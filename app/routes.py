"""All HTTP routes for the Pixforge API."""
import asyncio
import base64
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse

from fastapi import HTTPException

from app import browser as browser_mod, config, errors, jobs, screenshot
from app.models import AsyncRequest, BatchRequest, ScreenshotOptions

logger = logging.getLogger("pixforge.routes")

router = APIRouter()


class AuthError(Exception):
    """Raised when no valid auth credential is supplied."""


async def require_auth(request: Request):
    """Accept RapidAPI proxy-secret, admin Bearer key, or issued job Bearer token.

    Returns the caller key used for rate-limiting. Raises AuthError if none valid.

    Headers are read directly from request.headers so this works whether called as a
    FastAPI dependency or directly from the rate-limit middleware (which passes only
    the Request object). Using the Header() default would leave a Header object behind
    on the direct call and crash with AttributeError.

    When RAPIDAPI_PROXY_SECRET is configured, every request must carry the matching
    X-RapidAPI-Proxy-Secret header (RapidAPI injects this on proxied traffic only),
    proving the request originated from RapidAPI infrastructure. Direct/private calls
    use Authorization: Bearer <PIXFORGE_API_KEY> instead.
    """
    authorization = request.headers.get("authorization")
    x_rapidapi_proxy_secret = request.headers.get("x-rapidapi-proxy-secret")

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if config.ADMIN_API_KEY and token == config.ADMIN_API_KEY:
            return config.ADMIN_API_KEY
        # Only accept a Bearer token the service itself issued (anonymous job token);
        # any other Bearer value is rejected so the endpoint is not open to anyone.
        if token and jobs.get_job_by_token(token):
            request.state.job_token = token
            return f"job:{token}"
        raise AuthError()

    # When PIXFORGE_RAPIDAPI_PROXY_SECRET is set, every non-admin request MUST carry
    # the matching X-RapidAPI-Proxy-Secret header (RapidAPI injects it on proxied
    # traffic only), proving the request originated from RapidAPI infrastructure.
    # This blocks anyone calling the public origin URL directly.
    if config.RAPIDAPI_PROXY_SECRET:
        if x_rapidapi_proxy_secret != config.RAPIDAPI_PROXY_SECRET:
            raise AuthError()
        return x_rapidapi_proxy_secret

    if config.ADMIN_API_KEY and authorization and authorization == config.ADMIN_API_KEY:
        return config.ADMIN_API_KEY
    raise AuthError()


async def _render_pdf(browser, opts: dict) -> bytes:
    context_kwargs: dict = {}
    if opts.get("emulate_device"):
        preset = screenshot._devices().get(opts["emulate_device"])
        if preset is None:
            raise ValueError(f"unknown device: {opts['emulate_device']}")
        context_kwargs.update(preset)
    context_kwargs.setdefault("viewport", {
        "width": int(opts.get("width", config.DEFAULT_WIDTH)),
        "height": int(opts.get("height", config.DEFAULT_HEIGHT)),
    })
    context = await browser.new_context(**context_kwargs)
    page = await context.new_page()
    if opts.get("dark_mode"):
        await page.emulate_media(color_scheme="dark")
    try:
        await page.goto(opts["url"], wait_until=opts.get("wait_until", "networkidle"),
                        timeout=int(opts.get("timeout", config.DEFAULT_TIMEOUT_MS)))
        pdf_kwargs = {
            "format": opts.get("format", "A4"),
            "landscape": bool(opts.get("landscape", False)),
        }
        if opts.get("margin"):
            pdf_kwargs["margin"] = opts["margin"]
        data = await page.pdf(**pdf_kwargs)
    finally:
        await context.close()
    return data


@router.get("/v1/screenshots/image")
async def screenshot_image(
    request: Request,
    url: str = Query(...),
    width: Optional[int] = None,
    height: Optional[int] = None,
    type: str = Query(config.DEFAULT_TYPE),
    quality: int = Query(config.DEFAULT_QUALITY),
    full_page: bool = False,
    dark_mode: bool = False,
    emulate_device: Optional[str] = None,
    mobile: bool = False,
    scale: Optional[float] = None,
    delay: int = 0,
    wait_until: str = "networkidle",
    timeout: int = config.DEFAULT_TIMEOUT_MS,
    _auth: str = Depends(require_auth),
):
    if not browser_mod.is_ready():
        return errors.unavailable()
    opts = ScreenshotOptions(url=url, width=width, height=height, type=type,
                             quality=quality, full_page=full_page, dark_mode=dark_mode,
                             emulate_device=emulate_device, mobile=mobile, scale=scale,
                             delay=delay, wait_until=wait_until, timeout=timeout).to_opts()
    try:
        sem = browser_mod.get_semaphore()
        async with sem:
            data, media_type = await screenshot.capture(browser_mod.get_browser(), opts)
    except ValueError as e:
        return errors.bad_request(str(e), {"param": "options", "reason": str(e)})
    except Exception as e:
        logger.exception("capture failed")
        detail = {"error": str(e)} if config.DEBUG else None
        return errors.server_error(details=detail)
    return Response(content=data, media_type=media_type)


@router.get("/v1/screenshots/json")
async def screenshot_json(
    request: Request,
    url: str = Query(...),
    width: Optional[int] = None,
    height: Optional[int] = None,
    type: str = Query(config.DEFAULT_TYPE),
    quality: int = Query(config.DEFAULT_QUALITY),
    full_page: bool = False,
    dark_mode: bool = False,
    emulate_device: Optional[str] = None,
    mobile: bool = False,
    scale: Optional[float] = None,
    delay: int = 0,
    wait_until: str = "networkidle",
    timeout: int = config.DEFAULT_TIMEOUT_MS,
    _auth: str = Depends(require_auth),
):
    if not browser_mod.is_ready():
        return errors.unavailable()
    opts = ScreenshotOptions(url=url, width=width, height=height, type=type,
                             quality=quality, full_page=full_page, dark_mode=dark_mode,
                             emulate_device=emulate_device, mobile=mobile, scale=scale,
                             delay=delay, wait_until=wait_until, timeout=timeout).to_opts()
    try:
        result = await screenshot.capture_to_result(opts)
    except ValueError as e:
        return errors.bad_request(str(e), {"param": "options", "reason": str(e)})
    except Exception as e:
        logger.exception("capture failed")
        detail = {"error": str(e)} if config.DEBUG else None
        return errors.server_error(details=detail)
    return JSONResponse(result)


@router.get("/v1/pdf")
async def pdf_route(
    request: Request,
    url: str = Query(...),
    format: str = "A4",
    landscape: bool = False,
    width: Optional[int] = None,
    height: Optional[int] = None,
    dark_mode: bool = False,
    emulate_device: Optional[str] = None,
    wait_until: str = "networkidle",
    timeout: int = config.DEFAULT_TIMEOUT_MS,
    _auth: str = Depends(require_auth),
):
    if not browser_mod.is_ready():
        return errors.unavailable()
    opts = {"url": url, "format": format, "landscape": landscape,
            "dark_mode": dark_mode, "emulate_device": emulate_device,
            "wait_until": wait_until, "timeout": timeout}
    if width: opts["width"] = width
    if height: opts["height"] = height
    try:
        sem = browser_mod.get_semaphore()
        async with sem:
            data = await _render_pdf(browser_mod.get_browser(), opts)
    except ValueError as e:
        return errors.bad_request(str(e), {"param": "options"})
    except Exception as e:
        logger.exception("pdf failed")
        detail = {"error": str(e)} if config.DEBUG else None
        return errors.server_error(details=detail)
    return Response(content=data, media_type="application/pdf")


@router.post("/v1/batch")
async def batch_route(req: BatchRequest, request: Request,
                      _auth: str = Depends(require_auth)):
    if not browser_mod.is_ready():
        return errors.unavailable()
    results = []
    successful = 0
    failed = 0
    for item in req.requests:
        try:
            res = await screenshot.capture_to_result(item.to_opts())
            results.append({"image": res["image"], "url": res["url"], "error": None})
            successful += 1
        except Exception as e:
            results.append({"image": None, "url": item.url, "error": str(e)})
            failed += 1
    return JSONResponse({
        "total": len(req.requests),
        "successful": successful,
        "failed": failed,
        "results": results,
    })


@router.post("/v1/async/screenshots/image")
async def async_image(req: AsyncRequest, request: Request,
                      _auth: str = Depends(require_auth)):
    if not browser_mod.is_ready():
        return errors.unavailable()
    job = jobs.create_job(req.url, req.webhook_url, req.webhook_secret)
    opts = ScreenshotOptions(url=req.url, **(req.options or {})).to_opts()
    asyncio.create_task(_run_job(job.job_id, opts))
    return JSONResponse({
        "job_id": job.job_id,
        "access_token": job.access_token,
        "status": "pending",
        "status_url": f"/v1/jobs/{job.job_id}",
        "created_at": _iso(job.created_at),
    }, status_code=202)


async def _run_job(job_id: str, opts: dict) -> None:
    job = jobs.get_job(job_id)
    if job is None:
        return
    job.status = "processing"
    try:
        result = await screenshot.capture_to_result(opts)
        job.result = result
        job.status = "completed"
    except Exception as e:
        job.error = str(e)
        job.status = "failed"
    job.finished_at = jobs._now()
    await jobs.fire_webhook(job)


def _iso(ts: float) -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


@router.get("/v1/jobs/{job_id}")
async def job_status(job_id: str, request: Request,
                     authorization: Optional[str] = Header(None)):
    job = jobs.get_job(job_id)
    if job is None:
        return errors.not_found("Job not found or expired (jobs expire after 24h).")
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token and token != job.access_token:
        return errors.forbidden()
    return JSONResponse(jobs.public_view(job))


@router.get("/v1/devices")
async def devices_route(request: Request, _auth: str = Depends(require_auth)):
    return JSONResponse({"devices": screenshot.list_devices(),
                         "count": len(screenshot.list_devices())})


# Health checks — no auth.
@router.get("/healthz")
async def healthz():
    return JSONResponse({"status": "ok", "browser": browser_mod.is_ready()})


@router.get("/")
async def root():
    return JSONResponse({
        "product": config.PRODUCT_NAME,
        "docs": "/docs",
        "endpoints": [
            "GET /v1/screenshots/image",
            "GET /v1/screenshots/json",
            "GET /v1/pdf",
            "POST /v1/batch",
            "POST /v1/async/screenshots/image",
            "GET /v1/jobs/{job_id}",
            "GET /v1/devices",
        ],
    })
