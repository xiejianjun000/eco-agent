// src/tools/source-analysis.ts
// 污染物源强分析工具
// 自动识别报告中的源强数据，用标准公式验证计算准确性

import { CalculationEngine } from "../core/calc-engine"
import { IndustryDB } from "../core/industry-db"

export interface SourceAnalysisResult {
  pollutant: string
  reportedValue: number
  reportedUnit: string
  calculatedValue: number
  calculatedUnit: string
  deviation: number
  method: string
  recommendedMethod: string
  parameters: Record<string, number>
  issues: Array<{
    type: "calculation_error" | "unit_mismatch" | "missing_parameter" | "unreasonable_value" | "method_incorrect"
    description: string
    severity: "critical" | "major" | "minor"
    suggestion: string
  }>
  confidence: number
}

export interface SourceAnalysisReport {
  overallScore: number
  totalPollutants: number
  correctCalculations: number
  suspiciousCalculations: number
  errors: number
  details: SourceAnalysisResult[]
  summary: string
}

export class SourceAnalysisTool {
  private calcEngine = new CalculationEngine()
  private industryDB = new IndustryDB()

  async analyze(doc: any, industryCode: string): Promise<SourceAnalysisReport> {
    const results: SourceAnalysisResult[] = []
    const industryInfo = this.industryDB.get(industryCode)

    const extractedSources = this.extractSourceData(doc)

    for (const source of extractedSources) {
      const result = await this.validateSource(source, industryCode, industryInfo)
      results.push(result)
    }

    if (industryInfo) {
      const missingPollutants = industryInfo.keyPollutants.filter(
        kp => !extractedSources.some(es => es.pollutant.includes(kp) || kp.includes(es.pollutant))
      )

      for (const missing of missingPollutants) {
        results.push({
          pollutant: missing,
          reportedValue: 0,
          reportedUnit: "t/a",
          calculatedValue: 0,
          calculatedUnit: "t/a",
          deviation: 0,
          method: "未找到",
          recommendedMethod: this.getRecommendedMethod(missing, industryCode),
          parameters: {},
          issues: [{
            type: "missing_parameter",
            description: `${missing}是${industryInfo.name}的特征污染物，但报告中未找到源强核算数据`,
            severity: "major",
            suggestion: `应补充${missing}的源强核算，推荐采用${this.getRecommendedMethod(missing, industryCode)}`
          }],
          confidence: 0.95
        })
      }
    }

    const total = results.length
    const errors = results.filter(r => r.issues.some(i => i.severity === "critical")).length
    const suspicious = results.filter(r => r.issues.some(i => i.severity === "major" && !r.issues.some(j => j.severity === "critical"))).length
    const correct = total - errors - suspicious

    const score = Math.max(0, 100 - errors * 20 - suspicious * 10)

    return {
      overallScore: score,
      totalPollutants: total,
      correctCalculations: correct,
      suspiciousCalculations: suspicious,
      errors,
      details: results,
      summary: this.generateSummary(score, total, correct, suspicious, errors)
    }
  }

  private extractSourceData(doc: any): Array<{
    pollutant: string
    value: number
    unit: string
    method: string
    location: string
    parameters: Record<string, string>
  }> {
    const sources: any[] = []
    const text = doc.text || ""

    const patterns = [
      /([\u4e00-\u9fa5a-zA-Z0-9]+)[\s]*(?:产生量|排放量|源强)[\s]*[:：]?[\s]*([\d.]+)[\s]*([\u4e00-\u9fa5a-zA-Z/]+)/g,
      /污染物[：:]?([\u4e00-\u9fa5a-zA-Z0-9]+)[\s\S]*?(?:排放量|产生量)[：:]?([\d.]+)[\s]*([\u4e00-\u9fa5a-zA-Z/]+)/g,
      /([\u4e00-\u9fa5a-zA-Z0-9]+)[\s|]+([\d.]+)[\s|]+([\u4e00-\u9fa5a-zA-Z/]+)/g
    ]

    for (const pattern of patterns) {
      let match
      while ((match = pattern.exec(text)) !== null) {
        const pollutant = match[1].trim()
        const value = parseFloat(match[2])
        const unit = match[3].trim()

        if (!isNaN(value) && value > 0) {
          const methodMatch = text.substring(Math.max(0, match.index - 200), match.index + 200)
            .match(/(?:采用|使用|核算方法)[：:]?([\u4e00-\u9fa5]+法)/)

          const paramSection = text.substring(Math.max(0, match.index - 500), match.index + 500)
          const params: Record<string, string> = {}

          const paramPatterns = [
            /产量[：:]?([\d.]+)[\s]*([\u4e00-\u9fa5a-zA-Z/]+)/,
            /原辅料[：:]?([\d.]+)[\s]*([\u4e00-\u9fa5a-zA-Z/]+)/,
            /去除效率[：:]?([\d.]+)[\s]*%/,
            /产污系数[：:]?([\d.]+)/,
            /排放浓度[：:]?([\d.]+)[\s]*mg\/m³/
          ]

          for (const pp of paramPatterns) {
            const pm = paramSection.match(pp)
            if (pm) {
              const key = pp.source.match(/\w+/)?.[0] || "参数"
              params[key] = pm[1] + (pm[2] || "")
            }
          }

          sources.push({ pollutant, value, unit, method: methodMatch ? methodMatch[1] : "未识别", location: `${match.index}`, parameters: params })
        }
      }
    }

    const unique = new Map()
    for (const s of sources) {
      const key = `${s.pollutant}_${s.value}_${s.unit}`
      if (!unique.has(key)) unique.set(key, s)
    }
    return Array.from(unique.values())
  }

  private async validateSource(source: any, industryCode: string, industryInfo: any): Promise<SourceAnalysisResult> {
    const issues: any[] = []
    let calculatedValue = 0
    let recommendedMethod = this.getRecommendedMethod(source.pollutant, industryCode)

    const methodValidation = this.calcEngine.validateMethod(source.method)
    if (!methodValidation.valid) {
      issues.push({
        type: "method_incorrect",
        description: `使用非标准核算方法"${source.method}"，${methodValidation.error}`,
        severity: "major",
        suggestion: `应改用${recommendedMethod}进行核算`
      })
    }

    try {
      const params = this.parseParameters(source.parameters, source.pollutant)

      if (methodValidation.valid && methodValidation.method) {
        const calcResult = this.calcEngine.calculate(source.method, source.pollutant, params)
        calculatedValue = calcResult.value

        if (calculatedValue > 0) {
          const deviation = Math.abs(source.value - calculatedValue) / calculatedValue * 100

          if (deviation > 50) {
            issues.push({ type: "calculation_error", description: `计算结果偏差${deviation.toFixed(1)}%，报告值${source.value} vs 计算值${calculatedValue.toFixed(2)}`, severity: "critical", suggestion: "请重新核算，检查参数输入是否正确" })
          } else if (deviation > 20) {
            issues.push({ type: "calculation_error", description: `计算结果偏差${deviation.toFixed(1)}%，建议复核`, severity: "major", suggestion: "请复核计算过程和参数" })
          }

          if (params.removal_efficiency !== undefined && params.removal_efficiency > 100) {
            issues.push({ type: "unreasonable_value", description: `去除效率${params.removal_efficiency}%超过100%`, severity: "critical", suggestion: "去除效率应在0-100%之间" })
          }
          if (params.removal_efficiency !== undefined && params.removal_efficiency < 0) {
            issues.push({ type: "unreasonable_value", description: `去除效率${params.removal_efficiency}%为负值`, severity: "critical", suggestion: "去除效率不能为负值" })
          }
        }
      }
    } catch (e) {
      issues.push({ type: "missing_parameter", description: `无法验证计算：${e instanceof Error ? e.message : String(e)}`, severity: "minor", suggestion: "请补充完整的核算参数" })
    }

    if (!source.unit.includes("t/a") && !source.unit.includes("吨/年") && !source.unit.includes("kg/a") && !source.unit.includes("kg/h")) {
      issues.push({ type: "unit_mismatch", description: `单位"${source.unit}"非标准排放单位`, severity: "minor", suggestion: "源强核算单位应统一为t/a（吨/年）" })
    }

    if (source.value > 1000000) {
      issues.push({ type: "unreasonable_value", description: `排放量${source.value}${source.unit}过大，请核实`, severity: "major", suggestion: "请核实产量和产污系数是否正确" })
    }

    if (source.value < 0.001 && source.unit.includes("t/a")) {
      issues.push({ type: "unreasonable_value", description: `排放量${source.value}${source.unit}过小，可能遗漏主要排放源`, severity: "minor", suggestion: "请检查是否遗漏了主要排放工序" })
    }

    const confidence = issues.length === 0 ? 0.95 : issues.some(i => i.severity === "critical") ? 0.5 : issues.some(i => i.severity === "major") ? 0.7 : 0.85

    return {
      pollutant: source.pollutant,
      reportedValue: source.value,
      reportedUnit: source.unit,
      calculatedValue,
      calculatedUnit: "t/a",
      deviation: calculatedValue > 0 ? Math.abs(source.value - calculatedValue) / calculatedValue * 100 : 0,
      method: source.method,
      recommendedMethod,
      parameters: this.parseParameters(source.parameters, source.pollutant),
      issues,
      confidence
    }
  }

  private parseParameters(params: Record<string, string>, pollutant: string): Record<string, number> {
    const result: Record<string, number> = {}
    for (const [key, value] of Object.entries(params)) {
      const num = parseFloat(value.replace(/[^\d.]/g, ""))
      if (!isNaN(num)) result[this.normalizeParamName(key)] = num
    }
    return result
  }

  private normalizeParamName(name: string): string {
    const mapping: Record<string, string> = {
      "产量": "production", "product_output": "production",
      "原辅料": "input_material", "原料": "input_material",
      "去除效率": "removal_efficiency", "处理效率": "removal_efficiency",
      "产污系数": "emission_factor", "排污系数": "emission_factor",
      "排放浓度": "concentration", "流量": "flow_rate", "运行时间": "operation_hours"
    }
    return mapping[name] || name
  }

  private getRecommendedMethod(pollutant: string, industryCode: string): string {
    return this.calcEngine.getRecommendedMethod(pollutant, industryCode)[0] || "物料衡算法"
  }

  private generateSummary(score: number, total: number, correct: number, suspicious: number, errors: number): string {
    if (score >= 90) return `源强核算总体良好（${score}分），${total}项污染物中${correct}项计算正确，${suspicious}项需复核，${errors}项存在错误。`
    else if (score >= 70) return `源强核算存在部分问题（${score}分），${total}项污染物中${correct}项计算正确，${suspicious}项需复核，${errors}项存在错误。建议重点复核偏差较大的项目。`
    else return `源强核算存在严重问题（${score}分），${total}项污染物中${errors}项存在计算错误，${suspicious}项需复核。建议重新核算全部源强数据。`
  }
}

export default SourceAnalysisTool
