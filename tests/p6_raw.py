"""Read what PRIMAVERA P6 itself wrote into an export — independent of the tool's parser
(the final P6 test, comment 5: nothing here imports the tool).

Raw(path) → .project {id, name, data_date, finish}, .acts {code: {...}}, .rels [...], .cals {id: hpd}
All durations / floats in HOURS as P6 stores them; dates as datetime.
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime

REL = {'Finish to Start': 'FS', 'Start to Start': 'SS', 'Finish to Finish': 'FF', 'Start to Finish': 'SF',
       'PR_FS': 'FS', 'PR_SS': 'SS', 'PR_FF': 'FF', 'PR_SF': 'SF'}
STATUS = {'TK_NotStart': 'Not Started', 'TK_Active': 'In Progress', 'TK_Complete': 'Completed'}
TYPES = {'TT_Task': 'Task Dependent', 'TT_Rsrc': 'Resource Dependent', 'TT_LOE': 'Level of Effort',
         'TT_Mile': 'Start Milestone', 'TT_FinMile': 'Finish Milestone', 'TT_WBS': 'WBS Summary'}


def _dt(s):
    s = (s or '').strip()
    if not s:
        return None
    for f in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def _f(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


class Raw:
    def __init__(self, path):
        self.path = path
        self.acts, self.rels, self.cals, self.project = {}, [], {}, {}
        if path.lower().endswith('.xer'):
            self._xer()
        else:
            self._xml()

    # ── XML ──
    def _xml(self):
        root = ET.parse(self.path).getroot()
        ns = root.tag[:root.tag.index('}') + 1]
        t = lambda e, k: e.findtext(ns + k)
        for c in root.iter(ns + 'Calendar'):
            self.cals[t(c, 'ObjectId')] = _f(t(c, 'HoursPerDay'))
        prj = root.find(ns + 'Project')
        self.project = {'id': t(prj, 'Id'), 'name': t(prj, 'Name'), 'data_date': _dt(t(prj, 'DataDate')),
                        'finish': _dt(t(prj, 'ScheduledFinishDate')),
                        'default_cal': t(prj, 'ActivityDefaultCalendarObjectId')}
        self.wbs = {w.findtext(ns + 'ObjectId'): w.findtext(ns + 'ParentObjectId') for w in prj.findall(ns + 'WBS')}
        oid2code = {}
        for a in prj.findall(ns + 'Activity'):
            code = t(a, 'Id')
            oid2code[t(a, 'ObjectId')] = code
            cost = lambda *ks: sum(_f(t(a, k)) or 0.0 for k in ks)
            self.acts[code] = {
                'name': t(a, 'Name'), 'type': t(a, 'Type'), 'status': t(a, 'Status'), 'wbs': t(a, 'WBSObjectId'),
                'pl_start': _dt(t(a, 'PlannedStartDate')), 'pl_finish': _dt(t(a, 'PlannedFinishDate')),
                'start': _dt(t(a, 'StartDate')), 'finish': _dt(t(a, 'FinishDate')),
                'act_start': _dt(t(a, 'ActualStartDate')), 'act_finish': _dt(t(a, 'ActualFinishDate')),
                'pct': _f(t(a, 'PercentComplete')), 'tf_h': _f(t(a, 'TotalFloat')),
                'od_h': _f(t(a, 'PlannedDuration')), 'rd_h': _f(t(a, 'RemainingDuration')),
                'ref': _dt(t(a, 'RemainingEarlyFinishDate')), 'rlf': _dt(t(a, 'RemainingLateFinishDate')),
                'cal': t(a, 'CalendarObjectId'), 'cons': t(a, 'PrimaryConstraintType') or None,
                'cons2': t(a, 'SecondaryConstraintType') or None,
                'actual_cost': cost('ActualLaborCost', 'ActualNonLaborCost', 'ActualMaterialCost', 'ActualExpenseCost'),
                'at_compl_cost': cost('AtCompletionLaborCost', 'AtCompletionNonLaborCost',
                                      'AtCompletionMaterialCost', 'AtCompletionExpenseCost'),
            }
        C = self.calendars = XmlCalendars(self.path)
        if not any(a['tf_h'] is not None for a in self.acts.values()):
            # the file carries no TotalFloat → derive it
            for a in self.acts.values():
                if a['status'] != 'Completed' and a['ref'] and a['rlf']:
                    m = C.work_minutes(a['cal'], a['ref'], a['rlf'])
                    a['tf_h'] = m / 60.0
                    a['tf_derived'] = True
        # costs: an XML may carry them on the resource assignments instead of the activity
        oid_cost = {}
        for ra in prj.findall(ns + 'ResourceAssignment'):
            c = oid_cost.setdefault(t(ra, 'ActivityObjectId'), [0.0, 0.0, 0.0, []])
            c[0] += _f(t(ra, 'ActualCost')) or 0.0
            c[1] += _f(t(ra, 'AtCompletionCost')) or 0.0
            c[2] += _f(t(ra, 'PlannedCost')) or 0.0
            c[3].append((_dt(t(ra, 'PlannedStartDate')), _dt(t(ra, 'PlannedFinishDate')), _f(t(ra, 'PlannedCost')) or 0.0))
        for oid, (act_c, atc, plc, spans) in oid_cost.items():
            code = oid2code.get(oid)
            if code:
                a = self.acts[code]
                a['actual_cost'] += act_c
                a['at_compl_cost'] += atc
                a['planned_cost'] = a.get('planned_cost', 0.0) + plc
                a['cost_spans'] = spans
        for r in prj.findall(ns + 'Relationship'):
            p, s = oid2code.get(t(r, 'PredecessorActivityObjectId')), oid2code.get(t(r, 'SuccessorActivityObjectId'))
            if p and s:
                self.rels.append({'pred': p, 'succ': s, 'type': REL.get(t(r, 'Type'), t(r, 'Type')),
                                  'lag_h': _f(t(r, 'Lag')) or 0.0})

    # ── XER ──
    def _xer(self):
        tables, cur, fields = {}, None, None
        with open(self.path, encoding='cp1252', errors='replace') as fh:
            for line in fh:
                line = line.rstrip('\r\n')
                if line.startswith('%T'):
                    cur = line.split('\t')[1]; tables[cur] = []
                elif line.startswith('%F'):
                    fields = line.split('\t')[1:]
                elif line.startswith('%R') and cur:
                    vals = line.split('\t')[1:]
                    tables[cur].append(dict(zip(fields, vals + [''] * (len(fields) - len(vals)))))
        self.tables = tables
        for c in tables.get('CALENDAR', []):
            self.cals[c['clndr_id']] = _f(c.get('day_hr_cnt'))
        projs = tables.get('PROJECT', [])
        pr = max(projs, key=lambda p: sum(1 for x in tables.get('TASK', []) if x['proj_id'] == p['proj_id']))
        pid = pr['proj_id']
        name = next((w['wbs_name'] for w in tables.get('PROJWBS', []) if w['proj_id'] == pid and w.get('proj_node_flag') == 'Y'), '')
        self.project = {'id': pr.get('proj_short_name'), 'name': name, 'data_date': _dt(pr.get('last_recalc_date')),
                        'finish': _dt(pr.get('scd_end_date')), 'default_cal': pr.get('clndr_id')}
        self.wbs = {w['wbs_id']: w.get('parent_wbs_id') for w in tables.get('PROJWBS', []) if w['proj_id'] == pid}
        tid2code = {}
        cost_by_task = {}
        for r in tables.get('TASKRSRC', []):
            c = cost_by_task.setdefault(r['task_id'], [0.0, 0.0, 0.0])
            c[2] += _f(r.get('target_cost')) or 0
            c[0] += (_f(r.get('act_reg_cost')) or 0) + (_f(r.get('act_ot_cost')) or 0)
            c[1] += (_f(r.get('act_reg_cost')) or 0) + (_f(r.get('act_ot_cost')) or 0) + (_f(r.get('remain_cost')) or 0)
        for r in tables.get('PROJCOST', []):
            c = cost_by_task.setdefault(r['task_id'], [0.0, 0.0, 0.0])
            c[2] += _f(r.get('target_cost')) or 0
            c[0] += _f(r.get('act_cost')) or 0
            c[1] += (_f(r.get('act_cost')) or 0) + (_f(r.get('remain_cost')) or 0)
        for x in tables.get('TASK', []):
            if x['proj_id'] != pid:
                continue
            code = x['task_code']
            tid2code[x['task_id']] = code
            st = STATUS.get(x['status_code'], x['status_code'])
            act_s, act_f = _dt(x.get('act_start_date')), _dt(x.get('act_end_date'))
            start = act_s or _dt(x.get('restart_date')) or _dt(x.get('early_start_date')) or _dt(x.get('target_start_date'))
            finish = act_f or _dt(x.get('reend_date')) or _dt(x.get('early_end_date')) or _dt(x.get('target_end_date'))
            ct = x.get('complete_pct_type')
            pct = {'CP_Phys': _f(x.get('phys_complete_pct'))}.get(ct)
            if pct is None:
                od, rd = _f(x.get('target_drtn_hr_cnt')) or 0, _f(x.get('remain_drtn_hr_cnt')) or 0
                pct = (100.0 if st == 'Completed' else (max(0.0, (od - rd) / od * 100) if od else 0.0)) if ct == 'CP_Drtn' \
                    else _f(x.get('phys_complete_pct'))
            cst = cost_by_task.get(x['task_id'], [0.0, 0.0, 0.0])
            self.acts[code] = {
                'name': x['task_name'], 'type': TYPES.get(x['task_type'], x['task_type']), 'status': st,
                'wbs': x.get('wbs_id'), 'planned_cost': cst[2],
                'pl_start': _dt(x.get('target_start_date')), 'pl_finish': _dt(x.get('target_end_date')),
                'start': start, 'finish': finish, 'act_start': act_s, 'act_finish': act_f,
                'pct': (pct or 0.0) / 100.0, 'pct_type': ct,
                'tf_h': _f(x.get('total_float_hr_cnt')), 'od_h': _f(x.get('target_drtn_hr_cnt')),
                'rd_h': _f(x.get('remain_drtn_hr_cnt')), 'cal': x.get('clndr_id'),
                'cons': x.get('cstr_type') or None, 'cons2': x.get('cstr_type2') or None,
                'early_end': _dt(x.get('early_end_date')), 'late_end': _dt(x.get('late_end_date')),
                'actual_cost': cst[0], 'at_compl_cost': cst[1],
            }
        for r in tables.get('TASKPRED', []):
            p, s = tid2code.get(r['pred_task_id']), tid2code.get(r['task_id'])
            if p and s:
                self.rels.append({'pred': p, 'succ': s, 'type': REL.get(r['pred_type'], r['pred_type']),
                                  'lag_h': _f(r.get('lag_hr_cnt')) or 0.0})

    def hpd(self, code):
        a = self.acts[code]
        return self.cals.get(a['cal']) or self.cals.get(self.project.get('default_cal')) or 8.0


# ── P6's total float for an XML that does not store it: Remaining Late Finish − Remaining Early
#    Finish in working time on the activity's own calendar (the project's float type is
#    'finish float').  Calendars read straight from the XML: work week + holidays / exceptions.
from datetime import timedelta as _td


def _mins(hms):
    h, m, s = (int(x) for x in hms.split(':'))
    return h * 60 + m + (1 if m % 10 == 9 else 0)          # P6 writes 15:59 for a 16:00 end


class XmlCalendars:
    def __init__(self, path):
        root = ET.parse(path).getroot()
        ns = root.tag[:root.tag.index('}') + 1]
        self.cal = {}
        for c in root.iter(ns + 'Calendar'):
            week = {}
            ww = c.find(ns + 'StandardWorkWeek')
            for h in (ww.findall(ns + 'StandardWorkHours') if ww is not None else []):
                ivs = [(_mins(w.findtext(ns + 'Start')), _mins(w.findtext(ns + 'Finish')))
                       for w in h.findall(ns + 'WorkTime') if w.findtext(ns + 'Start')]
                week[h.findtext(ns + 'DayOfWeek')] = ivs
            exc = {}
            he = c.find(ns + 'HolidayOrExceptions')
            for x in (he.findall(ns + 'HolidayOrException') if he is not None else []):
                d = _dt(x.findtext(ns + 'Date'))
                if d:
                    exc[d.date()] = [(_mins(w.findtext(ns + 'Start')), _mins(w.findtext(ns + 'Finish')))
                                     for w in x.findall(ns + 'WorkTime') if w.findtext(ns + 'Start')]
            self.cal[c.findtext(ns + 'ObjectId')] = {'week': week, 'exc': exc,
                                                     'base': c.findtext(ns + 'BaseCalendarObjectId') or None}

    def _day(self, cid, d):
        c = self.cal.get(cid) or {}
        if d in c.get('exc', {}):
            return c['exc'][d]
        if c.get('base') and not c.get('week'):
            return self._day(c['base'], d)
        return c.get('week', {}).get(d.strftime('%A'), [])

    def work_minutes(self, cid, a, b):
        """Signed working minutes from datetime a to b on calendar cid."""
        if a is None or b is None:
            return None
        sign = 1
        if b < a:
            a, b, sign = b, a, -1
        tot, d = 0, a.date()
        while d <= b.date():
            lo = (a.hour * 60 + a.minute) if d == a.date() else 0
            hi = (b.hour * 60 + b.minute) if d == b.date() else 24 * 60
            for s, e in self._day(cid, d):
                tot += max(0, min(e, hi) - max(s, lo))
            d += _td(days=1)
        return sign * tot
