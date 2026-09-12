"""Baseline Narrative Report — the redesigned 10-section producer (locked design).

Turns a parsed P6 schedule into a :class:`NarrativeDoc` of the ten approved sections. It
emits DATA only — the HTML renderer (:mod:`p6_narrative.html`) and the Word renderer
(:mod:`p6_narrative.docx_writer`) both consume this same model and draw straight from the
payload (no re-derivation), so Preview == PDF == Print.

The approved design is captured pixel-for-pixel in ``mockups/narrative_full.html`` (screen /
PDF) and the standalone ``build_narrative_v2.py`` (Word). This producer fills the exact
payloads those renderers expect.

Section payload contract (renderers depend on it):

  1 Project Overview       kind 'overview'
      {paragraphs:[str,str], breakdown:[{world,count}], total:int}                editable
  2 Project Layout         kind 'image'      (OMITTED when no layout)
      {image:dataURL, caption:'Project general layout'}
  3 Project Brief          kind 'keyvals'
      {rows:[{k,v}]} — Owner, Consultant, Contractor, Project name, Location,
      Contract type, Data date, Baseline start, Baseline finish, Original duration,
      Contract Value  (missing → empty v, keep the row)
  4 Major Milestones       kind 'ms_table'
      {columns:['Milestone','Date'], rows:[[name, 'DD Month YYYY'], …]}            (Start + Finish)
  5 Key Dates              kind 'ms_table'
      {columns:['Milestone','Date'], rows:[[name, 'DD Month YYYY'], …]}            (all Start + Finish)
  6 Contract Value         kind 'value_bars'
      {total, unit?, rows:[{name, amount, pct}]}                                   (by type-of-work code)
  7 Scope of Work          kind 'scope'                                            editable
      {disciplines:[{name, pct, cost}], sections:[{discipline, buildings:[{name, elements:[str]}]}]}
  8 Project Calendars      kind 'table', payload.view 'calendars'
      {view, header:{calendar_count, activity_count}, dashboard:{…no shutdown…},
       calendars:[{name, activity_count, monthly:[{label, working_days, nonworking_days}], …}],
       holidays:[{date, description}], hours_profiles:[{name, hours, sub}]}
  9 Work Breakdown Structure  kind 'wbs_tree'
      {overview:{name, children:[{name}]},
       branches:[{name, columns:[[l2, [[l3, [l4,…]], …]], …], depth:3|4}]}
 10 Activity Codes         kind 'codes'
      {tables:[{dimension, rows:[{code, description}]}]}                           (two per row)

Every value is derived from the schedule / the before-run setup form — no project-specific
hardcoding.
"""
from collections import Counter, OrderedDict, defaultdict
from datetime import date, datetime

from p6_narrative.costflow import cost_by_wbs, value_by_code
from p6_narrative.intel.context import build_context
from p6_narrative.intel.fronts import detect_fronts, world_of
from p6_narrative.model import NarrativeDoc, Section
from p6_narrative.scope import scope_sections
from p6_narrative.util import as_date

# General EPC phase order (not project-specific): design/engineering → procurement →
# construction → testing/commissioning → close-out. Keyword-ranked so close-out is last.
_PHASE_WORDS = [
    (('design', 'engineering', 'ifc', 'drawing'), 1),
    (('procure', 'material', 'supply', 'fabricat'), 2),
    (('construct', 'execution', 'works', 'civil', 'install', 'build'), 3),
    (('test', 'commission', 'snag', 'inspection'), 4),
    (('closure', 'closeout', 'close-out', 'handover', 'completion', 'as-built', 'close'), 5),
]

_MILESTONE_TYPES = ('StartMilestone', 'FinishMilestone')
_MAX_WBS_KIDS = 12          # cap breadth on the per-branch org-charts


def _wname(ctx, wid):
    return (ctx.data.wbs.get(wid) or {}).get('name') or str(wid)


def _leaf(label):
    return str(label).split(' / ')[-1].strip()


def _full_date(v):
    """Format any date-ish value as 'DD Month YYYY' (e.g. '15 January 2026'), or None."""
    d = as_date(v)
    if d is None:
        return None if v in (None, '') else str(v)
    return '%d %s %d' % (d.day, d.strftime('%B'), d.year)


def _phase_rank(name):
    n = (name or '').lower()
    for words, rank in _PHASE_WORDS:
        if any(w in n for w in words):
            return rank
    return 2.5


def _median_str(vals):
    v = sorted(x for x in vals if x)
    return v[len(v) // 2] if v else '~'


def _ordered_worlds(ctx, worlds):
    starts = defaultdict(list)
    for o, a in ctx.steps.items():
        d = a.get('planned_start')
        if d:
            starts[world_of(ctx, o)].append(str(d)[:10])
    date_ = {w: _median_str(ds) for w, ds in starts.items()}
    return sorted(worlds, key=lambda w: (_phase_rank(w['world']), date_.get(w['world'], '~')))


def consolidate_seq(seq):
    """Collapse repeated sub-discipline stages (…Structural Shop Drawing Submittal /
    …Steel … / …Arc …) to the shared stage. Fires only on a genuinely repeated 2-word
    suffix, so distinct sequences (Excavation → Footing → Columns) are untouched.
    Kept for back-compat with callers/tests that import it."""
    if len(seq) <= 1:
        return list(seq)
    toks = [str(s).split() for s in seq]
    suf = Counter(' '.join(t[-2:]) for t in toks if len(t) >= 2)
    out = []
    for s, t in zip(seq, toks):
        key = ' '.join(t[-2:]) if len(t) >= 2 else s
        lab = (' '.join(t[-3:]) if len(t) >= 3 else s) if suf.get(key, 0) >= 2 else s
        if not out or out[-1] != lab:
            out.append(lab)
    return out


def _money(v, currency=''):
    try:
        s = '%s%s' % ((currency + ' ') if currency else '', format(float(v), ',.0f'))
        return s
    except (TypeError, ValueError):
        return ''


# ── §1 Project Overview ───────────────────────────────────────────────────────
def _overview(ctx, r):
    worlds = _ordered_worlds(ctx, r['worlds'])
    total = sum(w['total'] for w in worlds)
    paras = [
        "This Narrative Report is a comprehensive study of the project’s baseline "
        "schedule. Its purpose is to explain the plan in clear planning language — the "
        "execution strategy, the sequence of work, the major methodologies, the milestones, "
        "the Work Breakdown Structure and the interfaces between the major scopes — so the "
        "complete plan can be understood without opening the P6 schedule, while every statement "
        "stays traceable to the baseline activities.",
        "The project progresses from engineering and design, through procurement, into "
        "construction, and finally project close-out, executed as a set of repeatable "
        "work-package sequences.",
    ]
    breakdown = [{'world': w['world'], 'count': w['total']} for w in worlds]
    return Section('1', 'Project Overview', 'overview', 'auto',
                   payload={'paragraphs': paras, 'breakdown': breakdown, 'total': total},
                   editable=True, note='Executive introduction — edit the prose freely.')


# ── §2 Project Layout ─────────────────────────────────────────────────────────
def _layout(setup):
    img = setup.get('layout')
    if not img:
        return None
    return Section('2', 'Project Layout', 'image', 'auto',
                   payload={'image': img, 'caption': 'Project general layout'},
                   note='Uploaded in the report setup; the section is skipped when no drawing '
                        'is provided.')


# ── §3 Project Brief ──────────────────────────────────────────────────────────
def _project_window(data):
    project = data.project or {}
    acts = list(data.activities.values())
    a_starts = [as_date(a.get('planned_start')) for a in acts if a.get('planned_start')]
    a_fins = [as_date(a.get('planned_finish')) for a in acts if a.get('planned_finish')]
    start = as_date(project.get('planned_start')) or (min(a_starts) if a_starts else None)
    finish = as_date(project.get('scheduled_finish')) or (max(a_fins) if a_fins else None)
    return start, finish


def _brief(data, meta, setup):
    project = data.project or {}
    start, finish = _project_window(data)
    dur = ''
    if start and finish and finish >= start:
        dur = '%s calendar days' % format((finish - start).days + 1, ',')
    currency = setup.get('currency') or ''
    cval = setup.get('contract_value')
    if cval in (None, ''):
        total_bac = sum(data.bac_by_activity.values()) if data.bac_by_activity else 0.0
        cval = total_bac or None
    rows = [
        ('Owner', setup.get('owner') or ''),
        ('Consultant', setup.get('consultant') or ''),
        ('Contractor', setup.get('contractor') or ''),
        ('Project name', meta.get('project_name') or project.get('name') or ''),
        ('Location', meta.get('location') or ''),
        ('Contract type', meta.get('contract_type') or ''),
        ('Data date', _full_date(project.get('data_date')) or ''),
        ('Baseline start', _full_date(start) or ''),
        ('Baseline finish', _full_date(finish) or ''),
        ('Original duration', dur),
        ('Contract Value', _money(cval, currency) if cval not in (None, '') else ''),
    ]
    return Section('3', 'Project Brief', 'keyvals', 'auto',
                   payload={'rows': [{'k': k, 'v': v} for k, v in rows]},
                   note='Dates, name and value from P6; parties, location and contract type '
                        'from the setup form.')


# ── §4 / §5 milestone tables ──────────────────────────────────────────────────
def _all_milestones(ctx):
    """Every Start + Finish milestone, chronological → [(date_obj, name, 'DD Month YYYY')]."""
    rows = []
    for a in ctx.milestones.values():
        name = a.get('name')
        if not name:
            continue
        d = a.get('planned_finish') or a.get('planned_start') or a.get('constraint_date')
        rows.append((as_date(d) or date.max, name, _full_date(d) or '—'))
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


def _ms_section(number, title, all_ms, selected, note):
    keep = set(selected) if selected is not None else None
    rows = [[name, ds] for _, name, ds in all_ms if keep is None or name in keep]
    return Section(number, title, 'ms_table', 'auto',
                   payload={'columns': ['Milestone', 'Date'], 'rows': rows}, note=note)


# ── §6 Contract Value ─────────────────────────────────────────────────────────
def _contract_value(data, setup):
    acts = list(data.activities.values())
    bac = data.bac_by_activity or {}
    result = value_by_code(acts, bac, setup.get('tow_code'))
    if not result:                                     # fallback: split by WBS branch
        by_wbs = cost_by_wbs(acts, bac, data.wbs)
        result = {'total': by_wbs['total'],
                  'rows': [{'name': r['name'], 'amount': r['cost'], 'pct': r['pct']}
                           for r in by_wbs['rows']]}
    payload = {'total': result['total'], 'rows': result['rows']}
    if setup.get('value_unit'):
        payload['unit'] = setup['value_unit']
    return Section('6', 'Contract Value', 'value_bars', 'auto', payload=payload,
                   note='Total contract value and its distribution by type of work, from cost '
                        'loading.')


# ── §7 Scope of Work ──────────────────────────────────────────────────────────
def _scope(data, setup):
    payload = scope_sections(list(data.activities.values()), data.wbs,
                             bac_by_activity=data.bac_by_activity,
                             code_types=data.activity_code_types, setup=setup)
    return Section('7', 'Scope of Work', 'scope', 'auto', payload=payload, editable=True,
                   note='Share of contract value by discipline, then the detailed scope per '
                        'building and element — edit freely.')


# ── §8 Project Calendars & Holidays ───────────────────────────────────────────
def _calendars(cal_report, activity_count):
    if not cal_report:
        return None
    assigned = cal_report.get('assigned_calendars') or []
    by_cal = cal_report.get('by_calendar') or {}

    dash = dict(cal_report.get('dashboard') or {})
    for k in ('shutdown_periods', 'total_exceptions', 'baseline_start', 'baseline_finish',
              'window_start', 'window_finish', 'project_start', 'project_finish', 'data_date'):
        dash.pop(k, None)

    calendars = []
    for a in assigned:
        cid = a.get('object_id')
        info = by_cal.get(cid) or {}
        months = info.get('monthly_stats') or []
        monthly, labels, wdays, nwdays = [], [], [], []
        for m in months:
            wd = m.get('working_days', 0) or 0
            total_days = len(m.get('days') or []) or (wd + (m.get('exceptions', 0) or 0))
            nwd = max(total_days - wd, 0)
            monthly.append({'label': m.get('label'), 'working_days': wd, 'nonworking_days': nwd})
            labels.append(m.get('label'))
            wdays.append(wd)
            nwdays.append(nwd)
        calendars.append({
            'name': a.get('name') or '—',
            'activity_count': a.get('activity_count', 0),
            'monthly': monthly,
            'months': labels,
            'net_working_days': wdays,
            'nonworking_days': nwdays,
            'working_days': (info.get('totals') or {}).get('working_days', 0),
        })

    holidays = [{'date': h.get('description') or '', 'description': h.get('reason') or ''}
                for h in (cal_report.get('exceptions') or {}).get('holidays', [])]

    # One working-hours card per assigned calendar (its primary hours pattern).
    hours_profiles = []
    for a in assigned:
        cid = a.get('object_id')
        profs = (by_cal.get(cid) or {}).get('hours_profiles') or []
        if profs:
            p = profs[0]
            hours_profiles.append({'name': a.get('name') or p.get('name') or '—',
                                   'hours': p.get('hours') or '', 'sub': p.get('sub') or ''})

    payload = {
        'view': 'calendars',
        'header': {'calendar_count': len(assigned), 'activity_count': activity_count},
        'dashboard': dash,
        'calendars': calendars,
        'holidays': holidays,
        'hours_profiles': hours_profiles,
    }
    return Section('8', 'Project Calendars & Holidays', 'table', 'calendar', payload=payload,
                   note='From the Calendar feature — matches the P6 Calendar Audit.')


# ── §9 Work Breakdown Structure ───────────────────────────────────────────────
def _wbs(ctx):
    """9.1 an overview org-chart of the root and its major branches, then 9.2 one
    breakdown org-chart per major branch, resolved to Level 4 when that branch has
    4 or fewer Level-4 nodes, otherwise to Level 3. Purely data-driven from the WBS
    tree (``children_of_wbs``) — never inferred from names."""
    parents = {(ctx.data.wbs.get(b) or {}).get('parent_object_id') for b in ctx.branch_ids}
    root_id = parents.pop() if (len(parents) == 1 and None not in parents) else None
    root_name = _wname(ctx, root_id) if root_id else ((ctx.data.project or {}).get('name') or 'Project')

    overview = {'name': root_name,
                'children': [{'name': _wname(ctx, wid)} for wid in ctx.branch_ids]}

    branches = []
    for wid in ctx.branch_ids:
        l2s = ctx.children_of_wbs.get(wid, [])[:_MAX_WBS_KIDS]
        l4_count = sum(len(ctx.children_of_wbs.get(l3, []))
                       for l2 in l2s for l3 in ctx.children_of_wbs.get(l2, []))
        depth = 4 if l4_count <= 4 else 3
        columns = []
        for l2 in l2s:
            l3list = []
            for l3 in ctx.children_of_wbs.get(l2, [])[:_MAX_WBS_KIDS]:
                l4names = ([_leaf(_wname(ctx, l4))
                            for l4 in ctx.children_of_wbs.get(l3, [])[:_MAX_WBS_KIDS]]
                           if depth == 4 else [])
                l3list.append([_leaf(_wname(ctx, l3)), l4names])
            columns.append([_leaf(_wname(ctx, l2)), l3list])
        branches.append({'name': _wname(ctx, wid), 'columns': columns, 'depth': depth})

    return Section('9', 'Work Breakdown Structure', 'wbs_tree', 'auto',
                   payload={'overview': overview, 'branches': branches},
                   note='An overview org-chart of the major branches, then each branch expanded '
                        '— to Level 4 where its Level-4 nodes are 4 or fewer, else Level 3.')


# ── §10 Activity Codes ────────────────────────────────────────────────────────
def _dedup(rows):
    seen, out = set(), []
    for r in rows:
        key = (r.get('code'), r.get('description'))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _codes(data, code_catalog):
    if code_catalog:
        tables = [{'dimension': dim, 'rows': _dedup(rows)}
                  for dim, rows in code_catalog.items() if rows]
    else:
        dims = OrderedDict()
        for a in data.activities.values():
            for dim, val in (a.get('activity_codes') or {}).items():
                dims.setdefault(dim, set()).add(val)
        tables = [{'dimension': dim,
                   'rows': [{'code': v, 'description': v} for v in sorted(vals)]}
                  for dim, vals in dims.items()]
    return Section('10', 'Activity Codes', 'codes', 'auto', payload={'tables': tables},
                   note='One Code Value | Description table per code structure, laid two per row.')


# ── assembly ──────────────────────────────────────────────────────────────────
def build_report(data, path=None, meta=None, setup=None, **_ignored):
    """Assemble the redesigned Baseline Narrative Report as a :class:`NarrativeDoc` of the
    ten approved sections. Reconciled to ``mockups/narrative_full.html`` (screen/PDF) and the
    Word builder. Reads only what the parser produced plus the before-run setup form; never
    re-computes ``p6_evm`` metrics and never carries the ``records`` key."""
    ctx = build_context(data)
    r = detect_fronts(ctx)
    project = data.project or {}
    meta = dict(meta or {})
    setup = setup or {}

    meta.setdefault('project_name', project.get('name') or 'the project')
    meta.setdefault('project_id', project.get('id'))
    meta.setdefault('mode', r.get('mode'))
    meta['data_date'] = meta.get('data_date') or _full_date(project.get('data_date'))
    meta['location'] = meta.get('location') or setup.get('location') or project.get('location')
    meta['contract_type'] = meta.get('contract_type') or setup.get('contract_type') \
        or project.get('contract_type')
    meta['revision'] = meta.get('revision') or setup.get('revision')

    # Contract value on the meta (cover / brief) — setup value, else the cost-loading sum.
    cval = setup.get('contract_value')
    if cval in (None, ''):
        total_bac = sum(data.bac_by_activity.values()) if data.bac_by_activity else 0.0
        cval = total_bac or None
    meta['contract_value'] = cval

    # 3 party logos only (no title band in the header).
    logos = {k: setup.get(k + '_logo') for k in ('owner', 'consultant', 'contractor')
             if setup.get(k + '_logo')}
    if logos:
        meta['logos'] = logos

    # Calendar audit + activity-code catalog (best-effort; graceful when unavailable).
    cal = None
    try:
        from p6_calendar.audit import calendar_audit
        cal = calendar_audit(data)
    except Exception:
        cal = None
    cat = None
    if path:
        try:
            from p6_narrative.codes import read_code_catalog
            cat = read_code_catalog(path)
        except Exception:
            cat = None

    activity_count = len(data.activities)
    all_ms = _all_milestones(ctx)
    ms_names = [name for _, name, _ in all_ms]

    ordered = [
        _overview(ctx, r),
        _layout(setup),
        _brief(data, meta, setup),
        _ms_section('4', 'Major Milestones', all_ms, setup.get('milestone_keys'),
                    None if all_ms else 'No Start/Finish milestones are defined in the file.'),
        _ms_section('5', 'Key Dates', all_ms, setup.get('key_date_keys'),
                    None if all_ms else 'No Start/Finish milestones are defined in the file.'),
        _contract_value(data, setup),
        _scope(data, setup),
        _calendars(cal, activity_count),
        _wbs(ctx),
        _codes(data, cat),
    ]
    ordered = [s for s in ordered if s is not None]

    # Before-run pick lists surfaced on the meta for the UI checklists / dropdowns.
    meta['milestone_choices'] = list(ms_names)
    meta['key_date_choices'] = list(ms_names)
    meta['code_choices'] = list(data.activity_code_types or [])

    for i, s in enumerate(ordered, 1):
        s.number = str(i)
    return NarrativeDoc(meta, ordered)
