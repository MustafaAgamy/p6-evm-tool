"""System prompt, response schema, and request builder for the AI review.

The response is constrained with the Messages API *structured outputs*
(`output_config.format` → `json_schema`), so the model must return JSON matching
``RESPONSE_SCHEMA`` — no brittle free-text parsing.
"""
import json

SYSTEM = (
    "You are a senior planning and construction consultant reviewing a project's "
    "BASELINE schedule for constructability and scope completeness — the kind of "
    "review a client's planning manager does before approving a baseline. You reason "
    "from how projects of the detected type (infrastructure, industrial, roads, "
    "residential, administrative, hospital, airport, landscape, and others) are "
    "actually built.\n\n"
    "You are given a compact 'skeleton' of the schedule: activities (code, name, WBS "
    "path, duration, milestone flag), the relationships between them (predecessor → "
    "successor, type FS/SS/FF/SF, lag in working days), and the WBS. Costs and the "
    "client/project name are deliberately withheld.\n\n"
    "Your job — all of it ADVISORY OPINION, never presented as hard fact:\n"
    "1. Recognise the project type and summarise the build sequence you inferred.\n"
    "2. Flag ILLOGICAL relationships with technical engineering reasoning for *why*, "
    "and suggest the better logic. An activity may have several predecessors and "
    "successors — list them all. A suggestion may CHANGE a link, ADD one, or REMOVE a "
    "redundant one (mark each suggested link's 'kind').\n"
    "3. Find MISSING activities this project type normally needs. Give each a suggested "
    "activity id that MUST NOT match any existing activity id in the schedule, place it "
    "under an existing WBS (or propose a new WBS name and set new_wbs=true), and wire its "
    "predecessor and successor. Explain why it's normally needed.\n"
    "4. Review the WBS and flag MISSING WBS branches.\n"
    "Be specific and practical. Prefer Finish-Start logic unless another type is "
    "genuinely appropriate. Do not invent activities that already exist."
)

_REFERENCE_NOTE = (
    "\n\nA REFERENCE schedule skeleton is provided below. It is a proven baseline / "
    "template / standard for this project type, and it OUTRANKS your general knowledge: "
    "where the reference and your own expectations differ, follow the reference. Flag as "
    "missing anything the reference contains that this baseline lacks; judge logic against "
    "the reference first, then general practice."
)

# ── Structured-output schema (json_schema; additionalProperties:false everywhere) ──

def _link(extra_required=None):
    props = {
        'id': {'type': 'string'},
        'name': {'type': 'string'},
        'rel': {'type': 'string'},
    }
    req = ['id', 'name', 'rel']
    if extra_required:
        props['kind'] = {'type': 'string', 'enum': ['keep', 'change', 'add', 'remove']}
        req = req + ['kind']
    return {'type': 'array', 'items': {
        'type': 'object', 'properties': props, 'required': req, 'additionalProperties': False}}


_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['project_type', 'understood', 'illogical', 'missing', 'missing_wbs',
                 'wbs_review', 'conclusion'],
    'properties': {
        'project_type': {'type': 'string'},
        'understood': {
            'type': 'object', 'additionalProperties': False,
            'required': ['summary', 'phases'],
            'properties': {
                'summary': {'type': 'string'},
                'phases': {'type': 'array', 'items': {
                    'type': 'object', 'additionalProperties': False,
                    'required': ['name', 'present'],
                    'properties': {'name': {'type': 'string'}, 'present': {'type': 'boolean'}}}},
            }},
        'illogical': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['activity_id', 'activity_name', 'wbs_path', 'current_preds',
                         'current_succs', 'why', 'suggested_preds', 'suggested_succs', 'impact'],
            'properties': {
                'activity_id': {'type': 'string'},
                'activity_name': {'type': 'string'},
                'wbs_path': {'type': 'string'},
                'current_preds': _link(),
                'current_succs': _link(),
                'why': {'type': 'string'},
                'suggested_preds': _link(extra_required=True),
                'suggested_succs': _link(extra_required=True),
                'impact': {'type': 'string', 'enum': ['Critical', 'Near-critical', 'Minor']},
            }}},
        'missing': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['suggested_id', 'name', 'wbs', 'new_wbs', 'preds', 'succs', 'why', 'basis'],
            'properties': {
                'suggested_id': {'type': 'string'},
                'name': {'type': 'string'},
                'wbs': {'type': 'string'},
                'new_wbs': {'type': 'boolean'},
                'preds': _link(),
                'succs': _link(),
                'why': {'type': 'string'},
                'basis': {'type': 'string', 'enum': ['AI knowledge', 'Reference']},
            }}},
        'missing_wbs': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['name', 'why'],
            'properties': {'name': {'type': 'string'}, 'why': {'type': 'string'}}}},
        'wbs_review': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['name', 'status', 'note'],
            'properties': {
                'name': {'type': 'string'},
                'status': {'type': 'string', 'enum': ['ok', 'missing', 'partial']},
                'note': {'type': 'string'}}}},
        'conclusion': {'type': 'string'},
    },
}

RESPONSE_SCHEMA = {'type': 'json_schema', 'schema': _SCHEMA}


def build_request(skeleton, *, model, reference=None, effort='medium', max_tokens=16000):
    """Assemble the Messages API request body (dict) for a review."""
    parts = [
        "Review this baseline schedule. Skeleton (JSON):",
        json.dumps(skeleton, ensure_ascii=False),
    ]
    system = SYSTEM
    if reference is not None:
        system = SYSTEM + _REFERENCE_NOTE
        parts += ["\nREFERENCE skeleton (JSON) — this outranks general knowledge:",
                  json.dumps(reference, ensure_ascii=False)]
    else:
        parts.append("\n(No reference schedule provided — use your own construction knowledge.)")
    parts.append("\nReturn only the structured review.")
    return {
        'model': model,
        'max_tokens': max_tokens,
        'system': system,
        'output_config': {'format': RESPONSE_SCHEMA, 'effort': effort},
        'messages': [{'role': 'user', 'content': '\n'.join(parts)}],
    }
