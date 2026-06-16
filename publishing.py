"""JobMagnet's publishing seam (Phase 2).

One honest path to "publish" a post per platform. It reads the TENANT's connection
(Connections hub) and goes live when linked, else falls back to global env, else a safe
no-op:

  google (GBP)   -> "live" when the tenant connected Google (or GBP_ACCESS_TOKEN set)
  facebook       -> "live" when the tenant connected Meta (Facebook Page)
  instagram      -> "assisted" (auto-post needs Meta's image pipeline + app review)
  linkedin       -> "assisted" (no connector)

"Assisted" = we hand the owner finished copy to paste, which is real value while the
platform APIs are pending. We never pretend an unconnected channel auto-posted.
"""
import db
import connections
from config import GBP_ACCESS_TOKEN, META_ACCESS_TOKEN

ASSISTED_PLATFORMS = {"facebook", "instagram", "linkedin"}


def gbp_live(business_id=None):
    if business_id and db.get_connection(business_id, "gbp"):
        return True
    return bool(GBP_ACCESS_TOKEN)


def meta_live(business_id=None):
    if business_id and db.get_connection(business_id, "meta"):
        return True
    return bool(META_ACCESS_TOKEN)


def platform_mode(platform, business_id=None):
    """How a post on this platform will actually go out for this tenant right now."""
    if platform == "google":
        return "live" if gbp_live(business_id) else "simulated"
    if platform == "facebook":
        return "live" if meta_live(business_id) else "assisted"
    if platform in ("instagram", "linkedin"):
        return "assisted"        # auto-post not supported yet (honest)
    return "simulated"


def publishing_status(business_id=None):
    """For the UI: mode per known platform, for this tenant."""
    return {p: platform_mode(p, business_id) for p in ("facebook", "instagram", "google", "linkedin")}


# ---- Real providers (lazy imports; only hit when a connection exists) ----
def _gbp_post(creds, post):
    import requests
    location = creds.get("location_id", "")
    resp = requests.post(
        f"https://mybusiness.googleapis.com/v4/{location}/localPosts",
        headers={"Authorization": f"Bearer {creds.get('access_token','')}"},
        json={"languageCode": "en-US", "summary": post.get("body", ""),
              "topicType": "STANDARD"}, timeout=20)
    resp.raise_for_status()
    return True


def _meta_post(creds, post):
    import requests
    page = creds.get("page_id", "")
    resp = requests.post(
        f"https://graph.facebook.com/v19.0/{page}/feed",
        data={"message": post.get("body", ""), "access_token": creds.get("access_token", "")},
        timeout=20)
    resp.raise_for_status()
    return True


def publish_post(business_id, post):
    """Publish (or simulate/assist) a post and mark it published. Returns the mode so the
    UI can be honest about what happened. A live connection actually calls the platform;
    a failure is reported as 'error' (never a silent fake success)."""
    platform = post["platform"]
    mode = platform_mode(platform, business_id)
    if mode == "live":
        try:
            if platform == "google":
                _gbp_post(db.get_connection(business_id, "gbp") or {}, post)
            elif platform == "facebook":
                _meta_post(db.get_connection(business_id, "meta") or {}, post)
        except Exception as e:
            print(f"[jobmagnet] {platform} publish failed: {e}", flush=True)
            mode = "error"
    if mode == "error":
        # A real publish was attempted and failed -- never fake success. Leave the post
        # in the queue (still 'approved'/'scheduled') so the owner can retry.
        return {"mode": "error", "platform": platform}
    # Record HOW it went out so the dashboard shows an honest status: only a real
    # live post is "Published"; assisted = copy ready to paste, simulated = marked.
    db.set_post_published(post["id"], business_id, mode)
    return {"mode": mode, "platform": platform}
