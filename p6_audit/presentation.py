"""Normalized presentation for every Schedule Health Review check — the ONE source
the screen, the PDF and Excel all render from.

The screen (ui/modules/audit.js), the PDF (p6_audit/report.py) and Excel
(p6_audit/exporters.py) used to each define the module's KPI tiles and table
columns independently, so they drifted: the PDF only ever knew Dangling and
Float and printed every other check with the wrong columns. This module removes
that duplication.

`build_presentation(module_result)` returns, for one module:

    {
      'tiles':   [{'label','value'}],                 # KPI tiles (values pre-formatted)
      'columns': [{'label','align'}],                 # findings-table headers (no '#')
      'rows':    [[cell, ...], ...],                  # one row per finding, PARALLEL to
                                                       #   module['findings'] so the UI can
                                                       #   filter findings and render rows by index
      'verdict': str,                                 # one-line summary under the gauge
    }

A `cell` is {'text', 'cls'?, 'title'?, 'badge'?}. Every renderer draws a cell the
same way: `<td class=cls title=title>text</td>`, or a severity `badge` as a chip.
Formatting (thousands, "N d", ISO dates, short WBS) happens ONCE, here — never in
the renderers — so the three views cannot disagree.

Presentation is derived purely from the stored module dict (kpis + findings), so it
is recomputed identically on import and on the DB read path (like schedule_health).
No calculation logic lives here.
"""

# ── formatting (done once) ────────────────────────────────────────────────
_SEV_CLASS = {'Critical': 't-crit', 'High': 't-high', 'Medium': 't-med', 'Low': 't-low'}


def _num(v):
    try:
        return f"{int(round(float(v or 0))):,}"
    except (TypeError, ValueError):
        return str(v if v is not None else 0)


def _plain(v):
    """Mimic JS number-to-string so the PDF/Excel match the screen exactly:
    99.0 -> '99', 94.2 -> '94.2'. Strings pass through; None shows an em dash."""
    if v is None:
        return '—'
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _pct(v):
    return f"{_plain(v if v is not None else 0)}%"


def _days(v):
    return '—' if v is None else f"{_plain(v)} d"


def _iso(v):
    return str(v)[:10] if v else '—'


def short_wbs(path, n=3):
    if not path:
        return ''
    parts = [p.strip() for p in str(path).split('>')]
    return ' > '.join(parts[-n:])


def _chain(v):
    return ' → '.join(str(n.get('id', '')) for n in (v or []))


# ── cell builder ──────────────────────────────────────────────────────────
def _cell(text='', cls='', title=None, badge=None):
    c = {'text': '' if text is None else str(text)}
    if cls:
        c['cls'] = cls
    if title:
        c['title'] = title
    if badge:
        c['badge'] = badge
    return c


def _cell_for(kind, value):
    """One finding field → one normalized table cell, formatted by column kind."""
    if kind == 'mono':
        return _cell(value, 'mono')
    if kind == 'mut':
        return _cell(value, 'mut')
    if kind == 'num':
        return _cell(value, 'num')
    if kind == 'wbs':
        return _cell(short_wbs(value), title=value or None)
    if kind == 'sev':
        return _cell(value, badge=_SEV_CLASS.get(value, 't-low'))
    if kind == 'days':
        return _cell(_days(value), 'num')
    if kind == 'date':
        return _cell(_iso(value), 'mut')
    if kind == 'chain':
        return _cell(_chain(value), 'mono')
    return _cell(value)   # plain text


# align is 'num' (right) for numeric/day columns, '' otherwise.
_NUM_KINDS = {'num', 'days'}


# ── per-check specs (ported verbatim from ui MODULE_SPECS — single source) ──
# Each column is (label, finding_field, kind). '#' is added by the renderer.
def _v_pct(m, tail):
    return f"{_plain(m.get('pct'))}% {tail}"


SPECS = {
    'dangling': {
        'verdict': lambda m: _v_pct(m, 'of activities have broken start/finish logic (an open end on one side).'),
        'tiles': lambda k: [('Total Activities', _num(k.get('total_activities'))), ('Total Dangling', k.get('total_dangling', 0)),
                            ('Dangling %', _pct(k.get('dangling_pct'))), ('Dangling Start', k.get('start_dangling', 0)),
                            ('Dangling Finish', k.get('finish_dangling', 0)), ('Start + Finish', k.get('both_dangling', 0))],
        'columns': [('Activity ID', 'activity_id', 'mono'), ('Activity Name', 'activity_name', 'text'),
                    ('WBS Path', 'wbs_path', 'wbs'), ('Severity', 'severity', 'sev'), ('Logic Issue', 'logic_issue', 'text'),
                    ('Predecessor(s)', 'predecessors', 'mut'), ('Successor(s)', 'successors', 'mut'),
                    ('Suggested Logic Fix', 'suggested_fix', 'text'), ('Suggested Logic Fix 2', 'suggested_fix_2', 'mut')],
    },
    'open_ends': {
        'verdict': lambda m: _v_pct(m, 'of activities are open on at least one side — no predecessor and/or no successor.'),
        'tiles': lambda k: [('Total Activities', _num(k.get('total_activities'))), ('Open Ends', k.get('open_ends', 0)),
                            ('Open-End %', _pct(k.get('open_end_pct'))), ('No Predecessor', k.get('no_predecessor', 0)),
                            ('No Successor', k.get('no_successor', 0))],
        'columns': [('Activity ID', 'activity_id', 'mono'), ('Activity Name', 'activity_name', 'text'),
                    ('WBS Path', 'wbs_path', 'wbs'), ('Severity', 'severity', 'sev'), ('Issue', 'issue', 'text'),
                    ('Recommendation', 'recommendation', 'mut')],
    },
    'relationship_types': {
        'verdict': lambda m: f"{_plain((m.get('kpis') or {}).get('fs_pct'))}% of relationships are Finish-to-Start; "
                             f"{_plain((m.get('kpis') or {}).get('non_fs'))} are not (DCMA target ≥ 90% FS).",
        'tiles': lambda k: [('Total Relationships', _num(k.get('total_relationships'))), ('FS %', _pct(k.get('fs_pct'))),
                            ('SS %', _pct(k.get('ss_pct'))), ('FF %', _pct(k.get('ff_pct'))), ('SF %', _pct(k.get('sf_pct'))),
                            ('Non-FS', k.get('non_fs', 0))],
        'columns': [('Activity ID', 'activity_id', 'mono'), ('Activity Name', 'activity_name', 'text'),
                    ('WBS Path', 'wbs_path', 'wbs'), ('Predecessor', 'predecessor_display', 'mut'),
                    ('Successor', 'successor_display', 'mut'), ('Severity', 'severity', 'sev'),
                    ('Recommendation', 'recommendation', 'mut')],
    },
    'hard_constraints': {
        'verdict': lambda m: _v_pct(m, 'of activities carry a hard constraint that overrides the network logic.'),
        'tiles': lambda k: [('Total Activities', _num(k.get('total_activities'))), ('Hard Constraints', k.get('hard_count', 0)),
                            ('Hard-Constraint %', _pct(k.get('hard_pct')))],
        'columns': [('Activity ID', 'activity_id', 'mono'), ('Activity Name', 'activity_name', 'text'),
                    ('WBS Path', 'wbs_path', 'wbs'), ('Constraint Type', 'constraint_type', 'text'),
                    ('Constraint Date', 'constraint_date', 'date'), ('Severity', 'severity', 'sev'),
                    ('Recommendation', 'recommendation', 'mut')],
    },
    'high_duration': {
        'verdict': lambda m: f"{_plain(m.get('pct'))}% of activities run longer than {_plain((m.get('kpis') or {}).get('threshold'))} working days.",
        'tiles': lambda k: [('Total Activities', _num(k.get('total_activities'))), ('Over Threshold', k.get('over_threshold', 0)),
                            ('High-Duration %', _pct(k.get('high_pct'))), ('Threshold', _days(k.get('threshold'))),
                            ('Longest', _days(k.get('max_duration')))],
        'columns': [('Activity ID', 'activity_id', 'mono'), ('Activity Name', 'activity_name', 'text'),
                    ('WBS Path', 'wbs_path', 'wbs'), ('Duration', 'duration_days', 'days'), ('Severity', 'severity', 'sev'),
                    ('Recommendation', 'recommendation', 'mut')],
    },
    'leads': {
        'verdict': lambda m: _v_pct(m, 'of relationships are leads (negative lag) — DCMA target 0%.'),
        'tiles': lambda k: [('Total Relationships', _num(k.get('total_relationships'))), ('Leads', k.get('leads', 0)),
                            ('Lead %', _pct(k.get('lead_pct'))), ('Target', f"{k.get('target')}%")],
        'columns': [('Activity ID', 'activity_id', 'mono'), ('Activity Name', 'activity_name', 'text'),
                    ('WBS Path', 'wbs_path', 'wbs'), ('Type', 'rel_type', 'mono'), ('Lag', 'lag_days', 'days'),
                    ('Predecessor', 'predecessor_name', 'mut'), ('Severity', 'severity', 'sev'),
                    ('Recommendation', 'recommendation', 'mut')],
    },
    'negative_float': {
        'verdict': lambda m: _v_pct(m, 'of activities carry negative total float — a baseline must not start with any.'),
        'tiles': lambda k: [('Total Activities', _num(k.get('total_activities'))), ('Negative Float', k.get('negative_count', 0)),
                            ('Negative-Float %', _pct(k.get('neg_pct')))],
        'columns': [('Activity ID', 'activity_id', 'mono'), ('Activity Name', 'activity_name', 'text'),
                    ('WBS Path', 'wbs_path', 'wbs'), ('Total Float', 'total_float_days', 'days'),
                    ('Severity', 'severity', 'sev'), ('Recommendation', 'recommendation', 'mut')],
    },
    'whole_day': {
        'verdict': lambda m: _v_pct(m, 'of activities have a decimal duration that should round to a whole day.'),
        'tiles': lambda k: [('Total Activities', _num(k.get('total_activities'))), ('Decimal Durations', k.get('decimal_count', 0)),
                            ('Decimal %', _pct(k.get('decimal_pct')))],
        'columns': [('Activity ID', 'activity_id', 'mono'), ('Activity Name', 'activity_name', 'text'),
                    ('WBS Path', 'wbs_path', 'wbs'), ('Original', 'original_days', 'days'), ('Rounds To', 'rounds_to', 'days'),
                    ('Calendar', 'calendar', 'mut'), ('Severity', 'severity', 'sev'), ('Recommendation', 'recommendation', 'mut')],
    },
    'cpli': {
        'verdict': lambda m: _cpli_verdict(m),
        'tiles': lambda k: _cpli_tiles(k),
        'columns': [('Activity ID', 'activity_id', 'mono'), ('Activity Name', 'activity_name', 'text'),
                    ('WBS Path', 'wbs_path', 'wbs'), ('Start', 'start', 'date'), ('Finish', 'finish', 'date'),
                    ('Duration', 'duration_days', 'days'), ('Total Float', 'total_float_days', 'days')],
    },
    'circular': {
        'verdict': lambda m: ('No circular logic — the network calculates (F9).'
                              if not ((m.get('kpis') or {}).get('loops'))
                              else f"{(m.get('kpis') or {}).get('loops')} loop(s) block P6's calculation (F9)."),
        'tiles': lambda k: [('Total Activities', _num(k.get('total_activities'))), ('Loops', k.get('loops', 0)),
                            ('Activities in Loops', k.get('activities_in_loops', 0)), ('Longest Loop', k.get('longest_loop', 0)),
                            ('Circular %', _pct(k.get('circular_pct')))],
        'columns': [('Loop', 'loop_index', 'text'), ('Activities', 'activity_count', 'num'),
                    ('Closing Chain', 'chain', 'chain'), ('Recommendation', 'recommendation', 'mut')],
    },
}

# Fallback so an unexpected module never renders blank or wrong.
GENERIC = {
    'verdict': lambda m: _v_pct(m, 'of items flagged.'),
    'tiles': lambda k: [(str(lab).replace('_', ' '), v if isinstance(v, (int, float)) else str(v))
                        for lab, v in list((k or {}).items())[:6]],
    'columns': [('Activity ID', 'activity_id', 'mono'), ('Activity Name', 'activity_name', 'text'),
                ('WBS Path', 'wbs_path', 'wbs'), ('Severity', 'severity', 'sev'), ('Recommendation', 'recommendation', 'mut')],
}


def _cpli_computable(k):
    return k.get('computable') is not False and k.get('cpli') is not None


def _cpli_tiles(k):
    computable = _cpli_computable(k)
    cpl = k.get('critical_path_length_days')
    cpl_txt = '—' if cpl is None else f"{cpl} d{' (cal)' if k.get('cpl_basis') == 'calendar' else ''}"
    return [
        ('CPLI', f"{_plain(k.get('score', k.get('cpli')))}%" if computable else '—'),
        ('Critical Path Length', cpl_txt),
        ('Completion Total Float', _days(k.get('project_total_float_days'))),
        ('DCMA Target', f"{round((k.get('target') or 0.95) * 100)}%"),
        ('Finish Milestone', k.get('finish_milestone_id') or '—'),
    ]


def _cpli_verdict(m):
    k = m.get('kpis') or {}
    if not _cpli_computable(k):
        return 'CPLI not computable — the schedule has no dated finish milestone, or no float on it.'
    tgt = round((k.get('target') or 0.95) * 100)
    return f"CPLI {_plain(m.get('score'))}% — how realistically the finish can still be met (DCMA target {tgt}%)."


# CPLI's CPLI tile needs the module score, which lives on the module, not the kpis.
# Fold it in so `tiles(kpis)` can still read it.
def _cpli_tiles_from_module(m):
    k = dict(m.get('kpis') or {})
    k.setdefault('score', m.get('score'))
    return _cpli_tiles(k)


# ── Scoring transparency: how each check's 0-100 score is derived ──────────
# Unified Schedule Health model: Score = 100 − defect%, one uniform legend.
# CPLI is the exception (its own DCMA formula); Circular is a gate (not weighted).
_UNIFORM_BANDS_TEXT = '≥ 98 Excellent · ≥ 95 Good · ≥ 90 Acceptable · < 90 Critical'

# DCMA 14-Point reference per check — the industry benchmark, shown SEPARATELY
# from the tool's 0-100 score (they are not the same thing).
_DCMA_REF = {
    'dangling':           'DCMA Metric 3 — Missing Logic · benchmark: 0 open ends',
    'open_ends':          'DCMA Metric 3 — Missing Logic · benchmark: 0 open ends',
    'relationship_types': 'DCMA Metric 4 — Relationship Types · benchmark: FS ≥ 90%',
    'leads':              'DCMA Metric 2 — Leads (negative lag) · benchmark: 0',
    'negative_float':     'DCMA Metric 7 — Negative Float · benchmark: 0',
    'hard_constraints':   'DCMA Metric 5 — Hard Constraints · benchmark: 0',
    'high_duration':      'DCMA Metric 8 — High Duration · benchmark: 0',
    'cpli':               'DCMA Metric 13 — Critical Path Length Index · benchmark: CPLI ≥ 95%',
    'whole_day':          'Tool check — calendar-consistent whole-day durations',
    'circular':           'F9 gate — a circular loop stops P6 calculating; not weighted',
}

# defect% derivation per linear check: (count_kpi, total_kpi, noun-phrase).
_DEFECT_NOUN = {
    'dangling':           ('total_dangling', 'total_activities', 'activities have an open end on one side'),
    'open_ends':          ('open_ends', 'total_activities', 'activities are open on a side'),
    'relationship_types': ('non_fs', 'total_relationships', 'relationships are not Finish-to-Start'),
    'leads':              ('leads', 'total_relationships', 'relationships are leads (negative lag)'),
    'negative_float':     ('negative_count', 'total_activities', 'activities carry negative float'),
    'hard_constraints':   ('hard_count', 'total_activities', 'activities carry a hard constraint'),
    'high_duration':      ('over_threshold', 'total_activities', 'activities exceed the duration threshold'),
    'whole_day':          ('decimal_count', 'total_activities', 'activities have a decimal duration'),
}


def _scoring(m):
    """A truthful 'how this score is calculated' descriptor — shown on screen AND
    in the PDF so the 0-100 score is never a black box."""
    mod = m.get('module')
    k = m.get('kpis') or {}
    ref = _DCMA_REF.get(mod, '')

    if mod == 'cpli':
        return {'formula': 'Score = CPLI × 100, where CPLI = (CPL + TF) ÷ CPL',
                'derivation': _cpli_verdict(m), 'bands': _UNIFORM_BANDS_TEXT, 'benchmark': ref}
    if mod == 'circular':
        loops = k.get('loops', 0) or 0
        return {'formula': 'Gate — a circular loop caps the review; not weighted into the score',
                'derivation': ('No loops — the network calculates.' if not loops
                               else f"{loops} loop(s) block P6's calculation (F9)."),
                'bands': '', 'benchmark': ref}
    d = _DEFECT_NOUN.get(mod)
    if not d:
        return None
    count_k, total_k, noun = d
    count, total = k.get(count_k, 0), k.get(total_k, 0)
    defect, score = m.get('pct'), m.get('score')
    derivation = (f"{_num(count)} of {_num(total)} {noun} = {_plain(defect)}%  →  "
                  f"Score = 100 − {_plain(defect)}% = {_plain(score)}")
    return {'formula': 'Score = 100 − defect%', 'derivation': derivation,
            'bands': _UNIFORM_BANDS_TEXT, 'benchmark': ref}


# ── Severity criteria: what makes a finding Critical/High/Medium/Low ───────
# These mirror the ACTUAL rule engine (each module's severity assignment), so the
# legend is the truth, not a colour key. Most checks raise a finding one level when
# it sits on the critical path.
_SEVERITY = {
    'dangling': ('An issue on the critical path is raised one level.', [
        ('Critical', 'Open on both sides, on a critical-path activity'),
        ('High', 'Open on both sides (off path), or open on one side on the critical path'),
        ('Medium', 'Open on one side (start or finish), off the critical path')]),
    'open_ends': ('An issue on the critical path is raised one level.', [
        ('Critical', 'No successor / both sides open, on a critical-path activity'),
        ('High', 'No successor or both open (off path), or no predecessor on the critical path'),
        ('Medium', 'No predecessor, off the critical path')]),
    'relationship_types': ('Impact-based — a non-FS link touching the critical path is raised.', [
        ('Critical', 'Start-to-Finish relationship on the critical path'),
        ('High', 'Start-to-Finish relationship off the critical path (almost always a modelling error)'),
        ('Medium', 'SS / FF relationship touching the critical path'),
        ('Low', 'SS / FF relationship off the critical path')]),
    'hard_constraints': ('A constraint on the critical path is the most serious.', [
        ('Critical', 'Hard constraint on a critical-path activity'),
        ('High', 'Mandatory Start/Finish constraint (off the critical path)'),
        ('Medium', 'Other hard constraint (off the critical path)')]),
    'high_duration': ('An over-long activity on the critical path is raised.', [
        ('High', 'Over the duration threshold, on a critical-path activity'),
        ('Medium', 'Over the duration threshold, off the critical path')]),
    'leads': ('A lead into the critical path is the most serious.', [
        ('Critical', 'Lead (negative lag) into a critical-path activity'),
        ('High', 'Lead (negative lag) off the critical path')]),
    'negative_float': ('Any negative float on a baseline is Critical.', [
        ('Critical', 'Any activity carrying negative total float')]),
    'whole_day': ('A decimal duration on the critical path is raised.', [
        ('High', 'Decimal duration on a critical-path activity'),
        ('Medium', 'Decimal duration off the critical path')]),
    'circular': ('A loop stops P6 calculating — nothing milder applies.', [
        ('Critical', 'Any circular loop (blocks F9)')]),
}


def _severity(m):
    """What makes a finding Critical/High/Medium/Low for this check — the real rules."""
    entry = _SEVERITY.get(m.get('module'))
    if not entry:
        return None
    basis, levels = entry
    return {'basis': basis, 'levels': [{'level': lv, 'criteria': cr} for lv, cr in levels]}


def report_sections(m):
    """The report components the user can tick to include (Preview = PDF = Print),
    in order, each with an `empty` flag so sections with no data are skipped/greyed
    — the same registry the PDF renders from. A global framework: every check exposes
    the same component set."""
    m = m or {}
    has_findings = bool(m.get('findings'))
    return [
        {'key': 'executive',       'label': 'Executive score & KPIs', 'empty': False},
        {'key': 'scoring',         'label': 'Scoring & DCMA legend',   'empty': not _scoring(m)},
        {'key': 'severity',        'label': 'Severity legend',        'empty': not (_severity(m) and has_findings)},
        {'key': 'findings',        'label': 'Detailed findings',      'empty': not has_findings},
        {'key': 'recommendations', 'label': 'Recommendations',        'empty': not has_findings},
    ]


def build_presentation(module_result):
    """The normalized presentation for one module — tiles, columns, rows, verdict."""
    m = module_result or {}
    spec = SPECS.get(m.get('module'), GENERIC)
    k = m.get('kpis') or {}
    findings = m.get('findings') or []

    if m.get('module') == 'cpli':
        raw_tiles = _cpli_tiles_from_module(m)
    else:
        raw_tiles = spec['tiles'](k)
    tiles = [{'label': lab, 'value': _plain(val)} for lab, val in raw_tiles]

    columns = [{'label': lab, 'align': 'num' if kind in _NUM_KINDS else ''}
               for lab, field, kind in spec['columns']]
    rows = [[_cell_for(kind, f.get(field)) for lab, field, kind in spec['columns']]
            for f in findings]

    return {'tiles': tiles, 'columns': columns, 'rows': rows,
            'verdict': spec['verdict'](m), 'scoring': _scoring(m), 'severity': _severity(m),
            'sections': report_sections(m)}
