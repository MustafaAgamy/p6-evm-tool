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

    def as_dict(self):
        return asdict(self)


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
