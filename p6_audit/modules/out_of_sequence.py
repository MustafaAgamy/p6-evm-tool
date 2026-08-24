"""Out of Sequence module (V2) — a Consultant Review Report.

Flags activities whose ACTUAL progress breaks their predecessor logic
(the P6 out-of-sequence condition, F9), across Finish-to-Start,
Start-to-Start and Finish-to-Finish relationships. Detection compares
each successor's actual Start/Finish against its predecessor's actual dates.

The module is a management report, not an activity dump. It answers:
  - how many out-of-sequence activities exist (and what % of the schedule),
  - which WBS packages are affected,
  - the root cause of each condition and what the planner should review,
  - whether the Critical Path / completion date is affected.

It diagnoses and recommends — it never edits schedule logic.
"""
from collections import defaultdict

from p6_evm.calendars import signed_working_days
from p6_evm.classify import classify_branch_names
from p6_audit.findings import content_id
from p6_audit.scoring import module_score, grade_for_pct

MODULE = 'out_of_sequence'
NAME = 'Out of Sequence'


# ── Detection ──────────────────────────────────────────────────────────────

def _is_oos(rel_type, succ, pred):
    """True when the successor progressed ahead of what the relationship allows."""
    s_as, s_af = succ.get('actual_start'), succ.get('actual_finish')
    p_as, p_af = pred.get('actual_start'), pred.get('actual_finish')
    if rel_type == 'FS':   # must not start until predecessor finishes
        return bool(s_as) and (p_af is None or p_af > s_as)
    if rel_type == 'SS':   # must not start until predecessor starts
        return bool(s_as) and (p_as is None or p_as > s_as)
    if rel_type == 'FF':   # must not finish until predecessor finishes
        return bool(s_af) and (p_af is None or p_af > s_af)
    if rel_type == 'SF':   # must not finish until predecessor starts
        return bool(s_af) and (p_as is None or p_as > s_af)
    return False


_TYPE_PRIORITY = {'FS': 0, 'SS': 1, 'FF': 2, 'SF': 3}


def _incomplete(act):
    """Predecessor still unfinished = it has no actual finish. P6 reports out-of-sequence
    progress only when the predecessor a successor jumped ahead of is genuinely
    unfinished — a past overlap between two now-complete activities is finished work,
    not out of sequence. (Using actual-finish, not percent complete, is deliberate:
    PercentComplete is 0–100 in XML but 0–1 in XER, so a % threshold isn't scale-safe.)"""
    return act.get('actual_finish') is None


def _first_offending_pred(graph, oid, act):
    """The predecessor link this activity violated (FS preferred), or None.
    Only predecessors that are still incomplete count, to match P6."""
    offenders = []
    for link in graph.preds_of(oid):
        # Task→Task logic only: out-of-sequence is jumping ahead of unfinished WORK, so a
        # zero-duration milestone (or LOE) predecessor is not counted — matches P6.
        if not graph.is_real_activity(link['other']):
            continue
        p = graph.activities.get(link['other'])
        if not _incomplete(p):
            continue
        t = link.get('type', 'FS')
        if _is_oos(t, act, p):
            offenders.append((link, p, t))
    if not offenders:
        return None
    offenders.sort(key=lambda o: _TYPE_PRIORITY.get(o[2], 9))
    return offenders[0]


def _working_days(graph, act, d1, d2):
    """Working-day gap on the activity's calendar (falls back to calendar days)."""
    if not d1 or not d2:
        return 0
    cal = graph.calendars.get(act.get('calendar_id'))
    if cal is not None:
        try:
            return abs(int(round(signed_working_days(cal, d1, d2))))
        except Exception:
            pass
    return abs((d2 - d1).days)


# ── Advisory suggestions (never applied automatically) ─────────────────────

def _lag_suffix(lag):
    """'(+3d)' / '(−2d)' / '' for a zero lag."""
    lag = round(lag or 0.0, 1)
    if lag == 0:
        return ''
    return f"({'+' if lag > 0 else '−'}{abs(lag):g}d)"


def _rel_lag_label(rel, lag):
    """'SS(+3d)' / 'FS' — a compact relationship+lag label."""
    suf = _lag_suffix(lag)
    return f"{rel}{suf}" if suf else rel


def _resolution(action, applicable, action_text, *, new_type=None, new_lag_days=None,
                new_pred_id=None, sug_pred_id='', sug_pred_name='', sug_pred_rel='',
                sug_pred_lag=None, sug_succ_id='', sug_succ_name='No change'):
    """A machine-actionable proposed correction the planner can accept, edit, and apply.

    ``action`` ∈ {'change', 'remove', 'replace', 'data'}. 'data' is not applicable
    (a wrong actual date — no relationship edit clears it, so the finding stays Open).
    All fields are advisory defaults; the planner may edit type/lag/predecessor before
    applying, and re-validation (the same detection engine) is the final arbiter.
    """
    return {
        'action': action, 'applicable': applicable, 'action_text': action_text,
        'new_type': new_type, 'new_lag_days': new_lag_days, 'new_pred_id': new_pred_id,
        'sug_pred_id': sug_pred_id, 'sug_pred_name': sug_pred_name,
        'sug_pred_rel': sug_pred_rel, 'sug_pred_lag': sug_pred_lag,
        'sug_succ_id': sug_succ_id, 'sug_succ_name': sug_succ_name,
    }


def _suggest(graph, rel_type, succ, pred):
    """Advisory diagnosis + the two legacy fix labels (kept for backward compatibility
    and the PDF/Excel), PLUS a structured, machine-actionable ``resolution`` the planner
    can accept and apply (Resolve & Correct). Each fix label is (text, kind); kind is
    'change' / 'remove' / 'same' / 'na'. Nothing is applied automatically.
    """
    s_as, s_af = succ.get('actual_start'), succ.get('actual_finish')
    p_as, p_af = pred.get('actual_start'), pred.get('actual_finish')
    pred_id, pred_name = pred.get('id', ''), pred.get('name', '')
    succ_id = succ.get('id', '')
    pred_label = f"{pred_id} · {pred_name}"
    NA = ('N/A', 'na')

    # Defaults (SF / unknown). Legacy fix labels unchanged (PDF/Excel read them); the
    # new actionable resolution recommends removing the tie reality contradicts, editable.
    root = 'Schedule logic requires review following execution changes.'
    comment = 'Planning Engineer review required before modifying schedule logic.'
    pred_fix1, pred_fix2 = ('Planner to review', 'change'), NA
    resolution = _resolution(
        'remove', True, f"Remove link {pred_id} → {succ_id} ({rel_type})",
        sug_pred_id=pred_id, sug_pred_name=pred_name, sug_pred_rel='REMOVE')

    if s_af is not None and p_as is not None and s_af < p_as:
        # Successor fully executed before the predecessor even began → link contradicts reality.
        pred_fix1, pred_fix2 = ('Remove Relationship', 'remove'), ('Planner to review', 'change')
        root = 'Relationship logic may not represent actual execution sequence.'
        comment = 'Review predecessor-successor relationship.'
        resolution = _resolution(
            'remove', True, f"Remove link {pred_id} → {succ_id} ({rel_type})",
            sug_pred_id=pred_id, sug_pred_name=pred_name, sug_pred_rel='REMOVE')
    elif p_as is None:
        # Predecessor shows no actual start yet the successor has progressed → data inconsistency.
        pred_fix1, pred_fix2 = ('Planner to review', 'change'), NA
        root = 'Inconsistent Actual Dates.'
        comment = 'Validate Actual Dates.'
        resolution = _resolution(
            'data', False, 'Review actual dates in P6 — no logic fix applies',
            sug_pred_id='', sug_pred_name='Actual dates inconsistent', sug_pred_rel='DATA',
            sug_succ_name='—')
    elif rel_type == 'FS' and s_as is not None and s_as >= p_as:
        # Real execution overlapped — model it as Start-to-Start with lag, or Finish-to-Finish.
        lag = _working_days(graph, succ, p_as, s_as)
        pred_fix1, pred_fix2 = (f'SS({lag}) - {pred_label}', 'change'), (f'FF - {pred_label}', 'change')
        root = 'Activity started before predecessor completion.'
        comment = 'Review construction sequence.'
        resolution = _resolution(
            'change', True, f"Change {pred_id} → {succ_id} from FS to {_rel_lag_label('SS', lag)}",
            new_type='SS', new_lag_days=lag, new_pred_id=pred_id,
            sug_pred_id=pred_id, sug_pred_name=pred_name, sug_pred_rel='SS', sug_pred_lag=lag)
    elif rel_type == 'FS':
        # Successor started before the predecessor started, on an FS link.
        pred_fix1, pred_fix2 = ('Planner to review', 'change'), ('Remove Relationship', 'remove')
        root = 'Relationship logic may not represent actual execution sequence.'
        comment = 'Review predecessor-successor relationship.'
        resolution = _resolution(
            'remove', True, f"Remove link {pred_id} → {succ_id} (FS)",
            sug_pred_id=pred_id, sug_pred_name=pred_name, sug_pred_rel='REMOVE')
    elif rel_type == 'SS':
        pred_fix1, pred_fix2 = ('Planner to review', 'change'), ('Remove Relationship', 'remove')
        root = 'Relationship logic may not represent actual execution sequence.'
        comment = 'Review predecessor-successor relationship.'
        resolution = _resolution(
            'remove', True, f"Remove link {pred_id} → {succ_id} (SS)",
            sug_pred_id=pred_id, sug_pred_name=pred_name, sug_pred_rel='REMOVE')
    elif rel_type in ('FF', 'SF'):
        pred_fix1, pred_fix2 = ('Planner to review', 'change'), NA
        root = 'Relationship logic may not represent actual execution sequence.'
        comment = 'Review predecessor-successor relationship.'
        resolution = _resolution(
            'remove', True, f"Remove link {pred_id} → {succ_id} ({rel_type})",
            sug_pred_id=pred_id, sug_pred_name=pred_name, sug_pred_rel='REMOVE')

    # The out-of-sequence violation is on the predecessor side; the successor tie
    # is context and normally needs no change.
    succ_fix1, succ_fix2 = ('No Change', 'same'), NA
    return {
        'pred_fix1': pred_fix1[0], 'pred_fix1_kind': pred_fix1[1],
        'pred_fix2': pred_fix2[0], 'pred_fix2_kind': pred_fix2[1],
        'succ_fix1': succ_fix1[0], 'succ_fix1_kind': succ_fix1[1],
        'succ_fix2': succ_fix2[0], 'succ_fix2_kind': succ_fix2[1],
        'root_cause': root, 'planning_review_comment': comment,
        'resolution': resolution,
    }


def _first_successor(graph, oid):
    """(relationship, succ_id, succ_name, lag_days) of the activity's first real
    successor, for context. Empty strings / 0 when there is no successor."""
    for link in graph.succs_of(oid):
        s = graph.activities.get(link['other'])
        if s:
            return (link.get('type', 'FS'), s.get('id', ''), s.get('name', ''),
                    link.get('lag_days', 0.0) or 0.0)
    return '', '', '', 0.0


def _category_of(graph, oid):
    """Main WBS discipline (Construction / Engineering / Design / Procurement) for the
    distribution — decided by the top-most meaningful WBS phase, so sub-phases roll up
    (Design Phase I + Phase II Design → Design), matching the EVM category view."""
    a = graph.activities.get(oid, {})
    parts = [p.strip() for p in (a.get('wbs_path') or '').split('>') if p.strip()]
    if not parts:
        return '(uncategorised)'
    return classify_branch_names(parts[::-1])   # split is root→leaf; helper wants leaf→root


def _criticality(act, near_days):
    if act.get('is_critical'):
        return 'Critical'
    tf = act.get('total_float_days')
    if tf is not None and 0 < tf <= near_days:
        return 'Near-Critical'
    return ''


_SEV_OF = {'Critical': 'Critical', 'Near-Critical': 'High', '': 'Medium'}


# ── Executive conclusion (auto management summary) ──────────────────────────

def _conclusion(oos_count, distribution, critical_oos, near_oos):
    if oos_count == 0:
        return ('No out-of-sequence conditions were detected — schedule progress is '
                'consistent with the network logic.')
    by_count = sorted(distribution, key=lambda r: (-r['oos'], -r['pct']))
    top = by_count[0]
    leaf = (top['wbs'] or '').split('>')[-1].strip() or 'one WBS package'
    share = round(100.0 * top['oos'] / oos_count) if oos_count else 0
    parts = [f"Out-of-sequence conditions are concentrated in the {leaf} package "
             f"({top['oos']} of {oos_count} findings, {share}%)"]
    if len(by_count) > 1 and by_count[1]['oos'] > 0:
        leaf2 = (by_count[1]['wbs'] or '').split('>')[-1].strip()
        if leaf2:
            parts.append(f", with {leaf2} the next most affected")
    parts.append('. ')
    if critical_oos > 0:
        verb = 'lies' if critical_oos == 1 else 'lie'
        parts.append(f"{critical_oos} out-of-sequence "
                     f"activit{'y' if critical_oos == 1 else 'ies'} {verb} on the Critical Path, "
                     f"giving a direct impact on the completion date. ")
    elif near_oos > 0:
        parts.append(f"{near_oos} out-of-sequence "
                     f"activit{'y is' if near_oos == 1 else 'ies are'} near-critical, "
                     f"a potential impact on the completion date. ")
    else:
        parts.append("None of the out-of-sequence activities are on the Critical Path, "
                     "so no completion-date impact is detected. ")
    parts.append(f"The {leaf} sequence should be reviewed and the flagged relationships "
                 "validated against actual execution, to restore schedule reliability.")
    return ''.join(parts)


# ── Entry point ────────────────────────────────────────────────────────────

def run_out_of_sequence(graph, config):
    near_days = config.get('audit', {}).get('near_critical_days', 10)
    dd = getattr(graph, 'data_date', None)
    data_date_str = dd.strftime('%d-%b-%Y') if hasattr(dd, 'strftime') else ''
    real = [(oid, a) for oid, a in graph.activities.items() if graph.is_real_activity(oid)]
    total = len(real)

    findings = []
    for oid, act in real:
        s_as, s_af = act.get('actual_start'), act.get('actual_finish')
        if not s_as and not s_af:
            continue  # no actual progress → cannot be out of sequence
        offending = _first_offending_pred(graph, oid, act)
        if not offending:
            continue
        _link, pred, rel_type = offending
        sug = _suggest(graph, rel_type, act, pred)
        succ_rel, succ_id, succ_name, succ_lag = _first_successor(graph, oid)
        crit = _criticality(act, near_days)
        findings.append({
            'finding_id':                 content_id('OOS', act.get('id'), pred.get('id')),
            'activity_id':                act.get('id', ''),
            'activity_name':              act.get('name', ''),
            'wbs_path':                   graph.wbs_path(oid),
            'category':                   _category_of(graph, oid),
            'current_pred_rel':           rel_type,
            'current_pred_activity':      f"{pred.get('id', '')} · {pred.get('name', '')}",
            # Split IDs + lag (Resolve & Correct — one clean column each, no overlap):
            'pred_id':                    pred.get('id', ''),
            'pred_name':                  pred.get('name', ''),
            'current_pred_lag':           _link.get('lag_days', 0.0) or 0.0,
            'current_succ_rel':           succ_rel,
            'current_succ_activity':      (f"{succ_id} · {succ_name}" if succ_id else 'No successor'),
            'succ_id':                    succ_id,
            'succ_name':                  succ_name,
            'current_succ_lag':           succ_lag,
            'suggested_predecessor':      sug['pred_fix1'], 'suggested_predecessor_kind': sug['pred_fix1_kind'],
            'suggested_successor':        sug['succ_fix1'], 'suggested_successor_kind': sug['succ_fix1_kind'],
            'root_cause':                 sug['root_cause'],
            'planning_review_comment':    sug['planning_review_comment'],
            'criticality':                crit,
            'severity':                   _SEV_OF.get(crit, 'Medium'),
            # Machine-actionable proposed correction (accept / edit / apply):
            'resolution':                 sug['resolution'],
        })

    oos_count = len(findings)
    oos_pct = round(100.0 * oos_count / total, 1) if total else 0.0
    critical_oos = sum(1 for f in findings if f['criticality'] == 'Critical')
    near_oos = sum(1 for f in findings if f['criticality'] == 'Near-Critical')
    # % of ALL activities (same denominator as Out-of-Sequence %), so the tiles are
    # directly comparable — the raw counts carry the severity.
    critical_pct = round(100.0 * critical_oos / total, 1) if total else 0.0
    near_pct = round(100.0 * near_oos / total, 1) if total else 0.0

    # Distribution by top-level WBS category (Construction / Engineering / Design / …) —
    # the same phases as the EVM view: how many out-of-sequence activities per category.
    cat_total = defaultdict(int)
    for oid, _a in real:
        cat_total[_category_of(graph, oid)] += 1
    cat_oos, cat_crit, cat_near = defaultdict(int), defaultdict(int), defaultdict(int)
    for f in findings:
        c = f.get('category') or '(uncategorised)'
        cat_oos[c] += 1
        if f['criticality'] == 'Critical':
            cat_crit[c] += 1
        elif f['criticality'] == 'Near-Critical':
            cat_near[c] += 1
    distribution = []
    for c, tot in cat_total.items():
        k = cat_oos.get(c, 0)
        pct = round(100.0 * k / tot, 1) if tot else 0.0
        distribution.append({'wbs': c, 'activities': tot, 'oos': k, 'pct': pct,
                             'critical_oos': cat_crit.get(c, 0), 'near_critical_oos': cat_near.get(c, 0),
                             'grade': grade_for_pct(pct)})
    # Worst-first by out-of-sequence count, then percentage; affected categories on top.
    distribution.sort(key=lambda r: (-r['oos'], -r['pct']))
    affected = sum(1 for r in distribution if r['oos'] > 0)

    critical_path_impact = 'Yes' if critical_oos > 0 else 'No'
    if critical_oos > 0:
        completion_impact = 'Direct Impact'
    elif near_oos > 0:
        completion_impact = 'Potential Impact'
    else:
        completion_impact = 'No Impact'

    order = {'Critical': 0, 'Near-Critical': 1, '': 2}
    findings.sort(key=lambda f: (order.get(f['criticality'], 2), f['activity_id']))

    return {
        'module': MODULE,
        'name': NAME,
        'pct': oos_pct,
        'score': module_score(oos_pct),
        'grade': grade_for_pct(oos_pct),
        'kpis': {
            'total_activities':       total,
            'oos_count':              oos_count,
            'oos_pct':                oos_pct,
            'critical_oos':           critical_oos,
            'critical_oos_pct':       critical_pct,
            'near_critical_oos':      near_oos,
            'near_critical_oos_pct':  near_pct,
            'near_critical_days':     near_days,
            'data_date':              data_date_str,
            'affected_wbs':           affected,
            'critical_path_impact':   critical_path_impact,
            'completion_date_impact': completion_impact,
            'executive_conclusion':   _conclusion(oos_count, distribution, critical_oos, near_oos),
        },
        'wbs_summary': distribution,   # persisted as-is; the OOS renderer reads OOS keys
        'findings': findings,
    }
