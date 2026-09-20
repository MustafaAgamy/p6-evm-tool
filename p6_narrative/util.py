"""Shared, dependency-free helpers for the narrative assembler."""
import math


def chevron_layout(labels, max_width_px=724, base_font_px=12, min_w=84, max_w=210,
                   gap=6, vgap=10, pad=12, notch=14):
    """Lay out a sequence chevron flow so text is NEVER truncated: each label is word-wrapped
    (and the font shrunk when wrapping alone is not enough), each shape is sized to its own
    text, and the flow wraps onto MULTIPLE ROWS when one row would exceed ``max_width_px``.

    This is the single source of truth for BOTH renderers — ``html._chevrons`` (inline SVG,
    screen/PDF) and ``docx_native.add_chevron_flow`` (native Word shapes) — so the two read
    identically: same labels, same rows, same order, full text in both.

    Returns ``{'rows': [[item, …], …], 'width': float, 'height': float}`` where each ``item`` is::

        {'i': int, 'label': str, 'lines': [str, …], 'x': float, 'y': float,
         'w': float, 'h': float, 'font_px': int, 'kind': 'home'|'chevron'}

    ``x``/``y``/``w``/``h`` are px on a ``width`` × ``height`` canvas (index 0 is the flat-backed
    home-plate, every other item a both-sides chevron). None-safe: empty / single-label handled;
    a single very long label caps at ``max_w`` with a reduced font (never ellipsised or clipped).
    """
    labels = [str(x) for x in (labels or []) if x is not None and str(x).strip() != '']
    if not labels:
        return {'rows': [], 'width': 0.0, 'height': 0.0}

    # text width available inside a max-width chevron (both notches + a little breathing pad)
    text_area = max(max_w - notch * 2 - pad, 20)

    def _wrap(words, font_px):
        """Greedily wrap ``words`` into lines each estimated to fit ``text_area`` px."""
        lines, cur = [], ''
        for w in words:
            if not cur:
                cur = w
            elif len(cur + ' ' + w) * font_px * 0.52 <= text_area:
                cur = cur + ' ' + w
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or ['']

    items = []
    for i, label in enumerate(labels):
        words = label.split() or ['']
        font_px = base_font_px
        lines = _wrap(words, font_px)                 # ≤2 lines emerge naturally at base font
        # if the text still needs more than 3 lines within max_w, shrink the font (12→8)
        while len(lines) > 3 and font_px > 8:
            font_px -= 1
            lines = _wrap(words, font_px)
        if len(lines) == 1:                           # single line → keep the label VERBATIM
            lines = [label.strip()]                   # (preserve exact text/spacing, no rewrap)
        longest_px = max((len(ln) for ln in lines), default=0) * font_px * 0.52
        w = max(min_w, min(max_w, longest_px + notch * 2 + pad))
        line_h = math.ceil(font_px * 1.25)
        h = pad + len(lines) * line_h + pad
        items.append({'i': i, 'label': label, 'lines': lines, 'font_px': font_px,
                      'w': w, 'h': h, 'kind': 'home' if i == 0 else 'chevron'})

    # flow left→right, wrapping to a new row when the next shape would exceed max_width_px
    rows, cur_row, x = [], [], 0.0
    for it in items:
        if cur_row and (x + it['w'] > max_width_px):
            rows.append(cur_row)
            cur_row, x = [], 0.0
        it['x'] = x
        cur_row.append(it)
        x += it['w'] + gap
    if cur_row:
        rows.append(cur_row)

    # uniform row height per row; stack rows top→bottom; total canvas = widest row × total height
    y, width = 0.0, 0.0
    for row in rows:
        row_h = max(it['h'] for it in row)
        row_w = sum(it['w'] for it in row) + gap * (len(row) - 1)
        width = max(width, row_w)
        for it in row:
            it['y'] = y
            it['h'] = row_h
        y += row_h + vgap
    height = (y - vgap) if rows else 0.0
    return {'rows': rows, 'width': width, 'height': height}


def top_wbs_name(wbs_id, wbs):
    """Name of the highest WBS ancestor of ``wbs_id`` (its top-level branch)."""
    seen = set()
    cur, last = wbs_id, None
    while cur and cur not in seen and cur in wbs:
        seen.add(cur)
        node = wbs[cur]
        if node.get('name'):
            last = node['name']
        parent = node.get('parent_object_id')
        if not parent or parent not in wbs:
            break
        cur = parent
    return last


def wbs_grouping(wbs):
    """Map each WBS id to its 'major branch' id, and list the branch ids in order.

    Adaptive so single-root projects still get a real breakdown: if the file has one
    top root, the major branches are that root's children; otherwise the roots
    themselves. Returns ``(group_of, branch_ids)`` where ``group_of[wbs_id]`` is the
    branch id its subtree belongs to.
    """
    children, roots = {}, []
    for oid, node in wbs.items():
        parent = node.get('parent_object_id')
        if parent and parent in wbs:
            children.setdefault(parent, []).append(oid)
        else:
            roots.append(oid)
    branch_ids = children[roots[0]] if (len(roots) == 1 and children.get(roots[0])) else roots

    group_of, seen = {}, set()

    def mark(oid, branch):
        if oid in seen:
            return
        seen.add(oid)
        group_of[oid] = branch
        for c in children.get(oid, []):
            mark(c, branch)

    for br in branch_ids:
        mark(br, br)
    for r in roots:                     # the single top root itself, if it holds activities
        group_of.setdefault(r, r)
    return group_of, branch_ids


def as_date(x):
    """Coerce a datetime/date/ISO-string to a date, or None."""
    from datetime import date, datetime
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    try:
        return datetime.fromisoformat(str(x)[:19]).date()
    except ValueError:
        return None
