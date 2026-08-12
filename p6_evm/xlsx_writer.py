"""Minimal dependency-free .xlsx writer (inline strings).

Two entry points:
  * write_xlsx(path, sheet, headers, rows) — a flat table with a bold, frozen
    header row and an autofilter (findings/stats exports).
  * write_calendar_xlsx(path, months, cal_name, subtitle) — the Calendar Audit:
    a coloured month-by-month timeline grid (matching the PDF) on one sheet, and
    the Monthly Statistics table on a second sheet.
No third-party deps (openpyxl) — keeps the PyInstaller bundle small.
"""
import zipfile
from xml.sax.saxutils import escape

_ROOT_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''

# Flat-table styles: index 0 = default, index 1 = bold (header row).
_STYLES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf/></cellStyleXfs>
<cellXfs count="2"><xf/><xf fontId="1" applyFont="1"/></cellXfs>
</styleSheet>'''

# Calendar styles — fills tinted to match the PDF timeline legend.
#   fills: 0 none · 1 gray125(reserved) · 2 work · 3 weekend · 4 holiday · 5 shutdown · 6 special · 7 header
#   xfs:   0 default · 1 bold · 2 header(white on blue) · 3 work · 4 weekend · 5 holiday
#          6 shutdown · 7 special · 8 day-of-week header · 9 title
_CAL_STYLES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="4">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><b/><sz val="14"/><name val="Calibri"/></font>
</fonts>
<fills count="8">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFDCFCE7"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF1F5F9"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFEE2E2"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFEF3C7"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFDBEAFE"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF26517D"/></patternFill></fill>
</fills>
<borders count="2">
<border/>
<border><left style="thin"><color rgb="FFD0D7DE"/></left><right style="thin"><color rgb="FFD0D7DE"/></right><top style="thin"><color rgb="FFD0D7DE"/></top><bottom style="thin"><color rgb="FFD0D7DE"/></bottom></border>
</borders>
<cellStyleXfs count="1"><xf/></cellStyleXfs>
<cellXfs count="10">
<xf/>
<xf fontId="1" applyFont="1"/>
<xf fontId="2" fillId="7" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf fontId="0" fillId="2" borderId="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf fontId="0" fillId="3" borderId="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf fontId="0" fillId="4" borderId="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf fontId="0" fillId="5" borderId="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf fontId="0" fillId="6" borderId="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf fontId="1" applyFont="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf fontId="3" applyFont="1"/>
</cellXfs>
</styleSheet>'''

_STATUS_STYLE = {'work': 3, 'weekend': 4, 'holiday': 5, 'shutdown': 6, 'special': 7}
_LEGEND = [('Working', 3), ('Weekend', 4), ('Holiday', 5), ('Shutdown', 6), ('Special hours', 7)]
_DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


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


def _sheet(headers, rows):
    """A flat table sheet: bold frozen header row + autofilter."""
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


def _cells_sheet(cells, col_widths=None):
    """A free-placed sheet from {(row, col): (value, style)} — for the grid."""
    cols_xml = ''
    if col_widths:
        cols_xml = ('<cols>' + ''.join(
            f'<col min="{c + 1}" max="{c + 1}" width="{w}" customWidth="1"/>'
            for c, w in sorted(col_widths.items())) + '</cols>')
    by_row = {}
    for (r, c), (v, s) in cells.items():
        by_row.setdefault(r, {})[c] = (v, s)
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           cols_xml, '<sheetData>']
    for r in sorted(by_row):
        out.append(f'<row r="{r}">')
        for c in sorted(by_row[r]):
            v, s = by_row[r][c]
            out.append(_cell(c, r, v, style=s))
        out.append('</row>')
    out.append('</sheetData></worksheet>')
    return ''.join(out)


def _write_book(path, sheets, styles_xml):
    """Write a workbook of one or more (name, sheet_xml) sheets sharing styles_xml."""
    n = len(sheets)
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    for i in range(1, n + 1):
        ct.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    ct.append('</Types>')

    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i in range(1, n + 1):
        rels.append(f'<Relationship Id="rId{i}" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                    f'Target="worksheets/sheet{i}.xml"/>')
    rels.append(f'<Relationship Id="rId{n + 1}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
                'Target="styles.xml"/>')
    rels.append('</Relationships>')

    sheets_xml = ''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
                         for i, (name, _) in enumerate(sheets, 1))
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
                ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f'<sheets>{sheets_xml}</sheets></workbook>')

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ''.join(ct))
        z.writestr('_rels/.rels', _ROOT_RELS)
        z.writestr('xl/workbook.xml', workbook)
        z.writestr('xl/_rels/workbook.xml.rels', ''.join(rels))
        z.writestr('xl/styles.xml', styles_xml)
        for i, (_name, sheet_xml) in enumerate(sheets, 1):
            z.writestr(f'xl/worksheets/sheet{i}.xml', sheet_xml)


def write_xlsx(path, sheet_name, headers, rows):
    """Write a single-sheet flat table to `path`.

    headers: list[str]. rows: list of lists of str|int|float.
    Numbers become numeric cells; everything else an XML-escaped inline string.
    """
    _write_book(path, [(sheet_name, _sheet(headers, rows))], _STYLES)


def write_calendar_xlsx(path, months, cal_name, subtitle=''):
    """Write the Calendar Audit workbook: a coloured month-by-month timeline grid
    (sheet 1, matching the PDF) + the Monthly Statistics table (sheet 2)."""
    cells = {(1, 0): (f'Calendar Timeline — {cal_name}', 9)}
    if subtitle:
        cells[(2, 0)] = (subtitle, 0)
    for i, (lab, st) in enumerate(_LEGEND):
        cells[(4, i)] = (lab, st)

    r = 6
    for m in months:
        cells[(r, 0)] = (f'{m.get("label", "")} — {m.get("working_days", 0)} working days', 1)
        r += 1
        for c, d in enumerate(_DOW):
            cells[(r, c)] = (d, 8)
        r += 1
        pad = ((m.get('first_weekday', 0) % 7) + 7) % 7
        idx = pad
        for day in m.get('days', []):
            cells[(r + idx // 7, idx % 7)] = (day['d'], _STATUS_STYLE.get(day['status'], 3))
            idx += 1
        weeks = max(1, (idx + 6) // 7)
        r += weeks + 1        # blank row between months

    timeline_xml = _cells_sheet(cells, col_widths={c: 9 for c in range(7)})

    headers = ['Month', 'Working Days', 'Holidays', 'Exceptions', 'Working Hours']
    rows = [[m['label'], m['working_days'], m['holidays'], m['exceptions'], m['working_hours']]
            for m in months]
    _write_book(path, [('Timeline', timeline_xml), ('Monthly Stats', _sheet(headers, rows))],
                _CAL_STYLES)
