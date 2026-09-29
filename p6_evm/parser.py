import re
import xml.etree.ElementTree as ET
from datetime import datetime

from p6_evm.calendars import (Calendar, hhmmss_to_min, float_basis, total_float_hours,
                              lag_calendar_basis)

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


def _res_type_label(raw):
    """Human resource-type label from P6's ResourceType field. P6 uses Labor / Nonlabor /
    Material; return a plain word (Labour / Equipment / Material) or None when absent so the
    UI shows an honest '—' rather than a fabricated type."""
    if not raw:
        return None
    r = str(raw).strip().lower()
    if r.startswith('labor') or r.startswith('labour'):
        return 'Labour'
    if r.startswith('nonlabor') or r.startswith('non-labor') or r.startswith('nonlabour'):
        return 'Equipment'
    if r.startswith('material'):
        return 'Material'
    return str(raw).strip()


class ScheduleData:
    def __init__(self):
        self.calendars = {}
        # The embedded baseline project's OWN calendars (XML <BaselineProject><Calendar>, XER
        # CALENDAR rows of the baseline project) - kept OUT of `calendars`, which lists only the
        # current project's calendars (global + project + resource) the way P6 shows them, so the
        # calendar count / Calendar Audit never see baseline copies as unused project calendars
        # (findings P11 / P23). ObjectId -> Calendar.
        self.baseline_calendars = {}
        self.project = {}
        self.wbs = {}              # ObjectId -> {Name, ParentObjectId}
        self.activities = {}       # ObjectId -> activity dict
        self.baseline_by_id = {}   # activity Id (code) -> {PlannedStartDate, PlannedFinishDate}
        # WHERE baseline_by_id came from — ONE vocabulary for both formats (R4):
        #   'embedded' — the file carries its baseline project (XML <BaselineProject>)
        #   'self'     — it does not, so the file's own Planned dates stand in (approximate)
        #   'attached' — a separate baseline file was applied (p6_evm.baseline.resolve_baseline)
        self.baseline_source = None
        self.bac_by_activity = {}  # ActivityObjectId -> planned cost (current update)
        self.baseline_bac_by_activity = {}  # ActivityObjectId -> BASELINE budget (BAC) — P6's cost basis for PV/EV/%-rollup
        self.ac_by_activity = {}   # ActivityObjectId -> actual cost
        self.relationships = []    # list of {pred_id, succ_id, type, lag_days, lag_hours}
        self.activity_code_types = []  # available activity-code dimensions, e.g. ['Type of Works', ...]
        # Resource-loading detail (additive; populated only when the export carries it — a bare
        # XER/XML has none). Used by the optional Baseline Revision resource/cost comparison;
        # never read by EVM/metrics, which keep using bac_by_activity / ac_by_activity.
        self.resources = {}                # resource ObjectId -> {'name', 'code' (P6 Id), 'type'}
        self.assignments_by_activity = {}  # activity ObjectId -> [{resource_id, resource_code, resource_name,
                                           #   resource_type, budget_units, actual_units, budget_cost, rate}]


def _activity_calendar(data, cid, spare=None):
    """The Calendar a CURRENT activity runs on. Normally in data.calendars; should a file ever
    assign a current activity a calendar that is defined only with the baseline (or, in a
    multi-project XER, with another project), that calendar is promoted into data.calendars -
    it is then genuinely used by this project - rather than leaving the activity without one."""
    if not cid:
        return None
    cal = data.calendars.get(cid)
    if cal is None:
        cal = data.baseline_calendars.get(cid) or (spare or {}).get(cid)
        if cal is not None:
            data.calendars[cid] = cal
    return cal


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


def lag_calendar_id(data, pred_oid, succ_oid):
    """The calendar a relationship's lag is counted on, per the project's 'Calendar for
    scheduling Relationship Lag' option (data.project['lag_calendar'], read from the XML's
    <RelationshipLagCalendar> / the XER's sched_calendar_on_relationship_lag): the predecessor's
    (P6's default), the successor's, the project default calendar, or None for a 24-hour day."""
    project = getattr(data, 'project', None) or {}
    basis = project.get('lag_calendar') or 'predecessor'
    if basis == '24h':
        return None
    if basis == 'project':
        return project.get('default_calendar_id')
    oid = succ_oid if basis == 'successor' else pred_oid
    return ((getattr(data, 'activities', None) or {}).get(oid) or {}).get('calendar_id')


def lag_day_hours(data, pred_oid, succ_oid):
    """Hours per day of the lag calendar - lag_days = lag_hours / this, in BOTH parsers (finding
    P16: it used the successor's calendar whatever the project option said). 24 for the 24-hour
    option; 8 when the calendar is unknown (unchanged fallback)."""
    project = getattr(data, 'project', None) or {}
    if (project.get('lag_calendar') or 'predecessor') == '24h':
        return 24.0
    cal = (getattr(data, 'calendars', None) or {}).get(lag_calendar_id(data, pred_oid, succ_oid))
    dh = getattr(cal, 'day_hours', None) if cal is not None else None
    return dh if dh and dh > 0 else 8.0


def _schedule_option(project_el, name):
    """A <Project><ScheduleOptions> value (namespace-agnostic), or None."""
    if project_el is None:
        return None
    for el in project_el:
        if el.tag.rsplit('}', 1)[-1] == 'ScheduleOptions':
            for child in el:
                if child.tag.rsplit('}', 1)[-1] == name:
                    return child.text
    return None


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
        """(start_min, end_min) pairs from an element's <WorkTime> children.

        P6 XML writes a shift's LAST working minute as its <Finish> (a shift to 12:00 is
        11:59:00, to 18:30 is 18:29:00, a 24-hour day 23:59:00) where the XER writes the end
        (f|12:00, f|18:30, f|00:00). Read it back as the end - one minute on, capped at 24:00 -
        so XML hours match the XER and P6 (finding P10; needed for exact float hours, P8)."""
        out = []
        for wt in el.findall(tag('WorkTime')):
            sm = hhmmss_to_min(text(wt, 'Start'))
            em = hhmmss_to_min(text(wt, 'Finish'))
            if em is not None and em % 15 == 14:
                em = min(em + 1, 1440)
            if sm is not None and em is not None and em > sm:
                out.append((sm, em))
        return out

    # Calendars nested in a <BaselineProject> belong to the baseline, not to this project's
    # calendar list (finding P11) - they go to data.baseline_calendars, like the XER reader does
    # with the baseline project's CALENDAR rows.
    _bl_cal_els = {id(c) for bp in root.iter(tag('BaselineProject')) for c in bp.iter(tag('Calendar'))}

    for cal_el in root.iter(tag('Calendar')):
        object_id = text(cal_el, 'ObjectId')
        target = data.baseline_calendars if id(cal_el) in _bl_cal_els else data.calendars
        if object_id in target:
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
        target[object_id] = Calendar(
            object_id=object_id, name=name, nonworking_days=nonworking,
            holidays=holidays, added_work_days=added_work,
            day_hours=parse_float(hours_raw, 8.0) or 8.0,
            work_intervals=work_intervals, exception_intervals=exception_intervals,
            # The weekdays that carry work times - filled for BOTH formats (the XER reader takes
            # them from clndr_data), 24-hour days included (finding P12).
            weekly_working_days=set(work_intervals),
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
        # The project's own root WBS node (P6 <Project><WBSObjectId>; its top-level <WBS> have a
        # nil ParentObjectId) - same key as xer.py, which keeps that node OUT of data.wbs (P5).
        'wbs_root_id': text(project_el, 'WBSObjectId'),
        # 'Compute Total Float as' (ScheduleOptions) -> 'finish' | 'start' | 'smallest' - the basis
        # the float is reconstructed on, since P6 XML writes no activity float (P8).
        'total_float_type': float_basis(_schedule_option(project_el, 'ComputeTotalFloatType')),
        # The embedded baseline's name (None when the file does not carry it) — same key as xer.py.
        'baseline_name': text(baseline_el, 'Name') if baseline_el is not None else None,
        # Calendar Audit: project window (additive). P6 exports vary — take the first present.
        'planned_start': parse_datetime(
            text(project_el, 'PlannedStartDate') or text(project_el, 'StartDate')
            or text(project_el, 'AnticipatedStartDate')),
        'scheduled_finish': parse_datetime(
            text(project_el, 'ScheduledFinishDate') or text(project_el, 'FinishDate')
            or text(project_el, 'AnticipatedFinishDate') or text(project_el, 'MustFinishByDate')),
        # The project's Must Finish By date (P6 Project > Dates) - the XER's PROJECT.plan_end_date
        # (finding P13: read by neither parser before).
        'must_finish_by': parse_datetime(text(project_el, 'MustFinishByDate')),
        # 'Calendar for scheduling Relationship Lag' + the project default calendar it may name,
        # so lag_days is counted on the calendar P6 uses (finding P16) - same keys in xer.py.
        'lag_calendar': lag_calendar_basis(_schedule_option(project_el, 'RelationshipLagCalendar')),
        'default_calendar_id': text(project_el, 'ActivityDefaultCalendarObjectId'),
    }

    tf_basis = data.project['total_float_type']

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
        cal = _activity_calendar(data, act['calendar_id'])
        day_hours = cal.day_hours if cal else 8.0
        tf_hours_raw = text(act_el, 'TotalFloatHours')
        ff_hours_raw = text(act_el, 'FreeFloatHours')
        tf_hours = parse_float(tf_hours_raw, None) if tf_hours_raw else None
        ff_hours = parse_float(ff_hours_raw, None) if ff_hours_raw else None
        if tf_hours is not None:
            act['total_float_days'] = tf_hours / day_hours
            act['tf_from_hours'] = True
        else:
            # P6 XML writes no activity float: rebuild it exactly as P6 computes it - on the
            # project's 'Compute Total Float as' basis (Finish Float = RLF - REF by default), in
            # working HOURS on the activity's calendar, / hours-per-day - so it equals the XER's
            # stored total_float_hr_cnt (finding P8; was whole days of START float).
            h = total_float_hours(cal, act['remaining_early_start'], act['remaining_early_finish'],
                                  act['remaining_late_start'], act['remaining_late_finish'], tf_basis)
            act['total_float_days'] = (h / day_hours) if h is not None else None
            act['tf_from_hours'] = False   # reconstructed — Delay recomputed boundary-correct
        act['free_float_days'] = (ff_hours / day_hours) if ff_hours is not None else None
        act['is_critical'] = (act['total_float_days'] is not None and act['total_float_days'] <= 0)
        act['constraint_type'] = text(act_el, 'PrimaryConstraintType')
        act['constraint_date'] = parse_datetime(text(act_el, 'PrimaryConstraintDate'))
        act['secondary_constraint_type'] = text(act_el, 'SecondaryConstraintType')
        act['secondary_constraint_date'] = parse_datetime(text(act_el, 'SecondaryConstraintDate'))
        act['activity_codes'] = _activity_codes(act_el)
        act['wbs_path'] = full_wbs_path(act['wbs_id'], data.wbs)
        # Actual progress dates — needed by the Out-of-Sequence audit to compare
        # execution against network logic. Additive; EVM keys above are untouched.
        act['actual_start'] = parse_datetime(text(act_el, 'ActualStartDate'))
        act['actual_finish'] = parse_datetime(text(act_el, 'ActualFinishDate'))

    # Dimensions actually assigned to this project's activities (for the gap dropdown)
    data.activity_code_types = sorted(
        {dim for a in data.activities.values() for dim in a['activity_codes']})

    # Resource names (additive) — resources sit at document root in P6 XML. Best-effort:
    # any export without them simply yields no resource comparison.
    for res_el in root.iter(tag('Resource')):
        rid = text(res_el, 'ObjectId')
        if rid:
            # 'code' is P6's human Resource Id (the short code the planner sees, e.g. "LAB-01") —
            # distinct from the internal ObjectId. Display uses the code; ObjectId stays the key.
            data.resources[rid] = {'name': text(res_el, 'Name') or text(res_el, 'Id') or rid,
                                   'code': text(res_el, 'Id'),
                                   'type': _res_type_label(text(res_el, 'ResourceType'))}

    for ra_el in project_el.findall(tag('ResourceAssignment')):
        activity_id = text(ra_el, 'ActivityObjectId')
        if not activity_id:
            continue
        planned_cost = parse_float(text(ra_el, 'PlannedCost'))
        actual_cost = parse_float(text(ra_el, 'ActualCost'))
        data.bac_by_activity[activity_id] = data.bac_by_activity.get(activity_id, 0.0) + planned_cost
        data.ac_by_activity[activity_id] = data.ac_by_activity.get(activity_id, 0.0) + actual_cost
        # Per-assignment resource detail (additive; independent of the cost sums above).
        rid = text(ra_el, 'ResourceObjectId')
        data.assignments_by_activity.setdefault(activity_id, []).append({
            'resource_id': rid,
            'resource_code': (data.resources.get(rid) or {}).get('code'),   # P6 human Resource Id
            'resource_name': (data.resources.get(rid) or {}).get('name'),
            'resource_type': (data.resources.get(rid) or {}).get('type'),
            'budget_units': parse_float(text(ra_el, 'PlannedUnits')),
            'actual_units': parse_float(text(ra_el, 'ActualUnits')),
            'budget_cost': planned_cost,
            'rate': parse_float(text(ra_el, 'PricePerUnit'), None),
        })

    # Link baseline BAC (keyed by activity Id) to each current activity's ObjectId, so metrics
    # can weight PV/EV/%-rollup by the baseline budget like P6 does. Only set when the baseline
    # actually carries cost — otherwise metrics falls back to the current BAC (e.g. bare XER).
    if baseline_bac_by_id:
        for oid, act in data.activities.items():
            bl_bac = baseline_bac_by_id.get(act['id'])
            if bl_bac is not None:
                data.baseline_bac_by_activity[oid] = bl_bac

    # No baseline inside the file: stand in the activities' own Planned dates, exactly as the XER
    # reader does (xer.py), and SAY so via baseline_source — so an XML and an XER exported without
    # their baseline give the same (approximate) result instead of XML zero / XER numbers (R4).
    if data.baseline_by_id:
        data.baseline_source = 'embedded'
    else:
        for act in data.activities.values():
            if act.get('id'):
                data.baseline_by_id[act['id']] = {'planned_start': act.get('planned_start'),
                                                  'planned_finish': act.get('planned_finish')}
        data.baseline_source = 'self'

    for rel_el in project_el.findall(tag('Relationship')):
        pred = text(rel_el, 'PredecessorActivityObjectId')
        succ = text(rel_el, 'SuccessorActivityObjectId')
        if not pred or not succ:
            continue
        # Lag in days on the project's lag calendar (predecessor by default), not always the
        # successor's (finding P16) - identical rule in xer.py.
        day_hours = lag_day_hours(data, pred, succ)
        lag_hours = parse_float(text(rel_el, 'Lag'), 0.0)
        data.relationships.append({
            'pred_id': pred, 'succ_id': succ,
            'type': XML_REL_TYPE.get(text(rel_el, 'Type'), 'FS'),
            'lag_days': (lag_hours or 0.0) / day_hours,
            'lag_hours': lag_hours or 0.0,
            'lag_calendar_id': lag_calendar_id(data, pred, succ),
        })

    return data
