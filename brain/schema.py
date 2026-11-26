from typing import Literal
from pydantic import BaseModel, Field

ToolName = Literal[
    "ask_user",
    "launch_app",
    "inspect_ui",
    "click_ui",
    "type_or_hotkey",
    "browser_tab",
    "download_item",
    "file_ops",
    "save_memory",
    "save_skill",
    "done",
]

class ToolStep(BaseModel):
    tool: ToolName = Field(description="Exact whitelisted tool name.")
    app_name: str = Field(default="", description="Target installed app name for launch_app.")
    window_title: str = Field(default="", description="Target window title for inspect_ui or click_ui.")
    control_name: str = Field(default="", description="Exact UI element name from inspect_ui for click_ui.")
    text: str = Field(default="", description="Text to type for type_or_hotkey.")
    keys: list[str] = Field(default_factory=list, description="Hotkey sequence e.g. ['ctrl', 's'].")
    press_enter: bool = Field(default=False, description="Press Enter after typing.")
    browser_action: Literal["", "open", "search", "close"] = Field(default="", description="Browser tab action.")
    url_or_query: str = Field(default="", description="URL or search query for browser_tab or download_item.")
    save_dir: str = Field(default="", description="Verified target directory path for download_item.")
    filename: str = Field(default="auto", description="Target filename or 'auto'.")
    file_action: Literal["", "find", "move"] = Field(default="", description="Safe file operation.")
    source: str = Field(default="", description="Source file path.")
    dest: str = Field(default="", description="Destination directory path.")
    category: str = Field(default="preference", description="Memory category: preference, contact, or rule.")
    fact: str = Field(default="", description="Fact or preference to memorize.")
    skill_name: str = Field(default="", description="Unique snake_case skill identifier.")
    trigger_phrase: str = Field(default="", description="Natural language trigger for this skill.")
    steps: list[str] = Field(default_factory=list, description="Ordered action steps for save_skill.")
    question: str = Field(default="", description="Clarifying question for ask_user.")
    final_answer: str = Field(default="", description="Grounded final response for the user when tool='done'.")

class AgentStepPlan(BaseModel):
    grounding_check: str = Field(
        description="Brief verification of facts from Installed Apps, Recalled Memories, and Observations. State 'MISSING_INFO' if any required detail is absent."
    )
    step: ToolStep = Field(description="Single next deterministic action to execute or 'done' to answer.")
