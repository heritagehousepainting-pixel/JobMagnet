"""Public marketing, contact, and hosted legal pages."""

from datetime import datetime

from flask import Blueprint, abort, render_template, request

import plans
from auth import _EMAIL_RE
from config import BASE_DIR

bp = Blueprint("public", __name__)

# --- Per-IP rate limit for the public contact POST -------------------------
# The form is CSRF-protected but unauthenticated; without a limit one IP can spam
# contact_inbox.log. Simple in-process sliding window (per worker) — honest 429,
# no dependency. Good enough until real email delivery/a form service is wired.
_CONTACT_WINDOW_SEC = 3600
_CONTACT_MAX_PER_WINDOW = 5
_contact_hits = {}   # ip -> [timestamps]


def _contact_rate_limited(ip, now_ts):
    hits = [t for t in _contact_hits.get(ip, []) if now_ts - t < _CONTACT_WINDOW_SEC]
    limited = len(hits) >= _CONTACT_MAX_PER_WINDOW
    if not limited:
        hits.append(now_ts)
    _contact_hits[ip] = hits
    if len(_contact_hits) > 10000:   # bound memory: drop the stalest ips
        for stale in sorted(_contact_hits, key=lambda k: max(_contact_hits[k] or [0]))[:5000]:
            _contact_hits.pop(stale, None)
    return limited


def _site_ctx(**extra):
    """Shared context for the public marketing pages."""
    ctx = {"plans_data": plans.PLANS, "plan_order": plans.ORDER}
    ctx.update(extra)
    return ctx


@bp.route("/")
def index():
    # The public home is the front door. Logged-in visitors still see it; the nav
    # swaps to "Open JobMagnet" via the global template context.
    return render_template("site_home.html", **_site_ctx())


@bp.route("/pricing")
def pricing():
    return render_template("site_pricing.html", **_site_ctx())


@bp.route("/how-it-works")
def how_it_works():
    return render_template("site_how.html", **_site_ctx())


# Per-tenant hosted SMS compliance pages (A2P 10DLC privacy + terms).
LEGAL_UPDATED = "June 16, 2026"
LEGAL_BUSINESSES = {
    "heritage-house-painting": {
        "slug": "heritage-house-painting",
        "name": "Heritage House Painting",
        "phone": "(267) 756-2454",
        "email": "heritagehousepainting@gmail.com",
    },
}


@bp.route("/legal/<slug>/sms-privacy")
def legal_sms_privacy(slug):
    biz = LEGAL_BUSINESSES.get(slug)
    if not biz:
        abort(404)
    return render_template("legal.html", biz=biz, kind="privacy",
                           heading="SMS Privacy Policy", updated=LEGAL_UPDATED)


@bp.route("/legal/<slug>/sms-terms")
def legal_sms_terms(slug):
    biz = LEGAL_BUSINESSES.get(slug)
    if not biz:
        abort(404)
    return render_template("legal.html", biz=biz, kind="terms",
                           heading="SMS Terms & Conditions", updated=LEGAL_UPDATED)


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
              or request.remote_addr or "?")
        if _contact_rate_limited(ip, datetime.now().timestamp()):
            return (render_template("site_contact.html",
                                    error="Too many messages from this connection — "
                                          "please try again in an hour.",
                                    **_site_ctx()), 429)
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip()
        message = (request.form.get("message") or "").strip()
        if not name or not _EMAIL_RE.match(email) or not message:
            return render_template("site_contact.html",
                                   error="Add your name, a valid email, and a short message.",
                                   **_site_ctx())
        # No transactional email is wired yet, so record the inquiry honestly to a
        # local inbox file rather than pretending it was emailed. (See SETUP_NEEDED.)
        try:
            trade = (request.form.get("trade") or "").strip()
            with open(BASE_DIR / "contact_inbox.log", "a", encoding="utf-8") as fh:
                fh.write(f"{datetime.now().isoformat()}\t{name}\t{email}\t{trade}\t"
                         f"{message.replace(chr(9), ' ').replace(chr(10), ' ')}\n")
        except OSError:
            pass
        return render_template("site_contact.html", sent=True, **_site_ctx())
    return render_template("site_contact.html", **_site_ctx())
