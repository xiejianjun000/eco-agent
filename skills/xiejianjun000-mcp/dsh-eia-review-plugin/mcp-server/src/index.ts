// mcp-server/src/index.ts
// 环评与排污许可法规知识库 MCP 服务器
// 支持 stdio 和 streamable-http 两种传输模式

import { Server } from "@modelcontextprotocol/sdk/server/index.js"
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js"
import { VectorStore } from "./vector-store.js"
import { KnowledgeGraph } from "./knowledge-graph.js"
import { SearchEngine } from "./search-engine.js"
import { Reranker } from "./reranker.js"

const server = new Server(
  {
    name: "eia-knowledge-base",
    version: "1.0.0"
  },
  {
    capabilities: {
      tools: {
        kb_search: {
          description: "搜索环评/排污许可法规知识库",
          inputSchema: {
            type: "object",
            properties: {
              query: { type: "string", description: "查询内容" },
              topK: { type: "number", default: 5, description: "返回结果数量" },
              filter: {
                type: "object",
                properties: {
                  level: { type: "string", enum: ["national", "provincial"], description: "法规层级" },
                  province: { type: "string", description: "省份代码" },
                  category: { type: "string", enum: ["regulation", "standard", "guideline", "case"], description: "文件类别" },
                  industry: { type: "string", description: "行业代码" },
                  dateRange: { type: "string", description: "日期范围" }
                }
              }
            },
            required: ["query"]
          }
        },
        kb_verify: {
          description: "验证具体条款的现行有效性",
          inputSchema: {
            type: "object",
            properties: {
              standardCode: { type: "string", description: "标准编号" },
              clause: { type: "string", description: "条款内容" }
            },
            required: ["standardCode"]
          }
        },
        kb_calculate: {
          description: "执行标准计算（如排放量核算）",
          inputSchema: {
            type: "object",
            properties: {
              formula: { type: "string", description: "公式名称" },
              params: { type: "object", description: "计算参数" }
            },
            required: ["formula", "params"]
          }
        },
        kb_industry_info: {
          description: "查询行业环评/排污许可要求",
          inputSchema: {
            type: "object",
            properties: {
              industryCode: { type: "string", description: "行业代码(GB/T4754)" },
              queryType: { type: "string", enum: ["eia", "permit", "standards", "all"], default: "all" }
            },
            required: ["industryCode"]
          }
        }
      }
    }
  }
)

// 初始化组件
const vectorStore = new VectorStore()
const knowledgeGraph = new KnowledgeGraph()
const searchEngine = new SearchEngine(vectorStore, knowledgeGraph)
const reranker = new Reranker()

// 工具处理
server.setRequestHandler("tools/call", async (request) => {
  const { name, arguments: args } = request.params

  if (name === "kb_search") {
    return await handleSearch(args)
  }

  if (name === "kb_verify") {
    return await handleVerify(args)
  }

  if (name === "kb_calculate") {
    return await handleCalculate(args)
  }

  if (name === "kb_industry_info") {
    return await handleIndustryInfo(args)
  }

  throw new Error(`Unknown tool: ${name}`)
})

async function handleSearch(args: any) {
  // 1. 查询改写: 将自然语言转为结构化查询
  const structuredQuery = await rewriteQuery(args.query)

  // 2. 元数据预过滤
  const metadataFilter = buildMetadataFilter(args.filter)

  // 3. 双路检索（向量 + 关键词）
  const [vectorResults, keywordResults] = await Promise.all([
    vectorStore.search(structuredQuery.semantic, { filter: metadataFilter, topK: (args.topK || 5) * 2 }),
    keywordSearch(structuredQuery.keywords, { filter: metadataFilter, topK: (args.topK || 5) * 2 })
  ])

  // 4. RRF 融合排序
  const fused = reciprocalRankFusion(vectorResults, keywordResults)

  // 5. 领域重排序模型
  const reranked = await reranker.rerank(args.query, fused.slice(0, 10))

  return {
    content: [{
      type: "text",
      text: JSON.stringify({
        documents: reranked.slice(0, args.topK || 5).map((r: any) => ({
          content: r.content,
          source: r.metadata.source,
          score: r.score,
          article: r.metadata.article,
          effectiveDate: r.metadata.effectiveDate,
          level: r.metadata.level,
          category: r.metadata.category
        }))
      })
    }]
  }
}

async function handleVerify(args: any) {
  const { standardCode, clause } = args

  // 查询标准有效性
  const status = await vectorStore.getStandardStatus(standardCode)

  return {
    content: [{
      type: "text",
      text: JSON.stringify({
        standardCode,
        status: status.status,
        effectiveDate: status.effectiveDate,
        supersededBy: status.supersededBy,
        supersededDate: status.supersededDate,
        isActive: status.status === "active",
        clause: clause ? await verifyClause(standardCode, clause) : undefined
      })
    }]
  }
}

async function handleCalculate(args: any) {
  const { formula, params } = args

  // 执行标准计算
  const result = await executeFormula(formula, params)

  return {
    content: [{
      type: "text",
      text: JSON.stringify(result)
    }]
  }
}

async function handleIndustryInfo(args: any) {
  const { industryCode, queryType } = args

  // 查询行业知识图谱
  const info = await knowledgeGraph.getIndustryInfo(industryCode, queryType)

  return {
    content: [{
      type: "text",
      text: JSON.stringify(info)
    }]
  }
}

// 查询改写
async function rewriteQuery(query: string): Promise<{ semantic: string; keywords: string[] }> {
  // 使用 LLM 将自然语言转为结构化查询
  // 简化实现：提取关键词
  const keywords = query
    .replace(/[，。！？、；：""''（）【】《》]/g, " ")
    .split(/\s+/)
    .filter(w => w.length >= 2)
    .slice(0, 10)

  return { semantic: query, keywords }
}

// 元数据过滤构建
function buildMetadataFilter(filter?: any): any {
  if (!filter) return {}
  const result: any = {}
  if (filter.level) result.level = filter.level
  if (filter.province) result.province = filter.province
  if (filter.category) result.category = filter.category
  if (filter.industry) result.industry = filter.industry
  if (filter.dateRange) result.dateRange = filter.dateRange
  return result
}

// 关键词搜索（BM25）
async function keywordSearch(keywords: string[], options: any): Promise<any[]> {
  // 简化实现：从向量数据库中关键词匹配
  return vectorStore.keywordSearch(keywords.join(" "), options)
}

// RRF 融合排序
function reciprocalRankFusion(vectorResults: any[], keywordResults: any[]): any[] {
  const k = 60  // RRF 常数
  const scores: Map<string, { doc: any; score: number }> = new Map()

  // 向量检索得分
  vectorResults.forEach((doc, idx) => {
    const id = doc.id || doc.metadata?.source
    if (!scores.has(id)) {
      scores.set(id, { doc, score: 0 })
    }
    scores.get(id)!.score += 1 / (k + idx + 1)
  })

  // 关键词检索得分
  keywordResults.forEach((doc, idx) => {
    const id = doc.id || doc.metadata?.source
    if (!scores.has(id)) {
      scores.set(id, { doc, score: 0 })
    }
    scores.get(id)!.score += 1 / (k + idx + 1)
  })

  return Array.from(scores.values())
    .sort((a, b) => b.score - a.score)
    .map(s => ({ ...s.doc, score: s.score }))
}

// 条款验证
async function verifyClause(standardCode: string, clause: string): Promise<any> {
  // 查询知识库验证条款是否属于该标准
  const results = await vectorStore.search(`${standardCode} ${clause}`, { topK: 3 })
  const bestMatch = results[0]

  return {
    valid: bestMatch && bestMatch.score > 0.75,
    confidence: bestMatch?.score || 0,
    source: bestMatch?.metadata?.source
  }
}

// 公式执行
async function executeFormula(formula: string, params: any): Promise<any> {
  const formulas: Record<string, (p: any) => any> = {
    "emission_calculation": (p) => {
      // 排放量计算: G = 产量 × 产污系数 × (1 - 去除效率)
      const production = p.production || 0
      const factor = p.emission_factor || 0
      const efficiency = (p.removal_efficiency || 0) / 100
      return {
        value: production * factor * (1 - efficiency),
        unit: "t/a",
        formula: "G = 产量 × 产污系数 × (1 - 去除效率)",
        steps: [
          `产量: ${production} t/a`,
          `产污系数: ${factor} kg/t-产品`,
          `去除效率: ${efficiency * 100}%`,
          `计算: ${production} × ${factor} × ${1 - efficiency} = ${production * factor * (1 - efficiency)} t/a`
        ]
      }
    },
    "material_balance": (p) => {
      // 物料衡算
      const input = p.input_material || 0
      const inputContent = (p.input_content || 0) / 100
      const product = p.product_output || 0
      const productContent = (p.product_content || 0) / 100
      return {
        value: input * inputContent - product * productContent,
        unit: "t/a",
        formula: "G = 输入物料 × 污染物含量 - 产品 × 污染物含量",
        steps: [
          `输入物料: ${input} t/a × ${inputContent * 100}% = ${input * inputContent} t/a`,
          `产品带出: ${product} t/a × ${productContent * 100}% = ${product * productContent} t/a`,
          `污染物产生量: ${input * inputContent - product * productContent} t/a`
        ]
      }
    }
  }

  const executor = formulas[formula]
  if (!executor) {
    return { error: `未知公式: ${formula}`, available: Object.keys(formulas) }
  }

  return executor(params)
}

// 启动服务器
async function main() {
  // 初始化向量数据库
  await vectorStore.initialize()
  await knowledgeGraph.initialize()

  const transport = new StdioServerTransport()
  await server.connect(transport)

  console.error("MCP EIA Knowledge Server started")
}

main().catch(console.error)
