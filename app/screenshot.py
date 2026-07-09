"""Core capture logic: validate options, open a context, screenshot, return bytes."""
import base64
import logging
from typing import Any

from playwright.async_api import Browser, async_playwright

from app import browser as browser_mod, config

logger = logging.getLogger("pixforge.screenshot")

_DEVICE_CACHE: dict = {}


async def load_devices() -> None:
    """Populate the device registry once at startup using the async API
    (safe inside the running asyncio loop). Presets are static."""
    global _DEVICE_CACHE
    async with async_playwright() as p:
        _DEVICE_CACHE = dict(p.devices)
    logger.info("Loaded %d device presets.", len(_DEVICE_CACHE))


def _devices() -> dict:
    return _DEVICE_CACHE


def list_devices() -> list[str]:
    return sorted(_DEVICE_CACHE.keys())


def _validate_url(url: str) -> None:
    if not isinstance(url, str) or not url:
        raise ValueError("url is required")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("url must be a valid http(s) URL")


async def capture(browser: Browser, opts: dict) -> bytes:
    """Open a fresh context, navigate, screenshot. Returns raw image bytes."""
    _validate_url(opts["url"])

    context_kwargs: dict[str, Any] = {}

    # Device emulation overrides explicit width/height when present.
    device_name = opts.get("emulate_device")
    if device_name:
        preset = _devices().get(device_name)
        if preset is None:
            raise ValueError(f"unknown device: {device_name}")
        context_kwargs.update(preset)

    if "width" in opts and "height" in opts:
        context_kwargs.setdefault("viewport", {
            "width": int(opts["width"]),
            "height": int(opts["height"]),
        })
    else:
        context_kwargs.setdefault("viewport", {
            "width": config.DEFAULT_WIDTH,
            "height": config.DEFAULT_HEIGHT,
        })

    if opts.get("mobile"):
        context_kwargs.setdefault("is_mobile", True)
    if opts.get("scale") is not None:
        context_kwargs.setdefault("device_scale_factor", float(opts["scale"]))

    context = await browser.new_context(**context_kwargs)
    page = await context.new_page()

    # Resource blocking: drop media + fonts to shrink load + speed capture.
    async def _route(route):
        if route.request.resource_type in config.BLOCKED_RESOURCE_TYPES:
            await route.abort()
        else:
            await route.continue_()
    await page.route("**/*", _route)

    # Dark mode emulation.
    if opts.get("dark_mode"):
        await page.emulate_media(color_scheme="dark")

    try:
        await page.goto(
            opts["url"],
            wait_until=opts.get("wait_until", "networkidle"),
            timeout=int(opts.get("timeout", config.DEFAULT_TIMEOUT_MS)),
        )
        if opts.get("delay"):
            await page.wait_for_timeout(int(opts["delay"]))

        shot_kwargs: dict[str, Any] = {"full_page": bool(opts.get("full_page", False))}
        img_type = (opts.get("type") or config.DEFAULT_TYPE).lower()
        if img_type == "png":
            shot_kwargs["type"] = "png"
            media_type = "image/png"
        else:
            shot_kwargs["type"] = "jpeg"
            shot_kwargs["quality"] = int(opts.get("quality", config.DEFAULT_QUALITY))
            media_type = "image/jpeg"

        data = await page.screenshot(**shot_kwargs)
    finally:
        await context.close()

    return data, media_type


async def capture_to_result(opts: dict) -> dict:
    """Capture and wrap in the JSON-ish result dict used by /json + batch + jobs."""
    sem = browser_mod.get_semaphore()
    async with sem:
        data, media_type = await capture(browser_mod.get_browser(), opts)
    return {
        "image": base64.b64encode(data).decode(),
        "url": opts["url"],
        "media_type": media_type,
        "options": {k: opts.get(k) for k in (
            "width", "height", "type", "quality", "full_page",
            "dark_mode", "emulate_device", "mobile", "scale",
            "delay", "wait_until", "timeout",
        )},
    }
