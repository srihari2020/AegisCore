from typing import Literal
from pydantic import BaseModel, Field

ToolName = Literal[
    "done",
    "launch_app",
    "browser_tab",
    "download_item",
    "inspect_ui",
    "click_ui",
    "type_or_hotkey",
    "file_ops",
    "save_memory",
    "save_skill",
    "ask_user",
]

class AgentStepPlan(BaseModel):
    tool: ToolName = Field(description="Whitelisted tool to execute, or 'done' to reply.")
    target: str = Field(
        default="",
        description="App name, window title, URL/search query, source path, memory category, or skill name.",
    )
    value: str = Field(
        default="",
        description="UI control name, download save_dir, destination path, text/keys, memory fact, or skill trigger.",
    )
    extra: str = Field(
        default="",
        description="browser_tab action (open|search|close), file_ops action (find|move), filename, or skill steps.",
    )
    message: str = Field(
        default="",
        description="Required non-empty final response when tool='done', or non-empty clarifying question when tool='ask_user'.",
    )
