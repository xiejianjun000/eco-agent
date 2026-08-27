// src/core/enhanced-rules.ts
// 增强版国家通用审查规则集
// 整合 industry-db, standards-api, hw-code-db, calc-engine

import { ReviewRule, ParsedDocument, ReviewContext, RuleResult } from "../types"
import { IndustryDB } from "./industry-db"
import { StandardsAPI } from "./standards-api"
import { HazardousWasteDB } from "./hw-code-db"
import { CalculationEngine } from "./calc-engine"

// 初始化数据库和引擎
const industryDB = new IndustryDB()
const standardsAPI = new StandardsAPI()
const hwDB = new HazardousWasteDB()
const calcEngine = new CalculationEngine()

// ═══════════════════════════════════════════════════════════════════════════
// 辅助函数
// ═══════════════════════════════════════════════════════════════════════════

const YANGTZE_PROVINCES = new Set([
  "zhejiang", "jiangsu", "anhui", "jiangxi", "hubei", "hunan",
  "sichuan", "yunnan", "guizhou", "chongqing", "shanghai"
])

function extractProjectCategory(doc: ParsedDocument): string {
  const match = doc.text.match(/行业类别[：:]\s*([A-Z]\d{2,4})/)
  return match?.[1] || ""
}

function extractStandards(doc: ParsedDocument): Array<{ code: string; year?: number; lineRange?: string }> {
  const standards: Array<{ code: string; year?: number; lineRange?: string }> = []
  const pattern = /(GB\s*\d{4,5}[-–]\d{4}|HJ\s*\d{2,4}[-–]\d{4}|DB\d{2}\/\s*\d{3,4}[-–]\d{4})/g
  let match
  while ((match = pattern.exec(doc.text)) !== null) {
    const parts = match[1].replace(/\s/g, "").split(/[-–]/)
    standards.push({
      code: match[1].replace(/\s/g, ""),
      year: parts[1] ? parseInt(parts[1]) : undefined,
      lineRange: `${match.index}-${match.index + match[0].length}`
    })
  }
  return standards
}

function extractMajorChanges(doc: ParsedDocument): Array<{ isMajor: boolean; desc: string }> {
  const changes: Array<{ isMajor: boolean; desc: string }> = []
  const changeSection = doc.sections.changes?.text || ""
  const majorKeywords = ["性质变化", "规模扩大", "地点变更", "生产工艺变化", "防治措施变化", "产品方案变化", "原料变化"]
  majorKeywords.forEach(kw => {
    if (changeSection.includes(kw)) {
      changes.push({
        isMajor: !changeSection.includes("非重大") && !changeSection.includes("不属于"),
        desc: kw
      })
    }
  })
  return changes
}

function checkNegativeList(doc: ParsedDocument): string[] {
  const violations: string[] = []
  const forbidden = ["自然保护区核心", "风景名胜区核心", "饮用水水源一级保护区", "水产种质资源保护区核心区", "国家湿地公园核心"]
  forbidden.forEach(f => {
    if (doc.text.includes(f) && !doc.text.includes("符合准入")) violations.push(f)
  })
  return violations
}

// ═══════════════════════════════════════════════════════════════════════════
// 20条增强版国家通用审查规则
// ═══════════════════════════════════════════════════════════════════════════

export const EnhancedNationalRules: ReviewRule[] = [

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 1: 生态环境法典引用合规
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-LAW-001",
    category: "compliance",
    severity: "critical",
    name: "生态环境法典引用合规",
    description: "2026年3月12日后编制的环评报告是否引用《中华人民共和国生态环境法典》",
    basis: ["中华人民共和国生态环境法典（2026年3月12日，第十四届全国人大第四次会议通过）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const effectiveDate = new Date("2026-03-12")
      const reportDate = doc.date ? new Date(doc.date) : new Date()
      const hasCited = doc.citations?.some((c: string) => c.includes("生态环境法典") || c.includes("法典")) || doc.text.includes("生态环境法典")

      if (reportDate < effectiveDate) {
        return { passed: true, detail: `报告编制日期${doc.date || "未标注"}在法典生效前（2026-03-12），可不引用`, location: doc.sections.legalBasis?.lineRange || "封面/前言" }
      }
      return { passed: hasCited, detail: hasCited ? "已引用《生态环境法典》" : "法典已于2026年3月12日生效，报告未引用《生态环境法典》", location: doc.sections.legalBasis?.lineRange || "全文" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 2: 环评分类管理名录判定（增强版 - 整合行业数据库）
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-REG-001",
    category: "compliance",
    severity: "critical",
    name: "环评分类管理名录判定",
    description: "项目类别判定是否正确，报告书/报告表选择是否符合《建设项目环境影响评价分类管理名录（2021年版）》",
    basis: ["建设项目环境影响评价分类管理名录（2021年版，生态环境部令2020年第16号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const category = extractProjectCategory(doc)
      const declaredType = ctx.reportType

      // 使用行业数据库精确匹配
      const industryInfo = industryDB.get(category)
      const shouldBeBook = industryInfo ? industryInfo.eiaType === "report_book" : false
      const shouldBeRegistration = industryInfo ? industryInfo.eiaType === "registration" : false

      if (shouldBeRegistration && declaredType !== "registration") {
        return { passed: false, detail: `行业${category}(${industryInfo?.name || "未知"})仅需填报登记表，但申报为${declaredType}，存在违规升格`, location: doc.sections.projectOverview?.lineRange || "建设项目基本情况" }
      }

      if (shouldBeBook && declaredType !== "report_book") {
        return { passed: false, detail: `行业${category}(${industryInfo?.name || "未知"})依法应编制报告书，但申报为${declaredType}，存在违规降格`, location: doc.sections.projectOverview?.lineRange || "建设项目基本情况" }
      }

      if (!shouldBeBook && !shouldBeRegistration && declaredType === "report_book") {
        return { passed: false, detail: `行业${category}(${industryInfo?.name || "未知"})依法应编制报告表，但申报为报告书，存在违规升格`, location: doc.sections.projectOverview?.lineRange || "建设项目基本情况" }
      }

      return { passed: true, detail: `行业${category}(${industryInfo?.name || "未识别"})，申报为${declaredType}，分类判定${industryInfo ? "正确" : "（行业信息未入库，建议人工复核）"}`, location: doc.sections.projectOverview?.lineRange || "建设项目基本情况" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 3: 排污许可管理类别判定（增强版 - 整合行业数据库）
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-REG-002",
    category: "compliance",
    severity: "critical",
    name: "排污许可管理类别判定",
    description: "是否按《固定污染源排污许可分类管理名录》正确判定排污许可管理类别",
    basis: ["固定污染源排污许可分类管理名录（生态环境部令2019年第11号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const permitCategory = doc.text.match(/排污许可管理类别[：:]\s*(重点管理|简化管理|登记管理)/)?.[1] || ""
      const hasPermitSection = doc.sections.permit || doc.text.includes("排污许可")
      const category = extractProjectCategory(doc)
      const industryInfo = industryDB.get(category)
      const expectedPermitType = industryInfo ? industryInfo.permitType : "simplified"

      if (!hasPermitSection && industryInfo && industryInfo.permitType === "key_management") {
        return { passed: false, detail: `${industryInfo.name}(${category})属于排污许可重点管理行业，但报告缺少排污许可管理类别判定`, location: doc.sections.overview?.lineRange || "建设项目概况" }
      }

      if (!permitCategory && hasPermitSection) {
        return { passed: false, detail: "报告提及排污许可但未明确管理类别（重点管理/简化管理/登记管理）", location: doc.sections.permit?.lineRange || "全文" }
      }

      if (permitCategory && industryInfo) {
        const expectedCN = expectedPermitType === "key_management" ? "重点管理" : expectedPermitType === "simplified" ? "简化管理" : "登记管理"
        if (permitCategory !== expectedCN) {
          return { passed: false, detail: `${industryInfo.name}(${category})排污许可管理类别应为${expectedCN}，但报告判定为${permitCategory}`, location: doc.sections.permit?.lineRange || "排污许可" }
        }
      }

      return { passed: true, detail: permitCategory ? `排污许可管理类别判定为：${permitCategory}${industryInfo ? `（符合${industryInfo.name}要求）` : ""}` : "不涉及排污许可管理或已论证", location: doc.sections.permit?.lineRange || "-" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 4: 公众参与程序合规
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-REG-003",
    category: "procedure",
    severity: "major",
    name: "公众参与程序合规",
    description: "公众参与是否符合《环境影响评价公众参与办法》（生态环境部令第4号）要求",
    basis: ["环境影响评价公众参与办法（生态环境部令第4号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const hasPublicSection = doc.sections.publicParticipation
      const publicText = doc.sections.publicParticipation?.text || ""
      const datePattern = /(\d{4}年\d{1,2}月\d{1,2}日).*?(公示|公开|公告)/
      const hasDate = datePattern.test(publicText) || datePattern.test(doc.text)
      const hasPlatform = publicText.includes("网站") || publicText.includes("报纸") || publicText.includes("张贴") || doc.text.includes("网络平台")
      const durationMatch = publicText.match(/(\d+)\s*个工作日?/) || doc.text.match(/公示期.*?([1-9]\d?)\s*个工作日?/)
      const duration = durationMatch ? parseInt(durationMatch[1]) : 0
      const isReportBook = ctx.reportType === "report_book"

      if (!hasPublicSection && isReportBook) {
        return { passed: false, detail: "报告书依法必须编制公众参与专章，但报告缺少该章节", location: "目录/章节结构" }
      }

      if (isReportBook && duration > 0 && duration < 10) {
        return { passed: false, detail: `报告书公示期限为${duration}个工作日，少于法定10个工作日`, location: doc.sections.publicParticipation?.lineRange || "公众参与" }
      }

      if (!hasDate && isReportBook) {
        return { passed: false, detail: "公众参与章节未明确公示起止日期", location: doc.sections.publicParticipation?.lineRange || "公众参与" }
      }

      return { passed: true, detail: hasPublicSection ? `公众参与完整，公示${duration > 0 ? duration + "个工作日" : "（未明确天数）"}，平台：${hasPlatform ? "已说明" : "未明确"}` : "报告表无需公众参与专章或已简化说明", location: doc.sections.publicParticipation?.lineRange || "-" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 5: 编制单位及人员信用
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-REG-004",
    category: "procedure",
    severity: "major",
    name: "编制单位及人员信用",
    description: "环评编制单位及编制人员是否符合信用监管要求",
    basis: ["建设项目环境影响报告书（表）编制监督管理办法（生态环境部令2019年第9号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const hasUnit = doc.text.includes("编制单位") || doc.text.includes("环评单位")
      const hasPerson = doc.text.includes("编制人员") || doc.text.includes("环评工程师")
      const hasCredit = doc.text.includes("信用编号") || doc.text.includes("信用平台")
      const 挂靠迹象 = doc.text.includes("挂靠") || doc.text.includes("兼职") || (hasPerson && !hasUnit)

      if (!hasUnit || !hasPerson) {
        return { passed: false, detail: "报告未明确标注编制单位或编制人员信息", location: doc.sections.preparation?.lineRange || "封面/编制说明" }
      }

      if (!hasCredit) {
        return { passed: false, detail: "编制单位/人员未标注信用平台编号，不符合信用监管要求", location: doc.sections.preparation?.lineRange || "封面/编制说明" }
      }

      return { passed: !挂靠迹象, detail: 挂靠迹象 ? "发现挂靠迹象，需核实编制人员与编制单位劳动关系" : `编制单位及${hasPerson ? "编制人员" : "人员"}信息完整，信用编号已标注`, location: doc.sections.preparation?.lineRange || "封面" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 6: 新污染物清单管控（增强版 - 整合行业数据库）
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-REG-005",
    category: "compliance",
    severity: "critical",
    name: "重点管控新污染物清单",
    description: "是否涉及《重点管控新污染物清单（2023年版）》物质并开展专项分析",
    basis: ["重点管控新污染物清单（2023年版，生态环境部令第29号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const newPollutants = ["PFOS", "PFOA", "十溴二苯醚", "短链氯化石蜡", "六氯丁二烯", "五氯苯酚", "全氟辛酸", "全氟辛烷磺酸", "得克隆", "氯丹"]
      const found = newPollutants.filter(p => doc.text.includes(p) || doc.text.includes(p.toLowerCase()))
      const hasAssessment = doc.text.includes("新污染物") || doc.text.includes("POPs") || doc.text.includes("持久性有机污染物")

      // 检查行业是否属于新污染物重点行业
      const category = extractProjectCategory(doc)
      const industryInfo = industryDB.get(category)
      const isKeyIndustry = industryInfo ? industryInfo.isNewPollutantIndustry : false

      if (found.length > 0 && !hasAssessment) {
        return { passed: false, detail: `报告涉及重点管控新污染物：${found.join("、")}，但未开展新污染物专项分析`, location: doc.sections.pollutantAnalysis?.lineRange || "工程分析/污染源分析" }
      }

      if (isKeyIndustry && !hasAssessment) {
        return { passed: false, detail: `${industryInfo?.name || category}属于新污染物重点管控行业，但未按环环评〔2025〕28号要求开展新污染物源强核算与排放预测`, location: doc.sections.pollutantAnalysis?.lineRange || "工程分析" }
      }

      return { passed: true, detail: found.length > 0 ? `发现新污染物${found.join("、")}，${hasAssessment ? "已开展专项分析" : "（已评估或不在清单内）"}` : (isKeyIndustry ? `${industryInfo?.name}属于新污染物重点行业，${hasAssessment ? "已开展专项分析" : "未明确是否涉及新污染物"}` : "不涉及重点管控新污染物清单物质"), location: doc.sections.pollutantAnalysis?.lineRange || "-" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 7: 危废代码准确性（增强版 - 整合危废数据库）
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-REG-006",
    category: "standard",
    severity: "major",
    name: "危险废物代码准确性",
    description: "危险废物代码是否与《国家危险废物名录（2025年版）》一致",
    basis: ["国家危险废物名录（2025年版，生态环境部令等五部门2025年第36号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const wastes = doc.tables?.hazardousWaste || []

      if (wastes.length === 0) {
        const hasHazardous = doc.text.includes("危险废物") || doc.text.includes("危废")
        return { passed: !hasHazardous, detail: hasHazardous ? "报告提及危险废物但未在附表中列出明细" : "不产生危险废物", location: doc.sections.waste?.lineRange || "-" }
      }

      const invalidCodes = wastes.filter((w: any) => !hwDB.isValid(w.code))
      const formatErrors = wastes.filter((w: any) => {
        const validation = hwDB.validateFormat(w.code)
        return !validation.valid
      })

      // 检查危废与行业匹配性
      const category = extractProjectCategory(doc)
      const industryInfo = industryDB.get(category)
      const mismatched = wastes.filter((w: any) => {
        const hwInfo = hwDB.get(w.code)
        if (!hwInfo || !industryInfo) return false
        // 简化匹配：检查行业大类是否匹配
        return !hwInfo.examples.some((e: string) => industryInfo.name.includes(e) || e.includes(industryInfo.name))
      })

      const totalIssues = invalidCodes.length + formatErrors.length + mismatched.length

      return { passed: totalIssues === 0, detail: totalIssues > 0 ? `发现${invalidCodes.length}处无效代码、${formatErrors.length}处格式错误、${mismatched.length}处行业不匹配，需核对2025年版名录` : `危险废物代码共${wastes.length}项，均符合2025年版名录${industryInfo ? `（与${industryInfo.name}行业匹配）` : ""}`, location: invalidCodes.map((w: any) => w.lineRange).join("; ") || "附表/危废清单" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 8: 排污许可管理办法合规
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-REG-007",
    category: "compliance",
    severity: "major",
    name: "排污许可管理办法合规",
    description: "排污许可申请是否符合《排污许可管理办法》要求",
    basis: ["排污许可管理办法（生态环境部令第32号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const isPermitReview = ctx.reviewType === "permit"
      if (!isPermitReview) return { passed: true, detail: "当前为环评审查模式，不检查排污许可申请内容", location: "-" }

      const hasBasicInfo = doc.text.includes("排污单位名称") && doc.text.includes("统一社会信用代码")
      const hasOutlets = doc.text.includes("排放口") || doc.text.includes("排放口编号")
      const hasMonitoring = doc.text.includes("自行监测") || doc.text.includes("监测方案")
      const missing: string[] = []
      if (!hasBasicInfo) missing.push("基本信息")
      if (!hasOutlets) missing.push("排放口信息")
      if (!hasMonitoring) missing.push("自行监测方案")

      return { passed: missing.length === 0, detail: missing.length > 0 ? `排污许可申请缺少：${missing.join("、")}` : "排污许可申请内容完整，符合管理办法要求", location: doc.sections.permitApplication?.lineRange || "全文" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 9: 入河排污口合规
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-REG-008",
    category: "compliance",
    severity: "major",
    name: "入河排污口设置合规",
    description: "涉及入河排污口的项目是否符合《入河排污口监督管理办法》",
    basis: ["入河排污口监督管理办法（生态环境部令2024年第35号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const hasRiverOutlet = doc.text.includes("入河排污口") || doc.text.includes("入河排放口")
      const hasApproval = doc.text.includes("入河排污口设置") && (doc.text.includes("同意") || doc.text.includes("批复") || doc.text.includes("审批"))

      if (hasRiverOutlet && !hasApproval) {
        return { passed: false, detail: "项目设置入河排污口，但未提供入河排污口设置审批文件或论证", location: doc.sections.waterEnvironment?.lineRange || "水环境影响评价" }
      }

      return { passed: true, detail: hasRiverOutlet ? "已设置入河排污口且已论证/审批" : "不涉及入河排污口", location: doc.sections.waterEnvironment?.lineRange || "-" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 10: 长江经济带负面清单
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-DOC-001",
    category: "compliance",
    severity: "critical",
    name: "长江经济带负面清单",
    description: "是否违反《长江经济带发展负面清单指南（试行，2022年版）》",
    basis: ["长江经济带发展负面清单指南（试行，2022年版，长江办〔2022〕7号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const province = ctx.province || ""
      const inYangtze = YANGTZE_PROVINCES.has(province)

      if (!inYangtze) {
        return { passed: true, detail: `${province || "未指定省份"}不属于长江经济带覆盖范围`, location: "-" }
      }

      const violations = checkNegativeList(doc)
      const hasAnalysis = doc.text.includes("负面清单") || doc.text.includes("长江办〔2022〕7号")

      if (violations.length > 0) {
        return { passed: false, detail: `违反长江经济带负面清单：${violations.join("、")}。项目不得建设`, location: doc.sections.location?.lineRange || "选址/选线" }
      }

      if (!hasAnalysis) {
        return { passed: false, detail: "项目位于长江经济带，但未论证负面清单符合性", location: doc.sections.location?.lineRange || "选址/选线" }
      }

      return { passed: true, detail: "符合长江经济带发展负面清单要求", location: doc.sections.location?.lineRange || "-" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 11: 产业园区规划环评衔接
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-DOC-002",
    category: "compliance",
    severity: "major",
    name: "产业园区规划环评衔接",
    description: "位于产业园区的项目是否满足规划环评要求",
    basis: ["关于进一步加强产业园区规划环境影响评价工作的意见（环环评〔2020〕65号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const inPark = doc.text.includes("园区") || doc.text.includes("开发区") || doc.text.includes("高新区") || doc.text.includes("经开区")
      const hasPlanEIA = doc.text.includes("规划环评") || doc.text.includes("规划环境影响评价")
      const hasConformance = doc.text.includes("符合") && doc.text.includes("规划")

      if (!inPark) return { passed: true, detail: "项目不位于产业园区，无需规划环评衔接论证", location: "-" }
      if (!hasPlanEIA) return { passed: false, detail: "项目位于产业园区，但未论证与园区规划环评的符合性", location: doc.sections.planning?.lineRange || "选址/规划符合性" }
      return { passed: hasConformance, detail: hasConformance ? "已论证与园区规划环评的符合性" : "提及规划环评但未明确符合性结论", location: doc.sections.planning?.lineRange || "选址/规划符合性" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 12: 建设项目重大变动
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-DOC-003",
    category: "compliance",
    severity: "critical",
    name: "建设项目重大变动",
    description: "项目是否存在重大变动未重新报批",
    basis: ["污染影响类建设项目重大变动清单（试行，环办环评函〔2020〕688号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const changes = extractMajorChanges(doc)
      const majorChanges = changes.filter(c => c.isMajor)

      if (majorChanges.length > 0) {
        return { passed: false, detail: `存在${majorChanges.length}项重大变动（${majorChanges.map(c => c.desc).join("、")}），需重新报批环评文件`, location: doc.sections.changes?.lineRange || "项目变动情况" }
      }

      if (changes.length > 0) {
        return { passed: true, detail: `存在${changes.length}项变动，但均不属于重大变动，可纳入竣工环保验收管理`, location: doc.sections.changes?.lineRange || "项目变动情况" }
      }

      return { passed: true, detail: "项目无变动或变动情况已说明", location: doc.sections.changes?.lineRange || "-" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 13: 生态保护红线管理
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-DOC-004",
    category: "compliance",
    severity: "critical",
    name: "生态保护红线管理",
    description: "是否涉及生态保护红线及符合性论证",
    basis: ["关于加强生态保护红线管理的通知（试行，自然资发〔2022〕142号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const mentionsRedLine = doc.text.includes("生态保护红线") || doc.text.includes("生态红线")
      const hasAnalysis = doc.sections.ecological?.text?.includes("红线") || doc.text.includes("不占用生态保护红线") || doc.text.includes("符合生态保护红线")
      const hasMap = doc.attachments?.some((a: any) => a.type === "image" && (a.name?.includes("红线") || a.name?.includes("生态")))

      if (!mentionsRedLine) {
        const inSensitive = doc.text.includes("自然保护区") || doc.text.includes("森林公园") || doc.text.includes("湿地公园") || doc.text.includes("风景名胜区")
        if (inSensitive) return { passed: false, detail: "项目位于生态敏感区附近，但未论证与生态保护红线的位置关系", location: doc.sections.ecological?.lineRange || "生态环境影响评价" }
        return { passed: true, detail: "项目不涉及生态保护红线", location: "-" }
      }

      if (!hasAnalysis) return { passed: false, detail: "报告提及生态保护红线，但未充分论证符合性（占用/避让/穿越）", location: doc.sections.ecological?.lineRange || "生态环境影响评价" }
      return { passed: true, detail: `已论证生态保护红线符合性${hasMap ? "，附位置关系图" : "（建议补充位置关系图）"}`, location: doc.sections.ecological?.lineRange || "生态环境影响评价" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 14: 重点行业环评审批原则（增强版 - 整合行业数据库）
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-DOC-005",
    category: "compliance",
    severity: "major",
    name: "重点行业环评审批原则",
    description: "钢铁/焦化、现代煤化工、石化、火电项目是否符合审批原则",
    basis: ["钢铁/焦化、现代煤化工、石化、火电四个行业环评文件审批原则（环办环评〔2022〕31号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const category = extractProjectCategory(doc)
      const industryInfo = industryDB.get(category)

      if (!industryInfo || !industryInfo.isKeyIndustry) {
        return { passed: true, detail: `${industryInfo?.name || category || "未识别行业"}不属于重点监管行业`, location: "-" }
      }

      const hasPrinciples = doc.text.includes("审批原则") || doc.text.includes("环办环评〔2022〕31号") || doc.text.includes("超低排放") || doc.text.includes("产能置换")
      const hasSpecialReq = industryInfo.specialRequirements.some(r => doc.text.includes(r))

      if (!hasPrinciples && !hasSpecialReq) {
        return { passed: false, detail: `${industryInfo.name}(${category})属于重点监管行业，未按环办环评〔2022〕31号审批原则进行专项论证（${industryInfo.specialRequirements.join("、")}）`, location: doc.sections.overview?.lineRange || "建设项目概况" }
      }

      return { passed: true, detail: `${industryInfo.name}已按审批原则论证${hasSpecialReq ? "（满足特殊要求）" : ""}`, location: doc.sections.overview?.lineRange || "-" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 15: 2024年环评改革要求
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-DOC-006",
    category: "compliance",
    severity: "major",
    name: "环评深化改革要求",
    description: "是否符合《关于进一步深化环境影响评价改革的通知》要求",
    basis: ["关于进一步深化环境影响评价改革的通知（环环评〔2024〕65号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const reportDate = doc.date ? new Date(doc.date) : new Date()
      const reformDate = new Date("2024-09-14")
      if (reportDate < reformDate) return { passed: true, detail: `报告编制日期${doc.date || "未标注"}在改革文件发布前`, location: "-" }
      const hasReform = doc.text.includes("环评改革") || doc.text.includes("环环评〔2024〕65号") || doc.text.includes("优化环评") || doc.text.includes("打捆环评")
      return { passed: true, detail: hasReform ? "已响应2024年环评深化改革要求" : "建议关注环环评〔2024〕65号深化改革要求（优化环评分类、打捆审批等）", location: "全文" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 16: 全面实行排污许可制
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-DOC-007",
    category: "compliance",
    severity: "major",
    name: "全面实行排污许可制衔接",
    description: "是否符合《全面实行排污许可制实施方案》要求",
    basis: ["全面实行排污许可制实施方案（环环评〔2024〕79号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const hasPermit = doc.text.includes("排污许可") || doc.text.includes("排污许可证")
      const hasLinkage = doc.text.includes("环评与排污许可") || doc.text.includes("衔接") || doc.text.includes("证后管理")
      if (!hasPermit) return { passed: false, detail: "报告未论证排污许可制衔接，不符合全面实行排污许可制要求", location: doc.sections.permit?.lineRange || "环境管理" }
      return { passed: true, detail: hasLinkage ? "已论证环评与排污许可衔接及证后管理要求" : "已提及排污许可，建议完善与排污许可制的衔接论证", location: doc.sections.permit?.lineRange || "环境管理" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 17: 涉新污染物建设项目环评（增强版 - 整合行业数据库）
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-DOC-008",
    category: "compliance",
    severity: "major",
    name: "涉新污染物建设项目环评",
    description: "重点行业涉新污染物项目是否符合专项环评要求",
    basis: ["关于加强重点行业涉新污染物建设项目环境影响评价工作的意见（环环评〔2025〕28号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const category = extractProjectCategory(doc)
      const industryInfo = industryDB.get(category)
      const isKeyIndustry = industryInfo ? industryInfo.isNewPollutantIndustry : false

      if (!isKeyIndustry) return { passed: true, detail: `${industryInfo?.name || category || "未识别行业"}不属于新污染物重点管控行业`, location: "-" }

      const hasNewPollutantEIA = doc.text.includes("新污染物") && (doc.text.includes("源强核算") || doc.text.includes("排放预测"))
      const hasSubstitute = doc.text.includes("替代") || doc.text.includes("绿色替代")

      if (!hasNewPollutantEIA) {
        return { passed: false, detail: `${industryInfo?.name}(${category})属于新污染物重点行业，但未按环环评〔2025〕28号要求开展新污染物源强核算与排放预测`, location: doc.sections.pollutantAnalysis?.lineRange || "工程分析" }
      }

      return { passed: true, detail: `已开展新污染物环评专项分析${hasSubstitute ? "，并提出替代方案" : "（建议补充绿色替代方案）"}`, location: doc.sections.pollutantAnalysis?.lineRange || "-" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 18: 排污许可证质量提升
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-DOC-009",
    category: "compliance",
    severity: "major",
    name: "排污许可证质量提升工程",
    description: "是否符合《排污许可证质量提升工程方案》要求",
    basis: ["排污许可证质量提升工程方案（环办环评函〔2025〕332号）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const isPermit = ctx.reviewType === "permit"
      if (!isPermit) return { passed: true, detail: "当前为环评审查模式", location: "-" }
      const reportDate = doc.date ? new Date(doc.date) : new Date()
      const schemeDate = new Date("2025-09-08")
      if (reportDate < schemeDate) return { passed: true, detail: "申请日期在质量提升工程方案发布前", location: "-" }
      const hasQuality = doc.text.includes("质量") || doc.text.includes("准确性") || doc.text.includes("完整性")
      return { passed: true, detail: hasQuality ? "已关注排污许可证质量要求" : "建议按环办环评函〔2025〕332号要求提升许可证填报质量", location: "全文" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 19: 源强核算方法规范性（增强版 - 整合核算引擎）
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-CALC-001",
    category: "calculation",
    severity: "major",
    name: "污染物源强核算方法",
    description: "污染物源强核算方法是否符合《污染源源强核算技术指南》要求",
    basis: ["污染源源强核算技术指南（HJ 884-2018）"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const calcSection = doc.sections.sourceCalculation?.text || doc.text
      const methods = doc.tables?.sourceCalculation || []

      if (methods.length === 0) {
        const methodMatches = calcSection.match(/采用[了]?(\S+法)/g) || []
        if (methodMatches.length === 0) {
          return { passed: false, detail: "未识别到污染物源强核算方法说明", location: doc.sections.sourceCalculation?.lineRange || "工程分析/源强核算" }
        }
      }

      const allMethods = methods.length > 0 ? methods.map((m: any) => m.method) : (calcSection.match(/采用[了]?(\S+法)/g) || []).map((m: string) => m.replace(/采用[了]?/, ""))

      // 使用核算引擎验证
      const invalid = allMethods.filter((m: string) => {
        const result = calcEngine.validateMethod(m)
        return !result.valid
      })

      // 检查是否有推荐方法未使用
      const category = extractProjectCategory(doc)
      const industryInfo = industryDB.get(category)
      const recommended = industryInfo ? calcEngine.getRecommendedMethod("VOCs", category) : ["物料衡算法", "类比法", "实测法"]
      const usedRecommended = allMethods.filter((m: string) => recommended.some(r => m.includes(r) || r.includes(m)))

      if (invalid.length > 0) {
        return { passed: false, detail: `发现非标准核算方法：${invalid.join("、")}。应采用${recommended.join("、")}等标准方法`, location: doc.sections.sourceCalculation?.lineRange || "工程分析/源强核算" }
      }

      return { passed: true, detail: `源强核算方法：${allMethods.join("、")}，符合HJ 884-2018要求${usedRecommended.length > 0 ? `（使用了推荐方法：${usedRecommended.join("、")}）` : `（推荐方法：${recommended.join("、")}）`}`, location: doc.sections.sourceCalculation?.lineRange || "-" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 规则 20: 排放标准现行有效性（增强版 - 整合标准API）
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-STD-001",
    category: "standard",
    severity: "major",
    name: "排放标准现行有效性",
    description: "引用的排放标准是否为现行有效版本",
    basis: ["《生态环境标准管理办法》"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const standards = extractStandards(doc)

      if (standards.length === 0) {
        return { passed: false, detail: "未识别到引用的排放标准", location: doc.sections.standards?.lineRange || "评价标准" }
      }

      // 使用标准API批量校验
      const expired: Array<{ code: string; replacement?: string }> = []
      const suspicious: Array<{ code: string; year?: number }> = []

      standards.forEach(s => {
        if (standardsAPI.isExpired(s.code)) {
          expired.push({ code: s.code, replacement: standardsAPI.getSupersededBy(s.code) })
        } else if (s.year && s.year < 2015 && !standardsAPI.isActive(s.code)) {
          suspicious.push({ code: s.code, year: s.year })
        }
      })

      // 检查行业适用标准
      const category = extractProjectCategory(doc)
      const industryInfo = industryDB.get(category)
      const missingIndustryStandards = industryInfo ? industryInfo.applicableStandards.filter(s => !standards.some(st => st.code.includes(s.split("-")[0]))) : []

      if (expired.length > 0) {
        return { passed: false, detail: `引用已废止/过期标准${expired.length}项：${expired.map(e => `${e.code}${e.replacement ? `（已被${e.replacement}替代）` : ""}`).join("、")}`, location: expired.map(e => standards.find(s => s.code === e.code)?.lineRange).filter(Boolean).join("; ") || "评价标准" }
      }

      return { passed: true, detail: `共引用${standards.length}项标准${suspicious.length > 0 ? `，其中${suspicious.length}项年份较早建议核对现行有效性` : "，均为现行有效"}${missingIndustryStandards.length > 0 ? `；建议补充行业标准：${missingIndustryStandards.join("、")}` : ""}`, location: doc.sections.standards?.lineRange || "-" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 新增规则 21: 行业特征污染物完整性（增强版）
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-ENH-001",
    category: "compliance",
    severity: "major",
    name: "行业特征污染物完整性",
    description: "是否对行业特征污染物进行了充分分析",
    basis: ["HJ 2.1-2016 建设项目环境影响评价技术导则 总纲"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const category = extractProjectCategory(doc)
      const industryInfo = industryDB.get(category)

      if (!industryInfo) {
        return { passed: true, detail: "行业信息未入库，无法自动检查特征污染物", location: "-" }
      }

      const analyzedPollutants = industryInfo.keyPollutants.filter(p => doc.text.includes(p))
      const missing = industryInfo.keyPollutants.filter(p => !doc.text.includes(p))

      if (missing.length > 0) {
        return { passed: false, detail: `${industryInfo.name}(${category})特征污染物中缺少分析：${missing.join("、")}（已分析：${analyzedPollutants.join("、")}）`, location: doc.sections.pollutantAnalysis?.lineRange || "工程分析" }
      }

      return { passed: true, detail: `${industryInfo.name}全部${industryInfo.keyPollutants.length}项特征污染物均已分析：${analyzedPollutants.join("、")}`, location: doc.sections.pollutantAnalysis?.lineRange || "-" }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // 新增规则 22: 两高项目联合评估（增强版 - 整合行业数据库）
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: "NAT-ENH-002",
    category: "compliance",
    severity: "critical",
    name: "两高项目联合评估",
    description: "两高项目是否经过联合评估论证",
    basis: ["浙江省'两高'项目联合评估论证工作机制（试行，浙发改能源〔2025〕135号）", "国家层面两高项目管控要求"],
    check: (doc: ParsedDocument, ctx: ReviewContext): RuleResult => {
      const category = extractProjectCategory(doc)
      const industryInfo = industryDB.get(category)

      if (!industryInfo || !industryInfo.isTwoHigh) {
        return { passed: true, detail: `${industryInfo?.name || category || "未识别行业"}不属于两高项目管控范围`, location: "-" }
      }

      const hasAssessment = doc.text.includes("两高") && doc.text.includes("评估")
      const hasEnergy = doc.text.includes("能耗") || doc.text.includes("煤耗") || doc.text.includes("碳排放")
      const hasCapacity = doc.text.includes("产能置换") || doc.text.includes("产能指标")

      if (!hasAssessment) {
        return { passed: false, detail: `${industryInfo.name}(${category})属于两高项目，缺少联合评估论证`, location: doc.sections.overview?.lineRange || "建设项目概况" }
      }

      if (!hasEnergy) {
        return { passed: false, detail: `${industryInfo.name}属于两高项目，但未开展能耗/碳排放专项分析`, location: doc.sections.energy?.lineRange || "能源消耗" }
      }

      return { passed: true, detail: `${industryInfo.name}已按两高项目要求开展联合评估${hasCapacity ? "，并完成产能置换论证" : "（建议补充产能置换论证）"}`, location: doc.sections.overview?.lineRange || "-" }
    }
  }
]

export default EnhancedNationalRules
