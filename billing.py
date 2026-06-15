"""Stripe billing -- real subscriptions via Stripe Checkout + Customer Portal + webhooks.

Same honesty discipline as every other seam: a SAFE NO-OP until STRIPE_* is configured.
When keys are absent, `billing_live()` is False and the plan buttons fall back to an
in-app switch (dev), so nothing breaks. When keys are present, the buttons open real
Stripe Checkout and the webhook keeps the tenant's plan in sync with their subscription.

Card data never touches us -- Stripe Checkout is hosted and PCI-compliant.
"""
from config import (STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET,
                    STRIPE_PRICE_PRO, STRIPE_PRICE_PREMIUM, STRIPE_PRICE_SCALE)

PRICE_IDS = {"pro": STRIPE_PRICE_PRO, "premium": STRIPE_PRICE_PREMIUM, "scale": STRIPE_PRICE_SCALE}


def billing_live():
    """True only when the secret key AND all three price IDs are configured."""
    return bool(STRIPE_SECRET_KEY and all(PRICE_IDS.values()))


def _stripe():
    import stripe  # lazy: only needed (and only imported) when billing is live
    stripe.api_key = STRIPE_SECRET_KEY
    return stripe


def plan_for_price(price_id):
    for plan, pid in PRICE_IDS.items():
        if pid and pid == price_id:
            return plan
    return None


def create_checkout_url(business, plan, success_url, cancel_url):
    """A Stripe Checkout session for a subscription to `plan`. Returns the hosted URL."""
    s = _stripe()
    kwargs = dict(mode="subscription",
                  line_items=[{"price": PRICE_IDS[plan], "quantity": 1}],
                  success_url=success_url, cancel_url=cancel_url,
                  client_reference_id=str(business["id"]),
                  metadata={"business_id": str(business["id"]), "plan": plan})
    if business.get("stripe_customer_id"):
        kwargs["customer"] = business["stripe_customer_id"]
    return s.checkout.Session.create(**kwargs).url


def create_portal_url(business, return_url):
    """A Stripe Customer Portal session so the tenant manages/cancels their own plan."""
    s = _stripe()
    return s.billing_portal.Session.create(
        customer=business["stripe_customer_id"], return_url=return_url).url


def parse_event(payload, sig_header):
    """Verify a webhook (raises on bad signature) and normalize the events we act on.
    Returns a dict or None. None for events we ignore."""
    if not STRIPE_WEBHOOK_SECRET:
        return None
    s = _stripe()
    event = s.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    etype, obj = event["type"], event["data"]["object"]
    if etype == "checkout.session.completed":
        bid = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("business_id")
        return {"business_id": int(bid) if bid else 0,
                "plan": (obj.get("metadata") or {}).get("plan"), "status": "active",
                "customer_id": obj.get("customer"), "subscription_id": obj.get("subscription")}
    if etype in ("customer.subscription.created", "customer.subscription.updated"):
        price = obj["items"]["data"][0]["price"]["id"]
        return {"business_id": 0, "customer_id": obj.get("customer"),
                "subscription_id": obj.get("id"), "plan": plan_for_price(price),
                "status": obj.get("status")}
    if etype == "customer.subscription.deleted":
        return {"business_id": 0, "customer_id": obj.get("customer"),
                "subscription_id": obj.get("id"), "plan": "pro", "status": "canceled"}
    return None
