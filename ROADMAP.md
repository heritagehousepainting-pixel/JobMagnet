# JobMagnet — Build Roadmap (committed 2026-06-15)

The concrete, ordered plan we build to. Supersedes the naive "M1→M10" order with a
sequence chosen for **real, dogfoodable value at every step** and **risk-ascending**
channels. Grounded in [PRODUCT_SPEC.md](PRODUCT_SPEC.md) (the modules),
[MARKET_ECONOMICS.md](MARKET_ECONOMICS.md) (the numbers), and
[STRATEGY.md](STRATEGY.md) / [COMPETITORS.md](COMPETITORS.md) (the wedge).

**Product in one line:** the compliant AI marketing team built for the trades —
it creates demand AND books it, proven in cost-per-booked-job.

---

## Committed architecture decisions

1. **Standalone first, RingBack optional.** JobMagnet stands on its own: its own
   gated messaging seam, its own consent ledger, its own conversion/attribution
   data. **RingBack is a pluggable provider** — when a tenant connects it, JobMagnet
   gets richer booking data and can share the SMS rails; when not, JobMagnet works
   fully alone. This widens the market (sell JobMagnet solo) and still delivers the
   closed loop for RingBack users. Resolves the old open question in STRATEGY §9.
   → Design every outbound/booking touchpoint behind a **provider interface** so
   RingBack (or Twilio, or a future partner) is a swappable backend, never a hard
   dependency.

2. **First phase = Reviews (M2).** Fastest path to *real* (non-simulated),
   low-risk, dogfoodable value.

## Sequencing principles (why this order)

- **Real beats more** — every phase ships something Heritage can actually use; never
  simulated-as-real (RingBack's honesty discipline).
- **Risk-ascending** — warm/transactional + owned channels first; cold outbound
  consent-gated and last; AI voice dead last, attorney-reviewed.
- **Dodge the OAuth gauntlet early** — channels we can make real fast (SMS review
  links, Google Business Profile) before the Meta/IG app-review limbo.
- **Assemble the moat, don't front-load it** — the cost-per-booked-job loop is wired
  *after* live channels + conversion data exist, not on an empty dataset.
- **Thin vertical slices** — each phase is a working loop, not a horizontal module.

---

## The phases

### Phase 0 — Messaging & consent seam  *(small, foundational)*
JobMagnet's own gated outbound spine. Mirrors RingBack's pattern.
- `messaging` seam: one `send_sms` / `send_email` path that is **simulated until a
  provider is configured** (Twilio/SMTP creds), behind a **provider interface** so
  RingBack can plug in later.
- `contacts` + `contacts_consent` ledger; opt-out (STOP) handling; quiet hours.
- Honest "simulated vs live" status in the UI, like content publishing.
- **Done when:** a consent-checked message sends (simulated) through one path, and
  flipping a cred makes it real; opt-outs are recorded and enforced.

### Phase 1 — Reviews & Reputation (M2)  ← **building first**
First *real* outbound. Review requests go to your **own past customers** (warm,
existing relationship → low legal risk, not cold).
- Minimal customer/job record + CSV import + "request a review" action (and a
  later auto-trigger on job completion).
- SMS (and email) review invite with the tenant's Google review link.
- Review monitoring (Google first) + **AI-suggested responses** from the Brain.
- Surface review velocity (feeds the ROI dashboard later).
- **Done when:** Heritage sends a real review request and drafts a response.

### Phase 2 — Content & Local engine (M1 finish + M3)
The compounding owned-channel asset.
- Content **calendar + scheduling** (uses the existing `scheduled_for` column).
- **Photo-by-text capture** (text a job photo → AI drafts a post) — killer
  trades-native input, on the Phase 0 messaging rails.
- AI **image / before-after** generation.
- **GBP publishing (real)** — dodges the Meta gauntlet, doubles as SEO; **assisted
  copy/paste + download** for Facebook/Instagram until OAuth app-review clears.
- **Schema markup** (LocalBusiness/Service/FAQ) + **AEO** answer-first pages.
- **Done when:** Heritage's real social/GBP cadence runs from JobMagnet.

### Phase 3 — Closed-loop ROI dashboard (M10) + conversion data
The moat. Now there's activity to measure.
- Own conversion capture: tracked numbers, UTM, manual "mark won," **plus optional
  RingBack booking feed** via the provider interface.
- **Cost per booked job** per channel; recovered/created revenue, not impressions.
- **Done when:** the dashboard shows $/booked-job per channel for Heritage.

### Phase 4 — Paid ads assist (M7) + Lead engine (M8)
- **LSA-first** setup/optimization (cheapest qualified lead), then Search, then Meta.
- Contact/lead engine; DNC scrubbing + suppression; optional intent signals.

### Phase 5 — Cold email (M4)  *(first cold channel)*
- B2B partner outreach (realtors, PMs, GCs, insurance) — **not homeowners**.
- **CAN-SPAM by design:** opt-out, physical address, honest from-name, suppression.

### Phase 6 — Cold SMS / Voice (M5 / M6)  *(gated, last)*
- TCPA written-consent gate (SMS); FCC artificial-voice gate (voice).
- **Default OFF; ships only after a TCPA attorney reviews the consent flows.**

---

## Status

- **M0 Business Brain + platform** — built, audited & hardened 2026-06-15
  (multi-tenant leak fixed, CSRF added, tests isolated → 38/38).
- **M1 Social engine (core)** — built, MiniMax live; publishing simulated;
  scheduling/photo-by-text/images = Phase 2.
- **Next:** Phase 0 seam → Phase 1 Reviews.

## Guardrails (carried from RingBack, every phase)
Every integration a safe no-op until configured · honest "simulated vs live" UI ·
nothing blocks the hot path · consent ledger is the spine of all outbound · pure,
testable decision logic · compliance gates are hard gates, not warnings.

## The Assistant layer (packaging — see PRODUCT_SPEC §The Assistant)
The named persona is the *face* over M0–M10, not a new build — it surfaces what the
modules already do as one character with two jobs (daily briefing + chief of marketing),
tiered Basic / Pro (advisor, you approve) / Premium (~$300/mo, guarded-autonomous).
Sequencing implication: **build the modules to be assistant-narratable from the start** —
every action emits a plain-English "what I did / why / what's next" event so the daily
briefing and approval queue are free byproducts, not a bolt-on. **Premium autonomy is
gated by the same hard compliance gates above:** it acts freely on owned/warm channels,
but every regulated/cold touch (M4–M6) stays rule-bound or one-tap-approved — never
silent-fire. The persona ships meaningfully once Phase 1–2 give it real work to narrate.

**Mason's home (the shell):** a later surface that makes Mason the *front door* — a
persistent conversation (daily rundown + approval queue + wins) that **wraps the existing
routes**, turning the feature-grid into back rooms he operates. Not a rewrite; a
conversational layer + per-tenant memory that accrues his "character" per user. Build the
narration events (above) first; the shell renders them. **Production guardrail every
phase:** the voice is the wrapper — each capability must beat a real PA agency on results /
speed / price / trade-nativeness, measured in cost-per-booked-job, or it doesn't ship.
