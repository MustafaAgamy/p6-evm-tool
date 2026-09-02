from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, date
from utils import resource_path, exe_dir, app_data_dir, APP_NAME, APP_EDITION, APP_TITLE
import db
import report_theme


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
            mime = {'css': 'text/css', 'js': 'application/javascript',
                    'png': 'image/png', 'svg': 'image/svg+xml', 'ico': 'image/x-icon',
                    'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif',
                    'webp': 'image/webp'}.get(ext, 'text/plain')
            self._serve(resource_path(self.path.lstrip('/')), mime)
        elif self.path == '/api/history':
            self._handle_history()
        elif self.path == '/api/ai/settings':
            self._handle_ai_settings_get()
        elif self.path == '/api/kb':
            self._handle_kb_list()
        elif self.path == '/api/kb/knowledge':
            self._handle_kb_knowledge_get()
        elif self.path == '/api/database':
            self._handle_database_list()
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
        elif self.path == '/api/revcompare':
            self._handle_revcompare(body)
        elif self.path == '/api/revcompare/report':
            self._handle_revcompare_report(body)
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
        elif self.path == '/api/critpath/analyze':
            self._handle_critpath_analyze(body)
        elif self.path == '/api/critpath/report':
            self._handle_critpath_report(body)
        elif self.path == '/api/critpath/excel':
            self._handle_critpath_excel(body)
        elif self.path == '/api/update/analyze':
            self._handle_update_analyze(body)
        elif self.path == '/api/update/counts':
            self._handle_update_counts(body)
        elif self.path == '/api/update/scope':
            self._handle_update_scope(body)
        elif self.path == '/api/update/excel':
            self._handle_update_excel(body)
        elif self.path == '/api/update/report':
            self._handle_update_report(body)
        elif self.path == '/api/dashboard':
            self._handle_dashboard(body)
        elif self.path == '/api/narrative':
            self._handle_narrative(body)
        elif self.path == '/api/forecast':
            self._handle_forecast(body)
        elif self.path == '/api/copilot':
            self._handle_copilot(body)
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
        elif self.path == '/api/kb/starter-xml':
            self._handle_kb_starter_xml(body)
        elif self.path == '/api/kb/learned-file':
            self._handle_kb_learned_file(body)
        elif self.path == '/api/database/add':
            self._handle_database_add(body)
        elif self.path == '/api/database/example':
            self._handle_database_example(body)
        elif self.path == '/api/database/download':
            self._handle_database_download(body)
        elif self.path == '/api/kb/knowledge/export':
            self._handle_kb_knowledge_export(body)
        elif self.path == '/api/kb/knowledge/import':
            self._handle_kb_knowledge_import(body)
        elif self.path == '/api/kb/knowledge/import-xer':
            self._handle_kb_import_xer(body)
        elif self.path == '/api/kb/knowledge/enable':
            self._handle_kb_enable(body)
        elif self.path == '/api/kb/knowledge/remove':
            self._handle_kb_remove(body)
        elif self.path == '/api/kb/raw/download':
            self._handle_kb_raw_download(body)
        elif self.path == '/api/constructability/report':
            self._handle_constructability_report(body)
        elif self.path == '/api/constructability/excel':
            self._handle_constructability_excel(body)
        elif self.path == '/api/special/catalog':
            self._handle_special_catalog(body)
        elif self.path == '/api/special/render':
            self._handle_special_render(body)
        elif self.path == '/api/special/pdf':
            self._handle_special_pdf(body)
        elif self.path == '/api/special/doc':
            self._handle_special_doc(body)
        elif self.path == '/api/special/templates/list':
            self._handle_special_templates_list(body)
        elif self.path == '/api/special/templates/save':
            self._handle_special_templates_save(body)
        elif self.path == '/api/special/templates/delete':
            self._handle_special_templates_delete(body)
        elif self.path == '/api/report/manifest':
            self._handle_report_manifest(body)
        elif self.path == '/api/report/render':
            self._handle_report_render(body)
        else:
            self._json(404, {'ok': False, 'error': 'not found'})

    # ── /api/special/* — Special Report ─────────────────────────────────────
    def _special_pid(self, body):
        pid = body.get('project_id')
        if not pid and body.get('snapshot_id'):
            pid = db.get_project_id_for_snapshot(body.get('snapshot_id'))
        return pid

    def _handle_special_catalog(self, body):
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_special import assemble
            pid = self._special_pid(body)
            if not pid:
                self._json(200, {'ok': False, 'error': 'No project loaded.'})
                return
            groups = assemble.catalog(pid, snapshot_id=body.get('snapshot_id'),
                                      inputs=body.get('inputs') or {})
            self._json(200, {'ok': True, 'groups': groups})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _special_html(self, body):
        sys.path.insert(0, resource_path('.'))
        from p6_special import assemble
        import report_theme
        return assemble.build_html(
            self._special_pid(body), body.get('item_ids') or [],
            body.get('report_name') or 'Special Report',
            mode=report_theme.normalize(body.get('theme')),
            meta=body.get('meta') or {}, letterhead=body.get('letterhead') or {},
            inputs=body.get('inputs') or {}, snapshot_id=body.get('snapshot_id'))

    def _handle_special_render(self, body):
        try:
            self._json(200, {'ok': True, 'html': self._special_html(body)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_special_pdf(self, body):
        try:
            output_path = body.get('output_path')
            if not output_path:
                self._json(200, {'ok': False, 'error': 'No output path.'})
                return
            html = self._special_html(body)
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w',
                                             encoding='utf-8') as tmp:
                tmp.write(html)
                html_path = tmp.name
            chrome = _find_chrome()
            out = os.path.abspath(output_path)
            subprocess.run([chrome, '--headless', '--disable-gpu', '--no-sandbox',
                            f'--print-to-pdf={out}', '--no-pdf-header-footer',
                            f'file:///{html_path.replace(os.sep, "/")}'],
                           check=True, capture_output=True)
            os.unlink(html_path)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_special_doc(self, body):
        try:
            output_path = body.get('output_path')
            if not output_path:
                self._json(200, {'ok': False, 'error': 'No output path.'})
                return
            sys.path.insert(0, resource_path('.'))
            from p6_special import assemble
            from p6_special.word_export import save_word_document
            import report_theme
            html = assemble.build_word(
                self._special_pid(body), body.get('item_ids') or [],
                body.get('report_name') or 'Special Report',
                mode=report_theme.normalize(body.get('theme')),
                meta=body.get('meta') or {}, letterhead=body.get('letterhead') or {},
                inputs=body.get('inputs') or {}, snapshot_id=body.get('snapshot_id'))
            save_word_document(html, os.path.abspath(output_path))
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_special_templates_list(self, body):
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_special import templates
            self._json(200, {'ok': True,
                             'templates': templates.list_templates(self._special_pid(body))})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_special_templates_save(self, body):
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_special import templates
            rec = templates.save_template(self._special_pid(body), body.get('template') or {})
            self._json(200, {'ok': True, 'template': rec})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_special_templates_delete(self, body):
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_special import templates
            templates.delete_template(self._special_pid(body), body.get('id'))
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── Static files ───────────────────────────────────────────────────────
    def _serve_index(self):
        try:
            with open(resource_path('ui/index.html'), 'rb') as f:
                html = f.read().decode()
            port = self.server.server_address[1]
            # Inject runtime globals so the UI derives its branding from the
            # single source of truth (utils.APP_*). Any current or future UI
            # feature reads window.__APP_NAME__ / window.__APP_TITLE__ instead
            # of hardcoding the product name.
            assigns = ''.join(
                f'window.{k} = {json.dumps(v)};' for k, v in (
                    ('__SERVER_PORT__', port),
                    ('__APP_NAME__', APP_NAME),
                    ('__APP_EDITION__', APP_EDITION),
                    ('__APP_TITLE__', APP_TITLE),
                )
            )
            brand_script = (
                '<script>' + assigns
                + 'document.title=window.__APP_TITLE__;'
                + 'document.addEventListener("DOMContentLoaded",function(){'
                + 'var e=document.getElementById("app-title");'
                + 'if(e)e.textContent=window.__APP_TITLE__;});'
                + '</script>'
            )
            html = html.replace('</head>', brand_script + '</head>', 1)
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

            # ── Slim activity timeline for the Schedule (Gantt) view ──────────
            # JSON-safe {id,name,wbs,start,finish,pct,critical,milestone} — NOT the
            # heavy/non-serialisable `records`. Only rows with both dates are kept.
            try:
                from p6_evm.metrics import wbs_ancestor_names
                gantt = []
                for r in result['records']:
                    a = r['activity']
                    s, f = a.get('planned_start'), a.get('planned_finish')
                    if not s or not f:
                        continue
                    names = wbs_ancestor_names(a.get('wbs_id'), data.wbs)
                    tf = r.get('total_float')
                    gantt.append({
                        'id':        a.get('id') or '',
                        'name':      a.get('name') or '',
                        'wbs':       ' > '.join(names),
                        'wbs_top':   names[0] if names else 'Ungrouped',
                        'start':     s.isoformat() if hasattr(s, 'isoformat') else str(s),
                        'finish':    f.isoformat() if hasattr(f, 'isoformat') else str(f),
                        'pct':       round((a.get('percent_complete') or 0) * 100),
                        'critical':  tf is not None and tf <= 0,
                        'milestone': a.get('task_type') in ('StartMilestone', 'FinishMilestone'),
                    })
                gantt.sort(key=lambda x: x['start'])
                safe_result['activities'] = gantt
            except Exception as gantt_exc:
                safe_result['activities'] = []
                print(f'[gantt] slim activities skipped: {gantt_exc}', file=sys.stderr)

            # ── WBS summary tree — rolled up to the level that holds activities ──
            # Pre-order list of WBS nodes (with depth) whose subtree contains
            # activities; each carries weighted planned/actual %, an activity count
            # and the rolled-up start/finish, using the same BAC-else-duration
            # weighting as the EVM roll-up. `wbs_main` lists the selectable top-
            # level branches (e.g. Engineering / Construction). Leaf nodes are the
            # WBS that directly hold activities (activities themselves are NOT listed).
            try:
                from collections import defaultdict
                wmap = data.wbs
                any_bac = any((r.get('bac') or 0) > 0 for r in result['records'])

                def _mn(a, b):
                    return b if a is None else (a if b is None else min(a, b))

                def _mx(a, b):
                    return b if a is None else (a if b is None else max(a, b))

                base = lambda: {'n': 0, 'w': 0.0, 'wp': 0.0, 'wa': 0.0,
                                's': None, 'f': None, 'bs': None, 'bf': None}
                bl_by_id = getattr(data, 'baseline_by_id', None) or {}
                direct = defaultdict(base)
                for r in result['records']:
                    a = r['activity']
                    wid = a.get('wbs_id')
                    if wid is None:
                        continue
                    d = direct[wid]
                    d['s'] = _mn(d['s'], a.get('planned_start'))    # current schedule (expected)
                    d['f'] = _mx(d['f'], a.get('planned_finish'))
                    bl = bl_by_id.get(a.get('id'))                  # embedded baseline, when present
                    if bl:
                        d['bs'] = _mn(d['bs'], bl.get('planned_start'))
                        d['bf'] = _mx(d['bf'], bl.get('planned_finish'))
                    if r.get('planned_pct') is None:
                        continue
                    w = (r.get('bac') or 0.0) if any_bac else float(a.get('planned_duration') or 1.0)
                    d['n'] += 1; d['w'] += w
                    d['wp'] += w * r['planned_pct']; d['wa'] += w * (r.get('actual_pct') or 0.0)

                kids = defaultdict(list)
                for wid, node in wmap.items():
                    kids[node.get('parent_object_id')].append(wid)
                roots = [wid for wid in wmap
                         if not wmap[wid].get('parent_object_id') or wmap[wid].get('parent_object_id') not in wmap]

                sub = {}
                def _rollup(wid):
                    t = dict(direct.get(wid) or base())
                    for k in kids.get(wid, []):
                        c = _rollup(k)
                        t['n'] += c['n']; t['w'] += c['w']; t['wp'] += c['wp']; t['wa'] += c['wa']
                        t['s'] = _mn(t['s'], c['s']); t['f'] = _mx(t['f'], c['f'])
                        t['bs'] = _mn(t['bs'], c['bs']); t['bf'] = _mx(t['bf'], c['bf'])
                    sub[wid] = t
                    return t
                for rt in roots:
                    _rollup(rt)

                def _iso(x):
                    return x.date().isoformat() if hasattr(x, 'date') else (str(x)[:10] if x else None)

                wbs_summary = []
                def _emit(wid, depth, parent):
                    t = sub.get(wid) or base()
                    if t['n'] == 0:
                        return
                    childs = [k for k in kids.get(wid, []) if (sub.get(k) or base())['n'] > 0]
                    wbs_summary.append({
                        'id':         str(wid),
                        'parent':     str(parent) if parent is not None else None,
                        'name':       wmap[wid].get('name') or '(WBS)',
                        'depth':      depth,
                        'activities': t['n'],
                        'planned':    round(100 * t['wp'] / t['w'], 1) if t['w'] else None,
                        'actual':     round(100 * t['wa'] / t['w'], 1) if t['w'] else None,
                        'start':          _iso(t['s']),     # expected (current) start
                        'finish':         _iso(t['f']),     # expected (current) finish
                        'baseline_start': _iso(t['bs']),
                        'baseline_finish':_iso(t['bf']),
                        'leaf':       (direct.get(wid) or base())['n'] > 0 and not childs,
                    })
                    for k in sorted(childs, key=lambda x: (wmap[x].get('name') or '').lower()):
                        _emit(k, depth + 1, wid)
                for rt in sorted(roots, key=lambda x: (wmap[x].get('name') or '').lower()):
                    _emit(rt, 0, None)

                # Selectable top-level branches: the activity-bearing roots when
                # there are several, else the activity-bearing children of the sole
                # root (so a single "Project" root exposes Engineering/Construction).
                roots_act = [rt for rt in roots if (sub.get(rt) or base())['n'] > 0]
                if len(roots_act) >= 2:
                    main_ids = roots_act
                elif roots_act:
                    ch = [k for k in kids.get(roots_act[0], []) if (sub.get(k) or base())['n'] > 0]
                    main_ids = ch if len(ch) >= 2 else [roots_act[0]]
                else:
                    main_ids = []
                main_ids = sorted(main_ids, key=lambda x: (wmap[x].get('name') or '').lower())
                safe_result['wbs_main'] = [{'id': str(w), 'name': wmap[w].get('name') or '(WBS)'} for w in main_ids]
                safe_result['wbs_summary'] = wbs_summary
            except Exception as wbs_exc:
                safe_result['wbs_summary'] = []
                safe_result['wbs_main'] = []
                print(f'[wbs] summary skipped: {wbs_exc}', file=sys.stderr)

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

            # NOTE: importing an XER for ANALYSIS no longer adds it to the Knowledge Base
            # (Ibrahim's rule: a project joins the KB only when the user explicitly adds
            # it). Both learning mechanisms — the per-type profile and the generalized
            # sequencing patterns — now run only from the explicit "Add to Knowledge Base"
            # action (see db.add_import), never silently on analysis import.

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

            html_content = render_html(result, meta, theme=report_theme.normalize(body.get('theme')))

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

    # ── /api/update/* — Update Analysis (single file vs its baseline) ───────
    def _handle_update_analyze(self, body):
        """Update Analysis — a single-file read of the current schedule against the baseline
        embedded in it. Returns Time Status, Planned-vs-Actual by code and the Critical Path
        Analyzer. EVM figures reused from metrics.compute so they match the EVM tab. No records."""
        curr_path = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        if not curr_path or not os.path.isfile(curr_path):
            self._json(200, {'ok': False, 'error': 'Schedule not found — re-import it and try again.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_evm.metrics import compute
            from p6_evm.classify import auto_categories, build_wbs_classifier
            from p6_update.analysis import build_report_from_data
            with open(resource_path('config.json')) as f:
                base_config = json.load(f)
            data = parse_file(curr_path)
            cfg = dict(base_config)
            cfg['categories'] = auto_categories(data)
            metrics = compute(data, cfg, classifier=build_wbs_classifier(data))
            summary_level = int(body.get('summary_level', 0) or 0)
            report = build_report_from_data(data, metrics, summary_level=summary_level)
            report['file'] = os.path.basename(curr_path)
            if not report.get('has_baseline'):
                self._json(200, {'ok': False, 'code': 'no_baseline', 'report': report,
                                 'error': 'This update has no baseline inside it. Attach a baseline, then run Update Analysis.'})
                return
            self._json(200, {'ok': True, 'report': report})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_update_counts(self, body):
        """Section 4 — activity counts (Completed / In Progress / Not Started, Planned vs
        Actual) for construction/execution activities, optionally filtered to one activity-code
        value. Re-reads the file so the filter is exact."""
        curr_path = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        code_filter = body.get('code_filter')
        if not curr_path or not os.path.isfile(curr_path):
            self._json(200, {'ok': False, 'error': 'Schedule not found — re-import it and try again.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_update.analysis import activity_counts
            data = parse_file(curr_path)
            counts = activity_counts(data, code_filter=code_filter)
            self._json(200, {'ok': True, 'counts': counts,
                             'code_types': list(getattr(data, 'activity_code_types', []) or [])})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_update_scope(self, body):
        """Section 5 — scope weight for a chosen combination of activity-code dimensions.
        Re-reads the file so the combination is exact; returns weights + recommendation."""
        curr_path = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        types = body.get('types') or []
        if not curr_path or not os.path.isfile(curr_path):
            self._json(200, {'ok': False, 'error': 'Schedule not found — re-import it and try again.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_update.analysis import scope_weights
            data = parse_file(curr_path)
            self._json(200, {'ok': True, 'scope': scope_weights(data, types)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_update_excel(self, body):
        """Export the Update-Analysis report to .xlsx from the report the client holds."""
        report = body.get('report') or {}
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_update.exporters import report_excel
            from p6_evm.xlsx_writer import write_xlsx
            headers, rows = report_excel(report)
            write_xlsx(os.path.abspath(output_path), 'Update Analysis', headers, rows)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_update_report(self, body):
        """Update-Analysis PDF (or preview HTML) — rendered from the report the client holds,
        in the house consultant style. `sections` limits which of the three appear."""
        report = body.get('report') or {}
        sections = body.get('sections')
        code_filter = body.get('code_filter')
        scope_code = body.get('scope_code')
        preview = bool(body.get('preview'))
        output_path = body.get('output_path', '')
        if not preview and not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_update.exporters import render_html
            import subprocess, tempfile
            html_content = render_html(report, sections, code_filter, scope_code,
                                       theme=report_theme.normalize(body.get('theme')))
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

    # ── /api/critpath/* — Critical Path Analyzer (2–3 schedules) ────────────
    def _handle_critpath_analyze(self, body):
        """Critical Path Analyzer. Loads the schedules for the chosen mode and returns the
        comparison report (census, and — later slices — lanes, milestones, float migration,
        dashboard, recommendation). The current open schedule is always 'current'; the
        picked files fill 'previous' and/or 'baseline'. Nothing is written; no records.

        Modes:  two_updates → current + previous ; update_baseline → current + baseline ;
                two_plus_baseline → current + previous + baseline."""
        mode = body.get('mode', 'update_baseline')
        current_path = db.resolve_xml_path(body.get('current_path', ''), body.get('cached_path'))
        if not current_path or not os.path.isfile(current_path):
            self._json(200, {'ok': False, 'error': 'Current schedule not available. Re-import it first.'})
            return
        needs = {'two_updates': ('previous',), 'update_baseline': ('baseline',),
                 'two_plus_baseline': ('previous', 'baseline')}.get(mode)
        if needs is None:
            self._json(200, {'ok': False, 'error': f'Unknown comparison mode: {mode}'})
            return
        paths = {'current': current_path}
        for role in needs:
            p = body.get(f'{role}_path', '')
            if not p or not os.path.isfile(p):
                label = 'previous update' if role == 'previous' else 'baseline'
                self._json(200, {'ok': False, 'error': f'Pick the {label} file to compare against.'})
                return
            paths[role] = p
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_critpath.analysis import build_report
            schedules = {role: parse_file(p) for role, p in paths.items()}
            report = build_report(schedules, mode,
                                  milestone_code=body.get('milestone_code'),
                                  summary_level=int(body.get('summary_level', 0) or 0))
            report['files'] = {role: os.path.basename(p) for role, p in paths.items()}
            self._json(200, {'ok': True, 'report': report})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_critpath_report(self, body):
        """Critical Path Analyzer PDF (or preview HTML). Renders from the report the client
        holds — no re-parse. `sections` = section keys to include (None = all). Chrome
        headless → PDF."""
        report = body.get('report') or {}
        sections = body.get('sections')
        milestone_ids = body.get('milestone_ids')   # limit the driving-path section to these milestones
        preview = bool(body.get('preview'))
        output_path = body.get('output_path', '')
        if not preview and not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_critpath.exporters import render_html
            import subprocess, tempfile
            html_content = render_html(report, sections, milestone_ids,
                                       theme=report_theme.normalize(body.get('theme')))
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

    def _handle_critpath_excel(self, body):
        """Critical Path Analyzer Excel export — from the report the client holds."""
        report = body.get('report') or {}
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_critpath.exporters import to_excel
            to_excel(report, output_path)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/revcompare — Baseline Revision Comparison (Rev.00 vs Rev.01) ───
    def _handle_revcompare(self, body):
        """Baseline Revision Comparison. Parses two assigned baseline revisions and returns
        the neutral comparison report (executive summary, change register, critical path &
        sequence, milestones). Both files are user-assigned — neither is auto-run on import.
        Nothing is written to the DB; the report carries no `records`."""
        rev0_path = body.get('rev0_path', '')
        rev1_path = body.get('rev1_path', '')
        if not rev0_path or not os.path.isfile(rev0_path):
            self._json(200, {'ok': False, 'error': 'Assign the original baseline (Rev.00) file.'})
            return
        if not rev1_path or not os.path.isfile(rev1_path):
            self._json(200, {'ok': False, 'error': 'Assign the revised baseline (Rev.01) file.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_revcompare import build_report
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            report = build_report(rev0_path, rev1_path, config, options=body.get('options'))
            report['rev0']['file'] = os.path.basename(rev0_path)
            report['rev1']['file'] = os.path.basename(rev1_path)
            self._json(200, {'ok': True, 'report': report})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_revcompare_report(self, body):
        """Baseline Revision Comparison PDF (or preview HTML) — rendered from the report the
        client already holds (no re-parse). `sections` limits which sections are printed;
        Chrome headless → PDF when an output path is given."""
        report = body.get('report') or {}
        sections = body.get('sections')
        preview = bool(body.get('preview'))
        output_path = body.get('output_path', '')
        if not preview and not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_revcompare.exporters import render_html
            import subprocess, tempfile
            html_content = render_html(report, meta=body.get('meta'), sections=sections,
                                       theme=report_theme.normalize(body.get('theme')))
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

    # ── /api/kb (Knowledge Base library — browse the standards) ─────────────
    def _handle_kb_list(self):
        """Return the whole Construction Knowledge Base grouped by category for
        the browsable EPS view. Offline, no schedule needed — bundled defaults
        plus the per-user overlay."""
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.kb import load_kb
            from p6_kb.learn import load_all_profiles, learned_entry, has_learning
            entries = load_kb()
            cats, order = {}, []
            for e in entries:
                c = e.get('category', 'Other')
                if c not in cats:
                    cats[c] = []
                    order.append(c)
                cats[c].append(e)
            categories = [{'category': c, 'count': len(cats[c]), 'types': cats[c]} for c in order]
            total = len(entries)
            # "Learned from your projects" — private, local; only types with enough
            # imports to be meaningful. Shown first so the user's own data leads.
            learned = [learned_entry(p) for p in load_all_profiles() if has_learning(p)]
            if learned:
                categories.insert(0, {'category': 'Learned from your projects',
                                      'count': len(learned), 'types': learned, 'learned': True})
                total += len(learned)
            self._json(200, {'ok': True, 'categories': categories, 'total': total})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/kb/starter-xml (export a standard as a P6 starter schedule) ────
    def _handle_kb_starter_xml(self, body):
        """Write a project-type standard as a P6 XML starter-schedule skeleton
        (WBS + activities + logic + durations) the user imports into P6 and F9s.
        Nothing is computed from a real schedule — it is the reference standard
        rendered as P6 XML."""
        forced_type = body.get('type', '')
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.kb import load_kb
            from p6_kb.starter import write_starter_xml
            entry = next((e for e in load_kb() if e.get('type') == forced_type), None)
            if not entry:   # fall back to a learned-from-your-projects standard
                from p6_kb.learn import load_profile, learned_entry, has_learning
                prof = load_profile(forced_type)
                if prof and has_learning(prof):
                    entry = learned_entry(prof)
            if not entry:
                self._json(200, {'ok': False, 'error': f'Unknown project type: {forced_type}'})
                return
            res = write_starter_xml(entry, os.path.abspath(output_path))
            self._json(200, {'ok': True, **res})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/kb/learned-file (download a learned standard as a JSON file) ────
    def _handle_kb_learned_file(self, body):
        """Write a learned standard (recurring activities, durations and WBS the
        tool learned from the user's own imports of this type) to a JSON file."""
        forced_type = body.get('type', '')
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.learn import load_profile, learned_entry, has_learning
            prof = load_profile(forced_type)
            if not prof or not has_learning(prof):
                self._json(200, {'ok': False, 'error': f'No learned data yet for: {forced_type}'})
                return
            entry = learned_entry(prof)
            with open(os.path.abspath(output_path), 'w', encoding='utf-8') as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)
            self._json(200, {'ok': True, 'type': forced_type,
                             'activities': len(entry['activities']), 'wbs': len(entry['wbs'])})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/database (Construction Database — schedules by project type) ───
    def _handle_database_list(self):
        """Every KB type with its contributed files; generated examples are always
        available per type. Offline, no schedule needed."""
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.database import list_database
            self._json(200, {'ok': True, **list_database()})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_database_add(self, body):
        """Contribute the currently-imported schedule to the Construction Database:
        copy it into the per-user library under its detected type and index it. The
        import already fed the learning engine; this keeps the file too."""
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        if not resolved:
            self._json(200, {'ok': False, 'error': 'Schedule not found — re-import it and try again.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_kb.database import add_import
            data = parse_file(resolved)
            rec = add_import(resolved, data, forced_type=body.get('forced_type'))
            if rec is None:
                self._json(200, {'ok': False, 'error': 'Could not identify the project type of this schedule — pick a type in the review and try again.'})
                return
            self._json(200, {'ok': True, **rec})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_database_example(self, body):
        """Generate a downloadable example baseline for a type — a clean reference
        or a 'with typical gaps' one — as P6 XML written to output_path."""
        forced_type = body.get('type', '')
        output_path = body.get('output_path', '')
        gappy = bool(body.get('gappy'))
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.kb import load_kb
            from p6_kb.examples import write_example_xml
            entry = next((e for e in load_kb() if e.get('type') == forced_type), None)
            if not entry:
                self._json(200, {'ok': False, 'error': f'Unknown project type: {forced_type}'})
                return
            res = write_example_xml(entry, os.path.abspath(output_path), gappy=gappy)
            self._json(200, {'ok': True, **res})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_database_download(self, body):
        """Copy a contributed file out of the Construction Database to output_path."""
        forced_type = body.get('type', '')
        filename = body.get('filename', '')
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            import shutil
            from p6_kb.database import contributed_path
            src = contributed_path(forced_type, filename)
            if not src:
                self._json(200, {'ok': False, 'error': 'File not found in the database.'})
                return
            shutil.copy2(src, os.path.abspath(output_path))
            self._json(200, {'ok': True, 'filename': os.path.basename(output_path)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── Constructability Knowledge Base — export / import / provenance ──────
    def _handle_kb_knowledge_get(self):
        """The ONE Knowledge Base: the metadata list of every knowledge project
        (name/type/source/date/enabled/patterns/raw), plus provenance + counts."""
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.pattern_learning import provenance, kb_list
            self._json(200, {'ok': True, 'projects': kb_list(), **provenance()})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_kb_enable(self, body):
        """Turn a KB project's contribution to supporting knowledge on/off."""
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.pattern_learning import set_enabled, kb_list
            set_enabled(body.get('id', ''), bool(body.get('enabled', True)))
            self._json(200, {'ok': True, 'projects': kb_list()})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_kb_remove(self, body):
        """Remove a project from the Knowledge Base."""
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.pattern_learning import remove_project, kb_list
            remove_project(body.get('id', ''))
            self._json(200, {'ok': True, 'projects': kb_list()})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_kb_import_xer(self, body):
        """Import a real project XER/XML straight into the Knowledge Base: parse → tag →
        learn generalized patterns (deduped by project id, supporting-only) and keep the
        raw file. This is how the KB continuously grows from large real projects."""
        input_path = body.get('input_path', '')
        if not input_path:
            self._json(200, {'ok': False, 'error': 'No input path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_kb.model import schedule_view
            from p6_kb.tagging import tag_view
            from p6_kb.resolve import resolve as _resolve_arc
            from p6_kb.pattern_learning import learn_from_view, store_raw, provenance
            import db
            data = parse_file(os.path.abspath(input_path))
            fh = db.hash_file(os.path.abspath(input_path))
            pid = (data.project or {}).get('id', '') or fh
            name = (data.project or {}).get('name', '') or os.path.basename(input_path)
            view = schedule_view(data)
            tag_view(view)
            arc = (_resolve_arc(view) or {}).get('archetype', '')
            rawp = store_raw(os.path.abspath(input_path), pid, name, fh)
            learn_from_view(view, pid, project_type=arc, label=name, file_hash=fh,
                            source='user', raw=(os.path.basename(rawp) if rawp else ''))
            from p6_kb.pattern_learning import kb_list
            self._json(200, {'ok': True, 'project': name,
                             'activities': view.get('activity_count', 0),
                             'projects': kb_list(), **provenance()})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_kb_raw_download(self, body):
        """Copy a retained raw project file out to output_path (level-1 backup)."""
        filename = body.get('filename', '')
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            import shutil
            from p6_kb.pattern_learning import raw_file_path
            src = raw_file_path(filename)
            if not src:
                self._json(200, {'ok': False, 'error': 'Raw project file not found.'})
                return
            shutil.copy2(src, os.path.abspath(output_path))
            self._json(200, {'ok': True, 'filename': os.path.basename(output_path)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_kb_knowledge_export(self, body):
        """Write the learned knowledge to a portable, project-agnostic knowledge file
        (generalized concepts + provenance only — never raw activity/WBS text)."""
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.pattern_learning import export_knowledge
            data = export_knowledge()
            with open(os.path.abspath(output_path), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            self._json(200, {'ok': True, 'projects': data.get('projects_count', 0),
                             'filename': os.path.basename(output_path)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_kb_knowledge_import(self, body):
        """Merge a knowledge file into the KB — deduped by project, generalized-only
        (raw-looking entries are dropped). Contributes to future supporting knowledge."""
        input_path = body.get('input_path', '')
        if not input_path:
            self._json(200, {'ok': False, 'error': 'No input path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.pattern_learning import import_knowledge, provenance
            with open(os.path.abspath(input_path), encoding='utf-8') as f:
                data = json.load(f)
            result = import_knowledge(data)
            self._json(200, {'ok': True, 'result': result, **provenance()})
        except ValueError as exc:
            self._json(200, {'ok': False, 'error': f'Not a valid knowledge file: {exc}'})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/constructability/excel ────────────────────────────────────────
    def _handle_constructability_excel(self, body):
        """Export the Constructability findings to .xlsx from the report dict the
        client holds — no re-parse."""
        report = body.get('report') or {}
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.exporters import findings_excel
            from p6_evm.xlsx_writer import write_xlsx
            headers, rows = findings_excel(report)
            write_xlsx(os.path.abspath(output_path), 'Constructability Findings', headers, rows)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── Global Print-Preview framework: manifest + unified render/PDF ──────
    def _handle_report_manifest(self, body):
        """Return the Report-Contents component list for a feature + its report dict.

        The client holds the report already (no re-parse); this just tells the selector
        which sections exist, their type, default state and whether they have data."""
        feature = body.get('feature', '')
        report = body.get('report') or {}
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_report import get_spec, manifest
            spec = get_spec(feature, report)
            if spec is None:
                self._json(200, {'ok': False, 'error': f'Unknown report feature: {feature}'})
                return
            self._json(200, {'ok': True, 'feature': feature, 'title': spec.title,
                             'subtitle': spec.subtitle, 'components': manifest(spec, report)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_report_render(self, body):
        """The ONE assembler behind Preview == PDF == Print.

        Given a feature, its report dict and the user's selection (ids + order), build
        exactly one HTML document. With no ``output_path`` → return that HTML for the
        on-screen preview. With ``output_path`` → Chrome headless prints the SAME HTML
        to PDF. The preview and the PDF are therefore the identical document."""
        feature = body.get('feature', '')
        report = body.get('report') or {}
        selected_ids = body.get('selected_ids')          # None → the spec defaults
        order = body.get('order')
        output_path = body.get('output_path', '')
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_report import build_document, get_spec
            spec = get_spec(feature, report)
            if spec is None:
                self._json(200, {'ok': False, 'error': f'Unknown report feature: {feature}'})
                return
            html_content = build_document(spec, report, selected_ids, order,
                                          theme=report_theme.normalize(body.get('theme')))
            if not output_path:
                self._json(200, {'ok': True, 'html': html_content})
                return
            self._html_to_pdf(html_content, output_path)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _html_to_pdf(self, html_content, output_path):
        """Shared HTML→PDF via Chrome headless (same pipeline as every report)."""
        import subprocess
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
            tmp.write(html_content)
            html_path = tmp.name
        try:
            chrome = _find_chrome()
            subprocess.run([
                chrome, '--headless', '--disable-gpu', '--no-sandbox',
                f'--print-to-pdf={os.path.abspath(output_path)}', '--no-pdf-header-footer',
                f'file:///{html_path.replace(os.sep, "/")}',
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        finally:
            try:
                os.unlink(html_path)
            except OSError:
                pass

    # ── /api/constructability/report ───────────────────────────────────────
    def _handle_constructability_report(self, body):
        """Constructability Review PDF from the report dict the client holds — no
        re-parse. Chrome headless → PDF (same pipeline as the consultant report)."""
        import subprocess
        import tempfile
        report = body.get('report') or {}
        output_path = body.get('output_path', '')
        preview = bool(body.get('preview'))   # return HTML for on-screen print preview, no PDF
        if not preview and not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.exporters import render_html
            html_content = render_html(report, theme=report_theme.normalize(body.get('theme')))
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
            html_content = render_html(report, impact, theme=report_theme.normalize(body.get('theme')))
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
            html_content = render_html(report, trend, sections, code_filter, critical_style, critical_mode,
                                       theme=report_theme.normalize(body.get('theme')))
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
            _theme = report_theme.normalize(body.get('theme'))
            html_content = (render_summary_report(summary_health, meta_in, sections=body.get('sections'),
                                                   modules=(mods or {}).get('modules'),
                                                   completion_float=body.get('completion_float'), theme=_theme)
                            if is_summary else render_module_report(m, meta_in, sections=body.get('sections'), theme=_theme))
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
            html_content = render_evm_report(result, meta_in, gap=gap, engineering=engineering,
                                             theme=report_theme.normalize(body.get('theme')),
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
                                                  sections=body.get('sections'),
                                                  theme=report_theme.normalize(body.get('theme')))
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
    def _handle_copilot(self, body):
        """AI Copilot · TIA — the deterministic, offline core (Time-Impact Analysis +
        prioritised insights) from the already-computed result, reusing the saved
        weather estimate. `has_key` tells the UI whether the optional AI narrative
        (the key-gated AI review) can be offered."""
        try:
            from p6_evm.copilot import build_copilot
            result = body.get('result')
            weather = None
            snap = body.get('snapshot_id')
            if snap is not None:
                pid = db.snapshot_project_id(snap)
                if pid is not None:
                    weather = (db.get_project_settings(pid) or {}).get('last_weather')
                    if not result:
                        result = db.get_project_result(pid)
            if not result:
                self._json(200, {'ok': False, 'error': 'No project loaded — import a schedule first.'})
                return
            has_key = False
            try:
                from p6_ai import settings as ai_settings
                has_key = bool(ai_settings.has_api_key())
            except Exception:
                has_key = False
            self._json(200, {'ok': True, 'has_key': has_key, **build_copilot(result, weather)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_forecast(self, body):
        """Weather → Forecast: finish-date scenarios from the schedule's own
        figures + the weather impact Calendar Audit already computed (reused from
        project settings). Prefers the client result (it carries the finish dates)."""
        try:
            from p6_evm.forecast import build_forecast
            result = body.get('result')
            weather = None
            snap = body.get('snapshot_id')
            if snap is not None:
                pid = db.snapshot_project_id(snap)
                if pid is not None:
                    weather = (db.get_project_settings(pid) or {}).get('last_weather')
                    if not result:
                        result = db.get_project_result(pid)
            if not result:
                self._json(200, {'ok': False, 'error': 'No project loaded — import a schedule first.'})
                return
            self._json(200, {'ok': True, **build_forecast(result, weather)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_narrative(self, body):
        """Baseline Narrative: a deterministic status narrative built from the
        already-computed result. Prefers the DB result for the given snapshot
        (the read path); falls back to the client-supplied result."""
        try:
            from p6_evm.narrative import build_narrative
            result = None
            snap = body.get('snapshot_id')
            if snap is not None:
                pid = db.snapshot_project_id(snap)
                if pid is not None:
                    result = db.get_project_result(pid)
            if result is None:
                result = body.get('result')
            if not result:
                self._json(200, {'ok': False, 'error': 'No project loaded — import a schedule first.'})
                return
            self._json(200, {'ok': True, **build_narrative(result)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_dashboard(self, body):
        """Professional Dashboard read-model: the portfolio (latest snapshot per
        project) + the active project's snapshot trend. DB-only, no re-parse."""
        try:
            snap = body.get('snapshot_id')
            data = db.get_dashboard(active_snapshot_id=snap)
            self._json(200, {'ok': True, **data})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

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
