"""Unit tests for p6_special.dash_payload.map_tile — the locked tile contract."""
from p6_special import dash_payload
from p6_special import payloads as P


def _item(payload, **over):
    base = {
        'id': 'evm:planned_pct',
        'title': 'Planned %',
        'feature': 'evm',
        'feature_title': 'EVM',
        'ctype': 'kpi',
        'payload': payload,
    }
    base.update(over)
    return base


def test_kpi_group_mapping():
    payload = P.kpi_group([P.kpi('SPI', '0.87', tone='bad')])
    tile = dash_payload.map_tile(_item(payload))
    assert tile['id'] == 'evm:planned_pct'
    assert tile['title'] == 'Planned %'
    assert tile['source'] == 'EVM'
    assert tile['ctype'] == 'kpi'
    assert tile['kind'] == 'kpis'
    assert tile['shape'] == {'w': 1, 'h': 0}
    assert tile['data']['items'] == payload['items']
    assert tile['data']['items'][0]['label'] == 'SPI'
    assert tile['data']['items'][0]['tone'] == 'bad'


def test_table_mapping_narrow():
    payload = P.table(['A', 'B'], [[1, 2]])
    tile = dash_payload.map_tile(_item(payload))
    assert tile['kind'] == 'table'
    assert tile['shape'] == {'w': 1, 'h': 1}
    assert tile['data']['columns'] == ['A', 'B']
    assert tile['data']['rows'] == [[1, 2]]
    assert tile['data']['aligns'] is None


def test_table_mapping_wide_when_many_columns():
    payload = P.table(['A', 'B', 'C', 'D', 'E'], [[1, 2, 3, 4, 5]])
    tile = dash_payload.map_tile(_item(payload))
    assert tile['kind'] == 'table'
    assert tile['shape'] == {'w': 2, 'h': 1}


def test_bars_mapping():
    payload = P.bars(
        [{'label': 'Cons', 'values': [45], 'display': ['45%']}],
        [{'label': 'Actual', 'tone': 'accent'}],
    )
    tile = dash_payload.map_tile(_item(payload))
    assert tile['kind'] == 'bars'
    assert tile['shape'] == {'w': 1, 'h': 1}
    assert tile['data']['series'] == payload['series']
    assert tile['data']['rows'] == payload['rows']
    assert tile['data']['note'] == payload['note']
    assert tile['data']['axis_max'] == payload['axis_max']


def test_segbar_mapping():
    payload = P.segbar([{'label': 'Done', 'value': 40, 'tone': 'good'},
                        {'label': 'Remaining', 'value': 60, 'tone': 'neutral'}],
                       note='as of data date')
    tile = dash_payload.map_tile(_item(payload))
    assert tile['kind'] == 'segbar'
    assert tile['shape'] == {'w': 1, 'h': 0}
    assert tile['data']['segments'] == payload['segments']
    assert tile['data']['note'] == 'as of data date'


def test_findings_mapping():
    payload = P.findings([{'severity': 'high', 'title': 'Dangling activity', 'detail': 'A123'}])
    tile = dash_payload.map_tile(_item(payload))
    assert tile['kind'] == 'findings'
    assert tile['shape'] == {'w': 1, 'h': 1}
    assert tile['data']['items'] == payload['items']
    assert tile['data']['empty'] == 'No findings.'


def test_findings_mapping_custom_empty():
    payload = P.findings([], empty='All clear.')
    tile = dash_payload.map_tile(_item(payload))
    assert tile['data']['items'] == []
    assert tile['data']['empty'] == 'All clear.'


def test_keyvals_mapping():
    payload = P.keyvals([('a', 'b'), ('c', 'd')])
    tile = dash_payload.map_tile(_item(payload))
    assert tile['kind'] == 'keyvals'
    assert tile['shape'] == {'w': 1, 'h': 0}
    assert tile['data']['pairs'] == payload['pairs']


def test_text_mapping():
    payload = P.text('hi')
    tile = dash_payload.map_tile(_item(payload))
    assert tile['kind'] == 'text'
    assert tile['shape'] == {'w': 1, 'h': 1}
    assert tile['data']['paragraphs'] == ['hi']


def test_note_mapping():
    payload = P.note('n')
    tile = dash_payload.map_tile(_item(payload))
    assert tile['kind'] == 'note'
    assert tile['shape'] == {'w': 1, 'h': 0}
    assert tile['data']['message'] == 'n'
    assert tile['data']['tone'] == 'info'


def test_group_mapping_recurses_and_maps_blocks():
    payload = P.group([P.table(['A'], [[1]]), P.note('x')])
    tile = dash_payload.map_tile(_item(payload))
    assert tile['kind'] == 'group'
    assert tile['shape'] == {'w': 2, 'h': 1}
    blocks = tile['data']['blocks']
    assert len(blocks) == 2
    assert blocks[0]['kind'] == 'table'
    assert blocks[0]['data']['columns'] == ['A']
    assert blocks[1]['kind'] == 'note'
    assert blocks[1]['data']['message'] == 'x'


def test_no_data_sentinel_mapping():
    tile = dash_payload.map_tile(_item(P.NO_DATA))
    assert tile['kind'] == 'no_data'
    assert tile['shape'] == {'w': 1, 'h': 1}
    assert tile['data'] == {}


def test_unknown_kind_maps_to_no_data():
    tile = dash_payload.map_tile(_item({'kind': 'something_new', 'stuff': 1}))
    assert tile['kind'] == 'no_data'
    assert tile['shape'] == {'w': 1, 'h': 1}
    assert tile['data'] == {}


def test_missing_kind_maps_to_no_data():
    tile = dash_payload.map_tile(_item({'no_kind_key': True}))
    assert tile['kind'] == 'no_data'


def test_empty_item_does_not_raise():
    tile = dash_payload.map_tile({})
    assert tile['kind'] == 'no_data'
    assert tile['data'] == {}
    assert tile['id'] is None
    assert tile['title'] is None
    assert tile['source'] is None
    assert tile['ctype'] is None


def test_none_item_does_not_raise():
    tile = dash_payload.map_tile(None)
    assert tile['kind'] == 'no_data'
