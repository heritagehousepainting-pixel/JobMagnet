"""Database Reactivation engine -- win back past customers on their repaint cycle.

Found money: 5 to 6x cheaper than a new lead, and a list almost no contractor touches.
Pure cycle logic (no DB/Flask); customer job dates live in db. Only applies once a
shop is old enough to have customers coming due (the Mandate engine gates it).
"""
from datetime import datetime, timezone

# Years after a job until that service is typically due again. Lead-short for PA
# climate (snow/rain shorten exterior life). Grounded in MARKETING_PLAYBOOK.md cycles.
DUE_AFTER = {
    "interior": 3.0, "exterior": 5.0, "cabinets": 8.0,
    "deck": 2.0, "fence": 3.0, "commercial": 4.0,
}
DEFAULT_DUE = 4.0


def due_after_years(service):
    return DUE_AFTER.get((service or "").strip().lower(), DEFAULT_DUE)


def years_since(iso_date, now=None):
    """Years between a job date (ISO or YYYY-MM-DD) and now, or None if unparseable."""
    if not iso_date:
        return None
    d = None
    try:
        d = datetime.fromisoformat(iso_date)
    except (ValueError, TypeError):
        try:
            d = datetime.strptime(str(iso_date)[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)   # never mix naive + aware
    return (now - d).days / 365.25


def is_due(service, last_job_date, now=None):
    """True if this service is at/past its repaint window."""
    age = years_since(last_job_date, now)
    return age is not None and age >= due_after_years(service)


def reactivation_message(business, name="", service="", years=None):
    first = (name or "").split()[0] if (name or "").strip() else ""
    hi = f"Hi {first}, " if first else "Hi, "
    biz = business.get("name", "our team")
    svc = (service or "your project").strip().lower() or "your project"
    when = f"about {int(years)} years ago" if years and years >= 1 else "a while back"
    return (f"{hi}it's {biz}. We did your {svc} {when}, and around now is when a lot of "
            "homes are ready for a refresh. Want me to set up a free walkthrough? "
            "No pressure either way.")
