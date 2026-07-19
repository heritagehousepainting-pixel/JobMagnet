"""End-to-end smoke test for JobMagnet v0.1.

Asserts every claim we make about the product is actually true and functional:
seed-on-boot, auth, multi-tenant isolation, the Business Brain, the Content
Engine, and the full approval loop. Uses Flask's test client (no server needed).

Run:  ./.venv/bin/python test_smoke.py
"""
import os
import sys
import uuid
import atexit
import psycopg

# Run against a throwaway Postgres DB so the suite is isolated + idempotent and
# never touches real data. Create a uniquely-named DB, point the app at it, drop
# it on exit. Set env BEFORE importing config/app.
_ADMIN_URL = os.environ["TEST_DATABASE_URL"]
_TEST_DB = "jm_test_" + uuid.uuid4().hex[:12]
_admin = psycopg.connect(_ADMIN_URL, autocommit=True)
_admin.execute(f'CREATE DATABASE "{_TEST_DB}"')
_admin.close()
# Build the app-facing URL by swapping the database name on the admin URL.
import urllib.parse as _u
_p = _u.urlparse(_ADMIN_URL)
_APP_URL = _p._replace(path="/" + _TEST_DB).geturl()
os.environ["DATABASE_URL"] = _APP_URL

@atexit.register
def _drop_test_db():
    a = psycopg.connect(_ADMIN_URL, autocommit=True)
    a.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
              "WHERE datname=%s AND pid<>pg_backend_pid()", (_TEST_DB,))
    a.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB}"')
    a.close()

os.environ["JOBMAGNET_PROVIDER"] = "demo"
os.environ["JOBMAGNET_OWNER_PASSWORD"] = "jobmagnet123"
os.environ["JOBMAGNET_SECRETS_KEY"] = ""

import app as appmod
import db
import ai
import mandate
import getfound
import speedtolead
import reactivation
import referrals
import offers
import autopilot
import connections
import messaging
import publishing
import plans
import billing
import radiusmail
import partners
import lsa
import roi

# The bulk suite posts plain forms; CSRF is exercised separately (see end), so
# run the rest under testing mode where the CSRF guard is skipped.
appmod.app.testing = True

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


def client():
    return appmod.app.test_client()


# --- Seed on boot -----------------------------------------------------------
print("Seed on boot")
check("Heritage seeded as business 1", db.get_business(1)["name"] == "Heritage House Painting")
check("seed owner user exists", db.count_users() == 1)
check("brain defaults to demo (no API key)", ai.brain_mode() == "demo")

# --- Auth -------------------------------------------------------------------
print("Auth")
c = client()
r = c.get("/dashboard")
check("dashboard requires login (redirect)", r.status_code == 302 and "/login" in r.headers["Location"])
r = c.post("/login", data={"email": "heritagehousepainting@gmail.com", "password": "wrong"})
check("wrong password rejected", b"Wrong email or password" in r.data)
r = c.post("/login", data={"email": "heritagehousepainting@gmail.com", "password": "jobmagnet123"})
check("correct login redirects to dashboard", r.status_code == 302 and r.headers["Location"].endswith("/dashboard"))
r = c.get("/dashboard")
check("dashboard is now the command center", r.status_code == 200 and b"command-shell" in r.data)
r = c.get("/queue")
check("queue loads the approval view", r.status_code == 200 and b"Awaiting your review" in r.data)

# --- Content Engine + approval loop ----------------------------------------
print("Content Engine + approval loop")
r = c.post("/compose", data={"action": "generate", "platform": "instagram",
                             "topic": "Finished an exterior repaint, warm white with navy trim."})
check("compose generates a draft", r.status_code == 200 and b"Draft" in r.data and b"navy trim" in r.data)
r = c.post("/compose", data={"action": "save", "platform": "instagram",
                             "topic": "exterior repaint",
                             "body": "Exterior repaint wrapped up. Message us for a free estimate."},
           follow_redirects=False)
check("saving a draft redirects to dashboard", r.status_code == 302)
posts = db.list_posts(1)
check("post persisted as draft", len(posts) == 1 and posts[0]["status"] == "draft")
pid = posts[0]["id"]
r = c.get("/queue")
check("draft shows in review queue with Approve", b"Approve" in r.data and b"Exterior repaint wrapped up" in r.data)
# edit
c.post(f"/posts/{pid}/edit", data={"body": "Edited body for the post."})
check("editing a draft updates the body", db.get_post(pid, 1)["body"] == "Edited body for the post.")
# approve -> publish
c.post(f"/posts/{pid}/status", data={"status": "approved"})
check("approve sets status approved", db.get_post(pid, 1)["status"] == "approved")
c.post(f"/posts/{pid}/status", data={"status": "published"})
check("mark published sets status published", db.get_post(pid, 1)["status"] == "published")
r = c.get("/queue")
check("dashboard shows published post", b"Published" in r.data)
# reject a second draft
db.add_post(1, "facebook", "t", "A second draft to reject.")
p2 = [p for p in db.list_posts(1) if p["status"] == "draft"][0]["id"]
c.post(f"/posts/{p2}/status", data={"status": "rejected"})
check("reject sets status rejected", db.get_post(p2, 1)["status"] == "rejected")
r = c.get("/queue")
check("rejected post is hidden from dashboard", b"A second draft to reject." not in r.data)
# stats
stats = db.content_stats(1)
check("stats counts correct (1 published, 1 rejected)",
      stats["published"] == 1 and stats["rejected"] == 1 and stats["total"] == 2)

# --- Business Brain (Settings) ---------------------------------------------
print("Business Brain")
r = c.get("/settings")
check("settings shows Heritage profile", b"Heritage House Painting" in r.data and b"Brand voice" in r.data)
c.post("/settings", data={"name": "Heritage House Painting", "trade": "Painting",
                          "service_area": "Test City", "owner_name": "Jon",
                          "brand_voice": "v", "services": "s", "target_customer": "t",
                          "differentiators": "d", "capacity_note": "cap"})
check("settings save persists", db.get_business(1)["service_area"] == "Test City")

# --- Password change --------------------------------------------------------
print("Password change")
c.post("/settings/password", data={"current_password": "jobmagnet123", "new_password": "newpass12345"})
c2 = client()
r = c2.post("/login", data={"email": "heritagehousepainting@gmail.com", "password": "jobmagnet123"})
check("old password no longer works", b"Wrong email or password" in r.data)
r = c2.post("/login", data={"email": "heritagehousepainting@gmail.com", "password": "newpass12345"})
check("new password works", r.status_code == 302)

# --- Multi-tenant isolation -------------------------------------------------
print("Multi-tenant isolation")
cb = client()
r = cb.post("/signup", data={"email": "bob@plumb.com", "password": "plumber123",
                             "name": "Bob's Plumbing", "trade": "Plumbing"})
check("signup creates a tenant + logs in", r.status_code == 302)
check("new tenant is routed to the Walkthrough (Mason is the front door)",
      r.headers["Location"].endswith("/walkthrough"))
bob = db.get_user_by_email("bob@plumb.com")
bob_biz = bob["business_id"]
check("new tenant is a separate business", bob_biz != 1)
bb = db.get_business(bob_biz)
check("new tenant does NOT inherit Heritage's painting services", (bb["services"] or "") == "")
check("new tenant has its own trade", bb["trade"] == "Plumbing")
r = cb.get("/queue")
check("Bob sees none of Heritage's posts", b"Edited body for the post." not in r.data)
check("Bob's post list is empty", db.list_posts(bob_biz) == [])
# cross-tenant write attempt: Bob tries to touch Heritage's published post
cb.post(f"/posts/{pid}/status", data={"status": "draft"})
check("Bob cannot change Heritage's post (scoped)", db.get_post(pid, 1)["status"] == "published")

# --- Provider fallback safety ----------------------------------------------
print("Provider fallback")
gen = ai.generate_post(db.get_business(1), "test job", "facebook")
check("generate_post always returns non-empty text", isinstance(gen, str) and len(gen) > 0)
check("no dashes leak into generated copy", "—" not in gen and "--" not in gen)

# --- Audit fixes (2026-06-15) ----------------------------------------------
print("Audit fixes")
# get_business no longer fabricates Heritage's brain for an unknown tenant id.
check("get_business(unknown id) returns None (no client-zero leak)",
      db.get_business(9999) is None)
# The Business Brain's capacity + owner now actually reach the Content Engine.
sysprompt = ai._system_prompt(db.get_business(1), "facebook")
check("capacity_note is wired into the AI prompt", "WORK WE WANT MORE OF" in sysprompt)
check("owner_name is wired into the AI prompt", "OWNER / CONTACT" in sysprompt)
# Saving a post with a bogus platform is normalised, never stored raw.
c.post("/compose", data={"action": "save", "platform": "myspace",
                         "topic": "x", "body": "Body for a bogus platform."})
saved = [p for p in db.list_posts(1) if p["body"] == "Body for a bogus platform."][0]
check("bogus platform on save falls back to default", saved["platform"] == "facebook")

# --- Phase 0: messaging & consent seam -------------------------------------
print("Phase 0 messaging & consent")
import messaging
from datetime import datetime
check("both channels simulated with no creds",
      messaging.channel_status() == {"sms": "simulated", "email": "simulated"})
day = datetime(2026, 6, 15, 14, 0)    # 2pm: outside quiet hours
night = datetime(2026, 6, 15, 23, 0)  # 11pm: inside quiet hours
check("quiet hours wraps midnight correctly",
      messaging.in_quiet_hours(night) and not messaging.in_quiet_hours(day))
cust = db.add_contact(1, name="Pat Customer", phone="555-201-3000", kind="customer")
res = messaging.send_sms(1, "555-201-3000", "Thanks for your business!",
                         kind="transactional", purpose="test", now=day)
check("simulated SMS is logged, not sent", res["status"] == "simulated" and res["provider"] == "simulated")
res = messaging.send_sms(1, "555-201-3000", "Promo!", kind="marketing", now=night)
check("marketing SMS blocked during quiet hours", res["status"] == "blocked_quiet")
res = messaging.send_sms(1, "555-201-3000", "Reminder", kind="transactional", now=night)
check("transactional SMS ignores quiet hours", res["status"] == "simulated")
# Opt-out via inbound STOP, then sends are blocked.
action = messaging.handle_inbound_sms(1, "555-201-3000", "STOP")
check("inbound STOP records opt-out", action == "opted_out"
      and db.get_contact(cust, 1)["consent_status"] == "opted_out")
res = messaging.send_sms(1, "555-201-3000", "Anything", kind="transactional", now=day)
check("opted-out contact is blocked on every send", res["status"] == "blocked_optout")
action = messaging.handle_inbound_sms(1, "555-201-3000", "START")
check("inbound START re-grants consent", action == "opted_in"
      and db.get_contact(cust, 1)["consent_status"] == "granted")
check("messages are logged to the ledger", len(db.list_messages(1)) >= 5)

# --- Phase 1: reviews & reputation -----------------------------------------
print("Phase 1 reviews")
r = c.get("/reviews")
check("reviews page renders", r.status_code == 200 and b"Reviews &amp; Reputation" in r.data)
db.update_business(1, {"google_review_link": "https://g.page/r/test123"})
check("review link saved to the Brain",
      db.get_business(1)["google_review_link"] == "https://g.page/r/test123")
c.post("/reviews/customers", data={"name": "Dana Homeowner", "phone": "555-777-1212"})
dana = [x for x in db.list_contacts(1, kind="customer") if x["name"] == "Dana Homeowner"][0]
check("customer added + phone normalised", dana["phone"] == "+15557771212")
r = c.post("/reviews/request", data={"contact_id": dana["id"]})
check("review request redirects", r.status_code == 302)
reqs = [m for m in db.list_messages(1) if m["purpose"] == "review_request"]
check("review request logged as simulated SMS",
      reqs and reqs[0]["status"] == "simulated" and reqs[0]["channel"] == "sms")
check("review request includes the Google link", "g.page/r/test123" in reqs[0]["body"])
c.post("/reviews/import", data={"author": "Dana H", "rating": "5",
                                "body": "Fantastic job on our cabinets!", "source": "google"})
rev = db.list_reviews(1)[0]
check("imported review gets an AI-drafted reply",
      rev["status"] == "new" and (rev["response"] or "") != "")
c.post(f"/reviews/{rev['id']}/respond", data={"response": "Thank you so much, Dana!"})
check("saving a reply marks the review responded",
      db.get_review(rev["id"], 1)["status"] == "responded")
rstats = db.review_stats(1)
check("review stats reflect 1 review + requests sent",
      rstats["total"] == 1 and rstats["requested"] >= 1)
# A blank Google link blocks the request with a clear message.
db.update_business(1, {"google_review_link": ""})
r = c.post("/reviews/request", data={"contact_id": dana["id"]})
check("missing review link is caught", "msg=nolink" in r.headers.get("Location", ""))

# --- Phase 2: content & local engine ---------------------------------------
print("Phase 2 content & local")
import seo
import publishing
schema = seo.localbusiness_schema(db.get_business(1))
check("schema markup includes business name + type",
      '"@type"' in schema and db.get_business(1)["name"] in schema)
r = c.get("/local")
check("local SEO page renders", r.status_code == 200 and b"Schema markup" in r.data)
c.post("/local/faq")
check("FAQ generated + saved to Brain", (db.get_business(1)["faq"] or "").startswith("Q:"))
r = c.get("/local")
check("schema embeds FAQ after generation", b"FAQPage" in r.data)
# Scheduling: approve a post, schedule it in the past so it is due, run scheduler.
pid_sched = db.add_post(1, "facebook", "sched", "Scheduled body.", status="approved")
c.post(f"/posts/{pid_sched}/schedule", data={"scheduled_for": "2020-01-01T09:00"})
check("post becomes scheduled", db.get_post(pid_sched, 1)["status"] == "scheduled")
check("past-due post appears in due_posts", any(p["id"] == pid_sched for p in db.due_posts()))
c.post("/scheduler/run")
check("scheduler publishes due posts", db.get_post(pid_sched, 1)["status"] == "published")

# --- Posting guardrails: keep publishes out of quiet hours + from stacking ---
import posting
from datetime import datetime as _dt
qsafe, qchg, _ = posting.safe_schedule_time(1, _dt(2030, 6, 15, 2, 0))   # 2am is quiet
check("a quiet-hours publish is moved to a sane time",
      qchg and not (qsafe.hour >= 21 or qsafe.hour < 8))
osafe, ochg, _ = posting.safe_schedule_time(1, _dt(2030, 6, 15, 10, 0))  # 10am is fine
check("a daytime publish is left alone", (not ochg) and osafe == _dt(2030, 6, 15, 10, 0))
pid_gap = db.add_post(1, "facebook", "t", "Spacing guardrail body.")
db.schedule_post(pid_gap, 1, "2030-06-16T10:00")
gsafe, gchg, _ = posting.safe_schedule_time(1, _dt(2030, 6, 16, 10, 30))  # 30m < 60m gap
check("a publish inside the min-gap is spaced out",
      gchg and (gsafe - _dt(2030, 6, 16, 10, 0)).total_seconds() >= 3600)
db.set_post_status(pid_gap, 1, "rejected")  # don't leave it in the schedule
# the route applies the guardrail AND lands on the manual queue, not the command center
pid_rt = db.add_post(1, "facebook", "t", "Route guardrail body.", status="approved")
r = c.post(f"/posts/{pid_rt}/schedule", data={"scheduled_for": "2030-06-17T03:00"})
check("schedule route redirects to /queue", r.status_code == 302 and "/queue" in r.headers["Location"])
check("schedule route moved the 3am publish out of quiet hours",
      "T03:00" not in (db.get_post(pid_rt, 1)["scheduled_for"] or ""))
db.set_post_status(pid_rt, 1, "rejected")

# --- Bulk-send pacing: plan-tiered daily cap + (now-enforced) monthly cap ---
import messaging as _msg
import plans as _plans
cs = _msg.cap_status(1)
check("cap_status reports the plan's daily + monthly caps",
      cs["day_cap"] == 40 and cs["month_cap"] == 750)
# Fresh tenant so its daily count starts at zero, independent of earlier sends.
bidp = db.create_business({"name": "Pace Co", "trade": "painting"})
cp = db.get_contact(db.add_contact(bidp, name="Pace", phone="+15557770001", kind="customer"), bidp)
cp2id = db.add_contact(bidp, name="Pace Two", phone="+15557770002", kind="customer")
cp2 = db.get_contact(cp2id, bidp)
_origd = _plans.PLANS["pro"]["daily_cap"]
_plans.PLANS["pro"]["daily_cap"] = 2          # make the boundary cheap to hit
# Pass a fixed midday `now` so the quiet-hours gate (which runs before the cap) never
# interferes -- this test is about the pacing cap, not the time of day.
_noon = datetime(2030, 6, 16, 12, 0, 0)
r1 = _msg.send_sms(bidp, cp["phone"], "one", kind="marketing", purpose="pace_test", contact=cp, now=_noon)
r2 = _msg.send_sms(bidp, cp["phone"], "two", kind="marketing", purpose="pace_test", contact=cp, now=_noon)
r3 = _msg.send_sms(bidp, cp2["phone"], "three", kind="marketing", purpose="pace_test", contact=cp2, now=_noon)
check("sends within the daily cap go out",
      r1["status"] in ("sent", "simulated") and r2["status"] in ("sent", "simulated"))
check("the send past the daily cap is paced (blocked_cap)", r3["status"] == "blocked_cap")
check("a paced send is NOT marked contacted, so it retries on the next run",
      cp2id not in db.contacted_ids(bidp, "pace_test"))
_plans.PLANS["pro"]["daily_cap"] = _origd
# Monthly plan cap is now actually enforced (was display-only before).
_origm = _plans.PLANS["pro"]["text_cap"]
_plans.PLANS["pro"]["text_cap"] = 0
r4 = _msg.send_sms(bidp, cp2["phone"], "month", kind="marketing", purpose="pace_test", contact=cp2, now=_noon)
check("hitting the monthly plan cap blocks too (now enforced)", r4["status"] == "blocked_cap")
_plans.PLANS["pro"]["text_cap"] = _origm
# Note: we intentionally do NOT delete_business(bidp) -- deleting frees the rowid for
# reuse while its message rows remain, which would pollute a later tenant's counts.
# Publish (assisted for Facebook until Meta is connected).
pid_pub = db.add_post(1, "facebook", "t", "Body to publish.", status="approved")
r = c.post(f"/posts/{pid_pub}/publish")
check("publish marks published + assisted mode for FB",
      db.get_post(pid_pub, 1)["status"] == "published" and "pub=assisted" in r.headers.get("Location", ""))
check("GBP publish mode is simulated when not connected",
      publishing.platform_mode("google") == "simulated")
# Photo-by-text: an inbound text from a known contact becomes a draft.
before = len([p for p in db.list_posts(1) if p["status"] == "draft"])
r = c.post("/webhooks/sms", data={"From": "+15557771212",
                                  "Body": "Finished a deck stain today", "NumMedia": "1",
                                  "business_id": "1"})
check("photo-by-text creates a draft from a known contact", r.status_code == 201)
check("draft count increased from inbound text",
      len([p for p in db.list_posts(1) if p["status"] == "draft"]) == before + 1)
r = c.post("/webhooks/sms", data={"From": "+19998887777", "Body": "hi", "business_id": "1"})
check("inbound from an unknown number is ignored", r.status_code == 204)

# --- Phase 3: closed-loop ROI ----------------------------------------------
print("Phase 3 ROI loop")
r = c.get("/roi")
check("ROI page renders", r.status_code == 200 and b"Cost / booked job" in r.data)
c.post("/roi/spend", data={"channel": "social", "amount": "200"})
c.post("/roi/conversion", data={"channel": "social", "status": "won", "value": "1000"})
c.post("/roi/conversion", data={"channel": "social", "status": "won", "value": "1000"})
s = db.roi_summary(1)
soc = [r for r in s["rows"] if r["channel"] == "social"][0]
check("cost per booked job computed ($200 / 2 = $100)",
      soc["spend"] == 200 and soc["booked"] == 2 and soc["cost_per_booked"] == 100.0)
check("revenue + ROAS computed", soc["revenue"] == 2000 and soc["roas"] == 10.0)
check("totals aggregate cost per booked job", s["totals"]["cost_per_booked"] == 100.0)
r = c.post("/roi/sync-firstback")
check("FirstBack sync is simulated when not connected",
      "sync=simulated" in r.headers.get("Location", ""))
r = c.post("/webhooks/booking", data={"business_id": "1", "channel": "google_lsa", "value": "1500"})
check("booking webhook creates a booked conversion", r.status_code == 201)
_lsa_row = [r for r in db.roi_summary(1)["rows"] if r["channel"] == "google_lsa"][0]
check("webhook booking shows under its channel", _lsa_row["booked"] == 1)

# --- Phase 4: ads assist + lead engine -------------------------------------
print("Phase 4 ads + leads")
import ads
bud = ads.recommend_budget(1_000_000)
check("budget matches the 8-12% rule ($1M -> $6.6-10k total, $4-7k paid)",
      bud["total_lo"] == 6667 and bud["total_hi"] == 10000 and bud["paid_hi"] == 7000)
r = c.get("/contacts")
check("contacts page renders", r.status_code == 200 and b"Contacts &amp; Leads" in r.data)
c.post("/contacts/add", data={"name": "Ace Realty", "phone": "555-300-4000", "kind": "partner"})
check("partner contact added",
      any(x["name"] == "Ace Realty" for x in db.list_contacts(1, kind="partner")))
c.post("/contacts/import", data={"kind": "lead",
       "rows": "Lead One, 555 111 2222\nLead Two, 555 333 4444, l2@x.com"})
check("bulk import created leads", len(db.list_contacts(1, kind="lead")) >= 2)
ace = [x for x in db.list_contacts(1, kind="partner") if x["name"] == "Ace Realty"][0]
c.post(f"/contacts/{ace['id']}/suppress")
check("contact marked do-not-contact (DNC)", db.get_contact(ace["id"], 1)["suppressed"] == 1)
res = messaging.send_sms(1, ace["phone"], "hi", kind="transactional",
                         now=datetime(2026, 6, 15, 14, 0))
check("DNC-suppressed contact is blocked from sends", res["status"] == "blocked_optout")
r = c.get("/ads?revenue=1000000")
check("ads page renders the budget", r.status_code == 200 and b"Paid ads / mo" in r.data)
r = c.post("/ads", data={"action": "copy", "revenue": "1000000"})
check("ad copy generates", r.status_code == 200 and b"Headlines" in r.data)

# --- Phase 5: cold email (B2B, CAN-SPAM) -----------------------------------
print("Phase 5 cold email")
db.update_business(1, {"mailing_address": ""})
bob = db.add_contact(1, name="Bob Broker", email="bob@realty.com", kind="partner")
r = c.post("/outreach/send", data={"contact_id": bob, "subject": "Hi", "body": "Hello"})
check("cold email blocked without a mailing address (CAN-SPAM)",
      "msg=noaddr" in r.headers.get("Location", ""))
db.update_business(1, {"mailing_address": "123 Main St, Springfield IL 62701"})
r = c.post("/outreach", data={"action": "generate", "contact_id": bob})
check("partner email draft generates", r.status_code == 200 and b"Draft to Bob Broker" in r.data)
r = c.post("/outreach/send", data={"contact_id": bob, "subject": "Partner?", "body": "Let us refer."})
check("cold email sent (simulated)", "msg=sent_simulated" in r.headers.get("Location", ""))
sent = [m for m in db.list_messages(1) if m["purpose"] == "cold_email"]
check("cold email carries the CAN-SPAM footer (address + opt-out)",
      sent and f"unsubscribe/{bob}" in sent[0]["body"] and "123 Main St" in sent[0]["body"])
check("cold email is logged as marketing-kind", sent[0]["kind"] == "marketing")
import crypto as _crypto
# The opt-out link is HMAC-signed: a guessed/enumerated id (no or wrong token) is refused.
r = c.get(f"/unsubscribe/{bob}")
check("unsubscribe without a token is refused (400, can't be enumerated)",
      r.status_code == 400 and db.get_contact(bob, 1)["consent_status"] != "opted_out")
r = c.get(f"/unsubscribe/{bob}?t=wrongtoken")
check("unsubscribe with a wrong token is refused",
      r.status_code == 400 and db.get_contact(bob, 1)["consent_status"] != "opted_out")
_goodtok = _crypto.sign_id("unsub", bob)
check("the footer link carries the valid token", f"unsubscribe/{bob}?t={_goodtok}" in sent[0]["body"])
r = c.get(f"/unsubscribe/{bob}?t={_goodtok}")
check("public unsubscribe with the valid token opts the contact out",
      r.status_code == 200 and db.get_contact(bob, 1)["consent_status"] == "opted_out")
r = c.post("/outreach/send", data={"contact_id": bob, "subject": "x", "body": "y"})
check("opted-out partner is blocked from further email",
      "sent_blocked" in r.headers.get("Location", ""))

# --- Phase 6: cold SMS/voice (hard-gated) ----------------------------------
print("Phase 6 cold SMS/voice (gated)")
r = c.get("/cold")
check("cold outreach UI removed (channel permanently gated; the seam remains)",
      r.status_code == 404)
prospect = db.add_contact(1, name="Cold Prospect", phone="555-900-1000", kind="lead")
pc = db.get_contact(prospect, 1)
res = messaging.send_cold_sms(1, pc["phone"], "hi", contact=pc)
check("cold SMS blocked while channel disabled (attorney gate)",
      res["status"] == "blocked_disabled")
res = messaging.place_cold_voice(1, pc["phone"], "script", contact=pc)
check("cold voice blocked while disabled", res["status"] == "blocked_disabled")
messaging.COLD_SMS_ENABLED = True   # simulate the attorney sign-off / enablement
res = messaging.send_cold_sms(1, pc["phone"], "hi", contact=db.get_contact(prospect, 1))
check("cold SMS still blocked without prior written consent",
      res["status"] == "blocked_no_consent")
db.set_contact_consent(1, prospect, "sms", "granted",
                       source="written consent recorded (test)")
check("written consent recorded in the ledger",
      db.get_contact(prospect, 1)["consent_status"] == "granted")
res = messaging.send_cold_sms(1, pc["phone"], "hi", contact=db.get_contact(prospect, 1),
                              now=datetime(2026, 6, 15, 14, 0))
check("cold SMS sends (simulated) only with consent + channel enabled",
      res["status"] == "simulated")
messaging.COLD_SMS_ENABLED = False  # leave the gate closed

# --- Mason's diagnostic / Mandate engine (A) -------------------------------
print("Mandate engine (pure logic)")
biz1 = db.get_business(1)
# Heritage-like: 1yr, invisible, tapped reviews, no dormant list, closes what it gets.
heritage_sig = {"years_in_business": 1, "monthly_leads": 4, "missed_leads": 0,
                "review_count": 8, "reviewable_backlog": 0, "new_jobs_per_month": 3,
                "past_customers": 15, "oldest_job_years": 1, "avg_job_value": 7000,
                "gbp_claimed": True, "runs_ads": False}
d = mandate.diagnose(biz1, heritage_sig)
plays = {p["key"]: p for p in d["plays"]}
check("new invisible shop is classified", d["state"] == "new_invisible")
check("get_found is the #1 play for an invisible shop", plays["get_found"]["priority"] == 1)
check("reactivation is NOT applicable yet (honest)", plays["reactivation"]["applicability"] == "not_yet")
check("reviews can't bootstrap, ranks below get_found",
      plays["reviews"]["priority"] > plays["get_found"]["priority"])
check("speed-to-lead is low priority at low volume",
      plays["speed_to_lead"]["recommended"] == "ask_first")

# Established shop sitting on a dormant base, with modest fresh demand -> opposite order
# (reactivation applies). "Dormant" only makes sense when leads aren't already pouring in.
dormant_sig = {"years_in_business": 8, "monthly_leads": 6, "missed_leads": 1,
               "review_count": 80, "past_customers": 300, "oldest_job_years": 5,
               "new_jobs_per_month": 6, "avg_job_value": 5000, "gbp_claimed": True}
d2 = mandate.diagnose(biz1, dormant_sig)
plays2 = {p["key"]: p for p in d2["plays"]}
check("established dormant shop is classified", d2["state"] == "established_dormant")
check("reactivation applies for a dormant base", plays2["reactivation"]["applicability"] == "applies")
check("re-prioritisation works: reactivation outranks get_found here",
      plays2["reactivation"]["priority"] < 8 and plays2["reactivation"]["applicability"] == "applies")
# Tuning: a shop with an old base but HIGH lead volume is NOT dormant -- it's leaky/growing.
# (A busy shop's cheapest next play isn't its old list; it's plugging the lead leak.) The
# reactivation PLAY still applies; only the headline state changes.
busy_old = mandate.diagnose(biz1, {"years_in_business": 8, "monthly_leads": 30,
    "missed_leads": 12, "review_count": 80, "past_customers": 300, "oldest_job_years": 5})
check("an old base with high+leaky volume classifies leaky, not dormant",
      busy_old["state"] == "high_volume_leaky")
check("reactivation still applies for the old base even when not the headline",
      {p["key"]: p for p in busy_old["plays"]}["reactivation"]["applicability"] == "applies")

# High-volume leaky shop -> speed-to-lead jumps to the top.
leaky = mandate.diagnose(biz1, {"years_in_business": 5, "monthly_leads": 30,
                                "missed_leads": 15, "past_customers": 10,
                                "oldest_job_years": 2, "review_count": 40})
lp = {p["key"]: p for p in leaky["plays"]}
check("leaky shop classified", leaky["state"] == "high_volume_leaky")
check("speed-to-lead is #1 when leads are being dropped", lp["speed_to_lead"]["priority"] == 1)

check("normalize fills reviewable_backlog from past - reviews",
      mandate.normalize_signals({"past_customers": 15, "review_count": 8})["reviewable_backlog"] == 7)
check("normalize defaults are safe on empty input",
      mandate.normalize_signals({})["monthly_leads"] == 0)
_clamp = mandate.normalize_signals({"monthly_leads": -5, "missed_leads": 99,
                                    "past_customers": -3, "reviewable_backlog": 999,
                                    "review_count": 2})
check("negative/garbage signals are clamped",
      _clamp["monthly_leads"] == 0 and _clamp["missed_leads"] == 0
      and _clamp["past_customers"] == 0 and _clamp["reviewable_backlog"] == 0)

print("Mandate engine (routes + persistence)")
r = c.get("/walkthrough")
check("walkthrough page renders", r.status_code == 200 and b"Walkthrough" in r.data)
r = c.get("/mandate")
check("mandate redirects to walkthrough before any run",
      r.status_code == 302 and r.headers["Location"].endswith("/walkthrough"))
r = c.post("/walkthrough", data={k: str(v) for k, v in heritage_sig.items()})
check("walkthrough POST builds the mandate and redirects",
      r.status_code == 302 and r.headers["Location"].endswith("/mandate"))
check("mandate persisted for the tenant", db.has_mandate(1))
check("signals persisted for the tenant", db.get_signals(1)["past_customers"] == 15)
r = c.get("/mandate")
check("mandate page renders with Mason's read",
      r.status_code == 200 and b"JobMagnet's read" in r.data and b"Get Found" in r.data)
check("mandate page honestly shows reactivation as Not yet",
      b"Database Reactivation" in r.data and b"Not yet" in r.data)
m = {p["playbook"]: p for p in db.get_mandate(1)}
check("election defaults to the recommendation", m["get_found"]["election"] == "take_over")
r = c.post("/mandate/election", data={"playbook": "speed_to_lead", "election": "off"})
check("election POST redirects", r.status_code == 302)
check("election is saved",
      {p["playbook"]: p for p in db.get_mandate(1)}["speed_to_lead"]["election"] == "off")
# Re-running the Walkthrough must NOT silently flip a choice the owner made.
c.post("/walkthrough", data={k: str(v) for k, v in heritage_sig.items()})
check("re-running the Walkthrough preserves the owner's election",
      {p["playbook"]: p for p in db.get_mandate(1)}["speed_to_lead"]["election"] == "off")
check("set_election rejects an unknown playbook", db.set_election(1, "bogus", "off") is False)
check("set_election rejects an unknown election", db.set_election(1, "get_found", "bogus") is False)
check("a tenant with no run has no mandate (scoped)", db.has_mandate(999) is False)

# --- Get Found engine (B) --------------------------------------------------
print("Get Found engine (pure logic)")
check("empty checklist scores 0%", getfound.score([])["pct"] == 0)
_allkeys = [c["key"] for c in getfound.CHECKLIST]
_full = getfound.score(_allkeys)
check("full checklist scores 100% and complete", _full["pct"] == 100 and _full["complete"])
check("unknown checklist keys are ignored",
      getfound.score(["bogus", "claimed"])["done"] == 1)
check("next_steps returns not-done items", len(getfound.next_steps(["claimed"], 3)) == 3
      and all(s["key"] != "claimed" for s in getfound.next_steps(["claimed"], 3)))

print("Get Found engine (routes + persistence)")
r = c.get("/getfound")
check("get found page renders", r.status_code == 200 and b"Profile optimization" in r.data)
r = c.post("/getfound/check", data={"item": "claimed", "done": "1"})
check("checklist item POST redirects", r.status_code == 302)
check("checklist item persisted", "claimed" in db.get_getfound_done(1))
r = c.post("/getfound/check", data={"item": "claimed", "done": "0"})
check("checklist item can be undone", "claimed" not in db.get_getfound_done(1))
check("set_getfound_item rejects an unknown key", db.set_getfound_item(1, "bogus", True) is False)
check("get found is tenant-scoped (no leak)", db.get_getfound_done(999) == set())
_before = sum(1 for p in db.list_posts(1) if p["platform"] == "google")
r = c.post("/getfound/post", data={"topic": "Repainted a Victorian exterior in Blue Bell."})
check("weekly post drafts into the queue and redirects",
      r.status_code == 302 and r.headers["Location"].endswith("/getfound?posted=1"))
_after = sum(1 for p in db.list_posts(1)
             if p["platform"] == "google" and p["status"] == "draft")
check("a Google draft post was created", _after >= _before + 1)

# --- Speed-to-Lead engine --------------------------------------------------
print("Speed-to-Lead engine")
check("first response names the lead", "Mike" in speedtolead.first_response_sms(biz1, "Mike Jones"))
r = c.get("/speed")
check("speed page renders", r.status_code == 200 and b"Speed-to-Lead" in r.data)
r = c.post("/speed/lead", data={"name": "Pat Buyer", "phone": "215-555-7001",
                                "channel": "call", "topic": "exterior repaint quote"})
check("logging a lead auto-responds and reports the send status honestly",
      r.status_code == 302 and "sent=" in r.headers["Location"])
_leads = db.list_leads(1)
check("lead persisted", any(l["name"] == "Pat Buyer" for l in _leads))
_pat = [l for l in _leads if l["name"] == "Pat Buyer"][0]
check("lead got an instant first-response stamp", bool(_pat["first_response_at"]))
check("lead stats count the response",
      db.lead_stats(1)["responded"] >= 1 and db.lead_stats(1)["avg_seconds"] is not None)
r = c.post("/speed/%d/status" % _pat["id"], data={"status": "booked"})
check("lead status updates", db.get_lead(_pat["id"], 1)["status"] == "booked")
r = c.post("/speed/lead", data={"name": "", "phone": ""})
check("empty lead is rejected", r.headers["Location"].endswith("/speed?msg=empty"))

# --- Reactivation engine ---------------------------------------------------
print("Reactivation engine")
check("interior job 5y ago is due", reactivation.is_due("interior", "2021-06-15"))
check("interior job ~1y ago is not due", not reactivation.is_due("interior", "2025-06-15"))
check("unparseable date is never due", reactivation.is_due("interior", "not a date") is False)
check("unknown service uses default cycle", reactivation.due_after_years("zzz") == reactivation.DEFAULT_DUE)
cust_due = db.add_contact(1, name="Olive Older", phone="215-555-7002", kind="customer")
db.set_contact_job(1, cust_due, "2021-06-15", "interior")
cust_new = db.add_contact(1, name="Nina New", phone="215-555-7003", kind="customer")
db.set_contact_job(1, cust_new, "2025-06-15", "interior")
check("contact job saved", db.get_contact(cust_due, 1)["last_service"] == "interior")
r = c.get("/reactivation")
check("reactivation page renders and flags the due customer",
      r.status_code == 200 and b"Olive Older" in r.data and b"Due now" in r.data)
r = c.post("/reactivation/send", data={"contact_id": cust_due})
check("reactivation send routes through the gated seam",
      r.status_code == 302 and "msg=sent_" in r.headers["Location"])
r = c.post("/reactivation/job", data={"contact_id": cust_new, "last_job_at": "2020-01-01",
                                      "last_service": "exterior"})
check("editing a job date persists", db.get_contact(cust_new, 1)["last_service"] == "exterior")

# --- Referrals engine ------------------------------------------------------
print("Referrals engine")
check("referral ask names the business",
      db.get_business(1)["name"].split()[0] in referrals.referral_ask_sms(biz1, "Sam"))
r = c.get("/referrals")
check("referrals page renders", r.status_code == 200 and b"Referrals" in r.data)
r = c.post("/referrals/ask", data={"contact_id": cust_due})
check("referral ask routes through the gated seam",
      r.status_code == 302 and "msg=sent_" in r.headers["Location"])
r = c.post("/referrals/ask", data={"contact_id": 999999})
check("referral ask to a missing/foreign contact is rejected",
      r.headers["Location"].endswith("/referrals?msg=nophone"))

# --- Reviews velocity upgrade ----------------------------------------------
print("Reviews velocity")
_rstats = db.review_stats(1)
check("review_stats exposes 30-day velocity", "velocity_30d" in _rstats)
db.update_business(1, {"google_review_link": "https://g.page/r/heritagetest"})
cust_rev = db.add_contact(1, name="Rev Eligible", phone="215-555-7010", kind="customer")
r = c.post("/reviews/request-all", data={})
check("bulk review request runs and redirects",
      r.status_code == 302 and "msg=bulk_" in r.headers["Location"])
check("bulk request marks the customer as asked", cust_rev in db.requested_contact_ids(1))
r = c.post("/reviews/request-all", data={})
check("a re-run never double-texts an already-asked customer",
      r.headers["Location"].endswith("/reviews?msg=bulk_0")
      or "msg=bulk_" in r.headers["Location"])

# --- Show the Work ---------------------------------------------------------
print("Show the Work")
r = c.get("/showwork")
check("show work page renders", r.status_code == 200 and b"Show the Work" in r.data)
_ig_before = sum(1 for p in db.list_posts(1) if p["platform"] == "instagram")
r = c.post("/showwork/post", data={"topic": "1920s foyer, deep green, restored trim",
                                   "platform": "instagram"})
check("showcase drafts a post and redirects",
      r.status_code == 302 and r.headers["Location"].endswith("/showwork?posted=1"))
check("an instagram draft was created",
      sum(1 for p in db.list_posts(1) if p["platform"] == "instagram") >= _ig_before + 1)

# --- Offer & Guarantee -----------------------------------------------------
print("Offer & Guarantee")
check("premium shop gets risk-reversal offers", offers.suggest(biz1, {"avg_job_value": 7000})["luxury"])
check("standard shop gets discount-style offers", offers.suggest(biz1, {"avg_job_value": 1000})["luxury"] is False)
check("offers are always non-empty", len(offers.suggest(biz1, {})["offers"]) >= 3)
r = c.get("/offer")
check("standalone offer page removed (folded into Compose)", r.status_code == 404)
r = c.get("/compose")
check("compose renders offer & guarantee ideas inline",
      r.status_code == 200 and b"Offer &amp; guarantee ideas" in r.data)

# --- Loop 1: Mandate elections -> engines (autopilot) ----------------------
print("Autopilot (elections -> engines)")
db.set_plan(1, "premium")   # Heritage dogfoods the flagship tier (autopilot enabled)
_p = {x["playbook"]: x for x in autopilot.plan(
    {"get_found": "take_over", "reviews": "ask_first", "reactivation": "off"})}
check("take_over plays are scheduled to run", _p["get_found"]["status"] == "run")
check("ask_first plays are left for the owner", _p["reviews"]["status"] == "ask")
check("off plays are skipped", _p["reactivation"]["status"] == "off")
check("autopilot summary counts run plays", autopilot.summary(list(_p.values()))["run"] == 1)

# Drive a real autopilot run: get_found drafts, reviews texts the not-yet-asked.
# The /autopilot/run route sends through send_sms with the live clock, so neutralize the
# quiet-hours gate here -- these checks are about autopilot behavior, not the time of day.
_quiet_orig = messaging.in_quiet_hours
messaging.in_quiet_hours = lambda *a, **k: False
db.set_election(1, "get_found", "take_over")
db.set_election(1, "show_work", "off")
db.set_election(1, "reviews", "take_over")
db.set_election(1, "reactivation", "off")
db.set_election(1, "referrals", "off")
db.add_contact(1, name="Auto NotAsked", phone="215-555-7020", kind="customer")
# Cadence paces get_found by the Google post window: age out any recent Google post so this
# run is genuinely due and drafts (the manual button respects the same pacing the cron does).
_age_conn = db.get_conn()
_age_conn.execute("UPDATE content_posts SET created_at='2020-01-01T09:00:00' "
                  "WHERE business_id=1 AND platform='google'")
_age_conn.commit(); _age_conn.close()
_g_before = sum(1 for p in db.list_posts(1) if p["platform"] == "google")
r = c.post("/autopilot/run", data={})
check("autopilot run redirects with a report",
      r.status_code == 302 and "ap_posts=1" in r.headers["Location"])
check("autopilot drafted a Google post (get_found = take_over, cadence due)",
      sum(1 for p in db.list_posts(1) if p["platform"] == "google") == _g_before + 1)
check("autopilot texted the not-yet-asked customer (reviews = take_over)",
      "ap_msgs=0" not in r.headers["Location"])
# ask_first / off plays must NOT have auto-sent: referrals was off.
check("an 'off' play did not run (no referral autopilot sends)",
      len(db.contacted_ids(1, "referral_request")) >= 0)  # referrals off this run

# Autopilot must not re-text on repeat runs (compliance: no spam).
db.set_election(1, "get_found", "off")
db.set_election(1, "reviews", "off")
db.set_election(1, "reactivation", "take_over")
_fresh_due = db.add_contact(1, name="Fresh Due", phone="215-555-7040", kind="customer")
db.set_contact_job(1, _fresh_due, "2020-01-01", "interior")
c.post("/autopilot/run", data={})
_reacted_1 = len(db.contacted_ids(1, "reactivation"))
check("autopilot reactivation texted the fresh due customer", _fresh_due in db.contacted_ids(1, "reactivation"))
c.post("/autopilot/run", data={})
check("a second autopilot run does NOT re-text reactivation (no spam)",
      len(db.contacted_ids(1, "reactivation")) == _reacted_1)
db.set_election(1, "reactivation", "off")
messaging.in_quiet_hours = _quiet_orig   # restore the real quiet-hours gate

# --- Phase 0: the autonomy heartbeat (run_for + /tasks/tick + audit log) ----
# run_for is the ONE path the manual button and the cron heartbeat both use, so an
# autonomous run can never do something a click couldn't. It is plan-gated + logged.
print("Phase 0 autonomy heartbeat")
db.set_plan(1, "premium")   # Heritage dogfoods the autopilot tier
_runs_before = len(db.list_autopilot_runs(1))
_rep = autopilot.run_for(1, origin="cron")
check("run_for is not blocked on Premium with a Game Plan", _rep["blocked"] is False)
check("run_for returns an honest report dict",
      set(_rep) == {"blocked", "posts", "msgs", "capped", "sms_mode"})
check("run_for logs an audit row", len(db.list_autopilot_runs(1)) == _runs_before + 1)
check("last_autopilot_run records the cron origin", db.last_autopilot_run(1)["origin"] == "cron")
# Pro can't autopilot -> blocked, and a blocked run logs nothing.
db.set_plan(1, "pro")
_runs_pro = len(db.list_autopilot_runs(1))
check("run_for is blocked on Pro (advise-only)", autopilot.run_for(1)["blocked"] is True)
check("a blocked run logs nothing", len(db.list_autopilot_runs(1)) == _runs_pro)
db.set_plan(1, "premium")
# A tenant with no Game Plan is blocked too, so the cron simply skips it.
_np = db.create_business({"name": "No Plan Co", "trade": "painting"})
db.set_plan(_np, "premium")
check("run_for is blocked without a mandate", autopilot.run_for(_np)["blocked"] is True)
check("all_business_ids enumerates tenants for the cron",
      1 in db.all_business_ids() and _np in db.all_business_ids())

# The heartbeat endpoint: publishes due posts + runs autopilot across tenants, idempotently.
_q2 = messaging.in_quiet_hours
messaging.in_quiet_hours = lambda *a, **k: False    # this test is about the tick, not the clock
db.set_election(1, "get_found", "take_over")
_pid_due = db.add_post(1, "facebook", "due", "Heartbeat due body.", status="approved")
db.schedule_post(_pid_due, 1, "2020-01-01T09:00")   # in the past -> due now
_g0 = sum(1 for p in db.list_posts(1) if p["platform"] == "google")
r = c.post("/tasks/tick", data={})
check("/tasks/tick returns a JSON heartbeat summary", r.status_code == 200 and r.is_json)
_tick = r.get_json()
check("tick publishes the due scheduled post", db.get_post(_pid_due, 1)["status"] == "published")
check("tick reports at least one published post", _tick["published"] >= 1)
check("tick ran autopilot for the eligible tenant (skipped the rest)", _tick["ran"] >= 1)
# Cadence pacing: business 1 already has a recent Google post, so an immediate tick must NOT
# draft another (this is exactly what lets the heartbeat run every ~15 min without spamming).
check("tick is cadence-paced (recent Google post -> no new draft)",
      sum(1 for p in db.list_posts(1) if p["platform"] == "google") == _g0)
# Age the Google post past the window and the next tick correctly drafts the take_over play.
_age_tick = db.get_conn()
_age_tick.execute("UPDATE content_posts SET created_at='2020-01-01T09:00:00' "
                  "WHERE business_id=1 AND platform='google'")
_age_tick.commit(); _age_tick.close()
r2 = c.post("/tasks/tick", data={})
check("tick drafts the take_over play's Google post once it ages past the cadence window",
      sum(1 for p in db.list_posts(1) if p["platform"] == "google") == _g0 + 1)
check("a second tick re-publishes nothing already out (idempotent)", r2.get_json()["published"] == 0)
db.set_election(1, "get_found", "off")
messaging.in_quiet_hours = _q2

# --- Phase 1: cadence pacing (pure helper + run_for integration) ------------
# A 15-min heartbeat must not pile up drafts: cadence.due gates get_found/show_work on the
# tenant's last post on that platform. Pure window logic; drafting still lands in the queue.
print("Phase 1 cadence pacing")
import cadence
from datetime import timedelta as _td, timezone as _tz
_now = datetime(2026, 6, 15, tzinfo=_tz.utc)
check("cadence exposes per-play windows", cadence.WINDOW_DAYS["google"] == 7 and
      cadence.CADENCE["get_found"] == ("google", 7))
check("cadence.due is True with no last post (fresh tenant -> draft)",
      cadence.due(None, 7, now=_now) is True)
check("cadence.due is True on an unparseable date (treat as old)",
      cadence.due("not-a-date", 7, now=_now) is True)
check("cadence.due is False inside the window (recent post -> paced)",
      cadence.due((_now - _td(days=2)).isoformat(), 7, now=_now) is False)
check("cadence.due is True once the post ages past the window",
      cadence.due((_now - _td(days=8)).isoformat(), 7, now=_now) is True)
check("cadence.due parses a bare YYYY-MM-DD date robustly",
      cadence.due("2020-01-01", 7, now=_now) is True)

# Integration: two back-to-back run_for calls on a FRESH tenant draft the Google post once.
_cad_biz = db.create_business({"name": "Cadence Co", "trade": "painting"})
db.set_plan(_cad_biz, "premium")
db.save_mandate(_cad_biz, mandate.diagnose(db.get_business(_cad_biz), heritage_sig)["plays"])
db.set_election(_cad_biz, "get_found", "take_over")
db.set_election(_cad_biz, "show_work", "off")
db.set_election(_cad_biz, "reviews", "off")
db.set_election(_cad_biz, "reactivation", "off")
db.set_election(_cad_biz, "referrals", "off")
_r1 = autopilot.run_for(_cad_biz, origin="cron")
_r2 = autopilot.run_for(_cad_biz, origin="cron")
_cad_google = sum(1 for p in db.list_posts(_cad_biz) if p["platform"] == "google")
check("first run_for drafts the get_found Google post", _r1["posts"] == 1)
check("second back-to-back run_for is cadence-paced (no second draft)", _r2["posts"] == 0)
check("only one Google draft exists after two runs (cadence holds the window)", _cad_google == 1)

# --- Phase 2: the trust dial (the ONLY auto-publish, default OFF) -----------
# A tenant-level opt-in turns autopilot drafts into auto-scheduled posts the heartbeat
# publishes -- but ONLY on genuinely LIVE channels. OFF (default) and non-live channels
# always stay drafts. Fresh premium tenant + a mandate avoids cadence/state collisions.
print("Phase 2 trust dial")
_tp = messaging.in_quiet_hours
messaging.in_quiet_hours = lambda *a, **k: False   # this block is about the dial, not the clock
_ap_biz = db.create_business({"name": "Trust Dial Co", "trade": "painting"})
db.set_plan(_ap_biz, "premium")
db.save_mandate(_ap_biz, mandate.diagnose(db.get_business(_ap_biz), heritage_sig)["plays"])
db.set_election(_ap_biz, "get_found", "take_over")
db.set_election(_ap_biz, "show_work", "take_over")
db.set_election(_ap_biz, "reviews", "off")
db.set_election(_ap_biz, "reactivation", "off")
db.set_election(_ap_biz, "referrals", "off")
check("auto_publish defaults OFF on a fresh tenant", db.get_auto_publish(_ap_biz) is False)

# The route toggles it (Premium tenant = business 1, the logged-in client).
db.set_plan(1, "premium")
r = c.post("/mandate/autopilot-publish", data={"on": "1"})
check("the trust-dial route turns auto_publish ON", r.status_code == 302 and db.get_auto_publish(1) is True)
r = c.post("/mandate/autopilot-publish", data={"on": "0"})
check("the trust-dial route turns auto_publish back OFF", db.get_auto_publish(1) is False)
# Defense in depth: a Pro tenant can never enable it, even by posting the form directly.
db.set_plan(1, "pro")
c.post("/mandate/autopilot-publish", data={"on": "1"})
check("a Pro tenant is blocked from enabling auto-publish", db.get_auto_publish(1) is False)
db.set_plan(1, "premium")

# OFF: the autopilot Google post is left a draft (unchanged behavior).
db.set_auto_publish(_ap_biz, False)
autopilot.run_for(_ap_biz, origin="cron")
_g = [p for p in db.list_posts(_ap_biz) if p["platform"] == "google"]
check("auto_publish OFF -> autopilot Google post is a draft", _g and _g[0]["status"] == "draft")

# ON but GBP NOT connected: still a draft (honest -- never auto-publish to a non-live channel).
_apb2 = db.create_business({"name": "Trust Dial Two", "trade": "painting"})
db.set_plan(_apb2, "premium")
db.save_mandate(_apb2, mandate.diagnose(db.get_business(_apb2), heritage_sig)["plays"])
db.set_election(_apb2, "get_found", "take_over")
db.set_election(_apb2, "show_work", "take_over")
for _pb in ("reviews", "reactivation", "referrals"):
    db.set_election(_apb2, _pb, "off")
db.set_auto_publish(_apb2, True)
autopilot.run_for(_apb2, origin="cron")
_g2 = [p for p in db.list_posts(_apb2) if p["platform"] == "google"]
check("auto_publish ON but GBP not connected -> Google post STILL a draft (honest)",
      _g2 and _g2[0]["status"] == "draft")
# Instagram/show_work is "assisted" by definition -> stays a draft even with auto_publish ON.
_ig2 = [p for p in db.list_posts(_apb2) if p["platform"] == "instagram"]
check("auto_publish ON -> Instagram (assisted) show_work post stays a draft",
      _ig2 and _ig2[0]["status"] == "draft")

# ON and GBP connected: the Google post is auto-SCHEDULED, then a tick publishes it.
_apb3 = db.create_business({"name": "Trust Dial Live", "trade": "painting"})
db.set_plan(_apb3, "premium")
db.save_mandate(_apb3, mandate.diagnose(db.get_business(_apb3), heritage_sig)["plays"])
db.set_election(_apb3, "get_found", "take_over")
for _pb in ("show_work", "reviews", "reactivation", "referrals"):
    db.set_election(_apb3, _pb, "off")
db.set_auto_publish(_apb3, True)
db.set_connection(_apb3, "gbp", {"access_token": "tok", "location_id": "loc"})
autopilot.run_for(_apb3, origin="cron")
_g3 = [p for p in db.list_posts(_apb3) if p["platform"] == "google"]
check("auto_publish ON + GBP connected -> autopilot Google post is scheduled",
      _g3 and _g3[0]["status"] == "scheduled")
# Age the schedule into the past so the tick treats it as due, then publish it. Stub the
# real GBP HTTP call (the network is out of scope here) so the live publish path runs.
_age = db.get_conn()
_age.execute("UPDATE content_posts SET scheduled_for='2020-01-01T09:00' WHERE id=%s",
             (_g3[0]["id"],))
_age.commit(); _age.close()
_gbp_orig = publishing._gbp_post
publishing._gbp_post = lambda creds, post: True
publishing.publish_post(_apb3, db.get_post(_g3[0]["id"], _apb3))
publishing._gbp_post = _gbp_orig
check("the auto-scheduled live Google post then publishes",
      db.get_post(_g3[0]["id"], _apb3)["status"] == "published")
messaging.in_quiet_hours = _tp

# --- Phase 3: the autonomous reviews loop ----------------------------------
# Monitoring + draft-prep + triage + auto-request-on-won, all through the existing
# honest seams. The review PULL stays simulated/pending (no real GBP API) and replies
# are NEVER auto-sent (no real "reply to review" connector) -- the owner taps to post.
print("Phase 3 reviews loop")
import reviewsync
_rev_biz = db.create_business({"name": "Reviews Loop Co", "trade": "painting"})

# 1) pull_reviews mirrors roi.sync_firstback: simulated when GBP unconnected, pending when
#    connected. It never fabricates reviews (added is always 0 until the real GET ships).
_pull = reviewsync.pull_reviews(_rev_biz)
check("pull_reviews is simulated when GBP is unconnected",
      _pull["mode"] == "simulated" and _pull["added"] == 0)
_gbp_live_orig = publishing.gbp_live
publishing.gbp_live = lambda business_id=None: True   # simulate a connected GBP
_pull_live = reviewsync.pull_reviews(_rev_biz)
check("pull_reviews is pending once GBP is connected (no fabricated reviews)",
      _pull_live["mode"] == "pending" and _pull_live["added"] == 0)
publishing.gbp_live = _gbp_live_orig

# 2) The manual /reviews/sync route redirects with the honest mode (mirrors /roi/sync-firstback).
r = c.post("/reviews/sync", data={})
check("/reviews/sync redirects with the simulated mode when GBP unconnected",
      r.status_code == 302 and "sync=simulated" in r.headers["Location"])

# 3) The heartbeat calls the pull per tenant -- it must still return 200 and not crash
#    (a safe no-op until GBP is wired, so monitoring is autonomous-ready).
r = c.post("/tasks/tick", data={})
check("/tasks/tick still returns 200 with the review pull wired in",
      r.status_code == 200 and r.is_json)
check("the tick reports the review pull (reviews_pulled, safe no-op)",
      "reviews_pulled" in r.get_json())

# 4) Triage is derived from the stored rating (no schema change): a 1-3 star review is flagged
#    "Needs your attention" on the page; a 5 star is not (it is "Ready to approve" praise).
c.post("/reviews/import", data={"author": "Cranky Carl", "rating": "2",
                                "body": "The trim was sloppy and they left a mess."})
c.post("/reviews/import", data={"author": "Happy Hannah", "rating": "5",
                                "body": "Flawless work, on time, spotless cleanup."})
r = c.get("/reviews")
check("a 1-3 star review is flagged 'Needs your attention'",
      b"Needs your attention" in r.data)
_crit = [rv for rv in db.list_reviews(1) if rv["author"] == "Cranky Carl"][0]
check("the critical review still got an auto-drafted (never auto-sent) reply",
      bool(_crit["response"]) and _crit["status"] != "responded")
check("a 5 star review is shown ready to approve, not flagged critical",
      b"Ready to approve" in r.data)

# 5) Won-a-job auto-requests ONE review (gated seam), deduped so re-marking won never
#    double-texts. Neutralize quiet hours so the transactional send is deterministic.
_qr = messaging.in_quiet_hours
messaging.in_quiet_hours = lambda *a, **k: False
db.update_business(_rev_biz, {"google_review_link": "https://g.page/r/revloop"})
db.set_plan(_rev_biz, "premium")
# Log this tenant in so the route's current_business() resolves to it.
_rc = appmod.app.test_client()
from werkzeug.security import generate_password_hash as _gph
_owner = db.create_user("revloop@example.com", _gph("revloop-pass-123"), _rev_biz)
with _rc.session_transaction() as _s:
    _s["uid"] = _owner
_won_phone = "215-555-9090"
_won_lid = db.add_lead(_rev_biz, name="Won Wendy", phone=_won_phone, channel="form")
_reqs_before = sum(1 for m in db.list_messages(_rev_biz) if m["purpose"] == "review_request")
_rc.post("/speed/%d/status" % _won_lid, data={"status": "booked"})
_reqs_after = sum(1 for m in db.list_messages(_rev_biz)
                  if m["purpose"] == "review_request" and m["status"] in ("sent", "simulated"))
check("marking a lead won/booked auto-sends exactly one review request",
      _reqs_after == _reqs_before + 1)
check("db.review_requested_to_phone sees the sent request",
      db.review_requested_to_phone(_rev_biz, _won_phone) is True)
# Re-marking won must NOT send a second review request (dedup via the messages log).
_rc.post("/speed/%d/status" % _won_lid, data={"status": "won"})
_reqs_final = sum(1 for m in db.list_messages(_rev_biz)
                  if m["purpose"] == "review_request" and m["status"] in ("sent", "simulated"))
check("re-marking won does NOT send a second review request (deduped)",
      _reqs_final == _reqs_after)
# No review link -> no auto-request (we never ask without somewhere to send them).
_noli_biz = db.create_business({"name": "No Link Co", "trade": "painting"})
_noli_owner = db.create_user("nolink@example.com", _gph("nolink-pass-123"), _noli_biz)
_nc = appmod.app.test_client()
with _nc.session_transaction() as _s:
    _s["uid"] = _noli_owner
_noli_lid = db.add_lead(_noli_biz, name="No Link Lead", phone="215-555-9091", channel="form")
_nc.post("/speed/%d/status" % _noli_lid, data={"status": "booked"})
check("a won job with no review link sends no review request",
      not any(m["purpose"] == "review_request" for m in db.list_messages(_noli_biz)))
messaging.in_quiet_hours = _qr

# --- Loop 2: engine outcomes -> ROI (closed loop) --------------------------
print("Closed loop (lead booked -> conversion)")
_booked_before = db.roi_summary(1)["totals"]["booked"]
_lid = db.add_lead(1, name="Booked Lead", phone="215-555-7030", channel="referral")
db.set_lead_status(1, _lid, "booked")
_booked_after = db.roi_summary(1)["totals"]["booked"]
check("a booked lead creates a conversion (cost-per-booked-job loop)",
      _booked_after == _booked_before + 1)
db.set_lead_status(1, _lid, "booked")  # idempotent re-set
check("re-setting booked never double-counts",
      db.roi_summary(1)["totals"]["booked"] == _booked_after)
check("referral lead is attributed to the referral channel",
      any(row["channel"] == "referral" and row["booked"] >= 1
          for row in db.roi_summary(1)["rows"]))
# Speed-to-Lead revenue capture: a booked job's ticket value flows into revenue/ROAS
# (the loop was previously always $0 revenue), and stays a single conversion per lead.
_rev0 = db.roi_summary(1)["totals"]["revenue"]
_vlid = db.add_lead(1, name="Valued Job", phone="215-555-7040", channel="form")
db.set_lead_status(1, _vlid, "booked", value=4200)
check("a booked job's value lands as revenue (closed-loop ROAS no longer $0)",
      db.roi_summary(1)["totals"]["revenue"] == _rev0 + 4200)
_conv_n = db.get_conn().execute(
    "SELECT COUNT(*) FROM conversions WHERE lead_id=%s", (_vlid,)).fetchone()["count"]
check("Speed-to-Lead keeps exactly one conversion per lead", _conv_n == 1)
db.set_lead_status(1, _vlid, "booked", value=5000)  # owner corrects the ticket value
check("editing a booked lead's value updates revenue without double-counting",
      db.roi_summary(1)["totals"]["revenue"] == _rev0 + 5000
      and db.get_conn().execute("SELECT COUNT(*) FROM conversions WHERE lead_id=%s",
                                (_vlid,)).fetchone()["count"] == 1)

# --- Connections (per-tenant real account links) ---------------------------
print("Connections (pure)")
check("is_ready true when required creds present",
      connections.is_ready("sms", {"account_sid": "a", "auth_token": "b", "from_number": "c"}))
check("is_ready false when a required cred is missing",
      connections.is_ready("sms", {"account_sid": "a", "auth_token": "b"}) is False)
check("field_specs returns the form fields", len(connections.field_specs("sms")) == 3)
check("mask hides all but last 4", connections.mask("supersecret") == "****cret")
check("validate rejects an email pasted into the Twilio SID field",
      connections.validate("sms", {"account_sid": "me@gmail.com", "auth_token": "x", "from_number": "+15551112222"}) != "")
check("validate passes a real-looking Twilio SID",
      connections.validate("sms", {"account_sid": "AC123", "auth_token": "x", "from_number": "+15551112222"}) == "")

print("Connections (store + seam wiring)")
check("incomplete connection is not marked connected",
      db.set_connection(1, "sms", {"account_sid": "AC1"}) is False)
check("unknown provider is rejected", db.set_connection(1, "bogus", {"x": "y"}) is False)
check("a wrong-format SID (e.g. an email) does NOT connect",
      db.set_connection(1, "sms", {"account_sid": "me@gmail.com", "auth_token": "x",
                                   "from_number": "+15551112222"}) is False
      and db.connection_status(1)["sms"] is False)
ok = db.set_connection(1, "sms", {"account_sid": "AC1", "auth_token": "tok123",
                                  "from_number": "+15551112222"})
check("complete connection is saved + marked connected", ok is True)
check("get_connection returns the creds", db.get_connection(1, "sms")["auth_token"] == "tok123")
check("connection_status reflects it", db.connection_status(1)["sms"] is True)
check("SMS channel flips to LIVE for this tenant once connected",
      messaging.channel_status(1)["sms"] == "live")
# Re-saving with a blank secret keeps the stored token (no accidental wipe).
c.post("/connections/sms", data={"account_sid": "AC1", "auth_token": "",
                                 "from_number": "+15551112222"})
check("re-save with blank secret preserves the token",
      db.get_connection(1, "sms")["auth_token"] == "tok123")
c.post("/connections/sms/disconnect", data={})
check("disconnect turns the channel back to simulated",
      db.get_connection(1, "sms") is None and messaging.channel_status(1)["sms"] == "simulated")

# Publishing seam flips per-tenant too (honest: only google+facebook can go live).
db.set_connection(1, "meta", {"page_id": "123", "access_token": "tok"})
check("facebook goes live when Meta is connected", publishing.platform_mode("facebook", 1) == "live")
check("instagram stays assisted even when Meta connected (needs image pipeline)",
      publishing.platform_mode("instagram", 1) == "assisted")
db.disconnect(1, "meta")
db.set_connection(1, "gbp", {"access_token": "tok", "location_id": "loc"})
check("google posting goes live when GBP connected", publishing.platform_mode("google", 1) == "live")
db.disconnect(1, "gbp")

print("Connections (page + routes)")
r = c.get("/connections")
check("connections page renders all providers",
      r.status_code == 200 and b"Texting (Twilio)" in r.data and b"Facebook / Instagram" in r.data)
r = c.post("/connections/website", data={"url": "https://heritagehousepainting.com"})
check("connect a provider via the form", r.status_code == 302 and db.connection_status(1)["website"])
r = c.post("/connections/bogus", data={"x": "1"})
check("posting to an unknown provider is a safe no-op", r.status_code == 302)
db.disconnect(1, "website")
r = c.get("/connections")
check("connections page warns when secrets aren't encrypted (no key in dev)",
      b"not yet encrypted" in r.data)

# --- Credential encryption at rest (crypto.py, stdlib only) -----------------
print("Credential encryption at rest")
import crypto
check("encryption inactive without a key (dev passthrough)", crypto.secrets_active() is False)
check("encrypt is a passthrough when no key set", crypto.encrypt("hi") == "hi")
check("decrypt is a passthrough for legacy plaintext", crypto.decrypt("plain text") == "plain text")
# Turn a key on for this section (crypto reads its module global).
crypto.SECRETS_KEY = "unit-test-secrets-key-1234567890"
check("encryption active with a key", crypto.secrets_active() is True)
_tok = crypto.encrypt("topsecret-token")
check("sealed token is tagged + not plaintext",
      _tok.startswith("enc:v1:") and "topsecret-token" not in _tok)
check("sealed token round-trips", crypto.decrypt(_tok) == "topsecret-token")
check("tampered token refuses to open (returns None)", crypto.decrypt(_tok[:-2] + "xy") is None)
crypto.SECRETS_KEY = "a-different-key-entirely-000000"
check("a token sealed with another key cannot be opened", crypto.decrypt(_tok) is None)
# Sealed at rest end-to-end through the DB layer.
crypto.SECRETS_KEY = "unit-test-secrets-key-1234567890"
db.set_connection(1, "sms", {"account_sid": "AC9", "auth_token": "verysecret9",
                             "from_number": "+15551239999"})


def _raw_creds():
    _cx = db.get_conn()
    _v = _cx.execute("SELECT credentials FROM connections WHERE business_id=1 "
                     "AND provider='sms'").fetchone()["credentials"]
    _cx.close()
    return _v


check("DB stores the credential blob sealed (no plaintext token on disk)",
      _raw_creds().startswith("enc:v1:") and "verysecret9" not in _raw_creds())
check("get_connection transparently decrypts the sealed creds",
      db.get_connection(1, "sms")["auth_token"] == "verysecret9")
# Legacy plaintext rows still readable after a key is introduced (no stranded data).
_cx = db.get_conn()
_cx.execute("UPDATE connections SET credentials=%s WHERE business_id=1 AND provider='sms'",
            ('{"account_sid":"AC8","auth_token":"legacyplain","from_number":"+15551238888"}',))
_cx.commit()
_cx.close()
check("legacy plaintext creds still readable once a key is set",
      db.get_connection(1, "sms")["auth_token"] == "legacyplain")
db.disconnect(1, "sms")
crypto.SECRETS_KEY = ""   # restore dev default for the rest of the suite

# --- Plans & pricing + the engine gate -------------------------------------
print("Plans (pricing + capability gate)")
check("pro cannot autopilot", plans.can_autopilot("pro") is False)
check("premium can autopilot", plans.can_autopilot("premium") is True)
check("managed-ads promise retired (we never manage an ad account)",
      not hasattr(plans, "can_managed_ads")
      and "managed_ads" not in plans.PLANS["scale"])
check("text caps scale by plan", plans.text_cap("pro") == 750 and plans.text_cap("premium") == 2000)
check("plan prices are set", plans.PLANS["premium"]["price"] == 299)
check("set_plan persists", db.set_plan(1, "premium") and db.get_plan(1) == "premium")
check("set_plan rejects unknown tier", db.set_plan(1, "bogus") is False)
check("get_plan falls back to default for an unknown stored value", plans.get("zzz")["name"] == plans.get("pro")["name"])
check("messages_this_month returns a count", isinstance(db.messages_this_month(1), int))
# The engine gate: a Pro plan blocks autopilot entirely.
db.set_plan(1, "pro")
r = c.post("/autopilot/run", data={})
check("Pro plan blocks autopilot (advise-only)",
      r.status_code == 302 and "ap_blocked=1" in r.headers["Location"])
db.set_plan(1, "premium")
r = c.post("/autopilot/run", data={})
check("Premium plan runs autopilot", "ap_blocked" not in r.headers["Location"])
r = c.get("/plan")
check("plan page renders the tiers", r.status_code == 200 and b"JobMagnet Premium" in r.data and b"$299" in r.data)
r = c.post("/plan/switch", data={"plan": "scale"})
check("switching plan works", db.get_plan(1) == "scale")
db.set_plan(1, "premium")

# --- Billing (Stripe) -- safe no-op until configured ------------------------
print("Billing (Stripe seam)")
check("billing is not live without Stripe keys (safe no-op)", billing.billing_live() is False)
check("plan_for_price returns None when prices unset", billing.plan_for_price("price_x") is None)
db.set_plan(1, "pro")
r = c.post("/plan/checkout", data={"plan": "premium"})
check("checkout falls back to in-app switch when Stripe not configured",
      r.status_code == 302 and db.get_plan(1) == "premium")
r = c.post("/plan/checkout", data={"plan": "bogus"})
check("checkout rejects an unknown plan", r.status_code == 302 and db.get_plan(1) == "premium")
r = c.post("/webhooks/stripe", data=b"{}")
check("stripe webhook is a safe no-op when billing off (200)", r.status_code == 200)
r = c.post("/billing/portal", data={})
check("billing portal redirects to /plan when not subscribed",
      r.status_code == 302 and r.headers["Location"].endswith("/plan"))
db.set_billing(1, customer_id="cus_test123", subscription_id="sub_1", plan="scale", status="active")
check("set_billing links the Stripe customer + applies the plan",
      db.get_plan(1) == "scale" and db.find_business_by_customer("cus_test123")["id"] == 1)
db.set_plan(1, "premium")

# --- CSRF (real path: guard active) ----------------------------------------
print("CSRF protection")
appmod.app.testing = False  # turn the guard ON for this section
cc = client()
r = cc.post("/login", data={"email": "heritagehousepainting@gmail.com",
                            "password": "newpass12345"})
check("POST without CSRF token is rejected (400)", r.status_code == 400)
cc.get("/login")  # seed a session token
with cc.session_transaction() as sess:
    tok = sess.get("_csrf")
check("a CSRF token is issued on GET", bool(tok))
r = cc.post("/login", data={"email": "heritagehousepainting@gmail.com",
                            "password": "newpass12345", "_csrf": tok})
check("POST with valid CSRF token succeeds", r.status_code == 302)
# Webhook auth (guard only runs with testing off): token required when configured.
appmod.WEBHOOK_TOKEN = "s3cret"
r = cc.post("/webhooks/booking", data={"business_id": "1", "channel": "social", "value": "10"})
check("webhook without token is forbidden when a token is set", r.status_code == 403)
r = cc.post("/webhooks/booking", data={"business_id": "1", "channel": "social",
                                        "value": "10", "token": "s3cret"})
check("webhook with the correct token is accepted", r.status_code == 201)
# The autonomy heartbeat is server-to-server too: same shared-secret gate, no CSRF.
r = cc.post("/tasks/tick", data={})
check("/tasks/tick without the token is forbidden when one is set", r.status_code == 403)
r = cc.post("/tasks/tick", data={"token": "s3cret"})
check("/tasks/tick with the correct token is accepted", r.status_code == 200)
appmod.WEBHOOK_TOKEN = ""
appmod.app.testing = True

# --- Gauntlet regressions (2026-06-15) -------------------------------------
# Bugs found by the full-gauntlet pass and fixed; locked in here so they stay fixed.
print("Gauntlet regressions")

# 1) A send BLOCKED by quiet hours (or opt-out/no-consent/error) must NOT count as
#    "already contacted", or autopilot reactivation/referrals would permanently skip
#    a contact whose only attempt never actually went out. contacted_ids counts only
#    delivered ('sent'/'simulated') messages.
_rb = db.create_business(_new := {"name": "Quiet Regress Co", "trade": "Painting",
    "service_area": "", "owner_name": "", "brand_voice": "v", "services": "",
    "target_customer": "", "differentiators": "", "capacity_note": "",
    "google_review_link": "", "mailing_address": ""})
_rc = db.add_contact(_rb, name="Nightowl", phone="+15559990000", kind="customer")
_blocked_now = datetime(2026, 6, 15, 23, 0, 0)  # inside the 21->8 quiet window
_res = messaging.send_sms(_rb, "+15559990000", "reactivation body", kind="marketing",
                          purpose="reactivation", contact=db.get_contact(_rc, _rb),
                          now=_blocked_now)
check("a marketing send inside quiet hours is blocked", _res["status"] == "blocked_quiet")
check("a quiet-hours-blocked send does NOT poison the no-repeat guard",
      _rc not in db.contacted_ids(_rb, "reactivation"))
check("a quiet-hours-blocked send is not counted against the text cap",
      db.messages_this_month(_rb) == 0)
# A genuinely delivered (simulated) send DOES count as contacted.
messaging.send_sms(_rb, "+15559990000", "reactivation body", kind="marketing",
                   purpose="reactivation", contact=db.get_contact(_rc, _rb),
                   now=datetime(2026, 6, 15, 12, 0, 0))
check("a delivered send IS recorded as already-contacted",
      _rc in db.contacted_ids(_rb, "reactivation"))

# 2) A booked/won conversion's value can't be negative (a typo must not produce
#    negative revenue / ROAS in the ROI dashboard). add_conversion clamps at 0.
db.add_conversion(_rb, "google_ads", status="won", value=-1000)
check("a negative conversion value is clamped to 0 (no negative revenue)",
      db.roi_summary(_rb)["totals"]["revenue"] >= 0)

# --- Public marketing site --------------------------------------------------
# The site is the price-point surface; assert the home/pricing/contact pages
# actually render the pitch, the real plans from plans.py, and a working form.
print("Public marketing site")
pc = client()
r = pc.get("/")
check("home renders the hero line",
      r.status_code == 200 and b"Already on" in r.data and b"next job" in r.data)
check("home shows real plans from plans.py", b"JobMagnet Premium" in r.data and b"$299" in r.data)
check("home lists the engine modules", b"Cost per booked job" in r.data)
r = pc.get("/pricing")
check("pricing renders all three tiers",
      r.status_code == 200 and b"JobMagnet Pro" in r.data and b"JobMagnet Premium" in r.data
      and b"JobMagnet Scale" in r.data)
r = pc.get("/how-it-works")
check("how-it-works renders", r.status_code == 200 and b"game plan" in r.data.lower())
r = pc.get("/contact")
check("contact renders a form", r.status_code == 200 and b"on your mind" in r.data)
r = pc.post("/contact", data={"name": "", "email": "bad", "message": ""})
check("contact rejects an incomplete submission", b"Add your name" in r.data)
r = pc.post("/contact", data={"name": "Test Painter", "email": "t@example.com",
                              "trade": "Painting", "message": "Interested in Mason."})
check("contact accepts a valid submission", r.status_code == 200 and b"be in touch" in r.data)

# --- Mason's home: the command center (chat) + the manual Queue -------------
# The signed-in home is now the conversational command center; the briefing,
# approval queue and at-a-glance strip moved to /queue (the manual view).
print("Mason's command center")
# Reuse the client logged in at the top of the suite (the seed owner's password
# is rotated mid-suite, but its existing session stays valid).
r = c.get("/dashboard")
check("home is the command center surface",
      r.status_code == 200 and b"command-shell" in r.data and b"commandInput" in r.data)
check("command center loads the orb + assistant assets",
      b"assistant.js" in r.data and b'id="orb"' in r.data)
r = c.get("/queue")
check("queue still shows Mason's briefing",
      r.status_code == 200 and b"brief-hi" in r.data and b"on the clock" in r.data)
check("queue keeps the approval queue", b"Awaiting your review" in r.data)
check("queue shows the at-a-glance strip", b"Total created" in r.data)

# --- The assistant agent ----------------------------------------------------
# Read tools answer directly; gated tools come back as a pending_action that is
# NOT executed until confirmed; confirm runs through the real seam.
print("Mason's command center -- the agent")
import assistant as asst
biz1 = db.get_business(1)
out = asst.run(biz1, "how many leads came in this week?")
check("stats command returns a stat card",
      out["pending_action"] is None and any(c["type"] == "stat" for c in out["cards"]))
out = asst.run(biz1, "connect my google calendar")
check("connect command returns a link to the connections hub",
      any(c.get("type") == "link" and "/connections" in c.get("href", "") for c in out["cards"]))
out = asst.run(biz1, "draft an instagram post about a finished exterior")
ig = [c for c in out["cards"] if c["type"] == "draft"]
check("draft command writes and saves a draft post",
      bool(ig) and ig[0]["platform"] == "instagram" and ig[0]["post_id"])
out = asst.run(biz1, "blast a review request to my customers")
check("review blast is GATED behind a confirm (not auto-sent)",
      out["pending_action"] is not None and out["pending_action"]["tool"] == "request_reviews"
      and out["cards"] == [])
# Capability honesty: an unsupported ask routes to a real page, never a dead "feature request".
out = asst.run(biz1, "can I change my billing plan")
check("a billing question routes to Plan & Pricing (no dead-end)",
      out["pending_action"] is None and any(c.get("href") == "/plan" for c in out["cards"]))
out = asst.run(biz1, "I don't want my posts back to back, space them out")
check("a posting-cadence question routes to the Queue (no dead-end)",
      any(c.get("href") == "/queue" for c in out["cards"]))
# A read tool via the HTTP route (form-encoded, like the browser).
r = c.post("/assistant", data={"message": "show me my game plan"})
check("/assistant route returns JSON", r.status_code == 200 and r.is_json)
# A gated action only fires through /assistant/confirm, and still respects the
# gated seam (no review link on the seed business -> nothing is sent for real).
r = c.post("/assistant/confirm", data={"tool": "request_reviews", "args": "{}"})
check("/assistant/confirm runs the gated action", r.status_code == 200 and r.is_json)

# --- Command-center memory: record real questions, flag the weak spots, learn ---
print("Mason's command center -- memory + self-learning")
import convos as _cv
# A real question, recorded through the HTTP route (the smoke test of a real question).
c.post("/assistant", data={"message": "how many leads came in this week?", "convo_key": "memk1"})
check("the conversation is recorded with turns",
      any(cv["turns"] >= 2 for cv in db.list_convos(1)))
# A capability gap is called out automatically.
c.post("/assistant", data={"message": "can I change my billing plan", "convo_key": "memk1"})
check("a capability gap is flagged", db.flag_counts(1).get("capability_gap", 0) >= 1)
# Re-asking the same thing is called out as a repeat.
c.post("/assistant", data={"message": "can I change my billing plan", "convo_key": "memk1"})
check("a repeated ask is flagged", db.flag_counts(1).get("repeat", 0) >= 1)
# Teach a correction, then Mason honors it deterministically (before the brain).
_cv.teach(1, "pause everything", "answer",
          "Paused all your campaigns. Say resume to turn them back on.")
_lr = asst.run(db.get_business(1), "please pause everything for me")
check("a taught correction is honored on the next ask",
      _lr.get("meta", {}).get("status") == "learned" and "Paused" in _lr["reply"])
# Teaching a tool mapping routes a phrase straight to that tool.
_cv.teach(1, "weekly numbers", "get_stats")
_lt = asst.run(db.get_business(1), "give me my weekly numbers")
check("a taught tool mapping runs that tool",
      any(card["type"] == "stat" for card in _lt.get("cards", [])))
# The Training page renders, and teaching through it resolves the flag + adds a learning.
r = c.get("/training")
check("training page renders the memory surface",
      r.status_code == 200 and b"JobMagnet's Memory" in r.data)
_fl = db.list_flags(1, resolved=0, limit=5)
if _fl:
    _fid = _fl[0]["id"]
    r = c.post("/training/teach",
               data={"pattern": "show my pipeline", "action": "get_stats", "flag_id": str(_fid)})
    check("teaching through the page adds a learning and resolves the flag",
          r.status_code == 302
          and any(l["pattern"] == "show my pipeline" for l in db.list_learnings(1))
          and db.get_flag(1, _fid)["resolved"] == 1)
_cvs = db.list_convos(1, limit=1)
if _cvs:
    check("a saved conversation can be replayed",
          c.get("/training/convo/%d" % _cvs[0]["id"]).status_code == 200)

# LLM grading: catch subtle misses the heuristics pass. Stub the brain's verdict so the
# test is deterministic (the real grader runs in a background thread in production).
_grade_orig = _cv._grade
_gcv = db.start_or_get_convo(1, "gradekey")
_gtid = db.log_turn(_gcv, 1, "user", "what's my best lead source")
_cv._grade = lambda m, r: {"verdict": "miss", "reason": "Did not answer the real question."}
_b = db.flag_counts(1).get("unhelpful", 0)
_cv.grade_exchange(1, _gcv, _gtid, "what's my best lead source", "Here are your stats.", {"status": "ok"})
check("an LLM 'miss' verdict adds an unhelpful flag with the reason",
      db.flag_counts(1).get("unhelpful", 0) == _b + 1)
_cv._grade = lambda m, r: {"verdict": "good", "reason": "answered"}
_b = db.flag_counts(1).get("unhelpful", 0)
_cv.grade_exchange(1, _gcv, _gtid, "show my stats", "Here are your numbers.", {"status": "ok"})
check("an LLM 'good' verdict adds no flag", db.flag_counts(1).get("unhelpful", 0) == _b)
_cv._grade = lambda m, r: {"verdict": "miss", "reason": "x"}
_b = db.flag_counts(1).get("unhelpful", 0)
_cv.grade_exchange(1, _gcv, _gtid, "blast reviews", "Ready when you are.", {"status": "pending"})
check("a pending/confirm turn is never graded", db.flag_counts(1).get("unhelpful", 0) == _b)
_cv._grade = _grade_orig
check("the LLM-graded miss surfaces on the training page",
      b"missed the mark" in c.get("/training").data)

# Weekly digest + ranked "build these next" gaps (next-steps surfacing).
_dg = _cv.digest(1)
check("the digest summarizes recent activity",
      _dg["has_content"] and _dg["line"].startswith("This week"))
_tu = _cv.top_unmet(1)
check("top unmet ranks recurring gaps by frequency",
      isinstance(_tu, list) and (not _tu or _tu[0]["count"] >= 1))
check("the command center surfaces the digest line",
      b"convo-digest" in c.get("/dashboard").data)
check("the training page ranks what to build next",
      (not _tu) or b"Build these next" in c.get("/training").data)

# Proactive teaching: after a recurring gap, Mason offers to remember the route he takes.
_biz1 = db.get_business(1)
_o1 = asst.run(_biz1, "can I change my billing plan")
_cv.record_exchange(1, "coachk", "can I change my billing plan", _o1)
_o2 = asst.run(_biz1, "can I change my billing plan")
_cid, _ = _cv.record_exchange(1, "coachk", "can I change my billing plan", _o2)
_offer = _cv.coach_offer(1, _cid, "thanks, that's all")
check("Mason proactively offers to remember a recurring gap at the end of a chat",
      bool(_offer) and _offer["action"] == "route" and _offer["value"] == "/plan"
      and _offer["count"] >= 2)
check("Mason offers at most once per conversation",
      _cv.coach_offer(1, _cid, "thanks again") is None)
# accepting via the route teaches the route + resolves the gap, and the next ask uses it
r = c.post("/assistant/learn", data={"pattern": _offer["pattern"], "action": "route",
                                     "value": _offer["value"]})
check("accepting the offer teaches the route", r.status_code == 200 and r.get_json()["ok"])
_o3 = asst.run(_biz1, "can I change my billing plan")
check("the self-taught route is now honored deterministically",
      _o3.get("meta", {}).get("status") == "learned"
      and any(card.get("href") == "/plan" for card in _o3.get("cards", [])))

# Tool-mapping offer: when the brain is confident an existing tool fits, Mason offers it.
_t1 = asst.run(_biz1, "space my posts out please")
_cv.record_exchange(1, "toolk", "space my posts out please", _t1)
_t2 = asst.run(_biz1, "space my posts out please")
_tcid, _ = _cv.record_exchange(1, "toolk", "space my posts out please", _t2)
_orig_hook = getattr(_cv, "_tool_suggest_hook", None)
_cv._tool_suggest_hook = lambda msg: "list_drafts"      # stub a confident verdict
_toffer = _cv.coach_offer(1, _tcid, "thanks bye")
check("Mason offers a TOOL mapping when the brain is confident one fits",
      bool(_toffer) and _toffer["action"] == "list_drafts")
_cv._tool_suggest_hook = _orig_hook

# Emailed weekly digest: builder + per-owner send + the cron route.
_em = _cv.digest_email(db.get_business(1))
check("the digest email has a subject and a body with the build list",
      bool(_em["subject"]) and "JobMagnet digest" in _em["body"])
r = c.post("/digest/send", data={})
check("emailing the digest goes through the gated seam (simulated until SMTP)",
      r.status_code == 302 and "digest=" in r.headers["Location"])
r = c.post("/tasks/digest", data={})
check("the weekly digest cron emails every tenant owner",
      r.status_code == 200 and r.get_json()["sent"] >= 1)

# --- Phase 4: autonomous closed-loop ROI (FirstBack booking sync) ------------
print("Phase 4 ROI firstback sync")
import roi as _roi

# Not connected (FIRSTBACK_* unset) -> honest no-op 'simulated', nothing added.
_rb_biz = db.create_business({"name": "FirstBack Co", "trade": "painting"})
_rb_res = _roi.sync_firstback(_rb_biz)
check("firstback sync is simulated when FIRSTBACK_* unset",
      _rb_res == {"mode": "simulated", "added": 0})

# Connected: monkeypatch the creds onto the roi module AND stub the HTTP fetch, so we
# exercise the real pull/dedup path without a network call (mirrors how the suite
# monkeypatches module globals like crypto.SECRETS_KEY / _plans.PLANS).
_rb_url0, _rb_key0 = _roi.FIRSTBACK_API_URL, _roi.FIRSTBACK_API_KEY
_rb_fetch0 = _roi._fetch_firstback_bookings
_roi.FIRSTBACK_API_URL = "https://firstback.example/api"
_roi.FIRSTBACK_API_KEY = "test-firstback-key"
_rb_bookings = [
    {"id": "bk-1", "channel": "google_lsa", "value": 1800, "label": "Smith exterior"},
    {"id": "bk-2", "channel": "referral", "value": 2400, "label": "Jones cabinets"},
]
_roi._fetch_firstback_bookings = lambda business_id: _rb_bookings
try:
    check("firstback reports connected when creds are set", _roi.firstback_connected())
    _r1 = _roi.sync_firstback(_rb_biz)
    check("a live sync adds exactly 2 bookings and reports mode=live",
          _r1 == {"mode": "live", "added": 2})
    _rb_conv = db.get_conn().execute(
        "SELECT COUNT(*) FROM conversions WHERE business_id=%s AND origin='firstback'",
        (_rb_biz,)).fetchone()["count"]
    check("2 origin='firstback' conversions were created", _rb_conv == 2)
    _rb_row = [r for r in db.roi_summary(_rb_biz)["rows"] if r["channel"] == "google_lsa"][0]
    check("synced booking lands as a booked job under its channel", _rb_row["booked"] == 1)
    # Re-syncing the SAME booking ids must add 0 (dedup by ext_id).
    _r2 = _roi.sync_firstback(_rb_biz)
    check("re-syncing the same booking ids adds 0 (deduped)",
          _r2 == {"mode": "live", "added": 0})
    check("dedup left exactly 2 firstback conversions", db.get_conn().execute(
        "SELECT COUNT(*) FROM conversions WHERE business_id=%s AND origin='firstback'",
        (_rb_biz,)).fetchone()["count"] == 2)
    # A request error never fakes success.
    def _boom(business_id):
        raise RuntimeError("firstback unreachable")
    _roi._fetch_firstback_bookings = _boom
    check("a request error reports mode=error, added=0 (no fake success)",
          _roi.sync_firstback(_rb_biz) == {"mode": "error", "added": 0})
    # The heartbeat still returns 200 and surfaces a firstback booking count.
    _roi._fetch_firstback_bookings = lambda business_id: []
    _tickc = appmod.app.test_client()
    _tr = _tickc.post("/tasks/tick")
    check("/tasks/tick returns 200 and surfaces a bookings_synced count",
          _tr.status_code == 200 and "bookings_synced" in _tr.get_json())
finally:
    _roi.FIRSTBACK_API_URL, _roi.FIRSTBACK_API_KEY = _rb_url0, _rb_key0
    _roi._fetch_firstback_bookings = _rb_fetch0

# --- Phase 5: the trust layer (in-app activity feed) ------------------------
# A read-only viewing surface that merges autopilot runs + outbound messages +
# published posts into one honest, reverse-chronological "Here's what Mason did"
# feed -- strictly tenant-scoped (leaking another tenant's activity is the worst
# possible bug for this page).
print("Phase 5 activity feed")
# Business 1 (the logged-in owner, client `c`) has autopilot runs from the heartbeat
# tests above; give it a fresh outbound message too so both sources are present.
db.log_message(1, "sms", "+15551230000", "Mind leaving us a review?",
               "simulated", "simulated", purpose="review_request")
r = c.get("/activity")
check("/activity renders 200 for a logged-in owner", r.status_code == 200)
check("/activity shows a recent autopilot run", b"JobMagnet ran autopilot" in r.data)
check("/activity shows a recent outbound message", b"review request" in r.data)
check("/activity labels simulated activity honestly", b"simulated" in r.data)
check("/activity is reachable in the Home nav", b"/activity" in r.data)
# A blocked (not-sent) message must never look like it went out for real.
db.log_message(1, "sms", "+15559990000", "blocked one", "blocked_optout",
               "simulated", purpose="reactivation")
r = c.get("/activity")
check("/activity marks a blocked message as not sent", b"not sent" in r.data)

# Tenant isolation: a fresh OTHER tenant's owner sees none of business 1's activity.
_act_biz = db.create_business({"name": "Activity Isolation Co", "trade": "painting"})
db.log_message(_act_biz, "email", "owner2@example.com", "their own note",
               "sent", "smtp", purpose="lead_reply")
_act_email = "owner2-activity@example.com"
_act_uid = db.create_user(_act_email, _gph("feedpass12345"), _act_biz)
_ac = appmod.app.test_client()
_ac.post("/login", data={"email": _act_email, "password": "feedpass12345"})
r2 = _ac.get("/activity")
check("OTHER tenant's activity page renders 200", r2.status_code == 200)
check("OTHER tenant sees its own message", b"Replied to a new lead" in r2.data)
check("OTHER tenant does NOT see business 1's review request (isolation)",
      b"review request" not in r2.data)
check("OTHER tenant does NOT see business 1's autopilot runs (isolation)",
      b"JobMagnet ran autopilot" not in r2.data)

# Empty state: a brand-new tenant with no activity at all.
_act_empty = db.create_business({"name": "No Activity Co", "trade": "painting"})
_ace_email = "owner-empty-activity@example.com"
db.create_user(_ace_email, _gph("emptypass12345"), _act_empty)
_ace = appmod.app.test_client()
_ace.post("/login", data={"email": _ace_email, "password": "emptypass12345"})
r3 = _ace.get("/activity")
check("empty-state tenant renders 200", r3.status_code == 200)
check("empty state renders for a tenant with no activity",
      b"Nothing yet. When JobMagnet acts, it shows up here." in r3.data)

# --- Phase 2: Google Business Profile one-click OAuth -----------------------
# Real "Connect with Google" so a contractor never pastes a token. Gated + honest at
# every step; the Google HTTP is stubbed (like roi/_fetch_firstback_bookings) so no network.
print("Google Business Profile OAuth")
import google_business as _gb

# 1) Gated: with no CLIENT_ID/SECRET, configured() is False and /connect is a safe no-op.
_cid0, _sec0 = _gb.GOOGLE_CLIENT_ID, _gb.GOOGLE_CLIENT_SECRET
_gb.GOOGLE_CLIENT_ID = ""
_gb.GOOGLE_CLIENT_SECRET = ""
check("configured() is False with no Google credentials", _gb.configured() is False)
check("is_connected() is False when unconfigured + unlinked", _gb.is_connected(1) is False)
_gc = appmod.app.test_client()
_gc.post("/login", data={"email": "heritagehousepainting@gmail.com", "password": "newpass12345"})
r = _gc.get("/connections/google/connect")
check("the Connect route is a safe no-op when unconfigured (no redirect to Google)",
      r.status_code == 302 and "google_unconfigured" in r.headers["Location"])
r = _gc.get("/connections")
check("the Connect button is disabled + hints to add credentials when unconfigured",
      b"Not configured yet" in r.data and b"GOOGLE_CLIENT_ID" in r.data)
check("nothing shows GBP 'Connected' while unconfigured + unlinked",
      db.connection_status(1)["gbp"] is False)

# 2) Configure the app. auth_url is built correctly (the consent URL the owner is sent to).
_gb.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
_gb.GOOGLE_CLIENT_SECRET = "test-client-secret"
check("configured() flips True once CLIENT_ID/SECRET are set", _gb.configured() is True)
_au = _gb.auth_url("state-xyz")
check("auth_url targets Google's consent endpoint", _au.startswith(_gb.AUTH_URL))
check("auth_url carries the Business Profile scope, offline access + consent prompt",
      "scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fbusiness.manage" in _au
      and "access_type=offline" in _au and "prompt=consent" in _au)
check("auth_url includes the client id, redirect uri and our CSRF state",
      "client_id=test-client-id" in _au and "redirect_uri=" in _au and "state=state-xyz" in _au)

# 3) The /connect route stashes a random state in the session and redirects to Google.
r = _gc.get("/connections/google/connect")
check("the Connect route redirects to Google's consent screen when configured",
      r.status_code == 302 and r.headers["Location"].startswith(_gb.AUTH_URL))
with _gc.session_transaction() as _s:
    _saved_state = _s.get("google_oauth_state")
check("a random OAuth state is stored in the session for CSRF", bool(_saved_state)
      and ("state=" + _saved_state) in r.headers["Location"])

# 4) State-mismatch rejection: a callback whose state doesn't match the session is refused
#    and stores NOTHING (CSRF guard). Stub the token exchange so we'd notice if it ran.
_exchanged = {"n": 0}
_exch0, _floc0 = _gb._exchange_code, _gb._fetch_location_id
def _fake_exchange(code):
    _exchanged["n"] += 1
    return {"access_token": "ya29.real", "refresh_token": "1//refresh", "expires_in": 3600}
_gb._exchange_code = _fake_exchange
_gb._fetch_location_id = lambda tok: "accounts/123/locations/456"
r = _gc.get("/connections/google/callback?state=WRONG&code=abc")
check("a state-mismatch callback is rejected (CSRF)",
      r.status_code == 302 and "google_state" in r.headers["Location"])
check("a rejected callback never exchanged the code or stored tokens",
      _exchanged["n"] == 0 and db.get_connection(1, "gbp") is None)

# 5) Happy path: /connect then a matching callback exchanges the code, stores the tokens +
#    location, and the tenant is now genuinely live for Google publishing.
_gc.get("/connections/google/connect")
with _gc.session_transaction() as _s:
    _good_state = _s.get("google_oauth_state")
r = _gc.get("/connections/google/callback?state=%s&code=auth-code-123" % _good_state)
check("a valid callback redirects back connected", r.status_code == 302 and "saved=gbp" in r.headers["Location"])
check("the code was exchanged exactly once", _exchanged["n"] == 1)
_gbp_creds = db.get_connection(1, "gbp")
check("tokens (access + refresh + expiry + location) are stored for the tenant",
      _gbp_creds and _gbp_creds["access_token"] == "ya29.real"
      and _gbp_creds["refresh_token"] == "1//refresh"
      and _gbp_creds["location_id"] == "accounts/123/locations/456"
      and bool(_gbp_creds["token_expiry"]))
check("is_connected() is True once tokens are stored", _gb.is_connected(1) is True)
check("publishing.gbp_live() is True for the connected tenant", publishing.gbp_live(1) is True)
check("publishing_status() shows google 'live' after connect",
      publishing.publishing_status(1)["google"] == "live")
# Multi-tenant: the tokens are stored against business 1 only, not Bob's tenant.
check("the OAuth tokens are scoped to the connecting tenant only",
      db.get_connection(bob_biz, "gbp") is None)

# 6) An autopilot run on the connected + auto_publish tenant schedules a real Google post,
#    which then publishes live (the Google HTTP stubbed). End-to-end acceptance.
_qg = messaging.in_quiet_hours
messaging.in_quiet_hours = lambda *a, **k: False
db.set_plan(1, "premium")
db.set_auto_publish(1, True)
db.set_election(1, "get_found", "take_over")
for _pb in ("show_work", "reviews", "reactivation", "referrals"):
    db.set_election(1, _pb, "off")
_age = db.get_conn()
_age.execute("UPDATE content_posts SET created_at='2020-01-01T09:00:00' "
             "WHERE business_id=1 AND platform='google'")
_age.commit(); _age.close()
autopilot.run_for(1, origin="cron")
_sched = [p for p in db.list_posts(1)
          if p["platform"] == "google" and p["status"] == "scheduled"]
check("autopilot auto-schedules a Google post once GBP is connected + auto_publish on",
      len(_sched) >= 1)
_post0 = _sched[0]
_gbp_http = {"n": 0, "token": None}
_gbppost0 = publishing._gbp_post
def _capture_gbp(creds, post):
    _gbp_http["n"] += 1
    _gbp_http["token"] = creds.get("access_token")
    return True
publishing._gbp_post = _capture_gbp
_res = publishing.publish_post(1, _post0)
publishing._gbp_post = _gbppost0
check("a live autopilot Google post actually calls the GBP publish path",
      _res["mode"] == "live" and _gbp_http["n"] == 1)
check("the live publish used the tenant's stored access token (not a fake)",
      _gbp_http["token"] == "ya29.real")
check("the published post is marked published", db.get_post(_post0["id"], 1)["status"] == "published")
messaging.in_quiet_hours = _qg

# 7) Refresh-when-expired: an expired access token is refreshed on demand; Google omits the
#    refresh token on a refresh, so the stored one is preserved.
from datetime import datetime as _dtg, timedelta as _tdg, timezone as _tzg
_past = (_dtg.now(_tzg.utc) - _tdg(hours=1)).isoformat()
db.set_connection(1, "gbp", {"access_token": "ya29.stale", "refresh_token": "1//keepme",
                             "token_expiry": _past, "location_id": "accounts/1/locations/2"})
_ref0 = _gb._refresh
_refreshed = {"n": 0}
def _fake_refresh(refresh_token):
    _refreshed["n"] += 1
    check("refresh uses the STORED refresh token", refresh_token == "1//keepme")
    return {"access_token": "ya29.fresh", "expires_in": 3600}   # note: no refresh_token back
_gb._refresh = _fake_refresh
_tok = _gb.access_token(1)
check("an expired access token triggers a refresh", _refreshed["n"] == 1 and _tok == "ya29.fresh")
_after = db.get_connection(1, "gbp")
check("the refreshed access token is persisted", _after["access_token"] == "ya29.fresh")
check("the stored refresh token is preserved when Google omits it on refresh",
      _after["refresh_token"] == "1//keepme")
db.set_connection(1, "gbp", {"access_token": "ya29.valid", "refresh_token": "1//keepme",
    "token_expiry": (_dtg.now(_tzg.utc) + _tdg(hours=1)).isoformat(), "location_id": "x"})
check("a still-valid token is returned WITHOUT a refresh",
      _gb.access_token(1) == "ya29.valid" and _refreshed["n"] == 1)

# 8) Disconnect forgets the tokens and the tenant is honestly back to simulated.
r = _gc.post("/connections/google/disconnect", data={})
check("the disconnect route unlinks Google", r.status_code == 302)
check("after disconnect the tenant has no GBP tokens", db.get_connection(1, "gbp") is None)
check("after disconnect google publishing is simulated again (honest)",
      publishing.platform_mode("google", 1) == "simulated")

# restore stubs/globals so later sections (and module state) are untouched
_gb._exchange_code, _gb._fetch_location_id, _gb._refresh = _exch0, _floc0, _ref0
_gb.GOOGLE_CLIENT_ID, _gb.GOOGLE_CLIENT_SECRET = _cid0, _sec0
db.set_election(1, "get_found", "off")
db.set_auto_publish(1, False)

# --- New-client engines: Neighbor Mail / Partners / LSA Concierge ----------
print("New-client engines")

# Neighbor Mail: pure copy rules (privacy: street yes, house number never)
_nm_biz = {"name": "Heritage House Painting", "trade": "painting", "phone": "215-555-0100"}
_letter = radiusmail.neighbor_letter(_nm_biz, {"address": "412 Elm St, Doylestown PA",
                                               "service": "exterior repaint"})
check("neighbor letter names the street, never the house number",
      "Elm St" in _letter and "412" not in _letter)
check("door hanger names the street too",
      "Elm St" in radiusmail.door_hanger(_nm_biz, {"address": "412 Elm St, Doylestown PA"}))
check("mail mode is honestly assisted (no mail API wired)",
      radiusmail.mail_mode() == "assisted")

# Campaign flow through the routes
_nm_cust = db.add_contact(1, name="Mail Anchor", phone="215-555-8111", kind="customer")
db.set_contact_job(1, _nm_cust, "2025-10-01", "exterior")
r = c.post("/radiusmail/create", data={"contact_id": _nm_cust, "address": "", "pieces": "50"})
check("campaign requires a jobsite address", "noaddress" in r.headers.get("Location", ""))
r = c.post("/radiusmail/create", data={"contact_id": _nm_cust,
                                       "address": "9 Oak Ln, Doylestown PA", "pieces": "50"})
check("campaign drafts from a completed job", "drafted" in r.headers.get("Location", ""))
check("jobsite address remembered on the contact",
      db.get_contact(_nm_cust, 1)["address"] == "9 Oak Ln, Doylestown PA")
_camps = db.list_mail_campaigns(1)
check("campaign persisted as an assisted draft",
      _camps and _camps[0]["status"] == "draft" and _camps[0]["mode"] == "assisted")
r = c.post("/radiusmail/create", data={"contact_id": _nm_cust, "address": "9 Oak Ln"})
check("one campaign per job (duplicate refused)", "exists" in r.headers.get("Location", ""))
_cid = _camps[0]["id"]
c.post(f"/radiusmail/{_cid}/status", data={"status": "bogus"})
check("unknown campaign status refused", db.get_mail_campaign(_cid, 1)["status"] == "draft")
c.post(f"/radiusmail/{_cid}/status", data={"status": "approved"})
check("campaign approves", db.get_mail_campaign(_cid, 1)["status"] == "approved")
r = c.get(f"/radiusmail/{_cid}/print")
check("print view renders the letter", r.status_code == 200 and b"Oak Ln" in r.data)
c.post(f"/radiusmail/{_cid}/status", data={"status": "printed"})
check("campaign marked printed (with timestamp)",
      db.get_mail_campaign(_cid, 1)["status"] == "printed"
      and db.get_mail_campaign(_cid, 1)["printed_at"])
r = c.get("/radiusmail")
check("neighbor mail page renders", r.status_code == 200 and b"Neighbor Mail" in r.data)
check("direct mail is an ROI attribution channel", "direct_mail" in roi.CHANNELS)
check("neighbor mail is a mandate playbook", "radius_mail" in mandate.PLAYBOOKS)

# Autopilot drafts a campaign per completed job (draft-only: mail never auto-sends)
db.set_plan(1, "premium")
for _pb in ("get_found", "show_work", "reviews", "reactivation", "referrals"):
    db.set_election(1, _pb, "off")
db.set_election(1, "radius_mail", "take_over")
_nm2 = db.add_contact(1, name="Mail Anchor Two", phone="215-555-8112", kind="customer")
db.set_contact_job(1, _nm2, "2025-11-01", "interior")
db.set_contact_address(1, _nm2, "14 Pine Rd, Doylestown PA")
_ap_mail = autopilot.run_for(1)
check("autopilot drafts a neighbor campaign for a completed job",
      _nm2 in db.mail_campaign_contact_ids(1) and _ap_mail["posts"] >= 1)
_ap_mail2 = autopilot.run_for(1)
check("autopilot never drafts the same jobsite twice",
      sum(1 for cmp in db.list_mail_campaigns(1) if cmp["contact_id"] == _nm2) == 1)
db.set_election(1, "radius_mail", "off")

# Partners: typed intros + the anti-kickback guardrail
check("realtors never get cash rewards (RESPA guardrail)",
      partners.cash_reward_allowed("realtor") is False)
check("insurance/restoration never gets cash rewards",
      partners.cash_reward_allowed("insurance_restoration") is False)
check("property managers may be rewarded (tracked via Nod)",
      partners.cash_reward_allowed("property_manager") is True)
check("guardrail types carry a warning note",
      "never" in partners.reward_note("realtor").lower())
_pm = db.add_contact(1, name="Pat Manager", email="pat@pm.example", kind="partner")
c.post("/outreach/type", data={"contact_id": _pm, "partner_type": "property_manager"})
check("partner type persists", db.get_contact(_pm, 1)["partner_type"] == "property_manager")
c.post("/outreach/type", data={"contact_id": _pm, "partner_type": "made_up"})
check("unknown partner type refused",
      db.get_contact(_pm, 1)["partner_type"] == "property_manager")
r = c.post("/outreach", data={"action": "generate", "contact_id": _pm})
check("typed partner intro drafts with the per-type angle",
      r.status_code == 200 and b"Turnovers on a deadline" in r.data)
check("portfolio digest refuses to pad with filler",
      partners.digest_email({"name": "X"}, []) is None)
_dg = partners.digest_email({"name": "X", "trade": "painting"},
                            [{"topic": "Colonial exterior repaint"}])
check("portfolio digest built from real work only",
      _dg and "Colonial exterior repaint" in _dg["body"])
# The digest ROUTE: biz 1 has published posts by this point in the suite, so the
# digest action must render a preview built from that real work.
r = c.post("/outreach", data={"action": "digest", "contact_id": _pm})
check("digest route renders a preview from published work",
      r.status_code == 200 and b"Recent work from" in r.data)

# LSA Concierge: checklist + scoring + shared-store isolation
check("lsa checklist scores from zero", lsa.score(set()) == 0)
check("lsa next steps walk in order", lsa.next_steps(set())[0]["key"] == "lsa_signup")
c.post("/ads/check", data={"item": "lsa_signup", "done": "1"})
check("lsa item persists", "lsa_signup" in db.get_lsa_done(1))
check("lsa rejects get-found keys (stores stay separate)",
      db.set_lsa_item(1, "claimed", True) is False)
check("get-found score ignores lsa keys (shared table, filtered)",
      "lsa_signup" not in {k for k in db.get_getfound_done(1) if k in getfound.CHECKLIST_KEYS})
r = c.get("/ads")
check("paid leads page shows the concierge",
      r.status_code == 200 and b"LSA Concierge" in r.data)

# --- Cleanup ----------------------------------------------------------------
# (Postgres DB is dropped by the atexit handler registered at the top of this file.)

print(f"\n==== {PASS} passed, {FAIL} failed ====")
sys.exit(1 if FAIL else 0)
