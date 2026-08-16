"""Construction Database — example baselines (clean/gappy) + contributed-file store."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb.kb import load_kb
from p6_kb.examples import build_example_xml, write_example_xml
from p6_kb import database
from p6_kb.review import run_review
from p6_evm.parser import parse_file

ENTRIES = {e['type']: e for e in load_kb()}
MDF = ENTRIES['MDF / Wood Panel Factory']


def _review(xml_text):
    fd, p = tempfile.mkstemp(suffix='.xml')
    os.close(fd)
    try:
        with open(p, 'w', encoding='utf-8') as f:
            f.write(xml_text)
        return run_review(parse_file(p))
    finally:
        os.remove(p)


def test_clean_example_is_gap_free():
    xml, seeded = build_example_xml(MDF, gappy=False)
    assert seeded == {'illogical_seeded': 0, 'missing_seeded': 0}
    rep = _review(xml)
    assert rep['dashboard']['illogical_count'] == 0
    assert rep['dashboard']['missing_count'] == 0
    assert rep['score']['overall'] >= 90


def test_gappy_example_shows_real_gaps():
    xml, seeded = build_example_xml(MDF, gappy=True)
    assert seeded['illogical_seeded'] >= 1 and seeded['missing_seeded'] >= 1
    rep = _review(xml)
    # the seeded gaps must actually surface in a review against the full standard
    assert rep['dashboard']['illogical_count'] >= 1
    assert rep['dashboard']['missing_count'] >= 1
    clean = _review(build_example_xml(MDF, gappy=False)[0])
    assert rep['score']['overall'] < clean['score']['overall']


def _fake_import(gappy=True):
    fd, p = tempfile.mkstemp(suffix='.xml')
    os.close(fd)
    write_example_xml(MDF, p, gappy=gappy)
    return p, parse_file(p)


def test_add_import_indexes_and_dedups():
    with tempfile.TemporaryDirectory() as base:
        path, data = _fake_import()
        try:
            rec = database.add_import(path, data, base=base, when='2026-01-01')
            assert rec and rec['type'] == 'MDF / Wood Panel Factory'
            idx = database.load_index(base)
            files = next(v['files'] for v in idx.values() if v['type'] == MDF['type'])
            assert len(files) == 1
            # re-adding the identical file must not duplicate
            database.add_import(path, data, base=base, when='2026-01-02')
            idx = database.load_index(base)
            files = next(v['files'] for v in idx.values() if v['type'] == MDF['type'])
            assert len(files) == 1
            # the stored file resolves
            assert database.contributed_path(MDF['type'], files[0]['filename'], base=base)
        finally:
            os.remove(path)


def test_list_database_covers_all_types():
    with tempfile.TemporaryDirectory() as base:
        out = database.list_database(base=base)
        assert out['types_total'] == len(ENTRIES)
        assert out['contributed_total'] == 0
        cats = {c['category'] for c in out['categories']}
        assert 'Industrial' in cats and 'Buildings' in cats
