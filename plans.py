"""Plans & pricing -- what each tier costs and unlocks (pure registry).

Priced on value, not cost: COGS is ~$10-36/contractor/mo (see MARKET_ECONOMICS.md),
competitors charge ~$300 for less, and one extra booked job ($3-8k) pays back a plan
10-25x. Mason is in EVERY tier (he is the product); tiers differ by how much he's
allowed to DO -- advise (Pro) vs act on autopilot (Premium) vs managed ads (Scale).
"""

PLANS = {
    "pro": {
        "name": "Mason Pro", "price": 199, "autopilot": False, "managed_ads": False,
        "text_cap": 750, "tagline": "Mason advises. You approve every send.",
        "features": ["Game Plan + every engine",
                     "Drafts content, review requests & lead replies (you approve)",
                     "Managed texting line included", "Up to 750 texts / month"]},
    "premium": {
        "name": "Mason Premium", "price": 299, "autopilot": True, "managed_ads": False,
        "text_cap": 2000, "tagline": "Mason runs it on autopilot, within your rules.",
        "features": ["Everything in Pro", "Autopilot: Mason acts on his own",
                     "Speed-to-Lead, Reactivation & Referrals",
                     "Closed-loop cost-per-booked-job", "Up to 2,000 texts / month"]},
    "scale": {
        "name": "Mason Scale", "price": 599, "autopilot": True, "managed_ads": True,
        "text_cap": 6000, "tagline": "Premium plus managed ads & multi-location.",
        "features": ["Everything in Premium", "Managed paid ads (LSA + Meta)",
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
    return get(plan)["text_cap"]
