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
    print(f"Warming up {model} in GPU VRAM...")
    agent.warmup()
    apps = agent.get_installed_apps(force_refresh=True)
    bridge_status = f"ONLINE ({len(apps)} Windows apps indexed)" if agent.bridge_online else "OFFLINE (Windows apps unavailable until win_host_server.py runs)"
    print(f"AegisCore Online | Model: {model} | Bridge: {agent.bridge} [{bridge_status}]")
    print("Type a command (or 'exit' to quit):\n")

    while True:
        try:
            cmd = input("You: ").strip()
            if not cmd:
                continue
            if cmd.lower() in {"exit", "quit"}:
                break
            result = agent.run_turn(cmd)
            print(f"AegisCore:\n{result}\n")
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    main()
