"""Durable coverage for the growth-playbook features (GROWTH_PLAYBOOK_APPLIED.md).

Framework-free, like the other suites. Spins up a throwaway Postgres DB off
TEST_DATABASE_URL, drops it on exit. Exercises the new routes/branches the
existing suites do not touch.

Run:  TEST_DATABASE_URL='postgresql://...' ./.venv/bin/python test_growth.py
"""
import os
import sys
import uuid
import atexit
import psycopg
import urllib.parse as _u

_ADMIN = os.environ["TEST_DATABASE_URL"]
_DB = "jm_growth_" + uuid.uuid4().hex[:12]
_a = psycopg.connect(_ADMIN, autocommit=True)
_a.execute(f'CREATE DATABASE "{_DB}"')
_a.close()
os.environ["DATABASE_URL"] = _u.urlparse(_ADMIN)._replace(path="/" + _DB).geturl()


@atexit.register
def _drop():
    a = psycopg.connect(_ADMIN, autocommit=True)
    a.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
              "WHERE datname=%s AND pid<>pg_backend_pid()", (_DB,))
    a.execute(f'DROP DATABASE IF EXISTS "{_DB}"')
    a.close()


os.environ["JOBMAGNET_PROVIDER"] = "demo"
os.environ["JOBMAGNET_OWNER_PASSWORD"] = "jobmagnet123"
os.environ.setdefault("JOBMAGNET_SECRETS_KEY", "")

import app as appmod      # noqa: E402
import db                 # noqa: E402
import firstwin           # noqa: E402
import mandate            # noqa: E402
import reviewsync         # noqa: E402
import assistant          # noqa: E402

_p = _f = 0


def check(label, cond):
    global _p, _f
    if cond:
        _p += 1
    else:
        _f += 1
        print(f"  FAIL  {label}")


# ===========================================================================
# PURE — firstwin (no I/O)
# ===========================================================================
# P0-2: the orphaned out-of-scope win id is gone from both tables.
check("P0-2 orphaned win id absent from WINS",
      "firstback_booking" not in firstwin.WINS)
check("P0-2 orphaned win id absent from _FACT_WIN",
      all("firstback_booking" not in pair for pair in firstwin._FACT_WIN))
check("P0-2 every achievable win id has a WINS entry",
      all(win in firstwin.WINS for _, win in firstwin._FACT_WIN))

# P2-12: trade-aware designate — same signals, different first win by trade.
sig = {"past_customers": 50, "reviewable_backlog": 5}
live = {"sms_live": True, "gbp_connected": False}
painter = firstwin.designate(sig, live)                       # generic -> review_request
roofer = firstwin.designate(sig, live, {"trade": "roofing"})  # roof branch -> reactivation
check("P2-12 painter first win is review_request", painter == "review_request")
check("P2-12 roofer first win is reactivation", roofer == "reactivation")
check("P2-12 trade actually changes the recommendation", painter != roofer)
check("P2-12 hvac w/ missed leads + base -> reactivation",
      firstwin.designate({"missed_leads": 3, "past_customers": 10}, live, {"trade": "hvac"}) == "reactivation")
check("P2-12 hvac w/ missed leads, thin base -> review_request",
      firstwin.designate({"missed_leads": 3, "past_customers": 2}, live, {"trade": "hvac"}) == "review_request")
check("P2-12 no integrations -> aeo_faq fallback",
      firstwin.designate({}, {"sms_live": False, "gbp_connected": False}) == "aeo_faq")

# P2-15: photo_post win exists and is achievable via the MMS fact.
check("P2-15 photo_post in WINS with a CTA route",
      "photo_post" in firstwin.WINS and firstwin.WINS["photo_post"]["cta_route"])
check("P2-15 photo_post_generated fact resolves to photo_post",
      firstwin.achieved({"photo_post_generated": True}) == "photo_post")

# ===========================================================================
# INTEGRATION — routes (test client, logged in as the seed owner / business 1)
# ===========================================================================
appmod.app.testing = True
c = appmod.app.test_client()
r = c.post("/login", data={"email": "heritagehousepainting@gmail.com",
                           "password": "jobmagnet123"})
check("login redirects to dashboard", r.status_code == 302)

# P0-3: walkthrough_started_at is stamped on GET, idempotently.
check("P0-3 walkthrough_started_at unset before first GET",
      not db.get_business(1).get("walkthrough_started_at"))
c.get("/walkthrough")
_started = db.get_business(1).get("walkthrough_started_at")
check("P0-3 walkthrough_started_at set after GET", bool(_started))
c.get("/walkthrough")
check("P0-3 walkthrough_started_at is idempotent (unchanged on 2nd GET)",
      db.get_business(1).get("walkthrough_started_at") == _started)

# P0-3: funnel counts helper has the documented shape and stage 1 reflects the GET.
fc = db.activation_funnel_counts()
check("P0-3 activation_funnel_counts shape",
      isinstance(fc, dict) and {"stage1", "stage2", "stage3"} <= set(fc))
check("P0-3 stage1 counts the started tenant", fc["stage1"] >= 1)

# P1-5 / P1-10 / P2-19 / P2-20: POST captures Brain cols + the new signal.
# Thin past-customer base on purpose so reactivation is a not_yet play (for /insight).
r = c.post("/walkthrough", data={
    "trade": "painting", "service_area": "Pittsburgh PA", "years_in_business": "8",
    "avg_job_value": "3500", "past_customers": "2", "oldest_job_years": "0",
    "monthly_leads": "6", "missed_leads": "0", "review_count": "12",
    "reviewable_backlog": "0", "competitor_review_count": "80",
    "capacity_note": "high-end exterior repaints",
    "success_metric": "5 more booked jobs a month",
    "brief_format": "straight_and_brief",
}, follow_redirects=False)
check("P1-5 walkthrough POST succeeds", r.status_code in (200, 302))
b1 = db.get_business(1)
check("P1-5 capacity_note persisted", (b1.get("capacity_note") or "").strip() != "")
check("P1-5 success_metric persisted",
      "booked jobs" in (b1.get("success_metric") or ""))
check("P2-19 brief_format persisted",
      (b1.get("brief_format") or "") == "straight_and_brief")
_sig = db.get_signals(1) or {}
check("P2-20 competitor_review_count persisted as signal",
      (_sig.get("competitor_review_count") or 0) == 80)

# P2-16: aeo_faq auto-generated at POST (fresh tenant, no SMS/GBP) -> slug + faq + public page.
slug = b1.get("biz_slug")
check("P2-16 biz_slug generated at walkthrough POST", bool(slug))
check("P2-16 faq artifact persisted", bool((b1.get("faq") or "").strip()))
if slug:
    check("P2-16 public /faq/<slug> renders", c.get(f"/faq/{slug}").status_code == 200)
check("P2-16 unknown slug -> 404 (not 500)",
      c.get("/faq/no-such-business-xyz").status_code == 404)

# P2-17: public /insight/<slug>/<play_key> for a not_yet play.
result = mandate.diagnose(b1, _sig)
not_yet = [p for p in result["plays"] if p["applicability"] == "not_yet"]
check("P2-17 thin profile yields at least one not_yet play", len(not_yet) >= 1)
if slug and not_yet:
    key = not_yet[0]["key"]
    check("P2-17 /insight/<slug>/<not_yet key> renders",
          c.get(f"/insight/{slug}/{key}").status_code == 200)
    # an 'applies' play (or unknown key) must NOT render an insight page
    applies = [p for p in result["plays"] if p["applicability"] == "applies"]
    if applies:
        check("P2-17 /insight rejects a non-not_yet play -> 404",
              c.get(f"/insight/{slug}/{applies[0]['key']}").status_code == 404)
check("P2-17 unknown insight slug -> 404 (not 500)",
      c.get("/insight/nope/reactivation").status_code == 404)

# P2-13: bottleneck radio persists and the Mandate still renders.
r = c.post("/mandate/bottleneck", data={"bottleneck_priority": "no_reviews"},
           follow_redirects=True)
check("P2-13 /mandate/bottleneck no 500", r.status_code == 200)
check("P2-13 bottleneck_priority persisted",
      (db.get_business(1).get("bottleneck_priority") or "") == "no_reviews")
check("P2-13 /mandate renders after bottleneck set", c.get("/mandate").status_code == 200)

# P1-7: the Mandate is injected into the assistant system prompt.
sp_with = assistant._route_system(db.get_business(1))
check("P1-7 _route_system returns a non-empty system prompt", bool(sp_with) and len(sp_with) > 0)

# P1-4: _briefing surfaces the not_yet restraint copy as `passed_on`.
brief = appmod._briefing(db.get_business(1), {"draft": 0}, [], 0, True, _sig)
check("P1-4 _briefing returns a passed_on key", "passed_on" in brief)
check("P1-4 passed_on populated when a not_yet play exists",
      isinstance(brief["passed_on"], dict)
      and brief["passed_on"].get("label") and brief["passed_on"].get("reason"))

# P0-1: pull_reviews is an honest no-op until GBP is connected (never fabricates).
check("P0-1 pull_reviews simulated when GBP unconnected",
      reviewsync.pull_reviews(1) == {"mode": "simulated", "added": 0})

# P2-14: a jobmagnet_alert (renamed from mason_alert) can be set + cleared via the dashboard.
_conn = db.get_conn()
_conn.execute("UPDATE businesses SET jobmagnet_alert=%s WHERE id=1", ("stall test",))
_conn.commit()
_conn.close()
check("P2-14 jobmagnet_alert set", (db.get_business(1).get("jobmagnet_alert") or "") == "stall test")
c.get("/dashboard?clear=jobmagnet_alert")
check("P2-14 jobmagnet_alert cleared via /dashboard?clear=jobmagnet_alert",
      not db.get_business(1).get("jobmagnet_alert"))
# Backfill safety: the old mason_alert column still exists (not dropped) so the rename
# is reversible and never lost data.
_bc = db.get_conn()
_has_old = _bc.execute("SELECT column_name FROM information_schema.columns "
                       "WHERE table_name='businesses' AND column_name='mason_alert'").fetchone()
_bc.close()
check("legacy mason_alert column preserved (reversible rename)", _has_old is not None)

print(f"==== {_p} passed, {_f} failed ====")
sys.exit(1 if _f else 0)
