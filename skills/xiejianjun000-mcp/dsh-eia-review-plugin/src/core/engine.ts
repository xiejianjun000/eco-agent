// src/core/engine.ts
// 国家通用规则引擎执行器

import { NationalRules } from "./national-rules"
import {
  ParsedDocument,
  ReviewContext,
  ReviewIssue,
  RuleResult,
  ReviewOutput
} from "../types"

export class NationalRuleEngine {
  private rules = NationalRules

  /**
   * 执行国家通用规则审查
   * @param doc 解析后的文档
   * @param ctx 审查上下文
   * @returns 审查结果
   */
  async review(doc: ParsedDocument, ctx: ReviewContext): Promise<ReviewOutput> {
    const issues: ReviewIssue[] = []
    let criticalCount = 0
    let majorCount = 0
    let minorCount = 0

    for (const rule of this.rules) {
      try {
        const result: RuleResult = rule.check(doc, ctx)

        if (!result.passed) {
          const issue: ReviewIssue = {
            id: rule.id,
            category: rule.category,
            severity: rule.severity,
            name: rule.name,
            description: rule.description,
            detail: result.detail,
            location: result.location,
            basis: rule.basis,
            confidence: this.calculateConfidence(rule, result),
            level: "national",
            suggestion: result.suggestion
          }
          issues.push(issue)

          // 统计严重程度
          if (rule.severity === "critical") criticalCount++
          else if (rule.severity === "major") majorCount++
          else if (rule.severity === "minor") minorCount++
        }
      } catch (error) {
        console.error(`[NationalRuleEngine] Rule ${rule.id} execution failed:`, error)
        // 规则执行失败时记录为低置信度问题
        issues.push({
          id: rule.id,
          category: rule.category,
          severity: "minor",
          name: rule.name,
          description: `${rule.description}（规则执行异常）`,
          detail: `规则检查过程中发生错误：${error instanceof Error ? error.message : String(error)}`,
          location: "未知",
          basis: rule.basis,
          confidence: 0.5,
          level: "national"
        })
      }
    }

    // 计算得分：critical扣15分，major扣5分，minor扣2分，保底0分
    const score = Math.max(0, 100 - criticalCount * 15 - majorCount * 5 - minorCount * 2)

    // 判定是否通过：无critical且得分≥85
    const pass = score >= 85 && !issues.some(i => i.severity === "critical")

    // 提取知识库引用
    const knowledgeRefs = [...new Set(issues.flatMap(i => i.basis))]

    return {
      pass,
      score,
      issues,
      knowledgeRefs
    }
  }

  /**
   * 根据规则特征和结果计算置信度
   */
  private calculateConfidence(rule: any, result: RuleResult): number {
    let base = 0.85

    // 基于规则类别调整
    switch (rule.category) {
      case "compliance": base = 0.88; break
      case "standard": base = 0.90; break
      case "calculation": base = 0.87; break
      case "procedure": base = 0.86; break
      case "consistency": base = 0.84; break
    }

    // 基于严重程度调整
    switch (rule.severity) {
      case "critical": base += 0.03; break
      case "major": base += 0.01; break
      case "minor": base -= 0.02; break
    }

    // 如果结果包含精确位置信息，提升置信度
    if (result.location && result.location !== "-" && result.location !== "全文") {
      base += 0.02
    }

    // 如果结果包含数据支撑，提升置信度
    if (result.data) {
      base += 0.02
    }

    return Math.min(0.95, Math.max(0.60, base))
  }

  /**
   * 获取规则列表（用于调试和文档生成）
   */
  getRules() {
    return this.rules.map(r => ({
      id: r.id,
      name: r.name,
      category: r.category,
      severity: r.severity,
      basis: r.basis
    }))
  }

  /**
   * 按类别获取规则
   */
  getRulesByCategory(category: string) {
    return this.rules.filter(r => r.category === category)
  }

  /**
   * 按严重程度获取规则
   */
  getRulesBySeverity(severity: string) {
    return this.rules.filter(r => r.severity === severity)
  }
}

export default NationalRuleEngine
