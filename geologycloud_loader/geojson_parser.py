# -*- coding: utf-8 -*-
"""Convert the service's GeoJSON into QgsGeometry + attribute dictionaries.

The service clips geometries to the requested bbox, so a polygon layer can
receive slivers that collapse to lines or points (and vice versa).  Only the
parts matching the dataset's geometry kind are kept, always as multi-part
geometries for line/polygon datasets so a layer has one consistent type.

This module has no GUI dependencies and is safe to run inside a QgsTask.
"""

import json
import math

from qgis.core import QgsGeometry, QgsPointXY

from .catalog import LINE, POINT, POLYGON


class ServiceError(Exception):
    """The service answered, but not with a usable FeatureCollection."""


def _point(coords):
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        raise ValueError("invalid position")
    x, y = float(coords[0]), float(coords[1])
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError("non-finite coordinate")
    return QgsPointXY(x, y)


def _line(coords):
    return [_point(c) for c in coords]


def _polygon(coords):
    return [_line(ring) for ring in coords]


def _collect(geometry, points, lines, polygons):
    """Split any GeoJSON geometry into point / line / polygon parts."""
    if not isinstance(geometry, dict):
        return
    kind = geometry.get("type")
    coords = geometry.get("coordinates")
    if kind == "Point":
        points.append(_point(coords))
    elif kind == "MultiPoint":
        points.extend(_point(c) for c in coords)
    elif kind == "LineString":
        lines.append(_line(coords))
    elif kind == "MultiLineString":
        lines.extend(_line(c) for c in coords)
    elif kind == "Polygon":
        polygons.append(_polygon(coords))
    elif kind == "MultiPolygon":
        polygons.extend(_polygon(c) for c in coords)
    elif kind == "GeometryCollection":
        for part in geometry.get("geometries") or []:
            _collect(part, points, lines, polygons)


def build_geometry(geometry, target):
    """Return a QgsGeometry of the dataset's kind, or None if nothing fits."""
    points, lines, polygons = [], [], []
    _collect(geometry, points, lines, polygons)
    if target == POINT:
        if len(points) == 1:
            return QgsGeometry.fromPointXY(points[0])
        if points:
            return QgsGeometry.fromMultiPointXY(points)
        return None
    if target == LINE:
        lines = [part for part in lines if len(part) >= 2]
        return QgsGeometry.fromMultiPolylineXY(lines) if lines else None
    if target == POLYGON:
        polygons = [part for part in polygons if part and len(part[0]) >= 4]
        return QgsGeometry.fromMultiPolygonXY(polygons) if polygons else None
    raise ValueError("unknown geometry kind: %r" % (target,))


def clean_value(value):
    """Map JSON values onto what a QGIS string/double field can hold."""
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def parse_feature_collection(payload, target):
    """Parse response bytes/text.  Returns (rows, skipped).

    ``rows`` is a list of ``(QgsGeometry, {property: value})``; ``skipped`` is
    how many features had no usable geometry of the target kind.
    """
    if isinstance(payload, (bytes, bytearray)):
        payload = bytes(payload).decode("utf-8-sig")
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise ServiceError("服務回傳的不是 JSON（%s）" % exc) from exc
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ServiceError("服務回傳的不是 GeoJSON FeatureCollection")
    features = data.get("features")
    if not isinstance(features, list):
        raise ServiceError("FeatureCollection 缺少 features")

    rows, skipped = [], 0
    for feature in features:
        if not isinstance(feature, dict):
            skipped += 1
            continue
        try:
            geometry = build_geometry(feature.get("geometry"), target)
        except (TypeError, ValueError):
            geometry = None
        if geometry is None or geometry.isEmpty():
            skipped += 1
            continue
        properties = feature.get("properties") or {}
        if not isinstance(properties, dict):
            properties = {}
        attributes = {str(k): clean_value(v) for k, v in properties.items()}
        if target == POINT and geometry.isMultipart():
            # Point layers stay single-part: one feature per clipped point.
            for part in geometry.asMultiPoint():
                rows.append((QgsGeometry.fromPointXY(part), dict(attributes)))
        else:
            rows.append((geometry, attributes))
    return rows, skipped
