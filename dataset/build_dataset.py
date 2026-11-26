import json
import random
from pathlib import Path

SYSTEM_PROMPT = (
    "You are AegisCore, a fast, zero-hallucination local PC automation agent.\n"
    "Respond ONLY with JSON matching AgentStepPlan: {tool, target, value, extra, message}.\n"
    "RULES:\n"
    "1. Always populate 'message' with a helpful reply when tool='done' or a specific question when tool='ask_user'. Never leave 'message' empty for those two tools.\n"
    "2. Never invent app names, file paths, or UI controls not in Installed Apps, Memories, or Observations.\n"
    "3. After an action succeeds in Observations and no further steps are needed, call tool='done' with a clear confirmation in 'message'."
)

APPS_POOL = [
    "google chrome", "brave", "firefox", "vscode", "cursor", "vlc", "handbrake",
    "obs64", "blender", "fusion360", "spotify", "telegram", "discord",
    "explorer", "notepad", "terminal", "audacity", "gimp", "qbittorrent"
]

SITES = [
    ("YouTube", "https://youtube.com"),
    ("GitHub", "https://github.com"),
    ("Hugging Face", "https://huggingface.co"),
    ("arXiv", "https://arxiv.org"),
    ("Reddit", "https://reddit.com"),
]

TOPICS = [
    "QLoRA quantization", "llama.cpp GGUF", "ESP32 PCA9685 servo",
    "FastAPI async", "ChromaDB embeddings", "PyTorch CUDA"
]

FOLDERS = [
    ("research papers", r"D:\Documents\Papers"),
    ("datasets", r"D:\AI\Datasets"),
    ("videos", r"D:\Media\Clips"),
    ("installers", r"D:\Software\Setups"),
    ("invoices", r"D:\Finance\Invoices"),
]

WORKFLOWS = [
    ("handbrake", "HandBrake", ["Open Source", "Start Encode"], "compress_video", "compress video in HandBrake"),
    ("audacity", "Audacity", ["File", "Export Audio"], "export_mp3", "export audio as MP3 in Audacity"),
    ("obs64", "OBS Studio", ["Start Recording", "Stop Recording"], "obs_record", "start recording in OBS"),
    ("blender", "Blender", ["Render", "Render Image"], "blender_render", "render frame in Blender"),
]

GREETINGS = [
    ("hey", "Hey! Ready when you are. What would you like me to do?"),
    ("hello aegiscore", "Hello! Tell me which app, tab, download, or workflow you want to run."),
    ("what can you do", "I can launch Windows/Linux apps, control browser tabs and downloads, inspect and click inside app menus, remember your preferences, and save multi-step workflows."),
]

def plan_json(tool: str, target: str = "", value: str = "", extra: str = "", message: str = "") -> str:
    return json.dumps(
        {"tool": tool, "target": target, "value": value, "extra": extra, "message": message},
        ensure_ascii=False,
    )

def generate(n: int = 900) -> list[dict]:
    rng = random.Random(42)
    rows = []

    for i in range(n):
        case = i % 9
        apps = rng.sample(APPS_POOL, 6)

        if case == 0:
            # Conversational greeting / capability query -> immediate done
            prompt, reply = rng.choice(GREETINGS)
            ctx = f"Installed Apps ({len(apps)}): {apps}\nRecalled Memories: []\nSaved Skills: []\nObservations So Far: []"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": plan_json("done", message=reply)},
            ]})

        elif case == 1:
            # Launch installed app
            app = rng.choice(apps)
            ctx = f"Installed Apps ({len(apps)}): {apps}\nRecalled Memories: []\nSaved Skills: []\nObservations So Far: []"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": f"Open {app}"},
                {"role": "assistant", "content": plan_json("launch_app", target=app)},
            ]})

        elif case == 2:
            # Open browser tab
            site, url = rng.choice(SITES)
            ctx = f"Installed Apps ({len(apps)}): {apps}\nRecalled Memories: []\nSaved Skills: []\nObservations So Far: []"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": f"Open {site} in a new tab."},
                {"role": "assistant", "content": plan_json("browser_tab", target=url, extra="open")},
            ]})

        elif case == 3:
            # Download routed via recalled memory
            label, folder = rng.choice(FOLDERS)
            topic = rng.choice(TOPICS)
            ctx = f"Installed Apps ({len(apps)}): {apps}\nRecalled Memories: ['Save {label} to {folder}']\nSaved Skills: []\nObservations So Far: ['Step 1 [browser_tab]: Opened tab']"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": f"Download the {label} about {topic}."},
                {"role": "assistant", "content": plan_json("download_item", target="active_tab_download", value=folder, extra="auto")},
            ]})

        elif case == 4:
            # Missing download path -> ask_user
            ctx = f"Installed Apps ({len(apps)}): {apps}\nRecalled Memories: []\nSaved Skills: []\nObservations So Far: []"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": "Download this dataset for me."},
                {"role": "assistant", "content": plan_json(
                    "ask_user",
                    message="Which folder should I save this dataset into? Once you tell me, I will remember it for future datasets."
                )},
            ]})

        elif case == 5:
            # Uninstalled app -> anti-hallucination ask_user
            ctx = "Installed Apps (3): ['google chrome', 'vlc', 'vscode']\nRecalled Memories: []\nSaved Skills: []\nObservations So Far: []"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": "Open DaVinci Resolve"},
                {"role": "assistant", "content": plan_json(
                    "ask_user",
                    message="DaVinci Resolve is not in your installed apps list. Would you like me to search and download its installer first?"
                )},
            ]})

        elif case == 6:
            # Newly installed app -> inspect_ui after launch
            slug, title, ctrls, _, _ = rng.choice(WORKFLOWS)
            if slug not in apps:
                apps.append(slug)
            ctx = f"Installed Apps ({len(apps)}): {apps}\nRecalled Memories: []\nSaved Skills: []\nObservations So Far: ['Step 1 [launch_app]: Launched {slug}']"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": f"I just downloaded {title}. Open it and check its controls."},
                {"role": "assistant", "content": plan_json("inspect_ui", target=title)},
            ]})

        elif case == 7:
            # Save memory preference
            label, folder = rng.choice(FOLDERS)
            ctx = f"Installed Apps ({len(apps)}): {apps}\nRecalled Memories: []\nSaved Skills: []\nObservations So Far: []"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": f"Remember that whenever I download {label}, save them to {folder}."},
                {"role": "assistant", "content": plan_json("save_memory", target="rule", value=f"Always save {label} to {folder}.")},
            ]})

        else:
            # Final confirmation after tool execution
            app = rng.choice(apps)
            ctx = f"Installed Apps ({len(apps)}): {apps}\nRecalled Memories: []\nSaved Skills: []\nObservations So Far: ['Step 1 [launch_app]: LAUNCHED_VIA_WSL_INTEROP: {app}']"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": f"Open {app}"},
                {"role": "assistant", "content": plan_json("done", message=f"Opened {app}.")},
            ]})

    return rows

if __name__ == "__main__":
    dataset = generate(900)
    out = Path("dataset/aegiscore_train.jsonl")
    with out.open("w", encoding="utf-8") as f:
        for row in dataset:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Generated {len(dataset)} compact 5-field training records at {out}")
