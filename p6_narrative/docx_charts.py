"""Self-contained chart SVGs for the Word (.docx) export, rasterised to PNG.

The screen/PDF report (``html.py``) draws its charts with CSS classes and theme
variables — great for a live page, useless as a standalone image. Word can only
embed a raster, so this module re-builds the same charts as *self-contained* SVGs
(root ``<svg>`` with an ``xmlns``, explicit width/height, fully inline styling and
an opaque white background) and hands them to the shared Chrome rasteriser
(``chart_png.render_svg_png``). When Chrome is unavailable every ``chart_png``
call returns ``None`` and the caller falls back to a table.

Nothing here imports ``html.py`` — the builders are ports, not wrappers — so the
module is parallel-safe and has no side effects on the live report.
"""
import io
import math
import re
import html as _h

from p6_narrative.chart_png import render_svg_png
from p6_narrative import wbs_chart


# ── local helpers (ports — must not import html.py) ───────────────────────────
def _esc(x):
    return _h.escape('' if x is None else str(x))


def _money(v):
    try:
        return f'{float(v):,.0f}'
    except (TypeError, ValueError):
        return _esc(v)


def _clip(name, n=20):
    name = '' if name is None else str(name)
    return name if len(name) <= n else name[:n - 1] + '…'


_FONT = 'font-family="Segoe UI,Arial,sans-serif"'


def _open(width, height):
    """Root <svg> with xmlns, explicit intrinsic size and an opaque white ground."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(width)}" '
            f'height="{int(height)}" viewBox="0 0 {int(width)} {int(height)}" {_FONT}>'
            f'<rect x="0" y="0" width="{int(width)}" height="{int(height)}" fill="#ffffff"/>')


# ── donut (port of html._value's donut) ───────────────────────────────────────
_DONUT_PALETTE = ['#1f5fa8', '#c98a2b', '#7a5aa6', '#4b9d6e', '#a35d5d', '#5a8fb0']


def donut_svg(value_payload):
    """Cost-by-branch donut with a legend. '' when there are no rows."""
    rows = (value_payload or {}).get('rows') or []
    if not rows:
        return ''
    W, H = 380, max(200, 40 + len(rows) * 20)
    cx, cy, r, sw = 100, 100, 60, 30
    circ = 2 * math.pi * r
    off, segs = 0.0, ''
    for i, rw in enumerate(rows):
        col = _DONUT_PALETTE[i % len(_DONUT_PALETTE)]
        seg = circ * (rw.get('pct') or 0) / 100.0
        segs += (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{col}" '
                 f'stroke-width="{sw}" stroke-dasharray="{seg:.1f} {circ - seg:.1f}" '
                 f'stroke-dashoffset="{-off:.1f}"/>')
        off += seg
    donut = (f'<g transform="rotate(-90 {cx} {cy})">{segs}</g>'
             f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" font-size="17" '
             f'font-weight="700" fill="#1a1d21">{_money((value_payload or {}).get("total"))}</text>'
             f'<text x="{cx}" y="{cy + 15}" text-anchor="middle" font-size="10" '
             f'fill="#8a9099">total</text>')
    legend, ly = '', 40
    for i, rw in enumerate(rows):
        col = _DONUT_PALETTE[i % len(_DONUT_PALETTE)]
        legend += (f'<rect x="210" y="{ly - 10}" width="12" height="12" rx="2" fill="{col}"/>'
                   f'<text x="228" y="{ly}" font-size="11" fill="#1a1d21">'
                   f'{_esc(_clip(rw.get("name"), 22))} '
                   f'<tspan fill="#8a9099">{_esc(rw.get("pct"))}%</tspan></text>')
        ly += 20
    return _open(W, H) + donut + legend + '</svg>'


# ── timeline (port of html._timeline) ─────────────────────────────────────────
def timeline_svg(timeline_payload):
    """Milestone / key-date timeline. '' when there are no items."""
    items = (timeline_payload or {}).get('items') or []
    if not items:
        return ''
    n = len(items)
    W, H, y = max(130 * n, 400), 150, 75
    x0, x1 = 30, W - 30
    step = (x1 - x0) / max(n - 1, 1)
    body = (f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="#3487ae" '
            f'stroke-width="2"/>')
    for i, it in enumerate(items):
        x = x0 + i * step
        up = (i % 2 == 0)
        col = '#3487ae' if it.get('milestone') else '#c98a2b'
        lab = (it.get('label') or '')[:18]
        body += (f'<circle cx="{x:.0f}" cy="{y}" r="5.5" fill="{col}"/>'
                 f'<text x="{x:.0f}" y="{(y - 14 if up else y + 26)}" text-anchor="middle" '
                 f'font-size="9.5" fill="#1a1d21">{_esc(lab)}</text>'
                 f'<text x="{x:.0f}" y="{(y - 28 if up else y + 40)}" text-anchor="middle" '
                 f'font-size="9" fill="#8a9099">{_esc(it.get("date"))}</text>')
    return _open(W, H) + body + '</svg>'


# ── cost bars (port of html._costbars → SVG bar chart) ────────────────────────
def costbars_svg(costbars_payload):
    """Horizontal cost-share bars. '' when there are no rows."""
    rows = (costbars_payload or {}).get('rows') or []
    if not rows:
        return ''
    W = 560
    lab_w, row_h, top = 160, 34, 16
    track_x, track_r = lab_w, W - 70
    H = top + len(rows) * row_h + 8
    body = ''
    for i, rw in enumerate(rows):
        pct = rw.get('pct') or 0
        cy = top + i * row_h
        bar_y = cy + 6
        fill_w = max((track_r - track_x) * (pct / 100.0), 0)
        body += (f'<text x="{lab_w - 10}" y="{bar_y + 14}" text-anchor="end" '
                 f'font-size="11" fill="#1a1d21">{_esc(_clip(rw.get("name"), 22))}</text>'
                 f'<rect x="{track_x}" y="{bar_y}" width="{track_r - track_x}" height="18" '
                 f'rx="4" fill="#e3e8ee"/>'
                 f'<rect x="{track_x}" y="{bar_y}" width="{fill_w:.1f}" height="18" '
                 f'rx="4" fill="#3487ae"/>'
                 f'<text x="{track_r + 8}" y="{bar_y + 14}" font-size="11" '
                 f'fill="#8a9099">{_esc(pct)}%</text>')
    return _open(W, H) + body + '</svg>'


# ── WBS SmartArt (coloured org-chart; reuses wbs_chart geometry) ──────────────
_WBS_PALETTE = ['#1F4E79', '#2E75B6', '#4472C4', '#5B9BD5', '#DEEAF6']
_ACCENT = '#2E75B6'


def wbs_smartart_svg(node):
    """SmartArt 'Organization Chart' look: filled boxes with a per-depth blue
    palette and elbow connectors. '' on empty input."""
    if not node or (not node.get('name') and not (node.get('children'))):
        return ''
    root = wbs_chart._copy(node)          # never mutate the caller's tree
    wbs_chart._layout(root, 0, [0])
    nodes = []
    wbs_chart._collect(root, nodes)
    BOX_W, BOX_H = wbs_chart.BOX_W, wbs_chart.BOX_H
    X_STEP, Y_STEP, PAD = wbs_chart.X_STEP, wbs_chart.Y_STEP, wbs_chart.PAD
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
        depth = int(n['_y'])
        fill = _WBS_PALETTE[min(depth, len(_WBS_PALETTE) - 1)]
        tcol = '#12303d' if depth >= len(_WBS_PALETTE) - 1 else '#ffffff'
        boxes.append(
            f'<g><rect x="{bx(n):.0f}" y="{by(n):.0f}" width="{BOX_W}" height="{BOX_H}" '
            f'rx="7" fill="{fill}" stroke="{_ACCENT}" stroke-width="1.2"/>'
            f'<text x="{cx:.0f}" y="{by(n) + BOX_H / 2 + 4:.0f}" text-anchor="middle" '
            f'fill="{tcol}" font-size="11.5" font-weight="600">'
            f'<title>{_esc(n.get("name"))}</title>{_esc(_clip(n.get("name")))}</text></g>')

    return (_open(width, height)
            + f'<g stroke="{_ACCENT}" stroke-width="1.3" fill="none" opacity="0.85">'
            + ''.join(conns) + '</g>' + ''.join(boxes) + '</svg>')


# ── sequence flow (coloured 'Continuous Block Process' chevrons) ──────────────
_SEQ_PALETTE = ['#1F4E79', '#2E75B6', '#4472C4', '#5B9BD5', '#41719C', '#8FAADC']


def sequence_flow_svg(front):
    """A continuous chevron flow of ``front['sequence']`` steps. '' on empty."""
    seq = (front or {}).get('sequence') or []
    if not seq:
        return ''
    BW, BH, TIP, GAP = 150, 56, 18, 6
    top = 16
    W = int(len(seq) * (BW + GAP) - GAP + TIP + 4)
    H = top + BH + 16
    body = ''
    for i, step in enumerate(seq):
        x = i * (BW + GAP)
        y = top
        col = _SEQ_PALETTE[i % len(_SEQ_PALETTE)]
        if i == 0:
            pts = (f'{x},{y} {x + BW - TIP},{y} {x + BW},{y + BH / 2:.0f} '
                   f'{x + BW - TIP},{y + BH} {x},{y + BH}')
        else:
            pts = (f'{x},{y} {x + BW - TIP},{y} {x + BW},{y + BH / 2:.0f} '
                   f'{x + BW - TIP},{y + BH} {x},{y + BH} {x + TIP},{y + BH / 2:.0f}')
        tx = x + (BW + (TIP if i else 0)) / 2
        body += (f'<polygon points="{pts}" fill="{col}"/>'
                 f'<text x="{tx:.0f}" y="{y + BH / 2 + 4:.0f}" text-anchor="middle" '
                 f'fill="#ffffff" font-size="11" font-weight="600">'
                 f'{_esc(_clip(step, 18))}</text>')
    return _open(W, H) + body + '</svg>'


# ── cash flow (monthly BAR chart — Ibrahim's comment: bars, not an S-curve) ────
def cashflow_bars_svg(cashflow_payload):
    """Planned cost per calendar month as vertical bars (matches the reference Word
    file's cash-flow histogram). '' when there is no monthly data."""
    months = (cashflow_payload or {}).get('monthly') or []
    if not months:
        return ''
    n = len(months)
    bw = 30 if n <= 16 else max(12, int(520 / n))
    gap = max(6, int(bw * 0.4))
    left, right, top, plot_h, bottom = 20, 16, 26, 210, 52
    W = left + right + n * (bw + gap)
    H = top + plot_h + bottom
    max_cost = max((m.get('cost') or 0) for m in months) or 1
    base_y = top + plot_h
    body = f'<text x="{left}" y="{top - 8}" font-size="11" font-weight="700" fill="#1F4E79">Planned cost per month</text>'
    for g in range(1, 5):                              # faint horizontal gridlines
        gy = base_y - plot_h * g / 4
        body += (f'<line x1="{left}" y1="{gy:.0f}" x2="{W - right}" y2="{gy:.0f}" '
                 f'stroke="#eef1f5" stroke-width="1"/>')
    body += (f'<line x1="{left}" y1="{base_y}" x2="{W - right}" y2="{base_y}" '
             f'stroke="#c9d6de" stroke-width="1.2"/>')
    show_every = 1 if n <= 13 else (2 if n <= 26 else 3)
    for i, m in enumerate(months):
        x = left + i * (bw + gap) + gap / 2
        h = plot_h * (m.get('cost') or 0) / max_cost
        y = base_y - h
        body += (f'<rect x="{x:.0f}" y="{y:.0f}" width="{bw}" height="{max(h, 0):.0f}" '
                 f'rx="2" fill="#2E75B6"/>')
        if i % show_every == 0:
            lx, ly = x + bw / 2, base_y + 12
            body += (f'<text x="{lx:.0f}" y="{ly:.0f}" text-anchor="end" font-size="8.5" '
                     f'fill="#5b6472" transform="rotate(-40 {lx:.0f} {ly:.0f})">'
                     f'{_esc(m.get("label"))}</text>')
    return _open(W, H) + body + '</svg>'


# ── dispatch → PNG ────────────────────────────────────────────────────────────
_BUILDERS = {
    'donut': donut_svg,
    'value': donut_svg,
    'timeline': timeline_svg,
    'costbars': costbars_svg,
    'wbs_smartart': wbs_smartart_svg,
    'sequence_flow': sequence_flow_svg,
    'cashflow': cashflow_bars_svg,
    'cashflow_bars': cashflow_bars_svg,
}

_DIMS = re.compile(r'<svg[^>]*\bwidth="(\d+)"[^>]*\bheight="(\d+)"')


def chart_png(kind, data, chrome):
    """Build the SVG for ``kind`` from ``data`` and rasterise it to PNG bytes.
    Returns None when the kind is unknown, the SVG is empty, or Chrome is missing.
    """
    builder = _BUILDERS.get(kind)
    if builder is None or not chrome:
        return None
    svg = builder(data)
    if not svg:
        return None
    m = _DIMS.search(svg)
    if not m:
        return None
    width, height = int(m.group(1)), int(m.group(2))
    return render_svg_png(svg, width, height, chrome)


def stream(png_bytes):
    """Wrap PNG bytes in a fresh BytesIO (rewound), for python-docx add_picture."""
    return io.BytesIO(png_bytes)
