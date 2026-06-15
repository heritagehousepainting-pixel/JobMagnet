# JobMagnet — What YOU need to set up

A running tab of everything that requires **your** action to go from *simulated* to
*live* (accounts, API keys, approvals, legal). The app is built so every one of these
is a **safe no-op until configured** — nothing breaks while these are pending; the UI
just shows "simulated" instead of "live." Updated as we build.

Legend: ⬜ not started · 🟡 in progress · ✅ done

---

## Already done
- ✅ **MiniMax API key** — in `.env` (`MINIMAX_API_KEY`), brain is live.

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
- ⬜ (Later) **Google Business Profile API access** for pulling/monitoring reviews
  automatically (until then, monitoring is manual/simulated).

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
- ⬜ **Scheduler cron** — hit `POST /scheduler/run` on a schedule (e.g. every 15 min)
  to auto-publish due scheduled posts. Until then, use the "Publish due now" button.

## Phase 3 — ROI loop
- ⬜ **Tracked phone numbers** (Twilio) per channel for attribution.
- ⬜ (Optional) **RingBack connection** — if you want the closed loop, connect RingBack
  so its booking events feed cost-per-booked-job. Optional; JobMagnet works without it.

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
