# JobMagnet × Anthropic's Growth Playbook — Applied Plan

**Source:** Lenny's Podcast interview with Amol (Head of Growth at Anthropic) — on activation, friction, quality-as-growth, automating growth with AI, and "leaving money on the table."
**Method:** A brainstorm → audit → fix loop run by two Sonnet agents in parallel across 3 rounds (17 ideas → audited against this repo with `file:line` evidence → adversarially critiqued → consolidated). Every action below was verified against the actual code.
**Scope:** JobMagnet only. Standalone product. (Date: 2026-06-30.)

---

## TL;DR

**JobMagnet already embodies ~65–70% of this growth playbook by design.** JobMagnet's "not yet" restraint, the per-channel autonomy elections, the Type-1 compliance hard-gates, and the four-stage growth loop are all already in the architecture. **The gaps are almost entirely wiring problems, not conceptual ones** — the highest-leverage work is connecting circuits that already exist, not inventing new modules:

- `_briefing()` has no `signals` param, so the already-written "I won't pretend there's a goldmine" copy **never reaches the screen**.
- `_route_system()` never injects the Mandate, so every chat session **starts cold** and JobMagnet can contradict the contractor's own elections.
- `connections_save()` has no activation hook, so the **highest-intent moment** (saving a credential) ends on a generic page.
- A fifth `_FACT_WIN` entry has **no matching `WINS` key**, so the first-win celebration can render "First win: First win" with no CTA.

**Closing 5 ship blockers + fixing 3 silent wiring bugs + surfacing the existing restraint copy moves ship-readiness from 6/10 → ~8/10 without adding a single new module.**

> **Why this matters (the alignment verdict):** the structural choices Anthropic's growth team reached *empirically* — restraint-as-trust, intake data threading through every touchpoint, autonomy elections as activation, the growth loop as the operating model, a "for them" test inside every recommendation — JobMagnet designed in *from the start*. The implication: **unusually high ROI per engineering hour.** Fixing a function signature or adding 15 lines (each under two days) unlocks capability that would take weeks to design from scratch at most products.

---

## Lesson scorecard

Status: ✅ already embodies · 🟡 partial (wire it) · 🔴 gap · ⚙️ adjust to JobMagnet's context

| # | Lesson | Status | Reality → how to sharpen |
|---|--------|:---:|---|
| L1 | Activation is the highest lever | 🟡 | `firstwin.achieved()` + `onboarding_milestone` are wired, but the funnel has **one** measurement point and the post-connection moment dead-ends. → Instrument 3 stages; make `milestone.achieved_at` the north-star; fix the orphaned-win-id bug. |
| L2 | The *right* friction increases conversion | 🔴 | No commitment questions exist. The `capacity_note` wire in `mandate.py:236-239` is correct but the textarea is **absent** and the POST handler silently drops it. → Add `success_metric` + a bottleneck question, captured explicitly. |
| L3 | "For them" reconciliation rule | ✅ | Every play in `mandate.diagnose()` carries `applies`/`not_yet`/`gated` + a reason with real signal values; the Walkthrough teaches before asking. The rule is enforced in code. → Add a one-line reconciliation note when JobMagnet's top play ≠ the contractor's stated pain. |
| L4 | Ask who they are → recommend the right thing | 🟡 | `trade` is captured and used in `generate_faq`, but `designate()` ignores it and all Mandate headlines are static. → Trade-aware `designate()`; trade+city in headlines. |
| L5 | Quality drives growth | 🟡 | Tests are strong; first-session quality is broken in 3 spots (missing textarea, generic headlines, dead `_briefing` signature). → One sprint scoped to *Walkthrough-submit → first-win-achieved* only. |
| L6 | Intake data is juice that keeps giving | 🟡 | Signals drive `diagnose()`/`designate()` but never reach `_route_system()`; `aeo_faq` leaves the user a *to-do*, not an artifact. → Wire signals into chat; auto-generate the FAQ; host it publicly. |
| L7 | Break dense screens into steps | 🔴 | `walkthrough.html` is 10+ inputs on one scroll — the primary mobile bounce point. → 2-step wizard with `session` persistence on Back. |
| L8 | Cold-start / capability overhead | 🔴 | `connections_save()` and `google_callback()` both redirect to a generic `/connections` with no JobMagnet callout; the photo-by-text loop never replies. → Post-connection unlock callout; close the MMS reply loop. |
| L9 | Bigger bets if AI-first | ✅ | JobMagnet *is* the product; north-star = cost-per-booked-job; scope is 1–2 PA trades. The big AI-first bet is made by design. → Add a milestone gate: no new module until a real first win lands. |
| L10 | Automate growth with the AI itself (the loop) | 🟡 | Identify/build/test stages exist; **analyze is broken** — `reviewsync.pull_reviews()` returns `pending` unconditionally even when GBP is connected. → Fix the reviews pull; add stall detection. |
| L11 | Proactive scheduled agents | 🟡 | Heartbeat + weekly digest exist, but the brief is pull-based/web-only — a contractor at 6:30am on a job site won't open a browser. → Milestone-gated morning SMS/email; structured weekly read. |
| L12 | Arm the AI with structured context | 🟡 | The Mandate is a typed schema — *better* than any notebook channel — but `_route_system()` never references it. → Inject `mandate_block` using the pattern already in `_h_game_plan()` (~15 lines). |
| L13 | Leave money on the table | ⚙️ | Real Type-1 hard gates exist in `messaging.py`, but there's no `COMPLIANCE.md` for an attorney to review and the restraint voice is absent from every template. → Externalize the gates; add the trust callout. |
| L14 | Telling a user *not* to do something builds trust | ⚙️ | The `not_yet` copy (`mandate.py:167-169`, "no dormant goldmine… I won't pretend there is") is the best trust copy in the product and has **zero output pathway**. → Fix `_briefing()`; surface it. |
| L15 | Focus / freedom through constraints | 🟡 | Correctly scoped, but cold-outbound gating is time-based, not milestone-based, and blockers stay unshipped. → Milestone-gate M4–M6; add a PMF constraint. |
| L16 | Builder operating model | 🟡 | The test suites are a machine-readable spec, but sub-day changes still get PRDs while sub-2-day blockers sit documented-but-unshipped. → Adopt a 2-day build protocol (see Adjust-warnings). |
| L17 | Ship-to-learn & adaptability | 🟡 | Provider abstraction enables model swaps, but killed capabilities (conversational onboarding, image-gen, multimodal photo) have **no re-eval dates**. → `CAPABILITY_BACKLOG.md` with quarterly viability tests. |

---

## Prioritized action plan

Badges: `take` = adopt directly · `adjust` = adapt to JobMagnet's context · **SHARPEN** = exploit something already built · **BUILD** = net-new.

### P0 — do these before onboarding any paying tenant

**1. Close the 5 ship blockers** · `take` · effort M · SHARPEN
- **What:** In order — (1) set `JOBMAGNET_SECRETS_KEY` (`config.py:116` empty default → creds cleartext; 10 min); (2) wire live Twilio (`messaging.py:31-38` is the simulated fallback) and send a real test SMS; (3) **start A2P 10DLC brand+campaign registration today** — carrier approval is 2–4 weeks and on the critical path; (4) wire email delivery + SPF/DKIM/DMARC; (5) implement `reviewsync.pull_reviews()` against the GBP Reviews API (`reviewsync.py:24-34` returns `pending` unconditionally). Add a milestone gate to `ROADMAP.md`: no new module until Heritage has sent a real SMS review request and a real Google review was pulled as a result.
- **Why:** One real review-request outcome on a real Heritage customer proves the *entire* stack (messaging seam, consent ledger, GBP OAuth, review pull, ROI attribution) against reality — and it's the only story tellable to the next contractor. The growth loop's "analyze" stage is dead until `pull_reviews()` works.
- **Where:** `config.py:116`, `messaging.py:31-38`, `reviewsync.py:24-34`, `SHIP_READINESS.md`, `ROADMAP.md`.

**2. Reconcile the first-win `WINS` / `_FACT_WIN` tables (orphaned-win-id display bug)** · `take` · effort S · SHARPEN
- **What:** `_FACT_WIN` (`firstwin.py:39`) has a fifth entry whose win id is **not a key in `WINS`** (`firstwin.py:9-18`). Remove the out-of-scope fifth entry from `_FACT_WIN` and from `first_win_facts()` (`db.py:1505-1507`); that SQL row also has a duplicated-literal bug. ~4 lines deleted, no new code. (Going forward: every id `achieved()` can return must have a `WINS` entry.)
- **Why:** When `achieved()` returns that id, `WINS.get(id, {})` → `{}`, so the celebration renders "First win: First win" with no CTA route and no nudge — a silently broken UI state, no error raised.
- **Where:** `firstwin.py:39`, `db.py:1505-1507`.

**3. Instrument the 3-stage activation funnel** · `take` · effort S · SHARPEN
- **What:** Stage 1 `walkthrough_started_at` (idempotent, via `_ensure_columns` — **not** `_BUSINESS_COLS`); Stage 2 = ≥1 `playbook_elections` row (exists); Stage 3 = `onboarding_milestone.achieved_at` (already written by `first_win_block()`). Add `db.activation_funnel_counts()`; surface as an admin line on `/dashboard` gated to `biz id==1`. In `/tasks/tick`, add stage-aware re-engagement (stage-2 with no win after 7d; stage-1 with no elections after 48h).
- **Why:** The Mercury lesson worked because *real activation* (not form completion) was measured. `milestone.achieved_at` is the real activation event; make it the primary metric so every Walkthrough change is measured against outcomes, not form-fills.
- **Where:** `db.py` `init_db()` (~after line 331), `app.py:603` + `app.py:569-600`, `templates/command.html`.

### P1 — the wiring + first-session quality sprint

**4. Fix `_briefing()` signature and surface the restraint copy** · `take` · effort S · BUILD
- **What:** Change `_briefing(biz, stats, drafts, due_count, mandate_ready)` → add `signals=None`; update both call sites (`app.py:318`, `app.py:340`) to pass `db.get_signals(biz['id'])`. Inside, pull `not_yet` plays from `mandate.diagnose()` into a `brief_passed_on` dict; render one line: *"I'm holding off on [label] — [reason]."* Rewrite the all-caught-up state to lead with what JobMagnet **did** ("I scheduled your Wednesday GBP post"), not that the queue is empty.
- **Why:** `mandate.py:167-169` ("…no dormant goldmine to mine yet, and I won't pretend there is.") is the best trust copy in the product and currently has **no output pathway**. This is the voice rule the spec promises and the differentiator no horizontal tool can match.
- **Where:** `app.py:226-253`, `:318`, `:340`; `templates/command.html`, `templates/dashboard.html`.

**5. Fix Walkthrough POST capture for Business-Brain fields** · `take` · effort S · SHARPEN
- **What:** The POST handler captures only signal-comprehension keys, so `capacity_note` (a Brain column) and a new `success_metric` are **silently dropped**. After `save_signals()`, add explicit `request.form.get()` calls and a separate `db.update_business()` write for Brain columns.
- **Why:** `mandate.py:236-239` already injects "Aim every play at the work you want more of: {want}" as the first woven note — but the value is never captured. It's a latent bug *and* a missed personalization.
- **Where:** `app.py:609-614`, `db.py` `_BUSINESS_COLS:25` + `init_db()`, `templates/walkthrough.html`.

**6. Post-connection capability-unlock callout** · `take` · effort S · BUILD
- **What:** In `connections_save()` and `google_callback()` set a `session` flag before redirect. **Render the callout on `/connections`** (both redirect there, *not* `/dashboard`): *"SMS is live. I have {backlog} customers I can text a review request to today — head to /reviews."* (GBP variant → /getfound.)
- **Why:** Saving a credential is the highest-intent moment in the product and it currently dead-ends on a generic page. This collapses integration-saved → first-outcome-offered to one page load.
- **Where:** `app.py:1458-1471`, `:1503-1520`, `/connections` GET; `templates/connections.html`.

**7. Wire the Mandate into `_route_system()`** · `take` · effort S · BUILD
- **What:** In `assistant.py:403-422`, after `taught_block`, add ~15 lines copying the proven pattern from `_h_game_plan()` (`:239-252`): top-2 `applies` plays + first `not_yet` play with reason. `import db`/`import mandate` are already present.
- **Why:** Every chat starts cold today — a contractor who set a play to "Not yet" can get JobMagnet recommending it in the same session, the worst trust signal an assistant can produce.
- **Where:** `assistant.py:403-422`.

**8. Trust callout above the Mandate election buttons + "last updated"** · `take` · effort S · BUILD
- **What:** One card above the elections: what JobMagnet does autonomously, what always comes to you first, and *"If an ad isn't worth it, I'll say so."* Add a `Last updated` line from `playbook_elections.updated_at`.
- **Why:** The election screen is exactly when the "will it just burn my money?" objection resolves; the voice rule is in the spec but absent from every template.
- **Where:** `templates/mandate.html`.

**9. Freeze cold outbound behind a milestone gate** · `take` · effort S · SHARPEN
- **What:** Change M4/M5/M6 gating in `ROADMAP.md` from time-based to milestone-based: frozen until (a) a real `firstwin.achieved()` outcome for a tenant, (b) that tenant is paying, and (c) a TCPA attorney has signed off in writing. Move M4–M6 to a "Parked — milestone-gated" section.
- **Why:** M4–M6 need TCPA infra, cold-list sourcing, cold-campaign A2P, and attorney review. Building them before warm-channel value is proven is the classic trades-agency mistake.
- **Where:** `ROADMAP.md`; `firstwin.py:40-47` is the machine-readable test for (a).

**10. Walkthrough quality sprint: 2-step split + trade-specific Mandate headlines** · `take` · effort S · SHARPEN
- **What:** (1) Split `/walkthrough` into 2 steps (`data-step` + JS switcher, no reloads) with `session['walkthrough_step1']` persistence. (2) Add the `capacity_note` + `success_metric` textareas (depends on #5). (3) Rewrite the 4 static headlines in `mandate.py:213-233` to reference `business['trade']` + `service_area` (e.g., *"You've done {past_customers} {trade} jobs in {service_area}; the oldest goes back {oldest_job_years} years — that list is your cheapest next booking."*).
- **Why:** The Walkthrough is the front door; a mobile bounce here means no Mandate, no activation, no revenue. Trade-specific headlines are the fastest way to pass the "for them" test at first sight.
- **Where:** `templates/walkthrough.html:7-59`, `app.py:603-615`, `mandate.py:213-233`. *(Ship #3's `walkthrough_started_at` first, to enable before/after comparison.)*

**11. Schema/config pre-flight (semantic-integrity guard)** · `adjust` · effort S · SHARPEN
- **What:** (1) `users.login_at` via `_ensure_columns`, written on each authenticated `/dashboard` load. (2) `EMAIL_LIVE` module constant in `config.py`. (3) **CRITICAL:** do **not** add new lifecycle columns (`walkthrough_started_at`, `biz_slug`, `bottleneck_priority`, `mason_alert`, …) to `_BUSINESS_COLS` — `update_business()` (`db.py:398-408`) silently drops anything not in that list, and adding lifecycle timestamps there makes them eligible for accidental erasure by a Settings submit. Use `_ensure_columns` + direct `UPDATE`/named helpers. (4) Gate the morning brief on `SMS_LIVE or EMAIL_LIVE`.
- **Why:** Six proposed new columns across the rounds would be silently lost without this; it's the highest-priority correctness guard for everything else in the plan.
- **Where:** `db.py` `init_db()`, `config.py`, `app.py` `/dashboard`, `ROADMAP.md`.

### P2 — differentiation & growth-loop depth (after a paying first win)

**12. Trade-aware `designate()`** · `adjust` · effort S · BUILD — add `business=None`; roofers (storm-season) and HVAC (emergency-demand) get different first-win priorities than painters (repaint cycles). `firstwin.py:21-33`, `app.py:297`.

**13. Bottleneck radio on the Mandate + reconciliation note** · `adjust` · effort S · BUILD — 4-option radio orients the contractor (avoids 8-card decision paralysis); when their pick ≠ JobMagnet's top play, show *"You flagged X. JobMagnet's starting with Y because: {reason}."* Uses the already-computed `diagnose()` result — zero new AI calls. `app.py:618-635`, `templates/mandate.html`.

**14. Weekly self-audit (stall detection)** · `adjust` · effort S · BUILD — Monday branch in `/tasks/tick`: a `take_over` election with 0 autopilot output in 7 days → `mason_alert` ("a play is set to Take it Over but nothing went out — check /connections"). Converts a churn signal into a trust moment. `app.py:569-600`, `templates/command.html`.

**15. Close the photo-by-text MMS loop** · `adjust` · effort S · SHARPEN — the `/webhooks/sms` handler (`app.py:993-1014`) detects MMS, drafts, and saves a post but **never replies**. Add a ~3-line `send_sms()` reply + wire a `photo_post` win into `WINS`/`_FACT_WIN`. (Do *not* build multimodal vision yet — text-based draft proves the loop.) Depends on live Twilio.

**16. Auto-generate `aeo_faq` at Walkthrough POST + public `/faq/<slug>`** · `adjust` · effort M · SHARPEN — call `ai.generate_faq(biz)` (has a demo fallback) on submit, persist it, and render a paste-ready block on `/mandate` so the contractor leaves with a **real artifact**, not a to-do. Host at `/faq/<slug>` with JSON-LD + a "Get yours at jobmagnet.app" CTA — a zero-CAC, AI-search-indexable acquisition touchpoint. Parse with `ai._parse_qa()` (FAQ is `Q:/A:` text, not JSON). `app.py:609-614` + new public route, `templates/faq_public.html` (new).

**17. Make "JobMagnet said no" shareable: public `/insight/<slug>/<play_key>`** · `take` · effort S · BUILD — render a `not_yet` play's real-numbers reason on a public page ("Why JobMagnet hasn't run X for {business} yet") with a clipboard share link on `/mandate`. `mandate.diagnose()` is a pure function (safe from a public route). Honest restraint with the contractor's own numbers is the most credible possible positioning. Depends on #16's `biz_slug`.

**18. 2-day build protocol + PMF constraint + `COMPLIANCE.md`** · `adjust` · effort S · BUILD — write the build protocol and the PMF constraint into `ROADMAP.md`; write a 1-page `COMPLIANCE.md` referencing the existing hard gates (`messaging.py:69-79,104-113,209-249`) as Type-1 behaviors so an attorney has something to review. Add a growth-loop triage filter (which stage does this strengthen?). See Adjust-warnings for the 2-day rationale.

**19. Activate the adaptive register on day 1** · `take` · effort S · SHARPEN — the `/training` route is fully built (the LTV engine) but has no first-session seed. One "straight & brief / detailed & explained" radio in the Walkthrough, injected into `_route_system()`, starts the register on day 1 instead of waiting for corrections. `templates/walkthrough.html`, `assistant.py:403-422`.

**20. Competitor review count for relative Mandate framing** · `take` · effort S · BUILD — one Walkthrough input ("reviews your strongest competitor has") turns "14 backlog customers" into *"your top competitor has ~80 reviews, you have 12 — your fastest path to catch them is the 14 happy customers who haven't reviewed."* Must be added to **both** `_SIGNAL_COLS` and the physical `business_signals` schema. `db.py:783` + `init_db()`, `mandate.py`, `firstwin.py`.

### P3 — process hygiene

**21. `CAPABILITY_BACKLOG.md` with quarterly re-eval dates** · `adjust` · effort S · BUILD — DEAD / PARKED (with a viability test + re-eval date) / GRADUATED. Parks conversational onboarding (re-eval Sep 30 2026), AI image-gen (Oct 31 2026), and multimodal photo (after the basic loop proves out). One morning per quarter to run the tests. Prevents permanent kills — "last month's no may be this month's yes."

---

## Where JobMagnet must NOT copy Anthropic (the adjustments)

JobMagnet's user is a **blue-collar contractor on a job site**, and JobMagnet is **pre-PMF and solo-built** — not a knowledge-worker audience at a hypergrowth lab. These lessons need translation, not copying:

| Anthropic lesson | Why JobMagnet differs | JobMagnet translation |
|---|---|---|
| **L16** two-*week* PM/eng ownership threshold | 40-person team; here Jack is PM+eng+founder and Claude Code compresses build time | **2-*day* threshold.** Sub-2-day: ship against green test suites, no spec. Over-2-day: one paragraph (why / compliance check / what am I learning) first. The blockers are each sub-2-day — stop documenting, ship. |
| **L11** structured morning briefs on dashboards | A painter at 6:30am is on a roof, not at a monitor | Same scheduling discipline, **3 lines via SMS before 7am** (email fallback). Milestone-gate the build until a real message is confirmed delivering — a simulated push defeats the point. |
| **L12** notebook channels to arm the agents | JobMagnet already has a *better* artifact: the Mandate is a typed dict with scores + reasons | **Don't build new writing infra.** The Mandate *is* the notebook channel — the gap is the missing wire into `_route_system()`. |
| **L6** intake data → look-alike ad retargeting | No ad network, no audience, no budget at this scale | **Make the deliverable self-advertising:** public `/faq/<slug>` + `/insight/<slug>` pages. Same "data keeps giving," zero-CAC distribution. |
| **L5** Mercury's full-*quarter* quality sprint | Mercury had a team that could pause the roadmap; solo can't | **One sprint, first-session flow only** (Walkthrough-submit → first-win). Everything outside that window waits for the pilot. |
| **L13** Type-1/Type-2 controversy test | Anthropic's Type-1 is AI existential safety; JobMagnet's is TCPA/FCC legal liability | Adopt the *framework*, not the behaviors. JobMagnet's Type-1 list must be drafted **with a TCPA attorney**; the existing `messaging.py` gates are the starting point. |
| **L2** add a quiz to onboarding | Masterclass/Calm users arrive cold; JobMagnet's Walkthrough already captures 10+ signals | One bottleneck radio on the Mandate is the *max* that passes the "for them" test — more questions at the commitment moment would kill conversion, not help it. |
| **L4** route by user archetype | Anthropic routes by knowledge-worker/developer/B2B | JobMagnet routes by **trade economics** (roofer storm cycles ≠ painter repaint cycles ≠ HVAC tune-up season). |
| **L10** growth loop over a large user population | Anthropic A/B tests across segments; JobMagnet has one tenant, no A/B infra | The loop runs against **JobMagnet's own output** (did the `take_over` plays actually fire? did a sent review request produce a GBP review in 14 days?), not user segments. "Analyze" is the only broken stage — fix it first. |

---

## Operating model (how to *build* JobMagnet)

1. **2-day build threshold, applied now.** Each ship blocker and wiring fix is sub-2-day; the acceptance bar is `test_smoke.py` (405) + `test_compliance_core.py` (47) green. Put down the docs and close them.
2. **PMF constraint as a decision filter.** Until `milestone.achieved_at IS NOT NULL` for Heritage *as a paying tenant*, the only two things worth building are (a) a real warm-channel first win and (b) the "JobMagnet said no" surface. Everything else fails the filter.
3. **Growth-loop stage as a triage test.** Every proposal must name which stage it strengthens (identify / build / test / analyze). "Analyze" is broken (`pull_reviews()` → `pending`); that fix is P0. Stage-1 niceties (competitor count) are P2.
4. **Prototype-to-decide for new flows.** Build the `success_metric` anchor with Heritage's *actual* answer and watch the reaction — that reaction is the spec.
5. **Deputize the test suite as PM.** The 405+47 assertions are the machine-readable product contract; a change that breaks either has violated the spec. They replace the PRD for routine work.
6. **`CAPABILITY_BACKLOG.md`, one morning per quarter.** Re-run viability tests on parked capabilities; graduate any that pass.
7. **Surface `/training` as a feature, not a settings page.** JobMagnet getting smarter from corrections *is* the LTV engine — it's built; make it visible.

---

## Deliberately NOT doing (and why)

| Killed idea | Reason |
|---|---|
| Conversational-NLU Walkthrough (replace the form with chat) | 3–5 days to build signal extraction at 6/10 readiness; the 2-step split + `success_metric` + trade headlines deliver the same "feels like a conversation." Parked, re-eval Sep 30 2026. |
| Multimodal vision for photo-by-text | Text-based draft already proves the loop; vision adds scope before value is validated (and "AI reads your photo" would be inaccurate today). Parked, trigger = basic loop live 30 days. |
| Look-alike ad retargeting | No ad infra/audience/budget. Correct translation is shareable public pages (#16/#17). |
| Full Mercury-style quality *quarter* | Solo can't pause the roadmap; scope to the first-session flow instead. |
| `content_posts.playbook` + rejection-drift detection | L-effort schema migration for an *unobserved* problem at zero tenants. A code comment marks the spot; revisit post-pilot. |
| AI image generation UI | `ai.py:262-270` always returns `simulated`; shipping UI would fabricate a success signal (a Type-1 violation). Parked, re-eval Oct 31 2026. |
| 30/60/90-day Mandate re-prompts | Needs `login_at` + ≥1 tenant with 30 days of data. The stage-aware re-engagement in #3 covers the urgent need. |
| Automated test harness for parked capabilities | A static backlog + quarterly check is the right cadence for a solo builder; a harness is infra before evidence. |

---

## Top 3 bets

1. **Close the 5 ship blockers + fix the orphaned-win-id display bug before anything else.** Each is sub-2-day and has sat documented for weeks. Nothing else in this plan matters until the product can produce *and correctly display* a real first win. One real Heritage SMS review request that yields a real Google review is the only evidence worth having at pre-PMF.
2. **Surface "JobMagnet said no" through the product.** Fix `_briefing()` to take `signals`, extract `not_yet` plays, render `brief_passed_on`, and add the Mandate trust callout. ~30 lines across 4 files, under 2 days — and it unlocks a day-1 word-of-mouth mechanism (honest restraint with real numbers) that no horizontal tool can copy.
3. **Wire the Mandate into `_route_system()` + auto-generate the FAQ at Walkthrough POST.** 15 lines (reusing `_h_game_plan()`'s pattern) eliminates the most damaging trust failure — JobMagnet contradicting the contractor's own elections — and turns the first-win from a to-do into an artifact JobMagnet *already built before the contractor committed*. Together: JobMagnet stops being a cold-start chatbot and becomes a foreman that already knows the game plan and already did the first job.

---

## Open questions (decide before building the dependent item)

1. **Is Heritage's GBP OAuth token-refresh path confirmed end-to-end?** If not, the `pull_reviews()` blocker is really two sequential tasks (confirm OAuth, *then* implement the reviews GET).
2. **Has A2P 10DLC registration started?** 2–4 week carrier lead time, external, non-compressible — it gates the first real SMS, the photo-by-text loop, and the morning brief. Start it today.
3. **FAQ generation at Walkthrough POST: sync or async?** An LLM call adds 2–5s to submit. Block the redirect, or redirect immediately with a "JobMagnet is generating your FAQ" polling state?
4. **Morning-brief delivery: opt-in or opt-out?** Opt-in respects the inbox but suppresses activation before value is proven; opt-out risks early friction.
5. **`biz_slug`: permanent lock or settings-page override?** Changing it later breaks shared FAQ/insight URLs.
6. **Bottleneck "see AI first" option: trigger FAQ generation immediately?** Could compress time-to-first-win to <30s but needs the same sync/async decision.
7. **Should `mason_alert` escalate to email after 14 days unresolved?** Depends on whether `EMAIL_LIVE` ships before the stall check.

---

<sub>**Provenance:** generated by a 3-round brainstorm→audit→fix workflow (two Sonnet agents in parallel per round; an Opus orchestrator authored this synthesis). 17 ideas/round were audited against this repo with `file:line` evidence and adversarially critiqued; a scope guard on every round confirmed zero out-of-scope references. The two P0 code-bug claims (orphaned win id; dead `_briefing` signature) and the `not_yet` copy were independently re-verified against the source before inclusion. Raw structured output: `scratchpad/jm_final.json`.</sub>
