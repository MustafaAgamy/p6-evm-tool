from p6_evm.parser import (ScheduleData, full_wbs_path, _activity_calendar, lag_calendar_id,
                           lag_day_hours, sort_relationships, sort_calendars, units_percent_complete,
                           parse_p6_datetime, collect_unparsed_dates, resource_type_label,
                           resource_unit)
from p6_evm.calendars import Calendar, float_basis, total_float_hours, lag_calendar_basis, minute_hours
from p6_evm.clndr import parse_clndr_data

TASK_TYPE = {'TT_Task': 'Task', 'TT_Mile': 'StartMilestone', 'TT_FinMile': 'FinishMilestone',
             'TT_LOE': 'LOE', 'TT_WBS': 'WBSSummary', 'TT_Rsrc': 'ResourceDependent'}
PRED_TYPE = {'PR_FS': 'FS', 'PR_SS': 'SS', 'PR_FF': 'FF', 'PR_SF': 'SF'}
# ONE vocabulary for both formats (R4): the XER's codes are read as the words P6 writes to the
# XML (<Status>, <PrimaryConstraintType>/<SecondaryConstraintType>), so every status- or
# constraint-based check (hard constraints, milestones, float, engineering progress) works the
# same on either file (findings P6 / P7). An unknown code is kept as-is (honest, never guessed).
# CALENDAR.clndr_type -> the words P6 writes to the XML's <Calendar><Type> (finding P12).
CLNDR_TYPE = {'CA_Base': 'Global', 'CA_Project': 'Project', 'CA_Rsrc': 'Resource'}
STATUS = {'TK_NotStart': 'Not Started', 'TK_Active': 'In Progress', 'TK_Complete': 'Completed'}
CSTR_TYPE = {'CS_MSO': 'Start On', 'CS_MSOB': 'Start On or Before', 'CS_MSOA': 'Start On or After',
             'CS_MEO': 'Finish On', 'CS_MEOB': 'Finish On or Before', 'CS_MEOA': 'Finish On or After',
             'CS_ALAP': 'As Late As Possible', 'CS_MANDSTART': 'Mandatory Start',
             'CS_MANDFIN': 'Mandatory Finish'}


def _status(code):
    return STATUS.get(code, code or None)


def _cstr(code):
    return CSTR_TYPE.get(code, code) if code else None


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


def _unescape(v):
    """Decode P6's XER text escaping so a value reads exactly as the XML's: a double quote is
    written "" (finding P14 - ALSTOM resource '65"" inch' vs the XML's '65" inch', which broke
    resource / assignment matching) and a line break as two DEL characters 0x7F 0x7F (a lone
    0x7F for a bare line feed) where the XML holds a real newline (finding P15 - activity names
    such as 'FANS\\x7f\\x7f - Approval' vs 'FANS\\n - Approval')."""
    if '""' in v:
        v = v.replace('""', '"')
    if '\x7f' in v:
        v = v.replace('\x7f\x7f', '\n').replace('\x7f', '\n')
    return v


def read_xer_tables(path):
    """Parse an XER file into {table_name: [row_dict, ...]}, text values decoded (_unescape)."""
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
            if '"' in line or '\x7f' in line:
                values = [_unescape(v) for v in values]
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
    # The one tolerant P6 date reader shared with the XML path (finding P22): a value it cannot
    # read is recorded in data.unparsed_dates instead of silently dropped.
    return parse_p6_datetime(s)


def _pct_complete(t):
    """Activity % complete on the SAME basis P6 uses (complete_pct_type), so the XER
    matches the XML and P6's Earned Value. The old code always read physical %, which is
    0 for Duration-type activities — making the XER's EV wrong. Now:
      CP_Drtn  -> duration %  = (target − remaining) / target duration
      CP_Phys  -> physical % complete
      CP_Units -> units %     = actual units / (actual + remaining units), labour + nonlabour
                                like P6 (finding P19 - it counted labour units only)
    A completed activity is 100%.
    """
    if (t.get('status_code') or '') == 'TK_Complete':
        return 1.0
    typ = t.get('complete_pct_type') or 'CP_Drtn'
    if typ == 'CP_Phys':
        return max(0.0, min(1.0, (_num(t.get('phys_complete_pct'), 0.0) or 0.0) / 100.0))
    if typ == 'CP_Units':
        return units_percent_complete(_num(t.get('act_work_qty'), 0.0),
                                      _num(t.get('remain_work_qty'), 0.0),
                                      _num(t.get('act_equip_qty'), 0.0),
                                      _num(t.get('remain_equip_qty'), 0.0))
    tgt = _num(t.get('target_drtn_hr_cnt'), 0.0) or 0.0
    rem = _num(t.get('remain_drtn_hr_cnt'), 0.0) or 0.0
    return max(0.0, min(1.0, (tgt - rem) / tgt)) if tgt else 0.0


def parse_xer(path):
    with collect_unparsed_dates() as unparsed:
        data = _parse_xer(path)
    data.unparsed_dates = dict(unparsed)
    return data


def _parse_xer(path):
    tables = read_xer_tables(path)
    data = ScheduleData()

    proj, bl_proj = _current_and_baseline_project(tables)
    proj_id = proj.get('proj_id')
    bl_proj_id = bl_proj.get('proj_id') if bl_proj else None

    # Derive the human-readable project name from this project's root WBS node (proj_node_flag='Y')
    root_wbs = next((w for w in tables.get('PROJWBS', [])
                     if w.get('proj_node_flag') == 'Y'
                     and (not proj_id or w.get('proj_id') in (None, '', proj_id))), {})
    sched_opts = next((r for r in tables.get('SCHEDOPTIONS', [])
                       if not proj_id or r.get('proj_id') in (None, '', proj_id)), {})
    data.project = {
        'object_id': proj_id,
        'id': proj.get('proj_short_name'),
        'name': root_wbs.get('wbs_name') or proj.get('proj_short_name'),
        'data_date': _dt(proj.get('last_recalc_date')),
        # The project's current baseline — named even when its rows are not in the file (a
        # P6 XER update export carries only the BASELINE_EXPORT pointer), like the XML's
        # CurrentBaselineProjectObjectId, so the screen can ask for THAT baseline (finding P1).
        'baseline_object_id': proj.get('sum_base_proj_id') or None,
        # The project-root PROJWBS node (proj_node_flag=Y) - kept here, NOT in data.wbs, like the
        # XML's <Project><WBSObjectId> whose top-level <WBS> have no parent (finding P5).
        'wbs_root_id': root_wbs.get('wbs_id') or None,
        # 'Compute Total Float as' (SCHEDOPTIONS.sched_float_type FT_FF / FT_SF / FT_SM) -> the
        # same 'finish' | 'start' | 'smallest' the XML reports (P8).
        'total_float_type': float_basis(sched_opts.get('sched_float_type')),
        'baseline_name': _baseline_name(tables, proj, bl_proj),
        # Project window, read like the XML's <Project> dates (finding P13 - the XER had none, so
        # the Calendar Audit's project window was blank for an XER): Planned Start
        # (plan_start_date = <PlannedStartDate>), Scheduled Finish (scd_end_date =
        # <ScheduledFinishDate>, falling back to Must Finish By like the XML does) and Must
        # Finish By (plan_end_date = <MustFinishByDate>).
        'planned_start': _dt(proj.get('plan_start_date')),
        'scheduled_finish': _dt(proj.get('scd_end_date') or proj.get('plan_end_date')),
        'must_finish_by': _dt(proj.get('plan_end_date')),
        # 'Calendar for scheduling Relationship Lag' (sched_calendar_on_relationship_lag
        # rcal_Predecessor / ...) + the project default calendar (PROJECT.clndr_id = the XML's
        # <ActivityDefaultCalendarObjectId>) - lag_days is counted on it (finding P16).
        'lag_calendar': lag_calendar_basis(sched_opts.get('sched_calendar_on_relationship_lag')),
        'ss_lag_from_early_start': (sched_opts.get('sched_lag_early_start_flag') or 'Y').strip().upper() != 'N',
        'default_calendar_id': proj.get('clndr_id') or None,
    }

    # This project's calendars = global + resource calendars (no proj_id) + its own project
    # calendars - what the XML lists outside <BaselineProject>. The baseline project's calendars
    # go to data.baseline_calendars; another project's (multi-project XER) are held aside and
    # used only if one of this project's activities points at them (findings P11 / P23).
    other_project_cals = {}
    for c in tables.get('CALENDAR', []):
        oid = c.get('clndr_id')
        cproj = c.get('proj_id') or None
        if cproj and proj_id and cproj != proj_id:
            target = data.baseline_calendars if cproj == bl_proj_id else other_project_cals
        else:
            target = data.calendars
        # Read the working week + holidays from clndr_data so working-time math (Planned%,
        # Delay) matches the XML path. Falls back to a bare (whole-day) calendar on any parse
        # miss, preserving the prior behaviour.
        cd = {}
        try:
            cd = parse_clndr_data(c.get('clndr_data'))
        except Exception:
            cd = {}
        target[oid] = Calendar(
            object_id=oid, name=c.get('clndr_name'),
            day_hours=_num(c.get('day_hr_cnt'), 8.0) or 8.0,
            nonworking_days=cd.get('nonworking_days') or set(),
            holidays=cd.get('holidays') or set(),
            added_work_days=cd.get('added_work_days') or set(),
            work_intervals=cd.get('work_intervals') or {},
            exception_intervals=cd.get('exception_intervals') or {},
            weekly_working_days=cd.get('weekly_working_days') or set(),
            # Global / Project / Resource and the default flag, as the XML's <Type>/<IsDefault>
            # (finding P12 - the Calendar Audit's 'Default' role and type column).
            type=CLNDR_TYPE.get(c.get('clndr_type'), c.get('clndr_type') or ''),
            is_default=(c.get('default_flag') or '').strip().upper() == 'Y',
        )

    tf_basis = data.project['total_float_type']

    # Only import WBS nodes belonging to this project. The project-root node (proj_node_flag=Y,
    # the project itself) is NOT a WBS element: P6's XML never lists it as a <WBS> and its
    # top-level WBS have no parent. Skipping it keeps wbs_path / WBS roll-ups / top-level
    # grouping identical to the XML (finding P5: it prefixed every XER path with the project
    # name, added a depth-0 node and collapsed the top-level branches into one).
    root_id = data.project['wbs_root_id']
    for w in tables.get('PROJWBS', []):
        if proj_id and w.get('proj_id') not in (None, '', proj_id):
            continue
        if w.get('proj_node_flag') == 'Y' or (root_id and w.get('wbs_id') == root_id):
            continue
        parent = w.get('parent_wbs_id') or None
        data.wbs[w.get('wbs_id')] = {
            'name': w.get('wbs_name'),
            'parent_object_id': None if (root_id and parent == root_id) else parent,
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

    for t in tables.get('TASK', []):
        # Skip activities from other projects in multi-project XER exports
        if proj_id and t.get('proj_id') not in (None, '', proj_id):
            continue
        oid = t.get('task_id')
        cal = _activity_calendar(data, t.get('clndr_id'), other_project_cals)
        day_hours = cal.day_hours if cal else 8.0
        # float hours snapped to the minute in both formats, so XER == XML to the bit
        tf = minute_hours(_num(t.get('total_float_hr_cnt')))
        ff = minute_hours(_num(t.get('free_float_hr_cnt')))
        tf_days = (tf / day_hours) if tf is not None else None
        ff_days = (ff / day_hours) if ff is not None else None
        if tf is None:
            # P6 left total_float_hr_cnt blank (e.g. an unscheduled / older export): rebuild it
            # exactly as the XML reader does - on the project's 'Compute Total Float as' basis
            # (Finish Float = RLF - REF by default), in working hours on the activity's calendar
            # (finding P9). A Completed activity has no remaining dates -> None, as in P6.
            h = minute_hours(total_float_hours(cal, _dt(t.get('restart_date')), _dt(t.get('reend_date')),
                                               _dt(t.get('rem_late_start_date')),
                                               _dt(t.get('rem_late_end_date')), tf_basis))
            tf_days = (h / day_hours) if h is not None else None
        planned_start = _dt(t.get('target_start_date'))
        planned_finish = _dt(t.get('target_end_date'))
        data.activities[oid] = {
            'object_id': oid,
            'id': t.get('task_code'),
            'name': t.get('task_name'),
            'status': _status(t.get('status_code')),
            'calendar_id': t.get('clndr_id'),
            'wbs_id': t.get('wbs_id'),
            'task_type': TASK_TYPE.get(t.get('task_type'), 'Task'),
            'percent_complete': _pct_complete(t),
            'planned_duration': _num(t.get('target_drtn_hr_cnt'), 0.0),
            'remaining_duration': _num(t.get('remain_drtn_hr_cnt'), 0.0),
            'total_float_days': tf_days,
            # P6's float in working hours - stored, or rebuilt exactly like the XML (P9) - read by
            # ONE Delay rule in both formats (finding F7-D1)
            'tf_from_hours': tf_days is not None,
            'free_float_days': ff_days,   # XER-only: P6's XML carries no float (finding P24)
            'is_critical': (tf_days is not None and tf_days <= 0),
            'constraint_type': _cstr(t.get('cstr_type')),
            'constraint_date': _dt(t.get('cstr_date')),
            'secondary_constraint_type': _cstr(t.get('cstr_type2')),
            'secondary_constraint_date': _dt(t.get('cstr_date2')),
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

    # Dimensions actually assigned to THIS project's activities - the same rule as parser.py (the
    # XML carries only the code types in use); ACTVTYPE lists every type in the file, including
    # other projects' / unassigned ones (finding P18).
    data.activity_code_types = sorted(
        {dim for a in data.activities.values() for dim in a['activity_codes']})

    for r in tables.get('TASKPRED', []):
        succ = r.get('task_id')
        pred = r.get('pred_task_id')
        # Only include relationships whose both endpoints belong to this project
        if succ not in data.activities or pred not in data.activities:
            continue
        # Lag in days on the project's lag calendar (predecessor by default), not always the
        # successor's (finding P16) - identical rule in parser.py.
        day_hours = lag_day_hours(data, pred, succ)
        lag_hr = _num(r.get('lag_hr_cnt'), 0.0) or 0.0
        data.relationships.append({
            'pred_id': pred, 'succ_id': succ,
            'type': PRED_TYPE.get(r.get('pred_type'), 'FS'),
            'lag_days': lag_hr / day_hours,
            'lag_hours': lag_hr,
            'lag_calendar_id': lag_calendar_id(data, pred, succ),
        })
    sort_relationships(data)   # one order for XML and XER (P17)
    sort_calendars(data)       # one calendar order for XML and XER (R2 F7)

    # Resource names (additive) — resolve TASKRSRC assignments to a readable resource name.
    # 'code' is P6's human Resource Id (rsrc_short_name — the short code the planner sees), distinct
    # from the internal rsrc_id; the UI shows the code so the table matches P6.
    # Type and Unit of Measure read with the SAME vocabulary / rule as parser.py (finding P21).
    uom = {u.get('unit_id'): resource_unit(u.get('unit_abbrev'), u.get('unit_name'))
           for u in tables.get('UMEASURE', []) if u.get('unit_id')}
    for rr in tables.get('RSRC', []):
        rid = rr.get('rsrc_id')
        if rid:
            unit, unit_name = uom.get(rr.get('unit_id'), (None, None))
            data.resources[rid] = {'name': rr.get('rsrc_name') or rr.get('rsrc_short_name') or rid,
                                   'code': rr.get('rsrc_short_name'),
                                   'type': resource_type_label(rr.get('rsrc_type')),
                                   'unit': unit, 'unit_name': unit_name}

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
    # Any other baseline copy of a project in this file (orig_proj_id = that project - the XER
    # twin of the XML's <BaselineProject><OriginalProjectObjectId>) is not the current project
    # either, whichever row comes first (finding F10: a file carrying several baselines).
    baselines |= {r.get('proj_id') for r in rows
                  if r.get('orig_proj_id') and r.get('orig_proj_id') != r.get('proj_id')
                  and r.get('orig_proj_id') in ids}
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
    data.baseline_bac_by_code = dict(bac_by_code)
    for oid, a in data.activities.items():
        if a.get('id') in bac_by_code:
            data.baseline_bac_by_activity[oid] = bac_by_code[a['id']]
