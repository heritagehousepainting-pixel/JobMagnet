"""Paid ads assist (Phase 4).

Advisory, not auto-managed (we don't touch the ad account yet): budget guidance from
the contractor's revenue and copy generation. Numbers are the directional 2026
benchmarks captured in MARKET_ECONOMICS.md.
"""
# Cost-per-lead benchmarks (blended, USD) by channel.
CPL_BENCHMARKS = {"google_lsa": 53, "google_ads": 110, "facebook_ads": 30}
BUDGET_PCT = (0.08, 0.12)     # total marketing as a share of revenue (growth mode)
PAID_SHARE = (0.60, 0.70)     # of marketing budget that goes to paid ads


def recommend_budget(annual_revenue):
    """A monthly budget recommendation with an expected-leads estimate. Spend the
    paid budget LSA-first (cheapest qualified lead)."""
    rev = max(0.0, float(annual_revenue or 0))
    total_lo, total_hi = rev * BUDGET_PCT[0] / 12, rev * BUDGET_PCT[1] / 12
    paid_lo, paid_hi = total_lo * PAID_SHARE[0], total_hi * PAID_SHARE[1]
    seo_lo, seo_hi = total_lo * (1 - PAID_SHARE[1]), total_hi * (1 - PAID_SHARE[0])
    mid_paid = (paid_lo + paid_hi) / 2
    return {
        "annual_revenue": rev,
        "total_lo": round(total_lo), "total_hi": round(total_hi),
        "paid_lo": round(paid_lo), "paid_hi": round(paid_hi),
        "seo_lo": round(seo_lo), "seo_hi": round(seo_hi),
        "est_lsa_leads": round(mid_paid / CPL_BENCHMARKS["google_lsa"]) if mid_paid else 0,
        "cpl": CPL_BENCHMARKS,
    }
