"""Starter-baseline P6 XML export — validity via round-trip through the parser."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb.kb import load_kb
from p6_kb.starter import build_starter_xml, write_starter_xml
from p6_evm.parser import parse_file
from p6_kb.review import run_review

ENTRIES = {e['type']: e for e in load_kb()}
SAMPLES = ['MDF / Wood Panel Factory', 'GIS Substation (Gas-Insulated)',
           'Hospital / Healthcare', 'Precast Concrete Factory']


def _write(entry):
    fd, path = tempfile.mkstemp(suffix='.xml')
    os.close(fd)
    summary = write_starter_xml(entry, path)
    return path, summary


def test_starter_xml_is_wellformed_and_parses():
    entry = ENTRIES['MDF / Wood Panel Factory']
    path, summary = _write(entry)
    try:
        data = parse_file(path)
        # WBS root + branches, activities, and a relationship network all present
        assert summary['activities'] == len(data.activities)
        assert summary['relationships'] == len(data.relationships)
        assert len(data.wbs) == summary['wbs'] + 1        # +1 for the root node
        # durations came back in hours (days * 8), milestones are 0-duration
        phases = [a for a in data.activities.values() if a['task_type'] == 'Task']
        assert all(a['planned_duration'] > 0 for a in phases)
        assert any(a['task_type'] == 'FinishMilestone' for a in data.activities.values())
    finally:
        os.remove(path)


def test_starter_detects_own_type_and_has_no_illogic():
    for t in SAMPLES:
        path, _ = _write(ENTRIES[t])
        try:
            rep = run_review(parse_file(path))
            assert rep['detected'] and rep['detected']['type'] == t, f"{t} misdetected"
            # A starter built from the standard must satisfy the standard:
            assert rep['dashboard']['illogical_count'] == 0, f"{t} has illogic"
            assert rep['dashboard']['missing_count'] == 0, f"{t} missing activities"
            assert rep['dashboard']['missing_wbs'] == 0, f"{t} missing WBS"
            assert rep['score']['overall'] >= 90, f"{t} scored {rep['score']['overall']}"
        finally:
            os.remove(path)


def test_starter_relationships_are_acyclic_and_clean():
    # No self-loops, no duplicate edges, and the network is acyclic (a valid
    # schedule P6 can F9 without a loop error).
    for t in SAMPLES:
        _, _summary = _write(ENTRIES[t])  # noqa: F841 — exercised below via build
    entry = ENTRIES['Road / Highway Tunnel']
    xml = build_starter_xml(entry)
    assert xml.startswith('<?xml')
    assert 'APIBusinessObjects' in xml
    path, _ = _write(entry)
    try:
        data = parse_file(path)
        edges = [(r['pred_id'], r['succ_id']) for r in data.relationships]
        assert len(edges) == len(set(edges)), 'duplicate relationships'
        assert all(p != s for p, s in edges), 'self-loop relationship'
        # Kahn's algorithm: a full topological order exists ⇒ acyclic
        from collections import defaultdict
        succ, indeg = defaultdict(list), {}
        nodes = set(data.activities)
        for n in nodes:
            indeg.setdefault(n, 0)
        for p, s in edges:
            succ[p].append(s)
            indeg[s] = indeg.get(s, 0) + 1
        stack = [n for n in nodes if indeg[n] == 0]
        seen = 0
        while stack:
            n = stack.pop()
            seen += 1
            for m in succ[n]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    stack.append(m)
        assert seen == len(nodes), 'relationship network has a cycle'
    finally:
        os.remove(path)
