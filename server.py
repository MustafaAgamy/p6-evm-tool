from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import sys
from datetime import datetime, date
from utils import resource_path, exe_dir


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

            # Strip the large records list — UI only needs the rolled-up metrics
            safe_result = {k: v for k, v in result.items() if k != 'records'}
            # Augment with counts the UI shows in the file info bar
            safe_result['activity_count'] = len(data.activities)
            safe_result['calendar_count'] = len(data.calendars)
            safe_result['project_name'] = data.project.get('name', '')

            _save_history(xml_path, safe_result)
            self._json(200, {'ok': True, 'result': safe_result})

        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/report ────────────────────────────────────────────────────────
    def _handle_report(self, body):
        xml_path = body.get('xml_path', '')
        output_path = body.get('output_path', '')
        overrides_path = body.get('overrides_path')

        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        if not xml_path or not os.path.isfile(xml_path):
            self._json(200, {'ok': False, 'error': f'Original XML not found: {xml_path}. Re-import the file first.'})
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

            data = parse_file(xml_path)
            result = compute(data, config, overrides=overrides)

            fm = find_finish_milestone(result)
            milestone_baseline_finish = None
            if fm is not None:
                baseline = data.baseline_by_id.get(fm['activity']['id'])
                if baseline:
                    milestone_baseline_finish = baseline['planned_finish']

            meta = {
                'project_name': data.project.get('name') or 'Weekly Report',
                'project_id': data.project.get('id') or '',
                'source_file': os.path.basename(xml_path),
                'milestone_baseline_finish': milestone_baseline_finish,
            }

            html_content = render_html(result, meta)

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
        self._json(200, _load_history())


# ── Chrome finder (mirrors generate_report.py) ─────────────────────────────
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
        'No Chrome/Chromium found. Install Google Chrome or run: pip install playwright && playwright install chromium'
    )


# ── History helpers ────────────────────────────────────────────────────────
def _history_file():
    return os.path.join(exe_dir(), 'history.json')

def _load_history():
    path = _history_file()
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

def _save_history(xml_path, result):
    history = _load_history()
    categories = result.get('categories') or {}
    construction = categories.get('Construction', {})
    entry = {
        'path':             xml_path,
        'filename':         os.path.basename(xml_path),
        'data_date':        str(result.get('data_date', '')),
        'delay':            result.get('delay_days'),
        'spi':              result.get('spi'),
        'construction_pct': construction.get('actual_pct'),
    }
    history = [h for h in history if h.get('path') != xml_path]
    history.insert(0, entry)
    with open(_history_file(), 'w') as f:
        json.dump(history[:10], f, indent=2, cls=_Encoder)


def make_server():
    return HTTPServer(('127.0.0.1', 0), Handler)
