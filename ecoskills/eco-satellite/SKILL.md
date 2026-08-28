---
name: eco-satellite
description: 卫星遥感与环境事件技能——用 web_fetch 直拉 NASA GIBS/Worldview 免 key 卫星影像（MODIS/VIIRS 真彩色、火灾、气溶胶等图层）与 NASA EONET 环境事件（野火/洪水/风暴/火山）。触发词：卫星、影像、遥感、NDVI、气溶胶、野火、火灾、洪水、风暴、云图。
whenToUse: 用户需要大范围环境监测影像（污染扩散/火灾/洪水）、卫星云图、或环境灾害事件列表时
---

# 卫星遥感与环境事件（eco-satellite）

无需 API Key，直接通过 HTTP 拉取 NASA 开放数据。

## 数据源

1. **NASA GIBS Worldview 卫星影像**（免 key，WMTS 瓦片）：
   `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/{z}/{y}/{x}.jpg`
   - 常用图层：
     - `MODIS_Terra_CorrectedReflectance_TrueColor`（真彩色）
     - `VIIRS_SNPP_CorrectedReflectance_TrueColor`（夜间可用）
     - `MODIS_Terra_Aerosol`（气溶胶/污染扩散）
     - `MODIS_Terra_CorrectedReflectance_TrueColor` + 火灾点 `MODIS_Terra_Thermal_Anomalies`
   - 网页查看：`https://worldview.earthdata.nasa.gov/?l={layer}&t={时间}`
2. **NASA EONET 环境事件**（免 key JSON）：
   `https://eonet.gsfc.nasa.gov/api/v3/events?bbox=经度min,纬度min,经度max,纬度max&category=wildfires,floods,severeStorms`
   - categories: `wildfires`(野火) `floods`(洪水) `severeStorms`(风暴) `volcanoes`(火山) `drought`(干旱) `seaLakeIce`(海冰)

## 使用流程

1. **影像**：web_fetch 访问 `https://worldview.earthdata.nasa.gov/?l=MODIS_Terra_CorrectedReflectance_TrueColor&t=2026-08-27` 获取含目标区域 URL，或直接构造 GIBS 瓦片 URL（需地理范围）
2. **事件**：web_fetch 拉 EONET API（带 bbox），解析 JSON 返回事件列表（类型/位置/时间/几何）
3. **结合气象**：与 open-meteo（天气/空气质量）数据交叉，判断污染扩散/灾害趋势
4. **输出**：事件表（类型/时间/坐标/来源链接）+ 影像说明（图层/时间/区域）

## 示例

- "湖南近期有野火吗？" → EONET `bbox=108,24,114,30&category=wildfires` → 列出事件
- "长三角空气污染扩散影像" → GIBS `MODIS_Terra_Aerosol` 图层 + 说明
