# JobMagnet — Strategy

**Date:** 2026-06-14 · **Status:** vision / pre-build
**Product:** AI-run marketing engine for the trades — the top-of-funnel sibling to
[RingBack](../ringback).
**Tagline:** *Become the contractor jobs come to.*

---

## 1. The thesis

RingBack proved the bottom of the funnel: catch the missed call, text back, book
the estimate. It is **reactive** — it only acts on demand the contractor already
earned. JobMagnet is the **proactive** half: it *manufactures* demand and pours it
into RingBack to be booked.

```
TOP OF FUNNEL  ─────────────────────────────►  BOTTOM OF FUNNEL
JobMagnet (generate)                            RingBack (capture + convert)
 • AI social content engine                      • missed-call text-back
 • AI cold email                                 • AI booking by SMS/voice
 • AI cold SMS / voice (gated)                   • reminders + follow-ups
 • ads / local-SEO assist                        • owner alerts
        │                                                │
        └──────────►  one closed-loop ROI dashboard  ◄───┘
```

The two together are the product the market keeps failing to ship: **one
connected system for one vertical**, sold to one buyer.

---

## 2. The market gap (our wedge)

From the competitive research ([COMPETITORS.md](COMPETITORS.md)):

1. **Trades agencies are almost all inbound.** Market Movers, Advanced AI, Hook,
   Predictive Sales, Coherency — SEO, ads, GBP, capture. Real **outbound**
   (cold email/text/voice) for the trades is largely absent.
2. **The good outbound tools aren't trades-built or compliance-built.** Smartlead,
   Reply.io, AiSDR, Artisan, Retell are horizontal and sprinting into cold
   outreach carelessly. None speak "roofer."
3. **Nobody closes the loop.** GoHighLevel is the closest "everything," but it's a
   generic toolbox you assemble — and it doesn't book the job.

**JobMagnet's wedge:** the only trades-native engine that does *outbound demand-gen
→ booked job* as one compliant, productized system (via RingBack).

---

## 3. Positioning

- **Who:** home-services contractors (start narrow — see §7).
- **Against Angi/HomeAdvisor:** "Stop renting shared leads that go to five of your
  competitors. Own your demand."
- **Against generic agencies:** "We're built for the trades, not retail. One
  connected system — not a Facebook ad here and some SEO there." (This is the #1
  documented reason contractor marketing fails: disconnected tactics.)
- **Against horizontal AI tools:** "Compliance-built for cold outreach, and it
  books the job — not just sends the email."
- **Framing:** an **AI marketing team / AI employee**, not "software." Reframes
  price as *cheaper than a hire* (the AiSDR/Artisan/GHL playbook).

---

## 4. What works best in this market (steal list)

Distilled from the top players — the patterns that repeat among winners:

1. **Productized fixed tiers, not custom quotes** (Predictive Sales AI: $295→$1,495).
2. **"AI employee / marketing team" price framing** (AiSDR $900/mo, Artisan $2–5k/mo).
3. **Exclusive territory protection** (Market Movers, Coherency, Minyona) — premium
   lever *and* retention lock; trades fear funding a competitor.
4. **Niche hard by trade** — generic agencies fail because they don't understand
   *how people hire trades* (clarity, speed, proof).
5. **"System, not parts"** — sell the connected funnel, not isolated tactics.
6. **Outcome / ROI proof** — pay-per-booked-appointment energy (Minyona); show
   *recovered revenue*, not impressions. (RingBack already has the ROI-dashboard
   pattern.)
7. **Intent-data targeting** — property-level + storm data (Predictive Sales),
   income-zone geo (Advanced AI).

---

## 5. Channels (build priority)

Ordered by **legal risk** — start where the footing is sane, gate the dangerous
parts behind consent. (See §6.)

| Priority | Channel | Risk | Notes |
|---|---|---|---|
| 1 | **AI social content engine** | Low | Auto-generate posts + images on a cadence; schedule/publish. Steal: PostEverywhere, GHL AI Employee. Immediate, safe value. |
| 2 | **AI cold email** | Low–med | CAN-SPAM (opt-out + physical address). Steal: Smartlead deliverability, AiSDR personalization. |
| 3 | **Local SEO / GBP + ads assist** | Low | Owned channels that compound; intent targeting. |
| 4 | **AI cold SMS** | **High** | TCPA: marketing SMS generally needs prior express *written* consent. Reuse RingBack `messaging` + `contacts_consent`. Gate hard. |
| 5 | **AI cold voice** | **Highest** | FCC treats AI voice as artificial/prerecorded. **Do not lead with this.** Consent-gated, late-stage, lawyer-reviewed. |

---

## 6. Compliance — the moat AND the landmine

⚠️ **RingBack's legal safety does NOT transfer.** RingBack is safe *because* it is
informational and the customer called first. JobMagnet contacts strangers first —
a different legal regime entirely:

- **Cold SMS marketing** → generally prior express **written** consent (TCPA).
- **Cold AI voice** → FCC: AI-generated voice = artificial/prerecorded; the
  highest-risk category. RingBack itself refuses to auto-dial AI voice without an
  affirmative reply.
- **Cold email** → CAN-SPAM: clear opt-out, no deception, physical postal address.
- **DNC registry** scrubbing + per-state rules for any phone outreach.

**This is the wedge, not just the risk.** We already built the spine in RingBack —
the `contacts_consent` ledger, opt-out NLU, quiet hours, A2P 10DLC / STIR-SHAKEN
knowledge. Lean into "the compliant outbound engine for the trades" as a
*selling point*. **A TCPA attorney must review consent flows before any cold
phone/SMS channel ships to real customers** (same gate as RingBack's voice work).

---

## 7. Go-to-market

- **Start with one or two trades** where there's domain credibility
  (roofing/HVAC or painting). Win the niche, then widen — the opposite of
  GoHighLevel's "everything for everyone."
- **Land with the safe, instant-value channel** (social content + email), expand
  the account into outbound + the RingBack booking loop.
- **Sell the loop:** "We generate the lead *and* book it." No competitor can say
  both halves credibly.

### Pricing (draft — mirror the Predictive Sales AI ladder)

| Tier | ~Price/mo | Includes |
|---|---|---|
| **Spark** | $299–499 | AI social content engine + email nurture |
| **Engine** | ~$995 | + AI cold email/SMS outbound (gated), intent targeting |
| **Done-for-you** | $2,997+ | Full AI marketing team + ads + exclusive territory + RingBack loop |

Frame every tier as "your AI marketing team for less than a part-time hire."
Add **exclusive territory** as a premium/retention lever.

---

## 8. Build approach (decision pending)

- **Reuse RingBack infrastructure** (multi-tenant DB, `messaging` seam, Claude
  brain, gated-integration pattern, `contacts_consent`, design system) — see
  [README.md](README.md).
- **Open question:** shared monorepo with a common internal library vs. a separate
  repo that imports a shared package. The closed-loop ROI dashboard implies tight
  data sharing with RingBack — lean toward shared storage/lib. Decide before first
  code.
- **Keep RingBack's discipline:** every integration a safe no-op until configured;
  honest "simulated vs. live" UI; nothing blocks the hot path; pure, testable
  decision logic.

---

## 9. Open questions

- Monorepo vs. separate repo (above).
- Which trade(s) to launch first.
- Do we resell/whitelabel an existing engine (Smartlead/Retell) under the hood to
  move fast, or build native on the RingBack stack?
- Lead data source for outbound (build a scraper/enrichment vs. partner like Clay).
- Brand relationship: is JobMagnet co-branded with RingBack, or a clean separate
  brand that "integrates with" RingBack?
