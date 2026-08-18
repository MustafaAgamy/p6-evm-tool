"""Schedule Health roll-up (Schedule Health Review).

Turns the isolated module results into ONE weighted Schedule Health %, exactly as
locked on 2026-08-12: nine weighted sub-features summing to 100, two of them merged
from more than one module, and circular logic as a GATE rather than a weight.

Score-then-aggregate (Decision 006): every module scores itself in isolation and
this step only combines them. Nothing here re-reads the schedule.

  * merged sub-feature = the LOWER of its parts — a check is only as good as its
    weakest half, so a clean Leads score cannot hide negative float
  * points   = score x weight / 100
  * overall  = the sum of the points, with the weights renormalised over the
    sub-features that could actually be computed, so a check the file cannot
    support redistributes its weight instead of scoring a free 100
  * circular logic = gate. It never scores into the total, but while a loop exists
    P6 cannot F9, so the review comes back `blocking` and every date/float-driven
    sub-feature is flagged provisional until the loop is cleared.
"""
from p6_audit.scoring import uniform_grade

# Locked structure and weights (sum 100). `parts` are module keys; a sub-feature
# with more than one part scores the lower of them.
SUB_FEATURES = [
    {'key': 'milestones_constraints', 'name': 'Milestone Check', 'weight': 15,
     'parts': ['hard_constraints']},
    {'key': 'cpli',                   'name': 'Critical Path / CPLI',     'weight': 15,
     'parts': ['cpli']},
    {'key': 'float',                  'name': 'Float Analysis',           'weight': 15,
     'parts': ['float']},
    {'key': 'dangling',               'name': 'Dangling Activities',      'weight': 15,
     'parts': ['dangling']},
    {'key': 'whole_day',              'name': 'Whole-day Durations',      'weight': 10,
     'parts': ['whole_day']},
    {'key': 'leads_negative_float',   'name': 'Leads & Negative Float',   'weight': 10,
     'parts': ['leads', 'negative_float']},
    {'key': 'open_ends',              'name': 'Open Ends',                'weight': 10,
     'parts': ['open_ends']},
    {'key': 'relationship_types',     'name': 'Relationship Types',       'weight': 5,
     'parts': ['relationship_types']},
    {'key': 'high_duration',          'name': 'High Duration',            'weight': 5,
     'parts': ['high_duration']},
]

GATE_MODULE = 'circular'

# While a loop blocks F9, P6's dates and floats are not trustworthy, so anything
# derived from them is reported provisional rather than scored as fact.
PROVISIONAL_ON_LOOP = {'float', 'cpli', 'high_duration', 'leads_negative_float'}

# What to do about a sub-feature when its own findings do not carry a fix line —
# Dangling words its advice as suggested_fix, and the CPLI driving path is a route,
# not a defect list, so neither hands us a sentence.
_DEFAULT_ACTION = {
    'milestones_constraints': 'Review the hard constraints — a constraint later than the '
                              'logic-driven date is masking a delay',
    'cpli':                   'Recover the driving path so the completion milestone carries '
                              'zero or positive total float',
    'float':                  'Add the missing successors to the high-float activities',
    'dangling':               'Give each dangling activity the predecessor or successor its '
                              'register suggests',
    'whole_day':              'Round the decimal durations to whole days (no calendar change)',
    'leads_negative_float':   'Remove the negative lags and recover the negative float',
    'open_ends':              'Link every open end — only the start and finish milestones may '
                              'be open',
    'relationship_types':     'Re-type the non-FS links where the finish really drives the '
                              'successor',
    'high_duration':          'Break the over-long activities down, unless the duration is '
                              'quantity-driven',
}

# Pass / Review thresholds per sub-feature. Default is the uniform legend; a check
# whose DCMA target differs overrides it (FS >= 90% for relationship types).
_DEFAULT_THRESHOLDS = (95.0, 90.0)
_THRESHOLDS = {'relationship_types': (90.0, 85.0)}


def _thresholds(key):
    return _THRESHOLDS.get(key, _DEFAULT_THRESHOLDS)


def status_for(key, score):
    """Pass / Review / Critical — the three states the checks-status donut shows."""
    if score is None:
        return 'Not computed'
    pass_at, review_at = _thresholds(key)
    if score >= pass_at:
        return 'Pass'
    if score >= review_at:
        return 'Review'
    return 'Critical'


def _computable(module_result):
    """A module may declare itself uncomputable on this file (CPLI does when the
    schedule carries no dated finish or no float on it). Anything that does not
    declare otherwise counts."""
    return bool(module_result.get('kpis', {}).get('computable', True))


def _discipline(wbs_path):
    """The WBS level planners read as the discipline — one below the project root,
    falling back to the only level there is."""
    parts = [p.strip() for p in (wbs_path or '').split(' > ') if p.strip()]
    if not parts:
        return '(no WBS)'
    return parts[1] if len(parts) >= 2 else parts[0]


def _sub_features(modules):
    """One row per locked sub-feature, worst score first."""
    rows = []
    for rank, spec in enumerate(SUB_FEATURES):
        parts = [(k, modules[k]) for k in spec['parts'] if k in modules]
        usable = [(k, m) for k, m in parts if _computable(m)]
        score = min((m['score'] for _, m in usable), default=None)
        driver = None
        if usable:
            driver = min(usable, key=lambda km: km[1]['score'])[0]
        rows.append({
            'key':        spec['key'],
            'name':       spec['name'],
            # position in the locked list — the rail reads in this order, the
            # composition table re-sorts worst-first
            'rank':       rank,
            'weight':     spec['weight'],
            'score':      score,
            'grade':      uniform_grade(score) if score is not None else None,
            'status':     status_for(spec['key'], score),
            'available':  score is not None,
            'modules':    [k for k, _ in parts],
            # which part set the score — the merged rows are only as good as this one
            'driver':     driver,
            'findings':   sum(len(m.get('findings') or []) for _, m in parts),
        })
    rows.sort(key=lambda r: (r['score'] is None, r['score'] if r['score'] is not None else 0,
                             -r['weight'], r['name']))
    return rows


def _apply_weights(rows):
    """Renormalise the weights over the available sub-features and set the points.

    A check the file cannot support must not score a free 100 into the total, and
    must not silently shrink the total either — its weight is redistributed across
    the checks that did run, in proportion.
    """
    available_weight = sum(r['weight'] for r in rows if r['available'])
    for r in rows:
        if not r['available'] or not available_weight:
            r['effective_weight'] = 0.0
            r['points'] = None
            continue
        eff = r['weight'] * 100.0 / available_weight
        r['effective_weight'] = round(eff, 1)
        r['points'] = round(r['score'] * eff / 100.0, 1)
    return available_weight


def _verdict(score, blocking):
    """The submission call, in the words the report and the dashboard both use."""
    if blocking:
        return ('Blocked',
                'A circular loop stops P6 from calculating this schedule. Break the loop '
                'and re-run — until then the date and float checks are provisional.')
    if score is None:
        return ('Not computed', 'No sub-feature could be scored on this file.')
    # Ibrahim's rule: a baseline is acceptable to submit at 80% or better.
    if score >= 90:
        return ('Ready to submit',
                'Overall Schedule Health is well above the 80% submission standard — no '
                'sub-feature needs work before submission.')
    if score >= 80:
        return ('Acceptable to submit',
                'Overall Schedule Health meets the 80% submission standard; clear the checks '
                'below their targets when you can.')
    return ('Not ready to submit',
            'Overall Schedule Health is below the 80% submission standard — clear the critical '
            'checks and re-run for a score of 80 or better.')


def _problem_areas(modules, rows):
    """Where the findings actually sit — share of all weighted findings by WBS
    discipline. The gate module is left out; it is not a weighted defect count."""
    counted = {}
    total = 0
    keys = {k for r in rows for k in r['modules']}
    for key in keys:
        for f in modules.get(key, {}).get('findings') or []:
            if 'wbs_path' not in f:
                continue          # loop chains and other non-activity rows
            name = _discipline(f.get('wbs_path'))
            counted[name] = counted.get(name, 0) + 1
            total += 1
    areas = [{'name': n, 'findings': c, 'pct': round(100.0 * c / total, 1)}
             for n, c in counted.items()]
    areas.sort(key=lambda a: (-a['findings'], a['name']))
    return {'total_findings': total, 'areas': areas}


def _fix_first(modules, rows, limit=5):
    """Worst-first by the points a fix would actually win back — a weak check on a
    heavy weight beats a slightly weaker one on a light weight."""
    out = []
    for r in rows:
        if not r['available'] or r['score'] >= 100:
            continue
        lift = (100.0 - r['score']) * r['effective_weight'] / 100.0
        rec = ''
        for key in ([r['driver']] if r['driver'] else r['modules']):
            for f in modules.get(key, {}).get('findings') or []:
                rec = f.get('recommendation') or f.get('suggested_fix') or ''
                if rec:
                    break
            if rec:
                break
        rec = rec or _DEFAULT_ACTION.get(r['key'], '')
        out.append({'key': r['key'], 'name': r['name'], 'score': r['score'],
                    'weight': r['weight'], 'lift': round(lift, 1), 'recommendation': rec})
    out.sort(key=lambda x: (-x['lift'], x['name']))
    return out[:limit]


def schedule_health(modules):
    """The weighted roll-up over the isolated module results.

    Returns the whole Summary dashboard payload: the overall score and verdict, the
    sub-feature composition (worst first), the checks-status counts, the gate, where
    the findings sit, and what to fix first.
    """
    rows = _sub_features(modules)
    available_weight = _apply_weights(rows)

    scored = [r for r in rows if r['points'] is not None]
    score = round(sum(r['points'] for r in scored), 1) if scored else None

    gate_module = modules.get(GATE_MODULE) or {}
    loops = gate_module.get('kpis', {}).get('loops', 0) or 0
    # `loops` is the durable signal: only the KPIs survive the round-trip through
    # the DB, so a re-opened project must gate on the same loop count it did on
    # import rather than on the module's transient top-level flag.
    blocking = bool(gate_module.get('blocking') or loops > 0)
    if blocking:
        for r in rows:
            if r['key'] in PROVISIONAL_ON_LOOP:
                r['provisional'] = True

    verdict, statement = _verdict(score, blocking)
    counts = {'Pass': 0, 'Review': 0, 'Critical': 0, 'Not computed': 0}
    for r in rows:
        counts[r['status']] = counts.get(r['status'], 0) + 1

    return {
        'score':      score,
        'grade':      uniform_grade(score) if score is not None else None,
        'verdict':    verdict,
        'statement':  statement,
        # a loop caps the grade: nothing submits while P6 cannot calculate the file
        'blocking':   blocking,
        'ready':      bool(score is not None and score >= 80 and not blocking),
        'gate': {
            'module':   GATE_MODULE,
            'name':     gate_module.get('name', 'Circular Logic'),
            'blocking': blocking,
            'loops':    loops,
            'score':    gate_module.get('score'),
        },
        'sub_features':    rows,
        'counts':          counts,
        'scored_count':    len(scored),
        'total_count':     len(rows),
        'weight_covered':  available_weight,
        'problem_areas':   _problem_areas(modules, rows),
        'fix_first':       _fix_first(modules, rows),
    }
