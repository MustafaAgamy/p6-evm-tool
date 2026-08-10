// Power BI live dashboards — global "Open in Power BI" action + first-run setup.
import { state }     from './state.js';
import { showError } from './render.js';

const SEEN_KEY = 'p6_powerbi_seen';

async function apiPost(path, payload) {
  const resp = await fetch(`http://localhost:${state.serverPort}/${path}`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(payload || {}),
  });
  if (!resp.ok) throw new Error(`Server error ${resp.status}`);
  return resp.json();
}

const el = (id) => document.getElementById(id);
const showModal = () => { const m = el('pbi-modal'); if (m) m.style.display = 'flex'; };
const hideModal = () => { const m = el('pbi-modal'); if (m) m.style.display = 'none'; };

async function openDashboard() {
  const btn  = el('powerbi-btn');
  const idle = btn ? btn.innerHTML : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Preparing…'; }
  try {
    const data = await apiPost('api/powerbi/open', {});
    if (!data.ok) {
      showError(`Power BI dashboard failed: ${data.error || 'unknown error'}`);
    } else if (!data.opened) {
      // No Power BI association (or not installed) — point the user at the file.
      showError(`Dashboard ready. Open this file in Power BI Desktop: ${data.pbip}`);
    }
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) setTimeout(() => { btn.disabled = false; btn.innerHTML = idle; }, 2000);
  }
}

export function initPowerBI() {
  const btn = el('powerbi-btn');
  if (!btn) return;
  btn.addEventListener('click', () => {
    if (localStorage.getItem(SEEN_KEY)) openDashboard();
    else showModal();
  });
  el('pbi-modal-open')?.addEventListener('click', () => {
    localStorage.setItem(SEEN_KEY, '1');
    hideModal();
    openDashboard();
  });
  el('pbi-modal-close')?.addEventListener('click', hideModal);
  // click on the backdrop (not the panel) closes it
  el('pbi-modal')?.addEventListener('click', (e) => { if (e.target.id === 'pbi-modal') hideModal(); });
}
