"""The final report HTML → PDF with headless Chrome — the SAME print pipeline every
feature report already uses (``--print-to-pdf``, no browser header/footer, the report's
own ``@page`` size/margins, ``print-color-adjust: exact`` from the theme)."""
import glob
import os
import shutil
import subprocess
import tempfile

_INSTALLED = (
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files\Chromium\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
)


def chrome_candidates(first=None):
    """``first`` (normally ``server._find_chrome()``), then every other Chromium we know of —
    a broken install (e.g. a Playwright Chromium whose side-by-side manifest fails to load)
    must not stop the export when a working browser is also present."""
    out = []
    for p in [first, *_INSTALLED]:
        if p and p not in out and os.path.isfile(p):
            out.append(p)
    local = os.environ.get('LOCALAPPDATA') or ''
    if local:
        for p in sorted(glob.glob(os.path.join(local, 'ms-playwright', 'chromium_headless_shell-*',
                                               '*', 'headless_shell.exe'))):
            if p not in out:
                out.append(p)
    return out


def run_chrome(chrome, args, timeout=180):
    """Run headless Chrome with ``args`` (everything after the executable), falling back to
    the next candidate when a binary cannot start. Returns the executable that ran."""
    last = None
    prof = tempfile.mkdtemp(prefix='cx_chrome_')
    try:
        for exe in chrome_candidates(chrome):
            try:
                subprocess.run([exe, '--headless', '--disable-gpu', '--no-sandbox',
                                f'--user-data-dir={prof}', *args],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=timeout)
                return exe
            except (OSError, subprocess.CalledProcessError) as exc:
                last = exc
                continue
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    raise RuntimeError(f'No working Chrome/Chromium found to print the report ({last}).')


def html_to_pdf(html, output_path, chrome=None, timeout=180):
    """Print ``html`` to ``output_path``. ``chrome`` = path from ``server._find_chrome()``.
    The shared pagination layer (report_theme.with_pagination) is applied first — once —
    and a report that never declared a page size prints on A4 like its Word twin."""
    try:
        import report_theme
        html = report_theme.with_pagination(html)
    except Exception:
        pass
    with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w',
                                     encoding='utf-8') as tmp:
        tmp.write(html)
        html_path = tmp.name
    out = os.path.abspath(output_path)
    tmp_pdf = html_path[:-5] + '.pdf'           # print beside the temp HTML, then move into place
    try:
        run_chrome(chrome, [f'--print-to-pdf={tmp_pdf}', '--no-pdf-header-footer',
                            f'file:///{html_path.replace(os.sep, "/")}'], timeout=timeout)
        if not os.path.isfile(tmp_pdf) or os.path.getsize(tmp_pdf) == 0:
            raise RuntimeError('Chrome did not produce the PDF.')
        shutil.move(tmp_pdf, out)
    finally:
        for p in (html_path, tmp_pdf):
            try:
                os.unlink(p)
            except OSError:
                pass
    return out
