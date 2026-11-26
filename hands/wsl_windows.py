import json
import subprocess
from pathlib import Path

class WSLWindowsInterop:
    def __init__(self):
        self._apps_map: dict[str, str] = {}

    def _scan_uwp_start_apps(self) -> dict[str, str]:
        """Queries Windows Get-StartApps to index Microsoft Store / MSIX / UWP apps (e.g., WhatsApp)."""
        uwp_apps: dict[str, str] = {}
        try:
            ps_cmd = (
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"
            )
            raw = subprocess.check_output(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                cwd="/mnt/c",
                stderr=subprocess.DEVNULL,
                timeout=6.0,
            ).decode("utf-8", errors="ignore").strip()

            if not raw:
                return uwp_apps

            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                parsed = [parsed]

            for entry in parsed:
                name = (entry.get("Name") or "").strip().lower()
                app_id = (entry.get("AppID") or "").strip()
                if name and app_id and "uninstall" not in name:
                    uwp_apps[name] = f"uwp:{app_id}"
        except Exception:
            pass
        return uwp_apps

    def scan_apps(self) -> dict[str, str]:
        apps: dict[str, str] = {}

        # 1. Index all Windows Start Apps (covers Microsoft Store / UWP / MSIX apps like WhatsApp)
        apps.update(self._scan_uwp_start_apps())

        # 2. Common Win32 executables on C:\
        known_bins = {
            "google chrome": Path("/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"),
            "chrome": Path("/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"),
            "brave": Path("/mnt/c/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe"),
            "microsoft edge": Path("/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
            "vlc": Path("/mnt/c/Program Files/VideoLAN/VLC/vlc.exe"),
            "obs studio": Path("/mnt/c/Program Files/obs-studio/bin/64bit/obs64.exe"),
        }
        for name, path in known_bins.items():
            if path.is_file():
                apps[name] = str(path)

        # 3. Windows Start Menu & Desktop .lnk shortcuts
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

        if target.startswith("uwp:"):
            app_id = target[4:]
            subprocess.Popen(
                ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
                cwd="/mnt/c",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"LAUNCHED_UWP_APP: shell:AppsFolder\\{app_id}"

        win_path = subprocess.check_output(["wslpath", "-w", target]).decode().strip()
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", win_path],
            cwd="/mnt/c",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"LAUNCHED_VIA_WSL_INTEROP: {win_path}"
