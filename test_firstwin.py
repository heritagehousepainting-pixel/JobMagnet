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
check("sms live + past customers -> review_request",
      firstwin.designate({"past_customers": 12}, {"sms_live": True, "gbp_connected": True}) == "review_request")
check("sms live + reviewable backlog -> review_request",
      firstwin.designate({"reviewable_backlog": 3}, {"sms_live": True, "gbp_connected": False}) == "review_request")
check("sms live, customers, no backlog, gbp off, review picked before reactivation",
      firstwin.designate({"past_customers": 5}, {"sms_live": True, "gbp_connected": False}) == "review_request")
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

print(f"==== {_p} passed, {_f} failed ====")
sys.exit(1 if _f else 0)
