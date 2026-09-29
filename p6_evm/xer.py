from datetime import datetime
from p6_evm.parser import ScheduleData, full_wbs_path
from p6_evm.calendars import Calendar
from p6_evm.clndr import parse_clndr_data

TASK_TYPE = {'TT_Task': 'Task', 'TT_Mile': 'StartMilestone', 'TT_FinMile': 'FinishMilestone',
             'TT_LOE': 'LOE', 'TT_WBS': 'WBSSummary', 'TT_Rsrc': 'ResourceDependent'}
PRED_TYPE = {'PR_FS': 'FS', 'PR_SS': 'SS', 'PR_FF': 'FF', 'PR_SF': 'SF'}


def _read_text(path):
    # Try UTF-8 first (fails loudly on cp1252 high bytes); cp1252 last resort
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, encoding='latin-1') as f:
        return f.read()


def read_xer_tables(path):
    """Parse an XER file into {table_name: [row_dict, ...]}."""
    tables = {}
    current = None
    fields = []
    for line in _read_text(path).splitlines():
        if not line:
            continue
        parts = line.split('\t')
        tag = parts[0]
        if tag == '%T':
            current = parts[1]
            fields = []
            tables[current] = []
        elif tag == '%F':
            fields = parts[1:]
        elif tag == '%R' and current is not None:
            values = parts[1:]
            row = {}
            for i, name in enumerate(fields):
                row[name] = values[i] if i < len(values) else ''
            tables[current].append(row)
        # ERMHDR, %E, and anything else are ignored
    return tables


def _num(s, default=None):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def _dt(s):
    if not s:
        return None
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def _pct_complete(t):
    """Activity % complete on the SAME basis P6 uses (complete_pct_type), so the XER
    matches the XML and P6's Earned Value. The old code always read physical %, which is
    0 for Duration-type activities — making the XER's EV wrong. Now:
      CP_Drtn  -> duration %  = (target − remaining) / target duration
      CP_Phys  -> physical % complete
      CP_Units -> units %     = actual units / (actual + remaining units)
    A completed activity is 100%.
    """
    if (t.get('status_code') or '') == 'TK_Complete':
        return 1.0
    typ = t.get('complete_pct_type') or 'CP_Drtn'
    if typ == 'CP_Phys':
        return max(0.0, min(1.0, (_num(t.get('phys_complete_pct'), 0.0) or 0.0) / 100.0))
    if typ == 'CP_Units':
        aw = _num(t.get('act_work_qty'), 0.0) or 0.0
        rw = _num(t.get('remain_work_qty'), 0.0) or 0.0
        tot = aw + rw
        return max(0.0, min(1.0, aw / tot)) if tot else 0.0
    tgt = _num(t.get('target_drtn_hr_cnt'), 0.0) or 0.0
    rem = _num(t.get('remain_drtn_hr_cnt'), 0.0) or 0.0
    return max(0.0, min(1.0, (tgt - rem) / tgt)) if tgt else 0.0


def parse_xer(path):
    tables = read_xer_tables(path)
    data = ScheduleData()

    proj, bl_proj = _current_and_baseline_project(tables)
    proj_id = proj.get('proj_id')
    bl_proj_id = bl_proj.get('proj_id') if bl_proj else None

    # Derive the human-readable project name from this project's root WBS node (proj_node_flag='Y')
    root_wbs = next((w for w in tables.get('PROJWBS', [])
                     if w.get('proj_node_flag') == 'Y'
                     and (not proj_id or w.get('proj_id') in (None, '', proj_id))), {})
    data.project = {
        'object_id': proj_id,
        'id': proj.get('proj_short_name'),
        'name': root_wbs.get('wbs_name') or proj.get('proj_short_name'),
        'data_date': _dt(proj.get('last_recalc_date')),
        # The project's current baseline — named even when its rows are not in the file (a
        # P6 XER update export carries only the BASELINE_EXPORT pointer), like the XML's
        # CurrentBaselineProjectObjectId, so the screen can ask for THAT baseline (finding P1).
        'baseline_object_id': proj.get('sum_base_proj_id') or None,
        'baseline_name': _baseline_name(tables, proj, bl_proj),
    }

    for c in tables.get('CALENDAR', []):
        oid = c.get('clndr_id')
        # Read the working week + holidays from clndr_data so working-time math (Planned%,
        # Delay) matches the XML path. Falls back to a bare (whole-day) calendar on any parse
        # miss, preserving the prior behaviour.
        cd = {}
        try:
            cd = parse_clndr_data(c.get('clndr_data'))
        except Exception:
            cd = {}
        data.calendars[oid] = Calendar(
            object_id=oid, name=c.get('clndr_name'),
            day_hours=_num(c.get('day_hr_cnt'), 8.0) or 8.0,
            nonworking_days=cd.get('nonworking_days') or set(),
            holidays=cd.get('holidays') or set(),
            added_work_days=cd.get('added_work_days') or set(),
            work_intervals=cd.get('work_intervals') or {},
            exception_intervals=cd.get('exception_intervals') or {},
            weekly_working_days=cd.get('weekly_working_days') or set(),
        )

    # Only import WBS nodes belonging to this project
    for w in tables.get('PROJWBS', []):
        if proj_id and w.get('proj_id') not in (None, '', proj_id):
            continue
        data.wbs[w.get('wbs_id')] = {
            'name': w.get('wbs_name'),
            'parent_object_id': w.get('parent_wbs_id') or None,
        }

    # ── Activity codes: dimension names + per-task assignments ──────────────
    actv_type_name = {a.get('actv_code_type_id'): a.get('actv_code_type')
                      for a in tables.get('ACTVTYPE', []) if a.get('actv_code_type')}
    actv_code_val = {c.get('actv_code_id'): (c.get('actv_code_name') or c.get('short_name'))
                     for c in tables.get('ACTVCODE', [])}
    task_codes = {}
    for r in tables.get('TASKACTV', []):
        dim = actv_type_name.get(r.get('actv_code_type_id'))
        val = actv_code_val.get(r.get('actv_code_id'))
        if dim and val:
            task_codes.setdefault(r.get('task_id'), {})[dim] = val
    data.activity_code_types = sorted(actv_type_name.values())

    for t in tables.get('TASK', []):
        # Skip activities from other projects in multi-project XER exports
        if proj_id and t.get('proj_id') not in (None, '', proj_id):
            continue
        oid = t.get('task_id')
        cal = data.calendars.get(t.get('clndr_id'))
        day_hours = cal.day_hours if cal else 8.0
        tf = _num(t.get('total_float_hr_cnt'))
        ff = _num(t.get('free_float_hr_cnt'))
        tf_days = (tf / day_hours) if tf is not None else None
        ff_days = (ff / day_hours) if ff is not None else None
        planned_start = _dt(t.get('target_start_date'))
        planned_finish = _dt(t.get('target_end_date'))
        data.activities[oid] = {
            'object_id': oid,
            'id': t.get('task_code'),
            'name': t.get('task_name'),
            'status': t.get('status_code'),
            'calendar_id': t.get('clndr_id'),
            'wbs_id': t.get('wbs_id'),
            'task_type': TASK_TYPE.get(t.get('task_type'), 'Task'),
            'percent_complete': _pct_complete(t),
            'planned_duration': _num(t.get('target_drtn_hr_cnt'), 0.0),
            'remaining_duration': _num(t.get('remain_drtn_hr_cnt'), 0.0),
            'total_float_days': tf_days,
            'tf_from_hours': tf is not None,   # P6's stored float (authoritative for Delay)
            'free_float_days': ff_days,
            'is_critical': (tf_days is not None and tf_days <= 0),
            'constraint_type': t.get('cstr_type') or None,
            'constraint_date': _dt(t.get('cstr_date')),
            'activity_codes': task_codes.get(oid, {}),
            'wbs_path': full_wbs_path(t.get('wbs_id'), data.wbs),
            'planned_start': planned_start,
            'planned_finish': planned_finish,
            'remaining_early_start': _dt(t.get('restart_date')),
            'remaining_early_finish': _dt(t.get('reend_date')),
            'remaining_late_start': _dt(t.get('rem_late_start_date')),
            'remaining_late_finish': _dt(t.get('rem_late_end_date')),
            # Actual progress dates — for the Out-of-Sequence audit (execution vs logic).
            'actual_start': _dt(t.get('act_start_date')),
            'actual_finish': _dt(t.get('act_end_date')),
        }

    for r in tables.get('TASKPRED', []):
        succ = r.get('task_id')
        pred = r.get('pred_task_id')
        # Only include relationships whose both endpoints belong to this project
        if succ not in data.activities or pred not in data.activities:
            continue
        cal = data.calendars.get((data.activities.get(succ) or {}).get('calendar_id'))
        day_hours = cal.day_hours if cal else 8.0
        lag_hr = _num(r.get('lag_hr_cnt'), 0.0) or 0.0
        data.relationships.append({
            'pred_id': pred, 'succ_id': succ,
            'type': PRED_TYPE.get(r.get('pred_type'), 'FS'),
            'lag_days': lag_hr / day_hours,
            'lag_hours': lag_hr,
        })

    # Resource names (additive) — resolve TASKRSRC assignments to a readable resource name.
    # 'code' is P6's human Resource Id (rsrc_short_name — the short code the planner sees), distinct
    # from the internal rsrc_id; the UI shows the code so the table matches P6.
    _RSRC_TYPE = {'RT_Labor': 'Labour', 'RT_Nonlabor': 'Equipment', 'RT_Equip': 'Equipment',
                  'RT_Mat': 'Material'}
    for rr in tables.get('RSRC', []):
        rid = rr.get('rsrc_id')
        if rid:
            data.resources[rid] = {'name': rr.get('rsrc_name') or rr.get('rsrc_short_name') or rid,
                                   'code': rr.get('rsrc_short_name'),
                                   'type': _RSRC_TYPE.get(rr.get('rsrc_type'))}

    for ra in tables.get('TASKRSRC', []):
        tid = ra.get('task_id')
        if not tid or tid not in data.activities:
            continue
        bac = _num(ra.get('target_cost'), 0.0) or 0.0
        ac = (_num(ra.get('act_reg_cost'), 0.0) or 0.0) + (_num(ra.get('act_ot_cost'), 0.0) or 0.0)
        data.bac_by_activity[tid] = data.bac_by_activity.get(tid, 0.0) + bac
        data.ac_by_activity[tid] = data.ac_by_activity.get(tid, 0.0) + ac
        # Per-assignment resource detail (additive; independent of the cost sums above).
        rid = ra.get('rsrc_id')
        data.assignments_by_activity.setdefault(tid, []).append({
            'resource_id': rid,
            'resource_code': (data.resources.get(rid) or {}).get('code'),   # P6 human Resource Id
            'resource_name': (data.resources.get(rid) or {}).get('name'),
            'resource_type': (data.resources.get(rid) or {}).get('type'),
            'budget_units': _num(ra.get('target_qty'), 0.0) or 0.0,
            'actual_units': (_num(ra.get('act_reg_qty'), 0.0) or 0.0) + (_num(ra.get('act_ot_qty'), 0.0) or 0.0),
            'budget_cost': bac,
            'rate': _num(ra.get('cost_per_qty'), None),
        })

    if bl_proj_id:
        _read_embedded_baseline(tables, bl_proj_id, data)
    if data.baseline_by_id:
        data.baseline_source = 'embedded'
    else:
        # A P6 XER update export carries only the BASELINE_EXPORT pointer, not the baseline
        # rows: the activities' own Planned dates stand in, flagged 'self' - exactly as
        # parser.py does for an XML without <BaselineProject>; an attached baseline
        # (p6_evm.baseline.resolve_baseline) replaces it.
        for a in data.activities.values():
            if a.get('id'):
                data.baseline_by_id[a['id']] = {'planned_start': a.get('planned_start'),
                                                'planned_finish': a.get('planned_finish')}
        data.baseline_source = 'self'
    return data


def _current_and_baseline_project(tables):
    """(current PROJECT row, its baseline PROJECT row or None).

    A multi-project XER can carry the baseline project's own rows (PROJECT / PROJWBS / TASK /
    TASKRSRC ...) beside the update - the XER twin of the XML's <BaselineProject>. The current
    project is the first row that is NOT another row's baseline (sum_base_proj_id), wherever the
    baseline row sits; its baseline is the row whose proj_id is its sum_base_proj_id."""
    rows = tables.get('PROJECT') or [{}]
    ids = {r.get('proj_id') for r in rows}
    baselines = {r.get('sum_base_proj_id') for r in rows
                 if r.get('sum_base_proj_id') and r.get('sum_base_proj_id') != r.get('proj_id')}
    current = next((r for r in rows if r.get('proj_id') not in baselines), rows[0])
    bl_id = current.get('sum_base_proj_id')
    bl_row = None
    if bl_id and bl_id != current.get('proj_id') and bl_id in ids:
        bl_row = next(r for r in rows if r.get('proj_id') == bl_id)
    return current, bl_row


def _baseline_name(tables, proj, bl_proj):
    """The baseline's project name: BASELINE_EXPORT.proj_name for the project's baseline (P6
    writes it even when the baseline rows are not exported), else the baseline project's own
    root-WBS name (what the XML's <BaselineProject><Name> holds)."""
    bl_id = proj.get('sum_base_proj_id')
    if not bl_id:
        return None
    for r in tables.get('BASELINE_EXPORT', []):
        if r.get('proj_id') == bl_id and r.get('proj_name'):
            return r.get('proj_name')
    if bl_proj:
        root = next((w for w in tables.get('PROJWBS', [])
                     if w.get('proj_node_flag') == 'Y' and w.get('proj_id') == bl_id), {})
        return root.get('wbs_name') or bl_proj.get('proj_short_name')
    return None


def _read_embedded_baseline(tables, bl_proj_id, data):
    """Fill baseline_by_id / baseline_bac_by_activity from the baseline project's own TASK and
    TASKRSRC rows - the same linkage parser.py makes from <BaselineProject>: planned dates
    (target_start/end = PlannedStart/FinishDate) keyed by Activity Id, baseline budget
    (target_cost = PlannedCost) summed per activity and keyed back to the current activity by
    Activity Id (only where the baseline carries cost)."""
    bl_code = {}
    for t in tables.get('TASK', []):
        if t.get('proj_id') != bl_proj_id or not t.get('task_code'):
            continue
        bl_code[t.get('task_id')] = t.get('task_code')
        data.baseline_by_id[t.get('task_code')] = {
            'planned_start': _dt(t.get('target_start_date')),
            'planned_finish': _dt(t.get('target_end_date')),
        }
    bac_by_code = {}
    for ra in tables.get('TASKRSRC', []):
        code = bl_code.get(ra.get('task_id'))
        if code:
            bac_by_code[code] = bac_by_code.get(code, 0.0) + (_num(ra.get('target_cost'), 0.0) or 0.0)
    for oid, a in data.activities.items():
        if a.get('id') in bac_by_code:
            data.baseline_bac_by_activity[oid] = bac_by_code[a['id']]
