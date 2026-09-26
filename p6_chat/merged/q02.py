"""q02 — When will we finish, will we hit the dates — and what's slipping right now?

Covers: the forecast finish and how late (P6's network date, the float cross-check, CPLI, and why an
SPI projection is not the date), the driving path, every key-date / sectional milestone with its slip
and float, the contract & handover verdict with its honest caveat, late client inputs, quiet slips
due by the data date, what's blocking imminent work, and a 3-week driving-path look-ahead — derived
from F / N for ANY project (no project nouns, ids or dates are hard-coded).

The small helpers at the top (dates, key dates, chain fronts, client inputs) are also used by q03.
"""
import re
from collections import Counter
from datetime import datetime, timedelta

from . import _kit2 as K

try:                                    # the same words the network read uses to spot employer inputs
    from ..analysis import CLIENT_WORDS
except Exception:                       # pragma: no cover - analysis always ships with the chat
    CLIENT_WORDS = ('client', 'employer', 'owner', 'free issue', 'free-issue', 'furnished by', 'by client')

FMT = '%d-%b-%Y'
HANDOVER_WORDS = ('handover', 'hand over', 'hand-over', 'taking over', 'take over', 'practical completion',
                  'substantial completion')
# words too common in activity / WBS names to link two things on their own
STOP = {'the', 'of', 'and', 'for', 'to', 'from', 'in', 'on', 'at', 'by', 'a', 'an', 'with', 'all', 'get', 'before',
        'after', 'works', 'work', 'completion', 'complete', 'completed', 'milestone', 'finish', 'finalize', 'final',
        'start', 'phase', 'i', 'ii', 'iii', 'iv', 'package', 'total', 'project', 'scope', 'general'}
WEAK = {'design', 'engineering', 'construction', 'procurement', 'installation', 'installations', 'delivery',
        'approval', 'submittal', 'client', 'employer', 'owner', 'consultant'}


# ── small, None-safe helpers ────────────────────────────────────────────────────────────────────

def dt(s):
    """'19-Jul-2026' (or ISO) -> datetime, else None."""
    if not s:
        return None
    if isinstance(s, datetime):
        return s
    for f in (FMT, '%Y-%m-%d', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(str(s)[:19] if f != FMT else str(s), f)
        except ValueError:
            continue
    return None


def ds(d):
    return d.strftime(FMT) if d else None


def sg(n):
    """Signed whole number: +159 / -60 / 0."""
    if n is None:
        return '—'
    n = int(round(n))
    return f"{n:+d}" if n else '0'


def slip(n):
    return '—' if n is None else f"{sg(n)} wd"


def rng(vals, unit=''):
    """Signed range of the values, e.g. '+39 to +122 wd' / '-3 to -48'."""
    vals = [v for v in vals if v is not None]
    if not vals:
        return '—'
    lo, hi = min(vals), max(vals)
    if lo == hi:
        return sg(lo) + unit
    # floats read deepest last (-3 to -48); slips read smallest first (+39 to +122)
    a, b = (hi, lo) if hi <= 0 else (lo, hi)
    return f"{sg(a)} to {sg(b)}{unit}"


def clean(name):
    return re.sub(r'\s+', ' ', str(name or '')).strip()


def short(name, n=46):
    """An activity name cut at a word boundary for dense table cells."""
    s = clean(name)
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(' ', 1)[0].rstrip(' ,;:-&')
    return (cut or s[:n]) + '…'


def plural(n, one, many=None):
    return one if n == 1 else (many or one + 's')


def names(rows, limit=5):
    rows = list(rows)
    if not rows:
        return ''
    if len(rows) > limit:
        return f"{len(rows)} of them, from {clean(rows[0]['name'])} to {clean(rows[-1]['name'])},"
    out = [clean(r['name']) for r in rows]
    return out[0] if len(out) == 1 else ', '.join(out[:-1]) + ' and ' + out[-1]


def by_date_ids(rows):
    """'A.1 / 2 on 01-Aug-2026 and A.3 on 01-Oct-2026' — ids grouped by their forecast date."""
    groups = {}
    for x in rows:
        groups.setdefault(x.get('finish'), []).append(x['id'])
    order = sorted(groups, key=lambda f: dt(f) or datetime.max)
    return ' and '.join(f"{compact_ids(groups[f])} on {f}" for f in order)


def kpis(F, mod):
    return (((F.get('audit') or {}).get(mod) or {}).get('kpis')) or {}


def is_ms(x):
    return 'Milestone' in (x.get('type') or '')


def parts(x):
    return [p for p in (x.get('wbs') or '').split(' / ') if p]


def toks(s):
    return set(re.findall(r'[a-z0-9]+', str(s or '').lower()))


def compact_ids(ids):
    """['A.B.1010', 'A.B.1020'] -> 'A.B.1010 / 1020' when they share a prefix."""
    ids = sorted(ids)
    if len(ids) < 2:
        return ' / '.join(ids)
    pre = ids[0].rsplit('.', 1)[0] + '.' if '.' in ids[0] else ''
    if pre and all(i.startswith(pre) for i in ids):
        return ids[0] + ' / ' + ' / '.join(i[len(pre):] for i in ids[1:])
    return ' / '.join(ids)


def span(a, b):
    """'19–26 Jul' / '26 Jul–02 Aug'."""
    if a.month == b.month and a.year == b.year:
        return f"{a:%d}–{b:%d} {b:%b}"
    return f"{a:%d %b}–{b:%d %b}"


# ── position of the finish ───────────────────────────────────────────────────────────────────────

def position(F, N):
    """The finish as the file states it: milestone, forecast, baseline, delay, float, data date."""
    nok = bool(N and N.get('ok'))
    fin = ((N or {}).get('finish_milestone') if nok else None) or {}
    ck = kpis(F, 'cpli')
    d = F.get('delay_days')
    if d is None and fin.get('slip_wd') is not None:
        d = fin['slip_wd']
    fc = fin.get('finish') or F.get('forecast_finish') or ds(dt(ck.get('finish_date')))
    bl = fin.get('baseline_finish') or F.get('baseline_finish')
    tf = fin.get('tf')
    tf_src = 'milestone'
    if tf is None and ck.get('project_total_float_days') is not None:
        tf, tf_src = ck.get('project_total_float_days'), 'audit'
    dd = F.get('data_date') or ((N or {}).get('data_date') if nok else None)
    fid = fin.get('id')
    return {'nok': nok, 'fin': fin, 'd': d, 'fc': fc, 'bl': bl, 'tf': tf, 'tf_src': tf_src, 'dd': dd,
            'dd_dt': dt(dd), 'fid': fid, 'fname': clean(fin.get('name')) or 'the finish milestone',
            'flabel': (f"{clean(fin.get('name'))} ({fid})" if fid else 'the finish'),
            'behind': (d or 0) > 0, 'ahead': (d or 0) < 0,
            'cal_days': ((dt(fc) - dt(bl)).days if dt(fc) and dt(bl) else None)}


def is_client(x, cids=()):
    if x.get('id') in cids:
        return True
    t = ((x.get('wbs') or '') + ' ' + (x.get('name') or '')).lower()
    return any(w in t for w in CLIENT_WORDS)


def client_inputs(N):
    """(all, open, late_open, late_done, other_open) from the network read."""
    if not (N and N.get('ok')):
        return [], [], [], [], []
    allc = list(N.get('client_inputs') or [])
    opn = [x for x in allc if not x.get('done')]
    late_open = list(N.get('client_inputs_late_open') or [])
    late_done = list(N.get('client_inputs_late_done') or [])
    lo_ids = {x['id'] for x in late_open}
    other = [x for x in opn if x['id'] not in lo_ids]
    return allc, opn, late_open, late_done, other


def key_dates(N, P):
    """Open key-date milestones (not client inputs, not the finish itself), in forecast order;
    returns (keys, late)."""
    if not P['nok']:
        return [], []
    cids = {x['id'] for x in (N.get('client_inputs') or [])}
    seen, rows = set(), []
    for x in (N.get('milestones') or []) + (N.get('milestones_open_late') or []):
        if (x['id'] in seen or x.get('done') or x['id'] == P['fid'] or not x.get('baseline_finish')
                or is_client(x, cids)):
            continue
        seen.add(x['id'])
        rows.append(x)
    rows.sort(key=lambda x: dt(x.get('finish')) or datetime.max)
    return rows, [x for x in rows if (x.get('slip_wd') or 0) > 0]


def _front_label(x, common):
    rem = [p for p in parts(x) if p not in common] or parts(x)[-1:] or ['(no WBS)']
    lab = rem[-1]
    if len(lab) < 12 and len(rem) > 1:                          # a short area name reads better with its parent
        lab = rem[-2] + ' / ' + lab
    return lab


def chain_fronts(chain):
    """Group the chain's activities into work fronts: ([(label, count, not_started)], common_parts, {id: label}).
    WBS levels shared by almost every link are reported once (common_parts), not per front."""
    acts = [x for x in chain if not is_ms(x)]
    if not acts:
        return [], [], {}
    cnt = Counter(p for x in acts for p in set(parts(x)))
    common = [p for p, c in cnt.items() if c >= 0.8 * len(acts)]
    order = []
    for x in acts:                                              # keep WBS order for the common parts
        for p in parts(x):
            if p in common and p not in order:
                order.append(p)
    labmap = {x['id']: _front_label(x, common) for x in acts}
    groups = {}
    for x in acts:
        g = groups.setdefault(labmap[x['id']], [0, 0])
        g[0] += 1
        g[1] += 1 if (x.get('pct') or 0) == 0 else 0
    return [(k, v[0], v[1]) for k, v in groups.items()], order, labmap


def spine(chain, fin, limit=15):
    """A readable subset of the chain: its head, the first link of each front, anything deeper than the
    finish, the last links — evenly thinned to `limit` rows, ending on the finish milestone."""
    n = len(chain)
    if not n:
        return []
    ftf = fin.get('tf')
    if n + 1 <= limit:
        idx = list(range(n))
    else:
        keep, prev = {0, n - 1, n - 2}, None
        for i, x in enumerate(chain):
            f = ' / '.join(parts(x)[-2:])
            if f != prev:
                keep.add(i)
                prev = f
            if ftf is not None and x.get('tf') is not None and x['tf'] < ftf - 1:
                keep.add(i)
        idx = sorted(keep)
        room = limit - 1
        if len(idx) > room:
            must = [0, n - 1]
            rest = [i for i in idx if i not in must]
            take = room - len(must)
            step = len(rest) / float(take)
            idx = sorted(set(must) | {rest[int(k * step)] for k in range(take)})
    rows = [chain[i] for i in idx]
    if fin and fin.get('id') and fin['id'] not in {r['id'] for r in rows}:
        rows.append(fin)
    return rows


def token_link(a_name, candidates):
    """The candidate whose name shares the most distinctive words with a_name (>= 1 distinctive word)."""
    ta = toks(a_name) - STOP
    best, score = None, 0
    for c in candidates:
        tc = toks(c.get('name')) - STOP
        dist = (ta & tc) - WEAK
        if not dist:
            continue
        s = 10 * len(dist) + len((ta & tc) & WEAK)
        if s > score:
            best, score = c, s
    return best


def ms_group_match(ms_name, row):
    """True when every distinctive word of a sectional milestone's name is in an activity's WBS + name
    (e.g. a '<area> <trade> completion' milestone and that area's trade activities)."""
    # single letters stay: they are area designators ('Phase C', 'Zone B', 'Block A')
    t = {w for w in toks(ms_name) if w not in STOP or len(w) == 1} - {'as', 'built'}
    if not t:
        return False
    return t <= toks((row.get('wbs') or '') + ' ' + (row.get('name') or ''))


def untied_sectional(keys, chain):
    """A sectional milestone that forecasts EARLIER than chain work of the same area/trade (and with less
    negative float) — it may not be tied to its last activities. Returns (milestone, latest_row) or None."""
    for m in keys:
        fm = dt(m.get('finish'))
        if not fm or m.get('tf') is None:
            continue
        later = [x for x in chain if not is_ms(x) and ms_group_match(m['name'], x) and dt(x.get('finish'))
                 and dt(x['finish']) > fm and x.get('tf') is not None and x['tf'] < m['tf']]
        if later:
            return m, max(later, key=lambda x: dt(x['finish']))
    return None


def audit_total(F):
    for mod in ('negative_float', 'float', 'out_of_sequence', 'dangling', 'open_ends'):
        t = kpis(F, mod).get('total_activities')
        if t:
            return t
    return F.get('activity_count')


def oos_concentration(F):
    """'the Design package (19 of 23)' from the stored out-of-sequence conclusion, or ''."""
    txt = kpis(F, 'out_of_sequence').get('executive_conclusion') or ''
    m = re.search(r'concentrated in the (.+?) package \((\d+) of (\d+)', txt)
    return (m.group(1), int(m.group(2)), int(m.group(3))) if m else None


# ── the answer ──────────────────────────────────────────────────────────────────────────────────

def build(F, N, role):
    P = position(F, N)
    nok, fin, d, fc, bl, tf, dd = P['nok'], P['fin'], P['d'], P['fc'], P['bl'], P['tf'], P['dd']
    behind, ahead = P['behind'], P['ahead']
    spi = F.get('spi')
    drv = K.main_driver(F)
    ck = kpis(F, 'cpli')
    hk = kpis(F, 'hard_constraints')
    chain = list(N.get('chain') or []) if nok else []
    head = chain[0] if chain else None
    keys, keys_late = key_dates(N, P)
    allc, opn, late_open, late_done, other_open = client_inputs(N)
    deepest = list(N.get('deepest') or []) if nok else []
    chain_ids = {x['id'] for x in chain} | ({P['fid']} if P['fid'] else set())
    off_deep = [x for x in deepest if x['id'] not in chain_ids and tf is not None and x.get('tf') is not None
                and x['tf'] < tf and not is_client(x)]
    neg, negp = F.get('neg_float_count'), F.get('neg_float_pct')
    cm = hk.get('contract_milestones')
    hc_known = bool((F.get('audit') or {}).get('hard_constraints'))     # the contract-milestone check ran
    no_contract = hc_known and not cm
    thinking = []

    # ── verdict ─────────────────────────────────────────────────────────────────────────────────
    if d is None:
        head_line = (f"The finish is forecast for {fc}" if fc else "The forecast finish can't be read from this file") + \
                    f"; its slip against baseline isn't derivable (SPI {K.ratio(spi)})."
    elif behind:
        head_line = (f"{P['fname']} is forecast for {fc}, {K.wd(d)} past the {bl} baseline" if fc and bl else
                     f"The finish is about {K.wd(d)} (~{K.weeks(d)}) behind its baseline" + (f", forecast {fc}" if fc else ''))
        if keys:
            head_line += (f", and all {len(keys)} key dates are late" if len(keys_late) == len(keys) else
                          f", and {len(keys_late)} of {len(keys)} key dates are late")
        head_line += '.'
        focus = []
        if head and not head.get('done'):
            focus.append(("starting " if (head.get('pct') or 0) == 0 else "driving on ") + f"{clean(head['name'])} ({head['id']})")
        if late_open:
            focus.append(f"closing {len(late_open)} overdue client {plural(len(late_open), 'input')}")
        if focus:
            head_line += " The next three weeks turn on " + ' and '.join(focus) + '.'
        elif not nok:
            head_line += " I couldn't re-read the file this time, so milestone and look-ahead detail is limited."
    elif ahead:
        head_line = (f"Forecast finish {fc}, {K.wd(d)} ahead of the {bl} baseline" if fc and bl else
                     f"The finish is about {K.wd(d)} ahead of its baseline") + f" (SPI {K.ratio(spi)})."
        if keys_late:
            head_line += f" {len(keys_late)} of {len(keys)} key dates still sit behind their own baseline dates."
    else:
        head_line = f"The finish is on its baseline date{(' (' + fc + ')') if fc else ''} (SPI {K.ratio(spi)})."

    pills = [K.pill(f"Finish {fc} · {slip(d)}" if fc and d is not None else (K.signed(d) if d is not None else None),
                    'danger' if behind else ('success' if d is not None else 'neutral')),
             K.pill(f"{len(keys_late)} of {len(keys)} key dates late vs baseline", 'warning' if keys_late else 'success')
             if keys else None,
             K.pill(f"{len(late_open)} client {plural(len(late_open), 'input')} overdue"
                    + (' · all negative float' if late_open and all((x.get('tf') or 0) < 0 for x in late_open) else ''),
                    'danger') if late_open else None,
             K.pill('contract dates not in the file', 'neutral') if no_contract else None,
             K.pill(f"{neg:,} on negative float ({K.pct(negp, 1)})", 'danger') if neg else None,
             K.pill(f"{F.get('oos_count')} out-of-sequence ({F.get('critical_oos') or 0} critical)"
                    + (f" · {F.get('dangling_count')} dangling" if F.get('dangling_count') is not None else ''),
                    'warning' if (F.get('critical_oos') or 0) > 0 else 'neutral') if F.get('oos_count') is not None else None,
             K.pill(f"SPI {K.ratio(spi)} · {K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}",
                    'success' if (spi or 0) >= 1 else ('warning' if (spi or 0) >= 0.9 else 'danger'))
             if not nok and spi is not None else None]

    # ── 1. forecast finish and how late ─────────────────────────────────────────────────────────
    fp = []
    if d is not None and fc and bl:
        line = (f"**{P['flabel'][0].upper() + P['flabel'][1:]} is forecast for {fc}: {K.wd(d)}, about {K.weeks(d)}, "
                + ('past' if behind else 'ahead of') + f" its {bl} baseline." if d else
                f"**{P['flabel'][0].upper() + P['flabel'][1:]} is forecast for {fc}, on its baseline date.")
    elif d is not None:
        line = (f"**The finish is {K.wd(d)}, about {K.weeks(d)}, " + ('behind' if behind else 'ahead of') +
                " its baseline" + (f" (forecast {fc})" if fc else '') + '.') if d else "**The finish is on its baseline date."
    else:
        line = "**The finish slip against baseline can't be read from this update."
    if keys:
        sl = [x['slip_wd'] for x in keys_late]
        if len(keys_late) == len(keys):
            line += f" All {len(keys)} key-date milestones are late against baseline too, by {min(sl)} to {max(sl)} working days."
        elif keys_late:
            line += (f" {len(keys_late)} of the {len(keys)} other key-date milestones are late against baseline too, "
                     f"by {min(sl)} to {max(sl)} working days.")
        else:
            line += " The other key-date milestones are holding their baseline dates."
    if no_contract:
        line += (" This file can't say whether any of that breaches the contract, because it carries no contract dates."
                 if behind else " This file carries no contract dates, so that is measured against baseline only.")
    elif not hc_known:
        line += " No contract-milestone check is stored for this update, so the contract dates aren't tested here."
    fp.append(line + '**')
    if nok and fin and fc:
        seen_sd, same_day = set(), []
        for x in chain + keys:
            if x['id'] != P['fid'] and x['id'] not in seen_sd and is_ms(x) and x.get('finish') == fc and x.get('tf') == tf:
                seen_sd.add(x['id'])
                same_day.append(x)
        s = f"{fc} is P6's own date from the {dd} update."
        if same_day:
            s += (f" {P['fid']} and " + ', '.join(f"{clean(x['name'])} ({x['id']})" for x in same_day[:2]) +
                  f" {'both' if len(same_day) == 1 else 'all'} land there with {sg(tf)} wd total float.")
        elif tf is not None:
            s += f" {P['fid']} carries {sg(tf)} wd total float."
        if behind and tf is not None and abs(tf + d) <= 1:
            s += (f" Float equal to the slip tells me the file still measures against a {bl} finish, so the negative "
                  "float is the real gap to that date and not a modelling quirk.")
        elif behind and tf is not None:
            s += (f" Float ({sg(tf)}) and slip ({sg(d)}) don't match, which usually means a deadline, a constraint or a "
                  "different calendar sets the float — check it in P6 before quoting either figure.")
        if neg:
            s += f" {neg:,} activities ({K.pct(negp, 1)}) now sit below zero against it."
        fp.append(s)
    elif tf is not None and d is not None:
        fp.append(f"The stored critical-path check reads {sg(tf)} wd total float at the finish"
                  + (", matching the slip — the negative float is the real gap to the baseline date." if behind and abs(tf + d) <= 1 else '.')
                  + (f" {neg:,} activities ({K.pct(negp, 1)}) sit below zero." if neg else ''))
    if ck.get('cpli_computable') and ck.get('cpli') is not None:
        c = (f"CPLI (critical path length index: how achievable the target is at the current path length) is "
             f"{K.ratio(ck['cpli'])} against a {K.ratio(ck.get('target') or 0.95)} target.")
        cpl, ptf = ck.get('critical_path_length_days'), ck.get('project_total_float_days')
        if cpl and ptf is not None and ptf < 0 and cpl + ptf > 0:
            c += (f" The remaining critical path is {cpl} working days long, so landing on {bl or 'the baseline finish'} "
                  f"would mean fitting {cpl} days of path work into {cpl + ptf}, about {round(-ptf / cpl * 100)}% compressed.")
        fp.append(c)
    if behind and spi and spi < 1 and fc:
        fp.append(f"Quote {fc}, not an SPI projection. At {K.ratio(spi)} of the planned rate, a pace-based forecast "
                  f"stretches the remaining work by about {round((1 / spi - 1) * 100)}% and lands well after {fc}. That "
                  "overshoots on a part-progressed job, where the remaining path sets the date rather than the average "
                  "pace. Use SPI only to confirm the direction: slipping, not recovering.")
    elif ahead and spi is not None:
        fp.append(f"SPI {K.ratio(spi)} " + ("agrees in direction: work is being earned ahead of plan." if spi >= 1 else
                  "points the other way (work earned below plan) — the network date leads, but watch that the gain "
                  "isn't coming from float that later work will need."))
    s_fin = K.sec('Forecast finish and how late', *fp)
    thinking.append(f"Compared {P['flabel']}'s forecast with its baseline and its total float"
                    + (f" ({slip(d)}, float {sg(tf)})" if d is not None and tf is not None else ''))

    # ── 2. driving path ─────────────────────────────────────────────────────────────────────────
    if chain:
        fronts, common, labmap = chain_fronts(chain)
        acts = [x for x in chain if not is_ms(x)]
        ns = sum(1 for x in acts if (x.get('pct') or 0) == 0)
        chain_ms = [x for x in chain if is_ms(x)]
        s = (f"One {len(chain)}-activity chain sets the date" +
             (", and all of it is at 0%." if ns == len(acts) and acts else (f", {ns} of its activities not started." if ns else '.')))
        if fronts:
            s += (' It runs through ' + ', '.join(f"{lab} ({c})" for lab, c, _ in fronts[:6])
                  + (f" — {len(fronts) - 6} more fronts" if len(fronts) > 6 else '')
                  + (f", nearly all of it under {' / '.join(common)}" if common else ''))
            ends = [f"{x['id']}" for x in chain_ms] + ([P['fid']] if P['fid'] else [])
            s += (f", and ends at {', '.join(ends[:-1]) + ' and ' + ends[-1] if len(ends) > 1 else ends[0]}." if ends else '.')
            s += ' (Activity counts in brackets.)'
        sl = [x['slip_wd'] for x in chain if x.get('slip_wd') is not None]
        fl = [x['tf'] for x in chain if x.get('tf') is not None]
        if sl and min(sl) > 0:
            s += f" Every link is {min(sl)}–{max(sl)} wd behind its baseline finish and carries {rng(fl)} wd float."
        elif fl:
            s += f" Its links carry {rng(fl)} wd float."
        dp = [s]
        near = [x for x in chain if x.get('tf') is not None and tf is not None and abs(x['tf'] - tf) <= 1]
        near_fronts = {labmap[x['id']] for x in near if x['id'] in labmap}
        if len(near_fronts) >= 2:
            dp.append(f"The table shows the spine. {len(near)} of the {len(chain)} links sit within a day of the finish's float, "
                      f"spread across {len(near_fronts)} fronts running in parallel, so shortening one branch alone gains little.")
        else:
            dp.append("The table shows the spine; recovery has to land on these links — work off the chain doesn't move the finish.")
        rows = [[clean(x['name']), x['id'], x.get('finish'), x.get('baseline_finish'), slip(x.get('slip_wd')), sg(x.get('tf'))]
                for x in spine(chain, fin)]
        shown = sum(1 for r in rows if r[1] != P['fid'])
        note = (f"{shown} of the {len(chain)} chain activities shown" + (f", then the finish milestone {P['fid']}" if P['fid'] else '')
                + ", with names as spelled in the P6 file.")
        if off_deep:
            note += (f" {len(off_deep)} {plural(len(off_deep), 'activity sits', 'activities sit')} off the traced chain with even deeper float"
                     + (', all 0%' if all((x.get('pct') or 0) == 0 for x in off_deep) else '') + ': '
                     + '; '.join(f"{clean(x['name'])} ({x['id']}, {sg(x['tf'])})" for x in off_deep[:3])
                     + f". {'It belongs' if len(off_deep) == 1 else 'They belong'} in the same recovery plan.")
        s_path = K.sec("What's driving the date (driving path)", *dp,
                       table=K.tbl(['Activity', 'ID', 'Forecast finish', 'Baseline finish', 'Slip', 'Float'], rows, note))
        thinking.append(f"Traced the {len(chain)}-activity chain that sets the finish across {len(fronts)} work fronts")
    else:
        s_path = K.sec("What's driving the date (driving path)", K.network_note(N),
                       (f"From the stored float check: {neg:,} activities are on negative float ({K.pct(negp, 1)}); critical "
                        f"density is graded {F.get('cpli_density_grade') or 'n/a'}." if neg is not None else
                        "No float audit is stored for this update, so I can't name the driving path from the stored numbers "
                        "— run the Schedule Audit (or re-import the file) and I'll trace it."))

    # ── 3. milestone / sectional slip ───────────────────────────────────────────────────────────
    s_ms = None
    mis = untied_sectional(keys, chain)
    if keys:
        pos_late = [m for m in keys_late if m.get('tf') is not None and m['tf'] >= 0]
        negk = [m for m in keys if m.get('tf') is not None and m['tf'] < 0]
        p1 = ((f"Every key date is late against baseline" if len(keys_late) == len(keys) else
               f"{len(keys_late)} of the {len(keys)} key dates are late against baseline") +
              ", but only the ones with negative float threaten the finish. Slip measures how late a milestone is "
              f"against plan. Float measures how much room is left before the {bl or 'baseline'} target.") if keys_late else \
             "Every key date is holding its baseline date."
        p2 = ''
        if pos_late:
            p2 = f"{names(pos_late)} {'is' if len(pos_late) == 1 else 'are'} late but still carr{'ies' if len(pos_late) == 1 else 'y'} positive float."
        if negk:
            first = keys.index(negk[0])
            monotone = all((m.get('tf') is not None and m['tf'] < 0) for m in keys[first:])
            deep = min(negk, key=lambda m: m['tf'])
            p2 += ((f" From {clean(negk[0]['name'])} onward, float turns negative, and it deepens to {sg(deep['tf'])} at "
                    f"{clean(deep['name'])}.") if monotone else
                   f" {len(negk)} carry negative float, deepest {clean(deep['name'])} at {sg(deep['tf'])}.")
        rows = [[clean(m['name']), m['id'], m.get('baseline_finish'), m.get('finish'), slip(m.get('slip_wd')), sg(m.get('tf'))]
                for m in (keys + ([fin] if fin else []))[:18]]
        note = "Slip = forecast finish minus baseline finish, in working days. Float = P6 total float."
        big = [m for m in keys if (m.get('slip_wd') or 0) > (d or 0) and m.get('tf') is not None and m['tf'] >= 0]
        if big:
            b = max(big, key=lambda m: m['slip_wd'])
            note += (f" {clean(b['name'])} has the largest slip ({slip(b['slip_wd'])}) but {sg(b['tf'])} wd float, so it "
                     f"isn't on the {P['fname']} path.")
        if mis:
            m, x = mis
            note += (f" One to check: {clean(m['name'])} forecasts {m['finish']} at {sg(m['tf'])}, yet activities of the "
                     f"same scope on the driving chain finish later, up to {x['finish']} ({clean(x['name'])}, {x['id']}) at "
                     f"{sg(x['tf'])}. The milestone may not be tied to its last activities, so it may be reporting an "
                     "optimistic sectional date.")
        s_ms = K.sec('Milestone / sectional slip', p1, p2,
                     table=K.tbl(['Milestone', 'ID', 'Baseline', 'Forecast', 'Slip', 'Float'], rows, note))

    # ── 4. contract & handover verdict ──────────────────────────────────────────────────────────
    cv = []
    if d is not None:
        if behind:
            cv.append("Against the schedule's own baseline, the answer is no: " +
                      (("every key date is late, and " if keys and len(keys_late) == len(keys) else
                        (f"{len(keys_late)} of {len(keys)} key dates are late, and " if keys_late else '')) +
                       f"the {P['fname'] if P['fid'] else 'project'} finish is {d} wd late. That much is solid."))
        elif ahead:
            cv.append(f"Against the schedule's own baseline, yes: the finish is forecast {K.wd(d)} early"
                      + (f" ({fc} vs {bl})" if fc and bl else '') + '.'
                      + (f" {len(keys_late)} key {plural(len(keys_late), 'date is', 'dates are')} still late against baseline, though."
                         if keys_late else ''))
        else:
            cv.append("Against the schedule's own baseline, yes: the finish is on its baseline date.")
    if cm:
        cv.append(f"The audit matched {hk.get('matched', 0)} of {cm} contract milestones: {hk.get('late', 0)} forecast late, "
                  f"{hk.get('on_track', 0)} on track" + (f", {hk.get('masked')} masked by a constraint" if hk.get('masked') else '')
                  + ". Those are the dates that carry delay damages — lead the report with the late ones.")
    else:
        c = ("Against the contract, I can't call it from this file. " +
             ("The audit found no contract milestones to test (0 flagged)" if (F.get('audit') or {}).get('hard_constraints')
              else "No contract-milestone check is stored for this update") +
             f", so I can't say whether {fc or 'the forecast finish'} breaches a completion date or triggers delay damages.")
        if behind and tf is not None and tf < 0 and bl:
            c += (f" The {sg(tf)} wd float at {P['fid'] or 'the finish'} says the schedule is still held to {bl}. If that is the "
                  f"contractual date, your exposure is {d} wd; confirm it against the agreement before it goes in a report.")
        if nok:
            ho = [m for m in (N.get('milestones') or []) + list(N.get('milestones_open_late') or [])
                  if any(w in (m.get('name') or '').lower() for w in HANDOVER_WORDS)]
            if ho:
                h = ho[-1]
                c += (f" The handover milestone {clean(h['name'])} ({h['id']}) is forecast {h.get('finish')} "
                      f"({slip(h.get('slip_wd'))} vs baseline, float {sg(h.get('tf'))}).")
            elif P['fid']:
                c += (f" The extract has no separate handover milestone, so {P['fid']} {P['fname']} is the finish I'm "
                      "reading.")
        c += (" Once the contractual and sectional dates are entered, " +
              ("the milestone table above turns into a contract-vs-forecast verdict." if keys else
               "the finish above turns into a contract-vs-forecast verdict."))
        cv.append(c)
    if behind and late_open:
        cv.append(f"Before anyone reads that {d} wd as the contractor's exposure, weigh it against the late client inputs "
                  "below. They are the counterweight: strong EOT indicators, but not yet proof.")
    s_con = K.sec('Contract & handover verdict — with the honest caveat', *cv)

    # ── 5. late client inputs ───────────────────────────────────────────────────────────────────
    s_ci = None
    if nok and allc:
        if late_open:
            due = [x for x in late_open if dt(x.get('baseline_finish')) and P['dd_dt'] and dt(x['baseline_finish']) <= P['dd_dt']]
            negs = [x for x in late_open if (x.get('tf') or 0) < 0]
            on_dd = [x for x in late_open if x.get('finish') == dd]
            p1 = (f"Of the {len(opn)} client inputs still open, {len(late_open)} " +
                  ("were due by the data date" if len(due) == len(late_open) else "are late against their baseline dates") +
                  (", and every one sits on negative float." if len(negs) == len(late_open) else
                   (f", {len(negs)} of them on negative float." if negs else '.')))
            if on_dd:
                p1 += (f" {len(on_dd)} of them show a forecast of {dd}, the data date itself. That means P6 is assuming they "
                       "arrive today. Every week they stay open, the paths behind them lose another week, and the next "
                       "update will show it.")
            if late_done:
                p1 += (f" Another {len(late_done)} client {plural(len(late_done), 'input was', 'inputs were')} delivered late "
                       f"({rng([x.get('slip_wd') for x in late_done], ' wd')}); already delivered, so part of the record "
                       "rather than a live block.")
            p2 = ("Employer-side inputs on negative-float paths are the strongest EOT indicators this file offers. They "
                  "aren't proof yet." +
                  (f" The chain that sets the finish starts at {clean(head['name'])} ({head['id']}, {head.get('pct', 0)}% "
                   "done), and this snapshot can't show how much of its delay traces back to these inputs rather than to "
                   "the contractor's own mobilisation." if head else '') +
                  " A time-impact / windows analysis across the updates (Consultant Review, Update vs Update) makes that "
                  "split. Meanwhile, make sure each input has a notice on record.")
            rows = [[clean(x['name']), x['id'], x.get('baseline_finish'),
                     (x.get('finish') or '—') + (' (open)' if x.get('finish') == dd else ''), slip(x.get('slip_wd')), sg(x.get('tf'))]
                    for x in late_open[:12]]
            note = None
            if other_open:
                oo = sorted(other_open, key=lambda x: dt(x.get('baseline_finish')) or datetime.max)
                zero = [x for x in oo if x.get('tf') is not None and x['tf'] <= 0]
                on_bl = all((x.get('slip_wd') or 0) <= 0 for x in oo)
                one = len(oo) == 1
                note = (f"The other {len(oo)} open client {plural(len(oo), 'input is', 'inputs are')} "
                        + '; '.join(f"{clean(x['name'])} ({x['id']}, due {x.get('baseline_finish')})" for x in oo[:6])
                        + ('; and more' if len(oo) > 6 else '') + '.')
                if zero:
                    note += (f" {'It is' if one else ('All are' if on_bl else 'They are')} "
                             + ('on baseline' if on_bl else 'not yet late') + ' but '
                             + ('carr' + ('ies' if one else 'y') if len(zero) == len(oo) else f"{len(zero)} carry")
                             + f" {rng([x['tf'] for x in zero])} float, so any slip goes straight onto the paths behind them.")
            s_ci = K.sec('Late client inputs — strong EOT indicators, not yet proof', p1, p2,
                         table=K.tbl(['Client input', 'ID', 'Due (baseline)', 'Forecast now', 'Slip', 'Float'], rows, note))
        else:
            s_ci = K.sec('Late client inputs — strong EOT indicators, not yet proof',
                         f"None of the {len(allc)} client / employer input activities in the file is open and late"
                         + (f" ({len(late_done)} were delivered late and are already in)." if late_done else '.')
                         + " On this snapshot the slip reads as execution on the driving chain — still to be confirmed.")
        thinking.append(f"Checked {len(keys)} key-date milestones and {len(allc)} client inputs against their baseline dates")

    # ── 6. quiet slips ──────────────────────────────────────────────────────────────────────────
    s_quiet = None
    if nok and P['dd_dt']:
        seen, due = set(), []
        for x in chain + deepest + keys + ([fin] if fin else []):
            b = dt(x.get('baseline_finish'))
            if x['id'] in seen or x.get('done') or not b or b > P['dd_dt'] or is_client(x):
                continue
            seen.add(x['id'])
            due.append(x)
        due.sort(key=lambda x: dt(x['baseline_finish']))
        in_due = [x for x in late_open if dt(x.get('baseline_finish')) and dt(x['baseline_finish']) <= P['dd_dt']]
        end = P['dd_dt'] + timedelta(days=21)
        up_zero = [x for x in other_open if dt(x.get('finish')) and P['dd_dt'] < dt(x['finish']) <= end
                   and x.get('tf') is not None and x['tf'] <= 0]
        places = []
        head_due = head if head and head['id'] in seen else None
        if head_due:
            places.append(f"{clean(head_due['name'])} ({head_due['id']}) at the head of the finish chain was due by "
                          f"{head_due['baseline_finish']} and " +
                          ("hasn't started" if (head_due.get('pct') or 0) == 0 else f"is only {head_due['pct']}% done"))
        if in_due:
            places.append(f"{len(in_due)} client {plural(len(in_due), 'input', 'inputs')} due between "
                          f"{min(in_due, key=lambda x: dt(x['baseline_finish']))['baseline_finish']} and "
                          f"{max(in_due, key=lambda x: dt(x['baseline_finish']))['baseline_finish']} "
                          + ('is' if len(in_due) == 1 else 'are') + " still open"
                          + (', all on negative float' if all((x.get('tf') or 0) < 0 for x in in_due) else ''))
        if places:
            p1 = (f"**Right now the slip sits in {'two places' if len(places) == 2 else 'one place'}. " +
                  '. '.join(p[0].upper() + p[1:] for p in places) + '.')
            if up_zero:
                dates = sorted({x['finish'] for x in up_zero}, key=dt)
                p1 += (f" The next three weeks turn on {'those two' if len(places) == 2 else 'that'}, plus {len(up_zero)} "
                       f"client {plural(len(up_zero), 'input')} due {', '.join(dates)} with zero float.")
            p1 += '**'
        elif due:
            p1 = f"**{len(due)} key {plural(len(due), 'item was', 'items were')} due by {dd} and {'is' if len(due) == 1 else 'are'} still not done.**"
        else:
            p1 = (f"**Nothing on the driving chain, the key dates or the client inputs was due by {dd} and left undone — "
                  "no quiet slips in the items I can see.**")
        p2 = (f"A quiet slip is work planned to finish on or before the {dd} data date that carries no actual. There's no "
              "dramatic event, so nobody reports it." + (" The key dates and the driving chain show the items below." if due else '') +
              (f" The wider signal is that {neg:,} activities ({K.pct(negp, 1)}) now sit on negative float. Not all of them are "
               f"overdue, but none of them can make {bl} as the logic stands." if neg and bl and behind else ''))
        rows = []
        for x in due[:10]:
            st = (f"not achieved, now {x.get('finish')}" if is_ms(x) else f"{x.get('pct', 0)}%, now {x.get('finish')}")
            rows.append([clean(x['name']) + (' (head of the finish chain)' if head and x['id'] == head['id'] else ''),
                         x['id'], x.get('baseline_finish'), st, slip(x.get('slip_wd')), sg(x.get('tf'))])
        if in_due:
            b_sorted = sorted(in_due, key=lambda x: dt(x['baseline_finish']))
            pcts = sorted({x.get('pct', 0) for x in in_due})
            rows.append([f"{len(in_due)} client {plural(len(in_due), 'input')}: " + '; '.join(short(x['name'], 40) for x in in_due[:7]),
                         compact_ids([x['id'] for x in in_due]),
                         f"{b_sorted[0]['baseline_finish']} to {b_sorted[-1]['baseline_finish']}",
                         'all open, ' + '/'.join(f"{p}%" for p in pcts), rng([x.get('slip_wd') for x in in_due], ' wd'),
                         rng([x.get('tf') for x in in_due])])
        note = ((("The client inputs are itemised in the table above. " if in_due else '') +
                 f"The complete quiet-slip list across the schedule (every baseline finish on or before {dd} with no actual) "
                 "comes from the Schedule view filter. These rows are the key dates and driving-chain items.") if rows else None)
        s_quiet = K.sec('Quiet slips — due by the data date, still not done', p1, p2,
                        table=K.tbl(['Item', 'ID', 'Due (baseline)', f"Status at {dd}", 'Slip', 'Float'], rows, note))

    # ── 7. what's blocking imminent work ────────────────────────────────────────────────────────
    s_block = None
    if nok:
        blocks = []
        if late_open:
            srt = sorted(late_open, key=lambda x: (x.get('tf') if x.get('tf') is not None else 0))
            b = (f"the open client inputs. {len(late_open)} {plural(len(late_open), 'is', 'are')} overdue: " +
                 '; '.join(f"{short(x['name'], 60)} ({x['id']}, float {sg(x.get('tf'))})" for x in srt[:5]) +
                 (f"; and {len(srt) - 5} more" if len(srt) > 5 else '') + f". The deepest is {clean(srt[0]['name'])} ({srt[0]['id']}"
                 + (f", forecast {srt[0]['finish']}" if srt[0].get('finish') and srt[0]['finish'] != dd else '')
                 + f", float {sg(srt[0].get('tf'))}).")
            for dsc in F.get('disciplines') or []:
                if (dsc.get('actual') or 0) <= 5 and (dsc.get('gap') or 0) >= 20:
                    link = token_link(dsc['name'], late_open)
                    if link:
                        b += (f" {clean(link['name'])} ({link['id']}) is still open and {slip(link.get('slip_wd'))} late, "
                              f"which fits {dsc['name']} sitting at {dsc.get('actual')}% against {dsc.get('planned')}% planned — "
                              "the input's own wording ties it to that work.")
                        break
            blocks.append(b)
        if head and not head.get('done'):
            fr = chain_fronts(chain)[0]
            b = (f"the finish chain's own sequence. Its head, {clean(head['name'])} ({head['id']}), is at {head.get('pct', 0)}%"
                 + (f" and was {'due' if P['dd_dt'] and dt(head.get('baseline_finish')) and dt(head['baseline_finish']) <= P['dd_dt'] else 'planned to finish'} "
                    f"{head['baseline_finish']}" if head.get('baseline_finish') else '') + '.')
            if len(fr) >= 2:
                nsf = sum(1 for _, c, n0 in fr if c == n0)
                b += (" The chain runs " + ' → '.join(lab for lab, _, _ in fr[:5]) + (' → …' if len(fr) > 5 else '') +
                      "; each front waits on the one before it" +
                      (", and none of them has begun" if nsf == len(fr) else '') +
                      ", so every downstream trade on the chain is queued behind the head.")
            blocks.append(b)
        lq = []
        if F.get('dangling_count') is not None:
            lq.append(f"{F['dangling_count']} dangling activities (a start or finish not tied into the network)")
        if F.get('oos_count') is not None:
            lq.append(f"{F['oos_count']} out-of-sequence progressions, {F.get('critical_oos') or 0} of them on the critical path")
        if lq:
            b = "logic that could mislead the blocked list: " + ' and '.join(lq) + '.'
            conc = oos_concentration(F)
            if conc:
                b += f" {conc[1]} of the {conc[2]} out-of-sequence items are in the {conc[0]} package."
            if F.get('critical_oos'):
                b += f" Correct the {F['critical_oos']} critical {plural(F['critical_oos'], 'one')} before you trust the sequence P6 is calculating."
            loops = kpis(F, 'circular').get('loops')
            if F.get('open_ends') is not None:
                b += f" Open ends are {F['open_ends']}" + (", and there are no logic loops." if loops == 0 else '.')
            blocks.append(b)
        if blocks:
            ords = ['First', 'Second', 'Third']
            intro = {1: "One thing is holding work back.", 2: "Two things are holding work back, in order of weight.",
                     3: "Three things are holding work back, in order of weight."}[len(blocks)]
            s_block = K.sec("What's blocking imminent work", intro,
                            *[(f"{ords[i]}, {b}" if len(blocks) > 1 else b[0].upper() + b[1:]) for i, b in enumerate(blocks)])

    # ── 8. 3-week look-ahead ────────────────────────────────────────────────────────────────────
    s_look = None
    if nok and P['dd_dt'] and (chain or opn or keys):
        d0 = P['dd_dt']
        end = d0 + timedelta(days=21)
        bounds = [(1, d0, d0 + timedelta(days=7)), (2, d0 + timedelta(days=7), d0 + timedelta(days=14)),
                  (3, d0 + timedelta(days=14), end)]

        def wk(f):
            if not f or f > end:
                return None
            for n_, a_, b_ in bounds:
                if f <= b_:
                    return n_, a_, b_
            return None
        rows, used = [], set()
        today = [x for x in late_open if x.get('finish') == dd]
        if today:
            rows.append((0, f"Wk 1 · {span(d0, bounds[0][2])}",
                         f"{len(today)} open client {plural(len(today), 'input')} forecast on the data date: " +
                         '; '.join(f"{short(x['name'], 44)} ({x['id']})" for x in today[:7]),
                         f"P6 assumes {'it arrives' if len(today) == 1 else 'they arrive'} now, on paths at "
                         f"{rng([x.get('tf') for x in today])}. Chase in writing and record notices."))
            used |= {x['id'] for x in today}
        if head and not head.get('done'):
            w = wk(dt(head.get('finish')))
            lab = f"Wk {w[0]} · {span(w[1], w[2])}" if w else f"Wk 1–3 · {span(d0, end)}"
            rows.append((w[0] if w else 0.5, lab,
                         f"{clean(head['name'])} ({head['id']}): {head.get('pct', 0)}%, float {sg(head.get('tf'))}, "
                         f"forecast finish {head.get('finish')}",
                         f"Head of the finish chain. Any slip here pushes the whole chain and {fc} with it."))
            used.add(head['id'])
        grouped = {}
        for x in other_open + late_open:
            if x['id'] in used:
                continue
            w = wk(dt(x.get('finish')))
            if w and dt(x['finish']) > d0:
                grouped.setdefault((w, x['finish']), []).append(x)
        for (w, f), xs in grouped.items():
            zero = all(x.get('tf') is not None and x['tf'] <= 0 for x in xs)
            rows.append((w[0], f"Wk {w[0]} · {span(w[1], w[2])}",
                         f"Client {plural(len(xs), 'input')} due {f}: " + '; '.join(f"{short(x['name'], 44)} ({x['id']})" for x in xs[:6])
                         + (f", {'on baseline' if all((x.get('slip_wd') or 0) <= 0 for x in xs) else 'late'} with "
                            f"{rng([x.get('tf') for x in xs])} float" if xs else ''),
                         ("Confirm delivery this week. With zero float, a late delivery goes straight onto the path behind it."
                          if zero else "Confirm it's on track this week.")))
            used |= {x['id'] for x in xs}
        for x in keys + [c for c in chain if not is_ms(c)]:
            if x['id'] in used:
                continue
            w = wk(dt(x.get('finish')))
            if w and dt(x['finish']) > d0:
                on_chain = x['id'] in chain_ids
                rows.append((w[0], f"Wk {w[0]} · {span(w[1], w[2])}",
                             f"{clean(x['name'])} ({x['id']}), forecast {x['finish']}, {slip(x.get('slip_wd'))}, float {sg(x.get('tf'))}",
                             ("On the finish chain — protect it." if on_chain else
                              ("Not on the finish path, but it's a sectional date due in the window. Close it out cleanly."
                               if (x.get('tf') or 0) >= 0 else f"On negative float ({sg(x.get('tf'))}) — a slip here feeds the finish."))))
                used.add(x['id'])
        rows.sort(key=lambda r: r[0])
        rows = rows[:8]
        nxt = []
        later_in = sorted([x for x in late_open if x['id'] not in used and dt(x.get('finish')) and dt(x['finish']) > end],
                          key=lambda x: dt(x['finish']))
        if later_in:
            nxt.append(later_in[0])
        if off_deep:
            nxt.append(min(off_deep, key=lambda x: x['tf']))
        if nxt:
            rows.append((9, 'Just past the window',
                         '; '.join(f"{clean(x['name'])} ({x['id']}), forecast {x.get('finish')}, float {sg(x.get('tf'))}" for x in nxt),
                         "Start on these now — they're the next deep-float items to reach the front."))
        on_chain_in = [c for c in chain if wk(dt(c.get('finish'))) and dt(c['finish']) > d0]
        lp = f"The window is {d0:%d-%b} to {end:%d-%b-%Y}."
        if head and not on_chain_in:
            lp += (f" No activity on the finish chain finishes inside it — its head, {clean(head['name'])} ({head['id']}), "
                   f"finishes {head.get('finish')}" + (", so this look-ahead is short on construction and heavy on client inputs."
                                                        if today or grouped else '.'))
            if len(chain) > 1:
                lp += (f" The chain extract carries finish dates only, so confirm in P6 which chain activities start inside "
                       f"the window, starting with {clean(chain[1]['name'])} ({chain[1]['id']}, forecast finish {chain[1].get('finish')}).")
        elif on_chain_in:
            lp += f" {len(on_chain_in)} finish-chain {plural(len(on_chain_in), 'activity finishes', 'activities finish')} inside it."
        small = [x for x in F.get('disciplines') or [] if (x.get('weight') or 0) <= 0.05 and (x.get('gap') or 0) >= 20
                 and not (drv and x['name'] == drv['name'])]
        if small and drv:
            lp += (f" Protect these items, and don't move crews onto the {round((small[0].get('weight') or 0) * 100)}%-weight "
                   f"{' / '.join(x['name'] for x in small[:2])} {plural(len(small[:2]), 'line')} to chase "
                   f"{'its point gap' if len(small[:2]) == 1 else 'their point gaps'}.")
        s_look = K.sec('Your 3-week driving-path look-ahead', lp,
                       "The exact day-gain from resequencing or acceleration needs the What-if run and a re-schedule (F9) "
                       "in P6. This table is the filter, not the recovery number.",
                       table=K.tbl(['Window', 'Driving / near-driving item (from the file)', 'Watch'],
                                   [r[1:] for r in rows],
                                   'Built from the driving chain, the key dates and the client inputs in the file.'))
        thinking.append(f"Filtered the chain, key dates and client inputs to the 3-week window {span(d0, end)}"
                        + (f" ({len(rows)} rows)" if rows else ''))
    if not nok:
        thinking.append("Read the finish float, CPLI and contract-milestone check from the stored audit")

    # ── measured / actions / evidence ───────────────────────────────────────────────────────────
    cpl, ptf = ck.get('critical_path_length_days'), ck.get('project_total_float_days')
    measured = (("The forecast finish and every milestone date are P6's own exported dates" if nok else
                 "The finish position comes from the stored analysis of this update") + f" at the {dd} data date. "
                "Slip = forecast finish minus baseline finish, in working days; float = P6 total float. "
                + (f"CPLI = (critical path length + total float) ÷ critical path length = ({cpl} {'-' if ptf < 0 else '+'} "
                   f"{abs(ptf)}) ÷ {cpl} = {K.ratio(ck.get('cpli'))}, against the {K.ratio(ck.get('target') or 0.95)} target. "
                   if cpl and ptf is not None and ck.get('cpli') is not None else '')
                + (f"The driving chain is the {len(chain)} open activities within {N.get('chain_band')} wd of the finish "
                   f"milestone's float" + (f" ({P['fid']})" if P['fid'] else '') + ". " if chain else '')
                + ("Client inputs are the activities whose WBS or name marks them as client / employer / consultant inputs; "
                   "an input is overdue when it is open and its forecast sits after its baseline. " if allc else '')
                + ("Quiet slips = baseline finish on or before the data date with no finish, read here from the key dates and "
                   "the chain; the full list needs the Schedule view filter. " if s_quiet else '')
                + ("The look-ahead filters the chain, key dates and client inputs to the next three weeks. " if s_look else '')
                + ("The file carries no contract milestones, so breach and delay damages can't be assessed. " if no_contract else '')
                + (f"The EVM time check divides the remaining work by SPI {K.ratio(spi)}; it's an approximation, quoted for "
                   "direction only." if spi else ''))
    top_in = sorted(late_open, key=lambda x: (x.get('tf') if x.get('tf') is not None else 0))[:4]
    up_zero_all = [x for x in other_open if x.get('tf') is not None and x['tf'] <= 0 and dt(x.get('finish'))
                   and P['dd_dt'] and dt(x['finish']) > P['dd_dt']]
    actions = [
        (f"Quote {fc} ({P['fid'] + ', ' if P['fid'] else ''}{slip(d)}" + (f", float {sg(tf)}" if tf is not None else '')
         + ") as the forecast finish. It's the network date, not an SPI projection.") if fc and d is not None else
        (f"Report the finish as {K.signed(d)} against baseline." if d is not None else ''),
        (f"Get {clean(head['name'])} ({head['id']}) progressing in week 1, and confirm in P6 which chain activities start "
         "inside the window." + (f" Plan {clean(off_deep[0]['name'])} ({off_deep[0]['id']}, {sg(off_deep[0]['tf'])}) now."
                                 if off_deep else '')) if head and behind else '',
        (f"Chase the {len(late_open)} overdue client {plural(len(late_open), 'input')} in writing this week, starting with "
         + ', '.join(f"{short(x['name'], 60)} ({x['id']})" for x in top_in) + ". Make sure each has a notice on record.")
        if late_open else '',
        (f"Confirm the {len(up_zero_all)} upcoming client {plural(len(up_zero_all), 'input')} with zero float ("
         + by_date_ids(up_zero_all) + "). Any late one goes straight onto the path behind it.") if up_zero_all else '',
        ("Enter the contractual and sectional dates so the milestone table becomes a contract-vs-forecast verdict. Until "
         "then, report 'late vs baseline' only.") if no_contract else
        ("Run the Schedule Audit's contract-milestone check so the finish is tested against the contract dates, not just "
         "the baseline." if not hc_known else ''),
        (f"Check that {clean(mis[0]['name'])} ({mis[0]['id']}, {mis[0]['finish']}) is tied to its last activities — "
         f"chain work of the same scope finishes up to {mis[1]['finish']}.") if mis else '',
        (f"Correct the {F.get('critical_oos')} critical out-of-sequence {plural(F.get('critical_oos'), 'item')}"
         + (f" and close the {F.get('dangling_count')} dangling links" if F.get('dangling_count') else '')
         + " before you trust the blocked-work list.") if F.get('critical_oos') and F.get('oos_count') is not None else '',
        (f"Commission a windows / TIA analysis (Consultant Review, Update vs Update) before stating how much of the {d} wd "
         "is employer-side. Run the What-if on the finish chain for the real day-gain, and confirm it with F9 in P6.")
        if behind else "Re-import the next update and compare it here to confirm the finish is holding.",
    ]
    deep_all = min(deepest, key=lambda x: x['tf']) if deepest and all(x.get('tf') is not None for x in deepest) else None
    evidence = [K.ev('Forecast finish', f"{fc} ({P['fid']})" if fc and P['fid'] else fc),
                K.ev('Baseline finish', bl),
                K.ev('Delay', f"{slip(d)} (~{max(1, round(abs(d) / 5))} wk)" if d else (K.signed(d) if d is not None else None)),
                K.ev('Float at finish', f"{sg(tf)} wd" if tf is not None else None),
                K.ev('CPLI', f"{K.ratio(ck.get('cpli'))} (target {K.ratio(ck.get('target') or 0.95)})" if ck.get('cpli') is not None else None),
                K.ev('Key dates late', f"{len(keys_late)} of {len(keys)}" + (f" ({rng([x['slip_wd'] for x in keys_late], ' wd')})" if keys_late else '')
                     if keys else None),
                K.ev('Driving chain', f"{len(chain)} activities" + (', all 0%' if chain and all((x.get('pct') or 0) == 0 for x in chain) else '')
                     if chain else None),
                K.ev('Worst float', f"{sg(deep_all['tf'])} wd ({deep_all['id']})" if deep_all else None),
                K.ev('Neg. float', f"{neg:,} ({K.pct(negp, 1)})" if neg is not None else None),
                K.ev('At critical float', f"{F.get('cpli_critical_count'):,} ({K.pct(F.get('cpli_critical_pct'), 1)})"
                     if F.get('cpli_critical_count') is not None else None),
                K.ev('Client inputs overdue', f"{len(late_open)} of {len(opn)}" if allc else None),
                K.ev('Out-of-seq', f"{F.get('oos_count')} ({F.get('critical_oos') or 0} critical)" if F.get('oos_count') is not None else None),
                K.ev('Dangling', F.get('dangling_count')),
                K.ev('Open ends', F.get('open_ends'))]
    a = K.A2(head_line, [s_fin, s_path, s_ms, s_con, s_ci, s_quiet, s_block, s_look], pills=pills, measured=measured,
             actions=actions, evidence=evidence,
             drilldowns=[K.drill('q05', f"How do I recover the {d} days on the finish chain?") if behind else
                         K.drill('q04', 'How much float is left, and where?'),
                         K.drill('q13', 'Do the late client inputs give me an EOT case, and how many days?') if late_open else None,
                         K.drill('q04', 'How negative is the float, and where?') if behind else None,
                         K.drill('q06', 'Which logic problems do I fix first?'),
                         K.drill('q01', 'Are we ahead or behind, over or under budget?')])
    a['thinking'] = thinking[:4]
    return a
