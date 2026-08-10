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
]


def questions(mode='management'):
    src = MANAGEMENT if mode == 'management' else PLANNING
    return [{'id': qid, 'text': text} for qid, text in src]
