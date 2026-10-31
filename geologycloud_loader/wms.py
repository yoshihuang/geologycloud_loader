# -*- coding: utf-8 -*-
"""Add GSMMA WMS layers to the project, grouped like the official QGIS projects."""

from qgis.core import QgsProject, QgsRasterLayer

from .layers import GROUP_NAME
from .wms_catalog import WMS_BY_NAME, WMS_GROUP_NAME, WMS_GROUPS, WMS_URL, wms_uri

PROP = "geologycloud_loader/wms_layer"


class WmsManager:
    def __init__(self, project=None, url=None):
        self.project = project or QgsProject.instance()
        self.url = url or WMS_URL

    # -- project tree --------------------------------------------------------
    def _root_group(self):
        root = self.project.layerTreeRoot()
        group = root.findGroup(WMS_GROUP_NAME)
        if group is None:
            # Below the GeologyCloud vector group (if any) so vectors stay on top.
            index = 0
            for i, child in enumerate(root.children()):
                if child.name() == GROUP_NAME:
                    index = i + 1
                    break
            group = root.insertGroup(index, WMS_GROUP_NAME)
        return group

    def _sub_group(self, wms_group):
        parent = self._root_group()
        group = parent.findGroup(wms_group.title)
        if group is None:
            order = [g.title for g in WMS_GROUPS]
            mine = order.index(wms_group.title)
            index = sum(1 for child in parent.children()
                        if child.name() in order and order.index(child.name()) < mine)
            group = parent.insertGroup(index, wms_group.title)
        return group

    def existing(self):
        """WMS layer name -> map layer, for layers this plugin added."""
        found = {}
        for layer in self.project.mapLayers().values():
            name = layer.customProperty(PROP)
            if name:
                found[name] = layer
        return found

    # -- public --------------------------------------------------------------
    def add(self, names):
        """Add WMS layers by name. Returns (added, already_there, failed)."""
        existing = self.existing()
        added, present, failed = [], [], []
        for name in sorted(names, key=_draw_rank):
            if name in existing:
                present.append(name)
                continue
            wms_group, index, info = WMS_BY_NAME[name]
            layer = QgsRasterLayer(wms_uri(name, self.url), info.title, "wms")
            if not layer.isValid():
                failed.append(info.title)
                continue
            layer.setCustomProperty(PROP, name)
            self.project.addMapLayer(layer, False)
            group = self._sub_group(wms_group)
            position = sum(1 for child in group.findLayers()
                           if child.layer() is not None and child.layer().customProperty(PROP) in WMS_BY_NAME
                           and WMS_BY_NAME[child.layer().customProperty(PROP)][1] < index)
            group.insertLayer(position, layer)
            added.append(name)
        return added, present, failed


def _draw_rank(name):
    group, index, _layer = WMS_BY_NAME[name]
    return (WMS_GROUPS.index(group), index)
