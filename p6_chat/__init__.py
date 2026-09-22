"""Offline AI Chat — a Claude-style chat inside Controlyx that answers as a senior
planning manager, grounded in the open project's real analysis, running entirely
on the user's PC.

Public surface (used by server.py):
    get_library()                     -> the role-categorised question library
    ask(question, result, role=None)  -> a grounded answer (or honest fallback)
    brain_status()                    -> local-brain setup state for the UI
    brain_setup(model=None)           -> trigger the one-time model download
    save_brain_settings(base_url,model)
    build_dashboard(xml_path=,snapshot_id=)  -> a grounded professional-dashboard payload

The heavy analysis is never re-run here: grounding reads the already-computed
result (the DB read path). No third-party dependency; the local model is reached
over localhost via stdlib only.
"""
from . import service, llm

get_library = service.get_library
ask = service.ask
answer_stream = service.answer_stream


def brain_status():
    return llm.status()


def brain_setup(model=None):
    return llm.pull(model)


def save_brain_settings(base_url=None, model=None):
    return llm.save_settings(base_url=base_url, model=model)


def build_dashboard(xml_path=None, snapshot_id=None):
    """A grounded 'professional dashboard' payload for the chat — time status,
    planned-vs-actual, EV-vs-PV gap by activity code, SPI/CPI, cost loading and an
    S-curve. Re-parses the schedule (the report/PDF exception to the DB read path,
    since the charts need the full ScheduleData) and reuses the existing engines;
    every number is computed, never invented."""
    from . import dashboard
    return dashboard.build_from_snapshot(snapshot_id=snapshot_id, xml_path=xml_path)


__all__ = ['get_library', 'ask', 'answer_stream', 'brain_status', 'brain_setup',
           'save_brain_settings', 'build_dashboard']
