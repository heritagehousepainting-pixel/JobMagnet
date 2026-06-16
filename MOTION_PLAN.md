# Motion Plan — Firecrawl-inspired motion for JobMagnet

**Goal (2026-06-15):** Bring Firecrawl's *technical-editorial* motion language to the
JobMagnet public site, adapted to our brand (dark + emerald, not light + orange).
Studied from 7 screen recordings of firecrawl.dev.

## What Firecrawl actually does (the source motions)
1. **Scroll-reveal fade-up + stagger** — the dominant motion; sections/cards rise and
   fade as they enter the viewport.
2. **Hero entrance** — staggered reveal of eyebrow → headline → subhead → CTAs on load.
3. **"Alive" technical texture** — dotted grid + twinkling crosshair `+` markers +
   shimmering ASCII/dot "ember" clusters (esp. the CTA band).
4. **Monospace gutter annotations** — `[ 01 / 07 ] MAIN FEATURES` editorial indices.
5. **Count-up stats**, **card hover lift**, pricing toggle.

## What we'll build (adapted to JobMagnet)
- **P1 · Scroll-reveal engine** — one dependency-free IntersectionObserver
  (`static/motion.js`) + CSS. `data-reveal` on elements, `data-reveal-group` to
  stagger a container's children. Honors `prefers-reduced-motion` (shows everything,
  no animation). Applied across home, pricing, how-it-works.
- **P2 · Hero entrance** — staggered load reveal of the hero stack.
- **P3 · Emerald "ember" field** — a subtle canvas of drifting emerald dots + a few
  twinkling `+` crosshairs, behind the hero and the CTA band. Gated: DPR≤2, paused
  when offscreen/tab hidden, single static frame under reduced-motion. The headline
  stays the LCP; zero layout shift.
- **P4 · Count-up** — proof stats ($53, the "1") count up when scrolled into view.
- **P5 · Editorial section indices** — monospace `[ 01 / 06 ]` labels on section heads.
- **P6 · Hover polish** — consistent lift/border-highlight on feature/step/price cards.

## Guardrails
- No new dependencies; vanilla JS, deferred. Reduced-motion fully respected.
- Brand stays emerald; no orange. Marketing pages only (the app is a tool).
- Zero CLS; hero headline remains the LCP element.

## Done when
- Sections/cards reveal on scroll with a cohesive cadence; hero animates in on load.
- The ember field reads "alive" but subtle, and is off under reduced-motion.
- Stats count up; section indices present. All public routes still 200, suite green.
