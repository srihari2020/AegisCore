import json
import random
from pathlib import Path

SYSTEM_BASE = (
    "You are AegisCore, a local-first autonomous PC assistant. "
    "Convert user commands into structured tool calls using live OS context, recalled memories, and saved skills. "
    "Never guess missing details or run destructive actions without calling `ask_user` first."
)

APPS_POOL = [
    "chrome", "brave", "firefox", "vscode", "cursor", "vlc", "handbrake",
    "obs64", "blender", "fusion360", "spotify", "telegram", "discord",
    "explorer", "notepad", "terminal", "audacity", "gimp", "qbittorrent"
]

SITES = [
    ("YouTube", "https://youtube.com"),
    ("GitHub", "https://github.com"),
    ("Hugging Face", "https://huggingface.co"),
    ("arXiv", "https://arxiv.org"),
    ("Reddit", "https://reddit.com"),
    ("Google Scholar", "https://scholar.google.com"),
]

TOPICS = [
    "QLoRA fine-tuning", "llama.cpp GGUF quantization", "ESP32 servo control",
    "FastAPI async streaming", "ChromaDB metadata filtering", "PyTorch CUDA memory optimization"
]

DOWNLOAD_DIRS = [
    ("research papers", r"D:\Documents\Papers"),
    ("datasets", r"D:\AI\Datasets"),
    ("videos", r"D:\Media\Clips"),
    ("installers", r"D:\Software\Setups"),
    ("invoices", r"D:\Finance\Invoices"),
]

UI_WORKFLOWS = [
    ("handbrake", "HandBrake", ["Open Source", "Start Encode"], "compress_video", "compress video in HandBrake"),
    ("audacity", "Audacity", ["File", "Export Audio"], "export_mp3", "export audio as MP3 in Audacity"),
    ("obs64", "OBS Studio", ["Start Recording", "Stop Recording"], "obs_quick_record", "start recording screen in OBS"),
    ("blender", "Blender", ["Render", "Render Image"], "blender_render_frame", "render current frame in Blender"),
]

def make_sample(system_ctx: str, turns: list[dict]) -> dict:
    return {"messages": [{"role": "system", "content": f"{SYSTEM_BASE}\n{system_ctx}"}] + turns}

def generate_dataset(count: int = 400) -> list[dict]:
    rng = random.Random(42)
    records = []

    for i in range(count):
        mode = i % 7
        apps = rng.sample(APPS_POOL, 6)

        if mode == 0:
            # Tab opening + search + download routed via recalled memory
            site_name, url = rng.choice(SITES)
            topic = rng.choice(TOPICS)
            label, folder = rng.choice(DOWNLOAD_DIRS)
            ctx = f"Installed Apps: {apps}\nRecalled Memories: ['Save {label} to {folder}']\nSaved Skills: []"
            records.append(make_sample(ctx, [
                {"role": "user", "content": f"Open {site_name}, search for {topic}, and download the top result."},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"function": {"name": "browser_tab", "arguments": {"action": "open", "url_or_query": url}}},
                        {"function": {"name": "browser_tab", "arguments": {"action": "search", "url_or_query": topic}}},
                        {"function": {"name": "download_item", "arguments": {"url": "top_search_result", "save_dir": folder, "filename": "auto"}}},
                    ],
                },
            ]))

        elif mode == 1:
            # Newly installed app discovery & UI tree inspection
            app_slug, win_title, controls, _, _ = rng.choice(UI_WORKFLOWS)
            if app_slug not in apps:
                apps.append(app_slug)
            ctx = f"Installed Apps: {apps}\nRecalled Memories: []\nSaved Skills: []"
            records.append(make_sample(ctx, [
                {"role": "user", "content": f"I just downloaded {win_title}. Launch it and check what buttons are inside."},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"function": {"name": "launch_app", "arguments": {"app_name": app_slug}}},
                        {"function": {"name": "inspect_ui", "arguments": {"window_title": win_title}}},
                    ],
                },
            ]))

        elif mode == 2:
            # In-app UI clicking + saving workflow as a reusable skill
            app_slug, win_title, controls, skill_name, trigger = rng.choice(UI_WORKFLOWS)
            ui_desc = [f"Button('{c}')" for c in controls]
            ctx = f"Active Window: {win_title} | UI Controls: {ui_desc}\nRecalled Memories: []\nSaved Skills: []"
            records.append(make_sample(ctx, [
                {"role": "user", "content": f"Click {controls[0]} then {controls[1]}, and save this workflow as '{skill_name}'."},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"function": {"name": "click_ui", "arguments": {"window_title": win_title, "control_name": controls[0]}}},
                        {"function": {"name": "click_ui", "arguments": {"window_title": win_title, "control_name": controls[1]}}},
                        {
                            "function": {
                                "name": "save_skill",
                                "arguments": {
                                    "skill_name": skill_name,
                                    "trigger_phrase": trigger,
                                    "steps": [f"launch_app:{app_slug}"] + [f"click_ui:{c}" for c in controls],
                                },
                            }
                        },
                    ],
                },
            ]))

        elif mode == 3:
            # Multi-turn ambiguity clarification -> memory persistence
            ctx = f"Installed Apps: ['chrome', 'telegram', 'whatsapp']\nRecalled Memories: ['Contact: Phani (WhatsApp)', 'Contact: Phani Kumar (Telegram)']\nSaved Skills: []"
            records.append(make_sample(ctx, [
                {"role": "user", "content": "Download the latest build archive and send it to Phani."},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "ask_user",
                                "arguments": {
                                    "question": "Should I send the build archive to Phani on WhatsApp or Phani Kumar on Telegram?",
                                    "reason": "ambiguous_recipient",
                                },
                            }
                        }
                    ],
                },
                {"role": "user", "content": "Always send project builds to Phani on Telegram by default."},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "save_memory",
                                "arguments": {
                                    "category": "preference",
                                    "fact": "Send project builds to Phani Kumar on Telegram by default.",
                                },
                            }
                        },
                        {"function": {"name": "launch_app", "arguments": {"app_name": "telegram"}}},
                    ],
                },
            ]))

        elif mode == 4:
            # User correction -> immediate memory update
            label, folder = rng.choice(DOWNLOAD_DIRS)
            ctx = f"Installed Apps: {apps}\nRecalled Memories: ['Save {label} to C:\\Temp']\nSaved Skills: []"
            records.append(make_sample(ctx, [
                {"role": "user", "content": f"Stop saving {label} to C:\\Temp. Remember to always put them in {folder}."},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "save_memory",
                                "arguments": {
                                    "category": "rule",
                                    "fact": f"Always save {label} to {folder}.",
                                },
                            }
                        }
                    ],
                },
            ]))

        elif mode == 5:
            # Destructive file operation -> safety confirmation gate
            ctx = f"Installed Apps: {apps}\nRecalled Memories: []\nSaved Skills: []"
            records.append(make_sample(ctx, [
                {"role": "user", "content": "Delete all old .exe and .zip files inside my Downloads folder permanently."},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "ask_user",
                                "arguments": {
                                    "question": "Permanent deletion cannot be undone. Would you like me to move those installers and archives to the Recycle Bin instead, or confirm permanent delete?",
                                    "reason": "destructive_file_action",
                                },
                            }
                        }
                    ],
                },
            ]))

        else:
            # Replaying a previously learned skill
            app_slug, win_title, controls, skill_name, trigger = rng.choice(UI_WORKFLOWS)
            ctx = f"Installed Apps: {apps}\nRecalled Memories: []\nSaved Skills: ['{skill_name}: {trigger}']"
            records.append(make_sample(ctx, [
                {"role": "user", "content": f"Run my workflow to {trigger}."},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"function": {"name": "launch_app", "arguments": {"app_name": app_slug}}},
                        {"function": {"name": "click_ui", "arguments": {"window_title": win_title, "control_name": controls[0]}}},
                        {"function": {"name": "click_ui", "arguments": {"window_title": win_title, "control_name": controls[1]}}},
                    ],
                },
            ]))

    return records

if __name__ == "__main__":
    data = generate_dataset(420)
    out = Path("dataset/aegiscore_train.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in data:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Generated {len(data)} multi-scenario training records at {out}")
