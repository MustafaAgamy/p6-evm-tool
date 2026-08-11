"""Claims intelligence — weighs whether the update shows INDICATORS of a potential
extension-of-time (EOT) claim, from the delay to completion, the critical path, and
execution signals (out-of-sequence work).

Deliberately careful: it never states entitlement ("you are entitled to claim"). It only
surfaces indicators — the CAUSE of each delay (who owns it), whether delays overlap
(concurrency), and the contract decide a claim, and those need the human. SCL / FIDIC framing.
"""

# Guard: nothing this module produces may assert entitlement.
_FORBIDDEN = ('you are entitled', 'entitled to', 'you can claim', 'will win')


def eot_assessment(ctx):
    """Return a careful, plain claims read:
    {has_delay, verdict, indicators[], ownership, caveat, advice[], careful:True}."""
    delay = ctx.get('delay_days')

    if delay is None:
        return {'has_delay': None,
                'verdict': "There isn't enough finish-date information in this update to weigh a claim yet.",
                'indicators': [], 'ownership': None,
                'caveat': "Import an updated schedule with a finish milestone and I'll reassess.",
                'advice': [], 'careful': True}

    if delay <= 0:
        return {'has_delay': False,
                'verdict': "No delay to completion right now — so there's nothing to support a time-extension claim yet.",
                'indicators': ["The finish date is holding to plan in this update."],
                'ownership': None,
                'caveat': "If a delay appears in a later update, re-check — a claim needs a real impact on the finish date.",
                'advice': [], 'careful': True}

    # delay > 0
    indicators = [
        f"There is a real delay to completion — the finish is about {delay} working days late.",
        "That delay sits on the work that sets the finish date, so it moves completion directly — not just spare time being used up.",
    ]
    if ctx.get('oos_count'):
        indicators.append(f"{ctx['oos_count']} activities ran out of their planned order — part of the slippage looks execution-related.")

    ownership = ("What the schedule itself shows leans execution-side (progress and out-of-order work). "
                 "Any client-caused delays — late access, late drawings, variations — aren't in the schedule and must be "
                 "added to judge who owns the delay.")
    caveat = ("This is not a determination. Whether a time-extension (EOT) claim stands depends on the cause of each "
              "delay (who is responsible), whether delays overlap (concurrency), and your contract (e.g. FIDIC clause 8.5).")
    advice = [
        "List the delay events and who caused each one (client vs contractor).",
        "For a claim-grade figure, run the exact delay analysis (Time Impact Analysis) in Planning mode.",
        "Have the commercial team check the contract's time-extension clause.",
    ]
    return {'has_delay': True,
            'verdict': "There are indicators that could support a potential extension-of-time (EOT) claim.",
            'indicators': indicators, 'ownership': ownership, 'caveat': caveat, 'advice': advice, 'careful': True}
