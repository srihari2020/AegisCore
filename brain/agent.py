import os
import time
import subprocess
import httpx
from ollama import chat
from memory.store import AegisMemory
from hands.browser import BrowserHands
from brain.schema import AgentStepPlan
from brain.verifier import verify_step

def get_win_bridge_url() -> str:
    if os.environ.get("AEGIS_WIN_BRIDGE"):
        return os.environ["AEGIS_WIN_BRIDGE"]
    try:
        route = subprocess.check_output(["ip", "route", "show", "default"]).decode()
        host_ip = route.split()[2]
        return f"http://{host_ip}:8765"
    except Exception:
        return "http://127.0.0.1:8765"

class AegisAgent:
    def __init__(self, model_name: str = "aegiscore"):
        self.model = model_name
        self.mem = AegisMemory()
        self.browser = BrowserHands()
        self.bridge = get_win_bridge_url()
        self.bridge_online = False
        self._apps_cache: list[str] = []
        self._apps_cache_ts: float = 0.0
        self._schema = AgentStepPlan.model_json_schema()

    def get_installed_apps(self, force_refresh: bool = False) -> list[str]:
        now = time.time()
        if not force_refresh and self._apps_cache and (now - self._apps_cache_ts) < 30.0:
            return self._apps_cache
        try:
            r = httpx.get(f"{self.bridge}/apps", timeout=1.5)
            apps = sorted(r.json().get("apps", {}).keys())
            self.bridge_online = True
            self._apps_cache = apps
            self._apps_cache_ts = now
            return apps
        except Exception:
            self.bridge_online = False
            return ["chromium", "terminal", "vscode"]

    def _call_bridge(self, endpoint: str, method: str = "POST", payload: dict | None = None) -> str:
        try:
            if method == "GET":
                r = httpx.get(f"{self.bridge}{endpoint}", params=payload, timeout=5.0)
            else:
                r = httpx.post(f"{self.bridge}{endpoint}", json=payload, timeout=5.0)
            self.bridge_online = True
            return str(r.json())
        except Exception as e:
            self.bridge_online = False
            return (
                f"WINDOWS_BRIDGE_OFFLINE at {self.bridge}. "
                f"Start it on Windows with: python \\\\wsl$\\Ubuntu\\home\\srihari\\projects\\AegisCore\\bridge\\win_host_server.py ({e})"
            )

    def warmup(self):
        """Pins the model in GPU VRAM indefinitely so commands execute with zero cold-start lag."""
        try:
            chat(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                keep_alive=-1,
                options={"num_predict": 1, "num_ctx": 4096},
            )
        except Exception as e:
            print(f"[Warning] Warmup skipped: {e}")

    def run_turn(self, user_input: str, max_steps: int = 6) -> str:
        apps = self.get_installed_apps()
        recalled_mem = self.mem.recall_memories(user_input)
        recalled_skills = self.mem.recall_skills(user_input)
        observations: list[str] = []

        for step_idx in range(max_steps):
            sys_prompt = (
                "You are AegisCore, a zero-hallucination local PC automation agent.\n"
                "Return valid JSON matching the AgentStepPlan schema.\n"
                "STRICT RULES:\n"
                "1. For greetings, chat, or general questions requiring no PC action, immediately set tool='done' and write a clear, concise response in final_answer.\n"
                "2. Never invent app names, file paths, or UI controls not present in Context or Observations.\n"
                "3. Copy exact app names verbatim from Installed Apps.\n"
                "4. If required information (folder path, target recipient, ambiguous app, destructive action) is missing, choose tool='ask_user'.\n"
                "5. After launching an unfamiliar app, call tool='inspect_ui' before calling 'click_ui'.\n"
                "6. When the user states a preference or correction, call tool='save_memory'.\n"
                "7. Only choose tool='done' after all requested actions succeed or when answering directly.\n\n"
                f"Windows Bridge Online: {self.bridge_online}\n"
                f"Installed Apps ({len(apps)} total, sample): {apps[:90]}\n"
                f"Recalled Memories: {recalled_mem}\n"
                f"Saved Skills: {recalled_skills}\n"
                f"Execution Observations So Far: {observations}"
            )

            resp = chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_input},
                ],
                format=self._schema,
                keep_alive=-1,
                options={
                    "temperature": 0,
                    "top_p": 0.9,
                    "num_ctx": 4096,
                    "num_predict": 256,
                },
            )

            plan = AgentStepPlan.model_validate_json(resp.message.content)
            step = plan.step

            if step.tool == "done":
                return step.final_answer or ("\n".join(observations) if observations else "Completed.")

            if step.tool == "ask_user":
                answer = input(f"\n[AegisCore] {step.question}\nYou: ").strip()
                user_input = f"{user_input} | User answered: {answer}"
                recalled_mem = self.mem.recall_memories(user_input)
                continue

            is_valid, note, step = verify_step(step, apps, observations)
            if not is_valid:
                answer = input(f"\n[AegisCore Verification] {note}\nYou: ").strip()
                user_input = f"{user_input} | User clarification: {answer}"
                apps = self.get_installed_apps(force_refresh=True)
                continue

            if step.tool == "launch_app":
                obs = self._call_bridge("/launch", "POST", {"app_name": step.app_name})
            elif step.tool == "inspect_ui":
                obs = self._call_bridge("/ui_tree", "GET", {"window_title": step.window_title})
            elif step.tool == "click_ui":
                obs = self._call_bridge("/click_control", "POST", {
                    "window_title": step.window_title,
                    "control_name": step.control_name,
                })
            elif step.tool == "type_or_hotkey":
                obs = self._call_bridge("/type_or_hotkey", "POST", {
                    "text": step.text,
                    "keys": step.keys,
                    "press_enter": step.press_enter,
                })
            elif step.tool == "browser_tab":
                obs = self.browser.tab_action(step.browser_action or "open", step.url_or_query)
            elif step.tool == "download_item":
                obs = self.browser.download_item(step.url_or_query, step.save_dir, step.filename)
            elif step.tool == "file_ops":
                obs = self._call_bridge("/file_ops", "POST", {
                    "action": step.file_action,
                    "source": step.source,
                    "dest": step.dest,
                })
            elif step.tool == "save_memory":
                saved = self.mem.add_memory(step.fact, step.category)
                recalled_mem = self.mem.recall_memories(user_input)
                obs = f"MEMORIZED: {saved}"
            elif step.tool == "save_skill":
                saved = self.mem.save_skill(step.skill_name, step.trigger_phrase, step.steps)
                obs = f"SKILL_SAVED: {saved}"
            else:
                obs = f"UNHANDLED_TOOL: {step.tool}"

            observations.append(f"Step {step_idx + 1} [{step.tool}]: {obs}")

        return "\n".join(observations)
