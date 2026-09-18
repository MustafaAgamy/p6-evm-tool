"""Planning Knowledge Engine — multi-level generalized learning from imported projects,
with provenance, as SUPPORTING context only (never creates a finding). Curated KB is the
day-1 baseline; real project imports grow rich, project-agnostic intelligence."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(__file__))

from p6_kb import pattern_learning as PL
from p6_kb.findings import generate_findings
from p6_kb.resolve import resolve
from test_kb_findings_r3_r7 import mkview


def _proc(zone, rels=((0, 1), (1, 2))):
    # process-piping + equipment; `zone` only varies the NAMES, not the concept
    return mkview([f'{zone} Process Pipe Spool Erection', f'{zone} Process Pipe Hydrotest',
                   f'{zone} Process Pipe Insulation', f'{zone} Ball Mill Equipment Installation',
                   f'{zone} Transformer Energization', f'{zone} Ball Mill Commissioning'],
                  rels=list(rels) + [(3, 5), (4, 5)])


def test_extract_is_multi_level_and_project_agnostic():
    ex = PL.extract(_proc('Unit-1'))
    assert set(ex['levels']) == {'sysphase', 'system', 'discipline', 'phase'}
    # each level has real generalized keys, and NO raw text leaks
    blob = str(ex)
    assert 'Unit-1' not in blob and 'Spool' not in blob and 'Ball Mill' not in blob
    assert any(k.startswith('piping:ERECTION_INSTALL>piping:') for k in ex['levels']['sysphase'])
    # phase-level captures the install→test / phase chain concept
    assert ex['levels']['phase'], 'phase-level (construction-phase) patterns extracted'
    # a large project compresses into a bounded signature (counts, not copies)
    assert all(isinstance(n, int) for n in ex['levels']['sysphase'].values())


def test_same_concept_different_names_generalizes_identically():
    a, b = PL.extract(_proc('Unit-1')), PL.extract(_proc('Building-B'))
    assert a['levels'] == b['levels'] and a['levels']['sysphase']


def test_provenance_and_support_grow_with_projects(tmp_path):
    base = str(tmp_path)
    store = PL.load_store(base)
    for pid in ('P-100', 'P-200', 'P-300'):
        store = PL.learn_from_view(_proc(pid), pid, 'process', store=store)
    PL.save(store, base)
    reloaded = PL.load_store(base)
    assert PL.project_count(reloaded) == 3
    prov = PL.provenance(store=reloaded)
    top = prov['patterns'][0]
    assert top['support'] == 3 and len(top['projects']) == 3
    assert prov['patterns_by_level']['construction-phase sequence'] >= 1


def test_reimporting_same_project_does_not_inflate(tmp_path):
    base = str(tmp_path)
    store = PL.load_store(base)
    store = PL.learn_from_view(_proc('same'), 'P-1', 'process', store=store)
    store = PL.learn_from_view(_proc('same-again'), 'P-1', 'process', store=store)
    assert PL.project_count(store) == 1
    # support for any pattern is still 1 project — never inflated by re-import
    assert PL.provenance(store=store)['patterns'][0]['support'] == 1


def test_annotation_is_supporting_only_and_never_changes_findings(tmp_path):
    base = str(tmp_path)
    store = PL.load_store(base)
    for pid in ('P-1', 'P-2'):
        store = PL.learn_from_view(_proc(pid), pid, 'process', store=store)
    PL.save(store, base)

    bad = mkview(['Process Pipe Erection', 'Process Pipe Insulation', 'Process Pipe Hydrotest'],
                 rels=[(1, 2)])           # DEFECT: insulation before hydrotest
    findings = generate_findings(bad, resolve(bad))
    before = [(f['kind'], f['system'], f['strength']) for f in findings]
    PL.annotate_findings(findings, store=store)
    after = [(f['kind'], f['system'], f['strength']) for f in findings]
    assert before == after, 'annotation must not add, drop, reorder or re-grade findings'
    assert findings
    sup = findings[0]['support']
    assert sup['curated'] is True and sup['learned_projects'] == 2
    assert 'corroborated by 2' in sup['label']


def test_no_imports_still_curated_baseline(tmp_path):
    bad = mkview(['Process Pipe Erection', 'Process Pipe Insulation', 'Process Pipe Hydrotest'],
                 rels=[(1, 2)])
    findings = generate_findings(bad, resolve(bad))
    PL.annotate_findings(findings, base=str(tmp_path))
    assert findings[0]['support']['curated'] is True
    assert findings[0]['support']['learned_projects'] == 0


def test_v1_store_migrates_to_multi_level(tmp_path):
    import json
    p = PL.store_path(str(tmp_path))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:                 # legacy v1 shape
        json.dump({'version': 1, 'projects': {'OLD': {
            'type': 'process', 'systems': ['piping'],
            'transitions': ['piping:ERECTION_INSTALL>piping:TESTING:FS']}}}, f)
    store = PL.load_store(str(tmp_path))
    assert store['version'] == 2
    assert store['projects']['OLD']['levels']['sysphase'] == {'piping:ERECTION_INSTALL>piping:TESTING:FS': 1}


# ── export / import (user-extensible, portable knowledge) ────────────────────

def _seed(base, ids=('P-1', 'P-2', 'P-3')):
    store = PL.load_store(base)
    for pid in ids:
        store = PL.learn_from_view(_proc(pid), pid, 'process', label=f'Project {pid}', store=store)
    PL.save(store, base)
    return store


def test_export_is_multi_level_and_project_agnostic(tmp_path):
    _seed(str(tmp_path))
    bundle = PL.export_knowledge(base=str(tmp_path))
    assert bundle['format'] == 'constructability-knowledge' and bundle['projects_count'] == 3
    blob = str(bundle)
    assert 'Spool' not in blob and 'Ball Mill' not in blob     # no raw activity text
    for rec in bundle['projects'].values():
        for lv, keys in rec['levels'].items():
            for k in keys:
                assert PL._valid_key(lv, k)


def test_import_contributes_and_dedups(tmp_path, tmp_path_factory):
    src = str(tmp_path)
    _seed(src, ids=('A', 'B'))
    bundle = PL.export_knowledge(base=src)
    dst = str(tmp_path_factory.mktemp('dst'))
    _seed(dst, ids=('B', 'C'))                                 # B overlaps → dedup
    res = PL.import_knowledge(bundle, base=dst)
    assert res['imported'] == 1 and res['refreshed'] == 1
    assert PL.project_count(PL.load_store(dst)) == 3
    assert PL.provenance(base=dst)['projects_learned'] == 3


def test_import_drops_raw_or_malformed_patterns(tmp_path):
    bad = {'format': 'constructability-knowledge', 'version': 2, 'projects': {'X': {
        'label': 'X', 'type': 'process', 'systems': ['piping'], 'disciplines': [],
        'levels': {'sysphase': {'Install Pump before Foundation': 3,      # raw → dropped
                                'piping:ERECTION_INSTALL>piping:TESTING:FS': 2},   # valid
                   'system': {}, 'discipline': {}, 'phase': {}}}}}
    res = PL.import_knowledge(bad, base=str(tmp_path))
    store = PL.load_store(str(tmp_path))
    assert store['projects']['X']['levels']['sysphase'] == {'piping:ERECTION_INSTALL>piping:TESTING:FS': 2}
    assert res['dropped_patterns'] == 1


def test_import_rejects_wrong_format(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        PL.import_knowledge({'format': 'something-else'}, base=str(tmp_path))


# ── Level 1: raw project retention (download backup) ─────────────────────────

def test_raw_store_keeps_dedups_and_guards(tmp_path):
    base = str(tmp_path)
    src = tmp_path / 'ProjectAlpha.xml'
    src.write_text('<xml>schedule</xml>', encoding='utf-8')
    p1 = PL.store_raw(str(src), 'P-1', 'Project Alpha', 'hashaaaaaaaa', base=base)
    assert p1 and os.path.exists(p1)
    # same hash → deduped (not stored twice)
    p2 = PL.store_raw(str(src), 'P-1', 'Project Alpha', 'hashaaaaaaaa', base=base)
    assert p2 == p1 and len(PL.list_raw(base)) == 1
    # a different project is kept alongside
    PL.store_raw(str(src), 'P-2', 'Project Beta', 'hashbbbbbbbb', base=base)
    assert len(PL.list_raw(base)) == 2
    # download resolves within the raw dir; path traversal is refused
    fn = PL.list_raw(base)[0]['filename']
    assert PL.raw_file_path(fn, base=base)
    assert PL.raw_file_path('../../secret.txt', base=base) is None


# ── unified Knowledge Base: metadata list + enable toggle + remove ───────────

def test_kb_list_carries_metadata(tmp_path):
    base = str(tmp_path)
    PL.learn_from_view(_proc('P-1'), 'P-1', 'process', label='Alpha', base=base)
    row = PL.kb_list(base=base)[0]
    assert row['name'] == 'Alpha' and row['type'] == 'process'
    assert row['source'] == 'user' and row['enabled'] is True and row['date']
    assert row['patterns'] >= 1


def test_disabled_project_does_not_corroborate_but_stays_listed(tmp_path):
    base = str(tmp_path)
    PL.learn_from_view(_proc('P-1'), 'P-1', 'process', label='A', base=base)
    PL.learn_from_view(_proc('P-2'), 'P-2', 'process', label='B', base=base)
    assert PL.provenance(base=base)['patterns'][0]['support'] == 2
    PL.set_enabled('P-2', False, base=base)
    # still in the list (not deleted) but no longer corroborates
    assert len(PL.kb_list(base=base)) == 2
    assert PL.provenance(base=base)['patterns'][0]['support'] == 1


def test_remove_project(tmp_path):
    base = str(tmp_path)
    PL.learn_from_view(_proc('P-1'), 'P-1', 'process', label='A', base=base)
    PL.remove_project('P-1', base=base)
    assert PL.kb_list(base=base) == []
