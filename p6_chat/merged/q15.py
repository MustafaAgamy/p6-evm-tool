"""q15 — Reporting: the dashboard, board summary, narrative, and this week's messages.

Covers: the headline message, a one-page board/client summary, a paste-ready monthly narrative, the
planned-vs-actual-vs-forecast S-curve, what the professional dashboard shows (tiles, five charts, gap by
activity code, styles), this week's focus, the late client inputs to table, risks, good news, a
red-amber-green read and the portfolio / LD position — for ANY project.

Everything is composed from F (stored EVM + audit facts) and N (the network re-read from the P6 file).
Cost is never called "on budget" when actual cost is derived from progress; blame is never assigned from a
single snapshot; RAG colours are labelled as a planning judgement (no shipped RAG control); LD exposure and
portfolio are stated as gaps. Nothing project-specific is hardcoded.
"""
import re
from datetime import datetime

from . import _kit2 as K

_NUM_WORDS = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight',
              9: 'nine', 10: 'ten', 11: 'eleven', 12: 'twelve'}
_TRADE_RE = re.compile(r'\b(works?|installations?|erection|civil|mechanical|electrical|steel|structur\w*|cables?|'
                       r'finish(?:es|ing)|mep|piling|foundations?|concrete|architectur\w*|commissioning|hvac|'
                       r'plumbing|infra\w*|roads?|earthworks?|landscap\w*|fit[- ]?out)\b', re.I)
_PRIMARY = [(r'\bpil(?:e|es|ing)\b', 'piling'), (r'excavat', 'excavation'),
            (r'\bsoil\b|backfill|compaction|earthwork', 'soil works'), (r'column', 'columns'),
            (r'\bbeams?\b', 'beams'), (r'\bsog\b|slab', 'slabs'), (r'\brafts?\b', 'raft'),
            (r'footing|foundation', 'foundations'), (r'\bwalls?\b', 'walls'), (r'\broof', 'roofing'),
            (r'cladding|fa[cç]ade|(?:silos?|roof|wall)\s+sheets?\b|sheeting', 'sheeting / cladding'),
            (r'catwalk|steel', 'steelwork'), (r'\bcables?\b|conduct|conduit|wiring', 'cabling'),
            (r'terminat', 'terminations'), (r'conveyor|roller|equipment|assembl', 'equipment installation'),
            (r'asphalt|paving', 'paving')]
_SECONDARY = [(r'concrete|pour', 'concrete'), (r'\btests?\b|testing', 'testing'),
              (r'waterproof|insulation', 'insulation / waterproofing'), (r'paint|coating', 'coatings')]
_SUPPLY_RE = re.compile(r'^(?:deliver\w*|supply|shipment)\b|\bdelivery (?:for|of)\b|\b(?:shipment|equipment|'
                        r'materials?|accessories|free[- ]issue|furnished)\b', re.I)
_GENERIC_TOKENS = {'design', 'engineering', 'phase', 'works', 'work', 'procurement', 'construction', 'and', 'the',
                   'installation', 'general', 'package', 'scope', 'detailed', 'schematic'}
_GREEN = {'excellent', 'very good', 'good'}
_AMBER = {'acceptable', 'needs attention', 'fair'}
_RED = {'poor', 'critical'}


# ── small helpers ────────────────────────────────────────────────────────────────

def _word(n):
    return _NUM_WORDS.get(n, f"{n:,}") if isinstance(n, int) else str(n)


def _cap(s):
    return s[:1].upper() + s[1:] if s else s


def _date(s):
    if not s:
        return None
    for fmt in ('%d-%b-%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(s).strip()[:11], fmt)
        except ValueError:
            continue
    return None


def _fmt(dt):
    return dt.strftime('%d-%b-%Y') if dt else None


def _sg(n):
    if n is None:
        return '—'
    n = round(n)
    return f"{n:+d}" if n else '0'


def _m(v, unit=None):
    """Compact, currency-neutral value: '562.7M', '2.33M', '45.1K'. unit='M' forces millions."""
    if v is None:
        return '—'
    a, s = abs(v), ('-' if v < 0 else '')
    if unit == 'M':
        return s + (f"{a / 1e6:.1f}M" if a >= 1e7 else f"{a / 1e6:.2f}M")
    if a >= 1e9:
        return s + f"{a / 1e9:.2f}B"
    if a >= 1e7:
        return s + f"{a / 1e6:.1f}M"
    if a >= 1e6:
        return s + f"{a / 1e6:.2f}M"
    if a >= 1e3:
        return s + f"{a / 1e3:.1f}K"
    return s + f"{a:,.0f}"


def _is_ms(x):
    return 'Milestone' in (x.get('type') or '')


def _nm(x, limit=None):
    s = ' '.join(str((x.get('name') if isinstance(x, dict) else x) or '').split())
    if limit and len(s) > limit:
        cut = s[:limit].rsplit(' ', 1)[0]
        s = cut.rstrip(' ,;:-&') + '…'
    return s


def _brief(x, limit=48):
    """A long activity name cut to its subject: 'Full Release for Area X to Start Works on Area X' -> 'Full Release
    for Area X'. Falls back to a word-boundary cut."""
    s = _nm(x)
    if len(s) <= limit:
        return s
    head = re.split(r'\s+(?:to|before|so that)\s+', s, maxsplit=1)[0]
    return head if 10 <= len(head) <= limit else _nm(x, limit)


def _last_wbs(x):
    parts = [p for p in (x.get('wbs') or '').split(' / ') if p]
    return parts[-1] if parts else ''


def _where(x):
    """The activity's last WBS level when it adds something its name doesn't already say, else ''."""
    last = _last_wbs(x)
    toks = re.findall(r'[A-Za-z]{4,}', last.lower())
    return '' if (not last or any(t in _nm(x).lower() for t in toks)) else last


def _tag(x):
    w = _where(x)
    return f"{w} '{_nm(x)}'" if w else _nm(x)


def _trade_of(wbs):
    parts = [p for p in (wbs or '').split(' / ') if p]
    for i in range(len(parts) - 1, 0, -1):
        if _TRADE_RE.search(parts[i]):
            return parts[i], parts[i + 1:]
    if len(parts) == 1:
        return parts[0], []
    return (' / '.join(parts[-2:]) if parts else '(no WBS)'), []


def _trades(chain):
    out = {}
    for x in chain or []:
        if _is_ms(x):
            continue
        label, locs = _trade_of(x.get('wbs'))
        t = out.setdefault(label, {'label': label, 'locs': [], 'items': []})
        loc = ' / '.join(locs)
        if loc and loc not in t['locs']:
            t['locs'].append(loc)
        t['items'].append(x)
    return list(out.values())


def _locs_text(locs):
    if not locs:
        return ''
    split = [l.split(' / ') for l in locs]
    if len({s[0] for s in split}) == 1 and any(len(s) > 1 for s in split):
        tails = [' / '.join(s[1:]) for s in split if len(s) > 1]
        return f"{split[0][0]} — {', '.join(tails[:4])}"
    return ', '.join(locs[:4])


def _trade_text(t, detail=None):
    inner = ': '.join(x for x in (_locs_text(t['locs']), ', '.join(detail or [])) if x)
    return t['label'] + (f" ({inner})" if inner else '')


def _work_types(names, limit=6):
    seen = []
    for nm in names:
        prim = [lab for rx, lab in _PRIMARY if re.search(rx, nm, re.I)]
        for lab in (prim or [lab for rx, lab in _SECONDARY if re.search(rx, nm, re.I)]):
            if lab not in seen:
                seen.append(lab)
    return seen[:limit]


def _join(items, last='and'):
    items = [i for i in items if i]
    if len(items) <= 1:
        return ''.join(items)
    return ', '.join(items[:-1]) + f" {last} " + items[-1]


def _short_ms(name):
    """'Zone B Mechanical Installation Completion' -> 'Zone B Mechanical' (sectional milestone shorthand)."""
    s = _nm(name)
    s2 = re.sub(r'\s+(?:Works\s+)?(?:Installation\s+)?Completion$', '', s, flags=re.I)
    s2 = re.sub(r'\s+Works$', '', s2, flags=re.I)
    return s2 or s


def _rag(grade):
    g = (grade or '').strip().lower()
    return 'GREEN' if g in _GREEN else ('AMBER' if g in _AMBER else ('RED' if g in _RED else None))


def _kp(F, mod):
    return ((F.get('audit') or {}).get(mod) or {}).get('kpis') or {}


def _grade(F, mod):
    return ((F.get('audit') or {}).get(mod) or {}).get('grade')


def _tokens(s):
    return {t for t in re.findall(r'[a-z0-9]{3,}', (s or '').lower()) if t not in _GENERIC_TOKENS}


# ── the answer ───────────────────────────────────────────────────────────────────

def build(F, N, role):
    nok = bool(N and N.get('ok'))
    d = F.get('delay_days')
    d = None if d is None else round(d)
    behind, ahead = (d or 0) > 0, (d or 0) < 0
    wk = F.get('delay_weeks') or (max(1, round(abs(d) / 5)) if d else None)
    spi, cpi = F.get('spi'), F.get('cpi')
    ap, pp = F.get('actual_pct'), F.get('planned_pct')
    derived = bool(F.get('cost_derived'))
    drv = K.main_driver(F)
    dd_s = F.get('data_date') or (N.get('data_date') if nok else None)
    dd = _date(dd_s)
    thinking = []

    # finish milestone (file first, then stored facts / the CPLI record)
    ck = _kp(F, 'cpli')
    fin = (N.get('finish_milestone') or {}) if nok else {}
    ff = fin.get('finish') or F.get('forecast_finish') or _fmt(_date(ck.get('finish_date')))
    bf = fin.get('baseline_finish') or F.get('baseline_finish')
    ftf = fin.get('tf') if fin.get('tf') is not None else ck.get('project_total_float_days')
    fname = _nm(fin.get('name')) or 'the finish'
    Fname = _cap(fname)
    fid = fin.get('id')
    fname_id = f"{fname} ({fid})" if fid else fname
    Fname_id = _cap(fname_id)
    bf_sp = (bf + ' ') if bf else ''
    signed = K.signed(d) if d is not None else None

    # network pieces
    chain = (N.get('chain') or []) if nok else []
    trades = _trades(chain)
    t1 = trades[0] if trades else None
    t1_wt = _work_types([x['name'] for x in t1['items']]) if t1 else []
    t1_started = any((x.get('pct') or 0) > 0 for x in t1['items']) if t1 else True
    deepest = (N.get('deepest') or []) if nok else []
    client = (N.get('client_inputs') or []) if nok else []
    client_ids = {x['id'] for x in client}
    open_inputs = [x for x in client if not x['done']]
    late_open = (N.get('client_inputs_late_open') or []) if nok else []
    late_open_neg = [x for x in late_open if (x.get('tf') or 0) < 0]
    due_now = [x for x in late_open if x.get('finish') and x.get('finish') == dd_s]
    supply = [x for x in client if _SUPPLY_RE.search(x.get('name') or '')]
    fixed = [x for x in supply if not x['done'] and (x.get('slip_wd') or 0) <= 0 and x.get('tf') == 0]
    sup_late_done = [x for x in supply if x['done'] and (x.get('slip_wd') or 0) > 0]
    ms_all = (N.get('milestones') or []) if nok else []
    secs = [x for x in ms_all if not x['done'] and x['id'] not in client_ids and x['id'] != fid
            and x.get('tf') is not None]
    secs_late_neg = [x for x in secs if (x.get('slip_wd') or 0) > 0 and x['tf'] < 0]
    secs_deep = [x for x in secs_late_neg if x['tf'] < -10]
    secs_shallow = [x for x in secs_late_neg if x['tf'] >= -10]
    secs_pos = [x for x in secs if x['tf'] >= 0]
    good_ms = [x for x in secs_pos if (x.get('slip_wd') or 0) <= 20][:2]
    secs_pos_late = [x for x in secs_pos if (x.get('slip_wd') or 0) > 0 and x not in good_ms]
    chain_ms = [x for x in chain if _is_ms(x)]
    end_ms = chain_ms[-1] if chain_ms else (fin or None)

    # stored value gap by code
    vg = F.get('value_gap') or {}
    groups = [g for g in (vg.get('groups') or []) if isinstance(g, dict)]
    vg_top = next((g for g in groups if (g.get('gap') or 0) > 0), None)
    vg_total = vg.get('total_gap')

    # audit
    nf, nfp = F.get('neg_float_count'), F.get('neg_float_pct')
    crit, critp = F.get('cpli_critical_count'), F.get('cpli_critical_pct')
    cpli, cpl, target = ck.get('cpli'), ck.get('critical_path_length_days'), ck.get('target')
    lag = _kp(F, 'lag_lead')
    hc = _kp(F, 'hard_constraints')
    loops = _kp(F, 'circular').get('loops')
    leads = _kp(F, 'leads').get('leads')
    has_audit = bool(F.get('audit'))

    # dashboard verdict (same rule as the in-chat dashboard)
    db_behind = (spi is not None and spi < 0.98) or (d is not None and d > 0)
    db_ahead = (spi is not None and spi >= 1.0) and (d is None or d <= 0)
    verdict_word = 'AHEAD' if (db_ahead and not db_behind) else ('BEHIND' if db_behind else 'ON TRACK')
    reasons = []
    if verdict_word == 'BEHIND':
        if spi is not None and spi < 0.9:
            reasons.append('SPI is below 0.9')
        elif spi is not None and spi < 0.98:
            reasons.append('SPI is below 0.98')
        if d is not None and d > 10:
            reasons.append('the delay is over 10 wd')
        elif d is not None and d > 0:
            reasons.append('the finish is behind its baseline')
    elif verdict_word == 'AHEAD':
        reasons.append('SPI is at or above 1.0 and the finish holds its baseline')
    else:
        reasons.append('neither SPI nor the finish shows a slip')

    t1_name = t1['label'] if t1 else (drv['name'] if drv else 'driving')
    chain_path = ' → '.join([t['label'] for t in trades[:5]]) if trades else ''

    # ── 1. headline message ─────────────────────────────────────────────────────
    if behind:
        where = (f"the {_trade_text(t1)}" if t1 else (f"{drv['name']}, which carries {round((drv.get('weight') or 0) * 100)}% "
                                                      "of the weight" if drv else 'the chain that sets the finish'))
        where += ", and client inputs that are still outstanding" if late_open_neg else ''
        h1 = (f"**Lead with the date. {Fname} is now forecast for {ff or 'a later date'} against "
              f"{'a ' + bf if bf else 'its'} baseline, about {d} working days ({wk} weeks) late. Then say where the "
              f"delay sits: {where}.**")
        sc = [f"We are about {wk} weeks behind programme."]
        if bf and ff:
            sc.append(f"{Fname} has moved from {bf} to {ff}.")
        if drv:
            sc.append(f"The delay is in {drv['name']}, which is {round((drv.get('weight') or 0) * 100)}% of the job and "
                      f"stands at {drv['actual']}% against {drv['planned']}% planned.")
        if t1:
            sc.append(f"More precisely, it is in the {_trade_text(t1)}.")
            if len(trades) > 1:
                sc.append(("Those works have not started, and they" if not t1_started else "Those works")
                          + f" now drive the finish through {_join([t['label'] for t in trades[1:5]])}.")
        if late_open_neg:
            sc.append(f"{_cap(_word(len(late_open_neg)))} client input{'s are' if len(late_open_neg) > 1 else ' is'} "
                      "still outstanding on negative float, including "
                      f"{_join([_brief(x) for x in late_open_neg[:3]])}.")
        asks = [f"a recovery plan for the {t1_name} sequence"] + (["committed dates for those client inputs"]
                                                                  if late_open_neg else [])
        sc.append(f"We need {_word(len(asks))} decision{'s' if len(asks) > 1 else ''}: {_join(asks)}.")
        h2 = '"' + ' '.join(sc) + '"'
        h3 = ("Why this order: the date is what the room cares about, naming the front tells them it is one specific "
              "front rather than the whole job, and the asks turn a status report into a decision.")
        stay = []
        if derived:
            stay.append(f"cost. CPI reads {K.ratio(cpi)} only because actual cost in this file equals earned value "
                        "(cost is derived from progress), so 'on budget' is not something this file can support")
        if late_open_neg:
            stay.append("blame. Say the client inputs are outstanding, late and on negative float, and stop there. "
                        "Whether they drove the finish, and by how many days, needs a windows / TIA analysis. One "
                        "snapshot can't prove it")
        if len(stay) == 2:
            h3 += f" Two things stay out of the headline. The first is {stay[0]}. The second is {stay[1]}."
        elif stay:
            h3 += f" One thing stays out of the headline: {stay[0]}."
        if not derived:
            h3 += " " + K.cost_note(F) + " Put that in the headline too — it is measured, not derived."
    elif ahead:
        h1 = (f"**Lead with the date. {Fname} is forecast for {ff or 'its date'}"
              + (f" against {bf}" if bf else '') + f", about {abs(d)} working days ahead (SPI {K.ratio(spi)}). The "
              "message is protection, not recovery.**")
        sc = [f"We are about {wk} week{'s' if wk != 1 else ''} ahead of programme, earning {K.pct(ap)} against "
              f"{K.pct(pp)} planned."]
        if drv:
            sc.append(f"The one line below plan is {drv['name']} ({drv['actual']}% against {drv['planned']}%), and "
                      "we are watching it.")
        sc.append("We will hold the margin by keeping the driving path resourced and the logic clean.")
        h2 = '"' + ' '.join(sc) + '"'
        h3 = ("Why this order: the date is what the room cares about, and a margin is only worth reporting if you say "
              "how you'll keep it. " + K.cost_note(F)
              + (" Cost is measured in this file, so it belongs in the headline." if not derived else ''))
    else:
        h1 = f"**Lead with the date: {fname} is holding {ff or 'its date'} (SPI {K.ratio(spi)}).**"
        h2 = '"We are on programme. ' + (f"The line to watch is {drv['name']}." if drv else '') + '"'
        h3 = K.cost_note(F)
    s_head = K.sec('The headline message — lead with this', h1, h2, h3)

    # ── 2. one-page board / client summary ──────────────────────────────────────
    rows = [['Progress', f"{K.pct(ap)} earned vs {K.pct(pp)} planned (SPI {K.ratio(spi)})"]]
    if ff:
        rows.append(['Finish', f"{Fname_id}: " + (f"baseline {bf} → " if bf else '') + f"forecast {ff}"
                     + (f", {_sg(d)} wd (~{wk} weeks)" if d else '') + (f", total float {_sg(ftf)}" if ftf is not None else '')])
    if drv:
        gap_row = f"{drv['name']} ({round((drv.get('weight') or 0) * 100)}% weight): {drv['actual']}% vs {drv['planned']}%."
        if vg_top and vg_total:
            gap_row += (f" {vg_top['code']} hold{'s' if not str(vg_top['code']).endswith('s') else ''} "
                        f"{_m(vg_top['gap'])} of the {_m(vg_total)} planned-vs-earned gap ({round(vg_top.get('pct_of_gap') or 0, 2)}%)")
        rows.append(['Where the gap is', gap_row])
    if t1:
        rows.append(['What drives the date', f"{_trade_text(t1, t1_wt)}"
                     + (' → ' + ' → '.join(t['label'] for t in trades[1:5]) if len(trades) > 1 else '')
                     + (f" → {_nm(end_ms)} ({end_ms['id']}), {end_ms.get('finish')}" if end_ms else '')])
        c0 = chain[0]
        c0_due = _date(c0.get('baseline_finish'))
        rows.append(['First link in that chain',
                     f"{_tag(c0)} ({c0['id']}): baseline finish {c0.get('baseline_finish')}, "
                     + (f"still 0% at the data date, " if (c0.get('pct') == 0 and c0_due and dd and c0_due <= dd)
                        else f"{c0.get('pct')}% done, ")
                     + f"now {c0.get('finish')}, float {_sg(c0.get('tf'))}"])
    dneg = [x for x in deepest if (x.get('tf') or 0) < 0][:2]
    if dneg:
        rows.append(['Deepest negative float', '; '.join(f"{_tag(x)} ({x['id']}) {_sg(x['tf'])} wd" for x in dneg)
                     + (', both 0%' if len(dneg) == 2 and all(x.get('pct') == 0 for x in dneg) else '')])
    if late_open:
        rows.append(['Client inputs outstanding',
                     f"{len(late_open)} of {len(open_inputs)} open inputs past baseline"
                     + (" and on negative float" if len(late_open_neg) == len(late_open) else
                        (f", {len(late_open_neg)} on negative float" if late_open_neg else ''))
                     + ", including " + '; '.join(f"{_brief(x)} {_sg(x['slip_wd'])} wd (float {_sg(x['tf'])})"
                                                  for x in late_open[:3])])
    sec_list = secs_deep[:6] or secs_late_neg[:6]
    if sec_list or good_ms:
        sd = ', '.join(f"{_short_ms(x['name'])} {_sg(x['slip_wd'])}" + (' wd' if i == 0 else '')
                       for i, x in enumerate(sec_list))
        if good_ms:
            sd += ('. ' if sd else '') + (f"{_join([_short_ms(x['name']) + ' ' + _sg(x['slip_wd']) for x in good_ms])}"
                                          f", {'both ' if len(good_ms) == 2 else ''}on positive float "
                                          f"({', '.join(_sg(x['tf']) for x in good_ms)})")
        rows.append(['Sectional dates', sd])
    rows.append(['Cost', ("Not reported from this file. Actual cost equals earned value (derived from progress), so "
                          f"CPI {K.ratio(cpi)} carries no cost information") if derived else K.cost_note(F)])
    if behind:
        dec = [f"Recovery plan on the {t1_name} chain"] + (['Committed dates for the outstanding client inputs']
                                                           if late_open_neg else [])
    else:
        dec = ['Confirm how the margin is protected (driving path resourced, logic kept clean)']
    rows.append(['Decisions needed', ' '.join(f"({i + 1}) {x}." for i, x in enumerate(dec)).rstrip('.')])
    s_board = K.sec('One-page board / client summary', table=K.tbl(
        ['Measure', 'Position'], rows,
        note=f"Every row comes from the {dd_s} snapshot. Compose and export it in Reporting Studio, which pulls the "
             "same live figures, so the page can't drift away from the KPIs."
             + (" Keep the cause row as 'where it sits': one snapshot can't show how much of the delay is the "
                "employer's and how much is the contractor's." if behind else '')))
    thinking.append(f"Composed the board summary from the {dd_s} snapshot: SPI {K.ratio(spi)}, "
                    f"{K.pct(ap)} vs {K.pct(pp)}" + (f", {signed}" if signed else ''))

    # ── 3. monthly narrative ────────────────────────────────────────────────────
    nv = [f"As at the {dd_s} data date, the project is {K.pct(ap)} complete against a planned {K.pct(pp)} "
          f"(SPI {K.ratio(spi)})."]
    if ff and d is not None:
        if behind:
            nv.append(f"{Fname_id} is forecast for {ff}" + (f" against the {bf} baseline" if bf else '')
                      + f", approximately {d} working days ({wk} weeks) late"
                      + (f", and the project carries {ftf} working days of total float." if (ftf is not None and ftf < 0)
                         else '.'))
        elif ahead:
            nv.append(f"{Fname_id} is forecast for {ff}" + (f" against the {bf} baseline" if bf else '')
                      + f", approximately {abs(d)} working days ahead.")
        else:
            nv.append(f"{Fname_id} is forecast on its baseline date of {ff}.")
    if drv and behind:
        nv.append(f"The shortfall sits in {drv['name']}, which carries {round((drv.get('weight') or 0) * 100)}% of project "
                  f"weight and stands at {drv['actual']}% against {drv['planned']}% planned"
                  + (f"; {vg_top['code']} account{'s' if not str(vg_top['code']).endswith('s') else ''} for "
                     f"{round(vg_top.get('pct_of_gap') or 0, 2)}% of the gap between planned and earned value"
                     if vg_top else '') + '.')
    if t1 and behind:
        nv.append(f"The finish is driven by the {_trade_text(t1)}" + (f": {_join(t1_wt)}." if t1_wt else '.'))
        if not t1_started:
            nv.append("None of these works has started.")
        if len(trades) > 1:
            nv.append(f"They are followed by {_join([t['label'] for t in trades[1:5]])}"
                      + (f" to {_nm(end_ms)} ({end_ms['id']})." if end_ms else '.'))
        dn2 = [x for x in dneg if _trade_of(x.get('wbs'))[0] in {t['label'] for t in trades}]
        if dn2:
            nv.append("The most negative float on the programme sits on this front: "
                      + _join([f"'{_nm(x)}'" + (f" on {_where(x)}" if _where(x) else '') + f" at {x['tf']} working days"
                               for x in dn2]) + '.')
    if late_open_neg and behind:
        nv.append(f"{_cap(_word(len(late_open_neg)))} employer input{'s remain' if len(late_open_neg) > 1 else ' remains'} "
                  "outstanding on negative-float paths, including "
                  + _join([f"{_brief(x, 60)} ({x['slip_wd']} working days past baseline)" for x in late_open_neg[:3]]) + '.')
    if secs_late_neg and behind:
        nv.append(f"Sectional completions for {_join([_short_ms(x['name']) + ' (' + _sg(x['slip_wd']) + ')' for x in secs_deep[:3] or secs_late_neg[:3]])} "
                  "follow the same chain"
                  + (f", while {_join([_short_ms(x['name']) for x in good_ms])} remain within "
                     f"{max(x['slip_wd'] for x in good_ms)} working days of baseline." if good_ms else '.'))
    if behind:
        nv.append(f"Recovery measures on the {t1_name} sequence"
                  + (", together with confirmed dates for the outstanding employer inputs," if late_open_neg else '')
                  + " are being evaluated and will be sized before commitment.")
    elif ahead:
        nv.append("The margin is being protected by keeping the driving path resourced and the logic clean.")
    n2 = []
    if derived:
        n2.append("Cost is not mentioned because this file holds no independent actual cost.")
    if behind and late_open_neg:
        n2.append("The paragraph also doesn't say who caused the delay: the employer inputs are stated as facts "
                  "(outstanding, late, on negative float), and apportioning days to them needs a windows / TIA analysis "
                  "in Consultant Review or Update vs Update.")
    lead2 = f"{_cap(_word(len(n2)))} thing{'s are' if len(n2) > 1 else ' is'} left out on purpose. " if n2 else ''
    s_narr = K.sec('Monthly schedule narrative — drafted, ready to paste', '"' + ' '.join(nv) + '"',
                   (lead2 + ' '.join(n2) + " For the full monthly report, compose it in Reporting Studio so the "
                    "narrative, the tables and the KPIs all come from the same figures.").strip())

    # ── 4. S-curve ──────────────────────────────────────────────────────────────
    pv, ev_ = F.get('pv'), F.get('ev')
    s1 = (f"The curve has three legs. The planned leg reaches {K.pct(pp)}" + (f" (PV {_m(pv)})" if pv else '')
          + f" at the {dd_s} data date. The earned leg sits at {K.pct(ap)}" + (f" (EV {_m(ev_)})" if ev_ else ''))
    if pv and ev_:
        s1 += (f", and the {_m(abs(pv - ev_))} vertical gap between the two is the schedule variance"
               + (" (earned ahead of plan)" if ev_ > pv else ''))
    s1 += '.'
    if ff:
        s1 += (f" The forecast leg runs on to {ff}"
               + (f", {abs(d)} wd to the {'right' if behind else 'left'} of the {bf_sp}baseline finish."
                  if d else '.'))
    if derived:
        s1 += (" An actual-cost line would sit exactly on the earned line (AC = EV in this file), so don't present it "
               "as a separate cost story.")
    if behind:
        cap_line = (f"'The gap is {drv['name'] if drv else 'the driving work'}"
                    + (f"; the late finish comes from the {t1_name} chain.'" if t1 else ".'"))
        s2 = (f"Put one sentence under the chart so nobody misreads it: {cap_line} A caveat on the forecast leg: it "
              "follows the schedule as it stands at the data date, not a mitigated plan. Any recovery move, for example "
              f"adding a crew or overlapping work on the {t1_name} chain, has to be run in the What-if first. That "
              "gives an instant estimate, then the P6-exact figure after an F9 round-trip. Only after that should you "
              "draw a recovered curve.")
    else:
        s2 = ("Put one sentence under the chart so nobody misreads it: where the margin comes from and what protects "
              "it. The forecast leg follows the schedule as it stands at the data date.")
    tr = F.get('trend')
    if tr and tr.get('prev_delay') is not None:
        s2 += (f" Since the previous update the delay moved from {K.signed(tr['prev_delay'])} to {signed}, so the "
               "trend can be stated from the stored history.")
    else:
        s2 += (" Also, this snapshot shows where the gap stands, not whether it is widening or closing. Compare it with "
               "the previous update in Update vs Update before you describe the trend.")
    s_curve = K.sec('Planned vs actual vs forecast S-curve', s1, s2)

    # ── 5. the board ────────────────────────────────────────────────────────────
    b1 = f"**One screen: {'an' if verdict_word[0] in 'AEIOU' else 'a'} {verdict_word} verdict, six KPI tiles and five charts."
    if behind and drv and t1:
        b1 += f" On this file every chart points the same way, at {drv['name']} feeding the {t1_name} chain."
    b1 += '**'
    tiles = [f"SPI {K.ratio(spi)}", f"CPI {K.ratio(cpi)}", f"{K.pct(ap)} complete against {K.pct(pp)}",
             f"delay {_sg(d)} wd" if d is not None else 'delay —', f"EV {_m(ev_)}", f"PV {_m(pv)}"]
    b2 = ("Ask for the professional dashboard and you get a single executive board built from the imported file. At "
          f"the top is the health verdict: {verdict_word}, because {_join(reasons)}. Next come six tiles: "
          f"{_join(tiles)}. Below them are five charts: the S-curve, the SPI/CPI gauges, a time-status bar, planned vs "
          "actual by discipline, and the EV-vs-PV gap by activity code. Every figure is the same number the EVM tab "
          "shows. The board is calculated rather than written, and it runs offline.")
    cant = []
    if derived:
        cant.append('a cost story (AC = EV)')
    cant.append('resource loading (not in this read)')
    if hc.get('contract_milestones') == 0:
        cant.append('a contract date (no contract milestones)')
    else:
        cant.append("a contract date (the tool reads P6 dates, not the contract's)")
    b3 = (f"Some things the board can't show from this file: {_join(cant, 'or')}. It shows the schedule story"
          + (", and that is the one that matters on this project." if behind else '.'))
    s_board2 = K.sec('What sits on the board', b1, b2, b3)

    # ── 6. five charts table ────────────────────────────────────────────────────
    def zone(v):
        return '' if v is None else ('in the green' if v >= 0.98 else ('in the amber' if v >= 0.9 else 'in the red'))
    ds = sorted(F.get('disciplines') or [], key=lambda x: -(x.get('weight') or 0))
    crow = [['Cost-loading S-curve', f"Planned {K.pct(pp)}" + (f" (PV {_m(pv)})" if pv else '') + f" vs earned {K.pct(ap)}"
             + (f" (EV {_m(ev_)})" if ev_ else '') + f" at {dd_s}" + (f"; forecast leg to {ff}" if ff else '')],
            ['SPI / CPI gauges', f"SPI {K.ratio(spi)} {zone(spi)}. "
             + (f"CPI {K.ratio(cpi)} on the line, but only by construction (AC = EV)" if derived else
                f"CPI {K.ratio(cpi)} {zone(cpi)}")],
            ['Time-status bar', (f"{bf} → {ff}" if (bf and ff) else (ff or '—'))
             + (f", {_sg(d)} wd (~{wk} weeks)" if d else '')],
            ['Planned vs actual by discipline', '; '.join(
                f"{x['name']} {x['planned']}% / {x['actual']}% ({round((x.get('weight') or 0) * 100)}% weight)"
                for x in ds[:8]) or '—'],
            ['EV-vs-PV gap by activity code',
             (f"{vg_top['code']} {_m(-vg_top['gap'])} of the {_m(-vg_total)} total ({round(vg_top.get('pct_of_gap') or 0, 2)}%)"
              if (vg_top and vg_total) else "Computed live from the file when the board opens (not stored with this snapshot)")]]
    widest = max(ds, key=lambda x: x.get('gap') or 0) if ds else None
    note = "Read the discipline bars by weight, not by length."
    if drv and widest and widest['name'] != drv['name'] and (widest.get('gap') or 0) > (drv.get('gap') or 0):
        note += (f" The {widest['name']} bar looks worst, but weighs {round((widest.get('weight') or 0) * 100)}%. The "
                 f"{drv['name']} bar has a smaller gap and carries almost the whole delay.")
    if derived:
        note += (" Read the gauges as a pair with one caveat: SPI is the signal, and the CPI needle sits on 1.00 because "
                 "of how cost is recorded in this file, not because of cost performance.")
    s_charts = K.sec('The five charts — and what they read on this update',
                     table=K.tbl(['Chart', 'Reads now'], crow, note=note))

    # ── 7. EV-vs-PV gap by activity code ────────────────────────────────────────
    if groups and vg_total:
        unit = 'M' if abs(vg.get('total_pv') or vg_total) >= 1e6 else None
        topp = vg_top.get('pct_of_gap') or 0 if vg_top else 0
        share = (f"almost all of it is {vg_top['code']}" if topp >= 80 else
                 (f"most of it is {vg_top['code']}" if topp >= 50 else
                  f"it is spread, with {vg_top['code']} leading at {round(topp)}%")) if vg_top else 'no code value is behind'
        g1 = (f"This chart draws one bar per code value: the value planned to date minus the value earned. It shows "
              f"where the {_m(vg_total, unit)} shortfall sits, not just how big it is. Using the file's "
              f"{vg.get('dimension') or 'activity'} code, {share}.")
        grows = [[g['code'], _m(g.get('pv'), unit), _m(g.get('ev'), unit), _m(-(g.get('gap') or 0), unit),
                  f"{round(g.get('pct_of_gap') or 0, 2)}%"] for g in groups[:8]]
        if vg.get('total_pv') is not None:
            grows.append(['Total', _m(vg.get('total_pv'), unit), _m(vg.get('total_ev'), unit), _m(-vg_total, unit), '100%'])
        zeros = [g['code'] for g in groups if not (g.get('pv') or 0) and not (g.get('ev') or 0)]
        gnote = ("These are real rows from the file's " + (vg.get('dimension') or 'activity') + " code. The board uses "
                 "whichever code dimension carries the most cost and ranks the largest gap first.")
        if zeros:
            gnote += (f" A zero for {_join(zeros[:3])} means no value was planned in {'them' if len(zeros) > 1 else 'it'} "
                      f"by {dd_s}. It does not mean {'they are' if len(zeros) > 1 else 'it is'} on time")
            on_chain = [z for z in zeros if any(_tokens(z) & _tokens(t['label']) for t in trades)]
            ctfs = [x['tf'] for x in chain if x.get('tf') is not None]
            gnote += (f": {_join(on_chain)} sit{'s' if len(on_chain) == 1 else ''} on the finish chain at "
                      f"{_sg(max(ctfs))} to {_sg(min(ctfs))} float." if (on_chain and ctfs) else '.')
        gnote += (" To split the leading bar further, switch the code dimension (for example to a phase or area code, "
                  "if the file carries one) in Update Analysis.")
        s_gap = K.sec('EV-vs-PV gap by activity code', g1,
                      table=K.tbl([f"Activity code ({vg.get('dimension') or 'code'})", 'PV', 'EV', 'Gap', 'Share of gap'],
                                  grows, note=gnote))
    else:
        s_gap = K.sec('EV-vs-PV gap by activity code',
                      "This chart draws one bar per code value: the value planned to date minus the value earned, so it "
                      "shows where the shortfall sits, not just how big it is. The split by code isn't stored with this "
                      "snapshot, so I won't quote one; the board computes it live from the file (it picks the code "
                      "dimension carrying the most cost and ranks the largest gap first), and Update Analysis shows the "
                      "same split by any code."
                      + (f" What the stored figures do show: the total gap is {_m(abs(pv - ev_))} (PV {_m(pv)} vs EV "
                         f"{_m(ev_)})" + ((f", and by discipline the weighted driver is {drv['name']}." if behind else
                                           f", and the one discipline below plan on the weighted read is {drv['name']}.")
                                          if drv else '.') if (pv and ev_) else ''))

    # ── 8. styles ───────────────────────────────────────────────────────────────
    s_style = K.sec('Styles you can pick',
                    "The board has three formats: Executive, Midnight and Blueprint. You switch between them with the "
                    "control in the board's header. Only the look changes; the numbers stay the same. Use Executive for "
                    "the client or board pack, Blueprint for the internal planning review, and Midnight for a "
                    "meeting-room screen. For a formal report, open Reporting Studio from the board's footer and add the "
                    "board there, so the exported document carries the same figures.")

    # ── 9. this week ────────────────────────────────────────────────────────────
    wk_items = []
    d0 = None
    if behind:
        focus = ([f"get the {t1_name} chain moving"] if t1 else [f"get {drv['name'] if drv else 'the driving work'} moving"])
        if late_open_neg:
            focus.append('get committed dates for the open client inputs')
        w0 = (f"**This week, put the effort in {_word(len(focus))} place{'s' if len(focus) > 1 else ''}: "
              f"{_join(focus)}. That is where the {d} days sit.**")
        if chain:
            c0 = chain[0]
            c0_due = _date(c0.get('baseline_finish'))
            if c0.get('pct') == 0 and c0_due and dd and c0_due <= dd:
                wk_items.append(f"Start the chain. {_tag(c0)} ({c0['id']}) was due to finish on {c0['baseline_finish']} "
                                f"and is still at 0%. It now forecasts {c0['finish']} at {_sg(c0['tf'])} float, and it "
                                "heads the chain that runs to the finish. Find out what is holding it (area, crew, plant "
                                "or approval) and put a start date on it this week.")
            else:
                wk_items.append(f"Protect the head of the chain. {_tag(c0)} ({c0['id']}) is {c0.get('pct')}% done and "
                                f"forecasts {c0['finish']} at {_sg(c0['tf'])} float. Keep it resourced every day this week.")
            d0 = next((x for x in deepest if x['id'] != c0['id'] and (x.get('tf') or 0) < (c0.get('tf') or 0)), None)
            if d0:
                wk_items.append(f"Clear the deepest point. {_tag(d0)} ({d0['id']}) is at {d0.get('pct')}% with "
                                f"{_sg(d0['tf'])} float, the most negative in the network. Everything after it on the "
                                "finish chain waits on it.")
        elif drv:
            wk_items.append(f"Put the best resource on {drv['name']} ({drv['actual']}% vs {drv['planned']}% planned, "
                            f"{round((drv.get('weight') or 0) * 100)}% of the weight): it is where the weighted gap sits.")
        if late_open_neg:
            wk_items.append("Chase the client inputs in writing. Ask for a committed date on each open input, starting "
                            "with " + _join([f"{_brief(x)} ({x['id']}, float {_sg(x['tf'])})" for x in late_open_neg[:4]])
                            + ". Record each request. These are EOT indicators, and the records are what any later "
                            "claim rests on.")
        wk_items.append("Table the recovery plan this update, not next. Test each move in the What-if before promising "
                        "days." + (f" Anything that doesn't shorten the {chain_path} chain won't move {ff}."
                                   if (chain_path and ff) else " Only moves on the driving chain shift the finish."))
    else:
        w0 = ("**This week, protect the margin: keep the driving path resourced and the logic clean, so the "
              f"{abs(d) if d else ''} wd {'margin ' if d else ''}survives the next update.**").replace('  ', ' ')
        if drv:
            wk_items.append(f"Watch {drv['name']} ({drv['actual']}% vs {drv['planned']}% planned): it is the one line "
                            "below plan, so keep it from becoming the driver.")
        wk_items.append("Re-read the driving path after the update and keep the crews on it, not on float work.")
    small = [x for x in (F.get('disciplines') or []) if (x.get('weight') or 0) <= 0.05 and (x.get('gap') or 0) >= 20
             and (not drv or x['name'] != drv['name'])]
    if small and behind:
        txt = (f"Keep the {_join([x['name'] for x in small[:3]])} gap{'s' if len(small) > 1 else ''} in proportion. "
               + _join([f"{x['name']} ({x['actual']}% vs {x['planned']}%)" for x in small[:3]])
               + f" weigh{'s' if len(small) == 1 else ''} {_join(sorted({str(round((x.get('weight') or 0) * 100)) + '%' for x in small}))}"
               + (' each' if len(small) > 1 else '') + f" and {'don' if len(small) > 1 else 'doesn'}'t drive {fname}.")
        exc = None
        for x in small:
            tk = _tokens(x['name'])
            hit = next((c for c in late_open if tk & _tokens(c.get('name'))), None) if tk else None
            if hit:
                exc = (x, hit)
                break
        if exc:
            txt = txt.replace(' in proportion.', ' in proportion, with one exception.')
            txt += (f" The exception is that {exc[0]['name']} waits on a client input: '{_nm(exc[1])}' ({exc[1]['id']}) is "
                    f"{exc[1]['slip_wd']} wd past baseline. Report it as an outstanding client input, not as that team "
                    "falling behind.")
        wk_items.append(txt)
    if F.get('dangling_count') or F.get('critical_oos') or F.get('open_ends'):
        bits = [f"the {F['dangling_count']} dangling activities" if F.get('dangling_count') else '',
                f"the {F['open_ends']} open ends" if F.get('open_ends') else '',
                f"the {F['critical_oos']} out-of-sequence activit{'y' if F.get('critical_oos') == 1 else 'ies'} on the "
                "critical path" if F.get('critical_oos') else '']
        wk_items.append("Tidy the logic" + (" before the what-if" if behind else '') + f". Clear {_join(bits)}, so the "
                        + ("recovery scenario" if behind else 'next update') + " schedules cleanly.")
    s_week = K.sec('This week — to protect the end date', w0, *[f"{i + 1}. {x}" for i, x in enumerate(wk_items)])

    # ── 10. late client inputs ──────────────────────────────────────────────────
    s_inputs = None
    if nok and late_open:
        l1 = (f"{_cap(_word(len(late_open)))} of the {_word(len(open_inputs))} client inputs still open in the file "
              f"{'are' if len(late_open) > 1 else 'is'} past {'their' if len(late_open) > 1 else 'its'} baseline "
              f"date{'s' if len(late_open) > 1 else ''}"
              + (f", all on negative float" if len(late_open_neg) == len(late_open) and len(late_open) > 1 else
                 (' and on negative float' if len(late_open_neg) == len(late_open) else
                  f", {len(late_open_neg)} of them on negative float"))
              + (" and still at 0%" if all((x.get('pct') or 0) == 0 for x in late_open) else '') + '.')
        if due_now:
            l1 += (f" For the {_word(len(due_now))} that P6 now shows as due on the data date, the slip grows by one "
                   "working day for every working day they stay open.")
        l2 = ("These are strong EOT indicators: employer-side items, late, on paths that are already behind. They are "
              f"not yet proof. Whether each one actually moved {fname}"
              + (f", and by how much compared with the contractor's own {t1_name} slippage," if t1 else ',')
              + " needs a windows / TIA analysis (Consultant Review, Update vs Update). Report them as facts and let "
                "that analysis apportion the days." if behind else
              "They are employer-side items past their dates; with the finish holding, they are eating float rather "
              "than moving the date. Record them anyway, because they become EOT indicators the moment float runs out.")
        irows = [[f"{_nm(x)} ({x['id']})",
                  f"{x.get('baseline_finish')} → " + ('still open' if x.get('finish') == dd_s else (x.get('finish') or '—')),
                  _sg(x.get('slip_wd')), _sg(x.get('tf'))] for x in late_open[:10]]
        inote = []
        if fixed:
            by_date = {}
            for x in fixed:
                by_date.setdefault(x['finish'], []).append(_nm(x))
            dts = sorted(by_date, key=lambda s: _date(s) or datetime.max)
            inote.append(f"{_cap(_word(len(fixed)))} client deliver{'ies are' if len(fixed) > 1 else 'y is'} still forecast on "
                         f"{'their' if len(fixed) > 1 else 'its'} baseline date{'s' if len(fixed) > 1 else ''} but carr"
                         f"{'y' if len(fixed) > 1 else 'ies'} zero float: "
                         + '; '.join(f"{_join(by_date[t])} on {t}" for t in dts[:3]) + '.')
        if sup_late_done:
            lo, hi = min(x['slip_wd'] for x in sup_late_done), max(x['slip_wd'] for x in sup_late_done)
            inote.append(f"Separately, {_word(len(sup_late_done))} client-furnished deliver"
                         f"{'ies have' if len(sup_late_done) > 1 else 'y has'} already arrived, "
                         f"{lo}{'' if lo == hi else f'-{hi}'} wd after baseline. Keep those delivery records with the "
                         "claim file.")
        s_inputs = K.sec('Late client inputs — the asks to table this week', l1, l2,
                         table=K.tbl(['Client input (ID)', 'Baseline → now', 'Slip (wd)', 'Float (wd)'], irows,
                                     note=' '.join(inote) or None))
        thinking.append(f"Checked {len(client)} client/employer inputs: {len(late_open)} open and late, "
                        f"{len(late_open_neg)} on negative float")
    elif nok:
        s_inputs = K.sec('Late client inputs — the asks to table this week',
                         "No client or employer input in the file is open and past its baseline date, so there is no "
                         "client ask to table this week." + (f" {len(client)} client inputs were checked." if client else ''))

    # ── 11. risks ───────────────────────────────────────────────────────────────
    rk = []
    if nf is not None:
        broad = (nfp or 0) >= 20
        r1 = (("The pressure is broad, so there is nothing left to absorb a further slip. " if broad and behind else '')
              + f"{nf:,} activities ({K.pct(nfp, 1)}) are on negative float"
              + (f" and {crit:,} ({K.pct(critp, 1)}) are at critical float" if crit is not None else '') + '.')
        if cpli is not None and cpl:
            r1 += (f" CPLI is {K.ratio(cpli)} against a {K.ratio(target) if target else '0.95'} target: the {cpl}-wd "
                   f"critical path is carrying {_sg(ftf)} float.")
        if behind and ff:
            r1 += f" Any further day lost on the {t1_name} chain lands on {ff}."
        rk.append(r1)
    elif not has_audit:
        rk.append("There is no stored Schedule Health Review for this update, so float and critical-path density can't "
                  "be quoted; run it before the report goes out.")
    if secs_deep or secs_shallow or secs_pos_late:
        r2 = ''
        if secs_deep:
            r2 += ("The downstream sectional dates follow the driving chain. " if t1 else "Sectional dates are slipping. ") \
                + _join([f"{_short_ms(x['name'])} {_sg(x['slip_wd'])}" + (' wd' if i == 0 else '') + f" (float {_sg(x['tf'])})"
                         for i, x in enumerate(secs_deep[:6])]) + '.'
        pos_txt = (_join([f"{_short_ms(x['name'])} ({_sg(x['slip_wd'])}" + (' wd' if i == 0 else '') + f", float {_sg(x['tf'])})"
                          for i, x in enumerate(secs_pos_late[:3])])
                   + f" still hold{'s' if len(secs_pos_late) == 1 else ''} positive float") if secs_pos_late else ''
        neg_txt = (_join([f"{_short_ms(x['name'])} ({_sg(x['tf'])})" for x in secs_shallow[:3]])
                   + f" {'have' if len(secs_shallow) > 1 else 'has'} just gone negative") if secs_shallow else ''
        if pos_txt or neg_txt:
            r2 += (" Other sections are slipping too. " if secs_deep else "Sections are slipping. ") \
                + (f"{pos_txt}, but {neg_txt}." if (pos_txt and neg_txt) else f"{pos_txt or neg_txt}.")
        rk.append(r2.strip())
    if late_open_neg or fixed:
        rk.append("The client dependencies are still open: "
                  + (f"the {_word(len(late_open_neg))} input{'s' if len(late_open_neg) > 1 else ''} in the table above"
                     if late_open_neg else 'no late inputs, but')
                  + (f", plus {_word(len(fixed))} deliver{'ies' if len(fixed) > 1 else 'y'} at zero float. A late delivery "
                     "there lands on a path with no margin." if fixed else '.'))
    if lag.get('lagged_count') and (lag.get('lagged_pct') or 0) > (lag.get('dcma_lag_line') or 5):
        rk.append(f"The lags will draw questions. {lag['lagged_count']:,} links carry a lag ({lag.get('lagged_pct')}%, "
                  f"against the {lag.get('dcma_lag_line') or 5:g}% guideline)"
                  + (f", {lag['critical_count']} of them are on the critical path" if lag.get('critical_count') else '')
                  + (f", and {lag['need_justification_count']} are longer than {lag.get('long_threshold_days') or 14} wd "
                     "without a documented reason" if lag.get('need_justification_count') else '')
                  + ". A consultant will ask about these before accepting the forecast.")
    cannot = []
    if derived:
        cannot.append('cost risk (AC = EV)')
    cannot.append("whether crews are short (this read carries no resource loading, so a productivity delay can't be "
                  "told apart from an input-driven one)")
    cannot.append('LD exposure (no contract milestones in the file)' if hc.get('contract_milestones') == 0 else
                  "LD exposure (contract dates and rates aren't read)")
    if not (tr and tr.get('prev_delay') is not None):
        cannot.append('the trend (a single snapshot)')
    rk.append(f"What this file can't tell you: {_join(cannot)}.")
    if not nok:
        rk.insert(0, K.network_note(N))
    s_risk = K.sec('Risks to flag to management', *rk)

    # ── 12. good news ───────────────────────────────────────────────────────────
    gn = []
    if ahead:
        gn.append(f"The date itself: {fname} is forecast {abs(d)} wd ahead of its {bf_sp}baseline, with SPI {K.ratio(spi)}.")
    done = [x for x in (F.get('disciplines') or []) if (x.get('actual') or 0) >= 99.5 and (x.get('planned') or 0) >= 99.5]
    if done:
        g = (f"{_join([x['name'] for x in done])} {'are' if len(done) > 1 else 'is'} finished: "
             f"{'both' if len(done) == 2 else ('all' if len(done) > 2 else 'it is')} at 100% against 100% planned")
        subs = [s for s in (F.get('submittals') or []) if isinstance(s, dict) and (s.get('req') or 0) >= 5
                and (s.get('actual_appr') or 0) >= 0.9 * (s.get('req') or 1)]
        if subs:
            s0 = max(subs, key=lambda s: s.get('req') or 0)
            g += (f", and {s0['actual_appr']} of {s0['req']} {s0.get('trade') or ''} "
                  f"{(s0.get('submittal_type') or 'submittal').lower()}s are approved").replace('  ', ' ')
        g += '.' + (" The front end isn't what's holding construction." if behind else '')
        gn.append(g)
    near = [x for x in (F.get('disciplines') or []) if x not in done and (x.get('actual') or 0) >= 90
            and (x.get('planned') or 0) >= 90]
    for x in near[:2]:
        gn.append(f"{x['name']} is effectively done: {x['actual']}% against {x['planned']}%.")
    if good_ms:
        gm_txt = [_nm(x) + ' forecasts ' + str(x['finish']) + ' (' + _sg(x['slip_wd']) + ' wd)' for x in good_ms]
        gn.append(f"{_join(gm_txt)}. "
                  f"{'Both are' if len(good_ms) == 2 else 'It is'} well off the critical path (float "
                  f"{_join([_sg(x['tf']) for x in good_ms])}), so that is a near-term milestone you can show.")
    q_bits = []
    if F.get('open_ends') == 0:
        q_bits.append('0 open ends')
    if loops == 0:
        q_bits.append('0 logic loops')
    if leads == 0:
        q_bits.append('0 leads')
    if F.get('oos_pct') is not None and _rag(F.get('oos_grade')) == 'GREEN':
        q_bits.append(f"out-of-sequence at {F['oos_pct']}%")
    if F.get('dangling_pct') is not None and _rag(F.get('dangling_grade')) == 'GREEN':
        q_bits.append(f"dangling at {F['dangling_pct']}%")
    if len(q_bits) >= 3:
        g = f"The schedule is honest and well built: {_join(q_bits)}."
        if nf:
            g += (" The negative float shows openly rather than being masked, so "
                  f"{ff or 'the forecast'} is a genuine logic result. A recovery plan built on this network will "
                  "schedule the way you expect.")
        gn.append(g)
    if not gn:
        gn.append("Nothing in the stored figures stands out as good news beyond the facts above; lead with the plan "
                  "instead.")
    s_good = K.sec('Good news to open the client meeting with', *gn)

    # ── 13. RAG ─────────────────────────────────────────────────────────────────
    def rag_spi(v):
        return None if v is None else ('RED' if v < 0.9 else ('AMBER' if v < 0.98 else 'GREEN'))
    rr = [['Schedule (SPI)', f"{K.ratio(spi)} · {K.pct(ap)} vs {K.pct(pp)}", rag_spi(spi) or 'GREY: not measurable']]
    if d is not None:
        rr.append(['Finish date', (f"{fid} " if fid else '') + (f"{bf} → " if bf else '') + f"{ff or '—'} · {_sg(d)} wd"
                   + (f" · float {_sg(ftf)}" if ftf is not None else ''),
                   'RED' if d > 10 else ('AMBER' if d > 0 else 'GREEN')])
    if nf is not None:
        rr.append(['Float health', f"{nf:,} on negative float ({K.pct(nfp, 1)}) · graded {F.get('neg_float_grade') or '—'}",
                   _rag(F.get('neg_float_grade')) or 'AMBER'])
    if cpli is not None:
        rr.append(['Critical-path density (CPLI)',
                   f"CPLI {K.ratio(cpli)} vs {K.ratio(target) if target else '0.95'} target"
                   + (f" · {crit:,} at critical float ({K.pct(critp, 1)})" if crit is not None else '')
                   + (f" · {F.get('cpli_density_grade')}" if F.get('cpli_density_grade') else ''),
                   'GREEN' if cpli >= 1.0 else ('AMBER' if cpli >= (target or 0.95) else 'RED')])
    if nok:
        rr.append(['Client inputs', (f"{len(late_open)} of {len(open_inputs)} open, late"
                                     + (" and on negative float" if late_open_neg else '') if late_open else 'none late')
                   + (f" · {len(fixed)} deliveries at zero float" if fixed else ''),
                   'RED' if late_open_neg else ('AMBER' if (late_open or fixed) else 'GREEN')])
    if lag.get('lagged_count') is not None:
        lr = _rag(_grade(F, 'lag_lead'))
        rr.append(['Lags', f"{lag['lagged_count']:,} lagged links ({lag.get('lagged_pct')}% vs {lag.get('dcma_lag_line') or 5:g}% line)"
                   + (f" · {lag['critical_count']} on critical path" if lag.get('critical_count') else '')
                   + (f" · {lag['need_justification_count']} need a reason" if lag.get('need_justification_count') else '')
                   + (f" · tool grade {_grade(F, 'lag_lead')}" if _grade(F, 'lag_lead') else ''),
                   'AMBER' if lr in ('RED', 'AMBER') else (lr or 'GREY: not measurable')])
    if F.get('oos_count') is not None:
        rr.append(['Out-of-sequence', f"{F['oos_count']} ({K.pct(F.get('oos_pct'), 1)})"
                   + (f" · {F['critical_oos']} on the critical path" if F.get('critical_oos') else '')
                   + (f" · {F.get('oos_grade')}" if F.get('oos_grade') else ''), _rag(F.get('oos_grade')) or 'AMBER'])
    if F.get('dangling_count') is not None or F.get('open_ends') is not None:
        worst = [g for g in (_rag(F.get('dangling_grade')), _rag(F.get('open_ends_grade'))) if g]
        rr.append(['Dangling / open ends', f"{F.get('dangling_count') if F.get('dangling_count') is not None else '—'} dangling"
                   + (f" ({K.pct(F.get('dangling_pct'), 1)})" if F.get('dangling_pct') is not None else '')
                   + f" · {F.get('open_ends') if F.get('open_ends') is not None else '—'} open ends"
                   + (f" · {F.get('dangling_grade')}" if F.get('dangling_grade') else ''),
                   'RED' if 'RED' in worst else ('AMBER' if 'AMBER' in worst else ('GREEN' if worst else 'AMBER'))])
    rr.append(['Cost (CPI)', f"{K.ratio(cpi)} by construction (AC = EV)" if derived else f"{K.ratio(cpi)}",
               'GREY: not measurable' if (derived or cpi is None) else ('RED' if cpi < 0.9 else ('AMBER' if cpi < 0.98 else 'GREEN'))])
    rr.append(['Resources', 'No resource loading in this read', 'GREY: not measurable'])
    reds = sum(1 for r in rr if r[2] == 'RED')
    rnote = ("The tool has no one-click RAG control yet. These colours are my read, set from the Schedule Health Review "
             "grades and the EVM figures (SPI below 0.9 = red).")
    if reds >= 2 and behind and t1:
        rnote += (f" The {_word(reds)} reds are not scattered: they are one delay seen {_word(reds)} ways, sitting on the "
                  f"{t1_name} chain" + (" and the client inputs." if late_open_neg else '.'))
    if any(r[0] in ('Out-of-sequence', 'Dangling / open ends') and r[2] == 'GREEN' for r in rr) and reds:
        rnote += " The greens are the network quality that makes the reds believable."
    if lag.get('lagged_count') is not None and _rag(_grade(F, 'lag_lead')) == 'RED':
        rnote += (" I've set lags to amber rather than red because fixing them is a justification task, not a driver of "
                  "the delay.")
    if derived:
        rnote += (" Cost stays grey rather than green, because calling it green would mean reporting a result the file "
                  "doesn't hold.")
    s_rag = K.sec('Red-amber-green health view', table=K.tbl(['Dimension', 'Reading', 'RAG'], rr, note=rnote))
    thinking.append(f"Set a RAG read across {len(rr)} dimensions from the health grades and EVM ({reds} red)")

    # ── 14. portfolio / LD ──────────────────────────────────────────────────────
    p1 = ("Reporting is single-project today. A side-by-side portfolio view (SPI, delay and exposure per job) isn't in "
          "the app yet. It will arrive with the Power BI live dashboards that are in progress, and the database already "
          "stores every project and snapshot for it.")
    p2 = ("LD exposure can't be computed from this file. "
          + ("The file has no contract milestones (the constraint check found 0), and the tool" if hc.get('contract_milestones') == 0
             else "The tool") + " doesn't read contract dates or LD rates.")
    if behind and ff:
        p2 += (f" What I can give the commercial team is the indicator: {fname} is forecast {d} wd past its "
               f"{bf_sp}baseline. If {bf or 'that baseline'} is also the contractual date, that is the "
               "exposure window, before netting off any extension of time"
               + (" the late client inputs may support" if late_open_neg else '') + ". The rate and the netting are for "
               "the commercial team to apply under the contract terms.")
    elif ahead:
        p2 += f" On today's forecast there is no exposure window: {fname} sits {abs(d)} wd ahead of its baseline."
    s_port = K.sec('Portfolio / LD view', p1, p2)

    # ── pills / measured / actions / evidence ───────────────────────────────────
    pills = [K.pill(f"{_sg(d)} wd · ~{wk} weeks {'late' if behind else 'ahead'}", 'danger' if behind else 'success')
             if d else K.pill('On the planned finish', 'success'),
             K.pill(f"SPI {K.ratio(spi)} · {K.pct(ap)} vs {K.pct(pp)}",
                    'danger' if (spi or 1) < 0.9 else ('warning' if (spi or 1) < 0.98 else 'success')),
             K.pill(f"{vg_top['code']} = {round(vg_top.get('pct_of_gap') or 0, 2)}% of the value gap", 'warning')
             if vg_top else (K.pill(f"Driver: {drv['name']}", 'warning') if drv and behind else None),
             K.pill(f"Finish driven by {t1_name}", 'warning') if (t1 and behind) else None,
             K.pill(f"{len(late_open_neg)} client input{'s' if len(late_open_neg) > 1 else ''} open on negative float",
                    'warning') if late_open_neg else None,
             K.pill(f"{nf:,} on negative float ({K.pct(nfp, 1)})", 'danger' if (nfp or 0) >= 20 else 'warning')
             if nf else None,
             K.pill(f"CPI {K.ratio(cpi)} = derived, not a cost signal", 'neutral') if derived else
             K.pill(f"CPI {K.ratio(cpi)}", 'warning' if (cpi or 1) < 0.98 else 'success'),
             K.pill(f"Logic clean · {F.get('open_ends')} open ends · OOS {F.get('oos_pct')}%", 'success')
             if (F.get('open_ends') == 0 and _rag(F.get('oos_grade')) == 'GREEN') else None,
             K.pill('3 board formats', 'accent')]
    m = [f"Everything comes from the {dd_s} snapshot of '{F.get('project_name')}'"
         + (f" ({N.get('activity_count'):,} activities)." if nok and N.get('activity_count') else '.'),
         "Dates, total float and % complete are P6's own exported values."]
    if d is not None and ff:
        m.append(f"The {_sg(d)} wd is {fname_id}'s forecast finish ({ff}) against its baseline finish"
                 + (f" ({bf})" if bf else '') + (f", and it matches that milestone's {_sg(ftf)} total float."
                                                 if (ftf is not None and round(ftf) == -d) else '.'))
    m.append(f"SPI is the weighted actual % divided by the planned % across the {len(F.get('disciplines') or [])} "
             "disciplines. The tool re-derives PV and EV from the file's budgets and progress, because P6 XML doesn't "
             "export them, so treat them as a close approximation rather than P6's own figures.")
    m.append("CPI is 1.00 because actual cost in the file equals earned value." if derived else
             "CPI is EV ÷ AC from the file's actual cost.")
    if nok and chain:
        tfs = [x['tf'] for x in chain if x.get('tf') is not None]
        m.append(f"The finish chain is the file's driving path into {fid or 'the finish milestone'}"
                 + (f" ({_sg(max(tfs))} to {_sg(min(tfs))} float)" if tfs else '') + '.')
    if vg_top:
        m.append(f"The value gap by code is PV minus EV grouped on the {vg.get('dimension') or 'activity'} code.")
    if has_audit:
        ta = _kp(F, 'dangling').get('total_activities') or _kp(F, 'float').get('total_activities')
        tr_ = lag.get('total_relationships')
        m.append("The health grades (float, negative float, OOS, dangling, lags, CPLI) are the Schedule Health Review "
                 "bands" + (f" on {ta:,} activities" if ta else '') + (f" and {tr_:,} relationships" if tr_ else '') + '.')
    if nok:
        m.append("Client-input and milestone slips are baseline finish vs current finish, in working days.")
    m.append("The RAG colours are a planning judgement set from those grades, not an automatic score.")
    m.append(("The file has no contract milestones and this read has no resource loading, so LD exposure and "
              "resource-driven delay are not measured.") if hc.get('contract_milestones') == 0 else
             "Contract dates and resource loading are not read, so LD exposure and resource-driven delay are not measured.")
    if not nok:
        m.append(K.network_note(N))
    measured = ' '.join(m)

    if behind:
        actions = [
            f"Open every report and meeting with the date ({ff or 'the forecast'}"
            + (f" against {bf}" if bf else '') + f", about {d} wd late), then where the delay sits"
            + (f" (the {t1_name} chain" + (" and the open client inputs)" if late_open_neg else ')') if t1 else '')
            + ", then the asks.",
            (f"This week, get a start date for {_tag(chain[0])} ({chain[0]['id']})"
             + (f" and clear {_tag(d0)} ({d0['id']})" if (chain and d0) else '') + ". They head the finish chain.")
            if chain else (f"This week, put the best resource on {drv['name']}." if drv else ''),
            (f"Send a written request for committed dates on the {_word(len(late_open_neg))} open client inputs, led by "
             f"{_join([_brief(x) for x in late_open_neg[:3]])}, and keep the records for the EOT case.")
            if late_open_neg else '',
            "Run each recovery move in the What-if (instant estimate, then P6 F9) before a recovered date goes on the "
            "S-curve or into the narrative.",
            "Paste the drafted narrative into the monthly report through Reporting Studio."
            + (" Leave cost out" if derived else '') + (", and state the client inputs as facts, not blame."
                                                          if late_open_neg else ('.' if derived else '')),
            "Present the dashboard in the Executive format."
            + (f" Walk the room through the gap-by-code bar ({vg_top['code']} {round(vg_top.get('pct_of_gap') or 0, 2)}%), "
               "then switch the code in Update Analysis to show where inside it the gap sits." if vg_top else
               " Walk the room through the discipline bars by weight, then the gap-by-code bar."),
            ("Before the report goes to the consultant, "
             + _join([f"clear the {F['critical_oos']} critical out-of-sequence activities" if F.get('critical_oos') else '',
                      f"the {F['dangling_count']} dangling ones" if F.get('dangling_count') else '',
                      f"write a justification for the {lag['need_justification_count']} lags over "
                      f"{lag.get('long_threshold_days') or 14} wd" if lag.get('need_justification_count') else '']) + '.')
            if (F.get('critical_oos') or F.get('dangling_count') or lag.get('need_justification_count')) else '',
            "Run Update vs Update and Consultant Review against the previous update. That states the trend and starts "
            "separating employer delay from contractor delay.",
            "Ask the commercial team for the contract completion date and LD rate so the exposure window can be stated "
            "rather than assumed."]
    else:
        actions = [
            f"Open reports with the date ({ff or 'the forecast'}"
            + (f", {abs(d)} wd ahead of {bf}" if (d and bf) else '') + ") and how the margin is protected.",
            (f"Keep {drv['name']} ({drv['actual']}% vs {drv['planned']}%) from becoming the driver." if drv else ''),
            "Present the dashboard in the Executive format and paste the narrative through Reporting Studio.",
            (f"Report cost next to the date (CPI {K.ratio(cpi)} is measured in this file) and explain what drives it in "
             "the cost section." if (not derived and cpi is not None) else "Keep cost out of the headline: AC = EV in this file."),
            "Run the Schedule Health Review before the report goes out, so the logic grades back the date."
            if not has_audit else "Keep the logic clean so the margin is a genuine logic result.",
            "Load the previous update and run Update vs Update to state the trend."]
    evidence = [K.ev('Data date', dd_s),
                K.ev(fname_id if fid else 'Finish', ((f"{bf} → " if bf else '') + f"{ff} · {_sg(d)} wd"
                                                    + (f" · float {_sg(ftf)}" if ftf is not None else '')) if ff else None),
                K.ev('SPI / progress', f"{K.ratio(spi)} · {K.pct(ap)} vs {K.pct(pp)}"),
                K.ev('PV / EV / gap', f"{_m(pv)} / {_m(ev_)} / {_m((ev_ or 0) - (pv or 0))}" if (pv and ev_) else None),
                K.ev('CPI', f"{K.ratio(cpi)} (AC = EV, not a cost signal)" if derived else K.ratio(cpi)),
                K.ev(f"{vg_top['code']} share of gap" if vg_top else 'Value gap by code',
                     f"{_m(vg_top['gap'])} ({round(vg_top.get('pct_of_gap') or 0, 2)}%)" if vg_top else None),
                K.ev(drv['name'] if drv else 'Driver',
                     f"{drv['actual']}% vs {drv['planned']}% · {round((drv.get('weight') or 0) * 100)}% weight" if drv else None),
                K.ev('Chain head', f"{chain[0]['id']} {_nm(chain[0])} · {chain[0].get('pct')}% · float {_sg(chain[0]['tf'])}"
                     if chain else None),
                K.ev('Most negative float', ' · '.join(f"{x['id']} {_sg(x['tf'])}" for x in dneg)
                     + (' (both 0%)' if len(dneg) == 2 and all(x.get('pct') == 0 for x in dneg) else '') if dneg else None),
                K.ev('Client inputs open on negative float',
                     f"{len(late_open_neg)} of {len(open_inputs)} · {_brief(late_open_neg[0])} {_sg(late_open_neg[0]['slip_wd'])} wd, "
                     f"float {_sg(late_open_neg[0]['tf'])}" if late_open_neg else None),
                K.ev('Negative float', f"{nf:,} ({K.pct(nfp, 1)}) · {F.get('neg_float_grade')}" if nf is not None else None),
                K.ev('CPLI', f"{K.ratio(cpli)} vs {K.ratio(target) if target else '0.95'}"
                     + (f" · {crit:,} critical ({K.pct(critp, 1)})" if crit is not None else '') if cpli is not None else None),
                K.ev('Logic', (f"OOS {F['oos_count']} ({K.pct(F.get('oos_pct'), 1)}"
                               + (f", {F['critical_oos']} critical" if F.get('critical_oos') else '') + ")"
                               + (f" · dangling {F['dangling_count']}" if F.get('dangling_count') is not None else '')
                               + (f" · open ends {F['open_ends']}" if F.get('open_ends') is not None else ''))
                     if F.get('oos_count') is not None else None),
                K.ev('Lags', f"{lag['lagged_count']:,} ({lag.get('lagged_pct')}%) · {lag.get('need_justification_count') or 0} "
                     f"over {lag.get('long_threshold_days') or 14} wd" if lag.get('lagged_count') is not None else None),
                K.ev(_nm(good_ms[0]), f"{good_ms[0]['finish']} · {_sg(good_ms[0]['slip_wd'])} wd · float {_sg(good_ms[0]['tf'])}")
                if good_ms else None]
    drills = [K.drill('q05', f"How do I recover the ~{d} days" + (f" on the {t1_name} chain?" if t1 else '?'))
              if behind else K.drill('q04', 'What drives the date, and how much float is left?'),
              K.drill('q13', 'Do the late client inputs give me an EOT case?') if late_open_neg else None,
              K.drill('q02', 'Which sectional milestones are slipping, and by how much?'),
              K.drill('q04', 'What drives the date, and how negative is the float?') if behind else None,
              K.drill('q08', f"Why is CPI {K.ratio(cpi)} not a cost signal here?" if derived else
                      'Where do we stand on money, and where will it land?'),
              K.drill('q06', 'Is the schedule healthy enough to send to the consultant?')]
    fc_txt = f" forecast {ff}" if ff else ''
    if behind:
        head = (f"Lead every report with the date: {fname}{fc_txt}" + (f" against {bf}" if bf else '')
                + f", about {d} wd ({wk} weeks) late. Then say where the delay sits: "
                + (f"the {t1_name} chain" if t1 else (drv['name'] if drv else 'the driving work'))
                + (f", plus {_word(len(late_open_neg))} client input{'s' if len(late_open_neg) > 1 else ''} still open "
                   "on negative float" if late_open_neg else '') + '.'
                + (" Keep CPI out of it." if derived else f" {K.cost_note(F)}"))
    elif ahead:
        head = (f"Lead every report with the date: {fname}{fc_txt}" + (f" against {bf}" if bf else '')
                + f", about {abs(d)} wd ahead (SPI {K.ratio(spi)}). The message is how the margin is protected. "
                + K.cost_note(F))
    else:
        head = f"Lead every report with the date: {fname} is on its planned finish (SPI {K.ratio(spi)}). " + K.cost_note(F)
    thinking.insert(0, "Checked the finish milestone, SPI and the weighted driver"
                    + (f" ({drv['name']})" if drv else '') + " to set the headline message")
    if nok:
        thinking.insert(1, f"Traced the {N.get('chain_count', len(chain))}-activity chain that sets the finish and "
                           f"the {len(secs)} open sectional milestones")
    a = K.A2(head, [s_head, s_board, s_narr, s_curve, s_board2, s_charts, s_gap, s_style, s_week, s_inputs, s_risk,
                    s_good, s_rag, s_port],
             pills=pills, measured=measured, actions=actions, evidence=evidence, drilldowns=drills,
             tools=[K.tool('dashboard', 'Build the dashboard'), K.tool('report', "Manager's briefing")])
    a['thinking'] = thinking[:4]
    return a
