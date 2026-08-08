"""Float Analysis module (V2).

One row per activity that is over the float threshold OR has negative float.
Severity: negative float -> Critical; > 3x threshold -> High; else Medium.
Score from Float % (activities above threshold / total activities) on the curve.
"""
from collections import defaultdict
from p6_audit.findings import content_id
from p6_audit.scoring import module_score, grade_for_pct
from p6_audit.modules.float_management import float_management

MODULE = 'float'
NAME = 'Float Analysis'


def run_float(graph, config):
    threshold = config.get('audit', {}).get('float_threshold_days', 44)
    real = [(oid, a) for oid, a in graph.activities.items() if graph.is_real_activity(oid)]
    total = len(real)

    with_float = [(oid, a) for oid, a in real if a.get('total_float_days') is not None]
    floats = [a['total_float_days'] for _, a in with_float]

    findings = []
    above = 0
    for oid, act in with_float:
        tf = act['total_float_days']
        over = tf > threshold
        negative = tf < 0
        if not (over or negative):
            continue
        if over:
            above += 1

        leaf = (graph.wbs_path(oid) or '').split('>')[-1].strip() or 'this WBS package'
        if negative:
            severity, status = 'Critical', 'Negative Float'
            impact = None
            reason = 'Negative float — behind the finish need date'
            recommendation = 'Investigate the driving logic or delay; the finish milestone is threatened.'
        else:
            impact = round(tf / threshold, 1) if threshold else None
            if impact is not None and impact > 3:
                severity = 'High'
                reason = f'Severely excessive float ({impact}× threshold)'
                recommendation = f'Assign a driving Finish-to-Start successor — {impact}× float points to missing logic in "{leaf}".'
            else:
                severity = 'Medium'
                reason = 'Excessive float above threshold'
                recommendation = 'Review whether a Finish-to-Start successor is missing so the activity is properly driven.'
            status = 'Excessive Float'

        findings.append({
            'finding_id':       content_id('FLOAT', act['id'], status),
            'activity_id':      act['id'],
            'activity_name':    act.get('name', ''),
            'wbs_path':         graph.wbs_path(oid),
            'total_float_days': tf,
            'threshold':        threshold,
            'impact':           impact,
            'severity':         severity,
            'status':           status,
            'reason':           reason,
            'recommendation':   recommendation,
        })

    float_pct = round(100.0 * above / total, 1) if total else 0.0

    # WBS summary — where the excessive float concentrates (over-threshold only)
    wbs_total = defaultdict(int)
    for oid, a in real:
        wbs_total[graph.wbs_path(oid) or '(no WBS)'] += 1
    wbs_high = defaultdict(int)
    for f in findings:
        if f['status'] == 'Excessive Float':
            wbs_high[f['wbs_path'] or '(no WBS)'] += 1
    wbs_summary = []
    for wbs, high in wbs_high.items():
        tot = wbs_total.get(wbs, high)
        pct = round(100.0 * high / tot, 1) if tot else 0.0
        wbs_summary.append({'wbs': wbs, 'activities': tot, 'high': high,
                            'pct': pct, 'grade': grade_for_pct(pct)})
    wbs_summary.sort(key=lambda r: (-r['high'], -r['pct']))

    order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
    findings.sort(key=lambda f: (order.get(f['severity'], 9), -(f['total_float_days'] or 0)))

    return {
        'module': MODULE,
        'name': NAME,
        'kpis': {
            'total_activities': total,
            'above_threshold':  above,
            'float_pct':        float_pct,
            'threshold':        threshold,
            'max_float':        round(max(floats), 1) if floats else 0,
            'avg_float':        round(sum(floats) / len(floats), 1) if floats else 0,
        },
        'pct':   float_pct,
        'score': module_score(float_pct),
        'grade': grade_for_pct(float_pct),
        'findings': findings,
        'wbs_summary': wbs_summary,
        # V2 management-dashboard layer (calculation engine above is unchanged)
        'mgmt': float_management(graph, config),
    }
