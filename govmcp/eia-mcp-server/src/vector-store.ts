// mcp-server/src/vector-store.ts
// 向量数据库封装（基于 ChromaDB）

import { ChromaClient, Collection, IncludeEnum } from "chromadb"

export interface DocumentChunk {
  id: string
  content: string
  metadata: {
    source: string        // 来源文件/法规名称
    article?: string      // 条款编号
    level: "national" | "provincial" | "industry"  // 层级
    province?: string     // 省份代码
    category: "regulation" | "standard" | "guideline" | "case"  // 类别
    industry?: string     // 适用行业
    effectiveDate?: string  // 生效日期
    expiryDate?: string     // 废止日期
    status: "active" | "expired" | "draft"  // 状态
  }
}

export class VectorStore {
  private client: ChromaClient
  private collection?: Collection
  private embeddingModel: string = "Xenova/all-MiniLM-L6-v2"  // 轻量级中文模型

  constructor(options?: { host?: string; port?: number }) {
    const host = options?.host || process.env.CHROMA_HOST || "localhost"
    const port = options?.port || parseInt(process.env.CHROMA_PORT || "8000")
    this.client = new ChromaClient({ path: `http://${host}:${port}` })
  }

  async initialize() {
    try {
      this.collection = await this.client.getOrCreateCollection({
        name: "eia_knowledge_base",
        metadata: { description: "环评与排污许可法规知识库" }
      })
      console.error("Vector store initialized")
    } catch (e) {
      // 优雅降级：ChromaDB 不可用时向量检索禁用，关键词/图谱检索照常
      console.error("Failed to initialize vector store, degraded to keyword-only mode:", e)
      this.collection = undefined
    }
  }

  get available(): boolean {
    return this.collection !== undefined
  }

  async addDocuments(chunks: DocumentChunk[]) {
    if (!this.collection) throw new Error("Collection not initialized")

    await this.collection.add({
      ids: chunks.map(c => c.id),
      documents: chunks.map(c => c.content),
      metadatas: chunks.map(c => c.metadata)
    })

    console.error(`Added ${chunks.length} documents to vector store`)
  }

  async search(query: string, options?: { filter?: any; topK?: number }): Promise<any[]> {
    if (!this.collection) return []  // 向量不可用时降级为空结果，调用方回退关键词检索

    const results = await this.collection.query({
      queryTexts: [query],
      nResults: options?.topK || 5,
      where: options?.filter || undefined,
      include: [IncludeEnum.Documents, IncludeEnum.Metadatas, IncludeEnum.Distances]
    })

    return results.documents[0].map((doc, idx) => ({
      content: doc,
      metadata: results.metadatas[0][idx],
      distance: results.distances?.[0][idx],
      score: 1 - (results.distances?.[0][idx] || 0)  // 转换为相似度分数
    }))
  }

  async keywordSearch(query: string, options?: { filter?: any; topK?: number }): Promise<any[]> {
    // 简化实现：在向量搜索结果中做关键词过滤
    // 实际生产环境应使用 Elasticsearch 或 Meilisearch 做 BM25 搜索
    const vectorResults = await this.search(query, { ...options, topK: (options?.topK || 5) * 3 })

    // 关键词匹配过滤
    const keywords = query.toLowerCase().split(/\s+/)
    return vectorResults.filter(r => {
      const content = (r.content || "").toLowerCase()
      return keywords.some(kw => content.includes(kw))
    }).slice(0, options?.topK || 5)
  }

  async getStandardStatus(standardCode: string): Promise<any> {
    // 查询标准状态
    const results = await this.search(standardCode, { 
      filter: { category: "standard" }, 
      topK: 3 
    })

    const bestMatch = results[0]
    if (!bestMatch) {
      return { status: "unknown", standardCode }
    }

    return {
      status: bestMatch.metadata.status,
      effectiveDate: bestMatch.metadata.effectiveDate,
      expiryDate: bestMatch.metadata.expiryDate,
      source: bestMatch.metadata.source
    }
  }

  async getStats(): Promise<{ total: number; byLevel: Record<string, number>; byCategory: Record<string, number> }> {
    if (!this.collection) throw new Error("Collection not initialized")

    const count = await this.collection.count()

    // 简化统计
    return {
      total: count,
      byLevel: { national: 0, provincial: 0, industry: 0 },
      byCategory: { regulation: 0, standard: 0, guideline: 0, case: 0 }
    }
  }
}

export default VectorStore
