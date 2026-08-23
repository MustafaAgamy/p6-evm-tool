"""Compose the selected dashboard components into outputs.

Screen == PDF == Excel: the client posts the exact ``composition`` it renders on
screen, and these functions format it — the PDF via HTML→Chrome, the Excel via the
zero-dependency writer. Both read the SAME structured payloads, so the three outputs
never diverge. No feature calculation happens here.

``composition`` = {
    'header': {'title', 'subtitle', 'logo_left'?, 'logo_right'?},
    'components': [{'id','type','title','source','size', 'payload': {'type','data'}}],
}
"""

import html as _html

from p6_dashboard.xlsx_dashboard import write_dashboard_xlsx  # noqa: F401  (re-export for server)

_STATUS = {'good': 's-good', 'warn': 's-warn', 'bad': 's-bad', 'neutral': 's-neutral'}


def _e(s):
    return _html.escape('' if s is None else str(s))


def _status_cls(s):
    return _STATUS.get(s, 's-neutral')


# ── per-type body renderers (mirror ui/modules/dashboard.js) ────────────────

def _body(comp):
    payload = comp.get('payload') or {}
    data = payload.get('data') or {}
    t = comp.get('type') or payload.get('type')
    fn = _RENDERERS.get(t)
    if not fn:
        return '<div class="empty">—</div>'
    try:
        return fn(data)
    except Exception:
        return '<div class="empty">No data available</div>'


def _r_kpi(d):
    trend = d.get('trend')
    tr = f'<span class="trend">{_e(trend)}</span>' if trend else ''
    return (f'<div class="kpi-val {_status_cls(d.get("status"))}">{_e(d.get("value"))}{tr}</div>'
            f'<div class="kpi-note">{_e(d.get("note"))}</div>')


def _r_score(d):
    val = d.get('value') or 0
    return (f'<div class="score-row">{_gauge(val, _status_cls(d.get("status")))}'
            f'<div><div class="score-band">{_e(d.get("band"))}</div>'
            f'<div class="kpi-note">{_e(d.get("detail"))}</div></div></div>')


def _r_status(d):
    return (f'<div class="status-lbl {_status_cls(d.get("status"))}">{_e(d.get("label"))}</div>'
            f'<div class="kpi-note">{_e(d.get("note"))}</div>')


def _r_summary(d):
    cells = ''.join(
        f'<div class="stat"><div class="stat-l">{_e(s.get("label"))}</div>'
        f'<div class="stat-v {_status_cls(s.get("status"))}">{_e(s.get("value"))}</div></div>'
        for s in (d.get('stats') or []))
    return f'<div class="stats">{cells}</div>'


def _r_findings(d):
    rows = ''.join(
        f'<div class="find"><span class="dot {_status_cls(i.get("severity"))}"></span>'
        f'<div><div>{_e(i.get("text"))}</div>'
        f'<div class="src">{_e(i.get("source"))}</div></div></div>'
        for i in (d.get('items') or []))
    return f'<div class="finds">{rows}</div>' if rows else '<div class="empty">No findings</div>'


def _r_table(d):
    heads = ''.join(f'<th>{_e(h)}</th>' for h in (d.get('headers') or []))
    body = ''.join('<tr>' + ''.join(f'<td>{_e(c)}</td>' for c in row) + '</tr>'
                   for row in (d.get('rows') or []))
    if not body:
        return '<div class="empty">No rows</div>'
    return f'<table class="tbl"><thead><tr>{heads}</tr></thead><tbody>{body}</tbody></table>'


def _r_chart(d):
    kind = d.get('kind')
    if kind == 'bars':
        return _bars(d)
    if kind == 'grouped':
        return _grouped(d)
    if kind == 'line':
        return _line(d)
    return '<div class="empty">—</div>'


def _r_text(d):
    return f'<div class="usertext">{_e(d.get("text"))}</div>'


def _r_image(d):
    src = d.get('src') or ''
    if not src.startswith('data:'):
        return '<div class="empty">No image</div>'
    return f'<img class="userimg" src="{src}" alt="">'


_RENDERERS = {
    'kpi': _r_kpi, 'score': _r_score, 'status': _r_status, 'summary': _r_summary,
    'findings': _r_findings, 'table': _r_table, 'chart': _r_chart, 'trend': _r_chart,
    'text': _r_text, 'image': _r_image,
}


# ── SVG chart builders (mirror the mockup) ──────────────────────────────────

def _bars(d):
    rows = d.get('rows') or []
    mx = max([abs(r.get('value') or 0) for r in rows] + [1])
    out = []
    for r in rows:
        pct = min(100, 100 * abs(r.get('value') or 0) / mx)
        disp = r.get('display') if r.get('display') is not None else r.get('value')
        color = r.get('color') or '#3b6fa8'
        out.append(f'<div class="barrow"><div class="barlbl">{_e(r.get("label"))}</div>'
                   f'<div class="track"><div class="fill" style="width:{pct:.1f}%;background:{color}"></div></div>'
                   f'<div class="barval">{_e(disp)}</div></div>')
    return ''.join(out)


def _grouped(d):
    labels = d.get('labels') or []
    groups = d.get('groups') or []
    n = len(labels)
    W, H, padL, padB, padT = 300, 150, 24, 24, 8
    allv = [v for g in groups for v in (g.get('values') or [])] + [1]
    mx = max(abs(v) for v in allv)
    if n == 0 or not groups:
        return '<div class="empty">—</div>'
    bw = (W - padL - 6) / n
    gap = bw * 0.15
    slot = (bw - gap * 2) / max(1, len(groups))
    yb = lambda v: (H - padB) - (H - padB - padT) * (abs(v) / mx)
    bars = []
    for i in range(n):
        x0 = padL + bw * i + gap
        for gi, g in enumerate(groups):
            vals = g.get('values') or []
            v = vals[i] if i < len(vals) else 0
            x = x0 + slot * gi
            bars.append(f'<rect x="{x:.1f}" y="{yb(v):.1f}" width="{slot * 0.86:.1f}" '
                        f'height="{(H - padB) - yb(v):.1f}" fill="{g.get("color") or "#3b6fa8"}"></rect>')
    labs = ''.join(f'<text x="{padL + bw * i + bw / 2:.1f}" y="{H - 8}" font-size="7" '
                   f'fill="#64748b" text-anchor="middle">{_e(labels[i])}</text>' for i in range(n))
    axis = f'<line x1="{padL}" y1="{H - padB}" x2="{W - 2}" y2="{H - padB}" stroke="#b7c5d8"></line>'
    leg = ''.join(f'<span><i style="background:{g.get("color") or "#3b6fa8"}"></i>{_e(g.get("name"))}</span>'
                  for g in groups)
    return (f'<svg width="100%" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet">'
            f'{axis}{"".join(bars)}{labs}</svg><div class="legend">{leg}</div>')


def _line(d):
    series = d.get('series') or []
    if not series:
        return '<div class="empty">—</div>'
    n = max((len(s.get('points') or []) for s in series), default=0)
    if n < 2:
        return '<div class="empty">—</div>'
    W, H, pad = 280, 120, 22
    ymax = d.get('y_max') or max((max(s.get('points') or [0]) for s in series), default=100) or 100
    x = lambda i: pad + (W - pad - 6) * (i / (n - 1))
    y = lambda p: H - 18 - (H - 30) * (min(p, ymax) / ymax)
    axes = (f'<line x1="{pad}" y1="{H - 18}" x2="{W - 4}" y2="{H - 18}" stroke="#b7c5d8"></line>'
            f'<line x1="{pad}" y1="6" x2="{pad}" y2="{H - 18}" stroke="#b7c5d8"></line>')
    lines = []
    for s in series:
        pts = ' '.join(f'{x(i):.1f},{y(p):.1f}' for i, p in enumerate(s.get('points') or []))
        dash = f' stroke-dasharray="{s["dash"]}"' if s.get('dash') else ''
        lines.append(f'<polyline points="{pts}" fill="none" stroke="{s.get("color") or "#3b6fa8"}" '
                     f'stroke-width="2"{dash} stroke-linejoin="round"></polyline>')
    leg = ''.join(f'<span><i style="background:{s.get("color") or "#3b6fa8"}"></i>{_e(s.get("name"))}</span>'
                  for s in series)
    return (f'<svg width="100%" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet">'
            f'{axes}{"".join(lines)}</svg><div class="legend">{leg}</div>')


def _gauge(score, cls):
    import math
    R = 30
    C = 2 * math.pi * R
    off = C * (1 - (score or 0) / 100)
    return (f'<svg width="80" height="80" viewBox="0 0 80 80" class="{cls}">'
            f'<circle cx="40" cy="40" r="{R}" fill="none" stroke="#e6ebf2" stroke-width="9"></circle>'
            f'<circle cx="40" cy="40" r="{R}" fill="none" stroke="currentColor" stroke-width="9" '
            f'stroke-linecap="round" stroke-dasharray="{C:.1f}" stroke-dashoffset="{off:.1f}" '
            f'transform="rotate(-90 40 40)"></circle>'
            f'<text x="40" y="46" text-anchor="middle" font-size="20" font-weight="800" '
            f'fill="currentColor">{int(round(score or 0))}</text></svg>')


# ── document ────────────────────────────────────────────────────────────────

def _logos(header, side):
    """Render one side's logo group from the new header model (list of {src,size}),
    falling back to the legacy single logo_left/logo_right scalar."""
    arr = header.get('logos_' + side)
    if not arr:
        legacy = header.get('logo_' + side)
        arr = [{'src': legacy, 'size': 'm'}] if legacy else []
    imgs = ''.join(
        f'<img class="logo sz-{lg.get("size", "m")}" src="{lg.get("src")}" alt="">'
        for lg in arr if str(lg.get('src') or '').startswith('data:'))
    return f'<div class="logos logos-{side}">{imgs}</div>'


def render_dashboard_html(composition):
    header = composition.get('header') or {}
    comps = composition.get('components') or []
    panels = []
    for c in comps:
        span = ' span2' if (c.get('size') == 2) else ''
        panels.append(
            f'<section class="panel{span}"><div class="p-head">{_e(c.get("title"))}</div>'
            f'<div class="p-body">{_body(c)}</div></section>')
    return _DOC.format(
        title=_e(header.get('title') or 'Project Dashboard'),
        subtitle=_e(header.get('subtitle') or ''),
        tsz=_e(header.get('title_size') or 'm'),
        ssz=_e(header.get('sub_size') or 'm'),
        logo_left=_logos(header, 'left'),
        logo_right=_logos(header, 'right'),
        panels=''.join(panels) or '<div class="empty">No components selected.</div>',
    )


_DOC = '''<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: A4 landscape; margin: 12mm; }}
* {{ box-sizing: border-box; }}
body {{ font: 11px/1.4 -apple-system,"Segoe UI",Roboto,Arial,sans-serif; color:#1e293b; margin:0; }}
.titleband {{ display:flex; align-items:center; gap:14px; border:1px solid #b7c5d8; border-radius:5px;
  padding:9px 14px; margin-bottom:12px; background:linear-gradient(180deg,#d6e2f2,#fff); }}
.titleband .ttl {{ flex:1; text-align:center; }}
.titleband .t {{ font-weight:800; color:#1f3c66; }}
.titleband .t.tsz-s {{ font-size:13px; }} .titleband .t.tsz-m {{ font-size:16px; }} .titleband .t.tsz-l {{ font-size:20px; }} .titleband .t.tsz-xl {{ font-size:25px; }}
.titleband .s {{ color:#5d6b80; margin-top:2px; }}
.titleband .s.ssz-s {{ font-size:10px; }} .titleband .s.ssz-m {{ font-size:11px; }} .titleband .s.ssz-l {{ font-size:13px; }} .titleband .s.ssz-xl {{ font-size:16px; }}
.logos {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
.logo {{ object-fit:contain; }}
.logo.sz-s {{ max-height:28px; max-width:64px; }} .logo.sz-m {{ max-height:42px; max-width:96px; }} .logo.sz-l {{ max-height:60px; max-width:140px; }} .logo.sz-xl {{ max-height:84px; max-width:190px; }}
.grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:9px; }}
.panel {{ border:1px solid #b7c5d8; border-radius:5px; overflow:hidden; break-inside:avoid; }}
.panel.span2 {{ grid-column:span 2; }}
.p-head {{ background:linear-gradient(180deg,#d6e2f2,#c4d6ec); color:#1f3c66; font-weight:700;
  font-size:11px; text-align:center; padding:5px; border-bottom:1px solid #b7c5d8; }}
.p-body {{ padding:10px 12px; }}
.kpi-val {{ font-size:22px; font-weight:800; }} .kpi-note {{ font-size:10px; color:#5d6b80; margin-top:4px; }}
.trend {{ font-size:10px; margin-left:6px; }}
.s-good {{ color:#2e8b45; }} .s-warn {{ color:#c47d16; }} .s-bad {{ color:#c0392b; }} .s-neutral {{ color:#1e293b; }}
.score-row {{ display:flex; align-items:center; gap:12px; }} .score-band {{ font-weight:700; font-size:12px; }}
.status-lbl {{ font-size:15px; font-weight:800; }}
.stats {{ display:grid; grid-template-columns:repeat(2,1fr); gap:8px; }}
.stat-l {{ font-size:9px; text-transform:uppercase; letter-spacing:.4px; color:#5d6b80; }}
.stat-v {{ font-size:15px; font-weight:800; }}
.finds .find {{ display:flex; gap:8px; padding:5px 0; border-bottom:1px solid #eef2f7; font-size:10.5px; }}
.dot {{ width:8px; height:8px; border-radius:50%; margin-top:4px; flex:none; background:currentColor; }}
.find .src {{ color:#93a0b3; font-size:9px; }}
.tbl {{ width:100%; border-collapse:collapse; font-size:10px; }}
.tbl th,.tbl td {{ border:1px solid #e2e8f0; padding:3px 6px; text-align:left; }}
.tbl th {{ background:#eef2f7; font-weight:700; }}
.barrow {{ display:grid; grid-template-columns:90px 1fr 56px; align-items:center; gap:8px; margin:6px 0; font-size:10.5px; }}
.barlbl {{ color:#5d6b80; }} .track {{ height:10px; background:#e6ebf2; border-radius:2px; overflow:hidden; }}
.fill {{ height:100%; border-radius:2px; }} .barval {{ text-align:right; }}
.legend {{ display:flex; gap:11px; flex-wrap:wrap; font-size:9px; color:#5d6b80; margin-top:6px; justify-content:center; }}
.legend i {{ width:9px; height:9px; border-radius:2px; display:inline-block; margin-right:4px; }}
.usertext {{ font-size:11px; line-height:1.5; }} .userimg {{ max-width:100%; border-radius:4px; }}
.empty {{ color:#93a0b3; font-size:11px; text-align:center; padding:10px; }}
svg {{ display:block; }}
</style></head><body>
<div class="titleband">{logo_left}<div class="ttl"><div class="t tsz-{tsz}">{title}</div><div class="s ssz-{ssz}">{subtitle}</div></div>{logo_right}</div>
<div class="grid">{panels}</div>
</body></html>'''
