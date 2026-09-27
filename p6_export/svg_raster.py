"""Charts → PNG pictures for the Word export.

Word cannot draw the report's inline SVG charts (they are styled with CSS classes,
``var(--rpt-*)`` theme tokens and ``currentColor``) nor its CSS/div charts (bar rows,
histograms, calendar grids). This module turns both into PNG pictures:

* :func:`resolve_svg` — rewrites an inline ``<svg>`` so every paint / font / stroke is a
  CONCRETE value (computed through :mod:`p6_export.css`), class/style rules removed, the
  SVG camel-case restored (the HTML parser lower-cases ``viewBox`` …). Called by
  :mod:`p6_export.html_model` while it walks the report.
* :func:`svg_to_png` — rasterises that self-styled SVG with PyMuPDF (bundled in the .exe).
* :func:`chrome_raster` — the fallback for visuals that are not a single SVG (CSS charts)
  or that PyMuPDF could not draw: ONE headless-Chrome print of all of them (each on its
  own page, same stylesheet + theme as the report), then PyMuPDF rasterises each page and
  crops it to what was drawn. Same browser engine as the PDF → the picture looks the same.
* :func:`rasterize` — fills ``Visual.png`` for every visual of a parsed report.

No network; Chrome is only launched when a visual actually needs it.
"""
import copy
import os
import re
import tempfile

from . import css as C

SVG_NS = 'http://www.w3.org/2000/svg'
XLINK_NS = 'http://www.w3.org/1999/xlink'

# the HTML parser lower-cases every SVG tag / attribute — SVG is case-sensitive
_TAG_CASE = {t.lower(): t for t in (
    'linearGradient', 'radialGradient', 'clipPath', 'textPath', 'foreignObject', 'feGaussianBlur',
    'feOffset', 'feBlend', 'feColorMatrix', 'feComposite', 'feFlood', 'feMerge', 'feMergeNode',
    'feDropShadow', 'animateTransform')}
_ATTR_CASE = {a.lower(): a for a in (
    'viewBox', 'preserveAspectRatio', 'gradientUnits', 'gradientTransform', 'patternUnits',
    'patternContentUnits', 'patternTransform', 'clipPathUnits', 'maskUnits', 'maskContentUnits',
    'markerWidth', 'markerHeight', 'markerUnits', 'refX', 'refY', 'textLength', 'lengthAdjust',
    'startOffset', 'spreadMethod', 'stdDeviation', 'baseFrequency', 'numOctaves', 'pathLength',
    'primitiveUnits', 'filterUnits', 'kernelMatrix', 'tableValues', 'specularExponent')}

_PAINT = ('fill', 'stroke')
_PASS = ('stroke-width', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'font-family',
         'font-style', 'text-anchor', 'dominant-baseline', 'letter-spacing', 'text-decoration',
         'fill-rule', 'clip-rule', 'paint-order', 'visibility')
_OPACITY = ('opacity', 'fill-opacity', 'stroke-opacity', 'stop-opacity')


def _paint(value, current):
    """A CSS paint value → ('#rrggbb' | 'none' | 'url(#x)', alpha) or None."""
    if value is None:
        return None
    low = str(value).strip().lower()
    if not low:
        return None
    if low in ('none', 'transparent'):
        return 'none', 1.0
    if low.startswith('url('):
        return str(value).strip(), 1.0
    col = C.parse_color(value, current) or C.find_color(value, current)
    if col is None:
        return None
    alpha = col[3] if len(col) > 3 else 1.0
    return '#' + C.to_hex(col[:3] + (1.0,)).lower(), alpha


def _num(v, default=1.0):
    try:
        return float(str(v).strip().rstrip('%')) / (100.0 if str(v).strip().endswith('%') else 1.0)
    except (TypeError, ValueError):
        return default


def _fix_case(el):
    for node in el.iter():
        if not C.is_element(node):
            continue
        t = C.tag_of(node)
        node.tag = _TAG_CASE.get(t, t)
        for k in list(node.attrib):
            fixed = _ATTR_CASE.get(k.lower())
            if fixed and fixed != k:
                node.attrib[fixed] = node.attrib.pop(k)


def resolve_svg(svg_el, resolver, bg_rgb=(255, 255, 255)):
    """Return standalone SVG markup whose every element carries concrete paint/font values.

    ``resolver`` is the report's :class:`p6_export.css.Resolver` (so class rules, theme
    variables and ``currentColor`` resolve exactly as the browser does)."""
    from lxml import etree
    src = [e for e in svg_el.iter() if C.is_element(e)]
    clone = copy.deepcopy(svg_el)
    clone.tail = None
    dst = [e for e in clone.iter() if C.is_element(e)]
    drop = []
    for s, d in zip(src, dst):
        tag = C.tag_of(s)
        if tag in ('style', 'script', 'title', 'desc'):
            drop.append(d)
            continue
        st = resolver.style(s)
        current = st.color()
        decl = {}
        if st.display() == 'none':
            decl['display'] = 'none'
        for p in _PAINT:
            got = _paint(st.get(p), current)
            if got:
                decl[p] = got[0]
                if got[1] < 0.999:
                    decl[p + '-opacity'] = f'{got[1] * _num(st.get(p + "-opacity"), 1.0):.3f}'
        if tag == 'stop':
            sc = st.get('stop-color') or s.get('stop-color')
            if sc and 'var(' in sc:
                sc = C.resolve_vars(sc, st.get('_custom', {}))
            got = _paint(sc, current) if sc else None
            if got:
                decl['stop-color'] = got[0]
                if got[1] < 0.999:
                    decl['stop-opacity'] = f'{got[1] * _num(st.get("stop-opacity"), 1.0):.3f}'
        for p in _PASS:
            v = st.get(p)
            if v not in (None, ''):
                decl[p] = str(v)
        for p in _OPACITY:
            v = s.get(p) if p != 'opacity' else (st.get('opacity') or s.get('opacity'))
            if v not in (None, '') and p + '' not in decl:
                decl[p] = str(v)
        if tag in ('text', 'tspan', 'textpath', 'svg', 'g'):
            decl['font-size'] = f'{st.font_px():.2f}px'
            w = str(st.get('font-weight', '400')).strip().lower()
            decl['font-weight'] = 'bold' if st.is_bold() else ('normal' if w else w)
        for k in list(d.attrib):
            if k in ('class', 'style') or k in decl:
                del d.attrib[k]
        if decl:
            d.set('style', ';'.join(f'{k}:{v}' for k, v in decl.items()))
    for d in drop:
        p = d.getparent()
        if p is not None:
            if d.tail:
                prev = d.getprevious()
                if prev is not None:
                    prev.tail = (prev.tail or '') + d.tail
                else:
                    p.text = (p.text or '') + d.tail
            p.remove(d)
    _fix_case(clone)
    clone.tag = 'svg'
    clone.set('xmlns', SVG_NS)
    if any(k.startswith('xlink:') for n in clone.iter() if C.is_element(n) for k in n.attrib):
        clone.set('xmlns:xlink', XLINK_NS)
    vb = clone.get('viewBox')
    st = resolver.style(svg_el)
    for dim in ('width', 'height'):
        v = clone.get(dim)
        if not v or v.strip().endswith('%') or v.strip() == 'auto':
            px = C.length_px(st.get(dim) or '') if st.get(dim) and not str(st.get(dim)).endswith('%') else None
            if px:
                clone.set(dim, f'{px:g}')
            elif vb and len(vb.replace(',', ' ').split()) == 4:
                clone.set(dim, vb.replace(',', ' ').split()[2 if dim == 'width' else 3])
            elif dim in clone.attrib:
                del clone.attrib[dim]
    markup = etree.tostring(clone, encoding='unicode', method='xml', with_tail=False)
    # xmlns set as a plain attribute is serialised verbatim — make sure there is exactly one
    if markup.count('xmlns="') > 1:
        markup = re.sub(r'\sxmlns="[^"]*"', '', markup)
        markup = markup.replace('<svg', f'<svg xmlns="{SVG_NS}"', 1)
    return markup


def svg_to_png(svg_markup, width_px=None, scale=2.0):
    """Rasterise a self-styled SVG with PyMuPDF → PNG bytes (``None`` if it cannot)."""
    try:
        import pymupdf
    except ImportError:                                   # pragma: no cover - bundled
        try:
            import fitz as pymupdf
        except ImportError:
            return None
    try:
        doc = pymupdf.open(stream=svg_markup.encode('utf-8'), filetype='svg')
        try:
            page = doc[0]
            w = page.rect.width or 1
            zoom = scale * ((width_px / w) if width_px else 1.0)
            zoom = max(0.5, min(zoom, 8.0))
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            if pix.width < 2 or pix.height < 2:
                return None
            return pix.tobytes('png')
        finally:
            doc.close()
    except Exception:
        return None


def _find_chrome():
    """Only when the caller passed no browser: the first installed Chromium we know of
    (never imports the server — keeps this module usable from tests / the CLI)."""
    from .pdf import chrome_candidates
    found = chrome_candidates(None)
    return found[0] if found else None


def chrome_raster(visuals, rep, chrome=None, scale=2.0, timeout=120):
    """Render ``visuals`` (html_model.Visual) with headless Chrome in ONE print, then
    rasterise + crop each page with PyMuPDF. Fills ``v.png``; returns how many were drawn."""
    visuals = [v for v in visuals if v.html]
    if not visuals:
        return 0
    chrome = chrome or _find_chrome()
    if not chrome:
        return 0
    try:
        import pymupdf
    except ImportError:                                   # pragma: no cover
        import fitz as pymupdf
    page = rep.page or {}
    margins = page.get('margins_mm') or (10, 10, 10, 10)
    content_mm = (page.get('width_mm') or 210) - margins[1] - margins[3]
    content_px = content_mm * 96 / 25.4
    blocks = ''.join(
        f'<div class="__xcap" style="width:{(v.width_px or content_px):.0f}px">{v.html}</div>'
        for v in visuals)
    html = (f'<!DOCTYPE html><html class="{rep.html_class}"><head><meta charset="utf-8">'
            f'<style>{rep.head_css}</style>'
            '<style>@page{size:' f'{content_px + 16:.0f}px 1800px;margin:0}}'
            'html,body{margin:0!important;padding:0!important}'
            '.__xcap{padding:6px;box-sizing:content-box;break-after:page;page-break-after:always;'
            'break-inside:avoid;overflow:hidden}'
            '*{-webkit-print-color-adjust:exact;print-color-adjust:exact}</style>'
            f'</head><body class="{rep.body_class}">{blocks}</body></html>')
    tmpdir = tempfile.mkdtemp(prefix='cx_raster_')
    html_path = os.path.join(tmpdir, 'v.html')
    pdf_path = os.path.join(tmpdir, 'v.pdf')
    try:
        with open(html_path, 'w', encoding='utf-8') as fh:
            fh.write(html)
        from .pdf import run_chrome
        run_chrome(chrome, [f'--print-to-pdf={pdf_path}', '--no-pdf-header-footer',
                            'file:///' + html_path.replace(os.sep, '/')], timeout=timeout)
        doc = pymupdf.open(pdf_path)
        drawn = 0
        try:
            for i, v in enumerate(visuals):
                if i >= doc.page_count:
                    break
                pg = doc[i]
                full = pg.rect
                box = None
                for _kind, r in pg.get_bboxlog():
                    rect = pymupdf.Rect(r)
                    if rect.is_empty or rect.width * rect.height >= full.width * full.height * 0.9:
                        continue
                    box = rect if box is None else box | rect
                if box is None:
                    continue
                box = (box + (-4, -4, 4, 4)) & full
                pix = pg.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=box, alpha=False)
                v.png = pix.tobytes('png')
                v.width_px = box.width
                v.height_px = box.height
                drawn += 1
        finally:
            doc.close()
        return drawn
    except Exception:
        if os.environ.get('CX_EXPORT_DEBUG'):
            raise
        return 0
    finally:
        for name in ('v.html', 'v.pdf'):
            try:
                os.unlink(os.path.join(tmpdir, name))
            except OSError:
                pass
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def rasterize(rep, chrome=None, use_chrome=True):
    """Fill ``png`` on every visual of a parsed report: SVG → PyMuPDF first; whatever is
    left (CSS charts, or an SVG PyMuPDF could not draw) → one Chrome pass."""
    pending = []
    for b in rep.all_blocks():
        if getattr(b, 'kind', '') != 'visual' or b.png:
            continue
        if b.svg:
            b.png = svg_to_png(b.svg, b.width_px)
        if not b.png:
            pending.append(b)
    if pending and use_chrome:
        chrome_raster(pending, rep, chrome=chrome)
    return rep
