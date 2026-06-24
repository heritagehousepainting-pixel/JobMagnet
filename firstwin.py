"""First-win activation -- the single designated win Mason guides a new tenant toward.

Pure decision + copy (no I/O), mirroring mandate.py/getfound.py. The app supplies the
tenant's signals + live integration state to designate(), and the real-outcome facts to
achieved(); db.py does the I/O. Real-outcome only: a simulated send/post never counts.
"""

# Canonical win ids + UI metadata.
WINS = {
    "review_request": {"label": "Send your first review request", "cta_route": "/reviews",
                       "nudge": "Asking a recent happy customer for a review is the fastest local-SEO win."},
    "gbp_post":       {"label": "Publish your first Google post", "cta_route": "/getfound",
                       "nudge": "A fresh Google Business post keeps you visible in local search."},
    "reactivation":   {"label": "Win back a past customer", "cta_route": "/reactivation",
                       "nudge": "A friendly check-in to a past customer often books the next job."},
    "aeo_faq":        {"label": "Generate your AI-search FAQ + schema", "cta_route": "/local",
                       "nudge": "Answer-first FAQ + schema is real, paste-ready value AI search engines cite -- no account needed."},
}


def designate(signals, live_state):
    """The single win to guide this tenant toward. live_state: {sms_live, gbp_connected}.
    Always returns a reachable win (falls back to 'aeo_faq', which needs no integration)."""
    sms = bool(live_state.get("sms_live"))
    gbp = bool(live_state.get("gbp_connected"))
    s = signals or {}
    if sms and (s.get("reviewable_backlog") or 0) > 0:
        return "review_request"
    if gbp:
        return "gbp_post"
    if sms and (s.get("past_customers") or 0) > 0:
        return "reactivation"
    return "aeo_faq"


# Real-outcome fact key -> the win it satisfies (order = which wins first if several true).
_FACT_WIN = (("review_sent", "review_request"), ("gbp_live_post", "gbp_post"),
             ("reactivation_sent", "reactivation"), ("faq_generated", "aeo_faq"),
             ("firstback_booking", "firstback_booking"))


def achieved(facts):
    """Id of the first qualifying REAL outcome the tenant has, else None."""
    for key, win in _FACT_WIN:
        if facts.get(key):
            return win
    return None


def nudge_copy(win_id, days_since_signup):
    """Soft, day-aware nudge. No lockout/penalty language."""
    base = WINS.get(win_id, {}).get("nudge", "")
    d = days_since_signup or 0
    if d <= 1:
        lead = "Welcome -- here's your first win to aim for this week."
    elif d <= 4:
        lead = "Still here to help you land your first win."
    else:
        lead = "Let's get your first win before the week's out."
    return f"{lead} {base}".strip()
