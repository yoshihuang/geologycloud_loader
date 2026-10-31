# -*- coding: utf-8 -*-
"""Dock panel: dataset check list, update controls and one-click export."""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qgis.gui import QgsDockWidget

from .catalog import DATASETS, GROUPS, LICENSE_URL, SOURCE_TEXT, SWAGGER_URL, span_label
from .exporter import CRS_CHOICES, FORMATS
from .wms_catalog import LIST_URL, WMS_GROUPS, WMS_SOURCE_TEXT

KEY_ROLE = Qt.ItemDataRole.UserRole + 1


class GeologyCloudDock(QgsDockWidget):
    selection_changed = pyqtSignal(str, bool)   # dataset key, checked
    refresh_requested = pyqtSignal()
    export_requested = pyqtSignal()
    auto_toggled = pyqtSignal(bool)
    wms_add_requested = pyqtSignal(list)   # WMS layer names

    def __init__(self, parent=None):
        super().__init__("地質雲資料載入", parent)
        self.setObjectName("GeologyCloudLoaderDock")
        self._items = {}
        self._muted = False

        self.tabs = QTabWidget()
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(6, 6, 6, 6)

        hint = QLabel("勾選資料項目後，會下載目前畫面範圍內的資料，以暫存圖層顯示。"
                      "移動地圖後請按「立即更新」，或勾選「移動地圖時自動更新」。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["資料項目", "狀態"])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        self._build_tree()
        self.tree.itemChanged.connect(self._item_changed)
        layout.addWidget(self.tree, 1)

        buttons = QHBoxLayout()
        self.clear_button = QPushButton("全部取消勾選")
        self.clear_button.clicked.connect(self.clear_checks)
        self.refresh_button = QPushButton("立即更新")
        self.refresh_button.setToolTip("以目前地圖範圍重新下載所有勾選的資料")
        self.refresh_button.clicked.connect(self.refresh_requested)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        buttons.addWidget(self.refresh_button)
        layout.addLayout(buttons)

        self.auto_check = QCheckBox("移動地圖時自動更新")
        self.auto_check.setChecked(False)
        self.auto_check.setToolTip("預設不勾選：每次移動或縮放地圖都會向地質雲主機查詢，請視需要再開啟。")
        self.auto_check.toggled.connect(self.auto_toggled)
        layout.addWidget(self.auto_check)
        self.force_check = QCheckBox("忽略建議範圍（大範圍可能要下載很久）")
        self.force_check.setToolTip("大型資料（如地層、順向坡、落石）預設只在地圖放大到一定程度時下載。"
                                    "大範圍查詢會大量請求地質雲主機，請盡量避免。")
        layout.addWidget(self.force_check)
        self.load_warning = QLabel("⚠ 請避免查詢過大的地圖範圍（例如整個縣市或全臺），"
                                   "以免造成地質雲服務主機負荷過大；需要大範圍資料時，請分區放大查詢。")
        self.load_warning.setWordWrap(True)
        self.load_warning.setStyleSheet("color: #b35900;")
        layout.addWidget(self.load_warning)

        export_box = QGroupBox("匯出暫存圖層")
        form = QFormLayout(export_box)
        self.format_combo = QComboBox()
        for format_id, label, *_rest in FORMATS:
            self.format_combo.addItem(label, format_id)
        self.crs_combo = QComboBox()
        for crs_id, label in CRS_CHOICES:
            self.crs_combo.addItem(label, crs_id)
        self.export_button = QPushButton("一鍵匯出所有暫存圖層…")
        self.export_button.clicked.connect(self.export_requested)
        form.addRow("格式", self.format_combo)
        form.addRow("座標", self.crs_combo)
        form.addRow(self.export_button)
        layout.addWidget(export_box)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        credit = QLabel('資料來源：<a href="%s">%s</a>，依<a href="%s">政府資料開放授權條款第1版</a>提供，'
                        "使用時請註明出處。" % (SWAGGER_URL, SOURCE_TEXT, LICENSE_URL))
        credit.setWordWrap(True)
        credit.setOpenExternalLinks(True)
        credit.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(credit)

        self.tabs.addTab(body, "地質雲資料")
        self.tabs.addTab(self._build_wms_tab(), "WMS 圖資")
        self.setWidget(self.tabs)

    # -- WMS tab ---------------------------------------------------------------
    def _build_wms_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        hint = QLabel("地質調查及礦業管理中心「地質圖資 WMS 服務」，分組與圖層順序同官方 QGIS 專案檔。"
                      "勾選後按「加入地圖」，會以 WMS 影像圖層加入，由 QGIS 依畫面範圍即時繪製"
                      "（WMS 影像圖層不包含在「一鍵匯出」中）。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.wms_tree = QTreeWidget()
        self.wms_tree.setHeaderLabels(["WMS 圖層"])
        self.wms_tree.setRootIsDecorated(True)
        self.wms_tree.setUniformRowHeights(True)
        self._wms_items = {}
        for group in WMS_GROUPS:
            parent = QTreeWidgetItem(self.wms_tree, [group.title])
            parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
            parent.setCheckState(0, Qt.CheckState.Unchecked)
            parent.setToolTip(0, "官方 QGIS 專案檔：%s（%d 個圖層）" % (group.title, len(group.layers)))
            for layer in group.layers:
                item = QTreeWidgetItem(parent, [layer.short])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Unchecked)
                item.setData(0, KEY_ROLE, layer.name)
                tip = "%s\nWMS 圖層：%s" % (layer.title, layer.name)
                if layer.hint:
                    tip += "\n資料範圍有限，%s" % layer.hint
                item.setToolTip(0, tip)
                self._wms_items[layer.name] = item
        layout.addWidget(self.wms_tree, 1)

        buttons = QHBoxLayout()
        self.wms_clear_button = QPushButton("全部取消勾選")
        self.wms_clear_button.clicked.connect(self.clear_wms_checks)
        self.wms_add_button = QPushButton("加入地圖")
        self.wms_add_button.setToolTip("把勾選的 WMS 圖層加入「地質調查所 WMS」群組（已加入者不重複加入）")
        self.wms_add_button.clicked.connect(lambda: self.wms_add_requested.emit(self.checked_wms()))
        buttons.addWidget(self.wms_clear_button)
        buttons.addStretch(1)
        buttons.addWidget(self.wms_add_button)
        layout.addLayout(buttons)

        self.wms_status = QLabel("")
        self.wms_status.setWordWrap(True)
        layout.addWidget(self.wms_status)

        credit = QLabel('圖資來源：<a href="%s">%s</a>' % (LIST_URL, WMS_SOURCE_TEXT))
        credit.setWordWrap(True)
        credit.setOpenExternalLinks(True)
        credit.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(credit)
        return page

    def checked_wms(self):
        return [name for name, item in self._wms_items.items() if item.checkState(0) == Qt.CheckState.Checked]

    def clear_wms_checks(self):
        for index in range(self.wms_tree.topLevelItemCount()):
            self.wms_tree.topLevelItem(index).setCheckState(0, Qt.CheckState.Unchecked)

    # -- tree ----------------------------------------------------------------
    def _build_tree(self):
        groups = {}
        for name in GROUPS:
            item = QTreeWidgetItem(self.tree, [name, ""])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setExpanded(True)
            groups[name] = item
        for dataset in DATASETS:
            item = QTreeWidgetItem(groups[dataset.group], [dataset.title, ""])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setData(0, KEY_ROLE, dataset.key)
            item.setToolTip(0, "%s\n%s\nAPI：%s" % (dataset.description, span_label(dataset.max_span), dataset.url))
            self._items[dataset.key] = item

    def _item_changed(self, item, column):
        if column != 0 or self._muted:
            return
        key = item.data(0, KEY_ROLE)
        if key:
            self.selection_changed.emit(key, item.checkState(0) == Qt.CheckState.Checked)

    def checked_keys(self):
        return [key for key, item in self._items.items() if item.checkState(0) == Qt.CheckState.Checked]

    def set_checked(self, keys, emit=False):
        self._muted = not emit
        try:
            for key, item in self._items.items():
                item.setCheckState(0, Qt.CheckState.Checked if key in keys else Qt.CheckState.Unchecked)
        finally:
            self._muted = False

    def clear_checks(self):
        for key in self.checked_keys():
            self._items[key].setCheckState(0, Qt.CheckState.Unchecked)

    def set_state(self, key, text, tooltip=None, error=False):
        item = self._items.get(key)
        if item is None:
            return
        item.setText(1, text)
        item.setToolTip(1, tooltip or text)
        item.setForeground(1, QBrush(QColor("#c1121f")) if error else self.tree.palette().text())

    # -- settings helpers --------------------------------------------------
    def export_format(self):
        return self.format_combo.currentData()

    def export_crs(self):
        return self.crs_combo.currentData()

    def select_combo(self, combo, value):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
