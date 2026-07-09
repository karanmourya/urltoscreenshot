# Pixforge — URL-to-Screenshot API

A lightweight website-screenshot / PDF API built for hosting on Render (free tier)
and publishing on RapidAPI. Single Chromium instance, reused contexts, resource
blocking, and an in-memory async job store — tuned for ~512MB RAM.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/v1/screenshots/image` | Binary screenshot (jpeg/png) |
| GET | `/v1/screenshots/json` | Base64 screenshot in JSON (`image`, `url`, `options`) |
| GET | `/v1/pdf` | PDF of the page (`format`, `landscape`, `margin`) |
| POST | `/v1/batch` | Up to 10 URLs in one request |
| POST | `/v1/async/screenshots/image` | Submit async job (returns `job_id` + `access_token`) |
| GET | `/v1/jobs/{job_id}` | Poll job status/result (Bearer = `access_token`) |
| GET | `/v1/devices` | 133 device presets usable as `emulate_device` |
| GET | `/healthz` | Health check (no auth) |

### Screenshot parameters (`/image`, `/json`, `/batch` options)
`url` (required, http/https), `width` (1280), `height` (720), `type` (jpeg|png),
`quality` (1–100, jpeg), `full_page` (bool), `dark_mode` (bool),
`emulate_device` (name from `/v1/devices`), `mobile` (bool), `scale` (float),
`delay` (ms), `wait_until` (load|networkidle|domcontentloaded), `timeout` (ms, 10000).

## Authentication

The service sits behind RapidAPI, which forwards:
- `X-RapidAPI-Key` — RapidAPI subscriber key
- `Authorization: Bearer <PIXFORGE_API_KEY>` — direct/admin access
- `Authorization: Bearer <access_token>` — async job polling token

Rate limit (per caller key): `10/min` free, configurable via `PIXFORGE_RATE_LIMIT`.
Response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`,
and `Retry-After` on `429`.

## Error contract

All non-2xx responses use a uniform envelope:
```json
{ "error": true, "code": 400, "message": "...", "details": { ... } }
```
`400` bad params · `401` missing auth · `403` bad job token · `404` job not found/expired
(24h) · `429` rate limited · `500` crash · `503` browser not ready.

## Local development

```bash
uv venv && uv pip install -r requirements.txt
uv run playwright install chromium chromium-headless-shell
PIXFORGE_API_KEY=local uv run uvicorn app.main:app --reload --port 10000
```

## Deploy to Render (free)

`render.yaml` defines a Docker web service (`plan: free`). Connect the repo,
Render builds the image and launches with `uvicorn app.main:app --port 10000`.

A `Dockerfile` based on `mcr.microsoft.com/playwright/python:chromium` already
includes the Chromium browser, so no extra apt steps are needed.

**Keep-alive:** Render free sleeps after inactivity. Use an external cron
(e.g. UptimeRobot / a scheduled ping) hitting `/healthz` every ~10 min so the
browser stays warm and the async job store isn't interrupted.

### Env vars
`PIXFORGE_API_KEY` (auto-generated), `PIXFORGE_RATE_LIMIT` (10),
`PIXFORGE_CONCURRENCY` (1 — raising needs more RAM), `PIXFORGE_WIDTH/HEIGHT`
(1280×720), `PIXFORGE_TYPE` (jpeg), `PIXFORGE_QUALITY` (80),
`PIXFORGE_TIMEOUT_MS` (10000). Set `PIXFORGE_CONCURRENCY` to 2–4 on a paid
instance.

## Notes

- Concurrency is capped by `Semaphore(PIXFORGE_CONCURRENCY)` — one browser,
  one context per request.
- Fonts and media are blocked during capture to cut payload/latency.
- Webhooks (`webhook_url` + `webhook_secret` on async jobs) are signed with
  `HMAC-SHA256` in the `X-Pixforge-Signature` header.
