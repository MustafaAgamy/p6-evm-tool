"""Consultant-format EVM report (matches the Schedule Audit report styling).

Executive Dashboard (equal-size tiles, SPI% headline) → PV-vs-EV bar →
Category Weights & Progress → optional PV-EV Gap by activity code →
optional Engineering Progress. EVM only — never mixed with the audit modules.
render_evm_report() returns HTML; the caller renders it to PDF via Chrome.
"""
import html as _html


def _esc(v):
    return _html.escape('' if v is None else str(v))


def _egp(n):
    if n is None:
        return '—'
    a = abs(n)
    if a >= 1e9:
        return f'{n / 1e9:.2f}B'
    if a >= 1e6:
        return f'{n / 1e6:.1f}M'
    return f'{n:,.0f}'


def _pct(x):
    return '—' if x is None else f'{round(x * 100)}%'


def spi_status(spi):
    if spi is None:
        return 'n/a', '#6b7a8d'
    if spi >= 1.0:
        return 'Ahead / On Schedule', '#2e8b57'
    if spi >= 0.95:
        return 'Slightly Behind', '#e07b1a'
    return 'Behind Schedule', '#c0392b'


def _tile(label, value, note='', accent=None):
    style = f' style="border-left:3px solid {accent}"' if accent else ''
    n = f'<div class="n">{_esc(note)}</div>' if note else ''
    return f'<div class="kpi"{style}><div class="k">{_esc(label)}</div><div class="v">{_esc(value)}</div>{n}</div>'


def _fmt_date(d):
    if d is None:
        return '—'
    try:
        return d.strftime('%d-%b-%y')
    except AttributeError:
        return str(d)[:10]


def _dashboard(result, meta):
    spi = result.get('spi')
    cpi = result.get('cpi')
    status, color = spi_status(spi)
    tiles = [
        _tile('SPI · Schedule', _pct(spi), status, accent=color),
        _tile('Planned Value', _egp(result.get('pv')), 'EGP'),
        _tile('Earned Value', _egp(result.get('ev')), 'EGP'),
        _tile('Actual Cost', _egp(meta.get('actual_cost', result.get('ac'))),
              'entered' if meta.get('actual_cost') is not None else 'from P6'),
        _tile('CPI · Cost', _pct(cpi), 'auto from Actual Cost'),
        _tile('Baseline Finish', _fmt_date(meta.get('baseline_finish'))),
        _tile('Expected Finish', _fmt_date(meta.get('expected_finish'))),
        _tile('Delay', f"{result.get('delay_days')} days" if result.get('delay_days') is not None else '—'),
    ]
    return f'<div class="dash-grid">{"".join(tiles)}</div>'


def _pv_ev_bar(result):
    pv = result.get('pv') or 0
    ev = result.get('ev') or 0
    mx = max(pv, ev, 1)
    def row(label, val, color):
        w = 100.0 * val / mx
        return (f'<div class="bar-row"><div class="bar-label">{label}</div>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{w:.1f}%;background:{color}"></div></div>'
                f'<div class="bar-val">{_egp(val)}</div></div>')
    return (row('Planned Value (PV)', pv, '#3b6fa8')
            + row('Earned Value (EV)', ev, '#8bb648'))


def _category_table(result):
    cats = result.get('categories', {})
    rows = []
    tot_pw = tot_wa = 0.0
    for name, c in cats.items():
        w = c.get('weight') or 0
        pp = c.get('planned_pct') or 0
        ap = c.get('actual_pct') or 0
        pw = w * pp * 100
        wa = w * ap * 100
        tot_pw += pw
        tot_wa += wa
        rows.append(
            f'<tr><td>{_esc(name)}</td><td class="num">{w*100:.1f}%</td>'
            f'<td class="num">{pp*100:.1f}%</td><td class="num">{ap*100:.1f}%</td>'
            f'<td class="num">{pw:.2f}%</td><td class="num">{wa:.2f}%</td></tr>')
    rows.append(
        f'<tr class="tot"><td>Overall</td><td class="num">—</td><td class="num">—</td>'
        f'<td class="num">—</td><td class="num">{tot_pw:.2f}%</td><td class="num">{tot_wa:.2f}%</td></tr>')
    return (
        '<table><thead><tr><th>WBS Category</th><th class="num">Weight %</th>'
        '<th class="num">Planned %</th><th class="num">Actual %</th>'
        '<th class="num">Planned Weight %</th><th class="num">Weighted Actual %</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>')


def _gap_section(gap):
    if not gap or not gap.get('groups'):
        return ''
    rows = []
    for g in gap['groups'][:15]:
        rows.append(
            f'<tr><td>{_esc(g["code"])}</td><td class="num">{_egp(g["pv"])}</td>'
            f'<td class="num">{_egp(g["ev"])}</td><td class="num">{_egp(g["gap"])}</td>'
            f'<td class="num">{g["pct_of_gap"]:.0f}%</td></tr>')
    return (
        f'<h2 class="sec">PV vs EV Gap Analysis — by {_esc(gap.get("dimension", ""))}</h2>'
        f'<p class="note">Total gap (PV − EV) = {_egp(gap.get("total_gap"))} EGP, showing where the slippage concentrates.</p>'
        '<table><thead><tr><th>Group</th><th class="num">PV</th><th class="num">EV</th>'
        '<th class="num">Gap</th><th class="num">% of Gap</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>')


def _engineering_section(engineering):
    """engineering: {'mode': 'E1'|'P6', 'rows': [ {trade, submittal_type, req, planned,
    submitted_rows, approved_rows, not_approved_rows, under_review_rows,
    planned_pct, submitted_pct, approved_pct} ]}. Empty string when absent."""
    if not engineering or not engineering.get('rows'):
        return ''
    mode = engineering.get('mode', 'E1')
    src = ('E1 Log (Approved ÷ Req)' if mode == 'E1'
           else 'P6 fallback (in-progress ÷ total per trade)')
    rows = []
    for r in engineering['rows']:
        rows.append(
            f'<tr><td>{_esc(r.get("trade"))}</td><td>{_esc(r.get("submittal_type"))}</td>'
            f'<td class="num">{r.get("req", "")}</td><td class="num">{r.get("planned", "")}</td>'
            f'<td class="num">{r.get("submitted_rows", "")}</td><td class="num">{r.get("approved_rows", "")}</td>'
            f'<td class="num">{r.get("not_approved_rows", "")}</td><td class="num">{r.get("under_review_rows", "")}</td>'
            f'<td class="num">{r.get("planned_pct", "")}%</td><td class="num">{r.get("submitted_pct", "")}%</td>'
            f'<td class="num">{r.get("approved_pct", "")}%</td></tr>')
    table = (
        '<div style="overflow-x:auto"><table style="min-width:720px"><thead><tr>'
        '<th>Trade</th><th>Submittal Type</th><th class="num">Req</th><th class="num">Planned</th>'
        '<th class="num">Submitted</th><th class="num">Approved</th><th class="num">Not Appr</th>'
        '<th class="num">Under Rev</th><th class="num">Planned %</th><th class="num">Submitted %</th>'
        f'<th class="num">Approved %</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
    gap = engineering.get('gap') or []
    gap_html = ''
    if gap:
        grows = ''.join(
            f'<tr><td>{_esc(g.get("trade"))}</td><td class="num">{g.get("planned_appr", "")}</td>'
            f'<td class="num">{g.get("actual_appr", "")}</td><td class="num">{g.get("gap", "")}</td>'
            f'<td class="num">{g.get("pct_of_gap", 0):.0f}%</td></tr>' for g in gap)
        gap_html = (
            '<h2 class="sec">Engineering Gap Analysis — Planned vs Actual Approval by Trade</h2>'
            '<table><thead><tr><th>Trade</th><th class="num">Planned Appr</th>'
            '<th class="num">Actual Appr</th><th class="num">Gap</th><th class="num">% of Gap</th>'
            f'</tr></thead><tbody>{grows}</tbody></table>')
    return (f'<h2 class="sec">Engineering Progress — Drawings by Trade</h2>'
            f'<p class="note">Source: {_esc(src)}. % Submitted = (Submitted − Not Approved) ÷ Req; '
            f'% Approved = Approved ÷ Req.</p>{table}{gap_html}')


def render_evm_report(result, meta, gap=None, engineering=None):
    gap_html = _gap_section(gap)
    eng_html = _engineering_section(engineering)
    return f'''<!DOCTYPE html><html><head><meta charset="utf-8">
<title>EVM Results — {_esc(meta.get('project_name', ''))}</title>
<style>
  @page {{ margin: 20mm 14mm; }}
  body {{ font-family:'Segoe UI',Arial,sans-serif; color:#1f2a37; font-size:11px; margin:0; }}
  .head {{ border-bottom:3px solid #17457a; padding-bottom:12px; margin-bottom:18px; }}
  .kicker {{ font-size:10px; letter-spacing:2px; color:#17457a; font-weight:700; text-transform:uppercase; }}
  .title {{ font-size:24px; font-weight:800; color:#0f2440; margin:3px 0 1px; }}
  .subtitle {{ font-size:12px; color:#5b6472; }}
  .meta {{ display:flex; flex-wrap:wrap; gap:3px 26px; margin-top:10px; font-size:11px; }}
  .meta span {{ color:#8a93a0; }}
  h2.sec {{ font-size:12px; text-transform:uppercase; letter-spacing:1px; color:#17457a; border-bottom:1px solid #dbe1e8; padding-bottom:4px; margin:22px 0 10px; }}
  .dash-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }}
  .kpi {{ border:1px solid #e8ecf1; border-radius:8px; padding:12px 13px; min-height:62px; display:flex; flex-direction:column; justify-content:center; }}
  .kpi .k {{ font-size:9px; text-transform:uppercase; letter-spacing:.4px; color:#8a93a0; font-weight:700; }}
  .kpi .v {{ font-size:19px; font-weight:800; margin-top:2px; color:#0f2440; }}
  .kpi .n {{ font-size:9px; color:#8a93a0; margin-top:1px; }}
  .bar-row {{ display:flex; align-items:center; gap:8px; margin:6px 0; font-size:10px; }}
  .bar-label {{ width:150px; color:#5b6472; }}
  .bar-track {{ flex:1; background:#eef1f5; border-radius:4px; height:18px; overflow:hidden; }}
  .bar-fill {{ height:100%; border-radius:4px; }}
  .bar-val {{ width:90px; text-align:right; font-weight:700; }}
  table {{ width:100%; border-collapse:collapse; font-size:10.5px; margin-top:4px; }}
  th {{ background:#26517d; color:#fff; text-align:left; padding:7px 9px; font-weight:600; font-size:9.5px; }}
  td {{ padding:7px 9px; border-bottom:1px solid #eef1f5; }}
  tbody tr:nth-child(even) {{ background:#f7f9fb; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .tot {{ font-weight:800; background:#eef4fb !important; }}
  .note {{ font-size:10px; color:#8a93a0; font-style:italic; }}
  .foot {{ border-top:1px solid #dbe1e8; margin-top:20px; padding-top:8px; font-size:9px; color:#8a93a0; }}
</style></head><body>
  <div class="head">
    <div class="kicker">Earned Value Management · Report</div>
    <div class="title">EVM Results</div>
    <div class="subtitle">Schedule &amp; Cost Performance — Planned vs Earned Value</div>
    <div class="meta">
      <div><span>Project:</span> {_esc(meta.get('project_name', ''))}</div>
      <div><span>Data Date:</span> {_esc(meta.get('data_date', ''))}</div>
      <div><span>Report Date:</span> {_esc(meta.get('report_date', ''))}</div>
      <div><span>Schedule File:</span> {_esc(meta.get('source_file', ''))}</div>
    </div>
  </div>

  <h2 class="sec">Executive Dashboard</h2>
  {_dashboard(result, meta)}

  <h2 class="sec">Planned Value vs Earned Value</h2>
  {_pv_ev_bar(result)}

  <h2 class="sec">Category Weights &amp; Overall Progress</h2>
  {_category_table(result)}

  {eng_html}

  {gap_html}

  <div class="foot">EVM computed from the P6 schedule; Engineering % from the E1 Log when provided. This report covers EVM only, isolated from the Schedule Audit modules. · {_esc(meta.get('project_name', ''))}</div>
</body></html>'''
