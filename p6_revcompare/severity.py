"""Change classification and severity — transparent, defensible, conservative.

The tool never says a change is "wrong". Severity reflects **schedule impact only**,
so a consultant can defend every rating:

  * material  — the change can move the plan: it touches the critical or near-critical
                path (in either revision), moves a finish milestone, reverses execution
                sequence, or is a large duration change. Otherwise minor.
  * severity  — crit / high / review / info, a finer band within the above.

Pure functions over a small context dict; unit-tested.
"""

NEAR_THRESHOLD = 10.0        # working days; near-critical is 0 < TF < 10 (matches p6_critpath)
BIG_TIME_WD = 10.0           # a duration change this large is material even off the path
BIG_MS_SLIP = 20.0           # a milestone move this large is critical-severity

# The change taxonomy (§13).
CHANGE_TYPES = (
    'added', 'removed', 'renamed', 'idchange', 'moved_wbs',
    'logic', 'sequence', 'time', 'milestone', 'criticality',
    'calendar', 'constraint', 'wbs_add', 'wbs_remove', 'wbs_rename',
)

TYPE_LABEL = {
    'added': 'Scope', 'removed': 'Scope', 'renamed': 'Scope', 'idchange': 'Identity',
    'moved_wbs': 'WBS', 'logic': 'Logic', 'sequence': 'Sequence', 'time': 'Time',
    'milestone': 'Milestone', 'criticality': 'Criticality',
    'calendar': 'Calendar', 'constraint': 'Constraint',
    'wbs_add': 'WBS', 'wbs_remove': 'WBS', 'wbs_rename': 'WBS',
}

# Which planning category each change type rolls up into for the change profile (§13).
PROFILE_BUCKET = {
    'added': 'scope', 'removed': 'scope', 'renamed': 'scope', 'idchange': 'scope',
    'moved_wbs': 'wbs', 'logic': 'logic', 'sequence': 'sequence', 'time': 'time',
    'milestone': 'milestone', 'criticality': 'criticality',
    'calendar': 'calendar', 'constraint': 'constraint',
    'wbs_add': 'wbs', 'wbs_remove': 'wbs', 'wbs_rename': 'wbs',
}


def band(tf):
    """Float band for an activity: crit (TF<=0) / near (0<TF<10) / safe / None (no float)."""
    if tf is None:
        return None
    if tf <= 0:
        return 'crit'
    if tf < NEAR_THRESHOLD:
        return 'near'
    return 'safe'


def on_or_near_path(tf0, tf1):
    """True if the activity is critical or near-critical in EITHER revision."""
    return band(tf0) in ('crit', 'near') or band(tf1) in ('crit', 'near')


def is_critical(tf0, tf1):
    return band(tf0) == 'crit' or band(tf1) == 'crit'


def classify(kind, *, tf0=None, tf1=None, magnitude=0.0, on_cp=False, hard=False):
    """Return (impact, severity) for one detected change.

    kind      one of CHANGE_TYPES
    tf0/tf1   total float (working days) in rev0 / rev1, or None
    magnitude change size where relevant (duration delta / milestone slip in working days;
              for a calendar reassignment, the working-days-per-week change)
    on_cp     the change lands on the critical path (caller decides)
    hard      a hard (date-pinning) constraint is involved
    """
    near = on_or_near_path(tf0, tf1)
    crit = is_critical(tf0, tf1)
    mag = abs(magnitude or 0.0)

    if kind == 'calendar':
        # A calendar reassignment changes planned durations; a workweek change (mag>0) is the
        # material signal, otherwise (holidays/hours only) it is minor unless on the path.
        if mag > 0 or on_cp:
            return 'material', ('crit' if crit else 'hi')
        return 'minor', 'low'

    if kind == 'constraint':
        if hard and crit:
            return 'material', 'crit'
        if hard or near:
            return 'material', 'hi'
        return 'minor', 'med'

    if kind in ('wbs_add', 'wbs_remove'):
        return ('material', 'hi') if on_cp else ('minor', 'med')
    if kind == 'wbs_rename':
        return 'minor', 'low'

    if kind == 'milestone':
        impact = 'material'
        sev = 'crit' if mag >= BIG_MS_SLIP else ('hi' if mag > 0 else 'med')
        return impact, sev

    if kind == 'sequence':
        # A reversal is always worth review; critical when it sits on the critical/near path.
        return 'material', ('crit' if near else 'hi')

    if kind == 'criticality':
        # Became critical / near, or lost float onto the path.
        return 'material', ('crit' if crit else 'hi')

    if kind == 'time':
        material = near or mag >= BIG_TIME_WD
        if not material:
            return 'minor', 'low'
        return 'material', ('crit' if crit else ('hi' if mag >= BIG_MS_SLIP or near else 'med'))

    if kind == 'logic':
        if crit:
            return 'material', 'crit'
        if near:
            return 'material', 'hi'
        return 'minor', 'low'

    if kind in ('added', 'removed'):
        if on_cp or crit:
            return 'material', 'crit'
        if near:
            return 'material', 'hi'
        return 'minor', 'med' if kind == 'added' else 'low'

    if kind == 'moved_wbs':
        return ('material', 'hi') if near else ('minor', 'low')

    if kind in ('renamed', 'idchange'):
        # Identity/name housekeeping — not a schedule impact on its own.
        return 'minor', 'low'

    return 'minor', 'low'


def rank_key(row):
    """Sort key for the change register: material first, then severity, then criticality.
    Most-significant rows float to the top."""
    sev_order = {'crit': 0, 'hi': 1, 'med': 2, 'low': 3}
    return (0 if row.get('impact') == 'material' else 1,
            sev_order.get(row.get('severity'), 3),
            row.get('activity_name') or '')
