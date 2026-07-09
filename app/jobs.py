"""In-memory async job store + webhook dispatch (no external services)."""
import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app import config

logger = logging.getLogger("pixforge.jobs")

JOB_TTL = config.JOB_TTL_SECONDS  # seconds


@dataclass
class Job:
    job_id: str
    access_token: str
    url: str
    status: str = "pending"  # pending -> processing -> completed | failed
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    result: dict | None = None   # on success
    error: str | None = None     # on failure
    webhook_url: str | None = None
    webhook_secret: str | None = None


_STORE: dict[str, Job] = {}
_LOCK = asyncio.Lock()


def _now() -> float:
    return time.time()


def create_job(url: str, webhook_url: str | None = None,
               webhook_secret: str | None = None) -> Job:
    job = Job(
        job_id=secrets.token_hex(8),
        access_token=secrets.token_hex(16),
        url=url,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )
    _STORE[job.job_id] = job
    return job


def get_job(job_id: str) -> Job | None:
    job = _STORE.get(job_id)
    if job is None:
        return None
    if _now() - job.created_at > JOB_TTL:
        _STORE.pop(job_id, None)
        return None
    return job


def public_view(job: Job) -> dict:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "url": job.url,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(job.created_at)),
        "finished_at": (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(job.finished_at))
                        if job.finished_at else None),
        "result": job.result,
        "error": job.error,
    }


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def fire_webhook(job: Job) -> None:
    if not job.webhook_url:
        return
    payload = public_view(job)
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if job.webhook_secret:
        headers[config.WEBHOOK_HEADER] = _sign(job.webhook_secret, body)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(job.webhook_url, content=body, headers=headers)
    except Exception as exc:  # webhook failures must not crash the job flow
        logger.warning("Webhook delivery failed for %s: %s", job.job_id, exc)


async def sweep_expired() -> None:
    """Drop TTL-expired jobs. Call periodically from a background task."""
    now = _now()
    expired = [jid for jid, j in _STORE.items() if now - j.created_at > JOB_TTL]
    for jid in expired:
        _STORE.pop(jid, None)
