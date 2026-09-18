"""Baseline Narrative — a deterministic, plain-English status narrative built from
the already-computed EVM result (SPI/CPI/delay/overall %/category progress).

`build_narrative(result)` returns a structured, section-keyed narrative so the same
text drives the on-screen view and (later) the PDF — no LLM, works fully offline.
Every value is guarded: missing metrics degrade to a shorter, still-correct sentence.
"""
from datetime import datetime, date


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _pct(frac):
    """A stored fraction (0–1) → '58%'. None → '—'."""
    f = _num(frac)
    return '—' if f is None else f'{round(f * 100)}%'


def _date(v):
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.strftime('%d %b %Y')
    s = str(v)[:10]
    try:
        return datetime.strptime(s, '%Y-%m-%d').strftime('%d %b %Y')
    except ValueError:
        return s or None


def spi_phrase(spi):
    s = _num(spi)
    if s is None:
        return 'is progressing', 'neutral'
    if s >= 1.02:
        return 'is ahead of schedule', 'good'
    if s >= 0.98:
        return 'is on schedule', 'good'
    if s >= 0.90:
        return 'is slightly behind schedule', 'warn'
    if s >= 0.80:
        return 'is behind schedule', 'bad'
    return 'is significantly behind schedule', 'bad'


def cpi_phrase(cpi):
    c = _num(cpi)
    if c is None:
        return 'is progressing', 'neutral'
    if c >= 1.02:
        return 'is under budget', 'good'
    if c >= 0.98:
        return 'is on budget', 'good'
    if c >= 0.90:
        return 'is slightly over budget', 'warn'
    return 'is over budget', 'bad'


def build_narrative(result):
    """result → {'headline': str, 'tone': str, 'sections': [{key,title,tone,paragraphs}]}.
    Tone is one of good/warn/bad/neutral, so the UI can colour the verdict."""
    result = result or {}
    name = result.get('project_name') or 'This project'
    dd = _date(result.get('data_date'))
    planned = _num(result.get('overall_planned_pct'))
    actual = _num(result.get('overall_actual_pct'))
    spi = _num(result.get('spi'))
    cpi = _num(result.get('cpi'))
    delay = result.get('delay_days')
    delay = None if delay is None else int(delay)

    sched_txt, sched_tone = spi_phrase(spi)
    cost_txt, cost_tone = cpi_phrase(cpi)

    # ── Executive summary ──
    asof = f'As of the {dd} update, ' if dd else ''
    lead = f'{asof}{name} {sched_txt}'
    if actual is not None and planned is not None:
        gap = round((actual - planned) * 100)
        rel = ('level with the plan' if abs(gap) <= 1
               else f'{abs(gap)} points {"ahead of" if gap > 0 else "behind"} the planned {_pct(planned)}')
        lead += f', with {_pct(actual)} of the work complete — {rel}.'
    else:
        lead += '.'
    if spi is not None:
        lead += f' The Schedule Performance Index (SPI) is {spi:.2f}.'
    summary = [lead]

    # ── Schedule performance ──
    sched = []
    if spi is not None:
        earned = ('more' if spi >= 1 else 'less')
        sched.append(f'An SPI of {spi:.2f} means the project has earned {earned} value than planned '
                     f'for the time elapsed; it {sched_txt}.')
    if delay is not None:
        if delay > 0:
            sched.append(f'The current forecast finishes about {delay} day{"s" if abs(delay) != 1 else ""} '
                         f'later than the baseline. Recovery of this slippage should be the focus of the next period.')
        elif delay < 0:
            sched.append(f'The current forecast finishes about {abs(delay)} day{"s" if abs(delay) != 1 else ""} '
                         f'earlier than the baseline — a positive schedule position.')
        else:
            sched.append('The current forecast finish is level with the baseline finish date.')
    if not sched:
        sched.append('Schedule-performance metrics were not available in this update.')

    # ── Cost performance ──
    cost = []
    pv, ev, ac = _num(result.get('pv')), _num(result.get('ev')), _num(result.get('ac'))
    if cpi is not None:
        cost.append(f'The Cost Performance Index (CPI) is {cpi:.2f}; the project {cost_txt}.')
    if pv is not None and ev is not None and ac is not None:
        cost.append(f'Planned Value is {_egp(pv)}, Earned Value {_egp(ev)} and Actual Cost {_egp(ac)}.')
    if not cost:
        cost.append('Cost-performance metrics were not available in this update.')

    # ── Progress by area (categories) ──
    cats = result.get('categories') or {}
    area = []
    if cats:
        ranked = sorted(
            ((n, _num(c.get('planned_pct')), _num(c.get('actual_pct'))) for n, c in cats.items()),
            key=lambda t: ((t[2] or 0) - (t[1] or 0)))
        behind = [t for t in ranked if t[1] is not None and t[2] is not None and (t[2] - t[1]) < -0.005]
        ahead = [t for t in ranked if t[1] is not None and t[2] is not None and (t[2] - t[1]) > 0.005]
        if behind:
            worst = behind[0]
            area.append(f'The area furthest behind plan is {worst[0]} ({_pct(worst[2])} actual vs {_pct(worst[1])} planned).'
                        + (f' {len(behind)} of {len(cats)} areas are behind their planned progress.' if len(behind) > 1 else ''))
        if ahead:
            best = ahead[-1]
            area.append(f'{best[0]} is the strongest area, running ahead of plan at {_pct(best[2])} against {_pct(best[1])} planned.')
        if not behind and not ahead:
            area.append('All areas are tracking close to their planned progress.')
    else:
        area.append('No category breakdown was available for this update.')

    # ── Outlook & recommendation ──
    worst_tone = 'bad' if 'bad' in (sched_tone, cost_tone) else ('warn' if 'warn' in (sched_tone, cost_tone) else 'good')
    if worst_tone == 'good':
        outlook = ['The schedule and cost position are both healthy. Maintain the current plan and continue '
                   'monitoring the critical path for emerging risks.']
    elif worst_tone == 'warn':
        outlook = ['Performance is slipping at the margins. Target the areas behind plan and confirm the critical '
                   'path has not moved before the variance widens.']
    else:
        behind_bit = ' and recover the areas behind plan' if cats else ''
        outlook = [f'Corrective action is warranted. Re-sequence or add resource to the critical path{behind_bit}, '
                   f'and re-baseline the recovery plan for review at the next update.']

    return {
        'headline': lead,
        'tone': worst_tone,
        'sections': [
            {'key': 'summary',    'title': 'Executive summary',        'tone': sched_tone, 'paragraphs': summary},
            {'key': 'schedule',   'title': 'Schedule performance',     'tone': sched_tone, 'paragraphs': sched},
            {'key': 'cost',       'title': 'Cost performance',         'tone': cost_tone,  'paragraphs': cost},
            {'key': 'areas',      'title': 'Progress by area',         'tone': 'neutral',  'paragraphs': area},
            {'key': 'outlook',    'title': 'Outlook & recommendation', 'tone': worst_tone, 'paragraphs': outlook},
        ],
    }


def _egp(n):
    n = _num(n)
    if n is None:
        return '—'
    a = abs(n)
    if a >= 1e9:
        return f'{n / 1e9:.2f}B'
    if a >= 1e6:
        return f'{n / 1e6:.1f}M'
    return f'{n:,.0f}'
