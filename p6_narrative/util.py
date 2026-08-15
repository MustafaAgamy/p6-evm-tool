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


def wbs_grouping(wbs):
    """Map each WBS id to its 'major branch' id, and list the branch ids in order.

    Adaptive so single-root projects still get a real breakdown: if the file has one
    top root, the major branches are that root's children; otherwise the roots
    themselves. Returns ``(group_of, branch_ids)`` where ``group_of[wbs_id]`` is the
    branch id its subtree belongs to.
    """
    children, roots = {}, []
    for oid, node in wbs.items():
        parent = node.get('parent_object_id')
        if parent and parent in wbs:
            children.setdefault(parent, []).append(oid)
        else:
            roots.append(oid)
    branch_ids = children[roots[0]] if (len(roots) == 1 and children.get(roots[0])) else roots

    group_of, seen = {}, set()

    def mark(oid, branch):
        if oid in seen:
            return
        seen.add(oid)
        group_of[oid] = branch
        for c in children.get(oid, []):
            mark(c, branch)

    for br in branch_ids:
        mark(br, br)
    for r in roots:                     # the single top root itself, if it holds activities
        group_of.setdefault(r, r)
    return group_of, branch_ids


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
