"""The Knowledge Base loads the bundled Rail + Factory drafts, and a user overlay
overrides a bundled entry with the same (category, type)."""
import json
import os

from p6_kb.kb import load_kb


def test_bundled_kb_has_rail_and_factory():
    entries = load_kb(overlay='')  # bundled only
    types = {(e['category'], e['type']) for e in entries}
    assert ('Infrastructure', 'Rail') in types
    assert ('Industrial', 'Factory') in types
    rail = next(e for e in entries if e['type'] == 'Rail')
    for key in ('signatures', 'wbs', 'activities', 'logic_rules'):
        assert rail.get(key)


def test_overlay_overrides_bundled(tmp_path):
    cat = tmp_path / 'infrastructure'
    cat.mkdir()
    (cat / 'rail.json').write_text(json.dumps({
        'category': 'Infrastructure', 'type': 'Rail', 'signatures': ['CUSTOM'],
        'wbs': [], 'activities': [], 'logic_rules': []}), encoding='utf-8')
    entries = load_kb(overlay=str(tmp_path))
    rail = next(e for e in entries if e['type'] == 'Rail')
    assert rail['signatures'] == ['CUSTOM']  # overlay won
    # factory still comes from the bundled set
    assert any(e['type'] == 'Factory' for e in entries)


def test_logic_rule_impacts_use_agreed_vocabulary():
    # Impact must be one the severity pill knows, or it renders understated.
    allowed = {'Critical', 'Near-critical', 'Minor'}
    for entry in load_kb(overlay=''):
        for rule in entry.get('logic_rules', []):
            assert rule.get('impact', 'Minor') in allowed, (entry['type'], rule.get('impact'))


def test_missing_dirs_are_safe():
    assert load_kb(bundled='', overlay='') == []
