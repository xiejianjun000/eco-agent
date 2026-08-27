// src/mcp/knowledge-client.ts
// EHS 知识库 MCP 客户端 - 支持 SSE 远程连接
// 服务端点: http://111.230.89.107:8000/sse/
// 鉴权: X-API-Key (通过环境变量 EHS_KB_API_KEY 注入)

import type { Context } from "@deepseek-ai/cordis"

export interface MCPConfig {
  url: string
  apiKey?: string
  timeout?: number
}

export interface KBSearchResult {
  documents: Array<{
    content: string
    source: string
    score: number
    article?: string
    metadata?: Record<string, any>
  }>
  total: number
}

export interface KBStatus {
  status: "online" | "offline" | "error"
  version?: string
  lastSync?: string
  documentCount?: number  // 知识库文档总数（约81,071篇）
}

/**
 * EHS 知识库 MCP 客户端
 * 支持工具: kb_upload / kb_delete / kb_sync / kb_list / kb_search / kb_status
 */
export class EHSKnowledgeClient {
  private config: MCPConfig
  private ctx: Context
  private connected: boolean = false

  constructor(ctx: Context, config: MCPConfig) {
    this.ctx = ctx
    this.config = {
      timeout: 30000,
      ...config
    }
  }

  /**
   * 检查 MCP 连接状态
   */
  async checkStatus(): Promise<KBStatus> {
    try {
      // 通过 DSH MCP 工具调用 kb_status
      const result = await this.callTool("kb_status", {})
      return {
        status: "online",
        ...result
      }
    } catch (e) {
      return {
        status: "offline",
        version: undefined,
        lastSync: undefined,
        documentCount: 0
      }
    }
  }

  /**
   * 搜索知识库
   * @param query 查询文本
   * @param options 搜索选项
   */
  async search(
    query: string,
    options: {
      topK?: number
      filter?: Record<string, any>
      category?: "regulation" | "standard" | "guideline" | "case"
      province?: string
      level?: "national" | "provincial"
    } = {}
  ): Promise<KBSearchResult> {
    const params: Record<string, any> = {
      query,
      top_k: options.topK || 5,
      ...options.filter
    }

    if (options.category) params.category = options.category
    if (options.province) params.province = options.province
    if (options.level) params.level = options.level

    const result = await this.callTool("kb_search", params)

    return {
      documents: result.documents || result.results || [],
      total: result.total || result.count || 0
    }
  }

  /**
   * 同步知识库（增量更新）
   */
  async sync(): Promise<{ success: boolean; message: string }> {
    try {
      const result = await this.callTool("kb_sync", {})
      return {
        success: true,
        message: result.message || "同步完成"
      }
    } catch (e) {
      return {
        success: false,
        message: e instanceof Error ? e.message : "同步失败"
      }
    }
  }

  /**
   * 列出知识库中的文档
   */
  async list(options: {
    category?: string
    province?: string
    limit?: number
    offset?: number
  } = {}): Promise<Array<{
    id: string
    title: string
    source: string
    category: string
    uploadDate: string
  }>> {
    const result = await this.callTool("kb_list", {
      limit: options.limit || 20,
      offset: options.offset || 0,
      ...options
    })
    return result.documents || result.items || []
  }

  /**
   * 调用 MCP 工具（通过 DSH MCP 客户端代理）
   */
  private async callTool(toolName: string, params: Record<string, any>): Promise<any> {
    // 在 DSH 环境中，通过 ctx.tools 调用 MCP 工具
    // 工具名格式: mcp__ehs-kb__{toolName}
    const fullToolName = `mcp__ehs-kb__${toolName}`

    // 如果 DSH 已注册该工具，直接调用
    if (this.ctx.tools?.call) {
      try {
        return await this.ctx.tools.call(fullToolName, params)
      } catch (e) {
        // 回退：尝试直接 HTTP 调用（如果 DSH 未代理）
        return this.directHttpCall(toolName, params)
      }
    }

    // 直接 HTTP 调用
    return this.directHttpCall(toolName, params)
  }

  /**
   * 直接 HTTP 调用 MCP SSE 端点（备用方案）
   */
  private async directHttpCall(toolName: string, params: Record<string, any>): Promise<any> {
    if (!this.config.apiKey) {
      throw new Error("EHS_KB_API_KEY 环境变量未设置，无法连接知识库")
    }

    const url = `${this.config.url.replace(/\/+$/, "")}/tools/${toolName}`

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": this.config.apiKey,
        "Accept": "text/event-stream"
      },
      body: JSON.stringify(params)
    })

    if (!response.ok) {
      throw new Error(`MCP 调用失败: ${response.status} ${response.statusText}`)
    }

    // 解析 SSE 响应
    const text = await response.text()
    const lines = text.split("\n")
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          return JSON.parse(line.slice(6))
        } catch {
          continue
        }
      }
    }

    throw new Error("无法解析 MCP SSE 响应")
  }

  /**
   * 验证问题（核心功能：对低置信度问题查询知识库确认）
   */
  async verifyIssue(issue: {
    id: string
    name: string
    description: string
    detail: string
    category: string
    severity: string
  }, province?: string): Promise<{
    confirmed: boolean
    confidence: number
    citation?: string
    regulation?: string
    similarCases?: string[]
  }> {
    // 构建查询
    const query = this.buildQuery(issue, province)

    try {
      const result = await this.search(query, {
        topK: 3,
        level: province ? "provincial" : "national",
        province: province
      })

      if (result.documents.length === 0) {
        return { confirmed: false, confidence: 0.60 }
      }

      const best = result.documents[0]
      const score = best.score || 0

      // 根据知识库匹配度判定
      if (score >= 0.88) {
        return {
          confirmed: true,
          confidence: 0.95,
          citation: best.source,
          regulation: best.article || best.metadata?.article,
          similarCases: result.documents.slice(1).map(d => d.source)
        }
      } else if (score >= 0.75) {
        return {
          confirmed: true,
          confidence: 0.85,
          citation: best.source
        }
      } else {
        return {
          confirmed: false,
          confidence: 0.65,
          citation: best.source
        }
      }
    } catch (e) {
      console.error(`[EHS-KB] 知识库查询失败: ${e}`)
      return { confirmed: false, confidence: 0.60 }
    }
  }

  /**
   * 构建知识库查询语句
   */
  private buildQuery(issue: any, province?: string): string {
    const parts = [issue.name, issue.description]

    if (issue.detail) parts.push(issue.detail)
    if (province) parts.push(province)

    // 根据类别添加关键词
    if (issue.category === "compliance") parts.push("法规 合规 要求")
    if (issue.category === "standard") parts.push("标准 规范")
    if (issue.category === "calculation") parts.push("核算 计算 方法")
    if (issue.category === "procedure") parts.push("程序 流程 要求")

    return parts.join(" ")
  }
}

export default EHSKnowledgeClient
