"""q06 — Is the schedule healthy and reliable — and which logic problems do I fix?

Covers: the DCMA 14-point scorecard as far as this snapshot can score it (logic, leads, lags,
relationship mix, constraints, float, negative float, durations, missed tasks, critical-path test,
CPLI, BEI), logic health in plain English, consultant-readiness, statusing, the counted logic
problems with their fix route, what moves the finish versus what is cosmetic, and whether the
schedule is reliable enough to report off — for ANY project. Every count comes from the stored
Schedule Audit (F['audit']) and the network re-read (N); nothing is assumed.
"""
import math
import re
from datetime import datetime

from . import _kit2 as K

MINUS = '−'


# ── small, None-safe helpers ─────────────────────────────────────────────────────

def _k(F, mod):
    return (((F.get('audit') or {}).get(mod) or {}).get('kpis')) or {}


def _grade(F, mod):
    return ((F.get('audit') or {}).get(mod) or {}).get('grade')


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


def _short(v):
    n = _num(v)
    if n is None:
        return '—'
    for div, suf in ((1e9, 'B'), (1e6, 'M'), (1e3, 'k')):
        if abs(n) >= div:
            return f"{n / div:.1f}{suf}"
    return f"{n:,.0f}"


def _join(items):
    items = [i for i in items if i]
    if not items:
        return ''
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]


def _last_wbs(x):
    parts = [p for p in (x.get('wbs') or '').split(' / ') if p]
    return parts[-1] if parts else ''


def _name(x):
    return ' '.join(((x or {}).get('name') or '').split())


def _word(n, cap=False):
    """Small counts as words at the start of a sentence ('Seven'), larger ones as digits."""
    w = {0: 'none', 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight',
         9: 'nine', 10: 'ten', 11: 'eleven', 12: 'twelve'}.get(n, f"{n:,}" if isinstance(n, int) else str(n))
    return w[0].upper() + w[1:] if cap else w


def _join_or(items):
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else (', '.join(items[:-1]) + ' or ' + items[-1] if items else '')


def _nm(x):
    """Activity name, disambiguated by its short WBS leaf when that helps ('Drilling For Piles (Area 9)')."""
    name = _name(x)
    leaf = _last_wbs(x)
    if leaf and len(leaf) <= 12 and leaf.lower() not in name.lower():
        return f"{name} ({leaf})"
    return name


def _chain_fronts(chain):
    """Work fronts along the finish chain, in order of first appearance: ([(label, rows)], scope_label).
    The label is the most specific WBS level that differs between fronts; scope_label is the deepest
    level the whole chain shares (e.g. the phase or area it all sits in)."""
    tasks = [x for x in chain if 'Milestone' not in (x.get('type') or '')]
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


# ── the DCMA 14-point scorecard, from the stored audit ──────────────────────────

def _scorecard(F, N, nok, fin, chain_n):
    dk, ek, lk, llk = _k(F, 'dangling'), _k(F, 'open_ends'), _k(F, 'leads'), _k(F, 'lag_lead')
    rk, hk, fk, nk = _k(F, 'relationship_types'), _k(F, 'hard_constraints'), _k(F, 'float'), _k(F, 'negative_float')
    hdk, ck, cik = _k(F, 'high_duration'), _k(F, 'cpli'), _k(F, 'circular')
    rows = []

    def add(no, label, value, status, state):
        rows.append({'no': no, 'label': label, 'value': value, 'status': status, 'state': state})

    # 1 — logic (missing predecessor / successor)
    if dk or ek:
        parts = []
        if dk.get('total_dangling') is not None:
            s = f"{_i(dk['total_dangling'])} dangling ({_pc(dk.get('dangling_pct'))})"
            br = [f"{_i(dk[key])} {w}" for key, w in (('start_dangling', 'start'), ('finish_dangling', 'finish'),
                                                     ('both_dangling', 'both')) if dk.get(key)]
            if br and dk['total_dangling']:
                s += ': ' + ', '.join(br)
            parts.append(s)
        if ek.get('open_ends') is not None:
            parts.append(f"{_i(ek['open_ends'])} open ends")
        miss = (_num(dk.get('dangling_pct')) or 0) + (_num(ek.get('open_end_pct')) or 0)
        add(1, 'Logic (missing predecessor / successor)', '; '.join(parts), 'Pass' if miss <= 5 else 'FAIL',
            'pass' if miss <= 5 else 'fail')
    else:
        add(1, 'Logic (missing predecessor / successor)', 'not in this snapshot', 'Run Schedule Audit', 'na')

    # 2 — leads
    leads = llk.get('leads_count') if llk.get('leads_count') is not None else lk.get('leads')
    if leads is not None:
        add(2, 'Leads (negative lag)', _i(leads), 'Pass' if not leads else 'FAIL', 'pass' if not leads else 'fail')
    else:
        add(2, 'Leads (negative lag)', 'not in this snapshot', 'Run Schedule Audit', 'na')

    # 3 — lags
    if llk.get('lagged_count') is not None:
        line = _num(llk.get('dcma_lag_line')) or 5.0
        bits = [f"{_i(llk['lagged_count'])} links ({_pc(llk.get('lagged_pct'))})"]
        if llk.get('long_count'):
            bits.append(f"{_i(llk['long_count'])} over {_i(llk.get('long_threshold_days') or 14)} wd")
        if llk.get('critical_count'):
            bits.append(f"{_i(llk['critical_count'])} on the critical path")
        ok = (_num(llk.get('lagged_pct')) or 0) <= line
        add(3, f"Lags (≤{_pc(line)})", '; '.join(bits), 'Pass' if ok else 'FAIL', 'pass' if ok else 'fail')
    else:
        add(3, 'Lags (≤5%)', 'not in this snapshot', 'Run Schedule Audit', 'na')

    # 4 — relationship types
    fs = _num(rk.get('fs_pct'))
    if fs is not None:
        mix = ' · '.join(f"{t} {_pc(rk.get(key))}" for t, key in (('FS', 'fs_pct'), ('SS', 'ss_pct'), ('FF', 'ff_pct'),
                                                                   ('SF', 'sf_pct')) if rk.get(key) is not None)
        if rk.get('non_fs') is not None:
            mix += f" ({_i(rk['non_fs'])} non-FS)"
        ok = fs >= 90
        add(4, 'Relationship types (FS ≥90%)', mix, 'Pass' if ok else f"FAIL ({90 - fs:.1f} pts short)",
            'pass' if ok else 'fail')
    else:
        add(4, 'Relationship types (FS ≥90%)', 'not in this snapshot', 'Run Schedule Audit', 'na')

    # 5 — hard constraints (only when the audit actually counted them)
    if hk.get('hard_count') is not None:
        ok = (_num(hk.get('hard_pct')) or 0) <= 5
        add(5, 'Hard constraints (≤5%)', f"{_i(hk['hard_count'])} ({_pc(hk.get('hard_pct'))})",
            'Pass' if ok else 'FAIL', 'pass' if ok else 'fail')
    else:
        add(5, 'Hard constraints (≤5%)', 'not computed in this snapshot', 'Run Schedule Audit', 'na')

    # 6 — high float
    if fk.get('above_threshold') is not None:
        thr = _i(fk.get('threshold') or 44)
        v = f"{_i(fk['above_threshold'])} ({_pc(fk.get('float_pct'))})"
        if fk.get('max_float') is not None:
            v += f"; highest {_i(fk['max_float'])} wd"
        ok = (_num(fk.get('float_pct')) or 0) <= 5
        add(6, f"High float (>{thr} wd, ≤5%)", v, 'Pass' if ok else 'FAIL', 'pass' if ok else 'fail')
    else:
        add(6, 'High float (>44 wd, ≤5%)', 'not in this snapshot', 'Run Schedule Audit', 'na')

    # 7 — negative float
    if nk.get('negative_count') is not None:
        ok = not nk['negative_count']
        add(7, 'Negative float (= 0)', f"{_i(nk['negative_count'])} ({_pc(nk.get('neg_pct'))})",
            'Pass' if ok else 'FAIL', 'pass' if ok else 'fail')
    else:
        add(7, 'Negative float (= 0)', 'not in this snapshot', 'Run Schedule Audit', 'na')

    # 8 — high duration
    if hdk.get('over_threshold') is not None:
        thr = _i(hdk.get('threshold') or 44)
        v = f"{_i(hdk['over_threshold'])} ({_pc(hdk.get('high_pct'))})"
        if hdk.get('max_duration') is not None:
            v += f"; longest {_i(hdk['max_duration'])} wd"
        ok = (_num(hdk.get('high_pct')) or 0) <= 5
        add(8, f"High duration (>{thr} wd, ≤5%)", v, 'Pass' if ok else 'FAIL', 'pass' if ok else 'fail')
    else:
        add(8, 'High duration (>44 wd, ≤5%)', 'not in this snapshot', 'Run Schedule Audit', 'na')

    # 9 — invalid dates (the statusing tells live in Update Analysis)
    add(9, 'Invalid dates', 'not held in this snapshot', 'Run Update Analysis', 'na')

    # 10 — resources
    if (F.get('pv') or 0) > 0:
        add(10, 'Resources', f"budget values loaded (PV {_short(F['pv'])}); labour loading not read in this snapshot",
            'Partial', 'partial')
    else:
        add(10, 'Resources', 'no budget or resource loading read', 'Run Productivity & Resource Intelligence', 'na')

    # 11 — missed tasks: not counted by the audit; show what the re-read can see
    dd = _dt((N or {}).get('data_date') or F.get('data_date'))
    past = []
    if nok and dd:
        seen = {}
        for key in ('chain', 'deepest', 'milestones', 'client_inputs'):
            for x in N.get(key) or []:
                seen.setdefault(x['id'], x)
        if fin:
            seen.setdefault(fin['id'], fin)
        past = [x for x in seen.values() if not x.get('done') and _dt(x.get('baseline_finish'))
                and _dt(x['baseline_finish']) < dd]
        past.sort(key=lambda x: _dt(x['baseline_finish']))
    if past:
        cids = {x['id'] for x in N.get('client_inputs') or []}
        n_client = sum(1 for x in past if x['id'] in cids)
        others = [x for x in past if x['id'] not in cids]
        named = [f"{_nm(x)} due {x['baseline_finish']}" for x in others[:2]]
        if n_client:
            named.append(f"{n_client} client input{'s' if n_client != 1 else ''}")
        v = f"not counted, but at least {len(past)} open activities are past their baseline finish — " + '; '.join(named)
        add(11, 'Missed tasks', v, 'Run audit — expect a fail' if (F.get('spi') or 1) < 0.9 else 'Run audit', 'na')
    else:
        add(11, 'Missed tasks', 'not counted in this snapshot', 'Run audit', 'na')

    # 12 — critical path test (traced, not delay-injected)
    chain = (N or {}).get('chain') or []
    if nok and chain and fin:
        clean = not (_num(_k(F, 'open_ends').get('open_ends')) or 0) and not (_num(cik.get('loops')) or 0)
        add(12, 'Critical path test',
            f"unbroken {chain_n}-activity driving chain, {chain[0]['id']} → {fin['id']}" if clean else
            f"{chain_n}-activity chain traced, {chain[0]['id']} → {fin['id']}, but open ends or loops can break it",
            'Pass (traced)' if clean else 'FAIL until the logic is closed', 'pass' if clean else 'fail')
    else:
        add(12, 'Critical path test', 'not traced this time', 'Run Schedule Health Review', 'na')

    # 13 — CPLI
    cpli = _num(ck.get('cpli'))
    if cpli is not None and ck.get('cpli_computable', True):
        tgt = _num(ck.get('target')) or 0.95
        cpl, ptf = _num(ck.get('critical_path_length_days')), _num(ck.get('project_total_float_days'))
        v = K.ratio(cpli)
        if cpl and ptf is not None:
            v += f" = ({_i(cpl)} {'−' if ptf < 0 else '+'} {_i(abs(ptf))}) / {_i(cpl)}"
        if ck.get('critical_count') is not None:
            v += f"; {_i(ck['critical_count'])} activities ({_pc(ck.get('critical_pct'))}) at critical float"
        add(13, f"CPLI (≥{K.ratio(tgt)})", v, 'Pass' if cpli >= tgt else 'FAIL', 'pass' if cpli >= tgt else 'fail')
    else:
        add(13, 'CPLI (≥0.95)', 'not computed in this snapshot', 'Run Schedule Health Review', 'na')

    # 14 — BEI
    add(14, 'BEI (≥0.95)', f"not computed; SPI {K.ratio(F.get('spi'))} is the value-based proxy"
        if F.get('spi') is not None else 'not computed', 'Run audit', 'na')
    return rows, past


_SHORT = {1: 'logic', 2: 'leads', 3: 'lags', 4: 'FS mix', 5: 'constraints', 6: 'float', 7: 'float',
          8: 'durations', 12: 'critical path', 13: 'CPLI'}


def _fail_names(fails):
    names, out = [_SHORT.get(r['no'], r['label']) for r in fails], []
    for n in names:
        if n not in out:
            out.append(n)
    return [f"{n} ×{names.count(n)}" if names.count(n) > 1 else n for n in out]


# ── no stored audit: answer honestly from what is measured ──────────────────────

def _no_audit(F, N, nok):
    d = F.get('delay_days')
    behind, ahead = (d or 0) > 0, (d or 0) < 0
    fin = (N or {}).get('finish_milestone') or {}
    pos = K.delay_phrase(F) if d is not None else "not derivable from this file"
    brief = (f"{K.wd(d)} behind" if behind else f"{K.wd(d)} ahead" if ahead else 'on the date') if d is not None \
        else 'finish not derivable'
    s1 = K.sec('The 14 points — what this snapshot scores',
               "**I can't score the DCMA points yet: no Schedule Audit is stored with this snapshot, and I won't "
               "guess a pass.**",
               K.network_note(N),
               "Run the Schedule Audit on this file. It scores missing logic, leads, lags, the relationship mix, "
               "hard constraints, high float, negative float, long durations, loops and CPLI, and every finding "
               "comes with a fix you can apply and export. Invalid dates and missed tasks come from Update "
               "Analysis.")
    s2 = K.sec('Logic health, in plain English',
               f"What I can measure without the audit is the outcome, not the wiring. The schedule puts the finish "
               f"at {pos}, with SPI {K.ratio(F.get('spi'))} ({K.pct(F.get('actual_pct'))} earned against "
               f"{K.pct(F.get('planned_pct'))} planned).",
               ("A schedule that reports **ahead** deserves the checks that make one look better than it is: a "
                "date constraint holding the finish, out-of-sequence progress, and long lags standing in for work. "
                "Until the audit clears those, treat the margin as reported, not proven.") if ahead else
               ("Whether that slip is carried honestly through clean logic, or distorted by open ends, constraints "
                "or lags, is exactly what the audit answers.") if behind else
               "Whether that date is held by logic or by a constraint is exactly what the audit answers.")
    s3 = K.sec('Was it statused correctly?',
               f"Not verifiable from this snapshot. The data date is {F.get('data_date') or 'not recorded'}; run "
               "Update Analysis for the statusing tells — progress with no actual start, finished work with no "
               "actual dates, remaining duration left on completed activities, and forecasts left before the "
               "data date.")
    s4 = K.sec('Will cleaning them move the finish?',
               ("There's no slip for cleanup to recover. The risk runs the other way: removing a constraint or "
                f"closing a missing link can reveal less float than the {K.wd(d)} the schedule shows, so prove the "
                "margin after the audit, in the What-if (F9).") if ahead else
               ("Logic cleanup rarely recovers a genuine slip; it changes the date only where a defect sits on the "
                "driving path. Test any such fix in the What-if (F9) before you claim it.") if behind else
               "Logic cleanup changes the date only where a defect sits on the driving path; test it in the What-if (F9).")
    s5 = K.sec('Reliable enough to report off?',
               "Report the measured position — progress, SPI and the finish date — but not as a verified schedule. "
               "Say plainly that the logic hasn't been audited yet, run the Schedule Audit, and re-ask for the "
               "scorecard.")
    a = K.A2("I can't score the DCMA points from this snapshot: no Schedule Audit is stored with it. The headline "
             f"position — {brief}, SPI {K.ratio(F.get('spi'))} — is measured; the logic behind it isn't verified yet. "
             "Run the Schedule Audit and I'll give you the scorecard and the fix list.",
             [s1, s2, s3, s4, s5],
             pills=[K.pill('no audit stored — DCMA not scored', 'warning'),
                    K.pill(f"{K.signed(d)} · SPI {K.ratio(F.get('spi'))}", 'danger' if behind else 'success')
                    if d is not None else None,
                    K.pill('report the position, not a verified schedule', 'accent')],
             measured=("The DCMA points come from the Schedule Audit stored with a snapshot; none is stored here, so "
                       "nothing is scored. SPI = EV ÷ PV at the data date; the delay is the finish milestone's "
                       "forecast against its baseline in working days."),
             actions=['Run the Schedule Audit on this file, then ask again for the scorecard and the fix list.',
                      'Run Update Analysis for the statusing checks before you report.',
                      ('Before you bank the margin, check no date constraint is holding the finish.' if ahead else
                       'Report the position with the caveat that the logic is not yet audited.')],
             evidence=[K.ev('Audit', 'not stored'), K.ev('Delay', K.signed(d)), K.ev('SPI', K.ratio(F.get('spi'))),
                       K.ev('Data date', F.get('data_date'))],
             drilldowns=[K.drill('q01', 'Where do we stand overall?'),
                         K.drill('q04', "What's driving the date, and how much float is left?"),
                         K.drill('q12', 'Does the logic make construction sense?')])
    a['thinking'] = ['Looked for a stored Schedule Audit on this snapshot — none found',
                     'Read the measured position (SPI, delay) so the answer still says where you stand',
                     'Listed which feature scores each DCMA point instead of guessing a pass']
    return a


# ── the answer ─────────────────────────────────────────────────────────────────

def build(F, N, role):
    nok = bool(N and N.get('ok'))
    if not (F.get('has_audit') and F.get('audit')):
        return _no_audit(F, N, nok)

    d = F.get('delay_days')
    behind, ahead = (d or 0) > 0, (d or 0) < 0
    fin = ((N or {}).get('finish_milestone') or {}) if nok else {}
    chain = (N.get('chain') or []) if nok else []
    chain_n = (N.get('chain_count') or len(chain)) + (1 if fin else 0) if chain else 0
    fin_tf = N.get('finish_tf') if nok else None
    dd_s = (N.get('data_date') if nok else None) or F.get('data_date')
    dd = _dt(dd_s)
    fronts, scope = _chain_fronts(chain) if chain else ([], '')
    chain_lbl = f"the {scope} finish chain" if scope else 'the finish chain'
    thinking = []

    dk, ek, lk, llk = _k(F, 'dangling'), _k(F, 'open_ends'), _k(F, 'leads'), _k(F, 'lag_lead')
    rk, hk, fk, nk = _k(F, 'relationship_types'), _k(F, 'hard_constraints'), _k(F, 'float'), _k(F, 'negative_float')
    hdk, ck, cik, ok_, wk = (_k(F, 'high_duration'), _k(F, 'cpli'), _k(F, 'circular'),
                             _k(F, 'out_of_sequence'), _k(F, 'whole_day'))

    acts = dk.get('total_activities') or fk.get('total_activities') or nk.get('total_activities')
    rels = llk.get('total_relationships') or rk.get('total_relationships')
    dang, dpct, oe = dk.get('total_dangling'), dk.get('dangling_pct'), ek.get('open_ends')
    loops = cik.get('loops')
    leads = llk.get('leads_count') if llk.get('leads_count') is not None else lk.get('leads')
    lagged, lag_pct = llk.get('lagged_count'), llk.get('lagged_pct')
    long_n, lag_thr, lag_crit = llk.get('long_count') or 0, _i(llk.get('long_threshold_days') or 14), llk.get('critical_count') or 0
    fs_lags = next((t.get('count') for t in (llk.get('by_type') or []) if t.get('type') == 'FS'), None)
    fs, non_fs = _num(rk.get('fs_pct')), rk.get('non_fs')
    fs_short = 0
    if fs is not None and fs < 90 and rels and non_fs is not None:
        fs_short = max(0, math.ceil(0.9 * rels) - (int(rels) - int(non_fs)))
    above, fl_pct, fl_thr, fl_max = fk.get('above_threshold'), fk.get('float_pct'), _i(fk.get('threshold') or 44), fk.get('max_float')
    neg, neg_pct = nk.get('negative_count'), nk.get('neg_pct')
    hd_over, hd_pct, hd_thr, hd_max = hdk.get('over_threshold'), hdk.get('high_pct'), _i(hdk.get('threshold') or 44), hdk.get('max_duration')
    cpli, crit_cnt, crit_pct = _num(ck.get('cpli')), ck.get('critical_count'), ck.get('critical_pct')
    cpl, ptf = ck.get('critical_path_length_days'), ck.get('project_total_float_days')
    oos, oos_pct, crit_oos = ok_.get('oos_count'), ok_.get('oos_pct'), ok_.get('critical_oos') or 0
    direct = 'direct' in str(ok_.get('completion_date_impact') or '').lower()
    m = re.search(r'concentrated in the (.+?) package \((\d+) of (\d+)', str(ok_.get('executive_conclusion') or ''))
    pkg, pkg_n = (m.group(1), int(m.group(2))) if m else (None, None)
    dec = wk.get('decimal_count')
    hard_known = hk.get('hard_count') is not None

    rows, past = _scorecard(F, N, nok, fin, chain_n)
    passes = [r for r in rows if r['state'] == 'pass']
    fails = [r for r in rows if r['state'] == 'fail']
    partial = [r for r in rows if r['state'] == 'partial']
    na = [r for r in rows if r['state'] == 'na']
    scored = len(passes) + len(fails)
    failed = {r['no'] for r in fails}
    delay_fails = [n for no, n in ((7, 'negative float'), (13, 'CPLI')) if no in failed]
    habit_fails = [n for no, n in ((3, 'lags'), (4, 'FS mix'), (2, 'leads'), (6, 'high float')) if no in failed]
    logic_known = rows[0]['state'] in ('pass', 'fail')
    logic_ok = logic_known and 1 not in failed and not (loops or 0)
    oos_known = oos_pct is not None
    status_ok = oos_known and (_num(oos_pct) or 0) <= 5
    counts = _join([f"{_i(acts)} activities" if acts else '', f"{_i(rels)} relationships" if rels else ''])
    thinking.append(f"Scored {scored} of the 14 DCMA points from the stored audit"
                    + (f" ({counts})" if counts else '') + f"; {len(na)} need data this snapshot doesn't hold")

    # network facts used across sections
    cids = {x['id'] for x in (N.get('client_inputs') or [])} if nok else set()
    late_in = (N.get('client_inputs_late_open') or []) if nok else []
    late_neg = [x for x in late_in if x.get('tf') is not None and x['tf'] < 0]
    head = chain[0] if chain else None
    not_started = sum(1 for x in chain if (x.get('pct') or 0) == 0)
    seen = {}
    if nok:
        for key in ('chain', 'deepest', 'milestones', 'client_inputs'):
            for x in N.get(key) or []:
                seen.setdefault(x['id'], x)
        if fin:
            seen.setdefault(fin['id'], fin)
    open_vis = [x for x in seen.values() if not x.get('done')]
    before_dd = [x for x in open_vis if dd and _dt(x.get('finish')) and _dt(x['finish']) < dd]
    rolled = [x for x in late_in if dd and _dt(x.get('finish')) == dd]
    moved_on = next((x for x in chain + open_vis if x['id'] not in cids and dd and _dt(x.get('baseline_finish'))
                     and _dt(x['baseline_finish']) < dd and _dt(x.get('finish')) and _dt(x['finish']) >= dd), None)
    zero_tf = [x for x in open_vis if x.get('tf') == 0 and fin_tf is not None and fin_tf < 0]
    deeper = [x for x in ((N.get('deepest') or []) if nok else []) if fin_tf is not None and x['tf'] <= fin_tf - 3]
    if nok:
        thinking.append(f"Re-read the P6 file: traced the {chain_n}-activity chain that sets the finish and checked "
                        f"{len(open_vis)} open activities, milestones and client inputs against the {dd_s} data date")

    # ── verdict ─────────────────────────────────────────────────────────────────
    wired = ('Well connected' if logic_ok else 'Loosely connected') if logic_known else ''
    stat = ('honestly statused' if status_ok else f"with statusing to check (out-of-sequence {_pc(oos_pct)})") \
        if oos_known else ''
    if wired or stat:
        opener = f"{wired} and {stat}" if (wired and stat) else (wired or stat[0].upper() + stat[1:])
        head_txt = (f"{opener}, but it fails {len(fails)} of the {scored} DCMA points I can score" if fails else
                    f"{opener}, and it passes all {scored} DCMA points I can score")
    else:
        opener = 'Only part of the Schedule Audit is stored with this snapshot'
        head_txt = (f"{opener}: it fails {len(fails)} of the {scored} DCMA points I can score" if fails else
                    f"{opener}: it passes all {scored} DCMA points I can score")
    if loops:
        head_txt = (f"Not reliable yet: {_i(loops)} loop{'s' if loops != 1 else ''} stop the network calculating, so "
                    f"no date or float from it can be trusted until {'they are' if loops != 1 else 'it is'} broken. "
                    f"Beyond that, it fails {len(fails)} of the {scored} DCMA points I can score")
    if neg and behind and logic_ok:
        head_txt += ', and its negative float is genuine slip, not bad logic'
    head_txt += '.'
    fixes = _join([f"the {_i(crit_oos)} critical out-of-sequence" if crit_oos else '',
                   f"the {_i(dang)} danglers" if dang else '',
                   'the unjustified long lags' if long_n else '',
                   f"the {_i(oe)} open ends" if oe else ''])
    if fixes:
        head_txt += f" Fix {fixes}, then report it" + (' with the negative float stated.' if neg else '.')
    else:
        head_txt += (' Report it as it stands.' if logic_known else
                     ' Run the full Schedule Audit before you call the logic verified.')

    pills = [(K.pill('no open ends or danglers', 'success') if (oe == 0 and dang == 0) else
              K.pill(f"{_i(oe)} open ends · {_i(dang)} danglers ({_pc(dpct)})", 'success' if 1 not in failed else 'warning'))
             if (oe is not None and dang is not None) else K.pill('connectivity not scored', 'warning'),
             K.pill(f"{len(fails)} DCMA fails: " + ', '.join(_fail_names(fails)), 'danger') if fails else
             K.pill(f"all {scored} scored DCMA points pass", 'success'),
             K.pill(f"neg float {_i(neg)} ({_pc(neg_pct)}) = real slip", 'danger') if (neg and behind) else
             (K.pill(f"neg float {_i(neg)} — check constraints / calendars", 'warning') if neg else None),
             (K.pill('no out-of-sequence progress', 'success') if oos == 0 else
              K.pill(f"OOS {_i(oos)} ({_pc(oos_pct)}) · {_i(crit_oos)} critical", 'warning' if crit_oos else 'success'))
             if oos is not None else None,
             K.pill(f"{_i(long_n)} lags > {lag_thr} wd to justify", 'warning') if long_n else None,
             K.pill(f"cleanup won't recover the {_i(d)} wd", 'warning') if behind else None,
             K.pill('not reportable until the loops are broken', 'danger') if (loops or 0) else
             K.pill('reportable, caveat stated' if (neg or fails) else 'reportable', 'accent')]

    # ── 1. the scorecard ───────────────────────────────────────────────────────
    lo = opener.replace('connected', 'wired')
    sep = ', but it' if (wired or stat) else ': it'
    lead = (f"**{lo}{sep} fails {len(fails)} of the {scored} DCMA points I can score." if fails else
            f"**{lo}: all {scored} DCMA points I can score pass.")
    if delay_fails and behind:
        lead += (f" {'Two' if len(delay_fails) == 2 else 'One'} of those fails, {_join(delay_fails)}, "
                 f"{'are' if len(delay_fails) == 2 else 'is'} the delay itself showing, not bad logic.")
    lead += '**'
    cnt_line = (f"{_word(scored, True)} points score straight from this file's audit"
                + (f", {_word(len(partial))} {'is' if len(partial) == 1 else 'are'} partial" if partial else '')
                + (f", and {_word(len(na))} need data this snapshot doesn't hold" if na else '')
                + (f". Percentages are of the {counts} the audit counts. " if counts else '. ')
                + "Here's the scorecard:")
    note = "Pass and FAIL rows are read from this file's audit."
    if 12 in {r['no'] for r in passes}:
        note += (" Point 12 passes because an unbroken driving chain traces to the finish; the formal "
                 "delay-injection test wasn't run.")
    if nok and fin_tf is not None and d is not None and round(-fin_tf) == round(d):
        note += f" The finish milestone's own total float ({_sg(fin_tf)}) matches the {_i(abs(d))} wd delay."
    s1 = K.sec('The 14 points — what this snapshot scores', lead, cnt_line, K.network_note(N),
               table=K.tbl(['#', 'DCMA point', 'This snapshot', 'Status'],
                           [[r['no'], r['label'], r['value'], r['status']] for r in rows], note))

    # ── 2. logic health in plain English ────────────────────────────────────────
    clean = []
    if oe == 0:
        clean.append('no open ends')
    if dang == 0:
        clean.append('no dangling activities')
    elif dang is not None and 1 not in failed:
        clean.append(f"only {_i(dang)} dangling activities ({_pc(dpct)})")
    if loops == 0:
        clean.append('no loops')
    if leads == 0:
        clean.append('no leads')
    dur_ok = hd_over is not None and 8 not in failed
    if not logic_known:
        first = ("Connectivity (open ends, danglers, loops) isn't in this snapshot's audit, so I can't vouch for the "
                 "wiring; run the Schedule Audit for it."
                 + (f" Just {_i(hd_over)} activities run longer than {hd_thr} working days." if dur_ok else ''))
    elif logic_ok:
        first = ("The wiring is sound. There are " + (_join(clean) or 'no structural gaps')
                 + (f", and just {_i(hd_over)} activities run longer than {hd_thr} working days." if dur_ok else '.'))
    else:
        defects = [f"{_i(loops)} loop{'s' if loops != 1 else ''} that stop the network calculating" if loops else '',
                   f"{_i(oe)} open ends" if oe else '',
                   f"{_i(dang)} dangling activities ({_pc(dpct)})" if (dang and 1 in failed) else '']
        first = ("The wiring needs work: " + (_join(defects) or 'the missing-logic check fails') + '.'
                 + (f" On the plus side there are {_join(clean)}." if clean else '')
                 + (f" Just {_i(hd_over)} activities run longer than {hd_thr} working days." if dur_ok else ''))
    if hd_over is not None and not dur_ok:
        first += f" {_i(hd_over)} activities ({_pc(hd_pct)}) run longer than {hd_thr} working days, over the 5% line."
    lh = [first]
    if head and fin and logic_ok:
        lh.append(f"The network is connected and the critical path it calculates is real: you can trace it unbroken "
                  f"from {_nm(head)} to {_name(fin)}.")
    fp = [x for x in ('the float profile' if (6 in failed or 7 in failed or 13 in failed) else '',) if x]
    habits = [n for n in habit_fails if n != 'high float']
    if fp or habits:
        lh.append('What fails is ' + _join(fp + ([f"{'two logic habits' if len(habits) == 2 else 'a logic habit' if len(habits) == 1 else f'{len(habits)} logic habits'}"] if habits else [])) + '.')
    if neg and above and 6 in failed:
        where = ''
        if chain and behind:
            where = f", including the whole {chain_n}-activity finish chain"
            if late_neg:
                where += ' and the paths behind the late client inputs'
        lh.append(f"The float is split in two. {_i(neg)} activities ({_pc(neg_pct)}) are on negative float{where}. "
                  f"Another {_i(above)} ({_pc(fl_pct)}) carry more than {fl_thr} wd of float"
                  + (f", up to {_i(fl_max)} wd" if fl_max is not None else '')
                  + ", so they're only loosely tied to anything that governs the finish.")
    elif neg:
        lh.append(f"{_i(neg)} activities ({_pc(neg_pct)}) are on negative float.")
    if lagged is not None and (3 in failed or 4 in failed):
        bits = []
        if 3 in failed:
            bits.append(f"leans heavily on lags ({_i(lagged)} lagged links, {_pc(lag_pct)}"
                        + (f", {_i(fs_lags)} of them on Finish-to-Start links)" if fs_lags else ')'))
        if 4 in failed and fs is not None:
            bits.append(f"uses {'slightly ' if fs >= 85 else ''}too many SS/FF links (FS {_pc(fs)})")
        lh.append('The logic also ' + _join(bits) + '.')
    lh.append('In short, the structure is ' + ('sound' if logic_ok else 'in need of repair' if logic_known else 'unverified')
              + (', it carries real delay' if (neg and behind) else '')
              + (', and it has housekeeping to do.' if (fails or dang or oos) else ', and there is little to tidy.'))
    s2 = K.sec('Logic health, in plain English', ' '.join(lh))

    # ── 3. consultant-ready? ────────────────────────────────────────────────────
    bounce = []
    if 3 in failed:
        bounce.append(f"A consultant would bounce it on the lags before anything else: {_i(lagged)} lagged links"
                      + (f", {_i(long_n)} of them longer than {lag_thr} wd and needing a documented reason" if long_n else '')
                      + (f", and {_i(lag_crit)} on the critical path." if lag_crit else '.'))
    more = []
    if 4 in failed and fs is not None:
        more.append(f"FS at {_pc(fs)}" + (f" (about {fs_short} links short of 90%)" if fs_short else ''))
    if 6 in failed and above:
        more.append(f"the {_i(above)} high-float activities")
    if 1 in failed:
        more.append(f"the missing logic ({_i(dang)} danglers, {_i(oe)} open ends)")
    if more:
        bounce.append(("They'll also mark " if bounce else "A consultant would mark ") + _join(more)
                      + (f", and they'll want a status note on each of the {_i(oos)} out-of-sequence items." if oos else '.'))
    elif oos:
        bounce.append(f"They'll want a status note on each of the {_i(oos)} out-of-sequence items.")
    if delay_fails and behind:
        bounce.append(f"They'll accept the {_join(['negative float' if 7 in failed else '', f'CPLI {K.ratio(cpli)}' if 13 in failed else ''])} "
                      "only with an explanation attached: a recovery plan"
                      + (', plus the EOT notices wherever the late client inputs are the cause.' if late_neg else '.'))
    close = ' and '.join(x for x in (f"the {_i(dang)} danglers" if dang else '',
                                     f"{_i(crit_oos)} critical out-of-sequence items" if crit_oos else '') if x)
    todo = _join(['justify the long lags' if long_n else '',
                  'check the high-float set for missing successors' if 6 in failed else '',
                  f"close {close}" if close else ''])
    ready = not (3 in failed or 4 in failed or 6 in failed or 1 in failed or crit_oos)
    cons = [('Largely, yes.' if ready else 'Not as it stands.')] + bounce
    if ready:
        cons.append(('Every DCMA point I can score passes' if not fails else 'The failing points are the delay itself, not the logic')
                    + ('; attach a note on the out-of-sequence items' if oos else '')
                    + ('; attach the constraint read' if not hard_known else '')
                    + (", and it should clear review." if logic_known else
                       ", but a reviewer will ask for the connectivity checks this snapshot doesn't hold, so run the full "
                       "Schedule Audit before you send it."))
    if not ready and logic_ok:
        cons.append('None of this is structural.' + (f" {todo[0].upper() + todo[1:]}." if todo else ''))
        if behind and delay_fails:
            cons.append(f"Then submit it as 'logic sound, {_join(delay_fails)} failing because the job is {_i(d)} wd late, "
                        f"recovery{' and notices' if late_neg else ''} attached'. Presented as a clean 14-point pass, it "
                        "would not survive review.")
    elif not ready and logic_known:
        cons.append('Fix the missing logic first — a reviewer rejects a network that can hide slip.'
                    + (f" Then {todo}." if todo else ''))
    elif not ready:
        cons.append("Run the full Schedule Audit first: a reviewer will ask for the connectivity checks this snapshot "
                    "doesn't hold." + (f" Then {todo}." if todo else ''))
    s3 = K.sec('Consultant-ready?', ' '.join(cons))

    # ── 4. statusing ────────────────────────────────────────────────────────────
    st = [('Largely, yes.' if (status_ok and not before_dd) else
           'Not fully — check it before you report.' if (oos_known or before_dd) else
           "I can't confirm it from this snapshot's audit.")]
    if oos is not None:
        s = f"Out-of-sequence is {_pc(oos_pct)} ({_i(oos)} of {_i(acts)}" + (f", graded {_grade(F, 'out_of_sequence')})" if _grade(F, 'out_of_sequence') else ')')
        if pkg and pkg_n:
            s += f", and {pkg_n} of the {_i(oos)} sit in the {pkg} package"
            if any(w in pkg.lower() for w in ('design', 'engineer')):
                s += ', where progress running ahead of formal predecessors is common'
        st.append(s + '.')
        if status_ok:
            st.append('A badly statused update usually shows double-digit out-of-sequence in construction.')
    if nok:
        if not before_dd and open_vis:
            st.append(f"Every open activity and milestone on the driving chain and the client-input list is forecast on "
                      f"or after the {dd_s} data date.")
        elif before_dd:
            st.append(f"{len(before_dd)} open activities I can see are forecast before the {dd_s} data date ("
                      + '; '.join(f"{x['id']} {x['finish']}" for x in before_dd[:4]) + ") — a statusing error to fix first.")
        if rolled:
            st.append((f"The {len(rolled)} unreceived client inputs have" if len(rolled) == len(late_in) else
                       f"{_word(len(rolled), True)} of the {len(late_in)} unreceived client inputs have")
                      + " been rolled forward to the data date"
                      + (f", and {_nm(moved_on)}, which was due to finish {moved_on['baseline_finish']}, correctly shows "
                         f"{moved_on['pct']}% with a {moved_on['finish']} forecast instead of being left in the past."
                         if moved_on else '.'))
        elif moved_on:
            st.append(f"{_nm(moved_on)}, which was due to finish {moved_on['baseline_finish']}, correctly shows "
                      f"{moved_on['pct']}% with a {moved_on['finish']} forecast instead of being left in the past.")
        if (rolled or moved_on) and not before_dd:
            st.append("That's what an update rescheduled at the data date looks like.")
    checks = []
    if crit_oos:
        checks.append(f"the {_i(crit_oos)} out-of-sequence item{'s' if crit_oos != 1 else ''} on the critical path"
                      + (', which the audit flags as a direct completion-date impact' if direct else ''))
    checks.append("run Update Analysis for the tells this snapshot doesn't hold: progress with no actual start, finished "
                  "work with no actual dates, and remaining duration left on completed activities")
    st.append(f"{'Two checks' if len(checks) == 2 else 'One check'} before you sign it off. "
              + ' '.join(f"{w}, {c}." for w, c in zip(('First', 'Second'), checks)) if len(checks) == 2 else
              f"One check before you sign it off: {checks[0]}.")
    s4 = K.sec('Was it statused correctly?', ' '.join(p for p in st if p))

    # ── 5. logic problems counted ───────────────────────────────────────────────
    real_fixes = _join([f"the {_i(crit_oos)} critical out-of-sequence" if crit_oos else '',
                        f"the {_i(dang)} danglers" if dang else '',
                        f"the {_i(long_n)} unjustified long lags" if long_n else '',
                        f"the {_i(oe)} open ends" if oe else ''])
    lp_lead = ('**Connectivity is clean. ' if logic_ok else '**Connectivity needs repair first. ' if logic_known
               else "**Connectivity isn't scored in this snapshot. ") + (
        f"The real fixes are {real_fixes}, and every fix round-trips to a corrected schedule.**" if real_fixes
        else ("There's little to fix, and anything you do fix round-trips to a corrected schedule.**" if logic_known
              else "Run the full Schedule Audit to count the logic problems; every fix it finds round-trips to a "
                   "corrected schedule.**"))
    trows = []
    if dang is not None:
        trows.append(['Danglers (missing start or finish tie)',
                      f"{_i(dang)} ({_pc(dpct)})" + (': ' + ', '.join(f"{_i(dk[k])} {w}" for k, w in (('start_dangling', 'start'), ('finish_dangling', 'finish'), ('both_dangling', 'both')) if dk.get(k)) if dang else ''),
                      'Dangling — Resolve & Correct → corrected XER/XML' if dang else 'Clean — nothing to do'])
    if oe is not None:
        trows.append(['Open ends (no predecessor or no successor)', _i(oe),
                      'Schedule Audit: tie each in → corrected XER/XML' if oe else 'Clean — nothing to do'])
    if oos is not None:
        trows.append(['Out-of-sequence',
                      f"{_i(oos)} ({_pc(oos_pct)}); {_i(crit_oos)} on the critical path" + (f"; {pkg_n} in {pkg}" if pkg else ''),
                      'OOS — Resolve & Correct → corrected schedule' if oos else 'Clean'])
    if lagged is not None:
        trows.append(['Lags / leads',
                      f"{_i(lagged)} lags ({_pc(lag_pct)}); {_i(long_n)} > {lag_thr} wd; {_i(lag_crit)} on the critical path; {_i(leads)} leads",
                      'Lag Report: justify, or replace with an activity' if (long_n or 3 in failed) else 'Within the line'])
    if fs is not None:
        trows.append(['Relationship mix', rows[3]['value'],
                      f"Schedule Audit: convert about {fs_short} where FS is the true logic" if fs_short else 'Within the line'])
    if hd_over is not None:
        trows.append([f"Long durations (>{hd_thr} wd)",
                      f"{_i(hd_over)} ({_pc(hd_pct)})" + (f"; longest {_i(hd_max)} wd" if hd_max is not None else ''),
                      'Schedule Audit: split any that hide work' if hd_over else 'Clean'])
    if loops is not None:
        trows.append(['Loops (circular logic)', _i(loops), 'Clean' if not loops else 'Break first — nothing else is reliable until you do'])
    if dec is not None:
        trows.append(['Fractional durations', f"{_i(dec)} ({_pc(wk.get('decimal_pct'))})",
                      'Cosmetic: round to whole days' if dec else 'Clean'])
    trows.append(['Hard constraints', rows[4]['value'],
                  'Schedule Audit: replace with logic or justify' if hard_known else 'Schedule Audit constraint read'])
    trows.append(['Duplicate activity codes', 'not checked in this snapshot', 'Schedule Audit: fix ALL copies'])
    missing = _join(['Hard constraints' if not hard_known else '', 'duplicate codes'])
    s5 = K.sec('Your logic problems, counted', lp_lead,
               "Every row below is counted from this file's audit. Nothing is auto-applied: each fix stays advisory "
               "until you accept it.",
               table=K.tbl(['Logic check', 'Count / state', 'Route to fix'], trows,
                           "Counts are from this file's audit" + (f" ({counts}). " if counts else '. ') +
                           f"{missing[0].upper() + missing[1:]} {'are the two checks' if not hard_known else 'is the check'} "
                           "this snapshot doesn't carry."))

    # ── 6. clean vs needs the audit ─────────────────────────────────────────────
    ok_list = [x for x in (('zero open ends' if oe == 0 else ''), ('zero loops' if loops == 0 else ''),
                           ('zero leads' if leads == 0 else ''),
                           (f"{_i(hd_over)} long durations ({_pc(hd_pct)}, under the line)" if (hd_over and 8 not in failed) else ''),
                           (f"out-of-sequence at {_pc(oos_pct)}" if status_ok else '')) if x]
    act_now = [x for x in ((f"the {_i(crit_oos)} critical out-of-sequence items" if crit_oos else ''),
                           (f"the {_i(dang)} danglers" if dang else ''), (f"the {_i(long_n)} long lags" if long_n else ''),
                           (f"the {_i(oe)} open ends" if oe else '')) if x]
    cl = []
    if ok_list:
        cl.append('Already clean: ' + _join(ok_list) + '.')
    if act_now:
        cl.append('Actionable now: ' + _join(act_now) + '.')
    if not hard_known:
        cl.append("Two checks I can't put a number on from this snapshot. The first is hard constraints, which aren't "
                  "computed" + (', but ' + ('two patterns point at them.' if (zero_tf and deeper) else 'one pattern points at them.')
                                if (zero_tf or deeper) else '.'))
        if zero_tf:
            zc = sum(1 for x in zero_tf if x['id'] in cids)
            dates = sorted({x['finish'] for x in zero_tf if x.get('finish')}, key=lambda s: _dt(s) or datetime.max)
            round_dates = dates and all(s.startswith('01-') for s in dates)
            who = f"{len(zero_tf)} upcoming client input{'s' if len(zero_tf) != 1 else ''}" if zc == len(zero_tf) else \
                f"{len(zero_tf)} upcoming activit{'ies' if len(zero_tf) != 1 else 'y'}"
            cl.append(f"The {who} ({', '.join(x['id'] for x in zero_tf[:5])}{', …' if len(zero_tf) > 5 else ''}) sit at "
                      f"exactly 0 float" + (f" on round dates ({_join(dates[:3])})" if round_dates else '')
                      + f" while the finish is at {_sg(fin_tf)}, which usually means a date constraint.")
        if deeper:
            cl.append(f"And {'several' if len(deeper) > 2 else 'some'} floats run deeper than the project's {_sg(fin_tf)} ("
                      + _join([_sg(x['tf']) for x in sorted(deeper, key=lambda x: -x['tf'])]) + ' on '
                      + _join([_nm(x) for x in sorted(deeper, key=lambda x: -x['tf'])][:3])
                      + "), which points to an intermediate constraint or a different calendar"
                      + (f"; the file has {_i(F['calendar_count'])}." if F.get('calendar_count') else '.'))
        cl.append("The second is duplicate activity codes, which aren't checked. A P6 export can carry every activity "
                  "twice under two ObjectIds, and that quietly breaks code-keyed logic.")
    else:
        cl.append("One check I can't put a number on from this snapshot: duplicate activity codes. A P6 export can "
                  "carry every activity twice under two ObjectIds, and that quietly breaks code-keyed logic.")
    if dang:
        cl.append(f"Also confirm none of the {_i(dang)} danglers is a key milestone, because a dangling milestone reports "
                  "a date nobody's logic controls.")
    s6 = K.sec("What's genuinely clean vs what needs the audit", ' '.join(cl))
    thinking.append(f"Sorted the logic findings by whether they can touch the driving chain: {_i(crit_oos)} critical "
                    f"out-of-sequence, {_i(lag_crit)} critical-path lags, {_i(dang)} danglers to check")

    # ── 7. the fix route ────────────────────────────────────────────────────────
    order = [x for x in ((f"The {_i(crit_oos)} critical out-of-sequence item{'s' if crit_oos != 1 else ''} come first"
                          + (', since the audit says they directly affect completion.' if direct else '.')) if crit_oos else '',
                         (f"Next come any danglers on {chain_lbl}" + (' or the client-input paths' if late_neg else '')
                          + ', then the long lags.' if long_n else '.') if dang else
                         ('Next come the long lags.' if long_n else ''))
             if x]
    fx = ["The workflow is the same for every finding. Pick Fix 1 or Fix 2 (N/A when there's only one sensible option) "
          "and apply it; the same forward-pass engine re-validates it so you see whether the finding actually clears. "
          "When you're done, Download the Corrected XER/XML. It's a real in-place rewrite of the file, not a report "
          "about it."]
    if order:
        fx.append('Work in this order. ' + ' '.join(order))
    if long_n:
        fx.append(f"The Lag Report lets you record a justification against each of the {_i(long_n)} so the submission "
                  "reads as a defensible document. Where a lag hides real work (typically curing, testing, or a crew or "
                  "formwork move between areas), it's better as an activity, which also makes it visible when you plan "
                  "recovery.")
    fx.append('When you fix a duplicated code, fix every copy.')
    s7 = K.sec('The fix, and the route to a corrected schedule', ' '.join(fx))

    # ── 8. punch list ───────────────────────────────────────────────────────────
    if behind and logic_ok:
        pl_lead = (f"**The date is trustworthy and the {_i(d)} wd is genuine slip, not a logic artefact. Report off it, "
                   "state the negative float out loud, and don't book logic cleanup as recovery.**")
    elif behind and logic_known:
        pl_lead = (f"**Repair the missing logic before you trust the {_i(d)} wd — an open network can hide slip. Then "
                   "report it with the negative float stated.**")
    elif behind:
        pl_lead = (f"**The {_i(d)} wd is what the file reports; confirm the connectivity in the full Schedule Audit "
                   "before you call it free of logic artefacts.**")
    else:
        pl_lead = ("**Little here moves the date; the job of the cleanup is to make the reported margin defensible, "
                   "not to change it.**")
    prow = []
    if crit_oos:
        prow.append(['Critical out-of-sequence', _i(crit_oos),
                     'Yes: on the critical path' + (', and the audit flags a direct completion-date impact' if direct else '')])
    if lag_crit:
        prow.append(['Lags on the critical path', f"{_i(lag_crit)} of {_i(lagged)}",
                     "Possibly: a wrong or padded lag on the chain re-times the finish, a real wait doesn't"])
    if dang:
        prow.append(['Danglers on the finish chain' + (' or client-input paths' if late_neg else ''), f"subset of {_i(dang)}",
                     'Yes, if any: check each against the chain'])
    if oe:
        prow.append(['Open ends', _i(oe), 'Yes, if on the chain: an open end lets slip vanish'])
    if neg:
        prow.append(['Negative-float population', f"{_i(neg)} ({_pc(neg_pct)})",
                     "This is the delay itself; logic cleanup won't remove it" if behind else
                     'Check: negative float without a late finish points to constraints or calendars'])
    if long_n:
        prow.append(['Long lags off the critical path', f"part of {_i(long_n)}", 'No: justify them for the consultant'])
    if non_fs and 4 in failed:
        prow.append(['Relationship mix', f"{_i(non_fs)} non-FS (FS {_pc(fs)})", 'Rarely: DCMA housekeeping'])
    if above and 6 in failed:
        prow.append(['High-float activities', f"{_i(above)} ({_pc(fl_pct)})", 'No, but check them for missing successors'])
    if oos and oos - crit_oos > 0:
        prow.append(['Non-critical out-of-sequence', _i(oos - crit_oos) + (f" ({pkg} holds {pkg_n} of the {_i(oos)})" if pkg else ''),
                     'No: cosmetic'])
    if dec:
        prow.append(['Fractional durations', _i(dec), 'No: cosmetic'])
    pnote = None
    if head and fin:
        pnote = f"'On the chain' means the {chain_n}-activity driving chain from {head['id']} to {fin['id']}"
        if late_neg:
            tfs = [x['tf'] for x in late_neg]
            pnote += f", or the client-input paths at {_sg(max(tfs))} to {_sg(min(tfs))} behind it"
        pnote += '.'
    s8 = K.sec("Punch list — what moves the date vs what's cosmetic", pl_lead,
               'Sorted by whether it can actually move the finish:',
               table=K.tbl(['Item', 'Count', 'Moves the finish?'], prow, pnote))

    # ── 9. will cleaning move the finish? ───────────────────────────────────────
    if loops:
        wm = [f"Not until the {_i(loops)} loop{'s are' if loops != 1 else ' is'} broken. While the network can't "
              "calculate, nobody can say what the finish is, let alone what cleanup moves. Break the loops, re-run the "
              "audit, then test any driving-path fix in the What-if (F9)."]
    elif behind:
        wm = [f"Mostly no, and that's the message to protect. The {K.wd(d)} is a physical shortfall"
              + (', and the logic is reporting it honestly.' if logic_ok else '.')]
        if head:
            wm.append(f"{_nm(head)} was due to finish {head.get('baseline_finish')} and "
                      + ("hasn't started." if head.get('pct') == 0 else f"is only {head.get('pct')}% done."))
            if fronts:
                span = f"from {fronts[0][0]} through {fronts[-1][0]}" if len(fronts) > 1 else f"in {fronts[0][0]}"
                wm.append(f"The whole {chain_n}-activity chain {span} is 0% started." if not_started == len(chain)
                          else f"{not_started} of the {chain_n} activities on the chain {span} haven't started.")
        if late_neg:
            sl = [x['slip_wd'] for x in late_neg]
            wm.append(f"{_word(len(late_neg), True)} client input{'s are' if len(late_neg) != 1 else ' is'} "
                      + (f"{min(sl)} to {max(sl)} wd" if len(late_neg) > 1 else f"{sl[0]} wd")
                      + " late on negative-float paths (" + ', '.join(f"{_name(x)} {_sg(x['slip_wd'])} wd" for x in late_neg[:2]) + ').')
        if head or late_neg:
            wm.append('No amount of relinking changes any of that.')
        movers = _join([f"the {_i(crit_oos)} critical out-of-sequence items" if crit_oos else '',
                        'any dangler on the finish chain' if dang else '',
                        f"any of the {_i(lag_crit)} critical-path lags that turns out to be padding rather than a real wait"
                        if lag_crit else ''])
        wm.append("Cleanup moves the date only where a defect sits on the driving path and re-times a driving activity. "
                  + (f"Realistically that means {movers}. " if movers else
                     "The audit stored here doesn't flag any such defect, so expect little or no movement. ")
                  + "Even then the effect is small and can go either way, so test any such fix in the What-if (F9) "
                    "before you claim it.")
        drv = K.main_driver(F)
        wm.append(f"Whose days the {_i(d)} are is a separate question for Consultant Review"
                  + (f": the employer's late inputs versus the {drv['name'] if drv else 'contractor'} execution on "
                     f"{chain_lbl}." if late_neg else '.')
                  + " Clean logic makes that analysis possible; it doesn't answer it.")
    elif ahead:
        wm = [f"There's no slip for cleanup to recover. The risk runs the other way: removing a constraint or closing a "
              f"missing link can reveal less float than the {K.wd(d)} the schedule shows. Prove any such fix in the "
              "What-if (F9) before you bank the margin."]
    else:
        wm = ["Logic cleanup changes the date only where a defect sits on the driving path; test any such fix in the "
              "What-if (F9) before you claim it."]
    s9 = K.sec('Will cleaning them move the finish?', ' '.join(wm))

    # ── 10. reliable enough to report off? ──────────────────────────────────────
    if loops:
        rp = [f"Not yet. {_i(loops)} loop{'s' if loops != 1 else ''} stop the network calculating, so no date or float "
              "from it can be trusted until they're broken."]
    else:
        if not logic_known:
            rp = ["Yes for the measured position, with one caveat: the connectivity checks aren't in this snapshot's "
                  "audit, so say the logic is not yet verified and run the Schedule Audit."]
            conn = "The network is statused"
        else:
            rp = ['Yes, with the caveat stated out loud.' if (neg or fails) else 'Yes.']
            conn = (f"The network is {'connected' if logic_ok else 'mostly connected'} ("
                    + ', '.join(x for x in (f"{_i(oe)} open ends" if oe is not None else '',
                                            f"{_i(dang)} danglers" if dang is not None else '',
                                            f"{_i(loops)} loops" if loops is not None else '') if x) + ') and statused')
        if nok and fin and logic_known:
            rp.append(conn + f" to the {dd_s} data date, and its critical path traces unbroken to {_name(fin)}. "
                      f"So the {fin.get('finish')} forecast" + (f" and the {_i(d)} wd slip are" if behind else ' is')
                      + " what P6 itself calculates.")
        else:
            rp.append(conn + f" to the {dd_s} data date.")
        if neg:
            rp.append('Report the date and the condition together. With ' + _join(
                [f"{_i(neg)} activities ({_pc(neg_pct)}) on negative float",
                 f"{_i(crit_cnt)} at critical float" if crit_cnt is not None else '',
                 f"CPLI at {K.ratio(cpli)}" if cpli is not None else '']) + ", there's no float left to absorb anything.")
        if chain and behind:
            near = min(late_neg, key=lambda x: x['tf']) if late_neg else None
            rp.append(f"Every further slip on {chain_lbl} moves the finish day for day"
                      + (f", and the nearest late client input ({_name(near)}, {_sg(near['tf'])}) is "
                         f"{near['tf'] - fin_tf} wd from doing the same." if (near and fin_tf is not None) else '.'))
        rp.append("What a single snapshot can't give you is the trend or the cause split. Take those to Update vs "
                  "Update and Consultant Review.")
    s10 = K.sec('Reliable enough to report off?', ' '.join(rp))

    # ── measured / actions / evidence ───────────────────────────────────────────
    cp_to = ''
    if nok and ck.get('finish_milestone_id'):
        mid = ck['finish_milestone_id']
        hit = seen.get(mid)
        cp_to = f", measured to {_name(hit)} ({mid})" if hit else f", measured to {mid}"
    measured = (f"DCMA points are scored from this file's Schedule Audit ({_i(acts)} activities, {_i(rels)} relationships) "
                "against the standard lines: missing logic, lags, hard constraints, high float and high duration ≤5%; "
                "leads and negative float = 0; FS ≥90%; CPLI and BEI ≥0.95. "
                + (f"CPLI = (critical path length {_i(cpl)} wd + project total float {_sg(ptf)}) / {_i(cpl)} = {K.ratio(cpli)}{cp_to}. "
                   if (cpli is not None and cpl) else '')
                + (f"The critical-path test is passed by tracing an unbroken {chain_n}-activity driving chain from "
                   f"{head['id']} to {fin['id']}, not by delay injection. " if (head and fin) else '')
                + "This snapshot doesn't hold " + _join_or(['hard constraints' if not hard_known else '', 'invalid dates',
                                                            'missed tasks', 'BEI']) + ', and labour loading isn\'t read. '
                + ("Completion impact depends on whether an item sits on that driving chain"
                   + (' or on the client-input paths behind it. ' if late_neg else '. ') if head else '')
                + "The exact effect of any fix is the What-if's P6 F9 recalculation.")
    fail_txt = _join(delay_fails) if delay_fails else ''
    actions = [
        (f"Report it as 'logic sound, statused to {dd_s}, failing DCMA on {fail_txt} because the job is {_i(d)} wd late"
         + (f", and on {_join([h for h in habit_fails])} as housekeeping'" if habit_fails else "'")
         + '. Never present it as a clean 14-point pass.') if (behind and delay_fails and logic_ok) else
        ('Report it with the failing DCMA points named — never as a clean 14-point pass.' if fails else ''),
        (('Fix ' + ', '.join(x for x in [f"the {_i(crit_oos)} critical out-of-sequence items first" if crit_oos else '',
                                         (f"then any of the {_i(dang)} danglers on {chain_lbl}" if crit_oos else
                                          f"any of the {_i(dang)} danglers on {chain_lbl}")
                                         + (' or client-input paths' if late_neg else '') if dang else ''] if x)
          + ', using Resolve & Correct, then Download the Corrected XER/XML.') if (crit_oos or dang) else ''),
        (f"Justify the {_i(long_n)} lags over {lag_thr} wd in the Lag Report" + (f" and review the {_i(lag_crit)} on the critical path" if lag_crit else '')
         + '; turn any lag that hides real work into an activity.') if long_n else '',
        f"Convert about {fs_short} SS/FF links to FS where FS is the true logic, to clear the 90% line." if fs_short else '',
        f"Check the {_i(above)} high-float activities for missing successors." if (above and 6 in failed) else '',
        ('Run the Schedule Audit constraint read' + (': ' + _join([
            f"the {len(zero_tf)} activities at exactly 0 float" if zero_tf else '',
            'the floats deeper than the finish (' + ', '.join(_sg(x['tf']) for x in deeper[:3]) + ')' if deeper else ''])
            + ' point to constraints or calendar differences.' if (zero_tf or deeper) else '.')) if not hard_known else '',
        'Run Update Analysis for the statusing tells this snapshot doesn\'t hold, and check for duplicate activity codes, fixing every copy.',
        ("Don't book logic cleanup as recovery. Prove any driving-path fix in the What-if F9, and take the cause split to "
         "Consultant Review.") if behind else 'Prove any driving-path fix in the What-if F9 before you rely on it.']
    evidence = [K.ev('Open ends', _i(oe) if oe is not None else None),
                K.ev('Danglers', f"{_i(dang)} ({_pc(dpct)})" if dang is not None else None),
                K.ev('OOS', f"{_i(oos)} ({_pc(oos_pct)}) · {_i(crit_oos)} critical" if oos is not None else None),
                K.ev('Lags', f"{_i(lagged)} ({_pc(lag_pct)}) · {_i(long_n)} > {lag_thr} wd" if lagged is not None else None),
                K.ev('FS share', _pc(fs) if fs is not None else None),
                K.ev('High float', f"{_i(above)} ({_pc(fl_pct)})" if above is not None else None),
                K.ev('Neg float', f"{_i(neg)} ({_pc(neg_pct)})" if neg is not None else None),
                K.ev('CPLI', f"{K.ratio(cpli)} (target {K.ratio(_num(ck.get('target')) or 0.95)})" if cpli is not None else None),
                K.ev('Critical float', f"{_i(crit_cnt)} ({_pc(crit_pct)})" if crit_cnt is not None else None),
                K.ev('Loops / leads', f"{_i(loops)} / {_i(leads)}" if (loops is not None or leads is not None) else None),
                K.ev('Long durations', f"{_i(hd_over)} ({_pc(hd_pct)})" if hd_over is not None else None),
                K.ev('DCMA scored', f"{len(passes)} pass · {len(fails)} fail of {scored}"),
                K.ev('Hard constraints', f"{_i(hk['hard_count'])} ({_pc(hk.get('hard_pct'))})" if hard_known else 'not computed'),
                K.ev('Verdict', 'not reportable (loops)' if loops else ('reportable + caveat' if (neg or fails) else 'reportable'))]
    a = K.A2(head_txt, [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10], pills=pills, measured=measured, actions=actions,
             evidence=evidence,
             drilldowns=[K.drill('q05', f"How do I recover the ~{_i(d)} days?") if behind else
                         K.drill('q02', 'When will we finish, and will we hit the dates?'),
                         K.drill('q04', "What's driving the date, and how much float is left?"),
                         K.drill('q12', "Does the logic make construction sense, and what's missing?"),
                         K.drill('q13', 'Do the late client inputs give me an EOT case?') if late_neg else
                         K.drill('q07', 'What changed since the baseline — genuine re-plan or gaming?')])
    a['thinking'] = thinking[:4]
    return a
