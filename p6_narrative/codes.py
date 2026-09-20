"""Read the activity-code catalog (dimension -> [{code, description}]) from a P6
file, capturing BOTH the short code value and its description — richer than the
per-activity map the main parser keeps. Isolated here so ``p6_evm`` stays untouched.

XML is read namespace-aware (mirrors ``p6_evm.parser``). XER is read from its
ACTVTYPE / ACTVCODE tables. On any problem it returns ``{}`` and the builder falls
back to the codes actually assigned to activities.
"""
import re
from xml.etree import ElementTree as ET


def read_code_catalog(path):
    try:
        if path.lower().endswith('.xer'):
            return _from_xer(path)
        return _from_xml(path)
    except Exception:
        return {}


def _from_xml(path):
    with open(path, encoding='utf-8') as f:
        head = f.read(4000)
    m = re.search(r'xmlns="([^"]+)"', head)
    ns = f'{{{m.group(1)}}}' if m else ''
    root = ET.parse(path).getroot()

    def text(el, name):
        c = el.find(f'{ns}{name}')
        return c.text if c is not None else None

    type_name = {}
    for t in root.iter(f'{ns}ActivityCodeType'):
        oid, name = text(t, 'ObjectId'), text(t, 'Name')
        if oid and name:
            type_name[oid] = name

    catalog = {}
    for v in root.iter(f'{ns}ActivityCode'):
        tid = text(v, 'CodeTypeObjectId') or text(v, 'TypeObjectId')
        dim = type_name.get(tid)
        if not dim:
            continue
        code = text(v, 'CodeValue')
        desc = text(v, 'Description')
        catalog.setdefault(dim, []).append(
            {'code': code or desc or '', 'description': desc or code or ''})
    return catalog


def _from_xer(path):
    catalog, type_name = {}, {}
    with open(path, encoding='utf-8', errors='replace') as f:
        cols, table = [], None
        for line in f:
            parts = line.rstrip('\n').split('\t')
            tag = parts[0]
            if tag == '%T':
                table = parts[1]
                cols = []
            elif tag == '%F':
                cols = parts[1:]
            elif tag == '%R':
                row = dict(zip(cols, parts[1:]))
                if table == 'ACTVTYPE':
                    if row.get('actv_code_type_id') and row.get('actv_code_type'):
                        type_name[row['actv_code_type_id']] = row['actv_code_type']
                elif table == 'ACTVCODE':
                    dim = type_name.get(row.get('actv_code_type_id'))
                    if dim:
                        code = row.get('short_name') or ''
                        desc = row.get('actv_code_name') or ''
                        catalog.setdefault(dim, []).append(
                            {'code': code or desc, 'description': desc or code})
    return catalog
