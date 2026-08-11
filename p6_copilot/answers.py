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
    as_of = f"As of the {ctx['data_date']} update, " if ctx.get('data_date') else ""
    headline = (f"{as_of}{ctx['project_name']} is running about {delay} working days behind — "
                f"roughly {_weeks(delay)} week(s) late to finish.")
    if ctx.get('baseline_finish') and ctx.get('forecast_finish'):
        body = [f"The planned finish of **{ctx['baseline_finish']}** has moved to about **{ctx['forecast_finish']}** — "
                f"roughly {delay} working days later."]
    else:
        body = [f"At today's pace, the project would finish about {delay} working days later than planned."]
    if ctx.get('data_date'):
        ev.append({'module': 'Update date', 'plain': 'Measured from the latest update', 'value': ctx['data_date']})
    advice = []
    worst = ctx['worst_discipline']
    if worst:
        body.append(f"The main cause is the **{worst['name']}** work: only about **{worst['actual']}%** is done, "
                    f"when about **{worst['planned']}%** should be finished by now — the biggest gap on the project.")
        body.append(f"That {delay}-working-day figure already assumes **{worst['name']}** finishes on its current forecast; "
                    f"if **{worst['name']}** keeps slipping past that, the delay grows further.")
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
    as_of = f"as of {ctx['data_date']}, " if ctx.get('data_date') else ""
    return {'headline': f"Project health {as_of}is: {status}.", 'body': body, 'advice': advice, 'evidence': ev}


def risks_mgmt(ctx):
    delay = ctx['delay_days']
    worst = ctx['worst_discipline']
    risks = []
    if worst:
        risks.append(f"The **{worst['name']}** work slipping further — it's already the furthest behind.")
    if ctx.get('oos_count'):
        risks.append(f"**{ctx['oos_count']}** activities were started out of order — a rework and coordination risk.")
    if ctx.get('float_grade') in ('Critical', 'Needs Attention'):
        risks.append("There's very little spare time left in the plan to absorb new problems.")
    if delay and delay > 0 and not risks:
        risks.append("The finish date keeps slipping — recovery hasn't caught up yet.")
    if not risks:
        return {'headline': "No major risks stand out in this update.",
                'body': ["The schedule looks balanced — keep an eye on the areas furthest along."],
                'advice': [], 'evidence': []}
    advice = [f"Deal with **{worst['name']}** first — it's behind almost all of these." if worst
              else "Tackle the furthest-behind area first."]
    ev = [{'module': 'Finish date', 'plain': 'Delay', 'value': f"{delay} working days"}] if delay else []
    return {'headline': "The biggest risks right now:", 'body': risks, 'advice': advice, 'evidence': ev}


def eot_likely_mgmt(ctx):
    from p6_copilot.claims import eot_assessment
    a = eot_assessment(ctx)
    if not a.get('has_delay'):
        return {'headline': a['verdict'], 'body': list(a['indicators']), 'advice': [], 'evidence': []}
    # Manager-concise: the verdict, the top couple of indicators, the honest caveat, plain advice.
    body = a['indicators'][:2] + [a['caveat']]
    advice = ["Ask the commercial team to review the claim position, and note who caused each delay "
              "(e.g. late access) so ownership is clear."]
    return {'headline': a['verdict'], 'body': body, 'advice': advice,
            'evidence': [{'module': 'Finish date', 'plain': 'Delay to completion', 'value': f"{ctx['delay_days']} working days"}]}


def eot_likely_planning(ctx):
    """Planning-mode: the full, systematic claims read — indicators, ownership, concurrency,
    and the entitlement/method framing a planner needs to prepare the claim."""
    from p6_copilot.claims import eot_assessment
    a = eot_assessment(ctx)
    if not a.get('has_delay'):
        return {'headline': a['verdict'], 'body': list(a['indicators']), 'advice': [], 'evidence': []}
    body = list(a['indicators'])
    if a.get('ownership'):
        body.append(a['ownership'])
    if a.get('caveat'):
        body.append(a['caveat'])
    body.append("Structure it Cause -> Effect -> Entitlement -> Substantiation; the entitlement clause is typically FIDIC 8.5.")
    return {'headline': a['verdict'], 'body': body, 'advice': a.get('advice', []),
            'evidence': [{'module': 'Finish date', 'plain': 'Delay to completion', 'value': f"{ctx['delay_days']} working days"}]}


def actions_mgmt(ctx):
    delay = ctx['delay_days']
    worst = ctx['worst_discipline']
    if not delay or delay <= 0:
        return {'headline': "Nothing urgent this week — the project is on track.",
                'body': ["Keep protecting the pace on the areas furthest along."], 'advice': [], 'evidence': []}
    acts = []
    if worst:
        acts.append(f"Push a recovery plan for **{worst['name']}** — the biggest cause of the delay.")
    acts.append("Get the contractor's written recovery plan, with dates.")
    if ctx.get('oos_count'):
        acts.append(f"Review the **{ctx['oos_count']}** out-of-order activities before they cause rework.")
    acts.append("Re-forecast the finish date after the recovery plan (the what-if gives an exact figure).")
    acts.append("Ask the commercial team to review the claim position.")
    return {'headline': "Top actions this week:", 'body': acts, 'advice': [], 'evidence': []}


_ANSWERS = {
    ('management', 'why_delayed'): why_delayed_mgmt,
    ('management', 'which_wbs'):   which_wbs_mgmt,
    ('management', 'health'):      health_mgmt,
    ('management', 'risks'):       risks_mgmt,
    ('management', 'eot_likely'):  eot_likely_mgmt,
    ('management', 'can_claim'):   eot_likely_mgmt,
    ('management', 'actions'):     actions_mgmt,
    ('planning',   'eot_likely'):  eot_likely_planning,
    ('planning',   'can_claim'):   eot_likely_planning,
}


def answer(question_id, ctx, mode='management'):
    fn = _ANSWERS.get((mode, question_id)) or _ANSWERS.get(('management', question_id))
    if not fn:
        return {'headline': "The offline Copilot can't answer that one yet.",
                'body': ["Pick one of the suggested questions — those are answered with your schedule's own evidence. "
                         "Free-form questions come with the premium cloud upgrade."],
                'advice': [], 'evidence': []}
    return fn(ctx)
