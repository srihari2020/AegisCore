import os
import time
import subprocess
from pathlib import Path
import httpx
from ollama import chat
from memory.store import AegisMemory
from hands.browser import BrowserHands
from hands.wsl_windows import WSLWindowsInterop
from perception.screen_vision import ScreenVisionEngine
from perception.media_reader import MediaReader, resolve_wsl_path
from mcp_hub.manager import MCPHub
from brain.schema import AgentStepPlan
from brain.verifier import verify_step

ACTION_VERBS = (
    "open ", "launch ", "start ", "send ", "message ", "reply ", "type ",
    "click ", "press ", "search ", "find ", "download ", "save ", "remember ",
    "close ", "move ", "delete ", "inspect ", "run ", "see ", "look ", "read ",
    "watch ", "summarize ", "write ", "draft ", "create ", "mcp ",
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
        self.vision = ScreenVisionEngine()
        self.media = MediaReader(vision_model=self.vision.vision_model)
        self.mcp = MCPHub()
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

    def _looks_like_action_request(self, text: str) -> bool:
        low = text.strip().lower()
        return any(low.startswith(v) or f" {v}" in f" {low}" for v in ACTION_VERBS)

    def _jarvis_synthesize(self, user_input: str, observations: list[str], memories: list[str]) -> str:
        """Synthesizes execution results, documents, or screen observations in Jarvis voice + proactive ideas."""
        synth_prompt = (
            "You are AegisCore, an intelligent, calm, sharp local AI assistant inspired by JARVIS.\n"
            "Based strictly on the verified Tool Observations below (zero invented facts):\n"
            "1. Give a crisp, direct answer or confirmation of what was done/read/seen.\n"
            "2. Add a brief 'Next Ideas:' section with 2 practical, high-value follow-up actions you can execute right now.\n\n"
            f"User Request: {user_input}\n"
            f"Recalled Memories: {memories}\n"
            f"Verified Observations:\n" + "\n".join(observations)
        )
        resp = chat(
            model=self.model,
            messages=[{"role": "user", "content": synth_prompt}],
            keep_alive=-1,
            options={"temperature": 0.3, "num_ctx": 4096, "num_predict": 320},
        )
        return resp.message.content.strip()

    def run_turn(self, user_input: str, max_steps: int = 6) -> str:
        apps = self.get_installed_apps()
        recalled_mem = self.mem.recall_memories(user_input)
        recalled_skills = self.mem.recall_skills(user_input)
        mcp_tools = self.mcp.tool_catalog
        observations: list[str] = []
        executed_signatures: set[tuple[str, str, str, str]] = set()
        promise_retries = 0

        for step_idx in range(max_steps):
            sys_prompt = (
                "You are AegisCore, a multimodal, zero-hallucination local JARVIS agent.\n"
                "Respond ONLY with JSON matching AgentStepPlan: {tool, target, value, extra, message}.\n"
                "TOOL GUIDE:\n"
                "- see_screen: Capture Windows screen + numbered UI boxes and analyze what is visible (value=goal/question).\n"
                "- click_screen_target: Click an exact [ID] box discovered by see_screen (value=integer ID).\n"
                "- launch_app: Open any Windows/Store app (target=app_name).\n"
                "- in_app_search: Focus app, Ctrl+F, and open matching chat/item (target=app, value=query, extra='open_first').\n"
                "- send_message / send_sticker: Send text or sticker in app (target='whatsapp', value=text, extra=recipient).\n"
                "- browser_tab: Open/search/close web tab (target=url_or_query, extra='open'|'search'|'close').\n"
                "- download_item: Download file to folder (target=url, value=save_dir, extra='auto').\n"
                "- read_document: Read PDF, DOCX, Markdown, or code file (target=file_path).\n"
                "- watch_video: Transcribe audio + analyze keyframes of a video (target=video_path, value=question).\n"
                "- mcp_call: Invoke an MCP server tool (target=server_name, value=tool_name, extra=json_args_string).\n"
                "- write_content: Write a document, script, report, or email to workspace (target=filename, value=content).\n"
                "- save_memory / save_skill / ask_user / done.\n"
                "STRICT RULES:\n"
                "1. NEVER return tool='done' claiming you will do an action without executing the tool first.\n"
                "2. Never invent app names, file paths, or UI IDs not in Context or Observations.\n"
                "3. Once requested tools succeed in Observations, call tool='done' immediately.\n\n"
                f"Installed Apps ({len(apps)}): {apps[:100]}\n"
                f"MCP Tools Available: {mcp_tools[:30]}\n"
                f"Recent Turns: {self.recent_turns[-3:]}\n"
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
                    "num_predict": 180,
                },
            )

            plan = AgentStepPlan.model_validate_json(resp.message.content)

            if plan.tool == "done":
                if not observations and self._looks_like_action_request(user_input) and promise_retries < 2:
                    promise_retries += 1
                    observations.append("SYSTEM_WARNING: Execute the matching tool before returning tool='done'.")
                    continue
                observations = [o for o in observations if not o.startswith("SYSTEM_WARNING:")]
                if observations:
                    final_out = self._jarvis_synthesize(user_input, observations, recalled_mem)
                else:
                    final_out = plan.message.strip() or "Ready when you are, sir. What would you like to tackle?"
                self.recent_turns.append(f"User: {user_input} -> AegisCore: {final_out[:240]}")
                return final_out

            observations = [o for o in observations if not o.startswith("SYSTEM_WARNING:")]

            if plan.tool == "ask_user":
                if not plan.message.strip():
                    return self._jarvis_synthesize(user_input, observations, recalled_mem) if observations else "Could you specify the target file, app, or action?"
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
                plan.value.strip().lower()[:60],
                plan.extra.strip().lower()[:60],
            )
            if sig in executed_signatures:
                final_out = self._jarvis_synthesize(user_input, observations, recalled_mem)
                self.recent_turns.append(f"User: {user_input} -> AegisCore: {final_out[:240]}")
                return final_out

            try:
                obs = self._execute_tool(plan, user_input)
                if plan.tool == "save_memory":
                    recalled_mem = self.mem.recall_memories(user_input)
            except Exception as e:
                obs = f"TOOL_ERROR [{plan.tool}]: {e}"

            executed_signatures.add(sig)
            observations.append(f"Step {step_idx + 1} [{plan.tool}]: {obs}")

        final_out = self._jarvis_synthesize(user_input, observations, recalled_mem)
        self.recent_turns.append(f"User: {user_input} -> AegisCore: {final_out[:240]}")
        return final_out

    def _execute_tool(self, plan: AgentStepPlan, user_input: str) -> str:
        if plan.tool == "see_screen":
            decision = self.vision.see_and_reason(plan.value or user_input)
            click_note = ""
            if decision.target_element_id > 0 and decision.confidence >= 0.70 and any(
                w in user_input.lower() for w in ("click", "open", "select", "press", "tap")
            ):
                click_note = " | " + self.vision.click_element_id(decision.target_element_id)
            return (
                f"SCREEN_SEEN: {decision.screen_summary} | "
                f"Suggested Tag: [{decision.target_element_id}] (conf={decision.confidence:.2f}, {decision.reasoning}){click_note}"
            )
        elif plan.tool == "click_screen_target":
            eid = int("".join(ch for ch in plan.value if ch.isdigit()) or "-1")
            return self.vision.click_element_id(eid)
        elif plan.tool == "launch_app":
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
        elif plan.tool == "browser_tab":
            return self.browser.tab_action(plan.extra or "open", plan.target)
        elif plan.tool == "download_item":
            return self.browser.download_item(plan.target, plan.value, plan.extra or "auto")
        elif plan.tool == "read_document":
            return self.media.read_document(plan.target)
        elif plan.tool == "watch_video":
            return self.media.watch_video(plan.target, question=plan.value or user_input)
        elif plan.tool == "mcp_call":
            return self.mcp.call_tool(plan.target, plan.value, plan.extra)
        elif plan.tool == "write_content":
            fname = plan.target.strip() or "jarvis_draft.md"
            out_path = resolve_wsl_path(fname) if (":" in fname or fname.startswith("/")) else Path("workspace") / fname
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(plan.value, encoding="utf-8")
            return f"WROTE_FILE [{out_path}]:\n{plan.value}"
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
