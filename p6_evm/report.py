import html

import report_theme


def find_finish_milestone(result):
    records = [r for r in result['records'] if r['activity']['planned_finish']]
    if not records:
        return None
    return max(records, key=lambda r: r['activity']['planned_finish'])


def bar_svg(pairs, width=560, bar_h=28, gap=14, max_value=None, value_fmt=None):
    """pairs: list of (label, value, color). Simple horizontal bar chart."""
    value_fmt = value_fmt or (lambda v: f'{v:,.0f}')
    max_value = max_value or max(v for _, v, _ in pairs) or 1
    label_w = 170
    chart_w = width - label_w - 90
    rows = []
    y = 10
    for label, value, color in pairs:
        bar_len = max(2, (value / max_value) * chart_w)
        rows.append(f'''
          <text x="{label_w - 8}" y="{y + bar_h * 0.65}" text-anchor="end"
                font-size="13" fill="{report_theme.var('rpt-chart-axis')}">{html.escape(label)}</text>
          <rect x="{label_w}" y="{y}" width="{bar_len:.1f}" height="{bar_h}" fill="{color}" rx="3"/>
          <text x="{label_w + bar_len + 8}" y="{y + bar_h * 0.65}" font-size="13" fill="{report_theme.var('rpt-chart-axis')}">
                {html.escape(value_fmt(value))}</text>
        ''')
        y += bar_h + gap
    height = y
    return f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}">{"".join(rows)}</svg>'


def render_audit_section(audit):
    """HTML for the Schedule Health section of the PDF. Empty string if no audit."""
    if not audit:
        return ''
    ov = audit.get('scores', {}).get('overall', {})
    counts = audit.get('counts', {})
    by_sev = counts.get('by_severity', {})
    total_areas = audit.get('total_review_areas', 5)
    evaluated = ov.get('categories_evaluated', 0)
    sev_bits = ' &nbsp; '.join(
        f'{s}: {by_sev.get(s, 0)}' for s in ('Critical', 'High', 'Medium', 'Low')
    )
    rows = []
    for f in audit.get('findings', []):
        rows.append(f'''
          <tr>
            <td>{html.escape(f.get('severity', ''))}</td>
            <td>{html.escape(f.get('check_name', ''))}</td>
            <td>{html.escape(f.get('activity_id', ''))}<br>
                <span style="color:var(--rpt-muted);font-size:11px">{html.escape(f.get('activity_name', ''))}</span></td>
            <td style="font-size:11px;color:var(--rpt-ink-soft)">{html.escape(f.get('wbs_path', ''))}</td>
            <td>{html.escape(f.get('summary', ''))}<br>
                <span style="color:var(--rpt-muted);font-size:11px">{html.escape(f.get('recommendation', ''))}</span></td>
          </tr>''')
    findings_table = (
        '<table class="data"><tr><th>Severity</th><th>Check</th>'
        '<th>Activity</th><th>WBS Path</th><th>Issue &amp; Recommendation</th></tr>'
        + ''.join(rows) + '</table>'
    ) if rows else '<p class="note">No findings — the schedule passed all built checks.</p>'
    return f'''
      <h2>Schedule Health</h2>
      <div class="kpi-row">
        <div class="kpi"><div class="label">Health Score</div>
             <div class="value">{ov.get('score', '—')} / 100</div></div>
        <div class="kpi"><div class="label">Grade</div>
             <div class="value">{html.escape(str(ov.get('grade', '—')))}</div></div>
        <div class="kpi"><div class="label">Findings</div>
             <div class="value">{counts.get('total', 0)}</div></div>
      </div>
      <p class="note">Based on {evaluated} of {total_areas} review areas built so far
         (Schedule Logic &amp; Float Analysis). &nbsp; {sev_bits}</p>
      {findings_table}
    '''


def render_html(result, meta, audit=None, theme='light'):
    fm = find_finish_milestone(result)
    delay = result['delay_days']

    pv, ev, ac = result['pv'], result['ev'], result['ac']
    spi = result['spi']
    cpi = result['cpi']
    variance = result['variance']

    cat_rows = []
    cat_bar_pairs = []
    for name, c in result['categories'].items():
        source = 'Manual override' if c.get('overridden') else 'From XML'
        cat_rows.append(f'''
          <tr>
            <td>{html.escape(name)}</td>
            <td class="num">{c['weight'] * 100:.1f}%</td>
            <td class="num">{c['planned_pct'] * 100:.2f}%</td>
            <td class="num">{c['actual_pct'] * 100:.2f}%</td>
            <td class="num">{c['activity_count']}</td>
            <td>{source}</td>
          </tr>
        ''')
        cat_bar_pairs.append((f"{name} (Planned)", c['planned_pct'] * 100, report_theme.var('rpt-series-1')))
        cat_bar_pairs.append((f"{name} (Actual)", c['actual_pct'] * 100, report_theme.var('rpt-series-2')))

    overall_bar = bar_svg([
        ('Overall Planned%', result['overall_planned_pct'] * 100, report_theme.var('rpt-series-1')),
        ('Overall Actual%', result['overall_actual_pct'] * 100, report_theme.var('rpt-series-2')),
    ], max_value=100, value_fmt=lambda v: f'{v:.2f}%')

    category_bar = bar_svg(cat_bar_pairs, max_value=100, value_fmt=lambda v: f'{v:.2f}%')

    pv_ev_bar = bar_svg([
        ('Planned Value (PV)', pv, report_theme.var('rpt-series-1')),
        ('Earned Value (EV)', ev, report_theme.var('rpt-series-2')),
        ('Actual Cost (AC)', ac, report_theme.var('rpt-series-3')),
    ], value_fmt=lambda v: f'{v:,.0f}')

    delay_row = ''
    if fm is not None:
        baseline = result.get('baseline_lookup', {})
        bl_finish = meta.get('milestone_baseline_finish')
        cur_finish = fm['activity']['planned_finish']
        delay_row = f'''
          <tr>
            <td>{html.escape(fm['activity']['name'] or fm['activity']['id'] or '')}</td>
            <td>{bl_finish.strftime('%d-%b-%Y') if bl_finish else 'n/a'}</td>
            <td>{cur_finish.strftime('%d-%b-%Y') if cur_finish else 'n/a'}</td>
            <td class="num">{delay}</td>
          </tr>
        '''

    audit_section = render_audit_section(audit)

    excluded_note = '''
      <p class="note">
        This report covers only the sections computable from the P6 XML schedule:
        duration/delay, Planned/Earned Value, and category progress roll-ups.
        Sections that require data outside the schedule file &mdash; Invoice Log,
        Manpower &amp; Equipment, Major Material Delivered/Procurement Status,
        Area of Concern, and Progress Photos &mdash; are not included, since the
        source XML carries no such information.
      </p>
    '''

    return f'''
    <html>
    <head>
    <meta charset="utf-8">
    <title>{html.escape(meta.get('project_name', 'Weekly Report'))}</title>
    <style>
      body {{ font-family: Georgia, 'Times New Roman', serif; color: var(--rpt-ink); margin: 40px; }}
      h1 {{ font-size: 22px; margin-bottom: 4px; }}
      h2 {{ font-size: 16px; border-bottom: 2px solid var(--rpt-chart-axis); padding-bottom: 4px; margin-top: 36px; }}
      .meta-table td {{ padding: 3px 8px; font-size: 13px; }}
      .meta-table td.label {{ font-weight: bold; width: 160px; }}
      table.data {{ border-collapse: collapse; width: 100%; margin-top: 10px; font-size: 13px; }}
      table.data th, table.data td {{ border: 1px solid var(--rpt-hair-strong); padding: 6px 8px; }}
      table.data th {{ background: var(--rpt-th-bg); color: var(--rpt-th-ink); text-align: left; }}
      td.num, th.num {{ text-align: right; }}
      .kpi-row {{ display: flex; gap: 24px; margin-top: 12px; flex-wrap: wrap; }}
      .kpi {{ border: 1px solid var(--rpt-hair-strong); border-radius: 6px; padding: 10px 16px; min-width: 140px; }}
      .kpi .label {{ font-size: 11px; color: var(--rpt-ink-soft); text-transform: uppercase; }}
      .kpi .value {{ font-size: 18px; font-weight: bold; margin-top: 4px; }}
      .note {{ font-size: 12px; color: var(--rpt-ink-soft); font-style: italic; margin-top: 24px; }}
      .footer {{ margin-top: 40px; font-size: 11px; color: var(--rpt-muted); border-top: 1px solid var(--rpt-hair); padding-top: 8px; }}
    </style>
    {report_theme.theme_style_tag(theme)}
    </head>
    <body>
      <h1>{html.escape(meta.get('project_name', 'Weekly Report'))}</h1>
      <table class="meta-table">
        <tr><td class="label">Data Date</td><td>{result['data_date'].strftime('%d-%b-%Y')}</td></tr>
        <tr><td class="label">Project Id</td><td>{html.escape(meta.get('project_id', ''))}</td></tr>
        <tr><td class="label">Source File</td><td>{html.escape(meta.get('source_file', ''))}</td></tr>
      </table>

      <h2>Duration Status</h2>
      <table class="data">
        <tr><th>Item</th><th>Baseline Finish</th><th>Current Finish</th><th class="num">Delay (days)</th></tr>
        {delay_row}
      </table>

      <h2>Planned Value vs Earned Value</h2>
      {pv_ev_bar}
      <div class="kpi-row">
        <div class="kpi"><div class="label">Planned Value</div><div class="value">{pv:,.0f}</div></div>
        <div class="kpi"><div class="label">Earned Value</div><div class="value">{ev:,.0f}</div></div>
        <div class="kpi"><div class="label">Actual Cost</div><div class="value">{ac:,.0f}</div></div>
        <div class="kpi"><div class="label">SPI</div><div class="value">{spi:.4f}</div></div>
        <div class="kpi"><div class="label">CPI</div><div class="value">{cpi:.4f}</div></div>
        <div class="kpi"><div class="label">Variance</div><div class="value">{variance:,.0f}</div></div>
      </div>
      <p class="note">CPI is structurally ~1.00 in this schedule: cost is derived directly from
      % complete rather than tracked independently, so it does not carry additional signal beyond SPI.</p>

      <h2>Overall Project Progress</h2>
      {overall_bar}
      <table class="data">
        <tr>
          <th>Category</th><th class="num">Weight</th><th class="num">Planned%</th>
          <th class="num">Actual%</th><th class="num">#Activities</th><th>Source</th>
        </tr>
        {"".join(cat_rows)}
      </table>
      {category_bar}

      {audit_section}

      {excluded_note}

      <div class="footer">Generated by Controlyx from the attached P6 XML export.</div>
    </body>
    </html>
    '''
