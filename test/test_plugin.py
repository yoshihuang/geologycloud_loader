"""Offscreen integration test for geologycloud_loader against a local fake API."""
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/home/claude/geologycloud_loader")

from qgis.testing import start_app  # noqa: E402

APP = start_app()

from qgis.PyQt.QtCore import QEventLoop, QTimer  # noqa: E402
from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes, QgsCoordinateReferenceSystem, QgsRectangle  # noqa: E402

SAMPLES = json.load(open(os.path.join(os.path.dirname(__file__), "samples.json"), encoding="utf-8"))
REQUESTS = []


def big_drill(n=30000):
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [121 + i * 1e-5, 24 + i * 1e-5]},
              "properties": {"Project_No": "P%05d" % i, "Project_Name": "測試計畫", "Hole_Point_No": "BH%d" % i, "Depth": i % 50}}
             for i in range(n)]
    return {"type": "FeatureCollection", "features": feats}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        key = url.path.rsplit("/", 1)[-1]
        query = parse_qs(url.query)
        REQUESTS.append((key, query))
        bbox = [float(v) for v in query["bbox"][0].split(",")]
        if key == "Fold":
            body = b"<html>error</html>"
        else:
            if key == "Fault50":
                time.sleep(1.5)
            if key == "Drill" and bbox[0] < 121.0:
                data = big_drill()
            else:
                data = SAMPLES.get(key, SAMPLES["Empty"])
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

import geologycloud_loader.catalog as catalog  # noqa: E402
catalog.API_ROOT = "http://127.0.0.1:%d/api/v1/zh-tw/" % server.server_port

from geologycloud_loader.catalog import BY_KEY, DATASETS  # noqa: E402
from geologycloud_loader.fetcher import Fetcher, build_url  # noqa: E402
from geologycloud_loader.geojson_parser import parse_feature_collection  # noqa: E402
from geologycloud_loader.layers import LayerManager, GROUP_NAME  # noqa: E402
from geologycloud_loader.exporter import export_layers  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + ("  " + str(detail) if detail else ""))


def wait(cond, timeout=20):
    loop = QEventLoop()
    end = time.time() + timeout
    while not cond() and time.time() < end:
        QTimer.singleShot(30, loop.quit)
        loop.exec()
    return cond()


# ---------------------------------------------------------------- parser
rows, skipped = parse_feature_collection(json.dumps(SAMPLES["Stratum"]), "polygon")
check("parser: polygon kept, point-sliver dropped", len(rows) == 2 and skipped == 1, (len(rows), skipped))
check("parser: polygon is multipolygon", all(QgsWkbTypes.isMultiType(g.wkbType()) for g, _ in rows))
check("parser: dict property -> json text", rows[1][1]["Extra"] == '{"a": 1}', rows[1][1].get("Extra"))
rows, skipped = parse_feature_collection(json.dumps(SAMPLES["Attitude"]).encode(), "point")
check("parser: multipoint exploded to 3 single points", len(rows) == 3 and not any(g.isMultipart() for g, _ in rows))
try:
    parse_feature_collection(b"<html>", "line")
    check("parser: bad payload raises", False)
except Exception as exc:  # noqa: BLE001
    check("parser: bad payload raises ServiceError", type(exc).__name__ == "ServiceError", exc)

# ---------------------------------------------------------------- url guard
url = build_url(BY_KEY["Stratum"], (121.5, 25.0, 121.55, 25.05)).toString()
check("url: all=true & bbox", "all=true" in url and "bbox=121.500000,25.000000,121.550000,25.050000" in url, url)
for bad in [(121.5, 25.0, 121.5, 25.0), (121.6, 25.0, 121.5, 25.1), (float("nan"), 1, 2, 3)]:
    try:
        build_url(BY_KEY["Stratum"], bad)
        check("url: rejects %r" % (bad,), False)
    except ValueError:
        check("url: rejects %r" % (bad,), True)

# ---------------------------------------------------------------- layers for every dataset
project = QgsProject.instance()
manager = LayerManager(project)
for ds in DATASETS:
    layer = manager.ensure_layer(ds)
    check("layer valid %s" % ds.key, layer.isValid() and layer.fields().count() == len(ds.fields))
lay = manager.layer("Stratum")
n = manager.replace_features(BY_KEY["Stratum"], parse_feature_collection(json.dumps(SAMPLES["Stratum"]), "polygon")[0], (121.5, 25, 121.6, 25.1))
check("replace: Stratum 2 features + extra field", n == 2 and "Extra" in lay.fields().names(), lay.fields().names())
cats = lay.renderer().categories()
check("legend classes per spec code", [c.value() for c in cats] == ["6020", "6022"], [c.value() for c in cats])
check("legend label = code + abbrev + name", cats[0].label() == "6020 a 沖積層", [c.label() for c in cats])
n = manager.replace_features(BY_KEY["Stratum"], parse_feature_collection(json.dumps(SAMPLES["Stratum"]), "polygon")[0][:1])
check("replace: content swapped, not appended", n == 1)
att = manager.layer("Attitude")
manager.replace_features(BY_KEY["Attitude"], parse_feature_collection(json.dumps(SAMPLES["Attitude"]), "point")[0])
vals = sorted([(f["Code"], f["Direct"], f["Angle"]) for f in att.getFeatures()], key=str)
check("numeric coercion (string '45' -> 45.0, 'bad' -> NULL)", any(v[1] == 45.0 for v in vals) and any(v[2] is None or str(v[2]) == "NULL" for v in vals), vals)
att.startEditing()
check("edit mode protects layer", manager.replace_features(BY_KEY["Attitude"], []) is None)
att.rollBack()
check("group created at top", project.layerTreeRoot().children()[0].name() == GROUP_NAME)
manager.remove("Attitude")
check("remove layer", manager.layer("Attitude") is None)

# ---------------------------------------------------------------- spec symbology
from geologycloud_loader import symbology  # noqa: E402
API_AREA = open(os.path.join(os.path.dirname(__file__), "api_codes_area.txt")).read().split()
missing = [c for c in API_AREA if symbology.area_entry(c)[0] is None]
check("spec area symbols build for all %d API codes" % len(API_AREA),
      all(symbology.area_symbol(c).symbolLayerCount() >= 1 for c in API_AREA), len(API_AREA))
check("codes newer than spec 4.4 get rock-family colours (%d)" % len(missing),
      len(missing) <= 50 and all("規範未列" in symbology.area_label(c) for c in missing), missing[:5])
for c in ["0010", "6020", "T171", "1422", "L201"]:
    e, exact = symbology.area_entry(c)
    check("area %s exact spec entry" % c, exact and e is not None, e)
check("area 1226 falls back to 122x family", symbology.area_entry("1226")[1] is False and symbology.area_entry("1226")[0] is not None)
sym = symbology.area_symbol("0010")
check("0010 = bg fill + svg pattern + contact", [l.layerType() for l in sym.symbolLayers()] == ["SimpleFill", "SVGFill", "SimpleFill"],
      [l.layerType() for l in sym.symbolLayers()])
check("0010 colors from spec", sym.symbolLayer(0).color().name() == "#e1f2ea", sym.symbolLayer(0).color().name())
solid = symbology.area_symbol("0011")
check("0011 solid spec color", solid.symbolLayer(0).color().name() == "#8bd6b1")
LINES = "B101 B102 B201 B202 B211 B212 B301 B401 B402 B411 B412 B601 C002 C101 C102 C121 C141 C142 C301 C302 C321 C341 C342 D201 E101 E102".split()
check("line symbols build for all API line codes", all(symbology.line_symbol(c).symbolLayerCount() >= 1 for c in LINES))
b401, b102, c101, b601, a201 = (symbology.line_symbol("B401"), symbology.line_symbol("B102"), symbology.line_symbol("C101"),
                                  symbology.line_symbol("B601"), symbology.attitude_symbol("A201"))
check("B401 has sawteeth decoration", b401.symbolLayer(1).layerType() == "MarkerLine")
check("B102 dashed 1.5/0.5", list(b102.symbolLayer(0).customDashVector()) == [1.5, 0.5])
check("C101 red 0.25", c101.symbolLayer(0).color().name() == "#ff0000" and c101.symbolLayer(0).width() == 0.25)
check("B601 drawn as B103 (red)", b601.symbolLayer(0).color().name() == "#ff0000")
from qgis.core import QgsSymbolLayer  # noqa: E402
_angle = getattr(getattr(QgsSymbolLayer, "Property", None), "Angle", None) or QgsSymbolLayer.PropertyAngle
check("attitude rotated by Direct", "Direct" in a201.symbolLayer(0).dataDefinedProperties().property(_angle).expressionString())
from qgis.core import QgsExpression, QgsExpressionContext, QgsFeature, QgsFields  # noqa: E402
fields = QgsFields(); fields.append(__import__("geologycloud_loader.compat", fromlist=["make_field"]).make_field("SLOPE_DIR", "string"))
f = QgsFeature(fields); f["SLOPE_DIR"] = "B東南"
ctx = QgsExpressionContext(); ctx.setFeature(f)
check("dip slope direction 'B東南' -> 135", QgsExpression(symbology.dip_direction_expression("SLOPE_DIR")).evaluate(ctx) == 135)
f["SLOPE_DIR"] = "H東北"; ctx.setFeature(f)
check("dip slope direction 'H東北' -> 45", QgsExpression(symbology.dip_direction_expression("SLOPE_DIR")).evaluate(ctx) == 45)

# ---------------------------------------------------------------- labels
from geologycloud_loader.layers import dip_offset_expression  # noqa: E402
for key, expected in [("Fault", '"Name"'), ("Fold", '"Name"'), ("Stratum", '"Abbrev"'), ("Attitude", "Angle")]:
    lyr = manager.ensure_layer(BY_KEY[key])
    st = lyr.labeling().settings() if lyr.labeling() else None
    check("%s labelled with %s" % (key, expected), lyr.labelsEnabled() and st is not None and expected in st.fieldName,
          st.fieldName if st else None)
att_settings = manager.ensure_layer(BY_KEY["Attitude"]).labeling().settings()
_offset = getattr(getattr(type(att_settings), "Property", type(att_settings)), "OffsetXY")
check("attitude label offset follows dip direction",
      dip_offset_expression("Direct") in att_settings.dataDefinedProperties().property(_offset).expressionString())
ctx2 = QgsExpressionContext()
f2 = QgsFeature(fields)
fields_d = QgsFields(); fields_d.append(__import__("geologycloud_loader.compat", fromlist=["make_field"]).make_field("Direct", "double"))
f2 = QgsFeature(fields_d)
for direct, sx, sy in [(0, 0, -1), (90, 1, 0), (180, 0, 1), (270, -1, 0)]:
    f2["Direct"] = direct; ctx2.setFeature(f2)
    x, y = (float(v) for v in QgsExpression(dip_offset_expression("Direct")).evaluate(ctx2).split(","))
    check("dip %d -> label offset towards dip side" % direct, round(x / 2.2) == sx and round(y / 2.2) == sy, (x, y))
fields_s = QgsFields()
for n in ("Name", "Abbrev"):
    fields_s.append(__import__("geologycloud_loader.compat", fromlist=["make_field"]).make_field(n, "string"))
f3 = QgsFeature(fields_s); f3["Name"] = "南莊層"; f3["Abbrev"] = "Nc"; ctx2.setFeature(f3)
check("stratum label 'Name Abbrev'", QgsExpression(BY_KEY["Stratum"].style["label"]).evaluate(ctx2) == "南莊層 Nc")
f3["Name"] = " "; f3["Abbrev"] = None; ctx2.setFeature(f3)
check("blank stratum label suppressed", QgsExpression(BY_KEY["Stratum"].style["label"]).evaluate(ctx2) is None)

# ---------------------------------------------------------------- export
for ds in DATASETS:
    if ds.key in SAMPLES:
        manager.replace_features(ds, parse_feature_collection(json.dumps(SAMPLES[ds.key]), ds.geometry)[0], (121.4, 24.9, 121.6, 25.1))
for fmt in ["gpkg_single", "gpkg", "shp", "geojson"]:
    out = tempfile.mkdtemp(prefix="gc_%s_" % fmt)
    written, errors = export_layers(manager.layers(), out, fmt, "EPSG:3826", project)
    check("export %s no errors" % fmt, not errors, errors)
    data_files = [p for p in written if not p.endswith(".txt")]
    total = 0
    for path in data_files:
        if fmt == "gpkg_single":
            from osgeo import ogr
            ds_ = ogr.Open(path)
            for i in range(ds_.GetLayerCount()):
                if ds_.GetLayer(i).GetName() != "layer_styles":
                    total += ds_.GetLayer(i).GetFeatureCount()
            names = [ds_.GetLayer(i).GetName() for i in range(ds_.GetLayerCount())]
            has_styles = "layer_styles" in names
        else:
            vl = QgsVectorLayer(path, "x", "ogr")
            total += vl.featureCount()
            if fmt == "shp" and "RockMassStrength" in path:
                check("shp keeps readable CJK field name", "岩石強" in vl.fields().names(), vl.fields().names())
            if fmt == "shp" and "Drill" in path:
                check("shp shortened names unique", len(set(vl.fields().names())) == 4, vl.fields().names())
            if fmt == "shp":
                check("shp is TWD97", vl.crs().authid() == "EPSG:3826", vl.crs().authid())
    expected = sum(l.featureCount() for l in manager.layers())
    check("export %s feature total %d" % (fmt, expected), total == expected, (total, len(data_files)))
    if fmt == "gpkg_single":
        check("gpkg_single stores styles", has_styles, names)
        styled = QgsVectorLayer(data_files[0] + "|layername=Stratum", "s", "ogr")
        check("gpkg style auto-loads (categorized)", styled.renderer().type() == "categorizedSymbol", styled.renderer().type())
        debris = QgsVectorLayer(data_files[0] + "|layername=DebrisFlowDeposition", "d", "ogr")
        debris_symbol = debris.renderer().symbol()
        svg_layers = [l for l in debris_symbol.symbolLayers() if l.layerType() == "SVGFill"]
        check("gpkg style keeps embedded spec patterns (L205)", svg_layers and svg_layers[0].svgFilePath().startswith("base64:"),
              [l.layerType() for l in debris_symbol.symbolLayers()])
    if fmt == "shp":
        check("shp has qml sidecars", any(f.endswith(".qml") for f in os.listdir(out)))
    note = [p for p in written if p.endswith(".txt")][0]
    check("source note written %s" % fmt, "政府資料開放授權條款" in open(note, encoding="utf-8").read())

# ---------------------------------------------------------------- fetcher end to end
fetcher = Fetcher()
done, fail = {}, {}
fetcher.finished.connect(lambda k, r, s, t: done.__setitem__(k, (len(r), s)))
fetcher.failed.connect(lambda k, m: fail.__setitem__(k, m))
fetcher.fetch(BY_KEY["Fault"], (121.4, 24.9, 121.5, 25.0))
fetcher.fetch(BY_KEY["Fold"], (121.4, 24.9, 121.5, 25.0))
check("fetch Fault ok", wait(lambda: "Fault" in done) and done["Fault"] == (2, 0), done.get("Fault"))
check("fetch Fold bad payload -> failed signal", wait(lambda: "Fold" in fail), fail.get("Fold"))
fetcher.fetch(BY_KEY["Drill"], (120.9, 24.0, 121.4, 24.5))
check("big payload parsed in background task", wait(lambda: "Drill" in done, 60) and done["Drill"][0] == 30000, done.get("Drill"))
# stale answers: start slow request then immediately a new one for same key
REQUESTS.clear()
fetcher.fetch(BY_KEY["Fault50"], (121.0, 24.0, 121.1, 24.1))
QTimer.singleShot(200, lambda: fetcher.fetch(BY_KEY["Fault50"], (121.2, 24.2, 121.3, 24.3)))
hits = []
fetcher.finished.connect(lambda k, r, s, t: hits.append(k) if k == "Fault50" else None)
wait(lambda: len(hits) >= 1, 15)
wait(lambda: False, 2.5)
check("only newest Fault50 answer delivered once", hits == ["Fault50"], hits)
fetcher.fetch(BY_KEY["Fault50"], (121.0, 24.0, 121.1, 24.1))
fetcher.cancel("Fault50")
hits.clear()
wait(lambda: False, 2.5)
check("cancel drops answer", hits == [], hits)
check("all requests used all=true", all(q.get("all") == ["true"] for _k, q in REQUESTS))

# ---------------------------------------------------------------- plugin with mocked iface
from qgis.testing.mocked import get_iface  # noqa: E402
iface = get_iface()
canvas = iface.mapCanvas()
canvas.resize(800, 600)
project.removeAllMapLayers()
project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
from geologycloud_loader import classFactory  # noqa: E402
plugin = classFactory(iface)
plugin.initGui()
from qgis.core import QgsCoordinateTransform  # noqa: E402
tr = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), QgsCoordinateReferenceSystem("EPSG:3857"), project)
canvas.setExtent(tr.transformBoundingBox(QgsRectangle(121.50, 25.00, 121.56, 25.04)))
bbox = plugin.current_bbox()
check("current_bbox in lon/lat", bbox and 121.4 < bbox[0] < 121.51 and 25.03 < bbox[3] < 25.1, bbox)
plugin.dock.set_checked(["Fault", "Stratum"], emit=True)
check("checking datasets loads layers", wait(lambda: plugin.layers.layer("Fault") is not None and plugin.layers.layer("Fault").featureCount() == 2
                                            and plugin.layers.layer("Stratum").featureCount() == 2), plugin.dock._items["Fault"].text(1))
REQUESTS.clear()
canvas.setExtent(tr.transformBoundingBox(QgsRectangle(121.51, 25.01, 121.57, 25.05)))
wait(lambda: len(REQUESTS) >= 2, 5)
check("pan triggers debounced re-download", len(REQUESTS) == 2, [r[0] for r in REQUESTS])
REQUESTS.clear()
canvas.setExtent(tr.transformBoundingBox(QgsRectangle(119.5, 22.0, 122.5, 25.5)))
wait(lambda: len(REQUESTS) >= 1, 3)
check("zoomed out: Stratum skipped, Fault (2 deg) skipped, layers keep data",
      len(REQUESTS) == 0 and plugin.dock._items["Stratum"].text(1) == "請放大地圖" and plugin.layers.layer("Stratum").featureCount() == 2,
      ([r[0] for r in REQUESTS], plugin.dock._items["Stratum"].text(1)))
canvas.setExtent(tr.transformBoundingBox(QgsRectangle(100, 0, 105, 5)))
wait(lambda: False, 1.2)
check("outside Taiwan -> no request", plugin.dock._items["Fault"].text(1) == "不在服務範圍" and not REQUESTS)
plugin.dock.set_checked(["Fault"], emit=True)
check("unchecking removes layer", plugin.layers.layer("Stratum") is None and plugin.layers.layer("Fault") is not None)
plugin.unload()
check("unload clean", plugin.dock is None)

server.shutdown()
failed = [r for r in results if not r[1]]
print("\n%d checks, %d failed" % (len(results), len(failed)))
sys.exit(1 if failed else 0)
