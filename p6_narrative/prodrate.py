"""§15 Productivity Rates & Resources Assigned — planned daily production rate + assigned crew.

For every material (quantities) resource loaded in the baseline this derives:

  * total quantity      = Σ ``budget_units`` across its activities (kept in the resource's unit)
  * total working-days  = Σ, over its activities, of the activity's working-day count
                          (``resload._is_working`` on the activity's own calendar)
  * Rate/day (headline) = total quantity ÷ total working-days  — the WEIGHTED average (NOT the
                          mean of the per-activity rates)
  * Range               = lowest .. highest PER-ACTIVITY rate (activity qty ÷ its working days),
                          always rendered "min – max <unit>/day" even when min == max
  * Crew assigned/day   = for each labour/equipment resource on the SAME activities —
                          labour    → man-hours ÷ (total working-days × 8)   (men on site/day)
                          equipment → its count ÷ number of activities        (machines on site)

Isolated from ``p6_evm`` (reads only the already-parsed ``data`` plus the ``resload`` helpers)
exactly like :mod:`p6_narrative.volwork` — the core parser stays untouched. Generic: every
figure is read from the file's own resource assignments; nothing is hardcoded to a sample
project. Three honest fallbacks:

  * unit-bearing materials present   → one row per unit-bearing material, full rates.
  * only unit-less materials present → the same table with one row per material resource, its
                                       Total quantity and crew, but BLANK Rate/Range cells and an
                                       explanatory line (the resources carry no unit of measure).
  * no material resources at all     → ``{'available': False}`` (an honest no-data note).

The payload is DATA only — both the HTML/PDF renderer (:mod:`p6_narrative.html`) and the native
Word renderer (:mod:`p6_narrative.docx_writer`) draw straight from it, so screen == PDF == Word.
"""
import math
from collections import defaultdict
from datetime import timedelta

from p6_narrative import resload

WORK_HOURS_PER_DAY = 8.0

# Fixed method-note (worked-example) block — the SAME text is carried into BOTH the HTML/PDF and
# the Word renderers so the planner reads an identical explanation in each. The worked figures
# are illustrative examples of the method, not values read from the current file.
METHOD_INTRO = ("Every figure below is derived automatically from the schedule’s resource "
                "assignments, as follows:")
METHOD = [
    ['Working days',
     "an activity’s own calendar days that are working days; weekends and holidays on its "
     "calendar are not counted."],
    ['Rate per day',
     "Total quantity ÷ Total working days. Example — Piles m3: 36,401 m3 ÷ 464 "
     "working days = 78.5 m3/day."],
    ['Range',
     "the lowest to the highest rate among the activities that make up that quantity, where each "
     "activity’s own rate = its quantity ÷ its working days. Example — the "
     "individual Piles m3 activities range from 11.9 to 168.4 m3/day. Every activity and its own "
     "rate is listed by Activity ID in the breakdown below."],
    ['Crew (per day)',
     "the number of workers on site per working day = the crew’s man-hours ÷ (working "
     "days × hours per day). Example — the Carpenter on Columns m3: 3,460 man-hours "
     "÷ (180 days × 8 hours) = 2.4 carpenters per day."],
]

INTRO = ("This section reports the planned daily production rate for every quantity of work in "
         "the baseline — the material resources the schedule loads with a unit of measure "
         "(piles, concrete, reinforcement and the like) — together with the crew planned to "
         "deliver it. For each quantity it states the total quantity, the number of working days "
         "its activities span, the resulting production rate per day, the spread of that rate "
         "across the individual activities, and the labour and plant assigned to the same "
         "activities. Every figure is derived automatically from the schedule’s own resource "
         "assignments — nothing is assumed or entered by hand.")

CLOSING_NOTE = ("This section is generated automatically from the schedule’s own resource "
                "loading: each material resource is listed with the crew (labour and plant) "
                "assigned to its activities, and where a resource carries a unit of measure its "
                "weighted-average production rate and the per-activity range are shown. A schedule "
                "with no material resources at all shows a short note in place of the table rather "
                "than an empty figure.")

NO_UNIT_NOTE = ("The rate columns are blank because these material resources carry no unit of "
                "measure — in this schedule they hold the loaded cost, not a physical "
                "quantity — so a production rate per day cannot be expressed. Each "
                "resource’s total loaded value, its working days and the crew assigned to "
                "its activities are still shown.")

HEADERS = ['Quantities resource', 'Unit', 'Total quantity', 'Working-days',
           'Rate/day', 'Range (min–max)', 'Crew assigned (per day)']
# Column widths (inches) — Σ = 6.9" (A4 usable width). Name + crew columns widened so the worst
# wrapped cell stays inside the uniform §15 row height without clipping.
WIDTHS = [1.65, 0.52, 0.72, 0.58, 0.78, 0.87, 1.78]   # unit col widened so "Ton" never wraps

# Crew-cell character budget: the crew of one quantity can, in the unit-less cost-model fallback,
# aggregate every labour/plant resource in the project (a cost resource spans all activities). The
# §15 rows are one fixed height, so the crew text is bounded — the largest crews (by man-hours /
# count, already sorted first) are listed until this budget, then "; +N more". Comfortably above
# any genuine per-quantity crew (Grain's longest is ~62 chars), so real material rows never trim.
CREW_MAX_CHARS = 72

# ── 15.3 per-activity breakdown ───────────────────────────────────────────────
# For each unit-bearing quantities resource, the individual activities that make up its rate are
# listed by Activity ID (Ibrahim: "this shall include all items, not the piles only" + "clarify the
# activity id" + "remove the location column"). Activities that share the SAME quantity and the SAME
# working-days share a rate, so they are grouped onto one line; the Activity IDs in a group are
# listed until this cap, then summarised as "; +N more" so no single line overflows the page.
BREAKDOWN_HEADERS = ['Activity ID', 'Quantity', 'Working-days', 'Rate/day']
BREAKDOWN_WIDTHS = [3.2, 1.1, 0.9, 1.7]                   # inches, Σ = 6.9" (A4 usable width)
BREAKDOWN_ID_CAP = 16
BREAKDOWN_INTRO = ("For each quantity of work below, its activities are listed with the quantity, "
                   "the working-days and the resulting rate (quantity ÷ working-days). Activities "
                   "that share the same quantity and duration are grouped on one line, and the "
                   "fastest activity is shown first. The weighted overall rate for each quantity — "
                   "its total quantity ÷ its total working-days — is given in the summary rate "
                   "table that follows.")


# ── computation ───────────────────────────────────────────────────────────────
def _working_days(ps, pf, cal):
    """Inclusive working-day count in ``[ps, pf]`` on calendar ``cal`` (never below 1)."""
    s, f = ps.date(), pf.date()
    if f < s:
        f = s
    n, d = 0, s
    while d <= f:
        if resload._is_working(cal, d):
            n += 1
        d += timedelta(days=1)
    return n or 1


def _n0(v):
    try:
        return '{:,.0f}'.format(round(float(v or 0)))
    except (TypeError, ValueError, OverflowError):      # OverflowError guards inf
        return '0'


def _d1(v):
    """One decimal, trailing '.0' dropped: 78.5 -> '78.5', 1.0 -> '1', 11.9 -> '11.9'."""
    try:                                                # int()/round() inside the guard so a
        f = round(float(v or 0), 1)                     # non-finite value degrades to '0', never
        return '%d' % f if f == int(f) else '%.1f' % f  # an uncaught inf/NaN that blanks §15
    except (TypeError, ValueError, OverflowError):
        return '0'


def _crew_text(crew, max_chars=CREW_MAX_CHARS):
    """Compact 'Name ~N/day; Name2 ~M/day', or an em dash when no crew shares the activities.

    Bounded to ``max_chars`` of listed crews (largest first) so a single quantity's crew can never
    overflow the fixed §15 row height; any remainder is summarised as '; +N more'. The first crew
    is always shown."""
    if not crew:
        return '—'
    parts = ['%s ~%s/day' % (cn, _d1(v)) for cn, _ct, v in crew]
    shown, used = [], 0
    for part in parts:
        sep = 0 if not shown else 2                     # '; ' between entries
        if shown and used + sep + len(part) > max_chars:
            break
        shown.append(part)
        used += sep + len(part)
    if len(shown) < len(parts):
        shown.append('+%d more' % (len(parts) - len(shown)))
    return '; '.join(shown)


def _compute(data, meta):
    """Aggregate, per material resource key ``(name, unit)`` (``unit`` may be ``None`` for the
    unit-less cost-model materials): its activities' ``(qty, working-days)``, the Σ quantity and
    the crew (labour man-hours / equipment count) accumulated across the SAME activities."""
    cals = getattr(data, 'calendars', None) or {}
    activities = getattr(data, 'activities', None) or {}
    assigns = getattr(data, 'assignments_by_activity', None) or {}

    mat_acts = defaultdict(list)                             # (name, unit) -> [(qty, wd, act_id)]
    mat_total = defaultdict(float)                           # (name, unit) -> Σ qty
    mat_crew_val = defaultdict(lambda: defaultdict(float))   # material -> {crew name -> Σ mh|count}
    mat_crew_type = {}                                       # crew name -> 'L' | 'E'

    for oid, alist in assigns.items():
        act = activities.get(oid) or {}
        ps, pf = act.get('planned_start'), act.get('planned_finish')
        if not ps or not pf:
            continue
        wd = _working_days(ps, pf, cals.get(act.get('calendar_id')))
        aid = act.get('id') or oid              # human-facing P6 Activity ID (fallback: ObjectId)
        crew, mats = [], []
        for a in alist or []:
            rid = a.get('resource_id')
            rm = meta.get(rid) or {}
            typ, unit = rm.get('type'), rm.get('unit')
            nm = a.get('resource_name') or rid
            try:
                q = float(a.get('budget_units') or 0)
            except (TypeError, ValueError):
                q = 0.0
            if not math.isfinite(q):                    # a corrupt inf/NaN qty contributes nothing
                q = 0.0
            if typ == 'RT_Labor':
                crew.append((nm, 'L', q))
            elif typ == 'RT_Equip':
                crew.append((nm, 'E', q))
            elif typ == 'RT_Mat' and q > 0:                 # unit optional (no-unit fallback)
                mats.append(((nm, unit), q))
        for key, q in mats:
            mat_acts[key].append((q, wd, aid))
            mat_total[key] += q
            for cn, ct, cu in crew:
                mat_crew_type[cn] = ct
                mat_crew_val[key][cn] += cu
    return mat_acts, mat_total, mat_crew_val, mat_crew_type


def _record(key, mat_acts, mat_total, mat_crew_val, mat_crew_type):
    """One material resource's full record: totals, weighted rate, per-activity range and crew."""
    name, unit = key
    rows = mat_acts[key]
    nact = len(rows)
    total_qty = mat_total[key]
    total_wd = sum(wd for _q, wd, _a in rows)
    rates = [q / wd for q, wd, _a in rows if wd]
    rate = (total_qty / total_wd) if total_wd else 0.0      # WEIGHTED average headline
    rmin = min(rates) if rates else 0.0
    rmax = max(rates) if rates else 0.0
    crew_out = []
    for cn in sorted(mat_crew_val[key], key=lambda c: -mat_crew_val[key][c]):
        ct = mat_crew_type[cn]
        v = mat_crew_val[key][cn]
        if ct == 'L':
            per_day = v / (total_wd * WORK_HOURS_PER_DAY) if total_wd else 0.0   # men / working day
        else:
            per_day = v / nact if nact else 0.0                                  # machines on site
        crew_out.append((cn, ct, per_day))
    return {'name': name, 'unit': unit, 'nact': nact, 'total_qty': total_qty,
            'total_wd': total_wd, 'rate': rate, 'rmin': rmin, 'rmax': rmax, 'crew': crew_out}


def _breakdown_rows(key, unit, mat_acts):
    """The per-activity breakdown for one unit-bearing resource: one row per distinct
    (quantity, working-days) — its Activity ID(s), the quantity, the working-days and the resulting
    rate (qty ÷ working-days), fastest first. Activities sharing a (qty, wd) share a rate, so their
    Activity IDs are listed together; the top and bottom rows equal the section's Range endpoints."""
    groups = defaultdict(list)                                # (round(qty,3), wd) -> [Activity ID…]
    for q, wd, aid in mat_acts[key]:
        groups[(round(float(q or 0), 3), wd)].append(str(aid))
    out = []
    for (q, wd), ids in groups.items():
        rate = (q / wd) if wd else 0.0
        ids_sorted = sorted(ids)
        if len(ids_sorted) > BREAKDOWN_ID_CAP:
            ids_str = ('%s; +%d more'
                       % (', '.join(ids_sorted[:BREAKDOWN_ID_CAP]),
                          len(ids_sorted) - BREAKDOWN_ID_CAP))
        else:
            ids_str = ', '.join(ids_sorted)
        out.append((rate, [ids_str, _n0(q), '%d' % wd, '%s %s/day' % (_d1(rate), unit)]))
    out.sort(key=lambda t: (-t[0], t[1][0]))                  # fastest first, then by Activity ID
    return [r for _rate, r in out]


# ── public entry ──────────────────────────────────────────────────────────────
def productivity(data, path=None):
    """The §15 payload consumed by both renderers. ``{'available': False}`` only when the
    schedule carries no material resources at all; otherwise a table (one row per material
    resource), with full rates when the materials carry a unit of measure, or blank rate/range
    cells plus an explanatory line when they do not."""
    meta = resload.read_resource_meta(path)
    mat_acts, mat_total, mat_crew_val, mat_crew_type = _compute(data, meta)

    if not mat_total:                                   # zero material resources at all
        return {'available': False}

    unit_keys = [k for k in mat_total if k[1]]          # (name, unit) with a real unit of measure
    has_units = bool(unit_keys)
    keys = sorted(unit_keys if has_units else list(mat_total.keys()),
                  key=lambda k: mat_total[k], reverse=True)
    recs = [_record(k, mat_acts, mat_total, mat_crew_val, mat_crew_type) for k in keys]

    rows = []
    for r in recs:
        if has_units:
            unit = r['unit']
            rows.append([
                r['name'],
                unit,
                _n0(r['total_qty']),
                '%d' % r['total_wd'],
                '%s %s/day' % (_d1(r['rate']), unit),
                '%s – %s %s/day' % (_d1(r['rmin']), _d1(r['rmax']), unit),
                _crew_text(r['crew']),
            ])
        else:                                           # unit-less fallback — blank rate/range
            rows.append([
                r['name'],
                '',
                _n0(r['total_qty']),
                '%d' % r['total_wd'],
                '',
                '',
                _crew_text(r['crew']),
            ])

    # 15.3 — per-activity breakdown, one block per unit-bearing resource (same order as the table
    # above). Only when the materials carry a unit of measure; the unit-less fallback has no rates
    # to break down, so it shows no breakdown block.
    breakdown = []
    if has_units:
        for r, k in zip(recs, keys):
            u = r['unit']
            breakdown.append({
                'name': r['name'],
                'unit': u,
                'rate': '%s %s/day' % (_d1(r['rate']), u),
                'total_wd': r['total_wd'],
                'nact': r['nact'],
                'headers': list(BREAKDOWN_HEADERS),
                'widths': list(BREAKDOWN_WIDTHS),
                'rows': _breakdown_rows(k, u, mat_acts),
            })

    return {
        'available': True,
        'has_units': has_units,
        'intro': INTRO,
        'method_intro': METHOD_INTRO,
        'method': [list(m) for m in METHOD],
        'headers': list(HEADERS),
        'widths': list(WIDTHS),
        'rows': rows,
        'breakdown_intro': BREAKDOWN_INTRO if has_units else None,
        'breakdown': breakdown,
        'no_unit_note': None if has_units else NO_UNIT_NOTE,
        'closing_note': CLOSING_NOTE,
        'n': len(rows),
    }
