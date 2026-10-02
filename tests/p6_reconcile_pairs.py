"""Primavera P6 against the tool's TWO-schedule features — comment 44.

For a pair of P6 exports (an earlier revision / baseline and a later update), every figure the
two-revision features show is worked out again from what P6 itself wrote into the two files —
read by tests/p6_raw.py, which does not use the tool — and compared:

  Baseline Revision / Update vs Update   activities added / removed / renamed, relationship
                                         changes, milestone dates, budget totals
  Consultant Review                      matched activities, both finishes and the slip,
                                         milestone finishes, every changed-logic row's links,
                                         every duration row's original / remaining days
  Critical Path Analyzer                 per schedule: counted / critical activities, data date,
                                         governing finish and its baseline finish
  Update Analysis                        actual and planned (baseline) activity status counts

reconcile_pair(earlier_path, later_path) -> [{project, feature, check, p6, tool, ok, note}]
"""
import os

from tests.p6_raw import Raw

ROWS = []
_MS = ('Start Milestone', 'Finish Milestone')


def chk(project, feature, check, p6, tool, ok=None, note=''):
    if ok is None:
        ok = (p6 == tool)
    ROWS.append({'project': project, 'feature': feature, 'check': check, 'p6': p6, 'tool': tool,
                 'ok': bool(ok), 'note': note})


def _day(d):
    return d.strftime('%Y-%m-%d') if d else None


def _long_to_day(s):
    """'01 June 2025' / '30-Aug-2025' / '30 Aug 2025' -> '2025-06-01'."""
    from datetime import datetime
    for f in ('%d %B %Y', '%d-%b-%Y', '%d %b %Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, f).strftime('%Y-%m-%d')
        except (TypeError, ValueError):
            pass
    return None


def _forecast(a):
    """P6's Finish column: the actual finish once finished, else the (early) finish."""
    return a.get('act_finish') or a.get('finish')


def _edges(R, codes):
    """(pred, succ) -> {type: lag hours} — every link P6 holds between two matched activities."""
    out = {}
    for r in R.rels:
        if r['pred'] in codes and r['succ'] in codes:
            out.setdefault((r['pred'], r['succ']), {})[r['type']] = r['lag_h']
    return out


def reconcile_pair(earlier_path, later_path):
    global ROWS
    ROWS = []
    from p6_evm.parser import parse_file
    from p6_evm.baseline import use_picked_baseline, resolve_baseline
    R0, R1 = Raw(earlier_path), Raw(later_path)
    P = f"{os.path.basename(earlier_path)[:18]} → {os.path.basename(later_path)[:22]}"
    c0, c1 = set(R0.acts), set(R1.acts)
    both = c0 & c1

    # ── Baseline Revision / Update vs Update (p6_revcompare) ──
    from p6_revcompare.compare import build_report_from_data as revision
    rv = revision(parse_file(earlier_path), parse_file(later_path))
    s = rv['summary']
    F = 'Baseline Revision / Update vs Update'
    chk(P, F, 'activities in the earlier revision', len(R0.acts), s['activities0'])
    chk(P, F, 'activities in the later revision', len(R1.acts), s['activities1'])
    chk(P, F, 'activities added (incl. Activity ID changes)', len(c1 - c0), s['added'] + s['id_changes'])
    chk(P, F, 'activities removed (incl. Activity ID changes)', len(c0 - c1), s['removed'] + s['id_changes'])
    renamed = sum(1 for c in both if (R0.acts[c]['name'] or '').strip() != (R1.acts[c]['name'] or '').strip())
    chk(P, F, 'activities renamed', renamed, s['renamed'])
    # relationships counted per P6 LINK: a pair may hold one link of each type (an SS + FF)
    e0, e1 = _edges(R0, both), _edges(R1, both)
    k0, k1 = set(e0), set(e1)
    add = sum(len(e1[k]) for k in k1 - k0)
    rem = sum(len(e0[k]) for k in k0 - k1)
    typ = lag = 0
    for k in k0 & k1:
        lag += sum(1 for t in e0[k] if t in e1[k] and abs(e0[k][t] - e1[k][t]) > 1e-6)
        gone, new = len(set(e0[k]) - set(e1[k])), len(set(e1[k]) - set(e0[k]))
        typ += min(gone, new)
        add += new - min(gone, new)
        rem += gone - min(gone, new)
    chk(P, F, 'relationships added', add, s['logic']['added'])
    chk(P, F, 'relationships removed', rem, s['logic']['removed'])
    chk(P, F, 'relationship type changed', typ, s['logic']['type'])
    chk(P, F, 'relationship lag changed', lag, s['logic']['lag'])
    bad, ex, n = 0, '', 0
    for m in rv['milestones']:
        if m.get('kind') in ('new', 'removed', 'idchange'):
            continue
        n += 1
        p6 = (_day(_forecast(R0.acts[m['id']])), _day(_forecast(R1.acts[m['id']])))
        tool = (_long_to_day(m['rev0']), _long_to_day(m['rev1']))
        if p6 != tool:
            bad += 1; ex = ex or f"{m['id']}: P6 {p6} / tool {tool}"
    chk(P, F, f'milestone finish dates ({n} milestones, mismatches)', 0, bad, note=ex)
    b0 = sum(a.get('planned_cost') or 0 for a in R0.acts.values())
    b1 = sum(a.get('planned_cost') or 0 for a in R1.acts.values())
    tb = rv['resource_changes']['total_budget']
    chk(P, F, 'budget of the earlier revision', round(b0), tb['rev0'], ok=abs(b0 - tb['rev0']) <= 1)
    chk(P, F, 'budget of the later revision', round(b1), tb['rev1'], ok=abs(b1 - tb['rev1']) <= 1)

    # ── Consultant Review (p6_compare) ──
    from p6_compare.report import build_report_from_data as consultant
    cr = consultant(parse_file(earlier_path), parse_file(later_path))
    F = 'Consultant Review'
    chk(P, F, 'matched activities (same Activity ID)', len(both), cr['matched_activities'])
    chk(P, F, 'activities in the update', len(R1.acts), cr['update_activity_count'])
    f0, f1 = R0.project['finish'], R1.project['finish']
    chk(P, F, 'baseline finish', _day(f0), _long_to_day(cr['baseline_finish']))
    chk(P, F, 'update finish', _day(f1), _long_to_day(cr['update_finish']))
    if f0 and f1:
        chk(P, F, 'finish slip (calendar days)', (f1.date() - f0.date()).days, cr['dashboard']['finish_slip_days'])
    bad, ex = 0, ''
    for m in cr['milestones']:
        a0, a1 = R0.acts[m['activity_id']], R1.acts[m['activity_id']]
        p6 = (_day(a0.get('act_finish') or a0.get('pl_finish') or a0.get('finish')), _day(_forecast(a1)))
        tool = (_long_to_day(m['baseline_finish']), _long_to_day(m['update_finish']))
        if p6 != tool:
            bad += 1; ex = ex or f"{m['activity_id']}: P6 {p6} / tool {tool}"
    chk(P, F, f"milestone finishes ({len(cr['milestones'])} milestones, mismatches)", 0, bad, note=ex)
    preds = lambda R, code: {(r['pred'], r['type']) for r in R.rels if r['succ'] == code}
    bad, ex = 0, ''
    for row in cr['logic']['rows']:
        code = row['activity_id']
        t0 = {(p['code'], p['type']) for p in row['baseline_preds'] if p.get('status') != 'added'}
        t1 = {(p['code'], p['type']) for p in row['update_preds'] if p.get('status') != 'removed'}
        if t0 != preds(R0, code) or t1 != preds(R1, code):
            bad += 1; ex = ex or f'{code}: predecessors differ from P6'
    chk(P, F, f"changed-logic rows: predecessors as in P6 ({len(cr['logic']['rows'])} rows, mismatches)",
        0, bad, note=ex)
    bad, ex = 0, ''
    for row in cr['durations']['rows']:
        code = row['activity_id']
        od0 = R0.acts[code]['od_h'] / R0.hpd(code)
        rd1 = R1.acts[code]['rd_h'] / R1.hpd(code)
        if abs(od0 - row['baseline_orig_days']) > 0.051 or abs(rd1 - row['remaining_days']) > 0.051:
            bad += 1; ex = ex or f"{code}: P6 {od0:.1f}/{rd1:.1f} d / tool {row['baseline_orig_days']}/{row['remaining_days']} d"
    chk(P, F, f"duration rows: original / remaining days as in P6 ({len(cr['durations']['rows'])} rows, mismatches)",
        0, bad, note=ex)

    # ── Critical Path Analyzer (update vs baseline) ──
    from p6_critpath.analysis import build_report as critpath
    sched = {'current': parse_file(later_path), 'baseline': parse_file(earlier_path)}
    use_picked_baseline(sched, earlier_path)
    cp = critpath(sched, 'update_baseline')
    F = 'Critical Path Analyzer'
    # the baseline P6 names for the update: the one inside the XML, else the picked one
    blp = getattr(R1, 'baseline', None) or {c: {'pl_start': a['pl_start'], 'pl_finish': a['pl_finish']}
                                              for c, a in R0.acts.items()}
    for role, R in (('baseline', R0), ('current', R1)):
        c = cp['census'][role]
        tf = lambda a: a['tf_h'] if a['tf_h'] is not None else a.get('tf_sign')
        floated = [a for a in R.acts.values() if a['type'] not in _MS and tf(a) is not None]
        if c['critical_source'] == 'float':
            chk(P, F, f'{role}: activities counted', len(floated), c['total_activities'])
            chk(P, F, f'{role}: critical (total float <= 0)', sum(1 for a in floated if tf(a) <= 1e-6),
                c['critical'])
        chk(P, F, f'{role}: data date', _day(R.project['data_date']), _long_to_day(c['data_date']))
        fins = [a for a in R.acts.values() if a['type'] == 'Finish Milestone' and _forecast(a)]
        gov = max(fins, key=_forecast) if fins else None
        if gov:
            chk(P, F, f'{role}: governing finish', _day(_forecast(gov)), _long_to_day(c['gov_finish']))
            code = next(k for k, v in R.acts.items() if v is gov)
            src = R0.acts if role == 'baseline' else blp
            chk(P, F, f'{role}: governing baseline finish', _day((src.get(code) or {}).get('pl_finish')),
                _long_to_day(c['gov_baseline_finish']))

    # ── Update Analysis (the update measured against its baseline) ──
    from p6_evm.metrics import compute
    from p6_evm.classify import auto_categories, build_wbs_classifier
    from p6_update.analysis import build_report_from_data as update_analysis
    import json
    from utils import resource_path
    data = parse_file(later_path)
    resolve_baseline(data, earlier_path, parse_file)
    cfg = json.load(open(resource_path('config.json')))
    cfg['categories'] = auto_categories(data)
    ua = update_analysis(data, compute(data, cfg, classifier=build_wbs_classifier(data)))
    k = ua['counts']
    F = 'Update Analysis'
    # over the construction activities (the agreed scope: Task Dependent work outside
    # Engineering / Design / Procurement — a classification, not a P6 figure)
    from p6_compare.report import _construction_codes
    scope = _construction_codes(data)
    work = [(code, a) for code, a in R1.acts.items() if a['type'] not in _MS and code in scope]
    chk(P, F, 'activities counted', len(work), k['total'])
    chk(P, F, 'actually completed', sum(1 for _, a in work if a['status'] == 'Completed'), k['actual_completed'])
    chk(P, F, 'actually in progress', sum(1 for _, a in work if a['status'] == 'In Progress'), k['actual_in_progress'])
    chk(P, F, 'actually not started', sum(1 for _, a in work if a['status'] == 'Not Started'), k['actual_not_started'])
    dd = R1.project['data_date']
    plc = pli = pln = 0
    for code, a in work:
        b = blp.get(code) or {}
        bs, bf = b.get('pl_start'), b.get('pl_finish')
        if bf and bf <= dd:
            plc += 1
        elif bs and bs <= dd:
            pli += 1
        elif bs:
            pln += 1
    chk(P, F, 'planned complete by the data date (baseline)', plc, k['planned_completed'])
    chk(P, F, 'planned in progress at the data date (baseline)', pli, k['planned_in_progress'])
    chk(P, F, 'planned not started at the data date (baseline)', pln, k['planned_not_started'])
    return ROWS
