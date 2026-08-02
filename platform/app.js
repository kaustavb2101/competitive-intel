'use strict';
/* AutoX · เงินไชโย — Credit Intelligence Platform
   Loads data files, renders overview/map/acquisition/branches. Vanilla JS, no build step. */

/* Full HTML escape, for text this repo did not write. Almost everything rendered here is our own
   derived numbers and editorial copy, but Pantip posts, app-store reviews and YouTube comments are
   arbitrary strings typed by strangers and they reach innerHTML. Escape at the point of insertion.
   (Two functions further down declare a local `esc` that only escapes quotes for an attribute —
   that is a different job; this one is for element content and must not be confused with it.) */
const escHtml=s=>String(s==null?'':s).replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// Real measured quantities (no indices). val() reads measured fields; color/size scale to absolute max.
// Portfolio-risk lens is the exception: a/m/c are ESTIMATED proxies (OSM/price-based, 0–100), not measured.
// pill = the SHORT (≈2-word) label for the hero pill row docked over the National map.
// label = the longer legacy label (kept for the legend + aria). desc = plain-language methodology,
// surfaced as the per-pill "ⓘ" tooltip — NEVER name a pipeline script in copy shown in the UI.
// Order here is the pill order; the gold "Opportunity" lens is first and is the default on open.
// hero:true  → one of the 4 ALWAYS-VISIBLE hero pills docked over the map (the rest live in "More ▾").
// tag:'m'|'e' → the in-band [M] measured / [E] estimated badge shown on the pill (parity with the prov chips).
const LENS = {
  dws:  {pill:'Coverage gap', label:'District coverage gap ◇', desc:"COVERAGE · MEASURED — each branch's whole district demand (footfall + workers) minus how saturated AutoX already is there. Brighter = thinner AutoX coverage of local demand.", color:'#E6B450', unit:'coverage gap (0–100)', amp:true, hero:true, tag:'m', val:d=>d._amp?d._amp.whitespace:0},
  brisk:    {pill:'Composite risk', label:'Composite branch risk ▲ est', desc:"PORTFOLIO RISK · ESTIMATED composite (0–100) — one fused 'which branches are getting riskier' read, blending measured household debt + crop/drought stress + occupation concentration + the branch's own segment mix. A triage rank, not a measured default rate.", color:'#E0574F', unit:'composite (est)', est:true, brisk:true, hero:true, tag:'e', val:d=>briskVal(d)},
  comp:     {pill:'Competitors', label:'Competitor density ◆', desc:'COMPETITIVE PRESSURE · MEASURED (Google Places, a lower bound, not a registry) — rival title-loan branches (Srisawad, Muangthai, Tidlor, Heng) within ~5 km of each AutoX branch. Brighter = denser rival presence around us. Blank until the rival census loads.', color:'#E0574F', unit:'rivals ≤5km', cmp:true, hero:true, tag:'m', val:d=>compCount(d)},
  hhdti:    {pill:'Household DTI', label:'Household debt-to-income ●', desc:"BORROWER STRESS · MEASURED (NSO household survey 2566) — the branch's province household debt as a multiple of annual income. Brighter = more household balance-sheet stress. Hidden until the survey layer loads.", color:'#C8433B', unit:'×100 DTI', hh:true, prov:true, hero:true, tag:'m', val:d=>hhriskVal(d)},
  cstress:  {pill:'Agri PD', label:'Agri crop-stress ▲ est', desc:"PORTFOLIO RISK · ESTIMATED triage (0–100) — the branch's province crop-household stress (crop price pressure × drought, scaled by how farm-dependent the area is). A warning flag, not a measured default rate.", color:'#C8433B', unit:'crop-stress (est)', est:true, tag:'e', val:d=>cstressVal(d)},
  estab:    {pill:'Merchant', label:'Establishments ≤10km', desc:'MERCHANT BASE · MEASURED (Overture Places, a sample / lower bound) — total businesses within 10 km of each branch, a proxy for how much trade surrounds it. Brighter = a denser merchant ecosystem.', color:'#1C8C7D', unit:'estab', tag:'m', val:d=>estabCount(d)},
  motomix:  {pill:'Collateral', label:'Motorcycle-title share ▲', desc:'COLLATERAL EXPOSURE · MEASURED (DLT) — motorcycle share of the province vehicle stock. Motorcycles are the most volatile, lowest-recovery title collateral; brighter = more exposure to a used-bike value fall.', color:'#7A4FE0', unit:'% moto (DLT)', tag:'m', val:d=>motoShare(d)},
  occrisk:  {pill:'Occupation risk', label:'Occupation × stress ◆▲', desc:"PORTFOLIO RISK · MEASURED occupation mix × ESTIMATED stress weighting — flags branches whose borrower base is concentrated in a stressed sector (factories in a slowdown · farming under crop-stress). A triage flag, not a measured default rate.", color:'#C8433B', unit:'occ-stress (est)', est:true, occr:true, tag:'e', val:d=>occriskVal(d)},
  poirel:   {pill:'Relevant POI density', label:'Title-loan-relevant POI density ◇', desc:"BORROWER BASE · MEASURED counts (Overture/OSM, a sample / lower bound) — title-loan-relevant points of interest within ~10 km of each branch (gold shops, vehicle dealers, fresh markets, farms, factories, commerce, schools). Brighter = a denser pool of likely title-loan borrowers nearby. The per-category WEIGHTING that blends them into one 0–100 score is an estimated relevance model.", color:'#E6B450', unit:'relevant-POI (0–100)', poirel:true, tag:'m', val:d=>poiRelevanceVal(d)},
  drisk:{pill:'District risk', label:'District risk ▲ est', desc:"PORTFOLIO RISK · ESTIMATED (0–100) — the branch's district risk proxy (province crop-stress + province unemployment + local collateral / merchant mix). Not a measured default rate.", color:'#C8433B', unit:'district risk (est)', est:true, amp:true, tag:'e', val:d=>d._amp?d._amp.risk_proxy:0},
  unemp:{pill:'Unemployment', label:'District unemployment ▲', desc:"PORTFOLIO RISK · MEASURED (NSO Labour Force Survey, province-inherited) — the branch's district unemployment rate, shown raw rather than blended into the composite district-risk proxy above. Brighter = a higher local jobless rate.", color:'#C8433B', unit:'% unemployment', amp:true, unemp:true, tag:'m', val:d=>d._amp?(d._amp.unemployment_rate||0):0},
  dpico:{pill:'PICO rivals', label:'District PICO rivals ◆', desc:"COMPETITIVE PRESSURE · MEASURED (FPO registry) — licensed พิโกไฟแนนซ์ (PICO-finance) operators, a DISTINCT small-ticket rival class, registered in the branch's own district (อำเภอ). Brighter = more sub-scale rivals clustered in the same district. Kept separate from the district-risk lens (this is competition, obj #2 — not portfolio risk). Hidden until the district layer loads.", color:'#7A4FE0', unit:'PICO operators (district)', amp:true, pico:true, tag:'m', val:d=>d._amp?(d._amp.pico||0):0},
  doutnum:{pill:'Outnumbered', label:'PICO rivals per branch ◆', desc:"COMPETITIVE PRESSURE · MEASURED (FPO registry ÷ AutoX footprint) — licensed พิโกไฟแนนซ์ (PICO-finance) operators PER AutoX branch in the same district. Unlike raw PICO density, this weighs the rival field against how many branches we run there: brighter = the existing footprint is more heavily outnumbered street-by-street (obj #2 — pressure on the network we run, not a where-to-open cue). Defined only where AutoX operates; coverage-gap districts are the white-space lens's story. Kept separate from portfolio risk. Hidden until the district layer loads.", color:'#7A4FE0', unit:'PICO rivals / AutoX branch', amp:true, pico:true, tag:'m', val:d=>(d._amp&&d._amp.pico_ratio!=null)?d._amp.pico_ratio:null},
  crop: {pill:'Crop mix', label:'Dominant crop ◇ est', desc:"AGRI EXPOSURE · ESTIMATED (model-allocated crop areas) — each district coloured by its DOMINANT credit-relevant crop (rice / cassava / maize / sugarcane / oil palm) from SPAM 2010, a modeled spatial disaggregation of measured subnational statistics onto a ~9km grid. Shows which crop a district's borrower base depends on, so a macro move against that crop maps to exposure. Rubber is absent from SPAM (a known blind spot for the rubber belt).", color:'#4E9A6B', unit:'dominant crop', amp:true, cat:true, tag:'e', est:true, val:d=>0},
  pstress:{pill:'Province stress', label:'Province structural stress ▲ est', desc:"PORTFOLIO RISK · ESTIMATED composite (0–100) — blends the branch's province household debt-to-income percentile (NSO SES) with its province unemployment percentile (NSO LFS) into ONE 'which provinces are structurally riskiest' read, equal-weighted. Both inputs are measured; the blend + weighting are an editorial triage ordering, not a measured default rate. Hidden until the layer loads.", color:'#C8433B', unit:'stress (0–100, est)', pstr:true, prov:true, est:true, tag:'e', val:d=>pstressVal(d)},
  dsrch:{pill:'Search demand', label:'Title-loan search demand ▲ est', desc:"BRAND DEMAND · ESTIMATED (Google Trends relative index, 0–100) — how hard people in the branch's province search title-loan intent terms (จำนำทะเบียนรถ · สินเชื่อรถแลกเงิน). A demand/attention signal, NOT query volume or bookings. Hidden until the layer loads.", color:'#E6B450', unit:'search demand (0–100, est)', dsrch:true, prov:true, est:true, tag:'e', val:d=>sdemandVal(d)},
  peerdev:  {pill:'Vs twins', label:'Risk vs statistical twins ▲ est', desc:"PORTFOLIO RISK · ESTIMATED — how many points the branch's composite risk sits ABOVE its 15 statistical twins (branches with the most similar measured market elsewhere in the country, same household-leverage backdrop). Bright = the market alone doesn't explain the risk; something local is different. Audit these first.", color:'#E0574F', unit:'pts above twins (est)', est:true, peers:true, tag:'e', val:d=>peerDevVal(d)},
  macx:     {pill:'Macro headwind', label:'Macro headwind ▲ est', desc:"PORTFOLIO RISK · ESTIMATED — how exposed each branch's customer mix is to its dominant DETERIORATING macro factor (rice/rubber/palm price falls, drought, household leverage, factory slowdown). Brightest = customer base most exposed to a macro factor currently moving against them. Occupation mix MEASURED × sensitivity weights ESTIMATED × macro signals MEASURED; share-diluted scores, so compare branches relatively. Branches whose dominant factor is a tailwind read 0 — this lens flags headwinds.", color:'#C8433B', unit:'macro headwind (est, relative)', est:true, macx:true, tag:'e', val:d=>macxHeadwindVal(d)},
  workers:  {pill:'Factory jobs', label:'Factory workers', desc:'BORROWER BASE · MEASURED (DIW) — registered factory employment in the branch district. Brighter = a larger wage-earning borrower base nearby.', color:'#E6B450', unit:'workers', tag:'m', val:d=>d.dwork||0},
  pickups:  {pill:'Pickup stock', label:'Pickup stock', desc:'COLLATERAL SUPPLY · MEASURED (DLT) — pickup trucks registered in the province, the higher-recovery title collateral. Brighter = more pickup collateral to lend against.', color:'#7A4FE0', unit:'pickups', tag:'m', val:d=>(PLOOK[d.v]||{}).pickup||0},
  informal: {pill:'Informal labour', label:'Informal workforce', desc:'BORROWER BASE · MEASURED (NSO) — informal (cash-economy) workers in the province, the core title-loan customer. Brighter = a larger informal borrower base.', color:'#1C8C7D', unit:'workers', tag:'m', val:d=>(PLOOK[d.v]||{}).informal||0},
  autox:    {pill:'AutoX density', label:'AutoX saturation', desc:'OWN FOOTPRINT · MEASURED — how many AutoX branches sit within 10 km. Brighter = more self-overlap (cannibalisation risk); dark = standalone coverage.', color:'#5B7CFA', unit:'AutoX ≤10km', tag:'m', val:d=>d.w||0},
  risk:     {pill:'Segment risk', label:'Portfolio risk ▲ est', desc:'PORTFOLIO RISK · ESTIMATED proxy (0–100) — the worst of agri-PD / merchant / collateral segment stress. Switch the sub-metric below the pills. Not a measured default rate.', color:'#E0574F', unit:'risk (est)', est:true, tag:'e', val:d=>riskVal(d)},
};
// the 4 hero lens keys, in pill order (always visible; rest live in the More ▾ dropdown).
const HERO_LENS=['dws','brisk','comp','hhdti'];
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

// per-amphoe drought — lazy-loaded from data/drought_district.json (objective #1). MODELLED OAE SPEI
// (ERA5-Land reanalysis): a DISTRICT-grain read behind the province crop-stress verdict. Promise-cached.
let droughtdPromise=null;
function loadDroughtDistrict(){
  if(droughtdPromise) return droughtdPromise;
  droughtdPromise=fetch('data/drought_district.json').then(r=>r.ok?r.json():null).catch(()=>null);
  return droughtdPromise;
}

// District crop × drought exposure — lazy-loaded from data/amphoe_crops.json (objective #1). MEASURED
// planted area (OAE satellite amphoe surveys) × MODELLED drought (OAE SPEI). Names WHICH crop in WHICH
// district carries the largest rai exposure under drought — the crop-named, portfolio-actionable read
// behind the district-drought card above. Promise-cached.
let amphoecropsPromise=null;
function loadAmphoeCrops(){
  if(amphoecropsPromise) return amphoecropsPromise;
  amphoecropsPromise=fetch('data/amphoe_crops.json').then(r=>r.ok?r.json():null).catch(()=>null);
  return amphoecropsPromise;
}

// Provincial labour market — MEASURED, NSO Labour Force Survey 2026 Q1, all 77 provinces
// (data/province_lfs.json). Carries per-province unemployment_rate_pct + seasonal_share_pct (the
// share of the labour force "seasonally waiting" — idle between agricultural seasons). Obj #1: an
// income-timing backdrop behind the agri-PD book. Fully null-guarded: absent file → LFS stays null,
// the Overview block stays hidden (see renderProvinceLfs), nothing fabricated.
let LFS=null, LFS_META=null, lfsPromise=null;
async function loadProvinceLfs(){
  if(lfsPromise) return lfsPromise;
  lfsPromise=(async()=>{
    try{
      const j = await fetch('data/province_lfs.json').then(r=>r.json());
      LFS=j.provinces||null; LFS_META=j.meta||null;
    }catch(e){ LFS=null; LFS_META=null; }
    return LFS;
  })();
  return lfsPromise;
}
// RETIRED 2026-08-02 — the client loaders for data/napprang.json (OAE dry-season 2nd-rice area) and
// data/crop_margin.json (farm-gate price vs OAE cost). Both files are still MAINTAINED and still
// shipped; they are now read SERVER-SIDE by pipeline/build_farm_book.py and reach the page inside
// farm_book.json, so the browser no longer fetches them separately. Removing the loaders removes two
// network round-trips on every Overview render and, more importantly, removes the second copy of a
// join that used to live in both the builder and the page.
// New-vehicle first-registration TREND (data/brand_trends.json, DLT first registrations by year).
// Obj #1, collateral outlook: which vehicles enter the fleet today become tomorrow's used-title
// collateral pool. The diesel-share card above is a point-in-time snapshot; this carries the TIME
// dimension — how fast the future used-pickup collateral pool is replenished at source. Null-safe:
// absent / malformed file → BTREND stays null and the Overview block stays hidden.
let BTREND=null, btrendPromise=null;
async function loadBrandTrends(){
  if(btrendPromise) return btrendPromise;
  btrendPromise=(async()=>{
    try{
      const j = await fetch('data/brand_trends.json').then(r=>r.json());
      BTREND=(j&&j.new_regis_trend&&typeof j.new_regis_trend==='object')?j:null;
    }catch(e){ BTREND=null; }
    return BTREND;
  })();
  return btrendPromise;
}
// Regional household-debt backdrop — MEASURED (Bank of Thailand regional letters over NSO Socio-Economic
// Survey [SES] data; per-series vintages carried, the 4-region debt-per-household cut = SES 2566/2023, the
// most recent common vintage). Obj #1: household leverage is a DIRECT portfolio-risk backdrop — where
// borrower households already carry the most debt, an income shock bites soonest. Fully null-guarded:
// absent file → REGDEBT stays null, the Overview block stays hidden (see renderRegionDebt), nothing faked.
let REGDEBT=null, REGDEBT_META=null, REGDEBT_HEAD=null, regdebtPromise=null;
async function loadRegionDebt(){
  if(regdebtPromise) return regdebtPromise;
  regdebtPromise=(async()=>{
    try{
      const j = await fetch('data/region_debt.json').then(r=>r.json());
      REGDEBT=(j&&j.series)?j.series:null; REGDEBT_META=j.meta||null; REGDEBT_HEAD=j.headline||null;
    }catch(e){ REGDEBT=null; REGDEBT_META=null; REGDEBT_HEAD=null; }
    return REGDEBT;
  })();
  return regdebtPromise;
}
// RETIRED 2026-08-02 — the client loaders for data/truck_flow.json and data/collateral_flow.json.
// Both files are still MAINTAINED and still shipped; they are now read SERVER-SIDE by
// pipeline/build_collateral_book.py and reach the page inside collateral_book.json, where they sit
// with the rest of the collateral picture instead of in a business-backdrop section (owner points
// 18 + 19). Two fewer fetches per Overview render, and one place where the join lives.

// Business-formation pulse — MEASURED DBD (Department of Business Development) new juristic-person
// registrations for the snapshot month (data/dbd_formation.json). Per province: n new firms +
// registered capital. A DEMAND / economic-vitality backdrop for BOTH objectives: where new small
// businesses form maps the merchant / small-ticket borrower base AutoX's book draws on. It is ONE
// month's flow (a formation pulse, not a stock of active firms) and is NOT a competitor layer and NOT
// an open/expand cue — a vitality read on the footprint we already run. Fully null-guarded: absent
// file → DBDFORM stays null, the Overview block stays hidden (see renderDbdForm), nothing fabricated.
let DBDFORM=null, DBDFORM_META=null, dbdformPromise=null;
async function loadDbdForm(){
  if(dbdformPromise) return dbdformPromise;
  dbdformPromise=(async()=>{
    try{
      const j = await fetch('data/dbd_formation.json').then(r=>r.json());
      DBDFORM=j&&typeof j.by_province==='object'?j:null; DBDFORM_META=j&&j.meta?j.meta:null;
    }catch(e){ DBDFORM=null; DBDFORM_META=null; }
    return DBDFORM;
  })();
  return dbdformPromise;
}

// SFI system credit-quality backdrop — MEASURED quarterly NPL ratio of Thailand's Specialized Financial
// Institutions (GSB/BAAC/GHB/SME/EXIM/Islamic Bank) from FPO aggregates (data/sfi_credit.json). Obj #1
// leading-indicator BACKDROP: GSB (household) + BAAC (rural/agri) system NPL is the closest public read
// on the repayment stress AutoX's borrowers sit inside — a macro tide, NOT AutoX's own book and NOT
// per-province. Null-guarded: absent/short file → SFI stays null, the Overview block stays hidden
// (see renderSfi), nothing fabricated.
let SFI=null, SFI_META=null, sfiPromise=null;
async function loadSfi(){
  if(sfiPromise) return sfiPromise;
  sfiPromise=(async()=>{
    try{
      const j = await fetch('data/sfi_credit.json').then(r=>r.json());
      SFI=(j&&Array.isArray(j.series)&&j.series.length)?j.series:null; SFI_META=j&&j.meta?j.meta:null;
    }catch(e){ SFI=null; SFI_META=null; }
    return SFI;
  })();
  return sfiPromise;
}

// Live flood + rain pulse — MEASURED live ThaiWater telemetry (keyless api-v3.thaiwater.net; refreshed
// daily by .github/workflows/data-thaiwater.yml). Two per-province station aggregates: water LEVEL
// (data/thaiwater_flood.json — situation_level 1→5, ≥4 = high water / bank overflow) and 24h RAINFALL
// (data/thaiwater_rain.json — heavy ≥35.1mm, very heavy ≥90.1mm per Thai Met convention). Obj #1: water
// on the ground / arriving is an acute collections + collateral event, days before it reaches any
// monthly series — the fast counterpart to the slower crop-stress drought read. Fully null-guarded: if
// EITHER layer is absent the block stays hidden (see renderThaiwater), nothing fabricated.
let TWFLOOD=null, TWFLOOD_META=null, TWRAIN=null, TWRAIN_META=null, thaiwaterPromise=null;
async function loadThaiwater(){
  if(thaiwaterPromise) return thaiwaterPromise;
  thaiwaterPromise=(async()=>{
    try{
      const f = await fetch('data/thaiwater_flood.json').then(r=>r.json());
      TWFLOOD=(f&&f.provinces&&typeof f.provinces==='object')?f.provinces:null; TWFLOOD_META=f&&f.meta?f.meta:null;
    }catch(e){ TWFLOOD=null; TWFLOOD_META=null; }
    try{
      const r = await fetch('data/thaiwater_rain.json').then(x=>x.json());
      TWRAIN=(r&&r.provinces&&typeof r.provinces==='object')?r.provinces:null; TWRAIN_META=r&&r.meta?r.meta:null;
    }catch(e){ TWRAIN=null; TWRAIN_META=null; }
    return TWFLOOD;
  })();
  return thaiwaterPromise;
}

// Compact rai formatter for the second-rice exposure column ("0.91M rai" / "328k rai").
function fmtRai(n){
  if(n==null||!isFinite(n)) return '—';
  if(n>=1e6) return (n/1e6).toFixed(2).replace(/\.?0+$/,'')+'M rai';
  if(n>=1e3) return Math.round(n/1e3)+'k rai';
  return n+' rai';
}

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

/* ---------- combined province structural stress (household DTI + unemployment, objective #1) ----------
   Lazy-loaded from data/province_stress_index.json (pipeline/build_province_stress.py). PSTRESS maps
   Thai province name -> {debt_to_income, dti_percentile, unemployment_rate, unemployment_percentile,
   composite_stress, rank}. debt_to_income + unemployment_rate are MEASURED (NSO SES / NSO LFS);
   the two percentiles + composite_stress are an ESTIMATED equal-weighted blend. Null-guarded: if the
   file is ABSENT, PSTRESS stays empty, the lens hides itself, val() reads 0 — never errors. */
let PSTRESS=null, PSTRESS_META=null, PSTRESS_LIST=[], pstressLoaded=false, pstressPromise=null;
async function loadProvinceStress(){
  if(pstressPromise) return pstressPromise;
  pstressLoaded=true;
  pstressPromise=(async()=>{
    try{
      const r=await fetch('data/province_stress_index.json'); if(!r.ok) throw 0;
      const j=await r.json();
      PSTRESS_META=j.meta||null; PSTRESS={}; PSTRESS_LIST=[];
      if(!(j.meta&&j.meta.absent)){
        const list=(j.provinces||[]).filter(p=>p&&p.composite_stress!=null);
        list.forEach(p=>{PSTRESS[p.province]=p;});
        PSTRESS_LIST=list.slice().sort((a,b)=>(b.composite_stress||0)-(a.composite_stress||0));
      }
    }catch(e){ PSTRESS={}; PSTRESS_META=null; PSTRESS_LIST=[]; }
    return PSTRESS;
  })();
  return pstressPromise;
}
function pstressHasData(){return !!(PSTRESS&&Object.keys(PSTRESS).length);}
// ESTIMATED composite_stress (0-100) for a branch's province. 0 when unknown.
function pstressVal(d){const p=PSTRESS&&PSTRESS[d.v]; return p&&p.composite_stress!=null?Math.round(p.composite_stress):0;}

/* ---------- lowest-paid occupation nationally (objective #1) ----------
   Lazy-loaded from data/occupation_income.json (pipeline/build_occupation_income.py) — a national
   aggregate of the already-MEASURED province.html "income by occupation" panel (NSO SES 2566).
   OCCINC_LIST is sorted worst-first (lowest national_avg first), so OCCINC_LIST[0] is the concrete
   "lowest-paid occupation nationally" fact. Null-guarded: ABSENT source -> empty list, no error. */
let OCCINC_LIST=[], occincLoaded=false, occincPromise=null;
async function loadOccupationIncome(){
  if(occincPromise) return occincPromise;
  occincLoaded=true;
  occincPromise=(async()=>{
    try{
      const r=await fetch('data/occupation_income.json'); if(!r.ok) throw 0;
      const j=await r.json();
      OCCINC_LIST=(j.meta&&j.meta.absent)?[]:(j.categories||[]);
    }catch(e){ OCCINC_LIST=[]; }
    return OCCINC_LIST;
  })();
  return occincPromise;
}
function occincHasData(){return !!(OCCINC_LIST&&OCCINC_LIST.length);}

/* ---------- SME-owner income floor by province (merchant-lending segment, objective #1) ----------
   Lazy-loaded from data/sme_income_by_province.json (pipeline/build_sme_income.py) — NSO SES 2566
   SMEOwners-occupation monthly income, MEASURED, same builder shape as the factory/agri income-floor
   layers already surfaced on province.html/Simulator, applied here to the merchant segment instead.
   SMEINC_LIST is sorted worst-first (lowest ratio_to_national first). Null-guarded: ABSENT source ->
   empty list, no error. */
let SMEINC_LIST=[], SMEINC_META=null, smeincLoaded=false, smeincPromise=null;
async function loadSmeIncome(){
  if(smeincPromise) return smeincPromise;
  smeincLoaded=true;
  smeincPromise=(async()=>{
    try{
      const r=await fetch('data/sme_income_by_province.json'); if(!r.ok) throw 0;
      const j=await r.json();
      SMEINC_META=j.meta||null;
      const prov=(j.meta&&j.meta.absent)?{}:(j.provinces||{});
      SMEINC_LIST=Object.keys(prov).map(name=>Object.assign({province:name},prov[name]))
        .filter(p=>p.ratio_to_national!=null)
        .sort((a,b)=>(a.ratio_to_national||0)-(b.ratio_to_national||0));
    }catch(e){ SMEINC_LIST=[]; SMEINC_META=null; }
    return SMEINC_LIST;
  })();
  return smeincPromise;
}
function smeincHasData(){return !!(SMEINC_LIST&&SMEINC_LIST.length);}

/* ---------- title-loan SEARCH DEMAND + brand share-of-search (ESTIMATED · Google Trends, objective #2) ----------
   Lazy-loaded from data/search_demand.json (pipeline/build_search_demand.py). SDEMAND maps Thai province
   name -> {demand, sos:{brand:share}, autox_share, best_rival, autox_sos_rank, ...}. demand is a 0–100
   RELATIVE search-interest index (NOT query volume); sos is a share-of-search fraction (null in an all-zero
   province — the builder's honest guard). Everything is ESTIMATED. Null-guarded: absent file → SDEMAND stays
   empty, the map lens hides itself (lensAbsent), sdemandVal reads 0, and the #acq board shows a calm notice. */
let SDEMAND=null, SDEMAND_META=null, SDEMAND_LIST=[], sdemandLoaded=false, sdemandPromise=null;
async function loadSearchDemand(){
  if(sdemandPromise) return sdemandPromise;
  sdemandLoaded=true;
  sdemandPromise=(async()=>{
    try{
      const r=await fetch('data/search_demand.json'); if(!r.ok) throw 0;
      const j=await r.json();
      SDEMAND_META=j.meta||null; SDEMAND={}; SDEMAND_LIST=[];
      if(!(j.meta&&j.meta.absent)){
        const list=(j.provinces||[]).filter(p=>p&&p.demand!=null);
        list.forEach(p=>{SDEMAND[p.th]=p;});
        // sort by demand desc so the board/headline lead with the hottest-searching province.
        SDEMAND_LIST=list.slice().sort((a,b)=>(b.demand||0)-(a.demand||0));
      }
    }catch(e){ SDEMAND={}; SDEMAND_META=null; SDEMAND_LIST=[]; }
    return SDEMAND;
  })();
  return sdemandPromise;
}
function sdemandHasData(){return !!(SDEMAND&&Object.keys(SDEMAND).length);}
// ESTIMATED relative search-demand (0–100) for a branch's province. 0 when unknown.
function sdemandVal(d){const p=SDEMAND&&SDEMAND[d.v]; return p&&p.demand!=null?Math.round(p.demand):0;}

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
// O(1) branch index for the index-aligned lens data files. boot() stamps d._i on every branch;
// fall back to a linear scan only if that ever didn't run (defensive — keeps behaviour identical).
function idxOf(d){ return (d&&d._i!=null)?d._i:(DATA?DATA.indexOf(d):-1); }
// total measured establishments ≤10km for a branch (0 when the file/entry is absent) — the "estab" lens val().
function estabCount(d){
  if(!OCCDATA||!OCCDATA.branches||!DATA) return 0;
  const i=idxOf(d); if(i<0) return 0;
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

/* ---------- per-branch WORKFORCE mix (data/branch_workforce.json) ----------
   Lazy-loads the ESTIMATED per-branch WORKFORCE layer (build_branch_workforce.py): the mix of
   people by occupation within 10km, each occupation from the source that actually measures it —
   farmers from SPAM cropland × OAE area anchored to the NSO agri headline, factory from DIW,
   the 12 storefront occupations from Overture POI × headcount. Unlike branch_occupations.json
   (which counts BUSINESSES and so buries farmers), this answers "who WORKS here" and is the
   lead-by-occupation signal. Shape: { meta, buckets:[{key,label}], branches:[{w:[people],
   mix:[pct], top:[idx], dom, t}] } — INDEX-ALIGNED to branches.json. Fully null-guarded. */
let WFDATA=null, wfLoaded=false, wfPromise=null;
async function loadWorkforce(){
  if(wfPromise) return wfPromise;
  wfLoaded=true;
  wfPromise=(async()=>{
    try{ const r=await fetch('data/branch_workforce.json'); if(r.ok) WFDATA=await r.json(); }
    catch(e){ WFDATA=null; }
    return WFDATA;
  })();
  return wfPromise;
}

/* ---------- per-branch AGRICULTURE profile (data/branch_agri.json) ----------
   Crop exposure (SPAM) + REAL OAE farm-gate price stress + per-branch drought + farm income.
   Shape: { meta:{crops:[{key,label}],crop_price_yoy,...}, branches:[{ha,sh,dom,crop_ha,price_yoy,
   price_stress,rain_anom,drought_stress,intensity,agri_pressure,income_est}] } INDEX-ALIGNED. */
let AGRIDATA=null, agriLoaded=false, agriPromise=null;
async function loadAgri(){
  if(agriPromise) return agriPromise;
  agriLoaded=true;
  agriPromise=(async()=>{
    try{ const r=await fetch('data/branch_agri.json'); if(r.ok) AGRIDATA=await r.json(); }
    catch(e){ AGRIDATA=null; }
    return AGRIDATA;
  })();
  return agriPromise;
}

/* ---------- per-branch VEHICLE COLLATERAL (data/branch_vehicles.json) ----------
   DLT province vehicle stock allocated to each 10km catchment: est fleet by type + collateral
   mix + pickup share + a title-loan-able collateral score. Shape: { meta:{types,labels,...},
   branches:[{fleet:{car,pickup,moto,ev},mix,dom,pickup_share,collateral_score,n_est}] } aligned. */
let VEHDATA=null, vehLoaded=false, vehPromise=null;
async function loadVehicles(){
  if(vehPromise) return vehPromise;
  vehLoaded=true;
  vehPromise=(async()=>{
    try{ const r=await fetch('data/branch_vehicles.json'); if(r.ok) VEHDATA=await r.json(); }
    catch(e){ VEHDATA=null; }
    return VEHDATA;
  })();
  return vehPromise;
}

/* ---------- per-branch EMPLOYMENT & LABOUR (data/branch_labor.json) ----------
   Lazy-loads the MEASURED per-branch labour layer built by pipeline/build_branch_labor.py:
   top-3 catchment occupation buckets (Overture), district factory workers (DIW), province
   informal share + Labour-Force-Survey summary (NSO), all joined onto each branch by index/
   province. Shape: { meta, buckets, branches:[{occ_top:[{label,share_pct}], estab_total,
   factory_workers|null, informal_pct|null, prov_employed_k|null, prov_labor_force_k|null,
   prov_unemployment_rate|null}] } — branches[] is INDEX-ALIGNED to branches.json (entry i ↔ DATA[i]).
   Fully null-guarded: absent file/entry → nothing renders (the popup section is simply omitted). */
let LABORDATA=null, laborLoaded=false, laborPromise=null;
async function loadBranchLabor(){
  if(laborPromise) return laborPromise;
  laborLoaded=true;
  laborPromise=(async()=>{
    try{ const r=await fetch('data/branch_labor.json'); if(r.ok) LABORDATA=await r.json(); }
    catch(e){ LABORDATA=null; }
    return LABORDATA;
  })();
  return laborPromise;
}
function laborRec(d){
  if(!LABORDATA||!LABORDATA.branches||!DATA) return null;
  const i=idxOf(d); if(i<0) return null;
  return LABORDATA.branches[i]||null;
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
  const i=idxOf(d); if(i<0) return 0;
  const e=OCCRISK[i]; return (e&&e.s)||0;
}
// the per-branch occupation-risk record (for popups) — null when absent.
function occriskRec(d){
  if(!occriskHasData()||!DATA) return null;
  const i=idxOf(d); if(i<0) return null;
  return OCCRISK[i]||null;
}

/* ---------- per-province factory-worker income floor (data/factory_income_by_province.json) ----------
   MEASURED (NSO SES 2566), keyed by province Thai name (matches branch field d.v). Lets the
   Simulator's factory-slowdown lever (simFactoryModel) name WHICH manufacturing-base branches sit
   in a province whose factory-worker income already runs below the national average — a concrete
   geographic read layered on top of the existing flat national severity knob. Purely additive:
   simFactoryModel()'s core scenario numbers are unchanged whether this file is present or not.
   Written by pipeline/build_factory_income.py. Null-guarded throughout. */
let FACTINC=null, factincMeta=null, factincLoaded=false, factincPromise=null;
async function loadFactoryIncome(){
  if(factincPromise) return factincPromise;
  factincLoaded=true;
  factincPromise=(async()=>{
    try{ const r=await fetch('data/factory_income_by_province.json'); if(!r.ok) throw 0;
      const j=await r.json(); factincMeta=j.meta||null;
      FACTINC=(factincMeta&&factincMeta.absent)?null:(j.provinces||null); }
    catch(e){ FACTINC=null; factincMeta=null; }
    return FACTINC;
  })();
  return factincPromise;
}
function factincHasData(){return !!(FACTINC&&Object.keys(FACTINC).length);}

/* ---------- per-province agriculture-worker income floor (data/agri_income_by_province.json) ----------
   MEASURED (NSO SES 2566), keyed by province Thai name (matches crop_stress.json's `th`). Mirrors
   FACTINC/factory_income_by_province.json for a different NSO SES occupation column — lets the
   Simulator's crop-price/rainfall what-if (computeSim) show a static, MEASURED income-floor context
   alongside the ESTIMATED price/drought agri-stress scenario. Purely additive: computeSim()'s core
   scenario numbers are unchanged whether this file is present or not.
   Written by pipeline/build_agri_income.py. Null-guarded throughout. */
let AGRIINC=null, agrincMeta=null, agrincLoaded=false, agrincPromise=null;
async function loadAgriIncome(){
  if(agrincPromise) return agrincPromise;
  agrincLoaded=true;
  agrincPromise=(async()=>{
    try{ const r=await fetch('data/agri_income_by_province.json'); if(!r.ok) throw 0;
      const j=await r.json(); agrincMeta=j.meta||null;
      AGRIINC=(agrincMeta&&agrincMeta.absent)?null:(j.provinces||null); }
    catch(e){ AGRIINC=null; agrincMeta=null; }
    return AGRIINC;
  })();
  return agrincPromise;
}
function agrincHasData(){return !!(AGRIINC&&Object.keys(AGRIINC).length);}

/* ---------- per-branch RELEVANT-POI density (data/poi_relevance.json, obj#2) ----------
   Lazy-loads the title-loan-relevant POI-density layer built by pipeline/build_poi_relevance.py:
   {meta, branches:[{rel:0..100, raw, cat:{...category counts...}, src}]}, INDEX-ALIGNED to
   branches.json (entry i ↔ DATA[i]). The category COUNTS are MEASURED (Overture/OSM, a sample /
   lower bound); the per-category WEIGHTING that fuses them into the 0–100 `rel` score is an
   ESTIMATED relevance model (stated in the lens tooltip + legend). Fully null-guarded: absent file
   → POIREL stays empty, the lens hides itself (renderLenses), poiRelevanceVal() reads 0, and the
   popup block is omitted. Nothing is fabricated. */
let POIREL=null, poirelMeta=null, poirelLoaded=false, poirelPromise=null;
async function loadPoiRelevance(){
  if(poirelPromise) return poirelPromise;
  poirelLoaded=true;
  poirelPromise=(async()=>{
    try{ const r=await fetch('data/poi_relevance.json'); if(!r.ok){POIREL=null;return POIREL;}
      const j=await r.json(); poirelMeta=j.meta||null; POIREL=j.branches||null; }
    catch(e){ POIREL=null; poirelMeta=null; }
    return POIREL;
  })();
  return poirelPromise;
}
// true once the layer is loaded AND carries at least one branch read (i.e. not absent/empty).
function poiRelevanceHasData(){return !!(POIREL&&POIREL.length);}
// MEASURED-counts / ESTIMATED-weighting relevance score (0..100) for a branch — 0 when absent.
function poiRelevanceVal(d){
  if(!poiRelevanceHasData()||!DATA) return 0;
  const i=idxOf(d); if(i<0) return 0;
  const e=POIREL[i]; return (e&&e.rel)||0;
}
// per-branch relevant-POI record (for popups) — null when absent.
function poiRelevanceRec(d){
  if(!poiRelevanceHasData()||!DATA) return null;
  const i=idxOf(d); if(i<0) return null;
  return POIREL[i]||null;
}

/* ---------- per-branch BUILDING DENSITY within 10km (data/branch_density.json) ----------
   Lazy-loads pipeline/build_branch_density.py's projection of the already-committed
   source-data/perimeter_counts.json: {meta, branches:[{buildings_10km, bucket}]}, INDEX-ALIGNED
   to branches.json. buildings_10km is a MEASURED Overture footprint count (a sample from the
   capped per-province catchment pulls — a zero can mean "catchment file capped before reaching
   here", not "no buildings on the ground"). Fully null-guarded: absent file → BLDGDEN stays
   empty, bldgDensityRec() reads null, the popup block is omitted. Nothing is fabricated. */
let BLDGDEN=null, bldgdenLoaded=false, bldgdenPromise=null;
async function loadBranchDensity(){
  if(bldgdenPromise) return bldgdenPromise;
  bldgdenLoaded=true;
  bldgdenPromise=(async()=>{
    try{ const r=await fetch('data/branch_density.json'); if(!r.ok){BLDGDEN=null;return BLDGDEN;}
      const j=await r.json(); BLDGDEN=j.branches||null; }
    catch(e){ BLDGDEN=null; }
    return BLDGDEN;
  })();
  return bldgdenPromise;
}
// per-branch building-density record (for popups) — null when absent.
function bldgDensityRec(d){
  if(!BLDGDEN||!BLDGDEN.length||!DATA) return null;
  const i=idxOf(d); if(i<0) return null;
  return BLDGDEN[i]||null;
}

/* ---------- per-branch FUEL-STATION count within 10km (data/branch_fuel.json) ----------
   Lazy-loads pipeline/build_branch_fuel.py's projection of the committed source-data/fuel_stations.json
   (OSM amenity=fuel, Overpass pull): {meta, branches:[{n10}]}, INDEX-ALIGNED to branches.json. n10 is a
   MEASURED OSM fuel-station count ≤10km — a vehicle-economy / rural-reach signal (where fuel sells, the
   vehicles that back the title book live and move). OSM completeness varies, so a low/zero count is a
   FLOOR, not a census (stated inline). Fully null-guarded: absent file → FUELSTN stays null, fuelStnRec()
   reads null, the popup line is omitted. Nothing is fabricated. (Distinct from the LIVE fuel-PRICE
   globals below — this is the per-branch station COUNT layer.) */
let FUELSTN=null, fuelstnLoaded=false, fuelstnPromise=null;
async function loadBranchFuel(){
  if(fuelstnPromise) return fuelstnPromise;
  fuelstnLoaded=true;
  fuelstnPromise=(async()=>{
    try{ const r=await fetch('data/branch_fuel.json'); if(!r.ok){FUELSTN=null;return FUELSTN;}
      const j=await r.json(); FUELSTN=j.branches||null; }
    catch(e){ FUELSTN=null; }
    return FUELSTN;
  })();
  return fuelstnPromise;
}
// per-branch fuel-station record (for popups) — null when absent.
function fuelStnRec(d){
  if(!FUELSTN||!FUELSTN.length||!DATA) return null;
  const i=idxOf(d); if(i<0) return null;
  return FUELSTN[i]||null;
}

/* ---------- per-branch MEASURED-corrected CROP-AREA within 10km (data/branch_cropland.json) ----
   Lazy-loads pipeline/build_branch_cropland.py's output: {meta:{crops[],provenance,...},
   branches:[{ha:[…5 crops], crop_ha, dom, fac:[…]}]}, INDEX-ALIGNED to branches.json. The per-crop
   hectares are SPAM-2010's within-province spatial pattern (ESTIMATED) rescaled to DOAE's MEASURED
   2025 provincial planted-area magnitude — so the AREA is measured-corrected, the fine spatial
   distribution modelled (sugarcane uncorrected — OCSB, no DOAE). Complements the agri block's crop
   SHARE bars with absolute MAGNITUDE. Fully null-guarded: absent file → CROPLAND stays null and the
   popup block is omitted. Nothing is fabricated. */
let CROPLAND=null, croplandMeta=null, croplandLoaded=false, croplandPromise=null;
async function loadBranchCropland(){
  if(croplandPromise) return croplandPromise;
  croplandLoaded=true;
  croplandPromise=(async()=>{
    try{ const r=await fetch('data/branch_cropland.json'); if(!r.ok){CROPLAND=null;return CROPLAND;}
      const j=await r.json(); croplandMeta=j.meta||null; CROPLAND=j.branches||null; }
    catch(e){ CROPLAND=null; croplandMeta=null; }
    return CROPLAND;
  })();
  return croplandPromise;
}
// per-branch measured-corrected crop-area record (for popups) — null when absent.
function croplandRec(d){
  if(!CROPLAND||!CROPLAND.length||!DATA) return null;
  const i=idxOf(d); if(i<0) return null;
  return CROPLAND[i]||null;
}

/* ---------- per-branch COMPOSITE risk (data/branch_risk.json, obj#1) ----------
   Lazy-loads the fused composite-risk layer built by pipeline/build_branch_risk.py:
   {meta, branches:[{code, composite_risk 0–100, components{household,agri,occupation,segment},
   top_driver}]}, INDEX-ALIGNED to branches.json. It is an ESTIMATED composite (stated in the lens
   tooltip). Fully null-guarded: absent file → BRISK stays empty, the lens hides itself
   (renderLenses) and val() reads 0, the popup block is omitted. Nothing is fabricated. */
let BRISK=null, briskMeta=null, briskLoaded=false, briskPromise=null;
async function loadBranchRisk(){
  if(briskPromise) return briskPromise;
  briskLoaded=true;
  briskPromise=(async()=>{
    try{ const r=await fetch('data/branch_risk.json'); if(!r.ok){BRISK=null;return BRISK;}
      const j=await r.json(); briskMeta=j.meta||null; BRISK=j.branches||null; }
    catch(e){ BRISK=null; briskMeta=null; }
    return BRISK;
  })();
  return briskPromise;
}
function briskHasData(){return !!(BRISK&&BRISK.length);}
// ESTIMATED composite risk (0..100) for a branch — 0 when the file/entry is absent.
function briskVal(d){
  if(!briskHasData()||!DATA) return 0;
  const i=idxOf(d); if(i<0) return 0;
  const e=BRISK[i]; return (e&&e.composite_risk)||0;
}
// per-branch composite-risk record (for popups) — null when absent.
function briskRec(d){
  if(!briskHasData()||!DATA) return null;
  const i=idxOf(d); if(i<0) return null;
  return BRISK[i]||null;
}
// human label for a composite top_driver key (household/agri/occupation/segment).
const RISK_DRIVER_LABEL={household:'household leverage',agri:'crop / drought stress',occupation:'occupation concentration',segment:'segment / collateral mix'};
function riskDriverLabel(k){return RISK_DRIVER_LABEL[k]||k||'mixed';}

/* ---------- WHO-TO-ACQUIRE lead board (data/branch_leads.json, obj#2) ----------
   Lazy-loads the per-branch occupation lead board built by pipeline/build_branch_leads.py:
   {meta, buckets:[{k,label,fit,w,seg,why}], branches:[{leads:[{k,n,f,rf}], u:[...], inf, fw}]},
   INDEX-ALIGNED to branches.json (entry i ↔ DATA[i]). The counts (n) are MEASURED (Overture
   establishments ≤10km, a sample / lower bound); the high/med/low fit ranking, the ⚠ stressed-
   sector flag (rf) and the "untapped" inference (u[]) are ESTIMATED (editorial fit map + segment-
   score quartiles — stated in the popup). Fully null-guarded: absent file → LEADS stays null and
   the popup block is omitted. Nothing is fabricated. */
let LEADS=null, leadsBK=null, leadsMeta=null, leadsLoaded=false, leadsPromise=null;
async function loadBranchLeads(){
  if(leadsPromise) return leadsPromise;
  leadsLoaded=true;
  leadsPromise=(async()=>{
    try{ const r=await fetch('data/branch_leads.json'); if(!r.ok){LEADS=null;return LEADS;}
      const j=await r.json(); leadsMeta=j.meta||null; LEADS=j.branches||null;
      leadsBK={}; (j.buckets||[]).forEach(b=>{ if(b&&b.k) leadsBK[b.k]=b; }); }
    catch(e){ LEADS=null; leadsBK=null; leadsMeta=null; }
    return LEADS;
  })();
  return leadsPromise;
}
// per-branch lead-board record (for popups) — null when the file/entry is absent.
function leadsRec(d){
  if(!LEADS||!LEADS.length||!DATA) return null;
  const i=idxOf(d); if(i<0) return null;
  return LEADS[i]||null;
}

/* ---------- MACRO-EXPOSURE profile (data/macro_exposure.json, obj#1) ----------
   Lazy-loads the per-branch macro-factor exposure built by pipeline/build_macro_exposure.py:
   {meta:{factors:[{key,label,signal,severity,direction}],…}, branches:[{t3:[[factor,score,dir]…], d}]},
   INDEX-ALIGNED to branches.json. Scores are ESTIMATED composites (MEASURED occupation shares ×
   ESTIMATED sensitivity weights × MEASURED macro signals) and are SHARE-DILUTED (meta.score_scale:
   typical range 0–25, not 0–100) — so the popup presents them RELATIVELY (chip order), never as
   0–100 bars. Fully null-guarded: absent file → MACX stays null and the chip strip is omitted. */
let MACX=null, macxMeta=null, macxVec=null, macxLoaded=false, macxDone=false, macxPromise=null;
async function loadMacroExposure(){
  if(macxPromise) return macxPromise;
  macxLoaded=true;
  macxPromise=(async()=>{
    try{ const r=await fetch('data/macro_exposure.json'); if(!r.ok){MACX=null;macxDone=true;return MACX;}
      const j=await r.json(); macxMeta=j.meta||null; MACX=j.branches||null;
      // compact per-branch [dominant factor idx, score] vector — feeds the 'macx' map lens.
      macxVec=Array.isArray(j.vector)?j.vector:null; _macxTally=null; }
    catch(e){ MACX=null; macxMeta=null; macxVec=null; }
    // macxDone = the fetch SETTLED (vs macxLoaded = the fetch was merely kicked off — this loader
    // is warmed for popups on every map open, so lensAbsent must not read the in-flight gap as absent).
    macxDone=true;
    return MACX;
  })();
  return macxPromise;
}
// true once the layer is loaded AND carries branch reads (drives lensAbsent for the macx lens).
function macxHasData(){return !!(MACX&&MACX.length&&macxVec&&macxVec.length);}
// 'Macro headwind' lens val() — the branch's dominant-factor share-diluted score (ESTIMATED,
// relative ~0–25 range) but ONLY when that dominant exposure is a HEADWIND (t3[0][2]!=='t').
// Tailwind-dominant branches read 0: the lens flags customers a macro move is hurting, not helping.
function macxHeadwindVal(d){
  if(!macxHasData()||!DATA) return 0;
  const i=idxOf(d); if(i<0) return 0;
  const v=macxVec[i]; if(!v||v[0]==null||v[0]<0) return 0;
  const e=MACX[i]; if(!e||!e.t3||!e.t3.length||e.t3[0][2]==='t') return 0;
  return v[1]||0;
}
// dominant-factor tally over the whole network, computed once from the vector (~2,015 rows, cheap).
// Returns {head:{key:n} headwind-dominant counts, all:{key:n} any-direction counts, top:{key,label,n}
// the headwind factor hitting the most branches' customers} — null until the layer loads.
let _macxTally=null;
function macxDomTally(){
  if(_macxTally!==null) return _macxTally;
  if(!macxHasData()) return null;
  const keys=(macxMeta&&macxMeta.factor_keys)||[];
  const head={}, all={};
  macxVec.forEach((v,i)=>{
    if(!v||v[0]==null||v[0]<0) return;
    const k=keys[v[0]]; if(!k) return;
    all[k]=(all[k]||0)+1;
    const e=MACX[i];
    if(e&&e.t3&&e.t3.length&&e.t3[0][2]!=='t') head[k]=(head[k]||0)+1;
  });
  let top=null;
  Object.keys(head).forEach(k=>{ if(!top||head[k]>top.n){ const f=macxFactor(k); top={key:k,label:(f&&f.label)||k,n:head[k]}; } });
  _macxTally={head,all,top};
  return _macxTally;
}
// per-branch macro-exposure record (for popups) — null when the file/entry is absent.
function macxRec(d){
  if(!MACX||!MACX.length||!DATA) return null;
  const i=idxOf(d); if(i<0) return null;
  return MACX[i]||null;
}
// the factor definition (label/signal/direction) for a factor key — null when meta is absent.
function macxFactor(k){
  const fs=(macxMeta&&macxMeta.factors)||[];
  for(const f of fs) if(f&&f.key===k) return f;
  return null;
}

/* ---------- MACRO SENSITIVITY — what moves this branch (data/macro_sensitivity.json, obj#1) ----------
   Lazy-loads the per-branch top-2 macro drivers built by pipeline/build_macro_sensitivity.py:
   {meta:{drivers:{key:{label,yoy_pct,dir,…}},…}, branches:[[[key,score,dir,ctx]…]…], provinces:[…]}
   INDEX-ALIGNED to branches.json. ESTIMATED PROXY over measured inputs: real Pink Sheet price YoY
   (GLOBAL direction proxy) × measured OAE crop shares / rainfall / OSM gold shops, scaled by the
   ESTIMATED branch segment scores (a/c). Feeds the one-line "What moves this branch" popup read and
   the Overview province macro watchlist. Fully null-guarded: absent file → both surfaces are omitted. */
let MSENS=null, msensMeta=null, msensProv=null, msensLoaded=false, msensPromise=null;
function loadMacroSens(){
  if(msensPromise) return msensPromise;
  msensLoaded=true;
  msensPromise=fetch('data/macro_sensitivity.json').then(r=>r.ok?r.json():null)
    .then(j=>{ if(j){msensMeta=j.meta||null;MSENS=j.branches||null;msensProv=j.provinces||null;} return MSENS; })
    .catch(()=>{ MSENS=null; msensMeta=null; msensProv=null; return null; });
  return msensPromise;
}
// per-branch top-2 driver record — null when the file/entry is absent (no fabrication).
function msensRec(d){
  if(!MSENS||!MSENS.length||!DATA) return null;
  const i=idxOf(d); if(i<0) return null;
  const t2=MSENS[i];
  return (Array.isArray(t2)&&t2.length)?t2:null;
}
// ctx phrasing per driver — ctx is the MEASURED branch/province quantity behind the driver
// (meta.drivers[key].ctx_label): crop share %, OSM gold-shop count, or rain % of normal.
const MSENS_CTX={
  rice:c=>c+'% of province crop area', rubber:c=>c+'% of province crop area',
  palm:c=>c+'% of province crop area',
  gold:c=>c+' gold shop'+(c===1?'':'s')+' ≤10km',
  drought:c=>'rain '+c+'% of normal',
};
// one driver → a compact phrase: "Rubber price ▲ +32.4% YoY × 13% of province crop area".
// Headwind red / tailwind green (theme-safe CSS vars). Returns '' on malformed entries.
function msensPhrase(t){
  if(!Array.isArray(t)||t.length<4) return '';
  const k=t[0], dir=t[2], ctx=t[3];
  const drv=(msensMeta&&msensMeta.drivers&&msensMeta.drivers[k])||{};
  const col=dir==='h'?'var(--agri)':'var(--merch)';
  const arrow=(typeof drv.yoy_pct==='number')?(drv.yoy_pct>0?'▲':'▼'):'▼';
  const yoy=(typeof drv.yoy_pct==='number')?((drv.yoy_pct>0?'+':'')+drv.yoy_pct+'% YoY'):'';
  const ctxs=(ctx!=null&&MSENS_CTX[k])?MSENS_CTX[k](ctx):'';
  const join=k==='drought'?' — ':' × ';   // "Drought ▼ — rain 88% of normal" reads better than "×"
  return `<b style="color:${col}">${drv.label||k} ${arrow}${yoy?' '+yoy:''}</b>${ctxs?join+ctxs:''}`;
}

/* ---------- MEASURED lead-site coordinates (data/lead_sites.json, obj#2) ----------
   Lazy-loads the per-branch nearest lead SITES behind the who-to-acquire board (built by
   pipeline/build_lead_sites.py): {meta:{categories:[{k,label,…}]}, branches:[[cat_idx,lng,lat,dist_km]…]},
   INDEX-ALIGNED to branches.json, ≤12 sites/branch. Every point is a MEASURED OSM coordinate —
   drawn as tiny category-coloured pins around a branch WHILE its popup is open (selectBranch),
   cleared on popupclose / next selection. Fully null-guarded: absent file → LSITES stays null
   and no pins draw. Nothing is fabricated. */
let LSITES=null, lsitesMeta=null, lsitesLoaded=false, lsitesPromise=null;
async function loadLeadSites(){
  if(lsitesPromise) return lsitesPromise;
  lsitesLoaded=true;
  lsitesPromise=(async()=>{
    try{ const r=await fetch('data/lead_sites.json'); if(!r.ok){LSITES=null;return LSITES;}
      const j=await r.json(); lsitesMeta=j.meta||null; LSITES=j.branches||null; }
    catch(e){ LSITES=null; lsitesMeta=null; }
    return LSITES;
  })();
  return lsitesPromise;
}
// segment-palette colour per lead-site category key (gold/collateral/merchant/neutral families).
const LEADSITE_COL={gold:'#E6B450',industrial:'#E6B450',vehicle:'#7A4FE0',
  fresh_mkt:'#1C8C7D',supermarket:'#1C8C7D',convenience:'#1C8C7D',restaurant:'#1C8C7D',
  hotel:'#8b90a7',school:'#8b90a7'};

/* ---------- per-PROVINCE composite-risk rollup (data/province_risk.json, obj#1) ----------
   Lazy-loads the worst-first province rollup built by pipeline/build_province_risk.py:
   {meta, provinces:[{province, region, n_branches, mean_risk, p90_risk, top_driver_mix:{driver:count}}]}.
   n_branches is MEASURED; mean_risk / p90_risk are aggregates of the ESTIMATED branch composite.
   Fully null-guarded: absent file → PRISK_LIST stays empty and the Exposure panel + Home verdict omit
   gracefully. Nothing is fabricated. */
let PRISK_LIST=[], PRISK_META=null, priskLoaded=false, priskPromise=null;
async function loadProvinceRisk(){
  if(priskPromise) return priskPromise;
  priskLoaded=true;
  priskPromise=(async()=>{
    try{ const r=await fetch('data/province_risk.json'); if(!r.ok){PRISK_LIST=[];return PRISK_LIST;}
      const j=await r.json(); PRISK_META=j.meta||null;
      PRISK_LIST=Array.isArray(j.provinces)?j.provinces.slice().sort((a,b)=>(b.mean_risk||0)-(a.mean_risk||0)):[]; }
    catch(e){ PRISK_LIST=[]; PRISK_META=null; }
    return PRISK_LIST;
  })();
  return priskPromise;
}
function priskHasData(){return !!(PRISK_LIST&&PRISK_LIST.length);}
// dominant top_driver for a province-risk record (from top_driver_mix counts).
function priskDom(p){
  const m=p&&p.top_driver_mix; if(!m) return null;
  let k=null,best=-1; for(const d in m){ if((m[d]||0)>best){best=m[d];k=d;} }
  return k;
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
    // Prefer the MERGED full census (official store-locators for Muangthai/Srisawad/Tidlor +
    // Google/Overture sample for Heng — ~16,393 MEASURED rivals, already deduped). Fall back to the
    // raw Google∪Overture samples only if the census isn't built.
    const cen=await grab('data/competitors_census.json');
    let items, srcs;
    if(cen&&Array.isArray(cen.items)&&cen.items.length){
      items=cen.items.filter(it=>it&&it.lat!=null&&it.lng!=null);
      srcs=['official store-locators + sample']; COMP=cen;
    }else{
      const [g,o]=await Promise.all([grab('data/competitors_national.json'),grab('data/competitors_overture.json')]);
      srcs=[]; if(g)srcs.push('Google Places'); if(o)srcs.push('Overture');
      items=[].concat(g&&g.items||[], o&&o.items||[]).filter(it=>it&&it.lat!=null&&it.lng!=null);
      COMP=g||o;
    }
    if(!items.length){ COMP=null; COMP_META=null; COMP_ITEMS=[]; }
    else{
      COMP_ITEMS=cen?items:dedupComp(items);   // census is pre-deduped; only the raw samples need dedupComp
      COMP_META={sources:srcs, raw:items.length, deduped:COMP_ITEMS.length};
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
  const c=d._comp; if(!c||!c.ok) return 'Competitor census not loaded yet';
  if(!c.n) return `No rival branches ≤${COMP_RADIUS_KM}km (measured, lower bound)`;
  const parts=Object.entries(c.brands).sort((a,b)=>b[1]-a[1]).map(([b,n])=>`${b} ${n}`);
  return `${c.n} rival branch${c.n===1?'':'es'} ≤${COMP_RADIUS_KM}km: ${parts.join(', ')} (measured, lower bound)`;
}

/* ---------- catchment block (per-branch popup, all three numbers MEASURED) ----------
   Two extra MEASURED layers behind each branch popup's "Catchment ≤10km" block, both lazy-loaded
   with the same cached-promise pattern used across this file and both fully null-guarded (absent
   file → the line, or the whole block, is simply omitted — nothing is fabricated):
   (a) data/branch_population.json .values[i] — the TRUE ~10km-perimeter WorldPop 2020 population
       INSIDE this branch's 10km circle (MEASURED, index-aligned to branches.json).
   (b) data/competitors_census.json .items — the MERGED measured rival-branch census (Google Places
       UNION Overture, ~4,384 points); we count how many sit within CATCH_RADIUS_KM of this branch
       (client-side haversine, reusing havKm). This is the merged census (a fuller count than the
       5km per-brand COMP_ITEMS tally), so it gets its own 10km read to match the ≤10km framing.
   The third number — total establishments ≤10km — is just the sum of this branch's own k10 OSM
   counts already in branches.json, so it needs no extra fetch. */
const CATCH_RADIUS_KM=10;                                   // radius (km) for the catchment population / establishments / rival read
let BPOP=null, bpopLoaded=false, bpopPromise=null;          // MEASURED ~10km WorldPop population per branch (index-aligned .values)
async function loadBranchPopulation(){
  if(bpopPromise) return bpopPromise;
  bpopLoaded=true;
  bpopPromise=(async()=>{
    try{ const r=await fetch('data/branch_population.json'); if(r.ok){ const j=await r.json(); BPOP=Array.isArray(j&&j.values)?j.values:null; } }
    catch(e){ BPOP=null; }
    return BPOP;
  })();
  return bpopPromise;
}
// CONTESTED POPULATION (contested_pop.json, index-aligned; pipeline/build_contested_pop.py):
// MEASURED WorldPop-2020 × rival-census overlay — rows[i]=[pop10, contested_pop]: the population
// inside branch i's 10km circle and the subset of it living within 2km of ANY census rival.
// Share = rows[i][1]/rows[i][0] (census lower bound). Same cached-promise pattern.
let CPOP=null, cpopLoaded=false, cpopPromise=null;
async function loadContestedPop(){
  if(cpopPromise) return cpopPromise;
  cpopLoaded=true;
  cpopPromise=(async()=>{
    try{ const r=await fetch('data/contested_pop.json'); if(r.ok){ const j=await r.json();
      CPOP=(j&&Array.isArray(j.rows))?j:null; } }
    catch(e){ CPOP=null; }
    return CPOP;
  })();
  return cpopPromise;
}
let CCEN=null, ccenItems=[], ccenLoaded=false, ccenPromise=null;   // MEASURED merged rival-branch census (.items with lat/lng)
async function loadCompetitorCensus(){
  if(ccenPromise) return ccenPromise;
  ccenLoaded=true;
  ccenPromise=(async()=>{
    try{ const r=await fetch('data/competitors_census.json'); if(r.ok){ const j=await r.json();
      ccenItems=((j&&j.items)||[]).filter(it=>it&&it.lat!=null&&it.lng!=null); CCEN=ccenItems.length?j:null; } }
    catch(e){ CCEN=null; ccenItems=[]; }
    return ccenItems;
  })();
  return ccenPromise;
}
let CBRF=null, cbrfLoaded=false, cbrfPromise=null;   // per-branch macro cluster brief (.briefs, index-aligned)
async function loadClusterBrief(){
  if(cbrfPromise) return cbrfPromise;
  cbrfLoaded=true;
  cbrfPromise=(async()=>{
    try{ const r=await fetch('data/cluster_brief.json'); if(r.ok){ const j=await r.json(); CBRF=Array.isArray(j&&j.briefs)?j.briefs:null; } }
    catch(e){ CBRF=null; }
    return CBRF;
  })();
  return cbrfPromise;
}
// NAMED occupation leads per branch (occupation_leads.json .branches[i].L, index-aligned; buckets in meta).
let OCCL=null, OCCLB=null, occlLoaded=false, occlPromise=null;
async function loadOccLeads(){
  if(occlPromise) return occlPromise;
  occlLoaded=true;
  occlPromise=(async()=>{
    try{ const r=await fetch('data/occupation_leads.json'); if(r.ok){ const j=await r.json();
      OCCL=Array.isArray(j&&j.branches)?j.branches:null; OCCLB=(j&&j.meta&&j.meta.buckets)||null; } }
    catch(e){ OCCL=null; OCCLB=null; }
    return OCCL;
  })();
  return occlPromise;
}
// PER-BRANCH RIVAL PRESSURE (rival_pressure.json, index-aligned; pipeline/build_rival_pressure.py):
// MEASURED nearest-rival km per brand (.branches[i].d aligned to .brands), rivals within 2/5 km
// (n2/n5) and the stated siege flag (s:1 when >=3 rivals within 2 km). Same cached-promise pattern.
let RIVP=null, rivpLoaded=false, rivpPromise=null;
async function loadRivalPressure(){
  if(rivpPromise) return rivpPromise;
  rivpLoaded=true;
  rivpPromise=(async()=>{
    try{ const r=await fetch('data/rival_pressure.json'); if(r.ok){ const j=await r.json();
      RIVP=(j&&Array.isArray(j.branches)&&Array.isArray(j.brands))?j:null; } }
    catch(e){ RIVP=null; }
    return RIVP;
  })();
  return rivpPromise;
}
function rivpRec(d){
  if(!RIVP) return null;
  const i=idxOf(d); return (i>=0&&i<RIVP.branches.length)?RIVP.branches[i]:null;
}
/* ---------- per-branch LICENSED-PICO rival count in the branch's district (data/branch_pico.json) ----
   Lazy-loads build_branch_pico.py's output: {meta, branches:[{pico,head,branch,recent}]}, INDEX-ALIGNED
   to branches.json. Each record is the MEASURED count of licensed PICO-finance (พิโกไฟแนนซ์) operators
   registered in THIS branch's own district (อำเภอ), joined via amphoe.json's point-in-polygon branch
   assignment to the FPO registry (pico_district.json). This is the small-ticket rival class the big-4
   census (rival_pressure/compPopup) is blind to. Null-guarded: absent file → PICOBR stays null and the
   popup line is omitted. Nothing fabricated. */
let PICOBR=null, picobrLoaded=false, picobrPromise=null;
async function loadBranchPico(){
  if(picobrPromise) return picobrPromise;
  picobrLoaded=true;
  picobrPromise=(async()=>{
    try{ const r=await fetch('data/branch_pico.json'); if(r.ok){ const j=await r.json();
      PICOBR=(j&&Array.isArray(j.branches))?j.branches:null; } }
    catch(e){ PICOBR=null; }
    return PICOBR;
  })();
  return picobrPromise;
}
function picoBrRec(d){
  if(!PICOBR) return null;
  const i=idxOf(d); return (i>=0&&i<PICOBR.length)?PICOBR[i]:null;
}
// MEASURED rival branches within CATCH_RADIUS_KM of a branch (client-side haversine over the merged
// census). Computed only for the one open popup (≤4,384 haversines), so no precompute needed. Returns
// null when the census is absent so the popup omits the line rather than show a fabricated 0.
function catchRivalCount(d){
  if(!ccenItems.length) return null;
  let n=0;
  for(let j=0;j<ccenItems.length;j++){ const it=ccenItems[j];
    if(havKm(d.y,d.x,it.lat,it.lng)<=CATCH_RADIUS_KM) n++; }
  return n;
}
// risk sub-metric: composite (max of the three proxies) or a single selectable score.
let riskMetric='composite';
// carry the current light/dark theme over to the standalone 3D/map pages
function themeQS(){try{return '&theme='+(document.documentElement.dataset.theme==='light'?'light':'dark');}catch(e){return '';}}
function riskVal(d){
  const a=d.a==null?0:d.a, m=d.m==null?0:d.m, c=d.c==null?0:d.c;
  return riskMetric==='a'?a : riskMetric==='m'?m : riskMetric==='c'?c : Math.max(a,m,c);
}

let DATA=null, META=null, map=null, markers=[], curLens='dws', branchSort='dwork', mapReady=false;
let radiusCircle=null, showRadius=true;

const $ = s => document.querySelector(s);
const el = (t,c,h) => { const e=document.createElement(t); if(c)e.className=c; if(h!=null)e.innerHTML=h; return e; };
function barHTML(v,color,max=100){return `<span class="bar"><i style="width:${Math.round(62*Math.min(v,max)/max)}px;background:${color}"></i></span>`;}

/* ============================================================================
   CHART KIT — hand-rolled inline SVG, no library, no CDN.
   Why not Chart.js/D3: this is a no-build static deploy served straight off
   Vercel and off `python -m http.server` locally. A CDN <script> is a new
   external dependency on both, and the offline/local-server workflow is how
   this app is actually developed. Bars + sparklines are the two shapes that
   carry the load; both are ~40 lines of path generation.

   All three renderers are null-safe (bad/absent input → '') and colour
   themselves from the CSS custom properties, so light/dark come free.
   Interaction is a native <title> tooltip — no JS, works on keyboard, and
   costs nothing. Nothing here animates.
   RULE: never chart an ESTIMATE. A line makes a number look more
   authoritative than a table does, so composites/scores stay as text.
   ============================================================================ */
function svgEsc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}

/* Diverging horizontal bars around a zero axis — the right shape for YoY moves, because the
   direction of a set of numbers has to be visible at a glance rather than read row by row.
   rows: [{label, value, color?, note?}]. Returns '' if no finite value.

   CURRENTLY UNUSED — the commodities board was its only caller and now draws per-row cbBar() cells
   instead. HAZARD if you reuse it: it emits a viewBox with no intrinsic size, so `.chartwrap>svg
   {width:100%}` scales it UNIFORMLY to the container — on a 1920px screen it rendered 1590x627 from
   a 560x221 viewBox with 10.5px labels drawn at ~30px. `.chartwrap>svg` now carries a max-width to
   cap that, but if you mount this outside .chartwrap, constrain it yourself. */
function svgBars(rows,opt){
  opt=opt||{};
  const R=(rows||[]).filter(r=>r&&typeof r.value==='number'&&isFinite(r.value));
  if(!R.length) return '';
  const unit=opt.unit==null?'%':opt.unit;
  const rowH=opt.rowH||19, padT=6, labW=opt.labW||92, numW=opt.numW||46;
  const H=padT*2+R.length*rowH, W=560;                 // viewBox units; scales to container
  const plotL=labW, plotR=W-numW, plotW=plotR-plotL;
  const mx=Math.max(...R.map(r=>Math.abs(r.value)))||1;
  const zero=opt.signed===false?plotL:plotL+plotW/2;
  const scale=opt.signed===false?plotW/mx:(plotW/2)/mx;
  const parts=[`<svg class="cbars" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${svgEsc(opt.aria||'Bar chart')}">`];
  parts.push(`<line class="cbars-ax" x1="${zero.toFixed(1)}" y1="${padT-2}" x2="${zero.toFixed(1)}" y2="${H-padT+2}"/>`);
  R.forEach((r,i)=>{
    const y=padT+i*rowH, w=Math.abs(r.value)*scale;
    const x=r.value<0?zero-w:zero;
    const col=r.color||(r.value>0?'var(--up)':r.value<0?'var(--agri)':'var(--dim)');
    const txt=(r.value>0?'+':'')+r.value+unit;
    parts.push(`<g><title>${svgEsc(r.label)}: ${svgEsc(txt)}${r.note?' — '+svgEsc(r.note):''}</title>`
      +`<text class="cbars-l" x="${labW-8}" y="${y+rowH/2}">${svgEsc(r.label)}</text>`
      +`<rect class="cbars-b" x="${x.toFixed(1)}" y="${y+3}" width="${Math.max(w,0.8).toFixed(1)}" height="${rowH-8}" fill="${col}" rx="1.5"/>`
      +`<text class="cbars-v" x="${W-6}" y="${y+rowH/2}" fill="${col}">${svgEsc(txt)}</text></g>`);
  });
  parts.push('</svg>');
  return parts.join('');
}

/* Fixed-size diverging bar for ONE table cell, scaled against the column's own max.

   Sized in PIXELS on purpose. The full-width commodities chart this replaced used a
   viewBox + width:100% + preserveAspectRatio="meet", which scales UNIFORMLY to the container: on a
   1920px screen it rendered 1590x627 from a 560x221 viewBox — a 2.84x blow-up, with 10.5px label
   text drawn at ~30px, in a block 673px tall summarising a 409px table underneath it. A cell bar
   must never be able to do that, so width/height are attributes and the viewBox matches them 1:1. */
function cbBar(v, max, w) {
  if (typeof v !== 'number' || !isFinite(v)) return '<span class="s">n/a</span>';
  w = w || 104;
  const h = 13, mid = w / 2, m = Math.abs(max) || 1;
  const len = Math.max(Math.abs(v) / m * (w / 2), 1);
  const x = v < 0 ? mid - len : mid;
  const col = v > 0 ? 'var(--merch)' : v < 0 ? 'var(--agri)' : 'var(--dim)';
  return `<svg class="cbcell" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true">`
    + `<line x1="${mid}" y1="0" x2="${mid}" y2="${h}" stroke="var(--line)" stroke-width="1"/>`
    + `<rect x="${x.toFixed(1)}" y="3" width="${len.toFixed(1)}" height="${h - 6}" fill="${col}" rx="1.5"/></svg>`;
}

/* Sparkline over a numeric series. Deliberately returns '' for fewer than 4
   points — a 2-point "trend" is a straight line that says something the data
   does not support. Callers render the honest no-history marker instead. */
function svgSpark(vals,opt){
  opt=opt||{};
  const V=(vals||[]).filter(v=>typeof v==='number'&&isFinite(v));
  if(V.length<4) return '';
  const W=opt.w||120, H=opt.h||26, p=2;
  const lo=Math.min(...V), hi=Math.max(...V), span=(hi-lo)||1;
  const x=i=>p+(W-2*p)*i/(V.length-1);
  const y=v=>H-p-(H-2*p)*(v-lo)/span;
  const d=V.map((v,i)=>(i?'L':'M')+x(i).toFixed(1)+','+y(v).toFixed(1)).join(' ');
  const col=opt.color||(V[V.length-1]>=V[0]?'var(--up)':'var(--agri)');
  const area=opt.area===false?'':`<path class="csp-a" d="${d} L${x(V.length-1).toFixed(1)},${H} L${x(0).toFixed(1)},${H} Z" fill="${col}"/>`;
  return `<svg class="csp" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${svgEsc(opt.aria||'trend')}">`
    +`<title>${svgEsc(opt.title||'')}</title>${area}`
    +`<path class="csp-l" d="${d}" stroke="${col}"/>`
    +`<circle class="csp-p" cx="${x(V.length-1).toFixed(1)}" cy="${y(V[V.length-1]).toFixed(1)}" r="1.9" fill="${col}"/></svg>`;
}

/* The honest counterpart to svgSpark: a hairline that says WHY there is no
   line, rather than drawing one that isn't there. */
function noHist(why){return `<span class="csp-none" title="${svgEsc(why||'')}">— ${svgEsc(why||'history not retained')}</span>`;}

/* Dot plot against a reference line (rainfall vs normal, price vs 12-mo mean).
   rows: [{label, value, ref?}] where ref defaults to 100. */
function svgDots(rows,opt){
  opt=opt||{};
  const R=(rows||[]).filter(r=>r&&typeof r.value==='number'&&isFinite(r.value));
  if(!R.length) return '';
  const ref=opt.ref==null?100:opt.ref, unit=opt.unit==null?'%':opt.unit;
  const rowH=17, padT=6, labW=opt.labW||96, W=560, H=padT*2+R.length*rowH;
  const all=R.map(r=>r.value).concat([ref]);
  const lo=Math.min(...all), hi=Math.max(...all), span=(hi-lo)||1;
  const plotL=labW, plotR=W-42, x=v=>plotL+(plotR-plotL)*(v-lo)/span;
  const parts=[`<svg class="cbars" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${svgEsc(opt.aria||'Dot plot')}">`];
  parts.push(`<line class="cbars-ax" x1="${x(ref).toFixed(1)}" y1="${padT-2}" x2="${x(ref).toFixed(1)}" y2="${H-padT+2}"/>`);
  R.forEach((r,i)=>{
    const y=padT+i*rowH+rowH/2, col=r.color||(r.value<ref?'var(--agri)':'var(--up)');
    parts.push(`<g><title>${svgEsc(r.label)}: ${svgEsc(r.value+unit)} (normal ${ref}${unit})</title>`
      +`<text class="cbars-l" x="${labW-8}" y="${y}">${svgEsc(r.label)}</text>`
      +`<line class="cdot-s" x1="${x(ref).toFixed(1)}" y1="${y}" x2="${x(r.value).toFixed(1)}" y2="${y}" stroke="${col}"/>`
      +`<circle class="cdot" cx="${x(r.value).toFixed(1)}" cy="${y}" r="3.1" fill="${col}"/>`
      +`<text class="cbars-v" x="${W-6}" y="${y}" fill="${col}">${svgEsc(r.value+unit)}</text></g>`);
  });
  parts.push('</svg>');
  return parts.join('');
}
// honest n/a renderer for null measured fields (Batch 1 nulled some workforce releases)
function naNum(v){return v==null?'<span class="sub" title="Not in the NSO release we have">n/a</span>':v.toLocaleString();}
// honest renderer for NSO province fields NOT published for a province (e.g. กรุงเทพมหานคร/Bangkok has
// no key in the NSO informal/formal table → 170 branches). Show 'not published (NSO)', never blank.
// See branch_labor.json meta.gaps + docs/TONIGHT_CHECKLIST.md (a Thai-IP repull may list it as กทม.).
function nsoNum(v){return v==null?'<span class="sub" title="Not published by NSO for this province (see branch_labor meta.gaps)">not published (NSO)</span>':v.toLocaleString();}

/* ---------- skeleton placeholders ----------
   Shimmer-skeleton markup that mirrors the final layout while data loads, fading to real content
   when it arrives (CSS @keyframes shimmer, theme-aware). Replaces the old plain "Loading…" text.
   skelRows(n) → a list/table-shaped block (label line + value pill per row).
   skelLines(specs) → free-form stacked shimmer lines (each spec is a width class like 'skel-w70'). */
function skelRows(n){
  n=n||4;
  let rows='';
  const w=['skel-w70','skel-w55','skel-w40','skel-w55','skel-w30'];
  for(let i=0;i<n;i++){
    rows+=`<div class="skel-row"><span class="skel skel-line ${w[i%w.length]} skel-grow"></span>`+
      `<span class="skel skel-pill"></span></div>`;
  }
  return `<div class="skel-rows" aria-hidden="true">${rows}</div>`;
}
function skelLines(specs){
  specs=specs||['skel-w70','skel-w55','skel-w40'];
  return `<div class="skel-rows" aria-hidden="true">`+
    specs.map(w=>`<span class="skel skel-line ${w}"></span>`).join('')+`</div>`;
}

// The name for a scrollable-table region: the table's own section heading, so a screen-reader
// user navigating by region can tell the ~40 tables apart instead of hearing one generic name N
// times (axe landmark-unique). Walks back/up to the nearest preceding heading; the last heading in
// a preceding sibling block is the closest one to the table. Returns '' when none is found.
function tableSectionLabel(t){
  let n=t;
  for(let depth=0; n && n!==document.body && depth<6; depth++){
    let p=n.previousElementSibling;
    while(p){
      if(/^H[1-6]$/.test(p.tagName)) return p.textContent.replace(/\s+/g,' ').trim().slice(0,80);
      if(p.querySelectorAll){
        const hs=p.querySelectorAll('h1,h2,h3,h4,h5,h6');
        if(hs.length) return hs[hs.length-1].textContent.replace(/\s+/g,' ').trim().slice(0,80);
      }
      p=p.previousElementSibling;
    }
    n=n.parentElement;
  }
  return '';
}

// MOBILE: wrap every wide data table in a horizontal-scroll container so a many-column .tbl
// can never push the whole page sideways on a phone. The <table> nodes persist (only their
// innerHTML is replaced on re-render), so wrapping each once at boot is enough and stays
// deterministic. Idempotent — skips tables already inside a .tblwrap.
/* ---------- long-table fold (2026-08-01, owner: "the macro page is still very long") -----------
   Measured cause: 24 tables, 17 of them 9–13 data rows, each ~420–596px of solid numbers. Nobody
   reads row 9 of a province table on screen; they read the top of it and drill when something is
   off. So on screen a long table shows its first FOLD_KEEP rows and folds the rest behind a
   disclosure; the remaining rows stay in the DOM, so nothing is lost and Ctrl-F still finds them.

   Print deliberately opens every <details>, so the printout keeps EVERY row — which is exactly the
   contract the print export promises ("all the supporting data behind").

   Generic and column-agnostic on purpose: it never has to guess which column means what, so it
   cannot mislabel a table. Idempotent — renderers re-run and re-call wrapTables() freely. */
const FOLD_KEEP=5, FOLD_MIN=8;
function foldLongTables(root){
  (root||document).querySelectorAll('table.tbl,table.ic-tbl').forEach(t=>{
    if(t.dataset.folded) return;
    // The geo drill is EXEMPT. Owner directive 2026-08-02 (point 13): "All provinces, roll up into
    // regional summaries, roll up into national summary… the weakness of top ten lists." Folding a
    // 77-province drill back to 10 rows behind a "+67 more rows" button re-creates exactly the
    // pattern the drill exists to replace — and it is redundant, because .gd-wrap already scrolls.
    if(t.classList.contains('gd-tbl')) return;
    const host=t.tBodies&&t.tBodies.length?t.tBodies[0]:t;
    // data rows only — this app builds several tables as bare <tr><th> headers with no <thead>
    const rows=[...host.children].filter(r=>r.tagName==='TR'&&!r.querySelector('th'));
    if(rows.length<FOLD_MIN) return;
    t.dataset.folded='1';
    const hide=rows.slice(FOLD_KEEP);
    hide.forEach(r=>r.classList.add('tr-folded'));
    const cols=Math.max(1,(rows[0].children||[]).length);
    const tr=document.createElement('tr');
    tr.className='tr-foldctl no-print';
    tr.innerHTML=`<td colspan="${cols}"><button type="button" class="foldbtn" aria-expanded="false">`
      +`＋ ${hide.length} more row${hide.length===1?'':'s'}</button></td>`;
    host.appendChild(tr);
  });
}
document.addEventListener('click',e=>{
  const b=e.target.closest&&e.target.closest('.foldbtn'); if(!b) return;
  const tbl=b.closest('table'); if(!tbl) return;
  const open=b.getAttribute('aria-expanded')==='true';
  tbl.querySelectorAll('.tr-folded').forEach(r=>r.classList.toggle('tr-open',!open));
  b.setAttribute('aria-expanded',String(!open));
  const n=tbl.querySelectorAll('.tr-folded').length;
  b.textContent=open?`＋ ${n} more row${n===1?'':'s'}`:'－ show fewer';
});

/* Long method/caveat paragraphs are the Macro tab's second-biggest source of height after the
   tables: 5,283 words, of which the collateral section alone carried 1,577 — more than agri and
   labour combined. They are worth keeping (this product's credibility rests on saying how a number
   was made) but they do not need to be open while you scan. Clamp to two lines with a "more"
   affordance; print always shows them in full, and the provenance appendix repeats them anyway. */
const CLAMP_CHARS=190;
function clampLeads(root){
  (root||document).querySelectorAll('p.lead').forEach(p=>{
    if(p.dataset.clamped||p.closest('.print-only')) return;
    if((p.textContent||'').trim().length<CLAMP_CHARS) return;
    p.dataset.clamped='1'; p.classList.add('lead-clamp');
    const b=document.createElement('button');
    b.type='button'; b.className='clampbtn no-print'; b.textContent='more';
    b.setAttribute('aria-expanded','false');
    p.after(b);
    CLAMP_PRUNE.observe(p);
  });
}
/* Character count is only a cheap pre-filter. On a wide column a 200-char lead often still fits
   inside the two allowed lines, and then the "more" button hangs off text that is already fully
   visible — pure noise. The real test is whether the clamp actually hides anything, which needs
   layout. We cannot measure at clamp time: wrapTables() runs while the view is still display:none
   and most leads sit inside closed <details>, so clientHeight is 0 and every answer would be a
   false "it overflows". So measure LAZILY — the first time each paragraph is actually painted,
   check it and drop the clamp when nothing was hidden. Left alone if the reader already expanded it. */
const CLAMP_PRUNE=new IntersectionObserver(es=>{
  es.forEach(e=>{
    const p=e.target; if(!e.isIntersecting||!p.clientHeight) return;
    CLAMP_PRUNE.unobserve(p);
    const b=p.nextElementSibling;
    if(!b||!b.classList.contains('clampbtn')||b.getAttribute('aria-expanded')==='true') return;
    if(p.scrollHeight<=p.clientHeight+2){ p.classList.remove('lead-clamp'); delete p.dataset.clamped; b.remove(); }
  });
});
document.addEventListener('click',e=>{
  const b=e.target.closest&&e.target.closest('.clampbtn'); if(!b) return;
  const p=b.previousElementSibling; if(!p) return;
  const open=b.getAttribute('aria-expanded')==='true';
  p.classList.toggle('lead-clamp',open);
  b.setAttribute('aria-expanded',String(!open));
  b.textContent=open?'more':'less';
});

function wrapTables(){
  foldLongTables(document);
  clampLeads(document);
  // seed from any already-labelled wrappers (prior calls / static HTML) so cross-call names stay unique.
  const used=Object.create(null);
  document.querySelectorAll('.tblwrap[aria-label]').forEach(w=>{ used[w.getAttribute('aria-label')]=1; });
  document.querySelectorAll('table.tbl').forEach(t=>{
    if(t.parentElement&&t.parentElement.classList.contains('tblwrap')) return;
    const w=document.createElement('div'); w.className='tblwrap';
    // a11y: a horizontally-scrollable region must be keyboard-reachable + labelled so a
    // keyboard / screen-reader user can pan a wide table (WCAG 2.1.1 / scrollable-region-focusable).
    w.setAttribute('role','region');
    w.setAttribute('tabindex','0');
    // Name it from its section heading, and de-dup so every scrollable region is uniquely named
    // (axe landmark-unique) rather than all reading "Scrollable data table".
    let base='Scrollable table: '+(tableSectionLabel(t)||'data table');
    let lbl=base, k=1; while(used[lbl]) lbl=base+' ('+(++k)+')';
    used[lbl]=1;
    w.setAttribute('aria-label',lbl);
    t.parentNode.insertBefore(w,t); w.appendChild(t);
  });
}

/* ---------- tabs ---------- */
// Per-route browser-tab titles: without these all hash routes share one <title>, so history
// entries, bookmarks and open tabs are indistinguishable (and SPA route changes are silent to
// screen readers). Keeps the brand suffix so the tab is still recognisable at a glance.
const TAB_TITLES={home:'Command center',overview:'Macro',map:'Map view',assist:'Assistance',exposure:'Risk',acq:'Competition',trend:'Risk trend',provinces:'Provinces',market:'Market',branches:'Branches',sim:'Simulator'};
function showTab(v){
  if(!v||!document.getElementById('v-'+v)) v='home';
  document.title=(TAB_TITLES[v]?TAB_TITLES[v]+' · ':'')+'AutoX · เงินไชโย';
  // #navMoreMenu is RE-PARENTED to <body> by the nav script (so the dropdown escapes the nav's
  // overflow clipping — see styles.css .nav-more-menu). It is therefore NOT matched by '#nav a',
  // which meant no Explore route ever showed as active and the Explore button never lit up: you
  // clicked Market and the nav gave you no confirmation of where you were. Harmless when Explore
  // held two rarely-used items; not harmless now that five of the eleven routes live there.
  // Scope stays nav + menu on purpose — content "→" links carry data-v too and must NOT highlight.
  document.querySelectorAll('#nav a[data-v],#navMoreMenu a[data-v]').forEach(t=>{const sel=t.dataset.v===v;t.classList.toggle('on',sel);if(sel)t.setAttribute('aria-current','page');else t.removeAttribute('aria-current');});
  document.querySelectorAll('.view').forEach(s=>s.classList.toggle('on', s.id==='v-'+v));
  if(v==='home') renderHome();
  if(v==='assist'){ renderAssist(); renderIncome(); renderAssistOccMacro(); renderAssistOcc(); }
  // showOvPanel() with no argument falls back to the first topic, so entering Macro always lands on
  // exactly one open panel with its chip marked — including on a hard reload, where the static
  // `open` attribute in the markup would otherwise leave the chip row showing nothing selected.
  if(v==='overview'){ renderOverview(); renderCommoditiesBoard(); renderImfWeo(); showOvPanel(OV_PANEL); }
  if(v==='branches') renderBranches();
  if(v==='map') initMap();
  if(v==='provinces') renderProvinces();
  if(v==='market') renderMarket();
  if(v==='exposure'){ renderExposure(); renderProducts(); }
  if(v==='sim'){ renderSim(); renderScenarios(); }
  if(v==='trend') renderTrend();
  if(v==='acq') loadAmphoe();
  renderImpactMounts(v);    // Region→Province→Branch drill on Home + the pillar front doors
  closeBranchSheet();   // the mobile branch sheet belongs to the map — never let it cover another tab
  window.scrollTo(0,0);
}
$('#nav').addEventListener('click', e=>{
  const b=e.target.closest('a[data-v]'); if(!b) return;
  e.preventDefault(); const v=b.dataset.v;
  history.replaceState(null,'','#'+v);
  showTab(v);
});
window.addEventListener('hashchange',()=>showTab((location.hash||'').replace('#','')));
// content "→" links carry data-v but live outside #nav (command-center cards + the "Next in the
// story" tab footers); jump to that tab. Scoped to #main-content so it never double-handles the
// #nav links (those have their own handler) — nav is a sibling of <main>, not inside it.
document.addEventListener('click',e=>{
  const a=e.target.closest('#main-content a[data-v]'); if(!a) return;
  e.preventDefault(); const v=a.dataset.v; history.replaceState(null,'','#'+v); showTab(v);
});
// Keyboard activation for clickable table rows (role="link" tabindex=0): Enter / Space.
document.addEventListener('keydown',e=>{
  if(e.key!=='Enter'&&e.key!==' '&&e.key!=='Spacebar') return;
  const row=e.target.closest&&e.target.closest('tr[role="link"][onclick]');
  if(!row||row!==e.target) return;
  e.preventDefault(); row.click();
});
// In-tab jump-nav: open the target collapsible section and scroll to it. Delegated from document so
// it serves EVERY .jumpnav (Competition's #compjump, Macro's #ovjump, and any added later) — it used
// to be bound to #compjump alone, which meant a second pillar adopting the pattern silently got dead
// chips. One listener, no per-nav wiring.
document.addEventListener('click',e=>{
  const a=e.target.closest&&e.target.closest('.jumpnav [data-jump]'); if(!a) return;
  const sec=document.getElementById(a.dataset.jump); if(!sec) return;
  e.preventDefault();
  const nav=a.closest('.jumpnav');
  if(nav&&nav.dataset.exclusive){ showOvPanel(sec.id,{scroll:'nav'}); return; }
  sec.open=true;
  sec.scrollIntoView({behavior:'smooth',block:'start'});
  const sm=sec.querySelector('summary'); if(sm) sm.focus({preventScroll:true});
});

/* ---------- Macro topic switcher ----------
   The six Macro topics are still <details class="ovsec"> in the DOM. That is deliberate: the print
   engine already expands every <details> in a view, the native element keeps its own keyboard and
   screen-reader behaviour, and deep links keep working — so making them exclusive is a behaviour
   change, not a markup rewrite, and nothing downstream had to learn a new structure.

   What changes is that opening one CLOSES the rest, and the closed panels hide their <summary> so
   the reader sees exactly one heading and one panel instead of six stacked headings. The chip row
   above is the only control; it carries aria-selected so the active topic is announced.
   Printing overrides all of it (CSS restores every summary) — the export must still contain the
   whole tab, which is the promise the per-tab print made. */
// Remembers the chosen topic for the session, so leaving Macro for another pillar and coming back
// does not silently reset the reader to "Conditions & commodities".
let OV_PANEL='sec-ov-macro';
function showOvPanel(id,opt){
  opt=opt||{};
  const wrap=document.getElementById('ovswitch'), nav=document.getElementById('ovjump');
  if(!wrap) return;
  const secs=[...wrap.querySelectorAll('details.ovsec')];
  const target=secs.some(s=>s.id===id)?id:(secs[0]&&secs[0].id);
  OV_PANEL=target;
  secs.forEach(s=>{ s.open=(s.id===target); });
  if(nav) nav.querySelectorAll('[data-jump]').forEach(c=>{
    const on=c.dataset.jump===target;
    c.classList.toggle('on',on);
    c.setAttribute('aria-selected',String(on));
  });
  // Scroll to the CHIP ROW, not the panel: the switcher is the thing the reader is operating, and
  // leaving it off-screen after a switch strands them with no way back to the other five topics.
  if(opt.scroll==='nav'&&nav) nav.scrollIntoView({behavior:'smooth',block:'start'});
  const sm=wrap.querySelector('#'+CSS.escape(target)+' > summary');
  if(sm&&opt.scroll) sm.focus({preventScroll:true});
  // Build the topic's own sub-switcher. Most blocks are filled by async renderers, so build now for
  // the already-resolved ones and rebuild as the rest land — ovSubInit() is a full rebuild, so the
  // repeats are free and the reader's chosen subsection survives them (it is keyed by label).
  ovSubInit(target);
  [500,1500].forEach(ms=>setTimeout(()=>{ if(OV_PANEL===target) ovSubInit(target); },ms));
}
/* A click on a visible summary would normally just toggle that one panel; route it through the
   switcher so the "one open at a time" rule holds however the reader gets there. Closing the only
   open panel is refused — an all-closed Macro tab looks broken. */
document.addEventListener('click',e=>{
  const sm=e.target.closest&&e.target.closest('#ovswitch details.ovsec > summary'); if(!sm) return;
  e.preventDefault();
  showOvPanel(sm.parentElement.id);
});

/* ---------- SECOND level: a sub-switcher INSIDE the long topics (2026-08-02) ----------
   Making the six topics exclusive fixed the tab-level scroll. It did not fix the scroll INSIDE a
   topic, and that is where the length actually is: Collateral is 3,844px across 7 subsections and
   Farm households 3,022px across 4, so choosing "Collateral" still hands the reader seven subjects
   when they wanted one. This applies the same one-at-a-time rule a level down.

   Built from the DOM rather than declared in markup on purpose: every subsection already starts with
   an `h3.ovsub` (directly, or as the first heading of its own wrapper div), so a topic that gains or
   loses a subsection gets the right chips with no second place to update. It rebuilds on every call
   and is therefore idempotent — necessary because most of these blocks are filled asynchronously and
   a block can disappear entirely when its renderer finds no data.

   An "All" chip is always present: nothing this does may put content out of reach. Hiding is
   screen-only (see .ovsub-off in styles.css) so printing still emits the whole tab, which is the
   promise the per-tab print makes. */
const OV_SUB={};        // section id -> the chosen subsection LABEL (survives rebuilds; index doesn't)
const OV_SUB_MIN=3;     // below this a strip is just clutter — two headings read fine stacked
function ovSubBlocks(sec){
  const blocks=[];
  [...sec.children].forEach(c=>{
    if(c.tagName==='SUMMARY'||c.classList.contains('ovsubnav')) return;
    const h=(c.matches&&c.matches('h3.ovsub'))?c:(c.querySelector?c.querySelector('h3.ovsub'):null);
    if(h){
      // Chip label = the heading up to its first "·" separator, with the MEASURED/ESTIMATED tag
      // stripped. The full heading stays as the chip's title so nothing is lost to the shortening.
      const cl=h.cloneNode(true); cl.querySelectorAll('.tag').forEach(t=>t.remove());
      const full=cl.textContent.replace(/\s+/g,' ').trim();
      let label=full.split('·')[0].trim()||full;
      // Shortening must never drop a provenance qualifier. "Collateral recovery-value sensitivity ·
      // illustrative" shortened to "Collateral recovery-value sensitivity" would present a scenario
      // table under the same chip styling as the measured ones — the exact honesty the tab is built
      // on. If the part being cut says what kind of number it is, it stays.
      const qual=full.slice(label.length).match(/illustrativ\w*|estimat\w*|proxy|scenario\w*/i);
      if(qual) label+=' · '+qual[0].toLowerCase();
      blocks.push({label, full, nodes:[]});
    }
    if(!blocks.length) blocks.push({label:'', full:'', nodes:[]});   // preamble before any heading
    blocks[blocks.length-1].nodes.push(c);
  });
  // A block whose renderer hid its own wrapper has nothing to show — no chip for it.
  return blocks.filter(b=>b.label&&b.nodes.some(n=>n.style.display!=='none'));
}
function ovSubApply(sec,blocks,label){
  const all=!label;
  blocks.forEach(b=>b.nodes.forEach(n=>n.classList.toggle('ovsub-off',!all&&b.label!==label)));
  const nav=sec.querySelector(':scope > .ovsubnav');
  if(nav) nav.querySelectorAll('[data-ovsub]').forEach(c=>{
    const on=(c.dataset.ovsub||'')===(label||'');
    c.classList.toggle('on',on); c.setAttribute('aria-selected',String(on));
  });
}
function ovSubInit(secId){
  const sec=document.getElementById(secId); if(!sec) return;
  let nav=sec.querySelector(':scope > .ovsubnav');
  const blocks=ovSubBlocks(sec);
  if(blocks.length<OV_SUB_MIN){
    if(nav) nav.remove();
    // Never leave content hidden by a strip that no longer exists.
    sec.querySelectorAll('.ovsub-off').forEach(n=>n.classList.remove('ovsub-off'));
    return;
  }
  if(!nav){
    nav=document.createElement('nav');
    nav.className='jumpnav ovsubnav no-print';
    nav.setAttribute('aria-label','Choose one part of this topic');
    const sm=sec.querySelector(':scope > summary');
    sec.insertBefore(nav,sm?sm.nextSibling:sec.firstChild);
  }
  // The remembered choice can vanish when a block's data does — fall back to All, never to nothing.
  let sel=OV_SUB[secId]||'';
  if(sel&&!blocks.some(b=>b.label===sel)) sel='';
  OV_SUB[secId]=sel;
  nav.innerHTML=`<button type="button" class="chip" data-ovsub="" aria-selected="${!sel}">All</button>`
    +blocks.map(b=>`<button type="button" class="chip" data-ovsub="${b.label.replace(/"/g,'&quot;')}" title="${b.full.replace(/"/g,'&quot;')}" aria-selected="${sel===b.label}">${b.label}</button>`).join('');
  ovSubApply(sec,blocks,sel);
}
document.addEventListener('click',e=>{
  const c=e.target.closest&&e.target.closest('.ovsubnav [data-ovsub]'); if(!c) return;
  e.preventDefault();
  const sec=c.closest('details.ovsec'); if(!sec) return;
  OV_SUB[sec.id]=c.dataset.ovsub||'';
  ovSubApply(sec,ovSubBlocks(sec),OV_SUB[sec.id]);
  const nav=sec.querySelector(':scope > .ovsubnav');
  if(nav) nav.scrollIntoView({behavior:'smooth',block:'nearest'});
});

/* ---------- load ---------- */
async function boot(){
  try{
    const [b,m] = await Promise.all([
      fetch('data/branches.json').then(r=>r.json()),
      fetch('data/meta.json').then(r=>r.json())
    ]);
    DATA=b; META=m;
    // stamp each branch with its index once so the index-aligned lens accessors (branch-risk,
    // occupation-risk, poi-relevance, occupation-mix) can read d._i in O(1) instead of an
    // O(n) DATA.indexOf on every marker repaint (2,015 markers → O(n²) per lens switch/paint).
    if(Array.isArray(DATA)) DATA.forEach((d,i)=>{ if(d) d._i=i; });
    wrapTables();
    $('#updated').textContent = META.updated || '';
    try{ PROV = await fetch('data/provinces/index.json').then(r=>r.json()); PLOOK=provLookupByName(); }catch(e){}
    renderOverview(); renderCompetition(); renderLenses(); renderBranchSort(); renderBranches();
    showTab((location.hash||'').replace('#',''));
  }catch(err){
    document.querySelector('main').insertAdjacentHTML('afterbegin',
      `<div class="insight" style="border-left-color:var(--agri)">Couldn't load data files. Make sure <b>data/branches.json</b> and <b>data/meta.json</b> sit next to this page. (${err})</div>`);
  }
}

/* ---------- national macro-risk indicators (data/macro_indicators.json, obj#1) ----------
   BIS household debt-to-GDP + policy rate, World Bank CPI/lending/FX — MEASURED, cloud-refreshed.
   Household leverage is the core borrower-PD backdrop. Appended to the Overview macro board.
   Fully null-guarded: absent file → nothing extra renders. */
let MACROIND=null, macroIndDone=false, macroIndPromise=null;
async function loadMacroIndicators(){
  if(macroIndPromise) return macroIndPromise;
  macroIndPromise=fetch('data/macro_indicators.json').then(r=>r.ok?r.json():null)
    .then(d=>{MACROIND=d;macroIndDone=true;return d;}).catch(()=>{macroIndDone=true;return null;});
  return macroIndPromise;
}
function renderMacroIndicators(){
  const host=$('#macro'); if(!host||!MACROIND||!MACROIND.indicators) return;
  const I=MACROIND.indicators, cards=[];
  const arrow=v=>v==null?'':(v<0?'▼':(v>0?'▲':'●'));
  const hh=I.household_debt_gdp;
  if(hh) cards.push([`Household debt`, `${hh.value}%`,
    `of GDP · ${arrow(hh.yoy_change)}${hh.yoy_change!=null?Math.abs(hh.yoy_change)+'pp':''} YoY${hh.yoy_change<0?' (deleveraging)':''} · BIS ${hh.period}`]);
  const pr=I.policy_rate;
  if(pr) cards.push([`Policy rate`, `${pr.value}%`, `${arrow(pr.yoy_change)}${pr.yoy_change!=null?Math.abs(pr.yoy_change)+'pp':''} YoY · BIS ${pr.period}`]);
  const cpi=I.cpi_inflation;
  if(cpi) cards.push([`Inflation`, `${cpi.value}%`, `CPI YoY · World Bank ${cpi.period}`]);
  const fx=I.usd_thb;
  if(fx) cards.push([`USD/THB`, `${fx.value}`, `World Bank ${fx.period}`]);
  if(!cards.length) return;
  // IDEMPOTENT (fixed 2026-08-01 — the board was showing household debt / policy rate / inflation /
  // USD-THB TWICE). renderOverview() resets #macro synchronously but appends these asynchronously,
  // so two renderOverview() calls landing before the fetch settles produce two innerHTML resets
  // followed by two appends — both after the last reset. Clearing this appender's own cards first
  // makes the result independent of how many times it runs.
  host.querySelectorAll('.mcard[data-mc="ind"]').forEach(n=>n.remove());
  // Retire the EDITORIAL card for any indicator we now measure. The board was carrying household
  // debt twice (86.8% "Sep 2025", hand-written and unsourced, beside BIS 2025-Q4 87.5% of GDP with
  // its YoY) and inflation twice (a "~0.3% near-zero" 2026 note beside a measured World Bank CPI).
  // Two numbers for one indicator is worse than one: the reader has to work out which to believe.
  // Only fires when the measured card actually renders, so an absent layer leaves META intact.
  const SUPERSEDED=/^(household debt|inflation)/i;
  host.querySelectorAll('.mcard:not([data-mc])').forEach(n=>{
    const k=n.querySelector('.k'); if(k&&SUPERSEDED.test(k.textContent.trim())) n.remove();
  });
  host.insertAdjacentHTML('beforeend', cards.map(([k,v,n])=>
    `<div class="mcard" data-mc="ind"><div class="k">${k}</div><div class="v">${v}</div><div class="n">${n}</div></div>`).join(''));
}

/* ---------- national labour-market backdrop (data/labour_context.json, obj#1) ----------
   MEASURED — ILOSTAT mirror of Thailand's official NSO LFS. NATIONAL level only (no cloud path to
   per-province LFS). Informal + self-employed workers have no payslip — that IS the title-loan
   borrower base; the agri workforce trend is the agri-PD demand backdrop. Appended to the Overview
   macro board as extra MEASURED national KPIs, same idiom as renderMacroIndicators. Fully
   null-guarded: absent file → nothing extra renders. */
let LABCTX=null, labctxDone=false, labctxPromise=null;
async function loadLabourContext(){
  if(labctxPromise) return labctxPromise;
  labctxPromise=fetch('data/labour_context.json').then(r=>r.ok?r.json():null)
    .then(d=>{LABCTX=d;labctxDone=true;return d;}).catch(()=>{labctxDone=true;return null;});
  return labctxPromise;
}
function renderLabourContext(){
  const host=$('#macro'); if(!host||!LABCTX) return;
  const cards=[];
  const inf=LABCTX.informality;
  if(inf&&inf.rate_pct!=null) cards.push([`Informal work`, `${inf.rate_pct}%`,
    `of employment · no payslip — the title-loan borrower base · NSO LFS ${inf.as_of}`]);
  const se=LABCTX.self_employment;
  if(se&&se.self_employed_pct!=null) cards.push([`Self-employed`, `${se.self_employed_pct}%`,
    `own-account + family + employers · no payslip-issuing employer · NSO LFS ${se.as_of}`]);
  const emp=LABCTX.employment, agri=emp&&Array.isArray(emp.sectors)?emp.sectors.find(s=>/agri/i.test(s.sector||'')):null;
  if(agri&&agri.share_pct!=null){
    const yc=agri.yoy_change_thousands;
    const arrow=yc==null?'':(yc<0?'▼':(yc>0?'▲':'●'));
    const ynote=yc!=null?` · ${arrow}${Math.abs(Math.round(yc)).toLocaleString()}k jobs YoY — the agri-PD demand backdrop`:'';
    cards.push([`Agri jobs`, `${agri.share_pct}%`, `of employment${ynote} · NSO LFS ${agri.as_of||(emp&&emp.as_of)||''}`]);
  }
  if(!cards.length) return;
  // idempotent for the same reason as renderMacroIndicators above (informal work / self-employed /
  // agri jobs were each rendering twice).
  host.querySelectorAll('.mcard[data-mc="lab"]').forEach(n=>n.remove());
  host.insertAdjacentHTML('beforeend', cards.map(([k,v,n])=>
    `<div class="mcard" data-mc="lab"><div class="k">${k}</div><div class="v">${v}</div><div class="n">${n}</div></div>`).join(''));
}

/* ---------- national & regional outlook narrative (data/regional_outlook.json) ----------
   Leads the Overview with the ANSWER: current situation → factors hitting the economy & segments →
   regional impact → recommendation by region → nationwide. A deterministic rollup of the SAME
   per-branch recs shown on the map (not a fresh opinion). Fully null-guarded: absent file → the
   #outlook block renders nothing and the rest of the Overview is unchanged. */
let OUTLOOK=null, outlookDone=false, outlookPromise=null;
async function loadOutlook(){
  if(outlookPromise) return outlookPromise;
  outlookPromise=fetch('data/regional_outlook.json').then(r=>r.ok?r.json():null)
    .then(d=>{OUTLOOK=d;outlookDone=true;return d;}).catch(()=>{outlookDone=true;return null;});
  return outlookPromise;
}
// tone → theme-aware colour (CSS vars flip with light/dark; no hardcoded greys)
const OUT_TONE={good:'var(--merch)',warn:'var(--agri)',up:'var(--merch)',down:'var(--agri)',info:'var(--accent)'};
const REGION_ACCENT={Isan:'var(--agri)',North:'var(--opp)',South:'var(--gold)',East:'var(--accent)','Central&BKK':'var(--accent)'};
// per-province detail panel (revealed on row click) — the metrics that JUSTIFY the recommendation,
// with measured/estimated provenance. Vehicle stock is the collateral evidence AutoX lends against.
function provDetailHTML(p){
  const m=p.metrics||{};
  const M='<span style="color:var(--merch);font-size:8px;text-transform:uppercase;letter-spacing:.3px"> measured</span>';
  const E='<span style="color:var(--dim);font-size:8px;text-transform:uppercase;letter-spacing:.3px"> est</span>';
  const num=v=>v==null?'—':Number(v).toLocaleString();
  const stat=(lab,val,tag)=>`<div style="display:flex;justify-content:space-between;gap:10px;padding:2px 0"><span style="color:var(--mid)">${lab}</span><b style="color:var(--txt);white-space:nowrap">${val}${tag||''}</b></div>`;
  // vehicle-title collateral (the evidence behind "prime collateral density")
  const mix=[m.moto_pct!=null?`${m.moto_pct}% moto`:null, m.pickup_pct!=null?`${m.pickup_pct}% pickup`:null,
             m.car_pct!=null?`${m.car_pct}% car`:null, m.ev_pct!=null?`${m.ev_pct}% EV`:null].filter(Boolean).join(' · ');
  const coll=`<div style="flex:1;min-width:200px">`
    +`<div style="font:700 9px 'IBM Plex Sans Thai';color:var(--collat);text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px">Vehicle-title collateral</div>`
    +stat('Registered vehicles (DLT)', num(m.dlt_vehicles), M)
    +(mix?`<div class="sub" style="padding:2px 0;color:var(--mid)">${mix}${M}</div>`:'')
    +stat('Collateral score', m.coll_score!=null?m.coll_score+'/100':'—', E)
    +stat('Vehicle/moto shops ≤10km', m.veh_shops!=null?'~'+num(m.veh_shops):'—', M)
    +`</div>`;
  // demand / risk
  const risk=`<div style="flex:1;min-width:200px">`
    +`<div style="font:700 9px 'IBM Plex Sans Thai';color:var(--mid);text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px">Demand &amp; risk</div>`
    +stat('Branches', num(p.n), M)
    +stat('Coverage gap', p.opp!=null?p.opp:'—', E)
    +stat('Agri pressure', p.stress!=null?p.stress+'/100':'—', E)
    +stat(m.dom_crop?`${m.dom_crop} price YoY`:'Crop price YoY', m.price_yoy!=null?(m.price_yoy>0?'+':'')+m.price_yoy+'%':'—', M)
    +stat('Rival branches ≤2 / ≤5 km', (m.rivals2!=null?m.rivals2:'—')+' / '+(m.rivals5!=null?m.rivals5:'—'), M)
    +`</div>`;
  // deep-dive links
  const qs=(typeof themeQS==='function')?themeQS():'';
  const links=p.slug?`<div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">`
    +`<a href="rayong-catchment.html?city=${encodeURIComponent(p.slug)}${qs}" style="font:600 11px 'IBM Plex Sans Thai';color:var(--accent);text-decoration:none">🏙 3D scene →</a>`
    +`<a href="province.html?p=${encodeURIComponent(p.slug)}${qs}" style="font:600 11px 'IBM Plex Sans Thai';color:var(--accent);text-decoration:none">▦ district view →</a>`
    +`</div>`:'';
  return `<div style="border-left:2px solid var(--line);padding:6px 0 6px 10px;margin:2px 0 4px">`
    +`<div style="display:flex;gap:18px;flex-wrap:wrap;font:500 11px 'IBM Plex Sans Thai'">${coll}${risk}</div>`
    +links
    +`<div class="sub" style="font-size:9px;color:var(--dim);margin-top:5px">DLT vehicle stock &amp; rival counts are measured; collateral score, coverage gap &amp; agri pressure are estimated screens.</div>`
    +`</div>`;
}
function renderNationalOutlook(){
  const host=$('#outlook'); if(!host||!OUTLOOK||!OUTLOOK.national) return;
  const N=OUTLOOK.national;
  const sec=(t,s)=>`<div style="margin:18px 0 6px;font:700 12px 'IBM Plex Sans Thai';color:var(--mid);text-transform:uppercase;letter-spacing:.6px">${t}${s?` <span style="color:var(--dim);font-weight:500;text-transform:none;letter-spacing:0">— ${s}</span>`:''}</div>`;
  // 1) SITUATION — national macro cards.
  // De-duplicated against the answer band 2026-08-01: the band directly above this block already
  // shows Household debt and Policy rate off the SAME measured BIS series, and with a trend line —
  // so the identical figure was appearing twice within one screen. Whatever the band does not
  // carry (inflation, USD/THB) still shows here. Keys are matched loosely because the two layers
  // are built by different scripts (regional_outlook.json vs macro_indicators.json).
  const IN_ANSWER_BAND=/household\s*debt|policy\s*rate/i;
  const sit=(N.situation||[]).filter(c=>!IN_ANSWER_BAND.test(c.k||'')).map(c=>{
    const col=OUT_TONE[c.tone]||'var(--txt)';
    return `<div class="mcard"><div class="k">${c.k}</div><div class="v" style="color:${col}">${c.v}</div><div class="n">${c.d||''}${c.src?` · ${c.src}`:''}</div></div>`;
  }).join('');
  // 2) FACTORS — commodity/price movers with which segment they hit
  const fac=(N.factors||[]).map(f=>{
    const col=OUT_TONE[f.tone]||'var(--txt)', s=(f.yoy>0?'+':'')+f.yoy+'%';
    return `<div style="display:flex;gap:8px;align-items:baseline;padding:6px 9px;margin:0 0 4px;border-left:3px solid ${col};background:var(--raised);border-radius:0 6px 6px 0">`
      +`<b class="mono" style="color:${col};min-width:54px">${s}</b>`
      +`<span style="flex:1;font:500 12px 'IBM Plex Sans Thai';color:var(--txt)"><b>${f.lab}</b> <span class="sub">(${f.seg}${f.reg?' · '+f.reg:''})</span> — ${f.hits}. <span class="sub">${f.note||''}</span></span></div>`;
  }).join('');
  // ranked action list (shared by national + regional)
  const actions=(list)=>list.map(a=>{
    const col=OUT_TONE[a.tone]||'var(--mid)';
    return `<div style="display:flex;gap:8px;align-items:flex-start;padding:6px 9px;margin:0 0 4px;border-left:3px solid ${col};background:var(--raised);border-radius:0 6px 6px 0">`
      +`<span style="font-size:15px;line-height:1.2">${a.i}</span>`
      +`<span style="flex:1;font:500 12px 'IBM Plex Sans Thai';color:var(--txt);line-height:1.4">${a.t}</span></div>`;
  }).join('');
  // (Removed 2026-07-25, owner ask #5) The per-region "Regional impact & recommendation" cards were
  // too generic AND recommended grow/product-push actions ("grow farm lending", "push vehicle-title")
  // that contradict the consolidation pivot (the product makes no grow/open/expand calls). The macro
  // situation, the factor board, and the commodities board carry the Overview; per-region depth now
  // lives in the risk-drill (Home/Assistance/Exposure/Competition → region → province → branch).
  host.innerHTML=`<h2>National outlook — the answer up top</h2>`
    +`<div class="insight" style="border-left:3px solid var(--accent)"><b>Bottom line:</b> ${N.headline}</div>`
    +sec('Current situation','national macro backdrop')
    +`<div class="grid macro">${sit}</div>`
    +sec('Factors hitting the economy & segments','World Bank price direction + BIS rates — |YoY| ≥ 8%')
    +`<div>${fac}</div>`
    +`<p class="lead" style="margin-top:12px">Region- and province-level depth now lives in the risk-drill (Home / Assistance / Exposure / Competition → region → province → branch), where the loan-book buckets, DTI, crops and rivals are shown together. Deterministic — no model in the loop; inputs are measured/estimated as labelled in their source layers.</p>`;
}

/* ---------- overview ---------- */
function renderOverview(){
  loadOutlook().then(renderNationalOutlook);
  // AutoX lends against vehicle titles, not gold — drop the gold macro KPI card.
  $('#macro').innerHTML = META.macro.filter(([k])=>!/gold/i.test(k||'')).map(([k,v,n])=>
    `<div class="mcard"><div class="k">${k}</div><div class="v">${v}</div><div class="n">${n}</div></div>`).join('');
  loadMacroIndicators().then(renderMacroIndicators);
  // fold the MEASURED national labour backdrop (informality/self-employed/agri jobs) into the macro
  // board — the informal-borrower base behind every segment score (obj#1). Null-safe: absent file → nothing.
  loadLabourContext().then(renderLabourContext);
  renderCommodityBoard();
  // fold the macro-exposure footprint into the board notes once the layer lands ("hits customers
  // at N branches"). Null-safe: absent file → renderCommodityBoard() re-runs with no extra text.
  loadMacroExposure().then(()=>{ if(macxHasData()) renderCommodityBoard(); });
  // The "Segment signals by region" table (#region) and the province macro watchlist were both
  // removed 2026-08-01 — see index.html for the reasoning. META.region is still consumed by the
  // Command-center risk readout, so the DATA stays; only this Macro-tab rendering of it is gone.
  renderMacroSoWhat();
  renderAnswerBand();
  renderCollatOutlook();
  // THE COLLATERAL BOOK (collateral_book.json) — leads the section, because it is the answer the
  // rest of it supports. Absorbs, and replaces, five tables that used to be scattered across three
  // sections: collateral mix (point 12), diesel share (point 10), the brand tiles (point 8), the
  // truck fleet (point 18) and the used-collateral pulse (point 19). Null-safe: absent → hides.
  renderCollateralBook();
  // MEASURED new-pickup inflow trend (brand_trends.json, DLT) — the TIME dimension behind the
  // collateral book: how fast the future used-pickup pool replenishes. Null-safe.
  loadBrandTrends().then(renderBrandTrends);
  loadVehReg().then(renderVehReg);
  renderRecoverySensitivity();
  // MEASURED EV-penetration collateral watch (ev_penetration.json, DLT) — null-safe: absent file → note only
  renderEvWatch();
  // the crop mix → farm income correction (obj #1). Leads this section: it is the number the crop
  // tables underneath it explain. Null-safe: absent layer → nothing renders.
  renderFarmBook();
  // RETIRED 2026-08-02 from this tab — renderCropStress (the agri_stress 0-100 composite, owner:
  // "an estimated measure that has been made up. Difficult to relate.") and renderCropMargin (the
  // 5-crop farmer-margin table). Both are now INSIDE renderFarmBook: the stress table's measured
  // survivors — rainfall % of normal and OAE 2nd-rice area — are province columns on the drill, and
  // the margin table is the by-crop lens, widened to all 8 priced crops and joined to the loan book.
  // CSTRESS itself is untouched and still feeds the map lens, the simulator and the Risk-trend tab.
  // district-grain OAE SPEI drought (obj #1), MODELLED — sharpens the province crop-stress verdict.
  loadDroughtDistrict().then(renderDroughtDistrict);
  // district crop × drought exposure (obj #1) — MEASURED OAE planted area × MODELLED OAE SPEI: names the
  // largest crop-area exposures sitting under drought. Null-safe: absent file → the block stays hidden.
  loadAmphoeCrops().then(renderAmphoeCrops);
  // MEASURED provincial labour stress (province_lfs.json, NSO LFS 2026 Q1, obj #1) — the seasonal-idle
  // backdrop behind the agri-PD book. Null-safe: absent file → the block stays hidden.
  loadProvinceLfs().then(renderProvinceLfs);
  // MEASURED regional household-debt backdrop (region_debt.json, BoT over NSO SES, obj #1) — the borrower-
  // leverage floor under portfolio risk. Null-safe: absent file → the block stays hidden.
  loadRegionDebt().then(renderRegionDebt);
  // MOVED 2026-08-02 into the collateral block (owner points 18 + 19). truck_flow.json is now a
  // per-province column on the collateral drill and collateral_flow.json is the resale-market table
  // at its foot — both read server-side by build_collateral_book.py, so the page fetches neither.
  // MEASURED business-formation pulse (dbd_formation.json, DBD registry) — the small-business borrower
  // base backdrop for the merchant book (both objectives). Null-safe: absent file → the block stays hidden.
  loadDbdForm().then(renderDbdForm);
  // MEASURED state-bank system NPL ratio (sfi_credit.json, FPO / SFI aggregates, obj #1) — the structural
  // household + agri credit-quality tide AutoX's borrowers sit inside. Null-safe: absent file → hidden.
  loadSfi().then(renderSfi);
  // MEASURED live flood + rain pulse (thaiwater_flood/rain.json, ThaiWater telemetry, obj #1) — the acute
  // water-on-the-ground / arriving read behind collections + collateral. Null-safe: either layer absent
  // → the block stays hidden.
  loadThaiwater().then(renderThaiwater);
}
function renderCommodityBoard(){
  if(!META||!META.board) return;
  // The two split tables this function used to write (#board-crops / #board-other) were removed
  // 2026-08-01 as duplicates of the commodities board below — see index.html for the reasoning.
  // What remains, and is NOT duplicated anywhere, is the Key-read callout: it names the thing the
  // board cannot say in a row, that "farmers" are not one segment. Its numbers are injected LIVE
  // from META.board so the sentence can never contradict the board (they were hardcoded once, and
  // went stale at the next vintage refresh).
  // Key-read prose: inject LIVE numbers from the board so it can never contradict the table beside it
  // (was hardcoded chicken +25.6/beef +18.4/gold +62.7, stale after the vintage refresh).
  const kr=$('#ov-keyread');
  if(kr){
    const pick=re=>{const b=META.board.find(x=>re.test(x.lab||'')&&x.yoy!=null);return b?{v:b.yoy,s:(b.yoy>0?'+':'')+b.yoy+'%'}:null;};
    const chick=pick(/chicken|poultry/i), beef=pick(/beef|cattle/i);
    const live=[chick&&('chicken '+chick.s), beef&&('beef '+beef.s)].filter(Boolean).join(', ');
    const anyUp=(chick&&chick.v>0)||(beef&&beef.v>0);
    kr.innerHTML='<b>Key read:</b> "farmers" are not one segment. Crop households (rice, rubber, sugar, palm) '+
      'ride crop-price cycles, while livestock &amp; forestry households move on their own'+
      (live?(' ('+live+', '+(anyUp?'holding up better':'also under pressure')+')'):'')+'. '+
      'These crop/livestock income cycles drive borrower cash flow — and repayment — across the agri book.';
  }
}

/* ---------- ANSWER BAND (top of Macro) ----------------------------------------------------
   The tab used to open into prose and 13 screens of tables with nothing ranked. This is the
   answer first: MEASURED headline numbers only, each with its move, its refresh cadence, and a
   sparkline WHERE ONE HONESTLY EXISTS. Where the source stores a single point (which is most of
   them today) it prints why there is no line rather than drawing a flat one.

   Deliberately excluded: every composite/derived figure. A card at the top of the page is the
   most authoritative position on it, and an estimate does not earn that spot.
   Null-safe throughout: a tile whose source is absent is simply not emitted, and if nothing
   resolves the band hides itself rather than rendering an empty shell. */
function abTile(o){
  const mv=o.move==null?'':`<div class="ab-mv" style="color:${o.moveColor||'var(--mid)'}">${o.move}</div>`;
  const tr=o.spark||(o.why?noHist(o.why):'');
  return `<div class="ab"><div class="ab-k">${o.k}${o.cad?`<span class="ab-cad ${o.cadCls||''}">${o.cad}</span>`:''}</div>`
    +`<div class="ab-v">${o.v}${o.unit?`<small>${o.unit}</small>`:''}</div>${mv}`
    +(tr?`<div class="ab-tr">${tr}</div>`:'')
    +(o.sub?`<div class="ab-s">${o.sub}</div>`:'')+`</div>`;
}
/* ---------- Macro "so what" band (2026-08-02, owner ask) ----------
   The band below this one is six MEASURED numbers. Numbers are not an answer: a reader still has to
   work out which of them matters this week and what to do about it. This band is the sentence
   version — each row is one decision-relevant statement with its consequence, and each row jumps to
   the section that proves it, so the CEO reads the line and the branch team follows the arrow.
   Every row is computed from a committed layer; a row whose layer is absent is simply not emitted,
   so this can never invent a headline. Deliberately capped: if everything is urgent, nothing is. */
function renderMacroSoWhat(){
  const host=$('#ov-sowhat'); if(!host) return;
  Promise.all(['crop_mix','tape_real','brand_trends','thaiwater_flood','debt_source','farm_household','tape_geo_occ']
    .map(n=>tmliFetch(n))).then(([cm,tape,bt,flood,debt,fh,geo])=>{
    const R=[], N=n=>Number(n).toLocaleString();
    const row=(icon,jump,lead,tail)=>R.push({icon,jump,lead,tail});

    // 1. The farm book against the crop mix — in BAHT, not in account counts.
    //    CORRECTED 2026-08-02. This row used to read "17,287 farm accounts sit in 4 provinces whose
    //    crop mix is falling". Wrong: crop_mix.accounts is EVERY book account in the province (it is
    //    the weighting basis for the book-weighted shock), not the farm ones. The farm-specific
    //    exposure lives in the tape's เกษตร occupation cell, and it is an order of magnitude smaller
    //    — 1,826 accounts / ฿213m / 3% of the ฿7.17bn farm book. Worse, the two provinces with the
    //    dramatic crop collapses (สมุทรสงคราม −66%, สมุทรสาคร −62%) hold almost NO farm book at all
    //    (zero and 48 accounts). Counting accounts manufactured an alarm that counting baht dissolves,
    //    so this row now leads with baht and states the share.
    const AGRI='เกษตร';
    const farmOf=th=>{ const cs=(geo&&geo.provinces&&geo.provinces[th])||[];
      return cs.find(c=>c.occupation===AGRI)||null; };
    if(cm&&cm.national&&geo&&geo.provinces){
      let tot=0, negOs=0, negN=0, negCur=0;
      Object.keys(geo.provinces).forEach(th=>{
        const f=farmOf(th); if(!f) return;
        tot+=f.os_sum||0;
        const p=cm.provinces&&cm.provinces[th];
        if(p&&p.shock_pct<0){ negOs+=f.os_sum||0; negN+=f.n||0; negCur+=f.n_current||0; }
      });
      if(tot>0) row('🌾','sec-ov-agri',
        `<b>${(100*(tot-negOs)/tot).toFixed(0)}% of the ฿${(tot/1e9).toFixed(2)}bn farm book</b> sits in provinces whose crop mix is <b>rising</b>; the falling ones hold <b>฿${Math.round(negOs/1e6)}m</b> across ${N(negN)} accounts`,
        `the book-weighted national move is +${cm.national.book_weighted_shock_pct}% — and the two steepest crop falls (${(cm.national.worst||[]).slice(0,2).map(w=>w.prov).join(', ')}) carry almost no farm lending, so the headline crop collapse is not a portfolio event. ${N(negCur)} of the exposed accounts are still Current`);
    }
    // 2. What the titles are worth — accounts vs balance, which the book's own tape settles.
    const vt=tape&&tape.vehicle_types;
    if(vt&&vt.PU&&vt.MC){
      const tn=Object.values(vt).reduce((s,v)=>s+(v.n||0),0),
            to=Object.values(vt).reduce((s,v)=>s+(v.os_sum||0),0);
      const p=k=>({a:100*vt[k].n/tn, o:100*vt[k].os_sum/to});
      const pu=p('PU'), mc=p('MC');
      row('🛻','sec-ov-collateral',
        `<b>Pickups are ${pu.o.toFixed(0)}% of outstanding</b> on ${pu.a.toFixed(0)}% of accounts; <b>motorcycles are ${mc.a.toFixed(0)}% of accounts on ${mc.o.toFixed(0)}%</b> of the money`,
        'two books, not one: the same collections hour recovers a different amount of baht in each, so staff them separately');
    }
    // 3. The collateral pool ahead of us, not the one behind us.
    const tr=bt&&bt.new_regis_trend, yrs=tr?Object.keys(tr).sort():[];
    if(yrs.length>=2){
      const a=tr[yrs[0]].pickup, b=tr[yrs[yrs.length-1]].pickup;
      const ta=tr[yrs[0]].total, tb=tr[yrs[yrs.length-1]].total;
      const dp=Math.round(100*(a-b)/a), dt=Math.round(100*(ta-tb)/ta);
      if(a&&b) row('📉','sec-ov-collateral',
        `<b>New-pickup registrations are down ${dp}%</b> since ${Number(yrs[0])-543} (${N(a)} → ${N(b)}), against ${dt}% for the whole new-vehicle market`,
        `the used-pickup pool we will be lending against in a few years is thinning ${dt>0?(dp/dt).toFixed(1)+'× ':''}faster than the market, and pickups already carry the largest share of the balance`);
    }
    // 4. Live hazard: the only row here that can change between now and the meeting. Dated from the
    //    layer's own observation stamp — "right now" would be a lie the moment the pull goes stale.
    if(flood&&flood.provinces){
      const ps=Object.entries(flood.provinces).filter(([,v])=>v.n_high>0)
        .sort((a,b)=>b[1].n_high-a[1].n_high);
      const obs=(flood.meta&&flood.meta.observed_to)||'';
      if(ps.length) row('🌊','sec-ov-hazard',
        `<b>${ps.length} of ${Object.keys(flood.provinces).length} provinces had river stations at high water</b>${obs?` as of ${obs}`:''}, worst ${ps[0][0]} at ${ps[0][1].n_high} of ${ps[0][1].n_stations} stations`,
        'the only signal on this tab that moves daily; it names a collections problem days before any monthly series does');
    }
    // 5. Informal debt: the number everyone assumes is a region and is actually a job.
    if(debt&&debt.national&&debt.by_class){
      const last=debt.national[debt.national.length-1];
      const worst=debt.by_class.slice().sort((a,b)=>(b.informal_pct||0)-(a.informal_pct||0))[0];
      if(last&&worst) row('💸','sec-ov-labour',
        `<b>Informal debt is ${last.informal_pct}% of household debt nationally but ${worst.informal_pct}% for ${(worst.cls_en||'the occupations we lend to').toLowerCase()}s</b>`,
        `${(worst.informal_pct/last.informal_pct).toFixed(0)}× the national rate, and those are our borrowers' occupations: assume debt the file never shows, and read affordability accordingly`);
    }
    // 6. The correction that resizes every price claim on this tab.
    if(fh&&fh.latest&&fh.latest.nonfarm_share_of_income_pct!=null) row('🏠','sec-ov-agri',
      `<b>${fh.latest.nonfarm_share_of_income_pct}% of a farm household's cash income is non-farm</b>`,
      'so a crop-price shock reaches roughly half of what the household actually earns — halve every price number on this tab before you act on it');

    if(!R.length){ host.style.display='none'; return; }
    host.style.display='';
    host.innerHTML=`<div class="sw-hd">What this tab says today <span class="s">— the answer, then the evidence. Each line opens the section that proves it.</span></div>`
      +R.map(r=>`<button class="sw-row" data-swjump="${r.jump}">
          <span class="sw-ico" aria-hidden="true">${r.icon}</span>
          <span class="sw-txt">${r.lead}${r.tail?` <span class="sw-tail">— ${r.tail}</span>`:''}</span>
          <span class="sw-go" aria-hidden="true">→</span></button>`).join('');
  }).catch(()=>{ host.style.display='none'; });
}
document.addEventListener('click',e=>{
  const b=e.target.closest&&e.target.closest('[data-swjump]'); if(!b) return;
  // Reset the target topic to "All" first. A row promises to open the section that PROVES it, and
  // the sub-switcher remembers whichever subsection the reader last chose there — so without this,
  // following "pickups are 38% of outstanding" could land on the EV panel with the pickup evidence
  // hidden. The band's promise outranks the remembered sub-selection.
  if(typeof OV_SUB==='object'&&OV_SUB) OV_SUB[b.dataset.swjump]='';
  // Route through the SAME exclusive topic switcher the chips use, so the band can never leave two
  // topics open at once or desync the active chip.
  if(typeof showOvPanel==='function') showOvPanel(b.dataset.swjump,{scroll:'nav'});
  else { const s=document.getElementById(b.dataset.swjump); if(s){ s.open=true; s.scrollIntoView({behavior:'smooth',block:'start'}); } }
});

function renderAnswerBand(){
  const host=$('#ov-answer'); if(!host) return;
  Promise.all([tmliFetch('commodities'),loadMacroIndicators(),tmliFetch('tape_real'),
               tmliFetch('commodity_history')]).then(([com,mi,tape,hist])=>{
    const T=[], sig=v=>(v>0?'+':'')+v+'%';
    // price history, when the layer is present: label -> last N values (see build_commodity_history.py)
    const series=lab=>{
      if(!hist||!hist.series) return null;
      const s=hist.series[lab]||hist.series[String(lab||'').toLowerCase()];
      return s&&Array.isArray(s.values)?s.values:null;
    };
    const board=(com&&com.board)||[];
    const pick=re=>board.find(b=>re.test(b.lab||''));
    // 1-2. The two crops that carry the farm book, at the THAI farm-gate (measured) — not the
    //      world price, which is what the borrower does not get paid.
    [[/^rice/i,'Rice · Thai farm-gate','rice'],[/^rubber/i,'Rubber · Thai farm-gate','rubber']].forEach(([re,k,key])=>{
      const b=pick(re); if(!b) return;
      const loc=b.local_yoy, glob=b.global_yoy, v=(loc!=null?loc:glob);
      if(v==null) return;
      const vals=series(key);
      T.push(abTile({k,cad:'monthly',cadCls:'m',v:sig(v).replace('%',''),unit:'% YoY',
        move:(glob!=null&&loc!=null)?`world ${sig(glob)} · local ${loc>glob?'ahead':'behind'} ${Math.abs(Math.round((loc-glob)*10)/10)}pt`
             :(loc==null?'world price — no Thai farm-gate series':''),
        moveColor:v>0?'var(--merch)':'var(--agri)',
        spark:vals?svgSpark(vals,{aria:k+' price history',title:k}):'',
        why:vals?'':'monthly feed · history not retained yet',
        sub:loc!=null?'MEASURED Thai farm-gate':'MEASURED world price (Pink Sheet)'}));
    });
    // 3. Diesel — the cost line every pickup/haulage borrower pays, and the fastest-moving number here.
    const f=com&&com.fuel;
    if(f&&f.diesel_thb_l!=null) T.push(abTile({k:'Diesel · '+(f.name||'retail'),cad:'daily',cadCls:'d',
      v:f.diesel_thb_l,unit:' ฿/L',move:'cost line, not revenue',moveColor:'var(--mid)',
      why:'daily feed · history not retained yet',sub:'MEASURED Bangchak retail'}));
    // 4-5. The credit tide. These are the ONLY two series that already ship a real history array.
    const I=(mi&&mi.indicators)||{};
    if(I.household_debt_gdp) { const h=I.household_debt_gdp;
      T.push(abTile({k:'Household debt',cad:h.period||'quarterly',cadCls:'q',v:h.value,unit:'% GDP',
        move:h.yoy_change!=null?`${h.yoy_change<0?'▼':'▲'} ${Math.abs(h.yoy_change)}pt YoY`:'',
        moveColor:h.yoy_change<0?'var(--merch)':'var(--agri)',
        spark:svgSpark(h.trend,{color:'var(--accent)',aria:'household debt to GDP trend',title:'BIS'}),
        sub:'MEASURED BIS'})); }
    if(I.policy_rate) { const p=I.policy_rate;
      T.push(abTile({k:'Policy rate',cad:p.period||'quarterly',cadCls:'q',v:p.value,unit:'%',
        move:p.yoy_change!=null?`${p.yoy_change<0?'▼':'▲'} ${Math.abs(p.yoy_change)}pt YoY`:'',
        moveColor:'var(--mid)',
        spark:svgSpark(p.trend,{color:'var(--accent)',aria:'policy rate trend',title:'BIS'}),
        sub:'MEASURED BIS'})); }
    // 6. Our own book, so the backdrop is never read without the thing it acts on. Live book only —
    //    the 180+ legacy stock is held apart on purpose and blending them would flatter the number.
    //    (regex is anchored on "of accounts" — "NPL-live (90-179dpd) 4.92%" otherwise captures the
    //     "90" out of the bucket label rather than the rate.)
    const hd=tape&&tape.headline&&/NPL-live[^%]*?([0-9.]+)%\s*of accounts/.exec(tape.headline);
    if(hd) T.push(abTile({k:'Live book · NPL 90–179',cad:'tape vintage',cadCls:'q',
      v:hd[1],unit:'% of accounts',move:'180+ legacy held separately',moveColor:'var(--mid)',
      why:'2 vintages on disk · needs 6+ for a line',sub:'MEASURED real loan tape'}));

    if(!T.length){ host.style.display='none'; return; }
    host.style.display=''; host.innerHTML=T.join('');
    const n=$('#ov-answer-note');
    if(n) n.innerHTML='The answer first — every figure above is <b>measured</b>, with the source that '
      +'publishes it and how often it can change. A trend line is drawn only where history is actually '
      +'stored; where it says <i>history not retained yet</i> the feed is live but the pipeline keeps '
      +'only its latest value. Everything below this line is the evidence.';
  }).catch(()=>{ host.style.display='none'; });
}

/* Province macro watchlist + its branch drill were REMOVED 2026-08-01 (owner directive: no
   derived/composite metrics on Macro). Rationale is on the deleted mount in index.html. The
   macro_sensitivity layer itself is untouched — loadMacroSens() still feeds the branch drill
   and the cluster brief, which quote its real per-branch numbers rather than a ranking. */

/* ---------- Collateral outlook board (objective #1, portfolio risk) ----------
   Makes explicit that the two things AutoX lends against are diverging:
   GOLD value is UP (measured, from the commodity board), while the DIESEL-PICKUP collateral
   backing most title loans is under depreciation pressure (used-pickup glut + EV/PHEV
   transition). We have NO live Thai used-pickup index, so the pickup card is labelled an
   EDITORIAL / ESTIMATED WATCH — said plainly in the note. */
// per-province collateral recovery-value outlook (data/collateral_outlook.json, obj#1). Lazy-loaded
// once; feeds a national-summary card into the Overview collateral board. Graceful when absent.
let COLLO=null, colloLoaded=false, colloPromise=null;
function loadCollatOutlookData(){
  if(colloPromise) return colloPromise;
  colloLoaded=true;
  colloPromise=fetch('data/collateral_outlook.json').then(r=>r.ok?r.json():null)
    .then(j=>{COLLO=j||null;return COLLO;}).catch(()=>{COLLO=null;return null;});
  return colloPromise;
}
// MEASURED national title-collateral fleet trend (data/vehicle_fleet.json, obj#1). Adds the TIME
// dimension the single-vintage province vehicle stock lacks — is the collateral base growing/shrinking.
let FLEET=null, fleetLoaded=false, fleetPromise=null;
function loadFleetData(){
  if(fleetPromise) return fleetPromise;
  fleetLoaded=true;
  fleetPromise=fetch('data/vehicle_fleet.json').then(r=>r.ok?r.json():null)
    .then(j=>{FLEET=j||null;return FLEET;}).catch(()=>{FLEET=null;return null;});
  return fleetPromise;
}
// MEASURED EV-transition WORKFORCE exposure (data/ev_exposure.json, obj#1). The resale cards above read
// the collateral ASSET side (diesel-pickup recovery value under electrification); this reads the borrower
// INCOME side — the ICE auto-parts workforce (DIW s-curve automotive factories) whose jobs the same EV
// transition pressures, concentrated in the Eastern industrial corridor. Exposure, NOT a job-loss forecast.
let EVEXP=null, evexpLoaded=false, evexpPromise=null;
function loadEvExposure(){
  if(evexpPromise) return evexpPromise;
  evexpLoaded=true;
  evexpPromise=fetch('data/ev_exposure.json').then(r=>r.ok?r.json():null)
    .then(j=>{EVEXP=j||null;return EVEXP;}).catch(()=>{EVEXP=null;return null;});
  return evexpPromise;
}
function renderCollatOutlook(){
  const el=$('#collat-outlook'); if(!el) return;
  // warm the per-province outlook layer; re-render once it lands so the national card appears.
  if(!colloLoaded) loadCollatOutlookData().then(()=>{ try{renderCollatOutlook();}catch(e){} });
  if(!fleetLoaded) loadFleetData().then(()=>{ try{renderCollatOutlook();}catch(e){} });
  if(!evexpLoaded) loadEvExposure().then(()=>{ try{renderCollatOutlook();}catch(e){} });
  const cards=[
    {k:'Diesel-pickup collateral', v:'↓ pressure', d:'value at risk', cls:'down',
     n:'Editorial / estimated watch · used-pickup glut + EV/PHEV transition erode resale of the trucks backing most title loans. No live Thai used-pickup index yet.'},
    {k:'Used-motorcycle collateral', v:'↓ volatile', d:'lowest recovery', cls:'down',
     n:'Motorcycle titles are the smallest, most volatile, lowest-recovery collateral on the book — see the motorcycle-share table below (DLT, measured).'},
  ];
  // MEASURED national fleet trend (vehicle_fleet.json) — the collateral BASE size + whether it is
  // growing or shrinking (DLT/MOT registry). This is the measured companion to the editorial cards
  // above: it puts a real YoY number on the diesel-pickup / motorcycle collateral-pool direction.
  if(FLEET&&Array.isArray(FLEET.classes)){
    const yc=FLEET.latest_year_ce||(FLEET.meta&&FLEET.meta.latest_year_ce);
    const byk={}; FLEET.classes.forEach(c=>byk[c.key]=c);
    [['pickup','Pickup-title fleet'],['moto','Motorcycle-title fleet']].forEach(([k,lbl])=>{
      const c=byk[k]; if(!c||c.yoy_pct==null) return;
      const up=c.yoy_pct>0, v=(up?'▲ +':'▼ ')+c.yoy_pct.toFixed(2)+'%';
      cards.push({k:lbl+' (national)', v, d:c.latest.toLocaleString()+' regd', cls:up?'up':'down',
        n:'MEASURED · DLT/MOT registered-vehicle stock, YoY to '+(yc||'latest')+'. '+
          (up?'Collateral pool still growing (pace vs prior years).':'Collateral pool CONTRACTING — a shrinking resale/recovery base behind this slice of the book.')+
          ' Fleet SIZE, not resale value.'});
    });
  }
  // MEASURED EV-transition WORKFORCE exposure (ev_exposure.json) — the INCOME-side companion to the
  // editorial diesel-pickup resale card above. Same EV transition, different channel: the ICE auto-parts
  // jobs it pressures = borrower repayment capacity in the automotive-manufacturing provinces. Exposure
  // (the workforce that COULD be pressured), not a forecast that these jobs are being lost now.
  if(EVEXP&&EVEXP.meta&&EVEXP.meta.national&&EVEXP.meta.national.workers!=null){
    const en=EVEXP.meta.national, np=EVEXP.meta.n_provinces||0;
    const provs=Array.isArray(EVEXP.provinces)?EVEXP.provinces:(EVEXP.provinces?Object.values(EVEXP.provinces):[]);
    const top3=provs.slice().sort((a,b)=>(b.workers||0)-(a.workers||0)).slice(0,3);
    const t3=top3.map(p=>p.th).filter(Boolean).join(', ');
    const wk=en.workers, wkStr=wk>=1000?Math.round(wk/1000)+'k':(''+wk);
    cards.push({k:'ICE auto-parts jobs exposed', v:wkStr, d:'EV-transition income risk', cls:'down',
      n:'MEASURED · '+wk.toLocaleString()+' workers across '+(en.factories||0).toLocaleString()+' automotive-group factories in '+np+' provinces (DIW s-curve census). '+
        'The borrower-INCOME channel of the EV transition — distinct from the resale-value channel above — most concentrated in '+(t3||'the Eastern corridor')+'. '+
        'Exposure (jobs that COULD be pressured as production electrifies), NOT a measured job-loss forecast.'});
  }
  // national recovery-value outlook (from collateral_outlook.json) — firming vs softening + most-at-risk.
  const nat=COLLO&&COLLO.national;
  if(nat&&nat.exposure_weighted_outlook!=null){
    const o=nat.exposure_weighted_outlook, firm=o>=0;
    cards.push({k:'Recovery outlook (national)', v:firm?'firming':'softening', d:(firm?'+':'')+o.toFixed(2)+' index', cls:firm?'up':'down',
      n:'Estimated directional read · '+(nat.n_firming||0)+'/'+(nat.n_provinces||0)+' provinces firming; most at-risk '+(nat.most_at_risk_province||'—')+
        ' (highest motorcycle-title share). Based on measured DLT vehicle mix. NOT a measured recovery rate.'});
  }
  el.innerHTML=cards.map(c=>`<div class="mcard"><div class="k">${c.k}</div>
    <div class="v ${c.cls}">${c.v}</div><div class="d ${c.cls==='up'?'up':'dn'}">${c.d}</div>
    <div class="n">${c.n}</div></div>`).join('');
  const note=$('#collat-note');
  if(note) note.innerHTML='<b>Read:</b> AutoX lends against <b>vehicle titles</b> (pickups, cars, motorcycles) — the diesel-pickup and used-motorcycle sides both face a slow value squeeze. '+
    'If recovery values on repossessed vehicles fall, loss-given-default on the title book rises even before any change in default rates. '+
    'The same EV transition also has an <b>income-side</b> channel — the measured ICE auto-parts workforce card is exposure (jobs that could be pressured), not a job-loss forecast. '+
    'These directions are an <b>estimated / editorial watch</b> (no live Thai used-vehicle price index in this data); the vehicle-mix shares below are measured (DLT).';
}
/* ---------- Diesel-pickup collateral · per-province diesel share + national brand mix ----------
   objective #1, MEASURED. AutoX's core title collateral is the diesel pickup; the EV/diesel
   transition is the resale-value risk under it. Two MEASURED reads from data/vehicle_collateral.json:
   (a) per-province DIESEL SHARE of the car(รย.1)+pickup(รย.3) registered fleet (DLT dataset_1_1_04) —
       where diesel dominates, resale is most exposed as the fleet electrifies; and
   (b) the NATIONAL collateral BRAND mix (DLT first registrations) — Toyota+Isuzu pickups, Honda/Toyota
       cars, BYD/EV rising. Brand is NATIONAL ONLY (no measured brand×province in reachable Thai open
       data) — said plainly. Lazy-loaded; graceful/null-safe when absent. */
let VCOLL=null, vcollLoaded=false, vcollPromise=null;
function loadVehicleCollateral(){
  if(vcollPromise) return vcollPromise;
  vcollLoaded=true;
  vcollPromise=fetch('data/vehicle_collateral.json').then(r=>r.ok?r.json():null)
    .then(j=>{VCOLL=j||null;return VCOLL;}).catch(()=>{VCOLL=null;return null;});
  return vcollPromise;
}
/* RETIRED 2026-08-02 — renderDieselCollateral (the diesel-share + brand-tile block) and
   renderCollatMix (the "most motorcycle-heavy provinces" table). Both are inside renderCollateralBook
   now, and both were exactly what the owner objected to:

     point 10  "Diesel-share table good but its not all provinces. This is the weakness of top ten
               lists."      -> diesel share is a column on the geo drill, all 77 provinces
     point 12  "Give me the full mix to 100% and all provinces."
               -> the 8-type mix sums to 100% of the book; the geography is the drill
     point  8  the four brand tiles -> every brand the tape carries, ranked by outstanding

   renderCollatMix also ranked provinces by MOTORCYCLE share, which put the class that is 5.8% of the
   money at the top of a collateral table. The replacement ranks by baht everywhere.

   collatMixRows() SURVIVES — it is the province motorcycle/car/pickup/EV mix from the DLT stock, and
   the Command-center risk readout and the data-room export still read it. Only the table it fed is
   gone. */
function collatMixRows(){
  return (PROV||[]).filter(p=>p.vehicles&&p.moto!=null&&(p.branches||0)>0)
    .map(p=>({th:p.th,region:p.region,branches:p.branches,vehicles:p.vehicles,
              moto:Math.round(100*p.moto/p.vehicles),
              car:p.car!=null?Math.round(100*p.car/p.vehicles):null,
              pickup:p.pickup!=null?Math.round(100*p.pickup/p.vehicles):null,
              ev:p.ev!=null?Math.round(100*p.ev/p.vehicles):null}))
    .sort((a,b)=>b.moto-a.moto);
}

/* ---------- National registered-vehicle collateral base (objective #1, MEASURED) ----------
   The external anchor for the book's collateral mix: how large the registered-vehicle base is,
   split into the classes AutoX lends against (motorcycle / car / pickup / agri), and how each
   grew year-on-year — straight from the MOT open-data registry (vehicle_registry.json). MEASURED,
   national (NOT province — that dimension is the DLT-derived table below). Lazy + null-safe: absent
   file → the wrap stays hidden and the Overview reads exactly as before. */
let VEHREG=null, vehregPromise=null;
function loadVehReg(){
  if(vehregPromise) return vehregPromise;
  vehregPromise=fetch('data/vehicle_registry.json').then(r=>r.ok?r.json():null)
    .then(j=>{VEHREG=j||null;return VEHREG;}).catch(()=>{VEHREG=null;return null;});
  return vehregPromise;
}
function renderVehReg(){
  const wrap=$('#vehreg-wrap'), cards=$('#vehreg-cards'), note=$('#vehreg-note');
  if(!wrap||!cards||!VEHREG||!VEHREG.latest) return;
  const m=VEHREG.meta||{}, g=VEHREG.latest.groups||{}, yoy=VEHREG.yoy||{};
  const fmtM=n=>(n/1e6).toFixed(n>=1e7?1:2)+'M';
  const arrow=v=>v==null?'':(v>0?'▲':v<0?'▼':'•');
  const col=v=>v==null?'var(--collat)':(v>0?'var(--up)':v<0?'var(--agri)':'var(--collat)');
  const sig=v=>v==null?'':' <span style="font-size:12px;color:'+col(v)+'">'+arrow(v)+' '+(v>0?'+':'')+v+'% YoY</span>';
  const defs=[
    ['motorcycle','Motorcycle title','the small-ticket title core'],
    ['car','Car (sedan/van)','higher-ticket title'],
    ['pickup','Pickup &amp; van','the diesel-pickup book'],
    ['agri','Agri (tractor/farm)','agri collateral'],
  ];
  cards.innerHTML=defs.map(([k,lab,d])=>
    `<div class="mcard"><div class="k">${lab}</div>`
    +`<div class="v" style="color:var(--collat);font-size:17px">${fmtM(g[k]||0)}${sig(yoy[k])}</div>`
    +`<div class="n">${d}</div></div>`).join('');
  const share=m.moto_share_of_title_base_pct;
  if(note) note.innerHTML='The collateral base AutoX lends against, from the government registry: <b>'
    +(VEHREG.latest.title_base/1e6).toFixed(1)+'M</b> registered motorcycles, cars, pickups &amp; farm vehicles '
    +'(of '+(VEHREG.latest.all_vehicles/1e6).toFixed(1)+'M vehicles of every type), vintage <b>'+(m.vintage||'')+'</b>. '
    +'Motorcycles are <b>'+(share!=null?share+'%':'—')+'</b> of that title-lendable base — grounding the "≈half the book is motorcycle title" mix in a measured count rather than an assumption. '
    +TAG_M+' · MOT registry · national (a cumulative registered stock, not new sales — see method).';
  wrap.style.display='';
}

/* ---------- Collateral recovery-value sensitivity (objective #1, ILLUSTRATIVE) ----------
   Combines the MEASURED gold move (+62.7%, commodity board — gold collateral firming) with an
   ILLUSTRATIVE used-motorcycle value shock. We have NO loan balances and NO LTV, so we do NOT
   invent LTV-breach counts. Instead we rank the provinces AutoX operates in by motorcycle-title
   SHARE (measured) — those most exposed if used-motorcycle recovery values fall. The 10% figure
   is a stated, illustrative scenario, NOT a forecast. */
/* RECOVERY-VALUE SENSITIVITY — rebuilt on the real tape, 2026-08-02.
   Owner, point 14: "a very powerful dataset and table. I want greater elaboration and detail as
   AutoX focuses heavily on pickup and passenger cars. Motorcycles are a secondary focus due to
   smaller ticket size."

   The old version could not do that, and said so in its own note: "we have no loan balances and no
   LTV, so we rank by motorcycle-share exposure and deliberately show no LTV-breach counts." That
   stopped being true on 2026-07-21 when the real tape landed. Per collateral type we now hold the
   MEASURED outstanding per account and the MEASURED appraised value per account — so the question
   stops being "which provinces own a lot of motorcycles" and becomes the real one: how far can
   resale values fall before the collateral stops covering the loan.

   The shock ladder is ILLUSTRATIVE (no Thai used-vehicle price index exists to forecast from) but
   every position it is applied to is measured, and the rows are ordered by outstanding, so pickup
   and passenger car lead instead of the class that is 5.8% of the money. */
function renderRecoverySensitivity(){
  const cards=$('#recovery-cards'), note=$('#recovery-note'), tbl=$('#recoverytbl'); if(!cards) return;
  tmliFetch('collateral_book').then(j=>{
    const T=(j&&j.types)||[];
    if(!T.length){ cards.innerHTML=''; if(note) note.textContent=''; if(tbl) tbl.innerHTML=''; return; }
    const B=v=>v==null?'—':'฿'+Math.round(v).toLocaleString('en-US');
    const mB=v=>v>=1e9?'฿'+(v/1e9).toFixed(2)+'bn':'฿'+Math.round(v/1e6).toLocaleString('en-US')+'m';
    const withLtv=T.filter(t=>t.ltv_proxy_pct!=null);
    const head=v=>100-v;                       // the fall a class absorbs before it is underwater
    const thin=withLtv.slice().sort((a,b)=>b.ltv_proxy_pct-a.ltv_proxy_pct)[0];
    const core=T.filter(t=>t.tier==='core');
    const coreOs=core.reduce((s,t)=>s+t.os,0);
    // The fall the WHOLE book absorbs before the first baht is uncovered. At a ~52% lent-to-value
    // ratio this is large, and that is the finding — not a table that reports "nothing happens" at
    // shocks the book was never going to notice. The ladder below is scaled to actually cross 100%.
    const bookHead=withLtv.length?Math.min(...withLtv.map(t=>head(t.ltv_proxy_pct))):null;
    // Where a fall would actually be worked: the branches already lending the most against value.
    // The class ladder says the book is safe; this says which branches stop being safe first.
    let thinBr=null, nBr=0;
    if(j&&j.branches){ const all=[].concat(...Object.values(j.branches));
      nBr=all.length; thinBr=all.filter(b=>(b.ltv_proxy_pct||0)>=60).length; }
    cards.innerHTML=[
      {k:'Core collateral',v:mB(coreOs),d:core.map(t=>t.label.toLowerCase()).join(' + '),cls:'',
       n:'MEASURED — outstanding on the two focus classes. First here because they are the money, not because they are the most numerous.'},
      {k:'Thinnest headroom',v:thin?thin.label:'—',d:thin?head(thin.ltv_proxy_pct).toFixed(1)+'% before underwater':'',cls:'down',
       n:'MEASURED — the class lending the highest share of assessed value, so the first to go underwater when resale values fall.'},
      {k:'Branches over 60% of value',v:thinBr==null?'—':String(thinBr),d:nBr?'of '+nBr.toLocaleString('en-US')+' branches':'',cls:thinBr?'down':'',
       n:'MEASURED — branches whose book already lends more than 60% of assessed collateral value. Nothing in the book is uncovered until resale values fall '+(bookHead==null?'far':bookHead.toFixed(0)+'%')+', but these branches reach that point first, so they are where a fall would be worked.'}
    ].map(c=>`<div class="mcard"><div class="k">${c.k}</div>
      <div class="v ${c.cls}">${c.v}</div><div class="d ${c.cls==='down'?'dn':'up'}">${c.d}</div>
      <div class="n">${c.n}</div></div>`).join('');
    if(note) note.innerHTML='<b>How far can resale values fall before the collateral stops covering the loan?</b> '+
      'Per class we hold the <b>measured</b> outstanding per account and the <b>measured</b> appraised value per account; '+
      '<b>headroom</b> is the gap between them. The shock columns are <b>illustrative</b> — no Thai used-vehicle price index exists to forecast from — '+
      'but they are applied to measured positions, so the ranking is real, and the ladder is scaled to the fall that actually matters — at a 52% lent-to-value ratio a 10% dip changes nothing. '+
      'Ordered by outstanding, so <b>pickup and passenger car lead</b>; the previous version ranked by motorcycle share and led with 5.8% of the money.';
    if(tbl) tbl.innerHTML=`<tr><th scope="col">Collateral</th>
        <th scope="col" class="gd-r">Outstanding</th>
        <th scope="col" class="gd-r" title="MEASURED — outstanding per account">Ticket</th>
        <th scope="col" class="gd-r" title="MEASURED — appraised value per account">Appraised</th>
        <th scope="col" class="gd-r" title="DERIVED — outstanding ÷ appraised, per account">Lent vs value</th>
        <th scope="col" class="gd-r" title="DERIVED — how far resale value can fall before outstanding exceeds it">Headroom</th>
        <th scope="col" class="gd-r" title="ILLUSTRATIVE — appraised value after the fall, as a share of what is still lent. Below 100% the collateral no longer covers the loan.">After −20%</th>
        <th scope="col" class="gd-r">After −35%</th>
        <th scope="col" class="gd-r">After −50%</th></tr>`+
      T.map(t=>{
        if(t.ltv_proxy_pct==null) return `<tr><td class="gd-geo"><b>${t.label}</b></td><td class="gd-r">${mB(t.os)}</td>`+
          `<td class="gd-r">${B(t.ticket)}</td><td class="gd-r"><span class="gd-na">—</span></td>`+
          `<td class="gd-r" colspan="5"><span class="gd-na">no appraised value carried on this class</span></td></tr>`;
        const h=head(t.ltv_proxy_pct);
        const cell=f=>{ const cov=t.eval_avg*(1-f/100)/t.ticket*100;
          const col=cov<100?'var(--agri)':cov<115?'var(--gold)':'var(--merch)';
          return `<td class="gd-r" style="color:${col}">${cov.toFixed(0)}%</td>`; };
        return `<tr><td class="gd-geo"><b>${t.label}</b>${t.tier==='core'?' <span class="cb-tier core">core</span>':''}</td>
          <td class="gd-r">${mB(t.os)}</td><td class="gd-r">${B(t.ticket)}</td><td class="gd-r">${B(t.eval_avg)}</td>
          <td class="gd-r">${t.ltv_proxy_pct}%</td>
          <td class="gd-r" style="color:${h<40?'var(--agri)':h<48?'var(--gold)':'var(--merch)'}"><b>${h.toFixed(1)}%</b></td>
          ${cell(20)}${cell(35)}${cell(50)}</tr>`;
      }).join('')+`<tr><td class="gd-geo"><b>Whole book</b></td>
        <td class="gd-r"><b>${mB(T.reduce((s,t)=>s+t.os,0))}</b></td>
        <td colspan="7" class="sub" style="text-align:left">Cover = appraised value after the fall, as a share of what is still lent. Below 100% the collateral no longer covers the loan.</td></tr>`;
  }).catch(()=>{});
}

/* ---------- EV transition · used-collateral value watch (objective #1, MEASURED) ----------
   Surfaces data/ev_penetration.json (build_ev_penetration.py, DLT registered-fleet fuel-type
   split — a previously dangling MEASURED layer, visible nowhere in the app). Backs the editorial
   "EV/PHEV transition erodes resale" line in the recovery-sensitivity card with real DLT numbers.
   IMPORTANT honesty: this is registered-STOCK share, an exposure proxy — NOT a used-vehicle price
   index. BEV is still <1% of the national fleet, so the collateral-value threat is early, not
   present; the value is as a monitorable leading indicator concentrated in a few provinces. */
let EVLOADED=false, EVDATA=null;
function renderEvWatch(){
  const cards=$('#ev-cards'), note=$('#ev-note'), tbl=$('#evtbl'); if(!cards) return;
  if(!EVLOADED){
    fetch('data/ev_penetration.json').then(r=>r.ok?r.json():null).then(j=>{EVDATA=j;EVLOADED=true;try{renderEvWatch();}catch(e){}}).catch(()=>{EVLOADED=true;});
    return;
  }
  if(!EVDATA||!EVDATA.meta||!EVDATA.meta.national){
    cards.innerHTML=''; if(tbl) tbl.innerHTML='';
    if(note) note.innerHTML='<b>EV-penetration data not available.</b> <span class="sub">data/ev_penetration.json is absent — it fills in from the DLT registered-fleet mirror on the next data refresh.</span>';
    return;
  }
  const nat=EVDATA.meta.national, vin=EVDATA.meta.vintage||'';
  const elecPct=nat.total?+( 100*((nat.bev||0)+(nat.phev||0)+(nat.hybrid||0))/nat.total ).toFixed(2):0;
  const dieselPct=nat.total?+( 100*(nat.diesel||0)/nat.total ).toFixed(1):0;
  const bevPct=nat.bev_pct!=null?nat.bev_pct:(nat.total?+(100*(nat.bev||0)/nat.total).toFixed(2):0);
  cards.innerHTML=[
    {k:'National BEV share',v:bevPct+'%',d:'of registered fleet',cls:'down',
     n:'MEASURED (DLT) — pure battery-EV as % of the '+(nat.total||0).toLocaleString()+'-vehicle registered fleet. Still under 1% — the ICE title book is not yet materially threatened.'},
    {k:'Electrified share',v:elecPct+'%',d:'BEV + PHEV + hybrid',cls:'down',
     n:'MEASURED (DLT) — all electrified powertrains. The leading indicator to watch; most title collateral is still ICE.'},
    {k:'Diesel share',v:dieselPct+'%',d:'pickups & trucks',cls:'up',
     n:'MEASURED (DLT) — diesel (pickup/truck) share; the higher-recovery title collateral, least exposed to the EV shift so far.'},
  ].map(c=>`<div class="mcard"><div class="k">${c.k}</div>
    <div class="v ${c.cls}">${c.v}</div><div class="d ${c.cls==='up'?'up':'dn'}">${c.d}</div>
    <div class="n">${c.n}</div></div>`).join('');
  if(note) note.innerHTML='<b>Read:</b> AutoX lends against <b>used vehicle titles</b>, so a shift to EVs would soften resale of the ICE cars/pickups/motorcycles backing the book. '+
    'The transition is <b>real but early</b>: BEVs are only <b>'+bevPct+'%</b> of the registered fleet and electrified powertrains <b>'+elecPct+'%</b> (both <b>measured, DLT '+vin+'</b>). '+
    'This is registered-<b>stock</b> share — an <b>exposure proxy, not a used-vehicle price index</b> (we have no Thai used-vehicle price series). '+
    'It matters as a <b>leading indicator</b>: adoption is concentrated in the provinces below, where used-ICE resale softening would show first.';
  if(!tbl) return;
  // join the MEASURED EV layer to AutoX's own footprint (PROV branches/region) and keep only
  // provinces AutoX operates in — ties the collateral watch to the network we actually run.
  const byTh={}; (PROV||[]).forEach(p=>{byTh[p.th]=p;});
  const rows=(EVDATA.provinces||[]).map(r=>{const pv=byTh[r.th]||{};
    return {th:r.th,en:pv.en||r.th,region:pv.region||'—',branches:pv.branches||0,
            elec:r.electrified_pct,bev:r.bev_pct,diesel:r.diesel_pct};})
    .filter(r=>r.branches>0)
    .sort((a,b)=>b.elec-a.elec).slice(0,8);
  if(!rows.length){ tbl.innerHTML=''; return; }
  tbl.innerHTML=`<tr><th>#</th><th>Province</th><th>Region</th><th title="AutoX branches">Branches</th><th class="h-collat" title="BEV+PHEV+hybrid as % of registered fleet — DLT, measured">Electrified % ▲ (DLT)</th><th title="pure battery-EV share — DLT, measured">BEV %</th><th title="diesel share — DLT, measured">Diesel %</th></tr>`+
    rows.map((r,i)=>{const ec=r.elec>=4?'var(--agri)':r.elec>=2.5?'var(--gold)':'var(--collat)';
      return `<tr><td class="mono sub">${i+1}</td><td><b>${r.en}</b></td><td class="sub">${r.region}</td>
      <td class="mono">${r.branches}</td>
      <td>${barHTML(r.elec,ec,8)} <span class="mono" style="color:${ec}">${r.elec}%</span></td>
      <td class="mono sub">${r.bev!=null?r.bev+'%':'—'}</td>
      <td class="mono sub">${r.diesel!=null?r.diesel+'%':'—'}</td></tr>`;}).join('');
}

/* RETIRED 2026-08-02 — renderCstressVerdict + renderCropStress (the `agri_stress` 0-100 composite
   table). Owner: "agri stress is an estimated measure that has been made up. Difficult to relate…
   tie it to the table in item 1, combine if possible." It is now combined: the table's two MEASURED
   survivors — rainfall % of normal and OAE dry-season 2nd-rice area — are province columns on the
   farm-book drill, and the ranking quantity is outstanding baht instead of a composite. The `CSTRESS`
   layer itself is untouched and still drives the national map lens, the simulator and #trend. */

/* ---------- district drought (OAE SPEI) · Overview card, objective #1 ----------
   MODELLED per-amphoe SPEI (ERA5-Land reanalysis, OAE) — a DISTRICT-grain sharpening of the province
   crop-stress verdict above (whose drought input is a coarser HDX rainfall proxy). It names the
   specific driest districts the province table can't resolve. Honestly labelled MODELLED (a model
   product, not a measured observation, not a disaster declaration). Null-safe: absent / shapeless
   file → the whole card stays hidden and the Overview reads exactly as before. */
function renderDroughtDistrict(j){
  const wrap=$('#drought-district-wrap'); if(!wrap) return;
  const ds=j&&Array.isArray(j.districts)?j.districts:null;
  if(!ds||!ds.length){ wrap.style.display='none'; return; }
  const m=j.meta||{}, c=m.counts||{}, snap=m.snapshot||'';
  const total=ds.length, mworse=(c.extreme||0)+(c.severe||0)+(c.moderate||0);
  wrap.style.display='block';
  const v=$('#drought-district-verdict');
  if(v) v.innerHTML=`<div class="verdict-line">🌾 <b>District drought:</b> ${mworse} of ${total} districts at moderate-or-worse on OAE's SPEI${snap?` (${snap})`:''} — <b style="color:var(--agri)">${c.extreme||0} extreme</b>, <span style="color:var(--gold)">${c.severe||0} severe</span>, ${c.moderate||0} moderate.</div>`+
    `<div class="sub" style="margin-top:4px">A sharper district-grain read behind the province crop-stress verdict above · ${provChip('e','modelled','OAE SPEI')}</div>`;
  const note=$('#drought-district-note');
  if(note) note.innerHTML='<b>SPEI</b> (Standardized Precipitation-Evapotranspiration Index) is a <b>MODELLED</b> drought index OAE computes from ERA5-Land reanalysis — an official model product, <b>not</b> station rainfall and <b>not</b> a disaster declaration. Lower (more negative) = drier. The crop-stress table above uses a coarser HDX rainfall proxy; this resolves the same signal to the <b>district</b>.';
  // top driest CLEAN districts — drop suspect-zero grid gaps + ambiguous name→polygon joins for
  // honesty (never attribute a drought reading to an uncertain district). Already sorted driest-first.
  const clean=ds.filter(x=>x&&x.cls&&!x.suspect_zero&&!x.join_ambiguous&&x.spei!=null).slice(0,8);
  const col=cl=>cl==='extreme'?'var(--agri)':cl==='severe'?'var(--gold)':'var(--mid)';
  const tbl=$('#drought-district-tbl');
  if(tbl) tbl.innerHTML=`<tr><th>#</th><th>District</th><th>Province</th><th title="Standardized Precipitation-Evapotranspiration Index — lower = drier (modelled)">SPEI ○ modelled</th><th>Severity</th></tr>`+
    clean.map((x,i)=>`<tr><td class="mono sub">${i+1}</td><td><b>${x.name_th||x.name_en||x.code}</b></td><td class="sub">${x.province_th||'—'}</td><td class="mono" style="color:${col(x.cls)}">${x.spei.toFixed(2)}</td><td><span class="tag" style="color:${col(x.cls)};border:1px solid ${col(x.cls)}">${x.cls}</span></td></tr>`).join('');
}

// District crop × drought exposure (Overview, obj #1) — MEASURED planted area (OAE satellite amphoe
// surveys) × MODELLED drought (OAE SPEI). The district-drought card above names the driest districts;
// this names WHICH crop in WHICH district carries the largest rai exposure sitting under drought — the
// crop-named, portfolio-actionable read (which slice of the agri-PD book is most exposed). Renders the
// layer's own pre-sorted severe-or-worse hotspots (largest planted area first). Null-safe: absent /
// shapeless layer → the wrap stays hidden, nothing fabricated.
function renderAmphoeCrops(j){
  const wrap=$('#amphoe-crops-wrap'); if(!wrap) return;
  const hs=j&&Array.isArray(j.hotspots)?j.hotspots.filter(h=>h&&h.planted_rai!=null&&h.spei!=null):null;
  if(!hs||!hs.length){ wrap.style.display='none'; return; }
  const m=j.meta||{}, unj=m.drought_unjoined_rows;
  wrap.style.display='block';
  // MEASURED counts, computed from the layer's own rows (never invented). severe-or-worse cell count
  // replicates the builder's tally exactly: UNIQUE (province,amphoe,crop) cells at severe/extreme with a
  // positive planted area — deduped across survey vintages so it matches build_amphoe_crops's headline
  // (the 60-row hotspots array is only the largest-area sample, not the full severe set).
  const rows=Array.isArray(j.rows)?j.rows:[];
  let sw;
  if(rows.length){ const s=new Set();
    for(const r of rows){ if((r.drought==='severe'||r.drought==='extreme')&&(r.planted_rai||0)>0) s.add(r.province_th+'|'+r.amphoe_th+'|'+r.crop); }
    sw=s.size;
  } else sw=hs.length;
  const top=hs[0];
  const rai=v=>(v==null||!isFinite(v))?'—':Math.round(v).toLocaleString('en-US');
  const v=$('#amphoe-crops-verdict');
  if(v) v.innerHTML=`<div class="verdict-line">🌾 <b>Crop × drought exposure:</b> ${sw} district-crop cells sit at severe-or-worse drought across ${rows.length?rows.length.toLocaleString('en-US')+' measured':'the measured'} amphoe crop rows. `+
    `Largest single exposure: <b>${top.crop_th||top.crop}</b> in <b>${top.province_th}·${top.amphoe_th}</b> — ${rai(top.planted_rai)} rai at SPEI ${(top.spei).toFixed(2)}.</div>`+
    `<div class="sub" style="margin-top:4px">Which slice of the agri-PD book sits under the driest ground · ${provChip('m','measured','OAE area')} × ${provChip('e','modelled','OAE SPEI')}</div>`;
  const note=$('#amphoe-crops-note');
  if(note) note.innerHTML='<b>MEASURED</b> planted area (OAE Geo-Informatics satellite amphoe surveys + Zone-6 surveys, every row cites its source PDF) <b>×</b> <b>MODELLED</b> drought (OAE SPEI from ERA5-Land reanalysis — a model product, not station rainfall, not a disaster declaration; lower = drier). Name-joined district-to-district'+(unj!=null?`; ${Number(unj).toLocaleString('en-US')} rows had no drought match and are dropped, never guessed`:'')+'. <b>Do not sum across crops</b> — the two survey sources carry different vintages.';
  const col=cl=>cl==='extreme'?'var(--agri)':cl==='severe'?'var(--gold)':'var(--mid)';
  const tbl=$('#amphoe-crops-tbl');
  if(tbl) tbl.innerHTML=`<tr><th>#</th><th>District</th><th>Province</th><th>Crop</th><th title="Measured planted area, rai (OAE amphoe survey)">Planted rai ●</th><th title="Standardized Precipitation-Evapotranspiration Index — lower = drier (modelled)">SPEI ○ modelled</th></tr>`+
    hs.slice(0,10).map((h,i)=>`<tr><td class="mono sub">${i+1}</td><td><b>${h.amphoe_th}</b></td><td class="sub">${h.province_th}</td><td>${h.crop_th||h.crop}</td><td class="mono">${rai(h.planted_rai)}</td><td class="mono" style="color:${col(h.drought)}">${(h.spei).toFixed(2)} <span class="tag" style="color:${col(h.drought)};border:1px solid ${col(h.drought)}">${h.drought}</span></td></tr>`).join('');
}

/* ---------- provincial labour stress (MEASURED · NSO LFS 2026 Q1, obj #1) ----------
   Reads data/province_lfs.json. Thai headline unemployment is uniformly low, so the sharper obj-#1
   signal is the seasonal-waiting share (agri off-season idle labour) — it marks the Isan rice-belt
   provinces where borrower cash-flow is most seasonal/lumpy, behind the agri-PD book. Leads the table
   with that, carries unemployment alongside, and states the measured national headline. Null-safe:
   absent/empty layer → the wrap stays hidden, nothing fabricated. */
function renderProvinceLfs(){
  const wrap=$('#lfs-wrap');
  if(!wrap) return;
  const rows=Array.isArray(LFS)?LFS.filter(p=>p&&p.name_th):[];
  if(!rows.length){ wrap.style.display='none'; return; }
  // MEASURED national headline unemployment (labour-force-weighted, computed from the layer's own rows).
  const totLf=rows.reduce((s,p)=>s+(p.labor_force_k||0),0);
  const natUnemp=totLf?rows.reduce((s,p)=>s+(p.unemployment_rate_pct||0)*(p.labor_force_k||0),0)/totLf:0;
  const topUnemp=rows.slice().sort((a,b)=>(b.unemployment_rate_pct||0)-(a.unemployment_rate_pct||0)).slice(0,3);
  // lead the table by seasonal-waiting share (the discriminator); carry unemployment alongside.
  const bySeas=rows.slice().sort((a,b)=>(b.seasonal_share_pct||0)-(a.seasonal_share_pct||0)).slice(0,8);
  const note=$('#lfs-note');
  if(note) note.innerHTML=`<b>Measured</b> — NSO Labour Force Survey ${LFS_META&&LFS_META.vintage?LFS_META.vintage:'2026 Q1'}, all 77 provinces. `+
    `Thailand's headline unemployment is uniformly low (national ${natUnemp.toFixed(1)}%, labour-force-weighted), so the `+
    `sharper objective-#1 signal is the <b>seasonal-waiting share</b> — the slice of the labour force idle between `+
    `agricultural seasons, which marks where borrower cash-flow is most seasonal (concentrated in the Isan rice belt, `+
    `behind the agri-PD book). Highest headline unemployment: ${topUnemp.map(p=>`${p.name_th} ${(p.unemployment_rate_pct||0).toFixed(1)}%`).join(', ')}.`;
  const tbl=$('#lfstbl');
  if(tbl) tbl.innerHTML=`<tr><th>#</th><th>Province</th><th title="Share of the labour force seasonally waiting — idle between agricultural seasons (measured, NSO LFS)">Seasonal idle ●</th><th title="Unemployment rate (measured, NSO LFS)">Unemp. ●</th><th title="Labour force, thousands (measured, NSO LFS)">Labour force</th></tr>`+
    bySeas.map((p,i)=>{const s=p.seasonal_share_pct||0;const c=s>=4?'var(--agri)':s>=2?'var(--gold)':'var(--mid)';
      return `<tr><td class="mono sub">${i+1}</td><td><b>${p.name_th}</b></td>`+
        `<td>${barHTML(Math.min(100,s*12),c)} <span class="mono" style="color:${c}">${s.toFixed(1)}%</span></td>`+
        `<td class="mono">${(p.unemployment_rate_pct||0).toFixed(1)}%</td>`+
        `<td class="mono sub">${Math.round(p.labor_force_k||0)}k</td></tr>`;}).join('');
  wrap.style.display='';
}

/* RETIRED 2026-08-02 — renderCropMargin (the standalone farmer-margin table). Owner: "I like the
   commodities/margin table but expand to cover what we have on data AND consolidate with above
   tables." Both halves are done in renderFarmCrops: widened from the 5 crops with an OAE cost row to
   all 8 the mix prices, and joined to the loan book by allocated farm baht and by each crop's
   contribution in pp to the book's move. crop_margin.json is now read by build_farm_book.py. */

/* ---------- New-pickup inflow trend · the future used-collateral pool (Overview, obj #1) ----------
   MEASURED — DLT first registrations by class per Buddhist-era year (data/brand_trends.json).
   The diesel-share card above is a snapshot; this is the TIME dimension it lacks: the diesel pickup
   is AutoX's core auto-title collateral (MEASURED tape: 31.3% of accounts and 38.3% of outstanding —
   the single largest balance exposure in the book), and how fast NEW pickups enter the fleet
   sets how fast the future USED-pickup collateral pool (what AutoX lends against + recovers on) is
   replenished. Leads with the pickup-inflow change vs the whole-market change, notes the rising EV
   share as the used-value leading indicator. Null-safe: absent/thin file → wrap stays hidden. */
function renderBrandTrends(){
  const wrap=$('#btrend-wrap'); if(!wrap) return;
  const d=BTREND, t=d&&d.new_regis_trend;
  const yrs=t?Object.keys(t).filter(y=>t[y]&&t[y].pickup!=null).sort():[];
  if(!t||yrs.length<2){ wrap.style.display='none'; return; }
  const be2ce=y=>String((+y)-543);
  const num=v=>(v==null||!isFinite(v))?'—':(+v).toLocaleString('en-US');
  const first=t[yrs[0]], last=t[yrs[yrs.length-1]];
  const pk0=first.pickup||0, pk1=last.pickup||0;
  const pkChg=pk0?((pk1-pk0)/pk0*100):null;
  const totChg=(first.total)?((last.total-first.total)/first.total*100):null;
  const ev=(d.ytd&&d.ytd.ev_only_share_pct!=null)?d.ytd.ev_only_share_pct:null;
  const evYr=(d.ytd&&d.ytd.year_be)?be2ce(d.ytd.year_be):'';
  const pct=v=>(v==null)?'—':(v<0?'−':'+')+Math.abs(v).toFixed(0)+'%';
  // ---- answer-first verdict ----
  const vb=$('#btrend-verdict');
  if(vb){
    vb.className='verdict v-warn'; vb.style.display='block';
    vb.innerHTML=`<div class="verdict-line">🛻 <b>New-pickup registrations ${pkChg!=null?(pkChg<0?'fell '+Math.abs(pkChg).toFixed(0)+'%':'rose '+pkChg.toFixed(0)+'%'):'moved'}</b> ${be2ce(yrs[0])}→${be2ce(yrs[yrs.length-1])} — ${num(pk0)} → ${num(pk1)}${totChg!=null?`, far faster than the whole new-vehicle market (${pct(totChg)})`:''}.</div>`+
      `<div class="sub" style="margin-top:4px">The diesel pickup is AutoX's core auto-title collateral — a shrinking new-pickup stream means a <b>shrinking future used-pickup collateral pool</b>${ev!=null?`, while pure-EV take a rising <b>${ev}%</b> of new inflow (${evYr}), thinner and less-certain used values as they age into the pool`:''}. Counts ${TAG_M} DLT first registrations${ev!=null?` · EV share ${TAG_E}`:''}.</div>`;
  }
  // ---- note ----
  const note=$('#btrend-note');
  if(note) note.innerHTML='First registrations (new vehicles entering the fleet) by class — the <b>inflow that becomes tomorrow’s used-vehicle collateral</b>. '+
    'Pickups are AutoX’s core title collateral — <b>31.3% of accounts and 38.3% of outstanding</b> in the measured loan tape, the largest single balance exposure in the book; passenger cars and the all-class total (incl. motorcycles) are shown alongside. '+
    'All counts are <b>measured</b> (DLT first-registration registry). Years are Buddhist-era (พ.ศ. − 543 = ค.ศ., e.g. 2568 = 2025).';
  // ---- per-year table (pickup bar-scaled to its own max) ----
  const tbl=$('#btrendtbl');
  if(tbl){
    const pkMax=Math.max(...yrs.map(y=>t[y].pickup||0),1);
    tbl.innerHTML=`<tr><th>Year</th><th title="MEASURED — DLT first registrations, pickup trucks (รย.3): AutoX’s core title collateral">Pickup titles ◆</th><th title="MEASURED — DLT first registrations, passenger cars">Passenger cars ◆</th><th title="MEASURED — DLT first registrations, all vehicle classes incl. motorcycles">All new regis ◆</th></tr>`+
      yrs.map((y,i)=>{
        const r=t[y], w=Math.round((r.pickup||0)/pkMax*100);
        const prev=i>0?t[yrs[i-1]].pickup:null;
        const yoy=(prev)?((r.pickup-prev)/prev*100):null;
        const yoyTxt=yoy!=null?` <span class="mono sub" style="color:${yoy<0?'var(--agri)':'var(--merch)'}">${pct(yoy)}</span>`:'';
        return `<tr><td class="mono">${be2ce(y)}<span class="sub"> · ${y}</span></td>`+
          `<td>${barHTML(w,'var(--collat)')} <span class="mono">${num(r.pickup)}</span>${yoyTxt}</td>`+
          `<td class="mono sub">${num(r.passenger)}</td>`+
          `<td class="mono sub">${num(r.total)}</td></tr>`;
      }).join('');
  }
  wrap.style.display='';
}

// Regional household-debt backdrop card (Overview, obj #1) — MEASURED Bank of Thailand regional letters
// over NSO SES. Leads with the national debt-to-GDP macro headline, then the 4-region debt-per-household
// cut at the most recent COMMON vintage (SES 2566/2023) sorted heaviest-first — the borrower-leverage
// backdrop behind the book. The layer carries mixed 2009–2023 vintages per series, so we pick one clean
// comparable cut and flag the rest ("read direction, not decimals"). Null-safe: no clean region rows at
// the common vintage → the whole block stays hidden (nothing fabricated).
function renderRegionDebt(){
  const wrap=$('#regdebt-wrap'); if(!wrap) return;
  // The BIS/BoT reconciliation line below needs MACROIND, which loads on its own promise. Without
  // this, whichever layer lost the race silently dropped the reconciliation — the exact failure the
  // line exists to prevent. Load-then-re-render once; loadMacroIndicators() is promise-cached, so
  // this costs one extra call at most and cannot loop.
  if(!MACROIND&&!macroIndDone){ loadMacroIndicators().then(renderRegionDebt); }
  const S=REGDEBT||{};
  const money=v=>(v==null||!isFinite(v))?'—':'฿'+Math.round(v).toLocaleString('en-US');
  // 4-region debt-per-household at the most recent common vintage (SES 2566/2023); dedup by region.
  const reg=(Array.isArray(S.region)?S.region:[]).filter(r=>r&&r.indicator==='debt_per_household_thb'&&/2566/.test(r.vintage||'')&&r.value!=null);
  const byGeo={}; reg.forEach(r=>{ byGeo[r.geo]=r; });
  const rows=Object.values(byGeo).sort((a,b)=>(b.value||0)-(a.value||0));
  if(!rows.length){ wrap.style.display='none'; return; }
  const TH_REG={North:'ภาคเหนือ',Northeast:'ภาคอีสาน',Central:'ภาคกลาง',South:'ภาคใต้',Bangkok:'กรุงเทพฯ',East:'ภาคตะวันออก'};
  const nat=Array.isArray(S.national)?S.national:[];
  const natOne=ind=>{const c=nat.filter(r=>r&&r.indicator===ind&&r.value!=null); return c.length?c[c.length-1]:null;};
  const gdp=natOne('household_debt_to_gdp_pct'), cushion=natOne('financial_cushion_under_3mo_share_pct');
  // BoT's own province examples of the vulnerable-household share (Isan agri belt), if present.
  const prov=(Array.isArray(S.province)?S.province:[]).filter(r=>r&&r.indicator==='vulnerable_household_share_pct'&&r.value!=null).sort((a,b)=>(b.value||0)-(a.value||0));
  const max=rows[0].value||1, heaviest=rows[0];
  const vb=$('#regdebt-verdict');
  if(vb){
    vb.className='verdict v-warn'; vb.style.display='block';
    // TWO measured household-debt-to-GDP figures exist on this tab and used to sit ~400px apart with
    // no relationship stated: BIS 2025-Q4 = 87.5% (the answer band + the Bottom line) and BoT
    // Q2/2568 = 87.0% (here). Both are right; they are different compilers on different quarters,
    // and BIS's own series reads 87.2–87.5 across the same window, so the gap is definitional, not an
    // error in either. One number has to LEAD or the reader cannot tell which to quote — the band's
    // BIS figure leads because it is the newer vintage and carries the trend line, and this becomes
    // the named cross-check. Reconciled 2026-08-02 during the Macro audit.
    const bisHH=(typeof MACROIND==='object'&&MACROIND&&MACROIND.indicators)?MACROIND.indicators.household_debt_gdp:null;
    // One decimal on BOTH figures. 87.0 rendered as "87" next to a BIS "87.5" reads as a rounded
    // number being compared to a precise one, which is the kind of avoidable ambiguity that costs a
    // slide its credibility. The vintage string already contains its own parentheses — don't nest.
    const hh1=v=>(v==null||!isFinite(v))?'—':Number(v).toFixed(1);
    const vint=s=>String(s||'').replace(/^\((.*)\)$/,'$1');
    vb.innerHTML=`<div class="verdict-line">📉 <b>Household leverage is the macro backdrop under portfolio risk${gdp?`: BoT puts household debt at ${hh1(gdp.value)}% of GDP`:''}${gdp?` · ${vint(gdp.vintage)}`:''}.</b> `+
      `Regionally the heaviest household debt sits in <b>${TH_REG[heaviest.geo]||heaviest.geo}</b> at ${money(heaviest.value)}/household (SES 2023)</div>`+
      `<div class="sub" style="margin-top:4px">${cushion?`~${cushion.value}% of Thai households hold under 3 months' financial cushion · ${vint(cushion.vintage)}. `:''}`+
      `Where households already carry the most debt, an income shock bites soonest — the leverage floor beneath the agri-PD / title book. ${TAG_M}.</div>`+
      (bisHH&&gdp&&bisHH.value!=null&&bisHH.value!==gdp.value
        ? `<div class="sub" style="margin-top:4px">Reconciling the two figures on this tab: the headline band quotes <b>${hh1(bisHH.value)}% — BIS, ${bisHH.period}</b>; this line quotes <b>${hh1(gdp.value)}% — BoT, ${vint(gdp.vintage)}</b>. Different compilers on different quarters of the same concept — <b>lead with the BIS figure</b> (newer vintage, and the one carrying the trend), and treat BoT's as the domestic cross-check. The ${Math.abs(bisHH.value-gdp.value).toFixed(1)}pp gap is definitional, not a discrepancy; both point down.</div>`
        : '');
  }
  const note=$('#regdebt-note');
  if(note) note.innerHTML='<b>Measured</b> — Bank of Thailand regional letters over NSO Socio-Economic Survey (SES) data. '+
    'BoT publishes no routine province table, so <b>region is the honest grain</b>; the debt-per-household cut below is the '+
    'most recent <b>common</b> vintage (SES 2566 / 2023). Other series in this layer carry mixed 2009–2023 vintages, so '+
    '<b>read direction, not decimals</b>.'+
    (prov.length?` BoT's own province examples put the <b>vulnerable-household share</b> highest in the Isan agri belt — ${prov.slice(0,3).map(p=>`${p.geo} ${p.value}%`).join(', ')} (2019), exactly where the agri-PD book sits.`:'');
  const tbl=$('#regdebttbl');
  if(tbl) tbl.innerHTML=`<tr><th>#</th><th>Region</th><th title="MEASURED — average debt per household, NSO SES 2566 (2023), carried in BoT regional letters">Debt / household ◆</th></tr>`+
    rows.map((r,i)=>{const v=r.value||0; const c=v>=200000?'var(--agri)':v>=180000?'var(--gold)':'var(--merch)';
      return `<tr><td class="mono sub">${i+1}</td><td><b>${TH_REG[r.geo]||r.geo}</b></td>`+
        `<td>${barHTML(Math.round(100*v/max),c)} <span class="mono" style="color:${c}">${money(v)}</span></td></tr>`;}).join('');
  wrap.style.display='';
}

// Logistics-SME pulse card (Overview, obj #1) — MEASURED DLT truck-registration flow. Nationally the
// fleet is still growing (new registrations outrunning deregistrations), so the card leads with that
// cushion, then names the province pockets where new-truck DEMAND is contracting YoY — the sharpest
// segment-stress read the layer carries, and the intended sort ("worst-first by new_regis_yoy_pct").
// A modest base floor (≥250 new/12m) drops small-sample YoY noise; net fleet flow + used-market
// transfers carried alongside. Null-safe: no rows → the whole block stays hidden (nothing fabricated).
/* RETIRED 2026-08-02 — renderTruckFlow + renderCollateralFlow. Owner, points 18 and 19: both belong
   in the collateral section, and they are there now. Trucks are ฿1.84bn of our own book — a collateral
   class, not a business-backdrop curiosity — so the truck flow is a per-province column on the
   collateral drill and a row in the mix. The used-vehicle flow is the resale-market table at the foot
   of the same block. Point 18 also asked whether the flow exists for other vehicle classes: it does
   (car, pickup, motorcycle) but DLT publishes that one by registration office, so it is REGION grain
   while the truck flow is per province — both are labelled with their grain rather than blended. */

function renderDbdForm(){
  const wrap=$('#dbdform-wrap'); if(!wrap) return;
  const bp=(DBDFORM&&DBDFORM.by_province&&typeof DBDFORM.by_province==='object')?DBDFORM.by_province:null;
  // top rows: prefer the layer's own pre-sorted `top` ([prov,n,capital]); else derive from by_province.
  let rows=Array.isArray(DBDFORM&&DBDFORM.top)?DBDFORM.top.map(t=>({th:t[0],n:t[1],cap:t[2]})):
    (bp?Object.entries(bp).map(([k,v])=>({th:k,n:v.n||0,cap:v.capital_thb||0})).sort((a,b)=>b.n-a.n):[]);
  rows=rows.filter(r=>r&&r.th&&r.n>0);
  if(!rows.length){ wrap.style.display='none'; return; }
  const m=DBDFORM_META||{};
  // national totals — prefer the layer's own meta rollup, else sum the province rows.
  const natN=(typeof m.n_registrations==='number')?m.n_registrations:rows.reduce((s,r)=>s+(r.n||0),0);
  const natCap=(typeof m.capital_thb_total==='number')?m.capital_thb_total:rows.reduce((s,r)=>s+(r.cap||0),0);
  const nProv=(typeof m.n_provinces_present==='number')?m.n_provinces_present:Object.keys(bp||{}).length;
  const num=v=>(v==null||!isFinite(v))?'—':Math.round(v).toLocaleString('en-US');
  // compact ฿ formatter — bn / m.
  const baht=v=>{ if(v==null||!isFinite(v)||v<=0) return '—';
    if(v>=1e9) return '฿'+(v/1e9).toFixed(1)+'bn'; if(v>=1e6) return '฿'+Math.round(v/1e6)+'m'; return '฿'+Math.round(v/1e3)+'k'; };
  // concentration read (computed client-side from the measured rows) — Bangkok share + top-5 share.
  const bkk=bp&&bp['กรุงเทพมหานคร']?(bp['กรุงเทพมหานคร'].n||0):(rows.find(r=>r.th==='กรุงเทพมหานคร')||{}).n||0;
  const bkkShare=natN>0?bkk/natN*100:0;
  const top5=rows.slice(0,5).reduce((s,r)=>s+(r.n||0),0);
  const top5Share=natN>0?top5/natN*100:0;
  const vintage=m.snapshot_month_be?`${m.snapshot_month_be} (${m.vintage||m.snapshot_month||''})`:(m.snapshot_month||'—');
  const vb=$('#dbdform-verdict');
  if(vb){
    vb.className='verdict'; vb.style.display='block';
    vb.innerHTML=`<div class="verdict-line">🏢 <b>${num(natN)} new businesses formed nationwide in the ${m.snapshot_month||''} snapshot — ${baht(natCap)} registered capital, across ${num(nProv)} provinces.</b> `+
      `This is the small-business borrower base the merchant / small-ticket book draws on.</div>`+
      `<div class="sub" style="margin-top:4px">Formation is <b>heavily Bangkok-weighted</b> — กรุงเทพฯ alone is <b>${bkkShare.toFixed(0)}%</b> of new firms and the top-5 provinces <b>${top5Share.toFixed(0)}%</b>, so upcountry business formation (where AutoX's provincial book sits) is thin and concentrated. A demand backdrop, not a stress. ${TAG_M}.</div>`;
  }
  const note=$('#dbdform-note');
  if(note) note.innerHTML='<b>Measured</b> — DBD (Department of Business Development) monthly new juristic-person registrations for the '+
    `<b>${vintage}</b> snapshot, tallied by the registry's own head-office province. `+
    'This is <b>one month’s formation flow</b> (a pulse), <b>not</b> a stock of active firms and <b>not</b> annualised; '+
    'registered capital is <b>authorised at incorporation</b> (overstates deployed capital, skewed by a few large filings). '+
    'A merchant-demand / economic-vitality backdrop for the existing footprint — it makes <b>no</b> open / close / expand call.';
  const tbl=$('#dbdformtbl');
  if(tbl) tbl.innerHTML=`<tr><th>#</th><th>Province</th><th title="MEASURED — new juristic-person registrations in the snapshot month">New firms ●</th><th title="share of the national monthly total">Share</th><th title="MEASURED — registered (authorised) capital at incorporation, snapshot month">Reg. capital ●</th></tr>`+
    rows.slice(0,12).map((r,i)=>{ const sh=natN>0?r.n/natN*100:0;
      const c=sh>=15?'var(--merch)':sh>=3?'var(--gold)':'var(--dim)';
      return `<tr><td class="mono sub">${i+1}</td><td><b>${r.th}</b></td>`+
        `<td class="mono">${num(r.n)}</td>`+
        `<td class="mono" style="color:${c}">${sh.toFixed(1)}%</td>`+
        `<td class="mono sub">${baht(r.cap)}</td></tr>`;}).join('');
  wrap.style.display='';
}

// MEASURED SFI system credit-quality backdrop. A national quarterly time-series (not per-province):
// the last ~8 quarters of the state-bank system gross NPL ratio + a 5y peak/trough marker, with a
// verdict on the current level and its YoY direction. Requires the layer + a latest quarter; if absent
// the whole block stays hidden (nothing partial, nothing faked).
function renderSfi(){
  const wrap=$('#sfi-wrap'); if(!wrap) return;
  const m=SFI_META||{}, lt=m.latest;
  if(!SFI || !lt || lt.npl_ratio==null){ wrap.style.display='none'; return; }
  const pp=v=>(v==null||!isFinite(v))?'—':(v>0?'+':'')+v.toFixed(2)+'pp';
  const rat=v=>(v==null||!isFinite(v))?'—':v.toFixed(2)+'%';
  const yoy=m.yoy_ratio_delta_pp, qoq=m.qoq_ratio_delta_pp;
  // direction colour: rising NPL = risk-red, easing = merchant-teal, flat = dim.
  const dirC=(yoy==null)?'var(--dim)':(yoy>0.05?'var(--agri)':(yoy<-0.05?'var(--merch)':'var(--dim)'));
  const dirW=(yoy==null)?'flat':(yoy>0.05?'rising':(yoy<-0.05?'easing':'roughly flat'));
  const peak=m.peak_ratio_5y, trough=m.trough_ratio_5y;
  const vb=$('#sfi-verdict');
  if(vb){
    vb.className='verdict'; vb.style.display='block';
    vb.innerHTML=`<div class="verdict-line">🏦 <b>State-bank system NPL ratio is <span style="color:${dirC}">${rat(lt.npl_ratio)}</span> at ${lt.period} — ${dirW} <span style="color:${dirC}">${pp(yoy)}</span> year-on-year.</b> `+
      `This is the closest public read on the household + farm repayment stress AutoX's borrowers sit inside.</div>`+
      `<div class="sub" style="margin-top:4px">The Specialized Financial Institutions (GSB household, BAAC rural/agri, GHB housing …) carry a ฿${(lt.credit_gross/1e6).toFixed(2)}tn book; ${(lt.npl_gross/1e3).toFixed(0)}bn is non-performing.`+
      (peak?` Over the last 5 years the ratio ran between <b>${rat(trough&&trough.npl_ratio)}</b> (${trough&&trough.period}) and a <b>${rat(peak.npl_ratio)}</b> peak (${peak.period}).`:'')+
      ` A macro backdrop / direction signal — <b>not</b> AutoX's own NPL and <b>not</b> per-province. ${TAG_M}.</div>`;
  }
  const note=$('#sfi-note');
  if(note) note.innerHTML='<b>Measured</b> — FPO (Fiscal Policy Office) quarterly aggregates for Thailand’s '+
    'Specialized Financial Institutions: gross NPL outstanding ÷ gross credit outstanding. A national '+
    '<b>system</b> figure for all state-owned banks combined — <b>not</b> AutoX, <b>not</b> the non-bank '+
    'title-lender sector, and <b>not</b> split by institution or province. SFI books skew to '+
    'policy/subsidised lending, so read the <b>direction / trend</b>, not the level; the useful signal is '+
    'that a rising state-bank NPL tide tends to lead broad household + agri repayment stress. A slow '+
    'structural backdrop (the flood/rain card is the acute counterpart) — it makes <b>no</b> branch call.';
  const tbl=$('#sfitbl');
  if(tbl){
    const last=SFI.slice(-8);
    const maxR=Math.max(...last.map(r=>r.npl_ratio||0),0.01);
    tbl.innerHTML=`<tr><th>Quarter</th><th title="MEASURED — gross NPL outstanding ÷ gross credit outstanding for the SFI system">System NPL ratio ●</th><th title="MEASURED — gross NPL outstanding, THB billion">NPL (฿bn) ●</th><th>Trend</th></tr>`+
      last.map((r,i)=>{ const prev=i>0?last[i-1].npl_ratio:null;
        const d=(prev!=null&&r.npl_ratio!=null)?r.npl_ratio-prev:null;
        const dC=(d==null)?'var(--dim)':(d>0.02?'var(--agri)':(d<-0.02?'var(--merch)':'var(--dim)'));
        const arrow=(d==null)?'·':(d>0.02?'▲':(d<-0.02?'▼':'▬'));
        const w=Math.round((r.npl_ratio||0)/maxR*100);
        const isLast=i===last.length-1;
        return `<tr><td class="mono${isLast?'':' sub'}">${isLast?'<b>'+r.period+'</b>':r.period}</td>`+
          `<td class="mono"><span style="display:inline-block;height:7px;width:${w}px;background:var(--agri);opacity:.5;vertical-align:middle;margin-right:6px;border-radius:2px"></span>${rat(r.npl_ratio)}</td>`+
          `<td class="mono sub">${((r.npl_gross||0)/1e3).toFixed(0)}</td>`+
          `<td class="mono" style="color:${dC}">${arrow} ${d==null?'—':pp(d)}</td></tr>`;}).join('');
  }
  wrap.style.display='';
}

// MEASURED live flood + rain pulse (ThaiWater telemetry). Two per-province station aggregates rendered
// side by side: river/reservoir water LEVEL (flood) and 24h RAINFALL. Requires BOTH layers; if either is
// absent the whole block stays hidden (nothing partial, nothing faked).
function renderThaiwater(){
  const wrap=$('#thaiwater-wrap'); if(!wrap) return;
  if(!TWFLOOD || !TWRAIN){ wrap.style.display='none'; return; }
  const num=v=>(v==null||!isFinite(v))?'—':Math.round(v).toLocaleString('en-US');
  const pct=v=>(v==null||!isFinite(v))?'—':(v>=10?Math.round(v):v.toFixed(0))+'%';
  // flood rows: worst first (highest situation_level, then share of stations high).
  const fRows=Object.entries(TWFLOOD).map(([th,v])=>({th,...v}))
    .sort((a,b)=>(b.max_level-a.max_level)||(b.pct_high-a.pct_high)||(b.n_high-a.n_high));
  const fHigh=fRows.filter(r=>r.max_level>=4);          // provinces with any high-water/overflow station
  const fShow=(fHigh.length?fHigh:fRows).slice(0,10);
  // rain rows: wettest first by max 24h mm; keep those over the Thai-Met "heavy" threshold.
  const rRows=Object.entries(TWRAIN).map(([th,v])=>({th,...v}))
    .sort((a,b)=>(b.max_mm||0)-(a.max_mm||0));
  const rHeavy=rRows.filter(r=>(r.max_mm||0)>=35.1);
  const rShow=(rHeavy.length?rHeavy:rRows).slice(0,10);
  const fm=TWFLOOD_META||{}, rm=TWRAIN_META||{};
  const worstF=fRows[0], worstR=rRows[0];
  const obs=fm.observed_to||rm.observed_to||fm.pulled||'—';
  const vb=$('#thaiwater-verdict');
  if(vb){
    vb.className='verdict v-warn'; vb.style.display='block';
    const fLine=worstF&&worstF.max_level>=4
      ? `<b>${fHigh.length}</b> province${fHigh.length===1?'':'s'} have river/reservoir stations at high water (level ≥4) — worst is <b>${worstF.th}</b> (${num(worstF.n_high)}/${num(worstF.n_stations)} stations${worstF.max_level>=5?', at bank overflow':''} high).`
      : `No province currently shows a station at high water (level ≥4) — the highest is <b>${worstF?worstF.th:'—'}</b> at level ${worstF?worstF.max_level:'—'}.`;
    const rLine=worstR?`Heaviest 24h rain: <b>${worstR.th}</b> at <b>${num(worstR.max_mm)}mm</b> (${pct(worstR.pct_very_heavy)} of its stations very heavy).`:'';
    vb.innerHTML=`<div class="verdict-line">🌊 ${fLine} ${rLine}</div>`+
      `<div class="sub" style="margin-top:4px">Water on the ground / arriving is an <b>acute</b> collections + collateral event, days before it reaches any monthly series — the fast counterpart to the crop-stress drought read above. Live snapshot, observed to <b>${obs}</b>. ${TAG_M}.</div>`;
  }
  const note=$('#thaiwater-note');
  if(note) note.innerHTML='<b>Measured</b> — live per-province station aggregates from <b>ThaiWater</b> ('+
    'RID/DWR/TMD/EGAT telemetry, keyless). <b>Left:</b> river/reservoir <b>water level</b> — situation_level '+
    '1 (critical low) → 3 (normal) → 4 (high water) → 5 (bank overflow); n_high counts stations at level ≥4. '+
    '<b>Right:</b> <b>24h rainfall</b> — heavy ≥35.1mm, very heavy ≥90.1mm (Thai Met convention). '+
    'This is a <b>live snapshot</b> of the sampled station network, <b>not</b> a disaster declaration and <b>not</b> a '+
    'catchment-weighted flood model — an acute early read on where borrower income and collections are exposed now.';
  const ft=$('#thaiwater-flood-tbl');
  if(ft) ft.innerHTML=`<tr><th colspan="4" style="color:var(--accent)">Water on the ground · river/reservoir level ●</th></tr>`+
    `<tr><th>#</th><th>Province</th><th title="MEASURED — stations at situation_level ≥4 (high water / overflow) of the province's sampled stations">Stations high ●</th><th title="worst situation_level in the province (5 = bank overflow flood)">Worst level ●</th></tr>`+
    (fShow.length?fShow.map((r,i)=>{ const c=r.max_level>=5?'var(--agri)':r.max_level>=4?'var(--gold)':'var(--dim)';
      return `<tr><td class="mono sub">${i+1}</td><td><b>${r.th}</b></td>`+
        `<td class="mono">${num(r.n_high)}<span class="sub">/${num(r.n_stations)}</span> <span style="color:${c}">${pct(r.pct_high)}</span></td>`+
        `<td class="mono" style="color:${c}">L${r.max_level}${r.max_level>=5?' ⚠':''}</td></tr>`;}).join('')
      :`<tr><td colspan="4" class="sub">No station at high water in the current snapshot.</td></tr>`);
  const rt=$('#thaiwater-rain-tbl');
  if(rt) rt.innerHTML=`<tr><th colspan="4" style="color:var(--accent)">Rain arriving · 24h rainfall ●</th></tr>`+
    `<tr><th>#</th><th>Province</th><th title="MEASURED — highest 24h rainfall at any station in the province">Max 24h ●</th><th title="share of the province's stations over the heavy threshold (≥35.1mm/24h)">Stations heavy ●</th></tr>`+
    (rShow.length?rShow.map((r,i)=>{ const mm=r.max_mm||0; const c=mm>=90.1?'var(--agri)':mm>=35.1?'var(--gold)':'var(--dim)';
      return `<tr><td class="mono sub">${i+1}</td><td><b>${r.th}</b></td>`+
        `<td class="mono" style="color:${c}">${num(mm)}mm</td>`+
        `<td class="mono">${pct(r.pct_heavy)}</td></tr>`;}).join('')
      :`<tr><td colspan="4" class="sub">No heavy-rain station in the current snapshot.</td></tr>`);
  wrap.style.display='';
}

/* ---------- acquisition ---------- */
/* MEASURED household debt inside vs outside the formal system (data/debt_source.json, NSO).
   The point of the block is the CLASS table, not the national number: informal borrowing barely
   varies by region (1.3-1.5%) but varies 5x by occupation, and the two most exposed classes are
   exactly the ones this book lends to. Leads with that, and carries the under-reporting caveat
   next to the number rather than in a footnote, because the level is a floor and the ranking
   is the only defensible read. */
function renderDebtSource(){
  const host=document.getElementById('acq-debtsource'); if(!host) return;
  tmliFetch('debt_source').then(j=>{
    if(!j||!Array.isArray(j.by_class)){ tmliNote(host,'Needs <b>data/debt_source.json</b> — not built for this vintage.'); return; }
    const M=j.meta||{}, nat=j.national||[], B=n=>'฿'+Math.round(n).toLocaleString();
    const n0=nat[0]||{}, n1=nat[nat.length-1]||{};
    const cls=(j.by_class||[]).filter(r=>r.cls!=='รวม');
    const top=cls[0]||{};
    const all=(j.by_class||[]).find(r=>r.cls==='รวม')||n1;
    const mult=all.informal_pct?(top.informal_pct/all.informal_pct):null;
    const maxInf=Math.max(...cls.map(r=>r.informal_pct||0),1);
    const rows=cls.map(r=>{
      const w=Math.max((r.informal_pct||0)/maxInf*90,1);
      return `<tr><td><b>${r.cls_en}</b></td>
        <td class="mono">${B(r.total)}</td>
        <td class="mono">${B(r.informal)}</td>
        <td><span class="mono" style="color:${(r.informal_pct||0)>=3?'var(--agri)':'var(--dim)'}"><b>${r.informal_pct}%</b></span>
          <svg width="92" height="9" viewBox="0 0 92 9" aria-hidden="true" style="vertical-align:middle;margin-left:6px"><rect x="0" y="1" width="${w.toFixed(1)}" height="7" rx="1.5" fill="${(r.informal_pct||0)>=3?'var(--agri)':'var(--line)'}"/></svg></td>
        <td class="mono sub">${r.agri_pct==null?'—':r.agri_pct+'%'}</td></tr>`;}).join('');
    const regs=(j.by_region||[]).map(r=>`<tr><td><b>${r.region_en}</b></td>
        <td class="mono">${B(r.total)}</td><td class="mono sub">${B(r.informal)}</td>
        <td class="mono">${r.informal_pct}%</td>
        <td class="sub mono">${(r.informal_series||[]).map(s=>s.informal_pct+'%').join(' → ')}</td></tr>`).join('');
    host.innerHTML=`<p class="lead" style="margin:0 0 10px"><b>Informal debt is not a place, it is a job.</b> Nationally it is only <b>${n1.informal_pct}%</b> of the average household's debt and it has <b>shrunk</b> from ${n0.informal_pct}% in ${n0.year_ce} to ${n1.informal_pct}% in ${n1.year_ce}. But it barely moves between regions (${(j.by_region||[]).length?Math.min(...j.by_region.map(r=>r.informal_pct))+'–'+Math.max(...j.by_region.map(r=>r.informal_pct))+'%':'—'}) and varies <b>${mult?mult.toFixed(1)+'×':''}</b> between occupations — the most exposed being <b style="color:var(--agri)">${top.cls_en} at ${top.informal_pct}%</b>, which is squarely this book's borrower.</p>
      <div class="cb-gap cb-assist" style="margin:0 0 10px"><b>Read the level as a floor.</b> ${M.under_reporting_caveat||''}</div>
      <table class="tbl"><tr><th>Household type (NSO class)</th><th>Debt / household</th><th>Outside the system</th><th>Share outside</th><th class="sub" title="share of that household's debt borrowed for farming">For farming</th></tr>${rows}</table>
      <details style="margin-top:10px"><summary class="sub">By region — and how the informal share moved across the seven survey waves</summary>
        <table class="tbl" style="margin-top:8px"><tr><th>Region</th><th>Debt / household</th><th class="sub">Outside</th><th>Share</th><th class="sub">${(nat||[]).map(x=>x.year_ce).join(' → ')}</th></tr>${regs}</table></details>
      <p class="lead sub" style="margin:8px 0 0"><b>Reading:</b> ${M.scope_warning||''} ${M.label||''}</p>`;
    wrapTables();
  });
}

function renderCompetition(){
  $('#estates').innerHTML = `<tr><th>AutoX ≤10km</th><th>Industrial estate</th></tr>`+
    META.estates.map(s=>{const c=s.own<=3?'#E0474B':s.own<=6?'var(--gold)':'#2BB673';const t=s.own<=3?'white space':s.own<=6?'thin':'covered';
      return `<tr><td><span class="tag" style="color:${c};border:1px solid ${c}">${s.own} · ${t}</span></td><td>${s.name}</td></tr>`;}).join('');
  $('#mws').innerHTML = `<tr><th>Demand</th><th>AutoX</th><th>Fresh mkts</th><th>Province</th><th>Branch</th></tr>`+
    META.mws.map(m=>`<tr><td class="mono" style="color:var(--merch)">${m.md}</td><td class="mono">${m.own}</td><td class="mono">${m.fmkt}</td><td>${m.v}</td><td class="sub">${m.n}</td></tr>`).join('');
  $('#cws').innerHTML = `<tr><th>Collat</th><th>Vehicle</th><th>Gold</th><th>AutoX</th><th>Province</th><th>Branch</th></tr>`+
    META.cws.map(c=>`<tr><td class="mono" style="color:var(--collat)">${c.c}</td><td class="mono">${c.veh}</td><td class="mono">${c.gold}</td><td class="mono">${c.own}</td><td>${c.v}</td><td class="sub">${c.n}</td></tr>`).join('');
  renderGapBoard();
  renderSearchDemand();
  renderPeerScore();
  renderDebtSource();
  // ONE call paints both sentiment ladders. renderRivalIos() used to sit here as a second line, but it
  // was a bare alias for renderRivalPulse() — the fetch resolves once and paintPulse() draws Play and
  // iOS together, so the second call only re-entered the same guarded loader. It read like a separate
  // data path in every review of this file. Removed 2026-07-31.
  renderRivalPulse();
  renderRivalAds();
  renderRivalVideo();
  renderPantip();
  renderSocialThemes();
  renderRivalUniverse();
  renderCompCoverage();
  renderRivalDensity();
  renderPeerProvince();
  renderPeerNpl();
  renderRivRep();
  renderRivThreat();
  renderRivThreatRegion();
  renderPicoCompetitors();
  renderExitWhitespace();
  // Strategy pivot — the network is consolidating, not growing. The former branch-growth surfaces
  // (Road-to-3,000 headroom split, sequenced expansion plan, "where to open next" opportunity board)
  // and their CSV exports have been REMOVED from this file entirely. The scope is competitive risk on
  // the existing footprint; nothing here recommends where to open branches.
}

/* ---------- Where demand searches · title-loan search interest by province (obj #2) ----------
   Surfaces data/search_demand.json (built by pipeline/build_search_demand.py from the committed
   google_trends.json snapshot): per-province ESTIMATED search-demand index (0–100) + brand
   share-of-search. Answer-first readout + top-12 board. Lazy, promise-cached, graceful if absent. */
const SEARCH_TOPN=12;
function renderSearchDemand(){
  const tbl=$('#searchtbl'); if(!tbl) return;
  if(sdemandLoaded){ drawSearchDemand(); return; }
  loadSearchDemand().then(drawSearchDemand).catch(drawSearchDemand);
}
function drawSearchDemand(){
  const tbl=$('#searchtbl'), ro=$('#searchreadout'); if(!tbl) return;
  const rows=(SDEMAND_LIST&&SDEMAND_LIST.length)?SDEMAND_LIST:[];
  if(!rows.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Search-demand board not yet computed.</b> <span class="sub">Run pipeline/build_search_demand.py — it fills in on the next data refresh.</span>';
    return;
  }
  const pct=v=>(v==null?'<span class="sub">n/a</span>':`${Math.round(100*v)}%`);
  // AutoX = gold accent; rivals = merchant teal — both are theme-token colors (contrast-safe in light+dark).
  const AX='var(--gold)', RV='var(--merch)';
  const list=rows.slice(0,SEARCH_TOPN);
  tbl.innerHTML=`<tr><th scope="col">#</th><th scope="col">Province</th>`+
    `<th scope="col" title="Google Trends relative search-interest (0–100) for title-loan intent terms — ESTIMATED, a demand signal, not query volume">Demand ▲ est</th>`+
    `<th scope="col" title="AutoX (เงินไชโย) share of the five brands' search interest in this province — ESTIMATED">AutoX share-of-search</th>`+
    `<th scope="col" title="strongest rival brand by share-of-search in this province">Best rival</th></tr>`+
    list.map((r,i)=>{
      const dem=r.demand==null?0:r.demand;
      const ash=r.autox_share;
      const best=r.best_rival;
      const rank=r.autox_sos_rank!=null?`<span class="sub" title="province rank by AutoX share-of-search (1 = strongest)">#${r.autox_sos_rank} nat'l</span>`:'';
      const ashtxt=(ash==null)?'<span class="sub">n/a</span>'
        :`<span class="mono" style="color:${AX}"><b>${pct(ash)}</b></span> ${barHTML(100*ash,AX)}`;
      const btxt=best?`<span style="color:${RV}">${best.brand}</span> <span class="mono" style="color:${RV}">${pct(best.share)}</span>`:'<span class="sub">n/a</span>';
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td><b>${r.th}</b> <span class="sub">${r.en||''}</span></td>
        <td><span class="mono" style="color:${AX}">${dem.toFixed(0)}</span> ${barHTML(dem,AX)}</td>
        <td>${ashtxt} ${rank}</td>
        <td>${btxt}</td>
      </tr>`;}).join('');
  if(ro){
    const top=rows[0];
    const m=SDEMAND_META||{};
    // answer-first line: the hottest-searching province + whether AutoX or a rival owns share there.
    let verdict='';
    if(top){
      const ash=top.autox_share, best=top.best_rival;
      if(ash!=null&&best){
        const own=ash>=best.share;
        verdict=own
          ? `<b style="color:var(--gold)">${top.th}</b> searches title-loan intent hardest (demand <b>${Math.round(top.demand)}</b>/100) — and <b style="color:var(--gold)">AutoX leads share-of-search there</b> (${Math.round(100*ash)}% vs ${best.brand} ${Math.round(100*best.share)}%).`
          : `<b style="color:var(--gold)">${top.th}</b> searches title-loan intent hardest (demand <b>${Math.round(top.demand)}</b>/100) — but <b style="color:var(--merch)">${best.brand} owns share-of-search there</b> (${Math.round(100*best.share)}% vs AutoX ${Math.round(100*ash)}%). High demand + weak brand = a competitive soft spot where a rival leads brand demand.`;
      }else{
        verdict=`<b style="color:var(--gold)">${top.th}</b> searches title-loan intent hardest (demand <b>${Math.round(top.demand)}</b>/100).`;
      }
    }
    // where does AutoX brand search actually lead? count provinces where AutoX SoS rank is 1..N and it beats every rival.
    const axLead=rows.filter(r=>r.best_rival&&r.autox_share!=null&&r.autox_share>=r.best_rival.share).length;
    ro.innerHTML=`<b>Brand vs rival search:</b> ${verdict} `+
      `AutoX out-searches every rival brand in <b>${axLead}</b> of ${rows.length} provinces. ${TAG_E}`+
      methodBox(null,
        ['<b>Demand</b> = mean of two Google Trends title-loan intent terms per province (relative 0–100 index, <b>ESTIMATED</b> — a demand/attention signal, NOT query volume or bookings).',
         '<b>Share-of-search</b> = a brand’s search interest ÷ the five brands’ total in that province. The five brands share one Trends payload axis, so the split is meaningful; it is a demand proxy, <b>not</b> market share.',
         'Low-search-volume provinces are noisy — read the leaderboard as direction, not precise magnitude.',
         (m.pulled_at_utc?`Snapshot pulled ${m.pulled_at_utc} · ${m.source||'Google Trends'}.`:'Source: Google Trends (geo=TH).')]);
  }
}

/* ---------- Competitor coverage (lower bound) · found vs expected (obj #2) ----------
   Surfaces data/competitor_coverage.json (built by pipeline/build_competitor_coverage.py):
   per brand {found (MEASURED census count), expected (ESTIMATED-from-public-reports, cited),
   coverage_pct}. Makes the census UNDERCOUNT explicit and honest. Lazy-loaded once; degrades
   gracefully (calm notice) when the file is absent. We DO NOT compute anything here. */
let COMPCOV=null, compcovLoaded=false, compcovPromise=null;
// promise-cached loader so the Home command center can read the national coverage % without
// duplicating the fetch the Overview table already issues. Null-safe; never throws.
function loadCompCoverage(){
  if(compcovPromise) return compcovPromise;
  compcovPromise=fetch('data/competitor_coverage.json').then(r=>r.ok?r.json():null)
    .then(j=>{COMPCOV=j||null;compcovLoaded=true;return COMPCOV;})
    .catch(()=>{COMPCOV=null;compcovLoaded=true;return null;});
  return compcovPromise;
}
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
    if(ro) ro.innerHTML='<b>Competitor coverage not yet computed.</b> <span class="sub">This layer is being prepared — it fills in once the competitor census refresh lands.</span>';
    return;
  }
  // sort by coverage_pct desc (nulls last) so the best-covered brand leads.
  const list=rows.slice().sort((a,b)=>((b.coverage_pct==null?-1:b.coverage_pct)-(a.coverage_pct==null?-1:a.coverage_pct)));
  tbl.innerHTML=`<tr><th scope="col">Brand</th>`+
    `<th scope="col" title="MEASURED — locations of this brand in our de-duplicated census (a lower bound)">Found ◆ measured</th>`+
    `<th scope="col" title="ESTIMATED-from-public-reports — the brand's publicly-reported nationwide branch count (cited company IR / annual reports)">Expected ★ public</th>`+
    `<th scope="col" title="found ÷ expected — the share of the brand's reported network we have located so far. A confidence flag, NOT market share.">Coverage</th>`+
    `<th scope="col">Census completeness</th></tr>`+
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
      ? `We now hold <b style="color:var(--merch)">${(t.found||0).toLocaleString()}</b> measured rival branches vs an estimated <b style="color:var(--gold)">${(t.expected||0).toLocaleString()}</b> from public reports.`
      : `Found <b style="color:var(--merch)">${(t.found||0).toLocaleString()}</b> competitor locations.`;
    // national peer standing — where AutoX sits among the big-4 by branch-NETWORK size (obj #2).
    // AutoX size = MEASURED own network; peer size = REPORTED (cited IR). A footprint-scale read
    // that reframes the per-province density board; null-safe (older data has no block).
    const ns=m.national_standing;
    let nstxt='';
    if(ns&&ns.autox_rank&&Array.isArray(ns.ranking)){
      const ordLabel=n=>({1:'largest',2:'2nd-largest',3:'3rd-largest',4:'4th-largest',5:'5th-largest'}[n]||`#${n}`);
      const chain=ns.ranking.map(o=>`${o.operator==='AutoX'?'<b style="color:var(--accent)">AutoX</b>':o.operator} ${(o.branches||0).toLocaleString()}`).join(' &rsaquo; ');
      nstxt=`<div style="margin-top:6px"><b>Nationally, AutoX runs the ${ordLabel(ns.autox_rank)} title-loan branch network</b> `+
        `of the ${ns.n_ranked} big operators with a cited count: ${chain}. ${TAG_M} ${TAG_E} `+
        `<span class="sub">By network size — a different question from the per-province density board above, where rivals cluster and AutoX reads as a local 3rd.</span></div>`;
      // MEASURED-footprint reframe: rivals' full store-locator networks can outrank AutoX on
      // points-on-the-ground even when it leads on cited listed-entity counts. All-measured, null-safe.
      const fp=ns.footprint_measured;
      if(fp&&fp.autox_rank&&Array.isArray(fp.ranking)){
        const fchain=fp.ranking.map(o=>`${o.operator==='AutoX'?'<b style="color:var(--accent)">AutoX</b>':o.operator} ${(o.points||0).toLocaleString()}`).join(' &rsaquo; ');
        nstxt+=`<div style="margin-top:6px"><b>By MEASURED store-locator footprint AutoX is only ${ordLabel(fp.autox_rank)}</b> `+
          `of ${fp.n_ranked} — points on the ground: ${fchain}. ${TAG_M} `+
          `<span class="sub">Every number here is measured (own network + rivals' official locators); a locator counts a group's whole retail network, beyond its listed-entity IR count, so Srisawad's full footprint overtakes AutoX even though AutoX leads on cited branch count. Heng excluded (locator Cloudflare-blocked → lower bound).</span></div>`;
      }
    }
    ro.innerHTML=`<b>The census is now the near-complete rival network.</b> ${ttxt} ${TAG_M} ${TAG_E}${nstxt}`+
      methodBox(null,
        ['Muangthai, Srisawad &amp; Tidlor are pulled from each operator’s <b>official store-locator</b> (the full network) — coverage ~100%, and &gt;100% is expected because a locator lists every service point beyond the IR “branches” headline (SAWAD group ≈4.6× its listed-entity count).',
         'Heng is the one exception — still a Google/Overture <b>SAMPLE</b> (its locator is Cloudflare-blocked), so Heng alone is a lower bound.',
         'Coverage % is a data-completeness flag, <b>not</b> market share.',
         '<b>National standing</b> is read two ways. (1) By branch-network SIZE — AutoX = <b>MEASURED</b> own network; peers = <b>REPORTED</b> cited IR counts (Heng excluded, no cited count). (2) By MEASURED store-locator FOOTPRINT — all points on the ground, AutoX own network vs rivals’ official locators (Heng excluded, its locator is Cloudflare-blocked → lower bound). A locator counts a group’s whole retail network beyond its listed-entity IR figure, so the two rankings can differ — both true. Neither is market share, and both differ from the local per-province density read.']);
  }
}

/* ---------- where rivals own ground · districts where AutoX is outnumbered ----------
   Surfaces data/rival_density.json (928 districts, pipeline/build_rival_density.py): per-district
   AutoX vs the FULL official-locator rival census (16,393 measured branches), with a ceded-ground
   flag. Objective #2 — the actionable payoff of the full competitor pull. Lazy, graceful if absent. */
let RIVDEN=null, rivdenLoaded=false;
const RIVDEN_TOPN=20;
// Concentration of the RIVAL field in one district: which single big-4 brand holds the most of it,
// and its share of all rival branches there (AutoX excluded — by_brand is rivals only). MEASURED —
// a straight read of the committed per-brand census; nothing recomputed. agri when one brand owns a
// majority (single-brand-dominated — that one rival effectively sets the local terms AutoX competes
// against), gold when the field is fragmented across the big-4. The same competitive-risk texture the
// province peer board carries, one grain finer (obj #2). SUBSTANTIAL-field floor so a 1–2-branch field
// can't score a meaningless 100%.
const RIVDEN_CONC_MIN=10, RIVDEN_CONC_MAJ=0.5;
function rivFieldConc(bb){
  if(!bb||typeof bb!=='object') return null;
  const ent=Object.entries(bb).sort((a,b)=>(b[1]-a[1])||(a[0]<b[0]?-1:1));
  if(!ent.length) return null;
  const tot=ent.reduce((s,e)=>s+e[1],0);
  if(tot<RIVDEN_CONC_MIN) return null;
  return {brand:ent[0][0], cnt:ent[0][1], tot, share:ent[0][1]/tot, dominated:(ent[0][1]/tot)>=RIVDEN_CONC_MAJ};
}
function renderRivalDensity(){
  const tbl=$('#rivdentbl'); if(!tbl) return;
  if(rivdenLoaded){ drawRivalDensity(); return; }
  fetch('data/rival_density.json').then(r=>r.ok?r.json():null).then(j=>{
    RIVDEN=j; rivdenLoaded=true; drawRivalDensity();
  }).catch(()=>{ RIVDEN=null; rivdenLoaded=true; drawRivalDensity(); });
}
function drawRivalDensity(){
  const tbl=$('#rivdentbl'), ro=$('#rivdenreadout'); if(!tbl) return;
  const recs=(RIVDEN&&Array.isArray(RIVDEN.records))?RIVDEN.records:[];
  if(!recs.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Rival-density board not yet computed.</b> <span class="sub">Run pipeline/build_rival_density.py — it fills in on the next data refresh.</span>';
    return;
  }
  // most-outnumbered first: rank by (rivals − autox), i.e. the raw branch deficit vs the big-4.
  const list=recs.slice().filter(r=>(r.rivals||0)>(r.autox||0))
    .sort((a,b)=>((b.rivals-b.autox)-(a.rivals-a.autox))).slice(0,RIVDEN_TOPN);
  const brandStr=bb=>{ if(!bb||typeof bb!=='object')return ''; return Object.entries(bb)
    .sort((a,b)=>b[1]-a[1]).slice(0,2).map(([k,v])=>`${k} ${v}`).join(', '); };
  tbl.innerHTML=`<tr><th scope="col">#</th><th scope="col">District</th><th scope="col">Province</th>`+
    `<th scope="col" title="AutoX branches in this district (MEASURED)">AutoX</th>`+
    `<th scope="col" title="Big-4 rival branches in this district, from the full official-locator census (MEASURED)">Rivals ◆</th>`+
    `<th scope="col" title="rivals ÷ AutoX">Ratio</th>`+
    `<th scope="col" title="Which single big-4 brand holds the most of this district's rival field, and its share of all rival branches here (MEASURED). Bold = one rival owns a majority (single-brand-dominated — it sets the local terms); the sub-line is the top-2 brands by count.">Who holds it</th></tr>`+
    list.map((r,i)=>{
      const ratio=(r.autox>0)?(r.rivals/r.autox).toFixed(1)+'×':'∞';
      const rc=(r.rivals-r.autox)>=40?'var(--agri)':'var(--gold)';
      const conc=rivFieldConc(r.by_brand);
      const holds=conc
        ? `<b style="color:${conc.dominated?'var(--agri)':'var(--gold)'}" title="Of this district's ${conc.tot} big-4 rival branches (AutoX excluded), ${conc.brand} holds the most — ${Math.round(conc.share*100)}% (${conc.dominated?'single-brand-dominated — that one rival effectively sets the local terms':'fragmented across the big-4'}). MEASURED.">${conc.brand} ${Math.round(conc.share*100)}%</b><div class="sub" style="font-weight:400">${brandStr(r.by_brand)}</div>`
        : `<span class="sub">${brandStr(r.by_brand)}</span>`;
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td><b>${r.name||'—'}</b></td>
        <td class="sub">${r.province_th||''}</td>
        <td class="mono">${(r.autox||0).toLocaleString()}</td>
        <td class="mono" style="color:${rc}"><b>${(r.rivals||0).toLocaleString()}</b></td>
        <td class="mono" style="color:${rc}">${ratio}</td>
        <td>${holds}</td>
      </tr>`;}).join('');
  if(ro){
    const m=RIVDEN.meta||{};
    const nOut=m.n_outnumbered!=null?m.n_outnumbered:recs.filter(r=>r.flag==='outnumbered').length;
    // district-grain rival-field concentration (MEASURED, computed here from the committed by_brand
    // census): of the districts with a SUBSTANTIAL big-4 field, how many are single-brand-dominated,
    // and which brand dominates the most of them. The same texture the province peer board carries,
    // one grain finer — a real obj#2 signal the raw deficit ranking can't give.
    let concStr='';
    const subF=recs.map(r=>rivFieldConc(r.by_brand)).filter(Boolean);
    if(subF.length){
      const nDom=subF.filter(c=>c.dominated).length;
      const tally={}; subF.filter(c=>c.dominated).forEach(c=>{tally[c.brand]=(tally[c.brand]||0)+1;});
      const top=Object.entries(tally).sort((a,b)=>b[1]-a[1])[0];
      concStr=`At district grain the rival field is even more lopsided than the province rollup: of the `+
        `<b>${subF.length}</b> districts with a substantial big-4 field (≥${RIVDEN_CONC_MIN} rival branches), `+
        `<b style="color:var(--agri)">${nDom}</b> are single-brand-dominated — one rival holds a majority`+
        (top?`, <b>${top[0]}</b> in ${top[1]} of them`:'')+`. `;
    }
    ro.innerHTML=`<b>The big-4 out-station AutoX in <b style="color:var(--agri)">${nOut}</b> districts.</b> `+
      `Ranked by raw branch deficit against the FULL official-locator census (${(m.total_rivals||16393).toLocaleString()} measured rival branches). `+
      `These are the districts where competitors already own the ground — defend or concede deliberately. `+concStr+`${TAG_M}`+
      methodBox(null,
        ['AutoX + rival branch counts are <b>MEASURED</b> (point-in-district); ratio is computed.',
         'Rivals = the merged census (official store-locators for Muangthai/Srisawad/Tidlor; Heng is a sample).',
         '<b>Who holds it</b> reads the concentration of the rival field: bold = one brand owns a majority (single-brand-dominated, it sets the local terms); the % is that brand’s share of the district’s rival branches. MEASURED — a straight read of the per-brand census, gated on a ≥'+RIVDEN_CONC_MIN+'-branch field so a thin field can’t score a meaningless 100%.',
         'A high ratio is a competitive-density signal, not a verdict — some dense districts are worth contesting, others conceding.']);
  }
}

/* ---------- per-province peer comparison · AutoX vs each rival brand (obj #2) ----------
   Surfaces data/peer_province.json (77 provinces, pipeline/build_peer_province.py): a pure
   rollup of rival_density.json that KEEPS the per-brand split, so each province shows AutoX
   next to Muangthai / Srisawad / Tidlor / Heng separately. Lazy, graceful if absent. We DO
   NOT recompute anything here — we rank & show measured counts. A competitive-pressure read
   on the existing network; no open / expand call. */
let PEERPROV=null, peerprovLoaded=false, peerprovPromise=null;
const PEERPROV_TOPN=20;
// Reusable promise loader — shared by the Competition tab board AND the command-center thesis clause
// (obj#2). Fetches once, caches, degrades to null on any error so callers stay null-safe.
function loadPeerProvince(){
  if(peerprovPromise) return peerprovPromise;
  peerprovPromise=fetch('data/peer_province.json').then(r=>r.ok?r.json():null)
    .then(j=>{ PEERPROV=j; peerprovLoaded=true; return PEERPROV; })
    .catch(()=>{ PEERPROV=null; peerprovLoaded=true; return null; });
  return peerprovPromise;
}
// COMBINED PROVINCE PRESSURE (province_pressure.json) — the deterministic JOIN of portfolio-risk
// (province_stress_index composite_stress) x competitive-risk (peer_province rival:AutoX ratio),
// each as a 0-100 percentile. Powers the command-center thesis' cross-objective clause: how many
// provinces are BOTH borrower-stressed AND rival-dominated (both axes top-third) and which is worst.
// Fetches once, caches, degrades to null on any error so the thesis clause stays null-safe.
let PROVPRESS=null, provpressLoaded=false, provpressPromise=null;
function loadProvincePressure(){
  if(provpressPromise) return provpressPromise;
  provpressPromise=fetch('data/province_pressure.json').then(r=>r.ok?r.json():null)
    .then(j=>{ PROVPRESS=j; provpressLoaded=true; return PROVPRESS; })
    .catch(()=>{ PROVPRESS=null; provpressLoaded=true; return null; });
  return provpressPromise;
}
function renderPeerProvince(){
  const tbl=$('#peerprovtbl'); if(!tbl) return;
  if(peerprovLoaded){ drawPeerProvince(); return; }
  loadPeerProvince().then(drawPeerProvince);
}
function drawPeerProvince(){
  const tbl=$('#peerprovtbl'), ro=$('#peerprovreadout'); if(!tbl) return;
  const recs=(PEERPROV&&Array.isArray(PEERPROV.provinces))?PEERPROV.provinces:[];
  if(!recs.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Per-province peer board not yet computed.</b> <span class="sub">Run pipeline/build_peer_province.py — it fills in on the next data refresh.</span>';
    return;
  }
  const m=PEERPROV.meta||{};
  // fixed brand column order carried from the layer (alphabetical over the census).
  const brands=Array.isArray(m.brands)?m.brands:['Heng','Muangthai','Srisawad','Tidlor'];
  // licensed PICO-finance operators are a DISTINCT small-ticket rival class (FPO registry, MEASURED),
  // folded into the layer as its own `pico` column. Gate the column on the layer flag so an older
  // peer_province.json (pre-fold) degrades gracefully to the big-4-only board.
  const hasPico=m.pico_available===true;
  const list=recs.slice(0,PEERPROV_TOPN);
  const bh=brands.map(b=>`<th scope="col" title="${b} branches in this province (MEASURED census)">${b}</th>`).join('');
  const ph=hasPico?`<th scope="col" title="Licensed PICO-finance operators — a DISTINCT small-ticket rival class (MEASURED, FPO registry ${m.pico_source&&m.pico_source.vintage?m.pico_source.vintage:''})">PICO</th>`:'';
  // AutoX's own rank among the operators present (MEASURED counts, computed position) is
  // co-located under the AutoX count — gated on the layer field so a pre-fold file degrades.
  const hasRank=list.some(r=>r.autox_rank!=null);
  const ordinal=n=>n+(({1:'st',2:'nd',3:'rd'})[n]||'th');
  // Per-province saturation vs the MEASURED vehicle collateral base (title-lender branches per
  // 100k DLT registered vehicles) — the crowding read the raw count/ratio can't give, previously
  // only in the headline. Gated on the layer flag so a pre-fold peer_province.json degrades to
  // no column; † marks the Greater-Bangkok inner-ring (density inflated by central registration).
  const hasSatCol=m.vehicle_saturation_available===true && list.some(r=>r.titlelender_per_100k_veh!=null);
  const natTL=(typeof m.national_titlelender_per_100k_veh==='number')?m.national_titlelender_per_100k_veh:null;
  const sh=hasSatCol?`<th scope="col" title="Title-lender branches (AutoX + rivals) per 100,000 MEASURED DLT registered vehicles — how crowded the market is per unit of vehicle collateral, which the raw count can’t show${natTL!=null?`. National ${natTL.toFixed(1)}/100k`:''}. † = Greater-Bangkok inner-ring, density inflated by central vehicle registration (excluded from the crowding headline).">Sat/100k</th>`:'';
  // Intra-province ground contest: of a province's districts, how many is AutoX outnumbered in
  // (MEASURED, point-in-district — n_outnumbered_districts / n_districts). This is the read the
  // province rank/ratio can't give: a province AutoX ranks well in overall can still be outnumbered
  // in most of its districts (ground-level contest the aggregate masks). Gated on the layer field so
  // a pre-fold peer_province.json degrades to no column.
  // Rival-field concentration chip under Leads: the single big-4 brand holding the most of the
  // province's RIVAL field (AutoX excluded) and its share — the province-grain read the summary
  // prose only gives nationally. `leader`/`Leads` names the top operator (which can be AutoX) but
  // says nothing about whether the OTHER competitors are one dominant brand or a fragmented split;
  // where one rival owns a majority, that single competitor sets the local pricing AutoX faces.
  // Gated on a SUBSTANTIAL rival field (>= the layer's own concentration floor, default 10) so a
  // thin 1-2-branch field can't show a meaningless 100%; floors read from meta so the chip stays in
  // lockstep with build_peer_province.py. Both underlying fields are MEASURED per-brand census counts.
  const concMinRivals=(typeof m.rival_concentration_min_rivals==='number')?m.rival_concentration_min_rivals:10;
  const concShare=(typeof m.rival_concentration_share_floor==='number')?m.rival_concentration_share_floor:0.5;
  const hasDistCol=list.some(r=>r.n_districts);
  const dh=hasDistCol?`<th scope="col" title="Share of this province's districts where the big-4 rivals outnumber AutoX (MEASURED, point-in-district). The province rank can mask this — a good province standing can still lose most of its districts on the ground.">Dist. lost</th>`:'';
  tbl.innerHTML=`<tr><th scope="col">#</th><th scope="col">Province</th>`+
    `<th scope="col" title="AutoX branches in this province (MEASURED, point-in-district)${hasRank?' — the #k/n chip is AutoX’s rank among the operators present here':''}">AutoX${hasRank?' <span class="sub" style="font-weight:400">·rank</span>':''}</th>`+
    bh+ph+
    `<th scope="col" title="all big-4 rival branches ÷ AutoX">Ratio</th>`+
    sh+dh+
    `<th scope="col" title="the single operator with the most branches in the province">Leads</th></tr>`+
    list.map((r,i)=>{
      const ratio=(r.autox>0)?(r.rivals/r.autox).toFixed(1)+'×':'∞';
      const rc=(r.rivals-r.autox)>=200?'var(--agri)':'var(--gold)';
      const bcols=brands.map(b=>{const v=(r.by_brand&&r.by_brand[b])||0;
        return `<td class="mono"${v?'':' style="color:var(--dim)"'}>${v?v.toLocaleString():'·'}</td>`;}).join('');
      const pv=(r.pico!=null)?r.pico:0;
      const pcol=hasPico?`<td class="mono" style="color:${pv?'var(--collat)':'var(--dim)'}">${pv?pv.toLocaleString():'·'}</td>`:'';
      // saturation vs the vehicle collateral base: agri when above the national line (contested per
      // unit of collateral), gold below; flagged inner-ring shown dim with a † (inflated, off-headline).
      let satCol='';
      if(hasSatCol){
        const tl=r.titlelender_per_100k_veh;
        if(tl==null){ satCol='<td class="mono" style="color:var(--dim)">·</td>'; }
        else{
          const flagged=!!r.vehicle_stock_flag;
          const scol=flagged?'var(--dim)':((natTL!=null&&tl>natTL)?'var(--agri)':'var(--gold)');
          const dag=flagged?'<span style="color:var(--dim)"> †</span>':'';
          const brk=[r.autox_per_100k_veh!=null?`AutoX ${r.autox_per_100k_veh.toFixed(1)}`:null,
                     r.rivals_per_100k_veh!=null?`rivals ${r.rivals_per_100k_veh.toFixed(1)}`:null].filter(Boolean).join(' · ');
          satCol=`<td class="mono" style="color:${scol}"${brk?` title="${brk} per 100k veh${flagged?' · inner-ring density inflated by central registration':''}"`:''}>${tl.toFixed(1)}${dag}</td>`;
        }
      }
      // districts-lost cell: share of the province's districts where rivals outnumber AutoX.
      // teal when it holds every district (0 lost), gold below two-thirds, agri at/above two-thirds.
      let distCol='';
      if(hasDistCol){
        const nd=r.n_districts||0, no=r.n_outnumbered_districts;
        if(!nd||no==null){ distCol='<td class="mono" style="color:var(--dim)">·</td>'; }
        else{
          const share=no/nd, pct=Math.round(share*100);
          const dcol=(no===0)?'var(--merch)':(share>=2/3?'var(--agri)':'var(--gold)');
          distCol=`<td class="mono" style="color:${dcol}" title="AutoX is outnumbered by the big-4 in ${no} of ${nd} districts here (MEASURED, point-in-district)">${pct}%<span class="sub" style="font-weight:400"> ${no}/${nd}</span></td>`;
        }
      }
      const lead=(r.leader==='AutoX')?`<span style="color:var(--merch)"><b>AutoX</b></span>`:`<span class="sub">${r.leader||'—'}</span>`;
      // rival-field concentration chip (AutoX-excluded): agri when one rival owns a majority of the
      // field (single-brand-dominated — one competitor sets local pricing), gold when fragmented.
      // Shown only where the rival field is substantial; degrades to '' on a pre-fold layer.
      let concChip='';
      if(r.rival_top_brand&&r.rival_top_share!=null&&(r.rivals||0)>=concMinRivals){
        const dom=r.rival_top_share>=concShare, cpct=Math.round(r.rival_top_share*100);
        const ccol=dom?'var(--agri)':'var(--gold)';
        concChip=`<div class="sub" style="font-size:10px;line-height:1.15;margin-top:1px;color:${ccol}" title="Of this province's ${r.rivals} big-4 rival branches (AutoX excluded), ${r.rival_top_brand} holds the most — ${cpct}%. ${dom?'A single rival dominates the field, so local pricing is effectively set by one competitor':'The rival field is fragmented across several brands'} (MEASURED census).">field: ${r.rival_top_brand} ${cpct}%</div>`;
      }
      // AutoX rank chip: green when 1st/2nd (a defensible standing), red when it is the smallest
      // operator present (last of the pool), gold in between. Underlying counts are MEASURED.
      let rankCell='';
      if(r.autox_rank!=null){
        const rk=r.autox_rank, nr=r.n_ranked||1, last=(nr>1&&rk===nr);
        const rcol=rk<=2?'var(--merch)':(last?'var(--agri)':'var(--gold)');
        rankCell=`<div class="sub" style="font-size:10px;line-height:1.15;margin-top:1px;color:${rcol}" title="AutoX is the ${ordinal(rk)} largest of ${nr} operators present in this province (AutoX + big-4 brands with a branch here) — MEASURED branch counts">#${rk}/${nr}</div>`;
      }
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td><b>${r.province_th||'—'}</b></td>
        <td class="mono" style="color:var(--merch)"><b>${(r.autox||0).toLocaleString()}</b>${rankCell}</td>
        ${bcols}${pcol}
        <td class="mono" style="color:${rc}">${ratio}</td>
        ${satCol}${distCol}
        <td>${lead}${concChip}</td>
      </tr>`;}).join('');
  if(ro){
    const nOut=m.n_provinces_outnumbered!=null?m.n_provinces_outnumbered:recs.filter(r=>r.autox>0&&r.rivals>r.autox).length;
    const pbt=m.per_brand_total||{};
    const brandStr=brands.filter(b=>pbt[b]).map(b=>`${b} ${pbt[b].toLocaleString()}`).join(' · ');
    const hasPico=m.pico_available===true;
    const picoStr=hasPico?` Behind them sits a distinct small-ticket rival class: <b style="color:var(--collat)">${(m.total_pico||0).toLocaleString()}</b> licensed PICO-finance operators across ${m.n_provinces_pico_present||0} provinces (MEASURED, FPO registry).`:'';
    // Saturation vs the MEASURED vehicle collateral base — how crowded a market is per unit of
    // lendable collateral, which the raw count cannot show. Metro inner-ring is excluded upstream.
    const hasSat=m.vehicle_saturation_available===true && m.most_saturated_province;
    const ms=m.most_saturated_province||{};
    const satStr=hasSat?` <b>Per 100k registered vehicles</b> (the MEASURED collateral base) the ground carries <b>${(m.national_titlelender_per_100k_veh||0).toFixed(1)}</b> title-lender branches nationally (AutoX ${(m.national_autox_per_100k_veh||0).toFixed(1)} · rivals ${(m.national_rivals_per_100k_veh||0).toFixed(1)}); it is most crowded per unit of collateral in <b style="color:var(--agri)">${ms.province_th||'—'}</b> (${(ms.titlelender_per_100k_veh||0).toFixed(1)}/100k).`:'';
    // Most out-fielded relative to AutoX's OWN presence (rival:AutoX count ratio) — a competitive-
    // pressure lead the density read can't give: where each AutoX branch faces the most rival points.
    // ratio is a FLOOR (Heng is a lower-bound sample); autox/rivals carried so the exposure is visible.
    const mo=m.most_outnumbered_province||null;
    const outStr=mo?` Relative to its own footprint, AutoX is most out-fielded in <b style="color:var(--agri)">${mo.province_th}</b> — at least <b>${(mo.ratio||0).toFixed(1)}:1</b> (${mo.autox} AutoX vs ${mo.rivals} big-4 rivals).`:'';
    // AutoX's own standing (MEASURED rank among present operators): where it sits, not just who leads.
    const nProv=m.n_provinces||recs.length;
    const hasRankRollup=m.best_autox_rank!=null;
    const rankStr=hasRankRollup?` <b>By branch count AutoX is the single largest lender in <b style="color:var(--agri)">${m.n_provinces_autox_leads||0}</b> of ${nProv} provinces</b> — its best standing anywhere is <b>${ordinal(m.best_autox_rank)}</b> (in ${m.n_provinces_autox_top2||0}), it sits 3rd-or-lower in ${Math.max(0,nProv-(m.n_provinces_autox_top2||0))}, and it is the <b style="color:var(--agri)">smallest</b> of the operators present in <b>${m.n_provinces_autox_last||0}</b>.`:'';
    // WHICH rival dominates the most ground — data-driven from the MEASURED leader tally
    // (m.provinces_led_by, 77-province rollup of the `leader` field); degrades to the prior
    // generic phrasing on a pre-fold peer_province.json that lacks the field.
    const plb=m.provinces_led_by||null;
    let leadStr='Muangthai leads the ground in most';
    if(plb){
      const rivalsLed=Object.entries(plb).filter(([op,n])=>op!=='AutoX'&&n>0).sort((a,b)=>b[1]-a[1]);
      if(rivalsLed.length){
        const [top,topN]=rivalsLed[0];
        const rest=rivalsLed.slice(1).map(([op,n])=>`${op} ${n}`).join(', ');
        leadStr=`<b>${top}</b> leads the ground in <b style="color:var(--agri)">${topN}</b> of ${nProv} provinces`+
          (rest?` (${rest})`:'')+(plb.AutoX>0?`, AutoX in ${plb.AutoX}`:', AutoX in none');
      }
    }
    // WHERE that lead sits — the same MEASURED `leader` field rolled up by region
    // (m.region_brand_leaders). The national tally hides that a network can dominate everywhere yet
    // be genuinely contested in ONE region; this names the regional leader and flags any region where
    // the lead is a tie or thin (<60% of the region's provinces). Degrades to '' on a pre-fold layer.
    const rbl=m.region_brand_leaders||null;
    let regionStr='';
    if(rbl&&rbl.length){
      const regByLeader={};
      rbl.forEach(r=>{regByLeader[r.leader]=(regByLeader[r.leader]||0)+1;});
      const domEntries=Object.entries(regByLeader).sort((a,b)=>b[1]-a[1]);
      const domStr=(domEntries.length===1)
        ? `<b>${domEntries[0][0]}</b> holds the most provinces in all ${rbl.length} regions`
        : `the regional ground leader is ${domEntries.map(([op,n])=>`<b>${op}</b> in ${n}`).join(', ')}`;
      const contested=rbl.filter(r=>{
        const vals=Object.values(r.led_by||{}).sort((a,b)=>b-a);
        return (vals[1]||0)>=r.n_led || (r.n_provinces && r.n_led/r.n_provinces<0.6);
      }).map(r=>{
        const runner=Object.entries(r.led_by||{}).filter(([op])=>op!==r.leader).sort((a,b)=>b[1]-a[1])[0];
        return runner?`the <b style="color:var(--agri)">${r.region}</b> is contested (${r.leader} ${r.led_by[r.leader]} / ${runner[0]} ${runner[1]} of ${r.n_provinces})`:'';
      }).filter(Boolean);
      regionStr=` By region, ${domStr}${contested.length?' — but '+contested.join('; '):''}.`;
    }
    // Rival-field CONCENTRATION — is the big-4 field one dominant brand or a split? A distinct read
    // from `leader`/rank (those can name AutoX or the top brand while saying nothing about how lopsided
    // the RIVAL side is). Gated on the substantial-field rollup; degrades to '' on a pre-fold layer.
    const conc=m.most_rival_concentrated_province||null;
    let concStr='';
    if(conc&&m.n_provinces_rival_concentrated!=null){
      const bybrand=m.rival_concentration_by_brand||{};
      const domBrand=Object.entries(bybrand).sort((a,b)=>b[1]-a[1])[0];
      const domTxt=domBrand?` — usually <b>${domBrand[0]}</b>, which alone holds a majority of the field in <b style="color:var(--agri)">${domBrand[1]}</b>`:'';
      const pct=Math.round((conc.rival_top_share||0)*100);
      concStr=` In <b style="color:var(--agri)">${m.n_provinces_rival_concentrated}</b> of the ${m.n_provinces_rival_field_substantial} provinces with a substantial big-4 presence the rival field is <b>single-brand-dominated</b>${domTxt} — so local pricing there is set by one competitor, not a fragmented field. Most lopsided: <b>${conc.province_th}</b>, where <b>${conc.rival_top_brand}</b> holds <b>${pct}%</b> of its ${conc.rivals} big-4 rival branches.`;
    }
    // Intra-province ground contest, rolled up client-side from the same MEASURED per-record fields:
    // how many of ALL 77 provinces' districts the big-4 outnumber AutoX in, plus the "hidden contest"
    // cases where AutoX ranks top-2 in the province yet is outnumbered in the majority of its districts
    // (the province rank masks ground-level contest the district read exposes).
    const withDist=recs.filter(r=>r.n_districts);
    let distStr='';
    if(withDist.length){
      const totD=withDist.reduce((s,r)=>s+(r.n_districts||0),0);
      const lostD=withDist.reduce((s,r)=>s+(r.n_outnumbered_districts||0),0);
      const hidden=withDist.filter(r=>r.autox_rank!=null&&r.autox_rank<=2&&(r.n_outnumbered_districts/r.n_districts)>0.5)
                           .sort((a,b)=>(b.n_outnumbered_districts/b.n_districts)-(a.n_outnumbered_districts/a.n_districts));
      const hidStr=hidden.length?` The province rank can mask ground contest — AutoX ranks top-2 yet is outnumbered in most of its own districts in <b style="color:var(--agri)">${hidden.length}</b> province${hidden.length>1?'s':''} (worst: <b>${hidden[0].province_th}</b>, ${hidden[0].n_outnumbered_districts}/${hidden[0].n_districts}).`:'';
      distStr=` Zooming to districts, the big-4 outnumber AutoX in <b style="color:var(--agri)">${lostD.toLocaleString()}</b> of ${totD.toLocaleString()} districts nationwide (${totD?Math.round(100*lostD/totD):0}%).${hidStr}`;
    }
    ro.innerHTML=`<b>The big-4 out-station AutoX in <b style="color:var(--agri)">${nOut}</b> of 77 provinces.</b>${rankStr} `+
      `Against the full official-locator census (${(m.total_rivals||0).toLocaleString()} rival branches vs `+
      `${(m.total_autox||0).toLocaleString()} AutoX), ${leadStr}.${regionStr}${concStr} `+
      `National rival footprint: ${brandStr}.${picoStr}${satStr}${outStr}${distStr} ${TAG_M}`+
      methodBox(null,
        ['AutoX + per-brand rival counts are <b>MEASURED</b> — a straight province rollup of the district census (rival_density.json).',
         'The <b>per-100k-vehicle</b> saturation reads title-lender branches against <b>MEASURED</b> DLT registered-vehicle stock (the vehicle collateral base) — a crowding read the raw count can’t give. The three Greater-Bangkok inner-ring provinces are <b>excluded</b> from the most-crowded headline: they register most vehicles centrally at the Bangkok DLT office (a MEASURED NSO labour-force cross-check flags them), which would inflate their density. National saturation is unaffected (vehicle stock is sum-conserved).',
         'The <b>#k/n</b> chip under the AutoX count is AutoX’s <b>rank</b> among the operators present (AutoX + big-4 brands with a branch here) — MEASURED counts, computed position. It sharpens the Leads column: two provinces both led by Muangthai can have AutoX 2nd (defensible) or last of 4 (marginalised).',
         'The <b>Dist. lost</b> column is the share of the province’s districts where the big-4 outnumber AutoX (MEASURED, point-in-district) — a ground-level read the province rank/ratio can’t give: AutoX can rank well in a province overall yet be outnumbered in most of its districts.',
         'Muangthai / Srisawad / Tidlor are near-complete <b>official-locator</b> networks; Heng is a Google/Overture <b>sample</b> (under-counts).',
         'The <b>PICO</b> column is a separate <b>MEASURED</b> class — licensed พิโกไฟแนนซ์ operators from the FPO registry (small-ticket, not part of the big-4 ratio).',
         'The <b>single-brand-dominated</b> read is <b>MEASURED</b>-derived: over provinces with a substantial big-4 field (≥10 rival branches, so a tiny field can’t score a meaningless 100%), it counts those where one rival brand holds a majority of the rival branches — a lopsided field means a single competitor sets local pricing; a split field spreads the pressure. Computed share, MEASURED counts.',
         'Ratio is the merged big-4 count ÷ AutoX — a competitive-pressure signal on the existing network, not an expansion cue.']);
  }
}

/* ---------- MEASURED credit anchor · BoT NPL scale for the risk readout (obj #1) ----------
   Surfaces data/credit_anchor.json (pipeline/build_credit_anchor.py ← BoT FSR 2024 text layer +
   BoT statistics report 984). The real-world NPL + household-debt scale the ESTIMATED 0-100
   branch-risk composite is read against — CONTEXT, never a composite input. Lazy, null-safe. */
let CREDITANCHOR=null, creditAnchorLoaded=false;
function renderCreditAnchor(){
  const box=$('#creditanchor'); if(!box) return;
  if(creditAnchorLoaded){ drawCreditAnchor(); return; }
  fetch('data/credit_anchor.json').then(r=>r.ok?r.json():null).then(j=>{
    CREDITANCHOR=j; creditAnchorLoaded=true; drawCreditAnchor();
  }).catch(()=>{ CREDITANCHOR=null; creditAnchorLoaded=true; drawCreditAnchor(); });
}
function drawCreditAnchor(){
  const box=$('#creditanchor'), stats=$('#creditanchorstats'); if(!box) return;
  const metrics=(CREDITANCHOR&&Array.isArray(CREDITANCHOR.metrics))?CREDITANCHOR.metrics:[];
  if(!metrics.length){
    if(stats) stats.innerHTML='';
    box.innerHTML='<b>BoT credit anchor not available.</b> <span class="sub">data/credit_anchor.json is absent — it fills in from BoT FSR 2024 + statistics report 984 on the next data refresh (pipeline/pull_bot_credit.py).</span>';
    return;
  }
  const m=CREDITANCHOR.meta||{};
  const mc={system_npl:'var(--accent)',household_debt_to_gdp:'var(--collat)',household_debt:'var(--collat)',auto_hp_debt:'var(--gold)'};
  const by=k=>metrics.find(x=>x.key===k);
  const npl=by('system_npl'), hh=by('household_debt'), gdp=by('household_debt_to_gdp'), auto=by('auto_hp_debt');
  // answer-first headline
  const head=`<b>The measured real-world scale:</b> `+
    (npl?`system NPL <b style="color:var(--accent)">${npl.display}</b>`:'')+
    (hh?` · household debt <b style="color:var(--collat)">${hh.display}</b>${gdp?` (${gdp.display} of GDP)`:''}`:'')+
    (auto?`, of which vehicle hire-purchase <b style="color:var(--gold)">${auto.display}</b>${auto.share_of_hh_debt_pct!=null?` (${auto.share_of_hh_debt_pct}% of household debt)`:''}`:'')+
    `. ${TAG_M}`;
  const ahp=(CREDITANCHOR.auto_hp_npl)||{};
  box.innerHTML=head+
    `<div class="sub" style="margin-top:6px">The estimated 0–100 branch-risk score is a <b>triage rank, not a predicted NPL</b> — these BoT figures are the real-world scale it is read against, shown alongside the score, never inside it.</div>`+
    methodBox(m.label||null,
      [ ...metrics.map(x=>`<b>${x.label}: ${x.display}</b> — ${x.scope}. ${TAG_M} ${x.source} (${x.vintage})${x.source_url?` · <a href="${x.source_url}" target="_blank" rel="noopener" style="color:var(--accent)">source</a>`:''}`),
        ahp.reason_absent?`<b>Auto hire-purchase NPL:</b> ${ahp.reason_absent}`:null,
        m.source?`Source: ${m.source}. Vintage/pulled ${m.pulled||'—'}.`:null ]);
  if(stats){
    stats.innerHTML=metrics.map(x=>{
      const c=mc[x.key]||'var(--hi)';
      const sub=[x.vintage,x.source].filter(Boolean).join(' · ');
      return `<div class="mcard"><div class="k">${x.label}</div>`+
        `<div class="v" style="color:${c}">${x.display}</div>`+
        `<div class="n">${sub}</div></div>`;
    }).join('');
  }
}

/* ---------- listed-peer market scoreboard · SET (obj #2, MEASURED) ----------
   Surfaces data/peer_scoreboard.json (build_peer_scoreboard.py, from the autonomous SET pull):
   market cap, valuation, ROE + net profit for the 3 listed title-lenders, with AutoX's 25% ROE
   target as the reference line. MEASURED (Stock Exchange of Thailand). NOT an AutoX row (unlisted).
   Lazy, null-safe, graceful if absent. */
let PEERSCORE=null, peerscoreLoaded=false;
function renderPeerScore(){
  const tbl=$('#peerscoretbl'); if(!tbl) return;
  if(peerscoreLoaded){ drawPeerScore(); return; }
  fetch('data/peer_scoreboard.json').then(r=>r.ok?r.json():null).then(j=>{
    PEERSCORE=j; peerscoreLoaded=true; drawPeerScore();
  }).catch(()=>{ PEERSCORE=null; peerscoreLoaded=true; drawPeerScore(); });
}
function drawPeerScore(){
  const tbl=$('#peerscoretbl'), ro=$('#peerscorereadout'); if(!tbl) return;
  const peers=(PEERSCORE&&Array.isArray(PEERSCORE.peers))?PEERSCORE.peers:[];
  if(!peers.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Listed-peer scoreboard not available.</b> <span class="sub">data/peer_scoreboard.json is absent — run pipeline/pull_set_peers.py then build_peer_scoreboard.py.</span>';
    return;
  }
  const m=PEERSCORE.meta||{}, tgt=PEERSCORE.autox_roe_target;
  const roes=peers.map(p=>p.roe).filter(v=>typeof v==='number');
  const hiRoe=Math.max(...roes, tgt||0);
  const yc=v=>v==null?'var(--dim)':(v>0?'var(--merch)':'var(--agri)');
  tbl.innerHTML=`<tr><th>#</th><th>Listed peer</th>`+
    `<th title="market capitalisation (SET, price date)">Mkt cap</th>`+
    `<th title="year-to-date price change — share-price momentum / investor mindshare">YTD</th>`+
    `<th title="return on equity, latest quarter as SET reports">ROE</th>`+
    `<th title="net profit, latest quarter">Net profit/q</th>`+
    `<th title="price / earnings">P/E</th>`+
    `<th title="dividend yield">Div</th></tr>`+
    peers.map((p,i)=>{
      const roeBar=(typeof p.roe==='number')?barHTML(p.roe,'var(--merch)',hiRoe):'';
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td><b>${p.name||p.symbol}</b> <span class="sub mono">${p.symbol}</span></td>
        <td class="mono"><b>฿${p.market_cap_bn}bn</b></td>
        <td class="mono" style="color:${yc(p.ytd_pct)}">${p.ytd_pct>0?'+':''}${p.ytd_pct}%</td>
        <td class="mono">${roeBar} <b>${p.roe}%</b></td>
        <td class="mono sub">฿${p.net_profit_q_bn}bn</td>
        <td class="mono sub">${p.pe}</td>
        <td class="mono sub">${p.div_yield}%</td>
      </tr>`;}).join('')+
    (tgt?`<tr style="border-top:1px dashed var(--line)"><td></td><td><b style="color:var(--gold)">AutoX target</b> <span class="sub">(unlisted)</span></td><td class="sub">—</td><td class="sub">—</td><td class="mono"><b style="color:var(--gold)">${tgt}%</b> <span class="sub">ROE goal</span></td><td class="sub">—</td><td class="sub">—</td><td class="sub">—</td></tr>`:'');
  if(ro){
    const byRoe=peers.filter(p=>typeof p.roe==='number');
    const below=byRoe.filter(p=>p.roe<tgt).map(p=>p.name), above=byRoe.filter(p=>p.roe>=tgt).map(p=>p.name);
    ro.innerHTML=(PEERSCORE.headline||'')+` ${TAG_M}`+
      (tgt?` <b>AutoX's ${tgt}% ROE target</b> would sit above ${below.join(' & ')||'none'}, below ${above.join(' & ')||'none'} — the sharpest external benchmark we have.`:'')+
      methodBox(m.roe_caveat||null,
        [`<b>Measured</b> — Stock Exchange of Thailand (${m.source||'set.or.th'}); market cap/valuation as of ${m.price_asof||'the price date'}, fundamentals from ${m.fin_period||'the latest quarter'}.`,
         '<b>Not an AutoX row</b> — AutoX is unlisted (SCBX subsidiary); its 25% ROE target is a stated goal shown only as the reference line.',
         m.roe_caveat||'ROE is each peer’s own SET-reported ratio.']);
  }
}

/* ---------- iOS app sentiment · Apple App Store TH (obj #2, MEASURED) ----------
   Reads RIVPULSE.ios (build_rival_pulse.py <- pull_apple_reviews.py). Deliberately a SMALLER
   table than the Play ladder: Apple publishes no review dates, no star histogram and no dev
   replies, so no trend / detractor-share / reply-rate columns exist here rather than being
   faked from a review sample. Two guards the data forced:
     * rows under MIN_RATINGS are marked "thin" by the builder and must never be presented as a
       ranking — the nominal best title rival is Saksiam at 4.67 stars from NINE ratings;
     * the "digital" cohort is personal-loan/nano-finance, NOT title lenders, and is rendered in
       its own block so it can never read as title-lender share. */
function drawRivalIos(){
  const tbl=$('#pulseiostbl'), ro=$('#pulseiosreadout'), note=$('#pulseiosnote');
  if(!tbl) return;
  const ios=(RIVPULSE&&Array.isArray(RIVPULSE.ios))?RIVPULSE.ios:[];
  const im=(RIVPULSE&&RIVPULSE.ios_meta)||{};
  if(!ios.length){
    tbl.innerHTML=''; if(note) note.innerHTML='';
    if(ro) ro.innerHTML='<b>Apple pull not yet run.</b> <span class="sub">source-data/apple_reviews.json is absent — run pipeline/pull_apple_reviews.py (any IP, no key), then build_rival_pulse.py.</span>';
    return;
  }
  const title=ios.filter(r=>r.cohort==='title'), digital=ios.filter(r=>r.cohort==='digital');
  const own=title.find(r=>r.own);
  // comparisons are made ONLY against apps with enough ratings for a mean to mean anything
  const solid=title.filter(r=>!r.own&&!r.thin&&r.score!=null);
  const best=solid.length?solid.reduce((a,b)=>(b.score>a.score?b:a)):null;
  const star=v=>v==null?'—':`<b class="mono">${v.toFixed?v.toFixed(2):v}</b>★`;
  const rows=list=>list.map(r=>{
    const us=r.own, col=us?'var(--gold)':'var(--collat)';
    const nm=us?`<b style="color:var(--gold)">${r.name}</b> <span class="tag" style="color:var(--gold);border:1px solid var(--gold)">US</span>`:`<b>${r.name}</b>`;
    const thin=r.thin?' <span class="tag" title="too few ratings for the average to be meaningful — shown, but never ranked or compared">thin</span>':'';
    const th=(r.themes&&r.themes[0])?`${r.themes[0].label} <span class="sub mono">${r.themes[0].n}</span>`:'<span class="sub">—</span>';
    const q=(r.quotes&&r.quotes[0])?`<div class="sub" style="font-size:11px;margin-top:2px">“${(r.quotes[0].text||'').replace(/</g,'&lt;')}”</div>`:'';
    return `<tr${us?' style="background:rgba(230,180,80,.05)"':''}>
      <td>${nm}${thin}<div class="sub" style="font-size:11px">${r.brand}</div></td>
      <td class="mono">${barHTML(r.score||0,col,5)} ${star(r.score)}</td>
      <td class="mono sub">${r.ratings!=null?icN(r.ratings):'—'}</td>
      <td class="mono sub">${r.sample&&r.sample.n!=null?r.sample.n:'—'}</td>
      <td class="mono" style="color:${(r.sample&&r.sample.low_share_pct>=40)?'var(--agri)':'var(--dim)'}">${r.sample&&r.sample.low_share_pct!=null?r.sample.low_share_pct+'%':'—'}</td>
      <td class="sub" style="font-size:12px">${th}${q}</td></tr>`;}).join('');
  const head=`<tr><th>App</th><th title="lifetime average rating on the Thai App Store">Rating</th>`+
    `<th title="how many ratings that average is computed over">Ratings</th>`+
    `<th title="reviews we have stored and read for themes">Sample</th>`+
    `<th title="share of the WRITTEN-REVIEW sample at 1–2★. People who bother to write skew negative, so this always runs far darker than the star rating beside it (Tidlor: 76% of written reviews are 1–2★ against a 3.62★ lifetime average). Read it to compare operators against each other, never as the share of customers who are unhappy.">1–2★ of written sample</th>`+
    `<th title="ESTIMATED — Thai keyword read over the 1–2★ reviews">Top complaint</th></tr>`;
  tbl.innerHTML=head+rows(title);
  if(ro&&own&&best){
    const gap=(best.score-own.score);
    ro.innerHTML=`<b>On iPhone our เงินไชโย app rates ${own.score.toFixed(2)}★ across ${icN(own.ratings)} ratings — ${Math.abs(gap).toFixed(2)}★ ${gap>0?'behind':'ahead of'} ${best.name} (${best.score.toFixed(2)}★, ${icN(best.ratings)}).</b> <span class="sub">Compared only against apps with enough ratings to be meaningful; thin rows are shown but not ranked.</span>`;
  }
  if(note){
    const dr=digital.filter(r=>!r.thin);
    const dn=dr.reduce((a,b)=>a+(b.ratings||0),0), tn=title.reduce((a,b)=>a+(b.ratings||0),0);
    note.innerHTML=(digital.length?`<h3 class="compsub" style="margin-top:16px">Who else the same borrower has on their phone <span class="tag">ADJACENT — not title lenders</span></h3>`+
      `<p class="lead sub">Personal-loan and nano-finance apps. They do <b>not</b> lend against a vehicle book, so they are never counted in title-lender share — but they chase the same borrower with minutes-to-cash approval, and on mobile they outweigh the entire title field: <b>${icN(dn)}</b> ratings across ${dr.length} apps versus <b>${icN(tn)}</b> across all ${title.length} title lenders. That is substitution pressure on a branch-based product.</p>`+
      `<table class="tbl">${head}${rows(digital)}</table>`:'')+
      `<p class="sub" style="font-size:11px;margin-top:6px">${im.caveat||''}</p>`;
  }
}

/* ---------- rival PAID ADS · Google Ads Transparency Center (obj #2, MEASURED) ----------
   Surfaces data/rival_ads.json (build_google_ads.py, from pull_google_ads.py — runs from ANY
   IP incl. CI, unlike the Thai-IP promo pull). Google lists every creative an advertiser ran
   with its first/last shown date, so creative counts, live-today, run-length and format mix
   are MEASURED. It publishes spend/impressions ONLY for election ads, so this is share-of-
   VOLUME and the UI must never imply a spend ranking. Meta's Ad Library is not an alternative:
   its credit-ad slice is rejected as invalid for Thailand (see pipeline/spike_meta_ads.py).
   Lazy, null-safe, graceful when the pull has not been run. */
let RIVADS=null, rivadsLoaded=false;
function renderRivalAds(){
  const tbl=$('#pulseadstbl'); if(!tbl) return;
  if(rivadsLoaded){ drawRivalAds(); return; }
  fetch('data/rival_ads.json').then(r=>r.ok?r.json():null).then(j=>{
    RIVADS=j; rivadsLoaded=true; drawRivalAds();
  }).catch(()=>{ RIVADS=null; rivadsLoaded=true; drawRivalAds(); });
}
// 24-month creative-launch cadence as an inline sparkline — shows WHEN each rival pushed.
function adsSpark(series,color){
  if(!Array.isArray(series)||!series.length) return '<span class="sub">—</span>';
  const mx=Math.max.apply(null,series)||1, w=3, h=16;
  const bars=series.map((v,i)=>{
    const bh=Math.max(v>0?1:0,Math.round(h*v/mx));
    return `<rect x="${i*w}" y="${h-bh}" width="${w-1}" height="${bh}" fill="${color}"/>`;
  }).join('');
  return `<svg width="${series.length*w}" height="${h}" viewBox="0 0 ${series.length*w} ${h}" `+
         `role="img" aria-label="creative launches per month, last ${series.length} months" `+
         `style="vertical-align:-3px">${bars}</svg>`;
}
function drawRivalAds(){
  const tbl=$('#pulseadstbl'), ro=$('#pulseadsreadout'), note=$('#pulseadsnote');
  if(!tbl) return;
  const brands=(RIVADS&&Array.isArray(RIVADS.brands))?RIVADS.brands:[];
  const m=(RIVADS&&RIVADS.meta)||{};
  if(!brands.length){
    tbl.innerHTML='';
    if(note) note.innerHTML='';
    ['#pulseadsrates','#pulseadsmsgs'].forEach(s=>{const el=$(s); if(el) el.innerHTML='';});
    if(ro) ro.innerHTML='<b>Rival ad pull not yet run.</b> <span class="sub">data/rival_ads.json is absent — run pipeline/pull_google_ads.py (works from any IP), then build_google_ads.py.</span>';
    return;
  }
  const tot=brands.reduce((a,b)=>a+(b.n_creatives||0),0);
  const live=brands.reduce((a,b)=>a+(b.n_live||0),0);
  // Advertised rates keep the basis the ad stated — %/mo and %/yr are NEVER mixed or
  // converted here, because 1.25%/month is not 1.25%/year and pretending otherwise would
  // invent a price comparison the ads do not make.
  const rateTxt=r=>r?`<b>${r.value}%</b><span class="sub">/${r.basis==='month'?'mo':r.basis==='year'?'yr':'?'}</span>`:'<span class="sub">—</span>';
  tbl.innerHTML=`<tr><th>#</th><th>Brand</th>`+
    `<th title="distinct ad creatives Google lists for this advertiser in Thailand">Creatives</th>`+
    `<th title="creatives Google still showed within ${m.live_window_days||2} days of the pull">Live now</th>`+
    `<th title="creatives first shown in the last ${m.new_window_days||30} days — a fresh push">New 30d</th>`+
    `<th title="share of all tracked creative volume — NOT share of spend (Google does not publish commercial spend)">Share of volume</th>`+
    `<th title="median days between a creative's first and last shown date">Median run</th>`+
    `<th title="the headline rate this operator advertises, in the basis its own copy states — %/mo and %/yr are never converted into one another">Advertised rate</th>`+
    `<th title="ESTIMATED — the proposition its copy leans on most (keyword read over the ad text)">Lead message</th>`+
    `<th title="creative launches per month, oldest to newest">Cadence (24 mo)</th></tr>`+
    brands.map((b,i)=>{
      const us=b.is_us, col=us?'var(--gold)':'var(--collat)';
      const name=us?`<b style="color:var(--gold)">${b.brand}</b> <span class="tag" style="color:var(--gold);border:1px solid var(--gold)">US</span>`
                  :`<b>${b.brand}</b>`;
      const mix=Object.keys(b.kind_mix||{}).filter(k=>b.kind_mix[k])
                 .map(k=>`${k} <span class="sub mono">${b.kind_mix[k]}</span>`).join(' · ')||'<span class="sub">—</span>';
      return `<tr${us?' style="background:rgba(230,180,80,.05)"':''}>
        <td class="mono sub">${i+1}</td>
        <td>${name}<div class="sub" style="font-size:11px">${(b.advertiser_names||[]).join(' · ')||''}</div></td>
        <td class="mono">${barHTML(b.share_of_volume_pct||0,col,100)} <b>${icN(b.n_creatives)}</b></td>
        <td class="mono" style="color:${(b.n_live||0)>0?'var(--merch)':'var(--dim)'}">${icN(b.n_live)} <span class="sub">(${b.live_pct!=null?b.live_pct+'%':'—'})</span></td>
        <td class="mono" style="color:${(b.n_new_30d||0)>0?'var(--gold)':'var(--dim)'}">${icN(b.n_new_30d)}</td>
        <td class="mono">${b.share_of_volume_pct!=null?b.share_of_volume_pct+'%':'—'}</td>
        <td class="mono sub">${b.median_run_days!=null?b.median_run_days+'d':'—'}</td>
        <td class="mono">${rateTxt(b.headline_rate)}</td>
        <td class="sub" style="font-size:12px">${(b.themes&&b.themes[0])?b.themes[0].label+` <span class="sub mono">${b.themes[0].pct}%</span>`:'<span class="sub">—</span>'}</td>
        <td>${adsSpark(b.cadence,col)}</td>
      </tr>`;}).join('');
  // --- advertised-rate board: grouped BY BASIS so nothing implies a cross-basis ranking ---
  const rates=$('#pulseadsrates');
  if(rates){
    const mr=Array.isArray(RIVADS.market_rates)?RIVADS.market_rates:[];
    if(!mr.length){ rates.innerHTML='<p class="lead sub">No advertised rate appears in the copy we captured yet.</p>'; }
    else{
      const groups={month:'quoted per MONTH (ต่อเดือน)',year:'quoted per YEAR (ต่อปี)',unstated:'basis not stated in the ad'};
      rates.innerHTML=Object.keys(groups).filter(g=>mr.some(r=>r.basis===g)).map(g=>{
        const rows=mr.filter(r=>r.basis===g).sort((a,b)=>a.value-b.value);
        const mx=Math.max.apply(null,rows.map(r=>r.value))||1;
        return `<div style="margin:6px 0"><div class="sub mono" style="font-size:11px">${groups[g]}</div>`+
          rows.map(r=>{
            // the bar is the FROM rate the ad leads with; where the same ad also discloses a
            // ceiling, it is printed beside it so the headline never reads as the whole offer
            const band=(r.max!=null&&r.max>r.value)?`<span class="sub mono"> – ${r.max}%</span>`:'';
            return `<div style="display:flex;align-items:center;gap:8px;margin:2px 0">
            <span style="min-width:120px">${r.brand}</span>
            ${barHTML(r.value,'var(--collat)',mx)}
            <b class="mono">${r.value}%</b>${band}</div>`;}).join('')+`</div>`;
      }).join('')+`<p class="sub" style="font-size:11px;margin-top:4px">Grouped by the basis each ad states. A monthly quote and an annual quote are <b>not</b> comparable numbers and are never converted here — read each within its own group. These are <b>advertised headline</b> rates, not effective yields.</p>`;
    }
  }
  // --- the actual copy, per operator, newest first ---
  const msgs=$('#pulseadsmsgs');
  if(msgs){
    msgs.innerHTML=brands.filter(b=>(b.messages||[]).length).map(b=>{
      const ocr=(b.n_copy_ocr||0)>0;
      const themes=(b.themes||[]).slice(0,6).map(t=>`<span class="chip" style="cursor:default">${t.label} <span class="sub mono">${t.n}</span></span>`).join(' ');
      return `<details style="margin:6px 0"><summary style="cursor:pointer">
          <b>${b.brand}</b> <span class="sub">${b.n_messages} distinct message(s) from ${icN(b.n_with_copy)} creative(s) with readable copy — ${b.copy_coverage_pct}% of its ads</span>
          ${ocr?'<span class="tag" style="color:var(--gold);border:1px solid var(--gold)">incl. OCR · ESTIMATED</span>':''}
        </summary>
        <div class="chips" style="margin:6px 0">${themes}</div>
        <table class="tbl"><tr><th>Last shown</th><th>Ad copy</th><th>Creatives</th><th>Source</th></tr>`+
        b.messages.map(m=>`<tr>
            <td class="mono sub">${m.last||'—'}</td>
            <td style="font-size:12px">${(m.line||'').replace(/[<>]/g,'')}</td>
            <td class="mono sub">${m.n}</td>
            <td class="sub mono" style="font-size:11px">${m.src==='ocr'?'<span style="color:var(--gold)">OCR · est.</span>':'render · measured'}</td>
          </tr>`).join('')+`</table></details>`;
    }).join('')||'<p class="lead sub">No ad copy captured yet — run the pull without --no-text (and with --ocr to read image banners).</p>';
  }
  if(ro){
    const top=brands[0], us=brands.find(b=>b.is_us);
    const pushers=brands.filter(b=>(b.n_new_30d||0)>0)
                    .sort((a,b)=>(b.n_new_30d||0)-(a.n_new_30d||0));
    let lead=`<b>${top.brand} runs the most paid search/display volume</b> — ${icN(top.n_creatives)} creatives (${top.share_of_volume_pct}% of the ${icN(tot)} tracked), ${icN(top.n_live)} still live.`;
    if(pushers.length) lead+=` Freshest push: <b>${pushers[0].brand}</b> with ${icN(pushers[0].n_new_30d)} new creative(s) in the last ${m.new_window_days||30} days.`;
    if(us) lead+=` We are running <b>${icN(us.n_creatives)}</b> (${us.share_of_volume_pct}%).`;
    else lead+=` <b>We do not appear</b> in Google's Thai ad archive at all — no paid Google presence to compare against.`;
    // the sharpest competitive read in this dataset: the rate rivals put in front of customers
    const mr=(Array.isArray(RIVADS.market_rates)?RIVADS.market_rates:[]).slice()
              .sort((a,b)=>a.value-b.value);
    const perMo=mr.filter(r=>r.basis==='month'), perYr=mr.filter(r=>r.basis==='year');
    let rateLine='';
    if(perMo.length) rateLine+=` Cheapest monthly quote in market copy: <b>${perMo[0].brand} at ${perMo[0].value}%/mo</b>.`;
    if(perYr.length) rateLine+=` Cheapest annual quote: <b>${perYr[0].brand} at ${perYr[0].value}%/yr</b>.`;
    ro.innerHTML=lead+rateLine+` <span class="sub">${icN(live)} of ${icN(tot)} tracked creatives are live as of ${m.pulled||'the last pull'}.</span>`;
  }
  if(note){
    const silent=(m.no_account_found||[]);
    note.innerHTML=`Share-of-volume, <b>not</b> share-of-spend — ${m.limits?'Google publishes commercial ad dates and formats but not spend or impressions.':''} `+
      (silent.length?`Checked and found <b>no Google ad account</b> in Thailand for: ${silent.join(', ')} — a genuine absence of paid Google presence, not a gap in the pull. `:'')+
      `Source: ${m.source||'Google Ads Transparency Center'}, region ${m.region||'Thailand'}, pulled ${m.pulled||'—'}. Advertiser aggregates only — no users, no targeting, no personal data.`;
  }
  // The per-operator ad-copy sub-tables were injected into #pulseadsmsgs via innerHTML AFTER
  // boot, so the boot-time wrapTables() never reached them — an unwrapped wide table can push
  // the #acq page sideways on mobile. Re-run the idempotent wrapper (matches drawRivalPulse).
  wrapTables();
}

/* ---------- rival VIDEO pulse · YouTube Data API v3 (obj #2, MEASURED) ----------
   Surfaces data/rival_youtube.json (build_rival_youtube.py, from pull_rival_youtube.py — the
   official API, any IP, no scraping, brand channels only so no personal data). Includes our
   own เงินไชโย channel as the control. Title themes reuse the ad-copy lexicon so paid and
   organic messaging line up. Lazy, null-safe, graceful when the pull has not been run. */
let RIVVID=null, rivvidLoaded=false;
function renderRivalVideo(){
  const tbl=$('#pulsevidtbl'); if(!tbl) return;
  if(rivvidLoaded){ drawRivalVideo(); return; }
  fetch('data/rival_youtube.json').then(r=>r.ok?r.json():null).then(j=>{
    RIVVID=j; rivvidLoaded=true; drawRivalVideo();
  }).catch(()=>{ RIVVID=null; rivvidLoaded=true; drawRivalVideo(); });
}
function drawRivalVideo(){
  const tbl=$('#pulsevidtbl'), ro=$('#pulsevidreadout'), note=$('#pulsevidnote');
  if(!tbl) return;
  const ch=(RIVVID&&Array.isArray(RIVVID.channels))?RIVVID.channels:[];
  const m=(RIVVID&&RIVVID.meta)||{};
  if(!ch.length){
    tbl.innerHTML=''; if(note) note.innerHTML='';
    if(ro) ro.innerHTML='<b>Video pulse not yet pulled.</b> <span class="sub">data/rival_youtube.json is absent — set YOUTUBE_API_KEY, then run pipeline/pull_rival_youtube.py + build_rival_youtube.py.</span>';
    return;
  }
  // A channel with a tiny subscriber base but a huge median view count is BUYING placement,
  // not earning reach. Flagging it stops the table reading as organic popularity.
  const bought=c=>c.subscribers!=null&&c.median_views_365d!=null&&c.subscribers>0&&
                   c.median_views_365d>c.subscribers*3&&c.median_views_365d>5000;
  tbl.innerHTML=`<tr><th>#</th><th>Operator</th>`+
    `<th title="as published by YouTube; rounded at scale, so read as a band">Subscribers</th>`+
    `<th title="videos published in the last 30 days">Up 30d</th>`+
    `<th title="videos published in the last 365 days">Up 1yr</th>`+
    `<th title="days since the most recent upload">Last post</th>`+
    `<th title="median views of videos published in the last 365 days">Median views</th>`+
    `<th title="likes + comments per 1,000 views on the last 365 days of uploads">Engage /1k</th>`+
    `<th title="ESTIMATED — what its video titles push most (same lexicon as the ad copy)">Lead message</th>`+
    `<th title="uploads per month, oldest to newest">Cadence (24 mo)</th></tr>`+
    ch.map((c,i)=>{
      const us=c.is_us, col=us?'var(--gold)':'var(--merch)';
      const name=us?`<b style="color:var(--gold)">${c.brand}</b> <span class="tag" style="color:var(--gold);border:1px solid var(--gold)">US</span>`
                  :`<b>${c.brand}</b>`;
      const par=c.is_parent_channel?' <span class="tag" style="color:var(--dim);border:1px solid var(--dim)" title="parent auto-finance channel — markets more than title loans, excluded from share-of-voice">PARENT</span>':'';
      const dormant=(c.uploads_365d||0)===0;
      return `<tr${us?' style="background:rgba(230,180,80,.05)"':''}>
        <td class="mono sub">${i+1}</td>
        <td>${name}${par}<div class="sub" style="font-size:11px">${c.channel_title||''}</div></td>
        <td class="mono">${icN(c.subscribers)}${c.share_of_subs_pct!=null?` <span class="sub">(${c.share_of_subs_pct}%)</span>`:''}</td>
        <td class="mono" style="color:${(c.uploads_30d||0)>0?'var(--merch)':'var(--dim)'}">${icN(c.uploads_30d)}</td>
        <td class="mono ${dormant?'':'sub'}" style="color:${dormant?'var(--agri)':'inherit'}">${icN(c.uploads_365d)}</td>
        <td class="mono sub">${c.days_since_upload!=null?c.days_since_upload+'d':'—'}</td>
        <td class="mono">${icN(c.median_views_365d)}${bought(c)?' <span class="tag" style="color:var(--collat);border:1px solid var(--collat)" title="median views far exceed the subscriber base — reach is being bought, not earned">PAID</span>':''}</td>
        <td class="mono sub">${c.engagement_per_1k_365d!=null?c.engagement_per_1k_365d:'—'}</td>
        <td class="sub" style="font-size:12px">${(c.themes&&c.themes[0])?c.themes[0].label:'<span class="sub">—</span>'}</td>
        <td>${adsSpark(c.cadence,col)}</td>
      </tr>`;}).join('');
  if(ro){
    const comp=ch.filter(c=>!c.is_parent_channel);
    const busiest=comp.slice().sort((a,b)=>(b.uploads_30d||0)-(a.uploads_30d||0))[0];
    const dormant=comp.filter(c=>(c.uploads_365d||0)===0);
    const us=ch.find(c=>c.is_us);
    const paid=comp.filter(bought);
    let lead='';
    if(busiest&&(busiest.uploads_30d||0)>0)
      lead+=`<b>${busiest.brand} is publishing hardest right now</b> — ${icN(busiest.uploads_30d)} video(s) in the last 30 days.`;
    if(us) lead+=` We have <b>${icN(us.subscribers)}</b> subscribers and posted <b>${icN(us.uploads_30d)}</b> in the last 30 days${us.share_of_subs_pct!=null?` (${us.share_of_subs_pct}% of the tracked field's audience)`:''}.`;
    if(dormant.length) lead+=` <b>${dormant.map(c=>c.brand).join(', ')}</b> published nothing in a year — marketing-silent here.`;
    if(paid.length) lead+=` <span class="sub">${paid.map(c=>c.brand).join(', ')} show views far above their subscriber base — that reach is bought, not earned.</span>`;
    ro.innerHTML=lead;
  }
  if(note){
    const none=(m.no_channel_found||[]);
    note.innerHTML=(none.length?`No brand channel found for: ${none.join(', ')}. `:'')+
      (m.limits||'')+` Source: ${m.source||'YouTube Data API v3'}, pulled ${m.pulled||'—'}.`;
  }
}

/* ---------- rival pulse · live promotions + voice of customer (obj #2, MEASURED) ----------
   Surfaces data/rival_pulse.json (build_rival_pulse.py, from pull_rival_promos.py [Thai-IP pull of
   the rivals' own sites] + pull_app_reviews.py [Google Play, 5 apps incl. our own เงินไชโย]).
   Stars/histograms/promo dates MEASURED; detractor theme buckets ESTIMATED (keyword lexicon).
   Lazy, null-safe, graceful if absent. */
let RIVPULSE=null, rivpulseLoaded=false;
function renderRivalPulse(){
  const tbl=$('#pulsesenttbl'); if(!tbl) return;
  if(rivpulseLoaded){ paintPulse(); return; }
  fetch('data/rival_pulse.json').then(r=>r.ok?r.json():null).then(j=>{
    RIVPULSE=j; rivpulseLoaded=true; paintPulse();
  }).catch(()=>{ RIVPULSE=null; rivpulseLoaded=true; paintPulse(); });
}
/* PANTIP PANEL — data/pantip_panel.json (build_pantip_panel.py).
   Brand-level borrower voice, which the say/hear gap below deliberately averages away. Pantip is
   the one place Thai borrowers discuss lenders unprompted and at length.

   THREE THINGS THIS VIEW MUST NOT LET A READER BELIEVE:
     1. that the threads we retrieved measure how much a brand is discussed — search caps at 10 per
        term, so those counts are a ceiling we hit. Volume comes from Pantip's own reported total.
     2. that the reported total is clean — สมหวัง ("wish fulfilled") and ศรีสวัสดิ์ (also a district
        of Kanchanaburi) match far more than the lender. `match` is the measured share of sampled
        threads that really name the brand, and it is shown on every row, not buried in a footnote.
     3. that a rate off 10 threads is precise. Every rate is rendered as its own fraction.
   Lazy, null-safe, graceful if absent — same contract as renderRivalPulse. */
let PANTIP=null, pantipLoaded=false;
function renderPantip(){
  const tbl=$('#pantiptbl'); if(!tbl) return;
  if(pantipLoaded){ drawPantip(); return; }
  // The catch is attached to the FETCH, not to the draw. Chaining .catch() after a .then() that
  // also draws means a rendering bug is caught by the "data missing" handler and re-rendered as
  // "not yet built" — the reader is then told to go run a pipeline script for a file that is
  // sitting right there. Keep failing-to-load and failing-to-draw distinguishable.
  fetch('data/pantip_panel.json')
    .then(r=>r.ok?r.json():null)
    .catch(()=>null)
    .then(j=>{ PANTIP=j; pantipLoaded=true; drawPantip(); });
}
function drawPantip(){
  const tbl=$('#pantiptbl'), ro=$('#pantipreadout'), qs=$('#pantipquotes'), note=$('#pantipnote');
  if(!tbl) return;
  const rows=(PANTIP&&Array.isArray(PANTIP.brands))?PANTIP.brands:[];
  const m=(PANTIP&&PANTIP.meta)||{};
  if(!rows.length){
    tbl.innerHTML=''; if(qs) qs.innerHTML=''; if(note) note.textContent='';
    if(ro) ro.innerHTML='<b>Pantip panel not yet built.</b> <span class="sub">data/pantip_panel.json is absent — run pipeline/pull_pantip.py then pipeline/build_pantip_panel.py.</span>';
    return;
  }
  const n=v=>(v==null?'—':(+v).toLocaleString('en-US'));
  if(ro) ro.innerHTML=(PANTIP.headline?`<b>${escHtml(PANTIP.headline)}</b>`:'')+
    (PANTIP.reply_line?`<div class="sub" style="margin-top:6px">${escHtml(PANTIP.reply_line)}</div>`:'');

  tbl.innerHTML='<tr><th>Lender</th><th>Threads on Pantip</th><th>Match</th><th>Est. about the brand</th>'+
    '<th>Replies in public</th><th>What borrowers raise</th></tr>'+
    rows.map(b=>{
      const us=b.is_us?' style="background:var(--raised)"':'';
      // Match rate carries a colour only where it is low enough to change how the row is read.
      const mp=b.precision==null?null:Math.round(b.precision*100);
      const mcol=mp==null?'var(--dim)':(mp<50?'var(--agri)':(mp<80?'var(--gold)':'var(--merch)'));
      const rr=b.reply_rate==null
        ? '<span class="sub">too few threads</span>'
        : `<span class="mono">${b.org_reply_threads}/${b.n_threads_sampled}</span> <span class="sub">(${b.reply_rate}%)</span>`;
      return `<tr${us}><td>${b.is_us?'<b>':''}${escHtml(b.label)}${b.is_us?'</b> <span class="tag" style="color:var(--accent);border:1px solid var(--accent)">US</span>':''}`+
        `${b.tier==='category'?' <span class="sub">generic terms, no brand named</span>':''}</td>`+
        `<td class="mono">${n(b.reported_total)}<span class="sub"> claimed</span></td>`+
        `<td class="mono" style="color:${mcol}">${mp==null?'—':mp+'%'}</td>`+
        `<td class="mono">${n(b.est_threads)}</td>`+
        `<td>${rr}</td>`+
        `<td class="sub">${(b.themes||[]).slice(0,3).map(t=>escHtml(t.label)).join(' · ')||'—'}</td></tr>`;
    }).join('');

  // Quotes: us first — the point of showing these is to read our own book's complaints, not the
  // rivals'. Everything is already scrubbed and unattributed at build time.
  if(qs){
    const ordered=rows.slice().sort((a,b)=>(b.is_us?1:0)-(a.is_us?1:0));
    qs.innerHTML=ordered.filter(b=>(b.quotes||[]).length).map(b=>
      `<div class="qgrp" style="margin:10px 0 0"><div class="sub" style="font-weight:600;color:${b.is_us?'var(--accent)':'var(--mid)'}">`+
      `${escHtml(b.label)}${b.is_us?' — us':''}</div>`+
      b.quotes.map(q=>`<blockquote class="pq" lang="th">${escHtml(q.text)}`+
        `<span class="sub" style="display:block;margin-top:3px" lang="en">${escHtml(q.theme)}${q.date?' · '+escHtml(q.date):''}</span></blockquote>`).join('')+
      '</div>').join('');
  }
  if(note) note.innerHTML=[m.cap,m.name_collision,m.precision_bias,m.privacy]
    .filter(Boolean).map(s=>escHtml(s)).join(' ');
}

/* SAY / HEAR GAP — data/social_themes.json (build_social_themes.py).
   The synthesis of every reception channel on #acq: what lenders publish (ad creatives + promo
   pages) and what customers write (Pantip, Google Play, Apple, YouTube comments) counted against
   ONE Thai phrase list, so the two sides are comparable.

   Document counts are MEASURED; the theme buckets are ESTIMATED editorial judgement. Read the
   ORDERING, not the magnitude — an ad exists to make a claim while a comment is an unprompted
   reaction, so the denominators differ in kind and every gap is inflated.
   Lazy, null-safe, graceful if absent — same contract as renderRivalPulse. */
let THEMES=null, themesLoaded=false;
function renderSocialThemes(){
  const tbl=$('#themestbl'); if(!tbl) return;
  if(themesLoaded){ drawSocialThemes(); return; }
  fetch('data/social_themes.json').then(r=>r.ok?r.json():null).then(j=>{
    THEMES=j; themesLoaded=true; drawSocialThemes();
  }).catch(()=>{ THEMES=null; themesLoaded=true; drawSocialThemes(); });
}
function drawSocialThemes(){
  const tbl=$('#themestbl'), ro=$('#themesreadout'), cta=$('#themectatbl'), note=$('#themesnote');
  if(!tbl) return;
  const ans=(THEMES&&Array.isArray(THEMES.answered))?THEMES.answered:[];
  const ctas=(THEMES&&Array.isArray(THEMES.ctas))?THEMES.ctas:[];
  const m=(THEMES&&THEMES.meta)||{};
  if(!ans.length){
    tbl.innerHTML=''; if(cta) cta.innerHTML=''; if(note) note.textContent='';
    if(ro) ro.innerHTML='<b>Social themes not yet built.</b> <span class="sub">data/social_themes.json is absent — run the pulls (pull_pantip.py, pull_app_reviews.py, pull_apple_reviews.py, pull_youtube_comments.py) then pipeline/build_social_themes.py.</span>';
    return;
  }
  const pct=v=>(v==null?'—':(+v).toFixed(1)+'%');
  // Biggest over-said first: the field's loudest message against how little it is raised back.
  const over=ans.filter(a=>a.unanswered_pts<0).sort((a,b)=>a.unanswered_pts-b.unanswered_pts);
  const under=ans.filter(a=>a.unanswered_pts>0&&a.kind!=='praise').sort((a,b)=>b.unanswered_pts-a.unanswered_pts);
  if(ro){
    const top=over[0], q=under[0];
    ro.innerHTML=(top?`<b>The field's loudest message is its customers' quietest topic.</b> `+
      `<b>${pct(top.supply_share_pct)}</b> of the ${(m.supply_docs||0).toLocaleString()} lender documents push `+
      `<b>${top.label.toLowerCase()}</b>, against <b>${pct(top.demand_share_pct)}</b> of the `+
      `${(m.demand_docs||0).toLocaleString()} customer documents raising it.`:'')+
      (q?` <span class="sub">Biggest thing customers raise that nothing answers: <b>${q.label}</b> `+
      `(${pct(q.demand_share_pct)}, ${(q.demand_docs||0).toLocaleString()} documents`+
      `${q.no_counterpart?', no counterpart message at all':''}).</span>`:'');
  }
  tbl.innerHTML=`<tr><th>Theme</th><th>Lenders say</th><th>Customers raise</th><th>Imbalance</th><th>Read</th></tr>`+
    over.concat(under).map(a=>{
      const g=a.unanswered_pts, oversaid=g<0;
      const col=oversaid?'var(--collat)':'var(--gold)';
      return `<tr><td>${a.label}${a.thin?' <span class="sub">(thin)</span>':''}</td>`+
        `<td class="mono">${pct(a.supply_share_pct)}</td>`+
        `<td class="mono">${pct(a.demand_share_pct)}</td>`+
        `<td class="mono" style="color:${col}">${g>0?'+':''}${g.toFixed(1)} pts</td>`+
        `<td class="sub">${oversaid?'over-said by the field':(a.no_counterpart?'raised, nothing answers it':'under-answered')}</td></tr>`;
    }).join('');
  if(cta&&ctas.length){
    const brandsOf=c=>Object.keys(c.brands||{}).length
      ? Object.entries(c.brands).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`${k} ${v}`).join(' · ')
      : '<span style="color:var(--agri)">nobody</span>';
    // ctas is PAID only (ads + promo pages). The organic column is the same mechanic counted in the
    // lenders' unpaid forum replies — service, not campaign. Showing both is the finding: the field
    // behaves conversationally by hand and never buys it.
    const org=(THEMES&&Array.isArray(THEMES.ctas_organic))?THEMES.ctas_organic:[];
    const orgOf=k=>{const r=org.find(x=>x.key===k);return r?r.docs:0;};
    cta.innerHTML=`<tr><th>Call to action</th><th>In paid ads</th><th>Share of paid</th><th>In organic replies</th><th>Who runs it (paid)</th></tr>`+
      ctas.map(c=>`<tr><td>${c.label}</td><td class="mono">${(c.docs||0).toLocaleString()}</td>`+
        `<td class="mono">${pct(c.share_pct)}</td>`+
        `<td class="mono" style="color:var(--gold)">${orgOf(c.key)||'—'}</td>`+
        `<td class="sub">${brandsOf(c)}</td></tr>`).join('');
  }
  if(note){
    const bysrc=m.demand_by_source||{};
    const mix=Object.keys(bysrc).sort().map(k=>`${k} ${(bysrc[k].n||0).toLocaleString()}`).join(' · ');
    note.innerHTML=`Customer documents: ${mix}. `+
      `<b>Brands are not comparable across a blend of these</b> — app complaints concentrate in `+
      `app-store reviews and barely appear in comments, so a brand whose corpus is mostly reviews `+
      `looks worse on that theme by construction. Compare within one source.`+
      (m.as_of?` <span class="sub">As of ${m.as_of}.</span>`:'');
  }
}

// the iOS block rides on the SAME rival_pulse.json payload — paint both off one fetch
function paintPulse(){ drawRivalPulse(); drawRivalIos(); }
function drawRivalPulse(){
  const tbl=$('#pulsesenttbl'), ro=$('#pulsesentreadout'),
        plist=$('#pulsepromolist'), pro=$('#pulsepromoreadout');
  if(!tbl) return;
  const sent=(RIVPULSE&&Array.isArray(RIVPULSE.sentiment))?RIVPULSE.sentiment:[];
  const promos=(RIVPULSE&&Array.isArray(RIVPULSE.promos))?RIVPULSE.promos:[];
  const m=(RIVPULSE&&RIVPULSE.meta)||{};
  if(!sent.length&&!promos.length){
    tbl.innerHTML=''; if(plist) plist.innerHTML='';
    if(ro) ro.innerHTML='<b>Rival pulse not yet pulled.</b> <span class="sub">data/rival_pulse.json is absent — run pipeline/pull_rival_promos.py (Thai IP) + pull_app_reviews.py, then build_rival_pulse.py.</span>';
    if(pro) pro.innerHTML='';
    return;
  }
  // --- sentiment ladder (our own app highlighted) ---
  if(sent.length){
    tbl.innerHTML=`<tr><th>#</th><th>App</th>`+
      `<th title="lifetime Google Play score (all ratings)">Play score</th>`+
      `<th title="number of star ratings on the store page">Ratings</th>`+
      `<th title="share of ALL ratings that are 1★ (lifetime histogram)">1★ share</th>`+
      `<th title="average star of reviews in the last 90 days (from the stored newest reviews)">Last 90d</th>`+
      `<th title="share of last-90-day reviews at 1–2★">90d 1–2★</th>`+
      `<th title="share of stored reviews that got a developer reply — CX ops discipline">Dev reply</th>`+
      `<th title="ESTIMATED — keyword buckets over stored 1–2★ reviews">Top detractor theme</th></tr>`+
      sent.map((s,i)=>{
        const own=s.own, name=own?`<b style="color:var(--gold)">${s.name}</b> <span class="tag" style="color:var(--gold);border:1px solid var(--gold)">US</span>`:`<b>${s.name}</b>`;
        const sc=s.score!=null?s.score.toFixed(2):'—';
        const bar=s.score!=null?barHTML(s.score,own?'var(--gold)':'var(--merch)',5):'';
        const trendC=(s.recent90&&s.recent90.avg!=null&&s.score!=null)?(s.recent90.avg<s.score-0.15?'var(--agri)':s.recent90.avg>s.score+0.15?'var(--merch)':'var(--dim)'):'var(--dim)';
        const th=(s.themes&&s.themes[0])?`${s.themes[0].label} <span class="sub mono">×${s.themes[0].n}</span>`:'<span class="sub">—</span>';
        return `<tr${own?' style="background:rgba(230,180,80,.05)"':''}>
          <td class="mono sub">${i+1}</td>
          <td>${name} <span class="sub mono">${s.brand}</span></td>
          <td class="mono">${bar} <b>${sc}★</b></td>
          <td class="mono sub">${(s.ratings||0).toLocaleString()}</td>
          <td class="mono" style="color:${(s.detractor_pct||0)>=12?'var(--agri)':'var(--dim)'}">${s.detractor_pct!=null?s.detractor_pct+'%':'—'}</td>
          <td class="mono" style="color:${trendC}">${s.recent90&&s.recent90.avg!=null?s.recent90.avg.toFixed(2)+'★':'—'} <span class="sub">(${s.recent90?s.recent90.n:0})</span></td>
          <td class="mono" style="color:${(s.recent90&&s.recent90.low_share_pct>=25)?'var(--agri)':'var(--dim)'}">${s.recent90&&s.recent90.low_share_pct!=null?s.recent90.low_share_pct+'%':'—'}</td>
          <td class="mono sub">${s.reply_rate_pct!=null?s.reply_rate_pct+'%':'—'}</td>
          <td class="sub" style="font-size:12px">${th}</td>
        </tr>`;}).join('');
    if(ro){
      const own=sent.find(s=>s.own);
      const q=(own&&own.quotes&&own.quotes.length)?`<div style="margin-top:6px">${own.quotes.map(x=>`<div class="sub" style="font-size:12px;margin-top:2px">“${x.text}” <span class="mono">— ${'★'.repeat(x.score)} · ${x.at||''}</span></div>`).join('')}</div>`:'';
      ro.innerHTML=`${RIVPULSE.headline||''} ${TAG_M}`+q+
        methodBox(null,
          [`<b>Measured</b> — Google Play store pages (th/th): lifetime score + star histogram, plus the newest stored reviews per app (dated, public). Sentiment anchor ${m.sentiment_anchor||'—'}.`,
           `<b>Our own app is on the ladder</b> — เงินไชโย (th.co.autox.chaiyo) is the only AutoX-owned number on this tab; everything else is the rivals'.`,
           `<b>Estimated</b> — the detractor themes are keyword buckets over stored 1–2★ reviews (lexicon in the data file); read them as direction, not exact counts.`,
           m.note_installs||'']);
    }
  }
  // --- promo landscape: summarized by product / type / pricing (ESTIMATED LLM classification
  //     over MEASURED items; classify_promos_llm.py). Falls back to the raw feed when absent. ---
  const land=RIVPULSE&&RIVPULSE.promo_landscape;
  const lbox=$('#pulsepromolandscape'), rawwrap=$('#pulsepromorawwrap');
  const PRODL={title_loan_motorcycle:'Motorcycle title loan',title_loan_car:'Car title loan',
    title_loan_pickup:'Pickup title loan',title_loan_truck:'Truck title loan',
    title_loan_land:'Land title loan',personal_loan:'Personal loan',nano_finance:'Nano finance',
    hire_purchase:'Hire purchase',insurance_broking:'Insurance',corporate_or_ir:'Corporate / IR',
    other:'Other'};
  const TYPEL={rate_discount:'Rate cut',cashback:'Cashback',free_gift:'Free gift',
    lucky_draw:'Lucky draw',fee_waiver:'Fee waiver',fast_approval:'Fast approval',
    credit_line_boost:'Bigger line',refinance_offer:'Refinance',payment_relief:'Payment relief',
    partnership:'Partnership',brand_campaign:'Brand campaign',corporate_news:'Corporate news',
    content_marketing:'Article / tips',other:'Other'};
  const TYPEC={rate_discount:'var(--gold)',cashback:'var(--merch)',free_gift:'var(--merch)',
    lucky_draw:'var(--merch)',fee_waiver:'var(--gold)',fast_approval:'var(--accent)',
    credit_line_boost:'var(--accent)',refinance_offer:'var(--collat)',payment_relief:'var(--collat)',
    partnership:'var(--dim)',brand_campaign:'var(--dim)',corporate_news:'var(--dim)',other:'var(--dim)'};
  if(lbox){
    if(land&&land.by_product&&land.by_product.length){
      const chips=Object.entries(land.type_counts||{}).map(([t,n])=>
        `<span class="tag" style="color:${TYPEC[t]||'var(--dim)'};border:1px solid ${TYPEC[t]||'var(--dim)'}">${TYPEL[t]||t} ×${n}</span>`).join('');
      // flex-wrap the chip row: the .tag chips are white-space:nowrap and joined with no
      // whitespace, so an inline row has NO soft-wrap opportunity between them and runs off the
      // right edge on mobile — flex+gap gives each chip its own wrap point.
      lbox.innerHTML=`<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:6px 0 8px">${chips} <span class="tag">ESTIMATED · LLM-classified</span></div>`+
        land.by_product.map(g=>`<h4 class="compsub" style="margin:10px 0 4px">${PRODL[g.product]||g.product} <span class="sub mono">×${g.n}</span></h4>`+
          `<table class="tbl">${g.items.map(p=>`<tr>
            <td class="mono" style="white-space:nowrap"><b>${p.brand}</b></td>
            <td style="white-space:nowrap"><span class="tag" style="color:${TYPEC[p.promo_type]||'var(--dim)'};border:1px solid ${TYPEC[p.promo_type]||'var(--dim)'}">${TYPEL[p.promo_type]||p.promo_type}</span></td>
            <td class="mono" style="color:var(--gold);white-space:nowrap">${p.pricing||'<span class="sub">—</span>'}</td>
            <td class="sub" style="font-size:12px">${p.feature||''}</td>
            <td>${p.is_new?'<span class="tag" style="color:var(--gold);border:1px solid var(--gold)">NEW</span> ':''}<a href="${p.url}" target="_blank" rel="noopener" style="font-size:12px">${p.title}</a></td>
          </tr>`).join('')}</table>`).join('');
    } else {
      lbox.innerHTML='';
      if(rawwrap) rawwrap.open=true;   // no classification yet — show the raw feed un-collapsed
    }
  }
  // --- live promo feed, grouped by brand ---
  if(plist){
    const byBrand={};
    promos.forEach(p=>{(byBrand[p.brand]=byBrand[p.brand]||[]).push(p);});
    const order=['TIDLOR','SAWAD','MTC'].filter(b=>byBrand[b]);
    plist.innerHTML=order.map(b=>{
      const items=byBrand[b].slice(0,6);
      const kind=items.every(i=>i.kind==='news')?' <span class="sub">(news &amp; campaigns — MTC runs no public promo page)</span>':'';
      return `<h4 class="compsub" style="margin:10px 0 4px">${b}${kind}</h4>`+
        `<table class="tbl">${items.map(p=>`<tr>
          <td class="mono sub" style="white-space:nowrap">${p.date||p.first_seen||''}</td>
          <td>${p.is_new?'<span class="tag" style="color:var(--gold);border:1px solid var(--gold)">NEW</span> ':''}<a href="${p.url}" target="_blank" rel="noopener">${p.title}</a>${p.detail?`<div class="sub" style="font-size:11px">${p.detail}</div>`:''}</td>
        </tr>`).join('')}</table>`;
    }).join('');
    if(pro){
      const nNew=promos.filter(p=>p.is_new).length;
      pro.innerHTML=`<b>${promos.length} promotions / campaigns</b> tracked from the rivals' own websites`+
        (nNew?` — <b style="color:var(--gold)">${nNew} new</b> since the previous pull`:'')+
        `. Refreshed ${m.promos_pulled_at||'—'} (Thai-IP pull). ${TAG_M}`+
        methodBox(null,
          [`<b>Measured</b> — items published on tidlor.com (/th/promotion-activity), sawad.co.th (promotion posts) and muangthaicap.com (/news/ — MTC publishes campaigns as news). Every item carries first-seen tracking, so NEW = appeared since the previous pull.`,
           m.promos_coverage_note||'',
           `The corporate sites are geoblocked from foreign IPs — this feed refreshes from the Thai-IP laptop (pipeline/pull_rival_promos.py).`]);
    }
  }
  // The promo landscape + raw-feed tables are injected into #pulsepromolandscape / #pulsepromolist
  // via innerHTML AFTER boot, so the boot-time wrapTables() never reached them — an unwrapped wide
  // .tbl pushes the whole #acq route sideways on mobile. Re-run the idempotent wrapper here (it
  // skips tables already inside a .tblwrap) so every promo table scrolls inside its own box.
  wrapTables();
}

/* ---------- rival universe · the full จำนำทะเบียน field (obj #2) ----------
   Surfaces data/rival_universe.json (build_rival_universe.py): every material operator — us, the
   branch-led non-banks, and the bank-backed entrants — with owner, model, footprint claim
   (ESTIMATED-from-public-reports, cited in the data) and the measured Play app score joined on.
   Lazy, null-safe, graceful if absent. */
let RIVUNI=null, rivuniLoaded=false;
function renderRivalUniverse(){
  const tbl=$('#pulseunitbl'); if(!tbl) return;
  if(rivuniLoaded){ drawRivalUniverse(); return; }
  fetch('data/rival_universe.json').then(r=>r.ok?r.json():null).then(j=>{
    RIVUNI=j; rivuniLoaded=true; drawRivalUniverse();
  }).catch(()=>{ RIVUNI=null; rivuniLoaded=true; drawRivalUniverse(); });
}
function drawRivalUniverse(){
  const tbl=$('#pulseunitbl'), ro=$('#pulseunireadout'); if(!tbl) return;
  const ops=(RIVUNI&&Array.isArray(RIVUNI.operators))?RIVUNI.operators:[];
  if(!ops.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Operator census not available.</b> <span class="sub">data/rival_universe.json is absent — run pipeline/build_rival_universe.py.</span>';
    return;
  }
  const m=RIVUNI.meta||{};
  const TIER={us:'<span class="tag" style="color:var(--gold);border:1px solid var(--gold)">US</span>',
              nonbank:'<span class="tag" style="color:var(--agri);border:1px solid var(--agri)">NON-BANK</span>',
              bank:'<span class="tag" style="color:var(--accent);border:1px solid var(--accent)">BANK-BACKED</span>',
              /* 'broker' = online origination, no branches. Listed so the operator is on the record,
                 but never counted as local competitive pressure — the per-branch and per-province
                 rival counts come from the geo censuses, which only hold physical service points.
                 Without this entry the row rendered with a BLANK badge, which reads as a data bug. */
              broker:'<span class="tag" style="color:var(--dim);border:1px dashed var(--dim)">BROKER · NO BRANCHES</span>'};
  tbl.innerHTML=`<tr><th></th><th>Operator</th><th>Backing</th><th>Model</th>`+
    `<th title="each company's own public footprint claim — ESTIMATED, cited in the data file">Footprint (their claim)</th>`+
    `<th title="measured Google Play score, joined from the sentiment ladder">App</th></tr>`+
    ops.map(o=>{
      const app=o.app?`<span class="mono">${o.app.score.toFixed(2)}★</span> <span class="sub mono">(${(o.app.ratings||0).toLocaleString()})</span>`:'<span class="sub">—</span>';
      return `<tr${o.tier==='us'?' style="background:rgba(230,180,80,.05)"':''}>
        <td>${TIER[o.tier]||''}</td>
        <td><b lang="th">${o.name_th}</b><div class="sub" style="font-size:11px">${o.name_en||''}</div></td>
        <td class="sub">${o.owner||''}</td>
        <td class="sub" style="font-size:12px">${o.model||''}</td>
        <td class="sub" style="font-size:12px">${o.footprint||''}</td>
        <td>${app}</td>
      </tr>`;}).join('');
  if(ro){
    ro.innerHTML=`${RIVUNI.headline||''} <span class="tag" style="color:var(--gold);border:1px solid var(--gold)">estimated · public reports</span>`+
      methodBox(null,
        [`<b>Estimated-from-public-reports</b> — footprints are the companies' own claims (SET filings, IR, press; citations in the data file), verified ${m.verified||''}. Not our measurement.`,
         m.market_note||'',
         '<b>App scores are measured</b> (Google Play, joined from the sentiment ladder above).',
         'The bank tier competes through bank branches and apps, not storefronts — it shows up as rate/margin pressure before it shows up on a map.']);
  }
}

/* ---------- peer loan quality · reported NPL benchmark (obj #1 + #2) ----------
   Surfaces data/peer_npl.json (build_peer_npl.py): the listed title-lenders' own reported NPL
   ratios (docs/RESEARCH_DIGEST.md §B) PLUS a MEASURED AutoX self-anchor computed from the real
   loan tape (tape_real.json). Ranks the reported peers by NPL, then shows AutoX as a distinct
   MEASURED row BELOW them (NOT ranked in — different measurement basis; see the method note).
   A pure display: read the spread as the competitive loan-quality band. Lazy, graceful if absent. */
let PEERNPL=null, peernplLoaded=false;
function renderPeerNpl(){
  const tbl=$('#peernpltbl'); if(!tbl) return;
  if(peernplLoaded){ drawPeerNpl(); return; }
  fetch('data/peer_npl.json').then(r=>r.ok?r.json():null).then(j=>{
    PEERNPL=j; peernplLoaded=true; drawPeerNpl();
  }).catch(()=>{ PEERNPL=null; peernplLoaded=true; drawPeerNpl(); });
}
function drawPeerNpl(){
  const tbl=$('#peernpltbl'), ro=$('#peernplreadout'); if(!tbl) return;
  const peers=(PEERNPL&&Array.isArray(PEERNPL.peers))?PEERNPL.peers:[];
  if(!peers.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Peer NPL benchmark not available.</b> <span class="sub">data/peer_npl.json is absent — it fills in from docs/RESEARCH_DIGEST.md §B on the next data refresh.</span>';
    return;
  }
  const m=PEERNPL.meta||{};
  const list=peers.slice().sort((a,b)=>(a.npl||0)-(b.npl||0));
  const vals=list.map(p=>p.npl).filter(v=>typeof v==='number');
  const lo=Math.min(...vals), hi=Math.max(...vals);
  // colour the NPL band: lower is better (green), higher worse (red), scaled across the observed spread.
  const col=v=>{ if(hi<=lo) return 'var(--merch)'; const t=(v-lo)/(hi-lo); return t<=0.34?'var(--merch)':t>=0.67?'var(--agri)':'var(--gold)'; };
  // MEASURED AutoX self-anchor (from the real loan tape). Shown as a distinct row BELOW the
  // reported peers — NOT ranked among them (different measurement basis; see the method note).
  const ax=(PEERNPL&&PEERNPL.autox)?PEERNPL.autox:null;
  const axMax=ax?Math.max(hi,ax.npl_live_os_pct||0,4):Math.max(hi,4);
  tbl.innerHTML=`<tr><th scope="col">#</th><th scope="col">Peer</th>`+
    `<th scope="col" title="the operator's own reported non-performing-loan ratio (FY2025 / 2025 IR)">Reported NPL</th>`+
    `<th scope="col" title="the collateral mix that drives the NPL level">Collateral book</th>`+
    `<th scope="col">Source</th></tr>`+
    list.map((p,i)=>{
      const v=(typeof p.npl==='number')?p.npl:null;
      const label=p.npl_label?p.npl_label+'%':(v!=null?v.toFixed(2)+'%':'—');
      const c=v!=null?col(v):'var(--dim)';
      const bar=v!=null?barHTML(v,c,axMax):'';
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td><b>${p.name||p.ticker||'—'}</b>${p.ticker?` <span class="sub mono">${p.ticker}</span>`:''}</td>
        <td>${bar} <span class="mono" style="color:${c}"><b>${label}</b></span></td>
        <td class="sub">${p.collateral||'—'}</td>
        <td class="sub" style="font-size:11px">${p.source||'—'}</td>
      </tr>`;}).join('')+
    (ax?`<tr style="border-top:2px solid var(--accent)">
        <td class="mono sub" title="not ranked among the reported peers — a different measurement basis">—</td>
        <td><b>${ax.name}</b> <span class="tag" style="color:var(--accent);border:1px solid var(--accent);font-size:10px">MEASURED · own tape</span></td>
        <td>${barHTML(ax.npl_live_os_pct,'var(--accent)',axMax)} <span class="mono" style="color:var(--accent)"><b>${ax.npl_live_os_pct.toFixed(2)}%</b></span> <span class="sub" style="font-size:10px">live-book 90–179dpd, OS · strict 90+ ${ax.npl_90plus_os_pct.toFixed(1)}%</span></td>
        <td class="sub">${ax.collateral||'—'}</td>
        <td class="sub" style="font-size:11px">real loan tape (OS-weighted)</td>
      </tr>`:'');
  if(ro){
    const best=list[0], worst=list[list.length-1];
    const spread=(vals.length>1)?`from <b style="color:var(--merch)">${best.name} ${best.npl}%</b> (${best.collateral}) to <b style="color:var(--agri)">${worst.name} ${(worst.npl_label||worst.npl)}%</b> (${worst.collateral})`:'';
    const axLine=ax?` <b>AutoX's own book — measured from the real tape — runs NPL-live (90–179dpd) at <span style="color:var(--accent)">${ax.npl_live_os_pct.toFixed(2)}% OS-weighted</span></b>, at/above the top of that reported-peer band, consistent with its heavier motorcycle / pickup + land collateral mix.`:'';
    ro.innerHTML=`<b>The listed title-lenders' reported loan quality spans ${(hi-lo).toFixed(1)}pp</b> — ${spread}. `+
      `The gap is a <b>collateral story</b>: vehicle/gold books run the cleanest, land / heavy-vehicle / agri books the highest NPL.${axLine} ${TAG_M}`+
      methodBox(m.note||null,
        [`Peer figures are <b>reported by the companies themselves</b> (FY2025 / 2025 IR) — docs/RESEARCH_DIGEST.md §B. Vintage ${m.updated||'2026-06'}.`,
         ax?`<b>The AutoX row is MEASURED</b> from the real loan tape (${ax.basis?ax.basis.replace('MEASURED — ',''):'OS-weighted'}), not reported. ${ax.caveat||''}`:'',
         'The spread tracks collateral mix, not operator skill alone: a heavier land / agri / heavy-vehicle book carries structurally higher NPL than a vehicle/gold book at the same underwriting discipline.'].filter(Boolean));
  }
}

/* ---------- rival service reputation · measured Google ratings by brand (obj #2, MEASURED sample) ----------
   Surfaces data/rival_reputation.json (build_rival_reputation.py, from pull_place_ratings.py's Google
   Places ratings on the located rival branches). A QUALITY layer on top of rival density: review-count-
   weighted rating by brand. A SAMPLE (located rivals with a rating), and NOT an AutoX number (our own
   branches carry no Google ratings). Lazy, null-safe, graceful if absent. */
let RIVREP=null, rivrepLoaded=false;
function renderRivRep(){
  const tbl=$('#rivreptbl'); if(!tbl) return;
  if(rivrepLoaded){ drawRivRep(); return; }
  fetch('data/rival_reputation.json').then(r=>r.ok?r.json():null).then(j=>{
    RIVREP=j; rivrepLoaded=true; drawRivRep();
  }).catch(()=>{ RIVREP=null; rivrepLoaded=true; drawRivRep(); });
}
function drawRivRep(){
  const tbl=$('#rivreptbl'), ro=$('#rivrepreadout'); if(!tbl) return;
  const brands=(RIVREP&&Array.isArray(RIVREP.by_brand))?RIVREP.by_brand:[];
  if(!brands.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Rival reputation not yet computed.</b> <span class="sub">data/rival_reputation.json is absent — run pipeline/pull_place_ratings.py then build_rival_reputation.py.</span>';
    return;
  }
  const m=RIVREP.meta||{};
  const vals=brands.map(b=>b.rating_wavg).filter(v=>typeof v==='number');
  const lo=Math.min(...vals), hi=Math.max(...vals);
  // higher rating = stronger reputation (green/merch), lower = weaker (red/agri), scaled across the spread.
  const col=v=>{ if(hi<=lo) return 'var(--merch)'; const t=(v-lo)/(hi-lo); return t>=0.67?'var(--merch)':t<=0.34?'var(--agri)':'var(--gold)'; };
  tbl.innerHTML=`<tr><th>#</th><th>Rival brand</th>`+
    `<th title="review-count-weighted mean Google rating across this brand's located branches">Rating ★ (wtd)</th>`+
    `<th title="simple mean rating">Mean</th>`+
    `<th title="located branches carrying a Google rating">Rated br.</th>`+
    `<th title="total Google reviews across them">Reviews</th></tr>`+
    brands.map((b,i)=>{
      const v=(typeof b.rating_wavg==='number')?b.rating_wavg:null;
      const c=v!=null?col(v):'var(--dim)';
      const bar=v!=null?barHTML(v,c,5):'';
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td><b>${b.brand||'—'}</b></td>
        <td>${bar} <span class="mono" style="color:${c}"><b>${v!=null?v.toFixed(2):'—'}</b></span></td>
        <td class="mono sub">${b.rating_mean!=null?b.rating_mean.toFixed(2):'—'}</td>
        <td class="mono sub">${b.n_rated||0}</td>
        <td class="mono sub">${(b.reviews||0).toLocaleString()}</td>
      </tr>`;}).join('');
  if(ro){
    const pre=m.n_rated?`<b>Across ${m.n_rated} rated rival branches (${(m.reviews||0).toLocaleString()} reviews).</b> `:'';
    ro.innerHTML=pre+(RIVREP.headline||'')+` ${TAG_M}`+
      methodBox(m.note||null,
        [`<b>Measured</b> — Google Places rating + review count on the located rival branches (${m.source||'pull_place_ratings.py'}); review-count-weighted so a handful of five-star outliers can't dominate.`,
         '<b>A sample, not the full census</b> — only located rival branches that carry a Google rating; read the brand order, not hairline gaps.',
         '<b>Not an AutoX figure</b> — our own branches carry no Google ratings, so there is no comparable AutoX number here.']);
  }
}

/* ---------- rival threat matrix · footprint × service quality per brand (obj #2, MIXED) ----------
   Surfaces data/rival_threat.json (build_rival_threat.py): the density × quality JOIN — each rival's
   national footprint (company-IR headline, ESTIMATED; measured census count alongside) next to its
   measured Google service rating, so the strongest COMBINED threat reads at a glance. Footprint axis
   ESTIMATED-from-public-reports, service axis MEASURED (sample). Lazy, null-safe, graceful if absent. */
let RIVTHREAT=null, rivthreatLoaded=false;
function renderRivThreat(){
  const tbl=$('#rivthreattbl'); if(!tbl) return;
  if(rivthreatLoaded){ drawRivThreat(); return; }
  fetch('data/rival_threat.json').then(r=>r.ok?r.json():null).then(j=>{
    RIVTHREAT=j; rivthreatLoaded=true; drawRivThreat();
  }).catch(()=>{ RIVTHREAT=null; rivthreatLoaded=true; drawRivThreat(); });
}
function drawRivThreat(){
  const tbl=$('#rivthreattbl'), ro=$('#rivthreatreadout'); if(!tbl) return;
  const rows=(RIVTHREAT&&Array.isArray(RIVTHREAT.brands))?RIVTHREAT.brands:[];
  if(!rows.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Rival threat matrix not yet computed.</b> <span class="sub">data/rival_threat.json is absent — run pipeline/build_rival_threat.py (needs competitor_coverage.json + rival_reputation.json).</span>';
    return;
  }
  const m=RIVTHREAT.meta||{};
  // threat_class -> theme token (contrast-safe light+dark): combined/volume = risk-red, quality = gold, contained = teal, partial = dim.
  const cls=t=>{ if(t==='Strongest combined threat'||t==='Volume threat') return 'var(--agri)';
                 if(t==='Quality threat') return 'var(--gold)';
                 if(t==='Contained') return 'var(--merch)'; return 'var(--dim)'; };
  const fmt=n=>(n==null?'—':n.toLocaleString());
  tbl.innerHTML=`<tr><th>Rival brand</th>`+
    `<th title="branches vs the ~2,015 AutoX runs — company-IR headline (ESTIMATED); census count in the sub-line">Footprint ×AutoX</th>`+
    `<th title="review-count-weighted Google rating (MEASURED, located-branch sample)">Service ★</th>`+
    `<th title="the combined read of footprint and service">Threat</th></tr>`+
    rows.map(b=>{
      const c=cls(b.threat_class);
      const ratio=(typeof b.footprint_vs_autox==='number')?b.footprint_vs_autox:null;
      const rating=(typeof b.rating_wavg==='number')?b.rating_wavg:null;
      const fsub=b.branches_reported!=null?`${fmt(b.branches_reported)} rep · ${fmt(b.branches_found)} found`
                 :(b.branches_found!=null?`${fmt(b.branches_found)} census · no IR`:'—');
      const rsub=rating!=null?`${b.rating_tier||''} · ${fmt(b.reviews)} rev`:'no rating sampled';
      return `<tr>
        <td><b>${b.brand||'—'}</b></td>
        <td>${ratio!=null?`<span class="mono"><b>${ratio.toFixed(2)}×</b></span>`:'<span class="sub">—</span>'}<span class="sub" style="display:block">${fsub}</span></td>
        <td>${rating!=null?`${barHTML(rating,c,5)} <span class="mono" style="color:${c}"><b>${rating.toFixed(2)}</b></span>`:'<span class="sub">—</span>'}<span class="sub" style="display:block">${rsub}</span></td>
        <td style="color:${c}"><b>${b.threat_class||'—'}</b></td>
      </tr>`;}).join('');
  if(ro){
    ro.innerHTML=`<b>${RIVTHREAT.headline||''}</b> ${TAG_M}`+
      methodBox(null,
        [`<b>Footprint axis — ESTIMATED</b> (company-IR branch headline; the measured de-duped census count is shown in the sub-line). Where the census materially over-counts a brand vs its reported figure, the row says so — read the reported number.`,
         `<b>Service axis — MEASURED</b> (Google Places rating, review-count-weighted, a located-branch sample — ${m.service_axis||'not the full census'}).`,
         `<b>Not an AutoX figure</b> on the service axis — our own branches carry no Google ratings. This is a risk lens on the network we already run; it makes <b>no</b> open / close / expand recommendation.`]);
  }
}

/* ---------- rival threat by region · density × service quality where our branches sit (obj #2, MEASURED) ----------
   Surfaces data/rival_threat_region.json (build_rival_threat_region.py): the same density × quality
   join as the brand matrix, but localised to the 5 regions AutoX's branches sit in — how outgunned we
   are on the ground (measured rivals:AutoX census ratio + share of our districts rivals lead) next to
   how well-liked the rival field is (measured Google rating, a sample; thin samples flagged). Every
   region is heavily outgunned, so the defensibility CLASS is service-led. Lazy, null-safe, graceful if absent. */
let RIVTHREATREG=null, rivthreatregLoaded=false;
/* Shared loader — populates the RIVTHREATREG global once so both the Competition table and the
   command-center defensibility card read from the same fetch. Null-safe, idempotent. */
function loadRivThreatRegion(){
  if(rivthreatregLoaded) return Promise.resolve(RIVTHREATREG);
  return fetch('data/rival_threat_region.json').then(r=>r.ok?r.json():null)
    .then(j=>{ RIVTHREATREG=j; rivthreatregLoaded=true; return j; })
    .catch(()=>{ RIVTHREATREG=null; rivthreatregLoaded=true; return null; });
}
function renderRivThreatRegion(){
  const tbl=$('#rivthreatregtbl'); if(!tbl) return;
  if(rivthreatregLoaded){ drawRivThreatRegion(); return; }
  fetch('data/rival_threat_region.json').then(r=>r.ok?r.json():null).then(j=>{
    RIVTHREATREG=j; rivthreatregLoaded=true; drawRivThreatRegion();
  }).catch(()=>{ RIVTHREATREG=null; rivthreatregLoaded=true; drawRivThreatRegion(); });
}
function drawRivThreatRegion(){
  const tbl=$('#rivthreatregtbl'), ro=$('#rivthreatregreadout'); if(!tbl) return;
  const rows=(RIVTHREATREG&&Array.isArray(RIVTHREATREG.regions))?RIVTHREATREG.regions:[];
  if(!rows.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Regional rival threat not yet computed.</b> <span class="sub">data/rival_threat_region.json is absent — run pipeline/build_rival_threat_region.py (needs peer_province.json + rival_reputation.json).</span>';
    return;
  }
  // class -> theme token (contrast-safe): hardest-to-defend = risk-red, beatable-on-service = teal, most-defensible = gold.
  const cls=t=>{ if(t==='Hardest to defend') return 'var(--agri)';
                 if(t==='Beatable on service') return 'var(--merch)';
                 if(t==='Most defensible') return 'var(--gold)'; return 'var(--dim)'; };
  const fmt=n=>(n==null?'—':n.toLocaleString());
  tbl.innerHTML=`<tr><th>Region</th>`+
    `<th title="rivals:AutoX branches within the region (MEASURED census, both sides); sub-line = share of AutoX districts where rivals lead">Outgunned ×</th>`+
    `<th title="review-count-weighted Google rating for located rival branches (MEASURED sample); thin samples flagged">Rival service ★</th>`+
    `<th title="service-led defensibility class — density is high everywhere">Defensibility</th></tr>`+
    rows.map(r=>{
      const c=cls(r.threat_class);
      const ratio=(typeof r.rivals_vs_autox==='number')?r.rivals_vs_autox:null;
      const rating=(typeof r.rating_wavg==='number')?r.rating_wavg:null;
      const dsub=r.pct_districts_outnumbered!=null?`rivals lead ${r.pct_districts_outnumbered}% of our districts · ${fmt(r.autox)} vs ${fmt(r.rivals)}`:'—';
      const rsub=rating!=null?`${r.rating_tier||''} · ${fmt(r.reviews)} rev${r.thin_rating_sample?' · thin sample':''}`:'no rating sampled';
      return `<tr>
        <td><b>${r.region||'—'}</b></td>
        <td>${ratio!=null?`<span class="mono"><b>${ratio.toFixed(2)}×</b></span>`:'<span class="sub">—</span>'}<span class="sub" style="display:block">${dsub}</span></td>
        <td>${rating!=null?`${barHTML(rating,c,5)} <span class="mono" style="color:${c}"><b>${rating.toFixed(2)}</b></span>`:'<span class="sub">—</span>'}<span class="sub" style="display:block">${rsub}</span></td>
        <td style="color:${c}"><b>${r.threat_class||'—'}</b></td>
      </tr>`;}).join('');
  if(ro){
    ro.innerHTML=`<b>${RIVTHREATREG.headline||''}</b> ${TAG_M}`+
      methodBox(null,
        [`<b>Density axis — MEASURED</b> (rivals:AutoX census ratio within the region, both sides counted, plus the share of AutoX districts where rivals lead). Rivals outnumber us several-fold in every region.`,
         `<b>Service axis — MEASURED</b> (Google Places rating, review-count-weighted, a located-rival sample — thin samples are flagged; read the star figure as indicative there).`,
         `<b>Not an AutoX figure</b> on the service axis — our own branches carry no Google ratings. The class is service-led because density is high everywhere. A risk lens on the network we already run; <b>no</b> open / close / expand recommendation.`]);
  }
}

/* ---------- sub-scale rivals vs our footprint · PICO-finance per province (obj #2, MEASURED) ----------
   Surfaces data/pico_competitors.json (built by pipeline/build_pico_competitors.py): per-province
   MEASURED count of licensed PICO-finance operators (FPO registry) vs AutoX branch count, ranked by
   how much sub-scale rivals OUTNUMBER our footprint. Fully measured — two government/own tallies, no
   inference (unlike the ESTIMATED exit-whitespace cue below). Lazy, null-safe, graceful if absent. */
let PICOCOMP=null, picocompLoaded=false, picocompPromise=null;
const PICOCOMP_TOPN=15;
// Shared cached loader — the #acq leaderboard AND the home competitive-pressure card read one fetch.
function loadPicoCompetitors(){
  if(picocompPromise) return picocompPromise;
  picocompPromise=fetch('data/pico_competitors.json').then(r=>r.ok?r.json():null)
    .then(j=>{ PICOCOMP=j; picocompLoaded=true; return PICOCOMP; })
    .catch(()=>{ PICOCOMP=null; picocompLoaded=true; return null; });
  return picocompPromise;
}
// District-grain sharpening (pico_district.json, MEASURED): the FPO registry has no coordinate, but
// each operator's registered address carries an อำเภอ — parsed + exact-matched to the 928-district
// master. Sharpens the province table to "where WITHIN a province the rival field clusters". Null-safe.
let PICODIST=null, picodistLoaded=false, picodistPromise=null;
function loadPicoDistrict(){
  if(picodistPromise) return picodistPromise;
  picodistPromise=fetch('data/pico_district.json').then(r=>r.ok?r.json():null)
    .then(j=>{ PICODIST=j; picodistLoaded=true; return PICODIST; })
    .catch(()=>{ PICODIST=null; picodistLoaded=true; return null; });
  return picodistPromise;
}
function renderPicoCompetitors(){
  const tbl=$('#picocomptbl'); if(!tbl) return;
  if(picocompLoaded&&picodistLoaded){ drawPicoCompetitors(); return; }
  Promise.all([loadPicoCompetitors(),loadPicoDistrict()]).then(drawPicoCompetitors);
}
function drawPicoCompetitors(){
  const tbl=$('#picocomptbl'), ro=$('#picocompreadout'); if(!tbl) return;
  const rows=(PICOCOMP&&Array.isArray(PICOCOMP.provinces))?PICOCOMP.provinces:[];
  if(!rows.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Sub-scale rival census not yet computed.</b> <span class="sub">Run pipeline/build_pico_competitors.py (needs the FPO PICO census) — the leaderboard fills in on the next data refresh.</span>';
    return;
  }
  // measured theme tokens (contrast-safe in light + dark): PICO=gold, AutoX=teal, pressure(outnumber)=risk-red.
  const PICO='var(--gold)', AX='var(--merch)', PRESS='var(--agri)';
  const m=PICOCOMP.meta||{}, lm=m.licence_momentum||null;   // MEASURED licensing-momentum rollup (may be absent)
  const op=m.operating_momentum||null;                      // MEASURED go-live (commencement) momentum (may be absent)
  const winMo=(lm&&lm.window_months)||24;
  const top=rows.slice().sort((a,b)=>(b.outnumber||0)-(a.outnumber||0)).slice(0,PICOCOMP_TOPN);
  const maxPico=Math.max(1,...top.map(r=>r.pico_total||0));
  tbl.innerHTML=`<tr><th>#</th><th>Province</th>`+
    `<th title="MEASURED — licensed PICO-finance (พิโกไฟแนนซ์) operator service points in the province (FPO licence registry)">PICO operators ◆</th>`+
    `<th title="MEASURED — AutoX (เงินไชโย) branches in the province">AutoX branches ◆</th>`+
    `<th title="MEASURED — PICO operators minus AutoX branches. Positive (red) = sub-scale rivals outnumber our footprint here.">Outnumber ◆</th>`+
    `<th title="MEASURED — PICO operators per AutoX branch (n/a where AutoX has no branch)">Rivals / branch</th></tr>`+
    top.map((r,i)=>{
      const on=r.outnumber||0;
      const onc=on>0?PRESS:AX;
      const sign=on>0?'+':'';
      const ratio=(r.ratio==null)?'<span class="sub">n/a</span>':`<span class="mono" style="color:${on>0?PRESS:AX}">${r.ratio.toFixed(2)}×</span>`;
      const name=`<b>${r.th||'—'}</b>${r.en?` <span class="sub">${r.en}</span>`:''}`;
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td>${name}</td>
        <td>${barHTML(r.pico_total||0,PICO,maxPico)} <span class="mono" style="color:${PICO}">${r.pico_total==null?'—':r.pico_total}</span>${(r.pico_recent>0)?` <span class="sub" title="MEASURED — licensed in the trailing ${winMo} months (newly-arrived sub-scale rivals)">+${r.pico_recent} new</span>`:''}</td>
        <td>${barHTML(r.autox_branches||0,AX,maxPico)} <span class="mono" style="color:${AX}">${r.autox_branches==null?'—':r.autox_branches}</span></td>
        <td><span class="mono" style="color:${onc}"><b>${sign}${on}</b></span></td>
        <td>${ratio}</td>
      </tr>`;}).join('');
  if(ro){
    const t=top[0];
    const nOut=m.n_provinces_pico_outnumbers_autox!=null?m.n_provinces_pico_outnumbers_autox:rows.filter(r=>(r.outnumber||0)>0).length;
    const nProv=m.n_provinces||rows.length;
    let verdict='';
    if(t){
      verdict=(t.outnumber>0)
        ? `Sub-scale rivals outnumber AutoX most in <b style="color:var(--agri)">${t.th}${t.en?` (${t.en})`:''}</b> — <b style="color:var(--gold)">${t.pico_total}</b> licensed PICO operators vs <b style="color:var(--merch)">${t.autox_branches}</b> AutoX branches (${t.outnumber>0?'+':''}${t.outnumber}${t.ratio!=null?`, ${t.ratio.toFixed(2)}× our footprint`:''}).`
        : `AutoX is not outnumbered by sub-scale rivals in any province on this measure; ${t.th} is the tightest at ${t.pico_total} PICO vs ${t.autox_branches} branches.`;
    }
    // MEASURED licensing-momentum line: where the sub-scale field is NEWEST (rising pressure ≠ static density).
    let momo='';
    if(lm&&lm.n_recent!=null){
      const tr=(lm.top_recent||[])[0];
      momo=` <b>Where rival entry is newest:</b> <b style="color:var(--agri)">${lm.n_recent}</b> of ${m.pico_total!=null?m.pico_total:'—'} licensed PICO operators (${lm.recent_share_pct}%) were licensed in the trailing ${lm.window_months} months (since ${lm.cutoff_date})`+
        (tr?` — most in <b style="color:var(--gold)">${tr.th}${tr.en?` (${tr.en})`:''}</b>, where <b>${tr.pico_recent}</b> of its ${tr.pico_total} operators are new. Rising sub-scale entry is a distinct signal from existing density.`:'.');
    }
    // MEASURED operating-momentum line: where rivals recently WENT LIVE (commencement date) — distinct from
    // licence-grant, it catches operators licensed earlier that only recently opened their doors.
    let opmo='';
    if(op&&op.n_recent!=null){
      const otr=(op.top_recent||[])[0];
      opmo=` <b>Where rivals recently went live:</b> <b style="color:var(--agri)">${op.n_recent}</b> PICO operators (${op.recent_share_pct}%) began operating in the trailing ${op.window_months} months`+
        (otr?` — most in <b style="color:var(--gold)">${otr.th}${otr.en?` (${otr.en})`:''}</b> (<b>${otr.pico_recent_op}</b>). Commencement ≠ licence-grant: some went live years after licensing, so this "actually operating" lens catches live pressure the licensing lens misses.`:'.');
    }
    // MEASURED district-grain go-live sharpening (pico_district.json operating_momentum): where within
    // the provinces above rivals most recently WENT LIVE, down to the อำเภอ. Null-safe: '' if absent.
    let opdistmo='';
    const pdop=(PICODIST&&PICODIST.meta&&PICODIST.meta.operating_momentum)||null;
    if(pdop&&Array.isArray(pdop.top_recent)&&pdop.top_recent.length){
      const fmtGL=(k)=>{ const p=String(k).split('|'); return p.length===2?`<b style="color:var(--gold)">${p[1]}</b> <span class="sub">${p[0]}</span>`:`<b style="color:var(--gold)">${k}</b>`; };
      const t=pdop.top_recent[0];
      opdistmo=` At district grain the go-live pressure is sharpest in ${fmtGL(t[0])} — <b style="color:var(--agri)">${t[1]}</b> of its ${t[2]} operators went live in-window.`;
      // Compact ranked leaderboard of the top go-live districts (recent go-lives / total operators),
      // so the exec sees the whole contested-ground list, not just the single sharpest อำเภอ.
      const board=pdop.top_recent.slice(0,6).map(d=>`${fmtGL(d[0])} <span class="mono" style="color:var(--agri)">${d[1]}</span><span class="sub">/${d[2]}</span>`).join(' · ');
      if(board) opdistmo+=` <b>Top go-live districts (recent/total):</b> ${board}.`;
    }
    // MEASURED district-grain sharpening (pico_district.json): province density is not uniform — the
    // rival field clusters in the provincial-capital (เมือง) districts. Null-safe: '' if layer absent.
    const dm=(PICODIST&&PICODIST.meta)||null;
    let distClause='';
    if(dm&&Array.isArray(PICODIST.top_districts)&&PICODIST.top_districts.length){
      const fmtD=(k)=>{ const p=String(k).split('|'); return p.length===2?`<b style="color:var(--gold)">${p[1]}</b> <span class="sub">${p[0]}</span>`:`<b>${k}</b>`; };
      const tops=PICODIST.top_districts.slice(0,4).map(d=>`${fmtD(d[0])} <span class="mono" style="color:var(--gold)">${d[1]}</span>`).join(' · ');
      distClause=` <b>Within provinces, the rival field is not uniform:</b> parsing the อำเภอ out of each operator's registered address resolves `+
        `<b>${dm.n_district_resolved!=null?dm.n_district_resolved.toLocaleString():'—'}</b> of ${dm.n_operators!=null?dm.n_operators.toLocaleString():'—'} operators `+
        `(${dm.resolution_pct!=null?dm.resolution_pct:'—'}%) to <b>${dm.n_districts_present!=null?dm.n_districts_present:'—'}</b> districts — and PICO clusters in the provincial-capital (เมือง) districts: ${tops}.`;
    }
    ro.innerHTML=`<b>Where sub-scale rivals most outnumber us:</b> ${verdict} `+
      `Licensed PICO operators <b>outnumber</b> AutoX branches in <b>${nOut}</b> of ${nProv} provinces `+
      `(${m.pico_total!=null?m.pico_total:'—'} PICO operators nationwide vs ${m.autox_total!=null?m.autox_total:'—'} AutoX branches).${momo}${opmo}${opdistmo}${distClause} ${TAG_M}`+
      methodBox(null,
        ['<b>PICO operators</b> = a straight tally of licensed พิโกไฟแนนซ์ operators per province from the <b>FPO government licence registry</b> (MEASURED). A distinct small-ticket non-bank competitor class, separate from the big-4 title lenders.',
         '<b>AutoX branches</b> = our own branch count per province (MEASURED, from branches.json). <b>Outnumber</b> = PICO − AutoX; <b>Rivals/branch</b> = PICO ÷ AutoX.',
         (lm?`<b>+N new</b> / “rival entry is newest” = operators whose FPO licence-grant date (วันที่ได้รับใบอนุญาต) falls in the trailing ${lm.window_months} months before the registry snapshot (since ${lm.cutoff_date}) — MEASURED, anchored on the pinned snapshot vintage, not wall-clock. It reads rising pressure, not existing density.`:''),
         (dm?`<b>District grain:</b> the registry carries no coordinate, but each operator's registered address carries an อำเภอ (district) — parsed and exact-matched to the canonical 928-district master (pico_district.json), resolving <b>${dm.resolution_pct!=null?dm.resolution_pct:'—'}%</b> of operators (${dm.n_district_resolved!=null?dm.n_district_resolved.toLocaleString():'—'}/${dm.n_operators!=null?dm.n_operators.toLocaleString():'—'}) to ${dm.n_districts_present!=null?dm.n_districts_present:'—'} districts. The ${dm.n_unresolved!=null?dm.n_unresolved:'—'} unmatched (mostly districts absent from the 928-polygon master) are counted honestly in the layer, not dropped; the province totals above stay authoritative.`:'Province-grain: the registry carries a province of service (จังหวัดที่ให้บริการ), not a coordinate — so this is competitive density by province, not localised within it.'),
         'A licence is licensed capacity, not a guaranteed active storefront; PICO overlaps but is not identical to AutoX’s product.',
         (m.pico_vintage?`FPO registry snapshot ${m.pico_vintage}.`:'Source: FPO PICO-finance licence registry.')].filter(Boolean));
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
    if(ro) ro.innerHTML='<b>Rival-fragility cue not yet computed.</b> <span class="sub">This layer is being prepared — the leaderboard fills in on the next data refresh. The regulatory thesis above still stands.</span>';
    return;
  }
  const top=rows.slice().sort((a,b)=>(b.exit_capture_score||0)-(a.exit_capture_score||0)).slice(0,EXIT_TOPN);
  const cell=(v,color)=>{const n=Math.round(v||0); return `<td>${barHTML(n,color)} <span class="mono" style="color:${color}">${n}</span></td>`;};
  tbl.innerHTML=`<tr><th>#</th>`+
    `<th class="h-opp" title="ESTIMATED fragility cue (0–100): thin surviving big-4 field + residual sub-scale demand. Higher = the rival field here is most exposed if a marginal local operator exits under Q1-2026. NOT a measurement.">Rival-fragility ★ est</th>`+
    `<th>District (amphoe)</th><th>Province</th><th>Region</th>`+
    `<th title="AutoX branches inside the district (measured)">AutoX</th>`+
    `<th class="h-opp" title="ESTIMATED — demand the big-4 do NOT cover (demand × thin-big-4). Higher = residual market likely served by sub-scale, exit-prone operators.">Sub-scale residual est</th>`+
    `<th class="h-opp" title="MEASURED — district demand proxy minus AutoX saturation (0–100). Higher = thinner AutoX coverage.">Coverage-gap ★</th>`+
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
    ro.innerHTML=`<b>Most fragile rival field:</b> <b style="color:var(--accent)">${t.name}</b> (${t.province}, ${t.region}) tops the cue at
      <b style="color:var(--accent)">${Math.round(t.exit_capture_score)}</b>/100 — sub-scale residual ${Math.round(t0.sub_scale_proxy||0)},
      coverage-gap ${Math.round(t0.whitespace||0)}, big-4 branches ${t0.big4_competitors==null?'—':t0.big4_competitors}.
      <span class="sub">Top ${top.length} of ${rows.length} districts. ESTIMATED PROXY — inferred from big-4 scarcity (${cc.points_joined||0} censused points, brands: ${(cc.brands_censused||[]).join(' · ')||'—'}) × local demand, NOT a measurement of sub-scale operators. Thesis: registration window closes ${dl}; marginal lenders may exit.</span>`;
  }
}

/* ---------- nationwide acquisition leaderboard (item 2) ----------
   Ranks all 2,015 branch catchments by a white-space score computed client-side from
   data already present: high demand proxy (k10 footfall + district workers + province
   pickups + precomputed 'o' opportunity) against LOW own-AutoX saturation (w = ≤10km).
   Everything here is an ESTIMATED screen, not a site-survey. */
let gapRegion='all', gapRows=[];
// White-space score v2 — a defensible screen, not a site survey. Three legs, all from data present:
//   DEMAND  (0–1, avg of 4 proxies): footfall (cvs+rest+fmkt·3), DIW district factory workers,
//           province pickup stock (title collateral), and the precomputed opportunity 'o'.
//   SATURATION penalty: own AutoX ≤10km (w) — more of our own branches = less headroom.
//   COMPETITOR penalty (proxy, labelled): nearby banks+ATMs (k10) stand in for rival financial
//           presence — we have NO national lender-branch census (only 30 hand-curated competitors
//           in Rayong), so this is an OSM financial-density proxy, NOT a competitor count.
// Score = demand × ownHeadroom × compHeadroom, scaled 0–100. Each leg returned for transparency.
function gapLegs(d){
  const pl=(typeof PLOOK!=='undefined'&&PLOOK)?(PLOOK[d.v]||{}):{};
  const k=d.k10||{};
  const foot=((k.cvs||0)+(k.rest||0)+(k.fmkt||0)*3);
  const demand=(norm(foot,GAPN.foot)+norm(d.dwork||0,GAPN.dwork)+norm(pl.pickup||0,GAPN.pickup)+norm(d.o||0,GAPN.o))/4;
  // own-AutoX headroom: 1 at zero own branches, decays toward 0.35 floor as saturation rises.
  const ownHead=0.35+0.65*(1-Math.min(1,(d.w||0)/8));
  // competitor (financial-density proxy) headroom: dense banks+ATMs => slightly less white space.
  const fin=(k.bank||0)+(k.atm||0);
  const compHead=0.6+0.4*(1-Math.min(1,fin/(GAPN.fin||1)));
  return {demand,ownHead,compHead,fin};
}
function gapScore(d){const L=gapLegs(d); return Math.round(100*L.demand*L.ownHead*L.compHead);}
let GAPN={};
function buildGapNorms(){
  const mx=f=>Math.max(1,...DATA.map(f));
  // 90th-pct cap for the financial-density proxy so a couple of CBD outliers don't flatten everyone.
  const fins=DATA.map(d=>{const k=d.k10||{};return (k.bank||0)+(k.atm||0);}).sort((a,b)=>a-b);
  GAPN={
    foot:mx(d=>{const k=d.k10||{};return (k.cvs||0)+(k.rest||0)+(k.fmkt||0)*3;}),
    dwork:mx(d=>d.dwork||0),
    pickup:mx(d=>(PLOOK[d.v]||{}).pickup||0),
    o:mx(d=>d.o||0),
    fin:Math.max(1,fins[Math.floor(fins.length*0.9)]||1),
  };
}
function norm(v,mx){return Math.min(1,(v||0)/(mx||1));}
function renderGapBoard(){
  if(!$('#gapboard')) return;
  buildGapNorms();
  if(!$('#gapchips').dataset.init){
    const regions=['all',...Array.from(new Set(DATA.map(d=>d.r)))];
    $('#gapchips').setAttribute('role','group'); $('#gapchips').setAttribute('aria-label','Filter by region');
    $('#gapchips').innerHTML=regions.map((r,i)=>`<button class="chip ${i===0?'on':''}" data-r="${r}" aria-pressed="${i===0}">${r==='all'?'All regions':r}</button>`).join('');
    $('#gapchips').onclick=e=>{const b=e.target.closest('.chip'); if(!b)return;
      $('#gapchips').querySelectorAll('.chip').forEach(c=>{const on=c===b;c.classList.toggle('on',on);c.setAttribute('aria-pressed',String(on));});
      gapRegion=b.dataset.r; drawGapBoard();};
    $('#gapcsv').onclick=gapCSV; $('#gapchips').dataset.init='1';
  }
  drawGapBoard();
  // lazily fold the competitor census into the board so "underserved" can be re-read as
  // "underserved AND undercompeted". Null-safe: if the file is absent the column shows "n/a".
  if(!compAttached) loadCompetitors().then(()=>{ drawGapBoard(); });  // always redraw when census lands (was guarded on v-acq being visible, so the Rivals column stuck on 'n/a' until a chip click)
}
// Per-region ranking: which region has the most white space on average + the single best opening.
function drawGapRegions(){
  if(!$('#gapregions')) return;
  const byReg={};
  DATA.forEach(d=>{const r=d.r||'—'; const s=gapScore(d);
    const o=byReg[r]||(byReg[r]={r,n:0,sum:0,top:null,topS:-1});
    o.n++; o.sum+=s; if(s>o.topS){o.topS=s; o.top=d;}});
  const regs=Object.values(byReg).map(o=>({...o,avg:o.sum/o.n})).sort((a,b)=>b.avg-a.avg);
  const mxAvg=Math.max(1,...regs.map(o=>o.avg));
  $('#gapregions').innerHTML=`<tr><th>#</th><th>Region</th><th>Catchments</th><th class="h-opp" title="mean coverage-gap score across the region (est)">Avg coverage-gap ★ est</th><th>Widest single gap (est)</th></tr>`+
    regs.map((o,i)=>{const sc=o.avg>=45?'var(--gold)':o.avg>=30?'var(--merch)':'var(--mid)';
      return `<tr onclick="location.href='${branchHref(o.top)}'" tabindex="0" role="link" style="cursor:pointer">
      <td class="mono sub">${i+1}</td><td><b>${o.r}</b></td>
      <td class="mono sub">${o.n.toLocaleString()}</td>
      <td>${barHTML(o.avg,sc,mxAvg)} <span class="mono" style="color:${sc}">${o.avg.toFixed(1)}</span></td>
      <td class="sub">${o.top.n} <span class="mono" style="color:var(--gold)">★ ${o.topS}</span> · ${o.top.v}</td></tr>`;}).join('');
  // plain-language readout: lead with the answer.
  const best=regs[0], top1=gapRows[0];
  if($('#gapreadout')&&best&&top1){
    const t=top1.d, L=gapLegs(t);
    const drivers=[];
    if(L.demand>=0.4) drivers.push('strong demand signals');
    if(t.w<=2) drivers.push(`almost no own AutoX nearby (${t.w} ≤10km)`);
    else if(t.w<=5) drivers.push(`thin own coverage (${t.w} ≤10km)`);
    if((t.dwork||0)>=8000) drivers.push(`${Math.round((t.dwork||0)/1000)}k factory workers in the district`);
    const scope=gapRegion==='all'?'nationwide':`in ${gapRegion}`;
    $('#gapreadout').innerHTML=`<b>Widest coverage gap:</b> ${t.n} (${t.v}, ${t.r}) tops the screen ${scope}
      at <b style="color:var(--gold)">★ ${top1.s}</b>${drivers.length?' — '+drivers.join(', ')+'.':'.'}
      By region, <b>${best.r}</b> shows the widest average coverage gap (★ ${best.avg.toFixed(1)} across ${best.n.toLocaleString()} catchments).
      <span class="sub">Estimated coverage screen — a competitive-exposure read, not a site survey or an open-a-branch recommendation.</span>`;
  }
}
function drawGapBoard(){
  gapRows=DATA.filter(d=>gapRegion==='all'||d.r===gapRegion)
    .map(d=>({d, s:gapScore(d)})).sort((a,b)=>b.s-a.s).slice(0,60);
  drawGapRegions();
  const haveComp=compHasData();
  $('#gaptbl').innerHTML=`<tr><th>#</th><th class="h-opp" title="ESTIMATED coverage-gap screen: demand proxy × own-AutoX headroom × competitor-proxy headroom (0–100)">Coverage-gap ★ est</th><th>Branch / area</th><th>Prov</th><th>Region</th><th title="own AutoX ≤10km — lower = thinner coverage">AutoX ≤10km</th>`+
    `<th class="h-collat" title="MEASURED rival title-loan / vehicle-finance branches within ~5km (Google Places, a lower bound — not a registry). Low rivals + high coverage-gap = thinly-covered AND undercompeted.">Rivals ≤5km ◆ meas</th>`+
    `<th class="h-opp" title="DIW factory workers (measured)">Workers (DIW)</th><th title="province pickup stock (DLT)">Pickups (prov)</th><th title="banks+ATMs ≤10km (OSM) — financial-density proxy for rival presence, NOT a competitor census">Fin. density ◇ est</th></tr>`+
    gapRows.map((row,i)=>{const d=row.d, pl=PLOOK[d.v]||{}; const sc=row.s>=60?'var(--gold)':row.s>=40?'var(--merch)':'var(--mid)';
      const hd=d.w<=2?' · gap':d.w<=5?' · thin':' · covered';
      const k=d.k10||{}; const fin=(k.bank||0)+(k.atm||0);
      // competitor cell: measured count + an "undercompeted" flag when high white-space meets few rivals.
      const cn=compCount(d);
      const under = haveComp && row.s>=40 && cn===0;
      const compCell = !haveComp
        ? '<span class="sub" title="competitor census not loaded yet">n/a</span>'
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
  const cnote=$('#gapcompnote');
  if(cnote){
    if(!compLoaded){ cnote.innerHTML='<span class="sub">Loading competitor census…</span>'; }
    else if(!haveComp){ cnote.innerHTML='<span class="sub"><b>Rivals ≤5km</b> is blank — the competitor census isn\'t loaded yet. Once it refreshes, this column fills with measured rival-branch counts, turning "underserved" into "underserved <b>and</b> undercompeted".</span>'; }
    else {
      const flagged=gapRows.filter(row=>row.s>=40&&compCount(row.d)===0).length;
      cnote.innerHTML=`<span class="sub"><b>✦ ${flagged}</b> of the top ${gapRows.length} catchments are <b>thinly-covered AND undercompeted</b> — high coverage-gap with <b>zero</b> measured rival branches within ${COMP_RADIUS_KM}km. `+
        `Competitor counts are <b>measured</b> (Google Places) but a <b>lower bound</b>, not a lender registry.</span>`;
    }
  }
}
function gapCSV(){
  const haveComp=compHasData();
  const hdr=['rank','whitespace_score_est','demand_proxy_0_1_est','own_headroom_0_1_est','competitor_headroom_proxy_0_1_est','branch','province','region','own_autox_10km','rival_branches_5km_measured_lower_bound','undercompeted_flag','factory_workers_diw','province_pickups_dlt','fin_density_banks_atms_10km_est','opportunity_o_est'];
  const lines=[hdr.join(',')].concat(gapRows.map((row,i)=>{const d=row.d, pl=PLOOK[d.v]||{}; const L=gapLegs(d);
    const cn=compCount(d); const under=haveComp&&row.s>=40&&cn===0;
    return [i+1,row.s,L.demand.toFixed(3),L.ownHead.toFixed(3),L.compHead.toFixed(3),d.n,d.v,d.r,d.w,haveComp?cn:'',under?'yes':(haveComp?'no':''),d.dwork==null?'':d.dwork,pl.pickup==null?'':pl.pickup,L.fin,d.o==null?'':d.o]
      .map(v=>`"${String(v==null?'':v).replace(/"/g,'""')}"`).join(',');}));
  const blob=new Blob(['\ufeff',lines.join('\n')],{type:'text/csv;charset=utf-8;'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='autox_catchment_coverage.csv'; a.click(); URL.revokeObjectURL(a.href);
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

/* ---------- district (amphoe) CHOROPLETH polygons (National map) ----------
   Lazy-loads data/amphoe_geo.json — the SIMPLIFIED 928 amphoe boundary polygons
   (pipeline/build_amphoe_geo.py, Douglas–Peucker of th_amphoe.geojson, ~1.3MB). Each
   feature carries only properties.id (== amphoe.json id == shapeID). We paint them as a
   Leaflet choropleth UNDER the branch dots when a district lens (dws/drisk) is active,
   colouring each polygon by lensColor() of its lens value. Fully optional + null-safe:
   if the file is absent or fails to load the map behaves exactly as today (dots only). */
let AGEO=null, ageoLoaded=false, ageoPromise=null, ampById=null, ampChoroLayer=null;
function loadAmphoeGeo(){
  if(ageoPromise) return ageoPromise;
  ageoLoaded=true;
  ageoPromise=(async()=>{
    try{
      const j=await fetch('data/amphoe_geo.json').then(r=>r.ok?r.json():null);
      AGEO=(j&&Array.isArray(j.features))?j.features:null;
    }catch(e){ AGEO=null; }
    return AGEO;
  })();
  return ageoPromise;
}
// true when lens k is amphoe-keyed (reads d._amp / paints the district choropleth) — read off the
// LENS registry's own amp:true flag instead of a hand-maintained list of lens keys, so a future
// amp lens (LENS.foo={amp:true,...}) wires into the choropleth + join-warming automatically.
function isAmpLens(k){ return !!(LENS[k]&&LENS[k].amp); }

/* ---------- crop land-use (district dominant-crop) — CATEGORICAL amp lens ----------
   Lazy-loads data/crop_landuse.json (pipeline/build_crop_landuse.py — SPAM 2010 crop areas
   sampled into the 928 amphoe by point-in-polygon; ESTIMATED, model-allocated). Keyed by the
   amphoe `id` (== amphoe.json id == amphoe_geo feature id), so both the district choropleth and
   the branch dots colour categorically by dominant_crop. Fully optional + null-safe: absent file
   → CROPLU stays null, the lens hides itself (lensAbsent) and the paths below no-op. */
let CROPLU=null, cropLuLoaded=false, cropLuPromise=null, cropById=null;
const CROP_COLORS={rice:'#4E9A6B',cassava:'#A97432',maize:'#E0A03A',sugarcane:'#EBCB54',oilpalm:'#5F7A46',rubber:'#2E6E66'};
const CROP_LABEL={rice:'Rice',cassava:'Cassava',maize:'Maize',sugarcane:'Sugarcane',oilpalm:'Oil palm',rubber:'Rubber'};
function loadCropLanduse(){
  if(cropLuPromise) return cropLuPromise;
  cropLuLoaded=true;
  cropLuPromise=(async()=>{
    try{ const j=await fetch('data/crop_landuse.json').then(r=>r.ok?r.json():null);
      CROPLU=(j&&Array.isArray(j.amphoe))?j:null; }
    catch(e){ CROPLU=null; }
    return CROPLU;
  })();
  return cropLuPromise;
}
function cropHasData(){ return !!(CROPLU&&Array.isArray(CROPLU.amphoe)&&CROPLU.amphoe.length); }
function cropLuIndex(){
  if(cropById||!cropHasData()) return cropById;
  cropById={}; for(const e of CROPLU.amphoe){ if(e&&e.id!=null) cropById[e.id]=e; }
  return cropById;
}
// dominant-crop record for an amphoe.json record (by its id) — null when the file/entry is absent.
function cropRecForAmp(a){ const idx=cropLuIndex(); return (idx&&a&&a.id!=null)?(idx[a.id]||null):null; }
// id -> amphoe record lookup, built once from AMP (the scored districts).
function ampIndex(){
  if(ampById||!AMP) return ampById;
  ampById={}; for(const a of AMP){ if(a&&a.id!=null) ampById[a.id]=a; }
  return ampById;
}
// add / refresh / remove the choropleth to match the active lens. Idempotent + guarded:
// requires the map, the polygon file (AGEO) and the scored records (AMP). On a non-district
// lens it simply removes the layer, so branch lenses look exactly as before.
function drawAmphoeChoropleth(){
  if(!mapReady||!map||typeof L==='undefined'||!L.geoJSON) return;
  const on=isAmpLens(curLens);
  if(!on||!AGEO||!AMP){
    if(ampChoroLayer){ map.removeLayer(ampChoroLayer); ampChoroLayer=null; }
    return;
  }
  const l=LENS[curLens], idx=ampIndex();
  if(!l||!idx) return;
  const cat=!!l.cat;   // categorical (dominant-crop) lens vs continuous ramp
  // colour scale: max lens value across the SCORED districts (not the polygons) so the
  // ramp matches the dot legend. sqrt easing to match styleMarkers(). (unused for cat lenses)
  const mx=cat?1:Math.max(1,...AMP.map(a=>{ const v=l.val({_amp:a}); return (typeof v==='number'&&isFinite(v))?v:0; }));
  // rebuild fresh each time the lens changes (cheap; 928 light polygons, canvas-rendered)
  if(ampChoroLayer){ map.removeLayer(ampChoroLayer); ampChoroLayer=null; }
  const renderer=L.canvas({padding:0.5});
  ampChoroLayer=L.geoJSON({type:'FeatureCollection',features:AGEO},{
    renderer,
    style:f=>{
      const a=idx[f.properties&&f.properties.id];
      if(cat){
        const e=a?cropRecForAmp(a):null; const dc=e&&e.dominant_crop;
        return {fillColor:dc?(CROP_COLORS[dc]||'#8a94a8'):'rgba(70,80,100,.35)',
                fillOpacity:dc?0.62:0.18, color:'rgba(20,26,34,.28)', weight:0.4, interactive:true};
      }
      const v=a?l.val({_amp:a}):0;
      const t=Math.max(0,Math.min(1,(typeof v==='number'&&isFinite(v)?v:0)/mx));
      return {fillColor:lensColor(Math.sqrt(t),l.color), fillOpacity:0.5,
              color:'rgba(20,26,34,.28)', weight:0.4, interactive:true};
    },
    onEachFeature:(f,layer)=>{
      const a=idx[f.properties&&f.properties.id]; if(!a) return;
      const nm=a.name_measured?`${a.name} <span class="sub">${a.name_en||''}</span>`:(a.name_en||a.name||'');
      if(cat){
        const e=cropRecForAmp(a); const dc=e&&e.dominant_crop;
        const col=dc?(CROP_COLORS[dc]||'#8a94a8'):'#8a94a8';
        const shr=(dc&&e.shares&&e.shares[dc]!=null)?Math.round(e.shares[dc]*100)+'%':'';
        const cs=(e&&e.cropland_share!=null)?Math.round(e.cropland_share*100)+'%':'n/a';
        layer.bindPopup(`<div class="pop" style="min-width:0"><div class="pn" style="color:${col}">◇ ${nm}</div>`+
          `<div class="pv">${a.province_th||''}${a.region?' · '+a.region:''}</div>`+
          `<div class="sub" style="margin-top:4px">Dominant crop: <b style="color:${col}">${dc?(CROP_LABEL[dc]||dc):'none (SPAM)'}</b>${shr?' '+shr:''}</div>`+
          `<div class="sub">Tracked-crop land share: ${cs} · <span title="SPAM 2010 model-allocated crop areas">estimated · SPAM</span></div>`+
          `<div class="sub">AutoX branches inside: ${a.branches!=null?a.branches:'n/a'}</div></div>`,
          {closeButton:true,maxWidth:260});
        return;
      }
      const v=l.val({_amp:a});
      const unit=l.unit||'';
      const vtxt=(typeof v==='number'&&isFinite(v))?Math.round(v):'n/a';
      layer.bindPopup(`<div class="pop" style="min-width:0"><div class="pn" style="color:${l.color}">◇ ${nm}</div>`+
        `<div class="pv">${a.province_th||''}${a.region?' · '+a.region:''}</div>`+
        `<div class="sub" style="margin-top:4px"><b style="color:${l.color}">${vtxt}</b> ${unit}</div>`+
        `<div class="sub">AutoX branches inside: ${a.branches!=null?a.branches:'n/a'}</div></div>`,
        {closeButton:true,maxWidth:260});
    }
  });
  ampChoroLayer.addTo(map);
  // keep the choropleth BENEATH the branch dots (canvas markers) so dots stay clickable on top.
  if(ampChoroLayer.bringToBack) ampChoroLayer.bringToBack();
}

/* ---------- province CHOROPLETH polygons (National map) ----------
   hhdti/pstress are PROVINCE-resolution values (one number per province, not per district),
   so every branch in a province used to share a colour and paint as many same-coloured dots —
   read as noise instead of one clean shape (docs/IMPROVEMENT_BACKLOG.md, 2026-07-03 (2)/(5)).
   Lazy-loads data/province_geo.json (pipeline/build_province_geo.py — the amphoe polygons
   regrouped by province, no new geometry). Paints UNDER the branch dots exactly like the
   amphoe choropleth. Optional + null-safe: absent/failed file leaves PGEO null and this is a
   no-op (dots only, unchanged behaviour). */
let PGEO=null, pgeoLoaded=false, pgeoPromise=null, provChoroLayer=null;
function loadProvinceGeo(){
  if(pgeoPromise) return pgeoPromise;
  pgeoLoaded=true;
  pgeoPromise=(async()=>{
    try{
      const j=await fetch('data/province_geo.json').then(r=>r.ok?r.json():null);
      PGEO=(j&&Array.isArray(j.features))?j.features:null;
    }catch(e){ PGEO=null; }
    return PGEO;
  })();
  return pgeoPromise;
}
// true when lens k is province-keyed (reads d.v directly, one value per province) — same
// registry-flag pattern as isAmpLens so a future province lens wires in automatically.
function isProvLens(k){ return !!(LENS[k]&&LENS[k].prov); }
function drawProvinceChoropleth(){
  if(!mapReady||!map||typeof L==='undefined'||!L.geoJSON) return;
  const on=isProvLens(curLens);
  if(!on||!PGEO){
    if(provChoroLayer){ map.removeLayer(provChoroLayer); provChoroLayer=null; }
    return;
  }
  const l=LENS[curLens];
  if(!l) return;
  // colour scale keyed off the same per-province lists the lens itself reads (HHRISK_LIST /
  // PSTRESS_LIST), so the ramp matches the dot legend exactly.
  const mx=Math.max(1,...(PGEO.map(f=>{ const v=l.val({v:(f.properties||{}).province}); return (typeof v==='number'&&isFinite(v))?v:0; })));
  if(provChoroLayer){ map.removeLayer(provChoroLayer); provChoroLayer=null; }
  const renderer=L.canvas({padding:0.5});
  provChoroLayer=L.geoJSON({type:'FeatureCollection',features:PGEO},{
    renderer,
    style:f=>{
      const prov=(f.properties||{}).province;
      const v=l.val({v:prov});
      const t=Math.max(0,Math.min(1,(typeof v==='number'&&isFinite(v)?v:0)/mx));
      return {fillColor:lensColor(Math.sqrt(t),l.color), fillOpacity:0.45,
              color:'rgba(20,26,34,.28)', weight:0.4, interactive:true};
    },
    onEachFeature:(f,layer)=>{
      const prov=(f.properties||{}).province; if(!prov) return;
      const v=l.val({v:prov});
      const unit=l.unit||'';
      const vtxt=(typeof v==='number'&&isFinite(v))?v:'n/a';
      layer.bindPopup(`<div class="pop" style="min-width:0"><div class="pn" style="color:${l.color}">● ${prov}</div>`+
        `<div class="sub" style="margin-top:4px"><b style="color:${l.color}">${vtxt}</b> ${unit}</div></div>`,
        {closeButton:true,maxWidth:260});
    }
  });
  provChoroLayer.addTo(map);
  // keep the choropleth BENEATH the branch dots (canvas markers) so dots stay clickable on top.
  if(provChoroLayer.bringToBack) provChoroLayer.bringToBack();
}
function ampChips(id,cur,onPick){
  const box=$(id); if(!box||box.dataset.init) return;
  const regions=['all',...Array.from(new Set(AMP.map(a=>a.region)))];
  box.setAttribute('role','group'); box.setAttribute('aria-label','Filter by region');
  box.innerHTML=regions.map(r=>`<button class="chip ${r===cur?'on':''}" data-r="${r}" aria-pressed="${r===cur}">${r==='all'?'All regions':r}</button>`).join('');
  box.onclick=e=>{const b=e.target.closest('.chip'); if(!b)return;
    box.querySelectorAll('.chip').forEach(c=>{const on=c===b;c.classList.toggle('on',on);c.setAttribute('aria-pressed',String(on));}); onPick(b.dataset.r);};
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
  const reAmphoe=()=>{ if(document.getElementById('v-acq')&&document.getElementById('v-acq').classList.contains('on')) drawAmpBoard(); };
  if(!aoccLoaded) loadAmphoeOccupations().then(reAmphoe);
  if(!compAttached) loadCompetitors().then(reAmphoe);
}
function drawAmpBoard(){
  ampRows=AMP.filter(a=>ampRegion==='all'||a.region===ampRegion)
    .sort((x,y)=>(y.whitespace||0)-(x.whitespace||0)).slice(0,25);
  const mx=Math.max(1,...ampRows.map(a=>a.whitespace||0));
  const haveOcc=aoccHasData();      // measured dominant-occupation per district (Overture)
  const haveComp=compHasData();     // measured rival census near the district centroid
  $('#amptbl').innerHTML=`<tr><th scope="col">#</th>`+
    `<th scope="col" class="h-opp" title="ESTIMATED coverage-gap score (0–100): district demand proxy minus an AutoX-presence penalty. Higher = thinner AutoX coverage.">Coverage-gap ★ est</th>`+
    `<th scope="col">District</th><th scope="col">Province</th><th scope="col">Region</th>`+
    `<th scope="col" title="AutoX branches inside this amphoe (MEASURED, point-in-polygon). 0 = no own presence at all.">AutoX</th>`+
    (haveOcc?`<th scope="col" class="h-collat" title="MEASURED dominant occupation/establishment bucket inside the district (Overture Maps Places, a sample/lower bound) — the borrower base you'd be lending into. From amphoe_occupations.json.">Borrower base ◆ meas</th>`:'')+
    (haveComp?`<th scope="col" class="h-collat" title="MEASURED rival title-loan / vehicle-finance branches within ~${COMP_RADIUS_KM}km of the district centre (Google Places ∪ Overture, a lower bound — not a registry). Low rivals + high coverage-gap = thinly-covered AND undercompeted.">Rivals ≤${COMP_RADIUS_KM}km ◆ meas</th>`:'')+
    `<th scope="col" class="h-opp" title="DIW factory workers in the district (MEASURED where ✓; — where the district name didn't resolve to DIW)">Workers (DIW)</th>`+
    `<th scope="col" title="convenience stores + restaurants inside the amphoe (OSM, MEASURED) — merchant footfall proxy">Merchant POI ◇</th>`+
    `<th scope="col" title="gold shops + vehicle dealers inside the amphoe (OSM, MEASURED) — title/gold-collateral demand proxy">Collat POI ◇</th></tr>`+
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
      const clk=(a.cy!=null&&a.cx!=null)?` onclick="focusDistrictOnMap(${i},'ws')" tabindex="0" role="link" style="cursor:pointer" title="Show this district on the national map →"`:'';
      return `<tr${clk}>
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
      $('#ampreadout').innerHTML=`<b>Widest coverage gap ${scope}:</b> ${top.name_measured?top.name:''} ${top.name_en} (${top.province_th}, ${top.region})
        at <b style="color:var(--gold)">★ ${(top.whitespace||0).toFixed(0)}</b> — ${drivers.join(', ')}.
        ${zeros?`<b>${zeros}</b> of the top 25 ${scope} have <b>zero AutoX presence</b>. `:''}
        <span class="sub">Estimated coverage gap; borrower base &amp; rival counts measured (Overture / Google Places, lower bounds). A competitive-exposure read, not an open-a-branch recommendation.</span>`;
    }
  }
}
/* ---------- district → national-map drill-down (interaction spine) ----------
   Click a white-space leaderboard row → jump to the National map, switch to the district
   white-space lens, fly to the district centroid (cx,cy from amphoe.json, MEASURED polygon
   centroid), and drop a gold ping + label so the underserved district is unmistakable on the
   map. Deferred via pendingMapFocus because the map may not be initialised yet (lazy tab).
   Fully null-guarded: no centroid → row isn't clickable; every Leaflet call is try/caught. */
let pendingMapFocus=null, focusMarker=null;
function focusDistrictOnMap(i,kind){
  const risk=(kind==='risk');
  const a=((risk?ampRRows:ampRows)||[])[i]||null; if(!a||a.cy==null||a.cx==null) return;
  const val=risk?(a.risk_proxy||0):(a.whitespace||0);
  pendingMapFocus={lat:a.cy,lng:a.cx,name:a.name_measured?a.name:a.name_en,val,label:risk?'risk ▲':'coverage gap ★'};
  const lens=risk?'drisk':'dws';
  if(curLens!==lens){ curLens=lens; if(typeof renderLenses==='function') try{renderLenses();}catch(e){} }
  history.replaceState(null,'','#map'); showTab('map');
}
function applyMapFocus(){
  if(!pendingMapFocus||!mapReady||!map||!window.L) return;
  const f=pendingMapFocus; pendingMapFocus=null;
  try{
    if(focusMarker){ try{map.removeLayer(focusMarker);}catch(e){} focusMarker=null; }
    map.flyTo([f.lat,f.lng], 12, {duration:0.9});
    focusMarker=L.circleMarker([f.lat,f.lng],{radius:12,weight:2.5,color:'#E6B450',opacity:0.95,fill:false});
    focusMarker.addTo(map);
    focusMarker.bindTooltip(`${f.name} · ${f.label||'coverage gap ★'} ${Math.round(f.val!=null?f.val:(f.ws||0))}`,
      {permanent:true,direction:'top',offset:[0,-8],className:'focus-tip'}).openTooltip();
  }catch(e){}
}
function drawAmpRisk(){
  ampRRows=AMP.filter(a=>ampRRegion==='all'||a.region===ampRRegion)
    .sort((x,y)=>(y.risk_proxy||0)-(x.risk_proxy||0)).slice(0,25);
  const mx=Math.max(1,...ampRRows.map(a=>a.risk_proxy||0));
  $('#amprtbl').innerHTML=`<tr><th scope="col">#</th>`+
    `<th scope="col" class="h-opp" title="ESTIMATED risk proxy (0–100): 0.4·agri crop-stress + 0.2·unemployment stress (MEASURED NSO rate, scaled) + collateral/merchant pressure. NOT a measured default rate.">Risk ▲ est</th>`+
    `<th scope="col">District</th><th scope="col">Province</th><th scope="col">Region</th>`+
    `<th scope="col" title="province-mean agri crop-stress (price proxy × drought) — PROVINCE-INHERITED, not amphoe-measured">Agri stress ▲ est</th>`+
    `<th scope="col" title="province unemployment rate — MEASURED · NSO Labour Force Survey, province-inherited">Unemployment</th>`+
    `<th scope="col" title="AutoX branches inside this amphoe (MEASURED) — footprint exposed to the stress">AutoX</th></tr>`+
    ampRRows.map((a,i)=>{const rk=a.risk_proxy||0; const sc=rk>=60?'var(--agri)':rk>=45?'#D9742B':'var(--mid)';
      const clk=(a.cy!=null&&a.cx!=null)?` onclick="focusDistrictOnMap(${i},'risk')" tabindex="0" role="link" style="cursor:pointer" title="Show this district on the national map →"`:'';
      return `<tr${clk}>
        <td class="mono sub">${i+1}</td>
        <td>${barHTML(rk,sc,mx)} <span class="mono" style="color:${sc}">${rk.toFixed(0)}</span></td>
        <td>${ampName(a)}</td>
        <td class="sub">${a.province_th}</td><td class="sub">${a.region}</td>
        <td class="mono" style="color:var(--agri)">${(a.agri_stress||0).toFixed(0)} <span class="sub" title="province-inherited">prov</span></td>
        <td class="mono sub">${a.unemployment_rate!=null?a.unemployment_rate.toFixed(2)+'%':'—'}</td>
        <td class="mono ${a.branches?'':'sub'}">${a.branches}</td></tr>`;}).join('');
}
function ampCSV(){
  const rows=AMP.filter(a=>ampRegion==='all'||a.region===ampRegion)
    .sort((x,y)=>(y.whitespace||0)-(x.whitespace||0));
  const hdr=['rank','whitespace_score_est','district_th','district_en','province','region','autox_branches_measured',
    'dominant_occupation_measured_overture','dominant_occupation_share','rival_branches_5km_centroid_measured_lower_bound',
    'diw_workers','diw_workers_measured','merchant_poi_cvs_rest_measured','collateral_poi_gold_veh_measured',
    'demand_proxy_est','risk_proxy_est','agri_stress_province_inherited','unemployment_rate_pct_measured_nso_province_inherited'];
  const lines=[hdr.join(',')].concat(rows.map((a,i)=>{const p=a.poi||{};
    const dom=ampDomOcc(a); const sh=ampDomShare(a); const cn=ampCompCount(a);
    return [i+1,(a.whitespace||0).toFixed(1),a.name_measured?a.name:'',a.name_en,a.province_th,a.region,a.branches,
      dom||'',dom?sh.toFixed(3):'',cn==null?'':cn,
      a.fac_measured?(a.workers||0):'',a.fac_measured?'true':'false',(p.cvs||0)+(p.rest||0),(p.gold||0)+(p.veh||0),
      (a.demand||0).toFixed(1),(a.risk_proxy||0).toFixed(1),(a.agri_stress||0).toFixed(1),
      a.unemployment_rate!=null?a.unemployment_rate.toFixed(2):'']
      .map(v=>`"${String(v==null?'':v).replace(/"/g,'""')}"`).join(',');}));
  const blob=new Blob(['\ufeff',lines.join('\n')],{type:'text/csv;charset=utf-8;'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='autox_district_coverage.csv'; a.click(); URL.revokeObjectURL(a.href);
}

/* ---------- portfolio exposure / concentration (item 3) ----------
   "How much of the book sits in stressed-crop / drought / weak-segment provinces."
   Book proxy = branch count (we have no per-branch ฿ balance), labelled honestly.
   Uses branch fields already present: r (region), rain (drought proxy), a/m/c risk proxies,
   and the region's weakest-crop YoY from the commodity board. */
function renderExposureTape(){
  const wrap=$('#expo-tape'); if(!wrap) return;
  if(!TAPE){ wrap.style.display='none'; return; }
  wrap.style.display='';
  const N=n=>Number(n).toLocaleString(), bnf=n=>'฿'+(n/1e9).toFixed(1)+'bn';
  const sev=v=>v==null?'var(--dim)':v<8?'var(--merch)':v<14?'#9CB24E':v<20?'var(--opp)':v<26?'#D97A3A':'var(--agri)';

  // --- two-book split KPI cards (live book vs 180+ legacy) ---
  const bk=$('#expo-tape-books');
  if(bk&&TAPE.bucket_ladder){
    const lb=TAPE.bucket_ladder.live_book, lg=TAPE.bucket_ladder.legacy_180plus, bt=TAPE.bucket_ladder.book_total;
    bk.innerHTML=[
      ['Whole book',N(bt.n),bnf(bt.os_sum)+' OS'],
      ['Live book',N(lb.n),bnf(lb.os_sum)+' · Current…150dpd'],
      ['NPL-live (90–179)',lb.npl_live_pct+'%',lb.npl_live_os_pct+'% OS-weighted'],
      ['180+ legacy',bnf(lg.os_sum),N(lg.n)+' a/c · held apart'],
    ].map(k=>`<div class="mcard"><div class="k">${k[0]}</div><div class="v">${k[1]}</div><div class="n">${k[2]}</div></div>`).join('');
  }
  // --- bucket ladder (Current → NPL → legacy) ---
  const lad=$('#expo-tape-ladder');
  if(lad&&TAPE.bucket_ladder){
    const LBL={'1.Current':'Current','2.X_Days':'X-days','3.30_dpd':'30 dpd','4.60_dpd':'60 dpd','5.90_dpd':'90 dpd','6.120_dpd':'120 dpd','7.150_dpd':'150 dpd','8.180+_dpd':'180+ legacy'};
    const L=TAPE.bucket_ladder.ladder, maxN=Math.max(...L.map(x=>x.n));
    lad.innerHTML=`<tr><th scope="col">Bucket</th><th scope="col">Accounts</th><th scope="col">OS ฿bn</th><th scope="col"></th></tr>`+
      L.map(x=>{const lg=x.bucket[0]==='8';
        return `<tr><td class="mono">${LBL[x.bucket]||x.bucket}</td><td class="mono sub">${N(x.n)}</td>
          <td class="mono sub">${(x.os_sum/1e9).toFixed(2)}</td>
          <td>${barHTML(x.n,lg?'var(--collat)':'var(--accent)',maxN)}</td></tr>`;}).join('');
  }
  // --- restructuring: did it hold? ---
  const rs=$('#expo-tape-restr');
  if(rs&&TAPE.restructuring&&TAPE.restructuring.by_status){
    const rows=['Normal','Skip','Pre-emptive','TDR'].map(s=>TAPE.restructuring.by_status.find(x=>x.status===s)).filter(Boolean);
    rs.innerHTML=`<tr><th scope="col">Status</th><th scope="col">Accounts</th><th scope="col">90+</th><th scope="col">180+</th><th scope="col" title="avg NPAT margin per account">NPAT/acct</th></tr>`+
      rows.map(r=>{const neg=r.npat_margin_avg<0;
        return `<tr><td><b>${r.status}</b></td><td class="mono sub">${N(r.n)}</td>
          <td class="mono"><b style="color:${sev(r.dpd90p_pct)}">${r.dpd90p_pct}%</b></td>
          <td class="mono" style="color:${sev(r.late180_pct)}">${r.late180_pct}%</td>
          <td class="mono" style="color:${neg?'var(--agri)':'var(--merch)'}">${neg?'−':''}฿${N(Math.abs(r.npat_margin_avg))}</td></tr>`;}).join('');
  }

  const ltv=$('#expo-tape-ltv'), occ=$('#expo-tape-occ');
  if(ltv&&TAPE.ltv_ladder){
    const rows=Object.entries(TAPE.ltv_ladder).sort((a,b)=>a[0].localeCompare(b[0]));
    const worst=Math.max(...rows.map(([,v])=>v.dpd90p_pct));
    ltv.innerHTML=`<tr><th scope="col">LTV band</th><th scope="col">Accounts</th><th scope="col" title="share of accounts 90+ days past due">90+dpd</th><th scope="col">OS ฿bn</th></tr>`+
      rows.map(([k,v])=>`<tr><td class="mono">${k}</td><td class="mono sub">${N(v.n)}</td>
        <td class="mono" style="color:${sev(v.dpd90p_pct)}">${barHTML(v.dpd90p_pct,'var(--agri)',worst)} <b>${v.dpd90p_pct}%</b></td>
        <td class="mono sub">${(v.os_sum/1e9).toFixed(1)}</td></tr>`).join('');
  }
  if(occ&&TAPE.occupations){
    const rows=Object.entries(TAPE.occupations).filter(([k])=>k!=='(blank)').sort((a,b)=>b[1].n-a[1].n);
    occ.innerHTML=`<tr><th scope="col">Occupation</th><th scope="col">Accounts</th><th scope="col">90+dpd</th><th scope="col" title="X-days: late but under 30dpd — the pre-emptive assistance window">X-days</th><th scope="col" title="average NPAT margin per account, ฿">NPAT/acct</th><th scope="col">OS ฿bn</th></tr>`+
      rows.map(([k,v])=>`<tr><td>${k}</td><td class="mono sub">${N(v.n)}</td>
        <td class="mono" style="color:${sev(v.dpd90p_pct)}"><b>${v.dpd90p_pct}%</b></td>
        <td class="mono sub">${v.early_pct}%</td>
        <td class="mono" style="color:${v.npat_margin_avg<0?'var(--agri)':'var(--merch)'}">${v.npat_margin_avg.toLocaleString()}</td>
        <td class="mono sub">${(v.os_sum/1e9).toFixed(1)}</td></tr>`).join('');
  }
  const fr=$('#expo-tape-frontier');
  if(fr&&Array.isArray(TAPE.npat_frontier)){
    const cells=TAPE.npat_frontier.slice(0,18);
    fr.innerHTML=`<tr><th scope="col">Occupation</th><th scope="col">Region</th><th scope="col">Accounts</th><th scope="col">90+dpd</th><th scope="col">NPAT/acct</th><th scope="col" title="profitably risky = high dpd but positive margin; unprofitably safe = low dpd, negative margin">Read</th></tr>`+
      cells.map(c=>{
        const read=c.npat_margin_avg>=0
          ?(c.dpd90p_pct>=16?'<span style="color:var(--opp)">profitably risky</span>':'<span style="color:var(--merch)">core</span>')
          :(c.dpd90p_pct<12?'<span style="color:var(--agri)">unprofitably safe</span>':'<span style="color:var(--agri)">re-price</span>');
        return `<tr><td>${c.occupation}</td><td class="mono sub">${c.region}</td>
          <td class="mono sub">${N(c.n)}</td>
          <td class="mono" style="color:${sev(c.dpd90p_pct)}">${c.dpd90p_pct}%</td>
          <td class="mono" style="color:${c.npat_margin_avg<0?'var(--agri)':'var(--merch)'}">${c.npat_margin_avg.toLocaleString()}</td>
          <td class="sub" style="font-size:12px">${read}</td></tr>`;}).join('');
  }
  const co=$('#expo-tape-coll');
  if(co&&TAPE.collateral_brands){
    const brands=Object.entries(TAPE.collateral_brands).slice(0,10);
    const bands=[...new Set(brands.flatMap(([,d])=>Object.keys(d)))].sort();
    co.innerHTML=`<tr><th scope="col">Brand</th>`+bands.map(b=>`<th scope="col" class="mono" style="font-size:10px">${b.replace(/^\d\.\(?|\)?yr\.$/g,'')}y</th>`).join('')+`</tr>`+
      brands.map(([br,d])=>`<tr><td><b>${br}</b></td>`+bands.map(b=>{
        const c=d[b];
        if(!c) return '<td class="sub">—</td>';
        return `<td class="mono" style="font-size:11px" title="${c.n} accounts · ${c.dpd30p_pct}% 30+dpd">${(c.eval_avg/1000).toFixed(0)}k<br><span style="color:${c.dpd30p_pct>=30?'var(--agri)':'var(--dim)'};font-size:10px">${c.dpd30p_pct}%</span></td>`;
      }).join('')+`</tr>`).join('');
  }
}
function renderExposure(){
  if(!DATA||!$('#expocards')||!$('#expotbl')) return;
  loadTapeReal().then(renderExposureTape);
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
  // the .n note is line-clamped to 2 lines here (see #expocards .mcard .n in styles.css) so the 2x2
  // row scans as one set; carry the full note (incl. the measured/estimated provenance caveat) in a
  // title so the clipped tail stays recoverable on hover / to screen readers — no visual change.
  const hhiNote=`${hhiLabel} · footprint spread over ${provCount} provinces · book proxy = branch count`;
  $('#expocards').innerHTML=
    `<div class="mcard"><div class="k">◆ Geographic concentration (HHI)</div>
       <div class="v" style="color:${hhiCol}">${Math.round(hhi).toLocaleString()}</div>
       <div class="n" title="${dqEsc(hhiNote)}">${hhiNote}</div></div>`+
    cards.map(([k,n,p,note,col,gl])=>{
    const cn=`${n.toLocaleString()} of ${N.toLocaleString()} branches · ${note}`;
    return `<div class="mcard"><div class="k">${gl} ${k}</div><div class="v" style="color:${col}">${p}</div>
     <div class="n" title="${dqEsc(cn)}">${cn}</div></div>`;}).join('');
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
    $('#expoprov').innerHTML=`<tr><th scope="col">#</th><th scope="col">Province</th><th scope="col">Region</th><th scope="col">Branches</th><th scope="col" class="h-agri" title="branches carrying ≥1 stress flag (est)">Exposed (est)</th><th scope="col" title="exposed share of the province's branches">Share</th><th scope="col">Flags</th></tr>`+
      provs.map((o,i)=>{const sh=o.n?100*o.flag/o.n:0; const fc=sh>=66?'var(--agri)':sh>=33?'var(--gold)':'var(--mid)';
        const fl=[o.str?'▼crop':'',o.dry?'☀dry':'',o.agri?'▲agri':''].filter(Boolean).join(' · ');
        return `<tr><td class="mono sub">${i+1}</td><td><b>${o.v}</b></td><td class="sub">${o.r}</td>
        <td class="mono">${o.n}</td><td class="mono" style="color:${fc}">${o.flag}</td>
        <td class="mono" style="color:${fc}">${sh.toFixed(0)}%</td><td class="sub">${fl||'—'}</td></tr>`;}).join('');
  }
  const regs=Object.entries(byReg).sort((a,b)=>b[1].n-a[1].n);
  $('#expotbl').innerHTML=`<tr><th scope="col">Region</th><th scope="col">Branches</th><th scope="col" class="h-agri" title="share in stressed-crop region (est)">Stressed-crop ▼ est</th><th scope="col" class="h-opp" title="share in dry quartile (est)">Drought ☀ est</th><th scope="col" class="h-agri" title="share with high agri-PD proxy (est)">High agri-PD ▲ est</th></tr>`+
    regs.map(([r,o])=>{const wc=regionWorstCrop(r);
      return `<tr><td><b>${r}</b>${wc?` <span class="sub">${wc.lab} ${wc.yoy>0?'+':''}${wc.yoy}%</span>`:''}</td>
      <td class="mono">${o.n}</td>
      <td class="mono" style="color:${o.str/o.n>0.5?'var(--agri)':'var(--mid)'}">${(100*o.str/o.n).toFixed(0)}%</td>
      <td class="mono" style="color:${o.dry/o.n>0.3?'var(--gold)':'var(--mid)'}">${(100*o.dry/o.n).toFixed(0)}%</td>
      <td class="mono" style="color:${o.agri/o.n>0.3?'var(--agri)':'var(--mid)'}">${(100*o.agri/o.n).toFixed(0)}%</td></tr>`;}).join('');
  // OBJECTIVE #1: portfolio concentration by region (segment mix + HHI) — lead with the headline.
  renderConcentration();
  // OBJECTIVE #1: borrower-base concentration — is the book over-exposed to one occupation type?
  renderOccConcentration();
  // OBJECTIVE #1: composite-risk readouts — most-stressed provinces + riskiest branches (lazy, graceful).
  renderRiskReadouts();
  // OBJECTIVE #2: most contested ground — catchments where rivals sit on top of our population (measured).
  renderContestedGround();
}

/* ---------- most contested ground · contested population (objective #2, MEASURED) ----------
   Surfaces data/contested_pop.json (pipeline/build_contested_pop.py): for each branch, the WorldPop
   2020 population inside its 10km catchment and the MEASURED share of it also living within 2km of
   any rival in the merged competitor census. The .top list ships pre-ranked (share desc, pop10>=25k
   stated rule); we show the top 10. Lazy + graceful: absent file → renders nothing. DOM host is
   created in-JS after #expo-risk (falls back to #expoprov) so no index.html wiring is needed. */
function contestedHost(){
  let h=document.getElementById('expo-contested');
  if(h) return h;
  const anchor=document.getElementById('expo-risk')||document.getElementById('expoprov');
  if(!anchor||!anchor.parentNode) return null;
  h=document.createElement('div'); h.id='expo-contested'; h.style.marginTop='18px';
  anchor.parentNode.insertBefore(h,anchor.nextSibling);
  return h;
}
function renderContestedGround(){
  const host=contestedHost(); if(!host) return;
  if(!CPOP){
    if(!cpopLoaded) loadContestedPop().then(()=>{ if(onExposureView()) renderContestedGround(); });
    host.innerHTML=''; return;                       // graceful: nothing until the layer lands
  }
  const top=(Array.isArray(CPOP.top)?CPOP.top:[]).slice(0,10);
  if(!top.length){ host.innerHTML=''; return; }
  const natSh=(CPOP.meta&&CPOP.meta.national_contested_share_pct!=null)?CPOP.meta.national_contested_share_pct:null;
  host.innerHTML=
    `<h2 class="risk" style="margin-top:0">Most contested ground ${TAG_M}</h2>`+
    `<p class="lead">Top ${top.length} branches by the share of their <b>10km catchment population</b> that also lives `+
    `<b>within 2km of a rival branch</b> — <b>measured</b> (WorldPop 2020 × merged competitor census). This is where `+
    `AutoX and the rivals fight for the same people${natSh!=null?`; nationally <b>${natSh}%</b> of our catchment population is contested`:''}.</p>`+
    methodBox('A 1km WorldPop cell counts as CONTESTED when its centre lies within 2km of any rival in the merged census; share = contested people ÷ catchment people.',
      ['Population is <b>measured</b> — WorldPop 2020 (1km grid, UN-adjusted).',
       'The census misses Heng’s full network (sample) and all sub-scale local operators — contested share is a <b>lower bound</b>.',
       'Only branches with ≥25k catchment population are ranked (stated rule — keeps tiny catchments from posting empty 100%s).'])+
    `<table class="tbl" id="expo-contested-tbl"><tr><th scope="col">#</th><th scope="col">Branch</th><th scope="col">Province</th>`+
    `<th scope="col" title="WorldPop 2020 population inside the 10km catchment — measured">Catchment pop</th>`+
    `<th scope="col" class="h-agri" title="people of that catchment also within 2km of a rival — measured, census lower bound">Contested people</th>`+
    `<th scope="col" class="h-agri" title="contested ÷ catchment — measured share">Share</th></tr>`+
    top.map((t,rank)=>{
      const col=t.pct>=60?'var(--agri)':t.pct>=35?'var(--gold)':'var(--merch)';
      return `<tr><td class="mono sub">${rank+1}</td><td><b>${t.name||'—'}</b></td><td class="sub">${t.prov||'—'}${t.region?' · '+t.region:''}</td>`+
        `<td class="mono">${(t.pop||0).toLocaleString()}</td>`+
        `<td class="mono" style="color:${col}">${(t.cpop||0).toLocaleString()}</td>`+
        `<td class="mono" style="color:${col}">${t.pct}%</td></tr>`;
    }).join('')+`</table>`;
}

/* ---------- portfolio concentration by region · segment mix + HHI (objective #1) ----------
   Surfaces data/segment_exposure.json (national + 5 regions + 77 provinces; built by
   pipeline/build_segment_exposure.py). For each region we show its dominant segment, a stacked
   agri/merchant/collateral mix bar (CLAUDE.md colours), and the rescaled HHI 0–1 concentration.
   We DO NOT recompute anything — just read & display. ESTIMATED: the a/m/c segment scores are
   estimated proxies, so this is a STRUCTURAL footprint concentration, not a measured loss/AUM
   concentration. Lazy-loaded once; renders nothing gracefully when the file is absent. */
let SEGEXP=null, segexpLoaded=false;
const SEG_LABEL={agri:'agri',merchant:'merchant',collateral:'collateral'};
// LEAD WITH THE VERDICT — colored card at the top of the Exposure tab, built ONLY from segment_exposure.
// top = the most-concentrated region record; null → card hidden (graceful, no fabrication).
function renderExpoVerdict(top){
  const box=$('#expo-verdict'); if(!box) return;
  if(!top||!top.region){ box.style.display='none'; box.innerHTML=''; return; }
  const hhi=(top.hhi||0).toFixed(2);
  const dom=SEG_LABEL[top.dominant_segment]||top.dominant_segment||'mixed';
  box.style.display='block';
  box.innerHTML=`<div class="verdict-line">🔴 <b>${top.region}</b> is the most concentrated region — HHI ${hhi}, dominant <b>${dom}</b></div>`+
    `<div class="sub" style="margin-top:4px">${(top.n_branches||0)} branches · higher HHI = the footprint leans on one segment ${TAG_E}</div>`;
}
function renderConcentration(){
  const host=document.getElementById('expoconc'); if(!host) return;
  if(!segexpLoaded){
    segexpLoaded=true;
    fetch('data/segment_exposure.json').then(r=>r.ok?r.json():null).then(j=>{ SEGEXP=j; if(onExposureView()) renderConcentration(); })
      .catch(()=>{ SEGEXP=null; if(onExposureView()) renderConcentration(); });
    return;   // first paint waits for the fetch
  }
  const regions=(SEGEXP&&Array.isArray(SEGEXP.regions))?SEGEXP.regions:[];
  if(!regions.length){ host.innerHTML=''; renderExpoVerdict(null); return; }   // graceful: render nothing when absent
  // headline: most- and least-concentrated regions (regions already sorted most-concentrated-first).
  const sorted=regions.slice().sort((a,b)=>(b.hhi||0)-(a.hhi||0));
  const top=sorted[0];
  renderExpoVerdict(top);   // LEAD WITH THE VERDICT — most-concentrated region card at the top of the tab
  const agriLed=sorted.filter(r=>(r.dominant_segment==='agri')).map(r=>r.region);
  const agriTxt=agriLed.length?` ${agriLed.join(' & ')} ${agriLed.length>1?'are':'is'} agri-led.`:'';
  const head=`<b>${top.region} is near-pure ${SEG_LABEL[top.dominant_segment]||top.dominant_segment} (HHI ${(top.hhi||0).toFixed(2)})</b>`+
    (top.dominant_segment==='collateral'?' — the least-diversified region':'')+`.${agriTxt}`+
    ` Higher HHI = the footprint leans on one segment.`;
  const seg=(o,k)=>Math.round(100*((o.segment_mix||{})[k]||0));
  const rowsHtml=regions.map(o=>{
    const a=seg(o,'agri'),m=seg(o,'merchant'),c=seg(o,'collateral');
    const hhi=(o.hhi||0).toFixed(2);
    const hcol=(o.hhi||0)>=0.5?'var(--agri)':(o.hhi||0)>=0.25?'var(--gold)':'var(--merch)';
    const segCol=o.dominant_segment==='agri'?'var(--agri)':o.dominant_segment==='merchant'?'var(--merch)':'var(--collat)';
    return `<div class="conc-row">`+
      `<div class="conc-hd"><span class="conc-name">${o.region}</span>`+
        `<span class="conc-dom">${(o.n_branches||0)} branches · dominant <b style="color:${segCol}">${SEG_LABEL[o.dominant_segment]||o.dominant_segment}</b></span>`+
        `<span class="conc-hhi" style="color:${hcol}">${hhi}<span class="s"> HHI</span></span></div>`+
      `<div class="mix" title="agri ${a}% · merchant ${m}% · collateral ${c}%">`+
        (a?`<span class="ma" style="width:${a}%"></span>`:'')+
        (m?`<span class="mm" style="width:${m}%"></span>`:'')+
        (c?`<span class="mc" style="width:${c}%"></span>`:'')+`</div></div>`;
  }).join('');
  const nat=SEGEXP.national||{};
  const cav=(SEGEXP.meta&&Array.isArray(SEGEXP.meta.caveats))?SEGEXP.meta.caveats:[];
  host.innerHTML=`<h2 class="risk" style="margin-top:0">Portfolio concentration by region ${TAG_E}</h2>`+
    `<p class="conc-lead">${head}</p>`+
    `<div class="conc-legend"><span><i style="background:var(--agri)"></i>agri</span>`+
      `<span><i style="background:var(--merch)"></i>merchant</span>`+
      `<span><i style="background:var(--collat)"></i>collateral</span>`+
      (nat.hhi!=null?`<span style="margin-left:auto">national HHI ${(nat.hhi||0).toFixed(2)} · dominant ${SEG_LABEL[nat.dominant_segment]||nat.dominant_segment||'—'}</span>`:'')+`</div>`+
    rowsHtml+
    methodBox('HHI is a rescaled Herfindahl of the segment mix: 0 = balanced across agri/merchant/collateral, 1 = a single segment. The mix is the share of a region’s branches whose dominant segment (argmax of the a/m/c scores) is each of the three.',
      cav.concat(['Per-region segment mix and HHI are derived from <b>estimated</b> segment proxy scores — a structural footprint read, labelled est.']));
}
function onExposureView(){const v=document.getElementById('v-exposure'); return v&&v.classList.contains('on');}

/* ---------- composite-risk readouts on #exposure (objective #1) ----------
   Two exec-readable panels built from the risk layers that already ship but are under-shown:
   • Most-stressed provinces — top ~12 by mean composite_risk (province_risk.json) with a bar +
     branch count + dominant driver.
   • Riskiest branches — top-15 by composite_risk (branch_risk.json, index-aligned to branches.json,
     so name=DATA[i].n / province=DATA[i].v) with the dominant driver.
   Both are ESTIMATED COMPOSITE (mean/composite are aggregates of the estimated branch score; the bar
   max is the worst observed mean, so bars are relative). Lazy-load on first paint, re-render when data
   lands; render NOTHING when the source file is absent. DOM hosts are created in-JS and inserted after
   #expoprov's container so no extra index.html wiring is needed beyond the existing dash2-main. */
function riskHost(){
  let h=document.getElementById('expo-risk');
  if(h) return h;
  const t=document.getElementById('expoprov'); if(!t) return null;
  // attach after the provinces table inside dash2-main so it fills the widescreen right column.
  const anchor=t; h=document.createElement('div'); h.id='expo-risk'; h.style.marginTop='18px';
  anchor.parentNode.insertBefore(h,anchor.nextSibling);
  return h;
}
function renderRiskReadouts(){
  const host=riskHost(); if(!host) return;
  const onExp=()=>{const v=document.getElementById('v-exposure'); return v&&v.classList.contains('on');};
  if(!priskLoaded) loadProvinceRisk().then(()=>{ if(onExp()) renderRiskReadouts(); });
  if(!briskLoaded) loadBranchRisk().then(()=>{ if(onExp()) renderRiskReadouts(); });
  if(!pstressLoaded) loadProvinceStress().then(()=>{ if(onExp()) renderRiskReadouts(); });
  if(!occincLoaded) loadOccupationIncome().then(()=>{ if(onExp()) renderRiskReadouts(); });
  if(!smeincLoaded) loadSmeIncome().then(()=>{ if(onExp()) renderRiskReadouts(); });
  let html='';
  // 1) MOST-STRESSED PROVINCES (province_risk.json)
  if(priskHasData()){
    const top=PRISK_LIST.slice(0,12);
    const max=Math.max(1,...top.map(p=>p.mean_risk||0));
    html+=`<h2 class="risk" style="margin-top:0">Most-stressed provinces ${TAG_E}</h2>`+
      `<p class="lead">Top ${top.length} provinces by <b>mean composite risk</b> — one fused read of "which areas are getting riskier". Bars are relative to the worst.</p>`+
      methodBox('One fused read blending measured household debt + crop/drought + occupation + segment/collateral mix.',
        ['Branch counts are <b>measured</b>.',
         'Mean / p90 are aggregates of an <b>estimated composite</b> (0–100), <b>not</b> a measured default rate.',
         'Bars are relative to the worst-observed mean, so they rank — they are not an absolute scale.'])+
      `<div class="cc-card-b">`+top.map((p,i)=>{
        const w=Math.round(180*(p.mean_risk||0)/max);
        const dom=priskDom(p);
        return `<div class="cc-row"><div class="l">${i+1}. ${p.province}`+
          `<span class="s">${p.region||''} · ${(p.n_branches||0)} branches · ${riskDriverLabel(dom)}${dom==='household'?' '+TAG_M:' '+TAG_E}</span></div>`+
          `<div class="r" style="min-width:240px">`+
            `<span class="bar" style="width:180px;display:inline-block"><i style="width:${w}px;background:var(--agri)"></i></span> `+
            `<span class="mono" style="color:var(--agri)">${(p.mean_risk||0).toFixed(1)}</span>`+
            `<span class="s">p90 ${(p.p90_risk||0).toFixed(0)}</span></div></div>`;
      }).join('')+`</div>`;
  }
  // 1b) STRUCTURAL household-leverage read (province_stress_index.json: DTI + unemployment
  // percentiles, both MEASURED NSO legs). Distinct signal from the composite above (that one
  // blends agri/collateral/merchant/unemployment) — this is the pure borrower-leverage read,
  // same rank-1-surfacing pattern already used on the Home command-center risk card.
  if(pstressHasData()&&PSTRESS_LIST.length){
    const p=PSTRESS_LIST[0];
    html+=`<div class="cc-sub2" style="margin-top:14px">Structurally riskiest · household DTI + unemployment ${TAG_E}</div>`+
      `<div class="cc-card-b">`+ccRow(`${p.province} <span class="s">${p.region||''}</span>`,
        `DTI ${p.debt_to_income!=null?(+p.debt_to_income).toFixed(2)+'×':'—'} · unemployment ${p.unemployment_rate!=null?(+p.unemployment_rate).toFixed(1)+'%':'—'} (NSO, measured)`,
        `▲ ${(p.composite_stress||0).toFixed(0)}`,'composite','var(--agri)')+`</div>`;
  }
  // 1c) LOWEST-PAID OCCUPATION NATIONALLY (occupation_income.json) — a concrete income-floor
  // fact (not an index), same rank-1-surfacing pattern as the DTI+unemployment callout above.
  if(occincHasData()){
    const c=OCCINC_LIST[0];
    html+=`<div class="cc-sub2" style="margin-top:14px">Lowest-paid occupation nationally ${TAG_M}</div>`+
      `<div class="cc-card-b">`+ccRow(`${c.label}`,
        `worst: ${c.min_province} ฿${(c.min_value||0).toLocaleString()}/mo (NSO SES 2566, measured)`,
        `฿${(c.national_avg||0).toLocaleString()}`,'national avg/mo','var(--agri)')+`</div>`;
  }
  // 1d) MERCHANT-SEGMENT income floor (sme_income_by_province.json) — same rank-1-surfacing
  // pattern applied to the SME-owner occupation, the merchant-lending segment's income-floor proxy
  // (previously only surfaced on province.html; this is the Exposure/merchant-tab equivalent).
  if(smeincHasData()){
    const s=SMEINC_LIST[0];
    const nBelow=SMEINC_LIST.filter(p=>(p.ratio_to_national||0)<1).length;
    html+=`<div class="cc-sub2" style="margin-top:14px">Merchant segment income floor · SME owners ${TAG_M}</div>`+
      `<div class="cc-card-b">`+ccRow(`${s.province}`,
        `SME-owner income ฿${(s.sme_income||0).toLocaleString()}/mo · ${nBelow}/${SMEINC_LIST.length} provinces below the national floor (NSO SES 2566, measured)`,
        `${(s.ratio_to_national||0).toFixed(2)}×`,'vs national avg','var(--collat)')+`</div>`;
  }
  // 2) RISKIEST BRANCHES (branch_risk.json, index-aligned to DATA)
  if(briskHasData()&&DATA&&DATA.length===BRISK.length){
    const idx=BRISK.map((e,i)=>i).sort((a,b)=>(BRISK[b].composite_risk||0)-(BRISK[a].composite_risk||0)).slice(0,15);
    html+=`<h2 class="risk" style="margin-top:18px">Riskiest branches ${TAG_E}</h2>`+
      `<p class="lead">Top 15 branches by the same <b>estimated composite</b> (0–100). — a triage rank for where to look first.</p>`+
      methodBox('The readable list of the National map composite-risk lens.',
        ['A triage rank, <b>not</b> a measured default rate.',
         'Composite is index-aligned to the branch list; driver = the dominant component of the score.'])+
      `<table class="tbl" id="expo-brisk-tbl"><tr><th scope="col">#</th><th scope="col">Branch</th><th scope="col">Province</th>`+
      `<th scope="col" class="h-agri" title="estimated composite risk 0–100">Composite ▲ est</th><th scope="col" title="dominant driver of the composite">Top driver</th></tr>`+
      idx.map((i,rank)=>{const e=BRISK[i], d=DATA[i];
        return `<tr><td class="mono sub">${rank+1}</td><td><b>${d.n||'—'}</b></td><td class="sub">${d.v||'—'}</td>`+
        `<td class="mono" style="color:var(--agri)">${(e.composite_risk||0).toFixed(1)}</td>`+
        `<td class="sub">${riskDriverLabel(e.top_driver)}</td></tr>`;}).join('')+`</table>`;
  }
  host.innerHTML=html;
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
const SIM_HI=45; // high-agri-stress threshold on the 0–100 scale (crop_stress.agri_stress, still used by the map lens)
const simState={price:0,rain:0,veh:0,factory:0};
let simWired=false;

/* ---------- factory / manufacturing slowdown lever (objective #1) ----------
   Reuses the MEASURED occupation-risk layer already loaded client-side (OCCRISK, index-aligned to
   DATA). "Manufacturing base" = branches whose MEASURED dominant occupation bucket is factory or
   auto/vehicle work (OCC_BUCKET_COL groups both as the purple industrial bucket). The severity
   lever (0–100%) applies an ESTIMATED linear uplift to those branches' occupation-stress score,
   capped at 100. Everything is ESTIMATED except the branch counts + occupation shares (measured).
   Null-guarded: returns null when the occupation-risk pull is absent (lever is hidden then). */
const SIM_FACTORY_KEYS={factory:1,auto:1}; // measured dominant-bucket keys treated as manufacturing base
// max ESTIMATED occupation-stress uplift (points) at 100% slowdown severity — an illustrative lever, not calibrated.
const SIM_FACTORY_MAX_UPLIFT=35;
function simFactoryModel(){
  if(!occriskHasData()||!DATA) return null;
  const sev=Math.max(0,Math.min(100,simState.factory))/100;   // 0..1
  let mfgBr=0, baseSum=0, scenSum=0, worstDelta=0;
  DATA.forEach((d,i)=>{
    const e=OCCRISK[i]; if(!e||!SIM_FACTORY_KEYS[e.d]) return; // only manufacturing-dominant branches
    mfgBr++;
    const base=e.s||0;
    const scen=Math.min(100,base+sev*SIM_FACTORY_MAX_UPLIFT);
    baseSum+=base; scenSum+=scen;
    if(scen-base>worstDelta) worstDelta=scen-base;
  });
  if(!mfgBr) return {mfgBr:0,sev};
  const N=(DATA||[]).length||1;
  return {mfgBr,sev,N,
    baseAvg:baseSum/mfgBr, scenAvg:scenSum/mfgBr, delta:(scenSum-baseSum)/mfgBr,
    share:100*mfgBr/N, worstDelta};
}
// MEASURED context on top of the ESTIMATED lever above: of the manufacturing-base branches, how
// many sit in a province whose NSO factory-worker income already runs below the national average
// (factory_income_by_province.json)? Read-only — never changes simFactoryModel()'s scenario numbers.
// Null when either the occupation-risk or factory-income layer is absent.
function simFactoryIncomeFloor(){
  if(!occriskHasData()||!factincHasData()||!DATA) return null;
  let mfgBr=0, below=0, worstRatio=null, worstProv=null;
  DATA.forEach((d,i)=>{
    const e=OCCRISK[i]; if(!e||!SIM_FACTORY_KEYS[e.d]) return;
    mfgBr++;
    const rec=FACTINC[d.v]; if(!rec) return;
    if(rec.ratio_to_national<1){
      below++;
      if(worstRatio==null||rec.ratio_to_national<worstRatio){ worstRatio=rec.ratio_to_national; worstProv=d.v; }
    }
  });
  if(!mfgBr) return null;
  return {mfgBr,below,worstRatio,worstProv};
}
// render the factory-slowdown output cards. Hidden when the occupation-risk pull is absent.
function renderSimFactory(){
  const wrap=$('#sim-factory-out-wrap'), box=$('#sim-factory-out'); if(!box) return;
  const m=simFactoryModel();
  if(!m){ if(wrap) wrap.style.display='none'; box.innerHTML=''; return; }
  if(wrap) wrap.style.display='block';
  const shocked=simState.factory>0;
  const col=shocked?'var(--agri)':'var(--mid)';
  const cards=[
    {k:'Manufacturing-base branches',v:m.mfgBr.toLocaleString(),
     d:`${m.share.toFixed(1)}% of the network`,col:'var(--mid)',
     n:'Branches whose MEASURED dominant borrower base is factory / auto work (Overture occupation mix). Branch counts measured.'},
    {k:'Avg occupation-stress · est',v:m.scenAvg.toFixed(0),
     d:shocked?`+${m.delta.toFixed(0)} vs base (${m.baseAvg.toFixed(0)})`:`baseline (${m.baseAvg.toFixed(0)})`,col,
     n:'ESTIMATED occupation-stress (0–100) across the manufacturing-base branches under the slowdown lever. A triage direction, not a measured default rate.'},
    {k:'Peak branch uplift · est',v:shocked?`+${m.worstDelta.toFixed(0)}`:'—',
     d:shocked?'points on the most exposed branch':'set the slowdown lever',col:shocked?'var(--agri)':'var(--mid)',
     n:'Largest ESTIMATED occupation-stress rise on a single manufacturing-base branch under this severity. Illustrative — no loan balances.'},
  ];
  const fi=simFactoryIncomeFloor();
  if(fi){
    cards.push({k:'Below income-floor · measured',v:fi.below.toLocaleString(),
      d:fi.worstProv?`worst: ${fi.worstProv} (${(fi.worstRatio*100).toFixed(0)}% of national)`:'none below national avg',
      col:fi.below?'var(--agri)':'var(--mid)',
      n:'MEASURED count of manufacturing-base branches sitting in a province whose NSO SES factory-worker income already runs below the national average (factory_income_by_province.json). Context only — does not change the estimated stress figures above.'});
  }
  box.innerHTML=cards.map(c=>`<div class="mcard"><div class="k">${c.k}</div>
    <div class="v" style="color:${c.col}">${c.v}</div>
    <div class="d" style="color:${c.col}">${c.d}</div>
    <div class="n">${c.n}</div></div>`).join('');
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
// MEASURED context on top of the ESTIMATED crop-price/rainfall scenario above: of the agri-relevant
// provinces (CSTRESS_LIST), how many branches sit in a province whose NSO Agriculture-occupation
// income already runs below the national average (agri_income_by_province.json)? Read-only — never
// changes computeSim()'s scenario numbers. Null when either crop-stress or agri-income is absent.
function simAgriIncomeFloor(){
  if(!CSTRESS_LIST||!CSTRESS_LIST.length||!agrincHasData()) return null;
  const brn=simBranchByProv();
  let agriBr=0, belowBr=0, worstRatio=null, worstProv=null;
  CSTRESS_LIST.forEach(p=>{
    const br=brn[p.th]||0; if(!br) return;
    agriBr+=br;
    const rec=AGRIINC[p.th]; if(!rec) return;
    if(rec.ratio_to_national<1){
      belowBr+=br;
      if(worstRatio==null||rec.ratio_to_national<worstRatio){ worstRatio=rec.ratio_to_national; worstProv=p.th; }
    }
  });
  if(!agriBr) return null;
  return {agriBr,belowBr,worstRatio,worstProv};
}
function renderSim(){
  if(!simWired) wireSim();
  // load the crop-stress + occupation-risk layers, then (re)compute once either lands.
  const active=()=>document.getElementById('v-sim').classList.contains('on');
  loadCropStress().then(()=>{ if(active()) computeSim(); });
  loadOccRisk().then(()=>{ if(active()){ syncSimFactoryVisibility(); computeSim(); } });
  loadFactoryIncome().then(()=>{ if(active()) renderSimFactory(); });
  loadAgriIncome().then(()=>{ if(active()) computeSim(); });
  syncSimFactoryVisibility();
}
// show the factory-slowdown lever only when the Overture occupation-risk pull is present; otherwise
// hide the slider and show the quiet "needs the pull" note. NEVER fabricates. Reset lever when hidden.
function syncSimFactoryVisibility(){
  const has=occriskHasData();
  const wrap=$('#sim-factory-wrap'), note=$('#sim-factory-note');
  if(wrap) wrap.style.display=has?'':'none';
  if(note) note.style.display=has?'none':'';
  if(!has){ simState.factory=0; const inp=$('#sim-factory'); if(inp){ inp.value=0; inp.setAttribute('aria-valuetext','0%'); } const lab=$('#sim-factory-v'); if(lab) lab.textContent='0%'; }
}
function wireSim(){
  simWired=true;
  const bind=(id,key,fmt)=>{const inp=$(id); if(!inp) return;
    inp.oninput=()=>{simState[key]=+inp.value; const lab=$(id+'-v'); if(fmt){const t=fmt(+inp.value); if(lab) lab.textContent=t; inp.setAttribute('aria-valuetext',t);} computeSim();};};
  bind('#sim-price','price',v=>(v>0?'+':'')+v+'%');
  bind('#sim-rain','rain',v=>v===0?'normal':(v>0?'wetter +':'drier ')+v+'%');
  bind('#sim-veh','veh',v=>(v>0?'+':'')+v+'%');
  bind('#sim-factory','factory',v=>v+'%');
  const rs=$('#sim-reset'); if(rs) rs.onclick=simReset;
}
function simReset(){
  simState.price=0; simState.rain=0; simState.veh=0; simState.factory=0;
  const set=(id,v,vt)=>{const e=$(id); if(e){ e.value=v; e.setAttribute('aria-valuetext',vt); }};
  set('#sim-price',0,'0%'); set('#sim-rain',0,'normal'); set('#sim-veh',0,'0%'); set('#sim-factory',0,'0%');
  $('#sim-price-v')&&($('#sim-price-v').textContent='0%');
  $('#sim-rain-v')&&($('#sim-rain-v').textContent='normal');
  $('#sim-veh-v')&&($('#sim-veh-v').textContent='0%');
  $('#sim-factory-v')&&($('#sim-factory-v').textContent='0%');
  computeSim();
}
// BASELINE verdict shown ABOVE the sliders so the simulator says something on load (no slider move needed).
function renderSimVerdict(baseHiP,baseHiBr,N,shocked,scenHiP,scenHiBr){
  const box=$('#sim-verdict'); if(!box) return;
  box.style.display='block';
  if(baseHiP==null){
    box.innerHTML=`<div class="verdict-line">⚙️ <b>Baseline ready.</b> The agri what-if needs crop-stress data (data/crop_stress.json) — load it to run the crop / rainfall shock.</div>`;
    return;
  }
  if(!shocked){
    const pct=N?((100*baseHiBr/N).toFixed(1)):'0.0';
    box.innerHTML=`<div class="verdict-line">⚙️ <b>Baseline:</b> ${baseHiP} provinces in high agri-stress today — ${baseHiBr.toLocaleString()} branches (${pct}% of the network)</div>`+
      `<div class="sub" style="margin-top:4px">Drag a slider to stress the book. ILLUSTRATIVE what-if (estimated proxy, no loan balances) — a direction, not a number. ${TAG_E}</div>`;
  } else {
    const dP=scenHiP-baseHiP, dBr=scenHiBr-baseHiBr; const s=v=>(v>0?'+':'')+v;
    box.innerHTML=`<div class="verdict-line">⚙️ <b>Under this shock:</b> high-stress provinces ${baseHiP} → ${scenHiP} (${s(dP)}) · exposed branches ${baseHiBr.toLocaleString()} → ${scenHiBr.toLocaleString()} (${s(dBr)})</div>`+
      `<div class="sub" style="margin-top:4px">ILLUSTRATIVE what-if · branch counts measured, stress flag estimated ${TAG_E}</div>`;
  }
}
function computeSim(){
  if(!$('#sim-cards')) return;
  if(!CSTRESS_LIST||!CSTRESS_LIST.length){
    $('#sim-cards').innerHTML='';
    renderSimVerdict(null);
    $('#sim-readout').innerHTML='Crop-stress data not available (data/crop_stress.json missing) — the agri what-if needs it.';
    $('#sim-prov').innerHTML=''; renderSimCollat(); renderSimFactory(); return;
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
  renderSimVerdict(baseHiP,baseHiBr,N,shocked,scenHiP,scenHiBr);
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
  const ai=simAgriIncomeFloor();
  if(ai){
    cards.push({k:'Below income-floor · measured',v:ai.belowBr.toLocaleString(),
      d:ai.worstProv?`worst: ${ai.worstProv} (${(ai.worstRatio*100).toFixed(0)}% of national)`:'none below national avg',
      col:ai.belowBr?'var(--agri)':'var(--mid)',
      n:'MEASURED count of branches (across agri-relevant provinces) sitting in a province whose NSO SES Agriculture-occupation income already runs below the national average (agri_income_by_province.json). Context only — does not change the estimated agri-stress figures above.'});
  }
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
        tbl.innerHTML=`<tr><th scope="col">#</th><th scope="col">Province</th><th scope="col">Region</th><th scope="col" title="AutoX branches — measured footprint">Branches</th>`+
          `<th scope="col" class="h-agri" title="ESTIMATED agri-stress proxy before the shock (0–100)">Base ▲ est</th>`+
          `<th scope="col" class="h-agri" title="ESTIMATED agri-stress proxy under the shock (0–100)">Scenario ▲ est</th>`+
          `<th scope="col" class="h-agri" title="rise in the estimated agri-stress proxy">Δ est</th><th scope="col">Status</th></tr>`+
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
  renderSimFactory();
}
// collateral recovery-value DIRECTION from the used-vehicle slider (illustrative, no balances).
// AutoX lends against VEHICLE TITLES (not gold), so only the used-vehicle backing is modelled.
function renderSimCollat(){
  const box=$('#sim-collat'); if(!box) return;
  const {veh}=simState;
  const vt=veh>0?'recovery value ↑ · LGD ↓':veh<0?'recovery value ↓ · LGD ↑':'unchanged';
  // for vehicles a NEGATIVE move is the bad case
  const vCol=veh<0?'var(--agri)':veh>0?'var(--up)':'var(--mid)';
  const cards=[
    {k:'Used-vehicle collateral',v:(veh>0?'+':'')+veh+'%',d:(veh<0?'▼':veh>0?'▲':'•')+' '+vt,col:vCol,
     n:'ILLUSTRATIVE move on used motorcycle/pickup resale — the title-book backing. Down lowers recovery (loss-given-default rises). No LTV/balances.'},
    {k:'Recovery read',
     v:veh>0?'firming':veh<0?'softening':'unchanged',
     d:'direction only',
     col:vCol,
     n:'Qualitative read on vehicle-title recovery value. A fall raises loss-given-default on the title book even before defaults move. No portfolio ฿ figure — illustrative.'},
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
/* ---------- "Since last vintage" digest (top of #trend) ----------
   Lazy-loads data/vintage_digest.json (pipeline/build_vintage_digest.py): one exec headline +
   4-8 one-sentence findings, worst first, each chip-tagged better/worse/neutral. Every number
   is read from deltas.json by the builder — the card adds no interpretation of its own.
   With 0/1 snapshots it shows the calm "first vintage — no comparison yet" one-liner. */
let VDIGEST=null, vdigestLoaded=false;
async function renderVintageDigest(){
  if(!vdigestLoaded){
    vdigestLoaded=true;
    try{ VDIGEST = await fetch('data/vintage_digest.json').then(r=>r.ok?r.json():null); }
    catch(e){ VDIGEST=null; }
  }
  const box=$('#vdigest'); if(!box) return;
  if(!VDIGEST){ box.style.display='none'; return; }   // file absent → card simply stays hidden
  box.style.display='block';
  const vint=$('#vdgvint');
  if(vint) vint.textContent = VDIGEST.baseline ? (VDIGEST.to?`baseline ${VDIGEST.to}`:'') : `${VDIGEST.from} → ${VDIGEST.to}`;
  const hl=$('#vdgheadline'); if(hl) hl.textContent = VDIGEST.headline||'';
  const chip=t=>`<span class="vdg-chip ${t}">${t==='worse'?'▲ worse':t==='better'?'▼ better':'• flat'}</span>`;
  const list=$('#vdglist');
  if(list) list.innerHTML=(VDIGEST.findings||[]).map(f=>
    `<li>${chip(f.tone)}<span>${f.text}</span><span class="vdg-metric mono" title="underlying metric in deltas.json">${f.metric||''}</span></li>`).join('');
  const note=$('#vdgnote');
  if(note) note.textContent = VDIGEST.baseline
    ? 'Findings appear automatically once a second vintage is snapshotted.'
    : 'Every figure is read from deltas.json (the snapshot diff). Region/branch proxies are ESTIMATED; the commodity board is measured/editorial price direction (World Bank).';
}
function renderTrendTape(){
  const wrap=$('#trend-tape'); if(!wrap) return;
  if(!TAPE){ wrap.style.display='none'; return; }
  wrap.style.display='';
  const vt=$('#trend-tape-vint'), au=$('#trend-tape-audit');
  if(vt&&TAPE.vintage_curve){
    // rows are "YYYY|MMa-MMbm" months-on-book bands; show year totals at comparable young bands
    const byYear={};
    Object.entries(TAPE.vintage_curve).forEach(([k,v])=>{
      const [yr,band]=k.split('|'); (byYear[yr]=byYear[yr]||[]).push({band,...v});
    });
    const years=Object.keys(byYear).sort();
    vt.innerHTML=`<tr><th scope="col">Vintage</th><th scope="col">Months-on-book band</th><th scope="col">Accounts</th><th scope="col" title="share of the vintage 90+ days past due">90+dpd</th></tr>`+
      years.map(yr=>byYear[yr].sort((a,b)=>a.band.localeCompare(b.band)).map((r,i)=>`<tr>
        <td class="mono">${i===0?`<b>${yr}</b>`:''}</td><td class="mono sub">${r.band}</td>
        <td class="mono sub">${r.n.toLocaleString()}</td>
        <td class="mono" style="color:${r.dpd90p_pct>=16?'var(--agri)':r.dpd90p_pct>=10?'var(--opp)':'var(--merch)'}"><b>${r.dpd90p_pct}%</b></td>
      </tr>`).join('')).join('');
  }
  if(au&&TAPE.branch_audit){
    au.innerHTML=`<tr><th scope="col">#</th><th scope="col">Branch</th><th scope="col">Accounts</th><th scope="col" title="share of the branch's accounts 90+ days past due">90+dpd</th><th scope="col" title="X-days share — the pre-emptive window">X-days</th><th scope="col" title="first-payment-default share — underwriting quality at origination">FPD</th></tr>`+
      TAPE.branch_audit.map((b,i)=>`<tr><td class="mono sub">${i+1}</td><td>${b.branch}</td>
        <td class="mono sub">${b.n}</td>
        <td class="mono" style="color:var(--agri)"><b>${b.dpd90p_pct}%</b></td>
        <td class="mono sub">${b.early_pct}%</td>
        <td class="mono sub">${b.fpd_pct}%</td></tr>`).join('');
  }
}
async function renderTrend(){
  loadTapeReal().then(renderTrendTape);
  renderCreditAnchor();
  renderVintageDigest();
  renderPeerOutliers();
  renderSiegeTable();
  if(!trendLoaded){
    trendLoaded=true;
    try{ DELTAS = await fetch('data/deltas.json').then(r=>r.json()); }
    catch(e){ DELTAS=null; }
  }
  const baseEl=$('#trendbaseline'), bodyEl=$('#trendbody'), vintEl=$('#trendvint'),
        baseBodyEl=$('#trendbaselinebody');
  // No deltas file at all, OR a single-vintage baseline: BOTH render the DESIGNED baseline state
  // (never a raw apology). The baseline shows where risk stands NOW + flat sparkline skeletons.
  if(!DELTAS || DELTAS.baseline){
    if(vintEl) vintEl.textContent = (DELTAS&&DELTAS.to)?`Baseline vintage: ${DELTAS.to}.`:'';
    if(baseEl) baseEl.style.display='none';
    if(bodyEl) bodyEl.style.display='none';
    if(baseBodyEl) baseBodyEl.style.display='block';
    renderTrendBaseline(DELTAS);
    return;
  }
  if(vintEl) vintEl.textContent = `Comparing ${DELTAS.from} → ${DELTAS.to}.`;
  if(baseEl) baseEl.style.display='none';
  if(baseBodyEl) baseBodyEl.style.display='none';
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
    BD.innerHTML=`<tr><th scope="col">Item</th><th scope="col">Segment</th><th scope="col">YoY now</th><th scope="col">Prior YoY</th><th scope="col" title="change in the YoY figure — a fall means deepening price stress">Δ YoY · est</th></tr>`+
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
    BR.innerHTML=`<tr><th scope="col">#</th><th scope="col" title="composite risk proxy = worst of agri/merchant/collateral (est)">Risk now ▲ est</th><th scope="col" title="change in composite proxy vs prior vintage">Δ composite · est</th><th scope="col">Branch</th><th scope="col">Prov</th><th scope="col">Region</th><th scope="col">Δ agri</th><th scope="col">Δ merch</th><th scope="col">Δ collat</th></tr>`+
      (rows.length?rows.map((d,i)=>{const rc=d.comp>=60?'var(--agri)':d.comp>=40?'var(--gold)':'var(--merch)';
        return `<tr><td class="mono sub">${i+1}</td>
        <td class="mono" style="color:${rc}">▲ ${d.comp}</td>
        <td>${deltaPill(d.d_comp)}</td>
        <td>${d.n}</td><td class="sub">${d.v}</td><td class="sub">${d.r}</td>
        <td>${deltaPill(d.d_a)}</td><td>${deltaPill(d.d_m)}</td><td>${deltaPill(d.d_c)}</td></tr>`;}).join('')
        :'<tr><td class="sub" colspan="9">No branch-level movement between these vintages.</td></tr>');
  }
}

/* QW8 — DESIGNED RISK-TREND BASELINE.
   Until a SECOND vintage is snapshotted there are no deltas, so the time tab would otherwise be
   blank. Instead we render a CALM "baseline captured" readout of where stress stands NOW, pulled
   ONLY from the already-built risk layers (province_risk / crop_stress / household_risk). Each row
   carries a FLAT sparkline-skeleton — a single anchored point that will extend into a real trend
   line at the next refresh — plus a "Δ at next refresh" chip. Every source is null-safe: a missing
   layer simply omits its block; nothing is fabricated, and we never show a raw apology. */
let trendBaselineBooted=false;
// a flat sparkline skeleton: one solid baseline dot on the left, a dashed track to the right that
// fills once a second vintage lands. Purely decorative (aria-hidden).
function flatSpark(color){
  return `<span class="tspark" aria-hidden="true" title="One vintage captured — the trend line draws in at the next refresh">`+
    `<i class="tspark-track" style="--c:${color||'var(--mid)'}"></i>`+
    `<i class="tspark-dot" style="background:${color||'var(--mid)'}"></i></span>`;
}
function trendBaseChip(){
  return `<span class="tchip" title="A delta needs two vintages. The next snapshot fills this in.">Δ at next refresh</span>`;
}
/* ---------- peer-twin outliers · audit-first list (obj #1) ----------
   Surfaces data/branch_peers.json (pipeline/build_branch_peers.py): each branch benchmarked
   against its 15 statistical twins (measured market fingerprint + NSO leverage backdrop,
   >=25km away). ESTIMATED — deviation of the estimated composite risk vs the twin group.
   Vintage-independent (works before a 2nd snapshot exists). Graceful when absent. */
let PEERS=null, peersLoaded=false, peersPromise=null;
async function loadBranchPeers(){
  if(peersPromise) return peersPromise;
  peersLoaded=true;
  peersPromise=(async()=>{
    try{ const r=await fetch('data/branch_peers.json'); PEERS=r.ok?await r.json():null; }
    catch(e){ PEERS=null; }
    return PEERS;
  })();
  return peersPromise;
}
function peerHasData(){return !!(PEERS&&Array.isArray(PEERS.branches)&&PEERS.branches.length);}
// per-branch peer record {dev, rz, pm} — null when absent. Positive dev = risk above the twins.
function peerRec(d){
  if(!peerHasData()||!DATA) return null;
  const i=idxOf(d); if(i<0) return null;
  return PEERS.branches[i]||null;
}
// lens value: points ABOVE the twin median (0 when at/below — the lens flags anomalies, not comfort).
function peerDevVal(d){const e=peerRec(d); return e?Math.max(0,e.dev||0):0;}
function renderPeerOutliers(){
  const tbl=$('#peertbl'); if(!tbl) return;
  loadBranchPeers().then(drawPeerOutliers);  // promise is cached; repeat calls are cheap
}
function drawPeerOutliers(){
  const tbl=$('#peertbl'), ro=$('#peerreadout'); if(!tbl) return;
  const rows=(PEERS&&Array.isArray(PEERS.outliers))?PEERS.outliers:[];
  if(!rows.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Peer benchmark not yet computed.</b> <span class="sub">Run pipeline/build_branch_peers.py — the audit-first list fills in on the next data refresh.</span>';
    return;
  }
  tbl.innerHTML=`<tr><th>#</th><th>Branch</th><th>Province</th><th>Region</th>`+
    `<th class="h-risk" title="ESTIMATED composite risk proxy (0–100) from branch_risk.json">Risk ▲</th>`+
    `<th title="Median composite risk of the 15 statistical twins">Twins</th>`+
    `<th class="h-risk" title="Points above the twin median — the branch-local anomaly">+ vs twins</th>`+
    `<th title="Component driving the branch's composite (household / agri / occupation / segment)">Driver</th>`+
    `<th title="The 3 nearest twins (name · risk) — similar measured markets elsewhere">Closest twins</th></tr>`+
    rows.map((o,i)=>{
      const tw=(o.twins||[]).map(t=>`${t.name} <span class="mono sub">${t.risk}</span>`).join('<br>');
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td><b>${o.name||'—'}</b><div class="sub">${o.district||''}</div></td>
        <td>${o.prov||'—'}</td>
        <td class="sub">${o.region||'—'}</td>
        <td class="mono" style="color:var(--agri)"><b>${o.risk}</b></td>
        <td class="mono sub">${o.peer_median}</td>
        <td>${barHTML(o.dev,'var(--agri)',25)} <span class="mono" style="color:var(--agri)"><b>+${o.dev}</b></span></td>
        <td class="sub">${o.top_driver||'—'}</td>
        <td class="sub" style="font-size:11px">${tw}</td>
      </tr>`;}).join('');
  if(ro){
    const t=rows[0], m=PEERS.meta||{};
    ro.innerHTML=`<b>Audit first:</b> <b style="color:var(--agri)">${t.name}</b> (${t.prov}, ${t.region}) carries risk
      <b style="color:var(--agri)">${t.risk}</b> while its statistical twins sit at <b>${t.peer_median}</b> —
      <b style="color:var(--agri)">+${t.dev} points</b> above comparable markets, so the driver is likely <b>local</b>
      (${t.top_driver||'mixed'}), not the market. ${rows.length} branches sit ≥2 robust-σ above their twins.
      <span class="sub">ESTIMATED — twins matched on measured features (${(m.params||{}).k||15} twins, ≥${(m.params||{}).geo_excl_km||25} km away, same NSO leverage backdrop); deviation uses the estimated composite risk. Not a measured default rate.</span>`;
  }
}
/* ---------- most besieged branches · rival-pressure top-10 (obj #1 + #2, MEASURED) ----------
   Surfaces data/rival_pressure.json .besieged (pipeline/build_rival_pressure.py): the branches
   with the most rival branches within 2 km — same-street fights for the same walk-in borrower.
   All counts/distances MEASURED geometry over the merged competitor census; the only rule is the
   stated siege cutoff (>=3 rivals within 2 km). Graceful when the file is absent. */
function renderSiegeTable(){
  const tbl=$('#siegetbl'); if(!tbl) return;
  loadRivalPressure().then(drawSiegeTable);   // promise is cached; repeat calls are cheap
}
function drawSiegeTable(){
  const tbl=$('#siegetbl'), ro=$('#siegereadout'); if(!tbl) return;
  const rows=(RIVP&&Array.isArray(RIVP.besieged))?RIVP.besieged.slice(0,10):[];
  if(!rows.length){
    tbl.innerHTML='';
    if(ro) ro.innerHTML='<b>Rival pressure not yet computed.</b> <span class="sub">Run pipeline/build_rival_pressure.py — the besieged list fills in on the next data refresh.</span>';
    return;
  }
  tbl.innerHTML=`<tr><th>#</th><th>Branch</th><th>Province</th><th>Region</th>`+
    `<th class="h-risk" title="MEASURED — rival branches within 2 km (merged competitor census)">Rivals ≤2 km</th>`+
    `<th title="MEASURED — rival branches within 5 km">≤5 km</th>`+
    `<th title="MEASURED — the closest rival brand and its distance (haversine)">Nearest rival</th>`+
    `<th title="MEASURED — which brands hold the 2 km ring (brand · count)">Who surrounds it</th>`+
    `<th class="no-print">3D</th></tr>`+
    rows.map((o,i)=>{
      const by=(o.by2||[]).map(p=>`${p[0]} <span class="mono sub">${p[1]}</span>`).join(' · ');
      return `<tr>
        <td class="mono sub">${i+1}</td>
        <td><b>${o.name||'—'}</b><div class="sub">${o.district||''}</div></td>
        <td>${o.prov||'—'}</td>
        <td class="sub">${o.region||'—'}</td>
        <td>${barHTML(o.n2,'var(--agri)',(rows[0].n2||1))} <span class="mono" style="color:var(--agri)"><b>${o.n2}</b></span></td>
        <td class="mono sub">${o.n5}</td>
        <td class="mono">${o.nb||'—'} <span style="color:var(--gold)">${o.nd} km</span></td>
        <td class="sub" style="font-size:11px">${by}</td>
        <td class="no-print" style="white-space:nowrap">${branch3DLinks((typeof DATA!=='undefined'&&DATA)?DATA[o.i]:null,false)}</td>
      </tr>`;}).join('');
  if(ro){
    const t=rows[0], m=RIVP.meta||{};
    ro.innerHTML=`<b>Most besieged:</b> <b style="color:var(--agri)">${t.name}</b> (${t.prov}, ${t.region}) has
      <b style="color:var(--agri)">${t.n2} rival branches within 2 km</b> (${t.n5} within 5 km) — the nearest is
      <b>${t.nb}</b> at <b style="color:var(--gold)">${t.nd} km</b>. ${m.n_siege||'—'} of ${m.n_branches||'—'} branches
      are under siege (≥3 rivals ≤2 km) — these fight for the same walk-in borrower on the same street, so watch
      pricing/LTV pressure here first.
      <span class="sub">MEASURED — haversine over the merged competitor census (Muangthai/Srisawad/Tidlor official
      store locators, measured-complete; Heng is a sample, so pressure is a lower bound). The ≥3 cutoff is a stated
      rule, not a model.</span>`;
  }
}
function renderTrendBaseline(deltas){
  const box=$('#trendbaselinebody'); if(!box) return;
  const vint=(deltas&&deltas.to)||(snapVintage())||null;
  // warm the three risk layers once; re-render as each resolves (null-safe).
  if(!trendBaselineBooted){
    trendBaselineBooted=true;
    const re=()=>{ if(document.getElementById('v-trend').classList.contains('on')) renderTrendBaseline(deltas); };
    loadProvinceRisk().then(re); loadCropStress().then(re); loadHouseholdRisk().then(re);
  }
  let html='';
  // header / chip strip
  html+=`<div class="insight" style="border-left-color:var(--gold)">`+
    `<b>Baseline captured${vint?` (${vint})`:''}.</b> This is where portfolio stress stands <b>right now</b> — `+
    `the time-series plumbing is live and will draw movers, commodity re-rating and per-branch shifts `+
    `the moment a second vintage is snapshotted. <span class="sub">One data point in; deltas appear at the next refresh.</span> `+
    trendBaseChip()+`</div>`;

  // 1) MOST-STRESSED PROVINCES NOW (province_risk.json, composite — estimated)
  if(priskHasData()){
    const top=PRISK_LIST.slice(0,6).filter(p=>p&&p.province);
    if(top.length){
      html+=`<h2 class="risk" style="margin-top:18px">Most-stressed provinces now ${TAG_E}</h2>`+
        `<p class="lead">Top provinces by mean composite risk (0–100) at the current vintage. The flat marker becomes a trend line at the next refresh.</p>`+
        `<table class="tbl"><tr><th>#</th><th>Province</th><th>Region</th><th title="AutoX branches (measured)">Branches</th><th title="mean of the estimated per-branch composite, 0–100">Mean risk ▲</th><th>p90</th><th>Trend</th></tr>`+
        top.map((p,i)=>{const mr=p.mean_risk||0; const rc=mr>=60?'var(--agri)':mr>=45?'var(--gold)':'var(--merch)';
          return `<tr><td class="mono sub">${i+1}</td><td><b>${p.province}</b></td><td class="sub">${p.region||''}</td>`+
            `<td class="mono">${p.n_branches||0}</td>`+
            `<td>${barHTML(mr,rc)} <span class="mono" style="color:${rc}">${mr.toFixed(0)}</span></td>`+
            `<td class="mono sub">${(p.p90_risk||0).toFixed(0)}</td>`+
            `<td>${flatSpark(rc)}</td></tr>`;}).join('')+`</table>`;
    }
  }

  // 2) WORST CROP-HOUSEHOLD STRESS NOW (crop_stress.json — estimated proxy)
  if(CSTRESS_LIST&&CSTRESS_LIST.length){
    const top=CSTRESS_LIST.slice(0,6);
    html+=`<h2 class="risk" style="margin-top:18px">Worst crop-household stress now ${TAG_E}</h2>`+
      `<p class="lead">Agri-stress proxy (0–100) per province — crop-price direction (World Bank global proxy) × drought × crop dependence.</p>`+
      `<table class="tbl"><tr><th>#</th><th>Province</th><th>Region</th><th>Dominant crop</th><th title="planting-area-weighted crop-price YoY, global proxy">Price YoY</th><th>Agri-stress ▲</th><th>Trend</th></tr>`+
      top.map((w,i)=>{const sv=Math.round((w.agri_stress||0)*100); const sc=sv>=60?'var(--agri)':sv>=40?'var(--gold)':'var(--merch)';
        const crop=(w.crop_mix&&w.crop_mix[0]&&w.crop_mix[0].crop)||'—';
        return `<tr><td class="mono sub">${i+1}</td><td><b>${w.th}</b></td><td class="sub">${w.region||''}</td>`+
          `<td class="sub">${crop}</td>`+
          `<td class="mono sub">${w.price_stress!=null?(w.price_stress>0?'+':'')+w.price_stress+'%':'—'}</td>`+
          `<td>${barHTML(sv,sc)} <span class="mono" style="color:${sc}">${sv}</span></td>`+
          `<td>${flatSpark(sc)}</td></tr>`;}).join('')+`</table>`;
  }

  // 3) HIGHEST HOUSEHOLD LEVERAGE NOW (household_risk_by_province.json — MEASURED, NSO)
  if(hhriskHasData()&&HHRISK_LIST.length){
    const top=HHRISK_LIST.slice(0,6);
    html+=`<h2 class="risk" style="margin-top:18px">Highest household leverage now ${TAG_M}</h2>`+
      `<p class="lead">Debt-to-income per province (NSO SES, measured). Higher leverage = thinner repayment buffer on the title book.</p>`+
      `<table class="tbl"><tr><th>#</th><th>Province</th><th>Region</th><th title="household debt ÷ annual income, NSO measured">DTI ▲</th><th>Trend</th></tr>`+
      top.map((p,i)=>{const dti=p.debt_to_income||0; const dc=dti>=1?'var(--agri)':dti>=0.7?'var(--gold)':'var(--merch)';
        return `<tr><td class="mono sub">${i+1}</td><td><b>${p.province}</b></td><td class="sub">${p.region||''}</td>`+
          `<td>${barHTML(Math.min(dti*60,100),dc)} <span class="mono" style="color:${dc}">${dti.toFixed(2)}×</span></td>`+
          `<td>${flatSpark(dc)}</td></tr>`;}).join('')+`</table>`;
  }

  // nothing loaded yet (all three layers still in flight or absent) — calm placeholder, never an apology.
  if(!priskHasData() && !(CSTRESS_LIST&&CSTRESS_LIST.length) && !(hhriskHasData()&&HHRISK_LIST.length)){
    html+=`<div class="cc-empty" style="margin-top:14px">Loading the current risk snapshot…</div>`;
  }
  box.innerHTML=html;
}
// best-effort current vintage label from the snapshots index (loaded lazily; null until then).
let SNAPIDX=null, snapIdxLoaded=false;
function snapVintage(){
  if(!snapIdxLoaded){ snapIdxLoaded=true;
    fetch('data/snapshots_index.json').then(r=>r.ok?r.json():null).then(j=>{ SNAPIDX=j||null;
      if(document.getElementById('v-trend')&&document.getElementById('v-trend').classList.contains('on')) renderTrendBaseline(DELTAS);
    }).catch(()=>{SNAPIDX=null;});
  }
  const s=SNAPIDX&&Array.isArray(SNAPIDX.snapshots)&&SNAPIDX.snapshots.length?SNAPIDX.snapshots[SNAPIDX.snapshots.length-1]:null;
  return s?(s.label||null):null;
}

/* ---------- map ---------- */
// one map-lens pill (used for both the hero row and the More ▾ menu). disabled = data known-absent.
function lensPillHTML(k,opts){
  const l=LENS[k]; if(!l) return '';
  const menu=opts&&opts.menu;
  const disabled=lensAbsent(k);
  const lbl=(l.pill||l.label).replace(/"/g,'&quot;'), info=l.desc.replace(/"/g,'&quot;');
  // in-band provenance badge: [M] measured / [E] estimated — visible, not tooltip-only.
  const tag=l.tag==='m'
    ? `<span class="lpt m" title="Measured value" aria-hidden="true">M</span>`
    : `<span class="lpt e" title="Estimated / proxy — not a measured outcome" aria-hidden="true">E</span>`;
  const cls=`pill lens${menu?' lens-menu':''}${k===curLens?' on':''}${disabled?' lens-off':''}`;
  const dis=disabled?' disabled aria-disabled="true"':'';
  const note=disabled?' <span class="sub" style="font-size:9.5px">· no data</span>':'';
  return `<button class="${cls}" data-l="${k}"${dis} aria-pressed="${k===curLens}" aria-label="Map lens: ${lbl} (${l.tag==='m'?'measured':'estimated'}). ${info}">`+
    `<span class="lk" style="background:${l.color};color:${l.color}"></span>`+
    `<span class="pl">${lbl}</span>${tag}${note}`+
    `<span class="pi" title="${info}" aria-hidden="true">ⓘ</span></button>`;
}
// true once we KNOW a lens's source is absent (loaded + empty) — used to disable (not remove) a pill so
// the hero row never reflows. Non-data-gated lenses are never absent.
function lensAbsent(k){
  const l=LENS[k]; if(!l) return false;
  if(l.hh)    return hhriskLoaded && !hhriskHasData();
  if(l.pstr)  return pstressLoaded && !pstressHasData();
  if(l.dsrch) return sdemandLoaded && !sdemandHasData();
  if(l.occr)  return occriskLoaded && !occriskHasData();
  if(l.brisk) return briskLoaded && !briskHasData();
  if(l.poirel) return poirelLoaded && !poiRelevanceHasData();
  if(l.peers) return peersLoaded && !peerHasData();
  if(l.macx)  return macxDone && !macxHasData();
  if(l.cat)   return cropLuLoaded && !cropHasData();
  // pico district-rival lens: hide only once the district layer is loaded AND it predates the
  // pico fold (no record carries a pico field) — so an older amphoe.json degrades gracefully.
  if(l.pico)  return !!(AMP&&AMP.length)&&!AMP.some(a=>a&&a.pico!=null);
  return false;
}
function renderLenses(){
  // The map lens row is tamed: 4 ALWAYS-VISIBLE hero pills (Opportunity · Composite risk ·
  // Competitors · Household DTI) cover the two objectives; every other lens lives in a "More lenses ▾"
  // dropdown so the row never overwhelms. A data-gated lens (DTI / composite) is DISABLED in place
  // rather than removed, so the hero slots never reflow jarringly. Each pill carries an in-band
  // [M]/[E] provenance badge; methodology still rides the per-pill "ⓘ" tooltip + aria-label.
  const hero=HERO_LENS.map(k=>lensPillHTML(k)).join('');
  // any non-hero lens currently selected (e.g. via ?lens=) gets surfaced as a 5th pill so the active
  // lens is always visible even when it lives in the menu.
  const extraActive=(!HERO_LENS.includes(curLens)&&LENS[curLens])?lensPillHTML(curLens):'';
  const menuKeys=Object.keys(LENS).filter(k=>!HERO_LENS.includes(k));
  const menuItems=menuKeys.map(k=>lensPillHTML(k,{menu:true})).join('');
  const moreOn=(!HERO_LENS.includes(curLens))?' on':'';
  $('#lenses').innerHTML = hero + extraActive +
    `<div class="lens-more" id="lensMore">`+
      `<button type="button" class="pill lens lens-more-btn${moreOn}" id="lensMoreBtn" aria-haspopup="true" aria-expanded="false" aria-label="More map lenses">More lenses ▾</button>`+
      `<div class="lens-more-menu" id="lensMoreMenu" role="menu" aria-label="More map lenses">${menuItems}</div>`+
    `</div>`;
  wireLensMore();
  $('#lenses').onclick = e=>{const b=e.target.closest('.lens'); if(!b||b.id==='lensMoreBtn'||b.disabled)return; setLens(b.dataset.l);
    const wrap=$('#lensMore'); if(wrap) wrap.classList.remove('open');};
  renderRiskSub();
  renderLegend();
}
// wire the "More lenses ▾" dropdown (open/close, outside-click, Escape). Idempotent per render.
function wireLensMore(){
  const wrap=$('#lensMore'), btn=$('#lensMoreBtn'); if(!wrap||!btn) return;
  btn.addEventListener('click',e=>{e.stopPropagation(); const o=!wrap.classList.contains('open');
    wrap.classList.toggle('open',o); btn.setAttribute('aria-expanded',String(o));});
  if(!renderLenses._moreDoc){
    renderLenses._moreDoc=true;
    document.addEventListener('click',e=>{const w=$('#lensMore'); if(w&&!w.contains(e.target)){w.classList.remove('open'); const b=$('#lensMoreBtn'); if(b) b.setAttribute('aria-expanded','false');}});
    document.addEventListener('keydown',e=>{if(e.key==='Escape'){const w=$('#lensMore'); if(w){w.classList.remove('open'); const b=$('#lensMoreBtn'); if(b) b.setAttribute('aria-expanded','false');}}});
  }
}
// risk sub-metric chips — only shown when the Portfolio-risk lens is active
function renderRiskSub(){
  const wrap=$('#riskSub'); if(!wrap) return;
  if(curLens!=='risk'){ wrap.style.display='none'; wrap.innerHTML=''; return; }
  wrap.style.display='flex';
  wrap.setAttribute('role','group'); wrap.setAttribute('aria-label','Risk proxy metric');
  const opts=[['composite','Composite (worst of 3)'],['a','Agri-PD ●'],['m','Merchant ◆'],['c','Collateral ▲']];
  wrap.innerHTML='<span class="sub" style="align-self:center;margin-right:2px">Risk proxy:</span>'+
    opts.map(([k,t])=>`<button class="chip ${k===riskMetric?'on':''}" data-rm="${k}" aria-pressed="${k===riskMetric}">${t}</button>`).join('');
  wrap.onclick=e=>{const b=e.target.closest('[data-rm]'); if(!b)return; riskMetric=b.dataset.rm;
    wrap.querySelectorAll('.chip').forEach(c=>{const on=c===b;c.classList.toggle('on',on);c.setAttribute('aria-pressed',String(on));});
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
  // Categorical dominant-crop lens: a swatch KEY (not a ramp), honestly tagged estimated · SPAM.
  if(l.cat){
    if(!cropLuLoaded){ $('#maplegend').innerHTML='<span class="skel skel-line" style="display:inline-block;width:160px;vertical-align:middle" aria-hidden="true"></span> <span class="sub">crop land-use…</span>'; return; }
    if(!cropHasData()){ $('#maplegend').innerHTML='<span class="sub">Crop land-use layer not present — run pipeline/build_crop_landuse.py.</span>'; return; }
    const present={}; for(const e of CROPLU.amphoe){ if(e&&e.dominant_crop) present[e.dominant_crop]=1; }
    const order=['rice','cassava','maize','sugarcane','oilpalm','rubber'].filter(k=>present[k]);
    const key=order.map(k=>`<span><i style="background:${CROP_COLORS[k]};border-radius:2px"></i>${CROP_LABEL[k]}</span>`).join('');
    $('#maplegend').innerHTML = key +
      ` <span class="sub" title="SPAM 2010 v2.0 — a modeled spatial disaggregation of measured subnational crop statistics onto a ~9km grid; rubber absent">◇ estimated · SPAM 2010 (model-allocated)</span>`;
    return;
  }
  // Competitor-density lens: if the census file isn't present yet, say so quietly (no crash) instead
  // of a meaningless 0-coloured scale, and point at the puller. Once data is in, show the scale + an
  // honest "measured, lower bound" tag and a tiny brand key for the faint rival points.
  if(l.cmp){
    if(!compLoaded){ $('#maplegend').innerHTML='<span class="skel skel-line" style="display:inline-block;width:160px;vertical-align:middle" aria-hidden="true"></span> <span class="sub">competitor census…</span>'; return; }
    if(!compHasData()){
      $('#maplegend').innerHTML='<span class="sub" title="Rival-branch census not loaded yet">'+
        'Competitor map loading — the rival-branch census will appear once the latest census is in.</span>';
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
    if(!hhriskLoaded){ $('#maplegend').innerHTML='<span class="skel skel-line" style="display:inline-block;width:160px;vertical-align:middle" aria-hidden="true"></span> <span class="sub">household debt-to-income…</span>'; return; }
    const lo=(mx*.12/100).toFixed(2), mid=(mx*.5/100).toFixed(2), hi=(mx/100).toFixed(2);
    $('#maplegend').innerHTML =
      `<span><i style="background:${lensColor(.12,l.color)}"></i>${lo}×</span>`+
      `<span><i style="background:${lensColor(.5,l.color)}"></i>${mid}×</span>`+
      `<span><i style="background:${lensColor(1,l.color)}"></i>${hi}× debt÷annual income</span>`+
      ` <span class="sub" title="NSO SES 2566 household debt and income — province averages, measured">● measured · NSO SES</span>`;
    return;
  }
  // District unemployment lens: raw MEASURED percentage (NSO LFS), shown to one decimal rather than
  // the generic fmtK rounding (which would collapse e.g. 0.67% and 1.2% to the same integer "1").
  if(l.unemp){
    const lo=(mx*.12).toFixed(1), mid=(mx*.5).toFixed(1), hi=mx.toFixed(1);
    $('#maplegend').innerHTML =
      `<span><i style="background:${lensColor(.12,l.color)}"></i>${lo}%</span>`+
      `<span><i style="background:${lensColor(.5,l.color)}"></i>${mid}%</span>`+
      `<span><i style="background:${lensColor(1,l.color)}"></i>${hi}% unemployment</span>`+
      ` <span class="sub" title="NSO Labour Force Survey — province-inherited district rate, measured">● measured · NSO LFS</span>`;
    return;
  }
  // Search-demand lens: ESTIMATED relative index (0-100, Google Trends) — skeleton while loading,
  // then an honest 'estimated · Google Trends relative index' tag (a demand signal, not query volume).
  if(l.dsrch){
    if(!sdemandLoaded){ $('#maplegend').innerHTML='<span class="skel skel-line" style="display:inline-block;width:160px;vertical-align:middle" aria-hidden="true"></span> <span class="sub">search demand…</span>'; return; }
    $('#maplegend').innerHTML =
      `<span><i style="background:${lensColor(.12,l.color)}"></i>${Math.round(mx*.12)}</span>`+
      `<span><i style="background:${lensColor(.5,l.color)}"></i>${Math.round(mx*.5)}</span>`+
      `<span><i style="background:${lensColor(1,l.color)}"></i>${Math.round(mx)} ${l.unit}</span>`+
      ` <span class="sub" title="Google Trends relative search-interest (0–100) for title-loan intent terms — a demand/attention signal, not query volume or bookings">▲ estimated · Google Trends relative index</span>`;
    return;
  }
  // Combined province structural-stress lens: ESTIMATED composite (0-100) of two MEASURED
  // percentile ranks — tag it 'estimated' honestly, unlike the plain-MEASURED hhdti/unemp legends.
  if(l.pstr){
    if(!pstressLoaded){ $('#maplegend').innerHTML='<span class="skel skel-line" style="display:inline-block;width:160px;vertical-align:middle" aria-hidden="true"></span> <span class="sub">province structural stress…</span>'; return; }
    $('#maplegend').innerHTML =
      `<span><i style="background:${lensColor(.12,l.color)}"></i>${Math.round(mx*.12)}</span>`+
      `<span><i style="background:${lensColor(.5,l.color)}"></i>${Math.round(mx*.5)}</span>`+
      `<span><i style="background:${lensColor(1,l.color)}"></i>${Math.round(mx)} ${l.unit}</span>`+
      ` <span class="sub" title="0.5×household-DTI percentile (NSO SES) + 0.5×unemployment percentile (NSO LFS), both measured inputs, equal-weighted blend">▲ estimated · NSO SES + NSO LFS blend</span>`;
    return;
  }
  // Relevant-POI density lens: a shimmer skeleton while the (measured-counts) layer loads, then an
  // honest "measured counts · estimated weighting" tag so the M-badged pill is not misread as a
  // fully measured score.
  if(l.poirel){
    if(!poirelLoaded){ $('#maplegend').innerHTML='<span class="skel skel-line" style="display:inline-block;width:160px;vertical-align:middle" aria-hidden="true"></span> <span class="sub">relevant-POI density…</span>'; return; }
    $('#maplegend').innerHTML =
      `<span><i style="background:${lensColor(.12,l.color)}"></i>~0</span>`+
      `<span><i style="background:${lensColor(.5,l.color)}"></i>${fmtK(mx/2)}</span>`+
      `<span><i style="background:${lensColor(1,l.color)}"></i>${fmtK(mx)} ${l.unit}</span>`+
      ` <span class="sub" title="POI counts measured (Overture/OSM, lower bound); the per-category relevance weighting is an estimated model">◇ measured counts · estimated weighting</span>`;
    return;
  }
  // Macro-headwind lens: skeleton while the exposure layer loads, then an honest RELATIVE scale —
  // the scores are share-diluted (compare branches, not magnitudes) and tailwind-dominant reads 0.
  if(l.macx){
    if(!macxDone){ $('#maplegend').innerHTML='<span class="skel skel-line" style="display:inline-block;width:160px;vertical-align:middle" aria-hidden="true"></span> <span class="sub">macro exposure…</span>'; return; }
    $('#maplegend').innerHTML =
      `<span><i style="background:${lensColor(.12,l.color)}"></i>~0</span>`+
      `<span><i style="background:${lensColor(.5,l.color)}"></i>${fmtK(mx/2)}</span>`+
      `<span><i style="background:${lensColor(1,l.color)}"></i>${fmtK(mx)} ${l.unit}</span>`+
      ` <span class="sub" title="Occupation mix measured × sensitivity weights estimated × macro signals measured; share-diluted scores — compare branches relatively. Branches whose dominant macro factor is a tailwind read 0.">▲ estimated · relative · headwinds only</span>`;
    return;
  }
  $('#maplegend').innerHTML =
    `<span><i style="background:${lensColor(.12,l.color)}"></i>~0</span>
     <span><i style="background:${lensColor(.5,l.color)}"></i>${fmtK(mx/2)}</span>
     <span><i style="background:${lensColor(1,l.color)}"></i>${fmtK(mx)} ${l.unit}</span>${est}`;
}
function initMap(){
  if(mapReady){ map.invalidateSize(); applyMapFocus(); return; }
  if(!DATA) return;
  mapReady=true;
  // optional ?lens=<key> deep-link: pick the starting map lens (validated against LENS).
  try{ const ql=new URLSearchParams(location.search).get('lens'); if(ql&&LENS[ql]&&ql!==curLens){ curLens=ql; renderLenses(); } }catch(e){}
  map = L.map('map',{preferCanvas:true, attributionControl:true, zoomControl:true, scrollWheelZoom:true}).setView([13.4,101.2], window.innerWidth<600?5:6);
  // Light CARTO Positron basemap (marketing committee): a quiet, de-emphasized light map so the branch
  // data is the only saturated thing on screen — "quiet map, loud data" (Mapbox Light / CARTO recipe).
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{
    attribution:'&copy; OpenStreetMap &copy; CARTO', subdomains:'abcd', maxZoom:19}).addTo(map);
  const renderer = L.canvas({padding:0.5});
  markers = DATA.map(d=>{
    // dark thin stroke gives every dot a crisp edge on the light basemap (committee: 3:1 stroke)
    const m = L.circleMarker([d.y,d.x], {renderer, radius:4, weight:0.6, color:'rgba(20,26,34,.55)', fillOpacity:0.9});
    m._d=d; m.on('click',()=>selectBranch(d,m));
    return m.addTo(map);
  });
  map.on('popupclose', clearRadius);
  map.on('popupclose', clearLeadSites);   // lead-site pins live only while a branch popup is open
  addRadiusToggle();
  // P1: the district lenses (dws/drisk) read d._amp, which only exists after amphoe.json is joined.
  // Painting now would flash every branch pale (val 0) then snap when the join lands. So when we open
  // directly on a district lens, defer the first paint to the loadAmphoe().then below; otherwise paint
  // immediately as before. renderLegend() still runs so the legend isn't blank in the gap.
  const deferForAmp=isAmpLens(curLens)&&!ampJoinAttached;
  if(deferForAmp) renderLegend(); else styleMarkers();
  // warm the district join so popups always carry the amphoe white-space/risk block and the
  // district lenses recolour instantly. Small file, also used by the Acquisition tab.
  if(!ampJoinAttached) loadAmphoe().then(()=>{ if(mapReady){ renderLegend(); styleMarkers(); } });
  // warm the simplified amphoe polygons so the district lenses can paint the choropleth. Optional
  // + null-safe: absent/failed file leaves AGEO null and drawAmphoeChoropleth() is a no-op (dots only).
  if(!ageoLoaded) loadAmphoeGeo().then(()=>{ if(mapReady) drawAmphoeChoropleth(); });
  // warm the province polygons so hhdti/pstress can paint one shape per province instead of many
  // same-coloured dots. Optional + null-safe: absent/failed file leaves PGEO null (dots only).
  if(!pgeoLoaded) loadProvinceGeo().then(()=>{ if(mapReady) drawProvinceChoropleth(); });
  // warm the crop land-use layer so the Dominant-crop lens hides itself when absent and paints
  // categorically when present. Optional + null-safe: absent file → CROPLU null, lens filtered out.
  if(!cropLuLoaded) loadCropLanduse().then(()=>{ renderLenses(); if(mapReady&&LENS[curLens]&&LENS[curLens].cat){ renderLegend(); styleMarkers(); } });
  // warm the measured occupation rollup so branch popups carry the Overture occupation-mix block
  // when present (small, optional file). Absent → loader leaves OCCDATA null and nothing renders.
  if(!occLoaded) loadOccupations().then(()=>{ if(mapReady){ if(curLens==='estab'){ renderLegend(); styleMarkers(); } } });
  // warm the MEASURED per-branch employment & labour layer so branch popups carry the "Employment &
  // labour" section (occupation top-3, DIW factory workers, informal share, NSO province LFS) when
  // present. Optional + null-safe: absent file → LABORDATA stays null and the popup omits the block.
  if(!laborLoaded) loadBranchLabor();
  // warm the MEASURED household debt-to-income layer so the lens hides itself when absent and
  // popups carry the debt-to-income block. Absent file → loader leaves HHRISK empty, the lens is
  // filtered out, nothing renders.
  if(!hhriskLoaded) loadHouseholdRisk().then(()=>{ renderLenses(); if(mapReady&&curLens==='hhdti'){ renderLegend(); styleMarkers(); } });
  // warm the combined province structural-stress index (DTI + unemployment) so its lens hides
  // itself when absent. Absent file (build_province_stress.py not run / inputs missing) → PSTRESS
  // empty, lens filtered out.
  if(!pstressLoaded) loadProvinceStress().then(()=>{ renderLenses(); if(mapReady&&curLens==='pstress'){ renderLegend(); styleMarkers(); } });
  // warm the ESTIMATED title-loan search-demand layer (Google Trends) so its lens hides itself when
  // absent. Absent file (build_search_demand.py not run) → SDEMAND empty, lens filtered out.
  if(!sdemandLoaded) loadSearchDemand().then(()=>{ renderLenses(); if(mapReady&&curLens==='dsrch'){ renderLegend(); styleMarkers(); } });
  // warm the occupation × stress cross-read so the lens hides itself when absent. Absent file
  // (build_occupation_risk.py not run / no Overture pull yet) → OCCRISK empty, lens filtered out.
  if(!occriskLoaded) loadOccRisk().then(()=>{ renderLenses(); if(mapReady&&curLens==='occrisk'){ renderLegend(); styleMarkers(); } });
  // warm the per-branch COMPOSITE risk so its lens hides itself when absent (and is ready when picked).
  if(!briskLoaded) loadBranchRisk().then(()=>{ renderLenses(); if(mapReady&&curLens==='brisk'){ renderLegend(); styleMarkers(); } });
  // warm the MEASURED title-loan-relevant POI density so its menu lens disables itself when absent.
  if(!poirelLoaded) loadPoiRelevance().then(()=>{ renderLenses(); if(mapReady&&curLens==='poirel'){ renderLegend(); styleMarkers(); } });
  // warm the peer-twin deviation layer (vs-twins lens + popup line) — disables its pill when absent.
  if(!peersLoaded) loadBranchPeers().then(()=>{ renderLenses(); if(mapReady&&curLens==='peerdev'){ renderLegend(); styleMarkers(); } });
  // warm the ANSWER-FIRST popup layers (who-to-acquire lead board + macro-exposure chips) so the
  // first branch tap already carries them; selectBranch refreshes an open popup if they land late.
  // The macro layer also feeds the 'Macro headwind' lens, so on resolve re-render the pill row and
  // (if the lens is active, e.g. via ?lens=macx) repaint — otherwise the markers would stay pale 0s.
  if(!leadsLoaded) loadBranchLeads();
  // warm the "What moves this branch" top-2 macro drivers (est proxy) for the popup one-liner.
  if(!msensLoaded) loadMacroSens();
  if(!macxDone) loadMacroExposure().then(()=>{ renderLenses(); if(mapReady&&curLens==='macx'){ renderLegend(); styleMarkers(); } });
  // warm the MEASURED catchment layers (10km WorldPop population + merged rival census) so the first
  // branch tap already carries the "Catchment ≤10km" block; selectBranch refreshes an open popup if
  // they land late. Optional + null-safe: absent file → BPOP/CCEN stay null and the block is omitted.
  if(!bpopLoaded) loadBranchPopulation();
  if(!cpopLoaded) loadContestedPop();
  if(!ccenLoaded) loadCompetitorCensus();
  if(!cbrfLoaded) loadClusterBrief();
  if(!occlLoaded) loadOccLeads();
  if(!rivpLoaded) loadRivalPressure();
  if(!picobrLoaded) loadBranchPico();
  // warm the MEASURED lead-site coordinates (OSM points behind each branch's lead board) so the
  // pins draw on the first branch tap. Optional + null-safe: absent file → LSITES stays null,
  // selectBranch simply draws nothing.
  if(!lsitesLoaded) loadLeadSites();
  // warm the MEASURED building-density-within-10km popup line (Overture, projected from
  // source-data/perimeter_counts.json). Popup-only, no lens — selectBranch refreshes below.
  if(!bldgdenLoaded) loadBranchDensity();
  // warm the MEASURED-corrected per-branch crop-area popup block (SPAM×DOAE-2025). Popup-only, no lens.
  if(!croplandLoaded) loadBranchCropland();
  // warm the MEASURED per-branch fuel-station-within-10km popup line (OSM). Popup-only, no lens.
  if(!fuelstnLoaded) loadBranchFuel();
  // if the map opened directly on the competitor lens (e.g. ?lens=comp), warm the census now.
  if(curLens==='comp' && !compAttached){
    loadCompetitors().then(()=>{ if(curLens==='comp'&&mapReady){ renderLegend(); drawCompPoints(); styleMarkers(); } });
  }
  // if we arrived here from a district leaderboard row, fly to + ping that district now.
  applyMapFocus();
}
function selectBranch(d,m){
  // On phones the tall answer-first popup clips badly inside the small map, so route the SAME
  // popupHTML into a fixed bottom sheet instead of a Leaflet popup. Desktop path unchanged.
  const sheet=isMobileSheet();
  if(sheet) openBranchSheet(d);
  else m.bindPopup(popupHTML(d),{closeButton:true, maxWidth:320, minWidth:260}).openPopup();
  // "is this branch still the selected one?" — sheet path checks the sheet, popup path the popup.
  const stillOpen=()=>{ if(sheet) return isSheetOpenFor(d);
    const p=m.getPopup(); return !!(p&&p.isOpen&&p.isOpen()); };
  drawRadius(d);
  // MEASURED lead-site pins (WHERE the who-to-acquire leads physically are) — drawn only while
  // this popup/sheet is open; the previous branch's pins are cleared inside drawLeadSites. If the
  // tap beat the lazy fetch, draw once it lands (only if this branch is still the open one).
  if(LSITES) drawLeadSites(d);
  else loadLeadSites().then(()=>{ if(stillOpen()) drawLeadSites(d); });
  // the answer-first blocks (who-to-acquire + macro chips) lazy-load; if the tap beat the fetch,
  // re-render the still-open popup/sheet once they land so the FIRST read answers acquire + macro.
  // No-op when the files are absent (loaders resolve null, popupHTML output is unchanged).
  if(!LEADS||!MACX||!MSENS||!BPOP||!CPOP||!CCEN||!CBRF||!OCCL||!RIVP||!BLDGDEN||!WFDATA||!OCCDATA||!AGRIDATA||!CROPLAND||!VEHDATA||!RECDATA||!FUELSTN){
    Promise.all([loadBranchLeads(),loadMacroExposure(),loadMacroSens(),loadBranchPopulation(),loadContestedPop(),loadCompetitorCensus(),loadClusterBrief(),loadOccLeads(),loadRivalPressure(),loadBranchDensity(),loadWorkforce(),loadOccupations(),loadAgri(),loadBranchCropland(),loadBranchPico(),loadVehicles(),loadRecommendations(),loadBranchFuel()]).then(()=>{
      if(!stillOpen()) return;
      if(sheet) setSheetBody(popupHTML(d));
      else m.getPopup().setContent(popupHTML(d));
    });
  }
}
/* ---------- mobile bottom sheet (branch detail on the National map, ≤600px) ----------
   The Leaflet popup clips on small screens, so selectBranch routes popupHTML(d) into this fixed
   full-width sheet instead (max-height 62vh, internal scroll). Closes on handle tap, swipe-down,
   backdrop tap and Escape; closing performs the SAME cleanup the map 'popupclose' event does on
   desktop (clearRadius + clearLeadSites) so lead-site pins never outlive the sheet. Null-guarded:
   absent #msheet nodes (older HTML) → falls back to the Leaflet popup. z-index sits above the map
   (nav bar 2000) but below the nav More menu (2100). */
let sheetBranchIdx=-1, sheetTouchY=null, sheetReturnFocus=null;
function isMobileSheet(){
  try{ return matchMedia('(max-width:600px)').matches ||
       (matchMedia('(pointer:coarse)').matches && window.innerWidth<=700); }
  catch(e){ return false; }
}
function sheetEl(){ return document.getElementById('msheet'); }
function openBranchSheet(d){
  const s=sheetEl(), b=document.getElementById('msheet-backdrop'),
        body=document.getElementById('msheet-body');
  if(!s||!b||!body) return;                      // nodes absent → selectBranch's popup path still works
  // WCAG 2.4.3 / ARIA modal-dialog practice: remember what to restore focus to, then move
  // focus into the dialog so keyboard + screen-reader users land inside it (not stranded on the
  // now-inert map behind the aria-modal backdrop). Skip stealing focus if the opener wasn't a
  // real focus (e.g. a tap on a map marker leaves focus on <body>).
  const prev=document.activeElement;
  sheetReturnFocus=(prev && prev!==document.body && s!==prev && !s.contains(prev)) ? prev : null;
  sheetBranchIdx=idxOf(d);
  body.innerHTML=popupHTML(d);
  body.scrollTop=0;
  b.hidden=false; s.hidden=false;
  requestAnimationFrame(()=>{ s.classList.add('open'); b.classList.add('open'); try{ s.focus(); }catch(e){} });
  if(!s._wired){ wireBranchSheet(s,b,body); s._wired=true; }
}
function isSheetOpenFor(d){ const s=sheetEl(); return !!(s&&!s.hidden&&sheetBranchIdx===idxOf(d)); }
function setSheetBody(html){ const body=document.getElementById('msheet-body'); if(body) body.innerHTML=html; }
function closeBranchSheet(){
  const s=sheetEl(), b=document.getElementById('msheet-backdrop');
  if(!s||s.hidden) return;
  sheetBranchIdx=-1;
  s.classList.remove('open'); if(b) b.classList.remove('open');
  setTimeout(()=>{ s.hidden=true; if(b) b.hidden=true; },180);   // let the slide-down play
  // WCAG 2.4.3: hand focus back to whatever opened the sheet, so the keyboard user isn't
  // dropped at the top of the document after the dialog closes.
  const rf=sheetReturnFocus; sheetReturnFocus=null;
  if(rf && rf.isConnected){ try{ rf.focus(); }catch(e){} }
  // same cleanup the Leaflet popupclose handlers perform on desktop
  try{ clearRadius(); }catch(e){}
  try{ clearLeadSites(); }catch(e){}
}
function wireBranchSheet(s,b,body){
  b.addEventListener('click',closeBranchSheet);
  const h=document.getElementById('msheet-handle');
  if(h){ h.addEventListener('click',closeBranchSheet);
    // WCAG 2.1.1: the handle is role=button tabindex=0, but a <div> doesn't fire click on
    // Enter/Space like a native button — wire keyboard activation so it's operable by keyboard.
    h.addEventListener('keydown',e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); closeBranchSheet(); } }); }
  document.addEventListener('keydown',e=>{ if(e.key==='Escape') closeBranchSheet(); });
  // WCAG 2.4.3 focus trap: #msheet is aria-modal, so Tab must cycle WITHIN it — otherwise Tab
  // from the last control lands on the map/nav behind the backdrop. Wrap first↔last (the handle
  // is first, the body's links follow); only the boundaries are intercepted, interior tabbing
  // stays native. Empty body → keep focus on the handle rather than let it escape.
  s.addEventListener('keydown',e=>{
    if(e.key!=='Tab') return;
    const f=s.querySelectorAll('a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"])');
    const list=Array.prototype.filter.call(f,el=>el.offsetParent!==null);
    if(!list.length){ e.preventDefault(); s.focus(); return; }
    const first=list[0], last=list[list.length-1], a=document.activeElement;
    if(e.shiftKey){ if(a===first||a===s){ e.preventDefault(); last.focus(); } }
    else if(a===last){ e.preventDefault(); first.focus(); }
  });
  // simple swipe-down-to-close: arm on touchstart unless the body is mid-scroll (so internal
  // scrolling never fights the gesture); a downward drag past the threshold closes the sheet.
  s.addEventListener('touchstart',e=>{
    const t=e.touches[0]; if(!t){ sheetTouchY=null; return; }
    sheetTouchY=(body.contains(e.target)&&body.scrollTop>2)?null:t.clientY;
  },{passive:true});
  s.addEventListener('touchmove',e=>{
    if(sheetTouchY==null) return;
    const t=e.touches[0]; if(!t) return;
    if(t.clientY-sheetTouchY>60){ sheetTouchY=null; closeBranchSheet(); }
  },{passive:true});
  s.addEventListener('touchend',()=>{ sheetTouchY=null; });
}
// lead-site pin layer — tiny category-coloured circleMarkers around the SELECTED branch only
// (≤12, MEASURED OSM coordinates from lead_sites.json). Rebuilt per selection, cleared on
// popupclose. Null-safe: absent file/entry → draws nothing, returns 0.
let leadSiteLayer=null;
function clearLeadSites(){ if(leadSiteLayer&&map){ map.removeLayer(leadSiteLayer); } leadSiteLayer=null; }
function drawLeadSites(d){
  clearLeadSites();
  if(!mapReady||!map||!LSITES||!LSITES.length||!DATA) return 0;
  const i=idxOf(d); if(i<0) return 0;
  const sites=LSITES[i]; if(!Array.isArray(sites)||!sites.length) return 0;
  const cats=(lsitesMeta&&lsitesMeta.categories)||[];
  leadSiteLayer=L.layerGroup();
  sites.forEach(s=>{
    if(!Array.isArray(s)||s.length<4) return;
    const c=cats[s[0]]||{};
    const col=LEADSITE_COL[c.k]||'#8b90a7';
    L.circleMarker([s[2],s[1]],{radius:4,weight:1,color:col,fillColor:col,fillOpacity:.8,opacity:.95})
      .bindTooltip(`${c.label||'Lead site'} · ${s[3]} km (measured OSM)`,{direction:'top',opacity:.92})
      .addTo(leadSiteLayer);
  });
  leadSiteLayer.addTo(map);
  return sites.length;
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
// Rival-pressure line for a branch popup — ONE compact MEASURED line from the precomputed
// rival_pressure.json (nearest-rival km per brand + 2km/5km counts + stated siege rule), e.g.
// "Rivals: 4 within 2 km · 9 ≤5 km · nearest Srisawad 0.4 km". Null-guarded: absent file or
// entry → empty string, nothing fabricated. Loaded by the same warm path as the other layers.
function rivalPressureLineHTML(d){
  const e=rivpRec(d); if(!e||!Array.isArray(e.d)) return '';
  let nb=-1;
  for(let j=0;j<e.d.length;j++){ if(e.d[j]!=null&&(nb<0||e.d[j]<e.d[nb])) nb=j; }
  const near=nb>=0?`nearest ${RIVP.brands[nb]} ${e.d[nb]} km`:'no rival located';
  const col=e.s?'var(--agri)':(e.n2>0?'var(--gold)':'var(--merch)');
  const siege=e.s?` <span style="color:var(--agri);font-weight:700" title="siege = ≥3 rivals within 2 km (stated rule over measured counts)">⚑ under siege</span>`:'';
  return `<div class="pr" style="margin-top:4px"><span title="measured — haversine vs the merged competitor census (official locators; Heng sample)">Rival pressure (measured)</span>`
    +`<b style="color:${col}">${e.n2} ≤2 km · ${e.n5} ≤5 km · ${near}${siege}</b></div>`;
}
// Licensed-PICO rival line for a branch popup — ONE compact MEASURED line from branch_pico.json:
// how many licensed PICO-finance (พิโกไฟแนนซ์) operators are registered in THIS branch's district
// (อำเภอ), the small-ticket rival class the big-4 census above does not include. District grain (the
// FPO registry carries an address, not coordinates), stated in the line. A district with none is an
// honest zero (both sides share amphoe.json's identity) — shown as "none registered". Null-guarded:
// absent file/record → empty string, nothing fabricated.
function picoLineHTML(d){
  const e=picoBrRec(d); if(!e||typeof e.pico!=='number') return '';
  const col=e.pico>=8?'var(--agri)':(e.pico>0?'var(--gold)':'var(--merch)');
  const body=e.pico>0
    ? `${e.pico} in อำเภอ`+(e.head||e.branch?` (${e.head} head · ${e.branch} branch)`:'')+(e.recent?` · ${e.recent} newly licensed`:'')
    : 'none registered in อำเภอ';
  return `<div class="pr" style="margin-top:4px"><span title="measured — licensed PICO-finance operators registered in this branch's district (FPO registry via pico_district.json, joined by amphoe); district grain, not a km radius">Licensed PICO rivals (measured)</span>`
    +`<b style="color:${col}">${body}</b></div>`;
}
// Catchment block for a branch popup — three MEASURED numbers about this branch's ~10km catchment:
// (1) reachable population INSIDE the 10km circle (WorldPop 2020, data/branch_population.json .values[i]);
// (2) total establishments ≤10km = sum of this branch's OSM k10 counts (branches.json); (3) rival
// branches ≤10km from the merged competitor census (data/competitors_census.json, client-side haversine).
// Fully null-guarded: each line renders only when its measured value exists, and the whole block is
// omitted when none of the three are available. Nothing is fabricated.
function catchmentPopupHTML(d,sec,r){
  const i=idxOf(d);
  // contested-population overlay (contested_pop.json rows[i]=[pop10, contested_pop], measured);
  // falls back to its pop10 when branch_population.json is absent (same raster, same method).
  const cp=(CPOP&&i>=0&&i<CPOP.rows.length&&Array.isArray(CPOP.rows[i]))?CPOP.rows[i]:null;
  const pop=(BPOP&&i>=0&&i<BPOP.length&&BPOP[i]!=null)?BPOP[i]:(cp?cp[0]:null);
  const cpct=(cp&&cp[0]>0)?Math.round(100*cp[1]/cp[0]):null;
  const cc=cpct==null?'':cpct>=60?'var(--agri)':cpct>=35?'var(--gold)':'var(--merch)';
  const hasK=d.k10&&typeof d.k10==='object';
  const estab=hasK?Object.values(d.k10).reduce((a,v)=>a+(v||0),0):null;
  const rivals=catchRivalCount(d);
  if(pop==null && estab==null && rivals==null) return '';     // nothing measured to show → omit block
  const rc=rivals!=null&&rivals>0?'var(--agri)':'var(--merch)';
  return sec('Catchment ≤10km — measured')
    + (pop!=null?r('Catchment population', pop.toLocaleString()
        +(cpct!=null?` · <span style="color:${cc}" title="share of this 10km population also living within 2km of a rival branch — measured WorldPop 2020 × competitor census; census lower bound">${cpct}% contested by rivals</span>`:''), 'var(--accent)'):'')
    + (estab!=null?r('Establishments ≤10km (OSM)', estab.toLocaleString(), 'var(--merch)'):'')
    + (rivals!=null?r('Rival branches ≤10km', `<span style="color:${rc}">${rivals}</span>`, rc):'')
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">population = WorldPop 2020 inside this branch's 10km circle${cpct!=null?'; contested = share of that population within 2km of any census rival (lower bound — Heng sampled, sub-scale operators missing)':''}; establishments = sum of OSM POI counts ≤10km; rivals = official store-locator census (Muangthai/Srisawad/Tidlor measured-complete; Heng sample)</div>`;
}
// Macro cluster brief — a one-line plain-language read of the macro forces on this branch's customer
// cluster (cluster_brief.json, index-aligned; templated from measured board/crop/occupation signals).
// Loaded by boot() warming; renders nothing until available. Objective #1 made human-readable.
function briefPopupHTML(d,sec,r){
  const i=idxOf(d);
  const b=(CBRF&&i>=0&&i<CBRF.length)?CBRF[i]:null;
  const line=b&&typeof b.line==='string'?b.line.trim():'';
  if(!line) return '';
  return sec('Macro read — this cluster')
    + `<div style="font-size:12px;line-height:1.5;color:#c7cedd;padding:2px 0">${line}</div>`
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">templated from measured commodity-board YoY, crop-stress and occupation mix</div>`;
}
// NAMED occupation leads — the actual businesses to CALL near this branch, by occupation (Overture
// Places, name+phone). occupation_leads.json .branches[i].L = [[bucket_idx, name, phone, dist_km],...].
// The reframed core objective, on the front-door map. Null-guarded; renders nothing when absent.
function occLeadsPopupHTML(d,sec,r){
  const i=idxOf(d);
  const L=(OCCL&&i>=0&&i<OCCL.length&&OCCL[i]&&Array.isArray(OCCL[i].L))?OCCL[i].L:null;
  if(!L||!L.length||!OCCLB) return '';
  const byB={}; L.forEach(function(e){(byB[e[0]]=byB[e[0]]||[]).push(e);});
  const order=Object.keys(byB).map(Number).sort(function(a,b){return byB[b].length-byB[a].length;}).slice(0,5);
  const rows=order.map(function(bi){
    const lab=(OCCLB[bi]&&OCCLB[bi].label)||'—', e=byB[bi][0];  // nearest lead in this bucket
    const ph=(e[2]||'').replace(/\s/g,'');
    const call=ph?`<a href="tel:${ph}" style="color:var(--accent);text-decoration:none;font-family:'IBM Plex Mono'">${e[2]}</a>`:'<span class="sub">—</span>';
    return `<div style="display:flex;justify-content:space-between;gap:8px;font-size:11.5px;padding:1px 0">`
      +`<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><b style="color:var(--mid);font-weight:600">${lab.split(' ')[0]}</b> · ${e[1]}</span>${call}</div>`;
  }).join('');
  return sec('Leads to call — by occupation (measured)')
    + rows
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">nearest named establishment per occupation ≤10km (Overture Places); tap phone to call. Full list in the branch 3D scene.</div>`;
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
// WORKFORCE mix block — the reflective "who works in this 10km" answer (data/branch_workforce.json).
// Shows the estimated occupation mix (people), so farmers surface where they truly are — the
// lead-by-occupation signal. ESTIMATED, provenance-labelled. Graceful: absent file/entry → no block.
function workforcePopupHTML(d,sec){
  if(!WFDATA||!WFDATA.branches||!WFDATA.buckets||!DATA) return '';
  const i=idxOf(d); if(i<0) return '';
  const e=WFDATA.branches[i]; if(!e||!(e.t>0)) return '';
  let rows=WFDATA.buckets.map((bk,j)=>({lab:bk.label,col:OCC_BUCKET_COL[bk.key]||'#8b90a7',
      v:(e.w&&e.w[j])||0,pct:(e.mix&&e.mix[j])||0}))
    .filter(rw=>rw.v>0).sort((a,b)=>b.v-a.v).slice(0,6);
  if(!rows.length) return '';
  const mx=rows[0].pct||1;
  return sec('Workforce mix (estimated · who works here)')
    + `<div class="occ" style="margin-top:2px">`+rows.map(rw=>{
        const w=Math.max(4,Math.round(rw.pct/mx*100));
        return `<div class="pr" style="gap:8px"><span style="flex:1">${rw.lab}</span>`
          +`<span class="bar" style="flex:0 0 62px"><i style="width:${w}%;background:${rw.col}"></i></span>`
          +`<b class="mono" style="color:${rw.col};min-width:34px;text-align:right">${rw.pct}%</b></div>`;
      }).join('')
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">~${(e.t||0).toLocaleString()} workers ≤10km by occupation (ESTIMATED — farmers from SPAM cropland × OAE area anchored to NSO; factory DIW; services Overture×headcount) ${TAG_E}</div>`
    + `</div>`;
}
// AGRICULTURE profile block — crop exposure + REAL farm-gate price stress + drought + income
// (data/branch_agri.json). Only renders for branches with cropland in the catchment. The
// price signal is measured Thai OAE farm-gate YoY; the rest is estimated. Serves objective #1.
const AGRI_CROP_COL={rice:'#E6B450',cassava:'#C8433B',maize:'#7A4FE0',oilpalm:'#1C8C7D',sugarcane:'#8b90a7'};
function agriPopupHTML(d,sec,r){
  if(!AGRIDATA||!AGRIDATA.branches||!AGRIDATA.meta||!DATA) return '';
  const i=idxOf(d); if(i<0) return '';
  const e=AGRIDATA.branches[i]; if(!e||!(e.crop_ha>0)) return '';
  const crops=AGRIDATA.meta.crops||[];
  let rows=crops.map((c,j)=>({lab:c.label,col:AGRI_CROP_COL[c.key]||'#8b90a7',
      ha:(e.ha&&e.ha[j])||0,sh:(e.sh&&e.sh[j])||0}))
    .filter(rw=>rw.ha>0).sort((a,b)=>b.ha-a.ha);
  if(!rows.length) return '';
  const mx=rows[0].sh||1;
  // colour the pressure/price stress
  const pcol=e.agri_pressure>=40?'var(--agri)':(e.agri_pressure>=20?'var(--gold)':'#8b90a7');
  const yoyStr=e.price_yoy!=null?(e.price_yoy>0?'+':'')+e.price_yoy+'%':'n/a';
  const ycol=e.price_yoy!=null&&e.price_yoy<0?'var(--agri)':(e.price_yoy>0?'var(--merch)':'#8b90a7');
  let html=sec('Agriculture — crop exposure & stress')
    + `<div class="occ" style="margin-top:2px">`+rows.slice(0,5).map(rw=>{
        const w=Math.max(4,Math.round(rw.sh/mx*100)), pct=Math.round(rw.sh*100);
        return `<div class="pr" style="gap:8px"><span style="flex:1">${rw.lab}</span>`
          +`<span class="bar" style="flex:0 0 62px"><i style="width:${w}%;background:${rw.col}"></i></span>`
          +`<b class="mono" style="color:${rw.col};min-width:30px;text-align:right">${pct}%</b></div>`;
      }).join('')+`</div>`;
  html+=r('Farm-gate price YoY (crop mix)', `<b style="color:${ycol}">${yoyStr}</b> `+TAG_M, ycol);
  if(e.rain_anom!=null) html+=r('Rainfall (3-mo, % of normal)', e.rain_anom+'% '+TAG_M,
      e.rain_anom<90?'var(--gold)':'#8b90a7');
  html+=r('Agri pressure (price + drought)', `<b style="color:${pcol}">${e.agri_pressure}</b> / 100 ${TAG_E}`, pcol);
  if(e.income_est>0) html+=r('Est. gross farm income ≤10km', '฿'+(e.income_est/1e6).toFixed(1)+'M/yr '+TAG_E, 'var(--merch)');
  html+=`<div class="sub" style="margin:2px 0 0;font-size:10px">crop mix SPAM (modelled); price YoY MEASURED · OAE farm-gate; rainfall MEASURED · HDX; income + pressure ESTIMATED. Serves portfolio/PD risk.</div>`;
  return html;
}
// MEASURED-CORRECTED CROP AREA block (data/branch_cropland.json) — absolute cropland hectares in the
// 10km catchment, SPAM-2010's within-province spatial pattern rescaled to DOAE's MEASURED 2025
// provincial planted-area magnitude. Complements agriPopupHTML's crop SHARE bars by giving the AREA
// magnitude a share-only view hides. Labelled honestly: magnitude measured-corrected, fine spatial
// distribution modelled, sugarcane uncorrected (OCSB). Only renders where crop_ha>0. Empty when absent.
const CROPLAND_LABEL={rice:'Rice',cassava:'Cassava',maize:'Maize',oilpalm:'Oil palm',sugarcane:'Sugarcane'};
function croplandPopupHTML(d,sec,r){
  const e=croplandRec(d); if(!e||!(e.crop_ha>0)) return '';
  const keys=(croplandMeta&&croplandMeta.crops)||['rice','cassava','maize','oilpalm','sugarcane'];
  const rows=keys.map((k,j)=>({k,lab:CROPLAND_LABEL[k]||k,col:AGRI_CROP_COL[k]||'#8b90a7',ha:(e.ha&&e.ha[j])||0}))
    .filter(rw=>rw.ha>0).sort((a,b)=>b.ha-a.ha);
  if(!rows.length) return '';
  const fmtHa=v=>Math.round(v).toLocaleString();
  const dom=rows[0];
  const top=rows.slice(0,3).map(rw=>`<span style="color:${rw.col}">${rw.lab} ${fmtHa(rw.ha)}</span>`).join(' · ');
  return sec('Cropland ≤10km — DOAE-2025 magnitude · measured-corrected')
    + r('Crop area ≤10km', `${Math.round(e.crop_ha).toLocaleString()} <span class="sub">ha</span>`, 'var(--gold)')
    + r('Dominant crop', `<span style="color:${dom.col}">${dom.lab}</span> <span class="sub">${fmtHa(dom.ha)} ha</span>`, dom.col)
    + `<div class="pr"><span>Top crops (ha)</span><b style="text-align:right">${top}</b></div>`
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">absolute hectares MEASURED-CORRECTED to DOAE 2025 farmer-registry provincial planted area; SPAM-2010 supplies the within-province spatial pattern (modelled); sugarcane uncorrected (OCSB). Serves portfolio/agri-PD risk.</div>`;
}
// VEHICLE COLLATERAL block — AutoX's title-loan asset base (data/branch_vehicles.json). Estimated
// fleet by type in the 10km catchment + pickup share + a collateral-density score. Mix MEASURED (DLT
// province stock); catchment allocation ESTIMATED (population-weighted).
const VEH_TYPE_COL={pickup:'#E6B450',car:'#5B7CFA',moto:'#1C8C7D',ev:'#7A4FE0'};
function vehiclePopupHTML(d,sec,r){
  if(!VEHDATA||!VEHDATA.branches||!VEHDATA.meta||!DATA) return '';
  const i=idxOf(d); if(i<0) return '';
  const e=VEHDATA.branches[i]; if(!e||!(e.n_est>0)) return '';
  const L=VEHDATA.meta.labels||{};
  const order=['pickup','car','moto','ev'].filter(t=>(e.fleet&&e.fleet[t])>0);
  const mx=Math.max(...order.map(t=>e.fleet[t]))||1;
  const cscore=e.collateral_score, ccol=cscore>=60?'var(--gold)':(cscore>=35?'#5B7CFA':'#8b90a7');
  let html=sec('Vehicle collateral (≤10km · title-loan base)')
    + `<div class="occ" style="margin-top:2px">`+order.map(t=>{
        const w=Math.max(4,Math.round(e.fleet[t]/mx*100));
        return `<div class="pr" style="gap:8px"><span style="flex:1">${L[t]||t}</span>`
          +`<span class="bar" style="flex:0 0 62px"><i style="width:${w}%;background:${VEH_TYPE_COL[t]||'#8b90a7'}"></i></span>`
          +`<b class="mono" style="color:${VEH_TYPE_COL[t]||'#8b90a7'};min-width:52px;text-align:right">${e.fleet[t].toLocaleString()}</b></div>`;
      }).join('')+`</div>`;
  html+=r('Pickup share (prime collateral)', `<b style="color:var(--gold)">${e.pickup_share}%</b> `+TAG_M, 'var(--gold)');
  html+=r('Collateral density score', `<b style="color:${ccol}">${cscore}</b> / 100 ${TAG_E}`, ccol);
  html+=`<div class="sub" style="margin:2px 0 0;font-size:10px">~${e.n_est.toLocaleString()} vehicles est. in the catchment. Mix MEASURED · DLT province stock; allocation ESTIMATED (population). Brands · trends · trucks · agri-vehicles need the DLT deep pull.</div>`;
  return html;
}
function occPopupHTML(d,sec){
  if(!OCCDATA||!OCCDATA.branches||!OCCDATA.buckets||!DATA) return '';
  const i=idxOf(d); if(i<0) return '';
  const e=OCCDATA.branches[i]; if(!e||!(e.t>0)) return '';
  let rows=OCCDATA.buckets.map((bk,j)=>({lab:bk.label,col:OCC_BUCKET_COL[bk.key]||'#8b90a7',v:(e.o&&e.o[j])||0}))
    .filter(rw=>rw.v>0).sort((a,b)=>b.v-a.v).slice(0,6);
  if(!rows.length) return '';
  const tot=rows.reduce((a,rw)=>a+rw.v,0)||1, mx=rows[0].v||1;
  return sec('Businesses & services nearby (measured · Overture)')
    + `<div class="occ" style="margin-top:2px">`+rows.map(rw=>{
        const pct=Math.round(rw.v/tot*100), w=Math.max(4,Math.round(rw.v/mx*100));
        return `<div class="pr" style="gap:8px"><span style="flex:1">${rw.lab}</span>`
          +`<span class="bar" style="flex:0 0 62px"><i style="width:${w}%;background:${rw.col}"></i></span>`
          +`<b class="mono" style="color:${rw.col};min-width:30px;text-align:right">${pct}%</b></div>`;
      }).join('')
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">${(e.t||0).toLocaleString()} establishments ≤10km by category (Overture Maps Places — storefronts, a sample/lower bound; workforce mix above is the who-works-here read)</div>`
    + `</div>`;
}
// Employment & labour block for a branch popup — the MEASURED per-branch labour layer
// (data/branch_labor.json). Shows the top-3 catchment occupation buckets with small share bars
// (MEASURED · Overture), factory workers in the branch's district (MEASURED · DIW), the province
// informal share, and a one-line province Labour-Force-Survey readout (MEASURED · NSO). Fully
// graceful: absent file/entry → no block; each sub-line only renders when its measured value exists.
function laborPopupHTML(d,sec,r){
  const e=laborRec(d); if(!e) return '';
  const ot=Array.isArray(e.occ_top)?e.occ_top:[];
  // If the fuller occupation-mix block (occPopupHTML, OCCDATA) will render its own top-6 bars for
  // this branch, skip our top-3 bars here to avoid a duplicate list — we keep the labour-market
  // lines (factory workers, informal, province LFS) which that block does NOT show.
  const occElsewhere = estabCount(d)>0;
  const hasOcc=ot.length>0 && !occElsewhere;
  const hasFac=e.factory_workers!=null;
  const hasInf=e.informal_pct!=null;
  const hasLfs=e.prov_employed_k!=null;
  // informal_pct is an HONEST NULL for provinces NSO doesn't publish (Bangkok's 170 branches). If we
  // have any other labour signal for this branch, still show the informal line as 'not published (NSO)'
  // rather than silently dropping it — a gap named is more honest than a gap hidden.
  const showInfGap = !hasInf && (hasOcc||hasFac||hasLfs);
  if(!hasOcc&&!hasFac&&!hasInf&&!hasLfs) return '';
  const occCol=['var(--accent)','#7f93d6','#8b90a7'];
  let html=sec('Employment & labour');
  if(hasOcc){
    const mx=ot[0].share_pct||1;
    html+=`<div class="occ" style="margin-top:2px">`+ot.map((rw,i)=>{
        const col=occCol[i]||'#8b90a7', w=Math.max(4,Math.round((rw.share_pct||0)/mx*100));
        return `<div class="pr" style="gap:8px"><span style="flex:1">${rw.label||'—'}</span>`
          +`<span class="bar" style="flex:0 0 62px"><i style="width:${w}%;background:${col}"></i></span>`
          +`<b class="mono" style="color:${col};min-width:34px;text-align:right">${rw.share_pct}%</b></div>`;
      }).join('')
      +`<div class="sub" style="margin:2px 0 3px;font-size:10px">top-3 of ${(e.estab_total||0).toLocaleString()} establishments ≤10km by category (MEASURED · Overture · a sample/lower bound) ${TAG_M}</div>`
      +`</div>`;
  }
  if(hasFac) html+=r('Factory workers in district', e.factory_workers.toLocaleString()+' '+TAG_M, 'var(--gold)');
  if(hasInf) html+=r('Province informal share', e.informal_pct+'% '+TAG_M, 'var(--collat)');
  else if(showInfGap) html+=r('Province informal share', nsoNum(null), 'var(--collat)');
  if(hasLfs){
    const ur=e.prov_unemployment_rate;
    html+=r('Province labour force', `${(e.prov_labor_force_k||0).toLocaleString()}k`+(ur!=null?` · ${ur}% unemp`:'')+' '+TAG_M, '#c7cedd');
    html+=`<div class="sub" style="margin:2px 0 0;font-size:10px">province: ${(e.prov_employed_k||0).toLocaleString()}k employed${ur!=null?`, unemployment ${ur}%`:''} — MEASURED · NSO Labour Force Survey. Factory workers MEASURED · DIW (district); informal share MEASURED · NSO (province).</div>`;
  }
  return html;
}
// Occupation × stress block for a branch popup — the occupation_risk.json cross-read. Shows the
// ESTIMATED occupation-stress score (MEASURED shares × ESTIMATED stress weighting) and, when the
// branch is FLAGGED, a one-line callout naming the concentrated stressed base. Fully graceful:
// absent file / absent entry → no block. Only renders something when there is a real read (t>0).
function occriskPopupHTML(d,sec,r){
  const e=occriskRec(d); if(!e||!(e.t>0)) return '';
  const sc=e.s||0;
  // data-driven colour ramp: red at ≥ meta.flag_threshold (the build-time p95 of nonzero scores,
  // ~2.4 in the current vintage), amber at ≥ half of it. The old hardcoded 25/40 cutpoints sat far
  // above the achievable score ceiling, so even FLAGGED branches showed grey score text. Falls back
  // to the old cutpoints only when meta is absent.
  const th=(occriskMeta&&typeof occriskMeta.flag_threshold==='number')?occriskMeta.flag_threshold:null;
  const col=th!=null?(sc>=th?'var(--agri)':sc>=th/2?'var(--gold)':'#8b90a7')
                    :(sc>=40?'var(--agri)':sc>=25?'var(--gold)':'#8b90a7');
  const domLab=e.d?occLabel(e.d):'—';
  return sec('Occupation × stress — MEASURED mix · ESTIMATED weighting')
    + r('Occupation-stress ▲ · est', `<span style="color:${col}">${sc}</span> <span class="sub">/100</span>`, col)
    + r('Dominant base · measured', `${domLab}${e.ds?` <span class="sub">${Math.round(e.ds*100)}%</span>`:''}`, '#8b90a7')
    + (e.f?`<div class="sub" style="margin:2px 0 0;font-size:10px;color:var(--agri)">⚠ FLAGGED — borrower base concentrated in a stressed sector (occupation shares MEASURED; stressed-sector weighting ESTIMATED). A triage flag, not a measured default rate.</div>`
          :`<div class="sub" style="margin:2px 0 0;font-size:10px">occupation shares MEASURED (Overture, lower bound); stressed-sector weighting ESTIMATED (factory slowdown · province crop-stress)</div>`);
}
// Relevant-POI density block for a branch popup — the MEASURED title-loan-relevant POI counts
// within ~10km, fused into a 0–100 score by an ESTIMATED per-category relevance model. Renders
// only once poi_relevance.json is loaded and carries this branch.
const POIREL_CAT_LABEL={gold:'Gold shops',vehicle:'Vehicle dealers',fresh_mkt:'Fresh markets',
  agri:'Farms / agri',factory:'Factories',commerce:'Convenience & supers',
  retail_general:'Retail (all shops)',food_service:'Food service',school:'Schools'};
function poiRelevancePopupHTML(d,sec,r){
  const e=poiRelevanceRec(d); if(!e) return '';
  const sc=Math.round(e.rel||0);
  const col=sc>=60?'var(--gold)':sc>=35?'#cda23e':'#8b90a7';
  const cat=e.cat||{};
  const top=Object.keys(cat).filter(k=>cat[k]>0).sort((a,b)=>cat[b]-cat[a]).slice(0,3)
    .map(k=>`${POIREL_CAT_LABEL[k]||k} ${cat[k]}`).join(' · ');
  return sec('Relevant POI density — MEASURED counts · ESTIMATED weighting')
    + r('Relevant-POI density ◇', `<span style="color:${col}">${sc}</span> <span class="sub">/100</span>`, col)
    + (top?r('Top relevant POIs ≤10km', top, '#8b90a7'):'')
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">POI counts MEASURED (Overture/OSM, a sample / lower bound); the per-category relevance WEIGHTING that fuses them into one score is ESTIMATED (judgement model)</div>`;
}
// Building-density block for a branch popup — MEASURED Overture footprint count within 10km
// (data/branch_density.json, projected from source-data/perimeter_counts.json). A single line;
// a zero/low count can mean the underlying catchment pull was capped before reaching this branch
// (see meta.caveats), not that the ground truth is empty — stated inline so it isn't over-read.
const BLDGDEN_BUCKET_LABEL={rich_1000plus:'dense',good_200_999:'moderate',thin_50_199:'thin',
  sparse_1_49:'sparse',empty_0:'none in capped pull'};
function bldgDensityPopupHTML(d,r){
  const e=bldgDensityRec(d); if(!e) return '';
  const n=e.buildings_10km||0;
  const col=n>=1000?'#8b90a7':n>=200?'var(--gold)':n>0?'#cda23e':'var(--mid)';
  return r('Buildings ≤10km (Overture) · measured',
    `${n.toLocaleString()} <span class="sub">(${BLDGDEN_BUCKET_LABEL[e.bucket]||e.bucket})</span>`, col);
}
// FUEL-STATION density line for a branch popup — MEASURED OSM amenity=fuel count ≤10km, a vehicle-
// economy / rural-reach signal for the title book. Thresholds are anchored on the layer's own median
// (11 = moderate). OSM completeness varies, so the count is a FLOOR (stated inline): a low/zero value
// can mean thin OSM mapping here, not no fuel on the ground. Omitted when the file/entry is absent.
function fuelPopupHTML(d,r){
  const e=fuelStnRec(d); if(!e||e.n10==null) return '';
  const n=e.n10||0;
  const lab=n>=30?'dense':n>=11?'moderate':n>0?'thin':'none mapped';
  const col=n>=30?'#8b90a7':n>=11?'var(--gold)':n>0?'#cda23e':'var(--mid)';
  return r('Fuel stations ≤10km (OSM) · measured floor',
    `${n.toLocaleString()} <span class="sub">(${lab})</span>`, col);
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
  // MEASURED district-grain PICO-finance rival count (obj #2, competitive) — shown only when the
  // pico fold is present on the record; a district absent from the FPO registry is a measured zero.
  const picoLine = (a.pico!=null)
    ? r('PICO rivals in district ◆ · measured', `<span style="color:${a.pico?'var(--collat)':'#8b90a7'}">${(a.pico||0).toLocaleString()}</span> <span class="sub">licensed</span>`, a.pico?'var(--collat)':'#8b90a7')
    : '';
  // MEASURED competitive-pressure ratio (obj #2): PICO rivals per AutoX branch in this district.
  // Shown only where AutoX operates AND rivals exist; red when outnumbered (>1×), green when we lead.
  const orat = a.pico_ratio;
  const outColor = (orat!=null && orat>1) ? 'var(--agri)' : 'var(--merch)';
  const outnumLine = (orat!=null && a.pico>0)
    ? r('PICO rivals per branch ◆ · measured', `<span style="color:${outColor}">${orat.toFixed(orat<10?1:0)}×</span> <span class="sub">${a.pico} vs ${a.branches} branch${a.branches===1?'':'es'}</span>`, outColor)
    : '';
  return sec('District (amphoe) — coverage & risk')
    + r('White-space ◇ · measured', `<span style="color:${wc}">${ws}</span> <span class="sub">/100</span>`, wc)
    + r('District risk ▲ · est', `<span style="color:${rc}">${rk}</span> <span class="sub">/100</span>`, rc)
    + r('AutoX in district · measured', (a.branches||0)+(a.branches===1?' branch':' branches'), 'var(--accent)')
    + picoLine
    + outnumLine
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">coverage gap = district demand vs AutoX saturation (measured); risk = province-inherited agri-stress + local mix (estimated); PICO = licensed พิโกไฟแนนซ์ rivals in this district (measured, FPO registry); per-branch = PICO rivals ÷ AutoX branches here (measured, obj #2 competitive pressure)</div>`;
}
// ANSWER-FIRST §1 — "Who to acquire here": the branch's top-3 occupation leads from
// branch_leads.json. Counts (n) are MEASURED (Overture establishments ≤10km, lower bound);
// the high/med/low fit tag and the ⚠ stressed-sector flag are ESTIMATED (editorial fit map,
// rationale surfaced as the row tooltip). One "untapped" line when u[] is non-empty (big measured
// presence, bottom-quartile segment score — an inference, stated as est). Empty when absent.
const LEAD_FIT_LAB={h:'high fit',m:'med fit',l:'low fit'};
const LEAD_FIT_COL={h:'var(--merch)',m:'var(--gold)',l:'var(--mid)'};
function leadsPopupHTML(d,sec,r){
  const e=leadsRec(d); if(!e||!e.leads||!e.leads.length) return '';
  const esc=s=>String(s||'').replace(/"/g,'&quot;');
  let h=sec('Who to acquire here — top leads (measured nearby)');
  e.leads.slice(0,3).forEach(L=>{
    const bk=(leadsBK&&leadsBK[L.k])||{};
    const tip=esc((bk.why||'')+(L.rf?' ⚠ Stressed sector — court with careful underwriting, never exclude (est).':''));
    h+=r(`<span title="${tip}">${bk.label||L.k}${L.rf?' <span style="color:var(--agri)" title="stressed sector — underwrite carefully (est)">⚠</span>':''}</span>`,
         `${(L.n||0).toLocaleString()} <span class="sub" style="color:${LEAD_FIT_COL[L.f]||'var(--mid)'};font-size:10px">${LEAD_FIT_LAB[L.f]||''}</span>`,
         'var(--hi)');
  });
  if(e.u&&e.u.length){
    const u=e.u[0], ub=(leadsBK&&leadsBK[u.k])||{};
    h+=`<div class="sub" style="margin:2px 0 0;font-size:10px;color:var(--gold)">Untapped: ${ub.label||u.k} — big presence (${(u.n||0).toLocaleString()} measured), low segment score (est)</div>`;
  }
  h+=`<div class="sub" style="margin:2px 0 0;font-size:10px">counts MEASURED (Overture ≤10km, a sample / lower bound); fit ranking + ⚠ stress flag ESTIMATED (editorial fit map)</div>`;
  return h;
}
// ANSWER-FIRST §2 — macro-exposure chip strip from macro_exposure.json: the top-3 macro factors
// hitting THIS branch's customer mix, as compact chips [rice ▼] [leverage ▲] — headwind red /
// tailwind green, arrow = the measured signal's direction (price YoY sign; rainfall below normal ▼;
// household debt ▲). Scores are share-diluted (meta.score_scale) so ORDER carries the message —
// no 0–100 bars, no absolute readout. Tooltip carries the factor definition + provenance.
const MACX_ARROW={drought:'▼',leverage:'▲',mfg:'▼'};   // non-price factors: fixed signal direction
function macxPopupHTML(d,sec){
  const e=macxRec(d); if(!e||!e.t3||!e.t3.length) return '';
  const esc=s=>String(s||'').replace(/"/g,'&quot;');
  const chips=e.t3.map(t=>{
    const k=t[0], s=t[1], head=t[2]!=='t';
    const f=macxFactor(k)||{}, sig=f.signal||{};
    const col=head?'var(--agri)':'var(--merch)';
    const arrow=(typeof sig.yoy_pct==='number')?(sig.yoy_pct>0?'▲':'▼'):(MACX_ARROW[k]||(head?'▼':'▲'));
    const tip=esc(`${f.label||k} — ${head?'HEADWIND':'TAILWIND'} for this branch's customer mix. `
      +(typeof sig.yoy_pct==='number'?`YoY ${sig.yoy_pct>0?'+':''}${sig.yoy_pct}% (${sig.vintage||'—'}). `:'')
      +(sig.provenance||'')+` Relative exposure rank ${s} (share-diluted, est — compare order, not magnitude).`);
    return `<span class="mxchip" style="color:${col}" title="${tip}">${k} ${arrow}</span>`;
  }).join('');
  const dom=macxFactor(e.d);
  return sec('Macro exposure — what hits these customers (est)')
    + `<div class="mxstrip">${chips}</div>`
    + (e.d?`<div class="sub" style="margin:3px 0 0;font-size:10px">Customers most exposed to: <b style="color:var(--hi)">${dom?dom.label:e.d}</b> (est)</div>`:'')
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">occupation mix MEASURED × sensitivity weights ESTIMATED × macro signals MEASURED — a relative ranking (chip order), not a measured default rate</div>`;
}
// ANSWER-FIRST §2b — "What moves this branch": ONE line naming the branch's top-2 macro drivers
// with real numbers (macro_sensitivity.json) — e.g. "Rubber price ▲ +32.4% YoY × 93% of province
// crop area · Gold price ▲ +26.1% YoY × 2 gold shops ≤10km". Prices are MEASURED (Pink Sheet
// GLOBAL proxy); crop shares / gold-shop counts / rain are MEASURED; the ranking itself is an
// ESTIMATED proxy (segment scores scale relevance) — the chip says so. Empty when absent.
function msensPopupHTML(d,sec){
  const t2=msensRec(d); if(!t2) return '';
  const line=t2.map(msensPhrase).filter(Boolean).join(' <span style="color:var(--dim)">·</span> ');
  if(!line) return '';
  return sec('What moves this branch — top macro drivers')
    + `<div style="font-size:11.5px;line-height:1.5">${line}</div>`
    + `<div class="sub" style="margin:2px 0 0;font-size:10px">ESTIMATED proxy over measured inputs — global price YoY (not Thai farm-gate) × measured crop share / gold shops / rain, scaled by estimated segment scores. Rank, not elasticity.</div>`;
}
// "vs statistical twins" popup section — empty string when the peer layer is absent (no fabrication).
function peerPopupHTML(d,sec,r){
  const e=peerRec(d); if(!e) return '';
  const above=(e.dev||0)>0;
  const col=above?'var(--agri)':'var(--merch)';
  const sig=(e.rz!=null&&e.rz>=2)?' · ≥2σ — audit first':'';
  return sec('Vs statistical twins — ESTIMATED benchmark')
    + r('Twin-median risk (15 twins)', e.pm==null?'n/a':e.pm, '#8b90a7')
    + r('This branch vs twins', (above?'+':'')+(e.dev==null?'n/a':e.dev)+' pts'+sig, col);
}
/* ---------- per-branch ACTION recommendations (data/branch_recommendations.json) ----------
   The "what to do here" read — ranked recs (acquire/defend/agri/collateral/base/macro) shown at the
   TOP of the branch panel. Lazy-loaded + null-guarded. */
let RECDATA=null, recDone=false, recPromise=null;
async function loadRecommendations(){
  if(recPromise) return recPromise;
  recPromise=fetch('data/branch_recommendations.json').then(rp=>rp.ok?rp.json():null)
    .then(d=>{RECDATA=d;recDone=true;return d;}).catch(()=>{recDone=true;return null;});
  return recPromise;
}
const REC_TONE={good:'#1C8C7D',warn:'#C8433B',info:'#5B7CFA'};
function recsPopupHTML(d){
  if(!RECDATA||!RECDATA.branches||!DATA) return '';
  const i=idxOf(d); if(i<0) return '';
  const e=RECDATA.branches[i]; if(!e||!e.recs||!e.recs.length) return '';
  return `<div style="margin:8px 0 2px">`
    + `<div style="font:700 11px 'IBM Plex Sans Thai';color:#8b90a7;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Recommendations</div>`
    + e.recs.map(rc=>{
        const c=REC_TONE[rc.tone]||'#8b90a7';
        // evidence chips: the exact source · value that triggered this rec (auditable, no model in the loop)
        const ev=(rc.w||[]).map(wv=>{
          const meas=wv.m==='measured';
          const mc=meas?'#1C8C7D':'#8b7a3a';
          const tag=meas?'measured':'est';
          return `<span style="display:inline-flex;gap:4px;align-items:baseline;padding:2px 6px;margin:2px 3px 0 0;border-radius:5px;background:rgba(255,255,255,.04);border:1px solid ${mc}55;font:500 10px 'IBM Plex Mono'">`
            +`<span style="color:#8b90a7">${wv.s}</span>`
            +`<b style="color:${c}">${wv.v}</b>`
            +`<span style="color:${mc};font-size:8px;text-transform:uppercase;letter-spacing:.3px">${tag}</span></span>`;
        }).join('');
        return `<div style="padding:6px 8px;margin-bottom:5px;border-left:3px solid ${c};background:rgba(255,255,255,.03);border-radius:0 6px 6px 0">`
          +`<div style="display:flex;gap:7px;align-items:flex-start">`
          +`<span style="font-size:14px;line-height:1.2">${rc.i||'•'}</span>`
          +`<span style="flex:1;font:500 12px 'IBM Plex Sans Thai';color:#c7cedd;line-height:1.35">${rc.t}</span></div>`
          +(ev?`<div style="margin-top:5px;padding-left:21px">${ev}</div>`:'')
          +`</div>`;
      }).join('')
    + `<div class="sub" style="font-size:10px;color:#5B6479">Deterministic synthesis of the branch's own signals — each chip is the source layer · value that triggered the rec (no model in the loop). A triage prompt, not a credit decision.</div>`
    + `</div>`;
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
    ${(()=>{const slug=pl&&pl.slug; const bh=bldgCenterHref(slug,d.y,d.x);
      const btn='display:block;text-align:center;padding:7px;border-radius:7px;text-decoration:none;font:700 12px \'IBM Plex Sans Thai\'';
      const bldg=bh?`<a href="${bh}" style="${btn};background:var(--accent);color:#fff">🏙 3D buildings</a>`:'';
      const expl=`<a href="branch-explorer.html?lat=${d.y}&lng=${d.x}&n=${encodeURIComponent(d.n)}${themeQS()}" style="${btn};background:var(--accent);color:#fff">🔎 10 km explorer</a>`;
      return `<div style="display:grid;grid-template-columns:${bh?'1fr 1fr':'1fr'};gap:6px;margin:8px 0 2px">${bldg}${expl}</div>`;})()}
    ${recsPopupHTML(d)}
    ${briefPopupHTML(d,sec,r)}
    ${occLeadsPopupHTML(d,sec,r)}
    ${leadsPopupHTML(d,sec,r)}
    ${msensPopupHTML(d,sec)}
    ${macxPopupHTML(d,sec)}
    ${sec('Portfolio risk — ESTIMATED proxy (OSM/price, 0–100)')}
    ${r('Agri-PD ● (est)', d.a==null?'n/a':d.a, 'var(--agri)')}
    ${r('Merchant ◆ (est)', d.m==null?'n/a':d.m, 'var(--merch)')}
    ${r('Collateral ▲ (est)', d.c==null?'n/a':d.c, 'var(--collat)')}
    ${sec('Market — measured')}
    ${r('District factories (DIW)', naNum(d.dfac), 'var(--gold)')}
    ${r('District factory workers (DIW)', naNum(d.dwork), 'var(--gold)')}
    ${pl?r('Province pickups (DLT)', naNum(pl.pickup), 'var(--collat)'):''}
    ${pl?r('Province informal workers (NSO)', nsoNum(pl.informal), 'var(--collat)'):''}
    ${collatMixPopupHTML(d,sec,r)}
    ${hhriskPopupHTML(d,sec,r)}
    ${workforcePopupHTML(d,sec)}
    ${agriPopupHTML(d,sec,r)}
    ${croplandPopupHTML(d,sec,r)}
    ${vehiclePopupHTML(d,sec,r)}
    ${laborPopupHTML(d,sec,r)}
    ${occPopupHTML(d,sec)}
    ${occriskPopupHTML(d,sec,r)}
    ${peerPopupHTML(d,sec,r)}
    ${poiRelevancePopupHTML(d,sec,r)}
    ${amphoePopupHTML(d,sec,r)}
    ${catchmentPopupHTML(d,sec,r)}
    ${compPopupHTML(d,sec,r)}
    ${rivalPressureLineHTML(d)}
    ${picoLineHTML(d)}
    ${wc?r('Region weakest crop (YoY) · est', wc.lab+' '+(wc.yoy>0?'+':'')+wc.yoy+'%', wc.yoy<0?'var(--agri)':'var(--merch)'):''}
    ${cstressPopupHTML(d,sec,r)}
    ${sec('Within 10 km (OSM · measured)')}
    ${radar.map(rrow).join('')}
    ${bldgDensityPopupHTML(d,r)}
    ${fuelPopupHTML(d,r)}</div>`;
}
function styleMarkers(){
  const l=LENS[curLens], mx=lensMax(l);
  // polygon-resolution lenses (district amp:true — dws/drisk/unemp — and province prov:true —
  // hhdti/pstress) paint a choropleth fill under the dots; the default 0.9 dot opacity fully tiles
  // over it (district polygons are smaller than province ones, so the tiling is worse there), so
  // thin the dots whenever either fill is live.
  const polyDots=isProvLens(curLens)||isAmpLens(curLens);
  if(l.cat){
    // categorical (dominant-crop) lens: colour each branch dot by its district's dominant crop so
    // the dots agree with the choropleth beneath them (grey for districts with no tracked crop).
    markers.forEach(m=>{
      const a=m._d&&m._d._amp; const e=a?cropRecForAmp(a):null; const dc=e&&e.dominant_crop;
      m.setStyle({fillColor:dc?(CROP_COLORS[dc]||'#8a94a8'):'#6b7488', radius:4.5, fillOpacity:0.85});
    });
    drawAmphoeChoropleth();
    drawProvinceChoropleth();
    return;
  }
  markers.forEach(m=>{
    const v=l.val(m._d), t=v/mx;
    m.setStyle({fillColor:lensColor(Math.sqrt(t),l.color), radius:3+Math.min(1,t)*7, fillOpacity:polyDots?0.6:0.9});
  });
  // paint (or clear) the district choropleth to match the active lens — null-safe no-op
  // on a branch lens or when the polygon file is absent.
  drawAmphoeChoropleth();
  drawProvinceChoropleth();
}
function setLens(k){
  curLens=k;
  // re-render the pill row so a menu lens that becomes active surfaces as the visible 5th pill (and
  // the "More lenses" button reflects the active state). Keeps the 4 hero slots fixed.
  renderLenses();
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
  if(k==='pstress' && !pstressLoaded){
    loadProvinceStress().then(()=>{ renderLenses(); if(curLens==='pstress'){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if(k==='dsrch' && !sdemandLoaded){
    loadSearchDemand().then(()=>{ renderLenses(); if(curLens==='dsrch'){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if(k==='occrisk' && !occriskLoaded){
    loadOccRisk().then(()=>{ renderLenses(); if(curLens==='occrisk'){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if(k==='brisk' && !briskLoaded){
    loadBranchRisk().then(()=>{ renderLenses(); if(curLens==='brisk'){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if(k==='peerdev' && !peersLoaded){
    loadBranchPeers().then(()=>{ renderLenses(); if(curLens==='peerdev'){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if(k==='macx' && !macxDone){
    loadMacroExposure().then(()=>{ renderLenses(); if(curLens==='macx'){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if(k==='poirel' && !poirelLoaded){
    loadPoiRelevance().then(()=>{ renderLenses(); if(curLens==='poirel'){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if(isAmpLens(k) && !ampJoinAttached){
    loadAmphoe().then(()=>{ if(isAmpLens(curLens)){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if(isAmpLens(k) && !ageoLoaded){
    loadAmphoeGeo().then(()=>{ if(isAmpLens(curLens)&&mapReady) drawAmphoeChoropleth(); });
  }
  if(LENS[k]&&LENS[k].cat && !cropLuLoaded){
    loadCropLanduse().then(()=>{ renderLenses(); if(curLens===k){ renderLegend(); if(mapReady) styleMarkers(); } });
  }
  if(isProvLens(k) && !pgeoLoaded){
    loadProvinceGeo().then(()=>{ if(isProvLens(curLens)&&mapReady) drawProvinceChoropleth(); });
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
/* LANE 3D-7 — road every branch reference INTO the 3D scenes. One icon set, one order
   everywhere: 🏙 3D (Overture building scene, centred on the branch when lat/lng are known)
   then 🔎 explorer (per-branch deck.gl scene). We only EMIT links here — the catchment side
   reads the city/lat/lng/z params (lane 3D-4). Pure frontend, no new data. */
function bldgCenterHref(slug,lat,lng){
  if(!slug) return null;
  let u='rayong-catchment.html?city='+slug;
  if(lat!=null&&lng!=null) u+='&lat='+lat+'&lng='+lng+'&z=15';
  return u+themeQS();
}
// slug for a branch's province via the shared PLOOK (measured province index); null-safe.
function branchSlug(d){const pl=(typeof PLOOK!=='undefined'&&PLOOK)?PLOOK[d&&d.v]:null; return (pl&&pl.slug)||null;}
// compact "🏙 3D · 🔎 explorer" row for a full branch record (needs d.y=lat, d.x=lng, d.v→slug).
// stop=true adds stopPropagation so it doesn't also fire a parent row's onclick navigation.
function branch3DLinks(d,stop){
  if(!d) return '';
  const s=stop?' onclick="event.stopPropagation()"':'';
  const parts=[];
  const b=bldgCenterHref(branchSlug(d),d.y,d.x);
  if(b) parts.push(`<a href="${b}"${s} title="3D building scene — centred on this branch" style="text-decoration:none;color:var(--accent)">🏙 3D</a>`);
  parts.push(`<a href="${branchHref(d)}"${s} title="Per-branch 3D explorer — what's within 10 km" style="text-decoration:none;margin-left:8px;color:var(--mid,#8A94A8)">🔎 explorer</a>`);
  return parts.join('');
}
function renderBranches(){
  const q=($('#search').value||'').trim().toLowerCase();
  let rows=DATA.filter(d=>!q || d.n.toLowerCase().includes(q) || d.v.toLowerCase().includes(q)
    || ((PLOOK[d.v]&&PLOOK[d.v].en)?PLOOK[d.v].en.toLowerCase().includes(q):false));  // also match English province name (was Thai-only: 'rayong' returned 0)
  rows.sort((a,b)=> branchSort==='w' ? a.w-b.w : branchSortVal(b,branchSort)-branchSortVal(a,branchSort));
  const total=rows.length, CAP=150;   // silent-cap guard: the table renders only the top CAP; surface the count so the ~1,865 unshown branches aren't hidden without a cue
  rows=rows.slice(0,CAP);
  $('#branches').innerHTML = `<tr><th class="no-print" scope="col"></th><th class="h-agri" scope="col" title="ESTIMATED proxy (OSM/price-based, 0–100), not a measured default rate">Portfolio risk ▲ est</th><th scope="col">Branch</th><th scope="col">Prov</th><th class="h-opp" scope="col" title="DIW registered factory workers in the branch district — measured">Factory workers (DIW)</th><th scope="col">Pickups (prov)</th><th scope="col">Informal (prov)</th><th scope="col">AutoX</th><th class="no-print" scope="col">3D</th></tr>`+
    (rows.length ? rows.map(d=>{const pl=PLOOK[d.v]||{}; const rk=riskVal(d); const rc=rk>=60?'var(--agri)':rk>=40?'var(--gold)':'var(--merch)';
      const id=`branch:${d.n}|${d.v}`;
      const wItem={id,label:d.n,sub:`${d.v} · ${d.r}`,val:`▲ ${rk}`,valSub:'risk · est',col:rc,prov:d.v};
      return `<tr onclick="location.href='${branchHref(d)}'" tabindex="0" role="link" style="cursor:pointer">
      <td class="no-print">${starBtn(id,wItem)}</td>
      <td class="mono"><a href="${branchHref(d)}" style="color:${rc};text-decoration:none" title="ESTIMATED risk proxy ${riskMetric==='composite'?'(worst of agri/merchant/collateral)':''}">▲ ${rk}</a></td>
      <td>${d.n}</td><td class="sub">${d.v}</td>
      <td class="mono" style="color:var(--gold)">${naNum(d.dwork)}</td>
      <td class="mono" style="color:var(--collat)">${naNum(pl.pickup)}</td>
      <td class="mono" style="color:var(--collat)">${nsoNum(pl.informal)}</td>
      <td class="mono sub">${d.w}</td>
      <td class="no-print" style="white-space:nowrap">${branch3DLinks(d,true)}</td></tr>`;}).join('')
      +(total>CAP?`<tr class="no-print"><td colspan="9" class="cc-empty" style="padding:10px 7px">Showing the top ${CAP} of ${total.toLocaleString()} ${q?'matching ':''}branches — refine the search or change the sort to reach the rest.</td></tr>`:'')
     : `<tr><td colspan="9" class="cc-empty" style="padding:14px 7px">No branches match “${dqEsc(q)}”. Clear the search to see all 2,015.</td></tr>`);
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
    $('#provchips').setAttribute('role','group'); $('#provchips').setAttribute('aria-label','Filter by region');
    $('#provchips').innerHTML=regions.map((r,i)=>`<button class="chip ${i===0?'on':''}" data-r="${r}" aria-pressed="${i===0}">${r==='all'?'All':r}</button>`).join('');
    $('#provchips').onclick=e=>{const b=e.target.closest('.chip'); if(!b)return;
      document.querySelectorAll('#provchips .chip').forEach(c=>{const on=c===b;c.classList.toggle('on',on);c.setAttribute('aria-pressed',String(on));});
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
  $('#provtbl').innerHTML=`<tr><th class="no-print" scope="col"></th><th scope="col">Province</th><th scope="col">Region</th><th scope="col">Br</th><th scope="col">Distr</th><th scope="col">Factories</th><th scope="col">Vehicles</th><th scope="col">Fac/br</th><th class="no-print" scope="col">View</th></tr>`+
   (rows.length ? rows.map(p=>{const id=`prov:${p.th}`;
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
       <a href="${bldgURL(p.slug)}" onclick="event.stopPropagation()" title="3D building scene" style="text-decoration:none;color:var(--accent)">🏙 3D</a>
       <a href="${distURL(p.slug)}" onclick="event.stopPropagation()" title="Extruded district view" style="text-decoration:none;margin-left:8px;color:var(--mid,#8A94A8)">▦ district</a>
     </td></tr>`;}).join('')
    : `<tr><td colspan="9" class="cc-empty" style="padding:14px 7px">No provinces match “${dqEsc(q)}”${provRegion==='all'?'':` in ${dqEsc(provRegion)}`}. Clear the search to see all 77.</td></tr>`);
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
      $('#mktchips').setAttribute('role','group'); $('#mktchips').setAttribute('aria-label','Filter by region');
      $('#mktchips').innerHTML=regions.map((r,i)=>`<button class="chip ${i===0?'on':''}" data-r="${r}" aria-pressed="${i===0}">${r==='all'?'All':r}</button>`).join('');
      $('#mktchips').onclick=e=>{const b=e.target.closest('.chip'); if(!b)return;
        document.querySelectorAll('#mktchips .chip').forEach(c=>{const on=c===b;c.classList.toggle('on',on);c.setAttribute('aria-pressed',String(on));});
        mktRegion=b.dataset.r; drawMarket();};
      $('#mktsearch').oninput=drawMarket; $('#mktchips').dataset.init='1';
      $('#mktnote').textContent='Registered factory workers DIW · informal workforce NSO 2024 (some provinces n/a) · vehicles/pickups DLT · weakest crop = World Bank global price direction proxy (not Thai farm-gate), region-attributed.';
    }
    drawMarket();
    loadTapeReal().then(renderMarketCollateral);   // acquisition lens — collateral concentration
   }).catch(()=>{ $('#mkttbl').innerHTML='<tr><td>Could not load market data.</td></tr>'; });
}
// ACQUISITION LENS — collateral concentration from the real loan tape (TAPE.collateral): where &
// what collateral the book concentrates on. Null-safe: the whole block hides when the tape is absent.
function renderMarketCollateral(){
  const host=$('#mkt-coll'); if(!host) return;
  if(!TAPE||!TAPE.collateral){ host.style.display='none'; return; }
  host.style.display='';
  const C=TAPE.collateral, N=n=>Number(n).toLocaleString(), bnf=n=>'฿'+(n/1e9).toFixed(1)+'bn';
  const kk=n=>Math.round(n/1000)+'k';
  const sev=v=>v==null?'var(--dim)':v<8?'var(--merch)':v<14?'#9CB24E':v<20?'var(--opp)':v<26?'#D97A3A':'var(--agri)';
  const ec=$('#mkt-coll-econ');
  if(ec&&Array.isArray(C.economics_by_type)){
    ec.innerHTML=`<tr><th>Type</th><th>Accounts</th><th>OS</th><th>Yield</th><th title="yield − opex 8% − CoF 2.5%, before credit loss">Spread</th><th>90+</th></tr>`+
      C.economics_by_type.map(r=>`<tr><td><b>${r.type}</b></td><td class="mono sub">${N(r.n)}</td>
        <td class="mono sub">${bnf(r.os_sum)}</td><td class="mono">${r.yield_pct}%</td>
        <td class="mono" style="color:${r.gross_spread_pct<6?'var(--opp)':'var(--merch)'}"><b>${r.gross_spread_pct}%</b></td>
        <td class="mono" style="color:${sev(r.dpd90p_pct)}">${r.dpd90p_pct}%</td></tr>`).join('');
  }
  const br=$('#mkt-coll-branch');
  if(br&&Array.isArray(C.branch_brand_concentration)){
    br.innerHTML=`<tr><th>Branch</th><th>Brand</th><th>Accounts</th><th>90+</th></tr>`+
      C.branch_brand_concentration.slice(0,15).map(r=>`<tr><td>${(r.branch||'').replace('เงินไชโย','').replace('สาขา','')}</td>
        <td class="sub">${r.brand}</td><td class="mono sub">${N(r.n)}</td>
        <td class="mono" style="color:${sev(r.dpd90p_pct)}">${r.dpd90p_pct}%</td></tr>`).join('');
  }
  const rg=$('#mkt-coll-region');
  if(rg&&Array.isArray(C.type_x_region)){
    rg.innerHTML=`<tr><th>Type</th><th>Region</th><th>Accounts</th><th>OS</th><th>90+</th></tr>`+
      C.type_x_region.slice(0,15).map(r=>`<tr><td><b>${r.type}</b></td><td class="sub">${r.region}</td>
        <td class="mono sub">${N(r.n)}</td><td class="mono sub">${bnf(r.os_sum)}</td>
        <td class="mono" style="color:${sev(r.dpd90p_pct)}">${r.dpd90p_pct}%</td></tr>`).join('');
  }
  const ag=$('#mkt-coll-age');
  if(ag&&C.by_age){
    const AGL={'1.<=5 yr.':'≤5 yr','2.(5-10]yr.':'5–10 yr','3.(10-12]yr.':'10–12 yr','4.(12-15]yr.':'12–15 yr','5.(15-18]yr.':'15–18 yr','6.(18-20]yr.':'18–20 yr','7.(20-25]yr.':'20–25 yr','8.>25 yr.':'>25 yr'};
    const rows=Object.entries(C.by_age).sort((a,b)=>a[0].localeCompare(b[0]));
    ag.innerHTML=`<tr><th>Age at origination</th><th>Accounts</th><th>90+</th><th>Avg eval</th></tr>`+
      rows.map(([k,v])=>`<tr><td>${AGL[k]||k}</td><td class="mono sub">${N(v.n)}</td>
        <td class="mono" style="color:${sev(v.dpd90p_pct)}">${v.dpd90p_pct}%</td>
        <td class="mono sub">${v.eval_avg?kk(v.eval_avg):'—'}</td></tr>`).join('');
  }
  wrapTables();   // wrap the dynamically-built tables so wide ones scroll on narrow columns
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
  $('#mkttbl').innerHTML=`<tr><th scope="col">Province</th><th scope="col">Region</th><th class="h-opp" scope="col" title="DIW registered factory workers — distinct from NSO informal/formal labour">Registered factory workers (DIW)</th><th scope="col" title="NSO informal workforce — borrower base proxy">Informal workforce (NSO)</th><th scope="col">Pickups</th><th scope="col">Pickup %</th><th scope="col" title="World Bank global price direction proxy, region-attributed — not Thai farm-gate">Weakest crop (YoY) · est</th></tr>`+
   rows.map(p=>{const wc=regionWorstCrop(p.region);
     return `<tr onclick="location.href='${bldgURL(p.slug)}'" tabindex="0" role="link" style="cursor:pointer">
     <td><a href="${bldgURL(p.slug)}" style="color:inherit;text-decoration:none"><b>${p.th}</b> <span class="sub">${p.en||''}</span></a> <a href="${distURL(p.slug)}" onclick="event.stopPropagation()" title="Extruded district view" class="sub" style="text-decoration:none;margin-left:6px;color:var(--mid,#8A94A8)">▦</a></td>
     <td class="sub">${p.region}</td>
     <td class="mono">${naNum(p.workers)}</td>
     <td class="mono" style="color:var(--collat)">${naNum(p.informal)}</td>
     <td class="mono">${naNum(p.pickup)}</td>
     <td class="mono sub">${pct(p)}%</td>
     <td class="mono" style="color:${wc&&wc.yoy<0?'var(--agri)':'var(--mid)'}">${wc?wc.lab+' '+(wc.yoy>0?'+':'')+wc.yoy+'%':'—'}</td></tr>`;}).join('')
    || `<tr><td colspan="7" class="cc-empty" style="padding:14px 7px">No provinces match “${dqEsc(q)}”${mktRegion==='all'?'':` in ${dqEsc(mktRegion)}`}. Clear the search to see all 77.</td></tr>`;
  $('#mktcsv').onclick=()=>{
    const hdr=['province','province_en','region','branches','registered_factory_workers_diw','informal_workforce_nso','pickups_dlt','pickup_share_pct','vehicles_total','weakest_crop_est','weakest_crop_yoy_est'];
    const lines=[hdr.join(',')].concat(rows.map(p=>{const wc=regionWorstCrop(p.region);
      return [p.th,p.en,p.region,p.branches,p.workers,p.informal,p.pickup,pct(p),p.vehicles,wc?wc.lab:'',wc?wc.yoy:'']
        .map(v=>`"${String(v==null?'':v).replace(/"/g,'""')}"`).join(',');}));
    const blob=new Blob(['\ufeff',lines.join('\n')],{type:'text/csv;charset=utf-8;'});
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
// Standardized provenance chip (one consistent marker everywhere): filled dot = MEASURED,
// hollow dot = ESTIMATED. ≥11px, AA-contrast text on a tinted pill (see .prov in styles.css).
// provChip(kind[,label]) is the helper; TAG_M / TAG_E are the canonical short chips used inline.
// provChip(kind[,label[,src]]) — the ONE provenance pill. `src` (e.g. 'OSM','NSO','Google Places')
// renders as a muted "· src" suffix inside the same pill; omitted when absent (every existing call).
function provChip(kind,label,src){
  const m=kind==='m';
  return `<span class="prov ${m?'m':'e'}" title="${m?'Measured value':'Estimated / proxy — not a measured outcome'}">`+
    `<span class="pd" aria-hidden="true"></span>${label||(m?'measured':'est')}`+
    (src?`<span class="src">· ${src}</span>`:'')+`</span>`;
}
const TAG_M=provChip('m');
const TAG_E=provChip('e');
// Reusable "Method & caveats" expander — keeps the honesty but moves long inline caveat prose into one
// consistent collapsed disclosure. items = array of HTML strings (rendered as a list); intro optional.
function methodBox(intro,items){
  const li=(items||[]).filter(Boolean).map(t=>`<li>${t}</li>`).join('');
  return `<details class="method"><summary>Method &amp; caveats</summary><div class="mb">`+
    (intro?`<p style="margin:6px 0 4px">${intro}</p>`:'')+(li?`<ul>${li}</ul>`:'')+`</div></details>`;
}
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

/* ---- EXEC DECISION QUEUE — "This week — do these first" (data/decision_queue.json) ----
   ~8 ranked weekly actions built by pipeline/build_decision_queue.py from committed layers
   ONLY (rival_pressure / branch_peers / macro_sensitivity / crop_stress / opportunity_score /
   exit_whitespace). Each row: number, type chip (defend/expand/tighten/audit), one plain
   sentence with the real numbers inline, measured/estimated tag + source file + detail-tab
   link. The RANKING is an editorial rule stated in the file's meta — surfaced in the footer.
   Null-safe: absent file → calm note, never fabricated rows. */
let DQUEUE=null,dqLoaded=false;
function loadDecisionQueue(){
  if(dqLoaded) return Promise.resolve(DQUEUE);
  return fetch('data/decision_queue.json').then(r=>r.ok?r.json():null)
    .then(j=>{DQUEUE=j;dqLoaded=true;return j;})
    .catch(()=>{DQUEUE=null;dqLoaded=true;return null;});
}
function dqEsc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
/* LANE 3D-7 — road each queue action INTO the 3D scene it references. defend/audit name a
   specific branch → centre the building scene on it (found by exact name in DATA); expand/tighten
   name a district/province → open that province's building scene. Null-safe: no slug/branch → ''. */
function queue3DLink(it){
  if(!it) return '';
  if((it.type==='defend'||it.type==='audit') && typeof DATA!=='undefined' && Array.isArray(DATA)){
    const b=DATA.find(d=>d&&d.n===it.name);
    if(b){ const h=bldgCenterHref(branchSlug(b),b.y,b.x);
      if(h) return ` <a href="${h}" title="3D building scene — centred on this branch" style="text-decoration:none">🏙 3D</a>`; }
  }
  const pl=(typeof PLOOK!=='undefined'&&PLOOK)?PLOOK[it.prov]:null;
  if(pl&&pl.slug) return ` <a href="rayong-catchment.html?city=${pl.slug}${themeQS()}" title="3D building scene — ${dqEsc(pl.th||it.prov)}" style="text-decoration:none;color:var(--accent)">🏙 3D</a>`;
  return '';
}
/* ---------- IMPACT CARDS — the Region → Province → Branch drill (owner sign-off 2026-07-25) ----
   data/impact_cards.json (build_impact_cards.py). Big picture first: 5 region cards, press a
   region for its provinces, press a province for its branches. Humanized numbers by design
   (months-of-income, 1-per-N vehicles, plain rival ratios — no analyst codes); the trend chips
   embed the vintage deltas (the Risk-trend TAB is retired from the nav, the DIMENSION lives
   here). Same strip fronts Assistance / Risk / Competition with a pillar-specific ranking.
   Null-safe: absent layer → calm note, never a broken scene. */
let IMPACT=null, impactPromise=null;
let INCIMP=null;   // income_impact.json — read by icCropIncome() on the drill's province crop strip
function loadImpact(){
  if(impactPromise) return impactPromise;
  impactPromise=fetch('data/impact_cards.json').then(r=>r.ok?r.json():null)
    .then(j=>{IMPACT=(j&&Array.isArray(j.regions))?j:null;}).catch(()=>{IMPACT=null;});
  return impactPromise;
}
const IC_MOUNTS={home:['cc-impact',null],assist:['assist-impact','assist'],
                 exposure:['exposure-impact','risk'],acq:['competition-impact','competition']};
const IC_SORT={assist:(a,b)=>(b.roll_pct||0)-(a.roll_pct||0),
               risk:(a,b)=>(b.npl_live_pct||0)-(a.npl_live_pct||0),
               competition:(a,b)=>((b.rivals||{}).ratio||0)-((a.rivals||{}).ratio||0)};
const IC_MODE_NOTE={assist:'ranked for this pillar: rolling-worse (30–89d) first',
                    risk:'ranked for this pillar: NPL-live first',
                    competition:'ranked for this pillar: most-outgunned first'};
const IC_FLAG={'assist-first':['ASSIST FIRST','var(--agri)'],
               'cleanest-book':['CLEANEST BOOK','var(--merch)'],
               'thinnest-foothold':['THINNEST FOOTHOLD','var(--accent)'],
               'watch-rivals':['WATCH RIVALS','var(--gold)'],
               'hold-course':['HOLD COURSE','var(--merch)']};
function icN(x){return x==null?'—':Number(x).toLocaleString('en-US');}
function icPct(x,warn,bad){ if(x==null) return '—';
  const c=x>=bad?'var(--agri)':x>=warn?'var(--gold)':'var(--merch)';
  return `<b style="color:${c}">${x.toFixed(2)}%</b>`;}
function icTrendChip(d){ if(d==null) return '';
  const w=(IMPACT.meta||{}).trend_window||{};
  const dn=d<0;
  return `<span class="ic-trend ${dn?'dn':'up'}" title="AGRI BACKDROP — modelled farm-household risk (crop prices + drought), change between committed vintages (${w.from||''} → ${w.to||''}). A forward farm-economy signal, SEPARATE from the loan book's measured delinquency shown by the ladder / NPL-live / book status. The two need not move together — the farm backdrop can ease while a branch's book still carries elevated NPL from earlier vintages. Tape-NPL deltas begin at the second monthly tape vintage.">agri backdrop ${dn?'▼ easing':'▲ rising'}</span>`;}
/* Book delinquency status — MEASURED tape NPL-live / 30–89 roll LEVEL (not the agri-backdrop trend).
   Same thresholds at region / province / branch so the book story stays consistent when you drill in,
   and it does NOT contradict the agri-backdrop chip (different axis: current book vs forward farm signal). */
function icBookCue(r,withLabel){
  const npl=r.npl_live_pct, roll=r.roll_pct;
  if(npl==null) return '<span class="s">—</span>';
  const hot=(npl>=7||(roll!=null&&roll>=12)), warm=(npl>=5||(roll!=null&&roll>=9));
  const [ic,lab,c]=hot?['🔴','NPL elevated','var(--agri)']:warm?['🟡','roll watch','var(--gold)']:['🟢','book clean','var(--merch)'];
  const t=`measured tape: NPL-live ${npl.toFixed(1)}% · 30–89 roll ${roll!=null?roll.toFixed(1):'—'}% (book delinquency level — not the agri backdrop)`;
  return `<span class="ic-bookcue" style="color:${c}" title="${t}">${ic}${withLabel===false?'':' '+lab}</span>`;
}
/* Bucket ladder — the whole-book delinquency ladder Current → X(pre-30) → 30–89 → 90–179 → 180+,
   summing to 100. npl_live_pct is LIVE-book-based (excludes 180+ from its denominator), so the
   90–179 whole-book segment is derived as dpd30p − roll − late180 for a bar that sums to 100. */
const IC_BUCKETS=[['current','Current','var(--merch)'],['x','X · pre-30','var(--gold)'],
                  ['roll','30–89','#D97A3A'],['npl','90–179','var(--agri)'],['late','180+','var(--collat)']];
function icSegs(r){
  if(!r||r.current_pct==null||r.dpd30p_pct==null) return null;
  const late=r.late180_pct||0, roll=r.roll_pct||0;
  const npl=Math.max(0,+(r.dpd30p_pct-roll-late).toFixed(2));
  return {current:r.current_pct, x:r.early_pct||0, roll:roll, npl:npl, late:late};
}
function icLadder(r){
  const s=icSegs(r); if(!s) return '<span class="s">—</span>';
  const bar=IC_BUCKETS.map(([k,lab,c])=>s[k]>0
    ?`<span class="ic-lad-seg" style="width:${s[k]}%;background:${c}" title="${lab} ${s[k]}%"></span>`:'').join('');
  return `<span class="ic-lad" title="Current ${s.current}% · X ${s.x}% · 30–89 ${s.roll}% · 90–179 ${s.npl}% · 180+ ${s.late}%">${bar}</span>`;
}
function icLadderLegend(){
  return `<div class="ic-lad-leg">${IC_BUCKETS.map(([k,lab,c])=>`<span><i style="background:${c}"></i>${lab}</span>`).join('')}</div>`;
}
/* debt burden as a % of ANNUAL household income (standard DTI framing) — debt_months is months of
   income (debt ÷ monthly income), so DTI% = debt_months ÷ 12 × 100. Owner ask: "% not months". */
function icDTI(debt_months){ return debt_months==null?'<span class="s">—</span>'
  :`<b>${Math.round(debt_months/12*100)}%</b>`; }
function icPctCell(x){ return x==null?'<span class="s">—</span>':x.toFixed(1)+'%'; }
/* Crop / commodity impact for a province (owner ask #3/#6/#7): the province's MEASURED crop mix, each
   crop tagged with its World Bank Pink Sheet YoY + direction (the same board the region chips use),
   plus rainfall-vs-normal as a drought proxy. icCropCell = compact (province table); icCropStrip =
   the full "farm backdrop for this province's book" strip shown at the branch drill level. */
function icCropDir(cls){ return cls==='stress'?'▼':cls==='up'?'▲':'→'; }
function icCropCol(cls){ return cls==='stress'?'var(--agri)':cls==='up'?'var(--merch)':'var(--dim)'; }
function icCropCell(p){
  const cr=(p&&p.crops)||[];
  if(!cr.length) return '<span class="s">—</span>';
  return cr.slice(0,2).map(c=>`<span style="color:${icCropCol(c.cls)}" title="${c.crop} ${Math.round((c.share||0)*100)}% of cropland · Pink Sheet YoY ${c.yoy!=null?(c.yoy>0?'+':'')+c.yoy+'%':'n/a'}">${c.crop.replace('Oil palm','Palm')} ${icCropDir(c.cls)}</span>`).join(' · ');
}
/* What the crop mix is WORTH to the households behind this province's book. The chips above carry the
   world price; this line carries the farmer's cash — the modelled effect of crop prices on farm income
   and the baht/month it works out to for the Agriculture group. Null-safe: no income layer, no line. */
function icCropIncome(prov){
  const ip=(INCIMP&&INCIMP.provinces)?INCIMP.provinces[prov]:null;
  if(!ip||ip.agri_price_shock_pct==null) return '';
  const a=(ip.occ||{}).Agriculture||{}, s=ip.agri_price_shock_pct;
  const col=s>=0?'var(--merch)':'var(--agri)';
  return `<span class="ic-cchip ${s>=0?'good':'bad'}" title="modelled effect of this province's crop-price mix on farm-household income (income_impact.json) — ESTIMATED transmission over MEASURED prices and MEASURED NSO income levels">`+
    `farm income <b style="color:${col}">${s>0?'+':''}${s}%</b>`+
    (a.d_baht!=null?` ≈ ${a.d_baht>0?'+':''}฿${icN(a.d_baht)}/mo`:'')+`</span>`;
}
function icCropStrip(p,prov){
  const cr=(p&&p.crops)||[];
  if(!cr.length) return '';
  const chips=cr.map(c=>{
    const cl=c.cls==='stress'?'bad':c.cls==='up'?'good':'flat';
    const y=c.yoy!=null?`${c.yoy>0?'+':''}${c.yoy}%`:'n/a';
    return `<span class="ic-cchip ${cl}" title="${c.crop}: ${Math.round((c.share||0)*100)}% of this province's measured cropland · World Bank Pink Sheet YoY ${y}">${c.crop} ${Math.round((c.share||0)*100)}% ${icCropDir(c.cls)} ${y}</span>`;
  }).join('');
  const rain=p.rain_pct!=null?`<span class="ic-cchip ${p.rain_pct<85?'bad':'flat'}" title="rainfall as % of the local normal — drought proxy (crop-stress layer)">rain ${p.rain_pct}% of normal</span>`:'';
  return `<div class="ic-cropstrip"><span class="ic-bt" style="margin:0">CROPS & COMMODITIES <span class="s">${cr.length} measured crop${cr.length>1?'s':''} · farm backdrop for this province's book · Pink Sheet YoY</span></span>${chips}${rain}${icCropIncome(prov)}</div>`;
}
// Branch rows must RECONCILE to the province above them. They were silently short until
// 2026-07-31 (a top-400-by-size cap upstream, on top of the n>=30 no-PII floor, dropped ~1,570
// branches that cleared the floor). The cap is gone; this footer now states the coverage outright
// so any future shortfall is visible in the UI instead of being discovered by eye.
function icBranchCoverage(prov, rows){
  const p=(IMPACT.provinces||{})[prov]||{};
  const shown=rows.reduce((a,b)=>a+(b.n||0),0), tot=p.accounts||0;
  const nb=p.branches!=null?p.branches:null;
  if(!tot) return '';
  const pct=100*shown/tot, miss=tot-shown;
  const full=miss<=0;
  return `<div class="ic-note">Showing <b>${icN(rows.length)}</b>${nb!=null?' of '+icN(nb):''} branches — `+
    `<b>${icN(shown)}</b> of the province's <b>${icN(tot)}</b> accounts (<b>${pct.toFixed(1)}%</b>).`+
    (full?' These rows reconcile to the province total.'
         :` The remaining ${icN(miss)} sit in branches under the 30-account no-PII floor and are not published.`)+
    ` Branch detail → <a href="data.html">data book</a>.</div>`;
}
function icBranchRows(prov){
  const rows=(IMPACT.branches||{})[prov]||[];
  if(!rows.length) return `<div class="ic-note">No branch rows for this province — every branch here sits under the 30-account no-PII floor, so none can be published. Branch detail → <a href="data.html">data book</a>.</div>`;
  return `<div class="ic-scroll"><table class="ic-tbl ic-drilltbl"><thead><tr><th>Branch (tape)</th><th>Accounts</th><th>Book ฿m</th><th class="ic-ladcol">Bucket ladder — Current→180+</th><th>Current</th><th>X · pre-30</th><th>NPL-live</th><th title="measured book delinquency level — not the agri backdrop">Book status</th></tr></thead><tbody>`+
    rows.map(b=>{
      return `<tr><td>${b.name}</td><td class="n">${icN(b.n)}</td><td class="n">${icN(b.os_m)}</td>
        <td>${icLadder(b)}</td>
        <td class="n">${icPctCell(b.current_pct)}</td>
        <td class="n">${icPctCell(b.early_pct)}</td>
        <td class="n">${icPct(b.npl_live_pct,5,7)}</td>
        <td>${icBookCue(b)}</td></tr>`;
    }).join('')+`</tbody></table></div>`+icBranchCoverage(prov,rows)+icLadderLegend();
}
function icProvTable(g){
  const provs=(g.provinces||[]).map(p=>[p,(IMPACT.provinces||{})[p]]).filter(x=>x[1]);
  return `<div class="ic-scroll"><table class="ic-tbl ic-drilltbl"><thead><tr><th>Province</th><th>Book</th><th class="ic-ladcol">Bucket ladder — Current→180+</th><th>Current</th><th>X · pre-30</th><th title="90–179d, live-book denominator">NPL-live</th><th title="measured book delinquency level — not the agri backdrop">Book</th><th title="debt vs annual household income">DTI</th><th title="dominant measured crops + Pink Sheet price direction (▲ up · ▼ stress · → flat)">Crops</th><th>Rivals</th><th title="AGRI BACKDROP — modelled farm-household risk (crop prices + drought) trend; a forward farm signal, separate from the book delinquency">Agri backdrop</th></tr></thead><tbody>`+
    provs.map(([name,p])=>{
      const d=(p.d_agri!=null)?p.d_agri:(g.trend||{}).d_agri;
      const tr=d==null?'—':`<span style="color:${d<0?'var(--merch)':'var(--agri)'}">${d<0?'▼ easing':'▲ rising'}</span>`;
      const rv=p.rivals?`${(p.rivals.ratio!=null?p.rivals.ratio.toFixed(1):'—')}×`:'—';
      const rvt=p.rivals&&p.rivals.lead?` title="${p.rivals.lead} leads locally"`:'';
      return `<tr class="ic-prow" data-p="${dqEsc(name)}" tabindex="0" role="link" title="press for this province's branches">
        <td><span class="ic-chev">▸</span> ${name}</td>
        <td class="n">฿${icN(p.os_m)}m · ${icN(p.accounts)} acc</td>
        <td>${icLadder(p)}</td>
        <td class="n">${icPctCell(p.current_pct)}</td>
        <td class="n">${icPctCell(p.early_pct)}</td>
        <td class="n">${icPct(p.npl_live_pct,5,7)}</td>
        <td>${icBookCue(p,false)}</td>
        <td class="n" title="debt vs annual household income">${icDTI(p.debt_months)}</td>
        <td class="ic-cropcell">${icCropCell(p)}</td>
        <td class="n"${rvt}>${rv}</td>
        <td class="n">${tr}</td></tr>`;
    }).join('')+`</tbody></table></div>`+icLadderLegend();
}
function icCard(g){
  const [flab,fcol]=IC_FLAG[g.flag]||['',''];
  const p=g.people||{}, v=g.vehicles||{}, o=g.occupations||{}, rv=g.rivals||{};
  const occ=(o.book||[]).slice(0,3).map(b=>
    `<div class="ic-rw"><span>${b.occ} <span class="s">${b.pct}% of book</span></span><b>${b.npl_live_pct!=null?b.npl_live_pct.toFixed(1)+'% NPL':''}</b></div>`).join('');
  const commods=(g.commodities||[]).map(c=>{
    const cl=c.cls==='stress'?'bad':c.cls==='up'?'good':'flat';
    const ar=c.cls==='stress'?'▼':c.cls==='up'?'▲':'→';
    return `<span class="ic-cchip ${cl}" title="${c.note||''} — World Bank Pink Sheet YoY">${c.lab} ${ar} ${c.yoy>0?'+':''}${c.yoy}%</span>`;
  }).join('');
  return `<div class="ic-card" data-r="${g.key}">
    <span class="ic-sev" style="background:${fcol}"></span>
    <div class="ic-head">
      <h3>${g.key} <span lang="th" class="s">· ${g.name_th}</span></h3>
      <span class="ic-meta">${icN(g.branches)} branches · ${icN(g.accounts)} accounts</span>
      ${icTrendChip((g.trend||{}).d_agri)}
      ${flab?`<span class="ic-flag" style="color:${fcol};border-color:${fcol}">${flab}</span>`:''}
    </div>
    <div class="ic-blocks">
      <div class="ic-blk"><div class="ic-bt">LOAN BOOK <span class="m">MEASURED · TAPE</span></div>
        <div class="ic-rw"><span>Outstanding</span><b>฿${g.os_bn}bn</b></div>
        <div class="ic-rw"><span>Current (0 dpd)</span><b style="color:var(--merch)">${g.current_pct!=null?g.current_pct.toFixed(1)+'%':'—'}</b></div>
        <div class="ic-rw"><span>X · pre-30 <span class="s">watch</span></span><b style="color:var(--gold)">${g.early_pct!=null?g.early_pct.toFixed(1)+'%':'—'}</b></div>
        <div class="ic-rw"><span>NPL-live (90–179d)</span>${icPct(g.npl_live_pct,4.7,5.3)}</div>
        <div class="ic-rw"><span>Book status</span>${icBookCue(g)}</div>
        <div class="ic-lad-wrap">${icLadder(g)}</div></div>
      <div class="ic-blk"><div class="ic-bt">THE PEOPLE <span class="m">NSO · SES/LFS</span></div>
        <div class="ic-rw"><span>Avg individual income <span class="s">est. split</span></span><b>${p.income_ind!=null?'฿'+icN(p.income_ind)+'/mo':'—'}</b></div>
        <div class="ic-rw"><span>Debt-to-income <span class="s">vs annual</span></span>${icDTI(p.debt_months)}</div>
        <div class="ic-rw"><span>Workers · informal</span><b>${p.workers_m!=null?p.workers_m+'M · '+p.informal_pct+'% informal':'—'}</b></div></div>
      <div class="ic-blk"><div class="ic-bt">VEHICLES — OURS vs ALL <span class="m">DLT + TAPE</span></div>
        <div class="ic-rw"><span>Registered fleet</span><b>${v.fleet_m}M <span class="s">(${v.fleet_pu_m}M pickup · ${v.fleet_mc_m}M moto)</span></b></div>
        <div class="ic-rw"><span>We finance — pickups</span><b>1 per ${icN(v.per_pu)}</b></div>
        <div class="ic-rw"><span>We finance — motos</span><b>1 per ${icN(v.per_mc)}</b></div></div>
      <div class="ic-blk"><div class="ic-bt">OCCUPATIONS — BOOK vs WORKFORCE <span class="m">TAPE · LFS</span></div>
        ${occ}
        <div class="ic-rw"><span>Penetration</span><b>${o.workers_per_acc!=null?'1 account per '+icN(o.workers_per_acc)+' workers':'—'}</b></div></div>
    </div>
    <div class="ic-rivrow"><span class="ic-bt" style="margin:0">RIVALS</span>
      <b style="color:${rv.ratio>=9?'var(--agri)':rv.ratio>=7?'var(--gold)':'var(--merch)'}">${icN(rv.rivals)} vs ${icN(rv.ours)} (${rv.ratio!=null?rv.ratio.toFixed(1):'—'}×)</b>
      <span class="s">rivals lead in ${rv.pct_districts_outnumbered!=null?rv.pct_districts_outnumbered.toFixed(0):'—'}% of our districts</span></div>
    ${commods?`<div class="ic-commods"><span class="ic-bt" style="margin:0">CROP PRICES</span>${commods}</div>`:''}
    <button type="button" class="ic-drill" data-r="${g.key}" aria-label="Drill into ${g.key} — show its provinces">${ (g.provinces||[]).length } provinces — drill in <span class="ic-chev">›</span></button>
  </div>`;
}
/* Breadcrumb drill controller (owner ask 2026-07-25): the drill was nested 3 levels deep (branch
   table inside a colspan inside a province table inside a card) and cramped. Now ONE full-width level
   shows at a time — region cards → a region's province table → a province's branch table — with a
   back-crumb. Per-mount view state lives on the element so each pillar (Home/Assist/Risk/Competition)
   drills independently and persists across tab switches. */
function icRegionOf(key){ return IMPACT.regions.find(x=>x.key===key); }
/* parts: [{label, lvl}] — lvl is the level to jump to when that crumb is pressed; the last part is the
   current (non-clickable) location. Each crumb navigates directly to its own level (not just pop-one). */
function icCrumb(parts){
  return `<div class="ic-crumb">`+parts.map((p,i)=>
    i<parts.length-1
      ?`<button type="button" class="ic-back" data-lvl="${p.lvl}">${i===0?'‹ ':''}${p.label}</button><span class="ic-crumb-sep">›</span>`
      :`<span class="ic-crumb-cur">${p.label}</span>`).join('')+`</div>`;
}
function icRenderLevel(mount){
  const st=mount._icState, mode=mount._icMode, w=(IMPACT.meta||{}).trend_window||{};
  if(st.level==='province'){
    const g=icRegionOf(st.region);
    if(!g){ mount._icState={level:'regions'}; return icRenderLevel(mount); }
    mount.innerHTML=icCrumb([{label:'All regions',lvl:'regions'},{label:g.key+(g.name_th?' · '+g.name_th:'')}])+
      `<div class="ic-drill-h"><b>${g.key}</b> — ${(g.provinces||[]).length} provinces · press a province row for its branches</div>`+
      icProvTable(g);
    return;
  }
  if(st.level==='branch'){
    const g=icRegionOf(st.region);
    mount.innerHTML=icCrumb([{label:'All regions',lvl:'regions'},{label:(g?g.key:st.region),lvl:'province'},{label:st.province}])+
      `<div class="ic-drill-h"><b>${st.province}</b> — booking branches on the tape (n ≥ 30), worst NPL-live first</div>`+
      icCropStrip((IMPACT.provinces||{})[st.province],st.province)+
      icBranchRows(st.province);
    return;
  }
  let regs=IMPACT.regions.slice();
  if(mode&&IC_SORT[mode]) regs.sort(IC_SORT[mode]);
  mount.innerHTML=
    `<div class="ic-strip-h"><span>The five regions — press a region → its provinces → its branches</span>`+
    (mode&&IC_MODE_NOTE[mode]?`<span class="s">${IC_MODE_NOTE[mode]}</span>`:'')+`</div>`+
    icLadderLegend()+
    `<div class="ic-grid">${regs.map(icCard).join('')}</div>`+
    `<div class="ic-foot">All card numbers <b>measured</b> (tape ${((IMPACT.meta||{}).tape||{}).mob_anchor||''} · NSO SES/LFS · DLT fleet · rival census) except the est. individual-income split and the agri-risk trend model (${w.from||''} → ${w.to||''}). ${(IMPACT.meta||{}).occ_note||''}</div>`;
}
/* a11y (reconciles fc7e11c #165): the old nested drill was a disclosure widget, so aria-expanded
   announced its open/closed state. The breadcrumb rewrite made the drill a VIEW-SWAP navigation
   (the region grid is replaced by the province/branch level), for which aria-expanded is the wrong
   semantic. Instead, after a user-driven navigation we move focus to the new level's back-crumb so a
   screen reader announces the context change. preventScroll so it never fights the scrollIntoView.
   Not called on the initial render (renderImpactStrip → icRenderLevel) — only on click navigation —
   so page load never steals focus. */
function icFocusLevel(mount){ const b=mount&&mount.querySelector('.ic-back'); if(b){ try{ b.focus({preventScroll:true}); }catch(_){ b.focus(); } } }
function renderImpactStrip(mountId,mode){
  const mount=document.getElementById(mountId);
  if(!mount) return;
  // income_impact rides along so the province crop strip can show the farmer's cash, not just the
  // world price. It is cached by tmliFetch, so this costs one request for the whole session; a null
  // result just means icCropIncome renders nothing.
  Promise.all([loadImpact(),tmliFetch('income_impact')]).then(([,inc])=>{
    if(inc&&inc.provinces) INCIMP=inc;
    if(!IMPACT){ mount.innerHTML='<div class="ic-note">Impact cards not yet computed — data/impact_cards.json is absent (run pipeline/build_impact_cards.py).</div>'; return; }
    mount._icMode=mode;
    if(!mount._icState) mount._icState={level:'regions'};
    icRenderLevel(mount);
    if(!mount.dataset.icWired){
      mount.dataset.icWired='1';
      mount.addEventListener('click',e=>{
        const back=e.target.closest('.ic-back');
        if(back){ const st=mount._icState;
          mount._icState=(back.dataset.lvl==='province')?{level:'province',region:st.region}:{level:'regions'};
          icRenderLevel(mount); icFocusLevel(mount); return; }
        const drill=e.target.closest('.ic-drill');
        if(drill){ mount._icState={level:'province',region:drill.dataset.r};
          icRenderLevel(mount); mount.scrollIntoView({block:'nearest'}); icFocusLevel(mount); return; }
        const prow=e.target.closest('.ic-prow');
        if(prow){ mount._icState={level:'branch',region:(mount._icState||{}).region,province:prow.dataset.p};
          icRenderLevel(mount); mount.scrollIntoView({block:'nearest'}); icFocusLevel(mount); return; }
      });
      // Keyboard activation for the drill-down province rows (role="link" tabindex=0): Enter / Space.
      // The .ic-drill / .ic-back controls are native <button>s (already keyboard-activatable via the
      // click delegation); the .ic-prow <tr>s are not, so mirror the click branch here (WCAG 2.1.1).
      mount.addEventListener('keydown',e=>{
        if(e.key!=='Enter'&&e.key!==' '&&e.key!=='Spacebar') return;
        const prow=e.target.closest&&e.target.closest('.ic-prow');
        if(!prow||prow!==e.target) return;
        e.preventDefault();
        mount._icState={level:'branch',region:(mount._icState||{}).region,province:prow.dataset.p};
        icRenderLevel(mount); mount.scrollIntoView({block:'nearest'}); icFocusLevel(mount);
      });
    }
  });
}
function renderImpactMounts(v){
  const m=IC_MOUNTS[v];
  if(m) renderImpactStrip(m[0],m[1]);
}

/* ---------- TMLI-convergence panels (owner ask 2026-07-25) — the four layers that closed the gap
   with the retired TMLI effort. Each fetches its own data lazily, caches, and degrades to a calm
   absent-note (never a broken scene). All numbers labelled measured / estimated / stated. ------- */
let TMLI_CACHE={};
function tmliFetch(name){
  if(TMLI_CACHE[name]) return TMLI_CACHE[name];
  TMLI_CACHE[name]=fetch('data/'+name+'.json').then(r=>r.ok?r.json():null).catch(()=>null);
  return TMLI_CACHE[name];
}
function tmliNote(el,msg){ el.innerHTML=`<div class="ic-note">${msg}</div>`; }
function icArrow(x){ return x==null?'→':x>0?'▲':x<0?'▼':'→'; }
function icSign(x){ return x==null?'—':(x>0?'+':'')+x+'%'; }
function icMoveColor(x,invert){ if(x==null) return 'var(--muted)';
  const up=invert? x<0 : x>0; return up?'var(--merch)':(x===0?'var(--muted)':'var(--agri)'); }

/* MOVE 2 — income-impact engine: macro moves → occupation income → book pressure (Assistance). */
function renderIncome(){
  const el=document.getElementById('assist-income'); if(!el) return;
  tmliFetch('income_impact').then(j=>{
    if(!j||!Array.isArray(j.regions)){ tmliNote(el,'Income-impact engine not yet computed — <b>data/income_impact.json</b> is absent (run pipeline/build_income_impact.py).'); return; }
    const d=(j.meta||{}).drivers||{}, cy=d.crop_yoy_pct||{};
    const rows=j.regions.map(g=>{
      const p=g.income_pressure_pct, pc=icMoveColor(p);
      const mix=Object.entries(g.book_mix||{}).sort((a,b)=>b[1]-a[1]).slice(0,3)
        .map(([o,pct])=>`${o} ${pct}%`).join(' · ');
      const best=g.best_occ||{}, worst=g.worst_occ||{};
      const wa=g.nso_wage_ref||null;
      const waCell=(wa&&wa.headline)
        ? `<span title="MEASURED · NSO Labour Force Survey avg monthly EMPLOYEE wage — an independent anchor beside the SES income base, not the base itself (employee wage ≠ individual income)">฿${icN(wa.headline)}/mo</span>`
        : '<span class="s">—</span>';
      return `<tr>
        <td><b>${g.key}</b></td>
        <td class="n"><b style="color:${pc}">${p>0?'+':''}${p}%</b></td>
        <td>${best.occ?`<span style="color:var(--merch)">${best.occ} ${best.d_pct>0?'+':''}${best.d_pct}%</span>`:'—'}</td>
        <td>${worst.occ&&worst.d_pct<0?`<span style="color:var(--agri)">${worst.occ} ${worst.d_pct}%</span>`:'<span class="s">none declining</span>'}</td>
        <td class="s">${mix}</td>
        <td class="n">${waCell}</td></tr>`;
    }).join('');
    el.innerHTML=`
      <h2>Income-impact engine — what the macro move does to each region's book <span class="tag" style="color:var(--gold);border:1px solid var(--gold)">ESTIMATED · first-order</span></h2>
      <p class="lead">Current crop prices (rice ${icSign(cy.rice)}, rubber ${icSign(cy.rubber)}, palm ${icSign(cy.oilpalm)} YoY) passed through NSO occupation incomes and weighted by each region's book mix. <b>Positive = income tailwind</b> for the book. Fuel channel is 0 this vintage (no measured baseline to diff — we don't invent one), so today's picture is purely the crop channel. <b style="color:var(--agri)">Read this as a THREE-crop engine.</b> It weights rice, rubber and oilpalm only — all three rising — so it reports every region positive. The <a href="#overview" data-jump="sec-ov-agri">crop-mix panel on Macro</a> weights all eight priced crops and finds four provinces falling, coconut and sugarcane led; this table cannot see them.</p>
      <div class="ic-scroll"><table class="ic-tbl"><thead><tr><th>Region</th><th>Book income pressure</th><th>Best-off occupation</th><th>Worst-off occupation</th><th>Top book occupations</th><th title="MEASURED — NSO Labour Force Survey avg monthly EMPLOYEE wage; an independent cross-check beside the SES income base, not the base">NSO wage · LFS</th></tr></thead><tbody>${rows}</tbody></table></div>
      <p class="lead cc-provenance"><b>Provenance:</b> ESTIMATED first-order pass-through. Every quantity multiplied is measured (NSO SES income, crop planted area, World Bank commodity YoY); the sensitivity coefficients (how much of a price move reaches take-home income) are a documented assumption. Read direction and relative magnitude, not precise levels. <b>NSO wage · LFS</b> is a MEASURED cross-check only — the region's Labour Force Survey employee wage (${((j.meta||{}).vintage||{}).wage_anchor||'latest'}) shown beside the model; it is an employee wage, not the SES individual income the model bases on (which counts non-wage income), so read it as a directional anchor, not an equality.</p>`;
  });
}

/* MOVE 3 — scenario engine: LIVE / stated-stress presets, each with its vintage (Sim). */
const SCEN_KIND={live:['LIVE','var(--merch)'],stress:['STATED STRESS','var(--gold)']};
function renderScenarios(){
  const el=document.getElementById('sim-scenarios'); if(!el) return;
  tmliFetch('scenarios').then(j=>{
    if(!j||!Array.isArray(j.scenarios)){ tmliNote(el,'Scenario engine not yet computed — <b>data/scenarios.json</b> is absent (run pipeline/build_scenarios.py).'); return; }
    const cards=j.scenarios.map(s=>{
      const [lab,col]=SCEN_KIND[s.kind]||['',''];
      return `<div class="scn-card">
        <div class="scn-h"><span class="scn-badge" style="color:${col};border-color:${col}">${lab}</span>
          <span class="scn-vint">${s.vintage||''}</span></div>
        <h4>${s.title}</h4>
        <p class="scn-head">${s.headline}</p>
        <p class="scn-prov">${s.provenance||''}</p></div>`;
    }).join('');
    el.innerHTML=`
      <h2 class="risk">Current scenarios — refreshed weekly, not hardcoded <span class="tag" style="color:var(--accent);border:1px solid var(--accent)">DATA LAYER</span></h2>
      <p class="lead">The real-world shocks live right now, each stamped with its vintage. <b style="color:var(--merch)">LIVE</b> = measured current driver; <b style="color:var(--gold)">STATED STRESS</b> = a labelled hypothetical, not a forecast. Rebuilt weekly by the scenario cron from the measured signal layers. The sliders below let you run your own what-if.</p>
      <div class="scn-grid">${cards}</div>`;
  });
}

/* MOVE 4 — commodities board: global Pink Sheet × Thai farm-gate × who's-exposed drill (Overview). */
/* Commodity board label -> the crop key used by assist_price_radar.json / income_impact.json crop_mix.
   Only the crops with a province planted-area map appear here. Coconut, Pineapple and Sugar joined
   on 2026-08-01 — the first two once ingest_doae.py started reading all 19 registry crop columns
   instead of 5, and Sugar once ingest_ocsb_cane.py landed OCSB's own 47-province cane returns (cane
   growers register with the OCSB, so it is in no other registry here). Livestock and fisheries stay
   unmapped on purpose: they have no planted area, so joining them to one would be a guess. */
const CB_CROP={'Rice':'rice','Rubber':'rubber','Palm oil':'oilpalm','Maize':'maize','Cassava':'cassava',
               'Coconut':'coconut','Pineapple':'pineapple','Sugar':'sugarcane'};
const OCC_TH={Agriculture:'เกษตรกร',Transport:'ขนส่ง',FactoryWorkers:'โรงงาน',OfficeStaff:'พนักงานบริษัท',SMEOwners:'ผู้ประกอบการ'};

/* THAI price trend + province spread inside a commodity drill (data/thai_price_history.json).
   Every sparkline on the board itself is a WORLD price; this is the first Thai series the product
   has ever drawn. The province spread is the point: a national average is one number, but paddy
   ranges ~22% between the provinces this book lends into, which is wider than most YoY moves the
   board leads with. Returns '' when the series is absent — the drill just loses a block. */
function cbThaiHistory(THI,lab){
  const s=THI&&THI.series&&THI.series[lab]; if(!s||!Array.isArray(s.values)||s.values.length<2) return '';
  const ann=s.cadence==='annual', ch=s.change_pct;
  const col=ch==null?'var(--dim)':ch>0?'var(--merch)':ch<0?'var(--agri)':'var(--dim)';
  const fmt=v=>Number(v).toLocaleString(undefined,{maximumFractionDigits:2});
  const spark=svgSpark(s.values,{w:150,h:30,
    aria:lab+' Thai price, '+s.first_month+' to '+s.last_month,
    title:lab+' · '+s.product+' · '+s.first_month+' → '+s.last_month+' ('+s.n_months+' points)'});
  // Sugar is administered, so it has no province spread BY CONSTRUCTION — say which kind of empty
  // this is rather than showing a blank that reads as missing data.
  const spread=(s.provinces||[]).length>=2
    ? `<div class="cb-spread"><b>Province spread ${s.spread_pct==null?'':`<span style="color:var(--gold)">${s.spread_pct}%</span>`}</b>
        <span class="s">dearest vs cheapest quoting province, last ${THI.meta&&THI.meta.spread_note?'quarter':'window'} — a national average hides this</span>
        <table class="ic-tbl" style="margin-top:4px"><thead><tr><th>Province</th><th>Mean ${s.unit||''}</th><th title="quotes behind that mean">Quotes</th></tr></thead><tbody>${
        s.provinces.map(p=>`<tr><td>${p.province}</td><td class="n">${fmt(p.mean)}</td><td class="n s">${p.n}</td></tr>`).join('')
      }</tbody></table></div>`
    : `<div class="cb-spread s">${ann
        ? 'No province spread — the cane price is <b>administered nationally</b>, so every province is paid the same announced rate. Empty here means <i>cannot vary</i>, not <i>unknown</i>.'
        : 'Quoted by a single province, so there is no spread to show.'}</div>`;
  return `<div class="cb-thai"><div class="cb-thai-hd">
      <b>Thai price, ${s.first_month} → ${s.last_month}</b>
      <span class="tag" style="color:var(--merch);border:1px solid var(--merch)">MEASURED</span>
      ${ann?'<span class="tag" style="color:var(--gold);border:1px solid var(--gold)" title="one announced national price per season — not a market series">ANNUAL · ADMINISTERED</span>':''}
      <span class="mono" style="color:${col}"><b>${ch==null?'':(ch>0?'+':'')+ch+'%'}</b></span>
      <span class="s">over ${s.n_months} ${ann?'years':'months'} · ${fmt(s.min)}–${fmt(s.max)} ${s.unit||''}</span>
    </div>
    <div class="cb-thai-body">${spark}<span class="s">${s.product||''}</span></div>
    ${spread}</div>`;
}
function renderCommoditiesBoard(){
  const el=document.getElementById('ov-commodities'); if(!el) return;
  Promise.all([tmliFetch('commodities'),tmliFetch('assist_price_radar'),tmliFetch('income_impact'),
               tmliFetch('commodity_history'),tmliFetch('thai_price_history')]).then(([j,APR,INC,HIST,THI])=>{
    if(!j||!Array.isArray(j.board)){ tmliNote(el,''); return; }   // silent when absent — the legacy board still shows
    const aprCrop=k=>((APR&&Array.isArray(APR.crops))?APR.crops:[]).find(c=>c.key===k)||null;
    const incProv=p=>((INC&&INC.provinces)?INC.provinces[p]:null)||null;
    // 60-month Pink Sheet price history (commodity_history.json, 2026-08-01). Until this layer
    // landed the pipeline kept only `latest` + `yoy`, so no price chart was drawable anywhere in
    // the product. Series keys are the board's own lowercased labels; absent series → the honest
    // no-history marker, never a flat line.
    const spark=lab=>{
      const s=HIST&&HIST.series&&HIST.series[String(lab||'').toLowerCase().replace(/\s+.*$/,'')];
      const v=s&&Array.isArray(s.values)?s.values:null;
      if(!v) return '<span class="s">—</span>';
      const m=s.months||[];
      return svgSpark(v,{w:96,h:22,aria:lab+' 60-month price history',
        title:lab+' · '+(m[0]||'')+' → '+(m[m.length-1]||'')+' ('+v.length+' months)'});
    };
    // The move the BORROWER feels: Thai farm-gate where a local series exists, world price
    // otherwise. The builder already sorts the board on it; this is the same number drawn.
    const felt=c=>c.local_yoy!=null?c.local_yoy:c.global_yoy;
    const feltMax=Math.max(...j.board.map(c=>Math.abs(felt(c)||0)),1);
    const rows=j.board.map((c,i)=>{
      const gc=icMoveColor(c.global_yoy), lc=icMoveColor(c.local_yoy);
      const fv=felt(c), fc=icMoveColor(fv), isLoc=c.local_yoy!=null;
      const exp=c.exposure;
      const expCell=exp?`<span class="cb-exp" data-i="${i}">${icN(exp.book_accounts)} acc <span class="cb-chev">▸</span></span>`:'<span class="s">—</span>';
      const div=c.divergence;
      const divCell=div==null?'<span class="s">—</span>':`<b style="color:${div>0?'var(--merch)':'var(--agri)'}">${div>0?'+':''}${div} pts</b>`;
      let drill='';
      if(exp){
        // WHO the price actually reaches. The belt table alone says "accounts near this crop"; these
        // two lines say which OCCUPATION carries it, what the price move is worth to that household
        // in baht a month, and how much of the book is still healthy enough to call early.
        const ck=CB_CROP[c.lab], ap=ck?aprCrop(ck):null;
        const bp=(exp.top||[]).map(t=>({t,ip:incProv(t.prov)})).filter(x=>x.ip);
        const agri=bp.map(x=>x.ip.occ&&x.ip.occ.Agriculture).filter(Boolean);
        const shocks=bp.map(x=>x.ip.agri_price_shock_pct).filter(v=>v!=null);
        const avg=a=>a.length?a.reduce((s,v)=>s+v,0)/a.length:null;
        const shock=avg(shocks), dbaht=avg(agri.map(a=>a.d_baht).filter(v=>v!=null));
        const occLine=shock==null?'':`<div class="cb-occ"><b>Who carries it:</b> <span class="tag">${OCC_TH.Agriculture} · Agriculture</span> — across these belt provinces crop prices move farm income <b style="color:${shock>=0?'var(--merch)':'var(--agri)'}">${shock>0?'+':''}${shock.toFixed(1)}%</b>${dbaht==null?'':` (≈ <b>${dbaht>0?'+':''}฿${icN(Math.round(dbaht))}</b>/month per farm household)`}. <span class="s">Agriculture is the occupation the tape records; the crop a given borrower grows is not recorded.</span></div>`;
        // A row can carry a belt but no assistable population, because the assistance radar keys off
        // the Thai FARM-GATE series and not every crop has one. Sugar is exactly that case, and it
        // is the ONLY falling price that also has a belt — staying silent there reads as "nothing to
        // do" when the truth is "we cannot compute it yet". Say which of the two it is, and name the
        // unlock. (The other fallers — coconut, pineapple, pork, shrimp, eggs, chicken — have a Thai
        // price but no province area, so they cannot reach a belt at all.)
        // Two DIFFERENT reasons a belt can exist with no call list, and saying the wrong one is its
        // own error: either we hold no Thai price for the crop, or we hold one and the assistance
        // radar does not map the crop. All eight belted crops now clear both, so this line is a
        // guard for future rows rather than something any current commodity hits.
        const gapLine=`<div class="cb-assist cb-gap"><b>No call-list for ${c.lab} yet:</b> ${
          c.local_yoy==null
            ? `the assistable-now population is computed from a <b>Thai price series</b>, and ${c.lab} has none in this repo`
            : `${c.lab} <b>is</b> priced here (${c.local_yoy>0?'+':''}${c.local_yoy}% Thai), but the assistance radar's exposure join does not map it — it reads crop_stress.json planted-area shares, which livestock and fisheries have none of`
        } — so the ${icN(exp.book_accounts)} accounts above are <b>standing exposure</b>, not a worked list.</div>`;
        const assistLine=!ap?gapLine:`<div class="cb-assist"><b>Assistable now:</b> <b>${icN(ap.n_current_x)}</b> farm accounts across ${ap.n_provinces} provinces that depend on ${c.lab} are <b>Current or only X-bucket</b> — healthy today. ${ap.direction==='down'?`<b style="color:var(--agri)">This price is falling — that is the call list.</b>`:`Nothing to act on while the price is ${ap.direction} (${ap.yoy>0?'+':''}${ap.yoy}% farm-gate); this is the standing exposure if it turns.`} <a href="#assist" data-v="assist">Assistance →</a></div>`;
        const apv=exp.area_provenance||'', modelled=apv==='MODELLED';
        const areaLine=!apv?'':`<div class="cb-areasrc"><span class="tag" style="color:${modelled?'var(--gold)':'var(--merch)'};border:1px solid ${modelled?'var(--gold)':'var(--merch)'}">${apv} area</span> <b>${exp.area_source||''}</b> — <span class="s">${exp.area_note||''}</span></div>`;
        const thaiLine=cbThaiHistory(THI,c.lab);
        // The income columns used to show income_impact.json's province-wide agri_price_shock_pct,
        // which is area-weighted over rice/rubber/oilpalm ONLY — so the coconut belt read +26.84%
        // farm income while coconut itself was down 70.9%, because ประจวบคีรีขันธ์'s crop mix is 61%
        // rubber / 34% palm and holds no coconut at all. They now carry THIS crop's own effect, and
        // the assumption that makes them readable is stated on the page rather than in a tooltip.
        const incBasis=!exp.income_basis?'':`<div class="cb-incbasis"><span class="tag" style="color:var(--gold);border:1px solid var(--gold)">ESTIMATED</span> <b>Reading the income columns:</b> they are <b>${c.lab}'s own effect</b> on a farm household in that province <b>whose main crop is ${c.lab}</b> — the crop's Thai move passed through the income engine's farm sensitivity onto that province's measured NSO SES farm income. They are not the province's all-crop farm income (a different number, driven mostly by rice, rubber and palm, and shown on the province view). Not weighted by ${c.lab}'s share of local land: belt areas come from different registries, so a cross-source share would be false precision.</div>`;
        // TOTAL ROW (added 2026-08-01, owner ask). build_commodities.py used to emit only the belt's
        // six largest provinces while the line above the table quoted the whole belt, so the accounts
        // column visibly failed to add up to its own headline — rice showed 50,742 against 138,184
        // with the missing 63% nowhere on the page. The builder now emits every belt province, so
        // this row is a real total and it reconciles exactly. The partial branch is kept as a
        // guard: if a future change ever truncates the list again, the page says so instead of
        // quietly presenting a short column as if it were complete.
        const shown=exp.top||[], shownAcc=shown.reduce((s,t)=>s+(t.accounts||0),0),
              shownArea=shown.reduce((s,t)=>s+(t.area_rai||0),0),
              restProv=(exp.belt_provinces||0)-shown.length, restAcc=(exp.book_accounts||0)-shownAcc;
        const footRow=!shown.length?'':`<tfoot><tr class="cb-foot">
          <td><b>${restProv>0?`${shown.length} of ${exp.belt_provinces} belt provinces shown`:`Belt total · ${exp.belt_provinces} provinces`}</b></td>
          <td class="n"><b>${icN(shownArea)}</b></td>
          <td class="n"><b>${restProv>0?`${icN(shownAcc)} of ${icN(exp.book_accounts)}`:icN(shownAcc)}</b></td>
          <td colspan="2" class="s">${restProv>0
            ? `the other ${icN(restProv)} belt province${restProv===1?'':'s'} hold ${icN(restAcc)} accounts (${Math.round(restAcc/(exp.book_accounts||1)*100)}% of the belt)`
            : `adds up to the ${icN(exp.book_accounts)} above — this is the whole belt, not a sample`}</td></tr></tfoot>`;
        drill=`<tr class="cb-drill" data-i="${i}" hidden><td colspan="8"><div class="cb-belt">
          <b>Who's exposed:</b> ${icN(exp.book_accounts)} book accounts sit in the ${exp.belt_provinces}-province core belt — ${(exp.basis||'').replace(/^book accounts in /,'')}
          ${areaLine}
          <div class="cb-belttbl"><table class="ic-tbl" style="margin-top:6px"><thead><tr><th scope="col">Province (belt)</th><th scope="col">Planted area (rai)</th><th scope="col">Book accounts</th><th scope="col" title="THIS crop's effect on a farm household here whose main crop is ${c.lab} — sensitivity × the crop's Thai YoY. ESTIMATED.">${c.lab} → farm income</th><th scope="col" title="the same effect in baht, on the province's MEASURED NSO SES farm-income base">฿/month</th></tr></thead><tbody>${
            shown.map(t=>{
              const ipc=t.crop_income_pct, ibt=t.crop_income_baht;
              return `<tr><td>${t.prov}</td><td class="n">${icN(t.area_rai)}</td><td class="n">${icN(t.accounts)}</td>`+
                `<td class="n">${ipc!=null?`<span style="color:${ipc>=0?'var(--merch)':'var(--agri)'}">${ipc>0?'+':''}${ipc}%</span>`:'<span class="s">—</span>'}</td>`+
                `<td class="n">${ibt!=null?`<span style="color:${ibt>=0?'var(--merch)':'var(--agri)'}">${ibt>0?'+':'−'}฿${icN(Math.abs(ibt))}</span>`:'<span class="s">—</span>'}</td></tr>`;}).join('')
          }</tbody>${footRow}</table></div>${incBasis}${thaiLine}${occLine}${assistLine}</div></td></tr>`;
      }
      return `<tr class="cb-row"><td><b>${c.lab}</b> <span class="s">${c.seg||''}</span></td>
        <td class="cb-felt" title="${isLoc?'Thai farm-gate':'world price only — no Thai farm-gate series'}">${cbBar(fv,feltMax)}${
          fv==null?'':`<b style="color:${fc}">${fv>0?'+':''}${fv}%</b>${isLoc?'':'<span class="s cb-deg">°</span>'}`}</td>
        <td class="cb-spark">${spark(c.lab)}</td>
        <td class="n">${c.global_yoy==null?'<span class="s">n/a</span>':`<span style="color:${gc}">${icArrow(c.global_yoy)} ${c.global_yoy>0?'+':''}${c.global_yoy}%</span>`}</td>
        <td class="n">${c.local_yoy==null?'<span class="s">n/a</span>':`<span style="color:${lc}" title="${[c.local_product,c.local_source,c.local_price,c.local_date].filter(Boolean).join(' · ')}">${c.local_yoy>0?'+':''}${c.local_yoy}%</span>${
          c.local_markets?`<span class="s cb-mkt${c.local_markets<2?' thin':''}" title="${c.local_markets} market${c.local_markets>1?'s':''} quote this series${c.local_markets<2?' — a single-market quote, read it as thin':''}">${c.local_markets}mkt</span>`:''}`}</td>
        <td class="n">${divCell}</td>
        <td class="n">${expCell}</td>
        <td class="s">${c.note||''}</td></tr>${drill}`;
    }).join('');
    const f=j.fuel||{};
    // 2026-08-01: the standalone full-width bar chart that used to sit here was DELETED, not
    // resized. It restated the table's own 11 numbers in a second block, and because it scaled to
    // container width it rendered 673px tall against a 409px table. The ranking it provided is now
    // the table's sort order and its magnitudes are the "Borrower feels" cell bars — one block
    // instead of two, and every row carries its own bar.
    const nLoc=(j.board||[]).filter(c=>c.local_yoy!=null).length;
    el.innerHTML=`
      <h2>Commodities board · global price × Thai farm-gate × who's exposed <span class="tag" style="color:var(--gold);border:1px solid var(--gold)">MEASURED prices</span></h2>
      <p class="lead">World price (Pink Sheet YoY) beside the Thai farm-gate move, their <b>divergence</b> (where the local farmer's cash parts from the world index), and the <b>book accounts</b> sitting in each crop's growing belt — press a row to see the belt. ${f.diesel_thb_l?`Diesel now <b>฿${f.diesel_thb_l}/L</b> (${f.name}) — a cost line for pickup/haulage, not crop revenue.`:''}</p>
      <div class="ic-scroll"><table class="ic-tbl cb-tbl"><thead><tr><th>Commodity</th><th title="Thai farm-gate where a local series exists, world price otherwise">Borrower feels</th><th>5-yr trend</th><th>World YoY</th><th title="Thai farm-gate (raw crop forms) or the NABC daily market feed for livestock, fishery and orchard series. Nmkt = how many markets quote it.">Thai price</th><th>Divergence</th><th>Book exposed</th><th></th></tr></thead><tbody>${rows}</tbody></table>
        <p class="s cb-key">Sorted by the move the borrower feels. <b>°</b> = world price only, no Thai series (${(j.board||[]).length-nLoc} of ${(j.board||[]).length}). <b>Nmkt</b> = markets quoting that Thai price; a 1mkt series is measured but thin.${((j.meta||{}).nabc_excluded||[]).length?` Excluded as stale: ${(j.meta||{}).nabc_excluded.join('; ')}.`:''}</p></div>
      <p class="lead cc-provenance"><b>Provenance:</b> MEASURED prices (World Bank Pink Sheet global YoY + Thai farm-gate local YoY). Who's-exposed is an ESTIMATED book-footprint read — accounts in a crop's core growing belt (provinces = ~80% of national planted area). Each belt states its own area source, and <b>every belt on this board is now MEASURED</b>: rice / rubber / palm from the planted-area census, cassava / maize / coconut / pineapple from the DOAE farmer registry, sugarcane from OCSB's own returns (the modelled SPAM-2010 raster it replaced understated the cane belt by ~1.7×).</p>`;
    if(!el.dataset.wired){ el.dataset.wired='1';
      el.addEventListener('click',e=>{const x=e.target.closest('.cb-exp'); if(!x) return;
        const dr=el.querySelector(`.cb-drill[data-i="${x.dataset.i}"]`); if(!dr) return;
        const open=dr.hidden; dr.hidden=!open; const ch=x.querySelector('.cb-chev'); if(ch) ch.textContent=open?'▾':'▸';});
    }
  });
}

/* MOVE 5 — product → segment → driver map: which book each shock hits (Exposure/Risk). */
function renderProducts(){
  const el=document.getElementById('exposure-products'); if(!el) return;
  tmliFetch('product_segments').then(j=>{
    if(!j||!Array.isArray(j.products)){ tmliNote(el,''); return; }   // silent when absent
    const rows=j.products.map(p=>{
      const seg=(p.segments||[]).join(' · ')||'<span class="s">—</span>';
      const drv=(p.drivers||[]).map(d=>`<span class="pm-drv">${d}</span>`).join(' ');
      const scn=(p.scenarios||[]).map(s=>`<span class="pm-scn">${s}</span>`).join(' ');
      return `<tr><td><b>${p.product}</b>${p.th?` <span lang="th" class="s">${p.th}</span>`:''}</td>
        <td class="n">${p.book_share_pct}%</td>
        <td class="n">${icPct(p.npl_live_pct,4.7,5.3)}</td>
        <td>${seg}</td>
        <td>${drv}</td>
        <td>${scn}</td></tr>`;
    }).join('');
    const di=j.driver_index||{};
    const idx=Object.entries(di).map(([d,codes])=>`<div class="pm-idxrow"><span class="pm-drv">${d}</span> moves <b>${codes.join(', ')}</b></div>`).join('');
    el.innerHTML=`
      <h2 class="risk">Product → segment → driver map <span class="tag" style="color:var(--merch);border:1px solid var(--merch)">MEASURED book · curated map</span></h2>
      <p class="lead">Which borrowers sit behind each collateral product, what income driver moves them, and which scenarios (above, in the simulator) hit them. Book share &amp; NPL are <b>measured</b> from the tape; the segment / driver / scenario wiring is a <b>curated</b> transmission map.</p>
      <div class="ic-scroll"><table class="ic-tbl"><thead><tr><th>Product</th><th>Book share</th><th>NPL-live</th><th>Borrower segments</th><th>Income drivers</th><th>Scenarios that hit it</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="pm-idx"><div class="ic-bt" style="margin:0 0 4px">WHEN A DRIVER MOVES, THESE BOOKS FEEL IT</div>${idx}</div>
      <p class="lead cc-provenance"><b>Provenance:</b> MEASURED book economics per product (share / NPL / outstanding — tape vehicle_types). The product→segment→driver→scenario wiring is a curated editorial map, labelled as such. IMF WEO macro backdrop is now wired (Macro → IMF macro outlook); CPI-by-category / MOTS tourism feeds are not yet wired — each needs its own scheduled puller.</p>`;
  });
}

/* IMF WEO macro backdrop — Thailand growth/inflation/unemployment/debt + ASEAN peer benchmark
   (data/imf_weo.json, pull_imf_weo.py). Actuals vs IMF projections labelled; peers = external
   benchmark (AutoX has no IPO). Overview macro column. Null-safe: absent/empty → nothing renders. */
const IMF_DIR={NGDP_RPCH:1,PCPIPCH:-1,LUR:-1,GGXWDG_NGDP:-1,BCA_NGDPD:1}; // +1 = higher is better
function imfCol(code,v){ if(v==null) return 'var(--mid)'; const d=IMF_DIR[code]||0; if(!d) return 'var(--hi)';
  return ((d>0)===(v>=0))?'var(--merch)':'var(--agri)'; }
function renderImfWeo(){
  const el=document.getElementById('ov-imfweo'); if(!el) return;
  tmliFetch('imf_weo').then(j=>{
    if(!j||!j.thailand||!Object.keys(j.thailand).length){ tmliNote(el,''); return; }  // silent when absent
    const m=j.meta||{}, T=j.thailand, P=j.peers||{}, pn=m.peers||{};
    const rows=Object.entries(T).map(([code,v])=>{
      const la=v.latest_actual||{}, pr=v.projection||{};
      return `<tr><td><b>${v.label}</b> <span class="s">${v.unit}</span></td>
        <td class="n"><b style="color:${imfCol(code,la.val)}">${la.val!=null?la.val:'—'}</b> <span class="s">${la.year||''}</span></td>
        <td class="n" style="color:${imfCol(code,pr.val)}">${pr.val!=null?pr.val:'—'} <span class="s">${pr.year||''}</span></td>
        <td class="s">${v.why||''}</td></tr>`;
    }).join('');
    // peer benchmark for the two headline indicators
    const bench=['NGDP_RPCH','PCPIPCH'].filter(c=>P[c]).map(c=>{
      const order=Object.keys(pn);
      const cells=order.map(iso=>{
        const val=(P[c]||{})[iso]; const me=iso==='THA';
        return `<span class="imf-peer${me?' me':''}" title="${pn[iso]||iso}">${iso} ${val!=null?val:'—'}</span>`;
      }).join('');
      return `<div class="imf-benchrow"><span class="imf-blab">${(T[c]||{}).label||c} <span class="s">${m.peer_bench_year||''}</span></span>${cells}</div>`;
    }).join('');
    el.innerHTML=`
      <h2 style="margin-top:16px">IMF macro outlook · Thailand <span class="tag" style="color:var(--accent);border:1px solid var(--accent)">IMF WEO</span></h2>
      <p class="lead">The macro backdrop under borrower income — <b>actuals</b> and the <b>IMF projection</b> for the year ahead. Higher growth helps the book; higher inflation/unemployment pressure it.</p>
      <div class="ic-scroll"><table class="ic-tbl" style="min-width:520px"><thead><tr><th>Indicator</th><th>Latest actual</th><th>IMF projection</th><th>Why it matters</th></tr></thead><tbody>${rows}</tbody></table></div>
      ${bench?`<div class="imf-bench"><div class="ic-bt" style="margin:8px 0 4px">ASEAN external benchmark <span class="s">(${m.peer_bench_year||''} · IMF projection)</span></div>${bench}</div>`:''}
      <p class="lead cc-provenance"><b>Provenance:</b> ${m.label||'IMF World Economic Outlook (DataMapper API).'} Source: ${(m.source||'').split(' (')[0]}. Peers are an external benchmark, not an IPO comp.</p>`;
  });
}

function renderHomeQueue(){
  const box=$('#cc-queue-body'); if(!box) return;
  if(!dqLoaded){ return; }                                   // skeleton stays until the fetch resolves
  // strategy pivot: the network is consolidating, so branch-"expand" actions are not surfaced.
  // build_decision_queue.py no longer EMITS any expand row (consolidation scope), so this filter is
  // now a belt-and-suspenders guard against a stale/hand-edited data file — never trips in practice.
  const items=((DQUEUE&&Array.isArray(DQUEUE.items))?DQUEUE.items:[]).filter(it=>it&&it.type!=='expand');
  if(!items.length){
    box.innerHTML=`<div class="cc-empty">Decision queue not yet computed — run <span class="mono">pipeline/build_decision_queue.py</span>. The ranked weekly actions fill in on the next data refresh.</div>`;
    return;
  }
  box.innerHTML=items.map(it=>{
    const tag=it.basis==='measured'?TAG_M:TAG_E;
    return `<div class="cc-qrow">`+
      `<span class="cc-qnum mono">${it.rank}</span>`+
      `<span class="cc-qchip q-${dqEsc(it.type)}">${dqEsc(it.type)}</span>`+
      `<div class="cc-qtxt">${dqEsc(it.act)}`+
      ` <span class="cc-qmeta">${tag} <span class="sub">· ${dqEsc(it.source)} ·</span> <a data-v="${dqEsc(it.go)}" href="#${dqEsc(it.go)}">${dqEsc(it.go_label||'open →')}</a>${queue3DLink(it)}</span></div></div>`;
  }).join('')+
  `<div class="cc-qfoot sub">Ranking is a stated editorial rule (defend &gt; audit &gt; tighten, then each layer's own magnitude) — see <span class="mono">decision_queue.json</span> meta. Defend rows are measured rival geometry; the rest are estimated screens, not measured outcomes.</div>`;
}

/* ---- home orchestration ---- */
let homeBooted=false;
/* The "Recommendation by region" card was RETIRED 2026-07-25 (consolidation-pivot compliance): its
   per-region actions were grow / product-push ("🌿 Grow farm lending", "🚙 Push vehicle-title") and the
   product makes NO grow/open/expand calls — the same violation, from the same data layer, as the Overview
   "Regional impact & recommendation" cards cut in that batch. DELETED outright 2026-07-31: the retirement
   had left the markup, a renderHomeRegions() stub whose only job was to set display:none, and two call
   sites, so every inventory of this page kept reporting a live card that could never render.
   Do NOT re-add it. regional_outlook.json stays on disk only for its .national headline, which
   renderNationalOutlook() still uses. The front door's pivot-compliant per-region reads are cc-defend
   (competitive risk), the impact strip and the decision queue. */
/* Command-center "Where the network is hardest to defend" card — the per-region density × service
   read (data/rival_threat_region.json, the same MEASURED layer the Competition tab renders), rolled
   onto the front door so the hardest-to-defend regions sit beside the portfolio-risk headline.
   Reuses the RIVTHREATREG global (loaded lazily below). Objective #2. Null-safe: no rows → card hidden. */
function renderHomeDefend(){
  const wrap=$('#cc-defend'), body=$('#cc-defend-body');
  if(!wrap||!body) return;
  const rows=(RIVTHREATREG&&Array.isArray(RIVTHREATREG.regions))?RIVTHREATREG.regions:[];
  if(!rows.length) return;                                   // stay hidden until the fetch resolves
  // class -> theme token (same mapping as the Competition tab): hardest = risk-red, beatable = teal, defensible = gold.
  const cls=t=>{ if(t==='Hardest to defend') return 'var(--agri)';
                 if(t==='Beatable on service') return 'var(--merch)';
                 if(t==='Most defensible') return 'var(--gold)'; return 'var(--dim)'; };
  // hardest-to-defend first, then most-outgunned — lead with the region that needs the most defending.
  const ordered=rows.slice().sort((a,b)=>{
    const hard=x=>x.threat_class==='Hardest to defend'?0:1;
    if(hard(a)!==hard(b)) return hard(a)-hard(b);
    return (b.rivals_vs_autox||0)-(a.rivals_vs_autox||0);
  });
  // SUMMARY, NOT A SECOND COPY. This card used to render EVERY region — the same rows, the same three
  // numbers, as the Competition tab's "Rival threat by region" table, off the same file. Two identical
  // tables one click apart is not an exec summary, it is the reader wondering which one is authoritative.
  // The front door now carries only the regions actually classed hardest to defend (the answer), states
  // how many of how many that is, and hands off. Competition keeps the full per-region table.
  const hard=ordered.filter(r=>r.threat_class==='Hardest to defend');
  // If the classifier flags none, don't show an empty card — fall back to the two most-outgunned.
  const lead=hard.length?hard:ordered.slice(0,2);
  body.innerHTML=lead.map(r=>{
    const c=cls(r.threat_class);
    const ratio=(typeof r.rivals_vs_autox==='number')?r.rivals_vs_autox.toFixed(1)+'×':'—';
    const rating=(typeof r.rating_wavg==='number')?r.rating_wavg.toFixed(2)+'★':'—';
    return `<div class="cc-row">
      <span class="l"><b style="border-left:3px solid ${c};padding-left:7px">${r.region||'—'}</b>
        <span class="s">outgunned ${ratio} · rival service ${rating}${r.thin_rating_sample?' · thin sample':''}</span></span>
      <span class="r" style="color:${c}"><b>${r.threat_class||'—'}</b></span></div>`;
  }).join('')+
  `<div class="sub" style="margin-top:6px;color:var(--dim)"><b>${lead.length}</b> of <b>${ordered.length}</b> regions ${hard.length?'classed hardest to defend':'shown (none classed hardest — most-outgunned instead)'}. Density &amp; service both <b>measured</b> (rival:AutoX census + Google rating sample) — rivals outnumber us in every region, so the class is service-led. All ${ordered.length} regions, with the full numbers → <a class="cc-link no-print" data-v="acq" href="#acq" style="display:inline">Competition</a>.</div>`;
  wrap.style.display='';
}
/* ---------- REAL loan tape · assistance radar (obj #1, MEASURED) ----------
   data/tape_real.json (build_tape_layers.py ← ingest_real_tape.py no-PII aggregates).
   Card is hidden entirely when the layer is absent — calm, never fabricated. */
let TAPE=null, tapePromise=null;
function loadTapeReal(){
  if(tapePromise) return tapePromise;
  tapePromise=(async()=>{
    try{
      const r=await fetch('data/tape_real.json'); if(!r.ok) throw 0;
      const j=await r.json();
      TAPE=(j&&Array.isArray(j.assistance_radar))?j:null;
    }catch(e){ TAPE=null; }
  })();
  return tapePromise;
}
function renderHomeTape(){
  const card=$('#cc-tape'), body=$('#cc-tape-body');
  if(!card||!body) return;
  if(!TAPE||!TAPE.assistance_radar.length){ card.style.display='none'; return; }
  card.style.display='';
  const rows=TAPE.assistance_radar.slice(0,5);
  body.innerHTML=
    `<div class="tblwrap"><table class="tbl"><tr><th>Province</th>
      <th title="X-days bucket: late but under 30dpd — assistance still works. Call this week.">Tier 1 · slipping</th>
      <th title="Current accounts in the same stressed cell — fine today, measured stressor overhead.">Tier 2 · watch</th>
      <th title="share of the province's districts at severe/extreme OAE SPEI">Drought</th>
      <th>What they grow (stressed districts)</th></tr>`+
    rows.map(r=>`<tr>
      <td><b>${r.province}</b> <span class="sub mono">${r.n_farmers.toLocaleString()} farmers</span></td>
      <td class="mono" style="color:var(--gold)"><b>${r.tier1_slipping.toLocaleString()}</b></td>
      <td class="mono">${r.tier2_current_exposed.toLocaleString()}</td>
      <td class="mono" style="color:${r.districts_severe_pct>=60?'var(--agri)':'var(--dim)'}">${r.districts_severe_pct}% <span class="sub">SPEI ${r.worst_spei}</span></td>
      <td class="sub" style="font-size:12px">${(r.stressed_crops||[]).join(' · ')||'—'}</td>
    </tr>`).join('')+`</table></div>`+
    `<div class="sub" style="margin-top:6px;font-size:11px">${TAPE.meta.n_accounts.toLocaleString()} real accounts (no-PII aggregates, cells ≥30) · branch-join ${TAPE.meta.branch_join_pct}% · trigger: drought FIRING, crop-margin & fuel armed · ranking order ESTIMATED over MEASURED inputs</div>`;
}
/* FIVE-PILLAR SUMMARY BAND (owner IA 2026-07-24) — the platform's whole job on one row:
   ① Macro ② Acquisition ③ Assistance ④ Risk ⑤ Competitor. Each card leads with ONE headline
   metric from the committed layers and links to that pillar's detail. Every card is null-safe:
   if its source layer isn't loaded yet it degrades to a calm pointer, never a blank or a lie.
   Re-rendered as TAPE / competitor layers resolve. */
function pillCard(num,name,pc,tab,big,read,foot){
  // `tab` is normally a same-page hash route (data-v the SPA router intercepts); a cross-page
  // URL (e.g. data.html) carries a plain href and NO data-v so the browser navigates natively
  // (the #main-content click delegation only catches a[data-v]).
  const ext=/\.html?(\?|#|$)/.test(tab);
  const nav=ext?`href="${tab}"`:`data-v="${tab}" href="#${tab}"`;
  return `<a class="pill" style="--pc:${pc}" ${nav}>
    <span class="pill-eyebrow"><span class="pill-num">${num}</span><span class="pill-name">${name}</span></span>
    <span class="pill-big">${big||'<small>loading…</small>'}</span>
    <span class="pill-read">${read||''}</span>
    <span class="pill-foot">${foot||''} →</span></a>`;
}
function renderHomePillars(){
  const host=$('#cc-pillars'); if(!host) return;
  const T=TAPE, bn=n=>'฿'+(n/1e9).toFixed(1)+'bn', N=n=>Number(n).toLocaleString();
  const cards=[];

  // ① MACRO — the backdrop moving the book. Prefer live fuel + rate-cap; else a calm pointer.
  let mBig='Macro board', mRead='Commodities, FX &amp; fuel — the forces on the book.';
  if(typeof FUEL!=='undefined'&&FUEL&&FUEL.headline&&FUEL.headline.diesel!=null){
    mBig='฿'+Number(FUEL.headline.diesel).toFixed(2)+'<small>/L diesel</small>';
    mRead='Diesel (pickup/farm borrowers) &amp; the commodity board — the macro forces on collateral values and PD.'; }
  cards.push(pillCard(1,'Macro','var(--accent)','overview',mBig,mRead,'Macro'));

  // ② ACQUISITION — the collateral book &amp; where it concentrates (measured tape).
  if(T&&T.collateral&&T.bucket_ladder){
    const eco=(T.collateral.economics_by_type||[]).slice();
    const top=eco[0], na=T.meta.n_accounts||0;
    const share=top&&na?Math.round(top.n*100/na):null;
    const bc=(T.collateral.branch_brand_concentration||[])[0];
    const book=T.bucket_ladder.book_total?T.bucket_ladder.book_total.os_sum:null;
    cards.push(pillCard(2,'Acquisition','var(--opp)','data.html',
      book?bn(book)+'<small> book</small>':(top?N(top.n)+'<small> '+top.type+'</small>':''),
      (top?`<b>${top.type}</b> ${share}% of accounts · `:'')+
      (bc?`densest branch book: <b>${bc.branch.replace('สาขา','')}</b> ${N(bc.n)} ${bc.brand}`:'collateral concentration by branch, brand &amp; age'),
      'Data book'));
  } else cards.push(pillCard(2,'Acquisition','var(--opp)','data.html','','Where the book concentrates — collateral type, brand &amp; age by branch.','Data book'));

  // ③ ASSISTANCE — the pre-emptive window &amp; who needs help now (measured tape).
  if(T&&T.bucket_ladder){
    const x=T.bucket_ladder.live_book.xdays_n;
    const r0=(T.assistance_radar||[])[0];
    const pe=((T.restructuring&&T.restructuring.by_status)||[]).find(s=>s.status==='Pre-emptive');
    cards.push(pillCard(3,'Assistance','var(--agri)','assist',
      N(x)+'<small> in X-days</small>',
      `Pre-emptive window (late &lt;30dpd). `+
      (r0?`Radar #1: <b>${r0.province}</b>. `:'')+
      (pe?`<b>${N(pe.n)}</b> already pre-emptively restructured (${pe.dpd90p_pct}% at 90+).`:''),
      'Assistance radar'));
  } else cards.push(pillCard(3,'Assistance','var(--agri)','assist','','Who to help pre-emptively, before they roll — by segment &amp; province.','Assistance radar'));

  // ④ RISK — the live-book NPL &amp; the 180+ legacy stock, held separately (measured tape).
  if(T&&T.bucket_ladder){
    const lb=T.bucket_ladder.live_book, lg=T.bucket_ladder.legacy_180plus;
    cards.push(pillCard(4,'Risk','var(--collat)','exposure',
      lb.npl_live_pct+'%<small> NPL-live</small>',
      `90–179dpd on the live book (${lb.npl_live_os_pct}% OS-weighted). Held apart: a <b>${bn(lg.os_sum)}</b> / ${N(lg.n)}-acct 180+ legacy workout stock.`,
      'Risk exposure'));
  } else cards.push(pillCard(4,'Risk','var(--collat)','exposure','','Bucket ladder Current→NPL, live book vs the 180+ legacy stock.','Risk exposure'));

  // ⑤ COMPETITOR — rival pressure on the network we run (measured peer census, lazy).
  let cBig='', cRead='Where rivals outnumber the network — density, contested ground &amp; pulse.';
  if(typeof PEERPROV!=='undefined'&&PEERPROV&&Array.isArray(PEERPROV.provinces)){
    const distOut=PEERPROV.provinces.reduce((s,p)=>s+(p&&p.n_outnumbered_districts||0),0);
    if(distOut){ cBig=N(distOut)+'<small> districts</small>';
      cRead='where the big-4 out-number the existing network (measured per-district rival density).'; }
  }
  cards.push(pillCard(5,'Competitor','var(--merch)','acq',cBig,cRead,'Competition'));

  host.innerHTML=cards.join('');
}
/* ③ ASSISTANCE VIEW — the "who needs help now" page (owner ask: where are the segments hit most
   and needing assistance). Reads data/tape_real.json: segments-hit-most ranked hit-list +
   X-days pre-emptive window (drought radar) + restructuring (Normal / Pre-emptive / TDR — did it
   hold?). Null-safe: calm note when the tape layer is absent. */
function assistSev(v){ // color a 90+ rate
  if(v==null) return 'var(--dim)';
  if(v<8) return 'var(--merch)';
  if(v<14) return '#9CB24E';
  if(v<20) return 'var(--gold)';
  if(v<26) return '#D97A3A';
  return 'var(--agri)';
}
/* Geography × occupation drill (owner ask 2026-07-28): geography-first — regions → provinces →
   branches, the occupation mix INSIDE each level. Every occupation cell carries an at-risk triage
   (Current / X-days assist window / rolling 30–89 / already at risk 90+) and the expected income
   impact joined from the income engine. Region + province cells MEASURED (≥30 floor); branch cells
   MEASURED where the branch×occupation cell clears the floor, thin residual ESTIMATED from the
   province occupation mix (chip: EST). Reads data/tape_geo_occ.json + data/income_impact.json. */
const AOD_SES={'เกษตร':'Agriculture','รับจ้างทั่วไป':'FactoryWorkers','พนักงานบริษัท':'OfficeStaff',
  'ข้าราชการ':'OfficeStaff','กลุ่มวิชาชีพ':'OfficeStaff','ค้าขาย':'SMEOwners',
  'ผู้ประกอบการ':'SMEOwners','ธุรกิจเฉพาะ':'SMEOwners','บริการ':'SMEOwners',
  'แม่บ้าน/ว่างงาน':'HomeUnemployed'};
/* book-weighted Δincome per tape occupation over a province set (weights = province occ accounts) */
function aodIncomeMap(inc,geo,provFilter){
  if(!inc||!inc.provinces) return {};
  const pairs=Array.isArray(inc.provinces)?inc.provinces:Object.entries(inc.provinces);
  const acc={};
  pairs.forEach(pr=>{
    const pname=pr[0], rec=pr[1]||{};
    if(provFilter&&!provFilter(pname,rec)) return;
    ((geo.provinces||{})[pname]||[]).forEach(c=>{
      const ses=AOD_SES[c.occupation]; const io=ses&&(rec.occ||{})[ses];
      if(!io||io.d_pct==null) return;
      const a=acc[c.occupation]||(acc[c.occupation]={w:0,dp:0,db:0,inc:0,incw:0,lfs:0});
      a.w+=c.n; a.dp+=io.d_pct*c.n; a.db+=(io.d_baht||0)*c.n;
      if(io.income){ a.inc+=io.income*c.n; a.incw+=c.n; if(io.base_src==='lfs_region') a.lfs+=c.n; }
    });
  });
  const out={};
  Object.keys(acc).forEach(o=>{const a=acc[o];
    if(a.w>0) out[o]={d_pct:+(a.dp/a.w).toFixed(2),d_baht:Math.round(a.db/a.w),
      income:a.incw?Math.round(a.inc/a.incw):null,
      base_src:(a.incw&&a.lfs>a.incw/2)?'lfs_region':'ses'};});
  return out;
}
/* THB amount at the right magnitude: billions above ฿1bn, millions above ฿1m, else comma-grouped.
   (owner ask 2026-07-28: "฿11208m" is unreadable — it is ฿11.21bn.) */
function aodTHB(v){
  if(v==null) return '<span class="s">—</span>';
  if(v>=1e9) return '฿'+(v/1e9).toFixed(2)+'bn';
  if(v>=1e6) return '฿'+icN(+(v/1e6).toFixed(0))+'m';
  return '฿'+icN(Math.round(v));
}
/* income level (NSO base) and the modelled ฿ move — the owner reads baht, not coefficients */
function aodIncome(d){
  if(!d||d.income==null) return '<span class="s" title="no published income base for this group — NSO SES has no province row and the LFS has no matching employee category">—</span>';
  const lab=d.base_src==='lfs_region'?'NSO LFS employee wage (region) — ESTIMATED base at province grain'
    :'NSO SES individual income (province) — MEASURED base';
  return `<span title="${lab}">฿${icN(d.income)}<span class="s">/mo</span></span>`;
}
function aodImpact(d){
  if(!d) return '<span class="s">—</span>';
  if(d.d_baht==null||!d.income) return `<span class="s" title="no income base to apply the move to — no change modelled for this group">no change modelled</span>`;
  const up=d.d_baht>0, flat=d.d_baht===0;
  const c=flat?'var(--dim)':up?'var(--merch)':'var(--agri)';
  if(flat) return `<b style="color:${c}" title="no macro channel reaches this occupation's income in the short run (salaried / transfer income)">฿0</b>`;
  return `<b style="color:${c}" title="expected monthly income move — income engine, ESTIMATED first-order (${d.d_pct>0?'+':''}${d.d_pct}%)">${up?'+':'−'}฿${icN(Math.abs(d.d_baht))}<span class="s">/mo</span></b>`;
}
function aodDelta(d){ if(!d) return '<span class="s" title="not modelled — the income engine has no province-level income base for this occupation group">—</span>';
  const c=d.d_pct>0?'var(--merch)':d.d_pct<0?'var(--agri)':'var(--dim)';
  const baht=d.d_baht!=null?` (≈฿${icN(Math.abs(d.d_baht))}/mo)`:'';
  return `<b style="color:${c}" title="expected income move for this occupation here — income-impact engine, ESTIMATED first-order${baht}">${d.d_pct>0?'+':''}${d.d_pct}%</b>`;}
function aodBasis(b){ return b==='estimated'
  ?'<span class="aod-est" title="thin cell — fewer than 30 accounts measured at this branch, so the split is ESTIMATED: allocated from the province occupation mix, delinquency rates inherited from that province cell">EST</span>':''; }
/* merge measured occ cells across geographies into one occupation table (for the All-book level) */
function aodAgg(cellLists){
  const m={};
  cellLists.forEach(cells=>(cells||[]).forEach(c=>{
    const a=m[c.occupation]||(m[c.occupation]={occupation:c.occupation,basis:'measured',n:0,os_sum:0,
      _np:0,n_current:0,n_watch_xdays:0,n_rolling_3089:0,n_at_risk_90p:0});
    a.n+=c.n; a.os_sum+=c.os_sum; a._np+=c.npat_margin_avg*c.n;
    a.n_current+=c.n_current; a.n_watch_xdays+=c.n_watch_xdays;
    a.n_rolling_3089+=c.n_rolling_3089; a.n_at_risk_90p+=c.n_at_risk_90p;
  }));
  return Object.keys(m).map(k=>{const a=m[k]; a.npat_margin_avg=Math.round(a._np/a.n); return a;})
    .sort((x,y)=>y.n-x.n);
}
function aodSummary(cells){
  const s=(cells||[]).reduce((a,c)=>{a.n+=c.n;a.w+=c.n_watch_xdays;a.r+=c.n_at_risk_90p;return a;},{n:0,w:0,r:0});
  return `<p class="lead" style="margin:6px 0 4px"><b style="color:var(--gold)">${icN(s.w)}</b> need pre-emptive help now (X-days) · <b style="color:var(--agri)">${icN(s.r)}</b> already at risk (90+) · of <b>${icN(s.n)}</b> accounts</p>`;
}
function aodOccTable(cells,inc){
  if(!cells||!cells.length) return '<p class="lead sub">No occupation cells cleared the ≥30-account floor here.</p>';
  const rows=cells.map(c=>{
    const riskPct=c.n?+(c.n_at_risk_90p*100/c.n).toFixed(1):0;
    return `<tr>
      <td><b>${c.occupation}</b>${aodBasis(c.basis)}</td>
      <td class="mono">${icN(c.n)}</td>
      <td class="mono sub" title="outstanding balance">${aodTHB(c.os_sum)}</td>
      <td class="mono" style="color:var(--merch)">${icN(c.n_current)}</td>
      <td class="mono" style="color:var(--gold)"><b>${icN(c.n_watch_xdays)}</b></td>
      <td class="mono" style="color:#D97A3A">${icN(c.n_rolling_3089)}</td>
      <td class="mono"><b style="color:${assistSev(riskPct)}">${icN(c.n_at_risk_90p)}</b> <span class="s">${riskPct}%</span></td>
      <td class="n">${aodDelta(inc[c.occupation])}</td></tr>`;
  }).join('');
  return `<div class="tbl-wrap"><table class="tbl"><tr>
    <th>Occupation</th><th>Accounts</th><th>OS</th>
    <th title="0 dpd — healthy">Current</th>
    <th title="late but under 30dpd — the pre-emptive assistance window: call these first">X-days · assist</th>
    <th title="30–89dpd roll pipeline — recoverable middle">Rolling</th>
    <th title="90+dpd incl. the 180+ legacy — already at risk">At risk 90+</th>
    <th title="expected income impact for this occupation here — income engine, ESTIMATED first-order">Δ income</th></tr>${rows}</table></div>`;
}
/* The ranked hit-list follows the drill (owner ask 2026-07-28: "the table below should change with
   the drill level — it seems static"). Same ordering as the builder's segments_hit score
   (90+% + ½·30–89% + ¼·X-days%) but recomputed for whatever geography is open, from the same
   measured cells the drill is showing. */
function aodSyncHitList(scope,cells){
  const host=$('#assist-segments'); if(!host) return;
  const rows=(cells||[]).filter(c=>c.n>=30).map(c=>{
    const e=c.n?c.n_watch_xdays*100/c.n:0, r=c.n?c.n_rolling_3089*100/c.n:0,
          d=c.n?c.n_at_risk_90p*100/c.n:0;
    return {occ:c.occupation,basis:c.basis,n:c.n,os:c.os_sum,e:e,r:r,d:d,
            score:+(d+0.5*r+0.25*e).toFixed(2)};
  }).sort((a,b)=>b.score-a.score||b.n-a.n);
  host.innerHTML=`<div class="ic-drill-h" style="margin:0 0 6px">Ranked for <b>${scope}</b> — worst blend of 90+ severity, roll pressure and X-days slippage</div>`+
    (rows.length?`<table class="tbl"><tr>
      <th>Occupation</th><th>Accounts</th><th>OS</th>
      <th title="90+dpd share">90+</th><th title="30–89dpd roll">Roll</th>
      <th title="X-days slipping">X-days</th><th title="90+% + ½·roll% + ¼·X-days%">Score</th></tr>`+
      rows.map(x=>`<tr>
        <td><b>${x.occ}</b>${aodBasis(x.basis)}</td>
        <td class="mono">${icN(x.n)}</td><td class="mono sub">${aodTHB(x.os)}</td>
        <td class="mono"><b style="color:${assistSev(x.d)}">${x.d.toFixed(2)}%</b></td>
        <td class="mono">${x.r.toFixed(2)}%</td>
        <td class="mono" style="color:var(--opp)">${x.e.toFixed(2)}%</td>
        <td class="mono"><b>${x.score}</b></td></tr>`).join('')+`</table>`
    :`<p class="lead sub">No occupation cell here clears the ≥30-account floor.</p>`);
  wrapTables();
}
function aodRenderLevel(mount){
  const st=mount._aodState, geo=mount._aodGeo, inc=mount._aodInc;
  const provReg={};
  (geo.branches||[]).forEach(b=>{ if(b.prov&&b.region&&!provReg[b.prov]) provReg[b.prov]=b.region; });
  const incPairs=(inc&&inc.provinces)?(Array.isArray(inc.provinces)?inc.provinces:Object.entries(inc.provinces)):[];
  incPairs.forEach(pr=>{
    if(!provReg[pr[0]]&&(pr[1]||{}).region) provReg[pr[0]]=pr[1].region; });
  if(st.level==='province'){
    const cells=(geo.regions||{})[st.region]||[];
    const provs=Object.keys(geo.provinces||{}).filter(p=>provReg[p]===st.region)
      .map(p=>{const cs=geo.provinces[p];
        const s=cs.reduce((a,c)=>{a.n+=c.n;a.w+=c.n_watch_xdays;a.r+=c.n_at_risk_90p;return a;},{n:0,w:0,r:0});
        return {p,n:s.n,w:s.w,r:s.r,top:cs[0]?cs[0].occupation:'—'};})
      .sort((a,b)=>b.w-a.w);
    mount.innerHTML=icCrumb([{label:'All regions',lvl:'regions'},{label:st.region}])+
      aodSummary(cells)+aodOccTable(cells,aodIncomeMap(inc,geo,(p,rec)=>provReg[p]===st.region))+
      `<div class="ic-drill-h" style="margin-top:10px"><b>${st.region}</b> — ${provs.length} provinces, biggest pre-emptive workload first · press a province for its occupation mix + branches</div>`+
      `<div class="tbl-wrap"><table class="tbl"><tr><th>Province</th><th>Accounts</th><th>Top occupation</th><th>X-days · assist</th><th>At risk 90+</th><th></th></tr>`+
      provs.map(r=>`<tr class="aod-row" data-p="${r.p}" tabindex="0" role="link">
        <td><b>${r.p}</b></td><td class="mono">${icN(r.n)}</td><td>${r.top}</td>
        <td class="mono" style="color:var(--gold)"><b>${icN(r.w)}</b></td>
        <td class="mono" style="color:${assistSev(r.n?+(r.r*100/r.n).toFixed(1):0)}">${icN(r.r)}</td>
        <td class="n"><span class="ic-chev">›</span></td></tr>`).join('')+`</table></div>`;
    aodSyncHitList(st.region,cells);
    return;
  }
  if(st.level==='branch'){
    const cells=(geo.provinces||{})[st.province]||[];
    const brs=(geo.branches||[]).filter(b=>b.prov===st.province)
      .map(b=>{const meas=b.occs.filter(c=>c.basis==='measured').length, est=b.occs.length-meas;
        return {b,meas,est,w:Math.round(b.n*(b.early_pct||0)/100),r:Math.round(b.n*(b.dpd90p_pct||0)/100)};})
      .sort((a,b)=>b.w-a.w);
    mount.innerHTML=icCrumb([{label:'All regions',lvl:'regions'},{label:provReg[st.province]||'—',lvl:'province'},{label:st.province}])+
      aodSummary(cells)+aodOccTable(cells,aodIncomeMap(inc,geo,p=>p===st.province))+
      `<div class="ic-drill-h" style="margin-top:10px"><b>${st.province}</b> — ${brs.length} branches on the tape (n ≥ 30), biggest pre-emptive workload first · press a branch for its occupation split</div>`+
      `<div class="tbl-wrap"><table class="tbl"><tr><th>Branch</th><th>Accounts</th><th title="occupation cells: measured ≥30 / estimated from the province mix">Split basis</th><th>X-days · assist</th><th>At risk 90+</th><th></th></tr>`+
      brs.map(x=>`<tr class="aod-row" data-b="${x.b.branch}" tabindex="0" role="link">
        <td><b>${x.b.branch}</b></td><td class="mono">${icN(x.b.n)}</td>
        <td class="n">${x.meas} measured${x.est?` · <span style="color:var(--gold)">${x.est} est</span>`:''}</td>
        <td class="mono" style="color:var(--gold)"><b>${icN(x.w)}</b></td>
        <td class="mono" style="color:${assistSev(x.b.dpd90p_pct)}">${icN(x.r)}</td>
        <td class="n"><span class="ic-chev">›</span></td></tr>`).join('')+`</table></div>`;
    aodSyncHitList(st.province,cells);
    return;
  }
  if(st.level==='occs'){
    const rec=(geo.branches||[]).find(b=>b.branch===st.branch);
    if(!rec){ mount._aodState={level:'regions'}; return aodRenderLevel(mount); }
    const est=rec.occs.filter(c=>c.basis==='estimated');
    mount.innerHTML=icCrumb([{label:'All regions',lvl:'regions'},{label:rec.region||'—',lvl:'province'},{label:rec.prov||'—',lvl:'branch'},{label:rec.branch}])+
      aodSummary(rec.occs)+aodOccTable(rec.occs,aodIncomeMap(inc,geo,p=>p===rec.prov))+
      (est.length?`<p class="lead sub" style="margin:4px 0 0"><span class="aod-est">EST</span> rows: this branch's cells under the 30-account floor, allocated from the <b>${rec.prov}</b> occupation mix with that province-cell's delinquency rates — an honest estimate, not a measurement.</p>`:'');
    aodSyncHitList(rec.branch,rec.occs);
    return;
  }
  const regs=Object.keys(geo.regions||{}).map(reg=>{
    const cs=geo.regions[reg];
    const s=cs.reduce((a,c)=>{a.n+=c.n;a.w+=c.n_watch_xdays;a.r+=c.n_at_risk_90p;return a;},{n:0,w:0,r:0});
    return {reg,n:s.n,w:s.w,r:s.r,top:cs[0]?cs[0].occupation:'—'};
  }).sort((a,b)=>b.w-a.w);
  const all=aodAgg(Object.keys(geo.regions||{}).map(r=>geo.regions[r]));
  const cov=((geo.meta||{}).cells||{});
  aodSyncHitList('the whole book',all);
  mount.innerHTML=
    aodSummary(all)+aodOccTable(all,aodIncomeMap(inc,geo,null))+
    `<div class="ic-drill-h" style="margin-top:10px">Drill in — press a region → its provinces → its branches (biggest pre-emptive workload first)</div>`+
    `<div class="aod-regs">`+regs.map(r=>`<button type="button" class="mcard aod-reg" data-reg="${r.reg}" aria-label="Drill into ${r.reg}">
      <div class="k">${r.reg}</div><div class="v">${icN(r.n)}</div>
      <div class="n">top: ${r.top} · <b style="color:var(--gold)">${icN(r.w)}</b> assist · <b style="color:var(--agri)">${icN(r.r)}</b> at risk</div>
      <span class="ic-chev">›</span></button>`).join('')+`</div>`+
    `<p class="lead sub" style="margin:4px 0 0">Coverage: ${icN(cov.measured_branch)} branch×occupation cells <b>measured</b> (≥30 accounts) · ${icN(cov.estimated_branch)} thin cells <b>estimated</b> from province mixes. Region and province tables are fully measured.</p>`;
}
/* Occupation × macro panel (owner ask 2026-07-28): BEFORE the geographic drill — every occupation
   group in the book, the macro channel that reaches its income (sensitivity coefficients from the
   engine's documented matrix), and the expected book-weighted income move. Sets the "why" so the
   geographic "where" drill below reads in context. */
function aodChannel(sens){
  if(!sens) return '<span class="s">—</span>';
  if(!sens.crop&&!sens.fuel) return '<span class="s" title="no crop or fuel pass-through modelled — salaried / transfer income is fixed in the short run">no short-run channel</span>';
  const bits=[];
  if(sens.crop) bits.push(`<span style="color:var(--merch)" title="fraction of a crop-price move that reaches take-home income (documented first-order assumption)">crop ×${sens.crop}</span>`);
  if(sens.fuel) bits.push(`<span style="color:${sens.fuel<0?'var(--agri)':'var(--merch)'}" title="fraction of a fuel-cost move that reaches take-home income (negative = cost)">fuel ×${sens.fuel}</span>`);
  return bits.join(' · ');
}
function renderAssistOccMacro(){
  const mount=document.getElementById('assist-occ-macro'); if(!mount) return;
  Promise.all([tmliFetch('tape_geo_occ'),tmliFetch('income_impact')]).then(([geo,inc])=>{
    if(!geo||!geo.regions){ tmliNote(mount,'Occupation panel not yet computed — <b>data/tape_geo_occ.json</b> is absent (run pipeline/build_tape_layers.py after the tape ingest).'); return; }
    const all=aodAgg(Object.keys(geo.regions||{}).map(r=>geo.regions[r]));
    const dmap=aodIncomeMap(inc,geo,null);
    const sens=((inc||{}).meta||{}).sensitivity||{};
    const drv=((inc||{}).meta||{}).drivers||{};
    const tot=all.reduce((a,c)=>a+c.n,0);
    const cy=drv.crop_yoy_pct||{};
    const chips=[['Rice',cy.rice],['Rubber',cy.rubber],['Palm',cy.oilpalm]]
      .filter(x=>x[1]!=null)
      .map(x=>`<span class="ic-cchip ${x[1]<0?'bad':x[1]>0?'good':'flat'}">${x[0]} ${x[1]>0?'+':''}${x[1]}%</span>`).join('')+
      `<span class="ic-cchip ${drv.fuel_move_pct<0?'good':drv.fuel_move_pct>0?'bad':'flat'}" title="${drv.fuel_basis||''}">Fuel ${drv.fuel_move_pct>0?'+':''}${drv.fuel_move_pct!=null?drv.fuel_move_pct:'—'}%</span>`;
    mount.innerHTML=
      `<div style="margin:2px 0 8px">${chips}</div>`+
      `<div class="tbl-wrap"><table class="tbl"><tr>
        <th>Occupation</th><th>Accounts</th><th title="share of occupation-attributed accounts">% of book</th>
        <th title="monthly income base — NSO SES individual income where published, otherwise the region's NSO LFS employee wage">Income · NSO</th>
        <th title="expected monthly income move from the current crop/fuel price moves — book-weighted across provinces, ESTIMATED first-order">Est. impact to income</th></tr>`+
      all.map(c=>`<tr>
          <td><b>${c.occupation}</b></td>
          <td class="mono">${icN(c.n)}</td>
          <td class="mono sub">${tot?(c.n*100/tot).toFixed(1):'—'}%</td>
          <td class="mono">${aodIncome(dmap[c.occupation])}</td>
          <td class="mono">${aodImpact(dmap[c.occupation])}</td></tr>`).join('')+`</table></div>`;
    wrapTables();
  });
}
function renderAssistOcc(){
  const mount=document.getElementById('assist-occ'); if(!mount) return;
  Promise.all([tmliFetch('tape_geo_occ'),tmliFetch('income_impact')]).then(([geo,inc])=>{
    if(!geo||!geo.regions){ tmliNote(mount,'Occupation drill not yet computed — <b>data/tape_geo_occ.json</b> is absent (run pipeline/build_tape_layers.py after the tape ingest).'); return; }
    mount._aodGeo=geo; mount._aodInc=inc;
    if(!mount._aodState) mount._aodState={level:'regions'};
    aodRenderLevel(mount);
    if(!mount.dataset.aodWired){
      mount.dataset.aodWired='1';
      const go=st=>{mount._aodState=st; aodRenderLevel(mount); mount.scrollIntoView({block:'nearest'}); icFocusLevel(mount);};
      const act=t=>{
        const back=t.closest('.ic-back');
        if(back){const st=mount._aodState, lvl=back.dataset.lvl;
          if(lvl==='branch') go({level:'branch',province:st.level==='occs'?(mount._aodGeo.branches.find(b=>b.branch===st.branch)||{}).prov:st.province});
          else if(lvl==='province'){
            const st2=mount._aodState; let reg=st2.region;
            if(!reg){const rec=st2.branch&&mount._aodGeo.branches.find(b=>b.branch===st2.branch);
              reg=(rec&&rec.region)||provRegOf(mount,st2.province);}
            go({level:'province',region:reg});
          } else go({level:'regions'});
          return true;}
        const reg=t.closest('.aod-reg'); if(reg){go({level:'province',region:reg.dataset.reg}); return true;}
        const row=t.closest('.aod-row');
        if(row){ if(row.dataset.p) go({level:'branch',province:row.dataset.p,region:(mount._aodState||{}).region});
                 else if(row.dataset.b) go({level:'occs',branch:row.dataset.b}); return true;}
        return false;
      };
      mount.addEventListener('click',e=>{act(e.target);});
      mount.addEventListener('keydown',e=>{
        if(e.key!=='Enter'&&e.key!==' '&&e.key!=='Spacebar') return;
        const row=e.target.closest&&e.target.closest('.aod-row');
        if(!row||row!==e.target) return;
        e.preventDefault(); act(row);
      });
    }
  });
}
function provRegOf(mount,prov){
  const b=(mount._aodGeo.branches||[]).find(x=>x.prov===prov);
  return b?b.region:null;
}
/* PROACTIVE ASSIST · PRICE LENS (owner ask #4) — data/assist_price_radar.json.
   The drought radar above answers "who is slipping now". This answers the forward question: which
   crop price, if it turned, would put the most CURRENTLY-HEALTHY farm accounts at risk. Every crop
   with province-level exposure is up YoY today, so `tripped` is empty — and rather than print an
   empty box, the panel leads with the exposure that is real today (how much of the healthy farm book
   rides on each price) and states the trip rule so the empty state is legible rather than mysterious.
   Null-safe: absent layer → a calm note, never a broken table. */
function priceDirColor(d){ return d==='down'?'var(--agri)':d==='up'?'var(--merch)':'var(--muted)'; }
/* CROP MIX → FARM INCOME (data/crop_mix.json). The correction this section leads with: weighting
   ALL EIGHT priced crops by province area, farm income is not rising everywhere. The prior engine
   weighted rice/rubber/oilpalm only — all three up — so it reported all 77 provinces rising and was
   structurally blind to coconut, sugarcane and pineapple. Four provinces are negative and they carry
   real book. Null-safe: absent layer → nothing renders. */
/* ================= GEO DRILL — one component, every table on this tab =================
   Owner directive (2026-08-02, point 13): "All provinces, roll up into regional summaries, roll up
   into national summary. This type of format can be used to analyze impact by branch, by province,
   and by region for AutoX."

   A top-10 list answers the CEO's question and none of the branch team's. This is the same number at
   four grains — national → region → all provinces → our branches — with ONE level on screen at a
   time. That is what lets a table carry 77 provinces without costing 77 rows of scroll: the summary
   is what you present, the branch rows are what someone works on Monday.

   Deliberately generic. Every table in Waves B and C adopts it by passing a different `cols` and a
   different `data`, so the drill behaviour is written once and cannot diverge between sections.

   cfg = {
     id      unique mount id (state is kept per id)
     data    {national, regions:{}, provinces:{}, branches:{}}  — the farm_book.json shape
     rank    numeric field every level is sorted by, descending (the "size" of the row)
     cols    [{k, lab, fmt, cls, title, lev}]  lev omitted = all levels; 'p' = province only
     bcols   column set for the branch level (defaults to cols minus province-only ones)
     label   optional (row, key) => extra HTML appended to the geo name cell
     act     optional (state, rows) => an action sentence rendered above the table
   }
   External data is province-grain for most sources: DLT, NSO and DBD publish nothing per branch. So
   the branch level always shows OUR book's numbers joined to the province's signal — never a fake
   branch-level external figure. */
const GEO_ST={};
function geoFmt(v,f){
  if(v==null||v===''||(typeof v==='number'&&!isFinite(v))) return '<span class="gd-na">—</span>';
  const n=Number(v);
  switch(f){
    case 'baht':  return '฿'+Math.round(n).toLocaleString('en-US');
    case 'bahtM': return n>=1e9?'฿'+(n/1e9).toFixed(2)+'bn':'฿'+Math.round(n/1e6).toLocaleString('en-US')+'m';
    case 'num':   return Math.round(n).toLocaleString('en-US');
    case 'pct':   return n.toFixed(1)+'%';
    case 'pctS':  return (n>0?'+':n<0?'−':'')+Math.abs(n).toFixed(1)+'%';
    case 'bahtS': return (n>0?'+':n<0?'−':'')+'฿'+Math.abs(Math.round(n)).toLocaleString('en-US');
    default:      return String(v);
  }
}
function geoTone(v,cls){
  if(cls!=='sgn'||v==null) return '';
  return ' style="color:'+(Number(v)<0?'var(--agri)':'var(--merch)')+'"';
}
function geoDrill(host,cfg){
  if(!host) return;
  const D=cfg.data||{}, R=D.regions||{}, P=D.provinces||{}, B=D.branches||{};
  const ST=GEO_ST[cfg.id]||(GEO_ST[cfg.id]={lev:'nat',reg:null,prov:null});
  const rank=cfg.rank;

  function rowsFor(){
    if(ST.lev==='nat')  return Object.entries(R).map(([k,v])=>({key:k,v,kind:'reg'}));
    if(ST.lev==='reg')  return Object.entries(P).filter(([,v])=>v.region===ST.reg).map(([k,v])=>({key:k,v,kind:'prov'}));
    return (B[ST.prov]||[]).map(b=>({key:b.name,v:b,kind:'branch'}));
  }
  function draw(){
    const rows=rowsFor().sort((a,b)=>(Number(b.v[rank])||0)-(Number(a.v[rank])||0));
    // `lev` scopes a column to the rows it actually has data for: 'p' = only when PROVINCE rows are
    // listed, 'r' = only when REGION rows are. Without this a region-only field (a mix share the tape
    // publishes at region grain but not province grain) would render as a column of em-dashes on the
    // province list, which reads as missing data rather than as a different grain.
    const cols=(ST.lev==='reg'?cfg.cols.filter(c=>c.lev!=='r')
               :(ST.lev==='nat'?cfg.cols.filter(c=>c.lev!=='p')
               :(cfg.bcols||cfg.cols.filter(c=>c.lev!=='p'&&c.lev!=='r'))));
    const geoLab={nat:'Region',reg:'Province',branch:'Branch'}[ST.lev]||'';
    const crumb=`<nav class="gd-crumb" aria-label="Drill level">`
      +`<button type="button" data-go="nat"${ST.lev==='nat'?' class="on" aria-current="true"':''}>National</button>`
      +(ST.reg?`<span>›</span><button type="button" data-go="reg"${ST.lev==='reg'?' class="on" aria-current="true"':''}>${ST.reg}</button>`:'')
      +(ST.prov?`<span>›</span><button type="button" data-go="branch" class="on" aria-current="true">${ST.prov}</button>`:'')
      +`</nav>`;
    // The national row is always visible as a <tfoot>-style banner, so a reader three levels deep
    // never loses the denominator the row they are looking at is a share OF.
    const N=D.national||{};
    const natline=`<div class="gd-nat">${(cfg.natCols||cfg.cols.filter(c=>c.lev!=='p')).map(c=>
        `<span><i>${c.lab}</i>${geoFmt(N[c.k],c.fmt)}</span>`).join('')}</div>`;
    const head=`<tr><th scope="col">${geoLab}</th>`
      +cols.map(c=>`<th scope="col" class="gd-r"${c.title?` title="${c.title}"`:''}>${c.lab}</th>`).join('')+`</tr>`;
    const body=rows.map(r=>{
      const drill=r.kind!=='branch';
      const extra=cfg.label?cfg.label(r.v,r.key,r.kind):'';
      return `<tr${drill?` class="gd-go" data-k="${String(r.key).replace(/"/g,'&quot;')}" data-kind="${r.kind}" tabindex="0" role="link"`:''}>`
        +`<td class="gd-geo">${r.key}${drill?'<span class="gd-ar">›</span>':''}${extra}</td>`
        +cols.map(c=>`<td class="gd-r ${c.cls||''}"${geoTone(r.v[c.k],c.cls)}>${c.fmt==='raw'&&cfg.cell?cfg.cell(c.k,r.v):geoFmt(r.v[c.k],c.fmt)}</td>`).join('')
        +`</tr>`;
    }).join('');
    const act=cfg.act?cfg.act(ST,rows):'';
    host.innerHTML=crumb+natline+(act?`<div class="gd-act">${act}</div>`:'')
      +`<div class="tblwrap gd-wrap"><table class="tbl gd-tbl">${head}${body}</table></div>`
      +`<p class="gd-foot">${rows.length} ${ST.lev==='nat'?'regions':ST.lev==='reg'?'provinces':'branches'}${ST.lev!=='branch'?' — click a row to go deeper':''}${cfg.foot?' · '+cfg.foot:''}${(ST.lev==='branch'&&cfg.bfoot&&cfg.bfoot(ST))?' · '+cfg.bfoot(ST):''}</p>`;
    wrapTables&&wrapTables();
  }
  host.onclick=e=>{
    const go=e.target.closest('[data-go]');
    if(go){ const l=go.dataset.go; ST.lev=l; if(l==='nat'){ST.reg=null;ST.prov=null;} if(l==='reg')ST.prov=null; draw(); return; }
    const tr=e.target.closest('tr.gd-go'); if(!tr) return;
    if(tr.dataset.kind==='reg'){ ST.lev='reg'; ST.reg=tr.dataset.k; ST.prov=null; }
    else { ST.lev='branch'; ST.prov=tr.dataset.k; }
    draw();
  };
  host.onkeydown=e=>{
    if(e.key!=='Enter'&&e.key!==' ') return;
    const tr=e.target.closest&&e.target.closest('tr.gd-go'); if(!tr||tr!==e.target) return;
    e.preventDefault(); tr.click();
  };
  draw();
}

/* ================= THE FARM BLOCK — one table where there were four =================
   Replaces: the crop-mix panel + its 77-bar rank strip (owner: "doesn't give much utility apart
   from looking cool"), the crop-household stress table, and the `agri_stress` 0-100 composite
   (owner: "an estimated measure that has been made up. Difficult to relate.").

   Ranked by BAHT, which is what he chose over the index — and the choice immediately earned itself:
   counting accounts said 17,287 were exposed to a falling crop mix; counting baht says ฿213m, 3% of
   the book, and shows that the two provinces with the catastrophic crop moves carry almost no farm
   lending at all. The alarm was an artefact of the unit.

   The "what is driving it" column is the fix for the contradiction he caught: it used to name the
   biggest DRAG under a heading promising the biggest DRIVER, so ร้อยเอ็ด read "Sugarcane 5% of land"
   while rice — 91.7% of the land — supplied +11.4pp of its +11.8% move. Now the mix is ranked by
   absolute contribution and the drag is named as a drag. */
function renderFarmBook(){
  const host=document.getElementById('cropmix-wrap'); if(!host) return;
  tmliFetch('farm_book').then(j=>{
    if(!j||!j.national||!j.provinces){ host.style.display='none'; return; }
    host.style.display='';
    const N=j.national, num=n=>Number(n).toLocaleString('en-US');
    const bn=v=>'฿'+(v/1e9).toFixed(2)+'bn', m=v=>'฿'+Math.round(v/1e6).toLocaleString('en-US')+'m';
    const risePct=N.neg_share_of_os_pct==null?null:(100-N.neg_share_of_os_pct).toFixed(0);

    // The crop that MOVED the book is not the crop that IS the book. Name it in the commentary —
    // it is the single most counter-intuitive line in this section and a reader will not derive it
    // from the table.
    const CR=(j.crops||[]).slice();
    const big=CR.slice().sort((a,b)=>b.farm_os_alloc-a.farm_os_alloc)[0];
    const mov=CR.slice().sort((a,b)=>b.pp_of_book-a.pp_of_book)[0];
    const drg=CR.slice().sort((a,b)=>a.pp_of_book-b.pp_of_book)[0];
    const cropLine=(big&&mov&&drg&&mov.crop!==big.crop)
      ? ` <b>${big.en} is ${big.os_share_pct}% of the book, but ${mov.en.toLowerCase()} is what moved it</b> — on half ${big.en.toLowerCase()}'s share of the book, ${mov.en.toLowerCase()} contributed <b style="color:var(--merch)">+${mov.pp_of_book.toFixed(1)}pp</b> against ${big.en.toLowerCase()}'s +${big.pp_of_book.toFixed(1)}pp, because it is ${mov.yoy>0?'+':''}${mov.yoy}% YoY. The only material drag is <b style="color:var(--agri)">${drg.en.toLowerCase()} at ${drg.pp_of_book.toFixed(1)}pp</b>.`
      : '';

    host.innerHTML=`<h3 class="ovsub risk">Farm book — where the crop mix meets our money
        <span class="tag" style="color:var(--merch);border:1px solid var(--merch)">MEASURED exposure</span></h3>
      <div class="verdict"><b>${risePct}% of the ${bn(N.farm_os)} farm book sits in provinces whose crop mix is rising.</b>
        Weighted by the farm book itself across all eight priced crops, the move is <b style="color:var(--merch)">+${N.farm_weighted_mix_pct}%</b>.
        Only <b>${N.neg_provinces} provinces</b> are falling and they hold <b>${m(N.neg_farm_os)}</b> — ${N.neg_share_of_os_pct}% of the book, ${num(N.neg_farm_n)} accounts, of which <b>${num(N.neg_current)} are still Current</b>.
        The two steepest crop falls in the country carry almost no farm lending, so the headline collapse is not a portfolio event.${cropLine}
        <span class="sub">Ranked by outstanding baht, not by an index — that is what makes the distinction visible.
        Weighting by farm baht (+${N.farm_weighted_mix_pct}%) differs from weighting by every book account (+${N.book_weighted_mix_pct}%): farm lending is not spread like the book.</span></div>
      <div id="fb-drill"></div>
      <div id="fb-crops"></div>`;

    const drivers=v=>{
      const d=v.drivers||[]; if(!d.length) return '<span class="gd-na">—</span>';
      return d.map(c=>`<span class="fb-crop"><b>${c.crop}</b> ${c.share}%<i${c.pp<0?' class="dn"':''}>${c.pp>0?'+':'−'}${Math.abs(c.pp).toFixed(1)}pp</i></span>`).join('');
    };
    geoDrill(document.getElementById('fb-drill'),{
      id:'farmbook', data:j, rank:'farm_os',
      cols:[
        {k:'farm_os',fmt:'bahtM',lab:'Farm O/S',title:'MEASURED — outstanding on farm-occupation accounts, real loan tape'},
        {k:'farm_n',fmt:'num',lab:'Accts'},
        {k:'mix_pct',fmt:'pctS',cls:'sgn',lab:'Crop mix',title:'MEASURED — the province crop mix weighted by planted area, moved by each crop’s farm-gate YoY'},
        {k:'drivers',fmt:'raw',lab:'What is driving it',lev:'p',title:'The mix ranked by contribution in percentage points — the crop that actually moved the province, not the biggest drag'},
        {k:'farm_income_thb_month',fmt:'baht',lab:'Farm income',lev:'p',title:'NSO/LFS-anchored farm income per month — context only, not used to rank'},
        {k:'rain_pct_of_normal',fmt:'pct',lab:'Rain % nml',lev:'p',title:'MEASURED — 3-month rainfall as a share of normal. Below 100 is dry.'},
        {k:'napprang_rai',fmt:'num',lab:'2nd-rice rai',lev:'p',title:'MEASURED (OAE) — dry-season irrigated SECOND rice area. The income cushion behind a dry reading: a big area is a buffer today AND the income most at risk if water cuts skip the second crop.'},
        {k:'current',fmt:'num',lab:'Current',title:'Accounts still Current — the population you can still act on before it rolls'},
        {k:'dpd90p_pct',fmt:'pct',lab:'90+ %',lev:'p'}
      ],
      bcols:[
        {k:'farm_os',fmt:'bahtM',lab:'Farm O/S'},
        {k:'farm_n',fmt:'num',lab:'Accts'},
        {k:'current',fmt:'num',lab:'Current'},
        {k:'watch_x',fmt:'num',lab:'X-day'},
        {k:'roll_3089',fmt:'num',lab:'30–89'},
        {k:'dpd90p_pct',fmt:'pct',lab:'90+ %'}
      ],
      natCols:[{k:'farm_os',fmt:'bahtM',lab:'Farm book '},{k:'farm_n',fmt:'num',lab:'Accounts '},
               {k:'current',fmt:'num',lab:'Current '},{k:'provinces',fmt:'num',lab:'Provinces '},
               // farm-BAHT-weighted, matching every region row. crop_mix's headline weights by all
               // book accounts, which is a different denominator and read here would be a unit error.
               {k:'farm_weighted_mix_pct',fmt:'pctS',lab:'Farm-weighted mix '}],
      cell:(k,v)=>k==='drivers'?drivers(v):'',
      foot:'farm (เกษตร) accounts only · cells below the 30-account floor are not published',
      act:(ST,rows)=>{
        if(ST.lev!=='branch') return '';
        const p=(j.provinces||{})[ST.prov]||{};
        // A province can hold farm book that no single BRANCH cell can publish: in an urban province
        // the farm accounts spread so thin that no branch × เกษตร cell clears the 30-account floor.
        // Bangkok (฿15.7m / 102 accounts) and นนทบุรี (฿7.4m / 35) are both this case. Say so — an
        // empty table would read as "no farm book here", which is the opposite of the truth.
        if(!rows.length) return `<b>${ST.prov}</b> holds <b>${m(p.farm_os||0)}</b> of farm book across `
          +`${num(p.farm_n||0)} accounts, but no single branch's farm cell clears the 30-account `
          +`publication floor — so it cannot be broken out per branch. Work it from the province list.`;
        const cur=rows.reduce((s,r)=>s+(r.v.current||0),0), os=rows.reduce((s,r)=>s+(r.v.farm_os||0),0);
        const rn=p.rain_pct_of_normal, dry=rn!=null&&rn<100;
        return `<b>Action:</b> ${ST.prov} holds ${m(os)} of farm book across ${rows.length} branches, `
          +`<b>${num(cur)} accounts still Current</b>. `
          +(p.mix_pct!=null&&p.mix_pct<0
            ? `Its crop mix is down ${Math.abs(p.mix_pct)}% — work the Current list biggest-book-first before the next payment cycle.`
            : dry
              ? `Its crop mix is up ${p.mix_pct}%, but rainfall is <b>${rn.toFixed(1)}% of normal</b> — the risk here is water, not price. Watch collections; do not tighten on price.`
              : `Prices and rainfall are both favourable — monitor only.`);
      },
      // Branch rows are reconciled to the province's MEASURED cell (see build_farm_book._reconcile),
      // so they sum exactly. Saying which rows were measured and which were allocated is the honest
      // part of making them tie.
      bfoot:ST=>{
        const r=((j.provinces||{})[ST.prov]||{}).recon;
        if(!r) return '';
        return `${r.n_measured} of ${r.n_branches} branch cells are MEASURED; the rest are allocated `
          +`over the province mix so the branch rows sum exactly to the province's measured total`
          +(r.mode==='proportional'?' (proportional — measured cells alone exceeded the province total)':'');
      }
    });
    renderFarmCrops(document.getElementById('fb-crops'),j);
  }).catch(()=>{ host.style.display='none'; });
}

/* ================= THE COLLATERAL BOOK — one block where there were five =================
   Owner review, points 8-12, 14, 18 and 19. Five tables scattered across three sections of the tab
   ("Collateral outlook", "Business & credit backdrop") were all answering one question — what do we
   lend against, what is it worth, and what is the resale market doing — so they are one block now.

   POINT 14 IS THE ORGANISING PRINCIPLE, AND THE TAPE BACKS IT:
     "AutoX focuses heavily on pickup and passenger cars. Motorcycles are a secondary focus due to
      smaller ticket size."
   Measured: pickup + passenger car = 60.7% of outstanding on 54.0% of accounts. Motorcycles = 33.3%
   of accounts and 5.8% of the money, AND the worst 90+ rate of any class. Every table here therefore
   ranks by BAHT; ranking by account count would put the least important class on top — which is
   exactly what the retired "most motorcycle-heavy provinces" table did.

   ABSORBED: collateral mix (point 12, now the full 8-type mix to 100%), diesel share (point 10, now a
   province column across all 77), truck fleet (point 18, "why isn't it in the collateral section?" —
   it is now both a type row and a province column), the used-collateral pulse (point 19, now the
   resale-market table at the foot), and the brand box (point 8, "I want to know about all the other
   brands as well" — every brand the tape carries, ranked by outstanding).

   THE HONEST GAP, STATED IN THE UI: the tape crosses vehicle type with REGION, not province. So the
   per-province split of OUR book by collateral type does not exist and is not estimated — province
   rows carry our measured totals plus the measured local vehicle population, and the note says so. */
function renderCollateralBook(){
  const host=document.getElementById('collat-book'); if(!host) return;
  tmliFetch('collateral_book').then(j=>{
    if(!j||!j.national||!j.types){ host.style.display='none'; return; }
    host.style.display='';
    const N=j.national, M=j.meta||{};
    const num=n=>Number(n).toLocaleString('en-US');
    const bn=v=>'฿'+(v/1e9).toFixed(2)+'bn', mB=v=>v>=1e9?'฿'+(v/1e9).toFixed(2)+'bn':'฿'+Math.round(v/1e6).toLocaleString('en-US')+'m';
    const B=v=>v==null?'—':'฿'+Math.round(v).toLocaleString('en-US');
    const core=j.types.filter(t=>t.tier==='core');
    const pu=j.types.find(t=>t.type==='PU'), mc=j.types.find(t=>t.type==='MC');
    const mort=j.types.find(t=>t.type==='Mortgage');
    // The single most load-bearing sentence in the section: the same class is a third of the customers
    // and a twentieth of the money, and it is also the worst-performing. Say it in one breath.
    const motoLine=(mc&&pu)
      ? `<b>Motorcycles are ${mc.n_share_pct}% of accounts but ${mc.os_share_pct}% of the money</b> — and carry the worst 90+ rate of any class at <b style="color:var(--agri)">${mc.dpd90p_pct}%</b> against ${pu.dpd90p_pct}% on pickup. Counting customers and counting baht give opposite answers here; this section counts baht.`
      : '';

    host.innerHTML=`<h3 class="ovsub collat">Collateral book — what we lend against, and what it is worth
        <span class="tag" style="color:var(--merch);border:1px solid var(--merch)">MEASURED · real loan tape + DLT</span></h3>
      <div class="verdict"><b>Pickup and passenger car are ${N.core_share_pct}% of the ${bn(N.os)} book on ${N.core_n_share_pct}% of accounts.</b>
        ${motoLine}
        ${mort?`The second-largest class is not a vehicle at all: <b>property/mortgage at ${mort.os_share_pct}%</b> of outstanding on ${mort.n_share_pct}% of accounts, at a ${B(mort.ticket)} ticket.`:''}
        Across the whole book we lend <b>${N.ltv_proxy_pct}%</b> of assessed collateral value (${B(N.ticket)} outstanding against a ${B(N.eval_avg)} appraisal, per account).
        <span class="sub">Ranked by outstanding baht at every grain. Ranking by account count would lead with motorcycles.</span></div>
      <h4 class="fb-h4">The full mix to 100%<span class="tag" style="color:var(--merch);border:1px solid var(--merch)">MEASURED</span></h4>
      <div id="cb-types"></div>
      <h4 class="fb-h4">The same book by geography — and the collateral base around it</h4>
      <div id="cb-drill"></div>
      <h4 class="fb-h4">Every brand we hold<span class="tag" style="color:var(--merch);border:1px solid var(--merch)">MEASURED</span></h4>
      <div id="cb-brands"></div>
      <h4 class="fb-h4">The resale market this book recovers into<span class="tag" style="color:var(--collat);border:1px solid var(--collat)">MEASURED · DLT</span></h4>
      <div id="cb-flow"></div>`;

    /* ---- 1. the full mix to 100% (point 12) ---- */
    const tierTag=t=>t==='core'?`<span class="cb-tier core" title="Owner-stated focus: pickup and passenger car are the core collateral">core</span>`
      :t==='secondary'?`<span class="cb-tier sec" title="Secondary focus — smaller ticket or smaller book">secondary</span>`
      :`<span class="cb-tier oth" title="Non-vehicle collateral">other</span>`;
    const tt=document.getElementById('cb-types');
    tt.innerHTML=`<div class="tblwrap"><table class="tbl gd-tbl"><tr>
        <th scope="col">Collateral</th>
        <th scope="col" class="gd-r" title="MEASURED — outstanding on this collateral type, real loan tape">Outstanding</th>
        <th scope="col" class="gd-r">% of ฿</th>
        <th scope="col" class="gd-r" title="Share of ACCOUNTS. Where this differs sharply from the baht share, the class is many small tickets.">% of accts</th>
        <th scope="col" class="gd-r" title="DERIVED — outstanding per account">Ticket</th>
        <th scope="col" class="gd-r" title="MEASURED — average appraised collateral value per account">Appraised</th>
        <th scope="col" class="gd-r" title="DERIVED — outstanding per account ÷ appraised value per account. A proxy: outstanding amortises while the appraisal is struck at origination.">Lent vs value</th>
        <th scope="col" class="gd-r" title="MEASURED — 90+ days past due, share of accounts">90+</th>
        <th scope="col" class="gd-r" title="MEASURED — 180+ days, the legacy workout stock held apart from the live book">180+</th>
      </tr>`+j.types.map(t=>`<tr>
        <td class="gd-geo"><b>${t.label}</b> ${tierTag(t.tier)}</td>
        <td class="gd-r">${mB(t.os)}</td>
        <td class="gd-r"><b>${t.os_share_pct}%</b></td>
        <td class="gd-r">${t.n_share_pct}%</td>
        <td class="gd-r">${B(t.ticket)}</td>
        <td class="gd-r">${B(t.eval_avg)}</td>
        <td class="gd-r">${t.ltv_proxy_pct==null?'<span class="gd-na">—</span>':t.ltv_proxy_pct+'%'}</td>
        <td class="gd-r"${t.dpd90p_pct!=null?` style="color:${t.dpd90p_pct>=16?'var(--agri)':t.dpd90p_pct>=13?'var(--gold)':'var(--merch)'}"`:''}>${t.dpd90p_pct==null?'—':t.dpd90p_pct+'%'}</td>
        <td class="gd-r">${t.late180_pct==null?'—':t.late180_pct+'%'}</td>
      </tr>`).join('')+`</table></div>
      <p class="gd-foot">All ${j.types.length} collateral types, summing to 100% of the ${bn(N.os)} book — no top-N slice.
        Every column is MEASURED from the real loan tape except <b>ticket</b> and <b>lent vs value</b>, which are DERIVED from measured inputs.</p>`;

    /* ---- 2. the geo drill (point 13) ---- */
    geoDrill(document.getElementById('cb-drill'),{
      id:'collatbook', data:j, rank:'os',
      cols:[
        {k:'os',fmt:'bahtM',lab:'Outstanding',title:'MEASURED — our book here, real loan tape'},
        {k:'n',fmt:'num',lab:'Accts'},
        {k:'core_share_pct',fmt:'pct',lab:'Core %',lev:'r',title:'Pickup + passenger car as a share of outstanding. MEASURED at region grain; the tape does not cross collateral type with province.'},
        {k:'moto_os_share_pct',fmt:'pct',lab:'Moto % ฿',lev:'r',title:'Motorcycle share of outstanding — compare against the account share beside it'},
        {k:'ticket',fmt:'baht',lab:'Ticket'},
        {k:'eval_avg',fmt:'baht',lab:'Appraised',title:'MEASURED — average appraised collateral value per account'},
        {k:'ltv_proxy_pct',fmt:'pct',lab:'Lent vs value'},
        {k:'diesel_share_pct',fmt:'pct',lab:'Diesel % fleet',lev:'p',title:'MEASURED (DLT) — diesel share of the province car+pickup stock. All 77 provinces, not a top-ten list.'},
        {k:'electrified_pct',fmt:'pct',lab:'EV+hybrid %',lev:'p',title:'MEASURED (DLT) — BEV+PHEV+hybrid share of the province fleet. The leading indicator for used-value erosion on the diesel collateral we hold.'},
        {k:'truck_net_flow',fmt:'num',lab:'Truck net',lev:'p',title:'MEASURED (DLT) — 12-month net truck flow (new + transfers − deregistrations) in this province. Trucks are a collateral class in our book, so this belongs here.'},
        {k:'dpd90p_pct',fmt:'pct',lab:'90+'},
        {k:'current_pct',fmt:'pct',lab:'Current %',title:'DERIVED — accounts neither in the X-day watch bucket nor 30+ overdue'}
      ],
      bcols:[
        {k:'os',fmt:'bahtM',lab:'Outstanding'},
        {k:'n',fmt:'num',lab:'Accts'},
        {k:'ticket',fmt:'baht',lab:'Ticket'},
        {k:'eval_avg',fmt:'baht',lab:'Appraised'},
        {k:'ltv_proxy_pct',fmt:'pct',lab:'Lent vs value'},
        {k:'dpd90p_pct',fmt:'pct',lab:'90+'},
        {k:'late180_pct',fmt:'pct',lab:'180+'},
        {k:'current_pct',fmt:'pct',lab:'Current %'},
        {k:'fleet_est',fmt:'num',lab:'Vehicles ≤10km',title:'ESTIMATED — the province vehicle stock allocated to this branch’s 10km catchment by population share. The size of the local collateral pool, not its mix (the mix is identical for every branch in a province, so it is not shown per branch).'}
      ],
      natCols:[{k:'os',fmt:'bahtM',lab:'Book '},{k:'n',fmt:'num',lab:'Accounts '},
               {k:'ticket',fmt:'baht',lab:'Ticket '},{k:'eval_avg',fmt:'baht',lab:'Appraised '},
               {k:'ltv_proxy_pct',fmt:'pct',lab:'Lent vs value '},{k:'dpd90p_pct',fmt:'pct',lab:'90+ '}],
      foot:'ranked by outstanding at every level',
      act:(ST,rows)=>{
        if(ST.lev==='nat') return `<b>Read this by money, not by count.</b> The region with the most accounts is not the region with the most book, and the province columns are the collateral BASE around our branches — fleet, diesel share, EV share, truck flow — all MEASURED across all 77 provinces.`;
        if(ST.lev==='reg'){
          const r=(j.regions||{})[ST.reg]||{};
          return `<b>${ST.reg}</b> holds ${mB(r.os||0)} across ${num(r.n||0)} accounts. Pickup + passenger car are <b>${r.core_share_pct}%</b> of that money; motorcycles are ${r.moto_os_share_pct}% of the money on ${r.moto_n_share_pct}% of the accounts. `
            +`<span class="sub">The tape crosses collateral type with region, not province — so the province rows below carry our measured totals and the measured local vehicle population, and do not split our book by type. That split is an outstanding ask on the next export.</span>`;
        }
        const p=(j.provinces||{})[ST.prov]||{};
        if(!rows.length) return `<b>${ST.prov}</b> holds ${mB(p.os||0)} but has no branch rows in the tape's branch join.`;
        const os=rows.reduce((s,r)=>s+(r.v.os||0),0);
        const hi=rows.filter(r=>(r.v.ltv_proxy_pct||0)>=60).length;
        return `<b>${ST.prov}</b>: ${mB(os)} across ${rows.length} branches. `
          +(p.diesel_share_pct!=null?`Diesel is <b>${p.diesel_share_pct}%</b> of the local car+pickup fleet and EV+hybrid is ${p.electrified_pct}% — `:'')
          +(hi?`<b>${hi} branch${hi===1?'':'es'}</b> lend 60%+ of assessed collateral value here, which is where a resale-value fall bites first.`
              :`no branch here lends 60%+ of assessed collateral value.`);
      },
      bfoot:()=>`branch rows are MEASURED book totals; “Vehicles ≤10km” is ESTIMATED (province stock allocated by catchment population)`
    });

    /* ---- 3. every brand (point 8) ---- */
    const bt=document.getElementById('cb-brands'), BR=j.brand_book||[];
    if(BR.length){
      const dlt=j.brand_mix||{};
      bt.innerHTML=`<div class="tblwrap gd-wrap"><table class="tbl gd-tbl"><tr>
          <th scope="col">Brand on the title</th>
          <th scope="col" class="gd-r">Outstanding</th><th scope="col" class="gd-r">% of ฿</th>
          <th scope="col" class="gd-r">Accts</th><th scope="col" class="gd-r">Ticket</th>
          <th scope="col" class="gd-r">Appraised</th><th scope="col" class="gd-r">Lent vs value</th>
          <th scope="col" class="gd-r">90+</th><th scope="col" class="gd-r">180+</th></tr>`
        +BR.map(b=>`<tr><td class="gd-geo"><b>${b.brand}</b></td>
          <td class="gd-r">${mB(b.os)}</td><td class="gd-r">${b.os_share_pct}%</td>
          <td class="gd-r">${num(b.n)}</td><td class="gd-r">${B(b.ticket)}</td>
          <td class="gd-r">${B(b.eval_avg)}</td>
          <td class="gd-r">${b.ltv_proxy_pct==null?'<span class="gd-na">—</span>':b.ltv_proxy_pct+'%'}</td>
          <td class="gd-r"${b.dpd90p_pct!=null?` style="color:${b.dpd90p_pct>=16?'var(--agri)':b.dpd90p_pct>=13?'var(--gold)':'var(--merch)'}"`:''}>${b.dpd90p_pct==null?'—':b.dpd90p_pct+'%'}</td>
          <td class="gd-r">${b.late180_pct==null?'—':b.late180_pct+'%'}</td></tr>`).join('')
        +`</table></div>
        <p class="gd-foot">All ${BR.length} brands the tape carries, ranked by outstanding — not a top-four tile row.
          This is what WE hold${dlt.vintage_be?`; what the COUNTRY buys new is a different question, answered by the DLT first-registration mix (${dlt.vintage_ce||dlt.vintage_be})`:''}.
          Every column MEASURED except ticket and lent-vs-value, which are DERIVED.</p>`;
    } else { bt.style.display='none'; }

    /* ---- 4. the resale market (point 19) ---- */
    const ft=document.getElementById('cb-flow'), FL=j.used_flow||[];
    if(FL.length){
      const pc=v=>v==null?'<span class="gd-na">—</span>':(100*v).toFixed(1)+'%';
      ft.innerHTML=`<div class="tblwrap"><table class="tbl gd-tbl"><tr>
          <th scope="col">Region</th>
          <th scope="col" class="gd-r" title="Ownership transfers as a share of registrations processed — how liquid the second-hand market is">Transfer rate · all</th>
          <th scope="col" class="gd-r">Car</th><th scope="col" class="gd-r">Pickup</th><th scope="col" class="gd-r">Moto</th>
          <th scope="col" class="gd-r" title="Permanent deregistrations as a share of registrations processed — vehicles leaving the fleet for good">Dereg · car</th>
          <th scope="col" class="gd-r">Dereg · pickup</th><th scope="col" class="gd-r">Dereg · moto</th></tr>`
        +FL.map(r=>`<tr><td class="gd-geo"><b>${r.region}</b></td>
          <td class="gd-r">${pc(r.all&&r.all.transfer_rate)}</td>
          <td class="gd-r">${pc(r.car&&r.car.transfer_rate)}</td>
          <td class="gd-r">${pc(r.pickup&&r.pickup.transfer_rate)}</td>
          <td class="gd-r">${pc(r.moto&&r.moto.transfer_rate)}</td>
          <td class="gd-r">${pc(r.car&&r.car.dereg_rate)}</td>
          <td class="gd-r">${pc(r.pickup&&r.pickup.dereg_rate)}</td>
          <td class="gd-r">${pc(r.moto&&r.moto.dereg_rate)}</td></tr>`).join('')
        +`</table></div>
        <p class="gd-foot">MEASURED (DLT registrations). A <b>transfer</b> is a used vehicle changing hands — the deeper that market, the faster an enforced title converts to cash.
          A <b>deregistration</b> is a vehicle leaving the fleet permanently, which is the collateral pool shrinking.
          Motorcycles deregister at several times the rate of cars and pickups everywhere, which is the mechanism behind their weaker recovery.
          Region grain: DLT publishes this flow by registration office, not by province.</p>`;
    } else { ft.style.display='none'; }
  }).catch(()=>{ host.style.display='none'; });
}

/* THE SAME BOOK, CUT BY CROP — the second lens of the farm block, not a second section.
   Owner on the old farmer-margin table: "I like the commodities/margin table but expand to cover what
   we have on data AND consolidate with above tables." So it moves in here, widened from the 5 crops
   OAE publishes a cost for to all 8 the mix prices, and gains the two columns that connect it to the
   loan book: how much book each crop carries, and how many points of the book's move it supplied.

   The two money columns deliberately disagree, and that disagreement is the insight:
     Farm ฿ (alloc)  is an ALLOCATION — the tape records an occupation, never a crop. Order of
                     magnitude only, and it says so in the header.
     Contribution    is firm — measured farm-gate YoY x measured area share, weighted by measured
                     baht. It sums to the farm-weighted move in the banner above, so the column foots.
   Margin is DERIVED from two MEASURED OAE/NABC inputs whose vintages differ: read the direction. */
function renderFarmCrops(host,j){
  if(!host) return;
  const CR=j.crops||[]; if(!CR.length){ host.style.display='none'; return; }
  const N=j.national||{};
  const m=v=>'฿'+Math.round(v/1e6).toLocaleString('en-US')+'m';
  const sg=v=>v==null?'<span class="gd-na">—</span>':`<span style="color:${v<0?'var(--agri)':'var(--merch)'}">${v>0?'+':v<0?'−':''}${Math.abs(v).toFixed(1)}</span>`;
  const priced=CR.filter(c=>c.margin_per_rai!=null).length;
  host.innerHTML=`<h4 class="fb-h4">The same book, cut by crop
      <span class="tag" style="color:var(--gold);border:1px solid var(--gold)">MEASURED price · ALLOCATED book</span></h4>
    <div class="tblwrap"><table class="tbl gd-tbl"><tr>
      <th scope="col">Crop</th>
      <th scope="col" class="gd-r" title="ALLOCATED — the province's measured farm book spread over its measured planted-area mix. The tape records an occupation, not a crop, so read the order of magnitude.">Farm ฿ (alloc)</th>
      <th scope="col" class="gd-r">% of book</th>
      <th scope="col" class="gd-r" title="MEASURED — share of the eight priced crops' planted area nationally (OAE/DOAE)">% of area</th>
      <th scope="col" class="gd-r" title="MEASURED — farm-gate price YoY (NABC daily averages; OCSB announced price for cane)">Price YoY</th>
      <th scope="col" class="gd-r" title="The crop's contribution, in percentage points, to the farm-baht-weighted move of the whole book. These sum to the banner figure — this is the column that answers 'what is actually moving us'.">Moved the book</th>
      <th scope="col" class="gd-r" title="MEASURED — farm-gate price, baht per kg">฿/kg</th>
      <th scope="col" class="gd-r" title="MEASURED — OAE production cost, baht per kg. Where OAE reports several field practices the conservative (lowest-margin) one is shown.">Cost/kg</th>
      <th scope="col" class="gd-r" title="DERIVED from the two measured inputs — margin per rai. The vintages differ; read direction, not decimals.">Margin ฿/rai</th>
      <th scope="col" class="gd-r" title="Provinces where this crop is the largest share of planted area">Dominant in</th>
    </tr>`+CR.map(c=>`<tr>
      <td class="gd-geo"><b>${c.en}</b>${c.alts>1?`<span class="sub" title="OAE reports ${c.alts} cost rows for this crop (different field practices); the conservative one is shown"> · ${c.alts} OAE cost rows</span>`:''}</td>
      <td class="gd-r">${m(c.farm_os_alloc)}</td>
      <td class="gd-r">${c.os_share_pct.toFixed(1)}%</td>
      <td class="gd-r">${c.area_share_pct==null?'<span class="gd-na">—</span>':c.area_share_pct.toFixed(1)+'%'}</td>
      <td class="gd-r">${sg(c.yoy)}%</td>
      <td class="gd-r"><b>${sg(c.pp_of_book)}pp</b></td>
      <td class="gd-r">${c.price_kg==null?'<span class="gd-na">—</span>':'฿'+c.price_kg}</td>
      <td class="gd-r">${c.cost_kg==null?'<span class="gd-na">—</span>':'฿'+c.cost_kg}</td>
      <td class="gd-r">${c.margin_per_rai==null?'<span class="gd-na">—</span>':'฿'+Math.round(c.margin_per_rai).toLocaleString('en-US')}</td>
      <td class="gd-r">${c.dominant_in||'<span class="gd-na">—</span>'}</td>
    </tr>`).join('')+`</table></div>
    <p class="gd-foot">All ${CR.length} priced crops · the <b>Moved the book</b> column sums to the
      <b>${N.farm_weighted_mix_pct>0?'+':''}${Number(N.farm_weighted_mix_pct).toFixed(1)}%</b> in the banner above ·
      OAE publishes a production cost for ${priced} of ${CR.length}, so margin is blank for the rest
      rather than guessed · price and cost are MEASURED, the margin arithmetic is DERIVED and the two
      vintages differ — read direction, not decimals.</p>`;
  host.style.display='';
}

/* MEASURED farm-household cash P&L (data/farm_household.json) — the ground under every price claim
   in this product. The one number that changes how you read the rest is the non-farm share: a crop
   price move reaches only the farm half of a farm household's cash. National survey means, so it is
   framed as a backdrop and never joined to a province. */
function renderFarmHousehold(){
  const host=document.getElementById('assist-household'); if(!host) return;
  tmliFetch('farm_household').then(j=>{
    if(!j||!j.latest){ tmliNote(host,'The household backdrop needs <b>data/farm_household.json</b> — not built for this vintage.'); return; }
    const L=j.latest, yrs=j.years||[], B=n=>'฿'+Math.round(n).toLocaleString();
    const inc=L.income||{}, exp=L.expense||{};
    const nf=L.nonfarm_share_of_income_pct;
    // Farm income vs non-farm as one honest split bar — the whole point in a single glance.
    const w=340,h=16,fs=(L.farm_share_of_income_pct||0)/100;
    const bar=`<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="farm ${L.farm_share_of_income_pct}% vs non-farm ${nf}% of household cash income">
        <rect x="0" y="0" width="${(w*fs).toFixed(1)}" height="${h}" fill="var(--agri)" rx="2"/>
        <rect x="${(w*fs).toFixed(1)}" y="0" width="${(w*(1-fs)).toFixed(1)}" height="${h}" fill="var(--merch)" rx="2"/></svg>`;
    const trend=yrs.map(r=>`<tr><td><b>${r.crop_year}</b></td>
        <td class="mono">${B(r.income.farm_total)}</td>
        <td class="mono">${B(r.income.nonfarm)}</td>
        <td class="mono">${B(r.expense.total)}</td>
        <td class="mono"><b>${B(r.net_cash)}</b></td>
        <td class="mono sub">${B(r.net_cash_monthly)}</td>
        <td class="mono sub">${r.farm_share_of_income_pct==null?'—':r.farm_share_of_income_pct+'%'}</td></tr>`).join('');
    const hh=L.household||{};
    host.innerHTML=`<p class="lead" style="margin:0 0 8px"><b style="color:var(--merch)">${nf}% of a farm household's cash income is non-farm</b> — so a crop-price fall reaches roughly ${L.farm_share_of_income_pct}% of what the household actually earns, not all of it. In ${L.crop_year} the average farm household took ${B(inc.total)} cash, spent ${B(exp.total)}, and cleared <b>${B(L.net_cash)}</b> for the year — <b>${B(L.net_cash_monthly)}/month</b>.</p>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 10px">${bar}
        <span class="sub" style="font-size:12px"><span style="color:var(--agri)">■</span> farm ${L.farm_share_of_income_pct}% &nbsp; <span style="color:var(--merch)">■</span> non-farm ${nf}%</span></div>
      <table class="tbl"><tr><th>Crop year</th><th title="crops + livestock + other farm cash">Farm cash income</th>
        <th title="wages, remittances, off-season work — untouched by crop prices">Non-farm</th>
        <th>Cash expense</th><th>Net cash / yr</th><th class="sub">/ month</th><th class="sub">Farm share</th></tr>${trend}</table>
      <p class="lead sub" style="margin:8px 0 0"><b>Household:</b> head aged ${hh.head_age_years??'—'}, ${hh.household_size??'—'} people, ${hh.workers_15_64??'—'} of working age, ${hh.landholding_rai??'—'} rai held. <b>Reading:</b> ${(j.meta||{}).scope_warning||''} ${(j.meta||{}).not_covered||''}</p>`;
    wrapTables();
  });
}

function renderAssistPriceLens(){
  const host=document.getElementById('assist-price'); if(!host) return;
  tmliFetch('assist_price_radar').then(j=>{
    if(!j||!Array.isArray(j.crops)||!j.crops.length){
      tmliNote(host,'The price lens needs <b>data/assist_price_radar.json</b> — not built for this vintage. The drought radar above is unaffected.');
      return;
    }
    const N=n=>Number(n).toLocaleString();
    const trig=(j.meta&&j.meta.trigger)||{}, tripped=Array.isArray(j.tripped)?j.tripped:[];
    const provs=Array.isArray(j.provinces)?j.provinces:[];
    const total=(j.meta&&j.meta.n_current_x_total)||provs.reduce((a,r)=>a+(r.n_current_x||0),0);

    // Lead with the answer. If something has tripped that IS the answer; otherwise the answer is the
    // size of the healthy book and the fact that nothing is falling — said plainly, not padded.
    // With 22 provinces tripping, listing every name reads as noise. Lead with the size of the
    // callable slice and WHICH falling crop is driving it; the names go in the table below.
    const trippedRows=provs.filter(r=>r.tripped);
    const trippedN=trippedRows.reduce((a,r)=>a+(r.n_current_x||0),0);
    const byCrop={};
    trippedRows.forEach(r=>(r.falling_crops||[]).forEach(c=>{
      byCrop[c]=byCrop[c]||{n:0,prov:0};byCrop[c].n+=r.n_current_x||0;byCrop[c].prov++;}));
    const drivers=Object.entries(byCrop).sort((a,b)=>b[1].n-a[1].n).map(([c,v])=>{
      const yy=(j.crops.find(x=>x.crop===c)||{}).yoy;
      return `<b>${c}</b> ${yy==null?'':`<span class="mono" style="color:var(--agri)">${yy}%</span>`} <span class="sub">(${v.prov} prov, ${N(v.n)} accounts)</span>`;}).join(' · ');
    const named=trippedRows.slice().sort((a,b)=>(b.n_current_x||0)-(a.n_current_x||0)).slice(0,6).map(r=>r.th).join(' · ');
    const lead = tripped.length
      ? `<b style="color:var(--agri)">${N(trippedN)} healthy farm accounts are in a falling sector right now</b> — Current or X-bucket only, across <b>${tripped.length}</b> province${tripped.length>1?'s':''} where a crop covering ≥${Math.round((trig.dominant_share||0)*100)}% of the planted area is in price decline. Driven by ${drivers}. Biggest books: ${named}. This is the slice to call before collections turn.`
      : `<b>Nothing tripped.</b> Every mapped crop is up year-on-year, so no province is in farm-price distress today. What is real now is the exposure: <b>${N(total)}</b> farm accounts across <b>${provs.length}</b> provinces are <b>Current or only X-bucket</b> — healthy, and riding on the prices below.`;

    const crops=j.crops.map(c=>`<tr>
        <td><b>${c.crop}</b></td>
        <td class="mono" style="color:${priceDirColor(c.direction)}"><b>${c.yoy==null?'—':(c.yoy>0?'+':'')+c.yoy+'%'}</b></td>
        <td class="mono">${N(c.n_provinces)}</td>
        <td class="mono"><b>${N(c.n_current_x)}</b> <span class="sub">of ${N(c.n_farm_accounts)}</span></td>
        <td class="mono sub">${aodTHB(c.os_thb)}</td>
        <td class="sub" style="font-size:12px">${(c.top_provinces||[]).join(' · ')||'—'}</td></tr>`).join('');

    // The province detail is the actionable list, but it is long — keep it collapsed so the crop
    // rollup stays the thing you read first.
    // Tripped first — the file sorts by book size alone, which would bury the actionable rows
    // under large-but-healthy ones.
    const ordered=provs.slice().sort((a,b)=>(b.tripped?1:0)-(a.tripped?1:0)||(b.n_current_x||0)-(a.n_current_x||0));
    const top=ordered.slice(0,15).map(r=>`<tr>
        <td><b>${r.th}</b> <span class="sub mono">${r.region||''}</span>${r.tripped?' <span class="tag" style="color:var(--agri);border-color:var(--agri)" title="a crop this province depends on is in price decline">FALLING CROP</span>':''}${r.also_in_drought_radar?' <span class="tag" title="this province is also on the drought radar above">DROUGHT TOO</span>':''}</td>
        <td class="mono"><b>${N(r.n_current_x)}</b></td>
        <td class="mono sub">${N(r.n_current)} / ${N(r.n_early)}</td>
        <td class="mono sub">${N(r.n_farm_accounts)}</td>
        <td class="mono sub">${aodTHB(r.os_thb)}</td>
        <td class="sub" style="font-size:12px">${(r.crops||[]).filter(c=>c.depended_on).map(c=>`${c.crop} <span class="mono" style="color:${priceDirColor(c.direction)}">${c.yoy==null?'—':(c.yoy>0?'+':'')+c.yoy+'%'}</span>`).join(' · ')||'—'}</td></tr>`).join('');

    host.innerHTML=`<p class="lead" style="margin:0 0 10px">${lead}</p>
      <table class="tbl"><tr>
        <th>Crop</th>
        <th title="Thai farm-gate price, year-on-year — MEASURED NABC daily national average">Farm-gate YoY</th>
        <th title="provinces where this crop is at least the dominance share of planted area">Provinces on it</th>
        <th title="accounts that are Current or only in the X (pre-30dpd) bucket">Healthy accounts riding on it</th>
        <th title="the whole farm book in those provinces — the tape does not split outstanding by bucket">Farm book</th>
        <th>Where most of it sits</th></tr>${crops}</table>
      <details style="margin-top:10px"><summary class="sub">By province — falling-crop provinces first, then the largest healthy farm books (15 of ${provs.length})</summary>
        <table class="tbl" style="margin-top:8px"><tr>
          <th>Province</th><th>Current + X</th><th class="sub">Current / X</th>
          <th class="sub">Farm accounts</th><th class="sub">Farm book</th><th>Crops it depends on</th></tr>${top}</table></details>
      <p class="lead sub" style="margin:10px 0 0"><b>Trips when</b> ${trig.rule||'a depended-on crop turns negative'} <b>Reading:</b> the Current/X split is by <b>account count</b>; the farm book figure is the province's whole farm outstanding — the tape aggregate does not expose balance by bucket, and splitting it here would be invention. <b>Sugarcane joined this map on 1 Aug 2026</b> — cane growers register with the OCSB rather than DOAE, so it had no planted area here and its only price was a 2019 OAE snapshot reading <b>+26%</b> when the announced cane price is <b>−17.9%</b>. It now drives most of what has tripped. Livestock and fisheries (pork, shrimp, chicken, eggs) are still absent: they have no planted area to join on.</p>`;
    wrapTables();
  });
}

function renderAssist(){
  if(!document.getElementById('v-assist')) return;
  loadTapeReal().then(()=>{
    const T=TAPE, absent=$('#assist-absent'), hero=$('#assist-hero');
    if(!T||!T.bucket_ladder){ if(absent)absent.style.display=''; if(hero)hero.innerHTML=''; return; }
    if(absent)absent.style.display='none';
    // ฿ at the right magnitude everywhere on this page (owner ask 2026-07-28: "฿1075m" is unreadable)
    const N=n=>Number(n).toLocaleString(), bn=aodTHB, mn=aodTHB;
    const lb=T.bucket_ladder.live_book;
    const rs=(T.restructuring&&T.restructuring.by_status)||[];
    const pe=rs.find(s=>s.status==='Pre-emptive'), tdr=rs.find(s=>s.status==='TDR');
    const r0=(T.assistance_radar||[])[0];
    // hero KPI strip (reuse .mcard)
    if(hero) hero.innerHTML=[
      ['X-days pre-emptive window',N(lb.xdays_n),'accounts late &lt;30dpd — intervene before roll','var(--opp)'],
      ['Rolling (30–89dpd)',N(lb.roll_n),'in the roll pipeline — recoverable middle','#D97A3A'],
      ['Pre-emptively restructured',pe?N(pe.n):'—',pe?pe.dpd90p_pct+'% already at 90+ — bleeding':'','var(--collat)'],
      ['TDR — restructure failing',tdr?N(tdr.n):'—',tdr?tdr.dpd90p_pct+'% at 90+, '+tdr.late180_pct+'% at 180+':'','var(--agri)'],
    ].map(k=>`<div class="mcard" style="border-left:3px solid ${k[3]}"><div class="k">${k[0]}</div><div class="v">${k[1]}</div><div class="n">${k[2]}</div></div>`).join('');

    // "Segments hit most" is now rendered by aodSyncHitList() so it FOLLOWS the occupation drill
    // (owner ask 2026-07-28) instead of showing a fixed national occupation×region list.

    // pre-emptive radar (province × drought)
    const rad=(T.assistance_radar||[]).slice(0,12);
    $('#assist-radar').innerHTML = rad.length ? `<table class="tbl"><tr>
        <th>Province</th><th title="X-days: late but <30dpd — call this week">Tier 1 · slipping</th>
        <th title="current accounts in the same stressed cell">Tier 2 · watch</th>
        <th title="share of districts at severe/extreme OAE SPEI">Drought</th>
        <th>What they grow (stressed districts)</th></tr>`+
      rad.map(r=>`<tr>
        <td><b>${r.province}</b> <span class="sub mono">${N(r.n_farmers)} farmers</span></td>
        <td class="mono" style="color:var(--opp)"><b>${N(r.tier1_slipping)}</b></td>
        <td class="mono">${N(r.tier2_current_exposed)}</td>
        <td class="mono" style="color:${r.districts_severe_pct>=60?'var(--agri)':'var(--dim)'}">${r.districts_severe_pct}% <span class="sub">SPEI ${r.worst_spei}</span></td>
        <td class="sub" style="font-size:12px">${(r.stressed_crops||[]).join(' · ')||'—'}</td></tr>`).join('')+`</table>` :
      `<p class="lead sub">The drought radar is calm — no farm-household cells under severe SPEI stress right now.</p>`;

    renderFarmHousehold();
    renderAssistPriceLens();

    // restructuring — did it hold?
    const ORD=['Normal','Skip','Pre-emptive','TDR'];
    const rows=ORD.map(s=>rs.find(x=>x.status===s)).filter(Boolean);
    $('#assist-restr').innerHTML = rows.length ? `<table class="tbl"><tr>
        <th>Status</th><th>Accounts</th><th>OS</th><th>X-days</th><th>Roll</th>
        <th>90+</th><th>180+</th></tr>`+
      rows.map(r=>`<tr><td><b>${r.status}</b></td>
        <td class="mono">${N(r.n)}</td><td class="mono sub">${bn(r.os_sum)}</td>
        <td class="mono">${r.early_pct}%</td><td class="mono">${r.roll_pct}%</td>
        <td class="mono"><b style="color:${assistSev(r.dpd90p_pct)}">${r.dpd90p_pct}%</b></td>
        <td class="mono" style="color:${assistSev(r.late180_pct)}">${r.late180_pct}%</td></tr>`).join('')+`</table>` :
      `<p class="lead sub">Restructuring split unavailable in this tape vintage.</p>`;

    wrapTables();
  });
}
function renderHome(){
  renderHomePillars();      // the 5-pillar summary band (null-safe; re-rendered as layers load)
  renderHomeQueue();        // "This week — do these first" — exec decision queue (lazy, null-safe)
  renderHomeThesis();       // ONE board-ready risk sentence (synthesized, null-safe)
  renderHomeHero();         // QW5 — the verdict, in plain language (opportunity + household + crop)
  renderHomeWhitespace();   // uses META (estates/mws/cws) immediately; amphoe when loaded
  renderHomeRisk();         // uses META.region + crop_stress when loaded + PROV moto mix
  renderHomeMacro();        // META.macro + META.board
  renderHomeDefend();       // rival_threat_region.json — hardest-to-defend regions (lazy, null-safe)
  renderHomeMovers();       // deltas.json
  renderWatchlist();
  renderHomeDataRoom();     // provenance.json — measured/estimated/unlabelled census (lazy, null-safe)
  if(!homeBooted){
    homeBooted=true;
    const onHome=()=>document.getElementById('v-home').classList.contains('on');
    // exec decision queue — the FIRST card: ranked weekly actions (null-safe, calm when absent).
    loadDecisionQueue().then(()=>{ if(onHome()) renderHomeQueue(); });
    // data room — the provenance census (measured/estimated/unlabelled), lazy + null-safe.
    loadProvenance().then(()=>{ if(onHome()) renderHomeDataRoom(); });
    loadAmphoe().then(()=>{ if(onHome()){ renderHomeWhitespace(); renderHomeThesis(); } });
    loadCropStress().then(()=>{ if(onHome()){ renderHomeRisk(); renderHomeHero(); renderHomeThesis(); } });
    // Strategy pivot: the opportunity-score / expansion-plan loaders and their "open next" hero + growth
    // thesis have been REMOVED. The home thesis/hero now render from the risk layers only.
    // QW5 hero needs measured household leverage — lazy, null-safe re-render.
    loadHouseholdRisk().then(()=>{ if(onHome()){ renderHomeHero(); renderHomeThesis(); } });
    // obj#1 — structurally riskiest province (DTI+unemployment composite) into the risk card + thesis (null-safe).
    loadProvinceStress().then(()=>{ if(onHome()){ renderHomeRisk(); renderHomeThesis(); } });
    // obj#1 — macro-exposure dominant-factor headline in the thesis sentence (null-safe, est).
    loadMacroExposure().then(()=>{ if(onHome()) renderHomeThesis(); });
    // obj#1 — lead the "getting riskier" card with the composite province-risk verdict (null-safe).
    loadProvinceRisk().then(()=>{ if(onHome()) renderHomeRisk(); });
    // obj#1 — collateral RECOVERY outlook (national, collateral_outlook.json) into the risk card.
    loadCollatOutlookData().then(()=>{ if(onHome()) renderHomeRisk(); });
    // obj#1 — per-branch composite to name the single riskiest branch in the risk card (null-safe).
    loadBranchRisk().then(()=>{ if(onHome()) renderHomeRisk(); });
    // obj#1 — lowest-paid occupation nationally into the risk card (null-safe, mirrors Exposure).
    loadOccupationIncome().then(()=>{ if(onHome()) renderHomeRisk(); });
    // live fuel prices (Bangchak daily pull) into the macro card + pillar band — null-safe.
    loadFuelPrices().then(()=>{ if(onHome()){ renderHomeMacro(); renderHomePillars(); } });
    // obj#1 — REAL loan-tape assistance radar (pre-emptive help targeting) + pillar band; calm when absent.
    loadTapeReal().then(()=>{ if(onHome()){ renderHomeTape(); renderHomePillars(); } });
    // measured borrower-base + competitor census to enrich the top-district rows; null-safe re-render.
    const reHome=()=>{ if(onHome()) renderHomeWhitespace(); };
    loadAmphoeOccupations().then(reHome);
    loadCompetitors().then(reHome);
    // obj#2 — national competitor-coverage % chip in the where-to-expand card (null-safe).
    loadCompCoverage().then(reHome);
    // obj#2 — most-contested-ground rank-1 fact (measured WorldPop × rival census) into the
    // expand card, mirroring the full table already shipped on Exposure (null-safe).
    loadContestedPop().then(reHome);
    // obj#2 — sub-scale PICO-finance rival pressure (FPO registry, MEASURED): how many provinces the
    // licensed small-ticket field outnumbers the existing footprint, mirroring the #acq leaderboard.
    loadPicoCompetitors().then(reHome);
    // obj#2 — the CO-EQUAL competitive-risk clause in the board thesis: how many provinces the big-4
    // outnumber the existing network in (MEASURED per-province density). Null-safe re-render.
    loadPeerProvince().then(()=>{ if(onHome()){ renderHomeThesis(); renderHomePillars(); } });
    // obj#2 — the per-region density × service read (rival_threat_region.json) onto the front door:
    // which regions are hardest to defend, beside the portfolio-risk headline. Null-safe re-render.
    loadRivThreatRegion().then(()=>{ if(onHome()){ renderHomeDefend(); renderHomeThesis(); } });
    // obj#1 x obj#2 — the INTERSECTION clause: provinces both borrower-stressed AND rival-dominated
    // (province_pressure.json, a deterministic join of the two per-province axes). Null-safe re-render.
    loadProvincePressure().then(()=>{ if(onHome()) renderHomeThesis(); });
    const c=$('#cc-csv'), p=$('#cc-print');
    if(c) c.onclick=ccBriefCSV;
    if(p) p.onclick=()=>window.print();
  }
}

/* QW5 — HOME LEADS WITH THE VERDICT.
   2–3 BIG plain-language hero statements built ONLY from data already loaded (a RISK read, never a
   growth/where-to-open one):
   • "Watching: … household leverage (DTI …×) …" — from MEASURED household_risk (top DTI province)
     paired with the worst crop-household double-/single-stress (crop_stress).
   • a third drought/double-stress line when crop_stress carries a flagged province.
   Each statement links to its detail tab. Any source that is absent is omitted gracefully —
   never fabricated. Re-rendered as each lazy source resolves. */
/* BOARD THESIS — one spoken-English sentence a director could read aloud. Synthesized ONLY from data
   already in memory (DATA/META/AMP/HHRISK/CSTRESS); every clause is dropped if its source is absent, so
   it never fabricates. Re-rendered as lazy sources resolve. Names: how many branches we run, how many
   districts have no coverage, and what is stressing — a RISK read, not a growth plan. */
function renderHomeThesis(){
  const box=$('#cc-thesis'); if(!box) return;
  const have=(Array.isArray(DATA)?DATA.length:0);
  // zero-branch (no-coverage) district count — measured PIP from amphoe.json.
  const zeroDist=(AMP&&AMP.length)?AMP.filter(a=>a.branches===0).length:null;
  // what is stressing — the DTI+unemployment composite (more defensible, blends two NSO legs) else
  // raw household DTI else worst crop-stress province.
  const ps=(pstressHasData()&&PSTRESS_LIST.length)?PSTRESS_LIST[0]:null;
  const hh=(Array.isArray(HHRISK_LIST)&&HHRISK_LIST.length)?HHRISK_LIST[0]:null;
  const cs=(CSTRESS_LIST&&CSTRESS_LIST.length)?CSTRESS_LIST[0]:null;
  // ---- assemble the sentence, clause by clause, skipping any absent source ----
  const clauses=[];
  if(have){
    clauses.push(`AutoX runs <b>${have.toLocaleString()}</b> branches today`);
  }
  if(zeroDist!=null){
    clauses.push(`<b>${zeroDist.toLocaleString()}</b> district${zeroDist===1?'':'s'} have <b>no AutoX branch</b> (coverage gaps)`);
  }
  // obj#2 — the CO-EQUAL competitive-risk clause (CLAUDE.md: the command center aggregates competitive
  // risk + portfolio risk into ONE readout). How universally the big-4 title-lenders outnumber the
  // EXISTING network on local per-province density (MEASURED census, peer_province.json) — a risk read
  // on the footprint we run, never an open/expand call. Null-safe; dropped until the layer loads.
  const pp=(PEERPROV&&PEERPROV.meta)?PEERPROV.meta:null;
  if(pp&&pp.n_provinces_outnumbered!=null&&pp.n_provinces){
    const nOut=pp.n_provinces_outnumbered, nP=pp.n_provinces;
    const scope=(nOut>=nP)?`all <b>${nP}</b> provinces`:`<b>${nOut}</b> of ${nP} provinces`;
    clauses.push(`the big-4 rivals <b>outnumber AutoX</b> in ${scope} on local density (measured)`);
  }
  // obj#2 — the per-region DEFENSIBILITY discriminator (rival_threat_region.json, the same MEASURED
  // density×service layer the #cc-defend card renders). Density is high in every region (the clause
  // above), so the sharp read is SERVICE: which region's rival field is both dense AND best-loved,
  // i.e. hardest to take share from. Names the hardest-to-defend ground in prose beside the portfolio
  // verdict — the front door's job is one blended readout. Null-safe; dropped until the layer loads.
  const rt=(RIVTHREATREG&&Array.isArray(RIVTHREATREG.regions))?RIVTHREATREG.regions:null;
  if(rt&&rt.length){
    const hard=rt.filter(r=>r.threat_class==='Hardest to defend');
    if(hard.length){
      // lead the rating with the sharpest hard region: best-loved rival service, preferring a non-thin sample.
      const lead=hard.slice().sort((a,b)=>{
        if(!!a.thin_rating_sample!==!!b.thin_rating_sample) return a.thin_rating_sample?1:-1;
        return (b.rating_wavg||0)-(a.rating_wavg||0);
      })[0];
      const names=hard.map(r=>r.region).join(' &amp; ');
      const rr=(typeof lead.rating_wavg==='number')?lead.rating_wavg.toFixed(2)+'★':'—';
      clauses.push(`the ground <b>hardest to defend</b> is <b>${names}</b> (rivals both densest and best-loved, up to ${rr}${lead.thin_rating_sample?', thin sample':''}, measured)`);
    }
  }
  // THE INTERSECTION (province_pressure.json) — the sharpest cross-objective clause: how many
  // provinces sit in BOTH the top third for borrower stress AND for rival dominance (a fragile
  // portfolio where margin defence is hardest), and which one is worst. Both axes are relative
  // percentiles, so this is a RANKING, not a verdict; dropped until the layer loads. Null-safe.
  const cp=(PROVPRESS&&PROVPRESS.meta)?PROVPRESS.meta:null;
  if(cp&&cp.n_double_pressure){
    const w=cp.worst_province;
    const tail=(w&&w.province_th)?`, worst is <b>${w.province_th}</b>`:'';
    clauses.push(`<b>${cp.n_double_pressure}</b> province${cp.n_double_pressure===1?'':'s'} are <b>both stressed and outgunned</b> (top-third on portfolio risk AND rival pressure${tail})`);
  }
  if(ps){
    clauses.push(`the risk to watch is <b>${ps.province} household stress</b> (DTI ${ps.debt_to_income!=null?(+ps.debt_to_income).toFixed(2)+'×':'—'} + unemployment ${ps.unemployment_rate!=null?(+ps.unemployment_rate).toFixed(1)+'%':'—'}, composite ▲${(ps.composite_stress||0).toFixed(0)}, measured)`);
  } else if(hh){
    clauses.push(`the risk to watch is <b>${hh.region||hh.province} household leverage</b> (DTI ${(+hh.debt_to_income).toFixed(2)}× in ${hh.province}, measured)`);
  } else if(cs){
    clauses.push(`the risk to watch is a <b>${cs.th}</b> crop-income squeeze`);
  }
  // macro headline (obj#1) — the deteriorating macro factor DOMINANT at the most branches, tallied
  // client-side from the macro-exposure vector (ESTIMATED composite; omitted until the layer loads).
  const mt=macxLoaded?macxDomTally():null;
  if(mt&&mt.top){
    clauses.push(`the macro factor hitting the most branches' customers is <b>${mt.top.label}</b> (${mt.top.n.toLocaleString()} branches, est)`);
  }
  if(!clauses.length){ box.innerHTML=''; return; }
  const sentence=clauses.join('; ')+'.';
  // REMOVED (strategy pivot): the "Road to N" branch-count progress bar — the network is consolidating,
  // there is no growth target to track against.
  box.innerHTML=`<div class="cc-thesis-line">▶ ${sentence}</div>`;
}
function renderHomeHero(){
  const box=$('#cc-hero'); if(!box) return;
  const heroes=[];
  // REMOVED (strategy pivot): the "Open next in …" hero (sequenced growth plan / composite opportunity
  // score) — a branch-open recommendation. The network is consolidating, so the home hero leads with the
  // RISK read only. The competitive-risk detail lives on the Competition tab (#acq).
  // WATCHING — MEASURED household leverage (top DTI province) + worst crop-household stress.
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
      tag:hh?'measured + estimated':'estimated', cta:hh?'Map view →':'Macro →'});
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

// COMPETITIVE PRESSURE — leads with most contested ground (rivals in our catchments) + competitor
// coverage, then thinnest-coverage districts/provinces (with rival counts). A risk read on the
// EXISTING network — NOT an open-a-branch recommendation.
function renderHomeWhitespace(){
  const box=$('#cc-ws-body'); if(!box||!META) return;
  let html='';
  // MOST CONTESTED GROUND (contested_pop.json) — where we already fight a rival for the same catchment
  // population: the lead competitive-pressure signal. Lazy; appears once the layer loads.
  if(CPOP&&Array.isArray(CPOP.top)&&CPOP.top.length){
    const t=CPOP.top[0];
    html+=`<div class="cc-sub2" style="margin-top:0">Most contested ground ${TAG_M}</div>`;
    html+=ccRow(`${t.name||'—'} <span class="sub">${t.prov||''}${t.region?' · '+t.region:''}</span>`,
      `${(t.cpop||0).toLocaleString()} of ${(t.pop||0).toLocaleString()} catchment pop. within 2km of a rival`,
      `${t.pct}%`,'contested','var(--agri)');
  }
  // SUB-SCALE RIVAL PRESSURE — where the licensed PICO-finance field (a DISTINCT small-ticket rival
  // class, FPO registry, MEASURED) outnumbers the existing AutoX footprint. An obj#2 pressure read on
  // the network we already run (margin/contest pressure), mirroring the full leaderboard on Competition;
  // it is NOT an open-a-branch cue. Null-safe: appears only once pico_competitors.json has loaded.
  const pm=(PICOCOMP&&PICOCOMP.meta)||null;
  if(pm&&pm.n_provinces_pico_outnumbers_autox!=null){
    const prows=Array.isArray(PICOCOMP.provinces)?PICOCOMP.provinces:[];
    let worst=null; prows.forEach(r=>{ if(!worst||(r.outnumber||0)>(worst.outnumber||0)) worst=r; });
    const wstr=(worst&&(worst.outnumber||0)>0)
      ? ` · worst ${worst.th} (${(worst.pico_total||0).toLocaleString()} vs ${(worst.autox_branches||0).toLocaleString()})` : '';
    html+=`<div class="cc-sub2"${html?'':' style="margin-top:0"'}>Sub-scale rival pressure · PICO-finance ${TAG_M}</div>`;
    html+=ccRow(`Outnumbered in ${pm.n_provinces_pico_outnumbers_autox} of ${pm.n_provinces||77} provinces`,
      `${(pm.pico_total||0).toLocaleString()} licensed PICO operators nationally vs ${(pm.autox_total||0).toLocaleString()} AutoX branches${wstr} (FPO registry)`,
      `${pm.n_provinces_pico_outnumbers_autox}`,'prov. outgunned','var(--agri)');
  }
  // COMPETITOR COVERAGE — national census completeness (competitor_coverage.json totals). A confidence
  // flag on the coverage signals below, not market share. Omitted gracefully if absent.
  const cct=(COMPCOV&&COMPCOV.meta&&COMPCOV.meta.totals)||null;
  if(cct&&cct.coverage_pct!=null){
    html+=`<div class="cc-sub2"${html?'':' style="margin-top:0"'}>Competitor coverage · census completeness ${TAG_M}</div>`;
    html+=ccRow(`Located ${(cct.found||0).toLocaleString()} of ~${(cct.expected||0).toLocaleString()} rival branches`,
      'lower-bound census · a confidence flag on the coverage signal below, not market share',
      `${cct.coverage_pct.toFixed(0)}%`,'coverage','var(--merch)');
  }
  // thinnest-coverage districts from amphoe.json — where AutoX presence is thin vs demand, shown with
  // measured rival counts (a competitive-exposure read; NOT an open-a-branch recommendation).
  if(AMP&&AMP.length){
    const top=AMP.slice().sort((a,b)=>(b.whitespace||0)-(a.whitespace||0)).slice(0,3);
    // honest subhead: only advertise the measured extras that actually loaded.
    const extras=[]; if(aoccHasData()) extras.push('borrower base'); if(compHasData()) extras.push('rivals');
    const extraTag=extras.length?` <span class="sub">+ ${extras.join(' &amp; ')} ${TAG_M}</span>`:'';
    html+=`<div class="cc-sub2"${html?'':' style="margin-top:0"'}>Thinnest coverage · districts ${TAG_E}${extraTag}</div>`;
    html+=top.map(a=>{const nm=a.name_measured?a.name:a.name_en;
      const where=`${a.province_th} · ${a.region}`;
      // committee trim: max ~2-3 short bits so the gold score leads the row. Keep the zero-branch
      // flag (real signal); drop the occupation-base phrase (it lives in the branch popup).
      const bits=[where];
      if(a.branches===0) bits.push('no AutoX yet');
      const cn=ampCompCount(a);
      if(cn===0) bits.push('0 rivals ≤5km ✦');
      else if(cn!=null) bits.push(`${cn} rival${cn===1?'':'s'} ≤5km`);
      return ccRow(`${nm} <span class="sub">${a.name_measured?a.name_en:''}</span>`,bits.join(' · '),
        `★ ${(a.whitespace||0).toFixed(0)}`,'coverage gap','var(--gold)');}).join('');
  } else {
    html+=skelRows(3);
  }
  // top provinces by mean district coverage gap (rolled up from amphoe)
  if(AMP&&AMP.length){
    const byP={};
    AMP.forEach(a=>{const k=a.province_th; const o=byP[k]||(byP[k]={th:k,region:a.region,sum:0,n:0,zero:0});
      o.sum+=(a.whitespace||0); o.n++; if(a.branches===0)o.zero++;});
    const provs=Object.values(byP).map(o=>({...o,avg:o.sum/o.n})).sort((a,b)=>b.avg-a.avg).slice(0,3);
    html+=`<div class="cc-sub2">Top provinces · mean coverage gap ${TAG_E}</div>`;
    html+=provs.map(o=>ccRow(`${o.th}`,`${o.region} · ${o.zero} district${o.zero===1?'':'s'} with no AutoX`,
      `★ ${o.avg.toFixed(0)}`,'avg','var(--gold)')).join('');
  }
  box.innerHTML=html;
}

// WHAT IS GETTING RISKIER — worst crop-stress province, motorcycle-heavy collateral, gold-up vs pickup.
function renderHomeRisk(){
  const box=$('#cc-risk-body'); if(!box||!META) return;
  let html='';
  // LEAD WITH THE VERDICT — most-stressed provinces by composite risk (province_risk.json).
  // Pull ONLY from loaded data; omit gracefully if absent (no placeholder, no fabrication).
  if(priskHasData()){
    const top=PRISK_LIST.slice(0,3).filter(p=>p&&p.province);
    if(top.length){
      const names=top.map(p=>p.province).join(', ');
      const dom=priskDom(top[0]);
      html+=`<div class="cc-sub2" style="margin-top:0">Most stressed · composite risk ${TAG_E}</div>`;
      html+=ccRow(names,`${top[0].region||''} · driven by ${riskDriverLabel(dom)}`,
        `▲ ${(top[0].mean_risk||0).toFixed(0)}`,`p90 ${(top[0].p90_risk||0).toFixed(0)}`,'var(--agri)');
    }
  }
  // structurally riskiest province — composite of MEASURED household DTI + unemployment percentiles
  // (province_stress_index.json, build_province_stress.py). Distinct from the composite-risk verdict
  // above (that one blends agri/collateral/merchant/unemployment at province level); this one is the
  // pure household-leverage read. Omitted gracefully when the file hasn't loaded yet / is absent.
  if(pstressHasData()&&PSTRESS_LIST.length){
    const p=PSTRESS_LIST[0];
    html+=`<div class="cc-sub2">Structurally riskiest · DTI + unemployment ${TAG_E}</div>`;
    html+=ccRow(`${p.province} <span class="sub">${p.region||''}</span>`,
      `DTI ${p.debt_to_income!=null?(+p.debt_to_income).toFixed(2)+'×':'—'} · unemployment ${p.unemployment_rate!=null?(+p.unemployment_rate).toFixed(1)+'%':'—'} (NSO, measured)`,
      `▲ ${(p.composite_stress||0).toFixed(0)}`,'composite','var(--agri)');
  }
  // lowest-paid occupation nationally (occupation_income.json) — a concrete income-floor fact,
  // same rank-1-surfacing pattern already shipped on Exposure; mirrored here per the 2026-07-05 (8)
  // backlog follow-up ("Home doesn't yet surface the same fact").
  if(occincHasData()){
    const c=OCCINC_LIST[0];
    html+=`<div class="cc-sub2">Lowest-paid occupation nationally ${TAG_M}</div>`;
    html+=ccRow(`${c.label}`,
      `worst: ${c.min_province} ฿${(c.min_value||0).toLocaleString()}/mo (NSO SES 2566, measured)`,
      `฿${(c.national_avg||0).toLocaleString()}`,'national avg/mo','var(--agri)');
  }
  // single riskiest BRANCH (branch_risk.json, index-aligned to DATA) — names the sharpest single point.
  if(briskHasData()&&DATA&&DATA.length===BRISK.length){
    let bi=-1,bv=-1; for(let i=0;i<BRISK.length;i++){const v=(BRISK[i]&&BRISK[i].composite_risk)||0; if(v>bv){bv=v;bi=i;}}
    if(bi>=0){const e=BRISK[bi], d=DATA[bi];
      html+=`<div class="cc-sub2">Riskiest single branch ${TAG_E}</div>`;
      html+=ccRow(`${d.n||e.code} <span class="sub">${d.v||''}${d.r?' · '+d.r:''}</span>`,
        `driven by ${riskDriverLabel(e.top_driver)}`,
        `▲ ${(e.composite_risk||0).toFixed(0)}`,'composite','var(--agri)');
    }
  }
  // worst crop-household stress region/province (crop_stress.json)
  if(CSTRESS_LIST&&CSTRESS_LIST.length){
    const w=CSTRESS_LIST[0]; const sv=Math.round((w.agri_stress||0)*100);
    const dom=(w.crop_mix&&w.crop_mix[0])||{};
    html+=`<div class="cc-sub2" style="margin-top:0">Worst crop-household stress ${TAG_E}</div>`;
    html+=ccRow(`${w.th} <span class="sub">${w.region||''}</span>`,
      `${dom.crop||'crops'} ${dom.share!=null?Math.round(dom.share*100)+'%':''} · price ${w.price_stress!=null?(w.price_stress>0?'+':'')+w.price_stress+'%':'—'}`,
      `▲ ${sv}`,'agri-stress','var(--agri)');
  } else { html+=skelRows(3); }
  // most motorcycle-heavy collateral provinces (DLT, measured) — lowest-recovery title collateral
  const moto=collatMixRows().slice(0,2);
  if(moto.length){
    html+=`<div class="cc-sub2">Most motorcycle-heavy collateral ${TAG_M}</div>`;
    html+=moto.map(p=>ccRow(`${p.th} <span class="sub">${p.region}</span>`,
      `${p.branches} branches · lowest-recovery title collateral`,
      `${p.moto}%`,'moto share','var(--agri)')).join('');
  }
  // COLLATERAL RECOVERY OUTLOOK — lead with the national read from collateral_outlook.json when
  // loaded (firming vs softening + most-at-risk province), then the vehicle-title backings.
  // AutoX lends against VEHICLE TITLES (not gold), so gold-collateral is not shown.
  const nat=COLLO&&COLLO.national;
  if(nat&&nat.exposure_weighted_outlook!=null){
    const o=nat.exposure_weighted_outlook, firm=o>=0;
    html+=`<div class="cc-sub2">Collateral recovery outlook · national ${TAG_E}</div>`;
    html+=ccRow(firm?'Recovery value firming':'Recovery value softening',
      `${nat.n_firming||0}/${nat.n_provinces||0} provinces firming · most at-risk ${nat.most_at_risk_province||'—'} (motorcycle-title heavy)`,
      `${firm?'+':''}${o.toFixed(2)}`,'index 0–1','var(--up)');
  }
  html+=`<div class="cc-sub2">Vehicle-title collateral value · under pressure</div>`;
  html+=ccRow(`Diesel-pickup collateral ${TAG_E}`,'used-pickup glut + EV transition · editorial watch','↓ pressure','value at risk','var(--agri)');
  html+=ccRow(`Used-motorcycle collateral ${TAG_M}`,'smallest, most volatile, lowest-recovery title collateral','↓ volatile','lowest recovery','var(--agri)');
  box.innerHTML=html;
}

// LIVE fuel prices (data/fuel_prices.json, build_fuel_prices.py <- Bangchak daily pull).
// Diesel = pickup/farm title-loan collateral; gasohol = motorcycle title-loan collateral.
let FUEL=null, fuelLoaded=false, fuelPromise=null;
function loadFuelPrices(){
  if(fuelPromise) return fuelPromise;
  fuelLoaded=true;
  fuelPromise=(async()=>{
    try{
      const r=await fetch('data/fuel_prices.json'); if(!r.ok) throw 0;
      const j=await r.json();
      FUEL=(j&&j.headline)?j:null;
    }catch(e){ FUEL=null; }
    return FUEL;
  })();
  return fuelPromise;
}

// MACRO — key commodity moves + retail fuel from META.board / FUEL.
function renderHomeMacro(){
  const box=$('#cc-macro-body'); if(!box||!META) return;
  let html='';
  // key commodity moves: 2 worst + 2 best crop/livestock YoY (borrower income drivers; gold is
  // NOT AutoX collateral, so it is excluded).
  const board=(META.board||[]);
  const agri=board.filter(b=>(b.seg==='Crops'||b.seg==='Livestock')&&b.yoy!=null).sort((a,b)=>a.yoy-b.yoy);
  const moves=agri.slice(0,2).concat(agri.slice(-2).reverse()).filter((b,i,arr)=>arr.indexOf(b)===i);
  html+=`<div class="cc-sub2" style="margin-top:0">Key commodity moves ${TAG_M} <span class="sub">World Bank price direction · borrower income</span></div>`;
  moves.forEach(b=>html+=ccRow(`${b.lab}`,b.note||'',`${b.yoy>0?'+':''}${b.yoy}%`,'YoY',b.yoy>=0?'var(--up)':'var(--agri)'));
  // live retail fuel prices (Bangchak, daily) — diesel tracks pickup/farm borrowers, gasohol
  // tracks motorcycle borrowers, AutoX's two dominant title-loan collateral types.
  if(FUEL&&FUEL.headline){
    const h=FUEL.headline;
    html+=`<div class="cc-sub2">Fuel prices ${TAG_M} <span class="sub">Bangchak retail, daily</span></div>`;
    html+=ccRow('Diesel','pickup / farm-vehicle borrowers',`฿${h.diesel}`,'THB/L','var(--agri)');
    html+=ccRow('Gasohol 95','motorcycle-title borrowers',`฿${h.gasohol95}`,'THB/L','var(--agri)');
  }
  box.innerHTML=html;
}

/* ---- DATA ROOM — provenance census (data/provenance.json, built by build_provenance.py) ----
   MEASURED / ESTIMATED / UNLABELLED counts + a per-layer table. The 'unlabelled' rows are the
   shame board: numeric layers shipping with no meta stamp. Null-safe: calm note if absent. */
let PROVEN=null,provenLoaded=false;
function loadProvenance(){
  if(provenLoaded) return Promise.resolve(PROVEN);
  return fetch('data/provenance.json').then(r=>r.ok?r.json():null)
    .then(j=>{PROVEN=j;provenLoaded=true;return j;})
    .catch(()=>{PROVEN=null;provenLoaded=true;return null;});
}
function prBytes(n){
  n=+n||0;
  if(n>=1048576) return (n/1048576).toFixed(n>=10485760?0:1)+' MB';
  if(n>=1024) return Math.round(n/1024)+' KB';
  return n+' B';
}
function prChip(cls){
  const map={measured:['m','measured'],estimated:['e','estimated'],unlabelled:['u','unlabelled']};
  const [k,lab]=map[cls]||['u','unlabelled'];
  return `<span class="cc-tag ${k}">${lab}</span>`;
}
function renderHomeDataRoom(){
  const box=$('#cc-dataroom-body'); if(!box) return;
  if(!provenLoaded){ return; }                                  // skeleton stays until the fetch resolves
  if(!PROVEN||!Array.isArray(PROVEN.layers)||!PROVEN.counts){
    box.innerHTML=`<div class="cc-empty">Provenance census not yet computed — run <span class="mono">pipeline/build_provenance.py</span>. The layer-by-layer data-room table fills in on the next data refresh.</div>`;
    return;
  }
  const c=PROVEN.counts, f=PROVEN.files||{};
  // headline: N layers, split three ways
  let html=`<div class="dr-head">`+
    `<span class="dr-total mono">${c.layers} layers</span>`+
    `<span class="dr-split">`+
      `<b style="color:var(--dr-m)">${c.measured}</b> measured`+
      ` · <b style="color:var(--dr-e)">${c.estimated}</b> estimated`+
      ` · <b style="color:var(--dr-u)">${c.unlabelled}</b> unlabelled`+
    `</span></div>`;
  // per-file shame note. `hidden` = unstamped member files that sit INSIDE otherwise-labelled
  // families (so they don't show as their own unlabelled row) — surfaced so collapsing hides nothing.
  const hidden=PROVEN.layers.reduce((s,L)=>s+(L.cls!=='unlabelled'?(L.n_unlabelled||0):0),0);
  if((f.unlabelled||0)>0){
    html+=`<div class="cc-sub2" style="margin-top:2px">${f.unlabelled} of ${f.total} files carry no meta stamp`+
      (hidden>0?` — incl. ${hidden} basemap file${hidden!==1?'s':''} inside otherwise-labelled families`:'')+
      `. These are the ones to source next.</div>`;
  }
  // FRESHNESS pulse — lead with the answer: how far behind our newest committed data each layer
  // sits. Age is measured against the freshest dated layer (deterministic, from build_provenance.py),
  // so it never reads a wall clock. Only ISO-dated layers get an age; undated ones are stated plainly.
  const fr=PROVEN.freshness;
  if(fr&&fr.n_dated){
    const staleN=(fr.stale||[]).length, old=fr.oldest;
    html+=`<div class="dr-fresh cc-sub2">`+
      `<b>Freshness</b> — newest committed data <b>${dqEsc(fr.freshest.vintage)}</b>; `+
      `oldest dated layer <b>${old.age_days}d</b> behind (<span class="mono">${dqEsc(old.file)}</span> · ${dqEsc(old.vintage)}); `+
      (staleN?`<b style="color:var(--dr-u)">${staleN}</b>`:`<b>0</b>`)+` of ${fr.n_dated} dated layers &gt;${fr.stale_over_days}d stale`+
      (fr.n_undated?`. ${fr.n_undated} layers carry no machine-readable date.`:`.`)+
      `</div>`;
  }
  const staleThresh=(fr&&fr.stale_over_days)||180;
  // table: layer | chip | source | vintage/size
  html+=`<div class="dr-tblwrap"><table class="tbl dr-tbl"><thead><tr>`+
    `<th>Layer</th><th>Provenance</th><th>Source / builder</th><th class="num">Vintage · size</th>`+
    `</tr></thead><tbody>`;
  PROVEN.layers.forEach(L=>{
    const fam=L.family;
    const name=dqEsc(L.file)+(fam?` <span class="sub">×${L.n_files}</span>`:'');
    const shame=(L.n_unlabelled>0&&L.cls!=='unlabelled')?` <span class="dr-shame" title="${L.n_unlabelled} member file(s) have no meta stamp">△ ${L.n_unlabelled} unstamped</span>`:'';
    const src=L.source?dqEsc(L.source):(L.cls==='unlabelled'?'<span class="dr-shame">— no meta.source / meta.provenance</span>':'—');
    const cnt=L.count?`${L.count.toLocaleString()} ${dqEsc(L.count_of||'')}`:'';
    const vint=L.vintage?dqEsc(L.vintage)+' · ':'';
    const age=(L.age_days!=null)?`<span class="dr-age${L.age_days>staleThresh?' dr-age-stale':''}" title="${L.age_days} days behind the freshest committed layer">${L.age_days}d</span> · `:'';
    html+=`<tr class="dr-${L.cls}">`+
      `<td><span class="dr-name">${name}</span>${shame}`+(L.label?`<span class="dr-desc">${dqEsc(L.label)}</span>`:'')+`</td>`+
      `<td>${prChip(L.cls)}</td>`+
      `<td class="dr-src"><span title="${L.source?dqEsc(L.source):''}">${src}</span></td>`+
      `<td class="num mono dr-size">${vint}${age}${prBytes(L.bytes)}${cnt?`<span class="dr-cnt">${cnt}</span>`:''}</td>`+
      `</tr>`;
  });
  html+=`</tbody></table></div>`;
  html+=`<div class="cc-qfoot sub">MEASURED / ESTIMATED are read from each layer's own <span class="mono">meta</span> stamp; UNLABELLED = no stamp at all (the shame board). Per-province road/water/building basemaps are collapsed into one row each — see <span class="mono">provenance.json</span>. Generated by <span class="mono">build_provenance.py</span>.</div>`;
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
  // coverage gap (thinnest AutoX coverage vs demand — a competitive-exposure read, not a growth plan)
  if(AMP&&AMP.length){
    AMP.slice().sort((a,b)=>(b.whitespace||0)-(a.whitespace||0)).slice(0,3).forEach(a=>{
      rows.push(['coverage_gap_district',(a.name_measured?a.name:a.name_en),`${a.province_th} | ${a.region} | ${a.branches} AutoX inside`,(a.whitespace||0).toFixed(0),'estimated']);});
    const byP={}; AMP.forEach(a=>{const o=byP[a.province_th]||(byP[a.province_th]={s:0,n:0,r:a.region});o.s+=(a.whitespace||0);o.n++;});
    Object.entries(byP).map(([th,o])=>[th,o.r,o.s/o.n]).sort((a,b)=>b[2]-a[2]).slice(0,3).forEach(([th,r,avg])=>
      rows.push(['coverage_gap_province',th,r,avg.toFixed(0),'estimated']));
  }
  // risk
  if(CSTRESS_LIST&&CSTRESS_LIST.length){const w=CSTRESS_LIST[0];
    rows.push(['risk_crop_stress',w.th,`${w.region} | price ${w.price_stress}%`,Math.round((w.agri_stress||0)*100),'estimated']);}
  collatMixRows().slice(0,2).forEach(p=>rows.push(['risk_moto_collateral',p.th,`${p.region} | ${p.branches} branches`,p.moto+'%','measured']));
  const gold=(META.board||[]).find(b=>/gold/i.test(b.lab||''));
  if(gold) rows.push(['collateral_gold','Gold',gold.note||'',(gold.yoy>0?'+':'')+gold.yoy+'%','measured']);
  rows.push(['collateral_pickup','Diesel-pickup','used-pickup glut + EV transition','pressure (down)','editorial']);
  // macro
  (META.board||[]).filter(b=>b.seg==='Crops'&&b.yoy!=null).sort((a,b)=>a.yoy-b.yoy).slice(0,2).forEach(b=>
    rows.push(['macro_commodity',b.lab,b.note||'',(b.yoy>0?'+':'')+b.yoy+'%','measured']));
  // movers
  if(DELTAS&&!DELTAS.baseline&&DELTAS.branches){
    (DELTAS.branches||[]).slice(0,3).forEach(d=>rows.push(['risk_mover',d.n,`${d.v} | ${d.r}`,`comp ${d.comp} (d ${d.d_comp})`,'estimated']));
  } else { rows.push(['risk_mover','(baseline)','one vintage captured — trends after next refresh','','']); }
  // watchlist
  watchLoad().forEach(w=>rows.push(['watchlist',w.label,w.sub||'',w.val||'',(w.prov||'')]));
  const csv=rows.map(r=>r.map(v=>`"${String(v==null?'':v).replace(/"/g,'""')}"`).join(',')).join('\n');
  const blob=new Blob(['\ufeff',csv],{type:'text/csv;charset=utf-8;'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='autox_command_center_brief.csv'; a.click(); URL.revokeObjectURL(a.href);
}

boot();

/* ============================================================================
   PRINT / EXPORT PER TAB  (owner ask 2026-08-01)
   -------------------------------------------------------------------------
   Before this, @media print hard-coded `#v-home` — so whatever tab you were
   reading, Ctrl-P silently printed the Command Center instead. Now the print
   is OF THE TAB YOU ARE ON, and it carries two things the screen does not:

     1. a written SUMMARY of the tab, generated from the same rendered DOM the
        reader is looking at (so it can never drift from what is on screen);
     2. ALL the supporting data — every collapsed <details> is opened, every
        drill is un-hidden, and a provenance appendix lists each layer the tab
        read with its measured/estimated label and vintage.

   The summary is assembled from what the renderers already generate — verdict
   cards, answer-band tiles, section headings — rather than a second, parallel
   set of hand-written prose that would go stale the moment a number moved.
   ============================================================================ */
const PRINT_TITLES={'v-home':'Command centre','v-overview':'① Macro — the backdrop moving the book',
  'v-assist':'Assistance — who needs help now','v-map':'National map','v-acq':'Competition',
  'v-exposure':'Risk — where the book sits','v-sim':'Scenario simulator','v-trend':'Risk trend',
  'v-branches':'Branches','v-provinces':'Provinces','v-market':'Market'};

function printTxt(el){ return el?String(el.innerText||'').replace(/\s+/g,' ').trim():''; }

/* Collect the tab's own generated conclusions. Verdict cards and answer tiles are
   where the renderers already put "the answer"; lifting them is what keeps this
   summary honest instead of inventing a second narrative. */
function buildPrintSummary(view){
  const bits=[];
  const band=view.querySelector('.answerband');
  if(band){
    const tiles=[...band.querySelectorAll('.ab')].map(t=>{
      const k=printTxt(t.querySelector('.ab-k')), v=printTxt(t.querySelector('.ab-v')),
            m=printTxt(t.querySelector('.ab-mv'));
      return k&&v?`<li><b>${k}</b> — <span class="mono">${v}</span>${m?` <i>${m}</i>`:''}</li>`:'';
    }).filter(Boolean);
    if(tiles.length) bits.push(`<h3>Headline numbers</h3><ul class="pr-kv">${tiles.join('')}</ul>`);
  }
  // The three classes the renderers use for a GENERATED conclusion, across all tabs:
  // .verdict (Macro/Risk/Simulator), .insight (Competition — 21 of them), .cc-thesis (Command
  // centre). Selecting only .verdict gave Competition an empty summary, which is the tab whose
  // conclusions are most worth carrying into a printout.
  const verdicts=[...view.querySelectorAll('.verdict,.insight,.cc-thesis')]
    .filter(v=>v.style.display!=='none')
    .map(v=>printTxt(v)).filter(t=>t.length>25);
  const uniq=[...new Set(verdicts)];
  if(uniq.length) bits.push(`<h3>What the tab concludes</h3><ul class="pr-v">`
    +uniq.map(t=>`<li>${t}</li>`).join('')+`</ul>`);
  const secs=[...view.querySelectorAll('details.ovsec,details.compsec')].map(d=>{
    const h=printTxt(d.querySelector('summary h2')), w=printTxt(d.querySelector('.ovsec-what'));
    const nT=d.querySelectorAll('table').length, nC=d.querySelectorAll('svg.cbars,svg.csp').length;
    return h?`<tr><td><b>${h}</b></td><td>${w||''}</td><td class="mono">${nT} tables · ${nC} charts</td></tr>`:'';
  }).filter(Boolean);
  if(secs.length) bits.push(`<h3>What follows, in order</h3>`
    +`<table class="tbl pr-toc"><tr><th>Section</th><th>Contents</th><th>Evidence</th></tr>${secs.join('')}</table>`);
  return bits.length?bits.join(''):'<p>This tab has no generated summary block yet — the supporting data follows in full.</p>';
}

/* Provenance appendix: what this tab actually read, and whether each number in it is
   measured or estimated. This is the "supporting data behind" in the auditable sense —
   a reader who disagrees with a figure can see which layer produced it. */
function buildPrintProvenance(view){
  const seen=new Map();
  view.querySelectorAll('.cc-provenance,.ic-prov,[data-prov]').forEach(el=>{
    const t=printTxt(el); if(t.length>30&&!seen.has(t)) seen.set(t,1);
  });
  const tags=[...new Set([...view.querySelectorAll('.tag')].map(printTxt).filter(Boolean))];
  let h='';
  if(tags.length) h+=`<p class="pr-tags">${tags.map(t=>`<span>${t}</span>`).join('')}</p>`;
  if(seen.size) h+=[...seen.keys()].map(t=>`<p class="pr-p">${t}</p>`).join('');
  return h||'<p class="pr-p">No provenance block is emitted on this tab.</p>';
}

/* Open everything, so nothing the reader needs is hidden inside a collapsed section
   or an un-pressed drill. Remembers prior state and restores it after printing. */
let PRINT_STATE=null;
function expandForPrint(view){
  PRINT_STATE={details:[],hidden:[]};
  view.querySelectorAll('details').forEach(d=>{ PRINT_STATE.details.push([d,d.open]); d.open=true; });
  view.querySelectorAll('[hidden]').forEach(e=>{ PRINT_STATE.hidden.push(e); e.hidden=false; });
}
function restoreAfterPrint(){
  if(!PRINT_STATE) return;
  PRINT_STATE.details.forEach(([d,o])=>{ d.open=o; });
  PRINT_STATE.hidden.forEach(e=>{ e.hidden=true; });
  PRINT_STATE=null;
  const h=document.getElementById('print-head'); if(h) h.remove();
  const a=document.getElementById('print-appendix'); if(a) a.remove();
  document.documentElement.classList.remove('printing');
}

function preparePrint(){
  const view=document.querySelector('.view.on'); if(!view) return;
  restoreAfterPrint();                       // idempotent: a second Ctrl-P must not stack blocks
  document.documentElement.classList.add('printing');
  expandForPrint(view);
  const title=PRINT_TITLES[view.id]||view.id.replace(/^v-/,'');
  const vint=(META&&META.updated)?META.updated:'';
  const head=document.createElement('div');
  head.id='print-head'; head.className='print-only';
  head.innerHTML=`<div class="pr-mast"><div class="pr-brand">AutoX · เงินไชโย — credit intelligence</div>`
    +`<h1>${title}</h1>`
    +`<div class="pr-meta">Data vintage <b>${vint||'—'}</b> · every figure below is labelled measured or estimated`
    +` · loan-tape figures are no-PII aggregates, cells under 30 accounts suppressed</div></div>`
    +`<div class="pr-sum">${buildPrintSummary(view)}</div>`;
  view.insertBefore(head,view.firstChild);
  const app=document.createElement('div');
  app.id='print-appendix'; app.className='print-only';
  app.innerHTML=`<h3>Provenance — what produced these numbers</h3>${buildPrintProvenance(view)}`;
  view.appendChild(app);
}
window.addEventListener('beforeprint',preparePrint);
window.addEventListener('afterprint',restoreAfterPrint);
document.addEventListener('click',e=>{
  const b=e.target.closest&&e.target.closest('#printTab'); if(!b) return;
  e.preventDefault(); preparePrint(); window.print();
});
