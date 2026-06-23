"""Unit tests for the pure first-win decision module (no DB)."""
import sys
import firstwin

_p = _f = 0
def check(label, cond):
    global _p, _f
    if cond: _p += 1
    else: _f += 1; print(f"  FAIL  {label}")

# designate(): mode-aware priority + fallback
check("nothing live -> aeo_faq",
      firstwin.designate(None, {"sms_live": False, "gbp_connected": False}) == "aeo_faq")
check("gbp connected -> gbp_post",
      firstwin.designate({}, {"sms_live": False, "gbp_connected": True}) == "gbp_post")
check("sms live + reviewable backlog -> review_request",
      firstwin.designate({"reviewable_backlog": 3}, {"sms_live": True, "gbp_connected": False}) == "review_request")
check("sms live + backlog + past customers -> review_request (backlog wins)",
      firstwin.designate({"past_customers": 12, "reviewable_backlog": 2}, {"sms_live": True, "gbp_connected": True}) == "review_request")
check("sms live + past customers, no backlog, gbp off -> reactivation",
      firstwin.designate({"past_customers": 5}, {"sms_live": True, "gbp_connected": False}) == "reactivation")
check("sms live, no customers, no gbp -> aeo_faq",
      firstwin.designate({"past_customers": 0}, {"sms_live": True, "gbp_connected": False}) == "aeo_faq")

# achieved(): any real outcome; None when none
check("no facts -> None", firstwin.achieved({}) is None)
check("review_sent -> review_request", firstwin.achieved({"review_sent": True}) == "review_request")
check("only firstback booking counts", firstwin.achieved({"firstback_booking": True}) == "firstback_booking")
check("faq counts even as fallback", firstwin.achieved({"faq_generated": True}) == "aeo_faq")

# nudge_copy(): day-aware, no lockout language
n0 = firstwin.nudge_copy("aeo_faq", 0); n6 = firstwin.nudge_copy("aeo_faq", 6)
check("nudge non-empty day0", bool(n0))
check("nudge changes by day", n0 != n6)
check("no lockout language", "lock" not in (n0 + n6).lower() and "expire" not in (n0 + n6).lower())

# ---- DB-level: real-outcome facts + milestone persistence (Postgres) ----
import os
if os.environ.get("TEST_DATABASE_URL"):
    import uuid, psycopg, urllib.parse as _u
    _admin = os.environ["TEST_DATABASE_URL"]
    _name = "jm_fw_" + uuid.uuid4().hex[:10]
    _a = psycopg.connect(_admin, autocommit=True); _a.execute(f'CREATE DATABASE "{_name}"'); _a.close()
    os.environ["DATABASE_URL"] = _u.urlparse(_admin)._replace(path="/"+_name).geturl()
    os.environ.setdefault("JOBMAGNET_PROVIDER", "demo")
    import db
    db.init_db()
    bid = db.create_business({"name": "FW Co", "trade": "painting"})

    f0 = db.first_win_facts(bid)
    check("fresh tenant: no real outcomes", not any(f0.values()))
    check("milestone is None initially", db.get_milestone(bid) is None)

    # a SIMULATED review request must NOT count
    # log_message real sig: (business_id, channel, to_addr, body, status, provider, kind, purpose, ...)
    db.log_message(bid, "sms", "+15551112222", "review?",
                   "simulated", "simulated", kind="transactional", purpose="review_request")
    check("simulated review request does NOT count", not db.first_win_facts(bid)["review_sent"])
    # a SENT review request DOES count
    db.log_message(bid, "sms", "+15551112222", "review?",
                   "sent", "twilio", kind="transactional", purpose="review_request")
    check("sent review request counts", db.first_win_facts(bid)["review_sent"])

    # generated FAQ artifact counts
    db.update_business(bid, {"faq": "Q: Do you do interiors?\nA: Yes."})
    check("generated faq counts", db.first_win_facts(bid)["faq_generated"])

    # milestone persistence + idempotence + celebrate-once
    db.mark_milestone_achieved(bid, "review_request")
    m1 = db.get_milestone(bid)
    check("milestone recorded", m1 and m1["achieved_win"] == "review_request" and m1["achieved_at"])
    db.mark_milestone_achieved(bid, "aeo_faq")  # idempotent: must not overwrite
    check("achieve is idempotent", db.get_milestone(bid)["achieved_win"] == "review_request")
    check("not celebrated yet", db.get_milestone(bid)["celebrated"] in (0, False))
    db.mark_milestone_celebrated(bid)
    check("celebrated flips", db.get_milestone(bid)["celebrated"] in (1, True))

    # ---- app-level: first_win_block state machine (uses same DB) ----
    import app as appmod
    appmod.app.testing = True
    nb = db.create_business({"name": "Brief Co", "trade": "roofing"})
    blk = appmod.first_win_block(nb)
    check("fresh tenant in_progress + aeo_faq fallback",
          blk["state"] == "in_progress" and blk["win"] == "aeo_faq")
    check("block has cta + nudge + day count",
          blk["cta_route"] == "/local" and blk["nudge"] and blk["days_since_signup"] >= 0)
    # real outcome -> achieved (uncelebrated first, then celebrated)
    db.update_business(nb, {"faq": "Q: x\nA: y"})
    blk2 = appmod.first_win_block(nb)
    check("achieved_uncelebrated on first detection", blk2["state"] == "achieved_uncelebrated")
    blk3 = appmod.first_win_block(nb)
    check("celebrated only once", blk3["state"] == "achieved_celebrated")

    # ---- naive created_at must not crash (TypeError guard) ----
    nb2 = db.create_business({"name": "Naive Date Co", "trade": "plumbing"})
    conn = db.get_conn()
    conn.execute("UPDATE businesses SET created_at=%s WHERE id=%s",
                 ("2025-06-01T12:00:00", nb2))
    conn.commit()
    conn.close()
    blk_naive = appmod.first_win_block(nb2)
    check("naive created_at does not crash + days_since_signup >= 1",
          isinstance(blk_naive, dict) and blk_naive.get("days_since_signup", -1) >= 1)

    _a = psycopg.connect(_admin, autocommit=True)
    _a.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()", (_name,))
    _a.execute(f'DROP DATABASE IF EXISTS "{_name}"'); _a.close()

print(f"==== {_p} passed, {_f} failed ====")
sys.exit(1 if _f else 0)
