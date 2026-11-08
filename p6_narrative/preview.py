"""Live previews for the AI Assistant (Ibrahim, 20-Oct): "if you pick this activity code, the
section reads like this; if you pick these two codes, like this" - computed from the planner's own
file with the SAME engines that build §7 Scope of Work and §11 Sequence of Work, so the example is
exactly the final output, only shortened for the chat.
"""


def _m(v):
    v = float(v or 0)
    return f'{v / 1e6:,.1f} M' if abs(v) >= 1e6 else f'{v:,.0f}'


def scope_preview(data, codes, currency=''):
    """Compact §7 preview for an ordered list of activity codes (any number) - the same opening
    paragraph, bar and item-by-item description section 7 prints, cut to the first items."""
    from p6_narrative import scope as S
    codes = [c for c in (codes or []) if c]
    if not codes:
        return None
    sc = S.scope_sections(list(data.activities.values()), data.wbs, getattr(data, 'bac_by_activity', None),
                          data.activity_code_types, {'scope_codes': codes}, currency)

    def share(n):
        return '%s%%' % S._fmt_pct(n.get('pct') or 0) + ((' (%d activities)' % n['acts']) if n.get('acts') else '')

    def trim(nodes, depth, k):
        return [{'name': n.get('name'), 'alike': n.get('count') if (n.get('count') or 0) > 1 else None,
                 'share': ('%s%% of the scope' % S._fmt_pct(n.get('pct') or 0) + ((' · %d activities' % n['acts']) if n.get('acts') else ''))
                 if depth == 0 else share(n),
                 'kids': trim(n.get('children') or [], depth + 1, 5) if depth < 2 else []} for n in (nodes or [])[:k]]

    casc = sc.get('cascade') or []
    return {'codes': codes, 'paragraph': sc.get('paragraph') or '', 'split_code': sc.get('split_code'),
            'split': [{'name': r['name'], 'pct': r['pct']} for r in (sc.get('split') or [])[:6]],
            'items': trim(casc, 0, 3 if len(codes) >= 2 else 6), 'more_items': max(0, len(casc) - (3 if len(codes) >= 2 else 6)),
            'by_count': sc.get('basis') == 'count',
            'unclassified': sc.get('uncoded_pct') or None}


def sequence_preview(data, codes):
    """Compact §11 preview for one analysis (1 code = whole-project order, 2 codes = per area)."""
    from p6_narrative import seqflow
    codes = [c for c in (codes or []) if c][:2]
    if not codes:
        return None
    p = seqflow.sequence_analyses(list(data.activities.values()), data.wbs,
                                  getattr(data, 'relationships', []) or [],
                                  code_types=data.activity_code_types, analyses=[{'codes': codes}], setup={})
    an = (p.get('analyses') or [None])[0]
    if not an:
        return None
    out = {'codes': codes, 'kind': an.get('kind'), 'title': an.get('title')}
    if an.get('kind') == 'single':
        out['steps'] = [s.get('name') for s in (an.get('steps') or [])]
    else:
        out['groups'] = [{'label': g.get('label'), 'count': g.get('count'), 'steps': [s.get('name') for s in (g.get('steps') or [])]}
                         for g in (an.get('groups') or [])[:4]]
        out['more_groups'] = max(0, len(an.get('groups') or []) - 4)
        out['no_code'] = an.get('no_code') or []
    return out


def examples(data, kind, auto_codes, picks=None):
    """The example set the assistant shows: for scope, the detected order cut at 1, 2 and 3 codes
    (+ the planner's own pick); for sequence, the first code alone and the 2nd -> 3rd pair."""
    auto = [c for c in (auto_codes or []) if c]
    sets = []
    if kind == 'scope':
        for n in (1, 2, 3):
            if len(auto) >= n:
                sets.append(auto[:n])
    else:
        if auto:
            sets.append(auto[:1])
        if len(auto) >= 3:
            sets.append(auto[1:3])
        elif len(auto) == 2:
            sets.append(auto[:2])
    for p in (picks or []):
        if p and p not in sets:
            sets.append(p)
    fn = scope_preview if kind == 'scope' else sequence_preview
    out = []
    for s in sets:
        try:
            pv = fn(data, s)
        except Exception:
            pv = None
        if pv:
            out.append(pv)
    return out
