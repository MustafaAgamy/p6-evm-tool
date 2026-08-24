"""Structured payload vocabulary for Special Report sections.

Providers return payloads (plain dicts) in this small, shared vocabulary; the
Special Report renderer turns any payload into themed HTML that drives screen
preview, PDF and Word alike. Because every provider speaks this vocabulary, a
new feature only has to emit payloads — no renderer or export code changes.

``tone`` values are semantic, resolved to theme colours by the renderer:
``'neutral' | 'accent' | 'good' | 'warn' | 'bad'``.
"""

TONES = ('neutral', 'accent', 'good', 'warn', 'bad')


def kpi(label, value, sub=None, tone='neutral'):
    """A single KPI figure (label + big value + optional sub-line)."""
    return {'label': label, 'value': value, 'sub': sub, 'tone': tone}


def kpi_group(items):
    """A row of KPI tiles. ``items`` = list of :func:`kpi` dicts."""
    return {'kind': 'kpi_group', 'items': list(items)}


def table(columns, rows, aligns=None):
    """A data table.

    ``columns``: list of header strings.
    ``rows``: list of rows, each a list of cells (str/num, or a ``(text, tone)``
        tuple to colour a cell).
    ``aligns``: optional per-column alignment, each ``'l' | 'r' | 'c'``.
    """
    return {
        'kind': 'table',
        'columns': list(columns),
        'rows': [list(r) for r in rows],
        'aligns': list(aligns) if aligns else None,
    }


def bars(rows, series, note=None):
    """Horizontal comparison bars (e.g. Planned vs Actual).

    ``series``: list of ``{'label': str, 'tone': str}`` — one measure per bar row.
    ``rows``: list of ``{'label': str, 'values': [num, ...], 'display': [str, ...]?}``
        where ``values`` (0..100 scale) align to ``series``.
    """
    return {'kind': 'bars', 'series': list(series), 'rows': list(rows), 'note': note}


def segbar(segments, note=None):
    """A single 100%-stacked bar. ``segments`` = list of
    ``{'label': str, 'value': num, 'tone': str}`` (values need not sum to 100)."""
    return {'kind': 'segbar', 'segments': list(segments), 'note': note}


def findings(items, empty='No findings.'):
    """A findings register. ``items`` = list of
    ``{'severity': 'high'|'medium'|'low'|'info', 'title': str, 'detail': str?}``."""
    return {'kind': 'findings', 'items': list(items), 'empty': empty}


def keyvals(pairs):
    """A label/value list. ``pairs`` = list of ``(label, value)``."""
    return {'kind': 'keyvals', 'pairs': [(k, v) for k, v in pairs]}


def text(paragraphs):
    """Free text. ``paragraphs`` = str or list[str]."""
    if isinstance(paragraphs, str):
        paragraphs = [paragraphs]
    return {'kind': 'text', 'paragraphs': list(paragraphs)}


def note(message, tone='info'):
    """A short callout line. ``tone`` = ``'info'|'good'|'warn'|'bad'``."""
    return {'kind': 'note', 'message': message, 'tone': tone}


def group(blocks):
    """Several blocks rendered in order as one section. ``blocks`` = payloads."""
    return {'kind': 'group', 'blocks': [b for b in blocks if b]}


# Sentinel a provider may return from ``produce`` when the data isn't present.
NO_DATA = {'kind': 'no_data'}
