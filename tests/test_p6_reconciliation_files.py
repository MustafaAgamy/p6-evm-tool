"""The final P6 test (comment 5) on the real project schedules — every feature's figures equal
Primavera P6's own values in the export.

The schedules are client files and are not in the repository.  Point CONTROLYX_P6_FILES at the
folder holding them (MAFI XML, Grain Bulk / Saint Gobain / Alstom XER …) to run it:

    CONTROLYX_P6_FILES="D:\\Controlyx 2026 Course\\Baseline" pytest tests/test_p6_reconciliation_files.py

Without the folder the test is skipped.  2 Oct 2026: 619 checks on the 11 baseline and update
files (MAFI, Grain Bulk, Saint Gobain, Alstom; XER and XML) — all equal to P6, incl. the
Consultant Review but-for with no change applied: P6's finish and every open activity's
early finish, on every file.
"""
import glob
import http.client
import json
import os

import pytest

from tests.p6_reconcile import reconcile

FOLDER = os.environ.get('CONTROLYX_P6_FILES', '')
FILES = sorted(glob.glob(os.path.join(FOLDER, '*.xer')) + glob.glob(os.path.join(FOLDER, '*.xml'))) if FOLDER else []


@pytest.mark.slow
@pytest.mark.skipif(not FILES, reason='set CONTROLYX_P6_FILES to the folder of P6 schedules')
@pytest.mark.parametrize('path', FILES, ids=[os.path.basename(f) for f in FILES])
def test_every_feature_equals_p6(test_server, path):
    c = http.client.HTTPConnection('127.0.0.1', test_server, timeout=1800)
    c.request('POST', '/api/parse', body=json.dumps({'path': path}).encode(),
              headers={'Content-Type': 'application/json'})
    r = json.loads(c.getresponse().read())
    assert r.get('ok'), r.get('error')
    rows = reconcile(path, r['result'])
    bad = [f"{x['feature']} · {x['check']}: P6 {x['p6']} / tool {x['tool']} {x['note']}" for x in rows if not x['ok']]
    assert len(rows) > 20
    assert not bad, '\n'.join(bad)
