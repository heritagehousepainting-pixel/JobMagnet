# JobMagnet Compliance Reference

This document lists the hard gates and high-conviction guardrails baked into the codebase. It is the reference for any attorney reviewing outbound messaging flows before a cold-outbound module ships.

---

## Type-1 — Hard gates (never bypass)

These are enforced in code and cannot be overridden by configuration alone.

**(a) Quiet hours.** No marketing SMS is sent between `QUIET_HOURS_START` and `QUIET_HOURS_END` (configurable, defaulting to 9 PM–8 AM local). Enforced in `messaging.py:in_quiet_hours()` (lines 69–79). Every outbound SMS call passes through this gate before send.

**(b) Consent check.** Suppressed contacts and opted-out contacts are always blocked from receiving outbound messages. Enforced in `messaging.py:consent_ok()` (lines 104–113). The consent ledger (`contacts_consent` table) is the spine of all outbound — a contact missing explicit opt-in is treated as opted-out.

**(c) Cold outbound disabled by default.** Cold SMS and cold voice require an explicit enable flag and written consent on file before they can fire. Enforced in `messaging.py:send_cold_sms()` and `place_cold_voice()` (lines 208–249). These functions return a simulated/blocked status until the enable flag is set by an operator with attorney sign-off.

**(d) No simulated outcome is ever displayed as live in the UI.** The honest mode/status pattern is enforced throughout: every action that is simulated (i.e. not actually sent or published) is labeled "simulated" in the UI and in all response payloads. No function returns a "success" status for an action that did not happen.

---

## Type-2 — High-conviction only (require rollback plan)

These are not hard-blocked in code but require explicit product sign-off and a documented rollback plan before use.

**(a)** Two touches to the same warm customer within 72 hours in the same campaign run.

**(b)** Urgency copy ("respond by [date]") in review requests sent to past customers.

**(c)** Re-contacting a contact who did not respond to the first touch within the same campaign run, before the next scheduled cadence window.

---

> **Note:** This Type-1 list was drafted referencing existing code gates and must be reviewed by a TCPA attorney before any cold-outbound module ships. See ROADMAP.md — Parked section for the milestone gate that controls when cold-outbound enters the build queue.
