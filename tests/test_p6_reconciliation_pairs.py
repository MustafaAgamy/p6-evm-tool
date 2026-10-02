"""The final P6 test for the TWO-schedule features (comment 44) — Baseline Revision / Update vs
Update, Consultant Review, Critical Path Analyzer and Update Analysis on real baseline → update
pairs, every figure equal to what P6 wrote into the two files (tests/p6_reconcile_pairs.py).

The schedules are client files and are not in the repository. Point CONTROLYX_P6_FILES at the
folder holding the baselines and updates (Baseline.rar + Updates.rar, XER and XML, in one
folder) to run it; pairs whose files are missing are skipped.

2 Oct 2026: 222 checks on 6 pairs (Alstom BL R02 → UP-006 as XER and as XML, Saint Gobain
baseline → 7-Aug, 7-Aug → 22-Aug, baseline → 22-Aug XML, Grain Bulk → Update 19 Jul 2026) —
all equal to P6.
"""
import os

import pytest

from tests.p6_reconcile_pairs import reconcile_pair

FOLDER = os.environ.get('CONTROLYX_P6_FILES', '')
PAIRS = [
    ('Alstom-BL-R02 baselne.xer', 'Alstom-UP-006-12-Oct.25.xer'),
    ('Alstom-BL-R02 baselne.xer', 'Alstom-UP-006-12-Oct.25.xml'),
    ('SNT_GBN_Baseline_AS2-Fin-3.xer', 'SAINT GOBAIN, AS2 PKG3 - Update Cut of Date 7-Aug-2025.xer'),
    ('SAINT GOBAIN, AS2 PKG3 - Update Cut of Date 7-Aug-2025.xer', 'SNT_GBN_Update 22-Aug.2025.xer'),
    ('SNT_GBN_Baseline_AS2-Fin-3.xer', 'SNT_GBN_Update 22-Aug.2025.xml'),
    ('Grain Bulk Terminal - Phase I Scope Detailed Schedule.xer', 'Update Till 19 July.2026.xml'),
]


@pytest.mark.slow
@pytest.mark.skipif(not FOLDER, reason='set CONTROLYX_P6_FILES to the folder of P6 schedules')
@pytest.mark.parametrize('earlier,later', PAIRS, ids=[f'{a[:14]}->{b[:22]}' for a, b in PAIRS])
def test_two_schedule_features_equal_p6(earlier, later):
    a, b = os.path.join(FOLDER, earlier), os.path.join(FOLDER, later)
    if not (os.path.isfile(a) and os.path.isfile(b)):
        pytest.skip('pair not in the folder')
    rows = reconcile_pair(a, b)
    bad = [f"{x['feature']} · {x['check']}: P6 {x['p6']} / tool {x['tool']} {x['note']}" for x in rows if not x['ok']]
    assert len(rows) > 30
    assert not bad, '\n'.join(bad)
