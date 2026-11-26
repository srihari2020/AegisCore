import difflib
from brain.schema import ToolStep

APP_ALIASES = {
    "google chrome": ["google chrome", "chrome", "chromium"],
    "chrome": ["chrome", "google chrome", "chromium"],
    "vs code": ["visual studio code", "vscode", "code"],
    "vscode": ["vscode", "visual studio code", "code"],
    "file explorer": ["file explorer", "explorer"],
    "edge": ["microsoft edge", "msedge"],
}

def verify_step(step: ToolStep, installed_apps: list[str], observations: list[str]) -> tuple[bool, str, ToolStep]:
    """
    Validates a model-proposed step against real OS state before execution.
    Returns (is_valid, reason_or_override_question, step).
    """
    if step.tool == "launch_app":
        query = step.app_name.strip().lower()
        if not query:
            return False, "Which application would you like me to open?", step

        # 1. Exact match
        if query in installed_apps:
            return True, "verified", step

        # 2. Alias expansion (e.g., 'google chrome' -> 'chrome')
        for alias in APP_ALIASES.get(query, []):
            if alias in installed_apps:
                step.app_name = alias
                return True, f"Resolved alias '{query}' -> '{alias}'", step

        # 3. Substring match
        partial = [a for a in installed_apps if query in a or a in query]
        if partial:
            step.app_name = partial[0]
            return True, f"Matched installed app '{partial[0]}'", step

        # 4. High-confidence typo auto-correction (e.g., 'chromeium' -> 'chromium')
        high_conf = difflib.get_close_matches(query, installed_apps, n=1, cutoff=0.82)
        if high_conf:
            step.app_name = high_conf[0]
            return True, f"Corrected typo '{query}' -> '{high_conf[0]}'", step

        # 5. Genuinely missing app -> block hallucination and ask user
        close = difflib.get_close_matches(query, installed_apps, n=3, cutoff=0.55)
        suggestion = f" Closest installed matches: {close}." if close else ""
        return (
            False,
            f"'{step.app_name}' was not found in your installed apps.{suggestion} Should I search and download it or open another app?",
            step,
        )

    elif step.tool == "download_item":
        if not step.save_dir.strip():
            return False, "Where should I save this download? (Once you tell me, I'll remember it for next time.)", step
        if not step.url_or_query.strip():
            return False, "Which exact link or search result should I download?", step

    elif step.tool == "click_ui":
        if not step.control_name.strip():
            return False, "Which button or menu item should I click inside the active window?", step

    elif step.tool == "file_ops":
        if step.file_action not in {"find", "move"}:
            return False, "Only 'find' and 'move' are permitted automatically. Do you want me to proceed?", step
        if not step.source.strip():
            return False, "Which file or folder path should I operate on?", step

    return True, "verified", step
