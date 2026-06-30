"""Mason's diagnostic + Mandate engine -- the brain and the front door.

Pure decision logic: read a business's real state (its Business Brain + a few
diagnostic signals from the Walkthrough) and produce a *prioritised, honest* plan
-- which marketing playbooks to run, in what order, and whether each even applies
yet. There is deliberately no one-size "reviews first": a brand-new invisible shop
and an established shop sitting on a dormant customer list get opposite orders.
That re-prioritisation is the product -- the thing the Heritage teardown proved we
need (a 1-year shop can't bootstrap a "review flywheel"; an old shop's goldmine is
its dormant list).

Side-effect free (no DB, no Flask) so it's trivially testable and the same logic
can later drive the UI, an API, or Mason's chat. Grounded in MARKETING_PLAYBOOK.md
(the levers) and MASON_WALKTHROUGH_HERITAGE.md (the honest diagnosis).
"""

# The playbooks Mason can run. Keys are stable ids; label/blurb drive the UI.
PLAYBOOKS = {
    "get_found":     {"label": "Get Found",
                      "blurb": "Optimize your Google profile, local SEO and AI answers so the right homeowners find you. Owned, free, compounding."},
    "reviews":       {"label": "Review Velocity",
                      "blurb": "A steady drip of fresh Google reviews. Recency beats volume and it lifts your ranking."},
    "speed_to_lead": {"label": "Speed-to-Lead",
                      "blurb": "Answer every inbound in seconds. Whoever replies first usually wins the job."},
    "reactivation":  {"label": "Database Reactivation",
                      "blurb": "Win back past customers on their repaint cycle. Five to six times cheaper than a new lead."},
    "show_work":     {"label": "Show the Work",
                      "blurb": "Put your best projects in front of the right homeowners. Your work is the unfair advantage."},
    "referrals":     {"label": "Referrals & Plans",
                      "blurb": "Turn happy customers into a referral habit and recurring maintenance work."},
    "paid":          {"label": "Targeted Paid",
                      "blurb": "Local Services Ads and targeted ads. The realistic lead injector when organic isn't enough yet."},
    "offer":         {"label": "Offer & Guarantee",
                      "blurb": "Give every campaign a real hook and a risk-reversal so each lead costs less."},
}

ELECTIONS = ("take_over", "ask_first", "off")     # Premium / Pro / off
ELECTION_LABELS = {"take_over": "Take it over", "ask_first": "Ask me first", "off": "Not yet"}
APPLICABILITY = ("applies", "not_yet", "gated")
_APP_RANK = {"applies": 0, "not_yet": 1, "gated": 2}


def _num(v, default=0.0):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def normalize_signals(raw):
    """Coerce a raw signal dict (form values or kwargs) into typed values with sane
    defaults. `reviewable_backlog` defaults to (past_customers - review_count) but an
    explicit value wins (Heritage: clients already reviewed, so backlog is ~0)."""
    raw = raw or {}
    # Counts/amounts can never be negative; clamp so a typo can't skew the diagnosis.
    years = max(0.0, _num(raw.get("years_in_business"), 1.0))
    past = max(0, int(_num(raw.get("past_customers"), 0)))
    reviews = max(0, int(_num(raw.get("review_count"), 0)))
    leads = max(0, int(_num(raw.get("monthly_leads"), 0)))
    # Missed can't exceed total leads.
    missed = min(leads, max(0, int(_num(raw.get("missed_leads"), 0))))
    backlog_raw = raw.get("reviewable_backlog")
    if backlog_raw in (None, ""):
        backlog = max(0, past - reviews)
    else:
        backlog = max(0, int(_num(backlog_raw, max(0, past - reviews))))
    # Backlog can't exceed the customer base (and is 0 if there are no customers).
    backlog = min(backlog, past)
    return {
        "years_in_business": years,
        "monthly_leads": leads,
        "missed_leads": missed,
        "close_rate": max(0.0, _num(raw.get("close_rate"), 0.0)),
        "review_count": reviews,
        "new_jobs_per_month": max(0.0, _num(raw.get("new_jobs_per_month"), 0.0)),
        "past_customers": past,
        "oldest_job_years": max(0.0, _num(raw.get("oldest_job_years"), years)),
        "avg_job_value": max(0.0, _num(raw.get("avg_job_value"), 0.0)),
        "reviewable_backlog": backlog,
        "gbp_claimed": _bool(raw.get("gbp_claimed")),
        "runs_ads": _bool(raw.get("runs_ads")),
        "competitor_review_count": max(0, int(_num(raw.get("competitor_review_count"), 0))),
    }


def diagnose(business, raw_signals):
    """Return Mason's read: {state, headline, woven, signals, plays}. `plays` is the
    full ranked list (each: key,label,blurb,applicability,recommended,score,priority,
    reason), sorted applies-first then by score. Honest: plays that don't apply yet are
    tagged `not_yet`, not hidden -- Mason tells you what he won't do and why."""
    business = business or {}
    s = normalize_signals(raw_signals)
    ml = s["monthly_leads"]
    missed_ratio = (s["missed_leads"] / ml) if ml else 0.0
    luxury = s["avg_job_value"] >= 6000
    low_visibility = s["review_count"] < 20 and ml < 10
    reactivation_due = s["past_customers"] >= 30 and s["oldest_job_years"] >= 3
    has_happy_base = s["past_customers"] >= 10
    organic_fuel = (reactivation_due or s["reviewable_backlog"] >= 10
                    or s["new_jobs_per_month"] >= 4)

    plays = []

    def add(key, applicability, recommended, score, reason):
        plays.append({"key": key, "label": PLAYBOOKS[key]["label"],
                      "blurb": PLAYBOOKS[key]["blurb"], "applicability": applicability,
                      "recommended": recommended, "score": float(score), "reason": reason})

    # --- Get Found (owned, almost always the foundation) ---
    gf = 70.0
    if not s["gbp_claimed"]:
        gf += 15
        gf_reason = ("Your Google profile isn't even claimed yet. That's the cheapest "
                     "visibility you're leaving on the table.")
    elif low_visibility:
        gf += 12
        gf_reason = ("You do great work but you're nearly invisible online. Getting found "
                     "is the foundation everything else builds on.")
    else:
        gf_reason = ("Keep your owned channels (Google profile, local pages, AI answers) "
                     "fresh so they compound.")
    if s["review_count"] < 10:
        gf += 6
    add("get_found", "applies", "take_over", gf, gf_reason)

    # --- Review Velocity (can't be bootstrapped from a tapped base) ---
    comp_rv = s.get("competitor_review_count", 0)
    _comp_suffix = (f" Your top local competitor has roughly {comp_rv} reviews vs your "
                    f"{s['review_count']} — that gap is costing you clicks."
                    if comp_rv and comp_rv > s["review_count"] and (comp_rv - s["review_count"]) >= 20
                    else "")
    if s["reviewable_backlog"] >= 10:
        add("reviews", "applies", "take_over", 80,
            f"You've got about {s['reviewable_backlog']} happy past clients who haven't "
            "left a review yet. That's the fastest way to climb in search." + _comp_suffix)
    elif s["new_jobs_per_month"] >= 3:
        add("reviews", "applies", "take_over", 55,
            "Capture a review from every job. Steady velocity is what lifts your ranking."
            + _comp_suffix)
    else:
        add("reviews", "applies", "ask_first", 30,
            "Your past clients have already reviewed and you're not closing enough new "
            "jobs yet to spin a 'review flywheel' (chicken and egg). I'll grab one from "
            "every new job, but it can't be the lead engine yet." + _comp_suffix)

    # --- Speed-to-Lead (priority scales with volume + missed) ---
    if s["missed_leads"] >= 3 or missed_ratio >= 0.25:
        add("speed_to_lead", "applies", "take_over", 90,
            f"You're missing about {s['missed_leads']} leads a month. Whoever answers first "
            "usually wins, so this is found money.")
    elif ml >= 10:
        add("speed_to_lead", "applies", "take_over", 60,
            "At your volume, answering instantly meaningfully lifts booked jobs.")
    else:
        add("speed_to_lead", "applies", "ask_first", 35,
            f"At {ml} leads a month you're not bleeding many, and you already close what you "
            "get. I'll set it up so nothing slips as you grow, but it's not today's bottleneck.")

    # --- Database Reactivation (gated until repaint cycles are due) ---
    if reactivation_due:
        add("reactivation", "applies", "ask_first", 85,
            f"You're sitting on about {s['past_customers']} past customers with jobs going "
            f"back {int(s['oldest_job_years'])}+ years. Repaint cycles are coming due. Found "
            "money, five to six times cheaper than a new lead.")
    else:
        add("reactivation", "not_yet", "off", 0,
            "Your repaint cycles are years out and the past-customer base is small. There's "
            "no dormant goldmine to mine yet, and I won't pretend there is.")

    # --- Show the Work (visual proof; the unfair advantage) ---
    sw = 50 + (15 if low_visibility else 0)
    add("show_work", "applies", "ask_first", sw,
        "Put your best projects in front of the right homeowners. Your work is the "
        "advantage, and most of your market hasn't seen it.")

    # --- Referrals & Plans (warm, free, off the happy base) ---
    if has_happy_base:
        add("referrals", "applies", "ask_first", 64,
            f"Your {s['past_customers']} happy clients already vouch for you. Turning that "
            "into a referral habit is warm, free leads.")
    else:
        add("referrals", "applies", "ask_first", 35,
            "Build the referral habit early so word of mouth compounds as you grow.")

    # --- Targeted Paid (the injector when organic can't spin yet) ---
    if (not organic_fuel) and ml < 8:
        add("paid", "applies", "ask_first", 62,
            "You don't have the review backlog or a dormant list to spin organic growth "
            "yet, so a small, sharp targeted push is the realistic way to inject leads and "
            "break the logjam. Sooner than the usual playbook, on purpose.")
    else:
        add("paid", "applies", "ask_first", 40,
            "Once your reviews and profile make paid cheap, pour gas on what's working. "
            "Not first.")

    # --- Offer & Guarantee (woven, but worth a real hook) ---
    if luxury:
        add("offer", "applies", "ask_first", 45,
            "Lead with risk-reversal and a free design or color consult, not discounts. "
            "Discounting cheapens a premium brand.")
    else:
        add("offer", "applies", "ask_first", 45,
            "Give every campaign a real hook and a guarantee. A strong offer lowers what "
            "each lead costs.")

    # Rank: applies first, then by score. Assign 1-based priority across the list.
    plays.sort(key=lambda p: (_APP_RANK[p["applicability"]], -p["score"]))
    for i, p in enumerate(plays):
        p["priority"] = i + 1

    # Business state + a Mason-voiced headline.
    # "Dormant" means an old customer base that's the *cheapest* next play -- which is only
    # true when fresh demand isn't already pouring in. A shop drowning in leads is leaky or
    # growing, not dormant, even if it has an old base, so gate dormant on modest lead flow.
    trade = (business.get("trade") or "contractor").strip() or "contractor"
    area = (business.get("service_area") or "your area").strip() or "your area"
    if s["past_customers"] >= 50 and s["oldest_job_years"] >= 3 and ml < 15:
        state = "established_dormant"
        headline = (f"You've got a goldmine you're barely touching. A base of past {trade} "
                    f"customers in {area} coming due on their repaint cycle is the cheapest "
                    "revenue you'll ever book, so we mine that first.")
    elif ml >= 15 and missed_ratio >= 0.3:
        state = "high_volume_leaky"
        headline = (f"You've got the leads. You're dropping about {s['missed_leads']} of them. "
                    f"For a {trade} in {area}, whoever answers first wins the job — we plug "
                    "the leak before anything else.")
    elif s["years_in_business"] <= 2 and s["review_count"] < 20 and ml < 10:
        state = "new_invisible"
        headline = (f"Here is the straight version: you do great {trade} work in {area} "
                    "and almost nobody online knows it yet. You close what you get, so we "
                    "don't fix closing, we go get you found and put more at-bats in front of you.")
    else:
        state = "growing"
        headline = (f"Solid base for a {trade} in {area}. Now we compound it: get found, "
                    "keep the reviews fresh, and put your work in front of more of the right people.")

    woven = []
    want = (business.get("capacity_note") or "").strip()
    woven.append(f"Aim every play at the work you want more of: {want}" if want
                 else "Aim every play at the highest-value work you want more of, not "
                      "whatever walks in the door.")
    woven.append("Honesty is the brand: real numbers only, never a fabricated result or "
                 "review.")

    return {"state": state, "headline": headline, "woven": woven,
            "signals": s, "plays": plays}
