from pathlib import Path
from playwright.sync_api import sync_playwright

class BrowserHands:
    def __init__(self):
        self._pw = None
        self._browser = None
        self._context = None
        self._pages = []

    def _ensure_started(self):
        if self._browser is None:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=False)
            self._context = self._browser.new_context(accept_downloads=True)
            self._pages.append(self._context.new_page())

    def tab_action(self, action: str, url_or_query: str) -> str:
        self._ensure_started()
        if action == "open":
            page = self._context.new_page()
            self._pages.append(page)
            target = url_or_query if url_or_query.startswith("http") else f"https://{url_or_query}"
            page.goto(target, wait_until="domcontentloaded")
            return f"Opened tab {len(self._pages)}: {page.title()}"
        elif action == "search":
            page = self._pages[-1]
            page.goto(f"https://duckduckgo.com/?q={url_or_query.replace(' ', '+')}", wait_until="domcontentloaded")
            return f"Searched '{url_or_query}' in active tab"
        elif action == "close" and self._pages:
            page = self._pages.pop()
            page.close()
            return "Closed active tab"
        return f"Executed browser action: {action}"

    def download_item(self, url: str, save_dir: str, filename: str = "auto") -> str:
        self._ensure_started()
        out_dir = Path(save_dir).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        page = self._pages[-1]
        if url.startswith("http"):
            with page.expect_download() as dl_info:
                page.goto(url)
            dl = dl_info.value
            final_name = dl.suggested_filename if filename == "auto" else filename
            dest = out_dir / final_name
            dl.save_as(str(dest))
            return f"Downloaded file to {dest}"
        return f"Ready to download top result into {out_dir}"
