"""Network analysis of the loaded schedule for the Offline AI Chat.

The DB snapshot holds the headline numbers (EVM, audit KPIs); the questions a planner actually asks —
*what* is setting the finish, *which* milestones slipped, *which* client inputs are late — need the
network itself. ``network(snapshot_id)`` re-parses the snapshot's P6 file (the sanctioned report
exception, same path as the chat dashboard) and returns plain, JSON-ready facts. Generic: nothing here
knows about any particular project. Cached per (file, mtime) so a conversation re-parses once.

Sign convention: total float negative = behind; ``slip_wd`` = working days the current finish sits
after the baseline finish (positive = later than baseline).
"""
import json
import os
import threading

_CACHE = {}
_LOCK = threading.Lock()

# WBS / activity words that mark an input the EMPLOYER (client, owner, consultant) must provide.
CLIENT_WORDS = ('client', 'employer', 'owner', 'free issue', 'free-issue', 'furnished by', 'by client',
                'inputs required', 'consultant approval', 'approval from consultant')
CHAIN_BAND = 5          # working days either side of the finish milestone's float = "on the finish chain"
CAP = 60                # never ship more than this many rows per list


def _fmt(d):
    return d.strftime('%d-%b-%Y') if d else None


def _analyse(path):
    from utils import resource_path
    from p6_evm.parser import parse_file
    from p6_evm.metrics import compute
    from p6_evm.classify import auto_categories, build_wbs_classifier
    from p6_evm.calendars import signed_working_days

    with open(resource_path('config.json')) as f:
        cfg = dict(json.load(f))
    data = parse_file(path)
    cfg['categories'] = auto_categories(data)
    res = compute(data, cfg, classifier=build_wbs_classifier(data))
    dd = data.project.get('data_date')

    def wbs_path(wid, depth=4):
        names, cur, seen = [], wid, set()
        while cur and cur not in seen:
            seen.add(cur)
            node = data.wbs.get(cur)
            if not node:
                break
            names.append(node.get('name') or '')
            cur = node.get('parent_object_id')
        return ' / '.join([n for n in reversed(names) if n][:depth])

    def finish(a):
        return a.get('remaining_early_finish') or a.get('planned_finish')

    def row(r):
        a = r['activity']
        bl = (data.baseline_by_id.get(a['id']) or {}).get('planned_finish')
        cur = finish(a)
        cal = data.calendars.get(a.get('calendar_id'))
        slip = signed_working_days(cal, bl, cur) if (cal and bl and cur) else None
        tf = r.get('total_float')
        return {'id': a['id'], 'name': a.get('name') or '', 'tf': None if tf is None else round(tf),
                'pct': round((a.get('percent_complete') or 0) * 100), 'finish': _fmt(cur),
                'baseline_finish': _fmt(bl), 'slip_wd': slip, 'wbs': wbs_path(a.get('wbs_id')),
                'type': a.get('task_type') or '', 'done': (a.get('percent_complete') or 0) >= 1}

    recs = res.get('records') or []
    rows = [row(r) for r in recs]
    open_rows = [x for x in rows if not x['done'] and x['tf'] is not None]

    # finish milestone = the latest-finishing Finish Milestone (same rule as metrics.compute)
    fms = [x for x in rows if x['type'] == 'FinishMilestone' and x['finish']]
    from datetime import datetime
    key = lambda x: datetime.strptime(x['finish'], '%d-%b-%Y')
    project_end = ('scope completion', 'project completion', 'practical completion', 'handover', 'taking over',
                   'substantial completion', 'project finish')
    # latest finish wins; on a tie prefer the milestone that names the project's own completion
    fin = max(fms, key=lambda x: (key(x), any(w in x['name'].lower() for w in project_end))) if fms else None
    fin_tf = fin['tf'] if fin else (min((x['tf'] for x in open_rows), default=None))

    chain = []
    if fin_tf is not None:
        chain = [x for x in open_rows if fin_tf - CHAIN_BAND <= x['tf'] <= fin_tf + 1 and x is not fin]
        chain.sort(key=lambda x: key(x) if x['finish'] else datetime.max)
    deepest = sorted(open_rows, key=lambda x: x['tf'])[:8]

    milestones = [x for x in rows if 'Milestone' in x['type']]
    milestones.sort(key=lambda x: key(x) if x['finish'] else datetime.max)

    def is_client(x):
        t = (x['wbs'] + ' ' + x['name']).lower()
        return any(w in t for w in CLIENT_WORDS)
    client = sorted([x for x in rows if is_client(x)], key=lambda x: -(x['slip_wd'] or 0))

    level2 = {}
    for x in rows:
        k = ' / '.join(x['wbs'].split(' / ')[:2]) or '(no WBS)'
        level2[k] = level2.get(k, 0) + 1
    wbs_top = sorted(level2.items(), key=lambda kv: -kv[1])[:15]

    return {
        'ok': True,
        'data_date': _fmt(dd),
        'activity_count': len(rows),
        'open_count': len(open_rows),
        'finish_milestone': fin,
        'finish_tf': fin_tf,
        'chain': chain[:CAP],
        'chain_count': len(chain),
        'chain_band': CHAIN_BAND,
        'deepest': deepest,
        'milestones': milestones[:CAP],
        'milestones_open_late': [x for x in milestones if not x['done'] and (x['slip_wd'] or 0) > 0],
        'client_inputs': client[:CAP],
        'client_inputs_late_open': [x for x in client if not x['done'] and (x['slip_wd'] or 0) > 0],
        'client_inputs_late_done': [x for x in client if x['done'] and (x['slip_wd'] or 0) > 0],
        'wbs_top': [{'branch': k, 'activities': v} for k, v in wbs_top],
        # a small, name-bearing view for the Knowledge Base detector (reads names, not numbers)
        'kb_view': {'activities': [{'name': x['name'], 'wbs_path': x['wbs']} for x in rows], 'wbs': []},
    }


def network(snapshot_id=None, xml_path=None):
    """Network facts for the snapshot's schedule, or {'ok': False, 'error': ...}. Never raises."""
    try:
        path = xml_path
        if not path and snapshot_id is not None:
            import db
            path = db.get_snapshot_xml_path(snapshot_id)
        if not path or not os.path.isfile(path):
            return {'ok': False, 'error': 'The schedule file for this project was not found — re-import it.'}
        key = (os.path.abspath(path), os.path.getmtime(path))
        with _LOCK:
            if key in _CACHE:
                return _CACHE[key]
        out = _analyse(path)
        with _LOCK:
            _CACHE.clear() if len(_CACHE) > 4 else None
            _CACHE[key] = out
        return out
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}
