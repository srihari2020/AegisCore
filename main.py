import os
import ollama
from brain.agent import AegisAgent

def resolve_model() -> str:
    if os.environ.get("AEGIS_MODEL"):
        return os.environ["AEGIS_MODEL"]
    try:
        models = [m.model for m in ollama.list().models]
        for candidate in ("aegiscore:latest", "aegiscore", "qwen2.5:3b"):
            if candidate in models:
                return candidate
    except Exception:
        pass
    return "qwen2.5:3b"

def main():
    model = resolve_model()
    agent = AegisAgent(model_name=model)
    print(f"Warming up Planner ({model}) + Vision ({agent.vision.vision_model}) in GPU VRAM...")
    agent.warmup()
    apps = agent.get_installed_apps(force_refresh=True)
    mcp_tools = agent.mcp.discover_all_tools()
    mode = "Full UIA Bridge" if agent.bridge_online else "WSL2 Direct Interop"
    print(
        f"AegisCore JARVIS Online | Brain: {model} | Vision: {agent.vision.vision_model} "
        f"| Mode: {mode} | Apps: {len(apps)} | MCP Tools: {len(mcp_tools)}"
    )
    print("Type a command (or 'exit' to quit):\n")

    while True:
        try:
            cmd = input("You: ").strip()
            if not cmd:
                continue
            if cmd.lower() in {"exit", "quit"}:
                break
            result = agent.run_turn(cmd)
            print(f"\nAegisCore:\n{result}\n")
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    main()
