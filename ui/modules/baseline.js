// One "Attach baseline (XER or XML)" flow for every screen that needs a baseline
// (Earned Value banner + prompt, Update Analysis "no baseline" state).
//
// The server resolves a schedule's baseline ONE way for every feature (p6_evm/baseline.py):
//   embedded — the file carries its baseline project (an XML exported WITH it)
//   attached — else the baseline file attached here, remembered for this update (snapshot)
//   self     — else the file's own Planned dates stand in (approximate) — an XER update
//              (P6 never writes the baseline into an XER) or an XML exported without it.
// Attaching (or removing) recomputes the snapshot in place (/api/baseline/upload → the import
// pipeline), so the fresh result replaces state.currentResult and every view agrees.
import { state } from './state.js';

export const ATTACH_BASELINE_LABEL = '📎 Attach baseline (XER or XML)';

// Which baseline the current result is measured against. Results stored before the server
// reported `baseline_source` fall back to the old rule (an XER never carries its baseline).
export function baselineSource(result, path) {
  const r = result || {};
  if (r.baseline_name || r.baseline_source === 'attached') return 'attached';
  if (r.baseline_source) return r.baseline_source;
  return (typeof path === 'string' && /\.xer$/i.test(path)) ? 'self' : 'embedded';
}

// Keys the import pipeline does not rebuild (engineering logs are stored per snapshot and
// re-applied on open) — carried over when the refreshed result replaces the current one.
const _CARRY = ['engineering_e1', 'e1_extras'];

function _adopt(fresh) {
  if (!fresh) return null;
  const old = state.currentResult || {};
  for (const k of _CARRY) if (fresh[k] === undefined && old[k] !== undefined) fresh[k] = old[k];
  state.currentResult = fresh;
  return fresh;
}

async function _post(route, body) {
  const resp = await fetch(`http://localhost:${state.serverPort}/${route}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  return resp.json();
}

// Pick a baseline file (XER or XML) and attach it to the open update.
// Resolves { ok, cancelled?, matched, total, baseline_name, result?, error?, code? }.
// `result` (the recomputed import result) has already replaced state.currentResult.
export async function attachBaselineFile() {
  let path;
  try { path = await window.pywebview.api.choose_file(); } catch { path = null; }
  if (!path) return { ok: false, cancelled: true };
  let data;
  try {
    data = await _post('api/baseline/upload', {
      path, xml_path: state.currentXmlPath, cached_path: state.currentCachedPath,
      snapshot_id: state.currentSnapshotId,
    });
  } catch {
    return { ok: false, error: 'Could not reach the local server. Try again.' };
  }
  if (data.ok && data.matched > 0) _adopt(data.result);
  return data;
}

// Forget the attached baseline for the open update (back to its own baseline).
export async function removeBaselineFile() {
  let data;
  try {
    data = await _post('api/baseline/clear', {
      xml_path: state.currentXmlPath, cached_path: state.currentCachedPath,
      snapshot_id: state.currentSnapshotId,
    });
  } catch {
    return { ok: false, error: 'Could not reach the local server. Try again.' };
  }
  if (data.ok) _adopt(data.result);
  return data;
}

// One plain sentence for a failed / unmatched attach — shown in the page (WebView2 alert()
// is a no-op in the packaged app).
export function attachProblem(data) {
  if (!data || data.cancelled) return '';
  if (!data.ok) return `Baseline not attached: ${String(data.error || 'the file could not be read').replace(/\.$/, '')}.`;
  if (!data.matched) {
    return `No activities in “${data.baseline_name || 'that file'}” match this update by Activity ID — ` +
      'it is probably another project’s baseline, so it was not attached.';
  }
  return '';
}
