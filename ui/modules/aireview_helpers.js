// Pure helpers for the AI Constructability Review view — no DOM, no imports,
// so they're unit-testable under plain Node (tests/js/test_aireview.js).

export function bandHex(band) {
  return { green: '#16a34a', amber: '#d97706', orange: '#ea580c', red: '#dc2626' }[band] || '#94a3b8';
}

export function kindClass(kind) {
  return { add: 'ai-add', remove: 'ai-rem', change: 'ai-chg', keep: 'ai-keep' }[kind] || '';
}

// Clamp a score to a 0–100 gauge position.
export function markerLeft(score) {
  return Math.max(0, Math.min(100, Number(score) || 0));
}

export function impactPill(impact) {
  if (impact === 'Critical') return '<span class="ai-pill ai-crit">Critical</span>';
  if (impact === 'Near-critical') return '<span class="ai-pill ai-warn">Near-critical</span>';
  return '<span class="ai-pill ai-minor">Minor</span>';
}
