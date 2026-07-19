"""Neighbor Mail engine -- radius direct mail around every completed jobsite.

The one lawful COLD channel to homeowners: physical mail needs no prior consent
(no TCPA, no CAN-SPAM), and a finished job is proof the whole street can already
see. Each completed job becomes a small campaign: a neighbor letter + a door
hanger for the closest homes, anchored to the jobsite street.

v0 is ASSISTED and honest about it: JobMagnet drafts the copy and renders a
print-ready page plus USPS EDDM instructions (EDDM mails whole carrier routes
around an address -- no name/address list needed, ~$0.24/piece retail). No mail
API is wired yet, so mode is always "assisted"; a print/mail provider (Lob,
PostGrid) can flip campaigns to "live" later without changing this module.

Pure logic only (no DB, no Flask): copy generation + status/mode rules, mirroring
speedtolead.py/referrals.py so it's trivially testable.

Known v0 limitation (deliberate): ONE campaign per customer, not per job — the
contacts model stores only last_job_at, and re-mailing the same street on a repeat
job would waste pieces anyway. If repeat-job campaigns are ever wanted, that needs
a per-job table (see CAPABILITY_BACKLOG.md, Neighbor Mail v1).
"""

# Campaign lifecycle: drafted -> owner approved -> printed & dropped at USPS.
STATUSES = ("draft", "approved", "printed")

# Default piece count: one carrier route is typically ~300-600 homes; a tight
# "the closest streets" drop is 50. The owner can change it per campaign.
DEFAULT_PIECES = 50


def mail_mode():
    """Honest capability flag. 'assisted' until a print-and-mail provider is wired;
    never claim automated sending before it exists."""
    return "assisted"


def _street(address):
    """The street part of a jobsite address for social-proof copy ('on Elm St').
    First comma-segment, house number stripped so we never print the customer's
    exact address to their neighbors."""
    part = (address or "").split(",")[0].strip()
    words = part.split()
    if words and words[0].replace("-", "").replace("/", "").isdigit():
        words = words[1:]
    return " ".join(words).strip()


def neighbor_letter(business, job):
    """The letter to nearby homes. job: {address, service, customer_name(optional)}.
    Honest social proof: names the street (never the house), the real work done,
    and a plain invitation. No fake urgency, no fabricated discounts."""
    biz = business.get("name", "Our team")
    trade = (business.get("trade") or "work").strip() or "work"
    phone = (business.get("phone") or "").strip()
    site = (business.get("website") or "").strip()
    street = _street(job.get("address", ""))
    service = (job.get("service") or trade).strip() or trade
    where = f" on {street}" if street else " in your neighborhood"
    lines = [
        f"Hello neighbor,",
        "",
        f"We just finished a {service} project{where}, so you may have seen our "
        f"crew nearby. We're {biz}, a local {trade} business, and most of our work "
        "comes from neighbors of jobs like this one.",
        "",
        "If your home could use similar work, or you'd just like a price to plan "
        "around, we're happy to take a look while we're in the area. No pressure "
        "either way.",
        "",
        f"— {biz}",
    ]
    contact_bits = [b for b in (phone, site) if b]
    if contact_bits:
        lines.append("  " + "  ·  ".join(contact_bits))
    return "\n".join(lines)


def door_hanger(business, job):
    """Short-form copy for a door hanger / postcard front. Same honesty rules."""
    biz = business.get("name", "Our team")
    trade = (business.get("trade") or "work").strip() or "work"
    phone = (business.get("phone") or "").strip()
    street = _street(job.get("address", ""))
    service = (job.get("service") or trade).strip() or trade
    where = f"on {street}" if street else "in your neighborhood"
    head = f"We just finished a {service} project {where}."
    body = (f"{biz} — local {trade}. If your home is next, we'll gladly stop by "
            "for a look while we're in the area.")
    return f"{head}\n{body}" + (f"\nCall or text: {phone}" if phone else "")


def eddm_steps(pieces=DEFAULT_PIECES):
    """USPS Every Door Direct Mail: how the owner actually gets this delivered
    without any address list. Real steps, current pricing ballpark stated as such."""
    return [
        "Print the letter or postcard (postcard must be EDDM-sized, e.g. 6.5\" x 9\").",
        "Go to usps.com/business/every-door-direct-mail.htm and open the EDDM map tool.",
        "Enter the jobsite address and pick the carrier route(s) covering the "
        "surrounding streets (routes are ~300-600 homes; you can start with one).",
        f"Pay retail EDDM postage (about $0.24/piece as of 2026 — roughly "
        f"${pieces * 0.24:,.0f} for {pieces} pieces; verify current pricing at USPS).",
        "Bundle the pieces per USPS instructions and drop them at the local Post "
        "Office that serves those routes.",
        "Log what you spent under Results → Direct mail so cost-per-booked-job "
        "stays honest.",
    ]


def campaign_from_job(business, job, pieces=DEFAULT_PIECES):
    """Assemble a full draft campaign dict from a completed job. The route persists
    it; nothing here sends or spends anything."""
    return {
        "job_address": (job.get("address") or "").strip(),
        "service": (job.get("service") or "").strip(),
        "pieces": max(1, int(pieces or DEFAULT_PIECES)),
        "letter_body": neighbor_letter(business, job),
        "hanger_body": door_hanger(business, job),
        "status": "draft",
        "mode": mail_mode(),
    }
