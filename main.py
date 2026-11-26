import os
from brain.agent import AegisAgent

def main():
    model = os.environ.get("AEGIS_MODEL", "qwen2.5:3b")
    agent = AegisAgent(model_name=model)
    print(f"AegisCore Online | Model: {model} | Bridge: {agent.bridge}")
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
