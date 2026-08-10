"""Consultant Review — Baseline vs Current Update.

Compares an approved baseline (XER) against a current update (XML): the driving
logic / lag / duration changes that moved the delay, and a corrected "but-for"
update XML so P6's own F9 yields the right delay. The tool never computes a
schedule date itself — P6 reschedules the corrected file.

Isolated from p6_evm compute and p6_audit; activities and relationships are
matched by Activity code, never per-file ObjectId.
"""
