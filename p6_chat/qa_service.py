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


# ─────────────────────────────── v2: the 15 merged questions ───────────────────────────────

def _tool_answer(cap, F):
    """Short, grounded answer for an original question that is really an interactive tool."""
    from p6_chat.qa import _kit as K
    pos = K.delay_phrase(F)
    if cap == 'tia':
        return {'headline': "The time-impact read splits the slip into what's already happened, what today's pace adds, "
                            "and what weather adds.",
                'body': [f"The finish is {pos}. The decomposition shows how much of that is locked in to date, how much "
                         f"more comes if the current pace holds (SPI {K.ratio(F.get('spi'))}), and the weather allowance "
                         "for the site type — each in working days, with a likely and a worst-case finish.",
                         "For a claim, the prospective version is the fragnet: insert the delay event, re-run P6 F9, and "
                         "read the exact movement of the finish — that figure stands up; the decomposition explains it."],
                'advice': ["Run it to see the split, then F9 a fragnet for any number that goes in a claim."]}
    if cap == 'whatif':
        return {'headline': "Pick a lever, get an instant estimate, then build it and run P6 F9 for the exact figure.",
                'body': ["The levers: delay an activity, crash (shorten) it, add a crew, re-sequence (relax a driving "
                         "link), extend working time, change a calendar. The instant estimate compares moves in seconds; "
                         "the build → F9 → read round-trip gives the number you can defend.",
                         "Aim every lever at the chain that sets the finish — nothing off it moves the date."],
                'advice': ["Compare levers on the estimate, then F9 only the winning combination before you commit a date."]}
    return {'headline': "A one-page manager's briefing: the date, the front that owns the slip, and the decision needed.",
            'body': [f"It leads with the position (finish {pos}, SPI {K.ratio(F.get('spi'))}), names the driving front, "
                     "states the cost position honestly, and ends with the decision needed — with the planned-vs-earned "
                     "S-curve beside it. It exports to PDF or Word."],
            'advice': ["Send it before the progress meeting so the discussion starts from the recovery decision."]}


def _original_answer(o, F, ctx, N=None):
    from p6_chat import qa
    cap = o.get('cap')
    try:
        if not cap:
            a = qa.answer(o['id'], F, 'planning')
        elif cap == 'assistant' and o.get('qid') == 'project_needs':
            from p6_chat.copilot import project_needs
            a = project_needs(N)                       # the type from the WBS, not the project name
        elif cap == 'assistant':
            from p6_chat.copilot import engine_answer
            a = engine_answer(o.get('qid'), ctx, o.get('mode') or 'planning')
        else:
            a = _tool_answer(cap, F)
    except Exception:
        a = None
    a = a or {'headline': 'Covered in the answer above.', 'body': [], 'advice': []}
    return {'id': o['id'], 'q': o['q'], 'headline': a.get('headline', ''), 'body': list(a.get('body') or []),
            'advice': list(a.get('advice') or []), 'tool': cap if cap in ('tia', 'whatif', 'report') else None}


def _thinking(F, N, extra):
    steps = []
    if N and N.get('ok'):
        steps.append(f"Read {N['activity_count']:,} activities from your P6 file (data date {N.get('data_date')})")
    else:
        steps.append(f"Read the stored analysis of your P6 update (data date {F.get('data_date')})")
    return steps + [s for s in (extra or []) if s]


def _backfill_finish(F, N):
    """Fill a missing baseline / forecast finish (older imports, a damaged DB) and the re-read file's
    network facts into F — see ``facts.add_network``."""
    from p6_chat.facts import add_network
    add_network(F, N)


def answer_merged(snapshot_id, qid, role='planning', focus=None, followup=None):
    """The full v2 answer for one of the 15 merged questions. JSON-ready; never raises."""
    try:
        from p6_chat.facts import build_facts
        from p6_chat import merged, analysis
        from p6_chat import copilot as cp
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}
    e = merged.entry(qid)
    if not e:
        return {'ok': False, 'error': f'Unknown question {qid}.'}
    try:
        F = build_facts(snapshot_id)
    except Exception:
        F = {'ok': False}
    if not F.get('ok'):
        a = merged.K2.no_project()
        a.update({'id': qid, 'question': e['q'], 'group': e['group'], 'covers': e['covers'], 'specific': [],
                  'thinking': [], 'focus': None})
        return {'ok': True, 'v': 2, 'answer': a, 'matched': False}
    N = analysis.network(snapshot_id)
    _backfill_finish(F, N)
    a = merged.build(qid, F, N, role) or merged.K2.A2(
        "Here's the project position on that.", [merged.K2.sec('Position', f"The finish is {merged.K2.delay_phrase(F)}.")])
    try:
        ctx = cp.project_brain(snapshot_id) or {}
    except Exception:
        ctx = {}
    for k_ctx, k_f in (('baseline_finish', 'baseline_finish'), ('forecast_finish', 'forecast_finish')):
        if not ctx.get(k_ctx):
            ctx[k_ctx] = F.get(k_f)
    ctx['net_late_inputs'] = F.get('net_late_inputs') or []
    a['specific'] = [_original_answer(o, F, ctx, N) for o in e['originals']]
    a['thinking'] = _thinking(F, N, a.get('thinking'))
    a.update({'id': qid, 'question': e['q'], 'group': e['group'], 'covers': e['covers'],
              'focus': focus, 'followup': followup})
    return {'ok': True, 'v': 2, 'answer': a, 'matched': True}


def ask_text(snapshot_id, text, role='planning', last_qid=None):
    """Route a typed question to the right merged answer (and sub-question) and answer it."""
    from p6_chat import router, merged
    r = router.route(text, last_qid)
    if not r['matched']:
        alts = r.get('alternatives') or ['q01', 'q02', 'q05']
        return {'ok': True, 'v': 2, 'matched': False, 'route': r,
                'suggest': [{'id': q, 'q': merged.entry(q)['q']} for q in alts if merged.entry(q)]}
    out = answer_merged(snapshot_id, r['qid'], role, focus=r.get('focus'), followup=r.get('followup'))
    out['route'] = r
    if out.get('answer') is not None:
        out['answer']['also'] = [{'id': q, 'q': merged.entry(q)['q']} for q in r.get('alternatives', []) if merged.entry(q)]
    return out


def library15():
    """The drawer payload: 15 questions by group, each with the topics it covers and its original sub-questions."""
    from p6_chat import merged
    cat = merged.catalog()
    return {'ok': True, 'v': 2, 'groups': cat['groups'],
            'questions': [{'id': q['id'], 'group': q['group'], 'q': q['q'], 'covers': q['covers'],
                           'originals': [{'id': o['id'], 'q': o['q']} for o in q['originals']]}
                          for q in cat['questions']],
            'counts': cat['counts']}


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
