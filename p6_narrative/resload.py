"""§13 Resource Loading + §14 Material Resources — generic resource-loading engine.

Reads the baseline resource assignments already parsed onto ``data`` (works for BOTH
P6 .xml and .xer, populated additively by ``p6_evm.parser`` / ``p6_evm.xer``) and turns
them into two section payloads:

* **§13 Resource Loading** — Manpower and Equipment shown as a NUMBER on site per month,
  not raw budgeted units. Manpower converts budgeted man-hours to men
  (``crew = budgeted_hours / activity_working_hours``); the monthly bar is the average
  number of men on site. Equipment auto-detects its basis: when the budgeted quantity is a
  plant COUNT (the common case — ~1 per assignment, so ``qty / hours`` would collapse to
  zero) it is loaded on a count basis (machines on site); when equipment is genuinely
  hour-loaded it converts like manpower. Nothing is hardcoded to a sample project.
* **§14 Material Resources** — one monthly-quantity chart per material resource (top N by
  total), each kept in its own unit (Ton / m³ / no.); quantities are never summed across
  mixed units. Unit-less "material" assignments are the cost model (the contract value) and
  are reported as a note, never charted.

Resource TYPE (Labor/Equip/Mat) and UNIT of measure are the only two fields the main parser
does not keep, so they are read here straight from the file — isolated exactly like
``p6_narrative.codes`` so ``p6_evm`` stays untouched. On any problem the reader returns ``{}``
and the affected section falls back to an honest no-data note.
"""
import re
from collections import defaultdict
from datetime import timedelta
from xml.etree import ElementTree as ET

_ONE = timedelta(days=1)
_MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
_MON_FULL = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
             'August', 'September', 'October', 'November', 'December']

MAT_CHART_CAP = 8          # material resources charted individually (top N by total)
EQUIP_COUNT_THRESHOLD = 0.5  # median implied crew below this ⇒ the qty is a plant count

# Discipline hues shared with the rest of the report (see html._RAMP).
LABOR_HEX = '1F4E79'       # navy
EQUIP_HEX = '2E9E5B'       # green
MAT_HEX = 'E8A33D'         # amber


# ── resource type + unit reader (isolated; p6_evm untouched) ──────────────────
def read_resource_meta(path):
    """``{resource_id: {'type': 'RT_Labor'|'RT_Equip'|'RT_Mat'|None, 'unit': str|None}}``
    read directly from a P6 file. XER ← RSRC (``rsrc_type``, ``unit_id``) + UMEASURE;
    XML ← Resource (``ResourceType``, ``UnitOfMeasureObjectId``) + UnitOfMeasure.
    Returns ``{}`` on any problem."""
    if not path:
        return {}
    try:
        if path.lower().endswith('.xer'):
            return _res_from_xer(path)
        return _res_from_xml(path)
    except Exception:
        return {}


def _short_unit(abbrev, name):
    """The compact unit symbol. P6 stores it in either ``unit_abbrev`` or ``unit_name`` (this
    export inverts the convention), so pick the SHORTER non-empty of the two — 'm3' over
    'METR CUBED', 'no.' over 'Number' — which is generically the symbol on any file."""
    cands = [str(c or '').strip() for c in (abbrev, name)]
    cands = [c for c in cands if c]
    return min(cands, key=len) if cands else None


def _norm_type(raw):
    """Normalise a raw resource-type string to the P6 XER enum used across the engine."""
    s = str(raw or '').strip().lower()
    if not s:
        return None
    if s.startswith('rt_'):                       # already an XER enum
        if 'labor' in s or 'labour' in s:
            return 'RT_Labor'
        if 'equip' in s:
            return 'RT_Equip'
        if 'mat' in s:
            return 'RT_Mat'
        return raw
    if 'nonlabor' in s or 'nonlabour' in s or 'non-labor' in s:  # XML Nonlabor ⇒ equipment
        return 'RT_Equip'
    if s.startswith('labor') or s.startswith('labour'):
        return 'RT_Labor'
    if s.startswith('mat'):
        return 'RT_Mat'
    if 'equip' in s:
        return 'RT_Equip'
    return None


def _res_from_xer(path):
    umeasure, rsrc = {}, {}
    with open(path, encoding='utf-8', errors='replace') as f:
        cols, table = [], None
        for line in f:
            parts = line.rstrip('\n').split('\t')
            tag = parts[0]
            if tag == '%T':
                table, cols = parts[1], []
            elif tag == '%F':
                cols = parts[1:]
            elif tag == '%R':
                row = dict(zip(cols, parts[1:]))
                if table == 'UMEASURE':
                    uid = row.get('unit_id')
                    if uid:
                        umeasure[uid] = _short_unit(row.get('unit_abbrev'), row.get('unit_name'))
                elif table == 'RSRC':
                    rid = row.get('rsrc_id')
                    if rid:
                        rsrc[rid] = {'type': _norm_type(row.get('rsrc_type')),
                                     'unit_id': row.get('unit_id')}
    return {rid: {'type': r['type'], 'unit': umeasure.get(r['unit_id'])}
            for rid, r in rsrc.items()}


def _res_from_xml(path):
    with open(path, encoding='utf-8') as f:
        head = f.read(4000)
    m = re.search(r'xmlns="([^"]+)"', head)
    ns = f'{{{m.group(1)}}}' if m else ''
    root = ET.parse(path).getroot()

    def text(el, name):
        c = el.find(f'{ns}{name}')
        return c.text if c is not None else None

    umeasure = {}
    for u in root.iter(f'{ns}UnitOfMeasure'):
        oid = text(u, 'ObjectId')
        if oid:
            umeasure[oid] = _short_unit(text(u, 'Abbreviation'), text(u, 'Name'))

    out = {}
    for res_el in root.iter(f'{ns}Resource'):
        rid = text(res_el, 'ObjectId')
        if not rid:
            continue
        out[rid] = {'type': _norm_type(text(res_el, 'ResourceType')),
                    'unit': umeasure.get(text(res_el, 'UnitOfMeasureObjectId'))}
    return out


# ── small helpers ─────────────────────────────────────────────────────────────
def _fmt0(n):
    try:
        return '{:,.0f}'.format(round(float(n or 0)))
    except Exception:
        return '0'


def _mlabel(y, m):
    return '%s-%02d' % (_MON[m - 1], y % 100)


def _mfull(y, m):
    return '%s %d' % (_MON_FULL[m - 1], y)


def _day_label(d):
    return '%d %s %d' % (d.day, _MON[d.month - 1], d.year)


def _month_span(a, b):
    """Every ``(year, month)`` from ``a`` to ``b`` inclusive — a CONTIGUOUS monthly axis, so a
    histogram shows idle months as zero rather than compressing the timeline over a gap."""
    out, (y, m), (y1, m1) = [], a, b
    while (y, m) <= (y1, m1):
        out.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _dur_hours(act, ps, pf):
    """Activity working-hours: P6 ``planned_duration`` (already in hours on both formats),
    falling back to inclusive calendar days × 8 when it is missing/zero."""
    try:
        dur = float(act.get('planned_duration') or 0)
    except Exception:
        dur = 0.0
    if dur > 0:
        return dur
    return ((pf.date() - ps.date()).days + 1) * 8.0


# ── record building ───────────────────────────────────────────────────────────
def _records(data, meta):
    """One record per usable assignment: ``{rid, name, rtype, unit, qty, ps, pf, dur_hr}``.
    Assignments with no positive quantity, or no start/finish on their activity, are dropped."""
    activities = getattr(data, 'activities', None) or {}
    resources = getattr(data, 'resources', None) or {}
    assigns = getattr(data, 'assignments_by_activity', None) or {}
    recs = []
    for oid, alist in assigns.items():
        act = activities.get(oid) or {}
        ps, pf = act.get('planned_start'), act.get('planned_finish')
        if not ps or not pf:
            continue
        dur_hr = _dur_hours(act, ps, pf)
        for a in alist or []:
            try:
                qty = float(a.get('budget_units') or 0)
            except Exception:
                qty = 0.0
            if qty <= 0:
                continue
            rid = a.get('resource_id')
            rm = meta.get(rid) or {}
            recs.append({
                'rid': rid,
                'name': a.get('resource_name') or (resources.get(rid) or {}).get('name') or rid or '—',
                'rtype': rm.get('type'),
                'unit': rm.get('unit'),
                'qty': qty,
                'ps': ps, 'pf': pf, 'dur_hr': dur_hr,
            })
    return recs


# ── manpower / equipment profile (number on site per month) ───────────────────
def _basis_for_equipment(recs):
    """Derive whether equipment ``target_qty`` is HOURS (convert like manpower) or a plant
    COUNT (load directly). Median implied crew ``qty/hours`` below the threshold ⇒ the value
    is a count, not hours."""
    ratios = []
    for r in recs:
        dur = r['dur_hr'] or 0
        if dur > 0:
            ratios.append(r['qty'] / dur)
    if not ratios:
        return 'count'
    ratios.sort()
    med = ratios[len(ratios) // 2]
    return 'count' if med < EQUIP_COUNT_THRESHOLD else 'hours'


def _profile(recs, basis):
    """Average number on site per month + per-resource totals. ``basis='hours'`` converts
    ``crew = qty / working-hours``; ``basis='count'`` loads ``qty`` directly."""
    daily = defaultdict(float)
    per_res_daily = defaultdict(lambda: defaultdict(float))
    sigma = defaultdict(float)
    names = {}
    gmin = gmax = None
    for r in recs:
        ps, pf = r['ps'], r['pf']
        if basis == 'hours':
            dur = r['dur_hr'] or 0
            crew = (r['qty'] / dur) if dur > 0 else 0.0
        else:
            crew = r['qty']
        if crew <= 0:
            continue
        s, f = ps.date(), pf.date()
        if f < s:
            f = s
        gmin = ps if (gmin is None or ps < gmin) else gmin
        gmax = pf if (gmax is None or pf > gmax) else gmax
        rid = r['rid']
        names[rid] = r['name']
        sigma[rid] += r['qty']
        d = s
        while d <= f:
            daily[d] += crew
            per_res_daily[rid][d] += crew
            d += _ONE
    if gmin is None or not daily:
        return None

    msum, mcnt = defaultdict(float), defaultdict(int)
    d, end = gmin.date(), gmax.date()
    while d <= end:
        k = (d.year, d.month)
        msum[k] += daily.get(d, 0.0)
        mcnt[k] += 1
        d += _ONE
    span = sorted(msum.keys())
    values = [round(msum[k] / mcnt[k], 2) for k in span]

    pi = max(range(len(values)), key=lambda i: values[i])
    peak_day = max(daily, key=daily.get)
    rows = []
    for rid in sorted(sigma, key=lambda x: sigma[x], reverse=True):
        peak_res = max(per_res_daily[rid].values()) if per_res_daily[rid] else 0.0
        rows.append((names.get(rid, rid), sigma[rid], peak_res))
    return {
        'span': [_mlabel(*k) for k in span],
        'values': values,
        'peak_val': values[pi],
        'peak_label': _mfull(*span[pi]),
        'peak_day_val': daily[peak_day],
        'peak_day_label': _day_label(peak_day),
        'total': sum(sigma.values()),
        'window': '%s – %s' % (_mfull(gmin.year, gmin.month), _mfull(gmax.year, gmax.month)),
        'rows': rows,
    }


# ── material monthly quantities ───────────────────────────────────────────────
def _spread(qty, ps, pf):
    s, f = ps.date(), pf.date()
    if f < s:
        f = s
    total = (f - s).days + 1
    out = defaultdict(float)
    d = s
    while d <= f:
        out[(d.year, d.month)] += qty / total
        d += _ONE
    return out


def _materials(recs):
    monthly = defaultdict(lambda: defaultdict(float))   # (name, unit) -> {(y,m): qty}
    total = defaultdict(float)
    excl_n, excl_total = 0, 0.0
    for r in recs:
        if r['rtype'] != 'RT_Mat':
            continue
        unit = r['unit']
        if not unit:                                    # unit-less ⇒ cost-model, never charted
            excl_n += 1
            excl_total += r['qty']
            continue
        key = (r['name'], unit)
        for k, v in _spread(r['qty'], r['ps'], r['pf']).items():
            monthly[key][k] += v
        total[key] += r['qty']

    mats = []
    for key in sorted(total, key=lambda x: total[x], reverse=True):
        name, unit = key
        present = sorted(monthly[key].keys())
        span = _month_span(present[0], present[-1]) if present else []
        values = [round(monthly[key].get(k, 0.0), 1) for k in span]
        pi = max(range(len(values)), key=lambda i: values[i]) if values else 0
        mats.append({
            'name': name, 'unit': unit,
            'span': [_mlabel(*k) for k in span],
            'values': values,
            'total': total[key],
            'peak_val': values[pi] if values else 0,
            'peak_label': _mfull(*span[pi]) if span else '',
        })
    return mats, excl_n, excl_total


# ── public entry ──────────────────────────────────────────────────────────────
def resource_loading(data, path=None):
    """Compute the §13 (Resource Loading) and §14 (Material Resources) payloads from the
    baseline resource assignments. Returns ``{'loading': {...}, 'materials': {...}}`` where
    each sub-dict is the exact payload its renderer consumes; both carry ``available=False``
    with an honest note when the schedule is not resource-loaded."""
    rmeta = read_resource_meta(path)
    recs = _records(data, rmeta)

    labor = [r for r in recs if r['rtype'] == 'RT_Labor']
    equip = [r for r in recs if r['rtype'] == 'RT_Equip']
    # Resources with no readable type fall through to neither loading nor material charts.

    groups = []
    if labor:
        p = _profile(labor, 'hours')
        if p:
            groups.append(_loading_group(
                'manpower', 'Manpower', 'No. of men (monthly average)', LABOR_HEX, 'hours', p,
                'Total man-hours', 'Peak crew (men)',
                'Budgeted man-hours are converted to men — crew = budgeted hours ÷ the '
                'activity’s working hours — so each bar is the average number of men on site '
                'that month, not a raw unit total.'))
    if equip:
        basis = _basis_for_equipment(equip)
        p = _profile(equip, basis)
        if p:
            if basis == 'count':
                note = ('Equipment is shown as the number of machines on site — the budgeted '
                        'quantity is a plant count, not hours, so it is loaded directly.')
                tcol = 'Total plant loaded'
            else:
                note = ('Budgeted equipment-hours are converted to machines — count = budgeted '
                        'hours ÷ the activity’s working hours — so each bar is the average '
                        'number of machines on site that month.')
                tcol = 'Total equipment-hours'
            groups.append(_loading_group(
                'equipment', 'Equipment', 'No. of equipment (monthly average)', EQUIP_HEX,
                basis, p, tcol, 'Peak no. on site', note))

    loading = {
        'available': bool(groups),
        'intro': ('The manpower and equipment loading read from the baseline resource '
                  'assignments, shown as the number on site per month. Each bar carries its '
                  'value; every resource’s budgeted total is listed beneath its histogram.'),
        'groups': groups,
    }

    mats, excl_n, excl_total = _materials(recs)
    materials = {
        'available': bool(mats),
        'intro': ('The material resources loaded in the baseline, each shown as the quantity '
                  'required per month in its own unit of measure. Quantities are never summed '
                  'across different units.'),
        'charts': [dict(m, color=MAT_HEX) for m in mats[:MAT_CHART_CAP]],
        'charted_n': min(len(mats), MAT_CHART_CAP),
        'total_n': len(mats),
        'table_headers': ['Material resource', 'Total quantity', 'Unit'],
        'table_rows': [[m['name'], _fmt0(m['total']), m['unit']] for m in mats],
        'excluded': ({'n': excl_n, 'total_label': _fmt0(excl_total)} if excl_n else None),
    }
    return {'loading': loading, 'materials': materials}


def _loading_group(key, title, unit_label, color, basis, p, total_col, peak_col, basis_note):
    return {
        'key': key, 'title': title, 'unit_label': unit_label, 'color': color, 'basis': basis,
        'basis_note': basis_note,
        'span': p['span'], 'values': p['values'],
        'peak_val': p['peak_val'], 'peak_label': p['peak_label'],
        'peak_day_val': p['peak_day_val'], 'peak_day_label': p['peak_day_label'],
        'total_label': _fmt0(p['total']),
        'total_unit': ('man-hours' if key == 'manpower'
                       else ('equipment-hours' if basis == 'hours' else 'plant units')),
        'window': p['window'],
        'row_headers': ['Resource', total_col, peak_col],
        'rows': [[nm, _fmt0(tot), _fmt0(peak)] for nm, tot, peak in p['rows']],
    }
