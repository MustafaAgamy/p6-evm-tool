"""One-document exports — every output is built from the ONE final report HTML.

The Report Contents picker (ui/modules/preview.js + report_parts.js) holds the exact
final report: the feature's render for the ticked sections, in the chosen appearance mode,
with unticked parts removed and sections in the chosen order. That single HTML string is
sent to one of four generic routes, so the outputs cannot diverge:

  POST /api/export/pdf   → :func:`p6_export.pdf.html_to_pdf`       (headless Chrome)
  POST /api/export/html  → :func:`p6_export.to_html.write_html`    (self-contained .html)
  POST /api/export/docx  → :func:`p6_export.to_docx.html_to_docx`  (real Word document)
  POST /api/export/xlsx  → :func:`p6_export.to_xlsx.html_to_xlsx`  (write_sections_xlsx)

Modules: css (a small CSS cascade engine), html_model (HTML → neutral block model),
svg_raster (charts → PNG), to_docx, to_xlsx, to_html, pdf. Pure functions; unit-tested in
tests/test_p6_export_*.py. How a feature adopts it: docs/report-picker-adoption.md.
"""
