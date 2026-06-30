# JobMagnet Capability Backlog

Tracks capabilities that were considered, built, or started — and either retired permanently or parked with a concrete re-evaluation trigger. Before killing or deferring any capability, write it here. Before proposing to revive one, read this file first.

See also: ROADMAP.md Guardrails — "When a killed or deferred capability comes up in planning, check CAPABILITY_BACKLOG.md first — last month's no may be this month's yes."

---

## DEAD (permanently retired)

None currently.

---

## PARKED — re-evaluate on trigger date

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
