# -*- coding: utf-8 -*-
"""WMS layers of the GSMMA geological map service (地質圖資 WMS 服務).

The list mirrors the QGIS project files published on
https://geomap.gsmma.gov.tw/gsb108-1/list_service.cfm : one group per project
file, layers in the project's drawing order (first = drawn on top).
"""

from collections import namedtuple

# The service page recommends adding "&format=image/png" to the URL for QGIS.
WMS_URL = "https://geomap.gsmma.gov.tw/mapguide/mapagent/mapagent.fcgi?version=1.0.0&format=image/png"
WMS_CRS = "EPSG:4326"
WMS_FORMAT = "image/png"
LIST_URL = "https://geomap.gsmma.gov.tw/gsb108-1/list_service.cfm"
WMS_SOURCE_TEXT = "經濟部地質調查及礦業管理中心 地質圖資 WMS 服務"
WMS_GROUP_NAME = "地質調查所 WMS"

WmsLayer = namedtuple("WmsLayer", "name title short hint")
WmsGroup = namedtuple("WmsGroup", "key title layers")


def _layers(prefix, rows):
    """rows: (WMS layer name, short label[, hint]) -> WmsLayer list."""
    out = []
    for row in rows:
        name, short = row[0], row[1]
        hint = row[2] if len(row) > 2 else ""
        out.append(WmsLayer("WMS/" + name, prefix + short, short, hint))
    return out


WMS_GROUPS = [
    WmsGroup("50k", "1/50,000 臺灣地質圖", _layers("1/50,000_臺灣地質圖-", [
        ("50K_Geomap_Chi-Chi_earthquack_rupture", "集集地震地表破裂"),
        ("50K_Geomap_discontinuity_dip_angle", "不連續面傾角"),
        ("50K_Geomap_discontinuity_attitude", "不連續面位態"),
        ("50K_Geomap_fold", "褶皺"),
        ("50K_Geomap_fault", "斷層"),
        ("50K_Geomap_dip_angle", "地層傾角"),
        ("50K_Geomap_attitude", "地層位態"),
        ("50K_Geomap_fossil", "化石", "範例：白沙屯一帶"),
        ("50K_Geomap_ore_point", "礦床(點)", "範例：南方澳一帶"),
        ("50K_Geomap_ore_line", "礦床(線)", "範例：平溪一帶"),
    ]) + [WmsLayer("WMS/50K_Geomap_index_frame", "1/50,000_臺灣地質圖幅索引圖-圖框", "圖幅索引圖-圖框", ""),
          WmsLayer("WMS/50K_Geomap_index_name", "1/50,000_臺灣地質圖幅索引圖-圖名", "圖幅索引圖-圖名", "")] + _layers("1/50,000_臺灣地質圖-", [
        ("50K_Geomap_infer", "推定之地質資料", "範例：嘉義大埔鄉一帶"),
        ("50K_Geomap_palce_name", "地名"),
        ("50K_Geomap_other", "其他地質"),
        ("50K_Geomap_landslide", "崩塌與崩積區", "範例：中寮一帶"),
        ("50K_Geomap_landslide_boundary", "崩塌與崩積區界線", "範例：中寮一帶"),
        ("50K_Geomap_strata_boundary", "地層界線"),
        ("50K_Geomap_lable", "地層名稱"),
        ("50K_Geomap_strata", "地層"),
    ])),
    WmsGroup("50k_drainage", "1/50,000 臺灣流域地質圖", _layers("1/50,000_臺灣流域地質圖－", [
        ("50K_Geomap_drainage_fold_name_2013", "摺皺名稱_2013"),
        ("50K_Geomap_drainage_fold_2013", "摺皺_2013"),
        ("50K_Geomap_drainage_fault_name_2013", "斷層名稱_2013"),
        ("50K_Geomap_drainage_fault_2013", "斷層_2013"),
        ("50K_Geomap_drainage_lable_2013", "地層名稱_2013"),
        ("50K_Geomap_drainage_strata_boundary_2013", "地層界線_2013"),
        ("50K_Geomap_drainage_strata_2013", "地層_2013"),
    ])),
    WmsGroup("25k_fault", "1/25,000 臺灣活動斷層", _layers("1/25,000_", [
        ("25K_Geomap_fault_2021", "臺灣活動斷層分布圖(含名稱)_2021"),
    ])),
    WmsGroup("250k", "1/250,000 臺灣地質圖", _layers("1/250,000_臺灣地質圖-", [
        ("250K_Geomap_fault_1974", "斷層_1974"),
        ("250K_Geomap_strata_boundary_1974", "地層界線_1974"),
        ("250K_Geomap_lable_1974", "地層代號_1974"),
        ("250K_Geomap_ore_1974", "礦床_1974"),
        ("250K_Geomap_strata_1974", "地層_1974"),
    ])),
    WmsGroup("500k", "1/500,000 臺灣地質圖", _layers("1/500,000_臺灣地體構造圖-", [
        ("500K_Tectonic_map_placename_1978", "地名_1978"),
        ("500K_Tectonic_map_extinct_or_dormant_volcano_1978", "休止火山_1978"),
        ("500K_Tectonic_map_fold_1978", "褶皺_1978"),
        ("500K_Tectonic_map_fault_1978", "斷層_1978"),
        ("500K_Tectonic_map_tectonic_element_1978", "地體構造單元_1978"),
    ]) + _layers("1/500,000_臺灣地質圖-", [
        ("500K_Geomap_earthquake_fault_2000", "地震斷層_2000"),
        ("500K_Geomap_fault_2000", "斷層_2000"),
        ("500K_Geomap_boundary_2000", "地層界線_2000"),
        ("500K_Geomap_lable_2000", "地層名稱_2000"),
        ("500K_Geomap_strata_2000", "地層_2000"),
    ])),
    WmsGroup("1m", "1/1,000,000 臺灣地質圖", _layers("1/1,000,000_臺灣地質圖-", [
        ("1M_Geomap_lable_1986", "地層名稱_1986"),
        ("1M_Geomap_strata_boundary_1986", "地層界線_1986"),
        ("1M_Geomap_strata_1986", "地層_1986"),
    ])),
    WmsGroup("sensitive", "地質敏感區相關圖資", _layers("", [
        ("Sensitive_area_landslide", "山崩與地滑地質敏感區"),
        ("Sensitive_area_groundwater", "地下水補注地質敏感區"),
        ("Sensitive_area_landscape", "地質遺跡地質敏感區"),
        ("Sensitive_area_fault", "活動斷層地質敏感區"),
    ])),
    WmsGroup("environment", "環境地質相關圖資", _layers("環境地質相關圖資_", [
        ("Geomap_Envi_DipSlopeClass_2013", "順向坡岩體滑動潛勢分析圖_2013"),
        ("Geomap_Envi_DebrisSlide_2013", "岩屑崩滑潛勢分析圖_2013"),
        ("Geomap_Envi_DipSlope_2013", "順向坡分布圖_2013"),
        ("Geomap_Envi_RockSlide_2013", "岩體滑動潛勢分析圖_2013"),
    ]) + _layers("", [
        ("Geomap_Envi_Soil_liquefatcion_2021", "初級土壤液化潛勢_2021"),
    ]) + _layers("環境地質相關圖資_", [
        ("Geomap_Envi_Landslide_list_2006-2013", "航照判釋山崩目錄_2006-2013"),
    ])),
    WmsGroup("other", "其他圖資", _layers("", [
        ("Hydrogeological_well", "水文鑽井(含名稱)"),
        ("Spring_2014", "溫泉點位(含名稱)_2014"),
        ("Engineering_drilling", "工程地質探勘資料鑽井位置圖"),
    ])),
]

WMS_BY_NAME = {layer.name: (group, index, layer)
               for group in WMS_GROUPS for index, layer in enumerate(group.layers)}
WMS_GROUP_BY_KEY = {group.key: group for group in WMS_GROUPS}


def wms_uri(layer_name, url=None):
    """Data source string for QgsRasterLayer(..., "wms"), in the same form as the
    official QGIS project files."""
    from qgis.core import QgsDataSourceUri

    uri = QgsDataSourceUri()
    uri.setParam("contextualWMSLegend", "0")
    uri.setParam("crs", WMS_CRS)
    uri.setParam("dpiMode", "7")
    uri.setParam("featureCount", "10")
    uri.setParam("format", WMS_FORMAT)
    uri.setParam("layers", layer_name)
    uri.setParam("styles", "")
    uri.setParam("url", url or WMS_URL)
    return bytes(uri.encodedUri()).decode()
