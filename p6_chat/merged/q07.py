"""q07 — What changed in the baseline or update — and is it a genuine re-plan or gaming?

Covers: the headline change and what pushed the finish (scope, durations, logic, calendar), the path
re-route and float migration, scope growth vs re-decomposition, durations and logic on the driving path,
WBS / calendar / milestone movement, client inputs that moved, material vs cosmetic, the manipulation
and DCMA-quality check, the genuine-recovery test, and whether the contractor's update is honest by F9
— for ANY project.

Honest scope: one P6 file carries its own baseline dates, so baseline→update movement is read activity
by activity from N. A revision-to-revision diff (added/deleted, renamed-same-ID, WBS remap, calendar
diff, man-hour and budget deltas) needs both revision files in Baseline Revision Comparison — the answer
says so and never invents a delta.
"""
import re
from datetime import datetime

from . import _kit2 as K

MINUS = '−'


# ── small, None-safe helpers ─────────────────────────────────────────────────────

def _k(F, mod):
    return (((F.get('audit') or {}).get(mod) or {}).get('kpis')) or {}


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    n = _num(v)
    return '—' if n is None else f"{int(round(n)):,}"


def _pc(v):
    n = _num(v)
    if n is None:
        return '—'
    return f"{n:.0f}%" if abs(n - round(n)) < 0.05 else f"{n:.1f}%"


def _sg(v):
    n = _num(v)
    if n is None:
        return '—'
    n = int(round(n))
    return f"+{n}" if n > 0 else (f"{MINUS}{abs(n)}" if n < 0 else '0')


def _dt(s):
    try:
        return datetime.strptime(s, '%d-%b-%Y')
    except (TypeError, ValueError):
        return None


def _join(items):
    items = [i for i in items if i]
    if not items:
        return ''
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]


def _word(n, cap=False):
    w = {0: 'none', 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight',
         9: 'nine', 10: 'ten', 11: 'eleven', 12: 'twelve'}.get(n, f"{n:,}" if isinstance(n, int) else str(n))
    return w[0].upper() + w[1:] if cap else w


def _name(x):
    return ' '.join(((x or {}).get('name') or '').split())


def _leaf(x):
    parts = [p for p in ((x or {}).get('wbs') or '').split(' / ') if p]
    return parts[-1] if parts else ''


def _nm(x):
    """Activity name, disambiguated by its short WBS leaf when that helps."""
    name, leaf = _name(x), _leaf(x)
    if leaf and len(leaf) <= 12 and leaf.lower() not in name.lower():
        return f"{name} ({leaf})"
    return name


def _nmc(x):
    """Comma form of _nm for use next to parentheses ('Drilling For Piles, Area 9')."""
    name, leaf = _name(x), _leaf(x)
    if leaf and len(leaf) <= 12 and leaf.lower() not in name.lower():
        return f"{name}, {leaf}"
    return name


def _short(s, n=42):
    s = ' '.join((s or '').split())
    if len(s) <= n:
        return s
    return s[:n].rsplit(' ', 1)[0].rstrip(' ,;-&') + '…'


def _pos(d):
    """'+60 wd slip' / '12 wd margin' / 'on-date finish' — the position without nested brackets."""
    if d is None:
        return 'the forecast'
    d = round(d)
    return f"+{d} wd slip" if d > 0 else (f"{abs(d)} wd margin" if d < 0 else 'on-date finish')


def _is_ms(x):
    return 'Milestone' in ((x or {}).get('type') or '')


def _chain_fronts(chain):
    """Work fronts along the finish chain in order of first appearance: ([(label, rows)], scope_label)."""
    tasks = [x for x in chain if not _is_ms(x)]
    paths = [[p for p in (x.get('wbs') or '').split(' / ') if p] for x in tasks]
    if not paths:
        return [], ''
    common = set(paths[0]).intersection(*[set(p) for p in paths[1:]]) if len(paths) > 1 else set()
    out = []
    for x, p in zip(tasks, paths):
        rest = [q for q in p if q not in common]
        label = rest[-1] if rest else (p[-1] if p else '(no WBS)')
        for lab, rows in out:
            if lab == label:
                rows.append(x)
                break
        else:
            out.append((label, [x]))
    scope = [q for q in paths[0] if q in common]
    return out, (scope[-1] if scope else '')


def _diff_test(branch, disciplines):
    """What a two-file comparison tests in this WBS branch — chosen from the branch's own name."""
    b = branch.lower()
    l1 = branch.split(' / ')[0].strip().lower()
    done = next((d for d in disciplines or [] if (d.get('name') or '').strip().lower() == l1
                 and (d.get('actual') or 0) >= 95), None)
    if done:
        return 'Mostly complete; changes here are cosmetic unless dates move'
    if any(w in b for w in ('client', 'employer', 'owner', 'input')):
        return 'Client inputs added or re-dated (see below)'
    if any(w in b for w in ('procure', 'material', "po's", 'purchase', 'deliver')):
        return 'Items added or dropped'
    if any(w in b for w in ('shop drawing', 'submit', 'engineering')):
        return 'Submittal lines added or merged'
    if 'design' in b:
        return 'Design deliverables added or regrouped'
    if any(w in b for w in ('as-built', 'as built', 'close', 'handover')):
        return 'Close-out lines added or dropped'
    if any(w in b for w in ('construct', 'civil', 'install', 'works', 'erection', 'structure')):
        return 'Work packages added, or the same work re-cut into more lines?'
    return 'Activities added, deleted or re-cut'


def _wbs_rows(wbs_top, total, disciplines):
    """Top WBS branches for the scope table; small branches are grouped under their top level."""
    big, small = [], {}
    for b in wbs_top or []:
        parts = [p for p in (b.get('branch') or '').split(' / ') if p]
        n = b.get('activities') or 0
        if not total or n >= 0.05 * total or len(parts) < 2:
            big.append((b['branch'], n, b['branch']))
        else:
            small.setdefault(parts[0], []).append((parts[-1], n, b['branch']))
    rows = list(big)
    for l1, items in small.items():
        n = sum(x[1] for x in items)
        if len(items) == 1:
            rows.append((items[0][2], n, items[0][2]))
        elif len(items) <= 3:
            rows.append((f"{l1} ({' · '.join(f'{leaf} {c}' for leaf, c, _ in items)})", n, l1))
        else:
            rows.append((f"{l1} ({len(items)} branches)", n, l1))
    rows.sort(key=lambda r: -r[1])
    return [[label, _i(n), _diff_test(key, disciplines)] for label, n, key in rows[:10]]


# ── the answer ─────────────────────────────────────────────────────────────────

def build(F, N, role):
    nok = bool(N and N.get('ok'))
    d = F.get('delay_days')
    behind, ahead = (d or 0) > 0, (d or 0) < 0
    drv = K.main_driver(F)
    thinking = []

    fin = (N.get('finish_milestone') or {}) if nok else {}
    chain = (N.get('chain') or []) if nok else []
    chain_n = (N.get('chain_count') or len(chain)) if chain else 0      # the chain itself, finish milestone not counted
    fin_tf = N.get('finish_tf') if nok else None
    fin_slip = fin.get('slip_wd')
    bl = fin.get('baseline_finish') or F.get('baseline_finish')
    fc = fin.get('finish') or F.get('forecast_finish')
    dd_s = (N.get('data_date') if nok else None) or F.get('data_date')
    dd = _dt(dd_s)
    fronts, scope = _chain_fronts(chain)
    chain_lbl = f"the {scope} finish chain" if scope else 'the finish chain'
    head = next((x for x in chain if not _is_ms(x)), None)
    acts = (N.get('activity_count') if nok else None) or F.get('activity_count')

    # audit facts
    llk, ok_, nk, ck = _k(F, 'lag_lead'), _k(F, 'out_of_sequence'), _k(F, 'negative_float'), _k(F, 'cpli')
    dk, ek, lk, rk, hk = _k(F, 'dangling'), _k(F, 'open_ends'), _k(F, 'leads'), _k(F, 'relationship_types'), _k(F, 'hard_constraints')
    rels = llk.get('total_relationships') or rk.get('total_relationships')
    lagged, lag_pct, long_n = llk.get('lagged_count'), llk.get('lagged_pct'), llk.get('long_count') or 0
    lag_thr, lag_crit = _i(llk.get('long_threshold_days') or 14), llk.get('critical_count') or 0
    leads = llk.get('leads_count') if llk.get('leads_count') is not None else lk.get('leads')
    oos, oos_pct, crit_oos = ok_.get('oos_count'), ok_.get('oos_pct'), ok_.get('critical_oos') or 0
    m = re.search(r'concentrated in the (.+?) package \((\d+) of (\d+)', str(ok_.get('executive_conclusion') or ''))
    pkg, pkg_n = (m.group(1), int(m.group(2))) if m else (None, None)
    neg, neg_pct = nk.get('negative_count'), nk.get('neg_pct')
    cpli, tgt = _num(ck.get('cpli')), _num(ck.get('target')) or 0.95
    cpl, ptf = _num(ck.get('critical_path_length_days')), _num(ck.get('project_total_float_days'))
    crit_cnt, crit_pct = ck.get('critical_count'), ck.get('critical_pct')
    dang, oe, fs = dk.get('total_dangling'), ek.get('open_ends'), _num(rk.get('fs_pct'))
    hard_known = hk.get('hard_count') is not None
    contract_ms = hk.get('contract_milestones')
    float_grade = ((F.get('audit') or {}).get('float') or {}).get('grade')

    # network facts
    cids = {x['id'] for x in (N.get('client_inputs') or [])} if nok else set()
    late_in = (N.get('client_inputs_late_open') or []) if nok else []
    late_done = (N.get('client_inputs_late_done') or []) if nok else []
    on_bl_open = [x for x in ((N.get('client_inputs') or []) if nok else [])
                  if not x.get('done') and (x.get('slip_wd') or 0) <= 0]
    seen = {}
    if nok:
        for key in ('chain', 'deepest', 'milestones', 'client_inputs'):
            for x in N.get(key) or []:
                seen.setdefault(x['id'], x)
        if fin:
            seen.setdefault(fin['id'], fin)
    ref_slip = fin_slip if fin_slip is not None else (d if d is not None else None)
    pool = {x['id']: x for x in chain + ((N.get('deepest') or []) if nok else []) if not x.get('done')}
    outliers = sorted([x for x in pool.values() if ref_slip is not None and x.get('slip_wd') is not None
                       and x['slip_wd'] >= ref_slip + 5], key=lambda x: -x['slip_wd'])
    out_ids = {x['id'] for x in outliers}
    core = [x['slip_wd'] for x in chain if x['id'] not in out_ids and x.get('slip_wd') is not None]
    c_lo, c_hi = (min(core), max(core)) if core else (None, None)
    head_slip = (head or {}).get('slip_wd')
    late_start = bool(head_slip is not None and ref_slip and ref_slip > 0 and head_slip >= 0.8 * ref_slip)
    not_started = sum(1 for x in chain if (x.get('pct') or 0) == 0)
    key_dates = [x for x in ((N.get('milestones') or []) if nok else [])
                 if not x.get('done') and x['id'] not in cids and x.get('baseline_finish') and x.get('slip_wd') is not None]
    chain_ids = {x['id'] for x in chain} | ({fin['id']} if fin else set())
    behind_paths = sorted([x for x in key_dates + late_in if x['id'] not in chain_ids and x.get('tf') is not None
                           and fin_tf is not None and fin_tf < x['tf'] < 0], key=lambda x: x['tf'])
    if nok:
        thinking.append(f"Compared each activity's current finish with the baseline finish carried in the same file "
                        f"({len(seen)} chain activities, milestones and client inputs checked)")
    else:
        thinking.append("Tried to re-read the P6 file — not available, so answered from the stored numbers "
                        f"(SPI {K.ratio(F.get('spi'))}, {_pos(F.get('delay_days'))})")
    if chain:
        thinking.append(f"Traced the {chain_n}-activity finish chain: {_sg(head_slip)} wd at its head, "
                        f"{_sg(fin_slip)} at the finish — " + ('a late start carried forward, not a stretch' if late_start
                                                               else 'the slip grows along the chain'))
    if key_dates or late_in:
        thinking.append(f"Read {len(key_dates)} open key dates and {len(N.get('client_inputs') or [])} client inputs "
                        "against their own baselines")
    if F.get('has_audit') and F.get('audit'):
        thinking.append("Checked the audit's quality flags (lags, leads, dangling, out-of-sequence, constraints) for "
                        "signs of slip being masked")

    # ── verdict + pills ─────────────────────────────────────────────────────────
    if nok and fin and bl and fc and fin_slip is not None and fin_slip > 0:
        honest = bool(neg) or (fin_tf is not None and fin_tf < 0)
        verdict = (f"A real slip, {'shown honestly' if honest else 'on the face of this update'}: {_name(fin)} has moved "
                   f"from {bl} to {fc} ({_sg(fin_slip)} wd).")
        if head:
            verdict += (f" The delay starts with late {_nm(head)} and carries through "
                        + ('unchanged to the finish.' if late_start else 'the chain, growing on the way to the finish.'))
        verdict += " Proving nothing was gamed between baseline revisions still needs both revision files side by side."
    elif nok and fin and bl and fc:
        verdict = (f"No slip at the finish on this update: {_name(fin)} is forecast {fc} against a baseline of {bl} "
                   f"({_sg(fin_slip)} wd). Whether anything was re-planned or gamed between baseline revisions needs "
                   "both revision files side by side.")
    elif d is not None:
        verdict = ((f"A real slip on this update: the finish is about {K.wd(d)} behind (SPI {K.ratio(F.get('spi'))})." if behind
                    else f"Ahead on this update: about {K.wd(d)} of float to the finish (SPI {K.ratio(F.get('spi'))})." if ahead
                    else f"On the planned finish on this update (SPI {K.ratio(F.get('spi'))}).")
                   + " What changed between baseline revisions, and whether any of it was gamed, needs both revision "
                     "files side by side; this snapshot alone can't show a revision diff.")
    else:
        verdict = ("The finish slip can't be read from this file. What changed between baseline revisions needs both "
                   "revision files side by side in Baseline Revision Comparison.")

    tfs_in = [x['tf'] for x in late_in if x.get('tf') is not None]
    sl_in = [x['slip_wd'] for x in late_in if x.get('slip_wd') is not None]
    pills = [K.pill(f"finish {bl} → {fc} ({_sg(fin_slip)} wd)", 'danger' if (fin_slip or 0) > 0 else 'success')
             if (nok and fin and bl and fc) else (K.pill(K.signed(d), 'danger' if behind else 'success') if d is not None else None),
             K.pill(f"slip enters at {_nmc(head)} ({_sg(head_slip)} wd)", 'warning') if (head and (head_slip or 0) > 0) else None,
             (K.pill(f"chain carries {_sg(c_lo)} to {_sg(c_hi)} — late start, not stretched", 'neutral') if late_start else
              K.pill(f"slip grows along the chain ({_sg(head_slip)} → {_sg(fin_slip)})", 'warning')) if (chain and c_lo is not None and (fin_slip or 0) > 0) else None,
             K.pill(f"{_i(neg)} on negative float — shown openly", 'accent') if neg else None,
             K.pill(f"client inputs {_sg(min(sl_in))} to {_sg(max(sl_in))} wd late", 'warning') if len(sl_in) > 1 else
             (K.pill(f"client input {_sg(sl_in[0])} wd late", 'warning') if sl_in else None),
             K.pill(f"CPLI {K.ratio(cpli)} vs {K.ratio(tgt)}", 'danger' if cpli < tgt else 'success') if cpli is not None else None,
             K.pill(f"lags {_pc(lag_pct)} · {_i(lag_crit)} on critical path", 'warning') if (lagged and (_num(lag_pct) or 0) > 5) else None,
             K.pill(f"SPI {K.ratio(F.get('spi'))} · {K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}",
                    'danger' if (F.get('spi') or 1) < 0.9 else ('warning' if (F.get('spi') or 1) < 1 else 'success'))
             if not nok else None,
             K.pill('revision-to-revision diff needs both baselines', 'accent')]

    # ── 1. the headline ─────────────────────────────────────────────────────────
    if nok and fin and bl and fc:
        if (fin_slip or 0) > 0:
            lead = (f"**Lead with this: {_name(fin)} ({fin['id']}) has moved from {bl} to {fc}, about {K.wd(fin_slip)}.")
            if head:
                rest = [f for f, _ in fronts[1:]]
                lead += (f" The slip starts at the head of {chain_lbl} ({_nmc(head)}: {_sg(head_slip)} wd)."
                         + (f" From there it carries {'almost day for day' if late_start else 'and grows'} through "
                            f"{_join(rest)} to the finish." if rest else ''))
            lead += '**'
        else:
            lead = (f"**Lead with this: {_name(fin)} ({fin['id']}) is forecast {fc} against a baseline of {bl} "
                    f"({_sg(fin_slip)} wd) — the finish hasn't slipped on this update.**")
        p2 = ("This update carries its own baseline dates, so I can read baseline-to-update movement activity by activity "
              "from this one file. A revision-to-revision headline (Rev A baseline against Rev B baseline) is different. "
              "For that, load both revision files into Baseline Revision Comparison and it gives you one sentence: the "
              "finish moved from X to Y, N working days, driven mainly by scope, durations, logic or calendar.")
        p3 = ''
        if head and (fin_slip or 0) > 0:
            p3 = (f"The shape of the slip matters more than its size. {_nm(head)} was due to finish on "
                  f"{head.get('baseline_finish')} and is {'still ' if head.get('pct') == 0 else ''}{head.get('pct')}% at the "
                  f"{dd_s} data date.")
            if late_start:
                p3 += (f" Almost every activity after it on the finish chain is {c_lo} to {c_hi} wd late, and the finish is "
                       f"{fin_slip} wd late. So the chain started late; it did not stretch on the way. The question to "
                       f"answer is why {_nm(head)} has not {'started' if head.get('pct') == 0 else 'finished'}, not why the "
                       "work after it is taking longer.")
            else:
                p3 += (f" The chain's head is {_sg(head_slip)} wd late but the finish is {_sg(fin_slip)}, so about "
                       f"{fin_slip - (head_slip or 0)} wd were added downstream: longer durations, added links or lag, or a "
                       "calendar change. The two-file diff shows which.")
            if drv:
                p3 += (f" The weight is in the right place for that story: {drv['name']} is "
                       f"{round((drv.get('weight') or 0) * 100)}% of the job and stands at {drv['actual']}% against "
                       f"{drv['planned']}% planned.")
        s1 = K.sec('The headline — the one line to lead with', lead, p2, p3)
    else:
        s1 = K.sec('The headline — the one line to lead with',
                   (f"**Lead with this: the finish is {K.delay_phrase(F).replace('**', '')}, with SPI {K.ratio(F.get('spi'))} "
                    f"({K.pct(F.get('actual_pct'))} earned against {K.pct(F.get('planned_pct'))} planned).**"
                    if d is not None else "**The finish slip can't be read from this file.**"),
                   K.network_note(N),
                   (f"The shortfall is carried by {drv['name']} ({round((drv.get('weight') or 0) * 100)}% of the job by "
                    f"weight): {drv['actual']}% done against {drv['planned']}% planned." if (drv and behind) else ''),
                   "A revision-to-revision headline (Rev A baseline against Rev B baseline) needs both revision files in "
                   "Baseline Revision Comparison; it gives you one sentence: the finish moved from X to Y, N working "
                   "days, driven mainly by scope, durations, logic or calendar.")

    # ── 2. the four levers ──────────────────────────────────────────────────────
    top = [b for b in ((N.get('wbs_top') or []) if nok else [])][:2]
    scope_txt = (f"{_i(acts)} activities now" if acts else 'Activity count not read')
    if len(top) == 2:
        scope_txt += (f", {_i(top[0]['activities'] + top[1]['activities'])} of them in "
                      f"{top[0]['branch'].split(' / ')[-1]} ({_i(top[0]['activities'])}) and "
                      f"{top[1]['branch'].split(' / ')[-1]} ({_i(top[1]['activities'])})")
    scope_txt += '. Added or deleted activities need the prior baseline file.'
    if chain and c_lo is not None:
        dur_txt = (f"The finish chain holds {_sg(c_lo)} to {_sg(c_hi)} wd from its first activity to its last, so it "
                   + ('started late rather than stretched.' if late_start else 'grew along the way.'))
        if outliers:
            slips = sorted({_sg(x['slip_wd']) for x in outliers})
            dur_txt += (f" {_word(len(outliers), True)} activit{'ies are' if len(outliers) != 1 else 'y is'} the "
                        f"exception{'s' if len(outliers) != 1 else ''} at {' / '.join(slips)}: "
                        + _join([_nm(x) for x in outliers[:4]]) + '.')
    else:
        dur_txt = "Needs the file re-read to compare each activity's forecast with its own baseline."
    if lagged is not None:
        logic_txt = (f"{_i(rels)} links; {_i(lagged)} carry a lag ({_pc(lag_pct)}, against the 5% DCMA line)"
                     + (f"; {_i(lag_crit)} of those lags sit on the critical path" if lag_crit else '')
                     + (f"; {_i(long_n)} are longer than {lag_thr} wd" if long_n else '')
                     + '. Lag added or removed between revisions shows only in the diff.')
    else:
        logic_txt = 'The lag and link counts aren\'t in this snapshot\'s audit. Added or tightened links show only in the diff.'
    cal_txt = ((f"{_i(F['calendar_count'])} calendar{'s' if F['calendar_count'] != 1 else ''} in the file. "
                if F.get('calendar_count') else 'Calendar count not read. ')
               + "Changes against the prior revision need both files. Weather isn't in the file.")
    s2 = K.sec('What usually pushes the finish — the four levers',
               'Four things move a finish date between revisions. For each one, here is what this update already shows '
               'and what needs the second file.',
               table=K.tbl(['Lever', 'How it moves the date', 'What this update already shows'],
                           [['Scope', 'New activities lengthen the driving chain', scope_txt],
                            ['Durations', 'Key activities take longer', dur_txt],
                            ['Logic', 'New or tighter links, or added lag', logic_txt],
                            ['Calendar', 'Fewer working days or shorter hours', cal_txt]],
                           'Durations and logic are real from this update (current dates against its own baseline '
                           'dates). Scope and calendar changes need the prior revision loaded beside it.'))

    # ── 3. path re-route and float migration ────────────────────────────────────
    if chain and fronts:
        steps = []
        for label, rows in fronts[:7]:
            names = []
            for x in rows:
                n = _name(x)
                if n not in names:
                    names.append(n)
            steps.append(f"{label} ({', '.join(names[:3])}{', …' if len(names) > 3 else ''})")
        ends = [x for x in chain if _is_ms(x)]
        end_items = [f"{_name(x)} ({x['id']})" for x in ends[-1:]] + ([_name(fin)] if fin else [])
        end_tf = fin_tf if fin_tf is not None else (ends[-1].get('tf') if ends else None)
        end_txt = ((f" It ends at {_join(end_items)}"
                    + (f", {'both ' if len(end_items) > 1 else ''}at {_sg(end_tf)}" if end_tf is not None else '') + '.')
                   if end_items else '')
        pp = [f"Today's driving path runs through {scope or 'the finish chain'}: " + '; then '.join(steps) + '.'
              + end_txt + " Whether that was also the driver in the previous baseline needs that revision's own driving "
                          "path, which Baseline Revision Comparison traces."]
        if behind_paths:
            groups = []
            for x in behind_paths[:6]:
                if groups and groups[-1][0] == x['tf']:
                    groups[-1][1].append(_name(x))
                else:
                    groups.append((x['tf'], [_name(x)]))
            para = ("What this file does show is how little room sits behind the driver. "
                    + ' '.join(f"{_join(ns)} {'are' if len(ns) > 1 else 'is'} at {_sg(tf)}." for tf, ns in groups))
            if crit_cnt is not None:
                para += (f" In all, {_i(crit_cnt)} activities ({_pc(crit_pct)}) sit at critical float. "
                         + ("So float hasn't drained onto one chain; it has gone almost everywhere."
                            if (_num(crit_pct) or 0) >= 25 else "So the risk is still concentrated on a few chains."))
            pp.append(para)
            gap = behind_paths[0]['tf'] - fin_tf
            pp.append(f"Read that before accepting any recovery. If a revision fixes only part of {chain_lbl}, the "
                      f"{_sg(behind_paths[0]['tf'])} path takes over after about {gap} wd of recovery, and the others "
                      "follow. The risk will have moved, not gone.")
        s3 = K.sec('Path re-route and float migration', *pp)
    else:
        s3 = K.sec('Path re-route and float migration',
                   ("I can't trace the driving path without the file re-read. " if not nok else '')
                   + (f"From the stored audit: {_i(neg)} activities ({_pc(neg_pct)}) are on negative float and "
                      f"{_i(crit_cnt)} ({_pc(crit_pct)}) at critical float. " if (neg is not None and crit_cnt is not None) else '')
                   + "Whether the path re-routed, and where float migrated, needs both revisions' driving paths in "
                     "Baseline Revision Comparison.")

    # ── 4. activities & scope ───────────────────────────────────────────────────
    wrows = _wbs_rows(N.get('wbs_top') if nok else [], acts, F.get('disciplines')) if nok else []
    share = ''
    if len(top) == 2 and acts:
        frac = (top[0]['activities'] + top[1]['activities']) / acts
        share = ('more than half' if frac > 0.5 else 'about a third' if frac > 0.3 else 'a large share')
    lead4 = (f"**This one file can show scope as it stands: {_i(acts)} activities"
             + (f", {share} of them in {top[0]['branch'].split(' / ')[-1]} and {top[1]['branch'].split(' / ')[-1]}" if share else '')
             + ". Whether any of it is new, deleted or the same work re-cut needs the prior baseline loaded beside it.**")
    listed = sum(b['activities'] for b in ((N.get('wbs_top') or []) if nok else []))
    rest_n = (acts or 0) - listed if nok else 0
    s4 = K.sec('Activities & scope — real growth vs re-decomposition', lead4,
               "With both files loaded, Baseline Revision Comparison sorts every change into buckets (added, deleted, "
               "duration, logic, WBS, calendar, milestone). Then comes the harder question: is added scope real new "
               "work, or the same work split into more lines? A re-cut raises the activity count while man-hours and "
               "budget stay flat, so it looks like growth and isn't. Real growth moves the count, the man-hours and the "
               "budget together.",
               "One caution when the comparison totals man-hours: count labour resources only. Summing every resource "
               "type as hours mixes in material quantities and produces a meaningless 'man-hour' total.",
               table=K.tbl(['WBS branch (this update)', 'Activities', 'What the diff tests'], wrows,
                           "Real counts from this update" + (f" (the largest branches; {_i(rest_n)} more activities sit in "
                                                             "smaller ones)" if rest_n > 0 else '')
                           + ". Change counts, man-hour and budget deltas come only from the two-file comparison."))

    # ── 5. durations & logic on the driving path ────────────────────────────────
    dp = []
    if chain and (fin_slip or 0) > 0:
        if late_start:
            txt = ("Duration and logic changes only matter where they land, so start with the driving path. In this update "
                   "most of the finish chain slipped by the same amount as the finish, which fits a late start carried "
                   "forward rather than durations that grew.")
        else:
            txt = (f"Duration and logic changes only matter where they land, so start with the driving path. In this update "
                   f"the slip grows along the chain, from {_sg(head_slip)} at its head to {_sg(fin_slip)} at the finish, "
                   "which points to durations, links or lag added downstream.")
        if outliers:
            extra = round(sum(x['slip_wd'] - fin_slip for x in outliers) / len(outliers))
            o_tfs = [x['tf'] for x in outliers if x.get('tf') is not None]
            deeper = o_tfs and fin_tf is not None and all(t < fin_tf for t in o_tfs)
            txt += (f" {_word(len(outliers), True)} activit{'ies break' if len(outliers) != 1 else 'y breaks'} the pattern: "
                    f"{'they' if len(outliers) != 1 else 'it'} slipped about {extra} wd more than the finish"
                    + (f", and {'their' if len(outliers) != 1 else 'its'} float ({_sg(max(o_tfs))}"
                       + (f" to {_sg(min(o_tfs))}" if len(set(o_tfs)) > 1 else '') + f") is deeper than the finish's "
                       f"{_sg(fin_tf)}" if deeper else '')
                    + ". There are two possible explanations. Either they really slipped further (a duration or logic "
                      "change, which the two-file diff will show), or they run on a calendar with more working days a "
                      "week, so the same gap counts as more days."
                    + (f" Check their calendar in P6 before you quote {_sg(min(o_tfs))}." if o_tfs else ''))
        dp.append(txt)
    if lagged:
        dp.append(f"On logic, the quiet way a date moves is lag. This network carries {_i(lagged)} lags"
                  + (f", {_i(lag_crit)} of them on the critical path" if lag_crit else '')
                  + (f" and {_i(long_n)} longer than {lag_thr} wd" if long_n else '')
                  + f". A lag added, lengthened or removed on {chain_lbl if chain else 'the driving path'} between "
                    "revisions moves the finish without any visible 'delay' activity. That is the first logic bucket to "
                    "open in the diff.")
    elif not chain:
        dp.append("Durations and logic changes are read on the driving path; without the file re-read and the lag "
                  "audit, the two-file comparison is the place to open them.")
    trows = []
    if chain:
        pick = [head] if head else []
        pick += outliers[:3]
        mids = [x for x in chain if not _is_ms(x) and x['id'] not in out_ids and (not head or x['id'] != head['id'])]
        if mids:
            step = max(1, len(mids) // 4)
            pick += mids[step::step][:3] + [mids[-1]]
        ends = [x for x in chain if _is_ms(x)]
        pick += ends[-1:]
        uniq = {}
        for x in pick:
            uniq.setdefault(x['id'], x)
        ordered = sorted(uniq.values(), key=lambda x: (_dt(x.get('baseline_finish')) or datetime.max, x['id']))
        for j, x in enumerate(ordered[:10]):
            label = f"{x['id']} {_nm(x)}" + (f" — {x.get('pct')}%" if x is head else '')
            trows.append([label, f"{x.get('baseline_finish') or '—'} → {x.get('finish') or '—'}", _sg(x.get('slip_wd')),
                          _sg(x.get('tf'))])
    all_zero = chain and all((x.get('pct') or 0) == 0 for x in chain)
    s5 = K.sec('Durations & logic on the driving path', *dp,
               table=K.tbl(['Activity', 'Baseline finish → forecast', 'Slip (wd)', 'Total float'], trows,
                           "Real rows from this update, current forecast against its own baseline dates."
                           + (' All are 0% complete.' if all_zero else '')
                           + " Whether a duration or link changed between baseline revisions comes from the two-file diff."))

    # ── 6. WBS, calendar & milestones ───────────────────────────────────────────
    tree = {}
    for b in ((N.get('wbs_top') or []) if nok else []):
        parts = [p for p in (b.get('branch') or '').split(' / ') if p]
        if parts:
            tree.setdefault(parts[0], [0, []])
            tree[parts[0]][0] += b.get('activities') or 0
            if len(parts) > 1 and parts[-1] not in tree[parts[0]][1]:
                tree[parts[0]][1].append(parts[-1])
    l1s = sorted(tree.items(), key=lambda kv: -kv[1][0])
    w1 = ''
    if l1s:
        main = [f"{k} ({', '.join(v[1][:4])})" if v[1] else k for k, v in l1s[:2]]
        others = [k for k, _ in l1s[2:]]
        w1 = ("WBS: the current tree is " + '; '.join(main) + (f", plus {_join(others)}" if others else '') + '. '
              "If the prior revision grouped work differently, the comparison maps the old tree to the new one, so a "
              "reshuffle doesn't read as a change. ")
    else:
        w1 = ("WBS: a reshuffle between revisions is mapped old tree to new in Baseline Revision Comparison, so it "
              "doesn't read as a change. ")
    w1 += ((f"Calendars: the file has {_i(F['calendar_count'])}. " if F.get('calendar_count') else 'Calendars: ')
           + "The comparison matches them by working pattern, not by name, and highlights only new non-working days or "
             "shorter hours. A calendar cut is a silent duration extension.")
    kd_rows, w2 = [], ''
    if key_dates:
        kd_rows = [[f"{x['id']} {_name(x)}", f"{x['baseline_finish']} → {x.get('finish') or '—'}", _sg(x['slip_wd']),
                    _sg(x.get('tf'))] for x in key_dates[:16]]
        late_kd = [x for x in key_dates if x['slip_wd'] > 0]
        lo = min(key_dates, key=lambda x: x['slip_wd'])
        hi = max(key_dates, key=lambda x: x['slip_wd'])
        not_drv = [x for x in late_kd if (x.get('tf') or 0) >= 0]
        w2 = ("Milestones are where this one file says the most. Each key date carries its baseline, so the slip can be "
              f"read directly (table). "
              + (f"All {len(key_dates)} open key dates are late" if len(late_kd) == len(key_dates) else
                 f"{len(late_kd)} of the {len(key_dates)} open key dates are late")
              + (f", from {_sg(lo['slip_wd'])} on {_name(lo)} to {_sg(hi['slip_wd'])} on {_name(hi)}" if late_kd else '')
              + '.')
        if not_drv:
            nd = ([_name(x) for x in not_drv] if len(not_drv) <= 5 else
                  [_name(x) for x in not_drv[:4]] + [f"{len(not_drv) - 4} more"])
            w2 += (f" {_word(len(not_drv), True)} of them ({_join(nd)}) still carr{'y' if len(not_drv) != 1 else 'ies'} "
                   "positive float, so they are late but not driving.")
        w2 += (" One limit: these are the schedule's own key dates against its baseline. "
               + ("No contract milestones are loaded in the tool, so comparing them to contract dates needs those dates entered."
                  if contract_ms == 0 else "Comparing them to contract dates needs the contract dates entered in the tool."))
        hi_note = (f"{_name(hi)} slipped the most ({_sg(hi['slip_wd'])}) but still has {_sg(hi['tf'])} float, so it isn't driving."
                   if (hi.get('tf') or 0) >= 0 and hi['slip_wd'] > 0 else
                   f"{_name(hi)} slipped the most ({_sg(hi['slip_wd'])}).")
    s6 = K.sec('WBS, calendar & milestones', w1, w2,
               table=K.tbl(['Key date', 'Baseline → forecast', 'Slip (wd)', 'Total float'], kd_rows,
                           f"Real key dates from this update. {hi_note}") if kd_rows else None)

    # ── 7. client inputs ────────────────────────────────────────────────────────
    s7 = None
    if late_in:
        neg_in = [x for x in late_in if (x.get('tf') or 0) < 0]
        c1 = (f"Part of what changed since the baseline is on the client's side, and a planning manager has to separate it "
              f"out. {_word(len(late_in), True)} input{'s' if len(late_in) != 1 else ''} the Employer owes "
              f"{'are' if len(late_in) != 1 else 'is'} "
              + (f"{min(sl_in)} to {max(sl_in)}" if len(sl_in) > 1 else f"{sl_in[0]}") + " working days late"
              + (', all of them on negative-float paths' if len(neg_in) == len(late_in) and len(late_in) > 1 else
                 f", {len(neg_in)} of them on negative-float paths" if neg_in else '') + ' (table).')
        if late_done:
            ds = [x['slip_wd'] for x in late_done]
            c1 += (f" {_word(len(late_done), True)} more client input{'s' if len(late_done) != 1 else ''} arrived "
                   + (f"{min(ds)}–{max(ds)}" if len(ds) > 1 else f"{ds[0]}") + " wd late; they have now been delivered.")
        if on_bl_open:
            c1 += (f" {_word(len(on_bl_open), True)} other open client input{'s are' if len(on_bl_open) != 1 else ' is'} "
                   "still on baseline dates.")
        c2 = ''
        if fin_tf is not None and tfs_in:
            on_chain = [x for x in late_in if x.get('tf') is not None and x['tf'] <= fin_tf + (N.get('chain_band') or 5)]
            at_dd = [x for x in late_in if dd and _dt(x.get('finish')) == dd]
            near = min(late_in, key=lambda x: x.get('tf') if x.get('tf') is not None else 10 ** 6)
            c2 = ('Two honest limits. First, ' + (
                f"none of these inputs is on the {_sg(fin_tf)} finish chain as this snapshot shows it: their paths run from "
                f"{_sg(max(tfs_in))} to {_sg(min(tfs_in))}. The finish is driven by {chain_lbl} itself."
                if not on_chain else
                f"{_join([_name(x) for x in on_chain[:3]])} {'sit' if len(on_chain) > 1 else 'sits'} on the finish chain "
                f"itself, so {'they' if len(on_chain) > 1 else 'it'} drive{'' if len(on_chain) > 1 else 's'} the date "
                "directly."))
            if at_dd:
                c2 += (f" Second, the {'inputs' if len(at_dd) > 1 else 'input'} still at 0% "
                       f"{'are' if len(at_dd) > 1 else 'is'} forecast at the data date ({dd_s}), which means the schedule "
                       "assumes they arrive today. Each week they don't, the paths behind them slip further.")
            if near.get('tf') is not None and not on_chain:
                c2 += (f" {_name(near)} ({_sg(near['tf'])}) is only about {near['tf'] - fin_tf} wd from the finish "
                       f"chain's {_sg(fin_tf)}.")
        c3 = ("So a re-plan that moves because employer inputs moved is a legitimate re-plan, not gaming. These late "
              "inputs on negative-float paths are strong EOT indicators, but one snapshot can't prove how much of the "
              f"{_i(d) + ' wd' if behind else 'slip'} they caused. That split needs a TIA or windows analysis (Consultant "
              "Review, Update vs Update).")
        crow = [[f"{x['id']} {_name(x)}" + (f" — {x.get('pct')}%" if j == 0 else ''),
                 f"{x.get('baseline_finish') or '—'} → {x.get('finish') or '—'}", _sg(x.get('slip_wd')), _sg(x.get('tf'))]
                for j, x in enumerate(late_in[:10])]
        all0 = all((x.get('pct') or 0) == 0 for x in late_in)
        s7 = K.sec('Client inputs that moved since the baseline', c1, c2, c3,
                   table=K.tbl(['Client input', 'Baseline → forecast', 'Slip (wd)', 'Total float'], crow,
                               "Real rows from the client / employer input activities." + (' All are 0% complete.' if all0 else '')
                               + (f" A forecast of {dd_s} means the input is outstanding and is being carried at the data date."
                                  if any(dd and _dt(x.get('finish')) == dd for x in late_in) else '')))
    elif nok and N.get('client_inputs'):
        s7 = K.sec('Client inputs that moved since the baseline',
                   f"None of the {len(N['client_inputs'])} client / employer input activities in the file is open and late "
                   "against its baseline, so the movement since the baseline reads as the contractor's own work. A re-plan "
                   "can't lean on employer delay here.")

    # ── 8. material vs cosmetic ─────────────────────────────────────────────────
    honest_now = (fin_slip or 0) > 0 and (bool(neg) or (fin_tf is not None and fin_tf < 0))
    if honest_now:
        lead8 = (f"**On the evidence in this file, the update shows an honest, material slip. The finish moves "
                 f"{_i(fin_slip)} wd"
                 + (f", the lateness shows openly as negative float on {_i(neg)} activities" if neg else '')
                 + (f", and it traces to a late start at {_nm(head)} rather than to a date held in place" if (head and late_start) else '')
                 + ". Proving nothing was dressed up between baseline revisions still needs both files.**")
    elif behind:
        lead8 = ("**This update reports a real slip in its headline numbers. Whether it is shown honestly activity by "
                 "activity, and whether anything was dressed up between revisions, needs the file re-read and both "
                 "revision files.**")
    else:
        lead8 = ("**An update that reports no slip, or a gain, is the one to test hardest: a material recovery moves "
                 "durations, logic, crews or the finish; a cosmetic one only makes the same schedule look different.**")
    mrows = []
    if key_dates and nok and fin:
        mrows.append(['Finish or key dates moved', 'Material' if (fin_slip or 0) != 0 else 'No move',
                      f"{fin['id']} {_sg(fin_slip)} wd; key dates {_sg(min(x['slip_wd'] for x in key_dates))} to "
                      f"{_sg(max(x['slip_wd'] for x in key_dates))} wd"])
    elif d is not None:
        mrows.append(['Finish moved', 'Material' if behind else ('Material (gain) — test it' if ahead else 'No move'),
                      _pos(d) + ' against the baseline finish'])
    if neg is not None:
        mrows.append(['Lateness shown as negative float, not hidden', 'Honest' if neg and behind else 'Check',
                      f"{_i(neg)} activities ({_pc(neg_pct)})"
                      + (f"; finish float {_sg(fin_tf)}; finish date allowed to move to {fc}" if (nok and fin_tf is not None and fc) else '')])
    if oos is not None:
        mrows.append(['Progress recorded ahead of logic (out-of-sequence)', 'Watch' if oos else 'Clean',
                      f"{_i(oos)} ({_pc(oos_pct)}), {_i(crit_oos)} on the critical path"
                      + (f", {pkg_n} of {_i(oos)} in {pkg}" if pkg else '')])
    if lagged is not None:
        mrows.append(['Lag on the critical run', 'Watch' if lag_crit else 'Clean',
                      f"{_i(lag_crit)} critical-path lags; {_i(long_n)} lags over {lag_thr} wd"])
    mrows += [['Same ObjectId, new name or code', 'Cosmetic (renamed)', 'Needs both baseline files'],
              ['Count up, man-hours/budget flat', 'Cosmetic (re-cut)', 'Needs both baseline files']]
    n_read = len(mrows) - 2
    s8 = K.sec('Material vs cosmetic — the test', lead8,
               "A material change moves something real: durations, logic, man-hours, budget or the finish date. A "
               "cosmetic change makes the same schedule look different: activities renamed, the same ObjectId relabelled, "
               "work split into more lines with identical totals, or calendar tweaks that never touch the driving path. "
               "Baseline Revision Comparison flags renamed-same-ID items directly (same P6 ObjectId, new name or code), "
               "which is the classic 'looks new, isn't' move.",
               "One caution with P6 exports: an activity code can appear twice, under two ObjectIds. The comparison "
               "therefore matches on ObjectId, not code. Otherwise a rename check silently keys on the wrong copy.",
               table=K.tbl(['Signal', 'Reads as', 'In this update'], mrows,
                           (f"The first {_word(n_read)} rows read from this update" if n_read != 1 else
                            "The first row reads from this update") + "; the last two need the prior revision loaded."))

    # ── 9. manipulation & DCMA-quality ──────────────────────────────────────────
    q = ["The other tell is whether schedule quality got better or worse across the revision. A re-baseline that "
         "'recovers' the date while the network degrades is hiding slip behind poorer quality, not recovering. "
         "Degrading means more leads, broken logic, constraints or out-of-sequence progress."]
    if F.get('has_audit') and F.get('audit'):
        flags = _join([f"{_i(leads)} leads" if leads is not None else '', f"{_i(oe)} open ends" if oe is not None else '',
                       ('no dangling activities' if dang == 0 else
                        f"only {_i(dang)} dangling activities ({_pc(dk.get('dangling_pct'))})") if dang is not None else '',
                       ('no out-of-sequence progress' if oos == 0 else
                        f"{_i(oos)} out-of-sequence ({_pc(oos_pct)}, {_i(crit_oos)} critical)") if oos is not None else ''])
        surface = _join([f"{_i(neg)} activities on negative float ({_pc(neg_pct)})" if neg else '',
                         f"{_i(crit_cnt)} at critical float ({_pc(crit_pct)}"
                         + (f", {str(ck.get('critical_density_grade')).lower()}" if ck.get('critical_density_grade') else '') + ')'
                         if crit_cnt is not None else '',
                         f"float grade {float_grade}" if float_grade else '',
                         f"CPLI {K.ratio(cpli)} against the {K.ratio(tgt)} target" if cpli is not None else ''])
        masked = bool(neg) or behind
        q.append((f"This update's quality flags point to a schedule that {'reports its lateness rather than masks it' if masked else 'is not hiding slip'}."
                  + (f" It has {flags}." if flags else '')
                  + (f" The lateness is on the surface: {surface}." if (surface and masked) else '')))
        weak = _join([(f"lag density is {_pc(lag_pct)}"
                       + (f" ({_word(round((_num(lag_pct) or 0) / 5))} times the 5% line)" if (_num(lag_pct) or 0) >= 10 else ' (over the 5% line)')
                       + (f" with {_i(lag_crit)} lags on the critical path" if lag_crit else '')) if (_num(lag_pct) or 0) > 5 else '',
                      f"{_pc(fs)} of links are FS" if (fs is not None and fs < 90) else '',
                      "the constraint list isn't part of this read" if not hard_known else ''])
        q.append((f"The weak spots are where a future revision could hide slip: {weak}. " if weak else '')
                 + "When the next revision arrives, compare these KPIs one by one. If lags are removed, leads appear, "
                   "dangling rises or a finish constraint is added while the date holds, call it slip dressed up.")
    else:
        q.append("No Schedule Audit is stored with this snapshot, so I can't give you its quality baseline to compare "
                 "against. Run the Schedule Audit on each revision, then compare leads, lags, dangling, constraints and "
                 "out-of-sequence one by one: if they worsen while the date holds, call it slip dressed up.")
    s9 = K.sec('Manipulation & DCMA-quality check', *q)

    # ── 10. genuine recovery vs slip dressed up ─────────────────────────────────
    g = []
    if behind or (fin_slip or 0) > 0:
        if cpli is not None and cpl and ptf is not None and ptf < 0:
            frac = abs(ptf) / cpl
            fw = ('about a quarter' if 0.2 <= frac < 0.3 else 'about a third' if 0.3 <= frac < 0.4 else
                  'about half' if 0.4 <= frac < 0.6 else f"about {round(frac * 100)}%")
            txt = (f"CPLI {K.ratio(cpli)} tells you the size of any honest recovery. The remaining critical path is "
                   f"{_i(cpl)} working days, and holding {bl or 'the baseline finish'} means taking {_i(abs(ptf))} of them "
                   f"out, {fw}. A real recovery names where those days come from.")
        else:
            txt = f"Holding {bl or 'the baseline finish'} means recovering about {K.wd(fin_slip or d)}. A real recovery names where those days come from."
        if fronts:
            first = fronts[0][0]
            civ = [lab for lab, _ in fronts[:2]]
            txt += (f" On {chain_lbl} that means {_join(civ)} first (from {_nmc(head)} on)"
                    + (f"; after that come {_join([lab for lab, _ in fronts[2:6]])}" if len(fronts) > 2 else '') + '.')
        txt += (" Each cut needs a mechanism behind it: resequenced logic, a second crew or formwork set behind a duration "
                "cut" + (', or relief on the late client inputs.' if late_in else '.'))
        if behind_paths:
            txt += (" Float on the paths just behind (" + ', '.join(f"{_sg(x['tf'])} {_name(x)}" for x in behind_paths[:3])
                    + ') also has to improve.')
        g.append(txt)
        if len(fronts) > 1:
            g.append("One lever to check in P6: where consecutive areas on the chain share one crew, rig or formwork set, "
                     "part of the link between them is crew sequence, not physical dependency. A second crew can break "
                     "such a link legitimately; deleting the link without adding the crew is dressed up.")
        g.append("Slip dressed up keeps the same lateness but hides it. The signs are durations cut with no crew plan, "
                 f"lags stripped from {chain_lbl if chain else 'the driving path'}, a finish constraint pinning "
                 f"{bl or 'the baseline finish'}"
                 + (f", or progress claimed on {_nm(head)} without site evidence" if head else ', or progress claimed without site evidence')
                 + ". Which pattern applies comes from the two revisions side by side.")
    else:
        g.append("A revision that shows a gain must name where it came from: resequenced logic, added crews or shifts, a "
                 "shorter scope. If the finish improves while durations are cut with no crew plan, lags are stripped, or "
                 "a finish constraint appears, the gain is on paper only.")
        g.append("Which pattern applies comes from the two revisions side by side in Baseline Revision Comparison.")
    s10 = K.sec('Genuine recovery vs slip dressed up — the verdict rule', *g)

    # ── 11. honest by F9? ───────────────────────────────────────────────────────
    h = []
    spi_s = f"SPI is {K.ratio(F.get('spi'))} ({K.pct(F.get('actual_pct'))} earned against {K.pct(F.get('planned_pct'))} planned)"
    if behind:
        h.append(f"From this update: yes, it reads as genuinely behind and reported as such. {spi_s} and the finish sits "
                 f"{_i(d)} wd past {bl or 'its baseline'}."
                 + (f" The first activity on the finish chain, {_nm(head)}, was due on {head.get('baseline_finish')}. It is "
                    f"reported at {head.get('pct')}% and re-forecast to {head.get('finish')} rather than given progress on paper."
                    if (head and head.get('baseline_finish')) else ''))
    elif ahead:
        h.append(f"From this update it reads as ahead: {spi_s} and about {K.wd(d)} of float to the finish. An ahead "
                 "report deserves the same scrutiny as a late one: progress claimed must match site measurement, and no "
                 "constraint may be holding the finish.")
    else:
        h.append(f"From this update: {spi_s}, with the finish {K.delay_phrase(F)}.")
    at_dd_in = [x for x in late_in if dd and _dt(x.get('finish')) == dd]
    if at_dd_in and behind:
        latest = max(late_in, key=lambda x: _dt(x.get('finish')) or datetime.min)
        h.append("If anything, the forecast leans optimistic. The outstanding client inputs are carried at the data date, "
                 "so each update they stay outstanding pushes their paths further."
                 + (f" The {_sg(d)} holds only if {_name(latest)} (forecast {latest.get('finish')}) and the other inputs close."
                    if latest.get('finish') else ''))
    chk = [f"First, overstated progress: the XML can't confirm physical progress, so compare claimed % against site "
           f"measurement{' on the ' + drv['name'] + ' scope' if drv else ''}."
           + (f" Out-of-sequence progress is {'low' if (_num(oos_pct) or 0) <= 5 else 'high'} ({_i(oos)}"
              + (f", mostly in {pkg}" if pkg else '') + ")"
              + (", which is reassuring but not proof." if (_num(oos_pct) or 0) <= 5 else ", which needs explaining before you accept it.")
              if oos is not None else '')]
    unprog = ((", and every activity on the chain is unprogressed" if not_started == len(chain) else
               f", and {not_started} of the {len(chain)} activities on the chain are unprogressed") if chain and not_started else '')
    chk.append(f"Second, was the update actually rescheduled (F9) before it was issued? The {_pos(d)} is P6's own "
               "figure from the dates in this file, but an update issued without a final F9 carries stale dates"
               + unprog + ". Reschedule it in P6 and confirm the finish still reads the same.")
    h.append('Two checks remain. ' + ' '.join(chk))
    s11 = K.sec("Is the contractor's update honest by F9?", *h)

    # ── measured / actions / evidence ───────────────────────────────────────────
    ms_ids = _join([f"{_name(x)} {x['id']}" for x in [x for x in chain if _is_ms(x)][-1:]] + ([f"{_name(fin)} {fin['id']}"] if fin else []))
    measured = ("From this update, each activity's current finish is compared with the baseline finish carried in the same "
                "file. Slips are in working days; total float is P6's, read in each activity's own calendar. "
                + (f"The {_sg(d)} wd delay is the total float of the finish milestone ({ms_ids}) in its own calendar. "
                   if (nok and fin and d is not None and fin_tf is not None and round(-fin_tf) == round(d)) else
                   "The delay is the finish milestone's forecast against its baseline in working days. ")
                + ("The finish-driving chain and the most-negative-float list come from the tool's own path trace. " if nok else '')
                + ("The float, negative-float, out-of-sequence, dangling, open-end, lag and CPLI figures come from the "
                   "tool's DCMA checks on this file. " if F.get('has_audit') and F.get('audit') else '')
                + (f"CPLI = (critical path length {_i(cpl)} wd + total float {_sg(ptf)}) ÷ {_i(cpl)} = {K.ratio(cpli)}. "
                   if (cpli is not None and cpl and ptf is not None) else '')
                + f"SPI is category-weighted actual % ÷ planned % ({K.pct(F.get('actual_pct'))} ÷ {K.pct(F.get('planned_pct'))}). "
                  "Planned % is re-derived from baseline dates because P6 XML omits Schedule %/PV/EV. Revision-to-revision "
                  "buckets (added/deleted, renamed-same-ID, WBS remap, calendar diff, man-hour and budget deltas) come only "
                  "from Baseline Revision Comparison with both files loaded. It matches activities on P6 ObjectId, matches "
                  "calendars on working pattern, and counts man-hours as labour only."
                + (" Employer vs contractor responsibility for the slip is not derivable from one snapshot." if behind else ''))
    sl_fmt = ', '.join(f"{_short(_name(x))} {_sg(x['slip_wd'])}" for x in late_in[:7])
    neg_in_tf = [x for x in late_in if x.get('tf') is not None and x['tf'] < 0]
    chase = min(neg_in_tf, key=lambda x: x['tf']) if (neg_in_tf and fin_tf is not None) else None
    actions = [
        (f"Lead the report with one line: {_name(fin)} {bl} → {fc} ({_sg(fin_slip)} wd)."
         + (f" The slip starts at {_nmc(head)} ({head.get('pct')}%, due {head.get('baseline_finish')})"
            + (f" and carries through {_join([f for f, _ in fronts[1:]])}." if len(fronts) > 1 else '.') if head else ''))
        if (nok and fin and bl and fc) else
        (f"Lead the report with the position: {_pos(d)} against the baseline finish, SPI {K.ratio(F.get('spi'))}."
         if d is not None else ''),
        "Load the previous baseline revision beside this update in Baseline Revision Comparison. That gives the true "
        "revision-to-revision headline plus the scope, WBS and calendar buckets this one file can't give.",
        ((f"In the diff, open lags first: {_i(lag_crit)} sit on the critical path." if lag_crit else 'In the diff, open lags first.')
         + (f" Then check the {_word(len(outliers))} activit{'ies' if len(outliers) != 1 else 'y'} that slipped more than the "
            f"finish: " + _join([f"{_nmc(x)} ({_sg(x['slip_wd'])})" for x in outliers[:3]])
            + '. Confirm their calendars before quoting ' + _sg(min((x['tf'] for x in outliers if x.get('tf') is not None), default=0)) + '.'
            if outliers else '')),
        (f"Trace {_nm(head)}'s predecessors in P6. Is its late start tied to an employer input or to crew movement? That "
         "decides whose slip the head of the chain is.") if (head and late_start and behind) else '',
        (f"Log the late client inputs with baseline and forecast dates: {sl_fmt}. Issue notices and treat them as EOT "
         "indicators. Send the employer vs contractor split to Consultant Review / Update vs Update for a TIA.") if late_in else '',
        (f"Chase {_name(chase)} hardest: its path is at {_sg(chase['tf'])}, about {chase['tf'] - fin_tf} wd from "
         f"co-driving the finish, and it's forecast for {chase.get('finish')}.") if chase else '',
        (f"Reject any revision that holds {bl} without named changes on {chain_lbl}"
         + (f" and the {_sg(behind_paths[0]['tf'])} to {_sg(behind_paths[min(2, len(behind_paths) - 1)]['tf'])} paths behind it"
            if behind_paths else '')
         + (f". CPLI {K.ratio(cpli)} means {_i(abs(ptf))} of the {_i(cpl)} remaining critical-path days must come out."
            if (cpli is not None and cpl and ptf is not None and ptf < 0) else '.')) if (behind and bl) else '',
        "At each new revision, compare the quality KPIs (lags, leads, dangling, constraints, out-of-sequence). If they get "
        "worse while the date holds, call it slip dressed up.",
        f"Reschedule the update in P6 (F9) and confirm the {_pos(d)} holds — that proves the contractor issued "
        "a scheduled update, not stale dates."]
    evidence = [K.ev(f"Finish ({fin['id']})" if fin else 'Finish', f"{bl} → {fc} ({_sg(fin_slip)} wd)" if (fin and bl and fc)
                     else K.signed(d)),
                K.ev('Chain head', f"{head['id']} {_nm(head)}, {head.get('pct')}%, {_sg(head_slip)} wd, TF {_sg(head.get('tf'))}"
                     if head else None),
                K.ev('Chain slip', f"{_sg(c_lo)} to {_sg(c_hi)} wd first to last"
                     + (' (late start, not stretched)' if late_start else '') if c_lo is not None else None),
                K.ev('Deepest float', '; '.join(f"{_nm(x)} {_sg(x['tf'])}" for x in sorted(outliers, key=lambda x: x['tf'])[:2])
                     if outliers else None),
                K.ev('Next paths', ' · '.join(f"{_name(x)} {_sg(x['tf'])}" for x in behind_paths[:3]) if behind_paths else None),
                K.ev('Key dates', f"{_sg(min(x['slip_wd'] for x in key_dates))} to {_sg(max(x['slip_wd'] for x in key_dates))} wd"
                     if key_dates else None),
                K.ev('Client inputs', f"{len(late_in)} late, {_sg(min(sl_in))} to {_sg(max(sl_in))} wd; paths "
                     f"{_sg(max(tfs_in))} to {_sg(min(tfs_in))}" if (len(sl_in) > 1 and tfs_in) else None),
                K.ev('Negative float', f"{_i(neg)} ({_pc(neg_pct)})" if neg is not None else None),
                K.ev('Critical float', f"{_i(crit_cnt)} ({_pc(crit_pct)})" if crit_cnt is not None else None),
                K.ev('CPLI', f"{K.ratio(cpli)} (target {K.ratio(tgt)})" + (f"; path {_i(cpl)} wd" if cpl else '')
                     if cpli is not None else None),
                K.ev('Lags', f"{_i(lagged)} ({_pc(lag_pct)}); {_i(lag_crit)} critical; {_i(long_n)} > {lag_thr} wd"
                     if lagged is not None else None),
                K.ev('OOS / dangling / open ends', f"{_i(oos)} ({_i(crit_oos)} critical) / {_i(dang)} / {_i(oe)}"
                     if oos is not None else None),
                K.ev('Activities', _i(acts) if acts else None),
                K.ev('SPI', f"{K.ratio(F.get('spi'))} ({K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))})"),
                K.ev('Revision diff', 'needs both baselines (match on ObjectId)')]
    a = K.A2(verdict, [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11], pills=pills, measured=measured, actions=actions,
             evidence=evidence,
             drilldowns=[K.drill('q04', 'Which chain drives the finish, and how much float is left behind it?'),
                         K.drill('q13', 'Do the late client inputs give me an EOT case?') if late_in else
                         K.drill('q03', 'Is the delay real, and how did it build up?'),
                         K.drill('q05', f"How do I recover the ~{_i(d)} days?") if behind else
                         K.drill('q02', 'When will we finish, and will we hit the dates?'),
                         K.drill('q06', 'Is the schedule logic healthy enough to trust?')])
    if len(thinking) < 2:
        thinking.append('Separated what one file can show (movement against its own baseline) from what needs both '
                        'revision files (the revision diff)')
    a['thinking'] = thinking[:4]
    return a
