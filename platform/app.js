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
  risk:     {label:'Portfolio risk ▲ est', desc:'ESTIMATED proxy (OSM/price-based, 0–100) — composite of agri-PD / merchant / collateral. NOT a measured default rate.', color:'#E0574F', unit:'risk (est)', est:true, val:d=>riskVal(d)},
  cstress:  {label:'Agri crop-stress ▲ est', desc:"ESTIMATED triage index (0–100) — the branch's province crop-household stress (price proxy × drought, scaled by crop dependence). Lazy-loaded.", color:'#C8433B', unit:'crop-stress (est)', est:true, val:d=>cstressVal(d)},
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

/* ---------- tabs ---------- */
function showTab(v){
  if(!v||!document.getElementById('v-'+v)) v='home';
  document.querySelectorAll('#nav a[data-v]').forEach(t=>t.classList.toggle('on',t.dataset.v===v));
  document.querySelectorAll('.view').forEach(s=>s.classList.toggle('on', s.id==='v-'+v));
  if(v==='home') renderHome();
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

/* ---------- load ---------- */
async function boot(){
  try{
    const [b,m] = await Promise.all([
      fetch('data/branches.json').then(r=>r.json()),
      fetch('data/meta.json').then(r=>r.json())
    ]);
    DATA=b; META=m;
    $('#updated').textContent = META.updated || '';
    try{ PROV = await fetch('data/provinces/index.json').then(r=>r.json()); PLOOK=provLookupByName(); }catch(e){}
    renderOverview(); renderAcq(); renderLenses(); renderBranchSort(); renderBranches();
    showTab((location.hash||'').replace('#',''));
  }catch(err){
    document.querySelector('main').insertAdjacentHTML('afterbegin',
      `<div class="insight" style="border-left-color:#C8433B">Couldn't load data files. Make sure <b>data/branches.json</b> and <b>data/meta.json</b> sit next to this page. (${err})</div>`);
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
  const rc={Isan:'#C8433B',North:'#D9742B',South:'#C9A227',East:'#3B82F6','Central&BKK':'#5B7CFA'};
  $('#region').innerHTML = `<tr><th>Region</th><th>Branches</th><th>Agri-PD</th><th>Elevated</th><th>Merchant</th><th>Collateral</th></tr>`+
    META.region.map(r=>`<tr><td><b>${r.r}</b></td><td class="mono">${r.n}</td>
      <td>${barHTML(r.agri,rc[r.r])} <span class="mono">${r.agri}</span></td>
      <td class="mono" style="color:var(--agri)">${r.hi}</td>
      <td>${barHTML(r.md,'#1C8C7D')} <span class="mono">${r.md}</span></td>
      <td>${barHTML(r.col,'#7A4FE0')} <span class="mono">${r.col}</span></td></tr>`).join('');
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
    top.map((p,i)=>{const mc=p.moto>=70?'#C8433B':p.moto>=60?'#E6B450':'#7A4FE0';
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
    rows.map((p,i)=>{const mc=p.moto>=70?'#C8433B':p.moto>=60?'#E6B450':'#7A4FE0';
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
      const sv=Math.round((p.agri_stress||0)*100); const bar=sv>=45?'#C8433B':sv>=25?'#E6B450':'#23A28F'; const sc=sv>=45?'var(--agri)':sv>=25?'var(--gold)':'#23A28F';
      const rn=c.rain_pct_of_normal; const rcol=rn!=null&&rn<85?'var(--gold)':'var(--mid)';
      return `<tr><td class="mono sub">${i+1}</td><td><b>${p.th}</b></td><td class="sub">${p.region||'—'}</td>
      <td>${barHTML(sv,bar)} <span class="mono" style="color:${sc}">${sv}</span></td>
      <td class="sub">${dom.crop||'—'} <span class="mono">${dom.share!=null?Math.round(dom.share*100)+'%':''}</span></td>
      <td class="mono" style="color:${p.price_stress<0?'var(--agri)':'var(--mid)'}">${p.price_stress!=null?(p.price_stress>0?'+':'')+p.price_stress+'%':'—'}</td>
      <td class="mono" style="color:${rcol}">${rn!=null?rn+'%':'n/a'}</td></tr>`;}).join('');
}

/* ---------- acquisition ---------- */
function renderAcq(){
  $('#estates').innerHTML = `<tr><th>AutoX ≤10km</th><th>Industrial estate</th></tr>`+
    META.estates.map(s=>{const c=s.own<=3?'#E0474B':s.own<=6?'#E6B450':'#2BB673';const t=s.own<=3?'white space':s.own<=6?'thin':'covered';
      return `<tr><td><span class="tag" style="color:${c};border:1px solid ${c}">${s.own} · ${t}</span></td><td>${s.name}</td></tr>`;}).join('');
  $('#mws').innerHTML = `<tr><th>Demand</th><th>AutoX</th><th>Fresh mkts</th><th>Province</th><th>Branch</th></tr>`+
    META.mws.map(m=>`<tr><td class="mono" style="color:#1C8C7D">${m.md}</td><td class="mono">${m.own}</td><td class="mono">${m.fmkt}</td><td>${m.v}</td><td class="sub">${m.n}</td></tr>`).join('');
  $('#cws').innerHTML = `<tr><th>Collat</th><th>Vehicle</th><th>Gold</th><th>AutoX</th><th>Province</th><th>Branch</th></tr>`+
    META.cws.map(c=>`<tr><td class="mono" style="color:#7A4FE0">${c.c}</td><td class="mono">${c.veh}</td><td class="mono">${c.gold}</td><td class="mono">${c.own}</td><td>${c.v}</td><td class="sub">${c.n}</td></tr>`).join('');
  renderAcqBoard();
  renderRoad3k();
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
      const ac=o.alloc>0?'#E6B450':'var(--mid)';
      // dual bar: gold target outline behind, blue (accent) current filled in front, gold tick at target
      const dual=`<span class="bar" style="position:relative;width:62px">`+
        `<i style="position:absolute;left:0;top:0;width:${tgtW}px;background:rgba(230,180,80,.22)"></i>`+
        `<i style="position:absolute;left:0;top:0;width:${curW}px;background:#5B7CFA"></i>`+
        `</span>`;
      return `<tr>
        <td><b>${o.r}</b></td>
        <td class="mono">${o.branches.toLocaleString()}</td>
        <td class="mono sub">${(o.wf/1e6).toFixed(1)}M</td>
        <td class="mono sub">${o.sat.toFixed(2)}</td>
        <td class="mono" style="color:#E6B450">${Math.round(o.headroom).toLocaleString()}</td>
        <td>${barHTML(o.alloc,ac,mxA)} <span class="mono" style="color:${ac}">+${o.alloc}</span></td>
        <td>${dual}</td>
        <td class="mono" style="color:#E6B450">${o.targetBranches.toLocaleString()}</td></tr>`;}).join('')+
    `<tr style="border-top:2px solid var(--line)"><td><b>Total</b></td>`+
      `<td class="mono"><b>${totBr.toLocaleString()}</b></td>`+
      `<td class="mono sub">${(c.totWf/1e6).toFixed(1)}M</td><td></td>`+
      `<td class="mono" style="color:#E6B450"><b>${Math.round(c.totHr).toLocaleString()}</b></td>`+
      `<td class="mono" style="color:#E6B450"><b>+${net.toLocaleString()}</b></td><td></td>`+
      `<td class="mono" style="color:#E6B450"><b>${(totBr+net).toLocaleString()}</b></td></tr>`;
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
    regs.map((o,i)=>{const sc=o.avg>=45?'#E6B450':o.avg>=30?'#23A28F':'var(--mid)';
      return `<tr onclick="location.href='${branchHref(o.top)}'" style="cursor:pointer">
      <td class="mono sub">${i+1}</td><td><b>${o.r}</b></td>
      <td class="mono sub">${o.n.toLocaleString()}</td>
      <td>${barHTML(o.avg,sc,mxAvg)} <span class="mono" style="color:${sc}">${o.avg.toFixed(1)}</span></td>
      <td class="sub">${o.top.n} <span class="mono" style="color:#E6B450">★ ${o.topS}</span> · ${o.top.v}</td></tr>`;}).join('');
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
  $('#acqtbl').innerHTML=`<tr><th>#</th><th class="h-opp" title="ESTIMATED white-space screen: demand proxy × own-AutoX headroom × competitor-proxy headroom (0–100)">White-space ★ est</th><th>Branch / area</th><th>Prov</th><th>Region</th><th title="own AutoX ≤10km — lower = more headroom">AutoX ≤10km</th><th class="h-opp" title="DIW factory workers (measured)">Workers (DIW)</th><th title="province pickup stock (DLT)">Pickups (prov)</th><th title="banks+ATMs ≤10km (OSM) — financial-density proxy for rival presence, NOT a competitor census">Fin. density ◇ est</th></tr>`+
    acqRows.map((row,i)=>{const d=row.d, pl=PLOOK[d.v]||{}; const sc=row.s>=60?'#E6B450':row.s>=40?'#23A28F':'var(--mid)';
      const hd=d.w<=2?' · white space':d.w<=5?' · thin':' · covered';
      const k=d.k10||{}; const fin=(k.bank||0)+(k.atm||0);
      return `<tr onclick="location.href='${branchHref(d)}'" style="cursor:pointer">
      <td class="mono sub">${i+1}</td>
      <td class="mono"><a href="${branchHref(d)}" style="color:${sc};text-decoration:none">★ ${row.s}</a></td>
      <td>${d.n}<span class="sub">${hd}</span></td>
      <td class="sub">${d.v}</td><td class="sub">${d.r}</td>
      <td class="mono ${d.w<=2?'':'sub'}" style="${d.w<=2?'color:#E6B450':''}">${d.w}</td>
      <td class="mono" style="color:#E6B450">${naNum(d.dwork)}</td>
      <td class="mono" style="color:#7A4FE0">${naNum(pl.pickup)}</td>
      <td class="mono sub">${fin}</td></tr>`;}).join('');
}
function acqCSV(){
  const hdr=['rank','whitespace_score_est','demand_proxy_0_1_est','own_headroom_0_1_est','competitor_headroom_proxy_0_1_est','branch','province','region','own_autox_10km','factory_workers_diw','province_pickups_dlt','fin_density_banks_atms_10km_est','opportunity_o_est'];
  const lines=[hdr.join(',')].concat(acqRows.map((row,i)=>{const d=row.d, pl=PLOOK[d.v]||{}; const L=acqLegs(d);
    return [i+1,row.s,L.demand.toFixed(3),L.ownHead.toFixed(3),L.compHead.toFixed(3),d.n,d.v,d.r,d.w,d.dwork==null?'':d.dwork,pl.pickup==null?'':pl.pickup,L.fin,d.o==null?'':d.o]
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
}
function drawAmpBoard(){
  ampRows=AMP.filter(a=>ampRegion==='all'||a.region===ampRegion)
    .sort((x,y)=>(y.whitespace||0)-(x.whitespace||0)).slice(0,25);
  const mx=Math.max(1,...ampRows.map(a=>a.whitespace||0));
  $('#amptbl').innerHTML=`<tr><th>#</th>`+
    `<th class="h-opp" title="ESTIMATED white-space score (0–100): district demand proxy minus an AutoX-presence penalty. Higher = more underserved.">Whitespace ★ est</th>`+
    `<th>District</th><th>Province</th><th>Region</th>`+
    `<th title="AutoX branches inside this amphoe (MEASURED, point-in-polygon). 0 = no own presence at all.">AutoX</th>`+
    `<th class="h-opp" title="DIW factory workers in the district (MEASURED where ✓; — where the district name didn't resolve to DIW)">Workers (DIW)</th>`+
    `<th title="convenience stores + restaurants inside the amphoe (OSM, MEASURED) — merchant footfall proxy">Merchant POI ◇</th>`+
    `<th title="gold shops + vehicle dealers inside the amphoe (OSM, MEASURED) — title/gold-collateral demand proxy">Collat POI ◇</th></tr>`+
    ampRows.map((a,i)=>{const ws=a.whitespace||0; const sc=ws>=50?'#E6B450':ws>=35?'#23A28F':'var(--mid)';
      const p=a.poi||{}; const merch=(p.cvs||0)+(p.rest||0); const collat=(p.gold||0)+(p.veh||0);
      const wkr=a.fac_measured?`<span style="color:#E6B450">${(a.workers||0).toLocaleString()}</span> <span class="sub" title="DIW-measured at this district">✓</span>`:`<span class="sub" title="district name did not resolve to a DIW record">—</span>`;
      const hd=a.branches===0?' · no AutoX':a.branches<=1?' · thin':'';
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td>${barHTML(ws,sc,mx)} <span class="mono" style="color:${sc}">${ws.toFixed(0)}</span></td>
        <td>${ampName(a)}<span class="sub">${hd}</span></td>
        <td class="sub">${a.province_th}</td><td class="sub">${a.region}</td>
        <td class="mono ${a.branches===0?'':'sub'}" style="${a.branches===0?'color:#E6B450':''}">${a.branches}</td>
        <td class="mono">${wkr}</td>
        <td class="mono" style="color:#1C8C7D">${merch.toLocaleString()}</td>
        <td class="mono" style="color:#7A4FE0">${collat.toLocaleString()}</td></tr>`;}).join('');
  // plain-language readout: lead with the answer.
  if($('#ampreadout')){
    const top=ampRows[0]; const zeros=ampRows.filter(a=>a.branches===0).length;
    const scope=ampRegion==='all'?'nationwide':`in ${ampRegion}`;
    if(top){
      const drivers=[];
      if(top.branches===0) drivers.push('no AutoX branch there yet');
      else drivers.push(`only ${top.branches} AutoX inside`);
      if(top.fac_measured&&(top.workers||0)>=5000) drivers.push(`${Math.round((top.workers||0)/1000)}k DIW factory workers`);
      $('#ampreadout').innerHTML=`<b>Most underserved district ${scope}:</b> ${top.name_measured?top.name:''} ${top.name_en} (${top.province_th}, ${top.region})
        at <b style="color:var(--gold)">★ ${(top.whitespace||0).toFixed(0)}</b> — ${drivers.join(', ')}.
        ${zeros?`<b>${zeros}</b> of the top 25 ${scope} have <b>zero AutoX presence</b>. `:''}
        <span class="sub">Estimated screen from measured branch + POI counts; confirm with a site survey.</span>`;
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
    ampRRows.map((a,i)=>{const rk=a.risk_proxy||0; const sc=rk>=60?'#C8433B':rk>=45?'#D9742B':'var(--mid)';
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td>${barHTML(rk,sc,mx)} <span class="mono" style="color:${sc}">${rk.toFixed(0)}</span></td>
        <td>${ampName(a)}</td>
        <td class="sub">${a.province_th}</td><td class="sub">${a.region}</td>
        <td class="mono" style="color:#C8433B">${(a.agri_stress||0).toFixed(0)} <span class="sub" title="province-inherited">prov</span></td>
        <td class="mono ${a.branches?'':'sub'}">${a.branches}</td></tr>`;}).join('');
}
function ampCSV(){
  const rows=AMP.filter(a=>ampRegion==='all'||a.region===ampRegion)
    .sort((x,y)=>(y.whitespace||0)-(x.whitespace||0));
  const hdr=['rank','whitespace_score_est','district_th','district_en','province','region','autox_branches_measured',
    'diw_workers','diw_workers_measured','merchant_poi_cvs_rest_measured','collateral_poi_gold_veh_measured',
    'demand_proxy_est','risk_proxy_est','agri_stress_province_inherited'];
  const lines=[hdr.join(',')].concat(rows.map((a,i)=>{const p=a.poi||{};
    return [i+1,(a.whitespace||0).toFixed(1),a.name_measured?a.name:'',a.name_en,a.province_th,a.region,a.branches,
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
  const hhiCol=hhi<1500?'#23A28F':hhi<2500?'#E6B450':'#E0574F';
  const cards=[
    ['Stressed-crop regions', stressed.length, pctS(stressed.length), 'Region weakest crop in price stress (World Bank YoY < −10%, direction proxy)', '#E0574F','▼'],
    ['Drought-proxy (dry quartile)', drought.length, pctS(drought.length), 'Branch in the driest 25% by recent rainfall (HDX proxy)', '#E6B450','☀'],
    ['High agri-PD proxy', weakAgri.length, pctS(weakAgri.length), 'Estimated agri-PD risk proxy ≥ 60 (OSM/price-based, not measured)', '#E0574F','▲'],
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
    $('#sim-readout').innerHTML='Crop-stress data not available (data/crop_stress.json missing) — the what-if needs it.';
    $('#sim-prov').innerHTML=''; renderSimCollat(); return;
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
  if(simState.botcap) read+=`<br><span class="sub">⚑ BoT rate/fee cap flagged: a sector <b>margin</b> compression on auto/moto hire-purchase — pricing-headroom watch, not a borrower-credit signal. AutoX core is title loans, so the direct hit is limited.</span>`;
  read+=`<br><span class="sub">ILLUSTRATIVE sensitivity — same estimated proxy, no measured elasticities / loan balances / LTV. A direction, not a number.</span>`;
  $('#sim-readout').innerHTML=read;
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
      const legs=[['Agri-PD',r.d_agri,r.agri,'#E0574F'],['Merchant',r.d_md,r.md,'#23A28F'],['Collateral',r.d_col,r.col,'#8E63E8']];
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
      (rows.length?rows.map((d,i)=>{const rc=d.comp>=60?'#E0574F':d.comp>=40?'#E6B450':'#23A28F';
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
  $('#lenses').innerHTML = Object.entries(LENS).map(([k,l])=>
    `<button class="lens ${k===curLens?'on':''}" data-l="${k}" ${l.est?`title="${l.desc.replace(/"/g,'&quot;')}"`:''}>
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
}
function selectBranch(d,m){
  m.bindPopup(popupHTML(d),{closeButton:true, maxWidth:320, minWidth:260}).openPopup();
  drawRadius(d);
}
function drawRadius(d){
  clearRadius();
  if(!showRadius) return;
  radiusCircle = L.circle([d.y,d.x], {radius:10000, color:'#5B7CFA', weight:1.2,
    fillColor:'#5B7CFA', fillOpacity:0.07, dashArray:'4 4', interactive:false}).addTo(map);
}
function clearRadius(){ if(radiusCircle){ map.removeLayer(radiusCircle); radiusCircle=null; } }
function addRadiusToggle(){
  const C = L.control({position:'topright'});
  C.onAdd = ()=>{ const d=el('div','radius-toggle',
    `<label style="display:flex;align-items:center;gap:6px;background:rgba(8,11,18,.9);
      border:1px solid #2e3350;border-radius:7px;padding:6px 9px;font:600 12px 'IBM Plex Sans Thai',sans-serif;
      color:#c7cedd;cursor:pointer">
      <input type="checkbox" ${showRadius?'checked':''} style="accent-color:#5B7CFA"> 10&nbsp;km radius</label>`);
    L.DomEvent.disableClickPropagation(d);
    d.querySelector('input').onchange = e=>{ showRadius=e.target.checked;
      if(!showRadius) clearRadius(); };
    return d; };
  C.addTo(map);
}
// crop-household stress block for a branch popup — only the cstress lens loads the data,
// so render nothing until it's available. Shows the REAL components, honestly labelled.
function cstressPopupHTML(d,sec,r){
  const p=CSTRESS&&CSTRESS[d.v]; if(!p) return '';
  const dom=(p.crop_mix&&p.crop_mix[0])||null;
  const c=p.components||{};
  const sv=Math.round((p.agri_stress||0)*100);
  const sc=sv>=45?'#C8433B':sv>=25?'#E6B450':'#23A28F';
  return sec('Crop-household stress — ESTIMATED triage')
    + r('Agri-stress (0–100) · est', `<span style="color:${sc}">▲ ${sv}</span>`, sc)
    + (dom?r('Dominant crop (OAE · measured)', `${dom.crop} ${Math.round((dom.share||0)*100)}%`, '#c7cedd'):'')
    + r('Price YoY · WB global proxy', (p.price_stress>0?'+':'')+p.price_stress+'%', p.price_stress<0?'#C8433B':'#1C8C7D')
    + r('Rainfall % of normal · measured', (c.rain_pct_of_normal!=null?c.rain_pct_of_normal+'%':'n/a'), c.rain_pct_of_normal!=null&&c.rain_pct_of_normal<85?'#E6B450':'#23A28F');
}
// Collateral-mix block for a branch popup — the MEASURED DLT split of the province vehicle stock.
// Motorcycle share is highlighted as the highest-volatility / lowest-recovery title collateral.
function collatMixPopupHTML(d,sec,r){
  const p=PLOOK&&PLOOK[d.v]; if(!p||!p.vehicles) return '';
  const pct=v=>v==null?null:Math.round(100*v/p.vehicles);
  const mp=pct(p.moto), cp=pct(p.car), pp=pct(p.pickup), ep=pct(p.ev);
  const mc=mp!=null&&mp>=55?'#C8433B':'#7A4FE0';
  return sec('Collateral mix — DLT vehicle stock · measured')
    + r('Motorcycle share ▲', mp!=null?mp+'%':'n/a', mc)
    + (cp!=null?r('Car share', cp+'%', '#8b90a7'):'')
    + (pp!=null?r('Pickup share', pp+'%', '#8b90a7'):'')
    + (ep!=null?r('EV share', ep+'%', '#23A28F'):'');
}
// District (amphoe) block for a branch popup — shows the whole-district scores joined to this
// branch. White-space is MEASURED (demand POIs vs AutoX saturation); risk is ESTIMATED. Renders
// only once amphoe.json has been joined (d._amp set), so it appears after a district lens loads.
function amphoePopupHTML(d,sec,r){
  const a=d._amp; if(!a) return '';
  const ws=a.whitespace, rk=a.risk_proxy;
  const wc=ws>=40?'#E6B450':ws>=20?'#cda23e':'#8b90a7';
  const rc=rk>=55?'#C8433B':rk>=45?'#E6B450':'#23A28F';
  return sec('District (amphoe) — white-space & risk')
    + r('White-space ◇ · measured', `<span style="color:${wc}">${ws}</span> <span class="sub">/100</span>`, wc)
    + r('District risk ▲ · est', `<span style="color:${rc}">${rk}</span> <span class="sub">/100</span>`, rc)
    + r('AutoX in district · measured', (a.branches||0)+(a.branches===1?' branch':' branches'), '#5B7CFA')
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">white-space = district demand vs AutoX saturation (measured); risk = province-inherited agri-stress + local mix (estimated)</div>`;
}
function popupHTML(d){
  const r=(lab,val,col)=>`<div class="pr"><span>${lab}</span><b style="color:${col}">${val}</b></div>`;
  const k=d.k10||{};
  const pl=(typeof PLOOK!=='undefined'&&PLOOK)?PLOOK[d.v]:null;
  const wc=regionWorstCrop(d.r);
  // within-10km radar: label, count, bar scaled to a sensible per-row max
  const radar=[
    ['Factories (OSM)',k.ind,60,'#E6B450'],['Industrial estates',k.est,5,'#E6B450'],
    ['Vehicle/moto shops',k.veh,40,'#7A4FE0'],['Gold shops',k.gold,15,'#7A4FE0'],
    ['Banks',k.bank,40,'#5B7CFA'],['ATMs',k.atm,60,'#5B7CFA'],
    ['Convenience',k.cvs,80,'#1C8C7D'],['Supermarkets',k.super,15,'#1C8C7D'],
    ['Fresh markets',k.fmkt,15,'#1C8C7D'],['Restaurants',k.rest,80,'#1C8C7D'],
    ['Schools',k.sch,40,'#8b90a7'],['Hospitals/gov',k.civic,30,'#8b90a7'],
    ['Hotels',k.hotel,40,'#8b90a7'],['Pharmacies',k.pharm,30,'#8b90a7'],
  ];
  const sec=t=>`<div style="margin:8px 0 3px;font:700 11px 'IBM Plex Sans Thai';color:#8b90a7;text-transform:uppercase;letter-spacing:.5px">${t}</div>`;
  const rrow=([lab,v,mx,col])=>`<div class="pr" style="gap:8px"><span style="flex:1">${lab}</span>
     ${barHTML(v||0,col,mx)}<b class="mono" style="color:${col};min-width:24px;text-align:right">${v||0}</b></div>`;
  const dist = (d.dfac!=null) ? sec('District (DIW · measured)')
     + r('Factories', (d.dfac||0).toLocaleString(), '#E6B450')
     + r('Factory workers', (d.dwork||0).toLocaleString(), '#E6B450') : '';
  return `<div class="pop" style="max-height:62vh;overflow:auto">
    <div class="pn">${d.n}</div>
    <div class="pv">${d.v}${d.d?' · '+d.d:''} · ${d.r} · ${d.w} AutoX ≤10km</div>
    <a href="branch-explorer.html?lat=${d.y}&lng=${d.x}&n=${encodeURIComponent(d.n)}${themeQS()}"
       style="display:block;text-align:center;margin:8px 0 2px;padding:7px;border-radius:7px;
       background:#5B7CFA;color:#fff;text-decoration:none;font:700 12px 'IBM Plex Sans Thai'">🏙 Open 3D explorer · what's within 10 km</a>
    ${sec('Portfolio risk — ESTIMATED proxy (OSM/price, 0–100)')}
    ${r('Agri-PD ● (est)', d.a==null?'n/a':d.a, '#E0574F')}
    ${r('Merchant ◆ (est)', d.m==null?'n/a':d.m, '#23A28F')}
    ${r('Collateral ▲ (est)', d.c==null?'n/a':d.c, '#8E63E8')}
    ${sec('Market — measured')}
    ${r('District factories (DIW)', naNum(d.dfac), '#E6B450')}
    ${r('District factory workers (DIW)', naNum(d.dwork), '#E6B450')}
    ${pl?r('Province pickups (DLT)', naNum(pl.pickup), '#7A4FE0'):''}
    ${pl?r('Province informal workers (NSO)', naNum(pl.informal), '#7A4FE0'):''}
    ${collatMixPopupHTML(d,sec,r)}
    ${amphoePopupHTML(d,sec,r)}
    ${wc?r('Region weakest crop (YoY) · est', wc.lab+' '+(wc.yoy>0?'+':'')+wc.yoy+'%', wc.yoy<0?'#C8433B':'#1C8C7D'):''}
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
  document.querySelectorAll('.lens').forEach(b=>b.classList.toggle('on',b.dataset.l===k));
  renderRiskSub();
  if(k==='cstress' && !cstressLoaded){
    loadCropStress().then(()=>{ if(curLens==='cstress'){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if((k==='dws'||k==='drisk') && !ampJoinAttached){
    loadAmphoe().then(()=>{ if(curLens==='dws'||curLens==='drisk'){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  renderLegend(); if(mapReady) styleMarkers();
}

/* ---------- branches ---------- */
function renderBranchSort(){
  const opts=[['risk','Portfolio risk ▲ est'],['dwork','Factory workers'],['ind','Factories ≤10km'],['w','AutoX nearby']];
  $('#sortchips').innerHTML = opts.map(([k,t])=>`<button class="chip ${k===branchSort?'on':''}" data-s="${k}">${t}</button>`).join('');
  $('#sortchips').onclick=e=>{const b=e.target.closest('.chip'); if(!b)return; branchSort=b.dataset.s;
    $('#sortchips').querySelectorAll('.chip').forEach(c=>c.classList.toggle('on',c===b)); renderBranches();};
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
    rows.map(d=>{const pl=PLOOK[d.v]||{}; const rk=riskVal(d); const rc=rk>=60?'#E0574F':rk>=40?'#E6B450':'#23A28F';
      const id=`branch:${d.n}|${d.v}`;
      const wItem={id,label:d.n,sub:`${d.v} · ${d.r}`,val:`▲ ${rk}`,valSub:'risk · est',col:rc,prov:d.v};
      return `<tr onclick="location.href='${branchHref(d)}'" style="cursor:pointer">
      <td class="no-print">${starBtn(id,wItem)}</td>
      <td class="mono"><a href="${branchHref(d)}" style="color:${rc};text-decoration:none" title="ESTIMATED risk proxy ${riskMetric==='composite'?'(worst of agri/merchant/collateral)':''}">▲ ${rk}</a></td>
      <td>${d.n}</td><td class="sub">${d.v}</td>
      <td class="mono" style="color:#E6B450">${naNum(d.dwork)}</td>
      <td class="mono" style="color:#7A4FE0">${naNum(pl.pickup)}</td>
      <td class="mono" style="color:#7A4FE0">${naNum(pl.informal)}</td>
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
function drawProv(){
  const q=($('#provsearch').value||'').trim().toLowerCase();
  const rows=PROV.filter(p=>(provRegion==='all'||p.region===provRegion) &&
    (!q || p.th.includes(q) || (p.en||'').toLowerCase().includes(q) || p.slug.includes(q)))
    .sort((a,b)=>b.branches-a.branches);
  $('#provtbl').innerHTML=`<tr><th class="no-print"></th><th>Province</th><th>Region</th><th>Br</th><th>Distr</th><th>Factories</th><th>Vehicles</th><th>Fac/br</th></tr>`+
   rows.map(p=>{const id=`prov:${p.th}`;
     const wItem={id,label:p.th,sub:`${p.region} · ${p.branches} branches`,val:`${(p.factories||0).toLocaleString()}`,valSub:'factories · measured',col:'var(--gold)',prov:p.th};
     return `<tr onclick="location.href='province.html?p=${p.slug}${themeQS()}'" style="cursor:pointer">
     <td class="no-print">${starBtn(id,wItem)}</td>
     <td><a href="province.html?p=${p.slug}${themeQS()}" style="color:inherit;text-decoration:none"><b>${p.th}</b> <span class="sub">${p.en||''}</span></a></td>
     <td class="sub">${p.region}</td>
     <td class="mono">${p.branches}</td>
     <td class="mono">${p.districts}</td>
     <td class="mono" style="color:var(--gold)">${(p.factories||0).toLocaleString()}</td>
     <td class="mono">${Math.round((p.vehicles||0)/1000)}k</td>
     <td class="mono" style="color:var(--collat)">${p.branches?Math.round((p.factories||0)/p.branches):0}</td></tr>`;}).join('');
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
     return `<tr onclick="location.href='province.html?p=${p.slug}${themeQS()}'" style="cursor:pointer">
     <td><a href="province.html?p=${p.slug}${themeQS()}" style="color:inherit;text-decoration:none"><b>${p.th}</b> <span class="sub">${p.en||''}</span></a></td>
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
  renderHomeWhitespace();   // uses META (estates/mws/cws) immediately; amphoe when loaded
  renderHomeRisk();         // uses META.region + crop_stress when loaded + PROV moto mix
  renderHomeMacro();        // META.macro + META.board
  renderHomeMovers();       // deltas.json
  renderWatchlist();
  if(!homeBooted){
    homeBooted=true;
    loadAmphoe().then(()=>{ if(document.getElementById('v-home').classList.contains('on')) renderHomeWhitespace(); });
    loadCropStress().then(()=>{ if(document.getElementById('v-home').classList.contains('on')) renderHomeRisk(); });
    const c=$('#cc-csv'), p=$('#cc-print');
    if(c) c.onclick=ccBriefCSV;
    if(p) p.onclick=()=>window.print();
  }
}

// WHERE TO EXPAND — top 3 districts (amphoe whitespace) + top 3 provinces (province whitespace avg).
function renderHomeWhitespace(){
  const box=$('#cc-ws-body'); if(!box||!META) return;
  let html='';
  // top districts from amphoe.json (whitespace, est) — surfaces zero-branch white space
  if(AMP&&AMP.length){
    const top=AMP.slice().sort((a,b)=>(b.whitespace||0)-(a.whitespace||0)).slice(0,3);
    html+=`<div class="cc-sub2" style="margin-top:0">Top underserved districts ${TAG_E}</div>`;
    html+=top.map(a=>{const nm=a.name_measured?a.name:a.name_en;
      const where=`${a.province_th} · ${a.region}`;
      const hd=a.branches===0?'no AutoX branch yet':`${a.branches} AutoX inside`;
      return ccRow(`${nm} <span class="sub">${a.name_measured?a.name_en:''}</span>`,`${where} · ${hd}`,
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
      `${p.moto}%`,'moto share','#C8433B')).join('');
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
