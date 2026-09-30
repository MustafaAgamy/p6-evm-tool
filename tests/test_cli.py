"""Smoke test for cli.py — the terminal entry point.

Runs the CLI as a subprocess against the minimal fixture and checks that it
prints expected headers without crashing.  No DB or server involved.
"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
FIXTURE_XML  = Path(__file__).parent / 'fixtures' / 'minimal.xml'


def test_cli_runs_without_error():
    result = subprocess.run(
        [sys.executable, 'cli.py', str(FIXTURE_XML)],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, f'CLI exited {result.returncode}:\n{result.stderr}'


def test_cli_output_contains_expected_headers():
    result = subprocess.run(
        [sys.executable, 'cli.py', str(FIXTURE_XML)],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    for expected in ('Data Date:', 'SPI:', 'Planned Value (PV):', 'By category:'):
        assert expected in result.stdout, f'Missing header: {expected!r}'


# ── R2 F5: --baseline — XER + its baseline == XML with it, and the baseline is always named ──
import json
import os
import re

from tests.test_parser_parity import build_xer, build_xml

_KEYS = ('Planned Value (PV):', 'Earned Value  (EV):', 'SPI:', 'Overall Project Planned%:',
         'Delay (finish-milestone Total Float):')


def _files(tmp_path):
    x = build_xml()
    # the baseline project exported on its own (what the planner attaches): the XML's
    # <BaselineProject> as a <Project>, beside the global calendars / codes / resources
    bl = re.sub(r'\n<Project>\n.*?\n</Project>', '', x, flags=re.S)
    bl = bl.replace('<BaselineProject>', '<Project>').replace('</BaselineProject>', '</Project>')
    cfg = {'categories': [{'name': 'Engineering', 'weight': 0.2, 'wbs_match': 'Engineering'},
                          {'name': 'Construction', 'weight': 0.8, 'wbs_match': 'Construction'}]}
    out = {}
    for name, text in {'upd_bl.xml': x, 'upd_nobl.xml': build_xml(with_baseline=False),
                       'upd.xer': build_xer(baseline_rows=False), 'baseline.xml': bl,
                       'cfg.json': json.dumps(cfg)}.items():
        p = tmp_path / name
        p.write_text(text, encoding='utf-8', newline='')
        out[name] = str(p)
    return out


def _run(f, *args):
    r = subprocess.run([sys.executable, 'cli.py', *args, '--config', f['cfg.json']],
                       capture_output=True, text=True, encoding='utf-8', cwd=str(PROJECT_ROOT),
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    figures = {k: next(ln.split(k, 1)[1].strip() for ln in lines if k in ln) for k in _KEYS}
    return lines[0], figures, r.stderr


def test_cli_baseline_attached_to_xer_or_xml_matches_the_xml_with_it(tmp_path):
    f = _files(tmp_path)
    head_x, want, _ = _run(f, f['upd_bl.xml'])
    assert head_x == 'Baseline: inside the schedule file (Parity Test Project - Baseline)'
    assert want['Planned Value (PV):'] != '0.00'
    for upd in ('upd.xer', 'upd_nobl.xml'):
        head, got, _ = _run(f, f[upd], '--baseline', f['baseline.xml'])
        assert head == 'Baseline: attached: baseline.xml (7/7 activities matched)'
        assert got == want, upd


def test_cli_without_a_baseline_says_so_and_marks_approx(tmp_path):
    f = _files(tmp_path)
    _, want, _ = _run(f, f['upd_bl.xml'])
    head, got, _ = _run(f, f['upd.xer'])
    assert head.startswith('Baseline: not in the file and none attached')
    assert got['Planned Value (PV):'].endswith('(approx)')
    assert got['SPI:'].endswith('(approx)')
    assert got['Planned Value (PV):'] != want['Planned Value (PV):']   # own dates, not the baseline


def test_cli_baseline_is_not_used_over_an_embedded_one(tmp_path):
    f = _files(tmp_path)
    head, _, err = _run(f, f['upd_bl.xml'], '--baseline', f['baseline.xml'])
    assert head.startswith('Baseline: inside the schedule file')
    assert '--baseline was not used' in err


def test_cli_baseline_missing_file_is_an_error(tmp_path):
    r = subprocess.run([sys.executable, 'cli.py', str(FIXTURE_XML), '--baseline',
                        str(tmp_path / 'nope.xer')], capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    assert r.returncode == 2 and 'file not found' in r.stderr
