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

# The change taxonomy (§13). Calendar / constraint / resource land in a later slice.
CHANGE_TYPES = (
    'added', 'removed', 'renamed', 'idchange', 'moved_wbs',
    'logic', 'sequence', 'time', 'milestone', 'criticality',
)

TYPE_LABEL = {
    'added': 'Scope', 'removed': 'Scope', 'renamed': 'Scope', 'idchange': 'Identity',
    'moved_wbs': 'WBS', 'logic': 'Logic', 'sequence': 'Sequence', 'time': 'Time',
    'milestone': 'Milestone', 'criticality': 'Criticality',
}

# Which planning category each change type rolls up into for the change profile (§13).
PROFILE_BUCKET = {
    'added': 'scope', 'removed': 'scope', 'renamed': 'scope', 'idchange': 'scope',
    'moved_wbs': 'wbs', 'logic': 'logic', 'sequence': 'sequence', 'time': 'time',
    'milestone': 'milestone', 'criticality': 'criticality',
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


def classify(kind, *, tf0=None, tf1=None, magnitude=0.0, on_cp=False):
    """Return (impact, severity) for one detected change.

    kind      one of CHANGE_TYPES
    tf0/tf1   total float (working days) in rev0 / rev1, or None
    magnitude change size in working days (duration delta, milestone slip) where relevant
    on_cp     the added/removed activity lands on the critical path (caller decides)
    """
    near = on_or_near_path(tf0, tf1)
    crit = is_critical(tf0, tf1)
    mag = abs(magnitude or 0.0)

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
