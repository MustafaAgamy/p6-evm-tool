"""Special Report renderer — payloads -> one themed HTML document.

The same HTML drives the on-screen preview, the Chrome PDF, and the Word export,
so all three look identical. To keep Word faithful the markup is deliberately
"old-HTML" safe: tables, ``bgcolor``, inline styles, and **concrete hex** colours
resolved from the chosen appearance mode (Word ignores CSS ``var()``). All six
appearance modes therefore work in screen, PDF and Word with no per-mode code.
"""
import html as _html

import report_theme
from p6_special import payloads as P

# semantic tone -> theme token
_TONE_INK = {'neutral': 'rpt-ink', 'accent': 'rpt-accent',
             'good': 'rpt-good', 'warn': 'rpt-warn', 'bad': 'rpt-bad'}
_TONE_BAR = {'neutral': 'rpt-hair-strong', 'accent': 'rpt-accent',
             'good': 'rpt-good', 'warn': 'rpt-warn', 'bad': 'rpt-bad'}
_TONE_BG = {'neutral': 'rpt-surface', 'accent': 'rpt-accent-soft',
            'good': 'rpt-good-bg', 'warn': 'rpt-warn-bg', 'bad': 'rpt-bad-bg'}
_SEV_TONE = {'high': 'bad', 'medium': 'warn', 'low': 'good', 'info': 'accent'}

# The Baseline Narrative report's fixed STRUCTURAL colour — the navy that draws
# the page frame, running-header rule, cover title/rule, section badges/underline
# and table headers. It is deliberately NOT a theme token: it stays navy across
# the light-ground modes and lightens to a readable navy on the dark grounds, so
# the report keeps the same house style whatever appearance mode is chosen. It is
# emitted as concrete hex (also declared once as ``--sr-navy`` on :root) — never as
# ``var(--sr-navy)`` — because the same cover/contents/section markup is shared with
# the Word wrapper, whose HTML engine cannot resolve custom properties.
_SR_NAVY = {
    'light': '#1f3b63', 'sepia': '#1f3b63', 'contrast': '#1f3b63',
    'dark': '#4a72a8', 'midnight': '#4a72a8', 'blueprint': '#4a72a8',
}


def _esc(s):
    return _html.escape('' if s is None else str(s))


class _Colors:
    def __init__(self, mode):
        self.mode = report_theme.normalize(mode)
        self._v = report_theme.theme_vars(self.mode)
        self.navy = _SR_NAVY.get(self.mode, '#1f3b63')   # fixed structural navy (concrete hex)

    def __call__(self, token):
        return self._v.get(token, '#000000')

    def ink(self, tone):
        return self._v.get(_TONE_INK.get(tone, 'rpt-ink'), '#000000')

    def bar(self, tone):
        return self._v.get(_TONE_BAR.get(tone, 'rpt-accent'), '#2563eb')

    def bg(self, tone):
        return self._v.get(_TONE_BG.get(tone, 'rpt-surface'), '#f7f9fc')


# ── payload renderers ────────────────────────────────────────────────────────
def _kpi_group(pl, C):
    items = pl.get('items') or []
    if not items:
        return _no_data({}, C)
    cells = []
    for it in items:
        tone = it.get('tone', 'neutral')
        sub = f'<div style="font-size:10.5px;color:{C("rpt-muted")};margin-top:4px">{_esc(it["sub"])}</div>' if it.get('sub') else ''
        cells.append(
            f'<td valign="top" style="border:1px solid {C("rpt-edge")};'
            f'background:{C("rpt-surface")};padding:12px 14px;border-radius:8px">'
            f'<div style="font-size:10.5px;letter-spacing:.4px;text-transform:uppercase;color:{C("rpt-muted")}">{_esc(it.get("label"))}</div>'
            f'<div style="font-size:26px;font-weight:800;margin-top:4px;color:{C.ink(tone)}">{_esc(it.get("value"))}</div>'
            f'{sub}</td>'
        )
    spacer = f'<td style="width:12px"></td>'
    inner = spacer.join(cells)
    return (f'<table cellpadding="0" cellspacing="0" style="border-collapse:separate;width:100%;margin:4px 0 2px">'
            f'<tr>{inner}</tr></table>')


def _table(pl, C):
    cols = pl.get('columns') or []
    rows = pl.get('rows') or []
    aligns = pl.get('aligns') or ['l'] * len(cols)
    amap = {'l': 'left', 'r': 'right', 'c': 'center'}
    if not rows:
        return _no_data({}, C)
    head = ''.join(
        f'<th align="{amap.get(aligns[i] if i < len(aligns) else "l", "left")}" '
        f'style="background:{C("rpt-th-bg")};color:{C("rpt-th-ink")};padding:8px 10px;'
        f'border-bottom:2px solid {C("rpt-hair-strong")};font-size:11.5px">{_esc(c)}</th>'
        for i, c in enumerate(cols)
    )
    body = []
    for r in rows:
        tds = []
        for i, cell in enumerate(r):
            tone = None
            if isinstance(cell, tuple):
                cell, tone = cell
            al = amap.get(aligns[i] if i < len(aligns) else 'l', 'left')
            color = C.ink(tone) if tone else C('rpt-ink')
            weight = '600' if tone else '400'
            tds.append(
                f'<td align="{al}" style="padding:7px 10px;border-bottom:1px solid {C("rpt-hair")};'
                f'font-size:12px;color:{color};font-weight:{weight}">{_esc(cell)}</td>'
            )
        body.append(f'<tr>{"".join(tds)}</tr>')
    return (f'<table class="sr-dt" cellpadding="0" cellspacing="0" width="100%" '
            f'style="border-collapse:collapse;margin:6px 0;border:1px solid {C("rpt-edge")}">'
            f'<thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>')


def _bar_track(width_pct, color, track_color):
    w = max(0.0, min(100.0, float(width_pct or 0)))
    return (
        f'<table cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse">'
        f'<tr style="height:16px">'
        f'<td width="{w:.1f}%" bgcolor="{color}" style="background:{color};height:16px;line-height:16px;font-size:1px">&nbsp;</td>'
        f'<td bgcolor="{track_color}" style="background:{track_color};height:16px;line-height:16px;font-size:1px">&nbsp;</td>'
        f'</tr></table>'
    )


def _bars(pl, C):
    if pl.get('style') == 'variance':
        return _variance_bars(pl, C)
    series = pl.get('series') or []
    rows = pl.get('rows') or []
    if not rows or not series:
        return _no_data({}, C)
    axis_max = pl.get('axis_max')
    try:
        axis_max = float(axis_max) if axis_max else None
    except (TypeError, ValueError):
        axis_max = None
    track = C('rpt-surface-2')
    blocks = []
    for row in rows:
        label = row.get('label')
        vals = row.get('values') or []
        disp = row.get('display') or [None] * len(vals)
        lines = []
        for i, s in enumerate(series):
            v = vals[i] if i < len(vals) else 0
            try:
                vnum = float(v or 0)
            except (TypeError, ValueError):
                vnum = 0.0
            width = (vnum / axis_max * 100.0) if axis_max else vnum
            color = C.bar(s.get('tone', 'accent'))
            shown = disp[i] if i < len(disp) and disp[i] is not None else (f'{vnum:.1f}%' if not axis_max else f'{vnum:g}')
            lines.append(
                f'<tr>'
                f'<td width="120" style="font-size:11.5px;color:{C("rpt-ink-soft")};padding:3px 8px 3px 0">{_esc(s.get("label"))}</td>'
                f'<td>{_bar_track(width, color, track)}</td>'
                f'<td width="80" align="right" style="font-size:11.5px;color:{C("rpt-ink")};padding-left:8px;white-space:nowrap">{_esc(shown)}</td>'
                f'</tr>'
            )
        head = f'<div style="font-size:12.5px;font-weight:600;color:{C("rpt-ink")};margin:8px 0 4px">{_esc(label)}</div>' if label else ''
        blocks.append(head + f'<table cellpadding="0" cellspacing="0" width="100%">{"".join(lines)}</table>')
    note = pl.get('note')
    if note:
        blocks.append(f'<div style="font-size:11px;color:{C("rpt-muted")};margin-top:6px">{_esc(note)}</div>')
    return '<div style="margin:4px 0">' + ''.join(blocks) + '</div>'


def _segbar(pl, C):
    segs = [s for s in (pl.get('segments') or []) if (s.get('value') or 0) > 0]
    if not segs:
        return _no_data({}, C)
    total = sum(float(s.get('value') or 0) for s in segs) or 1.0
    cells = []
    legend = []
    for s in segs:
        pct = 100.0 * float(s.get('value') or 0) / total
        color = C.bar(s.get('tone', 'neutral'))
        cells.append(
            f'<td width="{pct:.1f}%" bgcolor="{color}" align="center" '
            f'style="background:{color};color:#ffffff;font-size:11px;padding:5px 2px">{_esc(s.get("label"))} {_esc(s.get("value"))}</td>'
        )
        legend.append(
            f'<span style="display:inline-block;margin-right:14px;font-size:11px;color:{C("rpt-muted")}">'
            f'<span style="display:inline-block;width:10px;height:10px;background:{color};margin-right:5px"></span>'
            f'{_esc(s.get("label"))}</span>'
        )
    note = pl.get('note')
    note_html = f'<div style="font-size:11px;color:{C("rpt-muted")};margin-top:6px">{_esc(note)}</div>' if note else ''
    return (f'<table cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;margin:8px 0">'
            f'<tr>{"".join(cells)}</tr></table>'
            f'<div style="margin-top:6px">{"".join(legend)}</div>{note_html}')


def _findings(pl, C):
    items = pl.get('items') or []
    if not items:
        return f'<div style="font-size:12px;color:{C("rpt-muted")};padding:6px 0">{_esc(pl.get("empty") or "No findings.")}</div>'
    blocks = []
    for f in items:
        tone = _SEV_TONE.get((f.get('severity') or 'info').lower(), 'accent')
        chip = C.ink(tone)
        detail = f'<div style="font-size:11.5px;color:{C("rpt-ink-soft")};margin-top:2px">{_esc(f.get("detail"))}</div>' if f.get('detail') else ''
        blocks.append(
            f'<table cellpadding="0" cellspacing="0" width="100%" style="margin:6px 0;border-collapse:collapse">'
            f'<tr><td width="4" bgcolor="{chip}" style="background:{chip}"></td>'
            f'<td style="padding:6px 10px;background:{C("rpt-surface")};border:1px solid {C("rpt-edge")};border-left:none">'
            f'<span style="font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:{chip};font-weight:700">{_esc(f.get("severity") or "info")}</span> '
            f'<span style="font-size:12.5px;font-weight:600;color:{C("rpt-ink")}">{_esc(f.get("title"))}</span>{detail}</td></tr></table>'
        )
    return ''.join(blocks)


def _keyvals(pl, C):
    pairs = pl.get('pairs') or []
    rows = ''.join(
        f'<tr><td style="padding:5px 14px 5px 0;font-size:12px;color:{C("rpt-muted")}">{_esc(k)}</td>'
        f'<td style="padding:5px 0;font-size:12.5px;font-weight:600;color:{C("rpt-ink")}">{_esc(v)}</td></tr>'
        for k, v in pairs
    )
    return f'<table cellpadding="0" cellspacing="0" style="margin:4px 0">{rows}</table>'


def _text(pl, C):
    return ''.join(
        f'<p style="font-size:12.5px;line-height:1.5;color:{C("rpt-ink-soft")};margin:6px 0">{_esc(p)}</p>'
        for p in (pl.get('paragraphs') or [])
    )


def _note(pl, C):
    tone = pl.get('tone', 'info')
    tone = 'accent' if tone == 'info' else tone
    return (f'<table cellpadding="0" cellspacing="0" width="100%" style="margin:10px 0"><tr>'
            f'<td style="background:{C.bg(tone)};border:1px solid {C("rpt-edge")};padding:11px 14px;'
            f'font-size:12px;color:{C("rpt-ink")};border-radius:8px">{_esc(pl.get("message"))}</td></tr></table>')


def _no_data(pl, C):
    err = pl.get('error')
    extra = f' <span style="color:{C("rpt-muted")}">({_esc(err)})</span>' if err else ''
    return (f'<div style="font-size:12px;color:{C("rpt-muted")};font-style:italic;padding:8px 0">'
            f'No data available for this result.{extra}</div>')


def _group(pl, C):
    return ''.join(render_payload(b, C) for b in (pl.get('blocks') or []))


def _html_block(pl, C):
    """A feature's own report markup (already scoped). CSS is collected at the
    document level; here we just place the fragment."""
    return pl.get('html') or _no_data({}, C)


def _numfmt(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return f'{float(v):g}'
    return str(v)


def _variance_bars(pl, C):
    """Discipline-gap 'variance' bars for the document: actual bar + the planned
    target shown alongside (the dashboard draws the tick + shortfall visually)."""
    rows = pl.get('rows') or []
    if not rows:
        return _no_data({}, C)
    axis_max = pl.get('axis_max')
    try:
        axis_max = float(axis_max) if axis_max else None
    except (TypeError, ValueError):
        axis_max = None
    track = C('rpt-surface-2')
    lines = []
    for row in rows:
        vals = row.get('values') or []
        try:
            actual = float(vals[0] or 0)
        except (TypeError, ValueError, IndexError):
            actual = 0.0
        target = row.get('target')
        try:
            target = float(target) if target is not None else None
        except (TypeError, ValueError):
            target = None
        width = (actual / axis_max * 100.0) if axis_max else actual
        color = C.bar(row.get('tone', 'accent'))
        disp = (row.get('display') or [None])
        shown = disp[0] if disp and disp[0] is not None else (f'{actual:.1f}%' if not axis_max else f'{actual:g}')
        if target is not None:
            tshown = row.get('target_display') or (f'{target:.1f}%' if not axis_max else f'{target:g}')
            shown = f'{shown} · plan {tshown}'
        ink = C.ink(row.get('tone')) if row.get('tone') else C('rpt-ink')
        lines.append(
            f'<tr><td width="120" style="font-size:11.5px;color:{C("rpt-ink-soft")};padding:3px 8px 3px 0">{_esc(row.get("label"))}</td>'
            f'<td>{_bar_track(width, color, track)}</td>'
            f'<td width="130" align="right" style="font-size:11.5px;color:{ink};padding-left:8px;white-space:nowrap">{_esc(shown)}</td></tr>'
        )
    note = pl.get('note')
    note_html = f'<div style="font-size:11px;color:{C("rpt-muted")};margin-top:6px">{_esc(note)}</div>' if note else ''
    return f'<table cellpadding="0" cellspacing="0" width="100%">{"".join(lines)}</table>{note_html}'


def _line(pl, C):
    """A trend across the weekly updates — rendered as a Word-safe table (x labels
    across the top, one row per series) plus the reference/caption."""
    series = pl.get('series') or []
    x = pl.get('x') or []
    n = max((len(s.get('points') or []) for s in series), default=0)
    if not series or n < 2:
        return _no_data({}, C)
    xh = ''.join(
        f'<th align="right" style="background:{C("rpt-th-bg")};color:{C("rpt-th-ink")};'
        f'padding:6px 8px;font-size:11px">{_esc(x[i]) if i < len(x) else i + 1}</th>'
        for i in range(n)
    )
    body = []
    for s in series:
        pts = s.get('points') or []
        color = C.ink(s.get('tone', 'accent'))
        cells = ''.join(
            f'<td align="right" style="padding:6px 8px;font-size:11.5px;border-bottom:1px solid {C("rpt-hair")}">'
            f'{"" if (i >= len(pts) or pts[i] is None) else _esc(_numfmt(pts[i]))}</td>'
            for i in range(n)
        )
        body.append(
            f'<tr><td style="padding:6px 8px;font-size:11.5px;font-weight:600;color:{color};'
            f'border-bottom:1px solid {C("rpt-hair")}">{_esc(s.get("label"))}</td>{cells}</tr>'
        )
    ref, note = pl.get('ref'), pl.get('note')
    cap = []
    if ref and ref.get('value') is not None:
        cap.append(f'{_esc(ref.get("label") or "target")} = {_esc(_numfmt(ref.get("value")))}')
    if note:
        cap.append(_esc(note))
    cap_html = f'<div style="font-size:11px;color:{C("rpt-muted")};margin-top:6px">{" · ".join(cap)}</div>' if cap else ''
    return (f'<table class="sr-dt" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;margin:6px 0;'
            f'border:1px solid {C("rpt-edge")}"><thead><tr><th style="background:{C("rpt-th-bg")}"></th>{xh}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table>{cap_html}')


def _status_header(pl, C):
    """Executive status header for the document: an optional verdict + a row of
    per-domain chips, each with its RAG letter (colour is never the only channel)."""
    domains = pl.get('domains') or []
    v = pl.get('verdict')
    if v:
        col = C.ink(v.get('tone'))
        head = f'<div style="font-size:15px;font-weight:800;color:{col};margin-bottom:4px">{_esc(v.get("label"))}</div>'
        if v.get('note'):
            head += f'<div style="font-size:11px;color:{C("rpt-muted")};font-style:italic;margin-bottom:6px">{_esc(v.get("note"))}</div>'
    else:
        head = (f'<div style="font-size:13px;font-weight:700;color:{C("rpt-ink")};margin-bottom:2px">Status by area</div>'
                f'<div style="font-size:11px;color:{C("rpt-muted")};font-style:italic;margin-bottom:6px">'
                f'Each area shows its own status; the single overall verdict is set up separately.</div>')
    cells = []
    for d in domains:
        tone = d.get('tone', 'neutral')
        chip = C.ink(tone) if tone in ('good', 'warn', 'bad') else C('rpt-muted')
        letter = {'good': 'G', 'warn': 'A', 'bad': 'R'}.get(tone, '–')
        cells.append(
            f'<td valign="top" style="padding:6px 10px;border:1px solid {C("rpt-edge")}">'
            f'<span style="display:inline-block;width:15px;height:15px;border-radius:3px;background:{chip};color:#fff;'
            f'font-size:9px;font-weight:800;text-align:center;line-height:15px;margin-right:6px">{letter}</span>'
            f'<span style="font-size:9px;text-transform:uppercase;letter-spacing:.4px;color:{C("rpt-muted")}">{_esc(d.get("domain"))}</span>'
            f'<div style="font-size:12.5px;font-weight:700;color:{C("rpt-ink")};margin-top:2px">{_esc(d.get("headline"))}</div></td>'
        )
    row = (f'<table cellpadding="0" cellspacing="0" style="border-collapse:separate;border-spacing:6px 0;margin:4px 0">'
           f'<tr>{"".join(cells)}</tr></table>')
    return head + row


_DISPATCH = {
    'kpi_group': _kpi_group, 'table': _table, 'bars': _bars, 'segbar': _segbar,
    'findings': _findings, 'keyvals': _keyvals, 'text': _text, 'note': _note,
    'line': _line, 'status_header': _status_header,
    'no_data': _no_data, 'group': _group, 'html': _html_block,
}


def render_payload(payload, C):
    if not payload:
        return _no_data({}, C)
    fn = _DISPATCH.get(payload.get('kind'))
    return fn(payload, C) if fn else _no_data({}, C)


# ── document assembly ────────────────────────────────────────────────────────
def render_section(index, item, C):
    """One numbered section: a navy number badge + title over a thin navy
    underline (the Narrative report's H1), then the section body. Word-safe (the
    heading is a table so it survives Word's HTML engine); navy is concrete hex so
    it renders identically in the screen preview, the Chrome PDF and Word."""
    navy = C.navy
    body = render_payload(item.get('payload'), C)
    return (
        f'<div class="sr-sec" style="margin:0 0 22px;page-break-inside:avoid">'
        f'<table class="sr-sec-h" cellpadding="0" cellspacing="0" width="100%" '
        f'style="border-collapse:collapse;margin-bottom:10px;border-bottom:2px solid {navy}"><tr>'
        f'<td valign="middle" style="width:1%;white-space:nowrap;padding:0 0 8px 0">'
        f'<span class="sr-num" style="display:inline-block;background:{navy};color:#ffffff;'
        f'border-radius:5px;padding:2px 10px;font-size:14px;font-weight:700">{index}</span></td>'
        f'<td valign="middle" style="font-size:16px;font-weight:800;color:{navy};padding:0 0 8px 10px">{_esc(item.get("title"))}</td>'
        f'</tr></table>'
        f'{body}</div>'
    )


def _fmt_date(v):
    """Show a clean date — drop any '00:00:00' time tail a stored data_date carries."""
    if not v:
        return ''
    s = str(v)
    return s.split(' ')[0] if ' ' in s else (s.split('T')[0] if 'T' in s else s)


def _logo_srcs(letterhead):
    """Best-effort three logo sources from the letterhead, tolerant of shapes:
    ``logos`` as a dict (owner/consultant/contractor), a list (of src strings or
    ``{src}`` dicts), or the board's ``logos_left``/``logos_right`` arrays."""
    lh = letterhead or {}
    srcs = [None, None, None]
    logos = lh.get('logos')
    if isinstance(logos, dict):
        for i, k in enumerate(('owner', 'consultant', 'contractor')):
            srcs[i] = logos.get(k)
    elif isinstance(logos, (list, tuple)):
        for i, it in enumerate(list(logos)[:3]):
            srcs[i] = it.get('src') if isinstance(it, dict) else it
    if not any(srcs):
        combined = list(lh.get('logos_left') or []) + list(lh.get('logos_right') or [])
        for i, it in enumerate(combined[:3]):
            srcs[i] = it.get('src') if isinstance(it, dict) else it
    return srcs


def _logo_row(letterhead, C, big=False):
    """Three evenly-spaced logo slots — the supplied image, else a 'LOGO'
    placeholder box (Word-safe table so it survives the Word wrapper too)."""
    h = 44 if big else 36
    cells = []
    for s in _logo_srcs(letterhead):
        if s:
            inner = f'<img src="{_esc(s)}" alt="logo" style="max-height:{h}px;max-width:150px;object-fit:contain"/>'
        else:
            inner = (f'<span style="display:inline-block;min-width:96px;height:{h}px;line-height:{h}px;'
                     f'border:1px dashed {C("rpt-edge")};border-radius:4px;color:{C("rpt-muted")};'
                     f'font-size:9px;letter-spacing:.08em;text-align:center">LOGO</span>')
        cells.append(f'<td style="width:33.33%;text-align:center;vertical-align:middle;padding:2px 8px">{inner}</td>')
    return (f'<table cellpadding="0" cellspacing="0" width="100%" '
            f'style="border-collapse:collapse;table-layout:fixed;margin-bottom:9px"><tr>{"".join(cells)}</tr></table>')


def _cover(report_name, meta, letterhead, C):
    """The separate title page: three logos, a navy kicker, the report name big in
    navy, a navy double rule, then project / data date / prepared-by (only the
    fields actually supplied). Breaks to its own page in print and Word."""
    lh = letterhead or {}
    navy = C.navy
    company = lh.get('company')
    brand = (f'<div style="font-size:12px;font-weight:700;color:{C("rpt-ink-soft")};margin-bottom:10px">{_esc(company)}</div>'
             if company else '')
    date_s = _fmt_date(meta.get('data_date'))
    # Only show 'Prepared by' when the user actually supplied it — never fabricate it.
    metas = [('Project', meta.get('project_name')), ('Data date', date_s),
             ('Prepared by', lh.get('prepared_by'))]
    metacells = ''.join(
        f'<td valign="top" style="padding-right:40px"><div style="font-size:10px;text-transform:uppercase;letter-spacing:1px;color:{C("rpt-muted")}">{_esc(k)}</div>'
        f'<div style="font-size:14px;font-weight:650;color:{C("rpt-ink")};margin-top:3px">{_esc(v)}</div></td>'
        for k, v in metas if v
    )
    kicker = _esc(lh.get('kicker') or 'Project Progress Report')
    return (
        f'<div class="sr-cover" style="page-break-after:always;padding:36px 6px 26px">'
        f'{_logo_row(lh, C, big=True)}'
        f'{brand}'
        f'<div class="sr-ckick" style="letter-spacing:.16em;text-transform:uppercase;font-size:10px;color:{navy};font-weight:700;margin-top:22px">{kicker}</div>'
        f'<div class="sr-rname" style="font-size:30px;font-weight:800;line-height:1.14;color:{navy};max-width:640px;margin:8px 0 0">{_esc(report_name)}</div>'
        f'<div style="border-bottom:3px double {navy};margin:14px 0 12px"></div>'
        f'<table cellpadding="0" cellspacing="0" style="margin-top:6px"><tr>{metacells}</tr></table>'
        f'</div>'
    )


def _toc(rendered, C):
    """The separate contents page: a navy heading, then numbered rows in pick order
    — number · title · faint source-feature tag · nominal page number. Breaks to
    its own page in print and Word."""
    navy = C.navy
    dot = C('rpt-hair-strong')
    rows = []
    for i, item in enumerate(rendered, 1):
        src = item.get('feature_title') or item.get('feature') or ''
        src_html = (f' <span style="font-size:10px;color:{C("rpt-muted")};font-weight:400">{_esc(src)}</span>'
                    if src else '')
        page_no = i + 2   # nominal: cover = 1, contents = 2, first section = 3
        rows.append(
            f'<tr>'
            f'<td valign="top" style="width:26px;font-size:12.5px;font-weight:800;color:{navy};padding:8px 0;border-bottom:1px dotted {dot}">{i}</td>'
            f'<td style="font-size:12.5px;font-weight:700;color:{C("rpt-ink")};padding:8px 6px;border-bottom:1px dotted {dot}">{_esc(item.get("title"))}{src_html}</td>'
            f'<td align="right" valign="top" style="font-size:12px;color:{C("rpt-muted")};padding:8px 0;border-bottom:1px dotted {dot}">{page_no}</td>'
            f'</tr>'
        )
    return (
        f'<div class="sr-toc" style="page-break-after:always;padding-bottom:6px">'
        f'<div class="sr-sec-h" style="font-size:16px;font-weight:800;color:{navy};'
        f'border-bottom:2px solid {navy};padding-bottom:8px;margin-bottom:8px">Table of contents</div>'
        f'<table cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse">{"".join(rows)}</table></div>'
    )


def _empty_notice(C):
    return (f'<div style="font-size:13px;color:{C("rpt-muted")};padding:20px 0">'
            f'No results selected. Pick results on the left to build the report.</div>')


def _running_header(meta, letterhead, C):
    """The repeating (thead) running-header band: three logos, a navy kicker and
    the project name on the right, over a navy rule. Chrome repeats it on every
    printed page (see the ``.sr-doc`` thead in :func:`build_document`)."""
    lh = letterhead or {}
    navy = C.navy
    project = _esc((meta or {}).get('project_name') or 'Project')
    kicker = _esc(lh.get('kicker') or 'Project Progress Report')
    return (
        f'<div class="sr-head" style="border-bottom:2px solid {navy};padding-bottom:8px">'
        f'{_logo_row(lh, C, big=False)}'
        f'<table cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse"><tr>'
        f'<td class="sr-kicker" style="letter-spacing:.12em;text-transform:uppercase;font-size:9px;color:{navy};font-weight:700">{kicker}</td>'
        f'<td class="sr-proj" align="right" style="font-size:11px;font-weight:600;color:{C("rpt-muted")};text-align:right">{project}</td>'
        f'</tr></table></div>'
    )


def _running_footer(meta, C):
    """The repeating (tfoot) footer band. On screen it shows a page-number
    PLACEHOLDER; the live 'Page X of Y' is drawn per printed page by the ``@page``
    bottom-centre counter in the shell CSS."""
    project = _esc((meta or {}).get('project_name') or '')
    return (
        f'<div class="sr-foot" style="border-top:1px solid {C("rpt-hair")};padding-top:8px">'
        f'<table cellpadding="0" cellspacing="0" width="100%"><tr>'
        f'<td style="font-size:9px;color:{C("rpt-muted")}">{project}</td>'
        f'<td class="sr-pph" align="right" style="text-align:right;font-size:9px;color:{C("rpt-muted")};font-style:italic">'
        f'Page numbers appear on the printed / PDF copy</td>'
        f'</tr></table></div>'
    )


def _base_css(C):
    return (
        '* { -webkit-print-color-adjust:exact; print-color-adjust:exact; box-sizing:border-box; }'
        '@page { size: A4; margin: 14mm 12mm; }'
        f"body {{ margin:0; padding:22px 26px; font-family:'Segoe UI',Arial,sans-serif; "
        f"font-size:13px; color:{C('rpt-ink')}; background:{C('rpt-bg')}; }}"
        'p { margin:6px 0; }'
    )


def _feature_css_head(rendered, mode):
    """Theme tokens + each reused feature's scoped CSS, for the head. Deduped by
    CSS *content*, not by feature: one feature can ship different stylesheets for
    different sections (e.g. Schedule Audit's Float report uses a different
    stylesheet than OOS/Lag/Dangling), and every distinct one must be kept or the
    later section renders unstyled. Identical blocks are emitted once. Only
    emitted when a reused feature-report section is present."""
    seen = set()
    blocks = []
    for it in rendered:
        pl = it.get('payload') or {}
        if pl.get('kind') == 'html' and pl.get('css'):
            css = pl['css']
            if css not in seen:
                seen.add(css)
                blocks.append(css)
    if not blocks:
        return ''
    return report_theme.theme_style_tag(mode) + '<style>' + '\n'.join(blocks) + '</style>'


def document_parts(report_name, meta, rendered, mode='light', letterhead=None):
    """Shared assembly used by both the HTML/PDF and the Word wrappers, so the
    two never diverge. Returns ``{colors, css, head_extra, body, title}`` — plus
    the additive ``cover`` and ``inner`` pieces the HTML/PDF shell places into the
    narrative frame (the Word wrapper reads only ``body``/``css``/``head_extra``/
    ``title``, so its ``body`` — cover + contents + sections — is unchanged)."""
    C = _Colors(mode)
    report_name = report_name or 'Special Report'
    cover = _cover(report_name, meta, letterhead, C)
    if rendered:
        toc = _toc(rendered, C)
        sections = ''.join(render_section(i, item, C) for i, item in enumerate(rendered, 1))
    else:
        toc = ''
        sections = _empty_notice(C)
    inner = toc + sections
    return {'colors': C, 'css': _base_css(C), 'head_extra': _feature_css_head(rendered, mode),
            'body': cover + inner, 'title': report_name, 'cover': cover, 'inner': inner,
            'toc': toc, 'sections': sections}


# ── the Baseline-Narrative shell stylesheet (HTML/PDF only) ───────────────────
# Screen: one bordered white "paper" (``.sr-page`` + ``::before`` inset = the
# double frame). A wrapping table (``.sr-doc``) carries the running header in its
# ``thead`` and footer in its ``tfoot``; Chrome repeats BOTH on every printed page
# and reserves their height, so they never overlap the body. Print: the paper
# border is dropped and a fixed ``.sr-frame`` (+ ``::after``) repaints the double
# navy frame within each page; the ``@page`` bottom-centre counter draws the live
# page numbers. Colours come from the appearance-mode tokens EXCEPT the fixed navy
# (``@NAVY``), which is concrete hex and also declared once as ``--sr-navy``.
_SHELL_CSS = """
:root{--sr-navy:@NAVY;}
html,body{margin:0;}
body{background:@SURROUND;padding:24px;font-family:"Segoe UI",Calibri,"Helvetica Neue",Arial,sans-serif;}
.sr-page{position:relative;max-width:900px;margin:0 auto 22px;background:@PAPER;border:1.6px solid @NAVY;box-shadow:0 3px 22px rgba(0,0,0,.14);}
.sr-page::before{content:"";position:absolute;inset:6px;border:1px solid @HAIR;pointer-events:none;z-index:2;}
.sr-page>*{position:relative;z-index:3;}
/* screen: cover + contents each fill their own page-height sheet (A4-ish at 900px) */
.sr-cover-sheet,.sr-toc-sheet{min-height:1150px;}
.sr-cover-sheet{padding:6px 34px;display:flex;flex-direction:column;justify-content:center;}
.sr-frame{display:none;}
.sr-doc{width:100%;border-collapse:collapse;table-layout:fixed;}
.sr-doc>thead{display:table-header-group;}
.sr-doc>tfoot{display:table-footer-group;}
.sr-head-cell{padding:18px 40px 0;}
.sr-main{padding:14px 40px 12px;vertical-align:top;}
.sr-foot-cell{padding:0 40px 16px;}
.sr-main table.sr-dt th{background:@NAVY!important;color:#ffffff!important;border-color:@NAVY!important;}
.sr-main table.sr-dt tbody tr:nth-child(even) td{background:@ZEBRA;}
@media print{
@page{size:A4 portrait;margin:14mm;@bottom-center{content:"Page " counter(page) " of " counter(pages);font:8.5pt "Segoe UI",Calibri,sans-serif;color:@MUTED;}}
html,body{background:@PAPER;padding:0;}
.sr-page{max-width:none;margin:0;border:0;box-shadow:none;background:transparent;}
.sr-toc-sheet{min-height:0;}
/* the cover fills the printable page so the report name centres vertically on page 1 */
.sr-cover-sheet{min-height:245mm;padding:0;}
.sr-page::before{display:none;}
/* the double frame paints ABOVE the (now transparent) pages so it shows on every
   page, not just where a short page leaves the frame uncovered */
.sr-frame{display:block;position:fixed;top:0;left:0;right:0;bottom:0;border:1.4pt solid @NAVY;z-index:40;pointer-events:none;}
.sr-frame::after{content:"";position:absolute;top:3pt;left:3pt;right:3pt;bottom:3pt;border:.5pt solid @NAVY;}
.sr-head-cell{padding:5mm 6mm 0;}
.sr-main{padding:3mm 6mm 3mm;}
.sr-foot-cell{padding:0 6mm 4mm;}
tr{break-inside:avoid;}
.sr-sec-h{break-after:avoid;}
}
"""


def _shell_css(C):
    """The ``.sr-*`` narrative shell stylesheet, with the appearance-mode colours
    (and the fixed navy) resolved to concrete hex."""
    out = _SHELL_CSS
    for tok, val in (('@NAVY', C.navy), ('@PAPER', C('rpt-bg')), ('@SURROUND', C('rpt-surface-2')),
                     ('@HAIR', C('rpt-hair')), ('@MUTED', C('rpt-muted')), ('@ZEBRA', C('rpt-surface'))):
        out = out.replace(tok, val)
    return out


def build_document(report_name, meta, rendered, mode='light', letterhead=None):
    """Assemble the full themed HTML document in the Baseline-Narrative house style
    (A4 portrait · double navy page frame · running header/footer · separate cover
    and contents pages · numbered navy sections). Used for the screen preview and
    the Chrome PDF, which must look identical.

    The cover sits OUTSIDE the ``.sr-doc`` wrapping table (so the running header
    never lands on the title page); the contents + numbered sections sit in the
    single ``tbody`` cell. ``rendered`` is the list from ``registry.render(ctx,
    ids)``; reused feature sections keep their own scoped CSS. The base + feature
    CSS is injected first, the shell stylesheet last so it wins on shared elements.
    The Word wrapper does NOT use this shell — it shares only ``document_parts``.
    """
    parts = document_parts(report_name, meta, rendered, mode=mode, letterhead=letterhead)
    C = parts['colors']
    header = _running_header(meta, letterhead, C)
    footer = _running_footer(meta, C)

    def _sheet(inner_cell, cls=''):
        # A discrete "paper" sheet with the running header (thead) + footer (tfoot),
        # so each renders as its OWN page on screen and repeats them per page in print.
        return (
            f'<div class="sr-page sr-sheet{cls}">'
            '<table class="sr-doc" cellpadding="0" cellspacing="0" width="100%">'
            f'<thead><tr><td class="sr-head-cell">{header}</td></tr></thead>'
            f'<tfoot><tr><td class="sr-foot-cell">{footer}</td></tr></tfoot>'
            f'<tbody><tr><td class="sr-main">{inner_cell}</td></tr></tbody>'
            '</table></div>'
        )

    # Cover on its OWN sheet (no running header — it's the title page), then contents
    # on its OWN sheet, then the numbered sections. Separate sheets on screen; the
    # inline page-break-after on the cover/contents keeps them separate pages in print.
    cover_sheet = f'<div class="sr-page sr-sheet sr-cover-sheet">{parts["cover"]}</div>'
    toc_sheet = _sheet(parts['toc'], ' sr-toc-sheet') if parts['toc'] else ''
    body_sheet = _sheet(parts['sections'])
    page = (f'<div class="sr-frame" aria-hidden="true"></div>'
            f'{cover_sheet}{toc_sheet}{body_sheet}')
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<title>{_esc(parts["title"])}</title>'
        f'{parts["head_extra"]}<style>{parts["css"]}</style>'
        f'<style>{_shell_css(C)}</style></head><body>'
        f'{page}'
        '</body></html>'
    )
