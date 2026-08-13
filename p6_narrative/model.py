"""The narrative document model — a plain, JSON-serialisable structure the HTML
and Word renderers both consume.

A ``Section`` has:
  * number/title       — as it appears in the document
  * kind               — how it renders: prose | keyvals | table | wbs | codes |
                         sequence | costbars | cashflow | fillblank
  * provenance         — where its content came from: auto | calendar | drafted | fill
  * payload            — kind-specific data
  * editable           — whether the on-screen prose is user-editable before export
"""

PROVENANCE = ('auto', 'calendar', 'drafted', 'fill')


class Section:
    def __init__(self, number, title, kind, provenance,
                 payload=None, note=None, editable=False):
        assert provenance in PROVENANCE, provenance
        self.number = number
        self.title = title
        self.kind = kind
        self.provenance = provenance
        self.payload = payload if payload is not None else {}
        self.note = note
        self.editable = editable

    def to_dict(self):
        return {
            'number': self.number, 'title': self.title, 'kind': self.kind,
            'provenance': self.provenance, 'payload': self.payload,
            'note': self.note, 'editable': self.editable,
        }


class NarrativeDoc:
    def __init__(self, meta, sections):
        self.meta = meta or {}
        self.sections = sections or []

    def to_dict(self):
        return {'meta': self.meta, 'sections': [s.to_dict() for s in self.sections]}

    def counts(self):
        """Tally sections by provenance (for the on-screen summary)."""
        out = {p: 0 for p in PROVENANCE}
        for s in self.sections:
            out[s.provenance] = out.get(s.provenance, 0) + 1
        return out
