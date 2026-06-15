"""JobMagnet -- Flask app.

Run:
    python app.py
Then open http://localhost:8900 and sign in.

v0.1 -- the Content Engine + Business Brain: write platform-aware social posts in
your brand voice, review them in an approval queue, and (gated) publish. Mirrors
RingBack's structure so the two stay siblings.
"""
import hmac
import re
import secrets
from functools import wraps

from flask import (Flask, render_template, request, redirect, session, url_for, abort)
from werkzeug.security import generate_password_hash, check_password_hash

import db
import ai
import mandate
import autopilot
import plans
import getfound
import speedtolead
import reactivation
import referrals
import offers
import connections
import crypto
import billing
import messaging
import publishing
import seo
import roi
import ads
import outreach
from config import (APP_NAME, TAGLINE, DEBUG, PORT, SECRET_KEY, SESSION_COOKIE_SECURE,
                    SEED_OWNER_EMAIL, SEED_OWNER_PASSWORD, PLATFORMS, DEFAULT_PLATFORM,
                    WEBHOOK_TOKEN)

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = SESSION_COOKIE_SECURE
db.init_db()

# Seed an owner login for "client zero" (business 1 = Heritage) on first run.
if db.count_users() == 0:
    db.create_user(SEED_OWNER_EMAIL, generate_password_hash(SEED_OWNER_PASSWORD), 1)


# ---- Auth ----
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def current_user():
    uid = session.get("uid")
    return db.get_user(uid) if uid else None


def current_business():
    u = current_user()
    return db.get_business(u["business_id"]) if u else None


# ---- CSRF ----
# Lightweight, dependency-free CSRF: a per-session token echoed by every form and
# checked on every state-changing request. (Skipped under app.testing so the smoke
# suite stays terse; a dedicated test exercises the real path.)
def csrf_token():
    tok = session.get("_csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["_csrf"] = tok
    return tok


@app.before_request
def _csrf_protect():
    if app.testing or request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    if request.path.startswith("/webhooks/"):
        # Stripe webhooks authenticate by their own signature header, not our token/CSRF.
        if request.path == "/webhooks/stripe":
            return
        # other server-to-server (e.g. Twilio); authenticated by shared-secret token.
        if WEBHOOK_TOKEN and request.values.get("token") != WEBHOOK_TOKEN:
            abort(403)
        return
    sent = request.form.get("_csrf", "")
    good = session.get("_csrf", "")
    if not good or not hmac.compare_digest(str(good), str(sent)):
        abort(400)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("uid"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def _safe_next(target):
    """Only allow same-site relative redirects (never //evil.com)."""
    return (target if (target and target.startswith("/")
                       and not target.startswith("//")) else "/dashboard")


def _new_tenant_fields(name, trade):
    """A fresh tenant's Business Brain. Only name + trade come from signup; the
    rest start blank (with a generic voice) so a new plumber never inherits
    Heritage's painting profile. They fill the specifics in Settings."""
    return {
        "name": name,
        "trade": trade or "home services",
        "service_area": "",
        "owner_name": "",
        "brand_voice": ("Professional, clear, and friendly. Confident craftsmanship "
                        "without bragging. Complete sentences, no slang, no emoji, "
                        "and no dashes."),
        "services": "",
        "target_customer": "",
        "differentiators": "",
        "capacity_note": "",
        "google_review_link": "",
        "mailing_address": "",
    }


@app.context_processor
def inject_globals():
    u = current_user()
    biz = db.get_business(u["business_id"]) if u else db.get_business(1)
    return {"app_name": APP_NAME, "tagline": TAGLINE, "brain": ai.brain_mode(),
            "business": biz, "current_user": u, "platforms": PLATFORMS,
            "csrf_token": csrf_token(),
            # Sidebar shows "Start Here" until a Game Plan exists, then "Game Plan".
            "has_mandate": db.has_mandate(biz["id"]) if biz else False}


# ---- Pages ----
@app.route("/")
def index():
    return redirect("/dashboard" if session.get("uid") else "/login")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        name = (request.form.get("name") or "").strip()
        trade = (request.form.get("trade") or "").strip()
        if not _EMAIL_RE.match(email) or len(password) < 8 or not name:
            return render_template("auth.html", mode="signup",
                                   error="Enter a business name, a valid email, and an 8+ character password.")
        if db.get_user_by_email(email):
            return render_template("auth.html", mode="signup",
                                   error="That email is already registered. Try logging in.")
        # A new tenant starts blank (generic voice); they refine in Settings.
        bid = db.create_business(_new_tenant_fields(name, trade))
        uid = db.create_user(email, generate_password_hash(password), bid)
        if not uid:  # email taken in a race: don't leave an orphan logged-out tenant
            db.delete_business(bid)
            return render_template("auth.html", mode="signup",
                                   error="That email is already registered. Try logging in.")
        session["uid"] = uid
        # New tenants start with the Walkthrough so Mason can build their Game Plan
        # before anything else -- he's the front door, not the feature grid.
        return redirect("/walkthrough")
    return render_template("auth.html", mode="signup")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = db.get_user_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            session["uid"] = user["id"]
            return redirect(_safe_next(request.args.get("next")))
        return render_template("auth.html", mode="login", error="Wrong email or password.")
    return render_template("auth.html", mode="login")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/dashboard")
@login_required
def dashboard():
    biz = current_business()
    posts = db.list_posts(biz["id"])
    stats = db.content_stats(biz["id"])
    drafts = [p for p in posts if p["status"] == "draft"]
    queue = [p for p in posts if p["status"] in ("approved", "scheduled", "published")]
    now = db.now_iso()
    due_count = sum(1 for p in posts if p["status"] == "scheduled"
                    and (p["scheduled_for"] or "") <= now)
    return render_template("dashboard.html", drafts=drafts, queue=queue, stats=stats,
                           due_count=due_count, mandate_ready=db.has_mandate(biz["id"]))


@app.route("/walkthrough", methods=["GET", "POST"])
@login_required
def walkthrough():
    """Mason's onboarding interview. The answers ARE the diagnostic signals that drive
    the Mandate, so the interview writes his own guardrails."""
    biz = current_business()
    if request.method == "POST":
        raw = {k: request.form.get(k) for k in mandate.normalize_signals({})}
        signals = mandate.normalize_signals(raw)
        db.save_signals(biz["id"], signals)
        db.save_mandate(biz["id"], mandate.diagnose(biz, signals)["plays"])
        return redirect("/mandate")
    return render_template("walkthrough.html", signals=db.get_signals(biz["id"]))


@app.route("/mandate")
@login_required
def mandate_page():
    """Mason's Game Plan: the ranked, honest playbook list with each one's election.
    Empty until the Walkthrough has run."""
    biz = current_business()
    if not db.has_mandate(biz["id"]):
        return redirect("/walkthrough")
    signals = db.get_signals(biz["id"]) or {}
    plays = db.get_mandate(biz["id"])
    ap_plan = autopilot.plan({p["playbook"]: p["election"] for p in plays})
    return render_template("mandate.html", plays=plays,
                           result=mandate.diagnose(biz, signals),
                           election_labels=mandate.ELECTION_LABELS,
                           ap_summary=autopilot.summary(ap_plan),
                           can_autopilot=plans.can_autopilot(db.get_plan(biz["id"])))


@app.route("/autopilot/run", methods=["POST"])
@login_required
def autopilot_run():
    """Run every play the owner set to 'Take it over'. Each action goes through the same
    consent-gated seam / approval queue a manual click would -- autonomy inside the
    guardrails. Drafts wait for approval; sends respect consent + quiet hours + opt-out."""
    biz = current_business()
    plan = db.get_plan(biz["id"])
    if not plans.can_autopilot(plan):
        return redirect("/mandate?ap_blocked=1")     # autopilot is a Premium+ capability
    # Honor the plan's monthly text allowance.
    remaining = max(0, plans.text_cap(plan) - db.messages_this_month(biz["id"]))
    elections = {p["playbook"]: p["election"] for p in db.get_mandate(biz["id"])}
    posts = msgs = 0
    link = (biz.get("google_review_link") or "").strip()

    def _text(cu, body, kind, purpose):
        nonlocal msgs, remaining
        if remaining <= 0:
            return False
        messaging.send_sms(biz["id"], cu["phone"], body, kind=kind, purpose=purpose, contact=cu)
        msgs += 1
        remaining -= 1
        return True

    def _eligible(cu):
        return (cu.get("phone") and not cu.get("suppressed")
                and cu.get("consent_status") != "opted_out")

    for item in autopilot.plan(elections):
        if item["status"] != "run":
            continue
        pb = item["playbook"]
        if pb == "get_found":
            db.add_post(biz["id"], "google", "Weekly update",
                        ai.generate_post(biz, "", "google"), status="draft"); posts += 1
        elif pb == "show_work":
            db.add_post(biz["id"], "instagram", "Project showcase",
                        ai.generate_post(biz, "Before and after project showcase",
                                         "instagram"), status="draft"); posts += 1
        elif pb == "reviews" and link:
            asked = db.requested_contact_ids(biz["id"])
            for cu in db.list_contacts(biz["id"], kind="customer"):
                if _eligible(cu) and cu["id"] not in asked:
                    _text(cu, ai.review_request_message(biz, cu.get("name", "")) + " " + link,
                          "transactional", "review_request")
        elif pb == "reactivation":
            reacted = db.contacted_ids(biz["id"], "reactivation")
            for cu in db.list_contacts(biz["id"], kind="customer"):
                if (_eligible(cu) and cu["id"] not in reacted
                        and reactivation.is_due(cu.get("last_service"), cu.get("last_job_at"))):
                    yrs = reactivation.years_since(cu.get("last_job_at"))
                    _text(cu, reactivation.reactivation_message(biz, cu.get("name", ""),
                                                                cu.get("last_service", ""), yrs),
                          "marketing", "reactivation")
        elif pb == "referrals":
            asked = db.contacted_ids(biz["id"], "referral_request")
            for cu in db.list_contacts(biz["id"], kind="customer"):
                if _eligible(cu) and cu["id"] not in asked:
                    _text(cu, referrals.referral_ask_sms(biz, cu.get("name", "")),
                          "marketing", "referral_request")
    return redirect(f"/mandate?ap_posts={posts}&ap_msgs={msgs}")


@app.route("/mandate/election", methods=["POST"])
@login_required
def mandate_election():
    """Owner sets one play's election (take_over | ask_first | off) -- the 3 buttons
    that ARE the autonomy tiers, made per-playbook."""
    biz = current_business()
    db.set_election(biz["id"], request.form.get("playbook") or "",
                    request.form.get("election") or "")
    return redirect("/mandate")


@app.route("/getfound")
@login_required
def getfound_page():
    """Get Found: the GBP optimization checklist + the weekly-post cadence. 'Claimed'
    is not 'optimized' -- this is the work that makes an invisible shop findable."""
    biz = current_business()
    done = db.get_getfound_done(biz["id"])
    return render_template("getfound.html",
                           checklist=getfound.CHECKLIST, done=done,
                           score=getfound.score(done),
                           next_steps=getfound.next_steps(done),
                           last_gbp_post=db.last_post_at(biz["id"], "google"))


@app.route("/getfound/check", methods=["POST"])
@login_required
def getfound_check():
    biz = current_business()
    db.set_getfound_item(biz["id"], request.form.get("item") or "",
                         request.form.get("done") == "1")
    return redirect("/getfound")


@app.route("/getfound/post", methods=["POST"])
@login_required
def getfound_post():
    """Draft this week's Google Business Profile post into the approval queue (reuses
    the Content Engine + the existing approve/publish loop)."""
    biz = current_business()
    topic = (request.form.get("topic") or "").strip()
    draft = ai.generate_post(biz, topic, "google")
    db.add_post(biz["id"], "google", topic, draft, status="draft")
    return redirect("/getfound?posted=1")


@app.route("/speed")
@login_required
def speed_page():
    """Speed-to-Lead: every inbound, time-to-first-touch, and instant text-back."""
    biz = current_business()
    return render_template("speed.html", leads=db.list_leads(biz["id"]),
                           stats=db.lead_stats(biz["id"]),
                           channels=speedtolead.LEAD_CHANNELS,
                           statuses=speedtolead.LEAD_STATUSES,
                           qualify=speedtolead.QUALIFY,
                           channel_status=messaging.channel_status(biz["id"]))


@app.route("/speed/lead", methods=["POST"])
@login_required
def speed_lead():
    """Log an inbound lead and INSTANTLY auto-respond (the whole point). The text-back
    is transactional (they contacted us first) and goes through the gated seam."""
    biz = current_business()
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    channel = request.form.get("channel") or "form"
    topic = (request.form.get("topic") or "").strip()
    if not (name or phone):
        return redirect("/speed?msg=empty")
    lid = db.add_lead(biz["id"], name=name, phone=phone, channel=channel, topic=topic)
    if phone:
        res = messaging.send_sms(biz["id"], phone, speedtolead.first_response_sms(biz, name),
                                 kind="transactional", purpose="speed_to_lead")
        db.mark_lead_responded(biz["id"], lid)
        return redirect(f"/speed?sent={res['status']}")
    return redirect("/speed?msg=logged")


@app.route("/speed/<int:lead_id>/status", methods=["POST"])
@login_required
def speed_status(lead_id):
    biz = current_business()
    # An optional job value (entered when marking booked/won) feeds the closed-loop ROI.
    db.set_lead_status(biz["id"], lead_id, request.form.get("status") or "",
                       value=request.form.get("value", type=float))
    return redirect("/speed")


@app.route("/reactivation")
@login_required
def reactivation_page():
    """Reactivation: past customers and who's due on their repaint cycle."""
    biz = current_business()
    rows = []
    for cu in db.list_contacts(biz["id"], kind="customer"):
        yrs = reactivation.years_since(cu.get("last_job_at"))
        rows.append({**cu, "years": round(yrs, 1) if yrs is not None else None,
                     "due": reactivation.is_due(cu.get("last_service"),
                                                cu.get("last_job_at"))})
    return render_template("reactivation.html", customers=rows,
                           due=[r for r in rows if r["due"]],
                           services=list(reactivation.DUE_AFTER),
                           channel_status=messaging.channel_status(biz["id"]))


@app.route("/reactivation/job", methods=["POST"])
@login_required
def reactivation_job():
    biz = current_business()
    cid = request.form.get("contact_id", type=int)
    if cid and db.get_contact(cid, biz["id"]):
        db.set_contact_job(biz["id"], cid, request.form.get("last_job_at"),
                           request.form.get("last_service"))
    return redirect("/reactivation")


@app.route("/reactivation/send", methods=["POST"])
@login_required
def reactivation_send():
    """Reactivation outreach to a past customer (marketing, consent-gated)."""
    biz = current_business()
    contact = db.get_contact(request.form.get("contact_id", type=int), biz["id"])
    if not contact or not contact.get("phone"):
        return redirect("/reactivation?msg=nophone")
    yrs = reactivation.years_since(contact.get("last_job_at"))
    body = reactivation.reactivation_message(biz, contact.get("name", ""),
                                             contact.get("last_service", ""), yrs)
    res = messaging.send_sms(biz["id"], contact["phone"], body, kind="marketing",
                             purpose="reactivation", contact=contact)
    return redirect(f"/reactivation?msg=sent_{res['status']}")


@app.route("/referrals")
@login_required
def referrals_page():
    """Referrals & Plans: ask happy customers for intros (warm, consent-gated)."""
    biz = current_business()
    return render_template("referrals.html",
                           customers=db.list_contacts(biz["id"], kind="customer"),
                           pitch=referrals.maintenance_pitch(biz),
                           channel_status=messaging.channel_status(biz["id"]))


@app.route("/referrals/ask", methods=["POST"])
@login_required
def referrals_ask():
    biz = current_business()
    contact = db.get_contact(request.form.get("contact_id", type=int), biz["id"])
    if not contact or not contact.get("phone"):
        return redirect("/referrals?msg=nophone")
    res = messaging.send_sms(biz["id"], contact["phone"],
                             referrals.referral_ask_sms(biz, contact.get("name", "")),
                             kind="marketing", purpose="referral_request", contact=contact)
    return redirect(f"/referrals?msg=sent_{res['status']}")


@app.route("/showwork")
@login_required
def showwork_page():
    """Show the Work: turn real projects into social proof. Reuses the Content Engine
    + approval queue; this is the guided, before/after-focused front door to it."""
    biz = current_business()
    recent = [p for p in db.list_posts(biz["id"])
              if p["platform"] in ("instagram", "facebook")][:5]
    return render_template("showwork.html", recent=recent, image_mode=ai.image_mode())


@app.route("/showwork/post", methods=["POST"])
@login_required
def showwork_post():
    biz = current_business()
    desc = (request.form.get("topic") or "").strip()
    platform = request.form.get("platform") or "instagram"
    if platform not in PLATFORMS:
        platform = "instagram"
    topic = f"Before and after project showcase: {desc}" if desc else "Before and after project showcase"
    draft = ai.generate_post(biz, topic, platform)
    db.add_post(biz["id"], platform, topic, draft, status="draft")
    return redirect("/showwork?posted=1")


@app.route("/offer")
@login_required
def offer_page():
    """Offer & Guarantee: suggested hooks + risk-reversal, tuned to whether this is a
    premium shop (avg job value)."""
    biz = current_business()
    return render_template("offer.html",
                           offer=offers.suggest(biz, db.get_signals(biz["id"]) or {}))


@app.route("/compose", methods=["GET", "POST"])
@login_required
def compose():
    biz = current_business()
    if request.method == "POST":
        action = request.form.get("action")
        platform = request.form.get("platform") or DEFAULT_PLATFORM
        if platform not in PLATFORMS:        # never store an unknown channel
            platform = DEFAULT_PLATFORM
        topic = (request.form.get("topic") or "").strip()
        if action == "save":
            body = (request.form.get("body") or "").strip()
            if body:
                db.add_post(biz["id"], platform, topic, body, status="draft")
            return redirect("/dashboard")
        # action == "generate" (default): draft a post and show it for review.
        draft = ai.generate_post(biz, topic, platform)
        image = ai.generate_image(biz, topic, platform)
        return render_template("compose.html", topic=topic, platform=platform,
                               draft=draft, image=image)
    return render_template("compose.html", topic="", platform=DEFAULT_PLATFORM,
                           draft=None, image=None)


@app.route("/posts/<int:post_id>/status", methods=["POST"])
@login_required
def post_status(post_id):
    biz = current_business()
    status = request.form.get("status") or ""
    if status in db.POST_STATUSES:
        db.set_post_status(post_id, biz["id"], status)
    return redirect(request.form.get("next") or "/dashboard")


@app.route("/posts/<int:post_id>/edit", methods=["POST"])
@login_required
def post_edit(post_id):
    biz = current_business()
    body = (request.form.get("body") or "").strip()
    if body:
        db.update_post_body(post_id, biz["id"], body)
    return redirect("/dashboard")


@app.route("/posts/<int:post_id>/schedule", methods=["POST"])
@login_required
def post_schedule(post_id):
    """Approve a post for a future time. Expects a datetime-local value."""
    biz = current_business()
    when = (request.form.get("scheduled_for") or "").strip()
    if db.get_post(post_id, biz["id"]) and when:
        db.schedule_post(post_id, biz["id"], when)
    return redirect("/dashboard")


@app.route("/posts/<int:post_id>/publish", methods=["POST"])
@login_required
def post_publish(post_id):
    """Publish a post through the publishing seam (live / assisted / simulated)."""
    biz = current_business()
    post = db.get_post(post_id, biz["id"])
    if not post:
        return redirect("/dashboard")
    res = publishing.publish_post(biz["id"], post)
    return redirect(f"/dashboard?pub={res['mode']}&platform={res['platform']}")


@app.route("/scheduler/run", methods=["POST"])
@login_required
def scheduler_run():
    """Publish any of this tenant's scheduled posts whose time has arrived. (A cron
    can call this; for now it's a button so scheduling is real, not pretend.)"""
    biz = current_business()
    n = 0
    for post in db.due_posts():
        if post["business_id"] == biz["id"]:
            publishing.publish_post(biz["id"], post)
            n += 1
    return redirect(f"/dashboard?due={n}")


@app.route("/local", methods=["GET"])
@login_required
def local():
    biz = current_business()
    faqs = ai._parse_qa(biz.get("faq") or "")
    schema = seo.localbusiness_schema(biz, faqs=faqs or None)
    return render_template("local.html", schema=schema, faqs=faqs,
                           publishing=publishing.publishing_status(biz["id"]))


@app.route("/local/faq", methods=["POST"])
@login_required
def local_faq():
    """Generate (or clear) the AEO FAQ, stored on the Brain so the schema can embed it."""
    biz = current_business()
    if request.form.get("action") == "clear":
        db.update_business(biz["id"], {"faq": ""})
    else:
        pairs = ai.generate_faq(biz)
        db.update_business(biz["id"],
                           {"faq": "\n".join(f"Q: {q}\nA: {a}" for q, a in pairs)})
    return redirect("/local")


@app.route("/webhooks/sms", methods=["POST"])
def webhook_sms():
    """Inbound SMS/MMS webhook (Twilio-shaped). Honours STOP/START, and turns a text
    or photo from a known contact into a draft post (photo-by-text capture). Maps to a
    business by the receiving number later; defaults to business 1 for now."""
    business_id = request.form.get("business_id", type=int) or 1
    frm = (request.form.get("From") or "").strip()
    body = (request.form.get("Body") or "").strip()
    num_media = request.form.get("NumMedia", type=int) or 0
    action = messaging.handle_inbound_sms(business_id, frm, body)
    if action in ("opted_out", "opted_in"):
        return ("", 204)
    contact = db.find_contact_by_phone(business_id, frm)
    if contact and (body or num_media):
        biz = db.get_business(business_id) or {}
        topic = body or "a recent job (photo attached)"
        if num_media:
            topic += " [photo attached by text]"
        draft = ai.generate_post(biz, topic, DEFAULT_PLATFORM)
        db.add_post(business_id, DEFAULT_PLATFORM, topic, draft, status="draft")
        return ("", 201)
    return ("", 204)


@app.route("/reviews")
@login_required
def reviews():
    biz = current_business()
    return render_template("reviews.html",
                           contacts=db.list_contacts(biz["id"], kind="customer"),
                           reviews=db.list_reviews(biz["id"]),
                           stats=db.review_stats(biz["id"]),
                           channels=messaging.channel_status(biz["id"]))


@app.route("/reviews/customers", methods=["POST"])
@login_required
def reviews_add_customer():
    biz = current_business()
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    email = (request.form.get("email") or "").strip()
    if name and (phone or email):
        db.add_contact(biz["id"], name=name, phone=phone, email=email, kind="customer")
    return redirect("/reviews")


@app.route("/reviews/request", methods=["POST"])
@login_required
def reviews_request():
    """Send a past customer a review invite (SMS) through the gated seam. Honest:
    simulated until Twilio is connected. Needs a Google review link in Settings."""
    biz = current_business()
    contact = db.get_contact(request.form.get("contact_id", type=int), biz["id"])
    link = (biz.get("google_review_link") or "").strip()
    if not contact or not contact.get("phone"):
        return redirect("/reviews?msg=nophone")
    if not link:
        return redirect("/reviews?msg=nolink")
    body = ai.review_request_message(biz, contact.get("name", "")) + " " + link
    res = messaging.send_sms(biz["id"], contact["phone"], body,
                             kind="transactional", purpose="review_request",
                             contact=contact)
    return redirect(f"/reviews?msg=sent_{res['status']}")


@app.route("/reviews/request-all", methods=["POST"])
@login_required
def reviews_request_all():
    """Velocity: ask every eligible customer who hasn't been asked yet (no double-texts,
    skips opt-outs/suppressed). Transactional, gated seam. We never 'gate' reviews -- ask
    everyone, route nobody away from leaving an honest review."""
    biz = current_business()
    link = (biz.get("google_review_link") or "").strip()
    if not link:
        return redirect("/reviews?msg=nolink")
    asked = db.requested_contact_ids(biz["id"])
    n = 0
    for cu in db.list_contacts(biz["id"], kind="customer"):
        if (cu.get("phone") and not cu.get("suppressed")
                and cu.get("consent_status") != "opted_out" and cu["id"] not in asked):
            body = ai.review_request_message(biz, cu.get("name", "")) + " " + link
            messaging.send_sms(biz["id"], cu["phone"], body, kind="transactional",
                               purpose="review_request", contact=cu)
            n += 1
    return redirect(f"/reviews?msg=bulk_{n}")


@app.route("/reviews/import", methods=["POST"])
@login_required
def reviews_import():
    """Add a review by hand (until the Google Business Profile API is connected,
    monitoring is manual). Drafts an AI response immediately."""
    biz = current_business()
    author = (request.form.get("author") or "").strip()
    body = (request.form.get("body") or "").strip()
    source = request.form.get("source") or "google"
    try:
        rating = max(1, min(5, int(request.form.get("rating") or 5)))
    except ValueError:
        rating = 5
    if body:
        rid = db.add_review(biz["id"], source, author, rating, body)
        draft = ai.generate_review_response(biz, db.get_review(rid, biz["id"]))
        db.set_review_response(rid, biz["id"], draft, mark_responded=False)
    return redirect("/reviews")


@app.route("/reviews/<int:review_id>/respond", methods=["POST"])
@login_required
def reviews_respond(review_id):
    biz = current_business()
    action = request.form.get("action")
    if action == "regenerate":
        review = db.get_review(review_id, biz["id"])
        if review:
            draft = ai.generate_review_response(biz, review)
            db.set_review_response(review_id, biz["id"], draft, mark_responded=False)
        return redirect("/reviews")
    response = (request.form.get("response") or "").strip()
    if response:
        db.set_review_response(review_id, biz["id"], response, mark_responded=True)
    return redirect("/reviews")


@app.route("/contacts")
@login_required
def contacts_page():
    biz = current_business()
    return render_template("contacts.html", contacts=db.list_contacts(biz["id"]),
                           kinds=db.CONTACT_KINDS, channels=messaging.channel_status(biz["id"]))


@app.route("/contacts/add", methods=["POST"])
@login_required
def contacts_add():
    biz = current_business()
    name = (request.form.get("name") or "").strip()
    kind = request.form.get("kind") or "customer"
    if name:
        db.add_contact(biz["id"], name=name,
                       phone=(request.form.get("phone") or "").strip(),
                       email=(request.form.get("email") or "").strip(), kind=kind)
    return redirect("/contacts")


@app.route("/contacts/import", methods=["POST"])
@login_required
def contacts_import():
    """Bulk import: one contact per line as 'name, phone, email'."""
    biz = current_business()
    kind = request.form.get("kind") or "customer"
    n = 0
    for line in (request.form.get("rows") or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if parts and parts[0]:
            db.add_contact(biz["id"], name=parts[0],
                           phone=parts[1] if len(parts) > 1 else "",
                           email=parts[2] if len(parts) > 2 else "", kind=kind)
            n += 1
    return redirect(f"/contacts?imported={n}")


@app.route("/contacts/<int:contact_id>/suppress", methods=["POST"])
@login_required
def contacts_suppress(contact_id):
    biz = current_business()
    c = db.get_contact(contact_id, biz["id"])
    if c:
        db.set_contact_suppressed(biz["id"], contact_id, not c.get("suppressed"))
    return redirect("/contacts")


@app.route("/ads", methods=["GET", "POST"])
@login_required
def ads_page():
    biz = current_business()
    revenue = request.values.get("revenue", type=float)
    budget = ads.recommend_budget(revenue) if revenue else None
    adcopy = ai.generate_ad_copy(biz) if (request.method == "POST"
                                          and request.form.get("action") == "copy") else None
    return render_template("ads.html", budget=budget, adcopy=adcopy,
                           revenue=revenue or "")


@app.route("/outreach", methods=["GET", "POST"])
@login_required
def outreach_page():
    """B2B partner cold email. Generate a draft for a partner, then send it through
    the CAN-SPAM-compliant, consent-gated email seam (simulated until SMTP is set)."""
    biz = current_business()
    preview = None
    if request.method == "POST" and request.form.get("action") == "generate":
        contact = db.get_contact(request.form.get("contact_id", type=int), biz["id"])
        if contact:
            email = ai.generate_cold_email(biz, contact)
            preview = {"contact": contact, "subject": email["subject"], "body": email["body"]}
    return render_template("outreach.html",
                           partners=db.list_contacts(biz["id"], kind="partner"),
                           preview=preview, channels=messaging.channel_status(biz["id"]),
                           can_spam=outreach.can_spam_ready(biz))


@app.route("/outreach/send", methods=["POST"])
@login_required
def outreach_send():
    biz = current_business()
    if not outreach.can_spam_ready(biz):
        return redirect("/outreach?msg=noaddr")
    contact = db.get_contact(request.form.get("contact_id", type=int), biz["id"])
    subject = (request.form.get("subject") or "").strip()
    body = (request.form.get("body") or "").strip()
    if not contact or not contact.get("email") or not subject or not body:
        return redirect("/outreach?msg=incomplete")
    full_body = body + outreach.footer(biz, contact["id"])
    res = messaging.send_email(biz["id"], contact["email"], subject, full_body,
                               kind="marketing", purpose="cold_email", contact=contact)
    return redirect(f"/outreach?msg=sent_{res['status']}")


@app.route("/cold")
@login_required
def cold_page():
    """Cold SMS / voice -- hard-gated. The page is mostly about the compliance posture
    (our moat): it stays disabled until a TCPA attorney signs off, and even then each
    contact needs written consent."""
    biz = current_business()
    leads = [c for c in db.list_contacts(biz["id"]) if c["kind"] in ("partner", "lead")]
    return render_template("cold.html", leads=leads,
                           sms_enabled=messaging.cold_sms_enabled(),
                           voice_enabled=messaging.cold_voice_enabled(),
                           channels=messaging.channel_status(biz["id"]))


@app.route("/cold/consent", methods=["POST"])
@login_required
def cold_consent():
    """Record prior express WRITTEN consent for a contact (the TCPA requirement for
    cold marketing SMS). In production this captures the signed proof; here it records
    the consent event in the ledger."""
    biz = current_business()
    contact = db.get_contact(request.form.get("contact_id", type=int), biz["id"])
    if contact:
        db.set_contact_consent(biz["id"], contact["id"], "sms", "granted",
                               source="written consent recorded in app")
    return redirect("/cold")


@app.route("/cold/sms", methods=["POST"])
@login_required
def cold_sms_send():
    biz = current_business()
    contact = db.get_contact(request.form.get("contact_id", type=int), biz["id"])
    body = (request.form.get("body") or "").strip()
    if not contact or not contact.get("phone") or not body:
        return redirect("/cold?msg=incomplete")
    res = messaging.send_cold_sms(biz["id"], contact["phone"], body, contact=contact)
    return redirect(f"/cold?msg={res['status']}")


@app.route("/unsubscribe/<int:contact_id>")
def unsubscribe(contact_id):
    """Public opt-out landing (CAN-SPAM). No login: the recipient clicks this. The link
    carries an HMAC token bound to the contact id, so the endpoint can't be enumerated to
    opt out contacts who never got an email."""
    wrap = "<p style='font-family:sans-serif;max-width:30rem;margin:4rem auto'>"
    if not crypto.verify_id("unsub", contact_id, request.args.get("t")):
        return (wrap + "This unsubscribe link is invalid or incomplete. If you keep "
                "receiving emails, reply STOP and we'll remove you.</p>", 400)
    contact = db.get_contact(contact_id)
    if contact:
        db.set_contact_consent(contact["business_id"], contact_id, "email",
                               "opted_out", source="email unsubscribe link")
    return (wrap + "You have been unsubscribed and will not receive further emails. "
            "Thank you.</p>")


@app.route("/roi")
@login_required
def roi_dashboard():
    biz = current_business()
    return render_template("roi.html", summary=db.roi_summary(biz["id"]),
                           channels=roi.CHANNELS, labels=roi.CHANNEL_LABELS,
                           ringback_connected=roi.ringback_connected())


@app.route("/roi/spend", methods=["POST"])
@login_required
def roi_spend():
    biz = current_business()
    channel = request.form.get("channel") or "other"
    if channel not in roi.CHANNELS:
        channel = "other"
    try:
        amount = float(request.form.get("amount") or 0)
    except ValueError:
        amount = 0
    if amount > 0:
        db.add_spend(biz["id"], channel, amount, note=(request.form.get("note") or "").strip())
    return redirect("/roi")


@app.route("/roi/conversion", methods=["POST"])
@login_required
def roi_conversion():
    """Log a booked/won job and the channel that sourced it (the closed loop)."""
    biz = current_business()
    channel = request.form.get("channel") or "other"
    if channel not in roi.CHANNELS:
        channel = "other"
    status = request.form.get("status") or "won"
    if status not in ("lead", "booked", "won", "lost"):
        status = "won"
    try:
        value = float(request.form.get("value") or 0)
    except ValueError:
        value = 0
    db.add_conversion(biz["id"], channel, status=status, value=value,
                      label=(request.form.get("label") or "").strip())
    return redirect("/roi")


@app.route("/roi/sync-ringback", methods=["POST"])
@login_required
def roi_sync_ringback():
    biz = current_business()
    res = roi.sync_ringback(biz["id"])
    return redirect(f"/roi?sync={res['mode']}&added={res['added']}")


@app.route("/webhooks/booking", methods=["POST"])
def webhook_booking():
    """External booking event (e.g. a RingBack push) -> a booked-job conversion."""
    business_id = request.form.get("business_id", type=int) or 1
    channel = request.form.get("channel") or "other"
    if channel not in roi.CHANNELS:
        channel = "other"
    try:
        value = float(request.form.get("value") or 0)
    except ValueError:
        value = 0
    db.add_conversion(business_id, channel, status="booked", value=value,
                      label=(request.form.get("label") or "").strip(), origin="webhook")
    return ("", 201)


@app.route("/plan")
@login_required
def plan_page():
    """Plan & pricing: the tiers, what each unlocks, and the tenant's current plan."""
    biz = current_business()
    return render_template("plan.html", plans=plans.PLANS, order=plans.ORDER,
                           current=db.get_plan(biz["id"]),
                           billing_live=billing.billing_live(),
                           subscribed=bool(biz.get("stripe_customer_id")))


@app.route("/plan/switch", methods=["POST"])
@login_required
def plan_switch():
    """Dev/fallback: switch plan in-app. Disabled once Stripe is live so a plan change
    can't bypass payment, it must go through checkout."""
    biz = current_business()
    if billing.billing_live():
        return redirect("/plan")
    db.set_plan(biz["id"], request.form.get("plan") or "")
    return redirect("/plan?switched=1")


@app.route("/plan/checkout", methods=["POST"])
@login_required
def plan_checkout():
    """Start real Stripe Checkout for a plan. Falls back to an in-app switch when Stripe
    isn't configured, so the button always does something sensible."""
    biz = current_business()
    plan = request.form.get("plan") or ""
    if plan not in plans.PLANS:
        return redirect("/plan")
    if not billing.billing_live():
        db.set_plan(biz["id"], plan)
        return redirect("/plan?switched=1")
    base = request.url_root.rstrip("/")
    try:
        url = billing.create_checkout_url(biz, plan, base + "/plan?switched=1", base + "/plan")
    except Exception as e:
        print(f"[jobmagnet] stripe checkout failed: {e}", flush=True)
        return redirect("/plan?billing_err=1")
    return redirect(url)


@app.route("/billing/portal", methods=["POST"])
@login_required
def billing_portal():
    """Open Stripe's Customer Portal so the tenant manages/cancels their own subscription."""
    biz = current_business()
    if billing.billing_live() and biz.get("stripe_customer_id"):
        try:
            return redirect(billing.create_portal_url(biz, request.url_root.rstrip("/") + "/plan"))
        except Exception as e:
            print(f"[jobmagnet] stripe portal failed: {e}", flush=True)
    return redirect("/plan")


@app.route("/webhooks/stripe", methods=["POST"])
def webhook_stripe():
    """Stripe subscription events keep the tenant's plan in sync (verified by signature)."""
    if not billing.billing_live():
        return ("", 200)
    try:
        info = billing.parse_event(request.get_data(), request.headers.get("Stripe-Signature", ""))
    except Exception:
        return ("", 400)              # bad signature / unparseable
    if not info:
        return ("", 200)
    bid = info.get("business_id") or 0
    if not bid and info.get("customer_id"):
        b = db.find_business_by_customer(info["customer_id"])
        bid = b["id"] if b else 0
    if bid:
        db.set_billing(bid, customer_id=info.get("customer_id"),
                       subscription_id=info.get("subscription_id"),
                       plan=info.get("plan"), status=info.get("status"))
    return ("", 200)


@app.route("/connections")
@login_required
def connections_page():
    """The Connections hub: link real accounts so Mason actually acts (texts, posts,
    pulls reviews) instead of simulating. Honest status per provider."""
    biz = current_business()
    status = db.connection_status(biz["id"])
    providers = []
    for pid, meta in connections.PROVIDERS.items():
        creds = db.get_connection(biz["id"], pid) or {}
        fields = []
        for f in connections.field_specs(pid):
            val = creds.get(f["key"], "")
            fields.append({**f, "display": connections.mask(val) if f["secret"] else val})
        providers.append({"id": pid, "label": meta["label"], "kind": meta["kind"],
                          "blurb": meta["blurb"], "connected": status.get(pid, False),
                          "fields": fields})
    return render_template("connections.html", providers=providers,
                           secrets_active=crypto.secrets_active())


@app.route("/connections/<provider>", methods=["POST"])
@login_required
def connections_save(provider):
    biz = current_business()
    if provider in connections.PROVIDERS:
        existing = db.get_connection(biz["id"], provider) or {}
        creds = {}
        for f in connections.field_specs(provider):
            submitted = (request.form.get(f["key"]) or "").strip()
            # Keep a stored secret if the (masked) field was left blank on re-save.
            if f["secret"] and not submitted and existing.get(f["key"]):
                creds[f["key"]] = existing[f["key"]]
            else:
                creds[f["key"]] = submitted
        db.set_connection(biz["id"], provider, creds)
        return redirect(f"/connections?saved={provider}")
    return redirect("/connections")


@app.route("/connections/<provider>/disconnect", methods=["POST"])
@login_required
def connections_disconnect(provider):
    biz = current_business()
    if provider in connections.PROVIDERS:
        db.disconnect(biz["id"], provider)
    return redirect("/connections")


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    biz = current_business()
    saved = False
    if request.method == "POST":
        fields = {k: (request.form.get(k) or "").strip() for k in
                  ("name", "trade", "service_area", "owner_name", "brand_voice",
                   "services", "target_customer", "differentiators", "capacity_note",
                   "google_review_link", "mailing_address")}
        db.update_business(biz["id"], fields)
        biz = current_business()
        saved = True
    return render_template("settings.html", business=biz, saved=saved)


@app.route("/settings/password", methods=["POST"])
@login_required
def settings_password():
    u = current_user()
    current = request.form.get("current_password") or ""
    new = request.form.get("new_password") or ""
    if (check_password_hash(u["password_hash"], current) and len(new) >= 8):
        db.update_user_password(u["id"], generate_password_hash(new))
        return redirect("/settings?pw=ok")
    return redirect("/settings?pw=err")


if __name__ == "__main__":
    print(f"{APP_NAME} -- {TAGLINE}")
    print(f"Brain: {ai.brain_mode()}  ·  http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG, use_reloader=False)
