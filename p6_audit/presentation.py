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


def _one(v):
    """A percentage / score to one decimal (comment 53): 26.84 -> 26.8, 99.0 -> 99."""
    try:
        return _plain(round(float(v), 1))
    except (TypeError, ValueError):
        return _plain(v)


def _pct(v):
    return f"{_one(v if v is not None else 0)}%"


def _whole_days(v):
    """Days as a whole number (comment 53): -10.44 -> -10, 117.6 -> 118 (never '-0')."""
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return str(v)
    return str(0 if n == 0 else n)


def _days(v):
    return '—' if v is None else f"{_whole_days(v)} d"


def float_days_text(v):
    """Total float as P6 holds it, decimals kept (comment 83): -0.05 -> '-0.05 d', -3.0 -> '-3 d'.
    A float smaller than a hundredth of a day keeps the digits that tell it from zero."""
    if v is None:
        return '—'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    r = round(f, 2)
    if r == 0 and f != 0:
        r = round(f, 4)
    if r == 0:
        return '0 d'
    txt = str(int(r)) if float(r).is_integer() else f'{r:.4f}'.rstrip('0').rstrip('.')
    return f'{txt} d'


def _days_exact(v):
    """The Whole-Day check's own finding IS the decimal (51.71 d) — shown as P6 holds it."""
    return '—' if v is None else f"{_plain(v)} d"


def _iso(v):
    return _fmt_date(v) if v else '—'                      # 03-Dec.2026 (comment 46)


_MON = ('', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def _fmt_date(v):
    """ISO 'YYYY-MM-DD' -> '09-Feb.2027' (the one date style, comment 46), matching the screen."""
    if not v:
        return '—'
    p = str(v)[:10].split('-')
    if len(p) == 3 and p[1].isdigit() and p[2].isdigit():
        return f"{int(p[2]):02d}-{_MON[int(p[1])]}.{p[0]}"
    return str(v)


def short_wbs(path, n=3):
    if not path:
        return ''
    parts = [p.strip() for p in str(path).split('>')]
    return ' > '.join(parts[-n:])


def _chain(v):
    return ' → '.join(str(n.get('id', '')) for n in (v or []))


# ── cell builder ──────────────────────────────────────────────────────────
def _date_text(v):
    from utils import date_text          # an ISO date shows as 03-Dec.2026 (comment 46)
    return date_text(v)


def _cell(text='', cls='', title=None, badge=None):
    c = {'text': '' if text is None else str(_date_text(text))}
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
    if kind == 'days_exact':
        return _cell(_days_exact(value), 'num')
    if kind == 'float_days':
        return _cell(float_days_text(value), 'num')
    if kind == 'date':
        return _cell(_iso(value), 'mut')
    if kind == 'chain':
        return _cell(_chain(value), 'mono')
    return _cell(value)   # plain text


# align is 'num' (right) for numeric/day columns, '' otherwise.
_NUM_KINDS = {'num', 'days', 'days_exact', 'float_days'}


# ── per-check specs (ported verbatim from ui MODULE_SPECS — single source) ──
# Each column is (label, finding_field, kind). '#' is added by the renderer.
def _v_pct(m, tail):
    return f"{_plain(m.get('pct'))}% {tail}"


def _type_pct(k, t):
    """'5.1% (252)' — the % with the relationship count it comes from (comment 47)."""
    n = k.get(f'{t}_count')
    return _pct(k.get(f'{t}_pct')) + (f' ({_num(n)})' if n is not None else '')


def _reltype_verdict(k):
    base = (f"{_plain(k.get('fs_pct'))}% of relationships are Finish-to-Start; "
            f"{_plain(k.get('non_fs'))} are not (DCMA target ≥ 90% FS).")
    if k.get('fs_count') is None:
        return base
    total = _num(k.get('total_relationships'))
    return (base + f" How each % is worked out: that type's relationships ÷ all {total} relationships — "
            f"FS {_num(k.get('fs_count'))} · SS {_num(k.get('ss_count'))} · FF {_num(k.get('ff_count'))} · "
            f"SF {_num(k.get('sf_count'))} (e.g. SS % = {_num(k.get('ss_count'))} ÷ {total} = {_pct(k.get('ss_pct'))}).")


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
        'verdict': lambda m: _v_pct(m, "of activities are open on at least one side — no predecessor and/or no successor (as P6's schedule log lists them, every activity type)."),
        'tiles': lambda k: [('Total Activities', _num(k.get('total_activities'))), ('Open Ends', k.get('open_ends', 0)),
                            ('Open-End %', _pct(k.get('open_end_pct'))), ('No Predecessor', k.get('no_predecessor', 0)),
                            ('No Successor', k.get('no_successor', 0))],
        'columns': [('Activity ID', 'activity_id', 'mono'), ('Activity Name', 'activity_name', 'text'),
                    ('WBS Path', 'wbs_path', 'wbs'), ('Severity', 'severity', 'sev'), ('Issue', 'issue', 'text'),
                    ('Recommendation', 'recommendation', 'mut')],
    },
    'relationship_types': {
        'verdict': lambda m: _reltype_verdict(m.get('kpis') or {}),
        'tiles': lambda k: [('Total Relationships', _num(k.get('total_relationships'))),
                            ('FS %', _type_pct(k, 'fs')), ('SS %', _type_pct(k, 'ss')),
                            ('FF %', _type_pct(k, 'ff')), ('SF %', _type_pct(k, 'sf'))],
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
        'verdict': lambda m: (f"{_plain(m.get('pct'))}% of the activities evaluated "
                              f"({(m.get('kpis') or {}).get('scope_label') or 'all WBS'}) run longer than "
                              f"{_plain((m.get('kpis') or {}).get('threshold'))} working days."),
        # the EVALUATION first (the Construction WBS); the whole-schedule figures after it, named so
        'tiles': lambda k: [('WBS Evaluated', k.get('scope_label') or 'All WBS'),
                            (_hd_eval_label(k, 'Activities'), _num(k.get('total_activities'))),
                            (_hd_eval_label(k, 'Over Threshold'), k.get('over_threshold', 0)),
                            ('of which Task Dependent', _num(k.get('scope_task_over'))),
                            ('High-Duration %', _pct(k.get('high_pct'))), ('Threshold', _days(k.get('threshold'))),
                            ('Whole schedule - Activities', _num(k.get('all_activities', k.get('total_activities')))),
                            ('Whole schedule - Over Threshold', _num(k.get('all_over_threshold'))),
                            ('Whole schedule - Longest', _days(k.get('max_duration')))]
                           + ([] if k.get('view_default', True) else
                              [('Also Shown (picked WBS)', k.get('view_label') or ''),
                               ('Over Threshold (picked WBS)',
                                f"{k.get('view_over', 0):,} of {k.get('view_activities', 0):,} - {_plain(k.get('view_pct'))}%")]),
        'columns': [('Activity ID', 'activity_id', 'mono'), ('Activity Name', 'activity_name', 'text'),
                    ('Activity Type', 'activity_type', 'text'),
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
        'verdict': lambda m: _v_pct(m, 'of the remaining activities carry negative total float — a baseline must not start with any.'),
        'tiles': lambda k: [('Total Activities', _num(k.get('total_activities'))),
                            ('Remaining Activities', _num(k.get('remaining_activities', k.get('total_activities')))),
                            ('Negative Float', k.get('negative_count', 0)),
                            ('Negative-Float % (of remaining)', _pct(k.get('neg_pct')))],
        'columns': [('Activity ID', 'activity_id', 'mono'), ('Activity Name', 'activity_name', 'text'),
                    ('WBS Path', 'wbs_path', 'wbs'), ('Total Float', 'total_float_days', 'float_days'),
                    ('Severity', 'severity', 'sev'), ('Recommendation', 'recommendation', 'mut')],
    },
    'whole_day': {
        'verdict': lambda m: _v_pct(m, 'of activities have a decimal duration that should round to a whole day.'),
        'tiles': lambda k: [('Total Activities', _num(k.get('total_activities'))), ('Decimal Durations', k.get('decimal_count', 0)),
                            ('Decimal %', _pct(k.get('decimal_pct')))],
        'columns': [('Activity ID', 'activity_id', 'mono'), ('Activity Name', 'activity_name', 'text'),
                    ('WBS Path', 'wbs_path', 'wbs'), ('Original', 'original_days', 'days_exact'), ('Rounds To', 'rounds_to', 'days'),
                    ('Calendar', 'calendar', 'mut'), ('Hrs/day', 'day_hours', 'mut'), ('Cause', 'cause_label', 'text'),
                    ('Severity', 'severity', 'sev'), ('Recommendation', 'recommendation', 'mut')],
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
    # the sub-feature is scored by critical-path DENSITY; computable when there is at
    # least one task-dependent activity to measure the critical share against.
    return k.get('computable') is not False and k.get('critical_pct') is not None


def _cpli_tiles(k):
    cpl = k.get('critical_path_length_days')
    cpl_txt = '—' if cpl is None else f"{_plain(cpl)} d{' (cal)' if k.get('cpl_basis') == 'calendar' else ''}"
    cpli_ratio = k.get('cpli')
    return [
        ('Total Activities', _num(k.get('total_activities'))),
        ('Remaining Activities', _num(k.get('remaining_activities', k.get('total_activities')))),
        ('Critical Activities', _num(k.get('critical_count')) if k.get('critical_count') is not None else '—'),
        ('Critical % (of remaining)', _pct(k.get('critical_pct')) if k.get('critical_pct') is not None else '—'),
        ('CPLI', f"{_plain(k.get('cpli_pct'))}%" if cpli_ratio is not None else '—'),
        ('Completion Total Float', float_days_text(k.get('project_total_float_days'))),
        ('Critical Path Length', cpl_txt),
        ('Finish Milestone', _fmt_date(k.get('finish_date')) if k.get('finish_date') else (k.get('finish_milestone_id') or '—')),
    ]


def _cpli_verdict(m):
    k = m.get('kpis') or {}
    if not _cpli_computable(k):
        return 'Critical-path density not computable — no task-dependent activities to assess.'
    cp = _plain(k.get('critical_pct'))
    sc = _plain(m.get('score'))
    ratio = k.get('cpli_pct')
    ctx = '' if ratio is None else f" Context — CPLI ratio (CPL + TF) ÷ CPL = {_plain(ratio)}% (DCMA Metric 13)."
    return (f"{cp}% of the remaining activities are critical in P6 → score {sc}. "
            f"Fewer critical activities = a less fragile schedule.{ctx}")


# CPLI's CPLI tile needs the module score, which lives on the module, not the kpis.
# Fold it in so `tiles(kpis)` can still read it.
def _cpli_tiles_from_module(m):
    k = dict(m.get('kpis') or {})
    k.setdefault('score', m.get('score'))
    return _cpli_tiles(k)


# ── Scoring transparency: how each check's 0-100 score is derived ──────────
# Unified Schedule Health model: Score = 100 − defect%, one uniform legend.
# CPLI is the exception (its own DCMA formula); Circular is a gate (not weighted).
_UNIFORM_BANDS_TEXT = 'Pass ≥ 95 · Review 90–95 · Critical < 90'

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
    'cpli':               'Critical-path density (fragility) — fewer critical = healthier · CPLI ratio ≥ 95% shown as context (DCMA Metric 13)',
    'whole_day':          'Tool check — calendar-consistent whole-day durations',
    'circular':           'F9 gate — a circular loop stops P6 calculating; not weighted',
}

# defect% derivation per linear check: (count_kpi, total_kpi, noun-phrase).
_DEFECT_NOUN = {
    'dangling':           ('total_dangling', 'total_activities', 'activities have an open end on one side'),
    'open_ends':          ('open_ends', 'total_activities', 'activities are open on a side'),
    'relationship_types': ('non_fs', 'total_relationships', 'relationships are not Finish-to-Start'),
    'leads':              ('leads', 'total_relationships', 'relationships are leads (negative lag)'),
    'negative_float':     ('negative_count', 'remaining_activities', 'remaining activities carry negative float'),
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
        return {'formula': 'Score = critical-path density — the share of activities on the critical path',
                'derivation': _cpli_verdict(m),
                'bands': ('≤ 25% → 100 · ≤ 30% → 90 · ≤ 35% → 85 · ≤ 40% → 75 · > 40% → 60'
                          '  ·  band: Pass ≥ 95 · Review 90–95 · Critical < 90'),
                'benchmark': ref}
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
    — the same registry the PDF renders from. A GLOBAL framework: every check (and
    every future feature) exposes its component set here and inherits the picker
    automatically. OOS / Lag / Float carry their own bespoke section lists."""
    m = m or {}
    mod = m.get('module')
    has_findings = bool(m.get('findings'))
    k = m.get('kpis') or {}

    if mod == 'out_of_sequence':
        return [
            {'key': 'executive',  'label': 'Executive dashboard',       'empty': False},
            {'key': 'wbs',        'label': 'Distribution by WBS',        'empty': not m.get('wbs_summary')},
            {'key': 'findings',   'label': 'Out-of-sequence review log', 'empty': not has_findings},
            {'key': 'cpi',        'label': 'Critical path impact',       'empty': False},
            {'key': 'conclusion', 'label': 'Executive conclusion',       'empty': not k.get('executive_conclusion')},
        ]
    if mod == 'lag_lead':
        return [
            {'key': 'summary',  'label': 'Summary',              'empty': False},
            {'key': 'charts',   'label': 'Lag charts',           'empty': not (k.get('by_type') or m.get('wbs_summary'))},
            {'key': 'findings', 'label': 'Lag & lead register',  'empty': not has_findings},
        ]
    if mod == 'float':
        mgmt = m.get('mgmt') or {}
        has_mgmt = bool((mgmt.get('stats') or {}).get('total'))
        return [
            {'key': 'executive',  'label': 'Executive dashboard',        'empty': not has_mgmt},
            {'key': 'statistics', 'label': 'Schedule statistics',        'empty': not has_mgmt},
            {'key': 'indicators', 'label': 'Float indicators',           'empty': not has_mgmt},
            {'key': 'wbs',        'label': 'Float distribution by WBS',   'empty': not mgmt.get('wbs')},
            {'key': 'conclusion', 'label': 'Executive conclusion',       'empty': not mgmt.get('conclusion')},
        ]
    return [
        {'key': 'executive',       'label': 'Executive score & KPIs', 'empty': False},
        {'key': 'scoring',         'label': 'Scoring & DCMA legend',   'empty': not _scoring(m)},
        {'key': 'severity',        'label': 'Severity legend',        'empty': not (_severity(m) and has_findings)},
        {'key': 'findings',        'label': 'Detailed findings',      'empty': not has_findings},
        {'key': 'recommendations', 'label': 'Recommendations',        'empty': not has_findings},
    ]


# checks that examine the task activities only (Task / Resource Dependent, completed included)
_TASK_BASED = {'dangling', 'hard_constraints', 'whole_day'}
# checks on relationships: P6's activity total shown beside them for context (comment 47;
# comment 80 took 'Remaining Activities' and 'Non-FS' off the Relationship Types report)
_ACTIVITY_CONTEXT = {'relationship_types'}
# comment 81: what the 'Task Activities Checked' tile counts, said in words under the tiles
TASKS_CHECKED_LABEL = 'Task Activities Checked'
TASKS_CHECKED_NOTE = ('Remaining Activities = every activity that is not completed yet (Not Started + In Progress), '
                      'of every type - the count P6 shows. '
                      'Task Activities Checked = the activities this check examines: Task Dependent and '
                      'Resource Dependent activities, completed ones included. Milestones, Level of Effort '
                      'and WBS Summary activities are not checked, so this figure is lower than Total Activities. '
                      'The two count different things: one leaves out completed activities, the other leaves out '
                      'milestones, Level of Effort and WBS Summary activities.')


_P6_FILTERS = (('start', 'Start Dangling Activity', 'Predecessor Details', ('FS', 'SS')),
               ('finish', 'Dangling Finish Activity', 'Successor Details', ('FS', 'FF')))
_P6_HIDDEN_MAX = 50


def _p6_hidden_row(h):
    """One hidden activity, walked through the P6 filter lines: the column text as P6 reads it (the
    misleading letters and the real types marked) and the verdict of each filter line."""
    side = h['side']
    _key, _name, param, letters = next(x for x in _P6_FILTERS if x[0] == side)
    segs, marked = [], False
    for i, (aid, typ) in enumerate(h['ties']):
        if i:
            segs.append([', ', ''])
        at = aid.upper().find(h['letters']) if (aid == h['linked_id'] and not marked) else -1
        if at >= 0:
            marked = True
            n = len(h['letters'])
            segs += [[aid[:at], ''], [aid[at:at + n], 'hit'], [aid[at + n:], '']]
        else:
            segs.append([aid, ''])
        segs += [[': ', ''], [typ, 'real']]
    lines = [{'text': f'Filter line 1 - {param} is not blank?', 'ok': True, 'verdict': 'passes'}]
    failed = False
    for n, letter in enumerate(letters, start=2):
        fail = (letter == h['letters'])
        failed = failed or fail
        lines.append({'text': f'Filter line {n} - does not contain "{letter}"?', 'ok': not fail,
                      'verdict': f'fails - P6 finds "{letter}" inside the Activity ID' if fail else 'passes'})
    types = ', '.join(sorted({typ for _aid, typ in h['ties']}))
    end = 'start' if side == 'start' else 'finish'
    link = 'predecessor' if side == 'start' else 'successor'
    return {'activity_id': h['activity_id'], 'side': 'Start' if side == 'start' else 'Finish',
            'param': param, 'segments': [s for s in segs if s[0]], 'lines': lines,
            'letters': h['letters'], 'linked_id': h['linked_id'], 'real': f'{types} - {end} not driven',
            'result': f'{h["activity_id"]} is left out of the {_name} list.',
            'reality': f'no {link} is of a type that drives its {end} ({types} only), so it is dangling.'}


def dangling_p6_check(k):
    """The 'P6 filter check' panel under the Dangling tiles: the two P6 filters with what each
    lists, why the two lists overlap, the bridge from P6's number to this report's, and every
    dangling activity the P6 text filter leaves out. Built once here; the screen, the PDF / Word
    report and the Excel sheet all draw it."""
    p6 = (k or {}).get('p6_filter')
    if not isinstance(p6, dict):
        return None
    total = int(k.get('total_dangling') or 0)
    start, finish, both, unique = (int(p6.get(x) or 0) for x in ('start', 'finish', 'both', 'unique'))
    other, opened, hid = (int(p6.get(x) or 0) for x in ('other_types', 'open_ends', 'hidden_activities'))
    bridge = [{'op': '', 'n': unique, 'label': 'your P6 filters show', 'kind': ''}]
    if other:
        bridge.append({'op': '-', 'n': other, 'kind': 'h',
                       'label': 'milestones / Level of Effort / WBS summaries (not task activities)'})
    if hid:
        bridge.append({'op': '+', 'n': hid, 'label': 'dangling, but hidden from the P6 filter', 'kind': 'h'})
    if opened:
        bridge.append({'op': '+', 'n': opened, 'kind': 'h',
                       'label': 'no predecessor or no successor at all (P6 filters leave these out)'})
    bridge.append({'op': '=', 'n': total, 'label': 'this report (true count)', 'kind': 't'})
    hidden = [_p6_hidden_row(h) for h in (p6.get('hidden') or [])[:_P6_HIDDEN_MAX]]
    return {
        'title': 'P6 filter check - why P6 may show a different number',
        'match': not (other or hid or opened),
        'match_text': f'Matches your P6 filters: P6 shows {unique}, this report counts {total}.',
        'filters': [{'name': name, 'param': param, 'values': list(letters), 'count': p6.get(key) or 0}
                    for key, name, param, letters in _P6_FILTERS],
        'both': both,
        'overlap': [{'op': '', 'n': start - both, 'label': 'only in Start Dangling', 'kind': ''},
                    {'op': '+', 'n': both, 'label': 'in both filters (counted once)', 'kind': 'b'},
                    {'op': '+', 'n': finish - both, 'label': 'only in Dangling Finish', 'kind': ''},
                    {'op': '=', 'n': unique, 'label': 'different activities in P6', 'kind': 't'}],
        'overlap_title': f'Why {start} + {finish} is {unique} activit{"y" if unique == 1 else "ies"}, not {start + finish}',
        'overlap_note': ('An activity that is dangling at both ends appears in both filters. '
                         'It is one activity, so it is counted once.'),
        'short': f'Short form: {start} + {finish} - {both} = {unique}.',
        'bridge': bridge, 'total': total,
        'hidden': hidden, 'hidden_total': len(p6.get('hidden') or []),
        'legend': [['hit', 'letters inside the Activity ID - the P6 filter reads them as a relationship type'],
                   ['real', 'the real relationship type - what this report reads']],
    }


def _tiles_note_with_figures(p6c, raw_tiles):
    """The Remaining vs Task Activities Checked note, led by this schedule's own numbers."""
    try:
        total, remaining = int(p6c.get('total')), int(p6c.get('remaining'))
        checked = next(int(str(v).replace(',', '')) for lab, v in raw_tiles if lab == TASKS_CHECKED_LABEL)
    except (TypeError, ValueError, StopIteration):
        return TASKS_CHECKED_NOTE
    done, skipped = total - remaining, total - checked
    if done < 0 or skipped < 0:
        return TASKS_CHECKED_NOTE
    return (f'In this schedule: Total Activities {total:,}. '
            f'Remaining Activities {remaining:,} = {total:,} total - {done:,} completed. '
            f'Task Activities Checked {checked:,} = {total:,} total - {skipped:,} milestones, '
            f'Level of Effort and WBS Summary activities. ' + TASKS_CHECKED_NOTE)


def _scope_text(k):
    """What the High Duration evaluation considers (Construction, always) and what the planner
    picked to see beside it."""
    names = k.get('scope_wbs') or []
    if not names:
        return ''
    total, every = k.get('total_activities') or 0, k.get('all_activities') or 0
    thr = _plain(k.get('threshold', 44))
    if k.get('scope_fallback'):
        lead = (f'No WBS of this schedule is named Construction, so the evaluation considers every WBS '
                f'({total:,} activities).')
    else:
        lead = (f"The {thr}-working-day limit is a construction rule: the evaluation (score, band and "
                f"Summary) considers the Construction WBS only, by default - {', '.join(names)}, "
                f"{total:,} of the {every:,} activities.")
    lead += (' The WBS scope is an additional option: picking other WBS shows their count and their '
             'activities - it does not change the evaluation.')
    if not k.get('view_default', True):
        lead += (f" Shown as picked: {k.get('view_label')} - {k.get('view_over', 0):,} of "
                 f"{k.get('view_activities', 0):,} activities over the limit ({_plain(k.get('view_pct'))}%).")
    return lead


def _hd_eval_label(k, what):
    """'Construction - Over Threshold' (or 'All WBS - ...' when no WBS is named construction)."""
    return ('All WBS' if k.get('scope_fallback') else 'Construction') + ' - ' + what


def p6_wbs_table(m):
    """The check's figures per major WBS, each beside P6's own count of the activities under
    that WBS band (every type, completed included) - {'title', 'note', 'headers', 'rows',
    'total'} for the screen, the report and Excel. None when the result carries no WBS rows."""
    mod, k = m.get('module'), (m.get('kpis') or {})
    thr = _plain(k.get('threshold', 44))
    if mod == 'cpli':
        src = [r for r in (m.get('wbs_summary') or []) if isinstance(r, dict) and 'critical' in r]
        cols = [('Activities in P6', 'activities'), ('Not Completed', 'remaining'), ('Critical', 'critical')]
        title = 'Critical activities by major WBS'
        note = ("Activities in P6 = every activity under the WBS band, as P6 counts it (every type, completed "
                "included). Critical = P6's Critical filter: not completed and flagged Critical.")
    elif mod == 'float':
        src = [r for r in ((m.get('mgmt') or {}).get('p6_wbs') or []) if isinstance(r, dict)]
        thr = _plain(k.get('threshold', 44))
        cols = [('Activities in P6', 'activities'), ('Not Completed', 'remaining'),
                (f'Total Float > {thr} d', 'over'), ('Critical', 'critical'), ('Negative Float', 'negative')]
        title = 'Float by major WBS'
        note = (f"Activities in P6 = every activity under the WBS band, as P6 counts it. Total Float > {thr} d = "
                f"P6's filter 'Total Float is greater than {thr}d' (a completed activity has no float).")
    elif mod == 'high_duration':
        src = [r for r in ((m.get('mgmt') or {}).get('wbs') or []) if isinstance(r, dict) and 'task_over' in r]
        cols = [('Activities in P6', 'activities'), (f'Original Duration > {thr} d', 'over'),
                ('of which Task Dependent', 'task_over')]
        title = 'High duration by WBS'
        note = (f"Original Duration > {thr} d = what P6 lists under that WBS with the filter 'Original Duration is "
                f"greater than {thr}d' (every activity type). The score counts the Construction WBS only.")
    else:
        return None
    if not src:
        return None
    rows = [[r.get('wbs') or '(no WBS)'] + [f"{int(r.get(f) or 0):,}" for _l, f in cols] for r in src]
    total = ['Whole schedule'] + [f"{sum(int(r.get(f) or 0) for r in src):,}" for _l, f in cols]
    return {'title': title, 'note': note, 'headers': ['Major WBS (as named in P6)'] + [l for l, _f in cols],
            'rows': rows, 'total': total}


def _critical_split(k):
    """'380 = 360 Task Dependent + 12 milestones + 8 Level of Effort' - the critical count by type."""
    parts = [(k.get('critical_task'), 'Task Dependent'), (k.get('critical_resource'), 'Resource Dependent'),
             (k.get('critical_milestone'), 'milestones'), (k.get('critical_loe'), 'Level of Effort'),
             (k.get('critical_wbs_summary'), 'WBS Summary')]
    parts = [f'{n:,} {name}' for n, name in parts if n]
    if not parts or k.get('critical_count') is None:
        return None
    return (f"Critical Activities {k['critical_count']:,} = " + ' + '.join(parts) + ". The same list as P6's "
            "Critical filter: In Progress and Not Started activities whose total float is within the project's "
            "critical limit. Level of Effort and WBS Summary activities are never Critical in P6, and neither "
            "is completed work.")


def high_duration_figures_note(k):
    """Every High Duration figure, worked out with this schedule's own numbers."""
    if not k.get('scope_wbs') or k.get('all_activities') is None:
        return None
    every, total, over = k.get('all_activities') or 0, k.get('total_activities') or 0, k.get('over_threshold') or 0
    thr, pct = _plain(k.get('threshold', 44)), _plain(k.get('high_pct'))
    score = _plain(round(100.0 - (k.get('high_pct') or 0), 1))
    where = 'the whole schedule' if k.get('scope_fallback') else f"the Construction WBS ({', '.join(k['scope_wbs'])})"
    task = k.get('scope_task_over') or 0
    return (f'In this schedule: Total Activities {every:,}. '
            f'Activities evaluated {total:,} = every activity under {where}, as P6 counts them. '
            f"Over Threshold {over:,} = the activities P6 lists there with the filter 'Original Duration is greater "
            f"than {thr}d' = {task:,} Task Dependent + {over - task:,} of other types. "
            f'High-Duration % {pct}% = {over:,} / {total:,}. Score {score} = 100 - {pct}. '
            f"Whole schedule - Over Threshold {k.get('all_over_threshold', 0):,} = the same filter without the WBS. "
            f"Longest {_plain(k.get('max_duration'))} d = the longest Original Duration in the schedule.")


def high_duration_p6_filter(k):
    """The P6 filter that lists the same activities as the High Duration list (review tip 4)."""
    names = k.get('view_wbs') or k.get('scope_wbs') or []
    if not names:
        return None
    thr = _plain(k.get('threshold', 44))
    wbs = '' if k.get('view_label') == 'All WBS' else ' and WBS is under ' + ' or '.join(names)
    n = k.get('view_over', k.get('over_threshold', 0))
    return (f"Check it in P6: filter "
            f"Original Duration is greater than {thr}d{wbs} - P6 lists {n:,} activities, "
            'the same activities as listed in this report.')


def hours_basis_text(k):
    """How hours become days (review decision 2026-10-11): each activity on the calendar assigned
    to it. None when the result carries no basis (an older import)."""
    b = k.get('hours_basis') if isinstance(k.get('hours_basis'), dict) else None
    days = (b or {}).get('days') or []
    if not days:
        return None
    text = "Days = hours \u00f7 the hours per day of the calendar assigned to each activity"
    if len(days) == 1:
        return text + f" - every activity of this schedule is on a calendar of {_plain(float(days[0]['hours']))} h/day."
    parts = ', '.join(f"{_plain(float(d['hours']))} h/day: {d['activities']:,} activities ({_plain(d['pct'])}%)"
                      for d in days)
    return text + f' ({parts}).'


def _highlight_note(m):
    """The highlighted note under a check's tiles (review comments 1, 2, 9) - what the check
    covers, said once for the screen, the PDF / Word report and Excel. None when there is none."""
    mod, k = m.get('module'), (m.get('kpis') or {})
    if mod == 'dangling':
        return ('This check covers Task Dependent and Resource Dependent activities only. '
                'Milestones, Level of Effort and WBS Summary activities are not checked for dangling logic.')
    if mod == 'high_duration':
        return (f"This check counts what P6 lists with the filter 'Original Duration is greater than "
                f"{_plain(k.get('threshold', 44))}d' and the WBS under Construction - every activity type, "
                'as P6 lists them. ' + _scope_text(k))
    if mod == 'negative_float':
        neg, frac = k.get('negative_count') or 0, k.get('fraction_count') or 0
        if neg and frac * 2 > neg:
            half = _plain(k.get('fraction_days', 0.5))
            lead = (f'All {neg:,} negative-float activities are' if frac == neg
                    else f'{frac:,} of the {neg:,} negative-float activities are')
            return (f'{lead} negative by no more than {half} day (most negative: '
                    f"{float_days_text(k.get('most_negative'))}). This is decimal (part-day) float in the "
                    'baseline - it comes from decimal durations, not from a delay to the finish. '
                    "The figures are computed from the schedule's own early and late dates.")
    return None


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
    p6c = m.get('p6_counts') or {}
    tiles_note = None
    if p6c and m.get('module') in _TASK_BASED:
        # comment 48: P6's own totals first — every activity (completed included) and the ones
        # still to do — then this check's own base, which is the task activities it examines
        raw_tiles = ([('Total Activities', _num(p6c.get('total'))), ('Remaining Activities', _num(p6c.get('remaining')))]
                     + [((TASKS_CHECKED_LABEL if lab == 'Total Activities' else lab), val) for lab, val in raw_tiles])
        tiles_note = _tiles_note_with_figures(p6c, raw_tiles)
    if p6c and m.get('module') in _ACTIVITY_CONTEXT:
        raw_tiles = [('Total Activities', _num(p6c.get('total')))] + list(raw_tiles)
    tiles = [{'label': lab, 'value': _plain(val)} for lab, val in raw_tiles]

    columns = [{'label': lab, 'align': 'num' if kind in _NUM_KINDS else ''}
               for lab, field, kind in spec['columns']]
    rows = [[_cell_for(kind, f.get(field)) for lab, field, kind in spec['columns']]
            for f in findings]

    extra = {}
    if m.get('module') == 'dangling':
        check = dangling_p6_check(k)
        if check:
            extra['p6_check'] = check
    extra = dict(extra)
    highlight = _highlight_note(m)
    # every highlighted line under the tiles, in order: what the check covers, then the day basis
    highlights = [t for t in (highlight, hours_basis_text(k)) if t]
    if m.get('module') == 'cpli' and _critical_split(k):
        tiles_note = _critical_split(k)
    extra['wbs_table'] = p6_wbs_table(m)
    if m.get('module') == 'high_duration':
        tiles_note = high_duration_figures_note(k)
        extra['p6_filter'] = high_duration_p6_filter(k)
        extra['wbs_scope'] = [{'wbs': r.get('wbs'), 'activities': r.get('activities', 0), 'over': r.get('over', 0),
                               'pct': r.get('pct', 0), 'counted': bool(r.get('counted')),
                               'evaluated': bool(r.get('evaluated')),
                               'is_construction': bool(r.get('is_construction'))}
                              for r in ((m.get('mgmt') or {}).get('wbs') or []) if isinstance(r, dict)]
    return {**extra, 'tiles': tiles, 'tiles_note': tiles_note, 'highlight': highlight,
            'highlights': highlights, 'columns': columns, 'rows': rows,
            'verdict': spec['verdict'](m), 'scoring': _scoring(m), 'severity': _severity(m),
            'sections': report_sections(m)}
