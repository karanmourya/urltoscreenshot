# Pixforge — URL-to-Screenshot & PDF API

Capture website screenshots, PDFs, and device-emulated images with a single API
call. Built for AI agents, SEO tools, link-preview generators, and automation
platforms (n8n, Make, Zapier).

This tutorial walks you from subscribe → first call → advanced recipes.

---

## 1. Setup

### Subscribe on RapidAPI
1. Open the **Pixforge** API page on RapidAPI.
2. Click **Subscribe** and pick a plan (Basic = 10 req/min, Pro = 100 req/min).
3. Copy your key from the **Code Snippets** panel — it appears as `X-RapidAPI-Key`.

### Authentication
Every request must include these two headers:

```
X-RapidAPI-Key: <your-rapidapi-key>
X-RapidAPI-Host: pixforge.p.rapidapi.com
```

> Pixforge also works **without RapidAPI** if you host it yourself: send
> `Authorization: Bearer <PIXFORGE_API_KEY>` instead. The examples below use
> the RapidAPI headers.

---

## 2. Capture a Screenshot (Instant)

### Binary image (JPEG/PNG)
Returns raw image bytes — save them directly to a file.

**cURL**
```bash
curl -X GET "https://pixforge.p.rapidapi.com/v1/screenshots/image?url=https://example.com&width=1280&type=jpeg" \
  -H "X-RapidAPI-Key: <your-key>" \
  -H "X-RapidAPI-Host: pixforge.p.rapidapi.com" \
  --output screenshot.jpg
```

**JavaScript (fetch)**
```js
const res = await fetch(
  "https://pixforge.p.rapidapi.com/v1/screenshots/image?url=https://example.com&width=1280&type=jpeg",
  { headers: { "X-RapidAPI-Key": "<your-key>", "X-RapidAPI-Host": "pixforge.p.rapidapi.com" } }
);
const blob = await res.blob();
// download or display the blob
```

**Python**
```python
import requests
resp = requests.get(
    "https://pixforge.p.rapidapi.com/v1/screenshots/image",
    params={"url": "https://example.com", "width": "1280", "type": "jpeg"},
    headers={"X-RapidAPI-Key": "<your-key>", "X-RapidAPI-Host": "pixforge.p.rapidapi.com"},
)
with open("screenshot.jpg", "wb") as f:
    f.write(resp.content)
```

### Base64 JSON
Same capture, but the response is JSON with a base64-encoded image — handy when
you can't write files (serverless functions, browsers).

**cURL**
```bash
curl -X GET "https://pixforge.p.rapidapi.com/v1/screenshots/json?url=https://example.com&dark_mode=true" \
  -H "X-RapidAPI-Key: <your-key>" \
  -H "X-RapidAPI-Host: pixforge.p.rapidapi.com"
```

**JavaScript (fetch)**
```js
const res = await fetch(
  "https://pixforge.p.rapidapi.com/v1/screenshots/json?url=https://example.com&dark_mode=true",
  { headers: { "X-RapidAPI-Key": "<your-key>", "X-RapidAPI-Host": "pixforge.p.rapidapi.com" } }
);
const data = await res.json();
// data.image  -> base64 string
// data.url    -> original url
// data.options -> applied options
```

**Python**
```python
import requests, base64
data = requests.get(
    "https://pixforge.p.rapidapi.com/v1/screenshots/json",
    params={"url": "https://example.com", "dark_mode": "true"},
    headers={"X-RapidAPI-Key": "<your-key>", "X-RapidAPI-Host": "pixforge.p.rapidapi.com"},
).json()
image_bytes = base64.b64decode(data["image"])
```

---

## 3. Capture a PDF

Generate a formatted PDF (A4 by default) of any page.

**cURL**
```bash
curl -X GET "https://pixforge.p.rapidapi.com/v1/pdf?url=https://example.com&format=A4&landscape=true" \
  -H "X-RapidAPI-Key: <your-key>" \
  -H "X-RapidAPI-Host: pixforge.p.rapidapi.com" \
  --output page.pdf
```

**Parameters:** `format` (`A4`, `Letter`, `A3`…), `landscape` (`true`/`false`),
`width`, `height`, `dark_mode`, `emulate_device`, `wait_until`, `timeout`.

---

## 4. Batch Screenshots

Capture up to **10 URLs** in a single request (cheaper than 10 calls).

**cURL**
```bash
curl -X POST "https://pixforge.p.rapidapi.com/v1/batch" \
  -H "X-RapidAPI-Key: <your-key>" \
  -H "X-RapidAPI-Host: pixforge.p.rapidapi.com" \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      { "url": "https://example.com", "options": { "width": "1280" } },
      { "url": "https://httpbin.org" }
    ]
  }'
```

**JavaScript (fetch)**
```js
const res = await fetch("https://pixforge.p.rapidapi.com/v1/batch", {
  method: "POST",
  headers: {
    "X-RapidAPI-Key": "<your-key>",
    "X-RapidAPI-Host": "pixforge.p.rapidapi.com",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    requests: [
      { url: "https://example.com", options: { width: "1280" } },
      { url: "https://httpbin.org" },
    ],
  }),
});
const result = await res.json();
// result.total, result.successful, result.failed
// result.results[].image  -> base64 (on success)
// result.results[].error  -> string (on failure)
```

---

## 5. Async Capture (Long-running jobs)

Use async for large or `full_page` captures that risk a timeout. You submit a
job, then poll (or receive a webhook) for the result.

### Step 1 — Submit a job
**cURL**
```bash
curl -X POST "https://pixforge.p.rapidapi.com/v1/async/screenshots/image" \
  -H "X-RapidAPI-Key: <your-key>" \
  -H "X-RapidAPI-Host: pixforge.p.rapidapi.com" \
  -H "Content-Type: application/json" \
  -d '{ "url": "https://example.com", "options": { "full_page": true } }'
```

**202 Accepted response**
```json
{
  "job_id": "abc123",
  "access_token": "tok_xxx",
  "status": "pending",
  "status_url": "/v1/jobs/abc123",
  "created_at": "2026-07-09T00:00:00Z"
}
```

### Step 2 — Poll for the result
Use the `access_token` as a Bearer token. Poll every 2–3 seconds.

**cURL**
```bash
curl -X GET "https://pixforge.p.rapidapi.com/v1/jobs/abc123" \
  -H "X-RapidAPI-Key: <your-key>" \
  -H "X-RapidAPI-Host: pixforge.p.rapidapi.com" \
  -H "Authorization: Bearer tok_xxx"
```

Job states: `pending` → `processing` → `completed` | `failed`. Jobs expire
after **24 hours**.

### Step 3 — Use a webhook instead of polling (recommended for production)
Pass `webhook_url` when creating the job. Pixforge POSTs the result there when
done, signed with `HMAC-SHA256` in the `X-Pixforge-Signature` header.

```json
{
  "url": "https://example.com",
  "webhook_url": "https://myapp.com/webhook",
  "webhook_secret": "my-secret"
}
```

Verify the signature in your webhook handler:
```js
import crypto from "crypto";
function verify(rawBody, signature, secret) {
  const expected = crypto.createHmac("sha256", secret).update(rawBody).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}
```

---

## 6. List Available Devices

`emulate_device` accepts 130+ real device presets.

**cURL**
```bash
curl -X GET "https://pixforge.p.rapidapi.com/v1/devices" \
  -H "X-RapidAPI-Key: <your-key>" \
  -H "X-RapidAPI-Host: pixforge.p.rapidapi.com"
```

Returns names like `"iPhone 14"`, `"Pixel 7"`, `"Galaxy S23"`, `"iPad Pro"`.
Pass any of them as `emulate_device` (overrides `width`/`height`).

---

## 7. Common Recipes

**Responsive design test** — same page at 3 viewports
```bash
for device in "iPhone 14" "iPad Pro" "Desktop"; do
  curl -X GET "https://pixforge.p.rapidapi.com/v1/screenshots/image?url=https://mysite.com&emulate_device=$device" \
    -H "X-RapidAPI-Key: <your-key>" \
    -H "X-RapidAPI-Host: pixforge.p.rapidapi.com" \
    --output "$device.jpg"
done
```

**PDF report**
```bash
curl -X GET "https://pixforge.p.rapidapi.com/v1/pdf?url=https://mysite.com/dashboard&format=Letter&landscape=true" \
  -H "X-RapidAPI-Key: <your-key>" \
  -H "X-RapidAPI-Host: pixforge.p.rapidapi.com" \
  --output report.pdf
```

**Monitor a page for changes** (run on a cron)
```js
const res = await fetch(
  "https://pixforge.p.rapidapi.com/v1/screenshots/json?url=https://competitor.com/pricing",
  { headers: { "X-RapidAPI-Key": "<your-key>", "X-RapidAPI-Host": "pixforge.p.rapidapi.com" } }
);
const { image } = await res.json();
// compare image hash with your previous capture
```

**Dark-mode full-page capture**
```bash
curl -X GET "https://pixforge.p.rapidapi.com/v1/screenshots/image?url=https://example.com&dark_mode=true&full_page=true&type=png" \
  -H "X-RapidAPI-Key: <your-key>" \
  -H "X-RapidAPI-Host: pixforge.p.rapidapi.com" \
  --output dark_full.png
```

---

## 8. Screenshot Parameters

All parameters work on `/image`, `/json`, and inside each `/batch` request's
`options` object.

| Param | Type | Default | Description |
|---|---|---|---|
| `url` | string | **required** | Target URL (must be `http://` or `https://`) |
| `width` | int | 1280 | Viewport width (px) |
| `height` | int | 720 | Viewport height (px) |
| `type` | `jpeg`\|`png` | `jpeg` | Output format |
| `quality` | int (1–100) | 80 | JPEG quality |
| `full_page` | bool | false | Capture entire scrollable page |
| `dark_mode` | bool | false | Emulate `prefers-color-scheme: dark` |
| `emulate_device` | string | — | Device name from `/v1/devices` (overrides width/height) |
| `mobile` | bool | false | Mobile viewport + touch |
| `scale` | float | 1 | Device scale factor (e.g. `2` for Retina) |
| `delay` | int (ms) | 0 | Wait after load before shooting |
| `wait_until` | `load`\|`networkidle`\|`domcontentloaded` | `networkidle` | Navigation wait condition |
| `timeout` | int (ms) | 10000 | Navigation timeout |

---

## 9. Error Handling

All errors return a uniform JSON envelope:

```json
{ "error": true, "code": 400, "message": "Invalid request parameters.", "details": { ... } }
```

| Status | Meaning | What to do |
|---|---|---|
| `400` | Bad request — missing/invalid params | Check the `details` field |
| `401` | Missing or invalid authentication | Send `X-RapidAPI-Key` |
| `403` | Invalid job access token (on poll) | Use the `access_token` from job creation |
| `404` | Job not found or expired | Jobs expire after 24h |
| `429` | Rate limit exceeded | Slow down; check `X-RateLimit-*` headers |
| `500` | Internal server error | Retry with exponential backoff |
| `503` | Browser not ready (e.g. cold start) | Retry after `Retry-After` |

Rate-limit headers on every response: `X-RateLimit-Limit`,
`X-RateLimit-Remaining`, `X-RateLimit-Reset`. On `429` you also get
`Retry-After`.

---

## 10. Best Practices

- **Use async for `full_page` captures** — very long pages can time out on sync endpoints.
- **Set a sensible timeout** — keep the default unless you have a reason to raise it.
- **Cache on your side** — screenshots of the same URL can be cached to save quota.
- **Use webhooks in production** — avoids polling and scales better.
- **Validate URLs first** — only valid `http(s)` URLs are accepted.
- **Respect rate limits** — read the `X-RateLimit-*` headers and back off on `429`.
- **Default to JPEG q80** — roughly 10× smaller than PNG, perfect for previews.
