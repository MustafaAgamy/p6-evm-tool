"""Report HTML → a neutral block model (the ONE document every export is built from).

The preview overlay holds the exact final report HTML (feature render for the chosen
sections + appearance mode, with unticked parts already removed on the client). Word
and Excel cannot read HTML/CSS, so this module turns that one HTML string into plain
blocks — headings, paragraphs of styled runs, lists, tables (with concrete cell colours),
KPI tile groups, images and visuals (charts to rasterise) — grouped into the report's
sections (``[data-sec]`` wrappers). Every colour is resolved to a concrete hex through
:mod:`p6_export.css`, so no ``var(--x)`` can leak into Word.

Renderer hints (all optional — see docs/report-picker-adoption.md):
  data-sec="key"            a top-level report section (sheet in Excel)
  data-sec-label="…"        the section's title when it has no heading
  data-part="sec.part"      a selectable part (picker) — tagged on the blocks it produces
  data-part-label="…"       the part's label (picker + Excel block title)
  data-export="image"       a visual (CSS/div chart) → picture in Word, data in Excel
  data-export="kpis"        force a KPI tile group        data-export="tile" one tile
  data-export="skip"        screen-only chrome — left out of every export
  data-chart-headers='[…]'  + data-chart-data='[[…],…]'  the numbers behind a visual (Excel,
                            and the Word fallback when a picture cannot be produced)
"""
import base64
import json
import re
from dataclasses import dataclass, field

import lxml.html
from lxml import etree

from . import css as C

# ── the block model ────────────────────────────────────────────────────────────


@dataclass
class Run:
    text: str = ''
    bold: bool = False
    italic: bool = False
    color: str = None          # 'RRGGBB'
    bg: str = None             # 'RRGGBB' — pill / badge shading
    size_pt: float = None
    underline: bool = False
    strike: bool = False
    caps: bool = False
    font: str = None
    br: bool = False           # a line break (text ignored)
    sup: bool = False
    sub: bool = False


def runs_text(runs):
    return ''.join('\n' if r.br else r.text for r in runs)


@dataclass
class Paragraph:
    runs: list = field(default_factory=list)
    align: str = 'left'
    bg: str = None
    border_left: tuple = None      # (width_pt, 'RRGGBB')
    border_bottom: tuple = None
    size_pt: float = None
    keep_with_next: bool = False
    role: str = 'p'                # 'p' | 'row' (joined flex row) | 'pre'
    part: str = None
    kind: str = 'paragraph'

    @property
    def text(self):
        return runs_text(self.runs).strip()


@dataclass
class Heading:
    level: int = 2
    runs: list = field(default_factory=list)
    align: str = 'left'
    border_bottom: tuple = None
    size_pt: float = None
    part: str = None
    kind: str = 'heading'
    keep_with_next: bool = True

    @property
    def text(self):
        return runs_text(self.runs).strip()


@dataclass
class ListBlock:
    ordered: bool = False
    items: list = field(default_factory=list)      # [[Run]]
    size_pt: float = None
    part: str = None
    kind: str = 'list'


@dataclass
class Cell:
    runs: list = field(default_factory=list)
    bg: str = None
    color: str = None
    bold: bool = False
    italic: bool = False
    align: str = 'left'
    colspan: int = 1
    rowspan: int = 1
    header: bool = False
    size_pt: float = None

    @property
    def text(self):
        return re.sub(r'[ \t]+', ' ', runs_text(self.runs)).strip()


@dataclass
class Table:
    rows: list = field(default_factory=list)       # [[Cell]]
    header_rows: int = 0
    col_weights: list = field(default_factory=list)
    caption: str = None
    border_color: str = None
    size_pt: float = None
    part: str = None
    kind: str = 'table'

    @property
    def ncols(self):
        return max((sum(c.colspan for c in r) for r in self.rows), default=0)


@dataclass
class Tile:
    label: str = ''
    value: str = ''
    note: str = ''
    accent: str = None         # left-edge accent colour
    value_color: str = None
    label_color: str = None
    note_color: str = None
    bg: str = None
    border: str = None
    value_pt: float = None
    label_pt: float = None


@dataclass
class KpiGroup:
    tiles: list = field(default_factory=list)
    columns: int = 4
    part: str = None
    kind: str = 'kpis'


@dataclass
class ImageBlock:
    data: bytes = b''
    mime: str = 'image/png'
    width_px: float = None
    height_px: float = None
    alt: str = ''
    part: str = None
    kind: str = 'image'


@dataclass
class Visual:
    html: str = ''             # outer HTML of the element (for the Chrome raster)
    svg: str = None            # resolved, self-styled SVG markup (PyMuPDF raster)
    width_px: float = None
    height_px: float = None
    title: str = ''
    data_headers: list = None
    data_rows: list = None
    text_lines: list = field(default_factory=list)
    bg: str = None             # effective background behind the visual
    part: str = None
    kind: str = 'visual'
    png: bytes = None          # filled by a rasteriser
    slices: list = None        # [(png, w_px, h_px)] when the picture is taller than a page


@dataclass
class PageBreak:
    kind: str = 'pagebreak'
    part: str = None


@dataclass
class Section:
    key: str = ''
    title: str = ''
    blocks: list = field(default_factory=list)
    kind: str = 'section'
    part: str = None


@dataclass
class ReportDoc:
    title: str = ''
    page: dict = field(default_factory=dict)
    theme: dict = field(default_factory=dict)       # {'rpt-bg': '#…', …}
    bg: str = 'FFFFFF'
    ink: str = '000000'
    font_family: str = 'Segoe UI'
    base_pt: float = 8.25
    front: list = field(default_factory=list)
    sections: list = field(default_factory=list)
    tail: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    head_css: str = ''                              # every <style> (for rasterising visuals)
    part_labels: dict = field(default_factory=dict)  # data-part id → label
    html_class: str = ''
    body_class: str = ''

    def all_blocks(self):
        out = list(self.front)
        for s in self.sections:
            out.extend(s.blocks)
        out.extend(self.tail)
        return out


# ── parsing helpers ────────────────────────────────────────────────────────────
_SKIP_TAGS = {'head', 'script', 'style', 'template', 'noscript', 'meta', 'link', 'title',
              'base', 'input', 'button', 'select', 'textarea', 'option', 'iframe', 'object',
              'embed', 'canvas', 'audio', 'video', 'map', 'dialog'}
_INLINE_TAGS = {'a', 'abbr', 'b', 'bdi', 'bdo', 'br', 'cite', 'code', 'data', 'dfn', 'em', 'i',
                'kbd', 'mark', 'q', 's', 'samp', 'small', 'span', 'strong', 'sub', 'sup', 'time',
                'u', 'var', 'label', 'font', 'del', 'ins', 'strike', 'tt', 'big', 'wbr', 'nobr'}
_HEADINGS = {'h1': 1, 'h2': 2, 'h3': 3, 'h4': 4, 'h5': 5, 'h6': 6}
_BLOCKY = {'table', 'svg', 'img', 'ul', 'ol', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div',
           'section', 'article', 'header', 'footer', 'figure', 'blockquote', 'pre', 'dl', 'hr',
           'main', 'aside', 'nav', 'li', 'details'}
_TILE_TOKENS = {'kpi', 'kpi-tile', 'tile', 'stat', 'stat-card', 'metric', 'kpi-card',
                'metric-card', 'stat-tile'}
_LABEL_TOKENS = ('k', 'label', 'kpi-label', 'lab', 'lbl', 't', 'title', 'name', 'stat-label',
                 'metric-label', 'kpi-k')
_VALUE_TOKENS = ('v', 'value', 'kpi-value', 'val', 'num', 'big', 'stat-value', 'metric-value',
                 'kpi-v')
_NOTE_TOKENS = ('n', 'note', 'kpi-note', 'sub', 's', 'hint', 'foot', 'stat-sub', 'kpi-n')
_BREAK_VALUES = ('page', 'always', 'left', 'right', 'recto', 'verso')


def _norm_ws(s):
    return re.sub(r'\s+', ' ', s or '')


def _pt(px):
    return None if px is None else round(px * 0.75, 2)


def _align(st):
    a = str(st.get('text-align', 'left')).strip().lower()
    if a in ('right', 'end', '-webkit-right'):
        return 'right'
    if a in ('center', '-webkit-center', 'middle'):
        return 'center'
    if a == 'justify':
        return 'justify'
    return 'left'


def _first_family(ff):
    for f in C._split_top(str(ff or '')):
        f = f.strip().strip('"\'')
        if f and f.lower() not in ('sans-serif', 'serif', 'monospace', 'system-ui', 'inherit',
                                   '-apple-system', 'blinkmacsystemfont', 'ui-sans-serif',
                                   'cursive', 'fantasy', 'emoji'):
            return f
    return None


def _json_attr(el, name):
    v = el.get(name)
    if not v:
        return None
    try:
        return json.loads(v)
    except (ValueError, TypeError):
        return None


class _Walker:
    """Converts DOM elements to blocks with the document's computed styles."""

    def __init__(self, resolver, page_bg_rgb, content_width_px):
        self.r = resolver
        self.page_bg_rgb = page_bg_rgb
        self.content_width_px = content_width_px
        self._eff_bg = {}
        self.part_labels = {}           # data-part id → data-part-label (picker / Excel titles)

    # ── colour helpers ──
    def eff_bg_rgb(self, el):
        """The opaque colour painted BEHIND ``el`` (its own bg, else an ancestor's)."""
        chain = []
        node = el
        while node is not None:
            if C.is_element(node):
                hit = self._eff_bg.get(node)
                if hit is not None:
                    base = hit
                    break
                chain.append(node)
            node = node.getparent()
        else:
            base = self.page_bg_rgb
        for n in reversed(chain):
            bg = self.r.style(n).background()
            if bg is not None:
                base = C.blend(bg, base)
            self._eff_bg[n] = base
        return self._eff_bg[el] if el in self._eff_bg else base

    def hex_over(self, rgba, el):
        if rgba is None:
            return None
        parent = el.getparent()
        under = self.eff_bg_rgb(parent) if parent is not None else self.page_bg_rgb
        return C.to_hex(rgba, under)

    def color_hex(self, el):
        return C.to_hex(self.r.style(el).color(), self.eff_bg_rgb(el))

    def own_bg_hex(self, el):
        return self.hex_over(self.r.style(el).background(), el)

    def border(self, el, side):
        b = self.r.border_color(el, side)
        if not b:
            return None
        w, col = b
        if w <= 0:
            return None
        return (round(w * 0.75, 2), C.to_hex(col, self.eff_bg_rgb(el)))

    # ── classification ──
    def hidden(self, el):
        if not C.is_element(el):
            return True
        tag = C.tag_of(el)
        if tag in _SKIP_TAGS:
            return True
        if el.get('data-export') == 'skip' or el.get('aria-hidden') == 'true' and not (el.text_content() or '').strip():
            return True
        return self.r.is_hidden(el)

    def is_inline(self, el):
        tag = C.tag_of(el)
        if tag in _BLOCKY and tag not in _INLINE_TAGS:
            if tag != 'svg':
                return False
        d = self.r.style(el).display()
        if tag == 'svg':
            return self._is_icon_svg(el)
        if tag == 'img':
            return False
        if tag == 'br':
            return True
        if not d.startswith('inline') and d != 'contents':
            return False
        for d2 in el.iter():
            if d2 is el or not C.is_element(d2):
                continue
            t2 = C.tag_of(d2)
            if t2 in ('table', 'ul', 'ol', 'img') or t2 in _HEADINGS:
                return False
            if t2 == 'svg' and not self._is_icon_svg(d2):
                return False
        return True

    def _is_icon_svg(self, el):
        w = C.length_px(el.get('width') or '') or 0
        h = C.length_px(el.get('height') or '') or 0
        st = self.r.style(el)
        w = w or C.length_px(st.get('width') or '') or 0
        h = h or C.length_px(st.get('height') or '') or 0
        if 0 < w <= 24 and 0 < h <= 24:
            return True
        return False

    def is_tile(self, el):
        if el.get('data-export') == 'tile':
            return True
        toks = set(C.classes_of(el))
        if not toks & _TILE_TOKENS:
            return False
        for d in el.iter():
            if C.is_element(d) and C.tag_of(d) in ('table', 'svg', 'img', 'ul', 'ol', 'h1', 'h2', 'h3'):
                return False
        leaves = [t for t in (x.strip() for x in el.itertext()) if t]
        return 1 <= len(leaves) <= 6

    def visible_children(self, el):
        return [c for c in el if C.is_element(c) and not self.hidden(c)]

    def is_tile_group(self, el):
        if el.get('data-export') == 'kpis':
            return True
        kids = self.visible_children(el)
        return len(kids) >= 1 and all(self.is_tile(k) for k in kids) and \
            (el.text or '').strip() == '' and all(not (k.tail or '').strip() for k in kids)

    # ── runs ──
    def runs_of(self, el, out=None, inherit_bg=False):
        """Inline runs for ``el``'s content (text + inline descendants)."""
        if out is None:
            out = []
        st = self.r.style(el)
        pre = str(st.get('white-space', 'normal')).startswith('pre')
        if el.text:
            self._text_run(out, el.text, el, st, pre)
        for ch in el:
            if C.is_element(ch) and not self.hidden(ch):
                tag = C.tag_of(ch)
                if tag == 'br':
                    out.append(Run(br=True))
                elif tag in ('table',):
                    self._table_text_runs(ch, out)
                elif tag == 'svg' or tag == 'img':
                    pass
                elif tag in ('ul', 'ol'):
                    for li in ch:
                        if C.is_element(li) and not self.hidden(li):
                            out.append(Run(br=True))
                            out.append(Run(text='• '))
                            self.runs_of(li, out)
                else:
                    is_blockish = not self.r.style(ch).display().startswith('inline') and tag not in _INLINE_TAGS
                    if is_blockish and out and not out[-1].br and runs_text(out).strip():
                        out.append(Run(br=True))
                    swatch = self._swatch(ch)
                    if swatch:
                        out.append(swatch)
                    else:
                        self.runs_of(ch, out)
                    if is_blockish and runs_text(out).strip():
                        out.append(Run(br=True))
            if ch.tail:
                self._text_run(out, ch.tail, el, st, pre)
        return out

    def _swatch(self, el):
        """An empty coloured inline box (legend key) → a ■ in that colour."""
        if (el.text_content() or '').strip():
            return None
        st = self.r.style(el)
        bg = st.background()
        if bg is None:
            return None
        return Run(text='■ ', color=self.hex_over(bg, el), size_pt=_pt(st.font_px()))

    def _text_run(self, out, text, el, st, pre):
        t = text if pre else _norm_ws(text)
        if not t:
            return
        if pre and '\n' in t:
            lines = t.split('\n')
            for i, line in enumerate(lines):
                if i:
                    out.append(Run(br=True))
                if line:
                    out.append(self._mk_run(line, el, st))
            return
        out.append(self._mk_run(t, el, st))

    def _mk_run(self, text, el, st):
        tag = C.tag_of(el)
        deco = str(st.get('text-decoration', '') or st.get('text-decoration-line', '')).lower()
        bg = None
        if st.display().startswith('inline') or tag in _INLINE_TAGS:
            own = st.background()
            if own is not None:
                bg = self.hex_over(own, el)
        va = str(st.get('vertical-align', '')).lower()
        return Run(text=text, bold=st.is_bold() or tag in ('b', 'strong'),
                   italic=st.is_italic() or tag in ('i', 'em') and bool((el.text or '').strip()),
                   color=self.color_hex(el), bg=bg, size_pt=_pt(st.font_px()),
                   underline='underline' in deco, strike='line-through' in deco,
                   caps=str(st.get('text-transform', '')).lower() == 'uppercase',
                   font=_first_family(st.get('font-family')),
                   sup=tag == 'sup' or va == 'super', sub=tag == 'sub' or va == 'sub')

    def _table_text_runs(self, table, out):
        for tr in table.iter('tr'):
            cells = [c for c in tr if C.is_element(c) and C.tag_of(c) in ('td', 'th')]
            txt = ' | '.join(_norm_ws(c.text_content()).strip() for c in cells)
            if txt.strip():
                if out and not out[-1].br:
                    out.append(Run(br=True))
                out.append(Run(text=txt))

    @staticmethod
    def trim(runs):
        """Collapse whitespace across run boundaries; drop leading/trailing spaces/breaks."""
        out = []
        prev_space = True
        for r in runs:
            if r.br:
                if out and not out[-1].br:
                    out.append(r)
                prev_space = True
                continue
            t = r.text
            if prev_space:
                t = t.lstrip(' ')
            if not t:
                continue
            prev_space = t.endswith(' ')
            r.text = t
            out.append(r)
        while out and (out[-1].br or not out[-1].text.strip()):
            if out[-1].br:
                out.pop()
                continue
            out[-1].text = out[-1].text.rstrip()
            if not out[-1].text:
                out.pop()
            else:
                break
        if out and not out[-1].br:
            out[-1].text = out[-1].text.rstrip()
        return out

    # ── block conversion ──
    def convert(self, el, part=None):
        if self.hidden(el):
            return []
        own_part = el.get('data-part')
        if own_part:
            self.part_labels.setdefault(own_part, (el.get('data-part-label') or '').strip())
        part = own_part or part
        tag = C.tag_of(el)
        st = self.r.style(el)
        blocks = self._convert(el, tag, st, part)
        before = str(st.get('break-before') or st.get('page-break-before') or '').lower()
        after = str(st.get('break-after') or st.get('page-break-after') or '').lower()
        if before in _BREAK_VALUES and blocks:
            blocks = [PageBreak(part=part)] + blocks
        if after in _BREAK_VALUES and blocks:
            blocks = blocks + [PageBreak(part=part)]
        return blocks

    def _convert(self, el, tag, st, part):
        sec = el.get('data-sec')
        if sec is not None and not getattr(self, '_in_section', False):
            self._in_section = True
            try:
                inner = self.children_blocks(el, part)
            finally:
                self._in_section = False
            return [Section(key=sec, title=el.get('data-sec-label') or '', blocks=inner)]
        if el.get('data-export') == 'image':
            return [self.visual(el, part)]
        if tag == 'svg':
            if self._is_icon_svg(el):
                return []
            return [self.visual(el, part)]
        if tag == 'table':
            t = self.table(el, part)
            return [t] if t.rows else []
        if tag == 'img':
            img = self.image(el, part)
            return [img] if img else []
        if tag in _HEADINGS:
            runs = self.trim(self.runs_of(el))
            if not runs:
                return []
            return [Heading(level=_HEADINGS[tag], runs=runs, align=_align(st),
                            border_bottom=self.border(el, 'bottom'), size_pt=_pt(st.font_px()),
                            part=part)]
        if tag in ('ul', 'ol'):
            items = []
            for li in el:
                if C.is_element(li) and not self.hidden(li):
                    runs = self.trim(self.runs_of(li))
                    if runs:
                        items.append(runs)
            return [ListBlock(ordered=tag == 'ol', items=items, size_pt=_pt(st.font_px()),
                              part=part)] if items else []
        if tag in ('br', 'hr', 'wbr'):
            return []
        if self.is_tile_group(el):
            g = self.kpi_group(el, self.visible_children(el), part)
            return [g] if g.tiles else []
        if self.is_tile(el):
            g = self.kpi_group(el, [el], part, single=True)
            return [g] if g.tiles else []
        if tag == 'pre':
            runs = self.trim(self.runs_of(el))
            return [Paragraph(runs=runs, role='pre', part=part, size_pt=_pt(st.font_px()),
                              bg=self.own_bg_hex(el))] if runs else []
        return self.container(el, st, part)

    def children_blocks(self, el, part):
        return self.container(el, self.r.style(el), part)

    def _flex_row(self, el, st):
        d = st.display()
        if d not in ('flex', 'inline-flex', 'grid', 'inline-grid'):
            return None
        if d.endswith('flex') and str(st.get('flex-direction', 'row')).startswith('column'):
            return None
        kids = self.visible_children(el)
        if len(kids) < 2 or (el.text or '').strip():
            return None
        for k in kids:
            if not self._simple(k):
                return None
            if len(_norm_ws(k.text_content()).strip()) > 90:
                return None
        return kids

    def _simple(self, el):
        """Only inline content inside (no nested blocks with their own structure)."""
        for d in el.iter():
            if not C.is_element(d) or d is el:
                continue
            t = C.tag_of(d)
            if t in ('table', 'ul', 'ol', 'img', 'svg', 'p') or t in _HEADINGS:
                return False
            if t == 'div' and (d.text_content() or '').strip():
                ds = self.r.style(d).display()
                if not ds.startswith('inline'):
                    # a block div with text inside → allowed only if it has no element children
                    if any(C.is_element(x) and not self.hidden(x) and
                           not self.r.style(x).display().startswith('inline') for x in d):
                        return False
        return True

    def container(self, el, st, part):
        row = self._flex_row(el, st)
        if row:
            runs = []
            sep_color = self.color_hex(el)
            for i, k in enumerate(row):
                kr = self.trim(self._flat_runs(k))
                if not kr:
                    swatch = self._swatch(k)
                    if swatch:
                        runs.append(swatch)
                    continue
                if runs and not (runs[-1].text or '').endswith('■ '):
                    runs.append(Run(text='   ·   ', color=sep_color, size_pt=_pt(st.font_px())))
                runs.extend(kr)
            runs = self.trim(runs)
            if runs:
                return [self._para(el, st, runs, part, role='row')]
            return []
        out, buf = [], []

        def flush():
            runs = self.trim(buf[:])
            buf.clear()
            if runs:
                out.append(self._para(el, st, runs, part))

        pre = str(st.get('white-space', 'normal')).startswith('pre')
        if el.text:
            self._text_run(buf, el.text, el, st, pre)
        for ch in el:
            if C.is_element(ch) and not self.hidden(ch):
                if self.is_inline(ch):
                    if C.tag_of(ch) == 'br':
                        buf.append(Run(br=True))
                    else:
                        sw = self._swatch(ch)
                        if sw:
                            buf.append(sw)
                        else:
                            self.runs_of(ch, buf)
                else:
                    flush()
                    out.extend(self.convert(ch, part))
            if ch.tail:
                self._text_run(buf, ch.tail, el, st, pre)
        flush()
        return out

    def _flat_runs(self, el):
        """Runs of a simple element whose block children are joined by spaces."""
        out = self.runs_of(el)
        return [r if not r.br else Run(text=' ') for r in out]

    def _para(self, el, st, runs, part, role='p'):
        return Paragraph(runs=runs, align=_align(st), bg=self.own_bg_hex(el),
                         border_left=self.border(el, 'left'), border_bottom=None,
                         size_pt=_pt(st.font_px()), role=role, part=part)

    # ── tables ──
    def table(self, el, part):
        st = self.r.style(el)
        rows_el = []
        for tr in el.iter('tr'):
            # nearest table ancestor must be this table (skip nested tables' rows)
            p = tr.getparent()
            while p is not None and C.tag_of(p) != 'table':
                p = p.getparent()
            if p is el and not self.hidden(tr):
                rows_el.append(tr)
        rows, header_rows, leading = [], 0, True
        for tr in rows_el:
            cells_el = [c for c in tr if C.is_element(c) and C.tag_of(c) in ('td', 'th')
                        and not self.hidden(c)]
            if not cells_el:
                continue
            in_head = C.tag_of(tr.getparent()) == 'thead'
            all_th = all(C.tag_of(c) == 'th' for c in cells_el)
            is_header = in_head or (leading and all_th)
            if is_header and leading:
                header_rows += 1
            else:
                leading = False
            row = []
            for c in cells_el:
                row.append(self.cell(c, tr, is_header))
            rows.append(row)
        caption = None
        cap = el.find('caption')
        if cap is not None:
            caption = _norm_ws(cap.text_content()).strip() or None
        weights = self._col_weights(el, rows)
        border = None
        for tr in rows_el[header_rows:header_rows + 1] or rows_el[:1]:
            for c in tr:
                if C.is_element(c):
                    b = self.border(c, 'bottom')
                    if b:
                        border = b[1]
                        break
        return Table(rows=rows, header_rows=header_rows, col_weights=weights, caption=caption,
                     border_color=border, size_pt=_pt(st.font_px()), part=part)

    def cell(self, c, tr, is_header):
        st = self.r.style(c)
        runs = self.trim(self.runs_of(c))
        bg = self.own_bg_hex(c)
        if bg is None:
            # the row / row-group / table background shows through a transparent cell
            node = tr
            while node is not None and C.tag_of(node) in ('tr', 'thead', 'tbody', 'tfoot', 'table'):
                bg = self.own_bg_hex(node)
                if bg is not None or C.tag_of(node) == 'table':
                    break
                node = node.getparent()
        try:
            colspan = max(1, int(c.get('colspan') or 1))
        except ValueError:
            colspan = 1
        try:
            rowspan = max(1, int(c.get('rowspan') or 1))
        except ValueError:
            rowspan = 1
        return Cell(runs=runs, bg=bg, color=self.color_hex(c), bold=st.is_bold(),
                    italic=st.is_italic(), align=_align(st), colspan=colspan, rowspan=rowspan,
                    header=is_header or C.tag_of(c) == 'th', size_pt=_pt(st.font_px()))

    def _col_weights(self, el, rows):
        n = max((sum(c.colspan for c in r) for r in rows), default=0)
        if not n:
            return []
        # explicit widths from <col>
        cols = [c for c in el.iter('col')]
        if len(cols) == n:
            ws = []
            for c in cols:
                w = c.get('width') or self.r.style(c).get('width')
                ws.append(self._pct_or_px(w))
            if all(w for w in ws):
                return self._norm(ws)
        est = [0.0] * n
        for ri, r in enumerate(rows):
            ci = 0
            for cell in r:
                t = cell.text
                if cell.colspan == 1 and ci < n:
                    if cell.header:
                        longest = max((len(w) for w in t.split()), default=1)
                        est[ci] = max(est[ci], min(18.0, longest + 1.0))
                    else:
                        est[ci] = max(est[ci], min(42.0, len(t) + 1.0))
                ci += cell.colspan
        est = [max(3.5, e) for e in est]
        return self._norm(est)

    @staticmethod
    def _pct_or_px(w):
        if not w:
            return None
        w = str(w).strip()
        if w.endswith('%'):
            try:
                return float(w[:-1])
            except ValueError:
                return None
        px = C.length_px(w if not w.isdigit() else w + 'px')
        return px

    @staticmethod
    def _norm(ws):
        tot = sum(ws) or 1.0
        return [w / tot for w in ws]

    # ── tiles ──
    def kpi_group(self, el, tiles_el, part, single=False):
        st = self.r.style(el)
        tiles = [t for t in (self.tile(t) for t in tiles_el) if t]
        cols = None
        gtc = str(st.get('grid-template-columns', '') or '')
        m = re.search(r'repeat\(\s*(\d+)', gtc)
        if m:
            cols = int(m.group(1))
        elif gtc and not single:
            tracks = [t for t in C._split_top(gtc.strip(), ' ') if t.strip()]
            if tracks:
                cols = len(tracks)
        if not cols:
            cols = min(len(tiles), 5) if st.display() in ('flex', 'inline-flex') else min(len(tiles), 4)
        cols = max(1, min(cols, 6, len(tiles) or 1))
        return KpiGroup(tiles=tiles, columns=cols, part=part)

    def tile(self, el):
        def pick(tokens):
            for d in el.iter():
                if d is el or not C.is_element(d) or self.hidden(d):
                    continue
                if set(C.classes_of(d)) & set(tokens):
                    return d
            return None
        lab_el, val_el, note_el = pick(_LABEL_TOKENS), pick(_VALUE_TOKENS), pick(_NOTE_TOKENS)
        leaves = []
        for d in el.iter():
            if not C.is_element(d) or self.hidden(d):
                continue
            own = (d.text or '').strip()
            if own:
                leaves.append(d)
        def txt(x):
            return _norm_ws(x.text_content()).strip() if x is not None else ''
        if val_el is None and lab_el is None and leaves:
            lab_el = leaves[0]
            val_el = leaves[1] if len(leaves) > 1 else None
            note_el = leaves[2] if len(leaves) > 2 else None
        label, value, note = txt(lab_el), txt(val_el), txt(note_el)
        if not (label or value):
            return None
        acc = self.border(el, 'left')
        border = self.border(el, 'top') or self.border(el, 'right')
        vst = self.r.style(val_el) if val_el is not None else None
        lst = self.r.style(lab_el) if lab_el is not None else None
        return Tile(label=label, value=value, note=note,
                    accent=acc[1] if acc and acc[0] >= 1.5 else None,
                    value_color=self.color_hex(val_el) if val_el is not None else None,
                    label_color=self.color_hex(lab_el) if lab_el is not None else None,
                    note_color=self.color_hex(note_el) if note_el is not None else None,
                    bg=self.own_bg_hex(el), border=border[1] if border else None,
                    value_pt=_pt(vst.font_px()) if vst is not None else None,
                    label_pt=_pt(lst.font_px()) if lst is not None else None)

    # ── images / visuals ──
    def image(self, el, part):
        src = el.get('src') or ''
        m = re.match(r'data:(image/[\w.+-]+);base64,(.*)$', src, re.S)
        if not m:
            return None
        try:
            data = base64.b64decode(m.group(2))
        except ValueError:
            return None
        st = self.r.style(el)
        w = C.length_px(el.get('width') or '') or C.length_px(st.get('width') or '')
        h = C.length_px(el.get('height') or '') or C.length_px(st.get('height') or '')
        return ImageBlock(data=data, mime=m.group(1), width_px=w, height_px=h,
                          alt=el.get('alt') or '', part=part)

    def _part_is_visual(self, el, part):
        """True when ``el`` is the only content of its part (so the part label names it)."""
        p = el.getparent()
        while p is not None and p.get('data-part') != part:
            p = p.getparent()
        if p is None:
            return False
        txt = _norm_ws(p.text_content()).strip()
        return txt == _norm_ws(el.text_content()).strip()

    def visual(self, el, part):
        from . import svg_raster
        tag = C.tag_of(el)
        st = self.r.style(el)
        svg = None
        svg_el = el if tag == 'svg' else None
        if svg_el is None:
            svgs = [s for s in el.iter('svg') if not self._is_icon_svg(s)]
            texts = _norm_ws(''.join(
                t for t in el.itertext())).strip()
            svg_texts = ''.join(_norm_ws(''.join(s.itertext())) for s in svgs).strip()
            if len(svgs) == 1 and texts.replace(' ', '') == svg_texts.replace(' ', ''):
                svg_el = svgs[0]
        if svg_el is not None:
            try:
                svg = svg_raster.resolve_svg(svg_el, self.r, self.eff_bg_rgb(svg_el))
            except Exception:
                svg = None
        w = C.length_px(el.get('width') or '') or C.length_px(st.get('width') or '')
        h = C.length_px(el.get('height') or '') or C.length_px(st.get('height') or '')
        if svg_el is not None and (not w or not h):
            vb = (svg_el.get('viewBox') or svg_el.get('viewbox') or '').replace(',', ' ').split()
            if len(vb) == 4:
                try:
                    vw, vh = float(vb[2]), float(vb[3])
                    if not w and not h:
                        w, h = vw, vh
                    elif w and not h and vw:
                        h = w * vh / vw
                    elif h and not w and vh:
                        w = h * vw / vh
                except ValueError:
                    pass
        title = (el.get('data-part-label') or el.get('aria-label')
                 or (self.part_labels.get(part) if part and self._part_is_visual(el, part) else '') or '')
        lines = [t for t in (_norm_ws(x).strip() for x in el.itertext()) if t]
        return Visual(html=etree.tostring(el, encoding='unicode', method='html', with_tail=False),
                      svg=svg, width_px=w, height_px=h, title=title,
                      data_headers=_json_attr(el, 'data-chart-headers'),
                      data_rows=_json_attr(el, 'data-chart-data'),
                      text_lines=lines, bg=C.to_hex(self.eff_bg_rgb(el) + (1.0,)), part=part)


# ── post-processing ────────────────────────────────────────────────────────────
_CONTENT_KINDS = ('table', 'kpis', 'visual', 'image', 'list')


def _keep_titles_with_content(blocks):
    """No orphaned titles: a heading, or a short label line, directly before content
    is kept on the same page as it (Word keep_with_next / Excel block title)."""
    for i, b in enumerate(blocks):
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        if b.kind == 'heading':
            b.keep_with_next = True
        elif b.kind == 'paragraph' and nxt is not None and nxt.kind in _CONTENT_KINDS + ('heading',):
            if len(b.text) <= 140:
                b.keep_with_next = True
        if b.kind == 'section':
            _keep_titles_with_content(b.blocks)


def _meta_from_blocks(blocks):
    meta = {}
    pat = {'project': r'Project\s*:\s*(.+)', 'data_date': r'Data\s*Date\s*:\s*(.+)',
           'report_date': r'Report\s*Date\s*:\s*(.+)', 'source_file': r'Schedule\s*File\s*:\s*(.+)',
           'baseline': r'Baseline\s*:\s*(.+)'}
    for b in blocks:
        if b.kind not in ('paragraph', 'heading'):
            continue
        for chunk in re.split(r'\s{2,}·\s{2,}|\n', b.text):
            for k, p in pat.items():
                m = re.match(p, chunk.strip(), re.I)
                if m and k not in meta:
                    meta[k] = m.group(1).strip()
    return meta


def _load(html):
    """Parse HTML with lxml, tolerant of an XML declaration / BOM / fragments."""
    if isinstance(html, bytes):
        html = html.decode('utf-8', 'replace')
    html = (html or '').lstrip('﻿')
    html = re.sub(r'^\s*<\?xml[^>]*>', '', html)
    if not html.strip():
        html = '<html><body></body></html>'
    parser = lxml.html.HTMLParser(encoding='utf-8', remove_comments=True)
    doc = lxml.html.document_fromstring(html.encode('utf-8'), parser=parser)
    return doc


def parse_report(html, sections=None):
    """Parse the final report HTML into a :class:`ReportDoc`.

    ``sections`` — optional ``[{key, label}]`` (the picker's section list) used to title a
    ``[data-sec]`` section that has no heading of its own."""
    doc = _load(html)
    style_texts = [s.text or '' for s in doc.iter('style')]
    sheet = C.StyleSheet(style_texts, page_width_px=720)
    sheet.prune_to(doc)          # F4: only rules this document can match (app CSS is ~300 KB)
    page = C.page_setup(sheet)
    content_w_px = (page['width_mm'] - page['margins_mm'][1] - page['margins_mm'][3]) * 96 / 25.4
    sheet.page_width_px = content_w_px
    resolver = C.Resolver(sheet)
    body = doc.find('body')
    if body is None:
        body = doc
    html_el = doc if C.tag_of(doc) == 'html' else doc.getroottree().getroot()
    hst = resolver.style(html_el)
    bst = resolver.style(body)
    page_bg = bst.background() or hst.background() or (255, 255, 255, 1.0)
    page_bg_rgb = C.blend(page_bg, (255, 255, 255))
    walker = _Walker(resolver, page_bg_rgb, content_w_px)
    blocks = walker.convert(body)
    C.clear_sibling_cache()      # release the per-parent sibling index (holds tree refs)
    # theme tokens (from :root custom properties)
    theme = {k[2:]: v for k, v in hst.get('_custom', {}).items() if k.startswith('--rpt-')}
    labels = {s.get('key'): s.get('label') for s in (sections or []) if isinstance(s, dict)}
    front, secs, tail = [], [], []
    for b in blocks:
        if b.kind == 'section':
            if not b.title:
                first_h = next((x for x in b.blocks if x.kind == 'heading'), None)
                b.title = (first_h.text if first_h else '') or labels.get(b.key) or b.key
            secs.append(b)
        elif secs:
            tail.append(b)
        else:
            front.append(b)
    # blocks that sit BETWEEN two sections belong to the preceding section
    if secs and tail:
        pass
    rep = ReportDoc(page=page, theme=theme, bg=C.to_hex(page_bg + (1.0,) if len(page_bg) == 3 else page_bg),
                    ink=C.to_hex(bst.color(), page_bg_rgb),
                    font_family=_first_family(bst.get('font-family')) or 'Segoe UI',
                    base_pt=_pt(bst.font_px()) or 8.25, front=front, sections=secs, tail=tail,
                    head_css='\n'.join(style_texts), html_class=html_el.get('class') or '',
                    body_class=body.get('class') or '')
    _reattach_between(rep, blocks)
    rep.part_labels = dict(walker.part_labels)
    t = doc.find('.//title')
    rep.title = _norm_ws(t.text_content()).strip() if t is not None else ''
    if not rep.title:
        h = next((b for b in rep.all_blocks() if b.kind == 'heading'), None)
        rep.title = h.text if h else ''
    rep.meta = _meta_from_blocks(rep.front[:12])
    _keep_titles_with_content(rep.front)
    for s in rep.sections:
        _keep_titles_with_content(s.blocks)
    _keep_titles_with_content(rep.tail)
    return rep


def _reattach_between(rep, blocks):
    """Content between two sections joins the section before it; only what follows the
    LAST section is the document tail (report footer)."""
    if len(rep.sections) < 2:
        return
    tail, cur = [], None
    for b in blocks:
        if b.kind == 'section':
            if tail and cur is not None:
                cur.blocks.extend(tail)
            tail = []
            cur = b
        elif cur is not None:
            tail.append(b)
    rep.tail = tail
