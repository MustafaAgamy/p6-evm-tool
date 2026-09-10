"""Maps Special Report rendered items to dashboard tile descriptors.

A rendered item (from ``registry.render``) carries a payload in the shared
payloads.py vocabulary (see that module for the exact fields of each
``kind``). This module is a pure translation layer: it never touches the DB,
the registry, or any other p6_special module — just dict-in, dict-out — so a
dashboard view can render the same picks the Special Report renders, without
re-deriving anything. ``map_tile`` must never raise, even on a malformed or
empty item.
"""

_ALLOWED_KINDS = ('kpis', 'table', 'bars', 'segbar', 'findings', 'keyvals',
                  'text', 'note', 'group', 'line', 'status_header', 'html', 'no_data')


def _map_payload(payload):
    """Map one payload dict to ``(kind, data, shape)`` per the tile contract."""
    payload = payload or {}
    kind = payload.get('kind')

    if kind == 'kpi_group':
        return 'kpis', {'items': payload.get('items') or []}, {'w': 1, 'h': 0}

    if kind == 'table':
        columns = payload.get('columns') or []
        data = {
            'columns': columns,
            'rows': payload.get('rows') or [],
            'aligns': payload.get('aligns'),
        }
        shape = {'w': 2 if len(columns) > 4 else 1, 'h': 1}
        return 'table', data, shape

    if kind == 'bars':
        data = {
            'series': payload.get('series') or [],
            'rows': payload.get('rows') or [],
            'note': payload.get('note'),
            'axis_max': payload.get('axis_max'),
            'style': payload.get('style'),
        }
        return 'bars', data, {'w': 1, 'h': 1}

    if kind == 'line':
        data = {
            'series': payload.get('series') or [],
            'x': payload.get('x'),
            'y_max': payload.get('y_max'),
            'ref': payload.get('ref'),
            'note': payload.get('note'),
        }
        return 'line', data, {'w': 2, 'h': 1}

    if kind == 'status_header':
        data = {
            'domains': payload.get('domains') or [],
            'verdict': payload.get('verdict'),
        }
        # Rendered full-width above the grid (the board special-cases it),
        # not as a normal panel; shape kept minimal.
        return 'status_header', data, {'w': 2, 'h': 0}

    if kind == 'html':
        # A feature's OWN report section, reused verbatim (its exact markup + a
        # scoped stylesheet). Wide, since these are detailed sections.
        data = {'html': payload.get('html') or '', 'css': payload.get('css') or ''}
        return 'html', data, {'w': 2, 'h': 1}

    if kind == 'segbar':
        data = {'segments': payload.get('segments') or [], 'note': payload.get('note')}
        return 'segbar', data, {'w': 1, 'h': 0}

    if kind == 'findings':
        data = {
            'items': payload.get('items') or [],
            'empty': payload.get('empty') or 'No findings.',
        }
        return 'findings', data, {'w': 1, 'h': 1}

    if kind == 'keyvals':
        return 'keyvals', {'pairs': payload.get('pairs') or []}, {'w': 1, 'h': 0}

    if kind == 'text':
        return 'text', {'paragraphs': payload.get('paragraphs') or []}, {'w': 1, 'h': 1}

    if kind == 'note':
        data = {'message': payload.get('message') or '', 'tone': payload.get('tone') or 'info'}
        return 'note', data, {'w': 1, 'h': 0}

    if kind == 'group':
        blocks = []
        for bp in (payload.get('blocks') or []):
            bk, bd, _bs = _map_payload(bp)
            blocks.append({'kind': bk, 'data': bd})
        return 'group', {'blocks': blocks}, {'w': 2, 'h': 1}

    # 'no_data' or any unknown/missing kind
    return 'no_data', {}, {'w': 1, 'h': 1}


def map_tile(item):
    """Map one rendered Special Report item to a dashboard tile dict.

    ``item`` is a dict as returned by ``registry.render`` — expected keys
    'id', 'title', 'feature_title', 'ctype', 'payload' — but this function
    never raises, even when fields are missing or malformed.
    """
    item = item or {}
    try:
        kind, data, shape = _map_payload(item.get('payload'))
    except Exception:
        kind, data, shape = 'no_data', {}, {'w': 1, 'h': 1}

    return {
        'id': item.get('id'),
        'title': item.get('title'),
        'source': item.get('feature_title'),
        'ctype': item.get('ctype'),
        'kind': kind,
        'shape': shape,
        'data': data,
    }
