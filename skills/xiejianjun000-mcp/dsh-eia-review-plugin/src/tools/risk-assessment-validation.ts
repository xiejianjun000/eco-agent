// src/tools/risk-assessment-validation.ts
// 环境风险评价验证工具
// 依据 HJ 169-2018《建设项目环境风险评价技术导则》

import { IndustryDB } from "../core/industry-db"

export interface RiskAssessmentResult {
  assessmentLevel: string       // 评价等级
  riskType: string              // 风险类型
  identifiedHazards: Array<{
    substance: string
    CAS: string
    maxStorage: number
    threshold: number
    ratio: number        // 实际储量/临界量比值
    isMajor: boolean     // 是否构成重大危险源
  }>
  sourceTermAnalysis: Array<{
    scenario: string
    releaseAmount: number
    releaseDuration: number
    releaseRate: number
    calculationMethod: string
    issues: Array<{
      type: string
      description: string
      severity: "critical" | "major" | "minor"
      suggestion: string
    }>
  }>
  consequenceAnalysis: Array<{
    scenario: string
    endpoint: string
    affectedArea: number
    sensitiveTargets: string[]
    isAcceptable: boolean
    issues: Array<{
      type: string
      description: string
      severity: "critical" | "major" | "minor"
      suggestion: string
    }>
  }>
  preventionMeasures: Array<{
    category: string
    items: string[]
    missing: string[]
  }>
  emergencyPlan: {
    hasPlan: boolean
    hasDrill: boolean
    hasEquipment: boolean
    missingItems: string[]
  }
  issues: Array<{
    type: "risk_identification" | "source_term" | "consequence" | "prevention" | "emergency" | "level_error"
    description: string
    severity: "critical" | "major" | "minor"
    suggestion: string
  }>
  confidence: number
}

export interface RiskAssessmentReport {
  overallScore: number
  assessmentLevel: string
  hasMajorHazard: boolean
  totalScenarios: number
  validScenarios: number
  suspiciousScenarios: number
  errorScenarios: number
  details: RiskAssessmentResult[]
  summary: string
}

// 危险物质临界量数据库（HJ 169-2018 附录B）
const HazardousSubstances: Record<string, {
  name: string
  CAS: string
  threshold: number  // 临界量，吨
  category: "toxic" | "flammable" | "explosive" | "corrosive"
  properties: string[]
}> = {
  "氨": { name: "氨", CAS: "7664-41-7", threshold: 5, category: "toxic", properties: ["有毒气体", "刺激性", "腐蚀性"] },
  "液氨": { name: "液氨", CAS: "7664-41-7", threshold: 5, category: "toxic", properties: ["有毒气体", "低温", "腐蚀性"] },
  "氯": { name: "氯", CAS: "7782-50-5", threshold: 1, category: "toxic", properties: ["剧毒气体", "强氧化性", "腐蚀性"] },
  "氯化氢": { name: "氯化氢", CAS: "7647-01-0", threshold: 2.5, category: "toxic", properties: ["有毒气体", "腐蚀性", "刺激性"] },
  "甲醛": { name: "甲醛", CAS: "50-00-0", threshold: 0.5, category: "toxic", properties: ["有毒", "致癌", "刺激性"] },
  "苯": { name: "苯", CAS: "71-43-2", threshold: 10, category: "flammable", properties: ["易燃", "有毒", "致癌"] },
  "甲苯": { name: "甲苯", CAS: "108-88-3", threshold: 10, category: "flammable", properties: ["易燃", "有毒", "刺激性"] },
  "二甲苯": { name: "二甲苯", CAS: "1330-20-7", threshold: 10, category: "flammable", properties: ["易燃", "有毒", "刺激性"] },
  "甲醇": { name: "甲醇", CAS: "67-56-1", threshold: 10, category: "flammable", properties: ["易燃", "有毒", "致盲"] },
  "乙醇": { name: "乙醇", CAS: "64-17-5", threshold: 500, category: "flammable", properties: ["易燃", "低毒"] },
  "汽油": { name: "汽油", CAS: "8006-61-9", threshold: 200, category: "flammable", properties: ["易燃", "易爆", "有毒"] },
  "柴油": { name: "柴油", CAS: "68334-30-5", threshold: 5000, category: "flammable", properties: ["可燃", "低毒"] },
  "天然气": { name: "天然气", CAS: "74-82-8", threshold: 50, category: "flammable", properties: ["易燃", "易爆", "窒息"] },
  "液化石油气": { name: "液化石油气", CAS: "68476-85-7", threshold: 50, category: "flammable", properties: ["易燃", "易爆", "窒息"] },
  "氢气": { name: "氢气", CAS: "1333-74-0", threshold: 5, category: "flammable", properties: ["极易燃", "易爆", "窒息"] },
  "硫化氢": { name: "硫化氢", CAS: "7783-06-4", threshold: 2.5, category: "toxic", properties: ["剧毒", "易燃", "恶臭"] },
  "一氧化碳": { name: "一氧化碳", CAS: "630-08-0", threshold: 7.5, category: "toxic", properties: ["剧毒", "易燃", "无味"] },
  "硫酸": { name: "硫酸", CAS: "7664-93-9", threshold: 10, category: "corrosive", properties: ["强腐蚀", "氧化性", "脱水性"] },
  "盐酸": { name: "盐酸", CAS: "7647-01-0", threshold: 7.5, category: "corrosive", properties: ["强腐蚀", "刺激性", "有毒"] },
  "硝酸": { name: "硝酸", CAS: "7697-37-2", threshold: 7.5, category: "corrosive", properties: ["强腐蚀", "强氧化", "易爆"] },
  "氢氧化钠": { name: "氢氧化钠", CAS: "1310-73-2", threshold: 50, category: "corrosive", properties: ["强腐蚀", "刺激性"] },
  "丙烯腈": { name: "丙烯腈", CAS: "107-13-1", threshold: 10, category: "toxic", properties: ["剧毒", "易燃", "致癌"] },
  "苯胺": { name: "苯胺", CAS: "62-53-3", threshold: 5, category: "toxic", properties: ["剧毒", "致癌", "血液毒"] },
  "硝基苯": { name: "硝基苯", CAS: "98-95-3", threshold: 10, category: "toxic", properties: ["剧毒", "致癌", "血液毒"] },
  "丙酮氰醇": { name: "丙酮氰醇", CAS: "75-86-5", threshold: 2.5, category: "toxic", properties: ["剧毒", "易燃", "分解产氰化氢"] },
  "氰化氢": { name: "氰化氢", CAS: "74-90-8", threshold: 1, category: "toxic", properties: ["剧毒", "易燃", "快速致死"] },
  "光气": { name: "光气", CAS: "75-44-5", threshold: 0.25, category: "toxic", properties: ["剧毒", "窒息性", "迟发毒性"] },
  "丙烯": { name: "丙烯", CAS: "115-07-1", threshold: 10, category: "flammable", properties: ["易燃", "易爆", "窒息"] },
  "乙烯": { name: "乙烯", CAS: "74-85-1", threshold: 50, category: "flammable", properties: ["易燃", "易爆", "窒息"] },
  "乙炔": { name: "乙炔", CAS: "74-86-2", threshold: 1, category: "flammable", properties: ["极易燃", "易爆", "不稳定"] },
  "环氧乙烷": { name: "环氧乙烷", CAS: "75-21-8", threshold: 7.5, category: "flammable", properties: ["易燃", "易爆", "致癌"] },
  "氯乙烯": { name: "氯乙烯", CAS: "75-01-4", threshold: 5, category: "flammable", properties: ["易燃", "易爆", "致癌"] }
}

// 工艺系统危险性评估标准
const ProcessRiskLevels: Record<string, {
  description: string
  score: number
  indicators: string[]
}> = {
  "极高": { description: "涉及光气、氰化氢等剧毒物质，或高压/高温/强放热反应", score: 10, indicators: ["剧毒物质", "高压>10MPa", "高温>500°C", "强放热反应"] },
  "高": { description: "涉及氨、氯、苯等危险物质，或中压/中温工艺", score: 7, indicators: ["有毒气体", "易燃液体", "中压2-10MPa", "中温200-500°C"] },
  "中": { description: "涉及一般化学品，或低压/常温工艺", score: 4, indicators: ["一般化学品", "低压<2MPa", "常温<200°C"] },
  "低": { description: "不涉及危险物质，常温常压操作", score: 1, indicators: ["无危险物质", "常温常压"] }
}

// 风险评价等级判定
function determineRiskLevel(hazardRatio: number, processRisk: string): string {
  const pScore = ProcessRiskLevels[processRisk]?.score || 1
  const total = hazardRatio * pScore

  if (total >= 100) return "一级（极高）"
  if (total >= 50) return "二级（高）"
  if (total >= 10) return "三级（中）"
  return "四级（低）"
}

export class RiskAssessmentValidationTool {
  private industryDB = new IndustryDB()

  /**
   * 验证环评报告中的环境风险评价内容
   */
  async validate(doc: any, industryCode: string): Promise<RiskAssessmentReport> {
    const results: RiskAssessmentResult[] = []

    // 1. 风险识别验证
    const riskIdentification = this.validateRiskIdentification(doc)
    results.push(riskIdentification)

    // 2. 源项分析验证
    const sourceTermAnalysis = this.validateSourceTermAnalysis(doc)
    results.push(sourceTermAnalysis)

    // 3. 后果分析验证
    const consequenceAnalysis = this.validateConsequenceAnalysis(doc)
    results.push(consequenceAnalysis)

    // 4. 风险防范措施验证
    const preventionMeasures = this.validatePreventionMeasures(doc)
    results.push(preventionMeasures)

    // 5. 应急预案验证
    const emergencyPlan = this.validateEmergencyPlan(doc)
    results.push(emergencyPlan)

    // 6. 计算总体评分
    const totalIssues = results.flatMap(r => r.issues)
    const critical = totalIssues.filter(i => i.severity === "critical").length
    const major = totalIssues.filter(i => i.severity === "major").length
    const minor = totalIssues.filter(i => i.severity === "minor").length

    const score = Math.max(0, 100 - critical * 20 - major * 10 - minor * 3)

    const hasMajorHazard = riskIdentification.identifiedHazards.some(h => h.isMajor)

    return {
      overallScore: score,
      assessmentLevel: riskIdentification.assessmentLevel,
      hasMajorHazard,
      totalScenarios: sourceTermAnalysis.sourceTermAnalysis.length,
      validScenarios: sourceTermAnalysis.sourceTermAnalysis.filter(s => s.issues.length === 0).length,
      suspiciousScenarios: sourceTermAnalysis.sourceTermAnalysis.filter(s => s.issues.some(i => i.severity === "major")).length,
      errorScenarios: sourceTermAnalysis.sourceTermAnalysis.filter(s => s.issues.some(i => i.severity === "critical")).length,
      details: results,
      summary: this.generateSummary(score, hasMajorHazard, critical, major, minor)
    }
  }

  /**
   * 验证风险识别
   */
  private validateRiskIdentification(doc: any): RiskAssessmentResult {
    const text = doc.text || ""
    const issues: RiskAssessmentResult["issues"] = []
    const identifiedHazards: RiskAssessmentResult["identifiedHazards"] = []

    // 检查是否有风险识别章节
    const hasRiskChapter = text.includes("风险识别") || text.includes("环境风险") || text.includes("危险物质")
    if (!hasRiskChapter) {
      issues.push({
        type: "risk_identification",
        description: "报告缺少环境风险评价专章或风险识别内容",
        severity: "critical",
        suggestion: "依据HJ 169-2018，应编制环境风险评价专章，包括风险识别、源项分析、后果计算、风险防范措施"
      })
    }

    // 识别危险物质
    for (const [name, info] of Object.entries(HazardousSubstances)) {
      if (text.includes(name)) {
        // 提取储量
        const storagePattern = new RegExp(`${name}.*?([\d.]+)\s*[吨t]")
        const storageMatch = text.match(storagePattern)
        const storage = storageMatch ? parseFloat(storageMatch[1]) : 0

        const ratio = storage > 0 ? storage / info.threshold : 0
        const isMajor = ratio >= 1

        identifiedHazards.push({
          substance: name,
          CAS: info.CAS,
          maxStorage: storage,
          threshold: info.threshold,
          ratio,
          isMajor
        })

        if (storage === 0) {
          issues.push({
            type: "risk_identification",
            description: `识别到危险物质"${name}"（CAS: ${info.CAS}），但未明确最大储存量`,
            severity: "major",
            suggestion: `应明确${name}的最大储存量，临界量为${info.threshold}吨`
          })
        } else if (isMajor) {
          issues.push({
            type: "risk_identification",
            description: `${name}最大储存量${storage}吨，超过临界量${info.threshold}吨（比值${ratio.toFixed(2)}），构成重大危险源`,
            severity: "major",
            suggestion: `应进行重大危险源登记，并提高风险评价等级`
          })
        }
      }
    }

    // 检查是否遗漏了常见危险物质（根据行业）
    const industryInfo = this.industryDB.get(industryCode)
    if (industryInfo) {
      const commonHazards = this.getCommonHazardsByIndustry(industryCode)
      for (const hazard of commonHazards) {
        if (!identifiedHazards.some(h => h.substance === hazard)) {
          issues.push({
            type: "risk_identification",
            description: `${industryInfo.name}行业通常涉及"${hazard}"，但报告中未识别该危险物质`,
            severity: "major",
            suggestion: `应核实是否使用${hazard}，如使用应补充风险识别`
          })
        }
      }
    }

    // 判定评价等级
    const maxRatio = identifiedHazards.length > 0 ? Math.max(...identifiedHazards.map(h => h.ratio)) : 0
    const processRisk = this.identifyProcessRisk(text)
    const assessmentLevel = determineRiskLevel(maxRatio, processRisk)

    // 检查评价等级是否合理
    const reportedLevel = this.extractReportedLevel(text)
    if (reportedLevel && reportedLevel !== assessmentLevel) {
      issues.push({
        type: "level_error",
        description: `报告判定风险评价等级为"${reportedLevel}"，但根据计算应为"${assessmentLevel}"（最大比值${maxRatio.toFixed(2)} × 工艺风险${processRisk}）`,
        severity: "critical",
        suggestion: `应重新核算风险评价等级，或提供等级调整的充分论证`
      })
    }

    const confidence = issues.length === 0 ? 0.95 : issues.some(i => i.severity === "critical") ? 0.5 : 0.75

    return {
      assessmentLevel,
      riskType: identifiedHazards.length > 0 ? identifiedHazards.map(h => h.substance).join("、") : "未识别",
      identifiedHazards,
      sourceTermAnalysis: [],
      consequenceAnalysis: [],
      preventionMeasures: [],
      emergencyPlan: { hasPlan: false, hasDrill: false, hasEquipment: false, missingItems: [] },
      issues,
      confidence
    }
  }

  /**
   * 验证源项分析
   */
  private validateSourceTermAnalysis(doc: any): RiskAssessmentResult {
    const text = doc.text || ""
    const issues: RiskAssessmentResult["issues"] = []
    const scenarios: RiskAssessmentResult["sourceTermAnalysis"] = []

    // 检查是否有源项分析
    const hasSourceTerm = text.includes("源项分析") || text.includes("泄漏量") || text.includes("释放量")
    if (!hasSourceTerm) {
      issues.push({
        type: "source_term",
        description: "报告缺少源项分析内容",
        severity: "critical",
        suggestion: "应进行源项分析，确定最大可信事故及泄漏/释放量"
      })
    }

    // 识别事故情景
    const scenarioPatterns = [
      { name: "储罐泄漏", pattern: /储罐.*?泄漏|储罐.*?破裂|储罐.*?破损/i },
      { name: "管道泄漏", pattern: /管道.*?泄漏|管道.*?破裂|管道.*?断裂/i },
      { name: "反应釜泄漏", pattern: /反应釜.*?泄漏|反应器.*?泄漏/i },
      { name: "火灾", pattern: /火灾|池火|喷射火|火球/i },
      { name: "爆炸", pattern: /爆炸|蒸气云爆炸|BLEVE|物理爆炸/i },
      { name: "有毒气体扩散", pattern: /有毒气体.*?扩散|毒气.*?扩散/i }
    ]

    for (const { name, pattern } of scenarioPatterns) {
      const match = text.match(pattern)
      if (match) {
        // 提取泄漏量
        const releasePattern = new RegExp(`${name}.*?([\d.]+)\s*[吨tkg千克]`)
        const releaseMatch = text.substring(Math.max(0, match.index - 200), match.index + 500).match(releasePattern)
        const releaseAmount = releaseMatch ? parseFloat(releaseMatch[1]) : 0

        // 提取泄漏时间
        const durationPattern = /(?:持续|泄漏).*?([\d.]+)\s*(分钟|min|小时|h)/
        const durationMatch = text.substring(Math.max(0, match.index - 200), match.index + 500).match(durationPattern)
        const duration = durationMatch ? parseFloat(durationMatch[1]) * (durationMatch[2].includes("小时") || durationMatch[2].includes("h") ? 60 : 1) : 0

        const scenarioIssues: RiskAssessmentResult["sourceTermAnalysis"][0]["issues"] = []

        if (releaseAmount === 0) {
          scenarioIssues.push({
            type: "missing_content",
            description: `${name}情景未给出泄漏/释放量`,
            severity: "major",
            suggestion: "应计算并给出泄漏量或释放量"
          })
        }

        if (duration === 0) {
          scenarioIssues.push({
            type: "missing_content",
            description: `${name}情景未给出泄漏持续时间`,
            severity: "major",
            suggestion: "应给出泄漏持续时间（分钟）"
          })
        }

        // 检查计算方法
        const methodSection = text.substring(Math.max(0, match.index - 300), match.index + 800)
        const hasCalculation = methodSection.includes("计算") || methodSection.includes("公式") || methodSection.includes("伯努利") || methodSection.includes("两相流")
        if (!hasCalculation && releaseAmount > 0) {
          scenarioIssues.push({
            type: "calculation_error",
            description: `${name}情景给出泄漏量${releaseAmount}但未说明计算方法`,
            severity: "major",
            suggestion: "应说明泄漏量计算方法（如伯努利方程、两相流模型等）"
          })
        }

        scenarios.push({
          scenario: name,
          releaseAmount,
          releaseDuration: duration,
          releaseRate: duration > 0 ? releaseAmount / duration : 0,
          calculationMethod: hasCalculation ? "已说明" : "未说明",
          issues: scenarioIssues
        })
      }
    }

    if (scenarios.length === 0) {
      issues.push({
        type: "source_term",
        description: "未识别到任何事故情景（储罐泄漏、管道泄漏、火灾、爆炸等）",
        severity: "critical",
        suggestion: "应至少分析最大可信事故情景，包括泄漏和火灾爆炸"
      })
    }

    const confidence = issues.length === 0 ? 0.9 : issues.some(i => i.severity === "critical") ? 0.5 : 0.7

    return {
      assessmentLevel: "",
      riskType: "",
      identifiedHazards: [],
      sourceTermAnalysis: scenarios,
      consequenceAnalysis: [],
      preventionMeasures: [],
      emergencyPlan: { hasPlan: false, hasDrill: false, hasEquipment: false, missingItems: [] },
      issues,
      confidence
    }
  }

  /**
   * 验证后果分析
   */
  private validateConsequenceAnalysis(doc: any): RiskAssessmentResult {
    const text = doc.text || ""
    const issues: RiskAssessmentResult["issues"] = []
    const consequences: RiskAssessmentResult["consequenceAnalysis"] = []

    // 检查是否有后果分析
    const hasConsequence = text.includes("后果分析") || text.includes("影响范围") || text.includes("浓度分布")
    if (!hasConsequence) {
      issues.push({
        type: "consequence",
        description: "报告缺少后果分析内容",
        severity: "critical",
        suggestion: "应进行后果分析，预测事故影响范围和程度"
      })
    }

    // 检查是否使用标准终点浓度
    const endpointPatterns = [
      { name: "AEGL-1", pattern: /AEGL-?1/i },
      { name: "AEGL-2", pattern: /AEGL-?2/i },
      { name: "ERPG-1", pattern: /ERPG-?1/i },
      { name: "ERPG-2", pattern: /ERPG-?2/i },
      { name: "IDLH", pattern: /IDLH/i },
      { name: "LC50", pattern: /LC50/i },
      { name: "毒性终点浓度", pattern: /毒性终点浓度|终点浓度/i }
    ]

    const usedEndpoints = endpointPatterns.filter(ep => ep.pattern.test(text)).map(ep => ep.name)
    if (usedEndpoints.length === 0) {
      issues.push({
        type: "consequence",
        description: "后果分析未使用标准终点浓度（如AEGL、ERPG、IDLH、毒性终点浓度）",
        severity: "major",
        suggestion: "应使用HJ 169-2018推荐的毒性终点浓度或AEGL/ERPG等标准值"
      })
    }

    // 检查敏感目标
    const sensitiveTargets = this.extractSensitiveTargets(text)
    if (sensitiveTargets.length === 0) {
      issues.push({
        type: "consequence",
        description: "未识别到受影响敏感目标（村庄、学校、医院等）",
        severity: "major",
        suggestion: "应识别并列出事故影响范围内的敏感目标"
      })
    }

    // 检查是否超标
    const exceedPattern = /超标|超过|大于|高于.*?标准|超过.*?限值/i
    if (!exceedPattern.test(text) && hasConsequence) {
      issues.push({
        type: "consequence",
        description: "后果分析未明确是否超标或影响是否可接受",
        severity: "major",
        suggestion: "应明确事故后果是否超过毒性终点浓度或影响是否可接受"
      })
    }

    const confidence = issues.length === 0 ? 0.9 : issues.some(i => i.severity === "critical") ? 0.5 : 0.7

    return {
      assessmentLevel: "",
      riskType: "",
      identifiedHazards: [],
      sourceTermAnalysis: [],
      consequenceAnalysis: consequences,
      preventionMeasures: [],
      emergencyPlan: { hasPlan: false, hasDrill: false, hasEquipment: false, missingItems: [] },
      issues,
      confidence
    }
  }

  /**
   * 验证风险防范措施
   */
  private validatePreventionMeasures(doc: any): RiskAssessmentResult {
    const text = doc.text || ""
    const issues: RiskAssessmentResult["issues"] = []

    // 标准风险防范措施清单
    const standardMeasures = {
      "工艺控制": ["DCS控制系统", "SIS安全仪表系统", "ESD紧急停车系统", "联锁保护", "报警系统"],
      "设备安全": ["设备定期检测", "压力容器登记", "安全阀", "爆破片", "阻火器", "静电接地"],
      "储运安全": ["围堰", "防火堤", "防渗", "泄漏检测", "气体检测报警", "视频监控"],
      "消防": ["消防水系统", "泡沫灭火系统", "灭火器", "消防通道", "消防水源"],
      "应急": ["应急池", "事故池", "切换阀", "收集沟", "应急物资"],
      "管理": ["操作规程", "巡检制度", "培训制度", "演练制度", "应急预案"]
    }

    const preventionMeasures: RiskAssessmentResult["preventionMeasures"] = []

    for (const [category, items] of Object.entries(standardMeasures)) {
      const found: string[] = []
      const missing: string[] = []

      for (const item of items) {
        if (text.includes(item)) {
          found.push(item)
        } else {
          missing.push(item)
        }
      }

      preventionMeasures.push({ category, items: found, missing })

      if (missing.length > 0 && found.length === 0) {
        issues.push({
          type: "prevention",
          description: `风险防范措施中缺少${category}相关内容（如${missing.slice(0, 3).join("、")}等）`,
          severity: missing.length > 3 ? "major" : "minor",
          suggestion: `应补充${category}措施，包括${missing.slice(0, 3).join("、")}`
        })
      }
    }

    const confidence = issues.length === 0 ? 0.9 : 0.7

    return {
      assessmentLevel: "",
      riskType: "",
      identifiedHazards: [],
      sourceTermAnalysis: [],
      consequenceAnalysis: [],
      preventionMeasures,
      emergencyPlan: { hasPlan: false, hasDrill: false, hasEquipment: false, missingItems: [] },
      issues,
      confidence
    }
  }

  /**
   * 验证应急预案
   */
  private validateEmergencyPlan(doc: any): RiskAssessmentResult {
    const text = doc.text || ""
    const issues: RiskAssessmentResult["issues"] = []

    const hasPlan = text.includes("应急预案") || text.includes("应急方案")
    const hasDrill = text.includes("演练") || text.includes("演习")
    const hasEquipment = text.includes("应急物资") || text.includes("应急装备") || text.includes("应急器材")

    const missingItems: string[] = []

    if (!hasPlan) {
      missingItems.push("应急预案")
      issues.push({
        type: "emergency",
        description: "报告未提及应急预案",
        severity: "major",
        suggestion: "应编制突发环境事件应急预案并报生态环境部门备案"
      })
    }

    if (!hasDrill) {
      missingItems.push("应急演练")
      issues.push({
        type: "emergency",
        description: "报告未提及应急演练计划",
        severity: "minor",
        suggestion: "应制定应急演练计划并定期演练"
      })
    }

    if (!hasEquipment) {
      missingItems.push("应急物资")
      issues.push({
        type: "emergency",
        description: "报告未提及应急物资/装备",
        severity: "major",
        suggestion: "应配备必要的应急物资和装备"
      })
    }

    const confidence = issues.length === 0 ? 0.9 : 0.7

    return {
      assessmentLevel: "",
      riskType: "",
      identifiedHazards: [],
      sourceTermAnalysis: [],
      consequenceAnalysis: [],
      preventionMeasures: [],
      emergencyPlan: { hasPlan, hasDrill, hasEquipment, missingItems },
      issues,
      confidence
    }
  }

  /**
   * 根据行业获取常见危险物质
   */
  private getCommonHazardsByIndustry(industryCode: string): string[] {
    const commonHazards: Record<string, string[]> = {
      "C2611": ["硫酸", "盐酸", "氯"],           // 无机酸
      "C2612": ["氨", "液氨", "氢氧化钠"],       // 无机碱
      "C2614": ["苯", "甲苯", "甲醇", "硫化氢"],  // 有机化学原料
      "C2631": ["氯", "苯", "甲醇", "硫化氢"],    // 农药
      "C2651": ["乙烯", "丙烯", "氯乙烯"],       // 合成树脂
      "C2710": ["甲醇", "丙酮", "乙酸乙酯"],     // 原料药
      "C3110": ["一氧化碳", "硫化氢", "氨"],      // 炼铁
      "D4411": ["氨", "液氨", "柴油", "天然气"],   // 火电
    }

    return commonHazards[industryCode] || []
  }

  /**
   * 识别工艺风险等级
   */
  private identifyProcessRisk(text: string): string {
    if (/光气|氰化氢|高压.*?10MPa|高温.*?500/.test(text)) return "极高"
    if (/氨.*?储罐|氯.*?钢瓶|苯.*?储罐|高压|高温/.test(text)) return "高"
    if (/化学品|反应釜|储罐/.test(text)) return "中"
    return "低"
  }

  /**
   * 提取报告中的评价等级
   */
  private extractReportedLevel(text: string): string | null {
    const match = text.match(/风险评价等级[：:]?\s*(一级|二级|三级|四级|极高|高|中|低)/)
    return match ? match[1] : null
  }

  /**
   * 提取敏感目标
   */
  private extractSensitiveTargets(text: string): string[] {
    const targets: string[] = []
    const patterns = [
      /([一-龥]{2,10}村)/g,
      /([一-龥]{2,10}小区)/g,
      /([一-龥]{2,10}学校)/g,
      /([一-龥]{2,10}医院)/g,
      /([一-龥]{2,10}幼儿园)/g,
      /([一-龥]{2,10}养老院)/g
    ]

    for (const pattern of patterns) {
      let match
      while ((match = pattern.exec(text)) !== null) {
        if (!targets.includes(match[1])) {
          targets.push(match[1])
        }
      }
    }

    return targets
  }

  /**
   * 生成摘要
   */
  private generateSummary(score: number, hasMajorHazard: boolean, critical: number, major: number, minor: number): string {
    let summary = `环境风险评价验证${score >= 80 ? "总体良好" : score >= 60 ? "存在部分问题" : "存在严重问题"}（${score}分）。`

    if (hasMajorHazard) {
      summary += `项目存在重大危险源，需特别关注。`
    }

    if (critical > 0) {
      summary += `发现${critical}项Critical问题，${major}项Major问题，${minor}项Minor问题。`
    } else if (major > 0) {
      summary += `发现${major}项Major问题，${minor}项Minor问题。`
    } else if (minor > 0) {
      summary += `发现${minor}项Minor问题。`
    }

    if (score < 60) {
      summary += `建议重新完善环境风险评价内容，重点补充风险识别、源项分析和风险防范措施。`
    }

    return summary
  }
}

export default RiskAssessmentValidationTool
