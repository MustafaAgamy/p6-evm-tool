"""q11 — Subcontractors, interfaces & handover: who's behind, and is commissioning covered?

Covers: ranking the scope packages (weighted) and — where the file allows — the trades/subcontractors by
value gap and key-date slip, interface handoffs tied into logic on both sides, the employer-side handoffs
(late client inputs), trade-stacking (an honest gap, plus what the finish chain shows), whether commissioning
and testing exist, track and sit on the critical path, the close-out spine for the job, the commissioning-tail
compression check and whether close-out is present AND linked — for ANY project, from F and N only.

Trades are read from the WBS of the finish chain and the file's own activity-code value split; nothing is
tied to a particular project's names.
"""
import re
from datetime import datetime, timedelta

from . import _kit2 as K

_ROMAN = {'i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'}
_GENERIC = {'phase', 'stage', 'package', 'design', 'engineering', 'engineer', 'procurement', 'and', 'of', 'the',
            'for', 'to', 'from', 'work', 'all', 'general', 'detailed', 'schematic', 'construction', 'completion'}
_TRADE_WORDS = {'civil', 'mechanical', 'electrical', 'steel', 'cable', 'piping', 'pipe', 'finishing', 'finish',
                'structure', 'structural', 'mep', 'hvac', 'plumbing', 'concrete', 'earthwork', 'road', 'paving',
                'equipment', 'instrumentation', 'insulation', 'painting', 'facade', 'roofing', 'landscaping', 'utility',
                'foundation', 'pile', 'piling', 'architectural', 'lighting', 'glazing', 'masonry', 'drainage',
                'cladding', 'marine', 'commissioning', 'testing', 'fitout'}
_ABBR = {'eqp': 'equipment', 'equip': 'equipment', 'mech': 'mechanical', 'elec': 'electrical', 'cvl': 'civil',
         'civ': 'civil', 'ss': 'steel', 'stl': 'steel', 'ce': 'cable', 'arch': 'architectural', 'str': 'structure',
         'plb': 'plumbing'}
_TRADE_NODE = re.compile(r'civil|mechanic|electric|steel|cable|piping|\bpipe|install|erection|finish|architect|structur'
                         r'|\bmep\b|hvac|plumb|concrete|earth|\broad|paving|equipment|instrument|insulation|painting'
                         r'|facade|roof|landscap|utilit|foundation|\bpil(e|ing)|works?$', re.I)
_DESIGN_INPUT = re.compile(r'design|drawing|layout|\bifc\b|detail', re.I)
_ITEM_NAME = re.compile(r'\bdeliver(?:y|ies|ed)?\s+(?:for|of)\b|shipment|free[- ]issue|furnished|supply of', re.I)
_INFO_NAME = re.compile(r'approv|design|drawing|layout|\bloads?\b|information|\bdata\b|review|comment|\blevel\b'
                        r'|survey|permit|offer', re.I)
_ITEM_WBS = re.compile(r'deliver|shipment|material|equipment|steel|free[- ]issue|furnished', re.I)
_CLIENT_WBS = re.compile(r'client|employer|owner|inputs required|free[- ]issue', re.I)
# close-out spine (searched on activity names + WBS)
_STAGES = [
    ('Construction tests', 'after each structural / installation stage', re.compile(r'\btests?\b|testing|load test', re.I)),
    ('Final connections / terminations', 'after installation, before testing',
     re.compile(r'terminat|hook[- ]?up|tie[- ]in|final connection', re.I)),
    ('Pre-commissioning (no-load runs, loop checks)', 'FS from the final connections',
     re.compile(r'pre[- ]?comm|no[- ]load|loop check|energi[sz]|cold commission|flushing|dry run', re.I)),
    ('Commissioning / trials', 'FS from pre-commissioning',
     re.compile(r'(?<!pre-)(?<!pre)commission|\bt\s?&\s?c\b|trial run|start[- ]?up|performance test|reliability run'
                r'|site acceptance|\bsat\b', re.I)),
    ('Punch list / snagging', 'before Taking-Over', re.compile(r'punch|snag', re.I)),
    ('Taking-Over / handover', 'the finish milestone',
     re.compile(r'hand ?over|handed over|taking[- ]over|take[- ]over|practical completion|substantial completion'
                r'|provisional acceptance', re.I)),
    ('As-builts', 'alongside close-out', re.compile(r'as[- ]?built', re.I)),
    ('O&M manuals / final documentation', 'alongside close-out',
     re.compile(r'o\s?&\s?m\b|operation (?:and|&) maintenance|manuals?\b|final documentation|handover documentation', re.I)),
    ('Demobilisation / retention release', 'after Taking-Over',
     re.compile(r'demobili[sz]|retention|final account|final acceptance|defects? (?:liability|notification)', re.I)),
]
_WORDS = {1: 'One', 2: 'Two', 3: 'Three', 4: 'Four', 5: 'Five', 6: 'Six', 7: 'Seven', 8: 'Eight', 9: 'Nine',
          10: 'Ten', 11: 'Eleven', 12: 'Twelve'}


# ── small helpers ──────────────────────────────────────────────────────────────
def _clean(s):
    return ' '.join(str(s or '').split())


def _short(s, n=46):
    s = _clean(s)
    if len(s) <= n:
        return s
    return s[:n].rsplit(' ', 1)[0].rstrip(' ,;:-&') + '…'


def _num(n, cap=False):
    w = _WORDS.get(n)
    return (w if cap else w.lower()) if w else str(n)


def _join(items):
    items = [i for i in items if i]
    if len(items) <= 1:
        return ''.join(items)
    return ', '.join(items[:-1]) + ' and ' + items[-1]


def _sg(n):
    if n is None:
        return '—'
    n = int(round(n))
    return f"+{n}" if n > 0 else (f"-{abs(n)}" if n < 0 else '0')


def _date(s):
    try:
        return datetime.strptime(s, '%d-%b-%Y')
    except (TypeError, ValueError):
        return None


def _toks(s):
    out = set()
    for t in re.findall(r'[a-z0-9]+', str(s or '').lower()):
        out.add(t[:-1] if len(t) > 3 and t.endswith('s') else t)
    return out


def _distinct(name):
    return {t for t in _toks(name) if t not in _GENERIC and t not in _ROMAN and len(t) > 1 and not t.isdigit()}


def _trade_toks(text, ident=''):
    t = _toks(text)
    for k in re.findall(r'[a-z0-9]+', str(ident or '').lower()):
        t.add(_ABBR.get(k, k))
    return t & _TRADE_WORDS


def _input_kind(x):
    n, w = _clean(x.get('name')), x.get('wbs') or ''
    if _ITEM_NAME.search(n):
        return 'item'
    if _INFO_NAME.search(n):
        return 'info'
    if _ITEM_WBS.search(w):
        return 'item'
    return 'access'


def _trade(x):
    """The trade a row belongs to: the deepest WBS node below level 1 that names a trade."""
    parts = [p for p in (x.get('wbs') or '').split(' / ') if p]
    c = [p for p in parts[1:] if _TRADE_NODE.search(p)]
    return c[-1] if c else (parts[1] if len(parts) > 1 else (parts[0] if parts else '(no WBS)'))


def _area(x):
    parts = [p for p in (x.get('wbs') or '').split(' / ') if p]
    t = _trade(x)
    return ' / '.join(p for p in parts[1:] if p != t and not _TRADE_NODE.search(p))


def _simplify(labels):
    """Drop the words every label shares ('Silos … Works') so trades read as 'Civil', 'Cable Erection'."""
    if len(labels) < 2:
        return {l: l for l in labels}
    common = set.intersection(*[set(w.lower() for w in l.split()) for l in labels])
    out = {}
    for l in labels:
        s = ' '.join(w for w in l.split() if w.lower() not in common)
        out[l] = s or l
    return out


def _leaf_areas(areas):
    """Keep the most specific areas: drop 'Zone A' when 'Zone A / Block 2' is also listed."""
    return [a for a in areas if not any(b != a and b.startswith(a + ' / ') for b in areas)]


_DESIG = re.compile(r'\b(phase|stage|area|zone|section|block|building|level|sector)\s+([a-z0-9]+)\b', re.I)


def _designators(s):
    return {f"{m.group(1).lower()} {m.group(2).lower()}" for m in _DESIG.finditer(str(s or ''))}


def _poss(name):
    return name + ("'" if name.endswith('s') else "'s")


def _pl(n, word, plural=None):
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def _lc(s):
    """Lower-case for running text, but keep acronyms (MEP, HVAC)."""
    return ' '.join(w if (w.isupper() and len(w) > 1) else w.lower() for w in str(s).split())


_NOT_TRADE = re.compile(r'hand ?over|close[- ]?out|punch|snag|taking[- ]over|milestone|key date|commission|testing', re.I)


_MISS = {'Construction tests': 'construction tests', 'Final connections / terminations': 'final connections',
         'Pre-commissioning (no-load runs, loop checks)': 'pre-commissioning', 'Commissioning / trials': 'commissioning',
         'Punch list / snagging': 'punch list', 'Taking-Over / handover': 'a Taking-Over milestone',
         'As-builts': 'as-builts', 'O&M manuals / final documentation': 'O&M manuals',
         'Demobilisation / retention release': 'demobilisation'}


def _wgap(x):
    return (x.get('weight') or 0) * (x.get('gap') or 0)


def _fmt_w(v):
    if v >= 1:
        return f"~{round(v)}"
    if v >= 0.1:
        return f"~{v:.1f}"
    if v > 0:
        return '<0.1'
    if v == 0:
        return '0'
    return f"{v:.1f}"


def build(F, N, role):
    nok = bool(N and N.get('ok'))
    d = F.get('delay_days')
    behind, ahead = (d or 0) > 0, (d or 0) < 0
    spi = F.get('spi')
    drv = K.main_driver(F)
    dd = F.get('data_date') or ((N or {}).get('data_date') if nok else None)
    ddt = _date(dd)
    has_audit = bool(F.get('has_audit'))
    audit = F.get('audit') or {}
    fin = (N.get('finish_milestone') or {}) if nok else {}
    ftf = N.get('finish_tf') if nok else None
    thinking = []

    ds = sorted(F.get('disciplines') or [], key=lambda x: -_wgap(x))
    acts = ((N.get('kb_view') or {}).get('activities') or []) if nok else []
    n_acts = (N.get('activity_count') if nok else None) or F.get('activity_count')
    client = list(N.get('client_inputs') or []) if nok else []
    client_ids = {x['id'] for x in client}
    open_client = [x for x in client if not x.get('done')]
    late_open = list(N.get('client_inputs_late_open') or []) if nok else []
    chain = list(N.get('chain') or []) if nok else []
    chain_ids = {x['id'] for x in chain}
    milestones = list(N.get('milestones') or []) if nok else []
    deepest = list(N.get('deepest') or []) if nok else []
    idrows = {}
    for r in chain + deepest + milestones:
        idrows.setdefault(_clean(r['name']).lower(), r)

    # ── the finish chain, read as trades in date order ──────────────────────────
    tasks = [x for x in chain if 'Milestone' not in (x.get('type') or '')]
    order, by_trade = [], {}
    for x in tasks:
        t = _trade(x)
        if t not in by_trade:
            order.append(t)
            by_trade[t] = []
        by_trade[t].append(x)
    simple = _simplify(order)
    lead = order[0] if order else None
    lead_areas = []
    for x in by_trade.get(lead, []):
        a = _area(x)
        if a and a not in lead_areas:
            lead_areas.append(a)
    lead_areas = _leaf_areas(lead_areas)
    lead_lbl = (f"{lead} front" + (f" ({', '.join(lead_areas[:3])})" if lead_areas else '')) if lead else None
    after = [t for t in order[1:] if not _NOT_TRADE.search(t)]
    after_zero = [t for t in after if all(not r.get('pct') for r in by_trade[t])]
    last = max(tasks, key=lambda x: (_date(x.get('finish')) or datetime.min)) if tasks else None
    fdt, ldt = _date(fin.get('finish')), _date((last or {}).get('finish'))
    tail_now = (fdt - ldt).days if (fdt and ldt) else None
    fbl, lbl_ = _date(fin.get('baseline_finish')), _date((last or {}).get('baseline_finish'))
    tail_base = (fbl - lbl_).days if (fbl and lbl_) else None

    # ── close-out spine: search every activity name/WBS in the file ─────────────
    def is_client_row(a):
        return bool(_CLIENT_WBS.search((a.get('wbs_path') or a.get('wbs') or '').split(' / ')[0]))

    spine = {}
    for label, links, rx in _STAGES:
        hits = [a for a in acts if not is_client_row(a) and rx.search((a.get('name') or '') + ' ' + (a.get('wbs_path') or ''))]
        spine[label] = hits
    # construction tests are the structural / installation tests — not the commissioning activities themselves
    _comm_rx = (_STAGES[2][2], _STAGES[3][2])
    spine['Construction tests'] = [a for a in spine['Construction tests']
                                   if not any(r.search(a.get('name') or '') for r in _comm_rx)]
    searched = (f"all {len(acts):,} activity names" if not n_acts or len(acts) >= n_acts else
                f"the first {len(acts):,} of {n_acts:,} activity names")
    comm_hits = spine['Pre-commissioning (no-load runs, loop checks)'] + spine['Commissioning / trials']
    comm_disc = [x for x in ds if re.search(r'commission|testing|\bt\s?&\s?c\b', x.get('name') or '', re.I)]
    comm_on_chain = [x for x in chain if re.search(r'commission|pre[- ]?comm|no[- ]load|trial run', x.get('name') or '', re.I)]
    handover_is_fin = bool(fin.get('name') and _STAGES[5][2].search(fin['name']))

    def examples(hits, k=4):
        """Up to k distinct activity names, the ones I can cite with an id first."""
        out, seen = [], set()
        ranked = sorted(hits, key=lambda a: 0 if _clean(a.get('name')).lower() in idrows else 1)
        for a in ranked:
            nm = _clean(a.get('name'))
            if nm.lower() in seen:
                continue
            seen.add(nm.lower())
            r = idrows.get(nm.lower())
            out.append(f"{nm} ({r['id']})" if r else nm)
            if len(out) >= k:
                break
        return out

    # ── value split by activity code (the trade proxy) ──────────────────────────
    vg = F.get('value_gap') if isinstance(F.get('value_gap'), dict) else None
    groups = [g for g in ((vg or {}).get('groups') or []) if isinstance(g, dict)]
    dim = (vg or {}).get('dimension') or 'activity code'
    sub_dim = bool(vg and re.search(r'sub-?contract|contractor|company|vendor|supplier', dim, re.I))
    key_ms = [m for m in milestones if not m.get('done') and m['id'] not in client_ids and m['id'] != fin.get('id')
              and not re.search(r'as[- ]?built', m['name'], re.I)]

    def worst_key(tt):
        c = [m for m in key_ms if tt & _trade_toks(m['name'], m['id']) and m.get('slip_wd') is not None]
        return max(c, key=lambda m: (m['slip_wd'], -(m.get('tf') or 0))) if c else None

    def chain_trade(tt, name=''):
        """The finish-chain trade a code / key date belongs to. A key date that names an area ('Phase B …') only
        belongs if the chain's work for that trade is in the same area."""
        des = _designators(name)
        for t in order:
            if not (tt & _trade_toks(t)):
                continue
            if des:
                areas = ' | '.join(_area(x) + ' ' + (x.get('wbs') or '') for x in by_trade[t])
                if not (des & _designators(areas)):
                    continue
            return t
        return None

    # ═══ 1. ranking the scope packages ═══════════════════════════════════════════
    total_gap = max(0, (F.get('planned_pct') or 0) - (F.get('actual_pct') or 0))
    p1 = []
    top_g = groups[0] if groups and (groups[0].get('gap') or 0) > 0 else None
    if drv and _wgap(drv) >= 1 and not ahead:
        t = (f"**{drv['name']} is the package behind — {drv['actual']}% done against {drv['planned']}% planned, on "
             f"{round((drv.get('weight') or 0) * 100)}% of the job's weight")
        if top_g:
            t += f" — and inside it the {top_g['code']} trade carries {round(top_g.get('pct_of_gap') or 0, 2)}% of the value gap"
        t += '.'
        if lead and chain and (chain[0].get('wbs') or '').split(' / ')[0].strip().lower() == drv['name'].strip().lower():
            t += f" The finish chain runs through its {lead_lbl}."
        p1.append(t + '**')
        others = [x for x in ds if x is not drv and (x.get('gap') or 0) > 0]
        pos_w = sum(_wgap(x) for x in ds if (x.get('gap') or 0) > 0)
        t = (f"I rank by the weighted categories in your file, because weight decides whether a gap can move the finish. "
             f"Weighted, {_poss(drv['name'])} {drv['gap']}-point gap is worth about {round(_wgap(drv))} of the roughly "
             + (f"{total_gap} points the whole job is behind ({F.get('planned_pct')}% planned vs {F.get('actual_pct')}% done)."
                if total_gap >= _wgap(drv) else f"{pos_w:.1f} points of weighted shortfall across the categories."))
        wide = [x for x in others if (x.get('gap') or 0) > (drv.get('gap') or 0)]
        if wide:
            ow = sum(_wgap(x) for x in others)
            one = len(wide) == 1
            t += (f" {_join([x['name'] for x in wide[:3]])} show{'s a' if one else ''} bigger raw gap{'' if one else 's'} but "
                  f"carr{'ies' if one else 'y'} about {round(max(x.get('weight') or 0 for x in wide) * 100)}% weight"
                  f"{'' if one else ' each'}, so together the smaller lines are worth about {ow:.1f} points — don't let the "
                  f"{max(x['gap'] for x in wide)}-point figure pull attention off the package that is actually late.")
        p1.append(t)
    elif drv and not ahead and behind:
        p1.append(f"**{drv['name']} carries the most weighted gap — {drv['actual']}% against {drv['planned']}% planned on "
                  f"{round((drv.get('weight') or 0) * 100)}% of the weight — but that's under a point of the job's progress, "
                  "so no single package explains the slip on the weighted read.**")
    else:
        lag = [x for x in ds if (x.get('gap') or 0) > 0]
        p1.append("**No package is materially behind"
                  + (f": {_join([x['name'] for x in lag[:3]])} {'is' if len(lag) == 1 else 'are'} the only "
                     f"line{'s' if len(lag) > 1 else ''} under plan, worth about {sum(_wgap(x) for x in lag):.1f} of a point "
                     "on the weighted read." if lag else " — every weighted category is at or ahead of plan.") + '**')
        p1.append("I rank by the weighted categories in your file, because weight decides whether a gap can move the finish.")
    # the small line that still deserves a phone call
    small = sorted([x for x in ds if x is not drv and (x.get('gap') or 0) > 0], key=lambda x: -(x.get('gap') or 0))
    for x in small[:3]:
        dt = _distinct(x['name'])
        cand = [c for c in open_client if dt and dt & _toks(c['name']) and (c.get('slip_wd') or 0) > 0]
        design_line = bool(re.search(r'design|engineer|drawing', x['name'], re.I))
        if design_line:
            cand = [c for c in cand if _input_kind(c) == 'info' and _DESIGN_INPUT.search(c['name'])]
        if cand:
            c = max(cand, key=lambda c: c.get('slip_wd') or 0)
            who = 'designer' if design_line else 'package'
            p1.append(f"One of the small lines still deserves a phone call. {x['name']} is {x['actual']}% against "
                      f"{x['planned']}% planned, and the client input its name says it waits on — '{_clean(c['name'])}' "
                      f"({c['id']}) — is {_sg(c.get('slip_wd'))} wd behind its baseline date with {_sg(c.get('tf'))} wd float. "
                      f"On the face of it that gap sits with the client's input, not the {who}; confirm it before anyone "
                      f"chases the {'design team' if design_line else 'package'}.")
            break
    s_rank = K.sec('Ranking the scope packages by how far behind', *p1,
                   table=K.tbl(['Scope package', 'Weight', 'Done / plan', 'Gap (pts)', 'Weighted gap (pts)'],
                               [[x['name'], f"{round((x.get('weight') or 0) * 100)}%", f"{x.get('actual')}% / {x.get('planned')}%",
                                 x.get('gap'), _fmt_w(_wgap(x))] for x in ds],
                               "The weighted category breakdown in your file. Weighted gap = weight × gap"
                               + (f"; {drv['name']} is {_fmt_w(_wgap(drv))} of the ~{total_gap} points behind."
                                  if drv and total_gap else '.')))
    thinking.append(f"Weighed the {len(ds)} categories by weight × gap to rank the packages")

    # ═══ 2. subcontractor-level ranking ══════════════════════════════════════════
    p2, t2 = [], None
    if sub_dim:
        p2.append(f"Your file carries a '{dim}' code, so this is a real ranking by who owns the work — worst first by "
                  "value gap, with each one's worst key date beside it.")
    elif vg:
        p2.append(f"Straight answer: I can't rank subcontractors from this file — the value split I hold is by its '{dim}' "
                  f"code, not a subcontractor or company code. Its values ({_join([g['code'] for g in groups[:6]])}) usually "
                  "map to specialist packages, so it's the closest honest proxy. I rank it two ways below, because the "
                  "two measures tell different stories.")
    else:
        p2.append("Straight answer: I can't rank subcontractors from what I hold — there's no subcontractor split stored for "
                  "this update, and no value split by activity code either (re-import the file to store one).")
    if vg and groups:
        rows = []
        slips = []
        for g in groups[:8]:
            tt = _trade_toks(g['code'])
            m = worst_key(tt)
            if m:
                slips.append(m['slip_wd'])
            ct = chain_trade(tt, m['name'] if m else '')
            if g is top_g:
                rd = "The trade that is actually behind" + (f" — its {simple.get(ct, ct)} front heads the finish chain"
                                                           if ct and ct == lead else '')
            elif ct and ct in after_zero:
                rd = f"Inherits the chain — 0% started on it, behind the {simple.get(lead, lead)} front"
            elif not (g.get('pv') or 0):
                rd = "No value planned to date — read it by its key date"
            elif m and (m.get('tf') or 0) < 0:
                rd = f"Late on its key date, on {_sg(m.get('tf'))} wd float"
            else:
                rd = "On or near its key date"
            share = (f"{round(g.get('pct_of_gap') or 0, 2)}%" if (g.get('pv') or 0) else "0% (no value planned to date)")
            rows.append([g['code'], share,
                         f"{m['name']} ({m['id']}) · {_sg(m.get('slip_wd'))} wd · {_sg(m.get('tf'))}" if m else '—', rd])
        t2 = K.tbl([f"Trade ('{dim}' code)", 'Share of PV–EV gap', 'Worst key date · slip · float', 'Reading'], rows,
                   f"Value gap grouped by the file's '{dim}' code; key dates are the open milestones named for each trade "
                   "(baseline vs current finish, in working days)."
                   + ('' if sub_dim else " A trade proxy, not a subcontractor ranking."))
        if nok and slips and top_g:
            t = (f"By value gap (planned minus earned value), {top_g['code']} is {round(top_g.get('pct_of_gap') or 0, 2)}% of "
                 f"the story. By key-date slip, the trades look {min(slips)}–{max(slips)} wd late.")
            if after_zero and lead:
                t += (f" The finish chain reconciles the two: the {_join([simple.get(x, x) for x in after_zero])} work on the "
                      f"chain is 0% started and sits behind the {simple.get(lead, lead)} front. Their slip is inherited from "
                      "the work ahead of them — they haven't started, so it can't be their output yet.")
            h = chain[0] if chain else None
            if h and ddt and _date(h.get('baseline_finish')) and _date(h['baseline_finish']) <= ddt and not h.get('pct'):
                t += (f" The front of that chain is {_clean(h['name'])} ({h['id']}): due to finish {h['baseline_finish']}, "
                      f"before the data date, and still 0%.")
            p2.append(t)
        zero = [g['code'] for g in groups if not (g.get('pv') or 0)]
        if zero:
            p2.append(f"{_join(zero)} carr{'y' if len(zero) > 1 else 'ies'} no planned value to date in the file (PV 0, EV 0), "
                      "so a value ranking can't see "
                      f"{'them' if len(zero) > 1 else 'it'} at all — that's why the key-date column matters.")
        thinking.append(f"Ranked the {len(groups)} '{dim}' values by value gap and matched each to its worst key date")
    elif nok and key_ms:
        late_k = sorted([m for m in key_ms if (m.get('slip_wd') or 0) > 0 and 'Finish' in (m.get('type') or 'Finish')],
                        key=lambda m: (m['tf'] if m.get('tf') is not None else 10 ** 6))[:10]
        if late_k:
            p2.append("What I can rank is the key-date milestone each package works to — below, most negative float first. "
                      "A trade whose key date sits on the finish chain but hasn't started is inheriting its slip, not "
                      "causing it.")
            rows = []
            for m in late_k:
                neg = (m.get('tf') or 0) < 0
                ct = chain_trade(_trade_toks(m['name'], m['id']), m['name']) if neg else None
                rd = ("Heads the finish chain — the front that is actually behind" if ct and ct == lead else
                      "Inherits the chain — 0% started behind the " + simple.get(lead, lead or '') + " front"
                      if ct and ct in after_zero else
                      "Late, on negative float off the finish chain" if neg else "Late but still has float")
                rows.append([f"{m['name']} ({m['id']})", f"{m.get('baseline_finish')} → {m.get('finish')}",
                             f"{_sg(m.get('slip_wd'))} wd · float {_sg(m.get('tf'))}", rd])
            t2 = K.tbl(['Key date', 'Baseline → forecast', 'Slip · float', 'Reading'], rows,
                       'Open key-date milestones from the file (client inputs and the finish milestone excluded).')
            thinking.append(f"Read {len(late_k)} late key-date milestones as the package proxy (no subcontractor split stored)")
    p2.append("To get a true subcontractor ranking, add a 'Subcontractor' activity code in P6, assign it and re-import; the "
              "tool then ranks each one worst-first by weighted gap." if not sub_dim else
              "Chase the top of this list this week; the ones inheriting chain slip need their fronts released, not pressure.")
    s_sub = K.sec('Subcontractor-level ranking (needs subcontractor coding)', *p2, table=t2)

    # ═══ 3. interface handoffs ═══════════════════════════════════════════════════
    p3 = []
    dk = ((audit.get('dangling') or {}).get('kpis') or {}) if has_audit else {}
    oe = F.get('open_ends') if has_audit else None
    if dk.get('total_dangling') is not None:
        good = (oe or 0) == 0 and (dk.get('dangling_pct') or 0) <= 5
        t = (f"A handoff is only safe when it's tied on both sides — the giving party's finish drives it and the receiving "
             f"work hangs off it. On this network that's in {'good' if good else 'poor'} shape: "
             f"{oe if oe is not None else 'an unknown number of'} open ends, and {'only ' if good else ''}"
             f"{dk['total_dangling']} dangling activities ({K.pct(dk.get('dangling_pct'), 1)})")
        parts = []
        if dk.get('start_dangling') is not None:
            parts.append(f"{dk['start_dangling']} with a start nothing drives")
        if dk.get('finish_dangling') is not None:
            parts.append(f"{dk['finish_dangling']} with a finish that drives nothing")
        if dk.get('both_dangling') is not None:
            parts.append(f"{dk['both_dangling']} loose at both ends")
        t += (' — ' + _join(parts) if parts else '') + '.'
        if dk.get('both_dangling'):
            t += (f" Open the {dk['both_dangling']} first: an activity whose start isn't driven and whose finish drives "
                  "nothing can slip without the schedule noticing, so if any of them is a handoff, it's invisible.")
        t += (f" The summary I hold doesn't name the {dk['total_dangling']} — Dangling Resolve & Correct lists each one and "
              "fixes the missing side in place.") if dk.get('total_dangling') else ''
        p3.append(t)
    else:
        p3.append("A handoff is only safe when it's tied on both sides — the giving party's finish drives it and the "
                  "receiving work hangs off it. The logic checks (open ends, dangling activities) aren't stored with this "
                  "update, so I can't count the loose ones; run the Schedule Audit and Dangling Resolve & Correct will "
                  "list each one and fix the missing side.")
    if nok and client:
        br = {}
        for c in client:
            k = (c.get('wbs') or '').split(' / ')[0] or '(no WBS)'
            br[k] = br.get(k, 0) + 1
        branch = max(br.items(), key=lambda kv: kv[1])[0]
        neg_open = [c for c in open_client if c.get('tf') is not None and c['tf'] < 0]
        t = (f"The handoffs that matter most are the employer's: the file has {len(client)} client/employer "
             f"input{'s' if len(client) != 1 else ''}" + (f", most of them under '{branch}'" if br[branch] < len(client)
                                                         else f", all under '{branch}'")
             + f" — {len(open_client)} still open.")
        if neg_open:
            t += (f" Those are tied in on the receiving side — {len(neg_open)} of the {len(open_client)} open ones "
                  f"carr{'ies' if len(neg_open) == 1 else 'y'} negative float, which a milestone only picks up from the work "
                  "hanging off it — so when they're late, the schedule shows it. That's what you want. They're listed in "
                  "the next section.")
        p3.append(t)
    if len(order) >= 2:
        p3.append("Handoffs between trades on the finish chain are its own links — "
                  + ' → '.join(simple.get(t, t) for t in order[:6])
                  + " — so those are tied in by definition; the risk there is timing, not missing logic.")
    s_int = K.sec('Interface handoffs tied into logic on both sides', *p3)

    # ═══ 4. late client inputs ═══════════════════════════════════════════════════
    p4, t4 = [], None
    pinned = [c for c in open_client if c.get('tf') == 0 and (c.get('slip_wd') or 0) == 0]
    if nok and client:
        late_neg = [c for c in late_open if c.get('tf') is not None and c['tf'] < 0]
        rolled = [c for c in late_open if c.get('finish') == dd and not c.get('pct')]
        if late_open:
            if late_neg and len(late_neg) == len(late_open):
                t = (f"{_num(len(late_neg), True)} of the {len(open_client)} open client inputs "
                     f"{'are' if len(late_neg) != 1 else 'is'} late and "
                     f"{'sit on negative-float paths' if len(late_neg) != 1 else 'sits on a negative-float path'} — the "
                     "strongest extension-of-time indicators in this file.")
            elif late_neg:
                subj = ((f"Both open client inputs are" if len(open_client) == 2 else
                         f"All {len(open_client)} open client inputs are") if len(late_open) == len(open_client) else
                        f"{_num(len(late_open), True)} of the {len(open_client)} open client inputs "
                        f"{'are' if len(late_open) != 1 else 'is'}")
                t = (f"{subj} late, and {len(late_neg)} of those "
                     f"{'sit on negative-float paths' if len(late_neg) != 1 else 'sits on a negative-float path'} — the "
                     f"strongest extension-of-time indicator{'s' if len(late_neg) != 1 else ''} in this file.")
            else:
                t = (f"{_num(len(late_open), True)} client input{'s are' if len(late_open) > 1 else ' is'} late but still on "
                     "zero or positive float — worth logging, not yet driving.")
            if rolled:
                t += (f" {_num(len(rolled), True)} of them show 0% with their forecast on the data date ({dd}), which in P6 "
                      "means they aren't actualised: either they're still outstanding — and their slip grows every week "
                      "they stay open — or the update hasn't recorded them. Confirm which, item by item, before anyone "
                      "quotes these numbers.")
            p4.append(t)
        else:
            p4.append("No client or employer input is late and still open in the file — the employer-side handoffs are "
                      "on their dates at this update.")
        if pinned:
            items = all(_input_kind(c) == 'item' for c in pinned)
            p4.append(f"The {_num(len(pinned))} client {'deliveries' if items else 'inputs'} still ahead "
                      f"({_join([_short(c['name'], 64) for c in pinned[:5]])}) show zero slip and exactly zero float on "
                      "their baseline dates. That pattern usually means a date constraint is holding them — and if so, "
                      "they will never show slip on their own; someone has to move them when the real date moves. Worth a "
                      "check with whoever tracks the client's supply.")
        if late_neg:
            p4.append("One caution, stated once: late employer inputs on negative-float paths are strong indicators for an "
                      "extension of time, not proof of it. Showing how many of the "
                      + (f"{round(d)} days" if behind else 'days') + " they caused"
                      + (f" — against the {simple.get(lead, lead)} front's own pace —" if lead else '')
                      + " needs a time-impact or windows analysis (Consultant Review, Update vs Update).")
        rows = [[f"{c['id']} {_clean(c['name'])}", f"{c.get('baseline_finish')} → {c.get('finish')}", _sg(c.get('slip_wd')),
                 _sg(c.get('tf'))] for c in sorted(late_open, key=lambda c: -(c.get('slip_wd') or 0))]
        if pinned:
            ids = [c['id'] for c in pinned]
            pre = ids[0].rsplit('.', 1)[0] + '.' if '.' in ids[0] else ''
            idtxt = (ids[0] + ' / ' + ' / '.join(i[len(pre):] if pre and i.startswith(pre) else i for i in ids[1:])) \
                if len(ids) > 1 else ids[0]
            dts = sorted({c['finish'] for c in pinned}, key=lambda s: _date(s) or datetime.max)
            rows.append([f"{idtxt} — {len(pinned)} still ahead", f"on baseline ({' / '.join(dts[:3])})", '0', '0'])
        t4 = K.tbl(['Client input', 'Baseline → forecast', 'Slip (wd)', 'Float (wd)'], rows,
                   f"The file's client/employer inputs. A 0% item forecast on {dd} is not actualised at the data date."
                   if (late_open and rolled) else "The file's client/employer inputs, baseline vs current finish.")
        thinking.append(f"Checked {len(client)} client/employer inputs: {len(late_open)} late and open, "
                        f"{sum(1 for c in late_open if (c.get('tf') or 0) < 0)} on negative float")
    elif nok:
        p4.append("The file has no activities marked as client, employer or owner inputs, so there are no employer-side "
                  "handoffs to track. If the contract has them (free-issue items, access, approvals), add them as "
                  "milestones tied into the work they release — they're your first line of EOT evidence.")
    else:
        p4.append("Listing the late client inputs needs the schedule file — it isn't in the stored numbers. Re-import it and "
                  "I'll show each one's slip and float against the finish.")
    s_cli = K.sec('Late client inputs — the employer-side handoffs', *p4, table=t4)

    # ═══ 5. trade-stacking ═══════════════════════════════════════════════════════
    p5 = ["I can't give you a congestion number, and I won't fake one: the tool has no spatial layer yet — no time-phased "
          "area-occupancy histogram showing which trades are in which area, week by week. That's a genuine feature gap, "
          "not a step I skipped."]
    win = []
    if nok and tasks:
        areas = []
        for x in tasks:
            a = _area(x)
            if a and a not in areas:
                areas.append(a)
        areas = _leaf_areas(areas)
        if areas:
            p5.append(f"Your WBS already splits the work by area — the finish chain alone runs through "
                      f"{_join(areas[:5])}{' and more' if len(areas) > 5 else ''} — which is exactly what a congestion "
                      "histogram would be built on.")
        end = fdt or ldt
        if end:
            win = [x for x in tasks if _date(x.get('finish')) and _date(x['finish']) >= end - timedelta(days=42)
                   and not re.search(r'hand ?over|close[- ]?out|punch|snag|taking[- ]over', _trade(x), re.I)]
        wt = [t for t in order if any(_trade(x) == t for x in win)]
        if len(wt) >= 2:
            desc = []
            for t in wt:
                fs = sorted(_date(x['finish']) for x in win if _trade(x) == t)
                desc.append(f"{simple.get(t, t)} ({fs[0].strftime('%d-%b')} → {fs[-1].strftime('%d-%b-%Y')})"
                            if fs[0] != fs[-1] else f"{simple.get(t, t)} ({fs[0].strftime('%d-%b-%Y')})")
            wa = []
            for x in win:
                a = _area(x)
                if a and a not in wa:
                    wa.append(a)
            wa = _leaf_areas(wa)
            t = (f"Even without the histogram, the finish chain shows where stacking will bite. "
                 f"{_num(len(wt), True)} trades finish inside the same six weeks"
                 + (f" in {_join(wa[:3])}" if wa else '') + ': ' + _join(desc) + '.')
            bls = [_date(x.get('baseline_finish')) for x in win if _date(x.get('baseline_finish'))]
            sl = [x['slip_wd'] for x in win if x.get('slip_wd') is not None]
            if bls and sl:
                if max(sl) - min(sl) <= 3:
                    t += (f" They were stacked the same way in the baseline ({min(bls).strftime('%d-%b-%Y')} → "
                          f"{max(bls).strftime('%d-%b-%Y')}); the slip moved the whole stack intact.")
                else:
                    t += (f" In the baseline the same work ran {min(bls).strftime('%d-%b-%Y')} → "
                          f"{max(bls).strftime('%d-%b-%Y')}; the slips differ by up to {max(sl) - min(sl)} wd, so the stack "
                          "has been reshaped, not just moved.")
            t += ((f" Any recovery that compresses the {simple.get(lead, lead)} front squeezes those {len(wt)} crews into the "
                   "same area even harder" if lead in wt else
                   f" Any recovery that pulls this back end forward squeezes those {len(wt)} crews together even harder")
                  + " — walk that area plan with site before you commit to one.")
            p5.append(t)
        elif len(wt) == 1:
            p5.append(f"On the finish chain only {simple.get(wt[0], wt[0])} works in the last six weeks, so the driving path "
                      "itself doesn't stack trades — check the parallel fronts with site.")
    elif not nok:
        p5.append("With the schedule file I can at least show which trades converge at the end of the finish chain; re-import "
                  "it to get that read.")
    s_stack = K.sec('Trade-stacking / spatial congestion — a known gap', *p5)

    # ═══ 6. is commissioning in and tracking? ════════════════════════════════════
    p6 = []
    equip_client = any(re.search(r'equipment', (c.get('name') or '') + ' ' + (c.get('wbs') or ''), re.I)
                       for c in client if _input_kind(c) == 'item')
    tests = spine['Construction tests']
    if not nok:
        p6.append(K.network_note(N))
        p6.append((f"From the stored numbers: {comm_disc[0]['name']} is {comm_disc[0]['actual']}% against "
                   f"{comm_disc[0]['planned']}% planned." if comm_disc else
                   "From the stored numbers: there's no commissioning or testing line in the weighted breakdown, so "
                   "nothing measures commissioning progress today.")
                  + " Whether commissioning activities exist in the network needs the file.")
    elif comm_hits or comm_disc:
        ex = examples(comm_hits)
        t = (f"**Commissioning is in the file: {len(comm_hits)} activit{'ies name' if len(comm_hits) != 1 else 'y names'} "
             f"it" + (f" ({_join(ex)})" if ex else '') + '.')
        if comm_disc:
            x = comm_disc[0]
            t += f" {x['name']} is tracking at {x['actual']}% against {x['planned']}% planned."
        t += '**'
        p6.append(t)
        p6.append(("Some of it sits on the finish chain (" + _join([f"{_clean(x['name'])} ({x['id']})" for x in comm_on_chain[:3]])
                   + "), so it's on the critical path now." if comm_on_chain else
                   "None of it sits on the finish chain today, so commissioning isn't yet driving the date — but it will "
                   "be the last thing before handover, so watch its float every update.")
                  + " Progress per activity is in Update Analysis.")
    else:
        t = "**No commissioning is visible before the finish"
        if last:
            same = (tail_now == 0)
            t += (f": the last activity on the finish chain ({_clean(last['name'])}, {last['id']}) finishes {last['finish']}"
                  + (f" — the same day as {fin.get('name')}" if same and fin.get('name') else
                     (f", {tail_now} days before {fin.get('name')}" if tail_now is not None and fin.get('name') else '')))
        t += (". Either commissioning is outside your contract"
              + (" (plausible, since the file shows the client furnishing equipment)" if equip_client else '')
              + " or it's missing from the network. Confirm which against the contract scope.**")
        p6.append(t)
        ex = [e for e in examples([a for a in tests if _clean(a.get('name')).lower() in idrows], 4)]
        if not ex:
            ex = examples(tests, 4)
        lvl2 = {' / '.join((a.get('wbs_path') or '').split(' / ')[:2]) for a in acts}
        tc_branch = [b for b in lvl2 if re.search(r'commission|testing|\bt\s?&\s?c\b', b, re.I)]
        if tests:
            p6.append(f"What the file does have is construction-stage testing, and it's real: {_join(ex)}"
                      + (f" — {len(tests)} test activities in all" if len(tests) > len(ex) else '')
                      + ". Those prove the structure; they don't prove the plant runs. "
                      + ("There's no testing or commissioning branch among the level-2 WBS branches" if not tc_branch else
                         f"The WBS has {_join(tc_branch[:2])}, but no activity in it is named for commissioning")
                      + " and no commissioning line in the weighted breakdown — so if commissioning is in your scope, "
                        "nothing is tracking it yet.")
        else:
            p6.append("There are no test activities named in the file either, and no commissioning line in the weighted "
                      "breakdown — so if commissioning is in your scope, nothing is tracking it yet.")
        p6.append(("If it is yours, adding it moves the finish: whatever duration it carries lands after "
                   f"{last['finish']}, because nothing sits between the last activity and the completion milestone today. "
                   if last and tail_now == 0 else
                   "If it is yours, adding it will move the finish by whatever it carries beyond the gap before the "
                   "completion milestone. ")
                  + f"I've searched {searched} in the file for commissioning, pre-commissioning, no-load, loop-check, "
                    "trial-run, energisation and start-up steps — none.")
    s_comm = K.sec('Is commissioning in and tracking?', *p6)

    # ═══ 7. is it on the critical path? ══════════════════════════════════════════
    p7 = []
    if nok and chain:
        seq = []
        for t in order[:6]:
            nm = []
            for x in by_trade[t]:
                n_ = _clean(x['name'])
                if n_ not in nm:
                    nm.append(n_)
            ar = [a for a in dict.fromkeys(_area(x) for x in by_trade[t]) if a]
            seq.append(f"{simple.get(t, t)}" + (f" on {_join(ar[:2])}" if ar else '') + f" ({', '.join(nm[:4])}"
                       + ('…' if len(nm) > 4 else '') + ')')
        ms_on = [x for x in chain if 'Milestone' in (x.get('type') or '')]
        seq += [f"{_clean(m['name'])} ({m['id']})" for m in ms_on[:2]]
        if fin.get('name'):
            seq.append(f"{fin['name']} ({fin.get('id')})")
        t = ("There's nothing to put on it yet. " if not comm_on_chain and not comm_hits else
             ("Yes. " if comm_on_chain else "Not yet. "))
        t += (f"The activities sharing the finish's negative float (about {_sg(ftf)} wd) run, in date order: " if (ftf or 0) < 0
              else "The activities that set the finish run, in date order: ") + ' → '.join(seq) + '.'
        beside = [m for m in key_ms if m['id'] not in chain_ids and m.get('tf') is not None and ftf is not None
                  and ftf < m['tf'] <= ftf + 10]
        if beside:
            b2 = beside[:2]
            vals = {m['tf'] for m in b2}
            t += ' ' + _join([f"{m['name']} ({m['id']})" for m in b2]) + \
                 (f" sits beside it at {_sg(b2[0]['tf'])}." if len(b2) == 1 else
                  f" sit beside it, both at {_sg(b2[0]['tf'])}." if len(vals) == 1 else
                  f" sit beside it at {_join([_sg(m['tf']) for m in b2])}.")
        if not comm_on_chain:
            t += " No test-and-commission step appears anywhere in that chain."
        p7.append(t)
    ck = ((audit.get('cpli') or {}).get('kpis') or {}) if has_audit else {}
    if not nok:
        p7.append("Tracing the chain that sets the finish needs the schedule file; "
                  + ("from the stored numbers I can only give the critical-path health below."
                     if (ck.get('cpli') is not None or (has_audit and F.get('cpli_critical_count') is not None)) else
                     "the critical-path audit isn't stored with this update either, so run the Schedule Health Review."))
    if ck.get('cpli') is not None or (has_audit and F.get('cpli_critical_count') is not None):
        t = ''
        if has_audit and F.get('cpli_critical_count') is not None:
            dg = re.sub(r'\s*density\s*', ' ', str(F.get('cpli_density_grade') or 'not graded')).strip().lower()
            t += (f"Critical density is {dg} — {F['cpli_critical_count']} "
                  f"activities ({K.pct(F.get('cpli_critical_pct'), 1)}) sit at critical float")
        if ck.get('cpli') is not None:
            t += ((" — and " if t else '') + f"CPLI (the critical path length index — below 1.0 means the remaining path "
                  f"doesn't fit the time left) is {K.ratio(ck['cpli'])} against a {K.ratio(ck.get('target') or 0.95)} target"
                  + (f", with {ck['critical_path_length_days']} working days of critical path left"
                     if ck.get('critical_path_length_days') is not None else '')
                  + (f" and {_sg(ck['project_total_float_days'])} wd of project float"
                     if ck.get('project_total_float_days') is not None else ''))
        p7.append(t + '.')
    if nok and not comm_on_chain:
        p7.append("In that network, commissioning would land on the critical path the moment it's added, because it follows "
                  "the last activities before the finish. That's the right place for it — testing follows the work it "
                  "tests. If you add it and it doesn't come out critical, the logic is wrong.")
    elif not nok:
        p7.append("Wherever commissioning sits, it should come out on the critical path once it's in, because it follows the "
                  "last work before handover — if it doesn't, the logic feeding it is wrong.")
    s_cp = K.sec('Is it on the critical path?', *p7)

    # ═══ 8. do the right activities exist? ═══════════════════════════════════════
    p8, t8 = [], None
    if nok:
        p8.append("Whatever the project type, the close-out spine should run: construction tests → final connections → "
                  "pre-commissioning → commissioning → punch list → Taking-Over, with as-builts and O&M documentation "
                  "alongside and demobilisation after. Here's what your file shows against each stage:")
        rows = []
        missing = []
        for label, links, rx in _STAGES:
            hits = spine[label]
            if label.startswith('Taking-Over'):
                if handover_is_fin:
                    shows = f"Present — the finish milestone is the handover: {fin['name']} ({fin.get('id')}, {fin.get('finish')})"
                elif hits:
                    shows = "Present — " + _join(examples(hits, 3))
                else:
                    shows = ((f"Finish is {fin['name']} ({fin.get('id')}, {fin.get('finish')}) — " if fin.get('name') else '')
                             + "no separate Taking-Over milestone visible")
                    missing.append(label)
            elif hits:
                shows = f"Present — {len(hits)} activit{'ies' if len(hits) != 1 else 'y'}: {_join(examples(hits, 3))}"
                if label.startswith('Final connections') and last and rx.search(last['name']):
                    shows += '; the last one sets the finish'
                if label == 'As-builts':
                    asm = next((m for m in milestones if rx.search(m['name']) and not m.get('done')), None)
                    if asm:
                        shows += (f"; {asm['name']} ({asm['id']}) {asm.get('baseline_finish')} → {asm.get('finish')}, "
                                  f"{_sg(asm.get('slip_wd'))} wd, float {_sg(asm.get('tf'))}")
            else:
                shows = 'Not visible'
                if label.startswith('Pre-commissioning') and last and tail_now == 0 and fin.get('id'):
                    shows += f" — nothing between {last['id']} and {fin['id']}"
                if label.startswith('Commissioning') and equip_client:
                    shows += ' — confirm scope (the client furnishes equipment)'
                missing.append(label)
            rows.append([label, links, shows])
        t8 = K.tbl(['Close-out stage', 'Should exist / typically links', 'What your file shows'], rows,
                   f"Searched {searched} and their WBS headings, plus the milestones and the finish chain. 'Not visible' "
                   "means nothing is named for it — confirm against the contract scope before adding it.")
        thinking.append(f"Searched {searched} for commissioning, testing, punch-list, handover and close-out steps")
    else:
        missing = []
        p8.append("Checking the close-out spine (construction tests → final connections → pre-commissioning → commissioning → "
                  "punch list → Taking-Over, with as-builts, O&M manuals and demobilisation) needs the activity list in the "
                  "schedule file. Re-import it and I'll mark each stage present or missing.")
    s_type = K.sec('Do the right activities exist for this type?', *p8, table=t8)

    # ═══ 9. commissioning-tail compression ═══════════════════════════════════════
    p9 = []
    if nok and chain and fdt:
        back = [x for x in chain if _date(x.get('finish')) and _date(x['finish']) >= fdt - timedelta(days=42)]
        sl = [x['slip_wd'] for x in back if x.get('slip_wd') is not None]
        fs = fin.get('slip_wd')
        if sl:
            lo, hi = min(sl), max(sl)
            bt = {_trade(x) for x in back if 'Milestone' not in (x.get('type') or '')}
            wt = [simple.get(t, t) for t in order if t in bt]
            ms_b = [_clean(x['name']) for x in back if 'Milestone' in (x.get('type') or '')]
            block = fs is not None and (hi - lo) <= 5 and lo >= fs - 5
            if block:
                t = ("Good news on compression, bad news on the tail. " if (tail_now == 0 and not comm_hits) else '') + \
                    ("Compression first: the back end of the chain slipped as a block. "
                     + (f"The {_join(wt)} work" if wt else 'The last activities')
                     + (f" and {_join(ms_b[:2])}" if ms_b else '')
                     + f" all moved {lo}–{hi} working days against the baseline, so nothing downstream was shortened to "
                       "protect a date. The finish moved honestly")
                if has_audit and F.get('neg_float_count') is not None:
                    t += (f" — consistent with the {F['neg_float_count']} activities ({K.pct(F.get('neg_float_pct'), 1)}) that "
                          "show negative float openly")
                p9.append(t + '.')
            else:
                short = [x for x in back if x.get('slip_wd') is not None and fs is not None and x['slip_wd'] < fs - 5]
                p9.append(f"Compression check: the back end of the chain moved {lo}–{hi} wd against the baseline while the "
                          f"finish moved {_sg(fs)} wd."
                          + (" Some of it moved less than the finish — check these durations for compression: "
                             + _join([f"{_clean(x['name'])} ({x['id']}, {_sg(x['slip_wd'])} wd)" for x in short[:3]]) + '.'
                             if short else ''))
        if tail_now is not None and tail_base is not None and last:
            if tail_now == 0 and tail_base == 0:
                p9.append(f"The problem is that there's no tail to compress. In the baseline the last activity "
                          f"({_clean(last['name'])}) and {fin.get('name')} were both {fin.get('baseline_finish')}; today both "
                          f"are {fin.get('finish')}. Zero days of testing then, zero now. If commissioning is in your scope and "
                          "the completion date is held, the testing time has to come from somewhere"
                          + (f" — and on a schedule already {round(d)} wd behind, that's where quality gets traded for dates."
                             if behind else '.'))
            elif tail_now < tail_base:
                p9.append(f"The tail between the last activity ({_clean(last['name'])}) and {fin.get('name')} has shrunk from "
                          f"{tail_base} to {tail_now} days since the baseline — that is compression; check whether it was a "
                          "deliberate, justified change.")
            else:
                p9.append(f"The tail between the last activity ({_clean(last['name'])}) and {fin.get('name')} is {tail_now} "
                          f"days today against {tail_base} in the baseline — intact.")
    elif not nok:
        p9.append("The compression check compares the back end of the finish chain with its baseline dates, which needs the "
                  "schedule file.")
    p9.append("To see how the tail behaves between updates rather than against baseline, run Update vs Update on the previous "
              "update; the days a re-sequence would buy back come from the What-if (P6 F9). I won't estimate either from one "
              "snapshot.")
    s_tail = K.sec('The commissioning-tail compression check', *p9)
    if nok and chain:
        thinking.append(f"Traced the {N.get('chain_count') or len(chain)}-activity finish chain for trade handoffs, "
                        "convergence and the commissioning tail")

    # ═══ 10. close-out present AND linked ════════════════════════════════════════
    p10 = []
    if nok:
        ab = spine['As-builts']
        asm = next((m for m in milestones if re.search(r'as[- ]?built', m['name'], re.I) and not m.get('done')), None)
        pres = []
        if ab:
            br = {}
            for a in ab:
                k = (a.get('wbs_path') or '').split(' / ')[0]
                br[k] = br.get(k, 0) + 1
            bk = max(br.items(), key=lambda kv: kv[1])[0]
            pres.append(f"as-builts ({bk}, {_pl(len(ab), 'activity', 'activities')})")
        for label in ('O&M manuals / final documentation', 'Punch list / snagging'):
            if spine[label]:
                pres.append(f"{_MISS[label]} ({_pl(len(spine[label]), 'activity', 'activities')})")
        if key_ms:
            pres.append(_pl(len(key_ms), 'open key-date milestone'))
        t = ("Present: " + _join(pres) + '.') if pres else "Present: none of the close-out steps is named in the file."
        if has_audit and F.get('open_ends') is not None:
            t += (f" Linked: {'yes, as far as the file shows — ' if F['open_ends'] == 0 else 'not fully — '}"
                  f"{F['open_ends']} open ends")
            if asm and asm.get('tf') is not None:
                t += (f", and {asm['name']} carries {_sg(asm['tf'])} wd float"
                      + (", which normally comes from logic tying it to the finish" if asm['tf'] < 0 else ''))
            t += '.'
            if asm and (asm.get('slip_wd') or 0) > 0:
                t += (f" It's also {_sg(asm['slip_wd'])} wd late against baseline ({asm.get('baseline_finish')} → "
                      f"{asm.get('finish')})" + (", so as-builts are on a negative-float path in their own right."
                                                 if (asm.get('tf') or 0) < 0 else '.'))
        p10.append(t)
        miss = [m for m in missing if m not in ('Construction tests', 'As-builts')]
        t = (f"Not present, as far as I can see: {_join([_MISS.get(m, m) for m in miss])}. "
             if miss else "Every close-out stage is named somewhere in the file. ")
        if has_audit and F.get('dangling_count'):
            t += (f"Whether any of the {F['dangling_count']} dangling activities is a close-out item needs Dangling Resolve "
                  "& Correct to name them. ")
        if not comm_hits and last:
            t += (f"Once commissioning scope is confirmed, add it FS from the last activities ({last['id']}) and FS into "
                  f"{fin.get('name') or 'the finish milestone'}, so the finish date genuinely includes it.")
        p10.append(t.strip())
    else:
        p10.append(("From the stored logic checks: " + f"{F.get('open_ends')} open ends and {F.get('dangling_count')} dangling "
                    "activities — so close-out items are at least not left open-ended, but whether they exist needs the "
                    "file.") if has_audit and F.get('open_ends') is not None else
                   "Whether close-out activities are present and linked needs the schedule file and the logic checks — "
                   "re-import the file and run the Schedule Audit.")
    s_close = K.sec('Close-out present AND linked', *p10)

    # ═══ verdict ═════════════════════════════════════════════════════════════════
    top_is_lead = bool(top_g and lead and _trade_toks(top_g['code']) & _trade_toks(lead))
    where = f" on {_join(lead_areas[:2])}" if lead_areas else ''
    if drv and _wgap(drv) >= 1 and behind:
        if top_g:
            head = (f"{top_g['code']} is the package behind ({round(top_g.get('pct_of_gap') or 0, 2)}% of the value gap)"
                    + (f" and its front{where} sets the finish" if top_is_lead and where else
                       f" and its {simple.get(lead, lead)} front sets the finish" if top_is_lead else
                       (f"; the {simple.get(lead, lead)} front{where} sets the finish" if lead else '')))
        else:
            head = (f"{drv['name']} is the package behind ({drv['actual']}% vs {drv['planned']}% on "
                    f"{round((drv.get('weight') or 0) * 100)}% of the weight)"
                    + (f" and its {simple.get(lead, lead)} front{where} sets the finish" if lead else ''))
        if after_zero:
            one = len(after_zero[:4]) == 1
            head += (f" — the {_join([_lc(simple.get(t, t)) for t in after_zero[:4]])} "
                     f"{'trade is' if one else 'trades are'} late mostly because {'it inherits' if one else 'they inherit'} "
                     f"its ~{round(d)} wd")
    elif ahead:
        head = f"No package is materially behind — the job is about {K.wd(d)} ahead (SPI {K.ratio(spi)})"
    elif drv and behind:
        head = f"The slip is spread thin — {drv['name']} carries the most weighted gap, but under a point"
    else:
        head = "No package is materially behind" + (f" (SPI {K.ratio(spi)})" if spi is not None else '')
    if nok:
        if comm_hits:
            head += f"; commissioning is in the file ({_pl(len(comm_hits), 'activity', 'activities')})" + \
                    (" and on the critical path." if comm_on_chain else ", not yet on the critical path.")
        elif last and tail_now == 0:
            head += (f" — and nothing sits between the last {_short(last['name'], 40)} and {fin.get('name')}, so confirm "
                     "whether commissioning is in your scope.")
        else:
            head += " — and no commissioning step is visible before the finish, so confirm whether it's in your scope."
    else:
        head += ". Commissioning coverage and the handoffs need the schedule file, which couldn't be re-read — re-import it."

    # ═══ pills ═══════════════════════════════════════════════════════════════════
    pills = []
    if ahead:
        pills.append(K.pill(f"Ahead · SPI {K.ratio(spi)} · {K.signed(d)}", 'success'))
    if top_g:
        pills.append(K.pill(f"{top_g['code']} · {round(top_g.get('pct_of_gap') or 0, 2)}% of the value gap",
                            'danger' if behind else 'warning'))
    if drv:
        pills.append(K.pill(f"{_short(drv['name'], 30)} · {drv['actual']}% vs {drv['planned']}%",
                            'danger' if (behind and _wgap(drv) >= 1) else 'warning'))
    elif ds:
        pills.append(K.pill('All packages at or ahead of plan', 'success'))
    if nok and open_client:
        neg_open = [c for c in open_client if c.get('tf') is not None and c['tf'] < 0]
        pills.append(K.pill(f"{len(neg_open)} of {len(open_client)} client inputs on negative float",
                            'warning' if neg_open else 'success'))
    pills.append(K.pill('Subcontractor code in the file' if sub_dim else
                        (f"Split by '{_short(dim, 24)}', not subcontractor" if vg else 'No subcontractor split stored'),
                        'neutral'))
    if nok:
        pills.append(K.pill('Commissioning in the file' if comm_hits else 'No commissioning step before the finish',
                            'success' if comm_hits else 'warning'))
    if nok and len({_trade(x) for x in win}) >= 2:
        ms_ = sorted(_date(x['finish']) for x in win)
        span = (ms_[-1].strftime('%b %Y') if ms_[0].strftime('%b %Y') == ms_[-1].strftime('%b %Y') else
                f"{ms_[0].strftime('%b')}–{ms_[-1].strftime('%b %Y')}" if ms_[0].year == ms_[-1].year else
                f"{ms_[0].strftime('%b %Y')}–{ms_[-1].strftime('%b %Y')}")
        pills.append(K.pill(f"{len({_trade(x) for x in win})} trades converge {span}", 'warning'))

    # ═══ measured / actions / evidence ═══════════════════════════════════════════
    measured = ("Package ranking = the weighted category breakdown in the file (weight × actual % vs planned %). "
                + (f"Trade ranking = the PV–EV value gap grouped by the file's '{dim}' activity code, plus the slip of the "
                   "open key-date milestones named for each trade (baseline vs current finish, in working days). " if vg else
                   "No value split by activity code is stored, so the package proxy is the open key-date milestones (baseline "
                   "vs current finish, in working days). ")
                + ("Client-input slip and float are read from the file's client/employer activities; a 0% item forecast on "
                   "the data date is not actualised in P6. " if nok else '')
                + ("Dangling and open ends come from the logic check. " if has_audit else '')
                + (f"The finish chain = the incomplete activities sharing the finish's float (within {N.get('chain_band')} wd), "
                   "in date order; trades are read from its WBS. Commissioning and close-out presence is a name search of "
                   f"{searched} and their WBS headings, plus the milestones and the finish chain. " if nok else '')
                + "Trade-stacking needs a time-phased area-occupancy histogram the tool doesn't build yet. Update-to-update "
                  "tail change needs Update vs Update; recoverable days need the What-if (P6 F9). The employer vs "
                  "contractor split of any delay needs a TIA / windows analysis.")
    actions = []
    if drv and behind and _wgap(drv) >= 1:
        actions.append(f"Name {top_g['code'] if top_g else drv['name']} as the package behind in this week's report"
                       + (f" — {round(top_g.get('pct_of_gap') or 0, 2)}% of the value gap —" if top_g else '')
                       + (f" with the {lead} front" + (f" on {_join(lead_areas[:3])}" if lead_areas else '')
                          + " as what sets the finish" if lead else '') + '.'
                       + (f" Don't chase the {_join([_lc(simple.get(t, t)) for t in after_zero[:4]])} trades for slip they "
                          "inherit." if after_zero else ''))
    if nok and not comm_hits:
        actions.append("Confirm with the contract whether pre-commissioning and commissioning are in your scope; if yes, add "
                       + (f"them FS from the last activities ({last['id']}) and FS into {fin.get('name')}"
                          if last and fin.get('name') else "them FS from the last installation work and FS into the finish")
                       + ", then re-run the forecast.")
    if late_open:
        ln = sorted([c for c in late_open if c.get('tf') is not None], key=lambda c: c['tf'])[:5]
        actions.append("Chase the late client inputs by name, worst float first — "
                       + ', '.join(f"{_short(c['name'], 72)} ({_sg(c['tf'])})" for c in ln)
                       + " — and actualise any that have in fact been received.")
    if pinned:
        actions.append(f"Check whether the {len(pinned)} client item{'s' if len(pinned) > 1 else ''} sitting at zero slip and "
                       "zero float are held by date constraints; if so, move them to the real promised dates.")
    if not sub_dim:
        actions.append("Add a 'Subcontractor' activity code in P6, assign it and re-import — the tool will then rank "
                       "subcontractors worst-first.")
    if has_audit and F.get('dangling_count'):
        both = ((audit.get('dangling') or {}).get('kpis') or {}).get('both_dangling')
        actions.append(f"Run Dangling Resolve & Correct on the {F['dangling_count']}"
                       + (f", starting with the {both} loose at both ends," if both else '')
                       + " and check whether any is a handoff or a close-out item.")
    if nok and len({_trade(x) for x in win}) >= 2 and behind:
        ms_ = sorted(_date(x['finish']) for x in win)
        actions.append(f"Before committing to a recovery on the {simple.get(lead, lead)} front, walk the area plan with site: "
                       f"{len({_trade(x) for x in win})} trades converge there between {ms_[0].strftime('%d-%b')} and "
                       f"{ms_[-1].strftime('%d-%b-%Y')}.")
    if late_open and behind:
        actions.append(f"Log the late client inputs in the delay record now, and run a TIA / Consultant Review before stating "
                       f"how many of the {round(d)} days they caused.")
    if not nok:
        actions.append("Re-import the schedule file to restore the chain, client-input and close-out detail.")

    evid = []
    if drv:
        evid.append(K.ev('Package behind' if (behind and _wgap(drv) >= 1) else 'Largest weighted gap',
                         f"{drv['name']} — {drv['actual']}% vs {drv['planned']}% ({round((drv.get('weight') or 0) * 100)}% weight)"))
    if top_g:
        evid.append(K.ev(f"{top_g['code']} share of value gap", f"{round(top_g.get('pct_of_gap') or 0, 2)}%"))
    evid.append(K.ev('Subcontractor split', f"'{dim}' code" if sub_dim else
                     (f"none — value split is by '{dim}'" if vg else 'none stored')))
    if nok and open_client:
        evid.append(K.ev('Client inputs on negative float',
                         f"{sum(1 for c in open_client if (c.get('tf') or 0) < 0)} of {len(open_client)} open"))
    if late_open:
        w = min([c for c in late_open if c.get('tf') is not None] or late_open, key=lambda c: c.get('tf') or 0)
        evid.append(K.ev('Worst client input', f"{_short(w['name'], 36)} {_sg(w.get('slip_wd'))} wd, float {_sg(w.get('tf'))}"))
    if vg and groups:
        ks = [(g['code'], worst_key(_trade_toks(g['code']))) for g in groups]
        ks = [(c, m) for c, m in ks if m]
        if ks:
            mx = max(m['slip_wd'] for _, m in ks)
            evid.append(K.ev('Latest trade key dates', f"{_join([_short(m['name'], 30) for _, m in ks if m['slip_wd'] == mx][:2])} "
                                                       f"{_sg(mx)} wd"))
    if last:
        evid.append(K.ev('Last activity before finish', f"{_short(last['name'], 36)}, {last['finish']}"))
    if nok:
        evid.append(K.ev(f"Commissioning before {fin.get('id') or 'finish'}",
                         f"{len(comm_hits)} activities" if comm_hits else 'none visible'))
        asm = next((m for m in milestones if re.search(r'as[- ]?built', m['name'], re.I) and not m.get('done')), None)
        if asm:
            evid.append(K.ev('As-builts', f"{_short(asm['name'], 30)} {_sg(asm.get('slip_wd'))} wd, float {_sg(asm.get('tf'))}"))
    if dk.get('total_dangling') is not None:
        evid.append(K.ev('Dangling / open ends', f"{dk['total_dangling']} ({dk.get('start_dangling')} / "
                                                 f"{dk.get('finish_dangling')} / {dk.get('both_dangling')}) · {F.get('open_ends')}"))
    evid.append(K.ev('SPI / slip', f"{K.ratio(spi)} · {K.signed(d)}" if d is not None else K.ratio(spi)))

    if not nok:
        thinking.append("The schedule file couldn't be re-read, so the chain, client inputs and close-out search were "
                        "answered from the stored categories and audits only")

    a = K.A2(head, [s_rank, s_sub, s_int, s_cli, s_stack, s_comm, s_cp, s_type, s_tail, s_close], pills=pills[:6],
             measured=measured, actions=actions, evidence=evid,
             drilldowns=[K.drill('q13', 'Do the late client inputs give me an EOT case?') if late_open
                         else K.drill('q04', "What's driving the date, and how much float is left?"),
                         K.drill('q05', f"How do I recover the ~{round(d)} days?") if behind
                         else K.drill('q01', 'Where do we stand overall?'),
                         K.drill('q02', 'Which milestones are slipping, and by how much?'),
                         K.drill('q12', 'Does the logic make construction sense?')])
    a['thinking'] = thinking[:4]
    return a
