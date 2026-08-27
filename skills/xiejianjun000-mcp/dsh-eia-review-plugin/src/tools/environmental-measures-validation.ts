// src/tools/environmental-measures-validation.ts
// 环保措施可行性验证工具
// 检查废气/废水/固废/噪声治理措施的技术可行性、达标可靠性、运行经济性

import { IndustryDB } from "../core/industry-db"

export interface MeasureValidationResult {
  category: "waste_gas" | "waste_water" | "solid_waste" | "noise" | "ecological"
  measureName: string
  technology: string
  targetPollutants: string[]
  designParameters: Record<string, any>
  expectedEfficiency: number
  reportedEfficiency: number
  meetsStandard: boolean
  standardLimit: number
  predictedEmission: number
  issues: Array<{
    type: "technology_selection" | "parameter_unreasonable" | "efficiency_unrealistic" | "standard_not_met" | "missing_linkage" | "economic_unreasonable"
    description: string
    severity: "critical" | "major" | "minor"
    suggestion: string
  }>
  confidence: number
}

export interface MeasuresValidationReport {
  overallScore: number
  totalMeasures: number
  validMeasures: number
  suspiciousMeasures: number
  errorMeasures: number
  categoryScores: Record<string, number>
  details: MeasureValidationResult[]
  summary: string
}

// 废气治理技术数据库
const WasteGasTechnologies: Record<string, {
  name: string
  applicablePollutants: string[]
  typicalEfficiency: { min: number; max: number; typical: number }
  keyParameters: Array<{ name: string; unit: string; range: { min: number; max: number } }>
  limitations: string[]
  operatingCost: { unit: string; range: { min: number; max: number } }
}> = {
  "SCR": {
    name: "选择性催化还原（SCR）脱硝",
    applicablePollutants: ["NOx"],
    typicalEfficiency: { min: 70, max: 95, typical: 85 },
    keyParameters: [
      { name: "反应温度", unit: "°C", range: { min: 280, max: 420 } },
      { name: "氨氮摩尔比", unit: "", range: { min: 0.8, max: 1.2 } },
      { name: "催化剂层数", unit: "层", range: { min: 2, max: 4 } },
      { name: "空速", unit: "h⁻¹", range: { min: 2000, max: 6000 } }
    ],
    limitations: ["需控制氨逃逸<2.5mg/m³", "催化剂寿命3-5年需更换", "对SO₂/SO₃敏感需控制"],
    operatingCost: { unit: "元/吨NOx", range: { min: 3000, max: 8000 } }
  },
  "SNCR": {
    name: "选择性非催化还原（SNCR）脱硝",
    applicablePollutants: ["NOx"],
    typicalEfficiency: { min: 30, max: 60, typical: 45 },
    keyParameters: [
      { name: "反应温度", unit: "°C", range: { min: 850, max: 1100 } },
      { name: "氨氮摩尔比", unit: "", range: { min: 1.0, max: 2.0 } },
      { name: "停留时间", unit: "s", range: { min: 0.5, max: 2.0 } }
    ],
    limitations: ["效率低于SCR", "氨逃逸较高", "温度窗口窄"],
    operatingCost: { unit: "元/吨NOx", range: { min: 2000, max: 5000 } }
  },
  "石灰石石膏法": {
    name: "石灰石-石膏湿法脱硫",
    applicablePollutants: ["SO₂"],
    typicalEfficiency: { min: 85, max: 99, typical: 95 },
    keyParameters: [
      { name: "液气比", unit: "L/m³", range: { min: 8, max: 25 } },
      { name: "pH值", unit: "", range: { min: 5.0, max: 6.2 } },
      { name: "钙硫比", unit: "", range: { min: 1.02, max: 1.05 } },
      { name: "停留时间", unit: "s", range: { min: 10, max: 30 } }
    ],
    limitations: ["产生脱硫石膏需处置", "废水需处理", "占地面积大"],
    operatingCost: { unit: "元/吨SO₂", range: { min: 1500, max: 4000 } }
  },
  "半干法脱硫": {
    name: "半干法脱硫（循环流化床/旋转喷雾）",
    applicablePollutants: ["SO₂"],
    typicalEfficiency: { min: 70, max: 90, typical: 80 },
    keyParameters: [
      { name: "钙硫比", unit: "", range: { min: 1.3, max: 2.0 } },
      { name: "烟气温度", unit: "°C", range: { min: 120, max: 180 } },
      { name: "喷水降温", unit: "", range: { min: 0, max: 1 } }
    ],
    limitations: ["效率低于湿法", "副产物综合利用难", "对入口SO₂浓度敏感"],
    operatingCost: { unit: "元/吨SO₂", range: { min: 2000, max: 5000 } }
  },
  "电除尘": {
    name: "电除尘器",
    applicablePollutants: ["颗粒物", "PM10", "PM2.5"],
    typicalEfficiency: { min: 95, max: 99.9, typical: 99.5 },
    keyParameters: [
      { name: "电场风速", unit: "m/s", range: { min: 0.5, max: 1.5 } },
      { name: "比集尘面积", unit: "m²/(m³/s)", range: { min: 30, max: 150 } },
      { name: "电场数", unit: "个", range: { min: 3, max: 5 } }
    ],
    limitations: ["对高比电阻粉尘效率下降", "对PM2.5捕集效率有限", "需配合湿法或袋式除尘"],
    operatingCost: { unit: "元/吨颗粒物", range: { min: 500, max: 2000 } }
  },
  "袋式除尘": {
    name: "袋式除尘器",
    applicablePollutants: ["颗粒物", "PM10", "PM2.5"],
    typicalEfficiency: { min: 99, max: 99.99, typical: 99.9 },
    keyParameters: [
      { name: "过滤风速", unit: "m/min", range: { min: 0.5, max: 1.2 } },
      { name: "滤袋材质", unit: "", range: { min: 0, max: 1 } },
      { name: "清灰方式", unit: "", range: { min: 0, max: 1 } }
    ],
    limitations: ["滤袋需定期更换", "不适用于高温高湿", "对粘结性粉尘效果差"],
    operatingCost: { unit: "元/吨颗粒物", range: { min: 1000, max: 3000 } }
  },
  "电袋复合": {
    name: "电袋复合除尘器",
    applicablePollutants: ["颗粒物", "PM10", "PM2.5"],
    typicalEfficiency: { min: 99.5, max: 99.99, typical: 99.95 },
    keyParameters: [
      { name: "电场风速", unit: "m/s", range: { min: 0.8, max: 1.5 } },
      { name: "过滤风速", unit: "m/min", range: { min: 0.6, max: 1.0 } }
    ],
    limitations: ["投资较高", "运行维护复杂", "兼具两者缺点"],
    operatingCost: { unit: "元/吨颗粒物", range: { min: 1500, max: 4000 } }
  },
  "RTO": {
    name: "蓄热式热力焚烧（RTO）",
    applicablePollutants: ["VOCs", "NMHC", "苯系物", "恶臭"],
    typicalEfficiency: { min: 95, max: 99, typical: 98 },
    keyParameters: [
      { name: "燃烧温度", unit: "°C", range: { min: 760, max: 1100 } },
      { name: "停留时间", unit: "s", range: { min: 0.5, max: 2.0 } },
      { name: "VOCs浓度", unit: "mg/m³", range: { min: 1000, max: 25000 } },
      { name: "热回收效率", unit: "%", range: { min: 90, max: 97 } }
    ],
    limitations: ["投资高", "适用于高浓度VOCs", "需防爆设计", "产生NOx二次污染"],
    operatingCost: { unit: "元/吨VOCs", range: { min: 5000, max: 15000 } }
  },
  "RCO": {
    name: "蓄热式催化燃烧（RCO）",
    applicablePollutants: ["VOCs", "NMHC", "苯系物"],
    typicalEfficiency: { min: 90, max: 99, typical: 95 },
    keyParameters: [
      { name: "催化温度", unit: "°C", range: { min: 250, max: 450 } },
      { name: "催化剂类型", unit: "", range: { min: 0, max: 1 } },
      { name: "空速", unit: "h⁻¹", range: { min: 5000, max: 40000 } }
    ],
    limitations: ["催化剂中毒失活", "不适用于含硫/氯/硅VOCs", "催化剂需定期更换"],
    operatingCost: { unit: "元/吨VOCs", range: { min: 3000, max: 10000 } }
  },
  "活性炭吸附": {
    name: "活性炭吸附",
    applicablePollutants: ["VOCs", "NMHC", "苯系物", "恶臭", "H₂S"],
    typicalEfficiency: { min: 70, max: 95, typical: 85 },
    keyParameters: [
      { name: "吸附温度", unit: "°C", range: { min: 0, max: 40 } },
      { name: "停留时间", unit: "s", range: { min: 0.5, max: 3.0 } },
      { name: "活性炭更换周期", unit: "月", range: { min: 1, max: 12 } },
      { name: "VOCs入口浓度", unit: "mg/m³", range: { min: 50, max: 5000 } }
    ],
    limitations: ["活性炭饱和需更换", "产生危废", "不适用于高湿度", "对高浓度效率下降"],
    operatingCost: { unit: "元/吨VOCs", range: { min: 8000, max: 20000 } }
  },
  "生物法": {
    name: "生物法（生物滤池/生物滴滤/生物洗涤）",
    applicablePollutants: ["VOCs", "恶臭", "H₂S", "NH₃"],
    typicalEfficiency: { min: 60, max: 90, typical: 75 },
    keyParameters: [
      { name: "停留时间", unit: "s", range: { min: 15, max: 60 } },
      { name: "湿度", unit: "%", range: { min: 40, max: 80 } },
      { name: "pH值", unit: "", range: { min: 5.0, max: 8.5 } },
      { name: "温度", unit: "°C", range: { min: 15, max: 35 } }
    ],
    limitations: ["启动时间长", "对难降解VOCs效率低", "受温度湿度影响大", "占地大"],
    operatingCost: { unit: "元/吨VOCs", range: { min: 2000, max: 6000 } }
  },
  "碱液吸收": {
    name: "碱液吸收（喷淋塔）",
    applicablePollutants: ["HCl", "SO₂", "NOx", "HF", "H₂S", "NH₃"],
    typicalEfficiency: { min: 80, max: 99, typical: 90 },
    keyParameters: [
      { name: "液气比", unit: "L/m³", range: { min: 1, max: 5 } },
      { name: "pH值", unit: "", range: { min: 8, max: 12 } },
      { name: "填料高度", unit: "m", range: { min: 2, max: 6 } }
    ],
    limitations: ["产生废水需处理", "对疏水性气体效率低", "填料堵塞"],
    operatingCost: { unit: "元/吨污染物", range: { min: 1000, max: 5000 } }
  },
  "湿式电除尘": {
    name: "湿式电除尘器（WESP）",
    applicablePollutants: ["颗粒物", "PM2.5", "SO₃酸雾", "重金属"],
    typicalEfficiency: { min: 70, max: 95, typical: 85 },
    keyParameters: [
      { name: "电场风速", unit: "m/s", range: { min: 1.0, max: 3.0 } },
      { name: "比集尘面积", unit: "m²/(m³/s)", range: { min: 10, max: 30 } },
      { name: "冲洗周期", unit: "min", range: { min: 30, max: 120 } }
    ],
    limitations: ["投资高", "产生废水", "需配合前端除尘", "对高比电阻不适用"],
    operatingCost: { unit: "元/吨颗粒物", range: { min: 3000, max: 8000 } }
  }
}

// 废水治理技术数据库
const WasteWaterTechnologies: Record<string, {
  name: string
  applicablePollutants: string[]
  typicalEfficiency: { min: number; max: number; typical: number }
  keyParameters: Array<{ name: string; unit: string; range: { min: number; max: number } }>
  limitations: string[]
  operatingCost: { unit: string; range: { min: number; max: number } }
}> = {
  "格栅": {
    name: "格栅",
    applicablePollutants: ["SS", "漂浮物"],
    typicalEfficiency: { min: 50, max: 90, typical: 70 },
    keyParameters: [
      { name: "栅隙", unit: "mm", range: { min: 5, max: 50 } },
      { name: "过栅流速", unit: "m/s", range: { min: 0.3, max: 1.0 } }
    ],
    limitations: ["仅去除大颗粒", "需定期清渣"],
    operatingCost: { unit: "元/m³", range: { min: 0.1, max: 0.5 } }
  },
  "调节池": {
    name: "调节池",
    applicablePollutants: ["水质水量波动"],
    typicalEfficiency: { min: 0, max: 0, typical: 0 },
    keyParameters: [
      { name: "停留时间", unit: "h", range: { min: 4, max: 24 } },
      { name: "有效容积", unit: "m³", range: { min: 0, max: 100000 } }
    ],
    limitations: ["仅调节均质", "需防臭防沉"],
    operatingCost: { unit: "元/m³", range: { min: 0.1, max: 0.3 } }
  },
  "混凝沉淀": {
    name: "混凝沉淀",
    applicablePollutants: ["SS", "COD", "TP", "重金属", "色度"],
    typicalEfficiency: { min: 60, max: 90, typical: 80 },
    keyParameters: [
      { name: "混凝剂投加量", unit: "mg/L", range: { min: 50, max: 500 } },
      { name: "反应时间", unit: "min", range: { min: 10, max: 30 } },
      { name: "沉淀时间", unit: "h", range: { min: 1, max: 4 } },
      { name: "表面负荷", unit: "m³/(m²·h)", range: { min: 0.5, max: 2.0 } }
    ],
    limitations: ["产生污泥", "对溶解性有机物效果有限", "需优化药剂种类和投加量"],
    operatingCost: { unit: "元/m³", range: { min: 0.5, max: 3.0 } }
  },
  "气浮": {
    name: "气浮",
    applicablePollutants: ["SS", "油类", "乳化油", "纤维"],
    typicalEfficiency: { min: 70, max: 95, typical: 85 },
    keyParameters: [
      { name: "溶气压力", unit: "MPa", range: { min: 0.3, max: 0.6 } },
      { name: "回流比", unit: "%", range: { min: 10, max: 50 } },
      { name: "表面负荷", unit: "m³/(m²·h)", range: { min: 3, max: 10 } }
    ],
    limitations: ["能耗较高", "对密度接近水的颗粒效果差", "需定期排渣"],
    operatingCost: { unit: "元/m³", range: { min: 0.8, max: 4.0 } }
  },
  "厌氧": {
    name: "厌氧处理（UASB/IC/EGSB）",
    applicablePollutants: ["COD", "BOD", "SS"],
    typicalEfficiency: { min: 60, max: 90, typical: 75 },
    keyParameters: [
      { name: "COD容积负荷", unit: "kg/(m³·d)", range: { min: 2, max: 20 } },
      { name: "上升流速", unit: "m/h", range: { min: 0.3, max: 2.0 } },
      { name: "温度", unit: "°C", range: { min: 25, max: 40 } },
      { name: "pH值", unit: "", range: { min: 6.5, max: 7.5 } },
      { name: "停留时间", unit: "h", range: { min: 8, max: 48 } }
    ],
    limitations: ["启动时间长", "对温度敏感", "产生沼气需安全处置", "出水COD仍较高需后续好氧"],
    operatingCost: { unit: "元/m³", range: { min: 0.3, max: 2.0 } }
  },
  "A/O": {
    name: "A/O工艺（缺氧/好氧）",
    applicablePollutants: ["COD", "BOD", "NH₃-N", "TN"],
    typicalEfficiency: { min: 80, max: 95, typical: 90 },
    keyParameters: [
      { name: "污泥龄", unit: "d", range: { min: 10, max: 30 } },
      { name: "DO好氧段", unit: "mg/L", range: { min: 2, max: 4 } },
      { name: "DO缺氧段", unit: "mg/L", range: { min: 0.2, max: 0.5 } },
      { name: "回流比", unit: "%", range: { min: 50, max: 200 } },
      { name: "MLSS", unit: "mg/L", range: { min: 2500, max: 5000 } }
    ],
    limitations: ["脱氮效率有限", "需控制碳氮比", "污泥膨胀风险"],
    operatingCost: { unit: "元/m³", range: { min: 0.5, max: 3.0 } }
  },
  "A²/O": {
    name: "A²/O工艺（厌氧/缺氧/好氧）",
    applicablePollutants: ["COD", "BOD", "NH₃-N", "TN", "TP"],
    typicalEfficiency: { min: 85, max: 98, typical: 92 },
    keyParameters: [
      { name: "污泥龄", unit: "d", range: { min: 10, max: 25 } },
      { name: "DO好氧段", unit: "mg/L", range: { min: 2, max: 4 } },
      { name: "DO缺氧段", unit: "mg/L", range: { min: 0.2, max: 0.5 } },
      { name: "回流比", unit: "%", range: { min: 50, max: 200 } },
      { name: "MLSS", unit: "mg/L", range: { min: 3000, max: 5000 } }
    ],
    limitations: ["除磷效率有限", "污泥龄矛盾（除磷需短龄，硝化需长龄）", "需化学辅助除磷"],
    operatingCost: { unit: "元/m³", range: { min: 0.8, max: 4.0 } }
  },
  "MBR": {
    name: "膜生物反应器（MBR）",
    applicablePollutants: ["COD", "BOD", "SS", "NH₃-N", "TN", "细菌"],
    typicalEfficiency: { min: 90, max: 99, typical: 95 },
    keyParameters: [
      { name: "膜通量", unit: "L/(m²·h)", range: { min: 10, max: 30 } },
      { name: "跨膜压差", unit: "kPa", range: { min: 5, max: 50 } },
      { name: "MLSS", unit: "mg/L", range: { min: 8000, max: 15000 } },
      { name: "清洗周期", unit: "d", range: { min: 7, max: 30 } }
    ],
    limitations: ["膜污染", "膜更换成本高", "能耗高", "需定期化学清洗"],
    operatingCost: { unit: "元/m³", range: { min: 2.0, max: 8.0 } }
  },
  "臭氧氧化": {
    name: "臭氧氧化",
    applicablePollutants: ["COD", "色度", "难降解有机物", "杀菌"],
    typicalEfficiency: { min: 30, max: 70, typical: 50 },
    keyParameters: [
      { name: "臭氧投加量", unit: "mg/L", range: { min: 5, max: 100 } },
      { name: "接触时间", unit: "min", range: { min: 10, max: 30 } },
      { name: "pH值", unit: "", range: { min: 6, max: 9 } }
    ],
    limitations: ["投资高", "运行成本高", "臭氧有毒需防护", "对COD去除有限需配合生化"],
    operatingCost: { unit: "元/m³", range: { min: 3.0, max: 15.0 } }
  },
  "活性炭吸附": {
    name: "活性炭吸附（废水）",
    applicablePollutants: ["COD", "色度", "重金属", "微量有机物"],
    typicalEfficiency: { min: 50, max: 90, typical: 70 },
    keyParameters: [
      { name: "炭层高度", unit: "m", range: { min: 1, max: 3 } },
      { name: "空床流速", unit: "m/h", range: { min: 5, max: 15 } },
      { name: "接触时间", unit: "min", range: { min: 10, max: 30 } },
      { name: "再生周期", unit: "d", range: { min: 30, max: 180 } }
    ],
    limitations: ["活性炭饱和需再生/更换", "产生危废", "投资高"],
    operatingCost: { unit: "元/m³", range: { min: 2.0, max: 10.0 } }
  },
  "反渗透": {
    name: "反渗透（RO）",
    applicablePollutants: ["TDS", "COD", "SS", "重金属", "细菌", "病毒"],
    typicalEfficiency: { min: 90, max: 99, typical: 95 },
    keyParameters: [
      { name: "进水压力", unit: "MPa", range: { min: 0.5, max: 2.0 } },
      { name: "回收率", unit: "%", range: { min: 50, max: 85 } },
      { name: "脱盐率", unit: "%", range: { min: 95, max: 99.5 } },
      { name: "SDI", unit: "", range: { min: 0, max: 5 } }
    ],
    limitations: ["膜污染", "浓水处置", "预处理要求高", "能耗高", "膜更换成本高"],
    operatingCost: { unit: "元/m³", range: { min: 3.0, max: 15.0 } }
  }
}

// 固废处置方式数据库
const SolidWasteDisposal: Record<string, {
  name: string
  applicableTypes: string[]
  requirements: string[]
  limitations: string[]
}> = {
  "焚烧": {
    name: "焚烧处置",
    applicableTypes: ["危险废物", "医疗废物", "污泥", "一般工业固废（热值高）"],
    requirements: ["需有危废经营许可证", "焚烧温度≥1100°C", "烟气停留时间≥2s", "烟气净化达标排放"],
    limitations: ["投资高", "运行成本高", "产生飞灰等二次危废", "需控制二噁英"]
  },
  "填埋": {
    name: "安全填埋",
    applicableTypes: ["危险废物（焚烧残渣）", "一般工业固废", "生活垃圾"],
    requirements: ["需有填埋资质", "防渗系统（HDPE膜）", "渗滤液收集处理", "封场后监测"],
    limitations: ["土地资源占用", "渗滤液长期管理", "选址困难"]
  },
  "综合利用": {
    name: "综合利用",
    applicableTypes: ["一般工业固废", "建筑垃圾", "废金属", "废塑料", "废纸张"],
    requirements: ["符合综合利用标准", "产品质量达标", "有接收单位协议"],
    limitations: ["需有稳定市场", "产品质量需监管", "不能用于食品/医药相关产品"]
  },
  "委外处置": {
    name: "委托有资质单位处置",
    applicableTypes: ["危险废物", "一般工业固废"],
    requirements: ["接收单位有资质", "签订处置协议", "转移联单", "台账记录"],
    limitations: ["处置费用高", "需核实接收单位资质", "运输风险"]
  },
  "自行处置": {
    name: "自行处置/利用",
    applicableTypes: ["一般工业固废", "部分危险废物（有资质）"],
    requirements: ["有处置资质", "环保验收", "达标排放", "台账记录"],
    limitations: ["需取得资质", "投资大", "技术门槛高"]
  }
}

// 噪声控制措施数据库
const NoiseControlMeasures: Record<string, {
  name: string
  applicableSources: string[]
  typicalReduction: { min: number; max: number; typical: number }
  keyParameters: Array<{ name: string; unit: string; range: { min: number; max: number } }>
  limitations: string[]
}> = {
  "隔声": {
    name: "隔声",
    applicableSources: ["风机", "泵", "压缩机", "发电机", "冷却塔"],
    typicalReduction: { min: 10, max: 30, typical: 20 },
    keyParameters: [
      { name: "隔声量", unit: "dB", range: { min: 10, max: 50 } },
      { name: "隔声材料厚度", unit: "mm", range: { min: 50, max: 200 } }
    ],
    limitations: ["对低频效果差", "需密封", "通风散热矛盾"]
  },
  "消声": {
    name: "消声器",
    applicableSources: ["风机", "空压机", "排气", "放空"],
    typicalReduction: { min: 10, max: 40, typical: 25 },
    keyParameters: [
      { name: "消声量", unit: "dB", range: { min: 10, max: 40 } },
      { name: "阻力损失", unit: "Pa", range: { min: 50, max: 500 } }
    ],
    limitations: ["对低频效果差", "需定期维护", "阻力损失影响系统运行"]
  },
  "吸声": {
    name: "吸声",
    applicableSources: ["车间", "机房", "控制室"],
    typicalReduction: { min: 3, max: 10, typical: 5 },
    keyParameters: [
      { name: "吸声系数", unit: "", range: { min: 0.3, max: 1.0 } }
    ],
    limitations: ["仅降低室内混响", "对室外传播无效", "需大面积敷设"]
  },
  "减振": {
    name: "减振",
    applicableSources: ["泵", "压缩机", "风机", "发电机", "变压器"],
    typicalReduction: { min: 5, max: 25, typical: 15 },
    keyParameters: [
      { name: "减振效率", unit: "%", range: { min: 50, max: 95 } },
      { name: "固有频率", unit: "Hz", range: { min: 5, max: 20 } }
    ],
    limitations: ["对高频振动效果好", "需定期更换减振器", "安装要求高"]
  },
  "隔声门窗": {
    name: "隔声门窗",
    applicableSources: ["车间", "机房", "控制室"],
    typicalReduction: { min: 15, max: 35, typical: 25 },
    keyParameters: [
      { name: "隔声量", unit: "dB", range: { min: 15, max: 40 } }
    ],
    limitations: ["影响通风", "需配合隔声墙体", "成本较高"]
  }
}

export class EnvironmentalMeasuresValidationTool {
  private industryDB = new IndustryDB()

  async validate(doc: any, industryCode: string): Promise<MeasuresValidationReport> {
    const results: MeasureValidationResult[] = []

    // 1. 废气治理措施验证
    const gasMeasures = this.validateWasteGasMeasures(doc, industryCode)
    results.push(...gasMeasures)

    // 2. 废水治理措施验证
    const waterMeasures = this.validateWasteWaterMeasures(doc, industryCode)
    results.push(...waterMeasures)

    // 3. 固废处置措施验证
    const solidMeasures = this.validateSolidWasteMeasures(doc, industryCode)
    results.push(...solidMeasures)

    // 4. 噪声控制措施验证
    const noiseMeasures = this.validateNoiseMeasures(doc, industryCode)
    results.push(...noiseMeasures)

    // 5. 计算评分
    const total = results.length
    const errors = results.filter(r => r.issues.some(i => i.severity === "critical")).length
    const suspicious = results.filter(r => r.issues.some(i => i.severity === "major" && !r.issues.some(j => j.severity === "critical"))).length
    const valid = total - errors - suspicious

    const score = Math.max(0, 100 - errors * 20 - suspicious * 10)

    // 分类评分
    const categories = ["waste_gas", "waste_water", "solid_waste", "noise"]
    const categoryScores: Record<string, number> = {}
    for (const cat of categories) {
      const catResults = results.filter(r => r.category === cat)
      if (catResults.length > 0) {
        const catErrors = catResults.filter(r => r.issues.some(i => i.severity === "critical")).length
        const catSuspicious = catResults.filter(r => r.issues.some(i => i.severity === "major")).length
        categoryScores[cat] = Math.max(0, 100 - catErrors * 25 - catSuspicious * 15)
      }
    }

    return {
      overallScore: score,
      totalMeasures: total,
      validMeasures: valid,
      suspiciousMeasures: suspicious,
      errorMeasures: errors,
      categoryScores,
      details: results,
      summary: this.generateSummary(score, total, valid, suspicious, errors, categoryScores)
    }
  }

  private validateWasteGasMeasures(doc: any, industryCode: string): MeasureValidationResult[] {
    const text = doc.text || ""
    const results: MeasureValidationResult[] = []

    // 识别废气治理措施
    for (const [techCode, tech] of Object.entries(WasteGasTechnologies)) {
      if (text.includes(tech.name) || text.includes(techCode)) {
        // 提取设计参数
        const params = this.extractParameters(text, tech.name)

        // 提取效率
        const efficiency = this.extractEfficiency(text, tech.name)

        // 检查适用性
        const industryInfo = this.industryDB.get(industryCode)
        const applicable = industryInfo ? tech.applicablePollutants.some(p => industryInfo.keyPollutants.includes(p)) : true

        const issues: MeasureValidationResult["issues"] = []

        // 检查效率合理性
        if (efficiency > 0) {
          if (efficiency > tech.typicalEfficiency.max) {
            issues.push({
              type: "efficiency_unrealistic",
              description: `${tech.name}设计效率${efficiency}%超过行业典型上限${tech.typicalEfficiency.max}%`,
              severity: "major",
              suggestion: `请核实设计效率，${tech.name}典型效率范围为${tech.typicalEfficiency.min}%-${tech.typicalEfficiency.max}%`
            })
          } else if (efficiency < tech.typicalEfficiency.min) {
            issues.push({
              type: "efficiency_unrealistic",
              description: `${tech.name}设计效率${efficiency}%低于行业典型下限${tech.typicalEfficiency.min}%`,
              severity: "minor",
              suggestion: `设计效率偏低，建议优化至${tech.typicalEfficiency.typical}%左右`
            })
          }
        }

        // 检查关键参数
        for (const param of tech.keyParameters) {
          const paramValue = params[param.name]
          if (paramValue === undefined) {
            issues.push({
              type: "missing_linkage",
              description: `${tech.name}缺少关键设计参数"${param.name}"`,
              severity: "major",
              suggestion: `应补充${param.name}设计参数，标准范围：${param.range.min}${param.unit}~${param.range.max}${param.unit}`
            })
          } else if (paramValue < param.range.min || paramValue > param.range.max) {
            issues.push({
              type: "parameter_unreasonable",
              description: `${tech.name}${param.name}=${paramValue}${param.unit}，超出标准范围${param.range.min}~${param.range.max}${param.unit}`,
              severity: "major",
              suggestion: `请核实${param.name}参数，应在${param.range.min}~${param.range.max}${param.unit}范围内`
            })
          }
        }

        // 检查是否适用
        if (!applicable) {
          issues.push({
            type: "technology_selection",
            description: `${tech.name}可能不适用于${industryInfo?.name || industryCode}行业特征污染物`,
            severity: "minor",
            suggestion: `请确认${tech.name}对该行业特征污染物的去除效果`
          })
        }

        results.push({
          category: "waste_gas",
          measureName: tech.name,
          technology: techCode,
          targetPollutants: tech.applicablePollutants,
          designParameters: params,
          expectedEfficiency: tech.typicalEfficiency.typical,
          reportedEfficiency: efficiency,
          meetsStandard: efficiency > 0 && efficiency <= tech.typicalEfficiency.max && efficiency >= tech.typicalEfficiency.min,
          standardLimit: 0,
          predictedEmission: 0,
          issues,
          confidence: issues.length === 0 ? 0.9 : issues.some(i => i.severity === "critical") ? 0.5 : 0.7
        })
      }
    }

    return results
  }

  private validateWasteWaterMeasures(doc: any, industryCode: string): MeasureValidationResult[] {
    const text = doc.text || ""
    const results: MeasureValidationResult[] = []

    for (const [techCode, tech] of Object.entries(WasteWaterTechnologies)) {
      if (text.includes(tech.name) || text.includes(techCode)) {
        const params = this.extractParameters(text, tech.name)
        const efficiency = this.extractEfficiency(text, tech.name)

        const issues: MeasureValidationResult["issues"] = []

        if (efficiency > 0) {
          if (efficiency > tech.typicalEfficiency.max) {
            issues.push({
              type: "efficiency_unrealistic",
              description: `${tech.name}设计效率${efficiency}%超过典型上限${tech.typicalEfficiency.max}%`,
              severity: "major",
              suggestion: `请核实设计效率，典型范围为${tech.typicalEfficiency.min}%-${tech.typicalEfficiency.max}%`
            })
          }
        }

        for (const param of tech.keyParameters) {
          const paramValue = params[param.name]
          if (paramValue === undefined) {
            issues.push({
              type: "missing_linkage",
              description: `${tech.name}缺少关键参数"${param.name}"`,
              severity: "major",
              suggestion: `应补充${param.name}，范围：${param.range.min}~${param.range.max}${param.unit}`
            })
          } else if (paramValue < param.range.min || paramValue > param.range.max) {
            issues.push({
              type: "parameter_unreasonable",
              description: `${tech.name}${param.name}=${paramValue}${param.unit}超出范围${param.range.min}~${param.range.max}${param.unit}`,
              severity: "major",
              suggestion: `请核实参数合理性`
            })
          }
        }

        results.push({
          category: "waste_water",
          measureName: tech.name,
          technology: techCode,
          targetPollutants: tech.applicablePollutants,
          designParameters: params,
          expectedEfficiency: tech.typicalEfficiency.typical,
          reportedEfficiency: efficiency,
          meetsStandard: true,
          standardLimit: 0,
          predictedEmission: 0,
          issues,
          confidence: issues.length === 0 ? 0.9 : 0.7
        })
      }
    }

    return results
  }

  private validateSolidWasteMeasures(doc: any, industryCode: string): MeasureValidationResult[] {
    const text = doc.text || ""
    const results: MeasureValidationResult[] = []

    // 识别固废处置方式
    for (const [methodCode, method] of Object.entries(SolidWasteDisposal)) {
      if (text.includes(method.name) || text.includes(methodCode)) {
        const issues: MeasureValidationResult["issues"] = []

        // 检查是否有资质要求
        if (methodCode === "焚烧" || methodCode === "填埋" || methodCode === "委外处置") {
          const hasQualification = text.includes("资质") || text.includes("许可证") || text.includes("经营许可证")
          if (!hasQualification) {
            issues.push({
              type: "missing_linkage",
              description: `${method.name}未提及接收单位资质或许可证`,
              severity: "major",
              suggestion: `应明确${method.name}接收单位的资质和许可证情况`
            })
          }
        }

        // 检查转移联单
        if (methodCode === "委外处置") {
          const hasTransfer = text.includes("转移联单") || text.includes("五联单")
          if (!hasTransfer) {
            issues.push({
              type: "missing_linkage",
              description: "危险废物委托处置未提及转移联单管理",
              severity: "major",
              suggestion: "危险废物转移应执行转移联单制度"
            })
          }
        }

        results.push({
          category: "solid_waste",
          measureName: method.name,
          technology: methodCode,
          targetPollutants: method.applicableTypes,
          designParameters: {},
          expectedEfficiency: 100,
          reportedEfficiency: 100,
          meetsStandard: issues.length === 0,
          standardLimit: 0,
          predictedEmission: 0,
          issues,
          confidence: issues.length === 0 ? 0.9 : 0.7
        })
      }
    }

    return results
  }

  private validateNoiseMeasures(doc: any, industryCode: string): MeasureValidationResult[] {
    const text = doc.text || ""
    const results: MeasureValidationResult[] = []

    for (const [measureCode, measure] of Object.entries(NoiseControlMeasures)) {
      if (text.includes(measure.name)) {
        const params = this.extractParameters(text, measure.name)
        const reduction = this.extractNoiseReduction(text, measure.name)

        const issues: MeasureValidationResult["issues"] = []

        if (reduction > 0) {
          if (reduction > measure.typicalReduction.max) {
            issues.push({
              type: "efficiency_unrealistic",
              description: `${measure.name}降噪量${reduction}dB超过典型上限${measure.typicalReduction.max}dB`,
              severity: "major",
              suggestion: `请核实降噪量，${measure.name}典型降噪范围为${measure.typicalReduction.min}~${measure.typicalReduction.max}dB`
            })
          }
        }

        for (const param of measure.keyParameters) {
          const paramValue = params[param.name]
          if (paramValue === undefined) {
            issues.push({
              type: "missing_linkage",
              description: `${measure.name}缺少参数"${param.name}"`,
              severity: "minor",
              suggestion: `应补充${param.name}参数`
            })
          }
        }

        results.push({
          category: "noise",
          measureName: measure.name,
          technology: measureCode,
          targetPollutants: measure.applicableSources,
          designParameters: params,
          expectedEfficiency: measure.typicalReduction.typical,
          reportedEfficiency: reduction,
          meetsStandard: true,
          standardLimit: 0,
          predictedEmission: 0,
          issues,
          confidence: issues.length === 0 ? 0.85 : 0.7
        })
      }
    }

    return results
  }

  private extractParameters(text: string, context: string): Record<string, number> {
    const params: Record<string, number> = {}
    const section = this.extractContextSection(text, context)

    // 通用参数提取模式
    const patterns: Record<string, RegExp> = {
      "反应温度": /反应温度[：:]?\s*([\d.]+)\s*[°℃]/,
      "燃烧温度": /燃烧温度|焚烧温度[：:]?\s*([\d.]+)\s*[°℃]/,
      "停留时间": /停留时间[：:]?\s*([\d.]+)\s*[秒s]/,
      "液气比": /液气比[：:]?\s*([\d.]+)/,
      "pH值": /pH[值]?[：:]?\s*([\d.]+)/,
      "过滤风速": /过滤风速|气布比[：:]?\s*([\d.]+)/,
      "电场风速": /电场风速[：:]?\s*([\d.]+)/,
      "氨氮摩尔比": /氨氮比|NSR|摩尔比[：:]?\s*([\d.]+)/,
      "钙硫比": /钙硫比|Ca\/S[：:]?\s*([\d.]+)/,
      "膜通量": /膜通量[：:]?\s*([\d.]+)/,
      "臭氧投加量": /臭氧[投加量]?[：:]?\s*([\d.]+)/,
      "减振效率": /减振效率|隔振效率[：:]?\s*([\d.]+)/,
      "隔声量": /隔声量|隔声[值]?[：:]?\s*([\d.]+)/
    }

    for (const [name, pattern] of Object.entries(patterns)) {
      const match = section.match(pattern)
      if (match) {
        params[name] = parseFloat(match[1])
      }
    }

    return params
  }

  private extractEfficiency(text: string, context: string): number {
    const section = this.extractContextSection(text, context)
    const match = section.match(/(?:去除效率|处理效率|净化效率|效率)[：:]?\s*([\d.]+)\s*%/)
    return match ? parseFloat(match[1]) : 0
  }

  private extractNoiseReduction(text: string, context: string): number {
    const section = this.extractContextSection(text, context)
    const match = section.match(/(?:降噪量|降噪|隔声量|消声量)[：:]?\s*([\d.]+)\s*dB/)
    return match ? parseFloat(match[1]) : 0
  }

  private extractContextSection(text: string, context: string): string {
    const index = text.indexOf(context)
    if (index === -1) return ""
    return text.substring(Math.max(0, index - 500), Math.min(text.length, index + 1000))
  }

  private generateSummary(score: number, total: number, valid: number, suspicious: number, errors: number, categoryScores: Record<string, number>): string {
    let summary = `环保措施可行性验证${score >= 80 ? "总体良好" : score >= 60 ? "存在部分问题" : "存在严重问题"}（${score}分）。`
    summary += `共${total}项措施，${valid}项可行，${suspicious}项需复核，${errors}项存在严重问题。`

    if (categoryScores["waste_gas"] !== undefined) {
      summary += `废气${categoryScores["waste_gas"]}分`
    }
    if (categoryScores["waste_water"] !== undefined) {
      summary += `、废水${categoryScores["waste_water"]}分`
    }
    if (categoryScores["solid_waste"] !== undefined) {
      summary += `、固废${categoryScores["solid_waste"]}分`
    }
    if (categoryScores["noise"] !== undefined) {
      summary += `、噪声${categoryScores["noise"]}分`
    }
    summary += `。`

    if (score < 60) {
      summary += `建议重点复核技术选型合理性、设计参数准确性和达标可靠性。`
    }

    return summary
  }
}

export default EnvironmentalMeasuresValidationTool
