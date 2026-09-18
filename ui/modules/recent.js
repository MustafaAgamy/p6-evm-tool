// Recent Projects — its own sidebar page (Decision 010, binding standard).
// The recent list must never trail the content flow of Home or any module report,
// so it lives here as a dedicated page — hidden by default, revealed only when its
// sidebar icon is clicked. Mirrors the show/exit pattern of the Knowledge Base
// (kblib.js) and Construction Database (database.js) pages.

import { loadHistory } from './api.js';

export function showRecent() {
  document.getElementById('recent-section')?.classList.remove('hidden');
  document.querySelector('.import-section')?.classList.add('hidden');
  document.getElementById('results-section')?.classList.add('hidden');
  document.getElementById('kb-section')?.classList.add('hidden');
  document.getElementById('kb-database-section')?.classList.add('hidden');
  document.getElementById('sb-home-btn')?.classList.remove('active');
  document.getElementById('sb-audit-btn')?.classList.remove('active');
  document.getElementById('sb-kb-btn')?.classList.remove('active');
  document.getElementById('sb-db-btn')?.classList.remove('active');
  document.getElementById('sb-recent-btn')?.classList.add('active');
  document.getElementById('topbar-sub').textContent = 'Recent Projects';
  // Refresh on open so a schedule imported moments ago is already at the top.
  loadHistory();
}

export function exitRecent() {
  document.getElementById('recent-section')?.classList.add('hidden');
  document.querySelector('.import-section')?.classList.remove('hidden');
  document.getElementById('sb-recent-btn')?.classList.remove('active');
  document.getElementById('sb-home-btn')?.classList.add('active');
}
