/* pmtiles-layer.js — stream Overture building tiles from a single hosted .pmtiles archive.
 *
 * The 3D scenes already stream an {z}/{x}/{y}.pbf MVT pyramid natively via deck.MVTLayer (mvtUrl).
 * A PMTiles archive is one file (range-request reads) — far easier to HOST (Vercel Blob / Cloudflare
 * R2) than millions of .pbf tiles — but deck.gl 8.9.35 can't read it without a small reader. This
 * file is that reader: window.makePMTilesBuildingLayer(deck, opts) returns a deck.TileLayer that
 * pulls each tile's bytes from the PMTiles archive, decodes the MVT, and extrudes the buildings with
 * the same warm, lighting-capped style as the rest of the scene (specular ZEROED -> no blow-out).
 *
 * Dependencies are loaded ON DEMAND (only when a pmtilesUrl is actually configured) via dynamic
 * import() of bundled ESM from a CDN, so there is ZERO cost until tiles are hosted:
 *   pmtiles (range reads) · @mapbox/vector-tile + pbf (MVT decode).
 * EVERYTHING is guarded: if the libs/CDN/archive are unavailable, getTileData returns null and the
 * scene simply falls back to its curated catchment — it never throws. NO fabricated data: it renders
 * only the footprints actually present in the hosted real-Overture archive.
 *
 * opts: { url, sourceLayer='buildings', minZoom=9, maxZoom=15, dark=true }
 */
(function(){
  if (typeof window === 'undefined') return;

  // --- lazy, cached loaders -----------------------------------------------------------------
  var _libs = null;       // Promise<{PMTiles, VectorTile, Pbf}> | null
  var _archives = {};     // url -> PMTiles instance

  function loadLibs(){
    if (_libs) return _libs;
    _libs = (async function(){
      // bundled ESM (deps inlined by esm.sh) — avoids fragile UMD globals. Pinned versions.
      var pm = await import('https://esm.sh/pmtiles@3.2.1');
      var vt = await import('https://esm.sh/@mapbox/vector-tile@2.0.3');
      var pbf = await import('https://esm.sh/pbf@3.2.1');
      return { PMTiles: pm.PMTiles, VectorTile: vt.VectorTile, Pbf: (pbf.default || pbf.Pbf || pbf) };
    })().catch(function(e){
      try{ console.warn('[pmtiles] library load failed — falling back to curated catchment:', e && e.message); }catch(_){}
      _libs = null;           // allow a later retry
      return null;
    });
    return _libs;
  }

  function archive(PMTiles, url){
    if (!_archives[url]) _archives[url] = new PMTiles(url);
    return _archives[url];
  }

  // height (m) from a building feature's properties; Overture/tippecanoe carry `height`.
  function heightOf(p){
    if (!p) return 4;
    var h = +(p.height || p.render_height || p.h || 0);
    if (!isFinite(h) || h <= 0) h = p.num_floors ? (+p.num_floors * 3) : (p.levels ? (+p.levels * 3) : 4);
    return h > 0 ? h : 4;
  }

  // --- public factory -----------------------------------------------------------------------
  window.makePMTilesBuildingLayer = function(deck, opts){
    try{
      opts = opts || {};
      if (!deck || !deck.TileLayer || !deck.GeoJsonLayer || !opts.url) return null;
      var SRC = opts.sourceLayer || 'buildings';
      var DARK = opts.dark !== false;
      var clamp = function(v){ return Math.max(0, Math.min(255, Math.round(v))); };
      var RAMP = DARK ? [[44,38,32],[156,108,50],[238,182,86]]
                      : [[210,203,191],[186,176,161],[142,128,108]];   // light ramp = curated light warm-gray mass (match the static scene)
      var rampAt = function(t){ var s=t<.5?0:1, lt=t<.5?t*2:(t-.5)*2; var a=RAMP[s], b=RAMP[s+1];
        return [a[0]+(b[0]-a[0])*lt, a[1]+(b[1]-a[1])*lt, a[2]+(b[2]-a[2])*lt]; };
      var H_LO = 3, H_HI = 35;   // fixed band for streamed tiles (no global sort available)
      var _loadedFired = false;  // fire opts.onLoaded ONCE, on the first tile that carries real features

      return new deck.TileLayer({
        id: 'pmtiles-bldg',
        minZoom: opts.minZoom || 9,
        maxZoom: opts.maxZoom || 15,
        tileSize: 512,
        // tell the host page the stream is ACTUALLY delivering buildings (not just constructed).
        // The page keeps its curated catchment on screen until this fires, so a failed/blocked
        // stream (CDN down, esm.sh unreachable, empty coverage) can never blank the city.
        onTileLoad: function(tile){
          try{
            var d = tile && (tile.content || tile.data);
            if (!_loadedFired && d && d.length){ _loadedFired = true; if (opts.onLoaded) opts.onLoaded(); }
          }catch(_){}
        },
        // read + decode one tile from the PMTiles archive -> array of GeoJSON building features.
        getTileData: function(tile){
          var idx = (tile && tile.index) || tile;
          var z = idx.z, x = idx.x, y = idx.y;
          return loadLibs().then(function(L){
            if (!L) return null;
            var pm = archive(L.PMTiles, opts.url);
            return pm.getZxy(z, x, y).then(function(res){
              if (!res || !res.data) return null;
              var vtile = new L.VectorTile(new L.Pbf(res.data));
              var layer = vtile.layers[SRC] || vtile.layers[Object.keys(vtile.layers)[0]];
              if (!layer) return null;
              var feats = [];
              for (var i = 0; i < layer.length; i++){
                try{ feats.push(layer.feature(i).toGeoJSON(x, y, z)); }catch(_){}
              }
              return feats;
            }).catch(function(){ return null; });
          }).catch(function(){ return null; });
        },
        renderSubLayers: function(props){
          var data = props.data;
          if (!data || !data.length) return null;
          return new deck.GeoJsonLayer({
            id: props.id + '-geo',
            data: data,
            extruded: true, filled: true, stroked: true, wireframe: false,
            getElevation: function(f){ var h = heightOf(f.properties); return h * (h<10?1.5:h<22?2.1:2.8); },
            getFillColor: function(f){
              var h = heightOf(f.properties); var t = (h - H_LO) / (H_HI - H_LO); t = t<0?0:t>1?1:t;
              var m = rampAt(t); return [clamp(m[0]), clamp(m[1]), clamp(m[2]), DARK?236:214];
            },
            getLineColor: DARK ? [28,22,14,210] : [164,156,144,150],   // warm dark stroke (tiny footprints read as their stroke at city zoom)
            lineWidthMinPixels: 0.4,
            material: false, // FLAT: no lighting term exists -> the real-GPU whiteout is impossible by construction
            parameters: { depthTest: true }, pickable: false
          });
        }
      });
    }catch(e){
      try{ console.warn('[pmtiles] layer disabled:', e && e.message); }catch(_){}
      return null;
    }
  };
})();
