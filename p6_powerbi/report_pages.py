"""PBIR report page + visual builders.

Each visual is a dict later written as its own visual.json (PBIR visualContainer
2.0.0 shape): name, position, and visual.query.queryState.<role>.projections
binding to model columns/measures.

Field spec used throughout: a tuple
  ('col',     table, column_name)   -> a Column reference
  ('measure', table, measure_name)  -> a Measure reference
"""

VISUAL_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.0.0/schema.json'
PAGE_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json'


def _field(spec):
    kind, table, prop = spec
    ref = {'Expression': {'SourceRef': {'Entity': table}}, 'Property': prop}
    if kind == 'measure':
        return {'field': {'Measure': ref}, 'queryRef': f'{table}.{prop}', 'nativeQueryRef': prop}
    return {'field': {'Column': ref}, 'queryRef': f'{table}.{prop}', 'nativeQueryRef': prop}


def _visual(name, visual_type, x, y, w, h, roles, z=0):
    """roles: {role_name: [field_spec, ...]} in draw order."""
    query_state = {}
    for role, specs in roles.items():
        query_state[role] = {'projections': [_field(s) for s in specs]}
    return {
        '$schema': VISUAL_SCHEMA,
        'name': name,
        'position': {'x': x, 'y': y, 'z': z, 'width': w, 'height': h, 'tabOrder': z},
        'visual': {
            'visualType': visual_type,
            'query': {'queryState': query_state},
            'drillFilterOtherVisuals': True,
        },
    }


def _slicer(name, x, y, w, h, spec):
    return _visual(name, 'slicer', x, y, w, h, {'Values': [spec]})


def _card(name, x, y, w, h, measure_spec):
    return _visual(name, 'card', x, y, w, h, {'Values': [measure_spec]})


def _line(name, x, y, w, h, category_spec, value_specs):
    return _visual(name, 'lineChart', x, y, w, h,
                   {'Category': [category_spec], 'Y': list(value_specs)})


def _bar(name, x, y, w, h, category_spec, value_specs):
    return _visual(name, 'clusteredBarChart', x, y, w, h,
                   {'Category': [category_spec], 'Y': list(value_specs)})


def _table(name, x, y, w, h, column_specs):
    return _visual(name, 'tableEx', x, y, w, h, {'Values': list(column_specs)})


def evm_page():
    """One project's latest-period EVM: slicers, KPI cards, category table + bar."""
    M = 'fact_metrics'
    C = 'fact_category'
    visuals = [
        _slicer('evm_slicer_project', 40, 36, 260, 90, ('col', 'dim_project', 'project_name')),
        _slicer('evm_slicer_date', 320, 36, 260, 90, ('col', M, 'data_date')),

        _card('evm_card_spi', 40, 150, 200, 110, ('measure', M, 'SPI')),
        _card('evm_card_cpi', 256, 150, 200, 110, ('measure', M, 'CPI')),
        _card('evm_card_delay', 472, 150, 200, 110, ('measure', M, 'Delay (wd)')),
        _card('evm_card_complete', 688, 150, 200, 110, ('measure', M, 'Complete %')),
        _card('evm_card_planned', 904, 150, 200, 110, ('measure', M, 'Planned %')),

        _table('evm_table_category', 40, 286, 560, 400, [
            ('col', C, 'category'),
            ('measure', C, 'Planned'),
            ('measure', C, 'Actual'),
        ]),
        _bar('evm_bar_category', 616, 286, 624, 400,
             ('col', C, 'category'),
             [('measure', C, 'Actual'), ('measure', C, 'Planned')]),
    ]
    return {'name': 'page_evm', 'displayName': 'EVM', 'visuals': visuals}


def trends_page():
    """SPI / CPI / delay / complete over time (every stored update)."""
    M = 'fact_metrics'
    date = ('col', M, 'data_date')
    visuals = [
        _slicer('tr_slicer_project', 40, 36, 260, 90, ('col', 'dim_project', 'project_name')),

        _line('tr_line_spi', 40, 150, 590, 250, date, [('measure', M, 'SPI')]),
        _line('tr_line_delay', 650, 150, 590, 250, date, [('measure', M, 'Delay (wd)')]),
        _line('tr_line_cpi', 40, 420, 590, 260, date, [('measure', M, 'CPI')]),
        _line('tr_line_progress', 650, 420, 590, 260, date,
              [('measure', M, 'Complete %'), ('measure', M, 'Planned %')]),
    ]
    return {'name': 'page_trends', 'displayName': 'Trends', 'visuals': visuals}


def build_pages():
    """Ordered list of pages for the Slice-1 report."""
    return [evm_page(), trends_page()]
