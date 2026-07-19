"""Autopilot -- the wire between the Mandate's elections and the engines.

This is what makes "Take it over / Ask me first / Not yet" mean something:
  take_over -> JobMagnet runs the play's safe autonomous action on an autopilot run
  ask_first -> JobMagnet leaves it for you (you act on the engine's page / approval queue)
  off/not_yet -> skipped

Pure planning only (what WOULD run); the route executes the plan through the same
consent-gated seam + approval queue every manual action uses, so autonomy never escapes
the guardrails. Owned/warm actions only -- regulated/cold sends stay gated elsewhere.
"""

# Playbooks that have a safe autonomous action, and the human-readable description.
AUTONOMOUS_ACTIONS = {
    "get_found":    "Draft this week's Google post",
    "show_work":    "Draft a project showcase post",
    "reviews":      "Text review requests to customers not yet asked",
    "reactivation": "Text past customers who are due on their cycle",
    "referrals":    "Ask happy customers for a referral",
    "radius_mail":  "Draft a neighbor mail campaign for each completed job",
}


def plan(elections):
    """elections: {playbook: election}. Returns the autopilot plan -- for each playbook
    with an autonomous action, what JobMagnet will do on a run:
      status 'run' (take_over) | 'ask' (ask_first, left for you) | 'off'."""
    out = []
    for pb, action in AUTONOMOUS_ACTIONS.items():
        el = elections.get(pb) or "off"
        status = "run" if el == "take_over" else ("ask" if el == "ask_first" else "off")
        out.append({"playbook": pb, "action": action, "election": el, "status": status})
    return out


def summary(plan_rows):
    """Counts for the UI: how many plays are on autopilot vs ask-first vs off."""
    return {"run": sum(1 for p in plan_rows if p["status"] == "run"),
            "ask": sum(1 for p in plan_rows if p["status"] == "ask"),
            "off": sum(1 for p in plan_rows if p["status"] == "off")}


# --------------------------------------------------------------------------
# EXECUTION  (impure: runs the plan through the real gated seams)
# --------------------------------------------------------------------------
# run_for is the single code path BOTH the manual "Run autopilot" button and the cron
# heartbeat (/tasks/tick) use, so an autopilot run can never do something a click couldn't.
# Imported here (not at module top) keeps the pure planning section above dependency-free
# and sidesteps any import-order surprise; db/messaging/ai do not import autopilot, so
# there is no cycle.
from datetime import datetime

import db
import ai
import messaging
import reactivation
import referrals
import radiusmail
import plans
import cadence
import posting
import publishing


def run_for(business_id, origin="manual"):
    """Run every take_over play for ONE tenant through the consent-gated seams, exactly as
    the /autopilot/run button does, and log the run to the activity trail. Returns:

        {"blocked": bool, "posts": int, "msgs": int, "capped": int, "sms_mode": str}

    blocked=True (no work done, nothing logged) when the tenant can't autopilot (plan gate,
    Premium+) or has no Game Plan yet. Drafts wait for approval; sends respect consent,
    quiet hours, opt-out/DNC and the plan's text allowance.

    NOTE (Phase 1): get_found/show_work are cadence-paced -- a play is skipped (and not
    counted in posts) when the tenant already has a recent post on that platform inside the
    play's window (cadence.CADENCE), so the heartbeat can run every ~15 min without
    over-drafting. Content still lands as a draft awaiting approval. See AUTONOMY_PLAN.
    """
    biz = db.get_business(business_id)
    tier = db.get_plan(business_id)
    sms_mode = messaging.channel_status(business_id).get("sms", "simulated")
    if not biz or not plans.can_autopilot(tier) or not db.has_mandate(business_id):
        return {"blocked": True, "posts": 0, "msgs": 0, "capped": 0, "sms_mode": sms_mode}

    remaining = max(0, plans.text_cap(tier) - db.messages_this_month(business_id))
    elections = {p["playbook"]: p["election"] for p in db.get_mandate(business_id)}
    posts = msgs = capped = 0
    link = (biz.get("google_review_link") or "").strip()

    def _text(cu, body, kind, purpose):
        nonlocal msgs, remaining, capped
        if remaining <= 0:                # monthly allowance exhausted -> pace the rest
            capped += 1
            return False
        res = messaging.send_sms(business_id, cu["phone"], body, kind=kind,
                                 purpose=purpose, contact=cu)
        # Only count a message that actually went out (live or simulated-delivery). A blocked
        # send (opt-out / quiet hours / no consent) isn't counted or charged, so the report
        # never claims a send that didn't happen.
        if res.get("status") in ("sent", "simulated"):
            msgs += 1
            remaining -= 1
            return True
        if res.get("status") == "blocked_cap":   # hit today's pace -> continues next run
            capped += 1
        return False

    def _eligible(cu):
        return (cu.get("phone") and not cu.get("suppressed")
                and cu.get("consent_status") != "opted_out")

    # Phase 2 trust dial: when the tenant opted in AND the channel is genuinely LIVE,
    # auto-schedule the freshly-drafted post so the heartbeat publishes it on a later
    # tick (mirrors the /posts/<id>/schedule route). Otherwise it stays a draft -- we
    # never auto-publish to a simulated/assisted channel.
    auto_publish = db.get_auto_publish(business_id)

    def _maybe_schedule(pid, platform):
        if auto_publish and publishing.platform_mode(platform, business_id) == "live":
            dt, _, _ = posting.safe_schedule_time(business_id, datetime.now())
            db.schedule_post(pid, business_id, dt.strftime("%Y-%m-%dT%H:%M"))

    for item in plan(elections):
        if item["status"] != "run":
            continue
        pb = item["playbook"]
        if pb == "get_found":
            platform, window = cadence.CADENCE["get_found"]
            if cadence.due(db.last_post_at(business_id, platform), window):
                pid = db.add_post(business_id, "google", "Weekly update",
                                  ai.generate_post(biz, "", "google"), status="draft")
                _maybe_schedule(pid, "google"); posts += 1
        elif pb == "show_work":
            platform, window = cadence.CADENCE["show_work"]
            if cadence.due(db.last_post_at(business_id, platform), window):
                pid = db.add_post(business_id, "instagram", "Project showcase",
                                  ai.generate_post(biz, "Before and after project showcase",
                                                   "instagram"), status="draft")
                _maybe_schedule(pid, "instagram"); posts += 1
        elif pb == "reviews" and link:
            asked = db.requested_contact_ids(business_id)
            for cu in db.list_contacts(business_id, kind="customer"):
                if _eligible(cu) and cu["id"] not in asked:
                    _text(cu, ai.review_request_message(biz, cu.get("name", "")) + " " + link,
                          "transactional", "review_request")
        elif pb == "reactivation":
            reacted = db.contacted_ids(business_id, "reactivation")
            for cu in db.list_contacts(business_id, kind="customer"):
                if (_eligible(cu) and cu["id"] not in reacted
                        and reactivation.is_due(cu.get("last_service"), cu.get("last_job_at"))):
                    yrs = reactivation.years_since(cu.get("last_job_at"))
                    _text(cu, reactivation.reactivation_message(biz, cu.get("name", ""),
                                                                cu.get("last_service", ""), yrs),
                          "marketing", "reactivation")
        elif pb == "referrals":
            asked = db.contacted_ids(business_id, "referral_request")
            for cu in db.list_contacts(business_id, kind="customer"):
                if _eligible(cu) and cu["id"] not in asked:
                    _text(cu, referrals.referral_ask_sms(biz, cu.get("name", "")),
                          "marketing", "referral_request")
        elif pb == "radius_mail":
            # Draft (never send/spend: mail v0 is assisted print-it-yourself) one
            # neighbor campaign per completed job that has a jobsite address and no
            # campaign yet. Counted with posts: it's a draft awaiting approval.
            done = db.mail_campaign_contact_ids(business_id)
            for cu in db.list_contacts(business_id, kind="customer"):
                if (cu.get("last_job_at") and (cu.get("address") or "").strip()
                        and cu["id"] not in done):
                    camp = radiusmail.campaign_from_job(
                        biz, {"address": cu["address"],
                              "service": cu.get("last_service", "")})
                    db.add_mail_campaign(business_id, camp, contact_id=cu["id"])
                    posts += 1
    db.log_autopilot_run(business_id, posts, msgs, capped, sms_mode, origin=origin)
    return {"blocked": False, "posts": posts, "msgs": msgs, "capped": capped,
            "sms_mode": sms_mode}
