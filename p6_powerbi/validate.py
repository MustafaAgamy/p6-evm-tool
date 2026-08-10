"""Structural validation of a generated PBIP — the best headless check available
(no Power BI in the build environment). Catches the errors most likely to stop
Power BI opening the project: missing required files, malformed JSON, and visual
field references that point at tables/columns/measures the model doesn't have.

Returns a list of human-readable error strings ([] == structurally clean).
"""
import json
import os

from p6_powerbi.pbip import NAME
from p6_powerbi.schema import TABLES, all_field_names


def _load(path, errors):
    if not os.path.isfile(path):
        errors.append(f'missing file: {os.path.basename(path)} ({path})')
        return None
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        errors.append(f'invalid JSON in {os.path.basename(path)}: {e}')
        return None


def _check_field_refs(visual, table_fields, errors):
    where = visual.get('name', '<unnamed>')
    query_state = (visual.get('visual') or {}).get('query', {}).get('queryState', {})
    for role, body in query_state.items():
        for proj in body.get('projections', []):
            field = proj.get('field', {})
            ref = field.get('Measure') or field.get('Column') or {}
            entity = ref.get('Expression', {}).get('SourceRef', {}).get('Entity')
            prop = ref.get('Property')
            if entity not in table_fields:
                errors.append(f'{where}: unknown table "{entity}"')
            elif prop not in table_fields[entity]:
                errors.append(f'{where}: "{entity}" has no field "{prop}"')


def validate_pbip(pbip_path):
    errors = []
    base = os.path.dirname(pbip_path)

    pbip = _load(pbip_path, errors)
    if pbip is not None and not pbip.get('artifacts'):
        errors.append('.pbip has no artifacts')

    sm_dir = os.path.join(base, f'{NAME}.SemanticModel')
    _load(os.path.join(sm_dir, 'definition.pbism'), errors)
    model = _load(os.path.join(sm_dir, 'model.bim'), errors)
    if model is not None:
        tables = {t['name']: t for t in model.get('model', {}).get('tables', [])}
        for expected in TABLES:
            if expected not in tables:
                errors.append(f'model.bim missing table "{expected}"')
                continue
            parts = tables[expected].get('partitions', [])
            expr = parts[0].get('source', {}).get('expression', '') if parts else ''
            if '.xlsx' not in expr:
                errors.append(f'table "{expected}" partition does not reference the workbook')

    report_dir = os.path.join(base, f'{NAME}.Report')
    pbir = _load(os.path.join(report_dir, 'definition.pbir'), errors)
    if pbir is not None and 'datasetReference' not in pbir:
        errors.append('definition.pbir has no datasetReference')

    defn = os.path.join(report_dir, 'definition')
    _load(os.path.join(defn, 'report.json'), errors)
    _load(os.path.join(defn, 'version.json'), errors)
    pages_meta = _load(os.path.join(defn, 'pages', 'pages.json'), errors)

    table_fields = {t: all_field_names(t) for t in TABLES}
    page_names = (pages_meta or {}).get('pageOrder', [])
    if not page_names:
        errors.append('pages.json lists no pages')
    for pname in page_names:
        pdir = os.path.join(defn, 'pages', pname)
        _load(os.path.join(pdir, 'page.json'), errors)
        vis_root = os.path.join(pdir, 'visuals')
        if not os.path.isdir(vis_root):
            errors.append(f'page "{pname}" has no visuals folder')
            continue
        for vname in sorted(os.listdir(vis_root)):
            visual = _load(os.path.join(vis_root, vname, 'visual.json'), errors)
            if visual is None:
                continue
            if not (visual.get('visual') or {}).get('visualType'):
                errors.append(f'visual "{vname}" has no visualType')
            if 'position' not in visual:
                errors.append(f'visual "{vname}" has no position')
            _check_field_refs(visual, table_fields, errors)

    return errors
