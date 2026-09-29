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
    # a picture taller than one Word page is cut into page-high slices (at a blank line)
    max_h_pt = ((page.get('height_mm') or 297) - max(margins[0], 16) - max(margins[2], 14) - 12) * 72 / 25.4
    # each chart opens with an empty link to _MARK+i: Chrome writes it as a PDF link
    # annotation on the page where that chart STARTS (nothing is drawn), so a chart taller
    # than one 7000px page keeps all its pages and the next chart still gets its own picture
    blocks = ''.join(
        f'<div class="__xcap" style="width:{(v.width_px or content_px):.0f}px">'
        f'<a class="__xmk" href="{_MARK}{i}"></a>{v.html}</div>'
        for i, v in enumerate(visuals))
    html = (f'<!DOCTYPE html><html class="{rep.html_class}"><head><meta charset="utf-8">'
            f'<style>{rep.head_css}</style>'
            '<style>@page{size:' f'{content_px + 16:.0f}px 7000px;margin:0}}'
            'html,body{margin:0!important;padding:0!important}'
            '.__xcap{padding:6px;box-sizing:content-box;break-after:page;page-break-after:always;'
            'break-inside:avoid;overflow:hidden}'
            '.__xmk{position:absolute;display:block;width:1px;height:1px}'
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
            starts = _chart_start_pages(doc, len(visuals))
            firsts = sorted(set(p for p in starts if p is not None))
            for i, v in enumerate(visuals):
                first = starts[i]
                if first is None:
                    continue
                last = next((p for p in firsts if p > first), doc.page_count)
                pieces = []
                for pno in range(first, last):          # every page this chart runs onto
                    pieces.extend(_page_pieces(doc[pno], max_h_pt, scale, pymupdf))
                if not pieces:
                    continue
                v.png, v.width_px, v.height_px = pieces[0]
                v.slices = pieces if len(pieces) > 1 else None
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


_MARK = 'https://xcap.invalid/'


def _chart_start_pages(doc, n):
    """Page index where chart i starts, read from its link marker. Without markers (an old
    Chromium that drops empty links) fall back to page i only when there is exactly one
    page per chart — never guess when a chart ran onto several pages."""
    starts = [None] * n
    for pno in range(doc.page_count):
        for link in doc[pno].get_links():
            uri = link.get('uri') or ''
            if uri.startswith(_MARK) and uri[len(_MARK):].isdigit():
                i = int(uri[len(_MARK):])
                if i < n and starts[i] is None:
                    starts[i] = pno
    if all(p is None for p in starts) and doc.page_count == n:
        starts = list(range(n))
    return starts


def _page_pieces(pg, max_h_pt, scale, pymupdf):
    """Crop what is drawn on one page into (png, width_px, height_px) slices."""
    full = pg.rect
    box = None
    rects = []
    for _kind, r in pg.get_bboxlog():
        rect = pymupdf.Rect(r)
        if rect.is_empty or rect.width * rect.height >= full.width * full.height * 0.9:
            continue
        rects.append(rect)
        box = rect if box is None else box | rect
    if box is None:
        return []
    box = (box + (-4, -4, 4, 4)) & full
    pieces = []
    for clip in _slices(box, rects, max_h_pt):
        pix = pg.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False)
        # PDF points → CSS px (96 dpi) so Word sizes the picture like the PDF
        pieces.append((pix.tobytes('png'), clip.width * 96 / 72, clip.height * 96 / 72))
    return pieces


def _slices(box, rects, max_h):
    """Split ``box`` into clips no taller than ``max_h``, cutting where nothing is drawn."""
    try:
        import pymupdf
    except ImportError:                                   # pragma: no cover
        import fitz as pymupdf
    if box.height <= max_h * 1.02:
        return [box]
    inner = [r for r in rects if r.height < box.height * 0.9]
    out, y = [], box.y0
    while box.y1 - y > max_h:
        target = y + max_h
        # the clean line (nothing drawn across it) with the WIDEST blank band below it —
        # i.e. between two blocks (months, cards), not between two rows of one block
        best = None
        for c in {r.y1 for r in inner if y + max_h * 0.5 < r.y1 <= target}:
            if any(r.y0 < c - 0.5 and r.y1 > c + 0.5 for r in inner):
                continue
            nxt = min((r.y0 for r in inner if r.y0 >= c - 0.5), default=box.y1)
            key = (round(nxt - c, 1), c)
            if best is None or key > best[0]:
                best = (key, c)
        cut = min(best[1] + 2, target) if best else target
        out.append(pymupdf.Rect(box.x0, y, box.x1, cut))
        y = cut
    out.append(pymupdf.Rect(box.x0, y, box.x1, box.y1))
    return out


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
