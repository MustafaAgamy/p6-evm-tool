"""q04 — Critical path & float — what's driving the date, and how much room is left?

Covers: the chain that sets the finish (what it runs through, how long, started or not, its float and slip
pattern), whether it's believable (CPLI, out-of-sequence, lags, constraints), longest path vs the zero-float
set, the parallel / near-critical paths behind it, float health (how much, how negative, where) and where
crews can come from — for ANY project.

``view(F, N)`` is the shared read of the network (fronts, ladder of parallel paths, crew sources…) that the
recovery answer (q05) builds on, so both answers describe the same chain the same way.
"""
import re
from datetime import datetime

from . import _kit2 as K

MINUS = '−'
DONOR_TF = 20            # wd of float before a sectional front counts as a place crews can come from

# Generic construction trades, used to tell which fronts share work with the driving chain.
TRADES = (
    ('design', ('design', 'engineering', 'drawing', 'as-built', 'as built', 'submittal')),
    ('civil', ('civil', 'concrete', 'foundation', 'pile', 'piling', 'earthwork', 'excavation', 'formwork')),
    ('mechanical', ('mechanical', 'mech')),
    ('steel', ('steel',)),
    ('electrical', ('electrical', 'cable', 'cabling')),
    ('piping', ('piping', 'pipe')),
    ('MEP', ('mep', 'hvac', 'plumbing', 'fire fighting', 'firefighting')),
    ('finishes', ('architectural', 'finishing', 'finishes', 'fit-out', 'fit out')),
    ('equipment', ('equipment', 'eqp')),
    ('instrumentation', ('instrument',)),
)
_TRADE_RX = [(name, re.compile(r'\b(?:' + '|'.join(re.escape(w) for w in words) + r')', re.I)) for name, words in TRADES]
_GENERIC = {'works', 'work', 'completion', 'complete', 'completed', 'installation', 'installations', 'install',
            'all', 'of', 'the', 'and', 'for', 'to', 'finish', 'structure', 'structures', 'erection', 'system',
            'systems', 'package', 'scope', 'key', 'dates', 'date', 'milestone'}


# ── small formatting helpers ──────────────────────────────────────────────────────────────────────
def fl(v):
    """Signed float/slip in working days: '−60', '+159', '0'."""
    if v is None:
        return '—'
    v = round(v)
    return f"{MINUS}{abs(v):,}" if v < 0 else (f"+{v:,}" if v > 0 else '0')


def rng(a, b):
    """A float range written from the value nearest zero outward: '−59 to −61', '+12 to +14'."""
    lo, hi = min(a, b), max(a, b)
    if lo == hi:
        return fl(lo)
    return f"{fl(hi)} to {fl(lo)}" if hi < 0 else f"{fl(lo)} to {fl(hi)}"


def p1(x):
    return '—' if x is None else f"{round(float(x), 1):g}"


def n0(x):
    return '—' if x is None else f"{int(round(x)):,}"


def date(s):
    try:
        return datetime.strptime(s, '%d-%b-%Y')
    except (TypeError, ValueError):
        return None


def nm(x):
    return ' '.join((x.get('name') or '').split())


def idn(x):
    return f"{nm(x)} ({x['id']})"


def join_and(items):
    items = [i for i in items if i]
    if len(items) <= 1:
        return ''.join(items)
    return ', '.join(items[:-1]) + ' and ' + items[-1]


def _parts(x):
    return [p.strip() for p in (x.get('wbs') or '').split(' / ') if p.strip()]


def front_of(x):
    p = _parts(x)
    return ' / '.join(p[-2:]) if p else '(no WBS)'


def trade_of(text):
    for name, rx in _TRADE_RX:
        if rx.search(text or ''):
            return name
    return None


def _tokens(s):
    return set(re.findall(r'[a-z0-9]+', (s or '').lower()))


def unit_of(name):
    """What's left of a milestone name once trade and generic words are removed — e.g. its phase/area."""
    return {t for t in _tokens(name) - _GENERIC if not trade_of(t)}


def is_ms(x):
    return 'Milestone' in (x.get('type') or '')


def status(x, dd):
    """'0%, forecast 20-Mar-2027' / '0%, was due 23-Jun-2026'."""
    bl, d0 = date(x.get('baseline_finish')), date(dd)
    if x.get('pct') == 0 and bl and d0 and bl < d0:
        return f"0%, was due {x['baseline_finish']}"
    return f"{x.get('pct', 0)}%, forecast {x.get('finish') or '—'}"


# ── the shared network read ───────────────────────────────────────────────────────────────────────
def view(F, N):
    """Everything both q04 and q05 need from the network, derived generically. {'ok': False} without N."""
    if not (N and N.get('ok')):
        return {'ok': False}
    dd = N.get('data_date') or F.get('data_date')
    fin = N.get('finish_milestone') or {}
    fin_tf = N.get('finish_tf')
    chain = [x for x in (N.get('chain') or []) if x.get('tf') is not None]
    work = [x for x in chain if not is_ms(x)]
    chain_ms = [x for x in chain if is_ms(x)]
    chain_ids = {x['id'] for x in chain} | ({fin['id']} if fin.get('id') else set())
    client = N.get('client_inputs') or []
    client_ids = {x['id'] for x in client}
    v = {'ok': True, 'dd': dd, 'fin': fin, 'fin_tf': fin_tf, 'chain': chain, 'work': work, 'chain_ms': chain_ms,
         'length': (N.get('chain_count') or len(chain)) + (1 if fin.get('id') else 0), 'band': N.get('chain_band'),
         'client': client, 'client_ids': client_ids}
    if fin_tf is None or not work:
        v.update({'work': [], 'fronts': [], 'head': None, 'ladder': [], 'deeper': [], 'sectional': [], 'donors': [],
                  'started': 0, 'handoff': None, 'window': None})
        v.update(_client_view(N, client))
        return v

    # fronts, in the order the chain first reaches them
    order, groups = [], {}
    for x in work:
        f = front_of(x)
        if f not in groups:
            groups[f] = []
            order.append(f)
        groups[f].append(x)
    fronts = [{'label': f, 'rows': groups[f], 'path': groups[f][0].get('wbs') or '',
               'trade': trade_of(groups[f][0].get('wbs') or '')} for f in order]
    head = work[0]
    started = sum(1 for x in chain if (x.get('pct') or 0) > 0)

    # float band: the core the chain sits in, and anything deeper than the finish itself
    tfs = [x['tf'] for x in chain] + [fin_tf]
    core = [t for t in tfs if t >= fin_tf - 1]
    outliers = [x for x in chain if x['tf'] < fin_tf - 1]

    # slip pattern along the chain
    slips = [x['slip_wd'] for x in work if x.get('slip_wd') is not None]
    slip = None
    if slips:
        med = sorted(slips)[len(slips) // 2]
        odd = [x for x in work if x.get('slip_wd') is not None and abs(x['slip_wd'] - med) > 4]
        core_s = [s for s in slips if abs(s - med) <= 4] or slips
        last = next((x['slip_wd'] for x in reversed(work) if x.get('slip_wd') is not None), None)
        slip = {'lo': min(core_s), 'hi': max(core_s), 'head': head.get('slip_wd'), 'tail': last, 'odd': odd}

    # unit-to-unit hand-off: two or more sibling WBS units of one parent on the chain (Area 1 → Area 2)
    by_parent = {}
    for fr in fronts:
        p = _parts(fr['rows'][0])
        if len(p) >= 3:
            by_parent.setdefault(' / '.join(p[:-1]), []).append(fr)
    handoff = None
    for parent, frs in by_parent.items():
        if len(frs) >= 2:
            handoff = {'parent': parent.split(' / ')[-1], 'units': [_parts(f['rows'][0])[-1] for f in frs],
                       'labels': [f['label'] for f in frs]}
            break
    has_wbs = bool(_parts(head))
    if handoff and front_of(head) in handoff['labels']:
        driver = f"{handoff['parent']} / " + ' → '.join(handoff['units'])
        driver_fronts = handoff['labels']
    else:
        driver, driver_fronts = (front_of(head) if has_wbs else nm(head)), [front_of(head)]
    chain_trades = []
    for fr in fronts:
        if fr['trade'] and fr['trade'] not in chain_trades:
            chain_trades.append(fr['trade'])
    chain_tokens = set()
    for x in work:
        chain_tokens |= _tokens(x.get('wbs'))

    def fed(m):
        """Does this milestone roll up work the chain itself feeds (same trade AND same phase/area)?"""
        if m['id'] in client_ids:
            return False
        t, u = trade_of(nm(m)) or trade_of(m.get('wbs')), unit_of(nm(m))
        return bool(t and t in chain_trades and u and u <= chain_tokens)

    # the ladder: open milestones / client inputs on negative float, less negative than the driver
    pool = {}
    for x in (N.get('milestones') or []) + client:
        if x.get('done') or x.get('tf') is None or x['id'] in chain_ids:
            continue
        if fin_tf < x['tf'] < 0:
            pool[x['id']] = x
    by_tf = {}
    for x in sorted(pool.values(), key=lambda r: r['tf']):
        by_tf.setdefault(x['tf'], []).append(x)
    ladder = []
    for tf, items in sorted(by_tf.items()):
        f = [i for i in items if fed(i)]
        ladder.append({'tf': tf, 'gap': tf - fin_tf, 'items': items, 'fed': bool(f),
                       'fed_trade': (trade_of(nm(f[0])) or trade_of(f[0].get('wbs'))) if f else None,
                       'client': all(i['id'] in client_ids for i in items)})
    indep = next((g for g in ladder if not g['fed']), None)

    # where the fed path joins the chain: fronts after that trade's front are the "tail"
    fed_idx = None
    if ladder and ladder[0]['fed']:
        fed_idx = next((i for i, fr in enumerate(fronts) if fr['trade'] == ladder[0]['fed_trade']), None)
    for i, fr in enumerate(fronts):
        fr['role'] = ('head' if i == 0 else
                      'fed' if fed_idx is not None and i == fed_idx else
                      'tail' if fed_idx is not None and i > fed_idx else 'upstream')

    deeper = [x for x in (N.get('deepest') or []) if x.get('tf') is not None and x['tf'] < fin_tf - 1]
    sectional = [m for m in (N.get('milestones') or []) if not m.get('done') and m.get('tf') is not None
                 and m.get('type') == 'FinishMilestone' and m['id'] not in client_ids and m['id'] not in chain_ids]

    # crew sources: sectional fronts with real float, in a trade the chain uses (never design)
    head_trade = fronts[0]['trade']
    donors = [m for m in sectional if m['tf'] >= DONOR_TF]
    donors = [m for m in donors if (trade_of(nm(m)) or trade_of(m.get('wbs'))) in chain_trades
              and (trade_of(nm(m)) or trade_of(m.get('wbs'))) != 'design']
    donors.sort(key=lambda m: (0 if (trade_of(nm(m)) or trade_of(m.get('wbs'))) == head_trade else 1, -m['tf']))
    for m in donors:
        m_u = unit_of(nm(m))
        m['_trade'] = trade_of(nm(m)) or trade_of(m.get('wbs'))
        m['_at_risk'] = [o for o in sectional if o is not m and o['tf'] < 0 and m_u and unit_of(nm(o)) == m_u]

    # when the chain's fronts stack up (months with work finishing on two or more fronts)
    months = {}
    for x in work:
        dt = date(x.get('finish'))
        if dt:
            months.setdefault((dt.year, dt.month), set()).add(front_of(x))
    busy = sorted(k for k, s in months.items() if len(s) >= 2)
    window = None
    if busy:
        a, b = datetime(busy[0][0], busy[0][1], 1), datetime(busy[-1][0], busy[-1][1], 1)
        window = (a.strftime('%b') + ('–' + b.strftime('%b %Y') if a != b else ' ' + a.strftime('%Y'))
                  if a.year == b.year else a.strftime('%b %Y') + '–' + b.strftime('%b %Y'))
        stack = []
        for k in busy:
            for f in [fr['label'] for fr in fronts if fr['label'] in months[k]]:
                if f not in stack:
                    stack.append(f)
        window = {'text': window, 'fronts': stack}

    v.update({'fronts': fronts, 'head': head, 'started': started, 'core': (min(core), max(core)),
              'full': (min(tfs), max(tfs)), 'outliers': outliers, 'slip': slip, 'handoff': handoff,
              'driver': driver, 'driver_fronts': driver_fronts, 'chain_trades': chain_trades, 'has_wbs': has_wbs,
              'ladder': ladder, 'indep': indep, 'deeper': deeper, 'sectional': sectional, 'donors': donors,
              'window': window})
    v.update(_client_view(N, client))
    return v


def _client_view(N, client):
    open_c = [x for x in client if not x.get('done')]
    late = [x for x in (N.get('client_inputs_late_open') or []) if x.get('slip_wd') is not None]
    return {'client_open': open_c,
            'client_late': sorted(late, key=lambda x: (x['tf'] if x.get('tf') is not None else 0)),
            'client_late_neg': sorted([x for x in late if x.get('tf') is not None and x['tf'] < 0], key=lambda x: x['tf']),
            'client_on_time': [x for x in open_c if (x.get('slip_wd') or 0) <= 0],
            'client_done_late': N.get('client_inputs_late_done') or []}


def audit_view(F):
    """The stored audit figures this answer uses — all None when no audit is stored for the update."""
    has = bool(F.get('has_audit'))
    au = (F.get('audit') or {}) if has else {}
    g = (lambda k: F.get(k)) if has else (lambda k: None)
    flk = (au.get('float') or {}).get('kpis') or {}
    neg, neg_pct, above, above_pct = g('neg_float_count'), g('neg_float_pct'), g('float_above'), g('float_pct')
    dens = g('cpli_density_grade')
    return {'has': has, 'au': au, 'cp': (au.get('cpli') or {}).get('kpis') or {},
            'lg': (au.get('lag_lead') or {}).get('kpis') or {},
            'total': flk.get('total_activities') or ((au.get('negative_float') or {}).get('kpis') or {}).get('total_activities'),
            'neg': neg, 'neg_pct': neg_pct, 'above': above, 'above_pct': above_pct, 'thr': g('float_threshold'),
            'avg': g('avg_float'), 'max': g('max_float'), 'crit': g('cpli_critical_count'),
            'crit_pct': g('cpli_critical_pct'), 'dpc': g('driving_path_count'), 'dens': dens,
            'dens_word': (dens or '').replace(' density', '').strip() or None,
            'oos': g('oos_count'), 'oos_pct': g('oos_pct'), 'coos': g('critical_oos'),
            'dangling': g('dangling_count'), 'float_grade': g('float_grade'),
            'bipolar': (neg is not None and above is not None and neg_pct is not None and above_pct is not None
                        and neg_pct >= 20 and above_pct >= 15)}


def no_chain(v):
    """Why the chain isn't named: the file wasn't re-read, or it was and shows no chain."""
    return ("I couldn't re-read the file, so the chain itself isn't traced here" if not v.get('ok') else
            "The file doesn't show a driving chain I can trace (no finish milestone or no open activity on its float)")


def was_due(x, dd):
    """One sentence on where the chain's head stands against its baseline."""
    bl, d0 = date(x.get('baseline_finish')), date(dd)
    if x.get('pct') == 0 and bl and d0 and bl < d0:
        return (f"That activity was due to finish {x['baseline_finish']}, hadn't started at the {dd} data date, "
                f"and is now forecast for {x['finish']}.")
    if x.get('baseline_finish'):
        return (f"It was baselined to finish {x['baseline_finish']} and is now forecast for {x['finish']} "
                f"({x.get('pct', 0)}% done).")
    return ''


def ends_of(v):
    ms = list(v['chain_ms']) + ([v['fin']] if v['fin'].get('id') else [])
    return join_and([idn(m) for m in ms])


def route(v):
    """'Area / Unit 1 → Unit 2 (civil) into mechanical, steel and electrical work'."""
    later = []
    for fr in v['fronts']:
        if fr['label'] in v['driver_fronts'] or not fr['trade'] or fr['trade'] == v['fronts'][0]['trade']:
            continue
        if fr['trade'] not in later:
            later.append(fr['trade'])
    t0 = v['fronts'][0]['trade']
    return v['driver'] + (f" {t0} work" if t0 else '') + (f" into {join_and(later)} work" if later else '')


def ladder_names(g, short=False):
    return ' / '.join((nm(i) if short else idn(i)) for i in g['items'][:2]) + (
        f" (+{len(g['items']) - 2})" if len(g['items']) > 2 else '')


# ── the answer ────────────────────────────────────────────────────────────────────────────────────
def build(F, N, role):
    v = view(F, N)
    nok = v['ok'] and bool(v.get('work'))
    d = F.get('delay_days')
    behind = (d or 0) > 0
    dd = v.get('dd') or F.get('data_date')
    A = audit_view(F)
    au, cp, lg = A['au'], A['cp'], A['lg']
    total_aud = A['total']
    neg, neg_pct, above, above_pct, thr = A['neg'], A['neg_pct'], A['above'], A['above_pct'], A['thr']
    avg, mx, crit, crit_pct, dpc = A['avg'], A['max'], A['crit'], A['crit_pct'], A['dpc']
    dens, dens_word = A['dens'], A['dens_word']
    bipolar = A['bipolar']
    cpli = cp.get('cpli') if cp.get('cpli_computable', True) else None
    cpl, ptf = cp.get('critical_path_length_days'), cp.get('project_total_float_days')
    left = (cpl + ptf) if (cpl is not None and ptf is not None) else None
    drv = K.main_driver(F)
    thinking = []

    fin = v.get('fin') or {}
    fin_tf = v.get('fin_tf')
    ladder = v.get('ladder') or []

    # ── verdict ─────────────────────────────────────────────────────────────────────────────────
    if nok:
        started = v['started']
        head = (f"One chain sets {fin.get('finish')}: {route(v)} — {v['length']} activities, "
                + ('none started' if started == 0 else f"{started} started")
                + f", at {rng(*v['core'])} wd"
                + (f" ({len(v['outliers'])} deeper, to {fl(min(x['tf'] for x in v['outliers']))})" if v['outliers'] else '') + '.')
    elif d is not None:
        head = (no_chain(v) + "; on the stored numbers the finish is "
                + (f"about {K.wd(d)} late" if behind else (f"ahead, with about {K.wd(d)} of float to completion" if d < 0 else 'on its date'))
                + f" (SPI {K.ratio(F.get('spi'))}).")
    else:
        head = no_chain(v) + ", and the stored numbers don't carry the finish slip."
    if bipolar:
        head += f" Float is bipolar: {n0(neg)} activities negative, {n0(above)} above {thr} wd."
    elif neg is not None:
        head += f" {n0(neg)} activities are on negative float ({p1(neg_pct)}%)."
    elif not A['has']:
        head += " No float audit is stored for this update, so float health can't be graded yet."

    pills = [K.pill(f"Driver: {v['driver']}", 'danger' if (fin_tf or 0) < 0 else 'warning') if nok else None,
             K.pill(f"{v['length']}-activity chain, {round(100 * v['started'] / max(1, len(v['chain'])))}% started",
                    'danger' if (fin_tf or 0) < 0 else 'neutral') if nok else None,
             K.pill(f"CPLI {K.ratio(cpli)} · {cpl}-wd path, {left} wd left", 'danger' if cpli < 0.95 else 'success')
             if cpli is not None and left is not None else None,
             K.pill(f"{n0(crit)} at critical float: {dens}", 'warning') if crit is not None and dens else None,
             K.pill(f"{n0(neg)} negative ({p1(neg_pct)}%)", 'danger' if (neg_pct or 0) > 5 else 'success') if neg is not None else None,
             K.pill(f"{n0(above)} above {thr} wd ({p1(above_pct)}%)", 'warning' if (above_pct or 0) > 5 else 'success')
             if above is not None and thr else None,
             K.pill('Next paths: ' + ' · '.join(fl(g['tf']) for g in ladder[:3]), 'accent') if ladder else None,
             K.pill(f"avg {p1(avg)} · max {n0(mx)} wd", 'neutral') if avg is not None and mx is not None else None,
             K.pill(K.signed(d), 'danger' if behind else 'success') if not nok and d is not None else None]

    # ── what's driving the date ─────────────────────────────────────────────────────────────────
    if nok:
        fronts, hd = v['fronts'], v['head']
        started = v['started']
        later = [fr['label'] for fr in fronts if fr['label'] not in v['driver_fronts']]
        p_lead = (f"**One chain sets the date. It runs from {v['driver']}"
                  + (f" into {join_and(later)}" if later else '')
                  + f", and ends at {ends_of(v)} on {fin.get('finish')}. It is {v['length']} activities long, "
                  + ('none of them has started' if started == 0 else f"{started} of them started")
                  + (f", and all sit at {rng(*v['core'])} wd.**" if not v['outliers']
                     else f", and all but {len(v['outliers'])} sit at {rng(*v['core'])} wd.**"))
        walk = []
        for fr in fronts:
            names, seen_n = [], set()
            for r in fr['rows']:
                if r is not hd and nm(r).lower() not in seen_n:
                    seen_n.add(nm(r).lower())
                    names.append(nm(r))
            if names:
                walk.append(f"{fr['label']} ({len(fr['rows'])}): " + ', '.join(names[:6])
                            + (f" and {len(names) - 6} more" if len(names) > 6 else ''))
        p_walk = (f"Read in finish order, the chain starts at **{nm(hd)}** ({hd['id']}) in {front_of(hd)}. "
                  + was_due(hd, dd)
                  + (" Grouped by work front, the chain runs through " + '; then '.join(walk) + f", and ends at {ends_of(v)}." if walk else ''))
        pts = []
        s = v['slip']
        if s and s['head'] is not None and s['tail'] is not None:
            odd = ''.join(f" (the exception is {nm(x)} ({x['id']}) at {fl(x['slip_wd'])})" for x in s['odd'][:1]) if s['odd'] else ''
            if s['hi'] <= 0:
                pts.append(f"the chain sits {fl(s['lo'])} to {fl(s['hi'])} wd against its baseline — ahead, not behind{odd}. "
                           "Hold that margin by protecting the head of the chain; the float is only as good as its first link.")
            elif abs(s['tail'] - s['head']) <= 3 and s['hi'] - s['lo'] <= 5:
                pts.append(f"the slip is the same {fl(s['lo'])} to {fl(s['hi'])} wd from the first link to the last{odd}. "
                           "The downstream durations are holding to plan, so the time was lost at the head of the chain, "
                           "not along it — recovery starts there.")
            elif s['tail'] > s['head']:
                pts.append(f"the slip grows along the chain, from {fl(s['head'])} wd at the head to {fl(s['tail'])} at the end{odd}. "
                           "Downstream work is running longer than planned too, so recovery has to look at durations along "
                           "the chain, not only at its start.")
            else:
                pts.append(f"the slip shrinks along the chain, from {fl(s['head'])} wd at the head to {fl(s['tail'])} at the end{odd}: "
                           "the downstream work is already absorbing some of it.")
        ho = v['handoff']
        if ho:
            pts.append(f"the chain hands from {ho['units'][0]} to {ho['units'][-1]} within {ho['parent']} — the same kind of "
                       "work repeating unit by unit. On repetitive work that link is often crew, rig or formwork flow (one set "
                       "moving from unit to unit) rather than hard engineering logic. Where it is, a second set breaks the link. "
                       "Check the relationship and any crew-movement activity codes in P6, and confirm the gain in the What-if "
                       "(F9) before promising any days.")
        else:
            pts.append("look for links on the chain that reflect crew or equipment availability rather than the physics of the "
                       "work — those are the cheapest to break. Confirm any gain in the What-if (F9) before promising days.")
        goal = 'recovery' if fin_tf < 0 else 'holding the date'
        p_pts = (f'Two points matter for {goal}. First, ' + pts[0] + ' Second, ' + pts[1]) if len(pts) == 2 else \
            (f'One point matters for {goal}: ' + pts[0])
        # a readable sample of the chain: head, the first step of each front, the chain's milestones and the finish
        idx = {0}
        pos = {id(x): i for i, x in enumerate(v['chain'])}
        for fr in fronts:
            idx.add(pos[id(fr['rows'][0])])
            idx.add(pos[id(fr['rows'][-1])])
        for x in v['chain_ms']:
            idx.add(pos[id(x)])
        step = max(1, len(v['chain']) // 12)
        for i in range(0, len(v['chain']), step):
            if len(idx) >= 15:
                break
            idx.add(i)
        picked = [v['chain'][i] for i in sorted(idx)][:15]
        rows = [[idn(x), fl(x['tf']), x.get('finish'),
                 f"{x.get('baseline_finish') or '—'} ({fl(x.get('slip_wd'))})"] for x in picked]
        if fin.get('id'):
            rows.append([idn(fin), fl(fin_tf), fin.get('finish'), f"{fin.get('baseline_finish') or '—'} ({fl(fin.get('slip_wd'))})"])
        rest = [x for x in v['chain'] if x not in picked]
        rest_core = [x['tf'] for x in rest if x['tf'] >= fin_tf - 1]
        rest_odd = [x for x in rest if x['tf'] < fin_tf - 1]
        note = (f"{len(rows)} of the {v['length']} chain activities from your file, in chain order."
                + (f" The other {len(rest)} sit at {rng(min(rest_core), max(rest_core))} wd" if rest_core else '')
                + (', plus ' + join_and([f"{idn(x)} at {fl(x['tf'])}" for x in rest_odd[:3]]) if rest_odd else '')
                + ('.' if rest else ''))
        s_drive = K.sec("What's driving the date", p_lead, p_walk, p_pts,
                        table=K.tbl(['Chain step (Activity ID)', 'Total float (wd)', 'Forecast finish', 'Baseline finish (slip, wd)'],
                                    rows, note))
        thinking.append(f"Found the finish milestone {fin.get('id')} ({fl(fin_tf)} wd) and collected the {v['length']}-activity "
                        f"chain within {v.get('band')} wd of its float, grouped into {len(fronts)} work fronts")
    else:
        paras = [K.network_note(N) or (no_chain(v) + " — no open activity sits in the finish milestone's float band.")]
        if crit is not None:
            paras.append(f"From the stored audit: {n0(crit)} activities ({p1(crit_pct)}%) sit at critical float and the "
                         f"driving-path trace counts {n0(dpc)}; critical density is graded {dens_word or 'n/a'}.")
        if drv:
            paras.append(f"On progress, the weighted driver is **{drv['name']}** ({round((drv.get('weight') or 0) * 100)}% of the "
                         f"weight, {drv['actual']}% done vs {drv['planned']}% planned) — the likeliest home of the critical "
                         "work, to be confirmed once the chain is traced.")
        s_drive = K.sec("What's driving the date", *paras)
        thinking.append("Couldn't re-read the file, so worked from the stored float, CPLI and progress figures")

    # ── is it believable? ───────────────────────────────────────────────────────────────────────
    bel = []
    oos, oos_pct, coos = A['oos'], A['oos_pct'], A['coos']
    matches = nok and fin.get('slip_wd') is not None and fin_tf is not None and abs(fin['slip_wd'] + fin_tf) <= 2
    good = (oos_pct is None or oos_pct < 5) and (not nok or matches)
    if cpli is not None and left is not None:
        target = fin.get('baseline_finish') or F.get('baseline_finish')
        if cpli < 1:
            bel.append(f"{'Yes' if good else 'Only partly'}{', as a behind schedule' if behind and good else ''}"
                       + (", and the chain itself is the most trustworthy part of the file" if good and nok and v['started'] == 0 else '')
                       + f". CPLI is {K.ratio(cpli)}: the remaining critical path is {cpl} wd long, but only {left} wd remain"
                       + (f" before the {target} target" if target else '') + f", so the path would have to be squeezed by "
                       f"about {round((1 - left / cpl) * 100)}% ({cpl} wd of work into {left}) to make that date.")
        else:
            bel.append(f"{'Yes' if good else 'Only partly'}. CPLI is {K.ratio(cpli)}: the remaining critical path ({cpl} wd) fits "
                       f"in the time left with {ptf} wd to spare.")
    elif good and (nok or oos is not None):
        bel.append('Broadly yes, on the checks the file allows.')
    sup = []
    if nok and v['started'] == 0:
        sup.append(f"None of the {v['length']} chain activities has started, so there is no progress on it for out-of-sequence "
                   "or progress-override settings to distort. It is plain forward logic from the data date.")
    if oos is not None:
        sup.append(f"Out-of-sequence progress is {'low' if (oos_pct or 0) < 5 else 'material'} across the file ({n0(oos)}, "
                   f"{p1(oos_pct)}%" + (f", with {coos} on the critical path" if coos is not None else '') + ').')
    if nok and fin.get('slip_wd') is not None:
        sup.append(f"The finish's float ({fl(fin_tf)}) matches its slip against baseline ({fl(fin['slip_wd'])}) to the day."
                   if matches else
                   f"The finish's float ({fl(fin_tf)}) and its slip against baseline ({fl(fin['slip_wd'])}) differ — an "
                   "intermediate constraint or a calendar difference is in play; check it in P6.")
    if sup:
        bel.append(('Three things support it. ' if len(sup) == 3 and good else 'What the file shows: ') + ' '.join(sup))
    chk = []
    if lg.get('lagged_count') is not None:
        chk.append(f"lags: {n0(lg['lagged_count'])} of the {n0(lg.get('total_relationships'))} relationships carry a lag "
                   f"({p1(lg.get('lagged_pct'))}%, against the {p1(lg.get('dcma_lag_line') or 5)}% guideline)"
                   + (f". {n0(lg.get('critical_count'))} of those are on critical links" if lg.get('critical_count') else '')
                   + (f" and {n0(lg.get('long_count'))} are longer than {lg.get('long_threshold_days')} wd" if lg.get('long_count') else '')
                   + ", and a lag nobody can justify is hidden duration on the path")
    if A['has'] and F.get('hard_constraints_computable') is False:
        chk.append("hard constraints: this export doesn't let me compute them, so I can't rule out a date holding part of "
                   "the path. The Schedule Audit constraint check settles it")
    if chk:
        bel.append(f"Check {'two things' if len(chk) == 2 else 'this'} before you vouch for it. "
                   + ' '.join(f"The {['first', 'second'][i]} is {c}." if len(chk) == 2 else f"The check is {c}."
                              for i, c in enumerate(chk)))
    if not A['has']:
        bel.append("No audit is stored for this update, so I can't grade the path's quality — CPLI, out-of-sequence "
                   "progress, lags and hard constraints are all unmeasured. Run the Schedule Health Review and the Critical "
                   "Path Analyzer on this update before you vouch for the path.")
    s_bel = K.sec('Is it believable?', *bel)

    # ── longest path vs zero-float set ──────────────────────────────────────────────────────────
    lp = []
    if crit is not None:
        lp.append(f"Don't confuse the two. P6's default 'critical' test is a float cut-off, and here it catches {n0(crit)} "
                  f"activities ({p1(crit_pct)}% of the {n0(total_aud)} audited) at zero or negative float"
                  + (f", {n0(neg)} of them already negative" if neg is not None else '') + ". That's a set of activities, not a line. "
                  + (f"The longest path is the one continuous chain that actually sets {fin.get('finish')}: the {v['length']} "
                     "activities above. " if nok else "The longest path is the one continuous chain that sets the finish — "
                     "re-import the file to trace it. ")
                  + (f"The driving-path trace counts {n0(dpc)} activities. It follows driving logic rather than a float "
                     "threshold, so it overlaps the critical set heavily without being identical to it." if dpc else ''))
        lp.append((f"The practical rule: recover the {v['length']}-activity chain first, because only moves on that chain pull "
                   f"the date in. Use the wider {n0(crit)}" + (f" and {n0(dpc)}" if dpc else '') + " sets to see what will "
                   "start driving once you do.") if nok else
                  "The practical rule: only moves on the continuous chain pull the date in; the wider set shows what will "
                  "start driving once you do.")
    elif nok:
        lp.append(f"The longest path is the one continuous chain that sets {fin.get('finish')}: the {v['length']} activities "
                  "above. No stored critical-float audit exists for this update, so I can't size the wider zero-float set "
                  "against it — run the Schedule Health Review.")
    s_lp = K.sec('Longest path vs the zero-float set', *lp) if lp else None

    # ── parallel / near-critical chains ─────────────────────────────────────────────────────────
    s_par = None
    if nok and ladder:
        g0, ind = ladder[0], v['indep']
        pp = [(f"Critical density grades {dens_word}, with {n0(crit)} activities at critical float, so the network is crowded. " if dens and crit is not None else '')
              + (f"It isn't flat, though: the next paths behind the driver sit at distinct float levels (table below). "
                 if len(ladder) > 1 else "One path sits behind the driver (table below). ")
              + f"The difference between each one's float and the driver's {fl(fin_tf)} is roughly how much you can pull out "
              "of the main chain before that path takes over and the finish stops moving."]
        tail_client = [g for g in ladder if g['client'] and g['gap'] < (d or 0) + 1]
        if g0['fed'] and ind:
            pp.append(f"For recovery, that means the first ~{ind['gap']} wd or so can come from the {v['driver']} chain. "
                      f"Recover them at the head, so {ladder_names(g0, True)} — fed by the same front — move with it. "
                      f"Beyond that point {ladder_names(ind, True)} ({fl(ind['tf'])}) starts to drive"
                      + (', then ' + join_and([ladder_names(g, True) for g in ladder[ladder.index(ind) + 1:ladder.index(ind) + 4]])
                         if len(ladder) > ladder.index(ind) + 1 else '') + '.')
        else:
            pp.append(f"For recovery, that means the first ~{g0['gap']} wd can come from the {v['driver']} chain; beyond that "
                      f"{ladder_names(g0, True)} ({fl(g0['tf'])}) starts to drive"
                      + (', then ' + join_and([ladder_names(g, True) for g in ladder[1:4]]) if len(ladder) > 1 else '') + '.')
        if tail_client:
            pp.append("Late client inputs sit on that ladder, so recovery has to pair the chain with closing them — crashing "
                      "the chain alone past their slack buys nothing.")
        rows = []
        for g in ladder[:8]:
            it = g['items'][0]
            if g['fed']:
                note = (f"Fed by the chain's {g['fed_trade']} front, so recovery at the head moves it too. Recovery only in the "
                        f"tail hands the drive to it after ~{g['gap']} wd")
            elif g['client']:
                note = ('Client input, still open; ' + ('rolled to the data date' if it.get('finish') == dd else f"forecast {it.get('finish')}")
                        + (f" ({fl(it.get('slip_wd'))} wd vs baseline)" if it.get('slip_wd') else ''))
            else:
                t = trade_of(nm(it)) or trade_of(it.get('wbs'))
                note = ('Design/documentation; keep it off the path' if t == 'design' else
                        (f"Rolls up {t} work beyond the chain; the chain's {t} steps are one part of it"
                         if t and t in v['chain_trades'] else
                         f"Forecast {it.get('finish')} ({fl(it.get('slip_wd'))} wd vs baseline)"))
            rows.append([ladder_names(g), fl(g['tf']), f"~{g['gap']}", note])
        s_par = K.sec('Parallel / near-critical chains', *pp,
                      table=K.tbl(['Next path in line (ID)', 'Float (wd)', 'Gap to driver (wd)', 'Note'], rows,
                                  "Float-difference arithmetic on one snapshot, read from the milestone and client-input floats; "
                                  "it assumes each path runs to the same finish. Where paths share work, only a What-if (F9) run "
                                  "gives the real order in which they take over."))
        thinking.append(f"Ranked {len(ladder)} parallel milestone / client-input paths by their float gap to the driver")
    elif dens and crit is not None:
        s_par = K.sec('Parallel / near-critical chains',
                      f"Critical density grades {dens_word}, with {n0(crit)} activities ({p1(crit_pct)}%) at critical float"
                      + (", so the network is crowded and the driver will jump once you compress it." if (crit_pct or 0) > 15 else '.'),
                      "Which paths sit next in line needs the file re-read (or the Critical Path Analyzer); I won't guess them.")
    elif nok and fin_tf >= 0:
        s_par = K.sec('Parallel / near-critical chains',
                      f"The finish carries {fl(fin_tf)} wd, so none of the milestones or client inputs I can see is behind its "
                      "dates. Watch the chain's own float rather than a rival path"
                      + (f" — {n0(crit)} activities at critical float still make the network sensitive." if crit else '.'))
    elif nok:
        s_par = K.sec('Parallel / near-critical chains',
                      "No other milestone or client-input path sits on negative float between the driver and zero, so the "
                      "chain has no close rival in this file — recovery on it moves the finish until it reaches zero float.")

    # ── how much, and how negative ──────────────────────────────────────────────────────────────
    if neg is not None and above is not None and total_aud:
        mid = total_aud - neg - above
        zero = (crit - neg) if (crit is not None and crit >= neg) else None
        lo = min((x['tf'] for x in (N.get('deepest') or []) if x.get('tf') is not None), default=None) if nok else None
        if bipolar:
            lead = (f"**Float is {A['float_grade'] or 'poor'} and bipolar. {n0(neg)} activities ({p1(neg_pct)}%) already have "
                    f"negative float and {n0(above)} ({p1(above_pct)}%) carry more than {thr} wd, so the {p1(avg)}-day average "
                    "describes almost none of them.**")
        else:
            lead = (f"**Float is graded {A['float_grade'] or 'n/a'}: {n0(neg)} activities ({p1(neg_pct)}%) are negative, "
                    f"{n0(above)} ({p1(above_pct)}%) carry more than {thr} wd, and the average is {p1(avg)} wd.**")
        body = (f"Of the {n0(total_aud)} audited activities, {n0(mid)} ({p1(100 * mid / total_aud)}%) sit in the healthy band "
                f"between zero and {thr} wd."
                + (f" The {p1(avg)} wd average comes from averaging the two extremes, so don't quote it as the job's buffer."
                   if bipolar else '')
                + (f" On the negative side float goes as low as {fl(lo)} wd" if lo is not None and lo < 0 else '')
                + (f", and on the positive side as high as {n0(mx)} wd." if mx is not None and lo is not None and lo < 0 else
                   (f" The highest float is {n0(mx)} wd." if mx is not None else '')))
        rows = [['Negative (already behind)', n0(neg), f"{p1(neg_pct)}%"],
                [f"Zero to {thr} wd", n0(mid), f"{p1(100 * mid / total_aud)}%"],
                [f"Above {thr} wd (high float)", n0(above), f"{p1(above_pct)}%"],
                ['Total audited', n0(total_aud), '100%'],
                ['Average / max', f"{p1(avg)} wd / {n0(mx)} wd", '—']]
        s_how = K.sec('How much, and how negative', lead, body,
                      table=K.tbl(['Float band', 'Activities', 'Share'], rows,
                                  f"From your file, with float counted in each activity's own calendar. The {thr}-wd line is the "
                                  f"DCMA high-float test. The zero-to-{thr} band is what remains ({n0(total_aud)} − {n0(neg)} − "
                                  f"{n0(above)})" + (f", and about {n0(zero)} of those sit at exactly zero ({n0(crit)} critical − "
                                                     f"{n0(neg)} negative)." if zero is not None else '.')))
        thinking.append(f"Split float across {n0(total_aud)} audited activities into negative / healthy / high bands")
    else:
        s_how = K.sec('How much, and how negative',
                      "No float audit is stored for this update, so I can't band the float or say how negative it runs. "
                      "Run the Schedule Audit (float and negative-float checks) and ask again"
                      + (f" — for now, the finish itself carries {fl(fin_tf)} wd." if nok else '.'))

    # ── where it's negative ─────────────────────────────────────────────────────────────────────
    s_where = None
    if nok and (neg or fin_tf < 0 or v['client_late_neg']):
        seen, pool = set(), []
        for x in list(N.get('deepest') or []) + v['chain']:
            if x['id'] in seen or is_ms(x) or x['id'] in v['client_ids'] or x.get('tf') is None or x['tf'] >= 0:
                continue
            seen.add(x['id'])
            pool.append(x)
        groups = {}
        for x in pool:
            p = _parts(x)
            groups.setdefault(' / '.join(p[:2]) or '(no WBS)', []).append(x)
        glist = []
        for key, xs in groups.items():
            p2 = [_parts(x) for x in xs]
            mids = [p[2] for p in p2 if len(p) > 2]
            subs = []
            for s_ in (mids if len(set(mids)) > 1 else [p[-1] for p in p2 if p]):
                if s_ not in subs:
                    subs.append(s_)
            label = (key.split(' / ')[-1]) + (f" ({', '.join(subs[:4])})" if subs else '')
            tf_ = [x['tf'] for x in xs]
            glist.append((min(tf_), label, max(tf_), len(xs), all((x.get('pct') or 0) == 0 for x in xs)))
        glist.sort()
        cl = v['client_late_neg']
        n_groups = len(glist) + (1 if cl else 0)
        bits = [f"{i + 1}) {lab}, at {rng(lo_, hi_)}" + (' — none of it started' if unst else '')
                for i, (lo_, lab, hi_, _n, unst) in enumerate(glist[:3])]
        if cl:
            bits.append(f"{len(bits) + 1}) the late client inputs, at {rng(min(x['tf'] for x in cl), max(x['tf'] for x in cl))}")
        sect = v['sectional']
        negs = sorted([m for m in sect if m['tf'] < 0], key=lambda m: m['tf'])
        poss = sorted([m for m in sect if m['tf'] > 0], key=lambda m: -m['tf'])
        ms_line = ''
        if negs or poss:
            ms_line = (" The sectional milestones tell the same story."
                       + (' Negative: ' + join_and([nm(m) + ' (' + fl(m['tf']) + ')' for m in negs[:8]]) + '.' if negs else '')
                       + (' Still positive: ' + join_and([nm(m) + ' (' + fl(m['tf']) + ')' for m in poss[:5]]) + '.' if poss else ''))
        w1 = (("It isn't scattered. " if n_groups <= 4 else '') + f"It sits in {n_groups} group{'s' if n_groups != 1 else ''}"
              + (", and they line up with the finish chain" + (" and the late client inputs" if cl else '') if nok else '')
              + '. ' + '. '.join(bits) + '.' + ms_line)
        cau = []
        if v['deeper']:
            cau.append(f"{len(v['deeper'])} item{'s' if len(v['deeper']) != 1 else ''} ("
                       + ', '.join(fl(x['tf']) for x in v['deeper'][:4]) + ") have "
                       + ('more negative float' if fin_tf < 0 else 'less float') + f" than the finish's "
                       f"{fl(fin_tf)}. That means something downstream of them is tighter than {fin.get('finish')}: an "
                       f"intermediate date, a lag, or a different calendar. Check those in P6 before using "
                       f"{fl(v['deeper'][0]['tf'])} as the headline.")
        mism = sorted([m for m in negs if (m.get('slip_wd') or 0) > 0 and m['slip_wd'] + m['tf'] >= 15],
                      key=lambda m: -(m['slip_wd'] + m['tf']))
        if mism:
            m = mism[0]
            cau.append(f"a milestone's float reflects its own link to the finish. {nm(m)} shows {fl(m['tf'])} float against a "
                       f"{fl(m['slip_wd'])} slip, so judge how critical that front is from its activities, not from that milestone.")
        tr = F.get('trend')
        spread = ("Whether negative float is spreading or being contained week to week needs a prior update in Update vs "
                  "Update; this single snapshot can't show it." if not (tr and tr.get('prev_delay') is not None) else
                  f"Since the previous update the finish moved from {K.signed(tr['prev_delay'])} to {K.signed(d)}; Update vs "
                  "Update shows which chains lost the float.")
        w2 = ((f"Two cautions on reading these numbers. First, {cau[0]} Second, {cau[1]} " if len(cau) == 2 else
               (f"One caution on reading these numbers: {cau[0]} " if cau else '')) + spread)
        rows = []
        for x in [y for y in (N.get('deepest') or []) if y.get('tf') is not None and y['tf'] < 0][:5]:
            rows.append([front_of(x), idn(x), fl(x['tf']), status(x, dd)])
        if cl:
            a, b = cl[0], cl[-1]
            rows.append(['Client inputs', f"{idn(a)} down to {idn(b)}" if a is not b else idn(a),
                         rng(min(x['tf'] for x in cl), max(x['tf'] for x in cl)),
                         f"{len(cl)} item{'s' if len(cl) != 1 else ''}, all still open"])
        s_where = K.sec("Where it's negative", w1, w2,
                        table=K.tbl(['Where', 'Most negative items (ID)', 'Float (wd)', 'Status'], rows,
                                    f"From your file at the {dd} data date."))

    # ── can I free up crews? ────────────────────────────────────────────────────────────────────
    s_crew = None
    if nok and fin_tf >= 0:
        don = v['donors']
        s_crew = K.sec('Can I free up crews?',
                       f"You don't need to pull crews onto the chain: the finish carries {fl(fin_tf)} wd of float. "
                       + ("If a front does slip, the spare room sits in " + join_and([f"{nm(m)} ({fl(m['tf'])})" for m in don[:3]])
                          + '. ' if don else '')
                       + "Keep the float by holding the chain's head to its forecast, and prove any crew move in the What-if "
                       "(F9) before making it.")
    elif nok:
        don = v['donors']
        if don:
            ht = v['fronts'][0]['trade']
            same = [m for m in don if m['_trade'] == ht]
            other = [m for m in don if m['_trade'] != ht]
            d0 = date(dd)

            def free(m):
                f = date(m.get('finish'))
                if not (f and d0):
                    return ''
                wk = round((f - d0).days / 7)
                return (f" and is due {m['finish']}, so those crews come free " +
                        ('about now' if wk <= 0 else f"in about {wk} week{'s' if wk != 1 else ''}"))
            c1 = ("Yes, and the file shows where they can come from. "
                  + (f"The positive float is in other {ht} fronts — the same trade the driver needs. " if same and ht else '')
                  + (f"{idn(same[0])} has {fl(same[0]['tf'])} wd float{free(same[0])}. " if same else '')
                  + (join_and([f"{idn(m)} has {fl(m['tf'])}" for m in same[1:4]]) + '. ' if len(same) > 1 else '')
                  + (join_and([f"{idn(m)} ({fl(m['tf'])})" for m in other[:2]])
                     + f" {'is' if len(other[:2]) == 1 else 'are'} the natural source later, for the chain's "
                     + join_and(sorted({m['_trade'] for m in other[:2]})) + ' work. ' if other else '')
                  + f"All of these should go to the {v['driver']} chain.")
            risk = [m for m in don if m['_at_risk']]
            chk = ["this file carries no crew or resource loading in what I read, so it can't show crew sizes, rigs, or "
                   "whether those fronts use the same subcontractor. Confirm that with site"]
            if risk:
                chk.append("keep the fronts you take crews from in positive float. " + join_and(
                    [f"{nm(o)} is already at {fl(o['tf'])}" for m in risk[:2] for o in m['_at_risk'][:1]])
                           + ", so don't strip " + join_and([nm(m) for m in risk[:2]]) + " hard enough to push them further")
            if mx is not None and don[0]['tf'] > mx:
                chk.append(f"the {fl(don[0]['tf'])} is a milestone's float; the {n0(mx)}-wd maximum above is the audited-activity "
                           "figure, so read the milestone number as 'this front has ample room', not as a precise activity float")
            if A['dangling']:
                chk.append(f"the {n0(A['dangling'])} dangling activities can make float look higher than it is, so check the "
                           "logic in the fronts you take crews from")
            chk.append("only P6's own recalculation gives the day-gain of each move. Run it through the What-if (F9)")
            words = ['one', 'two', 'three', 'four', 'five']
            c2 = (f"Check {words[len(chk) - 1]} things before anyone moves. "
                  + ' '.join(f"({i + 1}) {c[0].upper() + c[1:]}." for i, c in enumerate(chk)))
            s_crew = K.sec('Can I free up crews?', c1, c2)
            thinking.append(f"Looked for crew sources in {len(v['sectional'])} sectional milestones: {len(don)} "
                            f"{'has' if len(don) == 1 else 'have'} ≥{DONOR_TF} wd float in the chain's trades")
        else:
            s_crew = K.sec('Can I free up crews?',
                           f"Not from the sectional milestones: none in the chain's trades ({join_and(v['chain_trades']) or 'n/a'}) "
                           f"carries {DONOR_TF}+ wd of float. "
                           + (f"{n0(above)} activities do carry more than {thr} wd, so the Schedule Audit's high-float list "
                              "shows which fronts might release people. " if above else '')
                           + "The file carries no resource loading in what I read, so confirm any move with site and "
                           "prove the gain in the What-if (F9).")
    elif above:
        s_crew = K.sec('Can I free up crews?',
                       f"Possibly: {n0(above)} activities carry more than {thr} wd of float (max {n0(mx)}). Which fronts they "
                       "sit in, and whether they share a trade with the driving chain, needs the file re-read or the Schedule "
                       "Audit's high-float list. Crew sizes aren't in the file — confirm with site and prove any gain in the "
                       "What-if (F9).")

    # ── measured / actions / evidence ───────────────────────────────────────────────────────────
    measured = ((f"The finish chain is every open activity whose total float sits within {v.get('band')} wd of the finish "
                 f"milestone's ({fin.get('name')}, {fl(fin_tf)} wd), in finish order: {v['length']} activities, each with total "
                 "float, forecast and baseline finish from your file. Total float is P6's own figure, in each activity's "
                 "calendar. " if nok else (K.network_note(N) + ' ' if not v['ok'] else ''))
                + (f"CPLI = (critical-path length + project total float) ÷ critical-path length = ({cpl} {'−' if ptf < 0 else '+'} "
                   f"{abs(ptf)}) ÷ {cpl} = {K.ratio(cpli)}. " if cpli is not None and left is not None else '')
                + (f"Critical density counts activities at critical float ({n0(crit)} of the {n0(total_aud)} audited, "
                   f"{p1(crit_pct)}%); the driving-path trace ({n0(dpc)}) follows driving logic rather than a float cut-off. "
                   if crit is not None else '')
                + (f"Float bands: {n0(neg)} negative, {n0(above)} above the {thr}-wd DCMA high-float line, the rest in between. "
                   if neg is not None and above is not None else '')
                + (f"Each parallel-path gap is that path's float minus the driver's {fl(fin_tf)} — an approximation from one "
                   "snapshot; the real takeover order and each crew move's gain come from a What-if (F9). " if ladder else '')
                + "Not in this file: " + join_and([x for x in ['hard constraints (not computable)'
                                                               if A['has'] and F.get('hard_constraints_computable') is False else '',
                                                               'resource loading',
                                                               'an earlier update to show how float is moving'
                                                               if not (F.get('trend') or {}).get('prev_delay') else '']]) + '.')
    hd = v.get('head') if nok else None
    g0 = ladder[0] if ladder else None
    ind = v.get('indep') if nok else None
    actions = [
        (f"Put the {v['length']}-activity chain on one page and review it with site this week. Start with {idn(hd)}"
         + (f" (due {hd['baseline_finish']}) — why it hasn't started and what start date site will commit to." if hd.get('pct') == 0 and hd.get('baseline_finish')
            else " — what it needs to hold its forecast.")) if hd else
        'Re-import the schedule file so the driving chain can be traced activity by activity.',
        (f"Test a second crew, rig or formwork set on the {v['handoff']['units'][0]} → {v['handoff']['units'][-1]} links in the "
         "What-if (F9). Repeating unit-to-unit work is often crew flow, which is the cheapest logic to break.")
        if nok and v['handoff'] else '',
        ("Move crews onto the chain from " + join_and([f"{nm(m)} ({fl(m['tf'])})" for m in v['donors'][:3]])
         + ". Confirm crews and subcontractor with site, since the file isn't resource-loaded"
         + (", and don't push " + join_and([f"{nm(o)} ({fl(o['tf'])})" for m in v['donors'][:3] for o in m['_at_risk'][:1]]) + ' further negative.'
            if any(m['_at_risk'] for m in v['donors'][:3]) else '.')) if nok and v['donors'] and fin_tf < 0 else '',
        (f"Plan recovery in tiers. Past ~{(ind or g0)['gap']} wd on the chain, {ladder_names(ind or g0, True)} "
         f"({fl((ind or g0)['tf'])}) takes over"
         + (", so chase " + join_and([nm(x) for x in v['client_late_neg'][:4]]) + ' now, in parallel.' if v['client_late_neg'] else '.'))
        if nok and g0 else '',
        ("Check the items with " + ('more negative float' if fin_tf < 0 else 'less float') + " than the finish ("
         + ', '.join(x['id'] + ' ' + fl(x['tf']) for x in v['deeper'][:3])
         + ") for a constraint, lag or calendar, and run the Schedule Audit constraint check.") if nok and v['deeper'] else '',
        (f"Review the {n0(lg.get('critical_count'))} lags on critical links and justify the {n0(lg.get('long_count'))} longer "
         f"than {lg.get('long_threshold_days')} wd. A lag nobody can justify is a logic error; one that can be justified should "
         "be documented.") if lg.get('critical_count') and lg.get('long_count') else '',
        (f"Clean up the {n0(A['dangling'])} dangling activities so the float you're drawing on is real, and load an "
         "earlier update into Update vs Update to see whether negative float is spreading.") if A['dangling'] else
        'Load an earlier update into Update vs Update to see how float is moving between updates.',
        '' if A['has'] else 'Run the Schedule Audit on this update so float health, CPLI and lags can be graded.',
    ]
    evidence = [
        K.ev('Finish chain', f"{v['length']} activities, {'all 0%' if v['started'] == 0 else str(v['started']) + ' started'}, "
                             f"{rng(*v['core'])} wd") if nok else None,
        K.ev('Chain start', f"{idn(hd)}: " + (f"due {hd['baseline_finish']}" if hd.get('baseline_finish') else f"{hd.get('pct')}%")) if hd else None,
        K.ev('Chain end', f"{fin.get('id')}: {fin.get('finish')}, {fl(fin_tf)}") if nok else None,
        K.ev('CPLI', f"{K.ratio(cpli)} ({cpl}-wd path, {left} wd left)") if cpli is not None and left is not None else None,
        K.ev('Critical float', f"{n0(crit)} ({p1(crit_pct)}%), {dens}") if crit is not None else None,
        K.ev('Driving-path trace', f"{n0(dpc)} activities") if dpc else None,
        K.ev('Negative float', f"{n0(neg)} ({p1(neg_pct)}%)") if neg is not None else None,
        K.ev('Most negative', f"{N['deepest'][0]['id']} at {fl(N['deepest'][0]['tf'])} wd") if nok and N.get('deepest') else None,
        K.ev(f"High float > {thr} wd", f"{n0(above)} ({p1(above_pct)}%)") if above is not None and thr else None,
        K.ev('Avg / max float', f"{p1(avg)} / {n0(mx)} wd") if avg is not None else None,
        K.ev('Next paths', ', '.join(f"{fl(g['tf'])} ({ladder_names(g, True)})" for g in ladder[:3])) if ladder else None,
        K.ev('Crew sources (float)', ', '.join(f"{nm(m)} {fl(m['tf'])}" for m in v['donors'][:3])) if nok and v['donors'] else None,
        K.ev('Lags on critical links', f"{n0(lg['critical_count'])} of {n0(lg.get('lagged_count'))}") if lg.get('critical_count') else None,
        K.ev('Delay', K.signed(d)) if not nok else None,
        K.ev('Resource loading', 'not in what I read: crew moves need site input'),
    ]
    a = K.A2(head, [s_drive, s_bel, s_lp, s_par, s_how, s_where, s_crew], pills=pills, measured=measured,
             actions=actions, evidence=evidence,
             drilldowns=[K.drill('q05', f"How do I recover the ~{round(d)} days?") if behind else
                         K.drill('q05', 'How would I test a change before making it?'),
                         K.drill('q03', f"Is the {round(d)}-day delay genuine, and who owns it?") if behind else None,
                         K.drill('q13', 'Do the late client inputs on negative float support an EOT?')
                         if nok and v['client_late_neg'] else None,
                         K.drill('q06', 'Which logic problems (lags, dangling, constraints) should I fix first?'),
                         K.drill('q09', 'Can crews move, and is the delay resource-driven?')])
    a['thinking'] = thinking[:4]
    return a
