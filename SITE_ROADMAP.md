# JobMagnet — Site Build Roadmap

**Goal (2026-06-15):** Build the entire site top to bottom — the missing public
marketing site *and* a premium overhaul of the signed-in app — so JobMagnet looks
and feels like it lives up to its ~$300/mo price point.

**Decisions locked with the owner:**
- Public site visual direction: **dark, premium, cinematic** (dark hero, emerald
  glow, big confident type). Lead line: *"Already on the next job."*
- Signed-in scope: **add JobMagnet's conversational home + polish every page.**
- Keep the established **Emerald** accent and **Archivo** type. Keep the existing
  route structure and the 99-assertion smoke suite green.

## Hard constraints (don't break)
- `login` POST must redirect to `/dashboard` (test asserts it).
- `/dashboard` must keep the content approval queue strings: "Awaiting your
  review", "Approve", "Published" (tests assert them). → JobMagnet's home is built
  *around* the approval queue (the queue = "items waiting on your yes").
- CSRF token on every form; multi-tenant `business_id` scoping; honest
  simulated-vs-live status everywhere.

## Phases
1. **Public marketing site** — dark theme layer (`site.css`) + public base
   layout; `/` (home), `/pricing`, `/how-it-works`, `/contact`. Public nav +
   footer. `/` serves marketing to logged-out visitors, redirects logged-in to
   `/dashboard`. Pricing pulled from `plans.py`.
2. **JobMagnet home** — redesign `/dashboard` into "JobMagnet's Today": briefing hero +
   approval queue (preserved) + wins/stats.
3. **Auth polish** — premium split-layout login/signup.
4. **Signed-in polish** — elevate Game Plan, Reviews, Contacts, Results,
   Settings, Compose, Get Found, Plan with JobMagnet voice + stronger states.
5. **Tests + double audit** — new route tests, full suite green, two audit
   passes (function/wording/layout/security), reconcile SETUP_NEEDED.

## Done when
- Every public + signed-in route renders with no errors, walked live.
- Public site sells the price point (clear value, JobMagnet, proof, pricing, CTA).
- JobMagnet's home is the post-login front door; every signed-in page reads premium.
- Full smoke suite green; new tests added for the new surfaces.
