"""
DEFUNCT — build_platform.py

This script assembled platform/rayong-province.html and platform/rayong-catchment.html from
source parts (rayong-head.html, rayong-app.js, catch-head.html, catch-app.js) that were kept
alongside it in pipeline/. Those source files no longer exist — the pages are now committed
directly as self-contained monolithic files. Running this script will hard-error on the first
open() call.

Kept on disk for historical context only. Do NOT run it. If the pages ever need regenerating
from parts, reconstruct the source files first.

Last time this produced valid output: pre-2026 consolidation of rayong-catchment.html.
"""
import re

NAV_CSS = """
#nav{position:fixed;top:0;left:0;right:0;z-index:2000;display:flex;align-items:center;gap:2px;
 padding:0 8px;height:44px;background:rgba(8,11,18,.97);border-bottom:1px solid #1d2738;backdrop-filter:blur(10px);
 overflow-x:auto;scrollbar-width:none}
#nav::-webkit-scrollbar{display:none}
#nav .nb{font:700 13px 'IBM Plex Sans Thai',sans-serif;color:#eef1f7;white-space:nowrap;padding:0 10px 0 4px;flex:none}
#nav .nb b{color:#E0A93B;margin:0 1px}
#nav a{flex:none;color:#8a94a8;text-decoration:none;font:500 12.5px 'IBM Plex Sans Thai',sans-serif;
 padding:6px 11px;border-radius:7px;white-space:nowrap}
#nav a.on{color:#fff;background:#1a2336}
#nav a:active{background:#161d2c}
"""

def nav_html(active):
    # Rayong 3D + Catchment were consolidated into one page (rayong-catchment.html).
    # 'province' is kept as an alias key so nav_html('province') still resolves to the unified tab.
    links=[("index.html#overview","Overview","overview"),
           ("index.html#map","National","map"),
           ("rayong-catchment.html","Rayong 3D",("catchment","province")),
           ("index.html#acq","Acquisition","acq"),
           ("index.html#branches","Branches","branches")]
    def cls(k): return ' class="on"' if (active in k if isinstance(k,tuple) else k==active) else ''
    a="".join(f'<a href="{h}"{cls(k)}>{t}</a>' for h,t,k in links)
    return f'<nav id="nav"><span class="nb">AutoX<b>·</b>เงินไชโย</span>{a}</nav>'

# ---------- PROVINCE PAGE ----------
head=open('rayong-head.html').read()
app=open('rayong-app.js').read()
# function-wrap app, read window.RY
app=app.replace("(function(){\n'use strict';","window.initRayong=function(){\n'use strict';",1)
app=app.rstrip().rsplit("})();",1)[0]+"};"
# remove floating title (nav replaces it), push map down for nav
head=head.replace('<div id="title"><h1>Rayong <b>·</b> เงินไชโย</h1><p>EEC deep-dive — 57 branches · 8 districts · live competitors</p></div>','')
head=head.replace('</style>', NAV_CSS + '\n#map{top:44px}\n#title{display:none}\n.err{top:44px}\n</style>')
head=head.replace('<div id="map"></div>', nav_html('province')+'\n<div id="map"></div>')
loader=f"""<script>
(function(){{
 var box=document.createElement('div');box.className='err';box.style.color='#8a94a8';box.textContent='Loading Rayong province…';document.body.appendChild(box);
 fetch('data/rayong_province.json').then(function(r){{if(!r.ok)throw new Error('data '+r.status);return r.json();}})
  .then(function(d){{window.RY=d;box.remove();window.initRayong();}})
  .catch(function(e){{box.style.color='#E0474B';box.textContent='Could not load province data: '+e.message;}});
}})();
</script>"""
html=head.replace('<!--PAYLOAD-->','').replace('<!--APP-->','<script>'+app+'</script>\n'+loader)
open('platform/rayong-province.html','w').write(html)
print("province page", len(html)//1024,"KB")

# ---------- CATCHMENT PAGE ----------
chead=open('catch-head.html').read()
capp=open('catch-app.js').read()
capp=capp.replace("(function(){\n'use strict';","window.initCatch=function(){\n'use strict';",1)
capp=capp.rstrip().rsplit("})();",1)[0]+"};"
# the strip already has a title; add nav above, push everything down by 44
chead=chead.replace('</style>', NAV_CSS + '\n#strip{top:44px}\n.side{top:96px}\n#ctl{top:94px}\n.err{top:44px}\n@media(max-width:820px){.side{top:90px}#ctl{top:90px}}\n</style>')
chead=chead.replace('<div id="map"></div>', nav_html('catchment')+'\n<div id="map"></div>')
cloader=f"""<script>
(function(){{
 var box=document.createElement('div');box.className='err';box.style.color='#8a94a8';box.textContent='Loading catchment…';document.body.appendChild(box);
 fetch('data/rayong_catchment.json').then(function(r){{if(!r.ok)throw new Error('data '+r.status);return r.json();}})
  .then(function(d){{window.CA=d;box.remove();window.initCatch();}})
  .catch(function(e){{box.style.color='#E0474B';box.textContent='Could not load catchment data: '+e.message;}});
}})();
</script>"""
chtml=chead.replace('<!--PAYLOAD-->','').replace('<!--APP-->','<script>'+capp+'</script>\n'+cloader)
open('platform/rayong-catchment.html','w').write(chtml)
print("catchment page", len(chtml)//1024,"KB")
