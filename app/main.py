"""FastAPI app factory: lifespan (Chromium), rate limiter, exception wiring."""
import asyncio
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app import browser, config, errors, jobs, routes, screenshot
from app.routes import AuthError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pixforge")


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{config.PRODUCT_NAME} API",
        version="1.0.0",
        description="URL-to-screenshot API — sync, batch, async, PDF, device presets.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )

    # In-memory per-caller rate counter + X-RateLimit-* response headers.
    _rl_counters: dict[str, list] = {}  # key -> [used, window_start_epoch]
    _RL_WINDOW = 60

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if request.url.path in ("/healthz", "/", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)
        # Resolve + cache the caller key (require_auth is async).
        try:
            key = await routes.require_auth(request)
        except AuthError:
            key = request.client.host if request.client else "anon"
        request.state._caller_key = key
        now = time.time()
        # Use a single mutable list [used, window_start] per key.
        slot = _rl_counters.get(key)
        if slot is None or now - slot[1] >= _RL_WINDOW:
            slot = [0, now]
            _rl_counters[key] = slot
        used, start = slot[0], slot[1]
        if used >= config.RATE_LIMIT_PER_MINUTE:
            reset = max(0, int(start + _RL_WINDOW - now))
            body = errors.error_response(
                429, "Rate limit exceeded. Slow down or upgrade your plan.")
            body.headers["Retry-After"] = str(reset)
            body.headers["X-RateLimit-Limit"] = str(config.RATE_LIMIT_PER_MINUTE)
            body.headers["X-RateLimit-Remaining"] = "0"
            body.headers["X-RateLimit-Reset"] = str(reset)
            return body
        slot[0] += 1  # mutate the stored list in place
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(config.RATE_LIMIT_PER_MINUTE)
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, config.RATE_LIMIT_PER_MINUTE - slot[0]))
        response.headers["X-RateLimit-Reset"] = str(
            max(0, int(start + _RL_WINDOW - now)))
        return response

    @app.exception_handler(AuthError)
    async def _auth_handler(request: Request, exc: AuthError):
        return errors.error_response(401, "Missing or invalid authentication.", {
            "hint": "Provide X-RapidAPI-Key, or Authorization: Bearer <PIXFORGE_API_KEY>."})

    @app.exception_handler(ValidationError)
    async def _validation_handler(request: Request, exc: ValidationError):
        details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return errors.error_response(400, "Invalid request parameters.", {"errors": details})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error")
        return errors.server_error()

    @app.on_event("startup")
    async def _startup():
        asyncio.create_task(_background_sweep())
        await screenshot.load_devices()
        try:
            await browser.start_browser()
        except Exception:
            logger.exception("Chromium failed to start — service will return 503 until fixed.")

    @app.on_event("shutdown")
    async def _shutdown():
        await browser.stop_browser()

    app.include_router(routes.router)
    return app


async def _background_sweep():
    while True:
        await asyncio.sleep(1800)  # every 30 min
        await jobs.sweep_expired()


app = create_app()
