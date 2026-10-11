"""Schedule Health — ONE corrected schedule with the fixes applied in every sub-feature.

Each sub-feature that can fix what it finds registers a writer here; the Summary's "Corrected
schedule" card (and each sub-feature's own Download) sends the fixes it holds, keyed by sub-feature,
and they are written one after another into a single copy of the imported file.

To let another sub-feature join: give it a ``write_corrected(source_path, accepted, out_path,
completion=None)`` that edits a copy of the file and returns ``{'applied': n, 'out_path': ...}``,
and add one line to ``FIXERS``. The Summary card lists whatever is registered.
"""
import os
import shutil
import tempfile


def _dangling(src, accepted, out, completion=None):
    from p6_audit.modules.dangling_resolve import write_corrected
    return write_corrected(src, accepted, out, completion=completion)


def _whole_day(src, accepted, out, completion=None):
    from p6_audit.modules.whole_day_resolve import write_corrected
    return write_corrected(src, accepted, out)


# Order matters only for reading the result: logic first, then durations.
FIXERS = [
    {'key': 'dangling',  'name': 'Dangling Activities', 'write': _dangling},
    {'key': 'whole_day', 'name': 'Whole-day Durations', 'write': _whole_day},
]


def fixer_keys():
    return [f['key'] for f in FIXERS]


def write_combined(source_path, fixes, out_path, completion=None):
    """Write every sub-feature's accepted fixes into one corrected copy of ``source_path``.
    ``fixes`` = {sub-feature key: [accepted fix, ...]}. Returns
    {'applied': total, 'by_feature': {key: n}, 'out_path': out_path}. The source is never modified."""
    fixes = fixes or {}
    todo = [f for f in FIXERS if fixes.get(f['key'])]
    if not todo:
        raise ValueError('No fixes have been applied yet.')
    ext = os.path.splitext(source_path)[1] or '.xer'
    tmpdir = tempfile.mkdtemp(prefix='cx-corrected-')
    try:
        cur, by_feature = source_path, {}
        for i, f in enumerate(todo):
            nxt = os.path.join(tmpdir, f'step{i}{ext}')
            res = f['write'](cur, fixes[f['key']], nxt, completion=completion)
            by_feature[f['key']] = int(res.get('applied') or 0)
            cur = nxt
        shutil.copyfile(cur, out_path)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return {'applied': sum(by_feature.values()), 'by_feature': by_feature, 'out_path': out_path}
