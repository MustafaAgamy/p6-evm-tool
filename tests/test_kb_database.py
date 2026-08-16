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


def test_review_blends_learned_knowledge_into_the_standard():
    """A recurring activity learned from added schedules — but absent from the
    schedule under review — is flagged missing (basis 'your projects')."""
    import types
    from p6_kb import learn
    entry = {'type': 'MDF / Wood Panel Factory', 'category': 'Industrial'}

    def fake(names):
        d = types.SimpleNamespace()
        d.activities = {f'A{i}': {'name': n, 'id': f'A{i}', 'planned_duration': 80,
                                  'wbs_path': '', 'task_type': 'Task'} for i, n in enumerate(names)}
        d.wbs = {'W0': {'name': 'Press Line'}}
        d.relationships = []
        d.project = {'id': ''}
        return d

    with tempfile.TemporaryDirectory() as base:
        # two added schedules that both contain a custom recurring activity
        for h in ('p1', 'p2'):
            learn._fold(fake(['Hot Press Installation', 'Custom Special Handover Test']), entry, h, base)
        fd, xml = tempfile.mkstemp(suffix='.xml')
        os.close(fd)
        write_example_xml(MDF, xml, gappy=False)   # clean starter — lacks the custom activity
        try:
            rep = run_review(parse_file(xml), learn_base=base)
            assert rep['knowledge_enhanced'] is True
            miss_names = [m['name'] for m in rep['missing']]
            assert any('Custom Special Handover Test' in n for n in miss_names)
            assert any(m.get('basis') == 'your projects' for m in rep['missing'])
            # with no learned data the same schedule is gap-free — enhancement did work
            base_rep = run_review(parse_file(xml), learn_base=tempfile.mkdtemp())
            assert base_rep['dashboard']['missing_count'] < rep['dashboard']['missing_count']
        finally:
            os.remove(xml)
