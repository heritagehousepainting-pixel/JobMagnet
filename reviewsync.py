"""Review pull seam (Phase 3).

JobMagnet monitors a tenant's public reviews so the heartbeat can ingest new ones,
draft a reply, and triage them WITHOUT the owner typing each review in by hand. The
real pull is a Google Business Profile connector: when the tenant connects GBP, this
module GETs their reviews and add_review()s the new ones (deduped via gbp_review_id).

When GBP is NOT connected we report 'simulated' (monitoring is dormant, nothing pulled).
When GBP IS connected we attempt the live GBP Reviews API GET; any error (expired token,
network failure) returns 'error' rather than fabricating reviews. The heartbeat calls it
per tenant so monitoring is autonomous-ready the moment GBP is wired.

OPS NOTE: The GBP Reviews API (mybusiness.googleapis.com/v4) requires:
  - A valid OAuth2 access_token stored in the GBP connection credentials
  - The account_id and location_id stored in the connection credentials
  - The Business Profile API enabled in the Google Cloud project
  These must be set up via the Google Cloud console and the /connections/google flow.
"""
import publishing


def gbp_connected(business_id):
    """Whether this tenant has a live Google Business Profile connection (the source
    we'd pull reviews from). Mirrors the publish-side liveness check so 'monitoring'
    and 'publishing' agree on what 'connected' means."""
    return publishing.gbp_live(business_id)


def pull_reviews(business_id):
    """Pull new reviews from a connected Google Business Profile into the reviews table.
    Safe no-op until GBP is connected. When connected, attempts a live GBP Reviews GET
    and inserts any new reviews (deduped via gbp_review_id). Never fabricates reviews.

    Returns {'mode': str, 'added': int} where mode is one of:
      'simulated' -- GBP not connected; nothing pulled
      'live'      -- GBP connected; added N new reviews (0 is fine, means already up-to-date)
      'pending'   -- GBP connected but credentials incomplete (missing account/location ids)
      'error'     -- GBP connected but the API call failed (token expired, network, etc.)
    """
    if not gbp_connected(business_id):
        return {"mode": "simulated", "added": 0}

    try:
        import db
        import urllib.request
        import json as _json

        conn_creds = db.get_connection(business_id, "gbp")
        if not conn_creds:
            return {"mode": "pending", "added": 0}

        creds = conn_creds if isinstance(conn_creds, dict) else {}
        access_token = creds.get("access_token", "")
        account_id = creds.get("account_id", "")
        location_id = creds.get("location_id", "")

        if not (access_token and account_id and location_id):
            return {"mode": "pending", "added": 0}

        url = (f"https://mybusiness.googleapis.com/v4/accounts/{account_id}"
               f"/locations/{location_id}/reviews")
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {access_token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode())

        added = 0
        for review in data.get("reviews", []):
            gbp_id = review.get("reviewId", "")
            if not gbp_id:
                continue
            if db.review_exists_by_gbp_id(business_id, gbp_id):
                continue
            rating_map = {
                "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5
            }
            star_str = review.get("starRating", "")
            rating = rating_map.get(star_str, 0) or int(float(star_str or 0))
            author = review.get("reviewer", {}).get("displayName", "")
            body = review.get("comment", "")
            db.add_review(business_id, source="google", author=author,
                          rating=rating, body=body, gbp_review_id=gbp_id)
            added += 1

        return {"mode": "live", "added": added}

    except Exception:
        return {"mode": "error", "added": 0}
