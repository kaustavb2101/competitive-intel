'use strict';
/* AutoX · เงินไชโย — Credit Intelligence Platform
   Loads data files, renders overview/map/acquisition/branches. Vanilla JS, no build step. */

// Real measured quantities (no indices). val() reads measured fields; color/size scale to absolute max.
const LENS = {
  workers:  {label:'Factory workers',     desc:'DIW factory employment in the branch district', color:'#E6B450', unit:'workers', val:d=>d.dwork||0},
  pickups:  {label:'Pickup stock',        desc:'DLT pickups in the province — title collateral', color:'#7A4FE0', unit:'pickups', val:d=>(PLOOK[d.v]||{}).pickup||0},
  informal: {label:'Informal workforce',  desc:'NSO informal workers in the province — borrower base', color:'#1C8C7D', unit:'workers', val:d=>(PLOOK[d.v]||{}).informal||0},
  autox:    {label:'AutoX saturation',    desc:'own AutoX branches within 10 km', color:'#5B7CFA', unit:'AutoX ≤10km', val:d=>d.w||0},
};
const SEG_COLORS = {Crops:'#C8433B', Livestock:'#1C8C7D', Fisheries:'#1C8C7D', Forestry:'#C9A227', Collateral:'#E6B450'};

let DATA=null, META=null, map=null, markers=[], curLens='workers', branchSort='dwork', mapReady=false;
let radiusCircle=null, showRadius=true;

const $ = s => document.querySelector(s);
const el = (t,c,h) => { const e=document.createElement(t); if(c)e.className=c; if(h!=null)e.innerHTML=h; return e; };
const lerp=(a,b,t)=>a.map((v,i)=>Math.round(v+(b[i]-v)*t));
function ramp3(v,[c0,c1,c2]){v=Math.max(0,Math.min(100,v))/100;const c=v<.5?lerp(c0,c1,v*2):lerp(c1,c2,(v-.5)*2);return `rgb(${c[0]},${c[1]},${c[2]})`;}
function barHTML(v,color,max=100){return `<span class="bar"><i style="width:${Math.round(62*Math.min(v,max)/max)}px;background:${color}"></i></span>`;}

/* ---------- tabs ---------- */
function showTab(v){
  if(!v||!document.getElementById('v-'+v)) v='overview';
  document.querySelectorAll('#nav a[data-v]').forEach(t=>t.classList.toggle('on',t.dataset.v===v));
  document.querySelectorAll('.view').forEach(s=>s.classList.toggle('on', s.id==='v-'+v));
  if(v==='map') initMap();
  if(v==='provinces') renderProvinces();
  if(v==='market') renderMarket();
  window.scrollTo(0,0);
}
$('#nav').addEventListener('click', e=>{
  const b=e.target.closest('a[data-v]'); if(!b) return;
  e.preventDefault(); const v=b.dataset.v;
  history.replaceState(null,'','#'+v);
  showTab(v);
});
window.addEventListener('hashchange',()=>showTab((location.hash||'').replace('#','')));

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
}

/* ---------- map ---------- */
function renderLenses(){
  $('#lenses').innerHTML = Object.entries(LENS).map(([k,l])=>
    `<button class="lens ${k===curLens?'on':''}" data-l="${k}">
       <div class="lt"><span class="lk" style="background:${l.color}"></span>${l.label}</div>
       <div class="ld">${l.desc}</div></button>`).join('');
  $('#lenses').onclick = e=>{const b=e.target.closest('.lens'); if(!b)return; setLens(b.dataset.l);};
  renderLegend();
}
function hexRgb(h){return [parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)];}
function lensColor(t,hex){const a=[40,46,64],b=hexRgb(hex);t=Math.max(0,Math.min(1,t));
  return `rgb(${a.map((v,i)=>Math.round(v+(b[i]-v)*t)).join(',')})`;}
function lensMax(l){return Math.max(1,...DATA.map(l.val));}
function fmtK(n){return n>=1000?Math.round(n/1000)+'k':String(Math.round(n));}
function renderLegend(){
  const l=LENS[curLens], mx=lensMax(l);
  $('#maplegend').innerHTML =
    `<span><i style="background:${lensColor(.12,l.color)}"></i>~0</span>
     <span><i style="background:${lensColor(.5,l.color)}"></i>${fmtK(mx/2)}</span>
     <span><i style="background:${lensColor(1,l.color)}"></i>${fmtK(mx)} ${l.unit}</span>`;
}
function initMap(){
  if(mapReady){ map.invalidateSize(); return; }
  if(!DATA) return;
  mapReady=true;
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
    <a href="branch-explorer.html?lat=${d.y}&lng=${d.x}&n=${encodeURIComponent(d.n)}"
       style="display:block;text-align:center;margin:8px 0 2px;padding:7px;border-radius:7px;
       background:#5B7CFA;color:#fff;text-decoration:none;font:700 12px 'IBM Plex Sans Thai'">🏙 Open 3D explorer · what's within 10 km</a>
    ${sec('Market — measured')}
    ${r('District factories (DIW)', (d.dfac||0).toLocaleString(), '#E6B450')}
    ${r('District factory workers', (d.dwork||0).toLocaleString(), '#E6B450')}
    ${pl?r('Province pickups (DLT)', (pl.pickup||0).toLocaleString(), '#7A4FE0'):''}
    ${pl?r('Province informal workers', (pl.informal||0).toLocaleString(), '#7A4FE0'):''}
    ${wc?r('Region weakest crop (YoY)', wc.lab+' '+(wc.yoy>0?'+':'')+wc.yoy+'%', wc.yoy<0?'#C8433B':'#1C8C7D'):''}
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
  renderLegend(); if(mapReady) styleMarkers();
}

/* ---------- branches ---------- */
function renderBranchSort(){
  const opts=[['dwork','Factory workers'],['ind','Factories ≤10km'],['w','AutoX nearby']];
  $('#sortchips').innerHTML = opts.map(([k,t])=>`<button class="chip ${k===branchSort?'on':''}" data-s="${k}">${t}</button>`).join('');
  $('#sortchips').onclick=e=>{const b=e.target.closest('.chip'); if(!b)return; branchSort=b.dataset.s;
    document.querySelectorAll('.chip').forEach(c=>c.classList.toggle('on',c===b)); renderBranches();};
  $('#search').oninput=()=>renderBranches();
}
function branchSortVal(d,k){ return k==='ind' ? ((d.k10&&d.k10.ind)||0) : (d[k]||0); }
function renderBranches(){
  const q=($('#search').value||'').trim().toLowerCase();
  let rows=DATA.filter(d=>!q || d.n.toLowerCase().includes(q) || d.v.toLowerCase().includes(q));
  rows.sort((a,b)=> branchSort==='w' ? a.w-b.w : branchSortVal(b,branchSort)-branchSortVal(a,branchSort));
  rows=rows.slice(0,150);
  $('#branches').innerHTML = `<tr><th>Branch</th><th>Prov</th><th>Factory workers</th><th>Pickups (prov)</th><th>Informal (prov)</th><th>AutoX</th></tr>`+
    rows.map(d=>{const pl=PLOOK[d.v]||{}; return `<tr><td>${d.n}</td><td class="sub">${d.v}</td>
      <td class="mono" style="color:#E6B450">${(d.dwork||0).toLocaleString()}</td>
      <td class="mono" style="color:#7A4FE0">${(pl.pickup||0).toLocaleString()}</td>
      <td class="mono" style="color:#7A4FE0">${(pl.informal||0).toLocaleString()}</td>
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
  $('#provtbl').innerHTML=`<tr><th>Province</th><th>Region</th><th>Br</th><th>Distr</th><th>Factories</th><th>Vehicles</th><th>Fac/br</th></tr>`+
   rows.map(p=>`<tr onclick="location.href='province.html?p=${p.slug}'" style="cursor:pointer">
     <td><b>${p.th}</b> <span class="sub">${p.en||''}</span></td>
     <td class="sub">${p.region}</td>
     <td class="mono">${p.branches}</td>
     <td class="mono">${p.districts}</td>
     <td class="mono" style="color:var(--gold)">${(p.factories||0).toLocaleString()}</td>
     <td class="mono">${Math.round((p.vehicles||0)/1000)}k</td>
     <td class="mono" style="color:var(--collat)">${p.branches?Math.round((p.factories||0)/p.branches):0}</td></tr>`).join('');
}

/* ---------- market assessment (real measured numbers, no indices) ---------- */
// region -> worst (most negative YoY) crop on the commodity board (best-effort token match)
const REG_ABBR={Isan:['isan'],North:['n','north'],South:['s','south'],East:['e'],'Central&BKK':['c','central']};
function regionWorstCrop(region){
  if(!META||!META.board) return null;
  const ab=REG_ABBR[region]||[];
  const toks=s=>(s||'').toLowerCase().split(/[·,\s]+/);
  let worst=null;
  META.board.filter(b=>b.seg==='Crops' && b.yoy!=null).forEach(b=>{
    if(toks(b.reg).some(t=>ab.includes(t)) && (!worst||b.yoy<worst.yoy)) worst=b;
  });
  return worst;
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
      $('#mktnote').textContent='Workforce NSO 2024 · vehicles DLT · factories DIW · crop YoY World Bank 2025M12.';
    }
    drawMarket();
   }).catch(()=>{ $('#mkttbl').innerHTML='<tr><td>Could not load market data.</td></tr>'; });
}
let mktRegion='all';
function drawMarket(){
  const q=($('#mktsearch').value||'').trim().toLowerCase();
  const rows=PROV.filter(p=>(mktRegion==='all'||p.region===mktRegion) &&
    (!q||p.th.includes(q)||(p.en||'').toLowerCase().includes(q))).sort((a,b)=>(b.informal||0)-(a.informal||0));
  const pct=p=>p.vehicles?Math.round(100*(p.pickup||0)/p.vehicles):0;
  $('#mkttbl').innerHTML=`<tr><th>Province</th><th>Region</th><th>Factory workers</th><th>Informal workforce</th><th>Pickups</th><th>Pickup %</th><th>Weakest crop (YoY)</th></tr>`+
   rows.map(p=>{const wc=regionWorstCrop(p.region);
     return `<tr onclick="location.href='province.html?p=${p.slug}'" style="cursor:pointer">
     <td><b>${p.th}</b> <span class="sub">${p.en||''}</span></td>
     <td class="sub">${p.region}</td>
     <td class="mono">${(p.workers||0).toLocaleString()}</td>
     <td class="mono" style="color:var(--collat)">${(p.informal||0).toLocaleString()}</td>
     <td class="mono">${(p.pickup||0).toLocaleString()}</td>
     <td class="mono sub">${pct(p)}%</td>
     <td class="mono" style="color:${wc&&wc.yoy<0?'var(--agri)':'var(--mid)'}">${wc?wc.lab+' '+(wc.yoy>0?'+':'')+wc.yoy+'%':'—'}</td></tr>`;}).join('');
  $('#mktcsv').onclick=()=>{
    const hdr=['province','province_en','region','branches','factory_workers','informal_workforce','pickups','pickup_share_pct','vehicles_total','weakest_crop','weakest_crop_yoy'];
    const lines=[hdr.join(',')].concat(rows.map(p=>{const wc=regionWorstCrop(p.region);
      return [p.th,p.en,p.region,p.branches,p.workers,p.informal,p.pickup,pct(p),p.vehicles,wc?wc.lab:'',wc?wc.yoy:'']
        .map(v=>`"${String(v==null?'':v).replace(/"/g,'""')}"`).join(',');}));
    const blob=new Blob([lines.join('\n')],{type:'text/csv;charset=utf-8;'});
    const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
    a.download='autox_market_assessment.csv'; a.click(); URL.revokeObjectURL(a.href);
  };
}

boot();
