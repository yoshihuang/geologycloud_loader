# -*- coding: utf-8 -*-
"""Plugin entry point: wires the dock, the map canvas, downloads and layers."""

import os

from qgis.PyQt.QtCore import Qt, QTimer, QUrl
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsProject,
    QgsRectangle,
    QgsSettings,
)

from .catalog import BY_KEY, SERVICE_BOUNDS
from .compat import QAction
from .dock import GeologyCloudDock
from .exporter import export_layers
from .fetcher import Fetcher
from .layers import LayerManager

SETTINGS = "geologycloud_loader/"
DEBOUNCE_MS = 700
PLUGIN_DIR = os.path.dirname(__file__)


class GeologyCloudLoader:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dock = None
        self.fetcher = None
        self.layers = None
        self.timer = None
        self._last_bbox = {}   # bbox currently shown in each layer
        self._requested = {}   # bbox of the download in flight

    # -- QGIS plugin API -----------------------------------------------------
    def initGui(self):
        icon = QIcon(os.path.join(PLUGIN_DIR, "icon.svg"))
        self.action = QAction(icon, "地質雲資料載入 (GeologyCloud)", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.setToolTip("開啟／關閉地質雲資料載入面板")
        self.action.toggled.connect(self._toggle_dock)
        self.iface.addWebToolBarIcon(self.action)
        self.iface.addPluginToWebMenu("地質雲資料載入", self.action)

        self.layers = LayerManager()
        self.fetcher = Fetcher()
        self.fetcher.started.connect(self._on_started)
        self.fetcher.finished.connect(self._on_finished)
        self.fetcher.failed.connect(self._on_failed)

        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(DEBOUNCE_MS)
        self.timer.timeout.connect(self.refresh)

        self.dock = GeologyCloudDock(self.iface.mainWindow())
        self.dock.selection_changed.connect(self._on_selection_changed)
        self.dock.refresh_requested.connect(lambda: self.refresh(force=True))
        self.dock.export_requested.connect(self.export_all)
        self.dock.auto_toggled.connect(self._on_auto_toggled)
        self.dock.visibilityChanged.connect(self.action.setChecked)
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.hide()
        self._restore_settings()

        self.iface.mapCanvas().extentsChanged.connect(self._schedule)
        QgsProject.instance().cleared.connect(self._on_project_cleared)

    def unload(self):
        self._save_settings()
        try:
            self.iface.mapCanvas().extentsChanged.disconnect(self._schedule)
            QgsProject.instance().cleared.disconnect(self._on_project_cleared)
        except TypeError:
            pass  # already disconnected
        if self.timer is not None:
            self.timer.stop()
        if self.fetcher is not None:
            self.fetcher.cancel_all()
        if self.dock is not None:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
        if self.action is not None:
            self.iface.removeWebToolBarIcon(self.action)
            self.iface.removePluginWebMenu("地質雲資料載入", self.action)
            self.action.deleteLater()
        self.dock = self.action = self.fetcher = self.timer = None

    # -- settings --------------------------------------------------------------
    def _restore_settings(self):
        settings = QgsSettings()
        self.dock.auto_check.setChecked(settings.value(SETTINGS + "auto", True, type=bool))
        self.dock.select_combo(self.dock.format_combo, settings.value(SETTINGS + "format", "gpkg_single"))
        self.dock.select_combo(self.dock.crs_combo, settings.value(SETTINGS + "crs", "EPSG:3826"))
        # Checked datasets are deliberately not restored: nothing should start
        # downloading the moment QGIS opens.

    def _save_settings(self):
        if self.dock is None:
            return
        settings = QgsSettings()
        settings.setValue(SETTINGS + "auto", self.dock.auto_check.isChecked())
        settings.setValue(SETTINGS + "format", self.dock.export_format())
        settings.setValue(SETTINGS + "crs", self.dock.export_crs())

    # -- dock ----------------------------------------------------------------
    def _toggle_dock(self, checked):
        if self.dock is not None:
            self.dock.setVisible(checked)
            if checked:
                self._schedule()

    def _on_auto_toggled(self, enabled):
        if enabled:
            self._schedule()

    def _on_selection_changed(self, key, checked):
        dataset = BY_KEY[key]
        if checked:
            self.layers.ensure_layer(dataset)
            self._last_bbox.pop(key, None)
            self._request(dataset, self.current_bbox(), force=False)
        else:
            self.fetcher.cancel(key)
            self.layers.remove(key)
            self._last_bbox.pop(key, None)
            self.dock.set_state(key, "")

    def _on_project_cleared(self):
        if self.fetcher is not None:
            self.fetcher.cancel_all()
        self._last_bbox.clear()
        if self.dock is not None:
            self.dock.set_checked([])
            for key in BY_KEY:
                self.dock.set_state(key, "")

    # -- extent handling ---------------------------------------------------
    def current_bbox(self):
        """Visible map extent as a lon/lat bbox clipped to the service area,
        or None when the view is outside Taiwan."""
        canvas = self.iface.mapCanvas()
        source = canvas.mapSettings().destinationCrs()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        extent = canvas.extent()
        if source != wgs84:
            try:
                transform = QgsCoordinateTransform(source, wgs84, QgsProject.instance())
                extent = transform.transformBoundingBox(extent)
            except QgsCsException:
                return None
        clipped = extent.intersect(QgsRectangle(*SERVICE_BOUNDS))
        if clipped.isEmpty() or clipped.width() <= 0 or clipped.height() <= 0:
            return None
        return (round(clipped.xMinimum(), 6), round(clipped.yMinimum(), 6),
                round(clipped.xMaximum(), 6), round(clipped.yMaximum(), 6))

    def _schedule(self):
        if self.dock is not None and self.dock.auto_check.isChecked() and self.dock.checked_keys():
            self.timer.start()

    def refresh(self, force=False):
        if self.dock is None:
            return
        bbox = self.current_bbox()
        for key in self.dock.checked_keys():
            self._request(BY_KEY[key], bbox, force=force)

    def _request(self, dataset, bbox, force):
        key = dataset.key
        if bbox is None:
            self.dock.set_state(key, "不在服務範圍", "目前地圖不在臺灣範圍內，未下載")
            return
        too_big = (dataset.max_span is not None and not self.dock.force_check.isChecked()
                   and max(bbox[2] - bbox[0], bbox[3] - bbox[1]) > dataset.max_span)
        if too_big:
            self.fetcher.cancel(key)
            self.dock.set_state(
                key, "請放大地圖",
                "目前範圍太大，此資料在地圖寬或高小於約 %d 公里時才會下載；"
                "圖層保留上一次的內容。可勾選「忽略建議範圍」強制下載。" % round(dataset.max_span * 100))
            return
        if not force and self._last_bbox.get(key) == bbox and self.layers.layer(key) is not None:
            return
        self._requested[key] = bbox
        self.fetcher.fetch(dataset, bbox)

    # -- download results --------------------------------------------------
    def _on_started(self, key):
        if self.dock is not None:
            self.dock.set_state(key, "下載中…")

    def _on_finished(self, key, rows, skipped, seconds):
        if self.dock is None or key not in self.dock.checked_keys():
            return
        bbox = self._requested.get(key)
        count = self.layers.replace_features(BY_KEY[key], rows, bbox)
        if count is None:
            self.dock.set_state(key, "編輯中未更新", "圖層正在編輯模式，為保護您的修改未更新內容", error=True)
            return
        self._last_bbox[key] = bbox
        tip = "%d 筆，%.1f 秒" % (count, seconds)
        if skipped:
            tip += "（%d 筆裁切後無有效幾何，已略過）" % skipped
        self.dock.set_state(key, "%d 筆" % count, tip)

    def _on_failed(self, key, message):
        if self.dock is not None and key in self.dock.checked_keys():
            self.dock.set_state(key, "錯誤", message, error=True)
            self.iface.messageBar().pushMessage("地質雲", "%s：%s" % (BY_KEY[key].title, message),
                                                Qgis.MessageLevel.Warning, 6)

    # -- export ----------------------------------------------------------------
    def export_all(self):
        layers = self.layers.layers()
        if not any(layer.featureCount() for layer in layers):
            self.iface.messageBar().pushMessage("地質雲", "目前沒有可匯出的暫存圖層資料。",
                                                Qgis.MessageLevel.Info, 5)
            return
        settings = QgsSettings()
        start = settings.value(SETTINGS + "folder", os.path.expanduser("~"))
        folder = QFileDialog.getExistingDirectory(self.iface.mainWindow(), "選擇匯出資料夾", start)
        if not folder:
            return
        settings.setValue(SETTINGS + "folder", folder)
        self._save_settings()
        written, errors = export_layers(layers, folder, self.dock.export_format(), self.dock.export_crs())
        if errors:
            self.iface.messageBar().pushMessage("地質雲", "部分圖層匯出失敗：" + "；".join(errors),
                                                Qgis.MessageLevel.Warning, 10)
        if written:
            self.dock.status.setText("已匯出 %d 個檔案到：%s" % (len(written), folder))
            self.iface.messageBar().pushMessage(
                "地質雲", "已匯出到 <a href=\"%s\">%s</a>" % (
                    QUrl.fromLocalFile(folder).toString(), folder), Qgis.MessageLevel.Success, 8)
