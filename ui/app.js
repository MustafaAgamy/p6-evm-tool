import { state }                              from './modules/state.js';
import { initTheme }                          from './modules/theme.js';
import { importFile, loadProject, loadHistory, generatePdf, generateModulePdf, exportExcel, deleteProject, generateCalendarPdf, exportCalendarExcel } from './modules/api.js';
import { clearError, loadAnother, showError } from './modules/render.js';
import { switchView, showChooser }             from './modules/audit.js';
import { renderConstructPanel }               from './modules/construct.js';
import { showDatabase, exitDatabase, initDatabase } from './modules/database.js';
import { showRecent, exitRecent }                   from './modules/recent.js';
import { maybePromptBaseline }                 from './modules/evm.js';
import { renderComparePanel }                  from './modules/compare.js';
import { renderPeriodPanel }                   from './modules/period.js';
import { renderCritPathPanel }                 from './modules/critpath.js';
import { renderUpdatePanel }                   from './modules/update.js';
import { renderSpecialPanel }                  from './modules/special.js';
import { renderOverview, renderWbs }           from './modules/overview.js';
import { renderSchedule }                       from './modules/gantt.js';
import { initTooltips }                        from './modules/tooltip.js';
import { initReportAppearanceControl }         from './modules/appearance.js';

document.addEventListener('DOMContentLoaded', () => {
  state.serverPort = window.__SERVER_PORT__;
  initTheme();
  initTooltips();
  initDatabase();
  loadHistory();

  // Unified Appearance control (six modes) — themes the whole app screen AND every report
  // preview/PDF from one choice. initTheme() above already painted the saved mode on load.
  initReportAppearanceControl('report-appearance');

  // ── Aurora+ shell — Project Navigator (module selector) + menu bar ──────────
  const NAV_ICONS = {
    home:'<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    evm:'<path d="M4 19V5M4 15l5-5 4 3 7-8"/>',
    audit:'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/>',
    oos:'<path d="M3 12h5l3-8 4 16 3-8h3"/>',
    calendar:'<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
    construct:'<path d="M9 11l3 3 8-8"/><path d="M20 12v6a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h9"/>',
    compare:'<path d="M7 8l-4 4 4 4"/><path d="M17 8l4 4-4 4"/><line x1="14" y1="4" x2="10" y2="20"/>',
    lag:'<path d="M4 4h11l5 5v11H4z"/><path d="M8 12h8"/>',
    period:'<path d="M3 17l6-6 4 4 8-8"/><path d="M17 7h4v4"/>',
    critpath:'<path d="M4 20V4"/><path d="M4 8h6l4 6h6"/>',
    update:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    special:'<path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6"/><path d="M9 13h6M9 17h6"/>',
    recent:'<path d="M3 3v5h5"/><path d="M3.05 13A9 9 0 106 5.3L3 8"/><path d="M12 7v5l3 2"/>',
    kb:'<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0018 0V5"/><path d="M3 12a9 3 0 0018 0"/>',
    overview:'<rect x="3" y="3" width="8" height="9" rx="1"/><rect x="13" y="3" width="8" height="5" rx="1"/><rect x="13" y="12" width="8" height="9" rx="1"/><rect x="3" y="16" width="8" height="5" rx="1"/>',
    sched:'<rect x="3" y="4" width="18" height="17" rx="1"/><path d="M3 9h18M8 13h5M8 17h8"/>',
    wbs:'<rect x="9" y="3" width="6" height="4"/><rect x="3" y="17" width="6" height="4"/><rect x="15" y="17" width="6" height="4"/><path d="M12 7v5M6 17v-3h12v3"/>',
    dash:'<rect x="3" y="3" width="8" height="9" rx="1"/><rect x="13" y="3" width="8" height="5" rx="1"/><rect x="13" y="12" width="8" height="9" rx="1"/><rect x="3" y="16" width="8" height="5" rx="1"/>',
    weather:'<path d="M17 18a4 4 0 000-8 6 6 0 00-11.3 2A3.5 3.5 0 006 18z"/>',
    ai:'<path d="M12 3l1.8 4.4L18 9l-4.2 1.6L12 15l-1.8-4.4L6 9z"/>',
    doc:'<path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6"/>',
  };
  const svgIcon = (k) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${NAV_ICONS[k] || ''}</svg>`;
  const NAV = [
    { node: { id:'home', label:'Import a schedule', icon:'home' } },
    { group:'Project', items:[
      ['overview','Overview','overview'], ['wbs','WBS','wbs'],
    ]},
    { group:'Analysis', items:[
      ['evm','Earned Value'], ['audit','Schedule Health'], ['critpath','Critical Path'],
      ['construct','Constructability'], ['oos','Out of Sequence'], ['lag','Lag Report'],
      ['compare','Consultant Review'], ['update','Update Analysis'], ['period','Update vs Update'],
    ]},
    { group:'Preview · coming soon', items:[
      ['pv_dash','Professional Dashboard','dash','preview'], ['pv_weather','Weather → Forecast','weather','preview'],
      ['pv_ai','AI Copilot · TIA','ai','preview'], ['pv_narr','Baseline Narrative','doc','preview'],
    ]},
    { group:'Reports', items:[ ['special','Special Report'] ] },
    { group:'Library', items:[ ['recent','Recent Projects'], ['kb','Knowledge Base'] ] },
  ];
  const CRUMB = { home:'Home', recent:'Recent Projects', kb:'Knowledge Base', evm:'Earned Value',
    audit:'Schedule Health', oos:'Out of Sequence', calendar:'Calendars', construct:'Constructability',
    compare:'Consultant Review', lag:'Lag Report', period:'Update vs Update', critpath:'Critical Path',
    update:'Update Analysis', special:'Special Report', overview:'Overview', schedule:'Schedule (Gantt)', wbs:'WBS' };
  const navTree = document.getElementById('nav-tree');
  const tnode = (id, label, icon, o = {}) => {
    const dis = o.preview || o.soon;
    const badge = o.preview ? '<span class="pbadge">Preview</span>' : (o.soon ? '<span class="pbadge soon">Soon</span>' : '');
    return `<button class="tnode${o.root ? ' root' : ''}${dis ? ' disabled' : ''}" data-nav="${id}"${dis ? ' title="In development — coming soon"' : ''}>` +
      `<span class="ti">${svgIcon(icon)}</span><span class="tl">${label}</span>${badge}</button>`;
  };
  navTree.innerHTML = NAV.map(sec => sec.node
    ? tnode(sec.node.id, sec.node.label, sec.node.icon, { root: true })
    : `<div class="tgrp">${sec.group}</div>` + sec.items.map(it => tnode(it[0], it[1], it[2] || it[0], { preview: it[3] === 'preview', soon: it[3] === 'soon' })).join('')
  ).join('');

  const setCrumb = (id) => { const c = document.getElementById('topbar-crumb'); if (c) c.textContent = CRUMB[id] || ''; };
  const markNav = (id) => document.querySelectorAll('#nav-tree .tnode[data-nav]')
    .forEach(n => n.classList.toggle('on', n.dataset.nav === id));

  // Open a feature view — reuses the exact per-view render path the chooser cards used.
  function openView(view) {
    state.currentView = view;          // drives the global File ▸ Print / Export to PDF action
    switchView(view);
    if (view === 'overview')  renderOverview(state.currentResult);
    if (view === 'wbs')       renderWbs(state.currentResult);
    if (view === 'schedule')  renderSchedule(state.currentResult);
    if (view === 'evm')       maybePromptBaseline(state.currentResult);
    if (view === 'construct')  renderConstructPanel();
    if (view === 'compare')    renderComparePanel();
    if (view === 'period')     renderPeriodPanel();
    if (view === 'critpath')   renderCritPathPanel();
    if (view === 'update')     renderUpdatePanel();
    if (view === 'special')    renderSpecialPanel();
  }
  function goHome() { exitDatabase(); exitRecent(); loadAnother(); loadHistory(); setCrumb('home'); }

  navTree.addEventListener('click', (e) => {
    const btn = e.target.closest('.tnode[data-nav]'); if (!btn) return;
    if (btn.classList.contains('disabled')) { showError('This module is in development — it will light up in an upcoming release.'); return; }
    const id = btn.dataset.nav;
    if (id === 'home')   { goHome(); return; }
    if (id === 'recent') { exitDatabase(); showRecent();   setCrumb('recent'); markNav('recent'); return; }
    if (id === 'kb')     { exitRecent();  showDatabase();  setCrumb('kb');     markNav('kb');     return; }
    // a feature/module view — only runs the one the user picked
    exitDatabase(); exitRecent();
    if (!state.currentResult) {
      showError('Import a P6 schedule first, then choose a module.');
      document.querySelector('.import-section')?.scrollIntoView({ behavior:'smooth', block:'start' });
      return;
    }
    document.getElementById('import-section')?.classList.add('hidden');  // keep the landing hidden while a module is open (exit* re-shows it)
    document.getElementById('results-section').classList.remove('hidden');
    openView(id);
    setCrumb(id);
    document.getElementById('results-section').scrollIntoView({ behavior:'smooth', block:'start' });
  });

  // Shared file-picker trigger (used by the Import cards AND File ▸ Import)
  async function triggerBrowse() { const path = await window.pywebview.api.choose_file(); if (path) importFile(path); }

  // ── Menu bar — the single home for global commands ──────────────────────────
  const MENUS = {
    file:    [['Import XML / XER…','import'], ['sep'], ['Print / Export to PDF…','print'], ['Export to Excel…','export-excel'], ['sep'], ['Load another file','load-another'], ['sep'], ['Recent projects','recent'], ['sep'], ['Exit','']],
    project: [['Recent projects','recent'], ['Knowledge Base','kb']],
    view:    [['Show / hide navigator','nav-toggle'], ['sep'], ['Appearance — top-right','']],
    analysis:[['Choose module…','showchooser'], ['Back to import','load-another']],
    tools:   [['Knowledge Base','kb'], ['Settings','']],
    help:    [['About Controlyx 2026','about']],
  };
  const menubar = document.getElementById('menubar');
  const menuLayer = document.getElementById('menu-layer');
  let openMenu = null;
  function closeMenus() { menuLayer.innerHTML = ''; document.querySelectorAll('.menu.open').forEach(m => m.classList.remove('open')); openMenu = null; }
  // Active-view → its (now-hidden) report trigger buttons. The single global
  // File ▸ Print / Export to PDF (and Export to Excel) invokes the active module's
  // existing PDF Preview + Printing Selection workflow — one primary control, no
  // per-module duplicate buttons. Views without a report (overview/wbs/schedule)
  // aren't listed and report a friendly message.
  const REPORT_BTN = {
    evm:      { pdf: 'pdf-btn' },
    audit:    { pdf: 'pdf-btn-audit',   xls: 'excel-btn' },
    oos:      { pdf: 'oos-pdf-btn',     xls: 'oos-excel-btn' },
    lag:      { pdf: 'lag-pdf-btn',     xls: 'lag-excel-btn' },
    calendar: { pdf: 'cal-pdf-btn',     xls: 'cal-excel-btn' },
    compare:  { pdf: 'cmp-preview-pdf', xls: 'cmp-export-xlsx' },
    critpath: { pdf: 'cpa-export-pdf',  xls: 'cpa-export-xlsx' },
    construct:{ pdf: 'cx-pdf',          xls: 'cx-xls' },
    period:   { pdf: 'per-export-pdf',  xls: 'per-export-xlsx' },
    update:   { pdf: 'ua-export-pdf',   xls: 'ua-export-xlsx' },
  };
  function runReport(kind) {
    if (!state.currentResult) { showError('Import a P6 schedule and open a module first.'); return; }
    const map = REPORT_BTN[state.currentView];
    if (!map) { showError('This view has no report — open an analysis module (Earned Value, Schedule Health, Calendar, …), then use File ▸ Print / Export.'); return; }
    const el = map[kind] && document.getElementById(map[kind]);
    if (el) { el.click(); return; }                        // opens the module's Preview + Printing Selection
    showError(kind === 'pdf'
      ? 'Run this module’s analysis first, then File ▸ Print / Export to PDF.'
      : 'This module has no Excel export.');
  }

  function runMenuCmd(cmd) {
    if (cmd === 'import')            triggerBrowse();
    else if (cmd === 'print')        runReport('pdf');
    else if (cmd === 'export-excel') runReport('xls');
    else if (cmd === 'load-another'){ loadAnother(); loadHistory(); setCrumb('home'); }
    else if (cmd === 'nav-toggle')  toggleNav();
    else if (cmd === 'recent')      { exitDatabase(); showRecent(); setCrumb('recent'); markNav('recent'); }
    else if (cmd === 'kb')          { exitRecent(); showDatabase(); setCrumb('kb'); markNav('kb'); }
    else if (cmd === 'showchooser') { if (state.currentResult) { document.getElementById('results-section').classList.remove('hidden'); showChooser(); } }
    else if (cmd === 'about')       showError('Controlyx 2026 — Primavera P6 schedule analysis. Import a P6 XML/XER, pick a module from the navigator, review results, export.');
  }
  menubar.addEventListener('click', (e) => {
    const m = e.target.closest('.menu'); if (!m) return;
    const key = m.dataset.menu;
    if (openMenu === key) { closeMenus(); return; }
    closeMenus(); m.classList.add('open'); openMenu = key;
    const rect = m.getBoundingClientRect();
    const d = document.createElement('div'); d.className = 'mdrop';
    d.style.left = rect.left + 'px'; d.style.top = (rect.bottom - 2) + 'px';
    d.innerHTML = (MENUS[key] || []).map(it =>
      it[0] === 'sep' ? '<div class="mdsep"></div>' : `<button class="mditem" data-cmd="${it[1]}">${it[0]}</button>`).join('');
    menuLayer.appendChild(d);
    d.querySelectorAll('.mditem').forEach(b => b.addEventListener('click', () => { const c = b.dataset.cmd; closeMenus(); if (c) runMenuCmd(c); }));
  });
  document.addEventListener('click', (e) => { if (!e.target.closest('#menubar') && !e.target.closest('#menu-layer')) closeMenus(); });

  // ── Navigator collapse toggle ───────────────────────────────────────────────
  function toggleNav() { document.querySelector('.appmain').classList.toggle('navhidden'); }
  document.getElementById('nav-toggle').addEventListener('click', toggleNav);
  document.getElementById('nav-collapse').addEventListener('click', toggleNav);

  // The Aurora+ empty-state drop-zone (id="browse-btn") opens the native picker,
  // which accepts both XML and XER — one import affordance for both formats.
  document.getElementById('browse-btn').addEventListener('click', async () => {
    const path = await window.pywebview.api.choose_file();
    if (path) importFile(path);
  });

  document.getElementById('error-close').addEventListener('click', clearError);
  // "Load another file" is a single global action (File ▸ Load another file / Analysis ▸ Back
  // to import / the "Import a schedule" navigator root) — no per-module duplicate button.
  document.getElementById('pdf-btn').addEventListener('click', generatePdf);
  document.getElementById('pdf-btn-audit').addEventListener('click', () => generateModulePdf());
  document.getElementById('excel-btn').addEventListener('click', () => exportExcel());
  document.getElementById('oos-pdf-btn').addEventListener('click', () => generateModulePdf('oos-pdf-btn'));
  document.getElementById('oos-excel-btn').addEventListener('click', () => exportExcel('oos-excel-btn'));
  document.getElementById('lag-pdf-btn').addEventListener('click', () => generateModulePdf('lag-pdf-btn'));
  document.getElementById('lag-excel-btn').addEventListener('click', () => exportExcel('lag-excel-btn'));
  document.getElementById('cal-pdf-btn').addEventListener('click', generateCalendarPdf);
  document.getElementById('cal-excel-btn').addEventListener('click', exportCalendarExcel);

  // Analysis chooser (shown after upload) → reveal the chosen view. Routed through
  // openView so it takes the exact same path as the navigator (incl. setting
  // state.currentView, which drives the global File ▸ Print / Export action).
  document.querySelectorAll('.chooser-card').forEach(card =>
    card.addEventListener('click', () => openView(card.dataset.view)));
  document.getElementById('btn-change-analysis').addEventListener('click', showChooser);

  // View tabs (EVM ⇄ Schedule Audit ⇄ Out of Sequence ⇄ Calendar Audit ⇄ Consultant Review)
  document.getElementById('tab-evm').addEventListener('click', () => { switchView('evm'); maybePromptBaseline(state.currentResult); });
  document.getElementById('tab-audit').addEventListener('click', () => switchView('audit'));
  document.getElementById('tab-oos').addEventListener('click', () => switchView('oos'));
  document.getElementById('tab-calendar').addEventListener('click', () => switchView('calendar'));
  document.getElementById('tab-construct').addEventListener('click', () => { switchView('construct'); renderConstructPanel(); });
  document.getElementById('tab-compare').addEventListener('click', () => { switchView('compare'); renderComparePanel(); });
  document.getElementById('tab-lag').addEventListener('click', () => switchView('lag'));
  document.getElementById('tab-period').addEventListener('click', () => { switchView('period'); renderPeriodPanel(); });
  document.getElementById('tab-critpath').addEventListener('click', () => { switchView('critpath'); renderCritPathPanel(); });
  document.getElementById('tab-update').addEventListener('click', () => { switchView('update'); renderUpdatePanel(); });
  document.getElementById('tab-special').addEventListener('click', () => { switchView('special'); renderSpecialPanel(); });

  // Drag-and-drop
  const dropTarget = document.getElementById('drop-target');
  const dropStrip  = document.getElementById('drop-strip');
  dropTarget.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropStrip.classList.add('drag-over');
  });
  dropTarget.addEventListener('dragleave', (e) => {
    if (!dropTarget.contains(e.relatedTarget)) dropStrip.classList.remove('drag-over');
  });
  dropTarget.addEventListener('drop', (e) => {
    e.preventDefault();
    dropStrip.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const ext = file.path ? file.path.toLowerCase().split('.').pop() : '';
    if (!file.path || !['xml', 'xer'].includes(ext)) {
      showError('Please drop a .xml or .xer file exported from Primavera P6.');
      return;
    }
    exitDatabase();
    exitRecent();
    importFile(file.path);
  });

  // History table — event delegation (rows are dynamically rendered)
  document.getElementById('recent-tbody').addEventListener('click', async (e) => {
    // Open button
    const openBtn = e.target.closest('.open-btn');
    if (openBtn) {
      const filePath   = openBtn.dataset.path      || '';
      const cachedPath = openBtn.dataset.cached    || '';
      const projectId  = openBtn.dataset.projectId || '';
      const origText = openBtn.textContent;
      openBtn.disabled = true;
      openBtn.textContent = '…';
      // Opening from the Recent Projects page → leave that page and show the
      // schedule on the normal Home + results view (import bar back, recent hidden).
      exitRecent();
      try {
        await loadProject(projectId, filePath, cachedPath);
        document.getElementById('results-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
      } finally {
        openBtn.disabled = false;
        openBtn.textContent = origText;
      }
      return;
    }

    // Delete button
    const deleteBtn = e.target.closest('.delete-btn');
    if (deleteBtn) {
      const projectId = deleteBtn.dataset.projectId;
      const name = deleteBtn.closest('tr')?.querySelector('td')?.textContent?.trim() || 'this project';
      if (!confirm(`Remove all import history for "${name}"?\n\nThis cannot be undone.`)) return;
      deleteBtn.disabled = true;
      try {
        const data = await deleteProject(projectId);
        if (data?.ok) {
          await loadHistory();
        } else {
          showError(data?.error || 'Delete failed.');
          deleteBtn.disabled = false;
        }
      } catch {
        showError('Delete failed. Try restarting the app.');
        deleteBtn.disabled = false;
      }
    }
  });
});
