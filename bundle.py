#!/usr/bin/env python3
"""
bundle.py — produce a SINGLE self-contained HTML file you can drop on GitHub
(or GitHub Pages, or just double-click).

It inlines every data file the app fetches and installs a tiny fetch() shim so
index.html's loading code runs UNCHANGED: any request for ./data/<file> is
served from the embedded copy instead of the network. External calls (Leaflet
CDN, fonts, CARTO basemap tiles, OSM Overpass, MassGIS parcels) still go out to
the internet, and the ♥ Like feature falls back to localStorage (no server).

Run:  python3 bundle.py        ->  writes  ma-opportunity-map.html
Read-only on all inputs; only writes the one output file.
"""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SRC  = os.path.join(HERE, "index.html")
OUT  = os.path.join(HERE, "ma-opportunity-map.html")

# The exact files index.html fetches from ./data/ (see boot() in index.html).
FILES = [
    "manifest.json",
    "towns.geojson",
    "neighborhoods.geojson",
    "town_detail.json",
    "neighborhoods_detail.json",
    "listings.json",
    "prelist.json",
    "town_research.json",
    "neighborhoods_research.json",
]

def embed_safe(text):
    """Make JSON safe to sit inside <script type="application/json">.
    In JSON, '<' only ever appears inside string values, where the \\u003c
    escape is valid and parses back to '<'. Escaping every '<' guarantees the
    text can never contain '</script>' (or '<!--'), so the block can't break out.
    JSON.parse() restores the original content exactly."""
    return text.replace("<", "\\u003c")

def main():
    if not os.path.exists(SRC):
        sys.exit("index.html not found next to bundle.py")
    html = open(SRC, encoding="utf-8").read()

    blocks = []
    total = 0
    for fn in FILES:
        fp = os.path.join(DATA, fn)
        if not os.path.exists(fp):
            print(f"  ! skip (missing): {fn}")
            continue
        raw = open(fp, encoding="utf-8").read()
        # validate it's real JSON so we never embed a corrupt snapshot
        try:
            json.loads(raw)
        except Exception as e:
            sys.exit(f"{fn} is not valid JSON: {e}")
        total += len(raw)
        blocks.append(
            f'<script type="application/json" data-bundle="data/{fn}">'
            f'{embed_safe(raw)}</script>'
        )
        print(f"  + embedded data/{fn}  ({len(raw):,} bytes)")

    shim = """<script>
/* fetch() shim: serve embedded ./data/* offline; everything else hits network. */
(function(){
  var orig = window.fetch ? window.fetch.bind(window) : null;
  var MAP = {};
  var nodes = document.querySelectorAll('script[type="application/json"][data-bundle]');
  for (var i=0;i<nodes.length;i++){ MAP[nodes[i].getAttribute('data-bundle')] = nodes[i]; }
  function norm(u){
    try{ u = String(u); }catch(e){ return null; }
    var q = u.indexOf('?'); if(q>=0) u = u.slice(0,q);
    var k = u.indexOf('data/'); if(k>=0) return 'data/' + u.slice(k+5);
    return null;
  }
  window.fetch = function(input, init){
    var url = (input && input.url) ? input.url : input;
    var key = norm(url);
    if (key && MAP[key]){
      return Promise.resolve(new Response(MAP[key].textContent,
        {status:200, headers:{'Content-Type':'application/json'}}));
    }
    if (orig) return orig(input, init);
    return Promise.reject(new Error('offline and not bundled: ' + url));
  };
})();
</script>
"""

    inject = "\n" + shim + "\n" + "\n".join(blocks) + "\n"
    anchor = "</title>"
    if anchor not in html:
        sys.exit("could not find </title> anchor in index.html")
    html = html.replace(anchor, anchor + inject, 1)

    open(OUT, "w", encoding="utf-8").write(html)
    print(f"\n  wrote {OUT}")
    print(f"  data inlined: {total:,} bytes across {len(blocks)} files")
    print(f"  output size:  {os.path.getsize(OUT):,} bytes")

if __name__ == "__main__":
    main()
