"""The Copilot's question repertoire (offline V1). Seeded from Ibrahim's spec; grows over
time. Management questions read in plain manager language; Planning questions are technical.
Default mode is Management.
"""

MANAGEMENT = [
    ('why_delayed', 'Why is the project delayed?'),
    ('which_wbs',   'Which part of the project is causing the delay?'),
    ('health',      'Overall project health'),
    ('risks',       'Biggest risks right now'),
    ('eot_likely',  'Is a time extension likely?'),
    ('actions',     'Top actions this week'),
]

PLANNING = [
    ('why_delayed',     'Why is the project behind schedule?'),
    ('critical_driver', 'What is driving the finish date?'),
    ('recovery',        'Best recovery options'),
    ('risks',           'Top schedule risks'),
    ('eot_likely',      'Is there an EOT / claim case?'),
    ('delay_method',    'Which delay-analysis method fits?'),
    ('project_needs',   'What does this project type need?'),
]


def questions(mode='management'):
    src = MANAGEMENT if mode == 'management' else PLANNING
    return [{'id': qid, 'text': text} for qid, text in src]


def label_for(qid, mode='management'):
    """Plain label for a question id — the same wording shown on the button. Falls back to
    the other mode's label, then to the id itself, so a typed-question match always has a name."""
    primary = MANAGEMENT if mode == 'management' else PLANNING
    other = PLANNING if mode == 'management' else MANAGEMENT
    for qid_, text in list(primary) + list(other):
        if qid_ == qid:
            return text
    return qid
