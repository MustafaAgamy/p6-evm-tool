"""
All SQLite database operations for nPace.
DB lives at %APPDATA%/P6EVMTool/p6evm.db — one per OS user.
"""

import sqlite3
import os
import hashlib
import shutil
import json as _json
from datetime import datetime, timezone
from utils import app_data_dir, schedules_dir

MAX_CACHED_XML = 20  # oldest cached XML files deleted beyond this


# ── Connection ─────────────────────────────────────────────────────────────

def _db_path():
    return os.path.join(app_data_dir(), 'p6evm.db')

def get_conn():
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


# ── Schema ─────────────────────────────────────────────────────────────────

def init_db():
    with get_conn() as conn:
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

            CREATE TABLE IF NOT EXISTS calendar_audit (
                snapshot_id INTEGER PRIMARY KEY REFERENCES snapshots(id),
                data_json   TEXT
            );

            CREATE TABLE IF NOT EXISTS project_settings (
                project_id    INTEGER PRIMARY KEY REFERENCES projects(id),
                settings_json TEXT
            );
        ''')


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
    _cleanup_old_xml_files()
    return dest

def _cleanup_old_xml_files():
    """Keep only the MAX_CACHED_XML most recently modified XML files."""
    sdir = schedules_dir()
    files = sorted(
        [os.path.join(sdir, f) for f in os.listdir(sdir) if f.endswith('.xml')],
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
        ))
    if not rows:
        return
    with get_conn() as conn:
        conn.executemany(
            '''INSERT OR REPLACE INTO audit_modules
               (snapshot_id, module, seq, name, score, grade, pct,
                kpis_json, wbs_summary_json, findings_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
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
        conn.execute('INSERT OR REPLACE INTO evm_extras (snapshot_id, extras_json) VALUES (?, ?)',
                     (snapshot_id, _json.dumps(extras, default=str)))


def get_evm_extras(snapshot_id):
    with get_conn() as conn:
        row = conn.execute('SELECT extras_json FROM evm_extras WHERE snapshot_id = ?',
                           (snapshot_id,)).fetchone()
    return _json.loads(row['extras_json']) if row and row['extras_json'] else None


def save_baseline(snapshot_id, baseline_path):
    """Remember the attached baseline for this snapshot (merged into evm_extras)."""
    with get_conn() as conn:
        row = conn.execute('SELECT extras_json FROM evm_extras WHERE snapshot_id = ?',
                           (snapshot_id,)).fetchone()
        extras = _json.loads(row['extras_json']) if row and row['extras_json'] else {}
        extras['baseline_path'] = baseline_path
        conn.execute('INSERT OR REPLACE INTO evm_extras (snapshot_id, extras_json) VALUES (?, ?)',
                     (snapshot_id, _json.dumps(extras, default=str)))


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


def get_audit_modules_for_snapshot(snapshot_id):
    """Reconstruct {'modules': {...}, 'module_order': [...]} or None."""
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
        modules[r['module']] = {
            'module':      r['module'],
            'name':        r['name'],
            'score':       r['score'],
            'grade':       r['grade'],
            'pct':         r['pct'],
            'kpis':        _json.loads(r['kpis_json'] or '{}'),
            'wbs_summary': _json.loads(r['wbs_summary_json'] or '[]'),
            'findings':    _json.loads(r['findings_json'] or '[]'),
        }
    return {'modules': modules, 'module_order': order}


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
            conn.execute(f'DELETE FROM audit_modules    WHERE snapshot_id IN ({ph})', snap_ids)
            conn.execute(f'DELETE FROM audit_findings   WHERE snapshot_id IN ({ph})', snap_ids)
            conn.execute(f'DELETE FROM audit_scores     WHERE snapshot_id IN ({ph})', snap_ids)
            conn.execute(f'DELETE FROM category_metrics WHERE snapshot_id IN ({ph})', snap_ids)
            conn.execute(f'DELETE FROM metrics          WHERE snapshot_id IN ({ph})', snap_ids)
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
