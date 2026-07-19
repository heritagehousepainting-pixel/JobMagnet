"""Partner engine -- B2B referral relationships (realtors, PMs, designers, GCs, trades).

One realtor or property-manager relationship is a job stream for years; the miss is
that contractors never run the relationship. This engine gives every partner type a
compliant intro (sent through the CAN-SPAM outreach seam) and a recurring
portfolio-digest touch so the relationship is maintained, not just opened.

HARD GUARDRAIL (mirrors Nod's dual attestation, pending attorney review there):
licensed REALTORS and INSURANCE/RESTORATION contractors must never be offered cash
referral fees (RESPA / anti-kickback exposure). For those types the value exchange
is relationship-only: priority scheduling for their clients, fast quotes, a
portfolio they can hand out. JobMagnet has NO referral-fee ledger by design --
reward tracking is Nod's product; the cross-trade job network is TradeSource's.

Pure logic only (no DB, no Flask, no LLM): deterministic copy + the type registry.
"""

# Partner types. `cash_ok` False = the anti-kickback guardrail types.
PARTNER_TYPES = {
    "realtor": {
        "label": "Realtor", "cash_ok": False,
        "angle": ("Your listings move faster when they show well. We turn around "
                  "pre-listing work on short timelines, and your clients get "
                  "priority scheduling.")},
    "property_manager": {
        "label": "Property manager", "cash_ok": True,
        "angle": ("Turnovers on a deadline are our normal. One call, a fast quote, "
                  "and the unit is rent-ready on schedule.")},
    "designer": {
        "label": "Interior designer", "cash_ok": True,
        "angle": ("Your design deserves clean execution. We work to spec, protect "
                  "the site, and make your finished photos look right.")},
    "gc": {
        "label": "General contractor", "cash_ok": True,
        "angle": ("When your schedule stacks up, we slot in as a dependable sub "
                  "and hit the dates we give you.")},
    "insurance_restoration": {
        "label": "Insurance / restoration", "cash_ok": False,
        "angle": ("Claim work needs documentation and clean timelines. We provide "
                  "both, and homeowners get a local crew they can reach.")},
    "trade": {
        "label": "Complementary trade", "cash_ok": True,
        "angle": ("Our customers ask us who to call for adjacent work all the "
                  "time. Let's send each other the jobs we don't do.")},
    "other": {"label": "Other partner", "cash_ok": True,
              "angle": "We'd like to be the crew you recommend without worrying."},
}

DEFAULT_TYPE = "other"


def get_type(key):
    return PARTNER_TYPES.get((key or "").strip() or DEFAULT_TYPE,
                             PARTNER_TYPES[DEFAULT_TYPE])


def cash_reward_allowed(key):
    """False for the anti-kickback types (realtor, insurance/restoration). The UI
    must never suggest cash referral fees for these."""
    return get_type(key)["cash_ok"]


def intro_email(business, contact, ptype=None):
    """Deterministic partner intro: {'subject','body'}. Short, honest, no hype;
    the CAN-SPAM footer is appended by the outreach seam at send time."""
    t = get_type(ptype or contact.get("partner_type"))
    biz = business.get("name", "Our business")
    trade = (business.get("trade") or "home services").strip() or "home services"
    area = (business.get("service_area") or "the area").strip() or "the area"
    first = (contact.get("name") or "there").split()[0]
    subject = f"{biz} — a reliable {trade} partner in {area}"
    body = (
        f"Hi {first},\n\n"
        f"I run {biz}, a {trade} business in {area}. {t['angle']}\n\n"
        "If it's useful, I'll send over a short portfolio of recent local work "
        "and how we handle scheduling. And if you ever need a fast answer for a "
        "client, you can reach me directly.\n\n"
        f"— {biz}"
    )
    return {"subject": subject, "body": body}


def digest_email(business, recent_posts):
    """The recurring quarterly touch: a short portfolio digest built from real
    recent work (approved/published posts). Returns None when there's nothing real
    to show -- we never pad a digest with filler."""
    items = [(p.get("topic") or "").strip() for p in (recent_posts or [])
             if (p.get("topic") or "").strip()][:5]
    if not items:
        return None
    biz = business.get("name", "Our business")
    trade = (business.get("trade") or "home services").strip() or "home services"
    subject = f"Recent work from {biz}"
    lines = [f"Hi,\n\nA quick look at what {biz} has been up to lately:"]
    lines += [f"  • {i}" for i in items]
    lines.append(f"\nIf any of your clients need {trade} work handled well, we'd "
                 f"be glad to take care of them.\n\n— {biz}")
    return {"subject": subject, "body": "\n".join(lines)}


def reward_note(ptype):
    """The line the UI shows about how to thank this partner type. Encodes the
    guardrail in user-facing copy."""
    t = get_type(ptype)
    if not t["cash_ok"]:
        return (f"Heads up: never offer a {t['label'].lower()} cash referral fees "
                "(anti-kickback rules, e.g. RESPA). Thank them with priority "
                "scheduling and fast quotes for their clients instead.")
    return ("Want to reward referrals from this partner? Track rewards properly "
            "with Nod (getnod) rather than informal cash — it keeps the record "
            "clean for both sides.")
