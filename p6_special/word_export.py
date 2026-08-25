"""Word export — the SAME themed HTML as the PDF, wrapped as a Word-openable
document so the Word file looks identical to the PDF and stays editable.

Word's HTML engine ignores CSS variables, which is why the renderer resolves
every colour to concrete hex; here we only add the Office namespaces + a page
section so Word opens it cleanly as a print document. No third-party dependency.
"""
import html as _html

from p6_special.render_html import document_parts


def build_word_document(report_name, meta, rendered, mode='light', letterhead=None):
    """Return a Word-openable HTML document string (save with a .doc extension)."""
    parts = document_parts(report_name, meta, rendered, mode=mode, letterhead=letterhead)
    title = _html.escape(parts['title'])
    page_css = ('@page WordSection1 { size: 595.3pt 841.9pt; margin: 1.6cm 1.4cm; } '
                'div.WordSection1 { page: WordSection1; }')
    return (
        '<html xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:w="urn:schemas-microsoft-com:office:word" '
        'xmlns="http://www.w3.org/TR/REC-html40"><head>'
        '<meta charset="utf-8">'
        '<meta name="ProgId" content="Word.Document">'
        '<meta name="Generator" content="Microsoft Word 15">'
        f'<title>{title}</title>'
        '<!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View>'
        '<w:Zoom>100</w:Zoom><w:DoNotOptimizeForBrowser/></w:WordDocument></xml><![endif]-->'
        f'{parts.get("head_extra", "")}<style>{parts["css"]} {page_css}</style></head>'
        f'<body><div class="WordSection1">{parts["body"]}</div></body></html>'
    )


def save_word_document(html_str, output_path):
    """Write the Word HTML to ``output_path`` (a .doc path). Returns the path."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_str)
    return output_path
