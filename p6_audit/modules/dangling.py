"""Dangling Activities module (V2).

Primavera dangling definition, absorbing the old Open Ends check:
  * Dangling Start  = the start is not driven by an FS or SS predecessor
                      (includes activities with no predecessor at all).
  * Dangling Finish = the finish does not drive an FS or FF successor
                      (includes activities with no successor at all).
One merged row per activity. Score from Dangling % on the agreed curve.
"""
from p6_audit.findings import content_id, bump_severity
from p6_audit.scoring import linear_score, uniform_grade

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


def _fix(preds, succs, pred_drive, succ_drive):
    """A two-part predecessor + successor solution to the dangling, stated as a
    relationship-type change only (no activity IDs — those are in the
    Predecessor(s)/Successor(s) columns). Fix 1 uses FS/FS; Fix 2 uses the
    alternative valid types SS (start driver) / FF (finish driver).
    A suggestion only — never a schedule edit.
    """
    start_driven = any(e['type'] in ('FS', 'SS') for e in preds)
    finish_driven = any(e['type'] in ('FS', 'FF') for e in succs)

    # Predecessor part (drives the start)
    if not start_driven:
        pred_part = (f'Predecessor: change relationship to {pred_drive}' if preds
                     else f'Predecessor: add relationship ({pred_drive})')
    else:
        pred_part = 'Predecessor: OK'

    # Successor part (drives the finish)
    if not finish_driven:
        succ_part = (f'Successor: change relationship to {succ_drive}' if succs
                     else f'Successor: add relationship ({succ_drive})')
    else:
        succ_part = 'Successor: OK'

    return f'{pred_part}   |   {succ_part}'


def _ties(graph, edges):
    """Structured predecessor/successor ties (by activity CODE) for the Resolve & Correct layer.
    Additive — the display strings above are untouched."""
    out = []
    for e in edges:
        other = graph.activities.get(e['other'], {})
        out.append({
            'id':       other.get('id', '') or '',
            'name':     other.get('name', '') or '',
            'type':     e.get('type', 'FS'),
            'lag_days': float(e.get('lag_days', 0.0) or 0.0),
        })
    return out


def _side_fix(ties, recommended, alt):
    """A concrete, applyable fix for one dangling side, or a review marker.

    A side is dangling only when *no* tie on it drives (start: FS/SS · finish: FS/FF), so every
    existing tie is the wrong type and can be re-typed to a driver — a ``change``. When there is
    no tie at all there is nothing to re-type, so it is flagged ``review`` (Needs Planner Review);
    the tool never invents a link. ``recommended``/``alt`` are the two valid driver types for the
    side (Fix 1 / Fix 2)."""
    if not ties:
        return {'kind': 'review'}
    tgt = ties[0]
    return {
        'kind':             'change',
        'target_id':        tgt['id'],
        'target_name':      tgt['name'],
        'current_type':     tgt['type'],
        'current_lag_days': tgt['lag_days'],
        'recommended_type': recommended,
        'alt_type':         alt,
        'candidates':       ties,
    }


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
            issue, base = 'Dangling Start + Dangling Finish', 'High'
            both_n += 1
        elif start_dangling:
            issue, base = 'Dangling Start', 'Medium'
            start_n += 1
        else:
            issue, base = 'Dangling Finish', 'Medium'
            finish_n += 1

        severity = bump_severity(base) if act.get('is_critical') else base
        wbs_path = graph.wbs_path(oid)
        fix1 = _fix(preds, succs, 'FS', 'FS')
        fix2 = _fix(preds, succs, 'SS', 'FF')
        if fix2 == fix1:                     # no alternative beyond Fix 1
            fix2 = 'N/A'
        pred_ties = _ties(graph, preds)
        succ_ties = _ties(graph, succs)
        finding = {
            'finding_id':      content_id('DANGLING', act['id'], issue),
            'activity_id':     act['id'],
            'activity_name':   act.get('name', ''),
            'wbs_path':        wbs_path,
            'severity':        severity,
            'logic_issue':     issue,
            'predecessors':    _edge_str(graph, preds, 'No Predecessor'),
            'successors':      _edge_str(graph, succs, 'No Successor'),
            'suggested_fix':   fix1,
            'suggested_fix_2': fix2,
            'is_critical':     bool(act.get('is_critical')),
            # ── Resolve & Correct enrichment (additive; detection unchanged) ──
            'start_dangling':  start_dangling,
            'finish_dangling': finish_dangling,
            'pred_ties':       pred_ties,
            'succ_ties':       succ_ties,
        }
        # A concrete, applyable fix per dangling side (start driven by a predecessor: FS/SS;
        # finish driven by a successor: FS/FF), or a Needs-Planner-Review marker when no link exists.
        if start_dangling:
            finding['start_fix'] = _side_fix(pred_ties, 'FS', 'SS')
        if finish_dangling:
            finding['finish_fix'] = _side_fix(succ_ties, 'FS', 'FF')
        findings.append(finding)

    total = len(real)
    dangling = len(findings)
    pct = round(100.0 * dangling / total, 1) if total else 0.0

    order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
    findings.sort(key=lambda f: (order.get(f['severity'], 9), f['activity_id']))

    dd = getattr(graph, 'data_date', None)
    data_date_str = dd.strftime('%d-%b-%Y') if hasattr(dd, 'strftime') else ''

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
            'data_date':        data_date_str,
        },
        'pct':   pct,
        # Unified Schedule Health model: Score = 100 − defect%, uniform legend
        # (was a band curve; aligned with every other sub-feature on 2026-08-18).
        'score': linear_score(pct),
        'grade': uniform_grade(linear_score(pct)),
        'findings': findings,
        'wbs_summary': [],
    }
