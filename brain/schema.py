from typing import Literal
from pydantic import BaseModel, Field

ToolName = Literal[
    "done",
    "launch_app",
    "in_app_search",
    "send_message",
    "send_sticker",
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
        description="Message text, sticker hint, search query, UI control name, save_dir, destination path, or memory fact.",
    )
    extra: str = Field(
        default="",
        description="Recipient contact name (for send_message/send_sticker), in_app_search mode, browser_tab action, file_ops action, or skill steps.",
    )
    message: str = Field(
        default="",
        description="Required non-empty final response when tool='done', or non-empty clarifying question when tool='ask_user'.",
    )
