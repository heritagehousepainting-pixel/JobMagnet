"""Offer & Guarantee engine -- give every campaign a real hook + risk-reversal.

Offer strength is inversely correlated with cost-per-acquisition (80% of winning
med-spa campaigns open with a low-barrier offer). But a premium/luxury shop should
lead with risk-reversal and exclusivity, NOT discounts, which cheapen the brand.
Pure suggestion logic from the Business Brain + the avg-job-value signal.
"""

LUXURY_THRESHOLD = 6000.0


def suggest(business, signals=None):
    """Suggested offers + a guarantee line, tuned to whether this is a premium shop."""
    signals = signals or {}
    try:
        avg = float(signals.get("avg_job_value") or 0)
    except (TypeError, ValueError):
        avg = 0.0
    luxury = avg >= LUXURY_THRESHOLD
    if luxury:
        offers = [
            "Free in-home design & color consult, no obligation",
            "Workmanship warranty in writing on every project",
            "Priority scheduling for projects booked this season",
        ]
        guarantee = ("We're not done until you're happy, in writing. That's the premium "
                     "standard.")
        note = ("You're premium. Lead with risk-reversal and exclusivity, not discounts. "
                "Discounting cheapens the brand and trains clients to wait for a deal.")
    else:
        offers = [
            "Free, no-obligation estimate with a same-day quote",
            "A set amount off any project booked this month",
            "Satisfaction guarantee: we make it right or you don't pay the balance",
        ]
        guarantee = "100% satisfaction guarantee. If it isn't right, we make it right."
        note = ("Give every campaign a real hook plus a guarantee. A strong, low-barrier "
                "offer lowers what each lead costs you.")
    return {"offers": offers, "guarantee": guarantee, "note": note, "luxury": luxury}
