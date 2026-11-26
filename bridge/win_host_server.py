import os
import shutil
import subprocess
import winreg
from pathlib import Path
from fastapi import FastAPI
from pydantic import BaseModel
from pywinauto import Desktop
import pyautogui

app = FastAPI(title="AegisCore Windows Host Bridge")

class LaunchReq(BaseModel):
    app_name: str

class ClickReq(BaseModel):
    window_title: str
    control_name: str

class TypeReq(BaseModel):
    text: str = ""
    keys: list[str] = []
    press_enter: bool = False

class FileOpReq(BaseModel):
    action: str
    source: str
    dest: str = ""

@app.get("/health")
def health():
    return {"status": "online"}

@app.get("/apps")
def scan_installed_apps():
    apps = {}
    start_dirs = [
        Path(os.environ["PROGRAMDATA"]) / r"Microsoft\Windows\Start Menu\Programs",
        Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs",
    ]
    for base in start_dirs:
        if base.exists():
            for lnk in base.rglob("*.lnk"):
                apps[lnk.stem.lower()] = str(lnk)

    reg_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, reg_path) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    sub = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, sub) as subkey:
                        exe_path, _ = winreg.QueryValueEx(subkey, "")
                        if exe_path:
                            apps[Path(sub).stem.lower()] = exe_path.strip('"')
        except OSError:
            continue
    return {"apps": apps}

@app.post("/launch")
def launch_app(req: LaunchReq):
    apps = scan_installed_apps()["apps"]
    query = req.app_name.lower().strip()
    target = apps.get(query)
    if not target:
        matches = [k for k in apps if query in k]
        if not matches:
            return {"status": "not_found", "available_sample": list(apps.keys())[:30]}
        target = apps[matches[0]]
    subprocess.Popen(["cmd", "/c", "start", "", target], shell=True)
    return {"status": "launched", "target": target}

@app.get("/ui_tree")
def inspect_active_ui(window_title: str = "", max_items: int = 60):
    desktop = Desktop(backend="uia")
    win = desktop.window(title_re=f".*{window_title}.*") if window_title else desktop.top_window()
    elements = []
    for ctrl in win.descendants()[:max_items]:
        title = ctrl.window_text().strip()
        ctype = ctrl.friendly_class_name()
        if title:
            elements.append({"type": ctype, "name": title})
    return {"window": win.window_text(), "elements": elements}

@app.post("/click_control")
def click_control(req: ClickReq):
    win = Desktop(backend="uia").window(title_re=f".*{req.window_title}.*")
    ctrl = win.child_window(title_re=f".*{req.control_name}.*", found_index=0)
    ctrl.click_input()
    return {"status": "clicked", "control": req.control_name}

@app.post("/type_or_hotkey")
def type_or_hotkey(req: TypeReq):
    if req.keys:
        pyautogui.hotkey(*req.keys)
    if req.text:
        pyautogui.write(req.text, interval=0.02)
    if req.press_enter:
        pyautogui.press("enter")
    return {"status": "executed"}

@app.post("/file_ops")
def file_ops(req: FileOpReq):
    src = Path(os.path.expandvars(req.source)).expanduser()
    if req.action == "find":
        parent = src.parent if src.parent.exists() else Path.home() / "Downloads"
        matches = [str(p) for p in parent.glob(f"*{src.name}*")][:20]
        return {"status": "ok", "matches": matches}
    elif req.action == "move" and req.dest:
        dst = Path(os.path.expandvars(req.dest)).expanduser()
        dst.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst / src.name))
        return {"status": "moved", "to": str(dst / src.name)}
    return {"status": "unsupported_or_requires_confirmation"}
