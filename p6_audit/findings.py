import hashlib
from dataclasses import dataclass, asdict

SEVERITY_ORDER = ['Low', 'Medium', 'High', 'Critical']


@dataclass
class Finding:
    check_id: str
    check_name: str
    category: str | None
    severity: str
    activity_id: str
    activity_name: str
    wbs_path: str
    related_activity_id: str | None = None
    related_activity_name: str | None = None
    summary: str = ''
    basis: str = ''
    recommendation: str = ''
    confidence: float | None = None
    finding_id: str = ''

    def __post_init__(self):
        # Deterministic content id: re-importing the same schedule yields the
        # same finding_id, so Plan 2 can track a finding as "still open" across
        # snapshots. `basis` is part of the key so two findings on one activity
        # from the same check (e.g. dangling start AND finish under LOGIC-002)
        # do not collide. AI-layer findings get their own id the same way.
        if not self.finding_id:
            key = '|'.join((
                self.check_id or '',
                self.activity_id or '',
                self.related_activity_id or '',
                self.basis or '',
            ))
            self.finding_id = hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]

    def as_dict(self):
        # Lead with finding_id to match the Global Finding Output Standard order
        d = asdict(self)
        return {'finding_id': d.pop('finding_id'), **d}


def _rank(sev):
    return SEVERITY_ORDER.index(sev) if sev in SEVERITY_ORDER else 0


def resolve_severity(check_base, category, is_critical, config):
    audit_cfg = config.get('audit', {})
    default = audit_cfg.get('default_severity', 'Medium')
    cat_base = audit_cfg.get('category_severity', {}).get(category, default)
    base = check_base if _rank(check_base) >= _rank(cat_base) else cat_base
    if is_critical:
        return 'Critical'
    return base
