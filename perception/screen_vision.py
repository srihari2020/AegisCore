import base64
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field
import ollama

CAPTURE_CS = r"""
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Windows.Forms;

public class ScreenGrabber {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);

    public static void CaptureFullScreen(string outPath) {
        SetProcessDPIAware();
        Rectangle bounds = SystemInformation.VirtualScreen;
        using (Bitmap bmp = new Bitmap(bounds.Width, bounds.Height)) {
            using (Graphics g = Graphics.FromImage(bmp)) {
                g.CopyFromScreen(bounds.Location, Point.Empty, bounds.Size);
            }
            bmp.Save(outPath, ImageFormat.Png);
        }
    }

    public static void ClickAt(int x, int y) {
        SetProcessDPIAware();
        SetCursorPos(x, y);
        System.Threading.Thread.Sleep(60);
        mouse_event(0x0002, 0, 0, 0, UIntPtr.Zero);
        mouse_event(0x0004, 0, 0, 0, UIntPtr.Zero);
    }
}
"""

class VisualActionDecision(BaseModel):
    screen_summary: str = Field(description="Concise factual description of what is currently visible on screen.")
    target_element_id: int = Field(default=-1, description="Exact [ID] box number to click, or -1 if none applies.")
    confidence: float = Field(description="Confidence score 0.0 to 1.0.")
    reasoning: str = Field(description="Why this element matches the user goal.")

class ScreenVisionEngine:
    def __init__(self, vision_model: str = "qwen2.5vl:3b"):
        self.vision_model = self._resolve_vision_model(vision_model)
        self.win_cache_str, self.wsl_cache_dir = self._init_windows_cache()
        self.raw_png = self.wsl_cache_dir / "raw_screen.png"
        self.som_png = self.wsl_cache_dir / "som_screen.png"
        self.last_elements: dict[int, dict] = {}

    def _init_windows_cache(self) -> tuple[str, Path]:
        try:
            win_temp = subprocess.check_output(
                ["cmd.exe", "/c", "echo", "%TEMP%"],
                cwd="/mnt/c",
                stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="ignore").strip()
            wsl_temp = subprocess.check_output(["wslpath", "-u", win_temp]).decode().strip()
            cache_dir = Path(wsl_temp) / "AegisCore_Cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            return f"{win_temp}\\AegisCore_Cache", cache_dir
        except Exception:
            fallback = Path("/tmp/AegisCore_Cache")
            fallback.mkdir(parents=True, exist_ok=True)
            return r"C:\Windows\Temp\AegisCore_Cache", fallback

    def _resolve_vision_model(self, preferred: str) -> str:
        try:
            models = [m.model for m in ollama.list().models]
            for cand in (preferred, "qwen2.5vl:3b", "minicpm-v:latest", "llava-phi3:latest"):
                if cand in models:
                    return cand
        except Exception:
            pass
        return preferred

    def _run_ps(self, script: str, timeout: float = 15.0) -> tuple[str, str]:
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            cwd="/mnt/c",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return res.stdout.strip(), res.stderr.strip()

    def capture_and_annotate(self) -> tuple[Path, dict[int, dict], str]:
        if self.raw_png.exists():
            self.raw_png.unlink()

        win_png_path = f"{self.win_cache_str}\\raw_screen.png"
        ps_template = r"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$csCode = @'
__CAPTURE_CS__
'@
$refs = @([System.Drawing.Bitmap].Assembly.Location, [System.Windows.Forms.Form].Assembly.Location)
Add-Type -TypeDefinition $csCode -ReferencedAssemblies $refs

[ScreenGrabber]::CaptureFullScreen('__OUT_PNG__')
$hwnd = [ScreenGrabber]::GetForegroundWindow()
$winTitle = ""
$elements = @()

if ($hwnd -ne [IntPtr]::Zero) {
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
    $winTitle = $root.Current.Name
    $all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    $idx = 1
    foreach ($el in $all) {
        if ($idx -gt 65) { break }
        $r = $el.Current.BoundingRectangle
        if ($r.Width -ge 14 -and $r.Height -ge 12 -and $r.X -ge 0 -and $r.Y -ge 0) {
            $ct = $el.Current.ControlType.ProgrammaticName -replace "ControlType\.", ""
            if ($ct -in @("Button", "Edit", "ListItem", "MenuItem", "TabItem", "Hyperlink", "CheckBox", "ComboBox", "DataItem")) {
                $elements += [PSCustomObject]@{
                    id = $idx
                    type = $ct
                    name = $el.Current.Name
                    x = [int]$r.X
                    y = [int]$r.Y
                    w = [int]$r.Width
                    h = [int]$r.Height
                    cx = [int]($r.X + $r.Width / 2)
                    cy = [int]($r.Y + $r.Height / 2)
                }
                $idx++
            }
        }
    }
}

$outObj = [PSCustomObject]@{
    window = $winTitle
    elements = $elements
}
Write-Output ($outObj | ConvertTo-Json -Depth 4 -Compress)
"""
        ps_script = (
            ps_template
            .replace("__CAPTURE_CS__", CAPTURE_CS)
            .replace("__OUT_PNG__", win_png_path)
        )
        raw_json, stderr = self._run_ps(ps_script, timeout=15.0)
        if not self.raw_png.exists():
            raise RuntimeError(f"Windows screen capture failed: {stderr or 'raw_screen.png not created'}")

        data = json.loads(raw_json) if raw_json else {"window": "Unknown", "elements": []}
        win_title = data.get("window", "Unknown")
        elems_list = data.get("elements") or []
        if isinstance(elems_list, dict):
            elems_list = [elems_list]

        elem_map = {int(e["id"]): e for e in elems_list}
        self.last_elements = elem_map

        img = Image.open(self.raw_png).convert("RGB")
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()

        for eid, el in elem_map.items():
            x1, y1 = el["x"], el["y"]
            x2, y2 = x1 + el["w"], y1 + el["h"]
            draw.rectangle([x1, y1, x2, y2], outline=(255, 50, 50), width=2)
            tag = str(eid)
            tw = len(tag) * 7 + 6
            draw.rectangle([x1, max(0, y1 - 14), x1 + tw, max(14, y1)], fill=(255, 50, 50))
            draw.text((x1 + 3, max(1, y1 - 13)), tag, fill=(255, 255, 255), font=font)

        img.thumbnail((1440, 900))
        img.save(self.som_png, format="PNG", optimize=True)
        return self.som_png, elem_map, win_title

    def see_and_reason(self, user_goal: str) -> VisualActionDecision:
        som_path, elem_map, win_title = self.capture_and_annotate()
        elem_summary = [
            f"[{eid}] {e['type']}: '{e['name'][:40]}'"
            for eid, e in list(elem_map.items())[:50]
        ]

        prompt = (
            f"Active Window: {win_title}\n"
            f"Detected Numbered UI Tags: {elem_summary}\n"
            f"User Goal: {user_goal}\n"
            "Inspect the screenshot with red numbered [ID] tags. "
            "Describe what is on screen accurately, and if the user wants to click/interact with an element, "
            "return its exact target_element_id (or -1 if only observing/reading)."
        )

        resp = ollama.chat(
            model=self.vision_model,
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [str(som_path)],
            }],
            format=VisualActionDecision.model_json_schema(),
            keep_alive=-1,
            options={"temperature": 0, "num_predict": 200},
        )
        return VisualActionDecision.model_validate_json(resp.message.content)

    def click_element_id(self, element_id: int) -> str:
        el = self.last_elements.get(element_id)
        if not el:
            return f"INVALID_ELEMENT_ID: [{element_id}] not in current screen map."
        cx, cy = int(el["cx"]), int(el["cy"])
        ps_template = r"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$csCode = @'
__CAPTURE_CS__
'@
$refs = @([System.Drawing.Bitmap].Assembly.Location, [System.Windows.Forms.Form].Assembly.Location)
Add-Type -TypeDefinition $csCode -ReferencedAssemblies $refs
[ScreenGrabber]::ClickAt(__CX__, __CY__)
"""
        ps_script = (
            ps_template
            .replace("__CAPTURE_CS__", CAPTURE_CS)
            .replace("__CX__", str(cx))
            .replace("__CY__", str(cy))
        )
        self._run_ps(ps_script, timeout=8.0)
        return f"CLICKED_VISUAL_TAG [{element_id}] ({el['type']} '{el['name']}') at ({cx}, {cy})"
