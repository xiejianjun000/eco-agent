// src/types.ts
// 核心类型定义

/** 解析后的文档结构 */
export interface ParsedDocument {
  /** 原始文本内容 */
  text: string
  /** 报告日期 */
  date?: string
  /** 章节映射 */
  sections: Record<string, SectionInfo | undefined>
  /** 提取的表格数据 */
  tables?: Record<string, any[]>
  /** 引用文献列表 */
  citations?: string[]
  /** 附件列表 */
  attachments?: Array<{ type: string; name?: string; path?: string }>
  /** 项目规模信息 */
  projectScale?: any
  /** 审批级别 */
  approvalLevel?: string
}

/** 章节信息 */
export interface SectionInfo {
  /** 章节标题 */
  title: string
  /** 章节文本内容 */
  text: string
  /** 行号范围 */
  lineRange: string
  /** 页码范围 */
  pageRange?: string
}

/** 审查上下文 */
export interface ReviewContext {
  /** 报告类型: report_book | report_table | registration */
  reportType: string
  /** 行业类别 */
  industry?: string
  /** 项目所在省份 */
  province?: string
  /** 审查类型: eia | permit */
  reviewType?: string
  /** 其他扩展参数 */
  [key: string]: any
}

/** 规则检查结果 */
export interface RuleResult {
  /** 是否通过 */
  passed: boolean
  /** 检查详情 */
  detail: string
  /** 问题位置 */
  location: string
  /** 建议修正措施 */
  suggestion?: string
  /** 相关数据 */
  data?: any
}

/** 审查规则定义 */
export interface ReviewRule {
  /** 规则唯一标识 */
  id: string
  /** 规则类别 */
  category: "compliance" | "consistency" | "calculation" | "standard" | "procedure"
  /** 严重程度 */
  severity: "critical" | "major" | "minor" | "info"
  /** 规则名称 */
  name: string
  /** 规则描述 */
  description: string
  /** 法规依据 */
  basis: string[]
  /** 检查函数 */
  check: (doc: ParsedDocument, ctx: ReviewContext) => RuleResult
}

/** 审查问题项 */
export interface ReviewIssue {
  id: string
  category: string
  severity: string
  name: string
  description: string
  detail: string
  location: string
  basis: string[]
  confidence: number
  level: "national" | "provincial"
  suggestion?: string
}

/** 审查结果 */
export interface ReviewOutput {
  pass: boolean
  score: number
  issues: ReviewIssue[]
  knowledgeRefs: string[]
}
