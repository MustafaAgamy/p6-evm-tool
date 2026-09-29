"""XER == XML parity harness (R4) at the parser level.

ONE tiny schedule is described once below (SPEC) and written out twice, exactly the way Primavera
P6 writes each format:

  * XML  - P6 API business objects: <Calendar> work times end on the LAST working minute
           (a 08:00-12:00 shift is written 08:00:00-11:59:00, 24 h is 00:00:00-23:59:00), the
           baseline is embedded as <BaselineProject>, NO float fields on <Activity>, status /
           constraint / type written as words, a top-level WBS has a nil ParentObjectId,
           P6 19.x assignments may omit PricePerUnit.
  * XER  - tab-separated tables: TK_* statuses, CS_* constraints, a PROJWBS project-root node
           (proj_node_flag=Y), a clndr_data blob (24 h = s|00:00|f|00:00, dates as Excel serials),
           a " inside text written as "", a line break written as two DEL (0x7F) characters,
           total/free float in hours, money to 4 decimals, and - in the "with baseline" export -
           the baseline project's PROJECT / PROJWBS / CALENDAR / TASK / TASKRSRC rows.

Both files are parsed with p6_evm.parser.parse_file and every ScheduleData field is checked
  (1) against the P6 truth held in SPEC, per format  -> test_truth[xml-...] / test_truth[xer-...]
  (2) XML against XER (the R4 parity rule)           -> test_parity[...]
The schedule carries a baseline, three calendars (8 h with a lunch break, 24 h, a resource
calendar) with holidays / added / short / 24-h exception days, a project and a global activity
code type (plus an unused one), labour / nonlabour / material resources, FS/SS/FF/SF
relationships with lags and a lead, and progress on duration / physical / units % complete types.

Fields that fail TODAY are marked xfail(strict=True) with the parity-audit finding id
(D:/twe-scratch/phase2/parser/findings.json, commit "[parser:AUDIT]"). strict=True means a fix
that makes one pass turns it into an XPASS failure - remove the marker when you fix the finding.
The markers live in TRUTH_XFAIL / PARITY_XFAIL / STRUCTURE_XFAIL (search for the finding id,
e.g. "_P13") and on the variant tests at the bottom (P17, P22).
Run:  pytest tests/test_parser_parity.py -p no:cacheprovider -q -rxX
Genuine format differences (what P6 itself writes differently) are documented as plain tests,
not xfails: see test_tf_from_hours_* below.
"""
from datetime import date, datetime
from xml.sax.saxutils import escape

import pytest

from p6_evm.parser import parse_file


# ════════════════════════════════════════════════════════════════════════════════════════════
# SPEC - the one schedule, and the P6 truth every parser must return
# ════════════════════════════════════════════════════════════════════════════════════════════

def _d(s):
    return datetime.strptime(s, '%Y-%m-%d %H:%M') if s else None


DOWS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']  # P6 order 1..7
EIGHT_H = [(480, 720), (780, 1020)]        # 08:00-12:00, 13:00-17:00
FULL_DAY = [(0, 1440)]                     # a P6 24-hour day

PROJECT = {
    'object_id': '7000', 'id': 'PARITY-UP01', 'name': 'Parity Test Project - Update 01',
    'wbs_root': '7100', 'data_date': '2025-03-05 17:00', 'planned_start': '2025-03-03 08:00',
    'scheduled_finish': '2025-03-21 17:00', 'must_finish_by': '2025-03-28 17:00',
}
BASELINE = {
    'object_id': '6900', 'id': 'PARITY-BL', 'name': 'Parity Test Project - Baseline',
    'wbs_root': '6100', 'data_date': '2025-03-03 08:00', 'planned_start': '2025-03-03 08:00',
    'scheduled_finish': '2025-03-19 17:00', 'must_finish_by': '2025-03-28 17:00',
}
EPS_ID = '500'

CALENDARS = [
    {'oid': '8801', 'name': 'Standard 5-Day 8h', 'kind': 'Global', 'default': True, 'proj': None,
     'day_hours': 8.0,
     'week': {d: EIGHT_H for d in ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')},
     'exceptions': {date(2025, 3, 10): [],                    # holiday (Monday)
                    date(2025, 3, 8): [(480, 720)],           # added Saturday half day
                    date(2025, 3, 13): [(480, 720)]}},        # short Thursday
    {'oid': '8802', 'name': '24 Hrs - 6 Days', 'kind': 'Project', 'default': False, 'proj': '7000',
     'day_hours': 24.0,
     'week': {d: FULL_DAY for d in ('Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Saturday')},
     'exceptions': {date(2025, 3, 14): FULL_DAY,              # Friday worked 24 h
                    date(2025, 3, 15): []}},                  # holiday (Saturday)
    {'oid': '8803', 'name': 'Crew 10h - 6 Days', 'kind': 'Resource', 'default': False, 'proj': None,
     'day_hours': 10.0,
     'week': {d: [(420, 1020)] for d in ('Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday')},
     'exceptions': {date(2025, 3, 20): []}},
]
# The baseline project's own copy of the project calendar - lives with the baseline, never in
# the current project's calendar list (finding P11 / P23).
BASELINE_CALENDAR = dict(CALENDARS[1], oid='9101', name='24 Hrs - 6 Days (BL copy)', proj='6900',
                         exceptions={})

WBS = [('7101', 'Key Dates', None), ('7102', 'Engineering', None),
       ('7103', 'Construction', None), ('7104', 'Foundations', '7103')]
BASELINE_WBS = [('6101', 'Key Dates', None), ('6102', 'Engineering', None),
                ('6103', 'Construction', None), ('6104', 'Foundations', '6103')]

CODE_TYPES = [('5001', 'Area', 'Project'), ('5002', 'Discipline', 'Global'),
              ('5003', 'Unused Type', 'Global')]
CODE_VALUES = [('5101', '5001', 'ZA', 'Zone A'), ('5102', '5001', 'ZB', 'Zone B'),
               ('5201', '5002', 'CIV', 'Civil'), ('5202', '5002', 'MEP', 'Mechanical & Electrical')]

# (object id, P6 Resource Id, name, ScheduleData type)
RESOURCES = [('3001', 'LAB-01', 'Site Labour Crew', 'Labour'),
             ('3002', 'EXC-20', 'Excavator 20t', 'Equipment'),
             ('3003', 'MAT-PIPE6', 'Pipe 6" HDPE', 'Material')]
XML_RES_TYPE = {'Labour': 'Labor', 'Equipment': 'Nonlabor', 'Material': 'Material'}
XER_RES_TYPE = {'Labour': 'RT_Labor', 'Equipment': 'RT_Equip', 'Material': 'RT_Mat'}

XML_TO_XER_TASK_TYPE = {'Task Dependent': 'TT_Task', 'Start Milestone': 'TT_Mile',
                        'Finish Milestone': 'TT_FinMile'}
SD_TASK_TYPE = {'Task Dependent': 'Task', 'Start Milestone': 'StartMilestone',
                'Finish Milestone': 'FinishMilestone'}
XER_STATUS = {'Completed': 'TK_Complete', 'In Progress': 'TK_Active', 'Not Started': 'TK_NotStart'}
XER_PCT_TYPE = {'Duration': 'CP_Drtn', 'Physical': 'CP_Phys', 'Units': 'CP_Units'}
XER_CSTR = {'Start On': 'CS_MSO', 'Start On or Before': 'CS_MSOB', 'Start On or After': 'CS_MSOA',
            'Finish On': 'CS_MEO', 'Finish On or Before': 'CS_MEOB', 'Finish On or After': 'CS_MEOA'}


def _act(oid, code, name, typ, status, cal, wbs, pct_type, pd, rd, pct, ts, te, *, phys=0.0,
         act_s=None, act_f=None, res=None, ref=None, rls=None, rlf=None, tf=None, ff=None,
         cstr=(None, None), cstr2=(None, None), codes=None, act_work=0.0, rem_work=0.0,
         act_equip=0.0, rem_equip=0.0):
    return dict(oid=oid, code=code, name=name, type=typ, status=status, cal=cal, wbs=wbs,
                pct_type=pct_type, pd=pd, rd=rd, pct=pct, phys=phys, ts=ts, te=te, act_s=act_s,
                act_f=act_f, res=res, ref=ref, rls=rls, rlf=rlf, tf=tf, ff=ff, cstr=cstr,
                cstr2=cstr2, codes=codes or {}, act_work=act_work, rem_work=rem_work,
                act_equip=act_equip, rem_equip=rem_equip)


# Dates are P6's. Float (tf/ff, hours) is P6's FINISH float (REF -> RLF, ComputeTotalFloatType
# "Finish Float") in working hours on the activity calendar - worked out by hand below.
ACTIVITIES = [
    _act('70001', 'A1000', 'Project Start', 'Start Milestone', 'Completed', '8801', '7101',
         'Duration', 0.0, 0.0, 1.0, '2025-03-03 08:00', '2025-03-03 08:00',
         act_s='2025-03-03 08:00', act_f='2025-03-03 08:00', codes={'5002': '5201'}),
    # a " in the name (XER writes "")
    _act('70002', 'A1010', 'Design "Rev A" drawings', 'Task Dependent', 'Completed', '8801', '7102',
         'Duration', 16.0, 0.0, 1.0, '2025-03-03 08:00', '2025-03-04 17:00',
         act_s='2025-03-03 08:00', act_f='2025-03-04 17:00', codes={'5001': '5101', '5002': '5201'},
         act_work=16.0),
    # duration % = (32 - 16) / 32; TF 0 h -> critical
    _act('70003', 'A1015', 'Survey & setting out', 'Task Dependent', 'In Progress', '8801', '7104',
         'Duration', 32.0, 16.0, 0.5, '2025-03-04 08:00', '2025-03-07 17:00',
         act_s='2025-03-04 08:00', res='2025-03-06 08:00', ref='2025-03-07 17:00',
         rls='2025-03-06 08:00', rlf='2025-03-07 17:00', tf=0.0, ff=0.0, codes={'5001': '5101'}),
    # 24 h calendar; a line break in the name (XER writes 0x7F 0x7F); physical 40 %;
    # TF: REF Sat 08 05:00 -> RLF Sun 09 11:00 = 19 h + 11 h = 30 h = 1.25 days of 24 h.
    _act('70004', 'A1020', 'Excavation\nZone A', 'Task Dependent', 'In Progress', '8802', '7104',
         'Physical', 72.0, 36.0, 0.4, '2025-03-04 06:00', '2025-03-08 06:00', phys=0.4,
         act_s='2025-03-04 06:00', res='2025-03-05 17:00', ref='2025-03-08 05:00',
         rls='2025-03-06 23:00', rlf='2025-03-09 11:00', tf=30.0, ff=6.0,
         cstr=('Start On', '2025-03-04 06:00'), codes={'5001': '5101', '5002': '5201'},
         act_equip=30.0, rem_equip=42.0),
    # units % = (10 labour + 8 nonlabour) / (40 + 16) = 18/56; TF: REF Fri 07 17:00 -> RLF Sat 08
    # 12:00 = the 4 h added Saturday = 0.5 day.
    _act('70005', 'A1030', 'Blinding concrete', 'Task Dependent', 'In Progress', '8801', '7104',
         'Units', 24.0, 16.0, 18.0 / 56.0, '2025-03-05 08:00', '2025-03-07 17:00',
         act_s='2025-03-05 08:00', res='2025-03-06 08:00', ref='2025-03-07 17:00',
         rls='2025-03-06 13:00', rlf='2025-03-08 12:00', tf=4.0, ff=0.0,
         codes={'5001': '5102', '5002': '5201'}, act_work=10.0, rem_work=30.0, act_equip=8.0,
         rem_equip=8.0),
    # TF: REF Wed 12 17:00 -> RLF Tue 18 17:00 = 4 (short Thu) + 8 + 8 + 8 = 28 h = 3.5 days
    _act('70006', 'A1040', 'Rebar & formwork', 'Task Dependent', 'Not Started', '8801', '7104',
         'Duration', 16.0, 16.0, 0.0, '2025-03-11 08:00', '2025-03-12 17:00',
         res='2025-03-11 08:00', ref='2025-03-12 17:00', rls='2025-03-17 08:00',
         rlf='2025-03-18 17:00', tf=28.0, ff=0.0,
         cstr=('Finish On or Before', '2025-03-18 17:00'),
         cstr2=('Start On or After', '2025-03-11 08:00'), codes={'5001': '5102', '5002': '5202'}),
    # TF: Wed 12 17:00 -> Fri 21 17:00 = 4 + 8 + 5 x 8 = 52 h = 6.5 days
    _act('70007', 'A1050', 'Substantial Completion', 'Finish Milestone', 'Not Started', '8801',
         '7101', 'Duration', 0.0, 0.0, 0.0, '2025-03-12 17:00', '2025-03-12 17:00',
         res='2025-03-12 17:00', ref='2025-03-12 17:00', rls='2025-03-21 17:00',
         rlf='2025-03-21 17:00', tf=52.0, ff=52.0, cstr=('Finish On', '2025-03-21 17:00')),
]
ACT_BY_OID = {a['oid']: a for a in ACTIVITIES}
CAL_BY_OID = {c['oid']: c for c in CALENDARS + [BASELINE_CALENDAR]}

# Baseline project: its own object ids, same activity codes, earlier dates, plus one activity
# (A0990) deleted since the baseline.  (baseline oid, code, name, type, calendar, wbs, start, finish)
BASELINE_ACTIVITIES = [
    ('69000', 'A0990', 'Mobilisation (deleted)', 'Task Dependent', '8801', '6101',
     '2025-03-03 08:00', '2025-03-03 17:00'),
    ('69001', 'A1000', 'Project Start', 'Start Milestone', '8801', '6101',
     '2025-03-03 08:00', '2025-03-03 08:00'),
    ('69002', 'A1010', 'Design "Rev A" drawings', 'Task Dependent', '8801', '6102',
     '2025-03-03 08:00', '2025-03-04 17:00'),
    ('69003', 'A1015', 'Survey & setting out', 'Task Dependent', '8801', '6104',
     '2025-03-04 08:00', '2025-03-05 17:00'),
    ('69004', 'A1020', 'Excavation\nZone A', 'Task Dependent', '9101', '6104',
     '2025-03-04 06:00', '2025-03-06 18:00'),
    ('69005', 'A1030', 'Blinding concrete', 'Task Dependent', '8801', '6104',
     '2025-03-05 08:00', '2025-03-06 17:00'),
    ('69006', 'A1040', 'Rebar & formwork', 'Task Dependent', '8801', '6104',
     '2025-03-07 08:00', '2025-03-11 17:00'),
    ('69007', 'A1050', 'Substantial Completion', 'Finish Milestone', '8801', '6101',
     '2025-03-11 17:00', '2025-03-11 17:00'),
]
# (assignment oid, baseline activity oid, resource, planned units, planned cost)
BASELINE_ASSIGNMENTS = [('49002', '69002', '3001', 15.0, 750.0),
                        ('49004', '69004', '3002', 70.0, 7000.0),
                        ('49005', '69004', '3003', 96.0, 2400.0),
                        ('49006', '69005', '3001', 36.0, 1800.0),
                        ('49007', '69005', '3002', 16.0, 1600.0)]

# Current assignments. rate = P6 price/unit. xml_price=False: a P6 19.x XML that writes no
# PricePerUnit on the ResourceAssignment (finding P20).
ASSIGNMENTS = [
    dict(oid='4001', act='70002', rsrc='3001', target_qty=16.0, act_reg_qty=12.0, act_ot_qty=4.0,
         remain_qty=0.0, rate=50.0, target_cost=800.0, act_reg_cost=600.0, act_ot_cost=200.0,
         remain_cost=0.0, xml_price=True),
    dict(oid='4002', act='70004', rsrc='3002', target_qty=72.0, act_reg_qty=30.0, act_ot_qty=0.0,
         remain_qty=42.0, rate=100.0, target_cost=7200.0, act_reg_cost=3000.0, act_ot_cost=0.0,
         remain_cost=4200.0, xml_price=True),
    dict(oid='4003', act='70004', rsrc='3003', target_qty=100.0, act_reg_qty=40.0, act_ot_qty=0.0,
         remain_qty=60.0, rate=25.005, target_cost=2500.5, act_reg_cost=1000.2, act_ot_cost=0.0,
         remain_cost=1500.3, xml_price=False),
    dict(oid='4004', act='70005', rsrc='3001', target_qty=40.0, act_reg_qty=10.0, act_ot_qty=0.0,
         remain_qty=30.0, rate=50.0, target_cost=2000.0, act_reg_cost=500.0, act_ot_cost=0.0,
         remain_cost=1500.0, xml_price=True),
    dict(oid='4005', act='70005', rsrc='3002', target_qty=16.0, act_reg_qty=8.0, act_ot_qty=0.0,
         remain_qty=8.0, rate=100.0, target_cost=1600.0, act_reg_cost=800.0, act_ot_cost=0.0,
         remain_cost=800.0, xml_price=True),
]

# (relationship oid, pred, succ, type, lag hours). XML lists them in ObjectId order; P6's XER
# TASKPRED lists them in a different (successor) order (finding P17).
RELATIONSHIPS = [('80001', '70001', '70002', 'FS', 0.0),
                 ('80002', '70002', '70003', 'FS', 0.0),
                 ('80003', '70003', '70006', 'FS', 0.0),
                 ('80004', '70002', '70004', 'FS', 8.0),    # 8 h on the 8 h predecessor = 1 day
                 ('80005', '70004', '70005', 'SS', 24.0),   # 24 h on the 24 h predecessor = 1 day
                 ('80006', '70005', '70006', 'FF', 0.0),
                 ('80007', '70006', '70007', 'FS', -8.0),   # a lead
                 ('80008', '70001', '70007', 'SF', 0.0)]
XER_REL_ORDER = ['80001', '80002', '80004', '80005', '80003', '80006', '80008', '80007']
XML_REL_TYPE = {'FS': 'Finish to Start', 'SS': 'Start to Start', 'FF': 'Finish to Finish',
                'SF': 'Start to Finish'}
BASELINE_RELATIONSHIPS = [('89001', '69001', '69002', 'FS', 0.0)]


# ════════════════════════════════════════════════════════════════════════════════════════════
# Writers - SPEC -> P6 XML / P6 XER text
# ════════════════════════════════════════════════════════════════════════════════════════════

def _num(v):
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, float):
        s = ('%.10f' % v).rstrip('0').rstrip('.')
        return s or '0'
    return str(v)


# ── XML ──────────────────────────────────────────────────────────────────────────────────
XML_NS = 'http://xmlns.oracle.com/Primavera/P6Professional/V24.12/API/BusinessObjects'
XSI_NS = 'http://www.w3.org/2001/XMLSchema-instance'


def _x(tag, value):
    if value is None:
        return f'<{tag} xsi:nil="true" />'
    return f'<{tag}>{escape(_num(value))}</{tag}>'


def _xdt(s):
    """'2025-03-05 17:00' -> '2025-03-05T17:00:00' (P6 XML date-time)."""
    return s.replace(' ', 'T') + ':00' if s else None


def _xml_worktimes(ivs):
    """P6 XML writes a shift's LAST working minute as its Finish (12:00 -> 11:59:00)."""
    if not ivs:
        return '<WorkTime xsi:nil="true" />'
    out = []
    for sm, em in ivs:
        last = em - 1
        out.append('<WorkTime>' + _x('Finish', f'{last // 60:02d}:{last % 60:02d}:00')
                   + _x('Start', f'{sm // 60:02d}:{sm % 60:02d}:00') + '</WorkTime>')
    return ''.join(out)


def _xml_calendar(c):
    parts = ['<Calendar>']
    if c['exceptions']:
        parts.append('<HolidayOrExceptions>')
        for d, ivs in sorted(c['exceptions'].items()):
            parts.append('<HolidayOrException>' + _x('Date', d.isoformat() + 'T00:00:00')
                         + _xml_worktimes(ivs) + '</HolidayOrException>')
        parts.append('</HolidayOrExceptions>')
    parts += [_x('HoursPerDay', c['day_hours']), _x('IsDefault', c['default']),
              _x('Name', c['name']), _x('ObjectId', c['oid'])]
    parts.append('<StandardWorkWeek>')
    for dow in DOWS:
        parts.append('<StandardWorkHours>' + _x('DayOfWeek', dow)
                     + _xml_worktimes(c['week'].get(dow)) + '</StandardWorkHours>')
    parts.append('</StandardWorkWeek>')
    parts.append(_x('Type', c['kind']) + '</Calendar>')
    return ''.join(parts)


def _xml_code_type(oid, name, scope, proj=None):
    return ('<ActivityCodeType>' + _x('Name', name) + _x('ObjectId', oid)
            + (_x('ProjectObjectId', proj) if proj else '') + _x('Scope', scope)
            + '</ActivityCodeType>')


def _xml_code_value(oid, type_oid, short, desc):
    return ('<ActivityCode>' + _x('CodeTypeObjectId', type_oid) + _x('CodeValue', short)
            + _x('Description', desc) + _x('ObjectId', oid) + '</ActivityCode>')


def _xml_wbs(oid, name, parent, proj):
    return ('<WBS>' + _x('Code', name[:3].upper()) + _x('Name', name) + _x('ObjectId', oid)
            + _x('ParentObjectId', parent) + _x('ProjectObjectId', proj) + '</WBS>')


def _xml_activity(a):
    codes = ''.join('<Code>' + _x('TypeObjectId', t) + _x('ValueObjectId', v) + '</Code>'
                    for t, v in a['codes'].items())
    return ('<Activity>' + _x('ActualFinishDate', _xdt(a['act_f']))
            + _x('ActualStartDate', _xdt(a['act_s'])) + _x('CalendarObjectId', a['cal']) + codes
            + _x('Id', a['code']) + _x('Name', a['name']) + _x('ObjectId', a['oid'])
            + _x('PercentComplete', a['pct']) + _x('PercentCompleteType', a['pct_type'])
            + _x('PhysicalPercentComplete', a['phys']) + _x('PlannedDuration', a['pd'])
            + _x('PlannedFinishDate', _xdt(a['te'])) + _x('PlannedStartDate', _xdt(a['ts']))
            + _x('PrimaryConstraintDate', _xdt(a['cstr'][1]))
            + _x('PrimaryConstraintType', a['cstr'][0]) + _x('ProjectObjectId', PROJECT['object_id'])
            + _x('RemainingDuration', a['rd'])
            + _x('RemainingEarlyFinishDate', _xdt(a['ref']))
            + _x('RemainingEarlyStartDate', _xdt(a['res']))
            + _x('RemainingLateFinishDate', _xdt(a['rlf']))
            + _x('RemainingLateStartDate', _xdt(a['rls']))
            + _x('SecondaryConstraintDate', _xdt(a['cstr2'][1]))
            + _x('SecondaryConstraintType', a['cstr2'][0]) + _x('Status', a['status'])
            + _x('Type', a['type']) + _x('WBSObjectId', a['wbs']) + '</Activity>')


def _xml_assignment(s):
    rtype = next(r[3] for r in RESOURCES if r[0] == s['rsrc'])
    return ('<ResourceAssignment>' + _x('ActivityObjectId', s['act'])
            + _x('ActualCost', s['act_reg_cost'] + s['act_ot_cost'])
            + _x('ActualOvertimeCost', s['act_ot_cost']) + _x('ActualOvertimeUnits', s['act_ot_qty'])
            + _x('ActualRegularCost', s['act_reg_cost']) + _x('ActualRegularUnits', s['act_reg_qty'])
            + _x('ActualUnits', s['act_reg_qty'] + s['act_ot_qty']) + _x('ObjectId', s['oid'])
            + _x('PlannedCost', s['target_cost']) + _x('PlannedUnits', s['target_qty'])
            + (_x('PricePerUnit', s['rate']) if s['xml_price'] else '')
            + _x('ProjectObjectId', PROJECT['object_id']) + _x('RateSource', 'Resource')
            + _x('RemainingCost', s['remain_cost']) + _x('RemainingUnits', s['remain_qty'])
            + _x('ResourceObjectId', s['rsrc']) + _x('ResourceType', XML_RES_TYPE[rtype])
            + '</ResourceAssignment>')


def _xml_relationship(oid, pred, succ, typ, lag, proj):
    return ('<Relationship>' + _x('Lag', lag) + _x('ObjectId', oid)
            + _x('PredecessorActivityObjectId', pred) + _x('PredecessorProjectObjectId', proj)
            + _x('SuccessorActivityObjectId', succ) + _x('SuccessorProjectObjectId', proj)
            + _x('Type', XML_REL_TYPE[typ]) + '</Relationship>')


def build_xml(*, with_baseline=True, data_date=None):
    p = PROJECT
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           f'<APIBusinessObjects xmlns="{XML_NS}" xmlns:xsi="{XSI_NS}">']
    out += [_xml_calendar(c) for c in CALENDARS if c['proj'] is None]
    out += [_xml_code_type(oid, name, scope) for oid, name, scope in CODE_TYPES if scope == 'Global']
    out += [_xml_code_value(*v) for v in CODE_VALUES
            if dict((t[0], t[2]) for t in CODE_TYPES)[v[1]] == 'Global']
    for rid, code, name, typ in RESOURCES:
        out.append('<Resource>' + _x('Id', code) + _x('Name', name) + _x('ObjectId', rid)
                   + _x('ResourceType', XML_RES_TYPE[typ]) + '</Resource>')
    out.append('<Project>')
    out += [_x('ActivityDefaultCalendarObjectId', '8801'),
            _x('CurrentBaselineProjectObjectId', BASELINE['object_id']),
            _x('DataDate', data_date or _xdt(p['data_date'])), _x('Id', p['id']),
            _x('MustFinishByDate', _xdt(p['must_finish_by'])), _x('Name', p['name']),
            _x('ObjectId', p['object_id']), _x('PlannedStartDate', _xdt(p['planned_start'])),
            _x('ScheduledFinishDate', _xdt(p['scheduled_finish'])), _x('WBSObjectId', p['wbs_root'])]
    out += [_xml_code_type(oid, name, scope, p['object_id'])
            for oid, name, scope in CODE_TYPES if scope == 'Project']
    out += [_xml_code_value(*v) for v in CODE_VALUES
            if dict((t[0], t[2]) for t in CODE_TYPES)[v[1]] == 'Project']
    out += [_xml_calendar(c) for c in CALENDARS if c['proj'] == p['object_id']]
    out += [_xml_wbs(oid, name, parent, p['object_id']) for oid, name, parent in WBS]
    out += [_xml_activity(a) for a in ACTIVITIES]
    out += [_xml_assignment(s) for s in ASSIGNMENTS]
    out += [_xml_relationship(*r, p['object_id']) for r in RELATIONSHIPS]
    out.append('<ScheduleOptions>'
               + _x('ComputeTotalFloatType', 'Finish Float = Late Finish - Early Finish')
               + _x('RelationshipLagCalendar', 'Predecessor Activity Calendar')
               + '</ScheduleOptions>')
    out.append('</Project>')
    if with_baseline:
        b = BASELINE
        out.append('<BaselineProject>')
        out += [_x('DataDate', _xdt(b['data_date'])), _x('Id', b['id']),
                _x('MustFinishByDate', _xdt(b['must_finish_by'])), _x('Name', b['name']),
                _x('ObjectId', b['object_id']), _x('OriginalProjectObjectId', p['object_id']),
                _x('PlannedStartDate', _xdt(b['planned_start'])),
                _x('ScheduledFinishDate', _xdt(b['scheduled_finish'])),
                _x('WBSObjectId', b['wbs_root'])]
        out.append(_xml_calendar(BASELINE_CALENDAR))
        out += [_xml_wbs(oid, name, parent, b['object_id']) for oid, name, parent in BASELINE_WBS]
        for oid, code, name, typ, cal, wbs, s, f in BASELINE_ACTIVITIES:
            out.append('<Activity>' + _x('CalendarObjectId', cal) + _x('Id', code) + _x('Name', name)
                       + _x('ObjectId', oid) + _x('PlannedFinishDate', _xdt(f))
                       + _x('PlannedStartDate', _xdt(s)) + _x('ProjectObjectId', b['object_id'])
                       + _x('Status', 'Not Started') + _x('Type', typ) + _x('WBSObjectId', wbs)
                       + '</Activity>')
        for oid, act, rsrc, units, cost in BASELINE_ASSIGNMENTS:
            out.append('<ResourceAssignment>' + _x('ActivityObjectId', act) + _x('ObjectId', oid)
                       + _x('PlannedCost', cost) + _x('PlannedUnits', units)
                       + _x('ProjectObjectId', b['object_id']) + _x('ResourceObjectId', rsrc)
                       + '</ResourceAssignment>')
        out += [_xml_relationship(*r, b['object_id']) for r in BASELINE_RELATIONSHIPS]
        out.append('</BaselineProject>')
    out.append('</APIBusinessObjects>')
    return '\n'.join(out)


# ── XER ──────────────────────────────────────────────────────────────────────────────────
_EPOCH = date(1899, 12, 30)
_NL = '\x7f\x7f'                     # how P6 writes a line break inside an XER value


def _xer_value(v):
    if v is None:
        return ''
    if isinstance(v, str):
        return v.replace('"', '""').replace('\n', _NL)     # P6's XER text escaping
    return _num(v)


def _money(v):
    return '%.4f' % v                                     # P6 writes XER money to 4 dp


def _hhmm(m):
    return f'{m // 60:02d}:{m % 60:02d}'


def _xer_shifts(ivs, indent):
    out = []
    for k, (sm, em) in enumerate(ivs):
        # P6 writes a 24-hour shift as midnight-to-midnight: s|00:00|f|00:00
        fin = '00:00' if (sm, em) == (0, 1440) else _hhmm(em)
        out.append(f'{_NL}{indent}(0||{k}(s|{_hhmm(sm)}|f|{fin})())')
    return ''.join(out)


def _clndr_data(c):
    s = f'(0||CalendarData()({_NL}  (0||DaysOfWeek()('
    for i, dow in enumerate(DOWS, start=1):
        ivs = c['week'].get(dow)
        if ivs:
            s += f'{_NL}    (0||{i}()({_xer_shifts(ivs, "      ")}))'
        else:
            s += f'{_NL}    (0||{i}()())'
    s += f')){_NL}  (0||VIEW(ShowTotal|N)()){_NL}  (0||Exceptions()('
    for k, (d, ivs) in enumerate(sorted(c['exceptions'].items())):
        serial = (d - _EPOCH).days
        if ivs:
            s += f'{_NL}    (0||{k}(d|{serial})({_xer_shifts(ivs, "      ")}))'
        else:
            s += f'{_NL}    (0||{k}(d|{serial})())'
    return s + '))))'


def _xer_table(name, fields, rows):
    lines = [f'%T\t{name}', '%F\t' + '\t'.join(fields)]
    for r in rows:
        lines.append('%R\t' + '\t'.join(_xer_value(r.get(f)) for f in fields))
    return lines


_CLNDR_TYPE = {'Global': 'CA_Base', 'Project': 'CA_Project', 'Resource': 'CA_Rsrc'}


def _xer_calendar_row(c):
    return {'clndr_id': c['oid'], 'default_flag': 'Y' if c['default'] else 'N',
            'clndr_name': c['name'], 'proj_id': c['proj'], 'clndr_type': _CLNDR_TYPE[c['kind']],
            'day_hr_cnt': c['day_hours'], 'week_hr_cnt': c['day_hours'] * len(c['week']),
            'clndr_data': _clndr_data(c)}


def _xer_project_row(p, base_id):
    return {'proj_id': p['object_id'], 'proj_short_name': p['id'], 'clndr_id': '8801',
            'sum_base_proj_id': base_id, 'def_complete_pct_type': 'CP_Drtn',
            'last_recalc_date': p['data_date'], 'plan_start_date': p['planned_start'],
            'plan_end_date': p['must_finish_by'], 'scd_end_date': p['scheduled_finish']}


def _xer_wbs_rows(p, nodes):
    rows = [{'wbs_id': p['wbs_root'], 'proj_id': p['object_id'], 'seq_num': '0',
             'proj_node_flag': 'Y', 'wbs_short_name': p['id'], 'wbs_name': p['name'],
             'parent_wbs_id': EPS_ID}]
    for i, (oid, name, parent) in enumerate(nodes, start=1):
        rows.append({'wbs_id': oid, 'proj_id': p['object_id'], 'seq_num': str(i * 10),
                     'proj_node_flag': 'N', 'wbs_short_name': name[:3].upper(), 'wbs_name': name,
                     'parent_wbs_id': parent or p['wbs_root']})
    return rows


def _xer_task_row(a):
    cstr, cstr_d = a['cstr']
    cstr2, cstr2_d = a['cstr2']
    return {'task_id': a['oid'], 'proj_id': PROJECT['object_id'], 'wbs_id': a['wbs'],
            'clndr_id': a['cal'], 'phys_complete_pct': a['phys'] * 100.0,
            'complete_pct_type': XER_PCT_TYPE[a['pct_type']],
            'task_type': XML_TO_XER_TASK_TYPE[a['type']], 'duration_type': 'DT_FixedDUR2',
            'status_code': XER_STATUS[a['status']], 'task_code': a['code'], 'task_name': a['name'],
            'total_float_hr_cnt': a['tf'], 'free_float_hr_cnt': a['ff'],
            'remain_drtn_hr_cnt': a['rd'], 'act_work_qty': a['act_work'],
            'remain_work_qty': a['rem_work'], 'target_work_qty': a['act_work'] + a['rem_work'],
            'target_drtn_hr_cnt': a['pd'], 'target_equip_qty': a['act_equip'] + a['rem_equip'],
            'act_equip_qty': a['act_equip'], 'remain_equip_qty': a['rem_equip'],
            'cstr_date': cstr_d, 'act_start_date': a['act_s'], 'act_end_date': a['act_f'],
            'restart_date': a['res'], 'reend_date': a['ref'],
            'target_start_date': a['ts'], 'target_end_date': a['te'],
            'rem_late_start_date': a['rls'], 'rem_late_end_date': a['rlf'],
            'cstr_type': XER_CSTR.get(cstr), 'cstr_date2': cstr2_d, 'cstr_type2': XER_CSTR.get(cstr2)}


PROJECT_F = ['proj_id', 'proj_short_name', 'clndr_id', 'sum_base_proj_id', 'def_complete_pct_type',
             'last_recalc_date', 'plan_start_date', 'plan_end_date', 'scd_end_date']
CALENDAR_F = ['clndr_id', 'default_flag', 'clndr_name', 'proj_id', 'base_clndr_id',
              'clndr_type', 'day_hr_cnt', 'week_hr_cnt', 'clndr_data']
WBS_F = ['wbs_id', 'proj_id', 'seq_num', 'proj_node_flag', 'wbs_short_name', 'wbs_name',
         'parent_wbs_id']
TASK_F = ['task_id', 'proj_id', 'wbs_id', 'clndr_id', 'phys_complete_pct', 'complete_pct_type',
          'task_type', 'duration_type', 'status_code', 'task_code', 'task_name',
          'total_float_hr_cnt', 'free_float_hr_cnt', 'remain_drtn_hr_cnt', 'act_work_qty',
          'remain_work_qty', 'target_work_qty', 'target_drtn_hr_cnt', 'target_equip_qty',
          'act_equip_qty', 'remain_equip_qty', 'cstr_date', 'act_start_date', 'act_end_date',
          'restart_date', 'reend_date', 'target_start_date', 'target_end_date',
          'rem_late_start_date', 'rem_late_end_date', 'cstr_type', 'cstr_date2', 'cstr_type2']
TASKRSRC_F = ['taskrsrc_id', 'task_id', 'proj_id', 'rsrc_id', 'remain_qty', 'target_qty',
              'act_ot_qty', 'act_reg_qty', 'cost_per_qty', 'target_cost', 'act_reg_cost',
              'act_ot_cost', 'remain_cost', 'rsrc_type']
TASKPRED_F = ['task_pred_id', 'task_id', 'pred_task_id', 'proj_id', 'pred_proj_id', 'pred_type',
              'lag_hr_cnt']


def build_xer(*, baseline_rows=True, baseline_first=False, blank_float=False, data_date=None):
    """baseline_rows=True : the export carries the baseline project's rows (the XER twin of the
    XML's <BaselineProject>). False: only the BASELINE_EXPORT pointer, as real P6 update exports
    do (genuine finding G3)."""
    p, b = PROJECT, BASELINE
    lines = ['ERMHDR\t19.12\t2025-03-06\tProject\tadmin\tadmin\tdbxDatabaseNoName\t'
             'Project Management\tUSD']
    lines += _xer_table('BASELINE_EXPORT', ['export_flag', 'proj_id', 'proj_name', 'data_date'],
                        [{'export_flag': 'Y', 'proj_id': b['object_id'], 'proj_name': b['name'],
                          'data_date': b['data_date']}])
    prow = _xer_project_row(dict(p, data_date=data_date or p['data_date']), b['object_id'])
    prows = [prow]
    if baseline_rows:
        brow = _xer_project_row(b, '')
        prows = [brow, prow] if baseline_first else [prow, brow]
    lines += _xer_table('PROJECT', PROJECT_F, prows)
    cals = CALENDARS + ([BASELINE_CALENDAR] if baseline_rows else [])
    lines += _xer_table('CALENDAR', CALENDAR_F, [_xer_calendar_row(c) for c in cals])
    lines += _xer_table('SCHEDOPTIONS', ['schedoptions_id', 'proj_id', 'sched_float_type',
                                         'sched_calendar_on_relationship_lag'],
                        [{'schedoptions_id': '1', 'proj_id': p['object_id'],
                          'sched_float_type': 'FT_FF',
                          'sched_calendar_on_relationship_lag': 'rcal_Predecessor'}])
    wbs_rows = _xer_wbs_rows(p, WBS)
    if baseline_rows:
        bw = _xer_wbs_rows(b, BASELINE_WBS)
        wbs_rows = (bw + wbs_rows) if baseline_first else (wbs_rows + bw)
    lines += _xer_table('PROJWBS', WBS_F, wbs_rows)
    lines += _xer_table('RSRC', ['rsrc_id', 'clndr_id', 'rsrc_name', 'rsrc_short_name', 'rsrc_type'],
                        [{'rsrc_id': rid, 'clndr_id': '8803', 'rsrc_name': name,
                          'rsrc_short_name': code, 'rsrc_type': XER_RES_TYPE[typ]}
                         for rid, code, name, typ in RESOURCES])
    lines += _xer_table('ACTVTYPE', ['actv_code_type_id', 'actv_short_len', 'seq_num',
                                     'actv_code_type', 'proj_id', 'actv_code_type_scope'],
                        [{'actv_code_type_id': oid, 'actv_short_len': '3', 'seq_num': str(i),
                          'actv_code_type': name,
                          'proj_id': p['object_id'] if scope == 'Project' else None,
                          'actv_code_type_scope': 'AS_Project' if scope == 'Project' else 'AS_Global'}
                         for i, (oid, name, scope) in enumerate(CODE_TYPES)])
    task_rows = []
    for a in ACTIVITIES:
        row = _xer_task_row(a)
        if blank_float:
            row['total_float_hr_cnt'] = row['free_float_hr_cnt'] = None
        task_rows.append(row)
    if baseline_rows:
        brows = [{'task_id': oid, 'proj_id': b['object_id'], 'wbs_id': wbs, 'clndr_id': cal,
                  'complete_pct_type': 'CP_Drtn', 'task_type': XML_TO_XER_TASK_TYPE[typ],
                  'status_code': 'TK_NotStart', 'task_code': code, 'task_name': name,
                  'target_start_date': s, 'target_end_date': f, 'restart_date': s,
                  'reend_date': f, 'rem_late_start_date': s, 'rem_late_end_date': f,
                  'total_float_hr_cnt': 0.0, 'free_float_hr_cnt': 0.0}
                 for oid, code, name, typ, cal, wbs, s, f in BASELINE_ACTIVITIES]
        task_rows = (brows + task_rows) if baseline_first else (task_rows + brows)
    lines += _xer_table('TASK', TASK_F, task_rows)
    lines += _xer_table('ACTVCODE', ['actv_code_id', 'parent_actv_code_id', 'actv_code_type_id',
                                     'actv_code_name', 'short_name', 'seq_num'],
                        [{'actv_code_id': oid, 'actv_code_type_id': t, 'actv_code_name': desc,
                          'short_name': short, 'seq_num': str(i)}
                         for i, (oid, t, short, desc) in enumerate(CODE_VALUES)])
    rel_by_oid = {r[0]: r for r in RELATIONSHIPS}
    pred_rows = [{'task_pred_id': oid, 'task_id': succ, 'pred_task_id': pred,
                  'proj_id': p['object_id'], 'pred_proj_id': p['object_id'],
                  'pred_type': 'PR_' + typ, 'lag_hr_cnt': lag}
                 for oid, pred, succ, typ, lag in (rel_by_oid[o] for o in XER_REL_ORDER)]
    if baseline_rows:
        pred_rows += [{'task_pred_id': oid, 'task_id': succ, 'pred_task_id': pred,
                       'proj_id': b['object_id'], 'pred_proj_id': b['object_id'],
                       'pred_type': 'PR_' + typ, 'lag_hr_cnt': lag}
                      for oid, pred, succ, typ, lag in BASELINE_RELATIONSHIPS]
    lines += _xer_table('TASKPRED', TASKPRED_F, pred_rows)
    rtype = {r[0]: r[3] for r in RESOURCES}
    rs_rows = [{'taskrsrc_id': s['oid'], 'task_id': s['act'], 'proj_id': p['object_id'],
                'rsrc_id': s['rsrc'], 'remain_qty': s['remain_qty'], 'target_qty': s['target_qty'],
                'act_ot_qty': s['act_ot_qty'], 'act_reg_qty': s['act_reg_qty'],
                'cost_per_qty': _money(s['rate']), 'target_cost': _money(s['target_cost']),
                'act_reg_cost': _money(s['act_reg_cost']), 'act_ot_cost': _money(s['act_ot_cost']),
                'remain_cost': _money(s['remain_cost']), 'rsrc_type': XER_RES_TYPE[rtype[s['rsrc']]]}
               for s in ASSIGNMENTS]
    if baseline_rows:
        rs_rows += [{'taskrsrc_id': oid, 'task_id': act, 'proj_id': b['object_id'], 'rsrc_id': rsrc,
                     'remain_qty': units, 'target_qty': units, 'act_ot_qty': 0.0,
                     'act_reg_qty': 0.0, 'target_cost': _money(cost), 'act_reg_cost': _money(0),
                     'act_ot_cost': _money(0), 'remain_cost': _money(cost),
                     'rsrc_type': XER_RES_TYPE[rtype[rsrc]]}
                    for oid, act, rsrc, units, cost in BASELINE_ASSIGNMENTS]
    lines += _xer_table('TASKRSRC', TASKRSRC_F, rs_rows)
    lines += _xer_table('TASKACTV', ['task_id', 'actv_code_type_id', 'actv_code_id', 'proj_id'],
                        [{'task_id': a['oid'], 'actv_code_type_id': t, 'actv_code_id': v,
                          'proj_id': p['object_id']}
                         for a in ACTIVITIES for t, v in a['codes'].items()])
    lines.append('%E')
    return '\r\n'.join(lines) + '\r\n'


def _write(tmp_dir, name, text):
    path = tmp_dir / name
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    return str(path)


# ════════════════════════════════════════════════════════════════════════════════════════════
# Truth + views: the same shape for SPEC and for a parsed ScheduleData
# ════════════════════════════════════════════════════════════════════════════════════════════
MISSING = '<missing>'


def _norm(v):
    """Comparable form: floats to 6 dp (money / % / days), containers recursively."""
    if isinstance(v, bool) or v is None or isinstance(v, (str, datetime, date)):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 6)
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    if isinstance(v, (set, frozenset)):
        return frozenset(_norm(x) for x in v)
    if isinstance(v, (list, tuple)):
        return type(v)(_norm(x) for x in v)
    return v


def _text(v):
    """Names compare on their words: a line break may be kept as \\n or folded to a space, but
    P6's XER escapes ("" for ", 0x7F 0x7F for a line break) must be decoded (P14 / P15)."""
    return ' '.join(v.split()) if isinstance(v, str) else v


def _truth_cal(c, field):
    wk = c['week']
    exc = c['exceptions']
    return {
        'name': c['name'], 'day_hours': c['day_hours'],
        'nonworking_days': {d for d in DOWS if d not in wk},
        'holidays': {d for d, ivs in exc.items() if not ivs},
        'added_work_days': {d for d, ivs in exc.items() if ivs},
        'work_intervals': dict(wk),
        'exception_intervals': {d: ivs for d, ivs in exc.items() if ivs},
        'weekly_working_days': set(wk),
        'type': c['kind'], 'is_default': c['default'],
    }[field]


def _code_names():
    t = {oid: name for oid, name, _ in CODE_TYPES}
    v = {oid: desc for oid, _, _, desc in CODE_VALUES}
    return t, v


def _wbs_path(wbs_oid):
    nodes = {oid: (name, parent) for oid, name, parent in WBS}
    names, cur = [], wbs_oid
    while cur:
        names.append(nodes[cur][0])
        cur = nodes[cur][1]
    return ' > '.join(reversed(names))


def _truth_activity(a, field):
    tnames, vnames = _code_names()
    cal = CAL_BY_OID[a['cal']]
    tf = None if a['tf'] is None else a['tf'] / cal['day_hours']
    return {
        'id': a['code'], 'name': a['name'], 'status': a['status'], 'calendar_id': a['cal'],
        'wbs_id': a['wbs'], 'task_type': SD_TASK_TYPE[a['type']], 'percent_complete': a['pct'],
        'planned_duration': a['pd'], 'remaining_duration': a['rd'],
        'total_float_days': tf,
        'free_float_days': None if a['ff'] is None else a['ff'] / cal['day_hours'],
        'is_critical': tf is not None and tf <= 0,
        'constraint_type': a['cstr'][0], 'constraint_date': _d(a['cstr'][1]),
        'secondary_constraint_type': a['cstr2'][0], 'secondary_constraint_date': _d(a['cstr2'][1]),
        'activity_codes': {tnames[t]: vnames[v] for t, v in a['codes'].items()},
        'wbs_path': _wbs_path(a['wbs']),
        'planned_start': _d(a['ts']), 'planned_finish': _d(a['te']),
        'remaining_early_start': _d(a['res']), 'remaining_early_finish': _d(a['ref']),
        'remaining_late_start': _d(a['rls']), 'remaining_late_finish': _d(a['rlf']),
        'actual_start': _d(a['act_s']), 'actual_finish': _d(a['act_f']),
    }[field]


def truth(entity, field):
    p = PROJECT
    code = {a['oid']: a['code'] for a in ACTIVITIES}
    if entity == 'project':
        return {'object_id': p['object_id'], 'id': p['id'], 'name': p['name'],
                'data_date': _d(p['data_date']), 'baseline_object_id': BASELINE['object_id'],
                'planned_start': _d(p['planned_start']),
                'scheduled_finish': _d(p['scheduled_finish']),
                'must_finish_by': _d(p['must_finish_by']), 'baseline_name': BASELINE['name'],
                'wbs_root_id': p['wbs_root'], 'total_float_type': 'finish'}[field]
    if entity == 'data':
        if field == 'activity_code_types':
            tnames, _ = _code_names()
            return sorted({tnames[t] for a in ACTIVITIES for t in a['codes']})
        if field == 'baseline_by_id':
            return {c: {'planned_start': _d(s), 'planned_finish': _d(f)}
                    for _, c, _, _, _, _, s, f in BASELINE_ACTIVITIES}
        if field == 'baseline_bac_by_activity':
            bl_code = {oid: c for oid, c, *_ in BASELINE_ACTIVITIES}
            out = {}
            for _, act, _, _, cost in BASELINE_ASSIGNMENTS:
                out[bl_code[act]] = out.get(bl_code[act], 0.0) + cost
            return out
        if field == 'bac_by_activity':
            out = {}
            for s in ASSIGNMENTS:
                out[code[s['act']]] = out.get(code[s['act']], 0.0) + s['target_cost']
            return out
        if field == 'ac_by_activity':
            out = {}
            for s in ASSIGNMENTS:
                out[code[s['act']]] = (out.get(code[s['act']], 0.0) + s['act_reg_cost']
                                       + s['act_ot_cost'])
            return out
        if field == 'baseline_source':
            return 'embedded'
    if entity == 'calendar':
        if field == 'ids':
            return sorted(c['oid'] for c in CALENDARS)
        return {c['oid']: _truth_cal(c, field) for c in CALENDARS}
    if entity == 'wbs':
        if field == 'ids':
            return sorted(oid for oid, _, _ in WBS)
        return {oid: {'name': name, 'parent_object_id': parent}[field] for oid, name, parent in WBS}
    if entity == 'activity':
        if field == 'ids':
            return sorted(a['code'] for a in ACTIVITIES)
        return {a['code']: _truth_activity(a, field) for a in ACTIVITIES}
    if entity == 'relationship':
        if field == 'ids':
            return sorted((code[pr], code[su]) for _, pr, su, _, _ in RELATIONSHIPS)
        out = {}
        for _, pr, su, typ, lag in RELATIONSHIPS:
            day_h = CAL_BY_OID[ACT_BY_OID[pr]['cal']]['day_hours']   # PREDECESSOR calendar
            out[(code[pr], code[su])] = {'type': typ, 'lag_hours': lag,
                                         'lag_days': lag / day_h}[field]
        return out
    if entity == 'resource':
        return {rid: {'name': name, 'code': rc, 'type': typ}[field]
                for rid, rc, name, typ in RESOURCES}
    if entity == 'assignment':
        res = {rid: (rc, name, typ) for rid, rc, name, typ in RESOURCES}
        out = {}
        for s in ASSIGNMENTS:
            rc, name, typ = res[s['rsrc']]
            out[(code[s['act']], s['rsrc'])] = {
                'resource_code': rc, 'resource_name': name, 'resource_type': typ,
                'budget_units': s['target_qty'], 'actual_units': s['act_reg_qty'] + s['act_ot_qty'],
                'budget_cost': s['target_cost'], 'rate': s['rate']}[field]
        return out
    raise KeyError(entity)


def view(data, entity, field):
    code = {oid: a.get('id') for oid, a in data.activities.items()}
    if entity == 'project':
        v = data.project.get(field, MISSING)
        return _text(v) if field == 'name' else v
    if entity == 'data':
        v = getattr(data, field, MISSING)
        if field in ('bac_by_activity', 'ac_by_activity', 'baseline_bac_by_activity'):
            v = {code.get(k, k): x for k, x in v.items()}
        return v
    if entity == 'calendar':
        if field == 'ids':
            return sorted(data.calendars)
        ids = [c['oid'] for c in CALENDARS]
        return {oid: (getattr(data.calendars[oid], field, MISSING) if oid in data.calendars
                      else MISSING) for oid in ids}
    if entity == 'wbs':
        if field == 'ids':
            return sorted(data.wbs)
        return {oid: (data.wbs[oid].get(field, MISSING) if oid in data.wbs else MISSING)
                for oid, _, _ in WBS}
    if entity == 'activity':
        if field == 'ids':
            return sorted(a.get('id') for a in data.activities.values())
        return {a.get('id'): (_text(a.get(field, MISSING)) if field == 'name'
                              else a.get(field, MISSING))
                for a in data.activities.values()}
    if entity == 'relationship':
        if field == 'ids':
            return sorted((code.get(r['pred_id']), code.get(r['succ_id'])) for r in data.relationships)
        return {(code.get(r['pred_id']), code.get(r['succ_id'])): r.get(field, MISSING)
                for r in data.relationships}
    if entity == 'resource':
        return {rid: (_text(r.get(field, MISSING)) if field == 'name' else r.get(field, MISSING))
                for rid, r in data.resources.items()}
    if entity == 'assignment':
        out = {}
        for oid, lst in data.assignments_by_activity.items():
            for s in lst:
                v = s.get(field, MISSING)
                out[(code.get(oid), s.get('resource_id'))] = (_text(v) if field == 'resource_name'
                                                              else v)
        return out
    raise KeyError(entity)


def _truth_text(entity, field):
    t = truth(entity, field)
    if field in ('name', 'resource_name'):
        if isinstance(t, dict):
            return {k: _text(v) for k, v in t.items()}
        return _text(t)
    return t


def _explain(got, want):
    if isinstance(got, dict) and isinstance(want, dict):
        bad = [f'  {k!r}: got {got.get(k, MISSING)!r} want {want.get(k, MISSING)!r}'
               for k in sorted(set(got) | set(want), key=repr) if got.get(k, MISSING) != want.get(k, MISSING)]
        return '\n'.join(bad[:12])
    return f'  got {got!r}\n  want {want!r}'


# ════════════════════════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope='module')
def files(tmp_path_factory):
    d = tmp_path_factory.mktemp('parity')
    return {
        'xml': _write(d, 'parity.xml', build_xml()),
        'xer': _write(d, 'parity.xer', build_xer()),
        'xml_nobl': _write(d, 'parity_nobl.xml', build_xml(with_baseline=False)),
        'xer_nobl': _write(d, 'parity_nobl.xer', build_xer(baseline_rows=False)),
        'xer_bl_first': _write(d, 'parity_bl_first.xer', build_xer(baseline_first=True)),
        'xer_blank_tf': _write(d, 'parity_blank_tf.xer', build_xer(blank_float=True)),
        'xml_frac_dd': _write(d, 'parity_frac.xml', build_xml(data_date='2025-03-05T17:00:00.000')),
        'xer_frac_dd': _write(d, 'parity_frac.xer', build_xer(data_date='2025-03-05 17:00:00.000')),
    }


@pytest.fixture(scope='module')
def parsed(files):
    return {'xml': parse_file(files['xml']), 'xer': parse_file(files['xer'])}


# ════════════════════════════════════════════════════════════════════════════════════════════
# Field list + today's known failures (finding id from the [parser:AUDIT] parity audit)
# ════════════════════════════════════════════════════════════════════════════════════════════
FIELDS = (
    [('project', f) for f in ('object_id', 'id', 'name', 'data_date', 'baseline_object_id',
                              'planned_start', 'scheduled_finish', 'must_finish_by',
                              'baseline_name', 'wbs_root_id', 'total_float_type')]
    + [('data', f) for f in ('activity_code_types', 'baseline_by_id', 'baseline_bac_by_activity',
                             'bac_by_activity', 'ac_by_activity', 'baseline_source')]
    + [('calendar', f) for f in ('ids', 'name', 'day_hours', 'nonworking_days', 'holidays',
                                 'added_work_days', 'work_intervals', 'exception_intervals',
                                 'weekly_working_days', 'type', 'is_default')]
    + [('wbs', f) for f in ('ids', 'name', 'parent_object_id')]
    + [('activity', f) for f in ('ids', 'id', 'name', 'status', 'calendar_id', 'wbs_id',
                                 'task_type', 'percent_complete', 'planned_duration',
                                 'remaining_duration', 'total_float_days', 'free_float_days',
                                 'is_critical', 'constraint_type', 'constraint_date',
                                 'secondary_constraint_type', 'secondary_constraint_date',
                                 'activity_codes', 'wbs_path', 'planned_start', 'planned_finish',
                                 'remaining_early_start', 'remaining_early_finish',
                                 'remaining_late_start', 'remaining_late_finish', 'actual_start',
                                 'actual_finish')]
    + [('relationship', f) for f in ('ids', 'type', 'lag_hours', 'lag_days')]
    + [('resource', f) for f in ('name', 'code', 'type')]
    + [('assignment', f) for f in ('resource_code', 'resource_name', 'resource_type',
                                   'budget_units', 'actual_units', 'budget_cost', 'rate')]
)

# FIXED (markers removed): P1 XER baseline rows / pointer / name read like the XML's
# <BaselineProject>; P4 XER 24-h shift s|00:00|f|00:00 read as working to 24:00; P5 XER project-root
# WBS node kept out of data.wbs; P6 XER TK_* status / P7 CS_* constraint read as P6's words, and the
# secondary constraint read in both; P8 XML total float rebuilt as P6 finish float in working hours
# (with P10: the XML <WorkTime><Finish> last working minute read back as the shift end);
# P9 XER blank total_float_hr_cnt rebuilt the same way; P11 / P23 the baseline project's calendars
# kept out of the project calendar list in both formats (data.baseline_calendars); P12 calendar
# type / is_default read from the XER and weekly_working_days filled for the XML.
_P13 = 'P13: project window / must-finish-by / baseline pointer not read'
_P14 = 'P14: XER "" (escaped quote) not un-escaped'
_P15 = 'P15: XER line break 0x7F 0x7F kept in text'
_P16 = 'P16: lag converted on the SUCCESSOR calendar; project option is the PREDECESSOR calendar'
_P18 = 'P18: XER activity_code_types lists unassigned code types'
_P19 = 'P19: XER Units % complete counts labour units only (P6: labour + nonlabour)'
_P20 = 'P20: XML assignment without PricePerUnit gives rate None'
_P24 = 'P24: P6 XML exports no free float (format limitation - reconstruct or document)'

# (format, 'entity.field') -> finding. Measured by running this harness against the parsers as
# they stood at commit "[parser:AUDIT]" (every failure checked against the finding's evidence).
TRUTH_XFAIL = {
    ('xml', 'project.must_finish_by'): _P13,
    ('xml', 'activity.free_float_days'): _P24,
    ('xml', 'relationship.lag_days'): _P16,
    ('xml', 'assignment.rate'): _P20,
    ('xer', 'project.planned_start'): _P13,
    ('xer', 'project.scheduled_finish'): _P13,
    ('xer', 'project.must_finish_by'): _P13,
    ('xer', 'data.activity_code_types'): _P18,
    ('xer', 'activity.name'): _P14 + ' / ' + _P15,
    ('xer', 'activity.percent_complete'): _P19,
    ('xer', 'relationship.lag_days'): _P16,
    ('xer', 'resource.name'): _P14,
    ('xer', 'assignment.resource_name'): _P14,
}
# 'entity.field' -> finding(s) that make XML and XER disagree today. (A field both parsers get
# wrong the SAME way - P13 must-finish-by, P16 lag
# days - passes parity and is caught by test_truth only.)
PARITY_XFAIL = {
    'project.planned_start': _P13,
    'project.scheduled_finish': _P13,
    'data.activity_code_types': _P18,
    'activity.name': _P14 + ' / ' + _P15,
    'activity.percent_complete': _P19,
    'activity.free_float_days': _P24,
    'resource.name': _P14,
    'assignment.resource_name': _P14,
    'assignment.rate': _P20,
}


def _params(kind):
    out = []
    fmts = ('xml', 'xer') if kind == 'truth' else (None,)
    for fmt in fmts:
        for entity, field in FIELDS:
            key = f'{entity}.{field}'
            reason = (TRUTH_XFAIL.get((fmt, key)) if kind == 'truth' else PARITY_XFAIL.get(key))
            pid = f'{fmt}-{key}' if fmt else key
            args = (fmt, entity, field) if fmt else (entity, field)
            marks = [pytest.mark.xfail(strict=True, reason=reason)] if reason else []
            out.append(pytest.param(*args, id=pid, marks=marks))
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# The tests
# ════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('fmt,entity,field', _params('truth'))
def test_truth(parsed, fmt, entity, field):
    """Each format returns what P6 holds for this field."""
    got = _norm(view(parsed[fmt], entity, field))
    want = _norm(_truth_text(entity, field))
    assert got == want, f'{fmt} {entity}.{field} differs from P6:\n{_explain(got, want)}'


@pytest.mark.parametrize('entity,field', _params('parity'))
def test_parity(parsed, entity, field):
    """R4: the XML and the XER of the same schedule give the same ScheduleData field."""
    x = _norm(view(parsed['xml'], entity, field))
    r = _norm(view(parsed['xer'], entity, field))
    assert x == r, f'{entity}.{field}: XML vs XER\n{_explain(r, x)}'


@pytest.mark.xfail(strict=True, reason='P17: relationship order follows the file (XML ObjectId '
                                       'order vs XER TASKPRED order) - sort deterministically')
def test_relationship_order_matches(parsed):
    """Order-sensitive outputs (a representative link, 'first' predecessor) must not depend on
    the file format: the same links in the same order from XML and XER."""
    order = {}
    for fmt in ('xml', 'xer'):
        d = parsed[fmt]
        code = {oid: a['id'] for oid, a in d.activities.items()}
        order[fmt] = [(code[r['pred_id']], code[r['succ_id']]) for r in d.relationships]
    assert order['xml'] == order['xer']


STRUCTURE_XFAIL = {'project': _P13}


@pytest.mark.parametrize('part', [
    pytest.param(p, id=p, marks=[pytest.mark.xfail(strict=True, reason=STRUCTURE_XFAIL[p])]
                 if p in STRUCTURE_XFAIL else [])
    for p in ('schedule_data', 'project', 'activity', 'relationship', 'resource', 'assignment')])
def test_key_sets_match(parsed, part):
    """Both parsers expose the SAME keys, so a feature never meets a field that exists for one
    format only (a new key added to one parser must be added to the other)."""
    def keys(d):
        if part == 'schedule_data':
            return set(vars(d))
        if part == 'project':
            return set(d.project)
        if part == 'activity':
            return {frozenset(a) for a in d.activities.values()}
        if part == 'relationship':
            return {frozenset(r) for r in d.relationships}
        if part == 'resource':
            return {frozenset(r) for r in d.resources.values()}
        return {frozenset(s) for lst in d.assignments_by_activity.values() for s in lst}
    assert keys(parsed['xml']) == keys(parsed['xer'])


def test_tf_from_hours_is_a_genuine_format_difference(parsed):
    """GENUINE (not a defect): P6's XER stores Total Float (total_float_hr_cnt) while P6's XML
    exports NO float field on <Activity> (only <ComputeTotalFloatType>), so the XML float is always
    reconstructed. tf_from_hours records that provenance and legitimately differs; the float VALUE
    must still agree (test_parity[activity.total_float_days])."""
    xml = {a['id']: a['tf_from_hours'] for a in parsed['xml'].activities.values()}
    xer = {a['id']: a['tf_from_hours'] for a in parsed['xer'].activities.values()}
    assert set(xml.values()) == {False}
    assert xer == {a['code']: a['tf'] is not None for a in ACTIVITIES}


def test_twin_files_are_written_the_way_p6_writes_them(files):
    """Guard the harness itself: the synthetic files keep P6's real per-format encodings, so the
    parity tests exercise what P6 actually writes (evidence: SG / ALSTOM / GBT parity pairs)."""
    with open(files['xml'], encoding='utf-8') as f:
        xml = f.read()
    with open(files['xer'], encoding='utf-8') as f:
        xer = f.read()
    assert '<Finish>11:59:00</Finish>' in xml and '<Finish>23:59:00</Finish>' in xml
    assert '<TotalFloat' not in xml and '<FreeFloat' not in xml       # P6 XML has no float
    assert '<ParentObjectId xsi:nil="true" />' in xml and '<BaselineProject>' in xml
    assert xml.count('<PricePerUnit>') == len(ASSIGNMENTS) - 1
    assert 's|00:00|f|00:00' in xer and 's|08:00|f|12:00' in xer
    assert 'Design ""Rev A"" drawings' in xer and 'Excavation\x7f\x7fZone A' in xer
    assert '\tTK_Active\t' in xer and '\tCS_MSO\t' in xer and '\tCS_MSOA' in xer
    assert '\tY\tPARITY-UP01\tParity Test Project - Update 01\t500' in xer   # project-root WBS
    assert '\t2500.5000\t' in xer                                             # 4-dp money
    assert xer.count('%T\tPROJECT') == 1 and '\t6900\tPARITY-BL\t' in xer


# ── A schedule exported WITHOUT its baseline, in both formats ─────────────────────────────
# XML without <BaselineProject> (it still names CurrentBaselineProjectObjectId) vs a P6 XER
# update export (BASELINE_EXPORT pointer only - genuine finding G3). Neither carries the
# baseline, so both must end the same way and SAY so, never silently diverge (P1 / P2).

@pytest.fixture(scope='module')
def parsed_nobl(files):
    return {'xml': parse_file(files['xml_nobl']), 'xer': parse_file(files['xer_nobl'])}


def test_no_baseline_pair_states_the_same_baseline_source(parsed_nobl):
    src = {f: getattr(parsed_nobl[f], 'baseline_source', None) for f in ('xml', 'xer')}
    assert src['xml'] and src['xml'] != 'embedded', src
    assert src['xml'] == src['xer'], src


def test_no_baseline_pair_baseline_by_id_agrees(parsed_nobl):
    assert _norm(parsed_nobl['xml'].baseline_by_id) == _norm(parsed_nobl['xer'].baseline_by_id)


def test_no_baseline_pair_has_no_baseline_budget(parsed_nobl):
    assert parsed_nobl['xml'].baseline_bac_by_activity == {}
    assert parsed_nobl['xer'].baseline_bac_by_activity == {}


def test_no_baseline_pair_names_the_missing_baseline(parsed_nobl):
    """Both formats still know WHICH baseline is missing, so the UI can ask for it by name/id."""
    for fmt in ('xml', 'xer'):
        assert parsed_nobl[fmt].project.get('baseline_object_id') == BASELINE['object_id'], fmt


# ── XER / date edge cases ─────────────────────────────────────────────────────────────────

def test_xer_with_baseline_project_first_still_reads_the_current_project(files):
    d = parse_file(files['xer_bl_first'])
    assert d.project.get('object_id') == PROJECT['object_id']
    assert sorted(a['id'] for a in d.activities.values()) == truth('activity', 'ids')
    assert _norm(d.baseline_by_id) == _norm(truth('data', 'baseline_by_id'))


def test_xer_blank_total_float_is_reconstructed(files):
    """P9: an XER whose total_float_hr_cnt is blank (SG_BASELINE.xer: 896/896 rows) gets the same
    float P6 would store - rebuilt from the remaining early/late dates on the activity calendar."""
    d = parse_file(files['xer_blank_tf'])
    got = {a['id']: (a['total_float_days'], a['is_critical']) for a in d.activities.values()}
    want = {code: (tf, tf is not None and tf <= 0)
            for code, tf in truth('activity', 'total_float_days').items()}
    assert _norm(got) == _norm(want)


@pytest.mark.parametrize('fmt', ['xml', 'xer'])
@pytest.mark.xfail(strict=True, reason='P22: date parsing - XML crashes / XER silently drops a '
                                       'date with fractional seconds')
def test_date_with_fractional_seconds_parses(files, fmt):
    d = parse_file(files[f'{fmt}_frac_dd'])
    assert d.project.get('data_date') == _d(PROJECT['data_date'])


def test_no_baseline_xer_names_the_baseline_from_baseline_export(parsed_nobl):
    """A P6 XER update export carries only BASELINE_EXPORT (id + name) - still name it, flag the
    stand-in dates 'self', and carry no baseline budget (finding P1, real SG / ALSTOM exports)."""
    d = parsed_nobl['xer']
    assert d.project.get('baseline_object_id') == BASELINE['object_id']
    assert d.project.get('baseline_name') == BASELINE['name']
    assert d.baseline_source == 'self' and d.baseline_bac_by_activity == {}
