import os
import time
import subprocess
import httpx
from ollama import chat
from memory.store import AegisMemory
from hands.browser import BrowserHands
from hands.wsl_windows import WSLWindowsInterop
from brain.schema import AgentStepPlan
from brain.verifier import verify_step

ACTION_VERBS = (
    "open ", "launch ", "start ", "send ", "message ", "reply ", "type ",
    "click ", "press ", "search ", "find ", "download ", "save ", "remember ",
    "close ", "move ", "delete ", "inspect ", "run ",
)

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
        self.wsl_win = WSLWindowsInterop()
        self.bridge = get_win_bridge_url()
        self.bridge_online = False
        self._apps_cache: list[str] = []
        self._apps_cache_ts: float = 0.0
        self._schema = AgentStepPlan.model_json_schema()
        self.recent_turns: list[str] = []

    def get_installed_apps(self, force_refresh: bool = False) -> list[str]:
        now = time.time()
        if not force_refresh and self._apps_cache and (now - self._apps_cache_ts) < 300.0:
            return self._apps_cache

        apps_set = set(self.wsl_win.scan_apps().keys())
        try:
            r = httpx.get(f"{self.bridge}/apps", timeout=1.0)
            apps_set.update(r.json().get("apps", {}).keys())
            self.bridge_online = True
        except Exception:
            self.bridge_online = False

        apps = sorted(apps_set) if apps_set else ["chromium", "terminal", "vscode"]
        self._apps_cache = apps
        self._apps_cache_ts = now
        return apps

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
            return f"BRIDGE_OFFLINE ({e})"

    def warmup(self):
        try:
            chat(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                keep_alive=-1,
                options={"num_predict": 1, "num_ctx": 4096},
            )
        except Exception as e:
            print(f"[Warning] Warmup skipped: {e}")

    def _format_observations(self, observations: list[str]) -> str:
        if not observations:
            return "Completed."
        if len(observations) == 1:
            return observations[0].split("]: ", 1)[-1]
        return "\n".join(observations)

    def _looks_like_action_request(self, text: str) -> bool:
        low = text.strip().lower()
        return any(low.startswith(v) or f" {v}" in f" {low}" for v in ACTION_VERBS)

    def run_turn(self, user_input: str, max_steps: int = 6) -> str:
        apps = self.get_installed_apps()
        recalled_mem = self.mem.recall_memories(user_input)
        recalled_skills = self.mem.recall_skills(user_input)
        observations: list[str] = []
        executed_signatures: set[tuple[str, str, str, str]] = set()
        is_compound = any(sep in user_input.lower() for sep in (" and ", " then ", ",", ";", " after "))
        promise_retries = 0

        for step_idx in range(max_steps):
            sys_prompt = (
                "You are AegisCore, a fast, zero-hallucination local PC automation agent.\n"
                "Respond ONLY with JSON matching AgentStepPlan: {tool, target, value, extra, message}.\n"
                "EXAMPLES:\n"
                '- User: "hey" -> {"tool":"done","target":"","value":"","extra":"","message":"Hey! Ready when you are. What would you like me to do?"}\n'
                '- User: "open whatsapp" -> {"tool":"launch_app","target":"whatsapp","value":"","extra":"","message":""}\n'
                '- User: "in whatsapp open message for gopi" -> {"tool":"in_app_search","target":"whatsapp","value":"gopi","extra":"open_first","message":""}\n'
                '- User: "send gopi a sticker" -> {"tool":"send_sticker","target":"whatsapp","value":"","extra":"gopi","message":""}\n'
                '- User: "send gopi hello bro" -> {"tool":"send_message","target":"whatsapp","value":"hello bro","extra":"gopi","message":""}\n'
                '- User: "open youtube" -> {"tool":"browser_tab","target":"https://youtube.com","value":"","extra":"open","message":""}\n'
                '- User: "save papers to D:\\Papers" -> {"tool":"save_memory","target":"rule","value":"Save research papers to D:\\Papers","extra":"","message":""}\n'
                "RULES:\n"
                "1. NEVER reply with tool='done' saying 'I will do X' without actually executing a tool first.\n"
                "2. Always populate 'message' when tool='done' or tool='ask_user'. Never leave 'message' empty for those two tools.\n"
                "3. Never invent app names, file paths, or UI controls not in Installed Apps, Memories, or Observations.\n"
                "4. NEVER repeat an action already listed in Observations So Far—immediately call tool='done' once requested actions succeed.\n\n"
                f"Installed Apps ({len(apps)}): {apps[:110]}\n"
                f"Recent Session History: {self.recent_turns[-4:]}\n"
                f"Recalled Memories: {recalled_mem}\n"
                f"Saved Skills: {recalled_skills}\n"
                f"Observations So Far: {observations}"
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
                    "num_predict": 128,
                },
            )

            plan = AgentStepPlan.model_validate_json(resp.message.content)

            if plan.tool == "done":
                # Zero-Promise Guard: block hallucinated promises when no tool has executed yet
                if not observations and self._looks_like_action_request(user_input) and promise_retries < 2:
                    promise_retries += 1
                    observations.append("SYSTEM_WARNING: You returned tool='done' without executing any tool. Execute the matching tool now.")
                    continue
                observations = [o for o in observations if not o.startswith("SYSTEM_WARNING:")]
                final_out = plan.message.strip() or (self._format_observations(observations) if observations else "Ready. What would you like me to do?")
                self.recent_turns.append(f"User: {user_input} -> AegisCore: {final_out}")
                return final_out

            observations = [o for o in observations if not o.startswith("SYSTEM_WARNING:")]

            if plan.tool == "ask_user":
                if not plan.message.strip():
                    return self._format_observations(observations) if observations else "Could you clarify what action you want me to run?"
                answer = input(f"\n[AegisCore] {plan.message.strip()}\nYou: ").strip()
                if not answer:
                    return "Action cancelled."
                user_input = f"{user_input} | User answered: {answer}"
                recalled_mem = self.mem.recall_memories(user_input)
                continue

            is_valid, note, plan = verify_step(plan, apps)
            if not is_valid:
                answer = input(f"\n[AegisCore Verification] {note}\nYou: ").strip()
                if not answer:
                    return "Action cancelled."
                user_input = f"{user_input} | User clarification: {answer}"
                apps = self.get_installed_apps(force_refresh=True)
                continue

            sig = (
                plan.tool,
                plan.target.strip().lower(),
                plan.value.strip().lower(),
                plan.extra.strip().lower(),
            )
            if sig in executed_signatures:
                out = self._format_observations(observations)
                self.recent_turns.append(f"User: {user_input} -> AegisCore: {out}")
                return out

            try:
                obs = self._execute_tool(plan, user_input)
                if plan.tool == "save_memory":
                    recalled_mem = self.mem.recall_memories(user_input)
            except Exception as e:
                obs = f"TOOL_ERROR [{plan.tool}]: {e}"

            executed_signatures.add(sig)
            observations.append(f"Step {step_idx + 1} [{plan.tool}]: {obs}")

            if not is_compound and not obs.startswith(("NOT_FOUND", "TOOL_ERROR", "BRIDGE_OFFLINE", "DOWNLOAD_PENDING")):
                out = self._format_observations(observations)
                self.recent_turns.append(f"User: {user_input} -> AegisCore: {out}")
                return out

        out = self._format_observations(observations)
        self.recent_turns.append(f"User: {user_input} -> AegisCore: {out}")
        return out

    def _execute_tool(self, plan: AgentStepPlan, user_input: str) -> str:
        if plan.tool == "launch_app":
            if self.bridge_online:
                return self._call_bridge("/launch", "POST", {"app_name": plan.target})
            return self.wsl_win.launch(plan.target)
        elif plan.tool == "in_app_search":
            open_first = plan.extra.strip().lower() != "search_only"
            return self.wsl_win.in_app_search(plan.target, plan.value, open_first=open_first)
        elif plan.tool == "send_message":
            return self.wsl_win.send_message(plan.target or "whatsapp", plan.value, recipient=plan.extra)
        elif plan.tool == "send_sticker":
            return self.wsl_win.send_sticker(plan.target or "whatsapp", recipient=plan.extra, hint=plan.value)
        elif plan.tool == "inspect_ui":
            if self.bridge_online:
                return self._call_bridge("/ui_tree", "GET", {"window_title": plan.target})
            return self.wsl_win.inspect_ui(plan.target)
        elif plan.tool == "click_ui":
            if self.bridge_online:
                return self._call_bridge("/click_control", "POST", {
                    "window_title": plan.target,
                    "control_name": plan.value,
                })
            return self.wsl_win.click_ui(plan.target, plan.value)
        elif plan.tool == "type_or_hotkey":
            keys = [k.strip() for k in plan.extra.split("+") if k.strip()]
            return self._call_bridge("/type_or_hotkey", "POST", {
                "text": plan.value,
                "keys": keys,
                "press_enter": plan.extra.lower() == "enter",
            })
        elif plan.tool == "browser_tab":
            return self.browser.tab_action(plan.extra or "open", plan.target)
        elif plan.tool == "download_item":
            return self.browser.download_item(plan.target, plan.value, plan.extra or "auto")
        elif plan.tool == "file_ops":
            return self._call_bridge("/file_ops", "POST", {
                "action": plan.extra or "find",
                "source": plan.target,
                "dest": plan.value,
            })
        elif plan.tool == "save_memory":
            saved = self.mem.add_memory(plan.value, plan.target or "preference")
            return f"Memorized: {saved}"
        elif plan.tool == "save_skill":
            steps_list = [s.strip() for s in plan.extra.split(";") if s.strip()]
            saved = self.mem.save_skill(plan.target, plan.value, steps_list)
            return f"Saved skill: {saved}"
        return f"UNHANDLED_TOOL: {plan.tool}"
