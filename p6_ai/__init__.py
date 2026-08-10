"""AI Constructability Review — isolated advisory AI layer.

This package is the *optional AI layer* described in the project's Decision 003:
the deterministic EVM/audit engines never call it, and it never alters their
numbers. It reviews a baseline for construction-logic sense and scope
completeness, returning clearly-labelled AI *opinion* (never hard facts).

Everything here is additive and self-contained — nothing in ``p6_evm`` /
``p6_audit`` imports it.
"""
