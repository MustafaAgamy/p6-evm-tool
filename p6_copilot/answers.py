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
    and the method + entitlement framing a planner needs, cited from the knowledge base."""
    from p6_copilot.claims import eot_assessment
    from p6_copilot.knowledge import recommend_method, contract_line
    a = eot_assessment(ctx)
    if not a.get('has_delay'):
        return {'headline': a['verdict'], 'body': list(a['indicators']), 'advice': [], 'evidence': []}
    rec = recommend_method(ctx)
    m = rec['method']
    body = list(a['indicators'])
    if a.get('ownership'):
        body.append(a['ownership'])
    if a.get('caveat'):
        body.append(a['caveat'])
    body.append(f"Method — prove it with a **{m['name']}** ({m['aace']}): {m['plain']}")
    body.append(f"Contract — structure it Cause -> Effect -> Entitlement -> Substantiation; {contract_line()}")
    return {'headline': a['verdict'], 'body': body, 'advice': a.get('advice', []),
            'evidence': [{'module': 'Finish date', 'plain': 'Delay to completion', 'value': f"{ctx['delay_days']} working days"},
                         {'module': 'Knowledge base', 'plain': 'Method / clause', 'value': f"{m['name']} · FIDIC 8.5 / 8.4"}]}


# ── Planning Engineer (technical depth; project-control terms are fine here) ──

def why_delayed_planning(ctx):
    delay = ctx['delay_days']
    if delay is None:
        return _need_data('a finish milestone')
    if delay <= 0:
        tail = f" — about {abs(delay)} wd of positive total float on the driving path." if delay < 0 else "."
        return {'headline': f"No slip to completion — the finish milestone is holding{tail}",
                'body': ["The critical path is not pushing completion past its baseline in this update."],
                'advice': ["Keep the driving path protected and watch near-critical chains (total float <= 10 wd) for encroachment."],
                'evidence': [{'module': 'Delay', 'plain': 'Finish vs plan', 'value': f'{delay} working days'}]}
    worst = ctx['worst_discipline']
    ev = [{'module': 'Delay', 'plain': 'Finish milestone slip', 'value': f'{delay} working days'}]
    dates = (f" — baseline {ctx['baseline_finish']} -> forecast {ctx['forecast_finish']}"
             if ctx.get('baseline_finish') and ctx.get('forecast_finish') else "")
    body = [f"Completion is about **{delay} working days** behind{dates}."]
    if worst:
        body.append(f"The largest schedule variance sits in **{worst['name']}**: {worst['actual']}% complete against "
                    f"{worst['planned']}% planned (a {worst['gap']}-point gap) — the most likely home of the driving chain.")
        ev.append({'module': 'Progress', 'plain': f"{worst['name']} earned vs planned", 'value': f"{worst['actual']}% vs {worst['planned']}%"})
    if ctx['pace_pct'] is not None:
        body.append(f"Overall **SPI ≈ {ctx['pace_pct'] / 100:.2f}** ({ctx['pace_pct']}% of the planned progress rate).")
        ev.append({'module': 'EVM', 'plain': 'SPI', 'value': f"{ctx['pace_pct']}% of plan"})
    if ctx.get('oos_count'):
        body.append(f"{ctx['oos_count']} activities are progressing **out of sequence** — the logic driving the current "
                    "critical path may not reflect the as-built order; re-validate the driving path after a clean F9.")
    advice = []
    if worst:
        advice.append(f"Interrogate the **{worst['name']}** driving chain first — it carries the finish variance.")
    advice.append("Confirm the critical path with a clean reschedule (the DCMA critical-path test) before committing to a recovery plan.")
    driver = f"**{worst['name']}**" if worst else "the works in progress"
    return {'headline': f"Completion is ~{delay} working days behind, driven by {driver}.",
            'body': body, 'advice': advice, 'evidence': ev}


def critical_driver_planning(ctx):
    delay = ctx['delay_days']
    worst = ctx['worst_discipline']
    body = []
    if worst:
        body.append(f"**{worst['name']}** carries the largest variance ({worst['actual']}% vs {worst['planned']}% "
                    f"planned, {worst['gap']} pts) and is the most likely home of the driving chain.")
    else:
        body.append("No single discipline dominates the variance — the driving path is spread across the works in progress.")
    if ctx.get('float_grade'):
        slack = ('little slack remains to absorb further slippage' if ctx['float_grade'] in ('Critical', 'Needs Attention')
                 else 'there is still some slack in the network')
        body.append(f"Float health is graded **{ctx['float_grade']}** — {slack}.")
    if ctx.get('oos_count'):
        body.append(f"{ctx['oos_count']} out-of-sequence activities mean a reschedule may re-route the critical path — validate it after F9.")
    advice = ["Trace the longest path to the completion milestone in P6 and confirm total float <= 0 along it (the DCMA critical-path test).",
              "For the exact forward impact of a change on that path, use the what-if (build -> F9 -> read), not an estimate."]
    ev = [{'module': 'Delay', 'plain': 'Finish slip', 'value': f'{delay} working days'}] if delay else []
    if worst:
        ev.append({'module': 'Progress', 'plain': f"{worst['name']} variance", 'value': f"{worst['gap']} pts"})
    return {'headline': "What's driving the finish date:", 'body': body, 'advice': advice, 'evidence': ev}


def recovery_planning(ctx):
    delay = ctx['delay_days']
    worst = ctx['worst_discipline']
    if not delay or delay <= 0:
        return {'headline': "No recovery needed — completion is not behind.",
                'body': ["Hold the driving path and keep near-critical chains (total float <= 10 wd) protected."],
                'advice': [], 'evidence': []}
    crash = ("**Crash the critical path** — add resources/crews to the driving activities"
             + (f", starting with **{worst['name']}**" if worst else "")
             + ", to shorten remaining durations. Test each with the what-if (shorten / add-crew) before committing.")
    opts = [
        crash,
        "**Re-sequence / fast-track** — overlap driving activities where it's safe (e.g. convert a driving FS to SS "
        "with a lag, or run works in parallel). Relaxing a driving relationship is a what-if lever here.",
        "**Extend working time** — a 6-day week or targeted overtime on the critical work only; weigh the gain against "
        "productivity fall-off and cost.",
    ]
    advice = ["Model each option in the what-if, then build the winning scenario and F9 it in P6 for the exact recovered "
              "date — don't commit the plan on the estimate alone.",
              "Track the recovery as a separate target so any slippage against it is visible next update."]
    return {'headline': "Best recovery options, strongest first:", 'body': opts, 'advice': advice,
            'evidence': [{'module': 'Delay', 'plain': 'Slip to recover', 'value': f'{delay} working days'}]}


def risks_planning(ctx):
    worst = ctx['worst_discipline']
    risks = []
    if worst:
        risks.append(f"**{worst['name']}** slipping further — it holds the largest variance ({worst['gap']} pts) and, most likely, the driving path.")
    if ctx.get('float_grade') in ('Critical', 'Needs Attention'):
        risks.append(f"Float health **{ctx['float_grade']}** — minimal total float left; a small slip on any near-critical chain will hit completion.")
    if ctx.get('oos_count'):
        risks.append(f"{ctx['oos_count']} out-of-sequence activities — broken predecessor logic can mask the true critical path until re-logicked.")
    if ctx['pace_pct'] is not None and ctx['pace_pct'] < 100:
        risks.append(f"**SPI ≈ {ctx['pace_pct'] / 100:.2f}** — the current progress rate won't recover the finish without intervention.")
    if not risks:
        return {'headline': "No material schedule risks flagged in this update.",
                'body': ["Logic, float and sequence look sound — keep monitoring the driving path."], 'advice': [], 'evidence': []}
    advice = ["Run the DCMA 14-point check to confirm no logic gaps, hard constraints or negative float are masking risk.",
              (f"Prioritise the **{worst['name']}** driving chain in the recovery plan." if worst else "Prioritise the driving chain in the recovery plan.")]
    ev = [{'module': 'Float', 'plain': 'Float health', 'value': ctx['float_grade']}] if ctx.get('float_grade') else []
    return {'headline': "Top schedule risks:", 'body': risks, 'advice': advice, 'evidence': ev}


def delay_method_planning(ctx):
    from p6_copilot.knowledge import recommend_method, contract_line, STANDARDS
    rec = recommend_method(ctx)
    m = rec['method']
    body = [f"Recommended: **{m['name']}** ({m['aace']}) — {rec['why']}",
            m['plain'],
            f"Contract framing: {contract_line()}",
            f"Standard: {STANDARDS['scl']['name']} — {STANDARDS['scl']['plain']}"]
    advice = ["Build the delay fragnet in the What-if / Delay-analysis workspace, F9 in P6, and read the exact "
              "completion movement — that P6 number is the claim-grade figure, never an estimate.",
              "Record cause and ownership per delay event, and test for concurrency before asserting entitlement."]
    ev = [{'module': 'Knowledge base', 'plain': 'Method', 'value': m['name']},
          {'module': 'Knowledge base', 'plain': 'Clause', 'value': 'FIDIC 8.5 (2017) / 8.4 (1999)'}]
    return {'headline': "Which delay-analysis method fits here:", 'body': body, 'advice': advice, 'evidence': ev}


def project_needs_planning(ctx):
    from p6_copilot.knowledge import detect_project_type
    t = detect_project_type(ctx)
    if not t:
        return {'headline': "Not enough signal to name the project type yet.",
                'body': ["I matched the project and discipline names against the Construction Knowledge Base but "
                         "couldn't identify a sub-type confidently. Open **Constructability** to review against a chosen type."],
                'advice': ["Run the Constructability review and pick the closest type for the full missing-activity and logic check."],
                'evidence': []}
    label = t['type'] + (f" ({t['category']})" if t.get('category') else "")
    conf = "looks like" if t['confident'] else "may be"
    body = [f"From the project and discipline names, this {conf} a **{label}** project (Construction Knowledge Base)."]
    if t['needs']:
        body.append("Activities this type usually needs — confirm they're present and logic-linked: " + ", ".join(t['needs']) + ".")
    if t['issues']:
        body.append("Common pitfalls for this type: " + "; ".join(t['issues']) + ".")
    return {'headline': f"What a {label} programme usually needs:", 'body': body,
            'advice': ["Run the **Constructability** review against this type for the full missing-activity, logic and WBS check."],
            'evidence': [{'module': 'Constructability KB', 'plain': 'Detected type', 'value': label}]}


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
    ('management', 'why_delayed'):     why_delayed_mgmt,
    ('management', 'which_wbs'):       which_wbs_mgmt,
    ('management', 'health'):          health_mgmt,
    ('management', 'risks'):           risks_mgmt,
    ('management', 'eot_likely'):      eot_likely_mgmt,
    ('management', 'can_claim'):       eot_likely_mgmt,
    ('management', 'actions'):         actions_mgmt,
    ('planning',   'why_delayed'):     why_delayed_planning,
    ('planning',   'critical_driver'): critical_driver_planning,
    ('planning',   'recovery'):        recovery_planning,
    ('planning',   'risks'):           risks_planning,
    ('planning',   'eot_likely'):      eot_likely_planning,
    ('planning',   'can_claim'):       eot_likely_planning,
    ('planning',   'delay_method'):    delay_method_planning,
    ('planning',   'project_needs'):   project_needs_planning,
}


def answer(question_id, ctx, mode='management'):
    fn = _ANSWERS.get((mode, question_id)) or _ANSWERS.get(('management', question_id))
    if not fn:
        return {'headline': "The offline Copilot can't answer that one yet.",
                'body': ["Pick one of the suggested questions — those are answered with your schedule's own evidence. "
                         "Free-form questions come with the premium cloud upgrade."],
                'advice': [], 'evidence': []}
    return fn(ctx)
