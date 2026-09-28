"""Format-agnostic engineering-log reader (p6_evm.elog_smart).

Every workbook here is SYNTHETIC (built with openpyxl inside the test) and reproduces one
difficulty seen in real consultant logs; every expected count is worked out by hand in the
comment next to it, using the owner's counting rules:
  * a drawing counts ONCE (by its Drawing No. when the log has one);
  * once Approved (A/B) at any revision it stays approved;
  * otherwise the LATEST revision decides: awaiting a reply = Under review (and Submitted),
    C / D = Not approved (owner decision ELOG-4, 2026-09-27);
  * % Submitted = (Submitted − Rejected) ÷ Req;  % Approved = Approved ÷ Req.
"""
import csv
from datetime import datetime

import openpyxl
import pytest

from p6_evm import elog_smart as es
from p6_evm.e1_log import read_e1_rows, summarize_e1


# ── helpers ────────────────────────────────────────────────────────────────────────────
def _sheet(proposal, name):
    return next(s for s in proposal['sheets'] if s['sheet'] == name)


def _field_of(sheet, header, nth=0):
    cols = [c for c in sheet['columns'] if c['header'] == header]
    return cols[nth]['field']


def _col_with(sheet, field):
    return next((c for c in sheet['columns'] if c['field'] == field), None)


def _summary(path, layout=None):
    layout = layout or es.inspect_log(str(path))
    return summarize_e1(es.read_rows(str(path), layout))


# ── 1. legend + summary rows above a row-7 header, two "Type" columns, drawing numbers ──
def _sg_style(path):
    """Saint-Gobain-style sheet: rows 1-6 = project banner, a code legend with counts under
    it; the real header is on ROW 7 with two 'Type' columns and a 'TYPE' discipline column;
    revisions are separate rows keyed by Drawings No."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Civil'
    ws.append(['Project Name: TEST PLANT', None, None, None, None, None, None, None, None,
               None, None, 'Approved \n( A )', 'Approved as Noted \n( B )',
               'Revise & Resubmit\n  ( C )', 'Rejected \n( D )', 'Pending\n( W )', 'Total'])
    ws.append(['Project Code: X-1'])
    ws.append(['Employer : Someone'] + [None] * 10 + [0, 3, 3, 0, 2, 8])     # the log's own counts
    ws.append(['Consultant : '] + [None] * 10 + [0, .37, .37, 0, .26, 1])
    ws.append(['Contractor : Someone else'])
    ws.append(['Shop Drawing Log - Civil Works'])
    ws.append(['Ser.', 'Transmittal No.', 'Rev.', 'Area', 'Sent Date', 'Subject', 'Type', None,
               None, 'Title', 'Type', 'Drawings No', 'Received Date', 'Action', 'Delay', 'TYPE'])
    d = datetime

    def row(ser, tr, rev, area, sent, typ1, title, typ2, dwg, recv, act):
        return [ser, tr, rev, area, sent, 'Shop drawing package', typ1, 'Foundation', None,
                title, typ2, dwg, recv, act, 'On Date', 'Civil']
    rows = [
        # D-001: rev0 C, rev1 B                    → approved
        row(1, 'T-0001', 0, 'Plant', d(2025, 1, 5), 'RFT', 'Raft plan', 'SD', 'D-001', d(2025, 1, 9), 'C'),
        row(2, 'T-0001 Rev.01', 1, 'Plant', d(2025, 2, 5), 'RFT', 'Raft plan', 'SD', 'D-001', d(2025, 2, 9), 'B'),
        # D-002: rev0 B, rev1 C (a later re-issue)  → stays approved
        row(3, 'T-0002', 0, 'Plant', d(2025, 1, 6), 'Concrete Dimension', 'Walls', 'SD', 'D-002', d(2025, 1, 9), 'B'),
        row(4, 'T-0002 Rev.01', 1, 'Plant', d(2025, 3, 6), 'Concrete Dimension', 'Walls', 'SD', 'D-002', d(2025, 3, 9), 'C'),
        # D-003: rev0 C only                        → not approved
        row(5, 'T-0003', 0, 'Silo', d(2025, 1, 7), 'RFT', 'Silo wall', 'SD', 'D-003', d(2025, 1, 12), 'C'),
        # D-004: W, no reply yet                    → under review
        row(6, 'T-0004', 0, 'Silo', d(2025, 1, 8), 'RFT', 'Silo slab', 'SD', 'D-004', None, 'W'),
        # D-005: sent, no code, no reply            → under review (submitted with no reply)
        row(7, 'T-0005', 0, 'Silo', d(2025, 1, 9), 'RFT', 'Silo roof', 'SD', 'D-005', None, None),
        # D-006: rev0 B, the title is re-worded at rev1 → still ONE drawing (keyed by number)
        row(8, 'T-0006', 0, 'Silo', d(2025, 1, 10), 'RFT', 'Cone', 'SD', 'D-006', d(2025, 1, 15), 'B'),
        row(9, 'T-0006 Rev.01', 1, 'Silo', d(2025, 2, 10), 'RFT', 'Cone (revised)', 'SD', 'D-006', d(2025, 2, 15), 'B'),
    ]
    for r in rows:
        ws.append(r)
    wb.save(path)


def test_header_on_row_7_below_a_legend_and_summary_counts(tmp_path):
    p = tmp_path / 'shop_log.xlsx'
    _sg_style(p)
    prop = es.inspect_log(str(p))
    sh = _sheet(prop, 'Civil')
    assert sh['kind'] == 'register'
    assert sh['header_rows'] == [7]                   # Excel row numbers (1-based)
    assert sh['data_start'] == 8
    assert sh['row_count'] == 9


def test_code_legend_found_above_the_header(tmp_path):
    p = tmp_path / 'shop_log.xlsx'
    _sg_style(p)
    prop = es.inspect_log(str(p))
    leg = prop['legend']
    assert leg['A']['verdict'] == 'approved' and leg['B']['verdict'] == 'approved'
    assert leg['C']['verdict'] == 'not_approved' and leg['D']['verdict'] == 'not_approved'
    assert leg['W']['verdict'] == 'under_review'
    assert 'noted' in leg['B']['meaning'].lower()


def test_two_type_columns_resolved_by_content(tmp_path):
    p = tmp_path / 'shop_log.xlsx'
    _sg_style(p)
    sh = _sheet(es.inspect_log(str(p)), 'Civil')
    # the 'Type' whose values look like a submittal type (SD) wins; the drawing-group 'Type'
    # (RFT / Concrete Dimension) is not used; 'TYPE' holds the discipline (Civil)
    assert _field_of(sh, 'Type', 0) == 'ignore'
    assert _field_of(sh, 'Type', 1) == 'submittal_type'
    assert _field_of(sh, 'TYPE') == 'trade'
    assert _field_of(sh, 'Drawings No') == 'drawing_no'
    assert _field_of(sh, 'Rev.') == 'revision'
    assert _field_of(sh, 'Action') == 'action_code'
    assert _field_of(sh, 'Sent Date') == 'submitted'
    assert _field_of(sh, 'Received Date') == 'returned'
    assert _field_of(sh, 'Transmittal No.') == 'reference'
    assert _field_of(sh, 'Title') == 'description'
    assert _field_of(sh, 'Area') == 'building'
    for c in sh['columns']:
        assert 0.0 <= c['confidence'] <= 1.0 and c['reason']


def test_sg_style_counts_by_drawing_number(tmp_path):
    p = tmp_path / 'shop_log.xlsx'
    _sg_style(p)
    g = _summary(p)[('Civil', 'SD')]
    # 6 distinct drawings D-001..D-006 (9 rows).
    # approved: D-001 (C→B), D-002 (B→C stays), D-006 (B, B)       = 3
    # not approved: D-003                                          = 1
    # under review: D-004 (W), D-005 (sent, no reply)               = 2
    assert g['req'] == 6
    assert g['submitted_rows'] == 6
    assert g['approved_rows'] == 3
    assert g['not_approved_rows'] == 1
    assert g['under_review_rows'] == 2
    assert g['submitted_pct'] == round(100 * (6 - 1) / 6, 1)     # 83.3
    assert g['approved_pct'] == 50.0


def test_old_reader_misreads_the_sg_style_log(tmp_path):
    # documents WHY the smart reader exists: the old one groups by the wrong 'Type' and
    # keys drawings by title, so D-006's re-worded title counts twice
    p = tmp_path / 'shop_log.xlsx'
    _sg_style(p)
    old = summarize_e1(read_e1_rows(str(p)))
    assert ('Civil', 'SD') not in old


# ── 2. two-row merged header, text dates, word statuses, sections + footers ──────────────
def _om_style(path):
    """MDF-closure-style O&M register: a banner, a TWO-ROW header (merged vertically), a
    'PREVIOUS STATUS' and a 'CURRENT STATUS / RE-SUBMISSION DATE', text dates d-m-yyyy,
    section rows ('Electrical') and footer rows ('Total 3')."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'O&M LOG'
    ws.append(['PROJECT - OPERATION & MAINTENANCE MANUAL LOG'])
    ws.merge_cells('A1:I1')
    ws.append(['SN', 'O&M MANUAL TITLE', 'DISCIPLINE', 'PLANNED DATE', 'ACTUAL DATE OF SUBMISSION',
               'CONSULTANT REPLY DATE', 'PREVIOUS STATUS', 'CURRENT STATUS / RE-SUBMISSION DATE',
               'TRANSMITTAL REFERENCE'])
    ws.append([None, None, None, 'TO SUBMIT O&M', None, None, None, None, None])
    for col in 'ABCEFGHI':
        ws.merge_cells(f'{col}2:{col}3')
    ws.append(['Electrical'])
    ws.merge_cells('A4:I4')
    ws.append([1, 'O & M manual for Transformer', 'Electrical', '27-3-2024', '20-3-2024', '24-6-2024',
               'B', 'Approved (Code B)', 'E-T-01805'])
    ws.append([2, 'O & M manual for MV switchgear', 'Electrical', '27-3-2024', None, None,
               None, 'Approved (Code B)', 'E-T-01804'])       # approved, no submission date
    ws.append([3, 'O & M for ATS', 'Electrical', '30-7-2024', None, None, None, 'U.A', None])
    ws.append(['Total 3\n*Submitted 3\n*Approved 2\n*Waiting 1'])
    ws.merge_cells('A8:I8')
    ws.append(['Mechanical'])
    ws.merge_cells('A9:I9')
    ws.append([1, 'O & M manual for pumps', 'Mechanical', '25-5-2024', '21-5-2024', '9-12-2024',
               'B/C', 'Revise and resubmit', 'E-T-01810'])
    ws.append([2, 'O & M manual for fans', 'Mechanical', '25-6-2024', None, None, None, None, None])
    wb.save(path)


def test_two_row_merged_header_is_joined(tmp_path):
    p = tmp_path / 'closure.xlsx'
    _om_style(p)
    sh = _sheet(es.inspect_log(str(p)), 'O&M LOG')
    assert sh['kind'] == 'register'
    assert sh['header_rows'] == [2, 3]
    assert sh['data_start'] == 4
    planned = _col_with(sh, 'planned')
    assert planned['header'] == 'PLANNED DATE TO SUBMIT O&M'
    assert _field_of(sh, 'ACTUAL DATE OF SUBMISSION') == 'submitted'
    assert _field_of(sh, 'CONSULTANT REPLY DATE') == 'returned'
    assert _field_of(sh, 'CURRENT STATUS / RE-SUBMISSION DATE') == 'action_code'
    assert _field_of(sh, 'PREVIOUS STATUS') == 'ignore'
    assert _field_of(sh, 'DISCIPLINE') == 'trade'
    # no submittal-type column → the type comes from the sheet name
    assert sh['type_source'] == {'kind': 'sheet-name', 'value': 'O&M'}
    assert 'Electrical' in sh['sections'] and 'Mechanical' in sh['sections']


def test_om_style_counts(tmp_path):
    p = tmp_path / 'closure.xlsx'
    _om_style(p)
    s = _summary(p)
    e = s[('Electrical', 'O&M')]
    # 3 manuals; all 3 carry a reply (Approved / U.A) → all submitted (a reply means it was
    # sent); approved = Transformer + MV switchgear = 2; U.A = under approval = 1
    assert (e['req'], e['submitted_rows'], e['approved_rows'], e['under_review_rows']) == (3, 3, 2, 1)
    assert e['approved_pct'] == 66.7 and e['submitted_pct'] == 100.0
    m = s[('Mechanical', 'O&M')]
    # pumps: sent, "Revise and resubmit" → not approved; fans: not sent
    assert (m['req'], m['submitted_rows'], m['approved_rows'], m['not_approved_rows']) == (2, 1, 0, 1)
    assert m['submitted_pct'] == 0.0          # (1 − 1) ÷ 2


def test_reply_without_submission_date_is_reported(tmp_path):
    p = tmp_path / 'closure.xlsx'
    _om_style(p)
    sh = _sheet(es.inspect_log(str(p)), 'O&M LOG')
    assert any('no submission date' in w for w in sh['warnings'])


def test_text_dates_are_parsed_day_first(tmp_path):
    p = tmp_path / 'closure.xlsx'
    _om_style(p)
    rows = es.read_rows(str(p), es.inspect_log(str(p)))
    tr = next(r for r in rows if 'Transformer' in r['description'])
    assert tr['submitted'] == datetime(2024, 3, 20)
    assert tr['returned'] == datetime(2024, 6, 24)
    assert tr['planned'] == datetime(2024, 3, 27)


@pytest.mark.parametrize('text,expected', [
    ('27-3-2024', datetime(2024, 3, 27)),
    ('3/4/24', datetime(2024, 4, 3)),              # day first by default
    ('05-Mar-24', datetime(2024, 3, 5)),
    ('5 March 2024', datetime(2024, 3, 5)),
    ('2024-03-05', datetime(2024, 3, 5)),
    ('Mar 5, 2024', datetime(2024, 3, 5)),
    ('12.8.2024', datetime(2024, 8, 12)),
    ('TBD', None), ('N/A', None), ('31-2-2024', None), ('', None),
])
def test_parse_date(text, expected):
    assert es.parse_date(text) == expected


def test_month_first_column_detected():
    # one value with the second part > 12 proves the column is month-first
    assert es.detect_dayfirst(['3/4/2024', '12/25/2024']) is False
    assert es.detect_dayfirst(['27/3/2024', '3/4/2024']) is True
    assert es.detect_dayfirst(['3/4/2024']) is True


# ── 3. numeric review codes 1–4 + word statuses ────────────────────────────────────────
def test_numeric_codes_1_to_4(tmp_path):
    p = tmp_path / 'codes.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Register'
    ws.append(['Document No', 'Discipline', 'Document Type', 'Rev', 'Date Submitted', 'Review Code'])
    d = datetime(2025, 5, 1)
    for r in [['DOC-001', 'MEP', 'Shop Drawing', 0, d, 1],     # approved
              ['DOC-002', 'MEP', 'Shop Drawing', 0, d, 2],     # approved (as noted)
              ['DOC-003', 'MEP', 'Shop Drawing', 0, d, 3],     # revise & resubmit
              ['DOC-003', 'MEP', 'Shop Drawing', 1, d, 2],     # … then approved → approved
              ['DOC-004', 'MEP', 'Shop Drawing', 0, d, 4],     # rejected
              ['DOC-005', 'MEP', 'Shop Drawing', 0, None, None]]:   # not yet submitted
        ws.append(r)
    wb.save(p)
    sh = _sheet(es.inspect_log(str(p)), 'Register')
    assert _field_of(sh, 'Review Code') == 'action_code'
    assert _field_of(sh, 'Rev') == 'revision'
    g = _summary(p)[('MEP', 'Shop Drawing')]
    # 5 drawings; approved DOC-001, DOC-002, DOC-003 = 3; rejected DOC-004 = 1; 4 submitted
    assert (g['req'], g['submitted_rows'], g['approved_rows'], g['not_approved_rows']) == (5, 4, 3, 1)
    assert g['submitted_pct'] == 60.0 and g['approved_pct'] == 60.0


def test_word_statuses(tmp_path):
    p = tmp_path / 'words.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Submittals'
    ws.append(['Drawing Number', 'Trade', 'Submittal Type', 'Title', 'Sent', 'Consultant Status'])
    d = datetime(2025, 5, 1)
    for r in [['A-1', 'Arch', 'Material', 'Tiles', d, 'Reviewed – no exceptions taken'],  # approved
              ['A-2', 'Arch', 'Material', 'Paint', d, 'Approved (Code B)'],               # approved
              ['A-3', 'Arch', 'Material', 'Doors', d, 'Pending (W)'],                     # under review
              ['A-4', 'Arch', 'Material', 'Glass', d, 'No objection'],                    # approved
              ['A-5', 'Arch', 'Material', 'Stone', d, 'Rejected']]:                       # not approved
        ws.append(r)
    wb.save(p)
    g = _summary(p)[('Arch', 'Material')]
    assert (g['req'], g['approved_rows'], g['under_review_rows'], g['not_approved_rows']) == (5, 3, 1, 1)
    assert g['approved_pct'] == 60.0 and g['submitted_pct'] == 80.0


# ── 4. legend in the file overrides the default rule ───────────────────────────────────
def test_file_legend_overrides_default_meaning_of_c(tmp_path):
    p = tmp_path / 'legend.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Log'
    ws.append(['Review codes:', 'A - Approved', 'B - Approved with comments',
               'C - Approved with comments, resubmit for record', 'R - Rejected'])
    ws.append([])
    ws.append(['Dwg No', 'Discipline', 'Type', 'Date Sent', 'Code'])
    d = datetime(2025, 5, 1)
    for r in [['S-1', 'Steel', 'Shop', d, 'C'],      # legend: C is an approval here
              ['S-2', 'Steel', 'Shop', d, 'R'],      # legend: rejected
              ['S-3', 'Steel', 'Shop', d, 'A']]:
        ws.append(r)
    wb.save(p)
    prop = es.inspect_log(str(p))
    assert prop['legend']['C']['verdict'] == 'approved'
    assert prop['legend']['R']['verdict'] == 'not_approved'
    g = _summary(p, prop)[('Steel', 'Shop')]
    assert (g['approved_rows'], g['not_approved_rows']) == (2, 1)


def test_planner_can_remap_a_code(tmp_path):
    p = tmp_path / 'shop_log.xlsx'
    _sg_style(p)
    prop = es.inspect_log(str(p))
    codes = {c['value']: c for c in prop['codes']}
    assert codes['B']['verdict'] == 'approved' and codes['B']['count'] == 4
    assert codes['C']['verdict'] == 'not_approved'
    # the planner says: in this log, W should be ignored (not counted as anything)
    prop['code_map']['W'] = 'ignore'
    g = _summary(p, prop)[('Civil', 'SD')]
    assert g['under_review_rows'] == 1           # only D-005 (sent, no code) remains


# ── 5. per-discipline sheets + a Summary sheet ────────────────────────────────────────
def test_per_discipline_sheets_and_summary_sheet(tmp_path):
    p = tmp_path / 'multi.xlsx'
    wb = openpyxl.Workbook()
    d = datetime(2025, 6, 1)
    for name, rows in [('Civil', [['C-01', 'SD', 'Base', d, 'A'], ['C-02', 'SD', 'Walls', d, 'C']]),
                       ('Steel', [['S-01', 'SD', 'Frame', d, 'B'], ['S-02', 'SD', 'Roof', None, None]])]:
        ws = wb.active if name == 'Civil' else wb.create_sheet(name)
        ws.title = name
        ws.append(['Drawing No', 'Type', 'Title', 'Sent Date', 'Action'])
        for r in rows:
            ws.append(r)
    sm = wb.create_sheet('Summary')
    sm.append(['Summary for Shop Drawings'])
    sm.append([None, 'Civil', 'Steel', 'TOTAL'])
    sm.append(['OUT', 2, 1, 3])
    sm.append(['IN', 2, 1, 3])
    sm.append(['PENDING', 0, 0, 0])
    sm.append(['Status', 'Approved', 'Not Approved', 'Approved'])
    sm.append([None, 1, 1, 1])
    wb.save(p)
    prop = es.inspect_log(str(p))
    assert _sheet(prop, 'Summary')['kind'] == 'summary'
    assert _sheet(prop, 'Summary')['include'] is False
    civil = _sheet(prop, 'Civil')
    assert civil['trade_source'] == {'kind': 'sheet-name', 'value': 'Civil'}
    s = _summary(p, prop)
    assert (s[('Civil', 'SD')]['req'], s[('Civil', 'SD')]['approved_rows']) == (2, 1)
    assert (s[('Steel', 'SD')]['req'], s[('Steel', 'SD')]['submitted_rows']) == (2, 1)
    assert len(s) == 2                             # nothing counted from the Summary sheet


# ── 6. drawing numbers shared by several sheets of one submission ─────────────────────
def test_same_drawing_number_with_several_sheet_titles_in_one_submission(tmp_path):
    # SSB-ED-001 is issued as 3 sheets in one transmittal (different titles) — 3 drawings;
    # each C at rev0 then B at rev1 → 3 approved
    p = tmp_path / 'sheets.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Steel'
    ws.append(['Transmittal No.', 'Rev.', 'Title', 'Type', 'Drawings No', 'Sent Date', 'Action'])
    for tr, rev, code, sent in [('T-3', 0, 'C', datetime(2025, 5, 16)), ('T-3 Rev.01', 1, 'B', datetime(2025, 6, 1))]:
        for title in ('GA 3D view', 'GA cladding axis 1', 'GA roof cladding'):
            ws.append([tr, rev, title, 'SD', 'SSB-ED-001', sent, code])
    wb.save(p)
    g = _summary(p)[('Steel', 'SD')]
    assert (g['req'], g['approved_rows'], g['not_approved_rows']) == (3, 3, 0)


def test_no_drawing_number_uses_the_transmittal_revision_chain(tmp_path):
    # bar-bending schedules with Drawings No = 'N/A': each transmittal (T-9, T-11) is one
    # document with its own Rev chain, even though both are titled 'BAR LIST'.
    p = tmp_path / 'bbs.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Civil'
    ws.append(['Transmittal No.', 'Rev.', 'Area', 'Title', 'Type', 'Drawings No', 'Sent Date', 'Action'])
    d = datetime(2025, 3, 1)
    for r in [['T-9', 0, 'Plant', 'BAR LIST', 'BBS', 'N/A', d, 'B'],
              ['T-11', 0, 'Plant', 'BAR LIST', 'BBS', 'N/A', d, 'C'],
              ['T-11 Rev.01', 1, 'Plant', 'BAR LIST', 'BBS', 'N/A', d, 'B'],
              ['T-12', 0, 'Plant', 'Bar list for footings', 'BBS', 'N/A', d, 'C'],
              ['T-12 Rev.01', 1, 'Plant', 'Footings reinforcement bar list', 'BBS', 'N/A', d, 'W']]:
        ws.append(r)
    wb.save(p)
    g = _summary(p)[('Civil', 'BBS')]
    # T-9 approved; T-11 C→B approved; T-12 C then W (re-titled) = one document, and its
    # latest revision (W) decides → Under review (owner decision ELOG-4)
    assert (g['req'], g['approved_rows'], g['not_approved_rows'], g['under_review_rows']) == (3, 2, 0, 1)


# ── 7. CSV input ──────────────────────────────────────────────────────────────────────
def test_csv_input(tmp_path):
    p = tmp_path / 'mep_log.csv'
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Dwg No', 'Discipline', 'Type', 'Rev', 'Sent Date', 'Reply Date', 'Status'])
        w.writerow(['M-01', 'Mechanical', 'Shop Drawing', '0', '02/03/2025', '10/03/2025', 'C'])
        w.writerow(['M-01', 'Mechanical', 'Shop Drawing', '1', '15/03/2025', '20/03/2025', 'A'])
        w.writerow(['M-02', 'Mechanical', 'Shop Drawing', '0', '16/03/2025', '', ''])
        w.writerow(['E-01', 'Electrical', 'Shop Drawing', '0', '', '', ''])
    prop = es.inspect_log(str(p))
    assert prop['format'] == 'csv'
    sh = prop['sheets'][0]
    assert sh['kind'] == 'register' and _field_of(sh, 'Status') == 'action_code'
    s = _summary(p, prop)
    m = s[('Mechanical', 'Shop Drawing')]
    # M-01 C→A approved; M-02 sent, no reply → under review
    assert (m['req'], m['approved_rows'], m['under_review_rows'], m['submitted_rows']) == (2, 1, 1, 2)
    e = s[('Electrical', 'Shop Drawing')]
    assert (e['req'], e['submitted_rows']) == (1, 0)
    rows = es.read_rows(str(p), prop)
    assert next(r for r in rows if r['drawing_no'] == 'M-01')['submitted'] == datetime(2025, 3, 2)


# ── 8. ROOTS-style logs: the new engine agrees with the old reader exactly ─────────────
def _roots_style(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'E1 Log'
    ws.append(['ROOTS — E1 LOG'])
    ws.append([])
    ws.append(['No.', 'Descipline', 'Building', 'Description', 'Type of submittal', 'REV',
               'Date Submitted', 'Date Returned', 'Action Code', 'Planned Submission'])
    d = datetime
    rows = [
        [1, 'Civil', 'Main Silos', 'Raft RFT', 'Schematic', 0, d(2025, 1, 5), d(2025, 1, 20), 'C', d(2025, 1, 1)],
        [2, 'Civil', 'Main Silos', 'Raft RFT', 'Schematic', 1, d(2025, 2, 5), d(2025, 2, 20), 'B', d(2025, 1, 1)],
        [3, 'Civil', 'Main Silos', 'Walls', 'Schematic', 0, d(2025, 1, 6), d(2025, 1, 21), 'A', d(2025, 1, 2)],
        [4, 'Civil', 'Towers', 'Slab', 'Detailed', 0, d(2025, 3, 1), None, 'P', d(2025, 2, 1)],
        [5, 'Civil', 'Towers', 'Stair', 'Detailed', 0, None, None, None, d(2026, 9, 1)],
        [6, 'MEP', 'Towers', 'Duct', 'Shop', 0, d(2025, 3, 3), d(2025, 3, 9), 'C', d(2025, 3, 1)],
        [7, 'MEP', 'Delivery Bins', 'Cable', 'Shop', 0, d(2025, 3, 4), d(2025, 3, 11), 'B', d(2025, 3, 1)],
        [8, 'MEP', 'Delivery Bins', 'Cable', 'Shop', 1, d(2025, 5, 4), d(2025, 5, 11), 'C', d(2025, 3, 1)],
        [9, 'Arch', 'Towers', 'Facade', 'IFC', 0, d(2025, 4, 1), d(2025, 4, 8), 'AAN', d(2025, 4, 1)],
    ]
    for r in rows:
        ws.append(r)
    wb.save(path)


def test_roots_style_new_engine_equals_old_reader(tmp_path):
    p = tmp_path / 'roots_e1.xlsx'
    _roots_style(p)
    old = summarize_e1(read_e1_rows(str(p)))
    new = _summary(p)
    assert new == old
    cutoff = datetime(2025, 6, 1)
    assert summarize_e1(es.read_rows(str(p), es.inspect_log(str(p))), cutoff=cutoff) == \
        summarize_e1(read_e1_rows(str(p)), cutoff=cutoff)
    # sanity on the hand count: Civil/Schematic = 2 drawings, both approved
    assert new[('Civil', 'Schematic')]['approved_rows'] == 2


def test_alternative_header_fixtures_old_equals_new(tmp_path):
    # the two formats already covered by tests/test_e1_read_formats.py
    p = tmp_path / 'alt.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['Some title banner'])
    ws.append(['Division', 'Zone', 'Drawing Title', 'Drawing Type', 'Submission Date', 'Target Date', 'Review Status'])
    ws.append(['Civil', 'Silo 1', 'Foundation plan', 'Detailed Design', datetime(2026, 1, 10), datetime(2026, 1, 5), 'A'])
    ws.append(['Civil', 'Silo 1', 'Rebar layout', 'Shop Drawing', datetime(2026, 2, 1), datetime(2026, 1, 20), 'B'])
    ws.append(['MEP', 'Silo 2', 'Duct routing', 'Shop Drawing', None, datetime(2026, 3, 1), 'C'])
    wb.save(p)
    new, old = _summary(p), summarize_e1(read_e1_rows(str(p)))
    assert set(new) == set(old)
    assert new[('Civil', 'Detailed Design')] == old[('Civil', 'Detailed Design')]
    assert new[('Civil', 'Shop Drawing')] == old[('Civil', 'Shop Drawing')]
    # one deliberate improvement: 'Duct routing' came back with code C but has no
    # submission date. A reply means it was sent, so it now counts as submitted (and
    # rejected): % Submitted = (1 - 1) / 1 = 0%, where the old reader said -100%.
    n, o = new[('MEP', 'Shop Drawing')], old[('MEP', 'Shop Drawing')]
    assert (o['submitted_rows'], o['submitted_pct']) == (0, -100.0)
    assert (n['submitted_rows'], n['submitted_pct']) == (1, 0.0)
    assert n['not_approved_rows'] == o['not_approved_rows'] == 1

    p2 = tmp_path / 'e1_multisheet.xlsx'
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = 'Civil Drawings'
    ws1.append(['Drawing Type', 'Drawing Title', 'Submission Date', 'Planned', 'Status'])
    ws1.append(['Shop Drawing', 'Rebar', datetime(2026, 1, 10), datetime(2026, 1, 5), 'Approved'])
    ws1.append(['Shop Drawing', 'Formwork', None, datetime(2026, 1, 20), 'Under Review'])
    ws2 = wb.create_sheet('Arch.')
    ws2.append(['Drawing Type', 'Drawing Title', 'Submission Date', 'Planned', 'Status'])
    ws2.append(['Detailed Design', 'Facade', datetime(2026, 2, 1), datetime(2026, 1, 25), 'Rejected'])
    wb.save(p2)
    new = _summary(p2)
    old = summarize_e1(read_e1_rows(str(p2)))
    # identical except one deliberate improvement: 'Formwork' is Under Review with no
    # submission date — a reply means it was sent, so it now counts as submitted
    assert set(new) == set(old)
    assert new[('Arch.', 'Detailed Design')] == old[('Arch.', 'Detailed Design')]
    n, o = new[('Civil', 'Shop Drawing')], old[('Civil', 'Shop Drawing')]
    assert o['submitted_rows'] == 1 and n['submitted_rows'] == 2
    assert {k: v for k, v in n.items() if k not in ('submitted_rows', 'submitted_pct')} == \
        {k: v for k, v in o.items() if k not in ('submitted_rows', 'submitted_pct')}


def _roots_status_style(path):
    """ROOTS-style log whose review column is a word STATUS (not a letter code), including
    statuses that mean the drawing has NOT been sent yet (ELOG-1)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'E1 Log'
    ws.append(['ROOTS — SHOP DRAWING LOG'])
    ws.append([])
    ws.append(['No.', 'Descipline', 'Building', 'Description', 'Type of submittal', 'REV',
               'Date Submitted', 'Date Returned', 'Status', 'Planned Submission'])
    d = datetime
    for r in [
        [1, 'Civil', 'Main Silos', 'Raft', 'Shop Drawing', 0, d(2025, 1, 5), d(2025, 1, 9), 'Approved', d(2025, 1, 1)],
        [2, 'Civil', 'Main Silos', 'Walls', 'Shop Drawing', 0, None, None, 'Under preparation', d(2025, 2, 1)],
        [3, 'Civil', 'Towers', 'Slab', 'Shop Drawing', 0, None, None, 'Pending submission', d(2025, 3, 1)],
        [4, 'Civil', 'Towers', 'Stair', 'Shop Drawing', 0, None, None, 'In progress', d(2025, 4, 1)],
        [5, 'Civil', 'Towers', 'Roof', 'Shop Drawing', 0, d(2025, 2, 2), None, 'Under review', d(2025, 2, 1)],
        [6, 'Civil', 'Towers', 'Beams', 'Shop Drawing', 0, d(2025, 2, 3), d(2025, 2, 9), 'Revise & Resubmit', d(2025, 2, 1)],
        [7, 'MEP', 'Towers', 'Duct', 'Shop Drawing', 0, d(2025, 2, 4), None, 'Pending', d(2025, 2, 1)],
        [8, 'MEP', 'Towers', 'Cable', 'Shop Drawing', 0, None, None, 'Not yet submitted', d(2025, 5, 1)],
    ]:
        ws.append(r)
    wb.save(path)


def test_roots_style_status_column_not_sent_statuses_old_equals_new(tmp_path):
    p = tmp_path / 'roots_status.xlsx'
    _roots_status_style(p)
    new, old = _summary(p), summarize_e1(read_e1_rows(str(p)))
    assert new == old
    c = new[('Civil', 'Shop Drawing')]
    # 6 drawings. Sent: Raft (approved), Roof (under review), Beams (revise & resubmit) = 3.
    # Walls / Slab / Stair are not sent yet → not submitted, not under review.
    # % Submitted = (3 − 1) ÷ 6 = 33.3 ; % Approved = 1 ÷ 6 = 16.7
    assert (c['req'], c['submitted_rows'], c['approved_rows'], c['not_approved_rows'],
            c['under_review_rows']) == (6, 3, 1, 1, 1)
    assert (c['submitted_pct'], c['approved_pct']) == (33.3, 16.7)
    m = new[('MEP', 'Shop Drawing')]
    # Duct sent + 'Pending' → under review; Cable 'Not yet submitted' → nothing
    assert (m['req'], m['submitted_rows'], m['under_review_rows']) == (2, 1, 1)
    assert m['submitted_pct'] == 50.0


def test_not_sent_status_without_a_date_is_not_counted_as_submitted(tmp_path):
    # ELOG-1 reproduction: 1 approved with a date, then three "not sent yet" statuses with
    # no date. The reader must say 1 of 4 submitted (25%), not 4 of 4 (100%).
    p = tmp_path / 'prep.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Shop Log'
    ws.append(['Discipline', 'Drawing Title', 'Type of submittal', 'Date Submitted', 'Planned Submission', 'Status'])
    ws.append(['Civil', 'Raft', 'Shop Drawing', datetime(2025, 1, 5), datetime(2025, 1, 1), 'Approved'])
    ws.append(['Civil', 'Walls', 'Shop Drawing', None, datetime(2025, 2, 1), 'Under preparation'])
    ws.append(['Civil', 'Slab', 'Shop Drawing', None, datetime(2025, 3, 1), 'Pending submission'])
    ws.append(['Civil', 'Stair', 'Shop Drawing', None, datetime(2025, 4, 1), 'In progress'])
    wb.save(p)
    prop = es.inspect_log(str(p))
    g = _summary(p, prop)[('Civil', 'Shop Drawing')]
    assert (g['req'], g['submitted_rows'], g['approved_rows'], g['under_review_rows']) == (4, 1, 1, 0)
    assert g['submitted_pct'] == 25.0
    assert g == summarize_e1(read_e1_rows(str(p)))[('Civil', 'Shop Drawing')]
    # the panel explains these statuses instead of listing them as unknown codes
    codes = {c['value']: c for c in prop['codes']}
    assert codes['Under preparation']['verdict'] == 'ignore'
    assert codes['Under preparation']['known'] is True
    assert 'not sent' in codes['Under preparation']['meaning'].lower()
    sh = _sheet(prop, 'Shop Log')
    assert not any('no submission date' in w for w in sh['warnings'])
    assert any('not sent yet' in w for w in sh['warnings'])


def test_bare_pending_code_without_a_date_does_not_prove_it_was_sent(tmp_path):
    # ELOG-1 (a): W / P / 'Pending' alone is not a reply — only a real reply (approved /
    # not approved, or a reply date) or wording that puts the drawing WITH the consultant
    # ('Under review', 'U.A') shows it was sent.
    p = tmp_path / 'pend.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Log'
    ws.append(['Dwg No', 'Discipline', 'Type', 'Date Sent', 'Reply Date', 'Code'])
    for r in [['S-1', 'Steel', 'Shop', None, None, 'W'],             # not sent (no proof)
              ['S-2', 'Steel', 'Shop', None, None, 'P'],             # not sent (no proof)
              ['S-3', 'Steel', 'Shop', None, None, 'Under review'],  # with the consultant → sent
              ['S-4', 'Steel', 'Shop', None, datetime(2025, 3, 1), 'W'],   # a reply date → sent
              ['S-5', 'Steel', 'Shop', None, None, 'C']]:            # a reply → sent
        ws.append(r)
    wb.save(p)
    g = _summary(p)[('Steel', 'Shop')]
    # sent = S-3, S-4, S-5 = 3; not approved = S-5; under review = S-1..S-4 = 4
    assert (g['req'], g['submitted_rows'], g['not_approved_rows'], g['under_review_rows']) == (5, 3, 1, 4)


# ── 9. layout plumbing ────────────────────────────────────────────────────────────────
def test_planner_override_of_a_column_changes_the_count(tmp_path):
    p = tmp_path / 'shop_log.xlsx'
    _sg_style(p)
    prop = es.inspect_log(str(p))
    sh = _sheet(prop, 'Civil')
    # group by the OTHER 'Type' (RFT / Concrete Dimension) instead
    first_type = [c for c in sh['columns'] if c['header'] == 'Type'][0]
    second_type = [c for c in sh['columns'] if c['header'] == 'Type'][1]
    first_type['field'], second_type['field'] = 'submittal_type', 'ignore'
    s = _summary(p, prop)
    assert set(s) == {('Civil', 'RFT'), ('Civil', 'Concrete Dimension')}
    assert s[('Civil', 'RFT')]['req'] == 5 and s[('Civil', 'Concrete Dimension')]['req'] == 1


def test_excluded_sheet_is_not_counted(tmp_path):
    p = tmp_path / 'shop_log.xlsx'
    _sg_style(p)
    prop = es.inspect_log(str(p))
    _sheet(prop, 'Civil')['include'] = False
    assert es.read_rows(str(p), prop) == []


def test_signature_is_stable_and_layout_sensitive(tmp_path):
    a, b, c = tmp_path / 'a.xlsx', tmp_path / 'b.xlsx', tmp_path / 'c.xlsx'
    _sg_style(a)
    _sg_style(b)
    _om_style(c)
    sa, sb, sc = (es.inspect_log(str(x))['signature'] for x in (a, b, c))
    assert sa == sb and sa != sc


def test_remembered_layout_auto_applies(tmp_path):
    store = tmp_path / 'store'
    p = tmp_path / 'shop_log.xlsx'
    _sg_style(p)
    prop = es.inspect_log(str(p), store_dir=str(store))
    assert prop['remembered'] is None
    sh = _sheet(prop, 'Civil')
    types = [c for c in sh['columns'] if c['header'] == 'Type']
    types[0]['field'], types[1]['field'] = 'submittal_type', 'ignore'
    prop['code_map']['W'] = 'ignore'
    es.remember_layout(prop, store_dir=str(store))
    # the next log from the same source (same sheets + headings) opens with that choice
    p2 = tmp_path / 'shop_log_next_week.xlsx'
    _sg_style(p2)
    prop2 = es.inspect_log(str(p2), store_dir=str(store))
    assert prop2['remembered'] and prop2['remembered']['file'] == 'shop_log.xlsx'
    t2 = [c for c in _sheet(prop2, 'Civil')['columns'] if c['header'] == 'Type']
    assert (t2[0]['field'], t2[1]['field']) == ('submittal_type', 'ignore')
    assert prop2['code_map']['W'] == 'ignore'
    assert 'emembered' in t2[0]['reason']


def test_preview_counts_per_discipline(tmp_path):
    p = tmp_path / 'shop_log.xlsx'
    _sg_style(p)
    prop = es.inspect_log(str(p))
    pv = prop['preview']
    assert pv['rows_read'] == 9 and pv['drawings'] == 6
    civil = next(t for t in pv['by_trade'] if t['trade'] == 'Civil')
    assert (civil['req'], civil['approved_rows']) == (6, 3)


def test_sanitize_rejects_unknown_fields_and_bad_indices(tmp_path):
    p = tmp_path / 'shop_log.xlsx'
    _sg_style(p)
    prop = es.inspect_log(str(p))
    sh = _sheet(prop, 'Civil')
    sh['columns'][0]['field'] = 'drop table'          # not a field → treated as ignore
    sh['columns'].append({'index': 999, 'field': 'trade'})   # beyond the sheet → ignored
    rows = es.read_rows(str(p), prop)
    assert len(rows) == 9


def test_xls_is_refused_with_a_clear_message(tmp_path):
    p = tmp_path / 'old.xls'
    p.write_bytes(b'\xd0\xcf\x11\xe0 not really')
    with pytest.raises(ValueError, match='xlsx'):
        es.inspect_log(str(p))


# ── 10. optional offline-AI hook (off by default, never a cloud call) ─────────────────
def test_ai_hook_only_touches_low_confidence_columns_and_is_labelled(tmp_path):
    p = tmp_path / 'shop_log.xlsx'
    _sg_style(p)
    prop = es.inspect_log(str(p))
    seen = {}

    def fake_generate(system, user):
        seen['user'] = user
        return '{"suggestions": [{"index": 7, "field": "description"}, {"index": 0, "field": "bogus"}]}'
    out = es.suggest_columns_with_local_ai(prop, generate=fake_generate)
    sh = _sheet(out, 'Civil')
    col7 = next(c for c in sh['columns'] if c['index'] == 7)
    assert col7['ai_suggestion'] == 'description'
    assert col7['field'] != 'description' or col7['confidence'] >= 0.5   # a suggestion, not applied
    assert not any(c.get('ai_suggestion') == 'bogus' for c in sh['columns'])
    # only the header + a few sample values are sent — never whole rows
    assert 'D-001' not in seen['user'] or seen['user'].count('D-00') <= 8


def test_ai_hook_absent_brain_changes_nothing(tmp_path, monkeypatch):
    p = tmp_path / 'shop_log.xlsx'
    _sg_style(p)
    prop = es.inspect_log(str(p))
    monkeypatch.setattr(es, 'local_ai_ready', lambda: False)
    out = es.suggest_columns_with_local_ai(prop)
    assert out == prop


# ── 11. regressions found on a real closure log ───────────────────────────────────────
def test_group_titles_and_copy_counts_are_not_review_codes(tmp_path):
    # 'As-Built\nProgress' above the headings is a group title, not a legend 'AS = …';
    # a 'NUMBER OF COPIES' column full of 1s is not a column of review codes '1'.
    p = tmp_path / 'closure.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'O&M LOG'
    ws.append([None, 'As-Built\nProgress'])
    ws.append(['Dwg No', 'Discipline', 'Title', 'Date Sent', 'Status', 'NUMBER OF COPIES'])
    d = datetime(2025, 5, 1)
    for r in [['M-1', 'HVAC', 'Chiller manual', d, 'A', 1],
              ['M-2', 'HVAC', 'Pump manual', d, 'C', 1],
              ['M-3', 'HVAC', 'Fan manual', None, None, 1]]:
        ws.append(r)
    wb.save(p)
    prop = es.inspect_log(str(p))
    assert 'AS' not in prop['legend']
    sh = _sheet(prop, 'O&M LOG')
    copies = next(c for c in sh['columns'] if c['header'] == 'NUMBER OF COPIES')
    assert copies['field'] == 'ignore' and 'Review code' not in copies['reason']
    g = _summary(p, prop)[('HVAC', 'O&M')]
    assert (g['req'], g['submitted_rows'], g['approved_rows'], g['not_approved_rows']) == (3, 2, 1, 1)


def test_sheet_name_label_drops_log_even_when_glued_to_brackets():
    assert es._sheet_label('SPARE PARTS LOG(Arch)') == 'SPARE PARTS (Arch)'
    assert es._sheet_label('O&M LOG') == 'O&M'
    assert es._sheet_label('Civil Drawings') == 'Civil'


def test_headerless_running_number_is_a_serial_not_a_question(tmp_path):
    p = tmp_path / 'om.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'O&M LOG'
    ws.append([None, 'MANUAL TITLE', 'DISCIPLINE', 'ACTUAL DATE OF SUBMISSION', 'CURRENT STATUS'])
    ws.append(['Electrical'])
    for i, t in enumerate(['Transformer', 'UPS', 'ATS'], 1):
        ws.append([i, f'O&M for {t}', 'Electrical', '20-3-2024', 'Approved (Code B)'])
    ws.append(['Mechanical'])
    for i, t in enumerate(['Pumps', 'Fans'], 1):
        ws.append([i, f'O&M for {t}', 'Mechanical', '21-3-2024', 'U.A'])
    wb.save(p)
    col_a = _sheet(es.inspect_log(str(p)), 'O&M LOG')['columns'][0]
    assert col_a['index'] == 0 and col_a['field'] == 'ignore'
    assert col_a['level'] == 'high' and 'serial' in col_a['reason']


def test_text_code_with_decimal_zero_is_one_code_in_the_panel(tmp_path):
    # ELOG-3: '2.0' typed as text and the number 2 are the same review code
    p = tmp_path / 'dec.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Register'
    ws.append(['Document No', 'Discipline', 'Document Type', 'Date Submitted', 'Review Code'])
    d = datetime(2025, 5, 1)
    for r in [['DOC-1', 'MEP', 'Shop Drawing', d, 2], ['DOC-2', 'MEP', 'Shop Drawing', d, '2.0'],
              ['DOC-3', 'MEP', 'Shop Drawing', d, '3.0'], ['DOC-4', 'MEP', 'Shop Drawing', d, 'Resubmitted']]:
        ws.append(r)
    wb.save(p)
    prop = es.inspect_log(str(p))
    codes = {c['value']: c for c in prop['codes']}
    assert codes['2']['count'] == 2 and codes['2']['verdict'] == 'approved'
    assert '2.0' not in codes
    assert codes['Resubmitted']['verdict'] == 'under_review'
    g = _summary(p, prop)[('MEP', 'Shop Drawing')]
    # DOC-1, DOC-2 approved; DOC-3 not approved; DOC-4 resubmitted → under review
    assert (g['req'], g['approved_rows'], g['not_approved_rows'], g['under_review_rows']) == (4, 2, 1, 1)


# ── ELOG-2: words typed in a date column ───────────────────────────────────────────────
def test_negative_words_in_the_submitted_column_are_not_submissions(tmp_path):
    # 5 drawings: 2 sent with dates (A, B), then 'Not submitted', 'Not yet', 'No' typed in
    # the Date Submitted column. True % Submitted = 2 ÷ 5 = 40% (not 100%), nothing under
    # review, and the sheet says which words were read and how.
    p = tmp_path / 'notsub.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Shop Log'
    ws.append(['Discipline', 'Drawing Title', 'Type of submittal', 'Date Submitted', 'Action Code'])
    ws.append(['Civil', 'Raft', 'Shop Drawing', datetime(2025, 1, 5), 'A'])
    ws.append(['Civil', 'Walls', 'Shop Drawing', datetime(2025, 1, 6), 'B'])
    ws.append(['Civil', 'Slab', 'Shop Drawing', 'Not submitted', None])
    ws.append(['Civil', 'Stair', 'Shop Drawing', 'Not yet', None])
    ws.append(['Civil', 'Roof', 'Shop Drawing', 'No', None])
    wb.save(p)
    prop = es.inspect_log(str(p))
    g = _summary(p, prop)[('Civil', 'Shop Drawing')]
    assert (g['req'], g['submitted_rows'], g['approved_rows'], g['under_review_rows']) == (5, 2, 2, 0)
    assert g['submitted_pct'] == 40.0
    sh = _sheet(prop, 'Shop Log')
    note = next(w for w in sh['warnings'] if 'words, not dates' in w)
    assert '"Date Submitted"' in note and '"Not submitted"' in note and 'not sent' in note
    assert any('words, not dates' in w for w in prop['warnings'])


def test_positive_marks_in_the_submitted_column_still_count(tmp_path):
    # 'Yes' / 'Done' / a tick = it happened (no date typed); 'see remarks' is not a date
    # and not a clear yes → not counted as sent, and reported.
    p = tmp_path / 'marks.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Shop Log'
    ws.append(['Discipline', 'Drawing Title', 'Type of submittal', 'Date Submitted', 'Action Code'])
    ws.append(['Civil', 'Raft', 'Shop Drawing', datetime(2025, 1, 5), None])
    ws.append(['Civil', 'Walls', 'Shop Drawing', 'Yes', None])
    ws.append(['Civil', 'Slab', 'Shop Drawing', 'Done', None])
    ws.append(['Civil', 'Stair', 'Shop Drawing', '✓', None])
    ws.append(['Civil', 'Roof', 'Shop Drawing', 'see remarks', None])
    ws.append(['Civil', 'Beam', 'Shop Drawing', 'Pending', None])
    wb.save(p)
    prop = es.inspect_log(str(p))
    g = _summary(p, prop)[('Civil', 'Shop Drawing')]
    # sent = Raft, Walls, Slab, Stair = 4 (each sent with no reply → under review)
    assert (g['req'], g['submitted_rows'], g['under_review_rows']) == (6, 4, 4)
    note = next(w for w in _sheet(prop, 'Shop Log')['warnings'] if 'words, not dates' in w)
    assert '"Yes"' in note and '"see remarks"' in note and '"Pending"' in note


@pytest.mark.parametrize('text,expected', [
    ('Not submitted', 'no'), ('Not yet', 'no'), ('No', 'no'), ('N/S', 'no'), ('NS', 'no'),
    ('Pending', 'no'), ('Awaiting', 'no'), ('To be submitted', 'no'), ('Under prep.', 'no'),
    ('Yes', 'yes'), ('Y', 'yes'), ('Done', 'yes'), ('Submitted', 'yes'), ('✓', 'yes'), ('OK', 'yes'),
    ('see remarks', 'word'), ('27-3-2024', 'date'), (None, 'blank'), ('N/A', 'blank'), ('-', 'blank'),
])
def test_read_mark_kinds(text, expected):
    assert es._read_mark(text, True)[1] == expected


# ── ELOG-4 (owner decision 2026-09-27): rejected, then resubmitted → latest revision decides ──
def _rejected_then_resent(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Steel'
    ws.append(['Drawings No', 'Discipline', 'Type', 'Rev.', 'Sent Date', 'Received Date', 'Action'])
    d = datetime
    for r in [['BT-1', 'Steel', 'SD', 0, d(2025, 1, 5), d(2025, 1, 9), 'C'],
              ['BT-1', 'Steel', 'SD', 1, d(2025, 2, 5), None, 'W'],        # C → W (resubmitted)
              ['BT-2', 'Steel', 'SD', 0, d(2025, 1, 6), d(2025, 1, 9), 'C'],
              ['BT-2', 'Steel', 'SD', 1, d(2025, 2, 6), None, None],       # C → sent, no reply
              ['BT-3', 'Steel', 'SD', 0, d(2025, 1, 7), d(2025, 1, 9), 'C'],
              ['BT-3', 'Steel', 'SD', 1, d(2025, 2, 7), d(2025, 2, 9), 'B'],  # C → B = approved
              ['BT-4', 'Steel', 'SD', 0, d(2025, 1, 8), d(2025, 1, 9), 'D']]:  # D only
        ws.append(r)
    wb.save(path)


def test_rejected_then_resubmitted_latest_revision_decides_and_says_so(tmp_path):
    # OWNER DECISION ELOG-4 (2026-09-27): once approved it stays approved; otherwise the LATEST
    # revision decides. BT-1 (C→W) and BT-2 (C→sent, no reply) = Under review (and Submitted);
    # BT-3 (C→B) approved; BT-4 (D only) not approved.
    # % Submitted = (4 − 1) ÷ 4 = 75.0;  % Approved = 1 ÷ 4 = 25.0.
    p = tmp_path / 'steel.xlsx'
    _rejected_then_resent(p)
    prop = es.inspect_log(str(p))
    g = _summary(p, prop)[('Steel', 'SD')]
    assert (g['req'], g['submitted_rows'], g['approved_rows'], g['not_approved_rows'],
            g['under_review_rows']) == (4, 4, 1, 1, 2)
    assert (g['submitted_pct'], g['approved_pct']) == (75.0, 25.0)
    # … and the planner is told, in plain words, how many drawings this affects
    note = next(w for w in _sheet(prop, 'Steel')['warnings'] if 'resubmitted' in w)
    assert note.startswith('2 drawing(s)')
    assert 'latest revision decides' in note and 'Under review' in note
    assert 'until an approval comes back' not in note


def _om_with_empty_spare_parts(path, spare_submitted=False):
    """The real O&M register plus a SPARE PARTS LOG listing items that nothing has been
    submitted for yet (MDF closure log)."""
    _om_style(path)
    wb = openpyxl.load_workbook(path)
    ws = wb.create_sheet('SPARE PARTS LOG')
    ws.append(['SN', 'SPARE PARTS DESCRIPTION', 'DISCIPLINE', 'PLANNED DATE', 'ACTUAL DATE OF SUBMISSION',
               'CONSULTANT REPLY DATE', 'CURRENT STATUS'])
    for i, item in enumerate(('Spare fuses', 'Spare contactors', 'Spare filters', 'Spare belts'), 1):
        ws.append([i, item, 'Mechanical', '1-9-2024', '2-9-2024' if spare_submitted and i == 1 else None,
                   None, None])
    wb.save(path)


def test_register_with_nothing_submitted_is_switched_off_with_the_reason(tmp_path):
    p = tmp_path / 'closure.xlsx'
    _om_with_empty_spare_parts(p)
    prop = es.inspect_log(str(p))
    sp = _sheet(prop, 'SPARE PARTS LOG')
    assert sp['kind'] == 'register' and sp['include'] is False and sp['auto_off'] == 'untracked'
    assert 'nothing on this sheet' in sp['reason'].lower() and 'switch it on' in sp['reason'].lower()
    assert _sheet(prop, 'O&M LOG')['include'] is True
    assert prop['preview']['drawings'] == 5                      # the O&M register alone
    # the planner can switch it back on: its 4 items then count as not submitted
    _sheet(prop, 'SPARE PARTS LOG')['include'] = True
    again = es.refresh_layout(str(p), prop)
    assert again['preview']['drawings'] == 9
    back = _sheet(again, 'SPARE PARTS LOG')
    assert 'auto_off' not in back and 'switched off' not in back['reason']      # no stale reason
    assert any(w.startswith('SPARE PARTS LOG: Nothing on this sheet') for w in again['warnings'])


def test_register_with_a_submission_stays_counted(tmp_path):
    p = tmp_path / 'closure.xlsx'
    _om_with_empty_spare_parts(p, spare_submitted=True)
    prop = es.inspect_log(str(p))
    assert _sheet(prop, 'SPARE PARTS LOG')['include'] is True
    assert 'auto_off' not in _sheet(prop, 'SPARE PARTS LOG')


def test_log_with_nothing_submitted_anywhere_stays_counted(tmp_path):
    p = tmp_path / 'empty.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'SPARE PARTS LOG'
    ws.append(['SN', 'SPARE PARTS DESCRIPTION', 'DISCIPLINE', 'PLANNED DATE', 'ACTUAL DATE OF SUBMISSION',
               'CONSULTANT REPLY DATE', 'CURRENT STATUS'])
    for i, item in enumerate(('Spare fuses', 'Spare contactors', 'Spare filters'), 1):
        ws.append([i, item, 'Mechanical', '1-9-2024', None, None, None])
    wb.save(p)
    prop = es.inspect_log(str(p))
    assert _sheet(prop, 'SPARE PARTS LOG')['include'] is True
