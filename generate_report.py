import argparse
import json
import os
import subprocess
import sys
import tempfile

from p6_evm.metrics import compute
from p6_evm.parser import parse_file
from p6_evm.report import find_finish_milestone, render_html

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

# System-install fallbacks, tried only if Playwright's own Chromium isn't
# available -- covers users who already have a browser and skipped
# `playwright install chromium` from scripts/install.sh|ps1.
CHROME_CANDIDATES = [
    '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
    '/opt/pw-browsers/chromium/chrome-linux/chrome',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
]


def find_chrome():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            path = p.chromium.executable_path
            if path and os.path.exists(path):
                return path
    except Exception:
        pass

    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path

    raise RuntimeError(
        'No Chromium/Chrome binary found. Run scripts/install.sh (or install.ps1 on '
        'Windows) to fetch one via Playwright, or install Google Chrome/Chromium yourself.'
    )


def load_config(path):
    with open(path) as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description='Render a PDF weekly report from a P6 XML export')
    parser.add_argument('xml_file')
    parser.add_argument('--config', default=DEFAULT_CONFIG_PATH)
    parser.add_argument('--overrides')
    parser.add_argument('--out', required=True, help='output PDF path')
    parser.add_argument('--keep-html', help='also save the intermediate HTML to this path')
    args = parser.parse_args()

    config = load_config(args.config)
    overrides = load_config(args.overrides) if args.overrides else None
    data = parse_file(args.xml_file)
    result = compute(data, config, overrides=overrides)

    fm = find_finish_milestone(result)
    milestone_baseline_finish = None
    if fm is not None:
        baseline = data.baseline_by_id.get(fm['activity']['id'])
        if baseline:
            milestone_baseline_finish = baseline['planned_finish']

    meta = {
        'project_name': data.project.get('name') or 'Weekly Report',
        'project_id': data.project.get('id') or '',
        'source_file': os.path.basename(args.xml_file),
        'milestone_baseline_finish': milestone_baseline_finish,
    }

    html_content = render_html(result, meta)

    if args.keep_html:
        html_path = args.keep_html
    else:
        tmp = tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w')
        tmp.write(html_content)
        tmp.close()
        html_path = tmp.name

    if args.keep_html:
        with open(html_path, 'w') as f:
            f.write(html_content)

    chrome = find_chrome()
    out_path = os.path.abspath(args.out)
    subprocess.run([
        chrome, '--headless', '--disable-gpu', '--no-sandbox',
        f'--print-to-pdf={out_path}', '--no-pdf-header-footer',
        f'file://{os.path.abspath(html_path)}',
    ], check=True, capture_output=True)

    print(f'PDF written to {out_path}')


if __name__ == '__main__':
    sys.exit(main())
