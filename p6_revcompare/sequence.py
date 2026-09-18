"""Sequence-change detection from schedule logic (not from sorting by date).

A sequence change is a reversal of planned execution order between two matched
activities: A was planned before B (a logic path A→…→B) and is now planned after
it (B→…→A). At the relationship level this shows up as the directed edge (A,B)
disappearing while (B,A) appears — whether the planner literally flipped the link
or removed one and added the other. We detect that reversal over the matched
activities, then build a short local chain from each revision so the report can
show the before-vs-after order.

Reads only the code-keyed relationship maps on a ``MatchedSchedules`` — pure and
unit-testable.
"""


def _adjacency(rels, matched_codes):
    """(pred_code, succ_code) map -> {code: {'succ': set, 'pred': set}} over matched codes."""
    adj = {c: {'succ': set(), 'pred': set()} for c in matched_codes}
    mc = set(matched_codes)
    for (p, s) in rels:
        if p in mc and s in mc:
            adj[p]['succ'].add(s)
            adj[s]['pred'].add(p)
    return adj


def _local_chain(adj, by_code, a, b):
    """A short ordered chain [pred?, a, b, succ?] for a revision where a precedes b,
    using one representative matched predecessor of `a` and successor of `b`."""
    def _name(code):
        return (by_code.get(code) or {}).get('name') or code
    chain = []
    preds = sorted(adj.get(a, {}).get('pred', set()) - {b})
    if preds:
        chain.append(_name(preds[0]))
    chain.append(_name(a))
    chain.append(_name(b))
    succs = sorted(adj.get(b, {}).get('succ', set()) - {a})
    if succs:
        chain.append(_name(succs[0]))
    return chain


def detect_sequence_changes(matched):
    """Order reversals between matched activities. Returns a list of
    {a, b, a_name, b_name, rev0, rev1, chain0, chain1, shared_wbs}, most-connected first.

    A reversal: edge (a,b) exists in rev0 and is gone in rev1, while edge (b,a) exists in
    rev1 and was absent in rev0. Reported once per unordered pair."""
    codes = matched.matched_codes
    e0 = set((p, s) for (p, s) in matched.baseline_rels if p in set(codes) and s in set(codes))
    e1 = set((p, s) for (p, s) in matched.update_rels if p in set(codes) and s in set(codes))
    adj0 = _adjacency(matched.baseline_rels, codes)
    adj1 = _adjacency(matched.update_rels, codes)

    seen = set()
    out = []
    for (a, b) in e0:
        if (b, a) in e1 and (a, b) not in e1 and (b, a) not in e0:
            key = frozenset((a, b))
            if key in seen:
                continue
            seen.add(key)
            a0 = matched.baseline_by_code.get(a) or matched.update_by_code.get(a) or {}
            b0 = matched.baseline_by_code.get(b) or matched.update_by_code.get(b) or {}
            wbs = a0.get('wbs_path') if a0.get('wbs_path') == b0.get('wbs_path') else None
            # Codes whose logic changed only because of THIS reversal — the two activities plus
            # their immediate re-linked neighbours — so the register can fold them into one row.
            involved = {a, b}
            involved |= (adj0.get(a, {}).get('pred', set()) | adj1.get(b, {}).get('pred', set()))
            involved |= (adj0.get(b, {}).get('succ', set()) | adj1.get(a, {}).get('succ', set()))
            out.append({
                'a': a, 'b': b,
                'a_name': a0.get('name') or a, 'b_name': b0.get('name') or b,
                'rev0': f'{a0.get("name") or a} → {b0.get("name") or b}',
                'rev1': f'{b0.get("name") or b} → {a0.get("name") or a}',
                'chain0': _local_chain(adj0, matched.baseline_by_code, a, b),
                'chain1': _local_chain(adj1, matched.update_by_code, b, a),
                'shared_wbs': wbs,
                'involved': sorted(involved),
            })
    # Most-connected reversals first (they read as the more structural changes).
    out.sort(key=lambda r: -(len(r['chain0']) + len(r['chain1'])))
    return out
