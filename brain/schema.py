from typing import Literal
from pydantic import BaseModel, Field

ToolName = Literal[
    "done",
    "see_screen",
    "click_screen_target",
    "launch_app",
    "in_app_search",
    "send_message",
    "send_sticker",
    "browser_tab",
    "download_item",
    "read_document",
    "watch_video",
    "mcp_call",
    "write_content",
    "inspect_ui",
    "click_ui",
    "file_ops",
    "save_memory",
    "save_skill",
    "ask_user",
]

class AgentStepPlan(BaseModel):
    tool: ToolName = Field(description="Whitelisted tool to execute, or 'done' to reply.")
    target: str = Field(
        default="",
        description="App name, file/video path, URL/search query, MCP server name, output filename, or memory category.",
    )
    value: str = Field(
        default="",
        description="Visual goal, element_id, message text, search query, MCP tool name, content body, save_dir, or memory fact.",
    )
    extra: str = Field(
        default="",
        description="Recipient contact, MCP JSON arguments, browser action (open|search|close), file action (find|move), or skill steps.",
    )
    message: str = Field(
        default="",
        description="Required non-empty Jarvis response + proactive suggestions when tool='done', or clarifying question when tool='ask_user'.",
    )
