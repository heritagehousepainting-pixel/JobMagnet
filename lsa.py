"""LSA Concierge -- guided setup + weekly hygiene for Google Local Services Ads.

LSA is the cheapest high-intent paid lead in home services (~$53 avg, pay-per-lead,
~44% book rate -- see MARKET_ECONOMICS.md). Most contractors either never finish
Google Screened verification or leave money undisputed on junk leads. This is the
structured checklist that walks both, mirroring getfound.py exactly (pure logic:
checklist definition + scoring; the route persists which items are done).

No LSA API is used or claimed: this is guided-workflow value, honestly labeled.
Keys are prefixed lsa_ so they can share the checklist store with Get Found.
"""

CHECKLIST = [
    {"key": "lsa_signup",   "label": "Local Services Ads account created",
     "help": "Start at ads.google.com/localservices. It's pay-per-lead, not per-click."},
    {"key": "lsa_license",  "label": "Trade license submitted",
     "help": "Google verifies your license as part of Google Screened."},
    {"key": "lsa_insurance", "label": "Proof of insurance submitted",
     "help": "General liability certificate. Verification fails silently without it."},
    {"key": "lsa_background", "label": "Background check completed",
     "help": "Free through Google's partner. This is the step most contractors stall on."},
    {"key": "lsa_profile",  "label": "Profile complete: services, hours, service area",
     "help": "List every service you actually offer. Each one is a matching chance."},
    {"key": "lsa_budget",   "label": "Weekly budget set to your target lead flow",
     "help": "Use the budget calculator below. Start small; raise it once leads book."},
    {"key": "lsa_reviews",  "label": "Review flow feeding your LSA rating",
     "help": "LSA rank leans on review count + rating. Your Reviews engine feeds this."},
    {"key": "lsa_answer",   "label": "Answering every LSA call/message fast",
     "help": "Google tracks responsiveness and ranks you down when calls go unanswered. Speed-to-Lead is built for this."},
    {"key": "lsa_disputes", "label": "Disputing junk leads every week",
     "help": "Wrong service, out of area, spam: dispute them in the Leads tab. Contractors leave real money here every month."},
]

CHECKLIST_KEYS = {item["key"] for item in CHECKLIST}


def score(done_keys):
    """Percent complete (0-100) against the canonical checklist."""
    done = len([k for k in (done_keys or set()) if k in CHECKLIST_KEYS])
    return int(round(100.0 * done / len(CHECKLIST)))


def next_steps(done_keys, limit=3):
    """The first unfinished items, in walk order -- what to do next."""
    done_keys = done_keys or set()
    return [item for item in CHECKLIST if item["key"] not in done_keys][:limit]
