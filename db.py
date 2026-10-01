"""
All SQLite database operations for Controlyx.
DB lives at %APPDATA%/Controlyx/controlyx.db — one per OS user.
"""

import sqlite3
import threading
import time
import os
import hashlib
import shutil
import json as _json
from datetime import datetime, timezone
from utils import app_data_dir, schedules_dir

MAX_CACHED_XML = 20  # oldest cached XML files deleted beyond this


# ── Connection ─────────────────────────────────────────────────────────────

def _db_path():
    """Path to the SQLite DB, migrating the legacy 'p6evm.db' file to the
    branded 'controlyx.db' in place (WAL sidecars moved too). If the rename
    fails, the existing DB is read where it is so no history is lost."""
    d = app_data_dir()
    new = os.path.join(d, 'controlyx.db')
    legacy = os.path.join(d, 'p6evm.db')
    if not os.path.exists(new) and os.path.exists(legacy):
        try:
            os.rename(legacy, new)
        except OSError:
            return legacy
        for suffix in ('-wal', '-shm'):
            try:
                if os.path.exists(legacy + suffix):
                    os.rename(legacy + suffix, new + suffix)
            except OSError:
                pass
    return new

def get_conn(path=None):
    conn = sqlite3.connect(path or _db_path())
    try:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')     # raises on a malformed DB file
        conn.execute('PRAGMA foreign_keys=ON')
    except Exception:
        conn.close()                                # release the file so it can be set aside
        raise
    return conn


# ── Schema ─────────────────────────────────────────────────────────────────

def init_db(path=None):
    with get_conn(path) as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS projects (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                p6_project_id TEXT,
                name          TEXT,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id     INTEGER NOT NULL REFERENCES projects(id),
                imported_at    TEXT NOT NULL,
                data_date      TEXT,
                original_path  TEXT,
                cached_path    TEXT,
                file_hash      TEXT,
                activity_count INTEGER,
                calendar_count INTEGER
            );

            CREATE TABLE IF NOT EXISTS metrics (
                snapshot_id         INTEGER PRIMARY KEY REFERENCES snapshots(id),
                pv                  REAL,
                ev                  REAL,
                ac                  REAL,
                spi                 REAL,
                cpi                 REAL,
                delay_days          INTEGER,
                overall_planned_pct REAL,
                overall_actual_pct  REAL,
                variance            REAL
            );

            CREATE TABLE IF NOT EXISTS category_metrics (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id    INTEGER NOT NULL REFERENCES snapshots(id),
                name           TEXT,
                weight         REAL,
                planned_pct    REAL,
                actual_pct     REAL,
                bac            REAL,
                ac             REAL,
                activity_count INTEGER,
                overridden     INTEGER
            );

            CREATE TABLE IF NOT EXISTS audit_scores (
                snapshot_id          INTEGER PRIMARY KEY REFERENCES snapshots(id),
                overall_score        REAL,
                grade                TEXT,
                categories_evaluated INTEGER,
                categories_total     INTEGER,
                total_review_areas   INTEGER,
                categories_json      TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_findings (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id           INTEGER NOT NULL REFERENCES snapshots(id),
                seq                   INTEGER,
                finding_id            TEXT,
                check_id              TEXT,
                check_name            TEXT,
                category              TEXT,
                severity              TEXT,
                activity_id           TEXT,
                activity_name         TEXT,
                wbs_path              TEXT,
                related_activity_id   TEXT,
                related_activity_name TEXT,
                summary               TEXT,
                basis                 TEXT,
                recommendation        TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_project
                ON snapshots(project_id, imported_at DESC);
            CREATE INDEX IF NOT EXISTS idx_snapshots_hash
                ON snapshots(file_hash);
            CREATE INDEX IF NOT EXISTS idx_category_snapshot
                ON category_metrics(snapshot_id);
            CREATE INDEX IF NOT EXISTS idx_audit_findings_snapshot
                ON audit_findings(snapshot_id);

            CREATE TABLE IF NOT EXISTS audit_modules (
                snapshot_id       INTEGER NOT NULL REFERENCES snapshots(id),
                module            TEXT NOT NULL,
                seq               INTEGER,
                name              TEXT,
                score             REAL,
                grade             TEXT,
                pct               REAL,
                kpis_json         TEXT,
                wbs_summary_json  TEXT,
                findings_json     TEXT,
                mgmt_json         TEXT,
                PRIMARY KEY (snapshot_id, module)
            );
            CREATE INDEX IF NOT EXISTS idx_audit_modules_snapshot
                ON audit_modules(snapshot_id);

            CREATE TABLE IF NOT EXISTS e1_summary (
                snapshot_id INTEGER PRIMARY KEY REFERENCES snapshots(id),
                rows_json   TEXT
            );

            CREATE TABLE IF NOT EXISTS evm_extras (
                snapshot_id INTEGER PRIMARY KEY REFERENCES snapshots(id),
                extras_json TEXT
            );

            CREATE TABLE IF NOT EXISTS snapshot_views (
                snapshot_id INTEGER PRIMARY KEY REFERENCES snapshots(id),
                views_json  TEXT
            );

            CREATE TABLE IF NOT EXISTS calendar_audit (
                snapshot_id INTEGER PRIMARY KEY REFERENCES snapshots(id),
                data_json   TEXT
            );

            CREATE TABLE IF NOT EXISTS project_settings (
                project_id    INTEGER PRIMARY KEY REFERENCES projects(id),
                settings_json TEXT
            );

            -- What the user typed/attached on a screen for ONE imported schedule that is
            -- too big for ui_prefs.json and must survive a restart: the Baseline Narrative
            -- project setup (parties, contract details, logos + layout drawing as images).
            -- Kept out of project_settings so those images never ride along with every
            -- /api/parse and /api/project/load answer.
            CREATE TABLE IF NOT EXISTS snapshot_ui_state (
                snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
                key         TEXT    NOT NULL,
                value_json  TEXT,
                PRIMARY KEY (snapshot_id, key)
            );

            -- Milestone finishes per snapshot, extracted once for the Update-vs-Update
            -- milestone trend (slip chart). A single '__none__' row marks a snapshot as
            -- scanned when it has no milestones, so it is never re-parsed.
            CREATE TABLE IF NOT EXISTS snapshot_milestones (
                snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
                activity_id TEXT NOT NULL,
                name        TEXT,
                task_type   TEXT,
                finish_date TEXT,
                PRIMARY KEY (snapshot_id, activity_id)
            );
        ''')
        # Migrations for databases that predate a column (SQLite ADD COLUMN is cheap
        # and safe). Float's management-dashboard block (`mgmt`) was never persisted,
        # so its PDF/tab could not rebuild on a re-open.
        _audit_cols = {r['name'] for r in conn.execute('PRAGMA table_info(audit_modules)')}
        if 'mgmt_json' not in _audit_cols:
            conn.execute('ALTER TABLE audit_modules ADD COLUMN mgmt_json TEXT')


# ── Startup resilience ─────────────────────────────────────────────────────
# A damaged controlyx.db used to raise out of make_server() before the window existed
# (raw traceback, no app — every launch). Startup now calls open_db_resilient(), which
# never raises: a genuinely corrupt file is set aside as controlyx.db.corrupt-bak-<time>
# (with its -wal/-shm) and a fresh DB is created; a locked or unreadable DB is reported
# as 'degraded' and left untouched. GET /api/health exposes DB_STATUS so the page can
# say what happened instead of silently showing an empty Recent Projects list.

DB_STATUS = {'status': 'unknown', 'detail': None, 'backup': None}

_CORRUPT_CODES = ('SQLITE_CORRUPT', 'SQLITE_NOTADB')
_CORRUPT_TEXT = ('file is not a database', 'database disk image is malformed',
                 'malformed database schema')


def _is_corruption(exc):
    """True only for 'the file is damaged' errors — never for locked / busy / cannot-open
    (those must not cause a quarantine)."""
    name = getattr(exc, 'sqlite_errorname', '') or ''
    if any(name.startswith(c) for c in _CORRUPT_CODES):
        return True
    msg = str(exc).lower()
    return any(t in msg for t in _CORRUPT_TEXT)


def _quick_check_ok(path):
    """PRAGMA quick_check on a separate connection: True / False, None if it can't run."""
    try:
        conn = sqlite3.connect(path, timeout=5)
        try:
            rows = conn.execute('PRAGMA quick_check').fetchall()
        finally:
            conn.close()
        return bool(rows) and rows[0][0] == 'ok'
    except sqlite3.DatabaseError as exc:
        return False if _is_corruption(exc) else None
    except Exception:
        return None


def _quarantine_db(path):
    """Rename a damaged DB (and its WAL/SHM sidecars) out of the way. Returns the backup
    file name, or None when the main file could not be moved (e.g. held open by another
    running copy of the app)."""
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = f'{path}.corrupt-bak-{stamp}'
    try:
        os.replace(path, backup)
    except OSError:
        return None
    for suffix in ('-wal', '-shm'):
        try:
            if os.path.exists(path + suffix):
                os.replace(path + suffix, backup + suffix)
        except OSError:
            pass
    return os.path.basename(backup)


def open_db_resilient():
    """Create/upgrade the schema without ever raising. Returns a copy of DB_STATUS:
    status 'ok' | 'recovered' (damaged file set aside, fresh DB) | 'degraded'.
    (A file whose data pages are damaged opens 'ok'; start_background_check finds it.)"""
    _OPEN_GEN[0] += 1
    DB_STATUS.pop('check', None)
    DB_STATUS.pop('salvaged', None)
    try:
        init_db()
        DB_STATUS.update(status='ok', detail=None, backup=None)
        return dict(DB_STATUS)
    except sqlite3.DatabaseError as exc:
        # Keep only the text: the traceback pins init_db's frame and its open connection,
        # and Windows cannot rename a file that is still open.
        first, first_corrupt = str(exc), _is_corruption(exc)
    except Exception as exc:                            # e.g. the folder is not writable
        DB_STATUS.update(status='degraded', detail=f'{type(exc).__name__}: {exc}', backup=None)
        return dict(DB_STATUS)
    import gc
    gc.collect()                                        # close the failed connection now

    try:
        path = _db_path()
    except Exception:
        DB_STATUS.update(status='degraded', detail=first, backup=None)
        return dict(DB_STATUS)
    damaged = first_corrupt or (_quick_check_ok(path) is False)
    if not damaged:                                     # locked / busy / cannot open
        DB_STATUS.update(status='degraded', detail=first, backup=None)
        return dict(DB_STATUS)
    backup = _quarantine_db(path)
    if not backup:
        DB_STATUS.update(status='degraded', backup=None,
                         detail=f'{first} (the damaged file could not be moved aside)')
        return dict(DB_STATUS)
    try:
        init_db()
        DB_STATUS.update(status='recovered', detail=first, backup=backup)
    except Exception as exc:
        DB_STATUS.update(status='degraded', detail=f'{first}; fresh DB failed: {exc}',
                         backup=backup)
    return dict(DB_STATUS)


# ── Damage found AFTER start-up (S3) ───────────────────────────────────────
# CREATE TABLE IF NOT EXISTS only reads the schema pages, so a file whose DATA pages are
# damaged (the common case) opened as 'ok' and then every read of those rows failed with
# "database disk image is malformed" — Recent Projects kept failing with no way out.
# Now: (1) PRAGMA quick_check runs on a background thread once the server is listening
# (never before the first paint); (2) any request that meets a corruption error marks the
# DB 'damaged' (server._json notes it); (3) the page offers "set the damaged database aside
# and start fresh" — POST /api/db/recover -> recover_damaged_db(), which copies every row
# that can still be read into a new file and keeps the damaged one as .corrupt-bak-<time>.

_DAMAGE_LOCK = threading.Lock()
BACKGROUND_CHECK_DELAY_S = 2.0      # after the server listens: the window paints first
_OPEN_GEN = [0]                     # bumped by open_db_resilient: a check started for an
                                    # earlier open never reports on a newer one


def mark_damaged(detail):
    """Record that the history database is damaged (status 'damaged'). Returns True when
    the status changed."""
    text = str(detail or 'database disk image is malformed')
    with _DAMAGE_LOCK:
        if DB_STATUS.get('status') == 'damaged':
            return False
        DB_STATUS.update(status='damaged', detail=text, backup=None)
    return True


def note_error(err):
    """Mark the DB damaged when ``err`` (an exception or its text) is a corruption error;
    locked / busy / any other error is ignored. Returns True when it was corruption."""
    if err is None:
        return False
    if isinstance(err, BaseException):
        bad = _is_corruption(err)
    else:
        bad = any(t in str(err).lower() for t in _CORRUPT_TEXT)
    if bad:
        mark_damaged(str(err))
    return bad


def integrity_check(path=None, gen=None):
    """PRAGMA quick_check on its own connection. Returns (ok, detail): ok True, False
    (damaged — recorded in DB_STATUS) or None (could not run: locked, missing ...).
    ``gen``: the open this check was started for (a stale check reports nothing)."""
    if gen is not None and gen != _OPEN_GEN[0]:
        return None, 'stale check'
    DB_STATUS['check'] = 'running'
    try:
        path = path or _db_path()
        if not os.path.exists(path):
            return None, None
        conn = sqlite3.connect(path, timeout=5)
        try:
            rows = [r[0] for r in conn.execute('PRAGMA quick_check(20)').fetchall()]
        finally:
            conn.close()
        if rows and rows[0] == 'ok':
            return True, None
        detail = ('database disk image is malformed (' +
                  '; '.join(str(r) for r in rows[:3]) + ')')
        mark_damaged(detail)
        return False, detail
    except sqlite3.DatabaseError as exc:
        if _is_corruption(exc):
            mark_damaged(str(exc))
            return False, str(exc)
        return None, str(exc)
    except Exception as exc:
        return None, str(exc)
    finally:
        DB_STATUS['check'] = 'done'


def start_background_check(delay_s=None):
    """Run integrity_check() on a daemon thread after ``delay_s`` (default
    BACKGROUND_CHECK_DELAY_S; the window paints first) on the DB file open NOW.
    GET /api/health shows db.check: 'pending' -> 'running' -> 'done'."""
    DB_STATUS['check'] = 'pending'
    path, gen = _db_path(), _OPEN_GEN[0]
    delay_s = BACKGROUND_CHECK_DELAY_S if delay_s is None else delay_s

    def run():
        time.sleep(max(0.0, delay_s))
        if gen != _OPEN_GEN[0]:
            return
        integrity_check(path, gen)
    t = threading.Thread(target=run, name='db-quick-check', daemon=True)
    t.start()
    return t


def _salvage_rows(src, table, max_jumps=24):
    """Every row of ``table`` that can still be read, in rowid order, as
    (column names, rows). When a damaged page stops the scan, jump past it (growing steps)
    and carry on; gives up after ``max_jumps`` failed jumps."""
    q = 'SELECT rowid, * FROM "%s"' % table.replace('"', '""')
    rows, names, last, step, jumps = [], None, None, 1, 0
    while True:
        try:
            if last is None:
                cur = src.execute(q + ' ORDER BY rowid')
            else:
                cur = src.execute(q + ' WHERE rowid > ? ORDER BY rowid', (last,))
            names = [d[0] for d in cur.description]
            for r in cur:
                rows.append(tuple(r))
                last = r[0]
                step = 1
            return names, rows
        except sqlite3.DatabaseError:
            jumps += 1
            if jumps > max_jumps:
                return names, rows
            last = (last if last is not None else 0) + step
            step *= 2


def _copy_readable_rows(path, dst):
    """Copy every readable row of every table of the damaged file at ``path`` into ``dst``
    (a fresh schema). Returns ({table: rows copied}, [tables that could not be read])."""
    salvaged, lost = {}, []
    try:
        src = sqlite3.connect('file:%s?mode=ro' % os.path.abspath(path).replace(os.sep, '/'),
                              uri=True, timeout=5)
    except sqlite3.Error:
        return salvaged, lost
    try:
        tables = [r[0] for r in dst.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY rowid")]
        for t in tables:
            cols = [r[1] for r in dst.execute('PRAGMA table_info("%s")' % t)]
            try:
                have = {r[1] for r in src.execute('PRAGMA table_info("%s")' % t)}
            except sqlite3.DatabaseError:
                lost.append(t)
                continue
            use = [c for c in cols if c in have]
            if not use:
                continue
            names, rows = _salvage_rows(src, t)
            if names is None and not rows:
                lost.append(t)
                continue
            idx = [names.index(c) for c in use] if names else []
            sql = 'INSERT OR IGNORE INTO "%s" (%s) VALUES (%s)' % (
                t, ', '.join('"%s"' % c for c in use), ', '.join('?' * len(use)))
            n = 0
            for r in rows:
                try:
                    n += dst.execute(sql, [r[i] for i in idx]).rowcount or 0
                except sqlite3.Error:
                    pass
            salvaged[t] = n
    finally:
        src.close()
    return salvaged, lost


def recover_damaged_db(retries=10):
    """Set the damaged history database aside and start a fresh one, copying across every
    row that can still be read. Returns {'ok', 'backup', 'salvaged': {table: n},
    'lost_tables': [...]} or {'ok': False, 'error'}; DB_STATUS becomes 'recovered'."""
    import gc
    with _DAMAGE_LOCK:
        path = _db_path()
        tmp = '%s.rebuild-%s' % (path, datetime.now().strftime('%Y%m%d-%H%M%S'))
        salvaged, lost = {}, []
        try:
            init_db(tmp)                                # the fresh schema, in a side file
            gc.collect()
            dst = sqlite3.connect(tmp)
            try:
                dst.execute('PRAGMA foreign_keys=OFF')
                if os.path.exists(path):
                    salvaged, lost = _copy_readable_rows(path, dst)
                dst.commit()
                dst.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            finally:
                dst.close()
            gc.collect()                                # release every handle on the file
            backup = None
            if os.path.exists(path):
                for _ in range(max(1, retries)):
                    backup = _quarantine_db(path)
                    if backup:
                        break
                    gc.collect()
                    time.sleep(0.2)
                if not backup:
                    raise OSError('the damaged file could not be moved aside '
                                  '(is another copy of the app still open?)')
            os.replace(tmp, path)
            for suffix in ('-wal', '-shm'):
                try:
                    if os.path.exists(tmp + suffix):
                        os.replace(tmp + suffix, path + suffix)
                except OSError:
                    pass
            DB_STATUS.update(status='recovered', backup=backup, salvaged=salvaged,
                             detail=DB_STATUS.get('detail'))
            return {'ok': True, 'backup': backup, 'salvaged': salvaged, 'lost_tables': lost}
        except Exception as exc:
            for f in (tmp, tmp + '-wal', tmp + '-shm'):
                try:
                    if os.path.exists(f):
                        os.remove(f)
                except OSError:
                    pass
            return {'ok': False, 'error': '%s: %s' % (type(exc).__name__, exc),
                    'salvaged': salvaged}


# ── File helpers ───────────────────────────────────────────────────────────

def hash_file(path):
    """SHA256 of file content — used for dedup."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def cache_xml(xml_path, file_hash):
    """
    Copy xml_path into schedules_dir if not already there.
    Returns the cached path (existing or newly created).
    """
    with get_conn() as conn:
        row = conn.execute(
            'SELECT cached_path FROM snapshots WHERE file_hash = ? AND cached_path IS NOT NULL LIMIT 1',
            (file_hash,)
        ).fetchone()
    if row and os.path.exists(row['cached_path']):
        return row['cached_path']  # already cached, reuse

    filename = f"{file_hash[:12]}_{os.path.basename(xml_path)}"
    dest = os.path.join(schedules_dir(), filename)
    shutil.copy2(xml_path, dest)
    # copy2 keeps the source's modified time — a baseline exported months ago would be the
    # OLDEST cached file and deleted by the cleanup below in this very call. The cache is ordered
    # by when a file was cached, so stamp the copy now.
    try:
        os.utime(dest, None)
    except OSError:
        pass
    _cleanup_old_xml_files()
    return dest


def _attached_baseline_paths():
    """Every file recorded as a snapshot's attached baseline (evm_extras) — never evicted."""
    out = set()
    try:
        with get_conn() as conn:
            rows = conn.execute("SELECT extras_json FROM evm_extras "
                                "WHERE extras_json LIKE '%baseline_%'").fetchall()
    except Exception:
        return out
    for row in rows:
        try:
            extras = _json.loads(row['extras_json'] or '{}')
        except ValueError:
            continue
        for key in ('baseline_path', 'baseline_original'):
            if extras.get(key):
                out.add(os.path.normcase(os.path.abspath(extras[key])))
    return out


def _cleanup_old_xml_files():
    """Keep only the MAX_CACHED_XML most recently modified XML files. A file attached as a
    snapshot's baseline is kept regardless (and does not count toward the cap) — it is
    'remembered for this update and used by every feature', so it must not disappear."""
    sdir = schedules_dir()
    keep = _attached_baseline_paths()
    files = sorted(
        [p for p in (os.path.join(sdir, f) for f in os.listdir(sdir) if f.endswith('.xml'))
         if os.path.normcase(os.path.abspath(p)) not in keep],
        key=os.path.getmtime
    )
    for old in files[:-MAX_CACHED_XML]:
        try:
            os.remove(old)
        except OSError:
            pass


# ── Project upsert ─────────────────────────────────────────────────────────

def upsert_project(p6_project_id, name):
    """Return existing project id or insert a new one."""
    with get_conn() as conn:
        # match on p6_project_id if present, else on name
        if p6_project_id:
            row = conn.execute(
                'SELECT id FROM projects WHERE p6_project_id = ?', (p6_project_id,)
            ).fetchone()
        else:
            row = conn.execute(
                'SELECT id FROM projects WHERE name = ? AND (p6_project_id IS NULL OR p6_project_id = "")',
                (name,)
            ).fetchone()

        if row:
            return row['id']

        cur = conn.execute(
            'INSERT INTO projects (p6_project_id, name, created_at) VALUES (?, ?, ?)',
            (p6_project_id or '', name or '', _now())
        )
        return cur.lastrowid


# ── Snapshot + metrics insert ──────────────────────────────────────────────

def insert_snapshot(project_id, data_date, original_path, cached_path,
                    file_hash, activity_count, calendar_count):
    with get_conn() as conn:
        cur = conn.execute(
            '''INSERT INTO snapshots
               (project_id, imported_at, data_date, original_path, cached_path,
                file_hash, activity_count, calendar_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (project_id, _now(), str(data_date) if data_date else None,
             original_path, cached_path, file_hash, activity_count, calendar_count)
        )
        return cur.lastrowid

def insert_metrics(snapshot_id, result):
    with get_conn() as conn:
        conn.execute(
            '''INSERT INTO metrics
               (snapshot_id, pv, ev, ac, spi, cpi, delay_days,
                overall_planned_pct, overall_actual_pct, variance)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (snapshot_id,
             result.get('pv'), result.get('ev'), result.get('ac'),
             result.get('spi'), result.get('cpi'), result.get('delay_days'),
             result.get('overall_planned_pct'), result.get('overall_actual_pct'),
             result.get('variance'))
        )

def insert_category_metrics(snapshot_id, categories):
    rows = []
    for name, cat in (categories or {}).items():
        rows.append((
            snapshot_id, name,
            cat.get('weight'), cat.get('planned_pct'), cat.get('actual_pct'),
            cat.get('bac'), cat.get('ac'), cat.get('activity_count'),
            1 if cat.get('overridden') else 0
        ))
    if not rows:
        return
    with get_conn() as conn:
        conn.executemany(
            '''INSERT INTO category_metrics
               (snapshot_id, name, weight, planned_pct, actual_pct, bac, ac,
                activity_count, overridden)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            rows
        )


# ── Audit persistence ──────────────────────────────────────────────────────

def insert_audit(snapshot_id, audit_result, total_review_areas):
    """Store one audit run (scores + findings) for a snapshot."""
    scores = audit_result.get('scores', {})
    overall = scores.get('overall', {})
    categories = scores.get('categories', {})
    findings = audit_result.get('findings', [])
    with get_conn() as conn:
        conn.execute(
            '''INSERT OR REPLACE INTO audit_scores
               (snapshot_id, overall_score, grade, categories_evaluated,
                categories_total, total_review_areas, categories_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (snapshot_id, overall.get('score'), overall.get('grade'),
             overall.get('categories_evaluated'), overall.get('categories_total'),
             total_review_areas, _json.dumps(categories))
        )
        rows = []
        for seq, f in enumerate(findings):
            rows.append((
                snapshot_id, seq, f.get('finding_id'), f.get('check_id'),
                f.get('check_name'), f.get('category'), f.get('severity'),
                f.get('activity_id'), f.get('activity_name'), f.get('wbs_path'),
                f.get('related_activity_id'), f.get('related_activity_name'),
                f.get('summary'), f.get('basis'), f.get('recommendation'),
            ))
        if rows:
            conn.executemany(
                '''INSERT INTO audit_findings
                   (snapshot_id, seq, finding_id, check_id, check_name, category,
                    severity, activity_id, activity_name, wbs_path,
                    related_activity_id, related_activity_name, summary, basis, recommendation)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                rows
            )


def get_latest_snapshot_id(project_id):
    with get_conn() as conn:
        row = conn.execute(
            'SELECT id FROM snapshots WHERE project_id = ? ORDER BY imported_at DESC, id DESC LIMIT 1',
            (project_id,)
        ).fetchone()
    return row['id'] if row else None


def get_audit_for_snapshot(snapshot_id):
    """Reconstruct the {findings, scores, counts, total_review_areas} shape the
    UI/engine use, from stored rows. Returns None if no audit was stored."""
    with get_conn() as conn:
        score_row = conn.execute(
            'SELECT * FROM audit_scores WHERE snapshot_id = ?', (snapshot_id,)
        ).fetchone()
        if not score_row:
            return None
        frows = conn.execute(
            'SELECT * FROM audit_findings WHERE snapshot_id = ? ORDER BY seq ASC',
            (snapshot_id,)
        ).fetchall()

    findings = []
    by_severity = {}
    for r in frows:
        findings.append({
            'finding_id': r['finding_id'], 'check_id': r['check_id'],
            'check_name': r['check_name'], 'category': r['category'],
            'severity': r['severity'], 'activity_id': r['activity_id'],
            'activity_name': r['activity_name'], 'wbs_path': r['wbs_path'],
            'related_activity_id': r['related_activity_id'],
            'related_activity_name': r['related_activity_name'],
            'summary': r['summary'], 'basis': r['basis'],
            'recommendation': r['recommendation'], 'confidence': None,
        })
        by_severity[r['severity']] = by_severity.get(r['severity'], 0) + 1

    return {
        'findings': findings,
        'scores': {
            'categories': _json.loads(score_row['categories_json'] or '{}'),
            'overall': {
                'score': score_row['overall_score'],
                'grade': score_row['grade'],
                'categories_evaluated': score_row['categories_evaluated'],
                'categories_total': score_row['categories_total'],
            },
        },
        'counts': {'total': len(findings), 'by_severity': by_severity},
        'total_review_areas': score_row['total_review_areas'],
    }


# ── V2 isolated module persistence ─────────────────────────────────────────

def insert_audit_modules(snapshot_id, modules_result):
    """Store each isolated module report (JSON) for a snapshot."""
    order = modules_result.get('module_order', [])
    modules = modules_result.get('modules', {})
    rows = []
    for seq, key in enumerate(order):
        m = modules.get(key, {})
        rows.append((
            snapshot_id, key, seq, m.get('name'),
            m.get('score'), m.get('grade'), m.get('pct'),
            _json.dumps(m.get('kpis', {})),
            _json.dumps(m.get('wbs_summary', [])),
            _json.dumps(m.get('findings', [])),
            _json.dumps(m['mgmt']) if m.get('mgmt') is not None else None,
        ))
    if not rows:
        return
    with get_conn() as conn:
        conn.executemany(
            '''INSERT OR REPLACE INTO audit_modules
               (snapshot_id, module, seq, name, score, grade, pct,
                kpis_json, wbs_summary_json, findings_json, mgmt_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            rows
        )


def save_e1_summary(snapshot_id, eng_rows):
    with get_conn() as conn:
        conn.execute('INSERT OR REPLACE INTO e1_summary (snapshot_id, rows_json) VALUES (?, ?)',
                     (snapshot_id, _json.dumps(eng_rows)))


def get_e1_summary(snapshot_id):
    with get_conn() as conn:
        row = conn.execute('SELECT rows_json FROM e1_summary WHERE snapshot_id = ?',
                           (snapshot_id,)).fetchone()
    return _json.loads(row['rows_json']) if row and row['rows_json'] else None


def save_evm_extras(snapshot_id, extras):
    with get_conn() as conn:
        # Keep the attached baseline's ORIGINAL path (save_baseline) with it: a recompute or a
        # re-import of the same file re-saves extras with only the (resolved) baseline path.
        bl = extras.get('baseline_path')
        if bl and 'baseline_original' not in extras:
            for row in conn.execute("SELECT extras_json FROM evm_extras "
                                    "WHERE extras_json LIKE '%baseline_original%' "
                                    "ORDER BY (snapshot_id = ?) DESC, snapshot_id DESC",
                                    (snapshot_id,)).fetchall():
                try:
                    old = _json.loads(row['extras_json'] or '{}')
                except ValueError:
                    continue
                if old.get('baseline_original') and bl in (old.get('baseline_path'),
                                                           old['baseline_original']):
                    extras = dict(extras, baseline_path=old.get('baseline_path') or bl,
                                  baseline_original=old['baseline_original'])
                    break
        conn.execute('INSERT OR REPLACE INTO evm_extras (snapshot_id, extras_json) VALUES (?, ?)',
                     (snapshot_id, _json.dumps(extras, default=str)))


def save_snapshot_views(snapshot_id, views):
    """Store the view-only projections of a snapshot — the Schedule (Gantt) activity rows and
    the WBS summary tree — so a re-opened project shows them without re-parsing its file."""
    with get_conn() as conn:
        conn.execute('INSERT OR REPLACE INTO snapshot_views (snapshot_id, views_json) VALUES (?, ?)',
                     (snapshot_id, _json.dumps(views, default=str)))


def get_snapshot_views(snapshot_id):
    """→ {'activities', 'wbs_summary', 'wbs_main'} or None when nothing was stored."""
    with get_conn() as conn:
        row = conn.execute('SELECT views_json FROM snapshot_views WHERE snapshot_id = ?',
                           (snapshot_id,)).fetchone()
    return _json.loads(row['views_json']) if row and row['views_json'] else None


def get_evm_extras(snapshot_id):
    with get_conn() as conn:
        row = conn.execute('SELECT extras_json FROM evm_extras WHERE snapshot_id = ?',
                           (snapshot_id,)).fetchone()
    return _json.loads(row['extras_json']) if row and row['extras_json'] else None


def save_baseline(snapshot_id, baseline_path, original_path=None):
    """Remember the attached baseline for this snapshot (merged into evm_extras): its cached
    copy (``baseline_path``, content-exact) and the file the planner picked (``original_path``)
    as a fallback should the copy ever be missing. ``None`` forgets both."""
    with get_conn() as conn:
        row = conn.execute('SELECT extras_json FROM evm_extras WHERE snapshot_id = ?',
                           (snapshot_id,)).fetchone()
        extras = _json.loads(row['extras_json']) if row and row['extras_json'] else {}
        extras['baseline_path'] = baseline_path
        if baseline_path and original_path:
            extras['baseline_original'] = original_path
        else:
            extras.pop('baseline_original', None)
        conn.execute('INSERT OR REPLACE INTO evm_extras (snapshot_id, extras_json) VALUES (?, ?)',
                     (snapshot_id, _json.dumps(extras, default=str)))


def get_attached_baseline(snapshot_id=None, paths=()):
    """The baseline file attached for a snapshot (``evm_extras.baseline_path``) — by snapshot id
    when given, else for the LATEST snapshot of that file (matched by cached or original path;
    the cached path is content-specific). None when nothing is attached. Used by every feature
    that needs a baseline (p6_evm.baseline.load_for_project), so an attachment applies everywhere."""
    with get_conn() as conn:
        sid = None
        if snapshot_id:
            row = conn.execute('SELECT id FROM snapshots WHERE id = ?', (snapshot_id,)).fetchone()
            sid = row['id'] if row else None
        if sid is None:
            for p in paths or ():
                if not p:
                    continue
                row = conn.execute(
                    'SELECT id FROM snapshots WHERE cached_path = ? OR original_path = ? '
                    'ORDER BY id DESC LIMIT 1', (p, p)).fetchone()
                if row:
                    sid = row['id']
                    break
        if sid is None:
            return None
        row = conn.execute('SELECT extras_json FROM evm_extras WHERE snapshot_id = ?',
                           (sid,)).fetchone()
    extras = _json.loads(row['extras_json']) if row and row['extras_json'] else {}
    cached, original = extras.get('baseline_path'), extras.get('baseline_original')
    if cached and not os.path.isfile(cached) and original and os.path.isfile(original):
        return original            # the cached copy is gone — the file the planner picked
    return cached or None


def get_prior_baseline_for_hash(file_hash):
    """The baseline attached to the most recent earlier import of the SAME file (same SHA-256),
    so re-importing an update keeps its attached baseline. None when there is none."""
    with get_conn() as conn:
        row = conn.execute('SELECT id FROM snapshots WHERE file_hash = ? ORDER BY id DESC LIMIT 1',
                           (file_hash,)).fetchone()
    return get_attached_baseline(snapshot_id=row['id']) if row else None


def clear_snapshot_results(snapshot_id):
    """Drop a snapshot's computed rows (metrics / categories / audit modules) so it can be
    recomputed IN PLACE — used when a baseline is attached or removed, so the snapshot keeps
    its place in the history instead of a duplicate import being added."""
    with get_conn() as conn:
        for table in ('metrics', 'category_metrics', 'audit_modules'):
            conn.execute(f'DELETE FROM {table} WHERE snapshot_id = ?', (snapshot_id,))


def snapshot_exists(snapshot_id):
    with get_conn() as conn:
        return conn.execute('SELECT 1 FROM snapshots WHERE id = ?', (snapshot_id,)).fetchone() is not None


def get_snapshot_source(snapshot_id):
    """The exact file a snapshot was imported from — its cached copy first (content-exact: the
    original path may since hold a newer update), else the original. None when neither exists."""
    with get_conn() as conn:
        row = conn.execute('SELECT original_path, cached_path FROM snapshots WHERE id = ?',
                           (snapshot_id,)).fetchone()
    if not row:
        return None
    return resolve_xml_path(row['cached_path'], row['original_path'])


def get_project_id_for_snapshot(snapshot_id):
    with get_conn() as conn:
        row = conn.execute('SELECT project_id FROM snapshots WHERE id = ?',
                           (snapshot_id,)).fetchone()
    return row['project_id'] if row else None


def get_snapshot_ui_state(snapshot_id, key):
    """A screen's saved state for one imported schedule (e.g. the Narrative project
    setup), or None when nothing was saved."""
    with get_conn() as conn:
        row = conn.execute('SELECT value_json FROM snapshot_ui_state WHERE snapshot_id = ? AND key = ?',
                           (snapshot_id, key)).fetchone()
    return _json.loads(row['value_json']) if row and row['value_json'] else None


def get_snapshot_ui_state_inherited(snapshot_id, key):
    """Like get_snapshot_ui_state, but a schedule with nothing saved under ``key`` yet (a
    re-import, or the project's next update: every import is a new snapshot) gets the
    state most recently saved for ANOTHER schedule of the same project. Returns
    ``(value, from_snapshot_id)`` — ``from_snapshot_id`` is None when the value is this
    schedule's own. A schedule whose state was cleared keeps it cleared (the NULL row
    save_snapshot_ui_state leaves), and a later import inherits that clear too.
    [startup:R2] S6"""
    with get_conn() as conn:
        row = conn.execute('SELECT value_json FROM snapshot_ui_state WHERE snapshot_id = ? AND key = ?',
                           (snapshot_id, key)).fetchone()
        if row is None:
            row = conn.execute(
                '''SELECT u.snapshot_id, u.value_json FROM snapshot_ui_state u
                   JOIN snapshots s ON s.id = u.snapshot_id
                   WHERE u.key = ? AND u.snapshot_id <> ?
                     AND s.project_id = (SELECT project_id FROM snapshots WHERE id = ?)
                   ORDER BY u.rowid DESC LIMIT 1''',          # REPLACE -> newest rowid = last saved
                (key, snapshot_id, snapshot_id)).fetchone()
            if row is None or not row['value_json']:
                return None, None
            return _json.loads(row['value_json']), row['snapshot_id']
    return (_json.loads(row['value_json']) if row['value_json'] else None), None


def save_snapshot_ui_state(snapshot_id, key, value):
    """Save (or with ``value=None`` clear) a screen's state for one imported schedule. A
    clear keeps a NULL row, so the schedule does not inherit an older schedule's state
    again (get_snapshot_ui_state_inherited)."""
    with get_conn() as conn:
        conn.execute('INSERT OR REPLACE INTO snapshot_ui_state (snapshot_id, key, value_json) '
                     'VALUES (?, ?, ?)', (snapshot_id, key,
                                          None if value is None else _json.dumps(value, default=str)))
    return value


def save_calendar_audit(snapshot_id, result):
    """Store the Calendar Audit result (JSON) for a snapshot."""
    with get_conn() as conn:
        conn.execute('INSERT OR REPLACE INTO calendar_audit (snapshot_id, data_json) VALUES (?, ?)',
                     (snapshot_id, _json.dumps(result, default=str)))


def get_calendar_audit(snapshot_id):
    with get_conn() as conn:
        row = conn.execute('SELECT data_json FROM calendar_audit WHERE snapshot_id = ?',
                           (snapshot_id,)).fetchone()
    return _json.loads(row['data_json']) if row and row['data_json'] else None


def get_project_settings(project_id):
    """Per-project Calendar Audit settings: {location, shutdown_reasons, manual_shutdowns}."""
    with get_conn() as conn:
        row = conn.execute('SELECT settings_json FROM project_settings WHERE project_id = ?',
                           (project_id,)).fetchone()
    return _json.loads(row['settings_json']) if row and row['settings_json'] else {}


def save_project_settings(project_id, patch):
    """Merge `patch` into the project's stored settings (shallow merge by top-level key)."""
    with get_conn() as conn:
        row = conn.execute('SELECT settings_json FROM project_settings WHERE project_id = ?',
                           (project_id,)).fetchone()
        settings = _json.loads(row['settings_json']) if row and row['settings_json'] else {}
        settings.update(patch or {})
        conn.execute('INSERT OR REPLACE INTO project_settings (project_id, settings_json) VALUES (?, ?)',
                     (project_id, _json.dumps(settings, default=str)))
    return settings


def get_contract_milestones(project_id):
    """The contract milestones the user entered for this project: [{'name','date'}].
    Held per project so they persist across re-imports (Milestone Check, gate B)."""
    return get_project_settings(project_id).get('contract_milestones') or []


def save_contract_milestones(project_id, milestones):
    """Persist the user's contract milestones for this project."""
    save_project_settings(project_id, {'contract_milestones': milestones or []})
    return milestones or []


def get_snapshot_xml_path(snapshot_id):
    """Best available XML path for a snapshot (original, cached fallback) — for the
    routes that must re-parse (Milestone Check re-evaluation)."""
    with get_conn() as conn:
        row = conn.execute('SELECT original_path, cached_path FROM snapshots WHERE id = ?',
                           (snapshot_id,)).fetchone()
    if not row:
        return None
    return resolve_xml_path(row['original_path'], row['cached_path'])


def get_audit_modules_for_snapshot(snapshot_id):
    """Reconstruct {'modules': {...}, 'module_order': [...], 'health': {...}} or None.

    The roll-up is re-derived from the stored module scores rather than stored
    itself: it is pure arithmetic over numbers we already keep, and re-deriving it
    means a re-opened project reflects the current weights instead of the ones in
    force on the day it was imported. No XML is touched.
    """
    from p6_audit.health import schedule_health
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM audit_modules WHERE snapshot_id = ? ORDER BY seq ASC',
            (snapshot_id,)
        ).fetchall()
    if not rows:
        return None
    modules = {}
    order = []
    for r in rows:
        order.append(r['module'])
        mod = {
            'module':      r['module'],
            'name':        r['name'],
            'score':       r['score'],
            'grade':       r['grade'],
            'pct':         r['pct'],
            'kpis':        _json.loads(r['kpis_json'] or '{}'),
            'wbs_summary': _json.loads(r['wbs_summary_json'] or '[]'),
            'findings':    _json.loads(r['findings_json'] or '[]'),
        }
        if r['mgmt_json']:
            mod['mgmt'] = _json.loads(r['mgmt_json'])
        modules[r['module']] = mod
    # Attach the normalized presentation (the same single source the UI/PDF/Excel
    # render from) so a re-opened project renders identically to a fresh import.
    from p6_audit.presentation import build_presentation
    for m in modules.values():
        m['presentation'] = build_presentation(m)
    # Milestone Check (gate B) on re-open: rename + pre-fill the saved contract
    # milestones and mark it needs_input, so the user re-confirms (and the tool
    # re-evaluates against this baseline) before the review shows.
    hard = modules.get('hard_constraints')
    if hard is not None:
        try:
            from p6_audit.milestone_check import NAME as _MC_NAME
            pid = get_project_id_for_snapshot(snapshot_id)
            hard['name'] = _MC_NAME
            hard['contract_milestones'] = get_contract_milestones(pid) if pid else []
            hard['milestones'] = []
            hard['needs_input'] = True
        except Exception:
            pass
    return {'modules': modules, 'module_order': order,
            'health': schedule_health(modules)}


# ── Queries ────────────────────────────────────────────────────────────────

def get_recent_projects(limit=10):
    """
    One row per project — the most recent snapshot for each.
    Returns the data the home-screen Recent Projects table needs.
    """
    with get_conn() as conn:
        rows = conn.execute(
            '''SELECT
                 p.id          AS project_id,
                 p.name,
                 s.id          AS snapshot_id,
                 s.imported_at,
                 s.data_date,
                 s.original_path,
                 s.cached_path,
                 m.spi,
                 m.delay_days  AS delay,
                 cm.actual_pct AS construction_pct
               FROM projects p
               JOIN snapshots s ON s.id = (
                   SELECT id FROM snapshots
                   WHERE project_id = p.id
                   ORDER BY imported_at DESC LIMIT 1
               )
               LEFT JOIN metrics m ON m.snapshot_id = s.id
               LEFT JOIN category_metrics cm
                   ON cm.snapshot_id = s.id AND cm.name = 'Construction'
               ORDER BY s.imported_at DESC
               LIMIT ?''',
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]

def delete_project(project_id):
    """Remove a project and all its snapshots/metrics — explicit cascade (no FK CASCADE in schema)."""
    with get_conn() as conn:
        snap_ids = [r[0] for r in conn.execute(
            'SELECT id FROM snapshots WHERE project_id = ?', (project_id,)
        ).fetchall()]
        if snap_ids:
            ph = ','.join('?' * len(snap_ids))
            conn.execute(f'DELETE FROM e1_summary       WHERE snapshot_id IN ({ph})', snap_ids)
            conn.execute(f'DELETE FROM calendar_audit   WHERE snapshot_id IN ({ph})', snap_ids)
            conn.execute(f'DELETE FROM evm_extras       WHERE snapshot_id IN ({ph})', snap_ids)
            conn.execute(f'DELETE FROM snapshot_views   WHERE snapshot_id IN ({ph})', snap_ids)
            conn.execute(f'DELETE FROM audit_modules    WHERE snapshot_id IN ({ph})', snap_ids)
            conn.execute(f'DELETE FROM audit_findings   WHERE snapshot_id IN ({ph})', snap_ids)
            conn.execute(f'DELETE FROM audit_scores     WHERE snapshot_id IN ({ph})', snap_ids)
            conn.execute(f'DELETE FROM category_metrics WHERE snapshot_id IN ({ph})', snap_ids)
            conn.execute(f'DELETE FROM metrics          WHERE snapshot_id IN ({ph})', snap_ids)
            conn.execute(f'DELETE FROM snapshot_ui_state WHERE snapshot_id IN ({ph})', snap_ids)
            conn.execute('DELETE FROM snapshots WHERE project_id = ?', (project_id,))
        conn.execute('DELETE FROM project_settings WHERE project_id = ?', (project_id,))
        conn.execute('DELETE FROM projects WHERE id = ?', (project_id,))

def get_prior_import_date(file_hash):
    """
    Return the imported_at timestamp of the most recent snapshot with this
    file_hash, or None if this is the first time the file is seen.
    Called before inserting a new snapshot so the result reflects only
    genuinely prior imports.
    """
    with get_conn() as conn:
        row = conn.execute(
            'SELECT imported_at FROM snapshots WHERE file_hash = ? ORDER BY imported_at DESC LIMIT 1',
            (file_hash,)
        ).fetchone()
    return row['imported_at'] if row else None


def get_project_result(project_id):
    """
    Load the stored result for a project's most recent snapshot directly from
    the DB — no XML parsing, no metric recomputation.
    Returns a dict shaped identically to what /api/parse puts in data['result'],
    or None if the project doesn't exist.
    """
    with get_conn() as conn:
        snap = conn.execute(
            '''SELECT s.id, s.data_date, s.activity_count, s.calendar_count,
                      s.original_path, s.cached_path,
                      p.name AS project_name,
                      m.pv, m.ev, m.ac, m.spi, m.cpi, m.delay_days,
                      m.overall_planned_pct, m.overall_actual_pct, m.variance
               FROM snapshots s
               JOIN projects p ON p.id = s.project_id
               LEFT JOIN metrics m ON m.snapshot_id = s.id
               WHERE s.project_id = ?
               ORDER BY s.imported_at DESC, s.id DESC LIMIT 1''',
            (project_id,)
        ).fetchone()
        if not snap:
            return None
        cats = conn.execute(
            '''SELECT name, weight, planned_pct, actual_pct, bac, ac,
                      activity_count, overridden
               FROM category_metrics WHERE snapshot_id = ?''',
            (snap['id'],)
        ).fetchall()

    categories = {
        c['name']: {
            'weight':         c['weight'],
            'planned_pct':    c['planned_pct'],
            'actual_pct':     c['actual_pct'],
            'bac':            c['bac'],
            'ac':             c['ac'],
            'activity_count': c['activity_count'],
            'overridden':     bool(c['overridden']),
        }
        for c in cats
    }
    return {
        'pv':                  snap['pv'],
        'ev':                  snap['ev'],
        'ac':                  snap['ac'],
        'spi':                 snap['spi'],
        'cpi':                 snap['cpi'],
        'delay_days':          snap['delay_days'],
        'variance':            snap['variance'],
        'overall_planned_pct': snap['overall_planned_pct'],
        'overall_actual_pct':  snap['overall_actual_pct'],
        'data_date':           snap['data_date'],
        'activity_count':      snap['activity_count'],
        'calendar_count':      snap['calendar_count'],
        'project_name':        snap['project_name'],
        'categories':          categories,
        '_snapshot_id':        snap['id'],
        '_cached_path':        snap['cached_path'],
        '_original_path':      snap['original_path'],
    }


def get_project_snapshots(project_id):
    """All snapshots for one project — for trend charts (future dashboards)."""
    with get_conn() as conn:
        rows = conn.execute(
            '''SELECT s.id, s.data_date, s.imported_at,
                      m.pv, m.ev, m.ac, m.spi, m.cpi, m.delay_days,
                      m.overall_planned_pct, m.overall_actual_pct
               FROM snapshots s
               LEFT JOIN metrics m ON m.snapshot_id = s.id
               WHERE s.project_id = ?
               ORDER BY s.data_date ASC''',
            (project_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_prev_snapshot(snapshot_id):
    """The snapshot immediately before `snapshot_id` for the same project (by data
    date, then import time) — used by Update vs Update to auto-suggest last period.
    Returns {id, data_date, original_path, cached_path} or None."""
    with get_conn() as conn:
        cur = conn.execute(
            'SELECT project_id, data_date, imported_at FROM snapshots WHERE id = ?',
            (snapshot_id,)
        ).fetchone()
        if not cur:
            return None
        row = conn.execute(
            '''SELECT id, data_date, original_path, cached_path
               FROM snapshots
               WHERE project_id = ?
                 AND (data_date < ? OR (data_date = ? AND imported_at < ?))
               ORDER BY data_date DESC, imported_at DESC
               LIMIT 1''',
            (cur['project_id'], cur['data_date'], cur['data_date'], cur['imported_at'])
        ).fetchone()
        return dict(row) if row else None

def snapshot_project_id(snapshot_id):
    """project_id owning a snapshot (or None)."""
    with get_conn() as conn:
        r = conn.execute('SELECT project_id FROM snapshots WHERE id = ?', (snapshot_id,)).fetchone()
        return r['project_id'] if r else None

def get_project_snapshot_files(project_id):
    """[{id, data_date, original_path, cached_path}] for a project, oldest first —
    used by the milestone trend to walk every stored update."""
    with get_conn() as conn:
        rows = conn.execute(
            '''SELECT id, data_date, original_path, cached_path
               FROM snapshots WHERE project_id = ?
               ORDER BY data_date ASC, imported_at ASC''',
            (project_id,)
        ).fetchall()
    return [dict(r) for r in rows]

def cache_snapshot_milestones(snapshot_id, milestones):
    """Store extracted milestone finishes for a snapshot (idempotent). `milestones` is a
    list of {activity_id, name, task_type, finish_date}. An empty list writes a single
    '__none__' sentinel so the snapshot is marked scanned and never re-parsed."""
    rows = milestones or [{'activity_id': '__none__', 'name': None, 'task_type': None, 'finish_date': None}]
    with get_conn() as conn:
        conn.execute('DELETE FROM snapshot_milestones WHERE snapshot_id = ?', (snapshot_id,))
        conn.executemany(
            '''INSERT OR REPLACE INTO snapshot_milestones
               (snapshot_id, activity_id, name, task_type, finish_date) VALUES (?,?,?,?,?)''',
            [(snapshot_id, m['activity_id'], m.get('name'), m.get('task_type'), m.get('finish_date'))
             for m in rows])

def get_snapshot_milestones(snapshot_id):
    """(scanned, rows). scanned=True once extraction has been cached (even if the
    snapshot had no milestones); rows excludes the '__none__' sentinel."""
    with get_conn() as conn:
        raw = [dict(r) for r in conn.execute(
            '''SELECT activity_id, name, task_type, finish_date
               FROM snapshot_milestones WHERE snapshot_id = ?''', (snapshot_id,)).fetchall()]
    return (len(raw) > 0), [r for r in raw if r['activity_id'] != '__none__']

def resolve_xml_path(original_path, cached_path):
    """Return the best available XML path: original first, cached fallback."""
    if original_path and os.path.isfile(original_path):
        return original_path
    if cached_path and os.path.isfile(cached_path):
        return cached_path
    return None


# ── Migration from history.json ────────────────────────────────────────────

def migrate_history_json(json_path):
    """
    One-time import of legacy history.json into SQLite.
    Best-effort: only snapshot-level data available (no full metrics).
    Renames the file to history.json.migrated when done.
    """
    import json
    try:
        with open(json_path) as f:
            entries = json.load(f)
    except (OSError, json.JSONDecodeError):
        return

    for h in reversed(entries):  # oldest first so imported_at order makes sense
        try:
            p6_id = ''
            name  = h.get('filename', '')
            pid   = upsert_project(p6_id, name)

            with get_conn() as conn:
                conn.execute(
                    '''INSERT INTO snapshots
                       (project_id, imported_at, data_date, original_path,
                        cached_path, file_hash, activity_count, calendar_count)
                       VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL)''',
                    (pid, _now(), h.get('data_date'), h.get('path'))
                )
                sid = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

                # Store whatever partial metrics we have
                conn.execute(
                    '''INSERT INTO metrics
                       (snapshot_id, spi, delay_days)
                       VALUES (?, ?, ?)''',
                    (sid, h.get('spi'), h.get('delay'))
                )
                if h.get('construction_pct') is not None:
                    conn.execute(
                        '''INSERT INTO category_metrics
                           (snapshot_id, name, actual_pct)
                           VALUES (?, 'Construction', ?)''',
                        (sid, h['construction_pct'])
                    )
        except Exception:
            continue  # skip bad entries, keep going

    try:
        os.rename(json_path, json_path + '.migrated')
    except OSError:
        pass


# ── Helpers ────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc).isoformat()
