"""Dangling Activities module (V2).

Primavera dangling definition, absorbing the old Open Ends check:
  * Dangling Start  = the start is not driven by an FS or SS predecessor
                      (includes activities with no predecessor at all).
  * Dangling Finish = the finish does not drive an FS or FF successor
                      (includes activities with no successor at all).
One merged row per activity. Score from Dangling % on the agreed curve.
"""
from p6_audit.findings import content_id, bump_severity
from p6_audit.scoring import module_score, grade_for_pct

MODULE = 'dangling'
NAME = 'Dangling Activities'


def _edge_str(graph, edges, empty):
    if not edges:
        return empty
    parts = []
    for e in edges:
        other = graph.activities.get(e['other'], {})
        parts.append(f"{other.get('id', '?')} - {other.get('name', '')} ({e.get('type', 'FS')})")
    return '; '.join(parts)


def _wbs_leaf(wbs_path):
    if not wbs_path:
        return 'this WBS package'
    return wbs_path.split('>')[-1].strip() or 'this WBS package'


def _first_other(graph, edges):
    for e in edges:
        o = graph.activities.get(e['other'], {})
        return o.get('id', ''), e.get('type', 'FS')
    return None, None


def _reason(graph, issue, preds, succs, wbs_path):
    """Deterministic engineering reasoning → (suggested_fix, recommendation).

    Names the specific relationship to review from the activity's existing
    predecessors/successors and its WBS position — a suggestion only, never a
    schedule edit.
    """
    leaf = _wbs_leaf(wbs_path)
    if issue == 'Dangling Start':
        if preds:  # has predecessors, but none tie the start (wrong type)
            pid, ptype = _first_other(graph, preds)
            fix = f'Review predecessor {pid} (currently {ptype}) — a Finish-to-Start driver is expected.'
        else:
            fix = f'Add the missing Finish-to-Start predecessor from the preceding activity in "{leaf}".'
        rec = 'Verify the predecessor against the construction sequence so the start is driven by real logic.'
    elif issue == 'Dangling Finish':
        if succs:
            sid, stype = _first_other(graph, succs)
            fix = f'Review successor {sid} (currently {stype}) — a Finish-to-Start driver is expected.'
        else:
            fix = f'Add the missing Finish-to-Start successor to the next activity in "{leaf}".'
        rec = 'Verify the successor so completion drives downstream work and the float stays realistic.'
    else:  # Dangling Start + Finish
        fix = f'Add a Finish-to-Start predecessor and successor to embed this activity in the "{leaf}" sequence.'
        rec = 'Fully connect this isolated activity to its construction sequence; open ends distort the critical path and float.'
    return fix, rec


def run_dangling(graph, config):
    findings = []
    real = [(oid, a) for oid, a in graph.activities.items() if graph.is_real_activity(oid)]
    start_n = finish_n = both_n = 0

    for oid, act in real:
        preds = graph.preds_of(oid)
        succs = graph.succs_of(oid)
        start_dangling = not any(e['type'] in ('FS', 'SS') for e in preds)
        finish_dangling = not any(e['type'] in ('FS', 'FF') for e in succs)
        if not (start_dangling or finish_dangling):
            continue

        if start_dangling and finish_dangling:
            issue, base = 'Dangling Start + Finish', 'High'
            both_n += 1
        elif start_dangling:
            issue, base = 'Dangling Start', 'Medium'
            start_n += 1
        else:
            issue, base = 'Dangling Finish', 'Medium'
            finish_n += 1

        severity = bump_severity(base) if act.get('is_critical') else base
        wbs_path = graph.wbs_path(oid)
        fix, recommendation = _reason(graph, issue, preds, succs, wbs_path)
        findings.append({
            'finding_id':     content_id('DANGLING', act['id'], issue),
            'activity_id':    act['id'],
            'activity_name':  act.get('name', ''),
            'wbs_path':       wbs_path,
            'severity':       severity,
            'logic_issue':    issue,
            'predecessors':   _edge_str(graph, preds, 'No Predecessor'),
            'successors':     _edge_str(graph, succs, 'No Successor'),
            'suggested_fix':  fix,
            'recommendation': recommendation,
            'is_critical':    bool(act.get('is_critical')),
        })

    total = len(real)
    dangling = len(findings)
    pct = round(100.0 * dangling / total, 1) if total else 0.0

    order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
    findings.sort(key=lambda f: (order.get(f['severity'], 9), f['activity_id']))

    return {
        'module': MODULE,
        'name': NAME,
        'kpis': {
            'total_activities': total,
            'total_dangling':   dangling,
            'start_dangling':   start_n,
            'finish_dangling':  finish_n,
            'both_dangling':    both_n,
            'dangling_pct':     pct,
        },
        'pct':   pct,
        'score': module_score(pct),
        'grade': grade_for_pct(pct),
        'findings': findings,
        'wbs_summary': [],
    }
