"""The three Update-Analysis computations. All pure: they take a parsed `ScheduleData`
(and, for the time status, the `metrics.compute()` result so the cost figures tie to the
EVM tab). Nothing here schedules — expected finishes are read from the file's own
forecast dates, exactly as P6 wrote them.
"""
from p6_evm.metrics import activity_planned_pct
from p6_evm.calendars import signed_working_days

_MILESTONES = ('StartMilestone', 'FinishMilestone')


def _iso(d):
    return d.strftime('%Y-%m-%d') if d else None


def _from_iso(s):
    from datetime import datetime
    try:
        return datetime.strptime(str(s)[:10], '%Y-%m-%d') if s else None
    except Exception:
        return None


def _weight(data, act):
    """Activity's share — baseline budget (BAC) when the file carries one, else the current
    cost, else planned duration. Matches how the rest of the tool weights progress."""
    oid = act.get('object_id')
    bl = getattr(data, 'baseline_bac_by_activity', None) or {}
    bac = getattr(data, 'bac_by_activity', None) or {}
    w = bl.get(oid) or bac.get(oid) or 0.0
    return w if w and w > 0 else ((act.get('planned_duration') or 0.0) or 1.0)


def _cost_weight(data, act):
    """Activity's cost (baseline budget, else current cost); 0 when it carries no cost."""
    oid = act.get('object_id')
    bl = getattr(data, 'baseline_bac_by_activity', None) or {}
    bac = getattr(data, 'bac_by_activity', None) or {}
    return bl.get(oid) or bac.get(oid) or 0.0


def _file_has_cost(data):
    bl = getattr(data, 'baseline_bac_by_activity', None) or {}
    bac = getattr(data, 'bac_by_activity', None) or {}
    return any(v and v > 0 for v in bl.values()) or any(v and v > 0 for v in bac.values())


def _pct_weight(data, act, costed):
    """Weight for the Planned%/Actual% figures: baseline budget only over fully cost-loaded
    activities (Ibrahim's rule — no cost, no contribution). Falls back to duration only when
    the whole schedule carries no cost at all (a bare XER), so the feature still runs."""
    if costed:
        return _cost_weight(data, act)   # 0 for an uncosted activity → excluded from the %
    return (act.get('planned_duration') or 0.0) or 1.0


def _forecast_finish(act):
    """P6's own forecast finish for the activity — actual if complete, else remaining early,
    else the planned finish. Read from the file; never computed here."""
    return act.get('actual_finish') or act.get('remaining_early_finish') or act.get('planned_finish')


def _baseline_of(data, act):
    return (getattr(data, 'baseline_by_id', None) or {}).get(act.get('id')) or {}


def _ref_calendar(data):
    """A single reference calendar for project/WBS-level day counts — the most common one
    across activities, so slip-in-working-days is consistent across boxes."""
    cals = getattr(data, 'calendars', None) or {}
    counts = {}
    for a in data.activities.values():
        cid = a.get('calendar_id')
        if cid in cals:
            counts[cid] = counts.get(cid, 0) + 1
    if not counts:
        return None
    return cals.get(max(counts, key=counts.get))


def _days_between(cal, d1, d2):
    """Signed working days d1→d2 on the reference calendar; falls back to calendar days."""
    if not d1 or not d2:
        return None
    try:
        return round(signed_working_days(cal, d1, d2)) if cal else (d2 - d1).days
    except Exception:
        return (d2 - d1).days


# ── Section 1 · Time Status ──────────────────────────────────────────────────

def time_status(data, metrics, span_start=None, span_finish=None):
    """How much of the baseline's calendar has been used up, and the cost-earned vs
    cost-planned progress against it.

    - elapsed: calendar days (working AND non-working) from the baseline start to the
      data date, over the whole baseline duration to the baseline FINISH. When the data
      date passes the baseline finish it reads 100% + `exceeded_days` rather than >100%.
      The span defaults to the driving path — from the start milestone that releases it to
      the governing completion milestone (so procurement/mobilisation before the works don't
      count) — falling back to the earliest/latest baseline dates when no path is supplied.
    - actual %: Earned Value ÷ Budget across all cost-loaded activities (Ibrahim's rule).
    - planned %: PV ÷ Budget the same way (time-based planned %).
    """
    data_date = (getattr(data, 'project', None) or {}).get('data_date')
    bl = getattr(data, 'baseline_by_id', None) or {}
    if span_start and span_finish:
        bl_start, bl_finish = span_start, span_finish
    else:
        starts = [b['planned_start'] for b in bl.values() if b.get('planned_start')]
        finishes = [b['planned_finish'] for b in bl.values() if b.get('planned_finish')]
        bl_start = min(starts) if starts else None
        bl_finish = max(finishes) if finishes else None

    elapsed_pct = exceeded_days = total_days = elapsed_days = None
    if bl_start and bl_finish and data_date and bl_finish > bl_start:
        total_days = (bl_finish - bl_start).days
        elapsed_days = max(0, (data_date - bl_start).days)
        if data_date >= bl_finish:
            elapsed_pct = 100.0
            exceeded_days = (data_date - bl_finish).days
        else:
            elapsed_pct = round(elapsed_days / total_days * 100, 1)
            exceeded_days = 0

    # Cost-based planned/actual over all cost-loaded activities; fall back to duration
    # weighting when the file carries no cost at all, so the donut never blanks out.
    recs = metrics.get('records', []) if metrics else []
    cost_loaded = any((r.get('bac') or 0.0) > 0 for r in recs)

    tot_w = a_sum = p_sum = p_w = 0.0
    for r in recs:
        if cost_loaded:
            w = r.get('bac') or 0.0
            if w <= 0:
                continue
        else:
            w = (r['activity'].get('planned_duration') or 0.0) or 1.0
        a = r.get('actual_pct')
        p = r.get('planned_pct')
        tot_w += w
        a_sum += w * (a or 0.0)
        if p is not None:
            p_sum += w * p
            p_w += w

    # Two decimals on the cost-earned/planned % so Section 1 reads like P6 (e.g. 40.43% / 61.42%).
    actual_pct = round(a_sum / tot_w * 100, 2) if tot_w else None
    planned_pct = round(p_sum / p_w * 100, 2) if p_w else None

    # The money behind the percentages — Planned Value, Earned Value and their variance,
    # straight from metrics.compute (ties to the EVM tab).
    pv = metrics.get('pv') if metrics else None
    ev = metrics.get('ev') if metrics else None
    cost_variance = (ev - pv) if (pv is not None and ev is not None) else None

    behind_clock = None
    if actual_pct is not None and elapsed_pct is not None:
        behind_clock = round(elapsed_pct - actual_pct, 2)   # +ve = behind the clock
    behind_plan = None
    if actual_pct is not None and planned_pct is not None:
        behind_plan = round(planned_pct - actual_pct, 2)    # +ve = behind plan

    return {
        'elapsed_pct': elapsed_pct,
        'exceeded_days': exceeded_days,
        'total_days': total_days,
        'elapsed_days': elapsed_days,
        'baseline_start': _iso(bl_start),
        'baseline_finish': _iso(bl_finish),
        'data_date': _iso(data_date),
        'planned_pct': planned_pct,
        'actual_pct': actual_pct,
        'behind_clock': behind_clock,
        'behind_plan': behind_plan,
        'cost_loaded': cost_loaded,
        'pv': pv,
        'ev': ev,
        'cost_variance': cost_variance,
    }


# ── Section 2 · Planned vs Actual by activity code ───────────────────────────

def _bucket(data, types):
    """Cumulative (vs baseline) planned vs actual %, bucketed by the given activity-code
    dimension(s). Percentages are cost-based — weighted by baseline budget over fully
    cost-loaded activities only (Ibrahim's rule); an uncosted activity does not contribute.
    Falls back to duration only when the whole schedule carries no cost."""
    data_date = (getattr(data, 'project', None) or {}).get('data_date')
    costed = _file_has_cost(data)
    agg = {}
    for act in data.activities.values():
        if act.get('task_type') in _MILESTONES:
            continue
        codes = act.get('activity_codes') or {}
        vals = [codes.get(t) for t in types]
        if any(v is None for v in vals):
            continue
        planned = activity_planned_pct(act, data.baseline_by_id, data_date, data.calendars)
        if planned is None:
            continue   # no baseline for this activity → can't place it planned vs actual
        w = _pct_weight(data, act, costed)
        if w <= 0:
            continue   # cost-loaded only — an uncosted activity carries no weight
        actual = act.get('percent_complete') or 0.0
        key = ' · '.join(vals)
        e = agg.setdefault(key, [0.0, 0.0, 0.0, 0])
        e[0] += w
        e[1] += w * planned
        e[2] += w * actual
        e[3] += 1
    rows = []
    for key, (w, wp, wa, n) in agg.items():
        p = round(wp / w * 100, 1) if w else 0.0
        a = round(wa / w * 100, 1) if w else 0.0
        rows.append({'value': key, 'planned': p, 'actual': a,
                     'variance': round(a - p, 1), 'activity_count': n})
    rows.sort(key=lambda r: r['variance'])   # worst gap first
    return rows


def by_code(data):
    """{code_type: [rows]} for every single activity-code dimension in the schedule."""
    return {t: _bucket(data, [t]) for t in (getattr(data, 'activity_code_types', None) or [])}


# ── Section 4 · Planned vs Actual by activity count ──────────────────────────

def activity_counts(data, construction_only=True, code_filter=None):
    """Count activities by status — Completed / In Progress / Not Started — on the Planned
    side (from the baseline dates at the data date) and the Actual side (from % complete),
    over construction/execution activities only. Optionally filtered to one activity-code
    value. The three actual buckets sum to `total`; the three planned buckets sum to
    `planned_total` (activities that carry a baseline)."""
    cons = None
    if construction_only:
        try:
            from p6_compare.report import _construction_codes
            cons = _construction_codes(data) or None
        except Exception:
            cons = None
    data_date = (getattr(data, 'project', None) or {}).get('data_date')
    ft = (code_filter or {}).get('type')
    fv = (code_filter or {}).get('value')

    c = {'planned_completed': 0, 'planned_in_progress': 0, 'planned_not_started': 0,
         'actual_completed': 0, 'actual_in_progress': 0, 'actual_not_started': 0,
         'total': 0, 'planned_total': 0}
    for a in data.activities.values():
        if a.get('task_type') in _MILESTONES:
            continue
        if cons is not None and a.get('id') not in cons:
            continue
        if ft and fv and (a.get('activity_codes') or {}).get(ft) != fv:
            continue
        c['total'] += 1
        pc = a.get('percent_complete') or 0.0
        if pc >= 1.0 or a.get('actual_finish'):
            c['actual_completed'] += 1
        elif pc > 0.0 or a.get('actual_start'):
            c['actual_in_progress'] += 1
        else:
            c['actual_not_started'] += 1
        bl = _baseline_of(data, a)
        bs, bf = bl.get('planned_start'), bl.get('planned_finish')
        if bf and data_date and bf <= data_date:
            c['planned_completed'] += 1
            c['planned_total'] += 1
        elif bs and data_date and bs <= data_date:
            c['planned_in_progress'] += 1
            c['planned_total'] += 1
        elif bs:
            c['planned_not_started'] += 1
            c['planned_total'] += 1
    return c


# ── Section 5 · Scope weight & recommendation ────────────────────────────────

def _default_scope_code(types):
    tiers = [r'type of civil', r'type of work', r'disciplin', r'\btrade\b', r'main wbs']
    import re
    for pat in tiers:
        for t in types:
            if re.search(pat, t, re.I):
                return t
    return types[0] if types else None


def _recommendation(rows, code_type):
    """Smarter advice: prioritise the scope with the largest cost weight that is ALSO behind
    plan (biggest, most-slipped part of the scope). Falls back to the largest weight when
    nothing is behind. Recomputed for whatever code(s) are chosen."""
    if not rows:
        return []
    def gap(r):
        return round((r.get('planned') or 0.0) - (r.get('actual') or 0.0), 1)
    behind = [r for r in rows if gap(r) > 0.5]
    if behind:
        pick = max(behind, key=lambda r: r['weight_pct'])
        g = gap(pick)
        out = [f"Prioritise {pick['value']} — it is the largest weight ({pick['weight_pct']:.1f}%) that is behind "
               f"plan ({pick['actual']:.1f}% actual vs {pick['planned']:.1f}% planned, {g:.1f} points behind) in "
               f"the {code_type} scope. Focusing here moves the biggest, most-slipped part of the scope."]
        others = [r for r in behind if r is not pick]
        if others:
            r2 = max(others, key=lambda r: r['weight_pct'] * gap(r))
            out.append(f"Also watch {r2['value']} — {r2['weight_pct']:.1f}% of the scope and "
                       f"{gap(r2):.1f} points behind plan.")
        return out
    top = rows[0]
    return [f"It is recommended to work on {top['value']} as it represents the largest weight "
            f"({top['weight_pct']:.1f}%) in the {code_type} scope — and it is on or ahead of plan."]


def scope_weights(data, code_type, construction_only=True):
    """Each activity-code value's share of the cost-loaded scope (baseline budget), heaviest
    first, plus a recommendation naming the largest. Construction/execution activities only.
    `code_type` may be a single dimension or a LIST of dimensions — with several, activities are
    weighted by the COMBINATION (an activity counts only when it carries every chosen code)."""
    types = [t for t in (code_type if isinstance(code_type, (list, tuple)) else [code_type]) if t]
    label = ' · '.join(types)
    data_date = (getattr(data, 'project', None) or {}).get('data_date')
    cons = None
    if construction_only:
        try:
            from p6_compare.report import _construction_codes
            cons = _construction_codes(data) or None
        except Exception:
            cons = None
    agg = {}   # key -> [cost, planned_num, planned_den, actual_num]
    total = 0.0
    for a in data.activities.values():
        if a.get('task_type') in _MILESTONES:
            continue
        if cons is not None and a.get('id') not in cons:
            continue
        codes = a.get('activity_codes') or {}
        vals = [codes.get(t) for t in types]
        if any(v is None for v in vals):
            continue
        w = _cost_weight(data, a)
        if w <= 0:
            continue
        key = ' · '.join(vals)
        e = agg.setdefault(key, [0.0, 0.0, 0.0, 0.0])
        e[0] += w
        pl = activity_planned_pct(a, data.baseline_by_id, data_date, data.calendars)
        if pl is not None:
            e[1] += w * pl
            e[2] += w
        e[3] += w * (a.get('percent_complete') or 0.0)
        total += w
    rows = []
    if total > 0:
        for v, (cost, pn, pd, an) in agg.items():
            rows.append({'value': v, 'bac': round(cost), 'weight_pct': round(cost / total * 100, 1),
                         'planned': round(pn / pd * 100, 1) if pd else 0.0,
                         'actual': round(an / cost * 100, 1) if cost else 0.0})
    rows.sort(key=lambda r: -r['weight_pct'])
    return {'code_type': label, 'total': round(total), 'rows': rows,
            'recommendation': _recommendation(rows, label)}


def scope_all(data):
    """Scope weights for every activity-code dimension that carries cost — so the UI can switch
    code and see the recommendation rewrite itself instantly. {code_type: scope_weights(...)}."""
    out = {}
    for t in (getattr(data, 'activity_code_types', None) or []):
        s = scope_weights(data, t)
        if s['rows']:
            out[t] = s
    return out


# ── Section 3 · Driving Path Analyzer ────────────────────────────────────────

def _governing_milestone(data):
    """The completion milestone with the latest forecast finish — the one that decides when
    the project actually finishes. Falls back to the latest-finishing activity when the
    schedule carries no finish milestone (same rule as the EVM Delay)."""
    fin_ms = [a for a in data.activities.values()
              if a.get('task_type') == 'FinishMilestone' and _forecast_finish(a)]
    pool = fin_ms or [a for a in data.activities.values() if _forecast_finish(a)]
    if not pool:
        return None
    return max(pool, key=_forecast_finish)


def _trace_driving_chain(graph, start_oid, limit=500):
    """Walk backwards from the milestone along the binding predecessor at each step, returning
    the chain earliest→last. Prefer the driving predecessors; but the driving detector misses
    some SS/FF-with-lag links, so when it returns nothing we fall back to the activity's actual
    predecessors and follow the one whose controlling finish is latest — otherwise the path
    dead-ends early (it was stopping at Silo 10 instead of reaching Silo 9 and the start
    milestone that releases it)."""
    from p6_compare.driving import driving_predecessors
    chain = [start_oid]
    seen = {start_oid}
    cur = start_oid
    while len(chain) < limit:
        cands = [pl['pred_oid'] for pl in driving_predecessors(graph, cur)]
        if not cands:
            cands = [link['other'] for link in graph.preds_of(cur)]
        best, best_f = None, None
        for poid in cands:
            if poid in seen:
                continue
            p = graph.activities.get(poid)
            if not p:
                continue
            f = _forecast_finish(p)
            if best is None or (f and (best_f is None or f > best_f)):
                best, best_f = poid, f
        if not best:
            break
        chain.append(best)
        seen.add(best)
        cur = best
    chain.reverse()
    return chain


def _wbs_ancestor_ids(wbs_id, wmap):
    ids, seen, cur = [], set(), wbs_id
    while cur and cur not in seen:
        seen.add(cur)
        ids.append(cur)
        node = wmap.get(cur)
        if not node:
            break
        cur = node.get('parent_object_id')
    return ids


def _wbs_name(wbs_id, wmap):
    node = wmap.get(wbs_id) or {}
    return node.get('name') or ''


def _crumb(wbs_id, wmap):
    """Ancestor names above the work front, top→down (e.g. 'Phase A · Silo 1'). The project
    root is dropped — it's already the report title, so repeating it in every crumb is noise."""
    ids = _wbs_ancestor_ids(wbs_id, wmap)[1:]   # drop the work front itself → parent … root
    names = [n for n in (_wbs_name(i, wmap) for i in ids) if n]
    top_down = list(reversed(names))            # root … parent
    return ' · '.join(top_down[1:])             # drop the project root


def _box_wbs_id(act, wmap, summary_level):
    """The WBS node that represents this activity's work front. summary_level 0 = the
    activity's immediate WBS; 1/2 climb toward area/phase."""
    ids = _wbs_ancestor_ids(act.get('wbs_id'), wmap)
    if not ids:
        return None
    idx = min(summary_level, len(ids) - 1)
    return ids[idx]


def critical_path(data, summary_level=0, construction_only=True):
    """The governing completion milestone's driving path, rolled up to WBS work-front boxes.
    Construction/execution activities only by default. Every box is a WBS collapsed like in
    P6: % = WBS rollup, BL/Expected = the WBS's latest baseline / forecast finish."""
    from p6_audit.graph import ScheduleGraph

    cons = None
    if construction_only:
        try:
            from p6_compare.report import _construction_codes
            cons = _construction_codes(data) or None
        except Exception:
            cons = None

    milestone = _governing_milestone(data)
    if not milestone:
        return {'milestone': None, 'charts': [], 'summary_level': summary_level,
                'construction_only': construction_only, 'headline': ''}

    graph = ScheduleGraph(data)
    chain = _trace_driving_chain(graph, milestone.get('object_id'))

    wmap = getattr(data, 'wbs', None) or {}
    ref_cal = _ref_calendar(data)

    # Pre-index WBS subtree → activities (for the whole-WBS rollup each box shows).
    subtree = {}
    for a in data.activities.values():
        for anc in _wbs_ancestor_ids(a.get('wbs_id'), wmap):
            subtree.setdefault(anc, []).append(a)

    # Order the driving activities into work-front boxes. Each WBS work front appears once,
    # in path order. Keep the driving activity that put each WBS on the path (the no-cost
    # fallback below shows that activity by name) and the path activities (for the path start).
    data_date = (getattr(data, 'project', None) or {}).get('data_date')
    box_order = []
    seen_wids = set()
    box_driver = {}
    path_acts = []
    for oid in chain:
        act = graph.activities.get(oid)
        if not act:
            continue
        if cons is not None and act.get('id') not in cons:
            continue   # non-construction link — traversed for connectivity, not shown
        path_acts.append(act)
        wid = _box_wbs_id(act, wmap, summary_level)
        if not wid or wid in seen_wids:
            continue
        seen_wids.add(wid)
        box_order.append(wid)
        box_driver[wid] = act

    costed_file = _file_has_cost(data)

    def _has_cost(acts):
        return any(_cost_weight(data, a) > 0 for a in acts)

    boxes = []
    for wid in box_order:
        acts = subtree.get(wid, [])
        if not (costed_file and not _has_cost(acts)):
            # WBS rollup. Percentages are cost-weighted over the cost-loaded activities only
            # (a bare XER with no cost anywhere falls back to duration). The finish dates come
            # from ALL the WBS's activities — the work front's own baseline / forecast finish.
            w = wa = pw = pp = 0.0
            bls, exps = [], []
            for a in acts:
                ww = _pct_weight(data, a, costed_file)
                if ww > 0:
                    w += ww
                    wa += ww * (a.get('percent_complete') or 0.0)
                    pl = activity_planned_pct(a, data.baseline_by_id, data_date, data.calendars)
                    if pl is not None:
                        pw += ww
                        pp += ww * pl
                bf = _baseline_of(data, a).get('planned_finish')
                ff = _forecast_finish(a)
                if bf:
                    bls.append(bf)
                if ff:
                    exps.append(ff)
            pct = round(wa / w * 100, 1) if w else 0.0
            planned = round(pp / pw * 100, 1) if pw else 0.0
            bl_fin = max(bls) if bls else None
            exp_fin = max(exps) if exps else None
            name = _wbs_name(wid, wmap)
            source = 'wbs'
        else:
            # No cost anywhere in this work front → show the specific driving ACTIVITY by its
            # exact name, with its own numbers. A budget-weighted WBS % would be meaningless and
            # can blend unrelated activities (e.g. Silo 7 done + Silo 10 not started → a false 50%).
            a = box_driver[wid]
            pct = round((a.get('percent_complete') or 0.0) * 100, 1)
            pl = activity_planned_pct(a, data.baseline_by_id, data_date, data.calendars)
            planned = round((pl or 0.0) * 100, 1)
            bl_fin = _baseline_of(data, a).get('planned_finish')
            exp_fin = _forecast_finish(a)
            name = a.get('name') or a.get('id') or _wbs_name(wid, wmap)
            source = 'activity'
        slip = _days_between(ref_cal, bl_fin, exp_fin)
        boxes.append({
            'wbs_id': wid,
            'crumb': _crumb(wid, wmap),
            'name': name,
            'source': source,               # 'wbs' rollup, or a single 'activity' (no cost)
            'pct': pct,
            'planned': planned,
            'bl_finish': _iso(bl_fin),
            'exp_finish': _iso(exp_fin),
            'slip_days': slip,
            'status': 'done' if pct >= 100.0 else 'on-path',
            'complete': pct >= 100.0,
        })

    # Start-milestone "big box" — the start milestone that RELEASES the first work front (the
    # last Start Milestone on the chain before the first construction activity), e.g. "Finalize
    # Contract Addendum" before Silo 9 piles — not necessarily the earliest project milestone.
    start_ms = None
    for oid in chain:
        a = graph.activities.get(oid)
        if not a:
            continue
        if cons is not None and a.get('id') in cons:
            break   # reached the first work front
        if a.get('task_type') == 'StartMilestone':
            start_ms = a
    start_ms_date = None
    start_milestone = None
    if start_ms is not None:
        start_ms_date = _forecast_finish(start_ms) or _baseline_of(data, start_ms).get('planned_finish')
        start_milestone = {'name': start_ms.get('name') or start_ms.get('id'), 'date': _iso(start_ms_date)}

    # Path start (kept for the headline): the start milestone's date, else the earliest start.
    starts = [s for s in (_baseline_of(data, a).get('planned_start') for a in path_acts) if s]
    if not starts:
        starts = [s for s in ((a.get('remaining_early_start') or a.get('actual_start')) for a in path_acts) if s]
    ms_start = start_ms_date or (min(starts) if starts else None)

    ms_bl = _baseline_of(data, milestone).get('planned_finish')
    ms_exp = _forecast_finish(milestone)
    ms_slip = _days_between(ref_cal, ms_bl, ms_exp)
    ms = {
        'name': milestone.get('name') or milestone.get('id') or 'Project completion',
        'id': milestone.get('id'),
        'path_start': _iso(ms_start),
        'baseline_finish': _iso(ms_bl),
        'expected_finish': _iso(ms_exp),
        'slip_days': ms_slip,
    }

    headline = _cp_headline(ms, boxes)
    chart = {'title': ms['name'], 'boxes': boxes, 'milestone': ms, 'start_milestone': start_milestone}
    return {
        'milestone': ms,
        'charts': [chart] if boxes else [],
        'summary_level': summary_level,
        'construction_only': construction_only,
        'headline': headline,
    }


def _cp_headline(ms, boxes):
    if not boxes:
        return ''
    driver = boxes[-1]   # the box feeding the milestone
    parts = []
    if ms.get('expected_finish'):
        tail = ''
        if ms.get('slip_days') is not None:
            if ms['slip_days'] > 0:
                tail = f", {ms['slip_days']} working days later than the baseline {ms.get('baseline_finish') or ''}".rstrip()
            elif ms['slip_days'] < 0:
                tail = f", {abs(ms['slip_days'])} working days earlier than baseline"
        parts.append(f"The critical path finishes at {ms['name']} on {ms['expected_finish']}{tail}.")
    if driver and driver.get('name'):
        parts.append(f"It is driven by {driver['name']}.")
    n = len(boxes)
    parts.append(f"{n} construction work front{'s' if n != 1 else ''} lie on the driving path.")
    return ' '.join(parts)


# ── Report assembly ──────────────────────────────────────────────────────────

def build_report_from_data(data, metrics, summary_level=0):
    """Assemble the whole Update-Analysis report from a parsed update + its metrics.compute
    result. `has_baseline` false means the file carries no baseline — the caller shows the
    'attach a baseline' state rather than wrong numbers."""
    has_baseline = bool(getattr(data, 'baseline_by_id', None))
    proj = getattr(data, 'project', None) or {}
    cp = critical_path(data, summary_level=summary_level)
    # Time Status runs over the DRIVING PATH's span — from the start milestone that releases it
    # to the governing completion milestone — so procurement/mobilisation before the works don't
    # inflate "time elapsed". Falls back to the earliest/latest baseline dates when there's no path.
    span_start = span_finish = None
    if cp.get('charts'):
        sm = cp['charts'][0].get('start_milestone') or {}
        span_start = _from_iso(sm.get('date'))
    span_finish = _from_iso((cp.get('milestone') or {}).get('baseline_finish'))
    ts = time_status(data, metrics, span_start, span_finish)
    return {
        'project_name': proj.get('name') or proj.get('id') or 'Project',
        'data_date': _iso(proj.get('data_date')),
        'has_baseline': has_baseline,
        'activity_count': len(getattr(data, 'activities', {}) or {}),
        'code_types': list(getattr(data, 'activity_code_types', None) or []),
        'time_status': ts,
        'by_code': by_code(data),
        'critical_path': cp,
        'counts': activity_counts(data),
        'scope': scope_all(data),
        'scope_default': _default_scope_code(list(getattr(data, 'activity_code_types', None) or [])),
        'conclusion': _report_conclusion(ts, cp),
    }


def _report_conclusion(ts, cp):
    """One plain planner's read for the top of the report / PDF."""
    parts = []
    ep, ap, pp = ts.get('elapsed_pct'), ts.get('actual_pct'), ts.get('planned_pct')
    if ep is not None and ap is not None:
        clock = ''
        if ts.get('behind_clock') is not None:
            if ts['behind_clock'] > 0:
                clock = f" — {ts['behind_clock']} points behind the clock"
            elif ts['behind_clock'] < 0:
                clock = f" — {abs(ts['behind_clock'])} points ahead of the clock"
        exceeded = ''
        if ts.get('exceeded_days'):
            exceeded = f" (the baseline finish is already exceeded by {ts['exceeded_days']} days)"
        parts.append(f"{ep:.0f}% of the baseline time has elapsed and {ap:.0f}% is earned{clock}{exceeded}.")
    if pp is not None and ap is not None and ts.get('behind_plan') is not None and ts['behind_plan'] > 0:
        parts.append(f"That is {ts['behind_plan']} points behind the {pp:.0f}% planned.")
    if cp.get('headline'):
        parts.append(cp['headline'])
    return ' '.join(parts)
