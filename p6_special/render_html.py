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


def _esc(s):
    return _html.escape('' if s is None else str(s))


class _Colors:
    def __init__(self, mode):
        self.mode = report_theme.normalize(mode)
        self._v = report_theme.theme_vars(self.mode)

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
    return (f'<table cellpadding="0" cellspacing="0" width="100%" '
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


_DISPATCH = {
    'kpi_group': _kpi_group, 'table': _table, 'bars': _bars, 'segbar': _segbar,
    'findings': _findings, 'keyvals': _keyvals, 'text': _text, 'note': _note,
    'no_data': _no_data, 'group': _group,
}


def render_payload(payload, C):
    if not payload:
        return _no_data({}, C)
    fn = _DISPATCH.get(payload.get('kind'))
    return fn(payload, C) if fn else _no_data({}, C)


# ── document assembly ────────────────────────────────────────────────────────
def render_section(index, item, C):
    body = render_payload(item.get('payload'), C)
    return (
        f'<div class="sr-sec" style="margin:0 0 26px;page-break-inside:avoid">'
        f'<table cellpadding="0" cellspacing="0" style="margin-bottom:10px;'
        f'border-bottom:1px solid {C("rpt-hair")};width:100%"><tr>'
        f'<td valign="middle" style="font-size:20px;font-weight:800;color:{C("rpt-accent")};padding:0 10px 8px 0">{index}</td>'
        f'<td valign="middle" style="font-size:17px;font-weight:750;color:{C("rpt-ink")};padding-bottom:8px">{_esc(item.get("title"))}</td>'
        f'</tr></table>'
        f'{body}</div>'
    )


def _fmt_date(v):
    """Show a clean date — drop any '00:00:00' time tail a stored data_date carries."""
    if not v:
        return ''
    s = str(v)
    return s.split(' ')[0] if ' ' in s else (s.split('T')[0] if 'T' in s else s)


def _cover(report_name, meta, letterhead, C):
    lh = letterhead or {}
    company = lh.get('company')
    brand = (f'<div style="font-size:13px;font-weight:700;color:{C("rpt-ink-soft")};margin-bottom:26px">{_esc(company)}</div>'
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
        f'<div class="sr-cover" style="background:{C("rpt-surface")};border:1px solid {C("rpt-edge")};'
        f'border-top:5px solid {C("rpt-accent")};padding:44px 40px;margin-bottom:34px;page-break-after:avoid">'
        f'{brand}'
        f'<div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:{C("rpt-accent")};margin-bottom:12px">{kicker}</div>'
        f'<div style="font-size:34px;font-weight:800;line-height:1.15;color:{C("rpt-ink")};max-width:640px">{_esc(report_name)}</div>'
        f'<table cellpadding="0" cellspacing="0" style="margin-top:34px"><tr>{metacells}</tr></table>'
        f'</div>'
    )


def _toc(rendered, C):
    lines = []
    for i, item in enumerate(rendered, 1):
        lines.append(
            f'<tr><td valign="top" style="font-size:13.5px;font-weight:800;color:{C("rpt-accent")};width:28px;padding:6px 0">{i}</td>'
            f'<td style="font-size:13.5px;font-weight:600;color:{C("rpt-ink")};padding:6px 0">{_esc(item.get("title"))}</td></tr>'
        )
    return (
        f'<div class="sr-toc" style="margin-bottom:30px;page-break-after:avoid">'
        f'<div style="font-size:12px;letter-spacing:1.5px;text-transform:uppercase;color:{C("rpt-muted")};'
        f'border-bottom:2px solid {C("rpt-hair-strong")};padding-bottom:10px;margin-bottom:6px">Table of contents</div>'
        f'<table cellpadding="0" cellspacing="0" width="100%">{"".join(lines)}</table></div>'
    )


def _base_css(C):
    return (
        '* { -webkit-print-color-adjust:exact; print-color-adjust:exact; box-sizing:border-box; }'
        '@page { size: A4; margin: 14mm 12mm; }'
        f"body {{ margin:0; padding:22px 26px; font-family:'Segoe UI',Arial,sans-serif; "
        f"font-size:13px; color:{C('rpt-ink')}; background:{C('rpt-bg')}; }}"
        'p { margin:6px 0; }'
    )


def document_parts(report_name, meta, rendered, mode='light', letterhead=None):
    """Shared assembly used by both the HTML/PDF and the Word wrappers, so the
    two never diverge. Returns ``{colors, css, body, title}``."""
    C = _Colors(mode)
    report_name = report_name or 'Special Report'
    body = _cover(report_name, meta, letterhead, C)
    if rendered:
        body += _toc(rendered, C)
        body += ''.join(render_section(i, item, C) for i, item in enumerate(rendered, 1))
    else:
        body += (f'<div style="font-size:13px;color:{C("rpt-muted")};padding:20px 0">'
                 f'No results selected. Pick results on the left to build the report.</div>')
    return {'colors': C, 'css': _base_css(C), 'body': body, 'title': report_name}


def build_document(report_name, meta, rendered, mode='light', letterhead=None):
    """Assemble the full themed HTML document (cover + TOC + numbered sections).

    ``rendered`` is the list from ``registry.render(ctx, ids)``.
    Returns a complete ``<html>`` string used for screen preview and Chrome PDF;
    ``word_export`` wraps the same parts for Word so all three look identical.
    """
    parts = document_parts(report_name, meta, rendered, mode=mode, letterhead=letterhead)
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<title>{_esc(parts["title"])}</title>'
        f'<style>{parts["css"]}</style></head><body>'
        f'{parts["body"]}'
        '</body></html>'
    )
