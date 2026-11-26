import html
import json
import re
import subprocess
import xml.etree.ElementTree as ET
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

class BrowserHands:
    def __init__(self):
        self._pw = None
        self._browser = None
        self._context = None
        self._pages = []
        self.last_url: str = ""
        self.last_youtube_query: str = ""

    def _open_in_windows_browser(self, url: str) -> str:
        self.last_url = url
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
        if " " not in clean and ("." in clean or clean.startswith("localhost")):
            return f"https://{clean}"
        return f"https://www.google.com/search?q={quote_plus(clean)}"

    def _resolve_youtube_top_video(self, query: str) -> str | None:
        try:
            resp = httpx.get(
                "https://www.youtube.com/results",
                params={"search_query": query},
                headers=HEADERS,
                timeout=6.0,
            )
            ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
            for vid in ids:
                if vid:
                    return f"https://www.youtube.com/watch?v={vid}"
        except Exception:
            pass
        return None

    def analyze_youtube(self, url: str = "") -> str:
        target_url = url.strip() or self.last_url
        if "youtube.com/watch" not in target_url and "youtu.be/" not in target_url:
            return "NO_ACTIVE_YOUTUBE_VIDEO: No YouTube video URL is currently active."

        try:
            resp = httpx.get(target_url, headers=HEADERS, follow_redirects=True, timeout=8.0)
            page_html = resp.text

            title_m = re.search(r'"title":"(.*?)"', page_html)
            author_m = re.search(r'"author":"(.*?)"', page_html)
            desc_m = re.search(r'"shortDescription":"(.*?)"', page_html)

            def unescape_json_str(val: str) -> str:
                try:
                    return json.loads(f'"{val}"')
                except Exception:
                    return html.unescape(val)

            title = unescape_json_str(title_m.group(1)) if title_m else "Unknown Title"
            author = unescape_json_str(author_m.group(1)) if author_m else "Unknown Channel"
            desc = unescape_json_str(desc_m.group(1))[:1200] if desc_m else ""

            transcript_text = ""
            cap_m = re.search(r'"captionTracks":(\[.*?\])', page_html)
            if cap_m:
                try:
                    tracks = json.loads(cap_m.group(1))
                    if tracks and "baseUrl" in tracks[0]:
                        cap_xml = httpx.get(tracks[0]["baseUrl"], headers=HEADERS, timeout=6.0).text
                        root = ET.fromstring(cap_xml)
                        lines = [html.unescape(el.text or "").strip() for el in root.findall(".//text")]
                        transcript_text = " ".join(l for l in lines if l)[:3500]
                except Exception:
                    pass

            return (
                f"YOUTUBE_VIDEO_INFO ({target_url}):\n"
                f"- Title: {title}\n"
                f"- Channel: {author}\n"
                f"- Description: {desc or 'No description'}\n"
                f"- Captions/Transcript: {transcript_text or 'No captions available for this video'}"
            )
        except Exception as e:
            return f"YOUTUBE_ANALYZE_ERROR: {e}"

    def tab_action(self, action: str, url_or_query: str) -> str:
        clean = url_or_query.strip()
        act = (action or "open").strip().lower()

        if act in {"youtube_play", "play_youtube", "play_last"}:
            query = clean or self.last_youtube_query
            if not query:
                return "NO_YOUTUBE_QUERY: Tell me which video or creator you want to play."
            self.last_youtube_query = query
            watch_url = self._resolve_youtube_top_video(query)
            if watch_url:
                return self._open_in_windows_browser(watch_url) + f" (Playing top YouTube result for '{query}')"
            yt_search = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
            return self._open_in_windows_browser(yt_search)

        if act == "youtube_search":
            self.last_youtube_query = clean
            yt_search = f"https://www.youtube.com/results?search_query={quote_plus(clean)}"
            return self._open_in_windows_browser(yt_search)

        if act == "open":
            target = self._normalize_open_target(clean)
            return self._open_in_windows_browser(target)

        if act == "search":
            yt_match = re.sub(r"\s+on\s+youtube$", "", clean, flags=re.IGNORECASE).strip()
            if yt_match != clean or "youtube" in clean.lower() or "video" in clean.lower():
                self.last_youtube_query = yt_match
                watch_url = self._resolve_youtube_top_video(yt_match)
                if watch_url:
                    return self._open_in_windows_browser(watch_url) + f" (Playing top YouTube result for '{yt_match}')"
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
