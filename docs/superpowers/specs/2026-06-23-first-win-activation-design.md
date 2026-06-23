# First-Win Activation — Design

Date: 2026-06-23
Status: Approved (design); pending implementation plan
Scope: Track B (activation, audit priority #3). Independent of the storage work, but
builds ON the `postgres-migration` branch (new table + queries must be Postgres dialect).

## Problem

The audit's highest-leverage *product* gap: a new tenant has no guided path to a first
concrete win, and activation drives retention at $199–599/mo. We give each tenant ONE
designated win to guide toward in their first ~7 days, surface it in the command center,
and celebrate when it lands.

## Decisions (locked during brainstorming)

1. **One designated win per tenant**, chosen from the tenant's signals + connection state
   (not a checklist, not a single global milestone).
2. **Real-outcome only, mode-aware selection.** A win counts only on a genuine, honest
   outcome (actually sent/published, or a real artifact). Selection only ever designates a
   win the tenant can REALLY achieve in their current state; when no integration is live,
   it designates the AEO FAQ/schema win (a real artifact needing no integration).
3. **Soft 7-day target.** Track days since signup; Mason surfaces + gently nudges; no
   lockout or penalty. Celebrate on achievement.
4. **Approach A — derived + dynamic-until-achieved.** The designated win is recomputed each
   load (always the best currently-reachable real win). Achievement is derived from existing
   real-outcome data. Only `achieved_at` + a celebrate-once flag are persisted.

## The five wins & real-outcome detection (all from existing data)

| Win id | Achieved when (REAL, not simulated) | Source |
|---|---|---|
| `review_request` | a review-request message with `status='sent'` | `messages` |
| `gbp_post` | a content_post `status='published'` AND `publish_mode='live'` | `content_posts` |
| `reactivation` | a reactivation message with `status='sent'` | `messages` |
| `aeo_faq` | the Brain has a non-empty generated `faq` artifact | `businesses.faq` |
| `firstback_booking` | a `conversions` row with `origin` in (`firstback`,`ringback`) | `conversions` |

The exact message-kind columns/values for `review_request` vs `reactivation` are confirmed
against `db.py`/`messaging.py` during planning; the rule is always "status='sent' (live), not
'simulated'."

## Designated vs. achieved

- **Designated** = the single win Mason guides toward, chosen mode-aware by priority:
  1. `review_request` — if SMS is live AND the tenant has past customers / a reviewable backlog
  2. `gbp_post` — if GBP is connected (live publish possible)
  3. `reactivation` — if SMS is live AND past customers are due
  4. `aeo_faq` — **universal fallback** (always reachable, no integration, real artifact)

  `firstback_booking` is NOT a nudge target (a tenant can't force a booking).
  This priority order is a tunable product judgment, isolated in `firstwin.py`.

- **Achieved** = the designated win's condition **OR any other qualifying real outcome**
  (including `firstback_booking`). Rationale: a real win we didn't nudge should still count
  and be celebrated, never shown as "not yet."

## Architecture (pure-module + db split, matching `mandate.py`)

### `firstwin.py` (new, pure — no I/O)
- `WINS`: ordered canonical win ids with metadata `{id, label, cta_route, nudge}`.
- `designate(signals, live_state) -> win_id`: pure selection from the priority list.
  - `signals`: dict from `db.get_signals` (e.g. `past_customers`, `reviewable_backlog`).
  - `live_state`: dict `{sms_live: bool, gbp_connected: bool}` assembled by the caller.
- `achieved(facts) -> win_id | None`: pure; returns the first qualifying real outcome id,
  else None.
  - `facts`: dict of real-outcome booleans
    `{review_sent, gbp_live_post, reactivation_sent, faq_generated, firstback_booking}`.
- `nudge_copy(win_id, days_since_signup) -> str`: soft, day-aware copy
  (day 0–1 intro / day 2–4 reminder / day 5–7 "first week" nudge). No lockout language.

### `db.py` (Postgres dialect)
- `first_win_facts(business_id) -> dict`: gathers the real-outcome booleans via queries
  that exclude simulated outcomes (`status='sent'`, `publish_mode='live'`, non-empty `faq`,
  qualifying `conversions.origin`).
- New table `onboarding_milestone` (`business_id BIGINT PRIMARY KEY`, `achieved_at TEXT`,
  `achieved_win TEXT`, `celebrated INTEGER DEFAULT 0`) created in `init_db` (Postgres dialect).
- `get_milestone(business_id)`, `mark_milestone_achieved(business_id, win_id)` (idempotent —
  sets `achieved_at`/`achieved_win` once), `mark_milestone_celebrated(business_id)`.

### `app.py` (wiring)
- A `first_win_block(business_id)` helper that assembles the brief block:
  - reads signals + live_state → `designate`
  - reads `first_win_facts` → `achieved`
  - reads/updates `onboarding_milestone` (record `achieved_at` on first detection; decide
    celebrate state)
  - returns `{state, designated, achieved_win, days_since_signup, label, cta_route, nudge}`
    where `state` ∈ {`in_progress`, `achieved_uncelebrated`, `achieved_celebrated`}.
- Add this block to the command-center `brief` and a compact form on `/dashboard`.
- `days_since_signup` derived from `businesses.created_at`.

### Templates
- A partial rendered in `command.html` (hero) + `/dashboard`:
  - `in_progress`: designated win label + CTA button (→ `cta_route`) + soft "Day N of 7" + nudge.
  - `achieved_uncelebrated`: 🎉 celebration naming the achieved win; flips to celebrated after view.
  - `achieved_celebrated`: quiet "First win complete" badge (or hidden).

## Components & boundaries
- `firstwin.py` — pure decision + copy (unit-testable, no DB).
- `db.py` — the I/O: `first_win_facts` + `onboarding_milestone` CRUD.
- `app.py` — `first_win_block` glue into brief + dashboard.
- templates — presentation only.
- `test_firstwin.py` — new framework-free suite.

## Testing (framework-free, exit 0; runs on Postgres)
- `designate()` pure cases: nothing live → `aeo_faq`; GBP connected → `gbp_post`; SMS live +
  backlog → `review_request`; SMS live + due customers (no backlog) → `reactivation`.
- **Honest-states test (key):** `achieved()` / `first_win_facts` flips on a `status='sent'`
  message and a `publish_mode='live'` post, but NOT on `status='simulated'` / simulated post.
- `achieved` counts any qualifying real outcome (e.g. a `firstback` conversion) even when the
  designated win is `aeo_faq`.
- Celebrate-once: `celebrated` flips; a second load yields `achieved_celebrated`.
- `days_since_signup` derived correctly from `created_at`.
- Smoke: the command-center brief includes a `first_win` block with the expected `state`.

## Out of scope
- Building new action capabilities (all five win-actions already exist).
- Changing connector/integration behavior.
- The checklist/multi-milestone shapes (rejected in brainstorming).

## Acceptance criteria
- A fresh tenant sees a designated, currently-reachable real win in the command center with a
  CTA and a soft day counter.
- The designated win is mode-aware (never points at a win requiring an unconnected integration;
  falls back to `aeo_faq`).
- The milestone flips to achieved ONLY on a real outcome (a simulated send/post never counts),
  and is celebrated exactly once.
- New `db.py` SQL is Postgres dialect; full existing suite stays green; `test_firstwin.py` passes.
