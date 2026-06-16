"""Cadence -- how often a content play may draft, so a frequent heartbeat doesn't spam.

Pure pacing logic (no DB, no Flask): per content play a window in days, and a single
`due()` check the autopilot runner calls before drafting. The heartbeat can fire every
~15 min; cadence is what keeps it from piling up a fresh draft on every tick. It does NOT
change where content lands (still a draft awaiting approval) -- that stays Phase 2's job.

Robust ISO-date parsing mirrors reactivation.years_since (tz-aware, never mixes naive +
aware): a missing or unparseable-old last-post reads as "due now," so a tenant with no
history is never starved of its first draft.
"""
from datetime import datetime, timezone, timedelta

# How many days to wait between drafts of a play's content. GBP/Google posts hold a weekly
# freshness cadence (the local-rank lever); showcase posts run a touch more often. Grounded
# in MARKETING_PLAYBOOK.md (weekly post freshness).
WINDOW_DAYS = {
    "google":    7,    # get_found  -> roughly weekly
    "instagram": 4,    # show_work  -> a few days
}

# Per-playbook lookup so callers don't hardcode the window: (platform, window_days).
CADENCE = {
    "get_found": ("google",    WINDOW_DAYS["google"]),
    "show_work": ("instagram", WINDOW_DAYS["instagram"]),
}


def due(last_created_iso, window_days, now=None):
    """True if a new draft is allowed now: when there is no parseable last-post date, or the
    last post is older than `window_days`. Falsy / unparseable input reads as due."""
    if not last_created_iso:
        return True
    d = None
    try:
        d = datetime.fromisoformat(last_created_iso)
    except (ValueError, TypeError):
        try:
            d = datetime.strptime(str(last_created_iso)[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return True    # unparseable -> treat as old, don't block the draft
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)   # never mix naive + aware
    return (now - d) >= timedelta(days=window_days)
