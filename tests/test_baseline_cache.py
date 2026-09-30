"""Review F2 — an attached baseline must never be evicted from the 20-file XML cache.

Before: db.cache_xml copied with shutil.copy2 (keeping P6's old export time) and the cleanup
deleted the oldest-by-mtime .xml beyond 20 without looking at what is attached — a baseline
exported a while ago was deleted in the same call that cached it, the upload said "matched
896/896" and every feature silently fell back to the update's own Planned dates.
"""
import json
import os
import time
import urllib.request

import db
from tests.test_baseline_everywhere import NO_BL, BASELINE_ALONE


def _old(path, days=90):
    t = time.time() - days * 86400
    os.utime(path, (t, t))


def _fill_cache(sdir, n, start=0):
    for i in range(start, start + n):
        p = sdir / f'{i:012d}_dummy{i}.xml'
        p.write_text('<x/>')


def test_cached_copy_is_stamped_now_and_survives_a_full_cache(temp_db, tmp_path):
    sdir = temp_db / 'schedules'
    _fill_cache(sdir, 20)                                  # 20 schedules already cached
    bl = tmp_path / 'baseline_old.xml'
    bl.write_text(BASELINE_ALONE, encoding='utf-8')
    _old(bl)                                               # exported three months ago
    cached = db.cache_xml(str(bl), db.hash_file(str(bl)))
    assert os.path.isfile(cached)                          # not deleted by its own cleanup
    assert os.path.getmtime(cached) > time.time() - 60
    assert len(list(sdir.glob('*.xml'))) == 20


def test_attached_baseline_is_never_evicted(temp_db, tmp_path):
    sdir = temp_db / 'schedules'
    bl = tmp_path / 'baseline.xml'
    bl.write_text(BASELINE_ALONE, encoding='utf-8')
    cached = db.cache_xml(str(bl), db.hash_file(str(bl)))
    pid = db.upsert_project('P1', 'Proj')
    sid = db.insert_snapshot(pid, '2025-04-01', str(tmp_path / 'u.xml'), None, 'h' * 64, 3, 1)
    db.save_baseline(sid, cached, str(bl))
    _old(cached, 400)                                      # the oldest file in the cache …
    _fill_cache(sdir, 30)                                  # … and 30 newer imports after it
    db._cleanup_old_xml_files()
    assert os.path.isfile(cached)                          # still there: it is attached
    others = [p for p in sdir.glob('*.xml') if str(p) != cached]
    assert len(others) == 20                               # and it does not use up the cap
    assert db.get_attached_baseline(snapshot_id=sid) == cached

    db.save_baseline(sid, None)                            # forgotten → an ordinary cached file
    db._cleanup_old_xml_files()
    assert not os.path.isfile(cached)


def test_original_path_is_the_fallback_and_survives_a_recompute(temp_db, tmp_path):
    bl = tmp_path / 'baseline.xml'
    bl.write_text(BASELINE_ALONE, encoding='utf-8')
    cached = db.cache_xml(str(bl), db.hash_file(str(bl)))
    pid = db.upsert_project('P1', 'Proj')
    sid = db.insert_snapshot(pid, '2025-04-01', str(tmp_path / 'u.xml'), None, 'h' * 64, 3, 1)
    db.save_baseline(sid, cached, str(bl))
    # a recompute in place re-saves the extras with only the baseline path — the original stays
    db.save_evm_extras(sid, {'gap': None, 'baseline_path': cached})
    assert db.get_evm_extras(sid)['baseline_original'] == str(bl)
    # a re-import of the same update (a new snapshot) carries it too
    sid2 = db.insert_snapshot(pid, '2025-04-01', str(tmp_path / 'u.xml'), None, 'h' * 64, 3, 1)
    db.save_evm_extras(sid2, {'baseline_path': cached})
    assert db.get_evm_extras(sid2)['baseline_original'] == str(bl)

    os.remove(cached)                                      # the cached copy is gone
    assert db.get_attached_baseline(snapshot_id=sid) == str(bl)
    os.remove(bl)                                          # both gone → the missing copy is named
    assert db.get_attached_baseline(snapshot_id=sid) == cached


def _post(port, route, body):
    req = urllib.request.Request(
        f'http://127.0.0.1:{port}/{route}', data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def test_old_baseline_attached_to_a_full_cache_is_used_end_to_end(test_server, tmp_path):
    """The reviewer's run2, synthetic: 20 cached schedules, a baseline exported 90 days ago."""
    sdir = tmp_path / 'schedules'
    _fill_cache(sdir, 20)
    upd = tmp_path / 'update.xml'
    upd.write_text(NO_BL, encoding='utf-8')
    bl = tmp_path / 'bl_src' / 'baseline_old.xml'
    bl.parent.mkdir()
    bl.write_text(BASELINE_ALONE, encoding='utf-8')
    _old(bl)
    r = _post(test_server, 'api/parse', {'path': str(upd)})
    assert r['ok'], r.get('error')
    up = _post(test_server, 'api/baseline/upload', {
        'path': str(bl), 'xml_path': str(upd), 'cached_path': r['cached_path'],
        'snapshot_id': r['snapshot_id']})
    assert up['ok'] and up['matched'] == 3, up
    assert os.path.isfile(up['baseline_cached'])
    assert up['result']['baseline_source'] == 'attached'
    assert up['result'].get('baseline_missing') is None

    _fill_cache(sdir, 25, start=100)                       # 25 more imports later …
    db._cleanup_old_xml_files()
    assert os.path.isfile(up['baseline_cached'])           # … the baseline is still there
    ua = _post(test_server, 'api/update/analyze', {
        'xml_path': str(upd), 'cached_path': r['cached_path'], 'snapshot_id': r['snapshot_id']})
    assert ua['ok'], ua
    assert ua['report']['baseline_source'] == 'attached'
