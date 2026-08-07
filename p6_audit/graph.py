class ScheduleGraph:
    def __init__(self, data):
        self.activities = data.activities
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
        return bool(act) and act.get('task_type') == 'Task'

    def wbs_path(self, oid):
        act = self.activities.get(oid, {})
        return act.get('wbs_path', '') or ''

    def critical_ids(self):
        return {oid for oid, a in self.activities.items() if a.get('is_critical')}
