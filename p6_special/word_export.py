"""Word export — the SAME themed HTML as the PDF, wrapped as a Word-openable
document so the Word file looks the same as the PDF and stays editable.

Word's HTML engine ignores CSS custom properties (``var(--rpt-*)``) and
``color-mix()``. The Special Report's own payloads are already emitted with
concrete hex, but the *reused* feature-report sections carry each feature's own
CSS + inline styles, which are ``var()``-based. So for the Word document we
resolve every ``var(--rpt-*)`` to its concrete hex for the chosen appearance
mode, and blend the handful of ``color-mix()`` flourishes over the report
background — so the reused sections stay themed in Word too (all six modes),
matching the PDF. Only the very few ``color-mix`` gradient decorations are
approximated rather than pixel-exact. No third-party dependency.
"""
import html as _html
import re

import report_theme
from p6_special.render_html import document_parts, _logo_srcs

# Fixed structural navy for the Word chrome (page frame, header rule, footer, table
# headers). Mirrors render_html._SR_NAVY['light']; used only if the shared _Colors
# object does not expose ``.navy`` (it always does — this is a defensive fallback).
_WORD_NAVY = '#1f3b63'

_VAR_RE = re.compile(r'var\(\s*(--rpt-[\w-]+)\s*(?:,\s*([^()]*?))?\s*\)')
_MIX_RE = re.compile(r'color-mix\(\s*in\s+srgb\s*,\s*([^,()]+?)\s*,\s*([^()]+?)\s*\)', re.I)


def _rgb(hexstr):
    h = (hexstr or '').strip().lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    if len(h) >= 6:
        try:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except ValueError:
            return None
    return None


def _hex(r, g, b):
    clamp = lambda x: max(0, min(255, round(x)))
    return '#%02x%02x%02x' % (clamp(r), clamp(g), clamp(b))


def _blend(c1, c2, w1):
    a, b = _rgb(c1), _rgb(c2)
    if not a or not b:
        return c1 if a else c2
    return _hex(a[0] * w1 + b[0] * (1 - w1), a[1] * w1 + b[1] * (1 - w1), a[2] * w1 + b[2] * (1 - w1))


def _operand(part, bg):
    """A color-mix operand -> (concrete_color, weight_or_None). 'transparent'
    resolves to the report background (Word has no alpha compositing)."""
    toks = part.split()
    color = toks[0]
    if color.lower() == 'transparent':
        color = bg
    pct = None
    for t in toks[1:]:
        if t.endswith('%'):
            try:
                pct = float(t[:-1]) / 100.0
            except ValueError:
                pass
    return color, pct


def _resolve_theme_colors(text, mode):
    """Resolve var(--rpt-*) (and simple color-mix) to concrete hex so Word themes
    the reused feature sections the same as the PDF. Leaves the PDF/screen path
    untouched (that supports var() natively)."""
    if not text:
        return text
    palette = report_theme.theme_vars(mode)
    bg = palette.get('rpt-bg', '#ffffff')

    def sub_var(m):
        tok = m.group(1)[2:]                 # '--rpt-ink' -> 'rpt-ink'
        if tok in palette:
            return palette[tok]
        fb = (m.group(2) or '').strip()
        return fb or 'inherit'

    prev = None                              # var() can nest inside color-mix
    while prev != text:
        prev = text
        text = _VAR_RE.sub(sub_var, text)

    def sub_mix(m):
        c1, p1 = _operand(m.group(1), bg)
        c2, p2 = _operand(m.group(2), bg)
        if p1 is None and p2 is None:
            p1 = 0.5
        elif p1 is None:
            p1 = 1 - p2
        return _blend(c1, c2, p1)

    return _MIX_RE.sub(sub_mix, text)


def _page_setup_css(navy, muted, zebra):
    """The Word page-setup / chrome stylesheet: an A4-portrait ``@page`` with a navy
    double page border on every page, references to the running header (``h1``) and
    page-number footer (``f1``), header/footer paragraph styles, and the navy-header
    zebra table look (Word does not get render_html's shell CSS, so the data-table
    headers are re-navied here to match the on-screen / PDF report)."""
    return (
        # ── A4 portrait section, navy double frame, header/footer references ──
        '@page WordSection1 { '
        'size: 595.3pt 841.9pt; '                       # A4 portrait (210 x 297 mm)
        'margin: 1.85cm 1.4cm 1.75cm 1.4cm; '
        'mso-header-margin: 1.0cm; '
        'mso-footer-margin: 0.9cm; '
        'mso-paper-source: 0; '
        # Functional single-file header/footer refs (Word reads these + the
        # id-matched <div style="mso-element:header|footer">). Both spellings are
        # emitted so whichever a given Word build honours takes effect; the unknown
        # one is ignored (harmless).
        'mso-header: h1; mso-footer: f1; '
        'mso-header-data: h1; mso-footer-data: f1; '
        'mso-page-border-surround-header: no; '
        'mso-page-border-surround-footer: no; '
        f'border: 1.5pt double {navy}; '                # CSS fallback (solid-capable)
        f'mso-border-alt: double {navy} 1.5pt; '        # Word page-border art
        'padding: 14.0pt 14.0pt 14.0pt 14.0pt; '
        '} '
        'div.WordSection1 { page: WordSection1; } '
        # header / footer paragraph furniture
        'p.MsoHeader, li.MsoHeader, div.MsoHeader { margin:0; mso-pagination:widow-orphan; '
        'font-size:9.0pt; } '
        'p.MsoFooter, li.MsoFooter, div.MsoFooter { margin:0; mso-pagination:widow-orphan; '
        'font-size:9.0pt; } '
        # navy-header zebra data tables (parity with render_html._SHELL_CSS, which the
        # Word path never sees). Class + descendant selectors are honoured by Word's
        # .doc HTML engine the same as the reused-feature <style> blocks already are.
        f'table.sr-dt th {{ background:{navy} !important; color:#ffffff !important; '
        f'border-color:{navy} !important; }} '
        f'table.sr-dt tbody tr:nth-child(even) td {{ background:{zebra} !important; }} '
    )


def _word_header(meta, letterhead, navy, muted):
    """The repeating page header held in a ``mso-element:header`` div (id ``h1``):
    three logo slots, then a kicker (left) + project name (right), over a navy rule.
    A missing logo leaves an empty cell so the three columns keep their positions."""
    meta = meta or {}
    lh = letterhead or {}
    project = _html.escape(str(meta.get('project_name') or 'Project'))
    kicker = _html.escape(str(lh.get('kicker') or 'Project Progress Report'))
    cells = []
    for src in _logo_srcs(letterhead):
        if src:
            inner = (f'<img src="{_html.escape(str(src))}" alt="logo" '
                     f'style="max-height:34px;max-width:150px" />')
        else:
            inner = '&nbsp;'
        cells.append(f'<td width="33%" align="center" valign="middle" '
                     f'style="padding:2px 8px">{inner}</td>')
    logos = (f'<table cellpadding="0" cellspacing="0" width="100%" '
             f'style="border-collapse:collapse;table-layout:fixed"><tr>{"".join(cells)}</tr></table>')
    band = (f'<table cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse">'
            f'<tr><td align="left" style="font-size:8.5pt;letter-spacing:.4pt;color:{navy}">{kicker}</td>'
            f'<td align="right" style="font-size:8.5pt;color:{muted}">{project}</td></tr></table>')
    return (
        '<div style="mso-element:header" id="h1">'
        f'<div style="border-bottom:1.0pt solid {navy};padding-bottom:2pt">{logos}{band}</div>'
        '</div>'
    )


def _word_footer(navy, muted):
    """The repeating page footer held in a ``mso-element:footer`` div (id ``f1``):
    a centred ``Page N`` line, where N is a live Word ``PAGE`` field
    (``mso-field-code:PAGE``); the ``1`` is the cached value shown until Word
    updates fields."""
    return (
        '<div style="mso-element:footer" id="f1">'
        f'<p class="MsoFooter" align="center" '
        f'style="text-align:center;font-size:9.0pt;color:{muted}">'
        'Page <span style="mso-field-code:PAGE">1</span></p>'
        '</div>'
    )


def build_word_document(report_name, meta, rendered, mode='light', letterhead=None):
    """Return a Word-openable HTML document string (save with a .doc extension).

    The shared cover / contents / numbered sections come from
    :func:`render_html.document_parts` (already navy concrete hex); this wrapper adds
    the Baseline-Narrative Word chrome: an A4-portrait section, a navy double page
    border on every page, a running header (3 logos + project) and a page-number
    footer, plus the navy-header zebra table look — as far as Office-Word HTML allows.
    """
    parts = document_parts(report_name, meta, rendered, mode=mode, letterhead=letterhead)
    C = parts['colors']
    navy = getattr(C, 'navy', _WORD_NAVY)
    muted = C('rpt-muted') if callable(C) else '#6b7688'
    zebra = C('rpt-surface') if callable(C) else '#f7f9fc'
    title = _html.escape(parts['title'])
    # Word ignores var()/color-mix; resolve them to hex so reused feature sections
    # stay themed (the Special Report's own payloads are already concrete hex).
    head_extra = _resolve_theme_colors(parts.get('head_extra', ''), mode)
    # Word ignores CSS `page-break-after` on a div, so force the cover, contents and
    # sections onto separate pages with an explicit Word page-break element.
    brk = '<br clear="all" style="page-break-before:always;mso-break-type:page-break">'
    cover, toc, sections = parts.get('cover', ''), parts.get('toc', ''), parts.get('sections', '')
    raw_body = cover + (brk + toc if toc else '') + (brk + sections if sections else '')
    body = _resolve_theme_colors(raw_body, mode)
    page_css = _page_setup_css(navy, muted, zebra)
    header = _word_header(meta, letterhead, navy, muted)
    footer = _word_footer(navy, muted)
    return (
        '<html xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:w="urn:schemas-microsoft-com:office:word" '
        'xmlns="http://www.w3.org/TR/REC-html40"><head>'
        '<meta charset="utf-8">'
        '<meta name="ProgId" content="Word.Document">'
        '<meta name="Generator" content="Microsoft Word 15">'
        f'<title>{title}</title>'
        '<!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View>'
        '<w:Zoom>100</w:Zoom><w:DoNotOptimizeForBrowser/></w:WordDocument></xml><![endif]-->'
        f'{head_extra}<style>{parts["css"]} {page_css}</style></head>'
        f'<body><div class="WordSection1">{body}{header}{footer}</div></body></html>'
    )


def save_word_document(html_str, output_path):
    """Write the Word HTML to ``output_path`` (a .doc path). Returns the path."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_str)
    return output_path
