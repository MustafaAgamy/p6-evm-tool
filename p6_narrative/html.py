"""Render a NarrativeDoc (dict) to HTML — used both for the on-screen tab and as
the source for the PDF export. Returns a self-contained fragment (a scoped <style>
plus a ``.bn-doc`` element); ``page_html`` wraps it as a full page for Chrome.

Charts are drawn as flowing HTML/SVG so they read in any project and stay light on
both app themes (the document renders as a light "paper" sheet, like Word).
"""
import html as _h


def _esc(x):
    return _h.escape('' if x is None else str(x))


def _chip(prov):
    label = {'auto': 'Auto · from your file', 'calendar': 'From the Calendar feature',
             'drafted': 'Drafted · editable', 'fill': 'You fill'}.get(prov, prov)
    return f'<span class="bn-chip bn-{prov}">{_esc(label)}</span>'


def _prose(p):
    out = ''.join(f'<p>{_esc(t)}</p>' for t in p.get('paragraphs', []))
    if p.get('bullets'):
        out += '<ul class="bn-bul">' + ''.join(f'<li>{_esc(b)}</li>' for b in p['bullets']) + '</ul>'
    return out


def _keyvals(p):
    rows = ''.join(f'<tr><td class="bn-k">{_esc(r["k"])}</td><td>{_esc(r["v"])}</td></tr>'
                   for r in p.get('rows', []))
    return f'<div class="bn-tw"><table class="bn-t">{rows}</table></div>'


def _table(p):
    cols = ''.join(f'<th>{_esc(c)}</th>' for c in p.get('columns', []))
    body = ''.join('<tr>' + ''.join(f'<td>{_esc(c)}</td>' for c in row) + '</tr>'
                   for row in p.get('rows', []))
    if not body:
        body = f'<tr><td colspan="{max(len(p.get("columns", [])),1)}" class="bn-empty">—</td></tr>'
    return f'<div class="bn-tw"><table class="bn-t"><tr>{cols}</tr>{body}</table></div>'


def _calendars(p):
    crows = ''.join(
        f'<tr><td>{_esc(c["name"])}</td><td>{_esc(c["working_days"])}</td>'
        f'<td>{_esc(c["shift"])}</td><td class="bn-num">{_esc(c["activities"])}</td></tr>'
        for c in p.get('calendars', []))
    cal = (f'<div class="bn-tw"><table class="bn-t"><tr><th>Calendar</th><th>Working days</th>'
           f'<th>Shift</th><th>Assigned</th></tr>{crows}</table></div>')
    hols = p.get('holidays', [])
    if hols:
        hrows = ''.join(
            f'<tr><td>{_esc(h.get("range"))}</td><td>{_esc(h.get("name"))}</td>'
            f'<td class="bn-num">{_esc(h.get("days"))}</td></tr>' for h in hols)
        cal += (f'<div class="bn-cap">Holidays &amp; shutdowns (named in Calendar Audit):</div>'
                f'<div class="bn-tw"><table class="bn-t"><tr><th>When</th><th>Name</th>'
                f'<th>Days</th></tr>{hrows}</table></div>')
    return cal


def _wbs(p):
    from p6_narrative.wbs_chart import org_chart_svg
    tree = p.get('tree') or []
    if not tree:
        return '<p class="bn-empty">No WBS in the file.</p>'
    root = tree[0]
    overview = {'name': root.get('name'),
                'children': [{'name': c.get('name')} for c in (root.get('children') or [])]}
    out = (f'<div class="bn-wbsblock"><div class="bn-wbstitle">{_esc(root.get("name"))} — Main WBS</div>'
           f'{org_chart_svg(overview)}</div>')
    for c in root.get('children') or []:            # each main branch → its own sub-WBS chart
        if c.get('children'):
            out += (f'<div class="bn-wbsblock"><div class="bn-wbstitle">{_esc(c.get("name"))} — sub-WBS</div>'
                    f'{org_chart_svg(c)}</div>')
    for extra in tree[1:]:                            # rare: extra roots
        out += (f'<div class="bn-wbsblock"><div class="bn-wbstitle">{_esc(extra.get("name"))}</div>'
                f'{org_chart_svg(extra)}</div>')
    return out


def _codes(p):
    cards = ''
    for t in p.get('tables', []):
        rows = ''.join(f'<tr><td class="bn-code">{_esc(r.get("code"))}</td>'
                       f'<td>{_esc(r.get("description"))}</td></tr>' for r in t.get('rows', []))
        cards += (f'<div class="bn-codecard"><h4>{_esc(t["dimension"])}</h4>'
                  f'<div class="bn-tw"><table class="bn-t"><tr><th>Code</th><th>Description</th></tr>'
                  f'{rows}</table></div></div>')
    return f'<div class="bn-codes">{cards or "<p class=bn-empty>No activity codes in the file.</p>"}</div>'


def _sequence(p):
    out = ''.join(f'<p>{_esc(t)}</p>' for t in p.get('paragraphs', []))
    for ch in p.get('charts', []):
        pkgs = ''
        for i, pk in enumerate(ch.get('packages', [])):
            steps = ''.join(f'<div class="bn-step">{_esc(s["name"])}</div>' for s in pk.get('steps', []))
            arrow = '' if i == 0 else '<div class="bn-arrow">→</div>'
            pkgs += (f'{arrow}<div class="bn-pkg"><div class="bn-pkgt">{_esc(pk["name"])}</div>'
                     f'<div class="bn-steps">{steps}</div></div>')
        cont = ''
        if ch.get('chart_count', 1) > 1:
            cont = (f'<div class="bn-cont">{ch.get("steps_shown")} of {ch.get("steps_total")} steps · '
                    f'continues on chart {min(ch["chart_index"]+1, ch["chart_count"])} of {ch["chart_count"]}</div>')
        out += (f'<div class="bn-chart"><div class="bn-charth">'
                f'<span class="bn-disc">{_esc(ch["discipline"])}</span>'
                f'<span class="bn-cn">chart {ch.get("chart_index",1)} of {ch.get("chart_count",1)}</span></div>'
                f'<div class="bn-flowscroll"><div class="bn-flow">{pkgs}</div></div>{cont}</div>')
    return out


def _costbars(p):
    rows = ''
    for r in p.get('rows', []):
        rows += (f'<div class="bn-bar"><span class="bn-bn">{_esc(r["name"])}</span>'
                 f'<span class="bn-track"><span class="bn-fill" style="width:{r["pct"]}%"></span></span>'
                 f'<span class="bn-bv">{r["pct"]}%</span></div>')
    return f'<div class="bn-bars">{rows}</div>'


def _cashflow(p):
    pts = p.get('points', [])
    if not pts:
        return '<p class="bn-empty">No cost loading in the file.</p>'
    w, h = 680, 200
    n = len(pts) - 1 or 1
    coords = [(40 + i * (w - 60) / n, h - 20 - (pt['pct'] / 100.0) * (h - 40))
              for i, pt in enumerate(pts)]
    line = ' '.join(f'{x:.1f},{y:.1f}' for x, y in coords)
    area = f'40,{h-20} ' + line + f' {coords[-1][0]:.1f},{h-20}'
    lx, ly = coords[-1]
    return (f'<div class="bn-tw"><svg class="bn-svg" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet">'
            f'<line x1="40" y1="{h-20}" x2="{w-20}" y2="{h-20}" class="bn-axis"/>'
            f'<line x1="40" y1="20" x2="40" y2="{h-20}" class="bn-axis"/>'
            f'<polygon points="{area}" class="bn-area"/>'
            f'<polyline points="{line}" class="bn-line"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" class="bn-dot"/>'
            f'<text x="36" y="24" text-anchor="end" class="bn-axl">100%</text>'
            f'<text x="36" y="{h-16}" text-anchor="end" class="bn-axl">0</text></svg></div>')


def _scope(p):
    out = f'<p>{_esc(p.get("intro", ""))}</p>' if p.get('intro') else ''
    for b in p.get('blocks', []):
        chips = ''.join(f'<span class="bn-pkgchip">{_esc(x)}</span>'
                        for x in (b.get('packages') or [])[:12])
        cost = f' · {b["cost"]:,.0f}' if b.get('cost') else ''
        out += (f'<div class="bn-disc"><div class="bn-disch">{_esc(b.get("discipline"))}'
                f'<span class="bn-discm">{b.get("activity_count", 0)} activities{_esc(cost)}</span></div>'
                f'<p>{_esc(b.get("paragraph", ""))}</p>'
                f'<div class="bn-pkgs">{chips}</div></div>')
    return out


_RENDER = {'prose': _prose, 'keyvals': _keyvals, 'table': _table, 'wbs': _wbs,
           'codes': _codes, 'sequence': _sequence, 'costbars': _costbars,
           'cashflow': _cashflow, 'calendars': _calendars, 'scope': _scope}


def _section(s):
    body = _calendars(s['payload']) if s['kind'] == 'table' and s['payload'].get('view') == 'calendars' \
        else _RENDER.get(s['kind'], lambda p: '')(s['payload'])
    note = f'<div class="bn-note">{_esc(s["note"])}</div>' if s.get('note') else ''
    edit = ' data-editable="1"' if s.get('editable') else ''
    return (f'<section class="bn-sec" data-num="{_esc(s["number"])}"{edit}>'
            f'<div class="bn-sh"><span class="bn-n">{_esc(s["number"])}</span>'
            f'<h2>{_esc(s["title"])}</h2>{_chip(s["provenance"])}</div>'
            f'{note}<div class="bn-body">{body}</div></section>')


def render_narrative_html(doc):
    meta = doc.get('meta', {})
    sections = ''.join(_section(s) for s in doc.get('sections', []))
    cover = (f'<div class="bn-cover"><div class="bn-kt">Detailed Baseline Narrative</div>'
             f'<h1>{_esc(meta.get("project_name","Project"))}</h1>'
             f'<div class="bn-gen">generated by nPace · data date {_esc(meta.get("data_date","—"))}</div></div>')
    return f'<style>{_CSS}</style><div class="bn-doc">{cover}{sections}</div>'


def page_html(doc):
    """Full standalone HTML page (for Chrome → PDF)."""
    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<style>body{margin:0;background:#fff}</style></head><body>'
            + render_narrative_html(doc) + '</body></html>')


_CSS = """
.bn-doc{background:#fff;color:#1a1d21;font-family:Georgia,'Times New Roman',serif;
  max-width:860px;margin:0 auto;padding:34px 46px 60px;line-height:1.6;font-size:15.5px}
.bn-doc h1,.bn-doc h2,.bn-doc h4{font-family:system-ui,'Segoe UI',Arial,sans-serif}
.bn-cover{text-align:center;border-bottom:2px solid #265f7e;padding-bottom:20px;margin-bottom:26px}
.bn-kt{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#265f7e;font-family:system-ui,sans-serif;font-weight:600}
.bn-cover h1{font-size:30px;font-weight:600;margin:10px 0 4px}
.bn-gen{font-size:12px;color:#8a9099;font-family:system-ui,sans-serif}
.bn-sec{margin:30px 0 0}
.bn-sh{display:flex;align-items:center;gap:11px;flex-wrap:wrap;margin-bottom:8px}
.bn-n{font-family:system-ui,sans-serif;font-size:12px;font-weight:700;color:#fff;background:#265f7e;min-width:26px;height:26px;padding:0 7px;border-radius:6px;display:flex;align-items:center;justify-content:center}
.bn-sh h2{font-size:20px;font-weight:600;margin:0;flex:1}
.bn-chip{font-family:system-ui,sans-serif;font-size:10.5px;font-weight:600;padding:3px 9px;border-radius:20px;white-space:nowrap}
.bn-auto{color:#2e7d52;background:#e6f2eb}.bn-calendar{color:#6a4fa3;background:#eee9f7}
.bn-drafted{color:#a96a14;background:#faf0df}.bn-fill{color:#5f6771;background:#edeff2}
.bn-note{font-family:system-ui,sans-serif;font-size:12px;color:#8a9099;margin:2px 0 8px}
.bn-body p{margin:0 0 10px}
.bn-bul{margin:4px 0 8px;padding-left:20px}
.bn-tw{overflow-x:auto;margin:6px 0}
.bn-t{border-collapse:collapse;width:100%;font-family:system-ui,sans-serif;font-size:13px;min-width:340px}
.bn-t th{background:#f4f6f9;text-align:left;font-weight:600;padding:8px 12px;border-bottom:1px solid #dadee4;font-size:12px}
.bn-t td{padding:7px 12px;border-bottom:1px solid #ebeef1;vertical-align:top}
.bn-k{color:#565c64;font-weight:500;white-space:nowrap;width:210px}
.bn-num{text-align:right;font-variant-numeric:tabular-nums}
.bn-code{font-family:'Cascadia Code',Consolas,monospace;font-size:12px;color:#1c4a63;white-space:nowrap}
.bn-empty{color:#8a9099;font-style:italic}
.bn-cap{font-family:system-ui,sans-serif;font-size:12px;color:#8a9099;margin:10px 0 4px}
.bn-wbs{border:1px solid #dadee4;border-radius:8px;overflow:hidden;font-family:system-ui,sans-serif;font-size:13.5px}
.bn-wr{padding:6px 14px;border-bottom:1px solid #ebeef1}
.bn-wr:last-child{border-bottom:none}
.bn-codes{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.bn-codecard h4{font-size:12.5px;color:#1c4a63;margin:0 0 6px}
.bn-chart{border:1px solid #dadee4;border-radius:10px;background:#f7f9fb;padding:14px;margin:10px 0}
.bn-charth{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:6px}
.bn-disc{font-family:system-ui,sans-serif;font-size:13px;font-weight:700;color:#fff;background:#3487ae;padding:4px 12px;border-radius:16px}
.bn-cn{font-family:system-ui,sans-serif;font-size:11px;font-weight:600;color:#1c4a63;background:#e7f0f5;padding:3px 10px;border-radius:16px}
.bn-flowscroll{overflow-x:auto;padding-bottom:6px}
.bn-flow{display:flex;align-items:stretch;gap:6px;min-width:min-content}
.bn-pkg{background:#fff;border:1px solid #dadee4;border-top:3px solid #3487ae;border-radius:8px;padding:9px 11px;min-width:128px;flex:0 0 auto}
.bn-pkgt{font-family:system-ui,sans-serif;font-size:12px;font-weight:700;margin-bottom:7px}
.bn-steps{display:flex;flex-direction:column;gap:5px}
.bn-step{font-family:system-ui,sans-serif;font-size:11.5px;padding-left:12px;position:relative}
.bn-step:before{content:"";position:absolute;left:0;top:6px;width:5px;height:5px;border-radius:50%;background:#3487ae}
.bn-arrow{display:flex;align-items:center;color:#3487ae;font-size:20px;flex:0 0 auto}
.bn-cont{font-family:system-ui,sans-serif;font-size:11.5px;color:#a96a14;background:#faf0df;border-radius:7px;padding:7px 11px;margin-top:10px}
.bn-bars{display:flex;flex-direction:column;gap:9px;font-family:system-ui,sans-serif}
.bn-bar{display:grid;grid-template-columns:170px 1fr 56px;gap:11px;align-items:center;font-size:12.5px}
.bn-bn{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bn-track{height:14px;background:#ebeef1;border-radius:4px;overflow:hidden}
.bn-fill{display:block;height:100%;background:#3487ae;border-radius:4px}
.bn-bv{text-align:right;font-variant-numeric:tabular-nums;color:#565c64}
.bn-svg{width:100%;min-width:520px;height:auto;font-family:system-ui,sans-serif}
.bn-axis{stroke:#dadee4;stroke-width:1}
.bn-area{fill:#e7f0f5}.bn-line{fill:none;stroke:#3487ae;stroke-width:2.5}
.bn-dot{fill:#3487ae}.bn-axl{fill:#8a9099;font-size:11px}
[data-editable] .bn-body{outline:1px dashed transparent}
.bn-disc{border:1px solid #dadee4;border-left:4px solid #3487ae;border-radius:8px;padding:11px 14px;margin:9px 0}
.bn-disch{font-family:system-ui,sans-serif;font-size:14px;font-weight:700;display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:5px}
.bn-discm{font-family:'Cascadia Code',Consolas,monospace;font-size:11px;color:#8a9099;font-weight:400}
.bn-disc p{margin:0 0 8px}
.bn-pkgs{display:flex;flex-wrap:wrap;gap:6px}
.bn-pkgchip{font-family:system-ui,sans-serif;font-size:11.5px;background:#f4f6f9;border:1px solid #ebeef1;border-radius:14px;padding:3px 10px;color:#565c64}
.bn-wbsblock{border:1px solid #dadee4;border-radius:10px;margin:10px 0;overflow:hidden}
.bn-wbstitle{background:#265f7e;color:#fff;font-family:system-ui,sans-serif;font-weight:600;font-size:13px;padding:8px 14px}
.bn-wbsblock .bn-tw{margin:0;padding:12px}
"""
