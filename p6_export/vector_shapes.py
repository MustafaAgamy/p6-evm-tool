"""Charts in Word as NATIVE, EDITABLE drawings — never pictures (owner comment 41).

"The Word file must match the PDF exactly, not as a picture: Word that can be edited, with
the same format and style."

A chart, a gauge or a row of tiles has no Word equivalent, so it used to reach Word as a
picture of the PDF.  The PDF Chrome prints is a VECTOR drawing: every bar is a filled path,
every label a run of text with its font, size and colour.  This module reads that drawing
(PyMuPDF) and writes it into Word as a group of real Word shapes and text boxes at the same
positions, sizes and colours:

  * each bar / track / ring segment / card border  →  a Word shape (click it, recolour it,
    resize it, delete it);
  * each label and number                          →  a Word text box (click it, retype it).

Nothing is rasterised, so the drawing stays sharp at any zoom and prints like the PDF.

    prims = page_prims(page, clip)                 # read one clip of a PDF page
    xml   = group_drawing_xml(prims, w_pt, h_pt, ids, max_w_emu)   # <w:drawing>…</w:drawing>

Every function is defensive: a path it cannot express is skipped, never raised.
"""
import re
from xml.sax.saxutils import escape as _esc

EMU_PT = 12700                       # EMU per PDF point
MAX_PRIMS = 6000                     # above this a drawing is too heavy for Word → caller falls back

_DRAW_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
            'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"')
_WPG_URI = 'http://schemas.microsoft.com/office/word/2010/wordprocessingGroup'

# PDF font names → the family Word should use (the report fonts are system fonts)
_FAMILIES = (('segoeui', 'Segoe UI'), ('segoe', 'Segoe UI'), ('calibri', 'Calibri'), ('arial', 'Arial'),
             ('helvetica', 'Arial'), ('inter', 'Inter'), ('nunito', 'Nunito'), ('roboto', 'Roboto'),
             ('consolas', 'Consolas'), ('courier', 'Courier New'), ('jetbrains', 'Consolas'),
             ('cascadia', 'Consolas'), ('menlo', 'Consolas'), ('times', 'Times New Roman'),
             ('georgia', 'Georgia'), ('verdana', 'Verdana'), ('tahoma', 'Tahoma'), ('sora', 'Segoe UI'))


def _emu(pt):
    return int(round(float(pt) * EMU_PT))


def _hex(rgb):
    if rgb is None:
        return None
    try:
        r, g, b = (max(0, min(255, int(round(float(c) * 255)))) for c in rgb[:3])
        return '%02X%02X%02X' % (r, g, b)
    except (TypeError, ValueError):
        return None


def _hex_int(n):
    try:
        return '%06X' % (int(n) & 0xFFFFFF)
    except (TypeError, ValueError):
        return '000000'


def _family(pdf_font):
    """PDF font name → the Word font family.  Segoe UI's extra weights are separate families in
    Word (Segoe UI Semibold / Black / Light / Semilight): naming them keeps every label exactly
    as wide as it is in the PDF."""
    name = re.sub(r'^[A-Z]{6}\+', '', str(pdf_font or ''))           # drop the subset prefix
    low = name.lower().replace(' ', '').replace('-', '')
    if 'segoeui' in low:
        for key, fam in (('semibold', 'Segoe UI Semibold'), ('semilight', 'Segoe UI Semilight'),
                         ('black', 'Segoe UI Black'), ('light', 'Segoe UI Light')):
            if key in low:
                return fam
        return 'Segoe UI'
    for key, fam in _FAMILIES:
        if key in low:
            return fam
    base = re.split(r'[-,]', name)[0]
    base = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', base).strip()
    return base or 'Calibri'


def _bold(span):
    f = str(span.get('font') or '').lower().replace(' ', '').replace('-', '')
    if 'segoeui' in f and any(k in f for k in ('semibold', 'semilight', 'black', 'light')):
        return False                                                  # the weight is in the family name
    return bool(int(span.get('flags') or 0) & 16) or any(k in f for k in ('bold', 'black', 'heavy', 'extrab'))


def _italic(span):
    f = str(span.get('font') or '').lower()
    return bool(int(span.get('flags') or 0) & 2) or 'italic' in f or 'oblique' in f


def _dashes_to_outline(segs, fill, stroke, bbox):
    """A dashed / dotted border reaches the PDF as hundreds of tiny filled dashes in one path —
    far too heavy for Word, and not what a planner would edit.  It becomes ONE shape: a dashed
    rectangle outline (or one dashed line) in the same colour.  None → not a dash pattern."""
    if not fill or stroke:
        return None
    subs, cur = [], None
    for sg in segs:
        if sg[0] == 'M':
            cur = [sg[1]]; subs.append(cur)
        elif sg[0] == 'L' and cur is not None:
            cur.append(sg[1])
        elif sg[0] == 'C' and cur is not None:
            cur.extend(sg[1:])
    if len(subs) < 16:
        return None
    thick = []
    for pts in subs:
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if max(w, h) > 14:                              # a real shape, not a dash
            return None
        thick.append(min(w, h))
    thick.sort()
    width = max(0.4, min(3.0, thick[len(thick) // 2] or 0.75))
    x0, y0, x1, y1 = bbox
    if min(x1 - x0, y1 - y0) <= width * 2.5:            # a single dashed line
        if x1 - x0 >= y1 - y0:
            ym = (y0 + y1) / 2.0; line = [('M', (x0, ym)), ('L', (x1, ym))]
        else:
            xm = (x0 + x1) / 2.0; line = [('M', (xm, y0)), ('L', (xm, y1))]
        return {'k': 'path', 'segs': line, 'fill': None, 'stroke': fill, 'width': width, 'fa': None, 'sa': None,
                'dash': True, 'rect': False, 'bbox': bbox}
    h = width / 2.0
    return {'k': 'path', 'segs': [], 'fill': None, 'stroke': fill, 'width': width, 'fa': None, 'sa': None,
            'dash': True, 'rect': True, 'bbox': (x0 + h, y0 + h, x1 - h, y1 - h)}


# ── read one clip of a PDF page ───────────────────────────────────────────────────────────
def page_prims(pg, clip, page_area=None):
    """The vector content of ``clip`` on PDF page ``pg`` as primitives, in points relative to
    the clip's top-left corner.  → list of dicts: {'k': 'path', ...} / {'k': 'text', ...}."""
    cx0, cy0, cx1, cy1 = clip.x0, clip.y0, clip.x1, clip.y1
    area = page_area or (pg.rect.width * pg.rect.height)
    out = []
    for d in pg.get_drawings():
        r = d.get('rect')
        if r is None or r.is_empty and not d.get('color'):
            continue
        if r.x1 < cx0 - 0.5 or r.x0 > cx1 + 0.5 or r.y1 < cy0 - 0.5 or r.y0 > cy1 + 0.5:
            continue
        if r.width * r.height >= area * 0.9:                         # the page's own background
            continue
        fill, stroke = _hex(d.get('fill')), _hex(d.get('color'))
        width = float(d.get('width') or 0)
        typ = d.get('type') or ''
        if 'f' not in typ:
            fill = None
        if 's' not in typ or width <= 0:
            stroke = None
        if not fill and not stroke:
            continue
        segs = []                                                    # ('M'|'L'|'C'|'Z', pts…)
        cur = None

        def move(p):
            segs.append(('M', (p.x - cx0, p.y - cy0)))

        def near(a, b):
            return a is not None and abs(a.x - b.x) < 0.01 and abs(a.y - b.y) < 0.01
        for it in d.get('items') or []:
            op = it[0]
            if op == 'l':
                p1, p2 = it[1], it[2]
                if not near(cur, p1):
                    move(p1)
                segs.append(('L', (p2.x - cx0, p2.y - cy0))); cur = p2
            elif op == 'c':
                p1, p2, p3, p4 = it[1], it[2], it[3], it[4]
                if not near(cur, p1):
                    move(p1)
                segs.append(('C', (p2.x - cx0, p2.y - cy0), (p3.x - cx0, p3.y - cy0), (p4.x - cx0, p4.y - cy0)))
                cur = p4
            elif op == 're':
                rc = it[1]
                segs.append(('M', (rc.x0 - cx0, rc.y0 - cy0))); segs.append(('L', (rc.x1 - cx0, rc.y0 - cy0)))
                segs.append(('L', (rc.x1 - cx0, rc.y1 - cy0))); segs.append(('L', (rc.x0 - cx0, rc.y1 - cy0)))
                segs.append(('Z',)); cur = None
            elif op == 'qu':
                q = it[1]
                segs.append(('M', (q.ul.x - cx0, q.ul.y - cy0))); segs.append(('L', (q.ur.x - cx0, q.ur.y - cy0)))
                segs.append(('L', (q.lr.x - cx0, q.lr.y - cy0))); segs.append(('L', (q.ll.x - cx0, q.ll.y - cy0)))
                segs.append(('Z',)); cur = None
        if not segs:
            continue
        if d.get('closePath') and segs[-1][0] != 'Z':
            segs.append(('Z',))
        items = d.get('items') or []
        is_rect = len(items) == 1 and items[0][0] == 're'
        dashed = _dashes_to_outline(segs, fill, stroke, (r.x0 - cx0, r.y0 - cy0, r.x1 - cx0, r.y1 - cy0))
        if dashed:
            out.append(dashed)
            continue
        bx0, by0, bx1, by1 = r.x0 - cx0, r.y0 - cy0, r.x1 - cx0, r.y1 - cy0
        ch = cy1 - cy0
        if by0 < -1.0 or by1 > ch + 1.0:
            # the drawing was cut into page-high slices and this shape crosses the cut: a small
            # shape goes whole to the slice that holds its middle; a container (a card, a lane
            # background) is cut straight at the slice edge so each slice shows its own part
            mid = (by0 + by1) / 2.0
            if (by1 - by0) <= 40:
                if not (0 <= mid <= ch):
                    continue
            else:
                ny0, ny1 = max(by0, 0.0), min(by1, ch)
                if ny1 - ny0 < 1.0:
                    continue
                out.append({'k': 'path', 'segs': [], 'fill': fill, 'stroke': stroke, 'width': width,
                            'fa': d.get('fill_opacity'), 'sa': d.get('stroke_opacity'), 'dash': False,
                            'rect': True, 'bbox': (bx0, ny0, bx1, ny1)})
                continue
        out.append({'k': 'path', 'segs': segs, 'fill': fill, 'stroke': stroke, 'width': width,
                    'fa': d.get('fill_opacity'), 'sa': d.get('stroke_opacity'),
                    'dash': bool(d.get('dashes') and str(d.get('dashes')).strip('[] 0')),
                    'rect': is_rect, 'bbox': (r.x0 - cx0, r.y0 - cy0, r.x1 - cx0, r.y1 - cy0)})
    try:
        blocks = pg.get_text('dict', clip=clip).get('blocks') or []
    except Exception:
        blocks = []
    for b in blocks:
        for line in b.get('lines') or []:
            dx, dy = (line.get('dir') or (1, 0))[:2]
            for sp in line.get('spans') or []:
                text = sp.get('text') or ''
                if not text.strip():
                    continue
                x0, y0, x1, y1 = sp.get('bbox')
                by = (sp.get('origin') or (0, y1))[1]
                if not (cy0 - 0.01 <= by < cy1 + 0.01) and (cy1 - cy0) < pg.rect.height - 1:
                    continue
                out.append({'k': 'text', 'text': text, 'size': float(sp.get('size') or 9),
                            'color': _hex_int(sp.get('color')), 'bold': _bold(sp), 'italic': _italic(sp),
                            'font': _family(sp.get('font')), 'vert': abs(dy) > 0.7,
                            'up': dy < -0.7,
                            'base': (sp.get('origin') or (0, y1 - 0.22 * float(sp.get('size') or 9)))[1] - cy0,
                            'bbox': (x0 - cx0, y0 - cy0, x1 - cx0, y1 - cy0)})
    return out


# ── write one group of Word shapes ────────────────────────────────────────────────────────
def _clr(hexv, alpha=None):
    a = ''
    try:
        if alpha is not None and float(alpha) < 0.995:
            a = '<a:alpha val="%d"/>' % int(round(max(0.0, min(1.0, float(alpha))) * 100000))
    except (TypeError, ValueError):
        a = ''
    return f'<a:srgbClr val="{hexv}">{a}</a:srgbClr>'


def _ln(p):
    if not p.get('stroke'):
        return '<a:ln><a:noFill/></a:ln>'
    dash = '<a:prstDash val="dash"/>' if p.get('dash') else ''
    return (f'<a:ln w="{max(1, _emu(p["width"]))}"><a:solidFill>{_clr(p["stroke"], p.get("sa"))}</a:solidFill>'
            f'{dash}</a:ln>')


def _path_shape(p, sid):
    x0, y0, x1, y1 = p['bbox']
    pad = (p['width'] / 2.0) if p.get('stroke') else 0.0
    # a hairline (zero width or height) is not drawn by Word: give the box the line's thickness
    if x1 - x0 < 0.2:
        x0, x1 = x0 - max(pad, 0.25), x1 + max(pad, 0.25)
    if y1 - y0 < 0.2:
        y0, y1 = y0 - max(pad, 0.25), y1 + max(pad, 0.25)
    w, h = max(1, _emu(x1 - x0)), max(1, _emu(y1 - y0))
    fill = f'<a:solidFill>{_clr(p["fill"], p.get("fa"))}</a:solidFill>' if p.get('fill') else '<a:noFill/>'
    head = (f'<wps:wsp><wps:cNvPr id="{sid}" name="Shape {sid}"/><wps:cNvSpPr/><wps:spPr>'
            f'<a:xfrm><a:off x="{_emu(x0)}" y="{_emu(y0)}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>')
    if p.get('rect'):
        geom = '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
    else:
        d = ''
        for s in p['segs']:
            if s[0] == 'M':
                d += f'<a:moveTo><a:pt x="{_emu(s[1][0] - x0)}" y="{_emu(s[1][1] - y0)}"/></a:moveTo>'
            elif s[0] == 'L':
                d += f'<a:lnTo><a:pt x="{_emu(s[1][0] - x0)}" y="{_emu(s[1][1] - y0)}"/></a:lnTo>'
            elif s[0] == 'C':
                d += ('<a:cubicBezTo>' + ''.join(f'<a:pt x="{_emu(q[0] - x0)}" y="{_emu(q[1] - y0)}"/>' for q in s[1:])
                      + '</a:cubicBezTo>')
            else:
                d += '<a:close/>'
        mode = 'norm' if p.get('fill') else 'none'
        geom = (f'<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="0" t="0" r="{w}" b="{h}"/>'
                f'<a:pathLst><a:path w="{w}" h="{h}" fill="{mode}">{d}</a:path></a:pathLst></a:custGeom>')
    return f'{head}{geom}{fill}{_ln(p)}</wps:spPr><wps:bodyPr/></wps:wsp>'


def _text_shape(t, sid):
    x0, y0, x1, y1 = t['bbox']
    size_hp = max(2, int(round(t['size'] * 2)))
    # a little room on the right: Word's font metrics differ a hair from the PDF's, and a
    # label must never wrap or be cut
    w = (x1 - x0) + max(3.0, t['size'] * 0.9)
    h = max(y1 - y0, t['size'] * 1.25)
    rot = ''
    if t.get('vert'):                                               # a label turned 90°
        w, h = (y1 - y0) + max(3.0, t['size'] * 0.9), max(x1 - x0, t['size'] * 1.25)
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        x0, y0 = cx - w / 2.0, cy - h / 2.0
        rot = ' rot="%d"' % (-5400000 if t.get('up') else 5400000)
    # rFonts must come first inside rPr for a schema-valid document
    rpr = (f'<w:rFonts w:ascii="{_esc(t["font"])}" w:hAnsi="{_esc(t["font"])}" w:cs="{_esc(t["font"])}"/>'
           + ('<w:b/>' if t.get('bold') else '') + ('<w:i/>' if t.get('italic') else '')
           + f'<w:color w:val="{t["color"]}"/><w:sz w:val="{size_hp}"/><w:szCs w:val="{size_hp}"/>')
    text = _esc(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', t['text']))
    return (f'<wps:wsp><wps:cNvPr id="{sid}" name="Text {sid}"/><wps:cNvSpPr txBox="1"/><wps:spPr>'
            f'<a:xfrm{rot}><a:off x="{_emu(x0)}" y="{_emu(y0)}"/><a:ext cx="{max(1, _emu(w))}" cy="{max(1, _emu(h))}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></wps:spPr>'
            f'<wps:txbx><w:txbxContent><w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
            f'<w:jc w:val="left"/></w:pPr><w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
            f'</w:txbxContent></wps:txbx>'
            f'<wps:bodyPr rot="0" wrap="none" lIns="0" tIns="0" rIns="0" bIns="0" anchor="ctr"><a:noAutofit/></wps:bodyPr>'
            f'</wps:wsp>')


# ── labels as a few text LAYERS ───────────────────────────────────────────────────────────
# One Word text box per label is exact but slow: Word lays out every text box as its own
# story, and a report with hundreds of labels took minutes to open.  So the labels of one
# drawing share a few transparent text boxes ("layers") that cover the whole drawing.  Inside
# a layer every line of labels is one paragraph: its height puts it at the right place down
# the page, and a tab stop puts each label at the right place across it.  The text is still
# ordinary Word text — click a label and retype it.
# How Word sets a paragraph with EXACT line spacing L: the baseline sits 0.8 × L below the top
# of the line (measured in Word; it does not depend on the font).  So a label whose baseline
# must be at B gets a line of height 1.25 × its size that starts at B − size, and an empty
# spacer paragraph above it takes up whatever room is left.
RIGHT_PAD = 10.0                     # points added to the right of every drawing (see group_drawing_xml)
LINE_K = 1.35                        # a label's own line: this × its font size
MIN_K = 1.28                         # … and never less than this (the glyphs would be cut)
ASC = 0.8                            # Word: baseline = line top + 0.8 × line height


def _base(t):
    return t.get('base') if t.get('base') is not None else t['bbox'][3] - 0.22 * t['size']


def _text_lines(texts):
    """Labels grouped into lines (same baseline), each line sorted left → right."""
    lines = []
    for t in sorted(texts, key=lambda t: (_base(t), t['bbox'][0])):
        for ln in reversed(lines[-6:]):
            if abs(ln['base'] - _base(t)) <= 0.5 and all(
                    t['bbox'][0] >= o['bbox'][2] - 0.5 or t['bbox'][2] <= o['bbox'][0] + 0.5 for o in ln['spans']):
                ln['spans'].append(t)
                break
        else:
            lines.append({'base': _base(t), 'spans': [t]})
    for ln in lines:
        ln['spans'].sort(key=lambda t: t['bbox'][0])
        ln['size'] = max(t['size'] for t in ln['spans'])
    lines.sort(key=lambda l: l['base'])
    return lines


def _layers(lines):
    """Lines dealt into as few layers as possible.  Each layer is a list of
    (line, spacer_height, line_height) and stacks without overlap."""
    layers = []                                                  # [{'end': y, 'top': y, 'rows': […]}]
    for ln in lines:
        s, B = ln['size'], ln['base']
        want_top = B - ASC * LINE_K * s                          # so that a LINE_K line puts the baseline at B
        for lay in layers:
            room = want_top - lay['end']
            if room >= 1.0:                                      # a spacer fills the room
                lay['rows'].append((ln, room, LINE_K * s)); lay['end'] = want_top + LINE_K * s
                break
            height = (B - lay['end']) / ASC                      # start right where the layer ends
            if height >= MIN_K * s:
                lay['rows'].append((ln, 0.0, height)); lay['end'] += height
                break
        else:
            layers.append({'top': want_top, 'end': want_top + LINE_K * s, 'rows': [(ln, 0.0, LINE_K * s)]})
    return layers


def _rpr(t):
    size_hp = max(2, int(round(t['size'] * 2)))
    f = _esc(t['font'])
    return (f'<w:rPr><w:rFonts w:ascii="{f}" w:hAnsi="{f}" w:cs="{f}"/>'
            + ('<w:b/>' if t.get('bold') else '') + ('<w:i/>' if t.get('italic') else '')
            + f'<w:color w:val="{t["color"]}"/><w:sz w:val="{size_hp}"/><w:szCs w:val="{size_hp}"/></w:rPr>')


def _clean_text(text):
    return _esc(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text))


def _exact(height_pt):
    return f'<w:spacing w:before="0" w:after="0" w:line="{max(1, int(round(height_pt * 20)))}" w:lineRule="exact"/>'


def _layer_shape(layer, sid, w_pt, h_pt):
    """One transparent text box holding a layer: one paragraph per line of labels."""
    paras = ''
    for ln, spacer, height in layer['rows']:
        if spacer > 0:
            paras += f'<w:p><w:pPr>{_exact(spacer)}<w:rPr><w:sz w:val="2"/><w:szCs w:val="2"/></w:rPr></w:pPr></w:p>'
        tabs, runs, x_end, ind = '', '', None, 0
        for t in ln['spans']:
            x0 = t['bbox'][0]
            if x_end is None:
                ind = max(0, int(round(x0 * 20)))
            elif x0 - x_end > 1.2:                               # a gap: jump to this label's own position
                tabs += f'<w:tab w:val="left" w:pos="{max(1, int(round(x0 * 20)))}"/>'
                runs += f'<w:r>{_rpr(t)}<w:tab/></w:r>'
            runs += f'<w:r>{_rpr(t)}<w:t xml:space="preserve">{_clean_text(t["text"])}</w:t></w:r>'
            x_end = t['bbox'][2]
        paras += ('<w:p><w:pPr>' + (f'<w:tabs>{tabs}</w:tabs>' if tabs else '') + _exact(height)
                  + f'<w:ind w:left="{ind}"/><w:jc w:val="left"/></w:pPr>{runs}</w:p>')
    # the text box stays INSIDE the drawing's own frame: Word crops a group whose child
    # reaches outside it
    top = max(0.0, layer['top'])
    h = max(1.0, min(layer['end'] + 3.0, h_pt) - top)
    return (f'<wps:wsp><wps:cNvPr id="{sid}" name="Labels {sid}"/><wps:cNvSpPr txBox="1"/><wps:spPr>'
            f'<a:xfrm><a:off x="0" y="{_emu(top)}"/><a:ext cx="{max(1, _emu(w_pt))}" cy="{max(1, _emu(h))}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></wps:spPr>'
            f'<wps:txbx><w:txbxContent>{paras}</w:txbxContent></wps:txbx>'
            f'<wps:bodyPr rot="0" wrap="none" lIns="0" tIns="0" rIns="0" bIns="0" anchor="t"><a:noAutofit/></wps:bodyPr>'
            f'</wps:wsp>')


def _scaled(p, k):
    q = dict(p)
    x0, y0, x1, y1 = p['bbox']
    q['bbox'] = (x0 * k, y0 * k, x1 * k, y1 * k)
    if p['k'] == 'path':
        q['segs'] = [(sg[0],) + tuple((pt[0] * k, pt[1] * k) for pt in sg[1:]) for sg in p['segs']]
        q['width'] = p['width'] * k
    else:
        q['size'] = p['size'] * k
        if p.get('base') is not None:
            q['base'] = p['base'] * k
    return q


def group_drawing_xml(prims, w_pt, h_pt, ids, max_w_emu=None, max_h_emu=None, name='Chart'):
    """Primitives → one inline ``<w:drawing>`` holding a group of Word shapes (XML string), or
    None when there is nothing to draw / too much for Word.  ``ids`` is a one-item list used
    as the shape-id allocator.  The group is shown 1:1, or scaled down as a whole to fit
    ``max_w_emu`` × ``max_h_emu``."""
    if not prims or len(prims) > MAX_PRIMS or w_pt <= 0 or h_pt <= 0:
        return None
    # a little room on the right: Word's text is now and then a hair wider than the PDF's, and
    # a label that ends at the frame's edge would lose its last letters
    w_pt = w_pt + RIGHT_PAD
    w, h = max(1, _emu(w_pt)), max(1, _emu(h_pt))
    scale = 1.0
    if max_w_emu and w > max_w_emu:
        scale = min(scale, max_w_emu / float(w))
    if max_h_emu and h * scale > max_h_emu:
        scale = min(scale, max_h_emu / float(h))
    if scale < 0.999:
        # Word scales the SHAPES of a group but not the line heights of the text inside it, so
        # the labels would drift away from their bars.  Scale every coordinate and every font
        # size here instead, and show the group 1:1.
        prims = [_scaled(p, scale) for p in prims]
        w_pt, h_pt = w_pt * scale, h_pt * scale
        w, h = max(1, _emu(w_pt)), max(1, _emu(h_pt))
    dw, dh = w, h
    gid = ids[0]; ids[0] += 1
    # An invisible rectangle the size of the whole frame comes first.  Word lays a group out
    # from the box around its children: when the first shape starts a few points below the
    # frame's top, Word moves the shapes up to the top but not the text, and every label ends
    # up that much too low.  With this rectangle the children's box IS the frame.
    fid = ids[0]; ids[0] += 1
    shapes = [f'<wps:wsp><wps:cNvPr id="{fid}" name="Frame {fid}"/><wps:cNvSpPr/><wps:spPr>'
              f'<a:xfrm><a:off x="0" y="0"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
              f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></wps:spPr>'
              f'<wps:bodyPr/></wps:wsp>']
    flat = []                                                   # labels that go into the text layers
    for p in prims:
        if p['k'] == 'text' and not p.get('vert'):
            flat.append(p)
            continue
        sid = ids[0]; ids[0] += 1
        try:
            shapes.append(_path_shape(p, sid) if p['k'] == 'path' else _text_shape(p, sid))
        except Exception:
            continue
    try:
        for layer in _layers(_text_lines(flat)):
            sid = ids[0]; ids[0] += 1
            shapes.append(_layer_shape(layer, sid, w_pt, h_pt))
    except Exception:
        for t in flat:                                          # never lose a label
            sid = ids[0]; ids[0] += 1
            shapes.append(_text_shape(t, sid))
    if len(shapes) < 2:
        return None
    return (f'<w:drawing {_DRAW_NS}><wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{dw}" cy="{dh}"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
            f'<wp:docPr id="{gid}" name="{_esc(name)} {gid}"/><wp:cNvGraphicFramePr/>'
            f'<a:graphic><a:graphicData uri="{_WPG_URI}"><wpg:wgp><wpg:cNvGrpSpPr/>'
            f'<wpg:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{dw}" cy="{dh}"/>'
            f'<a:chOff x="0" y="0"/><a:chExt cx="{w}" cy="{h}"/></a:xfrm></wpg:grpSpPr>'
            f'{"".join(shapes)}</wpg:wgp></a:graphicData></a:graphic></wp:inline></w:drawing>')
