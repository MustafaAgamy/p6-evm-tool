from datetime import datetime
from p6_evm.parser import ScheduleData, full_wbs_path
from p6_evm.calendars import Calendar

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


def parse_xer(path):
    tables = read_xer_tables(path)
    data = ScheduleData()

    proj = (tables.get('PROJECT') or [{}])[0]
    proj_id = proj.get('proj_id')

    # Derive the human-readable project name from this project's root WBS node (proj_node_flag='Y')
    root_wbs = next((w for w in tables.get('PROJWBS', [])
                     if w.get('proj_node_flag') == 'Y'
                     and (not proj_id or w.get('proj_id') in (None, '', proj_id))), {})
    data.project = {
        'object_id': proj_id,
        'id': proj.get('proj_short_name'),
        'name': root_wbs.get('wbs_name') or proj.get('proj_short_name'),
        'data_date': _dt(proj.get('last_recalc_date')),
        'baseline_object_id': None,
    }

    for c in tables.get('CALENDAR', []):
        oid = c.get('clndr_id')
        data.calendars[oid] = Calendar(
            object_id=oid, name=c.get('clndr_name'),
            day_hours=_num(c.get('day_hr_cnt'), 8.0) or 8.0,
        )

    # Only import WBS nodes belonging to this project
    for w in tables.get('PROJWBS', []):
        if proj_id and w.get('proj_id') not in (None, '', proj_id):
            continue
        data.wbs[w.get('wbs_id')] = {
            'name': w.get('wbs_name'),
            'parent_object_id': w.get('parent_wbs_id') or None,
        }

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
            'percent_complete': (_num(t.get('phys_complete_pct'), 0.0) or 0.0) / 100.0,
            'planned_duration': _num(t.get('target_drtn_hr_cnt'), 0.0),
            'total_float_days': tf_days,
            'free_float_days': ff_days,
            'is_critical': (tf_days is not None and tf_days <= 0),
            'constraint_type': t.get('cstr_type') or None,
            'constraint_date': _dt(t.get('cstr_date')),
            'activity_codes': {},
            'wbs_path': full_wbs_path(t.get('wbs_id'), data.wbs),
            'planned_start': planned_start,
            'planned_finish': planned_finish,
            'remaining_early_start': _dt(t.get('remain_early_start_date')),
            'remaining_early_finish': _dt(t.get('remain_early_end_date')),
            'remaining_late_start': _dt(t.get('remain_late_start_date')),
            'remaining_late_finish': _dt(t.get('remain_late_end_date')),
        }
        # Populate baseline_by_id so EVM compute() can derive planned percentages
        task_code = t.get('task_code')
        if task_code:
            data.baseline_by_id[task_code] = {
                'planned_start': planned_start,
                'planned_finish': planned_finish,
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
        })

    for ra in tables.get('TASKRSRC', []):
        tid = ra.get('task_id')
        if not tid or tid not in data.activities:
            continue
        bac = _num(ra.get('target_cost'), 0.0) or 0.0
        ac = (_num(ra.get('act_reg_cost'), 0.0) or 0.0) + (_num(ra.get('act_ot_cost'), 0.0) or 0.0)
        data.bac_by_activity[tid] = data.bac_by_activity.get(tid, 0.0) + bac
        data.ac_by_activity[tid] = data.ac_by_activity.get(tid, 0.0) + ac

    return data
