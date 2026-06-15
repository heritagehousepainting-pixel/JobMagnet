"""Speed-to-Lead engine -- answer every inbound in seconds.

78% of multi-quote shoppers buy from whoever replies first, and a 5-minute reply
converts up to 100x better than 30 minutes. A contractor on a ladder can't do that;
this can. Pure response logic; timing + persistence live in db. The metric that
matters is time-to-first-touch.
"""
LEAD_CHANNELS = ("call", "form", "message", "referral", "other")
LEAD_STATUSES = ("new", "responded", "qualified", "booked", "lost")

# The 2-3 questions that actually qualify a job (kept short on purpose).
QUALIFY = [
    "What's the project?",
    "What's the address, so we confirm it's in our area?",
    "What's your timeline?",
]


def first_response_sms(business, name=""):
    """The instant text-back. Honest, fast, asks the one thing that moves it forward."""
    first = (name or "").split()[0] if (name or "").strip() else ""
    hi = f"Hi {first}, " if first else "Hi, "
    biz = business.get("name", "our team")
    return (f"{hi}thanks for reaching out to {biz}. We've got your message and will get "
            "you a call right back. Quick one so we can move fast: what's the project and "
            "the address? Reply here and we'll line up a fast quote.")
