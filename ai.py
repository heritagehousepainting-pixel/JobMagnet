"""JobMagnet's Content Engine.

Turns a short job update (and the Business Brain) into a ready-to-post social
caption, in the voice of the contractor's business.

Three modes, chosen by JOBMAGNET_PROVIDER, mirroring RingBack:
  1. "claude"  -- Anthropic Claude (best quality). Needs ANTHROPIC_API_KEY.
  2. "minimax" -- MiniMax, OpenAI-compatible. Needs MINIMAX_API_KEY.
  3. "demo"    -- a built-in templated writer so the product works with ZERO
                  setup. Good enough to demo the loop; replace/extend freely.

If the chosen provider has no key (or errors), JobMagnet falls back to demo so the
app never breaks.

>>> THIS FILE IS WHERE THE CONTENT LOGIC LIVES. Shape the output here. <<<
"""
import re
import sys

from config import (PROVIDER, PLATFORMS, DEFAULT_PLATFORM,
                    ANTHROPIC_API_KEY, CLAUDE_MODEL,
                    MINIMAX_API_KEY, MINIMAX_MODEL, MINIMAX_BASE_URL,
                    IMAGE_API_KEY)


def _platform_hint(platform):
    return PLATFORMS.get(platform, PLATFORMS[DEFAULT_PLATFORM])


def _system_prompt(business, platform):
    """Who the writer is + the brand + the rules it follows."""
    b = business
    return (
        f"You write social media posts for {b.get('name', 'a home-services business')}, "
        f"a {b.get('trade', 'home services')} business serving {b.get('service_area', 'the local area')}.\n\n"
        f"BRAND VOICE: {b.get('brand_voice', 'Professional, clear, and courteous.')}\n"
        f"SERVICES: {b.get('services', '')}\n"
        f"IDEAL CUSTOMER: {b.get('target_customer', '')}\n"
        f"WHAT SETS US APART: {b.get('differentiators', '')}\n"
        f"WORK WE WANT MORE OF RIGHT NOW: {b.get('capacity_note', '')}\n"
        f"OWNER / CONTACT: {b.get('owner_name', '')}\n\n"
        f"PLATFORM: {platform}. STYLE FOR THIS PLATFORM: {_platform_hint(platform)}\n\n"
        "RULES:\n"
        "- Write ONE finished post, ready to publish. Output only the post text.\n"
        "- Stay in the brand voice above. Sound like a real local business, not an ad agency.\n"
        "- Be specific about the work; never invent prices, dates, names, or guarantees "
        "that were not provided.\n"
        "- End with a soft, natural call to action to request a free estimate.\n"
        "- When it fits naturally, lean toward the kind of work we want more of right "
        "now (above). Never force it or fabricate a job.\n"
        "- Do not use dashes of any kind (no em dashes, en dashes, or double hyphens); "
        "use periods and commas instead.\n"
        "- No placeholders or brackets. No 'as an AI' meta text."
    )


def _user_prompt(topic):
    topic = (topic or "").strip()
    if not topic:
        return ("Write a general post that builds trust and invites homeowners to "
                "request a free estimate.")
    return f"Write a post about this job/update:\n{topic}"


# --------------------------------------------------------------------------
# REAL BRAINS
# --------------------------------------------------------------------------
def _claude_complete(system, user_text):
    import anthropic  # imported lazily so the other paths need no install
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=CLAUDE_MODEL, max_tokens=600, system=system,
        messages=[{"role": "user", "content": user_text}])
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _minimax_complete(system, user_text):
    import requests  # bundles certifi so TLS verifies cleanly on macOS
    resp = requests.post(
        f"{MINIMAX_BASE_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {MINIMAX_API_KEY}",
                 "Content-Type": "application/json"},
        json={"model": MINIMAX_MODEL,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user_text}],
              "max_completion_tokens": 800, "temperature": 0.8,
              "thinking": {"type": "disabled"}},
        timeout=30)
    resp.raise_for_status()
    return _strip_think(resp.json()["choices"][0]["message"]["content"])


def _strip_think(text):
    """Remove a MiniMax reasoning block (even an unclosed one) so it never leaks."""
    return re.sub(r"<think>.*?(?:</think>|$)", "", text or "", flags=re.DOTALL).strip()


# --------------------------------------------------------------------------
# DEMO MODE  (no API key needed)
# --------------------------------------------------------------------------
def _demo_post(business, topic, platform):
    """A templated post so the loop works out of the box."""
    name = business.get("name", "Our team")
    area = business.get("service_area", "your area")
    trade = (business.get("trade", "home services") or "home services").lower()
    job = (topic or "").strip()
    lead = (f"Another job wrapped up: {job}." if job
            else f"Proud of the work our crew is putting out across {area}.")
    cta = (f"Serving {area}. Message us for a free estimate and let's talk about your project.")
    body = f"{lead}\n\nQuality {trade} you can count on, done on time and done right. {cta}"
    if platform == "instagram":
        tag = re.sub(r"[^a-z0-9]", "", name.lower())[:20] or "localpros"
        body += f"\n\n#{tag} #{re.sub(r'[^a-z]', '', trade)[:18] or 'trades'} #localbusiness #freeestimate #qualitywork"
    elif platform == "google":
        body = f"{lead} {cta}"
    return _clean_punct(body)


# --------------------------------------------------------------------------
# SHARED
# --------------------------------------------------------------------------
def _clean_punct(text):
    """Brand voice uses standard punctuation only; never dashes. Convert any em
    dash, en dash, or double hyphen to a comma so none reach a published post."""
    text = re.sub(r"\s*[—–]\s*", ", ", text)  # em / en dash -> comma
    text = re.sub(r"\s*--+\s*", ", ", text)              # double hyphen -> comma
    text = re.sub(r"[ \t]+([,.!?;:])", r"\1", text)      # tidy space before punctuation
    text = re.sub(r",\s*,", ", ", text)                  # collapse doubled commas
    text = re.sub(r"[ \t]{2,}", " ", text)               # collapse runs of spaces
    return text.strip()


def _active_provider():
    """Which brain is actually usable right now (chosen provider + its key present)."""
    if PROVIDER == "claude" and ANTHROPIC_API_KEY:
        return "claude"
    if PROVIDER == "minimax" and MINIMAX_API_KEY:
        return "minimax"
    return "demo"


def generate_post(business, topic, platform=DEFAULT_PLATFORM):
    """Return a ready-to-review social post string for the given platform."""
    if platform not in PLATFORMS:
        platform = DEFAULT_PLATFORM
    provider = _active_provider()
    raw = None
    if provider in ("claude", "minimax"):
        system, user_text = _system_prompt(business, platform), _user_prompt(topic)
        try:
            raw = (_claude_complete if provider == "claude" else _minimax_complete)(
                system, user_text)
        except Exception as e:
            print(f"[jobmagnet] {provider} brain failed, using demo fallback: {e}",
                  file=sys.stderr, flush=True)
            raw = None
    if not raw:
        return _demo_post(business, topic, platform)
    return _clean_punct(raw)


def brain_mode():
    return _active_provider()


# --------------------------------------------------------------------------
# REVIEWS  (Phase 1)
# --------------------------------------------------------------------------
def review_request_message(business, contact_name=""):
    """A short, friendly SMS asking a past customer for a review. Kept as a clean
    template (not AI) so it's predictable and fast; the review link is appended by
    the caller."""
    name = business.get("name", "our team")
    hi = f"Hi {contact_name.split()[0]}, " if contact_name.strip() else "Hi, "
    return (f"{hi}thanks again for choosing {name}. If you have a moment, a quick "
            f"review really helps our small business. It only takes a minute:")


def _review_response_prompt(business, review):
    b = business
    stars = review.get("rating") or 0
    return (
        f"You are the owner of {b.get('name', 'a home-services business')}, a "
        f"{b.get('trade', 'home services')} business. Write a short, warm public reply "
        f"to this {stars}-star customer review. "
        f"BRAND VOICE: {b.get('brand_voice', 'Professional, clear, courteous.')}\n\n"
        f"REVIEW BY {review.get('author', 'a customer')}:\n{review.get('body', '')}\n\n"
        "RULES:\n"
        "- 2 to 4 sentences. Sound like a real local owner, grateful and specific.\n"
        "- Thank them by first name if available. If the review is critical, be "
        "gracious, take responsibility, and invite them to reach out directly. Never "
        "be defensive.\n"
        "- Do not invent details, names, prices, or promises.\n"
        "- No dashes of any kind; use periods and commas. Output only the reply text."
    )


def generate_review_response(business, review):
    """Draft a public response to a review, in the business's voice."""
    provider = _active_provider()
    if provider in ("claude", "minimax"):
        system = _review_response_prompt(business, review)
        try:
            raw = (_claude_complete if provider == "claude" else _minimax_complete)(
                system, "Write the reply now.")
            if raw:
                return _clean_punct(raw)
        except Exception as e:
            print(f"[jobmagnet] {provider} review reply failed, using template: {e}",
                  file=sys.stderr, flush=True)
    # Demo / fallback template.
    author = (review.get("author") or "there").split()[0]
    if (review.get("rating") or 5) >= 4:
        body = (f"Thank you so much, {author}. It was a pleasure doing this work for "
                f"you, and we are grateful you took the time to share your experience. "
                f"We hope to help you again.")
    else:
        body = (f"Thank you for the honest feedback, {author}. We are sorry this fell "
                f"short of what you expected. Please reach out to us directly so we can "
                f"make it right.")
    return _clean_punct(body)


# --------------------------------------------------------------------------
# LOCAL / AEO  (Phase 2)
# --------------------------------------------------------------------------
def _faq_demo(business):
    trade = (business.get("trade") or "home services").lower()
    area = business.get("service_area") or "your area"
    return [
        ("What areas do you serve?", f"We serve {area} and the surrounding communities."),
        ("Do you offer free estimates?",
         "Yes. We provide a free, no obligation estimate so you know the scope and price before any work begins."),
        ("Are you licensed and insured?",
         "Yes. We are fully licensed and insured for your protection and peace of mind."),
        ("How do I get started?",
         f"Reach out for a free estimate and we will schedule a visit to discuss your {trade} project."),
    ]


def generate_faq(business, n=5):
    """Answer-first FAQ pairs for the business, tuned for AEO (so AI answer engines
    can quote them). Returns a list of (question, answer) tuples."""
    provider = _active_provider()
    if provider in ("claude", "minimax"):
        b = business
        system = (
            f"You write concise FAQ content for {b.get('name','a home-services business')}, "
            f"a {b.get('trade','home services')} business serving {b.get('service_area','the local area')}. "
            f"SERVICES: {b.get('services','')}. WHAT SETS US APART: {b.get('differentiators','')}.\n"
            f"Write {n} frequently asked questions a homeowner would ask, each with a direct, "
            "answer-first response of 1 to 3 sentences. Do not invent prices or guarantees. "
            "No dashes; use periods and commas. Format EXACTLY as 'Q: ...' then 'A: ...' lines, "
            "one pair per question, no numbering, no extra text.")
        try:
            raw = (_claude_complete if provider == "claude" else _minimax_complete)(
                system, "Write the FAQ now.")
            pairs = _parse_qa(_clean_punct(raw or ""))
            if pairs:
                return pairs
        except Exception as e:
            print(f"[jobmagnet] {provider} FAQ failed, using template: {e}",
                  file=sys.stderr, flush=True)
    return _faq_demo(business)


def _parse_qa(text):
    """Parse 'Q: ... / A: ...' lines into (q, a) pairs."""
    pairs, q = [], None
    for line in (text or "").splitlines():
        line = line.strip()
        if line[:2].lower() == "q:":
            q = line[2:].strip()
        elif line[:2].lower() == "a:" and q:
            pairs.append((q, line[2:].strip()))
            q = None
    return pairs


def image_mode():
    """AI image generation status. No real image provider is wired yet, so this is
    always 'simulated' (prompt only) -- we never show 'live' for a call that returns
    no image. Restore the IMAGE_API_KEY gate here once generate_image makes a real
    provider call and returns a usable url."""
    return "simulated"


def generate_image(business, topic, platform=DEFAULT_PLATFORM):
    """Build the image prompt. Until a real provider is wired, this is simulated
    (prompt only, no url) -- an honest mode so the UI never implies an image exists
    when it does not."""
    prompt = (f"Professional, bright photo-style image for a {business.get('trade','home services')} "
              f"business social post about: {topic or 'quality local work'}. Clean, real, no text overlay.")
    # TODO: when IMAGE_API_KEY is set, call the provider here and return mode 'live'
    # with a real url. Until then, always simulated.
    return {"mode": "simulated", "prompt": prompt, "url": None}


# --------------------------------------------------------------------------
# ADS  (Phase 4)
# --------------------------------------------------------------------------
def _ad_copy_demo(business):
    trade = business.get("trade") or "Home Services"
    area = business.get("service_area") or "Your Area"
    return {
        "headlines": [f"{trade} in {area}", "Free Estimates, Fast Quotes",
                      "Licensed, Insured, Local", "Quality Work, Done Right",
                      "Book Your Estimate Today"],
        "descriptions": [
            f"Trusted local {trade.lower()} serving {area}. Call for a free estimate.",
            "On time, tidy crews and a workmanship guarantee. Get your free quote today."],
    }


def generate_ad_copy(business):
    """Google Search ad assets (headlines + descriptions) in the brand voice.
    Returns {'headlines': [...], 'descriptions': [...]}."""
    provider = _active_provider()
    if provider in ("claude", "minimax"):
        b = business
        system = (
            f"You write Google Search ads for {b.get('name','a home-services business')}, "
            f"a {b.get('trade','home services')} business serving {b.get('service_area','the local area')}. "
            f"WHAT SETS US APART: {b.get('differentiators','')}.\n"
            "Write 5 headlines (max 30 characters each) and 2 descriptions (max 90 characters each). "
            "High intent, local, a clear benefit and call to action. No dashes; use periods and commas. "
            "Format EXACTLY as 'H: ...' lines then 'D: ...' lines, nothing else.")
        try:
            raw = _clean_punct((_claude_complete if provider == "claude" else _minimax_complete)(
                system, "Write the ads now.") or "")
            heads = [l[2:].strip() for l in raw.splitlines() if l.strip()[:2].lower() == "h:"]
            descs = [l[2:].strip() for l in raw.splitlines() if l.strip()[:2].lower() == "d:"]
            if heads and descs:
                return {"headlines": heads, "descriptions": descs}
        except Exception as e:
            print(f"[jobmagnet] {provider} ad copy failed, using template: {e}",
                  file=sys.stderr, flush=True)
    return _ad_copy_demo(business)


# --------------------------------------------------------------------------
# COLD EMAIL  (Phase 5 -- B2B partners only)
# --------------------------------------------------------------------------
def generate_cold_email(business, contact):
    """A short, non-spammy B2B partner outreach email. Returns {'subject','body'}.
    The CAN-SPAM footer (physical address + opt-out) is added by the sender, not here."""
    b = business
    name = (contact.get("name") or "there").split()[0] if contact else "there"
    provider = _active_provider()
    if provider in ("claude", "minimax"):
        system = (
            f"You write brief, respectful B2B partnership outreach emails for "
            f"{b.get('name','a home-services business')}, a {b.get('trade','home services')} "
            f"business serving {b.get('service_area','the local area')}. The recipient is a "
            f"potential referral partner (realtor, property manager, or general contractor), "
            f"NOT a homeowner. WHAT SETS US APART: {b.get('differentiators','')}.\n"
            "Goal: open a referral relationship. Be human and concise (under 120 words), no "
            "hype, no pushy sales language. Do not invent prior contact. No dashes; use periods "
            "and commas. Format EXACTLY as 'SUBJECT: ...' on the first line, then a blank line, "
            "then the email body.")
        try:
            raw = _clean_punct((_claude_complete if provider == "claude" else _minimax_complete)(
                system, f"Write the email to {name}.") or "")
            subj, _, body = raw.partition("\n")
            subj = subj.replace("SUBJECT:", "").strip()
            body = body.strip()
            if subj and body:
                return {"subject": subj, "body": body}
        except Exception as e:
            print(f"[jobmagnet] {provider} cold email failed, using template: {e}",
                  file=sys.stderr, flush=True)
    return {
        "subject": f"Referral partnership with {b.get('name','our team')}?",
        "body": (f"Hi {name},\n\nI run {b.get('name','a local')} {b.get('trade','home services')} "
                 f"business here in {b.get('service_area','the area')}. We do a lot of work with "
                 f"local homeowners and I am always looking for trustworthy partners to refer "
                 f"clients back and forth with.\n\nIf you are open to it, I would love to grab a "
                 f"quick call. Either way, thanks for your time.\n\nBest,\n{b.get('owner_name','') or b.get('name','')}"),
    }
