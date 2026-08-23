"""Consultant-format EVM report (matches the Schedule Audit report styling).

Executive Dashboard (equal-size tiles, SPI% headline) → PV-vs-EV bar →
Category Weights & Progress → optional PV-EV Gap by activity code →
optional Engineering Progress. EVM only — never mixed with the audit modules.
render_evm_report() returns HTML; the caller renders it to PDF via Chrome.
"""
import html as _html
from datetime import datetime

import report_theme


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


def _gap_val(v, fmt):
    """Show a gap as 'Ahead X' when it's negative (Earned > Planned)."""
    if v is None:
        return '—'
    return f'Ahead {fmt(-v)}' if v < 0 else fmt(v)


def spi_status(spi):
    if spi is None:
        return 'n/a', report_theme.var('rpt-muted')
    if spi >= 1.0:
        return 'Ahead / On Schedule', report_theme.var('rpt-good')
    if spi >= 0.95:
        return 'Slightly Behind', report_theme.var('rpt-warn')
    return 'Behind Schedule', report_theme.var('rpt-bad')


def _tile(label, value, note='', accent=None):
    style = f' style="border-left:3px solid {accent}"' if accent else ''
    n = f'<div class="n">{_esc(note)}</div>' if note else ''
    return f'<div class="kpi"{style}><div class="k">{_esc(label)}</div><div class="v">{_esc(value)}</div>{n}</div>'


def _fmt_date(d):
    """Format a date as e.g. 09-Feb.2026 (day-Mon.year).

    Accepts a datetime OR a string (ISO like 2026-02-09T00:00:00, or already
    day-first). The dashboard passes dates as JSON strings, so we coerce first —
    otherwise strftime fails silently and the raw ISO string leaks into the PDF.
    """
    if d is None or d == '':
        return '—'
    if not hasattr(d, 'strftime'):
        s = str(d).strip()
        parsed = None
        try:
            parsed = datetime.fromisoformat(s.replace('Z', '').replace('T', ' ').strip())
        except ValueError:
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d-%b-%Y', '%d-%b-%y', '%m/%d/%Y'):
                try:
                    parsed = datetime.strptime(s[:10] if fmt == '%Y-%m-%d' else s, fmt)
                    break
                except ValueError:
                    continue
        if parsed is None:
            return s[:11]
        d = parsed
    return d.strftime('%d-%b.%Y')


def _dashboard(result, meta):
    spi = result.get('spi')
    cpi = result.get('cpi')
    status, color = spi_status(spi)
    cats = result.get('categories', {}) or {}
    op = sum((c.get('weight') or 0) * (c.get('planned_pct') or 0) for c in cats.values())
    oa = sum((c.get('weight') or 0) * (c.get('actual_pct') or 0) for c in cats.values())
    tiles = [
        _tile('SPI · Schedule', _pct(spi), status, accent=color),
        _tile('Overall Planned %', f'{op * 100:.1f}%', 'weighted table'),
        _tile('Overall Actual %', f'{oa * 100:.1f}%', 'weighted table'),
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
    return (row('Planned Value (PV)', pv, report_theme.var('rpt-series-1'))
            + row('Earned Value (EV)', ev, report_theme.var('rpt-series-2')))


def _progress_band(result):
    """Top-of-report 'Project Progress · Planned vs Actual' summary.

    Planned % / Actual % are the Overall totals of the Category Weights table
    (unweighted sum of weight × %), so they match that section exactly. On the
    PDF this is the static summary; the on-screen view adds the discipline slicer.
    """
    cats = result.get('categories', {}) or {}
    planned = sum((c.get('weight') or 0) * (c.get('planned_pct') or 0) for c in cats.values())
    actual = sum((c.get('weight') or 0) * (c.get('actual_pct') or 0) for c in cats.values())
    var = actual - planned
    behind = var < 0
    var_txt = f"{'−' if behind else '+'}{abs(var) * 100:.2f}%"
    tiles = (_tile('Planned %', f'{planned * 100:.2f}%', 'Overall Planned Weight %')
             + _tile('Actual %', f'{actual * 100:.2f}%', 'Overall Weighted Actual %')
             + _tile('Variance', var_txt, 'behind plan' if behind else 'ahead of plan',
                     accent=report_theme.var('rpt-bad') if behind else report_theme.var('rpt-good')))
    mx = max(planned, actual, 0.0001)

    def bar(label, val, color):
        w = 100.0 * val / mx
        return (f'<div class="bar-row"><div class="bar-label">{label}</div>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{w:.1f}%;background:{color}"></div></div>'
                f'<div class="bar-val">{val * 100:.2f}%</div></div>')
    bars = bar('Planned', planned, report_theme.var('rpt-series-1')) + bar('Actual', actual, report_theme.var('rpt-series-2'))
    return (f'<div class="dash-grid" style="grid-template-columns:repeat(3,1fr)">{tiles}</div>'
            f'<div style="margin-top:10px">{bars}</div>')


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
            f'<td class="num">{_egp(g["ev"])}</td><td class="num">{_gap_val(g["gap"], _egp)}</td>'
            f'<td class="num">{abs(g["pct_of_gap"]):.0f}%</td></tr>')
    return (
        f'<h2 class="sec">PV vs EV Gap Analysis — by {_esc(gap.get("dimension", ""))}</h2>'
        f'<p class="note">Total gap (PV − EV) = {_gap_val(gap.get("total_gap"), _egp)} EGP, showing where the slippage concentrates.</p>'
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
    rows = []
    if mode == 'P6':
        # Straight from P6: four submittal/approval columns, counted "once started".
        for r in engineering['rows']:
            rows.append(
                f'<tr><td>{_esc(r.get("trade"))}</td><td>{_esc(r.get("submittal_type"))}</td>'
                f'<td class="num">{r.get("req", "")}</td>'
                f'<td class="num">{r.get("planned_sub", "")}</td><td class="num">{r.get("actual_sub", "")}</td>'
                f'<td class="num">{r.get("planned_appr", "")}</td><td class="num">{r.get("actual_appr", "")}</td>'
                f'<td class="num">{r.get("actual_sub_pct", "")}%</td>'
                f'<td class="num">{r.get("actual_appr_pct", "")}%</td></tr>')
        table = (
            '<div style="overflow-x:auto"><table style="min-width:720px"><thead><tr>'
            '<th>Trade</th><th>Submittal Type</th><th class="num">Req</th>'
            '<th class="num">Planned SUB</th><th class="num">Actual SUB</th>'
            '<th class="num">Planned APP</th><th class="num">Actual APP</th>'
            '<th class="num">Sub %</th><th class="num">Appr %</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
        note = ('Source: P6 (Mode B). A drawing counts as Submitted / Approved once its '
                'submittal / approval activity has started. Planned = baseline finish on/before the '
                'data date. Sub % = Actual SUB ÷ Req; Appr % = Actual APP ÷ Req.')
    else:
        for r in engineering['rows']:
            rows.append(
                f'<tr><td>{_esc(r.get("trade"))}</td><td>{_esc(r.get("submittal_type"))}</td>'
                f'<td class="num">{r.get("req", "")}</td><td class="num">{r.get("planned", "")}</td>'
                f'<td class="num">{r.get("submitted_rows", "")}</td><td class="num">{r.get("approved_rows", "")}</td>'
                f'<td class="num">{r.get("not_approved_rows", "")}</td><td class="num">{r.get("under_review_rows", "")}</td>'
                f'<td class="num">{r.get("planned_pct", "")}%</td><td class="num">{r.get("submitted_pct", "")}%</td>'
                f'<td class="num">{r.get("approved_pct", "")}%</td></tr>')
        # Two overall rows: Design drawings (non-Shop) and Engineering (Shop)
        ov = engineering.get('overall') or {}

        def _ov(label, o, bg):
            return (f'<tr style="font-weight:800;background:{bg}"><td>{label}</td><td></td>'
                    f'<td class="num">{o.get("req", "")}</td><td class="num">{o.get("planned", "")}</td>'
                    f'<td class="num">{o.get("submitted_rows", "")}</td><td class="num">{o.get("approved_rows", "")}</td>'
                    f'<td class="num">{o.get("not_approved_rows", "")}</td><td class="num">{o.get("under_review_rows", "")}</td>'
                    f'<td class="num">{o.get("planned_pct", "")}%</td><td class="num">{o.get("submitted_pct", "")}%</td>'
                    f'<td class="num">{o.get("approved_pct", "")}%</td></tr>')
        if ov:
            rows.append(_ov('Overall — Design Drawings', ov.get('design', {}), report_theme.var('rpt-accent-soft')))
            rows.append(_ov('Overall — Engineering (Shop) Drawings', ov.get('engineering', {}), report_theme.var('rpt-good-bg')))
        table = (
            '<div style="overflow-x:auto"><table style="min-width:720px"><thead><tr>'
            '<th>Trade</th><th>Submittal Type</th><th class="num">Req</th><th class="num">Planned</th>'
            '<th class="num">Submitted</th><th class="num">Approved</th><th class="num">Not Appr</th>'
            '<th class="num">Under Rev</th><th class="num">Planned %</th><th class="num">Submitted %</th>'
            f'<th class="num">Approved %</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
        note = ('Source: E1 Log. Design = any non-Shop drawing; Engineering = Shop drawings. '
                '% Submitted = (Submitted − Not Approved) ÷ Req; % Approved = Approved ÷ Req.')

    # Totals by trade — Total Civil = every Civil drawing across types.
    by_trade = engineering.get('by_trade') or []
    trade_html = ''
    if by_trade:
        trows = ''.join(
            f'<tr style="font-weight:700;background:{report_theme.var("rpt-surface-2")}"><td>Total {_esc(t.get("trade"))}</td>'
            f'<td class="num">{t.get("req", "")}</td><td class="num">{t.get("submitted_rows", "")}</td>'
            f'<td class="num">{t.get("approved_rows", "")}</td><td class="num">{t.get("not_approved_rows", "")}</td>'
            f'<td class="num">{t.get("submitted_pct", "")}%</td><td class="num">{t.get("approved_pct", "")}%</td></tr>'
            for t in by_trade)
        trade_html = (
            '<h2 class="sec">Engineering — Totals by Trade</h2>'
            '<table><thead><tr><th>Trade</th><th class="num">Req</th><th class="num">Submitted</th>'
            '<th class="num">Approved</th><th class="num">Not Appr</th><th class="num">Sub %</th>'
            f'<th class="num">Appr %</th></tr></thead><tbody>{trows}</tbody></table>')

    # Engineering Gap — same logic as the PV-EV gap (Planned − Approved, share of total),
    # split into Design and Engineering(Shop).
    gaps = engineering.get('gaps') or {}

    def _gap_table(title, groups):
        if not groups:
            return ''
        grows = ''.join(
            f'<tr><td>{_esc(g.get("trade"))}</td><td class="num">{g.get("planned", "")}</td>'
            f'<td class="num">{g.get("approved", "")}</td><td class="num">{_gap_val(g.get("gap"), lambda n: f"{n:g}")}</td>'
            f'<td class="num">{abs(g.get("pct_of_gap", 0)):.0f}%</td></tr>' for g in groups)
        return (
            f'<h2 class="sec">{_esc(title)}</h2>'
            '<table><thead><tr><th>Trade</th><th class="num">Planned</th>'
            '<th class="num">Approved</th><th class="num">Gap</th><th class="num">% of Gap</th>'
            f'</tr></thead><tbody>{grows}</tbody></table>')
    gap_html = (_gap_table('Engineering Gap — Design Drawings (Planned vs Approved by Trade)', gaps.get('design'))
                + _gap_table('Engineering Gap — Shop Drawings (Planned vs Approved by Trade)', gaps.get('engineering')))
    return (f'<h2 class="sec">Engineering Progress — Drawings by Trade</h2>'
            f'<p class="note">{_esc(note)}</p>{table}{trade_html}{gap_html}')


def render_evm_report(result, meta, gap=None, engineering=None, theme='light'):
    gap_html = _gap_section(gap)
    eng_html = _engineering_section(engineering)
    return f'''<!DOCTYPE html><html><head><meta charset="utf-8">
<title>EVM Results — {_esc(meta.get('project_name', ''))}</title>
<style>
  @page {{ margin: 20mm 14mm; }}
  body {{ font-family:'Segoe UI',Arial,sans-serif; color:var(--rpt-ink); font-size:11px; margin:0; }}
  .head {{ border-bottom:3px solid var(--rpt-accent); padding-bottom:12px; margin-bottom:18px; }}
  .kicker {{ font-size:10px; letter-spacing:2px; color:var(--rpt-accent); font-weight:700; text-transform:uppercase; }}
  .title {{ font-size:24px; font-weight:800; color:var(--rpt-ink); margin:3px 0 1px; }}
  .subtitle {{ font-size:12px; color:var(--rpt-ink-soft); }}
  .meta {{ display:flex; flex-wrap:wrap; gap:3px 26px; margin-top:10px; font-size:11px; }}
  .meta span {{ color:var(--rpt-muted); }}
  h2.sec {{ font-size:12px; text-transform:uppercase; letter-spacing:1px; color:var(--rpt-accent); border-bottom:1px solid var(--rpt-hair); padding-bottom:4px; margin:22px 0 10px; }}
  .dash-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }}
  .kpi {{ border:1px solid var(--rpt-edge); border-radius:8px; padding:12px 13px; min-height:62px; display:flex; flex-direction:column; justify-content:center; }}
  .kpi .k {{ font-size:9px; text-transform:uppercase; letter-spacing:.4px; color:var(--rpt-muted); font-weight:700; }}
  .kpi .v {{ font-size:19px; font-weight:800; margin-top:2px; color:var(--rpt-ink); }}
  .kpi .n {{ font-size:9px; color:var(--rpt-muted); margin-top:1px; }}
  .bar-row {{ display:flex; align-items:center; gap:8px; margin:6px 0; font-size:10px; }}
  .bar-label {{ width:150px; color:var(--rpt-ink-soft); }}
  .bar-track {{ flex:1; background:var(--rpt-surface-2); border-radius:4px; height:18px; overflow:hidden; }}
  .bar-fill {{ height:100%; border-radius:4px; }}
  .bar-val {{ width:90px; text-align:right; font-weight:700; }}
  table {{ width:100%; border-collapse:collapse; font-size:10.5px; margin-top:4px; }}
  th {{ background:var(--rpt-th-bg); color:var(--rpt-th-ink); text-align:left; padding:7px 9px; font-weight:600; font-size:9.5px; }}
  td {{ padding:7px 9px; border-bottom:1px solid var(--rpt-hair); }}
  tbody tr:nth-child(even) {{ background:var(--rpt-surface); }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .tot {{ font-weight:800; background:var(--rpt-accent-soft) !important; }}
  .note {{ font-size:10px; color:var(--rpt-muted); font-style:italic; }}
  .foot {{ border-top:1px solid var(--rpt-hair); margin-top:20px; padding-top:8px; font-size:9px; color:var(--rpt-muted); }}
</style>
{report_theme.theme_style_tag(theme)}
</head><body>
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

  <h2 class="sec">Project Progress — Planned vs Actual</h2>
  {_progress_band(result)}

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
