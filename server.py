from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import sys
from datetime import datetime, date
from utils import resource_path, exe_dir, app_data_dir
import db


class _Encoder(json.JSONEncoder):
    """Handle datetime/date objects that metrics.py returns in data_date."""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # silence request logs

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self._serve_index()
        elif self.path.startswith('/ui/'):
            ext = self.path.rsplit('.', 1)[-1]
            mime = {'css': 'text/css', 'js': 'application/javascript'}.get(ext, 'text/plain')
            self._serve(resource_path(self.path.lstrip('/')), mime)
        elif self.path == '/api/history':
            self._handle_history()
        else:
            self._json(404, {'ok': False, 'error': 'not found'})

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length))
        if self.path == '/api/parse':
            self._handle_parse(body)
        elif self.path == '/api/report':
            self._handle_report(body)
        elif self.path == '/api/project/load':
            self._handle_project_load(body)
        elif self.path == '/api/project/delete':
            self._handle_project_delete(body)
        elif self.path == '/api/export/excel':
            self._handle_export_excel(body)
        elif self.path == '/api/report/module':
            self._handle_module_report(body)
        else:
            self._json(404, {'ok': False, 'error': 'not found'})

    # ── Static files ───────────────────────────────────────────────────────
    def _serve_index(self):
        try:
            with open(resource_path('ui/index.html'), 'rb') as f:
                html = f.read().decode()
            port = self.server.server_address[1]
            html = html.replace('</head>', f'<script>window.__SERVER_PORT__ = {port};</script></head>', 1)
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(html.encode())
        except FileNotFoundError:
            self._json(404, {'ok': False, 'error': 'index.html not found'})

    def _serve(self, path, mime):
        try:
            with open(path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self._json(404, {'ok': False, 'error': f'file not found: {path}'})

    def _json(self, status, data):
        body = json.dumps(data, cls=_Encoder).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    # ── /api/parse ─────────────────────────────────────────────────────────
    def _handle_parse(self, body):
        xml_path = body.get('path', '')
        overrides_path = body.get('overrides_path')

        if not xml_path or not os.path.isfile(xml_path):
            self._json(200, {'ok': False, 'error': f'File not found: {xml_path}'})
            return

        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_evm.metrics import compute

            with open(resource_path('config.json')) as f:
                config = json.load(f)

            overrides = {}
            if overrides_path and os.path.isfile(overrides_path):
                with open(overrides_path) as f:
                    overrides = json.load(f)

            data = parse_file(xml_path)
            result = compute(data, config, overrides=overrides)

            # Strip the large records list — UI only needs rolled-up metrics
            safe_result = {k: v for k, v in result.items() if k != 'records'}
            safe_result['activity_count'] = len(data.activities)
            safe_result['calendar_count'] = len(data.calendars)
            safe_result['project_name']   = data.project.get('name', '')

            # ── Schedule audit — isolated modules (never break EVM import) ──
            audit_modules_result = None
            try:
                from p6_audit import audit_modules as run_audit_modules
                audit_modules_result = run_audit_modules(data, config)
            except Exception as audit_exc:
                audit_modules_result = None
                print(f'[audit] skipped: {audit_exc}', file=sys.stderr)
            safe_result['audit_modules'] = audit_modules_result

            # ── Persist to DB ──────────────────────────────────────────────
            file_hash      = db.hash_file(xml_path)
            prior_import   = db.get_prior_import_date(file_hash)
            cached_path    = db.cache_xml(xml_path, file_hash)

            p6_id = data.project.get('id', '') or ''
            name  = data.project.get('name', '') or os.path.basename(xml_path)
            pid   = db.upsert_project(p6_id, name)

            sid = db.insert_snapshot(
                project_id     = pid,
                data_date      = result.get('data_date'),
                original_path  = xml_path,
                cached_path    = cached_path,
                file_hash      = file_hash,
                activity_count = len(data.activities),
                calendar_count = len(data.calendars),
            )
            db.insert_metrics(sid, result)
            db.insert_category_metrics(sid, result.get('categories'))
            if audit_modules_result is not None:
                db.insert_audit_modules(sid, audit_modules_result)
            # ──────────────────────────────────────────────────────────────

            self._json(200, {'ok': True, 'result': safe_result, 'cached_path': cached_path,
                             'previous_import': prior_import, 'snapshot_id': sid})

        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/report ────────────────────────────────────────────────────────
    def _handle_report(self, body):
        xml_path     = body.get('xml_path', '')
        output_path  = body.get('output_path', '')
        overrides_path = body.get('overrides_path')
        cached_path  = body.get('cached_path')  # optional, sent by frontend if known

        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return

        # Resolve best available XML — original first, cached fallback
        resolved = db.resolve_xml_path(xml_path, cached_path)
        if not resolved:
            self._json(200, {'ok': False, 'error': (
                'Original XML not found and no cached copy available. '
                'Re-import the file to generate a PDF.'
            )})
            return

        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_evm.metrics import compute
            from p6_evm.report import render_html, find_finish_milestone
            import subprocess, tempfile

            with open(resource_path('config.json')) as f:
                config = json.load(f)

            overrides = {}
            if overrides_path and os.path.isfile(overrides_path):
                with open(overrides_path) as f:
                    overrides = json.load(f)

            data   = parse_file(resolved)
            result = compute(data, config, overrides=overrides)

            fm = find_finish_milestone(result)
            milestone_baseline_finish = None
            if fm is not None:
                baseline = data.baseline_by_id.get(fm['activity']['id'])
                if baseline:
                    milestone_baseline_finish = baseline['planned_finish']

            meta = {
                'project_name':              data.project.get('name') or 'Weekly Report',
                'project_id':                data.project.get('id') or '',
                'source_file':               os.path.basename(resolved),
                'milestone_baseline_finish': milestone_baseline_finish,
            }

            html_content = render_html(result, meta)

            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name

            chrome  = _find_chrome()
            out_path = os.path.abspath(output_path)
            subprocess.run([
                chrome, '--headless', '--disable-gpu', '--no-sandbox',
                f'--print-to-pdf={out_path}', '--no-pdf-header-footer',
                f'file:///{html_path.replace(os.sep, "/")}',
            ], check=True, capture_output=True)

            os.unlink(html_path)
            self._json(200, {'ok': True})

        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/project/load ─────────────────────────────────────────────────
    def _handle_project_load(self, body):
        """Return stored metrics for a project without re-parsing the XML."""
        project_id = body.get('project_id')
        if not project_id:
            self._json(200, {'ok': False, 'error': 'project_id required'})
            return
        result = db.get_project_result(project_id)
        if result is None:
            self._json(200, {'ok': False, 'error': 'Project not found'})
            return
        snapshot_id   = result.pop('_snapshot_id', None)
        cached_path   = result.pop('_cached_path', None)
        original_path = result.pop('_original_path', None)
        result['audit_modules'] = db.get_audit_modules_for_snapshot(snapshot_id) if snapshot_id else None
        self._json(200, {'ok': True, 'result': result, 'snapshot_id': snapshot_id,
                         'cached_path': cached_path, 'original_path': original_path})

    # ── /api/project/delete ────────────────────────────────────────────────
    def _handle_project_delete(self, body):
        project_id = body.get('project_id')
        if not project_id:
            self._json(200, {'ok': False, 'error': 'project_id required'})
            return
        try:
            db.delete_project(project_id)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/export/excel ──────────────────────────────────────────────────
    def _handle_export_excel(self, body):
        """Excel for ONE isolated module (never mixed). Read path = DB."""
        snapshot_id = body.get('snapshot_id')
        module      = body.get('module')
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        mods = db.get_audit_modules_for_snapshot(snapshot_id) if snapshot_id else None
        m = (mods or {}).get('modules', {}).get(module)
        if not m:
            self._json(200, {'ok': False, 'error': 'No audit found for this module.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.xlsx_writer import write_xlsx
            from p6_audit.exporters import excel_columns
            headers, rows = excel_columns(m)
            write_xlsx(os.path.abspath(output_path), (m.get('name') or 'Schedule Audit')[:31], headers, rows)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/report/module ─────────────────────────────────────────────────
    def _handle_module_report(self, body):
        """Standalone consultant PDF for ONE isolated module."""
        snapshot_id = body.get('snapshot_id')
        module      = body.get('module')
        output_path = body.get('output_path', '')
        meta_in     = body.get('meta') or {}
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        mods = db.get_audit_modules_for_snapshot(snapshot_id) if snapshot_id else None
        m = (mods or {}).get('modules', {}).get(module)
        if not m:
            self._json(200, {'ok': False, 'error': 'No audit found for this module.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_audit.report import render_module_report
            import subprocess, tempfile
            html_content = render_module_report(m, meta_in)
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name
            chrome = _find_chrome()
            out_path = os.path.abspath(output_path)
            subprocess.run([
                chrome, '--headless', '--disable-gpu', '--no-sandbox',
                f'--print-to-pdf={out_path}', '--no-pdf-header-footer',
                f'file:///{html_path.replace(os.sep, "/")}',
            ], check=True, capture_output=True)
            os.unlink(html_path)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/history ───────────────────────────────────────────────────────
    def _handle_history(self):
        rows = db.get_recent_projects(limit=10)
        # Normalise to the shape app.js already expects
        history = []
        for r in rows:
            history.append({
                'path':             r.get('original_path', ''),
                'cached_path':      r.get('cached_path', ''),
                'filename':         os.path.basename(r.get('original_path') or r.get('name') or ''),
                'data_date':        r.get('data_date', ''),
                'delay':            r.get('delay'),
                'spi':              r.get('spi'),
                'construction_pct': r.get('construction_pct'),
                'project_id':       r.get('project_id'),
                'snapshot_id':      r.get('snapshot_id'),
            })
        self._json(200, history)


# ── Chrome finder ──────────────────────────────────────────────────────────
CHROME_CANDIDATES = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files\Chromium\Application\chrome.exe',
]

def _find_chrome():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            path = p.chromium.executable_path
            if path and os.path.exists(path):
                return path
    except Exception:
        pass
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    raise RuntimeError(
        'No Chrome/Chromium found. Install Google Chrome or run: '
        'pip install playwright && playwright install chromium'
    )


def make_server():
    # Run migration from legacy history.json if it exists
    legacy = os.path.join(exe_dir(), 'history.json')
    if os.path.exists(legacy):
        db.migrate_history_json(legacy)

    db.init_db()
    return HTTPServer(('127.0.0.1', 0), Handler)
