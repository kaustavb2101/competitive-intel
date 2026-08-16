// Pull what each rival's Facebook page shows about its current promotion.
//
// WHY A BROWSER AND NOT A FETCH. Facebook serves no useful markup to urllib. Every surface —
// mbasic, m, www — returns a login wall. But the wall is not opaque: before it, Facebook
// renders the page identity, the follower and "talking about" counts, and the SINGLE most
// recent post, truncated at "ดูเพิ่มเติม". A browser is what makes those readable. This is a
// login WALL, not bot mitigation: stock Chromium is served the same bytes as a patched one,
// so no stealth build is needed here (unlike KBank and KKP, which fingerprint the automation).
//
// WHAT THIS IS AND IS NOT. It is a daily MOVEMENT signal: who posted, how long ago, how the
// audience reacted, and the opening line of the promo. It is NOT a promo archive — one post
// per page per run, cut off mid-sentence. Reading it as "the rival's promotions" would
// overstate it. The full text needs a session; see --profile below.
//
// THE MEASURED / ESTIMATED LINE. followers and reactions are numbers Facebook prints, so they
// are MEASURED. `posted_ago` is Facebook's own relative stamp ("2 วัน") and is NOT converted
// to a date here: turning "2 วัน" into a calendar date requires the wall clock, and every
// other date in this repo is copied from a field the source stamped. It is carried verbatim.
//
// --profile <dir>  Use a persistent browser profile instead of a clean one. If that profile
//                  has an active Facebook session, the wall lifts and full post text is
//                  readable. The profile lives OUTSIDE the repo and is never committed; no
//                  credential is read by, passed to, or stored by this script. Kaustav
//                  approved this route on 2026-08-16. Two things to know before using it:
//                  it only works from the laptop (a session cookie is bound to its origin
//                  IP/device far more tightly than a geoblock), and automated access with a
//                  personal account is against Facebook's terms and can cost that account.
//                  Without the flag this script is anonymous and CI-safe.
//
// Writes source-data/rival_facebook.json, accumulating: an entry that stops appearing keeps
// its last_seen rather than being deleted, which is what lets a later diff say "stopped".
'use strict';
const path = require('path');
const fs = require('fs');
const REPO = path.resolve(__dirname, '..');
const { chromium } = require(path.join(REPO, 'node_modules', 'playwright'));

const UNIVERSE = path.join(REPO, 'source-data', 'rival_universe.json');
const OUT = path.join(REPO, 'source-data', 'rival_facebook.json');

const argv = process.argv.slice(2);
const arg = (n, d) => { const i = argv.indexOf(n); return i >= 0 && argv[i + 1] ? argv[i + 1] : d; };
const PROFILE = arg('--profile', null);
const ONLY = arg('--only', null);
const SLEEP_MS = parseInt(arg('--sleep', '2500'), 10);

// Facebook's furniture, in Thai and English. Stripping it is what leaves the post text.
const CHROME_NOISE = [
  'เข้าสู่ระบบ', 'ลืมบัญชีใช่ไหม', 'ลืมรหัสผ่านใช่ไหม', 'สร้างบัญชีใหม่', 'อีเมลหรือหมายเลขโทรศัพท์มือถือ',
  'รหัสผ่าน', 'ความเป็นส่วนตัว', 'ข้อกำหนด', 'ลงโฆษณา', 'ตัวเลือกโฆษณา', 'คุกกี้', 'เพิ่มเติม',
  'ตัวบ่งชี้สถานะออนไลน์', 'ตัวระบุสถานะกำลังใช้งาน', 'กำลังใช้งาน', 'ดูรูปภาพทั้งหมด',
  'สแกนคิวอาร์โค้ดและยืนยันว่าโค้ดตรงกันเพื่อเข้าสู่ระบบ', 'Log in', 'Forgot account?',
];
// "2 นาที" / "3 ชั่วโมง" / "1 วัน" / "5 สัปดาห์" — Facebook's own relative stamp.
// NO \b AFTER THE ALTERNATION. JavaScript's \b is defined on [A-Za-z0-9_], so every Thai
// character counts as a non-word character and \b after "นาที" can never match. The first
// version had it and silently read a post from 0 of 20 pages while every fetch returned 200.
// The Latin single-letter forms keep a boundary, since those genuinely need one.
const AGO = /(\d+)\s*(นาที|ชั่วโมง|วัน|สัปดาห์|เดือน|ปี)|(\d+)\s*(m|h|d|w|y)\b/;
const FOLLOWERS = /ผู้ติดตาม\s*([\d.,]+\s*(?:หมื่น|แสน|ล้าน|พัน)?)\s*คน/;
const REACTIONS = /([\d,]+)\s*ถูกใจ/;
const TALKING = /([\d,]+)\s*คนกำลังพูดถึงสิ่งนี้/;
const LIKES_OG = /ถูกใจ\s*([\d,]+)\s*คน/;

function stripChrome(t) {
  let s = t;
  for (const n of CHROME_NOISE) s = s.split(n).join(' ');
  return s.replace(/\s+/g, ' ').trim();
}

// The newest post is introduced by the page's own name followed by a relative timestamp:
//   "เงินไชโย 12 นาที · ผลสลากกินแบ่งรัฐบาล…"
// ANCHOR ON THAT PAIR, not on the name alone. The page name appears several times — the LAST
// one is the footer's "ดูอัพเดตเพิ่มเติมจาก <name>", which sits after the post, so seeking to
// it skips past the very thing we came for. That read a post from 0 of 20 pages on the first
// run while every fetch returned 200, which is exactly the shape of failure this repo treats
// as worse than an error: a clean green run reporting nothing.
function newestPost(bodyText, pageName) {
  const t = bodyText.replace(/\s+/g, ' ');
  let after = null, ago = null;
  if (pageName) {
    const esc = pageName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(esc + '\\s+(\\d+\\s*(?:นาที|ชั่วโมง|วัน|สัปดาห์|เดือน|ปี))\\s*·');
    const m = re.exec(t);
    if (m) { ago = m[1].trim(); after = t.slice(m.index + m[0].length); }
  }
  if (after === null) {
    // Fallback: first relative stamp followed by a separator anywhere in the body.
    const m = AGO.exec(t);
    if (!m) return { text: null, posted_ago: null };
    ago = m[0].trim(); after = t.slice(m.index + m[0].length);
  }
  after = after.replace(/^\s*·\s*/, '');
  // Cut at the engagement block or the "see more" marker — past that it is chrome again.
  const cut = after.search(/(ดูเพิ่มเติม|ความรู้สึกทั้งหมด|ถูกใจ\s|แสดงความคิดเห็น|ดูอัพเดตเพิ่มเติม)/);
  const text = stripChrome(cut > 0 ? after.slice(0, cut) : after).trim();
  return { text: text || null, posted_ago: ago,
           truncated: cut > 0 && after.slice(cut, cut + 20).includes('ดูเพิ่มเติม') };
}

(async () => {
  const uni = JSON.parse(fs.readFileSync(UNIVERSE, 'utf8'));
  let ops = uni.operators.filter(o => o.fb_page);
  if (ONLY) ops = ops.filter(o => o.key === ONLY);
  console.log(`${ops.length} operators carry an fb_page.${PROFILE ? '  USING PROFILE: ' + PROFILE : '  anonymous (no session)'}`);

  const launchOpts = { headless: true, args: ['--disable-blink-features=AutomationControlled'] };
  const ctxOpts = {
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    locale: 'th-TH', viewport: { width: 1280, height: 1100 }, ignoreHTTPSErrors: true,
  };
  let browser = null, ctx;
  if (PROFILE) ctx = await chromium.launchPersistentContext(PROFILE, { ...launchOpts, ...ctxOpts });
  else { browser = await chromium.launch(launchOpts); ctx = await browser.newContext(ctxOpts); }
  await ctx.addInitScript(() => Object.defineProperty(navigator, 'webdriver', { get: () => undefined }));

  const store = fs.existsSync(OUT) ? JSON.parse(fs.readFileSync(OUT, 'utf8')) : { meta: {}, pages: {} };
  store.pages = store.pages || {};
  let ok = 0, walled = 0;

  for (const o of ops) {
    const url = `https://m.facebook.com/${o.fb_page}`;
    const page = await ctx.newPage();
    const rec = { key: o.key, name_th: o.name_th, fb_page: o.fb_page,
                  is_product_page: o.fb_page_is_product !== false, url,
                  status: null, session: !!PROFILE, login_wall: null,
                  followers: null, talking_about: null, bio: null,
                  post: null, posted_ago: null, post_truncated: null,
                  reactions: null, error: null };
    try {
      const r = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      rec.status = r ? r.status() : null;
      await page.waitForTimeout(SLEEP_MS);
      const got = await page.evaluate(() => {
        const meta = n => { const e = document.querySelector(`meta[property="${n}"],meta[name="${n}"]`);
                            return e ? (e.getAttribute('content') || '') : ''; };
        return { body: document.body ? document.body.innerText : '',
                 ogTitle: meta('og:title'), ogDesc: meta('og:description') };
      });
      const body = got.body.replace(/\s+/g, ' ');
      rec.login_wall = /เข้าสู่ระบบ|Log ?in to Facebook/i.test(body);
      const pageName = (got.ogTitle || '').split('|')[0].trim();

      const f = FOLLOWERS.exec(body); if (f) rec.followers = f[1].trim();
      const ta = TALKING.exec(got.ogDesc || ''); if (ta) rec.talking_about = ta[1];
      const lk = LIKES_OG.exec(got.ogDesc || ''); if (lk) rec.likes = lk[1];
      const rx = REACTIONS.exec(body); if (rx) rec.reactions = rx[1];
      // og:description carries the bio after the follower counts.
      const bio = (got.ogDesc || '').split('·').pop();
      if (bio && bio.length > 12) rec.bio = bio.trim();

      const np = newestPost(body, pageName);
      rec.post = np.text; rec.posted_ago = np.posted_ago; rec.post_truncated = !!np.truncated;
      if (rec.post) ok++;
      if (rec.login_wall) walled++;
    } catch (e) { rec.error = String(e).split('\n')[0].slice(0, 140); }
    await page.close();

    // Accumulate. A page that goes quiet keeps its last reading and its last_seen, so a later
    // diff can say "stopped posting" instead of the entry simply vanishing.
    const prev = store.pages[o.key] || {};
    const changed = prev.post !== rec.post;
    store.pages[o.key] = { ...rec,
      first_seen: prev.first_seen || null,      // stamped by the builder from source dates
      previous_post: changed && prev.post ? prev.post : (prev.previous_post || null) };

    console.log(`${o.key.padEnd(13)} ${String(rec.status).padEnd(4)} wall=${rec.login_wall ? 'Y' : 'n'} ` +
      `followers=${(rec.followers || '-').padEnd(9)} ${rec.posted_ago ? 'posted ' + rec.posted_ago : 'no post read'}` +
      `${rec.error ? '  ERR ' + rec.error : ''}`);
    if (rec.post) console.log(`      · ${rec.post.slice(0, 150)}${rec.post_truncated ? ' …[cut by Facebook]' : ''}`);
  }

  store.meta = {
    label: PROFILE
      ? 'MEASURED from an authenticated session. Post text is full where Facebook returned it.'
      : 'MEASURED anonymously. Facebook serves ONE newest post per page, truncated at ' +
        '"ดูเพิ่มเติม", plus follower and engagement counts. This is a movement signal, not a ' +
        'promo archive — do not read it as the operator\'s full promotions.',
    session: !!PROFILE,
    // Counted over the STORE, not over this run's selection. --only SAK must not leave the
    // file claiming the universe is one page wide; the store still holds all the others.
    n_pages: Object.keys(store.pages).length,
    n_with_post: Object.values(store.pages).filter(p => p.post).length,
    n_login_wall: Object.values(store.pages).filter(p => p.login_wall).length,
    n_read_this_run: ops.length, partial_run: !!ONLY,
    note: 'posted_ago is Facebook\'s own relative stamp, carried verbatim and NOT converted ' +
          'to a date: that conversion needs the wall clock, and every other date in this repo ' +
          'is copied from a field the source stamped.',
    fb_page_missing: uni.meta.fb_page_missing || [],
  };
  fs.writeFileSync(OUT, JSON.stringify(store, null, 1) + '\n');
  if (browser) await browser.close(); else await ctx.close();
  console.log(`\nread a post from ${ok} of ${ops.length} pages; ${walled} showed a login wall.`);
  console.log(`wrote ${path.relative(REPO, OUT)}`);
})();
