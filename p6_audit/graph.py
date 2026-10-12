from collections import Counter

NEAR_CRITICAL_MIN_DAYS = 1   # P6 filter: Total Float 'is within range' 1d (min) .. 10d (max)


def is_near_critical(total_float_days, near_days, min_days=NEAR_CRITICAL_MIN_DAYS):
    """Near-critical exactly as the P6 filter 'Total Float is within range <min>d - <max>d' lists it
    (Ibrahim, 2026-10-12): 1 day <= total float <= 10 days, both ends included. A float between 0
    and 1 day is neither critical nor near-critical. ONE rule for every Schedule Health check."""
    return total_float_days is not None and (min_days - 1e-9) <= total_float_days <= (near_days + 1e-9)


class ScheduleGraph:
    def __init__(self, data):
        self.activities = data.activities
        # P6 never flags a Level of Effort / WBS Summary activity Critical. The reader's is_critical
        # already follows that (p6_evm.calendars.p6_is_critical); kept here too so a schedule
        # handed over with its own flags is counted the same way. Copies - the input is not edited.
        spans = {oid: dict(a, is_critical=False) for oid, a in data.activities.items()
                 if a.get('is_critical') and a.get('task_type') in ('LOE', 'WBSSummary')}
        if spans:
            self.activities = {**data.activities, **spans}
        self.calendars = getattr(data, 'calendars', {}) or {}  # for working-day lag in suggestions
        self._set_hours_basis()
        self.data_date = (getattr(data, 'project', None) or {}).get('data_date')  # update cut-off
        self._succ = {oid: [] for oid in self.activities}
        self._pred = {oid: [] for oid in self.activities}
        for rel in data.relationships:
            p, s = rel['pred_id'], rel['succ_id']
            if p not in self.activities or s not in self.activities:
                continue  # ignore dangling relationship records
            edge_type = rel.get('type', 'FS')
            lag = rel.get('lag_days', 0.0)
            self._succ[p].append({'other': s, 'type': edge_type, 'lag_days': lag})
            self._pred[s].append({'other': p, 'type': edge_type, 'lag_days': lag})

    # -- hours per day (review decision 2026-10-11) ---------------------------------------
    # Days = hours / the working day of the calendar ASSIGNED TO THE ACTIVITY - each activity on
    # its own calendar, as P6 holds it. `hours_basis` only describes that for the report.
    def day_hours(self, act):
        cal = self.calendars.get((act or {}).get('calendar_id'))
        return (getattr(cal, 'day_hours', None) or 8.0) if cal else 8.0

    def _set_hours_basis(self):
        counts = Counter(round(self.day_hours(a), 4) for a in self.activities.values())
        total = sum(counts.values())
        self.hours_basis = {
            'mode': 'own',                      # each activity on its own assigned calendar
            'days': [{'hours': h, 'activities': n, 'pct': round(100.0 * n / total, 1)}
                     for h, n in counts.most_common()],
        }

    def succs_of(self, oid):
        return self._succ.get(oid, [])

    def preds_of(self, oid):
        return self._pred.get(oid, [])

    # Plan-documented aliases
    successors = succs_of
    predecessors = preds_of

    def is_real_activity(self, oid):
        act = self.activities.get(oid)
        # real work = Task Dependent AND Resource Dependent (P6 and DCMA count both as tasks;
        # milestones, LOE and WBS summaries are not).  Resource Dependent used to be left out of
        # every Schedule Health check (final P6 test, comment 5: Grain Bulk 1,466 vs P6 1,467).
        return bool(act) and act.get('task_type') in ('Task', 'ResourceDependent')

    def is_span_activity(self, oid):
        """Level of Effort / WBS Summary: an activity that only SPANS other work. P6 takes its dates
        from the activities it is tied to and never drives them, so a chain that returns to its
        start through one is not a loop in P6 (review comment 3: Alstom, P6 schedules it)."""
        act = self.activities.get(oid)
        return bool(act) and act.get('task_type') in ('LOE', 'WBSSummary')

    # ── P6's own activity counts (comments 48-52) ─────────────────────────────────────
    # P6 lists — and its Critical / float filters count — EVERY activity type (tasks, milestones,
    # Level of Effort, WBS summaries). Percentages are over the activities still to do (Not
    # Started + In Progress); with nothing completed (a baseline) that is every activity.
    @staticmethod
    def is_completed(act):
        s = (act.get('status') or '').replace(' ', '').lower()
        if s == 'completed':
            return True
        if s in ('inprogress', 'notstarted'):
            return False
        return bool(act.get('actual_finish'))

    def p6_all(self):
        """Every activity in the file, as P6's Activities window counts them."""
        return list(self.activities.items())

    def p6_remaining(self):
        """Every activity not completed (Not Started + In Progress) — the base of each %."""
        return [(oid, a) for oid, a in self.activities.items() if not self.is_completed(a)]

    # -- P6's count under each major WBS (review 2026-10-11) -----------------------------
    # P6 groups the Activities window by WBS and counts EVERY activity under each band - every
    # type, completed included. Each check's WBS table starts from these counts.
    def wbs_key(self):
        """activity -> its major WBS (the top-level WBS as named in P6)."""
        if getattr(self, '_wbs_key', None) is None:
            from p6_audit.modules.float_management import _top_wbs_key
            self._wbs_key = _top_wbs_key([self.wbs_path(oid) for oid in self.activities])
        return self._wbs_key

    def major_wbs(self, oid):
        return self.wbs_key()(self.wbs_path(oid))

    # -- the Construction WBS (review 2026-10-12) ------------------------------------------
    # Construction = every activity under a WBS node NAMED construction, at whatever level that
    # node sits (top level 'Construction Works', or 'Production Zone > Construction'). Only a
    # schedule with no such node falls back to a top-level WBS that reads as construction.
    def _segments(self, oid):
        """The activity's WBS names from its major WBS downwards."""
        segs = [x.strip() for x in (self.wbs_path(oid) or '').split('>') if x.strip()]
        major = self.major_wbs(oid)
        return segs[segs.index(major):] if major in segs else segs

    def _construction_level(self):
        """How deep the Construction WBS sits: 0 = a major WBS is named construction, 1 = the level
        under it, ... - the SHALLOWEST level carrying the name, so a deeper 'Construction Drawings'
        under Engineering is not taken for it. None when no WBS is named construction."""
        if not hasattr(self, '_con_level'):
            levels = [i for oid in self.activities for i, x in enumerate(self._segments(oid))
                      if 'construction' in x.lower()]
            self._con_level = min(levels) if levels else None
        return self._con_level

    def is_construction(self, oid):
        level = self._construction_level()
        if level is not None:
            segs = self._segments(oid)
            return len(segs) > level and 'construction' in segs[level].lower()
        from p6_evm.classify import classify_wbs_name
        return classify_wbs_name(self.major_wbs(oid)) == 'Construction'

    def scope_group(self, oid):
        """The WBS an activity is counted under for a construction scope: the path down to its
        Construction node when it has one ('Production Zone > Construction'), else its major WBS."""
        level = self._construction_level()
        if level and self.is_construction(oid):
            return ' > '.join(self._segments(oid)[:level + 1])
        return self.major_wbs(oid)

    def p6_wbs_rows(self, key=None, **counters):
        """One row per major WBS, biggest first: {'wbs', 'activities' (every activity, as P6
        counts the band), 'remaining' (not completed)} plus one count per ``name=test(oid, act)``."""
        rows = {}
        for oid, act in self.activities.items():
            r = rows.setdefault((key or self.major_wbs)(oid), dict({'activities': 0, 'remaining': 0},
                                                         **{name: 0 for name in counters}))
            r['activities'] += 1
            r['remaining'] += 0 if self.is_completed(act) else 1
            for name, test in counters.items():
                r[name] += 1 if test(oid, act) else 0
        out = [dict({'wbs': wbs}, **r) for wbs, r in rows.items()]
        out.sort(key=lambda r: (-r['activities'], r['wbs']))
        return out

    def wbs_path(self, oid):
        act = self.activities.get(oid, {})
        return act.get('wbs_path', '') or ''

    def critical_ids(self):
        return {oid for oid, a in self.activities.items() if a.get('is_critical')}
