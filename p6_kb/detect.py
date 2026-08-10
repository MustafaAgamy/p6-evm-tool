"""Project sub-type detection — rule-based signature matching, no AI.

Each KB entry lists ``signatures`` (keywords). We count how many appear in the
schedule's activity + WBS text and pick the best-matching sub-type. The user can
override the detected type.
"""
from p6_kb.model import detection_text


def score_entries(view, entries):
    """Return [(entry, hits)] sorted best-first."""
    text = detection_text(view)
    scored = [(e, sum(1 for s in e.get('signatures', []) if s.lower() in text)) for e in entries]
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored


def detect_subtype(view, entries):
    """Return (best_entry_or_None, scored_list). None when nothing matches at all."""
    scored = score_entries(view, entries)
    if scored and scored[0][1] > 0:
        return scored[0][0], scored
    return None, scored
