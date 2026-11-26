import base64
import json
import re
import subprocess
from pathlib import Path

class WSLWindowsInterop:
    def __init__(self):
        self._apps_map: dict[str, str] = {}

    def _scan_uwp_start_apps(self) -> dict[str, str]:
        """Queries Windows Get-StartApps to index Microsoft Store / MSIX / UWP apps."""
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
        apps.update(self._scan_uwp_start_apps())

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

    @staticmethod
    def _clean_contact_query(raw_query: str) -> str:
        # Strip trailing relationship descriptors like "friend", "bro", "contact"
        cleaned = re.sub(r"\b(my\s+)?(friend|bro|bhai|contact|chat|message)\b", "", raw_query, flags=re.IGNORECASE)
        return " ".join(cleaned.split()).strip() or raw_query.strip()

    def in_app_search(self, app_name: str, search_query: str, open_first: bool = True) -> str:
        """Forces Windows foreground focus, searches inside app via UIA + Ctrl+F, and clicks the matching chat/item."""
        clean_query = self._clean_contact_query(search_query)
        self.launch(app_name)

        ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$win32Code = @"
using System;
using System.Runtime.InteropServices;
public class Win32Focus {{
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);

    public static void ForceForeground(IntPtr hWnd) {{
        keybd_event(0x12, 0, 0, UIntPtr.Zero); // Alt down (unlocks Windows foreground lock)
        ShowWindow(hWnd, 9); // SW_RESTORE
        BringWindowToTop(hWnd);
        SetForegroundWindow(hWnd);
        keybd_event(0x12, 0, 2, UIntPtr.Zero); // Alt up
    }}

    public static void ClickAt(int x, int y) {{
        SetCursorPos(x, y);
        System.Threading.Thread.Sleep(60);
        mouse_event(0x0002, 0, 0, 0, UIntPtr.Zero); // LEFTDOWN
        mouse_event(0x0004, 0, 0, 0, UIntPtr.Zero); // LEFTUP
    }}
}}
"@
Add-Type -TypeDefinition $win32Code

$appTitle = {json.dumps(app_name.strip())}
$query = {json.dumps(clean_query)}
$openFirst = {'$true' if open_first else '$false'}

$hwnd = [IntPtr]::Zero
for ($i = 0; $i -lt 15; $i++) {{
    $proc = Get-Process | Where-Object {{ $_.MainWindowTitle -like "*$appTitle*" -and $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
    if ($proc) {{
        $hwnd = $proc.MainWindowHandle
        break
    }}
    Start-Sleep -Milliseconds 300
}}

if ($hwnd -eq [IntPtr]::Zero) {{
    Write-Output "WINDOW_NOT_FOUND: Could not locate active window matching '$appTitle'"
    exit 0
}}

[Win32Focus]::ForceForeground($hwnd)
Start-Sleep -Milliseconds 350

$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)

# Try focusing the Search Edit control directly via UI Automation
$editCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Edit
)
$edits = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $editCond)
$searchFocused = $false
foreach ($el in $edits) {{
    $name = $el.Current.Name
    if ($name -match "Search|Find|chat") {{
        $rect = $el.Current.BoundingRectangle
        if ($rect.Width -gt 20 -and $rect.Height -gt 10) {{
            [Win32Focus]::ClickAt([int]($rect.X + $rect.Width / 2), [int]($rect.Y + $rect.Height / 2))
            $searchFocused = $true
            break
        }}
    }}
}}

if (-not $searchFocused) {{
    [System.Windows.Forms.SendKeys]::SendWait('^f')
    Start-Sleep -Milliseconds 250
}}

Set-Clipboard -Value $query
[System.Windows.Forms.SendKeys]::SendWait('^a')
Start-Sleep -Milliseconds 80
[System.Windows.Forms.SendKeys]::SendWait('^v')
Start-Sleep -Milliseconds 950

if ($openFirst) {{
    # Look for matching ListItem / DataItem in UIA tree and click its center
    $clickedName = ""
    $all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    $firstToken = ($query -split '\s+')[0]
    foreach ($item in $all) {{
        $ct = $item.Current.ControlType.ProgrammaticName
        $nm = $item.Current.Name
        if (($ct -eq "ControlType.ListItem" -or $ct -eq "ControlType.DataItem" -or $ct -eq "ControlType.Button") -and $nm -and ($nm -match [regex]::Escape($firstToken))) {{
            $r = $item.Current.BoundingRectangle
            if ($r.Width -gt 80 -and $r.Height -gt 28 -and $r.Y -gt 80) {{
                [Win32Focus]::ClickAt([int]($r.X + $r.Width / 2), [int]($r.Y + $r.Height / 2))
                $clickedName = $nm
                break
            }}
        }}
    }}

    if ($clickedName -ne "") {{
        Write-Output "OPENED_CHAT [$appTitle]: Searched '$query' and clicked '$clickedName'."
    }} else {{
        [System.Windows.Forms.SendKeys]::SendWait('{{DOWN}}{{ENTER}}')
        Write-Output "SEARCHED_AND_SELECTED [$appTitle]: Searched '$query' (keyboard fallback)."
    }}
}} else {{
    Write-Output "SEARCHED [$appTitle]: Typed '$query' in search bar."
}}
"""
        encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            cwd="/mnt/c",
            capture_output=True,
            text=True,
            timeout=15.0,
        )
        out = res.stdout.strip()
        return out if out else f"IN_APP_SEARCH [{app_name}]: Executed search for '{clean_query}'."
