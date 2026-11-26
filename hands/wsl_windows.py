import subprocess
from pathlib import Path

class WSLWindowsInterop:
    def __init__(self):
        self._apps_map: dict[str, str] = {}

    def scan_apps(self) -> dict[str, str]:
        apps: dict[str, str] = {}

        # 1. Common Windows browsers & tools on C:\
        known_bins = {
            "google chrome": Path("/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"),
            "chrome": Path("/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"),
            "brave": Path("/mnt/c/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe"),
            "microsoft edge": Path("/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
            "vlc": Path("/mnt/c/Program Files/VideoLAN/VLC/vlc.exe"),
            "obs studio": Path("/mnt/c/Program Files/obs-studio/bin/64bit/obs64.exe"),
            "blender": Path("/mnt/c/Program Files/Blender Foundation"),
        }
        for name, path in known_bins.items():
            if path.is_file():
                apps[name] = str(path)

        # 2. Windows Start Menu shortcuts (.lnk) via /mnt/c
        shortcut_roots = [
            Path("/mnt/c/ProgramData/Microsoft/Windows/Start Menu/Programs"),
        ]
        users_dir = Path("/mnt/c/Users")
        if users_dir.exists():
            for user_folder in users_dir.iterdir():
                if user_folder.name in {"Public", "Default", "Default User", "All Users"}:
                    continue
                start_menu = user_folder / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs"
                desktop = user_folder / "Desktop"
                if start_menu.exists():
                    shortcut_roots.append(start_menu)
                if desktop.exists():
                    shortcut_roots.append(desktop)

        for root in shortcut_roots:
            if not root.exists():
                continue
            try:
                for lnk in root.rglob("*.lnk"):
                    stem = lnk.stem.lower()
                    if "uninstall" not in stem:
                        apps[stem] = str(lnk)
            except PermissionError:
                continue

        self._apps_map = apps
        return apps

    def launch(self, app_name: str) -> str:
        if not self._apps_map:
            self.scan_apps()
        query = app_name.lower().strip()
        target = self._apps_map.get(query)
        if not target:
            matches = [k for k in self._apps_map if query in k or k in query]
            if not matches:
                return f"NOT_FOUND: '{app_name}' not found on Windows."
            target = self._apps_map[matches[0]]

        win_path = subprocess.check_output(["wslpath", "-w", target]).decode().strip()
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", win_path],
            cwd="/mnt/c",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"LAUNCHED_VIA_WSL_INTEROP: {win_path}"
