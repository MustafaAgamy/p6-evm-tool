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
        elif self.path == '/api/gap':
            self._handle_gap(body)
        elif self.path == '/api/e1/upload':
            self._handle_e1_upload(body)
        elif self.path == '/api/baseline/upload':
            self._handle_baseline_upload(body)
        elif self.path == '/api/report/evm':
            self._handle_evm_report(body)
        elif self.path == '/api/report/calendar':
            self._handle_calendar_report(body)
        elif self.path == '/api/export/calendar_excel':
            self._handle_calendar_excel(body)
        elif self.path == '/api/geocode':
            self._handle_geocode(body)
        elif self.path == '/api/weather':
            self._handle_weather(body)
        elif self.path == '/api/calendar/settings':
            self._handle_calendar_settings(body)
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

            from p6_evm.classify import auto_categories, build_wbs_classifier
            data = parse_file(xml_path)
            config['categories'] = auto_categories(data)   # auto-detect categories per project
            result = compute(data, config, overrides=overrides, classifier=build_wbs_classifier(data))

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

            # ── EVM v2 extras: engineering (Mode B, from P6) + code dimensions ──
            try:
                from p6_evm.engineering_p6 import engineering_from_p6
                eng_p6 = engineering_from_p6(data)
                safe_result['engineering_p6'] = [
                    {'trade': t, 'submittal_type': ty, **vals}
                    for (t, ty), vals in sorted(eng_p6.items())
                ]
            except Exception as eng_exc:
                safe_result['engineering_p6'] = []
                print(f'[evm] engineering skipped: {eng_exc}', file=sys.stderr)
            # Baseline vs expected finish (from the finish milestone) for the dashboard
            try:
                from p6_evm.report import find_finish_milestone
                fm = find_finish_milestone(result)
                if fm is not None:
                    safe_result['expected_finish'] = fm['activity'].get('planned_finish')
                    bl = data.baseline_by_id.get(fm['activity'].get('id'))
                    safe_result['baseline_finish'] = bl['planned_finish'] if bl else None
            except Exception:
                pass

            code_types = list(getattr(data, 'activity_code_types', []) or [])
            safe_result['activity_code_types'] = code_types
            # Default PV-EV gap on a sensible dimension (records still present on `result`)
            try:
                from p6_evm.gap import gap_by_code
                default_dim = 'Type of Works' if 'Type of Works' in code_types else (code_types[0] if code_types else None)
                safe_result['gap'] = gap_by_code(result['records'], default_dim) if default_dim else None
            except Exception:
                safe_result['gap'] = None

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

            # ── Calendar Audit — isolated, never breaks EVM import ──────────
            try:
                from p6_calendar import calendar_audit
                settings = db.get_project_settings(pid)
                cal_result = calendar_audit(data, config, settings)
                safe_result['calendar_audit'] = cal_result
                db.save_calendar_audit(sid, cal_result)
            except Exception as cal_exc:
                safe_result['calendar_audit'] = None
                print(f'[calendar] skipped: {cal_exc}', file=sys.stderr)
            db.save_evm_extras(sid, {
                'engineering_p6': safe_result.get('engineering_p6', []),
                'activity_code_types': safe_result.get('activity_code_types', []),
                'gap': safe_result.get('gap'),
                'baseline_finish': safe_result.get('baseline_finish'),
                'expected_finish': safe_result.get('expected_finish'),
            })
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

            from p6_evm.classify import auto_categories, build_wbs_classifier
            data   = parse_file(resolved)
            config['categories'] = auto_categories(data)
            result = compute(data, config, overrides=overrides, classifier=build_wbs_classifier(data))

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
        result['calendar_audit'] = db.get_calendar_audit(snapshot_id) if snapshot_id else None
        extras = (db.get_evm_extras(snapshot_id) or {}) if snapshot_id else {}
        result['engineering_p6'] = extras.get('engineering_p6', [])
        result['activity_code_types'] = extras.get('activity_code_types', [])
        result['gap'] = extras.get('gap')
        result['baseline_finish'] = extras.get('baseline_finish')
        result['expected_finish'] = extras.get('expected_finish')
        # Re-apply an attached baseline (re-parse update + baseline) so PV/SPI/Delay stay correct.
        bl_path = extras.get('baseline_path')
        if bl_path and os.path.isfile(bl_path) and cached_path and os.path.isfile(cached_path):
            try:
                sys.path.insert(0, resource_path('.'))
                from p6_evm.parser import parse_file
                from p6_evm.metrics import compute
                from p6_evm.classify import auto_categories, build_wbs_classifier
                with open(resource_path('config.json')) as f:
                    config = json.load(f)
                data = parse_file(cached_path)
                bl = parse_file(bl_path)
                data.baseline_by_id = {a['id']: {'planned_start': a.get('planned_start'),
                                                 'planned_finish': a.get('planned_finish')}
                                       for a in bl.activities.values() if a.get('id')}
                config['categories'] = auto_categories(data)
                rr = compute(data, config, classifier=build_wbs_classifier(data))
                for k in ('pv', 'ev', 'spi', 'cpi', 'delay_days',
                          'overall_planned_pct', 'overall_actual_pct'):
                    result[k] = rr[k]
                result['categories'] = {n: {'weight': c['weight'], 'planned_pct': c['planned_pct'],
                                            'actual_pct': c['actual_pct'], 'bac': c['bac'], 'ac': c['ac'],
                                            'activity_count': c['activity_count'], 'overridden': c['overridden']}
                                        for n, c in rr['categories'].items()}
                result['baseline_path'] = bl_path
                result['baseline_name'] = os.path.basename(bl_path)
            except Exception as bexc:
                print(f'[evm] baseline re-apply skipped: {bexc}', file=sys.stderr)

        e1_rows = db.get_e1_summary(snapshot_id) if snapshot_id else None
        result['engineering_e1'] = e1_rows
        if e1_rows:                          # re-apply E1 rollup so a re-opened project matches
            from p6_evm.e1_rollup import e1_extras
            result['e1_extras'] = e1_extras(e1_rows, list((result.get('categories') or {}).keys()))
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
        preview     = bool(body.get('preview'))   # return HTML for on-screen preview, don't write a PDF
        output_path = body.get('output_path', '')
        meta_in     = body.get('meta') or {}
        if not preview and not output_path:
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
            if preview:
                self._json(200, {'ok': True, 'html': html_content})
                return
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

    # ── /api/gap ───────────────────────────────────────────────────────────
    def _handle_gap(self, body):
        """Re-group the PV-EV gap by a different activity code (re-parses XML)."""
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        dim = body.get('dimension')
        if not resolved or not dim:
            self._json(200, {'ok': False, 'error': 'schedule or dimension unavailable'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_evm.metrics import compute
            from p6_evm.gap import gap_by_code
            from p6_evm.classify import auto_categories, build_wbs_classifier
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            data = parse_file(resolved)
            config['categories'] = auto_categories(data)
            result = compute(data, config, classifier=build_wbs_classifier(data))
            self._json(200, {'ok': True, 'gap': gap_by_code(result['records'], dim)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/e1/upload ─────────────────────────────────────────────────────
    def _handle_e1_upload(self, body):
        """Read one or more E1 / Design / Shop-drawing log Excels → combined drawings
        summary (Mode A); store per snapshot. A whole file whose NAME says Shop/Design
        tags all its rows to that bucket; a combined log is split by drawing type."""
        paths = body.get('paths') or ([body['path']] if body.get('path') else [])
        paths = [p for p in paths if p and os.path.isfile(p)]
        snapshot_id = body.get('snapshot_id')
        if not paths:
            self._json(200, {'ok': False, 'error': 'No Excel log file found.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.e1_log import read_e1_rows, summarize_e1
            from p6_evm.e1_rollup import e1_extras
            from p6_evm.classify import e1_file_bucket
            eng_rows = []
            for p in paths:
                bucket = e1_file_bucket(os.path.basename(p))   # 'design' | 'engineering' | None
                summ = summarize_e1(read_e1_rows(p))
                for (t, ty), vals in sorted(summ.items()):
                    row = {'trade': t, 'submittal_type': ty, **vals}
                    if bucket:
                        row['bucket'] = bucket
                    eng_rows.append(row)
            if snapshot_id:
                db.save_e1_summary(snapshot_id, eng_rows)
            extras = e1_extras(eng_rows, body.get('category_names') or [])
            self._json(200, {'ok': True, 'engineering_e1': eng_rows, 'e1_extras': extras})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/baseline/upload ───────────────────────────────────────────────
    def _handle_baseline_upload(self, body):
        """Attach a baseline schedule (XER/XML) so Planned Value uses the TRUE baseline
        dates. A XER update doesn't embed its baseline, so its PV is wrong without this;
        matching by Activity ID, we override the update's baseline and recompute."""
        bl_path = body.get('path', '')
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        if not bl_path or not os.path.isfile(bl_path):
            self._json(200, {'ok': False, 'error': f'Baseline file not found: {bl_path}'})
            return
        if not resolved:
            self._json(200, {'ok': False, 'error': 'Update schedule not available. Re-import it first.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_evm.metrics import compute
            from p6_evm.classify import auto_categories, build_wbs_classifier
            bl = parse_file(bl_path)
            bl_dates = {a['id']: {'planned_start': a.get('planned_start'),
                                  'planned_finish': a.get('planned_finish')}
                        for a in bl.activities.values() if a.get('id')}
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            data = parse_file(resolved)
            data.baseline_by_id = bl_dates          # use the attached baseline
            config['categories'] = auto_categories(data)
            result = compute(data, config, classifier=build_wbs_classifier(data))
            bl_cached = db.cache_xml(bl_path, db.hash_file(bl_path))
            if body.get('snapshot_id'):
                db.save_baseline(body['snapshot_id'], bl_cached)   # remember per project
            matched = sum(1 for a in data.activities.values() if a.get('id') in bl_dates)
            cats = {n: {'weight': c['weight'], 'planned_pct': c['planned_pct'],
                        'actual_pct': c['actual_pct'], 'bac': c['bac'], 'ac': c['ac'],
                        'activity_count': c['activity_count'], 'overridden': c['overridden']}
                    for n, c in result['categories'].items()}
            self._json(200, {'ok': True, 'baseline_name': os.path.basename(bl_path),
                             'baseline_cached': bl_cached, 'matched': matched,
                             'total': len(data.activities),
                             'pv': result['pv'], 'ev': result['ev'], 'spi': result['spi'],
                             'cpi': result['cpi'], 'delay_days': result['delay_days'],
                             'overall_planned_pct': result['overall_planned_pct'],
                             'overall_actual_pct': result['overall_actual_pct'],
                             'categories': cats})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/report/evm ────────────────────────────────────────────────────
    def _handle_evm_report(self, body):
        """Render the consultant EVM report PDF with the user's weights/AC/engineering."""
        preview = bool(body.get('preview'))   # return HTML for on-screen preview, don't write a PDF
        output_path = body.get('output_path', '')
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        if not preview and not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        if not resolved:
            self._json(200, {'ok': False, 'error': 'Schedule not available. Re-import the file.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_evm.metrics import compute
            from p6_evm.gap import gap_by_code
            from p6_evm.evm_report import render_evm_report
            import subprocess, tempfile
            from p6_evm.classify import auto_categories, build_wbs_classifier
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            weights = body.get('weights') or {}
            data = parse_file(resolved)
            bl_path = body.get('baseline_path')     # attached baseline (for correct PV)
            if bl_path and os.path.isfile(bl_path):
                bl = parse_file(bl_path)
                data.baseline_by_id = {a['id']: {'planned_start': a.get('planned_start'),
                                                 'planned_finish': a.get('planned_finish')}
                                       for a in bl.activities.values() if a.get('id')}
            config['categories'] = auto_categories(data, saved_weights=weights)
            result = compute(data, config, classifier=build_wbs_classifier(data))
            meta_in = body.get('meta') or {}
            if body.get('actual_cost') is not None:
                meta_in['actual_cost'] = body.get('actual_cost')
            dim = body.get('dimension')
            gap = gap_by_code(result['records'], dim) if dim else None
            engineering = body.get('engineering')
            # E1 Log drives the report: override Design/Engineering category actuals and
            # attach the overall rows + Design/Shop gaps (single source: e1_rollup).
            if engineering and engineering.get('mode') == 'E1' and engineering.get('rows'):
                from p6_evm.e1_rollup import e1_extras
                cats = result.get('categories', {})
                ex = e1_extras(engineering['rows'], list(cats.keys()))
                engineering['overall'] = ex['overall']
                engineering['by_trade'] = ex['by_trade']
                engineering['gaps'] = ex['gaps']
                for name, actual in ex['category_actuals'].items():
                    if name in cats:
                        cats[name]['actual_pct'] = actual
            html_content = render_evm_report(result, meta_in, gap=gap, engineering=engineering)
            if preview:
                self._json(200, {'ok': True, 'html': html_content})
                return
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name
            chrome = _find_chrome()
            subprocess.run([
                chrome, '--headless', '--disable-gpu', '--no-sandbox',
                f'--print-to-pdf={os.path.abspath(output_path)}', '--no-pdf-header-footer',
                f'file:///{html_path.replace(os.sep, "/")}',
            ], check=True, capture_output=True)
            os.unlink(html_path)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/report/calendar ───────────────────────────────────────────────
    def _handle_calendar_report(self, body):
        """Calendar Audit PDF (or preview HTML). Reads the stored calendar_audit
        from the DB — no re-parse needed."""
        snapshot_id = body.get('snapshot_id')
        preview     = bool(body.get('preview'))
        output_path = body.get('output_path', '')
        meta_in     = body.get('meta') or {}
        if not preview and not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        ca = db.get_calendar_audit(snapshot_id) if snapshot_id else None
        if not ca:
            self._json(200, {'ok': False, 'error': 'No calendar audit stored for this schedule.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_calendar.report import render_calendar_report
            import subprocess, tempfile
            html_content = render_calendar_report(ca, meta_in)
            if preview:
                self._json(200, {'ok': True, 'html': html_content})
                return
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name
            chrome = _find_chrome()
            subprocess.run([
                chrome, '--headless', '--disable-gpu', '--no-sandbox',
                f'--print-to-pdf={os.path.abspath(output_path)}', '--no-pdf-header-footer',
                f'file:///{html_path.replace(os.sep, "/")}',
            ], check=True, capture_output=True)
            os.unlink(html_path)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/export/calendar_excel ─────────────────────────────────────────
    def _handle_calendar_excel(self, body):
        """Export the primary calendar's Monthly Statistics table to .xlsx."""
        snapshot_id = body.get('snapshot_id')
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        ca = db.get_calendar_audit(snapshot_id) if snapshot_id else None
        if not ca:
            self._json(200, {'ok': False, 'error': 'No calendar audit stored for this schedule.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.xlsx_writer import write_xlsx
            primary = ca.get('primary_calendar_id')
            months = ((ca.get('by_calendar') or {}).get(primary, {}) or {}).get('monthly_stats', [])
            headers = ['Month', 'Working Days', 'Holidays', 'Exceptions', 'Working Hours']
            rows = [[m['label'], m['working_days'], m['holidays'], m['exceptions'], m['working_hours']]
                    for m in months]
            write_xlsx(os.path.abspath(output_path), 'Calendar Monthly Stats', headers, rows)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/geocode ───────────────────────────────────────────────────────
    def _handle_geocode(self, body):
        """Search a place name → coordinates, via OpenStreetMap Nominatim (server-side,
        so it carries a proper User-Agent and dodges browser CORS). Free, no key."""
        q = (body.get('q') or '').strip()
        if not q:
            self._json(200, {'ok': False, 'error': 'Type a place to search.'})
            return
        try:
            import urllib.request, urllib.parse
            url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(
                {'q': q, 'format': 'json', 'limit': 5})
            req = urllib.request.Request(url, headers={'User-Agent': 'nPace-CalendarAudit/1.0'})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode())
            results = [{'name': x.get('display_name'), 'lat': float(x['lat']), 'lon': float(x['lon'])}
                       for x in data]
            self._json(200, {'ok': True, 'results': results})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': f'Search failed (offline?): {exc}'})

    # ── /api/weather ───────────────────────────────────────────────────────
    def _handle_weather(self, body):
        """Compute the Weather Impact for a location. Re-parses the schedule (needs
        construction calendars + milestones), fetches historical/forecast weather,
        and returns the estimate. Saves the location per project. Network failures
        degrade to an empty (zero-impact) estimate rather than an error."""
        lat, lon = body.get('lat'), body.get('lon')
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        if lat is None or lon is None:
            self._json(200, {'ok': False, 'error': 'No project location set.'})
            return
        if not resolved:
            self._json(200, {'ok': False, 'error': 'Schedule not available. Re-import the file.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_calendar.weather import weather_inputs, build_daily_weather, weather_impact
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            data = parse_file(resolved)
            inp = weather_inputs(data)
            if not inp['data_date'] or not inp['project_finish']:
                self._json(200, {'ok': False, 'error': 'Schedule has no usable start/finish dates.'})
                return
            daily, horizon = build_daily_weather(lat, lon, inp['data_date'], inp['project_finish'])
            wx = weather_impact(**inp, daily_weather=daily, forecast_horizon=horizon,
                                thresholds=config.get('weather_thresholds'))
            location = {'lat': lat, 'lon': lon, 'name': body.get('place_name', '')}
            sid = body.get('snapshot_id')
            pid = db.get_project_id_for_snapshot(sid) if sid else None
            if pid:
                db.save_project_settings(pid, {'location': location})
            self._json(200, {'ok': True, 'weather': wx, 'location': location,
                             'offline': not daily})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/calendar/settings ─────────────────────────────────────────────
    def _handle_calendar_settings(self, body):
        """Persist per-project Calendar Audit settings (location / manual shutdowns /
        shutdown reasons) and recompute the calendar audit so the changes show at once."""
        sid = body.get('snapshot_id')
        pid = db.get_project_id_for_snapshot(sid) if sid else None
        if not pid:
            self._json(200, {'ok': False, 'error': 'Open a schedule first.'})
            return
        patch = {k: body[k] for k in ('location', 'manual_shutdowns', 'shutdown_reasons')
                 if body.get(k) is not None}
        settings = db.save_project_settings(pid, patch)
        ca = None
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        if resolved:
            try:
                sys.path.insert(0, resource_path('.'))
                from p6_evm.parser import parse_file
                from p6_calendar import calendar_audit
                with open(resource_path('config.json')) as f:
                    config = json.load(f)
                ca = calendar_audit(parse_file(resolved), config, settings)
                if sid:
                    db.save_calendar_audit(sid, ca)
            except Exception as cexc:
                print(f'[calendar] settings recompute skipped: {cexc}', file=sys.stderr)
        self._json(200, {'ok': True, 'settings': settings, 'calendar_audit': ca})

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
