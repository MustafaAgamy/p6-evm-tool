"""Every navigator page must have its host element in index.html.

Regression: the Reporting Studio merge (#80) dropped
`<section id="prodintel-section">` from index.html. prodintel.js looks the
host up with getElementById(...)?.  — so with the element gone the
Productivity & Resources page silently rendered nothing (no error, no page).
These checks tie each page module's host id to the markup so a future edit
can't remove one without a test failing.
"""
import os
import re

UI = os.path.join(os.path.dirname(__file__), '..', 'ui')


def _read(*parts):
    return open(os.path.join(UI, *parts), encoding='utf-8').read()


INDEX = _read('index.html')

# page module -> the host element id it renders into
PAGES = {
    'prodintel.js': 'prodintel-section',   # Productivity & Resources
    'knowledge.js': 'kb-playbooks-section',  # Knowledge Base (Playbooks)
    'recent.js': 'recent-section',          # Recent Projects
}


def _section(host_id):
    return re.search(r'<section[^>]*\bid="%s"[^>]*>' % re.escape(host_id), INDEX)


def test_each_page_module_still_uses_its_host_id():
    for module, host_id in PAGES.items():
        assert host_id in _read('modules', module), \
            f'{module} no longer references #{host_id} — update PAGES in this test'


def test_each_page_host_exists_in_index_html():
    missing = [host_id for host_id in PAGES.values() if not _section(host_id)]
    assert not missing, f'index.html is missing page host section(s): {missing}'


def test_each_page_host_starts_hidden():
    for host_id in PAGES.values():
        m = _section(host_id)
        assert m and re.search(r'class="[^"]*\bhidden\b', m.group(0)), \
            f'#{host_id} must start hidden (pages open only from the navigator)'
