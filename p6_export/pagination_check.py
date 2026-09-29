"""Automatic page checker (owner point 14) — finds page-composition defects in a FINISHED
report, PDF or Word, so every feature team can prove its report is laid out properly.

    python -m p6_export.pagination_check report.pdf
    python -m p6_export.pagination_check report.docx [--engine auto|word|spire]
    python -m p6_export.pagination_check report.pdf --html report.html   (heading hints)

prints ONE JSON object: ``{file, format, engine, status, pages, flag_count, counts, flags,
info, message}``; each flag is ``{type, page, detail}`` (``page`` is 1-based, the page the
defect is on — for a break, the page BEFORE it). Exit code: 0 clean · 1 flags found ·
2 error · 3 skipped (no renderer for a Word file on this machine).

Defects (``flags``):

  orphaned_heading              a heading is the last thing on a page; its content starts
                                on the next page
  kpi_separated_from_heading    a heading ends a page and its KPI / summary cards start the
                                next page
  heading_separated_from_block  a heading (+ a short intro) ends a page and its table /
                                chart / picture / cards start the next page
  picture_separated_from_caption (Word) a picture starts a page, its label / caption is on
                                the page before
  table_split_few_rows          a table breaks across pages leaving only 1-2 body rows on
                                one side (the rules keep >= 3)
  small_table_split             a table small enough to be kept whole (<= FIT of a page) is
                                split across two pages
  table_header_not_repeated     a table continues on the next page without its header row
  graphic_cut                   a chart / diagram / picture is cut by the page break (part
                                on each page, or clipped by the sheet edge)
  text_cut                      text runs off the sheet (content overflowed the page)
  content_in_margin             a page's content starts inside the top margin (the page lost
                                its margin / running header — an overflow page)
  large_blank_then_continuation a page ends more than 35 % blank and the next page goes on
                                with a pushed block (not a new section)
  stranded_fragment             a page holds only a small tail of a chart / cards block
  empty_page                    a page with nothing on it besides the running header/footer

Informational (``info``, never counted): ``section_break_blank`` — a page ends early because
the next page starts a new top-level section (a page break by design).

How a PDF is read (PyMuPDF): text lines with their font size / bold, vector drawings and
pictures per page. The running header / footer / page frame (the same thing at the same
place on most pages) and page numbers are set aside. Headings are found WITHOUT the source:
a short line alone on its row that is bold (or clearly larger than the body text) — the
same "heading-like" definition the print-time composer uses; the renderers' heading texts
can be passed as hints (``--html`` / ``headings=``). Tables are found as runs of rows of
side-by-side cells sharing column edges (PyMuPDF's table finder mistakes page frames for
tables); a table that continues across a break is matched by its column edges.

How a Word file is read: Word's OWN pagination through COM (Word installed + pywin32):
the document is opened read-only, repaginated, and the page + vertical position of every
paragraph, table row and picture is read — no PDF export (that hangs when Word runs
headless). Fallback: Spire.Doc renders the file to PDF (its free edition converts only the
first 10 pages) and the PDF rules run on that, with the document's heading texts as hints.
When neither is available the check is skipped with a clear message (status "skipped").

Thresholds are the SAME numbers the pagination rules use (report_theme.PAGINATION_*).
"""
import argparse
import collections
import html as _html
import json
import os
import re
import subprocess
import sys
import tempfile

try:                                   # the same thresholds as the rules the renderers follow
    import report_theme as _rt
    FIT = float(getattr(_rt, 'PAGINATION_FIT', 0.35))
    MIN_ROWS = int(getattr(_rt, 'PAGINATION_MIN_ROWS', 3))
    HEAD_MAX_CHARS = int(getattr(_rt, 'PAGINATION_HEAD_MAX_CHARS', 160))
except Exception:                      # pragma: no cover — report_theme always ships
    _rt = None
    FIT, MIN_ROWS, HEAD_MAX_CHARS = 0.35, 3, 160

BLANK = 0.35              # a page ending more than 35 % blank before a pushed block is a defect
FRAGMENT = 0.12           # a page holding < 12 % of content (a figure / cards tail) is stranded
INTRO_MAX_PT = 60.0       # a heading's short intro (about 3-4 lines)
TOP_ZONE_PT = 26.0        # "what the page starts with" looks this far below the first item
DEFECT_TYPES = (
    'orphaned_heading', 'kpi_separated_from_heading', 'heading_separated_from_block',
    'picture_separated_from_caption', 'table_split_few_rows', 'small_table_split',
    'table_header_not_repeated', 'graphic_cut', 'text_cut', 'content_in_margin',
    'large_blank_then_continuation',
    'stranded_fragment', 'empty_page',
)
INFO_TYPES = ('section_break_blank',)

EXIT_CLEAN, EXIT_FLAGS, EXIT_ERROR, EXIT_SKIPPED = 0, 1, 2, 3


def norm(s):
    """Lower-case words only — for matching heading texts across renderers."""
    s = _html.unescape(s or '').replace('\xa0', ' ')
    return re.sub(r'[^0-9a-z]+', ' ', s.lower()).strip()


def _result(path, fmt, engine, pages, flags, info=(), status='ok', message=''):
    flags = sorted(flags, key=lambda f: (f['page'], f['type']))
    counts = collections.Counter(f['type'] for f in flags)
    return {'file': path, 'format': fmt, 'engine': engine, 'status': status,
            'pages': pages, 'flag_count': len(flags), 'counts': dict(sorted(counts.items())),
            'flags': flags, 'info': sorted(info, key=lambda f: f['page']), 'message': message}


def _flag(kind, page, detail):
    return {'type': kind, 'page': int(page), 'detail': detail}


# ══ PDF ══════════════════════════════════════════════════════════════════════════
class _Line:
    __slots__ = ('t', 'n', 'x0', 'y0', 'x1', 'y1', 'bold', 'size')

    def __init__(self, t, x0, y0, x1, y1, bold, size):
        self.t, self.n = t, norm(t)
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.bold, self.size = bold, size


class _Band:
    """One row of text: the lines that sit side by side at the same height."""
    __slots__ = ('lines', 'x0', 'y0', 'x1', 'y1', 'heading', 'size')

    def __init__(self, lines):
        self.lines = sorted(lines, key=lambda l: l.x0)
        self.x0 = min(l.x0 for l in lines)
        self.x1 = max(l.x1 for l in lines)
        self.y0 = min(l.y0 for l in lines)
        self.y1 = max(l.y1 for l in lines)
        self.size = max(l.size for l in lines)
        self.heading = False

    @property
    def text(self):
        return ' '.join(l.t for l in self.lines)

    @property
    def grid(self):          # side-by-side cells (a table row / a row of cards)
        return len(self.lines) >= 2 and any(b.x0 - a.x1 > 3 for a, b in zip(self.lines, self.lines[1:]))

    @property
    def bold(self):
        return all(l.bold for l in self.lines)


class _Draw:
    __slots__ = ('x0', 'y0', 'x1', 'y1', 'ry0', 'ry1', 'w', 'h', 'curve', 'fill', 'thin', 'img')

    def __init__(self, x0, y0, x1, y1, ry0, ry1, curve=False, fill=None, img=False):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.ry0, self.ry1 = ry0, ry1
        self.w, self.h = x1 - x0, y1 - y0
        self.curve, self.fill, self.img = curve, fill, img
        self.thin = self.w < 2.5 or self.h < 2.5


class _Page:
    def __init__(self, no, W, H):
        self.no, self.W, self.H = no, W, H
        self.lines, self.draws, self.misc = [], [], []   # misc: rotated / tiny text extents
        self.bands, self.regions = [], []

    def items(self):
        return ([(b.y0, b.y1) for b in self.bands] + [(d.y0, d.y1) for d in self.draws]
                + list(self.misc))

    @property
    def empty(self):
        return not self.items()

    @property
    def top(self):
        return min(y0 for y0, _ in self.items())

    @property
    def bottom(self):
        return max(y1 for _, y1 in self.items())


def _is_bold(span):
    f = span.get('font') or ''
    return bool(span.get('flags', 0) & 16) or any(k in f for k in ('Bold', 'bold', 'Semibold', 'Black', 'Heavy'))


def _read_pdf(path):
    import pymupdf
    pages = []
    with pymupdf.open(path) as doc:
        for i, pg in enumerate(doc):
            W, H = pg.rect.width, pg.rect.height
            P = _Page(i + 1, W, H)
            for b in pg.get_text('dict')['blocks']:
                for ln in b.get('lines', []):
                    spans = [s for s in ln['spans'] if s['text'].strip()]
                    if not spans:
                        continue
                    x0, y0, x1, y1 = ln['bbox']
                    if y1 <= 0 or y0 >= H + 400:
                        continue
                    t = ' '.join(''.join(s['text'] for s in ln['spans']).split())
                    size = max(s['size'] for s in spans)
                    if size < 3 or t.startswith("Evaluation Warning"):
                        continue                  # invisible markers (a 1px section marker) / a renderer watermark
                    d = ln.get('dir', (1, 0))
                    if abs(d[0] - 1) > 0.01:
                        P.misc.append((max(y0, 0), min(y1, H)))   # rotated text (an axis label)
                        continue
                    P.lines.append(_Line(t, x0, y0, x1, y1, all(_is_bold(s) for s in spans), size))
            for d in pg.get_drawings():
                r = d['rect']
                if r.y1 <= 0.5 or r.y0 >= H - 0.5 or r.x1 <= 0 or r.x0 >= W:
                    continue                      # off-page paths (Chrome emits thousands)
                w, h = r.width, r.height
                fill, stroke = d.get('fill'), d.get('color')
                if w > 0.8 * W and h > 0.4 * H and (fill is None or (w > 0.95 * W and h > 0.9 * H)):
                    continue                      # page frame box / page background
                if (w < 2.5 and h > 0.25 * H) or (h < 2.5 and w > 0.85 * W):
                    continue                      # page frame lines
                if fill is not None and min(fill) > 0.985 and not stroke:
                    continue                      # white fills
                if fill is None and not stroke:
                    continue
                items = d.get('items') or []
                P.draws.append(_Draw(max(r.x0, 0), max(r.y0, 0), min(r.x1, W), min(r.y1, H), r.y0, r.y1,
                                     curve=any(it[0] == 'c' for it in items), fill=fill))
            for im in pg.get_image_info():
                x0, y0, x1, y1 = im['bbox']
                if y1 <= 0 or y0 >= H or x1 - x0 < 2 or y1 - y0 < 2:
                    continue
                P.draws.append(_Draw(max(x0, 0), max(y0, 0), min(x1, W), min(y1, H), y0, y1, img=True))
            pages.append(P)
    return pages


def _bands_of(lines):
    lines = sorted(lines, key=lambda l: (l.y0, l.x0))
    bands, cur = [], []
    for l in lines:
        if cur and (abs(l.y0 - cur[0].y0) <= 2.5 and l.y0 < max(c.y1 for c in cur)):
            cur.append(l)
        else:
            if cur:
                bands.append(_Band(cur))
            cur = [l]
    if cur:
        bands.append(_Band(cur))
    return bands


def _strip_running(pages):
    """Set aside the running header / footer / frame and page numbers: the same row of text
    (or the same drawing) at the same place on many pages. A table's REPEATED header row is
    kept — it also sits elsewhere on a page (where the table starts), right above table rows."""
    n = len(pages)
    pnum = re.compile(r'^(page )?\d+( (of|/) \d+)?$')
    # page numbers change from page to page (digits masked); a row of 3+ cells must match
    # exactly — table rows of the same shape at the same place are content, not a header
    sig = lambda b: re.sub(r'\d+', '#', norm(b.text)) if len(b.lines) <= 2 else norm(b.text)
    per_page = [_row_clusters(_bands_of(P.lines)) for P in pages]
    occ = collections.defaultdict(list)
    for bands in per_page:
        seen = set()
        for j, b in enumerate(bands):
            k = (round(b.y0 / 3), sig(b))
            if k not in seen:
                seen.add(k)
                occ[k].append((b, bands[j + 1] if j + 1 < len(bands) else None))
    need = max(3, 0.3 * n)

    def table_header(k):
        # a table's header row repeated on every page of the table: 3+ cells, and wherever
        # it sits, table rows with the same columns follow right under it
        return all(len(b.lines) >= 3 and nx is not None and nx.grid and nx.y0 - b.y1 <= 30
                   and _col_match(b.lines, nx.lines) >= 3 for b, nx in occ[k])

    H = pages[0].H if pages else 842.0

    def running(b):
        k = (round(b.y0 / 3), sig(b))
        if b.y1 < 0.1 * H or b.y0 > 0.9 * H:      # the header / footer band of the sheet:
            return n >= 2 and len(occ[k]) >= min(n, need)   # on every page of a short report
        return n >= 3 and len(occ[k]) >= need and not table_header(k)
    dkey = lambda d: (round(d.ry0 / 3), round(d.x0 / 3), round(d.w / 3), round((d.ry1 - d.ry0) / 3))
    dcnt = collections.Counter()
    for P in pages:
        dcnt.update({dkey(d) for d in P.draws if not d.img})
    drun = {k for k, c in dcnt.items() if n >= 3 and c >= need}
    for P, bands in zip(pages, per_page):
        edge = 0.07 * P.H
        keep = []
        for b in bands:
            if running(b):
                continue
            keep.extend(l for l in b.lines
                        if not (pnum.match(l.n or '#') and (l.y1 < edge or l.y0 > P.H - edge)))
        P.lines = keep
        P.draws = [d for d in P.draws if d.img or dkey(d) not in drun]


def _make_bands(P):
    P.bands = _bands_of(P.lines)


def _body_size(pages):
    c = collections.Counter()
    for P in pages:
        for l in P.lines:
            c[round(l.size * 2) / 2] += len(l.t)
    return c.most_common(1)[0][0] if c else 10.0


def _mark_headings(pages, body, hints):
    for P in pages:
        for b in P.bands:
            txt = b.text
            n = norm(txt)
            if len(n) < 3 or len(txt) > HEAD_MAX_CHARS or not re.search(r'[a-z]', n):
                continue
            alnum = re.sub(r'[^0-9a-z]', '', n)
            if sum(ch.isdigit() for ch in alnum) > 0.4 * len(alnum):
                continue                      # a value ("247 WD", "4.2%"), not a title
            if len(b.lines) > 2 or (len(b.lines) == 2 and b.lines[1].x0 - b.lines[0].x1 > 30):
                continue                      # cells side by side, not a title
            styled = all((l.bold and l.size >= 0.8 * body) or l.size >= 1.25 * body for l in b.lines)
            hinted = bool(hints) and any(
                n == h or (len(n) >= 8 and (h.startswith(n) or n.startswith(h[:max(12, len(h) // 2)])))
                for h in hints)
            b.heading = styled or hinted


def _col_match(a_lines, b_lines):
    hits = 0
    for l in b_lines:
        if any(abs(l.x0 - m.x0) < 4 or abs(l.x1 - m.x1) < 4 for m in a_lines):
            hits += 1
    return hits


class _Region:
    """A table (or a grid of cells): consecutive rows of side-by-side cells."""

    def __init__(self, band):
        self.rows = [band]
        self.members = [band]
        self.y0, self.y1 = band.y0, band.y1
        self.col0 = band.x0

    def add(self, band, row):
        self.members.append(band)
        if row:
            self.rows.append(band)
        self.y1 = max(self.y1, band.y1)
        self.col0 = min(self.col0, band.x0)

    def pop_row(self):
        band = self.rows.pop()
        self.members = [m for m in self.members if m is not band]
        self.y1 = max(m.y1 for m in self.members)
        return band

    @property
    def lines(self):
        return [l for b in self.rows for l in b.lines]

    def header_rows(self, strict=False):
        """Leading bold rows = the header. ``strict``: only when no later row is bold (bold
        group / total / label rows make a bold first row ambiguous)."""
        k = 0
        while k < len(self.rows) and k < 3 and self.rows[k].bold:
            k += 1
        if k == len(self.rows) and len(self.rows) > 1:
            return 0                     # every row bold: no separate header row
        if strict and (any(r.bold for r in self.rows[k:])
                       or not all(re.search('[a-z]', _sig(r)) for r in self.rows[:k])):
            return 0
        return k


def _sig(band):
    """A row's structure (digits ignored) — a repeated header row has the same signature."""
    return re.sub(r'[0-9]+', '#', norm(band.text))


def _continues_row(reg, b):
    """A second line of the previous row (wrapped cells) rather than a new row."""
    prev = reg.rows[-1]
    return (b.y0 - prev.y0 < 1.5 * max(b.size, 1) and len(b.lines) < len(prev.lines)
            and not any(abs(l.x0 - reg.col0) < 4 for l in b.lines))


def _row_clusters(bands):
    """Bands that overlap vertically are ONE table row (cells aligned top / middle / bottom,
    wrapped cells, a two-line header cell)."""
    out = []
    for b in bands:
        if out and not b.heading and not out[-1].heading and b.y0 < out[-1].y1 - 1.0:
            out[-1] = _Band(out[-1].lines + b.lines)
        else:
            out.append(b)
    return out


def _make_regions(P):
    regs, cur, pend = [], None, []

    def close_trailing():
        for m in pend:
            if m.y0 - cur.y1 <= 14 and cur.col0 - 4 <= m.x0 and not m.heading:
                cur.add(m, False)       # the last row's wrapped cell lines
            else:
                break
    for b in _row_clusters(P.bands):
        if b.grid and not b.heading:
            last_y = max(cur.y1, pend[-1].y1) if (cur is not None and pend) else (cur.y1 if cur else 0)
            if cur is not None and b.y0 - last_y <= 24 and _col_match(cur.lines, b.lines) >= 2:
                if b.bold and len(cur.rows) > 1 and re.search('[a-z]', _sig(b))                         and any(_sig(r) == _sig(b) for r in cur.rows):
                    # the same header row again: a new table starts here, with the bold title
                    # row(s) sitting right on top of it
                    lead = []
                    while len(cur.rows) > 1 and cur.rows[-1].bold and b.y0 - cur.rows[-1].y1 <= 8 and not pend:
                        lead.insert(0, cur.pop_row())
                    new = _Region(lead[0] if lead else b)
                    for r in lead[1:] + ([b] if lead else []):
                        new.add(r, True)
                    cur = new
                    regs.append(cur)
                else:
                    for m in pend:
                        cur.add(m, False)
                    cur.add(b, not _continues_row(cur, b))
            else:
                if cur is not None:
                    close_trailing()
                cur = _Region(b)
                regs.append(cur)
            pend = []
        elif (cur is not None and len(pend) < 12
              and b.y0 - (pend[-1].y1 if pend else cur.y1) <= (6 if b.heading else 14)):
            pend.append(b)               # a wrapped cell line / a group row inside the table
        else:
            if cur is not None:
                close_trailing()
            cur, pend = None, []
    if cur is not None:
        close_trailing()
    P.regions = regs


def _tiles(P, y_top, y_lim):
    """Boxes of a KPI / summary card row starting in [y_top, y_lim]: two or more boxes of about
    the same height side by side with a gap between them, each holding text."""
    boxes = [(d.x0, d.y0, d.x1, d.y1) for d in P.draws
             if not d.thin and not d.img and 18 <= d.h <= 170 and 28 <= d.w <= 0.62 * P.W
             and y_top - 2 <= d.y0 <= y_lim]
    # boxes drawn as four thin borders: pair the vertical sides sharing a span
    vs = collections.defaultdict(list)
    for d in P.draws:
        if d.w < 2.5 and 18 <= d.h <= 170 and y_top - 2 <= d.y0 <= y_lim:
            vs[(round(d.y0), round(d.y1))].append((d.x0 + d.x1) / 2)
    for (a, b), xs in vs.items():
        xs = sorted(set(round(x, 1) for x in xs))
        for x0, x1 in zip(xs, xs[1:]):
            if 28 <= x1 - x0 <= 0.62 * P.W:
                boxes.append((x0, a, x1, b))
    boxes = [bx for bx in boxes if any(bx[0] - 1 <= l.x0 and l.x1 <= bx[2] + 1 and bx[1] - 1 <= l.y0
                                        and l.y1 <= bx[3] + 1 for l in P.lines)]
    rows = []
    for bx in sorted(boxes, key=lambda b: (b[1], b[0])):
        for row in rows:
            a = row[0]
            if abs(bx[1] - a[1]) <= 3 and abs((bx[3] - bx[1]) - (a[3] - a[1])) <= 0.25 * (a[3] - a[1]):
                if not any(abs(bx[0] - c[0]) < 3 and abs(bx[2] - c[2]) < 3 for c in row):
                    row.append(bx)       # (a filled box and its border pair are the same tile)
                break
        else:
            rows.append([bx])
    for row in rows:
        row.sort(key=lambda b: b[0])
        gaps = [b[0] - a[2] for a, b in zip(row, row[1:])]
        # cards stand apart; table cells touch (a row with touching boxes is a table row)
        if len(row) >= 2 and all(g >= 2 for g in gaps):
            return row
    return None


def _section_size(pages, body, firsts):
    """The smallest heading size that marks a TOP-LEVEL section: clearly larger than the body
    text and starting a page at least half of the times it occurs (sections that start on a
    new page by design). A page-top heading at least this big is a section break."""
    seen = collections.defaultdict(lambda: [0, 0])
    for P in pages[1:]:
        for b in P.bands:
            if b.heading:
                seen[round(b.size * 2) / 2][0] += 1
    for P, (kind, _, size) in zip(pages[1:], firsts[1:]):
        if kind == 'heading':
            seen[round(size * 2) / 2][1] += 1
    cands = [k for k, (n, t) in seen.items() if k >= 1.2 * body and t >= max(1, 0.5 * n)]
    return min(cands) if cands else float('inf')


def _first_block(P):
    """What page P starts with: ('heading'|'kpi'|'table'|'figure'|'text'|'empty', text, size)."""
    if P.empty:
        return 'empty', '', 0
    top = P.top
    fb = P.bands[0] if P.bands else None
    figs_above = [d for d in P.draws if not d.thin and (fb is None or d.y1 <= fb.y0 + 0.5)
                  and not (fb is not None and d.x0 <= fb.x0 and d.x1 >= fb.x1 and d.y1 >= fb.y1)]
    if fb is not None and fb.heading and fb.y0 <= top + TOP_ZONE_PT and not figs_above:
        return 'heading', fb.text, fb.size
    if _tiles(P, top, top + TOP_ZONE_PT):
        return 'kpi', '', 0
    if fb is not None and fb.grid and fb.y0 <= top + TOP_ZONE_PT and not figs_above:
        return 'table', fb.text, fb.size
    zone = [d for d in P.draws if d.y0 <= top + TOP_ZONE_PT and not d.thin]
    textfree = [d for d in zone if not any(d.x0 - 1 <= l.x0 and l.x1 <= d.x1 + 1 and d.y0 - 1 <= l.y0
                                           and l.y1 <= d.y1 + 1 for l in P.lines)]
    if any(d.img or d.curve for d in zone) or len(textfree) >= 2:
        return 'figure', '', 0
    if fb is not None and fb.grid:
        return 'table', fb.text, fb.size
    return 'text', (fb.text if fb is not None else ''), (fb.size if fb is not None else 0)


def _below(P, y, head=None):
    """Content items on P starting below y (ignoring a heading's own underline / bar)."""
    out = []
    for b in P.bands:
        if b.y0 >= y - 0.5:
            out.append((b.y0, b.y1, 'text', b))
    for d in P.draws:
        if d.y0 < y - 0.5:
            continue
        if head is not None and d.thin and d.y0 <= y + 8 and d.h < 3:
            continue                      # the heading's underline
        out.append((d.y0, d.y1, 'figure' if (d.img or d.curve or not d.thin) else 'rule', d))
    for y0, y1 in P.misc:
        if y0 >= y - 0.5:
            out.append((y0, y1, 'figure', None))
    return out


def _table_split(A, B, a_reg, b_reg, area, flags):
    """Compare the table fragment ending page A with the one starting page B."""
    ha = a_reg.header_rows()
    body_a = len(a_reg.rows) - ha
    hb = 0
    sigs = [_sig(r) for r in a_reg.rows[:ha]]
    while hb < len(b_reg.rows) and hb < 3 and b_reg.rows[hb].bold and _sig(b_reg.rows[hb]) in sigs:
        hb += 1
    if hb == len(b_reg.rows) and hb > 1:
        hb = 0
    body_b = len(b_reg.rows) - hb
    height = (a_reg.y1 - a_reg.y0) + (b_reg.y1 - b_reg.y0)
    what = f'table {a_reg.rows[0].text[:40]!r}'
    if min(body_a, body_b) < MIN_ROWS:
        flags.append(_flag('table_split_few_rows', A.no,
                           f'{what} breaks p{A.no}->p{B.no} with {body_a} body row(s) on p{A.no} '
                           f'and {body_b} on p{B.no} (the rules keep >= {MIN_ROWS})'))
    elif height <= FIT * area:
        flags.append(_flag('small_table_split', A.no,
                           f'{what} ({body_a}+{body_b} rows, {height:.0f}pt = {height / area:.0%} of a page) '
                           f'fits on one page but is split p{A.no}->p{B.no}'))
    if a_reg.header_rows(strict=True) and not hb and body_b > 0:
        flags.append(_flag('table_header_not_repeated', B.no,
                           f'{what} continues on p{B.no} without its header row '
                           f'{a_reg.rows[0].text[:40]!r}'))


def _figure_cut(A, B, area_top, area_bottom):
    """A chart / diagram cut at the break between page A and page B (Chrome clips each part to
    its page: the part on A ends exactly on A's clip line, the part on B starts on B's)."""
    fa = [d for d in A.draws if not d.thin]
    fb = [d for d in B.draws if not d.thin]
    if not fa or not fb:
        return None
    clip_a = max(d.y1 for d in A.draws)
    clip_b = min(d.y0 for d in B.draws)
    if clip_a < area_bottom - 0.6 or clip_b > area_top + 0.6:
        return None                       # ends above the page-area bottom: nothing was cut
    if A.bands and max(b.y1 for b in A.bands) > clip_a + 0.5:
        return None                       # text below the graphic: it ended on this page
    if B.bands and min(b.y0 for b in B.bands) < clip_b - 0.5:
        return None                       # text above the graphic: it starts fresh
    wide = 0.85 * max(A.W, 1)
    ea = [d for d in fa if abs(d.y1 - clip_a) < 0.35 and d.w < wide]
    eb = [d for d in fb if abs(d.y0 - clip_b) < 0.35 and d.w < wide]
    if not ea or not eb:
        return None

    def overlap(a, b):
        return min(a.x1, b.x1) - max(a.x0, b.x0) > 0.5 * min(a.w, b.w)
    if not any(overlap(a, b) for a in ea for b in eb):
        return None
    # a table row / text box that breaks has text right at the break — a graphic does not
    near_a = [b for b in A.bands if b.y1 > clip_a - 4 and any(b.x0 < d.x1 and b.x1 > d.x0 for d in ea)]
    near_b = [b for b in B.bands if b.y0 < clip_b + 4 and any(b.x0 < d.x1 and b.x1 > d.x0 for d in eb)]
    if near_a or near_b:
        return None
    return len(ea), len(eb)


def _analyze_pages(pages, hints=()):
    n = len(pages)
    _strip_running(pages)
    for P in pages:
        _make_bands(P)
    body = _body_size(pages)
    _mark_headings(pages, body, [norm(h) for h in hints if norm(h)])
    for P in pages:
        _make_regions(P)
    full = [P for P in pages if not P.empty]
    if not full:
        return [], [], (0, 0)
    tops = sorted(P.top for P in full)
    bots = sorted(min(P.bottom, P.H) for P in full)
    T = tops[len(tops) // 2]
    B = bots[min(len(bots) - 1, round((len(bots) - 1) * 0.9))]
    area = max(B - T, 1.0)
    # the page-area edges: nothing on a normal page reaches past them (spilled pages aside)
    area_bottom = max((P.bottom for P in full if P.bottom <= P.H - 8), default=B)
    area_top = min((P.top for P in full if P.top >= 8), default=T)
    firsts = [_first_block(P) for P in pages]
    section_size = _section_size(pages, body, firsts)
    flags, info = [], []

    for i, P in enumerate(pages):
        nxt = pages[i + 1] if i + 1 < n else None
        kind_n, text_n, size_n = firsts[i + 1] if nxt is not None else ('none', '', 0)
        if P.empty:
            if n > 1:
                flags.append(_flag('empty_page', P.no, 'the page has nothing on it besides the running '
                                                       'header / footer / frame'))
            continue
        # content running off the sheet
        cut_t = [l for l in P.lines if l.y1 > P.H - 0.5 or l.y0 < 0.5]
        if cut_t:
            flags.append(_flag('text_cut', P.no, 'text runs off the sheet: '
                               + '; '.join(repr(l.t[:50]) for l in cut_t[:3])))
        elif P.no > 1 and T - 24 > 8:
            high = [l for l in P.lines if l.y0 < T - 24]
            if high:
                flags.append(_flag('content_in_margin', P.no,
                                   f'content starts at {min(l.y0 for l in high):.0f}pt, inside the top '
                                   f'margin (the body starts at {T:.0f}pt on the other pages) - the page '
                                   f'lost its margin / running header: ' + repr(high[0].t[:50])))
        edge = [d for d in P.draws if (d.ry1 > P.H + 0.5 and d.y0 < P.H - 2) or (d.ry0 < -0.5 and d.y1 > 2)]
        edge = [d for d in edge if d.img or (not d.thin and d.w < 0.85 * P.W and (d.ry1 - d.ry0) < 0.5 * P.H)]
        if edge:
            flags.append(_flag('graphic_cut', P.no, f'{len(edge)} picture / drawing part(s) are clipped by '
                                                   f'the edge of the sheet'))
        if nxt is None or nxt.empty:
            continue
        # headings that end the page
        hs = [b for b in P.bands if b.heading]
        if hs:
            h = max(hs, key=lambda b: b.y0)
            below = [it for it in _below(P, h.y1, head=h) if it[2] != 'rule']
            ext = (max(y1 for _, y1, _, _ in below) - h.y1) if below else 0.0
            closing = kind_n == 'heading' and size_n >= h.size - 0.3
            if (not below or ext < 3) and not closing:
                kind = 'kpi_separated_from_heading' if kind_n == 'kpi' else 'orphaned_heading'
                flags.append(_flag(kind, P.no, f'heading {h.text[:60]!r} is the last thing on page {P.no}; '
                                               f'its {kind_n} starts page {nxt.no}'))
            elif (ext <= INTRO_MAX_PT and all(k == 'text' and not it.grid and not it.heading
                                              for _, _, k, it in below)
                  and kind_n in ('table', 'figure', 'kpi')):
                kind = 'kpi_separated_from_heading' if kind_n == 'kpi' else 'heading_separated_from_block'
                flags.append(_flag(kind, P.no, f'heading {h.text[:60]!r} + {ext:.0f}pt of intro end page '
                                               f'{P.no}; its {kind_n} starts page {nxt.no}'))
        # a table that continues across the break
        if P.regions and nxt.regions and kind_n == 'table':
            a_reg, b_reg = P.regions[-1], nxt.regions[0]
            tail = [it for it in _below(P, a_reg.y1 + 1) if it[2] != 'rule']
            if (not tail and abs(b_reg.y0 - nxt.bands[0].y0) < 0.5
                    and _col_match(a_reg.lines, b_reg.rows[0].lines) >= 2):
                _table_split(P, nxt, a_reg, b_reg, area, flags)
        # a chart / diagram cut by the break
        cut = _figure_cut(P, nxt, area_top, area_bottom)
        if cut:
            flags.append(_flag('graphic_cut', P.no, f'a chart / diagram is cut by the page break '
                                                   f'p{P.no}->p{nxt.no} ({cut[0]} part(s) end on the '
                                                   f'break, {cut[1]} continue at the top of p{nxt.no})'))
        # a large blank area before the next page
        fill = (min(P.bottom, P.H) - T) / area
        if fill < 1 - BLANK:
            what = f'page {P.no} ends at {max(fill, 0):.0%} of the page ({1 - max(fill, 0):.0%} blank); ' \
                   f'page {nxt.no} starts with {kind_n}' + (f' {text_n[:40]!r}' if text_n else '')
            if kind_n == 'heading' and size_n >= section_size - 0.3:
                info.append(_flag('section_break_blank', P.no, what + ' (a new section)'))
            else:
                flags.append(_flag('large_blank_then_continuation', P.no, what))
        # a small tail of cards / a figure alone on a (middle) page
        if i > 0:
            k0 = firsts[i][0]
            if k0 in ('figure', 'kpi') and (min(P.bottom, P.H) - P.top) < FRAGMENT * area:
                flags.append(_flag('stranded_fragment', P.no,
                                   f'only {min(P.bottom, P.H) - P.top:.0f}pt of a {k0} block '
                                   f'({(min(P.bottom, P.H) - P.top) / area:.0%} of the page) sits on page {P.no}'))
    return flags, info, (T, B)


def check_pdf(path, headings=None):
    """Check a PDF. ``headings``: optional heading texts (hints) — e.g. from the source HTML."""
    try:
        pages = _read_pdf(path)
    except ImportError:
        return _result(path, 'pdf', 'pymupdf', 0, [], status='skipped',
                       message='PyMuPDF (pymupdf) is not installed - the PDF cannot be read.')
    flags, info, (T, B) = _analyze_pages(pages, headings or ())
    res = _result(path, 'pdf', 'pymupdf', len(pages), flags, info)
    res['body_area_pt'] = [round(T, 1), round(B, 1)]
    return res


# ── heading hints from a source HTML ─────────────────────────────────────────────
def html_headings(html):
    """Heading texts of a report HTML: h1-h6 + the renderers' heading classes."""
    from html.parser import HTMLParser
    classes = set()
    for s in (getattr(_rt, 'HEADING_SELECTORS', ()) if _rt else ()):
        m = re.fullmatch(r'(?:[a-z0-9]+)?\.([\w-]+)', s)
        if m:
            classes.add(m.group(1))

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack, self.out = [], []

        def handle_starttag(self, tag, attrs):
            if tag in ('br', 'img', 'hr', 'meta', 'link', 'input', 'col', 'wbr', 'source'):
                return
            cls = set((dict(attrs).get('class') or '').split())
            self.stack.append([tag, tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6') or bool(cls & classes), []])

        def handle_endtag(self, tag):
            while self.stack:
                t, is_h, buf = self.stack.pop()
                if is_h:
                    txt = ' '.join(''.join(buf).split())
                    if 2 < len(txt) <= HEAD_MAX_CHARS:
                        self.out.append(txt)
                if self.stack:
                    self.stack[-1][2].extend(buf)
                if t == tag:
                    break

        def handle_data(self, data):
            if self.stack:
                self.stack[-1][2].append(data)
    p = P()
    p.feed(html)
    return p.out


# ══ Word ═════════════════════════════════════════════════════════════════════════
def docx_headings(path):
    """Heading texts of a .docx (heading / title styles, outline levels, short bold lines)."""
    try:
        from docx import Document
    except ImportError:
        return []
    out = []
    try:
        d = Document(path)
    except Exception:
        return []
    for p in d.paragraphs:
        t = ' '.join(p.text.split())
        if not t or len(t) > HEAD_MAX_CHARS:
            continue
        st = (p.style.name if p.style is not None else '').lower()
        runs = [r for r in p.runs if r.text.strip()]
        if st.startswith(('heading', 'title', 'subtitle')) or (runs and all(r.bold for r in runs)):
            out.append(t)
    return out


def word_available():
    try:
        import win32com.client  # noqa: F401
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r'Word.Application\CLSID'))
        return True
    except Exception:
        return False


def spire_available():
    try:
        import spire.doc  # noqa: F401
        return True
    except Exception:
        return False


def word_layout(path):
    """Word's own pagination of a .docx / .doc via COM: in body order, paragraphs outside
    tables (page, y, style, outline level, bold, size, keep flags, picture height), and tables
    with the page + y of every row. No PDF export (it hangs when Word runs headless)."""
    import pythoncom
    import win32com.client as wc
    path = os.path.abspath(path)
    pythoncom.CoInitialize()
    word = wc.DispatchEx('Word.Application')
    res = {'file': path}
    try:
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(path, False, True, False)   # ConfirmConversions, ReadOnly, AddToRecent
        try:
            doc.Repaginate()
            ps = doc.PageSetup
            res['page'] = {'h': ps.PageHeight, 'w': ps.PageWidth, 'top': ps.TopMargin,
                           'bottom': ps.BottomMargin}
            items, spans = [], []
            for ti in range(1, doc.Tables.Count + 1):
                tb = doc.Tables(ti)
                r = tb.Range
                spans.append((r.Start, r.End))
                rows = []
                try:
                    for row in tb.Rows:
                        rr = row.Range
                        at = doc.Range(rr.Start, rr.Start)
                        rows.append({'page': at.Information(3), 'y': at.Information(6),
                                     'hdr': bool(row.HeadingFormat), 'n': row.Cells.Count,
                                     'bold': rr.Font.Bold == -1,
                                     't': rr.Text.replace('\r\x07', ' | ').replace('\x07', '').strip()[:60]})
                except Exception:              # merged cells: rows not addressable one by one
                    at = doc.Range(r.Start, r.Start)
                    rows = [{'page': at.Information(3), 'y': at.Information(6), 'hdr': False, 'n': 1,
                             'bold': False, 't': '(table)'}]
                items.append({'k': 'table', 'start': r.Start, 'end': r.End, 'rows': rows,
                              'page': rows[0]['page'], 'page_end': r.Information(3),
                              'y': rows[0]['y'], 't': rows[0]['t'],
                              'ncols': max((x['n'] for x in rows), default=1)})
            spans.sort()
            import bisect
            starts = [s for s, _ in spans]

            def in_table(pos):
                k = bisect.bisect_right(starts, pos) - 1
                return k >= 0 and spans[k][0] <= pos < spans[k][1]
            for p in doc.Paragraphs:
                r = p.Range
                if in_table(r.Start):
                    continue
                raw = r.Text
                txt = raw.strip().replace('\r', ' ').replace('\x07', '').replace('\x0c', '').strip()
                shape_h = 0.0
                try:
                    if r.InlineShapes.Count:
                        shape_h = max(r.InlineShapes(k).Height for k in range(1, r.InlineShapes.Count + 1))
                    elif txt in ('', '/') and r.ShapeRange.Count:     # an anchored (floating) picture
                        shape_h = max(r.ShapeRange(k).Height for k in range(1, r.ShapeRange.Count + 1))
                except Exception:
                    shape_h = 0.0
                brk = '\x0c' in raw
                if not txt and not shape_h and not brk:
                    continue
                if not shape_h and not brk and (r.Font.Hidden == -1 or 0 < (r.Font.Size or 10) <= 2):
                    continue                      # hidden / 1pt marker text is not content
                at = doc.Range(r.Start, r.Start)
                last = doc.Range(max(r.End - 1, r.Start), max(r.End - 1, r.Start))
                try:
                    style = p.Style.NameLocal
                except Exception:
                    style = ''
                items.append({'k': 'pic' if (shape_h and not txt.strip('/ ')) else 'p', 'start': r.Start,
                              'end': r.End, 't': txt[:90], 'page': at.Information(3),
                              'page_end': r.Information(3), 'y': at.Information(6),
                              'y_last': last.Information(6), 'style': style, 'ol': p.OutlineLevel,
                              'bold': r.Font.Bold == -1, 'size': r.Font.Size, 'kwn': bool(p.KeepWithNext),
                              'pbb': bool(p.PageBreakBefore), 'brk': brk, 'ls': p.LineSpacing,
                              'lsr': p.LineSpacingRule, 'sa': p.SpaceAfter, 'shape_h': shape_h,
                              'len': len(txt)})
            items.sort(key=lambda x: x['start'])
            res['items'] = items
            res['pages'] = doc.Content.Information(3)
        finally:
            doc.Close(False)
    finally:
        try:
            word.Quit(False)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return res


def _w_is_heading(it):
    if it['k'] != 'p':
        return False
    t = it.get('t') or ''
    if not t or len(t) > HEAD_MAX_CHARS or not re.search(r'[A-Za-z]', t):
        return False
    st = (it.get('style') or '').lower()
    if st.startswith(('heading', 'title', 'subtitle')) or (it.get('ol') or 10) < 10:
        return True
    return bool(it.get('bold')) and (it.get('len') or len(t)) <= 120


def _w_kind(it):
    if it['k'] == 'table':
        return 'kpi' if (len(it['rows']) <= 2 and (it.get('ncols') or 1) >= 3) else 'table'
    if it['k'] == 'pic':
        return 'picture'
    return 'heading' if _w_is_heading(it) else 'text'


def _w_end_y(it):
    """Where an item ends on its last page (points from the top of the page)."""
    if it['k'] == 'table':
        rows = [r for r in it['rows'] if r['page'] == it['page_end'] and r['y'] is not None and r['y'] >= 0]
        if not rows:
            return None
        ys = sorted(r['y'] for r in rows)
        step = min((b - a for a, b in zip(ys, ys[1:]) if b - a > 1), default=16.0)
        return ys[-1] + step
    if it['k'] == 'pic':
        return (it.get('y_last') or it['y']) + (it.get('shape_h') or 0)
    size = it.get('size') or 10
    if size > 200:                         # wdUndefined (mixed sizes)
        size = 10
    ls, lsr = it.get('ls') or 0, it.get('lsr')
    line = ls if lsr in (3, 4) and ls > size else size * 1.25
    return (it.get('y_last') or it['y']) + line + max(it.get('sa') or 0, 0)


def analyze_word_layout(layout):
    """Pagination defects from Word's own layout (``word_layout()`` output)."""
    pg = layout['page']
    top, bot = pg['top'], pg['h'] - pg['bottom']
    area = max(bot - top, 1.0)
    items = layout['items']
    npages = layout.get('pages') or max((it['page_end'] for it in items), default=0)
    flags, info = [], []

    def section_break_before(j):
        """True when a page break by design sits right before items[j]."""
        it = items[j]
        if it.get('pbb') or (it.get('brk') and not (it.get('t') or '').strip()):
            return True                   # page-break-before, or a paragraph holding only a break
        return j > 0 and bool(items[j - 1].get('brk'))

    for j, it in enumerate(items):
        k = _w_kind(it)
        nxt = items[j + 1] if j + 1 < len(items) else None
        if k == 'heading' and nxt is not None and nxt['page'] > it['page_end'] and not it.get('brk') \
                and not section_break_before(j + 1):
            kn = _w_kind(nxt)
            if not (kn == 'heading' and (nxt.get('size') or 0) >= (it.get('size') or 0)):
                kind = 'kpi_separated_from_heading' if kn == 'kpi' else 'orphaned_heading'
                flags.append(_flag(kind, it['page_end'], f"heading {it['t'][:60]!r} ends page {it['page_end']}; "
                                                         f"its {kn} starts page {nxt['page']}"))
        if k == 'heading' and nxt is not None and nxt['page'] == it['page_end'] and _w_kind(nxt) == 'text':
            n2 = items[j + 2] if j + 2 < len(items) else None
            if (n2 is not None and _w_kind(n2) in ('table', 'picture', 'kpi') and n2['page'] > nxt['page_end']
                    and not section_break_before(j + 2) and (nxt.get('len') or 0) <= 320):
                kn = _w_kind(n2)
                kind = 'kpi_separated_from_heading' if kn == 'kpi' else 'heading_separated_from_block'
                flags.append(_flag(kind, it['page_end'], f"heading {it['t'][:60]!r} + its intro end page "
                                                         f"{it['page_end']}; its {kn} starts page {n2['page']}"))
        if k == 'picture' and j > 0:
            prv = items[j - 1]
            if (prv['page_end'] < it['page'] and _w_kind(prv) == 'text' and len(prv.get('t') or '') <= 160
                    and not section_break_before(j)):
                flags.append(_flag('picture_separated_from_caption', it['page'],
                                   f"picture on page {it['page']} but its label / caption "
                                   f"{prv['t'][:50]!r} is on page {prv['page_end']}"))
        if k == 'picture' and (it.get('shape_h') or 0) > 0:
            end = (it.get('y_last') or it['y']) + it['shape_h']
            if it['shape_h'] > area + 2 or end > pg['h'] - 2:
                flags.append(_flag('graphic_cut', it['page'], f"picture of {it['shape_h']:.0f}pt does not fit "
                                                              f"the page ({area:.0f}pt) - it is clipped"))
        if it['k'] == 'table' and it['page_end'] > it['page'] and (it.get('ncols') or 1) >= 2:
            by = collections.OrderedDict()
            for r in it['rows']:
                if r['y'] is None or r['page'] is None:
                    continue
                by.setdefault(r['page'], []).append(r)
            hdr_rep = any(r['hdr'] for r in it['rows'])
            nh = 0
            while nh < len(it['rows']) and (it['rows'][nh]['hdr'] or (nh == 0 and it['rows'][0].get('bold')
                                                                         and len(it['rows']) > 1
                                                                         and not it['rows'][1].get('bold'))):
                nh += 1
                if not it['rows'][nh - 1]['hdr']:
                    break
            frags = []
            first = True
            for p, rows in by.items():
                body = len([r for r in rows if not r['hdr']]) - (nh if (first and not hdr_rep) else 0)
                ys = [r['y'] for r in rows]
                frags.append((p, max(body, 0), ys))
                first = False
            if len(frags) < 2:
                continue
            steps = [b - a for _, _, ys in frags for a, b in zip(ys, ys[1:]) if b - a > 1]
            step = sorted(steps)[len(steps) // 2] if steps else 16.0
            height = sum((ys[-1] - ys[0]) + step for _, _, ys in frags)
            desc = ', '.join(f'p{p}: {b} body row(s)' for p, b, _ in frags)
            what = f"table {it['t'][:40]!r} ({len(it['rows'])} rows)"
            small = [f for f in frags if f[1] < MIN_ROWS]
            if small:
                flags.append(_flag('table_split_few_rows', small[0][0], f'{what} split {desc} '
                                                                        f'(the rules keep >= {MIN_ROWS})'))
            elif height <= FIT * area:
                flags.append(_flag('small_table_split', frags[0][0], f'{what} of {height:.0f}pt '
                                                                      f'({height / area:.0%} of a page) fits on '
                                                                      f'one page but is split: {desc}'))
            if nh and not hdr_rep:
                flags.append(_flag('table_header_not_repeated', frags[1][0],
                                   f'{what} continues on page {frags[1][0]} without its header row'))
    # large blank at a page end followed by a pushed block; empty pages
    last_on, first_on, covered = {}, {}, set()
    for j, it in enumerate(items):
        e = _w_end_y(it)
        p = it['page_end']
        covered.update(range(it['page'], it['page_end'] + 1))
        if e is not None and (p not in last_on or e >= last_on[p][0]):
            last_on[p] = (e, it, j)
        if it['page'] not in first_on:
            first_on[it['page']] = (it, j)
    for p in range(1, (npages or 0) + 1):
        if p not in covered and npages > 1:
            flags.append(_flag('empty_page', p, 'the page has nothing on it'))
    for p in sorted(last_on):
        e, it, j = last_on[p]
        if p + 1 not in first_on:
            continue
        fill = (e - top) / area
        if fill >= 1 - BLANK:
            continue
        nf, jn = first_on[p + 1]
        kn = _w_kind(nf)
        what = f"page {p} ends at ~{max(fill, 0):.0%} ({1 - max(fill, 0):.0%} blank); page {p + 1} starts with {kn} " \
               f"{(nf.get('t') or '')[:40]!r}"
        if section_break_before(jn) or it.get('brk'):
            info.append(_flag('section_break_blank', p, what + ' (a page break by design)'))
        else:
            flags.append(_flag('large_blank_then_continuation', p, what))
    return flags, info, npages


def _word_layout_subprocess(path, timeout):
    """Run the COM layout in its own process (a hung Word never hangs the caller)."""
    fd, out = tempfile.mkstemp(suffix='.json', prefix='cx_wl_')
    os.close(fd)
    try:
        cp = subprocess.run([sys.executable, '-m', 'p6_export.pagination_check', '--word-layout', path, out],
                            timeout=timeout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if cp.returncode:
            tail = (cp.stderr or b'').decode('utf-8', 'replace').strip().splitlines()[-1:] or ['']
            raise RuntimeError(f'Word layout exited {cp.returncode}: {tail[0][:200]}')
        with open(out, encoding='utf-8') as fh:
            return json.load(fh)
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


def _spire_to_pdf(path):
    from spire.doc import Document, FileFormat
    fd, out = tempfile.mkstemp(suffix='.pdf', prefix='cx_spire_')
    os.close(fd)
    d = Document()
    d.LoadFromFile(os.path.abspath(path))
    d.SaveToFile(out, FileFormat.PDF)
    d.Close()
    return out


def check_docx(path, engine='auto', timeout=1800):
    """Check a Word file (.docx or .doc). ``engine``: 'auto' (Word, then Spire.Doc), 'word',
    'spire'. Returns status 'skipped' with a clear message when no renderer is available."""
    path = os.path.abspath(path)
    fmt = os.path.splitext(path)[1].lstrip('.').lower() or 'docx'
    tried = []
    if engine in ('auto', 'word'):
        if word_available():
            try:
                if getattr(sys, 'frozen', False):
                    layout = word_layout(path)
                else:
                    layout = _word_layout_subprocess(path, timeout)
                flags, info, npages = analyze_word_layout(layout)
                return _result(path, fmt, 'word-com', npages, flags, info,
                               message="Word's own pagination (COM layout)")
            except Exception as exc:          # fall through to Spire
                tried.append(f'Word COM failed: {str(exc)[:200]}')
        else:
            tried.append('Microsoft Word (COM via pywin32) is not available')
    if engine in ('auto', 'spire'):
        if spire_available():
            pdf = None
            try:
                pdf = _spire_to_pdf(path)
                res = check_pdf(pdf, headings=docx_headings(path) if fmt == 'docx' else None)
                res.update(file=path, format=fmt, engine='spire')
                res['message'] = ('rendered with Spire.Doc (its free edition converts only the first 10 '
                                  'pages; Word may paginate slightly differently)'
                                  + ('; ' + '; '.join(tried) if tried else ''))
                return res
            except Exception as exc:
                tried.append(f'Spire.Doc failed: {str(exc)[:200]}')
            finally:
                if pdf:
                    try:
                        os.remove(pdf)
                    except OSError:
                        pass
        else:
            tried.append('Spire.Doc (spire.doc) is not installed')
    return _result(path, fmt, 'none', 0, [], status='skipped',
                   message='Word file NOT checked - no local renderer: ' + '; '.join(tried)
                           + '. Install Microsoft Word + pywin32, or spire.doc, or check the PDF.')


def check_file(path, engine='auto', headings=None, timeout=1800):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.pdf':
        return check_pdf(path, headings=headings)
    if ext in ('.docx', '.doc'):
        return check_docx(path, engine=engine, timeout=timeout)
    raise ValueError(f'unsupported file type {ext!r} (expected .pdf, .docx or .doc)')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['--word-layout']:                    # internal: COM layout in a child process
        res = word_layout(argv[1])
        with open(argv[2], 'w', encoding='utf-8') as fh:
            json.dump(res, fh, ensure_ascii=False)
        return EXIT_CLEAN
    ap = argparse.ArgumentParser(prog='python -m p6_export.pagination_check',
                                 description='Find page-composition defects in a report PDF / Word file.')
    ap.add_argument('file', help='report .pdf, .docx or .doc')
    ap.add_argument('--engine', choices=('auto', 'word', 'spire'), default='auto',
                    help='Word renderer (default: Word COM, then Spire.Doc)')
    ap.add_argument('--html', help='the report source HTML - its heading texts help find headings')
    ap.add_argument('--timeout', type=int, default=1800, help='seconds allowed for Word to lay out')
    ap.add_argument('--indent', type=int, default=1)
    a = ap.parse_args(argv)
    if not os.path.isfile(a.file):
        print(json.dumps({'file': a.file, 'status': 'error', 'message': 'file not found'}))
        return EXIT_ERROR
    hints = None
    if a.html:
        with open(a.html, encoding='utf-8', errors='replace') as fh:
            hints = html_headings(fh.read())
    try:
        res = check_file(a.file, engine=a.engine, headings=hints, timeout=a.timeout)
    except Exception as exc:
        print(json.dumps({'file': a.file, 'status': 'error', 'message': str(exc)[:500]}))
        return EXIT_ERROR
    sys.stdout.write(json.dumps(res, ensure_ascii=False, indent=a.indent) + '\n')
    if res['status'] == 'skipped':
        return EXIT_SKIPPED
    return EXIT_FLAGS if res['flag_count'] else EXIT_CLEAN


if __name__ == '__main__':
    sys.exit(main())
