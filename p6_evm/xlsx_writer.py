"""Minimal dependency-free .xlsx writer (inline strings). Enough for a flat
findings table with a bold, frozen header row and an autofilter."""
import zipfile
from xml.sax.saxutils import escape

_CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''

_ROOT_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''

_WB_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''

# cellXfs: index 0 = default, index 1 = bold (fontId 1) for the header row.
_STYLES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf/></cellStyleXfs>
<cellXfs count="2"><xf/><xf fontId="1" applyFont="1"/></cellXfs>
</styleSheet>'''


def _col(idx):
    """0-based column index -> spreadsheet column letter(s)."""
    s = ''
    idx += 1
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(col, row, value, style=None):
    ref = f'{_col(col)}{row}'
    s_attr = f' s="{style}"' if style else ''
    if isinstance(value, bool):
        value = str(value)
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{s_attr}><v>{value}</v></c>'
    return (f'<c r="{ref}"{s_attr} t="inlineStr"><is>'
            f'<t xml:space="preserve">{escape(str(value))}</t></is></c>')


def _workbook(sheet_name):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
            ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets></workbook>')


def _sheet(headers, rows):
    n_cols = max(len(headers), 1)
    last = f'{_col(n_cols - 1)}{len(rows) + 1}'
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           '<sheetViews><sheetView workbookViewId="0">'
           '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
           '</sheetView></sheetViews>',
           '<sheetData>']
    out.append('<row r="1">')
    for c, h in enumerate(headers):
        out.append(_cell(c, 1, h, style=1))
    out.append('</row>')
    for i, row in enumerate(rows, start=2):
        out.append(f'<row r="{i}">')
        for c, v in enumerate(row):
            out.append(_cell(c, i, v))
        out.append('</row>')
    out.append('</sheetData>')
    out.append(f'<autoFilter ref="A1:{last}"/>')
    out.append('</worksheet>')
    return ''.join(out)


def write_xlsx(path, sheet_name, headers, rows):
    """Write a single-sheet .xlsx to `path`.

    headers: list[str]. rows: list of lists of str|int|float.
    Numbers become numeric cells; everything else an XML-escaped inline string.
    """
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', _CONTENT_TYPES)
        z.writestr('_rels/.rels', _ROOT_RELS)
        z.writestr('xl/workbook.xml', _workbook(sheet_name))
        z.writestr('xl/_rels/workbook.xml.rels', _WB_RELS)
        z.writestr('xl/styles.xml', _STYLES)
        z.writestr('xl/worksheets/sheet1.xml', _sheet(headers, rows))
