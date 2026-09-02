"""Baseline Revision Comparison — the neutral, progress-free comparison engine.

Compares two approved baseline revisions (Rev.00 original, Rev.01 revised) and
reports what changed and how much it can move the plan. It reuses the repo's
proven primitives — ``MatchedSchedules`` + ``diff_relationships`` for logic, and
``p6_critpath`` for the critical-path/float/milestone view — but keeps its own
neutral interpretation: no "manufactured delay", no but-for, no burn-down (a
baseline carries no progress). Every output is evidence; nothing is a verdict.

Public API:
    build_report(rev0_path, rev1_path, config=None, options=None)
    build_report_from_data(rev0, rev1, config=None, options=None)
"""
import os
from datetime import datetime

from p6_revcompare.matching import match_activities, canonicalize
from p6_revcompare.sequence import detect_sequence_changes
from p6_revcompare import severity as SEV


# ── date / duration helpers ─────────────────────────────────────────────────

def _long(d):
    return d.strftime('%d %B %Y') if isinstance(d, datetime) else None


def _short(d):
    return d.strftime('%d %b %Y') if isinstance(d, datetime) else None


def _d0(d):
    return d.replace(hour=0, minute=0, second=0, microsecond=0) if isinstance(d, datetime) else d


def _forecast_finish(act):
    return act.get('actual_finish') or act.get('remaining_early_finish') or act.get('planned_finish')


def _ref_cal(data, act=None):
    from p6_critpath.analysis import _ref_calendar
    return _ref_calendar(data, act)


def _wd_between(cal, d1, d2):
    from p6_critpath.analysis import _wd_between as wd
    return wd(cal, d1, d2)


def _day_hours(data, act):
    cal = (getattr(data, 'calendars', {}) or {}).get(act.get('calendar_id'))
    return getattr(cal, 'day_hours', 8.0) if cal else 8.0


def _dur_days(data, act):
    return round((act.get('planned_duration') or 0.0) / _day_hours(data, act), 1)


# ── critical path helpers ───────────────────────────────────────────────────

_MS = ('StartMilestone', 'FinishMilestone')


def _governing_finish(data):
    from p6_critpath.paths import _governing_finish_ms
    gov = _governing_finish_ms(data)
    return _forecast_finish(gov) if gov else None


def _critical_codes(data):
    """Activity codes on the critical path — TF ≤ 0 where the export carries float, else the
    longest-path chain (a clean baseline may carry no float)."""
    codes, any_tf = set(), False
    for a in data.activities.values():
        if a.get('task_type') in _MS:
            continue
        tf = a.get('total_float_days')
        if tf is not None:
            any_tf = True
            if tf <= 0 and a.get('id'):
                codes.add(a['id'])
    if not any_tf:
        from p6_critpath.analysis import _critical_from_paths
        for oid in _critical_from_paths(data):
            a = data.activities.get(oid)
            if a and a.get('id'):
                codes.add(a['id'])
    return codes


def _cp_chain(data, crit_codes, entered, left):
    """Driving chain to the governing finish milestone, start→finish, as display nodes."""
    from p6_critpath.paths import _governing_finish_ms, trace_driving_chain
    from p6_audit.graph import ScheduleGraph
    gov = _governing_finish_ms(data)
    if not gov:
        return []
    start = next((k for k, v in data.activities.items() if v is gov), None)
    if start is None:
        return []
    graph = ScheduleGraph(data)
    chain = list(trace_driving_chain(graph, start))
    nodes = []
    for oid in chain:
        a = graph.activities.get(oid) or data.activities.get(oid)
        if not a:
            continue
        code = a.get('id')
        st = 'enter' if code in entered else ('leave' if code in left else None)
        nodes.append({
            'code': code, 'name': a.get('name') or code,
            'tf': a.get('total_float_days'),
            'is_ms': a.get('task_type') in _MS,
            'state': st,
        })
    # trace runs from the finish milestone backward; present start→finish with the milestone last.
    if nodes and nodes[0]['is_ms'] and not nodes[-1]['is_ms']:
        nodes.reverse()
    return nodes


def _path_length_wd(data):
    try:
        from p6_critpath.analysis import schedule_census
        return schedule_census(data).get('path_length_wd')
    except Exception:
        return None


# ── logic (relationship) stats — edge level, precise counts ──────────────────

def _logic_stats(matched):
    """Edge-level relationship changes over matched codes: added/removed/type/lag counts."""
    e0, e1 = matched.baseline_rels, matched.update_rels
    k0, k1 = set(e0), set(e1)
    added = len(k1 - k0)
    removed = len(k0 - k1)
    type_ch = lag_ch = 0
    for k in (k0 & k1):
        a, b = e0[k], e1[k]
        if a.get('type') != b.get('type'):
            type_ch += 1
        elif abs((a.get('lag_days') or 0.0) - (b.get('lag_days') or 0.0)) > 1e-9:
            lag_ch += 1
    return {'total': added + removed + type_ch + lag_ch,
            'added': added, 'removed': removed, 'type': type_ch, 'lag': lag_ch}


# ── milestones ───────────────────────────────────────────────────────────────

def _finish_ms_by_code(data):
    out = {}
    for a in data.activities.values():
        if a.get('task_type') == 'FinishMilestone' and a.get('id'):
            out[a['id']] = a
    return out


def _compare_milestones(rev0, rev1, cal):
    m0, m1 = _finish_ms_by_code(rev0), _finish_ms_by_code(rev1)
    rows = []
    for code in sorted(set(m0) | set(m1)):
        a0, a1 = m0.get(code), m1.get(code)
        name = (a1 or a0).get('name') or code
        f0, f1 = (_forecast_finish(a0) if a0 else None), (_forecast_finish(a1) if a1 else None)
        if a0 and not a1:
            rows.append({'name': name, 'rev0': _long(f0), 'rev1': None,
                         'change': None, 'kind': 'removed', 'change_days': None})
            continue
        if a1 and not a0:
            rows.append({'name': name, 'rev0': None, 'rev1': _long(f1),
                         'change': None, 'kind': 'new', 'change_days': None})
            continue
        slip = _wd_between(cal, _d0(f0), _d0(f1)) if (f0 and f1) else None
        if slip is None:
            kind = 'unchanged'
        elif slip > 0:
            kind = 'delayed'
        elif slip < 0:
            kind = 'advanced'
        else:
            kind = 'unchanged'
        rows.append({'name': name, 'rev0': _long(f0), 'rev1': _long(f1),
                     'change': slip, 'kind': kind, 'change_days': slip})
    # governing / biggest movers first
    rows.sort(key=lambda r: (r['kind'] == 'unchanged', -abs(r.get('change_days') or 0)))
    return rows


# ── float / criticality movement ─────────────────────────────────────────────

def _float_movement(pairs, floor=5.0):
    rows = []
    for p in pairs:
        tf0, tf1 = p['act0'].get('total_float_days'), p['act1'].get('total_float_days')
        if tf0 is None or tf1 is None:
            continue
        b0, b1 = SEV.band(tf0), SEV.band(tf1)
        delta = round(tf1 - tf0, 1)
        movement = cls = None
        if b0 != 'crit' and b1 == 'crit':
            movement, cls = 'Became critical', 'rem'
        elif b0 == 'safe' and b1 == 'near':
            movement, cls = 'Became near-critical', 'chg'
        elif b0 == 'crit' and b1 != 'crit':
            movement, cls = 'Left critical path', 'add'
        elif delta <= -floor:
            movement, cls = 'Lost significant float', 'chg'
        elif delta >= floor:
            movement, cls = 'Gained float', 'add'
        if movement:
            rows.append({'activity_id': p['canonical'], 'name': p['act1'].get('name') or p['canonical'],
                         'rev0_tf': round(tf0, 1), 'rev1_tf': round(tf1, 1),
                         'delta': delta, 'movement': movement, 'movement_cls': cls})
    rows.sort(key=lambda r: -abs(r['delta']))
    return rows


# ── register ─────────────────────────────────────────────────────────────────

def _sev_row(activity_id, activity_name, change_type, rev0, rev1, change, tf0, tf1,
             magnitude=0.0, on_cp=False, detail=None, orig_id=None):
    impact, sev = SEV.classify(change_type, tf0=tf0, tf1=tf1, magnitude=magnitude, on_cp=on_cp)
    return {
        'activity_id': activity_id, 'orig_id': orig_id,
        'activity_name': activity_name,
        'change_type': change_type, 'type_label': SEV.TYPE_LABEL.get(change_type, change_type),
        'rev0': rev0, 'rev1': rev1, 'change': change,
        'impact': impact, 'severity': sev, 'status': 'open',
        'detail': detail,
    }


def _detail(pair_or_act0, act1, change_note, why, impact, review, cal, data0, data1):
    """Side-by-side Rev.00/Rev.01 snapshot + the four-part planning analysis."""
    def snap(data, a):
        if not a:
            return None
        return {
            'id': a.get('orig_id') or a.get('id'),
            'name': a.get('name'), 'wbs': a.get('wbs_path') or '—',
            'start': _short(a.get('planned_start')), 'finish': _short(_forecast_finish(a)),
            'duration': f"{_dur_days(data, a)} d",
            'total_float': ('%s d' % round(a['total_float_days'], 1)) if a.get('total_float_days') is not None else '—',
            'criticality': _crit_label(a.get('total_float_days')),
        }
    return {
        'rev0': snap(data0, pair_or_act0), 'rev1': snap(data1, act1),
        'detected': change_note, 'why': why, 'impact': impact, 'review': review,
    }


def _crit_label(tf):
    b = SEV.band(tf)
    return {'crit': 'Critical', 'near': 'Near-critical', 'safe': 'Non-critical'}.get(b, '—')


# ── the report ───────────────────────────────────────────────────────────────

def build_report(rev0_path, rev1_path, config=None, options=None):
    from p6_evm.parser import parse_file
    rev0 = parse_file(rev0_path)
    rev1 = parse_file(rev1_path)
    report = build_report_from_data(rev0, rev1, config, options)
    report['rev0']['file'] = os.path.basename(rev0_path)
    report['rev1']['file'] = os.path.basename(rev1_path)
    return report


def build_report_from_data(rev0, rev1, config=None, options=None):
    from p6_compare.model import MatchedSchedules
    from p6_compare.diff import diff_relationships, driving_pairs
    from p6_audit.graph import ScheduleGraph

    options = options or {}
    match = match_activities(rev0, rev1)
    rev1c = canonicalize(rev1, match['canonical'])
    matched = MatchedSchedules(rev0, rev1c)
    cal = _ref_cal(rev1c)

    # Warnings (format / float caveats) so the reader knows how far to trust each dimension.
    warnings = _warnings(rev0, rev1)

    # ── logic ────────────────────────────────────────────────────────────────
    logic_stats = _logic_stats(matched)
    logic = diff_relationships(matched, driving_pairs(ScheduleGraph(rev1c)))

    # ── critical path ──────────────────────────────────────────────────────────
    crit0, crit1 = _critical_codes(rev0), _critical_codes(rev1c)
    entered, left = (crit1 - crit0), (crit0 - crit1)
    len0, len1 = _path_length_wd(rev0), _path_length_wd(rev1c)
    cp_len_change = (len1 - len0) if (len0 is not None and len1 is not None) else None
    cp = {
        'rev0': _cp_chain(rev0, crit0, set(), set()),
        'rev1': _cp_chain(rev1c, crit1, entered, left),
        'entered': [{'code': c, 'name': (matched.update_by_code.get(c) or {}).get('name') or c}
                    for c in sorted(entered)],
        'left': [{'code': c, 'name': (matched.baseline_by_code.get(c) or {}).get('name') or c}
                 for c in sorted(left)],
        'length_change_wd': cp_len_change,
    }

    # ── sequence ───────────────────────────────────────────────────────────────
    sequences = detect_sequence_changes(matched)
    for s in sequences:
        a0 = matched.baseline_by_code.get(s['a']) or {}
        a1 = matched.update_by_code.get(s['a']) or {}
        s['impact'], s['severity'] = SEV.classify(
            'sequence', tf0=a0.get('total_float_days'), tf1=a1.get('total_float_days'))

    # ── milestones ─────────────────────────────────────────────────────────────
    milestones = _compare_milestones(rev0, rev1c, cal)

    # ── float movement ───────────────────────────────────────────────────────────
    floats = _float_movement(match['pairs'])

    # ── time (duration) changes on matched activities ───────────────────────────
    time_changes = _time_changes(match['pairs'], rev0, rev1c)

    # ── register ───────────────────────────────────────────────────────────────
    register = _build_register(match, matched, logic, sequences, milestones, floats,
                               time_changes, crit0, crit1, cal, rev0, rev1c)

    # ── summary / profile / ledger / findings / narrative ───────────────────────
    gov0, gov1 = _governing_finish(rev0), _governing_finish(rev1c)
    finish_shift = None
    if gov0 and gov1:
        finish_shift = (_d0(gov1) - _d0(gov0)).days
    summary = {
        'activities0': len(rev0.activities), 'activities1': len(rev1.activities),
        'net': len(rev1.activities) - len(rev0.activities),
        'added': len(match['added']), 'removed': len(match['removed']),
        'modified': _modified_count(register), 'id_changes': len(match['id_changes']),
        'renamed': len(match['renamed']), 'moved_wbs': len(match['moved_wbs']),
        'duration_change_wd': cp_len_change, 'finish_shift_days': finish_shift,
        'logic': logic_stats, 'sequence': len(sequences),
        'cp_in': len(entered), 'cp_out': len(left), 'cp_length_change_wd': cp_len_change,
        'criticality': sum(1 for f in floats if f['movement_cls'] in ('rem', 'add') and 'critical' in f['movement'].lower()),
        'float_moves': len(floats),
    }
    profile = _profile(match, logic_stats, sequences, floats, milestones, time_changes)
    ledger = _ledger(summary, match, milestones)
    findings = _findings(register, sequences, milestones, cp)
    narrative = _narrative(summary, finish_shift, sequences, milestones)

    return {
        'rev0': {'file': None, 'activities': len(rev0.activities),
                 'data_date': _short((rev0.project or {}).get('data_date')),
                 'finish': _short(gov0)},
        'rev1': {'file': None, 'activities': len(rev1.activities),
                 'data_date': _short((rev1.project or {}).get('data_date')),
                 'finish': _short(gov1)},
        'warnings': warnings,
        'summary': summary, 'profile': profile, 'ledger': ledger, 'findings': findings,
        'register': register, 'critical_path': cp, 'sequence': sequences,
        'float_movement': floats, 'milestones': milestones, 'narrative': narrative,
    }


# ── register assembly ────────────────────────────────────────────────────────

def _time_changes(pairs, data0, data1):
    rows = []
    for p in pairs:
        d0, d1 = _dur_days(data0, p['act0']), _dur_days(data1, p['act1'])
        delta = round(d1 - d0, 1)
        if abs(delta) < 0.5:
            continue
        rows.append({'pair': p, 'rev0_days': d0, 'rev1_days': d1, 'delta': delta})
    rows.sort(key=lambda r: -abs(r['delta']))
    return rows


def _build_register(match, matched, logic, sequences, milestones, floats, time_changes,
                    crit0, crit1, cal, data0, data1):
    rows = []
    seen = set()   # (activity, kind) dedupe

    def add(row):
        key = (row['activity_id'], row['change_type'])
        if key in seen:
            return
        seen.add(key)
        rows.append(row)

    # Codes whose logic changed only because of a detected sequence reversal — folded into
    # the sequence row so one methodology change doesn't explode into a cluster of logic rows.
    seq_folded = set()
    for s in sequences:
        seq_folded.update(s.get('involved') or [])

    # Sequence reversals — the flagship, with full detail.
    for s in sequences:
        a0 = matched.baseline_by_code.get(s['a']) or {}
        a1 = matched.update_by_code.get(s['a']) or {}
        pair = next((p for p in match['pairs'] if p['canonical'] == s['a']), None)
        detail = _detail(a0, a1,
                         f"{s['a_name']} moved from {s['rev0']} to {s['rev1']} — an execution-order reversal read from the logic.",
                         'A reversal changes the planned construction method/order for this work.',
                         'The activity and its neighbours re-sequence; where this sits on the critical path it can move the finish.',
                         'Confirm the revised sequence is a deliberate, approved methodology change. Neutral: legitimate, but verify the basis.',
                         cal, data0, data1)
        add(_sev_row(s['a'], s['a_name'], 'sequence',
                     s['rev0'], s['rev1'], 'Re-sequenced',
                     a0.get('total_float_days'), a1.get('total_float_days'),
                     detail=detail, orig_id=(a1.get('orig_id') or s['a'])))

    # Milestone movements.
    for m in milestones:
        if m['kind'] in ('delayed', 'advanced', 'new', 'removed'):
            add(_sev_row('MS:' + m['name'], m['name'], 'milestone',
                         m['rev0'] or '—', m['rev1'] or '—',
                         _slip_label(m), None, None, magnitude=abs(m.get('change_days') or 0)))

    # Logic (relationship) changes — material where on/near the path. Rows already
    # explained by a sequence reversal are folded away (see seq_folded).
    for r in logic['rows']:
        code = r['activity_id']
        if code in seq_folded:
            continue
        a0 = matched.baseline_by_code.get(code) or {}
        a1 = matched.update_by_code.get(code) or {}
        c0, c1 = _logic_cells(r)
        add(_sev_row(code, r['activity_name'], 'logic', c0, c1,
                     r['change_label'], a0.get('total_float_days'), a1.get('total_float_days'),
                     orig_id=(a1.get('orig_id') or code)))

    # Criticality / float movement.
    for f in floats:
        code = f['activity_id']
        a0 = matched.baseline_by_code.get(code) or {}
        a1 = matched.update_by_code.get(code) or {}
        add(_sev_row(code, f['name'], 'criticality',
                     f"TF {f['rev0_tf']} d", f"TF {f['rev1_tf']} d", f['movement'],
                     a0.get('total_float_days'), a1.get('total_float_days')))

    # Time / duration changes.
    for t in time_changes:
        p = t['pair']
        code = p['canonical']
        add(_sev_row(code, p['act1'].get('name') or code, 'time',
                     f"Dur {t['rev0_days']} d", f"Dur {t['rev1_days']} d",
                     f"{'+' if t['delta'] > 0 else ''}{t['delta']} d duration",
                     p['act0'].get('total_float_days'), p['act1'].get('total_float_days'),
                     magnitude=t['delta'], orig_id=(p['act1'].get('orig_id') or code)))

    # Scope: summary rows for added / removed, plus individual critical add/removes.
    if match['added']:
        add(_sev_row('SCOPE:added', f"{len(match['added'])} activities", 'added',
                     '—', 'Present in Rev.01', 'New activities', None, None))
    if match['removed']:
        add(_sev_row('SCOPE:removed', f"{len(match['removed'])} activities", 'removed',
                     'Present in Rev.00', '—', 'Removed activities', None, None))
    for a in match['added']:
        if a.get('id') in crit1:
            add(_sev_row(a['id'], a.get('name') or a['id'], 'added',
                         '—', 'Present in Rev.01', 'New critical activity', None,
                         a.get('total_float_days'), on_cp=True))
    for a in match['removed']:
        if a.get('id') in crit0:
            add(_sev_row(a['id'], a.get('name') or a['id'], 'removed',
                         'Present in Rev.00', '—', 'Removed critical activity',
                         a.get('total_float_days'), None, on_cp=True))

    # Identity changes and WBS moves.
    for p in match['id_changes']:
        add(_sev_row(p['canonical'], p['act1'].get('name') or p['canonical'], 'idchange',
                     p['code0'], p['code1'], f"{p['code0']} → {p['code1']}",
                     p['act0'].get('total_float_days'), p['act1'].get('total_float_days'),
                     orig_id=p['code1']))
    for p in match['moved_wbs']:
        add(_sev_row(p['canonical'], p['act1'].get('name') or p['canonical'], 'moved_wbs',
                     p['act0'].get('wbs_path') or '—', p['act1'].get('wbs_path') or '—',
                     'Moved WBS', p['act0'].get('total_float_days'), p['act1'].get('total_float_days')))

    rows.sort(key=SEV.rank_key)
    return rows


def _rel_lbl(l, arrow):
    lag = l.get('lag_days') or 0
    t = l.get('type', 'FS')
    return f"{arrow}{l.get('code')} {t}{('%+d' % round(lag)) if lag else ''}"


def _logic_cells(row):
    """Render the SPECIFIC changed relationship(s) for a logic row, before vs after —
    so the cells never look identical. Predecessors as 'code→', successors as '→code'."""
    changes = []   # (rev0_text, rev1_text)

    def scan(bl, ul, arrow):
        b_by = {l['code']: l for l in bl}
        u_by = {l['code']: l for l in ul}
        for code in sorted(set(b_by) | set(u_by)):
            b, u = b_by.get(code), u_by.get(code)
            if u and u.get('status') == 'added':
                changes.append((None, _rel_lbl(u, arrow)))
            elif b and b.get('status') == 'removed':
                changes.append((_rel_lbl(b, arrow), None))
            elif b and u and u.get('status') == 'changed':
                changes.append((_rel_lbl(b, arrow), _rel_lbl(u, arrow)))

    scan(row['baseline_preds'], row['update_preds'], '')
    scan(row['baseline_succs'], row['update_succs'], '→ ')
    if not changes:
        return row.get('change_label', ''), ''
    r0 = ' · '.join(c[0] for c in changes if c[0]) or '—'
    r1 = ' · '.join(c[1] for c in changes if c[1]) or '—'
    return r0, r1


def _slip_label(m):
    if m['kind'] == 'new':
        return 'New milestone'
    if m['kind'] == 'removed':
        return 'Removed milestone'
    d = m.get('change_days') or 0
    if d > 0:
        return f'+{d} d (delayed)'
    if d < 0:
        return f'{d} d (advanced)'
    return 'Unchanged'


def _modified_count(register):
    kinds = ('logic', 'time', 'criticality', 'sequence', 'moved_wbs')
    codes = set()
    for r in register:
        if r['change_type'] in kinds and not r['activity_id'].startswith(('MS:', 'SCOPE:')):
            codes.add(r['activity_id'])
    return len(codes)


# ── summary presentation ─────────────────────────────────────────────────────

def _profile(match, logic, sequences, floats, milestones, time_changes):
    scope = len(match['added']) + len(match['removed'])
    crit = sum(1 for f in floats if 'critical' in f['movement'].lower())
    ms = sum(1 for m in milestones if m['kind'] in ('delayed', 'advanced', 'new', 'removed'))
    return [
        {'key': 'logic', 'label': 'Logic / relationships', 'count': logic['total'], 'color': '#2563eb'},
        {'key': 'time', 'label': 'Time / durations', 'count': len(time_changes), 'color': '#b7791f'},
        {'key': 'scope', 'label': 'Scope (add/remove)', 'count': scope, 'color': '#12805c'},
        {'key': 'sequence', 'label': 'Sequence', 'count': len(sequences), 'color': '#7c3aed'},
        {'key': 'criticality', 'label': 'Criticality / float', 'count': len(floats), 'color': '#c23a3a'},
        {'key': 'milestone', 'label': 'Milestones', 'count': ms, 'color': '#0f766e'},
        {'key': 'wbs', 'label': 'WBS moves', 'count': len(match['moved_wbs']), 'color': '#7c3aed'},
        {'key': 'idchange', 'label': 'Identity (ID) changes', 'count': len(match['id_changes']), 'color': '#69768c'},
    ]


def _ledger(summary, match, milestones):
    L = summary['logic']
    gov = next((m for m in milestones if m['kind'] in ('delayed', 'advanced')), None)
    return [
        {'label': 'Total activities', 'rev0': summary['activities0'], 'rev1': summary['activities1'],
         'delta': summary['net']},
        {'label': 'New / removed activities', 'rev0': summary['added'], 'rev1': summary['removed'],
         'delta': None},
        {'label': 'Modified · identity (ID) changes', 'rev0': summary['modified'],
         'rev1': summary['id_changes'], 'delta': None},
        {'label': 'Logic / relationship changes',
         'rev0': L['total'], 'rev1': None,
         'delta': f"+{L['added']} −{L['removed']} · {L['type']} type · {L['lag']} lag"},
        {'label': 'Meaningful sequence changes', 'rev0': summary['sequence'], 'rev1': None, 'delta': None},
        {'label': 'Critical-path activities in / out',
         'rev0': summary['cp_in'], 'rev1': summary['cp_out'],
         'delta': (f"CP {'+' if (summary['cp_length_change_wd'] or 0) >= 0 else ''}{summary['cp_length_change_wd']} d"
                   if summary['cp_length_change_wd'] is not None else None)},
        {'label': 'Criticality / float movement', 'rev0': summary['float_moves'], 'rev1': None, 'delta': None},
    ]


def _findings(register, sequences, milestones, cp):
    """A curated, diverse set of the material changes most likely to affect the execution
    strategy — one per theme (sequence, milestone, logic, scope, criticality), ranked by
    severity, so the reader isn't shown five near-identical rows."""
    sev_order = {'crit': 0, 'hi': 1, 'med': 2, 'low': 3}
    picked, used_types = [], set()
    # Prefer detailed sequence rows and milestone rows first, then one of each other type.
    priority = {'sequence': 0, 'milestone': 1, 'added': 2, 'removed': 2, 'criticality': 3, 'logic': 4}
    for r in sorted(register, key=lambda r: (r['impact'] != 'material',
                                             priority.get(r['change_type'], 9),
                                             sev_order.get(r['severity'], 3))):
        if r['impact'] != 'material':
            continue
        t = r['change_type']
        if t in used_types and t not in ('sequence', 'milestone'):
            continue
        used_types.add(t)
        det = r.get('detail') or {}
        picked.append({
            'severity': r['severity'],
            'title': f"{r['activity_name']} — {r['change']}",
            'type_label': r['type_label'], 'change_type': t,
            'body': det.get('detected') or f"{r['rev0']} → {r['rev1']}",
            'flow_impact': det.get('impact'),
        })
        if len(picked) >= 5:
            break
    return picked


def _narrative(summary, finish_shift, sequences, milestones):
    parts = []
    net = summary['net']
    parts.append(
        f"Rev.01 carries {summary['activities1']} activities ({'+' if net >= 0 else ''}{net} vs Rev.00), "
        f"with {summary['added']} added, {summary['removed']} removed and {summary['modified']} modified "
        f"({summary['id_changes']} of the matches are identity/ID changes).")
    if finish_shift is not None and finish_shift != 0:
        word = 'later' if finish_shift > 0 else 'earlier'
        parts.append(f"The governing finish moves {abs(finish_shift)} days {word}.")
    if summary['sequence']:
        parts.append(f"{summary['sequence']} execution-sequence change(s) were detected from the logic.")
    if summary['cp_in'] or summary['cp_out']:
        parts.append(f"{summary['cp_in']} activities enter and {summary['cp_out']} leave the critical path.")
    parts.append("Findings are analytical observations for planning review — not judgements that the revision is incorrect.")
    return ' '.join(parts)


def _warnings(rev0, rev1):
    out = []
    def has_float(d):
        return any(a.get('total_float_days') is not None for a in d.activities.values()
                   if a.get('task_type') not in _MS)
    if not has_float(rev0) or not has_float(rev1):
        out.append('One revision carries no per-activity total float; critical-path and float '
                   'figures for it are derived from the longest path.')
    dd0 = (rev0.project or {}).get('data_date')
    dd1 = (rev1.project or {}).get('data_date')
    if isinstance(dd0, datetime) and isinstance(dd1, datetime) and _d0(dd0) != _d0(dd1):
        out.append('The two revisions have different data dates; date variances mix the revision '
                   'change with the elapsed period.')
    return out
