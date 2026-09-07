// Help Center — a self-contained, full-window overlay that opens ABOVE the running app.
// Ports the APPROVED Help-menu mockup into a real module: six sections (Getting Started,
// Feature Guide with per-feature required-input chips + live search, Keyboard Shortcuts,
// What's New, Contact & Support, About), a left mini-nav, and a title bar with a close ✕.
//
//   import { openHelp } from './modules/help.js';
//   openHelp('feature-guide');   // section ∈ the SECTIONS keys below; default 'feature-guide'
//
// Theming: NO hardcoded surface/text hexes — everything reads the app's appearance tokens
// (var(--card-bg), var(--bg), var(--border), var(--hair), var(--text), var(--ink-soft),
// var(--muted), var(--accent), var(--accent-soft), var(--success)…) so the Help Center
// retheme's with the active appearance mode. The only fixed colour is the amber "extra
// file" chip (#c2731a), which has no semantic token. Close via ✕, Esc, or the scrim.

import { shortcutRows } from './shortcuts.js';

const STYLE_ID = 'hc-help-style';
const OVERLAY_ID = 'hc-help-overlay';

const SECTIONS = [
  { key: 'getting-started', label: 'Getting Started', sub: 'How Controlyx works',
    icon: '<path d="M12 2 4 6v6c0 5 3.5 8 8 10 4.5-2 8-5 8-10V6z"/><path d="m9 12 2 2 4-4"/>' },
  { key: 'feature-guide', label: 'Feature Guide', sub: 'What each feature needs',
    icon: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M9 4v16"/>' },
  { key: 'shortcuts', label: 'Keyboard Shortcuts', sub: 'Work faster',
    icon: '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>' },
  { key: 'whats-new', label: "What's New", sub: 'Recent highlights',
    icon: '<path d="m12 3 2.3 4.7 5.2.8-3.7 3.6.9 5.1L12 15l-4.6 2.4.9-5.1L4.5 8.5l5.2-.8z"/>' },
  { key: 'contact', label: 'Contact & Support', sub: 'Get help',
    icon: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>' },
  { key: 'about', label: 'About Controlyx', sub: 'Version & credits',
    icon: '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/>' },
];
const VALID = new Set(SECTIONS.map(s => s.key));
const DEFAULT_SECTION = 'feature-guide';

// ---- Feature Guide data (ported verbatim from the approved mockup) ----
//   k: 'p6' = blue chip (1 P6 schedule), 'extra' = amber chip (needs another file),
//      'optional' = dashed chip (prefixed "optional:"), 'none' = dashed chip (no file input)
const FEATURES = [
  { name: 'Overview', what: 'A snapshot of progress', inputs: [{ t: '1 P6 schedule', k: 'p6' }] },
  { name: 'WBS', what: 'Work-breakdown rollup', inputs: [{ t: '1 P6 schedule', k: 'p6' }] },
  { name: 'Schedule (Gantt)', what: 'Time-scaled activity chart', inputs: [{ t: '1 P6 schedule', k: 'p6' }] },
  { name: 'Schedule Health', what: 'DCMA-style checks', inputs: [{ t: '1 P6 schedule', k: 'p6' }] },
  { name: 'Baseline Narrative', what: 'Basis-of-schedule write-up', inputs: [{ t: '1 P6 schedule', k: 'p6' }] },
  { name: 'Lag Report', what: 'Relationship lags / leads', inputs: [{ t: '1 P6 schedule', k: 'p6' }] },
  { name: 'Earned Value', what: 'PV / EV, SPI / CPI, delay', inputs: [{ t: '1 P6 schedule', k: 'p6' }, { t: 'baseline for accurate PV', k: 'optional' }] },
  { name: 'Out of Sequence', what: 'Logic adherence', inputs: [{ t: '1 P6 schedule', k: 'p6' }] },
  { name: 'Update Analysis', what: 'Update vs its embedded baseline', inputs: [{ t: '1 P6 update', k: 'p6' }] },
  { name: 'Critical Path', what: 'Driving path & float health', inputs: [{ t: 'current update', k: 'p6' }, { t: 'baseline / previous file', k: 'extra' }], extra: true },
  { name: 'Update vs Update', what: 'Period over period', inputs: [{ t: 'this period', k: 'p6' }, { t: 'last period', k: 'extra' }], extra: true },
  { name: 'Consultant Review', what: 'Forensic but-for delay', inputs: [{ t: 'current update', k: 'p6' }, { t: 'baseline programme', k: 'extra' }], extra: true },
  { name: 'Baseline Revision', what: 'Compare two baselines', inputs: [{ t: 'Rev.00', k: 'p6' }, { t: 'Rev.01', k: 'extra' }], extra: true },
  { name: 'AI Copilot · TIA', what: 'Time-impact insights (offline)', inputs: [{ t: '1 P6 schedule', k: 'p6' }, { t: 'API key for AI narrative', k: 'optional' }] },
  { name: 'P6 Calendar Audit', what: 'Working-time & net days', inputs: [{ t: '1 P6 schedule', k: 'p6' }] },
  { name: 'Bad Weather', what: 'Stop-work impact', inputs: [{ t: '1 P6 schedule', k: 'p6' }, { t: 'project location', k: 'extra' }], extra: true },
  { name: 'Constructability', what: 'Buildability vs knowledge base', inputs: [{ t: '1 P6 schedule', k: 'p6' }] },
  { name: 'Professional Dashboard', what: 'Portfolio KPIs', inputs: [{ t: 'your imported projects', k: 'none' }] },
  { name: 'Special Report', what: 'Compose a custom report', inputs: [{ t: 'results from any features', k: 'none' }] },
];

let onKeyDown = null;   // active Esc handler (set on open, removed on close)

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function svg(paths, extra) {
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round"' + (extra || '') + '>' + paths + '</svg>';
}

function injectStyle() {
  if (document.getElementById(STYLE_ID)) return;
  const css = `
  #${OVERLAY_ID}{
    position:fixed; inset:0; z-index:99999;
    display:flex; align-items:center; justify-content:center;
    padding:24px; background:rgba(0,0,0,.5);
    font-family:"Segoe UI", system-ui, -apple-system, sans-serif;
    color:var(--text,#1e293b);
    animation:hc-scrim-in .16s ease;
  }
  @keyframes hc-scrim-in{ from{opacity:0} to{opacity:1} }
  @keyframes hc-shell-in{ from{opacity:0; transform:translateY(8px)} to{opacity:1; transform:none} }

  .hc-shell{
    width:min(1180px, 95vw); height:min(780px, 92vh);
    display:flex; flex-direction:column; min-width:0;
    background:var(--card-bg,#fff); border:1px solid var(--border,#e2e8f0);
    border-radius:16px; overflow:hidden;
    box-shadow:0 24px 70px -18px rgba(0,0,0,.5);
    animation:hc-shell-in .2s ease;
  }

  /* Title bar */
  .hc-titlebar{
    display:flex; align-items:center; gap:12px;
    padding:14px 16px 14px 20px;
    border-bottom:1px solid var(--border,#e2e8f0);
    background:var(--card-bg,#fff);
    flex:none;
  }
  .hc-tb-logo{
    width:30px; height:30px; border-radius:8px; flex:none;
    display:grid; place-items:center; color:#fff; font-weight:800; font-size:16px;
    background:var(--accent,#2563eb);
  }
  .hc-tb-title{ font-weight:800; font-size:16px; letter-spacing:-.2px; color:var(--text,#1e293b); }
  .hc-tb-title .yr{ color:var(--accent,#2563eb); font-weight:800; margin-left:4px; }
  .hc-tb-spacer{ flex:1; }
  .hc-close{
    width:34px; height:34px; border-radius:9px; flex:none;
    display:grid; place-items:center; cursor:pointer;
    background:transparent; border:1px solid var(--border,#e2e8f0);
    color:var(--muted,#64748b); transition:background .12s, color .12s, border-color .12s;
  }
  .hc-close:hover{ background:var(--bg,#eef2f7); color:var(--text,#1e293b); border-color:var(--accent,#2563eb); }
  .hc-close svg{ width:17px; height:17px; }

  /* Body: mini-nav + content */
  .hc-body{ display:grid; grid-template-columns:236px 1fr; flex:1; min-height:0; }
  @media (max-width:760px){ .hc-body{ grid-template-columns:64px 1fr; } }

  .hc-nav{
    background:var(--card-bg,#fff); border-right:1px solid var(--border,#e2e8f0);
    padding:12px 10px; display:flex; flex-direction:column; gap:3px; overflow:auto;
  }
  .hc-nav-item{
    display:flex; align-items:center; gap:11px;
    padding:9px 11px; border-radius:10px; cursor:pointer;
    color:var(--ink-soft,#41506a); font-size:13px; font-weight:500;
    border:1px solid transparent; text-align:left; background:transparent; width:100%;
    transition:background .12s, color .12s;
  }
  .hc-nav-item:hover{ background:var(--bg,#eef2f7); }
  .hc-nav-item.active{ background:var(--accent-soft,#dbe6ff); color:var(--accent-dark,#1d4ed8); font-weight:700; }
  .hc-nav-ico{
    width:30px; height:30px; border-radius:8px; flex:none;
    display:grid; place-items:center; color:var(--muted,#64748b);
    background:var(--bg,#eef2f7);
  }
  .hc-nav-item.active .hc-nav-ico{ background:var(--card-bg,#fff); color:var(--accent,#2563eb); }
  .hc-nav-ico svg{ width:16px; height:16px; }
  .hc-nav-txt{ min-width:0; }
  .hc-nav-txt .t{ display:block; line-height:1.2; font-weight:600; }
  .hc-nav-txt .s{ display:block; font-size:11px; color:var(--muted,#64748b); font-weight:500; margin-top:2px; line-height:1.25; }
  .hc-nav-item.active .hc-nav-txt .s{ color:var(--accent-dark,#1d4ed8); opacity:.8; }
  .hc-nav-foot{ margin-top:auto; padding:10px 8px 2px; font-size:10.5px; color:var(--muted,#64748b); text-align:center; }
  @media (max-width:760px){ .hc-nav-txt, .hc-nav-foot{ display:none; } .hc-nav-item{ justify-content:center; } }

  /* Content pane */
  .hc-content{ background:var(--bg,#eef2f7); padding:24px 26px 30px; overflow:auto; min-width:0; }
  .hc-screen{ display:none; }
  .hc-screen.show{ display:block; }

  .hc-head{ margin-bottom:18px; }
  .hc-head h2{ font-size:22px; margin:0 0 5px; letter-spacing:-.3px; font-weight:800; color:var(--text,#1e293b); }
  .hc-head p{ margin:0; color:var(--muted,#64748b); font-size:13.5px; max-width:640px; line-height:1.55; }
  .hc-head p b{ color:var(--ink-soft,#41506a); }
  .hc-eyebrow{
    font-size:11px; font-weight:700; letter-spacing:.1em; text-transform:uppercase;
    color:var(--accent,#2563eb); margin-bottom:8px; display:inline-flex; align-items:center; gap:7px;
  }
  .hc-eyebrow .bar{ width:18px; height:2px; background:var(--accent,#2563eb); border-radius:2px; }

  .hc-card{
    background:var(--card-bg,#fff); border:1px solid var(--border,#e2e8f0);
    border-radius:14px; box-shadow:0 1px 2px rgba(0,0,0,.05);
  }
  .hc-pad{ padding:22px 24px; }

  /* ---- Getting Started ---- */
  .hc-flow{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; }
  @media (max-width:900px){ .hc-flow{ grid-template-columns:1fr 1fr; } }
  .hc-step{
    background:var(--card-bg,#fff); border:1px solid var(--border,#e2e8f0); border-radius:13px;
    padding:18px 16px; position:relative;
  }
  .hc-step .num{
    width:34px; height:34px; border-radius:10px; color:#fff;
    display:grid; place-items:center; font-weight:800; font-size:16px; margin-bottom:12px;
    background:var(--accent,#2563eb);
  }
  .hc-step:nth-child(3) .num{ background:#c2731a; }
  .hc-step:nth-child(4) .num{ background:var(--success,#15803d); }
  .hc-step h4{ margin:0 0 5px; font-size:14.5px; font-weight:700; color:var(--text,#1e293b); }
  .hc-step p{ margin:0; font-size:12.5px; color:var(--muted,#64748b); line-height:1.5; }

  .hc-gs-about{ display:grid; grid-template-columns:1.5fr 1fr; gap:16px; margin-top:20px; }
  @media (max-width:900px){ .hc-gs-about{ grid-template-columns:1fr; } }
  .hc-gs-about h4{ margin:0 0 8px; font-size:15px; font-weight:700; }
  .hc-gs-about p{ margin:0; color:var(--ink-soft,#41506a); font-size:13.5px; line-height:1.65; }
  .hc-tour{
    background:var(--sidebar-bg,#0a0f1e); border:1px solid var(--border,#e2e8f0);
    color:#fff; display:flex; flex-direction:column; justify-content:center;
  }
  .hc-tour .hc-eyebrow{ color:#f6a723; }
  .hc-tour .hc-eyebrow .bar{ background:#f6a723; }
  .hc-tour h4{ color:#fff; }
  .hc-tour p{ color:var(--sidebar-ink,#c7d2e6); }
  .hc-btn{
    display:inline-flex; align-items:center; gap:9px; align-self:flex-start; margin-top:14px;
    background:#f6a723; color:#3a2600; border:none; font-weight:700; font-size:13.5px;
    padding:11px 18px; border-radius:10px; cursor:pointer; transition:transform .12s;
  }
  .hc-btn:hover{ transform:translateY(-1px); }
  .hc-btn svg{ width:15px; height:15px; }

  /* ---- Feature Guide ---- */
  .hc-fg-toolbar{ display:flex; align-items:center; gap:12px; margin-bottom:14px; flex-wrap:wrap; }
  .hc-search{ flex:1; min-width:220px; position:relative; }
  .hc-search svg{ position:absolute; left:13px; top:50%; transform:translateY(-50%); width:17px; height:17px; color:var(--muted,#64748b); }
  .hc-search input{
    width:100%; padding:12px 14px 12px 40px; border:1px solid var(--border,#e2e8f0); border-radius:11px;
    background:var(--card-bg,#fff); color:var(--text,#1e293b); font-size:13.5px; font-family:inherit;
  }
  .hc-search input:focus{ outline:none; border-color:var(--accent,#2563eb); box-shadow:0 0 0 3px var(--accent-soft,#dbe6ff); }
  .hc-search input::placeholder{ color:var(--muted,#64748b); }
  .hc-legend{ display:flex; gap:14px; align-items:center; font-size:12px; color:var(--muted,#64748b); flex-wrap:wrap; }
  .hc-lg{ display:inline-flex; align-items:center; gap:6px; font-weight:500; }
  .hc-lg .sw{ width:11px; height:11px; border-radius:3px; }
  .hc-lg .sw.p6{ background:var(--accent-soft,#dbe6ff); border:1px solid var(--accent,#2563eb); }
  .hc-lg .sw.extra{ background:rgba(194,115,26,.14); border:1px solid #c2731a; }
  .hc-fg-count{ font-size:12px; color:var(--muted,#64748b); margin-bottom:10px; font-weight:500; }
  .hc-fg-count b{ color:var(--text,#1e293b); }

  .hc-fg-grid{ display:grid; grid-template-columns:repeat(2,1fr); gap:12px; }
  @media (max-width:980px){ .hc-fg-grid{ grid-template-columns:1fr; } }
  .hc-feat{
    background:var(--card-bg,#fff); border:1px solid var(--border,#e2e8f0); border-radius:12px;
    padding:15px 16px; display:flex; flex-direction:column; gap:9px;
    transition:border-color .14s, transform .14s;
  }
  .hc-feat:hover{ border-color:var(--accent,#2563eb); transform:translateY(-1px); }
  .hc-feat.extra-needed{ border-left:3px solid #c2731a; }
  .hc-feat-top{ display:flex; align-items:baseline; justify-content:space-between; gap:8px; }
  .hc-feat-name{ font-weight:800; font-size:14.5px; letter-spacing:-.2px; color:var(--text,#1e293b); }
  .hc-feat-tag{
    font-size:10px; font-weight:700; letter-spacing:.05em; text-transform:uppercase;
    color:#c2731a; background:rgba(194,115,26,.12); border:1px solid rgba(194,115,26,.3);
    padding:2px 7px; border-radius:6px; white-space:nowrap;
  }
  .hc-feat-what{ font-size:12.5px; color:var(--muted,#64748b); line-height:1.5; margin:0; }
  .hc-feat-inputs{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-top:1px; }
  .hc-inp-label{ font-size:10.5px; font-weight:700; color:var(--muted,#64748b); text-transform:uppercase; letter-spacing:.05em; margin-right:2px; }
  .hc-chip{ font-size:11.5px; font-weight:600; padding:4px 10px; border-radius:999px; display:inline-flex; align-items:center; gap:5px; }
  .hc-chip::before{ content:""; width:6px; height:6px; border-radius:50%; }
  .hc-chip.p6{ background:var(--accent-soft,#dbe6ff); color:var(--accent-dark,#1d4ed8); border:1px solid var(--accent-soft,#dbe6ff); }
  .hc-chip.p6::before{ background:var(--accent,#2563eb); }
  .hc-chip.extra{ background:rgba(194,115,26,.12); color:#c2731a; border:1px solid rgba(194,115,26,.3); }
  .hc-chip.extra::before{ background:#c2731a; }
  .hc-chip.optional{ background:transparent; color:var(--muted,#64748b); border:1px dashed var(--border,#e2e8f0); }
  .hc-chip.optional::before{ background:var(--muted,#64748b); }
  .hc-fg-empty{ text-align:center; padding:40px; color:var(--muted,#64748b); font-size:13.5px; display:none; }
  .hc-fg-empty.show{ display:block; }

  /* ---- Shortcuts ---- */
  .hc-kb-list{ display:grid; grid-template-columns:1fr 1fr; gap:2px 34px; }
  @media (max-width:760px){ .hc-kb-list{ grid-template-columns:1fr; } }
  .hc-kb-row{ display:flex; align-items:center; justify-content:space-between; padding:12px 2px; border-bottom:1px solid var(--hair,#eef1f6); }
  .hc-kb-row .lbl{ font-size:13.5px; color:var(--ink-soft,#41506a); }
  .hc-keys{ display:inline-flex; gap:5px; }
  .hc-keys kbd{
    font-family:inherit; font-size:11.5px; font-weight:700;
    background:var(--bg,#eef2f7); border:1px solid var(--border,#e2e8f0); border-bottom-width:2px;
    border-radius:6px; padding:3px 8px; color:var(--text,#1e293b); min-width:22px; text-align:center;
  }

  /* ---- What's New ---- */
  .hc-wn{ display:flex; gap:14px; padding:16px 0; border-bottom:1px solid var(--hair,#eef1f6); }
  .hc-wn:last-child{ border-bottom:none; }
  .hc-wn-dot{ flex:none; width:40px; height:40px; border-radius:11px; display:grid; place-items:center; color:#fff; background:var(--accent,#2563eb); }
  .hc-wn-dot.amber{ background:#c2731a; }
  .hc-wn-dot.green{ background:var(--success,#15803d); }
  .hc-wn-dot svg{ width:19px; height:19px; }
  .hc-wn-body h4{ margin:0 0 3px; font-size:14.5px; font-weight:700; display:flex; align-items:center; gap:9px; flex-wrap:wrap; color:var(--text,#1e293b); }
  .hc-wn-body p{ margin:0; font-size:13px; color:var(--muted,#64748b); line-height:1.55; }
  .hc-ver-pill{ font-size:10.5px; font-weight:700; color:var(--accent-dark,#1d4ed8); background:var(--accent-soft,#dbe6ff); border-radius:5px; padding:2px 7px; letter-spacing:.03em; }

  /* ---- Contact ---- */
  .hc-contact-grid{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  @media (max-width:760px){ .hc-contact-grid{ grid-template-columns:1fr; } }
  .hc-cc{ background:var(--card-bg,#fff); border:1px solid var(--border,#e2e8f0); border-radius:13px; padding:18px; display:flex; flex-direction:column; gap:10px; }
  .hc-cc.lead{ border-color:var(--accent,#2563eb); }
  .hc-cc-head{ display:flex; align-items:center; gap:13px; }
  .hc-cc-avatar{ width:46px; height:46px; border-radius:12px; flex:none; display:grid; place-items:center; font-weight:800; font-size:16px; color:#fff; background:var(--accent,#2563eb); }
  .hc-cc-avatar.alt{ background:var(--success,#15803d); }
  .hc-cc-name{ font-size:15.5px; font-weight:800; color:var(--text,#1e293b); letter-spacing:-.2px; }
  .hc-cc-role{ font-size:12px; color:var(--muted,#64748b); margin-top:2px; }
  .hc-cc-rows{ display:flex; flex-direction:column; gap:8px; }
  .hc-cc-row{
    display:flex; align-items:center; gap:12px; text-decoration:none;
    padding:10px 12px; border-radius:10px; border:1px solid var(--hair,#eef1f6);
    background:var(--bg,#eef2f7); transition:border-color .12s, background .12s;
  }
  .hc-cc-row:hover{ border-color:var(--accent,#2563eb); }
  .hc-cc-ico{ width:34px; height:34px; border-radius:9px; flex:none; display:grid; place-items:center; background:var(--accent-soft,#dbe6ff); color:var(--accent,#2563eb); }
  .hc-cc-ico svg{ width:17px; height:17px; }
  .hc-cc-info{ min-width:0; }
  .hc-cc-info .k{ font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.06em; color:var(--muted,#64748b); margin-bottom:2px; }
  .hc-cc-info .v{ font-size:13.5px; font-weight:700; color:var(--text,#1e293b); word-break:break-word; }
  .hc-resp{
    display:flex; align-items:center; gap:10px; margin-top:16px;
    background:var(--success-bg,#dcf3e4); border:1px solid var(--border,#e2e8f0); border-radius:11px;
    padding:13px 16px; font-size:13px; color:var(--ink-soft,#41506a); font-weight:500;
  }
  .hc-resp .rdot{ width:9px; height:9px; border-radius:50%; flex:none; background:var(--success,#15803d); }

  /* ---- About ---- */
  .hc-about{ text-align:center; padding:44px 30px; position:relative; overflow:hidden; }
  .hc-about-bg{ position:absolute; inset:0; background:radial-gradient(120% 90% at 50% -20%, var(--accent-soft,#dbe6ff), transparent 60%); opacity:.6; pointer-events:none; }
  .hc-about-inner{ position:relative; }
  .hc-brandmark{ font-size:42px; font-weight:800; letter-spacing:-1px; margin-bottom:4px; color:var(--text,#1e293b); }
  .hc-brandmark .x{ color:var(--accent,#2563eb); }
  .hc-tagline{ font-size:13.5px; color:var(--muted,#64748b); font-weight:600; }
  .hc-forp6{ font-size:12px; color:var(--muted,#64748b); margin-top:3px; margin-bottom:16px; }
  .hc-ver{
    display:inline-flex; align-items:center; gap:8px; font-size:12px; font-weight:700;
    background:var(--card-bg,#fff); border:1px solid var(--border,#e2e8f0); border-radius:999px;
    padding:6px 14px; color:var(--ink-soft,#41506a); margin-bottom:20px;
  }
  .hc-ver .g{ width:7px; height:7px; border-radius:50%; background:var(--success,#15803d); }
  .hc-desc{ max-width:580px; margin:0 auto 24px; font-size:13.5px; color:var(--ink-soft,#41506a); line-height:1.7; }
  .hc-credit{ display:inline-block; background:var(--sidebar-bg,#0a0f1e); border:1px solid var(--border,#e2e8f0); border-radius:14px; padding:18px 32px; }
  .hc-credit .lead{ font-size:11px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; color:#f6a723; margin-bottom:6px; }
  .hc-credit .name{ font-size:23px; font-weight:800; color:#fff; letter-spacing:-.3px; }
  .hc-credit .role{ font-size:12px; color:var(--sidebar-ink,#c7d2e6); margin-top:3px; }
  .hc-copyright{ font-size:11.5px; color:var(--muted,#64748b); margin-top:22px; }

  @media (prefers-reduced-motion: reduce){
    #${OVERLAY_ID}, .hc-shell{ animation:none !important; }
    #${OVERLAY_ID} *{ transition:none !important; }
  }`;
  const s = document.createElement('style');
  s.id = STYLE_ID;
  s.textContent = css;
  document.head.appendChild(s);
}

// ---- Section content builders ----
function screenGettingStarted() {
  return `
  <section class="hc-screen" data-sec="getting-started">
    <div class="hc-head">
      <div class="hc-eyebrow"><span class="bar"></span>Getting Started</div>
      <h2>How Controlyx works</h2>
      <p>Controlyx reads your Primavera P6 exports and turns them into clear schedule intelligence — earned value, health checks, delay analysis and board-ready reports. No spreadsheets, no manual number-crunching. Follow four steps.</p>
    </div>
    <div class="hc-flow">
      <div class="hc-step"><div class="num">1</div><h4>Import</h4><p>Drag in a P6 XML/XER export, or Browse to it. Controlyx parses activities, WBS and logic.</p></div>
      <div class="hc-step"><div class="num">2</div><h4>Choose a feature</h4><p>Pick what you need — Earned Value, Schedule Health, Consultant Review and more.</p></div>
      <div class="hc-step"><div class="num">3</div><h4>Run</h4><p>Confirm the inputs and click Run. Every analysis is explicit — nothing fires until you ask.</p></div>
      <div class="hc-step"><div class="num">4</div><h4>Results</h4><p>Read the KPIs on screen, then export a polished one-page PDF or a custom report.</p></div>
    </div>
    <div class="hc-gs-about">
      <div class="hc-card hc-pad">
        <h4>What this tool does</h4>
        <p>Controlyx is a desktop project-control platform for planners and PMs. It computes Planned Value, Earned Value, SPI/CPI and delay in days; runs DCMA-style schedule health checks; performs forensic but-for delay analysis; and audits calendars, weather impact and constructability — all offline, entirely from your P6 files. Import once and every view reads from a local database, so re-opening a project is instant.</p>
      </div>
      <div class="hc-card hc-pad hc-tour">
        <div class="hc-eyebrow"><span class="bar"></span>New here?</div>
        <h4>Explore the feature guide</h4>
        <p>See every analysis Controlyx offers and the exact inputs each one needs.</p>
        <button class="hc-btn" type="button" data-goto="feature-guide">
          ${svg('<path d="m6 4 14 8-14 8z"/>', ' stroke-width="2.4"')}
          Browse features
        </button>
      </div>
    </div>
  </section>`;
}

function screenFeatureGuide() {
  return `
  <section class="hc-screen" data-sec="feature-guide">
    <div class="hc-head">
      <div class="hc-eyebrow"><span class="bar"></span>Feature Guide</div>
      <h2>What each feature needs</h2>
      <p>Every analysis in Controlyx and the exact inputs it expects. Most features need just <b>one P6 schedule</b>; a few compare files and need a second input — the amber chips flag those at a glance.</p>
    </div>
    <div class="hc-fg-toolbar">
      <div class="hc-search">
        ${svg('<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>')}
        <input id="hc-fg-search" type="text" placeholder="Search features or inputs — e.g. baseline, weather, SPI…" autocomplete="off">
      </div>
      <div class="hc-legend">
        <span class="hc-lg"><span class="sw p6"></span>1 P6 schedule</span>
        <span class="hc-lg"><span class="sw extra"></span>Extra file needed</span>
      </div>
    </div>
    <div class="hc-fg-count"><b id="hc-fg-shown">${FEATURES.length}</b> of ${FEATURES.length} features</div>
    <div class="hc-fg-grid" id="hc-fg-grid"></div>
    <div class="hc-fg-empty" id="hc-fg-empty">No features match your search. Try “baseline”, “delay” or “calendar”.</div>
  </section>`;
}

function screenShortcuts() {
  // Rows come straight from the shared SHORTCUTS registry (shortcuts.js) — the same
  // source app.js binds its key handler to — so this list can never drift from the
  // shortcuts that actually fire. Add/change a shortcut there and it shows up here.
  const rows = shortcutRows().map(([lbl, keys]) =>
    `<div class="hc-kb-row"><span class="lbl">${esc(lbl)}</span><span class="hc-keys">${
      keys.map(k => `<kbd>${esc(k)}</kbd>`).join('')
    }</span></div>`).join('');
  return `
  <section class="hc-screen" data-sec="shortcuts">
    <div class="hc-head">
      <div class="hc-eyebrow"><span class="bar"></span>Keyboard Shortcuts</div>
      <h2>Work faster</h2>
      <p>A handful of shortcuts for the actions you use most.</p>
    </div>
    <div class="hc-card hc-pad"><div class="hc-kb-list">${rows}</div></div>
  </section>`;
}

function screenWhatsNew() {
  return `
  <section class="hc-screen" data-sec="whats-new">
    <div class="hc-head">
      <div class="hc-eyebrow"><span class="bar"></span>What's New</div>
      <h2>Recent highlights</h2>
      <p>The latest improvements shipped in Controlyx 2026.</p>
    </div>
    <div class="hc-card hc-pad">
      <div class="hc-wn">
        <div class="hc-wn-dot">${svg('<path d="M22 11.5V12a10 10 0 1 1-5.9-9.1"/><path d="m9 11 3 3L22 4"/>')}</div>
        <div class="hc-wn-body">
          <h4>Explicit choose-feature → Run workflow <span class="hc-ver-pill">v2.2.0</span></h4>
          <p>Importing a file no longer auto-runs anything. You pick a feature, confirm its inputs, then Run — clearer intent and no surprise recalculations.</p>
        </div>
      </div>
      <div class="hc-wn">
        <div class="hc-wn-dot amber">${svg('<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>')}</div>
        <div class="hc-wn-body">
          <h4>Reorganised Project Navigator</h4>
          <p>Recent Projects now lives on its own page and the sidebar groups Home, History and Database — less clutter, faster switching between schedules.</p>
        </div>
      </div>
      <div class="hc-wn">
        <div class="hc-wn-dot green">${svg('<path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"/>')}</div>
        <div class="hc-wn-body">
          <h4>Branded startup splash</h4>
          <p>A polished Controlyx splash screen greets you on launch while your database and knowledge base load in the background.</p>
        </div>
      </div>
    </div>
  </section>`;
}

function screenContact() {
  const phoneIco = svg('<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3.1-8.6A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.4-1.2a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>');
  const inIco = svg('<rect x="2" y="3" width="20" height="18" rx="2"/><path d="M7 10v7M7 7v.01M12 17v-4a2 2 0 0 1 4 0v4M16 17v-2"/>');
  return `
  <section class="hc-screen" data-sec="contact">
    <div class="hc-head">
      <div class="hc-eyebrow"><span class="bar"></span>Contact &amp; Support</div>
      <h2>Get help</h2>
      <p>Questions, feature requests or a bug to report — here's how to reach the team.</p>
    </div>
    <div class="hc-contact-grid">
      <div class="hc-cc lead">
        <div class="hc-cc-head">
          <div class="hc-cc-avatar">IG</div>
          <div><div class="hc-cc-name">Ibrahim Gebril</div><div class="hc-cc-role">Creator of Controlyx</div></div>
        </div>
        <div class="hc-cc-rows">
          <a class="hc-cc-row" href="https://www.linkedin.com/in/ibrahim-gebril-417a40270/" target="_blank" rel="noopener">
            <span class="hc-cc-ico">${inIco}</span>
            <span class="hc-cc-info"><span class="k">LinkedIn</span><span class="v">linkedin.com/in/ibrahim-gebril</span></span>
          </a>
          <a class="hc-cc-row" href="tel:+201096570066">
            <span class="hc-cc-ico">${phoneIco}</span>
            <span class="hc-cc-info"><span class="k">Phone</span><span class="v">+20 109 657 0066</span></span>
          </a>
        </div>
      </div>
      <div class="hc-cc">
        <div class="hc-cc-head">
          <div class="hc-cc-avatar alt">MA</div>
          <div><div class="hc-cc-name">Mustafa Agamy</div><div class="hc-cc-role">Technical Software Support</div></div>
        </div>
        <div class="hc-cc-rows">
          <a class="hc-cc-row" href="tel:+201012564657">
            <span class="hc-cc-ico">${phoneIco}</span>
            <span class="hc-cc-info"><span class="k">Phone</span><span class="v">+20 101 256 4657</span></span>
          </a>
        </div>
      </div>
    </div>
    <div class="hc-resp"><span class="rdot"></span>We usually respond within 2 days.</div>
  </section>`;
}

function screenAbout() {
  return `
  <section class="hc-screen" data-sec="about">
    <div class="hc-card hc-about">
      <div class="hc-about-bg"></div>
      <div class="hc-about-inner">
        <div class="hc-brandmark">Controly<span class="x">x</span></div>
        <div class="hc-tagline">Controlyx 2026 · Project Control Intelligence Platform</div>
        <div class="hc-forp6">for Primavera P6</div>
        <div class="hc-ver"><span class="g"></span>Version 2.2.0 · 2026 Edition</div>
        <p class="hc-desc">Controlyx turns Primavera P6 exports into clear, board-ready schedule intelligence — earned value, DCMA-style health checks, forensic delay analysis, calendar and weather audits, and custom reports — all computed offline on your machine, straight from your project files.</p>
        <div class="hc-credit">
          <div class="lead">Designed &amp; Developed by</div>
          <div class="name">Ibrahim Gebril</div>
          <div class="role">Construction Planning Engineer · Creator of Controlyx</div>
        </div>
        <div class="hc-copyright">© 2026 Ibrahim Gebril. All rights reserved.</div>
      </div>
    </div>
  </section>`;
}

function allScreens() {
  return screenGettingStarted() + screenFeatureGuide() + screenShortcuts() +
    screenWhatsNew() + screenContact() + screenAbout();
}

// ---- Feature Guide render + live search ----
function chipHtml(inp) {
  let cls = 'hc-chip ';
  let label = esc(inp.t);
  if (inp.k === 'extra') cls += 'extra';
  else if (inp.k === 'optional') { cls += 'optional'; label = 'optional: ' + label; }
  else if (inp.k === 'none') cls += 'optional';
  else cls += 'p6';
  return '<span class="' + cls + '">' + label + '</span>';
}

function renderFeatures(root, filter) {
  const grid = root.querySelector('#hc-fg-grid');
  const empty = root.querySelector('#hc-fg-empty');
  const shownEl = root.querySelector('#hc-fg-shown');
  if (!grid) return;
  const q = (filter || '').trim().toLowerCase();
  let shown = 0;
  let html = '';
  FEATURES.forEach(f => {
    const hay = (f.name + ' ' + f.what + ' ' + f.inputs.map(i => i.t).join(' ')).toLowerCase();
    if (q && hay.indexOf(q) === -1) return;
    shown++;
    const tag = f.extra ? '<span class="hc-feat-tag">2 files</span>' : '';
    const chips = f.inputs.map(chipHtml).join('');
    html +=
      '<div class="hc-feat' + (f.extra ? ' extra-needed' : '') + '">' +
        '<div class="hc-feat-top"><span class="hc-feat-name">' + esc(f.name) + '</span>' + tag + '</div>' +
        '<p class="hc-feat-what">' + esc(f.what) + '</p>' +
        '<div class="hc-feat-inputs"><span class="hc-inp-label">Needs</span>' + chips + '</div>' +
      '</div>';
  });
  grid.innerHTML = html;
  if (shownEl) shownEl.textContent = String(shown);
  if (empty) empty.classList.toggle('show', shown === 0);
}

// ---- Open / close ----
function selectSection(root, key) {
  const sec = VALID.has(key) ? key : DEFAULT_SECTION;
  root.querySelectorAll('.hc-nav-item').forEach(it =>
    it.classList.toggle('active', it.getAttribute('data-sec') === sec));
  root.querySelectorAll('.hc-screen').forEach(s =>
    s.classList.toggle('show', s.getAttribute('data-sec') === sec));
  const content = root.querySelector('.hc-content');
  if (content) content.scrollTop = 0;
  if (sec === 'feature-guide') {
    const box = root.querySelector('#hc-fg-search');
    if (box) setTimeout(() => { try { box.focus(); } catch (e) {} }, 0);
  }
}

export function closeHelp() {
  const ov = document.getElementById(OVERLAY_ID);
  if (ov && ov.parentNode) ov.parentNode.removeChild(ov);
  if (onKeyDown) { document.removeEventListener('keydown', onKeyDown, true); onKeyDown = null; }
}

/**
 * Open the Help Center overlay at a given section.
 *   section ∈ 'getting-started' | 'feature-guide' | 'shortcuts' | 'whats-new' | 'contact' | 'about'
 *   default 'feature-guide'. If the overlay is already open, this just switches section
 *   (it never stacks a second overlay).
 */
export function openHelp(section) {
  const sec = VALID.has(section) ? section : DEFAULT_SECTION;
  injectStyle();

  // Already open → just switch section, don't stack.
  const existing = document.getElementById(OVERLAY_ID);
  if (existing) { selectSection(existing, sec); return; }

  const navItems = SECTIONS.map(s =>
    `<button class="hc-nav-item" type="button" data-sec="${s.key}">
       <span class="hc-nav-ico">${svg(s.icon)}</span>
       <span class="hc-nav-txt"><span class="t">${esc(s.label)}</span><span class="s">${esc(s.sub)}</span></span>
     </button>`).join('');

  const overlay = document.createElement('div');
  overlay.id = OVERLAY_ID;
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.setAttribute('aria-label', 'Help Center');
  overlay.innerHTML = `
    <div class="hc-shell" role="document">
      <div class="hc-titlebar">
        <span class="hc-tb-logo">C</span>
        <span class="hc-tb-title">Help Center</span>
        <span class="hc-tb-spacer"></span>
        <button class="hc-close" type="button" aria-label="Close Help Center" title="Close (Esc)">
          ${svg('<path d="M18 6 6 18M6 6l12 12"/>')}
        </button>
      </div>
      <div class="hc-body">
        <nav class="hc-nav">
          ${navItems}
          <div class="hc-nav-foot">Controlyx 2026 · v2.2.0</div>
        </nav>
        <div class="hc-content">${allScreens()}</div>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  // Nav clicks switch section.
  overlay.querySelectorAll('.hc-nav-item').forEach(it => {
    it.addEventListener('click', () => selectSection(overlay, it.getAttribute('data-sec')));
  });

  // "Browse features" button on Getting Started → jump to the Feature Guide.
  overlay.querySelectorAll('[data-goto]').forEach(b => {
    b.addEventListener('click', () => selectSection(overlay, b.getAttribute('data-goto')));
  });

  // Live search on the Feature Guide.
  const box = overlay.querySelector('#hc-fg-search');
  if (box) box.addEventListener('input', () => renderFeatures(overlay, box.value));
  renderFeatures(overlay, '');

  // Close: ✕ button and clicking the scrim (outside the shell).
  const closeBtn = overlay.querySelector('.hc-close');
  if (closeBtn) closeBtn.addEventListener('click', closeHelp);
  overlay.addEventListener('mousedown', e => { if (e.target === overlay) closeHelp(); });

  // Close: Esc.
  onKeyDown = e => {
    if (e.key === 'Escape' || e.key === 'Esc') { e.stopPropagation(); e.preventDefault(); closeHelp(); }
  };
  document.addEventListener('keydown', onKeyDown, true);

  selectSection(overlay, sec);
  if (closeBtn) { try { closeBtn.focus(); } catch (e) {} }
}

export default openHelp;
