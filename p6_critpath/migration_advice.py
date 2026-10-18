"""Float-migration recommendation by building and trade (Ibrahim, comment 91 round 3).

Uses two activity codes of the current schedule: a LOCATION code (building / area / zone) and a
TRADE code (type of works / discipline). The activities that turned critical are crossed by the
two, the worst cells become the recommendations (count, average float lost), and the open
critical activities with the deepest negative float are named. Measured from the file; only the
mitigation wording is a planner's suggestion picked from the trade.

Everything works on the float_migration dict the report carries (its rows hold each activity's
codes), so the screen, the PDF and the Excel give the same answer for the codes picked.
"""

_LOC_WORDS = ('area', 'zone', 'building', 'location', 'block', 'tower', 'silo', 'level', 'floor', 'plot', 'unit', 'structure')
_TRADE_WORDS = ('type of work', 'trade', 'discipline', 'work type', 'scope', 'craft', 'works')
_TRADE_VALUES = ('civil', 'concrete', 'steel', 'mechanical', 'electrical', 'equipment', 'mep', 'piping',
                 'cable', 'finishing', 'architect', 'instrument', 'hvac', 'plumbing', 'installation')

_MITIGATION = (
    (('civil', 'concrete', 'foundation', 'pile', 'raft', 'sog', 'excavat', 'formwork', 'rft'),
     'add a second civil crew / formwork set, or overlap the pours (FS → SS with a lag) to win back the float'),
    (('arc', 'finish', 'block', 'plaster', 'paint', 'tile', 'ceiling', 'door', 'window'),
     'open more rooms / areas in parallel with an extra finishing crew, and release them from the structure early'),
    (('steel', 'catwalk'),
     'pre-assemble at ground level in parallel with the erection, and expedite the steel delivery'),
    (('cable', 'electrical', 'mep', 'instrument', 'hvac', 'plumbing'),
     'add a cable-pulling / MEP crew and work two zones in parallel; release containment and access early'),
    (('mechanical', 'installation', 'equipment', 'conveyor', 'piping'),
     'split the installation into two fronts or add a crew, and release the work areas ahead of it first'),
    (('design', 'engineering', 'submittal', 'approval', 'drawing', 'as-built'),
     'fast-track the review: weekly approval meetings and partial submittals'),
    (('procure', 'deliver', 'material', 'supply'),
     'expedite the delivery: split shipments and confirm the supplier dates'),
)
_DEFAULT_MITIGATION = 'add resources, or run it in parallel with its predecessor where the logic allows'

_TURNED = ('near_to_crit', 'safe_to_crit')
NO_VALUE = '(no value)'


def mitigation_for(*texts):
    low = ' '.join(t for t in texts if t).lower()
    for words, text in _MITIGATION:
        if any(w in low for w in words):
            return text
    return _DEFAULT_MITIGATION


def code_types(rows):
    """Every activity-code type carried by the activities that moved, with how many of the
    turned-critical activities carry a value - the picker lists them, most used first."""
    turned = [r for r in rows if r.get('kind') in _TURNED]
    cov = {}
    for r in turned:
        for t, v in (r.get('codes') or {}).items():
            if v:
                cov[t] = cov.get(t, 0) + 1
    return [{'type': t, 'covered': n} for t, n in sorted(cov.items(), key=lambda x: (-x[1], x[0]))]


def pick_codes(rows):
    """The default location and trade codes: by the code name first, then by its values, among
    the codes that cover at least a fifth of the turned-critical activities."""
    types = code_types(rows)
    turned = [r for r in rows if r.get('kind') in _TURNED]
    n = len(turned) or 1
    usable = [t for t in types if t['covered'] >= 0.2 * n] or types

    def values(t):
        return {(r.get('codes') or {}).get(t) for r in turned} - {None, ''}

    def trade_score(t):
        name = t['type'].lower()
        vals = ' '.join(values(t['type'])).lower()
        return (any(w in name for w in _TRADE_WORDS) * 2 + sum(w in vals for w in _TRADE_VALUES), t['covered'])

    def loc_score(t):
        name = t['type'].lower()
        vals = values(t['type'])
        valtxt = ' '.join(vals).lower()
        return (any(w in name for w in _LOC_WORDS) * 2 + sum(w in valtxt for w in _LOC_WORDS[4:]) + (len(vals) >= 3), t['covered'])

    trade = max(usable, key=trade_score)['type'] if usable else None
    rest = [t for t in usable if t['type'] != trade]
    loc = max(rest, key=loc_score)['type'] if rest else None
    return {'location': loc, 'trade': trade}


def advice(mig, location=None, trade=None, top=3):
    """{'location', 'trade', 'locations', 'trades', 'cells': {loc: {trade: n}}, 'items': [...], 'worst': [...]}"""
    rows = (mig or {}).get('rows') or []
    if not location and not trade:
        d = pick_codes(rows)
        location, trade = d['location'], d['trade']
    val = lambda r, t: ((r.get('codes') or {}).get(t) or NO_VALUE) if t else '—'
    turned = [r for r in rows if r.get('kind') in _TURNED]
    cells, lost = {}, {}
    for r in turned:
        k = (val(r, location), val(r, trade))
        cells.setdefault(k[0], {})
        cells[k[0]][k[1]] = cells[k[0]].get(k[1], 0) + 1
        if r.get('base_tf') is not None and r.get('curr_tf') is not None:
            lost.setdefault(k, []).append(r['base_tf'] - r['curr_tf'])
    loc_tot = {l: sum(t.values()) for l, t in cells.items()}
    trade_tot = {}
    for t in cells.values():
        for k, n in t.items():
            trade_tot[k] = trade_tot.get(k, 0) + n
    locations = sorted(loc_tot, key=lambda l: (l == NO_VALUE, -loc_tot[l], l))
    trades = sorted(trade_tot, key=lambda t: (t == NO_VALUE, -trade_tot[t], t))
    flat = sorted(((l, t, n) for l, ts in cells.items() for t, n in ts.items()),
                  key=lambda x: (x[0] == NO_VALUE and x[1] == NO_VALUE, -x[2], x[0], x[1]))
    items = []
    for l, t, n in flat[:top]:
        ls = lost.get((l, t)) or []
        items.append({'location': l, 'trade': t, 'turned_crit': n,
                      'avg_lost': round(sum(ls) / len(ls), 1) if ls else None,
                      'mitigation': mitigation_for(t, l)})
    # deepest negative float now, among the open critical activities (held + turned)
    crit_now = [r for r in rows if r.get('to') == 'crit' and r.get('curr_tf') is not None]
    worst = {}
    for r in crit_now:
        k = (val(r, location), val(r, trade))
        w = worst.setdefault(k, {'location': k[0], 'trade': k[1], 'activities': 0, 'min_tf': r['curr_tf']})
        w['activities'] += 1
        w['min_tf'] = min(w['min_tf'], r['curr_tf'])
    worst = sorted((w for w in worst.values() if w['min_tf'] < 0), key=lambda w: (w['min_tf'], -w['activities']))[:3]
    return {'location': location, 'trade': trade, 'locations': locations, 'trades': trades,
            'cells': cells, 'loc_totals': loc_tot, 'trade_totals': trade_tot,
            'turned_crit': len(turned), 'items': items, 'worst': worst}
