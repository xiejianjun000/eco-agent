// src/tools/prediction-model-validation.ts
// 环境影响预测模型验证工具
// 依据 HJ 2.2-2018（大气）、HJ 2.3-2018（地表水）、HJ 610-2016（地下水）、HJ 2.4-2021（声环境）等标准

import { IndustryDB } from "../core/industry-db"

export interface PredictionModelResult {
  modelType: string           // 模型类型
  modelName: string          // 具体模型名称
  reportedParameters: Record<string, any>  // 报告中的参数
  standardParameters: Record<string, any>  // 标准要求的参数
  missingParameters: string[]   // 缺失参数
  unreasonableParameters: Array<{
    name: string
    reportedValue: any
    standardRange: { min?: number; max?: number; enum?: string[] }
    severity: "critical" | "major" | "minor"
    description: string
  }>
  predictionResults: Array<{
    pollutant: string
    predictedValue: number
    standardLimit: number
    ratio: number              // 预测值/标准限值
    isExceed: boolean
    location: string
  }>
  issues: Array<{
    type: "model_selection" | "parameter_error" | "calculation_error" | "result_unreasonable" | "missing_content"
    description: string
    severity: "critical" | "major" | "minor"
    suggestion: string
  }>
  confidence: number
}

export interface PredictionModelReport {
  overallScore: number
  totalModels: number
  validModels: number
  suspiciousModels: number
  errorModels: number
  details: PredictionModelResult[]
  summary: string
}

// 大气预测模型标准参数
const AtmosphericModels: Record<string, {
  name: string
  applicable: string[]       // 适用场景
  requiredParameters: Array<{
    name: string
    unit: string
    range?: { min?: number; max?: number }
    enum?: string[]
    description: string
  }>
  resultRequirements: Array<{
    name: string
    description: string
  }>
}> = {
  "AERSCREEN": {
    name: "AERSCREEN 估算模型",
    applicable: ["一级评价", "二级评价", "简单地形", "复杂地形"],
    requiredParameters: [
      { name: "排放源类型", unit: "", enum: ["点源", "面源", "体源", "线源"], description: "污染源类型" },
      { name: "排放高度", unit: "m", range: { min: 0, max: 500 }, description: "排气筒高度或面源有效高度" },
      { name: "排放速率", unit: "g/s", range: { min: 0 }, description: "污染物排放速率" },
      { name: "烟气温度", unit: "K", range: { min: 273, max: 2000 }, description: "排放烟气温度" },
      { name: "烟气量", unit: "m³/s", range: { min: 0 }, description: "排放烟气量" },
      { name: "环境气温", unit: "K", range: { min: 233, max: 323 }, description: "评价区域环境气温" },
      { name: "风速", unit: "m/s", range: { min: 0.5, max: 20 }, description: "平均风速" },
      { name: "稳定度", unit: "", enum: ["A", "B", "C", "D", "E", "F"], description: "大气稳定度" },
      { name: "地形选项", unit: "", enum: ["简单地形", "复杂地形"], description: "地形复杂程度" },
      { name: "建筑物下洗", unit: "", enum: ["是", "否"], description: "是否考虑建筑物下洗" }
    ],
    resultRequirements: [
      { name: "最大落地浓度", description: "预测最大1小时平均浓度" },
      { name: "最大落地浓度距离", description: "最大落地浓度出现距离" },
      { name: "占标率", description: "最大浓度占标准限值百分比" }
    ]
  },
  "AERMOD": {
    name: "AERMOD 扩散模型",
    applicable: ["一级评价", "复杂地形", "城市环境"],
    requiredParameters: [
      { name: "气象数据时长", unit: "年", range: { min: 1 }, description: "地面气象数据时长" },
      { name: "探空数据", unit: "", enum: ["有", "无"], description: "是否有探空数据" },
      { name: "地形数据分辨率", unit: "m", range: { min: 30, max: 3000 }, description: "地形数据分辨率" },
      { name: "网格间距", unit: "m", range: { min: 50, max: 1000 }, description: "预测网格间距" },
      { name: "受体点设置", unit: "", description: "受体点（敏感点）设置" },
      { name: "背景浓度叠加", unit: "", enum: ["是", "否"], description: "是否叠加背景浓度" }
    ],
    resultRequirements: [
      { name: "小时浓度", description: "1小时平均浓度分布" },
      { name: "日均浓度", description: "24小时平均浓度分布" },
      { name: "年均浓度", description: "年平均浓度分布" },
      { name: "保证率日均浓度", description: "保证率日均浓度" }
    ]
  },
  "CALPUFF": {
    name: "CALPUFF 长距离传输模型",
    applicable: ["长距离传输", "复杂风场", "海岸/山谷"],
    requiredParameters: [
      { name: "模拟范围", unit: "km", range: { min: 50 }, description: "模拟区域范围" },
      { name: "网格分辨率", unit: "m", range: { min: 100, max: 5000 }, description: "计算网格分辨率" },
      { name: "气象数据时长", unit: "月", range: { min: 12 }, description: "气象数据时长" },
      { name: "化学转化", unit: "", enum: ["考虑", "不考虑"], description: "是否考虑化学转化" },
      { name: "干湿沉降", unit: "", enum: ["考虑", "不考虑"], description: "是否考虑干湿沉降" }
    ],
    resultRequirements: [
      { name: "逐时浓度", description: "逐小时浓度时间序列" },
      { name: "日均浓度", description: "日平均浓度" },
      { name: "长期平均浓度", description: "长期平均浓度分布" }
    ]
  }
}

// 地表水预测模型标准参数
const SurfaceWaterModels: Record<string, {
  name: string
  applicable: string[]
  requiredParameters: Array<{
    name: string
    unit: string
    range?: { min?: number; max?: number }
    enum?: string[]
    description: string
  }>
  resultRequirements: Array<{ name: string; description: string }>
}> = {
  "零维模型": {
    name: "零维水质模型（完全混合）",
    applicable: ["小型湖泊", "小型水库", "充分混合河段"],
    requiredParameters: [
      { name: "河流流量", unit: "m³/s", range: { min: 0 }, description: "河流流量" },
      { name: "废水流量", unit: "m³/s", range: { min: 0 }, description: "废水排放量" },
      { name: "上游浓度", unit: "mg/L", range: { min: 0 }, description: "上游污染物浓度" },
      { name: "排放浓度", unit: "mg/L", range: { min: 0 }, description: "排放污染物浓度" }
    ],
    resultRequirements: [
      { name: "混合后浓度", description: "完全混合后浓度" },
      { name: "达标分析", description: "是否满足水质标准" }
    ]
  },
  "一维模型": {
    name: "一维水质模型（河流纵向）",
    applicable: ["河流", "明渠"],
    requiredParameters: [
      { name: "河流流速", unit: "m/s", range: { min: 0.01, max: 10 }, description: "河流流速" },
      { name: "河流宽度", unit: "m", range: { min: 0.1 }, description: "河流宽度" },
      { name: "河流深度", unit: "m", range: { min: 0.1 }, description: "河流平均深度" },
      { name: "纵向扩散系数", unit: "m²/s", range: { min: 0 }, description: "纵向扩散系数" },
      { name: "降解系数", unit: "1/d", range: { min: 0 }, description: "污染物降解系数" },
      { name: "预测河段长度", unit: "m", range: { min: 100 }, description: "预测河段长度" }
    ],
    resultRequirements: [
      { name: "浓度纵向分布", description: "沿河流纵向浓度分布" },
      { name: "最大影响距离", description: "污染物最大影响距离" },
      { name: "衰减曲线", description: "浓度衰减曲线" }
    ]
  },
  "二维模型": {
    name: "二维水质模型（河流横向+纵向）",
    applicable: ["宽浅河流", "排污口附近", "河口"],
    requiredParameters: [
      { name: "横向扩散系数", unit: "m²/s", range: { min: 0 }, description: "横向扩散系数" },
      { name: "网格划分", unit: "", description: "计算网格划分" },
      { name: "边界条件", unit: "", description: "边界条件设置" },
      { name: "初始条件", unit: "", description: "初始条件设置" }
    ],
    resultRequirements: [
      { name: "浓度平面分布", description: "污染物浓度平面分布图" },
      { name: "混合区范围", description: "混合区范围及浓度" }
    ]
  }
}

// 地下水预测模型标准参数
const GroundwaterModels: Record<string, {
  name: string
  applicable: string[]
  requiredParameters: Array<{
    name: string
    unit: string
    range?: { min?: number; max?: number }
    enum?: string[]
    description: string
  }>
  resultRequirements: Array<{ name: string; description: string }>
}> = {
  "解析法": {
    name: "地下水解析解模型",
    applicable: ["一级评价", "二级评价", "简单水文地质条件"],
    requiredParameters: [
      { name: "含水层厚度", unit: "m", range: { min: 0.5, max: 500 }, description: "含水层厚度" },
      { name: "渗透系数", unit: "m/d", range: { min: 0.001, max: 1000 }, description: "含水层渗透系数" },
      { name: "水力梯度", unit: "", range: { min: 0.0001, max: 1 }, description: "水力梯度" },
      { name: "有效孔隙度", unit: "", range: { min: 0.01, max: 0.5 }, description: "有效孔隙度" },
      { name: "纵向弥散系数", unit: "m²/d", range: { min: 0.01 }, description: "纵向弥散系数" },
      { name: "横向弥散系数", unit: "m²/d", range: { min: 0.001 }, description: "横向弥散系数" },
      { name: "污染源强", unit: "g/d", range: { min: 0 }, description: "污染源强" },
      { name: "预测时段", unit: "d", range: { min: 100, max: 10000 }, description: "预测时段" }
    ],
    resultRequirements: [
      { name: "浓度-时间曲线", description: "固定点浓度随时间变化" },
      { name: "浓度-距离曲线", description: "固定时刻浓度随距离变化" },
      { name: "影响范围", description: "超标影响范围" },
      { name: "到达时间", description: "污染物到达敏感点的时间" }
    ]
  },
  "数值法": {
    name: "地下水数值模型（MODFLOW/MT3DMS）",
    applicable: ["一级评价", "复杂水文地质条件", "多层含水层"],
    requiredParameters: [
      { name: "模型范围", unit: "km²", range: { min: 1 }, description: "模型模拟范围" },
      { name: "网格分辨率", unit: "m", range: { min: 10, max: 1000 }, description: "网格分辨率" },
      { name: "含水层分层", unit: "", description: "含水层分层数及参数" },
      { name: "边界条件", unit: "", enum: ["定水头", "定流量", "混合边界"], description: "边界条件类型" },
      { name: "源汇项", unit: "", description: "源汇项设置（降雨入渗、蒸发等）" },
      { name: "模型识别", unit: "", enum: ["已完成", "未完成"], description: "模型识别与验证" },
      { name: "识别时段", unit: "月", range: { min: 12 }, description: "模型识别时段" }
    ],
    resultRequirements: [
      { name: "流场拟合", description: "地下水流场拟合图" },
      { name: "浓度场分布", description: "污染物浓度场分布" },
      { name: "时间序列", description: "敏感点浓度时间序列" },
      { name: "影响范围", description: "不同时间的影响范围" }
    ]
  }
}

// 声环境预测模型
const NoiseModels: Record<string, {
  name: string
  applicable: string[]
  requiredParameters: Array<{
    name: string
    unit: string
    range?: { min?: number; max?: number }
    description: string
  }>
  resultRequirements: Array<{ name: string; description: string }>
}> = {
  "工业噪声": {
    name: "工业噪声预测模型",
    applicable: ["工厂", "车间", "设备"],
    requiredParameters: [
      { name: "声源声功率级", unit: "dB", range: { min: 50, max: 150 }, description: "声源声功率级或声压级" },
      { name: "声源数量", unit: "个", range: { min: 1 }, description: "声源数量" },
      { name: "声源位置", unit: "", description: "声源坐标位置" },
      { name: "传播距离", unit: "m", range: { min: 1 }, description: "声源到预测点距离" },
      { name: "屏障衰减", unit: "dB", range: { min: 0, max: 30 }, description: "声屏障衰减量" },
      { name: "地面吸收", unit: "dB", range: { min: 0, max: 10 }, description: "地面吸收衰减" },
      { name: "空气吸收", unit: "dB", range: { min: 0, max: 10 }, description: "空气吸收衰减" },
      { name: "背景噪声", unit: "dB", range: { min: 20, max: 80 }, description: "背景噪声值" }
    ],
    resultRequirements: [
      { name: "贡献值", description: "项目噪声贡献值" },
      { name: "预测值", description: "叠加背景后的预测值" },
      { name: "超标分析", description: "是否满足声环境质量标准" },
      { name: "等声级线图", description: "等声级线图" }
    ]
  },
  "交通噪声": {
    name: "交通噪声预测模型",
    applicable: ["公路", "铁路", "机场"],
    requiredParameters: [
      { name: "车流量", unit: "辆/h", range: { min: 0 }, description: "小时车流量" },
      { name: "车型比例", unit: "", description: "大/中/小型车比例" },
      { name: "车速", unit: "km/h", range: { min: 10, max: 200 }, description: "平均车速" },
      { name: "路面类型", unit: "", description: "路面类型（沥青/水泥）" },
      { name: "纵坡", unit: "%", range: { min: -10, max: 10 }, description: "道路纵坡" }
    ],
    resultRequirements: [
      { name: "等声级线图", description: "道路两侧等声级线图" },
      { name: "敏感点噪声", description: "敏感点昼/夜噪声值" },
      { name: "超标分析", description: "超标情况及范围" }
    ]
  }
}

export class PredictionModelValidationTool {
  private industryDB = new IndustryDB()

  /**
   * 验证环评报告中的预测模型
   */
  async validate(doc: any, industryCode: string): Promise<PredictionModelReport> {
    const results: PredictionModelResult[] = []

    // 1. 识别报告中使用的预测模型
    const identifiedModels = this.identifyModels(doc)

    // 2. 对每个模型进行验证
    for (const model of identifiedModels) {
      const result = await this.validateModel(doc, model)
      results.push(result)
    }

    // 3. 检查是否有遗漏的预测内容
    const missingModels = this.checkMissingModels(doc, industryCode, identifiedModels)
    for (const missing of missingModels) {
      results.push(missing)
    }

    // 4. 计算总体评分
    const total = results.length
    const errors = results.filter(r => r.issues.some(i => i.severity === "critical")).length
    const suspicious = results.filter(r => r.issues.some(i => i.severity === "major" && !r.issues.some(j => j.severity === "critical"))).length
    const valid = total - errors - suspicious

    const score = Math.max(0, 100 - errors * 25 - suspicious * 15)

    return {
      overallScore: score,
      totalModels: total,
      validModels: valid,
      suspiciousModels: suspicious,
      errorModels: errors,
      details: results,
      summary: this.generateSummary(score, total, valid, suspicious, errors)
    }
  }

  /**
   * 识别报告中使用的预测模型
   */
  private identifyModels(doc: any): Array<{
    type: "atmospheric" | "surface_water" | "groundwater" | "noise" | "soil"
    name: string
    location: string
    parameters: Record<string, any>
  }> {
    const models: Array<{
      type: "atmospheric" | "surface_water" | "groundwater" | "noise" | "soil"
      name: string
      location: string
      parameters: Record<string, any>
    }> = []

    const text = doc.text || ""

    // 大气模型识别
    const atmosphericPatterns = [
      { name: "AERSCREEN", pattern: /AERSCREEN/i },
      { name: "AERMOD", pattern: /AERMOD/i },
      { name: "CALPUFF", pattern: /CALPUFF/i },
      { name: "ADMS", pattern: /ADMS/i },
      { name: "估算模式", pattern: /估算模式|SCREEN3/i }
    ]

    for (const { name, pattern } of atmosphericPatterns) {
      const match = text.match(pattern)
      if (match) {
        const params = this.extractParameters(text, match.index || 0, "atmospheric")
        models.push({ type: "atmospheric", name, location: `${match.index}`, parameters: params })
      }
    }

    // 地表水模型识别
    const waterPatterns = [
      { name: "零维模型", pattern: /零维|完全混合/i },
      { name: "一维模型", pattern: /一维.*水质|纵向扩散/i },
      { name: "二维模型", pattern: /二维.*水质|横向扩散/i },
      { name: "MIKE21", pattern: /MIKE21|MIKE/i },
      { name: "EFDC", pattern: /EFDC/i }
    ]

    for (const { name, pattern } of waterPatterns) {
      const match = text.match(pattern)
      if (match) {
        const params = this.extractParameters(text, match.index || 0, "surface_water")
        models.push({ type: "surface_water", name, location: `${match.index}`, parameters: params })
      }
    }

    // 地下水模型识别
    const gwPatterns = [
      { name: "解析法", pattern: /解析法|解析解/i },
      { name: "数值法", pattern: /数值法|数值模拟|MODFLOW|MT3DMS/i },
      { name: "Visual MODFLOW", pattern: /Visual MODFLOW/i },
      { name: "GMS", pattern: /GMS/i }
    ]

    for (const { name, pattern } of gwPatterns) {
      const match = text.match(pattern)
      if (match) {
        const params = this.extractParameters(text, match.index || 0, "groundwater")
        models.push({ type: "groundwater", name, location: `${match.index}`, parameters: params })
      }
    }

    // 声环境模型识别
    const noisePatterns = [
      { name: "工业噪声", pattern: /工业噪声.*预测|声源.*预测/i },
      { name: "交通噪声", pattern: /交通噪声.*预测|公路.*噪声/i }
    ]

    for (const { name, pattern } of noisePatterns) {
      const match = text.match(pattern)
      if (match) {
        const params = this.extractParameters(text, match.index || 0, "noise")
        models.push({ type: "noise", name, location: `${match.index}`, parameters: params })
      }
    }

    return models
  }

  /**
   * 从文本中提取参数
   */
  private extractParameters(text: string, position: number, modelType: string): Record<string, any> {
    const params: Record<string, any> = {}
    const section = text.substring(Math.max(0, position - 500), Math.min(text.length, position + 1000))

    // 通用参数提取模式
    const patterns: Record<string, RegExp> = {
      "排放高度": /排放高度[：:]?\s*([\d.]+)\s*[m米]/,
      "排放速率": /排放速率[：:]?\s*([\d.]+)\s*[g克]/,
      "烟气温度": /烟气温度[：:]?\s*([\d.]+)\s*[Kk]/,
      "烟气量": /烟气量[：:]?\s*([\d.]+)\s*[m³]/,
      "风速": /风速[：:]?\s*([\d.]+)\s*[m米]/,
      "河流流量": /河流流量[：:]?\s*([\d.]+)\s*[m³]/,
      "河流流速": /流速[：:]?\s*([\d.]+)\s*[m米]/,
      "渗透系数": /渗透系数[：:]?\s*([\d.]+)\s*[m米]/,
      "含水层厚度": /含水层厚度[：:]?\s*([\d.]+)\s*[m米]/,
      "声功率级": /声功率级[：:]?\s*([\d.]+)\s*[dD]/,
      "车流量": /车流量[：:]?\s*([\d.]+)/
    }

    for (const [name, pattern] of Object.entries(patterns)) {
      const match = section.match(pattern)
      if (match) {
        params[name] = parseFloat(match[1])
      }
    }

    // 提取枚举类型参数
    const enumPatterns: Record<string, RegExp> = {
      "排放源类型": /排放源类型[：:]?\s*(点源|面源|体源|线源)/,
      "稳定度": /稳定度[：:]?\s*([A-F])/,
      "地形选项": /地形[：:]?\s*(简单|复杂)/,
      "边界条件": /边界条件[：:]?\s*(定水头|定流量|混合)/,
      "模型识别": /模型识别.*(已完成|未完成)/
    }

    for (const [name, pattern] of Object.entries(enumPatterns)) {
      const match = section.match(pattern)
      if (match) {
        params[name] = match[1]
      }
    }

    return params
  }

  /**
   * 验证单个模型
   */
  private async validateModel(
    doc: any,
    model: {
      type: "atmospheric" | "surface_water" | "groundwater" | "noise" | "soil"
      name: string
      location: string
      parameters: Record<string, any>
    }
  ): Promise<PredictionModelResult> {
    const issues: PredictionModelResult["issues"] = []
    const missingParams: string[] = []
    const unreasonableParams: PredictionModelResult["unreasonableParameters"] = []

    // 获取标准模型定义
    let standardModel: any = null
    switch (model.type) {
      case "atmospheric":
        standardModel = AtmosphericModels[model.name]
        break
      case "surface_water":
        standardModel = SurfaceWaterModels[model.name]
        break
      case "groundwater":
        standardModel = GroundwaterModels[model.name]
        break
      case "noise":
        standardModel = NoiseModels[model.name]
        break
    }

    if (!standardModel) {
      return {
        modelType: model.type,
        modelName: model.name,
        reportedParameters: model.parameters,
        standardParameters: {},
        missingParameters: [],
        unreasonableParameters: [],
        predictionResults: [],
        issues: [{
          type: "model_selection",
          description: `使用了未在标准模型库中定义的模型"${model.name}"，请确认模型适用性`,
          severity: "minor",
          suggestion: "建议使用HJ标准推荐的模型，或提供模型适用性论证"
        }],
        confidence: 0.6
      }
    }

    // 检查必需参数
    for (const param of standardModel.requiredParameters) {
      if (model.parameters[param.name] === undefined) {
        missingParams.push(param.name)
        issues.push({
          type: "missing_content",
          description: `缺少必需参数"${param.name}"（${param.description}）`,
          severity: "major",
          suggestion: `应补充${param.name}参数，单位：${param.unit}`
        })
      } else {
        // 检查参数范围
        const value = model.parameters[param.name]
        if (param.range) {
          if (param.range.min !== undefined && value < param.range.min) {
            unreasonableParams.push({
              name: param.name,
              reportedValue: value,
              standardRange: param.range,
              severity: "major",
              description: `${param.name}=${value}${param.unit}，低于标准下限${param.range.min}${param.unit}`
            })
            issues.push({
              type: "parameter_error",
              description: `${param.name}=${value}${param.unit}，低于标准下限${param.range.min}${param.unit}`,
              severity: "major",
              suggestion: `请核实${param.name}参数，应在${param.range.min}~${param.range.max || "∞"}${param.unit}范围内`
            })
          }
          if (param.range.max !== undefined && value > param.range.max) {
            unreasonableParams.push({
              name: param.name,
              reportedValue: value,
              standardRange: param.range,
              severity: "major",
              description: `${param.name}=${value}${param.unit}，超过标准上限${param.range.max}${param.unit}`
            })
            issues.push({
              type: "parameter_error",
              description: `${param.name}=${value}${param.unit}，超过标准上限${param.range.max}${param.unit}`,
              severity: "major",
              suggestion: `请核实${param.name}参数，应在${param.range.min || "0"}~${param.range.max}${param.unit}范围内`
            })
          }
        }

        // 检查枚举值
        if (param.enum && !param.enum.includes(value)) {
          issues.push({
            type: "parameter_error",
            description: `${param.name}="${value}"，不在标准选项[${param.enum.join("、")}]中`,
            severity: "major",
            suggestion: `${param.name}应为：${param.enum.join("、")}`
          })
        }
      }
    }

    // 检查预测结果
    const predictionResults = this.extractPredictionResults(doc, model)

    // 验证结果合理性
    for (const result of predictionResults) {
      if (result.ratio > 1) {
        issues.push({
          type: "result_unreasonable",
          description: `${result.pollutant}在${result.location}的预测浓度${result.predictedValue}超过标准限值${result.standardLimit}（占标率${(result.ratio * 100).toFixed(1)}%）`,
          severity: "critical",
          suggestion: "预测浓度超过环境质量标准，需优化环保措施或调整布局"
        })
      } else if (result.ratio > 0.8) {
        issues.push({
          type: "result_unreasonable",
          description: `${result.pollutant}在${result.location}的预测浓度接近标准限值（占标率${(result.ratio * 100).toFixed(1)}%）`,
          severity: "major",
          suggestion: "预测浓度接近标准限值，建议留足安全余量"
        })
      }
    }

    // 检查是否有结果输出要求
    const text = doc.text || ""
    for (const req of standardModel.resultRequirements) {
      const hasResult = text.includes(req.name) || text.includes(req.description)
      if (!hasResult) {
        issues.push({
          type: "missing_content",
          description: `缺少预测结果"${req.name}"（${req.description}）`,
          severity: "major",
          suggestion: `应补充${req.name}的预测结果`
        })
      }
    }

    const confidence = issues.length === 0 ? 0.95 :
                     issues.some(i => i.severity === "critical") ? 0.5 :
                     issues.some(i => i.severity === "major") ? 0.7 : 0.85

    return {
      modelType: model.type,
      modelName: standardModel.name,
      reportedParameters: model.parameters,
      standardParameters: Object.fromEntries(standardModel.requiredParameters.map((p: any) => [p.name, p])),
      missingParameters: missingParams,
      unreasonableParameters: unreasonableParams,
      predictionResults,
      issues,
      confidence
    }
  }

  /**
   * 提取预测结果
   */
  private extractPredictionResults(doc: any, model: any): Array<{
    pollutant: string
    predictedValue: number
    standardLimit: number
    ratio: number
    isExceed: boolean
    location: string
  }> {
    const results: Array<{
      pollutant: string
      predictedValue: number
      standardLimit: number
      ratio: number
      isExceed: boolean
      location: string
    }> = []

    const text = doc.text || ""

    // 匹配预测浓度数据
    // 格式: 污染物名称 + 预测浓度 + 标准限值 + 占标率 + 位置
    const pattern = /([\u4e00-\u9fa5a-zA-Z0-9]+).*?(?:预测|贡献).*?([\d.]+).*?(?:mg\/m³|μg\/m³|dB|mg\/L).*?(?:标准|限值).*?([\d.]+)/g

    let match
    while ((match = pattern.exec(text)) !== null) {
      const pollutant = match[1].trim()
      const predicted = parseFloat(match[2])
      const standard = parseFloat(match[3])

      if (!isNaN(predicted) && !isNaN(standard) && standard > 0) {
        // 提取位置信息
        const locationMatch = text.substring(Math.max(0, match.index - 100), match.index + 200)
          .match(/([\u4e00-\u9fa5]{2,20}(?:村|小区|学校|医院|保护区|边界))/)

        results.push({
          pollutant,
          predictedValue: predicted,
          standardLimit: standard,
          ratio: predicted / standard,
          isExceed: predicted > standard,
          location: locationMatch ? locationMatch[1] : "未指定位置"
        })
      }
    }

    return results
  }

  /**
   * 检查是否有遗漏的预测模型
   */
  private checkMissingModels(
    doc: any,
    industryCode: string,
    identifiedModels: Array<{ type: string; name: string }>
  ): PredictionModelResult[] {
    const missing: PredictionModelResult[] = []
    const industryInfo = this.industryDB.get(industryCode)

    if (!industryInfo) return missing

    const text = doc.text || ""
    const hasAtmospheric = identifiedModels.some(m => m.type === "atmospheric")
    const hasWater = identifiedModels.some(m => m.type === "surface_water")
    const hasGroundwater = identifiedModels.some(m => m.type === "groundwater")
    const hasNoise = identifiedModels.some(m => m.type === "noise")

    // 根据行业特征判断应有的大气预测
    const hasAirPollutants = industryInfo.keyPollutants.some(p => 
      ["SO2", "NOx", "颗粒物", "VOCs", "PM10", "PM2.5"].includes(p)
    )
    if (hasAirPollutants && !hasAtmospheric) {
      missing.push({
        modelType: "atmospheric",
        modelName: "大气环境影响预测",
        reportedParameters: {},
        standardParameters: {},
        missingParameters: [],
        unreasonableParameters: [],
        predictionResults: [],
        issues: [{
          type: "missing_content",
          description: `${industryInfo.name}(${industryCode})排放大气污染物（${industryInfo.keyPollutants.filter(p => ["SO2", "NOx", "颗粒物", "VOCs"].includes(p)).join("、")}），但未进行大气环境影响预测`,
          severity: "critical",
          suggestion: `应进行大气环境影响预测，推荐使用AERSCREEN或AERMOD模型`
        }],
        confidence: 0.95
      })
    }

    // 判断应有的水环境预测
    const hasWaterPollutants = industryInfo.keyPollutants.some(p =>
      ["COD", "氨氮", "总磷", "总氮", "石油类"].includes(p)
    )
    if (hasWaterPollutants && !hasWater) {
      missing.push({
        modelType: "surface_water",
        modelName: "地表水环境影响预测",
        reportedParameters: {},
        standardParameters: {},
        missingParameters: [],
        unreasonableParameters: [],
        predictionResults: [],
        issues: [{
          type: "missing_content",
          description: `${industryInfo.name}排放水污染物（${industryInfo.keyPollutants.filter(p => ["COD", "氨氮", "总磷", "总氮"].includes(p)).join("、")}），但未进行地表水环境影响预测`,
          severity: "critical",
          suggestion: `应进行地表水环境影响预测，根据河流特征选择零维/一维/二维模型`
        }],
        confidence: 0.95
      })
    }

    // 判断应有的地下水预测（涉及危废、化学品、污水站等）
    const needsGroundwater = industryInfo.keyPollutants.some(p =>
      ["COD", "氨氮", "重金属", "石油类"].includes(p)
    ) || text.includes("危险废物") || text.includes("化学品") || text.includes("污水处理")

    if (needsGroundwater && !hasGroundwater) {
      missing.push({
        modelType: "groundwater",
        modelName: "地下水环境影响预测",
        reportedParameters: {},
        standardParameters: {},
        missingParameters: [],
        unreasonableParameters: [],
        predictionResults: [],
        issues: [{
          type: "missing_content",
          description: `项目涉及化学品/危废/污水处理，存在地下水污染风险，但未进行地下水环境影响预测`,
          severity: "major",
          suggestion: `应进行地下水环境影响预测，推荐采用解析法或数值法（MODFLOW）`
        }],
        confidence: 0.9
      })
    }

    // 判断应有的声环境预测
    const hasNoiseSources = text.includes("风机") || text.includes("泵") || text.includes("压缩机") || 
                          text.includes("冷却塔") || text.includes("发电机")
    if (hasNoiseSources && !hasNoise) {
      missing.push({
        modelType: "noise",
        modelName: "声环境影响预测",
        reportedParameters: {},
        standardParameters: {},
        missingParameters: [],
        unreasonableParameters: [],
        predictionResults: [],
        issues: [{
          type: "missing_content",
          description: `项目存在噪声源（风机/泵/压缩机等），但未进行声环境影响预测`,
          severity: "major",
          suggestion: `应进行声环境影响预测，采用工业噪声预测模型`
        }],
        confidence: 0.9
      })
    }

    return missing
  }

  /**
   * 生成摘要
   */
  private generateSummary(score: number, total: number, valid: number, suspicious: number, errors: number): string {
    if (score >= 90) {
      return `预测模型验证总体良好（${score}分），${total}个模型中${valid}个验证通过，${suspicious}个需复核，${errors}个存在严重问题。`
    } else if (score >= 70) {
      return `预测模型验证存在部分问题（${score}分），${total}个模型中${valid}个验证通过，${suspicious}个需复核，${errors}个存在严重问题。建议重点复核参数设置和预测结果。`
    } else {
      return `预测模型验证存在严重问题（${score}分），${total}个模型中${errors}个存在严重错误，${suspicious}个需复核。建议重新审查模型选择、参数设置和预测结果。`
    }
  }
}

export default PredictionModelValidationTool
