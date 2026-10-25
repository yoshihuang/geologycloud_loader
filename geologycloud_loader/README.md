# GeologyCloud Loader 地質雲資料載入

作者：黃敏郎（GitHub: [yoshihuang](https://github.com/yoshihuang)）

QGIS plugin that loads open geological data from Taiwan's **Geology Cloud value-added
application platform** (地質雲加值應用平臺, Geological Survey and Mining Management Agency, MOEA)
for the current map view.

在 QGIS 中直接介接[地質雲資料供應服務](https://www.geologycloud.tw/geohome/DataService/swagger/api)：
勾選資料項目後，移動或縮放地圖時，套件會自動下載畫面範圍內的資料，以記憶體暫存圖層顯示；
也可以一鍵把所有暫存圖層匯出到指定資料夾。

## 功能

- 23 項資料可複選（基本地質圖、環境地質、主題圖），面板中以樹狀清單呈現，並顯示每項資料的筆數與狀態。
- 地圖移動或縮放停止約 0.7 秒後自動更新；新的範圍會中止舊的下載，最多同時 3 個連線，大量資料在背景解析，不會卡住 QGIS。
- 每項資料一個暫存圖層（EPSG:4326），集中放在「地質雲 GeologyCloud」群組。
- **圖例依《經濟部中央地質調查所數值地質圖資料規範（第 4.4 版）》自動套用**（詳見下方「圖例規範」）。
- 大型資料（地層、順向坡、落石、岩體強度、鑽探點位等）只在地圖放大到一定程度時才下載，
  避免一次下載全台資料；可勾選「忽略建議範圍」強制下載。
- 一鍵匯出：GeoPackage（單一檔或每層一檔）、Shapefile、GeoJSON；
  座標可選 WGS84、TWD97 TM2 121／119，或與專案相同。
  GeoPackage 會把樣式存在檔內，Shapefile／GeoJSON 另附 `.qml` 樣式檔；
  同時產生「資料來源說明.txt」，記錄出處、授權與下載範圍。
- 支援 QGIS 3.34 以上版本，以及 QGIS 4（Qt6）。不需要另外安裝 Python 套件。

## 資料項目

| 分類 | 資料 | API 端點 | 自動下載的範圍上限 |
|---|---|---|---|
| 基本地質圖 | 5萬分之1 地層／褶皺／位態／斷層／煤層／圖幅框 | Stratum, Fold, Attitude, Fault, CoalSeam, MapZone | 約 50／150／100／200／200 公里／不限 |
| 基本地質圖 | 25萬分之1 地層／斷層 | Stratum25, Fault25 | 約 250 公里／不限 |
| 環境地質 | 順向坡、落石、土石流流動區／扇狀地／堆積區、岩體強度分級、岩石強度 | DipSlope, RockFall, DebrisFlowTrack, DebrisFlowFan, DebrisFlowDeposition, RockMassClassification, RockMassStrength | 約 30–100 公里 |
| 主題圖 | 溫泉、工程地質鑽探點位、CGPS、50萬分之1 地體構造／褶皺／不連續面／斷層 | HotSpring, Drill, CGPS, TectonicElement50, Fold50, Discontinuity50, Fault50 | 鑽探點位約 50 公里，其餘不限 |

## 圖例規範

地質雲 API 回傳的 `Code` 欄位就是規範的「符號碼」。套件內建規範附錄五〈圖形符號設計與製作〉的符號資料
（`spec_symbols.json`，407 個面符號碼的前景／背景 RGB 與圖樣），收到資料後依符號碼自動建立分類圖例：

| 圖層 | 套用的規範符號 |
|---|---|
| 5萬／25萬地層、50萬地體構造單元 | 面符號（岩石地層單位 0010–9xxx、T 類）：背景色＋圖樣（橫線、斜線、點、磚紋、鋸齒…）＋前景色；界線依 A101 接觸帶（0.125 mm） |
| 5萬／25萬／50萬斷層 | 線符號 B 類：B101／B102 實線與虛線、B2xx 平移斷層半箭頭、B3xx 正斷層方塊、B4xx 逆斷層鋸齒（在上盤）；活動斷層紅／橘／灰 |
| 5萬／50萬褶皺 | 線符號 C 類（紅色 0.25 mm）：背斜、向斜、倒轉、複背斜／複向斜箭頭，推測者為虛線 |
| 5萬煤層、50萬不連續面 | E101／E102 煤層（紅線＋C 型符號）、D201 葉理方向 |
| 5萬位態 | 點符號 A101–A501（T 字型底線 5 mm），依 `Direct`（傾向，規範 DIREC）旋轉；傾角標註在傾向（短軸）那一側 |
| 順向坡 | L102 順向坡方向符號，依坡向旋轉，標在坡面內 |
| 落石、土石流流動區／堆積區／扇狀地 | L201 墜落區、L204 流動區、L205 崩積區圖樣 |
| 溫泉、鑽探點位、CGPS | X702 溫泉、X901 鑽井位置、Z001 測量點 |
| 圖幅框 | Z101 圖框線 |

- 標註：5萬斷層、褶皺沿線標註 `Name`；5萬地層在面內標註 `Name Abbrev`（名稱空白者不標）。
- 圖例名稱：地層為「符號碼 縮寫 地層名」，線／點符號為「符號碼 規範中文名稱」，依符號碼排序。
- 規範第 4.4 版之後新增的地層碼：同族碼（前三碼相同）沿用同族符號；完全沒有對應的，依岩類範圍
  （沉積岩、火成岩、變質岩…）配色，並在圖例註明「規範未列」。
- API 的 B601（地震地表破裂）在第 4.4 版不是有效線符號碼，改以 B103（地震斷層－位置確定，紅線）繪製。
- 岩體強度分級、岩石強度兩項規範沒有對應符號，維持依屬性分類配色。
- 符號以 SVG 內嵌在樣式中，匯出的 GeoPackage／QML 在沒有安裝本套件的電腦上也能正確顯示。

## 資料授權

資料來源為經濟部地質調查及礦業管理中心「地質雲加值應用平臺」，依
[政府資料開放授權條款－第1版](https://data.gov.tw/license)提供，使用時請註明出處。
本套件只負責介接公開 API，不重新散布資料。

## 開發與測試

```
geologycloud_loader/   # 套件本體（上架時只壓縮這個資料夾）
test/                  # 離線整合測試：以本機假 API 測試解析、圖層、匯出與下載流程
```

```bash
QT_QPA_PLATFORM=offscreen python3 test/test_plugin.py
```

## License

GPL-2.0-or-later. See [LICENSE](LICENSE).
