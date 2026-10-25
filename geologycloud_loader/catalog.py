# -*- coding: utf-8 -*-
"""Dataset catalogue for the Geology Cloud data supply service.

Every entry mirrors one GET endpoint documented at
https://www.geologycloud.tw/geohome/DataService/swagger/api
(``/api/v1/zh-tw/<key>``, GeoJSON in EPSG:4326, ``bbox`` = lon/lat).

``max_span`` is the largest width or height (in degrees) of the view that is
requested automatically.  Heavy island-wide datasets are only fetched when the
map is zoomed in far enough; ``None`` means the whole dataset is small enough
to fetch at any scale.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

API_ROOT = "https://www.geologycloud.tw/api/v1/zh-tw/"
SWAGGER_URL = "https://www.geologycloud.tw/geohome/DataService/swagger/api"
SOURCE_TEXT = "經濟部地質調查及礦業管理中心 地質雲加值應用平臺"
LICENSE_TEXT = "政府資料開放授權條款-第1版 (Open Government Data License, version 1.0)"
LICENSE_URL = "https://data.gov.tw/license"

# Taiwan, Penghu, Kinmen and Matsu, generously padded (lon/lat).
SERVICE_BOUNDS = (117.5, 21.5, 123.5, 26.6)

S = "string"
D = "double"

POINT = "point"
LINE = "line"
POLYGON = "polygon"

GROUPS = ["基本地質圖", "環境地質", "主題圖"]


@dataclass(frozen=True)
class Dataset:
    key: str
    title: str
    group: str
    geometry: str
    fields: Tuple[Tuple[str, str], ...]
    max_span: Optional[float]
    description: str
    style: dict = field(default_factory=dict)

    @property
    def url(self) -> str:
        return API_ROOT + self.key

    @property
    def layer_name(self) -> str:
        return "地質雲｜" + self.title


_F_CODE_NAME_NOTE = (("Code", S), ("Name", S), ("Note", S))
_F_STRATUM = (("Code", S), ("Name", S), ("Note", S), ("Time", S), ("Abbrev", S))
_F_50 = (("LYNOTE_C", S), ("LYNOTE_E", S), ("Code", S), ("NOTE_C", S), ("NOTE_E", S))
_F_DEBRIS = (("IDENTIFIER", S), ("TRAFFIC", S), ("CONSTRUCT", S), ("CONST_NOW", S),
             ("PROT_TARG", S), ("CHAN_WIDTH", S), ("CHAN_ANGLE", S), ("CHAN_VEGE", S))

# Label expressions (blank names such as " " are not labelled).
LABEL_NAME = "nullif(trim(\"Name\"), '')"
LABEL_NAME_ABBREV = "nullif(trim(concat(\"Name\", ' ', \"Abbrev\")), '')"

DATASETS: List[Dataset] = [
    Dataset("Stratum", "5萬分之1 地層", "基本地質圖", POLYGON, _F_STRATUM, 0.5,
            "五萬分之一地層：圖元代號、地層名稱、縮寫、備註、地層年代",
            {"kind": "spec_area", "field": "Code", "name": "Name", "abbrev": "Abbrev", "opacity": 0.8,
             "label": LABEL_NAME_ABBREV, "label_mode": "polygon", "label_size": 8.0, "label_color": "#333333"}),
    Dataset("Fold", "5萬分之1 褶皺", "基本地質圖", LINE, _F_CODE_NAME_NOTE, 1.5,
            "五萬分之一褶皺：圖元代號、名稱、備註",
            {"kind": "spec_line", "field": "Code", "note": "Note",
             "label": LABEL_NAME, "label_mode": "line", "label_size": 8.0, "label_color": "#c00000"}),
    Dataset("Attitude", "5萬分之1 位態", "基本地質圖", POINT,
            (("Code", S), ("Direct", D), ("Angle", D), ("Note", S)), 1.0,
            "五萬分之一位態：走向(Direct)、傾斜(Angle)",
            {"kind": "spec_point", "field": "Code", "note": "Note", "angle": "Direct",
             "label": "Angle", "label_size": 7.0, "label_mode": "dip"}),
    Dataset("Fault", "5萬分之1 斷層", "基本地質圖", LINE, _F_CODE_NAME_NOTE, 2.0,
            "五萬分之一斷層：圖元代號、名稱、備註",
            {"kind": "spec_line", "field": "Code", "note": "Note",
             "label": LABEL_NAME, "label_mode": "line", "label_size": 8.0, "label_color": "#000000"}),
    Dataset("CoalSeam", "5萬分之1 煤層", "基本地質圖", LINE, _F_CODE_NAME_NOTE, 2.0,
            "五萬分之一煤層：圖元代號、備註",
            {"kind": "spec_line", "field": "Code", "note": "Note"}),
    Dataset("MapZone", "5萬分之1 圖幅框", "基本地質圖", POLYGON, (("MapID", S), ("Name", S)), None,
            "全臺五萬分之一圖幅框：圖幅編號、圖幅名稱",
            {"kind": "frame", "label": "Name"}),
    Dataset("Stratum25", "25萬分之1 地層", "基本地質圖", POLYGON, _F_STRATUM, 2.5,
            "二十五萬分之一地層：圖元代號、地層名稱、縮寫、備註、地層年代",
            {"kind": "spec_area", "field": "Code", "name": "Name", "abbrev": "Abbrev", "opacity": 0.8}),
    Dataset("Fault25", "25萬分之1 斷層", "基本地質圖", LINE, _F_CODE_NAME_NOTE, None,
            "二十五萬分之一斷層：圖元代號、名稱、備註",
            {"kind": "spec_line", "field": "Code", "note": "Note"}),

    Dataset("DipSlope", "全臺順向坡", "環境地質", POLYGON,
            (("MAP_NAME", S), ("SLOPE_DIR", S), ("Identifier", S), ("COUN_NAME", S)), 0.3,
            "全臺順向坡分布：圖幅名稱、坡向、識別者、所屬行政區",
            {"kind": "dipslope"}),
    Dataset("RockFall", "全臺落石", "環境地質", POLYGON,
            (("MAP_ID", S), ("MAP_NUM", S), ("MAP_NAME", S), ("IDEN_DATE", S), ("IDENTIFIER", S),
             ("SLOPE_SHA", S), ("SLOPE_DIR", S), ("SLOPE_HEI", S), ("SLOPE_WID", D), ("SLOPE_ANG", S),
             ("SLOPE_VEGE", S), ("ACTIVITY", S), ("SLOPE_HANG", S), ("RF_AREA", D), ("COUN_NAME", S)), 0.3,
            "全臺落石分布：圖幅名稱、識別者、識別時間、活動性、所屬行政區等",
            {"kind": "landslide", "code": "L201"}),
    Dataset("DebrisFlowTrack", "全臺土石流流動區", "環境地質", POLYGON, _F_DEBRIS, 0.5,
            "全臺土石流流動區：保全對象、範圍寬度、流動角度、流動面",
            {"kind": "landslide", "code": "L204"}),
    Dataset("DebrisFlowFan", "全臺土石流扇狀地", "環境地質", POLYGON,
            (("FAN_AREA", D), ("SITECHECK", S)), 1.0,
            "全臺土石流扇狀地分布",
            {"kind": "landslide", "code": "L205", "dashed": True}),
    Dataset("DebrisFlowDeposition", "全臺土石流堆積區", "環境地質", POLYGON, _F_DEBRIS, 1.0,
            "全臺土石流堆積區：識別者、範圍寬度、角度、堆積面",
            {"kind": "landslide", "code": "L205"}),
    Dataset("RockMassClassification", "岩體強度分級", "環境地質", POLYGON,
            (("ST_C", S), ("ABBREV", S), ("CHAR_C", S), ("LITH_C", S), ("強度分級", S)), 0.5,
            "岩體強度分級分布：地層、岩性、強度分級",
            {"kind": "categorized", "field": "強度分級", "opacity": 0.55}),
    Dataset("RockMassStrength", "岩石強度", "環境地質", POLYGON,
            (("ST_C", S), ("ABBREV", S), ("CHAR_C", S), ("LITH_C", S), ("岩石強度", S)), 0.5,
            "岩石強度分布：地層、岩性、岩石強度",
            {"kind": "categorized", "field": "岩石強度", "opacity": 0.55}),

    Dataset("HotSpring", "溫泉露頭點位", "主題圖", POINT,
            (("SpaName", S), ("SpaPH", D), ("Temperature", D), ("Type", S)), None,
            "臺灣溫泉露頭：名稱、PH值、水溫、泉質",
            {"kind": "hotspring"}),
    Dataset("Drill", "工程地質鑽探點位", "主題圖", POINT,
            (("Project_No", S), ("Project_Name", S), ("Hole_Point_No", S), ("Depth", D)), 0.5,
            "工程地質探勘資料庫鑽井位置：計畫編號、計畫名稱、井號、井深度",
            {"kind": "borehole"}),
    Dataset("CGPS", "CGPS連續觀測站", "主題圖", POINT,
            (("CGPS_ID", S), ("NAME", S), ("CGPS_TYPE", S), ("UNIT", S), ("TWD97H", D), ("REMARK", S)), None,
            "GPS連續追蹤站：編號、名稱、類型、建置單位、高程",
            {"kind": "survey"}),
    Dataset("TectonicElement50", "50萬分之1 地體構造單元", "主題圖", POLYGON,
            (("LYNOTE_C", S), ("LYNOTE_E", S), ("Code", S), ("NAME_C", S), ("NAME_E", S),
             ("ABBREV", S), ("NOTE_C", S), ("NOTE_E", S)), None,
            "五十萬分之一地體構造單元：中英文名稱、縮寫、備註",
            {"kind": "spec_area", "field": "Code", "name": "NAME_C", "abbrev": "ABBREV", "opacity": 0.8}),
    Dataset("Fold50", "50萬分之1 褶皺", "主題圖", LINE, _F_50, None,
            "五十萬分之一褶皺",
            {"kind": "spec_line", "field": "Code", "note": "NOTE_C"}),
    Dataset("Discontinuity50", "50萬分之1 不連續面", "主題圖", LINE, _F_50, None,
            "五十萬分之一不連續面（葉理方向）",
            {"kind": "spec_line", "field": "Code", "note": "NOTE_C"}),
    Dataset("Fault50", "50萬分之1 斷層", "主題圖", LINE, _F_50, None,
            "五十萬分之一斷層",
            {"kind": "spec_line", "field": "Code", "note": "NOTE_C"}),
]

BY_KEY = {d.key: d for d in DATASETS}


def span_label(span: Optional[float]) -> str:
    """Human readable size limit (1 degree is roughly 100 km in Taiwan)."""
    if span is None:
        return "不限範圍"
    return "地圖寬或高小於約 %d 公里時載入" % round(span * 100)
