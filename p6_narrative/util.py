"""Shared, dependency-free helpers for the narrative assembler."""


def top_wbs_name(wbs_id, wbs):
    """Name of the highest WBS ancestor of ``wbs_id`` (its top-level branch)."""
    seen = set()
    cur, last = wbs_id, None
    while cur and cur not in seen and cur in wbs:
        seen.add(cur)
        node = wbs[cur]
        if node.get('name'):
            last = node['name']
        parent = node.get('parent_object_id')
        if not parent or parent not in wbs:
            break
        cur = parent
    return last


def as_date(x):
    """Coerce a datetime/date/ISO-string to a date, or None."""
    from datetime import date, datetime
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    try:
        return datetime.fromisoformat(str(x)[:19]).date()
    except ValueError:
        return None
