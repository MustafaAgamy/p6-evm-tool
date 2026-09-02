"""Consultant-grade report for the Baseline Revision Comparison.

Renders the report dict (from ``compare.build_report``) into a single professional
document — Executive Summary, Revision Overview, Milestone Comparison, Critical Path
Comparison, Major Sequence Changes, Major Logic Changes, WBS/Scope Changes, the
Change Register and the Detailed Change Analysis. Uses the shared ``--rpt-*`` theme
tokens so the on-screen preview and the exported PDF look identical across all six
appearance modes (report_theme), and so every future report stays visually consistent.
"""
import html as _html
import report_theme


def _e(v):
    return _html.escape(str(v)) if v is not None else ''


def _sev_cls(sev):
    return {'crit': 'bad', 'hi': 'warn', 'med': 'accent', 'low': 'muted'}.get(sev, 'muted')


def _sev_label(sev):
    return {'crit': 'Critical', 'hi': 'High', 'med': 'Review', 'low': 'Info'}.get(sev, sev)


# ── sections ─────────────────────────────────────────────────────────────────

def _header(report, meta):
    r0, r1 = report['rev0'], report['rev1']
    date = (meta or {}).get('report_date', '')
    return f'''<div class="rh">
      <div><h1>Baseline Revision Comparison</h1>
        <div class="meta">Rev.00 <b>{_e(r0.get('file') or '—')}</b> &nbsp;→&nbsp; Rev.01 <b>{_e(r1.get('file') or '—')}</b></div></div>
      <div class="rhr"><div class="meta">Planning &amp; schedule review</div><div class="meta">{_e(date)}</div></div>
    </div>'''


def _overview(report):
    r0, r1 = report['rev0'], report['rev1']
    warn = ''
    if report.get('warnings'):
        warn = '<div class="warns">' + ''.join(f'<div class="warn">⚠ {_e(w)}</div>' for w in report['warnings']) + '</div>'
    def row(lbl, a, b):
        return f'<tr><td class="k">{_e(lbl)}</td><td>{_e(a)}</td><td>{_e(b)}</td></tr>'
    return f'''<table class="ov"><thead><tr><th></th><th>Rev.00 · Original</th><th>Rev.01 · Revised</th></tr></thead><tbody>
      {row('File', r0.get('file'), r1.get('file'))}
      {row('Activities', r0.get('activities'), r1.get('activities'))}
      {row('Data date', r0.get('data_date'), r1.get('data_date'))}
      {row('Governing finish', r0.get('finish'), r1.get('finish'))}
    </tbody></table>{warn}'''


def _kpis(report):
    s = report['summary']
    def sgn(n, unit=''):
        if n is None:
            return '—'
        return f"{'+' if n > 0 else ''}{n}{unit}"
    tiles = [
        ('Activities', f"{s['activities0']}→{s['activities1']}", f"{sgn(s['net'])} net"),
        ('New', s['added'], 'added in Rev.01'),
        ('Removed', s['removed'], 'not in Rev.01'),
        ('Modified', s['modified'], f"+{s['id_changes']} ID changes"),
        ('Duration', sgn(s.get('duration_change_wd'), ' wd'), 'critical-path length'),
        ('Finish', report['rev1'].get('finish') or '—', sgn(s.get('finish_shift_days'), ' days')),
    ]
    cells = ''.join(f'<div class="kpi"><div class="kk">{_e(k)}</div><div class="kv">{_e(v)}</div><div class="kd">{_e(d)}</div></div>'
                    for k, v, d in tiles)
    return f'<div class="kpis">{cells}</div>'


def _profile(report):
    prof = report.get('profile') or []
    mx = max([p['count'] for p in prof] + [1])
    rows = ''.join(
        f'''<div class="pf"><div class="pfl">{_e(p['label'])}</div>
          <div class="pft"><i style="width:{round(p['count'] / mx * 100)}%;background:{_e(p['color'])}"></i></div>
          <div class="pfv">{p['count']}</div></div>''' for p in prof)
    return f'<div class="profile">{rows}</div>'


def _findings(report):
    out = []
    for f in report.get('findings', []):
        out.append(f'''<div class="find {_sev_cls(f['severity'])}">
          <div class="ft">{_e(f['title'])} <span class="tag {_sev_cls(f['severity'])}">{_sev_label(f['severity'])}</span></div>
          <div class="fb">{_e(f.get('body'))}</div>
          <div class="flow"><span>Change detected</span><b>→</b><span>{_e(f.get('flow_impact') or 'Potential schedule impact')}</span><b>→</b><span>Planning review</span></div>
        </div>''')
    return ''.join(out) or '<p class="muted">No material changes detected between the two revisions.</p>'


def _milestones(report):
    rows = ''
    for m in report.get('milestones', []):
        kind = {'delayed': 'bad', 'advanced': 'good', 'unchanged': 'muted', 'new': 'accent', 'removed': 'warn'}.get(m['kind'], 'muted')
        chg = (f"{'+' if (m.get('change_days') or 0) > 0 else ''}{m['change_days']} d" if m.get('change_days') is not None
               else m['kind'].capitalize())
        rows += f'''<tr><td class="k">{_e(m['name'])}</td><td>{_e(m.get('rev0') or '—')}</td>
          <td>{_e(m.get('rev1') or '—')}</td><td class="num">{_e(chg)}</td>
          <td><span class="tag {kind}">{m['kind'].capitalize()}</span></td></tr>'''
    if not rows:
        return '<p class="muted">No finish milestones found in the revisions.</p>'
    return f'''<table class="grid"><thead><tr><th>Milestone</th><th>Rev.00</th><th>Rev.01</th><th class="num">Change</th><th>Impact</th></tr></thead><tbody>{rows}</tbody></table>'''


def _chain(nodes):
    if not nodes:
        return '<div class="muted">No driving path available.</div>'
    parts = []
    for i, n in enumerate(nodes):
        cls = 'enter' if n.get('state') == 'enter' else 'leave' if n.get('state') == 'leave' else ''
        parts.append(f'<span class="cn {cls}">{_e(n["name"])}</span>')
        if i < len(nodes) - 1:
            parts.append('<b class="ar">→</b>')
    return '<div class="chain">' + ''.join(parts) + '</div>'


def _critpath(report):
    cp = report.get('critical_path') or {}
    lc = cp.get('length_change_wd')
    sub = (f"Rev.01 critical path is {'+' if (lc or 0) >= 0 else ''}{lc} working days {'longer' if (lc or 0) >= 0 else 'shorter'}."
           if lc is not None else '')
    entered = ', '.join(e['name'] for e in cp.get('entered', [])) or '—'
    left = ', '.join(e['name'] for e in cp.get('left', [])) or '—'
    return f'''<p class="sub">{_e(sub)}</p>
      <div class="cprow"><div class="cplab">Rev.00</div>{_chain(cp.get('rev0'))}</div>
      <div class="cprow"><div class="cplab r1">Rev.01</div>{_chain(cp.get('rev1'))}</div>
      <table class="grid mt"><tbody>
        <tr><td class="k">Entered critical path ({len(cp.get('entered', []))})</td><td>{_e(entered)}</td></tr>
        <tr><td class="k">Left critical path ({len(cp.get('left', []))})</td><td>{_e(left)}</td></tr>
      </tbody></table>'''


def _sequences(report):
    seqs = report.get('sequence') or []
    if not seqs:
        return '<p class="muted">No execution-order reversals detected from the logic.</p>'
    out = []
    for s in seqs:
        out.append(f'''<div class="seqcard">
          <div class="ft">{_e(s['a_name'])} re-sequenced relative to {_e(s['b_name'])}</div>
          <div class="seqline"><span class="k">Rev.00</span> {' → '.join(_e(x) for x in s.get('chain0', []))}</div>
          <div class="seqline"><span class="k r1">Rev.01</span> {' → '.join(_e(x) for x in s.get('chain1', []))}</div>
          <div class="fb">Was planned <b>{_e(s['rev0'])}</b>; now <b>{_e(s['rev1'])}</b>. Flagged for review, not marked incorrect.</div>
        </div>''')
    return ''.join(out)


def _logic(report):
    rows = ''
    for row in report.get('register', []):
        if row['change_type'] != 'logic':
            continue
        rows += f'''<tr><td class="mono">{_e(row.get('orig_id') or row['activity_id'])}</td><td>{_e(row['activity_name'])}</td>
          <td>{_e(row['rev0'])}</td><td>{_e(row['rev1'])}</td><td>{_e(row['change'])}</td>
          <td><span class="tag {_sev_cls(row['severity'])}">{_sev_label(row['severity'])}</span></td></tr>'''
    if not rows:
        return '<p class="muted">No relationship/logic changes on matched activities.</p>'
    return f'''<table class="grid"><thead><tr><th>Activity</th><th>Name</th><th>Rev.00</th><th>Rev.01</th><th>Change</th><th>Severity</th></tr></thead><tbody>{rows}</tbody></table>'''


def _scope(report):
    s = report['summary']
    lg = s['logic']
    items = [
        ('New activities', s['added']), ('Removed activities', s['removed']),
        ('Identity (ID) changes', s['id_changes']), ('Moved between WBS', s.get('moved_wbs', 0)),
        ('WBS branches +/−/renamed', f"{s.get('wbs_added', 0)} / {s.get('wbs_removed', 0)} / {s.get('wbs_renamed', 0)}"),
        ('Relationships added / removed', f"{lg['added']} / {lg['removed']}"),
        ('Calendar reassignments', s.get('calendar_reassigned', 0)),
        ('Constraint changes', s.get('constraint_changes', 0)),
    ]
    cells = ''.join(f'<div class="scard"><div class="kk">{_e(k)}</div><div class="kv">{_e(v)}</div></div>' for k, v in items)
    out = [f'<div class="scope">{cells}</div>']

    reas = (report.get('calendar_changes') or {}).get('reassignments') or []
    if reas:
        rows = ''.join(
            f'<tr><td class="k">{_e(g["from"])}</td><td>{_e(g["to"])}</td>'
            f'<td>{(_e(str(g["from_wd"]) + "-day → " + str(g["to_wd"]) + "-day") if g.get("from_wd") is not None and g.get("to_wd") is not None else "—")}</td>'
            f'<td class="num">{g["count"]}</td></tr>' for g in reas)
        out.append('<h3 style="margin-top:12px">Calendar reassignments</h3>'
                   '<table class="grid"><thead><tr><th>From</th><th>To</th><th>Workweek</th><th class="num">Activities</th></tr></thead>'
                   f'<tbody>{rows}</tbody></table>')

    cons = report.get('constraint_changes') or []
    if cons:
        _kl = {'added': 'Added', 'removed': 'Removed', 'type': 'Type changed', 'date': 'Date changed'}
        rows = ''.join(
            f'<tr><td class="mono">{_e(c["activity_id"])}</td><td>{_e(c["name"])}</td>'
            f'<td>{_e(_kl.get(c["kind"], c["kind"]))}{" · hard" if c.get("hard") else ""}</td>'
            f'<td>{_e(c["rev0"])}</td><td>{_e(c["rev1"])}</td></tr>' for c in cons[:20])
        out.append('<h3 style="margin-top:12px">Constraint changes</h3>'
                   '<table class="grid"><thead><tr><th>Activity</th><th>Name</th><th>Change</th><th>Rev.00</th><th>Rev.01</th></tr></thead>'
                   f'<tbody>{rows}</tbody></table>')
    return ''.join(out)


def _register(report):
    rows = ''
    for row in report.get('register', []):
        idt = (row.get('orig_id') or row['activity_id'])
        idt = idt.replace('MS:', '').replace('SCOPE:', '')
        rows += f'''<tr><td class="mono">{_e(idt)}</td><td>{_e(row['activity_name'])}</td>
          <td>{_e(row['type_label'])}</td><td>{_e(row.get('rev0') or '—')}</td><td>{_e(row.get('rev1') or '—')}</td>
          <td>{_e(row.get('change') or '')}</td>
          <td class="{'imp-mat' if row['impact'] == 'material' else 'imp-min'}">{'Material' if row['impact'] == 'material' else 'Minor'}</td>
          <td><span class="tag {_sev_cls(row['severity'])}">{_sev_label(row['severity'])}</span></td></tr>'''
    if not rows:
        return '<p class="muted">No material changes detected between the two revisions.</p>'
    return f'''<table class="grid reg"><thead><tr><th>Activity</th><th>Name</th><th>Type</th><th>Rev.00</th><th>Rev.01</th><th>Change</th><th>Impact</th><th>Severity</th></tr></thead><tbody>{rows}</tbody></table>'''


def _detailed(report):
    out = []
    for row in report.get('register', []):
        d = row.get('detail')
        if not d:
            continue
        def col(v, title):
            if not v:
                return ''
            K = [('Activity ID', v.get('id')), ('Name', v.get('name')), ('WBS', v.get('wbs')),
                 ('Start', v.get('start')), ('Finish', v.get('finish')), ('Duration', v.get('duration')),
                 ('Total float', v.get('total_float')), ('Criticality', v.get('criticality'))]
            body = ''.join(f'<tr><td class="k">{_e(k)}</td><td class="num">{_e(val)}</td></tr>' for k, val in K)
            return f'<div class="dcol"><div class="dch">{_e(title)}</div><table class="dtl">{body}</table></div>'
        out.append(f'''<div class="dblock">
          <div class="ft">{_e(row['activity_name'])} — {_e(row.get('change'))}</div>
          <div class="dcols">{col(d.get('rev0'), 'Rev.00 · Original')}{col(d.get('rev1'), 'Rev.01 · Revised')}</div>
          <div class="analysis">
            <div class="ab"><span>Change detected</span><p>{_e(d.get('detected'))}</p></div>
            <div class="ab"><span>Why it matters</span><p>{_e(d.get('why'))}</p></div>
            <div class="ab"><span>Potential impact</span><p>{_e(d.get('impact'))}</p></div>
            <div class="ab"><span>Planning review</span><p>{_e(d.get('review'))}</p></div>
          </div></div>''')
    if not out:
        return ''
    return ''.join(out)


# ── document ─────────────────────────────────────────────────────────────────

def render_html(report, meta=None, sections=None, theme='light'):
    narrative = report.get('narrative', '')
    secs = [
        ('summary', 'Executive Summary',
         _kpis(report) + '<div class="two"><div class="col"><h3>Change profile</h3>' + _profile(report)
         + '</div><div class="col"><h3>Assessment</h3><p class="narr">' + _e(narrative) + '</p></div></div>'
         + '<h3>Key findings — material changes</h3>' + _findings(report), False),
        ('overview', 'Revision Overview', _overview(report), False),
        ('milestones', 'Milestone Comparison', _milestones(report), False),
        ('critpath', 'Critical Path Comparison', _critpath(report), True),
        ('sequence', 'Major Sequence Changes', _sequences(report), False),
        ('logic', 'Major Relationship / Logic Changes', _logic(report), False),
        ('scope', 'WBS, Calendar &amp; Constraint Changes', _scope(report), False),
        ('register', 'Detailed Change Register', _register(report), True),
        ('detailed', 'Detailed Change Analysis', _detailed(report), True),
    ]
    keys = set(sections) if sections else None
    body = [_header(report, meta)]
    for key, title, htmlc, brk in secs:
        if keys is not None and key not in keys:
            continue
        if key == 'detailed' and not htmlc:
            continue
        body.append(f'<section data-sec="{key}"{" class=pagebreak" if brk else ""}><h2>{_e(title)}</h2>{htmlc}</section>')

    css = _CSS
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style>'
            f'{report_theme.theme_style_tag(theme)}</head><body>'
            + ''.join(body) + '</body></html>')


_CSS = '''
@page { size: A4 landscape; margin: 12mm; }
* { box-sizing: border-box; }
body { font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; color: var(--rpt-ink); font-size: 11.5px; margin: 0; }
h1 { font-size: 19px; margin: 0; }
h2 { font-size: 13px; margin: 16px 0 9px; color: var(--rpt-accent); border-bottom: 1px solid var(--rpt-hair); padding-bottom: 4px; }
h3 { font-size: 11px; text-transform: uppercase; letter-spacing: .4px; color: var(--rpt-muted); margin: 0 0 7px; }
section.pagebreak { page-break-before: always; }
section { page-break-inside: auto; }
.muted { color: var(--rpt-muted); } .num { text-align: right; } .mono { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 10.5px; }
.rh { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid var(--rpt-edge); padding-bottom: 9px; }
.rhr { text-align: right; } .meta { color: var(--rpt-muted); font-size: 10.5px; margin-top: 3px; } .meta b { color: var(--rpt-ink); }
.kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 9px; margin-bottom: 12px; }
.kpi { border: 1px solid var(--rpt-edge); border-radius: 9px; padding: 9px 11px; }
.kk { font-size: 9px; text-transform: uppercase; letter-spacing: .3px; color: var(--rpt-muted); font-weight: 700; }
.kv { font-size: 18px; font-weight: 800; margin-top: 3px; } .kd { font-size: 10px; color: var(--rpt-muted); margin-top: 3px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 6px; }
.narr { font-size: 11.5px; line-height: 1.55; color: var(--rpt-ink-soft); margin: 0; }
.profile { display: flex; flex-direction: column; gap: 6px; }
.pf { display: flex; align-items: center; gap: 9px; font-size: 11px; }
.pfl { width: 150px; color: var(--rpt-ink-soft); } .pft { flex: 1; height: 8px; background: var(--rpt-surface-2); border-radius: 5px; overflow: hidden; }
.pft i { display: block; height: 100%; border-radius: 5px; } .pfv { width: 26px; text-align: right; font-weight: 700; }
.find { border: 1px solid var(--rpt-edge); border-left: 4px solid var(--rpt-muted); border-radius: 8px; padding: 9px 12px; margin-bottom: 8px; page-break-inside: avoid; }
.find.bad { border-left-color: var(--rpt-bad); } .find.warn { border-left-color: var(--rpt-warn); } .find.accent { border-left-color: var(--rpt-accent); }
.ft { font-weight: 700; font-size: 12px; } .fb { font-size: 11px; color: var(--rpt-ink-soft); margin-top: 4px; line-height: 1.5; } .fb b { color: var(--rpt-ink); }
.flow { display: flex; gap: 7px; align-items: center; margin-top: 6px; font-size: 10px; color: var(--rpt-muted); } .flow b { color: var(--rpt-accent); }
.tag { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .3px; padding: 2px 7px; border-radius: 5px; }
.tag.bad { background: var(--rpt-bad-bg); color: var(--rpt-bad); } .tag.warn { background: var(--rpt-warn-bg); color: var(--rpt-warn); }
.tag.good { background: var(--rpt-good-bg); color: var(--rpt-good); } .tag.accent { background: var(--rpt-accent-soft); color: var(--rpt-accent); }
.tag.muted { background: var(--rpt-surface-2); color: var(--rpt-muted); }
table.grid, table.ov { width: 100%; border-collapse: collapse; font-size: 11px; }
table.ov { margin-bottom: 8px; } .mt { margin-top: 8px; }
.grid th, .ov th { text-align: left; background: var(--rpt-th-bg); color: var(--rpt-th-ink); font-size: 9px; text-transform: uppercase; letter-spacing: .3px; padding: 6px 8px; }
.grid td, .ov td { padding: 6px 8px; border-bottom: 1px solid var(--rpt-hair); vertical-align: top; }
.grid th.num, .grid td.num { text-align: right; } .k { color: var(--rpt-muted); } td.k { font-weight: 600; color: var(--rpt-ink-soft); }
.reg { font-size: 10px; } .imp-mat { color: var(--rpt-bad); font-weight: 700; } .imp-min { color: var(--rpt-muted); }
.warns { margin-top: 8px; } .warn { background: var(--rpt-warn-bg); color: var(--rpt-warn); border-radius: 6px; padding: 6px 10px; font-size: 10px; margin-bottom: 4px; }
.sub { color: var(--rpt-muted); font-size: 11px; margin: 0 0 8px; }
.cprow { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 8px; }
.cplab { width: 54px; font-size: 9px; font-weight: 800; text-transform: uppercase; color: var(--rpt-muted); padding-top: 6px; } .cplab.r1 { color: var(--rpt-accent); }
.chain { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; }
.cn { border: 1px solid var(--rpt-edge); border-radius: 7px; padding: 5px 9px; font-size: 10.5px; font-weight: 600; }
.cn.enter { border-color: var(--rpt-good); background: var(--rpt-good-bg); color: var(--rpt-good); }
.cn.leave { border-color: var(--rpt-bad); background: var(--rpt-bad-bg); color: var(--rpt-bad); text-decoration: line-through; }
.ar { color: var(--rpt-accent); font-weight: 900; }
.seqcard { border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 9px 12px; margin-bottom: 8px; page-break-inside: avoid; }
.seqline { font-size: 10.5px; margin-top: 4px; color: var(--rpt-ink-soft); } .seqline .k.r1 { color: var(--rpt-accent); }
.scope { display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; }
.scard { border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 9px 11px; }
.dblock { border: 1px solid var(--rpt-edge); border-radius: 9px; padding: 11px 13px; margin-bottom: 10px; page-break-inside: avoid; }
.dcols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 8px 0; }
.dcol { border: 1px solid var(--rpt-hair); border-radius: 7px; overflow: hidden; }
.dch { background: var(--rpt-surface-2); padding: 5px 9px; font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .3px; color: var(--rpt-ink-soft); }
table.dtl { width: 100%; border-collapse: collapse; font-size: 10px; }
table.dtl td { padding: 4px 9px; border-top: 1px solid var(--rpt-hair); } table.dtl td.num { text-align: right; font-weight: 600; }
.analysis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.ab { border: 1px solid var(--rpt-hair); border-radius: 7px; padding: 8px 10px; }
.ab span { font-size: 8.5px; font-weight: 800; text-transform: uppercase; letter-spacing: .3px; color: var(--rpt-accent); }
.ab p { margin: 4px 0 0; font-size: 10px; line-height: 1.45; color: var(--rpt-ink-soft); }
'''
