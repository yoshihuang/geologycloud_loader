# -*- coding: utf-8 -*-
"""Memory (scratch) layers that hold the features of the current map view."""

import zlib

from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis,
    QgsCategorizedSymbolRenderer,
    QgsExpression,
    QgsFeature,
    QgsFeatureRequest,
    QgsFillSymbol,
    QgsLayerMetadata,
    QgsPalLayerSettings,
    QgsProject,
    QgsProperty,
    QgsRendererCategory,
    QgsSingleSymbolRenderer,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)

from .catalog import LICENSE_TEXT, LICENSE_URL, LINE, POINT, SOURCE_TEXT, SWAGGER_URL
from . import symbology
from .compat import make_field

_NO_GEOMETRY = getattr(getattr(QgsFeatureRequest, "Flag", QgsFeatureRequest), "NoGeometry")

GROUP_NAME = "地質雲 GeologyCloud"
KEY_PROPERTY = "geologycloud_loader/key"
BBOX_PROPERTY = "geologycloud_loader/bbox"

_URI_TYPES = {POINT: "Point", LINE: "MultiLineString"}


def value_color(value):
    """Stable, readable colour for a category value (same value, same colour)."""
    digest = zlib.crc32(str(value).encode("utf-8"))
    hue = digest % 360
    saturation = 110 + (digest >> 9) % 90
    lightness = 130 + (digest >> 17) % 60
    return QColor.fromHsl(hue, saturation, lightness)


def _fill_symbol(color, opacity, outline="#555555", outline_width="0.15"):
    symbol = QgsFillSymbol.createSimple({
        "color": QColor(color).name(),
        "outline_color": outline,
        "outline_width": outline_width,
    })
    symbol.setOpacity(opacity)
    return symbol


_LABEL_PROPS = getattr(QgsPalLayerSettings, "Property", QgsPalLayerSettings)
_PLACEMENT = getattr(Qgis, "LabelPlacement", QgsPalLayerSettings)
DIP_LABEL_OFFSET = 2.2   # mm from the symbol centre, towards the dip (short tick) side


def dip_offset_expression(angle_field):
    """'x,y' label offset (mm) pointing in the dip direction (azimuth, clockwise
    from north).  Label offsets use screen axes, so north is -y."""
    azimuth = 'radians(coalesce("%s", 0))' % angle_field
    return "concat(to_string(%s * sin(%s)), ',', to_string(-%s * cos(%s)))" % (
        DIP_LABEL_OFFSET, azimuth, DIP_LABEL_OFFSET, azimuth)


def _labeling(expression, size=9.0, mode="point", color="#1d3557", angle_field="Direct"):
    """Label settings.  ``expression`` is a field name or an expression.
    mode: 'point' (over the point), 'dip' (dip side of an attitude symbol),
    'line' (follows the line), 'polygon' (horizontal, inside the polygon)."""
    settings = QgsPalLayerSettings()
    settings.fieldName = expression
    settings.isExpression = "(" in expression
    text_format = QgsTextFormat()
    font = QFont()
    font.setBold(True)
    text_format.setFont(font)
    text_format.setSize(size)
    text_format.setColor(QColor(color))
    buffer = text_format.buffer()
    buffer.setEnabled(True)
    buffer.setSize(0.8)
    buffer.setColor(QColor("white"))
    text_format.setBuffer(buffer)
    settings.setFormat(text_format)
    if mode == "dip":
        settings.placement = _PLACEMENT.OverPoint
        settings.dataDefinedProperties().setProperty(
            _LABEL_PROPS.OffsetXY, QgsProperty.fromExpression(dip_offset_expression(angle_field)))
    elif mode == "line":
        settings.placement = _PLACEMENT.Curved
        settings.repeatDistance = 60.0
    elif mode == "polygon":
        settings.placement = _PLACEMENT.Horizontal
    return QgsVectorLayerSimpleLabeling(settings)


def _single(layer, symbol):
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def apply_style(layer, dataset):
    """Initial renderer.  Code-based layers start with an empty categorized
    renderer; classes are added by ``update_categories`` as codes arrive."""
    style = dataset.style
    kind = style.get("kind")
    if kind in ("spec_area", "spec_line", "spec_point", "categorized"):
        layer.setRenderer(QgsCategorizedSymbolRenderer(style["field"], []))
    elif kind == "fill":
        _single(layer, _fill_symbol(style["color"], style.get("opacity", 0.6)))
    elif kind == "frame":
        _single(layer, symbology.frame_symbol())
    elif kind == "dipslope":
        _single(layer, symbology.dipslope_symbol("SLOPE_DIR"))
    elif kind == "landslide":
        _single(layer, symbology.landslide_symbol(style["code"], style.get("dashed", False)))
    elif kind == "hotspring":
        _single(layer, symbology.hot_spring_symbol())
    elif kind == "borehole":
        _single(layer, symbology.borehole_symbol())
    elif kind == "survey":
        _single(layer, symbology.survey_point_symbol())
    if style.get("label"):
        layer.setLabeling(_labeling(style["label"], style.get("label_size", 9.0), style.get("label_mode", "point"),
                                    style.get("label_color", "#1d3557"), style.get("angle", "Direct")))
        layer.setLabelsEnabled(True)


def _first_attributes(layer, field, value, names):
    """Attribute values of one feature with ``field`` = ``value`` (legend text)."""
    request = QgsFeatureRequest().setFilterExpression(
        QgsExpression.createFieldEqualityExpression(field, value)).setLimit(1)
    request.setFlags(_NO_GEOMETRY)
    for feature in layer.getFeatures(request):
        return {name: feature[name] for name in names if layer.fields().indexOf(name) >= 0}
    return {}


def _text(value):
    if value is None or str(value) in ("", "NULL") or not str(value).strip():
        return None
    return str(value).strip()


def _category_symbol(layer, dataset, value):
    style = dataset.style
    kind = style.get("kind")
    code = str(value)
    if kind == "spec_area":
        attrs = _first_attributes(layer, style["field"], value, [style.get("name"), style.get("abbrev")])
        symbol = symbology.area_symbol(code, style.get("opacity", 1.0))
        label = symbology.area_label(code, _text(attrs.get(style.get("name"))), _text(attrs.get(style.get("abbrev"))))
        return symbol, label
    if kind == "spec_line":
        attrs = _first_attributes(layer, style["field"], value, [style.get("note")])
        return symbology.line_symbol(code), symbology.line_label(code, _text(attrs.get(style.get("note"))))
    if kind == "spec_point":
        attrs = _first_attributes(layer, style["field"], value, [style.get("note")])
        return symbology.attitude_symbol(code, style.get("angle", "Direct")), symbology.point_label(
            code, _text(attrs.get(style.get("note"))))
    return _fill_symbol(value_color(code), style.get("opacity", 0.55)), code


def update_categories(layer, dataset):
    """Add a class (spec symbol + legend text) for every new value; existing
    classes, including any the user restyled, are left untouched."""
    renderer = layer.renderer()
    if not isinstance(renderer, QgsCategorizedSymbolRenderer):
        return
    index = layer.fields().indexOf(renderer.classAttribute())
    if index < 0:
        return
    known = {category.value() for category in renderer.categories()}
    new_values = [v for v in layer.uniqueValues(index) if v not in known and _text(v) is not None]
    if not new_values:
        return
    for value in new_values:
        symbol, label = _category_symbol(layer, dataset, value)
        renderer.addCategory(QgsRendererCategory(value, symbol, label))
    # Keep the legend in code order (spec order), like a printed map legend.
    renderer.sortByValue()


def _metadata(dataset):
    metadata = QgsLayerMetadata()
    metadata.setTitle(dataset.layer_name)
    metadata.setAbstract("%s\n資料來源：%s\n%s\nAPI：%s" % (
        dataset.description, SOURCE_TEXT, dataset.url, SWAGGER_URL))
    metadata.setRights(["資料來源：" + SOURCE_TEXT, "圖例依據：" + symbology.SPEC_SOURCE])
    metadata.setLicenses([LICENSE_TEXT + " " + LICENSE_URL])
    metadata.setKeywords({"GeologyCloud": ["地質雲", dataset.key]})
    return metadata


class LayerManager:
    """Creates, refreshes and removes one memory layer per dataset."""

    def __init__(self, project=None):
        self.project = project or QgsProject.instance()
        self._ids = {}

    # -- lookup ----------------------------------------------------------
    def layer(self, key):
        layer_id = self._ids.get(key)
        layer = self.project.mapLayer(layer_id) if layer_id else None
        if layer is None:
            self._ids.pop(key, None)
        return layer

    def layers(self):
        """Existing plugin layers in catalogue order of creation."""
        return [layer for layer in (self.layer(key) for key in list(self._ids)) if layer is not None]

    # -- create / remove --------------------------------------------------
    def _group(self):
        root = self.project.layerTreeRoot()
        group = root.findGroup(GROUP_NAME)
        if group is None:
            group = root.insertGroup(0, GROUP_NAME)
        return group

    def ensure_layer(self, dataset):
        layer = self.layer(dataset.key)
        if layer is not None:
            return layer
        geometry_type = _URI_TYPES.get(dataset.geometry, "MultiPolygon")
        layer = QgsVectorLayer("%s?crs=EPSG:4326" % geometry_type, dataset.layer_name, "memory")
        layer.dataProvider().addAttributes([make_field(name, kind) for name, kind in dataset.fields])
        layer.updateFields()
        layer.setCustomProperty(KEY_PROPERTY, dataset.key)
        layer.setMetadata(_metadata(dataset))
        apply_style(layer, dataset)
        self.project.addMapLayer(layer, False)
        self._group().insertLayer(0, layer)
        self._ids[dataset.key] = layer.id()
        return layer

    def remove(self, key):
        layer = self.layer(key)
        self._ids.pop(key, None)
        if layer is not None:
            self.project.removeMapLayer(layer.id())
        group = self.project.layerTreeRoot().findGroup(GROUP_NAME)
        if group is not None and not group.children():
            group.parent().removeChildNode(group)

    # -- refresh -----------------------------------------------------------
    def replace_features(self, dataset, rows, bbox=None):
        """Swap the layer content for ``rows``.  Returns the feature count,
        or None when the layer is in edit mode (the user's edits win)."""
        layer = self.ensure_layer(dataset)
        if layer.isEditable():
            return None
        provider = layer.dataProvider()

        names = set(layer.fields().names())
        extra = []
        for _geometry, attributes in rows:
            for name in attributes:
                if name not in names:
                    names.add(name)
                    extra.append(make_field(name, "string"))
        if extra:
            provider.addAttributes(extra)
            layer.updateFields()

        fields = layer.fields()
        numeric = [fields.at(i).isNumeric() for i in range(fields.count())]
        features = []
        for geometry, attributes in rows:
            feature = QgsFeature(fields)
            feature.setGeometry(geometry)
            values = [None] * fields.count()
            for name, value in attributes.items():
                index = fields.indexOf(name)
                if index < 0 or value is None:
                    continue
                if numeric[index]:
                    try:
                        values[index] = float(value)
                    except (TypeError, ValueError):
                        values[index] = None
                else:
                    values[index] = str(value)
            feature.setAttributes(values)
            features.append(feature)

        provider.truncate()
        if features:
            provider.addFeatures(features)
        layer.updateExtents()
        if bbox:
            layer.setCustomProperty(BBOX_PROPERTY, "%.6f,%.6f,%.6f,%.6f" % tuple(bbox))
        update_categories(layer, dataset)
        layer.triggerRepaint()
        return layer.featureCount()
