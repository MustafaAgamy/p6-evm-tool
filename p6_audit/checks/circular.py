from p6_audit.findings import Finding, resolve_severity


def _sccs(graph):
    """Iterative Tarjan over pred->succ edges. Returns list of SCC id-lists (size>1 or self-loop)."""
    index = {}
    low = {}
    on_stack = set()
    stack = []
    counter = [0]
    result = []
    nodes = list(graph.activities.keys())

    def succ_ids(oid):
        return [e['other'] for e in graph.succs_of(oid)]

    for root in nodes:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            node, pi = work[-1]
            if pi == 0:
                index[node] = low[node] = counter[0]
                counter[0] += 1
                stack.append(node)
                on_stack.add(node)
            recursed = False
            neighbors = succ_ids(node)
            if pi < len(neighbors):
                work[-1] = (node, pi + 1)
                nxt = neighbors[pi]
                if nxt not in index:
                    work.append((nxt, 0))
                    recursed = True
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if recursed:
                continue
            if pi >= len(neighbors):
                if low[node] == index[node]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        comp.append(w)
                        if w == node:
                            break
                    self_loop = node in succ_ids(node)
                    if len(comp) > 1 or self_loop:
                        result.append(comp)
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
    return result


def check_circular(graph, config):
    findings = []
    for comp in _sccs(graph):
        ids = sorted(graph.activities[o]['id'] for o in comp)
        anchor_oid = min(comp, key=lambda o: graph.activities[o]['id'])
        anchor = graph.activities[anchor_oid]
        chain = ' → '.join(ids + [ids[0]])
        findings.append(Finding(
            check_id='LOGIC-003', check_name='Circular Logic', category=anchor.get('category'),
            severity=resolve_severity('Critical', anchor.get('category'), True, config),
            activity_id=anchor['id'], activity_name=anchor['name'],
            wbs_path=graph.wbs_path(anchor_oid),
            summary=f'Logic loop of {len(comp)} activities — P6 cannot compute a valid schedule',
            basis=f'cycle: {chain}',
            recommendation='Break the loop by removing or re-typing one relationship in the chain.',
        ))
    return findings
