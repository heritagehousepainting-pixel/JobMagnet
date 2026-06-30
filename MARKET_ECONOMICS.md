# JobMagnet — Market Economics (what it actually costs a contractor to win)

**Researched:** 2026-06-15 (live web). This is the money truth our product has to
respect: what contractors spend, where it goes, and the cost-per-lead reality by
channel and trade. If JobMagnet can't move these numbers, it isn't worth buying.
Companion to [STRATEGY.md](STRATEGY.md) and [COMPETITORS.md](COMPETITORS.md).

---

## 1. The marketing budget — what to spend

Industry guidance for **growth-oriented** home-services contractors:

- **Total marketing budget: 8–12% of gross revenue.** (Maintain-only businesses
  run 5–8%; aggressive growth 12–15%.)
- Of that budget: **60–70% to paid digital** (Google Ads, LSAs, Meta) and
  **30–40% to SEO + website/owned channels.**

| Annual revenue | Total marketing/mo | Of which paid ads/mo |
|---|---|---|
| $500K | $3,300–5,000 | $2,000–3,500 |
| $1M | $6,600–10,000 | $4,000–7,000 |
| $2M | $13,300–20,000 | $8,000–14,000 |

**Implication for pricing:** a contractor at ~$1M revenue has ~$6.6–10K/mo to
spend. Our tiers ($299 → $995 → $2,997) must read as a *fraction* of that and be
justified by leads booked, not features.

---

## 2. Cost per lead — the channel + trade reality (2026)

CPL is rising ~10%+ YoY as more contractors bid into paid search. Numbers vary a
lot by source and metro, so treat these as **ranges, not gospel** — but the
*ordering* is stable.

### By channel (blended home services)
| Channel | Cost per lead | Notes |
|---|---|---|
| **Google Local Services Ads (LSA)** | **~$25–80** (avg ~$53) | Cheapest high-intent. Pay-per-lead, top of the page, "Google Screened" badge. ~44% book rate, ~7.8x ROAS in aggregate datasets. |
| **Google Search Ads (PPC)** | **~$90–125 blended** (non-branded higher) | High intent but ~2x LSA cost per lead. CPCs avg ~$7.85, roofing/gutters ~$10.70. |
| **Meta / Facebook Ads** | **~$15–40 raw lead** | Cheap leads, *low intent* — demand-capture vs demand-creation. Needs strong creative + heavy follow-up or leads rot. |
| **Angi / HomeAdvisor / Thumbtack** | Sub + per-lead | Shared leads sold to ~5 competitors; contractors widely report ~90% are tire-kickers. The thing they hate — our anti-positioning. |

### By trade (Google Ads CPL, directional 2026)
Roofing is the most expensive lead in the trades; cleaning/handyman the cheapest.

| Trade | LSA CPL | Google Ads CPL (range across sources) |
|---|---|---|
| Roofing | $55–90 | $79 → $124 → $228 (non-branded, high end) |
| HVAC | $45–80 | $45 → $149 |
| Plumbing | $35–65 | $52 → $183 |
| Electrical | $40–75 | $58 |
| Cleaning / handyman / pools | — | $45–54 (most efficient) |

### The metric that actually matters
**Cost per *booked job*, not cost per lead.** A $15 Facebook lead that never closes
is worth less than a $100 Google lead that becomes a $15K job. Benchmarks worth
anchoring to: LSA avg cost-per-paying-customer ~$233, avg ticket ~$1,826.
→ **JobMagnet's ROI dashboard must report cost-per-booked-job (via the FirstBack
loop), which no point tool can compute because they don't see the booking.**

---

## 3. Where the money should go (channel priorities)

1. **Google Local Services Ads first.** Cheapest qualified lead, highest intent,
   pay-per-lead not per-click. The "Google Screened" badge (background +
   insurance check) still matters even though Google dropped the customer
   money-back "Guaranteed" promise in Oct 2025. **This is the contractor's single
   best paid dollar — JobMagnet must help set up + optimize the LSA profile.**
2. **Local SEO + Google Business Profile (GBP).** The compounding owned asset.
   See §4 — this is where 30–40% of budget should live.
3. **Google Search Ads** for high-intent keywords LSA doesn't cover.
4. **Meta** for retargeting, brand, and visual trades (remodels, painting,
   landscaping) — strong creative + fast follow-up, never standalone.
5. **Reviews/reputation** as a force-multiplier on *all* of the above (§5).

---

## 4. SEO that ranks a contractor in 2026

Local pack ranking weight (directional, from local-SEO ranking studies):

- **Proximity to searcher: ~55%** — the single biggest factor (and not directly
  controllable, which is why the rest matters so much).
- **Google Business Profile signals: ~32%** — the highest-impact thing we *can*
  control.
- **Reviews: ~16–20%.**
- **On-page / citations: ~7–19%.**

### The GBP playbook (highest ROI per hour)
- **Primary category is the single highest-impact field.** Get it exactly right.
- **Weekly GBP posts** (What's New / Offer / Event) — most contractors never do
  this; easy AI win.
- **Respond to every review within 72h** — the response text is itself a content
  field Google reads for keyword relevance.
- **Review acquisition system** — volume + recency + response rate.

### Schema markup (structured data) — punching above its weight
- **LocalBusiness schema → ~14% lift in GBP click-through.** FAQ schema adds ~9%.
- **Service** and **FAQ** schema help both Google *and* AI answer engines extract
  and recommend the business.
- Most contractor sites have none → cheap, automatable edge JobMagnet can ship.

### Answer Engine Optimization (AEO/GEO) — the 2026 frontier
Homeowners increasingly ask **ChatGPT / Google AI Overviews** "who's the best
roofer near me" *before* they ever see a website. To get cited by AI engines:

- **Answer-first content** (the question, then a direct answer up top).
- **Per-location pages** with full NAP, services, hours, FAQs, unique value — AI
  engines extract structured local facts to cite.
- **Entity consistency** across the web (NAP identical everywhere).
- **Structured data** (schema) is the substrate AI reads.

→ **This is a wide-open feature: an AI marketing engine is uniquely positioned to
do AEO. Build "get found by AI" as a headline capability.**

---

## 5. Reviews & reputation — the cheapest lever

Reputation feeds SEO (16–20% of ranking), ad CTR, and close rate simultaneously.
The category is proven and expensive (Podium $399–599/mo, Birdeye $200–700/mo,
NiceJob the SMB pick with Jobber/Housecall integrations). Core mechanics to own:

- **Automated review invites by SMS** right after job completion (SMS >> email
  response rate).
- **AI-suggested review responses** (Google reads them; reply to all within 72h).
- **Aggregate + monitor** across Google/Facebook/etc.

→ Cheap to build on the FirstBack SMS rails, high perceived value, natural v0.2.

---

## 6. What this means for JobMagnet (design constraints)

1. **Report cost-per-booked-job, not vanity metrics.** Only the JobMagnet+FirstBack
   loop can — make it the centerpiece of the ROI dashboard.
2. **Lead with LSA + GBP + reviews** (cheapest, highest-intent, compounding,
   low legal risk) before any cold outbound.
3. **Schema + AEO are automatable, near-free edges** most agencies skip — ship
   them as standard.
4. **Price as a fraction of their existing ad budget**, justified by booked jobs.
5. **Don't out-tool the toolmakers** (GHL/Smartlead/Podium are deep). Win on
   *trades-native + the closed loop + compliance*, not feature count.

---

## Sources

- Budgets / ad split: [BaaDigi — FB vs Google for contractors](https://www.baadigi.com/blog/facebook-ads-vs-google-ads-for-contractors-which-gets-more-leads-per-dollar)
- CPL benchmarks: [LocaliQ home-services search benchmarks](https://localiq.com/blog/home-services-search-advertising-benchmarks/) ·
  [WordStream 2025 Google Ads benchmarks](https://www.wordstream.com/blog/2025-google-ads-benchmarks) ·
  [Searchlight — roofing Google Ads CPL](https://searchlightdigital.io/roofing-google-ads-cost-per-lead/)
- LSA: [Searchlight — LSA CPL by trade](https://searchlightdigital.io/google-local-service-ads-cost-per-lead/) ·
  [Pipeline On — are LSAs worth it 2026](https://pipelineon.com/blog/google-local-services-ads-2026/) ·
  [BlueGrid — LSA statistics 2026](https://bluegridmedia.com/lsa-statistics-2026)
- Local SEO / GBP / schema: [BizIQ local SEO statistics 2026](https://biziq.com/blog/local-seo-statistics-2026/) ·
  [AltaVista — contractor SEO checklist 2026](https://www.altavistasp.com/2026-contractor-seo-checklist/)
- AEO/GEO: [HubSpot — AEO trends 2026](https://blog.hubspot.com/marketing/answer-engine-optimization-trends) ·
  [Footbridge — AEO for contractors](https://www.footbridgemedia.com/marketing-tips/aeo-contractors-home-service-companies)
- Reputation: [Birdeye vs Podium 2026](https://revioreputation.com/blog/birdeye-vs-podium-2026-honest-comparison/)

---

## JobMagnet pricing + unit economics (decided 2026-06-15, built into the app)

**Cost to serve one contractor (COGS, managed model), ballpark 2026:**
- Twilio number ~$1.15/mo · A2P 10DLC campaign ~$2/mo (sole-prop low-volume) to ~$15/mo
  (standard) · outbound SMS ~$0.013 all-in (msg + carrier fee) · email (SendGrid) ~$0.20/mo
  · AI generation (MiniMax) ~$1-2/mo · hosting share ~$0.50.
- **Typical contractor ≈ $9-10/mo; heavy ≈ $36/mo.** One-time onboarding ~$20 (brand reg +
  vetting; toll-free verification is free). → Price is value-driven, not cost-driven.

**Anchors:** Podium/Birdeye ~$300-600/mo for *just* reviews+messaging; agencies $1.5-5k/mo;
Angi pay-per-lead $15-100. One extra booked job ($3-8k) pays back a plan 10-25x.

**The tiers (JobMagnet in every tier; tiers gate how much it DOES):**
| Plan | Price | Unlocks | COGS → margin |
|---|---|---|---|
| **Pro** | **$199/mo** | Advisor: drafts everything, you approve; all engines; ~750 texts | ~$10 → ~95% |
| **Premium** | **$299/mo** | + **Autopilot** (acts on its own), Speed-to-Lead/Reactivation/Referrals, closed-loop ROI; ~2,000 texts | ~$25-36 → ~88% |
| **Scale** | **$599/mo** | + managed paid ads (LSA/Meta), multi-location, priority; ~6,000 texts | ~$50-80 → ~85% |

Annual = ~2 months free · **$0 setup** (we handle provisioning + registration) · risk-reversal
trial. **Engine gate is live in code** (`plans.py`): autopilot is Premium+, managed ads is
Scale, text volume capped per plan. Real card billing (Stripe) = next step.
