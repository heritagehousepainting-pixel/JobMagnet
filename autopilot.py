"""Autopilot -- the wire between the Mandate's elections and the engines.

This is what makes "Take it over / Ask me first / Not yet" mean something:
  take_over -> Mason runs the play's safe autonomous action on an autopilot run
  ask_first -> Mason leaves it for you (you act on the engine's page / approval queue)
  off/not_yet -> skipped

Pure planning only (what WOULD run); the route executes the plan through the same
consent-gated seam + approval queue every manual action uses, so autonomy never escapes
the guardrails. Owned/warm actions only -- regulated/cold sends stay gated elsewhere.
"""

# Playbooks that have a safe autonomous action, and the human-readable description.
AUTONOMOUS_ACTIONS = {
    "get_found":    "Draft this week's Google post",
    "show_work":    "Draft a project showcase post",
    "reviews":      "Text review requests to customers not yet asked",
    "reactivation": "Text past customers who are due on their cycle",
    "referrals":    "Ask happy customers for a referral",
}


def plan(elections):
    """elections: {playbook: election}. Returns the autopilot plan -- for each playbook
    with an autonomous action, what Mason will do on a run:
      status 'run' (take_over) | 'ask' (ask_first, left for you) | 'off'."""
    out = []
    for pb, action in AUTONOMOUS_ACTIONS.items():
        el = elections.get(pb) or "off"
        status = "run" if el == "take_over" else ("ask" if el == "ask_first" else "off")
        out.append({"playbook": pb, "action": action, "election": el, "status": status})
    return out


def summary(plan_rows):
    """Counts for the UI: how many plays are on autopilot vs ask-first vs off."""
    return {"run": sum(1 for p in plan_rows if p["status"] == "run"),
            "ask": sum(1 for p in plan_rows if p["status"] == "ask"),
            "off": sum(1 for p in plan_rows if p["status"] == "off")}
