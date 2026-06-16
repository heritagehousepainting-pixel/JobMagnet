"""JobMagnet's outbound spine (Phase 0).

ONE gated path for every SMS/email the product sends, so consent, quiet hours, and
the simulated-vs-live decision live in a single auditable place. Mirrors RingBack's
discipline: every send is a SAFE NO-OP (simulated, logged) until a real provider is
configured, and consent is checked before anything leaves.

Provider interface (standalone first, RingBack/Twilio pluggable):
  SMS   -> Twilio when TWILIO_* configured, else "simulated"
  Email -> SMTP when SMTP_* configured, else "simulated"

Every send returns a result dict and is written to the `messages` log:
  {"status": "...", "provider": "...", "message_id": <int>}
  status in: sent | simulated | blocked_optout | blocked_quiet | blocked_cap |
             blocked_no_consent | error
(blocked_cap = the tenant hit today's pacing cap or the monthly plan ceiling; the send
 waits and a later run continues it, so blasts drip instead of dumping.)
"""
from datetime import datetime

import db
import plans
import connections
from config import (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM,
                    EMAIL_FROM, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
                    QUIET_HOURS_START, QUIET_HOURS_END,
                    COLD_SMS_ENABLED, COLD_VOICE_ENABLED)

# Inbound keywords that toggle consent (carrier convention).
STOP_WORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "optout", "opt-out"}
START_WORDS = {"start", "unstop", "yes", "optin", "opt-in"}


# ---- Provider credentials (per-tenant connection first, then global env) ----
def _sms_creds(business_id=None):
    """The Twilio creds that will actually be used: the tenant's own connection if
    they've linked one, else the global env (dev), else None (=> simulated)."""
    c = db.get_connection(business_id, "sms") if business_id else None
    if c and connections.is_ready("sms", c):
        return c
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM:
        return {"account_sid": TWILIO_ACCOUNT_SID, "auth_token": TWILIO_AUTH_TOKEN,
                "from_number": TWILIO_FROM}
    return None


def _email_creds(business_id=None):
    c = db.get_connection(business_id, "email") if business_id else None
    if c and connections.is_ready("email", c):
        return c
    if EMAIL_FROM and SMTP_HOST:
        return {"from_addr": EMAIL_FROM, "smtp_host": SMTP_HOST, "smtp_port": SMTP_PORT,
                "smtp_user": SMTP_USER, "smtp_password": SMTP_PASSWORD}
    return None


# ---- Provider availability (is the channel live or simulated?) ----
def sms_live(business_id=None):
    return bool(_sms_creds(business_id))


def email_live(business_id=None):
    return bool(_email_creds(business_id))


def channel_status(business_id=None):
    """For the UI: honest 'live' vs 'simulated' per channel, for THIS tenant."""
    return {"sms": "live" if sms_live(business_id) else "simulated",
            "email": "live" if email_live(business_id) else "simulated"}


# ---- Policy checks ----
def in_quiet_hours(now=None):
    """True if `now` (local) falls inside the no-send window. Handles a window that
    wraps midnight (e.g. 21->8)."""
    now = now or datetime.now()
    h = now.hour
    start, end = QUIET_HOURS_START, QUIET_HOURS_END
    if start == end:
        return False
    if start < end:
        return start <= h < end
    return h >= start or h < end          # wraps midnight


def cap_status(business_id):
    """How much outbound SMS headroom this tenant has, given their plan: today's daily
    pacing cap and the monthly plan ceiling. Surfaced honestly in the UI and enforced by
    the gate below, so a blast drips over days instead of dumping (carrier hygiene)."""
    plan = db.get_plan(business_id)
    day_used, month_used = db.messages_today(business_id), db.messages_this_month(business_id)
    day_cap, month_cap = plans.daily_cap(plan), plans.text_cap(plan)
    return {"day_used": day_used, "day_cap": day_cap, "day_left": max(0, day_cap - day_used),
            "month_used": month_used, "month_cap": month_cap,
            "month_left": max(0, month_cap - month_used)}


def _over_cap(business_id):
    """'month' / 'day' if the tenant has hit a cap and the send must wait, else None."""
    s = cap_status(business_id)
    if s["month_left"] <= 0:
        return "month"
    if s["day_left"] <= 0:
        return "day"
    return None


def consent_ok(contact, kind):
    """(ok, reason). Opt-out and DNC suppression always block. Marketing to a stranger
    (no contact on file, or consent unknown) is allowed in this phase but flagged; cold
    channels (Phase 5/6) tighten this to require explicit 'granted'. Transactional
    (e.g. a review request to your own customer) only needs 'not blocked'."""
    if contact and contact.get("suppressed"):
        return False, "blocked_optout"
    if contact and contact.get("consent_status") == "opted_out":
        return False, "blocked_optout"
    return True, "ok"


# ---- Real providers (lazy imports; only hit when a connection exists) ----
def _twilio_send(creds, to, body):
    import requests
    sid = creds["account_sid"]
    resp = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, creds["auth_token"]),
        data={"From": creds["from_number"], "To": to, "Body": body}, timeout=20)
    resp.raise_for_status()
    return resp.json().get("sid", "")


def _smtp_send(creds, to, subject, body):
    import smtplib
    from email.mime.text import MIMEText
    msg = MIMEText(body)
    msg["Subject"], msg["From"], msg["To"] = subject, creds["from_addr"], to
    port = int(creds.get("smtp_port") or 587)
    with smtplib.SMTP(creds["smtp_host"], port, timeout=20) as s:
        s.starttls()
        if creds.get("smtp_user"):
            s.login(creds["smtp_user"], creds.get("smtp_password") or "")
        s.sendmail(creds["from_addr"], [to], msg.as_string())
    return "sent"


# ---- The one gated send path ----
def send_sms(business_id, to, body, kind="marketing", purpose="",
             contact=None, now=None):
    """Send (or simulate) an SMS through the consent + quiet-hours gate, logging
    every outcome. `kind` is 'marketing' or 'transactional'."""
    if contact is None:
        contact = db.find_contact_by_phone(business_id, to)
    cid = contact["id"] if contact else None

    ok, reason = consent_ok(contact, kind)
    if not ok:
        return _logged(business_id, "sms", to, body, reason, "blocked",
                       kind, purpose, cid)
    if kind == "marketing" and in_quiet_hours(now):
        return _logged(business_id, "sms", to, body, "blocked_quiet", "blocked",
                       kind, purpose, cid)
    # Pacing: hold the send when the tenant has hit today's daily cap or the monthly plan
    # ceiling. blocked_cap is NOT counted as contacted (see db.contacted_ids), so the next
    # run picks this contact up -- a big blast drips over days instead of dumping.
    if _over_cap(business_id):
        return _logged(business_id, "sms", to, body, "blocked_cap", "blocked",
                       kind, purpose, cid)

    creds = _sms_creds(business_id)
    if creds:
        try:
            _twilio_send(creds, to, body)
            return _logged(business_id, "sms", to, body, "sent", "twilio",
                           kind, purpose, cid)
        except Exception as e:
            print(f"[jobmagnet] twilio send failed: {e}", flush=True)
            return _logged(business_id, "sms", to, body, "error", "twilio",
                           kind, purpose, cid)
    return _logged(business_id, "sms", to, body, "simulated", "simulated",
                   kind, purpose, cid)


def send_email(business_id, to, subject, body, kind="marketing", purpose="",
               contact=None):
    # The caller passes `contact` when known (so consent + logging are scoped to it);
    # email-keyed lookup of an unknown contact is a later refinement.
    cid = contact["id"] if contact else None
    ok, reason = consent_ok(contact, kind)
    if not ok:
        return _logged(business_id, "email", to, body, reason, "blocked",
                       kind, purpose, cid)
    creds = _email_creds(business_id)
    if creds:
        try:
            _smtp_send(creds, to, subject, body)
            return _logged(business_id, "email", to, body, "sent", "smtp",
                           kind, purpose, cid)
        except Exception as e:
            print(f"[jobmagnet] smtp send failed: {e}", flush=True)
            return _logged(business_id, "email", to, body, "error", "smtp",
                           kind, purpose, cid)
    return _logged(business_id, "email", to, body, "simulated", "simulated",
                   kind, purpose, cid)


def _logged(business_id, channel, to, body, status, provider, kind, purpose, cid):
    mid = db.log_message(business_id, channel, to, body, status, provider,
                         kind=kind, purpose=purpose, contact_id=cid)
    return {"status": status, "provider": provider, "message_id": mid}


# ---- Cold phone channels (Phase 6): hard-gated ----
def cold_sms_enabled():
    return bool(COLD_SMS_ENABLED)


def cold_voice_enabled():
    return bool(COLD_VOICE_ENABLED)


def send_cold_sms(business_id, to, body, contact=None, now=None):
    """Cold marketing SMS to a NON-customer. Triple-gated:
      1. the channel must be enabled (off until a TCPA attorney signs off),
      2. the contact must have prior express WRITTEN consent on file (granted),
      3. plus the normal not-suppressed / quiet-hours / provider gate.
    Returns blocked_disabled or blocked_no_consent rather than sending when unsafe."""
    if not COLD_SMS_ENABLED:
        return _logged(business_id, "sms", to, body, "blocked_disabled", "blocked",
                       "marketing", "cold_sms", contact["id"] if contact else None)
    if contact is None:
        contact = db.find_contact_by_phone(business_id, to)
    if (not contact or contact.get("suppressed")
            or contact.get("consent_status") != "granted"):
        return _logged(business_id, "sms", to, body, "blocked_no_consent", "blocked",
                       "marketing", "cold_sms", contact["id"] if contact else None)
    return send_sms(business_id, to, body, kind="marketing", purpose="cold_sms",
                    contact=contact, now=now)


def place_cold_voice(business_id, to, script, contact=None):
    """Cold AI voice -- the highest legal risk (FCC: AI voice = artificial/
    prerecorded). Disabled by default and, even when enabled, requires written
    consent. We never auto-dial without an explicit affirmative record."""
    cid = contact["id"] if contact else None
    if not COLD_VOICE_ENABLED:
        return _logged(business_id, "voice", to, script, "blocked_disabled", "blocked",
                       "marketing", "cold_voice", cid)
    if not contact or contact.get("suppressed") or contact.get("consent_status") != "granted":
        return _logged(business_id, "voice", to, script, "blocked_no_consent", "blocked",
                       "marketing", "cold_voice", cid)
    # A real dialer would be invoked here once a connector is configured + reviewed.
    return _logged(business_id, "voice", to, script, "simulated", "simulated",
                   "marketing", "cold_voice", cid)


# ---- Inbound (opt-out / opt-in handling) ----
def handle_inbound_sms(business_id, from_phone, text):
    """Process an inbound SMS reply: honour STOP/START so the consent ledger always
    reflects the contact's wishes. Returns the action taken."""
    word = (text or "").strip().lower().split()
    first = word[0] if word else ""
    contact = db.find_contact_by_phone(business_id, from_phone)
    db.log_message(business_id, "sms", from_phone, text or "", "received",
                   "inbound", kind="transactional", purpose="inbound",
                   contact_id=(contact["id"] if contact else None),
                   direction="inbound")
    if not contact:
        return "ignored_unknown"
    if first in STOP_WORDS:
        db.set_contact_consent(business_id, contact["id"], "sms", "opted_out",
                               source="inbound STOP")
        return "opted_out"
    if first in START_WORDS:
        db.set_contact_consent(business_id, contact["id"], "sms", "granted",
                               source="inbound START")
        return "opted_in"
    return "no_action"
