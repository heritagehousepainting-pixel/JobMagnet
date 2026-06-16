# JobMagnet — What YOU need to set up

A running tab of everything that requires **your** action to go from *simulated* to
*live* (accounts, API keys, approvals, legal). The app is built so every one of these
is a **safe no-op until configured** — nothing breaks while these are pending; the UI
just shows "simulated" instead of "live." Updated as we build.

Legend: ⬜ not started · 🟡 in progress · ✅ done

---

## Already done
- ✅ **MiniMax API key** — in `.env` (`MINIMAX_API_KEY`), brain is live.
- ✅ **Public marketing site** — home (`/`), `/pricing`, `/how-it-works`, `/contact`
  are built and live (dark, premium). Pricing pulls from `plans.py`, so changing a
  plan there updates the site automatically.

## Code-pending — NOT just a credential (won't work until built)
The truthfulness audit (2026-06-15) confirmed the site now only claims what the code
does. A few seams are gated honestly but still need **code**, not just a key — the UI
says so:
- 🟡 **RingBack auto booking-sync** — the bookings pull + heartbeat hook are now WIRED.
  `roi.sync_ringback` does a real bookings GET and adds deduped `origin='ringback'`
  conversions; the autonomy heartbeat (`/tasks/tick`) runs it per tenant. It stays a safe
  no-op (mode "simulated") until you set `RINGBACK_API_URL` + `RINGBACK_API_KEY`, then it
  goes live automatically (mode "live"; "error" if RingBack is unreachable, never a fake
  success). Only remaining: the bookings GET shape (`/bookings`, Bearer auth, list/envelope
  JSON) may need matching to RingBack's real API. Manual "Log a booked job" still works.
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
- ⬜ **Domain + favicon + OG/social image.** The site is ready to deploy; it needs a
  domain, a favicon, and an Open Graph share image for link previews.
- ⬜ (Optional) **Rate-limit the public contact POST.** It's CSRF-protected but
  unauthenticated; add a simple per-IP limit before launch to avoid log spam.

## Security — before onboarding real tenants  ⚠️
- ⬜ **`JOBMAGNET_SECRETS_KEY`** — encrypts stored connection credentials (Twilio/Google/
  Meta tokens) **at rest**. While unset (dev), credentials are stored in the clear and the
  Connections page shows a red "not yet encrypted" warning. Generate once and put in `.env`:
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Set this **before any real
  account is connected**. (Existing plaintext rows keep working after you set it; new writes
  are sealed. If you ever rotate this key, re-enter each connection's credentials.)

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
  triggers it manually. Until connected it honestly reports 'simulated' (monitoring dormant),
  and once connected 'pending' until the reviews GET is implemented — it never fabricates
  reviews. Reply auto-posting is intentionally out of scope (no real GBP reply connector).

## Phase 2 — Content & Local
- ⬜ **Google Business Profile API** (OAuth) to publish GBP posts automatically.
- ⬜ **Meta (Facebook/Instagram) app + app review** to auto-publish. This is the slow
  one (weeks). Until approved, FB/IG is "assisted publish" (copy/paste + download).
- ⬜ **AI image generation key** (provider TBD) for post images/before-afters.
- ⬜ Confirm the **website** where schema markup / AEO landing pages will live (and how
  we deploy to it). The Local SEO page generates the JSON-LD; you paste it into your
  site `<head>`.
- ⬜ **Public URL + Twilio inbound webhook** pointed at `POST /webhooks/sms` so
  texting a job photo creates a draft (photo-by-text). Needs the app deployed (or a
  tunnel) and per-business sending numbers to map texts to the right tenant.
- ⬜ **Autonomy heartbeat cron** — hit `POST /tasks/tick` on a schedule to make the
  product run on its own: it publishes due scheduled posts AND runs each Premium+ tenant's
  take_over plays through the gated seams. Token-gated by `JOBMAGNET_WEBHOOK_TOKEN` (send it
  as a `token` form field). **Safe to run every ~15 min** — Phase 1 (content cadence) now
  paces the get_found/show_work plays: each only redrafts once its platform window has passed
  (Google ~weekly, showcase ~every few days), so a frequent heartbeat publishes and sends
  without piling up drafts. The older per-tenant `POST /scheduler/run` button still works for
  publishing due posts by hand.

## Phase 3 — ROI loop
- ⬜ **Tracked phone numbers** (Twilio) per channel for attribution.
- 🟡 (Optional) **RingBack connection** — if you want the closed loop, set `RINGBACK_API_URL`
  + `RINGBACK_API_KEY` so its booking events feed cost-per-booked-job. The pull + heartbeat
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
- Twilio: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`.
- Email: `JOBMAGNET_EMAIL_FROM`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`.
- Optional connectors: `GBP_ACCESS_TOKEN`, `META_ACCESS_TOKEN`, `JOBMAGNET_IMAGE_KEY`,
  `RINGBACK_API_URL` + `RINGBACK_API_KEY`.
- Cold channels (after attorney sign-off only): `JOBMAGNET_COLD_SMS=1`.
