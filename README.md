# JobMagnet

**Become the contractor jobs come to.**

JobMagnet is the **AI marketing engine for the trades**: it runs a contractor's
social content, reviews/reputation, local SEO + AI visibility, partner outreach,
paid-ads guidance, and (compliance-gated) cold outreach — and proves it all in
**cost per booked job**.

It is **standalone first**: its own messaging, consent, and conversion data, sellable
on its own. [FirstBack](../firstback) (missed-call text-back + AI booking) is an
**optional pluggable provider** — connect it and JobMagnet gets a richer booked-job
feed for the closed loop. One vertical (the trades), one buyer (the owner).

```
JobMagnet                         FirstBack
─────────                         ────────
generate demand        ──feeds──►  catch + book it
(social · cold email ·             (missed-call text-back ·
 cold SMS/voice · ads)              AI booking · reminders)
        │                                  │
        └──────────► one closed-loop ROI dashboard ◄────────┘
              "we got you the lead AND booked it"
```

## Status

**Core workflows across the 6 roadmap phases are built + tested** (Flask + SQLite,
port 8900), with live integrations behind honest connector gates. Verified end-to-end
by `test_smoke.py` (**405 assertions**) — run `./.venv/bin/python test_smoke.py`.
MiniMax is the live AI brain when configured. A **dark, premium public marketing site**
(home, pricing, how-it-works, contact) fronts the app, and the signed-in dashboard is
now **Mason's conversational home** (daily brief + approval queue).

What is **actually working** today:

| Page | Module | What it does |
|---|---|---|
| Dashboard / Compose | Content engine | AI social posts, approval loop, **scheduling**, **photo-by-text** capture, publish (GBP/assisted/simulated) |
| Reviews | Reputation | SMS review requests + AI-drafted responses |
| Local SEO | SEO / AEO | LocalBusiness + FAQ **schema markup**, answer-first FAQ for AI search |
| Contacts | Lead engine | Customers/partners/leads, consent ledger, **DNC suppression** |
| Outreach | Cold email | B2B partner emails, **CAN-SPAM** footer + working unsubscribe |
| Cold Outreach | Cold SMS/voice | **Hard-gated** (off until attorney sign-off + written consent) |
| Ads | Paid assist | Budget calculator (8–12% rule, LSA-first) + ad-copy generation |
| Results | Closed loop | **Cost per booked job** per channel; optional FirstBack feed |

**Compliance + honesty are enforced in code:** one gated messaging seam (consent +
quiet hours + opt-out/DNC), CSRF on every form, multi-tenant isolation, and an
honest "simulated vs live" status everywhere — nothing pretends to be real until
its connector is configured.

What needs **your setup** to go from simulated → live (Twilio, email, GBP/Meta,
FirstBack, attorney sign-off for cold phone): see **[SETUP_NEEDED.md](SETUP_NEEDED.md)**.

Not built yet (honest): real social publishing connectors (assisted/ simulated for
now), per-location landing **pages** (we generate the schema/FAQ, not standalone
pages), and automatic review monitoring (manual until the GBP API is connected).

Docs: **[ROADMAP.md](ROADMAP.md)** (the plan), [PRODUCT_SPEC.md](PRODUCT_SPEC.md)
(the modules), [MARKET_ECONOMICS.md](MARKET_ECONOMICS.md),
[STRATEGY.md](STRATEGY.md), [COMPETITORS.md](COMPETITORS.md).

## The thesis in one paragraph

The trades market is full of inbound agencies (SEO, ads, Google Business Profile)
and a separate world of horizontal AI outbound tools (Smartlead, AiSDR, Retell)
that aren't built for the trades and aren't compliance-built for cold outreach.
**Nobody convincingly bundles top-of-funnel demand-gen with bottom-of-funnel
booking for one vertical.** JobMagnet + FirstBack is that closed loop. The moat is
the part everyone underestimates: **compliance** (TCPA / CAN-SPAM / DNC) — which
FirstBack already has a spine for.

## What we'll reuse from FirstBack

JobMagnet should not reinvent infrastructure FirstBack already proved out:

| FirstBack asset | Reused for |
|---|---|
| Multi-tenant SQLite (`business_id` scoping) | Per-contractor JobMagnet accounts |
| `messaging.send_sms` outbound seam (gated/simulated) | Cold SMS sends |
| Pluggable Claude/MiniMax AI brain | Content + outreach generation |
| Gated-integration pattern (`configured()`/`is_connected()`) | Email/social/ads connectors |
| `contacts_consent` ledger + opt-out NLU + quiet hours | **The compliance moat** |
| Design system (`ui.css`, app shell, macros) | JobMagnet product UI |

> Resolved (2026-06-15): **standalone first, FirstBack optional**. JobMagnet has its
> own messaging/consent/conversion data; FirstBack plugs in as an optional provider
> for a richer closed loop. See [ROADMAP.md](ROADMAP.md).
