"""JobMagnet -- Flask app.

Run:
    python app.py
Then open http://localhost:8900 and sign in.

v0.1 -- the Content Engine + Business Brain: write platform-aware social posts in
your brand voice, review them in an approval queue, and (gated) publish. Mirrors
FirstBack's structure so the two stay siblings.
"""
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from flask import (Flask, render_template, request, redirect, session, abort,
                   jsonify)
from werkzeug.security import generate_password_hash, check_password_hash

import db
import ai
import assistant
import convos
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
import google_business
import firstwin
import billing
import messaging
import publishing
import posting
import seo
import roi
import reviewsync
import ads
import lsa
import partners
import radiusmail
import outreach
from config import (APP_NAME, TAGLINE, DEBUG, PORT, SECRET_KEY, SESSION_COOKIE_SECURE,
                    SEED_OWNER_EMAIL, SEED_OWNER_PASSWORD, PLATFORMS, DEFAULT_PLATFORM,
                    WEBHOOK_TOKEN, EMAIL_LIVE)
from routes import register_blueprints

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = SESSION_COOKIE_SECURE
register_blueprints(app)
db.init_db()

# Wire the command-center memory into the assistant without an import cycle: the router
# consults taught corrections (convos.lookup) before the brain, and folds the tenant's
# confirmed corrections into its routing prompt (convos.learnings_for_prompt).
assistant._learning_lookup = convos.lookup
assistant._learning_examples_hook = convos.learnings_for_prompt
# When a gap recurs, let JobMagnet check if a real tool now fits it (proactive self-teaching).
convos._tool_suggest_hook = assistant.suggest_tool_for

# Seed an owner login for "client zero" (business 1 = Heritage) on first run.
if db.count_users() == 0:
    db.create_user(SEED_OWNER_EMAIL, generate_password_hash(SEED_OWNER_PASSWORD), 1)


# ---- Auth ----  (kernel: current_user/current_business/login_required/_safe_next/
# _EMAIL_RE live in auth.py — edit trades_core/auth.py, then run trades_core/sync.py)
from auth import current_user, current_business, login_required, _safe_next, _EMAIL_RE


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
    if request.path.startswith("/webhooks/") or request.path.startswith("/tasks/"):
        # Stripe webhooks authenticate by their own signature header, not our token/CSRF.
        if request.path == "/webhooks/stripe":
            return
        # other server-to-server (webhooks, the digest cron); shared-secret token, no CSRF.
        # Fail CLOSED: an unset token must never leave these state-changing endpoints
        # open to anonymous callers. Constant-time compare.
        if not WEBHOOK_TOKEN or not hmac.compare_digest(
                str(request.values.get("token", "")), str(WEBHOOK_TOKEN)):
            abort(403)
        return
    sent = request.form.get("_csrf", "")
    good = session.get("_csrf", "")
    if not good or not hmac.compare_digest(str(good), str(sent)):
        abort(400)


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


# ---- Section navigation ----
# Each sidebar group, as ordered (href, label) tabs. Rendered as a horizontal
# tab bar at the top of every signed-in page so you can switch between the tools
# in a section without going back to the sidebar. Single source of truth.
NAV_SECTIONS = [
    ("Home", [("/dashboard", "Command Center"), ("/queue", "Queue"),
              ("/mandate", "Game Plan"), ("/activity", "Activity"),
              ("/training", "Memory")]),
    ("Get Found", [("/getfound", "Get Found"), ("/reviews", "Reviews"),
                   ("/showwork", "Show Work"), ("/compose", "Compose"),
                   ("/local", "Local SEO")]),
    ("Win the Job", [("/speed", "Speed-to-Lead"), ("/reactivation", "Reactivation"),
                     ("/referrals", "Referrals")]),
    ("New Clients", [("/radiusmail", "Neighbor Mail"), ("/outreach", "Partners"),
                     ("/ads", "Paid Leads")]),
    ("My Business", [("/plan", "Plan & Pricing"), ("/connections", "Connections"),
                     ("/roi", "Results"), ("/contacts", "Contacts"),
                     ("/settings", "Business Brain")]),
]


def _section_for(path):
    """Return (section_name, tabs, active_href) for the current path, or blanks
    for pages that aren't in a section (e.g. the public site)."""
    if path.startswith("/walkthrough"):  # the Walkthrough lives under Game Plan
        path = "/mandate"
    for name, items in NAV_SECTIONS:
        for href, _label in items:
            if path == href or path.startswith(href + "/"):
                return name, items, href
    return None, [], None


@app.context_processor
def inject_globals():
    u = current_user()
    biz = db.get_business(u["business_id"]) if u else db.get_business(1)
    _sec = _section_for(request.path)
    return {"app_name": APP_NAME, "tagline": TAGLINE, "brain": ai.brain_mode(),
            "business": biz, "current_user": u, "platforms": PLATFORMS,
            "csrf_token": csrf_token(), "year": datetime.now().year,
            # Theme preference (cookie, default dark) — rendered server-side so the
            # correct theme paints on first load with no flash.
            "theme": request.cookies.get("jm_theme", "dark"),
            # Section tab bar (the current group's sibling pages).
            "section_name": _sec[0], "section_tabs": _sec[1], "section_active": _sec[2],
            # Sidebar shows "Start Here" until a Game Plan exists, then "Game Plan".
            "has_mandate": db.has_mandate(biz["id"]) if biz else False}


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
        # New tenants start with the Walkthrough so JobMagnet can build their Game Plan
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


def _briefing(biz, stats, drafts, due_count, mandate_ready, signals=None):
    """JobMagnet's morning brief — derived only from real state, never fabricated.
    Returns the greeting, a one-line status, and the single thing to do today."""
    hour = datetime.now().hour
    part = "Morning" if hour < 12 else ("Afternoon" if hour < 17 else "Evening")
    owner = (biz.get("owner_name") or "").strip()
    hello = f"{part}, {owner.split()[0]}." if owner else f"{part}."

    n_draft = stats.get("draft", 0)
    if not mandate_ready:
        line = ("I'm ready when you are. Run the walkthrough and I'll build your game plan, "
                "tell you what to do first, and what to skip.")
        todo = ("Run the walkthrough", "/walkthrough")
    elif due_count:
        line = (f"{due_count} scheduled post{'s' if due_count != 1 else ''} "
                f"{'are' if due_count != 1 else 'is'} due to go out. Say the word.")
        todo = ("Review what's going out", "#queue")
    elif n_draft:
        line = (f"I wrote {n_draft} post{'s' if n_draft != 1 else ''} for you. "
                f"{'They' if n_draft != 1 else 'It'} need your okay before "
                f"{'they' if n_draft != 1 else 'it'} go{'' if n_draft != 1 else 'es'} out.")
        todo = (f"Approve {n_draft} draft{'s' if n_draft != 1 else ''}", "#review")
    else:
        line = "I am lining up your next posts. Nothing needs you right now."
        todo = ("Write something new", "/compose")
    passed_on = None
    if signals and mandate_ready:
        result = mandate.diagnose(biz, signals)
        not_yet = [p for p in result["plays"] if p["applicability"] == "not_yet"]
        if not_yet:
            play = not_yet[0]
            passed_on = {"label": play["label"], "reason": play["reason"][:100]}
    return {"hello": hello, "line": line, "todo_label": todo[0], "todo_href": todo[1],
            "awaiting": n_draft, "passed_on": passed_on}


def first_win_block(business_id):
    """Assemble the command-center first-win block. State machine:
    in_progress -> achieved_uncelebrated (first time a real outcome is seen)
    -> achieved_celebrated (after one view)."""
    biz = db.get_business(business_id) or {}
    facts = db.first_win_facts(business_id)
    won = firstwin.achieved(facts)
    milestone = db.get_milestone(business_id)

    # days since signup (created_at is UTC ISO text; guard naive timestamps too)
    days = 0
    if biz.get("created_at"):
        try:
            created = datetime.fromisoformat(biz["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            days = max(0, (datetime.now(timezone.utc) - created).days)
        except (ValueError, TypeError):
            days = 0

    if won:
        if not milestone:
            db.mark_milestone_achieved(business_id, won)
            return {"state": "achieved_uncelebrated", "win": won, "achieved_win": won,
                    "label": firstwin.WINS.get(won, {}).get("label", "First win"),
                    "cta_route": None, "nudge": "", "days_since_signup": days}
        if not milestone.get("celebrated"):
            db.mark_milestone_celebrated(business_id)
            return {"state": "achieved_celebrated", "win": milestone["achieved_win"],
                    "achieved_win": milestone["achieved_win"],
                    "label": firstwin.WINS.get(milestone["achieved_win"], {}).get("label", "First win"),
                    "cta_route": None, "nudge": "", "days_since_signup": days}
        return {"state": "achieved_celebrated", "win": milestone["achieved_win"],
                "achieved_win": milestone["achieved_win"],
                "label": firstwin.WINS.get(milestone["achieved_win"], {}).get("label", "First win"),
                "cta_route": None, "nudge": "", "days_since_signup": days}

    # not yet achieved -> designate a reachable win
    signals = db.get_signals(business_id)
    live = {"sms_live": messaging.sms_live(business_id),
            "gbp_connected": google_business.is_connected(business_id)}
    win = firstwin.designate(signals, live, biz)
    meta = firstwin.WINS[win]
    return {"state": "in_progress", "win": win, "achieved_win": None,
            "label": meta["label"], "cta_route": meta["cta_route"],
            "nudge": firstwin.nudge_copy(win, days), "days_since_signup": days}


@app.route("/dashboard")
@login_required
def dashboard():
    """The signed-in home is now JobMagnet's command center: an AI control surface where the
    owner runs the whole product by conversation. The card-based view still lives at
    /queue for working by hand."""
    biz = current_business()
    db.write_login_at(session.get("uid"))
    mason_alert = biz.get("mason_alert")
    if request.args.get("clear") == "mason_alert":
        conn = db.get_conn()
        conn.execute("UPDATE businesses SET mason_alert=NULL, mason_alert_at=NULL WHERE id=%s",
                     (biz["id"],))
        conn.commit()
        conn.close()
        return redirect("/dashboard")
    stats = db.content_stats(biz["id"])
    mandate_ready = db.has_mandate(biz["id"])
    posts = db.list_posts(biz["id"])
    drafts = [p for p in posts if p["status"] == "draft"]
    now = db.now_iso()
    due_count = sum(1 for p in posts if p["status"] == "scheduled"
                    and (p["scheduled_for"] or "") <= now)
    signals = db.get_signals(biz["id"])
    activation_funnel = db.activation_funnel_counts() if biz["id"] == 1 else None
    brief = _briefing(biz, stats, drafts, due_count, mandate_ready, signals=signals)
    return render_template("command.html", brief=brief, stats=stats,
                           mandate_ready=mandate_ready,
                           digest=convos.digest(biz["id"]),
                           suggestions=assistant.suggestions(),
                           first_win=first_win_block(biz["id"]),
                           mason_alert=mason_alert,
                           activation_funnel=activation_funnel)


@app.route("/queue")
@login_required
def queue():
    """The manual view: JobMagnet's morning brief, the approval queue, and the schedule.
    Everything the command center can do by chat, you can still do here by hand."""
    biz = current_business()
    posts = db.list_posts(biz["id"])
    stats = db.content_stats(biz["id"])
    drafts = [p for p in posts if p["status"] == "draft"]
    queue_items = [p for p in posts if p["status"] in ("approved", "scheduled", "published")]
    now = db.now_iso()
    due_count = sum(1 for p in posts if p["status"] == "scheduled"
                    and (p["scheduled_for"] or "") <= now)
    mandate_ready = db.has_mandate(biz["id"])
    brief = _briefing(biz, stats, drafts, due_count, mandate_ready,
                      signals=db.get_signals(biz["id"]))
    return render_template("dashboard.html", drafts=drafts, queue=queue_items, stats=stats,
                           due_count=due_count, mandate_ready=mandate_ready, brief=brief,
                           first_win=first_win_block(biz["id"]))


@app.route("/assistant", methods=["POST"])
@login_required
def assistant_chat():
    """One natural-language turn against JobMagnet's command center. Form-encoded (so the
    existing CSRF gate applies unchanged); returns the reply, any inline cards, and an
    optional pending_action that needs an explicit confirm before it runs."""
    biz = current_business()
    message = (request.form.get("message") or "").strip()
    try:
        history = json.loads(request.form.get("history") or "[]")
        if not isinstance(history, list):
            history = []
    except (ValueError, TypeError):
        history = []
    out = assistant.run(biz, message, history[-12:])
    # Record the exchange + auto-flag the weak spots (so we can learn from them later).
    if message:
        convo_id, _ = convos.record_exchange(biz["id"], request.form.get("convo_key", ""),
                                             message, out)
        # At a natural close, let JobMagnet proactively offer to remember a recurring gap.
        out["coach"] = convos.coach_offer(biz["id"], convo_id, message)
    return jsonify(out)


@app.route("/assistant/confirm", methods=["POST"])
@login_required
def assistant_confirm():
    """Run a gated action the owner just approved (publish, review blast, autopilot).
    The action still flows through the same consent/publishing seams a button would."""
    biz = current_business()
    tool = (request.form.get("tool") or "").strip()
    try:
        args = json.loads(request.form.get("args") or "{}")
        if not isinstance(args, dict):
            args = {}
    except (ValueError, TypeError):
        args = {}
    out = assistant.execute(biz, tool, args)
    convos.record_exchange(biz["id"], request.form.get("convo_key", ""),
                           f"[confirmed: {tool}]", out)
    return jsonify(out)


@app.route("/assistant/learn", methods=["POST"])
@login_required
def assistant_learn():
    """Accept JobMagnet's proactive teaching offer: store the learning + resolve the gap."""
    biz = current_business()
    pattern = (request.form.get("pattern") or "").strip()
    action = (request.form.get("action") or "route").strip()
    value = (request.form.get("value") or "").strip()
    if pattern:
        convos.accept_coach(biz["id"], pattern, action, value)
    return jsonify({"ok": bool(pattern)})


# ---- JobMagnet's Memory / Training: review conversations, call out issues, teach ----
_ISSUE_LABEL = {"capability_gap": "No tool was available for this",
                "empty": "A tool returned nothing", "repeat": "You had to re-ask",
                "negative": "You pushed back on the answer",
                "unhelpful": "The answer missed the mark"}


@app.route("/training")
@login_required
def training():
    """What JobMagnet has heard, where he fell short, and what you've taught him. The owner
    turns a flagged exchange into a learning JobMagnet honors next time."""
    biz = current_business()
    return render_template("training.html",
                           flags=db.list_flags(biz["id"], resolved=0, limit=40),
                           counts=db.flag_counts(biz["id"]),
                           convos=db.list_convos(biz["id"], limit=12),
                           learnings=db.list_learnings(biz["id"]),
                           digest=convos.digest(biz["id"]),
                           top_unmet=convos.top_unmet(biz["id"]),
                           tools=sorted(assistant.TOOLS.keys()),
                           issue_label=_ISSUE_LABEL)


@app.route("/training/convo/<int:convo_id>")
@login_required
def training_convo(convo_id):
    """Replay one saved conversation (tenant-scoped)."""
    biz = current_business()
    turns = db.get_convo_turns(convo_id, biz["id"])
    if not turns:
        return redirect("/training")
    return render_template("training_convo.html", convo_id=convo_id, turns=turns)


@app.route("/training/teach", methods=["POST"])
@login_required
def training_teach():
    """Teach JobMagnet a correction from a flagged exchange (and resolve the flag)."""
    biz = current_business()
    pattern = (request.form.get("pattern") or "").strip()
    action = (request.form.get("action") or "").strip()
    value = (request.form.get("value") or "").strip()
    if not pattern or not action:
        return redirect("/training")
    # action is a tool name, or 'route' (value = page path), or 'answer' (value = reply text)
    if action in assistant.TOOLS:
        convos.teach(biz["id"], pattern, action)
    elif action in ("route", "answer"):
        convos.teach(biz["id"], pattern, action, answer=value)
    flag_id = request.form.get("flag_id")
    if flag_id and flag_id.isdigit():
        db.resolve_flag(biz["id"], int(flag_id))
    return redirect("/training?taught=1")


@app.route("/training/resolve", methods=["POST"])
@login_required
def training_resolve():
    """Dismiss a flag without teaching anything."""
    biz = current_business()
    flag_id = request.form.get("flag_id")
    if flag_id and flag_id.isdigit():
        db.resolve_flag(biz["id"], int(flag_id))
    return redirect("/training")


@app.route("/activity")
@login_required
def activity():
    """The trust layer: a reverse-chronological, honest feed of everything JobMagnet did
    for THIS tenant -- autopilot runs, outbound messages, and published posts -- so the
    owner can see (and never be misled about) what went out on its own vs simulated.
    Read-only: it never changes how anything runs or sends."""
    biz = current_business()
    bid = biz["id"]
    events = []

    # 1) Autopilot runs (Phase 0 audit log): drafts created, messages sent, sends paced.
    for run in db.list_autopilot_runs(bid, limit=50):
        bits = [f"{run['posts']} draft(s)", f"{run['msgs']} message(s)"]
        if run["capped"]:
            bits.append(f"{run['capped']} paced")
        origin = "on its own" if run.get("origin") == "cron" else "you ran it"
        events.append({
            "created_at": run.get("created_at"),
            "icon": "autopilot",
            "label": "Autopilot",
            "desc": f"JobMagnet ran autopilot: {', '.join(bits)} ({origin}).",
            "tag": None if (run.get("sms_mode") or "simulated") == "live" else "simulated",
        })

    # 2) Outbound messages: honest per purpose and delivery status.
    for m in db.list_messages(bid, limit=50):
        if (m.get("direction") or "outbound") != "outbound":
            continue
        purpose = {
            "review_request": "Sent a review request",
            "reactivation": "Reached out to win back a past customer",
            "referral": "Sent a referral ask",
            "lead_reply": "Replied to a new lead",
            "cold_email": "Sent a cold outreach email",
            "digest": "Emailed your activity digest",
        }.get(m.get("purpose") or "", "Sent a message")
        status = m.get("status") or ""
        if status == "sent":
            tag = None
        elif status == "simulated":
            tag = "simulated"
        else:  # blocked_optout / blocked_quiet / blocked_no_consent / paced / error
            tag = "not sent"
        events.append({
            "created_at": m.get("created_at"),
            "icon": "message",
            "label": "Message",
            "desc": f"{purpose} by {m.get('channel') or 'message'}.",
            "tag": tag,
        })

    # 3) Published posts: honest publish_mode (live / assisted / simulated).
    for p in db.list_posts(bid, status="published"):
        mode = p.get("publish_mode") or "simulated"
        tag = None if mode == "live" else mode
        events.append({
            "created_at": p.get("decided_at") or p.get("created_at"),
            "icon": "post",
            "label": "Post",
            "desc": f"Published to {p.get('platform') or 'a channel'}.",
            "tag": tag,
        })

    # Merge reverse-chronological and cap. created_at is ISO so string sort is correct.
    events.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    events = events[:50]

    return render_template("activity.html",
                           events=events,
                           digest=convos.digest(bid))


@app.route("/digest/send", methods=["POST"])
@login_required
def digest_send():
    """Email this owner their weekly digest now, through the gated email seam (honest
    simulated-vs-live until SMTP is configured)."""
    biz = current_business()
    user = current_user()
    em = convos.digest_email(biz)
    res = messaging.send_email(biz["id"], user["email"], em["subject"], em["body"],
                               kind="transactional", purpose="digest")
    return redirect(f"/training?digest={res['status']}")


@app.route("/tasks/digest", methods=["POST"])
def tasks_digest():
    """The weekly-digest cron: email every tenant's owner their digest. Token-gated
    (JOBMAGNET_WEBHOOK_TOKEN); a scheduler hits this once a week."""
    sent = 0
    for bid, email in db.all_owner_recipients():
        biz = db.get_business(bid)
        em = convos.digest_email(biz)
        messaging.send_email(bid, email, em["subject"], em["body"],
                             kind="transactional", purpose="digest")
        sent += 1
    return jsonify({"sent": sent})


@app.route("/tasks/tick", methods=["POST"])
def tasks_tick():
    """The autonomy heartbeat. A scheduler hits this on an interval; token-gated
    (JOBMAGNET_WEBHOOK_TOKEN), idempotent, and multi-tenant. For every tenant it
      1. publishes any scheduled posts whose time has arrived, and
      2. runs the take_over plays through the same consent-gated seams the buttons use.
    Safe to call repeatedly: due_posts only returns still-scheduled posts, and the
    no-repeat guards + caps keep sends from doubling. See SETUP_NEEDED (Scheduler cron).

    NOTE (Phase 0): until Phase 1 adds content cadence, get_found/show_work draft a fresh
    post each run, so run this hourly+ (not every few minutes) for now."""
    published = 0
    for post in db.due_posts():
        publishing.publish_post(post["business_id"], post)
        published += 1
    ran = posts = msgs = capped = pulled = booked = 0
    for bid in db.all_business_ids():
        # Monitor reviews (autonomous-ready; a safe no-op until GBP is connected, then
        # it ingests + drafts + triages new reviews automatically). Mirrors roi sync.
        pulled += reviewsync.pull_reviews(bid)["added"]
        # Closed-loop ROI (Phase 4): pull booked jobs from FirstBack into conversions.
        # A safe no-op (mode 'simulated', added 0) until FIRSTBACK_* is configured; deduped
        # by ext_id so repeated ticks never double-count the same booking.
        booked += roi.sync_firstback(bid)["added"]

        # P2-14: Monday stall-detection — take_over election with 0 autopilot output
        # in 7 days -> set mason_alert so the dashboard amber callout surfaces it.
        if datetime.now().weekday() == 0:
            _conn = db.get_conn()
            _take_over_count = _conn.execute(
                "SELECT COUNT(*) FROM playbook_elections "
                "WHERE business_id=%s AND election='take_over'",
                (bid,)).fetchone()["count"]
            _seven_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            _activity_row = _conn.execute(
                "SELECT COALESCE(SUM(posts + msgs), 0) AS total FROM autopilot_runs "
                "WHERE business_id=%s AND created_at >= %s",
                (bid, _seven_ago)).fetchone()
            _activity = int(_activity_row["total"]) if _activity_row else 0
            if _take_over_count > 0 and _activity == 0:
                _conn.execute(
                    "UPDATE businesses SET mason_alert=%s, mason_alert_at=%s WHERE id=%s",
                    ("JobMagnet has not been able to run any content in 7 days. "
                     "Check your settings.", db.now_iso(), bid))
                _conn.commit()
            _conn.close()

        # P0-3 stage-aware re-engagement (after Monday stall block).
        _biz_row = db.get_business(bid) or {}
        _walkthrough_started = _biz_row.get("walkthrough_started_at")
        if _walkthrough_started:
            try:
                _started_dt = datetime.fromisoformat(_walkthrough_started)
                if _started_dt.tzinfo is None:
                    _started_dt = _started_dt.replace(tzinfo=timezone.utc)
                _hours_since = (datetime.now(timezone.utc) - _started_dt).total_seconds() / 3600
            except (ValueError, TypeError):
                _hours_since = 0
            _has_mandate = db.has_mandate(bid)
            _milestone = db.get_milestone(bid)
            if (_has_mandate and not (_milestone and _milestone.get("achieved_at"))
                    and _hours_since > 168 and (messaging.sms_live(bid) or EMAIL_LIVE)):
                # Stage 2: has mandate, no first win, > 7 days since walkthrough start.
                _signals = db.get_signals(bid) or {}
                _live_state = {"sms_live": messaging.sms_live(bid),
                               "gbp_connected": google_business.is_connected(bid)}
                _win = firstwin.designate(_signals, _live_state, _biz_row)
                _nudge = firstwin.WINS.get(_win, {}).get(
                    "nudge", "Your next win is waiting. Finish your first play.")
                if EMAIL_LIVE:
                    _econn = db.get_conn()
                    _erow = _econn.execute(
                        "SELECT email FROM users WHERE business_id=%s LIMIT 1",
                        (bid,)).fetchone()
                    _econn.close()
                    if _erow:
                        messaging.send_email(bid, _erow["email"],
                                             "JobMagnet: your next win is waiting", _nudge,
                                             kind="transactional", purpose="reengagement")
            elif (not _has_mandate and _hours_since > 48
                  and (messaging.sms_live(bid) or EMAIL_LIVE)):
                # Stage 1: started walkthrough, no mandate elected, > 48h ago.
                _nudge1 = ("You started your game plan. Finish the walkthrough and JobMagnet "
                           "will tell you exactly what to do first.")
                if EMAIL_LIVE:
                    _econn1 = db.get_conn()
                    _erow1 = _econn1.execute(
                        "SELECT email FROM users WHERE business_id=%s LIMIT 1",
                        (bid,)).fetchone()
                    _econn1.close()
                    if _erow1:
                        messaging.send_email(bid, _erow1["email"],
                                             "JobMagnet: finish your game plan", _nudge1,
                                             kind="transactional", purpose="reengagement")

        rep = autopilot.run_for(bid, origin="cron")
        if rep["blocked"]:
            continue
        ran += 1
        posts += rep["posts"]; msgs += rep["msgs"]; capped += rep["capped"]
    return jsonify({"ok": True, "published": published, "ran": ran,
                    "posts": posts, "msgs": msgs, "capped": capped,
                    "reviews_pulled": pulled, "bookings_synced": booked})


@app.route("/walkthrough", methods=["GET", "POST"])
@login_required
def walkthrough():
    """JobMagnet's onboarding interview. The answers ARE the diagnostic signals that drive
    the Mandate, so the interview writes his own guardrails."""
    biz = current_business()
    if request.method == "POST":
        raw = {k: request.form.get(k) for k in mandate.normalize_signals({})}
        signals = mandate.normalize_signals(raw)
        db.save_signals(biz["id"], signals)
        db.save_mandate(biz["id"], mandate.diagnose(biz, signals)["plays"])
        # P1-5 + P1-10 + P2-19: capture Brain/editable columns in one consolidated call.
        brain = {f: request.form.get(f, "").strip()
                 for f in ("capacity_note", "success_metric", "brief_format")
                 if request.form.get(f, "").strip()}
        if brain:
            db.update_business(biz["id"], brain)
        # P2-16: auto-generate AEO FAQ when designate() picks aeo_faq as the first win.
        live_state = {"sms_live": messaging.sms_live(biz["id"]),
                      "gbp_connected": google_business.is_connected(biz["id"])}
        if firstwin.designate(signals, live_state, biz) == "aeo_faq":
            pairs = ai.generate_faq(biz)
            faq_text = "\n".join(f"Q: {q}\nA: {a}" for q, a in pairs)
            db.update_business(biz["id"], {"faq": faq_text})
            biz_name = (biz.get("name") or "").strip()
            raw_slug = re.sub(r"[^a-z0-9]+", "-", biz_name.lower()).strip("-") if biz_name else ""
            biz_slug = raw_slug or str(biz["id"])
            _sconn = db.get_conn()
            _sconn.execute(
                "UPDATE businesses SET biz_slug=%s WHERE id=%s "
                "AND (biz_slug IS NULL OR biz_slug='')",
                (biz_slug, biz["id"]))
            _sconn.commit()
            _sconn.close()
        return redirect("/mandate")
    # P0-3: record when this tenant first opens the Walkthrough (idempotent).
    db.set_walkthrough_started(biz["id"])
    return render_template("walkthrough.html", signals=db.get_signals(biz["id"]))


@app.route("/mandate")
@login_required
def mandate_page():
    """JobMagnet's Game Plan: the ranked, honest playbook list with each one's election.
    Empty until the Walkthrough has run."""
    biz = current_business()
    if not db.has_mandate(biz["id"]):
        return redirect("/walkthrough")
    signals = db.get_signals(biz["id"]) or {}
    plays = db.get_mandate(biz["id"])
    ap_plan = autopilot.plan({p["playbook"]: p["election"] for p in plays})
    # P2-13: extract result to a named var so we can build reconciliation_note.
    result = mandate.diagnose(biz, signals)
    BOTTLENECK_MAP = {"not_enough_leads": "paid", "no_reviews": "reviews",
                      "win_back_customers": "reactivation", "see_ai_first": "get_found"}
    contractor_play = BOTTLENECK_MAP.get(biz.get("bottleneck_priority", "") or "")
    top_applies = [p for p in result["plays"] if p["applicability"] == "applies"]
    top_play_key = top_applies[0]["key"] if top_applies else None
    reconciliation_note = (
        f'JobMagnet sees {top_applies[0]["label"]} as the top play, but you flagged '
        f'{contractor_play} as the bottleneck. Both are on.'
        if contractor_play and top_play_key and contractor_play != top_play_key else None)
    elections_updated_at = max(
        (p.get("updated_at", "") for p in plays if p.get("updated_at")), default=None)
    return render_template("mandate.html", plays=plays,
                           result=result,
                           election_labels=mandate.ELECTION_LABELS,
                           ap_summary=autopilot.summary(ap_plan),
                           can_autopilot=plans.can_autopilot(db.get_plan(biz["id"])),
                           auto_publish=db.get_auto_publish(biz["id"]),
                           last_run=db.last_autopilot_run(biz["id"]),
                           bottleneck_priority=biz.get("bottleneck_priority"),
                           reconciliation_note=reconciliation_note,
                           elections_updated_at=elections_updated_at,
                           biz_slug=biz.get("biz_slug"),
                           faq=biz.get("faq"))


@app.route("/autopilot/run", methods=["POST"])
@login_required
def autopilot_run():
    """Run every play the owner set to 'Take it over'. Delegates to autopilot.run_for --
    the SAME code path the cron heartbeat (/tasks/tick) uses -- so manual and autonomous
    runs are identical and both flow through the consent-gated seam / approval queue.
    Drafts wait for approval; sends respect consent + quiet hours + opt-out."""
    biz = current_business()
    rep = autopilot.run_for(biz["id"], origin="manual")
    if rep["blocked"]:
        return redirect("/mandate?ap_blocked=1")     # autopilot is a Premium+ capability
    return redirect(f"/mandate?ap_posts={rep['posts']}&ap_msgs={rep['msgs']}"
                    f"&ap_sms={rep['sms_mode']}"
                    + (f"&ap_capped={rep['capped']}" if rep["capped"] else ""))


@app.route("/mandate/election", methods=["POST"])
@login_required
def mandate_election():
    """Owner sets one play's election (take_over | ask_first | off) -- the 3 buttons
    that ARE the autonomy tiers, made per-playbook."""
    biz = current_business()
    db.set_election(biz["id"], request.form.get("playbook") or "",
                    request.form.get("election") or "")
    return redirect("/mandate")


@app.route("/mandate/autopilot-publish", methods=["POST"])
@login_required
def mandate_autopilot_publish():
    """The trust dial (Phase 2): owner opts in to let JobMagnet auto-schedule & publish
    autopilot content -- but only on connected (live) channels; everything else still
    drafts for approval. Premium+ only; defense in depth so a Pro tenant can never
    enable it even by posting the form directly."""
    biz = current_business()
    if plans.can_autopilot(db.get_plan(biz["id"])):
        db.set_auto_publish(biz["id"], request.form.get("on") == "1")
    return redirect("/mandate")


@app.route("/mandate/bottleneck", methods=["POST"])
@login_required
def mandate_bottleneck():
    """P2-13: Contractor states their bottleneck so JobMagnet can frame the Mandate relative
    to what they feel the problem is. Written via direct UPDATE (lifecycle col, not
    _BUSINESS_COLS, so Settings form can never accidentally erase it)."""
    bottleneck_priority = (request.form.get("bottleneck_priority") or "").strip()
    biz = current_business()
    conn = db.get_conn()
    conn.execute("UPDATE businesses SET bottleneck_priority=%s WHERE id=%s",
                 (bottleneck_priority, biz["id"]))
    conn.commit()
    conn.close()
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
        # Only count the lead as auto-responded if the text actually went out (live or
        # simulated-delivery). A blocked send (opt-out) shouldn't show as "Responded".
        if res.get("status") in ("sent", "simulated"):
            db.mark_lead_responded(biz["id"], lid)
        return redirect(f"/speed?sent={res['status']}")
    return redirect("/speed?msg=logged")


@app.route("/speed/<int:lead_id>/status", methods=["POST"])
@login_required
def speed_status(lead_id):
    biz = current_business()
    status = request.form.get("status") or ""
    # An optional job value (entered when marking booked/won) feeds the closed-loop ROI.
    db.set_lead_status(biz["id"], lead_id, status,
                       value=request.form.get("value", type=float))
    # A won job is the perfect moment to ask for a review. When the lead just landed in a
    # won state, has a phone, and we have a review link, send ONE invite through the gated
    # seam (consent + caps respected there). Deduped so re-marking won never double-texts.
    if status in ("won", "booked"):
        lead = db.get_lead(lead_id, biz["id"])
        link = (biz.get("google_review_link") or "").strip()
        phone = (lead or {}).get("phone")
        if lead and link and phone and not db.review_requested_to_phone(biz["id"], phone):
            contact = db.find_contact_by_phone(biz["id"], phone)
            body = ai.review_request_message(biz, lead.get("name", "")) + " " + link
            messaging.send_sms(biz["id"], phone, body, kind="transactional",
                               purpose="review_request", contact=contact)
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


@app.route("/compose", methods=["GET", "POST"])
@login_required
def compose():
    """Compose. The Offer & Guarantee suggestions (offers.py) render inline here —
    the standalone /offer page was folded in so hooks sit next to the copy they
    should strengthen."""
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
            return redirect("/queue")
        # action == "generate" (default): draft a post and show it for review.
        draft = ai.generate_post(biz, topic, platform)
        image = ai.generate_image(biz, topic, platform)
        return render_template("compose.html", topic=topic, platform=platform,
                               draft=draft, image=image,
                               offer=offers.suggest(biz, db.get_signals(biz["id"]) or {}))
    return render_template("compose.html", topic="", platform=DEFAULT_PLATFORM,
                           draft=None, image=None,
                           offer=offers.suggest(biz, db.get_signals(biz["id"]) or {}))


@app.route("/posts/<int:post_id>/status", methods=["POST"])
@login_required
def post_status(post_id):
    biz = current_business()
    status = request.form.get("status") or ""
    if status in db.POST_STATUSES:
        db.set_post_status(post_id, biz["id"], status)
    return redirect(request.form.get("next") or "/queue")


@app.route("/posts/<int:post_id>/edit", methods=["POST"])
@login_required
def post_edit(post_id):
    biz = current_business()
    body = (request.form.get("body") or "").strip()
    if body:
        db.update_post_body(post_id, biz["id"], body)
    return redirect("/queue")


@app.route("/posts/<int:post_id>/schedule", methods=["POST"])
@login_required
def post_schedule(post_id):
    """Approve a post for a future time. Expects a datetime-local value. The posting
    guardrail keeps the publish out of quiet hours and from stacking on another post,
    adjusting the time and saying so honestly."""
    biz = current_business()
    when = (request.form.get("scheduled_for") or "").strip()
    adjusted = ""
    if db.get_post(post_id, biz["id"]) and when:
        try:
            dt, changed, reason = posting.safe_schedule_time(
                biz["id"], datetime.fromisoformat(when))
            when = dt.strftime("%Y-%m-%dT%H:%M")
            adjusted = reason if changed else ""
        except ValueError:
            pass  # unparseable -> store as given (old behavior)
        db.schedule_post(post_id, biz["id"], when)
    if adjusted:
        return redirect(f"/queue?sched={quote(adjusted)}&when={quote(when)}")
    return redirect("/queue")


@app.route("/posts/<int:post_id>/publish", methods=["POST"])
@login_required
def post_publish(post_id):
    """Publish a post through the publishing seam (live / assisted / simulated)."""
    biz = current_business()
    post = db.get_post(post_id, biz["id"])
    if not post:
        return redirect("/queue")
    res = publishing.publish_post(biz["id"], post)
    return redirect(f"/queue?pub={res['mode']}&platform={res['platform']}")


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
    return redirect(f"/queue?due={n}")


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
        # P2-15: close the MMS loop — reply to the sender so they know the draft is ready.
        if messaging.sms_live(business_id):
            messaging.send_sms(business_id, frm,
                               "Draft post from your job photo is ready. Review it at /queue.",
                               kind="transactional", purpose="photo_post_reply")
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
                           channels=messaging.channel_status(biz["id"]),
                           gbp_connected=reviewsync.gbp_connected(biz["id"]))


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
    n = capped = 0
    for cu in db.list_contacts(biz["id"], kind="customer"):
        if (cu.get("phone") and not cu.get("suppressed")
                and cu.get("consent_status") != "opted_out" and cu["id"] not in asked):
            body = ai.review_request_message(biz, cu.get("name", "")) + " " + link
            r = messaging.send_sms(biz["id"], cu["phone"], body, kind="transactional",
                                   purpose="review_request", contact=cu)
            if r["status"] == "blocked_cap":
                capped += 1
            else:
                n += 1
    return redirect(f"/reviews?msg=bulk_{n}" + (f"&capped={capped}" if capped else ""))


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


@app.route("/reviews/sync", methods=["POST"])
@login_required
def reviews_sync():
    """Manually trigger the review pull (the same seam the heartbeat runs per tick).
    Honest like /roi/sync-firstback: 'simulated' until Google Business Profile is
    connected, 'pending' once connected (auto-pull not live yet). Never fabricates."""
    biz = current_business()
    res = reviewsync.pull_reviews(biz["id"])
    return redirect(f"/reviews?sync={res['mode']}&added={res['added']}")


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
    """Paid Leads: the LSA Concierge (guided Google Screened setup + weekly hygiene,
    the cheapest qualified lead in the trades) plus budget guidance and ad copy.
    Advisory + guided only — no ad account is touched, and we say so."""
    biz = current_business()
    revenue = request.values.get("revenue", type=float)
    budget = ads.recommend_budget(revenue) if revenue else None
    adcopy = ai.generate_ad_copy(biz) if (request.method == "POST"
                                          and request.form.get("action") == "copy") else None
    lsa_done = db.get_lsa_done(biz["id"])
    return render_template("ads.html", budget=budget, adcopy=adcopy,
                           revenue=revenue or "",
                           lsa_checklist=lsa.CHECKLIST, lsa_done=lsa_done,
                           lsa_score=lsa.score(lsa_done),
                           lsa_next=lsa.next_steps(lsa_done))


@app.route("/ads/check", methods=["POST"])
@login_required
def ads_lsa_check():
    biz = current_business()
    db.set_lsa_item(biz["id"], request.form.get("item") or "",
                    request.form.get("done") == "1")
    return redirect("/ads")


@app.route("/outreach", methods=["GET", "POST"])
@login_required
def outreach_page():
    """Partner engine: typed B2B partners (realtor / PM / designer / GC / trade), a
    per-type intro, and a recurring portfolio digest — all through the CAN-SPAM email
    seam (simulated until SMTP is set). Reward guardrail: no cash fees for realtors or
    insurance/restoration partners (partners.py); reward tracking belongs to Nod."""
    biz = current_business()
    preview = None
    if request.method == "POST" and request.form.get("action") == "generate":
        contact = db.get_contact(request.form.get("contact_id", type=int), biz["id"])
        if contact:
            ptype = contact.get("partner_type")
            if ptype:
                email = partners.intro_email(biz, contact, ptype)
            else:  # untyped partner: fall back to the AI-drafted generic intro
                email = ai.generate_cold_email(biz, contact)
            preview = {"contact": contact, "subject": email["subject"], "body": email["body"]}
    elif request.method == "POST" and request.form.get("action") == "digest":
        contact = db.get_contact(request.form.get("contact_id", type=int), biz["id"])
        recent = [p for p in db.list_posts(biz["id"]) if p["status"] == "published"][:5]
        email = partners.digest_email(biz, recent)
        if contact and email:
            preview = {"contact": contact, "subject": email["subject"], "body": email["body"]}
        elif contact:
            return redirect("/outreach?msg=nodigest")
    plist = db.list_contacts(biz["id"], kind="partner")
    for p in plist:
        p["type_label"] = partners.get_type(p.get("partner_type"))["label"] if p.get("partner_type") else ""
        p["reward_note"] = partners.reward_note(p.get("partner_type")) if p.get("partner_type") else ""
    return render_template("outreach.html",
                           partners=plist, partner_types=partners.PARTNER_TYPES,
                           preview=preview, channels=messaging.channel_status(biz["id"]),
                           can_spam=outreach.can_spam_ready(biz))


@app.route("/outreach/type", methods=["POST"])
@login_required
def outreach_set_type():
    biz = current_business()
    contact = db.get_contact(request.form.get("contact_id", type=int), biz["id"])
    ptype = request.form.get("partner_type") or ""
    if contact and (ptype in partners.PARTNER_TYPES or ptype == ""):
        db.set_contact_partner_type(biz["id"], contact["id"], ptype)
    return redirect("/outreach")


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


# NOTE: the /cold UI (cold SMS / voice) was removed 2026-07-19. Cold phone outreach
# to homeowners is permanently hard-blocked (TCPA; no attorney sign-off, no approval
# path), so a page advertising it violated AUDIT_TRUTH in spirit. The fail-closed
# messaging seam (messaging.send_cold_sms + consent ledger + DNC) is KEPT — it is the
# compliance moat and other engines rely on it. See CAPABILITY_BACKLOG.md.


@app.route("/radiusmail")
@login_required
def radiusmail_page():
    """Neighbor Mail: radius direct-mail campaigns around completed jobsites — the
    one lawful cold channel to homeowners (paper needs no consent). v0 is assisted:
    JobMagnet drafts, the owner prints + drops via USPS EDDM."""
    biz = current_business()
    campaigns = db.list_mail_campaigns(biz["id"])
    covered = db.mail_campaign_contact_ids(biz["id"])
    jobs = [c for c in db.list_contacts(biz["id"], kind="customer")
            if c.get("last_job_at") and c["id"] not in covered]
    return render_template("radiusmail.html", campaigns=campaigns, jobs=jobs,
                           mode=radiusmail.mail_mode(),
                           default_pieces=radiusmail.DEFAULT_PIECES,
                           eddm_steps=radiusmail.eddm_steps())


@app.route("/radiusmail/create", methods=["POST"])
@login_required
def radiusmail_create():
    """Draft a campaign for a completed job. The jobsite address is entered here (and
    remembered on the contact so the next campaign prefills)."""
    biz = current_business()
    contact = db.get_contact(request.form.get("contact_id", type=int), biz["id"])
    address = (request.form.get("address") or (contact or {}).get("address") or "").strip()
    if not contact or not address:
        return redirect("/radiusmail?msg=noaddress")
    if contact["id"] in db.mail_campaign_contact_ids(biz["id"]):
        return redirect("/radiusmail?msg=exists")
    db.set_contact_address(biz["id"], contact["id"], address)
    camp = radiusmail.campaign_from_job(
        biz, {"address": address, "service": contact.get("last_service", "")},
        pieces=request.form.get("pieces", type=int) or radiusmail.DEFAULT_PIECES)
    db.add_mail_campaign(biz["id"], camp, contact_id=contact["id"])
    return redirect("/radiusmail?msg=drafted")


@app.route("/radiusmail/<int:campaign_id>/status", methods=["POST"])
@login_required
def radiusmail_status(campaign_id):
    biz = current_business()
    status = request.form.get("status") or ""
    if db.get_mail_campaign(campaign_id, biz["id"]):
        db.set_mail_campaign_status(biz["id"], campaign_id, status)
    return redirect("/radiusmail")


@app.route("/radiusmail/<int:campaign_id>/print")
@login_required
def radiusmail_print(campaign_id):
    """Print-ready page (letter + door hanger) — plain layout, browser print dialog."""
    biz = current_business()
    camp = db.get_mail_campaign(campaign_id, biz["id"])
    if not camp:
        return redirect("/radiusmail")
    return render_template("radiusmail_print.html", camp=camp, business=biz)


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
                           firstback_connected=roi.firstback_connected())


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


@app.route("/roi/sync-firstback", methods=["POST"])
@login_required
def roi_sync_firstback():
    biz = current_business()
    res = roi.sync_firstback(biz["id"])
    return redirect(f"/roi?sync={res['mode']}&added={res['added']}")


@app.route("/webhooks/booking", methods=["POST"])
def webhook_booking():
    """External booking event (e.g. a FirstBack push) -> a booked-job conversion."""
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
    """The Connections hub: link real accounts so JobMagnet actually acts (texts, posts,
    pulls reviews) instead of simulating. Honest status per provider."""
    biz = current_business()
    # P1-6: pop capability-unlock flags and build the callout shown right after connection.
    sms_just_unlocked = session.pop("sms_just_unlocked", False)
    gbp_just_unlocked = session.pop("gbp_just_unlocked", False)
    if sms_just_unlocked:
        signals = db.get_signals(biz["id"])
        backlog = (signals.get("reviewable_backlog", 0) or 0) if signals else 0
        unlock_callout = {
            "message": f"SMS is live. You have {backlog} past customers who haven't reviewed yet.",
            "href": "/reviews",
            "cta": "Start review requests",
        }
    elif gbp_just_unlocked:
        unlock_callout = {
            "message": "Google Business Profile is connected. I can now publish posts and pull reviews.",
            "href": "/getfound",
            "cta": "See what's next",
        }
    else:
        unlock_callout = None
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
                           secrets_active=crypto.secrets_active(),
                           google_configured=google_business.configured(),
                           google_connected=google_business.is_connected(biz["id"]),
                           unlock_callout=unlock_callout)


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
        if provider == "twilio":
            session["sms_just_unlocked"] = True
        return redirect(f"/connections?saved={provider}")
    return redirect("/connections")


@app.route("/connections/<provider>/disconnect", methods=["POST"])
@login_required
def connections_disconnect(provider):
    biz = current_business()
    if provider in connections.PROVIDERS:
        db.disconnect(biz["id"], provider)
    return redirect("/connections")


# ---- Google Business Profile: one-click OAuth (Phase 2) ----
# Real "Connect with Google" so a contractor never pastes a token. The flow is gated and
# honest: with no GOOGLE_CLIENT_ID/SECRET set, /connect is a safe no-op; the callback is
# CSRF-guarded by a random `state` we stash in the session and verify on return; nothing
# shows "Connected" until real tokens are stored. The static /connections/google/* paths
# take precedence over the generic /connections/<provider> rules (more specific wins).
@app.route("/connections/google/connect")
@login_required
def google_connect():
    if not google_business.configured():
        # Not configured -> a safe no-op. The UI also disables the button + hints why.
        return redirect("/connections?msg=google_unconfigured")
    state = secrets.token_urlsafe(24)
    session["google_oauth_state"] = state
    return redirect(google_business.auth_url(state))


@app.route("/connections/google/callback")
@login_required
def google_callback():
    biz = current_business()
    # CSRF: the `state` we sent must come back unchanged. Pop it so a code can't be replayed.
    expected = session.pop("google_oauth_state", "")
    got = request.args.get("state", "")
    if not expected or not hmac.compare_digest(str(expected), str(got)):
        return redirect("/connections?msg=google_state")
    if request.args.get("error"):           # owner declined consent at Google
        return redirect("/connections?msg=google_denied")
    code = request.args.get("code", "")
    if not code:
        return redirect("/connections?msg=google_denied")
    try:
        google_business.connect_with_code(biz["id"], code)
    except Exception as e:                   # noqa: BLE001 -- never 500 the owner here
        print(f"[jobmagnet] google connect failed (biz {biz['id']}): {e}", flush=True)
        return redirect("/connections?msg=google_error")
    session["gbp_just_unlocked"] = True
    return redirect("/connections?saved=gbp")


@app.route("/connections/google/disconnect", methods=["POST"])
@login_required
def google_disconnect():
    biz = current_business()
    google_business.disconnect(biz["id"])
    return redirect("/connections")


@app.route("/faq/<slug>")
def faq_public(slug):
    """P2-16: Public AEO FAQ page for a business. Serves JSON-LD for AI search indexing
    and a paste-ready block for the contractor. No login required."""
    biz = db.get_business_by_slug(slug)
    if not biz:
        abort(404)
    faq_text = biz.get("faq", "")
    if not faq_text:
        abort(404)
    faq_pairs = [{"q": q, "a": a} for q, a in ai._parse_qa(faq_text)]
    faq_jsonld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": p["q"],
             "acceptedAnswer": {"@type": "Answer", "text": p["a"]}}
            for p in faq_pairs
        ],
    }
    return render_template("faq_public.html", biz=biz, faq_pairs=faq_pairs,
                           faq_jsonld=faq_jsonld)


@app.route("/insight/<slug>/<play_key>")
def insight_public(slug, play_key):
    """P2-17: Public 'JobMagnet said no' page — renders a not_yet play's real-numbers reason
    so contractors can share it. mandate.diagnose() is pure, safe for public routes."""
    biz = db.get_business_by_slug(slug)
    if not biz:
        abort(404)
    signals = db.get_signals(biz["id"]) or {}
    result = mandate.diagnose(biz, signals)
    not_yet_plays = [p for p in result["plays"]
                     if p["applicability"] == "not_yet" and p["key"] == play_key]
    if not not_yet_plays:
        abort(404)
    play = not_yet_plays[0]
    return render_template("insight_public.html", play=play, biz=biz)


if __name__ == "__main__":
    print(f"{APP_NAME} -- {TAGLINE}")
    print(f"Brain: {ai.brain_mode()}  ·  http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG, use_reloader=False)
