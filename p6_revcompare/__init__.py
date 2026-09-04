"""Baseline Revision Comparison — compare two P6 baseline revisions (Rev.00 vs Rev.01).

A neutral, progress-free planning/consultant comparison built on the repo's existing
diff and critical-path primitives. See ``compare.build_report``.
"""
from p6_revcompare.compare import build_report, build_report_from_data

__all__ = ['build_report', 'build_report_from_data']
