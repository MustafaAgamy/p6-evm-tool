"""MatchedSchedules — reconcile a baseline and an update, keyed by Activity code.

ObjectIds are per-file, so the same activity carries different ObjectIds in the
baseline and the update. Everything here matches on the Activity code (``id``):
activities by code, relationships by ``(pred_code, succ_code)``.
"""

_MILESTONE_TYPES = ('StartMilestone', 'FinishMilestone')


def _index_by_code(data):
    """Activity code -> activity dict. Last one wins if a code repeats (unusual)."""
    out = {}
    for act in data.activities.values():
        code = act.get('id')
        if code:
            out[code] = act
    return out


def _rels_by_pair(data):
    """(pred_code, succ_code) -> {type, lag_days, pred_name, succ_name}.

    Resolves each relationship's per-file ObjectId endpoints to Activity codes so
    the baseline and update relationship maps share a key space. Relationships that
    reference an activity absent from this file are dropped.
    """
    by_oid = data.activities
    out = {}
    for rel in data.relationships:
        pred = by_oid.get(rel.get('pred_id'))
        succ = by_oid.get(rel.get('succ_id'))
        if not pred or not succ:
            continue
        pc, sc = pred.get('id'), succ.get('id')
        if not pc or not sc:
            continue
        this = (rel.get('type', 'FS'), rel.get('lag_hours', 0.0) or 0.0)
        prev = out.get((pc, sc))
        out[(pc, sc)] = {
            'type': rel.get('type', 'FS'),
            'lag_days': rel.get('lag_days', 0.0) or 0.0,
            'lag_hours': rel.get('lag_hours', 0.0) or 0.0,
            'pred_name': pred.get('name', ''),
            'succ_name': succ.get('name', ''),
            # P6 allows several links between the same two activities (e.g. SS and FF).  The
            # pair keeps one entry, but it remembers every link: 'links' is how many P6 holds
            # (so relationship totals equal P6's) and 'multi' is their signature (so a change
            # to ANY of them is seen as a change).
            'links': (prev['links'] if prev else 0) + 1,
            'all_links': (prev['all_links'] if prev else ()) + (this,),
        }
    for v in out.values():
        v['multi'] = ' + '.join('%s%+g' % (t, h) for t, h in sorted(v['all_links'])) if v['links'] > 1 else ''
    return out


def rel_count(rels):
    """How many relationships P6 holds in a ``_rels_by_pair`` map (a pair may carry several)."""
    return sum((v.get('links') or 1) for v in (rels or {}).values())


class MatchedSchedules:
    def __init__(self, baseline, update):
        self.baseline = baseline
        self.update = update
        self.baseline_by_code = _index_by_code(baseline)
        self.update_by_code = _index_by_code(update)
        self.baseline_rels = _rels_by_pair(baseline)
        self.update_rels = _rels_by_pair(update)

    @property
    def matched_codes(self):
        return sorted(set(self.baseline_by_code) & set(self.update_by_code))

    @property
    def added_activity_codes(self):
        return sorted(set(self.update_by_code) - set(self.baseline_by_code))

    @property
    def removed_activity_codes(self):
        return sorted(set(self.baseline_by_code) - set(self.update_by_code))

    @property
    def milestone_codes(self):
        """Codes of matched milestone activities (per the update's task_type)."""
        out = []
        for code in self.matched_codes:
            act = self.update_by_code.get(code, {})
            if act.get('task_type') in _MILESTONE_TYPES:
                out.append(code)
        return out
