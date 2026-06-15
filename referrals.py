"""Referrals & Plans engine -- turn happy customers into warm, free leads.

Retention/referral is 5 to 7x cheaper than new acquisition, and the ask lands best at
peak happiness (right after the job, or right after a 5-star review). Pure message
logic; sends go through the consent-gated messaging seam.
"""


def referral_ask_sms(business, name=""):
    first = (name or "").split()[0] if (name or "").strip() else ""
    hi = f"Hi {first}, " if first else "Hi, "
    biz = business.get("name", "our team")
    return (f"{hi}it was a pleasure working with you. If you know anyone who could use "
            f"{biz}, an intro means a lot to a local business like ours, and we'll take "
            "great care of them. Thank you either way.")


def maintenance_pitch(business):
    """One-line pitch for a recurring maintenance/touch-up plan (the lock-in)."""
    biz = business.get("name", "our team")
    return (f"Ask about the {biz} touch-up plan: a yearly visit to keep everything looking "
            "fresh, with priority scheduling. It keeps your home sharp and saves you the "
            "big repaint later.")
