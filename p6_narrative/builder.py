"""Assemble the Baseline Narrative document from an already-parsed schedule.

Thin assembler: pulls each section's content from the engines the tool already has
(parser data, the Calendar feature's report, the driving-logic-derived sequence,
cost loading / cash flow) and lays them into the Basis-of-Schedule skeleton.
Recomputes nothing; generic across any construction project.
"""
import re
from datetime import date

from p6_narrative.costflow import branch_stats, cash_flow, cost_by_wbs
from p6_narrative.model import NarrativeDoc, Section
from p6_narrative.scope import scope_blocks
from p6_narrative.sequence import build_sequences
from p6_narrative.util import as_date, wbs_grouping

_MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
_MILESTONE_TYPES = ('StartMilestone', 'FinishMilestone')


def _fmt_date(x):
    d = as_date(x)
    return f'{d.day:02d}-{_MONTHS[d.month]}-{d.year}' if d else '—'


def _fmt_money(v):
    try:
        return f'{float(v):,.0f}'
    except (TypeError, ValueError):
        return '—'


def _milestones(data):
    rows = []
    for a in data.activities.values():
        if a.get('task_type') in _MILESTONE_TYPES:
            d = a.get('planned_finish') or a.get('planned_start')
            rows.append((as_date(d) or date.max, a.get('name') or '—', _fmt_date(d)))
    rows.sort(key=lambda r: r[0])
    return [[name, shown] for _, name, shown in rows]


def _wbs_tree(data):
    wbs = data.wbs
    children, roots = {}, []
    for oid, node in wbs.items():
        parent = node.get('parent_object_id')
        (children.setdefault(parent, []).append(oid)
         if parent and parent in wbs else roots.append(oid))
    out, seen = [], set()

    def walk(oid, level):
        if oid in seen:            # guard against a malformed WBS parent cycle
            return
        seen.add(oid)
        out.append({'name': wbs[oid].get('name') or '—', 'level': level})
        for child in children.get(oid, []):
            walk(child, level + 1)

    for r in roots:
        walk(r, 0)
    return out


def _wbs_tree_nested(data):
    """Nested WBS tree ([{name, children:[...]}]) for the org-chart renderer."""
    wbs = data.wbs
    children, roots = {}, []
    for oid, node in wbs.items():
        parent = node.get('parent_object_id')
        (children.setdefault(parent, []).append(oid)
         if parent and parent in wbs else roots.append(oid))
    seen = set()

    def build(oid):
        if oid in seen:                 # guard against a malformed WBS parent cycle
            return None
        seen.add(oid)
        kids = [build(c) for c in children.get(oid, [])]
        return {'name': wbs[oid].get('name') or '—', 'children': [k for k in kids if k]}

    return [t for t in (build(r) for r in roots) if t]


def _dedup(rows):
    seen, out = set(), []
    for r in rows:
        key = (r.get('code'), r.get('description'))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _codes_payload(data, code_catalog):
    if code_catalog:
        return {'tables': [{'dimension': dim, 'rows': _dedup(rows)}
                           for dim, rows in code_catalog.items() if rows]}
    # fallback: distinct values actually assigned to activities
    dims = {}
    for a in data.activities.values():
        for dim, val in (a.get('activity_codes') or {}).items():
            dims.setdefault(dim, set()).add(val)
    return {'tables': [{'dimension': dim,
                        'rows': [{'code': v, 'description': v} for v in sorted(vals)]}
                       for dim, vals in sorted(dims.items())]}


def _calendars_payload(calendar_report):
    if not calendar_report:
        return None
    calendars = []
    for c in calendar_report.get('assigned_calendars', []):
        dpw, hpd = c.get('days_per_week'), c.get('hours_per_day')
        calendars.append({
            'name': c.get('name') or '—',
            'working_days': f'{dpw} days/week' if dpw else '—',
            'shift': f'{hpd:g} h/day' if hpd else '—',
            'activities': c.get('activity_count', 0),
        })
    holidays = [
        {'range': h.get('description'), 'name': h.get('reason') or '', 'days': h.get('days')}
        for h in (calendar_report.get('exceptions') or {}).get('holidays', [])
    ]
    return {'calendars': calendars, 'holidays': holidays}


def _key_dates(data, limit=14):
    """Dated items for the key-dates timeline: milestones + constraint-dated activities."""
    items = []
    for a in data.activities.values():
        is_ms = a.get('task_type') in _MILESTONE_TYPES
        if not (is_ms or a.get('constraint_date')):
            continue
        d = as_date(a.get('planned_finish') or a.get('planned_start') or a.get('constraint_date'))
        if d:
            items.append({'date': d.isoformat(), 'label': a.get('name') or '—', 'milestone': is_ms})
    items.sort(key=lambda x: x['date'])
    return items[:limit]


def _id_anatomy(data):
    """Decode a representative activity ID into its delimited parts — generic across
    any coding convention (splits on . - _ and labels by position)."""
    best = None
    for a in data.activities.values():
        aid = (a.get('id') or '').strip()
        parts = [p for p in re.split(r'[.\-_]', aid) if p]
        if len(parts) >= 2 and (best is None or len(parts) > len(best[1])):
            best = (aid, parts)
    if not best:
        return None
    aid, parts = best
    role = ['Module', 'Work type', 'Area', 'Detail', 'Sub']
    n = len(parts)
    segs = [{'value': part,
             'label': ('Serial' if i == n - 1 else role[i] if i < len(role) else f'Part {i + 1}')}
            for i, part in enumerate(parts)]
    return {'id': aid, 'segments': segs}


def _design_proc_sequence(data, acts):
    """Sequence charts for the design / engineering / procurement branches (generic)."""
    group_of, _ = wbs_grouping(data.wbs)
    kw = ('design', 'engineer', 'procure', 'submittal', 'approval', 'shop drawing')

    def is_dp(a):
        name = ((data.wbs.get(group_of.get(a.get('wbs_id'))) or {}).get('name') or '').lower()
        return any(k in name for k in kw)

    dp = [a for a in acts if is_dp(a)]
    return build_sequences(dp, data.wbs, code_types=data.activity_code_types) if dp else []


def build_narrative(data, calendar_report=None, code_catalog=None, meta=None, setup=None):
    project = data.project or {}
    name = project.get('name') or 'the project'
    meta = dict(meta or {})
    meta.setdefault('project_name', name)
    meta.setdefault('project_id', project.get('id'))
    meta.setdefault('data_date', _fmt_date(project.get('data_date')))
    # Project setup (parties + logos + layout) — the details P6 doesn't hold. Logos ride
    # in the meta (they become the Word page header); the layout image fills §2.
    setup = setup or {}
    logos = {k: setup.get(k + '_logo') for k in ('owner', 'consultant', 'contractor')
             if setup.get(k + '_logo')}
    if logos:
        meta['logos'] = logos

    acts = list(data.activities.values())
    total_bac = round(sum(data.bac_by_activity.values()), 2) if data.bac_by_activity else 0.0
    sections = []

    intro = (f"The purpose of this narrative is to set out the planned scope, execution "
             f"methodology, work-breakdown and coding structure, project calendars, and the "
             f"sequence of works for {name}, as modelled in Primavera P6. It explains the "
             f"basis on which the baseline schedule has been developed, including the "
             f"milestones, engineering, procurement and construction logic that drive the "
             f"programme.")
    sections.append(Section('1', 'Introduction', 'prose', 'drafted',
                            payload={'paragraphs': [intro]}, editable=True,
                            note='Drafted from the schedule — edit freely.'))

    sections.append(Section('2', 'Project layout', 'image', 'fill',
                            payload={'image': setup.get('layout')},
                            note='Your project layout image, from setup.'))

    brief = []
    for key, lbl in (('owner', 'Owner'), ('consultant', 'Consultant'), ('contractor', 'Contractor')):
        if setup.get(key):
            brief.append((lbl, setup[key]))
    brief.append(('Project name', name))
    if project.get('id'):
        brief.append(('Project ID', project['id']))
    brief += [('Data date', _fmt_date(project.get('data_date'))),
              ('Planned start', _fmt_date(project.get('planned_start'))),
              ('Planned finish', _fmt_date(project.get('scheduled_finish')))]
    if total_bac:
        brief.append(('Budget (from cost loading)', _fmt_money(total_bac)))
    sections.append(Section(
        '3', 'Project brief', 'keyvals', 'auto',
        payload={'rows': [{'k': k, 'v': v} for k, v in brief]},
        note='Employer, Engineer and contract type come from the project’s user fields '
             'where present — otherwise confirm them.'))

    ms = _milestones(data)
    sections.append(Section('3.1', 'Project milestones', 'table', 'auto',
                            payload={'columns': ['Milestone', 'Date'], 'rows': ms},
                            note=None if ms else 'No milestone activities found in the file.'))

    kd = _key_dates(data)
    if kd:
        sections.append(Section('3.2', 'Key dates & milestones timeline', 'timeline', 'auto',
                                payload={'items': kd},
                                note='Milestones and constraint-dated activities on a timeline.'))

    value = cost_by_wbs(acts, data.bac_by_activity, data.wbs)
    if value.get('rows'):
        sections.append(Section('3.3', 'Contract value', 'value', 'auto',
                                payload={'total': value['total'], 'rows': value['rows']},
                                note='Budget split by major WBS branch, from cost loading.'))

    scope = scope_blocks(acts, data.wbs, code_types=data.activity_code_types,
                         bac_by_activity=data.bac_by_activity)
    n_ms = sum(1 for a in acts if a.get('task_type') in _MILESTONE_TYPES)
    stats = [
        {'v': _fmt_money(total_bac) if total_bac else '—', 'l': 'Budget'},
        {'v': str(len(acts)), 'l': 'Activities'},
        {'v': str(len(scope)), 'l': 'Disciplines'},
        {'v': str(len(data.wbs)), 'l': 'WBS nodes'},
        {'v': str(n_ms), 'l': 'Milestones'},
        {'v': str(len(data.relationships)), 'l': 'Logic links'},
    ]
    sections.append(Section(
        '4', 'Scope of work', 'scope', 'auto',
        payload={'intro': f"The scope of {name} is delivered across the following "
                          f"disciplines, read from the programme:",
                 'blocks': scope, 'stats': stats},
        note='A scope-at-a-glance dashboard, then a written block per discipline — from your file.'))

    calp = _calendars_payload(calendar_report)
    if calp is not None:
        sections.append(Section('5', 'Project calendars & holidays', 'table', 'calendar',
                                payload={'view': 'calendars', **calp},
                                note='From the Calendar feature — matches Calendar Audit.'))

    sections.append(Section('6', 'Work breakdown structure', 'wbs', 'auto',
                            payload={'nodes': _wbs_tree(data), 'tree': _wbs_tree_nested(data),
                                     'branches': branch_stats(acts, data.bac_by_activity, data.wbs),
                                     'cost_rows': cost_by_wbs(acts, data.bac_by_activity, data.wbs)['rows'],
                                     'total_activities': len(acts)},
                            note='Annotated org-chart (count · cost share · weight) + a cost treemap, '
                                 'then each branch’s sub-WBS. Word carries the same WBS as an editable outline.'))

    sections.append(Section('7', 'Activity codes', 'codes', 'auto',
                            payload=_codes_payload(data, code_catalog)))

    anatomy = _id_anatomy(data)
    if anatomy:
        sections.append(Section('8', 'Activity IDs', 'idanatomy', 'auto', payload=anatomy,
                                note='An activity ID decoded into its parts — the values are from the '
                                     'file; the part labels are a positional guide, edit if needed.'))

    dp_charts = _design_proc_sequence(data, acts)
    if dp_charts:
        sections.append(Section('9', 'Design & procurement sequence', 'sequence', 'drafted',
                                payload={'paragraphs': ['The design and procurement cycle, per package.'],
                                         'charts': dp_charts},
                                editable=True, note='Design / procurement logic from the file.'))

    charts = build_sequences(acts, data.wbs, code_types=data.activity_code_types)
    sections.append(Section(
        '10', 'Sequence of work', 'sequence', 'drafted',
        payload={'paragraphs': ["The works are sequenced per discipline below, grouped by "
                                "WBS work-package and ordered by the programme logic."],
                 'charts': charts},
        editable=True, note='Charts from the P6 logic — write the methodology around them.'))

    sections.append(Section('11', 'Major quantities', 'prose', 'fill',
                            payload={'paragraphs': ['Major quantities (piles, concrete volumes, etc.) come '
                                     'from the P6 resource quantities. Resource-quantity import is the '
                                     'immediate follow-on; add them here meanwhile.']},
                            editable=True, note='From P6 resource quantities (QTY) — follow-on.'))
    sections.append(Section('12', 'Productivity & resources', 'prose', 'fill',
                            payload={'paragraphs': ['Production rates and the crew / equipment allocation '
                                     'come from the P6 resources (MNP) — the immediate follow-on.']},
                            editable=True, note='From P6 resources (MNP) — follow-on.'))

    sections.append(Section('13', 'Cost loading', 'costbars', 'auto',
                            payload=cost_by_wbs(acts, data.bac_by_activity, data.wbs)))

    sections.append(Section(
        '14', 'Cash flow', 'cashflow', 'auto',
        payload=cash_flow(acts, data.bac_by_activity),
        note='Illustrative cost-loaded S-curve — each activity’s budget spread evenly across '
             'its planned dates and accumulated; the plan’s shape, not a P6-exact cost curve.'))

    return NarrativeDoc(meta, sections)


def apply_edits(doc_dict, edits):
    """Merge the user's in-app prose edits into an editable section's payload.

    ``edits`` maps a section number -> ``{'paragraphs': [...], 'bullets': [...]}``.
    Only editable sections are touched; everything else is ignored.
    """
    by_number = {s['number']: s for s in doc_dict.get('sections', [])}
    for number, patch in (edits or {}).items():
        section = by_number.get(number)
        if not section or not section.get('editable') or not isinstance(patch, dict):
            continue
        for key in ('paragraphs', 'bullets'):
            if isinstance(patch.get(key), list):
                section['payload'][key] = [str(x) for x in patch[key]]
    return doc_dict
