"""Live previews for the AI Assistant (Ibrahim, 20-Oct): "if you pick this activity code, the
section reads like this; if you pick these two codes, like this" - computed from the planner's own
file with the SAME engines that build §7 Scope of Work and §11 Sequence of Work, so the example is
exactly the final output, only shortened for the chat.
"""


def _m(v):
    v = float(v or 0)
    return f'{v / 1e6:,.1f} M' if abs(v) >= 1e6 else f'{v:,.0f}'


def scope_preview(data, codes, currency=''):
    """Compact §7 preview for an ordered list of 1-3 activity codes."""
    from p6_narrative import scope as S
    codes = [c for c in (codes or []) if c]
    if not codes:
        return None
    sc = S.scope_sections(list(data.activities.values()), data.wbs, getattr(data, 'bac_by_activity', None),
                          data.activity_code_types, {'scope_codes': codes}, currency)
    top = [{'name': d.get('name'), 'value': _m(d.get('cost')), 'pct': d.get('pct')} for d in (sc.get('disciplines') or [])[:6]]
    drill = []
    casc = (sc.get('cascade') or [])
    if len(codes) >= 2 and casc:
        first = casc[0]
        for ch in (first.get('children') or [])[:4]:
            row = {'name': ch.get('name'), 'value': _m(ch.get('cost')), 'pct': ch.get('pct'), 'count': ch.get('count')}
            if len(codes) >= 3:
                row['parts'] = [{'name': g.get('name'), 'pct': g.get('pct')} for g in (ch.get('children') or [])[:5]]
            drill.append(row)
        drill = {'parent': first.get('name'), 'rows': drill}
    return {'codes': codes, 'total': _m(sc.get('total')), 'top': top, 'drill': drill or None,
            'unclassified': next((d.get('pct') for d in (sc.get('disciplines') or []) if d.get('name') == 'Unclassified'), None)}


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
