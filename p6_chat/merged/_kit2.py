"""Answer kit (v2) for the 15 merged chat questions.

A merged answer is one comprehensive, Claude-style reply to a question that used to be several:

    {'verdict': str,                              # the direct answer, one line
     'pills': [{'text', 'tone'}],                 # tone: danger | warning | success | accent | neutral
     'sections': [{'label', 'paras': [str], 'table': {'cols', 'rows', 'note'} | None}],
     'measured': str,                             # how this was measured from the P6 file
     'actions': [str],                            # what I'd do
     'evidence': [{'k', 'v'}],                    # the key numbers
     'drilldowns': [{'to': 'qNN', 'text'}],       # natural next questions (other merged ids)
     'tools': [{'cap', 'label'}]}                 # interactive tools to run from this answer
                                                  # cap: dashboard | whatif | tia | report

The service adds question/group/covers/thinking/specific/focus. Paragraph text accepts **bold**.

Rules every builder follows (binding):
  * Ground on F (DB facts) and N (network re-read from the P6 file) only. Never invent a number, an
    activity, or a project noun — use the names in N / F['disciplines'].
  * delay_days POSITIVE = behind. Negative total float = behind its dates.
  * The driver is the weighted one (K.main_driver: weight x gap), not the largest raw gap.
  * F['cost_derived'] True means actual cost equals earned value in the file: never say "on budget".
  * N may be {'ok': False} (file missing): say so once and answer from F; never crash.
  * Where the file can't prove something (causation, entitlement, a second baseline, resources,
    contract dates, weather) say so plainly and route to the feature that can.
"""
from p6_chat.qa import _kit as K

# number/phrase helpers re-exported so builders import one kit
wd, weeks, pct, ratio, money = K.wd, K.weeks, K.pct, K.ratio, K.money
delay_phrase, spi_verdict, main_driver = K.delay_phrase, K.spi_verdict, K.main_driver

TONES = ('danger', 'warning', 'success', 'accent', 'neutral')


def pill(text, tone='neutral'):
    return {'text': str(text), 'tone': tone if tone in TONES else 'neutral'} if text else None


def ev(k, v):
    return None if v is None or v == '' else {'k': str(k), 'v': str(v)}


def tbl(cols, rows, note=None):
    rows = [[('—' if c is None else str(c)) for c in r] for r in (rows or [])]
    if not rows:
        return None
    t = {'cols': [str(c) for c in cols], 'rows': rows}
    if note:
        t['note'] = note
    return t


def sec(label, *paras, table=None):
    return {'label': label, 'paras': [p for p in paras if p], 'table': table}


def drill(to, text):
    return {'to': to, 'text': text}


def tool(cap, label):
    return {'cap': cap, 'label': label}


def A2(verdict, sections, pills=(), measured='', actions=(), evidence=(), drilldowns=(), tools=()):
    return {
        'verdict': verdict,
        'pills': [p for p in pills if p],
        'sections': [s for s in sections if s and (s.get('paras') or s.get('table'))],
        'measured': measured,
        'actions': [a for a in actions if a],
        'evidence': [e for e in evidence if e],
        'drilldowns': [d for d in drilldowns if d],
        'tools': [t for t in tools if t],
    }


def no_project():
    return A2("Send me your P6 schedule first.",
              [sec('What I need', "Drag a .xer or .xml P6 export anywhere in the chat, or choose a file — I'll read "
                                  "it and answer from your own numbers. Offline: nothing leaves your PC.")])


def signed(d):
    """'+60 wd (behind)' / '-12 wd (ahead)' / 'on the date'."""
    if d is None:
        return None
    d = round(d)
    return f"+{d} wd (behind)" if d > 0 else (f"{d} wd (ahead)" if d < 0 else 'on the date')


def network_note(N):
    """One honest line when the P6 file couldn't be re-read (answer continues from stored numbers)."""
    if N and N.get('ok'):
        return ''
    return ("I couldn't re-read the schedule file this time (" + ((N or {}).get('error') or 'file not found') +
            "), so the activity-level detail below is limited to the stored numbers. Re-import the file to restore it.")


def rows_of(items, fields, limit=12):
    """Pick fields from N rows for a table, capped; returns (rows, more_count)."""
    items = list(items or [])
    return [[x.get(f) for f in fields] for x in items[:limit]], max(0, len(items) - limit)


def cost_note(F):
    """The honest line about CPI when cost is derived from progress."""
    if F.get('cost_derived'):
        return ("Don't read the CPI of " + ratio(F.get('cpi')) + " as 'on budget': in this file actual cost equals "
                "earned value (cost is derived from progress), so CPI is 1.00 by construction and says nothing "
                "about money. The schedule position is measured; the cost position is not.")
    cpi = F.get('cpi')
    if cpi is None:
        return "Cost performance can't be read from this file (no actual cost loaded)."
    word = 'over' if cpi < 0.98 else ('under' if cpi > 1.02 else 'close to')
    return f"CPI is {ratio(cpi)} — running {word} budget on the work done so far."
