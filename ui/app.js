import { state }                              from './modules/state.js';
import { initTheme }                          from './modules/theme.js';
import { importFile, loadProject, loadHistory, generatePdf, generateModulePdf, exportExcel, deleteProject, generateCalendarPdf, exportCalendarExcel } from './modules/api.js';
import { clearError, loadAnother, showError } from './modules/render.js';
import { switchView, showChooser }             from './modules/audit.js';
import { renderConstructPanel }               from './modules/construct.js';
import { showKbLibrary, exitKbLibrary, initKbLibrary } from './modules/kblib.js';
import { showDatabase, exitDatabase, initDatabase } from './modules/database.js';
import { maybePromptBaseline }                 from './modules/evm.js';
import { renderComparePanel }                  from './modules/compare.js';
import { renderPeriodPanel }                   from './modules/period.js';
import { renderCritPathPanel }                 from './modules/critpath.js';
import { renderUpdatePanel }                   from './modules/update.js';
import { renderSpecialPanel }                  from './modules/special.js';
import { initTooltips }                        from './modules/tooltip.js';
import { initReportAppearanceControl }         from './modules/appearance.js';

document.addEventListener('DOMContentLoaded', () => {
  state.serverPort = window.__SERVER_PORT__;
  initTheme();
  initTooltips();
  initKbLibrary();
  initDatabase();
  loadHistory();

  // Unified Appearance control (six modes) — themes the whole app screen AND every report
  // preview/PDF from one choice. initTheme() above already painted the saved mode on load.
  initReportAppearanceControl('report-appearance');

  document.getElementById('sb-home-btn').addEventListener('click', () => {
    exitKbLibrary();
    exitDatabase();
    loadAnother();
    loadHistory();
  });

  // Knowledge Base — its own sidebar page (browse the project-type standards)
  document.getElementById('sb-kb-btn').addEventListener('click', () => { exitDatabase(); showKbLibrary(); });
  // Construction Database — downloadable schedules by type
  document.getElementById('sb-db-btn').addEventListener('click', () => { exitKbLibrary(); showDatabase(); });

  document.getElementById('browse-btn').addEventListener('click', async () => {
    const path = await window.pywebview.api.choose_file();
    if (path) importFile(path);
  });

  document.getElementById('xer-btn').addEventListener('click', async () => {
    const path = await window.pywebview.api.choose_file();
    if (path) importFile(path);
  });

  document.getElementById('error-close').addEventListener('click', clearError);
  document.getElementById('load-another-btn').addEventListener('click', () => { loadAnother(); loadHistory(); });
  document.getElementById('pdf-btn').addEventListener('click', generatePdf);
  document.getElementById('pdf-btn-audit').addEventListener('click', () => generateModulePdf());
  document.getElementById('excel-btn').addEventListener('click', () => exportExcel());
  document.getElementById('oos-pdf-btn').addEventListener('click', () => generateModulePdf('oos-pdf-btn'));
  document.getElementById('oos-excel-btn').addEventListener('click', () => exportExcel('oos-excel-btn'));
  document.getElementById('lag-pdf-btn').addEventListener('click', () => generateModulePdf('lag-pdf-btn'));
  document.getElementById('lag-excel-btn').addEventListener('click', () => exportExcel('lag-excel-btn'));
  document.getElementById('cal-pdf-btn').addEventListener('click', generateCalendarPdf);
  document.getElementById('cal-excel-btn').addEventListener('click', exportCalendarExcel);

  // Analysis chooser (shown after upload) → reveal the chosen view
  document.querySelectorAll('.chooser-card').forEach(card =>
    card.addEventListener('click', () => {
      switchView(card.dataset.view);
      // XER + EVM → prompt to import the baseline first so results match the XML/P6 exactly
      if (card.dataset.view === 'evm') maybePromptBaseline(state.currentResult);
      if (card.dataset.view === 'construct') renderConstructPanel();
      if (card.dataset.view === 'compare') renderComparePanel();
      if (card.dataset.view === 'period') renderPeriodPanel();
      if (card.dataset.view === 'critpath') renderCritPathPanel();
      if (card.dataset.view === 'update') renderUpdatePanel();
      if (card.dataset.view === 'special') renderSpecialPanel();
    }));
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

  // Sidebar shield → jump to the Audit view when a schedule is loaded
  document.getElementById('sb-audit-btn').addEventListener('click', () => {
    exitKbLibrary();
    exitDatabase();
    if (state.currentResult) {
      document.getElementById('results-section').classList.remove('hidden');
      switchView('audit');
      document.getElementById('results-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
      document.querySelector('.import-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });

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
    exitKbLibrary();
    exitDatabase();
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
