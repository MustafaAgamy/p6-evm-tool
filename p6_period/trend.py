"""Milestone finish trend across every stored update — the slip chart.

Walks all snapshots of the project (oldest first), extracting each snapshot's milestone
finishes once (cached in the DB, backfilled by parsing the stored XML), and assembles a
series per key milestone: its forecast finish over the successive data dates. A rising
series = that milestone's finish keeps slipping later; flat = holding.
"""
_MILESTONES = ('StartMilestone', 'FinishMilestone')


def extract_milestones(data):
    """[{activity_id, name, task_type, finish_date(iso)}] for a parsed schedule."""
    out = []
    for a in getattr(data, 'activities', {}).values():
        if a.get('task_type') in _MILESTONES:
            code = a.get('id')
            if not code:
                continue
            fin = a.get('remaining_early_finish') or a.get('planned_finish') or a.get('actual_finish')
            out.append({'activity_id': code, 'name': a.get('name', ''),
                        'task_type': a.get('task_type'),
                        'finish_date': fin.strftime('%Y-%m-%d') if fin else None})
    return out


def assemble_trend(snapshots_meta, milestones_per_snapshot, max_series=8):
    """Pure assembly. `snapshots_meta` = [{data_date}], `milestones_per_snapshot` = a
    parallel list of milestone lists. Returns {'periods': [...], 'series': [...]}.

    Series are chosen from the LATEST snapshot's milestones, finish milestones first,
    then latest finishes; capped at max_series."""
    periods = [str(s.get('data_date') or '')[:10] for s in snapshots_meta]
    per_snap, latest_meta = [], {}
    for ms in milestones_per_snapshot:
        m = {}
        for r in ms:
            m[r['activity_id']] = r.get('finish_date')
            latest_meta[r['activity_id']] = {'name': r.get('name'), 'task_type': r.get('task_type')}
        per_snap.append(m)
    latest = per_snap[-1] if per_snap else {}
    codes = list(latest.keys()) or list(latest_meta.keys())
    finish_ms = [c for c in codes if latest_meta.get(c, {}).get('task_type') == 'FinishMilestone']
    others = [c for c in codes if c not in finish_ms]
    finish_ms.sort(key=lambda c: latest.get(c) or '', reverse=True)
    chosen = (finish_ms + others)[:max_series]
    series = [{
        'code': c,
        'name': latest_meta.get(c, {}).get('name') or c,
        'task_type': latest_meta.get(c, {}).get('task_type'),
        'finishes': [snap.get(c) for snap in per_snap],
    } for c in chosen]
    return {'periods': periods, 'series': series}


def _milestones_for_snapshot(snap, db, parse_file):
    """Cached milestone finishes for one snapshot; parse+cache on first sight."""
    sid = snap['id']
    scanned, rows = db.get_snapshot_milestones(sid)
    if scanned:
        return rows
    path = db.resolve_xml_path(snap.get('original_path'), snap.get('cached_path'))
    milestones = []
    if path:
        try:
            milestones = extract_milestones(parse_file(path))
        except Exception:
            milestones = []
    db.cache_snapshot_milestones(sid, milestones)
    return milestones


def milestone_trend(snapshot_id, max_series=8, db_module=None, parse=None):
    """Trend dict for the project owning `snapshot_id`. IO is injectable for testing;
    defaults to the real db module and p6_evm.parser.parse_file."""
    if db_module is None:
        import db as db_module
    if parse is None:
        from p6_evm.parser import parse_file as parse
    pid = db_module.snapshot_project_id(snapshot_id)
    if pid is None:
        return {'periods': [], 'series': []}
    snaps = db_module.get_project_snapshot_files(pid)
    if not snaps:
        return {'periods': [], 'series': []}
    milestones_per = [_milestones_for_snapshot(s, db_module, parse) for s in snaps]
    return assemble_trend(snaps, milestones_per, max_series)
