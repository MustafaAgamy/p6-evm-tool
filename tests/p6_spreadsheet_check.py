"""The P6 file opened as a spreadsheet, and every Schedule Health number proved against it.

For each XER this reads the TASK / PROJWBS / CALENDAR / TASKPRED tables straight from the file
(p6_evm.xer.read_xer_tables only splits the text into rows - none of the tool's import or
Schedule Health code is used for the P6 side), writes one row per activity to an Excel workbook
(the same columns as a P6 spreadsheet export: Activity ID, Type, Status, WBS, Original Duration,
Total Float, Critical) and counts them the way the P6 filters do:

    Critical                  not completed, not a Level of Effort / WBS Summary, and Total Float
                              <= the project's critical limit (P6's default Critical filter)
    Total Float > 44d         not completed and Total Float > 44 days
    Total Float < 0           not completed and Total Float < 0
    Near critical             not completed and Total Float within range 1d - 10d
    Original Duration > 44d   every activity type; and Activity Type = Task Dependent

Then it runs the tool's own import and compares every figure, whole schedule and per major WBS.

    python tests/p6_spreadsheet_check.py <file.xer> [...] [--out <folder>]

Exit code 1 when any figure differs.
"""
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from p6_evm.xer import read_xer_tables, _current_and_baseline_project   # noqa: E402

TYPES = {'TT_Task': 'Task Dependent', 'TT_Rsrc': 'Resource Dependent', 'TT_Mile': 'Start Milestone',
         'TT_FinMile': 'Finish Milestone', 'TT_LOE': 'Level of Effort', 'TT_WBS': 'WBS Summary'}
STATUS = {'TK_NotStart': 'Not Started', 'TK_Active': 'In Progress', 'TK_Complete': 'Completed'}
LIMIT = 44


def _num(v):
    return float(v) if v not in (None, '') else None


def p6_rows(path):
    """One dict per activity of the file's own project, from the raw tables."""
    t = read_xer_tables(path)
    proj, _bl = _current_and_baseline_project(t)
    pid = proj.get('proj_id')
    crit_limit = _num(proj.get('critical_drtn_hr_cnt')) or 0.0
    longest = 'DrivPath' in (proj.get('critical_path_type') or '')
    cal = {c['clndr_id']: (c.get('clndr_name'), _num(c.get('day_hr_cnt')) or 8.0) for c in t.get('CALENDAR', [])}
    wbs = {w['wbs_id']: w for w in t.get('PROJWBS', []) if not pid or w.get('proj_id') in (None, '', pid)}

    def path_of(wid):
        names = []
        while wid in wbs and wbs[wid].get('proj_node_flag') != 'Y':
            names.append(wbs[wid].get('wbs_name') or '')
            wid = wbs[wid].get('parent_wbs_id')
        return list(reversed(names))

    rows = []
    for r in t.get('TASK', []):
        if pid and r.get('proj_id') not in (None, '', pid):
            continue
        name, hours = cal.get(r.get('clndr_id'), ('', 8.0))
        tf, od = _num(r.get('total_float_hr_cnt')), _num(r.get('target_drtn_hr_cnt')) or 0.0
        done = r.get('status_code') == 'TK_Complete'
        if done or r.get('task_type') in ('TT_LOE', 'TT_WBS'):
            critical = False          # P6 never flags completed work or a Level of Effort / WBS Summary
        elif longest and r.get('driving_path_flag'):
            critical = r.get('driving_path_flag') == 'Y'
        else:
            critical = tf is not None and tf <= crit_limit + 1e-9
        p = path_of(r.get('wbs_id'))
        rows.append({
            'oid': r.get('task_id'), 'cstr': r.get('cstr_type') or '', 'raw_type': r.get('task_type'),
            'id': r.get('task_code'), 'name': r.get('task_name'), 'type': TYPES.get(r.get('task_type'), r.get('task_type')),
            'status': STATUS.get(r.get('status_code'), r.get('status_code')), 'done': done,
            'major_wbs': p[0] if p else '(no WBS)', 'wbs': ' > '.join(p), 'path': p, 'calendar': name, 'day_hours': hours,
            'od_hours': od, 'od_days': od / hours, 'tf_hours': tf, 'tf_days': None if tf is None else tf / hours,
            'critical': critical,
        })
    ids = {r['oid'] for r in rows}
    rels = [p for p in t.get('TASKPRED', []) if p.get('task_id') in ids and p.get('pred_task_id') in ids]
    return rows, rels


HARD = {'CS_MANDSTART', 'CS_MANDFIN', 'CS_MSO', 'CS_MEO'}     # Mandatory Start / Finish, Start On, Finish On


def p6_construction(rows):
    """The Construction WBS counted from the raw WBS names: every activity under the WBS node
    named construction, at the shallowest level that carries the name."""
    levels = [i for r in rows for i, n in enumerate(r['path']) if 'construction' in n.lower()]
    if not levels:
        return None
    lv = min(levels)
    con = [r for r in rows if len(r['path']) > lv and 'construction' in r['path'][lv].lower()]
    live = [r for r in con if not r['done'] and r['tf_days'] is not None]
    task = [r for r in con if r['type'] == 'Task Dependent']
    return {
        'activities':   len(con),
        'completed':    sum(1 for r in con if r['done']),
        'tf_over':      sum(1 for r in live if r['tf_days'] > LIMIT),
        'tf_base':      len(live),
        'task':         len(task),
        'od_over_task': sum(1 for r in task if r['od_days'] > LIMIT),
        'od_over_all':  sum(1 for r in con if r['od_days'] > LIMIT),
    }


def p6_logic_counts(rows, rels):
    """The logic checks, counted from the raw relationships: open ends, dangling (the two P6
    filters), hard constraints, decimal durations, loops."""
    preds, succs = collections.defaultdict(list), collections.defaultdict(list)
    for p in rels:
        kind = (p.get('pred_type') or 'PR_FS').replace('PR_', '')
        preds[p['task_id']].append(kind)
        succs[p['pred_task_id']].append(kind)
    real = [r for r in rows if r['raw_type'] in ('TT_Task', 'TT_Rsrc')]
    c = collections.Counter()
    c['task_activities'] = len(real)
    c['all_activities'] = len(rows)
    for r in rows:                   # P6's schedule log lists every activity type
        P, S = preds[r['oid']], succs[r['oid']]
        c['no_pred'] += not P
        c['no_succ'] += not S
        c['open_ends'] += (not P) or (not S)
    for r in real:
        P, S = preds[r['oid']], succs[r['oid']]
        sd = not any(k in ('FS', 'SS') for k in P)
        fd = not any(k in ('FS', 'FF') for k in S)
        c['dangling'] += sd or fd
        c['dangling_start_only'] += sd and not fd
        c['dangling_finish_only'] += fd and not sd
        c['dangling_both'] += sd and fd
        c['hard'] += r['cstr'] in HARD
        if r['od_hours'] and abs(r['od_days'] - round(r['od_days'])) > 0.01:
            c['decimal'] += 1
    # a loop exists when a topological sort cannot empty the network (Level of Effort / WBS
    # Summary activities only span work - P6 does not treat a chain through one as a loop)
    span = {r['oid'] for r in rows if r['raw_type'] in ('TT_LOE', 'TT_WBS')}
    indeg, out = collections.Counter(), collections.defaultdict(list)
    nodes = {r['oid'] for r in rows} - span
    for p in rels:
        a, b = p['pred_task_id'], p['task_id']
        if a in nodes and b in nodes:
            out[a].append(b)
            indeg[b] += 1
    queue = [n for n in nodes if not indeg[n]]
    seen = 0
    while queue:
        n = queue.pop()
        seen += 1
        for b in out[n]:
            indeg[b] -= 1
            if not indeg[b]:
                queue.append(b)
    c['in_loops'] = len(nodes) - seen
    return c


def p6_counts(rows):
    """The P6 filters, counted whole schedule and per major WBS."""
    def count(sel):
        c = collections.Counter(r['major_wbs'] for r in rows if sel(r))
        return sum(c.values()), dict(c)
    live = lambda r: not r['done'] and r['tf_days'] is not None
    return {
        'activities':        count(lambda r: True),
        'not_completed':     count(lambda r: not r['done']),
        'critical':          count(lambda r: r['critical']),
        'tf_over':           count(lambda r: live(r) and r['tf_days'] > LIMIT),
        'tf_negative':       count(lambda r: live(r) and r['tf_days'] < 0),
        'near_critical':     count(lambda r: live(r) and not r['critical'] and 1 - 1e-9 <= r['tf_days'] <= 10 + 1e-9),
        'od_over_all':       count(lambda r: r['od_days'] > LIMIT),
        'od_over_task':      count(lambda r: r['type'] == 'Task Dependent' and r['od_days'] > LIMIT),
        'task_dependent':    count(lambda r: r['type'] == 'Task Dependent'),
    }


def tool_counts(path):
    from p6_evm.parser import parse_file
    from p6_audit.engine import audit_modules
    with open(os.path.join(ROOT, 'config.json')) as f:
        cfg = json.load(f)
    m = audit_modules(parse_file(path), cfg)['modules']

    def table(rows, field):
        # High Duration lists a deeper Construction WBS as 'Zone > Construction': fold it back
        # under its major WBS for the per-WBS comparison
        per = collections.Counter()
        for r in rows:
            per[r['wbs'].split(' > ')[0]] += int(r.get(field) or 0)
        return sum(per.values()), {w: n for w, n in per.items() if n}
    cp, fl, hd = m['cpli'], m['float'], m['high_duration']
    fw, hw = fl['mgmt']['p6_wbs'], hd['mgmt']['wbs']
    out = {
        'activities':     table(cp['wbs_summary'], 'activities'),
        'not_completed':  table(cp['wbs_summary'], 'remaining'),
        'critical':       table(cp['wbs_summary'], 'critical'),
        'tf_over':        table(fw, 'over'),
        'tf_negative':    table(fw, 'negative'),
        'near_critical':  (fl['mgmt']['stats']['near_critical'], None),
        'od_over_all':    table(hw, 'p6_over'),
        'od_over_task':   table(hw, 'task_over'),
    }
    tiles = {
        'CPLI - Total Activities':                 (cp['kpis']['total_activities'], 'activities'),
        'CPLI - Remaining Activities':             (cp['kpis']['remaining_activities'], 'not_completed'),
        'CPLI - Critical Activities':              (cp['kpis']['critical_count'], 'critical'),
        'CPLI - driving path rows':                (len(cp['findings']), 'critical'),
        'Float - Critical Activities':             (fl['mgmt']['stats']['critical'], 'critical'),
        'Float - Activities above 44 d':           (fl['kpis']['above_threshold'], 'tf_over'),
        'Negative Float - count':                  (m['negative_float']['kpis']['negative_count'], 'tf_negative'),
        'Negative Float - rows':                   (len(m['negative_float']['findings']), 'tf_negative'),
        'High Duration - whole schedule (P6 filter)': (hd['kpis']['all_over_threshold'], 'od_over_all'),
        'High Duration - whole schedule rows':        (len(hd['findings']) + len(hd['mgmt']['not_counted']), 'od_over_all'),
        'High Duration - of which Task Dependent':    (hd['kpis']['all_task_over'], 'od_over_task'),
        'High Duration - Task Dependent activities':  (hd['kpis']['all_task_activities'], 'task_dependent'),
    }
    rt = m['relationship_types']['kpis']
    return out, tiles, rt, m['leads']['kpis'], m['lag_lead']['kpis'], m


def write_workbook(path, rows, counts, out_dir):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Activities (from the P6 file)'
    ws.append(['Activity ID', 'Activity Name', 'Activity Type', 'Activity Status', 'Major WBS', 'WBS',
               'Calendar', 'Hours / day', 'Original Duration (h)', 'Original Duration (d)',
               'Total Float (h)', 'Total Float (d)', 'Critical'])
    for r in rows:
        ws.append([r['id'], r['name'], r['type'], r['status'], r['major_wbs'], r['wbs'], r['calendar'], r['day_hours'],
                   r['od_hours'], round(r['od_days'], 2), r['tf_hours'],
                   None if r['tf_days'] is None else round(r['tf_days'], 2), 'Yes' if r['critical'] else 'No'])
    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = 'A2'
    cs = wb.create_sheet('Counts by major WBS')
    heads = [('activities', 'Activities'), ('not_completed', 'Not Completed'), ('critical', 'Critical'),
             ('tf_over', f'Total Float > {LIMIT}d'), ('tf_negative', 'Total Float < 0'),
             ('od_over_all', f'Original Duration > {LIMIT}d (every type)'),
             ('od_over_task', f'Original Duration > {LIMIT}d (Task Dependent)')]
    cs.append(['Major WBS'] + [h for _k, h in heads])
    for w, _n in sorted(counts['activities'][1].items(), key=lambda x: -x[1]):
        cs.append([w] + [counts[k][1].get(w, 0) for k, _h in heads])
    cs.append(['Whole schedule'] + [counts[k][0] for k, _h in heads])
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ' - P6 values.xlsx')
    wb.save(out)
    return out


def check(path, out_dir=None):
    """[(figure, p6, tool, ok)] for one schedule; writes the workbook when out_dir is given."""
    rows, rels = p6_rows(path)
    p6 = p6_counts(rows)
    stored = any(r['tf_hours'] is not None for r in rows if not r['done'])
    tool, tiles, rt, leads, lag, m = tool_counts(path)
    res = []
    float_keys = {'critical', 'tf_over', 'tf_negative', 'near_critical'}
    for key in tool:
        note = '' if (stored or key not in float_keys) else 'P6 stored no total float in this file'
        ok = (p6[key][0] == tool[key][0]
              and (tool[key][1] is None or {k: v for k, v in p6[key][1].items() if v} == tool[key][1]))
        res.append((f'{key} (whole schedule + every major WBS)', p6[key][0], tool[key][0], ok or bool(note), note))
    for name, (value, key) in tiles.items():
        note = '' if (stored or key not in float_keys) else 'P6 stored no total float in this file'
        res.append((name, p6[key][0], value, p6[key][0] == value or bool(note), note))
    ty = collections.Counter(p['pred_type'] for p in rels)
    for name, a, b in (('Relationships', len(rels), rt['total_relationships']), ('FS', ty['PR_FS'], rt['fs_count']),
                       ('SS', ty['PR_SS'], rt['ss_count']), ('FF', ty['PR_FF'], rt['ff_count']),
                       ('SF', ty['PR_SF'], rt['sf_count']),
                       ('Leads (negative lag)', sum(1 for p in rels if (_num(p['lag_hr_cnt']) or 0) < 0), leads['leads']),
                       ('Lags (positive lag)', sum(1 for p in rels if (_num(p['lag_hr_cnt']) or 0) > 0), lag['positive_count'])):
        res.append((name, a, b, a == b, ''))
    lc = p6_logic_counts(rows, rels)
    k = lambda mod: m[mod]['kpis']
    for name, a, b in (
            ('Open Ends - activities checked (every type)', lc['all_activities'], k('open_ends')['total_activities']),
            ('Open Ends - open ends', lc['open_ends'], k('open_ends')['open_ends']),
            ('Open Ends - no predecessor', lc['no_pred'], k('open_ends')['no_predecessor']),
            ('Open Ends - no successor', lc['no_succ'], k('open_ends')['no_successor']),
            ('Dangling - total', lc['dangling'], k('dangling')['total_dangling']),
            ('Dangling - start only', lc['dangling_start_only'], k('dangling')['start_dangling']),
            ('Dangling - finish only', lc['dangling_finish_only'], k('dangling')['finish_dangling']),
            ('Dangling - start + finish', lc['dangling_both'], k('dangling')['both_dangling']),
            ('Hard constraints', lc['hard'], m['hard_constraints']['kpis'].get('hard_count')),
            ('Decimal (not whole-day) durations', lc['decimal'], k('whole_day')['decimal_count']),
            ('Circular - a loop exists', lc['in_loops'] > 0, k('circular')['loops'] > 0),
            ('Lag - relationships with a lag or lead', sum(1 for p in rels if (_num(p['lag_hr_cnt']) or 0) != 0), lag['lagged_count'])):
        res.append((name, a, b, a == b, ''))
    # every percentage and score follows from its two counts
    def pct(n, base):
        return round(100.0 * n / base, 1) if base else 0.0
    nc = p6['not_completed'][0]
    for name, a, b in (
            ('Critical %', pct(p6['critical'][0], nc), m['cpli']['kpis']['critical_pct'] or 0.0),
            ('Float % above 44 d', pct(p6['tf_over'][0], nc), m['float']['kpis']['float_pct']),
            ('Negative Float %', pct(p6['tf_negative'][0], nc), m['negative_float']['kpis']['neg_pct']),
            ('Open End %', pct(lc['open_ends'], lc['all_activities']), k('open_ends')['open_end_pct']),
            ('Dangling %', pct(lc['dangling'], lc['task_activities']), k('dangling')['dangling_pct']),
            ('Decimal %', pct(lc['decimal'], lc['task_activities']), k('whole_day')['decimal_pct']),
            ('Lead %', pct(sum(1 for p in rels if (_num(p['lag_hr_cnt']) or 0) < 0), len(rels)), leads['lead_pct']),
            ('FS %', pct(ty['PR_FS'], len(rels)), rt['fs_pct'])):
        note = '' if (stored or name not in ('Critical %', 'Float % above 44 d', 'Negative Float %')) else 'P6 stored no total float in this file'
        res.append((name, a, b, a == b or bool(note), note))
    con = p6_construction(rows)
    if con:
        ind, hk = m['float']['mgmt']['indicators'], m['high_duration']['kpis']
        for name, a, b, floaty in (
                ('Construction - activities in P6 (Float Analysis)', con['activities'], ind['constr_all'], False),
                ('Construction - completed (Float Analysis)', con['completed'], ind['constr_completed'], False),
                ('Construction - not completed, with float', con['tf_base'], ind['constr_total'], True),
                ('Construction - Total Float > 44 d', con['tf_over'], ind['constr_over'], True),
                ('Construction - activities in P6 (High Duration)', con['activities'], hk['scope_p6_activities'], False),
                ('Construction - activities evaluated (High Duration)', con['activities'], hk['total_activities'], False),
                ('Construction - Original Duration > 44 d (the P6 filter)', con['od_over_all'], hk['over_threshold'], False),
                ('Construction - High Duration rows listed', con['od_over_all'], len(m['high_duration']['findings']), False),
                ('Construction - of which Task Dependent', con['od_over_task'], hk['scope_task_over'], False),
                ('High Duration % (Construction)', pct(con['od_over_all'], con['activities']), hk['high_pct'], False)):
            note = 'P6 stored no total float in this file' if (floaty and not stored) else ''
            res.append((name, a, b, a == b or bool(note), note))
    book = write_workbook(path, rows, p6, out_dir) if out_dir else None
    return res, book


def main(argv):
    out_dir = None
    if '--out' in argv:
        i = argv.index('--out')
        out_dir = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    bad = 0
    for path in argv:
        res, book = check(path, out_dir)
        print('\n' + os.path.basename(path) + (f'\n  workbook: {book}' if book else ''))
        for name, a, b, ok, note in res:
            bad += 0 if ok else 1
            print(f"  {'OK ' if ok else 'DIFF'} {name:<52} P6 {a!s:>7}   tool {b!s:>7}  {note}")
    print(f'\n{bad} figure(s) differ.' if bad else '\nEvery figure matches the P6 file.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
