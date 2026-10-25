# -*- coding: utf-8 -*-
"""Geological map symbols following the CGS digital geological map specification.

Source: 經濟部中央地質調查所《數值地質圖資料規範》第 4.4 版（民國 97 年 3 月）
  肆、數值地質圖圖形符號規範 (symbol codes and names) and
  附錄五、圖形符號設計與製作 (colours, patterns, line and marker dimensions).

The Geology Cloud API returns the specification's symbol code in the ``Code``
attribute, so every feature can be drawn with its own specification symbol:

* area codes  (地層 / 地體構造)  -> background colour + pattern colour + pattern
* line codes  (斷層 / 褶皺 / 煤層 / 葉理) -> line width, dash and decorations
* point codes (位態 / 溫泉 / 鑽井 / 測量點) -> rotated marker

Patterns and decorations are drawn as small SVG tiles embedded in the style
(``base64:`` paths), so exported GeoPackage / QML styles keep working on
computers without this plugin.  Sizes are in millimetres as in the spec.
"""

import base64
import json
import os
import zlib

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    Qgis,
    QgsCentroidFillSymbolLayer,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMarkerLineSymbolLayer,
    QgsMarkerSymbol,
    QgsProperty,
    QgsSimpleFillSymbolLayer,
    QgsSimpleLineSymbolLayer,
    QgsSVGFillSymbolLayer,
    QgsSvgMarkerSymbolLayer,
    QgsSymbolLayer,
)

# Data-defined angle key: QgsSymbolLayer.Property.Angle on QGIS >= 3.36 / 4.x;
# QGIS 3.34 uses the older member name inside the same scoped enum.
ANGLE_PROPERTY = getattr(QgsSymbolLayer.Property, "Angle", None)
if ANGLE_PROPERTY is None:
    ANGLE_PROPERTY = getattr(QgsSymbolLayer.Property, "Property" + "Angle")

_HERE = os.path.dirname(__file__)
with open(os.path.join(_HERE, "spec_symbols.json"), encoding="utf-8") as _handle:
    SPEC = json.load(_handle)

SPEC_SOURCE = SPEC["source"]
CONTACT_WIDTH = 0.125      # 規範 A101 接觸帶-位置確定：粗細 0.125 mm
PATTERN_SCALE = 1.5        # area pattern tiles: 1 SVG unit = 0.15 mm (legible at 1:25,000-1:50,000)
BLACK = "#000000"
RED = "#ff0000"
ORANGE = "#ffaa00"
GRAY = "#787878"


# ---------------------------------------------------------------- helpers
def _mm(layer):
    layer.setOutputUnit(Qgis.RenderUnit.Millimeters)


def _embed(svg):
    return "base64:" + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _svg(width, height, body, view=None):
    view = view or "0 0 %s %s" % (width, height)
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" viewBox="%s">%s</svg>'
            % (width, height, view, body))


def _line(x1, y1, x2, y2, color, width, cap="butt"):
    return ('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-width="%s" stroke-linecap="%s"/>'
            % (x1, y1, x2, y2, color, width, cap))


def _path(d, color, width, fill="none", join="miter"):
    return ('<path d="%s" stroke="%s" stroke-width="%s" fill="%s" stroke-linejoin="%s"/>'
            % (d, color, width, fill, join))


def _circle(cx, cy, r, fill, stroke="none", width=0):
    return '<circle cx="%s" cy="%s" r="%s" fill="%s" stroke="%s" stroke-width="%s"/>' % (cx, cy, r, fill, stroke, width)


def _mix(color, other, ratio):
    a, b = QColor(color), QColor(other)
    return QColor(round(a.red() + (b.red() - a.red()) * ratio),
                  round(a.green() + (b.green() - a.green()) * ratio),
                  round(a.blue() + (b.blue() - a.blue()) * ratio)).name()


def light(color, ratio=0.5):
    return _mix(color, "#ffffff", ratio)


def dark(color, ratio=0.35):
    return _mix(color, "#000000", ratio)


def stable_color(value):
    digest = zlib.crc32(str(value).encode("utf-8"))
    return QColor.fromHsl(digest % 360, 110 + (digest >> 9) % 90, 140 + (digest >> 17) % 50).name()


# Hue ranges for codes newer than spec 4.4, by the spec's code ranges
# (肆、一、(一)): 000-399 sedimentary named, 400-499 igneous named,
# 500-599 metamorphic named, 600-699 unnamed sediments, 700-799 unnamed
# igneous, 800-899 unnamed metamorphic, 900-999 other.
_FAMILY_HUES = {"0": (60, 150), "1": (60, 150), "2": (60, 150), "3": (60, 150), "4": (340, 380),
                "5": (190, 280), "6": (45, 60), "7": (340, 380), "8": (190, 280), "9": (0, 0)}


def family_color(code):
    """Colour in the rock family's hue band (stable for the same code)."""
    digest = zlib.crc32(str(code).encode("utf-8"))
    low, high = _FAMILY_HUES.get(str(code)[:1], (0, 0))
    if high == low:
        return QColor.fromHsl(0, 0, 175 + digest % 40).name()
    hue = (low + digest % (high - low)) % 360
    return QColor.fromHsl(hue, 90 + (digest >> 8) % 80, 165 + (digest >> 16) % 45).name()


def _diagonals(size, color, width, slash=True, shift=0):
    """Seamless '/' (or '\\') lines in a square tile."""
    s = size
    parts = []
    for k in (-1, 0, 1):
        o = k * s + shift
        if slash:
            parts.append(_line(o, s, o + s, 0, color, width))
        else:
            parts.append(_line(o, 0, o + s, s, color, width))
    return "".join(parts)


# ---------------------------------------------------------------- area patterns
# Each entry: tile width in mm, and a function (fg) -> (svg width, height, body).
# Tile units are 0.1 mm, so stroke-width 2 = 0.2 mm on the map.
def _p_hlines(rows, height, width=40):
    def build(c):
        body = "".join(_line(0, y, width, y, c if col is None else col(c), sw) for y, sw, col in rows)
        return width, height, body
    return build


def _p_vlines(cols, width, height=40):
    def build(c):
        body = "".join(_line(x, 0, x, height, c if col is None else col(c), sw) for x, sw, col in cols)
        return width, height, body
    return build


def _p_diag(size, sw, slash):
    def build(c):
        return size, size, _diagonals(size, c, sw, slash)
    return build


def _scatter(points, make):
    def build(c):
        return 60, 60, "".join(make(c, x, y, i) for i, (x, y) in enumerate(points))
    return build


_RANDOM_A = [(5, 7), (17, 3), (29, 11), (44, 6), (55, 15), (9, 22), (24, 27), (38, 21), (50, 31),
             (3, 39), (16, 44), (31, 37), (45, 46), (57, 52), (11, 55), (27, 53), (40, 58), (21, 14)]
_RANDOM_B = [(8, 9), (30, 5), (49, 12), (18, 27), (40, 30), (6, 45), (26, 49), (52, 44), (14, 58)]


def _p_glyph_grid(glyph, size=40):
    """Glyph drawn twice per tile, staggered (rows offset by half a tile)."""
    def build(c):
        half = size / 2
        return size, size, glyph(c, half / 2, half / 2) + glyph(c, half * 1.5, half * 1.5)
    return build


def _g_triangle(c, x, y, fill="none", base=False):
    d = "M%s,%s L%s,%s L%s,%s Z" % (x - 6, y + 5, x, y - 5, x + 6, y + 5)
    out = _path(d, c, 1.8, fill)
    if base:
        out += _line(x - 8, y + 7.5, x + 8, y + 7.5, c, 1.5)
    return out


AREA_PATTERNS = {
    "0010": _p_hlines([(3, 2.0, None), (9, 1.0, None)], 12),
    "0012": _p_diag(16, 2.2, False),
    "0020": lambda c: (24, 24, _circle(6, 6, 1.5, c) + _circle(18, 18, 1.5, c)),
    "0080": lambda c: (48, 16, _line(4, 4, 28, 4, c, 2.0) + _line(28, 12, 52, 12, light(c, 0.35), 1.4)
                       + _line(-20, 12, 4, 12, light(c, 0.35), 1.4)),
    "0150": lambda c: (30, 30, _circle(7.5, 7.5, 4.2, c) + _circle(22.5, 22.5, 4.2, c)),
    "0161": _p_vlines([(4, 2.4, None), (12, 1.0, None)], 16),
    "0180": _p_diag(30, 3.0, False),
    "1023": _scatter(_RANDOM_A, lambda c, x, y, i: _circle(x, y, 1.4 + (i % 3) * 0.3, c)),
    "1040": lambda c: (24, 20, _path("M0,5 L6,13 L12,5 L18,13 L24,5", c, 1.8)),
    "1061": lambda c: (40, 20, '<rect x="0" y="0" width="40" height="20" fill="%s"/>' % light(c, 0.75)
                       + _line(0, 0.75, 40, 0.75, c, 1.5) + _line(0, 10, 40, 10, c, 1.5)
                       + _line(0.75, 0, 0.75, 10, c, 1.5) + _line(20, 10, 20, 20, c, 1.5)),
    "1120": _p_diag(16, 3.0, True),
    "1131": _p_glyph_grid(lambda c, x, y: _g_triangle(c, x, y)),
    "1170": _p_hlines([(4, 1.4, None), (10, 1.4, None)], 24),
    "1200": _scatter(_RANDOM_B, lambda c, x, y, i: _circle(x, y, 2.4, "none", c, 1.2)),
    "1250": lambda c: (60, 16, _line(0, 4, 24, 4, c, 2) + _line(30, 4, 54, 4, c, 2) + _line(15, 12, 39, 12, c, 2)
                       + _line(45, 12, 69, 12, c, 2) + _line(-15, 12, 9, 12, c, 2)),
    "1272": _p_hlines([(4, 6.0, None), (14, 1.0, None), (22, 1.0, None)], 30),
    "1310": lambda c: (40, 12, _line(4, 6, 28, 6, c, 1.6)),
    "1313": lambda c: (16, 16, _line(8, 0, 8, 16, c, 2.2) + _line(0, 8, 16, 8, c, 2.2)),
    "1340": lambda c: (20, 14, _line(6, 7, 14, 7, c, 2.0)),
    "1422": lambda c: (20, 20, _diagonals(20, c, 2.2, True) + _diagonals(20, c, 2.2, False)),
    "1450": _p_hlines([(12, 1.0, None)], 24),
    "1470": lambda c: (24, 24, _diagonals(24, c, 3.0, True) + _diagonals(24, dark(c, 0.2), 1.0, True, 9)),
    "1650": lambda c: (30, 60, _line(8, 5, 8, 20, c, 3) + _line(23, 35, 23, 50, c, 3)),
    "1662": _p_diag(24, 4.0, True),
    "1791": _scatter(_RANDOM_A[::2], lambda c, x, y, i: _line(x - 4, y - (i % 3) * 2, x + 4, y + (i % 3) * 2, c, 2.0)),
    "1851": _p_hlines([(3, 1.4, None), (8, 0.8, None)], 12),
    "1853": _p_vlines([(3, 1.2, None), (8, 0.8, None)], 12),
    "1854": _p_vlines([(4, 3.0, None), (12, 1.0, None), (18, 2.0, None)], 24),
    "1940": _p_vlines([(4, 1.6, None), (12, 1.0, lambda c: light(c, 0.3))], 16),
    "4011": _p_glyph_grid(lambda c, x, y: _path("M%s,%s L%s,%s L%s,%s" % (x - 3, y - 6, x + 3, y, x - 3, y + 6), c, 2)),
    "4012": lambda c: (24, 24, _line(12, 6, 12, 18, c, 2) + _line(6, 12, 18, 12, c, 2)),
    "4030": lambda c: (24, 24, _path("M4,9 L12,15 L20,9", c, 2)),
    "4032": _scatter(_RANDOM_A, lambda c, x, y, i: _line(x - 3, y + (i % 4 - 1.5) * 2, x + 3, y - (i % 4 - 1.5) * 2, c, 1.4)),
    "4034": _p_glyph_grid(lambda c, x, y: _line(x - 4, y - 4, x + 4, y + 4, c, 2) + _line(x - 4, y + 4, x + 4, y - 4, c, 2)),
    "5030": lambda c: (24, 24, _diagonals(24, c, 2.0, True) + _line(6, 6, 12, 12, c, 2.0) + _line(18, 18, 24, 24, c, 2.0)),
    "7004": lambda c: (20, 20, _line(0, 10, 20, 10, c, 1.5) + _diagonals(20, c, 1.5, True)),
    "7005": _p_glyph_grid(lambda c, x, y: _path("M%s,%s L%s,%s L%s,%s" % (x - 7, y - 3, x, y + 3, x + 7, y - 3), c, 2)),
    "7013": lambda c: (14, 14, _line(0, 7, 14, 7, c, 1.4) + _diagonals(14, c, 1.4, True)),
    "7014": lambda c: (12, 24, _line(0, 24, 12, 0, c, 1.4) + _line(-12, 24, 0, 0, c, 1.4) + _line(12, 24, 24, 0, c, 1.4)
                       + _line(0, 12, 12, 12, c, 1.4)),
    "7017": lambda c: (12, 24, _line(0, 24, 12, 0, c, 1.4) + _line(0, 0, 12, 24, c, 1.4)),
    "7018": lambda c: (20, 20, _diagonals(20, c, 1.2, True) + _diagonals(20, c, 1.2, False)
                       + _line(0, 10, 20, 10, c, 1.2) + _line(10, 0, 10, 20, c, 1.2)),
    "7019": lambda c: (20, 20, _diagonals(20, c, 1.2, True) + _diagonals(20, c, 1.2, False) + _line(0, 10, 20, 10, c, 1.2)),
    "A1AVL": lambda c: (16, 16, _line(8, 0, 8, 16, c, 1.6) + _line(0, 8, 16, 8, c, 1.6)),
    "A2": lambda c: (16, 16, _line(0, 8, 16, 8, c, 1.6) + _line(8, 0, 8, 16, "#2e7d32", 2.0)),
    "A7": lambda c: (16, 16, _line(0, 8, 16, 8, c, 1.6) + _line(8, 0, 8, 16, "#3a7bd5", 2.0)),
    "E103": _p_diag(20, 1.5, True),
    "E104": _p_diag(30, 1.5, True),
    "L200": lambda c: (10, 10, _circle(5, 5, 0.6, c)),
    "L201": _p_glyph_grid(lambda c, x, y: _line(x, y - 7, x, y + 3, c, 2) + _path(
        "M%s,%s L%s,%s L%s,%s" % (x - 5, y - 1, x, y + 4, x + 5, y - 1), c, 2) + _line(x - 6, y + 7, x + 6, y + 7, c, 1.5)),
    "L202": _p_glyph_grid(lambda c, x, y: _circle(x, y, 5.5, c) + _line(x - 6, y, x + 6, y, "#ffffff", 1.2)),
    "L203": _p_glyph_grid(lambda c, x, y: _path("M%s,%s L%s,%s L%s,%s" % (x - 5, y - 5, x, y + 5, x + 5, y - 5), c, 2.6)),
    "L204": _p_glyph_grid(lambda c, x, y: _path("M%s,%s L%s,%s A5,5 0 0 0 %s,%s L%s,%s" % (
        x - 5, y - 6, x - 5, y + 1, x + 5, y + 1, x + 5, y - 6), c, 2.2)),
    "L205": _p_glyph_grid(lambda c, x, y: _g_triangle(c, x, y, base=True)),
    "L211": _p_glyph_grid(lambda c, x, y: _path("M%s,%s q3,-3 6,0 t6,0" % (x - 6, y), c, 1.6)),
    "Z102": _p_diag(10, 0.8, True),
    "dots4": lambda c: (14, 14, _circle(7, 7, 2.2, c)),
    "dots8": lambda c: (28, 28, _circle(14, 14, 3.0, c)),
}


def _pattern_layer(pattern, color):
    builder = AREA_PATTERNS.get(pattern)
    if builder is None:
        return None
    width, height, body = builder(color)
    layer = QgsSVGFillSymbolLayer(_embed(_svg(width, height, body)), width / 10.0 * PATTERN_SCALE, 0)
    _mm(layer)
    layer.setSvgFillColor(QColor(color))
    layer.setSvgStrokeColor(QColor(color))
    sub = layer.subSymbol()
    if sub is not None:  # no outline around each tile area
        sub.setColor(QColor(0, 0, 0, 0))
        for index in range(sub.symbolLayerCount()):
            sub.symbolLayer(index).setPenStyle(Qt.PenStyle.NoPen)
    return layer


def _plain_fill(color=None, stroke=BLACK, stroke_width=CONTACT_WIDTH, dashed=False):
    layer = QgsSimpleFillSymbolLayer()
    if color is None:
        layer.setBrushStyle(Qt.BrushStyle.NoBrush)
    else:
        layer.setColor(QColor(color))
    if stroke is None:
        layer.setStrokeStyle(Qt.PenStyle.NoPen)
    else:
        layer.setStrokeColor(QColor(stroke))
        layer.setStrokeWidth(stroke_width)
        if dashed:
            layer.setStrokeStyle(Qt.PenStyle.DashLine)
    _mm(layer)
    return layer


def area_entry(code):
    """Specification entry for an area code, falling back to the same family
    (first three digits) for codes newer than spec 4.4.  Returns (entry, exact)."""
    entries = SPEC["area"]
    if code in entries:
        return entries[code], True
    if code and len(code) == 4:
        family = sorted(k for k in entries if k[:3] == code[:3])
        if family:
            preferred = code[:3] + "0"
            return entries[preferred if preferred in entries else family[0]], False
    return None, False


def area_symbol(code, opacity=1.0, contact=True):
    """Fill symbol for a 地層 / 地體構造 code (spec 附錄五 面符號)."""
    entry, _exact = area_entry(code)
    stroke = BLACK if contact else None
    if entry is None:
        symbol = QgsFillSymbol([_plain_fill(family_color(code), stroke)])
        symbol.setOpacity(opacity)
        return symbol
    pattern, fg, bg = entry.get("p"), entry.get("fg"), entry.get("bg")
    border = entry.get("w")
    border_color = entry.get("bc") or (fg if border and fg and pattern in ("E103", "E104", "1120", "dots8") else BLACK)
    layers = []
    if pattern == "0011":
        layers.append(_plain_fill(fg or "#ffffff", None))
    else:
        if bg:
            layers.append(_plain_fill(bg, None))
        overlay = _pattern_layer(pattern, fg or BLACK) if pattern not in ("outline", "dashoutline") else None
        if overlay is not None:
            layers.append(overlay)
    if border:
        layers.append(_plain_fill(None, border_color, border, dashed=(pattern == "dashoutline")))
    elif contact:
        layers.append(_plain_fill(None, BLACK, CONTACT_WIDTH))
    if not layers:
        layers.append(_plain_fill(None, BLACK))
    symbol = QgsFillSymbol(layers)
    symbol.setOpacity(opacity)
    return symbol


# ---------------------------------------------------------------- line symbols
def _simple_line(color, width, dash=None):
    layer = QgsSimpleLineSymbolLayer(QColor(color), width)
    _mm(layer)
    if dash:
        layer.setUseCustomDashPattern(True)
        layer.setCustomDashVector([float(v) for v in dash])
        layer.setCustomDashPatternUnit(Qgis.RenderUnit.Millimeters)
    layer.setPenCapStyle(Qt.PenCapStyle.FlatCap)
    return layer


def _svg_marker(svg_body, size_mm, view, height_units):
    """SVG marker whose centre (0,0 of ``view``) sits on the anchor point."""
    width_units = float(view.split()[2])
    svg = _svg(width_units, height_units, svg_body, view)
    marker = QgsSvgMarkerSymbolLayer(_embed(svg), size_mm)
    _mm(marker)
    return marker


def _decoration(svg_body, size_mm, view, height_units, placement, interval=None, rotate=True):
    marker = _svg_marker(svg_body, size_mm, view, height_units)
    line = QgsMarkerLineSymbolLayer(rotate, interval or 10.0)
    _mm(line)
    line.setPlacements(Qgis.MarkerLinePlacements(getattr(Qgis.MarkerLinePlacement, placement)))
    if interval:
        line.setInterval(interval)
        # First group close to the start so short lines and legend patches show it.
        line.setOffsetAlongLine(3.0)
    line.setSubSymbol(QgsMarkerSymbol([marker]))
    return line


# Decorations are drawn in 0.1 mm units; +y is the right-hand side of the
# digitising direction (QGIS rotates the marker with the line).
# Side of the trace for upper-plate decorations (鋸齒、方塊、圓齒在上盤):
# -1 = left of the digitising direction, which matches how the Geology Cloud
# fault lines are digitised (checked by the author against the geological maps).
UPPER_PLATE_SIDE = -1


def _teeth(color, solid=True, shape="triangle"):
    fill = color if solid else "#ffffff"
    k = UPPER_PLATE_SIDE
    parts = []
    for x in (-20, 0, 20):
        if shape == "triangle":       # 正三角：高 1.375 mm
            d = "M%s,0 L%s,%s L%s,0 Z" % (x - 7.9, x, 13.75 * k, x + 7.9)
            parts.append(_path(d, color, 2.0, fill))
        elif shape == "square":       # 正方形：邊長 1 mm
            top = 1.5 if k > 0 else -11.5
            parts.append('<rect x="%s" y="%s" width="10" height="10" fill="%s" stroke="%s" stroke-width="2"/>'
                         % (x - 5, top, fill, color))
        else:                         # 圓齒
            parts.append(_circle(x, 6.5 * k, 5, fill, color, 2.0))
    return "".join(parts)


def _strike_slip(color, right_lateral):
    """Pair of half arrows (主軸長 5、倒勾 1.75、夾角 20) on both sides of the
    trace showing relative movement: 左移 (sinistral) or 右移 (dextral)."""
    m = -1 if right_lateral else 1
    upper = _path("M%s,-6 L%s,-6 L%s,-12" % (25 * m, -25 * m, -8.6 * m), color, 2.5)
    lower = _path("M%s,6 L%s,6 L%s,12" % (-25 * m, 25 * m, 8.6 * m), color, 2.5)
    return upper + lower


def _fold_arrows(color, outward, length=22.5, head="tail", overturned=False):
    """Fold axis arrows perpendicular to the trace (雙箭頭長 2.25+2.25)."""
    parts = []
    for side in (-1, 1):
        y_tip = side * length if outward else side * 3
        y_tail = side * 3 if outward else side * length
        parts.append(_line(0, y_tail, 0, y_tip, color, 2.5))
        direction = 1 if (y_tip - y_tail) > 0 else -1
        if head == "triangle":
            parts.append(_path("M-6,%s L0,%s L6,%s Z" % (y_tip - direction * 12.5, y_tip, y_tip - direction * 12.5),
                               color, 1.5, color))
        else:
            parts.append(_path("M-5,%s L0,%s L5,%s" % (y_tip - direction * 13.75, y_tip, y_tip - direction * 13.75),
                               color, 2.5))
    if overturned:  # 半圓：直徑 2、空心
        parts.append(_path("M-10,0 A10,10 0 0 1 10,0", color, 2.5))
    return parts and "".join(parts)


_FAULT_COLORS = (BLACK, RED, ORANGE, GRAY)
_LINE_ALIASES = {"B601": "B103"}   # API 地震地表破裂 -> 規範 第一類活動斷層／地震斷層


def _variant(serial):
    """Spec families run in pairs: 1/2 black, 3/4 red, 5/6 orange, 7/8 gray;
    odd = 位置確定 (solid), even = 位置概略、推測、掩覆 (dashed)."""
    serial = max(1, serial)
    return _FAULT_COLORS[(serial - 1) // 2 % 4], serial % 2 == 0


def _serial(code, digits):
    tail = code[-digits:]
    return int(tail) if tail.isdigit() else 1


def line_symbol(code):
    """Line symbol for a 斷層 / 褶皺 / 煤層 / 葉理 code (spec 附錄五 線符號)."""
    code = _LINE_ALIASES.get(code, code or "")
    family = code[:2]
    layers = []
    if family == "B1":
        color, dashed = _variant(_serial(code, 2))
        layers.append(_simple_line(color, 0.3, [1.5, 0.5] if dashed else None))
    elif family == "B2":
        color, dashed = _variant(_serial(code, 1))
        right = code[2] == "1"
        layers.append(_simple_line(color, 0.3, [1.5, 0.5] if dashed else None))
        layers.append(_decoration(_strike_slip(color, right), 5.0, "-25 -15 50 30", 30, "CentralPoint"))
    elif family == "B3":
        hollow = code[2] == "1"
        color, dashed = (BLACK, code == "B312") if hollow else _variant(_serial(code, 1))
        layers.append(_simple_line(color, 0.3, [3.5, 0.5] if dashed else None))
        layers.append(_decoration(_teeth(color, not hollow, "square"), 5.0, "-25 -15 50 30", 30, "Interval", 15.0))
    elif family == "B4":
        hollow = code in ("B402", "B403", "B407", "B412")
        dashed = code[2] == "1"
        color = {"B404": RED, "B405": ORANGE, "B406": GRAY, "B407": RED,
                 "B416": RED, "B417": ORANGE, "B418": GRAY}.get(code, BLACK)
        layers.append(_simple_line(color, 0.3, [1.75, 0.5] if dashed else None))
        layers.append(_decoration(_teeth(color, not hollow), 5.0, "-25 -15 50 30", 30, "Interval", 15.0))
    elif family == "B5":
        hollow = code in ("B502", "B503")
        layers.append(_simple_line(BLACK, 0.3, [1.5, 0.5] if code[2] == "1" else None))
        layers.append(_decoration(_teeth(BLACK, not hollow, "circle"), 5.0, "-25 -15 50 30", 30, "Interval", 15.0))
    elif family == "B9":
        layers.append(_simple_line(BLACK if code != "B991" else "#00c800", 0.3))
    elif family[0] == "C":
        dashed = code in ("C002", "C102", "C142", "C302", "C342")
        layers.append(_simple_line(RED, 0.25, [1.5, 0.5] if dashed else None))
        anticline = code[1] in "01"
        if code != "C002":
            head = "triangle" if code[1:3] in ("14", "34") else "tail"
            length = 45 if head == "triangle" else 22.5
            overturned = code[1:3] in ("12", "32")
            body = _fold_arrows(RED, anticline, length / 2.0 if head == "triangle" else length, head, overturned)
            layers.append(_decoration(body, 5.0, "-25 -25 50 50", 50, "CentralPoint"))
    elif code == "D201" or family[0] == "D":
        layers.append(_simple_line(BLACK, 0.1))
    elif code in ("E101", "E102"):
        layers.append(_simple_line(RED, 0.3, [3.5, 0.5] if code == "E102" else None))
        c_mark = _path("M6,-15 A9,9 0 1 0 6,15", RED, 2.5)      # C 型：高 3 mm
        layers.append(_decoration(c_mark, 3.0, "-15 -15 30 30", 30, "Interval", 12.0))
    else:
        layers.append(_simple_line(BLACK, 0.25))
    return QgsLineSymbol(layers)


# ---------------------------------------------------------------- point symbols
def _rotate_by(layer, expression):
    layer.setDataDefinedProperty(ANGLE_PROPERTY, QgsProperty.fromExpression(expression))


def _attitude_body(code):
    """位態符號：底線 5 mm（走向），短線 0.875 mm 指向傾向（rotation = DIREC）."""
    k = BLACK
    if code == "A101":   # 水平地層：⊕ 直徑 2.5
        return _circle(0, 0, 12.5, "none", k, 3) + _line(-12.5, 0, 12.5, 0, k, 3) + _line(0, -12.5, 0, 12.5, k, 3)
    base = _line(-25, 0, 25, 0, k, 3)
    if code == "A202":
        base = _line(-25, 0, -5, 0, k, 3) + _line(5, 0, 25, 0, k, 3)
    if code == "A203":
        base = _path("M-25,0 q3,-4 6,0 t6,0 t6,0 t6,0 t6,0 t6,0 t6,0 t6,0", k, 3)
    tick = _line(0, 0, 0, -8.75, k, 3)
    if code in ("A301", "A302"):     # 倒轉：半圓 直徑 1.25
        tick = _line(0, 0, 0, -8.75, k, 3) + _path("M0,-8.75 A6.25,6.25 0 0 1 -12.5,-8.75", k, 3)
    elif code in ("A401", "A402"):   # 垂直：寬 5、高 1.75
        tick = _line(0, -8.75, 0, 8.75, k, 3)
    elif code == "A501":             # 岩脈：雙短線 長 1.375、間距 1
        tick = _line(-5, 0, -5, -13.75, k, 3) + _line(5, 0, 5, -13.75, k, 3)
        base = _line(-27.5, 0, 27.5, 0, k, 3)
    dot = _circle(-14, -4, 3.75, k) if code in ("A204", "A302", "A402") else ""
    return base + tick + dot


def attitude_symbol(code, angle_field="Direct"):
    marker = _svg_marker(_attitude_body(code), 5.5, "-27.5 -27.5 55 55", 55)
    if code != "A101":
        _rotate_by(marker, 'coalesce("%s", 0)' % angle_field)
    return QgsMarkerSymbol([marker])


def hot_spring_symbol():
    """X702 溫泉：長 3、寬 2（紅色）."""
    k = RED
    body = (_path("M-9,-4 c-4,-5 4,-8 0,-14", k, 2.2) + _path("M0,-4 c-4,-5 4,-8 0,-14", k, 2.2)
            + _path("M9,-4 c-4,-5 4,-8 0,-14", k, 2.2) + _path("M-13,0 A13,10 0 0 0 13,0", k, 2.6))
    return QgsMarkerSymbol([_svg_marker(body, 3.0, "-15 -18 30 30", 30)])


def circle_symbol(diameter, fill, stroke=None, stroke_width=0.0):
    symbol = QgsMarkerSymbol.createSimple({
        "name": "circle", "size": str(diameter), "color": fill,
        "outline_color": stroke or fill, "outline_width": str(stroke_width),
        "outline_style": "solid" if stroke else "no", "size_unit": "MM"})
    return symbol


def borehole_symbol():
    return circle_symbol(2.0, RED)                         # X901 圓：直徑 2、實心、紅


def survey_point_symbol():
    return circle_symbol(2.0, "#fffb00", "#e8a200", 0.3)   # Z001 圓：直徑 2、粗細 0.3


DIP_DIRECTIONS = {"北": 0, "東北": 45, "東": 90, "東南": 135, "南": 180, "西南": 225, "西": 270, "西北": 315}


def dip_direction_expression(field):
    """'B東南' -> 135 ; L102 順向坡方向 marker rotation."""
    cases = " ".join("WHEN \"%s\" LIKE '%%%s' THEN %d" % (field, name, angle)
                     for name, angle in sorted(DIP_DIRECTIONS.items(), key=lambda item: -len(item[0])))
    return "CASE %s ELSE 0 END" % cases


def dipslope_symbol(field="SLOPE_DIR"):
    """順向坡：坡面範圍（淺色）＋ 重心處 L102 順向坡方向符號（同 A201，高 2 mm）."""
    fill = _plain_fill("#f6c89f", "#b35c00", 0.15)
    body = _line(-25, 0, 25, 0, BLACK, 3) + _line(0, 0, 0, -20, BLACK, 3)
    marker = _svg_marker(body, 5.0, "-25 -25 50 50", 50)
    _rotate_by(marker, dip_direction_expression(field))
    centroid = QgsCentroidFillSymbolLayer()
    centroid.setPointOnSurface(True)
    centroid.setSubSymbol(QgsMarkerSymbol([marker]))
    return QgsFillSymbol([fill, centroid])


def landslide_symbol(code, dashed_outline=False):
    """L2xx 山崩類面符號（黑色圖樣、透空）."""
    entry = SPEC["area"].get(code, {})
    layers = [_pattern_layer(entry.get("p", code), entry.get("fg", BLACK))]
    layers.append(_plain_fill(None, BLACK, 0.2, dashed_outline))
    return QgsFillSymbol([layer for layer in layers if layer is not None])


def frame_symbol():
    """Z101 圖框：粗細 0.1，黑."""
    return QgsFillSymbol([_plain_fill(None, BLACK, 0.1)])


# ---------------------------------------------------------------- legend labels
def area_label(code, name=None, abbrev=None):
    entry, exact = area_entry(code)
    title = name or (entry or {}).get("zh") or "未知地層"
    parts = [code]
    if abbrev:
        parts.append(abbrev)
    parts.append(title)
    label = " ".join(p for p in parts if p)
    if entry is None:
        label += "（規範未列，依岩類配色）"
    elif not exact:
        label += "（規範未列，套用同族符號）"
    return label


def line_label(code, note=None):
    spec_code = _LINE_ALIASES.get(code, code)
    zh = SPEC["line"].get(spec_code, {}).get("zh")
    if code in _LINE_ALIASES:
        return "%s %s（依規範 %s 繪製）" % (code, note or "", spec_code)
    return "%s %s" % (code, zh or note or "")


def point_label(code, note=None):
    zh = SPEC["point"].get(code, {}).get("zh")
    return "%s %s" % (code, zh or note or "")
