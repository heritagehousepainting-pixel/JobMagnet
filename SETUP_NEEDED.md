# JobMagnet — What YOU need to set up

A running tab of everything that requires **your** action to go from *simulated* to
*live* (accounts, API keys, approvals, legal). The app is built so every one of these
is a **safe no-op until configured** — nothing breaks while these are pending; the UI
just shows "simulated" instead of "live." Updated as we build.

Legend: ⬜ not started · 🟡 in progress · ✅ done

---

## Already done
- ✅ **Public marketing site** — home (`/`), `/pricing`, `/how-it-works`, `/contact`,
  `/features` are built and live (dark, premium). Pricing pulls from `plans.py`, so
  changing a plan there updates the site automatically.

## AI brain — the two-tier engine (set at least one key)  ⚠️
Every generation goes through the one gated seam (`brain.py`). Until a key is set it runs
the built-in **demo templates** (honest, works with zero setup — this is what production
runs today). Two tiers, each falling back to demo if unconfigured:
- **Bulk tier** (routine posts, assistant routing, the grader) — cheapest configured
  provider. Set **`DEEPSEEK_API_KEY`** (model `deepseek-chat`, from platform.deepseek.com)
  or keep **`MINIMAX_API_KEY`**.
- **Brand tier** (review replies, FAQ/AEO, ad copy, partner emails, assistant chat) —
  **`ANTHROPIC_API_KEY`** from console.anthropic.com; model defaults to `claude-sonnet-5`
  (override with `JOBMAGNET_BRAND_MODEL`). A **Claude API key is separate from a Claude
  subscription** — the subscription can't drive a server; you need a Console API key.
- Set only one key → the whole product is real on that provider (not tier-split). Set a
  bulk key AND Claude → the split turns on automatically.
- **`JOBMAGNET_PROVIDER`** (legacy single-provider switch) is superseded by the tier
  routing above; the tiers key off the individual API keys, not this var.

### Spend caps (the surprise-bill wall) — already on, tune if needed
- **`JOBMAGNET_LLM_DAILY_CAP_USD`** — platform-wide daily ceiling across all tenants
  (default **$25**). At/over it, generation degrades to templates until UTC midnight.
  Set **0** to disable all real LLM (demo only) as a kill switch.
- **`JOBMAGNET_LLM_TENANT_DAILY_CAP_USD`** — per-tenant daily ceiling (default **$3**),
  so one runaway tenant (e.g. a chat loop) can't eat the platform budget.
- Both caps FAIL OPEN (a ledger read error never blocks a send). Every real call is
  written to the `llm_usage` cost ledger for capping + future cost-of-serve reporting.

## Code-pending — NOT just a credential (won't work until built)
The truthfulness audit (2026-06-15) confirmed the site now only claims what the code
does. A few seams are gated honestly but still need **code**, not just a key — the UI
says so:
- 🟡 **FirstBack auto booking-sync** — the bookings pull + heartbeat hook are now WIRED.
  `roi.sync_firstback` does a real bookings GET and adds deduped `origin='firstback'`
  conversions; the autonomy heartbeat (`/tasks/tick`) runs it per tenant. It stays a safe
  no-op (mode "simulated") until you set `FIRSTBACK_API_URL` + `FIRSTBACK_API_KEY`, then it
  goes live automatically (mode "live"; "error" if FirstBack is unreachable, never a fake
  success). Only remaining: the bookings GET shape (`/bookings`, Bearer auth, list/envelope
  JSON) may need matching to FirstBack's real API. Manual "Log a booked job" still works.
- ⬜ **AI image generation** — `ai.generate_image` is prompt-only; status is always
  "simulated" even with `JOBMAGNET_IMAGE_KEY` set, until a provider call is wired.
- ⬜ **Managed paid ads** — `ads.py` is advisory (budgets + copy), not ad-account
  management. The site says "Paid-ads guidance," not "managed," on purpose.
- ⬜ **Texting line** — included as a feature you *connect* (Twilio in Connections);
  not pre-provisioned. Until a number is linked, review/lead texts are simulated.

## Public site — to make it fully real
- ⬜ **Contact form delivery.** `POST /contact` currently appends each inquiry to a
  local `contact_inbox.log` file (honest: it's recorded, not emailed) and shows the
  visitor a confirmation. To get inquiries in your inbox, wire it to the email
  provider (Phase 0 SMTP) or a form service. The `hello@jobmagnet.app` address shown
  on the page is a placeholder — point it at a real mailbox.
- ⬜ **Domain + OG/social image.** The site is ready to deploy; it needs a domain and an
  Open Graph share image for link previews. (Favicons are DONE — `/static/favicon-*.png`.)
- ✅ **Rate-limit the public contact POST.** Per-IP in-process limit added 2026-07-19
  (on top of CSRF): bursts get a 429, honest message shown.

## Security — before onboarding real tenants  ⚠️
- ⬜ **`JOBMAGNET_SECRETS_KEY`** — encrypts stored connection credentials (Twilio/Google/
  Meta tokens) **at rest**. While unset (dev), credentials are stored in the clear and the
  Connections page shows a red "not yet encrypted" warning. Generate once and put in `.env`:
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Set this **before any real
  account is connected**. (Existing plaintext rows keep working after you set it; new writes
  are sealed. If you ever rotate this key, re-enter each connection's credentials.)
- ⬜ **Change the seeded owner password.** ⚠️ First boot seeds the owner account with
  `JOBMAGNET_OWNER_PASSWORD`, which **defaults to `jobmagnet123`** (config.py
  `SEED_OWNER_PASSWORD`). Any deploy that doesn't override the env var has a known
  default login. Set `JOBMAGNET_OWNER_PASSWORD` before first boot, or log in and
  change it immediately after. Never onboard a tenant on the default.

## Phase 0 — Messaging & consent (to send real SMS/email)
- ⬜ **Twilio account + phone number** (SMS). Need: Account SID, Auth Token, a sending
  number. Add to `.env` as `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`.
  Until then, SMS is simulated (logged, not sent).
- ⬜ **A2P 10DLC brand + campaign registration** (US SMS deliverability). Required by
  carriers for business texting; without it real SMS may be blocked/filtered.
- ⬜ **Email sending domain + SMTP/provider** (e.g. Postmark/SendGrid/SES). Need
  credentials in `.env`. Until then, email is simulated.
- ⬜ **SPF / DKIM / DMARC** DNS records on the sending domain (deliverability).

## Phase 1 — Reviews
- ⬜ **Google Business Profile review link** for each business (paste into Settings).
  This is the link customers are sent to leave a review.
- ⬜ **Google Business Profile API access** for pulling/monitoring reviews automatically.
  The pull seam (`reviewsync.pull_reviews`) and the heartbeat hook (`/tasks/tick` calls it
  per tenant) are already wired and activate the moment GBP is connected; `POST /reviews/sync`
  triggers it manually. Until connected it honestly reports 'simulated' (monitoring dormant);
  once connected with full credentials the reviews GET runs live (implemented + tested against
  a stubbed API 2026-07-19 — **at first real connect, verify the API host**: the call uses the
  v4 shape matching the stored combined location resource, and Google keeps migrating the
  Business Profile APIs). It never fabricates reviews. Reply auto-posting is intentionally out
  of scope (no real GBP reply connector).

## Phase 2 — Content & Local
- 🟡 **Google Business Profile — one-click "Connect with Google" (OAuth) is WIRED.**
  Contractors no longer paste a token: the Connections page has a **Connect Google Business
  Profile** button that runs the real OAuth web-server flow (`google_business.py`), stores
  per-tenant `{access_token, refresh_token, token_expiry, location_id}` sealed at rest, and
  refreshes the token on demand. Once a tenant connects, Google publishing flips to **live**
  and autopilot auto-posts to it (when `auto_publish` is on). It stays a safe disabled no-op
  until **you** register the app once:
    1. In **Google Cloud Console**, create an **OAuth 2.0 Client ID** (type: *Web
       application*).
    2. **Enable the Business Profile API** (the "Business Profile API" / "My Business" APIs)
       on that project, and request access if the project needs it.
    3. Add the **authorized redirect URI** exactly:
       `https://YOUR_DOMAIN/connections/google/callback`
       (locally: `http://localhost:8900/connections/google/callback`).
    4. Set the three env vars in `.env`:
       `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI`
       (the redirect URI must match step 3 character-for-character).
    5. Make sure `JOBMAGNET_SECRETS_KEY` is set first (see Security) so the tokens are
       encrypted at rest before any real account connects.
  Until `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are set, the button is disabled with an
  "add Google credentials" hint and nothing ever shows "Connected". (Note: while the app is
  in Google's "Testing" publishing status, only whitelisted test users can connect; submit
  for verification to open it to all tenants.)
- ⬜ **Meta (Facebook/Instagram) app + app review** to auto-publish. This is the slow
  one (weeks). Until approved, FB/IG is "assisted publish" (copy/paste + download).
- ⬜ **AI image generation key** (provider TBD) for post images/before-afters.
- ⬜ Confirm the **website** where schema markup / AEO landing pages will live (and how
  we deploy to it). The Local SEO page generates the JSON-LD; you paste it into your
  site `<head>`.
- ⬜ **Public URL + Twilio inbound webhook** pointed at `POST /webhooks/sms` so
  texting a job photo creates a draft (photo-by-text). Needs the app deployed (or a
  tunnel) and per-business sending numbers to map texts to the right tenant.
- 🟡 **Autonomy heartbeat cron** — WIRED IN THE BLUEPRINT 2026-07-19: `render.yaml` now
  defines a `jobmagnet-tick` cron (every 15 min) and a `jobmagnet-digest` cron (Mondays)
  that POST the token to `/tasks/tick` / `/tasks/digest`. One manual step remains: **approve
  the Blueprint sync in the Render dashboard** so the two new cron services get provisioned
  (Render asks for approval when a blueprint adds services; small extra cost per cron job).
  Safe every ~15 min by design: cadence pacing, daily SMS caps, and dedupe guards mean a
  frequent heartbeat never piles up drafts or double-texts. The per-tenant
  `POST /scheduler/run` button still works for publishing due posts by hand.

## Phase 3 — ROI loop
- ⬜ **Tracked phone numbers** (Twilio) per channel for attribution.
- 🟡 (Optional) **FirstBack connection** — if you want the closed loop, set `FIRSTBACK_API_URL`
  + `FIRSTBACK_API_KEY` so its booking events feed cost-per-booked-job. The pull + heartbeat
  hook are wired and activate automatically once those are set (see the gated-seam note up
  top for the GET-shape caveat). Optional; JobMagnet works without it.

## Phase 4 — Paid ads
- ⬜ **Google Ads / Local Services Ads account** (+ Google Screened verification:
  background check + insurance) for LSA.
- ⬜ **Meta Ads account** (if running paid social).
- ⬜ Decide whether we *manage* ad spend or *advise* (affects access needed).

## Phase 5 — Cold email (B2B)
- ⬜ **Mailing address** — enter it in Business Brain (Settings). Cold email stays OFF
  until this is set (CAN-SPAM requires a physical address on marketing email). ✅ field
  is wired; you just need to fill it in.
- ⬜ **Separate cold-email sending domain** (don't burn your primary domain) + inbox
  warmup, plus SMTP creds (Phase 0 email keys).
- ⬜ **B2B contact data source** (list provider / enrichment) — decision pending.

## Phase 6 — Cold SMS / Voice  ⚠️ legal gate
- ⬜ **TCPA attorney review of consent flows** — HARD GATE. Nothing cold-phone ships to
  real customers until this is done. Channels are OFF in code by default; only after
  sign-off do you set `JOBMAGNET_COLD_SMS=1` (and never `JOBMAGNET_COLD_VOICE=1` without
  explicit counsel approval). Even enabled, each contact still needs written consent.
- ⬜ **Prior express *written* consent** capture mechanism signed off by counsel.
- ⬜ **DNC registry access/scrubbing** subscription.
- ⬜ AI-voice provider + **STIR/SHAKEN** considerations (voice only, last).

---

## App secrets / config (the `.env` keys we'll add as we go)
Tracked here so you have one checklist. Details in `.env.example`.
- `JOBMAGNET_SECRET` — set a long random value before any non-local use. Also signs the
  CAN-SPAM unsubscribe links, so keep it stable (changing it invalidates old opt-out links).
- `JOBMAGNET_SECRETS_KEY` — encrypts connection credentials at rest. **Set before connecting
  any real account** (see the Security section above).
- `JOBMAGNET_WEBHOOK_TOKEN` — shared secret for inbound webhooks. **Set before
  deploying**; while empty the webhooks are open (local dev only).
- AI brain (see the two-tier section up top): `ANTHROPIC_API_KEY` (+ optional
  `JOBMAGNET_BRAND_MODEL`, default `claude-sonnet-5`), `DEEPSEEK_API_KEY` (+ `DEEPSEEK_MODEL`,
  `DEEPSEEK_BASE_URL`), `MINIMAX_API_KEY` (+ `MINIMAX_MODEL`, `MINIMAX_BASE_URL`).
  Spend caps: `JOBMAGNET_LLM_DAILY_CAP_USD` (default 25), `JOBMAGNET_LLM_TENANT_DAILY_CAP_USD`
  (default 3). Set the platform cap to 0 to disable all real LLM.
- Twilio: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`.
- Email: `JOBMAGNET_EMAIL_FROM`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`.
- Google Business Profile one-click connect: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
  `GOOGLE_REDIRECT_URI` (must match the redirect URI whitelisted in Google Cloud). See
  Phase 2 above. While unset, the Connect button is a safe disabled no-op.
- Optional connectors: `GBP_ACCESS_TOKEN` (legacy manual token; the OAuth flow above
  supersedes it), `META_ACCESS_TOKEN`, `JOBMAGNET_IMAGE_KEY`, `FIRSTBACK_API_URL` +
  `FIRSTBACK_API_KEY`.
- Cold channels (after attorney sign-off only): `JOBMAGNET_COLD_SMS=1`.
