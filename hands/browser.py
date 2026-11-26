import re
import subprocess
from pathlib import Path
from urllib.parse import quote_plus
import httpx
from playwright.sync_api import sync_playwright

SITE_SHORTCUTS = {
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "huggingface": "https://huggingface.co",
    "hugging face": "https://huggingface.co",
    "reddit": "https://www.reddit.com",
    "gmail": "https://mail.google.com",
    "chatgpt": "https://chatgpt.com",
    "leetcode": "https://leetcode.com",
    "arxiv": "https://arxiv.org",
}

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
        return f"Opened in Windows browser: {url}"

    def _ensure_playwright(self):
        if self._browser is None:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)
            self._context = self._browser.new_context(accept_downloads=True)
            self._pages.append(self._context.new_page())

    def _normalize_open_target(self, raw: str) -> str:
        clean = raw.strip()
        low = clean.lower().rstrip("/")
        if low in SITE_SHORTCUTS:
            return SITE_SHORTCUTS[low]
        if clean.startswith(("http://", "https://")):
            return clean
        # Valid domain/host check (must contain a dot or localhost, and no spaces)
        if " " not in clean and ("." in clean or clean.startswith("localhost")):
            return f"https://{clean}"
        # Otherwise treat bare words/phrases as a Google search instead of a broken DNS host
        return f"https://www.google.com/search?q={quote_plus(clean)}"

    def _resolve_youtube_top_video(self, query: str) -> str | None:
        """Fetches YouTube search HTML and extracts the top playable watch URL in ~300ms."""
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
            resp = httpx.get(
                "https://www.youtube.com/results",
                params={"search_query": query},
                headers=headers,
                timeout=6.0,
            )
            ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
            for vid in ids:
                if vid:
                    return f"https://www.youtube.com/watch?v={vid}"
        except Exception:
            pass
        return None

    def tab_action(self, action: str, url_or_query: str) -> str:
        clean = url_or_query.strip()
        act = (action or "open").strip().lower()

        if act in {"youtube_play", "play_youtube"}:
            watch_url = self._resolve_youtube_top_video(clean)
            if watch_url:
                return self._open_in_windows_browser(watch_url) + f" (Top YouTube match for '{clean}')"
            yt_search = f"https://www.youtube.com/results?search_query={quote_plus(clean)}"
            return self._open_in_windows_browser(yt_search)

        if act == "youtube_search":
            yt_search = f"https://www.youtube.com/results?search_query={quote_plus(clean)}"
            return self._open_in_windows_browser(yt_search)

        if act == "open":
            target = self._normalize_open_target(clean)
            return self._open_in_windows_browser(target)

        if act == "search":
            # Detect "... on youtube" inside generic search queries
            yt_match = re.sub(r"\s+on\s+youtube$", "", clean, flags=re.IGNORECASE).strip()
            if yt_match != clean:
                yt_search = f"https://www.youtube.com/results?search_query={quote_plus(yt_match)}"
                return self._open_in_windows_browser(yt_search)
            query_url = f"https://www.google.com/search?q={quote_plus(clean)}"
            return self._open_in_windows_browser(query_url)

        if act == "close":
            if self._pages:
                page = self._pages.pop()
                page.close()
                return "Closed background automation tab."
            return "Closed active tab."

        return self._open_in_windows_browser(self._normalize_open_target(clean))

    def download_item(self, url: str, save_dir: str, filename: str = "auto") -> str:
        if len(save_dir) >= 2 and save_dir[1] == ":":
            drive = save_dir[0].lower()
            rest = save_dir[2:].replace("\\", "/").lstrip("/")
            out_dir = Path(f"/mnt/{drive}/{rest}")
        else:
            out_dir = Path(save_dir).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)

        if not url.startswith(("http://", "https://")):
            return f"DOWNLOAD_PENDING: Need direct URL to save into {out_dir}"

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
