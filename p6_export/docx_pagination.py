"""Word pagination rules — the Word twin of ``report_theme.pagination_css()`` (owner point 14).

ONE post-pass every Word writer runs on its finished python-docx ``Document`` just before
saving (p6_export.to_docx, the Baseline Narrative docx toolkit, the Reporting Studio
docx_report), so every Word report follows the same page-composition rules as the PDF:

* a heading never ends a page — it keeps with the next paragraph, and the keep runs on
  through empty spacer paragraphs and a short intro/label up to the first block;
* a short paragraph right before a table or a picture (a heading, an intro, a caption /
  label) keeps with it; a picture keeps with a caption line under it ("Figure …");
* tables: every row ``cantSplit`` (a row never breaks across pages); a table that fits in
  about a third of a page is kept whole (keep-with-next on every row but the last); a
  longer table repeats its header row on every page and keeps its first 3 and last 3
  body rows together, so no page ever holds only 1–2 rows of it;
* KPI tile tables are small tables → kept whole, with their heading.

Pure lxml work on the document body; never changes text, values, colours or order.
"""
import math

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

try:                                   # the same thresholds as the PDF rules
    import report_theme as _rt
    FIT = float(getattr(_rt, 'PAGINATION_FIT', 0.35))
    MIN_ROWS = int(getattr(_rt, 'PAGINATION_MIN_ROWS', 3))
except Exception:                      # pragma: no cover — report_theme always ships
    FIT, MIN_ROWS = 0.35, 3

EMU_PER_PT = 12700
_SHORT_LEAD = 320          # chars: a heading / intro / label / caption, not a body paragraph
_CAPTION_PREFIXES = ('figure', 'fig.', 'fig ', 'chart', 'source:', 'note:', 'table ')
_PICTURE_SLACK_PT = 14.0   # room left under a fitted picture (line spacing, rounding)

_W_P, _W_TBL, _W_TR, _W_TC = qn('w:p'), qn('w:tbl'), qn('w:tr'), qn('w:tc')
_TRPR_ORDER = ('cnfStyle', 'divId', 'gridBefore', 'gridAfter', 'wBefore', 'wAfter', 'cantSplit',
               'trHeight', 'tblHeader', 'tblCellSpacing', 'jc', 'hidden', 'ins', 'del',
               'trPrChange')
_TRPR_RANK = {qn('w:' + n): i for i, n in enumerate(_TRPR_ORDER)}


# ── small XML helpers ───────────────────────────────────────────────────────────
def _text(el):
    return ''.join(t.text or '' for t in el.iter(qn('w:t')))


def _has_drawing(p):
    for tag in ('w:drawing', 'w:pict', 'w:object'):
        if p.find('.//' + qn(tag)) is not None:
            return True
    return False


def _has_break(p):
    """A paragraph that forces a new page (page break run, page-break-before, section end)."""
    for br in p.iter(qn('w:br')):
        if br.get(qn('w:type')) == 'page':
            return True
    ppr = p.find(qn('w:pPr'))
    if ppr is not None:
        if ppr.find(qn('w:sectPr')) is not None:
            return True
        pb = ppr.find(qn('w:pageBreakBefore'))
        if pb is not None and pb.get(qn('w:val'), 'true') not in ('0', 'false', 'off'):
            return True
    return False


def _ends_page(p):
    """A paragraph whose own content ends the page (a page-break run, a section end) — unlike
    'page break before', which only starts ITS paragraph on a new page (a section heading
    that opens a new page still keeps with its content)."""
    for br in p.iter(qn('w:br')):
        if br.get(qn('w:type')) == 'page':
            return True
    ppr = p.find(qn('w:pPr'))
    return ppr is not None and ppr.find(qn('w:sectPr')) is not None


def _style_id(p):
    ppr = p.find(qn('w:pPr'))
    st = ppr.find(qn('w:pStyle')) if ppr is not None else None
    return (st.get(qn('w:val')) or '') if st is not None else ''


def _keep_next_on(p):
    ppr = p.find(qn('w:pPr'))
    kn = ppr.find(qn('w:keepNext')) if ppr is not None else None
    return kn is not None and kn.get(qn('w:val'), 'true') not in ('0', 'false', 'off')


def _keep_next_off(p):
    """The renderer EXPLICITLY turned 'keep with next' off (``<w:keepNext w:val="0"/>``,
    python-docx ``keep_with_next = False``): the paragraph closes the block above it — a
    chart's 'Peak …' caption — and is not a lead of the block after it."""
    ppr = p.find(qn('w:pPr'))
    kn = ppr.find(qn('w:keepNext')) if ppr is not None else None
    return kn is not None and kn.get(qn('w:val'), 'true') in ('0', 'false', 'off')


def keep_with_next(p):
    """Set Word 'Keep with next' on a ``w:p`` element (schema order handled by python-docx)."""
    if p is None or p.tag != _W_P or _ends_page(p):
        return
    p.get_or_add_pPr().keepNext_val = True


def _set_tr_flag(tr, name, val=None):
    trPr = tr.find(qn('w:trPr'))
    if trPr is None:
        trPr = OxmlElement('w:trPr')
        tr.insert(1 if (len(tr) and tr[0].tag == qn('w:tblPrEx')) else 0, trPr)
    tag = qn('w:' + name)
    if trPr.find(tag) is not None:
        return
    el = OxmlElement('w:' + name)
    if val is not None:
        el.set(qn('w:val'), val)
    rank = _TRPR_RANK.get(tag, len(_TRPR_RANK))
    for i, ch in enumerate(list(trPr)):
        if _TRPR_RANK.get(ch.tag, len(_TRPR_RANK)) > rank:
            trPr.insert(i, el)
            return
    trPr.append(el)


def _clear_tr_flag(tr, name):
    trPr = tr.find(qn('w:trPr'))
    if trPr is not None:
        for el in trPr.findall(qn('w:' + name)):
            trPr.remove(el)


def _is_header_row(tr):
    trPr = tr.find(qn('w:trPr'))
    if trPr is None:
        return False
    h = trPr.find(qn('w:tblHeader'))
    return h is not None and h.get(qn('w:val'), 'true') not in ('0', 'false', 'off')


def _row_paragraphs(tr):
    """The row's own paragraphs (not those of a table nested inside a cell)."""
    out = []
    for tc in tr.findall(_W_TC):
        out.extend(tc.findall(_W_P))
    return out


def _keep_row_with_next(tr):
    for p in _row_paragraphs(tr):
        keep_with_next(p)


def _all_bold(tr):
    runs = [r for tc in tr.findall(_W_TC) for p in tc.findall(_W_P) for r in p.findall(qn('w:r'))
            if (_text(r) or '').strip()]
    if not runs:
        return False
    for r in runs:
        rpr = r.find(qn('w:rPr'))
        b = rpr.find(qn('w:b')) if rpr is not None else None
        if b is None or b.get(qn('w:val'), 'true') in ('0', 'false', 'off'):
            return False
    return True


# ── size estimates (twips = 1/20 pt) ────────────────────────────────────────────
def _body_height_pt(document):
    best = None
    try:
        for s in document.sections:
            if s.page_height is None:
                continue
            h = (int(s.page_height) - int(s.top_margin or 0) - int(s.bottom_margin or 0)) / EMU_PER_PT
            best = h if best is None else min(best, h)
    except Exception:
        best = None
    return best or 734.0                      # A4 portrait with ~1 in margins


def _body_width_pt(document):
    try:
        s = document.sections[0]
        return (int(s.page_width) - int(s.left_margin or 0) - int(s.right_margin or 0)) / EMU_PER_PT
    except Exception:
        return 470.0


def _font_pt(p, default=10.0):
    for sz in p.iter(qn('w:sz')):
        try:
            return int(sz.get(qn('w:val'))) / 2.0
        except (TypeError, ValueError):
            continue
    return default


def _tc_width_pt(tc, fallback):
    tcPr = tc.find(qn('w:tcPr'))
    w = tcPr.find(qn('w:tcW')) if tcPr is not None else None
    if w is not None and w.get(qn('w:type'), 'dxa') == 'dxa':
        try:
            v = int(float(w.get(qn('w:w')))) / 20.0
            if v > 10:
                return v
        except (TypeError, ValueError):
            pass
    return fallback


def _row_height_pt(tr, width_pt):
    trPr = tr.find(qn('w:trPr'))
    trh = trPr.find(qn('w:trHeight')) if trPr is not None else None
    fixed = 0.0
    if trh is not None:
        try:
            fixed = int(trh.get(qn('w:val'))) / 20.0
        except (TypeError, ValueError):
            fixed = 0.0
        if trh.get(qn('w:hRule')) == 'exact' and fixed:
            return fixed
    tcs = tr.findall(_W_TC)
    col_w = width_pt / max(1, len(tcs))
    best = 0.0
    for tc in tcs:
        cw = max(20.0, _tc_width_pt(tc, col_w) - 8.0)
        h = 4.0                                              # cell padding
        for p in tc.findall(_W_P):
            size = _font_pt(p)
            chars = len(_text(p))
            per_line = max(1, int(cw / (size * 0.5)))
            lines = max(1, math.ceil(chars / per_line))
            h += lines * size * 1.2
            if _has_drawing(p):
                h += _drawing_height_pt(p)
        for inner in tc.findall(_W_TBL):
            h += _table_height_pt(inner, cw)
        best = max(best, h)
    return max(best, fixed)


def _drawing_height_pt(el):
    for ext in el.iter(qn('wp:extent')):
        try:
            return int(ext.get('cy')) / EMU_PER_PT
        except (TypeError, ValueError):
            continue
    return 0.0


def _table_height_pt(tbl, width_pt):
    return sum(_row_height_pt(tr, width_pt) for tr in tbl.findall(_W_TR))


def _para_height_pt(p, width_pt):
    """Rough height of a text paragraph: its lines plus its space before / after."""
    size = _font_pt(p)
    per_line = max(1, int(max(20.0, width_pt) / (size * 0.5)))
    lines = max(1, math.ceil(len(_text(p)) / per_line))
    h = lines * size * 1.25
    ppr = p.find(qn('w:pPr'))
    sp = ppr.find(qn('w:spacing')) if ppr is not None else None
    if sp is not None:
        for k in ('before', 'after'):
            try:
                h += int(sp.get(qn('w:' + k)) or 0) / 20.0
            except (TypeError, ValueError):
                pass
    return h


def _inline_pictures(p):
    """The paragraph's inline pictures as (wp:extent, [a:ext …]) pairs (anchored shapes —
    floating, positioned by the writer — are left alone)."""
    out = []
    for inl in p.iter(qn('wp:inline')):
        ext = inl.find(qn('wp:extent'))
        if ext is not None:
            out.append((ext, list(inl.iter(qn('a:ext')))))
    return out


def fit_picture(p, avail_pt, min_scale=0.5):
    """Scale the one inline picture of paragraph ``p`` down (aspect kept) so it is at most
    ``avail_pt`` tall. Returns True when it was scaled. A picture that would have to shrink
    below ``min_scale`` of its size is left as it is (it would become unreadable)."""
    pics = _inline_pictures(p)
    if len(pics) != 1 or avail_pt <= 0:
        return False
    ext, inner = pics[0]
    try:
        cx, cy = int(ext.get('cx')), int(ext.get('cy'))
    except (TypeError, ValueError):
        return False
    h = cy / EMU_PER_PT
    if h <= avail_pt:
        return False
    scale = avail_pt / h
    if scale < min_scale:
        return False
    ncx, ncy = max(1, int(cx * scale)), max(1, int(cy * scale))
    ext.set('cx', str(ncx))
    ext.set('cy', str(ncy))
    for a in inner:                      # a:ext of the picture's own transform
        if a.get('cx') is not None and a.get('cy') is not None:
            a.set('cx', str(ncx))
            a.set('cy', str(ncy))
    return True


# ── the rules ───────────────────────────────────────────────────────────────────
def paginate_table(tbl, body_h_pt, body_w_pt, header_rows=None):
    """Apply the table rules to one body-level ``w:tbl``. ``header_rows`` = how many leading
    rows are the header (``None`` → rows already marked ``tblHeader``, or a first row that is
    all bold over a body that is not)."""
    rows = tbl.findall(_W_TR)
    n = len(rows)
    if not n:
        return
    if header_rows is None:
        header_rows = 0
        while header_rows < n and _is_header_row(rows[header_rows]):
            header_rows += 1
        if (header_rows == 0 and n >= 4 and len(rows[0].findall(_W_TC)) >= 2
                and _all_bold(rows[0]) and not _all_bold(rows[1])):
            header_rows = 1
    heights = [_row_height_pt(tr, body_w_pt) for tr in rows]
    for i, tr in enumerate(rows):
        if heights[i] > body_h_pt * 0.8:
            _clear_tr_flag(tr, 'cantSplit')      # Word would CLIP a non-breaking row taller than a page
        else:
            _set_tr_flag(tr, 'cantSplit')
        if i < header_rows:
            _set_tr_flag(tr, 'tblHeader', 'true')
    est = sum(heights)
    if est <= body_h_pt * FIT or (n <= MIN_ROWS + header_rows and est <= body_h_pt * 0.8):
        for tr in rows[:-1]:                                # small: kept whole
            _keep_row_with_next(tr)
        return
    # long: header + first MIN_ROWS body rows together, last MIN_ROWS rows together
    for tr in rows[:min(n - 1, header_rows + MIN_ROWS - 1)]:
        _keep_row_with_next(tr)
    for tr in rows[max(header_rows, n - MIN_ROWS):n - 1]:
        _keep_row_with_next(tr)


def _is_heading(p):
    sid = _style_id(p).lower()
    return sid.startswith('heading') or sid in ('title', 'subtitle') or _keep_next_on(p)


def _blank(p):
    return p.tag == _W_P and not _text(p).strip() and not _has_drawing(p) and not _has_break(p)


def paginate_docx(document):
    """Apply every Word pagination rule to ``document`` (a python-docx ``Document``) in
    place and return it. Safe to run more than once."""
    body = document.element.body
    body_h = _body_height_pt(document)
    body_w = _body_width_pt(document)
    items = [el for el in body if el.tag in (_W_P, _W_TBL)]
    # tables (body level only; nested layout tables ride inside their cell)
    for el in items:
        if el.tag == _W_TBL:
            try:
                paginate_table(el, body_h, body_w)
            except Exception:
                continue
    n = len(items)

    def prev_lead(i):
        """Chain back from a block at ``i``: blank spacers and ONE short lead paragraph."""
        j = i - 1
        chain = []
        while j >= 0 and items[j].tag == _W_P and _blank(items[j]):
            chain.append(items[j])
            j -= 1
        if j >= 0 and items[j].tag == _W_P and _keep_next_off(items[j]) and not _is_heading(items[j]):
            return []                                       # a caption that closes its figure
        if j >= 0 and items[j].tag == _W_P and not _has_drawing(items[j]) and not _has_break(items[j]):
            t = _text(items[j]).strip()
            if t and len(t) <= _SHORT_LEAD:
                chain.append(items[j])
                # a heading directly above that short lead keeps with it too
                k = j - 1
                while k >= 0 and items[k].tag == _W_P and _blank(items[k]):
                    k -= 1
                if k >= 0 and items[k].tag == _W_P and _is_heading(items[k]):
                    chain.append(items[k])
                    chain.extend(x for x in items[k + 1:j] if _blank(x))
            else:
                return []
        elif chain and not (j >= 0 and items[j].tag == _W_P and _is_heading(items[j])):
            return []
        return chain

    for i, el in enumerate(items):
        if el.tag == _W_P and _is_heading(el) and not _ends_page(el):
            keep_with_next(el)                              # heading → first line of next
            j = i + 1
            while j < n and items[j].tag == _W_P and _blank(items[j]):
                keep_with_next(items[j])                    # through empty spacers
                j += 1
        is_block = el.tag == _W_TBL or (el.tag == _W_P and _has_drawing(el))
        lead = prev_lead(i) if is_block else []
        for p in lead:
            keep_with_next(p)
        cap_h = 0.0
        if el.tag == _W_P and _has_drawing(el) and i + 1 < n and items[i + 1].tag == _W_P:
            cap = _text(items[i + 1]).strip().lower()
            if cap and len(cap) <= _SHORT_LEAD and cap.startswith(_CAPTION_PREFIXES):
                keep_with_next(el)                          # picture stays with its caption
                cap_h = _para_height_pt(items[i + 1], body_w)
        if el.tag == _W_P and _has_drawing(el):
            # a picture kept with its heading / label / caption must FIT on one page with
            # them — otherwise Word leaves the heading alone on a near-blank page (or clips
            # a picture taller than the page). Scale it down to the room left (aspect kept).
            lead_h = sum(_para_height_pt(p, body_w) for p in lead)
            try:
                fit_picture(el, body_h - lead_h - cap_h - _PICTURE_SLACK_PT)
            except Exception:
                pass
    return document
