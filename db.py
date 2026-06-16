"""SQLite storage for JobMagnet. File-based, zero-config.

Multi-tenant: every business (tenant) owns its own content, all scoped by
`business_id`. `users` log in and map to one business. "Client zero" (Heritage
House Painting) is business id 1. Mirrors RingBack's storage conventions so the
two products can later share a library.
"""
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import mandate  # pure decision module (no DB deps) -- canonical playbook/election ids
import getfound  # pure module -- canonical Get Found checklist keys
import speedtolead  # pure module -- canonical lead channel/status ids
import connections  # pure module -- canonical provider ids
import plans  # pure module -- canonical plan ids + capabilities
import crypto  # at-rest credential sealing (stdlib only)
from config import DB_PATH, DEFAULT_BUSINESS

# The Business Brain columns the Content Engine writes from. Order-independent;
# create_business/update_business only touch columns actually provided.
_BUSINESS_COLS = ["name", "trade", "service_area", "owner_name", "brand_voice",
                  "services", "target_customer", "differentiators", "capacity_note",
                  "google_review_link", "faq", "mailing_address"]

# Lifecycle of a generated post. 'scheduled' = approved + a future publish time.
POST_STATUSES = ("draft", "approved", "scheduled", "published", "rejected")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_columns(cursor, table, cols):
    """Add any missing columns to an existing table (simple forward migration).
    `cols` maps column name -> SQL type."""
    have = {r["name"] for r in cursor.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, sqltype in cols.items():
        if name not in have:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sqltype}")


# Shared data-core (trades_core kernel): timestamp + users/auth CRUD + assistant-subsystem
# helpers, byte-identical with RingBack. Inject our connection factory, then re-export the
# names so every existing db.now_iso()/db.get_user()/… call site is unchanged.
import db_core as _core
_core.get_conn = get_conn
from db_core import (now_iso, get_user, get_user_by_email, create_user,  # noqa: E402,F401
                     log_turn, get_convo_turns, flag_counts)


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY,
            name TEXT, trade TEXT, service_area TEXT, owner_name TEXT,
            brand_voice TEXT, services TEXT, target_customer TEXT,
            differentiators TEXT, capacity_note TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            business_id INTEGER NOT NULL, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS content_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            topic TEXT,
            body TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT,
            decided_at TEXT,
            scheduled_for TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_posts_biz_status
            ON content_posts(business_id, status, created_at);

        -- Phase 0: contacts + consent ledger + message log (the outbound spine).
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            name TEXT,
            phone TEXT,
            email TEXT,
            kind TEXT NOT NULL DEFAULT 'customer',   -- customer | partner | lead
            consent_status TEXT NOT NULL DEFAULT 'unknown', -- unknown | granted | opted_out
            notes TEXT,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_contacts_biz ON contacts(business_id, created_at);

        CREATE TABLE IF NOT EXISTS consent_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            contact_id INTEGER,
            channel TEXT,            -- sms | email | voice
            event TEXT NOT NULL,     -- granted | opted_out
            source TEXT,             -- how/where it happened
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            contact_id INTEGER,
            channel TEXT NOT NULL,           -- sms | email
            direction TEXT NOT NULL DEFAULT 'outbound',
            kind TEXT NOT NULL DEFAULT 'marketing',  -- transactional | marketing
            to_addr TEXT,
            body TEXT,
            status TEXT NOT NULL,            -- simulated | sent | blocked_optout | blocked_quiet | blocked_no_consent | error
            provider TEXT,                   -- simulated | twilio | smtp
            purpose TEXT,                    -- e.g. review_request
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_messages_biz ON messages(business_id, created_at);

        -- Phase 1: monitored reviews + drafted responses.
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            contact_id INTEGER,
            source TEXT NOT NULL DEFAULT 'google',   -- google | facebook | other
            author TEXT,
            rating INTEGER,                           -- 1..5
            body TEXT,
            status TEXT NOT NULL DEFAULT 'new',        -- new | responded
            response TEXT,
            created_at TEXT,
            responded_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_reviews_biz ON reviews(business_id, created_at);

        -- Phase 3: conversions (the closed loop) + marketing spend.
        CREATE TABLE IF NOT EXISTS conversions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            channel TEXT NOT NULL,                    -- which marketing channel sourced it
            status TEXT NOT NULL DEFAULT 'won',        -- lead | booked | won | lost
            value REAL NOT NULL DEFAULT 0,             -- job ticket value (won jobs)
            contact_id INTEGER,
            label TEXT,                                -- free note / customer name
            origin TEXT NOT NULL DEFAULT 'manual',     -- manual | ringback | webhook
            created_at TEXT,
            won_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_conv_biz ON conversions(business_id, channel);

        CREATE TABLE IF NOT EXISTS spend (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            channel TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            note TEXT,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_spend_biz ON spend(business_id, channel);

        -- Mason's engine: diagnostic signals (the Walkthrough answers) + the Mandate
        -- (per-playbook election + priority). One signals row per tenant.
        CREATE TABLE IF NOT EXISTS business_signals (
            business_id INTEGER PRIMARY KEY,
            years_in_business REAL, monthly_leads INTEGER, missed_leads INTEGER,
            close_rate REAL, review_count INTEGER, new_jobs_per_month REAL,
            past_customers INTEGER, oldest_job_years REAL, avg_job_value REAL,
            reviewable_backlog INTEGER, gbp_claimed INTEGER, runs_ads INTEGER,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS playbook_elections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            playbook TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            applicability TEXT NOT NULL DEFAULT 'applies',
            recommended TEXT,
            reason TEXT,
            election TEXT,
            updated_at TEXT,
            UNIQUE(business_id, playbook)
        );
        CREATE INDEX IF NOT EXISTS idx_elections_biz ON playbook_elections(business_id, priority);

        -- Get Found engine: which GBP optimization checklist items a tenant has done.
        CREATE TABLE IF NOT EXISTS getfound_checklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT,
            UNIQUE(business_id, item)
        );
        CREATE INDEX IF NOT EXISTS idx_getfound_biz ON getfound_checklist(business_id);

        -- Speed-to-Lead: inbound leads + time-to-first-touch.
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            contact_id INTEGER,
            name TEXT, phone TEXT,
            channel TEXT NOT NULL DEFAULT 'form',     -- call | form | message | referral | other
            topic TEXT,
            status TEXT NOT NULL DEFAULT 'new',         -- new | responded | qualified | booked | lost
            first_response_at TEXT,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_leads_biz ON leads(business_id, created_at);

        -- Connections: a tenant's real account links (Twilio, Google, Meta, ...).
        -- credentials is a JSON blob; status 'connected' means the seams go live.
        CREATE TABLE IF NOT EXISTS connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'connected',
            credentials TEXT,
            connected_at TEXT,
            UNIQUE(business_id, provider)
        );
        CREATE INDEX IF NOT EXISTS idx_connections_biz ON connections(business_id);

        -- Command-center memory: every conversation the owner has with Mason, so we can
        -- replay it, call out the weak spots, and learn from confirmed corrections.
        CREATE TABLE IF NOT EXISTS assistant_convos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            session_key TEXT,
            started_at TEXT,
            last_at TEXT
        );
        CREATE TABLE IF NOT EXISTS assistant_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            convo_id INTEGER NOT NULL,
            business_id INTEGER NOT NULL,
            role TEXT,           -- 'user' | 'assistant'
            content TEXT,
            tool TEXT,           -- which tool ran (or 'chat' / 'route' / NULL)
            status TEXT,         -- ok | pending | capability_gap | chat | empty | error
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS assistant_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            convo_id INTEGER,
            turn_id INTEGER,
            kind TEXT,           -- capability_gap | empty | repeat | negative
            detail TEXT,
            created_at TEXT,
            resolved INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS assistant_learnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            pattern TEXT,        -- normalized phrase the owner said
            action TEXT,         -- a tool name, 'route', or 'answer'
            answer TEXT,         -- canned reply / link target (for 'answer'/'route')
            source_turn_id INTEGER,
            confirmed INTEGER DEFAULT 0,
            uses INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_aturns_convo ON assistant_turns(convo_id);
        CREATE INDEX IF NOT EXISTS idx_aturns_biz ON assistant_turns(business_id);
        CREATE INDEX IF NOT EXISTS idx_aflags_biz ON assistant_flags(business_id);
        CREATE INDEX IF NOT EXISTS idx_alearn_biz ON assistant_learnings(business_id);

        -- Phase 0 autonomy: an audit row for every autopilot run (manual button or cron
        -- heartbeat), so the owner can see what Mason did unattended. Phase 5 reads this.
        CREATE TABLE IF NOT EXISTS autopilot_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            origin TEXT NOT NULL DEFAULT 'manual',   -- manual | cron
            posts INTEGER NOT NULL DEFAULT 0,        -- drafts created this run
            msgs INTEGER NOT NULL DEFAULT 0,         -- messages that actually went out
            capped INTEGER NOT NULL DEFAULT 0,       -- sends paced to a later run
            sms_mode TEXT,                           -- live | simulated (honest at run time)
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_aprun_biz ON autopilot_runs(business_id, created_at);
        """
    )
    # Lightweight migrations so existing DBs gain new columns without a rebuild.
    _ensure_columns(c, "businesses", {"google_review_link": "TEXT", "faq": "TEXT",
                                      "mailing_address": "TEXT"})
    _ensure_columns(c, "contacts", {"suppressed": "INTEGER DEFAULT 0"})  # DNC / do-not-contact
    # Speed-to-Lead: a lead's job ticket value, so a booked/won job carries revenue
    # into the closed-loop ROI (cost-per-booked-job + ROAS), not just a count.
    _ensure_columns(c, "leads", {"value": "REAL DEFAULT 0"})
    # Link a closed-loop conversion back to the lead that produced it, so the single
    # conversion can be promoted booked -> won (with revenue) and never double-counted.
    _ensure_columns(c, "conversions", {"lead_id": "INTEGER"})
    # Phase 4: a provider's stable booking id, so re-syncing RingBack (or any external
    # feed) never double-counts the same booked job. Scoped by (business_id, origin, ext_id).
    _ensure_columns(c, "conversions", {"ext_id": "TEXT"})
    # Reactivation needs each customer's last job date + service to compute repaint cycles.
    _ensure_columns(c, "contacts", {"last_job_at": "TEXT", "last_service": "TEXT"})
    # Subscription plan per tenant (gates autopilot, managed ads, text volume).
    _ensure_columns(c, "businesses", {"plan": "TEXT DEFAULT 'pro'"})
    # Stripe billing linkage.
    _ensure_columns(c, "businesses", {"stripe_customer_id": "TEXT",
                                      "stripe_subscription_id": "TEXT",
                                      "plan_status": "TEXT"})
    # How a published post actually went out (live / assisted / simulated), so the UI
    # can show an honest status instead of badging un-posted copy as "Published".
    _ensure_columns(c, "content_posts", {"publish_mode": "TEXT"})
    # Phase 2 trust dial: when ON, autopilot-generated content for this tenant is
    # auto-scheduled (so the heartbeat publishes it) -- but ONLY on live channels.
    # Default OFF: everything still drafts and waits for approval.
    _ensure_columns(c, "businesses", {"auto_publish": "INTEGER DEFAULT 0"})
    conn.commit()
    # Seed "client zero" (Heritage) so the app is usable on first boot.
    existing = c.execute("SELECT 1 FROM businesses WHERE id=1").fetchone()
    if not existing:
        cols = ["id"] + _BUSINESS_COLS + ["created_at"]
        vals = [1] + [DEFAULT_BUSINESS.get(col, "") for col in _BUSINESS_COLS] + [now_iso()]
        marks = ",".join("?" for _ in cols)
        c.execute(f"INSERT INTO businesses ({','.join(cols)}) VALUES ({marks})", vals)
        conn.commit()
    conn.close()


# ---- Users / auth ----  (create_user / get_user / get_user_by_email are in the
# trades_core db_core kernel; imported + re-exported near the top of this file.)
def count_users():
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return n


def update_user_password(user_id, password_hash):
    conn = get_conn()
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))
    conn.commit()
    conn.close()


# ---- Business Brain ----
def create_business(fields):
    """Create a new tenant business (signup). Returns its id."""
    cols = [col for col in _BUSINESS_COLS if col in fields]
    conn = get_conn()
    collist = ",".join(cols + ["created_at"])
    marks = ",".join("?" for _ in range(len(cols) + 1))
    cur = conn.execute(f"INSERT INTO businesses ({collist}) VALUES ({marks})",
                       tuple(fields[col] for col in cols) + (now_iso(),))
    conn.commit()
    bid = cur.lastrowid
    conn.close()
    return bid


def delete_business(business_id):
    """Remove a tenant row. Used to clean up an orphan business created during a
    signup race (never used on a tenant that has users/posts)."""
    conn = get_conn()
    conn.execute("DELETE FROM businesses WHERE id=?", (business_id,))
    conn.commit()
    conn.close()


def get_business(business_id=1):
    """A tenant's Business Brain, or None if no such tenant exists. (Never
    fabricate DEFAULT_BUSINESS for an unknown id -- that would leak client zero's
    profile to a tenant whose row is missing. Business 1 is always seeded by
    init_db, so the app shell can rely on get_business(1).)"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_business(business_id, fields):
    """Update only the columns actually provided, so an omitted field is never blanked."""
    cols = [col for col in _BUSINESS_COLS if col in fields]
    if not cols:
        return
    conn = get_conn()
    sets = ", ".join(f"{col}=?" for col in cols)
    conn.execute(f"UPDATE businesses SET {sets} WHERE id=?",
                 tuple(fields[col] for col in cols) + (business_id,))
    conn.commit()
    conn.close()


# ---- Content posts ----
def add_post(business_id, platform, topic, body, status="draft"):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO content_posts (business_id, platform, topic, body, status, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (business_id, platform, topic, body, status, now_iso()))
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def get_post(post_id, business_id=None):
    """A single post, optionally scoped to a tenant (so one tenant can't touch
    another's posts)."""
    conn = get_conn()
    if business_id is None:
        row = conn.execute("SELECT * FROM content_posts WHERE id=?", (post_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM content_posts WHERE id=? AND business_id=?",
                           (post_id, business_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_posts(business_id, status=None):
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM content_posts WHERE business_id=? AND status=? "
            "ORDER BY created_at DESC", (business_id, status)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM content_posts WHERE business_id=? ORDER BY created_at DESC",
            (business_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_post_status(post_id, business_id, status):
    """Move a post through its lifecycle. Scoped to the tenant."""
    if status not in POST_STATUSES:
        return False
    conn = get_conn()
    cur = conn.execute(
        "UPDATE content_posts SET status=?, decided_at=? WHERE id=? AND business_id=?",
        (status, now_iso(), post_id, business_id))
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def set_post_published(post_id, business_id, mode):
    """Mark a post published AND record how it went out (live/assisted/simulated), so
    the dashboard can label it honestly. Scoped to the tenant."""
    conn = get_conn()
    conn.execute(
        "UPDATE content_posts SET status='published', publish_mode=?, decided_at=? "
        "WHERE id=? AND business_id=?",
        (mode, now_iso(), post_id, business_id))
    conn.commit()
    conn.close()


def update_post_body(post_id, business_id, body):
    conn = get_conn()
    conn.execute("UPDATE content_posts SET body=? WHERE id=? AND business_id=?",
                 (body, post_id, business_id))
    conn.commit()
    conn.close()


def schedule_post(post_id, business_id, when_iso):
    """Approve a post for a future publish time (status 'scheduled')."""
    conn = get_conn()
    conn.execute("UPDATE content_posts SET status='scheduled', scheduled_for=?, decided_at=? "
                 "WHERE id=? AND business_id=?",
                 (when_iso, now_iso(), post_id, business_id))
    conn.commit()
    conn.close()


def scheduled_post_times(business_id):
    """Parsed datetimes of a tenant's still-scheduled posts -- the posting guardrail
    uses these to keep a new schedule from stacking on an existing one."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT scheduled_for FROM content_posts WHERE business_id=? AND status='scheduled' "
        "AND scheduled_for IS NOT NULL", (business_id,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        try:
            out.append(datetime.fromisoformat(r["scheduled_for"]))
        except (ValueError, TypeError):
            pass
    return out


def due_posts(now_iso_str=None):
    """Scheduled posts whose time has arrived (across all tenants) -- the scheduler
    runner publishes these."""
    cutoff = now_iso_str or now_iso()
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM content_posts WHERE status='scheduled' AND scheduled_for IS NOT NULL "
        "AND scheduled_for <= ? ORDER BY scheduled_for", (cutoff,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def content_stats(business_id):
    """Counts per status for the dashboard tiles."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM content_posts WHERE business_id=? "
        "GROUP BY status", (business_id,)).fetchall()
    conn.close()
    counts = {s: 0 for s in POST_STATUSES}
    for r in rows:
        counts[r["status"]] = r["n"]
    counts["total"] = sum(counts[s] for s in POST_STATUSES)
    return counts


# ---- Contacts ----  (Phase 0)
CONTACT_KINDS = ("customer", "partner", "lead")


def _norm_phone(phone):
    """Loose E.164-ish normalisation so STOP from a number matches the contact."""
    if not phone:
        return ""
    digits = re.sub(r"[^\d+]", "", phone)
    if digits and not digits.startswith("+") and len(digits) == 10:
        digits = "+1" + digits          # assume US if 10 digits, no country code
    elif digits and not digits.startswith("+") and len(digits) == 11 and digits[0] == "1":
        digits = "+" + digits
    return digits


def add_contact(business_id, name="", phone="", email="", kind="customer", notes=""):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO contacts (business_id, name, phone, email, kind, notes, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (business_id, name.strip(), _norm_phone(phone), email.strip().lower(),
         kind if kind in CONTACT_KINDS else "customer", notes.strip(), now_iso()))
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid


def get_contact(contact_id, business_id=None):
    conn = get_conn()
    if business_id is None:
        row = conn.execute("SELECT * FROM contacts WHERE id=?", (contact_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM contacts WHERE id=? AND business_id=?",
                           (contact_id, business_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def find_contact_by_phone(business_id, phone):
    conn = get_conn()
    row = conn.execute("SELECT * FROM contacts WHERE business_id=? AND phone=?",
                       (business_id, _norm_phone(phone))).fetchone()
    conn.close()
    return dict(row) if row else None


def list_contacts(business_id, kind=None):
    conn = get_conn()
    if kind:
        rows = conn.execute("SELECT * FROM contacts WHERE business_id=? AND kind=? "
                            "ORDER BY created_at DESC", (business_id, kind)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM contacts WHERE business_id=? "
                            "ORDER BY created_at DESC", (business_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_contact_suppressed(business_id, contact_id, suppressed=True):
    """Mark a contact do-not-contact (DNC). Blocks every outbound send to them."""
    conn = get_conn()
    conn.execute("UPDATE contacts SET suppressed=? WHERE id=? AND business_id=?",
                 (1 if suppressed else 0, contact_id, business_id))
    conn.commit()
    conn.close()


def set_contact_consent(business_id, contact_id, channel, event, source=""):
    """Record a consent event ('granted'|'opted_out') and reflect it on the contact.
    The ledger is the audit trail; consent_status is the fast-read summary."""
    if event not in ("granted", "opted_out"):
        return False
    conn = get_conn()
    conn.execute(
        "INSERT INTO consent_events (business_id, contact_id, channel, event, source, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (business_id, contact_id, channel, event, source, now_iso()))
    conn.execute("UPDATE contacts SET consent_status=? WHERE id=? AND business_id=?",
                 (event if event == "opted_out" else "granted", contact_id, business_id))
    conn.commit()
    conn.close()
    return True


# ---- Message log ----
def log_message(business_id, channel, to_addr, body, status, provider,
                kind="marketing", purpose="", contact_id=None, direction="outbound"):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO messages (business_id, contact_id, channel, direction, kind, "
        "to_addr, body, status, provider, purpose, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (business_id, contact_id, channel, direction, kind, to_addr, body,
         status, provider, purpose, now_iso()))
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return mid


def list_messages(business_id, limit=100):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM messages WHERE business_id=? "
                        "ORDER BY created_at DESC LIMIT ?", (business_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---- Reviews ----  (Phase 1)
def add_review(business_id, source, author, rating, body, contact_id=None):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO reviews (business_id, contact_id, source, author, rating, body, "
        "status, created_at) VALUES (?,?,?,?,?,?, 'new', ?)",
        (business_id, contact_id, source, author, rating, body, now_iso()))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def get_review(review_id, business_id=None):
    conn = get_conn()
    if business_id is None:
        row = conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM reviews WHERE id=? AND business_id=?",
                           (review_id, business_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_reviews(business_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM reviews WHERE business_id=? ORDER BY created_at DESC",
                        (business_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_review_response(review_id, business_id, response, mark_responded=True):
    """Save a drafted/edited response. Scoped to the tenant."""
    conn = get_conn()
    if mark_responded:
        conn.execute("UPDATE reviews SET response=?, status='responded', responded_at=? "
                     "WHERE id=? AND business_id=?",
                     (response, now_iso(), review_id, business_id))
    else:
        conn.execute("UPDATE reviews SET response=? WHERE id=? AND business_id=?",
                     (response, review_id, business_id))
    conn.commit()
    conn.close()


# ---- Conversions + spend (Phase 3: the closed loop) ----
def add_conversion(business_id, channel, status="won", value=0.0, contact_id=None,
                   label="", origin="manual", lead_id=None, ext_id=None):
    conn = get_conn()
    won_at = now_iso() if status == "won" else None
    # A job's value can't be negative; clamp so a typo can't poison revenue/ROAS.
    value = max(0.0, float(value or 0))
    cur = conn.execute(
        "INSERT INTO conversions (business_id, channel, status, value, contact_id, "
        "label, origin, lead_id, ext_id, created_at, won_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (business_id, channel, status, value, contact_id, label, origin, lead_id,
         ext_id, now_iso(), won_at))
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid


def conversion_exists(business_id, origin, ext_id):
    """True if a conversion with this provider booking id already exists for the tenant
    (the Phase 4 dedup guard, so re-syncing an external feed never double-counts)."""
    if ext_id is None or ext_id == "":
        return False
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM conversions WHERE business_id=? AND origin=? AND ext_id=? LIMIT 1",
        (business_id, origin, str(ext_id))).fetchone()
    conn.close()
    return row is not None


def add_spend(business_id, channel, amount, note=""):
    conn = get_conn()
    conn.execute("INSERT INTO spend (business_id, channel, amount, note, created_at) "
                 "VALUES (?,?,?,?,?)",
                 (business_id, channel, float(amount or 0), note, now_iso()))
    conn.commit()
    conn.close()


def roi_summary(business_id):
    """Per-channel marketing economics: spend, booked jobs, revenue, and the metric
    that matters -- cost per booked job -- plus ROAS. The closed loop no point tool
    can compute, because only JobMagnet sees spend -> booked job."""
    conn = get_conn()
    spend_rows = conn.execute(
        "SELECT channel, COALESCE(SUM(amount),0) AS spend FROM spend "
        "WHERE business_id=? GROUP BY channel", (business_id,)).fetchall()
    conv_rows = conn.execute(
        "SELECT channel, status, COUNT(*) AS n, COALESCE(SUM(value),0) AS revenue "
        "FROM conversions WHERE business_id=? GROUP BY channel, status",
        (business_id,)).fetchall()
    conn.close()

    chans = {}
    def row(ch):
        return chans.setdefault(ch, {"channel": ch, "spend": 0.0, "leads": 0,
                                     "booked": 0, "won": 0, "revenue": 0.0})
    for s in spend_rows:
        row(s["channel"])["spend"] = round(s["spend"], 2)
    for cr in conv_rows:
        r = row(cr["channel"])
        if cr["status"] == "lead":
            r["leads"] += cr["n"]
        if cr["status"] in ("booked", "won"):
            r["booked"] += cr["n"]
            # A booked job is sold work -- its ticket value is revenue. The headline
            # metric is cost per BOOKED job, so booked value drives revenue + ROAS
            # (a separately-logged 'won' is also counted; the StL loop keeps one row
            # per lead so the auto path never double-counts).
            r["revenue"] = round(r["revenue"] + cr["revenue"], 2)
        if cr["status"] == "won":
            r["won"] += cr["n"]

    rows = []
    totals = {"spend": 0.0, "leads": 0, "booked": 0, "won": 0, "revenue": 0.0}
    for r in chans.values():
        r["cost_per_booked"] = round(r["spend"] / r["booked"], 2) if r["booked"] else None
        r["roas"] = round(r["revenue"] / r["spend"], 2) if r["spend"] else None
        for k in totals:
            totals[k] = round(totals[k] + r[k], 2) if isinstance(totals[k], float) else totals[k] + r[k]
        rows.append(r)
    rows.sort(key=lambda x: x["spend"], reverse=True)
    totals["cost_per_booked"] = round(totals["spend"] / totals["booked"], 2) if totals["booked"] else None
    totals["roas"] = round(totals["revenue"] / totals["spend"], 2) if totals["spend"] else None
    return {"rows": rows, "totals": totals}


# ---- Mason's engine: diagnostic signals + the Mandate ----
_SIGNAL_COLS = ["years_in_business", "monthly_leads", "missed_leads", "close_rate",
                "review_count", "new_jobs_per_month", "past_customers",
                "oldest_job_years", "avg_job_value", "reviewable_backlog",
                "gbp_claimed", "runs_ads"]


def save_signals(business_id, signals):
    """Upsert a tenant's diagnostic signals (one row). `signals` is a normalized dict
    (see mandate.normalize_signals); booleans are stored as 0/1."""
    cols = ["business_id"] + _SIGNAL_COLS + ["updated_at"]
    vals = [business_id] + [signals.get(c) for c in _SIGNAL_COLS] + [now_iso()]
    vals = [int(v) if isinstance(v, bool) else v for v in vals]
    marks = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in _SIGNAL_COLS + ["updated_at"])
    conn = get_conn()
    conn.execute(
        f"INSERT INTO business_signals ({','.join(cols)}) VALUES ({marks}) "
        f"ON CONFLICT(business_id) DO UPDATE SET {updates}", vals)
    conn.commit()
    conn.close()


def get_signals(business_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM business_signals WHERE business_id=?",
                       (business_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def save_mandate(business_id, plays):
    """Persist a diagnosis (mandate.diagnose plays) as the tenant's Mandate. Refreshes
    priority/applicability/recommended/reason each run, but PRESERVES the owner's existing
    election on a still-applicable play -- so re-running the Walkthrough never silently
    flips a choice they made. New or no-longer-applicable plays take the recommendation."""
    conn = get_conn()
    for p in plays:
        existing = conn.execute(
            "SELECT election FROM playbook_elections WHERE business_id=? AND playbook=?",
            (business_id, p["key"])).fetchone()
        keep = (existing["election"] if existing and existing["election"]
                and p["applicability"] == "applies" else p["recommended"])
        conn.execute(
            "INSERT INTO playbook_elections "
            "(business_id, playbook, priority, applicability, recommended, reason, "
            "election, updated_at) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(business_id, playbook) DO UPDATE SET "
            "priority=excluded.priority, applicability=excluded.applicability, "
            "recommended=excluded.recommended, reason=excluded.reason, "
            "election=excluded.election, updated_at=excluded.updated_at",
            (business_id, p["key"], p["priority"], p["applicability"], p["recommended"],
             p["reason"], keep, now_iso()))
    conn.commit()
    conn.close()


def has_mandate(business_id):
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM playbook_elections WHERE business_id=?",
                     (business_id,)).fetchone()[0]
    conn.close()
    return n > 0


def get_mandate(business_id):
    """The tenant's Mandate: ranked plays merged with their label/blurb, sorted
    applies-first then by priority."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM playbook_elections WHERE business_id=? ORDER BY priority",
        (business_id,)).fetchall()
    conn.close()
    rank = {"applies": 0, "not_yet": 1, "gated": 2}
    out = []
    for r in rows:
        meta = mandate.PLAYBOOKS.get(r["playbook"], {})
        d = dict(r)
        d["label"] = meta.get("label", r["playbook"])
        d["blurb"] = meta.get("blurb", "")
        out.append(d)
    out.sort(key=lambda d: (rank.get(d["applicability"], 9), d["priority"]))
    return out


def set_election(business_id, playbook, election):
    """Owner sets one playbook's election (take_over | ask_first | off). Scoped to the
    tenant; validates against the known playbooks + elections. Returns True if changed."""
    if playbook not in mandate.PLAYBOOKS or election not in mandate.ELECTIONS:
        return False
    conn = get_conn()
    cur = conn.execute(
        "UPDATE playbook_elections SET election=?, updated_at=? "
        "WHERE business_id=? AND playbook=?",
        (election, now_iso(), business_id, playbook))
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


# ---- Plan (subscription tier) ----
def get_plan(business_id):
    conn = get_conn()
    row = conn.execute("SELECT plan FROM businesses WHERE id=?", (business_id,)).fetchone()
    conn.close()
    return (row["plan"] if row and row["plan"] in plans.PLANS else plans.DEFAULT_PLAN)


def set_plan(business_id, plan):
    if plan not in plans.PLANS:
        return False
    conn = get_conn()
    conn.execute("UPDATE businesses SET plan=? WHERE id=?", (plan, business_id))
    conn.commit()
    conn.close()
    return True


def get_auto_publish(business_id):
    """Phase 2 trust dial: is this tenant opted in to auto-schedule & publish autopilot
    content on its live channels? Default OFF."""
    conn = get_conn()
    row = conn.execute("SELECT auto_publish FROM businesses WHERE id=?",
                       (business_id,)).fetchone()
    conn.close()
    return bool(row and row["auto_publish"])


def set_auto_publish(business_id, on):
    """Set the tenant's auto-publish opt-in (stored 0/1, tenant-scoped)."""
    conn = get_conn()
    conn.execute("UPDATE businesses SET auto_publish=? WHERE id=?",
                 (1 if on else 0, business_id))
    conn.commit()
    conn.close()


def find_business_by_customer(customer_id):
    """Map a Stripe customer back to a tenant (for subscription webhooks)."""
    if not customer_id:
        return None
    conn = get_conn()
    row = conn.execute("SELECT * FROM businesses WHERE stripe_customer_id=?",
                       (customer_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_billing(business_id, customer_id=None, subscription_id=None, plan=None, status=None):
    """Apply a billing update from a Stripe webhook. Only sets the fields provided;
    a valid plan also updates the tier (so capabilities follow the subscription)."""
    sets, vals = [], []
    if customer_id is not None:
        sets.append("stripe_customer_id=?"); vals.append(customer_id)
    if subscription_id is not None:
        sets.append("stripe_subscription_id=?"); vals.append(subscription_id)
    if status is not None:
        sets.append("plan_status=?"); vals.append(status)
    if plan in plans.PLANS:
        sets.append("plan=?"); vals.append(plan)
    if not sets:
        return
    conn = get_conn()
    conn.execute(f"UPDATE businesses SET {', '.join(sets)} WHERE id=?", tuple(vals) + (business_id,))
    conn.commit()
    conn.close()


def messages_this_month(business_id):
    """Outbound SMS actually sent/simulated this calendar month (for plan text caps)."""
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0,
                                               microsecond=0).isoformat()
    return _outbound_sms_since(business_id, start)


def messages_today(business_id):
    """Outbound SMS actually sent/simulated so far today (for the daily pacing cap)."""
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0,
                                               microsecond=0).isoformat()
    return _outbound_sms_since(business_id, start)


def _outbound_sms_since(business_id, start_iso):
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE business_id=? AND channel='sms' "
        "AND direction='outbound' AND status IN ('sent','simulated') AND created_at>=?",
        (business_id, start_iso)).fetchone()[0]
    conn.close()
    return n


# ---- Command-center conversation memory (record / flag / learn) ----
def start_or_get_convo(business_id, session_key):
    """Reuse this browser session's current conversation (if recent) or open a new one,
    so a back-and-forth groups into one replayable thread."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, last_at FROM assistant_convos WHERE business_id=? AND session_key=? "
        "ORDER BY id DESC LIMIT 1", (business_id, session_key or "")).fetchone()
    cid = None
    if row:
        try:
            gap = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(row["last_at"])).total_seconds()
            if gap < 7200:                 # within 2h -> same conversation
                cid = row["id"]
        except (ValueError, TypeError):
            cid = row["id"]
    now = now_iso()
    if cid is None:
        cid = conn.execute(
            "INSERT INTO assistant_convos (business_id, session_key, started_at, last_at) "
            "VALUES (?,?,?,?)", (business_id, session_key or "", now, now)).lastrowid
    else:
        conn.execute("UPDATE assistant_convos SET last_at=? WHERE id=?", (now, cid))
    conn.commit()
    conn.close()
    return cid


def recent_user_turns(convo_id, business_id, limit=6):
    conn = get_conn()
    rows = conn.execute(
        "SELECT content FROM assistant_turns WHERE convo_id=? AND business_id=? AND role='user' "
        "ORDER BY id DESC LIMIT ?", (convo_id, business_id, limit)).fetchall()
    conn.close()
    return [r["content"] for r in rows]


def add_flag(business_id, convo_id, turn_id, kind, detail=""):
    conn = get_conn()
    fid = conn.execute(
        "INSERT INTO assistant_flags (business_id, convo_id, turn_id, kind, detail, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (business_id, convo_id, turn_id, kind, detail, now_iso())).lastrowid
    conn.commit()
    conn.close()
    return fid


def list_convos(business_id, limit=30):
    conn = get_conn()
    rows = conn.execute(
        "SELECT c.id, c.started_at, c.last_at, "
        " (SELECT COUNT(*) FROM assistant_turns t WHERE t.convo_id=c.id) AS turns, "
        " (SELECT COUNT(*) FROM assistant_flags f WHERE f.convo_id=c.id AND f.resolved=0) AS flags "
        "FROM assistant_convos c WHERE c.business_id=? ORDER BY c.id DESC LIMIT ?",
        (business_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_flags(business_id, resolved=0, limit=50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT f.*, t.content AS turn_content FROM assistant_flags f "
        "LEFT JOIN assistant_turns t ON t.id=f.turn_id "
        "WHERE f.business_id=? AND f.resolved=? ORDER BY f.id DESC LIMIT ?",
        (business_id, resolved, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_flag(business_id, flag_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM assistant_flags WHERE id=? AND business_id=?",
                       (flag_id, business_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def resolve_flag(business_id, flag_id):
    conn = get_conn()
    conn.execute("UPDATE assistant_flags SET resolved=1 WHERE id=? AND business_id=?",
                 (flag_id, business_id))
    conn.commit()
    conn.close()


def add_learning(business_id, pattern, action, answer="", source_turn_id=None, confirmed=1):
    conn = get_conn()
    lid = conn.execute(
        "INSERT INTO assistant_learnings (business_id, pattern, action, answer, source_turn_id, "
        "confirmed, created_at) VALUES (?,?,?,?,?,?,?)",
        (business_id, (pattern or "").strip().lower(), action, answer, source_turn_id,
         1 if confirmed else 0, now_iso())).lastrowid
    conn.commit()
    conn.close()
    return lid


def list_learnings(business_id, confirmed_only=True):
    conn = get_conn()
    q = "SELECT * FROM assistant_learnings WHERE business_id=?"
    if confirmed_only:
        q += " AND confirmed=1"
    rows = conn.execute(q + " ORDER BY id DESC", (business_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def bump_learning(business_id, learning_id):
    conn = get_conn()
    conn.execute("UPDATE assistant_learnings SET uses=uses+1 WHERE id=? AND business_id=?",
                 (learning_id, business_id))
    conn.commit()
    conn.close()


def memory_digest(business_id, since_iso):
    """Counts since `since_iso` for the command-center digest: flags by kind, learnings
    added, and conversations touched."""
    conn = get_conn()
    flags = conn.execute(
        "SELECT kind, COUNT(*) AS n FROM assistant_flags WHERE business_id=? AND created_at>=? "
        "GROUP BY kind", (business_id, since_iso)).fetchall()
    learns = conn.execute(
        "SELECT COUNT(*) FROM assistant_learnings WHERE business_id=? AND created_at>=?",
        (business_id, since_iso)).fetchone()[0]
    convs = conn.execute(
        "SELECT COUNT(*) FROM assistant_convos WHERE business_id=? "
        "AND COALESCE(last_at, started_at)>=?", (business_id, since_iso)).fetchone()[0]
    conn.close()
    d = {r["kind"]: r["n"] for r in flags}
    return {"gaps": d.get("capability_gap", 0) + d.get("unhelpful", 0),
            "repeats": d.get("repeat", 0), "negatives": d.get("negative", 0),
            "learnings": learns, "convos": convs}


def unmet_flag_contents(business_id):
    """The owner messages behind every still-open capability-gap / unhelpful flag, so we
    can rank which missing capability recurs the most (what to build next)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT t.content AS c FROM assistant_flags f JOIN assistant_turns t ON t.id=f.turn_id "
        "WHERE f.business_id=? AND f.resolved=0 AND f.kind IN ('capability_gap','unhelpful') "
        "AND t.content IS NOT NULL AND t.content != ''", (business_id,)).fetchall()
    conn.close()
    return [r["c"] for r in rows]


def coach_candidates(business_id):
    """(message, route) for every open capability-gap whose flag recorded the page Mason
    pointed to -- the raw material for a proactive 'want me to remember this' offer."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT t.content AS c, f.detail AS d FROM assistant_flags f "
        "JOIN assistant_turns t ON t.id=f.turn_id "
        "WHERE f.business_id=? AND f.resolved=0 AND f.kind='capability_gap' "
        "AND f.detail LIKE 'route:%' AND t.content IS NOT NULL AND t.content != ''",
        (business_id,)).fetchall()
    conn.close()
    return [(r["c"], r["d"][6:]) for r in rows]   # strip the 'route:' prefix


def convo_user_turn_count(business_id, convo_id):
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM assistant_turns WHERE business_id=? AND convo_id=? "
                     "AND role='user'", (business_id, convo_id)).fetchone()[0]
    conn.close()
    return n


def has_coach_offer(business_id, convo_id):
    """True once Mason has already made a teaching offer in this conversation (so he asks
    at most once per chat)."""
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM assistant_flags WHERE business_id=? AND convo_id=? "
                     "AND kind='coach_offered'", (business_id, convo_id)).fetchone()[0]
    conn.close()
    return n > 0


def mark_coach_offered(business_id, convo_id):
    """Record that an offer was made (resolved=1 so it never shows up as an open issue)."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO assistant_flags (business_id, convo_id, turn_id, kind, detail, "
        "created_at, resolved) VALUES (?,?,?,?,?,?,1)",
        (business_id, convo_id, None, "coach_offered", "", now_iso()))
    conn.commit()
    conn.close()


def all_owner_recipients():
    """(business_id, owner_email) for every tenant -- the weekly-digest cron's mailing list."""
    conn = get_conn()
    rows = conn.execute("SELECT business_id AS bid, email FROM users").fetchall()
    conn.close()
    return [(r["bid"], r["email"]) for r in rows if r["email"]]


def all_business_ids():
    """Every tenant's id -- the autonomy heartbeat (/tasks/tick) iterates these to run
    each tenant's autopilot through the same gated seams a button would."""
    conn = get_conn()
    rows = conn.execute("SELECT id FROM businesses ORDER BY id").fetchall()
    conn.close()
    return [r["id"] for r in rows]


# ---- Autopilot run log (Phase 0: the activity audit trail) ----
def log_autopilot_run(business_id, posts, msgs, capped, sms_mode, origin="manual"):
    """Record one autopilot run so the owner can see what Mason did on his own."""
    conn = get_conn()
    rid = conn.execute(
        "INSERT INTO autopilot_runs (business_id, origin, posts, msgs, capped, sms_mode, "
        "created_at) VALUES (?,?,?,?,?,?,?)",
        (business_id, origin, int(posts), int(msgs), int(capped), sms_mode,
         now_iso())).lastrowid
    conn.commit()
    conn.close()
    return rid


def list_autopilot_runs(business_id, limit=20):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM autopilot_runs WHERE business_id=? ORDER BY id DESC LIMIT ?",
        (business_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def last_autopilot_run(business_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM autopilot_runs WHERE business_id=? ORDER BY id DESC LIMIT 1",
        (business_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ---- Connections (per-tenant real account links) ----
def set_connection(business_id, provider, creds):
    """Save/replace a tenant's connection for a provider. Marks it connected only if
    the credentials are actually complete (else stores as 'disconnected')."""
    if provider not in connections.PROVIDERS:
        return False
    creds = {k: (v or "").strip() for k, v in (creds or {}).items()}
    # Connected only if the required fields are present AND pass a basic format check,
    # so a wrong value (e.g. an email in the Twilio SID field) never shows "Connected".
    valid = connections.is_ready(provider, creds) and not connections.validate(provider, creds)
    status = "connected" if valid else "disconnected"
    # Seal the credential blob at rest (no-op passthrough in dev when no key is set).
    sealed = crypto.encrypt(json.dumps(creds))
    conn = get_conn()
    conn.execute(
        "INSERT INTO connections (business_id, provider, status, credentials, connected_at) "
        "VALUES (?,?,?,?,?) ON CONFLICT(business_id, provider) DO UPDATE SET "
        "status=excluded.status, credentials=excluded.credentials, connected_at=excluded.connected_at",
        (business_id, provider, status, sealed, now_iso()))
    conn.commit()
    conn.close()
    return status == "connected"


def get_connection(business_id, provider):
    """A tenant's live credentials for a provider (dict), or None if not connected."""
    conn = get_conn()
    row = conn.execute(
        "SELECT credentials, status FROM connections WHERE business_id=? AND provider=?",
        (business_id, provider)).fetchone()
    conn.close()
    if not row or row["status"] != "connected":
        return None
    blob = crypto.decrypt(row["credentials"])    # unseal (passthrough for legacy plaintext)
    if blob is None:                              # sealed but unopenable (key missing/rotated)
        return None
    try:
        return json.loads(blob or "{}")
    except (ValueError, TypeError):
        return None


def disconnect(business_id, provider):
    conn = get_conn()
    conn.execute("UPDATE connections SET status='disconnected' WHERE business_id=? AND provider=?",
                 (business_id, provider))
    conn.commit()
    conn.close()


def connection_status(business_id):
    """{provider: True/False connected} for every known provider (for the hub UI)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT provider, status FROM connections WHERE business_id=?", (business_id,)).fetchall()
    conn.close()
    live = {r["provider"] for r in rows if r["status"] == "connected"}
    return {p: (p in live) for p in connections.PROVIDERS}


# ---- Get Found checklist ----
def get_getfound_done(business_id):
    """The set of completed Get Found checklist item keys for a tenant."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT item FROM getfound_checklist WHERE business_id=? AND done=1",
        (business_id,)).fetchall()
    conn.close()
    return {r["item"] for r in rows}


def set_getfound_item(business_id, item, done):
    """Mark one checklist item done/undone. Scoped to the tenant; validates the key
    against the known checklist. Returns True if it was a valid item."""
    if item not in getfound.CHECKLIST_KEYS:
        return False
    conn = get_conn()
    conn.execute(
        "INSERT INTO getfound_checklist (business_id, item, done, updated_at) "
        "VALUES (?,?,?,?) ON CONFLICT(business_id, item) DO UPDATE SET "
        "done=excluded.done, updated_at=excluded.updated_at",
        (business_id, item, 1 if done else 0, now_iso()))
    conn.commit()
    conn.close()
    return True


# ---- Speed-to-Lead: leads + timing ----
def add_lead(business_id, name="", phone="", channel="form", topic="", contact_id=None):
    if channel not in speedtolead.LEAD_CHANNELS:
        channel = "other"
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO leads (business_id, contact_id, name, phone, channel, topic, "
        "status, created_at) VALUES (?,?,?,?,?,?, 'new', ?)",
        (business_id, contact_id, name.strip(), _norm_phone(phone), channel,
         topic.strip(), now_iso()))
    conn.commit()
    lid = cur.lastrowid
    conn.close()
    return lid


def list_leads(business_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM leads WHERE business_id=? ORDER BY created_at DESC",
                        (business_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_lead(lead_id, business_id=None):
    conn = get_conn()
    if business_id is None:
        row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM leads WHERE id=? AND business_id=?",
                           (lead_id, business_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def mark_lead_responded(business_id, lead_id):
    """Stamp the first response (idempotent) and move 'new' -> 'responded'."""
    conn = get_conn()
    conn.execute(
        "UPDATE leads SET first_response_at=COALESCE(first_response_at, ?), "
        "status=CASE WHEN status='new' THEN 'responded' ELSE status END "
        "WHERE id=? AND business_id=?", (now_iso(), lead_id, business_id))
    conn.commit()
    conn.close()


def set_lead_status(business_id, lead_id, status, value=None):
    """Move a lead through its lifecycle. An optional `value` (entered when marking the
    job booked/won) is the ticket value and flows into the closed-loop ROI."""
    if status not in speedtolead.LEAD_STATUSES:
        return False
    conn = get_conn()
    row = conn.execute(
        "SELECT channel, status, name, value FROM leads WHERE id=? AND business_id=?",
        (lead_id, business_id)).fetchone()
    if not row:
        conn.close()
        return False
    if value is not None:
        conn.execute("UPDATE leads SET status=?, value=? WHERE id=? AND business_id=?",
                     (status, max(0.0, float(value or 0)), lead_id, business_id))
    else:
        conn.execute("UPDATE leads SET status=? WHERE id=? AND business_id=?",
                     (status, lead_id, business_id))
    conn.commit()
    conn.close()
    # Closed loop: keep exactly ONE conversion per lead, mirroring its furthest state
    # (booked -> won) and ticket value, so cost-per-booked-job AND revenue/ROAS reflect
    # Speed-to-Lead without ever double-counting.
    if status in ("booked", "won"):
        job_value = max(0.0, float((value if value is not None else row["value"]) or 0))
        channel = "referral" if row["channel"] == "referral" else "other"
        _sync_lead_conversion(business_id, lead_id, channel, status, job_value,
                              row["name"] or "Lead")
    return True


def _sync_lead_conversion(business_id, lead_id, channel, status, value, label):
    """Upsert the single Speed-to-Lead conversion for a lead. First booked/won inserts;
    a later booked -> won promotes the same row (records won_at + revenue), so the loop
    never creates a second conversion."""
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM conversions WHERE business_id=? AND lead_id=? AND origin='speed_to_lead'",
        (business_id, lead_id)).fetchone()
    if existing:
        won_at = now_iso() if status == "won" else None
        conn.execute(
            "UPDATE conversions SET status=?, value=?, channel=?, "
            "won_at=COALESCE(?, won_at) WHERE id=?",
            (status, value, channel, won_at, existing["id"]))
        conn.commit()
        conn.close()
    else:
        conn.close()
        add_conversion(business_id, channel, status=status, value=value,
                       label=label, origin="speed_to_lead", lead_id=lead_id)


def lead_stats(business_id):
    """Counts + average time-to-first-touch (seconds) -- the speed metric."""
    leads = list_leads(business_id)
    responded = [l for l in leads if l["first_response_at"]]
    times = []
    for l in responded:
        try:
            c0 = datetime.fromisoformat(l["created_at"])
            fr = datetime.fromisoformat(l["first_response_at"])
            times.append((fr - c0).total_seconds())
        except (ValueError, TypeError):
            pass
    return {"total": len(leads),
            "awaiting": sum(1 for l in leads if l["status"] == "new"),
            "responded": len(responded),
            "avg_seconds": round(sum(times) / len(times)) if times else None}


# ---- Reactivation: a customer's last job (for repaint-cycle timing) ----
def set_contact_job(business_id, contact_id, last_job_at, last_service):
    conn = get_conn()
    conn.execute("UPDATE contacts SET last_job_at=?, last_service=? "
                 "WHERE id=? AND business_id=?",
                 ((last_job_at or "").strip(), (last_service or "").strip(),
                  contact_id, business_id))
    conn.commit()
    conn.close()


def last_post_at(business_id, platform):
    """Most recent created_at for a tenant's posts on a platform (cadence check), or None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT MAX(created_at) AS last FROM content_posts WHERE business_id=? AND platform=?",
        (business_id, platform)).fetchone()
    conn.close()
    return row["last"] if row else None


def contacted_ids(business_id, purpose):
    """Contacts we ACTUALLY reached for this purpose (so a bulk/autopilot send never
    double-texts the same person). Only 'sent'/'simulated' count: a message blocked by
    quiet hours / opt-out / no-consent, or one that errored, was never delivered, so it
    must not poison the no-repeat guard and permanently skip that contact on later runs."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT contact_id FROM messages WHERE business_id=? AND purpose=? "
        "AND contact_id IS NOT NULL AND status IN ('sent','simulated')",
        (business_id, purpose)).fetchall()
    conn.close()
    return {r["contact_id"] for r in rows}


def requested_contact_ids(business_id):
    """Contacts already sent a review request (so a bulk ask never double-texts)."""
    return contacted_ids(business_id, "review_request")


def review_requested_to_phone(business_id, phone):
    """Whether we've already sent a review request to this phone number (regardless of
    whether it's a saved contact). Lets the won-a-job auto-request dedup so re-marking a
    lead won never double-texts. Only delivered sends count (matches contacted_ids)."""
    norm = _norm_phone(phone)
    if not norm:
        return False
    conn = get_conn()
    rows = conn.execute(
        "SELECT to_addr FROM messages WHERE business_id=? AND purpose='review_request' "
        "AND status IN ('sent','simulated')", (business_id,)).fetchall()
    conn.close()
    return any(_norm_phone(r["to_addr"]) == norm for r in rows)


def get_election(business_id, playbook):
    """A single playbook's current election (take_over | ask_first | off), or None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT election FROM playbook_elections WHERE business_id=? AND playbook=?",
        (business_id, playbook)).fetchone()
    conn.close()
    return row["election"] if row else None


def review_stats(business_id):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    conn = get_conn()
    rows = conn.execute("SELECT rating, status, created_at FROM reviews WHERE business_id=?",
                        (business_id,)).fetchall()
    requested = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE business_id=? AND purpose='review_request'",
        (business_id,)).fetchone()[0]
    conn.close()
    total = len(rows)
    avg = round(sum(r["rating"] for r in rows if r["rating"]) / total, 1) if total else 0
    new = sum(1 for r in rows if r["status"] == "new")
    # Velocity is the real lever: fresh reviews in the last 30 days, not lifetime total.
    velocity_30d = sum(1 for r in rows if (r["created_at"] or "") >= cutoff)
    return {"total": total, "avg": avg, "new": new, "requested": requested,
            "velocity_30d": velocity_30d}
