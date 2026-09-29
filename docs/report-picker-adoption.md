# Report Contents picker + one-document exports — adoption recipe
Every feature's File ▸ Print / "Generate … PDF" opens ONE picker: showReportPreview in ui/modules/preview.js. It has two levels, sections (sub-features) ▸ parts (each table / chart / KPI group / findings list), and ONE export bar: Print · PDF · Word · HTML · Excel. All five come from the final HTML the preview shows: feature render → unticked parts removed → sections in the user's order → appearance mode. Pilots to copy: p6_evm/evm_report.py and p6_calendar/report.py (see their _part() / _sec() helpers).

## 1. Annotate the report HTML (Python renderer)
1. Wrap every top-level section in `<div data-sec="<key>">…</div>`, with the section's `<h2>` INSIDE. The keys are the UI `sections` list and the renderer's `sections=` filter.
2. Wrap each distinct part the screen shows in `<div data-part="<key>.<part>" data-part-label="Readable name">…</div>`: each table, chart, KPI/tile group and findings list. A part's own sub-heading goes INSIDE the part so it disappears with it.
3. CSS/div charts: add `data-export="image"` so Word gets a Chrome-drawn picture, plus `data-chart-headers='[…]'` and `data-chart-data='[[…],…]'` (JSON, html-escaped) so Excel gets the numbers. Inline `<svg>` needs nothing: PyMuPDF draws it after classes, var(--rpt-*) and currentColor are resolved.
4. A part with nothing to show: render the wrapper empty, or with `data-empty="1"`. The report then prints "No data available". Never silently drop a ticked part.
5. Headings stay with their content: `h2.sec{break-after:avoid}` and `[data-part]{break-inside:avoid-page}`, plus `.rpt-nodata` styling. Word gets keep_with_next automatically.
6. Screen-only chrome gets `data-export="skip"`. Colours use var(--rpt-*) tokens only (report_theme.var()).
7. Keep the report head line `Project: … · Data Date: … · Report Date: … · Schedule File: …`. The Word running header and the Excel header block read it.

## 2. Route the feature's print through the picker (UI)
showReportPreview({ title, subtitle, html, sections, selected, storageKey:'p6_report_sections_x', initialMode, onRerender:(keys,theme)=>fetchPreview(keys,theme), onThemeChange:(theme,keys)=>fetchPreview(keys,theme), feature:'X', exportName:'X_report', meta:{project}, onSave })
- `sections` = [{key,label,empty?}] in screen order. Sections found only in the HTML are appended automatically and start ticked. Parts are discovered from the HTML, so there is no JS list to maintain.
- The saved choice is {v:2,order,sections,offParts}; a legacy array is still read. Any caller reading storageKey must use an Array.isArray guard (every current caller does).
- Use `legacyPdf:true` only if the feature's PDF route does something the one-document PDF cannot. `exports:['pdf']` hides Word/HTML/Excel when the feature has a richer dedicated export (Reporting Studio).
- Never use alert/confirm/prompt (they do nothing in WebView2); the overlay shows its own toast.

## 3. Register it in the menu
In ui/app.js, add `REPORT_BTN[view] = {pdf:'<button id>', xls:'<excel id>'}`, or `PRINT_VIEW[view] = {module,title,get}` for printView screens. printView composes `<section class="pr-sec">`; switch those to data-sec/data-part wrappers to get parts. File ▸ Print must open the picker.

## 4. Parity checklist
- Every screen sub-feature is a data-sec; every table/chart/KPI group on screen is a data-part with a clear label.
- Same numbers, columns and date/number format as the screen. Format in the Python renderer, never in the exporters.
- Every chart has data-chart-* or is an `<svg>`.
- All 6 appearance modes use tokens only; check dark mode in both PDF and Word.

## 5. Tests (copy tests/test_p6_export.py and tests/test_p6_export_routes.py)
1. The renderer emits every data-sec key and data-part id: `p6_export.html_model.parse_report(html)` → `rep.sections[*].key`, `rep.part_labels`.
2. Prune one part (the `_prune()` helper), run to_docx.html_to_docx / to_xlsx.html_to_xlsx / to_html.write_html, and assert the part's unique text is absent while the other tables' cells are present.
3. Dark mode: the Word XML has no `var(` and has a `w:background`.
4. Live: open the feature with audit_kit, click its PDF button, stub `window.pywebview.api.choose_save_path`, untick a part, click `[data-exp=pdf|docx|html|xlsx]`, then check with pdf_text / docx_text / xlsx_text. See scratchpad/build/export/s/live_verify.py for a working script.

OTHER NOTES:
- The routes take {html, output_path, title, meta:{feature, project, data_date?}, sections?}. The Excel data date defaults to the report head's "Data Date:" text.
- p6_evm/xlsx_writer.py: xf 11-22 are the new number/date formats (NUMFMT_STYLE); wrap a value in `Styled(value, style, text)` for write_sections_xlsx blocks. Existing indices 0-10 are unchanged.
- The owner's "E2 Log" and review-code questions are untouched (not in this foundation's scope).

## 6. Page composition check (owner point 14) — run it on every PDF and Word you ship
`python -m p6_export.pagination_check <report.pdf|report.docx|report.doc>` prints JSON (`flags` with
page numbers, `counts`, `info`); exit 0 = clean, 1 = flags, 2 = error, 3 = skipped (no Word renderer).
It flags: orphaned_heading, kpi_separated_from_heading, heading_separated_from_block,
picture_separated_from_caption (Word), table_split_few_rows (< 3 body rows on a page),
small_table_split (a table <= 35 % of a page split), table_header_not_repeated, graphic_cut,
text_cut, content_in_margin, large_blank_then_continuation (> 35 % blank before a pushed block),
stranded_fragment, empty_page, and for a .docx's own pictures picture_truncated (content runs into
the picture's bottom edge - a section cut off) and picture_mostly_blank (< 50 % painted, >= 2 in of
white). `info.section_break_blank` (a new top-level section on a new page) is
not a defect. Word files are laid out by Word itself (COM, ~1-2 s a page) or, without Word, by
Spire.Doc (first 10 pages only). `--html report.html` passes the renderer's heading texts as hints.
Target: zero flags on GBT_XML for your feature's PDF and Word. In a test: `pc.check_pdf(path)['flags'] == []`
(see tests/test_pagination_check.py for the synthetic-report pattern).
