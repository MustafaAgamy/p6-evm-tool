"""Generate a PBIP project (semantic model + report) pointed at the live dataset.

Format choices (see the vault plan): TMSL model.bim for the semantic model
(single JSON, no extra 'TMDL' preview toggle) + PBIR for the report (documented,
structurally checkable). The Excel workbook's absolute path is baked into each
table's Power Query M partition so opening the .pbip needs no parameter prompt.

Opening it needs two Power BI Desktop preview features enabled once:
  - Power BI Project (.pbip) save option
  - Store reports using enhanced metadata format (PBIR)
"""
import json
import os
import shutil

from p6_powerbi import paths
from p6_powerbi import report_pages
from p6_powerbi.schema import TABLES, MEASURES, RELATIONSHIPS

NAME = 'P6EVM'

PBIP_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json'
PBISM_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json'
PBIR_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json'
REPORT_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/2.0.0/schema.json'
VERSION_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json'
PAGES_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json'


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def _m_expression(workbook_path, table):
    p = workbook_path.replace('"', '""')  # M escapes a double-quote by doubling it
    return (
        'let\n'
        f'    Source = Excel.Workbook(File.Contents("{p}"), null, true),\n'
        f'    Data = Source{{[Item="{table}",Kind="Table"]}}[Data]\n'
        'in\n'
        '    Data'
    )


def _model_bim(workbook_path):
    tables = []
    for tname, cols in TABLES.items():
        table = {
            'name': tname,
            'columns': [
                {'name': c, 'dataType': dt, 'sourceColumn': c, 'summarizeBy': 'none'}
                for c, dt in cols
            ],
            'partitions': [{
                'name': tname,
                'mode': 'import',
                'source': {'type': 'm', 'expression': _m_expression(workbook_path, tname)},
            }],
        }
        if tname in MEASURES:
            table['measures'] = [
                {'name': mn, 'expression': dax, 'formatString': fmt}
                for mn, dax, fmt in MEASURES[tname]
            ]
        tables.append(table)

    relationships = [
        {'name': f'rel_{i}', 'fromTable': ft, 'fromColumn': fc, 'toTable': tt, 'toColumn': tc}
        for i, (ft, fc, tt, tc) in enumerate(RELATIONSHIPS)
    ]

    return {
        'name': NAME,
        'compatibilityLevel': 1550,
        'model': {
            'culture': 'en-US',
            'defaultPowerBIDataSourceVersion': 'powerBI_V3',
            'sourceQueryCulture': 'en-US',
            'tables': tables,
            'relationships': relationships,
            'annotations': [
                {'name': '__PBI_TimeIntelligenceEnabled', 'value': '0'},
                {'name': 'PBI_QueryOrder', 'value': json.dumps(list(TABLES.keys()))},
            ],
        },
    }


def _write_semantic_model(sm_dir, workbook_path):
    _write_json(os.path.join(sm_dir, 'definition.pbism'),
                {'$schema': PBISM_SCHEMA, 'version': '4.0', 'settings': {}})
    _write_json(os.path.join(sm_dir, 'model.bim'), _model_bim(workbook_path))


def _write_report(report_dir):
    _write_json(os.path.join(report_dir, 'definition.pbir'), {
        '$schema': PBIR_SCHEMA,
        'version': '4.0',
        'datasetReference': {'byPath': {'path': f'../{NAME}.SemanticModel'}},
    })
    defn = os.path.join(report_dir, 'definition')
    _write_json(os.path.join(defn, 'version.json'), {'$schema': VERSION_SCHEMA, 'version': '2.0.0'})
    _write_json(os.path.join(defn, 'report.json'), {
        '$schema': REPORT_SCHEMA,
        'themeCollection': {'baseTheme': {
            'name': 'CY24SU06', 'reportVersionAtImport': '5.55', 'type': 'SharedResources'}},
    })

    pages = report_pages.build_pages()
    _write_json(os.path.join(defn, 'pages', 'pages.json'), {
        '$schema': PAGES_SCHEMA,
        'pageOrder': [p['name'] for p in pages],
        'activePageName': pages[0]['name'],
    })
    for page in pages:
        pdir = os.path.join(defn, 'pages', page['name'])
        _write_json(os.path.join(pdir, 'page.json'), {
            '$schema': report_pages.PAGE_SCHEMA,
            'name': page['name'],
            'displayName': page['displayName'],
            'displayOption': 'FitToPage',
            'height': 720,
            'width': 1280,
        })
        for visual in page['visuals']:
            _write_json(os.path.join(pdir, 'visuals', visual['name'], 'visual.json'), visual)


def generate_pbip(workbook_path=None, out_dir=None):
    """Write the PBIP project. Returns the path to the .pbip file."""
    workbook_path = os.path.abspath(workbook_path or paths.dataset_workbook())
    out_dir = out_dir or paths.dashboard_dir()
    os.makedirs(out_dir, exist_ok=True)

    sm_dir = os.path.join(out_dir, f'{NAME}.SemanticModel')
    report_dir = os.path.join(out_dir, f'{NAME}.Report')
    for d in (sm_dir, report_dir):
        if os.path.isdir(d):
            shutil.rmtree(d)

    _write_semantic_model(sm_dir, workbook_path)
    _write_report(report_dir)

    pbip_path = os.path.join(out_dir, f'{NAME}.pbip')
    _write_json(pbip_path, {
        '$schema': PBIP_SCHEMA,
        'version': '1.0',
        'artifacts': [{'report': {'path': f'{NAME}.Report'}}],
        'settings': {'enableAutoRecovery': True},
    })
    return pbip_path
