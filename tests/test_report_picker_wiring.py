"""Report Contents picker — UI wiring rules that the pure node tests cannot see.

* The one-document export bar is OPT-IN: Word / HTML / Excel are offered only by features whose
  report is adopted (data-sec / data-part annotated). An unannotated report's CSS charts reach
  Word / Excel as bare text, so every other preview keeps the PDF-only bar.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
MODS = ROOT / 'ui' / 'modules'


def _read(name):
    return (MODS / name).read_text(encoding='utf-8')


def _fn_body(src, name):
    """The source of `export async function <name>(` up to the next top-level function."""
    m = re.search(r'^export (?:async )?function %s\(' % re.escape(name), src, re.M)
    assert m, name
    nxt = re.search(r'^(?:export )?(?:async )?function \w+\(', src[m.end():], re.M)
    return src[m.start():m.end() + (nxt.start() if nxt else len(src))]


# ── F1: the export bar is opt-in ─────────────────────────────────────────────
def test_preview_defaults_to_the_pdf_only_bar():
    src = _read('preview.js')
    assert 'exportKinds(exports)' in src
    # the old default-all filter must be gone
    assert '!Array.isArray(exports) ||' not in src
    parts = _read('report_parts.js')
    assert re.search(r"if \(!Array\.isArray\(exports\)\) return \['pdf'\];", parts)


def test_only_adopted_features_offer_word_html_excel():
    api = _read('api.js')
    assert "const ADOPTED_EXPORTS = ['pdf', 'docx', 'html', 'xlsx'];" in api
    assert api.count('exports: ADOPTED_EXPORTS') == 2
    assert 'exports: ADOPTED_EXPORTS' in _fn_body(api, 'generatePdf')          # Earned Value
    assert 'exports: ADOPTED_EXPORTS' in _fn_body(api, 'generateCalendarPdf')  # P6 Calendar Audit
    for fn in ('generateModulePdf', 'generateWeatherPdf'):
        assert 'exports:' not in _fn_body(api, fn), fn
    # no other preview caller turns the full bar on until it is adopted
    for name in ('compare.js', 'revcompare.js', 'printview.js', 'special.js'):
        src = _read(name)
        assert not re.search(r"exports:\s*\[[^\]]*'(docx|xlsx|html)'", src), name
        assert 'ADOPTED_EXPORTS' not in src, name


# ── F2: drag-to-reorder only where the new order reaches the outputs ─────────
def test_drag_is_gated_on_can_reorder():
    src = _read('preview.js')
    body = src[src.index('function paintTree()'):src.index("if (hasSel) {\n    const all")]
    assert 'const reorder = canReorder(wraps, serverOrder);' in body
    assert 'li.draggable = reorder && !s.empty;' in body
    # the grip is only drawn when a drag is possible, and the drag listeners only bound then
    assert re.search(r"\$\{reorder \? '<span class=\"rpv-grip\"", body)
    assert body.index('if (reorder) {') < body.index("addEventListener('dragstart'")
    # the old unconditional grip/draggable are gone
    assert 'li.draggable = !s.empty;' not in body


def test_refetch_uses_needs_rerender_with_server_order():
    src = _read('preview.js')
    assert 'needsRerender(keys, lastKeys, { wraps, serverOrder: !!serverOrder })' in src


def test_printview_sections_are_picker_managed():
    src = _read('printview.js')
    assert 'data-sec="${_attr(s.key)}"' in src
    # sections are emitted in the SELECTED order (selectedKeys drives the map), not the caller's
    assert '(selectedKeys || []).map((k) => byKey.get(k))' in src


# ── F6: every audit check exports under its own name ─────────────────────────
def test_module_exports_carry_the_check_name_file_name_and_meta():
    body = _fn_body(_read('api.js'), 'generateModulePdf')
    # the feature name is the check's own (Lag, OOS…); only the roll-up is "Schedule Health Review"
    assert re.search(r"module === '__summary__' \? 'Schedule Health Review' : \(mod\.name \|\| module\)", body)
    assert re.search(r'^\s*feature: featureName,', body, re.M)
    # file name back to `${module}_report` (not the shared title slug)
    assert re.search(r"exportName: `\$\{module\.replace\([^`]+\}_report`", body)
    # Word header / Excel header block get the project and a FORMATTED data date
    assert 'project: reqBody.meta.project_name' in body
    assert re.search(r'data_date: reqBody\.meta\.data_date \? fmtDate\(', body)
    # fmtDate imported from format.js (other helpers may share the import line)
    assert re.search(r"^import \{[^}]*\bfmtDate\b[^}]*\}\s+from '\./format\.js';", _read('api.js'), re.M)
