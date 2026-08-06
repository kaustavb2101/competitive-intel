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
 * Usage:  node tests/visual_overflow.js [baseUrl] [--viewports=1440,900;390,844]
 *         (serve platform/ first: cd platform && python3 -m http.server 8765)
 * Exit 0 = clean, 1 = findings, 2 = could not run (server down, playwright missing).
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
];
// Phone first: almost every overflow bug shows there first, and the desktop width is where the
// owner actually reviews. Two viewports keep the run under a minute.
const DEFAULT_VIEWPORTS = [[1440, 900], [390, 844]];
const TOLERANCE = 2; // px — sub-pixel rounding and 1px borders are not findings

const base = (process.argv[2] && !process.argv[2].startsWith('--')) ? process.argv[2] : 'http://localhost:8765';
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

(async () => {
  let chromium;
  try { ({ chromium } = require('playwright')); }
  catch {
    console.error('visual_overflow: the playwright npm package is not installed here.');
    console.error('  Either `npm i -D playwright` and re-run, or use the escape hatch:');
    console.error('    node tests/visual_overflow.js --print-audit');
    console.error('  and evaluate that expression in a browser on each route.');
    process.exit(2);
  }

  const browser = await chromium.launch();
  const findings = [];
  const consoleErrors = [];

  for (const [w, h] of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const page = await ctx.newPage();
    page.on('console', m => { if (m.type() === 'error') consoleErrors.push(`${w}x${h} ${m.text().slice(0, 160)}`); });
    page.on('pageerror', e => consoleErrors.push(`${w}x${h} pageerror: ${String(e).slice(0, 160)}`));

    for (const [name, route] of ROUTES) {
      try {
        await page.goto(base + route, { waitUntil: 'load', timeout: 20000 });
      } catch (e) {
        console.error(`visual_overflow: cannot reach ${base + route} — is the server running?`);
        await browser.close();
        process.exit(2);
      }
      // Data layers land async and several sections are <details> that only lay out once open.
      await page.waitForTimeout(3500);
      await page.evaluate(() => document.querySelectorAll('details').forEach(d => { d.open = true; }));
      await page.waitForTimeout(1200);
      const res = await page.evaluate(AUDIT);
      res.forEach(f => findings.push({ ...f, route: name, vp: `${w}x${h}` }));
    }
    await ctx.close();
  }
  await browser.close();

  if (consoleErrors.length) {
    console.log(`\nCONSOLE ERRORS (${consoleErrors.length}):`);
    [...new Set(consoleErrors)].slice(0, 20).forEach(e => console.log('  ' + e));
  }
  if (!findings.length) {
    console.log(`\nvisual_overflow: clean — ${ROUTES.length} routes x ${VIEWPORTS.length} viewports, no bleed, clipping, page-x or collisions.`);
    process.exit(consoleErrors.length ? 1 : 0);
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
