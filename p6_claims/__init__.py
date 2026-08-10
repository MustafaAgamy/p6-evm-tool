"""Delay-analysis and claims engine (the AI Copilot's core knowledge).

The deterministic side builds impacted programmes and reads the exact impact back
from P6 (F9) — the day-count is never computed here or by the AI. The AI side
(reusing :mod:`p6_ai`) supplies method knowledge and structures the claim.
"""
