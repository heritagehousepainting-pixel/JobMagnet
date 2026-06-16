"""One-click "Connect with Google" OAuth for Google Business Profile, per tenant.

This is what lets a contractor link their Google profile with a single button instead of
pasting an access token by hand. It mirrors the proven web-server OAuth flow from the
sibling product RingBack (google_cal.py):

  configured()                      -> True once the app has Google CLIENT_ID/SECRET
  is_connected(business_id)         -> True once THIS tenant has linked their account
  auth_url(state)                   -> the Google consent URL to redirect the owner to
  connect_with_code(business_id, …) -> exchange the callback code for tokens + store them
  access_token(business_id)         -> a valid token, refreshing on demand
  disconnect(business_id)           -> forget the tenant's tokens

Honesty discipline (same as every other seam): with no CLIENT_ID/SECRET set, every entry
point is a safe no-op -- the Connect button is disabled and nothing ever reads "Connected".

Storage: tokens live in the existing per-tenant `connections` table under provider "gbp"
({access_token, refresh_token, token_expiry, location_id}), sealed at rest by crypto.py via
db.set_connection. No new table; publishing.gbp_live already goes live off that row.

Dependency-light: `requests` only (no Google SDK). The three network calls are isolated in
small helpers (_exchange_code / _refresh / _fetch_location_id) so tests can stub them.
"""
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import db
from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
# Manage the business's posts/locations (publish localPosts, read locations).
SCOPE = "https://www.googleapis.com/auth/business.manage"
# Account/location lookup endpoints (Business Profile APIs) used to resolve the location
# resource name the v4 localPosts publish call needs ("accounts/X/locations/Y").
ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
_PROVIDER = "gbp"
_SKEW = timedelta(seconds=60)   # refresh slightly early so a token never expires mid-call


def configured():
    """True if the app has Google OAuth credentials at all (else everything no-ops)."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def is_connected(business_id):
    """True if this tenant has linked a Google account (a stored access token exists)."""
    creds = db.get_connection(business_id, _PROVIDER) or {}
    return bool(creds.get("access_token"))


# ---- OAuth flow ----------------------------------------------------------
def auth_url(state):
    """The Google consent URL to redirect the contractor to. `state` is the CSRF guard
    we verify on the callback. We ask for offline access + prompt=consent so Google
    returns a refresh token we can mint future access tokens from."""
    return AUTH_URL + "?" + urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",     # ask for a refresh token
        "prompt": "consent",          # ensure a refresh token is returned
        "include_granted_scopes": "true",
        "state": state,
    })


def connect_with_code(business_id, code):
    """Exchange an auth code for tokens and store them for the tenant, then resolve and
    store the GBP location id the publish call needs. Returns True if an access token was
    obtained. Raises on a hard HTTP failure (the route turns that into an honest error)."""
    tok = _exchange_code(code)
    access = tok.get("access_token") or ""
    refresh = tok.get("refresh_token") or ""
    location_id = _fetch_location_id(access) if access else ""
    db.set_connection(business_id, _PROVIDER, {
        "access_token": access,
        "refresh_token": refresh,
        "token_expiry": _expiry_iso(tok),
        "location_id": location_id or "",
    })
    return bool(access)


def disconnect(business_id):
    """Forget this tenant's Google tokens (publishing.gbp_live flips back to simulated)."""
    db.disconnect(business_id, _PROVIDER)


def access_token(business_id):
    """A valid access token for the tenant, refreshing if expired. None if the tenant is
    not connected or a refresh fails (honest -- never returns a token we can't trust)."""
    creds = db.get_connection(business_id, _PROVIDER) or {}
    access = creds.get("access_token")
    if not access:
        return None
    if not _is_expired(creds.get("token_expiry")):
        return access
    # Expired (or unparseable expiry). Refresh if we can; Google omits the refresh token
    # on a refresh response, so we keep the stored one.
    refresh = creds.get("refresh_token")
    if not refresh:
        return access                 # can't refresh (e.g. legacy paste) -> best effort
    try:
        tok = _refresh(refresh)
    except Exception as e:            # noqa: BLE001 -- never break a publish on a refresh blip
        print(f"[jobmagnet] google token refresh failed (biz {business_id}): {e}",
              file=sys.stderr, flush=True)
        return None
    new_access = tok.get("access_token")
    if not new_access:
        return None
    db.set_connection(business_id, _PROVIDER, {
        "access_token": new_access,
        "refresh_token": tok.get("refresh_token") or refresh,   # keep the stored one
        "token_expiry": _expiry_iso(tok),
        "location_id": creds.get("location_id", ""),
    })
    return new_access


# ---- internals (network isolated here so tests can stub them) ------------
def _expiry_iso(tok):
    secs = int(tok.get("expires_in", 3600) or 3600)
    return (datetime.now(timezone.utc) + timedelta(seconds=secs)).isoformat()


def _is_expired(expiry_iso):
    """True if the stored expiry is in the past (minus a small skew). An absent or
    unparseable expiry is treated as expired so we refresh rather than send a stale token."""
    if not expiry_iso:
        return True
    try:
        exp = datetime.fromisoformat(expiry_iso)
    except (ValueError, TypeError):
        return True
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp <= datetime.now(timezone.utc) + _SKEW


def _exchange_code(code):
    """POST the auth code to Google's token endpoint -> token dict."""
    import requests
    r = requests.post(TOKEN_URL, data={
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=30)
    r.raise_for_status()
    return r.json()


def _refresh(refresh_token):
    """Mint a fresh access token from a stored refresh token -> token dict."""
    import requests
    r = requests.post(TOKEN_URL, data={
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }, timeout=30)
    r.raise_for_status()
    return r.json()


def _fetch_location_id(access_token_str):
    """Best-effort resolve the tenant's first GBP location resource name
    ("accounts/X/locations/Y") that the v4 localPosts publish call needs. Returns "" on any
    error -- the owner can still finish connecting; a missing location just means the
    publish call will surface its own error later rather than silently faking success."""
    import requests
    headers = {"Authorization": f"Bearer {access_token_str}"}
    try:
        ar = requests.get(ACCOUNTS_URL, headers=headers, timeout=20)
        ar.raise_for_status()
        accounts = ar.json().get("accounts", [])
        if not accounts:
            return ""
        account = accounts[0].get("name", "")   # "accounts/123"
        if not account:
            return ""
        lr = requests.get(
            f"https://mybusinessbusinessinformation.googleapis.com/v1/{account}/locations",
            headers=headers, params={"readMask": "name"}, timeout=20)
        lr.raise_for_status()
        locations = lr.json().get("locations", [])
        if not locations:
            return ""
        loc = locations[0].get("name", "")      # "locations/456"
        if not loc:
            return ""
        # v4 localPosts wants the combined "accounts/X/locations/Y" resource name.
        return f"{account}/{loc}" if loc.startswith("locations/") else f"{account}/locations/{loc}"
    except Exception as e:                       # noqa: BLE001
        print(f"[jobmagnet] google location lookup failed: {e}", file=sys.stderr, flush=True)
        return ""
