# JobMagnet — Everything YOU Need To Do (single source of truth)

Your complete owner to-do list. Every item here is something the **code cannot do for
itself** — accounts, API keys, approvals, legal. The app ships honest-but-gated: it runs
today on safe demo/simulated modes and each item below flips one loop from simulated → live.
**Work top to bottom.** ☐ = task · `CODE` = a Render environment variable · *How:* = the clicks.

- Live app: `https://jobmagnet-49l9.onrender.com` · Repo auto-deploys on push to `main`.
- Generate any "random string" with: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
- _Last updated 2026-07-19._

---

## TIER 0 — Do today (exploitable / blocking, ~10 minutes in the Render dashboard)

- ☐ **Change the seeded owner password.** `CODE` **`JOBMAGNET_OWNER_PASSWORD`** = a strong
  value. ⚠️ **The default `jobmagnet123` works on the live site right now** — confirmed by
  login. Set this, redeploy or restart, then verify the default no longer works.
- ☐ **Turn on the AI brain** (it's running canned *demo* templates in prod today). Set at
  least one key — no deploy needed, takes effect on save:
  - Brand tier (review replies, FAQ, ads, partner emails, chat): `CODE` **`ANTHROPIC_API_KEY`**
    from console.anthropic.com. *(A Claude **API key** ≠ a Claude **subscription** — the app
    is a server and needs the Console API key.)* Model defaults to `claude-sonnet-5`.
  - Bulk tier (routine posts, routing, grader): `CODE` **`DEEPSEEK_API_KEY`** (deepseek.com)
    **or** `CODE` **`MINIMAX_API_KEY`**. Set one bulk key + Claude to get the cost-saving split.
  - Spend caps are already ON: platform `JOBMAGNET_LLM_DAILY_CAP_USD` ($25/day default),
    per-tenant `JOBMAGNET_LLM_TENANT_DAILY_CAP_USD` ($3/day). Set the platform cap to `0` as
    a kill switch. You never get a surprise bill.
- ☐ **Approve the Render Blueprint sync** so the two cron services provision:
  `jobmagnet-tick` (every 15 min) and `jobmagnet-digest` (Mondays). *How:* Render dashboard →
  the JobMagnet Blueprint → approve the pending sync (small per-cron cost). Until you do,
  autopilot only runs when you click buttons — the crons are what make it autonomous.
- ☐ **Confirm `JOBMAGNET_SECRETS_KEY` is set** (encrypts connection creds at rest). The
  Blueprint auto-generates it on deploy; verify the Connections page shows no red "not
  encrypted" warning before connecting any real account.

## TIER 1 — SMS value loop (start the A2P registration FIRST — it takes days–weeks)

- ☐ **Twilio account + number.** `CODE` **`TWILIO_ACCOUNT_SID`**, **`TWILIO_AUTH_TOKEN`**,
  **`TWILIO_FROM`** (`+1…`). Until set, all texts (reactivation, review requests, referrals,
  speed-to-lead) are simulated (logged, not sent).
- ☐ **A2P 10DLC brand + campaign registration** (US carriers require it). Register the brand
  + campaign, associate the sending number, link the hosted SMS privacy/terms pages. **Start
  this early** — approval is the long pole. Verify deliverability with one real send.

## TIER 2 — Email (partner outreach + contact form delivery)

- ☐ **SMTP provider** (Postmark/SendGrid/SES). `CODE` **`JOBMAGNET_EMAIL_FROM`**, **`SMTP_HOST`**,
  **`SMTP_PORT`**, **`SMTP_USER`**, **`SMTP_PASSWORD`**. Until set, partner emails + the
  contact form are simulated (recorded to `contact_inbox.log`, not delivered).
- ☐ **SPF / DKIM / DMARC** DNS records on the sending domain (deliverability).

## TIER 3 — Get Found live (Google Business Profile)

- ☐ **Google Cloud OAuth app.** `CODE` **`GOOGLE_CLIENT_ID`**, **`GOOGLE_CLIENT_SECRET`**,
  **`GOOGLE_REDIRECT_URI`** (must match the whitelisted URI exactly). Enable the Business
  Profile API. Unlocks one-click GBP connect → auto-posting + the review pull.
- ☐ **At first real GBP connect, tell Jim to verify the review/post API endpoints.** The
  reviewsync + publishing calls use the v4 shape matching the stored creds; Google keeps
  migrating the Business Profile APIs, so confirm against a live connected account before
  trusting "live" (flagged in `SETUP_NEEDED.md`).

## TIER 4 — Billing (real card charges)   ⚠️ MONEY gate — Jack hands-on

- ☐ **Stripe live keys** + register the webhook endpoint + run ONE end-to-end test charge.
  `CODE` **`STRIPE_SECRET_KEY`** (and webhook secret). Billing stays simulated until verified.

## TIER 5 — Launch polish

- ☐ **A domain.** ⚠️ **You do NOT own `jobmagnet.app`** — it's a stranger's job board.
  Buy a domain you control (or `jobmagnet.app` if available) and point the app at it; the
  in-app links currently fall back to the Render URL.
- ☐ **Open Graph share image** for link previews (favicons are already done).
- ☐ **FirstBack booking-sync** (optional closed loop): `CODE` **`FIRSTBACK_API_URL`** +
  **`FIRSTBACK_API_KEY`**. Wired + gated; the bookings GET shape needs matching to
  FirstBack's real API once live.

## TIER 6 — Cold channels   ⚠️ legal gate (may never open)

- ☐ **Cold SMS/voice to homeowners stays permanently blocked** — no action, by design.
  The lawful cold channel is **Neighbor Mail** (paper, no consent needed), already live.

---

## Decisions only you can make (not tasks — rulings)

- ☐ **Pricing points** — do Premium/Scale prices move now that they carry Neighbor Mail /
  LSA Concierge? (Feature copy is aligned; the numbers are your call.)
- ☐ **Portfolio rulings**: cross-trade network → TradeSource · reward ledgers → Nod ·
  SEO-geography coordination with TradeSource's PA-county painter pages.
- ☐ **The `.claude/` directory** — commit, gitignore, or leave (untracked).
- ☐ **Neighbor Mail v1** (automated print-and-mail via Lob) — parked; MONEY gate. Trigger:
  ≥3 tenants mark a v0 campaign "printed", then Jim brings a costed spec.

---

## What's already DONE (for reference — do not redo)

Built + deployed this cycle: three new-client engines (Neighbor Mail, Partner Engine, LSA
Concierge) · cut the dead cold-outreach UI + managed-ads promise · fixed the reviewsync
bug · public `/features` page + hero · honest headline · repointed jobmagnet.app links ·
heartbeat crons wired in the Blueprint · the two-tier cost-capped AI brain (`brain.py`) ·
`mason_alert → jobmagnet_alert` rename. Everything above is green across all four test
suites and live in production. The runtime is complete — **what remains is only the
credentials and approvals in this file.**
