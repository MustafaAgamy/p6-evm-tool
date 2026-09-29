"""Read the activity-code catalog (dimension -> [{code, description}]) from a P6
file, capturing BOTH the short code value and its description — richer than the
per-activity map the main parser keeps. Isolated here so ``p6_evm`` stays untouched.

XML is read namespace-aware (mirrors ``p6_evm.parser``). XER is read from its
ACTVTYPE / ACTVCODE tables. On any problem it returns ``{}`` and the builder falls
back to the codes actually assigned to activities.
"""
import os
import re
from xml.etree import ElementTree as ET


def read_code_catalog(path):
    """The catalog depends only on the file, and every Reporting Studio open (and every
    Narrative build) asks for it — each read re-parses the whole file, seconds on a big XML.
    So it is remembered per (path, modified time, size); a changed or re-exported file is
    re-read. Callers always get their own copy."""
    if not path:
        return {}
    key = file_key(path)
    cat = _CATALOG_CACHE.get(key) if key else None
    if cat is None:
        try:
            if path.lower().endswith('.xer'):
                cat = _from_xer(path)
            else:
                cat = _from_xml(path)
        except Exception:
            return {}
        remember(key, cat)
    return {dim: [dict(v) for v in vals] for dim, vals in cat.items()}


_CATALOG_CACHE = {}        # (abs path, mtime_ns, size) -> {dimension: [{code, description}]}
_CATALOG_CACHE_MAX = 4


def file_key(path):
    """(absolute path, modified time, size) — a changed or re-exported file gets a new key."""
    try:
        st = os.stat(path)
        return (os.path.abspath(path), st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def remember(key, cat):
    if key and key not in _CATALOG_CACHE:
        if len(_CATALOG_CACHE) >= _CATALOG_CACHE_MAX:
            _CATALOG_CACHE.pop(next(iter(_CATALOG_CACHE)), None)
        _CATALOG_CACHE[key] = cat


def _xml_ns(path):
    with open(path, encoding='utf-8') as f:
        head = f.read(4000)
    m = re.search(r'xmlns="([^"]+)"', head)
    return f'{{{m.group(1)}}}' if m else ''


def _from_xml(path):
    ns = _xml_ns(path)
    root = ET.parse(path).getroot()
    # The same report also needs the resource types of this file (p6_narrative.resload), which
    # is another whole-file parse — seconds on a big XML. Read them from this tree now, once.
    try:
        from p6_narrative import resload
        resload.prime_from_root(path, root, ns)
    except Exception:
        pass
    return codes_from_root(root, ns)


def codes_from_root(root, ns):
    """The activity-code catalog from an already-parsed P6 XML tree."""
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
