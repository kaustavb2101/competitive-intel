#!/usr/bin/env node
/* VISUAL OVERFLOW AUDIT — the standing check for "text bleeding out of its box".
 *
 * Why this exists: on 2026-08-02 the owner caught two overflow bugs by eye that no gate could see —
 * a gloss line running out through the right edge of a rounded chip (it had inherited
 * white-space:nowrap from its parent), and a paragraph clipped mid-sentence. `node --check` reads
 * syntax, the determinism gate reads bytes, and neither of them lays out a single pixel. This does.
 *
 * WHAT IT FLAGS, and why each one is a real defect rather than a style opinion:
 *   BLEED    an element's ink extends past its own padding box on a container that does not scroll.
 *            The text is physically outside the border the reader sees. Always a bug.
 *   CLIP     an element is overflow:hidden / text-overflow:ellipsis AND its content does not fit, so
 *            a sentence ends in "…" and cannot be finished. Deliberate one-line truncation on a
 *            table cell is fine; a clipped PARAGRAPH is not, so only block text is reported.
 *   PAGEX    the document itself scrolls sideways at this viewport. The house rule is that wide
 *            content scrolls inside its own container and the body never does.
 *   COLLIDE  two siblings that should stack visibly overlap.
 *
 * WHAT IT DELIBERATELY IGNORES: anything inside an element that legitimately scrolls
 * (overflow-x:auto — tables, code, the resale chart on a phone), off-screen/aria-hidden nodes,
 * zero-size nodes, and SVG internals (an SVG's own coordinate system is not CSS layout).
 *
 * Usage:  node tests/visual_overflow.js [--viewports=1440,900;390,844]
 *         Self-serves platform/ and drives the pre-provisioned headless chromium DIRECTLY (chrome
 *         CLI --dump-dom, the exact zero-dependency approach tests/lib/render.sh already uses), so
 *         it needs no `npm i playwright` and no external server. 2026-09-14: this was the one QA
 *         script still gated behind the playwright npm package that the harness RETIRED as a
 *         dependency on 2026-08-01 (see tests/package.json) — so it self-skipped (exit 2) in the
 *         determinism-gate / CI / autonomous-loop environment where node_modules is absent, and the
 *         standing layout audit only ever ran hand-driven. Rewiring it to the provisioned chromium
 *         lets `bash tests/run.sh overflow` actually run the audit there.
 * Exit 0 = clean, 1 = findings (overflow / console errors / a route that could not be audited),
 *          2 = could not run at all (no chromium under /opt/pw-browsers).
 */
const ROUTES = [
  ['home', '/index.html#home'],
  ['macro', '/index.html#overview'],
  ['trend', '/index.html#trend'],
  ['competition', '/index.html#acq'],
  ['exposure', '/index.html#exposure'],
  ['assistance', '/index.html#assist'],
  ['simulator', '/index.html#sim'],
  ['provinces', '/index.html#provinces'],
  ['market', '/index.html#market'],
  ['branches', '/index.html#branches'],
  ['databook', '/data.html'],
  ['live', '/live.html'],
  ['status', '/status.html'],
];
// Phone first: almost every overflow bug shows there first, and the desktop width is where the
// owner actually reviews. A mid-band 1000px is added because several bleed classes only appear at
// the tablet width where a desktop 2-col grid has collapsed but the phone stack has not yet — the
// two-viewport default (1440 / 390) stepped straight over it.
const DEFAULT_VIEWPORTS = [[1440, 900], [1000, 800], [390, 844]];
const TOLERANCE = 2; // px — sub-pixel rounding and 1px borders are not findings

const vpArg = process.argv.find(a => a.startsWith('--viewports='));
const VIEWPORTS = vpArg
  ? vpArg.slice(12).split(';').map(s => s.split(',').map(Number))
  : DEFAULT_VIEWPORTS;

const AUDIT = /* js */ `(tol => {
  const out = [];
  const scrolls = el => {
    const s = getComputedStyle(el);
    return /auto|scroll/.test(s.overflowX) || /auto|scroll/.test(s.overflowY);
  };
  const visible = el => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) return false;
    if (el.closest('[hidden],[aria-hidden="true"]')) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };
  const path = el => {
    const bits = [];
    for (let n = el; n && n.nodeType === 1 && bits.length < 4; n = n.parentElement) {
      bits.unshift(n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') +
        (n.classList.length ? '.' + [...n.classList].slice(0, 2).join('.') : ''));
    }
    return bits.join(' > ');
  };
  const txt = el => (el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 90);

  // PAGEX — the body must never scroll sideways
  const de = document.documentElement;
  if (de.scrollWidth > de.clientWidth + tol) {
    out.push({ kind: 'PAGEX', sel: 'html', text: '',
      detail: de.scrollWidth + 'px of content in a ' + de.clientWidth + 'px viewport' });
  }

  const all = [...document.querySelectorAll('body *')].filter(el => !el.closest('svg') && visible(el));

  // A parent whose child overflows reports the same overflow, so a single bad chip lights up its
  // whole ancestor chain. Only the INNERMOST element on each chain is a finding — that is the one
  // whose CSS has to change. An ancestor is suppressed when a descendant already reported at least
  // as much overflow on the same axis.
  // Content inside a scrolling container is REACHABLE, not lost — a wide table inside an
  // overflow-x:auto wrapper is the house pattern, not a defect. So an element is only bleeding if
  // nothing between it and <body> can scroll it into view.
  const inScroller = el => {
    for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
      if (scrolls(n)) return true;
    }
    return false;
  };

  const bled = new Map();  // element -> {x, y}
  for (const el of all) {
    if (scrolls(el) || inScroller(el)) continue;
    const s = getComputedStyle(el);
    const dx = el.scrollWidth - el.clientWidth;
    const dy = el.scrollHeight - el.clientHeight;
    const hidesX = /hidden|clip/.test(s.overflowX), hidesY = /hidden|clip/.test(s.overflowY);
    bled.set(el, { x: (dx > tol && !hidesX) ? dx : 0, y: (dy > tol && !hidesY) ? dy : 0, s });
  }
  // A scrollWidth/clientWidth delta is arithmetic, not evidence: both are integers rounded from a
  // fractional layout, so a flex/grid row on sub-pixel boundaries reports a phantom few px every
  // time. Before reporting a horizontal bleed, confirm geometrically that something is actually
  // sticking out — a descendant box or a run of text with ink past the padding edge. Both edges are
  // checked so a negative margin or an RTL run still counts.
  const inkOverflowsX = el => {
    const cs = bled.get(el).s, r = el.getBoundingClientRect();
    const padL = r.left + (parseFloat(cs.borderLeftWidth) || 0);
    const padR = r.right - (parseFloat(cs.borderRightWidth) || 0);
    const slack = 1;                                   // one device pixel for antialiasing
    for (const k of el.querySelectorAll('*')) {
      const kr = k.getBoundingClientRect();
      if (!kr.width && !kr.height) continue;           // display:none / empty — no ink
      if (kr.right > padR + slack || kr.left < padL - slack) return true;
    }
    const rng = document.createRange();
    rng.selectNodeContents(el);
    for (const tr of rng.getClientRects()) {
      if (tr.right > padR + slack || tr.left < padL - slack) return true;
    }
    return false;
  };
  const coveredByChild = (el, axis) => {
    for (const [other, v] of bled) {
      if (other !== el && el.contains(other) && v[axis] >= (bled.get(el)[axis] - tol)) return true;
    }
    return false;
  };
  for (const [el, v] of bled) {
    const s = v.s;
    if (v.x > 0 && !coveredByChild(el, 'x') && inkOverflowsX(el)) {
      out.push({ kind: 'BLEED', sel: path(el), text: txt(el),
        detail: 'content is ' + v.x + 'px wider than its box (white-space:' + s.whiteSpace + ')' });
    } else if (v.y > 0 && !coveredByChild(el, 'y') && s.display !== 'inline' && el.children.length === 0
               // Only a CONTAINED vertical overflow loses the reader anything. IBM Plex Sans Thai has
               // Thai vertical metrics (two mark levels up, one down), so its natural line box is
               // ~1.5em for every string it sets — under that, every text node in the app reports a
               // few px of "overflow" that is simply leading and renders in full.
               && (/hidden|clip|auto|scroll/.test(s.overflowY)
                   || (s.webkitLineClamp && s.webkitLineClamp !== 'none')
                   || s.height !== 'auto' && /px$/.test(s.height) && s.maxHeight !== 'none')) {
      out.push({ kind: 'BLEED', sel: path(el), text: txt(el),
        detail: 'content is ' + v.y + 'px taller than its box' });
    }
  }

  for (const el of all) {
    const s = getComputedStyle(el);

    // CLIP — a paragraph the reader cannot finish. Table cells and single-line labels are exempt:
    // a truncated cell is a deliberate layout choice, a truncated sentence is a defect.
    // Clamped-with-an-expander is a deliberate pattern here (clampLeads in app.js clamps a long
    // method note to two lines and puts a "more" button straight after it). The reader can finish
    // the sentence, so it is not a defect. Clamped with NO affordance is — that text is unreachable.
    const expandable = el.nextElementSibling &&
      /clampbtn|more|expand/i.test(el.nextElementSibling.className + ' ' + el.nextElementSibling.textContent.slice(0, 12));
    const isProse = /^(P|LI|DIV|SPAN)$/.test(el.tagName) && el.children.length === 0
      && (el.textContent || '').trim().length > 60 && !el.closest('td,th,button,summary')
      && !expandable;
    if (isProse) {
      const clipped = (/hidden|clip/.test(s.overflowY) && el.scrollHeight > el.clientHeight + tol)
        || (s.textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth + tol)
        || (s.webkitLineClamp && s.webkitLineClamp !== 'none' && el.scrollHeight > el.clientHeight + tol);
      if (clipped) {
        out.push({ kind: 'CLIP', sel: path(el), text: txt(el),
          detail: 'prose is cut off — ' + el.scrollHeight + 'px of text in ' + el.clientHeight + 'px' });
      }
    }
  }

  // COLLIDE — BLOCK siblings that visibly overlap. Inline and inline-block siblings are excluded:
  // two <span>s on the same wrapped line of text share a line box and therefore overlap vertically
  // by design, which is a fact about inline layout, not a defect. Flexbox and grid children are
  // excluded too — their parent places them, and a deliberate negative-margin overlap there is a
  // design decision rather than a collision.
  const seen = new Set();
  for (const el of all) {
    const ps = getComputedStyle(el);
    if (/flex|grid/.test(ps.display)) continue;
    const kids = [...el.children].filter(k => {
      if (!visible(k)) return false;
      const ks = getComputedStyle(k);
      return ks.position === 'static' && !/^inline/.test(ks.display) && ks.float === 'none';
    });
    for (let i = 0; i < kids.length - 1; i++) {
      const a = kids[i].getBoundingClientRect(), b = kids[i + 1].getBoundingClientRect();
      const ov = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      if (ov > tol * 3 && ox > tol * 3 && a.top !== b.top) {
        const key = path(kids[i]) + '|' + path(kids[i + 1]);
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({ kind: 'COLLIDE', sel: key, text: txt(kids[i]),
          detail: Math.round(ov) + 'px vertical overlap between adjacent siblings' });
      }
    }
  }
  // One report per selector+kind: a repeated row is one bug, not forty.
  const uniq = new Map();
  for (const f of out) { const k = f.kind + '|' + f.sel; if (!uniq.has(k)) uniq.set(k, f); }
  return [...uniq.values()];
})(${TOLERANCE})`;

// `--print-audit` writes the audit expression to stdout and stops. That is the escape hatch for the
// common case here: the repo has no node_modules and the only browser to hand is the Playwright MCP
// session, which evaluates an expression but cannot require() a package. Pipe this into any console
// (or an MCP browser_evaluate) and it returns the same finding list this script would print.
if (process.argv.includes('--print-audit')) { console.log(AUDIT); process.exit(0); }

// ---------------------------------------------------------------------------
// Runner. Mirrors tests/lib/render.sh exactly: no npm, no playwright — a tiny in-process static
// server over platform/, plus the pre-provisioned headless chromium driven by CLI flags. The AUDIT
// above cannot come off a static --dump-dom (it needs live getComputedStyle / getBoundingClientRect),
// so it is injected as a probe that opens every <details>, runs the audit on an interval, and writes
// the finding list onto a <meta id="__ovf"> node. --virtual-time-budget lets async data fetches
// settle, then --dump-dom serialises the settled DOM and we read the node back — same mechanism
// render.sh uses to read its deck/Leaflet-init probe.
const fs = require('fs');
const path = require('path');
const { execFileSync, spawn } = require('child_process');
const os = require('os');

const PLATFORM = path.resolve(__dirname, '..', 'platform');
const BUDGET = 7000;                                   // virtual-time ms per page — room for data fetch + layout

function findChrome() {
  const cands = [process.env.CHROME_PATH, '/opt/pw-browsers/chromium'].filter(Boolean);
  try {
    for (const d of fs.readdirSync('/opt/pw-browsers')) {
      if (/^chromium-\d/.test(d)) cands.push(`/opt/pw-browsers/${d}/chrome-linux/chrome`);
    }
  } catch (e) { /* dir absent — handled below */ }
  for (const c of cands) { try { if (fs.statSync(c)) return c; } catch (e) { /* next */ } }
  return null;
}

// The injected probe. Uses AUDIT verbatim (the tested detector) — the value is plain JS text, so it
// embeds by concatenation with no re-escaping. The cross-origin fetch guard matches render.sh's:
// the audit must see the page the way it ships, not a page that reached a proxy-blocked CDN.
//
// The leading CSP meta REFUSES every external subresource (Google-Fonts CSS/fonts, cartocdn basemap
// tiles, any CDN) the instant it is requested. Those hosts are proxy-blocked in the gate/CI/loop
// environment regardless, so the SETTLED layout is identical either way (fallback fonts, blank
// basemap — the same state render.sh documents) — but WITHOUT this, chrome's virtual clock pauses in
// REAL time waiting ~30s for each blocked request to time out, which made a single route take ~40s.
// With it each route settles in a few seconds. Only external hosts are blocked; every same-origin
// asset (app.js, vendored deck.gl/Leaflet, styles.css, data/*.json, inline scripts) still loads.
const PROBE = '<meta http-equiv="Content-Security-Policy" content="default-src \'self\' \'unsafe-inline\' \'unsafe-eval\' data: blob:;">'
  + '<script>(function(){'
  + 'var of=window.fetch;window.fetch=function(u,o){var s=(typeof u==="string")?u:(u&&u.url)||"";'
  + 'if(/^https?:[/][/]/i.test(s)&&s.indexOf(location.origin)!==0){return Promise.reject(new TypeError("qa-blocked cross-origin fetch: "+s));}'
  + 'return of.apply(this,arguments);};'
  + 'var d=document.createElement("meta");d.id="__ovf";d.setAttribute("data-findings","[]");d.setAttribute("data-errors","[]");document.documentElement.appendChild(d);'
  + 'var errs=[];function pushErr(m){if(errs.length<40)errs.push(String(m).slice(0,160));}'
  + 'var ce=console.error;console.error=function(){pushErr([].join.call(arguments," "));return ce.apply(console,arguments);};'
  + 'window.addEventListener("error",function(e){pushErr(e.message||(e.error&&e.error.message)||e);});'
  + 'window.addEventListener("unhandledrejection",function(e){pushErr("reject:"+((e.reason&&e.reason.message)||e.reason));});'
  // Opening <details> is cheap (a property set), so keep late-rendered ones open on a light interval;
  // the AUDIT itself walks every element and is O(n) per call, so run it only at a couple of timed
  // checkpoints (the last completed one wins) rather than on every tick — a per-tick audit made a
  // heavy tab like #map take ~20x longer for no extra coverage.
  + 'function openAll(){try{document.querySelectorAll("details").forEach(function(x){x.open=true;});}catch(e){}}'
  + 'function run(){try{openAll();var r=(' + AUDIT + ');d.setAttribute("data-findings",JSON.stringify(r));d.setAttribute("data-errors",JSON.stringify(errs));}'
  + 'catch(e){d.setAttribute("data-auditerr",String(e&&e.message||e));}}'
  + 'window.addEventListener("load",openAll);setInterval(openAll,600);'
  + 'setTimeout(run,4000);setTimeout(run,7500);'
  + '})();</script>';

const unesc = s => s.replace(/&quot;/g, '"').replace(/&#39;/g, "'")
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

(() => {
  const chrome = findChrome();
  if (!chrome) {
    console.error('visual_overflow: no chromium under /opt/pw-browsers (set CHROME_PATH to override).');
    console.error('  Escape hatch: node tests/visual_overflow.js --print-audit  then eval in any browser.');
    process.exit(2);
  }

  // Inject the probe once per DISTINCT page (many routes share index.html). The temp copies live in
  // platform/ so every relative path (data/, vendor/, styles.css) still resolves; cleaned in finally.
  const pages = [...new Set(ROUTES.map(([, r]) => r.split('#')[0]))];
  const tmpFor = {};
  let server;
  const cleanup = () => {
    if (server) { try { server.kill('SIGKILL'); } catch (e) {} }
    for (const t of Object.values(tmpFor)) { try { fs.unlinkSync(t); } catch (e) {} }
  };
  process.on('SIGINT', () => { cleanup(); process.exit(2); });
  process.on('SIGTERM', () => { cleanup(); process.exit(2); });

  const findings = [];
  const consoleErrors = new Set();
  const failed = [];
  try {
    for (const pg of pages) {
      const src = path.join(PLATFORM, pg.replace(/^\//, ''));
      if (!fs.existsSync(src)) { failed.push(`${pg} (no such page)`); continue; }
      const tmpName = '_ovf_' + pg.replace(/^\//, '').replace(/[/]/g, '_');
      const tmp = path.join(PLATFORM, tmpName);
      const htmlOut = fs.readFileSync(src, 'utf8').replace('<head>', '<head>' + PROBE);
      fs.writeFileSync(tmp, htmlOut);
      tmpFor[pg] = tmp;
    }

    // The server MUST be a separate process, not an in-process Node http server: the chrome passes
    // below run through the SYNCHRONOUS execFileSync, which blocks this process's event loop for the
    // whole run — an in-process server could not answer chrome's data/*.json fetches during that
    // block, so the page would never load and every pass would hit the wall. python3 -m http.server
    // is exactly what tests/lib/render.sh uses, for the same reason.
    let port = 0;
    for (let t = 0; t < 6 && !port; t++) {
      const tryPort = 8800 + Math.floor(Math.random() * 700);
      server = spawn('python3', ['-m', 'http.server', String(tryPort), '--directory', PLATFORM], { stdio: 'ignore' });
      try {   // poll until it answers (bash exits 0), or give up on this port (exits 1 -> throws)
        execFileSync('bash', ['-c',
          `for i in $(seq 1 40); do curl -s -o /dev/null "http://localhost:${tryPort}/" && exit 0; sleep 0.25; done; exit 1`],
          { stdio: 'ignore' });
        port = tryPort;
      } catch (e) { try { server.kill('SIGKILL'); } catch (e2) {} server = null; }
    }
    if (!port) { console.error('visual_overflow: could not start a static server for platform/.'); cleanup(); process.exit(2); }

    for (const [w, h] of VIEWPORTS) {
      for (const [name, route] of ROUTES) {
        const page = route.split('#')[0];
        const hash = route.includes('#') ? '#' + route.split('#').slice(1).join('#') : '';
        if (!tmpFor[page]) { failed.push(`${name} @ ${w}x${h} (page missing)`); continue; }
        const url = `http://localhost:${port}/${path.basename(tmpFor[page])}${hash}`;
        const flags = ['--headless=new', '--no-sandbox', '--disable-gpu', '--use-gl=angle',
          '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--hide-scrollbars',
          `--window-size=${w},${h}`, `--virtual-time-budget=${BUDGET}`, '--dump-dom'];
        if (process.env.VOVF_PROGRESS) process.stderr.write(`  · ${name} @ ${w}x${h}\n`);
        let dom = '';
        // A single swiftshader pass occasionally comes back empty (render.sh sees the same); retry
        // with a fresh profile until the settled probe node is present. killSignal SIGKILL because a
        // wedged swiftshader chrome ignores SIGTERM (execFileSync's default) and would hang the wall.
        for (let attempt = 0; attempt < 3 && !/<meta id="__ovf"[^>]*data-findings=/.test(dom); attempt++) {
          const prof = fs.mkdtempSync(path.join(os.tmpdir(), 'ovf-'));
          try {
            dom = execFileSync(chrome, [...flags, `--user-data-dir=${prof}`, url],
              { encoding: 'utf8', timeout: BUDGET + 8000, killSignal: 'SIGKILL', maxBuffer: 96 * 1024 * 1024, stdio: ['ignore', 'pipe', 'ignore'] });
          } catch (e) { dom = (e && e.stdout) ? String(e.stdout) : ''; }
          finally { try { fs.rmSync(prof, { recursive: true, force: true }); } catch (e2) {} }
        }
        const m = dom.match(/<meta id="__ovf"[^>]*>/g);
        if (!m) { failed.push(`${name} @ ${w}x${h} (no probe — chromium produced no settled DOM)`); continue; }
        const tag = m[m.length - 1];
        const ae = tag.match(/data-auditerr="(.*?)"/);
        if (ae) { failed.push(`${name} @ ${w}x${h} (audit threw: ${unesc(ae[1])})`); continue; }
        const fm = tag.match(/data-findings="(.*?)"/s);
        const em = tag.match(/data-errors="(.*?)"/s);
        try {
          (JSON.parse(fm ? unesc(fm[1]) : '[]')).forEach(f => findings.push({ ...f, route: name, vp: `${w}x${h}` }));
        } catch (e) { failed.push(`${name} @ ${w}x${h} (unparseable findings)`); }
        try {
          (JSON.parse(em ? unesc(em[1]) : '[]')).forEach(x => consoleErrors.add(`${w}x${h} ${name}: ${x}`));
        } catch (e) { /* errors are advisory */ }
      }
    }
  } finally {
    cleanup();   // kills the static server + removes the probe temp copies
  }

  if (failed.length === VIEWPORTS.length * ROUTES.length) {
    console.error('visual_overflow: could not audit any route — chromium produced no settled DOM.');
    failed.slice(0, 6).forEach(f => console.error('  ' + f));
    process.exit(2);
  }
  if (consoleErrors.size) {
    console.log(`\nCONSOLE ERRORS (${consoleErrors.size}):`);
    [...consoleErrors].slice(0, 20).forEach(e => console.log('  ' + e));
  }
  if (failed.length) {
    console.log(`\nROUTES NOT AUDITED (${failed.length}):`);
    failed.forEach(f => console.log('  ' + f));
  }
  if (!findings.length) {
    console.log(`\nvisual_overflow: clean — ${ROUTES.length} routes x ${VIEWPORTS.length} viewports, no bleed, clipping, page-x or collisions.`);
    process.exit(consoleErrors.size || failed.length ? 1 : 0);
  }
  const byKind = findings.reduce((m, f) => (m[f.kind] = (m[f.kind] || 0) + 1, m), {});
  console.log(`\nvisual_overflow: ${findings.length} finding(s) — ` +
    Object.entries(byKind).map(([k, n]) => `${k} ${n}`).join(', '));
  for (const f of findings) {
    console.log(`\n  [${f.kind}] ${f.route} @ ${f.vp}\n    ${f.sel}\n    ${f.detail}` +
      (f.text ? `\n    text: "${f.text}"` : ''));
  }
  process.exit(1);
})();
