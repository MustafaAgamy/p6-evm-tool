"""Golden reconciliation on REAL P6 exports: a XER update + its baseline must produce the SAME EVM
as the XML update, to the penny. Auto-discovers project triples (Update.xml + Update.xer + a
*baseline*.xer) in a local sample folder. Skips when that folder isn't present, so it validates on
Ibrahim's machine and never breaks CI (the real client schedules are NOT committed to the repo).

Point it at your own folder with the P6_GOLDEN_DIR env var, or drop the files in
'<home>/Desktop/XER File Test'. This is the definitive 'XER == XML for any project' guardrail.
"""
import json
import os
import re
from pathlib import Path

import pytest

from p6_evm.parser import parse_file
from p6_evm.metrics import compute
from p6_evm.classify import auto_categories, build_wbs_classifier
from p6_evm.baseline import apply_baseline


def _golden_dir():
    env = os.environ.get('P6_GOLDEN_DIR')
    for c in ([env] if env else []) + [str(Path.home() / 'Desktop' / 'XER File Test')]:
        if c and os.path.isdir(c):
            return c
    return None


GOLDEN = _golden_dir()


def _token(name):
    return re.split(r'[^A-Za-z0-9]', name)[0].lower()


def _discover(folder):
    files = os.listdir(folder)
    xmls = {os.path.splitext(f)[0]: f for f in files if f.lower().endswith('.xml')}
    xers = [f for f in files if f.lower().endswith('.xer')]
    baselines = [f for f in xers if re.search(r'baseline|(?<![a-z])bl(?![a-z])', f, re.I)]
    out = []
    for stem, xml in xmls.items():
        xer = next((x for x in xers if os.path.splitext(x)[0] == stem), None)
        if not xer:
            continue
        tok = _token(stem)
        bl = next((b for b in baselines if _token(b) == tok or tok in b.lower()), None)
        if bl:
            out.append((stem, xml, xer, bl))
    return out


def _evm(data):
    with open('config.json') as f:
        cfg = json.load(f)
    cfg['categories'] = auto_categories(data)
    return compute(data, cfg, classifier=build_wbs_classifier(data))


PROJECTS = _discover(GOLDEN) if GOLDEN else []


@pytest.mark.skipif(not PROJECTS, reason='no golden sample folder — set P6_GOLDEN_DIR or add ~/Desktop/XER File Test')
@pytest.mark.parametrize('stem,xml,xer,bl', PROJECTS, ids=[_token(p[0]).upper() for p in PROJECTS])
def test_xer_update_matches_xml_update(stem, xml, xer, bl):
    rx = _evm(parse_file(os.path.join(GOLDEN, xml)))
    dy = parse_file(os.path.join(GOLDEN, xer))
    apply_baseline(dy, parse_file(os.path.join(GOLDEN, bl)))
    ry = _evm(dy)

    assert round(rx['pv'], 2) == round(ry['pv'], 2), 'PV'
    assert round(rx['ev'], 2) == round(ry['ev'], 2), 'EV'
    assert round(rx['ac'], 2) == round(ry['ac'], 2), 'AC'
    assert rx['delay_days'] == ry['delay_days'], 'Delay'
    for k in ('spi', 'cpi', 'overall_planned_pct', 'overall_actual_pct'):
        a, b = rx[k], ry[k]
        assert (a is None and b is None) or abs(a - b) <= 0.0005, k
    # every category: planned% / actual% / BAC
    for name in set(rx['categories']) | set(ry['categories']):
        cx, cy = rx['categories'].get(name), ry['categories'].get(name)
        assert cx and cy, f'category {name} missing on one side'
        assert abs(cx['planned_pct'] - cy['planned_pct']) <= 0.0005, f'{name} planned%'
        assert abs(cx['actual_pct'] - cy['actual_pct']) <= 0.0005, f'{name} actual%'
        assert abs(cx['bac'] - cy['bac']) <= 0.01, f'{name} BAC'
