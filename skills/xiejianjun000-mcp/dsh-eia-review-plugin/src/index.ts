import type { Context } from "@deepseek-ai/cordis"
import { defineTool } from "@deepseek-ai/dsh-tools"
import { NationalRuleEngine } from "./core/engine"
import { ProvincialRegistry } from "./provinces/registry"
import { DocumentParser } from "./parsers/document-parser"
import { EHSKnowledgeClient } from "./mcp/knowledge-client"

export const name = "dsh-eia-review-plugin"
export const inject = ["tools", "llm", "skills"]

export interface Config {
  province?: string
  reviewMode: "eia" | "permit" | "both"
  enableMCP: boolean
  strictMode: boolean
  mcpUrl?: string           // MCP SSE 端点 URL
  mcpApiKey?: string        // MCP API Key (优先从环境变量读取)
}

export function apply(ctx: Context, config: Config) {
  const nationalEngine = new NationalRuleEngine()
  const provincialRegistry = new ProvincialRegistry()
  const parser = new DocumentParser()

  // 初始化 EHS 知识库 MCP 客户端
  let kbClient: EHSKnowledgeClient | null = null
  if (config.enableMCP) {
    const apiKey = config.mcpApiKey || process.env.EHS_KB_API_KEY
    const mcpUrl = config.mcpUrl || "http://111.230.89.107:8000/sse/"

    if (apiKey) {
      kbClient = new EHSKnowledgeClient(ctx, {
        url: mcpUrl,
        apiKey: apiKey
      })
      console.log(`[dsh-eia-review] EHS 知识库 MCP 已连接: ${mcpUrl}`)
    } else {
      console.warn("[dsh-eia-review] EHS_KB_API_KEY 未设置，MCP 知识库增强已禁用")
    }
  }

  // ═══════════════════════════════════════════════════════════════════════
  // 工具1: 环评技术审查
  // ═══════════════════════════════════════════════════════════════════════
  ctx.tools.register(defineTool({
    name: "eia_technical_review",
    description: "对建设项目环境影响评价报告书/表进行技术审查，支持EHS知识库MCP增强。",
    parameters: {
      reportPath: { type: "string", required: true, description: "环评报告文件路径(PDF/Word)" },
      reportType: { type: "string", required: true, enum: ["report_book", "report_table", "registration"], description: "报告书/报告表/登记表" },
      projectProvince: { type: "string", required: false, description: "项目所在省份代码，如zhejiang" },
      industry: { type: "string", required: false, description: "行业类别(GB/T4754)" },
      useKnowledgeBase: { type: "boolean", required: false, description: "是否启用EHS知识库MCP增强", default: true }
    },
    output: {
      schema: {
        type: "object",
        properties: {
          pass: { type: "boolean" },
          score: { type: "number" },
          nationalIssues: { type: "array" },
          provincialIssues: { type: "array" },
          knowledgeRefs: { type: "array" },
          kbEnhanced: { type: "boolean" },
          kbStatus: { type: "string" }
        }
      },
      render: (args, value) => [{
        type: "text",
        text: formatReviewResult(value, args.projectProvince || config.province || "national")
      }]
    },
    async execute(args, exec) {
      const doc = await parser.parse(args.reportPath)
      const effectiveProvince = args.projectProvince || config.province || "national"
      const useKB = args.useKnowledgeBase !== false && config.enableMCP && kbClient !== null

      // 检查知识库状态
      let kbStatus = "disabled"
      if (useKB && kbClient) {
        const status = await kbClient.checkStatus()
        kbStatus = status.status === "online" ? "connected" : "offline"
      }

      // 第一层：国家通用规则审查
      const nationalResult = await nationalEngine.review(doc, {
        reportType: args.reportType,
        industry: args.industry,
        province: effectiveProvince,
        reviewType: "eia"
      })

      // 第二层：省级规则审查
      let provincialResult = { issues: [], score: 100 }
      if (effectiveProvince !== "national") {
        const provEngine = provincialRegistry.load(effectiveProvince)
        provincialResult = await provEngine.review(doc, {
          reportType: args.reportType,
          industry: args.industry,
          province: effectiveProvince
        })
      }

      // 第三层：EHS 知识库 MCP 增强
      let allIssues = [...nationalResult.issues, ...provincialResult.issues]
      let kbEnhanced = false

      if (useKB && kbClient && kbStatus === "connected") {
        console.log(`[dsh-eia-review] 启用 EHS 知识库增强，处理 ${allIssues.length} 个问题...`)

        for (const issue of allIssues) {
          if (issue.confidence >= 0.95) continue  // 已高置信度，跳过

          try {
            const kbResult = await kbClient.verifyIssue(issue, effectiveProvince)

            if (kbResult.confirmed) {
              issue.confidence = kbResult.confidence
              issue.kbConfirmed = true
              issue.kbCitation = kbResult.citation
              issue.kbRegulation = kbResult.regulation
              if (kbResult.similarCases) {
                issue.kbSimilarCases = kbResult.similarCases
              }
              console.log(`[dsh-eia-review] [${issue.id}] 知识库确认 ✅ 置信度→${kbResult.confidence}`)
            } else {
              console.log(`[dsh-eia-review] [${issue.id}] 知识库未确认 ❌`)
              if (config.strictMode) {
                // 严格模式：知识库无法确认则降级
                issue.confidence = Math.min(issue.confidence, 0.65)
                issue.kbConfirmed = false
              }
            }
          } catch (e) {
            console.error(`[dsh-eia-review] [${issue.id}] 知识库查询异常: ${e}`)
          }
        }

        kbEnhanced = true
      }

      // 严格模式：过滤低置信度问题
      if (config.strictMode) {
        const beforeCount = allIssues.length
        allIssues = allIssues.filter(i => i.confidence >= 0.75)
        if (beforeCount > allIssues.length) {
          console.log(`[dsh-eia-review] 严格模式过滤: ${beforeCount - allIssues.length} 个低置信度问题已移除`)
        }
      }

      // 计算加权得分
      const totalScore = Math.round(
        nationalResult.score * 0.7 + provincialResult.score * 0.3
      )

      return {
        pass: totalScore >= 85 && !allIssues.some((i: any) => i.severity === "critical" && i.confidence >= 0.85),
        score: totalScore,
        nationalIssues: nationalResult.issues,
        provincialIssues: provincialResult.issues,
        knowledgeRefs: [...new Set(allIssues.flatMap((i: any) => i.basis || []))],
        kbEnhanced,
        kbStatus
      }
    }
  }))

  // ═══════════════════════════════════════════════════════════════════════
  // 工具2: 排污许可证技术审查
  // ═══════════════════════════════════════════════════════════════════════
  ctx.tools.register(defineTool({
    name: "permit_technical_review",
    description: "对排污许可证申请材料进行技术审查，支持EHS知识库MCP增强。",
    parameters: {
      applicationPath: { type: "string", required: true },
      reviewType: { type: "string", required: true, enum: ["formal", "substantive", "full"] },
      province: { type: "string", required: false }
    },
    output: { schema: { type: "object" }, render: () => [] },
    async execute(args, exec) {
      const doc = await parser.parse(args.applicationPath)
      const effectiveProvince = args.province || config.province || "national"

      const nationalResult = await nationalEngine.review(doc, {
        reportType: "permit",
        province: effectiveProvince,
        reviewType: "permit"
      })

      return {
        pass: nationalResult.score >= 85,
        score: nationalResult.score,
        issues: nationalResult.issues,
        knowledgeRefs: nationalResult.knowledgeRefs,
        kbEnhanced: false,
        kbStatus: kbClient ? (await kbClient.checkStatus()).status : "disabled"
      }
    }
  }))

  // ═══════════════════════════════════════════════════════════════════════
  // 工具3: 知识库状态检查
  // ═══════════════════════════════════════════════════════════════════════
  if (kbClient) {
    ctx.tools.register(defineTool({
      name: "ehs_kb_status",
      description: "检查 EHS 知识库 MCP 连接状态",
      parameters: {},
      output: {
        schema: { type: "object" },
        render: (args, value) => [{
          type: "text",
          text: `## EHS 知识库状态\n\n` +
                `**连接状态**: ${value.status === "online" ? "🟢 在线" : "🔴 离线"}\n` +
                `**服务端点**: ${value.url || "未配置"}\n` +
                `**版本**: ${value.version || "未知"}\n` +
                `**文档数**: ${value.documentCount || 0}\n` +
                `**最后同步**: ${value.lastSync || "未同步"}`
        }]
      },
      async execute() {
        const status = await kbClient!.checkStatus()
        return {
          ...status,
          url: config.mcpUrl || "http://111.230.89.107:8000/sse/"
        }
      }
    }))

    // 工具4: 知识库搜索（调试用）
    ctx.tools.register(defineTool({
      name: "ehs_kb_search",
      description: "搜索 EHS 知识库（调试/验证用）",
      parameters: {
        query: { type: "string", required: true },
        topK: { type: "number", required: false, default: 5 },
        province: { type: "string", required: false }
      },
      output: { schema: { type: "object" }, render: () => [] },
      async execute(args) {
        return kbClient!.search(args.query, {
          topK: args.topK || 5,
          province: args.province
        })
      }
    }))
  }

  // ═══════════════════════════════════════════════════════════════════════
  // 注册 Skill
  // ═══════════════════════════════════════════════════════════════════════
  ctx.skills?.register?.({
    name: "eia-review-expert",
    description: "环境影响评价技术审查专家，集成EHS知识库MCP",
    body: `你是环评技术审查专家，集成EHS知识库MCP增强能力：
1. 优先执行国家通用规则（20条）
2. 根据项目所在省份加载省级规则
3. 对低置信度问题自动查询EHS知识库确认
4. 输出结构化审查报告：通过/不通过、得分、问题清单、法规依据、知识库引用`
  })
}

// 格式化审查结果
function formatReviewResult(value: any, province: string): string {
  const allIssues = [...(value.nationalIssues || []), ...(value.provincialIssues || [])]
  const critical = allIssues.filter((i: any) => i.severity === "critical").length
  const major = allIssues.filter((i: any) => i.severity === "major").length
  const minor = allIssues.filter((i: any) => i.severity === "minor").length

  let text = `## 环评技术审查结果\n\n`
  text += `**省份**: ${province === "national" ? "全国通用" : province}\n`
  text += `**结论**: ${value.pass ? "✅ 通过" : "❌ 不通过"}\n`
  text += `**得分**: ${value.score}/100\n`
  text += `**知识库**: ${value.kbEnhanced ? "🟢 已增强" : value.kbStatus === "connected" ? "🟡 未启用" : "🔴 未连接"}\n`
  text += `**问题统计**: 🔴Critical ${critical} | 🟡Major ${major} | 🟢Minor ${minor}\n\n`

  if (allIssues.length > 0) {
    text += `### 问题清单\n\n`
    for (const [idx, issue] of allIssues.entries()) {
      const icon = issue.severity === "critical" ? "🔴" : issue.severity === "major" ? "🟡" : "🟢"
      const kbIcon = issue.kbConfirmed === true ? "✅" : issue.kbConfirmed === false ? "❓" : ""
      text += `${idx + 1}. ${icon} **[${issue.level === "national" ? "国家" : "省级"}] ${issue.name}** ${kbIcon}\n`
      text += `   - 详情: ${issue.detail}\n`
      text += `   - 位置: ${issue.location}\n`
      text += `   - 依据: ${issue.basis?.join("、") || "-"}\n`
      if (issue.kbCitation) text += `   - 知识库引用: ${issue.kbCitation}\n`
      if (issue.kbRegulation) text += `   - 法规条款: ${issue.kbRegulation}\n`
      text += `   - 置信度: ${(issue.confidence * 100).toFixed(0)}%\n\n`
    }
  }

  return text
}
