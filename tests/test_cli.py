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
