"""Scope-of-work is discussed per discipline, from the file — not a scaffold."""
import os

from p6_evm.parser import parse_file
from p6_narrative.scope import scope_blocks

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml')


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
