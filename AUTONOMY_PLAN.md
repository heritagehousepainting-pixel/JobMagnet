# JobMagnet — Autonomy Plan

**Goal (2026-06-15):** Move the marketing-site "Real today" list from *true but
button-driven* to *true and autonomous*. Everything in the left column already works;
the engine is correctly built behind gated seams. What's missing is a **heartbeat** that
runs the work on its own, plus an honest **trust dial** that lets the owner raise how much
JobMagnet does unattended.

This plan does NOT loosen any guardrail. Every autonomous action still flows through the
same seams a button uses today: `messaging.send_sms` (consent + quiet hours + caps),
`publishing.publish_post` (live/assisted/simulated), `posting.safe_schedule_time`, and the
approval queue. Autonomy is added *on top of* the existing discipline, never around it.

---

## The core diagnosis

| Capability | Built behind a seam? | What triggers it today | Gap to autonomy |
|---|---|---|---|
| Autopilot plays (get_found, show_work, reviews, reactivation, referrals) | ✅ `autopilot.plan` + `/autopilot/run` | **Owner clicks "Run autopilot"** | No recurring runner |
| Scheduled-post publishing | ✅ `publishing.publish_post`, `db.due_posts` | **Owner clicks "Publish due now"** | No cron tick |
| Content cadence | ✅ `ai.generate_post`, `db.last_post_at` | Manual / one draft per autopilot click | No cadence pacing; drafts pile up |
| Review monitoring | ⬜ no GBP pull (`reviews_import` is manual) | **Owner types the review in** | No puller |
| Review responses | ✅ `ai.generate_review_response` (auto-drafts) | **Owner clicks publish** | No auto-publish tier |
| Closed-loop ROI | ✅ webhook + `roi.sync_firstback` live pull (deduped, heartbeat-driven) | **Auto (FirstBack) or owner logs the job** | Activates when FIRSTBACK_* set; GET shape may need matching |

**One sentence:** build a per-tenant heartbeat, route the existing engines through it,
give the owner a dial for how far to let it run, and show them what it did.

---

## Hard constraints (don't break)
- Every send still passes `messaging.consent_ok` + quiet hours + `cap_status` pacing.
- Every publish still goes through `publishing.publish_post` (honest live/assisted/simulated).
- `contacted_ids` / `requested_contact_ids` no-repeat guards stay authoritative (no double-sends).
- Plan gating holds: autonomy is Premium+ (`plans.can_autopilot`); Pro stays advise-and-approve.
- Multi-tenant `business_id` scoping on every query the runner touches.
- Keep the smoke suite green; add tests for each new seam.
- **Honesty in lockstep:** marketing copy (per `AUDIT_TRUTH.md`) only moves a "don't do yet"
  item to "real" *after* the code ships. Never claim autonomy the runner can't perform.

---

## Phases (risk-ordered, thin tested slices)

### Phase 0 — The heartbeat (the whole unlock)  ✅ SHIPPED
The minimum that makes everything else continuous. Built: `autopilot.run_for(business_id)`
(shared by the button + cron), `autopilot_runs` audit table + `db` helpers, token-gated
idempotent `POST /tasks/tick`, last-run surfaced on the Game Plan. 20 new tests, suite green.
- Refactor the body of `/autopilot/run` into a reusable `autopilot.run_for(business_id)` so
  the button and the cron share one code path (no second source of truth).
- Add an authenticated, idempotent **`POST /cron/tick`** (auth by `WEBHOOK_TOKEN`, like the
  other webhooks) that, for every active tenant:
  1. publishes due scheduled posts (`db.due_posts`, already cross-tenant),
  2. runs `autopilot.run_for` for plays set to `take_over`,
  3. writes an **`autopilot_runs`** audit row (when, what ran, counts, capped).
- Drive it from an external cron / platform scheduler every ~15 min. Document in
  `SETUP_NEEDED.md` (the "Scheduler cron" item already anticipates this).
- Surface `last_tick` + last-run summary in the UI so the owner can see the heartbeat is alive.

*Result:* reactivation, referrals, review requests, and GBP drafting become continuous
instead of waiting for a click — using the gates that already exist.

### Phase 1 — Autonomous content cadence (pacing only)  ✅ SHIPPED
Built: pure `cadence.py` (per-play window map + `due()`), and `autopilot.run_for` now gates
get_found/show_work drafting on `db.last_post_at` so a recent post inside the window is skipped
(not counted). The heartbeat is now safe at ~15 min; drafts still wait for approval. Tests added,
the Phase 0 heartbeat test updated to assert pacing honestly, suite green.

A 15-min tick must not spam drafts. This phase ONLY adds pacing; it does not change where
content lands (still `draft`, still waits for approval) — auto-publishing is Phase 2's job,
introduced once, behind its trust dial. Clean separation so the two phases never collide.
- A small, pure cadence helper: per content play a window (GBP ≈ weekly, showcase ≈ a few
  days), and `due(last_created_at, window, now)`.
- In `autopilot.run_for`, skip generating a get_found/show_work draft when the tenant already
  has a recent post on that platform (via `db.last_post_at`) inside the window.

*Result:* the heartbeat can run every 15 min without over-drafting, removing the Phase 0
caveat. Behavior is otherwise unchanged (drafts still wait for approval).

### Phase 2 — The trust dial (auto-approve ceiling + the ONLY auto-publish)  ✅ SHIPPED
Built: tenant-level `auto_publish` (default OFF), `db.get_auto_publish`/`set_auto_publish`,
`POST /mandate/autopilot-publish` (Premium+, defense-in-depth), and the dial in the Game Plan.
When ON, `autopilot.run_for` auto-schedules get_found/show_work drafts via `posting.safe_schedule_time`
ONLY on genuinely LIVE channels (so the heartbeat publishes them); OFF or non-live channels still
draft for approval. New "Phase 2 trust dial" tests; suite green (340 passed, 0 failed).

Make "how autonomous" an explicit, owner-controlled, honest setting. This phase introduces
auto-publishing for the first and only time, behind the dial, default OFF.
- Today `take_over` still drafts content to the queue. Add a tenant-level (or per-play)
  **"Schedule & publish for me"** opt-in, Premium+, conservative default OFF.
- When ON: autopilot-generated content for that tenant is **auto-scheduled** via
  `posting.safe_schedule_time` (spreads, dodges quiet hours) and the heartbeat publishes it
  on a later tick — but **only on live channels** (GBP/FB connected) and owned/warm content.
  Assisted channels (IG/LinkedIn) can't be auto-published by definition; they stay drafts.
- When OFF (default): unchanged — everything drafts and waits for approval.
- Show the dial prominently in the Game Plan so the owner always knows what JobMagnet does alone.

### Phase 3 — Autonomous reviews loop  ✅ SHIPPED
Built: pure `reviewsync.py` (`pull_reviews(business_id)`) mirroring `roi.sync_firstback` —
'simulated' when GBP unconnected, 'pending' once connected but credentials incomplete, 'live'
with full creds (the reviews GET IS implemented — fixed 2026-07-19 to use the stored combined
"accounts/X/locations/Y" resource; a phantom `account_id` read had forced 'pending' forever;
endpoint host still needs verification against a real connected account; never fabricates reviews). Manual `POST /reviews/sync` (mirrors `/roi/sync-firstback`); the heartbeat
`/tasks/tick` now calls `pull_reviews` per tenant so monitoring is autonomous-ready (safe no-op
until GBP is wired). Honest triage surfaced on the reviews page (derived from the stored rating,
no schema change): 4-5★ = "Ready to approve" praise, 1-3★ = "Needs your attention" (still
auto-drafts a gracious reply but is flagged and NEVER auto-sent). Marking a lead won/booked with a
review link + phone sends ONE review request through the gated seam, deduped by the messages log
(`db.review_requested_to_phone`) so re-marking never double-texts. New "Phase 3 reviews loop" tests;
suite green.

**Honesty boundary held:** there is no real Google "reply to review" API in this codebase, so
replies are never auto-published / auto-marked-responded — autonomy here is monitoring + draft-prep
+ triage; the owner still taps to post the public reply. The pull stays honestly simulated/pending.

Closes "we don't auto-monitor reviews yet."
- ✅ GBP review **pull** implemented (verify the API host at first live connect — SETUP_NEEDED).
- Auto-draft the response (already works on import) → **flag 1–3★ for the owner** (never
  auto-respond to a critical review). Auto-publish of replies is intentionally NOT built: no real
  GBP reply connector exists, so faking a posted public reply would be dishonest.
- Auto-request a review when a job is marked won (lead → won/booked transition) instead of bulk blasts.

### Phase 4 — Autonomous closed loop (ROI) ✅ SHIPPED
Closes "bookings reach ROI by webhook or manual log."
- `roi.sync_firstback` now does the real bookings GET (factored into `roi._fetch_firstback_bookings`
  for stubbing): connected -> live pull adding `add_conversion(... origin='firstback', ext_id=...)`
  for each NEW booking, deduped by `(business_id, origin, ext_id)` via `db.conversion_exists` so
  re-syncing never double-counts. Honest modes: simulated (creds unset) / live (pulled, n>=0) /
  error (request failed, never a faked success).
- `/tasks/tick` pulls each tenant's bookings every heartbeat and reports `bookings_synced`. A safe
  no-op until `FIRSTBACK_API_URL` + `FIRSTBACK_API_KEY` are set; cost-per-booked-job then updates with
  no manual logging. The booking webhook (`/webhooks/booking`) still covers the push path.
- For later: the bookings GET path/shape (`/bookings`, Bearer auth, list-or-envelope JSON) is a
  reasonable default and must be matched to FirstBack's real API when the instance is live.

### Phase 5 — The trust layer (so unattended feels safe, not scary) ✅ SHIPPED
Autonomy without visibility erodes trust fast.
- An **activity feed** — "Here's what JobMagnet did" — from `autopilot_runs` + the messages log.
- An optional **daily/weekly digest** (email/SMS via the seam, or in-app), reusing
  `convos.digest`. Tell the owner what went out, what's queued, what got capped/paced.

---

## Explicitly OUT of scope (stays gated / honest)
- **AI image generation** — a missing *capability*, not an autonomy gap. Wire a provider into
  `ai.generate_image` separately; until then it stays "simulated."
- **Managed ad accounts** — needs account access + its own legal posture. Stays advisory; the
  most we add autonomously is a weekly ad-copy refresh draft + budget-pacing alerts.
- **Cold SMS / voice** — correctly hard-gated behind the TCPA attorney sign-off. The heartbeat
  must never touch cold channels. No change here, on purpose.

---

## Done when
- A cron tick runs the whole `take_over` mandate per tenant, every interval, idempotently.
- Content posts itself end-to-end on connected channels; assisted channels auto-prepare.
- Reviews are pulled, replied to (gated), and escalated without the owner typing them in.
- Booked jobs reach the ROI dashboard automatically.
- The owner can see and tune everything JobMagnet did unattended.
- Suite green; every new autonomous path has a test; marketing copy updated truthfully.
