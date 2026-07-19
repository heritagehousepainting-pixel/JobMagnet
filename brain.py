"""brain.py -- the ONE gated path for every LLM call JobMagnet makes.

This is to LLM spend what messaging.py is to SMS: a single seam that every generation
passes through, so cost is capped, honest, and logged in exactly one place. Nothing in
the app should call an LLM provider directly.

Two tiers (config.py explains the routing):
  bulk  -> cheap/high-volume copy (routine posts, assistant routing, the LLM grader)
  brand -> Claude for customer-facing/judgment copy (review replies, FAQ, ads, partner
           emails, assistant chat) where voice + not-fabricating are the product

Honest degradation, every time. generate() returns None -- and the caller falls back to
its built-in template -- when: the tier has no configured provider (demo), the daily
spend cap is reached, or the provider call errors. The app never breaks and never spends
past the cap. Both caps FAIL OPEN: if the ledger read itself errors, the call proceeds
(the cap is a safety net, not a hard dependency).

The actual provider call is isolated in _call_provider() so it is trivially stubbed in
tests -- no network, no keys.
"""
import sys

import config
import db
from llm import strip_think as _strip_think

# Per-model pricing, USD per 1M tokens, prefix-matched against model.lower().
# Claude rates are the current published rates; DeepSeek/MiniMax are directional (verify
# at purchase). Unknown models price at the conservative Sonnet fallback.
_PRICE = [
    # (model-id-prefix, input_per_1m_usd, output_per_1m_usd)
    ("claude-opus",   5.00, 25.00),
    ("claude-sonnet", 3.00, 15.00),
    ("claude-haiku",  1.00,  5.00),
    ("deepseek",      0.28,  1.10),
    ("minimax",       0.30,  1.20),
]
_PRICE_FALLBACK = (3.00, 15.00)   # Sonnet rates -> conservative for an unknown model


def _cost(model, input_tokens, output_tokens):
    """Estimated USD for one call given token counts (first prefix match wins)."""
    ml = (model or "").lower()
    ir, orr = _PRICE_FALLBACK
    for prefix, i, o in _PRICE:
        if prefix in ml:
            ir, orr = i, o
            break
    return round((input_tokens or 0) / 1_000_000 * ir
                 + (output_tokens or 0) / 1_000_000 * orr, 8)


def resolve(tier):
    """Return (provider, model) actually usable right now for this tier, or ('demo', '').
    brand prefers Claude; bulk prefers DeepSeek then MiniMax. Each tier falls back to the
    other real provider before demo, so a single configured key makes the whole product
    real (just not tier-split)."""
    have_claude = bool(config.ANTHROPIC_API_KEY)
    have_deepseek = bool(config.DEEPSEEK_API_KEY)
    have_minimax = bool(config.MINIMAX_API_KEY)

    if tier == "brand":
        if have_claude:
            return ("claude", config.BRAND_MODEL)
        # No Claude -> use whatever bulk provider exists rather than demo.
        if have_deepseek:
            return ("deepseek", config.DEEPSEEK_MODEL)
        if have_minimax:
            return ("minimax", config.MINIMAX_MODEL)
        return ("demo", "")

    # bulk (default)
    if have_deepseek:
        return ("deepseek", config.DEEPSEEK_MODEL)
    if have_minimax:
        return ("minimax", config.MINIMAX_MODEL)
    if have_claude:                       # only Claude configured -> real beats demo
        return ("claude", config.BRAND_MODEL)
    return ("demo", "")


def tiers_status():
    """Honest readout of which brain runs each tier (for a status surface / setup check)."""
    return {"bulk": resolve("bulk")[0], "brand": resolve("brand")[0]}


def _call_provider(provider, model, system, user, *, max_tokens, temperature):
    """Make the real provider call. Returns (text, {input_tokens, output_tokens}).
    Isolated so tests stub it -- this is the only function here that touches the network.
    MiniMax + DeepSeek share the OpenAI-compatible shape; Claude uses the SDK with prompt
    caching on the system block."""
    if provider in ("minimax", "deepseek"):
        import requests  # bundles certifi so TLS verifies cleanly on macOS
        if provider == "deepseek":
            base, key, tok_field, extra = (config.DEEPSEEK_BASE_URL,
                                           config.DEEPSEEK_API_KEY, "max_tokens", {})
        else:
            base, key, tok_field, extra = (config.MINIMAX_BASE_URL,
                                           config.MINIMAX_API_KEY, "max_completion_tokens",
                                           {"thinking": {"type": "disabled"}})
        payload = {"model": model,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}],
                   tok_field: max_tokens, "temperature": temperature, **extra}
        resp = requests.post(f"{base}/v1/chat/completions",
                             headers={"Authorization": f"Bearer {key}",
                                      "Content-Type": "application/json"},
                             json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        text = _strip_think(data["choices"][0]["message"]["content"])
        u = data.get("usage") or {}
        return text, {"input_tokens": u.get("prompt_tokens", 0),
                      "output_tokens": u.get("completion_tokens", 0)}
    if provider == "claude":
        import anthropic  # lazy import so non-Claude paths need no install
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=model, max_tokens=max_tokens,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return text, {"input_tokens": getattr(resp.usage, "input_tokens", 0),
                      "output_tokens": getattr(resp.usage, "output_tokens", 0)}
    return "", {}


def _capped(business_id):
    """True if a real LLM call must be withheld right now. Order:
      cap<=0        -> disabled entirely (demo only)
      platform cost -> at/over the platform daily cap
      tenant cost   -> at/over the per-tenant daily cap (only when business_id known)
    Fails OPEN: any ledger read error returns False (proceed with the call)."""
    if config.LLM_DAILY_COST_CAP_USD <= 0:
        return True
    try:
        if db.llm_cost_today() >= config.LLM_DAILY_COST_CAP_USD:
            print("[jobmagnet] llm platform daily cap reached -> using templates",
                  file=sys.stderr, flush=True)
            return True
        if (business_id is not None and config.LLM_TENANT_DAILY_CAP_USD > 0
                and db.llm_cost_today(business_id) >= config.LLM_TENANT_DAILY_CAP_USD):
            print(f"[jobmagnet] llm tenant daily cap reached (biz {business_id}) "
                  "-> using templates", file=sys.stderr, flush=True)
            return True
    except Exception as e:
        print(f"[jobmagnet] llm cap check error (fail-open): {e}",
              file=sys.stderr, flush=True)
    return False


def generate(tier, system, user, *, max_tokens=600, business_id=None, temperature=0.8):
    """The single entry point. Returns the model's text, or None so the caller falls back
    to a template. None happens on: demo tier (no key), spend cap reached, or any error.
    Logs every successful real call to the cost ledger (logging never breaks the return)."""
    provider, model = resolve(tier)
    if provider == "demo":
        return None
    if _capped(business_id):
        return None
    try:
        text, usage = _call_provider(provider, model, system, user,
                                     max_tokens=max_tokens, temperature=temperature)
    except Exception as e:
        print(f"[jobmagnet] brain {provider}/{tier} call failed, using template: {e}",
              file=sys.stderr, flush=True)
        return None
    try:
        cost = _cost(model, usage.get("input_tokens", 0), usage.get("output_tokens", 0))
        db.log_llm_usage(model, usage.get("input_tokens", 0),
                         usage.get("output_tokens", 0), cost,
                         business_id=business_id, tier=tier, provider=provider)
    except Exception as e:
        print(f"[jobmagnet] llm usage log error: {e}", file=sys.stderr, flush=True)
    return (text or "").strip() or None
