"""Mason's command center -- the conversational control surface (the "Jarvis").

ONE natural-language seam over the whole product. The signed-in home is a chat: the
owner types "how many leads this week", "draft an Instagram post about the Oak St
exterior", "connect my Google calendar", "set reviews to autopilot" -- and this module
turns that into a real action against the existing engines (db, ai, messaging,
publishing, autopilot, connections). No new source of truth: every tool wraps a function
the manual UI already uses, so the chat can never do something a button couldn't.

Three guarantees, inherited from the rest of JobMagnet:
  1. Provider-agnostic brain. Claude tool-routing when ANTHROPIC_API_KEY is set, MiniMax
     when keyed, and a deterministic keyword router as the always-works floor -- so the
     command bar never goes dark (mirrors ai._active_provider).
  2. Tenant-scoped. Every tool runs against the signed-in business_id; nothing reaches
     another tenant's data.
  3. Honest + consent-gated. Read and draft freely. Anything that actually leaves the
     building or can't be undone (a real text/email blast, a publish, an autopilot
     election) is returned as a `pending_action` and only runs after the owner confirms.
     Outbound still flows through the gated messaging/publishing seams, so quiet hours,
     opt-out and "simulated vs live" stay true.

run(business, message, history) -> {reply, cards, pending_action}
execute(business, tool, args)   -> {reply, cards}      (runs a confirmed action)
"""
import json
import re

import db
import ai
import mandate
import autopilot
import messaging
import publishing
import connections
from config import PLATFORMS, DEFAULT_PLATFORM

# Connection providers the chat can offer to link, with the friendly words a user is
# likely to say for each. "link my google calendar" -> calendar.
_CONNECT_ALIASES = {
    "calendar": ["calendar", "google calendar", "gcal", "schedule"],
    "gbp": ["google business", "google profile", "gbp", "business profile", "google my business"],
    "meta": ["facebook", "instagram", "meta", "fb", "ig"],
    "sms": ["twilio", "texting", "text messaging", "sms", "phone number"],
    "email": ["email", "smtp", "mailbox"],
    "website": ["website", "site", "domain"],
}


# --------------------------------------------------------------------------
# CARD BUILDERS  (typed payloads the frontend renders inline in the transcript)
# --------------------------------------------------------------------------
def _text(body):
    return {"type": "text", "body": body}


def _note(body, tone="info"):
    return {"type": "note", "body": body, "tone": tone}


def _link(title, href, label, note=""):
    return {"type": "link", "title": title, "href": href, "label": label, "note": note}


# --------------------------------------------------------------------------
# TOOL HANDLERS  (each wraps an existing engine; business is the tenant row)
# --------------------------------------------------------------------------
def _h_get_stats(business, args):
    bid = business["id"]
    ls = db.lead_stats(bid)
    cs = db.content_stats(bid)
    rs = db.review_stats(bid)
    roi = db.roi_summary(bid)["totals"]
    speed = ("--" if ls["avg_seconds"] is None
             else (f"{round(ls['avg_seconds'] / 60)}m" if ls["avg_seconds"] >= 60
                   else f"{ls['avg_seconds']}s"))
    cpb = roi["cost_per_booked"]
    card = {"type": "stat", "title": "Where things stand", "groups": [
        {"label": "Leads", "value": ls["total"],
         "sub": f"{ls['awaiting']} awaiting reply"},
        {"label": "Avg response", "value": speed, "sub": "time to first touch"},
        {"label": "Reviews", "value": rs["total"],
         "sub": f"{rs['velocity_30d']} in last 30 days"},
        {"label": "Posts published", "value": cs.get("published", 0),
         "sub": f"{cs.get('draft', 0)} drafts waiting"},
        {"label": "Booked jobs", "value": roi["booked"],
         "sub": (f"${cpb:,.0f} per booked job" if cpb else "no ad spend logged")},
        {"label": "Revenue", "value": f"${roi['revenue']:,.0f}",
         "sub": (f"{roi['roas']}x ROAS" if roi["roas"] else "tracked to date")},
    ]}
    reply = ("Here is the current picture. These are running totals to date, not a "
             "7-day slice -- I will not invent a weekly cut I cannot measure yet.")
    return {"reply": reply, "cards": [card]}


def _h_list_leads(business, args):
    leads = db.list_leads(business["id"])[:8]
    if not leads:
        return {"reply": "No leads on file yet. The moment one comes in, it lands here.",
                "cards": []}
    items = [{"title": (l.get("name") or l.get("phone") or "Lead"),
              "sub": f"{l.get('channel', 'lead')} · {l.get('status', 'new')}"
                     + (f" · {l['topic']}" if l.get("topic") else "")}
             for l in leads]
    return {"reply": f"Your {len(items)} most recent leads.",
            "cards": [{"type": "list", "title": "Recent leads", "items": items}]}


def _h_list_drafts(business, args):
    drafts = [p for p in db.list_posts(business["id"]) if p["status"] == "draft"]
    if not drafts:
        return {"reply": "Nothing is waiting on your okay right now.", "cards": []}
    cards = [{"type": "draft", "post_id": p["id"], "platform": p["platform"],
              "title": f"{p['platform'].capitalize()} draft", "body": p["body"],
              "status": p["status"]} for p in drafts[:5]]
    return {"reply": f"You have {len(drafts)} draft(s) waiting. Approve, edit, or tell me "
                     "to publish one.", "cards": cards}


def _h_add_contact(business, args):
    name = (args.get("name") or "").strip()
    phone = (args.get("phone") or "").strip()
    email = (args.get("email") or "").strip()
    kind = (args.get("kind") or "customer").strip().lower()
    if not (name or phone or email):
        return {"reply": "Tell me at least a name or a phone number and I will save them.",
                "cards": []}
    cid = db.add_contact(business["id"], name=name, phone=phone, email=email, kind=kind)
    who = name or phone or email
    return {"reply": f"Saved {who} to your {kind} contacts.",
            "cards": [_note(f"Contact #{cid} stored. I can text them a review request or "
                            "add them to a campaign whenever you want.", "ok")]}


def _h_draft_post(business, args):
    topic = (args.get("topic") or "").strip()
    platform = (args.get("platform") or DEFAULT_PLATFORM).strip().lower()
    if platform not in PLATFORMS:
        platform = DEFAULT_PLATFORM
    body = ai.generate_post(business, topic, platform)
    pid = db.add_post(business["id"], platform, topic, body, status="draft")
    mode = publishing.platform_mode(platform, business["id"])
    note = {"live": "I can publish this for real on your confirmation.",
            "assisted": "This platform is assisted: I will hand you finished copy to paste.",
            "simulated": "This channel is simulated until you connect it."}.get(mode, "")
    return {"reply": f"Drafted a {platform.capitalize()} post for you. Say \"publish it\" "
                     "to send it out, or edit it first.",
            "cards": [{"type": "draft", "post_id": pid, "platform": platform,
                       "title": f"{platform.capitalize()} draft", "body": body,
                       "status": "draft", "mode": mode, "note": note}]}


def _h_publish_post(business, args):
    """CONFIRM tool. Publish a specific post (or the latest draft) through the gated
    publishing seam, which is honest about live / assisted / simulated."""
    pid = args.get("post_id")
    if not pid:
        drafts = [p for p in db.list_posts(business["id"]) if p["status"] == "draft"]
        if not drafts:
            return {"reply": "There is no draft to publish.", "cards": []}
        pid = drafts[0]["id"]
    post = db.get_post(int(pid), business["id"])
    if not post:
        return {"reply": "I could not find that post.", "cards": []}
    res = publishing.publish_post(business["id"], post)
    mode = res["mode"]
    msg = {"live": f"Published to {res['platform'].capitalize()}.",
           "assisted": f"Your {res['platform'].capitalize()} copy is ready to paste "
                       "(that account is not auto-post connected yet).",
           "simulated": f"Marked as published (simulated). Connect {res['platform'].capitalize()} "
                        "to post for real.",
           "error": f"I could not reach {res['platform'].capitalize()} just now, so nothing "
                    "went out. The post is still in your queue."}.get(mode, "Done.")
    tone = "warn" if mode == "error" else "ok"
    return {"reply": msg, "cards": [_note(msg, tone)]}


def _h_request_reviews(business, args):
    """CONFIRM tool. Text a review request to every eligible customer not yet asked.
    Transactional, but a real outbound blast -- so it is gated behind confirm and still
    flows through messaging.send_sms (consent, opt-out, simulated-vs-live all honored)."""
    bid = business["id"]
    link = (business.get("google_review_link") or "").strip()
    if not link:
        return {"reply": "Add your Google review link in Business Brain first, then I can "
                         "send review requests.",
                "cards": [_link("Add your review link", "/settings", "Open Business Brain")]}
    asked = db.requested_contact_ids(bid)
    sent = simulated = capped = 0
    for cu in db.list_contacts(bid, kind="customer"):
        if (cu.get("phone") and not cu.get("suppressed")
                and cu.get("consent_status") != "opted_out" and cu["id"] not in asked):
            body = ai.review_request_message(business, cu.get("name", "")) + " " + link
            r = messaging.send_sms(bid, cu["phone"], body, kind="transactional",
                                   purpose="review_request", contact=cu)
            if r["status"] == "sent":
                sent += 1
            elif r["status"] == "simulated":
                simulated += 1
            elif r["status"] == "blocked_cap":
                capped += 1
    total = sent + simulated
    # Pacing: anything over today's cap waits; the next run continues it (it was never
    # marked as contacted), so a big list drips over a few days instead of dumping.
    drip = (f" {capped} more are paced for the next few days so we stay carrier-friendly."
            if capped else "")
    if not total and not capped:
        return {"reply": "Everyone eligible has already been asked, or there are no "
                         "customers with a phone number on file yet.", "cards": []}
    if not total and capped:
        return {"reply": f"You have hit today's send pace. {capped} review request(s) are "
                         "queued to go out over the next few days.",
                "cards": [_note(f"{capped} paced for later (carrier-friendly).", "info")]}
    live = messaging.sms_live(bid)
    msg = (f"Sent {total} review request(s)." if live
           else f"Prepared {total} review request(s) (simulated -- connect Twilio to send "
                "for real).") + drip
    return {"reply": msg, "cards": [_note(msg, "ok")]}


def _h_connect(business, args):
    prov = (args.get("provider") or "").strip().lower()
    if prov not in connections.PROVIDERS:
        prov = _match_provider(prov) or _match_provider(args.get("raw", ""))
    if not prov:
        return {"reply": "I can link your calendar, Google Business Profile, "
                         "Facebook/Instagram, texting (Twilio), email, or website. Which one?",
                "cards": [_link("Open Connections", "/connections", "See all connections")]}
    label = connections.PROVIDERS[prov]["label"]
    linked = bool(db.get_connection(business["id"], prov))
    if linked:
        return {"reply": f"{label} is already connected.",
                "cards": [_link(f"Manage {label}", "/connections", "Open Connections")]}
    return {"reply": f"Let's connect {label}. Open the connections hub and I will walk you "
                     "through it.",
            "cards": [_link(f"Connect {label}", "/connections", f"Connect {label}",
                            note=connections.PROVIDERS[prov].get("blurb", ""))]}


def _h_game_plan(business, args):
    bid = business["id"]
    signals = db.get_signals(bid) or {}
    if not db.has_mandate(bid):
        return {"reply": "I have not built your game plan yet. Run the quick walkthrough and "
                         "I will tell you what to do first and what to skip.",
                "cards": [_link("Run the walkthrough", "/walkthrough", "Build my game plan")]}
    result = mandate.diagnose(business, signals)
    top = [p for p in result["plays"] if p["applicability"] == "applies"][:5]
    items = [{"label": f"{i+1}. {p['label']}", "blurb": p["reason"],
              "recommended": p["recommended"], "applicability": p["applicability"]}
             for i, p in enumerate(top)]
    return {"reply": result["headline"],
            "cards": [{"type": "plays", "title": "Your game plan", "items": items}]}


def _h_set_autopilot(business, args):
    """CONFIRM tool. Set a playbook's election (take_over / ask_first / off)."""
    pb = (args.get("playbook") or "").strip().lower().replace(" ", "_")
    election = (args.get("election") or "take_over").strip().lower()
    if pb not in mandate.PLAYBOOKS:
        pb = _match_playbook(args.get("playbook") or args.get("raw", ""))
    if not pb:
        names = ", ".join(v["label"] for v in mandate.PLAYBOOKS.values())
        return {"reply": f"Which play should I set? I run: {names}.", "cards": []}
    if election not in mandate.ELECTIONS:
        election = "take_over"
    db.set_election(business["id"], pb, election)
    lbl = mandate.PLAYBOOKS[pb]["label"]
    el_lbl = mandate.ELECTION_LABELS[election]
    return {"reply": f"Set {lbl} to \"{el_lbl}\".",
            "cards": [_note(f"{lbl}: {el_lbl}. Run autopilot whenever you are ready and I "
                            "will handle the plays you set me to take over.", "ok"),
                      _link("See your game plan", "/mandate", "Open Game Plan")]}


def _h_run_autopilot(business, args):
    """CONFIRM tool. Report what autopilot WOULD run; the actual send still happens on the
    Game Plan page through the gated seam, so this stays a safe preview + handoff."""
    bid = business["id"]
    plays = db.get_mandate(bid)
    if not plays:
        return {"reply": "Build your game plan first and set a play or two to \"Take it over.\"",
                "cards": [_link("Run the walkthrough", "/walkthrough", "Build my game plan")]}
    rows = autopilot.plan({p["playbook"]: p["election"] for p in plays})
    on = [r for r in rows if r["status"] == "run"]
    if not on:
        return {"reply": "Nothing is set to \"Take it over\" yet, so autopilot has nothing to "
                         "run. Tell me which play to take over.",
                "cards": [_link("Open Game Plan", "/mandate", "Set autopilot")]}
    items = [{"title": r["action"], "sub": "ready to run"} for r in on]
    return {"reply": f"{len(on)} play(s) are on autopilot. Kick them off from the Game Plan "
                     "page and each goes through the same approval and consent gates.",
            "cards": [{"type": "list", "title": "On autopilot", "items": items},
                      _link("Run autopilot", "/mandate", "Open Game Plan")]}


# The registry. `confirm` tools are previewed as a pending_action and only run after the
# owner taps Confirm (-> execute()).
TOOLS = {
    "get_stats":       {"fn": _h_get_stats, "confirm": False,
                        "desc": "Show current numbers: leads, response time, reviews, posts, booked jobs, revenue.",
                        "params": []},
    "list_leads":      {"fn": _h_list_leads, "confirm": False,
                        "desc": "List the most recent leads.", "params": []},
    "list_drafts":     {"fn": _h_list_drafts, "confirm": False,
                        "desc": "Show social posts waiting for approval.", "params": []},
    "add_contact":     {"fn": _h_add_contact, "confirm": False,
                        "desc": "Save a contact (customer, partner, or lead).",
                        "params": ["name", "phone", "email", "kind"]},
    "draft_post":      {"fn": _h_draft_post, "confirm": False,
                        "desc": "Write a social post draft for a platform about a topic.",
                        "params": ["topic", "platform"]},
    "publish_post":    {"fn": _h_publish_post, "confirm": True,
                        "desc": "Publish a post (or the latest draft) out to its platform.",
                        "params": ["post_id"]},
    "request_reviews": {"fn": _h_request_reviews, "confirm": True,
                        "desc": "Text a review request to every eligible past customer.",
                        "params": []},
    "connect":         {"fn": _h_connect, "confirm": False,
                        "desc": "Link an account: calendar, Google profile, Facebook/Instagram, texting, email, website.",
                        "params": ["provider"]},
    "game_plan":       {"fn": _h_game_plan, "confirm": False,
                        "desc": "Show Mason's ranked marketing game plan for this business.",
                        "params": []},
    "set_autopilot":   {"fn": _h_set_autopilot, "confirm": True,
                        "desc": "Set a playbook to take_over, ask_first, or off.",
                        "params": ["playbook", "election"]},
    "run_autopilot":   {"fn": _h_run_autopilot, "confirm": True,
                        "desc": "Run the plays set to take over.", "params": []},
}

# A short, human summary for the confirm card of each gated tool.
_CONFIRM_SUMMARY = {
    "publish_post": "Publish this post to its platform.",
    "request_reviews": "Text a review request to every eligible customer who has not been asked.",
    "set_autopilot": "Change which marketing plays Mason runs on his own.",
    "run_autopilot": "Run the plays you have set to take over.",
}


# --------------------------------------------------------------------------
# MATCHERS  (used by the demo router and to repair loose LLM args)
# --------------------------------------------------------------------------
def _match_provider(text):
    t = (text or "").lower()
    for prov, aliases in _CONNECT_ALIASES.items():
        if any(a in t for a in aliases):
            return prov
    return None


def _match_platform(text):
    t = (text or "").lower()
    if "instagram" in t or " ig " in f" {t} ":
        return "instagram"
    if "facebook" in t or " fb " in f" {t} ":
        return "facebook"
    if "google" in t:
        return "google"
    if "linkedin" in t:
        return "linkedin"
    return None


def _match_playbook(text):
    t = (text or "").lower()
    table = {"reviews": ["review"], "get_found": ["get found", "seo", "google profile", "found"],
             "speed_to_lead": ["speed", "lead response", "respond"],
             "reactivation": ["reactivat", "past customer", "win back", "dormant"],
             "show_work": ["show work", "showcase", "project", "portfolio"],
             "referrals": ["referral", "refer"], "paid": ["paid", "ads", "advertis"],
             "offer": ["offer", "guarantee"]}
    for pb, kws in table.items():
        if any(k in t for k in kws):
            return pb
    return None


_PHONE_RE = re.compile(r"(\+?\d[\d\-\.\s\(\)]{6,}\d)")
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


# --------------------------------------------------------------------------
# THE BRAIN  (LLM tool-routing, with a deterministic floor)
# --------------------------------------------------------------------------
def _tool_catalog():
    lines = []
    for name, spec in TOOLS.items():
        p = (" params: " + ", ".join(spec["params"])) if spec["params"] else ""
        lines.append(f"- {name}: {spec['desc']}{p}")
    return "\n".join(lines)


def _learning_examples(business):
    """Few-shot lines from this tenant's confirmed corrections (hook wired by the app to
    convos.learnings_for_prompt), so the brain generalizes what the owner has taught."""
    fn = globals().get("_learning_examples_hook")
    try:
        return fn(business["id"]) if fn else ""
    except Exception:
        return ""


def _route_system(business=None):
    taught = _learning_examples(business) if business else ""
    taught_block = ("\nThe owner has TAUGHT you these corrections; honor them:\n" + taught
                    + "\n") if taught else ""
    return (
        "You are Mason, the control assistant inside JobMagnet, an AI marketing app for a "
        "home-services contractor. Decide which ONE tool best answers the owner's message, "
        "and extract its parameters from what they said.\n\n"
        "TOOLS:\n" + _tool_catalog() + "\n" + taught_block + "\n"
        "Respond with ONLY a JSON object, no prose, no code fences, in this exact shape:\n"
        '{\"tool\": \"<tool name or chat>\", \"args\": {<params>}, \"reply\": \"<one short '
        'friendly sentence to say while doing it>\"}\n'
        "There is NO tool for post scheduling, spacing, or cadence (the app spaces posts and "
        "avoids quiet hours automatically), for billing or plan changes, or for editing the "
        "business profile. For any of those, use \"chat\" and the app will point them to the "
        "right page. draft_post writes new content; list_drafts only shows posts already "
        "awaiting approval, so do not use it for a scheduling question.\n"
        "Use \"chat\" as the tool when they are just talking, greeting, or asking something no "
        "tool covers, and put your answer in reply. Never invent data. Do not use dashes; use "
        "periods and commas.")


def _llm_route(business, message, history):
    """Ask the active brain to pick a tool + args. Returns a dict or None (-> demo floor)."""
    provider = ai._active_provider()
    if provider not in ("claude", "minimax"):
        return None
    convo = ""
    for turn in (history or [])[-6:]:
        who = "Owner" if turn.get("role") == "user" else "Mason"
        convo += f"{who}: {turn.get('content', '')}\n"
    user_text = f"{convo}Owner: {message}\n\nReturn the JSON now."
    try:
        complete = ai._claude_complete if provider == "claude" else ai._minimax_complete
        raw = ai._strip_think(complete(_route_system(business), user_text))
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
        if isinstance(data, dict) and data.get("tool"):
            return data
    except Exception as e:
        print(f"[jobmagnet] assistant route failed, using keyword floor: {e}", flush=True)
    return None


def suggest_tool_for(message):
    """Given a request Mason fell back on (a recurring gap), ask the brain whether ONE
    existing tool would genuinely satisfy it. Returns a tool name only on high confidence,
    else None. Powers the proactive 'I think I can actually do that now' offer."""
    provider = ai._active_provider()
    if provider not in ("claude", "minimax"):
        return None
    system = (
        "An assistant could not handle a request and fell back to pointing the owner at a "
        "page. Decide if ONE of the existing tools below would ACTUALLY do what the owner "
        "asked. Be conservative: only name a tool if you are confident it FULLY satisfies "
        "the request; otherwise say none.\nTOOLS:\n" + _tool_catalog() + "\n"
        'Reply with ONLY a JSON object: {"tool":"<exact tool name or none>","confidence":"high|low"}.')
    user = f"OWNER REQUEST: {message}\n\nReturn the JSON now."
    try:
        complete = ai._claude_complete if provider == "claude" else ai._minimax_complete
        raw = ai._strip_think(complete(system, user))
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        d = json.loads(m.group(0)) if m else {}
        if d.get("tool") in TOOLS and d.get("confidence") == "high":
            return d["tool"]
    except Exception:
        return None
    return None


def _demo_route(message):
    """The always-works floor: keyword -> tool + best-effort args. No API needed."""
    t = message.lower().strip()
    args = {"raw": message}

    if any(k in t for k in ("how many", "stats", "numbers", "results", "how are we",
                            "how's it going", "leads this", "this week", "roas", "revenue")):
        if "lead" in t and "how many" not in t and "list" in t:
            return "list_leads", args
        return "get_stats", args
    if "list" in t and "lead" in t:
        return "list_leads", args
    if any(k in t for k in ("connect", "link", "hook up", "integrat")):
        args["provider"] = _match_provider(t) or ""
        return "connect", args
    if "review" in t and any(k in t for k in ("request", "ask", "blast", "send", "get more")):
        return "request_reviews", args
    if any(k in t for k in ("draft", "write", "compose", "post about", "blast", "publish a",
                            "make a post")):
        args["platform"] = _match_platform(t) or DEFAULT_PLATFORM
        args["topic"] = re.sub(r".*?(about|on|for)\s+", "", message, count=1, flags=re.I).strip() \
            if re.search(r"\b(about|on|for)\b", t) else message
        return "draft_post", args
    if "draft" in t or "waiting" in t or "approve" in t:
        return "list_drafts", args
    if any(k in t for k in ("contact", "save", "store", "add ")) and (
            _PHONE_RE.search(message) or _EMAIL_RE.search(message) or "contact" in t):
        ph = _PHONE_RE.search(message)
        em = _EMAIL_RE.search(message)
        if ph:
            args["phone"] = ph.group(1).strip()
        if em:
            args["email"] = em.group(0).strip()
        # Name = words before the phone/email, minus the command verb.
        head = re.split(r"(\+?\d|@)", message)[0]
        args["name"] = re.sub(r"^(save|store|add|new)\s+(contact\s+)?", "", head,
                              flags=re.I).strip(" ,")
        return "add_contact", args
    if any(k in t for k in ("autopilot", "automate", "take it over", "take over", "on auto")):
        if any(k in t for k in ("run", "go", "kick off", "start")):
            return "run_autopilot", args
        args["playbook"] = _match_playbook(t) or ""
        args["election"] = "off" if ("off" in t or "stop" in t) else (
            "ask_first" if "ask" in t else "take_over")
        if args["playbook"]:
            return "set_autopilot", args
        return "game_plan", args
    if any(k in t for k in ("game plan", "what should i", "what next", "where do i start",
                            "diagnose", "what do you recommend", "priorit")):
        return "game_plan", args
    return "chat", args


def _route_topic(message):
    """Capability honesty: for a request with no direct tool, route to the nearest real
    page instead of dead-ending it as a 'feature request'. Returns {reply, cards} or None."""
    t = message.lower()
    if any(k in t for k in ("buffer", "back to back", "back-to-back", "too close", "double book",
                            "calendar rule", "posting schedule", "schedule my posts", "cadence",
                            "when to post", "post at", "quiet hours", "spacing", "space my posts",
                            "stagger")):
        return {"reply": "I space your scheduled posts out automatically and never auto-publish "
                         "during your quiet hours. You can set any post's exact time in the Queue.",
                "cards": [_link("Schedule a post", "/queue", "Open the Queue")]}
    if any(k in t for k in ("billing", "plan", "upgrade", "subscription", "pricing", "price",
                            "pay", "cancel my")):
        return {"reply": "You can change your plan or billing here.",
                "cards": [_link("Plan & Pricing", "/plan", "Open Plan & Pricing")]}
    if any(k in t for k in ("password", "my account", "profile", "brand voice", "business brain",
                            "my business info", "logo", "service area", "my hours")):
        return {"reply": "Your business details and brand voice live in your Business Brain.",
                "cards": [_link("Business Brain", "/settings", "Open Business Brain")]}
    return None


def _chat_reply(message):
    """A plain conversational answer (no tool). Uses the brain if available, else a
    helpful capabilities nudge."""
    provider = ai._active_provider()
    if provider in ("claude", "minimax"):
        try:
            complete = ai._claude_complete if provider == "claude" else ai._minimax_complete
            sys = ("You are Mason, a warm, concise marketing assistant for a home-services "
                   "contractor inside the JobMagnet app. Answer in 1 to 3 sentences. Do not "
                   "use dashes; use periods and commas. If they seem to want an action you can "
                   "take (draft a post, send reviews, connect an account, show stats, set "
                   "autopilot), offer it. Never call something a 'feature request' or say it is "
                   "'for future development'. If you cannot do it directly, point them to the "
                   "right place honestly (the Queue for scheduling, Plan and Pricing for billing, "
                   "the Business Brain in Settings for their profile).")
            out = ai._strip_think(complete(sys, message))
            if out:
                return out
        except Exception:
            pass
    return ("I am your control desk. Ask me things like \"how many leads this week,\" "
            "\"draft an Instagram post about the Oak Street exterior,\" \"connect my Google "
            "calendar,\" or \"set reviews to autopilot.\"")


def _chat_or_route(message, llm_reply=""):
    """Chat answer, but first route known topics to a real page (capability honesty).
    A routed reply is a capability_gap (Mason had no native tool, so he pointed elsewhere);
    a plain chat reply is just conversation. Both are logged so we can learn from them."""
    routed = _route_topic(message)
    if routed:
        return {"reply": routed["reply"], "cards": routed["cards"], "pending_action": None,
                "meta": {"tool": "route", "status": "capability_gap"}}
    return {"reply": llm_reply or _chat_reply(message), "cards": [], "pending_action": None,
            "meta": {"tool": "chat", "status": "chat"}}


# --------------------------------------------------------------------------
# PUBLIC ENTRY POINTS
# --------------------------------------------------------------------------
def run(business, message, history=None):
    """Turn one owner message into {reply, cards, pending_action}. Gated tools are NOT
    executed here -- they come back as a pending_action for an explicit confirm."""
    message = (message or "").strip()
    if not message:
        return {"reply": "What can I do for you?", "cards": [], "pending_action": None,
                "meta": {"tool": None, "status": "empty"}}

    # A confirmed learning for this tenant beats the brain (deterministic + reversible).
    taught = _apply_learning(business, message)
    if taught is not None:
        return taught

    routed = _llm_route(business, message, history)
    if routed and routed.get("tool") in TOOLS:
        tool, args = routed["tool"], (routed.get("args") or {})
        args.setdefault("raw", message)
        llm_reply = routed.get("reply") or ""
    elif routed and routed.get("tool") == "chat":
        return _chat_or_route(message, routed.get("reply") or "")
    else:
        tool, args = _demo_route(message)
        llm_reply = ""

    if tool == "chat":
        return _chat_or_route(message)

    spec = TOOLS[tool]
    if spec["confirm"]:
        # Never let the brain imply it already acted. Gated actions are previewed and
        # wait for an explicit confirm, so the reply must ask, not announce.
        summary = _CONFIRM_SUMMARY.get(tool, "Run this action.")
        return {"reply": "Ready when you are. Confirm below and I will take care of it.",
                "cards": [], "pending_action": {"tool": tool, "args": args, "summary": summary},
                "meta": {"tool": tool, "status": "pending"}}

    out = spec["fn"](business, args)
    reply = out.get("reply") or llm_reply
    cards = out.get("cards", [])
    return {"reply": reply, "cards": cards, "pending_action": None,
            "meta": {"tool": tool, "status": "ok" if cards else "empty"}}


def _apply_learning(business, message):
    """If the tenant taught Mason a confirmed correction matching this message, honor it
    (deterministic override, consulted before the brain). The lookup hook is wired by the
    app to convos.lookup; it returns a full result, or a {'_run_tool': name} directive we
    execute here so tool execution stays in this module (no import cycle)."""
    fn = globals().get("_learning_lookup")
    if not fn:
        return None
    hit = fn(business, message)
    if not hit:
        return None
    if "_run_tool" in hit:
        tool = hit["_run_tool"]
        spec = TOOLS.get(tool)
        if not spec:
            return None
        if spec["confirm"]:
            summary = _CONFIRM_SUMMARY.get(tool, "Run this action.")
            return {"reply": "Ready when you are. Confirm below and I will take care of it.",
                    "cards": [], "pending_action": {"tool": tool, "args": {"raw": message},
                                                    "summary": summary},
                    "meta": {"tool": tool, "status": "pending"}}
        out = spec["fn"](business, {"raw": message})
        cards = out.get("cards", [])
        return {"reply": out.get("reply", ""), "cards": cards, "pending_action": None,
                "meta": {"tool": tool, "status": "learned" if cards else "empty"}}
    return hit


def execute(business, tool, args):
    """Run a confirmed action (a gated tool the owner approved). Returns {reply, cards}."""
    spec = TOOLS.get(tool)
    if not spec:
        return {"reply": "That action is no longer available.", "cards": [],
                "meta": {"tool": tool, "status": "error"}}
    out = spec["fn"](business, args or {})
    cards = out.get("cards", [])
    return {"reply": out.get("reply", "Done."), "cards": cards,
            "meta": {"tool": tool, "status": "ok" if cards else "empty"}}


def suggestions():
    """The starter chips shown under an empty command bar."""
    return [
        "How many leads came in this week?",
        "Draft an Instagram post about a finished exterior",
        "Connect my Google calendar",
        "Set reviews to autopilot",
        "What should I focus on next?",
    ]
