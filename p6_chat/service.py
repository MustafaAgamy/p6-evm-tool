"""Ties the pieces together: answer a question about the open project.

Flow: grounding (from the DB result) + tool knowledge + persona -> the local brain
-> a detailed, grounded planning-manager answer. When the brain isn't set up yet,
fall back honestly to a real snapshot read straight from the schedule plus a
one-line pointer to set the brain up — never a canned or another project's answer.
"""
from . import knowledge, grounding, library, llm, charts


def _role_title(role):
    if not role or role == 'all':
        return None
    for r in library.roles():
        if r.get('key') == role or r.get('title') == role:
            return r.get('title')
    return role


def _snapshot(result):
    """A short 'what I can read right now' block for the pre-brain fallback."""
    bits = []
    if result.get('spi') is not None:
        bits.append('Schedule performance (SPI) %s' % round(float(result['spi']), 2))
    if result.get('cpi') is not None:
        bits.append('Cost performance (CPI) %s' % round(float(result['cpi']), 2))
    op = result.get('overall_planned_pct')
    oa = result.get('overall_actual_pct')
    if oa is not None:
        bits.append('progress %.1f%% actual%s' % (
            float(oa), (' vs %.1f%% planned' % float(op)) if op is not None else ''))
    if result.get('delay_days') is not None:
        bits.append('%s working days behind baseline finish' % result['delay_days'])
    return bits


def ask(question, result, role=None):
    """Answer `question` about the open project (`result` = db.get_project_result).
    Returns {ok, answer, source, grounded, brain, needs_setup}."""
    if not question or not str(question).strip():
        return {'ok': False, 'error': 'Ask a question first.'}
    brain = llm.status()
    role_title = _role_title(role)
    ground = grounding.build(result)
    has_ground = grounding.available(result)
    ch = charts.charts_for(question, result)          # grounded charts, brain or not

    # Brain ready → the real, detailed, grounded answer (+ grounded charts).
    if brain.get('ready'):
        try:
            answer = llm.generate(knowledge.system_prompt(),
                                  knowledge.build_prompt(question, ground, role_title))
            if answer:
                return {'ok': True, 'answer': answer, 'source': 'brain',
                        'grounded': has_ground, 'brain': brain, 'charts': ch}
        except llm.LlmNotReady:
            pass
        except llm.LlmError as exc:
            return {'ok': True, 'answer': None, 'source': 'error',
                    'error': str(exc), 'brain': brain, 'charts': ch}

    # Brain not set up → honest fallback: real snapshot + charts + a pointer to set up.
    if has_ground:
        snap = _snapshot(result)
        lines = ["**Your offline AI brain isn't set up yet**, so I can't give the "
                 "full, reasoned answer to that question. It's a one-time download "
                 "inside the app (about 2 GB) — nothing to install — after which it "
                 "runs entirely on your PC, no internet, no cost."]
        if snap:
            lines.append("For now, here's what I can read straight from your "
                         "imported schedule:")
            lines.append("\n".join('• ' + b for b in snap))
        answer = "\n\n".join(lines)
    else:
        answer = ("Import a P6 schedule first — then I can read it and answer this "
                  "in detail. (Your offline AI brain also needs a one-time model "
                  "download to give the full reasoned answers.)")
    return {'ok': True, 'answer': answer, 'source': 'setup',
            'grounded': has_ground, 'needs_setup': True, 'brain': brain, 'charts': ch}


def get_library():
    """The question library payload for the UI (themes, roles, gaps, counts)."""
    return library.library()
