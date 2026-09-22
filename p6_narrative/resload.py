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
import calendar as _cal
from collections import defaultdict
from datetime import timedelta, date
from xml.etree import ElementTree as ET

try:
    # Correctly counts a P6 24-hour calendar's working days (its midnight-to-midnight shift makes
    # the raw ``is_working_day`` mark every day non-working). Display-only, never EVM math.
    from p6_calendar.audit import _is_working_day_display as _wd_display
except Exception:                               # pragma: no cover - defensive
    _wd_display = None

_ONE = timedelta(days=1)
_MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
_MON_FULL = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
             'August', 'September', 'October', 'November', 'December']

MAT_CHART_CAP = 8          # material resources charted individually (top N by total)
EQUIP_COUNT_THRESHOLD = 0.5  # median implied crew below this ⇒ the qty is a plant count

# Discipline hues shared with the rest of the report (see html._RAMP).
LABOR_HEX = '1F4E79'       # navy   — manpower man-hours
LABOR_HEX2 = '2E75B6'      # blue   — manpower number (headcount)
EQUIP_HEX = '2E9E5B'       # green  — equipment
MAT_HEX = 'E8A33D'         # amber  — materials


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


def _fmt_peak(n):
    """Like :func:`_fmt0` but never floors a genuinely-loaded resource's peak to ``0`` — a
    peak simultaneous count between 0 and 1 (e.g. two half-overlapping machines → 0.5) is
    shown to one decimal instead of rounding to a self-contradictory '0'."""
    try:
        x = float(n or 0)
    except Exception:
        return '0'
    if 0 < x < 1:
        return '{:.1f}'.format(x)
    return '{:,.0f}'.format(round(x))


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


def _is_working(cal, d):
    """True if ``d`` is a working day on calendar ``cal`` (None/error ⇒ treat as working).
    Uses the display classifier so a 24-hour calendar is not read as all non-working."""
    if cal is None:
        return True
    try:
        if _wd_display is not None:
            return bool(_wd_display(cal, d))
        return bool(cal.is_working_day(d))
    except Exception:
        return True


def _working_days_in_month(cal, y, m, wstart, wend):
    """Working days of month ``(y, m)`` on calendar ``cal`` that fall inside the project window
    ``[wstart, wend]`` — the per-assignment denominator for the sustained-crew figure (an
    assignment's man-days ÷ its own calendar's working days = its crew that month). A missing
    calendar counts every day, matching how such an assignment is loaded."""
    n = 0
    for dd in range(1, _cal.monthrange(y, m)[1] + 1):
        d = date(y, m, dd)
        if wstart <= d <= wend and _is_working(cal, d):
            n += 1
    return n


def _wd_spread(qty, ps, pf, cal):
    """Spread ``qty`` LINEARLY across the activity's working days (per its calendar) and bucket
    by month — P6's standard resource-usage time distribution, so §13 man-hours and §14 material
    quantities reproduce P6's Resource Usage Spreadsheet to the figure."""
    s, f = ps.date(), pf.date()
    if f < s:
        f = s
    days = []
    d = s
    while d <= f:
        if _is_working(cal, d):
            days.append((d.year, d.month))
        d += _ONE
    if not days:                          # calendar marks nothing working — fall back to all days
        d = s
        while d <= f:
            days.append((d.year, d.month))
            d += _ONE
    out = defaultdict(float)
    for k in days:
        out[k] += qty / len(days)
    return out


def _units_profile(recs, calendars):
    """Monthly BUDGETED UNITS via linear working-day spread, aggregated across a group's
    assignments — the exact P6 Resource-Usage figure (man-hours for labour)."""
    calendars = calendars or {}
    monthly = defaultdict(float)
    gmin = gmax = None
    for r in recs:
        cal = calendars.get(r.get('cal'))
        for k, v in _wd_spread(r['qty'], r['ps'], r['pf'], cal).items():
            monthly[k] += v
        gmin = r['ps'] if (gmin is None or r['ps'] < gmin) else gmin
        gmax = r['pf'] if (gmax is None or r['pf'] > gmax) else gmax
    if not monthly:
        return None
    span = _month_span((gmin.year, gmin.month), (gmax.year, gmax.month))
    values = [round(monthly.get(k, 0.0), 1) for k in span]
    pi = max(range(len(values)), key=lambda i: values[i])
    return {'span': [_mlabel(*k) for k in span], 'values': values,
            'peak_val': values[pi], 'peak_label': _mfull(*span[pi]),
            'total': sum(r['qty'] for r in recs)}


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
                'cal': act.get('calendar_id'),
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


def _profile(recs, basis, calendars=None):
    """The SUSTAINED crew on site per month + per-resource totals. Each assignment's crew
    (``basis='hours'`` → ``qty / working-hours`` men; ``basis='count'`` → ``qty`` machines) is
    loaded onto the activity's WORKING days (per its calendar); the monthly bar is that month's
    man-days ÷ its working days = the men actually needed on site that month, NOT diluted by
    idle/non-working days. Matches how P6 reports resource loading."""
    calendars = calendars or {}
    daily = defaultdict(float)
    per_res_daily = defaultdict(lambda: defaultdict(float))
    sigma = defaultdict(float)
    names = {}
    loads = []                                   # (crew, cal, {(y,m): working days this activity loads})
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
        cal = calendars.get(r.get('cal'))
        s, f = ps.date(), pf.date()
        if f < s:
            f = s
        gmin = ps if (gmin is None or ps < gmin) else gmin
        gmax = pf if (gmax is None or pf > gmax) else gmax
        rid = r['rid']
        names[rid] = r['name']
        sigma[rid] += r['qty']
        wd_by_month = defaultdict(int)
        d = s
        while d <= f:
            if _is_working(cal, d):          # load only working days (P6 spreads over working time)
                daily[d] += crew
                per_res_daily[rid][d] += crew
                wd_by_month[(d.year, d.month)] += 1
            d += _ONE
        if wd_by_month:
            loads.append((crew, cal, wd_by_month))
    if gmin is None or not daily:
        return None

    # SUSTAINED crew = Σ over assignments of crew × (its working days loaded in the month) ÷ (its
    # OWN calendar's working days in that month). Per-assignment normalisation keeps numerator and
    # denominator on the SAME calendar, so a mix of calendars (e.g. a 24-hour calendar beside a
    # 6-day one) neither inflates nor zeroes a month — the divisor is always ≥ the loaded days.
    wstart, wend = gmin.date(), gmax.date()
    monthly = defaultdict(float)
    for crew, cal, wd_by_month in loads:
        for k, loaded in wd_by_month.items():
            cal_wd = _working_days_in_month(cal, k[0], k[1], wstart, wend) or loaded
            monthly[k] += crew * loaded / cal_wd
    span = _month_span((gmin.year, gmin.month), (gmax.year, gmax.month))
    values = [round(monthly.get(k, 0.0), 2) for k in span]

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
def _excluded_costmodel(data, meta):
    """Count the unit-less "material" assignments — the cost model (contract value) reported in
    §14's note but never charted. Counted over ALL assignments (independent of whether the
    activity carries dates), so the note's count/value is complete on any schedule."""
    n, total = 0, 0.0
    for _oid, alist in (getattr(data, 'assignments_by_activity', None) or {}).items():
        for a in alist or []:
            rm = meta.get(a.get('resource_id')) or {}
            if rm.get('type') != 'RT_Mat' or rm.get('unit'):
                continue                                # only unit-LESS material = cost model
            try:
                qty = float(a.get('budget_units') or 0)
            except Exception:
                qty = 0.0
            if qty <= 0:
                continue
            n += 1
            total += qty
    return n, total


def _materials(recs, calendars):
    calendars = calendars or {}
    monthly = defaultdict(lambda: defaultdict(float))   # (name, unit) -> {(y,m): qty}
    total = defaultdict(float)
    for r in recs:
        if r['rtype'] != 'RT_Mat':
            continue
        unit = r['unit']
        if not unit:                                    # unit-less ⇒ cost-model (counted separately)
            continue
        key = (r['name'], unit)
        # P6 spreads each quantity across the activity's WORKING days (its Resource Usage
        # Spreadsheet distribution) — verified to match P6 to the figure.
        cal = calendars.get(r.get('cal'))
        for k, v in _wd_spread(r['qty'], r['ps'], r['pf'], cal).items():
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
    return mats


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

    cals = getattr(data, 'calendars', None) or {}
    groups = []
    if labor:
        num = _profile(labor, 'hours', cals)       # headcount (sustained crew, over working days)
        hrs = _units_profile(labor, cals)          # man-hours (working-day spread = P6)
        if num and hrs:
            groups.append(_manpower_group(num, hrs))
    if equip:
        basis = _basis_for_equipment(equip)
        num = _profile(equip, basis, cals)
        if num:
            groups.append(_equipment_group(num, basis))

    loading = {
        'available': bool(groups),
        'intro': ('The manpower and equipment loading read from the baseline resource '
                  'assignments. Manpower is shown both as budgeted man-hours per month (matching '
                  'P6) and converted to a headcount; equipment as the number of machines on site. '
                  'Every bar carries its value and each resource’s total is listed below.'),
        'groups': groups,
    }

    mats = _materials(recs, cals)
    excl_n, excl_total = _excluded_costmodel(data, rmeta)
    materials = {
        'available': bool(mats),
        'intro': ('The material resources loaded in the baseline, each shown as the quantity '
                  'required per month in its own unit of measure. Quantities are never summed '
                  'across different units.'),
        'charts': [dict(m, color=MAT_HEX) for m in mats[:MAT_CHART_CAP]],
        'charted_n': min(len(mats), MAT_CHART_CAP),
        'total_n': len(mats),
        'table_headers': ['Material resource', 'Unit', 'Total Quantity'],
        'table_rows': [[m['name'], m['unit'], _fmt0(m['total'])] for m in mats],
        'excluded': ({'n': excl_n, 'total_label': _fmt0(excl_total)} if excl_n else None),
    }
    return {'loading': loading, 'materials': materials}


def _manpower_group(num, hrs):
    """§13.1 Manpower — TWO histograms (man-hours per month = P6, and that converted to a
    headcount) + the per-resource totals table."""
    return {
        'key': 'manpower', 'title': 'Manpower',
        'basis_note': ('Read from the Labour resource assignments — budgeted man-hours spread '
                       'across each activity’s working days (matching P6’s Resource Usage). '
                       'Shown two ways: the man-hours per month, and that converted to a headcount '
                       '(a month’s man-hours ÷ its working hours).'),
        'window': num['window'],
        'charts': [
            {'chart_title': 'Manpower — man-hours per month', 'color': LABOR_HEX,
             'span': hrs['span'], 'values': hrs['values'],
             'peak_val': hrs['peak_val'], 'peak_label': hrs['peak_label'], 'peak_unit': 'man-hours'},
            {'chart_title': 'Manpower — number per month', 'color': LABOR_HEX2,
             'span': num['span'], 'values': num['values'],
             'peak_val': num['peak_val'], 'peak_label': num['peak_label'], 'peak_unit': ''},
        ],
        'total_label': _fmt0(hrs['total']), 'total_unit': 'man-hours',
        'row_headers': ['Resource', 'Total man-hours', 'Peak number'],
        'rows': [[nm, _fmt0(tot), _fmt_peak(peak)] for nm, tot, peak in num['rows']],
    }


def _equipment_group(num, basis):
    """§13.2 Equipment — number of machines on site per month + the per-resource totals table."""
    tcol = 'Total plant loaded' if basis == 'count' else 'Total equipment-hours'
    return {
        'key': 'equipment', 'title': 'Equipment',
        'basis_note': ('Read from the Non-labour (equipment) resource assignments — the number of '
                       'machines on site per month, loaded over each activity’s working days.'),
        'window': num['window'],
        'charts': [
            {'chart_title': 'Equipment — number per month', 'color': EQUIP_HEX,
             'span': num['span'], 'values': num['values'],
             'peak_val': num['peak_val'], 'peak_label': num['peak_label'], 'peak_unit': ''},
        ],
        'total_label': _fmt0(num['total']),
        'total_unit': ('plant units' if basis == 'count' else 'equipment-hours'),
        'row_headers': ['Resource', tcol, 'Peak no. on site'],
        'rows': [[nm, _fmt0(tot), _fmt_peak(peak)] for nm, tot, peak in num['rows']],
    }
