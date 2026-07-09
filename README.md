# Pixforge — URL-to-Screenshot & PDF API

> A lightweight, self-hostable screenshot API built for **Render** (free tier) and
> publishing on **RapidAPI**. One Chromium instance, reused per request, tuned for
> ~512 MB RAM. Capture screenshots, full-page PNG/JPEG, dark-mode, device-emulated
> shots, PDFs, and async jobs with HMAC-signed webhooks.

This README is the **complete A→Z guide** for *you*: what the project is, how it
works, how to host it on Render, how to list it on RapidAPI, how to use it
directly (without RapidAPI), how to tune rate limits/concurrency, and best
practices.

---

## Table of Contents

1. [What this project is](#1-what-this-project-is)
2. [Project structure](#2-project-structure)
3. [How it works (architecture)](#3-how-it-works-architecture)
4. [Endpoints at a glance](#4-endpoints-at-a-glance)
5. [Configuration / environment variables](#5-configuration--environment-variables)
6. [Local development & testing](#6-local-development--testing)
7. [Host on Render (step-by-step)](#7-host-on-render-step-by-step)
8. [Keep the free tier awake](#8-keep-the-free-tier-awake)
9. [Use it WITHOUT RapidAPI (direct / external)](#9-use-it-without-rapidapi-direct--external)
10. [List & sell on RapidAPI (step-by-step)](#10-list--sell-on-rapidapi-step-by-step)
11. [Set a custom rate limit](#11-set-a-custom-rate-limit)
12. [Tuning concurrency & performance](#12-tuning-concurrency--performance)
13. [Webhooks (async jobs)](#13-webhooks-async-jobs)
14. [Error handling](#14-error-handling)
15. [Best practices](#15-best-practices)
16. [Going beyond (Phase 2 ideas)](#16-going-beyond-phase-2-ideas)

---

## 1. What this project is

Pixforge turns a URL into a screenshot or PDF through a simple HTTP API. It is
designed to:

- Run cheaply on **Render Free** (512 MB RAM, spins down when idle).
- Be a **drop-in alternative** to commercial screenshot APIs (Urlbox,
  ScreenshotOne, APIRobots) — same endpoint shape, so existing RapidAPI
  consumers can switch by changing the host + key.
- Work **both** behind RapidAPI *and* standalone (you can use it privately or
  expose it to your own apps).

It is **not** a multi-tenant SaaS with billing — billing happens on RapidAPI.
Pixforge just serves screenshots and enforces a per-key rate limit.

---

## 2. Project structure

```
urltoscreenshot/
├── app/
│   ├── main.py        # FastAPI app factory, lifecycle, rate-limit middleware
│   ├── config.py      # All env-driven settings (single source of truth)
│   ├── browser.py     # Global Chromium launch + Semaphore(1) concurrency gate
│   ├── screenshot.py  # Core capture logic + 133 device presets
│   ├── routes.py      # All HTTP endpoints + auth dependency
│   ├── models.py      # Pydantic request models + param validation
│   ├── jobs.py        # In-memory async job store + webhook dispatch
│   └── errors.py      # Uniform error envelope (400/401/403/404/429/500/503)
├── Dockerfile         # Playwright/Chromium base image (includes the browser)
├── render.yaml        # One-click Render deploy definition (free plan)
├── requirements.txt   # Python deps (pinned)
├── test_features.sh   # Reproducible full test suite
├── TEST_REPORT.md     # Test results + per-feature code
├── tutorials.md       # RapidAPI listing copy (paste-ready)
└── README.md          # This file
```

---

## 3. How it works (architecture)

```
Request ──▶ [Rate-limit middleware] ──▶ [Auth: RapidAPI key | Bearer | job token]
                                         │
                                         ▼
                              FastAPI router (/v1/...)
                                         │
                                         ▼
                          Global Chromium (launched ONCE at startup)
                                         │  acquire Semaphore(MAX_CONCURRENCY)
                                         ▼
                          New browser context (isolated) → page.goto → screenshot
                                         │  release semaphore
                                         ▼
                          Response: binary image / JSON / PDF / job status
```

Key design decisions (why it survives the free tier):

- **One browser, many contexts.** Chromium launches once (cold start ≈ 6–10 s).
  Each request opens a *new context* (isolated cookies/cache) and closes it
  after. This avoids the 2–5 s cost of launching a browser per request.
- **Concurrency gate.** A `Semaphore(MAX_CONCURRENCY)` (default **1**) lets only
  N screenshots run at once, preventing OOM on 512 MB.
- **Resource blocking.** `media` and `font` requests are aborted mid-flight,
  shrinking page weight and capture time by 30–50%.
- **JPEG default.** `type=jpeg&quality=80` is ~10× smaller than PNG — ideal for
  previews. PNG available when quality matters.
- **In-memory job store.** Async jobs live in RAM with a 24 h TTL. No Redis
  needed. (Jobs are short; the free tier mostly sleeps *between* requests, not
  mid-job — and you're using a cron ping to keep it awake, so this is safe.)

The only stateful thing is the async job store. Everything else is
stateless per request.

---

## 4. Endpoints at a glance

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/v1/screenshots/image` | yes | Binary screenshot (jpeg/png) |
| GET | `/v1/screenshots/json` | yes | Base64 screenshot in JSON |
| GET | `/v1/pdf` | yes | PDF of the page |
| POST | `/v1/batch` | yes | Up to 10 URLs at once |
| POST | `/v1/async/screenshots/image` | yes | Submit async job → 202 |
| GET | `/v1/jobs/{job_id}` | job token (Bearer) | Poll job result |
| GET | `/v1/devices` | yes | 133 emulation presets |
| GET | `/healthz` | no | Health check (`{"status":"ok","browser":bool}`) |
| GET | `/docs` | no | Interactive Swagger UI |

**Screenshot parameters** (on `/image`, `/json`, and each `/batch` `options`):

| Param | Type | Default | Notes |
|---|---|---|---|
| `url` | string | **required** | Must be `http://` or `https://` |
| `width` / `height` | int | 1280 / 720 | Viewport size |
| `type` | `jpeg`\|`png` | `jpeg` | Output format |
| `quality` | int 1–100 | 80 | JPEG only |
| `full_page` | bool | false | Capture entire scroll height |
| `dark_mode` | bool | false | Emulate `prefers-color-scheme: dark` |
| `emulate_device` | string | — | Name from `/v1/devices` (overrides w/h) |
| `mobile` | bool | false | Mobile viewport + touch |
| `scale` | float | 1 | Device scale factor (2 = Retina) |
| `delay` | int ms | 0 | Wait after load before shooting |
| `wait_until` | `load`\|`networkidle`\|`domcontentloaded` | `networkidle` | Nav wait |
| `timeout` | int ms | 10000 | Nav timeout |

---

## 5. Configuration / environment variables

All settings come from env vars (see `app/config.py`). On Render these live in
`render.yaml` or the dashboard.

| Variable | Default | What it does |
|---|---|---|
| `PIXFORGE_API_KEY` | *(empty)* | **Admin/direct key.** Lets you call the service without RapidAPI. Auto-generated on Render. |
| `PIXFORGE_RATE_LIMIT` | `10` | Requests/minute **per caller key** (RapidAPI key, admin key, or job token). |
| `PIXFORGE_CONCURRENCY` | `1` | Max simultaneous screenshots. Raise only with more RAM. |
| `PIXFORGE_WIDTH` / `PIXFORGE_HEIGHT` | `1280` / `720` | Default viewport when not specified. |
| `PIXFORGE_TYPE` | `jpeg` | Default output format. |
| `PIXFORGE_QUALITY` | `80` | Default JPEG quality. |
| `PIXFORGE_TIMEOUT_MS` | `10000` | Default navigation timeout. |
| `PIXFORGE_JOB_TTL` | `86400` | Async job lifetime in seconds (24 h). |
| `PIXFORGE_NAME` | `Pixforge` | Product name (also drives the webhook header `X-Pixforge-Signature`). |

---

## 6. Local development & testing

Requirements: Python 3.11+, `uv`, and the Playwright Chromium browser.

```bash
cd urltoscreenshot

# 1. Create venv + install deps
uv venv
uv pip install -r requirements.txt

# 2. Install the browser (one-time)
uv run playwright install chromium chromium-headless-shell

# 3. Run (from the PROJECT ROOT, note the word "uvicorn")
PIXFORGE_API_KEY=localkey uv run uvicorn app.main:app --host 127.0.0.1 --port 10000

# 4. Wait for readiness
curl -s http://127.0.0.1:10000/healthz
# -> {"status":"ok","browser":true}
```

> ⚠️ **WSL/Git-Bash gotchas**
> - Always run `uvicorn app.main:app` **with** the `uvicorn` word — `uv run
>   main:app` looks for a program named `main:app` and fails.
> - Run from the **project root** (`urltoscreenshot/`), not from `app/`.
> - A venv built on Windows won't work under WSL/Linux. If you switch shells,
>   rebuild it: `uv venv && uv pip install -r requirements.txt`.

Test everything:

```bash
bash test_features.sh
# PASS=N FAIL=M  (24/24 expected)
```

Full results + per-call code: see `TEST_REPORT.md`.

---

## 7. Host on Render (step-by-step)

### Option A — One-click via `render.yaml` (recommended)

1. Push this repo to GitHub.
2. Go to **Render Dashboard → New → Blueprint**.
3. Connect the GitHub repo. Render reads `render.yaml` and creates a **Docker
   web service** on the **free plan** (`pixforge`).
4. Click **Deploy**. Render builds the image (Chromium is pre-installed in the
   base image, so no extra apt steps).
5. Once live, your URL is `https://pixforge-<hash>.onrender.com`.

`render.yaml` already sets: `plan: free`, `healthCheckPath: /healthz`, and the
env vars (`PIXFORGE_API_KEY` auto-generated, `PIXFORGE_RATE_LIMIT=10`,
`PIXFORGE_CONCURRENCY=1`, defaults for size/type/quality/timeout).

### Option B — Manual

1. **New → Web Service** → connect repo.
2. **Runtime:** Docker. **Plan:** Free.
3. **Health check path:** `/healthz`.
4. **Start command** (set automatically by Dockerfile):
   `uvicorn app.main:app --host 0.0.0.0 --port 10000`
5. Add env vars from the table in §5 (at minimum let Render auto-generate
   `PIXFORGE_API_KEY`).
6. Deploy.

Either way, the service listens on Render's `$PORT` (the Dockerfile/uvicorn uses
`10000`, which Render maps). Your first request after a cold start takes ~10 s
while Chromium boots — that's expected.

---

## 8. Keep the free tier awake

Render Free spins the service down after ~15 min of inactivity, and has a 750 hr
/month cap. Two mitigations:

1. **Cron ping (you're already doing this).** Use an external pinger
   (UptimeRobot, Cron-job.org, or a GitHub Action scheduled workflow) to `GET
   https://<your-app>.onrender.com/healthz` every ~10 minutes. This keeps the
   browser warm and prevents job-store interruption.
2. **Treat cold starts gracefully.** Responses during the first ~10 s after
   wake may return `503` if a request lands before Chromium finishes booting.
   RapidAPI consumers should retry with backoff.

> 💡 If demand grows, switch to a paid instance (`render.yaml` → `plan:
> starter`, ~$7/mo, 2 GB RAM, no sleep). Then raise `PIXFORGE_CONCURRENCY` to
> 3–4.

---

## 9. Use it WITHOUT RapidAPI (direct / external)

Pixforge doesn't require RapidAPI. You can call it directly using your
**admin key** (`PIXFORGE_API_KEY`). This is perfect for your own apps, cron
jobs, or internal tools.

Start the service (or use your Render URL) and send:

```bash
B="https://pixforge-<hash>.onrender.com"   # or http://127.0.0.1:10000 locally
K="Authorization: Bearer $PIXFORGE_API_KEY"

# Screenshot → file
curl -s -H "$K" "$B/v1/screenshots/image?url=https://example.com&width=1280" -o shot.jpg

# Base64 JSON
curl -s -H "$K" "$B/v1/screenshots/json?url=https://example.com&dark_mode=true"

# PDF
curl -s -H "$K" "$B/v1/pdf?url=https://example.com&format=A4" -o page.pdf

# Batch
curl -s -H "$K" -H "Content-Type: application/json" -X POST "$B/v1/batch" \
  -d '{"requests":[{"url":"https://example.com"},{"url":"https://example.org"}]}'
```

**Python example (direct use):**

```python
import requests, base64, os

BASE = "https://pixforge-<hash>.onrender.com"
HEADERS = {"Authorization": f"Bearer {os.environ['PIXFORGE_API_KEY']}"}

# Binary
r = requests.get(f"{BASE}/v1/screenshots/image",
                 params={"url": "https://example.com", "type": "jpeg"},
                 headers=HEADERS)
with open("shot.jpg", "wb") as f:
    f.write(r.content)

# Base64 JSON
data = requests.get(f"{BASE}/v1/screenshots/json",
                    params={"url": "https://example.com"},
                    headers=HEADERS).json()
img_bytes = base64.b64decode(data["image"])
```

**Async from your own code** (poll with the returned `access_token`):

```python
import requests
BASE = "https://pixforge-<hash>.onrender.com"
H = {"Authorization": f"Bearer {os.environ['PIXFORGE_API_KEY']}"}

job = requests.post(f"{BASE}/v1/async/screenshots/image",
                    json={"url": "https://example.com", "options": {"full_page": True}},
                    headers=H).json()
token = job["access_token"]
# poll
while True:
    res = requests.get(f"{BASE}/v1/jobs/{job['job_id']}",
                       headers={"Authorization": f"Bearer {token}"}).json()
    if res["status"] in ("completed", "failed"):
        break
    time.sleep(2)
```

---

## 10. List & sell on RapidAPI (step-by-step)

RapidAPI sits **in front** of your Render service. It forwards each call with
`X-RapidAPI-Key` and `X-RapidAPI-Host` headers, and handles billing/plans.

1. **Deploy to Render first** (§7). Note your Render URL.
2. **Create the API** at rapidapi.com → *Add API* → *Create an API*.
   - **Name:** Pixforge
   - **Category:** Visual Recognition / Data / Developer Tools
   - **Base URL:** your Render URL (`https://pixforge-<hash>.onrender.com`)
3. **Add endpoints** (mirror your routes). For each, set the method + path and a
   sample. Use `tutorials.md` as the listing copy. Example endpoint:
   - `GET /v1/screenshots/image` with query param `url` (required).
   - Repeat for `/json`, `/pdf`, `/batch` (POST+body), `/async/...` (POST),
     `/jobs/{job_id}` (GET), `/devices` (GET).
4. **Define plans / pricing.** E.g.:
   - *Basic*: 10 req/min, $0 or $X/mo.
   - *Pro*: 100 req/min, $Y/mo.
   (Your per-key rate limit in `PIXFORGE_RATE_LIMIT` is the hard ceiling; RapidAPI
   plans are the commercial gate. Keep them aligned — e.g. set `PIXFORGE_RATE_LIMIT`
   to your Pro value so no one exceeds it.)
5. **Test from RapidAPI console** using your own subscribed key.
6. **Publish** when ready.

**How auth flows:** A consumer's call hits RapidAPI → RapidAPI adds
`X-RapidAPI-Key: <consumer-key>` → your service validates *that header* (see
`routes.require_auth`). Your `PIXFORGE_API_KEY` is **not** used by RapidAPI
traffic; it's only for your direct/admin access (§9).

**Consumer call shape (what your RapidAPI buyers use):**

```bash
curl -X GET "https://pixforge.p.rapidapi.com/v1/screenshots/image?url=https://example.com" \
  -H "X-RapidAPI-Key: <consumer-key>" \
  -H "X-RapidAPI-Host: pixforge.p.rapidapi.com"
```

> Note: `pixforge.p.rapidapi.com` is RapidAPI's assigned host — use whatever
> they give you in the dashboard.

---

## 11. Set a custom rate limit

The limit is **per caller key** (each RapidAPI consumer key, your admin key, or
each job token is bucketed separately) and is controlled by one env var:

```bash
PIXFORGE_RATE_LIMIT=100      # 100 requests/minute per key
```

- **Render:** add `PIXFORGE_RATE_LIMIT` to `render.yaml` envVars (or the
  dashboard) and redeploy.
- **Local:** `PIXFORGE_RATE_LIMIT=100 uv run uvicorn app.main:app ...`
- **Per-plan:** set it to your highest plan's value (e.g. Pro = 100). RapidAPI
  enforces lower tiers commercially; your service just won't exceed the env cap.

**Behavior / headers:** every response includes
`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`. On
exceeding the limit you get `429` with `Retry-After`. The limit window is a
rolling 60-second counter (not a fixed clock window), so it self-resets.

---

## 12. Tuning concurrency & performance

`PIXFORGE_CONCURRENCY` controls how many screenshots run in parallel.

| RAM | Recommended concurrency | Notes |
|---|---|---|
| 512 MB (Render Free) | **1** | Safe. One page ≈ 30–60 MB + Chromium 150–250 MB. |
| 2 GB (Render Starter) | 3–4 | Comfortable headroom. |
| 4 GB+ | 5–8 | High throughput. |

Higher concurrency = more throughput but more RAM risk. If you see `503`s or
crashes under load, lower it. The semaphore guarantees we never exceed it.

Other levers:
- `PIXFORGE_QUALITY` (lower = smaller/faster JPEG).
- `PIXFORGE_TIMEOUT_MS` (lower = fails fast on slow sites).
- `emulate_device` / `mobile` keep default viewport sizing predictable.

---

## 13. Webhooks (async jobs)

For long or `full_page` captures, use async + webhooks (avoids polling/timeouts).

Submit with a webhook:

```bash
curl -X POST "$B/v1/async/screenshots/image" \
  -H "$K" -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "options": { "full_page": true },
    "webhook_url": "https://myapp.com/webhook",
    "webhook_secret": "my-secret"
  }'
```

When the job finishes, Pixforge POSTs the full job result (same as the poll
response) to `webhook_url`, with an HMAC-SHA256 signature in the
`X-Pixforge-Signature` header. **Verify it:**

```js
import crypto from "crypto";
function verify(rawBody, signature, secret) {
  const expected = crypto.createHmac("sha256", secret).update(rawBody).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}
```

(Virtual device name appears in the header as `X-Pixforge-Signature`; if you
change `PIXFORGE_NAME`, the header prefix changes too.)

---

## 14. Error handling

All errors return a uniform envelope:

```json
{ "error": true, "code": 400, "message": "Invalid request parameters.", "details": { ... } }
```

| Status | Meaning | Action |
|---|---|---|
| `400` | Bad params (bad URL, unknown device, quality>100…) | Fix input; see `details`. |
| `401` | Missing/invalid auth | Send `X-RapidAPI-Key` or `Authorization: Bearer`. |
| `403` | Invalid job `access_token` (on poll) | Use the token from job creation. |
| `404` | Job not found/expired | Jobs expire after 24 h (`PIXFORGE_JOB_TTL`). |
| `429` | Rate limit | Back off; read `X-RateLimit-*` / `Retry-After`. |
| `500` | Internal error | Retry with exponential backoff. |
| `503` | Browser not ready (cold start) | Retry after `Retry-After`. |

This matches the RapidAPI consumer expectations documented in `tutorials.md`.

---

## 15. Best practices

**For you (operator):**
- Keep the cron ping to `/healthz` running so the free tier stays warm.
- Align `PIXFORGE_RATE_LIMIT` with your top RapidAPI plan.
- Cache screenshots of the same URL on your side (or tell consumers to) to save
  quota and money.
- Monitor Render logs; if you hit OOM, lower `PIXFORGE_CONCURRENCY`.

**For API consumers (put this in your listing):**
- Prefer **async** for `full_page` or very long pages.
- Default to **JPEG q80** for previews (≈10× smaller than PNG).
- Validate URLs before sending (only `http(s)` accepted).
- Respect rate limits — read `X-RateLimit-*` and back off on `429`.
- Use **webhooks** in production instead of polling.

**Security:**
- Never expose `PIXFORGE_API_KEY` publicly; it's your admin key.
- Always verify webhook `X-Pixforge-Signature` with your `webhook_secret`.
- The service accepts only valid `http(s)` URLs (validated server-side).

---

## 16. Going beyond (Phase 2 ideas)

The `/v1/` router is structured so you can add a "website intelligence toolkit"
without rewrites:
- `/metadata` — Open Graph tags, title, favicon
- `/markdown` — webpage → Markdown
- `/links` — extract all links
- `/readability` — clean article extraction
- `/colors` — dominant color palette

These would use `BeautifulSoup`/`readability-lxml`/`markdownify` on the already-
fetched page, reusing the same browser context pattern. Good differentiator vs.
single-purpose screenshot APIs.

---

## Quick command reference

```bash
# Local run
PIXFORGE_API_KEY=localkey uv run uvicorn app.main:app --host 127.0.0.1 --port 10000

# Test
bash test_features.sh

# Env examples
PIXFORGE_RATE_LIMIT=100 PIXFORGE_CONCURRENCY=1 PIXFORGE_TYPE=jpeg PIXFORGE_QUALITY=80

# Health
curl https://<your-app>.onrender.com/healthz
```

**Files you'll touch most:** `app/config.py` (settings), `render.yaml`
(deploy), `app/routes.py` (endpoints), `app/screenshot.py` (capture logic).
