"""Primavera P6 (the raw export) against what the tool shows, feature by feature — comment 5.

For each schedule, every value P6 itself wrote into the file (dates, status, % complete, total
float — derived from P6's own early/late dates and calendars when the XML stores none —
relationships and lags, calendars, costs) is read by tests/p6_raw.py, which does not use the
tool, and compared with the result of the tool's own import pipeline: Overview, the Gantt row of
every activity, all Schedule Health checks, Calendar Audit and Earned Value.
"""
import collections
import os
import sys

from tests.p6_raw import Raw

ROWS = []


def chk(project, feature, check, p6, tool, ok=None, note=''):
    if ok is None:
        ok = (p6 == tool)
    ROWS.append({'project': project, 'feature': feature, 'check': check, 'p6': p6, 'tool': tool, 'ok': bool(ok), 'note': note})


def day(d):
    return d.strftime('%Y-%m-%d') if d else None


def reconcile(path, res):
    """[{project, feature, check, p6, tool, ok, note}] — the tool's import result against P6."""
    global ROWS
    ROWS = []
    R = Raw(path)
    P = os.path.basename(path).split(' - ')[0].split('_Baseline')[0].split('-BL')[0][:28]
    base = {c: a for c, a in R.acts.items() if a['type'] in ('Task Dependent', 'Resource Dependent')}
    open_ = lambda a: a['status'] != 'Completed'
    tfd = lambda c: (R.acts[c]['tf_h'] / R.hpd(c)) if R.acts[c]['tf_h'] is not None else None
    has_tf = any(a['tf_h'] is not None for a in R.acts.values() if open_(a))

    # ── Overview / import ──
    chk(P, 'Overview', 'Activities', len(R.acts), res['activity_count'])
    chk(P, 'Overview', 'Calendars', len(R.cals), res['calendar_count'])
    chk(P, 'Overview', 'Data date', day(R.project['data_date']), (res['data_date'] or '')[:10])
    chk(P, 'Overview', 'Project name', R.project['name'], res['project_name'])

    # ── Schedule (Gantt) — every activity ──
    G = {a['id']: a for a in res['activities']}
    chk(P, 'Gantt', 'Activities shown', len(R.acts), len(G))
    mism = collections.Counter(); ex = {}
    for c, a in R.acts.items():
        g = G.get(c)
        if not g:
            mism['missing'] += 1; ex.setdefault('missing', c); continue
        pairs = {'start': (day(a['start']), (g['start'] or '')[:10] or None),
                 'finish': (day(a['finish']), (g['finish'] or '')[:10] or None),
                 'status': (a['status'], g['status']),
                 'pct': (round((a['pct'] or 0) * 100), round(g['pct'] or 0)),
                 'milestone': ('Milestone' in (a['type'] or ''), bool(g['milestone']))}
        if a['tf_h'] is not None and open_(a):
            pairs['total float'] = (round(tfd(c), 1), None if g['tf'] is None else round(g['tf'], 1))
            pairs['critical'] = (tfd(c) <= 0, bool(g['critical']))
        for k, (x, y) in pairs.items():
            if x != y:
                mism[k] += 1; ex.setdefault(k, f'{c}: P6 {x} / tool {y}')
    for k in ('start', 'finish', 'status', 'pct', 'milestone', 'total float', 'critical', 'missing'):
        chk(P, 'Gantt', f'per-activity {k} (mismatches)', 0, mism[k], note=ex.get(k, ''))

    M = res['audit_modules']['modules']
    K = lambda m: M[m]['kpis']
    # ── Schedule Health ──
    chk(P, 'Schedule Health', 'activities checked (tasks, no milestones/LOE)', len(base), K('open_ends')['total_activities'])
    tc = collections.Counter(r['type'] for r in R.rels)
    n = len(R.rels)
    rt = K('relationship_types')
    chk(P, 'Relationship Types', 'total relationships', n, rt['total_relationships'])
    for t in ('fs', 'ss', 'ff', 'sf'):
        chk(P, 'Relationship Types', f'{t.upper()} %', round(tc[t.upper()] / n * 100, 1) if n else 0, rt[f'{t}_pct'])
    chk(P, 'Relationship Types', 'non-FS links', n - tc['FS'], rt['non_fs'])
    lg = K('lag_lead')
    lagged = [r for r in R.rels if abs(r['lag_h']) > 1e-9]
    chk(P, 'Lag Report', 'links with a lag', len(lagged), lg['lagged_count'])
    chk(P, 'Lag Report', 'leads (negative lag)', sum(1 for r in R.rels if r['lag_h'] < 0), lg['leads_count'])
    chk(P, 'Lag Report', 'positive lags', sum(1 for r in R.rels if r['lag_h'] > 0), lg['positive_count'])
    bt = {x['type']: x['count'] for x in lg.get('by_type') or []}
    lt = collections.Counter(r['type'] for r in lagged)
    for t in ('FS', 'SS', 'FF', 'SF'):
        if lt[t] or bt.get(t):
            chk(P, 'Lag Report', f'lagged {t} links', lt[t], bt.get(t, 0))
    chk(P, 'Leads', 'leads', sum(1 for r in R.rels if r['lag_h'] < 0), K('leads')['leads'])
    if has_tf:
        chk(P, 'Negative Float', 'open tasks with float < 0', sum(1 for c, a in base.items() if open_(a) and a['tf_h'] is not None and tfd(c) < 0),
            K('negative_float')['negative_count'])
        chk(P, 'Float Analysis', 'open tasks with float > 44 d',
            sum(1 for c, a in base.items() if open_(a) and a['tf_h'] is not None and tfd(c) > 44), K('float')['above_threshold'])
    od = lambda c: (R.acts[c]['od_h'] or 0) / R.hpd(c)
    rd = lambda c: (R.acts[c]['rd_h'] or 0) / R.hpd(c)
    chk(P, 'High Duration', 'tasks with original duration > 44 d', sum(1 for c in base if od(c) > 44),
        K('high_duration')['over_threshold'])
    chk(P, 'High Duration', 'longest original duration (d)', round(max((od(c) for c in base), default=0), 1),
        round(K('high_duration')['max_duration'] or 0, 1))
    # Out of sequence — the P6 condition on ACTUAL dates (successor progressed ahead of its logic)
    def oos(t, s, p):
        if t == 'FS': return bool(s['act_start']) and (p['act_finish'] is None or p['act_finish'] > s['act_start'])
        if t == 'SS': return bool(s['act_start']) and (p['act_start'] is None or p['act_start'] > s['act_start'])
        if t == 'FF': return bool(s['act_finish']) and (p['act_finish'] is None or p['act_finish'] > s['act_finish'])
        if t == 'SF': return bool(s['act_finish']) and (p['act_start'] is None or p['act_start'] > s['act_finish'])
    # as P6's schedule log: only a predecessor that is unfinished WORK (a task without an actual finish)
    oos_acts = {r['succ'] for r in R.rels if r['succ'] in base and r['pred'] in base
                and R.acts[r['pred']]['act_finish'] is None and oos(r['type'], R.acts[r['succ']], R.acts[r['pred']])}
    chk(P, 'Out of Sequence', 'tasks progressed ahead of their logic', len(oos_acts), K('out_of_sequence')['oos_count'])
    # Dangling — start not driven by FS/SS, finish not driving FS/FF
    pin = collections.defaultdict(set); pout = collections.defaultdict(set)
    for r in R.rels:
        pin[r['succ']].add(r['type']); pout[r['pred']].add(r['type'])
    dstart = {c for c in base if not (pin[c] & {'FS', 'SS'})}
    dfin = {c for c in base if not (pout[c] & {'FS', 'FF'})}
    dk = K('dangling')
    chk(P, 'Dangling', 'dangling start only', len(dstart - dfin), dk['start_dangling'])
    chk(P, 'Dangling', 'dangling finish only', len(dfin - dstart), dk['finish_dangling'])
    chk(P, 'Dangling', 'both', len(dstart & dfin), dk['both_dangling'])
    chk(P, 'Whole-day Durations', 'tasks with a part-day duration',
        sum(1 for c in base if abs(od(c) - round(od(c))) > 1e-6), K('whole_day')['decimal_count'])
    preds = collections.defaultdict(set); succs = collections.defaultdict(set)
    for r in R.rels:
        preds[r['succ']].add(r['pred']); succs[r['pred']].add(r['succ'])
    oe = K('open_ends')
    chk(P, 'Open Ends', 'tasks without a predecessor', sum(1 for c in base if not preds[c]), oe['no_predecessor'])
    chk(P, 'Open Ends', 'tasks without a successor', sum(1 for c in base if not succs[c]), oe['no_successor'])
    # circular logic — Tarjan on the raw links
    idx, low, on, st, sccs, cnt = {}, {}, set(), [], [], [0]
    sys.setrecursionlimit(100000)
    def sc(v):
        idx[v] = low[v] = cnt[0]; cnt[0] += 1; st.append(v); on.add(v)
        for w in succs[v]:
            if w not in idx:
                sc(w); low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            comp = []
            while True:
                w = st.pop(); on.discard(w); comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(comp)
    for v in list(R.acts):
        if v not in idx:
            sc(v)
    chk(P, 'Circular Logic', 'loops', len(sccs), K('circular')['loops'])
    if has_tf:
        crit = sum(1 for c, a in base.items() if open_(a) and a['tf_h'] is not None and tfd(c) <= 0)
        chk(P, 'Critical Path / CPLI', 'critical open tasks (float <= 0)', crit, K('cpli')['critical_count'])
    # ── P6 Calendar Audit ──
    ca = res['calendar_audit']
    for c in ca.get('assigned_calendars') or []:
        chk(P, 'P6 Calendar Audit', f"hours/day · {c['name']}", R.cals.get(str(c['object_id'])), c.get('hours_per_day'))
        chk(P, 'P6 Calendar Audit', f"activities on · {c['name']}",
            sum(1 for a in R.acts.values() if str(a['cal']) == str(c['object_id'])), c.get('activity_count'))
    # ── Consultant Review's but-for scheduler (p6_compare.schedule) — with no change applied it
    #    must reproduce P6's own schedule: the project finish exactly, every activity's early finish
    #    to the minute where P6's dates follow from the file's logic (comment 44) ──
    try:
        from p6_evm.parser import parse_file
        from p6_compare.schedule import forward_pass, project_finish
        data = parse_file(path)
        efs = forward_pass(data)
        open_acts = [(o, a) for o, a in data.activities.items() if not a.get('actual_finish') and a.get('remaining_early_finish')]
        same = sum(1 for o, a in open_acts if efs.get(o) and abs((efs[o] - a['remaining_early_finish']).total_seconds()) < 60)
        pf = project_finish(data)
        p6f = R.project['finish']
        chk(P, 'Consultant Review (but-for scheduler)', 'project finish with no change applied',
            p6f.strftime('%Y-%m-%d %H:%M') if p6f else None, pf.strftime('%Y-%m-%d %H:%M') if pf else None,
            ok=bool(p6f and pf and abs((pf - p6f).total_seconds()) < 60))
        share = round(100.0 * same / len(open_acts), 1) if open_acts else 100.0
        chk(P, 'Consultant Review (but-for scheduler)', 'open activities whose early finish equals P6 (%)',
            '≥ 90', share, ok=share >= 90.0, note=f'{same} of {len(open_acts)}')
    except Exception as exc:                                  # never hide a crash as a pass
        chk(P, 'Consultant Review (but-for scheduler)', 'runs', 'ok', str(exc)[:80], ok=False)

    # ── WBS — every element's activity count and dates, rolled up from P6's own activity dates ──
    kids = collections.defaultdict(list)
    for w, parent in R.wbs.items():
        kids[parent].append(w)
    under = {}

    def collect(w):
        if w in under:
            return under[w]
        acts = [c for c, a in R.acts.items() if a.get('wbs') == w]
        for k in kids.get(w, []):
            acts += collect(k)
        under[w] = acts
        return acts
    bad_n = bad_s = bad_f = 0
    ex = ''
    for node in res.get('wbs_summary') or []:
        acts = collect(str(node['id']))
        if not acts:
            continue
        starts = [R.acts[c]['start'] for c in acts if R.acts[c]['start']]
        fins = [R.acts[c]['finish'] for c in acts if R.acts[c]['finish']]
        if len(acts) != node.get('activities'):
            bad_n += 1; ex = ex or f"{node['name']}: P6 {len(acts)} / tool {node.get('activities')}"
        if starts and day(min(starts)) != node.get('start'):
            bad_s += 1; ex = ex or f"{node['name']} start: P6 {day(min(starts))} / tool {node.get('start')}"
        if fins and day(max(fins)) != node.get('finish'):
            bad_f += 1; ex = ex or f"{node['name']} finish: P6 {day(max(fins))} / tool {node.get('finish')}"
    nodes = len([n for n in res.get('wbs_summary') or [] if collect(str(n['id']))])
    chk(P, 'WBS', f'elements checked', nodes, nodes, ok=nodes > 0)
    for k, v in (('activity count', bad_n), ('start', bad_s), ('finish', bad_f)):
        chk(P, 'WBS', f'per-element {k} (mismatches)', 0, v, note=ex)

    # ── Earned Value — P6's own formulas ('Activity percent complete' earned value):
    #    BAC = budgeted (planned) cost · EV = BAC × % complete · AC = actual cost ·
    #    PV = BAC × schedule % complete (data date within each activity's planned dates, working time)
    bac = sum(a.get('planned_cost') or 0 for a in R.acts.values())
    if bac:
        tol = lambda x, y: abs(x - (y or 0)) <= max(1.0, abs(x) * 1e-6)
        ev = sum((a.get('planned_cost') or 0) * (a['pct'] or 0) for a in R.acts.values())
        cat_bac = sum(c.get('bac') or 0 for c in (res.get('categories') or {}).values())
        chk(P, 'Earned Value', 'budget at completion (BAC)', round(bac), round(cat_bac), ok=tol(bac, cat_bac))
        chk(P, 'Earned Value', 'earned value (EV = BAC × % complete)', round(ev), round(res['ev'] or 0), ok=tol(ev, res['ev']))
        ac_ = sum(a['actual_cost'] for a in R.acts.values())
        chk(P, 'Earned Value', 'actual cost (AC)', round(ac_), round(res['ac'] or 0), ok=tol(ac_, res['ac']))
        if ac_ and res.get('cpi') is not None:
            chk(P, 'Earned Value', 'CPI = EV / AC', round(ev / ac_, 4), round(res['cpi'], 4))
        if getattr(R, 'calendars', None):
            dd = R.project['data_date']
            pv = 0.0
            for a in R.acts.values():
                c, s0, f0 = a.get('planned_cost') or 0, a.get('pl_start'), a.get('pl_finish')
                if not c or not s0 or not f0:
                    continue
                if dd >= f0:
                    pv += c
                elif dd > s0:
                    tot = R.calendars.work_minutes(a['cal'], s0, f0)
                    pv += c * (R.calendars.work_minutes(a['cal'], s0, dd) / tot if tot else 1.0)
            chk(P, 'Earned Value', 'planned value (PV = BAC × schedule % complete)', round(pv), round(res['pv'] or 0),
                ok=tol(pv, res['pv']))

    # ── P6 Calendar Audit — working days per month on the main calendar (from P6's calendar) ──
    if getattr(R, 'calendars', None):
        ca = res['calendar_audit']
        pc = str(ca.get('primary_calendar_id'))
        months = ((ca.get('by_calendar') or {}).get(pc) or {}).get('monthly_stats') or []
        bad, ex = 0, ''
        import datetime as _d
        for m in months:
            days = [x['d'] for x in m.get('days') or []]
            if not days:
                continue
            wd = sum(1 for d0 in days if R.calendars.work_minutes(pc, _d.datetime(m['year'], m['month'], d0),
                                                                  _d.datetime(m['year'], m['month'], d0) + _d.timedelta(days=1)) > 0)
            if wd != m.get('working_days'):
                bad += 1; ex = ex or f"{m['label']}: P6 {wd} / tool {m.get('working_days')}"
        chk(P, 'P6 Calendar Audit', f'working days per month ({len(months)} months, main calendar)', 0, bad, note=ex)

    # ── Earned Value ──
    ac = sum(a['actual_cost'] for a in R.acts.values())
    if ac:
        chk(P, 'Earned Value', 'actual cost (AC)', round(ac), round(res['ac'] or 0), ok=abs(ac - (res['ac'] or 0)) <= max(1, ac * 1e-6))
    return ROWS
