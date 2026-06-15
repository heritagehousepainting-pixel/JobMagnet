"""Closed-loop ROI helpers (Phase 3).

Cost-per-booked-job is JobMagnet's moat: only it sees marketing spend AND the booked
job. JobMagnet computes this from its OWN conversion data (manual mark-won, tracked
numbers, the booking webhook). RingBack is an OPTIONAL provider: when connected, it
feeds booked-job events automatically. Standalone first, RingBack pluggable.
"""
import db
from config import RINGBACK_API_URL, RINGBACK_API_KEY

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


def ringback_connected():
    return bool(RINGBACK_API_URL and RINGBACK_API_KEY)


def sync_ringback(business_id):
    """Pull booked jobs from a connected RingBack instance into conversions. Safe
    no-op (simulated) until RINGBACK_* is configured."""
    if not ringback_connected():
        return {"mode": "simulated", "added": 0}
    # A real implementation would GET RingBack's bookings API and add_conversion(...)
    # for each new booking with origin='ringback'. Not reached until configured.
    return {"mode": "live", "added": 0}
