"""Cold email outreach (Phase 5) -- B2B partners only, CAN-SPAM by design.

Cold email is the first COLD channel. It is lawful without prior consent (unlike cold
SMS under TCPA), but only if every message is CAN-SPAM compliant: a real physical
mailing address, a clear opt-out, honest from/subject, and prompt suppression of
opt-outs. This module enforces the address + opt-out footer; the consent ledger and
DNC suppression handle the rest.
"""
import crypto


def can_spam_ready(business):
    """A business must have a physical mailing address before any cold email goes out."""
    return bool((business.get("mailing_address") or "").strip())


def footer(business, contact_id):
    """The CAN-SPAM footer appended to every outreach email: why they got it, how to
    opt out, and the sender's physical address."""
    addr = (business.get("mailing_address") or "").strip()
    area = business.get("service_area") or "your area"
    name = business.get("name") or "Our business"
    # The opt-out link carries an HMAC token bound to this contact id, so the public
    # unsubscribe endpoint can't be enumerated to opt out arbitrary contacts.
    token = crypto.sign_id("unsub", contact_id)
    return ("\n\n--\n"
            f"You received this because we partner with local businesses in {area}. "
            f"If you would prefer not to hear from us, reply STOP or opt out here: "
            f"/unsubscribe/{contact_id}?t={token}\n"
            f"{name}. {addr}")
