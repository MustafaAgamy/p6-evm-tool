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
from p6_special.render_html import document_parts

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


def build_word_document(report_name, meta, rendered, mode='light', letterhead=None):
    """Return a Word-openable HTML document string (save with a .doc extension)."""
    parts = document_parts(report_name, meta, rendered, mode=mode, letterhead=letterhead)
    title = _html.escape(parts['title'])
    # Word ignores var()/color-mix; resolve them to hex so reused feature sections
    # stay themed (the Special Report's own payloads are already concrete hex).
    head_extra = _resolve_theme_colors(parts.get('head_extra', ''), mode)
    body = _resolve_theme_colors(parts['body'], mode)
    page_css = ('@page WordSection1 { size: 595.3pt 841.9pt; margin: 1.6cm 1.4cm; } '
                'div.WordSection1 { page: WordSection1; }')
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
        f'<body><div class="WordSection1">{body}</div></body></html>'
    )


def save_word_document(html_str, output_path):
    """Write the Word HTML to ``output_path`` (a .doc path). Returns the path."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_str)
    return output_path
