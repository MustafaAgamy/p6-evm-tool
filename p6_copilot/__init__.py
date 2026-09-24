"""AI Copilot V2 — offline expert engine.

Reads every module's already-computed result for the open project (DB is the read
path) and answers the planner's / manager's questions with real schedule evidence —
fully offline, no cloud, no cost. `context` builds the 'project brain'; `answers`
turns a question into a plain, evidence-cited answer; `questions` is the repertoire.

Management-mode answers must read plainly to a manager with NO Primavera / project-
control background: jargon-free, advice-first, a full picture they can act on.
"""
