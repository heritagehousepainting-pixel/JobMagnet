# JobMagnet — cross-pollination handoff

**Date:** 2026-06-27 · **Repo:** heritagehousepainting-pixel/JobMagnet (Python/Flask; data layer now psycopg/Postgres — README still says SQLite, confirm) · **Deploy:** Render `jobmagnet`.

Output of an 8-agent portfolio survey (Nod, FirstBack, TradeSourceV3, JobMagnet). JobMagnet is the **marketing/get-found/autopilot** leader (export `mandate`, `autopilot`, `cadence`, `getfound`, `seo`). Its gaps: **learning which copy converts**, and **capturing/booking** the demand it generates. Below: what JobMagnet should *adopt*.

## What JobMagnet already leads on (export, don't rebuild)
Mandate/diagnostic engine, autopilot + cadence + trust dial, GBP/local-SEO/AEO (`getfound.py`/`seo.py`/`google_business.py`), AI content/reviews/ads generation, self-improving `convos.py` (LLM grader + weekly digest), gated `messaging.py` + plans/gating.

## Proposed adoptions (prioritized)
| # | Adopt | From | Why (better / efficient / track) | Source files to study | Effort |
|---|---|---|---|---|---|
| 1 | **Conversion-learning loop** (cross-tenant, anonymized) | Nod `insights.py` | JobMagnet's product *is* generated copy (posts/ads/emails). Learning **which copy actually converts** across tenants and feeding it back is a direct quality + tracking upgrade to the core engine. | Nod `insights.py`, `db.*_outcomes_for_insights`, the conversion-learning specs in Nod `docs/superpowers/specs/2026-06-27-conversion-learning-loop-phase-*` | Medium |
| 2 | **Anti-hallucination prompt guards** | Nod / TradeSourceV3 | JobMagnet generates copy from sparse business inputs — exactly the fabrication risk. A FACTS anchor + missing-field guard makes its ad/post/email output safer and more accurate. | Nod `social._facts_anchor`/`_no_invent_guard`; tradesourcev3 `app/api/scope/generate/route.ts` | Easy |
| 3 | **Missed-call text-back + AI booking + voice** (close the loop) | FirstBack | JobMagnet *drives* demand; FirstBack *captures + books* it. JobMagnet has a "speed-to-lead" play — wiring it into FirstBack's text-back/booking/voice stack closes demand→booking (they're already designed to integrate). Track cost-per-booked-job end to end. | firstback `app.py` (`_missed_call_textback`, `handle_inbound`), `voice_service.py`, `messaging.py` | Medium |
| 4 | **Full referral rail + e-signed agreement** | Nod | JobMagnet has a `referrals.py` play (a message); Nod has a trackable referral rail (link → confirm → reward → signed agreement). Upgrades the play into a measurable system. | Nod intake/vault routes, `agreements.py` | Medium |
| 5 | **`token_crypto` (encrypt OAuth tokens at rest)** | FirstBack | JobMagnet stores GBP/Meta/Twilio tokens; versioned dual-read encryption flips on with no migration. | firstback `token_crypto.py` | Easy |
| 6 | **Programmatic local-SEO page factory + MDX blog** | TradeSourceV3 | JobMagnet's whole thesis is "get found" — TradeSource's county/town page generator + schema + pillar blog is a turnkey extension of `getfound`/`seo`. | tradesourcev3 `lib/seo/{counties,towns,schema}.ts`, `content/blog`, `app/sitemap.ts` | Medium (TS→Python render rework; reuse data + strategy) |

## Shared-kernel note
JobMagnet + FirstBack share **`trades_core`** (`auth.py`,`db_core.py`,`consent.py`,`llm.py`). Nod now vendors `auth.py`+`db_core.py` and ported `consent.py`+`llm.py` patterns. The **LLM cost-ledger + daily cap** Nod added to its `llm.py` is worth folding back into the shared `llm.py` so all three apps track AI spend uniformly.

## Working conventions
Keep JobMagnet's existing discipline: honesty-as-architecture (every integration live/assisted/simulated/pending, never claim a capability before it ships — see `AUDIT_TRUTH.md`); autonomy layered *on top of* the same gated seams a button uses (never around them); standalone `test_smoke.py`. Spec → build → self-gate → commit/push. **Confirm the Postgres vs SQLite reality before reusing any data-layer code.** Push auto-deploys `jobmagnet`.
