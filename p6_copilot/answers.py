"""The offline answer engine. Each answer takes the project 'brain' (context) and returns
a plain, evidence-cited answer. Management answers speak to a manager with NO Primavera /
project-control background — jargon-free, advice-first. Every claim carries the module it
came from; nothing is invented.

Answer shape: {headline, body:[..], advice:[..], evidence:[{module, plain, value}]}.
"""


def _weeks(days):
    return max(1, round(abs(days) / 5))   # rough working weeks


def _need_data(what):
    return {'headline': f"There isn't enough information yet to answer that.",
            'body': [f"Import an updated schedule with {what} so the Copilot can work it out."],
            'advice': [], 'evidence': []}


# ── Management (plain language for any manager) ────────────────────────────

def why_delayed_mgmt(ctx):
    delay = ctx['delay_days']
    if delay is None:
        return _need_data('a finish milestone')
    if delay <= 0:
        ahead = f", and about {abs(delay)} working days ahead" if delay < 0 else ""
        return {
            'headline': f"Good news — {ctx['project_name']} is on track to finish on time{ahead}.",
            'body': ["The finish date isn't slipping against the plan right now."],
            'advice': ["Keep protecting the pace on the areas that are furthest along."],
            'evidence': [{'module': 'Delay', 'plain': 'Finish date versus the plan', 'value': f'{delay} working days'}]}

    ev = [{'module': 'Delay', 'plain': 'The finish date has slipped by', 'value': f'{delay} working days'}]
    headline = (f"{ctx['project_name']} is running about {delay} working days behind — "
                f"roughly {_weeks(delay)} week(s) late to finish.")
    body = [f"At today's pace, the project would finish about {delay} working days later than planned."]
    advice = []
    worst = ctx['worst_discipline']
    if worst:
        body.append(f"The main cause is the **{worst['name']}** work: only about **{worst['actual']}%** is done, "
                    f"when about **{worst['planned']}%** should be finished by now — the biggest gap on the project.")
        ev.append({'module': 'Progress', 'plain': f"{worst['name']} done versus what should be done",
                   'value': f"{worst['actual']}% vs {worst['planned']}%"})
        advice.append(f"Put the recovery effort into **{worst['name']}** first — it's the single biggest reason the project is late.")
    if ctx['pace_pct'] is not None and ctx['pace_pct'] < 100:
        body.append(f"Overall the work is getting done at about **{ctx['pace_pct']}%** of the planned speed.")
        ev.append({'module': 'Overall progress', 'plain': 'Work getting done versus planned speed', 'value': f"{ctx['pace_pct']}% of plan"})
    advice.append("Ask the team for a recovery plan for that area, then re-check the finish date once it's in.")
    return {'headline': headline, 'body': body, 'advice': advice, 'evidence': ev}


def which_wbs_mgmt(ctx):
    worst = ctx['worst_discipline']
    if not worst:
        return {'headline': "No single part of the project stands out as behind right now.",
                'body': ["The work is fairly balanced against the plan — no one area is dragging the finish date."],
                'advice': [], 'evidence': []}
    body = [f"The **{worst['name']}** work is the biggest drag: about **{worst['actual']}%** done versus "
            f"**{worst['planned']}%** that should be done by now — a gap of about **{worst['gap']} points**."]
    others = [d for d in ctx['disciplines'] if d is not worst and d['gap'] > 0][:2]
    if others:
        body.append("After that, keep an eye on: " + ', '.join(f"{d['name']} ({d['gap']} behind)" for d in others) + ".")
    return {'headline': f"The **{worst['name']}** work is causing most of the delay.",
            'body': body,
            'advice': [f"Focus recovery and management attention on **{worst['name']}** first — fixing it moves the finish date the most."],
            'evidence': [{'module': 'Progress', 'plain': f"{worst['name']} done versus planned",
                          'value': f"{worst['actual']}% vs {worst['planned']}%"}]}


def health_mgmt(ctx):
    delay = ctx['delay_days']
    if delay is None:
        return _need_data('a finish milestone')
    if delay <= 0:
        status, note = 'Healthy', "The project is on or ahead of schedule."
    elif delay <= 10:
        status, note = 'Slipping', (f"The project is a little behind — about {delay} working days late — "
                                    "but it's recoverable if acted on now.")
    else:
        status, note = 'Behind', (f"The project is materially behind — about {delay} working days "
                                  f"(roughly {_weeks(delay)} weeks) late to finish.")
    body = [note]
    ev = [{'module': 'Delay', 'plain': 'Finish date versus the plan', 'value': f'{delay} working days'}]
    if ctx['actual_pct'] is not None and ctx['planned_pct'] is not None:
        body.append(f"Overall, about **{ctx['actual_pct']}%** of the work is done, against roughly "
                    f"**{ctx['planned_pct']}%** planned by now.")
        ev.append({'module': 'Overall progress', 'plain': 'Work done versus planned', 'value': f"{ctx['actual_pct']}% vs {ctx['planned_pct']}%"})
    advice = []
    worst = ctx['worst_discipline']
    if worst and worst['gap'] > 0:
        advice.append(f"Watch **{worst['name']}** most closely — it's the furthest behind.")
    return {'headline': f"Project health: {status}.", 'body': body, 'advice': advice, 'evidence': ev}


_ANSWERS = {
    ('management', 'why_delayed'): why_delayed_mgmt,
    ('management', 'which_wbs'):   which_wbs_mgmt,
    ('management', 'health'):      health_mgmt,
}


def answer(question_id, ctx, mode='management'):
    fn = _ANSWERS.get((mode, question_id)) or _ANSWERS.get(('management', question_id))
    if not fn:
        return {'headline': "The offline Copilot can't answer that one yet.",
                'body': ["Pick one of the suggested questions — those are answered with your schedule's own evidence. "
                         "Free-form questions come with the premium cloud upgrade."],
                'advice': [], 'evidence': []}
    return fn(ctx)
