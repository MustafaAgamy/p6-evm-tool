"""Backend entry for the offline question-answer engine.

``answer_question(snapshot_id, question_id, role)`` builds the grounded FACTS for the loaded
project (DB read path — never re-parses) and hands them to the ``p6_chat.qa`` registry, which
returns a detailed, senior-planning-engineer answer with NO AI model. Unknown ids and the
no-project state degrade to an honest, useful message. Returns a JSON-ready dict; never raises.
"""


def _no_project():
    return {'headline': "Send me your P6 schedule first.",
            'body': ["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can "
                     "answer this from your own numbers — offline, nothing leaves your PC."],
            'advice': [], 'evidence': []}


def _fallback(F, question_id):
    """An honest answer when no function is registered for this id: give the grounded headline
    the project does have, and point to the full library / the matching feature."""
    from p6_chat.qa import _kit as K
    spi = F.get('spi')
    body = [
        "I don't have a purpose-built read for that exact question yet, but here's where the "
        "project stands so you're not left empty-handed:",
        (f"SPI ≈ {K.ratio(spi)} ({K.pct(F.get('pace_pct'))} of the planned rate); the finish is "
         f"{K.delay_phrase(F)}." if spi is not None else "Load a schedule and I'll ground this."),
    ]
    dl = K.driver_line(F)
    if dl:
        body.append(dl)
    return {'headline': "Here's the project position on that.",
            'body': body,
            'advice': ["Pick a suggested question from the library — those are answered from your "
                       "schedule's own evidence."],
            'evidence': [K.ev('EVM', 'SPI', K.ratio(spi)),
                         K.ev('EVM', 'Delay', _signed_delay(F))]}


def _signed_delay(F):
    d = F.get('delay_days')
    if d is None:
        return None
    d = round(d)
    return f"+{d} wd (behind)" if d > 0 else (f"{d} wd (ahead)" if d < 0 else "on date")


def answer_question(snapshot_id, question_id, role='management'):
    try:
        from p6_chat.facts import build_facts
        from p6_chat import qa
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}
    try:
        F = build_facts(snapshot_id)
    except Exception:
        F = {'ok': False}
    if not F.get('ok'):
        return {'ok': True, 'answer': _no_project(), 'source': 'computed', 'matched': False}
    a = qa.answer(question_id, F, role or 'management')
    if a is None:
        return {'ok': True, 'answer': _fallback(F, question_id), 'source': 'computed', 'matched': False}
    return {'ok': True, 'answer': a, 'source': 'computed', 'matched': True}
