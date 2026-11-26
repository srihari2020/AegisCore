import asyncio
import json
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPHub:
    def __init__(self, config_path: str = "mcp_servers.json"):
        self.config_path = Path(config_path)
        self.servers: dict[str, dict] = {}
        self.tool_catalog: list[dict] = []
        self.reload_config()

    def reload_config(self):
        if not self.config_path.exists():
            self.servers = {}
            return
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            self.servers = data.get("servers", {})
        except Exception:
            self.servers = {}

    async def _discover_server(self, name: str, cfg: dict) -> list[dict]:
        params = StdioServerParameters(
            command=cfg["command"],
            args=cfg.get("args", []),
            env=cfg.get("env"),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.list_tools()
                return [
                    {
                        "server": name,
                        "tool": t.name,
                        "description": (t.description or "")[:140],
                    }
                    for t in res.tools
                ]

    def discover_all_tools(self) -> list[dict]:
        self.reload_config()
        if not self.servers:
            self.tool_catalog = []
            return []

        async def _gather():
            all_tools = []
            for srv_name, cfg in self.servers.items():
                try:
                    tools = await self._discover_server(srv_name, cfg)
                    all_tools.extend(tools)
                except Exception as e:
                    all_tools.append({"server": srv_name, "tool": "ERROR", "description": str(e)})
            return all_tools

        self.tool_catalog = asyncio.run(_gather())
        return self.tool_catalog

    def call_tool(self, server_name: str, tool_name: str, arguments_json: str) -> str:
        self.reload_config()
        cfg = self.servers.get(server_name)
        if not cfg:
            return f"MCP_SERVER_NOT_FOUND: '{server_name}'. Configured servers: {list(self.servers.keys())}"

        try:
            args = json.loads(arguments_json) if arguments_json.strip() else {}
        except json.JSONDecodeError as e:
            return f"MCP_INVALID_ARGS_JSON: {e}"

        async def _invoke():
            params = StdioServerParameters(
                command=cfg["command"],
                args=cfg.get("args", []),
                env=cfg.get("env"),
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=args)
                    chunks = [getattr(c, "text", str(c)) for c in result.content]
                    return "\n".join(chunks)

        try:
            out = asyncio.run(_invoke())
            return f"MCP [{server_name}.{tool_name}]: {out[:6000]}"
        except Exception as e:
            return f"MCP_CALL_ERROR [{server_name}.{tool_name}]: {e}"
