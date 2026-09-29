"""Guard against duplicate POST routes / duplicate handler methods in server.py.

A second `elif self.path == X` can never be reached, and a second `def _handle_X`
silently replaces the first — both hide dead code and make it unclear which
implementation actually runs (finding F4: /api/special/excel was doubled).
"""
import ast
import os
from collections import Counter

SERVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server.py')


def _tree():
    with open(SERVER, encoding='utf-8') as fh:
        return ast.parse(fh.read())


def _handler_class(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and any(
                isinstance(n, ast.FunctionDef) and n.name == 'do_POST' for n in node.body):
            return node
    raise AssertionError('handler class with do_POST not found')


def _route_literals(func):
    """Every string compared with `self.path == '...'` inside func."""
    out = []
    for node in ast.walk(func):
        if (isinstance(node, ast.Compare) and len(node.ops) == 1
                and isinstance(node.ops[0], ast.Eq)
                and isinstance(node.left, ast.Attribute) and node.left.attr == 'path'
                and isinstance(node.comparators[0], ast.Constant)
                and isinstance(node.comparators[0].value, str)):
            out.append(node.comparators[0].value)
    return out


def test_no_duplicate_post_routes():
    cls = _handler_class(_tree())
    do_post = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'do_POST')
    dups = [p for p, c in Counter(_route_literals(do_post)).items() if c > 1]
    assert not dups, f'POST routes dispatched more than once: {dups}'


def test_no_duplicate_handler_methods():
    cls = _handler_class(_tree())
    names = [n.name for n in cls.body if isinstance(n, ast.FunctionDef)]
    dups = [n for n, c in Counter(names).items() if c > 1]
    assert not dups, f'methods defined more than once (earlier copy is dead): {dups}'


def test_special_excel_uses_assemble_excel():
    """The surviving handler is the one matching the current p6_special API.

    The removed later copy called ``excel_export.build_excel(project_id=..., mode=...,
    letterhead=...)`` — a signature that no longer exists (build_excel takes
    ``path, report_name, meta, rendered``), so every Studio Excel export raised
    TypeError. ``assemble.excel`` resolves the items then calls build_excel correctly.
    """
    cls = _handler_class(_tree())
    fn = next(n for n in cls.body
              if isinstance(n, ast.FunctionDef) and n.name == '_handle_special_excel')
    src = ast.unparse(fn)
    assert 'assemble.excel(' in src
    assert 'build_excel(' not in src


def test_special_excel_route_writes_workbook(tmp_path):
    """Live POST /api/special/excel returns ok and writes a real .xlsx."""
    import json
    import threading
    import urllib.request
    import zipfile
    import server

    srv = server.make_server()
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        out = tmp_path / 'studio.xlsx'
        req = urllib.request.Request(
            f'http://127.0.0.1:{port}/api/special/excel',
            data=json.dumps({'output_path': str(out), 'item_ids': [],
                             'report_name': 'F4 check'}).encode(),
            headers={'Content-Type': 'application/json'})
        res = json.loads(urllib.request.urlopen(req, timeout=60).read())
        assert res == {'ok': True}, res
        assert out.exists() and zipfile.is_zipfile(out)
    finally:
        srv.shutdown()
        srv.server_close()
