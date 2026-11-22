"""Offline runtime acceptance probe. Safe with Docker --network none."""
import asyncio
from .browser import BrowserController


async def _main():
    browser = BrowserController()
    try:
        await browser.start()
        info = await browser.status()
        screenshot = await browser.screenshot("jpeg")
        if info["url"] != "about:blank" or not screenshot.startswith(b"\xff\xd8"):
            raise RuntimeError("Chromium/browser acceptance probe failed")
        print("STARS_BROWSER_CHROMIUM_SMOKE_OK")
    finally:
        if browser.playwright:
            await browser.stop()


if __name__ == "__main__":
    asyncio.run(_main())
