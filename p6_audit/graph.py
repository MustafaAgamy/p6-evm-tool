class ScheduleGraph:
    def __init__(self, data):
        self.activities = data.activities
        self.calendars = getattr(data, 'calendars', {}) or {}  # for working-day lag in suggestions
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

    def wbs_path(self, oid):
        act = self.activities.get(oid, {})
        return act.get('wbs_path', '') or ''

    def critical_ids(self):
        return {oid for oid, a in self.activities.items() if a.get('is_critical')}
