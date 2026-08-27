// mcp-server/src/search-engine.ts
// 混合检索引擎：向量检索 + 关键词检索 + 知识图谱

import { VectorStore } from "./vector-store.js"
import { KnowledgeGraph } from "./knowledge-graph.js"

export interface SearchResult {
  content: string
  metadata: any
  score: number
  source: "vector" | "keyword" | "knowledge_graph" | "hybrid"
}

export class SearchEngine {
  private vectorStore: VectorStore
  private knowledgeGraph: KnowledgeGraph

  constructor(vectorStore: VectorStore, knowledgeGraph: KnowledgeGraph) {
    this.vectorStore = vectorStore
    this.knowledgeGraph = knowledgeGraph
  }

  async search(query: string, options: {
    filter?: any
    topK?: number
    useKnowledgeGraph?: boolean
  } = {}): Promise<SearchResult[]> {
    const { filter, topK = 5, useKnowledgeGraph = true } = options

    // 1. 向量检索
    const vectorResults = await this.vectorStore.search(query, { filter, topK: topK * 2 })

    // 2. 关键词检索
    const keywordResults = await this.vectorStore.keywordSearch(query, { filter, topK: topK * 2 })

    // 3. RRF 融合
    const fused = this.rrfFusion(vectorResults, keywordResults)

    // 4. 知识图谱增强（如果启用）
    if (useKnowledgeGraph) {
      const kgResults = await this.knowledgeGraphSearch(query)
      fused.push(...kgResults)
    }

    // 5. 去重并排序
    return this.deduplicateAndSort(fused, topK)
  }

  private rrfFusion(vectorResults: any[], keywordResults: any[], k: number = 60): SearchResult[] {
    const scores: Map<string, SearchResult> = new Map()

    vectorResults.forEach((doc, idx) => {
      const id = doc.metadata?.source || doc.content?.substring(0, 50)
      if (!scores.has(id)) {
        scores.set(id, { ...doc, source: "vector", score: 0 })
      }
      scores.get(id)!.score += 1 / (k + idx + 1)
    })

    keywordResults.forEach((doc, idx) => {
      const id = doc.metadata?.source || doc.content?.substring(0, 50)
      if (!scores.has(id)) {
        scores.set(id, { ...doc, source: "keyword", score: 0 })
      }
      scores.get(id)!.score += 1 / (k + idx + 1)
    })

    return Array.from(scores.values())
  }

  private async knowledgeGraphSearch(query: string): Promise<SearchResult[]> {
    // 从查询中提取行业代码
    const industryMatch = query.match(/([A-Z]\d{4})/)
    if (!industryMatch) return []

    const industryCode = industryMatch[1]
    const info = await this.knowledgeGraph.getIndustryInfo(industryCode)

    if (info.error) return []

    return [{
      content: `行业知识图谱：${info.name}\n特征污染物：${info.keyPollutants?.join("、")}\n环评要求：${info.eiaRequirements?.join("、")}\n排污许可要求：${info.permitRequirements?.join("、")}`,
      metadata: { source: "knowledge_graph", industry: industryCode, level: "industry" },
      score: 0.95,
      source: "knowledge_graph"
    }]
  }

  private deduplicateAndSort(results: SearchResult[], topK: number): SearchResult[] {
    const seen = new Set<string>()
    return results
      .filter(r => {
        const key = r.metadata?.source || r.content?.substring(0, 100)
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
      .sort((a, b) => b.score - a.score)
      .slice(0, topK)
  }
}

export default SearchEngine
