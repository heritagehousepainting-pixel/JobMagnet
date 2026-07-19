# Ship-Readiness Checklist

Current honest rating: **6/10** ("ready to ship").
- Engineering foundation: ~8–9 (tests pass, honest integration gating, security hardening, deploy config, responsive polished UI).
- "Actually does the paid job for a real tenant": ~4–5 (core value loops still simulated/unconfigured; one security must-do pending).

Definitions of "ship":
- **Honest beta / waitlist / demo on a domain** → already ~8/10. Deployable today; it won't misrepresent anything.
- **Real contractors paying to send texts & manage reviews** → ~5/10 until the blockers below are cleared.

Source of truth for details: `SETUP_NEEDED.md` and `AUDIT_TRUTH.md`.

---

## 6 → 8 — Ship-blockers (clear these before onboarding paying tenants)

### Security
- [ ] **Set `JOBMAGNET_SECRETS_KEY`** before any real account is connected.
  Until set, stored connection credentials (Twilio/Google/Meta) are **cleartext at rest**;
  the Connections page shows a red "not yet encrypted" warning.
  - Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
  - Add to prod env (`.env` / Render); verify the warning clears and new writes are sealed.
  - Rotating the key later requires re-entering each connection's credentials.

### Messaging (SMS value loop)
- [ ] **Connect Twilio (live SMS).** SMS is simulated (logged, not sent) until configured.
  - Add `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` to prod env.
  - Confirm Connections shows Twilio "live"; send a real test text; verify webhook signature check.
- [ ] **Complete A2P 10DLC brand + campaign registration.** Without it US carriers may block/filter real SMS.
  - Register brand + campaign; associate the sending number; link the hosted SMS privacy/terms pages.
  - Verify deliverability with a real send.

### Email (delivery + contact form)
- [ ] **Wire email delivery (SMTP/provider) + SPF/DKIM/DMARC.** Email is simulated until configured.
  - Choose provider (Postmark/SendGrid/SES), add credentials (Phase 0 SMTP).
  - Add SPF/DKIM/DMARC DNS records on the sending domain.
  - Wire `POST /contact` to actually deliver (currently appends to `contact_inbox.log` only);
    point the placeholder `hello@jobmagnet.app` at a real mailbox.

### Reviews (reviews value loop)
- [x] **GBP review-pull implemented** (`reviewsync.pull_reviews`) — fixed 2026-07-19: it now
  uses the stored combined `accounts/X/locations/Y` resource + on-demand token refresh (a
  phantom `account_id` read had forced `pending` forever). Live path covered by stubbed-API
  tests: ingest, rating map, dedupe.
- [ ] **Verify at first real connect**: the GET uses the v4 host matching the stored resource
  shape; Google keeps migrating Business Profile APIs — confirm the endpoint against a real
  connected account, then confirm `simulated` → `pending` → `live` end-to-end.

---

## 8 → 9+ — Launch polish & remaining build (after blockers)

### Public site / launch ops
- [ ] **Domain + Open Graph / social share image** (site is deploy-ready; favicons are DONE —
  `/static/favicon-*.png`).
- [x] **Rate-limit the public `POST /contact`** — per-IP sliding window added 2026-07-19 (429 on burst).
- [ ] **SEO meta** — add `<link rel=canonical>`, Open Graph tags, and JSON-LD structured data to
  the public templates (`<meta name=description>` is already in `site_base.html`).

### Still-simulated integrations (build or cut from the pitch)
- [ ] **AI image generation** — `ai.generate_image` is prompt-only (always `simulated`); wire a provider call, or drop the claim.
- [x] **Managed paid ads** — RESOLVED 2026-07-19 by retirement: the promise was removed from Scale
  (nothing managed an ad account) and replaced with the real LSA Concierge. See CAPABILITY_BACKLOG.
- [ ] **Neighbor Mail v1** — v0 (assisted print + EDDM) is live; automated print-and-mail (Lob) is
  parked with a MONEY-gate trigger in CAPABILITY_BACKLOG.
- [ ] **FirstBack booking-sync** — wired and gated, but the bookings GET shape (`/bookings`, Bearer, list/envelope JSON) needs matching to FirstBack's real API once `FIRSTBACK_API_URL` + `FIRSTBACK_API_KEY` are set.

---

## Already done (the 8–9 foundation)
- Test suite robust: `test_smoke` ~440 pass, `test_compliance_core` 47, `test_firstwin` 30,
  `test_growth` 39 — all green as of 2026-07-19 (new-client engines + reviewsync fix included).
- Honest integration gating — every seam reports real `simulated`/`live`/`error` and never fakes success (`AUDIT_TRUTH.md`).
- Security hardening — CSRF, fail-closed Twilio webhook signatures, session auth, credential sealing (when the key above is set).
- Deploy-ready — `render.yaml` + gunicorn; SQLite→Postgres migration complete.
- UI — responsive (no overflow/overlap at 360/768/1280/1920), brand/token cleanup done, marketing site polished.
- Compliance moat — TCPA quiet-hours + append-only consent ledger; per-tenant hosted SMS legal pages.
