// Startup splash — plays once when the app window opens, then fades away to reveal
// the real app shell beneath it. Motion identity shared with featurereveal.js:
// a schedule builds → a glowing critical path rises → it resolves into the brand mark
// → the wordmark writes in → the splash lifts to reveal the app. Self-contained (injects
// its own CSS + overlay DOM); call playBoot() once from app.js on load.
//
// Honest progress (startup audit BLACK-9): the caption and the bar follow the REAL
// start-up steps the startup guard (ui/startup_guard.js, window.__cxStartup) records —
// local server answered (/api/health), program files loaded, screen built, project
// history answered. The owner's 11-s presentation (#07/#83, no Skip) keeps its length,
// but the bar is held at the first step not yet done and 'Ready' only shows once every
// step really happened. If the start fails (the guard reloads or shows its Retry card)
// the splash steps aside at once instead of finishing into an empty shell.
// The product name comes from window.__APP_NAME__ / __APP_EDITION__ / __APP_TITLE__
// (server.py injects them from utils.APP_*), never written here (VER-2).

let injected = false;

function injectCss() {
  if (injected) return; injected = true;
  const css = `
  #boot{position:fixed; inset:0; z-index:99999; overflow:hidden; opacity:1;
    background:radial-gradient(125% 95% at 50% 40%, #14284f 0%, #0a1330 42%, #06090f 100%);
    display:grid; place-items:center; transition:opacity .28s ease; will-change:opacity;
    font-family:"Segoe UI",system-ui,-apple-system,sans-serif;}
  #boot.gone{opacity:0; pointer-events:none;}
  #boot .grid{position:absolute; inset:0; opacity:.7;
    background-image:linear-gradient(rgba(120,150,220,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(120,150,220,.05) 1px,transparent 1px);
    background-size:44px 44px; -webkit-mask:radial-gradient(circle at 50% 44%,#000 30%,transparent 78%); mask:radial-gradient(circle at 50% 44%,#000 30%,transparent 78%);}
  #boot .vig{position:absolute; inset:0; pointer-events:none; box-shadow:inset 0 0 240px 40px rgba(3,5,12,.9);}
  #boot .stagewrap{position:relative; width:min(860px,92vw); height:min(430px,52vh);}
  #boot svg.stage{position:absolute; inset:0; width:100%; height:100%; overflow:visible;}
  #boot .wm{position:absolute; left:50%; top:calc(50% + 118px); transform:translate(-50%,0); text-align:center; opacity:0;}
  #boot .wm .nm{font-family:Archivo,"Segoe UI",system-ui; font-weight:800; font-size:46px; letter-spacing:.02em; line-height:1; white-space:nowrap;
    color:#fff; -webkit-text-fill-color:transparent; -webkit-background-clip:text; background-clip:text;
    background-image:linear-gradient(90deg,#fff 0%,#dfe8ff 60%,#bcd2ff 100%);
    filter:drop-shadow(0 2px 18px rgba(91,155,255,.35)); clip-path:inset(0 100% 0 0);}
  #boot .wm .nm .yr{-webkit-text-fill-color:#5b9bff; color:#5b9bff; font-size:.42em; font-weight:700; letter-spacing:.02em; margin-left:.26em; vertical-align:.62em;}
  #boot .wm .tg{margin-top:10px; font-size:11px; letter-spacing:.22em; text-transform:uppercase; color:#8a99bd; font-weight:600; white-space:nowrap;}
  #boot .wm .p6{margin-top:7px; font-size:9.5px; letter-spacing:.16em; text-transform:uppercase; color:#5f6d8f; font-weight:600; white-space:nowrap;}
  #boot .wm .p6 em{font-style:normal; color:#7f8fb3;}
  #boot .hud{position:absolute; left:50%; bottom:8%; transform:translateX(-50%); width:min(440px,74vw); text-align:center;}
  #boot .cap{display:flex; justify-content:space-between; font-size:12px; letter-spacing:.12em; text-transform:uppercase; color:#9fb0d6; font-weight:600; margin-bottom:9px;}
  #boot .cap b{color:#fff; font-variant-numeric:tabular-nums; font-family:Archivo,"Segoe UI",system-ui;}
  #boot .track{height:3px; border-radius:3px; background:rgba(120,150,220,.16); overflow:hidden;}
  #boot .barf{height:100%; width:0%; border-radius:3px; background:linear-gradient(90deg,#f6a723,#5b9bff); box-shadow:0 0 12px rgba(91,155,255,.6);}
  #boot .ver{position:absolute; left:0; right:0; bottom:20px; text-align:center; color:#556488; font-size:10.5px; letter-spacing:.28em; text-transform:uppercase;}
  #boot .skip{position:absolute; top:16px; right:16px; z-index:2; display:inline-flex; align-items:center; gap:6px;
    background:rgba(255,255,255,.06); color:#cdd8f0; border:1px solid rgba(255,255,255,.14); border-radius:20px;
    padding:6px 13px; font:600 12px/1 "Segoe UI",system-ui; cursor:pointer;}
  #boot .skip:hover{background:rgba(255,255,255,.12); color:#fff;}
  @media (prefers-reduced-motion: reduce){ #boot{transition:opacity .3s ease;} }`;
  const s = document.createElement('style'); s.id = 'boot-style'; s.textContent = css;
  document.head.appendChild(s);
}

const clamp = (x, a, b) => { a = a == null ? 0 : a; b = b == null ? 1 : b; return x < a ? a : x > b ? b : x; };
const ease = x => x <= 0 ? 0 : x >= 1 ? 1 : 1 - Math.pow(1 - x, 3);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const nb = s => esc(s).replace(/ /g, '&nbsp;');

// The real start-up steps, in the order they happen (keys match the guard's steps).
export const BOOT_STEPS = [
  ['server',  'Starting local server'],
  ['program', 'Loading program files'],
  ['screen',  'Building the screen'],
  ['history', 'Opening project history'],
];

// Caption + bar for timeline position t (0..1 of the 11-s presentation) given the steps
// really done. The bar follows the timeline but never passes the first step not yet done;
// the caption names the step the bar is on; 'Ready' only at 100 %, i.e. all steps done.
export function bootProgress(t, steps) {
  steps = steps || {};
  const n = BOOT_STEPS.length;
  let done = 0;
  while (done < n && steps[BOOT_STEPS[done][0]]) done++;
  const timeProg = clamp((t - 0.03) / 0.86);
  const prog = Math.min(timeProg, done / n);
  const ready = done === n && prog >= 1;
  const label = ready ? 'Ready' : BOOT_STEPS[Math.min(Math.floor(prog * n + 1e-9), done, n - 1)][1];
  return { prog, pct: Math.round(prog * 100), label, ready, held: timeProg > done / n };
}

// What the splash does now: 'finish' (lift it to show the app), 'abort' (step aside at once
// — the guard is reloading or shows its Retry card) or 'wait'. timelineDone = the
// presentation has played; capped = its hard cap has passed. Without a guard (a page served
// without it) the splash behaves as a plain timed presentation.
export function bootDecision(guard, timelineDone, capped) {
  if (!guard) return timelineDone ? 'finish' : 'wait';
  if (guard.phase === 'retrying' || guard.phase === 'failed') return 'abort';
  if (guard.phase !== 'ready') return 'wait';                 // still loading / 'Still starting…'
  if (timelineDone && bootProgress(1, guard.steps).ready) return 'finish';
  // Project history slower than the whole presentation: the screen is built and the
  // Recent Projects table says its own state (loading / Retry) — don't hold the app.
  return capped ? 'finish' : 'wait';
}

function brand() {
  const w = typeof window !== 'undefined' ? window : {};
  const name = w.__APP_NAME__ || '';
  const edition = w.__APP_EDITION__ || '';
  const title = w.__APP_TITLE__ || [name, edition].filter(Boolean).join(' ');
  return { name, edition, title };
}

export function playBoot(opts) {
  opts = opts || {};
  const DUR = opts.durationMs || 11000;
  const onDone = typeof opts.onDone === 'function' ? opts.onDone : function () {};
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const guard = window.__cxStartup || null;
  const B = brand();
  injectCss();

  const boot = document.createElement('div');
  boot.id = 'boot';
  boot.innerHTML =
    `<div class="grid"></div><div class="vig"></div>
     <div class="stagewrap">
       <svg class="stage" viewBox="0 0 860 430" preserveAspectRatio="xMidYMid meet">
         <defs>
           <linearGradient id="bootmg" x1="0" y1="1" x2="1" y2="0">
             <stop offset="0" stop-color="#f6a723"/><stop offset=".55" stop-color="#4f8cf0"/><stop offset="1" stop-color="#5b9bff"/>
           </linearGradient>
           <filter id="bootglow" x="-40%" y="-40%" width="180%" height="180%">
             <feGaussianBlur stdDeviation="3.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
           </filter>
         </defs>
         <g class="bars"></g>
         <path class="cpath" fill="none" stroke="#5b9bff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
               pathLength="100" filter="url(#bootglow)" opacity="0" d="M60 300 L170 286 L300 250 L430 222 L560 176 L700 120"/>
         <g class="markg" opacity="0" filter="url(#bootglow)" transform="translate(300,86) scale(11.4)">
           <path class="mark" d="M4 19V5M4 15l5-5 4 3 7-8" fill="none" stroke="url(#bootmg)" stroke-width="2.05"
                 stroke-linecap="round" stroke-linejoin="round" pathLength="100"/>
         </g>
         <circle class="spark" r="5.5" fill="#fff" opacity="0"/>
       </svg>
       <div class="wm"><div class="nm">${esc(B.name)}<span class="yr">${esc(B.edition)}</span></div><div class="tg">Project&nbsp;Control&nbsp;Intelligence&nbsp;Platform</div><div class="p6">for&nbsp;<em>Primavera&nbsp;P6</em>&nbsp;·&nbsp;XER&nbsp;&amp;&nbsp;XML</div></div>
     </div>
     <div class="hud"><div class="cap"><span class="capt">${BOOT_STEPS[0][1]}</span><b class="pct">0%</b></div>
       <div class="track"><div class="barf"></div></div></div>
     <div class="ver">${nb(B.title)} · Project&nbsp;Control&nbsp;Intelligence&nbsp;Platform</div>`;
  document.body.appendChild(boot);
  // We are now the single startup splash — drop the immediate anti-flash cover.
  const _cover = document.getElementById('brand-splash');
  if (_cover && _cover.parentNode) _cover.parentNode.removeChild(_cover);

  const $ = s => boot.querySelector(s);
  const barsG = $('.bars'), cp = $('.cpath'), markg = $('.markg'), mark = $('.mark'),
        spark = $('.spark'), wm = $('.wm'), nm = $('.nm'), barf = $('.barf'), pct = $('.pct'), capt = $('.capt');

  // Deterministic faux-schedule bars (rows).
  let seed = 1; const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
  const BARS = [];
  for (let r = 0; r < 7; r++) {
    let x = 70; const n = 2 + Math.floor(rnd() * 3);
    for (let k = 0; k < n; k++) { const w = 60 + rnd() * 150; x += rnd() * 30; if (x + w > 780) break; BARS.push({ x, y: 70 + r * 44, w, crit: rnd() > 0.72 }); x += w + 14; }
  }
  const barEls = BARS.map((b, i) => {
    const el = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    el.setAttribute('x', b.x); el.setAttribute('y', b.y); el.setAttribute('height', 12); el.setAttribute('rx', 3.5);
    el.setAttribute('fill', b.crit ? '#3f6bd6' : '#2c3c5e'); barsG.appendChild(el);
    b.appear = 0.03 + i * (0.30 / BARS.length); return el;
  });

  function render(t) {
    t = clamp(t, 0, 1);
    const barFade = ease(clamp((t - 0.50) / 0.14));
    for (let i = 0; i < BARS.length; i++) {
      const b = BARS[i], p = ease(clamp((t - b.appear) / 0.09));
      barEls[i].setAttribute('width', (b.w * p).toFixed(1));
      barEls[i].setAttribute('opacity', (p * (1 - barFade) * 0.92).toFixed(3));
    }
    const cpp = ease(clamp((t - 0.28) / 0.22));
    cp.setAttribute('opacity', (clamp((t - 0.26) / 0.06) * (1 - barFade)).toFixed(3));
    cp.setAttribute('stroke-dasharray', '100 100'); cp.setAttribute('stroke-dashoffset', (100 - cpp * 100).toFixed(2));
    const mp = ease(clamp((t - 0.50) / 0.22));
    markg.setAttribute('opacity', clamp((t - 0.50) / 0.06).toFixed(3));
    mark.setAttribute('stroke-dasharray', '100 100'); mark.setAttribute('stroke-dashoffset', (100 - mp * 100).toFixed(2));
    const ms = 1 + (reduce ? 0.02 : 0.06) * (1 - ease(clamp((t - 0.72) / 0.16)));
    markg.setAttribute('transform', 'translate(300,86) scale(' + (11.4 * ms).toFixed(3) + ')');
    spark.setAttribute('cx', 300 + 20 * 11.4); spark.setAttribute('cy', 86 + 5 * 11.4);
    spark.setAttribute('opacity', (clamp((mp - 0.55) / 0.3) * (0.5 + 0.5 * Math.abs(Math.sin(t * 22)))).toFixed(3));
    const wp = ease(clamp((t - 0.66) / 0.18));
    wm.style.opacity = wp.toFixed(3); wm.style.transform = 'translate(-50%,' + ((1 - wp) * 10).toFixed(1) + 'px)';
    nm.style.clipPath = 'inset(0 ' + ((1 - wp) * 100).toFixed(1) + '% 0 0)';
    // Caption + bar from the REAL steps (held at the first one not yet done).
    const p = bootProgress(t, guard ? guard.steps : null);
    barf.style.width = (p.prog * 100).toFixed(1) + '%'; pct.textContent = p.pct + '%';
    if (capt.textContent !== p.label) capt.textContent = p.label;
    // The splash stays fully opaque through the presentation; finish() does one quick
    // crisp fade so the app appears the instant loading completes (no slow blur).
  }

  let raf = null, start = null, finished = false, lastT = 0, timelineDone = false, capped = false;
  let unlisten = null;
  function finish() {
    if (finished) return; finished = true;
    if (raf) cancelAnimationFrame(raf);
    if (unlisten) unlisten();
    render(Math.max(lastT, 0.9));             // the frame it lifts on says where start-up got to
    boot.classList.add('gone');
    setTimeout(() => { if (boot.parentNode) boot.parentNode.removeChild(boot); }, 320);
    try { onDone(); } catch (e) {}
  }
  // The start failed: the guard is reloading the page or shows its Retry card — step aside
  // now rather than play on (or finish) over an empty shell.
  function abort() {
    if (finished) return; finished = true;
    if (raf) cancelAnimationFrame(raf);
    if (unlisten) unlisten();
    if (boot.parentNode) boot.parentNode.removeChild(boot);
  }
  function decide() {
    if (finished) return true;
    const d = bootDecision(guard, timelineDone, capped);
    if (d === 'finish') finish(); else if (d === 'abort') abort();
    return finished;
  }
  // #07: the startup presentation plays in full — no Skip button, by request.

  render(0);
  function step(ts) {
    if (finished) return;
    if (start == null) start = ts;
    const t = (ts - start) / DUR;
    lastT = t;
    render(t);
    // Lift right after the bar hits 100% + the mark/wordmark settle (~t 0.89) — once every
    // real step is done; until then hold on the step still running (the guard's
    // 'Still starting…' / Retry takes over if it stalls or fails).
    if (t >= 0.9) timelineDone = true;
    if (!decide()) raf = requestAnimationFrame(step);
  }
  raf = requestAnimationFrame(step);
  if (guard && typeof guard.onChange === 'function') unlisten = guard.onChange(() => decide());
  decide();                                   // a start that already failed: step aside now
  // Safety: if rAF is throttled (hidden window), never trap the user — hard cap.
  setTimeout(() => { if (finished) return; timelineDone = true; capped = true; decide(); }, DUR + 1500);
}
