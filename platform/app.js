'use strict';
/* AutoX · เงินไชโย — Credit Intelligence Platform
   Loads data files, renders overview/map/acquisition/branches. Vanilla JS, no build step. */

// Real measured quantities (no indices). val() reads measured fields; color/size scale to absolute max.
// Portfolio-risk lens is the exception: a/m/c are ESTIMATED proxies (OSM/price-based, 0–100), not measured.
const LENS = {
  workers:  {label:'Factory workers',     desc:'DIW factory employment in the branch district', color:'#E6B450', unit:'workers', val:d=>d.dwork||0},
  pickups:  {label:'Pickup stock',        desc:'DLT pickups in the province — title collateral', color:'#7A4FE0', unit:'pickups', val:d=>(PLOOK[d.v]||{}).pickup||0},
  motomix:  {label:'Motorcycle-title share ▲', desc:'MEASURED (DLT) — motorcycle share of the province vehicle stock (moto ÷ total). The most volatile, lowest-recovery title collateral; higher share = more exposure to a used-motorcycle value fall.', color:'#7A4FE0', unit:'% moto (DLT)', val:d=>motoShare(d)},
  informal: {label:'Informal workforce',  desc:'NSO informal workers in the province — borrower base', color:'#1C8C7D', unit:'workers', val:d=>(PLOOK[d.v]||{}).informal||0},
  autox:    {label:'AutoX saturation',    desc:'own AutoX branches within 10 km', color:'#5B7CFA', unit:'AutoX ≤10km', val:d=>d.w||0},
  estab:    {label:'Establishments ≤10km', desc:'MEASURED establishment density (Overture Maps Places, a sample/lower bound) — total points of interest within 10 km of each branch, a proxy for how much economic activity surrounds it. Lazy-loads branch_occupations.json; run pull_overture_places.py + build_occupations.py to populate.', color:'#1C8C7D', unit:'estab', val:d=>estabCount(d)},
  comp:     {label:'Competitor density ◆', desc:'MEASURED competitor locations (Google Places, a LOWER BOUND, not a registry) — rival title-loan / vehicle-finance branches (Srisawad, Muangthai, Tidlor, Heng) within ~5km of each AutoX branch. Lazy-loads competitors_national.json; run pull_competitors.py to populate.', color:'#E0574F', unit:'rivals ≤5km', cmp:true, val:d=>compCount(d)},
  risk:     {label:'Portfolio risk ▲ est', desc:'ESTIMATED proxy (OSM/price-based, 0–100) — composite of agri-PD / merchant / collateral. NOT a measured default rate.', color:'#E0574F', unit:'risk (est)', est:true, val:d=>riskVal(d)},
  cstress:  {label:'Agri crop-stress ▲ est', desc:"ESTIMATED triage index (0–100) — the branch's province crop-household stress (price proxy × drought, scaled by crop dependence). Lazy-loaded.", color:'#C8433B', unit:'crop-stress (est)', est:true, val:d=>cstressVal(d)},
  hhdti:    {label:'Household debt-to-income ●', desc:"MEASURED · NSO — the branch's province household debt as a multiple of annual income (NSO SES 2566, debt ÷ income). Higher = more borrower balance-sheet stress. Lazy-loads household_risk_by_province.json; hidden if absent.", color:'#C8433B', unit:'×100 DTI', hh:true, val:d=>hhriskVal(d)},
  occrisk:  {label:'Occupation × stress ◆▲', desc:"MEASURED occupation mix · ESTIMATED stress weighting — flags branches whose borrower base is concentrated in a STRESSED sector (factory under industrial slowdown · agriculture under the branch's province crop-stress). Occupation shares are MEASURED (Overture Maps Places, a sample/lower bound); the 'stressed sector' weighting is ESTIMATED (editorial macro judgement). A triage flag, NOT a measured default rate. Lazy-loads occupation_risk.json; hidden if absent.", color:'#C8433B', unit:'occ-stress (est)', est:true, occr:true, val:d=>occriskVal(d)},
  // District (amphoe) lenses — colour each branch by its district's score from amphoe.json.
  // White-space is MEASURED (demand POIs vs AutoX saturation); risk is ESTIMATED (province-inherited
  // agri-stress + local mix). Both lazy-load amphoe.json (joined per-branch via build_amphoe.py).
  dws:  {label:'District white-space ◇', desc:"MEASURED — the branch's whole district demand (POI footfall + workers) minus AutoX saturation. Higher = underserved room around an existing branch. From amphoe.json.", color:'#E6B450', unit:'white-space (0–100)', amp:true, val:d=>d._amp?d._amp.whitespace:0},
  drisk:{label:'District risk ▲ est', desc:"ESTIMATED — the branch's district risk proxy (province-inherited agri-stress + local collateral/merchant mix, 0–100). NOT a measured default rate. From amphoe.json.", color:'#C8433B', unit:'district risk (est)', est:true, amp:true, val:d=>d._amp?d._amp.risk_proxy:0},
};
// per-province crop-household stress — lazy-loaded from data/crop_stress.json (objective #1).
// CSTRESS maps Thai province name -> province record; val() returns agri_stress on a 0–100 scale.
let CSTRESS=null, cstressLoaded=false;
function cstressVal(d){const p=CSTRESS&&CSTRESS[d.v]; return p?Math.round((p.agri_stress||0)*100):0;}
// Motorcycle-title share (MEASURED, DLT): moto ÷ total vehicle stock in the branch's province, 0–100.
// This is the highest-volatility / lowest-recovery title collateral — the lens colours branches by exposure.
function motoShare(d){const p=PLOOK&&PLOOK[d.v]; if(!p||!p.vehicles||p.moto==null) return 0; return Math.round(100*p.moto/p.vehicles);}
let cstressPromise=null;
async function loadCropStress(){
  // cache the in-flight PROMISE (not just the boolean) so concurrent callers all await the real
  // fetch — otherwise a second caller returns early with CSTRESS still empty mid-flight.
  if(cstressPromise) return cstressPromise;
  cstressLoaded=true;
  cstressPromise=(async()=>{
    try{
      const j = await fetch('data/crop_stress.json').then(r=>r.json());
      CSTRESS={}; CSTRESS_META=j.meta||null; CSTRESS_LIST=j.provinces||[];
      (j.provinces||[]).forEach(p=>{CSTRESS[p.th]=p;});
    }catch(e){ CSTRESS={}; CSTRESS_LIST=[]; }
    return CSTRESS;
  })();
  return cstressPromise;
}
let CSTRESS_META=null, CSTRESS_LIST=[];

/* ---------- household debt-to-income (MEASURED · NSO SES, objective #1) ----------
   Lazy-loaded from data/household_risk_by_province.json (pipeline/build_household_risk.py).
   HHRISK maps Thai province name -> {debt, income, debt_to_income, stress_index}. debt + income
   + debt_to_income are MEASURED (NSO SES 2566); stress_index is an ESTIMATED 0–100 percentile rank.
   Fully null-guarded: if the file is ABSENT (or has meta.absent), HHRISK stays empty, the lens
   hides itself (see renderLenses), and the val() reads 0 — never errors. */
let HHRISK=null, HHRISK_META=null, HHRISK_LIST=[], hhriskLoaded=false, hhriskPromise=null;
async function loadHouseholdRisk(){
  if(hhriskPromise) return hhriskPromise;
  hhriskLoaded=true;
  hhriskPromise=(async()=>{
    try{
      const r=await fetch('data/household_risk_by_province.json'); if(!r.ok) throw 0;
      const j=await r.json();
      HHRISK_META=j.meta||null; HHRISK={}; HHRISK_LIST=[];
      if(!(j.meta&&j.meta.absent)){
        const list=(j.provinces||[]).filter(p=>p&&p.debt_to_income!=null);
        list.forEach(p=>{HHRISK[p.province]=p;});
        // sort by leverage so the hero/headline always names the most-stressed province.
        HHRISK_LIST=list.slice().sort((a,b)=>(b.debt_to_income||0)-(a.debt_to_income||0));
      }
    }catch(e){ HHRISK={}; HHRISK_META=null; HHRISK_LIST=[]; }
    return HHRISK;
  })();
  return hhriskPromise;
}
// true once the layer is loaded AND carries at least one province (i.e. not absent/empty).
function hhriskHasData(){return !!(HHRISK&&Object.keys(HHRISK).length);}
// MEASURED debt-to-income for a branch's province, scaled ×100 so the lens shares the integer
// colour scale of the other lenses (e.g. DTI 1.15 -> 115). 0 when unknown.
function hhriskVal(d){const p=HHRISK&&HHRISK[d.v]; return p&&p.debt_to_income!=null?Math.round(p.debt_to_income*100):0;}

/* ---------- measured occupation mix (Overture Places) ----------
   Lazy-loads data/branch_occupations.json — a MEASURED per-branch rollup of establishment
   points by occupation bucket within 10km, written by pipeline/build_occupations.py once
   pull_overture_places.py has run (from a normal/Thai network). The "branches" array is
   INDEX-ALIGNED to branches.json (entry i ↔ DATA[i]), shape:
     { buckets:[{key,label}], branches:[{t:total, o:[counts aligned to buckets]}] }
   Everything is null-guarded: absent file or absent branch entry → nothing extra renders,
   the national map's "estab" lens reads 0, and the branch popup simply omits the block.
   Mirrors the branch-explorer.html reference implementation (loadOccupations/OCC_BUCKET_COL). */
let OCCDATA=null, occLoaded=false, occPromise=null;
// stable colour per occupation bucket key — parity with the branch-explorer palette.
const OCC_BUCKET_COL={factory:'#7A4FE0',auto:'#7A4FE0',retail:'#1C8C7D',food:'#E6B450',
  hospitality:'#E6B450',finance:'#C8433B',health:'#5B7CFA',education:'#5B7CFA',
  public:'#8b90a7',professional:'#5B7CFA',agriculture:'#C8433B',personal:'#1C8C7D',
  logistics:'#8b90a7',construction:'#E6B450'};
async function loadOccupations(){
  // cache the in-flight PROMISE (mirrors loadCompetitors/loadCropStress) so concurrent callers
  // all await the one real fetch instead of returning early with OCCDATA still null.
  if(occPromise) return occPromise;
  occLoaded=true;
  occPromise=(async()=>{
    try{ const r=await fetch('data/branch_occupations.json'); if(r.ok) OCCDATA=await r.json(); }
    catch(e){ OCCDATA=null; }
    return OCCDATA;
  })();
  return occPromise;
}
// total measured establishments ≤10km for a branch (0 when the file/entry is absent) — the "estab" lens val().
function estabCount(d){
  if(!OCCDATA||!OCCDATA.branches||!DATA) return 0;
  const i=DATA.indexOf(d); if(i<0) return 0;
  const e=OCCDATA.branches[i]; return (e&&e.t)||0;
}
// pretty label for an occupation-bucket key (Title Case fallback when a file omits a label).
function occLabel(key){
  if(!key) return '';
  const m={factory:'Factory workers',auto:'Auto / vehicle',retail:'Retail trade',food:'Food service',
    hospitality:'Hospitality',finance:'Finance',health:'Healthcare',education:'Education',
    public:'Public sector',professional:'Professional',agriculture:'Agriculture',personal:'Personal services',
    logistics:'Logistics',construction:'Construction'};
  return m[key]||(key.charAt(0).toUpperCase()+key.slice(1));
}

/* ---------- occupation × risk cross-read (objective #1) ----------
   Lazy-loads data/occupation_risk.json — a per-branch flag for branches whose MEASURED
   borrower base (Overture occupation shares) is concentrated in a STRESSED sector (factory
   under industrial slowdown, agriculture under crop-stress). Shape:
     { meta:{...}, stress_weights:{...},
       branches:[{s:0..100 occ-risk, f:flag, d:dominant bucket key, ds:dom share, t:total}] }
   The branches[] array is INDEX-ALIGNED to branches.json (entry i ↔ DATA[i]), so a branch's
   read is OCCRISK[DATA.indexOf(d)]. The score is an ESTIMATED composite: MEASURED occupation
   shares × an ESTIMATED "stressed sector" weighting (stated in the lens tooltip).
   Fully null-guarded: absent file → OCCRISK stays empty, the lens hides itself (renderLenses),
   val() reads 0, and nothing errors. Written by pipeline/build_occupation_risk.py, which itself
   needs branch_occupations.json (the Overture pull) — so this is dark-until-data. */
let OCCRISK=null, occriskMeta=null, occriskLoaded=false, occriskPromise=null;
async function loadOccRisk(){
  if(occriskPromise) return occriskPromise;
  occriskLoaded=true;
  occriskPromise=(async()=>{
    try{ const r=await fetch('data/occupation_risk.json'); if(!r.ok) throw 0;
      const j=await r.json(); occriskMeta=j.meta||null; OCCRISK=j.branches||null; }
    catch(e){ OCCRISK=null; occriskMeta=null; }
    return OCCRISK;
  })();
  return occriskPromise;
}
// true once the layer is loaded AND carries at least one branch read (i.e. not absent/empty).
function occriskHasData(){return !!(OCCRISK&&OCCRISK.length);}
// ESTIMATED occupation-stress score (0..100) for a branch — 0 when the file/entry is absent.
function occriskVal(d){
  if(!occriskHasData()||!DATA) return 0;
  const i=DATA.indexOf(d); if(i<0) return 0;
  const e=OCCRISK[i]; return (e&&e.s)||0;
}
// the per-branch occupation-risk record (for popups) — null when absent.
function occriskRec(d){
  if(!occriskHasData()||!DATA) return null;
  const i=DATA.indexOf(d); if(i<0) return null;
  return OCCRISK[i]||null;
}

/* ---------- measured occupation mix per DISTRICT (Overture Places) ----------
   Lazy-loads data/amphoe_occupations.json — a MEASURED per-amphoe rollup of establishment
   points by occupation bucket, keyed by the amphoe `id` (matches amphoe.json). Shape:
     { buckets:[{key,label}], amphoe:{ "<id>": {t:total, o:[counts aligned to buckets], dom:<bucket idx>} } }
   Null-guarded throughout: absent file or absent entry → the district leaderboard simply omits the
   "Borrower base" cell, falling back to the existing layout. Mirrors loadOccupations/loadCompetitors. */
let AOCC=null, aoccLoaded=false, aoccPromise=null;
async function loadAmphoeOccupations(){
  if(aoccPromise) return aoccPromise;
  aoccLoaded=true;
  aoccPromise=(async()=>{
    try{ const r=await fetch('data/amphoe_occupations.json'); if(r.ok) AOCC=await r.json(); }
    catch(e){ AOCC=null; }
    return AOCC;
  })();
  return aoccPromise;
}
function aoccHasData(){return !!(AOCC&&AOCC.amphoe&&AOCC.buckets);}
// resolved dominant-bucket index for an amphoe occupation entry (uses e.dom, else argmax of e.o).
function aoccDomIdx(e){
  if(!e) return null;
  if(e.dom!=null) return e.dom;
  if(!Array.isArray(e.o)||!e.o.length) return null;
  let idx=0; for(let i=1;i<e.o.length;i++) if((e.o[i]||0)>(e.o[idx]||0)) idx=i; return idx;
}
// dominant-occupation label for an amphoe record (by its id) — '' when the file/entry is absent.
function ampDomOcc(a){
  if(!aoccHasData()||!a) return '';
  const e=AOCC.amphoe[a.id]; if(!e) return '';
  const idx=aoccDomIdx(e); if(idx==null) return '';
  const b=AOCC.buckets[idx]; if(!b) return '';
  return b.label||occLabel(b.key);
}
// share (0–1) the dominant bucket holds inside the amphoe — for a concentration hint. 0 when unknown.
function ampDomShare(a){
  if(!aoccHasData()||!a) return 0;
  const e=AOCC.amphoe[a.id]; if(!e||!Array.isArray(e.o)) return 0;
  const tot=e.t||e.o.reduce((s,v)=>s+(v||0),0); if(!tot) return 0;
  const idx=aoccDomIdx(e); if(idx==null) return 0;
  return (e.o[idx]||0)/tot;
}
// MEASURED rival branches within COMP_RADIUS_KM of an amphoe centroid (cx,cy). Uses the unioned
// competitor census (same source the per-branch d._comp tally reads). null when the census is absent.
function ampCompCount(a){
  if(!compHasData()||!a||a.cy==null||a.cx==null) return null;
  let n=0;
  for(let j=0;j<COMP_ITEMS.length;j++){
    const it=COMP_ITEMS[j];
    if(havKm(a.cy,a.cx,it.lat,it.lng)<=COMP_RADIUS_KM) n++;
  }
  return n;
}
// brand-broken-down tooltip for the district competitor cell (measured, lower bound).
function ampCompTooltip(a){
  if(!compHasData()||!a||a.cy==null||a.cx==null) return 'no competitor data yet';
  const by={}; let n=0;
  for(let j=0;j<COMP_ITEMS.length;j++){
    const it=COMP_ITEMS[j];
    if(havKm(a.cy,a.cx,it.lat,it.lng)<=COMP_RADIUS_KM){ n++; by[it.brand]=(by[it.brand]||0)+1; }
  }
  if(!n) return `No rival branches ≤${COMP_RADIUS_KM}km of district centre (measured, lower bound)`;
  const parts=Object.entries(by).sort((x,y)=>y[1]-x[1]).map(([b,c])=>`${b} ${c}`);
  return `${n} rival branch${n===1?'':'es'} ≤${COMP_RADIUS_KM}km of district centre: ${parts.join(', ')} (measured, lower bound)`;
}

/* ---------- competitor census (objective #2: competitor-AWARE white-space) ----------
   Lazy-loads data/competitors_national.json — a MEASURED census of rival title-loan / vehicle-
   finance branches (Srisawad, Muangthai, Tidlor, Heng) from Google Places, written by
   pipeline/pull_competitors.py (run from a Thai IP). It is a LOWER BOUND, not a registry:
   Places caps ~60 results/query and not every branch is listed. Everything is null-guarded so
   the app works BEFORE the file exists — the lens then shows a quiet "run pull_competitors.py" note.
   We count rival branches within ~5km of each AutoX branch (client-side haversine) so an
   "underserved" district can be re-read as "underserved AND undercompeted". */
let COMP=null, COMP_META=null, COMP_ITEMS=[], compLoaded=false, compPromise=null;
let compAttached=false;               // per-AutoX competitor counts joined onto DATA (d._comp)
const COMP_RADIUS_KM=5;               // competitor-proximity radius (km) for the AutoX-vs-rival count
// brand -> dot colour for faint competitor points + tooltips (kept distinct from AutoX accent).
const COMP_BRAND_COLOR={Srisawad:'#E0574F',Muangthai:'#E6B450',Tidlor:'#1C8C7D',Heng:'#7A4FE0'};
function compHasData(){return !!(COMP_ITEMS&&COMP_ITEMS.length);}
// UNION two competitor sources (Google Places census + Overture-Places harvest), deduping
// rivals of the SAME brand within ~150m via a coarse grid (O(n)). Either source may be absent.
function dedupComp(items){
  const out=[], seen=new Map(); // cellKey -> array of [lat,lng]
  const C=0.0015; // ~165m grid cell
  for(const it of items){
    if(!it||it.lat==null||it.lng==null) continue;
    const gx=Math.round(it.lat/C), gy=Math.round(it.lng/C);
    let dup=false;
    for(let dx=-1;dx<=1&&!dup;dx++)for(let dy=-1;dy<=1&&!dup;dy++){
      const k=it.brand+'|'+(gx+dx)+'|'+(gy+dy), arr=seen.get(k);
      if(arr) for(const p of arr){ if(havKm(it.lat,it.lng,p[0],p[1])<=0.15){dup=true;break;} }
    }
    if(dup) continue;
    const k=it.brand+'|'+gx+'|'+gy; (seen.get(k)||seen.set(k,[]).get(k)).push([it.lat,it.lng]);
    out.push(it);
  }
  return out;
}
async function loadCompetitors(){
  if(compPromise) return compPromise;
  compLoaded=true;
  compPromise=(async()=>{
    const grab=async u=>{ try{const r=await fetch(u); if(!r.ok)return null; return await r.json();}catch(e){return null;} };
    const [g,o]=await Promise.all([grab('data/competitors_national.json'),grab('data/competitors_overture.json')]);
    const srcs=[]; if(g)srcs.push('Google Places'); if(o)srcs.push('Overture');
    const items=[].concat(g&&g.items||[], o&&o.items||[]).filter(it=>it&&it.lat!=null&&it.lng!=null);
    if(!items.length){ COMP=null; COMP_META=null; COMP_ITEMS=[]; }
    else{
      COMP_ITEMS=dedupComp(items);
      COMP=g||o; COMP_META={sources:srcs, raw:items.length, deduped:COMP_ITEMS.length};
    }
    attachCompToBranches();
    return COMP_ITEMS;
  })();
  return compPromise;
}
// great-circle distance (km) between two lat/lng points.
function havKm(la1,lo1,la2,lo2){
  const R=6371, p=Math.PI/180;
  const dla=(la2-la1)*p, dlo=(lo2-lo1)*p;
  const a=Math.sin(dla/2)**2+Math.cos(la1*p)*Math.cos(la2*p)*Math.sin(dlo/2)**2;
  return 2*R*Math.asin(Math.min(1,Math.sqrt(a)));
}
// For each AutoX branch, count rival branches within COMP_RADIUS_KM and tally by brand.
// O(branches × competitors) but tiny (≤2,015 × a few thousand) and runs once, lazily.
function attachCompToBranches(){
  if(compAttached||!DATA) return;
  const has=compHasData();
  for(let i=0;i<DATA.length;i++){
    const d=DATA[i];
    if(!has){ d._comp={n:0,brands:{},ok:false}; continue; }
    const by={}; let n=0;
    for(let j=0;j<COMP_ITEMS.length;j++){
      const it=COMP_ITEMS[j];
      if(havKm(d.y,d.x,it.lat,it.lng)<=COMP_RADIUS_KM){ n++; by[it.brand]=(by[it.brand]||0)+1; }
    }
    d._comp={n,brands:by,ok:true};
  }
  compAttached=true;
}
function compCount(d){return (d._comp&&d._comp.ok)?d._comp.n:0;}
// competitor-vs-AutoX read for a branch: ratio of nearby rivals to our own ≤10km presence.
// High rivals + low own = contested; low rivals + demand = undercompeted white space.
function compTooltip(d){
  const c=d._comp; if(!c||!c.ok) return 'No competitor data — run pull_competitors.py';
  if(!c.n) return `No rival branches ≤${COMP_RADIUS_KM}km (measured, lower bound)`;
  const parts=Object.entries(c.brands).sort((a,b)=>b[1]-a[1]).map(([b,n])=>`${b} ${n}`);
  return `${c.n} rival branch${c.n===1?'':'es'} ≤${COMP_RADIUS_KM}km: ${parts.join(', ')} (measured, lower bound)`;
}
// risk sub-metric: composite (max of the three proxies) or a single selectable score.
let riskMetric='composite';
// carry the current light/dark theme over to the standalone 3D/map pages
function themeQS(){try{return '&theme='+(document.documentElement.dataset.theme==='light'?'light':'dark');}catch(e){return '';}}
function riskVal(d){
  const a=d.a==null?0:d.a, m=d.m==null?0:d.m, c=d.c==null?0:d.c;
  return riskMetric==='a'?a : riskMetric==='m'?m : riskMetric==='c'?c : Math.max(a,m,c);
}

let DATA=null, META=null, map=null, markers=[], curLens='workers', branchSort='dwork', mapReady=false;
let radiusCircle=null, showRadius=true;

const $ = s => document.querySelector(s);
const el = (t,c,h) => { const e=document.createElement(t); if(c)e.className=c; if(h!=null)e.innerHTML=h; return e; };
function barHTML(v,color,max=100){return `<span class="bar"><i style="width:${Math.round(62*Math.min(v,max)/max)}px;background:${color}"></i></span>`;}
// honest n/a renderer for null measured fields (Batch 1 nulled some workforce releases)
function naNum(v){return v==null?'<span class="sub" title="Not in the NSO release we have">n/a</span>':v.toLocaleString();}

// MOBILE: wrap every wide data table in a horizontal-scroll container so a many-column .tbl
// can never push the whole page sideways on a phone. The <table> nodes persist (only their
// innerHTML is replaced on re-render), so wrapping each once at boot is enough and stays
// deterministic. Idempotent — skips tables already inside a .tblwrap.
function wrapTables(){
  document.querySelectorAll('table.tbl').forEach(t=>{
    if(t.parentElement&&t.parentElement.classList.contains('tblwrap')) return;
    const w=document.createElement('div'); w.className='tblwrap';
    // a11y: a horizontally-scrollable region must be keyboard-reachable + labelled so a
    // keyboard / screen-reader user can pan a wide table (WCAG 2.1.1 / scrollable-region-focusable).
    w.setAttribute('role','region');
    w.setAttribute('tabindex','0');
    w.setAttribute('aria-label','Scrollable data table');
    t.parentNode.insertBefore(w,t); w.appendChild(t);
  });
}

/* ---------- tabs ---------- */
function showTab(v){
  if(!v||!document.getElementById('v-'+v)) v='home';
  document.querySelectorAll('#nav a[data-v]').forEach(t=>{const sel=t.dataset.v===v;t.classList.toggle('on',sel);t.setAttribute('aria-selected',String(sel));});
  document.querySelectorAll('.view').forEach(s=>s.classList.toggle('on', s.id==='v-'+v));
  if(v==='home') renderHome();
  if(v==='overview') renderOverview();
  if(v==='branches') renderBranches();
  if(v==='map') initMap();
  if(v==='provinces') renderProvinces();
  if(v==='market') renderMarket();
  if(v==='exposure') renderExposure();
  if(v==='sim') renderSim();
  if(v==='trend') renderTrend();
  if(v==='acq') loadAmphoe();
  window.scrollTo(0,0);
}
$('#nav').addEventListener('click', e=>{
  const b=e.target.closest('a[data-v]'); if(!b) return;
  e.preventDefault(); const v=b.dataset.v;
  history.replaceState(null,'','#'+v);
  showTab(v);
});
window.addEventListener('hashchange',()=>showTab((location.hash||'').replace('#','')));
// command-center "→" links carry data-v but live outside #nav; jump to that tab.
document.addEventListener('click',e=>{
  const a=e.target.closest('#v-home a[data-v]'); if(!a) return;
  e.preventDefault(); const v=a.dataset.v; history.replaceState(null,'','#'+v); showTab(v);
});
// Keyboard activation for clickable table rows (role="link" tabindex=0): Enter / Space.
document.addEventListener('keydown',e=>{
  if(e.key!=='Enter'&&e.key!==' '&&e.key!=='Spacebar') return;
  const row=e.target.closest&&e.target.closest('tr[role="link"][onclick]');
  if(!row||row!==e.target) return;
  e.preventDefault(); row.click();
});
// Acquisition in-tab jump-nav: open the target collapsible section and scroll to it.
(function(){const j=document.getElementById('acqjump'); if(!j) return;
  j.addEventListener('click',e=>{const a=e.target.closest('[data-acq]'); if(!a) return;
    e.preventDefault();
    const sec=document.getElementById(a.dataset.acq); if(!sec) return;
    sec.open=true;
    sec.scrollIntoView({behavior:'smooth',block:'start'});
    const sm=sec.querySelector('summary'); if(sm) sm.focus({preventScroll:true});
  });})();

/* ---------- load ---------- */
async function boot(){
  try{
    const [b,m] = await Promise.all([
      fetch('data/branches.json').then(r=>r.json()),
      fetch('data/meta.json').then(r=>r.json())
    ]);
    DATA=b; META=m;
    wrapTables();
    $('#updated').textContent = META.updated || '';
    try{ PROV = await fetch('data/provinces/index.json').then(r=>r.json()); PLOOK=provLookupByName(); }catch(e){}
    renderOverview(); renderAcq(); renderLenses(); renderBranchSort(); renderBranches();
    showTab((location.hash||'').replace('#',''));
  }catch(err){
    document.querySelector('main').insertAdjacentHTML('afterbegin',
      `<div class="insight" style="border-left-color:var(--agri)">Couldn't load data files. Make sure <b>data/branches.json</b> and <b>data/meta.json</b> sit next to this page. (${err})</div>`);
  }
}

/* ---------- overview ---------- */
function renderOverview(){
  $('#macro').innerHTML = META.macro.map(([k,v,n])=>
    `<div class="mcard"><div class="k">${k}</div><div class="v">${v}</div><div class="n">${n}</div></div>`).join('');
  const cls=b=> (b.yoy||0)>5?'var(--up)':(b.yoy||0)<-8?'var(--agri)':(b.yoy||0)<0?'#D9742B':'#C9A227';
  const row=b=>`<tr><td>${b.lab}</td><td class="mono" style="color:${cls(b)}">${b.yoy!=null?(b.yoy>0?'+':'')+b.yoy+'%':'—'}</td><td class="sub">${b.reg}</td><td class="sub">${b.note}</td></tr>`;
  const head=`<tr><th>Item</th><th>YoY</th><th>Region</th><th>Note</th></tr>`;
  $('#board-crops').innerHTML = head + META.board.filter(b=>b.seg==='Crops').map(row).join('');
  $('#board-other').innerHTML = head + META.board.filter(b=>b.seg!=='Crops').map(row).join('');
  const rc={Isan:'var(--agri)',North:'#D9742B',South:'#C9A227',East:'#3B82F6','Central&BKK':'var(--accent)'};
  $('#region').innerHTML = `<tr><th>Region</th><th>Branches</th><th>Agri-PD</th><th>Elevated</th><th>Merchant</th><th>Collateral</th></tr>`+
    META.region.map(r=>`<tr><td><b>${r.r}</b></td><td class="mono">${r.n}</td>
      <td>${barHTML(r.agri,rc[r.r])} <span class="mono">${r.agri}</span></td>
      <td class="mono" style="color:var(--agri)">${r.hi}</td>
      <td>${barHTML(r.md,'var(--merch)')} <span class="mono">${r.md}</span></td>
      <td>${barHTML(r.col,'var(--collat)')} <span class="mono">${r.col}</span></td></tr>`).join('');
  renderBotCap();
  renderCollatOutlook();
  renderCollatMix();
  renderRecoverySensitivity();
  // lazy-load + render the crop-household stress card (objective #1, portfolio risk)
  loadCropStress().then(renderCropStress);
}

/* ---------- BoT hire-purchase rate-cap macro card (objective #1, margin watch) ----------
   Editorial / regulatory note. The Bank of Thailand introduced a ceiling on interest +
   fees for car & motorcycle hire-purchase lending, effective ~Dec 2025. We deliberately do
   NOT print a precise rate — only the direction and that it is a SECTOR-MARGIN watch, not a
   borrower-credit signal. Clearly dated and labelled editorial. */
function renderBotCap(){
  const el=$('#botcap'); if(!el) return;
  el.innerHTML=`<b>Bank of Thailand hire-purchase rate/fee cap</b> on car &amp; motorcycle lending —
    effective <b>~Dec 2025</b>. Ceiling on interest + fees compresses yields across the auto &amp;
    motorcycle hire-purchase sector, a <b>margin watch</b> for lenders. AutoX's core is
    <b>title loans</b> (not hire-purchase), so the direct hit is limited — but it signals a
    <b>tightening regulatory posture</b> on vehicle-secured consumer credit and caps pricing
    headroom across the segment.
    <span class="sub" style="display:block;margin-top:6px">Editorial / regulatory · no precise rate stated · dated ~Dec 2025 · sector-margin item, not a portfolio-credit signal.</span>`;
}

/* ---------- Collateral outlook board (objective #1, portfolio risk) ----------
   Makes explicit that the two things AutoX lends against are diverging:
   GOLD value is UP (measured, from the commodity board), while the DIESEL-PICKUP collateral
   backing most title loans is under depreciation pressure (used-pickup glut + EV/PHEV
   transition). We have NO live Thai used-pickup index, so the pickup card is labelled an
   EDITORIAL / ESTIMATED WATCH — said plainly in the note. */
function renderCollatOutlook(){
  const el=$('#collat-outlook'); if(!el) return;
  const gold=(META.board||[]).find(b=>b.seg==='Collateral'&&/gold/i.test(b.lab||''));
  const gy=gold&&gold.yoy!=null?(gold.yoy>0?'+':'')+gold.yoy+'%':'+62.7%';
  const cards=[
    {k:'Gold collateral', v:gy, d:'value ↑', cls:'up',
     n:'Measured · commodity board (World Bank, '+(gold&&gold.stale?gold.stale:'2025M12')+'). Lifts pawn / gold-backed loan value & recovery.'},
    {k:'Diesel-pickup collateral', v:'↓ pressure', d:'value at risk', cls:'down',
     n:'Editorial / estimated watch · used-pickup glut + EV/PHEV transition erode resale of the trucks backing most title loans. No live Thai used-pickup index yet.'},
  ];
  el.innerHTML=cards.map(c=>`<div class="mcard"><div class="k">${c.k}</div>
    <div class="v ${c.cls}">${c.v}</div><div class="d ${c.cls==='up'?'up':'dn'}">${c.d}</div>
    <div class="n">${c.n}</div></div>`).join('');
  const note=$('#collat-note');
  if(note) note.innerHTML='<b>Read:</b> the gold side of the book is appreciating while the diesel-pickup side faces a slow value squeeze — '+
    'if recovery values on repossessed pickups fall, loss-given-default on the title book rises even before any change in default rates. '+
    'The pickup direction is an <b>estimated/editorial watch</b> (no live Thai used-pickup price index in this data); gold is measured.';
}
/* ---------- Collateral mix · most motorcycle-heavy provinces (objective #1, MEASURED) ----------
   Pure DLT vehicle stock split per province (moto / car / pickup / EV share of total). A ฿10k
   motorcycle title and a ฿500k car title are one "vehicle" each but very different risk — this
   surfaces the mix. We rank provinces WHERE AUTOX OPERATES (branches > 0) by motorcycle share,
   the most volatile / lowest-recovery title collateral. Everything here is MEASURED (DLT). */
function collatMixRows(){
  return (PROV||[]).filter(p=>p.vehicles&&p.moto!=null&&(p.branches||0)>0)
    .map(p=>({th:p.th,region:p.region,branches:p.branches,vehicles:p.vehicles,
              moto:Math.round(100*p.moto/p.vehicles),
              car:p.car!=null?Math.round(100*p.car/p.vehicles):null,
              pickup:p.pickup!=null?Math.round(100*p.pickup/p.vehicles):null,
              ev:p.ev!=null?Math.round(100*p.ev/p.vehicles):null}))
    .sort((a,b)=>b.moto-a.moto);
}
function renderCollatMix(){
  const tbl=$('#collatmixtbl'), note=$('#collatmix-note'); if(!tbl) return;
  const rows=collatMixRows();
  if(!rows.length){ if(note) note.textContent='Vehicle-mix data not available (data/provinces/index.json missing).'; return; }
  const natMoto=(()=>{let m=0,t=0;(PROV||[]).forEach(p=>{if(p.vehicles&&p.moto!=null){m+=p.moto;t+=p.vehicles;}});return t?Math.round(100*m/t):0;})();
  if(note) note.innerHTML='The collateral behind a title loan is not one thing: a ฿10k motorcycle title and a ฿500k car title are each <b>one "vehicle"</b> but very different risk. '+
    'These are the provinces (with AutoX branches) whose registered fleet is most <b>motorcycle</b>-weighted — the lowest-recovery, most volatile title collateral. '+
    'All shares are <b>measured (DLT registered vehicle stock)</b>. Nationally motorcycles are <b>'+natMoto+'%</b> of the fleet.';
  const top=rows.slice(0,10);
  tbl.innerHTML=`<tr><th>#</th><th>Province</th><th>Region</th><th title="AutoX branches">Branches</th><th class="h-collat" title="motorcycle share of the province registered vehicle stock — DLT, measured">Motorcycle % ▲</th><th title="DLT, measured">Car %</th><th title="DLT, measured">Pickup %</th><th title="DLT, measured">EV %</th></tr>`+
    top.map((p,i)=>{const mc=p.moto>=70?'var(--agri)':p.moto>=60?'var(--gold)':'var(--collat)';
      return `<tr><td class="mono sub">${i+1}</td><td><b>${p.th}</b></td><td class="sub">${p.region}</td>
      <td class="mono">${p.branches}</td>
      <td>${barHTML(p.moto,mc)} <span class="mono" style="color:${mc}">${p.moto}%</span></td>
      <td class="mono sub">${p.car!=null?p.car+'%':'—'}</td>
      <td class="mono sub">${p.pickup!=null?p.pickup+'%':'—'}</td>
      <td class="mono sub">${p.ev!=null?p.ev+'%':'—'}</td></tr>`;}).join('');
}

/* ---------- Collateral recovery-value sensitivity (objective #1, ILLUSTRATIVE) ----------
   Combines the MEASURED gold move (+62.7%, commodity board — gold collateral firming) with an
   ILLUSTRATIVE used-motorcycle value shock. We have NO loan balances and NO LTV, so we do NOT
   invent LTV-breach counts. Instead we rank the provinces AutoX operates in by motorcycle-title
   SHARE (measured) — those most exposed if used-motorcycle recovery values fall. The 10% figure
   is a stated, illustrative scenario, NOT a forecast. */
function renderRecoverySensitivity(){
  const cards=$('#recovery-cards'), note=$('#recovery-note'), tbl=$('#recoverytbl'); if(!cards) return;
  const gold=(META.board||[]).find(b=>b.seg==='Collateral'&&/gold/i.test(b.lab||''));
  const gy=gold&&gold.yoy!=null?(gold.yoy>0?'+':'')+gold.yoy+'%':'+62.7%';
  cards.innerHTML=[
    {k:'Gold collateral',v:gy,d:'recovery value ↑',cls:'up',
     n:'MEASURED · commodity board (World Bank, '+(gold&&gold.stale?gold.stale:'2025M12')+'). Higher gold price lifts recovery on gold-backed loans.'},
    {k:'Used-motorcycle value',v:'−10%',d:'illustrative shock',cls:'down',
     n:'ILLUSTRATIVE scenario (not a forecast). We have no Thai used-motorcycle price index; this is a stated stress to rank exposure.'},
    {k:'Most exposed',v:'high-moto provinces',d:'by title-share',cls:'down',
     n:'Ranked by MEASURED motorcycle-title share (DLT). No LTV/loan-balance data, so we rank exposure — we do NOT show breach counts.'},
  ].map(c=>`<div class="mcard"><div class="k">${c.k}</div>
    <div class="v ${c.cls}">${c.v}</div><div class="d ${c.cls==='up'?'up':'dn'}">${c.d}</div>
    <div class="n">${c.n}</div></div>`).join('');
  if(note) note.innerHTML='<b>Read:</b> gold collateral is appreciating (measured, +62.7%) while motorcycles — the highest-share, lowest-recovery title collateral — would be most hurt by any fall in used-vehicle values. '+
    'A <b>10% fall in used-motorcycle values</b> most exposes the provinces below, which carry the highest motorcycle-title share. '+
    'This is an <b>ESTIMATED / illustrative sensitivity</b>: we have <b>no loan balances and no LTV</b>, so we rank by motorcycle-share exposure and deliberately show <b>no LTV-breach counts</b>. Shares are measured (DLT).';
  const rows=collatMixRows().slice(0,8); if(!tbl||!rows.length) return;
  tbl.innerHTML=`<tr><th>#</th><th>Province</th><th>Region</th><th title="AutoX branches">Branches</th><th class="h-collat" title="motorcycle share of registered vehicle stock — DLT, measured">Moto-title share ▲ (DLT)</th><th class="h-collat" title="relative exposure to a 10% used-motorcycle value fall — illustrative, proportional to motorcycle share">Relative exposure ◇ illustrative</th></tr>`+
    rows.map((p,i)=>{const mc=p.moto>=70?'var(--agri)':p.moto>=60?'var(--gold)':'var(--collat)';
      const rank=i===0?'Highest':i<3?'High':'Elevated';
      return `<tr><td class="mono sub">${i+1}</td><td><b>${p.th}</b></td><td class="sub">${p.region}</td>
      <td class="mono">${p.branches}</td>
      <td>${barHTML(p.moto,mc)} <span class="mono" style="color:${mc}">${p.moto}%</span></td>
      <td class="mono" style="color:${mc}">▲ ${rank}</td></tr>`;}).join('');
}

/* ---------- crop-household stress (Overview card) ----------
   Top ~8 worst provinces by the ESTIMATED agri_stress triage index, with the REAL components:
   dominant crop + share (OAE, measured), price YoY (World Bank GLOBAL direction proxy — NOT Thai
   farm-gate), rainfall % of normal (HDX, measured). Data from data/crop_stress.json (lazy). */
function renderCropStress(){
  const tbl=$('#cstresstbl'), note=$('#cstress-note');
  if(!tbl) return;
  if(!CSTRESS_LIST||!CSTRESS_LIST.length){
    if(note) note.textContent='Crop-household stress data not available (data/crop_stress.json missing).';
    return;
  }
  const top=CSTRESS_LIST.slice(0,8); // already sorted worst-first by agri_stress
  if(note) note.innerHTML='Which crop-farming provinces are squeezing borrower income most. '+
    '<b>Agri-stress</b> is an <b>estimated triage index</b> (price proxy × drought, scaled by how much the province farms). '+
    '<b>Price YoY</b> = World Bank <b>global</b> price direction proxy (<i>not</i> Thai farm-gate). '+
    '<b>Dominant crop</b> (OAE planting area) and <b>rainfall % of normal</b> (HDX) are <b>measured</b>.';
  tbl.innerHTML=`<tr><th>#</th><th>Province</th><th>Region</th><th class="h-agri" title="ESTIMATED triage index 0–100">Agri-stress ▲ est</th><th title="OAE planting-area dominant crop — measured">Dominant crop</th><th title="World Bank GLOBAL price YoY direction proxy — not Thai farm-gate">Price YoY ◇ est</th><th title="HDX rainfall as % of normal — measured">Rain % normal</th></tr>`+
    top.map((p,i)=>{const c=p.components||{}; const dom=(p.crop_mix&&p.crop_mix[0])||{};
      const sv=Math.round((p.agri_stress||0)*100); const bar=sv>=45?'var(--agri)':sv>=25?'var(--gold)':'var(--merch)'; const sc=sv>=45?'var(--agri)':sv>=25?'var(--gold)':'var(--merch)';
      const rn=c.rain_pct_of_normal; const rcol=rn!=null&&rn<85?'var(--gold)':'var(--mid)';
      // double-stress badge: rice/rubber-heavy AND softening prices AND elevated drought
      // (ESTIMATED flag from crop_stress.json). Graceful: nothing rendered when absent/false.
      const ds=p.double_stress?` <span class="tag" style="color:var(--agri);border:1px solid var(--agri)" title="ESTIMATED — rice/rubber-heavy AND prices softening AND drought elevated (double-stress, crop_stress.json)">double-stress</span>`:'';
      return `<tr><td class="mono sub">${i+1}</td><td><b>${p.th}</b>${ds}</td><td class="sub">${p.region||'—'}</td>
      <td>${barHTML(sv,bar)} <span class="mono" style="color:${sc}">${sv}</span></td>
      <td class="sub">${dom.crop||'—'} <span class="mono">${dom.share!=null?Math.round(dom.share*100)+'%':''}</span></td>
      <td class="mono" style="color:${p.price_stress<0?'var(--agri)':'var(--mid)'}">${p.price_stress!=null?(p.price_stress>0?'+':'')+p.price_stress+'%':'—'}</td>
      <td class="mono" style="color:${rcol}">${rn!=null?rn+'%':'n/a'}</td></tr>`;}).join('');
}

/* ---------- acquisition ---------- */
function renderAcq(){
  $('#estates').innerHTML = `<tr><th>AutoX ≤10km</th><th>Industrial estate</th></tr>`+
    META.estates.map(s=>{const c=s.own<=3?'#E0474B':s.own<=6?'var(--gold)':'#2BB673';const t=s.own<=3?'white space':s.own<=6?'thin':'covered';
      return `<tr><td><span class="tag" style="color:${c};border:1px solid ${c}">${s.own} · ${t}</span></td><td>${s.name}</td></tr>`;}).join('');
  $('#mws').innerHTML = `<tr><th>Demand</th><th>AutoX</th><th>Fresh mkts</th><th>Province</th><th>Branch</th></tr>`+
    META.mws.map(m=>`<tr><td class="mono" style="color:var(--merch)">${m.md}</td><td class="mono">${m.own}</td><td class="mono">${m.fmkt}</td><td>${m.v}</td><td class="sub">${m.n}</td></tr>`).join('');
  $('#cws').innerHTML = `<tr><th>Collat</th><th>Vehicle</th><th>Gold</th><th>AutoX</th><th>Province</th><th>Branch</th></tr>`+
    META.cws.map(c=>`<tr><td class="mono" style="color:var(--collat)">${c.c}</td><td class="mono">${c.veh}</td><td class="mono">${c.gold}</td><td class="mono">${c.own}</td><td>${c.v}</td><td class="sub">${c.n}</td></tr>`).join('');
  renderAcqBoard();
  renderRoad3k();
  renderOppScore();
  renderCompCoverage();
  renderExitWhitespace();
}

/* ---------- Competitor coverage (lower bound) · found vs expected (obj #2) ----------
   Surfaces data/competitor_coverage.json (built by pipeline/build_competitor_coverage.py):
   per brand {found (MEASURED census count), expected (ESTIMATED-from-public-reports, cited),
   coverage_pct}. Makes the census UNDERCOUNT explicit and honest. Lazy-loaded once; degrades
   gracefully (calm notice) when the file is absent. We DO NOT compute anything here. */
let COMPCOV=null, compcovLoaded=false;
function renderCompCoverage(){
  const tbl=$('#compcovtbl'); if(!tbl) return;
  if(compcovLoaded){ drawCompCoverage(); return; }
  fetch('data/competitor_coverage.json').then(r=>r.ok?r.json():null).then(j=>{
    COMPCOV=j; compcovLoaded=true; drawCompCoverage();
  }).catch(()=>{ COMPCOV=null; compcovLoaded=true; drawCompCoverage(); });
}
function drawCompCoverage(){
  const tbl=$('#compcovtbl'), ro=$('#compcovreadout'); if(!tbl) return;
  const rows=(COMPCOV&&Array.isArray(COMPCOV.brands))?COMPCOV.brands:[];
  if(!rows.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Competitor coverage not yet computed.</b> <span class="sub">Run <span class="mono">pipeline/build_competitor_coverage.py</span> to populate <span class="mono">data/competitor_coverage.json</span> (needs a competitor census), then this panel fills in.</span>';
    return;
  }
  // sort by coverage_pct desc (nulls last) so the best-covered brand leads.
  const list=rows.slice().sort((a,b)=>((b.coverage_pct==null?-1:b.coverage_pct)-(a.coverage_pct==null?-1:a.coverage_pct)));
  tbl.innerHTML=`<tr><th>Brand</th>`+
    `<th title="MEASURED — locations of this brand in our de-duplicated census (a lower bound)">Found ◆ measured</th>`+
    `<th title="ESTIMATED-from-public-reports — the brand's publicly-reported nationwide branch count (cited company IR / annual reports)">Expected ★ public</th>`+
    `<th title="found ÷ expected — the share of the brand's reported network we have located so far. A confidence flag, NOT market share.">Coverage</th>`+
    `<th>Census completeness</th></tr>`+
    list.map(b=>{
      const exp=b.expected, cov=b.coverage_pct;
      const covtxt=(cov==null)?'<span class="sub">n/a</span>':`<span class="mono" style="color:var(--gold)"><b>${cov.toFixed(1)}%</b></span>`;
      const exptxt=(exp==null)?'<span class="sub" title="no nationwide branch count cited in our research — not invented">n/a (uncited)</span>':`<span class="mono">${exp.toLocaleString()}</span>`;
      const bar=(cov==null)?'<span class="sub">—</span>':barHTML(cov,'var(--merch)');
      return `<tr>
        <td><b>${b.brand}</b></td>
        <td class="mono" style="color:var(--merch)">${(b.found||0).toLocaleString()}</td>
        <td>${exptxt}</td>
        <td>${covtxt}</td>
        <td>${bar}</td>
      </tr>`;}).join('');
  if(ro){
    const m=COMPCOV.meta||{}, t=m.totals||{};
    const ttxt=(t.coverage_pct!=null)
      ? `Overall we have located <b style="color:var(--merch)">${(t.found||0).toLocaleString()}</b> of an estimated <b style="color:var(--gold)">${(t.expected||0).toLocaleString()}</b> reported branches — about <b style="color:var(--gold)">${t.coverage_pct.toFixed(1)}%</b> coverage.`
      : `Found <b style="color:var(--merch)">${(t.found||0).toLocaleString()}</b> competitor locations (lower bound).`;
    ro.innerHTML=`<b>Our competitor census is a LOWER BOUND.</b> ${ttxt}
      <span class="sub">Found = MEASURED; expected = ESTIMATED-from-public-reports (cited IR / annual reports — uncited brands left blank, never invented).
      Coverage % is a confidence flag on our competitor-density signals, not market share. The census is being expanded.</span>`;
  }
}

/* ---------- composite opportunity score · where to open next (item 2) ----------
   Surfaces data/opportunity_score.json (928 districts, built by pipeline/build_opportunity_score.py):
   an ESTIMATED COMPOSITE blending MEASURED white-space + MEASURED competitor-gap with ESTIMATED
   province agri-stress. We DO NOT recompute it here — we just rank & show the top districts with each
   component exposed, so the number stays honest. Lazy-loaded once; graceful if absent/empty. */
let OPPSCORE=null, oppLoaded=false;
const OPP_TOPN=20;
function renderOppScore(){
  const tbl=$('#opptbl'); if(!tbl) return;
  if(oppLoaded){ drawOppScore(); return; }
  fetch('data/opportunity_score.json').then(r=>r.ok?r.json():null).then(j=>{
    OPPSCORE=j; oppLoaded=true; drawOppScore();
  }).catch(()=>{ OPPSCORE=null; oppLoaded=true; drawOppScore(); });
}
function drawOppScore(){
  const tbl=$('#opptbl'), ro=$('#oppreadout'); if(!tbl) return;
  const rows=(OPPSCORE&&Array.isArray(OPPSCORE.districts))?OPPSCORE.districts:[];
  if(!rows.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Opportunity score not yet computed.</b> <span class="sub">Run <span class="mono">pipeline/build_opportunity_score.py</span> to populate <span class="mono">data/opportunity_score.json</span>, then this leaderboard fills in.</span>';
    return;
  }
  // already sorted (score desc) in the file, but sort defensively so the view is stable
  const top=rows.slice().sort((a,b)=>(b.score||0)-(a.score||0)).slice(0,OPP_TOPN);
  // component colours per CLAUDE.md: white-space = gold, competitor-gap = merchant, agri-stress = agri
  const cell=(v,color)=>{const n=Math.round(v||0); return `<td>${barHTML(n,color)} <span class="mono" style="color:${color}">${n}</span></td>`;};
  tbl.innerHTML=`<tr><th>#</th>`+
    `<th class="h-opp" title="ESTIMATED COMPOSITE (0–100): weighted blend of the three components. Higher = open here sooner. A ranking aid, not a measured quantity.">Opportunity ★ est</th>`+
    `<th>District (amphoe)</th><th>Province</th><th>Region</th>`+
    `<th title="AutoX branches inside the district (measured)">AutoX</th>`+
    `<th class="h-opp" title="MEASURED — district demand proxy minus AutoX saturation (0–100). Higher = more underserved.">White-space ★</th>`+
    `<th class="h-opp" title="MEASURED — 100 minus normalised rival-branch count (0–100). Higher = fewer competitors = more room.">Competitor-gap</th>`+
    `<th class="h-opp" title="ESTIMATED — province-inherited crop-household stress (0–100). A demand-pull signal, not a measured default rate.">Agri-stress est</th></tr>`+
    top.map((d,i)=>{
      const c=d.components||{};
      const sc=Math.round(d.score||0);
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td>${barHTML(sc,'var(--accent)')} <span class="mono" style="color:var(--accent)"><b>${sc}</b></span></td>
        <td><b>${d.name||'—'}</b></td>
        <td>${d.province||'—'}</td>
        <td class="sub">${d.region||'—'}</td>
        <td class="mono sub">${d.branches==null?'—':d.branches}</td>
        ${cell(c.whitespace,'var(--gold)')}
        ${cell(c.competitor_gap,'var(--merch)')}
        ${cell(c.agri_stress,'var(--agri)')}
      </tr>`;}).join('');
  if(ro){
    const t=top[0], m=OPPSCORE.meta||{};
    const w=m.weights_effective||m.weights_full||{};
    const wtxt=(w.whitespace!=null)?` Weights: white-space ${Math.round(w.whitespace*100)}% · competitor-gap ${Math.round((w.competitor_gap||0)*100)}% · agri-stress ${Math.round((w.agri_stress||0)*100)}%.`:'';
    ro.innerHTML=`<b>Open here next:</b> <b style="color:var(--accent)">${t.name}</b> (${t.province}, ${t.region}) tops the composite at
      <b style="color:var(--accent)">${Math.round(t.score)}</b>/100 — white-space ${Math.round((t.components||{}).whitespace||0)},
      competitor-gap ${Math.round((t.components||{}).competitor_gap||0)}, agri-stress ${Math.round((t.components||{}).agri_stress||0)}.
      <span class="sub">Top ${top.length} of ${rows.length} districts. ESTIMATED COMPOSITE — a ranking aid for expansion, not a measured quantity.${wtxt}</span>`;
  }
}

/* ---------- competitor-exit white-space · regulatory tailwind (obj #2) ----------
   Surfaces data/exit_whitespace.json (928 districts, built by pipeline/build_exit_whitespace.py).
   ESTIMATED PROXY: where AutoX could CAPTURE SHARE if marginal sub-scale operators exit under the
   Q1-2026 BoT registration deadline. We do NOT census the sub-scale operators that would exit (only
   the big-4 compliant brands), so this is INFERRED from big-4 scarcity × our demand/white-space —
   labelled ESTIMATED. We don't recompute here; just rank & expose each component. Graceful if absent. */
let EXITWS=null, exitLoaded=false;
const EXIT_TOPN=20;
function renderExitWhitespace(){
  const tbl=$('#exittbl'); if(!tbl) return;
  if(exitLoaded){ drawExitWhitespace(); return; }
  fetch('data/exit_whitespace.json').then(r=>r.ok?r.json():null).then(j=>{
    EXITWS=j; exitLoaded=true; drawExitWhitespace();
  }).catch(()=>{ EXITWS=null; exitLoaded=true; drawExitWhitespace(); });
}
function drawExitWhitespace(){
  const tbl=$('#exittbl'), ro=$('#exitreadout'); if(!tbl) return;
  const rows=(EXITWS&&Array.isArray(EXITWS.districts))?EXITWS.districts:[];
  if(!rows.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Competitor-exit white-space not yet computed.</b> <span class="sub">Run <span class="mono">pipeline/build_exit_whitespace.py</span> to populate <span class="mono">data/exit_whitespace.json</span>, then this leaderboard fills in. The regulatory thesis above still stands.</span>';
    return;
  }
  const top=rows.slice().sort((a,b)=>(b.exit_capture_score||0)-(a.exit_capture_score||0)).slice(0,EXIT_TOPN);
  const cell=(v,color)=>{const n=Math.round(v||0); return `<td>${barHTML(n,color)} <span class="mono" style="color:${color}">${n}</span></td>`;};
  tbl.innerHTML=`<tr><th>#</th>`+
    `<th class="h-opp" title="ESTIMATED capture cue (0–100): residual sub-scale demand + AutoX white-space. Higher = best place to win share if a marginal local operator exits under Q1-2026. NOT a measurement.">Exit-capture ★ est</th>`+
    `<th>District (amphoe)</th><th>Province</th><th>Region</th>`+
    `<th title="AutoX branches inside the district (measured)">AutoX</th>`+
    `<th class="h-opp" title="ESTIMATED — demand the big-4 do NOT cover (demand × thin-big-4). Higher = residual market likely served by sub-scale, exit-prone operators.">Sub-scale residual est</th>`+
    `<th class="h-opp" title="MEASURED — district demand proxy minus AutoX saturation (0–100). Higher = more underserved.">White-space ★</th>`+
    `<th title="MEASURED — big-4 rival branches inside the district (Google Places, lower bound). Lower = thinner surviving-incumbent footprint.">Big-4 ≤district</th></tr>`+
    top.map((d,i)=>{
      const c=d.components||{};
      const sc=Math.round(d.exit_capture_score||0);
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td>${barHTML(sc,'var(--accent)')} <span class="mono" style="color:var(--accent)"><b>${sc}</b></span></td>
        <td><b>${d.name||'—'}</b></td>
        <td>${d.province||'—'}</td>
        <td class="sub">${d.region||'—'}</td>
        <td class="mono sub">${d.branches==null?'—':d.branches}</td>
        ${cell(c.sub_scale_proxy,'var(--gold)')}
        ${cell(c.whitespace,'var(--merch)')}
        <td class="mono sub">${c.big4_competitors==null?'—':c.big4_competitors}</td>
      </tr>`;}).join('');
  if(ro){
    const t=top[0], m=EXITWS.meta||{}, cc=m.competitor_census||{};
    const t0=t.components||{};
    const dl=(m.regulatory_citation||{}).deadline||'Q1 2026';
    ro.innerHTML=`<b>Capture target if rivals exit:</b> <b style="color:var(--accent)">${t.name}</b> (${t.province}, ${t.region}) tops the cue at
      <b style="color:var(--accent)">${Math.round(t.exit_capture_score)}</b>/100 — sub-scale residual ${Math.round(t0.sub_scale_proxy||0)},
      white-space ${Math.round(t0.whitespace||0)}, big-4 branches ${t0.big4_competitors==null?'—':t0.big4_competitors}.
      <span class="sub">Top ${top.length} of ${rows.length} districts. ESTIMATED PROXY — inferred from big-4 scarcity (${cc.points_joined||0} censused points, brands: ${(cc.brands_censused||[]).join(' · ')||'—'}) × our white-space, NOT a measurement of sub-scale operators. Thesis: registration window closes ${dl}; marginal lenders may exit.</span>`;
  }
}

/* ---------- Road to 3,000 · regional headroom allocation ----------
   Splits the net-new branches (3,000 target − current) across the 5 regions, proportional to
   remaining headroom. Capacity proxy = regional WORKFORCE (informal+formal employment, NSO,
   measured) aggregated from data/provinces/index.json — a market-SIZE stand-in, NOT a demand or
   revenue model. Saturation = branches per 100k workforce. Headroom = the gap to the
   branches-per-100k density that the 3,000-branch target implies nationally:
     fair_share@3000 = TARGET × (region workforce / national workforce)
     headroom        = max(0, fair_share@3000 − current branches)
     alloc           = NET_NEW × (region headroom / Σ headroom)   [largest-remainder rounding → Σ = TARGET]
   Everything here is an ILLUSTRATIVE planning split, labelled as such. */
const R3K_TARGET=3000;
let r3kRows=[], r3kNet=0;
function computeRoad3k(){
  if(!PROV||!PROV.length) return null;
  const byReg={};
  PROV.forEach(p=>{const r=p.region||'—';
    const o=byReg[r]||(byReg[r]={r,branches:0,wf:0});
    o.branches+=p.branches||0;
    o.wf+=(p.informal||0)+(p.formal||0);   // workforce capacity proxy (NSO, measured); nulls treated as 0
  });
  const regs=Object.values(byReg).filter(o=>o.wf>0);
  const totBr=regs.reduce((s,o)=>s+o.branches,0);
  const totWf=regs.reduce((s,o)=>s+o.wf,0);
  if(!totWf||!totBr) return null;
  const net=Math.max(0,R3K_TARGET-totBr);
  // headroom relative to the per-workforce density implied by the 3,000 target
  regs.forEach(o=>{
    o.fair=R3K_TARGET*o.wf/totWf;
    o.headroom=Math.max(0,o.fair-o.branches);
    o.sat=o.branches/o.wf*1e5;            // branches per 100k workforce (current saturation)
  });
  const totHr=regs.reduce((s,o)=>s+o.headroom,0);
  // largest-remainder allocation so the alloc sums to exactly `net`
  if(totHr>0){
    regs.forEach(o=>{o._raw=net*o.headroom/totHr; o.alloc=Math.floor(o._raw); o._rem=o._raw-o.alloc;});
    let assigned=regs.reduce((s,o)=>s+o.alloc,0);
    regs.sort((a,b)=>b._rem-a._rem).forEach(o=>{ if(assigned<net){o.alloc++;assigned++;} });
  } else { regs.forEach(o=>o.alloc=0); }
  regs.forEach(o=>{o.targetBranches=o.branches+o.alloc;});
  regs.sort((a,b)=>b.alloc-a.alloc);
  r3kRows=regs; r3kNet=net;
  return {regs,net,totBr,totWf,totHr};
}
function renderRoad3k(){
  if(!$('#r3ktbl')) return;
  const c=computeRoad3k();
  if(!c){ $('#r3ktbl').innerHTML='<tr><td class="sub">Workforce data not available (data/provinces/index.json).</td></tr>'; return; }
  const {regs,net,totBr}=c;
  if($('#r3kcur')) $('#r3kcur').textContent=totBr.toLocaleString();
  if($('#r3knet')) $('#r3knet').textContent=net.toLocaleString();
  const mxT=Math.max(1,...regs.map(o=>o.targetBranches));   // shared scale: current & target bars comparable
  const mxA=Math.max(1,...regs.map(o=>o.alloc));
  $('#r3ktbl').innerHTML=`<tr><th>Region</th>`+
    `<th title="AutoX branches today (measured)">Now</th>`+
    `<th title="regional workforce = informal + formal employment (NSO, measured) — a market-SIZE proxy, not demand">Workforce</th>`+
    `<th title="branches per 100k workforce — lower = more headroom">Per 100k</th>`+
    `<th class="h-opp" title="gap to the branches-per-100k density that the 3,000 target implies nationally">Headroom est</th>`+
    `<th class="h-opp" title="net-new branches allocated to this region, proportional to headroom (illustrative split)">+ New</th>`+
    `<th title="now vs target (illustrative). Filled = current, outline tick = target">Now → 3,000 (target)</th>`+
    `<th title="branches at the 3,000-branch target">Target</th></tr>`+
    regs.map(o=>{
      const curW=Math.round(62*Math.min(o.branches,mxT)/mxT);
      const tgtW=Math.round(62*Math.min(o.targetBranches,mxT)/mxT);
      const ac=o.alloc>0?'var(--gold)':'var(--mid)';
      // dual bar: gold target outline behind, blue (accent) current filled in front, gold tick at target
      const dual=`<span class="bar" style="position:relative;width:62px">`+
        `<i style="position:absolute;left:0;top:0;width:${tgtW}px;background:rgba(230,180,80,.22)"></i>`+
        `<i style="position:absolute;left:0;top:0;width:${curW}px;background:var(--accent)"></i>`+
        `</span>`;
      return `<tr>
        <td><b>${o.r}</b></td>
        <td class="mono">${o.branches.toLocaleString()}</td>
        <td class="mono sub">${(o.wf/1e6).toFixed(1)}M</td>
        <td class="mono sub">${o.sat.toFixed(2)}</td>
        <td class="mono" style="color:var(--gold)">${Math.round(o.headroom).toLocaleString()}</td>
        <td>${barHTML(o.alloc,ac,mxA)} <span class="mono" style="color:${ac}">+${o.alloc}</span></td>
        <td>${dual}</td>
        <td class="mono" style="color:var(--gold)">${o.targetBranches.toLocaleString()}</td></tr>`;}).join('')+
    `<tr style="border-top:2px solid var(--line)"><td><b>Total</b></td>`+
      `<td class="mono"><b>${totBr.toLocaleString()}</b></td>`+
      `<td class="mono sub">${(c.totWf/1e6).toFixed(1)}M</td><td></td>`+
      `<td class="mono" style="color:var(--gold)"><b>${Math.round(c.totHr).toLocaleString()}</b></td>`+
      `<td class="mono" style="color:var(--gold)"><b>+${net.toLocaleString()}</b></td><td></td>`+
      `<td class="mono" style="color:var(--gold)"><b>${(totBr+net).toLocaleString()}</b></td></tr>`;
  if($('#r3kreadout')){
    const top=regs[0];
    const ranked=regs.filter(o=>o.alloc>0).map(o=>`${o.r} +${o.alloc}`).join(' · ');
    $('#r3kreadout').innerHTML=`<b>Road to 3,000:</b> add <b style="color:var(--gold)">${net.toLocaleString()}</b> branches (${totBr.toLocaleString()} → 3,000).
      Biggest share goes to <b>${top.r}</b> (<b style="color:var(--gold)">+${top.alloc}</b>) — it is furthest below the workforce-density line.
      Split: ${ranked}.
      <span class="sub">Capacity = workforce (NSO, measured); allocation is an illustrative planning proxy, not a demand model — confirm with site surveys.</span>`;
  }
  if($('#r3kcsv')&&!$('#r3kcsv').dataset.init){ $('#r3kcsv').onclick=road3kCSV; $('#r3kcsv').dataset.init='1'; }
}
function road3kCSV(){
  if(!r3kRows.length) computeRoad3k();
  const hdr=['region','branches_now_measured','workforce_informal_plus_formal_nso_measured','branches_per_100k_workforce',
    'fair_share_at_3000_proxy','headroom_est','net_new_allocated_illustrative','target_branches'];
  const lines=[hdr.join(',')].concat(r3kRows.map(o=>
    [o.r,o.branches,o.wf,o.sat.toFixed(3),Math.round(o.fair),Math.round(o.headroom),o.alloc,o.targetBranches]
      .map(v=>`"${String(v==null?'':v).replace(/"/g,'""')}"`).join(',')));
  const totBr=r3kRows.reduce((s,o)=>s+o.branches,0), totWf=r3kRows.reduce((s,o)=>s+o.wf,0), totHr=r3kRows.reduce((s,o)=>s+o.headroom,0);
  lines.push(['Total',totBr,totWf,'',R3K_TARGET,Math.round(totHr),r3kNet,totBr+r3kNet].map(v=>`"${v}"`).join(','));
  const blob=new Blob([lines.join('\n')],{type:'text/csv;charset=utf-8;'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='autox_road_to_3000.csv'; a.click(); URL.revokeObjectURL(a.href);
}

/* ---------- nationwide acquisition leaderboard (item 2) ----------
   Ranks all 2,015 branch catchments by a white-space score computed client-side from
   data already present: high demand proxy (k10 footfall + district workers + province
   pickups + precomputed 'o' opportunity) against LOW own-AutoX saturation (w = ≤10km).
   Everything here is an ESTIMATED screen, not a site-survey. */
let acqRegion='all', acqRows=[];
// White-space score v2 — a defensible screen, not a site survey. Three legs, all from data present:
//   DEMAND  (0–1, avg of 4 proxies): footfall (cvs+rest+fmkt·3), DIW district factory workers,
//           province pickup stock (title collateral), and the precomputed opportunity 'o'.
//   SATURATION penalty: own AutoX ≤10km (w) — more of our own branches = less headroom.
//   COMPETITOR penalty (proxy, labelled): nearby banks+ATMs (k10) stand in for rival financial
//           presence — we have NO national lender-branch census (only 30 hand-curated competitors
//           in Rayong), so this is an OSM financial-density proxy, NOT a competitor count.
// Score = demand × ownHeadroom × compHeadroom, scaled 0–100. Each leg returned for transparency.
function acqLegs(d){
  const pl=(typeof PLOOK!=='undefined'&&PLOOK)?(PLOOK[d.v]||{}):{};
  const k=d.k10||{};
  const foot=((k.cvs||0)+(k.rest||0)+(k.fmkt||0)*3);
  const demand=(norm(foot,ACQN.foot)+norm(d.dwork||0,ACQN.dwork)+norm(pl.pickup||0,ACQN.pickup)+norm(d.o||0,ACQN.o))/4;
  // own-AutoX headroom: 1 at zero own branches, decays toward 0.35 floor as saturation rises.
  const ownHead=0.35+0.65*(1-Math.min(1,(d.w||0)/8));
  // competitor (financial-density proxy) headroom: dense banks+ATMs => slightly less white space.
  const fin=(k.bank||0)+(k.atm||0);
  const compHead=0.6+0.4*(1-Math.min(1,fin/(ACQN.fin||1)));
  return {demand,ownHead,compHead,fin};
}
function acqScore(d){const L=acqLegs(d); return Math.round(100*L.demand*L.ownHead*L.compHead);}
let ACQN={};
function buildAcqNorms(){
  const mx=f=>Math.max(1,...DATA.map(f));
  // 90th-pct cap for the financial-density proxy so a couple of CBD outliers don't flatten everyone.
  const fins=DATA.map(d=>{const k=d.k10||{};return (k.bank||0)+(k.atm||0);}).sort((a,b)=>a-b);
  ACQN={
    foot:mx(d=>{const k=d.k10||{};return (k.cvs||0)+(k.rest||0)+(k.fmkt||0)*3;}),
    dwork:mx(d=>d.dwork||0),
    pickup:mx(d=>(PLOOK[d.v]||{}).pickup||0),
    o:mx(d=>d.o||0),
    fin:Math.max(1,fins[Math.floor(fins.length*0.9)]||1),
  };
}
function norm(v,mx){return Math.min(1,(v||0)/(mx||1));}
function renderAcqBoard(){
  if(!$('#acqboard')) return;
  buildAcqNorms();
  if(!$('#acqchips').dataset.init){
    const regions=['all',...Array.from(new Set(DATA.map(d=>d.r)))];
    $('#acqchips').innerHTML=regions.map((r,i)=>`<button class="chip ${i===0?'on':''}" data-r="${r}">${r==='all'?'All regions':r}</button>`).join('');
    $('#acqchips').onclick=e=>{const b=e.target.closest('.chip'); if(!b)return;
      $('#acqchips').querySelectorAll('.chip').forEach(c=>c.classList.toggle('on',c===b));
      acqRegion=b.dataset.r; drawAcqBoard();};
    $('#acqcsv').onclick=acqCSV; $('#acqchips').dataset.init='1';
  }
  drawAcqBoard();
  // lazily fold the competitor census into the board so "underserved" can be re-read as
  // "underserved AND undercompeted". Null-safe: if the file is absent the column shows "n/a".
  if(!compAttached) loadCompetitors().then(()=>{ if(document.getElementById('v-acq')&&document.getElementById('v-acq').classList.contains('on')) drawAcqBoard(); });
}
// Per-region ranking: which region has the most white space on average + the single best opening.
function drawAcqRegions(){
  if(!$('#acqregions')) return;
  const byReg={};
  DATA.forEach(d=>{const r=d.r||'—'; const s=acqScore(d);
    const o=byReg[r]||(byReg[r]={r,n:0,sum:0,top:null,topS:-1});
    o.n++; o.sum+=s; if(s>o.topS){o.topS=s; o.top=d;}});
  const regs=Object.values(byReg).map(o=>({...o,avg:o.sum/o.n})).sort((a,b)=>b.avg-a.avg);
  const mxAvg=Math.max(1,...regs.map(o=>o.avg));
  $('#acqregions').innerHTML=`<tr><th>#</th><th>Region</th><th>Catchments</th><th class="h-opp" title="mean white-space score across the region (est)">Avg white-space ★ est</th><th>Best single opening (est)</th></tr>`+
    regs.map((o,i)=>{const sc=o.avg>=45?'var(--gold)':o.avg>=30?'var(--merch)':'var(--mid)';
      return `<tr onclick="location.href='${branchHref(o.top)}'" tabindex="0" role="link" style="cursor:pointer">
      <td class="mono sub">${i+1}</td><td><b>${o.r}</b></td>
      <td class="mono sub">${o.n.toLocaleString()}</td>
      <td>${barHTML(o.avg,sc,mxAvg)} <span class="mono" style="color:${sc}">${o.avg.toFixed(1)}</span></td>
      <td class="sub">${o.top.n} <span class="mono" style="color:var(--gold)">★ ${o.topS}</span> · ${o.top.v}</td></tr>`;}).join('');
  // plain-language readout: lead with the answer.
  const best=regs[0], top1=acqRows[0];
  if($('#acqreadout')&&best&&top1){
    const t=top1.d, L=acqLegs(t);
    const drivers=[];
    if(L.demand>=0.4) drivers.push('strong demand signals');
    if(t.w<=2) drivers.push(`almost no own AutoX nearby (${t.w} ≤10km)`);
    else if(t.w<=5) drivers.push(`thin own coverage (${t.w} ≤10km)`);
    if((t.dwork||0)>=8000) drivers.push(`${Math.round((t.dwork||0)/1000)}k factory workers in the district`);
    const scope=acqRegion==='all'?'nationwide':`in ${acqRegion}`;
    $('#acqreadout').innerHTML=`<b>Open here next:</b> ${t.n} (${t.v}, ${t.r}) tops the screen ${scope}
      at <b style="color:var(--gold)">★ ${top1.s}</b>${drivers.length?' — '+drivers.join(', ')+'.':'.'}
      By region, <b>${best.r}</b> shows the most average white space (★ ${best.avg.toFixed(1)} across ${best.n.toLocaleString()} catchments).
      <span class="sub">Estimated screen — confirm with a site survey before committing.</span>`;
  }
}
function drawAcqBoard(){
  acqRows=DATA.filter(d=>acqRegion==='all'||d.r===acqRegion)
    .map(d=>({d, s:acqScore(d)})).sort((a,b)=>b.s-a.s).slice(0,60);
  drawAcqRegions();
  const haveComp=compHasData();
  $('#acqtbl').innerHTML=`<tr><th>#</th><th class="h-opp" title="ESTIMATED white-space screen: demand proxy × own-AutoX headroom × competitor-proxy headroom (0–100)">White-space ★ est</th><th>Branch / area</th><th>Prov</th><th>Region</th><th title="own AutoX ≤10km — lower = more headroom">AutoX ≤10km</th>`+
    `<th class="h-collat" title="MEASURED rival title-loan / vehicle-finance branches within ~5km (Google Places, a lower bound — not a registry). Low rivals + high white-space = underserved AND undercompeted.">Rivals ≤5km ◆ meas</th>`+
    `<th class="h-opp" title="DIW factory workers (measured)">Workers (DIW)</th><th title="province pickup stock (DLT)">Pickups (prov)</th><th title="banks+ATMs ≤10km (OSM) — financial-density proxy for rival presence, NOT a competitor census">Fin. density ◇ est</th></tr>`+
    acqRows.map((row,i)=>{const d=row.d, pl=PLOOK[d.v]||{}; const sc=row.s>=60?'var(--gold)':row.s>=40?'var(--merch)':'var(--mid)';
      const hd=d.w<=2?' · white space':d.w<=5?' · thin':' · covered';
      const k=d.k10||{}; const fin=(k.bank||0)+(k.atm||0);
      // competitor cell: measured count + an "undercompeted" flag when high white-space meets few rivals.
      const cn=compCount(d);
      const under = haveComp && row.s>=40 && cn===0;
      const compCell = !haveComp
        ? '<span class="sub" title="run pipeline/pull_competitors.py">n/a</span>'
        : (cn===0
            ? `<span style="color:${under?'var(--gold)':'var(--merch)'}">0${under?' ✦':''}</span>`
            : `<span style="color:var(--agri)">${cn}</span>`);
      return `<tr onclick="location.href='${branchHref(d)}'" tabindex="0" role="link" style="cursor:pointer">
      <td class="mono sub">${i+1}</td>
      <td class="mono"><a href="${branchHref(d)}" style="color:${sc};text-decoration:none">★ ${row.s}</a></td>
      <td>${d.n}<span class="sub">${hd}</span></td>
      <td class="sub">${d.v}</td><td class="sub">${d.r}</td>
      <td class="mono ${d.w<=2?'':'sub'}" style="${d.w<=2?'color:var(--gold)':''}">${d.w}</td>
      <td class="mono" title="${haveComp?compTooltip(d).replace(/"/g,'&quot;'):'no competitor data yet'}">${compCell}</td>
      <td class="mono" style="color:var(--gold)">${naNum(d.dwork)}</td>
      <td class="mono" style="color:var(--collat)">${naNum(pl.pickup)}</td>
      <td class="mono sub">${fin}</td></tr>`;}).join('');
  // honest one-line note under the board about the competitor column's provenance + meaning.
  const cnote=$('#acqcompnote');
  if(cnote){
    if(!compLoaded){ cnote.innerHTML='<span class="sub">Loading competitor census…</span>'; }
    else if(!haveComp){ cnote.innerHTML='<span class="sub"><b>Rivals ≤5km</b> is blank — no competitor census yet. Run <span class="mono">pipeline/pull_competitors.py</span> (from a Thai IP) and the column fills with measured rival-branch counts, turning "underserved" into "underserved <b>and</b> undercompeted".</span>'; }
    else {
      const flagged=acqRows.filter(row=>row.s>=40&&compCount(row.d)===0).length;
      cnote.innerHTML=`<span class="sub"><b>✦ ${flagged}</b> of the top ${acqRows.length} catchments are <b>underserved AND undercompeted</b> — high white-space with <b>zero</b> measured rival branches within ${COMP_RADIUS_KM}km. `+
        `Competitor counts are <b>measured</b> (Google Places) but a <b>lower bound</b>, not a lender registry.</span>`;
    }
  }
}
function acqCSV(){
  const haveComp=compHasData();
  const hdr=['rank','whitespace_score_est','demand_proxy_0_1_est','own_headroom_0_1_est','competitor_headroom_proxy_0_1_est','branch','province','region','own_autox_10km','rival_branches_5km_measured_lower_bound','undercompeted_flag','factory_workers_diw','province_pickups_dlt','fin_density_banks_atms_10km_est','opportunity_o_est'];
  const lines=[hdr.join(',')].concat(acqRows.map((row,i)=>{const d=row.d, pl=PLOOK[d.v]||{}; const L=acqLegs(d);
    const cn=compCount(d); const under=haveComp&&row.s>=40&&cn===0;
    return [i+1,row.s,L.demand.toFixed(3),L.ownHead.toFixed(3),L.compHead.toFixed(3),d.n,d.v,d.r,d.w,haveComp?cn:'',under?'yes':(haveComp?'no':''),d.dwork==null?'':d.dwork,pl.pickup==null?'':pl.pickup,L.fin,d.o==null?'':d.o]
      .map(v=>`"${String(v==null?'':v).replace(/"/g,'""')}"`).join(',');}));
  const blob=new Blob([lines.join('\n')],{type:'text/csv;charset=utf-8;'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='autox_acquisition_leaderboard.csv'; a.click(); URL.revokeObjectURL(a.href);
}

/* ---------- district (amphoe) white-space + risk (Step 2) ----------
   Lazy-loads data/amphoe.json (928 districts, built by pipeline/build_amphoe.py via point-in-polygon
   of branches + OSM POIs into th_amphoe.geojson). Unlike the catchment screen above (which only looks
   around our existing branches), this ranks EVERY district nationally — surfacing the 86 amphoe with no
   AutoX branch at all. Two readouts: a white-space leaderboard (acquisition) and a most-stressed risk
   list (portfolio). All scores are precomputed in the data file; we only sort/filter/label here. */
let AMP=null, ampLoaded=false, ampMeta=null, ampRegion='all', ampRRegion='all', ampRows=[], ampRRows=[];
// BAMP[i] = index into AMP[] for DATA[i] (branches.json is 1:1 with branches_final.json,
// and build_amphoe.py emits branch_amphoe in that same order). Attaching the joined
// amphoe onto each branch record (d._amp) lets the National map district lenses colour
// every marker by its district's measured white-space / estimated risk — a total join.
let BAMP=null, ampJoinAttached=false;
let ampPromise=null;
async function loadAmphoe(){
  if(ampPromise) return ampPromise;
  ampLoaded=true;
  ampPromise=(async()=>{
    try{
      const j=await fetch('data/amphoe.json').then(r=>r.json());
      AMP=j.amphoe||[]; ampMeta=j.meta||null; BAMP=j.branch_amphoe||null;
    }catch(e){ AMP=[]; }
    attachAmpToBranches();
    renderAmphoe();
    return AMP;
  })();
  return ampPromise;
}
// join the per-district record onto each branch so the map lenses can read d._amp.
function attachAmpToBranches(){
  if(ampJoinAttached||!DATA||!AMP||!BAMP) return;
  if(BAMP.length!==DATA.length) return;   // order/length mismatch → skip rather than mis-join
  for(let i=0;i<DATA.length;i++){ DATA[i]._amp = AMP[BAMP[i]] || null; }
  ampJoinAttached=true;
}
function ampChips(id,cur,onPick){
  const box=$(id); if(!box||box.dataset.init) return;
  const regions=['all',...Array.from(new Set(AMP.map(a=>a.region)))];
  box.innerHTML=regions.map(r=>`<button class="chip ${r===cur?'on':''}" data-r="${r}">${r==='all'?'All regions':r}</button>`).join('');
  box.onclick=e=>{const b=e.target.closest('.chip'); if(!b)return;
    box.querySelectorAll('.chip').forEach(c=>c.classList.toggle('on',c===b)); onPick(b.dataset.r);};
  box.dataset.init='1';
}
// readable district label: Thai name where measured, else the English shapeName.
function ampName(a){return a.name_measured?`${a.name} <span class="sub">${a.name_en}</span>`:`${a.name_en}`;}
function renderAmphoe(){
  if(!AMP||!$('#amptbl')) return;
  if(ampMeta&&$('#ampzero')) $('#ampzero').textContent=(ampMeta.n_amphoe_zero_branch||0)+' ';
  ampChips('#ampchips',ampRegion,r=>{ampRegion=r;drawAmpBoard();});
  ampChips('#amprchips',ampRRegion,r=>{ampRRegion=r;drawAmpRisk();});
  if($('#ampcsv')&&!$('#ampcsv').dataset.init){$('#ampcsv').onclick=ampCSV;$('#ampcsv').dataset.init='1';}
  drawAmpBoard(); drawAmpRisk();
  // Fold in the measured borrower-base (dominant occupation) + competitor census so the white-space
  // leaderboard reads "underserved + what borrower base + how contested". Both lazy + null-safe: if a
  // file is absent the extra cells just don't render and the original layout stands.
  const reAcq=()=>{ if(document.getElementById('v-acq')&&document.getElementById('v-acq').classList.contains('on')) drawAmpBoard(); };
  if(!aoccLoaded) loadAmphoeOccupations().then(reAcq);
  if(!compAttached) loadCompetitors().then(reAcq);
}
function drawAmpBoard(){
  ampRows=AMP.filter(a=>ampRegion==='all'||a.region===ampRegion)
    .sort((x,y)=>(y.whitespace||0)-(x.whitespace||0)).slice(0,25);
  const mx=Math.max(1,...ampRows.map(a=>a.whitespace||0));
  const haveOcc=aoccHasData();      // measured dominant-occupation per district (Overture)
  const haveComp=compHasData();     // measured rival census near the district centroid
  $('#amptbl').innerHTML=`<tr><th>#</th>`+
    `<th class="h-opp" title="ESTIMATED white-space score (0–100): district demand proxy minus an AutoX-presence penalty. Higher = more underserved.">Whitespace ★ est</th>`+
    `<th>District</th><th>Province</th><th>Region</th>`+
    `<th title="AutoX branches inside this amphoe (MEASURED, point-in-polygon). 0 = no own presence at all.">AutoX</th>`+
    (haveOcc?`<th class="h-collat" title="MEASURED dominant occupation/establishment bucket inside the district (Overture Maps Places, a sample/lower bound) — the borrower base you'd be lending into. From amphoe_occupations.json.">Borrower base ◆ meas</th>`:'')+
    (haveComp?`<th class="h-collat" title="MEASURED rival title-loan / vehicle-finance branches within ~${COMP_RADIUS_KM}km of the district centre (Google Places ∪ Overture, a lower bound — not a registry). Low rivals + high white-space = underserved AND undercompeted.">Rivals ≤${COMP_RADIUS_KM}km ◆ meas</th>`:'')+
    `<th class="h-opp" title="DIW factory workers in the district (MEASURED where ✓; — where the district name didn't resolve to DIW)">Workers (DIW)</th>`+
    `<th title="convenience stores + restaurants inside the amphoe (OSM, MEASURED) — merchant footfall proxy">Merchant POI ◇</th>`+
    `<th title="gold shops + vehicle dealers inside the amphoe (OSM, MEASURED) — title/gold-collateral demand proxy">Collat POI ◇</th></tr>`+
    ampRows.map((a,i)=>{const ws=a.whitespace||0; const sc=ws>=50?'var(--gold)':ws>=35?'var(--merch)':'var(--mid)';
      const p=a.poi||{}; const merch=(p.cvs||0)+(p.rest||0); const collat=(p.gold||0)+(p.veh||0);
      const wkr=a.fac_measured?`<span style="color:var(--gold)">${(a.workers||0).toLocaleString()}</span> <span class="sub" title="DIW-measured at this district">✓</span>`:`<span class="sub" title="district name did not resolve to a DIW record">—</span>`;
      const hd=a.branches===0?' · no AutoX':a.branches<=1?' · thin':'';
      // borrower-base cell: dominant occupation bucket + its share (measured). "—" where Overture is thin here.
      let occCell='';
      if(haveOcc){
        const dom=ampDomOcc(a);
        if(dom){const sh=ampDomShare(a); occCell=`<td style="color:var(--collat)">${dom}${sh>=0.2?` <span class="sub mono">${Math.round(sh*100)}%</span>`:''}</td>`;}
        else occCell=`<td class="sub" title="no Overture establishment points landed in this district">—</td>`;
      }
      // contested cell: rival branches near the district centre. ✦ = underserved AND undercompeted.
      let compCell='';
      if(haveComp){
        const cn=ampCompCount(a); const under=ws>=35&&cn===0;
        compCell=`<td class="mono" title="${ampCompTooltip(a)}">`+(cn===0
          ? `<span style="color:${under?'var(--gold)':'var(--merch)'}">0${under?' ✦':''}</span>`
          : `<span style="color:var(--agri)">${cn}</span>`)+`</td>`;
      }
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td>${barHTML(ws,sc,mx)} <span class="mono" style="color:${sc}">${ws.toFixed(0)}</span></td>
        <td>${ampName(a)}<span class="sub">${hd}</span></td>
        <td class="sub">${a.province_th}</td><td class="sub">${a.region}</td>
        <td class="mono ${a.branches===0?'':'sub'}" style="${a.branches===0?'color:var(--gold)':''}">${a.branches}</td>
        ${occCell}${compCell}
        <td class="mono">${wkr}</td>
        <td class="mono" style="color:var(--merch)">${merch.toLocaleString()}</td>
        <td class="mono" style="color:var(--collat)">${collat.toLocaleString()}</td></tr>`;}).join('');
  // plain-language readout: lead with the answer.
  if($('#ampreadout')){
    const top=ampRows[0]; const zeros=ampRows.filter(a=>a.branches===0).length;
    const scope=ampRegion==='all'?'nationwide':`in ${ampRegion}`;
    if(top){
      const drivers=[];
      if(top.branches===0) drivers.push('no AutoX branch there yet');
      else drivers.push(`only ${top.branches} AutoX inside`);
      if(top.fac_measured&&(top.workers||0)>=5000) drivers.push(`${Math.round((top.workers||0)/1000)}k DIW factory workers`);
      // borrower base + how contested — the "what + how" half of the answer (both measured when present).
      const dom=ampDomOcc(top); if(dom) drivers.push(`borrower base mostly <b>${dom.toLowerCase()}</b>`);
      const cn=ampCompCount(top);
      if(cn===0) drivers.push('<b>zero</b> rival branches nearby (undercompeted)');
      else if(cn!=null) drivers.push(`${cn} rival branch${cn===1?'':'es'} nearby`);
      $('#ampreadout').innerHTML=`<b>Most underserved district ${scope}:</b> ${top.name_measured?top.name:''} ${top.name_en} (${top.province_th}, ${top.region})
        at <b style="color:var(--gold)">★ ${(top.whitespace||0).toFixed(0)}</b> — ${drivers.join(', ')}.
        ${zeros?`<b>${zeros}</b> of the top 25 ${scope} have <b>zero AutoX presence</b>. `:''}
        <span class="sub">Estimated white-space; borrower base &amp; rival counts measured (Overture / Google Places, lower bounds). Confirm with a site survey.</span>`;
    }
  }
}
function drawAmpRisk(){
  ampRRows=AMP.filter(a=>ampRRegion==='all'||a.region===ampRRegion)
    .sort((x,y)=>(y.risk_proxy||0)-(x.risk_proxy||0)).slice(0,25);
  const mx=Math.max(1,...ampRRows.map(a=>a.risk_proxy||0));
  $('#amprtbl').innerHTML=`<tr><th>#</th>`+
    `<th class="h-opp" title="ESTIMATED risk proxy (0–100): 0.5·agri crop-stress + collateral/merchant pressure. NOT a measured default rate.">Risk ▲ est</th>`+
    `<th>District</th><th>Province</th><th>Region</th>`+
    `<th title="province-mean agri crop-stress (price proxy × drought) — PROVINCE-INHERITED, not amphoe-measured">Agri stress ▲ est</th>`+
    `<th title="AutoX branches inside this amphoe (MEASURED) — footprint exposed to the stress">AutoX</th></tr>`+
    ampRRows.map((a,i)=>{const rk=a.risk_proxy||0; const sc=rk>=60?'var(--agri)':rk>=45?'#D9742B':'var(--mid)';
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td>${barHTML(rk,sc,mx)} <span class="mono" style="color:${sc}">${rk.toFixed(0)}</span></td>
        <td>${ampName(a)}</td>
        <td class="sub">${a.province_th}</td><td class="sub">${a.region}</td>
        <td class="mono" style="color:var(--agri)">${(a.agri_stress||0).toFixed(0)} <span class="sub" title="province-inherited">prov</span></td>
        <td class="mono ${a.branches?'':'sub'}">${a.branches}</td></tr>`;}).join('');
}
function ampCSV(){
  const rows=AMP.filter(a=>ampRegion==='all'||a.region===ampRegion)
    .sort((x,y)=>(y.whitespace||0)-(x.whitespace||0));
  const hdr=['rank','whitespace_score_est','district_th','district_en','province','region','autox_branches_measured',
    'dominant_occupation_measured_overture','dominant_occupation_share','rival_branches_5km_centroid_measured_lower_bound',
    'diw_workers','diw_workers_measured','merchant_poi_cvs_rest_measured','collateral_poi_gold_veh_measured',
    'demand_proxy_est','risk_proxy_est','agri_stress_province_inherited'];
  const lines=[hdr.join(',')].concat(rows.map((a,i)=>{const p=a.poi||{};
    const dom=ampDomOcc(a); const sh=ampDomShare(a); const cn=ampCompCount(a);
    return [i+1,(a.whitespace||0).toFixed(1),a.name_measured?a.name:'',a.name_en,a.province_th,a.region,a.branches,
      dom||'',dom?sh.toFixed(3):'',cn==null?'':cn,
      a.fac_measured?(a.workers||0):'',a.fac_measured?'true':'false',(p.cvs||0)+(p.rest||0),(p.gold||0)+(p.veh||0),
      (a.demand||0).toFixed(1),(a.risk_proxy||0).toFixed(1),(a.agri_stress||0).toFixed(1)]
      .map(v=>`"${String(v==null?'':v).replace(/"/g,'""')}"`).join(',');}));
  const blob=new Blob([lines.join('\n')],{type:'text/csv;charset=utf-8;'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='autox_district_whitespace.csv'; a.click(); URL.revokeObjectURL(a.href);
}

/* ---------- portfolio exposure / concentration (item 3) ----------
   "How much of the book sits in stressed-crop / drought / weak-segment provinces."
   Book proxy = branch count (we have no per-branch ฿ balance), labelled honestly.
   Uses branch fields already present: r (region), rain (drought proxy), a/m/c risk proxies,
   and the region's weakest-crop YoY from the commodity board. */
function renderExposure(){
  if(!DATA||!$('#expocards')||!$('#expotbl')) return;
  const N=DATA.length;
  const pctS=n=>(100*n/N).toFixed(1)+'%';
  // 1) stressed-crop exposure: branches whose region's weakest crop is in price stress (YoY < -10%)
  const stressed=DATA.filter(d=>{const wc=regionWorstCrop(d.r); return wc && wc.yoy<-10;});
  // 2) drought proxy: branches with low recent rainfall (bottom quartile of 'rain')
  const rains=DATA.map(d=>d.rain).filter(v=>v!=null).sort((a,b)=>a-b);
  const q1=rains.length?rains[Math.floor(rains.length*0.25)]:0;
  const drought=DATA.filter(d=>d.rain!=null && d.rain<=q1);
  // 3) weak-segment (high estimated agri-PD proxy >=60)
  const weakAgri=DATA.filter(d=>(d.a||0)>=60);
  // Herfindahl-Hirschman concentration of the footprint across provinces (book proxy = branch count).
  // HHI = sum of squared province shares. Reported on the 0–10,000 scale (×share-in-%²) like a regulator
  // would read it: <1500 unconcentrated, 1500–2500 moderate, >2500 concentrated.
  const byProvN={};
  DATA.forEach(d=>{const v=d.v||'—'; byProvN[v]=(byProvN[v]||0)+1;});
  const provCount=Object.keys(byProvN).length;
  const hhi=Object.values(byProvN).reduce((s,n)=>s+Math.pow(100*n/N,2),0);
  const hhiLabel=hhi<1500?'unconcentrated':hhi<2500?'moderate':'concentrated';
  const hhiCol=hhi<1500?'var(--merch)':hhi<2500?'var(--gold)':'var(--agri)';
  const cards=[
    ['Stressed-crop regions', stressed.length, pctS(stressed.length), 'Region weakest crop in price stress (World Bank YoY < −10%, direction proxy)', 'var(--agri)','▼'],
    ['Drought-proxy (dry quartile)', drought.length, pctS(drought.length), 'Branch in the driest 25% by recent rainfall (HDX proxy)', 'var(--gold)','☀'],
    ['High agri-PD proxy', weakAgri.length, pctS(weakAgri.length), 'Estimated agri-PD risk proxy ≥ 60 (OSM/price-based, not measured)', 'var(--agri)','▲'],
  ];
  $('#expocards').innerHTML=
    `<div class="mcard"><div class="k">◆ Geographic concentration (HHI)</div>
       <div class="v" style="color:${hhiCol}">${Math.round(hhi).toLocaleString()}</div>
       <div class="n">${hhiLabel} · footprint spread over ${provCount} provinces · book proxy = branch count</div></div>`+
    cards.map(([k,n,p,note,col,gl])=>
    `<div class="mcard"><div class="k">${gl} ${k}</div><div class="v" style="color:${col}">${p}</div>
     <div class="n">${n.toLocaleString()} of ${N.toLocaleString()} branches · ${note}</div></div>`).join('');
  // per-region concentration table
  const byReg={};
  DATA.forEach(d=>{const r=d.r||'—'; const o=byReg[r]||(byReg[r]={n:0,str:0,dry:0,agri:0});
    o.n++; const wc=regionWorstCrop(r); if(wc&&wc.yoy<-10)o.str++; if(d.rain!=null&&d.rain<=q1)o.dry++; if((d.a||0)>=60)o.agri++;});
  // top exposed provinces: count branches carrying ≥1 stress flag, rank by that count.
  if($('#expoprov')){
    const byProv={};
    DATA.forEach(d=>{const v=d.v||'—'; const o=byProv[v]||(byProv[v]={v,r:d.r||'—',n:0,flag:0,str:0,dry:0,agri:0});
      o.n++; const wc=regionWorstCrop(d.r); const sf=wc&&wc.yoy<-10; const df=d.rain!=null&&d.rain<=q1; const af=(d.a||0)>=60;
      if(sf)o.str++; if(df)o.dry++; if(af)o.agri++; if(sf||df||af)o.flag++;});
    const provs=Object.values(byProv).sort((a,b)=>b.flag-a.flag||b.n-a.n).slice(0,15);
    $('#expoprov').innerHTML=`<tr><th>#</th><th>Province</th><th>Region</th><th>Branches</th><th class="h-agri" title="branches carrying ≥1 stress flag (est)">Exposed (est)</th><th title="exposed share of the province's branches">Share</th><th>Flags</th></tr>`+
      provs.map((o,i)=>{const sh=o.n?100*o.flag/o.n:0; const fc=sh>=66?'var(--agri)':sh>=33?'var(--gold)':'var(--mid)';
        const fl=[o.str?'▼crop':'',o.dry?'☀dry':'',o.agri?'▲agri':''].filter(Boolean).join(' · ');
        return `<tr><td class="mono sub">${i+1}</td><td><b>${o.v}</b></td><td class="sub">${o.r}</td>
        <td class="mono">${o.n}</td><td class="mono" style="color:${fc}">${o.flag}</td>
        <td class="mono" style="color:${fc}">${sh.toFixed(0)}%</td><td class="sub">${fl||'—'}</td></tr>`;}).join('');
  }
  const regs=Object.entries(byReg).sort((a,b)=>b[1].n-a[1].n);
  $('#expotbl').innerHTML=`<tr><th>Region</th><th>Branches</th><th class="h-agri" title="share in stressed-crop region (est)">Stressed-crop ▼ est</th><th class="h-opp" title="share in dry quartile (est)">Drought ☀ est</th><th class="h-agri" title="share with high agri-PD proxy (est)">High agri-PD ▲ est</th></tr>`+
    regs.map(([r,o])=>{const wc=regionWorstCrop(r);
      return `<tr><td><b>${r}</b>${wc?` <span class="sub">${wc.lab} ${wc.yoy>0?'+':''}${wc.yoy}%</span>`:''}</td>
      <td class="mono">${o.n}</td>
      <td class="mono" style="color:${o.str/o.n>0.5?'var(--agri)':'var(--mid)'}">${(100*o.str/o.n).toFixed(0)}%</td>
      <td class="mono" style="color:${o.dry/o.n>0.3?'var(--gold)':'var(--mid)'}">${(100*o.dry/o.n).toFixed(0)}%</td>
      <td class="mono" style="color:${o.agri/o.n>0.3?'var(--agri)':'var(--mid)'}">${(100*o.agri/o.n).toFixed(0)}%</td></tr>`;}).join('');
  // OBJECTIVE #1: borrower-base concentration — is the book over-exposed to one occupation type?
  renderOccConcentration();
}

/* ---------- borrower-base (occupation) concentration · objective #1 ----------
   Sums each occupation bucket across ALL branches' ≤10km establishment mix (branch_occupations.json,
   MEASURED via Overture), normalizes to shares, and computes an HHI-style concentration so the exec
   can see whether the book leans on ONE borrower-base type (e.g. factory workers) vs a diversified mix.
   Lazy + graceful: with no branch_occupations.json the block renders nothing (the section just shows the
   existing geographic concentration). The DOM host is created once and inserted after #expocards so no
   index.html change is needed. Book proxy = establishment-mix counts, NOT ฿ balances — labelled. */
function occHost(){
  let h=document.getElementById('expo-occ');
  if(h) return h;
  const cards=$('#expocards'); if(!cards||!cards.parentNode) return null;
  h=document.createElement('div'); h.id='expo-occ';
  cards.parentNode.insertBefore(h,cards.nextSibling);   // directly under the concentration cards
  return h;
}
function renderOccConcentration(){
  const host=occHost(); if(!host) return;
  // lazy-load on first paint, then re-render once data lands.
  if(!occLoaded){ loadOccupations().then(()=>{ if(document.getElementById('v-exposure')&&document.getElementById('v-exposure').classList.contains('on')) renderOccConcentration(); }); }
  if(!OCCDATA||!OCCDATA.buckets||!OCCDATA.branches){ host.innerHTML=''; return; }  // graceful: render nothing
  const buckets=OCCDATA.buckets;
  const sums=new Array(buckets.length).fill(0); let tot=0;
  OCCDATA.branches.forEach(e=>{ if(e&&Array.isArray(e.o)) e.o.forEach((v,i)=>{ const n=v||0; sums[i]+=n; tot+=n; }); });
  if(!tot){ host.innerHTML=''; return; }
  // shares (%), HHI on the 0–10,000 regulator scale (Σ share-in-%²).
  const rows=buckets.map((b,i)=>({key:b.key,label:b.label||occLabel(b.key),n:sums[i],sh:100*sums[i]/tot}))
    .sort((x,y)=>y.n-x.n);
  const hhi=rows.reduce((s,r)=>s+r.sh*r.sh,0);
  const hhiLabel=hhi<1500?'diversified borrower base':hhi<2500?'moderately concentrated':'concentrated — over-exposed to one base';
  const hhiCol=hhi<1500?'var(--merch)':hhi<2500?'var(--gold)':'var(--agri)';
  const top=rows[0];
  const col=k=>OCC_BUCKET_COL[k]||'var(--accent)';
  const barRows=rows.filter(r=>r.n>0).slice(0,10).map(r=>{
    const w=Math.round(180*r.sh/Math.max(1,top.sh));
    return `<div class="cc-row"><div class="l">${r.label}<span class="s">${r.n.toLocaleString()} establishments ≤10km</span></div>`+
      `<div class="r" style="min-width:230px"><span class="bar" style="width:180px;display:inline-block"><i style="width:${w}px;background:${col(r.key)}"></i></span> `+
      `<span class="mono" style="color:${col(r.key)}">${r.sh.toFixed(1)}%</span></div></div>`;
  }).join('');
  host.innerHTML=
    `<h2 class="risk" style="margin-top:18px">Borrower-base concentration ${TAG_M}</h2>`+
    `<p class="lead">Sum of each occupation/establishment bucket across all ${OCCDATA.branches.length.toLocaleString()} branch catchments `+
    `(≤10km, Overture Maps Places — <b>measured</b>, a sample/lower bound). Shows whether the book leans on <i>one</i> borrower-base `+
    `type. <b>Book proxy = establishment mix</b>, not ฿ balances. HHI on the 0–10,000 scale: &lt;1500 diversified · 1500–2500 moderate · &gt;2500 concentrated.</p>`+
    `<div class="grid macro">`+
      `<div class="mcard"><div class="k">◆ Borrower-base HHI</div>`+
        `<div class="v" style="color:${hhiCol}">${Math.round(hhi).toLocaleString()}</div>`+
        `<div class="n">${hhiLabel} · across ${rows.filter(r=>r.n>0).length} occupation buckets</div></div>`+
      `<div class="mcard"><div class="k">▲ Largest single base</div>`+
        `<div class="v" style="color:${col(top.key)}">${top.sh.toFixed(1)}%</div>`+
        `<div class="n">${top.label} · ${top.n.toLocaleString()} establishments ≤10km (measured)</div></div>`+
    `</div>`+
    `<div class="cc-card-b" style="margin-top:10px">${barRows}</div>`;
}

/* ---------- scenario simulator (client-side what-if) ----------
   An ILLUSTRATIVE sensitivity the exec can drive with sliders — NOT a forecast. It re-runs the
   SAME estimated agri-stress proxy already shipped in crop_stress.json under a crop-price + rainfall
   shock, recomputing per-province agri_stress from the published formula (so it stays consistent with
   the rest of the site). It counts how many provinces / branches tip into "high agri-stress" (≥45/100),
   reads collateral recovery-value DIRECTION from the gold + used-vehicle sliders, and surfaces the
   provinces that worsen most. Deterministic. Exposure = branch footprint (no per-branch ฿ balance / LTV /
   elasticities — all stated). Reuses crop_stress.json (lazy) + branches.json; no new data, no server. */
const SIM_HI=45; // high-agri-stress threshold on the 0–100 scale (matches the red cut in renderCropStress)
const simState={price:0,rain:0,gold:0,veh:0,botcap:false};
let simWired=false;

/* ---------- BoT 28% title-loan rate-cap scenario (objective #1) ----------
   REGULATORY FACT (cited): the Bank of Thailand title-loan / personal-loan interest ceiling is
   28% APR, effective 2 Dec 2025 (Royal Decree 5 Jun 2025 → FIBA / direct BoT supervision; BoT
   notification 25680030). Source: docs/RESEARCH_DIGEST.md (2026-06-30, Entry 1A); primary:
   https://www.bot.or.th/content/dam/bot/fipcs/documents/FPG/2568/EngPDF/25680030.pdf
   ⛔ NOT a measured book. This is a SCENARIO MODEL: the product buckets below — their assumed
   effective APR and assumed share of the book — are ESTIMATED illustrative LEVERS the exec can
   reason about, NOT AutoX's actual loan tape. When a real loan tape lands (loan_tape_derived.json),
   replace SIM_CAP_BOOK with measured product yields + balances. Math is deliberately simple:
   book yield = share-weighted APR; under the cap each bucket's APR = min(APR, 28). Buckets ALREADY
   at/below 28% are unaffected; only the high-rate tail compresses. */
const SIM_CAP_RATE=28; // % APR — the BoT title-loan ceiling (cited fact, not an assumption)
// Illustrative title-loan book mix. share = % of book; apr = assumed effective APR (%). ASSUMPTIONS.
const SIM_CAP_BOOK=[
  {seg:'Motorcycle title',     apr:33, share:30},
  {seg:'Pickup / car title',   apr:26, share:34},
  {seg:'Land / house title',   apr:22, share:18},
  {seg:'Agri-vehicle title',   apr:31, share:10},
  {seg:'Top-up / small-ticket',apr:30, share:8},
];
// Compute book yield before vs after the 28% cap from the illustrative mix above. Pure + deterministic.
function simCapModel(){
  const tot=SIM_CAP_BOOK.reduce((s,b)=>s+b.share,0)||1;
  let yBase=0, yCap=0;
  const rows=SIM_CAP_BOOK.map(b=>{
    const w=b.share/tot;
    const capped=Math.min(b.apr,SIM_CAP_RATE);
    yBase+=w*b.apr; yCap+=w*capped;
    return {seg:b.seg,share:b.share,apr:b.apr,capped,compress:b.apr>SIM_CAP_RATE,drop:b.apr-capped};
  });
  return {rows,yBase,yCap,drop:yBase-yCap};
}
// recompute one province's agri_stress (0..1) from its published components under a price/rain shock.
// Mirrors crop_stress.json meta.formula EXACTLY so the baseline (shock=0) reproduces the shipped value.
function simAgriStress(p,priceShock,rainShock){
  const c=p.components||{};
  // price_stress is a YoY %; a negative crop-price shock makes it more negative (deeper income squeeze).
  const ps=(p.price_stress==null?0:p.price_stress)+priceShock;
  const priceTerm=Math.max(0,Math.min(1,-ps/25));
  // rain shock shifts rainfall as % of normal; drier (lower %) raises drought hazard.
  const rain=(c.rain_pct_of_normal==null?100:c.rain_pct_of_normal)+rainShock;
  const droughtTerm=Math.max(0,Math.min(1,(100-rain)/40));
  const hazard=0.6*priceTerm+0.4*droughtTerm;
  return hazard*(p.crop_dependence==null?0:p.crop_dependence);
}
// branch count per province (book proxy) — built once from DATA.
let SIM_BRN=null;
function simBranchByProv(){
  if(SIM_BRN) return SIM_BRN;
  SIM_BRN={}; (DATA||[]).forEach(d=>{const v=d.v||'—'; SIM_BRN[v]=(SIM_BRN[v]||0)+1;});
  return SIM_BRN;
}
function renderSim(){
  if(!simWired) wireSim();
  loadCropStress().then(()=>{ if(document.getElementById('v-sim').classList.contains('on')) computeSim(); });
}
function wireSim(){
  simWired=true;
  const bind=(id,key,fmt)=>{const inp=$(id); if(!inp) return;
    inp.oninput=()=>{simState[key]=+inp.value; const lab=$(id+'-v'); if(lab&&fmt) lab.textContent=fmt(+inp.value); computeSim();};};
  bind('#sim-price','price',v=>(v>0?'+':'')+v+'%');
  bind('#sim-rain','rain',v=>v===0?'normal':(v>0?'wetter +':'drier ')+v+'%');
  bind('#sim-gold','gold',v=>(v>0?'+':'')+v+'%');
  bind('#sim-veh','veh',v=>(v>0?'+':'')+v+'%');
  const bot=$('#sim-botcap'); if(bot) bot.onchange=()=>{simState.botcap=bot.checked; computeSim();};
  const rs=$('#sim-reset'); if(rs) rs.onclick=simReset;
}
function simReset(){
  simState.price=0; simState.rain=0; simState.gold=0; simState.veh=0; simState.botcap=false;
  const set=(id,v)=>{const e=$(id); if(e) e.value=v;};
  set('#sim-price',0); set('#sim-rain',0); set('#sim-gold',0); set('#sim-veh',0);
  const bot=$('#sim-botcap'); if(bot) bot.checked=false;
  $('#sim-price-v')&&($('#sim-price-v').textContent='0%');
  $('#sim-rain-v')&&($('#sim-rain-v').textContent='normal');
  $('#sim-gold-v')&&($('#sim-gold-v').textContent='0%');
  $('#sim-veh-v')&&($('#sim-veh-v').textContent='0%');
  computeSim();
}
function computeSim(){
  if(!$('#sim-cards')) return;
  if(!CSTRESS_LIST||!CSTRESS_LIST.length){
    $('#sim-cards').innerHTML='';
    $('#sim-readout').innerHTML='Crop-stress data not available (data/crop_stress.json missing) — the agri what-if needs it. The BoT rate-cap scenario below still works (it needs no data file).';
    $('#sim-prov').innerHTML=''; renderSimCollat(); renderSimCap(); return;
  }
  const brn=simBranchByProv();
  const {price,rain}=simState;
  // baseline (shock=0) vs scenario, per province
  let baseHiP=0, scenHiP=0, baseHiBr=0, scenHiBr=0, newBr=0;
  const rows=CSTRESS_LIST.map(p=>{
    const base=simAgriStress(p,0,0)*100;
    const scen=simAgriStress(p,price,rain)*100;
    const br=brn[p.th]||0;
    const baseHi=base>=SIM_HI, scenHi=scen>=SIM_HI;
    if(baseHi){baseHiP++; baseHiBr+=br;}
    if(scenHi){scenHiP++; scenHiBr+=br;}
    if(scenHi&&!baseHi) newBr+=br;
    return {th:p.th,region:p.region,base,scen,delta:scen-base,br,baseHi,scenHi,isNew:scenHi&&!baseHi};
  });
  const N=(DATA||[]).length||1;
  const dP=scenHiP-baseHiP, dBr=scenHiBr-baseHiBr;
  const shocked=(price!==0||rain!==0);
  // ----- summary cards -----
  const dCol=v=>v>0?'var(--agri)':v<0?'var(--up)':'var(--mid)';
  const sign=v=>(v>0?'+':'')+v;
  const cards=[
    {k:'High agri-stress provinces',v:`${scenHiP}`,
     d:shocked?`${sign(dP)} vs base (${baseHiP})`:`baseline (${baseHiP})`,col:dCol(dP),
     n:'Provinces with the ESTIMATED agri-stress proxy ≥45/100 under the scenario. What-if, not a forecast.'},
    {k:'Branches in high-stress provinces',v:`${scenHiBr.toLocaleString()}`,
     d:shocked?`${sign(dBr)} vs base (${baseHiBr.toLocaleString()})`:`baseline (${baseHiBr.toLocaleString()})`,col:dCol(dBr),
     n:'Footprint exposure = branch count (no per-branch ฿ balance). Branch counts MEASURED; stress flag ESTIMATED.'},
    {k:'Newly-stressed exposure',v:`${(100*newBr/N).toFixed(1)}%`,
     d:`${newBr.toLocaleString()} branches tip in`,col:newBr>0?'var(--agri)':'var(--mid)',
     n:'Share of all '+N.toLocaleString()+' branches that move into a newly high-stress province because of this shock.'},
  ];
  $('#sim-cards').innerHTML=cards.map(c=>`<div class="mcard"><div class="k">${c.k}</div>
    <div class="v" style="color:${c.col}">${c.v}</div>
    <div class="d" style="color:${c.col}">${c.d}</div>
    <div class="n">${c.n}</div></div>`).join('');
  // ----- plain-language readout (lead with the answer) -----
  let read;
  if(!shocked){
    read=`<b>No crop shock set.</b> At baseline, <b>${baseHiP}</b> provinces (<b>${baseHiBr.toLocaleString()}</b> branches) sit in high agri-stress. `+
      `Drag the crop-price or rainfall slider to see who tips in.`;
  } else {
    const worse=rows.filter(r=>r.isNew).sort((a,b)=>b.delta-a.delta);
    const lead=worse[0];
    read=`<b>Under this what-if:</b> high agri-stress provinces go from <b>${baseHiP}</b> to <b style="color:${dCol(dP)}">${scenHiP}</b> `+
      `(${sign(dP)}), and the exposed footprint from <b>${baseHiBr.toLocaleString()}</b> to <b style="color:${dCol(dBr)}">${scenHiBr.toLocaleString()}</b> branches `+
      `(<b>${(100*scenHiBr/N).toFixed(1)}%</b> of the network). `+
      (lead?`<b>${worse.length}</b> province${worse.length===1?'':'s'} newly tip in — worst is <b>${lead.th}</b> (${lead.region||'—'}, +${lead.delta.toFixed(0)} pts). `:`No new province crosses the high-stress line. `);
  }
  if(simState.botcap){
    const cap=simCapModel();
    const compress=cap.rows.filter(r=>r.compress).sort((a,b)=>b.drop-a.drop);
    const segList=compress.map(r=>`<b>${r.seg}</b> (${r.apr}%→28%)`).join(', ');
    read+=`<br><br><b style="color:var(--gold)">⚖ BoT 28% rate cap (effective 2 Dec 2025):</b> `+
      `book yield <b>${cap.yBase.toFixed(1)}%</b> → <b style="color:var(--agri)">${cap.yCap.toFixed(1)}%</b> `+
      `(<b style="color:var(--agri)">−${cap.drop.toFixed(1)} pts</b> of yield). `+
      (compress.length
        ? `Products priced above 28% compress to the ceiling: ${segList}. Buckets already ≤28% are unaffected.`
        : `No product is priced above 28% in this illustrative mix — the cap is non-binding.`);
    read+=`<br><span class="sub">⛔ SCENARIO MODEL — illustrative product mix &amp; APRs are ASSUMPTIONS (levers), not AutoX's measured loan tape. `+
      `28% ceiling is a cited regulatory fact (BoT notification 25680030 · Royal Decree 5 Jun 2025).</span>`;
  }
  read+=`<br><span class="sub">ILLUSTRATIVE sensitivity — same estimated proxy, no measured elasticities / loan balances / LTV. A direction, not a number.</span>`;
  $('#sim-readout').innerHTML=read;
  renderSimCap();
  // ----- worsening provinces table -----
  const tbl=$('#sim-prov');
  if(tbl){
    if(!shocked){ tbl.innerHTML='<tr><td class="sub" style="padding:10px">Move a crop-price or rainfall slider to rank the provinces that worsen.</td></tr>'; }
    else {
      const worse=rows.filter(r=>r.delta>0.5).sort((a,b)=>b.delta-a.delta).slice(0,15);
      if(!worse.length){ tbl.innerHTML='<tr><td class="sub" style="padding:10px">No province worsens materially under this shock.</td></tr>'; }
      else {
        const mx=Math.max(1,...worse.map(r=>r.delta));
        tbl.innerHTML=`<tr><th>#</th><th>Province</th><th>Region</th><th title="AutoX branches — measured footprint">Branches</th>`+
          `<th class="h-agri" title="ESTIMATED agri-stress proxy before the shock (0–100)">Base ▲ est</th>`+
          `<th class="h-agri" title="ESTIMATED agri-stress proxy under the shock (0–100)">Scenario ▲ est</th>`+
          `<th class="h-agri" title="rise in the estimated agri-stress proxy">Δ est</th><th>Status</th></tr>`+
          worse.map((r,i)=>{const sc=r.scen>=SIM_HI?'var(--agri)':r.scen>=25?'var(--gold)':'var(--mid)';
            const tag=r.isNew?'<span class="mono" style="color:var(--agri)">↑ NEW high</span>':r.scenHi?'<span class="mono" style="color:var(--gold)">stays high</span>':'<span class="sub">elevated</span>';
            return `<tr><td class="mono sub">${i+1}</td><td><b>${r.th}</b></td><td class="sub">${r.region||'—'}</td>
            <td class="mono">${r.br}</td>
            <td class="mono sub">${r.base.toFixed(0)}</td>
            <td>${barHTML(r.scen,sc)} <span class="mono" style="color:${sc}">${r.scen.toFixed(0)}</span></td>
            <td class="mono" style="color:var(--agri)">+${r.delta.toFixed(0)}</td>
            <td>${tag}</td></tr>`;}).join('');
      }
    }
  }
  renderSimCollat();
}
// collateral recovery-value DIRECTION from the gold + used-vehicle sliders (illustrative, no balances).
function renderSimCollat(){
  const box=$('#sim-collat'); if(!box) return;
  const {gold,veh}=simState;
  const dir=(v,upTxt,dnTxt)=>v>0?{t:upTxt,cls:'up',col:'var(--up)',a:'▲'}:v<0?{t:dnTxt,cls:'down',col:'var(--agri)',a:'▼'}:{t:'unchanged',cls:'',col:'var(--mid)',a:'•'};
  const g=dir(gold,'recovery value ↑','recovery value ↓');
  const v=dir(veh,'recovery value ↓ · LGD ↑','recovery value ↑ · LGD ↓');
  // for vehicles a NEGATIVE move is the bad case, so flip the colour logic
  const vCol=veh<0?'var(--agri)':veh>0?'var(--up)':'var(--mid)';
  const cards=[
    {k:'Gold collateral',v:(gold>0?'+':'')+gold+'%',d:g.a+' '+g.t,col:g.col,
     n:'ILLUSTRATIVE move applied to gold-backed recovery value. Baseline gold direction (measured) is +62.7% YoY on the board.'},
    {k:'Used-vehicle collateral',v:(veh>0?'+':'')+veh+'%',d:(veh<0?'▼':veh>0?'▲':'•')+' '+v.t,col:vCol,
     n:'ILLUSTRATIVE move on used motorcycle/pickup resale — the title-book backing. Down lowers recovery (loss-given-default rises). No LTV/balances.'},
    {k:'Net collateral read',
     v:(gold>=0&&veh>=0)?'firming':(gold<0&&veh<0)?'softening':'mixed',
     d:'direction only',
     col:(gold<0&&veh<0)?'var(--agri)':(gold>0&&veh>=0)||(gold>=0&&veh>0)?'var(--up)':'var(--mid)',
     n:'Qualitative net of the two backings. Gold up + vehicles down = the divergence AutoX already faces. No portfolio ฿ figure — illustrative.'},
  ];
  box.innerHTML=cards.map(c=>`<div class="mcard"><div class="k">${c.k}</div>
    <div class="v" style="color:${c.col}">${c.v}</div>
    <div class="d" style="color:${c.col}">${c.d}</div>
    <div class="n">${c.n}</div></div>`).join('');
}
// BoT 28% rate-cap readout: headline yield cards + which products compress. Only shown when toggled ON.
function renderSimCap(){
  const wrap=$('#sim-cap'); const outer=$('#sim-cap-wrap'); if(!wrap) return;
  if(!simState.botcap){ if(outer) outer.style.display='none'; wrap.innerHTML=''; return; }
  if(outer) outer.style.display='block';
  const m=simCapModel();
  const cards=[
    {k:'Book yield — before cap',v:m.yBase.toFixed(1)+'%',col:'var(--mid)',
     n:'Share-weighted effective APR of the illustrative title-loan mix. ASSUMED rates, not measured.'},
    {k:'Book yield — under 28% cap',v:m.yCap.toFixed(1)+'%',col:'var(--agri)',
     n:'Each product capped at the BoT 28% ceiling, re-weighted by the same illustrative shares.'},
    {k:'Yield compression',v:'−'+m.drop.toFixed(1)+' pts',col:'var(--agri)',
     d:m.rows.filter(r=>r.compress).length+' of '+m.rows.length+' products bind',
     n:'Lost yield from clipping the high-rate tail to 28%. Pre-tax, pre-volume — a pricing ceiling, not a credit-loss figure.'},
  ];
  const ch=cards.map(c=>`<div class="mcard"><div class="k">${c.k}</div>
    <div class="v" style="color:${c.col}">${c.v}</div>
    ${c.d?`<div class="d" style="color:${c.col}">${c.d}</div>`:''}
    <div class="n">${c.n}</div></div>`).join('');
  const rows=m.rows.slice().sort((a,b)=>b.apr-a.apr).map(r=>{
    const col=r.compress?'var(--agri)':'var(--up)';
    const tag=r.compress?`<span class="mono" style="color:var(--agri)">▼ caps to 28%</span>`:`<span class="mono" style="color:var(--up)">unaffected</span>`;
    return `<tr><td><b>${r.seg}</b></td><td class="mono">${r.share}%</td>
      <td class="mono">${r.apr}%</td><td class="mono" style="color:${col}">${r.capped.toFixed(0)}%</td>
      <td class="mono" style="color:${r.compress?'var(--agri)':'var(--mid)'}">${r.drop>0?'−'+r.drop.toFixed(0):'—'}</td>
      <td>${tag}</td></tr>`;}).join('');
  wrap.innerHTML=`<div class="grid macro">${ch}</div>
    <table class="tbl" style="margin-top:12px">
      <tr><th>Product</th><th title="ASSUMED share of the book">Share · est</th>
      <th title="ASSUMED effective APR">APR now · est</th><th title="APR after the 28% cap">Under cap</th>
      <th title="APR points lost to the cap">Δ pts</th><th>Status</th></tr>${rows}</table>
    <p class="lead" style="margin-top:6px">⛔ <b>Scenario model.</b> Product shares &amp; APRs are <b>ASSUMPTIONS</b> (levers) until a real loan tape lands — not AutoX's measured book.
      The <b>28% ceiling is a cited regulatory fact</b>: BoT title-loan rate cap, effective <b>2 Dec 2025</b> (notification 25680030 · Royal Decree 5 Jun 2025).</p>`;
}

/* ---------- risk trend (time dimension, Phase 3) ----------
   Lazy-loads data/deltas.json (built by pipeline/timeseries.py from the snapshot
   set). With one vintage it shows a "baseline captured" message; with two it shows
   region movers, the commodity-board YoY re-rating, and the biggest branch movers.
   All region/branch numbers are ESTIMATED proxies; the board is editorial price dir. */
let DELTAS=null, trendLoaded=false;
// signed delta pill: ▲ red when risk rises, ▼ green when it eases, • grey when flat.
function deltaPill(d,invert){
  const v=d==null?0:d; const eps=0.05;
  const rising = invert ? v<-eps : v>eps;     // for board YoY a FALL is the bad/“rising-stress” case
  const easing = invert ? v>eps : v<-eps;
  const col = rising?'var(--agri)':easing?'var(--up)':'var(--mid)';
  const arr = rising?'▲':easing?'▼':'•';
  const txt = d==null?'n/a':(v>0?'+':'')+v;
  return `<span class="mono" style="color:${col}" title="change vs prior vintage">${arr} ${txt}</span>`;
}
async function renderTrend(){
  if(!trendLoaded){
    trendLoaded=true;
    try{ DELTAS = await fetch('data/deltas.json').then(r=>r.json()); }
    catch(e){ DELTAS=null; }
  }
  const baseEl=$('#trendbaseline'), bodyEl=$('#trendbody'), vintEl=$('#trendvint');
  if(!DELTAS){
    if(baseEl){ baseEl.style.display='block';
      baseEl.innerHTML='Trend data not available yet (<b>data/deltas.json</b> missing).'; }
    if(bodyEl) bodyEl.style.display='none';
    return;
  }
  if(vintEl){
    vintEl.textContent = DELTAS.baseline
      ? (DELTAS.to?`Baseline vintage: ${DELTAS.to}.`:'')
      : `Comparing ${DELTAS.from} → ${DELTAS.to}.`;
  }
  if(DELTAS.baseline){
    if(baseEl){ baseEl.style.display='block';
      baseEl.innerHTML=`<b>Baseline captured${DELTAS.to?` (${DELTAS.to})`:''}.</b> Trends appear after the next data refresh —
        once a second vintage is snapshotted, this tab fills in with region movers, commodity re-rating and per-branch risk shifts.
        <span class="sub">The plumbing is live; it just needs one more data point.</span>`; }
    if(bodyEl) bodyEl.style.display='none';
    return;
  }
  if(baseEl) baseEl.style.display='none';
  if(bodyEl) bodyEl.style.display='block';

  // region mover cards — composite arrow led by the worst-moving leg
  const RC=$('#trendregions');
  if(RC){
    RC.innerHTML=(DELTAS.region||[]).map(r=>{
      const legs=[['Agri-PD',r.d_agri,r.agri,'var(--agri)'],['Merchant',r.d_md,r.md,'var(--merch)'],['Collateral',r.d_col,r.col,'var(--collat)']];
      const worst=legs.reduce((a,b)=>Math.abs(b[1])>Math.abs(a[1])?b:a,legs[0]);
      const hc=worst[1]>0.05?'var(--agri)':worst[1]<-0.05?'var(--up)':'var(--mid)';
      return `<div class="mcard"><div class="k">${r.r} <span class="sub">· ${r.n} branches</span></div>
        <div class="v" style="color:${hc}">${deltaPill(worst[1])}</div>
        <div class="n">${legs.map(([lab,d,now])=>`${lab} ${now} ${deltaPill(d)}`).join(' · ')}</div></div>`;
    }).join('') || '<div class="sub">No region movers.</div>';
  }
  // commodity board YoY re-rating — for board, a FALLING YoY = deepening stress (invert)
  const BD=$('#trendboard');
  if(BD){
    const rows=(DELTAS.board||[]).filter(b=>b.d_yoy!=null)
      .sort((a,b)=>Math.abs(b.d_yoy)-Math.abs(a.d_yoy));
    BD.innerHTML=`<tr><th>Item</th><th>Segment</th><th>YoY now</th><th>Prior YoY</th><th title="change in the YoY figure — a fall means deepening price stress">Δ YoY · est</th></tr>`+
      (rows.length?rows.map(b=>`<tr><td>${b.lab}</td><td class="sub">${b.seg||'—'}</td>
        <td class="mono">${b.yoy!=null?(b.yoy>0?'+':'')+b.yoy+'%':'—'}</td>
        <td class="mono sub">${b.prev_yoy!=null?(b.prev_yoy>0?'+':'')+b.prev_yoy+'%':'—'}</td>
        <td>${deltaPill(b.d_yoy,true)}</td></tr>`).join('')
        :'<tr><td class="sub" colspan="5">No board re-rating between these vintages.</td></tr>');
  }
  // per-branch risk movers
  const BR=$('#trendbranches');
  if(BR){
    const rows=DELTAS.branches||[];
    BR.innerHTML=`<tr><th>#</th><th title="composite risk proxy = worst of agri/merchant/collateral (est)">Risk now ▲ est</th><th title="change in composite proxy vs prior vintage">Δ composite · est</th><th>Branch</th><th>Prov</th><th>Region</th><th>Δ agri</th><th>Δ merch</th><th>Δ collat</th></tr>`+
      (rows.length?rows.map((d,i)=>{const rc=d.comp>=60?'var(--agri)':d.comp>=40?'var(--gold)':'var(--merch)';
        return `<tr><td class="mono sub">${i+1}</td>
        <td class="mono" style="color:${rc}">▲ ${d.comp}</td>
        <td>${deltaPill(d.d_comp)}</td>
        <td>${d.n}</td><td class="sub">${d.v}</td><td class="sub">${d.r}</td>
        <td>${deltaPill(d.d_a)}</td><td>${deltaPill(d.d_m)}</td><td>${deltaPill(d.d_c)}</td></tr>`;}).join('')
        :'<tr><td class="sub" colspan="9">No branch-level movement between these vintages.</td></tr>');
  }
}

/* ---------- map ---------- */
function renderLenses(){
  // Hide the household debt-to-income lens once we KNOW its source is absent (loaded, empty) —
  // graceful degrade: the button never appears for a dataset that isn't there. Before load it
  // shows (warmed at map init); if the load yields no data it is filtered out on the next render.
  $('#lenses').innerHTML = Object.entries(LENS)
    .filter(([k,l])=>!(l.hh && hhriskLoaded && !hhriskHasData()))
    .filter(([k,l])=>!(l.occr && occriskLoaded && !occriskHasData()))
    .map(([k,l])=>
    `<button class="lens ${k===curLens?'on':''}" data-l="${k}" aria-pressed="${k===curLens}" aria-label="Map lens: ${l.label.replace(/"/g,'&quot;')}" ${l.est?`title="${l.desc.replace(/"/g,'&quot;')}"`:''}>
       <div class="lt"><span class="lk" style="background:${l.color}"></span>${l.label}</div>
       <div class="ld">${l.desc}</div></button>`).join('');
  $('#lenses').onclick = e=>{const b=e.target.closest('.lens'); if(!b)return; setLens(b.dataset.l);};
  renderRiskSub();
  renderLegend();
}
// risk sub-metric chips — only shown when the Portfolio-risk lens is active
function renderRiskSub(){
  const wrap=$('#riskSub'); if(!wrap) return;
  if(curLens!=='risk'){ wrap.style.display='none'; wrap.innerHTML=''; return; }
  wrap.style.display='flex';
  const opts=[['composite','Composite (worst of 3)'],['a','Agri-PD ●'],['m','Merchant ◆'],['c','Collateral ▲']];
  wrap.innerHTML='<span class="sub" style="align-self:center;margin-right:2px">Risk proxy:</span>'+
    opts.map(([k,t])=>`<button class="chip ${k===riskMetric?'on':''}" data-rm="${k}">${t}</button>`).join('');
  wrap.onclick=e=>{const b=e.target.closest('[data-rm]'); if(!b)return; riskMetric=b.dataset.rm;
    wrap.querySelectorAll('.chip').forEach(c=>c.classList.toggle('on',c===b));
    renderLegend(); if(mapReady) styleMarkers();};
}
function hexRgb(h){return [parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)];}
function lensColor(t,hex){const a=[40,46,64],b=hexRgb(hex);t=Math.max(0,Math.min(1,t));
  return `rgb(${a.map((v,i)=>Math.round(v+(b[i]-v)*t)).join(',')})`;}
function lensMax(l){return Math.max(1,...DATA.map(l.val));}
function fmtK(n){return n>=1000?Math.round(n/1000)+'k':String(Math.round(n));}
function renderLegend(){
  const l=LENS[curLens], mx=lensMax(l);
  const est=l.est?' <span class="sub" title="Estimated proxy, not measured">▲ estimated</span>':'';
  // Competitor-density lens: if the census file isn't present yet, say so quietly (no crash) instead
  // of a meaningless 0-coloured scale, and point at the puller. Once data is in, show the scale + an
  // honest "measured, lower bound" tag and a tiny brand key for the faint rival points.
  if(l.cmp){
    if(!compLoaded){ $('#maplegend').innerHTML='<span class="sub">Loading competitor census…</span>'; return; }
    if(!compHasData()){
      $('#maplegend').innerHTML='<span class="sub" title="competitors_national.json not found in data/">'+
        'No competitor data yet — run <span class="mono">pipeline/pull_competitors.py</span> (from a Thai IP) to populate the rival-branch census.</span>';
      return;
    }
    const key=Object.entries(COMP_BRAND_COLOR).map(([b,c])=>`<span><i style="background:${c};border-radius:50%"></i>${b}</span>`).join('');
    $('#maplegend').innerHTML =
      `<span><i style="background:${lensColor(.12,l.color)}"></i>0</span>`+
      `<span><i style="background:${lensColor(.5,l.color)}"></i>${fmtK(mx/2)}</span>`+
      `<span><i style="background:${lensColor(1,l.color)}"></i>${fmtK(mx)} ${l.unit}</span>`+
      ` <span class="sub" title="${(COMP_META&&COMP_META.sources||['']).join(' + ')} — a sample/lower bound, not a registry; dense brands are undercounted">◆ measured · ${(COMP_META&&COMP_META.sources||[]).join('+')||'sample'} · lower bound</span>`+
      ` &nbsp; ${key}`;
    return;
  }
  // Household debt-to-income lens: the val() is DTI×100, so present the scale in real DTI terms
  // and tag it honestly MEASURED · NSO. Absent file → the lens is already filtered out of the bar.
  if(l.hh){
    if(!hhriskLoaded){ $('#maplegend').innerHTML='<span class="sub">Loading household debt-to-income…</span>'; return; }
    const lo=(mx*.12/100).toFixed(2), mid=(mx*.5/100).toFixed(2), hi=(mx/100).toFixed(2);
    $('#maplegend').innerHTML =
      `<span><i style="background:${lensColor(.12,l.color)}"></i>${lo}×</span>`+
      `<span><i style="background:${lensColor(.5,l.color)}"></i>${mid}×</span>`+
      `<span><i style="background:${lensColor(1,l.color)}"></i>${hi}× debt÷annual income</span>`+
      ` <span class="sub" title="NSO SES 2566 household debt and income — province averages, measured">● measured · NSO SES</span>`;
    return;
  }
  $('#maplegend').innerHTML =
    `<span><i style="background:${lensColor(.12,l.color)}"></i>~0</span>
     <span><i style="background:${lensColor(.5,l.color)}"></i>${fmtK(mx/2)}</span>
     <span><i style="background:${lensColor(1,l.color)}"></i>${fmtK(mx)} ${l.unit}</span>${est}`;
}
function initMap(){
  if(mapReady){ map.invalidateSize(); return; }
  if(!DATA) return;
  mapReady=true;
  // optional ?lens=<key> deep-link: pick the starting map lens (validated against LENS).
  try{ const ql=new URLSearchParams(location.search).get('lens'); if(ql&&LENS[ql]&&ql!==curLens){ curLens=ql; renderLenses(); } }catch(e){}
  map = L.map('map',{preferCanvas:true, attributionControl:true, zoomControl:true}).setView([13.4,101.2], window.innerWidth<600?5:6);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{
    attribution:'&copy; OpenStreetMap &copy; CARTO', subdomains:'abcd', maxZoom:19}).addTo(map);
  const renderer = L.canvas({padding:0.5});
  markers = DATA.map(d=>{
    const m = L.circleMarker([d.y,d.x], {renderer, radius:4, weight:0.4, color:'#0c1118', fillOpacity:0.85});
    m._d=d; m.on('click',()=>selectBranch(d,m));
    return m.addTo(map);
  });
  map.on('popupclose', clearRadius);
  addRadiusToggle();
  styleMarkers();
  // warm the district join so popups always carry the amphoe white-space/risk block and the
  // district lenses recolour instantly. Small file, also used by the Acquisition tab.
  if(!ampJoinAttached) loadAmphoe().then(()=>{ if(mapReady){ renderLegend(); styleMarkers(); } });
  // warm the measured occupation rollup so branch popups carry the Overture occupation-mix block
  // when present (small, optional file). Absent → loader leaves OCCDATA null and nothing renders.
  if(!occLoaded) loadOccupations().then(()=>{ if(mapReady){ if(curLens==='estab'){ renderLegend(); styleMarkers(); } } });
  // warm the MEASURED household debt-to-income layer so the lens hides itself when absent and
  // popups carry the debt-to-income block. Absent file → loader leaves HHRISK empty, the lens is
  // filtered out, nothing renders.
  if(!hhriskLoaded) loadHouseholdRisk().then(()=>{ renderLenses(); if(mapReady&&curLens==='hhdti'){ renderLegend(); styleMarkers(); } });
  // warm the occupation × stress cross-read so the lens hides itself when absent. Absent file
  // (build_occupation_risk.py not run / no Overture pull yet) → OCCRISK empty, lens filtered out.
  if(!occriskLoaded) loadOccRisk().then(()=>{ renderLenses(); if(mapReady&&curLens==='occrisk'){ renderLegend(); styleMarkers(); } });
  // if the map opened directly on the competitor lens (e.g. ?lens=comp), warm the census now.
  if(curLens==='comp' && !compAttached){
    loadCompetitors().then(()=>{ if(curLens==='comp'&&mapReady){ renderLegend(); drawCompPoints(); styleMarkers(); } });
  }
}
function selectBranch(d,m){
  m.bindPopup(popupHTML(d),{closeButton:true, maxWidth:320, minWidth:260}).openPopup();
  drawRadius(d);
}
function drawRadius(d){
  clearRadius();
  if(!showRadius) return;
  radiusCircle = L.circle([d.y,d.x], {radius:10000, color:'var(--accent)', weight:1.2,
    fillColor:'#5B7CFA', fillOpacity:0.07, dashArray:'4 4', interactive:false}).addTo(map);
}
function clearRadius(){ if(radiusCircle){ map.removeLayer(radiusCircle); radiusCircle=null; } }
function addRadiusToggle(){
  const C = L.control({position:'topright'});
  C.onAdd = ()=>{ const d=el('div','radius-toggle',
    `<label style="display:flex;align-items:center;gap:6px;background:rgba(8,11,18,.9);
      border:1px solid #2e3350;border-radius:7px;padding:6px 9px;font:600 12px 'IBM Plex Sans Thai',sans-serif;
      color:#c7cedd;cursor:pointer">
      <input type="checkbox" ${showRadius?'checked':''} style="accent-color:var(--accent)"> 10&nbsp;km radius</label>`);
    L.DomEvent.disableClickPropagation(d);
    d.querySelector('input').onchange = e=>{ showRadius=e.target.checked;
      if(!showRadius) clearRadius(); };
    return d; };
  C.addTo(map);
}
// faint competitor points — plotted ONLY while the Competitor-density lens is active, so the 2,015
// AutoX dots stay readable in every other lens. Small translucent markers, brand-coloured, with a
// click popup naming the rival. Built once, then shown/hidden. Null-safe: no data → nothing drawn.
let compLayer=null;
function drawCompPoints(){
  if(!mapReady||!map) return;
  if(curLens!=='comp'||!compHasData()){
    if(compLayer){ map.removeLayer(compLayer); compLayer=null; }
    return;
  }
  if(compLayer) return;  // already drawn for this lens
  const renderer=L.canvas({padding:0.5});
  compLayer=L.layerGroup();
  COMP_ITEMS.forEach(it=>{
    const col=COMP_BRAND_COLOR[it.brand]||'#8b90a7';
    const m=L.circleMarker([it.lat,it.lng],{renderer,radius:2.6,weight:0,fillColor:col,fillOpacity:0.55,interactive:true});
    m.bindPopup(`<div class="pop" style="min-width:0"><div class="pn" style="color:${col}">◆ ${it.brand}</div>`+
      `<div class="pv">${it.name||''}${it.prov?' · '+it.prov:''}</div>`+
      `<div class="sub" style="margin-top:4px">Rival branch · measured location (Google Places, lower bound)</div></div>`,
      {closeButton:true,maxWidth:260});
    compLayer.addLayer(m);
  });
  compLayer.addTo(map);
  if(map.getPane('markerPane')&&compLayer.eachLayer){/* keep AutoX markers clickable on top */}
}
// competitor block for an AutoX branch popup — measured rivals within ~5km, broken out by brand,
// read against own ≤10km saturation. Only meaningful once the census is loaded (d._comp.ok).
function compPopupHTML(d,sec,r){
  const c=d._comp; if(!c||!c.ok) return '';
  const col=c.n>0?'var(--agri)':'var(--merch)';
  const brands=Object.entries(c.brands).sort((a,b)=>b[1]-a[1])
    .map(([b,n])=>`${b} ${n}`).join(' · ');
  // contested vs undercompeted read: rivals nearby vs our own ≤10km presence
  const verdict = c.n===0 ? 'no nearby rivals — undercompeted'
    : (c.n> (d.w||0) ? 'more rivals than own AutoX — contested'
                     : 'rivals present, own coverage leads');
  return sec('Competitors — measured (Google Places, lower bound)')
    + r(`Rival branches ≤${COMP_RADIUS_KM}km`, `<span style="color:${col}">${c.n}</span>`, col)
    + (brands?r('By brand', brands, '#c7cedd'):'')
    + r('Own AutoX ≤10km', (d.w||0), 'var(--accent)')
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">${verdict} · Places coverage is a lower bound, not a lender registry</div>`;
}
// crop-household stress block for a branch popup — only the cstress lens loads the data,
// so render nothing until it's available. Shows the REAL components, honestly labelled.
function cstressPopupHTML(d,sec,r){
  const p=CSTRESS&&CSTRESS[d.v]; if(!p) return '';
  const dom=(p.crop_mix&&p.crop_mix[0])||null;
  const c=p.components||{};
  const sv=Math.round((p.agri_stress||0)*100);
  const sc=sv>=45?'var(--agri)':sv>=25?'var(--gold)':'var(--merch)';
  return sec('Crop-household stress — ESTIMATED triage')
    + r('Agri-stress (0–100) · est', `<span style="color:${sc}">▲ ${sv}</span>`, sc)
    + (dom?r('Dominant crop (OAE · measured)', `${dom.crop} ${Math.round((dom.share||0)*100)}%`, '#c7cedd'):'')
    + r('Price YoY · WB global proxy', (p.price_stress>0?'+':'')+p.price_stress+'%', p.price_stress<0?'var(--agri)':'var(--merch)')
    + r('Rainfall % of normal · measured', (c.rain_pct_of_normal!=null?c.rain_pct_of_normal+'%':'n/a'), c.rain_pct_of_normal!=null&&c.rain_pct_of_normal<85?'var(--gold)':'var(--merch)');
}
// Household debt-to-income block for a branch popup — the MEASURED NSO SES province balance-sheet
// read. debt + income + ratio are measured; stress_index is an ESTIMATED percentile rank. Renders
// nothing until household_risk_by_province.json is loaded and this province has an entry.
function hhriskPopupHTML(d,sec,r){
  const p=HHRISK&&HHRISK[d.v]; if(!p||p.debt_to_income==null) return '';
  const dti=p.debt_to_income, si=p.stress_index;
  const dc=dti>=1.0?'var(--agri)':dti>=0.7?'var(--gold)':'var(--merch)';
  return sec('Household debt-to-income — measured (NSO SES)')
    + r('Debt ÷ annual income', `<span style="color:${dc}">${dti.toFixed(2)}×</span>`, dc)
    + r('Avg household debt (THB)', (p.debt||0).toLocaleString(), '#c7cedd')
    + r('Avg annual income (THB)', (p.income||0).toLocaleString(), '#c7cedd')
    + (si!=null?r('Stress rank ▲ · est', `${Math.round(si)} <span class="sub">/100 pct</span>`, dc):'')
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">debt &amp; income measured (NSO SES 2566, province average); stress rank = percentile of DTI across provinces (estimated)</div>`;
}
// Occupation-mix block for a branch popup — the MEASURED Overture-Places rollup of establishments
// by occupation bucket within 10km of this branch. Renders nothing until branch_occupations.json is
// loaded AND this branch has a non-empty entry (entry.t>0), so it is fully graceful: absent file or
// absent/empty entry → no block at all. Shows the top ~6 buckets as labelled percentage bars.
function occPopupHTML(d,sec){
  if(!OCCDATA||!OCCDATA.branches||!OCCDATA.buckets||!DATA) return '';
  const i=DATA.indexOf(d); if(i<0) return '';
  const e=OCCDATA.branches[i]; if(!e||!(e.t>0)) return '';
  let rows=OCCDATA.buckets.map((bk,j)=>({lab:bk.label,col:OCC_BUCKET_COL[bk.key]||'#8b90a7',v:(e.o&&e.o[j])||0}))
    .filter(rw=>rw.v>0).sort((a,b)=>b.v-a.v).slice(0,6);
  if(!rows.length) return '';
  const tot=rows.reduce((a,rw)=>a+rw.v,0)||1, mx=rows[0].v||1;
  return sec('Occupation mix (measured · Overture)')
    + `<div class="occ" style="margin-top:2px">`+rows.map(rw=>{
        const pct=Math.round(rw.v/tot*100), w=Math.max(4,Math.round(rw.v/mx*100));
        return `<div class="pr" style="gap:8px"><span style="flex:1">${rw.lab}</span>`
          +`<span class="bar" style="flex:0 0 62px"><i style="width:${w}%;background:${rw.col}"></i></span>`
          +`<b class="mono" style="color:${rw.col};min-width:30px;text-align:right">${pct}%</b></div>`;
      }).join('')
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">${(e.t||0).toLocaleString()} establishments ≤10km by category (Overture Maps Places — a sample/lower bound, not a registry)</div>`
    + `</div>`;
}
// Occupation × stress block for a branch popup — the occupation_risk.json cross-read. Shows the
// ESTIMATED occupation-stress score (MEASURED shares × ESTIMATED stress weighting) and, when the
// branch is FLAGGED, a one-line callout naming the concentrated stressed base. Fully graceful:
// absent file / absent entry → no block. Only renders something when there is a real read (t>0).
function occriskPopupHTML(d,sec,r){
  const e=occriskRec(d); if(!e||!(e.t>0)) return '';
  const sc=e.s||0;
  const col=sc>=40?'var(--agri)':sc>=25?'var(--gold)':'#8b90a7';
  const domLab=e.d?occLabel(e.d):'—';
  return sec('Occupation × stress — MEASURED mix · ESTIMATED weighting')
    + r('Occupation-stress ▲ · est', `<span style="color:${col}">${sc}</span> <span class="sub">/100</span>`, col)
    + r('Dominant base · measured', `${domLab}${e.ds?` <span class="sub">${Math.round(e.ds*100)}%</span>`:''}`, '#8b90a7')
    + (e.f?`<div class="sub" style="margin:2px 0 0;font-size:10px;color:var(--agri)">⚠ FLAGGED — borrower base concentrated in a stressed sector (occupation shares MEASURED; stressed-sector weighting ESTIMATED). A triage flag, not a measured default rate.</div>`
          :`<div class="sub" style="margin:2px 0 0;font-size:10px">occupation shares MEASURED (Overture, lower bound); stressed-sector weighting ESTIMATED (factory slowdown · province crop-stress)</div>`);
}
// Collateral-mix block for a branch popup — the MEASURED DLT split of the province vehicle stock.
// Motorcycle share is highlighted as the highest-volatility / lowest-recovery title collateral.
function collatMixPopupHTML(d,sec,r){
  const p=PLOOK&&PLOOK[d.v]; if(!p||!p.vehicles) return '';
  const pct=v=>v==null?null:Math.round(100*v/p.vehicles);
  const mp=pct(p.moto), cp=pct(p.car), pp=pct(p.pickup), ep=pct(p.ev);
  const mc=mp!=null&&mp>=55?'var(--agri)':'var(--collat)';
  return sec('Collateral mix — DLT vehicle stock · measured')
    + r('Motorcycle share ▲', mp!=null?mp+'%':'n/a', mc)
    + (cp!=null?r('Car share', cp+'%', '#8b90a7'):'')
    + (pp!=null?r('Pickup share', pp+'%', '#8b90a7'):'')
    + (ep!=null?r('EV share', ep+'%', 'var(--merch)'):'');
}
// District (amphoe) block for a branch popup — shows the whole-district scores joined to this
// branch. White-space is MEASURED (demand POIs vs AutoX saturation); risk is ESTIMATED. Renders
// only once amphoe.json has been joined (d._amp set), so it appears after a district lens loads.
function amphoePopupHTML(d,sec,r){
  const a=d._amp; if(!a) return '';
  const ws=a.whitespace, rk=a.risk_proxy;
  const wc=ws>=40?'var(--gold)':ws>=20?'#cda23e':'#8b90a7';
  const rc=rk>=55?'var(--agri)':rk>=45?'var(--gold)':'var(--merch)';
  return sec('District (amphoe) — white-space & risk')
    + r('White-space ◇ · measured', `<span style="color:${wc}">${ws}</span> <span class="sub">/100</span>`, wc)
    + r('District risk ▲ · est', `<span style="color:${rc}">${rk}</span> <span class="sub">/100</span>`, rc)
    + r('AutoX in district · measured', (a.branches||0)+(a.branches===1?' branch':' branches'), 'var(--accent)')
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">white-space = district demand vs AutoX saturation (measured); risk = province-inherited agri-stress + local mix (estimated)</div>`;
}
function popupHTML(d){
  const r=(lab,val,col)=>`<div class="pr"><span>${lab}</span><b style="color:${col}">${val}</b></div>`;
  const k=d.k10||{};
  const pl=(typeof PLOOK!=='undefined'&&PLOOK)?PLOOK[d.v]:null;
  const wc=regionWorstCrop(d.r);
  // within-10km radar: label, count, bar scaled to a sensible per-row max
  const radar=[
    ['Factories (OSM)',k.ind,60,'var(--gold)'],['Industrial estates',k.est,5,'var(--gold)'],
    ['Vehicle/moto shops',k.veh,40,'var(--collat)'],['Gold shops',k.gold,15,'var(--collat)'],
    ['Banks',k.bank,40,'var(--accent)'],['ATMs',k.atm,60,'var(--accent)'],
    ['Convenience',k.cvs,80,'var(--merch)'],['Supermarkets',k.super,15,'var(--merch)'],
    ['Fresh markets',k.fmkt,15,'var(--merch)'],['Restaurants',k.rest,80,'var(--merch)'],
    ['Schools',k.sch,40,'#8b90a7'],['Hospitals/gov',k.civic,30,'#8b90a7'],
    ['Hotels',k.hotel,40,'#8b90a7'],['Pharmacies',k.pharm,30,'#8b90a7'],
  ];
  const sec=t=>`<div style="margin:8px 0 3px;font:700 11px 'IBM Plex Sans Thai';color:#8b90a7;text-transform:uppercase;letter-spacing:.5px">${t}</div>`;
  const rrow=([lab,v,mx,col])=>`<div class="pr" style="gap:8px"><span style="flex:1">${lab}</span>
     ${barHTML(v||0,col,mx)}<b class="mono" style="color:${col};min-width:24px;text-align:right">${v||0}</b></div>`;
  const dist = (d.dfac!=null) ? sec('District (DIW · measured)')
     + r('Factories', (d.dfac||0).toLocaleString(), 'var(--gold)')
     + r('Factory workers', (d.dwork||0).toLocaleString(), 'var(--gold)') : '';
  return `<div class="pop" style="max-height:62vh;overflow:auto">
    <div class="pn">${d.n}</div>
    <div class="pv">${d.v}${d.d?' · '+d.d:''} · ${d.r} · ${d.w} AutoX ≤10km</div>
    <a href="branch-explorer.html?lat=${d.y}&lng=${d.x}&n=${encodeURIComponent(d.n)}${themeQS()}"
       style="display:block;text-align:center;margin:8px 0 2px;padding:7px;border-radius:7px;
       background:var(--accent);color:#fff;text-decoration:none;font:700 12px 'IBM Plex Sans Thai'">🏙 Open 3D explorer · what's within 10 km</a>
    ${sec('Portfolio risk — ESTIMATED proxy (OSM/price, 0–100)')}
    ${r('Agri-PD ● (est)', d.a==null?'n/a':d.a, 'var(--agri)')}
    ${r('Merchant ◆ (est)', d.m==null?'n/a':d.m, 'var(--merch)')}
    ${r('Collateral ▲ (est)', d.c==null?'n/a':d.c, 'var(--collat)')}
    ${sec('Market — measured')}
    ${r('District factories (DIW)', naNum(d.dfac), 'var(--gold)')}
    ${r('District factory workers (DIW)', naNum(d.dwork), 'var(--gold)')}
    ${pl?r('Province pickups (DLT)', naNum(pl.pickup), 'var(--collat)'):''}
    ${pl?r('Province informal workers (NSO)', naNum(pl.informal), 'var(--collat)'):''}
    ${collatMixPopupHTML(d,sec,r)}
    ${hhriskPopupHTML(d,sec,r)}
    ${occPopupHTML(d,sec)}
    ${occriskPopupHTML(d,sec,r)}
    ${amphoePopupHTML(d,sec,r)}
    ${compPopupHTML(d,sec,r)}
    ${wc?r('Region weakest crop (YoY) · est', wc.lab+' '+(wc.yoy>0?'+':'')+wc.yoy+'%', wc.yoy<0?'var(--agri)':'var(--merch)'):''}
    ${cstressPopupHTML(d,sec,r)}
    ${sec('Within 10 km (OSM · measured)')}
    ${radar.map(rrow).join('')}</div>`;
}
function styleMarkers(){
  const l=LENS[curLens], mx=lensMax(l);
  markers.forEach(m=>{
    const v=l.val(m._d), t=v/mx;
    m.setStyle({fillColor:lensColor(Math.sqrt(t),l.color), radius:3+Math.min(1,t)*7});
  });
}
function setLens(k){
  curLens=k;
  document.querySelectorAll('.lens').forEach(b=>{const on=b.dataset.l===k;b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on));});
  renderRiskSub();
  if(k==='cstress' && !cstressLoaded){
    loadCropStress().then(()=>{ if(curLens==='cstress'){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if(k==='estab' && !occLoaded){
    loadOccupations().then(()=>{ if(curLens==='estab'){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if(k==='hhdti' && !hhriskLoaded){
    loadHouseholdRisk().then(()=>{ renderLenses(); if(curLens==='hhdti'){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if(k==='occrisk' && !occriskLoaded){
    loadOccRisk().then(()=>{ renderLenses(); if(curLens==='occrisk'){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if((k==='dws'||k==='drisk') && !ampJoinAttached){
    loadAmphoe().then(()=>{ if(curLens==='dws'||curLens==='drisk'){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if(k==='comp' && !compAttached){
    loadCompetitors().then(()=>{ if(curLens==='comp'){ renderLegend(); if(mapReady){ drawCompPoints(); styleMarkers(); } } });
  }
  if(mapReady) drawCompPoints();   // show/hide the faint rival points with the lens
  renderLegend(); if(mapReady) styleMarkers();
}

/* ---------- branches ---------- */
function renderBranchSort(){
  const opts=[['risk','Portfolio risk ▲ est'],['dwork','Factory workers'],['ind','Factories ≤10km'],['w','AutoX nearby']];
  $('#sortchips').setAttribute('role','group'); $('#sortchips').setAttribute('aria-label','Sort branches by');
  $('#sortchips').innerHTML = opts.map(([k,t])=>`<button class="chip ${k===branchSort?'on':''}" data-s="${k}" aria-pressed="${k===branchSort}">${t}</button>`).join('');
  $('#sortchips').onclick=e=>{const b=e.target.closest('.chip'); if(!b)return; branchSort=b.dataset.s;
    $('#sortchips').querySelectorAll('.chip').forEach(c=>{const on=c===b;c.classList.toggle('on',on);c.setAttribute('aria-pressed',String(on));}); renderBranches();};
  $('#search').oninput=()=>renderBranches();
}
function branchSortVal(d,k){ return k==='ind'?((d.k10&&d.k10.ind)||0) : k==='risk'?riskVal(d) : (d[k]||0); }
function branchHref(d){return `branch-explorer.html?lat=${d.y}&lng=${d.x}&n=${encodeURIComponent(d.n)}${themeQS()}`;}
function renderBranches(){
  const q=($('#search').value||'').trim().toLowerCase();
  let rows=DATA.filter(d=>!q || d.n.toLowerCase().includes(q) || d.v.toLowerCase().includes(q));
  rows.sort((a,b)=> branchSort==='w' ? a.w-b.w : branchSortVal(b,branchSort)-branchSortVal(a,branchSort));
  rows=rows.slice(0,150);
  $('#branches').innerHTML = `<tr><th class="no-print"></th><th class="h-agri" title="ESTIMATED proxy (OSM/price-based, 0–100), not a measured default rate">Portfolio risk ▲ est</th><th>Branch</th><th>Prov</th><th class="h-opp" title="DIW registered factory workers in the branch district — measured">Factory workers (DIW)</th><th>Pickups (prov)</th><th>Informal (prov)</th><th>AutoX</th></tr>`+
    rows.map(d=>{const pl=PLOOK[d.v]||{}; const rk=riskVal(d); const rc=rk>=60?'var(--agri)':rk>=40?'var(--gold)':'var(--merch)';
      const id=`branch:${d.n}|${d.v}`;
      const wItem={id,label:d.n,sub:`${d.v} · ${d.r}`,val:`▲ ${rk}`,valSub:'risk · est',col:rc,prov:d.v};
      return `<tr onclick="location.href='${branchHref(d)}'" tabindex="0" role="link" style="cursor:pointer">
      <td class="no-print">${starBtn(id,wItem)}</td>
      <td class="mono"><a href="${branchHref(d)}" style="color:${rc};text-decoration:none" title="ESTIMATED risk proxy ${riskMetric==='composite'?'(worst of agri/merchant/collateral)':''}">▲ ${rk}</a></td>
      <td>${d.n}</td><td class="sub">${d.v}</td>
      <td class="mono" style="color:var(--gold)">${naNum(d.dwork)}</td>
      <td class="mono" style="color:var(--collat)">${naNum(pl.pickup)}</td>
      <td class="mono" style="color:var(--collat)">${naNum(pl.informal)}</td>
      <td class="mono sub">${d.w}</td></tr>`;}).join('');
}

/* ---------- provinces selector ---------- */
let PROV=null, provRegion='all', PLOOK={};
async function renderProvinces(){
  if(!PROV){
    try{ PROV = await fetch('data/provinces/index.json').then(r=>r.json()); }
    catch(e){ $('#provtbl').innerHTML='<tr><td>Could not load provinces.</td></tr>'; return; }
  }
  if(!$('#provchips').dataset.init){
    const regions=['all',...Array.from(new Set(PROV.map(p=>p.region)))];
    $('#provchips').innerHTML=regions.map((r,i)=>`<button class="chip ${i===0?'on':''}" data-r="${r}">${r==='all'?'All':r}</button>`).join('');
    $('#provchips').onclick=e=>{const b=e.target.closest('.chip'); if(!b)return;
      document.querySelectorAll('#provchips .chip').forEach(c=>c.classList.toggle('on',c===b));
      provRegion=b.dataset.r; drawProv();};
    $('#provsearch').oninput=drawProv; $('#provchips').dataset.init='1';
  }
  drawProv();
}
// Primary 3D entry per province = the Overture BUILDING scene (rayong-catchment.html?city=<slug>),
// the same fancy scene as Rayong/Bangkok. It degrades gracefully to a "not pulled yet" notice (with
// a link to the district view) for provinces whose <slug>_catchment.json hasn't been pulled yet.
// The extruded-relief district view (province.html?p=<slug>) stays reachable as the secondary link.
function bldgURL(slug){return `rayong-catchment.html?city=${slug}${themeQS()}`;}      // ?city= -> &theme=
function distURL(slug){return `province.html?p=${slug}${themeQS()}`;}                  // ?p=   -> &theme=
function drawProv(){
  const q=($('#provsearch').value||'').trim().toLowerCase();
  const rows=PROV.filter(p=>(provRegion==='all'||p.region===provRegion) &&
    (!q || p.th.includes(q) || (p.en||'').toLowerCase().includes(q) || p.slug.includes(q)))
    .sort((a,b)=>b.branches-a.branches);
  $('#provtbl').innerHTML=`<tr><th class="no-print"></th><th>Province</th><th>Region</th><th>Br</th><th>Distr</th><th>Factories</th><th>Vehicles</th><th>Fac/br</th><th class="no-print">View</th></tr>`+
   rows.map(p=>{const id=`prov:${p.th}`;
     const wItem={id,label:p.th,sub:`${p.region} · ${p.branches} branches`,val:`${(p.factories||0).toLocaleString()}`,valSub:'factories · measured',col:'var(--gold)',prov:p.th};
     return `<tr onclick="location.href='${bldgURL(p.slug)}'" tabindex="0" role="link" style="cursor:pointer">
     <td class="no-print">${starBtn(id,wItem)}</td>
     <td><a href="${bldgURL(p.slug)}" style="color:inherit;text-decoration:none"><b>${p.th}</b> <span class="sub">${p.en||''}</span></a></td>
     <td class="sub">${p.region}</td>
     <td class="mono">${p.branches}</td>
     <td class="mono">${p.districts}</td>
     <td class="mono" style="color:var(--gold)">${(p.factories||0).toLocaleString()}</td>
     <td class="mono">${Math.round((p.vehicles||0)/1000)}k</td>
     <td class="mono" style="color:var(--collat)">${p.branches?Math.round((p.factories||0)/p.branches):0}</td>
     <td class="no-print sub" style="white-space:nowrap">
       <a href="${bldgURL(p.slug)}" onclick="event.stopPropagation()" title="3D building scene" style="text-decoration:none">🏙 3D</a>
       <a href="${distURL(p.slug)}" onclick="event.stopPropagation()" title="Extruded district view" style="text-decoration:none;margin-left:8px;color:var(--mid,#8A94A8)">▦ district</a>
     </td></tr>`;}).join('');
}

/* ---------- market assessment (real measured numbers, no indices) ---------- */
// region -> worst (most negative YoY) crop on the commodity board.
// EXPLICIT mapping: commodity-board `reg` abbreviation -> set of app regions it covers.
// (The old single-letter token match collided: "North" tokenised to "n" hit Rice's "N".)
// Each crop row is attributed to the region(s) where it is the dominant smallholder crop,
// not every province where a stalk grows. Rice -> Isan & Central paddy belt (the North's
// signature crop is Maize, so North is deliberately NOT tagged to Rice). East/Central upland
// has no single dominant board crop -> left unmatched so those regions show "—" honestly.
const BOARD_REG_TAGS={
  'Isan·N·C':['Isan','Central&BKK'], // Rice — Isan + central paddy belt
  'S·E':['South','East'],            // Rubber — southern + eastern plantations
  'Isan·C':['Isan'],                 // Sugar — Isan cane belt
  'South':['South'],                 // Palm oil — deep south
  'North':['North'],                 // Maize — northern uplands
};
function regionWorstCrop(region){
  if(!META||!META.board) return null;
  let worst=null;
  META.board.filter(b=>b.seg==='Crops' && b.yoy!=null).forEach(b=>{
    const tags=BOARD_REG_TAGS[b.reg]; // only explicitly-tagged crop rows are eligible
    if(tags && tags.includes(region) && (!worst||b.yoy<worst.yoy)) worst=b;
  });
  return worst; // null -> callers render "—"
}
function provLookupByName(){ const m={}; (PROV||[]).forEach(p=>m[p.th]=p); return m; }
function renderMarket(){
  (PROV ? Promise.resolve(PROV) : fetch('data/provinces/index.json').then(r=>r.json()).then(d=>(PROV=d)))
   .then(()=>{
    if(!$('#mktchips').dataset.init){
      const regions=['all',...Array.from(new Set(PROV.map(p=>p.region)))];
      $('#mktchips').innerHTML=regions.map((r,i)=>`<button class="chip ${i===0?'on':''}" data-r="${r}">${r==='all'?'All':r}</button>`).join('');
      $('#mktchips').onclick=e=>{const b=e.target.closest('.chip'); if(!b)return;
        document.querySelectorAll('#mktchips .chip').forEach(c=>c.classList.toggle('on',c===b));
        mktRegion=b.dataset.r; drawMarket();};
      $('#mktsearch').oninput=drawMarket; $('#mktchips').dataset.init='1';
      $('#mktnote').textContent='Registered factory workers DIW · informal workforce NSO 2024 (some provinces n/a) · vehicles/pickups DLT · weakest crop = World Bank global price direction proxy (not Thai farm-gate), region-attributed.';
    }
    drawMarket();
   }).catch(()=>{ $('#mkttbl').innerHTML='<tr><td>Could not load market data.</td></tr>'; });
}
let mktRegion='all';
function drawMarket(){
  const q=($('#mktsearch').value||'').trim().toLowerCase();
  // sort by informal workforce, but push null-informal provinces (not in NSO release) to the
  // bottom rather than ranking them as a fake zero (e.g. Bangkok).
  const rows=PROV.filter(p=>(mktRegion==='all'||p.region===mktRegion) &&
    (!q||p.th.includes(q)||(p.en||'').toLowerCase().includes(q)))
    .sort((a,b)=>{const an=a.informal==null, bn=b.informal==null;
      if(an!==bn) return an?1:-1; return (b.informal||0)-(a.informal||0);});
  const pct=p=>p.vehicles?Math.round(100*(p.pickup||0)/p.vehicles):0;
  $('#mkttbl').innerHTML=`<tr><th>Province</th><th>Region</th><th class="h-opp" title="DIW registered factory workers — distinct from NSO informal/formal labour">Registered factory workers (DIW)</th><th title="NSO informal workforce — borrower base proxy">Informal workforce (NSO)</th><th>Pickups</th><th>Pickup %</th><th title="World Bank global price direction proxy, region-attributed — not Thai farm-gate">Weakest crop (YoY) · est</th></tr>`+
   rows.map(p=>{const wc=regionWorstCrop(p.region);
     return `<tr onclick="location.href='${bldgURL(p.slug)}'" tabindex="0" role="link" style="cursor:pointer">
     <td><a href="${bldgURL(p.slug)}" style="color:inherit;text-decoration:none"><b>${p.th}</b> <span class="sub">${p.en||''}</span></a> <a href="${distURL(p.slug)}" onclick="event.stopPropagation()" title="Extruded district view" class="sub" style="text-decoration:none;margin-left:6px;color:var(--mid,#8A94A8)">▦</a></td>
     <td class="sub">${p.region}</td>
     <td class="mono">${naNum(p.workers)}</td>
     <td class="mono" style="color:var(--collat)">${naNum(p.informal)}</td>
     <td class="mono">${naNum(p.pickup)}</td>
     <td class="mono sub">${pct(p)}%</td>
     <td class="mono" style="color:${wc&&wc.yoy<0?'var(--agri)':'var(--mid)'}">${wc?wc.lab+' '+(wc.yoy>0?'+':'')+wc.yoy+'%':'—'}</td></tr>`;}).join('');
  $('#mktcsv').onclick=()=>{
    const hdr=['province','province_en','region','branches','registered_factory_workers_diw','informal_workforce_nso','pickups_dlt','pickup_share_pct','vehicles_total','weakest_crop_est','weakest_crop_yoy_est'];
    const lines=[hdr.join(',')].concat(rows.map(p=>{const wc=regionWorstCrop(p.region);
      return [p.th,p.en,p.region,p.branches,p.workers,p.informal,p.pickup,pct(p),p.vehicles,wc?wc.lab:'',wc?wc.yoy:'']
        .map(v=>`"${String(v==null?'':v).replace(/"/g,'""')}"`).join(',');}));
    const blob=new Blob([lines.join('\n')],{type:'text/csv;charset=utf-8;'});
    const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
    a.download='autox_market_assessment.csv'; a.click(); URL.revokeObjectURL(a.href);
  };
}

/* ---------- command center (Step 1, daily-use front door) ----------
   Aggregates the existing computed signals into one screen answering the two standing
   objectives: WHERE TO EXPAND (top white-space districts + provinces) and WHAT IS GETTING
   RISKIER (crop stress, motorcycle-heavy collateral, gold-up vs pickup-pressure). Plus a
   macro/regulatory read, risk movers (when ≥2 vintages exist), a localStorage watchlist, and
   CSV + print export. Every figure is tagged measured (m) or estimated/proxy (e). No new data
   files — it reuses branches.json, meta.json, amphoe.json, crop_stress.json, deltas.json. */
const TAG_M='<span class="cc-tag m" title="Measured">measured</span>';
const TAG_E='<span class="cc-tag e" title="Estimated / proxy — not a measured outcome">est</span>';
function ccRow(l,sub,r,rsub,col){
  return `<div class="cc-row"><div class="l">${l}${sub?`<span class="s">${sub}</span>`:''}</div>`+
    `<div class="r" ${col?`style="color:${col}"`:''}>${r}${rsub?`<span class="s">${rsub}</span>`:''}</div></div>`;
}

/* ---- watchlist (localStorage) ---- */
const WATCH_KEY='autox-watchlist';
function watchLoad(){try{return JSON.parse(localStorage.getItem(WATCH_KEY)||'[]');}catch(e){return [];}}
function watchSave(a){try{localStorage.setItem(WATCH_KEY,JSON.stringify(a));}catch(e){}}
// id schema: "type:key" — branch:<name>|<province>, prov:<thai>
function watchHas(id){return watchLoad().some(w=>w.id===id);}
function watchToggle(item){
  let a=watchLoad(); const i=a.findIndex(w=>w.id===item.id);
  if(i>=0) a.splice(i,1); else a.push(item);
  watchSave(a);
  // refresh any visible star buttons for this id + the watchlist card
  document.querySelectorAll(`.cc-star[data-id="${cssEsc(item.id)}"]`).forEach(b=>b.classList.toggle('on',watchHas(item.id)));
  if(document.getElementById('v-home').classList.contains('on')) renderWatchlist();
}
function cssEsc(s){return String(s).replace(/["\\]/g,'\\$&');}
function starBtn(id,item){
  const on=watchHas(id)?' on':'';
  return `<button class="cc-star${on} no-print" data-id="${id.replace(/"/g,'&quot;')}" title="Add to watchlist" onclick='event.stopPropagation();ccStar(${JSON.stringify(item).replace(/'/g,"&#39;")})'>★</button>`;
}
function ccStar(item){watchToggle(item);}

/* ---- home orchestration ---- */
let homeBooted=false;
function renderHome(){
  renderHomeHero();         // QW5 — the verdict, in plain language (opportunity + household + crop)
  renderHomeWhitespace();   // uses META (estates/mws/cws) immediately; amphoe when loaded
  renderHomeRisk();         // uses META.region + crop_stress when loaded + PROV moto mix
  renderHomeMacro();        // META.macro + META.board
  renderHomeMovers();       // deltas.json
  renderWatchlist();
  if(!homeBooted){
    homeBooted=true;
    const onHome=()=>document.getElementById('v-home').classList.contains('on');
    loadAmphoe().then(()=>{ if(onHome()) renderHomeWhitespace(); });
    loadCropStress().then(()=>{ if(onHome()){ renderHomeRisk(); renderHomeHero(); } });
    // QW5 hero needs the opportunity composite + measured household leverage — lazy, null-safe re-render.
    loadOppScore().then(()=>{ if(onHome()) renderHomeHero(); });
    loadHouseholdRisk().then(()=>{ if(onHome()) renderHomeHero(); });
    // measured borrower-base + competitor census to enrich the top-district rows; null-safe re-render.
    const reHome=()=>{ if(onHome()) renderHomeWhitespace(); };
    loadAmphoeOccupations().then(reHome);
    loadCompetitors().then(reHome);
    const c=$('#cc-csv'), p=$('#cc-print');
    if(c) c.onclick=ccBriefCSV;
    if(p) p.onclick=()=>window.print();
  }
}

/* QW5 — HOME LEADS WITH THE VERDICT.
   2–3 BIG plain-language hero statements built ONLY from data already loaded:
   • "Open next in …" — from the opportunity_score composite (top districts).
   • "Watching: … household leverage (DTI …×) …" — from MEASURED household_risk (top DTI province)
     paired with the worst crop-household double-/single-stress (crop_stress).
   • a third drought/double-stress line when crop_stress carries a flagged province.
   Each statement links to its detail tab. Any source that is absent is omitted gracefully —
   never fabricated. Re-rendered as each lazy source resolves. */
function loadOppScore(){
  if(oppLoaded) return Promise.resolve(OPPSCORE);
  return fetch('data/opportunity_score.json').then(r=>r.ok?r.json():null)
    .then(j=>{OPPSCORE=j;oppLoaded=true;return j;})
    .catch(()=>{OPPSCORE=null;oppLoaded=true;return null;});
}
function renderHomeHero(){
  const box=$('#cc-hero'); if(!box) return;
  const heroes=[];
  // 1) WHERE TO OPEN NEXT — top-2 opportunity districts (ESTIMATED composite).
  const od=(OPPSCORE&&Array.isArray(OPPSCORE.districts))?OPPSCORE.districts:null;
  if(od&&od.length){
    const top=od.slice().sort((a,b)=>(b.score||0)-(a.score||0)).slice(0,2).filter(d=>d&&d.name);
    if(top.length){
      const names=top.map(d=>d.name).join(' & ');
      const lead=top[0];
      heroes.push({tone:'opp',v:'acq',
        big:`Open next in ${names}`,
        sub:`Top of the composite opportunity score (${top.map(d=>Math.round(d.score)).join(' & ')}/100) · ${lead.province||''}${lead.region?' · '+lead.region:''}`,
        tag:'estimated composite', cta:'Acquisition →'});
    }
  }
  // 2) WATCHING — MEASURED household leverage (top DTI province) + worst crop-household stress.
  const hh=(Array.isArray(HHRISK_LIST)&&HHRISK_LIST.length)?HHRISK_LIST[0]:null;
  const cs=(CSTRESS_LIST&&CSTRESS_LIST.length)?CSTRESS_LIST[0]:null;
  if(hh||cs){
    let big='Watching: ', subBits=[];
    if(hh){
      big+=`${hh.region||'household'} household leverage`;
      subBits.push(`DTI ${(+hh.debt_to_income).toFixed(2)}× in ${hh.province} (NSO, measured)`);
    }
    if(cs){
      const crop=(cs.crop_mix&&cs.crop_mix[0]&&cs.crop_mix[0].crop)||'crops';
      const crop2=(cs.crop_mix&&cs.crop_mix[1]&&cs.crop_mix[1].crop)||null;
      const dbl=cs.double_stress?' double-stress':'';
      big+=`${hh?' + ':''}${crop.toLowerCase()}${crop2?'/'+crop2.toLowerCase():''}${dbl} squeeze`;
      subBits.push(`${cs.th}: price ${cs.price_stress!=null?(cs.price_stress>0?'+':'')+Math.round(cs.price_stress)+'%':'—'}${cs.drought!=null?' · drought '+Math.round(cs.drought*100)+'%':''}${cs.double_stress?' (rice/rubber + drought)':''}`);
    }
    heroes.push({tone:'risk',v:hh?'map':'overview',big,sub:subBits.join(' · '),
      tag:hh?'measured + estimated':'estimated', cta:hh?'National map →':'Overview →'});
  }
  if(!heroes.length){ box.innerHTML=''; return; }
  box.innerHTML=heroes.map(h=>{
    const col=h.tone==='opp'?'var(--gold)':'var(--agri)';
    return `<a class="cc-hero-card ${h.tone}" data-v="${h.v}" href="#${h.v}" role="button" style="--hc:${col}">`+
      `<div class="cc-hero-big">${h.big}</div>`+
      `<div class="cc-hero-sub">${h.sub}</div>`+
      `<div class="cc-hero-foot"><span class="cc-hero-tag">${h.tag}</span><span class="cc-hero-cta">${h.cta}</span></div>`+
      `</a>`;
  }).join('');
}

// WHERE TO EXPAND — top 3 districts (amphoe whitespace) + top 3 provinces (province whitespace avg).
function renderHomeWhitespace(){
  const box=$('#cc-ws-body'); if(!box||!META) return;
  let html='';
  // top districts from amphoe.json (whitespace, est) — surfaces zero-branch white space
  if(AMP&&AMP.length){
    const top=AMP.slice().sort((a,b)=>(b.whitespace||0)-(a.whitespace||0)).slice(0,3);
    // honest subhead: only advertise the measured extras that actually loaded.
    const extras=[]; if(aoccHasData()) extras.push('borrower base'); if(compHasData()) extras.push('rivals');
    const extraTag=extras.length?` <span class="sub">+ ${extras.join(' &amp; ')} ${TAG_M}</span>`:'';
    html+=`<div class="cc-sub2" style="margin-top:0">Top underserved districts ${TAG_E}${extraTag}</div>`;
    html+=top.map(a=>{const nm=a.name_measured?a.name:a.name_en;
      const where=`${a.province_th} · ${a.region}`;
      const hd=a.branches===0?'no AutoX branch yet':`${a.branches} AutoX inside`;
      // append the measured "what borrower base + how contested" half when those files are loaded.
      const bits=[where,hd];
      const dom=ampDomOcc(a); if(dom) bits.push(`base: ${dom.toLowerCase()}`);
      const cn=ampCompCount(a);
      if(cn===0) bits.push('0 rivals ≤5km ✦');
      else if(cn!=null) bits.push(`${cn} rival${cn===1?'':'s'} ≤5km`);
      return ccRow(`${nm} <span class="sub">${a.name_measured?a.name_en:''}</span>`,bits.join(' · '),
        `★ ${(a.whitespace||0).toFixed(0)}`,'whitespace','var(--gold)');}).join('');
  } else {
    html+=`<div class="cc-empty">Loading district white-space…</div>`;
  }
  // top provinces by mean district whitespace (rolled up from amphoe) — "which province has room"
  if(AMP&&AMP.length){
    const byP={};
    AMP.forEach(a=>{const k=a.province_th; const o=byP[k]||(byP[k]={th:k,region:a.region,sum:0,n:0,zero:0});
      o.sum+=(a.whitespace||0); o.n++; if(a.branches===0)o.zero++;});
    const provs=Object.values(byP).map(o=>({...o,avg:o.sum/o.n})).sort((a,b)=>b.avg-a.avg).slice(0,3);
    html+=`<div class="cc-sub2">Top provinces · mean district white-space ${TAG_E}</div>`;
    html+=provs.map(o=>ccRow(`${o.th}`,`${o.region} · ${o.zero} district${o.zero===1?'':'s'} with no AutoX`,
      `★ ${o.avg.toFixed(0)}`,'avg','var(--gold)')).join('');
  }
  box.innerHTML=html;
}

// WHAT IS GETTING RISKIER — worst crop-stress province, motorcycle-heavy collateral, gold-up vs pickup.
function renderHomeRisk(){
  const box=$('#cc-risk-body'); if(!box||!META) return;
  let html='';
  // worst crop-household stress region/province (crop_stress.json)
  if(CSTRESS_LIST&&CSTRESS_LIST.length){
    const w=CSTRESS_LIST[0]; const sv=Math.round((w.agri_stress||0)*100);
    const dom=(w.crop_mix&&w.crop_mix[0])||{};
    html+=`<div class="cc-sub2" style="margin-top:0">Worst crop-household stress ${TAG_E}</div>`;
    html+=ccRow(`${w.th} <span class="sub">${w.region||''}</span>`,
      `${dom.crop||'crops'} ${dom.share!=null?Math.round(dom.share*100)+'%':''} · price ${w.price_stress!=null?(w.price_stress>0?'+':'')+w.price_stress+'%':'—'}`,
      `▲ ${sv}`,'agri-stress','var(--agri)');
  } else { html+=`<div class="cc-empty">Loading crop stress…</div>`; }
  // most motorcycle-heavy collateral provinces (DLT, measured) — lowest-recovery title collateral
  const moto=collatMixRows().slice(0,2);
  if(moto.length){
    html+=`<div class="cc-sub2">Most motorcycle-heavy collateral ${TAG_M}</div>`;
    html+=moto.map(p=>ccRow(`${p.th} <span class="sub">${p.region}</span>`,
      `${p.branches} branches · lowest-recovery title collateral`,
      `${p.moto}%`,'moto share','var(--agri)')).join('');
  }
  // gold-up vs pickup-pressure collateral read (board measured + editorial pickup watch)
  const gold=(META.board||[]).find(b=>b.seg==='Collateral'&&/gold/i.test(b.lab||''));
  const gy=gold&&gold.yoy!=null?(gold.yoy>0?'+':'')+gold.yoy+'%':'+62.7%';
  html+=`<div class="cc-sub2">Collateral value · the two backings diverge</div>`;
  html+=ccRow(`Gold collateral ${TAG_M}`,'pawn / gold-backed recovery value ↑',gy,'value ↑','var(--up)');
  html+=ccRow(`Diesel-pickup collateral ${TAG_E}`,'used-pickup glut + EV transition · editorial watch','↓ pressure','value at risk','var(--agri)');
  box.innerHTML=html;
}

// MACRO / REGULATORY — BoT rate-cap watch + key commodity moves from META.board.
function renderHomeMacro(){
  const box=$('#cc-macro-body'); if(!box||!META) return;
  let html='';
  html+=`<div class="cc-sub2" style="margin-top:0">Regulatory watch</div>`;
  html+=ccRow(`BoT hire-purchase rate/fee cap ${TAG_E}`,
    'car &amp; motorcycle lending · effective ~Dec 2025 · sector-margin item, not a credit signal',
    '~Dec 2025','margin watch','#D9742B');
  // key commodity moves: 2 worst crop YoY + gold
  const board=(META.board||[]);
  const crops=board.filter(b=>b.seg==='Crops'&&b.yoy!=null).sort((a,b)=>a.yoy-b.yoy).slice(0,2);
  const gold=board.find(b=>/gold/i.test(b.lab||''));
  html+=`<div class="cc-sub2">Key commodity moves ${TAG_M} <span class="sub">World Bank price direction</span></div>`;
  crops.forEach(b=>html+=ccRow(`${b.lab}`,b.note||'',`${b.yoy>0?'+':''}${b.yoy}%`,'YoY','var(--agri)'));
  if(gold) html+=ccRow(`Gold`,gold.note||'collateral value ↑',`+${gold.yoy}%`,'YoY','var(--up)');
  box.innerHTML=html;
}

// RISK MOVERS — top movers if deltas has ≥2 snapshots, else honest baseline message.
function renderHomeMovers(){
  const box=$('#cc-movers-body'); if(!box) return;
  const draw=()=>{
    if(!DELTAS||DELTAS.baseline||!(DELTAS.branches&&DELTAS.branches.length)){
      box.innerHTML=`<div class="cc-empty">Baseline captured${DELTAS&&DELTAS.to?` (${DELTAS.to})`:''} — trends appear after the next data refresh. The plumbing is live; it needs one more vintage.</div>`;
      return;
    }
    let html='';
    const reg=(DELTAS.region||[]).slice().sort((a,b)=>Math.abs(b.d_agri||0)-Math.abs(a.d_agri||0)).slice(0,2);
    if(reg.length){
      html+=`<div class="cc-sub2" style="margin-top:0">Region movers ${TAG_E} <span class="sub">vs prior vintage</span></div>`;
      html+=reg.map(r=>ccRow(`${r.r} <span class="sub">${r.n} branches</span>`,'agri-PD proxy shift',
        `${(r.d_agri||0)>0?'▲ +':'▼ '}${r.d_agri}`,'Δ agri',(r.d_agri||0)>0?'var(--agri)':'var(--up)')).join('');
    }
    const br=(DELTAS.branches||[]).slice(0,3);
    if(br.length){
      html+=`<div class="cc-sub2">Branch movers ${TAG_E}</div>`;
      html+=br.map(d=>ccRow(`${d.n} <span class="sub">${d.v} · ${d.r}</span>`,'composite risk proxy',
        `▲ ${d.comp}`,`Δ ${(d.d_comp||0)>0?'+':''}${d.d_comp}`,'var(--agri)')).join('');
    }
    box.innerHTML=html||`<div class="cc-empty">No material movement between vintages.</div>`;
  };
  if(DELTAS!==null||trendLoaded){ draw(); }
  else { fetch('data/deltas.json').then(r=>r.json()).then(j=>{DELTAS=j;trendLoaded=true;draw();}).catch(()=>{trendLoaded=true;DELTAS=null;draw();}); }
}

// WATCHLIST — starred branches & provinces with their key numbers.
function renderWatchlist(){
  const box=$('#cc-watch-body'); if(!box) return;
  const items=watchLoad();
  if(!items.length){
    box.innerHTML=`<div class="cc-empty">No starred items yet. Hit the ★ on any row in <b>Branches</b> or <b>Provinces</b> to pin it here with its key numbers.</div>`;
    return;
  }
  box.innerHTML=items.map(w=>{
    const star=`<button class="cc-star on no-print" data-id="${w.id.replace(/"/g,'&quot;')}" title="Remove from watchlist" onclick='ccStar(${JSON.stringify(w).replace(/'/g,"&#39;")})'>★</button>`;
    return ccRow(`${star} ${w.label}`,w.sub||'',w.val||'',w.valSub||'',w.col||'var(--hi)');
  }).join('');
}

// EXPORT — CSV brief of the command-center numbers.
function ccBriefCSV(){
  const rows=[['section','item','detail','value','provenance']];
  // white-space
  if(AMP&&AMP.length){
    AMP.slice().sort((a,b)=>(b.whitespace||0)-(a.whitespace||0)).slice(0,3).forEach(a=>{
      rows.push(['where_to_expand_district',(a.name_measured?a.name:a.name_en),`${a.province_th} | ${a.region} | ${a.branches} AutoX inside`,(a.whitespace||0).toFixed(0),'estimated']);});
    const byP={}; AMP.forEach(a=>{const o=byP[a.province_th]||(byP[a.province_th]={s:0,n:0,r:a.region});o.s+=(a.whitespace||0);o.n++;});
    Object.entries(byP).map(([th,o])=>[th,o.r,o.s/o.n]).sort((a,b)=>b[2]-a[2]).slice(0,3).forEach(([th,r,avg])=>
      rows.push(['where_to_expand_province',th,r,avg.toFixed(0),'estimated']));
  }
  // risk
  if(CSTRESS_LIST&&CSTRESS_LIST.length){const w=CSTRESS_LIST[0];
    rows.push(['risk_crop_stress',w.th,`${w.region} | price ${w.price_stress}%`,Math.round((w.agri_stress||0)*100),'estimated']);}
  collatMixRows().slice(0,2).forEach(p=>rows.push(['risk_moto_collateral',p.th,`${p.region} | ${p.branches} branches`,p.moto+'%','measured']));
  const gold=(META.board||[]).find(b=>/gold/i.test(b.lab||''));
  if(gold) rows.push(['collateral_gold','Gold',gold.note||'',(gold.yoy>0?'+':'')+gold.yoy+'%','measured']);
  rows.push(['collateral_pickup','Diesel-pickup','used-pickup glut + EV transition','pressure (down)','editorial']);
  // macro
  rows.push(['regulatory','BoT hire-purchase rate/fee cap','effective ~Dec 2025, sector-margin','~Dec 2025','editorial']);
  (META.board||[]).filter(b=>b.seg==='Crops'&&b.yoy!=null).sort((a,b)=>a.yoy-b.yoy).slice(0,2).forEach(b=>
    rows.push(['macro_commodity',b.lab,b.note||'',(b.yoy>0?'+':'')+b.yoy+'%','measured']));
  // movers
  if(DELTAS&&!DELTAS.baseline&&DELTAS.branches){
    (DELTAS.branches||[]).slice(0,3).forEach(d=>rows.push(['risk_mover',d.n,`${d.v} | ${d.r}`,`comp ${d.comp} (d ${d.d_comp})`,'estimated']));
  } else { rows.push(['risk_mover','(baseline)','one vintage captured — trends after next refresh','','']); }
  // watchlist
  watchLoad().forEach(w=>rows.push(['watchlist',w.label,w.sub||'',w.val||'',(w.prov||'')]));
  const csv=rows.map(r=>r.map(v=>`"${String(v==null?'':v).replace(/"/g,'""')}"`).join(',')).join('\n');
  const blob=new Blob([csv],{type:'text/csv;charset=utf-8;'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='autox_command_center_brief.csv'; a.click(); URL.revokeObjectURL(a.href);
}

boot();
