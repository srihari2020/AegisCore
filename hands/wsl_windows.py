import base64
import json
import re
import subprocess
from pathlib import Path

WIN32_HELPER_CS = r"""
using System;
using System.Runtime.InteropServices;
public class Win32Focus {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);

    public static void ForceForeground(IntPtr hWnd) {
        keybd_event(0x12, 0, 0, UIntPtr.Zero);
        ShowWindow(hWnd, 9);
        BringWindowToTop(hWnd);
        SetForegroundWindow(hWnd);
        keybd_event(0x12, 0, 2, UIntPtr.Zero);
    }

    public static void ClickAt(int x, int y) {
        SetCursorPos(x, y);
        System.Threading.Thread.Sleep(60);
        mouse_event(0x0002, 0, 0, 0, UIntPtr.Zero);
        mouse_event(0x0004, 0, 0, 0, UIntPtr.Zero);
    }
}
"""

class WSLWindowsInterop:
    def __init__(self):
        self._apps_map: dict[str, str] = {}

    def _run_ps(self, ps_script: str, timeout: float = 15.0) -> str:
        encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            cwd="/mnt/c",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return res.stdout.strip()

    def _scan_uwp_start_apps(self) -> dict[str, str]:
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
        cleaned = re.sub(r"\b(my\s+)?(friend|bro|bhai|contact|chat|message)\b", "", raw_query, flags=re.IGNORECASE)
        return " ".join(cleaned.split()).strip() or raw_query.strip()

    def in_app_search(self, app_name: str, search_query: str, open_first: bool = True) -> str:
        clean_query = self._clean_contact_query(search_query)
        self.launch(app_name)

        ps_template = r"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
__WIN32_CS__
'@

$appTitle = __APP_TITLE__
$query = __QUERY__
$openFirst = __OPEN_FIRST__

$hwnd = [IntPtr]::Zero
for ($i = 0; $i -lt 15; $i++) {
    foreach ($p in (Get-Process)) {
        if ($p.MainWindowHandle -ne 0 -and $p.MainWindowTitle -like "*$appTitle*") {
            $hwnd = $p.MainWindowHandle
            break
        }
    }
    if ($hwnd -ne [IntPtr]::Zero) { break }
    Start-Sleep -Milliseconds 300
}
if ($hwnd -eq [IntPtr]::Zero) { Write-Output "WINDOW_NOT_FOUND: '$appTitle'"; exit 0 }

[Win32Focus]::ForceForeground($hwnd)
Start-Sleep -Milliseconds 350

$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$editCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Edit
)
$edits = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $editCond)
$searchFocused = $false
foreach ($el in $edits) {
    if ($el.Current.Name -match "Search|Find|chat") {
        $rect = $el.Current.BoundingRectangle
        if ($rect.Width -gt 20 -and $rect.Height -gt 10) {
            [Win32Focus]::ClickAt([int]($rect.X + $rect.Width / 2), [int]($rect.Y + $rect.Height / 2))
            $searchFocused = $true
            break
        }
    }
}
if (-not $searchFocused) {
    [System.Windows.Forms.SendKeys]::SendWait('^f')
    Start-Sleep -Milliseconds 250
}

Set-Clipboard -Value $query
[System.Windows.Forms.SendKeys]::SendWait('^a')
Start-Sleep -Milliseconds 80
[System.Windows.Forms.SendKeys]::SendWait('^v')
Start-Sleep -Milliseconds 950

if ($openFirst) {
    $clickedName = ""
    $all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    $tokens = $query -split '\s+'
    $firstToken = $tokens[0]
    foreach ($item in $all) {
        $ct = $item.Current.ControlType.ProgrammaticName
        $nm = $item.Current.Name
        if (($ct -eq "ControlType.ListItem" -or $ct -eq "ControlType.DataItem" -or $ct -eq "ControlType.Button") -and $nm -and ($nm -match [regex]::Escape($firstToken))) {
            $r = $item.Current.BoundingRectangle
            if ($r.Width -gt 80 -and $r.Height -gt 28 -and $r.Y -gt 80) {
                [Win32Focus]::ClickAt([int]($r.X + $r.Width / 2), [int]($r.Y + $r.Height / 2))
                $clickedName = $nm
                break
            }
        }
    }
    if ($clickedName -ne "") {
        Write-Output "OPENED_CHAT [$appTitle]: Searched '$query' and clicked '$clickedName'."
    } else {
        [System.Windows.Forms.SendKeys]::SendWait('{DOWN}{ENTER}')
        Write-Output "SEARCHED_AND_SELECTED [$appTitle]: Searched '$query' (keyboard fallback)."
    }
} else {
    Write-Output "SEARCHED [$appTitle]: Typed '$query' in search bar."
}
"""
        ps_script = (
            ps_template
            .replace("__WIN32_CS__", WIN32_HELPER_CS)
            .replace("__APP_TITLE__", json.dumps(app_name.strip()))
            .replace("__QUERY__", json.dumps(clean_query))
            .replace("__OPEN_FIRST__", "$true" if open_first else "$false")
        )
        out = self._run_ps(ps_script)
        return out if out else f"IN_APP_SEARCH [{app_name}]: Executed search for '{clean_query}'."

    def send_message(self, app_name: str, text: str, recipient: str = "") -> str:
        prefix_log = ""
        if recipient.strip():
            prefix_log = self.in_app_search(app_name, recipient, open_first=True) + " | "

        ps_template = r"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
__WIN32_CS__
'@

$appTitle = __APP_TITLE__
$msg = __MSG__

$hwnd = [IntPtr]::Zero
foreach ($p in (Get-Process)) {
    if ($p.MainWindowHandle -ne 0 -and $p.MainWindowTitle -like "*$appTitle*") {
        $hwnd = $p.MainWindowHandle
        break
    }
}
if ($hwnd -eq [IntPtr]::Zero) { Write-Output "WINDOW_NOT_FOUND: '$appTitle'"; exit 0 }
[Win32Focus]::ForceForeground($hwnd)
Start-Sleep -Milliseconds 300

$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$editCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Edit
)
$edits = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $editCond)
$focused = $false
foreach ($el in $edits) {
    $nm = $el.Current.Name
    if ($nm -match "Type a message|Write a message|Message") {
        $r = $el.Current.BoundingRectangle
        if ($r.Width -gt 50 -and $r.Height -gt 12) {
            [Win32Focus]::ClickAt([int]($r.X + $r.Width / 2), [int]($r.Y + $r.Height / 2))
            $focused = $true
            break
        }
    }
}

Set-Clipboard -Value $msg
Start-Sleep -Milliseconds 120
[System.Windows.Forms.SendKeys]::SendWait('^v')
Start-Sleep -Milliseconds 150
[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
Write-Output "SENT_MESSAGE [$appTitle]: Sent '$msg' (composeFocused=$focused)."
"""
        ps_script = (
            ps_template
            .replace("__WIN32_CS__", WIN32_HELPER_CS)
            .replace("__APP_TITLE__", json.dumps(app_name.strip()))
            .replace("__MSG__", json.dumps(text))
        )
        out = self._run_ps(ps_script, timeout=15.0)
        return prefix_log + (out or f"SENT_MESSAGE [{app_name}]: Sent '{text}'.")

    def send_sticker(self, app_name: str, recipient: str = "", hint: str = "") -> str:
        prefix_log = ""
        if recipient.strip():
            prefix_log = self.in_app_search(app_name, recipient, open_first=True) + " | "

        ps_template = r"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
__WIN32_CS__
'@

$appTitle = __APP_TITLE__
$hint = __HINT__

$hwnd = [IntPtr]::Zero
foreach ($p in (Get-Process)) {
    if ($p.MainWindowHandle -ne 0 -and $p.MainWindowTitle -like "*$appTitle*") {
        $hwnd = $p.MainWindowHandle
        break
    }
}
if ($hwnd -eq [IntPtr]::Zero) { Write-Output "WINDOW_NOT_FOUND: '$appTitle'"; exit 0 }
[Win32Focus]::ForceForeground($hwnd)
Start-Sleep -Milliseconds 350

$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$winRect = $root.Current.BoundingRectangle

$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$openedTray = $false
foreach ($el in $all) {
    $ct = $el.Current.ControlType.ProgrammaticName
    $nm = $el.Current.Name
    if ($ct -eq "ControlType.Button" -and $nm -and ($nm -match "Sticker|Emoji")) {
        $r = $el.Current.BoundingRectangle
        if ($r.Width -gt 14 -and $r.Height -gt 14 -and $r.Y -gt ($winRect.Y + $winRect.Height * 0.65)) {
            [Win32Focus]::ClickAt([int]($r.X + $r.Width / 2), [int]($r.Y + $r.Height / 2))
            $openedTray = $true
            break
        }
    }
}

if (-not $openedTray) {
    Write-Output "STICKER_TRAY_NOT_FOUND: Could not find Emoji/Stickers button in '$appTitle'. Make sure a chat is open."
    exit 0
}

Start-Sleep -Milliseconds 650

$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$trayElems = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
foreach ($el in $trayElems) {
    $ct = $el.Current.ControlType.ProgrammaticName
    $nm = $el.Current.Name
    if (($ct -eq "ControlType.Button" -or $ct -eq "ControlType.TabItem") -and $nm -and ($nm -match "^Stickers?$")) {
        $r = $el.Current.BoundingRectangle
        if ($r.Width -gt 16 -and $r.Height -gt 16) {
            [Win32Focus]::ClickAt([int]($r.X + $r.Width / 2), [int]($r.Y + $r.Height / 2))
            Start-Sleep -Milliseconds 650
            break
        }
    }
}

$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$gridElems = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$clickedSticker = ""
foreach ($el in $gridElems) {
    $ct = $el.Current.ControlType.ProgrammaticName
    $nm = $el.Current.Name
    if (($ct -eq "ControlType.Button" -or $ct -eq "ControlType.ListItem" -or $ct -eq "ControlType.Image") -and $nm -and ($nm -match "Sticker")) {
        if ($nm -notmatch "^Stickers?$" -and $nm -notmatch "Emoji") {
            if ($hint -eq "" -or $nm -match [regex]::Escape($hint)) {
                $r = $el.Current.BoundingRectangle
                if ($r.Width -ge 40 -and $r.Height -ge 40 -and $r.Y -lt ($winRect.Y + $winRect.Height - 55)) {
                    [Win32Focus]::ClickAt([int]($r.X + $r.Width / 2), [int]($r.Y + $r.Height / 2))
                    $clickedSticker = $nm
                    break
                }
            }
        }
    }
}

if ($clickedSticker -ne "") {
    Write-Output "SENT_STICKER [$appTitle]: Clicked '$clickedSticker'."
} else {
    Write-Output "STICKER_PICKER_OPENED [$appTitle]: Opened Stickers tray, but no clickable sticker item matched automatically."
}
"""
        ps_script = (
            ps_template
            .replace("__WIN32_CS__", WIN32_HELPER_CS)
            .replace("__APP_TITLE__", json.dumps(app_name.strip()))
            .replace("__HINT__", json.dumps(hint.strip()))
        )
        out = self._run_ps(ps_script, timeout=18.0)
        return prefix_log + (out or f"SENT_STICKER [{app_name}]: Triggered sticker send.")

    def inspect_ui(self, app_name: str, max_items: int = 45) -> str:
        ps_template = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$appTitle = __APP_TITLE__
$hwnd = [IntPtr]::Zero
foreach ($p in (Get-Process)) {
    if ($p.MainWindowHandle -ne 0 -and $p.MainWindowTitle -like "*$appTitle*") {
        $hwnd = $p.MainWindowHandle
        break
    }
}
if ($hwnd -eq [IntPtr]::Zero) { Write-Output "WINDOW_NOT_FOUND: '$appTitle'"; exit 0 }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$items = @()
foreach ($el in $all) {
    $nm = $el.Current.Name
    if ($nm) {
        $ct = $el.Current.ControlType.ProgrammaticName -replace "ControlType\.", ""
        $items += "$ct('$nm')"
        if ($items.Count -ge __MAX_ITEMS__) { break }
    }
}
Write-Output ($items -join ", ")
"""
        ps_script = (
            ps_template
            .replace("__APP_TITLE__", json.dumps(app_name.strip()))
            .replace("__MAX_ITEMS__", str(max_items))
        )
        out = self._run_ps(ps_script, timeout=10.0)
        return f"UI_ELEMENTS [{app_name}]: {out}" if out else f"UI_ELEMENTS [{app_name}]: none found"

    def click_ui(self, app_name: str, control_name: str) -> str:
        ps_template = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
__WIN32_CS__
'@
$appTitle = __APP_TITLE__
$targetName = __TARGET_NAME__
$hwnd = [IntPtr]::Zero
foreach ($p in (Get-Process)) {
    if ($p.MainWindowHandle -ne 0 -and $p.MainWindowTitle -like "*$appTitle*") {
        $hwnd = $p.MainWindowHandle
        break
    }
}
if ($hwnd -eq [IntPtr]::Zero) { Write-Output "WINDOW_NOT_FOUND: '$appTitle'"; exit 0 }
[Win32Focus]::ForceForeground($hwnd)
Start-Sleep -Milliseconds 250
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
foreach ($el in $all) {
    $nm = $el.Current.Name
    if ($nm -and $nm -match [regex]::Escape($targetName)) {
        $r = $el.Current.BoundingRectangle
        if ($r.Width -gt 4 -and $r.Height -gt 4) {
            [Win32Focus]::ClickAt([int]($r.X + $r.Width / 2), [int]($r.Y + $r.Height / 2))
            Write-Output "CLICKED_UI [$appTitle]: '$nm'"
            exit 0
        }
    }
}
Write-Output "CONTROL_NOT_FOUND [$appTitle]: '$targetName'"
"""
        ps_script = (
            ps_template
            .replace("__WIN32_CS__", WIN32_HELPER_CS)
            .replace("__APP_TITLE__", json.dumps(app_name.strip()))
            .replace("__TARGET_NAME__", json.dumps(control_name.strip()))
        )
        return self._run_ps(ps_script, timeout=10.0)
