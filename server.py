from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, date
from utils import resource_path, exe_dir, app_data_dir, APP_NAME, APP_EDITION, APP_TITLE, APP_VERSION
from utils import APP_RELEASE_NOTES
import db
import report_theme
import app_startup          # startup log + readiness handshake (black-screen fixes)
import ui_prefs             # screen preferences kept across restarts (<app data>/ui_prefs.json)


def _fmt_meta_date(v):
    """Render a date-ish value ('2026-02-09', a datetime, or an already-human string)
    as '09 Feb 2026'; pass anything unparseable through unchanged."""
    if v in (None, ''):
        return None
    if isinstance(v, (datetime, date)):
        return v.strftime('%d %b %Y')
    s = str(v).strip()
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00')).strftime('%d %b %Y')
    except ValueError:
        pass
    for fmt in ('%Y-%m-%d', '%d %b %Y', '%d-%b-%Y', '%m/%d/%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%d %b %Y')
        except ValueError:
            continue
    return s


def _with_parts(html):
    """A report's PREVIEW HTML with the picker's second level filled in (owner comment 1): inside
    every section the renderer marks (data-sec), each table / chart / tile group / sub-headed
    block becomes a tickable part — unless the renderer marked its own parts. Only attributes
    are added, so the report looks the same; on any doubt the HTML comes back unchanged."""
    try:
        sys.path.insert(0, resource_path('.'))
        from p6_export.auto_parts import annotate
        return annotate(html)
    except Exception:
        return html


def _excel_meta(title, src=None, snapshot_id=None, **extra):
    """The uniform Excel header/context block passed to the shared writer.

    Every export opens self-explaining: "<APP_NAME> — <title>" over a grey context
    line of Project · Data date · [extras] · Generated. Project/data-date are pulled
    from whatever common keys the feature's report/result dict uses (a nested ``meta``
    dict is also consulted); when they're absent and `snapshot_id` is given, they're
    looked up from the DB so even DB-read exports name their project. Anything still
    missing is simply omitted. `extra` keyword pairs (e.g. baseline='Rev 3',
    period='Aug → Sep') are inserted before Generated.
    """
    src = src or {}
    meta = src.get('meta') if isinstance(src.get('meta'), dict) else {}

    def pick(*keys):
        for k in keys:
            for d in (src, meta):
                v = d.get(k)
                if v not in (None, ''):
                    return v
        return None

    project = pick('project', 'project_name', 'projectName', 'project_title')
    data_date = pick('data_date', 'dataDate', 'data_date_str', 'date')
    if snapshot_id is not None and (not project or not data_date):
        try:
            with db.get_conn() as conn:
                row = conn.execute(
                    '''SELECT p.name AS project_name, s.data_date AS data_date
                       FROM snapshots s JOIN projects p ON p.id = s.project_id
                       WHERE s.id = ?''', (snapshot_id,)).fetchone()
            if row:
                project = project or row['project_name']
                data_date = data_date or row['data_date']
        except Exception:
            pass                                          # a missing project name is non-fatal

    ctx = []
    if project:
        ctx.append(('Project', str(project)))
    dd = _fmt_meta_date(data_date)
    if dd:
        ctx.append(('Data date', dd))
    for k, v in extra.items():
        if v not in (None, ''):
            ctx.append((k.replace('_', ' ').capitalize(), str(v)))
    ctx.append(('Generated', datetime.now().strftime('%d %b %Y')))
    return {'app': APP_NAME, 'title': title, 'context': ctx}


def _schedule_for(path, body=None, snapshot_key='snapshot_id', cached_key='cached_path',
                  fallback_baseline=None):
    """The open schedule with its baseline resolved the ONE way every feature uses
    (p6_evm.baseline): embedded in the file, else the baseline attached for this snapshot /
    file (Earned Value or Update Analysis "Attach baseline"), else the file's own Planned dates
    (flagged data.baseline_source='self'). XER and XML therefore give the same result."""
    sys.path.insert(0, resource_path('.'))
    from p6_evm.baseline import attached_baseline_for, load_schedule
    body = body or {}
    attached = (attached_baseline_for(path, body.get(snapshot_key), body.get(cached_key))
                or fallback_baseline)
    return load_schedule(path, attached)


def _prodintel_excel_sections(r):
    """Build (name, headers, rows) sheets from a Productivity Intelligence result."""
    ctx = r.get('context') or {}
    hasq = r.get('has_quantity')
    roll = r.get('rollup') or {}
    comps = r.get('components') or []
    shift = ctx.get('shift_hours') or 8
    dash = lambda x: x if x is not None else '—'

    summ = [['Item', r.get('item')], ['Discipline', r.get('discipline')], ['System', r.get('system')],
            ['Project type', ctx.get('Project type')], ['Location', ctx.get('Location')],
            ['Methodology', ctx.get('Methodology')], ['Shift (hr/day)', shift]]
    if hasq:
        summ += [['Quantity', '%s %s' % (r.get('quantity'), r.get('primary_unit') or '')],
                 ['Total man-hours', roll.get('total_mh')],
                 ['Estimated duration (days)', roll.get('duration_days')],
                 ['Controlling component', roll.get('controlling_component')],
                 ['Blended rate (MH/%s)' % (r.get('primary_unit') or ''), roll.get('blended_mh_per_primary')]]
    # what each setting did to the rate (owner comment 37): the planner's own factor, a factor the
    # library item carries with evidence, or none — the same lines as the screen's ledger
    for row in (r.get('context_ledger') or []):
        if not (row.get('choice') or row.get('applied')):
            continue
        if row.get('applied') or row.get('source') == 'user':
            txt = 'x%s — %s' % (row.get('multiplier'), row.get('evidence') or '')
        else:
            txt = row.get('evidence') or 'not adjusted'
        summ.append(['Factor · %s (%s)' % (row.get('factor'), row.get('choice') or '—'), txt])
    if r.get('context_net') not in (None, 1, 1.0):
        summ.append(['All factors together', 'x%s on man-hours; output per day ÷ %s' % (r.get('context_net'), r.get('context_net'))])
    if r.get('project_type_applies') is False:
        summ.append(['Note', 'This work item is not normally part of %s projects' % (ctx.get('Project type') or '')])
    summ += [['Overall confidence', r.get('overall_confidence')]]

    prod_h = ['Work component', 'Unit', 'Productivity rate (MH/unit)', 'Output/day', 'Library norm (MH/unit)', 'Crew', 'Quantity', 'Man-hours']
    prod_r = []
    for c in comps:
        rate = c.get('rate') or {}
        crew = ', '.join('%sx %s' % (g.get('count'), g.get('trade')) for g in (c.get('gang') or []))
        prod_r.append([c.get('name'), c.get('unit'), dash(rate.get('mh_per_unit')),
                       ('%s %s' % (rate.get('output_per_day'), rate.get('output_unit') or '')) if rate.get('output_per_day') else '—',
                       dash(rate.get('mh_per_unit_base', rate.get('mh_per_unit'))),
                       crew or '—', dash(c.get('component_qty')) if hasq else '—',
                       dash(c.get('man_hours')) if hasq else '—'])

    labour, equip, material = {}, {}, {}
    for c in comps:
        if not c.get('rate'):
            continue
        n = c.get('n_gangs') or 1
        gp = c.get('gang_persons') or 0
        for g in (c.get('gang') or []):
            cur = labour.setdefault(g.get('trade'), {'persons': 0, 'mh': 0.0})
            cur['persons'] += (g.get('count') or 0) * n
            if hasq and c.get('man_hours') and gp:
                cur['mh'] += c['man_hours'] * (g.get('count') or 0) / gp
        for e in (c.get('equipment') or []):
            if e.get('name') not in equip:
                hrs = round(c['duration_days'] * shift) if (hasq and c.get('duration_days')) else None
                equip[e.get('name')] = 'shared' if 'shar' in (e.get('name') or '').lower() else (hrs if hrs is not None else '—')
        for m in (c.get('material') or []):
            q = (c.get('component_qty') or 0) * m['qty_per_unit'] if (hasq and c.get('component_qty') and m.get('qty_per_unit') is not None) else None
            cur = material.setdefault(m.get('name'), {'unit': m.get('unit'), 'qty': 0.0, 'known': False})
            if q is not None:
                cur['qty'] += q
                cur['known'] = True

    res_r = []
    for t, v in labour.items():
        res_r.append(['Labour', t, v['persons'], 'persons' + (' · %d MH' % round(v['mh']) if v['mh'] else '')])
    for name, val in equip.items():
        res_r.append(['Equipment', name, val, 'h' if isinstance(val, (int, float)) else ''])
    for name, val in material.items():
        res_r.append(['Material', name, (round(val['qty']) if val['known'] else '—'), (val['unit'] or '').split('/')[0]])

    sections = [('Summary', ['Field', 'Value'], summ),
                ('Productivity', prod_h, prod_r),
                ('Resources', ['Category', 'Resource', 'Amount', 'Unit'], res_r)]
    if hasq:
        p6_r = []
        for t, v in labour.items():
            p6_r.append([t, 'Labor', '%d MH' % round(v['mh']), '%d h/d' % (v['persons'] * shift)])
        for name, val in equip.items():
            p6_r.append([name, 'Nonlabor', ('shared' if val == 'shared' else ('%s h' % val if isinstance(val, (int, float)) else '—')), 'per method'])
        for name, val in material.items():
            if val['known']:
                p6_r.append([name, 'Material', '%s %s' % (round(val['qty']), (val['unit'] or '').split('/')[0]), '—'])
        if p6_r:
            sections.append(('Assign in P6', ['Resource', 'P6 type', 'Budgeted units', 'Units/time'], p6_r))
    # shape into the shared write_sections_xlsx contract: one sheet per section, one titled block each
    return [{'name': n, 'blocks': [{'title': n, 'headers': h, 'rows': rows}]} for (n, h, rows) in sections]


# ── Project Setup (EVM category weights + Actual Cost) ─────────────────────
def clean_evm_setup(weights, actual_cost):
    """Validate Project Setup before it is saved: {'weights': {category: fraction 0–1},
    'actual_cost': number >= 0 | None}. Raises ValueError with a plain message."""
    import math
    out = {}
    if weights is not None and not isinstance(weights, dict):
        raise ValueError('Category weights were not understood.')
    for name, w in (weights or {}).items():
        if not isinstance(name, str) or not name or len(name) > 200:
            raise ValueError('A category name was not understood.')
        if isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w):
            raise ValueError(f'The weight for {name} is not a number.')
        if w < 0 or w > 1:
            raise ValueError(f'The weight for {name} must be between 0% and 100%.')
        out[name] = float(w)
    if len(out) > 200:
        raise ValueError('Too many categories.')
    ac = None
    if actual_cost is not None:
        if (isinstance(actual_cost, bool) or not isinstance(actual_cost, (int, float))
                or not math.isfinite(actual_cost)):
            raise ValueError('Actual Cost is not a number.')
        if actual_cost < 0:
            raise ValueError('Actual Cost cannot be negative.')
        ac = float(actual_cost)
    return {'weights': out, 'actual_cost': ac}


# ── online-service messages (Bad Weather / place search) ───────────────────────
def _weather_download_gap(net, daily, climate_samples):
    """The plain message when the weather the estimate NEEDS could not be downloaded, else
    None. `net` is filled by p6_calendar.weather.build_daily_weather: offline → nothing
    reached Open-Meteo; history_needed → dates after the forecast horizon exist (they can
    only come from the climate history)."""
    from utils import network_error_message
    errs = (net or {}).get('errors') or {}
    if (net or {}).get('offline'):
        return network_error_message(errs.get('forecast') or OSError('offline'),
                                     'Open-Meteo (the weather service)',
                                     needs='the weather estimate') + (
            ' Your location, site type and limits are saved; the last estimate (if any) is kept.')
    if (net or {}).get('history_needed') and not climate_samples:
        if errs.get('history') is not None:
            why = network_error_message(errs['history'], 'Open-Meteo (the weather history)',
                                        needs='the climate history')
        else:
            why = 'Open-Meteo returned no weather history for this location.'
        return why + ' The estimate needs it for the dates after the 16-day forecast, so no estimate was made.'
    if not (net or {}).get('history_needed') and not daily:
        if errs.get('forecast') is not None:
            return network_error_message(errs['forecast'], 'Open-Meteo (the weather forecast)',
                                         needs='the weather forecast') + ' No estimate was made.'
        return 'Open-Meteo returned no forecast for this location — no estimate was made.'
    return None


_NOMINATIM = 'https://nominatim.openstreetmap.org/'


def _nominatim_get(endpoint, params, timeout=10):
    """One OpenStreetMap Nominatim call ('search' | 'reverse') → parsed JSON. Raises on any
    network / HTTP / parse failure (the caller turns it into a plain message). The honest
    User-Agent comes from the brand constants (Nominatim's usage policy requires one).
    utils.open_url gives up CONNECTING after utils.CONNECT_TIMEOUT, so a black-holed network
    is reported in seconds rather than holding the search spinner.
    Names come back in English (accept-language=en, R2 S8): without it Nominatim answers in
    the local script (e.g. Arabic for Saudi sites), which then showed on the English
    Bad Weather screen and PDF."""
    import urllib.parse
    import urllib.request
    import utils
    params = {**params, 'accept-language': 'en'}
    url = _NOMINATIM + endpoint + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': utils.USER_AGENT,
                                               'Accept-Language': 'en'})
    with utils.open_url(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _parse_coordinates(text):
    """'26.9598, 49.5687' / '26.9598 49.5687' → (lat, lon), or None. Lets the planner set the
    site location with no internet (typed coordinates need no place search)."""
    import re
    m = re.fullmatch(r'\s*([-+]?\d{1,2}(?:\.\d+)?)\s*[,;\s]\s*([-+]?\d{1,3}(?:\.\d+)?)\s*', text or '')
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    return None


def _weather_partial_gaps(net):
    """What the estimate ran WITHOUT (listed with the source reference on screen + PDF)."""
    from utils import network_error_message
    errs = (net or {}).get('errors') or {}
    gaps = []
    if errs.get('forecast') is not None:
        gaps.append('Live forecast unavailable (' + network_error_message(
            errs['forecast'], 'Open-Meteo forecast').rstrip('.') +
            ') — the next ~16 days use the climate history as well.')
    if errs.get('dust') is not None:
        gaps.append('Dust forecast unavailable (' + network_error_message(
            errs['dust'], 'Open-Meteo air-quality').rstrip('.') +
            ') — sandstorm days in the next 5 days are not counted.')
    return gaps


class _Encoder(json.JSONEncoder):
    """Handle datetime/date objects that metrics.py returns in data_date."""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


# ── Run stages (owner comment 36: an honest Run bar on long waits) ────────────
# A long Run (read two or three schedules, then compare) names the step it is really on, so
# the feature's Run bar can say "Reading Rev.01 — <file>" and move through that step's share
# of the bar instead of one long guess. The page sends a `run_id` with its request and polls
# GET /api/run/stage?id=<run_id> while it waits. In memory only — nothing is stored.
_RUN_STAGES = {}
_PARSE_MB_PER_S = 16.0      # measured: P6 XML and XER are both read at ~16-18 MB/s


def _parse_secs(path):
    """Estimated seconds to read a schedule file (its size at the measured read rate)."""
    try:
        return os.path.getsize(path) / 1e6 / _PARSE_MB_PER_S
    except OSError:
        return 1.0


class _RunStages:
    def __init__(self, body, steps):
        """steps = [(label, estimated seconds)] in order; each step owns its share of the bar."""
        self.id = str((body or {}).get('run_id') or '')[:80]
        secs = [max(0.05, float(e or 0)) for _, e in steps]
        total = sum(secs) or 1.0
        self.bands, acc = [], 0.0
        for (label, _), e in zip(steps, secs):
            self.bands.append({'label': label, 'from': round(acc / total, 4),
                               'to': round((acc + e) / total, 4), 'est_s': round(e, 2)})
            acc += e

    def enter(self, i):
        if self.id and 0 <= i < len(self.bands):
            _RUN_STAGES[self.id] = dict(self.bands[i], step=i + 1, steps=len(self.bands))

    def close(self):
        _RUN_STAGES.pop(self.id, None)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # silence request logs

    def do_GET(self):
        if self.path.split('?', 1)[0] == '/api/health':        # startup readiness probe
            self._handle_app_health()
        elif self.path.split('?', 1)[0] in ('/', '/index.html'):
            self._serve_index()
        elif self.path.startswith('/ui/'):
            _p = self.path.split('?', 1)[0]                   # a ?v= query never breaks the MIME type
            ext = _p.rsplit('.', 1)[-1]
            mime = {'css': 'text/css', 'js': 'application/javascript',
                    'html': 'text/html',
                    'png': 'image/png', 'svg': 'image/svg+xml', 'ico': 'image/x-icon',
                    'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif',
                    'webp': 'image/webp'}.get(ext, 'text/plain')
            self._serve(resource_path(_p.lstrip('/')), mime)
        elif self.path == '/api/history':
            self._handle_history()
        elif self.path.split('?', 1)[0] == '/api/ui-prefs':      # saved screen preferences
            self._handle_ui_prefs_get()
        elif self.path == '/api/graphics-mode':                  # Help: Safe graphics switch
            self._json(200, {'ok': True, **app_startup.graphics_status()})
        elif self.path == '/api/ai/settings':
            self._handle_ai_settings_get()
        elif self.path == '/api/kb':
            self._handle_kb_list()
        elif self.path == '/api/kb/knowledge':
            self._handle_kb_knowledge_get()
        elif self.path == '/api/kb/playbooks':
            self._handle_kb_playbooks()
        elif self.path == '/api/database':
            self._handle_database_list()
        elif self.path == '/api/prodintel/tree':
            self._handle_prodintel_tree()
        elif self.path == '/api/chat/library':
            self._handle_chat_library()
        elif self.path == '/api/chat/library2':
            self._handle_chat_library2()
        elif self.path == '/api/chat/status':
            self._handle_chat_status()
        elif self.path == '/api/report/pagination':
            # the ONE shared page-composition layer (report_theme) for client-composed docs
            self._json(200, {'ok': True, 'css': report_theme.pagination_css(),
                             'script': report_theme.pagination_script()})
        elif self.path.startswith('/api/run/stage'):
            from urllib.parse import urlparse, parse_qs
            rid = (parse_qs(urlparse(self.path).query).get('id') or [''])[0]
            self._json(200, {'ok': True, 'stage': _RUN_STAGES.get(rid)})
        else:
            self._json(404, {'ok': False, 'error': 'not found'})

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length))
        if self.path == '/api/client-log':                 # page startup guard -> startup log
            self._json(200, {'ok': True, 'kind': app_startup.client_log(body)['kind']})
            return
        if self.path == '/api/ui-prefs':                   # ui/prefs_bridge.js -> ui_prefs.json
            self._handle_ui_prefs_post(body)
            return
        if self.path == '/api/graphics-mode':              # Help: Safe graphics switch
            self._handle_graphics_mode_post(body)
            return
        if self.path == '/api/db/recover':                 # S3: set a damaged history DB aside
            self._handle_db_recover()
            return
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
        elif self.path == '/api/oos/validate':
            self._handle_oos_validate(body)
        elif self.path == '/api/oos/corrected-file':
            self._handle_oos_corrected(body)
        elif self.path == '/api/prodintel/query':
            self._handle_prodintel_query(body)
        elif self.path == '/api/prodintel/excel':
            self._handle_prodintel_excel(body)
        elif self.path == '/api/dangling/validate':
            self._handle_dangling_validate(body)
        elif self.path == '/api/dangling/corrected-file':
            self._handle_dangling_corrected(body)
        elif self.path == '/api/health/recompute':
            self._handle_health_recompute(body)
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
        elif self.path == '/api/evm/excel':
            self._handle_evm_excel(body)
        elif self.path == '/api/revcompare/excel':
            self._handle_revcompare_excel(body)
        elif self.path == '/api/copilot/excel':
            self._handle_copilot_excel(body)
        elif self.path == '/api/dash/excel':
            self._handle_dash_excel(body)
        elif self.path == '/api/special/excel':
            self._handle_special_excel(body)
        elif self.path == '/api/narrative/excel':
            self._handle_narrative_excel(body)
        elif self.path == '/api/overview/excel':
            self._handle_overview_excel(body)
        elif self.path == '/api/wbs/excel':
            self._handle_wbs_excel(body)
        elif self.path == '/api/schedule/excel':
            self._handle_schedule_excel(body)
        elif self.path == '/api/update/report':
            self._handle_update_report(body)
        elif self.path == '/api/narrative':
            self._handle_narrative(body)
        elif self.path == '/api/narrative/setup':           # Narrative project setup (DB)
            self._handle_narrative_setup(body)
        elif self.path == '/api/narrative/choices':
            self._handle_narrative_choices(body)
        elif self.path == '/api/narrative/docx':
            self._handle_narrative_docx(body)
        elif self.path == '/api/narrative/pdf':
            self._handle_narrative_pdf(body)
        elif self.path == '/api/narrative/html':
            self._handle_narrative_html(body)
        elif self.path == '/api/copilot':
            self._handle_copilot(body)
        elif self.path == '/api/report/html':
            self._handle_report_html(body)
        elif self.path in ('/api/export/pdf', '/api/export/html', '/api/export/docx',
                           '/api/export/xlsx'):
            self._handle_export_document(body, self.path.rsplit('/', 1)[-1])
        elif self.path == '/api/project/load':
            self._handle_project_load(body)
        elif self.path == '/api/project/delete':
            self._handle_project_delete(body)
        elif self.path == '/api/report/annotate':
            self._json(200, {'ok': True, 'html': _with_parts(body.get('html') or '')})
        elif self.path == '/api/export/excel':
            self._handle_export_excel(body)
        elif self.path == '/api/report/module':
            self._handle_module_report(body)
        elif self.path == '/api/gap':
            self._handle_gap(body)
        elif self.path == '/api/e1/upload':
            self._handle_e1_upload(body)
        elif self.path == '/api/e1/inspect':
            self._handle_e1_inspect(body)
        elif self.path == '/api/e1/preview':
            self._handle_e1_preview(body)
        elif self.path == '/api/e1/ai-suggest':
            self._handle_e1_ai_suggest(body)
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
        elif self.path == '/api/export/weather_excel':
            self._handle_weather_excel(body)
        elif self.path == '/api/geocode':
            self._handle_geocode(body)
        elif self.path == '/api/weather':
            self._handle_weather(body)
        elif self.path == '/api/calendar/settings':
            self._handle_calendar_settings(body)
        elif self.path == '/api/project/evm-setup':
            self._handle_evm_setup(body)
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
        elif self.path == '/api/kb/starter-xer':
            self._handle_kb_starter_xer(body)
        elif self.path == '/api/kb/detailed-xer':
            self._handle_kb_detailed_xer(body)
        elif self.path == '/api/kb/excel':
            self._handle_kb_excel(body)
        elif self.path == '/api/kb/playbook':
            self._handle_kb_playbook(body)
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
        elif self.path == '/api/special/docx':
            self._handle_special_docx(body)
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
        elif self.path == '/api/chat/ask':
            self._handle_chat_ask(body)
        elif self.path == '/api/chat/setup':
            self._handle_chat_setup(body)
        elif self.path == '/api/chat/settings':
            self._handle_chat_settings(body)
        elif self.path == '/api/chat/dashboard':
            self._handle_chat_dashboard(body)
        elif self.path == '/api/chat/dashboard/excel':
            self._handle_chat_dashboard_excel(body)
        elif self.path == '/api/chat/qa':
            self._handle_chat_qa(body)
        elif self.path == '/api/chat/qa2':
            self._handle_chat_qa2(body)
        elif self.path == '/api/chat/ask2':
            self._handle_chat_ask2(body)
        elif self.path == '/api/chat/copilot/ask':
            self._handle_chat_copilot_ask(body)
        elif self.path == '/api/chat/copilot/tia':
            self._handle_chat_copilot_tia(body)
        elif self.path == '/api/chat/copilot/activities':
            self._handle_chat_copilot_activities(body)
        elif self.path == '/api/chat/copilot/whatif':
            self._handle_chat_copilot_whatif(body)
        elif self.path == '/api/chat/copilot/scenario':
            self._handle_chat_copilot_scenario(body)
        elif self.path == '/api/chat/copilot/impact':
            self._handle_chat_copilot_impact(body)
        elif self.path == '/api/chat/copilot/report':
            self._handle_chat_copilot_report(body)
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
            sys.path.insert(0, resource_path('.'))
            from p6_special import assemble
            import report_theme
            # Two-pass render so the contents page shows REAL page numbers.
            assemble.render_pdf(
                os.path.abspath(output_path), self._special_pid(body),
                body.get('item_ids') or [], body.get('report_name') or 'Special Report',
                mode=report_theme.normalize(body.get('theme')),
                meta=body.get('meta') or {}, letterhead=body.get('letterhead') or {},
                inputs=body.get('inputs') or {}, snapshot_id=body.get('snapshot_id'),
                chrome=_find_chrome())
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

    def _handle_special_docx(self, body):
        """Export the picked Studio results to a REAL Word .docx (python-docx) in the
        narrative house style — double page frame, logo header, page-number footer,
        navy cover + tables, bars drawn as bars — matching the PDF as Word allows."""
        try:
            output_path = body.get('output_path')
            if not output_path:
                self._json(200, {'ok': False, 'error': 'No output path.'})
                return
            sys.path.insert(0, resource_path('.'))
            from p6_special import assemble
            # Reused feature sections are chart-heavy HTML; the .docx rasterises them
            # to an image via Chrome (headless) so Word matches the PDF exactly. A
            # missing Chrome must NOT fail the export — pass None and let docx_report
            # fall back to text/table extraction.
            try:
                chrome = _find_chrome()
            except Exception:
                chrome = None
            assemble.docx(
                os.path.abspath(output_path), self._special_pid(body),
                body.get('item_ids') or [], body.get('report_name') or 'Special Report',
                meta=body.get('meta') or {}, letterhead=body.get('letterhead') or {},
                inputs=body.get('inputs') or {}, snapshot_id=body.get('snapshot_id'),
                chrome=chrome, mode=report_theme.normalize(body.get('theme')),
                editable=True)      # always real Word content — never a picture copy of the PDF (comment 41)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_special_excel(self, body):
        """Export the picked Studio results to .xlsx (a Contents sheet + one data
        sheet per result) — the numbers behind the Document/Dashboard."""
        try:
            output_path = body.get('output_path')
            if not output_path:
                self._json(200, {'ok': False, 'error': 'No output path.'})
                return
            sys.path.insert(0, resource_path('.'))
            from p6_special import assemble
            assemble.excel(
                os.path.abspath(output_path), self._special_pid(body),
                body.get('item_ids') or [], body.get('report_name') or 'Special Report',
                meta=body.get('meta') or {}, inputs=body.get('inputs') or {},
                snapshot_id=body.get('snapshot_id'))
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
            html = _read_ui_file(resource_path('ui/index.html')).decode()
            html = _fill_brand(html)               # data-brand spans: name at first paint
            html = _inline_ui_prefs(html)          # before the guard fills its marker
            html = _inline_startup_guard(html)
            port = self.server.server_address[1]
            # Inject runtime globals so the UI derives its branding from the
            # single source of truth (utils.APP_*). Any current or future UI
            # feature reads window.__APP_NAME__ / window.__APP_TITLE__ instead
            # of hardcoding the product name.
            def _js(v):   # '</' escaped: text read from the changelog can never close the <script>
                return json.dumps(v).replace('</', '<\\/')
            assigns = ''.join(
                f'window.{k} = {_js(v)};' for k, v in (
                    ('__SERVER_PORT__', port),
                    ('__APP_NAME__', APP_NAME),
                    ('__APP_EDITION__', APP_EDITION),
                    ('__APP_TITLE__', APP_TITLE),
                    ('__APP_VERSION__', APP_VERSION),
                    ('__APP_RELEASE_NOTES__', APP_RELEASE_NOTES),   # Help ▸ What's New
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
            self._send_static(html.encode(), 'text/html; charset=utf-8')
        except FileNotFoundError:
            self._json(404, {'ok': False, 'error': 'index.html not found'})
        except OSError as exc:
            # index.html itself locked (antivirus): a visible, self-retrying 'Starting' page
            # instead of raw JSON the window would sit on until the app's watchdog.
            app_startup.log('static file unavailable: ui/index.html (%r)', exc)
            body = _starting_page_html().encode('utf-8')
            self.send_response(503)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Retry-After', '1')
            self.end_headers()
            self.wfile.write(body)

    def _serve(self, path, mime):
        try:
            data = _read_ui_file(path)
            self._send_static(data, mime)
        except FileNotFoundError:
            self._json(404, {'ok': False, 'error': f'file not found: {path}'})
        except OSError as exc:
            # An antivirus scan of the freshly unpacked files (PermissionError / sharing
            # violation) used to escape here and DROP the connection: one failed module and
            # the page stayed on its black startup cover. Answer 503 instead (the page's
            # startup guard retries) and log it.
            self._static_unavailable(path, exc)

    def _send_static(self, data, mime):
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-cache')    # never mix files from two builds
        self.end_headers()
        self.wfile.write(data)

    def _static_unavailable(self, path, exc):
        app_startup.log('static file unavailable: %s (%r)', path, exc)
        body = json.dumps({'ok': False, 'error': f'temporarily unavailable: {exc}'}).encode()
        self.send_response(503)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Retry-After', '1')
        self.end_headers()
        self.wfile.write(body)

    def _handle_db_recover(self):
        """POST /api/db/recover: only when the history DB is known to be damaged — set it
        aside (kept as .corrupt-bak-<time>) and start a fresh one with every row that can
        still be read (db.recover_damaged_db). Never touches a healthy or locked DB."""
        if db.DB_STATUS.get('status') != 'damaged':
            self._json(409, {'ok': False, 'db': dict(db.DB_STATUS),
                             'message': 'The project history database is not damaged.'})
            return
        res = db.recover_damaged_db()
        app_startup.log('database recovery: %s', res)
        self._json(200, {**res, 'db': dict(db.DB_STATUS)})

    def _handle_app_health(self):
        """GET /api/health: a light readiness probe (the server answers, the DB state
        ok / recovered / degraded, and the page handshake state). Never touches XML.
        Always answers 200 with whatever it has (R2 S7) — never a dropped connection."""
        try:
            app = app_startup.health()
        except Exception as exc:                        # noqa: BLE001 — the probe must answer
            app = {'health_error': str(exc)}
        self._json(200, {'ok': True, 'app': APP_NAME, 'version': APP_VERSION,
                         'db': dict(db.DB_STATUS), **app})

    # ── /api/ui-prefs — screen preferences that survive an app restart ─────
    # (Appearance, Report Contents picks, table columns …; owner comment 31 b.) The page
    # keeps them in its browser storage, which the app window loses at every restart;
    # ui/prefs_bridge.js mirrors that storage here and _serve_index hands it back.
    def _handle_ui_prefs_get(self):
        self._json(200, {'ok': True, 'prefs': ui_prefs.load(_ui_prefs_dir())})

    def _handle_ui_prefs_post(self, body):
        if not isinstance(body, dict):
            self._json(400, {'ok': False, 'error': 'Preferences were not understood.'})
            return
        try:
            count, skipped = ui_prefs.update(_ui_prefs_dir(), body.get('set'), body.get('remove'))
        except ValueError as exc:
            self._json(400, {'ok': False, 'error': str(exc)})
            return
        except OSError as exc:                  # file locked / disk full: the page retries
            app_startup.log('ui prefs not saved (%r)', exc)
            self._json(503, {'ok': False, 'error': 'Screen preferences could not be saved right now.'})
            return
        self._json(200, {'ok': True, 'count': count, 'skipped': skipped})

    # Help ▸ Contact & Support 'Safe graphics' switch (BLACK-6): WebView2 without the GPU
    # (--disable-gpu) from the NEXT launch. The app also turns it on by itself after a
    # launch that never showed the page; this is the way back (and a manual way in).
    def _handle_graphics_mode_post(self, body):
        safe = body.get('safe') if isinstance(body, dict) else None
        if not isinstance(safe, bool):
            self._json(400, {'ok': False, 'error': 'Say safe: true or false.'})
            return
        if safe:
            app_startup.enable_safe_graphics('turned on in Help')
        else:
            app_startup.disable_safe_graphics('turned off in Help')
        status = app_startup.graphics_status()
        if status['saved'] != safe:
            self._json(500, {'ok': False, **status,
                             'error': 'The graphics setting could not be saved (the app '
                                      'data folder is not writable).'})
            return
        self._json(200, {'ok': True, **status})

    def _json(self, status, data):
        if isinstance(data, dict) and data.get('error') and data.get('ok') is not True:
            try:
                db.note_error(str(data.get('error')))   # S3: damaged history DB -> said
            except Exception:
                pass
        body = json.dumps(data, cls=_Encoder).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    # ── /api/prodintel — Productivity & Resource Intelligence ──────────
    def _handle_prodintel_tree(self):
        try:
            import p6_prodintel
            self._json(200, {'ok': True, 'tree': p6_prodintel.build_tree()})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_prodintel_query(self, body):
        try:
            import p6_prodintel
            res = p6_prodintel.query(
                body.get('item_id'),
                context=body.get('context') or {},
                quantity=body.get('quantity'),
                component_quantities=body.get('component_quantities') or {},
            )
            self._json(200, {'ok': True, 'result': res})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_prodintel_excel(self, body):
        """Export the current Productivity result to .xlsx — one sheet per report section."""
        try:
            import p6_prodintel
            from p6_evm.xlsx_writer import write_sections_xlsx
            output_path = body.get('output_path')
            if not output_path:
                self._json(200, {'ok': False, 'error': 'No output path.'})
                return
            r = p6_prodintel.query(body.get('item_id'), context=body.get('context') or {},
                                   quantity=body.get('quantity'),
                                   component_quantities=body.get('component_quantities') or {})
            if not r or r.get('found') is False:
                self._json(200, {'ok': False, 'error': 'No validated reference for this selection.'})
                return
            write_sections_xlsx(os.path.abspath(output_path), _prodintel_excel_sections(r),
                                meta=_excel_meta('Productivity & Resource Intelligence', r))
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/parse ─────────────────────────────────────────────────────────
    def _handle_parse(self, body):
        self._json(200, self._parse_pipeline(body))

    def _parse_pipeline(self, body):
        """The import pipeline (/api/parse) as a dict — also re-run IN PLACE for a snapshot
        (refresh_snapshot_id) when its baseline is attached or removed, so every derived view
        (EVM, WBS, gap, calendar, audit…) is rebuilt from the same code as an import."""
        xml_path = body.get('path', '')
        overrides_path = body.get('overrides_path')
        refresh_sid = body.get('refresh_snapshot_id')     # recompute an existing snapshot in place
        if refresh_sid:
            if db.snapshot_exists(refresh_sid):
                xml_path = db.get_snapshot_source(refresh_sid) or xml_path   # its exact content
            else:
                refresh_sid = None

        if not xml_path or not os.path.isfile(xml_path):
            return {'ok': False, 'error': f'File not found: {xml_path}'}

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
            from p6_evm.baseline import load_schedule, baseline_fields
            # Baseline — the ONE resolution every feature uses: embedded in the file, else the
            # baseline attached for this snapshot (a baseline attach/remove re-runs this route
            # with refresh_snapshot_id to recompute that snapshot IN PLACE), else the one
            # attached to an earlier import of the same file, else the file's own dates.
            file_hash = db.hash_file(xml_path)
            # /api/baseline/upload hands the baseline file the planner just picked
            # (attach_baseline): the pipeline itself decides 'already inside the file' / 'matches
            # no activity' BEFORE anything is stored, so an attach parses the update and the
            # baseline once, not twice (R3 F11).
            trial_bl = body.get('attach_baseline') if refresh_sid else None
            attached_bl = trial_bl or (db.get_attached_baseline(snapshot_id=refresh_sid) if refresh_sid
                                       else db.get_prior_baseline_for_hash(file_hash))
            data = load_schedule(xml_path, attached_bl)
            bl_info = getattr(data, 'baseline_info', None) or {}
            if trial_bl:
                if bl_info.get('source') == 'embedded':    # nothing to attach — nothing stored
                    return {'ok': False, 'code': 'embedded', 'baseline_info': bl_info}
                if not bl_info.get('matched'):             # another project's baseline — never stored
                    return {'ok': True, 'code': 'no_match', 'baseline_info': bl_info,
                            'total': len(data.activities)}
                # It lines up: keep its content-exact cached copy with the snapshot.
                attached_bl = db.cache_xml(trial_bl, db.hash_file(trial_bl))
                bl_info['path'] = attached_bl
                db.save_baseline(refresh_sid, attached_bl, trial_bl)
            if bl_info.get('matched') == 0:
                attached_bl = None                         # the wrong project's baseline — forget it
            config['categories'] = auto_categories(data)   # auto-detect categories per project
            result = compute(data, config, overrides=overrides, classifier=build_wbs_classifier(data))

            # Strip the large records list — UI only needs rolled-up metrics
            safe_result = {k: v for k, v in result.items() if k != 'records'}
            safe_result.update(baseline_fields(bl_info))   # embedded / attached / self — for the UI
            from p6_evm.baseline import schedule_baseline
            safe_result.update(schedule_baseline(data))    # '· approx' + the one 'Baseline:' line
            safe_result['activity_count'] = len(data.activities)
            safe_result['calendar_count'] = len(data.calendars)
            safe_result['project_name']   = data.project.get('name', '')
            if getattr(data, 'unparsed_dates', None):   # P22: values in date fields that are not dates
                safe_result['unparsed_dates'] = {'count': sum(data.unparsed_dates.values()),
                                                 'samples': list(data.unparsed_dates)[:5]}
            # Does this update have a REAL baseline (inside the file, or attached)? The very rule
            # /api/update/analyze applies (update_has_baseline) — lets Update Analysis answer
            # "no baseline" at once, without a re-read. An attach / remove re-runs this pipeline,
            # so the flag follows the attached baseline.
            try:
                from p6_update.analysis import update_has_baseline
                safe_result['has_embedded_baseline'] = bool(update_has_baseline(data))
            except Exception:
                safe_result['has_embedded_baseline'] = None   # unknown → the screen asks the server

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

            # ── View-only projections: Schedule (Gantt) rows + the WBS summary tree ──
            # JSON-safe (NOT the heavy/non-serialisable `records`); built by
            # p6_evm.schedule_view and stored with the snapshot below, so a project re-opened
            # from Recent Projects shows the same Gantt / WBS with no re-parse.
            try:
                from p6_evm.schedule_view import gantt_activities
                safe_result['activities'] = gantt_activities(result['records'], data.wbs)
            except Exception as gantt_exc:
                safe_result['activities'] = []
                print(f'[gantt] slim activities skipped: {gantt_exc}', file=sys.stderr)
            try:
                from p6_evm.schedule_view import wbs_views
                safe_result['wbs_summary'], safe_result['wbs_main'] = wbs_views(result['records'], data)
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
            prior_import   = None if refresh_sid else db.get_prior_import_date(file_hash)
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

            if refresh_sid:                        # baseline attached / removed: same snapshot
                sid = refresh_sid
                db.clear_snapshot_results(sid)
            else:
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
                # The project's saved settings (Project Setup weights/Actual Cost, weather
                # location/limits…) are returned even when the calendar audit fails.
                try:
                    safe_result['calendar_settings'] = db.get_project_settings(pid) or {}
                except Exception:
                    safe_result['calendar_settings'] = {}
                print(f'[calendar] skipped: {cal_exc}', file=sys.stderr)
            db.save_evm_extras(sid, {
                'engineering_p6': safe_result.get('engineering_p6', []),
                'activity_code_types': safe_result.get('activity_code_types', []),
                'gap': safe_result.get('gap'),
                'baseline_finish': safe_result.get('baseline_finish'),
                'expected_finish': safe_result.get('expected_finish'),
                'baseline_path': attached_bl,      # the attached baseline stays with the snapshot
                'baseline_fields': baseline_fields(bl_info),   # what the stored numbers used
                'has_embedded_baseline': safe_result.get('has_embedded_baseline'),
            })
            try:                                   # the Gantt / WBS views stay with the snapshot
                db.save_snapshot_views(sid, {k: safe_result.get(k) or [] for k in
                                             ('activities', 'wbs_summary', 'wbs_main')})
            except Exception as view_exc:
                print(f'[views] not stored: {view_exc}', file=sys.stderr)
            # ──────────────────────────────────────────────────────────────

            return {'ok': True, 'result': safe_result, 'cached_path': cached_path,
                    'previous_import': prior_import, 'snapshot_id': sid}

        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

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
            data   = _schedule_for(resolved, body)   # embedded > attached > self baseline
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
            _chrome_print_pdf(html_path, out_path, chrome)

            os.unlink(html_path)
            self._json(200, {'ok': True})

        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/update/* — Update Analysis (single file vs its baseline) ───────
    def _handle_update_analyze(self, body):
        """Update Analysis — the current schedule read against its baseline, resolved the one
        way every feature uses (p6_evm.baseline): embedded in the file, else the baseline
        attached for this update (here or on Earned Value, XER or XML). Returns Time Status, Planned-vs-Actual by code and the Critical Path
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
            data = _schedule_for(curr_path, body)   # embedded > attached > self baseline
            cfg = dict(base_config)
            cfg['categories'] = auto_categories(data)
            metrics = compute(data, cfg, classifier=build_wbs_classifier(data))
            summary_level = int(body.get('summary_level', 0) or 0)
            report = build_report_from_data(data, metrics, summary_level=summary_level)
            report['file'] = os.path.basename(curr_path)
            if not report.get('has_baseline'):
                # Neither inside the file nor attached (an XER never carries it; an XML exported
                # without its baseline project neither) — never measure it against its own plan.
                self._json(200, {'ok': False, 'code': 'no_baseline', 'report': report,
                                 'baseline_missing': (getattr(data, 'baseline_info', None) or {}).get('missing'),
                                 'baseline_expected_name': report.get('baseline_expected_name'),
                                 'error': 'This update carries no baseline and none is attached. Attach the '
                                          'baseline (XER or XML) — it is remembered for this update and used by '
                                          'every feature — or re-export the update from P6 as XML with its '
                                          'baseline project included.'})
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
            data = _schedule_for(curr_path, body)   # embedded > attached > self baseline
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
            data = _schedule_for(curr_path, body)   # embedded > attached > self baseline
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
            from p6_update.exporters import report_excel_sections
            from p6_evm.xlsx_writer import write_sections_xlsx
            bl = report.get('baseline_label')
            write_sections_xlsx(os.path.abspath(output_path), report_excel_sections(report),
                                meta=_excel_meta('Update Analysis', report,
                                                 **({'baseline': bl} if bl else {})))
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_evm_excel(self, body):
        """Export the Earned Value report to .xlsx from the report the client holds."""
        report = body.get('report') or {}
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.evm_excel import evm_excel
            from p6_evm.xlsx_writer import write_sections_xlsx
            from p6_evm.baseline import baseline_label
            res = report.get('result') or {}      # the label the screen + PDF print (R2 F8)
            bl = res.get('baseline_label') or baseline_label(res)
            write_sections_xlsx(os.path.abspath(output_path), evm_excel(report),
                                meta=_excel_meta('Earned Value Report', report,
                                                 **({'baseline': bl} if bl else {})))
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_revcompare_excel(self, body):
        """Export the Baseline Revision Comparison to .xlsx from the report the client
        already holds (no re-parse). Mirrors the PDF's sections as stacked titled tables."""
        report = body.get('report') or {}
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_revcompare.xlsx_export import revcompare_excel
            from p6_evm.xlsx_writer import write_sections_xlsx
            write_sections_xlsx(os.path.abspath(output_path), revcompare_excel(report),
                                meta=_excel_meta('Baseline Revision Comparison', report))
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_copilot_excel(self, body):
        """Export the AI Copilot · TIA report to .xlsx from the result the client
        holds. Rebuilds the same deterministic copilot report the screen showed
        (build_copilot, reusing the saved weather estimate), then mirrors its
        sections into the workbook via the shared sections writer."""
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            from p6_evm.copilot import build_copilot
            from p6_evm.copilot_exporters import copilot_excel
            from p6_evm.xlsx_writer import write_sections_xlsx
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
            report = build_copilot(result, weather)
            write_sections_xlsx(os.path.abspath(output_path), copilot_excel(report),
                                meta=_excel_meta('AI Copilot · Time Impact Analysis', result))
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_dash_excel(self, body):
        """Export the Professional Dashboard read-model the client holds to .xlsx.
        DB read path — the client posts the /api/dashboard dict; nothing re-parsed here."""
        dashboard = body.get('dashboard') or {}
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.dashboard_excel import dashboard_excel
            from p6_evm.xlsx_writer import write_sections_xlsx
            sheets = dashboard_excel(dashboard)
            write_sections_xlsx(os.path.abspath(output_path), sheets,
                                meta=_excel_meta('Professional Dashboard', dashboard))
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_dashboard_excel(self, body):
        """The AI Chat Professional Dashboard to .xlsx — from the payload the page is showing
        (``p6_chat.dashboard.build``), so the workbook's figures are the screen's."""
        dashboard = body.get('dashboard') or {}
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        if not isinstance(dashboard, dict) or not dashboard.get('ok'):
            self._json(200, {'ok': False, 'error': 'Build the dashboard first, then save it to Excel.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_chat.dashboard_excel import sheets
            from p6_evm.xlsx_writer import write_sections_xlsx
            m = dashboard.get('meta') or {}
            write_sections_xlsx(os.path.abspath(output_path), sheets(dashboard),
                                meta=_excel_meta('Professional Dashboard',
                                                 {'project_name': m.get('project'), 'data_date': m.get('data_date')},
                                                 snapshot_id=body.get('snapshot_id')))
            self._json(200, {'ok': True, 'path': output_path})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_narrative_excel(self, body):
        """Export the Baseline Narrative REPORT to .xlsx — one sheet per report section, every
        table with all its rows, every chart as its numbers (owner comment 29). Built from the
        same document the screen / PDF / Word use: the client's document (with its edits and its
        Report-Contents selection) when it posts one, else the report rebuilt from the snapshot's
        own schedule file with the saved setup (the sanctioned report re-parse)."""
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_narrative.xlsx_report import narrative_sheets
            from p6_evm.xlsx_writer import write_sections_xlsx
            doc = body.get('doc')
            snap = body.get('snapshot_id')
            if doc:
                from p6_narrative.builder import apply_edits
                doc = apply_edits(doc, body.get('edits'))
            else:
                src = db.get_snapshot_source(snap) if snap is not None else None
                if not src:
                    src = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
                if not src:
                    self._json(200, {'ok': False, 'error': 'Schedule not found — re-import it and try again.'})
                    return
                from p6_evm.parser import parse_file
                from p6_narrative.report import build_report
                setup = body.get('setup')
                if setup is None and snap is not None:
                    try:
                        setup, _src = db.get_snapshot_ui_state_inherited(snap, 'narrative_setup')
                    except Exception:
                        setup = None
                doc = build_report(parse_file(src), path=src, setup=setup).to_dict()
            meta = (doc or {}).get('meta') or {}
            write_sections_xlsx(os.path.abspath(output_path), narrative_sheets(doc),
                                meta=_excel_meta('Baseline Narrative Report',
                                                 {'project_name': meta.get('project_name'),
                                                  'data_date': meta.get('data_date')}, snapshot_id=snap))
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_overview_excel(self, body):
        """Export the Project Overview to .xlsx from the parse result the client holds."""
        report = body.get('report') or {}
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.overview_excel import overview_excel
            from p6_evm.xlsx_writer import write_sections_xlsx
            sheets = overview_excel(report)
            bl = (report.get('baseline_line') or '').replace('Baseline: ', '', 1)   # approx only
            write_sections_xlsx(os.path.abspath(output_path), sheets,
                                meta=_excel_meta('Project Overview', report,
                                                 **({'baseline': bl} if bl else {})))
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_wbs_excel(self, body):
        """Export the Project ▸ WBS summary to .xlsx from the report the client holds."""
        report = body.get('report') or {}
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.wbs_excel import wbs_excel
            from p6_evm.xlsx_writer import write_sections_xlsx
            bl = (report.get('baseline_line') or '').replace('Baseline: ', '', 1)   # approx only
            write_sections_xlsx(os.path.abspath(output_path), wbs_excel(report),
                                meta=_excel_meta('WBS Summary', report,
                                                 **({'baseline': bl} if bl else {})))
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_schedule_excel(self, body):
        """Export the Schedule (Gantt) view to .xlsx from the parse result the client
        holds. No XML re-parse — the slim `activities` list is already in the result."""
        result = body.get('result') or {}
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.schedule_excel import schedule_excel
            from p6_evm.xlsx_writer import write_sections_xlsx
            write_sections_xlsx(os.path.abspath(output_path), schedule_excel(result),
                                meta=_excel_meta('Schedule (Gantt)', result))
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
                self._json(200, {'ok': True, 'html': _with_parts(html_content)})
                return
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name
            chrome = _find_chrome()
            out_path = os.path.abspath(output_path)
            _chrome_print_pdf(html_path, out_path, chrome)
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
        read = _parse_secs(baseline_path) + _parse_secs(update_path)
        stages = _RunStages(body, [
            (f'Reading the baseline — {os.path.basename(baseline_path)}', _parse_secs(baseline_path)),
            (f'Reading the update — {os.path.basename(update_path)}', _parse_secs(update_path)),
            ('Comparing logic, durations and milestones', 0.2 + 0.1 * read),
        ])
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_compare.report import build_report_from_data
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            stages.enter(0)
            baseline = parse_file(baseline_path)
            stages.enter(1)
            update = parse_file(update_path)
            stages.enter(2)
            report = build_report_from_data(baseline, update, config)
            # The attached baseline is its cached copy ({hash12}_name) — name the planner's file (R3 F9).
            from p6_evm.baseline import display_name
            report['baseline_file'] = display_name(baseline_path)
            report['update_file'] = display_name(update_path)
            self._json(200, {'ok': True, 'report': report})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})
        finally:
            stages.close()

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
        role_name = {'current': 'the current schedule', 'previous': 'the previous update', 'baseline': 'the baseline'}
        read = sum(_parse_secs(p) for p in paths.values())
        stages = _RunStages(body, [(f'Reading {role_name.get(r, r)} — {os.path.basename(p)}', _parse_secs(p))
                                   for r, p in paths.items()]
                            + [('Tracing the driving path to every finish milestone', 0.2 + 0.05 * read)])
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_critpath.analysis import build_report
            # One baseline resolution (embedded > attached > self): the current update first (its
            # embedded baseline, else the one attached for it); the previous update its own, else
            # the CURRENT update's baseline — inside the XML or attached, the same (R4).
            # The Run bar names each real read in the caller's role order (current first) — RUNUX.
            from p6_evm.baseline import inherit_baseline
            roles = list(paths)
            stages.enter(roles.index('current'))
            schedules = {'current': _schedule_for(current_path, body)}
            for i, (role, p) in enumerate(paths.items()):
                if role == 'baseline':                # the picked baseline IS the baseline
                    stages.enter(i)
                    schedules[role] = parse_file(p)
                elif role == 'previous':
                    stages.enter(i)
                    schedules[role] = _schedule_for(p, {})
                    inherit_baseline(schedules[role], schedules['current'])
            schedules = {role: schedules[role] for role in paths}   # keep the caller's role order
            stages.enter(len(paths))
            report = build_report(schedules, mode,
                                  milestone_code=body.get('milestone_code'),
                                  summary_level=int(body.get('summary_level', 0) or 0))
            from p6_evm.baseline import display_name    # cached copies ({hash12}_name) → file name (R3 F9)
            report['files'] = {role: display_name(p) for role, p in paths.items()}
            self._json(200, {'ok': True, 'report': report})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})
        finally:
            stages.close()

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
                self._json(200, {'ok': True, 'html': _with_parts(html_content)})
                return
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name
            chrome = _find_chrome()
            _chrome_print_pdf(html_path, os.path.abspath(output_path), chrome)
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
            from p6_critpath.exporters import critpath_excel_sections
            from p6_evm.xlsx_writer import write_sections_xlsx
            _bl = report.get('baseline_label') if report.get('baseline_approx') else None
            write_sections_xlsx(os.path.abspath(output_path), critpath_excel_sections(report),
                                meta=_excel_meta('Critical Path Analyzer', report,
                                                 snapshot_id=body.get('snapshot_id'),
                                                 **({'baseline': _bl} if _bl else {})))
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
        read = _parse_secs(rev0_path) + _parse_secs(rev1_path)
        stages = _RunStages(body, [
            (f'Reading Rev.00 — {os.path.basename(rev0_path)}', _parse_secs(rev0_path)),
            (f'Reading Rev.01 — {os.path.basename(rev1_path)}', _parse_secs(rev1_path)),
            ('Matching activities and comparing the revisions', 0.3 + 0.25 * read),
        ])
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_revcompare.compare import build_report_from_data
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            stages.enter(0)
            rev0 = parse_file(rev0_path)
            stages.enter(1)
            rev1 = parse_file(rev1_path)
            stages.enter(2)
            report = build_report_from_data(rev0, rev1, config, body.get('options'))
            report['rev0']['file'] = os.path.basename(rev0_path)
            report['rev1']['file'] = os.path.basename(rev1_path)
            self._json(200, {'ok': True, 'report': report})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})
        finally:
            stages.close()

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
                                       theme=report_theme.normalize(body.get('theme')),
                                       filters=body.get('filters'))
            if preview:
                self._json(200, {'ok': True, 'html': _with_parts(html_content)})
                return
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name
            chrome = _find_chrome()
            _chrome_print_pdf(html_path, os.path.abspath(output_path), chrome)
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

    # ── /api/kb/playbooks + /api/kb/playbook (Project Type Playbooks) ────────
    def _handle_kb_playbooks(self):
        """The Project-Type Playbooks library — every project type as a card,
        grouped by sector. Reference only; built from the bundled KB."""
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.playbooks import library
            self._json(200, {'ok': True, **library()})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_kb_playbook(self, body):
        """One Project-Type Playbook: overview, step-by-step construction
        sequence, suggested WBS, baseline-file availability, hold points,
        commissioning ladder and evidence."""
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.playbooks import playbook
            pb = playbook(body.get('archetype', ''))
            if pb is None:
                self._json(200, {'ok': False,
                                 'error': f"Unknown project type: {body.get('archetype', '')}"})
                return
            self._json(200, {'ok': True, 'playbook': pb})
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

    def _handle_kb_detailed_xer(self, body):
        """Write a project-type's DETAILED baseline as an importable P6 XER — the
        curated WBS expanded across execution zones/levels into a full ~1000+
        activity schedule (procurement + per-zone trade steps + commissioning,
        with FS/SS logic and Zone activity codes). A reference programme skeleton
        to flesh out; nothing from a real schedule."""
        archetype = body.get('type', '')
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.playbooks import playbook
            from p6_kb.starter_xer import write_detailed_xer
            pb = playbook(archetype)
            if not pb or not pb.get('curated'):
                self._json(200, {'ok': False, 'error': f'No detailed schedule for: {archetype}'})
                return
            res = write_detailed_xer(pb.get('name') or archetype, pb['curated'], os.path.abspath(output_path))
            self._json(200, {'ok': True, **res})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_kb_excel(self, body):
        """Export a project type's playbook as a multi-sheet .xlsx mirroring the
        on-screen sections (brief & scope, MEP, sequence by trade, WBS, Basis of
        Planning) via the shared write_sections_xlsx standard."""
        archetype = body.get('type') or body.get('archetype') or ''
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.playbooks import playbook
            from p6_evm.xlsx_writer import write_sections_xlsx
            pb = playbook(archetype)
            if not pb:
                self._json(200, {'ok': False, 'error': f'Unknown project type: {archetype}'})
                return
            cur = pb.get('curated') or {}
            b = cur.get('brief') if isinstance(cur.get('brief'), dict) else {}
            overview_blocks = []
            if b.get('intro'):
                overview_blocks.append({'title': 'Project brief', 'headers': ['Overview'], 'rows': [[b['intro']]]})
            if b.get('scope'):
                overview_blocks.append({'title': 'Scope of works', 'headers': ['Item', 'Detail'],
                                        'rows': [[s.get('name'), s.get('desc')] for s in b['scope']]})
            if b.get('glossary'):
                overview_blocks.append({'title': 'Key terms — in plain words', 'headers': ['Term', 'Plain meaning'],
                                        'rows': [[g.get('term'), g.get('plain')] for g in b['glossary']]})
            if b.get('must_get_right'):
                overview_blocks.append({'title': 'What you must get right', 'headers': ['Point'],
                                        'rows': [[m] for m in b['must_get_right']]})
            if cur.get('components'):
                overview_blocks.append({'title': 'Main components', 'headers': ['Component', 'Detail', 'Primary'],
                                        'rows': [[c.get('name'), c.get('desc'), 'Yes' if c.get('primary') else ''] for c in cur['components']]})
            if cur.get('mep_systems'):
                mep = [[m.get('discipline'), it] for m in cur['mep_systems'] for it in (m.get('items') or [])]
                overview_blocks.append({'title': 'MEP systems', 'headers': ['Discipline', 'System'], 'rows': mep})
            sheets = [{'name': 'Brief & Scope', 'blocks': overview_blocks or [{'title': 'Project', 'headers': ['Name'], 'rows': [[pb.get('name')]]}]}]
            if cur.get('trades'):
                seq = [[t.get('name'), i + 1, s, 'hold' if i in (t.get('holds') or []) else '']
                       for t in cur['trades'] for i, s in enumerate(t.get('steps') or [])]
                seq_blocks = []
                # the two overview pictures of the page, as their figures (owner comments 29 / 38)
                if cur.get('overview_phases'):
                    seq_blocks.append({'title': 'Sequence of work — overview', 'headers': ['Phase', 'Name'],
                                       'rows': [[i, ph] for i, ph in enumerate(cur['overview_phases'], 1)]})
                lanes = (cur.get('sequence_chart') or {}).get('lanes') or []
                if lanes:
                    seq_blocks.append({
                        'title': 'Sequence of work — chart by trade',
                        'note': 'Start and finish are positions along the programme (0 % = start, 100 % = finish) — '
                                'logic order, not dates.',
                        'headers': ['Trade', 'Discipline', 'Starts at (%)', 'Finishes at (%)', 'What happens'],
                        'rows': [[ln.get('trade'), ln.get('disc'), ln.get('start'),
                                  (ln.get('start') or 0) + (ln.get('width') or 0), ln.get('label')] for ln in lanes]})
                seq_blocks.append({'title': 'Typical sequence of work',
                                   'headers': ['Trade', 'Step', 'Activity', 'Hold'], 'rows': seq})
                sheets.append({'name': 'Sequence by trade', 'blocks': seq_blocks})
            if cur.get('wbs'):
                sheets.append({'name': 'WBS', 'blocks': [{'title': 'Suggested WBS (Primavera P6)',
                              'headers': ['WBS Code', 'WBS Name', 'Level'],
                              'rows': [[w.get('code'), w.get('name'), w.get('level')] for w in cur['wbs']]}]})
            bop = cur.get('basis_of_planning') or {}
            if bop.get('sections'):
                blocks = [{'title': 'Basis of Planning — ' + (bop.get('standard') or 'AACE 38R-06'),
                           'headers': ['Section', 'Content'],
                           'rows': [[s.get('heading'), s.get('body')] for s in bop['sections']]}]
                for s in bop['sections']:
                    tbl = s.get('table')
                    if tbl and tbl.get('rows'):
                        blocks.append({'title': s.get('heading'), 'headers': tbl.get('columns') or [], 'rows': tbl['rows']})
                if cur.get('standards'):
                    blocks.append({'title': 'Standards used', 'headers': ['Use', 'Standard'],
                                   'rows': [[st.get('code'), st.get('text')] for st in cur['standards']]})
                sheets.append({'name': 'Basis of Planning', 'blocks': blocks})
            write_sections_xlsx(os.path.abspath(output_path), sheets,
                                meta=_excel_meta('Knowledge Base — ' + (pb.get('name') or archetype),
                                                 sector=pb.get('sector_label') or None))
            self._json(200, {'ok': True, 'path': output_path, 'sheets': len(sheets)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_kb_starter_xer(self, body):
        """Write a project-type's suggested WBS as an importable P6 **XER** starter
        schedule (WBS tree + a works activity per branch + start/finish milestones,
        chained Finish-to-Start). Built from the curated WBS so the file matches the
        screen; a reference skeleton, nothing from a real schedule."""
        archetype = body.get('type', '')
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_kb.playbooks import playbook
            from p6_kb.starter_xer import write_starter_xer
            pb = playbook(archetype)
            if not pb:
                self._json(200, {'ok': False, 'error': f'Unknown project type: {archetype}'})
                return
            cur = pb.get('curated') or {}
            wbs_rows = cur.get('wbs') or [{'code': b.get('code'), 'name': b.get('name'), 'level': 1}
                                          for b in ((pb.get('wbs') or {}).get('branches') or [])]
            res = write_starter_xer(pb.get('name') or archetype, wbs_rows, os.path.abspath(output_path))
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
            from p6_kb.exporters import findings_excel_sections
            from p6_evm.xlsx_writer import write_sections_xlsx
            write_sections_xlsx(os.path.abspath(output_path), findings_excel_sections(report),
                                meta=_excel_meta('Constructability Review', report,
                                                 snapshot_id=body.get('snapshot_id')))
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
                self._json(200, {'ok': True, 'html': _with_parts(html_content)})
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
            _chrome_print_pdf(html_path, os.path.abspath(output_path), chrome)
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
                self._json(200, {'ok': True, 'html': _with_parts(html_content)})
                return
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name
            chrome = _find_chrome()
            _chrome_print_pdf(html_path, os.path.abspath(output_path), chrome)
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

    # ── /api/oos/validate ─────────────────────────────────────────────────
    def _handle_oos_validate(self, body):
        """Out-of-Sequence — re-validate after the planner applies corrections. Re-parses
        the imported schedule, applies the accepted relationship corrections to an in-memory
        copy, re-runs the SAME detection engine, and reports the fresh findings + which
        accepted findings are now genuinely resolved. Nothing is written to disk."""
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        accepted = body.get('accepted') or []
        if not resolved or not os.path.isfile(resolved):
            self._json(200, {'ok': False, 'error': 'Schedule not available. Re-import it first.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_audit.modules.oos_resolve import revalidate_from_path
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            res = revalidate_from_path(resolved, config, accepted)
            self._json(200, {'ok': True, **res})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/oos/corrected-file ───────────────────────────────────────────
    def _handle_oos_corrected(self, body):
        """Out-of-Sequence — write the corrected schedule (accepted relationship corrections
        only) to a separate file in the same format as the import (P6 XML or XER). Actuals
        and dates are never touched; open in P6 → F9. The user's original file is not modified."""
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        output_path = body.get('output_path', '')
        accepted = body.get('accepted') or []
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        if not resolved or not os.path.isfile(resolved):
            self._json(200, {'ok': False, 'error': 'Schedule not available. Re-import it first.'})
            return
        if not accepted:
            self._json(200, {'ok': False, 'error': 'No corrections have been applied yet.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_audit.modules.oos_resolve import write_corrected
            res = write_corrected(os.path.abspath(resolved), accepted, os.path.abspath(output_path))
            self._json(200, {'ok': True, 'applied': res['applied'], 'out_path': res['out_path']})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/dangling/validate ────────────────────────────────────────────
    def _handle_dangling_validate(self, body):
        """Dangling — re-validate after the planner applies relationship-type fixes. Re-parses the
        imported schedule, applies the accepted fixes to an in-memory copy, re-runs the SAME dangling
        engine, and reports the fresh findings + which activities are now genuinely no longer
        dangling. Nothing is written to disk."""
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        accepted = body.get('accepted') or []
        if not resolved or not os.path.isfile(resolved):
            self._json(200, {'ok': False, 'error': 'Schedule not available. Re-import it first.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_audit.modules.dangling_resolve import revalidate_from_path
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            res = revalidate_from_path(resolved, config, accepted, completion=body.get('completion'))
            self._json(200, {'ok': True, **res})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/dangling/corrected-file ──────────────────────────────────────
    def _handle_dangling_corrected(self, body):
        """Dangling — write the corrected schedule (accepted relationship-type fixes only) to a
        separate file in the same format as the import (P6 XML or XER). Actuals and dates are never
        touched; open in P6 → F9. The user's original file is not modified."""
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        output_path = body.get('output_path', '')
        accepted = body.get('accepted') or []
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        if not resolved or not os.path.isfile(resolved):
            self._json(200, {'ok': False, 'error': 'Schedule not available. Re-import it first.'})
            return
        if not accepted:
            self._json(200, {'ok': False, 'error': 'No fixes have been applied yet.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_audit.modules.dangling_resolve import write_corrected
            res = write_corrected(os.path.abspath(resolved), accepted, os.path.abspath(output_path),
                                  completion=body.get('completion'))
            self._json(200, {'ok': True, 'applied': res['applied'], 'out_path': res['out_path']})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/health/recompute ─────────────────────────────────────────────
    def _handle_health_recompute(self, body):
        """Recompute the Schedule Health roll-up from the client's CURRENT modules (with any in-memory
        Dangling fixes previewed in), so the Dangling module tab score AND the Summary roll-up update
        live as findings resolve — using the same weighted engine as import (single source of truth)."""
        modules = body.get('modules') or {}
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_audit.health import schedule_health
            self._json(200, {'ok': True, 'health': schedule_health(modules)})
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
            from p6_compare.exporters import logic_excel_sections
            from p6_evm.xlsx_writer import write_sections_xlsx
            impact = body.get('impact')
            write_sections_xlsx(os.path.abspath(output_path), logic_excel_sections(report, impact),
                                meta=_excel_meta('Consultant Review', report))
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
            html_content = render_html(report, impact, theme=report_theme.normalize(body.get('theme')),
                                        sections=body.get('sections'))
            if preview:
                self._json(200, {'ok': True, 'html': _with_parts(html_content)})
                return
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name
            chrome = _find_chrome()
            # DEVNULL (not PIPE) so a verbose/large Chrome render can't dead-lock on a full
            # pipe buffer — that was the "Export PDF does nothing" hang on big schedules.
            # A timeout turns any remaining hang into a clear error instead of silence.
            _chrome_print_pdf(html_path, os.path.abspath(output_path), chrome)
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
        # The Run bar names the real step (reading each update, then comparing) — RUNUX-R2.
        read = _parse_secs(prev_path) + _parse_secs(curr_path)
        stages = _RunStages(body, [
            (f'Reading the current update — {os.path.basename(curr_path)}', _parse_secs(curr_path)),
            (f'Reading the previous update — {os.path.basename(prev_path)}', _parse_secs(prev_path)),
            ('Comparing the two periods', 0.2 + 0.1 * read),
        ])
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_evm.metrics import compute
            from p6_evm.classify import auto_categories, build_wbs_classifier
            from p6_period.report import build_report_from_data
            with open(resource_path('config.json')) as f:
                base_config = json.load(f)

            # One baseline resolution (embedded > attached > self): the current update first (its
            # embedded baseline, else the one attached for it); the previous update its own, else
            # the CURRENT update's baseline — inside the XML or attached, the same (R4).
            from p6_evm.baseline import inherit_baseline

            def parse_and_compute(path, sched_body, curr=None):
                data = _schedule_for(path, sched_body)
                if curr is not None:
                    inherit_baseline(data, curr)
                cfg = dict(base_config)
                cfg['categories'] = auto_categories(data)
                metrics = compute(data, cfg, classifier=build_wbs_classifier(data))
                return data, metrics

            # The current update is read FIRST — the previous one may inherit its baseline.
            stages.enter(0)
            curr_data, curr_m = parse_and_compute(curr_path, body)
            stages.enter(1)
            prev_data, prev_m = parse_and_compute(prev_path, {'cached_path': body.get('prev_cached_path')},
                                                  curr_data)
            stages.enter(2)
            report = build_report_from_data(prev_data, curr_data, prev_m, curr_m, base_config)
            report['prev_file'] = os.path.basename(prev_path)
            report['update_file'] = os.path.basename(curr_path)
            self._json(200, {'ok': True, 'report': report})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})
        finally:
            stages.close()

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
            _bl = report.get('baseline_label') if report.get('baseline_approx') else None   # approx only
            # Sheet 1 = the report as before; then the S-curve numbers, progress by every activity
            # code, the critical path lists and the what-moved activities (owner comment 29).
            from p6_evm.xlsx_writer import write_sections_xlsx, _sheet
            from p6_period.exporters import report_excel_extra_sheets
            first = _sheet(headers, rows, meta=_excel_meta('Update vs Update — Windows Analysis', report,
                                                           **({'baseline': _bl} if _bl else {})))
            write_sections_xlsx(os.path.abspath(output_path),
                                [{'name': 'Update vs Update', 'xml': first}]
                                + report_excel_extra_sheets(report))
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
                self._json(200, {'ok': True, 'html': _with_parts(html_content)})
                return
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name
            chrome = _find_chrome()
            _chrome_print_pdf(html_path, os.path.abspath(output_path), chrome)
            os.unlink(html_path)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/project/load ─────────────────────────────────────────────────
    def _snapshot_views(self, snapshot_id):
        """The Schedule (Gantt) rows and WBS tree stored with a snapshot. A snapshot imported
        before these were stored is built ONCE from its cached file (parse + compute, metrics
        untouched) and stored, so every later open reads the DB only."""
        empty = {'activities': [], 'wbs_summary': [], 'wbs_main': []}
        if not snapshot_id:
            return empty
        views = db.get_snapshot_views(snapshot_id)
        if views is None:
            src = db.get_snapshot_source(snapshot_id)
            if not src:
                return empty
            try:
                sys.path.insert(0, resource_path('.'))
                from p6_evm.metrics import compute
                from p6_evm.classify import auto_categories, build_wbs_classifier
                from p6_evm.schedule_view import build_views
                with open(resource_path('config.json')) as f:
                    config = json.load(f)
                data = _schedule_for(src, {'snapshot_id': snapshot_id})
                config['categories'] = auto_categories(data)
                rr = compute(data, config, classifier=build_wbs_classifier(data))
                views = build_views(rr['records'], data)
                db.save_snapshot_views(snapshot_id, views)
            except Exception as exc:
                print(f'[views] snapshot {snapshot_id} not rebuilt: {exc}', file=sys.stderr)
                return empty
        return {k: views.get(k) or [] for k in empty}

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
        # A snapshot stored before the one baseline resolver keeps no record of which baseline its
        # numbers used, so an XML exported without its baseline re-opened with PV 0, no banner and
        # no Attach button (R2 F6). Recompute it ONCE, in place, through the import pipeline (the
        # same code an import / a baseline attach runs: embedded, else attached, else own dates)
        # — every derived view is rebuilt and baseline_fields stored, so later opens read the DB.
        if snapshot_id and not (db.get_evm_extras(snapshot_id) or {}).get('baseline_fields'):
            src = db.get_snapshot_source(snapshot_id)
            if src:
                try:
                    fresh = self._parse_pipeline({'path': src, 'refresh_snapshot_id': snapshot_id})
                except Exception as exc:
                    fresh = {'ok': False, 'error': str(exc)}
                if fresh.get('ok'):
                    result = db.get_project_result(project_id) or result
                    for k in ('_snapshot_id', '_cached_path', '_original_path'):
                        result.pop(k, None)
                else:
                    print(f"[baseline] old snapshot {snapshot_id} not recomputed: {fresh.get('error')}",
                          file=sys.stderr)
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
        result['has_embedded_baseline'] = extras.get('has_embedded_baseline')   # None = older snapshot (unknown)
        # Baseline: a snapshot stored since the one-resolver change carries what its stored
        # numbers used (embedded / attached / self) — nothing to re-parse. An older snapshot
        # whose baseline was attached the old way (numbers stored WITHOUT it) is recomputed
        # through the same resolver so PV / SPI / Delay stay correct.
        stored_bl = extras.get('baseline_fields')
        bl_path = extras.get('baseline_path')
        if stored_bl:
            result.update(stored_bl)
            try:                                  # '· approx' + the one 'Baseline:' line (R2)
                from p6_evm.baseline import baseline_approx, baseline_label
                result['baseline_approx'] = baseline_approx(stored_bl)
                result['baseline_label'] = baseline_label(stored_bl, stored_bl.get('baseline_embedded_name')
                                                          or stored_bl.get('baseline_expected_name'))
            except Exception:
                pass
        elif bl_path and cached_path and os.path.isfile(cached_path):
            try:
                sys.path.insert(0, resource_path('.'))
                from p6_evm.metrics import compute
                from p6_evm.classify import auto_categories, build_wbs_classifier
                from p6_evm.baseline import baseline_fields
                with open(resource_path('config.json')) as f:
                    config = json.load(f)
                data = _schedule_for(cached_path, {'snapshot_id': snapshot_id})
                config['categories'] = auto_categories(data)
                rr = compute(data, config, classifier=build_wbs_classifier(data))
                for k in ('pv', 'ev', 'spi', 'cpi', 'delay_days',
                          'overall_planned_pct', 'overall_actual_pct'):
                    result[k] = rr[k]
                result['categories'] = {n: {'weight': c['weight'], 'planned_pct': c['planned_pct'],
                                            'actual_pct': c['actual_pct'], 'bac': c['bac'], 'ac': c['ac'],
                                            'activity_count': c['activity_count'], 'overridden': c['overridden']}
                                        for n, c in rr['categories'].items()}
                result.update(baseline_fields(getattr(data, 'baseline_info', None)))
                from p6_evm.baseline import schedule_baseline
                result.update(schedule_baseline(data))
            except Exception as bexc:
                print(f'[evm] baseline re-apply skipped: {bexc}', file=sys.stderr)

        result.update(self._snapshot_views(snapshot_id))      # Schedule (Gantt) rows + WBS tree
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
            from p6_audit.exporters import (excel_columns, excel_highlight_cols,
                                            excel_severity_meta, filter_lag_findings)
            lag_justifications = body.get('lag_justifications')
            if module == 'lag_lead' and lag_justifications:
                # Print the justifications the planner has on screen (typed or previously saved).
                # The DB copy loaded above carries none — they're merged in only on parse /
                # project-load — so without this the register would export blank reasons.
                from p6_audit.modules.lag_lead import apply_justifications
                apply_justifications(m, lag_justifications)
            lag_visible_keys = body.get('lag_visible_keys')
            if module == 'lag_lead' and lag_visible_keys is not None:
                # On-screen filter honoured in the export — findings only; the row-detail
                # columns already exist here (Lag (wd), Flags). No caption row: write_xlsx
                # has no title/caption argument (see p6_evm/xlsx_writer.py — read-only).
                m = filter_lag_findings(m, lag_visible_keys)
            if module == 'hard_constraints' and not m.get('baseline_milestones') \
                    and isinstance(body.get('baseline_milestones'), list):
                # the schedule's own milestones are an on-screen list (not stored) — the client sends it
                m = dict(m, baseline_milestones=body['baseline_milestones'])
            headers, rows = excel_columns(m)
            sev_col, legend = excel_severity_meta(m, headers)
            # Sheet 1 = the findings register (unchanged); then the rest of the report — score,
            # key figures, severity rules, by-WBS table, milestones — so the workbook carries
            # everything the screen / PDF show (owner comment 29).
            from p6_evm.xlsx_writer import write_sections_xlsx, _sheet
            from p6_audit.excel_sheets import extra_sheets
            findings_xml = _sheet(headers, rows, excel_highlight_cols(headers), sev_col, legend,
                                  meta=_excel_meta(m.get('name') or 'Schedule Health Review',
                                                   m, snapshot_id=snapshot_id))
            write_sections_xlsx(os.path.abspath(output_path),
                                [{'name': (m.get('name') or 'Schedule Health Review')[:31],
                                  'xml': findings_xml}] + extra_sheets(m))
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
            from p6_audit.exporters import filter_lag_findings
            import subprocess, tempfile
            _theme = report_theme.normalize(body.get('theme'))
            lag_justifications = body.get('lag_justifications')
            if not is_summary and module == 'lag_lead' and lag_justifications:
                # Print the on-screen justifications (typed or saved) — the DB module has none
                # (merged only on parse / project-load), so the PDF register would be blank
                # otherwise. Applied before the filter so surviving rows carry their reasons.
                from p6_audit.modules.lag_lead import apply_justifications
                apply_justifications(m, lag_justifications)
            lag_visible_keys = body.get('lag_visible_keys')
            if not is_summary and module == 'lag_lead' and lag_visible_keys is not None:
                # On-screen filter honoured in the PDF — register (findings) only; charts/KPIs
                # read m['kpis']/m['wbs_summary'], untouched by filter_lag_findings, so they
                # stay whole-schedule even though the register narrows.
                m = filter_lag_findings(m, lag_visible_keys)
            html_content = (render_summary_report(summary_health, meta_in, sections=body.get('sections'),
                                                   modules=(mods or {}).get('modules'),
                                                   completion_float=body.get('completion_float'), theme=_theme)
                            if is_summary else render_module_report(m, meta_in, sections=body.get('sections'), theme=_theme,
                                                                     lag_caption=body.get('lag_filter_caption')))
            if preview:
                self._json(200, {'ok': True, 'html': _with_parts(html_content)})
                return
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name
            chrome = _find_chrome()
            out_path = os.path.abspath(output_path)
            _chrome_print_pdf(html_path, out_path, chrome)
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
            data = _schedule_for(resolved, body)   # embedded > attached > self baseline
            config['categories'] = auto_categories(data)
            result = compute(data, config, classifier=build_wbs_classifier(data))
            self._json(200, {'ok': True, 'gap': gap_by_code(result['records'], dim)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/e1/inspect · /api/e1/preview · /api/e1/ai-suggest ─────────────
    @staticmethod
    def _elog_store_dir():
        """Per-user memory of confirmed engineering-log layouts (next to the DB)."""
        return os.path.join(db.app_data_dir(), 'elog_layouts')

    @staticmethod
    def _e1_paths(body):
        paths = body.get('paths') or ([body['path']] if body.get('path') else [])
        return [p for p in paths if isinstance(p, str) and p and os.path.isfile(p)]

    def _handle_e1_inspect(self, body):
        """Read the chosen log file(s) and PROPOSE how to count them — sheets, what each
        column means (with how sure), the review codes and a preview per discipline.
        Nothing is saved; the planner confirms (or corrects) before /api/e1/upload."""
        paths = self._e1_paths(body)
        if not paths:
            self._json(200, {'ok': False, 'error': 'No log file found.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm import elog_smart
            files = []
            for p in paths:
                try:
                    files.append(elog_smart.inspect_log(p, store_dir=self._elog_store_dir()))
                except Exception as exc:              # one unreadable file must not hide the rest
                    files.append({'file': os.path.basename(p), 'path': p, 'error': str(exc)})
            self._json(200, {'ok': True, 'files': files, 'ai_ready': elog_smart.local_ai_ready()})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_e1_preview(self, body):
        """Re-count one file with the planner's edited layout (column / sheet / code changes)."""
        paths = self._e1_paths(body)
        layout = body.get('layout')
        if not paths or not isinstance(layout, dict):
            self._json(200, {'ok': False, 'error': 'No log file or layout given.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm import elog_smart
            self._json(200, {'ok': True, 'layout': elog_smart.refresh_layout(paths[0], layout)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_e1_ai_suggest(self, body):
        """Optional second opinion from the OFFLINE AI brain on low-confidence columns only.
        Never a cloud call; with no brain installed the layout comes back unchanged."""
        layout = body.get('layout')
        if not isinstance(layout, dict):
            self._json(200, {'ok': False, 'error': 'No layout given.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm import elog_smart
            if not elog_smart.local_ai_ready():
                self._json(200, {'ok': False, 'error': 'The offline AI brain is not set up on this PC.'})
                return
            self._json(200, {'ok': True, 'layout': elog_smart.suggest_columns_with_local_ai(layout)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/e1/upload ─────────────────────────────────────────────────────
    def _handle_e1_upload(self, body):
        """Read one or more E1 / Design / Shop-drawing log Excels → combined drawings
        summary (Mode A); store per snapshot. A whole file whose NAME says Shop/Design
        tags all its rows to that bucket; a combined log is split by drawing type.
        Optional ``layouts`` ({path: layout} or a list aligned with ``paths``) = the
        planner's CONFIRMED reading from /api/e1/inspect: those files are read with the
        format-agnostic reader (p6_evm.elog_smart) and the layout is remembered for next
        time; files without one keep the original reader."""
        paths = self._e1_paths(body)
        snapshot_id = body.get('snapshot_id')
        if not paths:
            self._json(200, {'ok': False, 'error': 'No Excel log file found.'})
            return
        layouts = body.get('layouts') or {}
        if isinstance(layouts, list):
            raw = body.get('paths') or []
            layouts = {raw[i]: lay for i, lay in enumerate(layouts) if i < len(raw)}
        if not isinstance(layouts, dict):
            layouts = {}
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.e1_log import read_e1_rows, summarize_e1
            from p6_evm.e1_rollup import e1_extras
            from p6_evm.classify import e1_file_bucket
            eng_rows = []
            for p in paths:
                bucket = e1_file_bucket(os.path.basename(p))   # 'design' | 'engineering' | None
                layout = layouts.get(p)
                if isinstance(layout, dict) and layout.get('sheets'):
                    from p6_evm import elog_smart
                    summ = summarize_e1(elog_smart.read_rows(p, layout))
                    try:
                        elog_smart.remember_layout(layout, store_dir=self._elog_store_dir(), path=p)
                    except Exception:
                        pass                          # memory is a convenience, never a blocker
                else:
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
    @staticmethod
    def _evm_numbers(result):
        """The EVM figures the baseline banner merges (from compute() or a refreshed import)."""
        cats = {n: {'weight': c['weight'], 'planned_pct': c['planned_pct'],
                    'actual_pct': c['actual_pct'], 'bac': c['bac'], 'ac': c['ac'],
                    'activity_count': c['activity_count'], 'overridden': c['overridden']}
                for n, c in (result.get('categories') or {}).items()}
        out = {k: result.get(k) for k in ('pv', 'ev', 'spi', 'cpi', 'delay_days',
                                          'overall_planned_pct', 'overall_actual_pct')}
        out['categories'] = cats
        return out

    def _refresh_snapshot(self, sid, resolved, out):
        """Recompute the snapshot IN PLACE through the import pipeline (same code as an import,
        now reading the attached / removed baseline) and hand the fresh result to the UI, so
        every view — EVM, WBS, gap, calendar, audits — and every later feature agree."""
        full = self._parse_pipeline({'refresh_snapshot_id': sid, 'path': resolved})
        if not full.get('ok'):
            raise RuntimeError(full.get('error') or 'recompute failed')
        out.update(self._evm_numbers(full['result']))
        out['result'] = full['result']
        return out

    def _handle_baseline_upload(self, body):
        """Attach a baseline schedule (XER or XML) to the open update — an XER update (P6 never
        writes the baseline rows into an XER) or an XML exported WITHOUT its baseline project.
        Matched by Activity Id, remembered for the snapshot, and the snapshot is recomputed in
        place, so EVERY feature reads the same baseline (p6_evm.baseline: embedded > attached >
        self) — XML-with-baseline == XML + attached baseline == XER + attached baseline."""
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
            from p6_evm.baseline import (resolve_baseline, display_name, baseline_fields,
                                         schedule_baseline)
            fmt = 'XER' if os.path.splitext(body.get('xml_path') or resolved)[1].lower() == '.xer' else 'XML'
            embedded_msg = (f'This {fmt} already carries its baseline project inside it, and that '
                            'baseline is the one used — there is nothing to attach.')

            def _answer(info, total):
                return {'ok': True, 'baseline_name': display_name(bl_path),
                        'matched': info.get('matched') or 0, 'total': total,
                        # the baseline P6 names vs the project attached — a wrong revision is flagged
                        'baseline_expected_name': info.get('expected_name'),
                        'baseline_attached_project': info.get('attached_project'),
                        'baseline_mismatch': bool(info.get('mismatch'))}

            sid = body.get('snapshot_id')
            if sid and db.snapshot_exists(sid):
                # The import pipeline reads the update + this baseline ONCE, refuses / skips before
                # storing anything, else remembers it for the snapshot and recomputes it in place.
                full = self._parse_pipeline({'refresh_snapshot_id': sid, 'path': resolved,
                                             'attach_baseline': bl_path})
                if full.get('code') == 'embedded':
                    self._json(200, {'ok': False, 'code': 'embedded', 'error': embedded_msg})
                    return
                if not full.get('ok'):
                    raise RuntimeError(full.get('error') or 'recompute failed')
                if full.get('code') == 'no_match':    # the wrong project's baseline — never remembered
                    self._json(200, _answer(full['baseline_info'], full['total']))
                    return
                res = full['result']
                out = _answer({'matched': res.get('baseline_matched'),
                               'expected_name': res.get('baseline_expected_name'),
                               'attached_project': res.get('baseline_attached_project'),
                               'mismatch': res.get('baseline_mismatch')}, res.get('activity_count'))
                out['baseline_cached'] = res.get('baseline_path')
                out.update(self._evm_numbers(res))
                out['result'] = res
                self._json(200, out)
                return

            # No snapshot to recompute (nothing stored): read both here, hand back the numbers.
            data = parse_file(resolved)
            if getattr(data, 'baseline_source', None) == 'embedded':
                self._json(200, {'ok': False, 'code': 'embedded', 'error': embedded_msg})
                return
            info = resolve_baseline(data, bl_path, parse_file)
            out = _answer(info, len(data.activities))
            if not out['matched']:                    # the wrong project's baseline — never remembered
                self._json(200, out)
                return
            bl_cached = db.cache_xml(bl_path, db.hash_file(bl_path))
            info['path'] = bl_cached
            out['baseline_cached'] = bl_cached
            # the result's baseline keys (source, label, approx …) for the screen to adopt
            out['baseline_fields'] = {**baseline_fields(info), **schedule_baseline(data)}
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            config['categories'] = auto_categories(data)
            out.update(self._evm_numbers(compute(data, config, classifier=build_wbs_classifier(data))))
            self._json(200, out)
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/baseline/clear ────────────────────────────────────────────────
    def _handle_baseline_clear(self, body):
        """Remove an attached baseline: forget it for this snapshot and recompute the snapshot
        in place — back to the file's own baseline (embedded, else its own Planned dates)."""
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        if not resolved:
            self._json(200, {'ok': False, 'error': 'Schedule not available. Re-import the file.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.metrics import compute
            from p6_evm.classify import auto_categories, build_wbs_classifier
            from p6_evm.baseline import load_schedule
            out = {'ok': True}
            sid = body.get('snapshot_id')
            if sid and db.snapshot_exists(sid):
                db.save_baseline(sid, None)            # forget the attached baseline
                self._refresh_snapshot(sid, resolved, out)
            else:
                with open(resource_path('config.json')) as f:
                    config = json.load(f)
                data = load_schedule(resolved)
                from p6_evm.baseline import baseline_fields, schedule_baseline
                # the result's baseline keys for the screen (source 'self', not null — R3 F11)
                out['baseline_fields'] = {**baseline_fields(getattr(data, 'baseline_info', None)),
                                          **schedule_baseline(data)}
                config['categories'] = auto_categories(data)
                out.update(self._evm_numbers(compute(data, config, classifier=build_wbs_classifier(data))))
            self._json(200, out)
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
            # embedded > attached (for this snapshot, or the one the screen names) > self baseline
            data = _schedule_for(resolved, body, fallback_baseline=body.get('baseline_path'))
            config['categories'] = auto_categories(data, saved_weights=weights)
            result = compute(data, config, classifier=build_wbs_classifier(data))
            meta_in = body.get('meta') or {}
            if body.get('actual_cost') is not None:
                meta_in['actual_cost'] = body.get('actual_cost')
            from p6_evm.baseline import baseline_fields, baseline_label, baseline_approx
            _blf = baseline_fields(getattr(data, 'baseline_info', None))   # labelled, never silent
            meta_in['baseline_label'] = baseline_label(_blf, (data.project or {}).get('baseline_name'))
            meta_in['baseline_approx'] = baseline_approx(_blf)
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
                self._json(200, {'ok': True, 'html': _with_parts(html_content)})
                return
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name
            chrome = _find_chrome()
            _chrome_print_pdf(html_path, os.path.abspath(output_path), chrome)
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
                                                  theme=report_theme.normalize(body.get('theme')),
                                                  feature=body.get('feature', 'calendar'))
            if preview:
                self._json(200, {'ok': True, 'html': _with_parts(html_content)})
                return
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name
            chrome = _find_chrome()
            _chrome_print_pdf(html_path, os.path.abspath(output_path), chrome)
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
            _d = ca.get('dashboard') or {}
            _bl = _d.get('baseline_label') if _d.get('baseline_approx') else None   # approx only
            write_calendar_xlsx(os.path.abspath(output_path), ca, weather=weather,
                                meta=_excel_meta('Calendar Audit', snapshot_id=snapshot_id,
                                                 **({'baseline': _bl} if _bl else {})))
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_weather_excel(self, body):
        """Export the Bad Weather workbook to .xlsx: a construction-calendar month grid with
        the bad-weather days highlighted amber, then the weather tables."""
        snapshot_id = body.get('snapshot_id')
        output_path = body.get('output_path', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        ca = db.get_calendar_audit(snapshot_id) if snapshot_id else None
        if not ca:
            self._json(200, {'ok': False, 'error': 'No calendar audit stored for this schedule.'})
            return
        pid = db.get_project_id_for_snapshot(snapshot_id) if snapshot_id else None
        weather = (db.get_project_settings(pid) or {}).get('last_weather') if pid else None
        if not weather:
            self._json(200, {'ok': False, 'error': 'Set a location and calculate the weather first.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.xlsx_writer import write_weather_xlsx
            write_weather_xlsx(os.path.abspath(output_path), ca, weather,
                               meta=_excel_meta('Bad Weather', snapshot_id=snapshot_id))
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/geocode ───────────────────────────────────────────────────────
    def _handle_geocode(self, body):
        """Place name → coordinates (search), OR lat/lon → place name (reverse), via
        OpenStreetMap Nominatim (server-side: proper User-Agent, dodges browser CORS).
        Free, no key. Reverse is used when the user drops/drags a pin on the map.
        Typed coordinates ("30.0444, 31.2357") are answered locally — no internet needed.
        Offline / service errors come back as {ok:false, offline, error} in plain English."""
        import urllib.parse
        from utils import network_error_message
        lat, lon = body.get('lat'), body.get('lon')
        try:
            if lat is not None and lon is not None:
                fallback = f'{float(lat):.4f}, {float(lon):.4f}'
                try:
                    data = _nominatim_get('reverse', {'lat': lat, 'lon': lon, 'format': 'json',
                                                      'zoom': 13})
                except Exception as exc:     # offline: the pin still works, named by its coordinates
                    self._json(200, {'ok': False, 'offline': True, 'name': fallback,
                                     'error': network_error_message(
                                         exc, 'OpenStreetMap', needs='naming the pinned place')})
                    return
                name = (data or {}).get('display_name') or fallback
                self._json(200, {'ok': True, 'name': name})
                return
            q = (body.get('q') or '').strip()
            if not q:
                self._json(200, {'ok': False, 'error': 'Type a place to search.'})
                return
            coords = _parse_coordinates(q)
            if coords:
                self._json(200, {'ok': True, 'results': [
                    {'name': f'{coords[0]:.4f}, {coords[1]:.4f}', 'lat': coords[0], 'lon': coords[1]}]})
                return
            try:
                data = _nominatim_get('search', {'q': q, 'format': 'json', 'limit': 5})
            except Exception as exc:
                self._json(200, {'ok': False, 'offline': True, 'error': network_error_message(
                    exc, 'OpenStreetMap', needs='the place search') + (
                    ' Offline, type the site coordinates instead (e.g. 26.9598, 49.5687).')})
                return
            results = [{'name': x.get('display_name'), 'lat': float(x['lat']), 'lon': float(x['lon'])}
                       for x in (data or []) if isinstance(x, dict) and 'lat' in x and 'lon' in x]
            self._json(200, {'ok': True, 'results': results})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': f'The place search failed: {exc}'})

    # ── /api/weather ───────────────────────────────────────────────────────
    def _handle_weather(self, body):
        """Compute the Weather Impact for a location. Re-parses the schedule (needs
        construction calendars + milestones), fetches historical/forecast weather,
        and returns the estimate. Saves the location per project. When the weather could
        not be downloaded (offline / Open-Meteo down) it answers {ok:false, offline, error}
        with a plain message and KEEPS the last good estimate — an empty download is never
        presented (or saved) as a zero-impact result. Partial gaps (live forecast / dust
        forecast unavailable) are listed in climate_reference.gaps (screen + PDF)."""
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
            from p6_calendar.weather import (weather_inputs, build_daily_weather,
                                             weather_impact, resolve_site_thresholds)
            with open(resource_path('config.json')) as f:
                config = json.load(f)
            sid = body.get('snapshot_id')
            pid = db.get_project_id_for_snapshot(sid) if sid else None
            saved = db.get_project_settings(pid) if pid else {}
            # Site type (Marine/Port, Desert, …) — one pick loads the limits that fit the work.
            site_type = body.get('site_type') or saved.get('site_type')
            # Stop-work limits: this request's edits win, else the picked site-type preset,
            # else the project's saved limits, else the app defaults (rain>=5 / heat>=42 /
            # dust on / wind off = the Desert preset).
            thresholds = (body.get('thresholds')
                          or (resolve_site_thresholds(site_type) if site_type else None)
                          or saved.get('weather_thresholds')
                          or config.get('weather_thresholds'))
            data = _schedule_for(resolved, body)   # embedded > attached > self baseline
            inp = weather_inputs(data)
            if not inp['data_date'] or not inp['project_finish']:
                self._json(200, {'ok': False, 'error': 'Schedule has no usable start/finish dates.'})
                return
            net = {}
            daily, climate_samples, horizon, climate_meta = build_daily_weather(
                lat, lon, inp['data_date'], inp['project_finish'], net=net)
            location = {'lat': lat, 'lon': lon, 'name': body.get('place_name', '')}
            # The location, site type and edited limits are the planner's settings — keep them
            # even when the weather itself could not be downloaded.
            patch = {'location': location}
            if site_type is not None:
                patch['site_type'] = site_type
            if body.get('thresholds'):
                patch['weather_thresholds'] = body['thresholds']
            gap = _weather_download_gap(net, daily, climate_samples)
            if gap:
                # Never present (or save) an empty download as a zero-impact estimate: tell
                # the planner plainly and keep the last good estimate as it was.
                if pid:
                    db.save_project_settings(pid, patch)
                self._json(200, {'ok': False, 'offline': bool(net.get('offline')),
                                 'error': gap, 'location': location,
                                 'kept_previous': bool(saved.get('last_weather')),
                                 'settings_saved': bool(pid)})
                return
            wx = weather_impact(**inp, daily_weather=daily, forecast_horizon=horizon,
                                thresholds=thresholds, site_type=site_type,
                                climate_samples=climate_samples, climate_meta=climate_meta)
            # Fill the climate reference's location so the user sees exactly where it applies.
            if isinstance(wx.get('climate_reference'), dict):
                wx['climate_reference'].update({'lat': lat, 'lon': lon,
                                                'place_name': body.get('place_name', ''),
                                                'gaps': _weather_partial_gaps(net)})
            if pid:
                # Persist location, the site type, the edited limits, and the latest weather
                # (so re-opening restores the picker and the PDF can include it).
                patch['last_weather'] = wx
                db.save_project_settings(pid, patch)
            self._json(200, {'ok': True, 'weather': wx, 'location': location,
                             'offline': False})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/calendar/settings ─────────────────────────────────────────────
    def _handle_calendar_settings(self, body):
        """Persist per-project Calendar Audit settings (location / manual shutdowns /
        shutdown reasons / working-hours notes) and recompute the calendar audit so the
        changes show at once."""
        sid = body.get('snapshot_id')
        pid = db.get_project_id_for_snapshot(sid) if sid else None
        if not pid:
            self._json(200, {'ok': False, 'error': 'Open a schedule first.'})
            return
        patch = {k: body[k] for k in ('location', 'manual_shutdowns', 'shutdown_reasons',
                                      'hours_notes')
                 if body.get(k) is not None}
        # Reasons / hours notes are edited ONE row at a time: merge into what is saved
        # (a blank text clears that row) instead of replacing the whole set — before, each
        # edit silently wiped every other row's saved reason.
        saved = db.get_project_settings(pid)
        for k in ('shutdown_reasons', 'hours_notes'):
            if isinstance(patch.get(k), dict):
                merged = dict(saved.get(k) or {})
                for rk, rv in patch[k].items():
                    if rv is None or (isinstance(rv, str) and not rv.strip()):
                        merged.pop(rk, None)
                    else:
                        merged[rk] = rv
                patch[k] = merged
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
                ca = calendar_audit(_schedule_for(resolved, body), config, settings)   # embedded > attached > self
                if sid:
                    db.save_calendar_audit(sid, ca)
            except Exception as cexc:
                print(f'[calendar] settings recompute skipped: {cexc}', file=sys.stderr)
        self._json(200, {'ok': True, 'settings': settings, 'calendar_audit': ca})

    # ── /api/project/evm-setup ──────────────────────────────────────────────
    def _handle_evm_setup(self, body):
        """Save Project Setup (category weights + Actual Cost override) for the project the
        snapshot belongs to. Held in the project's settings (keyed by project id, so two
        projects with the same name never share them) and returned by /api/parse and
        /api/project/load as calendar_settings.evm_setup — it survives re-opening the
        project, re-importing an update and restarting the app (the web view's own storage
        does not). Answers {ok, evm_setup} or {ok:false, error} in plain English."""
        sid = body.get('snapshot_id')
        pid = db.get_project_id_for_snapshot(sid) if sid else None
        if not pid:
            self._json(200, {'ok': False, 'error': 'Open a schedule first.'})
            return
        try:
            setup = clean_evm_setup(body.get('weights'), body.get('actual_cost'))
        except ValueError as exc:
            self._json(200, {'ok': False, 'error': str(exc)})
            return
        db.save_project_settings(pid, {'evm_setup': setup})
        self._json(200, {'ok': True, 'evm_setup': setup})

    # ── /api/narrative/setup ────────────────────────────────────────────────
    _NARRATIVE_SETUP_MAX = 40 * 1024 * 1024      # JSON chars: logos + a large layout drawing

    def _handle_narrative_setup(self, body):
        """The Baseline Narrative project setup (parties, contract details, logos, layout
        drawing) for one imported schedule, kept in the database. It used to live only in
        the web view's storage, which is empty after every restart, and its images are too
        big for ui_prefs.json (a value over 512 KB was skipped, losing the whole setup).
        {snapshot_id} -> {ok, setup|None}; {snapshot_id, setup} saves (setup null clears).
        A schedule with no setup of its own yet (a re-import or the project's next update)
        gets the project's most recently saved one, marked inherited (R2 S6); the first
        change saves it under this schedule."""
        sid = body.get('snapshot_id') if isinstance(body, dict) else None
        if not sid or not db.get_project_id_for_snapshot(sid):
            self._json(200, {'ok': False, 'error': 'Open a schedule first.'})
            return
        if 'setup' not in body:
            setup, src = db.get_snapshot_ui_state_inherited(sid, 'narrative_setup')
            self._json(200, {'ok': True, 'setup': setup,
                             **({'inherited': True, 'from_snapshot_id': src} if src else {})})
            return
        setup = body.get('setup')
        if setup is not None and not isinstance(setup, dict):
            self._json(200, {'ok': False, 'error': 'The project setup was not understood.'})
            return
        if setup is not None and len(json.dumps(setup)) > self._NARRATIVE_SETUP_MAX:
            self._json(200, {'ok': False, 'error': 'The logos and layout drawing are too large '
                                                   'to keep (over 40 MB). Use smaller images.'})
            return
        try:
            db.save_snapshot_ui_state(sid, 'narrative_setup', setup or None)
        except Exception as exc:                  # noqa: BLE001 — DB busy/locked: page retries
            app_startup.log('narrative setup not saved (%r)', exc)
            self._json(503, {'ok': False, 'error': 'The database is busy; the setup was not '
                                                   'saved yet.'})
            return
        self._json(200, {'ok': True})

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
        # only complete rows ({name, date} text) are kept — a stray blank row never wipes the list
        milestones = [{'name': str(m.get('name') or '').strip(), 'date': str(m.get('date') or '').strip()}
                      for m in (body.get('milestones') or []) if isinstance(m, dict)]
        milestones = [m for m in milestones if m['name'] and m['date']]
        try:
            db.save_contract_milestones(pid, milestones)
        except Exception as sexc:                       # DB busy/locked -> say so, keep the old list
            self._json(200, {'ok': False, 'error': 'Your contract milestones could not be saved '
                                                   f'just now ({sexc}) — please press Run again.'})
            return
        module = None
        health = None
        eval_error = None
        resolved = db.get_snapshot_xml_path(sid)
        if not resolved:
            eval_error = ('the schedule file for this project could not be found '
                          '(re-import it to check them)')
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
                data = _schedule_for(resolved, body)   # embedded > attached > self baseline
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
                eval_error = f'the schedule could not be read ({mexc})'
        out = {'ok': True, 'saved': True, 'milestones': milestones,
               'milestone_module': module, 'health': health}
        if module is None and eval_error:
            out['error'] = eval_error
        self._json(200, out)

    # ── /api/history ───────────────────────────────────────────────────────
    # ── /api/export/{pdf,html,docx,xlsx} — ONE-DOCUMENT exports ─────────────
    def _handle_export_document(self, body, kind):
        """Every output of the Report Contents picker is built from the ONE final report
        HTML the preview shows (feature render + appearance mode + ticked parts, in the
        chosen order) — so PDF · Word · HTML · Excel cannot diverge (p6_export).

        body: {html, output_path, title?, meta?: {feature?, project?, data_date?}, sections?}
        Returns {ok, path} or {ok: False, error}."""
        output_path = (body.get('output_path') or '').strip()
        html_content = body.get('html') or ''
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        if not html_content.strip():
            self._json(200, {'ok': False, 'error': 'Nothing to export — the report is empty.'})
            return
        meta = body.get('meta') or {}
        title = (body.get('title') or meta.get('feature') or '').strip()
        feature = (meta.get('feature') or title or '').strip()
        project = (meta.get('project') or '').strip()

        def chrome():
            try:
                return _find_chrome()
            except Exception:
                return None
        try:
            sys.path.insert(0, resource_path('.'))
            if kind == 'pdf':
                from p6_export.pdf import html_to_pdf
                html_to_pdf(html_content, output_path, chrome=chrome())
            elif kind == 'html':
                from p6_export.to_html import write_html
                write_html(html_content, output_path, title=title or APP_NAME)
            elif kind == 'docx':
                from p6_export.to_docx import html_to_docx
                from p6_export.auto_visuals import mark_visuals
                # charts / tile groups built of styled divs go to Word as pictures (comment 2)
                html_content = mark_visuals(html_content)
                html_to_docx(html_content, output_path, app_name=APP_NAME, feature=feature,
                             project=project, chrome=chrome(), sections=body.get('sections'))
            elif kind == 'xlsx':
                from p6_export.to_xlsx import html_to_xlsx
                from p6_export.auto_visuals import mark_visuals
                html_content = mark_visuals(html_content)   # … and to Excel as their numbers
                html_to_xlsx(html_content, output_path, app_name=APP_NAME, feature=feature,
                             project=project, data_date=(meta.get('data_date') or ''),
                             sections=body.get('sections'))
            else:
                self._json(200, {'ok': False, 'error': f'Unknown export type: {kind}'})
                return
            self._json(200, {'ok': True, 'path': output_path})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_report_html(self, body):
        """Generic 'print this view' → PDF. The client composes a self-contained HTML
        document (app stylesheet inlined, light theme, only the ticked sections) so
        Preview == PDF == Print; this route just renders it with headless Chrome.
        Every screen view prints through here via the shared printView() helper."""
        output_path = body.get('output_path', '')
        html_content = body.get('html', '')
        if not output_path:
            self._json(200, {'ok': False, 'error': 'No output path provided'})
            return
        if not html_content:
            self._json(200, {'ok': False, 'error': 'Nothing to print — the report was empty.'})
            return
        try:
            html_content = report_theme.with_pagination(html_content)   # shared pagination rules
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(html_content)
                html_path = tmp.name
            chrome = _find_chrome()
            _chrome_print_pdf(html_path, os.path.abspath(output_path), chrome)
            os.unlink(html_path)
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

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

    # ── /api/chat/* — Offline AI Chat ────────────────────────────────────────
    def _chat_result(self, body):
        """Resolve the open project's computed result for grounding (DB read path,
        falling back to a client-supplied result)."""
        result = body.get('result')
        snap = body.get('snapshot_id')
        if not result and snap is not None:
            pid = db.snapshot_project_id(snap)
            if pid is not None:
                result = db.get_project_result(pid)
        return result

    def _handle_chat_library(self):
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            self._json(200, {'ok': True, **p6_chat.get_library()})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_status(self):
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            self._json(200, {'ok': True, 'brain': p6_chat.brain_status()})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_ask(self, body):
        """Stream the answer as NDJSON: {"delta": "..."} lines while the local brain
        writes, then a final {"done": true, ...meta} line with charts/source/brain.
        Streaming keeps long, detailed answers usable (they appear as they're
        written) even though generation runs locally on the CPU."""
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            meta, gen = p6_chat.answer_stream(body.get('question'),
                                              self._chat_result(body) or {},
                                              role=body.get('role'))
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})
            return
        if not meta.get('ok'):
            self._json(200, meta)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-ndjson')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

        def write(obj):
            self.wfile.write((json.dumps(obj, cls=_Encoder) + '\n').encode())
            self.wfile.flush()
        try:
            for delta in gen:
                write({'delta': delta})
        except Exception as exc:
            try:
                write({'delta': '\n\n_(stream error: %s)_' % exc})
            except Exception:
                return                                    # client gone — nothing to send
        final = {'done': True}
        final.update({k: v for k, v in meta.items() if k != 'ok'})
        try:
            write(final)
        except Exception:
            pass

    def _handle_chat_setup(self, body):
        """Kick off the one-time model download in the background and return at once;
        the UI polls /api/chat/status and enables the chat when the brain is ready."""
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat, threading
            threading.Thread(target=p6_chat.brain_setup, args=(body.get('model'),),
                             daemon=True).start()
            self._json(200, {'ok': True, 'started': True,
                             'note': 'Downloading the AI brain — this can take several '
                                     'minutes on first setup. It runs in the background; '
                                     'the chat enables itself when it finishes.'})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_settings(self, body):
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            s = p6_chat.save_brain_settings(base_url=body.get('base_url'), model=body.get('model'))
            self._json(200, {'ok': True, 'settings': s, 'brain': p6_chat.brain_status()})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_dashboard(self, body):
        """Build the in-chat professional dashboard. Re-parses the open snapshot's XML
        (the report/PDF exception to the DB read path — the charts need the full
        ScheduleData) and reuses the existing engines; every number is grounded."""
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            xml_path = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
            snap = body.get('snapshot_id')
            if not xml_path and snap is not None:
                xml_path = db.get_snapshot_xml_path(snap)
            if not xml_path:
                self._json(200, {'ok': False, 'error': 'Import a P6 schedule first, then ask me to build the dashboard.'})
                return
            self._json(200, p6_chat.build_dashboard(xml_path=xml_path, snapshot_id=snap))
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/chat/copilot/* — Offline AI Chat ▸ the AI Copilot engines ───────
    def _chat_copilot_xml(self, body):
        """Resolve the open snapshot's XML the same way _handle_chat_dashboard does
        (original → cached → best-for-snapshot). Returns the path or None."""
        xml_path = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        snap = body.get('snapshot_id')
        if not xml_path and snap is not None:
            xml_path = db.get_snapshot_xml_path(snap)
        return xml_path

    def _handle_chat_library2(self):
        """The 15 merged questions for the chat drawer (each with its topics and original sub-questions)."""
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            self._json(200, p6_chat.library15())
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_qa2(self, body):
        """One of the 15 merged questions, answered in full from the DB facts + the network re-read from
        the P6 file (the sanctioned report exception), no model."""
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            self._json(200, p6_chat.answer_merged(
                body.get('snapshot_id'), body.get('question_id'), body.get('mode', 'planning'),
                focus=body.get('focus'), followup=body.get('followup')))
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_ask2(self, body):
        """A typed question: routed to the right merged answer and sub-question, then answered."""
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            self._json(200, p6_chat.ask_text(
                body.get('snapshot_id'), body.get('question_text') or '', body.get('mode', 'planning'),
                last_qid=body.get('last_qid')))
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_qa(self, body):
        """Answer one library question by its id from the offline grounded engine
        (p6_chat.qa) — a detailed, senior-planning-engineer answer, DB read path, no model."""
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            self._json(200, p6_chat.answer_question(
                body.get('snapshot_id'),
                body.get('question_id'),
                body.get('mode', 'management')))
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_copilot_ask(self, body):
        """Answer one Copilot question (repertoire button or free-typed) for the loaded
        project, from the DB read path — never re-parses."""
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            self._json(200, p6_chat.copilot.ask(
                body.get('snapshot_id'),
                question_id=body.get('question_id'),
                question_text=body.get('question_text'),
                mode=body.get('mode', 'management')))
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_copilot_tia(self, body):
        """Finish-slip decomposition + ranked insights for the loaded project (DB read path)."""
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            self._json(200, p6_chat.copilot.tia(body.get('snapshot_id')))
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_copilot_activities(self, body):
        """Activity picker list — re-parses the open snapshot's XML (the report exception)."""
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            xml_path = self._chat_copilot_xml(body)
            if not xml_path:
                self._json(200, {'ok': False, 'error': 'Import a P6 schedule first, then try again.'})
                return
            self._json(200, p6_chat.copilot.activities(xml_path))
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_copilot_whatif(self, body):
        """Instant offline what-if estimate — re-parses the open snapshot's XML."""
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            xml_path = self._chat_copilot_xml(body)
            if not xml_path:
                self._json(200, {'ok': False, 'error': 'Import a P6 schedule first, then try again.'})
                return
            self._json(200, p6_chat.copilot.whatif(
                xml_path, body.get('kind'),
                activity_id=body.get('activity_id'), days=body.get('days')))
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_copilot_scenario(self, body):
        """Write a what-if scenario programme for the planner to F9 — re-parses the XML."""
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            xml_path = self._chat_copilot_xml(body)
            if not xml_path:
                self._json(200, {'ok': False, 'error': 'Import a P6 schedule first, then try again.'})
                return
            self._json(200, p6_chat.copilot.scenario(
                xml_path, body.get('kind'),
                activity_id=body.get('activity_id'), days=body.get('days'),
                output_path=body.get('output_path', ''), label=body.get('label')))
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_copilot_impact(self, body):
        """Read P6's exact TIA impact (base vs the F9-rescheduled file) — re-parses both."""
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            xml_path = self._chat_copilot_xml(body)
            if not xml_path:
                self._json(200, {'ok': False, 'error': 'Base schedule not found — re-import it and try again.'})
                return
            self._json(200, p6_chat.copilot.impact(xml_path, body.get('rescheduled_path', '')))
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_chat_copilot_report(self, body):
        """Build the Manager Report — preview HTML (default) or a written PDF. The XML is
        resolved best-effort for the drivers/recovery enrichment (only used when behind)."""
        try:
            sys.path.insert(0, resource_path('.'))
            import p6_chat
            self._json(200, p6_chat.copilot.manager_report(
                body.get('snapshot_id'),
                xml_path=self._chat_copilot_xml(body),
                preview=bool(body.get('preview')),
                output_path=body.get('output_path', ''),
                meta=body.get('meta')))
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/narrative ────────────────────────────────────────────────────
    def _handle_narrative(self, body):
        """Baseline Narrative — assemble the Basis-of-Schedule document from the
        parsed baseline. Re-parses, pulls the Calendar feature's report and the full
        activity-code catalog, and returns the document model + rendered HTML. A thin
        assembler over the existing engines — recomputes no number. No `records`."""
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        if not resolved:
            self._json(200, {'ok': False, 'error': 'Schedule not found — re-import it and try again.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_narrative.report import build_report
            from p6_narrative.html import render_narrative_html
            data = parse_file(resolved)

            # v5 Narrative Report — driven by the Schedule-Intelligence front detector.
            # A read-only study of the baseline; recomputes no EVM number.
            doc = build_report(data, path=resolved, setup=body.get('setup'))
            doc_dict = doc.to_dict()
            self._json(200, {'ok': True, 'doc': doc_dict,
                             'html': render_narrative_html(doc_dict), 'counts': doc.counts()})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/narrative/choices ────────────────────────────────────────────
    def _handle_narrative_choices(self, body):
        """LIGHTWEIGHT detection for the conversational setup — resolve + parse the
        baseline exactly like ``/api/narrative``, but return ONLY the detected choices
        (milestones, key dates, activity codes, scope cascade, project name/count,
        contract value) WITHOUT building any of the report's sections. Lets the chat
        pre-fill its questions fast; the full report is built once, at Generate."""
        resolved = db.resolve_xml_path(body.get('xml_path', ''), body.get('cached_path'))
        if not resolved:
            self._json(200, {'ok': False, 'error': 'Schedule not found — re-import it and try again.'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            from p6_narrative import report
            data = parse_file(resolved)
            setup = body.get('setup') or {}
            self._json(200, {'ok': True, 'meta': report.narrative_choices(data, setup)})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/narrative/docx ───────────────────────────────────────────────
    def _handle_narrative_docx(self, body):
        """Write the (possibly user-edited) narrative to an editable Word file. The
        client holds the document and applies in-app prose edits, so no re-parse."""
        doc_dict = body.get('doc')
        output_path = body.get('output_path', '')
        if not doc_dict or not output_path:
            self._json(200, {'ok': False, 'error': 'Missing document or output path'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_narrative.builder import apply_edits
            from p6_narrative.docx_writer import write_docx
            write_docx(apply_edits(doc_dict, body.get('edits')), os.path.abspath(output_path),
                       chrome=_find_chrome())
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/narrative/pdf ────────────────────────────────────────────────
    def _handle_narrative_pdf(self, body):
        """Render the (edited) narrative to PDF via Chrome headless — same pipeline
        as the other reports, so the PDF reflects the user's on-screen edits.

        TWO-PASS so the Table of Contents can carry the sections' real physical page
        numbers (a section that overflows onto a later sheet still lists the page you
        turn to): pass-1 renders with ordinal TOC numbers, PyMuPDF then locates every
        section heading in that PDF to build a page-map, and pass-2 re-renders the TOC
        with those real pages. If PyMuPDF is unavailable or no heading can be located,
        the pass-1 PDF (ordinal TOC) is kept — no failure, just the earlier behaviour."""
        doc_dict = body.get('doc')
        output_path = body.get('output_path', '')
        if not doc_dict or not output_path:
            self._json(200, {'ok': False, 'error': 'Missing document or output path'})
            return
        try:
            import subprocess, tempfile
            sys.path.insert(0, resource_path('.'))
            from p6_narrative.builder import apply_edits
            from p6_narrative.html import page_html
            edited = apply_edits(doc_dict, body.get('edits'))
            chrome = _find_chrome()
            out = os.path.abspath(output_path)

            def _render_pdf(html_str, out_pdf):
                with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w',
                                                 encoding='utf-8') as tmp:
                    tmp.write(html_str)
                    html_path = tmp.name
                try:
                    _chrome_print_pdf(html_path, out_pdf, chrome)
                finally:
                    try:
                        os.unlink(html_path)
                    except OSError:
                        pass

            # pass 1 — ordinal TOC, into a temp PDF used only for measuring page numbers
            pass1 = out + '.pass1.pdf'
            _render_pdf(page_html(edited), pass1)

            page_map = None
            try:
                page_map = _narrative_page_map(pass1, edited.get('sections') or [])
            except Exception:
                page_map = None

            if page_map:
                # pass 2 — TOC stamped with real physical pages
                _render_pdf(page_html(edited, page_map=page_map), out)
                try:
                    os.unlink(pass1)
                except OSError:
                    pass
            else:
                # keep the pass-1 PDF (ordinal TOC) as the deliverable
                os.replace(pass1, out)

            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    # ── /api/narrative/html ───────────────────────────────────────────────
    def _handle_narrative_html(self, body):
        """Write the (edited) narrative as a self-contained HTML file — the same
        HTML the PDF export builds, minus the Chrome print step. page_html returns
        a full <!doctype html> document with inline CSS + data-URI logos, so the
        single file needs no external assets."""
        doc_dict = body.get('doc')
        output_path = body.get('output_path')
        if not doc_dict or not output_path:
            self._json(200, {'ok': False, 'error': 'Missing document or output path'})
            return
        try:
            sys.path.insert(0, resource_path('.'))
            from p6_narrative.builder import apply_edits
            from p6_narrative.html import page_html
            with open(os.path.abspath(output_path), 'w', encoding='utf-8') as f:
                f.write(page_html(apply_edits(doc_dict, body.get('edits'))))
            self._json(200, {'ok': True})
        except Exception as exc:
            self._json(200, {'ok': False, 'error': str(exc)})

    def _handle_history(self):
        try:
            rows = db.get_recent_projects(limit=10)
        except Exception as exc:          # a damaged/locked DB: answer, don't drop the socket
            app_startup.log('history unavailable: %s', repr(exc))   # text only: a kept record
            # holding the exception would pin the failed connection (and the damaged file)
            damaged = db.note_error(exc)
            self._json(503, {'ok': False, 'error': f'Recent projects could not be read: {exc}',
                             'damaged': damaged, 'db': dict(db.DB_STATUS)})
            return
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
# ONE tool-wide browser helper (p6_export.pdf): every candidate is PROBED once (a real
# one-line headless print) and the first that works is cached for the session —
# installed Google Chrome → Microsoft Edge → Chromium → Playwright headless shell →
# Playwright full Chromium last (on the owner's PC that one fails to start with
# "[WinError 14001] side-by-side configuration is incorrect"; it used to be tried FIRST
# with no fallback, so every per-feature PDF route could fail).

def _export_pkg():
    root = resource_path('.')
    if root not in sys.path:
        sys.path.insert(0, root)
    from p6_export import pdf
    return pdf


def _find_chrome():
    """The Chrome/Edge/Chromium this machine can actually print with (probed once, cached).
    Raises a clear error when none works."""
    path = _export_pkg().find_working_chrome()
    if path:
        return path
    raise RuntimeError('No working Chrome, Edge or Chromium found to print the PDF. '
                       'Install Google Chrome or Microsoft Edge and try again.')


def _chrome_print_pdf(html_path, output_path, chrome=None, timeout=300):
    """Print a report HTML file to ``output_path`` — EVERY PDF route goes through here
    (p6_export.pdf.run_chrome: the cached browser first, then the next candidate when one
    cannot start or writes nothing)."""
    return _export_pkg().print_html_file(html_path, output_path, chrome=chrome, timeout=timeout)


def _narrative_page_map(pdf_path, sections):
    """Second half of the Baseline-Narrative two-pass PDF export: open the pass-1 PDF
    with PyMuPDF and locate each section's real physical page by its ``"N) Title"``
    heading text, returning ``{section_number: physical_page}`` (1-based) for the TOC.

    Front matter (cover + Table of Contents) is skipped so a section title that also
    appears in the TOC never yields a false match. Headings are matched in body order
    with a forward pointer (every section starts on its own sheet), and whitespace is
    normalised so a wrapped or re-spaced heading still matches. Returns ``None`` if
    nothing could be located (caller then keeps the pass-1 ordinals)."""
    import pymupdf
    pdf = pymupdf.open(pdf_path)
    try:
        texts = [' '.join((pdf[i].get_text() or '').split()) for i in range(pdf.page_count)]
    finally:
        pdf.close()
    start = 0
    for i, t in enumerate(texts):                       # first body page = after the TOC
        if 'Table of Contents' in t:
            start = i + 1
    page_map, ptr = {}, start
    for s in sections or []:
        if not s:
            continue
        num = str(s.get('number'))
        heading = ' '.join(('%s) %s' % (num, s.get('title') or '')).split())
        if s.get('appendix') or s.get('cover'):          # appendix titles print without "N)"
            heading = ' '.join((s.get('title') or '').split())
        if not heading:
            continue
        found = next((i for i in range(ptr, len(texts)) if heading in texts[i]), None)
        if found is None:                               # relax: anywhere in the body
            found = next((i for i in range(start, len(texts)) if heading in texts[i]), None)
        if found is not None:
            page_map[num] = found + 1                    # 1-based physical page
            ptr = found + 1
    return page_map or None


# ── Startup: static-file reads, startup guard, loopback server ────────────

def _read_ui_file(path, attempts=4, delays=(0.1, 0.25, 0.5)):
    """Read a bundled UI file, retrying transient OSErrors (antivirus sharing violations
    on the files PyInstaller has just unpacked). FileNotFoundError is not retried."""
    import time as _time
    for i in range(attempts):
        try:
            with open(path, 'rb') as f:
                return f.read()
        except FileNotFoundError:
            raise
        except OSError:
            if i == attempts - 1:
                raise
            _time.sleep(delays[min(i, len(delays) - 1)])


_GUARD_MARK = '<!--cx:startup-guard-->'


def _ui_prefs_dir():
    """Where ui_prefs.json lives: the per-user app data folder, beside the database
    (db.app_data_dir, so a test's temporary data folder holds it too)."""
    return db.app_data_dir()


def _inline_ui_prefs(html):
    """Put the saved screen preferences (window.__UI_PREFS__) and ui/prefs_bridge.js inline
    at the top of <head>, before the early Appearance script and every module, so the saved
    Appearance paints first and each module reads its remembered setting as before. Never
    fails the page: an unreadable store gives {} and a missing bridge file a script tag."""
    try:
        prefs = ui_prefs.load(_ui_prefs_dir())
    except Exception:                                    # noqa: BLE001 — never block the page
        prefs = {}
    head = '<script>window.__UI_PREFS__=' + ui_prefs.script_json(prefs) + ';</script>'
    try:
        js = _read_ui_file(resource_path('ui/prefs_bridge.js')).decode('utf-8')
        head += '<script>' + js.replace('</script', '<\\/script') + '</script>'
    except OSError:
        head += '<script src="/ui/prefs_bridge.js"></script>'
    if _GUARD_MARK in html:
        return html.replace(_GUARD_MARK, _GUARD_MARK + head, 1)
    return html.replace('<head>', '<head>' + head, 1)


_BRAND_RE = None


def _fill_brand(html):
    """Write the product name into every element marked data-brand="name|edition|title"
    in index.html (the start-up screens, the menu bar, the account block, the landing page)
    before the page is sent, so it paints with the name from utils.APP_* - index.html
    itself never hardcodes it (startup audit VER-2)."""
    global _BRAND_RE
    import re
    from html import escape
    if _BRAND_RE is None:
        _BRAND_RE = re.compile(
            r'(<(\w+)\b[^>]*\sdata-brand="(name|edition|title)"[^>]*>)[^<]*(</\2>)')
    values = {'name': APP_NAME, 'edition': APP_EDITION, 'title': APP_TITLE}
    return _BRAND_RE.sub(
        lambda m: m.group(1) + escape(str(values[m.group(3)])) + m.group(4), html)


def _inline_startup_guard(html):
    """Inline ui/startup_guard.js into index.html (at its marker, else before </head>) so
    the startup watchdog runs even when a program file fails to load. If it can't be read,
    fall back to a normal script tag."""
    try:
        js = _read_ui_file(resource_path('ui/startup_guard.js')).decode('utf-8')
        tag = '<script>' + js.replace('</script', '<\\/script') + '</script>'
    except OSError:
        tag = '<script src="/ui/startup_guard.js"></script>'
    if _GUARD_MARK in html:
        return html.replace(_GUARD_MARK, tag, 1)
    return html.replace('</head>', tag + '</head>', 1)


def _starting_page_html():
    """The page served (503) when index.html can't be read yet: the window background
    colour, a visible 'Starting' line, automatic reloads with backoff (count kept in
    sessionStorage, reset after a quiet minute), then an in-page Retry button. Plain ES5,
    no alert/confirm/prompt (WebView2 no-ops); the name comes from utils.APP_NAME."""
    from html import escape
    name = json.dumps(APP_NAME)
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<title>' + escape(APP_TITLE) + '</title>'
        '<style>html,body{margin:0;height:100%;background:#06090f;color:#c3cde3;'
        'font:14px/1.5 "Segoe UI",system-ui,sans-serif}'
        '#w{height:100%;display:flex;align-items:center;justify-content:center;padding:16px;'
        'box-sizing:border-box;text-align:center}#t{color:#fff;font-size:16px;font-weight:600}'
        '#cx-index-retry{display:none;margin:14px auto 0;background:#3b82f6;color:#fff;border:0;'
        'border-radius:8px;padding:8px 18px;font:600 13px/1 "Segoe UI",system-ui,sans-serif;'
        'cursor:pointer}</style>'
        '</head><body><div id="w"><div><div id="t">Starting ' + escape(APP_NAME) + '…</div>'
        '<div id="m">Waiting for the program files to become available.</div>'
        '<button type="button" id="cx-index-retry">Retry</button></div></div>'
        '<script>(function(){var K="cx_index_attempt",D=[1000,2000,3000,5000,8000],n=0,'
        'now=Date.now(),s=null;try{s=window.sessionStorage;var v=JSON.parse(s.getItem(K)||"null");'
        'if(v&&now-v.t<60000)n=v.n;}catch(e){}'
        'var b=document.getElementById("cx-index-retry");'
        'b.onclick=function(){try{s&&s.removeItem(K);}catch(e){}location.reload();};'
        'if(n<D.length){try{s&&s.setItem(K,JSON.stringify({n:n+1,t:now}));}catch(e){}'
        'document.getElementById("m").textContent="Waiting for the program files to become '
        'available — trying again (attempt "+(n+1)+" of "+D.length+").";'
        'setTimeout(function(){location.reload();},D[n]);}'
        'else{document.getElementById("t").textContent=' + name + '+" couldn’t finish starting";'
        'document.getElementById("m").textContent="The program files could not be read (they may '
        'be held by antivirus). Your projects and data are safe. Click Retry; if this keeps '
        'happening, close the app and open it again.";b.style.display="block";}'
        '}());</script></body></html>'
    )


class _LoopbackServer(ThreadingHTTPServer):
    """Loopback-only threaded server. Threaded so a long local-AI generation (the chat
    streams for minutes on a CPU) doesn't block every other request. The listen backlog is
    128, not socketserver's 5: on Windows a full backlog REFUSES the ~40 parallel UI-file
    requests at startup, and one refused module used to mean a black screen."""
    request_queue_size = 128
    daemon_threads = True
    allow_reuse_address = False       # plus SO_EXCLUSIVEADDRUSE: never share a port

    def server_bind(self):
        import socket as _socket
        import socketserver
        if sys.platform == 'win32' and hasattr(_socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(_socket.SOL_SOCKET, _socket.SO_EXCLUSIVEADDRUSE, 1)
        socketserver.TCPServer.server_bind(self)        # skip HTTPServer's getfqdn() lookup
        self.server_name = 'localhost'
        self.server_port = self.server_address[1]

    def handle_error(self, request, client_address):
        # The windowed exe has no stderr: log handler crashes instead of losing them.
        app_startup.log_exception('request handler error (%s)', client_address)


class _LoopbackServer6(_LoopbackServer):
    address_family = __import__('socket').AF_INET6


class _AppServer(_LoopbackServer):
    """127.0.0.1 server with an optional [::1] twin on the SAME port. The window and every
    UI call use http://localhost:PORT; Windows resolves localhost to ::1 first, and a
    connect to a closed ::1 port takes ~2 s to fail before the IPv4 fallback, per request
    (measured 2.8 s vs 0.1 s to DOMContentLoaded). A foreign process listening on
    [::1]:PORT would even have received the page. Owning both addresses fixes both."""
    companion = None
    _companion_running = False

    def serve_forever(self, poll_interval=0.5):
        import threading as _threading
        if self.companion is not None and not self._companion_running:
            self._companion_running = True
            _threading.Thread(target=self.companion.serve_forever, args=(poll_interval,),
                              daemon=True).start()
        super().serve_forever(poll_interval)

    def shutdown(self):
        if self.companion is not None and self._companion_running:
            self.companion.shutdown()
            self._companion_running = False
        super().shutdown()

    def server_close(self):
        if self.companion is not None:
            try:
                self.companion.server_close()
            except OSError:
                pass
        super().server_close()


def _bind_loopback(attempts=8):
    """Bind 127.0.0.1 on a free port and [::1] on the same port. If ::1 is taken on that
    port, try another port; if IPv6 is unavailable, serve IPv4 only (the old behaviour)."""
    import errno
    last = None
    for _ in range(attempts):
        srv = _AppServer(('127.0.0.1', 0), Handler)
        port = srv.server_address[1]
        try:
            srv.companion = _LoopbackServer6(('::1', port), Handler)
            return srv
        except OSError as exc:
            last = exc
            in_use = (exc.errno in (errno.EADDRINUSE, errno.EACCES)
                      or getattr(exc, 'winerror', None) in (10048, 10013))
            if in_use:
                srv.server_close()
                continue                              # someone owns [::1]:port: new port
            app_startup.log('IPv6 loopback unavailable (%r): serving 127.0.0.1 only', exc)
            return srv
    app_startup.log('could not pair [::1] with a port (%r): serving 127.0.0.1 only', last)
    return _AppServer(('127.0.0.1', 0), Handler)


def make_server():
    # Run migration from legacy history.json if it exists
    legacy = os.path.join(exe_dir(), 'history.json')
    try:
        if os.path.exists(legacy):
            db.migrate_history_json(legacy)
    except Exception:
        app_startup.log_exception('legacy history.json migration failed')

    # Never let the database stop the app from opening: a damaged file is set aside and a
    # fresh one created; a locked one is reported as degraded (see /api/health).
    status = db.open_db_resilient()
    app_startup.log('database: %s%s', status.get('status'),
                    (' (' + str(status.get('detail')) + ')') if status.get('detail') else '')
    srv = _bind_loopback()
    app_startup.log('server listening on port %s (%s)', srv.server_address[1],
                    'IPv4 + IPv6 loopback' if srv.companion is not None else 'IPv4 loopback')
    # A file whose DATA pages are damaged opens as 'ok' (S3): check it in the background,
    # after the window has painted; damage is reported through /api/health (db.status).
    if status.get('status') == 'ok':
        db.start_background_check()
    return srv
