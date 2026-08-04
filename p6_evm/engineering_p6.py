"""Engineering progress from P6 (Mode B) — the fallback when no E1 Log is uploaded.

Engineering drawings appear in P6 as Submittal + Approval activity pairs, coded
by Trade Design (Civil/MEP/Arch) and Design Cycle (Schematic/Detailed/IFC/Shop).
Per Trade x Drawing Type: Req = submittal activities; Submitted/Approved = the
submittal/approval activities that are complete; Planned = those whose baseline
finish is on/before the data date. Percentages are count / Req.
"""


def _is_done(a):
    return (a.get('percent_complete') or 0) >= 0.999


def _drawing_type(codes):
    dt = codes.get('Design Cycle')
    if dt:
        return dt
    eng = codes.get('Engineering SUB WBS') or ''
    if 'Shop Drawing' in eng:
        return 'Shop Drawing'
    return None


def engineering_from_p6(data):
    data_date = (data.project or {}).get('data_date')
    groups = {}
    for a in data.activities.values():
        codes = a.get('activity_codes', {}) or {}
        trade = codes.get('Trade Design')
        dtype = _drawing_type(codes)
        if not trade or not dtype:
            continue
        sub_wbs = (codes.get('Design SUB WBS') or codes.get('Engineering SUB WBS') or '')
        aid = a.get('id', '') or ''
        is_sub = 'Submittal' in sub_wbs or '.SUB.' in aid
        is_app = 'Approval' in sub_wbs or '.APP.' in aid
        if not (is_sub or is_app):
            continue

        g = groups.setdefault((trade, dtype), {
            'req': 0, 'planned_sub': 0, 'actual_sub': 0,
            'planned_appr': 0, 'actual_appr': 0})
        done = _is_done(a)
        bl = (data.baseline_by_id.get(aid) or {}).get('planned_finish')
        planned = bl is not None and data_date is not None and bl <= data_date
        if is_sub:
            g['req'] += 1
            g['actual_sub'] += 1 if done else 0
            g['planned_sub'] += 1 if planned else 0
        if is_app:
            g['actual_appr'] += 1 if done else 0
            g['planned_appr'] += 1 if planned else 0

    result = {}
    for key, g in groups.items():
        req = g['req'] or 0
        pct = lambda n: round(100.0 * n / req, 1) if req else 0.0
        result[key] = {
            'req': req,
            'planned_sub': g['planned_sub'], 'actual_sub': g['actual_sub'],
            'planned_appr': g['planned_appr'], 'actual_appr': g['actual_appr'],
            'planned_sub_pct': pct(g['planned_sub']), 'actual_sub_pct': pct(g['actual_sub']),
            'planned_appr_pct': pct(g['planned_appr']), 'actual_appr_pct': pct(g['actual_appr']),
        }
    return result
