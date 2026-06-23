"""Closed-loop ROI helpers (Phase 3).

Cost-per-booked-job is JobMagnet's moat: only it sees marketing spend AND the booked
job. JobMagnet computes this from its OWN conversion data (manual mark-won, tracked
numbers, the booking webhook). FirstBack is an OPTIONAL provider: when connected, it
feeds booked-job events automatically. Standalone first, FirstBack pluggable.
"""
import db
from config import FIRSTBACK_API_URL, FIRSTBACK_API_KEY

# The marketing channels we attribute spend and bookings to.
CHANNELS = [
    "social", "google_lsa", "google_ads", "facebook_ads", "local_seo",
    "reviews", "email", "referral", "other",
]

CHANNEL_LABELS = {
    "social": "Social content", "google_lsa": "Local Services Ads",
    "google_ads": "Google Search Ads", "facebook_ads": "Facebook/Instagram Ads",
    "local_seo": "Local SEO / GBP", "reviews": "Reviews", "email": "Email",
    "referral": "Referral / word of mouth", "other": "Other",
}


def firstback_connected():
    return bool(FIRSTBACK_API_URL and FIRSTBACK_API_KEY)


def _fetch_firstback_bookings(business_id):
    """GET booked jobs from the connected FirstBack instance. Returns a list of booking
    dicts (FirstBack's shape). Factored out so the suite can stub the HTTP call. Lazily
    imports requests (only hit when a connection exists), mirroring publishing/messaging.

    The exact bookings GET shape must be matched to FirstBack's real API; the parsing in
    sync_firstback reads conservatively (id, channel, value, label) with safe defaults."""
    import requests  # lazy: only when FirstBack is actually configured
    resp = requests.get(
        FIRSTBACK_API_URL.rstrip("/") + "/bookings",
        headers={"Authorization": f"Bearer {FIRSTBACK_API_KEY}"},
        params={"business_id": business_id},
        timeout=20)
    resp.raise_for_status()
    data = resp.json()
    # Accept either a bare list or a {"bookings": [...]} envelope.
    if isinstance(data, dict):
        data = data.get("bookings") or data.get("data") or []
    return data if isinstance(data, list) else []


def sync_firstback(business_id):
    """Pull booked jobs from a connected FirstBack instance into conversions.

    Honest modes:
      - not connected -> {"mode": "simulated", "added": 0} (safe no-op)
      - connected     -> actually GET the bookings and add_conversion(... origin='firstback')
                         for each NEW booking (deduped by ext_id so re-syncing never
                         double-counts). Returns {"mode": "live", "added": n} (n may be 0).
      - request error -> {"mode": "error", "added": 0} (never a faked success)
    """
    if not firstback_connected():
        return {"mode": "simulated", "added": 0}
    try:
        bookings = _fetch_firstback_bookings(business_id)
    except Exception as e:
        print(f"[jobmagnet] firstback sync failed for business {business_id}: {e}", flush=True)
        return {"mode": "error", "added": 0}
    added = 0
    for b in bookings:
        if not isinstance(b, dict):
            continue
        ext_id = b.get("id") or b.get("booking_id") or b.get("ext_id")
        if ext_id is None:
            continue                       # no stable id -> can't dedup -> skip honestly
        ext_id = str(ext_id)
        if db.conversion_exists(business_id, "firstback", ext_id):
            continue                       # already pulled this booking; no double-count
        channel = b.get("channel") or "other"
        if channel not in CHANNELS:
            channel = "other"
        try:
            value = float(b.get("value") or 0)
        except (TypeError, ValueError):
            value = 0
        label = (b.get("label") or b.get("customer") or b.get("name") or "").strip()
        db.add_conversion(business_id, channel, status="booked", value=value,
                          label=label, origin="firstback", ext_id=ext_id)
        added += 1
    return {"mode": "live", "added": added}
