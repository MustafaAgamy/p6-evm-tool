from datetime import datetime
from p6_evm.parser import ScheduleData, full_wbs_path
from p6_evm.calendars import Calendar

TASK_TYPE = {'TT_Task': 'Task', 'TT_Mile': 'StartMilestone', 'TT_FinMile': 'FinishMilestone',
             'TT_LOE': 'LOE', 'TT_WBS': 'WBSSummary', 'TT_Rsrc': 'ResourceDependent'}
PRED_TYPE = {'PR_FS': 'FS', 'PR_SS': 'SS', 'PR_FF': 'FF', 'PR_SF': 'SF'}


def _read_text(path):
    for enc in ('cp1252', 'utf-8'):
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
    data.project = {
        'object_id': proj.get('proj_id'),
        'id': proj.get('proj_short_name'),
        'name': proj.get('proj_short_name'),
        'data_date': _dt(proj.get('last_recalc_date')),
        'baseline_object_id': None,
    }

    for c in tables.get('CALENDAR', []):
        oid = c.get('clndr_id')
        data.calendars[oid] = Calendar(
            object_id=oid, name=c.get('clndr_name'),
            day_hours=_num(c.get('day_hr_cnt'), 8.0) or 8.0,
        )

    for w in tables.get('PROJWBS', []):
        data.wbs[w.get('wbs_id')] = {
            'name': w.get('wbs_name'),
            'parent_object_id': w.get('parent_wbs_id') or None,
        }

    for t in tables.get('TASK', []):
        oid = t.get('task_id')
        cal = data.calendars.get(t.get('clndr_id'))
        day_hours = cal.day_hours if cal else 8.0
        tf = _num(t.get('total_float_hr_cnt'))
        ff = _num(t.get('free_float_hr_cnt'))
        tf_days = (tf / day_hours) if tf is not None else None
        ff_days = (ff / day_hours) if ff is not None else None
        data.activities[oid] = {
            'object_id': oid,
            'id': t.get('task_code'),
            'name': t.get('task_name'),
            'status': t.get('status_code'),
            'calendar_id': t.get('clndr_id'),
            'wbs_id': t.get('wbs_id'),
            'task_type': TASK_TYPE.get(t.get('task_type'), 'Task'),
            'percent_complete': _num(t.get('phys_complete_pct'), 0.0) or 0.0,
            'planned_duration': _num(t.get('target_drtn_hr_cnt'), 0.0),
            'total_float_days': tf_days,
            'free_float_days': ff_days,
            'is_critical': (tf_days is not None and tf_days <= 0),
            'constraint_type': t.get('cstr_type') or None,
            'constraint_date': _dt(t.get('cstr_date')),
            'activity_codes': {},
            'wbs_path': full_wbs_path(t.get('wbs_id'), data.wbs),
            # EVM-facing date fields absent in this minimal XER mapping:
            'planned_start': None, 'planned_finish': None,
            'remaining_early_start': None, 'remaining_early_finish': None,
            'remaining_late_start': None, 'remaining_late_finish': None,
        }

    for r in tables.get('TASKPRED', []):
        succ = r.get('task_id')
        pred = r.get('pred_task_id')
        day_hours = 8.0
        cal = data.calendars.get((data.activities.get(succ) or {}).get('calendar_id'))
        if cal:
            day_hours = cal.day_hours
        lag_hr = _num(r.get('lag_hr_cnt'), 0.0) or 0.0
        data.relationships.append({
            'pred_id': pred, 'succ_id': succ,
            'type': PRED_TYPE.get(r.get('pred_type'), 'FS'),
            'lag_days': lag_hr / day_hours,
        })

    for ra in tables.get('TASKRSRC', []):
        tid = ra.get('task_id')
        if not tid:
            continue
        bac = _num(ra.get('target_cost'), 0.0) or 0.0
        ac = (_num(ra.get('act_reg_cost'), 0.0) or 0.0) + (_num(ra.get('act_ot_cost'), 0.0) or 0.0)
        data.bac_by_activity[tid] = data.bac_by_activity.get(tid, 0.0) + bac
        data.ac_by_activity[tid] = data.ac_by_activity.get(tid, 0.0) + ac

    return data
