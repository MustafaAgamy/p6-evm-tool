"""WBS structure view + sequence-change roll-up for the Baseline Revision report.

Two neutral, presentation-oriented projections built from data the engine has
already computed — nothing here re-detects change, it only arranges it for the
report:

  * ``build_wbs_view``      — flattens each revision's WBS hierarchy (``data.wbs``,
                              parent-linked) into ordered, indented rows and marks
                              each node added / removed / moved (re-parented) by
                              comparing paths, using the ``diff_wbs`` result.
  * ``build_sequence_rollup`` — groups the already-detected sequence reversals by
                              their shared WBS branch and derives a coarse
                              direction tag from the before/after chains.

Pure functions: they read parsed ``ScheduleData`` / the ``diff_wbs`` dict / the
sequence list, never mutate them, and always return plain JSON-serialisable
structures. Every path is guarded so missing data yields an empty-but-valid
shape rather than an exception.
"""

from p6_evm.parser import full_wbs_path


# ── WBS hierarchy flattening ─────────────────────────────────────────────────

def _wbs_nodes(data):
    """Pre-order (depth-first, name-sorted) flatten of a revision's WBS tree.

    Returns a list of ``{oid, name, depth, path, parent}`` where ``path`` is the
    full root-first path and ``parent`` the path of the node above it. Guards a
    missing/empty ``wbs`` map (→ ``[]``) and cyclic parent links.
    """
    wbs = getattr(data, 'wbs', None) or {}
    if not wbs:
        return []

    children, roots = {}, []
    for oid, node in wbs.items():
        parent = (node or {}).get('parent_object_id')
        if parent and parent in wbs:
            children.setdefault(parent, []).append(oid)
        else:
            roots.append(oid)

    def _key(oid):
        return ((wbs.get(oid) or {}).get('name') or '', str(oid))

    roots.sort(key=_key)
    for kids in children.values():
        kids.sort(key=_key)

    nodes, seen = [], set()

    def visit(oid, depth):
        if oid in seen:            # defend against a cyclic parent link
            return
        seen.add(oid)
        node = wbs.get(oid) or {}
        path = full_wbs_path(oid, wbs)
        parent = path.rsplit(' > ', 1)[0] if ' > ' in path else ''
        nodes.append({
            'oid': oid,
            'name': node.get('name') or '',
            'depth': depth,
            'path': path,
            'parent': parent,
        })
        for c in children.get(oid, []):
            visit(c, depth + 1)

    for r in roots:
        visit(r, 0)
    return nodes


def _moved_paths(nodes0, nodes1):
    """Detect re-parented (moved) WBS nodes by comparing paths.

    A node is *moved* when its exact path is gone on the other side but a node
    with the same (non-empty) name exists there under a *different* parent — i.e.
    the branch persists but was re-parented. Returns ``(moved0, moved1)`` — the
    sets of rev0 and rev1 full paths so marked. Matching is greedy and 1-to-1.
    """
    p0 = {n['path'] for n in nodes0}
    p1 = {n['path'] for n in nodes1}

    gone0 = [n for n in nodes0 if n['name'] and n['path'] not in p1]
    new1 = [n for n in nodes1 if n['name'] and n['path'] not in p0]

    by_name1 = {}
    for n in new1:
        by_name1.setdefault(n['name'], []).append(n)

    moved0, moved1, used1 = set(), set(), set()
    for n in gone0:
        for m in by_name1.get(n['name'], ()):
            if m['path'] in used1 or m['parent'] == n['parent']:
                continue
            moved0.add(n['path'])
            moved1.add(m['path'])
            used1.add(m['path'])
            break
    return moved0, moved1


def build_wbs_view(rev0, rev1, wbs_changes):
    """Primavera colour-grouped WBS compare: each revision flattened to ordered,
    indented rows with a per-node state.

    Returns::

        {
          'rev0': [ {level:int, name:str, state:'unchanged'|'removed'|'moved'} ],
          'rev1': [ {level:int, name:str, state:'unchanged'|'added'|'moved'} ],
          'summary': {added, removed, moved, reparented},
        }

    ``added``/``removed`` states come from the ``diff_wbs`` result (which already
    folds simple renames away, so a rename shows as *unchanged* on both sides);
    ``moved`` is derived here by comparing paths. Summary counts: ``added`` /
    ``removed`` = WBS branches added / removed, ``moved`` = WBS nodes re-parented,
    ``reparented`` = activities re-parented (``diff_wbs['moved_activities']``).
    """
    wbs_changes = wbs_changes or {}
    added_paths = {(w or {}).get('path') for w in (wbs_changes.get('added') or [])}
    removed_paths = {(w or {}).get('path') for w in (wbs_changes.get('removed') or [])}

    nodes0 = _wbs_nodes(rev0)
    nodes1 = _wbs_nodes(rev1)
    moved0, moved1 = _moved_paths(nodes0, nodes1)

    def rows(nodes, moved, changed_paths, change_state):
        out = []
        for n in nodes:
            if n['path'] in moved:
                state = 'moved'
            elif n['path'] in changed_paths:
                state = change_state
            else:
                state = 'unchanged'
            out.append({'level': n['depth'], 'name': n['name'], 'state': state})
        return out

    rev0_rows = rows(nodes0, moved0, removed_paths, 'removed')
    rev1_rows = rows(nodes1, moved1, added_paths, 'added')

    # Count the resolved states so a re-parented (moved) node is never also tallied
    # as an add+remove — matching the report's "N added · N removed · N moved" line.
    return {
        'rev0': rev0_rows,
        'rev1': rev1_rows,
        'summary': {
            'added': sum(1 for r in rev1_rows if r['state'] == 'added'),
            'removed': sum(1 for r in rev0_rows if r['state'] == 'removed'),
            'moved': len(moved1),
            'reparented': int(wbs_changes.get('moved_activities') or 0),
        },
    }


# ── Sequence roll-up ─────────────────────────────────────────────────────────

def _branch(path):
    """Coarsen a full WBS path to its top branch (first two segments) for grouping."""
    if not path:
        return None
    segs = [s for s in path.split(' > ') if s]
    if not segs:
        return None
    return ' > '.join(segs[:2])


def _direction(chain0, chain1):
    """A coarse, deterministic direction tag for a re-sequence, read from the
    before/after chains: pure reversal → 'zone order reversed'; the same
    activities re-ordered another way → 'de-interleaved'; otherwise (re-linked to
    different neighbours / an overlap) → 'trades overlapped'."""
    c0 = [x for x in (chain0 or []) if x]
    c1 = [x for x in (chain1 or []) if x]
    if not c0 or not c1:
        return 'trades overlapped'
    if c1 == c0[::-1] and len(c0) >= 2:
        return 'zone order reversed'
    if set(c0) == set(c1) and len(set(c0)) >= 2:
        return 'de-interleaved'
    return 'trades overlapped'


def _seq_branch(s, matched):
    """The group branch for one reversal — its shared WBS branch, falling back to
    activity ``a``'s WBS branch (via ``matched``) and finally 'Cross-WBS'."""
    wbs = s.get('shared_wbs')
    if not wbs and matched is not None:
        a = ((getattr(matched, 'update_by_code', None) or {}).get(s.get('a'))
             or (getattr(matched, 'baseline_by_code', None) or {}).get(s.get('a'))
             or {})
        wbs = a.get('wbs_path')
    return _branch(wbs) or 'Cross-WBS'


def build_sequence_rollup(sequences, matched):
    """Group already-detected sequence reversals by shared WBS branch.

    Returns a list, most-populated group first::

        [ {group:str, count:int,
           items:[ {a_name, b_name, direction, chain0, chain1} ]} ]

    ``count`` is the number of re-sequences in the group (``len(items)``).
    ``direction`` is one of 'de-interleaved' | 'trades overlapped' |
    'zone order reversed'. Guards an empty / ``None`` sequence list (→ ``[]``).
    """
    groups = {}
    order = []
    for s in (sequences or []):
        g = _seq_branch(s, matched)
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append({
            'a_name': s.get('a_name') or s.get('a'),
            'b_name': s.get('b_name') or s.get('b'),
            'direction': _direction(s.get('chain0'), s.get('chain1')),
            'chain0': list(s.get('chain0') or []),
            'chain1': list(s.get('chain1') or []),
        })

    out = [{'group': g, 'count': len(groups[g]), 'items': groups[g]} for g in order]
    out.sort(key=lambda r: (-r['count'], r['group']))
    return out
