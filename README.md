# AegisCore

**AegisCore** is a local-first, self-learning PC automation and cognitive agent powered by a fine-tuned small language model (`Qwen2.5-3B` / `7B`), persistent episodic memory (`ChromaDB`), dynamic OS application discovery, and a cross-environment UI automation bridge.

## Core Capabilities
- **Structured Tool Routing:** Converts natural language commands into strict, whitelisted JSON tool calls without raw shell execution.
- **Dynamic App Discovery:** Scans installed Windows/Linux applications at runtime so newly downloaded software works immediately without retraining.
- **In-App GUI Control & Skill Learning:** Inspects native UI Automation (UIA) trees (`pywinauto`) with vision-model fallback, saving verified multi-step workflows into a reusable skill library.
- **Episodic & Preference Memory:** Stores user habits, folder paths, and corrections in a local vector database and injects relevant context before every action.
- **Human-in-the-Loop Safety:** Pauses and asks clarifying questions (`ask_user`) whenever parameters are missing, entities collide, or destructive operations are requested.

## Architecture
- `brain/` — Agent planner, runtime context injector, and tool dispatcher
- `memory/` — ChromaDB episodic memory and post-task rule consolidation
- `skills/` — Self-learning workflow registry and deterministic macro replay
- `hands/` — Playwright browser controller and Linux desktop automation
- `bridge/` — Native Windows host daemon (`pywinauto` + Start Menu/Registry scanner) for WSL2 interoperability
- `dataset/` — Multi-scenario ChatML tool-calling dataset generator
- `training/` — Unsloth QLoRA fine-tuning and GGUF export pipeline for Ollama
