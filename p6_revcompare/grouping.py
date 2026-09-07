"""Fold the flat change register into ONE entry per activity, for presentation.

The engine's ``register`` is one row per (activity, change_type): an activity with a
logic change *and* a criticality change appears twice, and a swapped resource shows as a
separate 'removed' row and 'added' row. Planners read that as the same activity repeated.

``group_register`` folds those rows into one entry per activity — all its change badges
together, each change kept as its own Rev.00 → Rev.01 line, and a removed+added resource
paired onto a single line. It is **presentation only**: it reads the register the engine
already produced and changes no number, no severity and no impact. The flat ``register``
stays untouched for the report sections that consume it directly.

Both the on-screen view and the exported PDF render from the result, so they stay identical.
"""
from p6_revcompare import severity as SEV

_SEV_ORDER = {'crit': 0, 'hi': 1, 'med': 2, 'low': 3}
_SYNTH = ('MS:', 'CAL:', 'WBS:', 'SCOPE:')


def _clean_id(s):
    return s.replace('MS:', '').replace('SCOPE:', '') if s else s


def _derive_key(row):
    """Grouping key when the engine didn't tag one — the underlying activity code."""
    aid = row.get('activity_id') or ''
    if aid.startswith('SCOPE:'):
        return None                      # summary counts — never a register entry
    if aid.startswith('RES:'):
        parts = aid.split(':')
        return parts[1] if len(parts) > 1 else aid
    return aid                           # MS:/CAL:/WBS: (own row) or a real activity code


def _res_name(row):
    if not row:
        return None
    if row.get('resource_name'):
        return row['resource_name']
    name = row.get('activity_name') or ''
    return name.split(' · ', 1)[1] if ' · ' in name else name


def group_register(register):
    """[flat register rows] -> [one entry per activity], worst-severity first (input order)."""
    groups, order = {}, []
    for row in register or []:
        key = row.get('activity_key', _MISSING)
        if key is _MISSING:
            key = _derive_key(row)
        if key is None:
            continue                     # dropped (SCOPE summary rows)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)
    return [_build_group(k, groups[k]) for k in order]


class _Missing:
    pass


_MISSING = _Missing()


def _scope_kind(rows):
    if len(rows) == 1 and rows[0]['change_type'] in ('added', 'removed'):
        return rows[0]['change_type']
    return None


def _build_group(key, rows):
    key_s = str(key)
    is_ms = any(r['change_type'] == 'milestone' for r in rows)
    is_struct = key_s.startswith(('CAL:', 'WBS:'))

    change_types = []
    for r in rows:
        if r['change_type'] not in change_types:
            change_types.append(r['change_type'])

    impact = 'material' if any(r.get('impact') == 'material' for r in rows) else 'minor'
    severity = min((r.get('severity') for r in rows),
                   key=lambda s: _SEV_ORDER.get(s, 3))

    # name: prefer a clean activity name (a non-resource row carries it), else the
    # activity name attached to a resource/cost row (never "name · resource").
    name = next((r.get('activity_name') for r in rows
                 if r['change_type'] != 'resource' and r.get('activity_name')), None)
    if name is None:
        name = rows[0].get('act_name') or rows[0].get('activity_name')

    disp_id, wbs = None, None
    if not is_ms and not is_struct:
        # Prefer a real Rev.01 id (idchange rows carry orig_id), else the group key — which
        # IS the clean activity code. Never the raw activity_id: resource rows carry the
        # synthetic "RES:<code>:<resource>" token there, which must not reach the display.
        rid = next((r.get('orig_id') for r in rows if r.get('orig_id')), None) or key_s
        disp_id = _clean_id(rid)
        wbs = next((r.get('wbs') for r in rows if r.get('wbs')), None)

    kind = 'milestone' if is_ms else 'structure' if is_struct else (_scope_kind(rows) or 'activity')
    changes = _build_changes(rows)
    detail = next((r.get('detail') for r in rows if r.get('detail')), None)

    return {
        'key': key_s,
        'kind': kind,
        'activity_name': name,
        'activity_id': disp_id,
        'wbs': wbs,
        'change_types': change_types,
        'type_labels': [SEV.TYPE_LABEL.get(ct, ct) for ct in change_types],
        'impact': impact,
        'severity': severity,
        'status': rows[0].get('status', 'open'),
        'summary': _summary(changes),
        'changes': changes,
        'detail': detail,
        'change_count': len(rows),
    }


def _build_changes(rows):
    """Per-change Rev.00 → Rev.01 lines; removed+added resources paired onto one line."""
    lines = []
    for r in rows:
        if r['change_type'] == 'resource':
            continue
        lines.append({
            'dimension': SEV.TYPE_LABEL.get(r['change_type'], r['change_type']),
            'change_type': r['change_type'],
            'rev0': r.get('rev0'), 'rev1': r.get('rev1'),
            'note': r.get('change'),
            'removed': None, 'added': None,
        })

    res = [r for r in rows if r['change_type'] == 'resource']
    if res:
        removed = [r for r in res if r.get('res_kind') == 'removed']
        added = [r for r in res if r.get('res_kind') == 'added']
        others = [r for r in res if r.get('res_kind') not in ('removed', 'added')]
        for i in range(max(len(removed), len(added))):
            rr = removed[i] if i < len(removed) else None
            ra = added[i] if i < len(added) else None
            lines.append({
                'dimension': 'Resource', 'change_type': 'resource',
                'rev0': rr.get('rev0') if rr else None,
                'rev1': ra.get('rev1') if ra else None,
                'removed': _res_name(rr), 'added': _res_name(ra),
                'note': 'Replaced' if (rr and ra) else ('Removed' if rr else 'Added'),
            })
        for r in others:
            lines.append({
                'dimension': 'Resource', 'change_type': 'resource',
                'rev0': r.get('rev0'), 'rev1': r.get('rev1'),
                'removed': None, 'added': None,
                'note': r.get('change'), 'resource': _res_name(r),
            })
    return lines


def _summary(changes):
    """A compact one-line 'what changed' for the collapsed row."""
    bits = []
    for c in changes:
        if c.get('removed') or c.get('added'):
            bits.append(' → '.join(x for x in (c.get('removed'), c.get('added')) if x))
        elif c.get('note'):
            bits.append(str(c['note']))
    # de-duplicate while preserving order, keep it short
    seen, out = set(), []
    for b in bits:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return ' · '.join(out[:3]) + (' …' if len(out) > 3 else '')
