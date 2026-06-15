"""Local SEO / AEO helpers (Phase 2).

Generates structured data (schema.org JSON-LD) from the Business Brain. This is real,
shippable value with no external dependency: most contractor sites have no schema, and
LocalBusiness + Service + FAQ markup measurably lifts click-through and is what AI
answer engines (ChatGPT, Google AI Overviews) read to cite a business. The owner pastes
the snippet into their site's <head>.
"""
import json


def localbusiness_schema(business, faqs=None):
    """A schema.org JSON-LD block: LocalBusiness + the services it offers, and an
    optional FAQPage. Returns a pretty-printed string ready to paste in a <script
    type="application/ld+json"> tag."""
    b = business
    name = b.get("name") or "Your Business"
    services = [s.strip() for s in (b.get("services") or "").replace("\n", ",").split(",")
                if s.strip()]

    local = {
        "@context": "https://schema.org",
        "@type": "HomeAndConstructionBusiness",
        "name": name,
        "description": (b.get("differentiators") or "").strip() or
                       f"{b.get('trade', 'Home services')} serving {b.get('service_area', 'the local area')}.",
        "areaServed": b.get("service_area") or "",
        "knowsAbout": services,
    }
    if b.get("trade"):
        local["slogan"] = b["trade"]
    # Offer catalog from services.
    if services:
        local["makesOffer"] = [
            {"@type": "Offer", "itemOffered": {"@type": "Service", "name": s}}
            for s in services
        ]

    blocks = [local]
    if faqs:
        blocks.append({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faqs
            ],
        })
    payload = blocks[0] if len(blocks) == 1 else blocks
    return json.dumps(payload, indent=2, ensure_ascii=False)
