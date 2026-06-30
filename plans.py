"""Plans & pricing -- what each tier costs and unlocks (pure registry).

Priced on value, not cost: COGS is ~$10-36/contractor/mo (see MARKET_ECONOMICS.md),
competitors charge ~$300 for less, and one extra booked job ($3-8k) pays back a plan
10-25x. Mason is in EVERY tier (he is the product); tiers differ by how much he's
allowed to DO -- advise (Pro) vs act on autopilot (Premium) vs managed ads (Scale).
"""

PLANS = {
    "pro": {
        "name": "JobMagnet Pro", "price": 199, "autopilot": False, "managed_ads": False,
        "text_cap": 750, "daily_cap": 40, "tagline": "JobMagnet advises. You approve every send.",
        "features": ["Game Plan + every engine",
                     "Drafts content, review requests & lead replies (you approve)",
                     "Texting line you connect (live once your number is linked)",
                     "Up to 750 texts / month"]},
    "premium": {
        "name": "JobMagnet Premium", "price": 299, "autopilot": True, "managed_ads": False,
        "text_cap": 2000, "daily_cap": 100, "tagline": "JobMagnet runs it on autopilot, within your rules.",
        "features": ["Everything in Pro", "Autopilot: acts on your behalf",
                     "Speed-to-Lead, Reactivation & Referrals",
                     "Closed-loop cost-per-booked-job", "Up to 2,000 texts / month"]},
    "scale": {
        "name": "JobMagnet Scale", "price": 599, "autopilot": True, "managed_ads": True,
        "text_cap": 6000, "daily_cap": 300, "tagline": "Premium plus managed ads & multi-location.",
        "features": ["Everything in Premium", "Paid-ads guidance (LSA + Meta budgets & copy)",
                     "Multi-location & multiple numbers", "Priority support",
                     "Up to 6,000 texts / month"]},
}
ORDER = ["pro", "premium", "scale"]
DEFAULT_PLAN = "pro"


def get(plan):
    return PLANS.get(plan or DEFAULT_PLAN, PLANS[DEFAULT_PLAN])


def can_autopilot(plan):
    return get(plan)["autopilot"]


def can_managed_ads(plan):
    return get(plan)["managed_ads"]


def text_cap(plan):
    """Monthly outbound SMS ceiling for the plan (a hard limit)."""
    return get(plan)["text_cap"]


def daily_cap(plan):
    """Per-day SMS ceiling for the plan -- carrier-friendly pacing so a blast drips
    instead of dumping. Derived from the monthly cap (~1/20th), and the reason a big
    review/reactivation blast spreads over a few days instead of firing all at once."""
    return get(plan).get("daily_cap") or max(1, get(plan)["text_cap"] // 20)
