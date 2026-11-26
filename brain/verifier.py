import difflib
from brain.schema import AgentStepPlan
from perception.media_reader import resolve_wsl_path

APP_ALIASES = {
    "google chrome": ["google chrome", "chrome", "chromium"],
    "chrome": ["chrome", "google chrome", "chromium"],
    "vs code": ["visual studio code", "vscode", "code"],
    "vscode": ["vscode", "visual studio code", "code"],
    "file explorer": ["file explorer", "explorer"],
    "edge": ["microsoft edge", "msedge"],
}

def verify_step(plan: AgentStepPlan, installed_apps: list[str]) -> tuple[bool, str, AgentStepPlan]:
    if plan.tool in {"launch_app", "in_app_search", "send_message", "send_sticker"}:
        if not plan.target.strip() and plan.tool in {"send_message", "send_sticker"}:
            plan.target = "whatsapp"

        query = plan.target.strip().lower()
        if not query:
            return False, "Which application would you like me to use?", plan

        if plan.tool == "in_app_search" and not plan.value.strip():
            return False, f"What contact or text should I search for inside {plan.target}?", plan

        if plan.tool == "send_message" and not plan.value.strip():
            return False, "What message text should I send?", plan

        if query in installed_apps:
            return True, "verified", plan

        for alias in APP_ALIASES.get(query, []):
            if alias in installed_apps:
                plan.target = alias
                return True, f"Resolved alias '{query}' -> '{alias}'", plan

        partial = [a for a in installed_apps if query in a or a in query]
        if partial:
            plan.target = partial[0]
            return True, f"Matched installed app '{partial[0]}'", plan

        high_conf = difflib.get_close_matches(query, installed_apps, n=1, cutoff=0.80)
        if high_conf:
            plan.target = high_conf[0]
            return True, f"Corrected '{query}' -> '{high_conf[0]}'", plan

        close = difflib.get_close_matches(query, installed_apps, n=3, cutoff=0.50)
        suggestion = f" Closest installed matches: {close}." if close else ""
        return (
            False,
            f"'{plan.target}' is not installed.{suggestion} Should I search and download it or open a different app?",
            plan,
        )

    elif plan.tool in {"read_document", "watch_video"}:
        raw_target = plan.target.strip()
        if not raw_target:
            return False, "Which exact local file path would you like me to read or analyze?", plan
        resolved = resolve_wsl_path(raw_target)
        if not resolved.is_file():
            return (
                False,
                f"I couldn't find '{raw_target}' on disk. Please provide the exact local file path (or tell me if you meant a YouTube/browser video).",
                plan,
            )

    elif plan.tool == "download_item":
        if not plan.value.strip():
            return False, "Which folder should I save this download into? (I'll remember it for next time.)", plan
        if not plan.target.strip():
            return False, "Which exact link or search result should I download?", plan

    elif plan.tool == "click_ui":
        if not plan.value.strip():
            return False, "Which button or menu item should I click inside the active window?", plan

    elif plan.tool == "file_ops":
        if plan.extra not in {"find", "move"}:
            return False, "Only 'find' and 'move' are permitted automatically. Do you want me to proceed?", plan
        if not plan.target.strip():
            return False, "Which file or folder path should I operate on?", plan

    return True, "verified", plan
