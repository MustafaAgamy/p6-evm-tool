from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import subprocess
import sys
import tempfile
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
        elif self.path == '/api/ai/settings':
            self._handle_ai_settings_get()
        else:
            self._json(404, {'ok': False, 'error': 'not found'})

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length))
        if self.path == '/api/parse':
            self._handle_parse(body)
        elif self.path == '/api/report':
            self._handle_report(body)
        elif self.path == '/api/compare':
            self._handle_compare(body)
        elif self.path == '/api/compare/corrected-xml':
            self._handle_corrected_xml(body)
        elif self.path == '/api/compare/before-after':
            self._handle_before_after(body)
        elif self.path == '/api/compare/excel':
            self._handle_compare_excel(body)
        elif self.path == '/api/compare/report':
            self._handle_compare_report(body)
        elif self.path == '/api/period/compare':
            self._handle_period_compare(body)
        elif self.path == '/api/period/previous':
            self._handle_period_previous(body)
        elif self.path == '/api/period/trend':
            self._handle_period_trend(body)
        elif self.path == '/api/period/excel':
            self._handle_period_excel(body)
        elif self.path == '/api/period/report':
            self._handle_period_report(body)
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
        elif self.path == '/api/baseline/clear':
            self._handle_baseline_clear(body)
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
        elif self.path == '/api/lag/justification':
            self._handle_lag_justification(body)
        elif self.path == '/api/milestones/save':
            self._handle_milestones_save(body)
        elif self.path == '/api/ai/settings':
            self._handle_ai_settings_set(body)
        elif self.path == '/api/ai-review':
            self._handle_ai_review(body)
        elif self.path == '/api/constructability':
            self._handle_constructability(body)
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

            # Merge the planner's saved lag/lead justifications (held per project) into the
            # register before it is persisted and returned, so re-imports keep the reasons.
            if audit_modules_result is not None:
                try:
                    from p6_audit.modules.lag_lead import apply_justifications
                    lag_mod = (audit_modules_result.get('modules') or {}).get('lag_lead')
                    apply_justifications(lag_mod, db.get_project_settings(pid).get('lag_justifications'))
                except Exception as lag_exc:
                    print(f'[lag] justification merge skipped: {lag_exc}', file=sys.stderr)

                # Milestone Check (gate B): merge the contract-milestone evaluation into
                # the (renamed) Hard Constraints module, plus the baseline's milestone list
                # so the entry screen can offer real activities to match against.
                try:
                    from p6_audit.milestone_check import build_milestone_module
                    from p6_audit.graph import ScheduleGraph
                    mods = audit_modules_result.get('modules') or {}
                    if 'hard_constraints' in mods:
                        mods['hard_constraints'] = build_milestone_module(
                            mods['hard_constraints'], ScheduleGraph(data),
                            db.get_contract_milestones(pid))
                except Exception as mc_exc:
                    print(f'[milestone] attach skipped: {mc_exc}', file=sys.stderr)

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
                safe_result['calendar_settings'] = settings
                db.save_calendar_audit(sid, cal_result)
            except Exception as cal_exc:
                safe_result['calendar_audit'] = None
                safe_result['calendar_settings'] = {}
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

    # ── /api/ai/settings + /api/ai-review ──────────────────────────────────
    def _handle_ai_settings_get(self):
        from p6_ai import settings as ai_settings
        self._json(200, {'ok': True, 'has_key': ai_settings.has_api_key()})

    def _handle_ai_settings_set(self, body):
        from p6_ai import settings as ai_settings
        ai_settings.set_api_key(body.get('api_key', ''))
        self._json(200, {'ok': True, 'has_key': ai_settings.has_api_key()})

    def _handle_ai_review(self, body):
        """AI Constructability Review — opt-in; the only route that calls the cloud.

        Re-parses the baseline (and an optional reference), runs the AI review, and
        returns the report dict. The report carries no `records` key. Every failure
        is reported as {ok:false, error, code} for the UI to surface plainly.
        """
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        if not resolved:
            self._json(200, {'ok': False, 'error': 'Schedule not found — re-import it and try again.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_ai import settings as ai_settings
            from p6_ai.review import run_review
            from p6_ai.client import AiError

            if not ai_settings.has_api_key():
                self._json(200, {'ok': False, 'error': 'No Anthropic API key set.', 'code': 'no_key'})
                return

            data = parse_file(resolved)
            reference_data = None
            ref_path = body.get('reference_path')
            if ref_path and os.path.isfile(ref_path):
                reference_data = parse_file(ref_path)

            try:
                report = run_review(data, ai_settings.get_api_key(),
                                    reference_data=reference_data, cfg=ai_settings.get_config())
            except AiError as e:
                self._json(200, {'ok': False, 'error': str(e), 'code': e.code})
                return
            self._json(200, {'ok': True, 'report': report})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/compare ───────────────────────────────────────────────────────
    def _handle_compare(self, body):
        """Consultant Review — Baseline vs Current Update. Parses a baseline
        (XER/XML) and an update (XML/XER) and returns the comparison report dict:
        driving logic & lag changes, duration changes, change summary, milestones.
        The report carries no `records`; nothing is written to the schedule."""
        baseline_path = body.get('baseline_path', '')
        # The update is the currently-open schedule — resolve original → cached like the
        # other routes, so a project reopened from history (original moved) still compares.
        update_path = db.resolve_xml_path(body.get('update_path', ''), body.get('cached_path'))
        if not baseline_path or not os.path.isfile(baseline_path):
            self._json(200, {'ok': False, 'error': f'Baseline file not found: {baseline_path}'})
            return
        if not update_path:
            self._json(200, {'ok': False, 'error': 'Update schedule not available. Re-import it first.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_compare.report import build_report
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            report = build_report(baseline_path, update_path, config)
            report['baseline_file'] = os.path.basename(baseline_path)
            report['update_file'] = os.path.basename(update_path)
            self._json(200, {'ok': True, 'report': report})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/constructability (rule-based, offline, no AI) ──────────────────
    def _handle_constructability(self, body):
        """Rule-based Constructability Review against the local Knowledge Base.

        Re-parses the schedule, runs the offline engine, returns the report dict
        (no `records` key). `forced_type` lets the UI override the detected sub-type.
        """
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        if not resolved:
            self._json(200, {'ok': False, 'error': 'Schedule not found — re-import it and try again.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_kb.review import run_review
            data = parse_file(resolved)
            report = run_review(data, forced_type=body.get('forced_type'))
            self._json(200, {'ok': True, 'report': report})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/compare/corrected-xml ────────────────────────────────────────
    def _handle_corrected_xml(self, body):
        """Consultant Review — write the corrected 'but-for' XML: revert the selected
        relationship / lag / duration changes back to baseline, leaving every actual
        untouched. P6 does the F9. The update must be a P6 XML export. Nothing is
        written to the user's own schedule — a separate file is produced."""
        baseline_path = body.get('baseline_path', '')
        update_path = db.resolve_xml_path(body.get('update_path', ''), body.get('cached_path'))
        output_path = body.get('output_path', '')
        selected_ids = body.get('selected_ids')   # None → revert everything
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        if not baseline_path or not os.path.isfile(baseline_path):
            self._json(200, {'ok': False, 'error': f'Baseline file not found: {baseline_path}'})
            return
        if not update_path or not os.path.isfile(update_path):
            self._json(200, {'ok': False, 'error': 'Update schedule not available. Re-import it first.'})
            return
        if not update_path.lower().endswith('.xml'):
            self._json(200, {'ok': False, 'error': 'The corrected file is written as P6 XML — re-export the current '
                                                    'update from P6 as an XML file and open it, then try again.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_compare.revert import write_corrected_from_paths
            note = ('Consultant Review — BUT-FOR analysis file. Relationships, lags and durations reverted '
                    'to baseline to reveal the genuine delay after F9 in P6. NOT the official schedule.')
            res = write_corrected_from_paths(
                baseline_path, os.path.abspath(update_path), os.path.abspath(output_path),
                selected_ids=selected_ids, note=note)
            self._json(200, {'ok': True, 'applied': res['applied']})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/compare/before-after ─────────────────────────────────────────
    def _handle_before_after(self, body):
        """Consultant Review — the but-for impact. Given the baseline, the update, and
        the **rescheduled corrected file** (F9-ed in P6, re-exported as XML), returns the
        delay before/after, manufactured days, forecast completion, per-milestone
        before/after, and the consultant recommendation. Delay = metrics.compute's
        finish-milestone float, identical to the EVM tab. Nothing is written."""
        baseline_path = body.get('baseline_path', '')
        update_path = db.resolve_xml_path(body.get('update_path', ''), body.get('cached_path'))
        corrected_path = body.get('corrected_path', '')
        if not baseline_path or not os.path.isfile(baseline_path):
            self._json(200, {'ok': False, 'error': f'Baseline file not found: {baseline_path}'})
            return
        if not corrected_path or not os.path.isfile(corrected_path):
            self._json(200, {'ok': False, 'error': f'Rescheduled corrected file not found: {corrected_path}'})
            return
        if not update_path or not os.path.isfile(update_path):
            self._json(200, {'ok': False, 'error': 'Update schedule not available. Re-import it first.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_compare.impact import before_after_from_paths
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            impact = before_after_from_paths(baseline_path, update_path, corrected_path, config)
            self._json(200, {'ok': True, 'impact': impact})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/compare/excel ────────────────────────────────────────────────
    def _handle_compare_excel(self, body):
        """Export the Consultant Review driving-logic change table to .xlsx.
        Renders from the report dict the client already holds — no re-parse."""
        report = body.get('report') or {}
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_compare.exporters import logic_excel
            from p6_evm.xlsx_writer import write_xlsx
            headers, rows = logic_excel(report)
            write_xlsx(os.path.abspath(output_path), 'Driving Logic Changes', headers, rows)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/compare/report ───────────────────────────────────────────────
    def _handle_compare_report(self, body):
        """Consultant Review PDF (or preview HTML). Renders from the report + optional
        before/after impact the client holds — no re-parse. Chrome headless → PDF."""
        report = body.get('report') or {}
        impact = body.get('impact')
        preview = bool(body.get('preview'))
        output_path = body.get('output_path', '')
        if not preview and not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_compare.exporters import render_html
            html_content = render_html(report, impact)
            if preview:
                self._json(200, {'ok': True, 'html': html_content})
                return
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name
            chrome = _find_chrome()
            # DEVNULL (not PIPE) so a verbose/large Chrome render can't dead-lock on a full
            # pipe buffer — that was the "Export PDF does nothing" hang on big schedules.
            # A timeout turns any remaining hang into a clear error instead of silence.
            subprocess.run([
                chrome, '--headless', '--disable-gpu', '--no-sandbox',
                f'--print-to-pdf={os.path.abspath(output_path)}', '--no-pdf-header-footer',
                f'file:///{html_path.replace(os.sep, "/")}',
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
            os.unlink(html_path)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/period/compare ───────────────────────────────────────────────
    def _handle_period_compare(self, body):
        """Update vs Update — Windows Analysis. Compares the previous update
        (prev_path / prev_cached_path) against the current open schedule (update_path /
        cached_path). Returns the period report: progress vs last period's forecast,
        activity % variance, critical-path movement, buckets, period S-curve. EVM
        numbers reused from metrics.compute so they match the EVM tab. No records."""
        prev_path = db.resolve_xml_path(body.get('prev_path', ''), body.get('prev_cached_path'))
        curr_path = db.resolve_xml_path(body.get('update_path', ''), body.get('cached_path'))
        if not prev_path or not os.path.isfile(prev_path):
            self._json(200, {'ok': False, 'error': 'Previous update not found. Pick the previous period file.'})
            return
        if not curr_path or not os.path.isfile(curr_path):
            self._json(200, {'ok': False, 'error': 'Current update not available. Re-import it first.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_evm.metrics import compute
            from p6_evm.classify import auto_categories, build_wbs_classifier
            from p6_period.report import build_report_from_data
            with open(resource_path('config.json')) as f:
                base_config = json.load(f)

            def parse_and_compute(path):
                data = parse_file(path)
                cfg = dict(base_config)
                cfg['categories'] = auto_categories(data)
                metrics = compute(data, cfg, classifier=build_wbs_classifier(data))
                return data, metrics

            prev_data, prev_m = parse_and_compute(prev_path)
            curr_data, curr_m = parse_and_compute(curr_path)
            report = build_report_from_data(prev_data, curr_data, prev_m, curr_m, base_config)
            report['prev_file'] = os.path.basename(prev_path)
            report['update_file'] = os.path.basename(curr_path)
            self._json(200, {'ok': True, 'report': report})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/period/previous ──────────────────────────────────────────────
    def _handle_period_previous(self, body):
        """Suggest the previous period: the snapshot before the current one for this
        project, so the user can compare against last period in one click."""
        sid = body.get('snapshot_id')
        if not sid:
            self._json(200, {'ok': True, 'previous': None})
            return
        try:
            prev = db.get_prev_snapshot(sid)
            if not prev:
                self._json(200, {'ok': True, 'previous': None})
                return
            fname = os.path.basename(prev.get('original_path') or prev.get('cached_path') or '')
            self._json(200, {'ok': True, 'previous': {
                'snapshot_id': prev['id'],
                'data_date': prev.get('data_date'),
                'cached_path': prev.get('cached_path'),
                'filename': fname,
            }})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/period/trend ─────────────────────────────────────────────────
    def _handle_period_trend(self, body):
        """Milestone finish trend across every stored update of this project (slip
        chart). Reads snapshots from the DB, extracting milestone finishes once."""
        sid = body.get('snapshot_id')
        if not sid:
            self._json(200, {'ok': True, 'trend': {'periods': [], 'series': []}})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_period.trend import milestone_trend
            self._json(200, {'ok': True, 'trend': milestone_trend(sid)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/period/excel ─────────────────────────────────────────────────
    def _handle_period_excel(self, body):
        """Export the Update-vs-Update progress table to .xlsx from the report the
        client holds — no re-parse."""
        report = body.get('report') or {}
        trend = body.get('trend')
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_period.exporters import report_excel
            from p6_evm.xlsx_writer import write_xlsx
            headers, rows = report_excel(report, trend)
            write_xlsx(os.path.abspath(output_path), 'Update vs Update', headers, rows)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/period/report ────────────────────────────────────────────────
    def _handle_period_report(self, body):
        """Update-vs-Update PDF (or preview HTML). Renders from the report (+ optional
        milestone trend) the client holds — no re-parse. Chrome headless → PDF."""
        report = body.get('report') or {}
        trend = body.get('trend')
        sections = body.get('sections')            # None = all; else list of section keys to include
        code_filter = body.get('code_filter')      # {type, value} to limit the activity tables
        critical_style = body.get('critical_style') or 'chain'   # chain | timeline | table (picked on screen)
        critical_mode = body.get('critical_mode') or 'leaf-parent'
        preview = bool(body.get('preview'))
        output_path = body.get('output_path', '')
        if not preview and not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_period.exporters import render_html
            import subprocess, tempfile
            html_content = render_html(report, trend, sections, code_filter, critical_style, critical_mode)
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
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
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
        result['calendar_settings'] = db.get_project_settings(project_id) or {}
        # Re-apply the planner's saved lag/lead justifications over the reloaded register
        # (settings are the live source of truth; the snapshot copy may pre-date an edit).
        try:
            from p6_audit.modules.lag_lead import apply_justifications
            lag_mod = ((result.get('audit_modules') or {}).get('modules') or {}).get('lag_lead')
            apply_justifications(lag_mod, result['calendar_settings'].get('lag_justifications'))
        except Exception:
            pass
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
                from p6_evm.baseline import apply_baseline
                with open(resource_path('config.json')) as f:
                    config = json.load(f)
                data = parse_file(cached_path)
                bl = parse_file(bl_path)
                rep = apply_baseline(data, bl)      # baseline dates + budget
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
                result['baseline_matched'] = rep['matched']
                result['baseline_total'] = rep['total']
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
            write_xlsx(os.path.abspath(output_path), (m.get('name') or 'Schedule Health Review')[:31], headers, rows)
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
        is_summary = (module == '__summary__')
        m = None if is_summary else (mods or {}).get('modules', {}).get(module)
        # For the Summary, prefer the health the client is CURRENTLY showing so the PDF
        # matches the screen exactly (incl. the Milestone Check the user just entered);
        # fall back to the DB roll-up for a re-opened project.
        summary_health = body.get('health') if is_summary else None
        if is_summary and not summary_health:
            summary_health = (mods or {}).get('health')
        if is_summary and not summary_health:
            self._json(200, {'ok': False, 'error': 'No Summary available for this schedule.'})
            return
        if not is_summary and not m:
            self._json(200, {'ok': False, 'error': 'No audit found for this module.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_audit.report import render_module_report, render_summary_report
            import subprocess, tempfile
            html_content = (render_summary_report(summary_health, meta_in, sections=body.get('sections'),
                                                   modules=(mods or {}).get('modules'),
                                                   completion_float=body.get('completion_float'))
                            if is_summary else render_module_report(m, meta_in, sections=body.get('sections')))
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
            from p6_evm.baseline import apply_baseline
            bl = parse_file(bl_path)
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            data = parse_file(resolved)
            report = apply_baseline(data, bl)       # baseline dates + budget, matched by Activity Id
            config['categories'] = auto_categories(data)
            result = compute(data, config, classifier=build_wbs_classifier(data))
            bl_cached = db.cache_xml(bl_path, db.hash_file(bl_path))
            if body.get('snapshot_id'):
                db.save_baseline(body['snapshot_id'], bl_cached)   # remember per project
            matched = report['matched']
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

    # ── /api/baseline/clear ────────────────────────────────────────────────
    def _handle_baseline_clear(self, body):
        """Remove an attached baseline: forget it for this snapshot and recompute the plain
        (no-baseline, approximate) EVM so the UI can revert the numbers."""
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        if not resolved:
            self._json(200, {'ok': False, 'error': 'Schedule not available. Re-import the file.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_evm.metrics import compute
            from p6_evm.classify import auto_categories, build_wbs_classifier
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            if body.get('snapshot_id'):
                db.save_baseline(body['snapshot_id'], None)   # forget the attached baseline
            data = parse_file(resolved)
            config['categories'] = auto_categories(data)
            result = compute(data, config, classifier=build_wbs_classifier(data))
            cats = {n: {'weight': c['weight'], 'planned_pct': c['planned_pct'],
                        'actual_pct': c['actual_pct'], 'bac': c['bac'], 'ac': c['ac'],
                        'activity_count': c['activity_count'], 'overridden': c['overridden']}
                    for n, c in result['categories'].items()}
            self._json(200, {'ok': True,
                             'pv': result['pv'], 'ev': result['ev'], 'spi': result['spi'],
                             'cpi': result['cpi'], 'delay_days': result['delay_days'],
                             'overall_planned_pct': result['overall_planned_pct'],
                             'overall_actual_pct': result['overall_actual_pct'], 'categories': cats})
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
                from p6_evm.baseline import apply_baseline
                apply_baseline(data, parse_file(bl_path))   # baseline dates + budget
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
            pid = db.get_project_id_for_snapshot(snapshot_id) if snapshot_id else None
            weather = (db.get_project_settings(pid) or {}).get('last_weather') if pid else None
            html_content = render_calendar_report(ca, meta_in, weather=weather,
                                                  sections=body.get('sections'))
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
        """Export the full Calendar Audit to .xlsx (#04/#05/#08): one coloured timeline
        sheet per assigned calendar (names inside the day cells) + Exceptions, Comparison,
        Usage and — when a location was set — the Weather tables."""
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
            from p6_evm.xlsx_writer import write_calendar_xlsx
            pid = db.get_project_id_for_snapshot(snapshot_id) if snapshot_id else None
            weather = (db.get_project_settings(pid) or {}).get('last_weather') if pid else None
            write_calendar_xlsx(os.path.abspath(output_path), ca, weather=weather)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/geocode ───────────────────────────────────────────────────────
    def _handle_geocode(self, body):
        """Place name → coordinates (search), OR lat/lon → place name (reverse), via
        OpenStreetMap Nominatim (server-side: proper User-Agent, dodges browser CORS).
        Free, no key. Reverse is used when the user drops/drags a pin on the map."""
        import urllib.request, urllib.parse
        lat, lon = body.get('lat'), body.get('lon')
        try:
            if lat is not None and lon is not None:
                url = 'https://nominatim.openstreetmap.org/reverse?' + urllib.parse.urlencode(
                    {'lat': lat, 'lon': lon, 'format': 'json', 'zoom': 13})
                req = urllib.request.Request(url, headers={'User-Agent': 'nPace-CalendarAudit/1.0'})
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = json.loads(r.read().decode())
                name = data.get('display_name') or f'{float(lat):.4f}, {float(lon):.4f}'
                self._json(200, {'ok': True, 'name': name})
                return
            q = (body.get('q') or '').strip()
            if not q:
                self._json(200, {'ok': False, 'error': 'Type a place to search.'})
                return
            url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(
                {'q': q, 'format': 'json', 'limit': 5})
            req = urllib.request.Request(url, headers={'User-Agent': 'nPace-CalendarAudit/1.0'})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode())
            results = [{'name': x.get('display_name'), 'lat': float(x['lat']), 'lon': float(x['lon'])}
                       for x in data]
            self._json(200, {'ok': True, 'results': results})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': f'Geocode failed (offline?): {exc}'})

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
            sid = body.get('snapshot_id')
            pid = db.get_project_id_for_snapshot(sid) if sid else None
            saved = db.get_project_settings(pid) if pid else {}
            # Stop-work limits: this request's edits win, else the project's saved limits,
            # else the app defaults (rain>=5 / heat>=42 / dust on / wind off).
            thresholds = (body.get('thresholds') or saved.get('weather_thresholds')
                          or config.get('weather_thresholds'))
            data = parse_file(resolved)
            inp = weather_inputs(data)
            if not inp['data_date'] or not inp['project_finish']:
                self._json(200, {'ok': False, 'error': 'Schedule has no usable start/finish dates.'})
                return
            daily, horizon = build_daily_weather(lat, lon, inp['data_date'], inp['project_finish'])
            wx = weather_impact(**inp, daily_weather=daily, forecast_horizon=horizon,
                                thresholds=thresholds)
            location = {'lat': lat, 'lon': lon, 'name': body.get('place_name', '')}
            if pid:
                # Persist location, the edited limits, and the latest weather (so the PDF can include it).
                patch = {'location': location, 'last_weather': wx}
                if body.get('thresholds'):
                    patch['weather_thresholds'] = body['thresholds']
                db.save_project_settings(pid, patch)
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

    # ── /api/lag/justification ──────────────────────────────────────────────
    def _handle_lag_justification(self, body):
        """Save one Lag & Lead justification (keyed by rel_key) for the project. Held in
        project settings so it survives re-imports and reopening. Returns the merged map."""
        sid = body.get('snapshot_id')
        pid = db.get_project_id_for_snapshot(sid) if sid else None
        if not pid:
            self._json(200, {'ok': False, 'error': 'Open a schedule first.'})
            return
        key = (body.get('rel_key') or '').strip()
        if not key:
            self._json(200, {'ok': False, 'error': 'rel_key required'})
            return
        text = (body.get('text') or '').strip()
        current = dict(db.get_project_settings(pid).get('lag_justifications') or {})
        if text:
            current[key] = text
        else:
            current.pop(key, None)      # blanking a reason clears it
        db.save_project_settings(pid, {'lag_justifications': current})
        self._json(200, {'ok': True, 'lag_justifications': current})

    # ── /api/milestones/save ─────────────────────────────────────────────────
    def _handle_milestones_save(self, body):
        """Save the project's contract milestones (gate B) and re-evaluate them against
        the baseline, returning the refreshed Milestone Check module so the review can
        un-gate and show the verdicts at once."""
        sid = body.get('snapshot_id')
        pid = db.get_project_id_for_snapshot(sid) if sid else None
        if not pid:
            self._json(200, {'ok': False, 'error': 'Open a schedule first.'})
            return
        milestones = body.get('milestones') or []
        db.save_contract_milestones(pid, milestones)
        module = None
        health = None
        resolved = db.get_snapshot_xml_path(sid)
        if resolved:
            try:
                sys.path.insert(0, resource_path('.'))
                from p6_evm.parser import parse_file
                from p6_evm.classify import auto_categories
                from p6_audit import audit_modules as run_audit_modules
                from p6_audit.graph import ScheduleGraph
                from p6_audit.milestone_check import build_milestone_module
                from p6_audit.health import schedule_health
                with open(resource_path('config.json')) as f:
                    config = json.load(f)
                data = parse_file(resolved)
                config['categories'] = auto_categories(data)
                am = run_audit_modules(data, config)
                hard = (am.get('modules') or {}).get('hard_constraints')
                module = build_milestone_module(hard, ScheduleGraph(data), milestones)
                # recompute the roll-up with the milestone applied, so the screen (and any
                # Summary PDF built from it) reflect the just-entered contract milestones
                am['modules']['hard_constraints'] = module
                health = schedule_health(am['modules'])
            except Exception as mexc:
                print(f'[milestone] save recompute skipped: {mexc}', file=sys.stderr)
        self._json(200, {'ok': True, 'milestones': milestones, 'milestone_module': module, 'health': health})

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
