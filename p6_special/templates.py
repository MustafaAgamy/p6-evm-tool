"""Named Special Report templates, saved per project.

Stored in ``project_settings`` under the ``'special_reports'`` key as a list of
``{id, name, item_ids, letterhead, mode}``. Uses ``save_project_settings``
(shallow-merge by top-level key), so we read the whole list, modify it, and
write it back — never clobbering other consumers' settings (calendar, weather…).
"""
import db

KEY = 'special_reports'


def list_templates(project_id):
    return list((db.get_project_settings(project_id) or {}).get(KEY) or [])


def get_template(project_id, template_id):
    for t in list_templates(project_id):
        if t.get('id') == template_id:
            return t
    return None


def _next_id(existing):
    ids = {t.get('id') for t in existing}
    n = 1
    while f'sr{n}' in ids:
        n += 1
    return f'sr{n}'


def save_template(project_id, template):
    """Insert or update a named template. Returns the stored record."""
    items = list_templates(project_id)
    tid = template.get('id')
    rec = {
        'id': tid or _next_id(items),
        'name': (template.get('name') or 'Untitled report').strip() or 'Untitled report',
        'item_ids': list(template.get('item_ids') or []),
        'letterhead': template.get('letterhead') or {},
        'mode': template.get('mode') or 'light',
    }
    if tid and any(t.get('id') == tid for t in items):
        items = [rec if t.get('id') == tid else t for t in items]
    else:
        items.append(rec)
    db.save_project_settings(project_id, {KEY: items})
    return rec


def delete_template(project_id, template_id):
    items = [t for t in list_templates(project_id) if t.get('id') != template_id]
    db.save_project_settings(project_id, {KEY: items})
    return items
