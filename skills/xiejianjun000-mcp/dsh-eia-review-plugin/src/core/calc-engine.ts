// src/core/calc-engine.ts
// 污染物源强核算技术指南公式引擎
// 依据 HJ 884-2018 等标准

export interface CalculationMethod {
  name: string
  description: string
  applicable: string[]  // 适用场景
  formula: string      // 公式表达式
  parameters: Array<{
    name: string
    unit: string
    required: boolean
    description: string
  }>
  validation: (params: Record<string, number>) => { valid: boolean; error?: string }
}

export interface CalculationResult {
  method: string
  pollutant: string
  value: number
  unit: string
  confidence: number  // 计算置信度
  warnings: string[]
}

// 标准核算方法库
export const CalculationMethods: Record<string, CalculationMethod> = {
  "material_balance": {
    name: "物料衡算法",
    description: "根据物质守恒定律，通过输入物料与输出物料的平衡关系计算污染物产生量",
    applicable: ["VOCs", "颗粒物", "SO2", "NOx", "COD", "氨氮"],
    formula: "G = Σ(输入物料量 × 污染物含量) - Σ(产品量 × 污染物含量) - Σ(回收物料量 × 污染物含量)",
    parameters: [
      { name: "input_material", unit: "t/a", required: true, description: "输入物料量" },
      { name: "pollutant_content_input", unit: "%", required: true, description: "输入物料污染物含量" },
      { name: "product_output", unit: "t/a", required: true, description: "产品产量" },
      { name: "pollutant_content_product", unit: "%", required: true, description: "产品污染物含量" },
      { name: "recovery_material", unit: "t/a", required: false, description: "回收物料量" },
      { name: "pollutant_content_recovery", unit: "%", required: false, description: "回收物料污染物含量" }
    ],
    validation: (params) => {
      if (params.input_material <= 0) return { valid: false, error: "输入物料量必须大于0" }
      if (params.pollutant_content_input < 0 || params.pollutant_content_input > 100) {
        return { valid: false, error: "污染物含量应在0-100%之间" }
      }
      return { valid: true }
    }
  },

  "analogy": {
    name: "类比法",
    description: "通过与已建类似项目或设备进行比较，推算污染物产生量",
    applicable: ["VOCs", "颗粒物", "SO2", "NOx", "COD", "氨氮", "噪声"],
    formula: "G = G0 × (Q/Q0)^n × (其他修正系数)",
    parameters: [
      { name: "reference_emission", unit: "t/a", required: true, description: "类比项目污染物排放量" },
      { name: "reference_capacity", unit: "t/a", required: true, description: "类比项目产能" },
      { name: "project_capacity", unit: "t/a", required: true, description: "本项目产能" },
      { name: "scale_exponent", unit: "无量纲", required: false, description: "规模效应指数（通常0.6-0.8）" },
      { name: "correction_factor", unit: "无量纲", required: false, description: "其他修正系数" }
    ],
    validation: (params) => {
      if (params.reference_emission <= 0) return { valid: false, error: "类比项目排放量必须大于0" }
      if (params.reference_capacity <= 0) return { valid: false, error: "类比项目产能必须大于0" }
      if (params.project_capacity <= 0) return { valid: false, error: "本项目产能必须大于0" }
      if (params.scale_exponent !== undefined && (params.scale_exponent < 0 || params.scale_exponent > 1)) {
        return { valid: false, error: "规模效应指数应在0-1之间" }
      }
      return { valid: true }
    }
  },

  "emission_factor": {
    name: "产排污系数法",
    description: "根据单位产品、单位原料或单位设备的污染物产排污系数计算",
    applicable: ["VOCs", "颗粒物", "SO2", "NOx", "COD", "氨氮", "工业固体废物"],
    formula: "G = 产品产量 × 产污系数 × (1 - 去除效率)",
    parameters: [
      { name: "product_output", unit: "t/a", required: true, description: "产品产量" },
      { name: "emission_factor", unit: "kg/t-产品", required: true, description: "产污系数" },
      { name: "removal_efficiency", unit: "%", required: false, description: "去除效率" },
      { name: "operation_hours", unit: "h/a", required: false, description: "年运行小时数" }
    ],
    validation: (params) => {
      if (params.product_output <= 0) return { valid: false, error: "产品产量必须大于0" }
      if (params.emission_factor <= 0) return { valid: false, error: "产污系数必须大于0" }
      if (params.removal_efficiency !== undefined && (params.removal_efficiency < 0 || params.removal_efficiency > 100)) {
        return { valid: false, error: "去除效率应在0-100%之间" }
      }
      return { valid: true }
    }
  },

  "actual_measurement": {
    name: "实测法",
    description: "通过现场监测获取污染物排放浓度和流量，计算排放量",
    applicable: ["所有污染物"],
    formula: "G = C × Q × t × 10^-6",
    parameters: [
      { name: "concentration", unit: "mg/m³", required: true, description: "排放浓度" },
      { name: "flow_rate", unit: "m³/h", required: true, description: "排放流量" },
      { name: "operation_hours", unit: "h/a", required: true, description: "年运行小时数" },
      { name: "monitoring_frequency", unit: "次/年", required: false, description: "监测频次" }
    ],
    validation: (params) => {
      if (params.concentration < 0) return { valid: false, error: "浓度不能为负" }
      if (params.flow_rate <= 0) return { valid: false, error: "流量必须大于0" }
      if (params.operation_hours <= 0) return { valid: false, error: "运行小时数必须大于0" }
      return { valid: true }
    }
  },

  "experimental": {
    name: "实验法",
    description: "通过实验室模拟实验确定污染物产生量",
    applicable: ["VOCs", "特征污染物", "新污染物"],
    formula: "G = 实验测定值 × 生产规模放大系数",
    parameters: [
      { name: "experimental_value", unit: "g/批次", required: true, description: "实验测定值" },
      { name: "scale_factor", unit: "无量纲", required: true, description: "放大系数" },
      { name: "batch_count", unit: "次/年", required: true, description: "年生产批次" },
      { name: "confidence_level", unit: "%", required: false, description: "实验置信度" }
    ],
    validation: (params) => {
      if (params.experimental_value < 0) return { valid: false, error: "实验值不能为负" }
      if (params.scale_factor <= 0) return { valid: false, error: "放大系数必须大于0" }
      if (params.batch_count <= 0) return { valid: false, error: "批次必须大于0" }
      return { valid: true }
    }
  }
}

// 有效核算方法名称集合
export const ValidCalculationMethods = new Set([
  "物料衡算法", "类比法", "实测法", "产排污系数法", "排污系数法",
  "实验法", "material_balance", "analogy", "actual_measurement",
  "emission_factor", "experimental"
])

export class CalculationEngine {
  private methods = CalculationMethods

  validateMethod(methodName: string): { valid: boolean; method?: CalculationMethod; error?: string } {
    // 标准化名称
    const normalized = methodName.replace(/法$/, "").trim()
    const methodKey = Object.keys(this.methods).find(k => {
      const m = this.methods[k]
      return m.name.includes(normalized) || normalized.includes(m.name.replace(/法$/, ""))
    })

    if (methodKey) {
      return { valid: true, method: this.methods[methodKey] }
    }

    if (ValidCalculationMethods.has(methodName)) {
      return { valid: true }
    }

    return { valid: false, error: `非标准核算方法: ${methodName}。应采用物料衡算法、类比法、实测法或产排污系数法` }
  }

  calculate(methodName: string, pollutant: string, params: Record<string, number>): CalculationResult {
    const validation = this.validateMethod(methodName)
    if (!validation.valid) {
      return {
        method: methodName,
        pollutant,
        value: 0,
        unit: "t/a",
        confidence: 0.3,
        warnings: [validation.error || "未知方法"]
      }
    }

    const method = validation.method
    if (!method) {
      return {
        method: methodName,
        pollutant,
        value: 0,
        unit: "t/a",
        confidence: 0.5,
        warnings: ["方法存在但无详细公式验证"]
      }
    }

    // 参数校验
    const paramValidation = method.validation(params)
    if (!paramValidation.valid) {
      return {
        method: methodName,
        pollutant,
        value: 0,
        unit: "t/a",
        confidence: 0.4,
        warnings: [paramValidation.error || "参数校验失败"]
      }
    }

    // 简化计算（实际应根据公式执行）
    let value = 0
    let confidence = 0.85
    const warnings: string[] = []

    switch (method.name) {
      case "物料衡算法":
        value = (params.input_material || 0) * (params.pollutant_content_input || 0) / 100
          - (params.product_output || 0) * (params.pollutant_content_product || 0) / 100
          - (params.recovery_material || 0) * (params.pollutant_content_recovery || 0) / 100
        confidence = 0.90
        break
      case "类比法":
        const scale = (params.project_capacity || 0) / (params.reference_capacity || 1)
        const exponent = params.scale_exponent || 0.7
        value = (params.reference_emission || 0) * Math.pow(scale, exponent) * (params.correction_factor || 1)
        confidence = 0.80
        if (!params.correction_factor) warnings.push("缺少修正系数，计算结果可能偏差")
        break
      case "产排污系数法":
        const removal = (params.removal_efficiency || 0) / 100
        value = (params.product_output || 0) * (params.emission_factor || 0) / 1000 * (1 - removal)
        confidence = 0.85
        break
      case "实测法":
        value = (params.concentration || 0) * (params.flow_rate || 0) * (params.operation_hours || 0) / 1e6
        confidence = 0.95
        if ((params.monitoring_frequency || 0) < 4) warnings.push("监测频次不足，建议每季度至少1次")
        break
      case "实验法":
        value = (params.experimental_value || 0) * (params.scale_factor || 1) * (params.batch_count || 0) / 1e6
        confidence = 0.70
        if ((params.confidence_level || 0) < 95) warnings.push("实验置信度不足，建议提高实验精度")
        break
    }

    return {
      method: method.name,
      pollutant,
      value: Math.max(0, value),
      unit: "t/a",
      confidence,
      warnings
    }
  }

  getRecommendedMethod(pollutant: string, industry: string): string[] {
    const recommendations: string[] = []

    // 根据污染物类型推荐
    if (["VOCs", "NMHC", "TVOC"].includes(pollutant)) {
      recommendations.push("物料衡算法", "实测法")
    } else if (["SO2", "NOx", "颗粒物"].includes(pollutant)) {
      recommendations.push("物料衡算法", "产排污系数法")
    } else if (["COD", "BOD5", "氨氮"].includes(pollutant)) {
      recommendations.push("物料衡算法", "实测法", "产排污系数法")
    } else if (["噪声", "振动"].includes(pollutant)) {
      recommendations.push("实测法", "类比法")
    } else {
      recommendations.push("物料衡算法", "类比法", "实测法")
    }

    // 根据行业调整
    if (["C2614", "C2651", "C2710"].includes(industry)) {
      // 化工/医药优先物料衡算
      recommendations.unshift("物料衡算法")
    } else if (["D4411", "D4412", "C3110"].includes(industry)) {
      // 火电/钢铁优先产排污系数
      recommendations.unshift("产排污系数法")
    }

    return [...new Set(recommendations)]
  }

  crossValidate(methods: Array<{ method: string; result: number }>): { consistent: boolean; deviation: number; recommendation: string } {
    if (methods.length < 2) {
      return { consistent: true, deviation: 0, recommendation: "单一方法，无法交叉验证" }
    }

    const values = methods.map(m => m.result).filter(v => v > 0)
    if (values.length < 2) {
      return { consistent: false, deviation: Infinity, recommendation: "有效结果不足，无法交叉验证" }
    }

    const avg = values.reduce((a, b) => a + b, 0) / values.length
    const max = Math.max(...values)
    const min = Math.min(...values)
    const deviation = (max - min) / avg

    const consistent = deviation < 0.3  // 偏差小于30%认为一致

    return {
      consistent,
      deviation,
      recommendation: consistent
        ? "多种方法计算结果一致，可信度高"
        : `多种方法计算结果偏差${(deviation * 100).toFixed(1)}%，建议复核参数`
    }
  }
}

export default CalculationEngine
