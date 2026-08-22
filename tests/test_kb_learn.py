"""Local learning — per-type profiles grown from imports (private, offline)."""
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb import learn
from p6_kb.kb import load_kb
from p6_kb.starter import write_starter_xml
from p6_kb.model import schedule_view
from p6_evm.parser import parse_file


def _fake(activities, wbs):
    """A minimal stand-in for ScheduleData: .activities and .wbs dicts."""
    d = types.SimpleNamespace()
    d.activities = {f'A{i}': {'name': n, 'id': f'A{i}', 'planned_duration': h,
                              'wbs_path': '', 'task_type': 'Task'}
                    for i, (n, h) in enumerate(activities)}
    d.wbs = {f'W{i}': {'name': n} for i, n in enumerate(wbs)}
    d.relationships = []
    return d


ENTRY = {'type': 'Test Type', 'category': 'Industrial'}


def test_counts_and_dedup_by_hash():
    with tempfile.TemporaryDirectory() as base:
        acts = [('Excavation', 80), ('Foundations', 160), ('Steel Erection', 240)]
        d = _fake(acts, ['Substructure', 'Superstructure'])
        p = learn._fold(d, ENTRY, 'hash-1', base)
        assert p['imports'] == 1
        # re-importing the same file (same hash) must not inflate
        p = learn._fold(d, ENTRY, 'hash-1', base)
        assert p['imports'] == 1
        assert p['activities'][learn._norm('Excavation')]['seen'] == 1
        # a different file of the same type counts
        p = learn._fold(d, ENTRY, 'hash-2', base)
        assert p['imports'] == 2
        assert p['activities'][learn._norm('Steel Erection')]['seen'] == 2
        # duration tracked in days (hours / 8)
        rec = p['activities'][learn._norm('Foundations')]
        assert round(rec['dur_sum'] / rec['dur_count']) == 20


def test_recurring_threshold_and_panel():
    with tempfile.TemporaryDirectory() as base:
        common = [('Excavation', 80), ('Foundations', 160)]
        # import #1 has an extra one-off activity; #2 and #3 don't
        learn._fold(_fake(common + [('One-off Temporary Works', 40)], ['Sub']), ENTRY, 'h1', base)
        learn._fold(_fake(common, ['Sub']), ENTRY, 'h2', base)
        learn._fold(_fake(common, ['Sub']), ENTRY, 'h3', base)
        prof = learn.load_profile('Test Type', base)
        assert prof['imports'] == 3
        rec_names = {r['name'] for r in learn.recurring_activities(prof)}
        assert 'Excavation' in rec_names and 'Foundations' in rec_names
        assert 'One-off Temporary Works' not in rec_names  # seen once → not recurring

        # a schedule missing "Foundations" flags it in the panel
        view = schedule_view(_fake([('Excavation', 80)], ['Sub']))
        panel = learn.learned_panel(prof, view)
        assert panel['imports'] == 3
        missing = [a['name'] for a in panel['activities'] if not a['in_schedule']]
        assert 'Foundations' in missing
        assert panel['missing_count'] >= 1


def test_learned_entry_is_kb_shaped():
    with tempfile.TemporaryDirectory() as base:
        for h in ('h1', 'h2'):
            learn._fold(_fake([('Excavation', 80), ('Piling', 120)], ['Substructure']), ENTRY, h, base)
        entry = learn.learned_entry(learn.load_profile('Test Type', base))
        assert entry['status'] == 'learned' and entry['category'] == 'Learned from your projects'
        assert {a['name'] for a in entry['activities']} == {'Excavation', 'Piling'}
        assert all('duration_days' in a for a in entry['activities'])


def test_end_to_end_detects_and_learns():
    # Generate a real schedule, parse it, and confirm learning detects the type.
    entry = next(e for e in load_kb() if e['type'] == 'MDF / Wood Panel Factory')
    with tempfile.TemporaryDirectory() as base:
        fd, xml = tempfile.mkstemp(suffix='.xml')
        os.close(fd)
        try:
            write_starter_xml(entry, xml)
            data = parse_file(xml)
            prof = learn.learn_from_schedule(data, file_hash='e2e-1', base=base,
                                             entries=load_kb())
            assert prof is not None
            assert prof['type'] == 'MDF / Wood Panel Factory'
            assert prof['imports'] == 1
        finally:
            os.remove(xml)
