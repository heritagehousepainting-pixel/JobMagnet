"""Posting guardrails (Phase: scheduling audit).

A scheduled social post should never auto-publish in the middle of the night or stack on
top of another post. This is the content-side sibling of the messaging consent gate: one
place that adjusts a requested publish time to a sane one, honestly, so the scheduler can
stay dumb. Pure + side-effect free (reads existing schedule via db), so it's easy to test.

  safe_schedule_time(business_id, requested_dt) -> (datetime, adjusted_bool, reason)
"""
from datetime import timedelta

import db
from config import QUIET_HOURS_START, QUIET_HOURS_END, POST_MIN_GAP_MIN


def _in_quiet(dt):
    """True if dt falls inside the no-publish window (handles a window that wraps
    midnight, e.g. 21 -> 8)."""
    h = dt.hour
    s, e = QUIET_HOURS_START, QUIET_HOURS_END
    if s == e:
        return False
    if s < e:
        return s <= h < e
    return h >= s or h < e


def _next_open(dt):
    """Move dt forward to the end of quiet hours if it lands inside them, else return it."""
    if not _in_quiet(dt):
        return dt
    end = dt.replace(hour=QUIET_HOURS_END, minute=0, second=0, microsecond=0)
    # If we're in the evening side of a midnight-wrapping window, quiet-end is tomorrow.
    if end <= dt:
        end = end + timedelta(days=1)
    return end


def safe_schedule_time(business_id, requested_dt):
    """Adjust a requested publish time so it is (a) outside quiet hours and (b) at least
    POST_MIN_GAP_MIN away from every other scheduled post for this tenant. Returns the
    safe datetime, whether it changed, and a short human reason."""
    dt = _next_open(requested_dt)
    quiet_shift = dt != requested_dt
    existing = db.scheduled_post_times(business_id)
    gap = timedelta(minutes=POST_MIN_GAP_MIN)
    spacing_shift = False
    for _ in range(200):  # bounded; each pass moves at least one gap forward
        clash = [t for t in existing if abs((dt - t).total_seconds()) < gap.total_seconds()]
        if not clash:
            break
        dt = _next_open(max(clash) + gap)
        spacing_shift = True
    if quiet_shift and spacing_shift:
        reason = "moved out of quiet hours and spaced from your other posts"
    elif quiet_shift:
        reason = "moved out of quiet hours"
    elif spacing_shift:
        reason = "spaced from your other scheduled posts"
    else:
        reason = ""
    return dt, (dt != requested_dt), reason
