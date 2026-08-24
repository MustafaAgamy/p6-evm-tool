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


def _resolution(action, applicable, action_text, *, reasoning='', new_type=None,
                new_lag_days=None, new_pred_id=None, sug_pred_id='', sug_pred_name='',
                sug_pred_rel='', sug_pred_lag=None, sug_succ_id='', sug_succ_name='No change'):
    """A machine-actionable proposed correction the planner can accept, edit, and apply.

    ``action`` ∈ {'change', 'remove', 'replace', 'manual'}:
      - 'change'  — repair the dependency by changing the relationship type (+ lag). Preferred.
      - 'remove'  — last resort: no relationship type can hold; ``reasoning`` states why.
      - 'manual'  — not applicable (inconsistent actual dates); ``reasoning`` explains why no
                    automatic correction is safe.
    ``reasoning`` is the plain-language WHY behind the recommendation (shown to the planner).
    Every field is an editable default; re-validation (the same detection engine) is the arbiter.
    """
    return {
        'action': action, 'applicable': applicable, 'action_text': action_text,
        'reasoning': reasoning,
        'new_type': new_type, 'new_lag_days': new_lag_days, 'new_pred_id': new_pred_id,
        'sug_pred_id': sug_pred_id, 'sug_pred_name': sug_pred_name,
        'sug_pred_rel': sug_pred_rel, 'sug_pred_lag': sug_pred_lag,
        'sug_succ_id': sug_succ_id, 'sug_succ_name': sug_succ_name,
    }


# Relationship types the repair search may try, in planner-preference order.
# Finish-to-Start is deliberately excluded: the offending predecessor is always INCOMPLETE
# (no actual finish), so an FS tie can never be satisfied while the successor has progressed —
# recommending FS would never clear the condition.
_REPAIR_TYPES = ('SS', 'FF', 'SF')


def _repair_lag(graph, new_type, succ, pred):
    """A lag that represents the observed overlap for the repaired relationship, so the
    corrected link reflects what actually happened rather than snapping to zero."""
    s_as, s_af = succ.get('actual_start'), succ.get('actual_finish')
    p_as, p_af = pred.get('actual_start'), pred.get('actual_finish')
    if new_type == 'SS' and p_as and s_as:
        return _working_days(graph, succ, p_as, s_as)
    if new_type == 'FF' and p_af and s_af:
        return _working_days(graph, succ, p_af, s_af)
    if new_type == 'SF' and p_as and s_af:
        return _working_days(graph, succ, p_as, s_af)
    return 0


def _why_clears(new_type):
    return {
        'SS': 'the successor started after the predecessor started',
        'FF': 'the successor has not finished, so it can still finish after the predecessor',
        'SF': 'the successor finished after the predecessor started',
    }.get(new_type, '')


def _recommend_correction(graph, cur_type, cur_lag, succ, pred):
    """Behave like an experienced Planning / Project-Controls engineer: try to REPAIR the
    dependency (change the relationship type, with a lag that reflects the real overlap)
    before ever removing it. Removal is the last resort — only when no relationship type can
    hold without creating another logical conflict — and its reason is stated explicitly.

    Whether a candidate type clears the out-of-sequence condition is decided by the SAME
    detection rule (`_is_oos`), so the recommendation and the later re-validation always agree.
    """
    s_as, s_af = succ.get('actual_start'), succ.get('actual_finish')
    p_as = pred.get('actual_start')
    pred_id, pred_name = pred.get('id', ''), pred.get('name', '')
    succ_id = succ.get('id', '')
    cur_label = _rel_lag_label(cur_type, cur_lag)

    # 1) Inconsistent actual dates — predecessor never started yet the successor progressed.
    #    No relationship edit can safely fix a wrong actual date; say so, in full.
    if p_as is None:
        reasoning = (f"Actual dates are inconsistent: predecessor {pred_id} shows no actual start "
                     f"while successor {succ_id} has already progressed. An automatic relationship "
                     f"correction cannot be safely determined from the schedule logic — verify the "
                     f"actual dates in P6. Manual review required.")
        return _resolution(
            'manual', False,
            f"Manual review — actual dates inconsistent: {pred_id} has no actual start while "
            f"{succ_id} has progressed, so no automatic correction can be safely determined.",
            reasoning=reasoning,
            sug_pred_id='', sug_pred_name='Manual review required', sug_pred_rel='MANUAL',
            sug_succ_name='—')

    # 2) Repair search — the first relationship type that clears the condition (SS → FF → SF).
    #    This keeps the dependency and only changes its form to match what actually happened.
    for new_type in _REPAIR_TYPES:
        if new_type == cur_type:
            continue                              # already the flagged type — changing it is the point
        if not _is_oos(new_type, succ, pred):     # candidate clears the out-of-sequence condition
            lag = _repair_lag(graph, new_type, succ, pred)
            new_label = _rel_lag_label(new_type, lag)
            reasoning = (f"Keep the dependency. Changing {pred_id} → {succ_id} from {cur_label} to "
                         f"{new_label} makes the logic match what actually happened "
                         f"({_why_clears(new_type)}), so the sequence becomes consistent without "
                         f"deleting the link.")
            return _resolution(
                'change', True,
                f"Change {pred_id} → {succ_id} from {cur_label} to {new_label}",
                reasoning=reasoning, new_type=new_type, new_lag_days=lag, new_pred_id=pred_id,
                sug_pred_id=pred_id, sug_pred_name=pred_name, sug_pred_rel=new_type, sug_pred_lag=lag)

    # 3) No relationship type can hold — removal is the last resort, with the reason stated.
    #    This is only reached when the successor FINISHED before the predecessor STARTED.
    reasoning = (f"No relationship type (SS, FF or SF) or lag can hold between {pred_id} and "
                 f"{succ_id} without creating another logical conflict: the successor finished "
                 f"before the predecessor started, so the dependency no longer reflects reality. "
                 f"Removing the link is the only reasonable correction.")
    return _resolution(
        'remove', True,
        f"Remove {pred_id} → {succ_id} — no valid relationship type or lag resolves the sequence "
        f"without another logical conflict.",
        reasoning=reasoning,
        sug_pred_id=pred_id, sug_pred_name=pred_name, sug_pred_rel='REMOVE')


def _suggest(graph, cur_type, cur_lag, succ, pred):
    """Wrap the repair-first recommendation and derive the legacy fix labels (kept for the
    PDF/Excel and older tests) from it, so every surface tells the same story."""
    res = _recommend_correction(graph, cur_type, cur_lag, succ, pred)
    pred_id, pred_name = pred.get('id', ''), pred.get('name', '')
    if res['action'] == 'change':
        pred_fix = f"{_rel_lag_label(res['sug_pred_rel'], res['sug_pred_lag'])} - {pred_id} · {pred_name}"
        kind = 'change'
        root = 'Activity progressed out of logical sequence — the relationship type can be repaired.'
        comment = 'Change the relationship type to match the actual sequence (dependency preserved).'
    elif res['action'] == 'remove':
        pred_fix, kind = 'Remove Relationship', 'remove'
        root = 'Successor executed before the predecessor began — the dependency contradicts reality.'
        comment = 'No valid relationship type resolves it; remove the dependency (last resort).'
    else:  # manual
        pred_fix, kind = 'Manual review', 'na'
        root = 'Inconsistent Actual Dates.'
        comment = 'Validate actual dates in P6; no automatic correction can be safely determined.'
    return {
        'pred_fix1': pred_fix, 'pred_fix1_kind': kind,
        'pred_fix2': 'N/A', 'pred_fix2_kind': 'na',
        'succ_fix1': 'No Change', 'succ_fix1_kind': 'same',
        'succ_fix2': 'N/A', 'succ_fix2_kind': 'na',
        'root_cause': root, 'planning_review_comment': comment,
        'resolution': res,
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
        cur_lag = _link.get('lag_days', 0.0) or 0.0
        sug = _suggest(graph, rel_type, cur_lag, act, pred)
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
