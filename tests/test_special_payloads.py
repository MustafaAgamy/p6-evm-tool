"""Tests for the Special Report payload vocabulary."""
from p6_special import payloads as P


def test_kpi_and_group():
    g = P.kpi_group([P.kpi('Planned %', '61.4%', sub='vs plan', tone='accent')])
    assert g['kind'] == 'kpi_group'
    item = g['items'][0]
    assert item['label'] == 'Planned %'
    assert item['value'] == '61.4%'
    assert item['sub'] == 'vs plan'
    assert item['tone'] == 'accent'


def test_table_shapes_rows_and_aligns():
    t = P.table(['Cat', 'Planned'], [['Construction', '58%']], aligns=['l', 'r'])
    assert t['kind'] == 'table'
    assert t['columns'] == ['Cat', 'Planned']
    assert t['rows'] == [['Construction', '58%']]
    assert t['aligns'] == ['l', 'r']


def test_table_default_aligns_none():
    assert P.table(['A'], [[1]])['aligns'] is None


def test_bars():
    b = P.bars(
        rows=[{'label': 'Overall', 'values': [61.4, 40.4], 'display': ['61.4%', '40.4%']}],
        series=[{'label': 'Planned', 'tone': 'neutral'}, {'label': 'Actual', 'tone': 'accent'}],
    )
    assert b['kind'] == 'bars'
    assert len(b['series']) == 2
    assert b['rows'][0]['values'] == [61.4, 40.4]


def test_segbar():
    s = P.segbar([{'label': 'Completed', 'value': 156, 'tone': 'good'}])
    assert s['kind'] == 'segbar'
    assert s['segments'][0]['value'] == 156


def test_findings_default_empty():
    f = P.findings([])
    assert f['kind'] == 'findings'
    assert f['items'] == []
    assert f['empty']


def test_text_str_becomes_list():
    assert P.text('hello')['paragraphs'] == ['hello']
    assert P.text(['a', 'b'])['paragraphs'] == ['a', 'b']


def test_keyvals():
    kv = P.keyvals([('Data date', '19 Oct 2026')])
    assert kv['pairs'] == [('Data date', '19 Oct 2026')]


def test_group_drops_falsy_blocks():
    g = P.group([P.text('a'), None, P.note('b')])
    assert len(g['blocks']) == 2


def test_no_data_sentinel():
    assert P.NO_DATA['kind'] == 'no_data'
