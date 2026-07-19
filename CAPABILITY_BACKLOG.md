# JobMagnet Capability Backlog

Tracks capabilities that were considered, built, or started — and either retired permanently or parked with a concrete re-evaluation trigger. Before killing or deferring any capability, write it here. Before proposing to revive one, read this file first.

See also: ROADMAP.md Guardrails — "When a killed or deferred capability comes up in planning, check CAPABILITY_BACKLOG.md first — last month's no may be this month's yes."

---

## DEAD (permanently retired)

### Cold AI voice to homeowners
**Retired:** 2026-07-19
**Why dead:** FCC treats AI voice as artificial/prerecorded — the highest-risk outreach category, with no realistic path to compliant cold use for consumer trades. The /cold UI was removed with it. The fail-closed messaging seam (`messaging.place_cold_voice`, consent ledger, DNC) remains in code as the enforcement layer, permanently blocked.

### Managed paid ads (Scale tier promise)
**Retired:** 2026-07-19
**Why dead:** `can_managed_ads` gated nothing — no code ever touched an ad account, and the tier copy overclaimed (AUDIT_TRUTH violation). Scale's paid story is now the LSA Concierge (real, guided). If ad-account management is ever revisited it is a new capability proposal (MONEY gate: spending tenant money), not a revival of this flag.

---

## PARKED — re-evaluate on trigger date

### Cold SMS to homeowners
**Re-eval trigger:** TCPA attorney sign-off obtained AND a tenant explicitly asks for it. No date — this does not age into viability.
**Why parked:** Cold marketing SMS requires prior express written consent per contact; the attorney review never happened; and Neighbor Mail now covers "cold reach to homeowners" lawfully (paper needs no consent). The /cold UI was removed 2026-07-19; the fail-closed seam (`messaging.send_cold_sms` + consent ledger + `JOBMAGNET_COLD_SMS` flag) remains and stays hard-blocked.
**Viability test:** Written attorney sign-off on the consent-capture flow, plus one real tenant with a lawful consented list.

---

### Neighbor Mail v1 — automated print-and-mail (Lob/PostGrid)
**Re-eval trigger:** ≥3 tenants have marked a v0 campaign "printed" (proof the assisted loop is used) OR one tenant asks for automation.
**Why parked:** v0 (assisted: draft + print view + USPS EDDM walkthrough) shipped 2026-07-19 with zero COGS and zero new legal surface. v1 spends tenant money per piece → MONEY gate: per-campaign budget approval UX + metered billing design must route through Finance + Jack before build.
**Viability test:** v0 usage evidence above; then a costed spec (per-piece margin, spend-cap UX) approved by Jack.

---

### New-owner welcome campaigns (deed-transfer triggered mail)
**Re-eval trigger:** Neighbor Mail v1 live AND a property-data source costed (ATTOM/county records per-lookup pricing validated).
**Why parked:** Perfect-timing demand creation (new owners renovate early) on the same mail rails, but it needs a paid property-data feed whose economics are unvalidated. Rails first, data second.
**Viability test:** Data source returns ≥90% of actual sales in one test county within 30 days of closing, at a per-record cost that keeps campaign CPL under blended LSA CPL (~$53).

### Conversational Walkthrough NLU
**Re-eval date:** 2026-09-30
**Why parked:** Free-text intake is compelling for mobile-native contractors, but extraction accuracy on trade-specific jargon has not been validated. The structured form delivers the same signal faster and more reliably right now.
**Viability test:** Model correctly extracts all 10 `normalize_signals()` values from 10 Heritage-style free-text responses at 90%+ accuracy in a blind test. Run against the actual field names in `db.py:_SIGNAL_COLS`.

---

### AI image generation for before/after visuals
**Re-eval date:** 2026-10-31
**Why parked:** Image generation is plausible for trade marketing but requires prompt tuning per trade, approval UX, and hosting — overhead that is not justified until the core content loop (text-based GBP posts, review requests) is proven in production.
**Viability test:** `generate_image()` produces trade-specific images the contractor would approve unchanged 60%+ of the time on 5 sample prompts, evaluated by at least one real Heritage-type contractor (not internal).

---

### Photo-by-text multimodal vision enhancement
**Re-eval date:** Triggered — after the basic SMS reply loop (P2-15) has been live and proven for 30 days.
**Why parked:** The basic photo-by-text loop (contractor texts a job photo → JobMagnet drafts a text-based GBP post) is being built first (P2-15). Vision-enhanced drafts require the base loop to be live, measured, and showing adoption before adding the model-cost overhead.
**Viability test:** Vision-enhanced draft is approved unchanged at 70%+ vs text-based baseline on 10 sample MMS inputs, measured in production on real contractor submissions (not synthetic).

---

## GRADUATED

None yet.
