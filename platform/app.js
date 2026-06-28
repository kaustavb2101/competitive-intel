'use strict';
/* AutoX · เงินไชโย — Credit Intelligence Platform
   Loads data files, renders overview/map/acquisition/branches. Vanilla JS, no build step. */

const LENS = {
  opp:    {field:'o', label:'Acquisition opportunity', desc:'net demand vs competition', color:'#E6B450', ramp:[[74,80,96],[122,79,224],[230,180,80]], hi:'high opportunity'},
  agri:   {field:'a', label:'Farmer · agri-PD',         desc:'crop stress × drought, net livestock', color:'#C8433B', ramp:[[28,140,125],[201,162,39],[200,67,59]], hi:'high stress'},
  merch:  {field:'m', label:'Merchant demand',          desc:'vendor ecosystem + footfall', color:'#1C8C7D', ramp:[[70,80,100],[91,124,250],[43,182,115]], hi:'high demand'},
  collat: {field:'c', label:'Collateral density',       desc:'vehicle + gold trade', color:'#7A4FE0', ramp:[[60,66,84],[122,79,224],[230,180,80]], hi:'high density'},
};
const SEG_COLORS = {Crops:'#C8433B', Livestock:'#1C8C7D', Fisheries:'#1C8C7D', Forestry:'#C9A227', Collateral:'#E6B450'};

let DATA=null, META=null, map=null, markers=[], curLens='opp', branchSort='o', mapReady=false;

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
function renderLegend(){
  const l=LENS[curLens];
  $('#maplegend').innerHTML =
    `<span><i style="background:${ramp3(15,l.ramp)}"></i>low</span>
     <span><i style="background:${ramp3(55,l.ramp)}"></i>mid</span>
     <span><i style="background:${ramp3(92,l.ramp)}"></i>${l.hi}</span>`;
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
    m._d=d; m.on('click',()=>m.bindPopup(popupHTML(d),{closeButton:false}).openPopup());
    return m.addTo(map);
  });
  styleMarkers();
}
function popupHTML(d){
  const r=(lab,val,col)=>`<div class="pr"><span>${lab}</span><b style="color:${col}">${val}</b></div>`;
  return `<div class="pop"><div class="pn">${d.n}</div><div class="pv">${d.v} · ${d.r} · ${d.w} AutoX ≤10km</div>
    ${r('Acquisition opp.', d.o, '#E6B450')}
    ${r('Farmer agri-PD', d.a, '#C8433B')}
    ${r('Merchant demand', d.m, '#1C8C7D')}
    ${r('Collateral density', d.c, '#7A4FE0')}</div>`;
}
function styleMarkers(){
  const l=LENS[curLens];
  markers.forEach(m=>{
    const v=m._d[l.field];
    m.setStyle({fillColor:ramp3(v,l.ramp), radius:3+Math.min(v,100)/100*7});
  });
}
function setLens(k){
  curLens=k;
  document.querySelectorAll('.lens').forEach(b=>b.classList.toggle('on',b.dataset.l===k));
  renderLegend(); if(mapReady) styleMarkers();
}

/* ---------- branches ---------- */
function renderBranchSort(){
  const opts=[['o','Opportunity'],['a','Agri-PD'],['m','Merchant'],['c','Collateral'],['w','AutoX nearby']];
  $('#sortchips').innerHTML = opts.map(([k,t])=>`<button class="chip ${k===branchSort?'on':''}" data-s="${k}">${t}</button>`).join('');
  $('#sortchips').onclick=e=>{const b=e.target.closest('.chip'); if(!b)return; branchSort=b.dataset.s;
    document.querySelectorAll('.chip').forEach(c=>c.classList.toggle('on',c===b)); renderBranches();};
  $('#search').oninput=()=>renderBranches();
}
function renderBranches(){
  const q=($('#search').value||'').trim().toLowerCase();
  let rows=DATA.filter(d=>!q || d.n.toLowerCase().includes(q) || d.v.toLowerCase().includes(q));
  rows.sort((a,b)=> branchSort==='w' ? a.w-b.w : b[branchSort]-a[branchSort]);
  rows=rows.slice(0,150);
  $('#branches').innerHTML = `<tr><th>Branch</th><th>Prov</th><th>Opp</th><th>Agri</th><th>Merch</th><th>Collat</th><th>AutoX</th></tr>`+
    rows.map(d=>`<tr><td>${d.n}</td><td class="sub">${d.v}</td>
      <td class="mono" style="color:#E6B450">${d.o}</td>
      <td class="mono" style="color:#C8433B">${d.a}</td>
      <td class="mono" style="color:#1C8C7D">${d.m}</td>
      <td class="mono" style="color:#7A4FE0">${d.c}</td>
      <td class="mono sub">${d.w}</td></tr>`).join('');
}

boot();
