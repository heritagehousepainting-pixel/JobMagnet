"""Connections -- the contractor's real account links, per business.

This is what turns Mason from a logbook into an assistant with hands. Each tenant
connects their OWN accounts (their Twilio number, their Google profile, their Facebook
page); the messaging + publishing seams then read that tenant's connection and go LIVE
instead of simulating. No connection -> still a safe simulated/assisted no-op (the
honesty discipline), so nothing ever silently fails.

Pure registry + helpers only (no DB/Flask). Credentials are stored by db.py.
"""

# provider -> {label, kind, fields}. fields: (key, label) or (key, label, secret).
PROVIDERS = {
    "sms": {"label": "Texting (Twilio)", "kind": "keys", "blurb":
            "Sends review requests, reactivation, referrals and instant lead replies as real texts.",
            "fields": [("account_sid", "Account SID"), ("auth_token", "Auth Token", True),
                       ("from_number", "From number (+1...)")]},
    "email": {"label": "Email (SMTP)", "kind": "keys", "blurb":
              "Sends real review and partner-outreach emails.",
              "fields": [("from_addr", "From address"), ("smtp_host", "SMTP host"),
                         ("smtp_port", "SMTP port"), ("smtp_user", "Username"),
                         ("smtp_password", "Password", True)]},
    "gbp": {"label": "Google Business Profile", "kind": "oauth", "blurb":
            "Auto-posts to Google and pulls/responds to your reviews. Needs Google approval.",
            "fields": [("access_token", "Access token", True), ("location_id", "Location ID")]},
    "meta": {"label": "Facebook / Instagram", "kind": "oauth", "blurb":
             "Auto-posts to your Facebook Page (and Instagram once Meta approves the app).",
             "fields": [("page_id", "Facebook Page ID"), ("ig_user_id", "Instagram user ID"),
                        ("access_token", "Page access token", True)]},
    "calendar": {"label": "Calendar (Google)", "kind": "oauth", "blurb":
                 "Lets Mason book estimates straight onto your calendar.",
                 "fields": [("access_token", "Access token", True), ("calendar_id", "Calendar ID")]},
    "website": {"label": "Website", "kind": "keys", "blurb":
                "Your site address, so Mason can point links and embed schema there.",
                "fields": [("url", "Website URL")]},
}

# The fields that must be present for a connection to be considered live.
REQUIRED = {
    "sms": ["account_sid", "auth_token", "from_number"],
    "email": ["from_addr", "smtp_host"],
    "gbp": ["access_token"],
    "meta": ["access_token", "page_id"],
    "calendar": ["access_token"],
    "website": ["url"],
}


def field_specs(provider):
    """Normalized field list for the connect form: [{key,label,secret}]."""
    out = []
    for f in PROVIDERS.get(provider, {}).get("fields", []):
        out.append({"key": f[0], "label": f[1], "secret": len(f) > 2 and f[2]})
    return out


def is_ready(provider, creds):
    """True if the stored creds have everything needed to actually act."""
    creds = creds or {}
    return all(str(creds.get(k) or "").strip() for k in REQUIRED.get(provider, []))


def validate(provider, creds):
    """A light format check so an obviously-wrong value never shows as 'Connected'.
    Returns '' if fine, else a human hint. (Catches e.g. an email pasted into the
    Twilio SID field.)"""
    creds = creds or {}
    if provider == "sms":
        sid = str(creds.get("account_sid") or "").strip()
        frm = str(creds.get("from_number") or "").strip()
        if sid and not sid.startswith("AC"):
            return "Twilio Account SID should start with 'AC' (it's on your Twilio Console dashboard, not your email)."
        if frm and not frm.startswith("+"):
            return "The From number must be in +1XXXXXXXXXX format."
    if provider == "email":
        addr = str(creds.get("from_addr") or "")
        if addr and "@" not in addr:
            return "From address should be a valid email."
    if provider == "website":
        u = str(creds.get("url") or "")
        if u and not u.startswith("http"):
            return "Website URL should start with http:// or https://."
    return ""


def mask(value):
    """Show only the last 4 chars of a secret for display."""
    v = str(value or "")
    return ("****" + v[-4:]) if len(v) > 4 else ("****" if v else "")
