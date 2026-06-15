"""JobMagnet — central configuration.

Everything you'll want to tweak early lives here. Change a value, restart the
server, done. Mirrors RingBack's config so the two products stay siblings.
"""
import os
from pathlib import Path

# Load a local .env (if present) so secrets stay out of code. Real environment
# variables always win over .env values (setdefault).
_ENV_FILE = Path(__file__).resolve().parent / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _val = _line.split("=", 1)
            os.environ.setdefault(_key.strip(), _val.strip().strip('"').strip("'"))

# --- Branding -------------------------------------------------------------
APP_NAME = "JobMagnet"
TAGLINE = "Become the contractor jobs come to."

# --- AI brain / provider --------------------------------------------------
# Which brain writes content:
#   "demo"    -> built-in templated writer (zero setup, always works)
#   "claude"  -> Anthropic Claude (set ANTHROPIC_API_KEY)
#   "minimax" -> MiniMax, OpenAI-compatible (set MINIMAX_API_KEY)
# If the chosen provider has no key, JobMagnet falls back to demo so it never breaks.
PROVIDER = os.environ.get("JOBMAGNET_PROVIDER", "demo")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
MINIMAX_BASE_URL = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io")

# --- Messaging (Phase 0): outbound SMS/email. Safe no-op until configured. ---
# SMS via Twilio. Leave blank to keep SMS simulated (logged, not sent).
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.environ.get("TWILIO_FROM", "")
# Email via SMTP. Leave blank to keep email simulated.
EMAIL_FROM = os.environ.get("JOBMAGNET_EMAIL_FROM", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or "587")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
# Quiet hours (local clock) -- no marketing SMS sends inside this window.
# Default 9pm-8am. Transactional messages still respect opt-outs but not quiet hours.
QUIET_HOURS_START = int(os.environ.get("JOBMAGNET_QUIET_START", "21") or "21")
QUIET_HOURS_END = int(os.environ.get("JOBMAGNET_QUIET_END", "8") or "8")
# Physical mailing address (CAN-SPAM requires one in marketing email).
MAILING_ADDRESS = os.environ.get("JOBMAGNET_MAILING_ADDRESS", "")

# --- Cold phone channels (Phase 6): HARD-GATED, default OFF. ---
# Cold SMS needs prior express WRITTEN consent (TCPA). Cold AI voice is the highest
# legal risk (FCC treats AI voice as artificial/prerecorded). These do not ship to
# real customers until a TCPA attorney reviews the consent flows. Even when enabled,
# the code still requires per-contact written consent on file.
COLD_SMS_ENABLED = os.environ.get("JOBMAGNET_COLD_SMS", "").strip().lower() in ("1", "true", "yes", "on")
COLD_VOICE_ENABLED = os.environ.get("JOBMAGNET_COLD_VOICE", "").strip().lower() in ("1", "true", "yes", "on")

# Shared secret for inbound webhooks (Twilio, RingBack). When set, /webhooks/* require
# a matching `token`. Empty -> open (local dev only); MUST be set before deploying.
WEBHOOK_TOKEN = os.environ.get("JOBMAGNET_WEBHOOK_TOKEN", "")

# --- Publishing (Phase 2): social/GBP connectors. Safe no-op until configured. ---
# Google Business Profile publishing (OAuth token). Empty -> GBP posts simulated.
GBP_ACCESS_TOKEN = os.environ.get("GBP_ACCESS_TOKEN", "")
# Meta (Facebook/Instagram) publishing. Empty -> FB/IG are "assisted" (copy/paste).
META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "")
# AI image generation. Empty -> image generation simulated (prompt only).
IMAGE_API_KEY = os.environ.get("JOBMAGNET_IMAGE_KEY", "")

# --- RingBack link (Phase 3): OPTIONAL booking feed for the closed loop. ---
# JobMagnet is standalone; when these are set it can pull booked-job data from a
# RingBack instance to compute cost-per-booked-job automatically. Empty -> the loop
# runs on JobMagnet's own conversion data (manual mark-won / tracked numbers).
RINGBACK_API_URL = os.environ.get("RINGBACK_API_URL", "")
RINGBACK_API_KEY = os.environ.get("RINGBACK_API_KEY", "")

# --- Billing (Stripe). Safe no-op until configured: plan buttons fall back to an
# in-app switch until STRIPE_SECRET_KEY + the price IDs are set. ---
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
# Create three recurring Prices in Stripe (Pro/Premium/Scale) and paste their IDs:
STRIPE_PRICE_PRO = os.environ.get("STRIPE_PRICE_PRO", "")
STRIPE_PRICE_PREMIUM = os.environ.get("STRIPE_PRICE_PREMIUM", "")
STRIPE_PRICE_SCALE = os.environ.get("STRIPE_PRICE_SCALE", "")

# --- Runtime --------------------------------------------------------------
DEBUG = os.environ.get("JOBMAGNET_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")
PORT = int(os.environ.get("JOBMAGNET_PORT", "8900") or "8900")

# Signs the login session cookie. MUST be a long random value in production.
SECRET_KEY = os.environ.get("JOBMAGNET_SECRET", "dev-insecure-secret-change-me")
# Encrypts stored connection credentials (Twilio/Google/Meta tokens) at rest. When set,
# connections.credentials is sealed with authenticated encryption; when blank (dev), creds
# are stored in the clear and the Connections UI flags them as unencrypted. MUST be set to
# a long random value before onboarding real tenants. Generate: python -c "import secrets;
# print(secrets.token_urlsafe(48))".
SECRETS_KEY = os.environ.get("JOBMAGNET_SECRETS_KEY", "")
# HTTPS-only cookie; leave off for local http dev, turn on in prod (JOBMAGNET_HTTPS=1).
SESSION_COOKIE_SECURE = os.environ.get("JOBMAGNET_HTTPS", "").strip().lower() in ("1", "true", "yes", "on")

# Starter owner login seeded for "client zero" (business 1 = Heritage).
SEED_OWNER_EMAIL = os.environ.get("JOBMAGNET_OWNER_EMAIL", "heritagehousepainting@gmail.com")
SEED_OWNER_PASSWORD = os.environ.get("JOBMAGNET_OWNER_PASSWORD", "jobmagnet123")

# --- Storage --------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("JOBMAGNET_DB_PATH", "").strip() or (BASE_DIR / "jobmagnet.db")

# --- Content platforms ----------------------------------------------------
# The channels the Content Engine can write for. Each carries a short style hint
# the AI uses to shape length, tone, and hashtag norms.
PLATFORMS = {
    "facebook": "Warm, neighborly, 2-4 short paragraphs. A few relevant hashtags at most.",
    "instagram": "Visual-first caption, punchy first line, 1-2 short lines, then 5-10 hashtags.",
    "google": "Google Business Profile post: concise, local-SEO friendly, include the service area and a clear call to action. No hashtags.",
    "linkedin": "Professional, credibility-focused (great for commercial/B2B work). 2-3 short paragraphs, minimal hashtags.",
}
DEFAULT_PLATFORM = "facebook"

# --- The Business Brain (default = "client zero", your own painting company) --
# This is the structured profile the Content Engine writes from. Edit it in
# Settings; these are just the seed values the database starts with.
DEFAULT_BUSINESS = {
    "name": "Heritage House Painting",
    "trade": "Residential & commercial painting",
    "service_area": "Greater metro area (30-mile radius)",
    "owner_name": "Jonathan",
    "brand_voice": (
        "Professional, clear, and courteous. Confident craftsmanship without bragging. "
        "Complete sentences, correct grammar, friendly but not casual. No slang, no "
        "filler, no emoji, and never use dashes (use periods and commas)."
    ),
    "services": (
        "Interior and exterior repaints, cabinet refinishing, trim and millwork, "
        "deck and fence staining, color consultation, light carpentry and prep."
    ),
    "target_customer": (
        "Homeowners in older and historic homes who care about a clean, durable, "
        "detail-oriented finish; plus property managers and general contractors for "
        "commercial repaints."
    ),
    "differentiators": (
        "Meticulous prep, on-time and tidy crews, written quotes after a free in-person "
        "estimate, and a workmanship guarantee. Locally owned."
    ),
    "capacity_note": (
        "Currently taking new estimates. Prefer higher-value full-exterior and cabinet "
        "jobs when the schedule is tight."
    ),
    "google_review_link": "",
    "mailing_address": "",
}
