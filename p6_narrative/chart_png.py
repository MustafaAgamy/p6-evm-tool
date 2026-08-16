"""Rasterise a chart SVG to PNG bytes via headless Chrome, so the Word export can
embed real graphs (not just tables). Chrome is the same dependency the PDF export
already uses; when it isn't available the caller falls back to a table. Nothing here
is project-specific — it renders whatever SVG it's given.
"""
import os
import subprocess
import tempfile


def render_svg_png(svg, width, height, chrome=None):
    """Return PNG bytes for ``svg`` rendered at ``width``x``height``, or None if Chrome
    is unavailable or the render fails (caller should fall back)."""
    if not chrome or not svg:
        return None
    html = ('<!doctype html><html><head><meta charset="utf-8">'
            '<style>html,body{margin:0;padding:0;background:#fff}</style></head>'
            f'<body>{svg}</body></html>')
    tmp_html = tmp_png = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as f:
            f.write(html)
            tmp_html = f.name
        tmp_png = tmp_html[:-5] + '.png'
        subprocess.run([
            chrome, '--headless', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
            '--force-device-scale-factor=2', f'--window-size={width},{height}',
            f'--screenshot={tmp_png}', f'file:///{tmp_html.replace(os.sep, "/")}',
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        with open(tmp_png, 'rb') as f:
            return f.read()
    except Exception:
        return None
    finally:
        for path in (tmp_html, tmp_png):
            try:
                if path and os.path.isfile(path):
                    os.unlink(path)
            except OSError:
                pass


def cashflow_svg(points, width=760, height=320):
    """Self-contained (inline-styled) baseline S-curve SVG for the Word image."""
    if not points:
        return None
    n = len(points) - 1 or 1
    left, right, top, bot = 56, 20, 24, 42

    def px(i):
        return left + i * (width - left - right) / n

    def py(pct):
        return (height - bot) - (pct / 100.0) * (height - bot - top)

    line = ' '.join(f'{px(i):.1f},{py(p["pct"]):.1f}' for i, p in enumerate(points))
    area = f'{px(0):.1f},{height - bot:.1f} ' + line + f' {px(n):.1f},{height - bot:.1f}'
    grid = ylab = ''
    for g in (0, 25, 50, 75, 100):
        y = py(g)
        grid += f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#e6e9ee"/>'
        ylab += (f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" font-size="12" '
                 f'fill="#8a9099">{g}%</text>')
    xlab = ''
    for i in sorted({0, n // 2, n}):
        d = str(points[i].get('date', ''))[:7]
        xlab += (f'<text x="{px(i):.1f}" y="{height - bot + 20:.1f}" text-anchor="middle" '
                 f'font-size="12" fill="#8a9099">{d}</text>')
    lx, ly = px(n), py(points[-1]['pct'])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" font-family="Segoe UI,Arial,sans-serif">'
            f'<rect width="{width}" height="{height}" fill="#ffffff"/>{grid}'
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bot}" stroke="#c9ced6"/>'
            f'<line x1="{left}" y1="{height - bot}" x2="{width - right}" y2="{height - bot}" stroke="#c9ced6"/>'
            f'<polygon points="{area}" fill="#e7f0f5"/>'
            f'<polyline points="{line}" fill="none" stroke="#265f7e" stroke-width="3"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="5" fill="#265f7e"/>{ylab}{xlab}'
            f'<text x="{left}" y="15" font-size="13" font-weight="bold" fill="#1a1d21">'
            f'Baseline S-curve — cumulative planned %</text></svg>')
