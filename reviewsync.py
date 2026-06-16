"""Review pull seam (Phase 3).

JobMagnet monitors a tenant's public reviews so the heartbeat can ingest new ones,
draft a reply, and triage them WITHOUT the owner typing each review in by hand. The
real pull is a Google Business Profile connector: when the tenant connects GBP, this
module GETs their reviews and add_review()s the new ones.

That GET isn't implemented yet, so this seam is honest exactly like roi.sync_ringback:
when GBP is NOT connected we report 'simulated' (monitoring is dormant, nothing pulled);
when GBP IS connected we report 'pending' (configured, auto-pull not live yet) rather
than claiming a live sync that fabricated reviews. The heartbeat calls it per tenant so
monitoring is autonomous-ready the moment GBP is wired -- a safe no-op until then.
"""
import publishing


def gbp_connected(business_id):
    """Whether this tenant has a live Google Business Profile connection (the source
    we'd pull reviews from). Mirrors the publish-side liveness check so 'monitoring'
    and 'publishing' agree on what 'connected' means."""
    return publishing.gbp_live(business_id)


def pull_reviews(business_id):
    """Pull new reviews from a connected Google Business Profile into the reviews table.
    Safe no-op until GBP is connected. The actual reviews GET isn't implemented yet, so
    when GBP IS connected we honestly report 'pending' (configured, auto-pull not live)
    rather than claiming a live sync that ingested reviews. Never fabricates reviews."""
    if not gbp_connected(business_id):
        return {"mode": "simulated", "added": 0}
    # TODO: GET the GBP reviews API and add_review(... source='google') for each new
    # review, then draft + triage it the same way /reviews/import does. Until that's
    # built, do not claim a live pull.
    return {"mode": "pending", "added": 0}
