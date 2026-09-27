"""The final report HTML → PDF with headless Chrome — the SAME print pipeline every
feature report already uses (``--print-to-pdf``, no browser header/footer, the report's
own ``@page`` size/margins, ``print-color-adjust: exact`` from the theme)."""
import os
import subprocess
import tempfile


def html_to_pdf(html, output_path, chrome, timeout=180):
    """Print ``html`` to ``output_path``. ``chrome`` = path from ``server._find_chrome()``."""
    if not chrome:
        raise RuntimeError('No Chrome/Chromium found to print the PDF.')
    with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w',
                                     encoding='utf-8') as tmp:
        tmp.write(html)
        html_path = tmp.name
    try:
        subprocess.run([
            chrome, '--headless', '--disable-gpu', '--no-sandbox',
            f'--print-to-pdf={os.path.abspath(output_path)}', '--no-pdf-header-footer',
            f'file:///{html_path.replace(os.sep, "/")}',
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
    finally:
        try:
            os.unlink(html_path)
        except OSError:
            pass
    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError('Chrome did not produce the PDF.')
    return output_path
