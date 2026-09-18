"""Circular Logic module (Schedule Health Review).

A circular relationship (a loop) is a chain of activities whose links eventually
point back to their own start — e.g. A drives B, B drives C, C drives A. P6
cannot run its forward/backward pass (F9) while a loop exists, so a single loop
stops the whole schedule from calculating. This is a *blocking* defect: it must
be broken before any other health metric can be trusted.

One finding per distinct loop. The chain is listed in loop order with the first
activity repeated at the end so the closure is obvious. Score on the Schedule
Health Review model: score = 100 - Circular %, with the uniform grade legend.
"""
from p6_audit.findings import content_id
from p6_audit.scoring import linear_score, uniform_grade

MODULE = 'circular'
NAME = 'Circular Logic'


def _find_cycles(graph):
    """Iterative DFS over pred->succ edges. Returns each distinct loop as an
    ordered list of activity object-ids (e.g. [a, b, c] means a->b->c->a).
    Distinct = distinct set of member activities (one representative loop each).
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {oid: WHITE for oid in graph.activities}
    cycles = []
    seen = set()

    def succ_ids(oid):
        return [e['other'] for e in graph.succs_of(oid) if e['other'] in graph.activities]

    for root in graph.activities:
        if color[root] != WHITE:
            continue
        color[root] = GRAY
        path = [root]
        pos = {root: 0}
        stack = [(root, iter(succ_ids(root)))]
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                c = color[nxt]
                if c == GRAY:
                    # back edge -> loop from nxt's position on the path to here
                    cyc = path[pos[nxt]:]
                    key = frozenset(cyc)
                    if key not in seen:
                        seen.add(key)
                        cycles.append(list(cyc))
                elif c == WHITE:
                    color[nxt] = GRAY
                    pos[nxt] = len(path)
                    path.append(nxt)
                    stack.append((nxt, iter(succ_ids(nxt))))
                    advanced = True
                    break
                # BLACK -> fully explored, skip
            if not advanced:
                stack.pop()
                color[node] = BLACK
                path.pop()
                del pos[node]
    return cycles


def _aid(graph, oid):
    """Activity id (task code), falling back to the object-id when blank."""
    return graph.activities[oid]['id'] or oid


def run_circular(graph, config):
    total_real = sum(1 for oid in graph.activities if graph.is_real_activity(oid))
    cycles = _find_cycles(graph)

    # Canonicalise each loop: rotate so it starts at the smallest activity id,
    # so the finding id / chain order is stable across re-imports.
    canon = []
    for cyc in cycles:
        start = min(range(len(cyc)), key=lambda i: _aid(graph, cyc[i]))
        rotated = cyc[start:] + cyc[:start]
        canon.append(rotated)
    canon.sort(key=lambda c: (_aid(graph, c[0]), len(c), [_aid(graph, o) for o in c]))

    findings = []
    for i, cyc in enumerate(canon, start=1):
        first_id = _aid(graph, cyc[0])
        chain = [{'id': _aid(graph, o), 'name': graph.activities[o].get('name', '')} for o in cyc]
        chain.append(dict(chain[0]))  # repeat the first to close the loop
        findings.append({
            'finding_id':     content_id('CIRCULAR', first_id, str(i)),
            'loop_index':     i,
            'chain':          chain,
            'activity_count': len(cyc),
            'severity':       'Critical',   # a loop stops F9 outright — nothing milder applies
            'recommendation': 'Break one link in this loop so P6 can calculate a valid schedule',
        })

    loops = len(canon)
    activities_in_loops = len({o for cyc in canon for o in cyc})
    longest_loop = max((len(c) for c in canon), default=0)
    defect_pct = round(100.0 * activities_in_loops / total_real, 1) if (loops and total_real) else 0.0
    score = linear_score(defect_pct)

    return {
        'module': MODULE,
        'name': NAME,
        'kpis': {
            'total_activities':    total_real,
            'loops':               loops,
            'activities_in_loops': activities_in_loops,
            'longest_loop':        longest_loop,
            'circular_pct':        defect_pct,
        },
        'pct':      defect_pct,
        'score':    score,
        'grade':    uniform_grade(score),
        'blocking': bool(loops > 0),
        'findings': findings,
    }
