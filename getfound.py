"""Get Found engine -- GBP / local / AEO optimization (JobMagnet's #1 play for an
invisible shop).

"Claimed" is not "optimized." This is the structured best-practice checklist that
takes a dormant Google Business Profile to a working one, plus the weekly-post
cadence that signals freshness (the single fastest local-rank lever after reviews).

Pure logic only (no DB, no Flask): the checklist definition + scoring, so it's
trivially testable and the route just persists which items are done. Grounded in
MARKETING_PLAYBOOK.md (Get Found / AEO) and the local-SEO research (review velocity,
freshness, NAP, schema).
"""

# The optimization checklist, in roughly the order JobMagnet would walk an owner through.
CHECKLIST = [
    {"key": "claimed",     "label": "Google Business Profile claimed & verified",
     "help": "The foundation. An unverified profile barely ranks."},
    {"key": "category",    "label": "Primary category set correctly",
     "help": "The single biggest category-level ranking factor. Pick the most specific match."},
    {"key": "services",    "label": "All services listed",
     "help": "Each service is a chance to match a search. List them all."},
    {"key": "description", "label": "Full, keyword-rich business description",
     "help": "Use the space (up to ~750 chars). Say what you do and where, naturally."},
    {"key": "service_area","label": "Service area (towns / zips) set",
     "help": "Proximity drives local rank. Set the real towns you serve."},
    {"key": "hours",       "label": "Hours accurate (and holiday hours)",
     "help": "Wrong hours quietly kill trust and clicks."},
    {"key": "contact",     "label": "Phone, website & booking link added",
     "help": "Every path to contact you should be one tap away."},
    {"key": "photos",      "label": "10+ real project photos uploaded",
     "help": "Before/afters of real work. Profiles with photos get far more clicks."},
    {"key": "posts",       "label": "Posting weekly (fresh activity)",
     "help": "Freshness signals you're active. A weekly post is the cadence to hold."},
    {"key": "qa",          "label": "Q&A seeded / FAQ published",
     "help": "Answer-first content that doubles as AEO so AI engines can quote you."},
    {"key": "reviews",     "label": "Collecting & responding to reviews",
     "help": "The #1 controllable rank lever. Velocity and responses both count."},
    {"key": "nap",         "label": "Name/address/phone consistent across the web",
     "help": "Mismatched listings confuse Google and cost you rank."},
]
CHECKLIST_KEYS = {c["key"] for c in CHECKLIST}


def score(done):
    """Completion summary from the set/list of done item keys (unknown keys ignored)."""
    valid = {k for k in (done or []) if k in CHECKLIST_KEYS}
    total = len(CHECKLIST)
    n = len(valid)
    return {"done": n, "total": total,
            "pct": round(100 * n / total) if total else 0,
            "complete": n == total}


def next_steps(done, k=3):
    """The next few not-yet-done items -- what JobMagnet would tackle next."""
    done = {k2 for k2 in (done or []) if k2 in CHECKLIST_KEYS}
    return [c for c in CHECKLIST if c["key"] not in done][:k]
