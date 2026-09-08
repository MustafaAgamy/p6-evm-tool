"""Structured payload vocabulary for Special Report sections.

Providers return payloads (plain dicts) in this small, shared vocabulary; the
Special Report renderer turns any payload into themed HTML that drives screen
preview, PDF and Word alike. Because every provider speaks this vocabulary, a
new feature only has to emit payloads — no renderer or export code changes.

``tone`` values are semantic, resolved to theme colours by the renderer:
``'neutral' | 'accent' | 'good' | 'warn' | 'bad'``.
"""

TONES = ('neutral', 'accent', 'good', 'warn', 'bad')


def kpi(label, value, sub=None, tone='neutral', spark=None, delta=None, delta_tone='neutral'):
    """A single KPI figure (label + big value + optional sub-line).

    Optional trend (drawn only on the dashboard): ``spark`` = list of recent
    values shown as an axis-less mini line under the value; ``delta`` = a short
    change string vs the previous update (e.g. ``'+0.03'`` or ``'▲ 3 d'``);
    ``delta_tone`` = the delta's colour, defaulting to ``'neutral'`` until change
    thresholds are confirmed.
    """
    return {'label': label, 'value': value, 'sub': sub, 'tone': tone,
            'spark': list(spark) if spark else None, 'delta': delta,
            'delta_tone': delta_tone}


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


def bars(rows, series, note=None, axis_max=None, style=None):
    """Horizontal comparison bars (e.g. Planned vs Actual, or counts by schedule).

    ``series``: list of ``{'label': str, 'tone': str}`` — one measure per bar row.
    ``rows``: list of ``{'label': str, 'values': [num, ...], 'display': [str, ...]?}``
        aligned to ``series``.
    ``axis_max``: if given, bar width = value / axis_max (for counts/days/money);
        if omitted, ``values`` are treated as already on a 0..100 percent scale.
    ``style``: ``None`` (default) or ``'variance'`` — a variance row draws its bar
        to the actual value with a tick at the row's ``target`` and the shortfall
        between actual and target shaded. Variance rows carry ``target`` (num) and
        optional ``target_display`` (str) beside ``values``/``display``.
    """
    return {'kind': 'bars', 'series': list(series), 'rows': list(rows),
            'note': note, 'axis_max': axis_max, 'style': style}


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


def line(series, x=None, y_max=None, ref=None, note=None):
    """A multi-series line chart for trends over time (e.g. SPI/CPI per update).

    ``series``: list of ``{'label': str, 'tone': str, 'points': [num|None, ...]}``
        aligned to ``x``; a ``None`` point is a gap (skipped), never drawn as 0.
    ``x``: optional list of x-axis labels (e.g. data dates).
    ``y_max``: optional fixed y max (else derived from the data).
    ``ref``: optional ``{'value': num, 'label': str}`` horizontal reference line
        (e.g. the 1.00 SPI/CPI target) — the dashboard never invents this value.
    ``note``: optional caption.
    """
    return {'kind': 'line', 'series': list(series), 'x': list(x) if x else None,
            'y_max': y_max, 'ref': ref, 'note': note}


def status_header(domains, verdict=None):
    """Executive status header: per-domain status chips + an optional single verdict.

    ``domains``: list of ``{'domain': str, 'tone': str, 'headline': str}`` — one
        chip per assessed area; ``tone='neutral'`` reads as "Not run", never a
        false green.
    ``verdict``: optional ``{'label': str, 'tone': str, 'note': str}`` — the single
        overall On-track / At-risk / Critical label. Left ``None`` until its rule is
        configured, so the header shows only the honest per-domain chips.
    """
    return {'kind': 'status_header', 'domains': list(domains), 'verdict': verdict}


def group(blocks):
    """Several blocks rendered in order as one section. ``blocks`` = payloads."""
    return {'kind': 'group', 'blocks': [b for b in blocks if b]}


# Sentinel a provider may return from ``produce`` when the data isn't present.
NO_DATA = {'kind': 'no_data'}
