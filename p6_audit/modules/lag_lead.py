"""Lag & Lead Audit module — a DCMA-style schedule-quality report on relationship lags.

Lists every relationship in the schedule that carries a lag or a lead (negative lag),
measured against the two DCMA 14-Point lines: lags should be no more than 5% of all
relationships, and leads should be zero. It flags long lags (over a threshold, default
14 working days) and the links sitting on the critical / near-critical path — the ones
that actually move the finish date.

Each row is anchored on the successor activity (the one that waits): the audited lag is
shown as its predecessor relationship, and the successor's own onward link is carried as
context — the same activity-centred shape as the Consultant Review logic table. The
planner adds a Justification per row; those are held server-side per project (merged in
by the caller from project settings) and print into the PDF and Excel.

Advisory only — it diagnoses and documents, it never edits schedule logic.
"""
from collections import defaultdict

from p6_audit.scoring import module_score, grade_for_pct

MODULE = 'lag_lead'
NAME = 'Lag & Lead'

DCMA_LAG_LINE = 5.0          # DCMA: relationships with a lag should be <= 5%
_SEV_OF = {'Critical': 'Critical', 'Near-Critical': 'High', '': 'Medium'}


def _rel_label(rel_type, lag_wd):
    """'FS' when no lag, else 'FS+7' / 'FS-3' (the minus comes from the number)."""
    if not lag_wd:
        return rel_type
    return f"{rel_type}{'+' if lag_wd > 0 else ''}{lag_wd}"


def _wbs_area(wbs_path):
    """The top WBS area for the distribution: root > AREA > ... → AREA."""
    parts = [p.strip() for p in (wbs_path or '').split('>') if p.strip()]
    if len(parts) >= 2:
        return parts[1]
    if parts:
        return parts[0]
    return '(no WBS)'


def _criticality(pred, succ, near_days):
    """A lagged link is Critical when either endpoint is critical (float <= 0), and
    Near-Critical when the tighter endpoint's total float is within near_days — the same
    yardstick the Out of Sequence and Float modules use."""
    tfs = [t for t in (pred.get('total_float_days'), succ.get('total_float_days')) if t is not None]
    if pred.get('is_critical') or succ.get('is_critical') or (tfs and min(tfs) <= 0):
        return 'Critical'
    if tfs and min(tfs) <= near_days:
        return 'Near-Critical'
    return ''


def _context_succ(graph, succ_oid):
    """(code, name, rel-label) of the anchor activity's first real onward link — context
    only; that link, if it carries a lag, has its own row anchored on its own successor."""
    for link in graph.succs_of(succ_oid):
        nxt = graph.activities.get(link['other'])
        if not nxt:
            continue
        lag = int(round(link.get('lag_days') or 0))
        return nxt.get('id', ''), nxt.get('name', ''), _rel_label(link.get('type', 'FS'), lag)
    return '', '', ''


def _rank(f):
    """Worst-first: leads, then long-on-critical, long, critical, near-critical, the rest —
    each tier by descending lag magnitude."""
    mag = -abs(f['lag_days'])
    if f['is_lead']:
        return (0, mag)
    if f['is_long'] and f['criticality'] == 'Critical':
        return (1, mag)
    if f['is_long']:
        return (2, mag)
    if f['criticality'] == 'Critical':
        return (3, mag)
    if f['criticality'] == 'Near-Critical':
        return (4, mag)
    return (5, mag)


def _verdict_reason(lagged_pct, leads):
    bits = []
    if lagged_pct > DCMA_LAG_LINE:
        bits.append(f'{lagged_pct}% of links carry a lag (over the 5% line)')
    if leads:
        bits.append(f'{leads} lead{"s" if leads != 1 else ""} present (should be zero)')
    if not bits:
        return 'Within both DCMA lines — lags under 5% of links and no leads.'
    return ' and '.join(bits) + '.'


def _conclusion(lagged, lagged_pct, leads, longs, crit_c, long_days):
    if lagged == 0:
        return ('No lags or leads were found — every relationship drives directly, with no '
                'waiting time built into the network logic.')
    within = 'within' if lagged_pct <= DCMA_LAG_LINE else 'above'
    parts = [f'The schedule carries {lagged} lag{"s" if lagged != 1 else ""} '
             f'({lagged_pct}% of all relationships), {within} the 5% DCMA guideline. ']
    if leads:
        parts.append(f'{leads} of these {"is a lead" if leads == 1 else "are leads"} '
                     '(negative lag), which DCMA says should be zero — a lead lets work start '
                     'before its predecessor finishes and can pull the finish date in on paper. ')
    if longs:
        parts.append(f'{longs} lag{"s" if longs != 1 else ""} exceed {long_days} working days '
                     'and should carry a documented reason. ')
    if crit_c:
        verb = 'lies' if crit_c == 1 else 'lie'
        parts.append(f'{crit_c} {verb} on the critical path, directly affecting completion. ')
    else:
        parts.append('None of the flagged links sit on the critical path. ')
    parts.append('Add a justification against each flagged link so the report reads as a '
                 'defensible document.')
    return ''.join(parts)


def apply_justifications(lag_module, justifications):
    """Merge the planner's saved justifications (kept per project, keyed by rel_key) onto the
    register rows. Called by the server after run — the module itself stays stateless."""
    if not lag_module:
        return lag_module
    j = justifications or {}
    for f in lag_module.get('findings', []):
        f['justification'] = j.get(f.get('rel_key', ''), '')
    return lag_module


def run_lag_lead(graph, config):
    audit_cfg = config.get('audit', {})
    near_days = audit_cfg.get('near_critical_days', 10)
    long_days = audit_cfg.get('long_lag_days', 14)
    dd = getattr(graph, 'data_date', None)
    data_date_str = dd.strftime('%d-%b-%Y') if hasattr(dd, 'strftime') else ''

    total_rels = 0
    findings = []
    for pred_oid, pred in graph.activities.items():
        for link in graph.succs_of(pred_oid):
            succ = graph.activities.get(link['other'])
            if succ is None:
                continue
            total_rels += 1
            lag_wd = int(round(link.get('lag_days') or 0))
            if lag_wd == 0:
                continue
            rel_type = link.get('type', 'FS')
            crit = _criticality(pred, succ, near_days)
            is_lead = lag_wd < 0
            is_long = abs(lag_wd) > long_days
            c_code, c_name, c_rel = _context_succ(graph, link['other'])
            findings.append({
                'activity_id':   succ.get('id', ''),
                'activity_name': succ.get('name', ''),
                'wbs_path':      succ.get('wbs_path', '') or graph.wbs_path(link['other']),
                'pred_id':       pred.get('id', ''),
                'pred_name':     pred.get('name', ''),
                'pred_rel':      _rel_label(rel_type, lag_wd),
                'succ_id':       c_code,
                'succ_name':     c_name,
                'succ_rel':      c_rel,
                'lag_days':      lag_wd,
                'rel_type':      rel_type,
                'is_lead':       is_lead,
                'is_long':       is_long,
                'criticality':   crit,
                'severity':      _SEV_OF.get(crit, 'Medium') if (is_lead or is_long) else 'Low',
                'rel_key':       f"{pred.get('id', '')}|{succ.get('id', '')}|{rel_type}",
                'justification': '',
            })

    lagged = len(findings)
    lagged_pct = round(100.0 * lagged / total_rels, 1) if total_rels else 0.0
    leads = sum(1 for f in findings if f['is_lead'])
    longs = sum(1 for f in findings if f['is_long'])
    positives = sum(1 for f in findings if f['lag_days'] > 0)
    crit_c = sum(1 for f in findings if f['criticality'] == 'Critical')
    near_c = sum(1 for f in findings if f['criticality'] == 'Near-Critical')

    by_type = []
    for t in ('FS', 'SS', 'FF', 'SF'):
        c = sum(1 for f in findings if f['rel_type'] == t)
        if c:
            by_type.append({'type': t, 'count': c,
                            'pct': round(100.0 * c / lagged, 1) if lagged else 0.0})

    area_count = defaultdict(int)
    for f in findings:
        area_count[_wbs_area(f['wbs_path'])] += 1
    wbs_summary = [{'wbs': a, 'lagged': c, 'pct': round(100.0 * c / lagged, 1) if lagged else 0.0}
                   for a, c in area_count.items()]
    wbs_summary.sort(key=lambda r: (-r['lagged'], r['wbs']))

    verdict = 'Needs attention' if (lagged_pct > DCMA_LAG_LINE or leads > 0) else 'Pass'
    findings.sort(key=_rank)

    return {
        'module': MODULE,
        'name': NAME,
        'pct': lagged_pct,
        'score': module_score(lagged_pct),
        'grade': grade_for_pct(lagged_pct),
        'kpis': {
            'total_relationships':  total_rels,
            'lagged_count':         lagged,
            'lagged_pct':           lagged_pct,
            'dcma_lag_line':        DCMA_LAG_LINE,
            'leads_count':          leads,
            'positive_count':       positives,
            'long_count':           longs,
            'long_threshold_days':  long_days,
            'critical_count':       crit_c,
            'near_critical_count':  near_c,
            'near_critical_days':   near_days,
            'by_type':              by_type,
            'data_date':            data_date_str,
            'verdict':              verdict,
            'verdict_reason':       _verdict_reason(lagged_pct, leads),
            'executive_conclusion': _conclusion(lagged, lagged_pct, leads, longs, crit_c, long_days),
        },
        'wbs_summary': wbs_summary,
        'findings': findings,
    }
