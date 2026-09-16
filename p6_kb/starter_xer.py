"""Starter-baseline export as a Primavera **XER** file.

Turns a Knowledge Base project-type WBS into an importable P6 XER skeleton: the
suggested WBS tree (exactly what the screen shows — screen == file), a placeholder
works activity per main branch, and start / finish milestones chained Finish-to-
Start so P6 schedules it on F9. A reference skeleton, not a finished programme;
nothing here comes from a real schedule.

Field/table names are the real Primavera XER names (PROJECT / PROJWBS / TASK /
TASKPRED / CALENDAR), so the file both round-trips through the tool's own
``p6_evm.xer.parse_xer`` (a validity check) and imports into Primavera P6.
"""

DAY_HR = 8.0
BRANCH_DAYS = 20

# A plain 5-day, 8-hour standard calendar in P6 clndr_data form (Mon–Fri
# 08:00–12:00 / 13:00–17:00; day 1 = Sunday). Single line — no tabs/newlines.
_CLNDR_DATA = (
    "(0||CalendarData()("
    "(0||DaysOfWeek()("
    "(0||1()())"
    "(0||2()(0|s|08:00|f|12:00)(0|s|13:00|f|17:00))"
    "(0||3()(0|s|08:00|f|12:00)(0|s|13:00|f|17:00))"
    "(0||4()(0|s|08:00|f|12:00)(0|s|13:00|f|17:00))"
    "(0||5()(0|s|08:00|f|12:00)(0|s|13:00|f|17:00))"
    "(0||6()(0|s|08:00|f|12:00)(0|s|13:00|f|17:00))"
    "(0||7()())"
    "))(0||Exceptions()())))"
)


def _clean(v):
    """XER values are tab/newline delimited — never allow either inside a value."""
    return str('' if v is None else v).replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')


def _table(name, fields, rows):
    out = ['%T\t' + name, '%F\t' + '\t'.join(fields)]
    for r in rows:
        out.append('%R\t' + '\t'.join(_clean(r.get(f, '')) for f in fields))
    return '\n'.join(out)


def _parent_code(code):
    """The WBS code one level up: 'DC.02.20' -> 'DC.02'; 'DC' -> None."""
    if not code or '.' not in code:
        return None
    return code.rsplit('.', 1)[0]


def build_starter_xer(project_name, wbs_rows, proj_id='1', clndr_id='1',
                      data_date='2025-01-01 00:00', start_date='2025-01-01 08:00'):
    """Return the XER text for a starter schedule built from ``wbs_rows``.

    ``wbs_rows`` = ``[{'code', 'name', 'level'}, ...]`` (the curated WBS). The
    first level-1 row becomes the project's root WBS node; the rest hang off it by
    code prefix. A works activity is added per level-2 branch, bracketed by start
    and finish milestones, chained Finish-to-Start.
    """
    rows = [w for w in (wbs_rows or []) if w.get('code')]
    if not rows:
        rows = [{'code': 'PRJ', 'name': project_name or 'Project', 'level': 1}]

    # ── WBS: assign ids; the level-1 row is the project (root) node ──
    code_to_id, projwbs, seq = {}, [], 0
    root_code = next((w['code'] for w in rows if int(w.get('level', 1)) == 1), rows[0]['code'])
    for i, w in enumerate(rows, start=1):
        wid = str(1000 + i)
        code_to_id[w['code']] = wid
    for i, w in enumerate(rows, start=1):
        seq += 10
        wid = code_to_id[w['code']]
        is_root = (w['code'] == root_code)
        parent_code = _parent_code(w['code'])
        parent_id = code_to_id.get(parent_code, '') if not is_root else ''
        projwbs.append({
            'wbs_id': wid, 'proj_id': proj_id, 'obs_id': '', 'seq_num': str(seq),
            'est_wt': '1', 'proj_node_flag': 'Y' if is_root else 'N',
            'sum_data_flag': 'N', 'status_code': 'WS_Open',
            'wbs_short_name': w['code'], 'wbs_name': w.get('name') or w['code'],
            'parent_wbs_id': parent_id,
        })
    root_id = code_to_id[root_code]

    # ── TASK: start MS, a works task per level-2 branch, finish MS ──
    tasks, order = [], []
    tid = 2000

    def add_task(name, wbs_id, ttype, days):
        nonlocal tid
        tid += 1
        hr = 0 if ttype in ('TT_Mile', 'TT_FinMile') else round(days * DAY_HR, 2)
        tasks.append({
            'task_id': str(tid), 'proj_id': proj_id, 'wbs_id': wbs_id,
            'clndr_id': clndr_id, 'task_code': f'A{tid}', 'task_name': name,
            'task_type': ttype, 'status_code': 'TK_NotStart',
            'complete_pct_type': 'CP_Drtn', 'phys_complete_pct': '0',
            'target_drtn_hr_cnt': str(hr), 'remain_drtn_hr_cnt': str(hr),
            'target_start_date': '', 'target_end_date': '',
        })
        order.append(str(tid))
        return str(tid)

    add_task('Project Start', root_id, 'TT_Mile', 0)
    for w in rows:
        if int(w.get('level', 1)) == 2:
            add_task(f"{w.get('name') or w['code']} — works", code_to_id[w['code']], 'TT_Task', BRANCH_DAYS)
    add_task('Project Finish', root_id, 'TT_FinMile', 0)

    # ── TASKPRED: chain Finish-to-Start in creation order ──
    preds, pid = [], 3000
    for pred, succ in zip(order, order[1:]):
        pid += 1
        preds.append({'task_pred_id': str(pid), 'task_id': succ, 'pred_task_id': pred,
                      'proj_id': proj_id, 'pred_proj_id': proj_id,
                      'pred_type': 'PR_FS', 'lag_hr_cnt': '0'})

    # ── assemble ──
    parts = ['ERMHDR\t19.12\t2025-01-01\tProject\tadmin\tadmin\tdb\tProject Management\tUSD']
    parts.append(_table('CALENDAR',
        ['clndr_id', 'default_flag', 'clndr_name', 'proj_id', 'base_clndr_id',
         'last_chng_date', 'clndr_type', 'day_hr_cnt', 'week_hr_cnt', 'month_hr_cnt',
         'year_hr_cnt', 'rsrc_private', 'clndr_data'],
        [{'clndr_id': clndr_id, 'default_flag': 'Y', 'clndr_name': 'Standard 5-Day Workweek',
          'proj_id': '', 'base_clndr_id': '', 'last_chng_date': '', 'clndr_type': 'CA_Base',
          'day_hr_cnt': '8', 'week_hr_cnt': '40', 'month_hr_cnt': '172', 'year_hr_cnt': '2000',
          'rsrc_private': 'N', 'clndr_data': _CLNDR_DATA}]))
    parts.append(_table('PROJECT',
        ['proj_id', 'proj_short_name', 'clndr_id', 'plan_start_date', 'plan_end_date',
         'last_recalc_date', 'sum_data_date', 'task_code_base', 'task_code_step'],
        [{'proj_id': proj_id, 'proj_short_name': (project_name or 'PROJ')[:20],
          'clndr_id': clndr_id, 'plan_start_date': start_date, 'plan_end_date': '',
          'last_recalc_date': data_date, 'sum_data_date': data_date,
          'task_code_base': '1000', 'task_code_step': '10'}]))
    parts.append(_table('PROJWBS',
        ['wbs_id', 'proj_id', 'obs_id', 'seq_num', 'est_wt', 'proj_node_flag',
         'sum_data_flag', 'status_code', 'wbs_short_name', 'wbs_name', 'parent_wbs_id'],
        projwbs))
    parts.append(_table('TASK',
        ['task_id', 'proj_id', 'wbs_id', 'clndr_id', 'task_code', 'task_name', 'task_type',
         'status_code', 'complete_pct_type', 'phys_complete_pct', 'target_drtn_hr_cnt',
         'remain_drtn_hr_cnt', 'target_start_date', 'target_end_date'],
        tasks))
    parts.append(_table('TASKPRED',
        ['task_pred_id', 'task_id', 'pred_task_id', 'proj_id', 'pred_proj_id',
         'pred_type', 'lag_hr_cnt'],
        preds))
    parts.append('%E')
    return '\n'.join(parts) + '\n', {'wbs': len(projwbs), 'activities': len(tasks),
                                     'relationships': len(preds)}


def write_starter_xer(project_name, wbs_rows, output_path):
    """Write the starter XER to ``output_path``; return a small summary dict."""
    text, summary = build_starter_xer(project_name, wbs_rows)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(text)
    summary['path'] = output_path
    summary['type'] = project_name
    return summary
