"""Pixforge configuration (env-driven, with sane free-tier defaults)."""
import os

PRODUCT_NAME = os.getenv("PIXFORGE_NAME", "Pixforge")
WEBHOOK_HEADER = f"X-{PRODUCT_NAME}-Signature"

# Direct/admin auth: lets you call the service without going through RapidAPI.
ADMIN_API_KEY = os.getenv("PIXFORGE_API_KEY", "")

# Rate limit: requests per minute, per caller key.
RATE_LIMIT_PER_MINUTE = int(os.getenv("PIXFORGE_RATE_LIMIT", "10"))

# Concurrency: at most N simultaneous screenshots (Render free has ~512MB RAM).
MAX_CONCURRENCY = int(os.getenv("PIXFORGE_CONCURRENCY", "1"))

# Default capture settings (consumer can override per request).
DEFAULT_WIDTH = int(os.getenv("PIXFORGE_WIDTH", "1280"))
DEFAULT_HEIGHT = int(os.getenv("PIXFORGE_HEIGHT", "720"))
DEFAULT_TYPE = os.getenv("PIXFORGE_TYPE", "jpeg")  # jpeg | png
DEFAULT_QUALITY = int(os.getenv("PIXFORGE_QUALITY", "80"))  # 1-100, jpeg only
DEFAULT_TIMEOUT_MS = int(os.getenv("PIXFORGE_TIMEOUT_MS", "10000"))

# Async jobs auto-expire after this many seconds (reference contract: 24h).
JOB_TTL_SECONDS = int(os.getenv("PIXFORGE_JOB_TTL", str(24 * 60 * 60)))

# Chromium launch flags — tuned for low RAM on Render free.
CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-default-apps",
    "--mute-audio",
    "--hide-scrollbars",
    "--no-first-run",
    "--no-zygote",
]

# Resource types we block to shrink payload + speed up capture.
BLOCKED_RESOURCE_TYPES = {"media", "font"}

# Max URLs per /batch request (reference contract).
BATCH_MAX = 10
