import os
import subprocess
import httpx
from ollama import chat
from memory.store import AegisMemory
from hands.browser import BrowserHands

def get_win_bridge_url() -> str:
    if os.environ.get("AEGIS_WIN_BRIDGE"):
        return os.environ["AEGIS_WIN_BRIDGE"]
    # Auto-detect WSL2 Windows host IP if localhost forwarding isn't active
    try:
        route = subprocess.check_output(["ip", "route", "show", "default"]).decode()
        host_ip = route.split()[2]
        return f"http://{host_ip}:8765"
    except Exception:
        return "http://127.0.0.1:8765"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Ask the user a clarifying question when details are missing, ambiguous, or destructive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["question", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "launch_app",
            "description": "Launch an installed desktop application by name.",
            "parameters": {
                "type": "object",
                "properties": {"app_name": {"type": "string"}},
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_ui",
            "description": "Inspect live UI controls inside an open window.",
            "parameters": {
                "type": "object",
                "properties": {"window_title": {"type": "string"}},
                "required": ["window_title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_ui",
            "description": "Click a named button or menu inside an open window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "window_title": {"type": "string"},
                    "control_name": {"type": "string"},
                },
                "required": ["window_title", "control_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_tab",
            "description": "Open, search, or close browser tabs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["open", "search", "close"]},
                    "url_or_query": {"type": "string"},
                },
                "required": ["action", "url_or_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "download_item",
            "description": "Download a file or paper to a specific directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "save_dir": {"type": "string"},
                    "filename": {"type": "string"},
                },
                "required": ["url", "save_dir"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Persist a user preference, rule, or correction into long-term memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "fact": {"type": "string"},
                },
                "required": ["category", "fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_skill",
            "description": "Save a verified multi-step workflow into the reusable skill library.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "trigger_phrase": {"type": "string"},
                    "steps": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["skill_name", "trigger_phrase", "steps"],
            },
        },
    },
]

class AegisAgent:
    def __init__(self, model_name: str = "qwen2.5:3b"):
        self.model = model_name
        self.mem = AegisMemory()
        self.browser = BrowserHands()
        self.bridge = get_win_bridge_url()

    def _get_installed_apps(self) -> list[str]:
        try:
            r = httpx.get(f"{self.bridge}/apps", timeout=2.0)
            return list(r.json().get("apps", {}).keys())[:80]
        except Exception:
            return ["chromium", "terminal", "vscode"]

    def _call_bridge(self, endpoint: str, method: str = "POST", payload: dict | None = None) -> str:
        try:
            if method == "GET":
                r = httpx.get(f"{self.bridge}{endpoint}", params=payload, timeout=5.0)
            else:
                r = httpx.post(f"{self.bridge}{endpoint}", json=payload, timeout=5.0)
            return str(r.json())
        except Exception as e:
            return f"Windows bridge unreachable at {self.bridge} ({e}). Start win_host_server.py on Windows."

    def run_turn(self, user_input: str) -> str:
        apps = self._get_installed_apps()
        recalled_mem = self.mem.recall_memories(user_input)
        recalled_skills = self.mem.recall_skills(user_input)

        sys_prompt = (
            "You are AegisCore, a local-first autonomous PC assistant. "
            "Convert user commands into structured tool calls using live OS context, recalled memories, and saved skills. "
            "Never guess missing details or run destructive actions without calling `ask_user` first.\n"
            f"Installed Apps: {apps}\n"
            f"Recalled Memories: {recalled_mem}\n"
            f"Saved Skills: {recalled_skills}"
        )

        resp = chat(
            model=self.model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_input},
            ],
            tools=TOOLS,
        )

        calls = resp.message.tool_calls or []
        if not calls:
            return resp.message.content or "Done."

        logs = []
        for call in calls:
            fn = call.function.name
            args = call.function.arguments

            if fn == "ask_user":
                answer = input(f"\n[AegisCore Clarification] {args['question']}\nYou: ")
                return self.run_turn(f"{user_input} | User Clarification: {answer}")
            elif fn == "launch_app":
                logs.append(self._call_bridge("/launch", "POST", args))
            elif fn == "inspect_ui":
                logs.append(self._call_bridge("/ui_tree", "GET", args))
            elif fn == "click_ui":
                logs.append(self._call_bridge("/click_control", "POST", args))
            elif fn == "browser_tab":
                logs.append(self.browser.tab_action(args["action"], args["url_or_query"]))
            elif fn == "download_item":
                logs.append(self.browser.download_item(args["url"], args["save_dir"], args.get("filename", "auto")))
            elif fn == "save_memory":
                self.mem.add_memory(args["fact"], args.get("category", "preference"))
                logs.append(f"Memorized: {args['fact']}")
            elif fn == "save_skill":
                self.mem.save_skill(args["skill_name"], args["trigger_phrase"], args["steps"])
                logs.append(f"Saved skill '{args['skill_name']}'")

        return "\n".join(logs)
