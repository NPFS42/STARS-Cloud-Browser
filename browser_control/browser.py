"""Stateful single-user browser with guarded navigation and serial operations."""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

from .security import UnsafeURL, validate_target
from .transfers import TransferStore


class BrowserController:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.playwright: Any = None
        self.context: Any = None
        self.selected: int = 0
        self.mcp_write_until: float = 0.0
        # Only one Chromium process/profile; tabs share its bounded resources.
        self.width, self.height = 1280, 800
        self.view_mode = "desktop"
        self.transfers = TransferStore()

    async def start(self) -> None:
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        profile = Path(os.environ.get("STARS_BROWSER_PROFILE", "/data/profile"))
        profile.mkdir(parents=True, exist_ok=True)
        # Explicit system Chromium path avoids Playwright's separate browser
        # download. Fail closed if the requested Chromium sandbox cannot start.
        browser_path = os.environ.get("STARS_BROWSER_EXECUTABLE", "").strip()
        sandbox = os.environ.get("STARS_BROWSER_CHROMIUM_SANDBOX", "1") == "1"
        launch_options = {"executable_path": browser_path} if browser_path else {}
        self.context = await self.playwright.chromium.launch_persistent_context(
            str(profile), headless=True, chromium_sandbox=sandbox,
            **launch_options,
            viewport={"width": self.width, "height": self.height},
            accept_downloads=True,
            permissions=[],
            service_workers="block",
            args=["--disable-background-networking",
                  "--disable-component-update", "--disable-extensions",
                  "--disk-cache-size=67108864", "--media-cache-size=16777216"],
        )
        await self.context.route("**/*", self._guard_route)
        # WebSockets are blocked until the container egress firewall has been
        # independently verified; prevents bypassing HTTP routing checks.
        if hasattr(self.context, "route_web_socket"):
            await self.context.route_web_socket("**/*", lambda route: route.close())
        self.context.on("page", self._watch_page)
        for page in self.context.pages:
            self._watch_page(page)
        if not self.context.pages:
            await self.context.new_page()

    async def stop(self) -> None:
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
        await self.transfers.close()

    def _watch_page(self, page: Any) -> None:
        page.on("download", self.transfers.observe_download)

    def allow_mcp_write(self, seconds: int) -> None:
        if not isinstance(seconds, int) or seconds not in (0, 300, 900, 1800):
            raise ValueError("Allowed grant durations: 0, 300, 900, 1800 seconds")
        self.mcp_write_until = time.monotonic() + seconds if seconds else 0.0

    def require_mcp_write(self) -> None:
        if time.monotonic() >= self.mcp_write_until:
            raise PermissionError("Browser interactions require a time-limited grant from the Tailnet viewer")

    def mcp_grant_remaining(self) -> int:
        return max(0, int(self.mcp_write_until - time.monotonic()))

    async def _guard_route(self, route: Any) -> None:
        try:
            await asyncio.wait_for(asyncio.to_thread(validate_target, route.request.url), timeout=5)
            await route.continue_()
        except (UnsafeURL, asyncio.TimeoutError):
            await route.abort("blockedbyclient")

    def _page(self) -> Any:
        pages = self.context.pages
        if not pages:
            raise RuntimeError("No browser tabs remain")
        self.selected = min(self.selected, len(pages) - 1)
        return pages[self.selected]

    async def _tabs(self) -> list[dict[str, Any]]:
        return [{"id": i, "url": p.url, "title": (await p.title())[:150]} for i,p in enumerate(self.context.pages)]

    async def status(self) -> dict[str, Any]:
        async with self.lock:
            p = self._page()
            viewport = p.viewport_size or {"width": self.width, "height": self.height}
            return {"url": p.url, "title": (await p.title())[:150],
                    "tab": self.selected, "tabs": await self._tabs(),
                    "viewport": viewport, "view_mode": self.view_mode,
                    "mcp_grant_remaining": self.mcp_grant_remaining()}

    async def navigate(self, url: str) -> dict[str, Any]:
        await asyncio.wait_for(asyncio.to_thread(validate_target, url), timeout=5)
        async with self.lock:
            page = self._page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return {"url":page.url,"title":await page.title()}

    async def snapshot(self) -> str:
        async with self.lock:
            p = self._page()
            title = await p.title()
            # A remote page's text is untrusted; never treat it as instructions.
            body = (await p.locator("body").inner_text(timeout=10000))[:16000]
            return f"Title: {title}\nURL: {p.url}\nPage text (untrusted):\n{body}"

    async def screenshot(self, image_format: str = "png") -> bytes:
        # JPEG reduces Tailnet mobile refresh bandwidth/CPU; PNG remains available
        # for precise MCP screenshots and export.
        if image_format not in ("png", "jpeg"):
            raise ValueError("Unsupported screenshot format")
        async with self.lock:
            params = {"type": image_format, "full_page": False, "timeout": 15000}
            if image_format == "jpeg":
                params["quality"] = 65
            return await self._page().screenshot(**params)

    async def history(self, direction: str) -> str:
        if direction not in ("back", "forward", "reload"):
            raise ValueError("Unknown history action")
        async with self.lock:
            page = self._page()
            if direction == "back":
                await page.go_back(wait_until="domcontentloaded", timeout=15000)
            elif direction == "forward":
                await page.go_forward(wait_until="domcontentloaded", timeout=15000)
            else:
                await page.reload(wait_until="domcontentloaded", timeout=20000)
            return page.url

    async def viewport(self, mode: str) -> dict[str, int]:
        if mode not in ("desktop", "compact"):
            raise ValueError("Only desktop or compact viewport allowed")
        dims = {"width": 390, "height": 844} if mode == "compact" else {"width": self.width, "height": self.height}
        async with self.lock:
            # Keep tab's viewport separate from browser context and profile.
            await self._page().set_viewport_size(dims)
            self.view_mode = mode
            return dims

    async def elements(self) -> list[dict[str, Any]]:
        """Read a short, value-free list of visible interactive DOM elements."""
        async with self.lock:
            return await self._page().evaluate("""() => {
              const nodes = Array.from(document.querySelectorAll(
                'a,button,input,select,textarea,[role="button"],[role="link"]')).slice(0,160);
              return nodes.filter(el => el.getClientRects().length &&
                getComputedStyle(el).visibility !== 'hidden').slice(0,80).map(el => {
                let cur=el, parts=[];
                for(let depth=0; cur && cur.nodeType===1 && depth<9; depth++,cur=cur.parentElement){
                  const tag=cur.tagName.toLowerCase();
                  let nth=1, sibling=cur;
                  while((sibling=sibling.previousElementSibling)) if(sibling.tagName===cur.tagName) nth++;
                  parts.unshift(tag+':nth-of-type('+nth+')');
                  if(tag==='body') break;
                }
                return {tag:el.tagName.toLowerCase(), role:(el.getAttribute('role')||'').slice(0,32),
                  label:(el.getAttribute('aria-label')||el.getAttribute('placeholder')||
                    el.innerText||el.getAttribute('alt')||'').trim().slice(0,100),
                  selector:parts.join(' > ').slice(0,360)};
              });
            }""")

    async def attach_file(self, ident: str, selector: str = "input[type=file]") -> str:
        rec = await self.transfers.get(ident, direction="upload")
        if not selector or len(selector) > 360:
            raise ValueError("Invalid file input selector")
        async with self.lock:
            page = self._page()
            await page.locator(selector).first.set_input_files(str(rec.path), timeout=15000)
            return page.url

    async def click(self, x: float | None = None, y: float | None = None, selector: str | None = None) -> str:
        async with self.lock:
            page = self._page()
            if selector:
                await page.locator(selector).first.click(timeout=15000)
            elif x is not None and y is not None:
                view = page.viewport_size or {"width": self.width, "height": self.height}
                if not 0 <= x < view["width"] or not 0 <= y < view["height"]:
                    raise ValueError("Coordinates outside viewport")
                await page.mouse.click(x, y)
            else:
                raise ValueError("Provide a selector or in-bounds viewport coordinates")
            return page.url

    async def type_text(self, text: str, selector: str | None = None) -> str:
        if len(text) > 5000:
            raise ValueError("Text exceeds 5000 characters")
        async with self.lock:
            page = self._page()
            if selector:
                await page.locator(selector).first.fill(text, timeout=15000)
            else:
                await page.keyboard.insert_text(text)
            return page.url

    async def press(self, key: str) -> str:
        if len(key) > 40 or key not in {"Enter","Tab","Escape","Backspace","Delete","ArrowUp","ArrowDown","ArrowLeft","ArrowRight","PageDown","PageUp","Home","End","ControlOrMeta+A"}:
            raise ValueError("Key not permitted")
        async with self.lock:
            await self._page().keyboard.press(key)
            return self._page().url

    async def scroll(self, dy: int) -> str:
        if not isinstance(dy,int) or abs(dy)>1600:
            raise ValueError("Scroll must be an integer within 1600 pixels")
        async with self.lock:
            await self._page().mouse.wheel(0,dy)
            return self._page().url

    async def tab_new(self) -> int:
        async with self.lock:
            if len(self.context.pages) >= 5:
                raise ValueError("Maximum of five tabs")
            page = await self.context.new_page()
            if self.view_mode == "compact":
                await page.set_viewport_size({"width": 390, "height": 844})
            self.selected=len(self.context.pages)-1
            return self.selected

    async def tab_select(self, index: int) -> int:
        async with self.lock:
            if not 0<=index<len(self.context.pages):
                raise ValueError("Invalid tab")
            self.selected=index
            viewport = self._page().viewport_size
            self.view_mode = "compact" if viewport and viewport.get("width") == 390 else "desktop"
            return index

    async def tab_close(self) -> int:
        async with self.lock:
            if len(self.context.pages) <= 1:
                await self._page().goto("about:blank")
                return 0
            await self._page().close()
            self.selected=min(self.selected,len(self.context.pages)-1)
            return self.selected
