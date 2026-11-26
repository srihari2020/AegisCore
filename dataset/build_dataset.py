import json
import random
from pathlib import Path

SYSTEM_PROMPT = (
    "You are AegisCore, a zero-hallucination local PC automation agent.\n"
    "Return valid JSON matching the AgentStepPlan schema.\n"
    "STRICT RULES:\n"
    "1. Never invent app names, file paths, or UI controls not present in Context or Observations.\n"
    "2. If required information (folder path, target recipient, ambiguous app, destructive action) is missing, choose tool='ask_user'.\n"
    "3. After launching an unfamiliar app, call tool='inspect_ui' before calling 'click_ui'.\n"
    "4. When the user states a preference or correction, call tool='save_memory'.\n"
    "5. Only choose tool='done' after all requested actions succeed or when answering a pure question."
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

def plan_json(grounding_check: str, **step_kwargs) -> str:
    step = {
        "tool": "done",
        "app_name": "",
        "window_title": "",
        "control_name": "",
        "text": "",
        "keys": [],
        "press_enter": False,
        "browser_action": "",
        "url_or_query": "",
        "save_dir": "",
        "filename": "auto",
        "file_action": "",
        "source": "",
        "dest": "",
        "category": "preference",
        "fact": "",
        "skill_name": "",
        "trigger_phrase": "",
        "steps": [],
        "question": "",
        "final_answer": "",
    }
    step.update(step_kwargs)
    return json.dumps({"grounding_check": grounding_check, "step": step}, ensure_ascii=False)

def generate(n: int = 800) -> list[dict]:
    rng = random.Random(42)
    rows = []

    for i in range(n):
        case = i % 8
        apps = rng.sample(APPS_POOL, 6)

        if case == 0:
            # 1. Open tab + search
            site, url = rng.choice(SITES)
            topic = rng.choice(TOPICS)
            ctx = f"Installed Apps: {apps}\nRecalled Memories: []\nSaved Skills: []\nExecution Observations So Far: []"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": f"Open {site} in a new tab and search for {topic}."},
                {"role": "assistant", "content": plan_json(
                    f"Action is browser_tab open on {url}.",
                    tool="browser_tab", browser_action="open", url_or_query=url
                )},
            ]})

        elif case == 1:
            # 2. Download with recalled memory path
            label, folder = rng.choice(FOLDERS)
            topic = rng.choice(TOPICS)
            ctx = f"Installed Apps: {apps}\nRecalled Memories: ['Save {label} to {folder}']\nSaved Skills: []\nExecution Observations So Far: ['Step 1 [browser_tab]: Opened tab']"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": f"Download the {label} about {topic} from this tab."},
                {"role": "assistant", "content": plan_json(
                    f"Recalled memory specifies save_dir='{folder}' for {label}.",
                    tool="download_item", url_or_query="active_tab_download", save_dir=folder, filename="auto"
                )},
            ]})

        elif case == 2:
            # 3. Missing download path -> anti-hallucination ask_user
            ctx = f"Installed Apps: {apps}\nRecalled Memories: []\nSaved Skills: []\nExecution Observations So Far: []"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": "Download this dataset file for me."},
                {"role": "assistant", "content": plan_json(
                    "MISSING_INFO: No target folder found in Recalled Memories or prompt.",
                    tool="ask_user",
                    question="Which folder should I save this dataset into? Once you tell me, I will remember it for future datasets."
                )},
            ]})

        elif case == 3:
            # 4. Uninstalled app -> anti-hallucination refusal/clarification
            ctx = f"Installed Apps: ['chrome', 'vlc', 'vscode']\nRecalled Memories: []\nSaved Skills: []\nExecution Observations So Far: []"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": "Open DaVinci Resolve and start a project."},
                {"role": "assistant", "content": plan_json(
                    "MISSING_INFO: 'davinci resolve' is not present in Installed Apps.",
                    tool="ask_user",
                    question="DaVinci Resolve is not in your installed apps list. Would you like me to search and download its installer first?"
                )},
            ]})

        elif case == 4:
            # 5. Newly installed app -> launch then inspect_ui
            slug, title, ctrls, _, _ = rng.choice(WORKFLOWS)
            if slug not in apps:
                apps.append(slug)
            ctx = f"Installed Apps: {apps}\nRecalled Memories: []\nSaved Skills: []\nExecution Observations So Far: ['Step 1 [launch_app]: launched {slug}']"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": f"I just installed {title}. Open it and use it to process my file."},
                {"role": "assistant", "content": plan_json(
                    f"{title} launched; inspecting UI tree before clicking any controls.",
                    tool="inspect_ui", window_title=title
                )},
            ]})

        elif case == 5:
            # 6. Click observed UI control + save skill
            slug, title, ctrls, skill_name, trigger = rng.choice(WORKFLOWS)
            ctx = (
                f"Installed Apps: {apps}\nRecalled Memories: []\nSaved Skills: []\n"
                f"Execution Observations So Far: ['Step 1 [inspect_ui]: {{\"window\": \"{title}\", \"elements\": [{{\"type\": \"Button\", \"name\": \"{ctrls[0]}\"}}, {{\"type\": \"Button\", \"name\": \"{ctrls[1]}\"}}]}}']"
            )
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": f"Click {ctrls[1]} and save this workflow as {skill_name}."},
                {"role": "assistant", "content": plan_json(
                    f"Control '{ctrls[1]}' verified in inspect_ui output.",
                    tool="click_ui", window_title=title, control_name=ctrls[1]
                )},
            ]})

        elif case == 6:
            # 7. Save user preference / correction
            label, folder = rng.choice(FOLDERS)
            ctx = f"Installed Apps: {apps}\nRecalled Memories: []\nSaved Skills: []\nExecution Observations So Far: []"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": f"Remember that whenever I download {label}, always save them to {folder}."},
                {"role": "assistant", "content": plan_json(
                    f"User explicitly stated a persistent storage rule for {label}.",
                    tool="save_memory", category="rule", fact=f"Always save {label} to {folder}."
                )},
            ]})

        else:
            # 8. Completion & grounded final answer after tool execution
            site, url = rng.choice(SITES)
            ctx = f"Installed Apps: {apps}\nRecalled Memories: []\nSaved Skills: []\nExecution Observations So Far: ['Step 1 [browser_tab]: Opened tab 1: {site}']"
            rows.append({"messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{ctx}"},
                {"role": "user", "content": f"Open {site}."},
                {"role": "assistant", "content": plan_json(
                    f"Observation confirms {site} tab is already open.",
                    tool="done", final_answer=f"Opened {site} ({url}) in a new browser tab."
                )},
            ]})

    return rows

if __name__ == "__main__":
    dataset = generate(800)
    out = Path("dataset/aegiscore_train.jsonl")
    with out.open("w", encoding="utf-8") as f:
        for row in dataset:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Generated {len(dataset)} schema-aligned training records at {out}")
