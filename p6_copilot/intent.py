"""Map a freely-typed question to one in the Copilot's repertoire (offline V1).

A manager can type "can we claim?" and get the EOT answer; a planner can type "which method
for the delay?" and reach the delay-method answer. Pure keyword / synonym matching over the
question sets — no cloud. When nothing matches with enough signal, the caller falls back to
the graceful 'that's the premium cloud upgrade' deferral.
"""

# question_id -> the phrases/keywords that signal it. Ordered most-specific first, so
# "claim" wins over the broad "why / late" catch. Kept lower-case; matched as substrings.
_INTENTS = [
    ('eot_likely',      ['claim', 'eot', 'extension of time', 'time extension', 'entitle',
                         'prolongation', 'compensation event']),
    ('delay_method',    ['which method', 'delay method', 'analysis method', 'method to use', 'tia',
                         'time impact', 'windows analysis', 'as-planned', 'as planned', 'as-built',
                         'as built', 'forensic', 'collapsed']),
    ('recovery',        ['recover', 'catch up', 'catch-up', 'back on track', 'accelerat', 'crash',
                         'mitigat', 'speed up', 'pull back', 'make up time', 'shorten the']),
    ('critical_driver', ['critical path', 'driving the', 'longest path', 'what is driving', 'drives the finish',
                         'critical activit', 'driving path', 'driver of']),
    ('which_wbs',       ['which part', 'which area', 'which wbs', 'which discipline', 'where is the delay',
                         'what part', 'which trade']),
    ('project_needs',   ['project type', 'missing activit', 'usually need', 'typical activit',
                         'construction logic', 'what should the schedule', 'is anything missing']),
    ('risks',           ['risk', 'threat', 'concern', 'worry', 'exposure', 'danger']),
    ('actions',         ['action', 'what should i do', 'what to do', 'next step', 'this week',
                         'priorit', 'focus on']),
    ('health',          ['health', 'how is the project', "how's the project", 'overall status',
                         'on track', 'how are we doing', 'project status']),
    ('why_delayed',     ['why', 'delay', 'behind', ' late', 'slipp', 'running late', 'losing time']),
]

# These have technical answers only — don't offer them for a Management-mode typed question.
_PLANNING_ONLY = {'delay_method', 'critical_driver', 'project_needs'}


def match_intent(text, mode='management'):
    """Return (question_id, matched). Picks the first intent whose keywords hit the typed
    text; returns (None, False) when nothing meaningful matches."""
    raw = (text or '').strip().lower()
    if len(raw) < 3:
        return None, False
    t = ' ' + raw + ' '
    for qid, keys in _INTENTS:
        if mode != 'planning' and qid in _PLANNING_ONLY:
            continue
        if any(k in t for k in keys):
            return qid, True
    return None, False
