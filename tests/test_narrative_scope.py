"""Scope-of-work is discussed per discipline, from the file — not a scaffold.

The primary target (Ibrahim, Comment 6) is a BRIEF prose outline, per trade x per
building/area, built from the activity codes with the connective "... consist of:"
then the element list — and identical areas collapsed to "same scope as <first>".
The old per-discipline block prose is kept as the no-codes fallback.
"""
import os

from p6_evm.parser import parse_file
from p6_narrative.scope import scope_blocks, scope_prose

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml')


def _mk(oid, trade, area, elem, start, code_types=('Discipline', 'Building', 'Type of Works')):
    codes = {}
    if trade is not None:
        codes[code_types[0]] = trade
    if area is not None:
        codes[code_types[1]] = area
    if elem is not None:
        codes[code_types[2]] = elem
    return {'task_type': 'Task', 'wbs_id': 'root', 'object_id': oid, 'id': oid,
            'planned_start': start, 'activity_codes': codes}


# ── the new per-trade x per-area prose ────────────────────────────────────────

def test_scope_prose_consists_of_phrasing_and_dedup():
    wbs = {'root': {'name': 'Works', 'parent_object_id': None}}
    code_types = ['Discipline', 'Building', 'Type of Works']
    acts = [
        _mk('a1', 'Civil', 'Silo 1', 'Piles', '2024-01-01'),
        _mk('a2', 'Civil', 'Silo 1', 'Coring', '2024-02-01'),
        # Silo 2 has the SAME element set as Silo 1 -> must collapse
        _mk('a3', 'Civil', 'Silo 2', 'Piles', '2024-03-01'),
        _mk('a4', 'Civil', 'Silo 2', 'Coring', '2024-04-01'),
        # Delivery Bins is a different element set -> described on its own
        _mk('a5', 'Civil', 'Delivery Bins', 'Piles', '2024-05-01'),
        _mk('a6', 'Civil', 'Delivery Bins', 'Columns', '2024-06-01'),
    ]
    payload = scope_prose(acts, wbs, code_types=code_types)
    assert payload and payload.get('trades')
    civil = payload['trades'][0]
    assert civil['trade'] == 'Civil'

    first = civil['areas'][0]
    assert first['sentence'].startswith('Silo 1 Civil works consist of:')
    assert 'Piles' in first['sentence'] and 'Coring' in first['sentence']

    joined = ' '.join(a['sentence'] for a in civil['areas'])
    # the duplicate silo collapses to a "same scope as" one-liner
    assert 'same scope as Silo 1' in joined
    assert 'Silo 2' in joined
    assert 'Silo 2-Silo 2' not in joined      # a single member is not folded into a range
    # the distinct area keeps its own "consist of" sentence
    assert 'Delivery Bins Civil works consist of:' in joined


def test_scope_prose_folds_contiguous_area_run():
    wbs = {'root': {'name': 'Works', 'parent_object_id': None}}
    code_types = ['Discipline', 'Building', 'Type of Works']
    acts = []
    # S1 described, S2..S5 identical -> collapse to a single "S2-S5" line
    for i in range(1, 6):
        acts.append(_mk(f'p{i}', 'Civil', f'S{i}', 'Piles', f'2024-0{i}-01'))
        acts.append(_mk(f'c{i}', 'Civil', f'S{i}', 'Raft', f'2024-0{i}-15'))
    payload = scope_prose(acts, wbs, code_types=code_types)
    joined = ' '.join(a['sentence'] for a in payload['trades'][0]['areas'])
    assert 'S1 Civil works consist of:' in joined
    assert 'S2-S5: same scope as S1' in joined


def test_scope_prose_trade_order_civil_first():
    wbs = {'root': {'name': 'Works', 'parent_object_id': None}}
    code_types = ['Discipline', 'Building', 'Type of Works']
    acts = [
        _mk('s1', 'Steel', 'Tower', 'TR33', '2024-01-01'),
        _mk('m1', 'Mechanical', 'Line 1', 'Conveyor', '2024-01-01'),
        _mk('c1', 'Civil', 'Silo 1', 'Piles', '2024-01-01'),
        _mk('e1', 'Cable', 'Line 1', 'Tray', '2024-01-01'),
    ]
    payload = scope_prose(acts, wbs, code_types=code_types)
    trades = [t['trade'] for t in payload['trades']]
    assert trades[0] == 'Civil'
    assert trades.index('Mechanical') < trades.index('Steel')
    assert trades.index('Steel') < trades.index('Cable')


def test_scope_prose_falls_back_without_codes():
    # minimal.xml carries no activity codes -> None, builder uses the block prose
    data = parse_file(FIX)
    assert scope_prose(list(data.activities.values()), data.wbs,
                       code_types=data.activity_code_types) is None


def test_scope_prose_is_none_safe_on_empty():
    assert scope_prose([], {}, code_types=None) is None


# ── the retained per-discipline block prose (fallback) ────────────────────────

def test_scope_blocks_group_and_describe():
    data = parse_file(FIX)
    blocks = scope_blocks(list(data.activities.values()), data.wbs,
                          code_types=data.activity_code_types,
                          bac_by_activity=data.bac_by_activity)
    assert blocks, 'expected at least one discipline block'
    for b in blocks:
        assert b['discipline']
        assert b['activity_count'] >= 1
        assert b['packages']                      # real work-packages listed
        assert str(b['activity_count']) in b['paragraph']   # paragraph cites real counts
        assert b['packages'][0] in b['paragraph']           # and names a real package


def test_scope_paragraph_caps_long_package_lists():
    # one discipline ('Civil', via the code), 12 distinct WBS work-packages under it
    wbs = {'root': {'name': 'Construction', 'parent_object_id': None}}
    wbs.update({f'w{i}': {'name': f'PKG{i}', 'parent_object_id': 'root'} for i in range(12)})
    acts = [{'task_type': 'Task', 'wbs_id': f'w{i}', 'object_id': f'o{i}',
             'activity_codes': {'Type of Works': 'Civil'}} for i in range(12)]
    blocks = scope_blocks(acts, wbs, code_types=['Type of Works'])
    assert len(blocks) == 1 and blocks[0]['discipline'] == 'Civil'
    assert 'and 4 more' in blocks[0]['paragraph']    # 12 - 8 shown = 4 more
