import subprocess
from pathlib import Path
from urllib.parse import quote_plus
import httpx
from playwright.sync_api import sync_playwright

class BrowserHands:
    def __init__(self):
        self._pw = None
        self._browser = None
        self._context = None
        self._pages = []

    def _open_in_windows_browser(self, url: str) -> str:
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", url],
            cwd="/mnt/c",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Opened in Windows default browser: {url}"

    def _ensure_playwright(self):
        if self._browser is None:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)
            self._context = self._browser.new_context(accept_downloads=True)
            self._pages.append(self._context.new_page())

    def tab_action(self, action: str, url_or_query: str) -> str:
        clean = url_or_query.strip()
        if action == "open":
            target = clean if clean.startswith(("http://", "https://")) else f"https://{clean}"
            return self._open_in_windows_browser(target)
        elif action == "search":
            query_url = f"https://www.google.com/search?q={quote_plus(clean)}"
            return self._open_in_windows_browser(query_url)
        elif action == "close":
            if self._pages:
                page = self._pages.pop()
                page.close()
                return "Closed background automation tab."
            return "Sent close tab hotkey instruction."
        return f"Executed browser action: {action}"

    def download_item(self, url: str, save_dir: str, filename: str = "auto") -> str:
        # Convert Windows path (e.g. D:\Papers) to WSL2 path (/mnt/d/Papers) if needed
        if len(save_dir) >= 2 and save_dir[1] == ":":
            drive = save_dir[0].lower()
            rest = save_dir[2:].replace("\\", "/").lstrip("/")
            out_dir = Path(f"/mnt/{drive}/{rest}")
        else:
            out_dir = Path(save_dir).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)

        if not url.startswith(("http://", "https://")):
            return f"DOWNLOAD_PENDING: Need direct URL to save into {out_dir}"

        # Fast direct stream download first, Playwright browser download fallback
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=20.0) as resp:
                resp.raise_for_status()
                inferred = url.split("?")[0].rstrip("/").split("/")[-1] or "download.bin"
                final_name = inferred if filename == "auto" else filename
                dest = out_dir / final_name
                with dest.open("wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        f.write(chunk)
                return f"Downloaded directly to {dest}"
        except Exception:
            self._ensure_playwright()
            page = self._pages[-1]
            with page.expect_download(timeout=20000) as dl_info:
                page.goto(url)
            dl = dl_info.value
            final_name = dl.suggested_filename if filename == "auto" else filename
            dest = out_dir / final_name
            dl.save_as(str(dest))
            return f"Downloaded via Playwright to {dest}"
