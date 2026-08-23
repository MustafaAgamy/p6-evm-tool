"""
DashboardContext — the single object every provider reads from.

It gives providers **parse-free** access to a project's stored results (the DB read
path, per Decision 001), and a lazily-parsed schedule for the few features that
recompute on demand (Constructability, Update Analysis). Everything is memoised, so
if several providers need the same source it is loaded/parsed exactly once per
dashboard request.

Providers must go through this object — never re-implement a feature's calculation.
"""

import os
import sys
import json

import db


class DashboardContext:
    def __init__(self, snapshot_id, project_id=None, xml_path=None, cached_path=None):
        self.snapshot_id = snapshot_id
        self.project_id = project_id or (db.snapshot_project_id(snapshot_id) if snapshot_id else None)
        self._xml_path = xml_path
        self._cached_path = cached_path
        self._memo = {}

    def _get(self, key, fn):
        if key not in self._memo:
            try:
                self._memo[key] = fn()
            except Exception as exc:  # pragma: no cover - defensive
                print(f'[dashboard] context.{key} failed: {exc}', file=sys.stderr)
                self._memo[key] = None
        return self._memo[key]

    def memo(self, key, fn):
        """Public memoisation for providers that recompute an expensive feature result
        (parse + review). Ensures the feature entry runs once even when several of its
        components are rendered together. Use a unique key per feature."""
        return self._get(f'prov:{key}', fn)

    # ── Parse-free stored results (no XML touched) ──────────────────────────

    def evm(self):
        """Rolled-up EVM result for the project's latest snapshot (metrics + categories
        + project name + finish dates), rebuilt from the DB. None if not stored."""
        if not self.project_id:
            return None
        return self._get('evm', lambda: db.get_project_result(self.project_id))

    def audit(self):
        """{'modules': {...}, 'module_order': [...]} from stored audit modules, or None."""
        return self._get('audit', lambda: db.get_audit_modules_for_snapshot(self.snapshot_id))

    def calendar(self):
        """Full Calendar Audit result blob, or None."""
        return self._get('calendar', lambda: db.get_calendar_audit(self.snapshot_id))

    def extras(self):
        """evm_extras blob: engineering_p6, activity_code_types, gap, baseline/expected
        finish, baseline_path. {} if none."""
        return self._get('extras', lambda: db.get_evm_extras(self.snapshot_id) or {})

    def e1(self):
        return self._get('e1', lambda: db.get_e1_summary(self.snapshot_id))

    def settings(self):
        """Per-project settings blob (location, weather, lag justifications, and the
        saved dashboard layout / last-run two-file results)."""
        if not self.project_id:
            return {}
        return self._get('settings', lambda: db.get_project_settings(self.project_id))

    def snapshots(self):
        """Per-snapshot EVM series for the project (trend charts), oldest first."""
        if not self.project_id:
            return []
        return self._get('snapshots', lambda: db.get_project_snapshots(self.project_id) or [])

    # ── Lazy parse + compute (recompute features only) ──────────────────────

    def xml_path(self):
        return self._get('xmlpath', lambda: db.resolve_xml_path(self._xml_path, self._cached_path))

    def config(self):
        def _load():
            from utils import resource_path
            with open(resource_path('config.json')) as f:
                return json.load(f)
        return self._get('config', _load)

    def parsed(self):
        """The parsed ScheduleData, or None if the XML is unavailable. Parsed once."""
        def _parse():
            path = self.xml_path()
            if not path or not os.path.isfile(path):
                return None
            from utils import resource_path
            sys.path.insert(0, resource_path('.'))
            from p6_evm.parser import parse_file
            return parse_file(path)
        return self._get('parsed', _parse)

    def computed(self):
        """metrics.compute(parsed) with auto-categories — the same numbers the EVM tab
        shows. Memoised. None if the XML is unavailable."""
        def _compute():
            data = self.parsed()
            if data is None:
                return None
            from p6_evm.metrics import compute
            from p6_evm.classify import auto_categories, build_wbs_classifier
            cfg = dict(self.config())
            cfg['categories'] = auto_categories(data)
            return compute(data, cfg, classifier=build_wbs_classifier(data))
        return self._get('computed', _compute)

    def has_xml(self):
        p = self.xml_path()
        return bool(p and os.path.isfile(p))
