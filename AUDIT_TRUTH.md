# Truthfulness Audit — "say only what we actually do"

**Goal (2026-06-15):** Every button, link, status, and marketing claim across the
whole site must be TRUE against the code as it stands. Catch overclaims: anywhere we
imply we DO something / CONNECT to a provider / something is LIVE when the code
actually simulates it, gates it off, logs locally, or doesn't do it.

## Method
A 3-lane parallel audit (read-only agents report; fixes applied centrally):
- **Lane A — Public site:** home, pricing, how-it-works, contact, auth. Every CTA/link
  destination + every product claim vs real capability.
- **Lane B — App buttons & links:** every signed-in template's buttons/forms/links →
  do they hit a real route that does the real thing? Honest success messages?
- **Lane C — Connector honesty (core):** the integration seams (Twilio SMS, SMTP email,
  GBP/Meta publishing, Stripe billing, FirstBack feed, AI brain). Are "live/connected/
  simulated" statuses driven by real config checks? Do we ever claim a live connection
  that's actually a no-op?

Severity: P0 = false/could mislead a paying customer or legal risk · P1 = overclaim ·
P2 = minor wording.

## Then
Consolidate → fix overclaims (make copy/labels honest, or gate them) → keep the 260-test
suite green → re-walk routes → reconcile SETUP_NEEDED.md.

## Done when
Every audited claim is either TRUE as written, or corrected to be honest (or honestly
labeled simulated/gated). Suite green, all routes 200.
