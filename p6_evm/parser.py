import re
import xml.etree.ElementTree as ET
from datetime import datetime

from p6_evm.calendars import Calendar, signed_working_days, hhmmss_to_min

DATETIME_FMT = '%Y-%m-%dT%H:%M:%S'

XML_TASK_TYPE = {
    'Task Dependent': 'Task', 'Resource Dependent': 'ResourceDependent',
    'Level of Effort': 'LOE', 'Start Milestone': 'StartMilestone',
    'Finish Milestone': 'FinishMilestone', 'WBS Summary': 'WBSSummary',
}
XML_REL_TYPE = {
    'Finish to Start': 'FS', 'Start to Start': 'SS',
    'Finish to Finish': 'FF', 'Start to Finish': 'SF',
}


def parse_datetime(s):
    if not s:
        return None
    return datetime.strptime(s, DATETIME_FMT)


def parse_float(s, default=0.0):
    if s in (None, ''):
        return default
    return float(s)


class ScheduleData:
    def __init__(self):
        self.calendars = {}
        self.project = {}
        self.wbs = {}              # ObjectId -> {Name, ParentObjectId}
        self.activities = {}       # ObjectId -> activity dict
        self.baseline_by_id = {}   # activity Id (code) -> {PlannedStartDate, PlannedFinishDate}
        self.bac_by_activity = {}  # ActivityObjectId -> planned cost (current update)
        self.baseline_bac_by_activity = {}  # ActivityObjectId -> BASELINE budget (BAC) — P6's cost basis for PV/EV/%-rollup
        self.ac_by_activity = {}   # ActivityObjectId -> actual cost
        self.relationships = []    # list of {pred_id, succ_id, type, lag_days, lag_hours}
        self.activity_code_types = []  # available activity-code dimensions, e.g. ['Type of Works', ...]


def full_wbs_path(wbs_id, wbs_map):
    """Root-first WBS path string, e.g. 'Tower 33 > Foundation > Raft'."""
    names = []
    seen = set()
    current = wbs_id
    while current and current not in seen:
        seen.add(current)
        node = wbs_map.get(current)
        if not node:
            break
        if node.get('name'):
            names.append(node['name'])
        current = node.get('parent_object_id')
    return ' > '.join(reversed(names))


def _detect_namespace(path):
    with open(path, encoding='utf-8') as f:
        head = f.read(4000)
    m = re.search(r'xmlns="([^"]+)"', head)
    return m.group(1) if m else ''


def parse_file(path) -> ScheduleData:
    if path.lower().endswith('.xer'):
        from p6_evm.xer import parse_xer
        return parse_xer(path)
    # ---- existing XML parsing continues unchanged below ----
    ns_uri = _detect_namespace(path)
    ns = f'{{{ns_uri}}}' if ns_uri else ''

    def tag(name):
        return f'{ns}{name}'

    def text(el, name):
        child = el.find(tag(name))
        if child is None or child.text is None:
            return None
        return child.text

    root = ET.parse(path).getroot()
    data = ScheduleData()

    # ── Activity-code lookups (XML equivalent of the XER path in xer.py) ──────
    # <ActivityCodeType> defines a dimension (ObjectId -> Name); <ActivityCode>
    # defines a value (ObjectId -> Description, falling back to CodeValue); each
    # activity carries <Code><TypeObjectId>/<ValueObjectId></Code> assignments.
    _code_type_name = {}
    for t_el in root.iter(tag('ActivityCodeType')):
        oid = text(t_el, 'ObjectId')
        nm = text(t_el, 'Name')
        if oid and nm:
            _code_type_name[oid] = nm
    _code_value = {}
    for v_el in root.iter(tag('ActivityCode')):
        oid = text(v_el, 'ObjectId')
        val = text(v_el, 'Description') or text(v_el, 'CodeValue')
        if oid and val:
            _code_value[oid] = val

    def _activity_codes(act_el):
        codes = {}
        for code_el in act_el.findall(tag('Code')):
            tid = text(code_el, 'TypeObjectId')
            vid = text(code_el, 'ValueObjectId')
            if tid and vid:
                dim = _code_type_name.get(tid)
                val = _code_value.get(vid)
                if dim and val:
                    codes[dim] = val
        return codes

    # Read EVERY <Calendar> in the tree, not just root-level ones: P6 nests
    # project calendars (Type=Project) inside <Project> and baseline calendars
    # inside <BaselineProject>. Missing them left activities' calendars unresolved
    # (e.g. "6 Days Per Week" used by ~all activities) → wrong working-time and a
    # blank Delay. Keyed by ObjectId; first definition wins so a baseline calendar
    # can never clobber a live one that shares an id.
    def _work_intervals(el):
        """(start_min, end_min) pairs from an element's <WorkTime> children."""
        out = []
        for wt in el.findall(tag('WorkTime')):
            sm = hhmmss_to_min(text(wt, 'Start'))
            em = hhmmss_to_min(text(wt, 'Finish'))
            if sm is not None and em is not None and em > sm:
                out.append((sm, em))
        return out

    for cal_el in root.iter(tag('Calendar')):
        object_id = text(cal_el, 'ObjectId')
        if object_id in data.calendars:
            continue
        name = text(cal_el, 'Name')
        nonworking = set()
        work_intervals = {}
        ww = cal_el.find(tag('StandardWorkWeek'))
        if ww is not None:
            for day_el in ww.findall(tag('StandardWorkHours')):
                dow = text(day_el, 'DayOfWeek')
                ivs = _work_intervals(day_el)
                if ivs:
                    work_intervals[dow] = ivs      # working day with its intraday hours
                else:
                    nonworking.add(dow)
        holidays = set()
        added_work = set()
        exception_intervals = {}
        exc = cal_el.find(tag('HolidayOrExceptions'))
        if exc is not None:
            for item in exc.findall(tag('HolidayOrException')):
                d = parse_datetime(text(item, 'Date'))
                if d is None:
                    continue
                ivs = _work_intervals(item)
                if ivs:
                    added_work.add(d.date())
                    exception_intervals[d.date()] = ivs
                else:
                    holidays.add(d.date())
        hours_raw = text(cal_el, 'HoursPerDay')
        cal_type = (text(cal_el, 'Type') or '').replace('Calendar', '').strip()  # 'Global'/'Project'/'Resource'
        is_default = (text(cal_el, 'IsDefault') or '').strip().lower() in ('true', '1', 'yes')
        data.calendars[object_id] = Calendar(
            object_id=object_id, name=name, nonworking_days=nonworking,
            holidays=holidays, added_work_days=added_work,
            day_hours=parse_float(hours_raw, 8.0) or 8.0,
            work_intervals=work_intervals, exception_intervals=exception_intervals,
            type=cal_type, is_default=is_default,
        )

    project_el = root.find(tag('Project'))
    baseline_el = root.find(tag('BaselineProject'))

    data.project = {
        'object_id': text(project_el, 'ObjectId'),
        'id': text(project_el, 'Id'),
        'name': text(project_el, 'Name'),
        'data_date': parse_datetime(text(project_el, 'DataDate')),
        'baseline_object_id': text(project_el, 'CurrentBaselineProjectObjectId'),
        # Calendar Audit: project window (additive). P6 exports vary — take the first present.
        'planned_start': parse_datetime(
            text(project_el, 'PlannedStartDate') or text(project_el, 'StartDate')
            or text(project_el, 'AnticipatedStartDate')),
        'scheduled_finish': parse_datetime(
            text(project_el, 'ScheduledFinishDate') or text(project_el, 'FinishDate')
            or text(project_el, 'AnticipatedFinishDate') or text(project_el, 'MustFinishByDate')),
    }

    for wbs_el in project_el.findall(tag('WBS')):
        object_id = text(wbs_el, 'ObjectId')
        data.wbs[object_id] = {
            'name': text(wbs_el, 'Name'),
            'parent_object_id': text(wbs_el, 'ParentObjectId'),
        }

    baseline_bac_by_id = {}   # baseline activity Id (code) -> baseline BAC; mapped to object ids below
    if baseline_el is not None:
        bl_oid_to_id = {}     # baseline ActivityObjectId -> activity Id, to link baseline costs to activities
        for act_el in baseline_el.findall(tag('Activity')):
            activity_id = text(act_el, 'Id')
            if not activity_id:
                continue
            bl_oid_to_id[text(act_el, 'ObjectId')] = activity_id
            data.baseline_by_id[activity_id] = {
                'planned_start': parse_datetime(text(act_el, 'PlannedStartDate')),
                'planned_finish': parse_datetime(text(act_el, 'PlannedFinishDate')),
            }
        # Baseline budget (BAC) per activity — P6 anchors Planned Value and WBS %-rollup to
        # the baseline cost, not the current update's cost loading. Sum the baseline project's
        # resource assignments and key them back to the activity Id.
        for ra_el in baseline_el.findall(tag('ResourceAssignment')):
            bl_aid = bl_oid_to_id.get(text(ra_el, 'ActivityObjectId'))
            if not bl_aid:
                continue
            baseline_bac_by_id[bl_aid] = baseline_bac_by_id.get(bl_aid, 0.0) + parse_float(text(ra_el, 'PlannedCost'))

    for act_el in project_el.findall(tag('Activity')):
        object_id = text(act_el, 'ObjectId')
        data.activities[object_id] = {
            'object_id': object_id,
            'id': text(act_el, 'Id'),
            'name': text(act_el, 'Name'),
            'status': text(act_el, 'Status'),
            'calendar_id': text(act_el, 'CalendarObjectId'),
            'wbs_id': text(act_el, 'WBSObjectId'),
            'percent_complete': parse_float(text(act_el, 'PercentComplete')),
            'planned_duration': parse_float(text(act_el, 'PlannedDuration')),
            'remaining_duration': parse_float(text(act_el, 'RemainingDuration')),
            'planned_start': parse_datetime(text(act_el, 'PlannedStartDate')),
            'planned_finish': parse_datetime(text(act_el, 'PlannedFinishDate')),
            'remaining_early_start': parse_datetime(text(act_el, 'RemainingEarlyStartDate')),
            'remaining_early_finish': parse_datetime(text(act_el, 'RemainingEarlyFinishDate')),
            'remaining_late_start': parse_datetime(text(act_el, 'RemainingLateStartDate')),
            'remaining_late_finish': parse_datetime(text(act_el, 'RemainingLateFinishDate')),
        }
        # Audit fields — additive, never alter EVM keys above
        act = data.activities[object_id]
        act['task_type'] = XML_TASK_TYPE.get(text(act_el, 'Type'), 'Task')
        cal = data.calendars.get(act['calendar_id'])
        day_hours = cal.day_hours if cal else 8.0
        tf_hours_raw = text(act_el, 'TotalFloatHours')
        ff_hours_raw = text(act_el, 'FreeFloatHours')
        tf_hours = parse_float(tf_hours_raw, None) if tf_hours_raw else None
        ff_hours = parse_float(ff_hours_raw, None) if ff_hours_raw else None
        if tf_hours is not None:
            act['total_float_days'] = tf_hours / day_hours
            act['tf_from_hours'] = True
        else:
            act['total_float_days'] = (
                signed_working_days(cal, act['remaining_early_start'], act['remaining_late_start'])
                if (cal and act['remaining_early_start'] and act['remaining_late_start']) else None
            )
            act['tf_from_hours'] = False   # reconstructed — Delay recomputed boundary-correct
        act['free_float_days'] = (ff_hours / day_hours) if ff_hours is not None else None
        act['is_critical'] = (act['total_float_days'] is not None and act['total_float_days'] <= 0)
        act['constraint_type'] = text(act_el, 'PrimaryConstraintType')
        act['constraint_date'] = parse_datetime(text(act_el, 'PrimaryConstraintDate'))
        act['activity_codes'] = _activity_codes(act_el)
        act['wbs_path'] = full_wbs_path(act['wbs_id'], data.wbs)
        # Actual progress dates — needed by the Out-of-Sequence audit to compare
        # execution against network logic. Additive; EVM keys above are untouched.
        act['actual_start'] = parse_datetime(text(act_el, 'ActualStartDate'))
        act['actual_finish'] = parse_datetime(text(act_el, 'ActualFinishDate'))

    # Dimensions actually assigned to this project's activities (for the gap dropdown)
    data.activity_code_types = sorted(
        {dim for a in data.activities.values() for dim in a['activity_codes']})

    for ra_el in project_el.findall(tag('ResourceAssignment')):
        activity_id = text(ra_el, 'ActivityObjectId')
        if not activity_id:
            continue
        planned_cost = parse_float(text(ra_el, 'PlannedCost'))
        actual_cost = parse_float(text(ra_el, 'ActualCost'))
        data.bac_by_activity[activity_id] = data.bac_by_activity.get(activity_id, 0.0) + planned_cost
        data.ac_by_activity[activity_id] = data.ac_by_activity.get(activity_id, 0.0) + actual_cost

    # Link baseline BAC (keyed by activity Id) to each current activity's ObjectId, so metrics
    # can weight PV/EV/%-rollup by the baseline budget like P6 does. Only set when the baseline
    # actually carries cost — otherwise metrics falls back to the current BAC (e.g. bare XER).
    if baseline_bac_by_id:
        for oid, act in data.activities.items():
            bl_bac = baseline_bac_by_id.get(act['id'])
            if bl_bac is not None:
                data.baseline_bac_by_activity[oid] = bl_bac

    for rel_el in project_el.findall(tag('Relationship')):
        pred = text(rel_el, 'PredecessorActivityObjectId')
        succ = text(rel_el, 'SuccessorActivityObjectId')
        if not pred or not succ:
            continue
        cal = data.calendars.get(data.activities.get(succ, {}).get('calendar_id'))
        day_hours = cal.day_hours if cal else 8.0
        lag_hours = parse_float(text(rel_el, 'Lag'), 0.0)
        data.relationships.append({
            'pred_id': pred, 'succ_id': succ,
            'type': XML_REL_TYPE.get(text(rel_el, 'Type'), 'FS'),
            'lag_days': (lag_hours or 0.0) / day_hours,
            'lag_hours': lag_hours or 0.0,
        })

    return data
