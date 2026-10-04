"""The rest of a Schedule Health check's report, as extra workbook sheets (owner comment 29).

The first sheet of a check's Excel is its findings register (``exporters.excel_columns``). The
screen and the PDF also show the score and how it was worked out, the key figures, the severity
rules, the by-WBS distribution and (for the milestone check) the milestones found in the file.
``extra_sheets`` returns those as sheets for ``write_sections_xlsx`` — every table with all its
rows, every chart as its numbers — so the workbook carries everything the report does.

Pure and guarded: a check that has none of a block simply gets no such block / sheet.
"""

# Keys whose plain wording is not just the key with spaces.
_LABELS = {
    'wbs': 'WBS', 'pct': '%', 'oos': 'Out of sequence', 'oos_count': 'Out-of-sequence activities',
    'oos_pct': 'Out of sequence %', 'critical_oos': 'Out of sequence on the critical path',
    'near_critical_oos': 'Out of sequence near-critical', 'avg_float': 'Average float (d)',
    'max_float': 'Maximum float (d)', 'activity_id': 'Activity ID', 'name': 'Activity Name',
    'task_type': 'Type', 'finish': 'Finish', 'lagged': 'Links with a lag',
    'is_construction': 'Construction scope', 'cpli': 'CPLI', 'cpli_pct': 'CPLI %',
    'dcma_lag_line': 'DCMA lag guideline %', 'dcma_max_pct': 'DCMA maximum %',
    'dcma_within_pct': 'DCMA within %', 'fs_pct': 'FS %', 'ss_pct': 'SS %', 'ff_pct': 'FF %',
    'sf_pct': 'SF %', 'non_fs': 'Non-FS relationships',
    'fs_count': 'FS relationships', 'ss_count': 'SS relationships', 'ff_count': 'FF relationships',
    'sf_count': 'SF relationships', 'remaining_activities': 'Remaining activities (not started + in progress)',
    'total_activities': 'Total activities', 'total_all': 'Total activities (incl. completed)',
    'basis_type': 'How lags by relationship type are counted', 'basis_wbs': 'How lags by WBS area are counted',
}
# Display-only keys (colours, short duplicates of a label, internal switches).
_SKIP = {'fh_color', 'short', 'computable', 'cpli_computable', 'score_basis', 'cpl_basis',
         'context', 'is_update', 'total_label'}
# A check's own top-level tables → the sheet each becomes.
_TABLES = (
    ('wbs_summary', 'By WBS', 'Distribution by WBS'),
    ('milestones', 'Contract Milestones', 'Contract milestones checked against the schedule'),
    ('baseline_milestones', 'Schedule Milestones', 'Milestones found in the schedule file'),
)


def label(key):
    """A report key as a column / row heading: 'above_threshold' → 'Above threshold'."""
    if key in _LABELS:
        return _LABELS[key]
    words = str(key).replace('_', ' ').strip()
    words = words[:-4] + ' %' if words.endswith(' pct') else words
    return words[:1].upper() + words[1:]


def _tile_label(text):
    """A tile caption for the Summary sheet.  A caption that is still a raw key ('lagged pct',
    'dcma lag line') is written as a heading ('Lagged %'); a real caption is kept as it is."""
    t = str(text or '')
    return label(t.replace(' ', '_')) if t and t == t.lower() else t


def _value(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'Yes' if v else 'No'
    if isinstance(v, (int, float, str)):
        return v
    return str(v)


def _scalar(v):
    return v is None or isinstance(v, (str, int, float, bool))


def _pairs(d):
    """A flat dict's plain figures as [heading, value] rows (nested parts are left to the caller)."""
    return [[label(k), _value(v)] for k, v in d.items() if k not in _SKIP and _scalar(v)]


def _table(rows):
    """A list of flat dicts as (headers, rows) — the columns in first-seen order."""
    keys = []
    for r in rows:
        for k, v in r.items():
            if k not in keys and k not in _SKIP and _scalar(v):
                keys.append(k)
    return [label(k) for k in keys], [[_value(r.get(k)) for k in keys] for r in rows]


def _dict_rows(rows):
    return [r for r in (rows or []) if isinstance(r, dict)]


def _summary_blocks(m):
    p = m.get('presentation') or {}
    kpis = m.get('kpis') or {}
    blocks = []

    result = []
    # The Lag Report is a register with a justification column: its screen and its PDF show no
    # score, so its workbook shows none either (the score belongs to the Schedule Health checks).
    scored = m.get('module') != 'lag_lead'
    if scored and m.get('score') is not None:
        result.append(['Score', _value(m.get('score'))])
    if scored and m.get('grade'):
        result.append(['Grade', m.get('grade')])
    if scored and p.get('verdict'):
        result.append(['Result', p.get('verdict')])
    sc = (p.get('scoring') or {}) if scored else {}
    for key, head in (('formula', 'How it is scored'), ('derivation', 'This schedule'),
                      ('bands', 'Grade bands'), ('benchmark', 'Benchmark')):
        if sc.get(key):
            result.append([head, sc[key]])
    if result:
        blocks.append({'title': 'Result', 'headers': ['Item', 'Value'], 'rows': result})

    tiles = [[_tile_label(t.get('label', '')), _value(t.get('value'))] for t in (p.get('tiles') or [])
             if isinstance(t, dict)]
    if tiles:
        blocks.append({'title': 'Key figures (as shown on the report)',
                       'headers': ['Figure', 'Value'], 'rows': tiles})

    figures = _pairs(kpis)
    if figures:
        blocks.append({'title': 'All figures', 'headers': ['Figure', 'Value'], 'rows': figures})
    for k, v in kpis.items():                                  # a chart's numbers (e.g. lags by type)
        rows = _dict_rows(v) if isinstance(v, list) else []
        if rows:
            headers, body = _table(rows)
            blocks.append({'title': label(k), 'headers': headers, 'rows': body})

    sev = p.get('severity') or {}
    levels = [[lv.get('level', ''), lv.get('criteria', '')] for lv in _dict_rows(sev.get('levels'))]
    if levels:
        blocks.append({'title': 'Severity — how each level is set', 'note': sev.get('basis') or None,
                       'headers': ['Severity', 'Criteria'], 'rows': levels})

    counts = m.get('milestone_counts')
    if isinstance(counts, dict) and counts:
        blocks.append({'title': 'Contract milestones by status', 'headers': ['Status', 'Milestones'],
                       'rows': [[k, _value(v)] for k, v in counts.items()]})
    return blocks


def _mgmt_sheets(mgmt):
    """The management view of a check (Float & Flexibility): its figure groups on one sheet,
    its own tables on theirs."""
    blocks, sheets = [], []
    top = _pairs({k: v for k, v in mgmt.items() if k != 'conclusion'})
    if top:
        blocks.append({'title': 'Overall', 'headers': ['Figure', 'Value'], 'rows': top})
    for k, v in mgmt.items():
        if isinstance(v, dict):
            rows = _pairs(v)
            if rows:
                blocks.append({'title': label(k), 'headers': ['Figure', 'Value'], 'rows': rows})
        elif isinstance(v, list) and _dict_rows(v):
            headers, body = _table(_dict_rows(v))
            sheets.append({'name': 'Management — ' + label(k),
                           'blocks': [{'title': 'Management view — ' + label(k),
                                       'headers': headers, 'rows': body}]})
    if mgmt.get('conclusion'):
        blocks.append({'title': 'Conclusion', 'headers': ['Conclusion'], 'rows': [[mgmt['conclusion']]]})
    if blocks:
        sheets.insert(0, {'name': 'Management View', 'blocks': blocks})
    return sheets


def extra_sheets(m):
    """Every part of one check's report that is not its findings register, as workbook sheets
    ({'name', 'blocks'} for ``write_sections_xlsx``). [] when the check has nothing more."""
    m = m or {}
    sheets = []
    try:
        blocks = _summary_blocks(m)
        if blocks:
            sheets.append({'name': 'Summary', 'blocks': blocks})
        if isinstance(m.get('mgmt'), dict):
            sheets.extend(_mgmt_sheets(m['mgmt']))
        for key, name, title in _TABLES:
            rows = _dict_rows(m.get(key))
            if rows:
                headers, body = _table(rows)
                sheets.append({'name': name, 'blocks': [{'title': title, 'headers': headers,
                                                         'rows': body}]})
    except Exception:
        return sheets          # never lose the findings sheet to an odd extra
    return sheets
