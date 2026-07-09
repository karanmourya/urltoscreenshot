"""Global Chromium lifecycle — launched once, reused via fresh contexts."""
import asyncio
import logging

from playwright.async_api import async_playwright, Browser, Playwright

from app import config

logger = logging.getLogger("pixforge.browser")

_browser: Browser | None = None
_playwright: Playwright | None = None
_semaphore: asyncio.Semaphore | None = None


async def start_browser() -> None:
    """Launch Chromium once at startup (cold boot is the only heavy moment)."""
    global _browser, _playwright, _semaphore
    logger.info("Launching Chromium...")
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(
        headless=True,
        args=config.CHROMIUM_ARGS,
    )
    _semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY)
    logger.info("Chromium ready (concurrency=%d).", config.MAX_CONCURRENCY)


async def stop_browser() -> None:
    global _browser, _playwright
    if _browser is not None:
        await _browser.close()
    if _playwright is not None:
        await _playwright.stop()
    _browser, _playwright = None, None


def get_browser() -> Browser:
    if _browser is None:
        raise RuntimeError("Browser not started")
    return _browser


def get_semaphore() -> asyncio.Semaphore:
    if _semaphore is None:
        raise RuntimeError("Browser not started")
    return _semaphore


def is_ready() -> bool:
    return _browser is not None
