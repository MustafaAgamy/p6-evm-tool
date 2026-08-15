"""Render a WBS subtree as a SmartArt-style top-down org-chart (SVG string).

Pure string generation — no I/O. A simple tidy-tree layout: leaves take successive
x-slots, parents centre over their children, depth sets the row. Boxes are joined by
elbow connectors, like a Word hierarchy SmartArt. Generic for any tree; wide trees
scroll horizontally. The document renders as a light "paper" sheet, so colours are
fixed (matching the rest of html.py) rather than theme variables.
"""
import html as _h

BOX_W, BOX_H, X_STEP, Y_STEP, PAD = 138, 42, 156, 92, 16
ACCENT = '#3487ae'


def _esc(x):
    return _h.escape('' if x is None else str(x))


def _clip(name, n=20):
    name = '' if name is None else str(name)
    return name if len(name) <= n else name[:n - 1] + '…'


def _layout(node, depth, counter):
    kids = node.get('children') or []
    if not kids:
        node['_x'] = counter[0]
        counter[0] += 1
    else:
        for k in kids:
            _layout(k, depth + 1, counter)
        node['_x'] = sum(k['_x'] for k in kids) / len(kids)
    node['_y'] = depth


def _collect(node, out):
    out.append(node)
    for k in node.get('children') or []:
        _collect(k, out)


_TREEMAP_PALETTE = ['#3487ae', '#c98a2b', '#7a5aa6', '#4b9d6e', '#a35d5d', '#5a8fb0',
                    '#b0894a', '#6a6fae']


def annotated_org_chart_svg(root_name, branches, total_activities=None):
    """Overview org-chart where each branch box carries its activity count and cost
    share, with the heaviest branch shaded solid — from ``branches`` (branch_stats)."""
    if not branches:
        return ''
    n = len(branches)
    BW, BH, GAP = 152, 60, 12
    width = max(n * (BW + GAP) - GAP, 260) + 12
    height = 176
    max_pct = max((b.get('pct') or 0) for b in branches) or 1

    def cx(i):
        return 6 + i * (BW + GAP) + BW / 2

    root_cx = width / 2
    conns = [f'<path d="M{root_cx:.0f} 58 V80"/>']
    if n > 1:
        conns.append(f'<path d="M{cx(0):.0f} 80 H{cx(n-1):.0f}"/>')
    for i in range(n):
        conns.append(f'<path d="M{cx(i):.0f} 80 V96"/>')

    boxes = ''
    for i, b in enumerate(branches):
        left = 6 + i * (BW + GAP)
        pct = b.get('pct') or 0
        strong = pct >= max_pct and max_pct > 0
        fill = ACCENT if strong else 'var(--asoft, #e7f0f5)'
        tcol = '#ffffff' if strong else '#1a1d21'
        sub = '#ffffffcc' if strong else '#8a9099'
        barbg = '#ffffff44' if strong else '#e3e8ee'
        barfg = '#ffffff' if strong else ACCENT
        barw = max(120 * pct / 100.0, 1)
        boxes += (
            f'<g><rect x="{left}" y="96" width="{BW}" height="{BH}" rx="7" fill="{fill}" '
            f'stroke="{ACCENT}" stroke-width="1.2"/>'
            f'<text x="{left + BW/2:.0f}" y="118" text-anchor="middle" fill="{tcol}" '
            f'font-size="11.5" font-weight="600"><title>{_esc(b.get("name"))}</title>{_esc(_clip(b.get("name"), 18))}</text>'
            f'<text x="{left + BW/2:.0f}" y="133" text-anchor="middle" fill="{sub}" font-size="9.5">'
            f'{b.get("count", 0)} acts · {pct:g}%</text>'
            f'<rect x="{left + 16}" y="142" width="120" height="5" rx="2" fill="{barbg}"/>'
            f'<rect x="{left + 16}" y="142" width="{barw:.0f}" height="5" rx="2" fill="{barfg}"/></g>')

    root = (f'<rect x="{root_cx - 62:.0f}" y="16" width="124" height="42" rx="8" fill="{ACCENT}"/>'
            f'<text x="{root_cx:.0f}" y="35" text-anchor="middle" fill="#fff" font-size="12" font-weight="600">'
            f'{_esc(_clip(root_name, 20))}</text>'
            + (f'<text x="{root_cx:.0f}" y="50" text-anchor="middle" fill="#ffffffcc" font-size="9">'
               f'~{total_activities} activities</text>' if total_activities else ''))
    inner = min(int(width), 800)
    return (f'<div class="bn-tw"><svg viewBox="0 0 {int(width)} {height}" style="width:100%;'
            f'min-width:{inner}px;height:auto;font-family:system-ui,sans-serif">'
            f'<g stroke="{ACCENT}" stroke-width="1.3" fill="none" opacity="0.8">{"".join(conns)}</g>'
            f'{root}{boxes}</svg></div>')


def treemap_svg(rows):
    """A slice-and-dice treemap: each branch a full-height strip whose width = cost
    share. Generic — any number of branches, always readable."""
    rows = [r for r in (rows or []) if (r.get('pct') or 0) > 0]
    if not rows:
        return ''
    W, H = 600, 180
    x, segs = 0.0, ''
    for i, r in enumerate(rows):
        w = max(W * (r['pct'] / 100.0), 20)
        col = _TREEMAP_PALETTE[i % len(_TREEMAP_PALETTE)]
        label = ''
        if w >= 64:
            label = (f'<text x="{x + 10:.0f}" y="26" fill="#fff" font-size="12" font-weight="700">'
                     f'{_esc(_clip(r.get("name"), int(w / 8)))}</text>'
                     f'<text x="{x + 10:.0f}" y="44" fill="#ffffffdd" font-size="11">{r["pct"]:g}%</text>')
        elif w >= 30:
            label = f'<text x="{x + w/2:.0f}" y="{H/2:.0f}" text-anchor="middle" fill="#fff" font-size="10" transform="rotate(-90 {x + w/2:.0f} {H/2:.0f})">{r["pct"]:g}%</text>'
        segs += f'<rect x="{x:.1f}" y="0" width="{w - 1.5:.1f}" height="{H}" fill="{col}"/>{label}'
        x += w
    return (f'<div class="bn-tw"><svg viewBox="0 0 {W} {H}" style="width:100%;min-width:440px;'
            f'height:auto;font-family:system-ui,sans-serif">{segs}</svg></div>')


def _copy(n):
    return {'name': n.get('name'), 'children': [_copy(c) for c in (n.get('children') or [])]}


def org_chart_svg(root):
    """Return an SVG (wrapped in a scroll div) of ``root`` and its descendants."""
    root = _copy(root)          # never mutate the caller's tree (it's in the doc payload)
    _layout(root, 0, [0])
    nodes = []
    _collect(root, nodes)
    max_x = max((n['_x'] for n in nodes), default=0)
    max_d = max((n['_y'] for n in nodes), default=0)
    width = int(max_x * X_STEP + BOX_W + PAD * 2)
    height = int(max_d * Y_STEP + BOX_H + PAD * 2)

    def bx(n):
        return PAD + n['_x'] * X_STEP

    def by(n):
        return PAD + n['_y'] * Y_STEP

    conns, boxes = [], []
    for n in nodes:
        cx = bx(n) + BOX_W / 2
        for k in n.get('children') or []:
            kcx = bx(k) + BOX_W / 2
            mid = by(n) + BOX_H + (Y_STEP - BOX_H) / 2
            conns.append(f'<path d="M{cx:.0f} {by(n) + BOX_H:.0f} V{mid:.0f} '
                         f'H{kcx:.0f} V{by(k):.0f}"/>')
        is_root = n is root
        fill = ACCENT if is_root else '#ffffff'
        tcol = '#ffffff' if is_root else '#1a1d21'
        boxes.append(
            f'<g><rect x="{bx(n):.0f}" y="{by(n):.0f}" width="{BOX_W}" height="{BOX_H}" '
            f'rx="7" fill="{fill}" stroke="{ACCENT}" stroke-width="1.2"/>'
            f'<text x="{cx:.0f}" y="{by(n) + BOX_H / 2 + 4:.0f}" text-anchor="middle" '
            f'fill="{tcol}" font-size="11.5" font-weight="600">'
            f'<title>{_esc(n.get("name"))}</title>{_esc(_clip(n.get("name")))}</text></g>')

    inner = min(width, 760)
    return (f'<div class="bn-tw"><svg viewBox="0 0 {width} {height}" '
            f'style="width:100%;min-width:{inner}px;height:auto;font-family:system-ui,sans-serif">'
            f'<g stroke="{ACCENT}" stroke-width="1.3" fill="none" opacity="0.8">{"".join(conns)}</g>'
            f'{"".join(boxes)}</svg></div>')
