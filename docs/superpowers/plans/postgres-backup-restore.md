# Postgres Backup and Restore Drill

JobMagnet runs on a Render-managed Postgres 16 instance (`jobmagnet-db`). This document covers where backups live, how to trigger a manual backup, and the exact steps to restore.

---

## 1. Where automated backups live

In the Render dashboard:

1. Open **Dashboard → PostgreSQL → jobmagnet-db**.
2. Click the **Backups** tab in the left sidebar.
3. Automated daily backups appear here as timestamped snapshots. Retention window depends on your plan (typically 7 days on Basic, longer on higher tiers).

**Tier requirement for PITR (point-in-time recovery):** The `basic-256mb` plan includes daily automated snapshots. Continuous WAL-based PITR (restore to any second in time) requires the **Pro** tier or higher. If you need PITR, upgrade the database plan in the Render dashboard before an incident — you cannot add it retroactively to cover a gap.

---

## 2. How to trigger a manual backup

Render does not expose a one-click "backup now" button for managed Postgres, but you can take a logical dump yourself at any time:

```bash
# Get the internal connection string from the Render dashboard
# (PostgreSQL → jobmagnet-db → Connect → External Database URL)
export PGURL="postgres://..."

pg_dump "$PGURL" \
  --no-owner \
  --no-acl \
  --format=custom \
  --file="jobmagnet-$(date +%Y%m%d-%H%M%S).dump"
```

Store the resulting `.dump` file in a safe location (S3 bucket, encrypted local drive, etc.). This is your point-in-time escape hatch outside Render's retention window.

---

## 3. Restore drill — step by step

Use this procedure whenever you need to recover from data loss or test a backup.

### Step 1: Create a new Postgres instance on Render

1. Dashboard → **New +** → **PostgreSQL**.
2. Name it `jobmagnet-db-restore` (keep it separate from production until verified).
3. Choose the same major version (16) and a plan large enough to hold the data.
4. Wait for status to show **Available**.

### Step 2: Restore from a Render automated snapshot

1. Go to Dashboard → **PostgreSQL → jobmagnet-db → Backups**.
2. Click the three-dot menu on the snapshot you want to restore.
3. Select **Restore** and choose the new instance (`jobmagnet-db-restore`) as the target.
4. Confirm. Render will copy the snapshot into the target instance (this can take several minutes).

If restoring from a manual `pg_dump` file instead:

```bash
export RESTORE_URL="postgres://..."   # External URL of jobmagnet-db-restore

pg_restore "$RESTORE_URL" \
  --no-owner \
  --no-acl \
  --clean \
  --if-exists \
  --dbname="$RESTORE_URL" \
  jobmagnet-20240101-120000.dump
```

### Step 3: Verify row counts

Connect to the restored instance and confirm critical tables look right:

```bash
psql "$RESTORE_URL" <<'SQL'
-- Businesses registered in the system
SELECT COUNT(*) AS business_count FROM businesses;

-- Consent ledger entries (SMS/email opt-in/out audit trail)
SELECT COUNT(*) AS consent_count FROM consent_ledger;

-- Spot-check most recent consents
SELECT business_id, contact_phone, event, created_at
FROM consent_ledger
ORDER BY created_at DESC
LIMIT 10;
SQL
```

Expected: `business_count` and `consent_count` match what you saw on production before the incident. If the numbers are off, try an earlier snapshot.

### Step 4: Repoint DATABASE_URL

Once verified, cut production over to the restored instance:

1. Dashboard → **PostgreSQL → jobmagnet-db-restore → Connect → Internal Database URL**. Copy it.
2. Dashboard → **Web Service → jobmagnet → Environment**.
3. Update `DATABASE_URL` to the new internal URL.
4. Click **Save Changes** — Render redeploys the web service automatically.
5. Smoke-test the live app: log in, check the dashboard, send a test SMS.

### Step 5: Clean up (after confirming production is healthy)

- Delete or suspend `jobmagnet-db-restore` to stop billing on it.
- If the original `jobmagnet-db` was corrupted and you want to reuse that name, delete it and rename the restore instance.

---

## 4. PITR (point-in-time recovery)

Available on Render **Pro tier and above**. When enabled, the Backups tab shows a date/time picker instead of discrete snapshots. Choose any timestamp within the retention window and Render replays WAL segments to restore to that exact moment.

Steps are the same as above except in Step 2 you pick a timestamp rather than a snapshot. Useful for "someone deleted all the leads at 14:23 UTC" style incidents.

---

## 5. Monitoring

Render sends email alerts for failed backups by default. Confirm your account notification email is correct under **Account Settings → Notifications**. Consider also setting a weekly calendar reminder to open the Backups tab and verify the latest snapshot timestamp is less than 25 hours old.
