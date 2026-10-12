"""The tool against Primavera P6's own schedule log (SCHEDLOG.TXT), activity by activity.

P6 writes the log when it schedules (F9, 'Log to file'). It lists exactly the activities behind
four numbers of Schedule Health / Out of Sequence:

    Critical Activities                  -> CPLI / Float Analysis critical count
    Out-of-sequence activities           -> Out of Sequence
    Activities without predecessors      -> Open Ends (no predecessor)
    Activities without successors        -> Open Ends (no successor)

This reads those four lists from the log and compares them, as SETS of Activity IDs, with what the
tool reports for the same schedule file. Unlike tests/p6_spreadsheet_check.py (which proves the
tool against the values P6 stored in the XER), this proves it against what P6 itself printed.

    python tests/p6_schedlog_check.py <SCHEDLOG.TXT> <schedule.xer|.xml>

Exit code 1 when any list differs.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SECTIONS = {
    'critical':       'Critical Activities',
    'out_of_sequence': 'Out-of-sequence activities',
    'no_predecessor': 'Activities without predecessors',
    'no_successor':   'Activities without successors',
}


def read_log(path):
    """{section: (count printed by P6, [activity ids listed])} for the sections above."""
    with open(path, encoding='latin-1') as f:
        lines = f.read().splitlines()
    out = {}
    for key, title in SECTIONS.items():
        head = re.compile(r'^\s*' + re.escape(title) + r'\.{3,}\s*(\d+)\s*$')
        for i, line in enumerate(lines):
            m = head.match(line)
            if not m:
                continue
            ids = []
            for row in lines[i + 1:]:
                parts = row.split('\t')
                if 'Activity:' not in parts:
                    if row.strip() == '' or re.match(r'^\s*\S.*\.{3,}', row):
                        break
                    continue            # a wrapped activity name
                ids.append(parts[parts.index('Activity:') + 1].strip())
            out[key] = (int(m.group(1)), ids)
            break
    return out


def tool_lists(schedule_path):
    from p6_evm.parser import parse_file
    from p6_audit.engine import audit_modules
    with open(os.path.join(ROOT, 'config.json')) as f:
        cfg = json.load(f)
    data = parse_file(schedule_path)
    m = audit_modules(data, cfg)['modules']
    ends = m['open_ends']['findings']
    return {
        'critical':        [f['activity_id'] for f in m['cpli']['findings']],
        'out_of_sequence': [f['activity_id'] for f in m['out_of_sequence']['findings']],
        'no_predecessor':  [f['activity_id'] for f in ends if 'no predecessor' in f['issue'].lower()],
        'no_successor':    [f['activity_id'] for f in ends if 'no successor' in f['issue'].lower()],
    }


def check(log_path, schedule_path):
    """[(section, P6 count, tool count, only in P6, only in tool)]."""
    log, tool = read_log(log_path), tool_lists(schedule_path)
    rows = []
    for key in SECTIONS:
        if key not in log:
            continue
        count, ids = log[key]
        p6, mine = set(ids), set(tool[key])
        rows.append((SECTIONS[key], count, len(mine), sorted(p6 - mine), sorted(mine - p6)))
    return rows


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    bad = 0
    for title, count, mine, only_p6, only_tool in check(argv[0], argv[1]):
        ok = not only_p6 and not only_tool and count == mine
        bad += 0 if ok else 1
        print(f"{'OK  ' if ok else 'DIFF'} {title:<34} P6 log {count:>5}   tool {mine:>5}"
              + ('' if ok else f'   only in P6: {only_p6[:8]}   only in tool: {only_tool[:8]}'))
    print('\nEvery list matches the P6 schedule log.' if not bad else f'\n{bad} list(s) differ.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
