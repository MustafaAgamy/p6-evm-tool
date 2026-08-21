"""Cross-project intelligence layer — learns generalized sequencing patterns from
imported schedules, with provenance, as SUPPORTING context only (never creates a
finding). Curated KB is day-1 baseline; user imports grow the intelligence."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(__file__))

from p6_kb import pattern_learning as PL
from p6_kb.findings import generate_findings
from p6_kb.resolve import resolve
from test_kb_findings_r3_r7 import mkview


def _proc_schedule(zone):
    # a small process-piping schedule; `zone` only varies the names, NOT the concept
    return mkview([f'{zone} Process Pipe Spool Erection', f'{zone} Process Pipe Hydrotest',
                   f'{zone} Process Pipe Insulation'],
                  rels=[(0, 1), (1, 2)])


def test_learns_the_concept_not_the_names():
    """Two projects with DIFFERENT activity names but the SAME sequencing concept produce
    the SAME generalized transitions — and no activity name / WBS / id is stored."""
    _sys_a, tx_a = PL.generalized(_proc_schedule('Unit-1'))
    _sys_b, tx_b = PL.generalized(_proc_schedule('Building-B'))
    assert tx_a == tx_b and tx_a, 'same concept must generalize identically'
    blob = ' '.join(tx_a)
    assert 'Unit-1' not in blob and 'Building-B' not in blob and 'Spool' not in blob
    # keys are (system:phase>system:phase:type) concepts
    assert any(k.startswith('piping:ERECTION_INSTALL>piping:') for k in tx_a)


def test_provenance_and_support_grow_with_projects(tmp_path):
    base = str(tmp_path)
    store = PL.load_store(base)
    for pid in ('P-100', 'P-200', 'P-300'):
        store = PL.learn_from_view(_proc_schedule(pid), pid, 'process', store=store)
    PL.save(store, base)
    reloaded = PL.load_store(base)
    assert PL.project_count(reloaded) == 3
    tx_index, _sy = PL._index(reloaded)
    key = next(k for k in tx_index if k.startswith('piping:ERECTION_INSTALL>piping:TESTING'))
    assert len(tx_index[key]) == 3, 'a transition seen in 3 projects has support 3'


def test_reimporting_same_project_does_not_inflate(tmp_path):
    base = str(tmp_path)
    store = PL.load_store(base)
    store = PL.learn_from_view(_proc_schedule('same'), 'P-1', 'process', store=store)
    store = PL.learn_from_view(_proc_schedule('same-again'), 'P-1', 'process', store=store)
    assert PL.project_count(store) == 1, 'dedup by project id — re-import never inflates'


def test_annotation_is_supporting_only_and_never_changes_findings(tmp_path):
    base = str(tmp_path)
    # learn from two projects that show the CORRECT hydrotest→insulation order
    store = PL.load_store(base)
    for pid in ('P-1', 'P-2'):
        good = mkview([f'{pid} Process Pipe Spool Erection', f'{pid} Process Pipe Hydrotest',
                       f'{pid} Process Pipe Insulation'],
                      rels=[(0, 1), (1, 2)])
        store = PL.learn_from_view(good, pid, 'process', store=store)
    PL.save(store, base)

    # a NEW schedule with the DEFECT (insulation before hydrotest)
    bad = mkview(['Process Pipe Erection', 'Process Pipe Insulation', 'Process Pipe Hydrotest'],
                 rels=[(1, 2)])
    findings = generate_findings(bad, resolve(bad))
    before = [(f['kind'], f['system'], f['strength']) for f in findings]

    PL.annotate_findings(findings, store=store)
    after = [(f['kind'], f['system'], f['strength']) for f in findings]
    assert before == after, 'annotation must not add, drop, reorder or re-grade findings'
    assert findings, 'the defect finding is still raised — from the current XER evidence'
    sup = findings[0]['support']
    assert sup['curated'] is True and sup['learned_projects'] == 2
    assert 'corroborated by 2' in sup['label']


def test_no_imports_still_curated_baseline(tmp_path):
    bad = mkview(['Process Pipe Erection', 'Process Pipe Insulation', 'Process Pipe Hydrotest'],
                 rels=[(1, 2)])
    findings = generate_findings(bad, resolve(bad))
    PL.annotate_findings(findings, base=str(tmp_path))   # empty store
    assert findings[0]['support']['curated'] is True
    assert findings[0]['support']['learned_projects'] == 0
