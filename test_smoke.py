"""End-to-end smoke test for JobMagnet v0.1.

Asserts every claim we make about the product is actually true and functional:
seed-on-boot, auth, multi-tenant isolation, the Business Brain, the Content
Engine, and the full approval loop. Uses Flask's test client (no server needed).

Run:  ./.venv/bin/python test_smoke.py
"""
import os
import sys
import tempfile

# Run against a throwaway DB and the deterministic demo brain, so the suite is
# isolated and idempotent -- it must never touch the real jobmagnet.db or depend
# on which AI provider/key happens to be configured. Set BEFORE importing config.
_TMP_DB = tempfile.NamedTemporaryFile(prefix="jobmagnet-test-", suffix=".db", delete=False)
_TMP_DB.close()
os.environ["JOBMAGNET_DB_PATH"] = _TMP_DB.name
os.environ["JOBMAGNET_PROVIDER"] = "demo"

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
check("dashboard loads when logged in", r.status_code == 200 and b"Awaiting your review" in r.data)

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
r = c.get("/dashboard")
check("draft shows in review queue with Approve", b"Approve" in r.data and b"Exterior repaint wrapped up" in r.data)
# edit
c.post(f"/posts/{pid}/edit", data={"body": "Edited body for the post."})
check("editing a draft updates the body", db.get_post(pid, 1)["body"] == "Edited body for the post.")
# approve -> publish
c.post(f"/posts/{pid}/status", data={"status": "approved"})
check("approve sets status approved", db.get_post(pid, 1)["status"] == "approved")
c.post(f"/posts/{pid}/status", data={"status": "published"})
check("mark published sets status published", db.get_post(pid, 1)["status"] == "published")
r = c.get("/dashboard")
check("dashboard shows published post", b"Published" in r.data)
# reject a second draft
db.add_post(1, "facebook", "t", "A second draft to reject.")
p2 = [p for p in db.list_posts(1) if p["status"] == "draft"][0]["id"]
c.post(f"/posts/{p2}/status", data={"status": "rejected"})
check("reject sets status rejected", db.get_post(p2, 1)["status"] == "rejected")
r = c.get("/dashboard")
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
r = cb.get("/dashboard")
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
r = c.post("/roi/sync-ringback")
check("RingBack sync is simulated when not connected",
      "sync=simulated" in r.headers.get("Location", ""))
r = c.post("/webhooks/booking", data={"business_id": "1", "channel": "google_lsa", "value": "1500"})
check("booking webhook creates a booked conversion", r.status_code == 201)
lsa = [r for r in db.roi_summary(1)["rows"] if r["channel"] == "google_lsa"][0]
check("webhook booking shows under its channel", lsa["booked"] == 1)

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
check("cold outreach page renders", r.status_code == 200 and b"Cold SMS" in r.data)
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
c.post("/cold/consent", data={"contact_id": prospect})
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
      r.status_code == 200 and b"Mason's read" in r.data and b"Get Found" in r.data)
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
check("offer page renders", r.status_code == 200 and b"Offer" in r.data)

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
db.set_election(1, "get_found", "take_over")
db.set_election(1, "show_work", "off")
db.set_election(1, "reviews", "take_over")
db.set_election(1, "reactivation", "off")
db.set_election(1, "referrals", "off")
db.add_contact(1, name="Auto NotAsked", phone="215-555-7020", kind="customer")
_g_before = sum(1 for p in db.list_posts(1) if p["platform"] == "google")
r = c.post("/autopilot/run", data={})
check("autopilot run redirects with a report",
      r.status_code == 302 and "ap_posts=1" in r.headers["Location"])
check("autopilot drafted a Google post (get_found = take_over)",
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
    "SELECT COUNT(*) FROM conversions WHERE lead_id=?", (_vlid,)).fetchone()[0]
check("Speed-to-Lead keeps exactly one conversion per lead", _conv_n == 1)
db.set_lead_status(1, _vlid, "booked", value=5000)  # owner corrects the ticket value
check("editing a booked lead's value updates revenue without double-counting",
      db.roi_summary(1)["totals"]["revenue"] == _rev0 + 5000
      and db.get_conn().execute("SELECT COUNT(*) FROM conversions WHERE lead_id=?",
                                (_vlid,)).fetchone()[0] == 1)

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
                     "AND provider='sms'").fetchone()[0]
    _cx.close()
    return _v


check("DB stores the credential blob sealed (no plaintext token on disk)",
      _raw_creds().startswith("enc:v1:") and "verysecret9" not in _raw_creds())
check("get_connection transparently decrypts the sealed creds",
      db.get_connection(1, "sms")["auth_token"] == "verysecret9")
# Legacy plaintext rows still readable after a key is introduced (no stranded data).
_cx = db.get_conn()
_cx.execute("UPDATE connections SET credentials=? WHERE business_id=1 AND provider='sms'",
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
check("scale unlocks managed ads", plans.can_managed_ads("scale") is True)
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
check("plan page renders the tiers", r.status_code == 200 and b"Mason Premium" in r.data and b"$299" in r.data)
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

# --- Cleanup ----------------------------------------------------------------
try:
    os.unlink(_TMP_DB.name)
    os.unlink(_TMP_DB.name + "-wal")
    os.unlink(_TMP_DB.name + "-shm")
except OSError:
    pass

print(f"\n==== {PASS} passed, {FAIL} failed ====")
sys.exit(1 if FAIL else 0)
