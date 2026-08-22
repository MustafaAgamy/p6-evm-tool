"""Baseline Narrative Report — the v5 producer (locked design).

Turns a parsed P6 schedule into a :class:`NarrativeDoc` of five executive sections, driven
by the Schedule-Intelligence front detector (:func:`p6_narrative.intel.fronts.detect_fronts`).
It emits DATA only — the HTML renderer (:mod:`p6_narrative.html`) and the Word renderer
(:mod:`p6_narrative.docx_writer`) both consume this same model, so Preview == PDF == Print.

Section payload contract (stable — renderers depend on it):

  1 Project Overview   kind 'overview'
      {paragraphs:[str], breakdown:[{world,count}], total:int}                editable
  2 Major Milestones   kind 'ms_table'
      {columns:['Milestone','Date'], rows:[[name, date_str], …]}
  3 Work Breakdown Structure   kind 'wbs_tree'
      {worlds:[{name, layout:'tree'|'columns', root:{name, children:[node,…]}}]}
      node = {name:str, children:[node,…]}
  4 Sequence of Work   kind 'seq'
      {worlds:[{world, fronts:[{title, sequence:[str], instances:[str],
                                activities:[{id,name,wbs}]}]}]}              editable (structural)
  5 Interfaces & Dependencies   kind 'interfaces'
      {macro:[world,…], notes:[str], edges:[[a,b], …]}

Every value is derived from the schedule — no project-specific hardcoding.
"""
from collections import Counter, defaultdict
from datetime import datetime

from p6_narrative.intel.context import build_context
from p6_narrative.intel.fronts import detect_fronts, world_of
from p6_narrative.model import NarrativeDoc, Section

_MAX_WBS_DEPTH = 3
_MAX_WBS_KIDS = 12

# General EPC phase order (not project-specific): design/engineering → procurement →
# construction → testing/commissioning → close-out. Keyword-ranked so close-out is last.
_PHASE_WORDS = [
    (('design', 'engineering', 'ifc', 'drawing'), 1),
    (('procure', 'material', 'supply', 'fabricat'), 2),
    (('construct', 'execution', 'works', 'civil', 'install', 'build'), 3),
    (('test', 'commission', 'snag', 'inspection'), 4),
    (('closure', 'closeout', 'close-out', 'handover', 'completion', 'as-built', 'close'), 5),
]


def _wname(ctx, wid):
    return (ctx.data.wbs.get(wid) or {}).get('name') or str(wid)


def _leaf(label):
    return str(label).split(' / ')[-1].strip()


def _full_date(v):
    if not v:
        return None
    if isinstance(v, datetime):
        dt = v
    else:
        try:
            dt = datetime.strptime(str(v)[:10], '%Y-%m-%d')
        except ValueError:
            return str(v)
    return '%d %s %d' % (dt.day, dt.strftime('%B'), dt.year)


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
    date = {w: _median_str(ds) for w, ds in starts.items()}
    return sorted(worlds, key=lambda w: (_phase_rank(w['world']), date.get(w['world'], '~')))


def consolidate_seq(seq):
    """Collapse repeated sub-discipline stages (…Structural Shop Drawing Submittal /
    …Steel … / …Arc …) to the shared stage. Fires only on a genuinely repeated 2-word
    suffix, so distinct sequences (Excavation → Footing → Columns) are untouched."""
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


def _wbs_size(ctx, wid):
    total, maxb = [0], [0]

    def walk(w, d):
        kids = ctx.children_of_wbs.get(w, [])
        if d < _MAX_WBS_DEPTH and kids:
            maxb[0] = max(maxb[0], len(kids))
            for k in kids[:_MAX_WBS_KIDS]:
                total[0] += 1
                walk(k, d + 1)
    walk(wid, 0)
    return total[0], maxb[0]


def _wbs_tree(ctx, wid, depth=0):
    node = {'name': _wname(ctx, wid) if depth == 0 else _leaf(_wname(ctx, wid)), 'children': []}
    kids = ctx.children_of_wbs.get(wid, [])
    if kids and depth < _MAX_WBS_DEPTH:
        for k in kids[:_MAX_WBS_KIDS]:
            node['children'].append(_wbs_tree(ctx, k, depth + 1))
        if len(kids) > _MAX_WBS_KIDS:
            node['children'].append({'name': '+%d more' % (len(kids) - _MAX_WBS_KIDS),
                                     'children': [], 'more': True})
    return node


# ── section builders ─────────────────────────────────────────────────────────
def _overview(ctx, r):
    worlds = _ordered_worlds(ctx, r['worlds'])
    total = sum(w['total'] for w in worlds)
    names = [w['world'] for w in worlds]
    worldlist = (', '.join(names[:-1]) + ' and ' + names[-1]) if len(names) > 1 else (names[0] if names else 'the project')
    paras = [
        "This Narrative Report is a comprehensive study of the project's baseline schedule. Its "
        "purpose is to explain the plan in clear planning language — the overall execution "
        "strategy, the sequence of work, the major work-package methodologies, the key "
        "milestones, the Work Breakdown Structure, and the interfaces between the major scopes — "
        "so the complete plan can be understood without opening the P6 schedule, while every "
        "statement stays traceable to the baseline activities.",
        "The project is planned to progress from engineering and design, through procurement, "
        "into construction, and finally project close-out. Design and engineering mature the "
        "drawings and secure approvals; procurement delivers the materials; construction executes "
        "the physical work as a set of repeatable work-package sequences; and close-out completes "
        "the scope. The sections that follow set out the milestones (2), the breakdown structure "
        "(3), how each scope is executed (4), and how the scopes interface (5).",
    ]
    breakdown = [{'world': w['world'], 'count': w['total']} for w in worlds]
    return Section('1', 'Project Overview', 'overview', 'auto',
                   payload={'paragraphs': paras, 'breakdown': breakdown, 'total': total,
                            'worldlist': worldlist}, editable=True,
                   note='Executive introduction — edit the prose freely.')


def _milestones(ctx):
    rows = []
    for a in ctx.milestones.values():
        if (a.get('task_type') or '') != 'FinishMilestone':
            continue
        d = a.get('planned_finish') or a.get('planned_start') or a.get('constraint_date')
        if a.get('name'):
            rows.append((str(d)[:10] if d else '~', a.get('name'), _full_date(d) or '—'))
    rows.sort()
    return Section('2', 'Major Milestones', 'ms_table', 'auto',
                   payload={'columns': ['Milestone', 'Date'],
                            'rows': [[n, ds] for _, n, ds in rows]},
                   note=None if rows else 'No finish milestones are defined in the file.')


def _wbs(ctx, r):
    names = {w['world'] for w in r['worlds']}
    worlds = []
    for wid in ctx.branch_ids:
        if _wname(ctx, wid) not in names:
            continue
        n, maxb = _wbs_size(ctx, wid)
        worlds.append({'name': _wname(ctx, wid),
                       'layout': 'tree' if (n <= 16 and maxb <= 5) else 'columns',
                       'root': _wbs_tree(ctx, wid)})
    return Section('3', 'Work Breakdown Structure', 'wbs_tree', 'auto',
                   payload={'worlds': worlds},
                   note='Actual P6 breakdown per scope; layout adapts (small = centered tree, '
                        'large = compact columns). Structure only — sequence is in Section 4.')


def _sequence(ctx, r):
    worlds = []
    for w in _ordered_worlds(ctx, r['worlds']):
        fronts = []
        for f in sorted(w['fronts'], key=lambda f: -len(f['activities'])):
            fronts.append({
                'title': (f['title'] or 'front').title(),
                'sequence': consolidate_seq([p for p, _ in f['phase_flow']]),
                'instances': [_leaf(i) for i in f['instances']],
                'activities': f['activities'],
            })
        worlds.append({'world': w['world'], 'fronts': fronts})
    return Section('4', 'Sequence of Work', 'seq', 'auto',
                   payload={'worlds': worlds}, editable=True,
                   note='How each scope is executed, at the major work-package level. '
                        'Edit packages, order and grouping; P6 activities stay in the drill-down.')


def _interfaces(ctx, r):
    seq = [w['world'] for w in _ordered_worlds(ctx, r['worlds'])]
    low = [n.lower() for n in seq]
    notes = []
    if any('design' in n or 'engineering' in n for n in low):
        notes.append('Engineering and design deliverables — IFC drawings and shop-drawing '
                     'submittal → approval — release each scope for procurement and construction.')
    if any('procure' in n for n in low):
        notes.append('Procurement (material submittal → approval → delivery) secures materials '
                     'ahead of the construction fronts that consume them.')
    if any('construct' in n for n in low):
        notes.append('The construction fronts are executed per building / area, each following '
                     'its work-package sequence once its engineering and materials are in place.')
    if any(k in n for n in low for k in ('commission', 'test', 'closure', 'closeout', 'completion')):
        notes.append('Completion of the construction scope enables testing / commissioning and '
                     'project close-out.')
    edges = [[_leaf(a), _leaf(b)] for a, b, _c in r['interactions'].get('building_edges', [])[:12]]
    return Section('5', 'Interfaces & Dependencies', 'interfaces', 'auto',
                   payload={'macro': seq, 'notes': notes, 'edges': edges},
                   note='Macro execution flow and the key cross-scope / cross-front dependencies.')


def build_report(data, meta=None, setup=None, **_ignored):
    """Assemble the v5 Narrative Report as a :class:`NarrativeDoc`."""
    ctx = build_context(data)
    r = detect_fronts(ctx)
    project = data.project or {}
    meta = dict(meta or {})
    meta.setdefault('project_name', project.get('name') or 'the project')
    meta.setdefault('project_id', project.get('id'))
    meta.setdefault('mode', r.get('mode'))
    setup = setup or {}
    logos = {k: setup.get(k + '_logo') for k in ('owner', 'consultant', 'contractor')
             if setup.get(k + '_logo')}
    if logos:
        meta['logos'] = logos
    sections = [_overview(ctx, r), _milestones(ctx), _wbs(ctx, r),
                _sequence(ctx, r), _interfaces(ctx, r)]
    return NarrativeDoc(meta, sections)
