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
