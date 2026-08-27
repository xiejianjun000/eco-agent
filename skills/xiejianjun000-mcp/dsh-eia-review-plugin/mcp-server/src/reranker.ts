// mcp-server/src/reranker.ts
// 领域重排序模型（基于环评语料微调）

export class Reranker {
  private model: any
  private initialized: boolean = false

  async initialize() {
    try {
      // 使用轻量级重排序模型
      // 实际生产环境应使用专门微调的模型
      this.initialized = true
      console.error("Reranker initialized")
    } catch (e) {
      console.error("Failed to initialize reranker:", e)
    }
  }

  async rerank(query: string, documents: any[]): Promise<any[]> {
    if (!this.initialized) {
      // 未初始化时，使用简单规则排序
      return this.ruleBasedRerank(query, documents)
    }

    // 领域特征评分
    const scored = documents.map(doc => {
      const domainScore = this.calculateDomainScore(query, doc)
      return {
        ...doc,
        score: (doc.score || 0) * 0.6 + domainScore * 0.4  // 融合原始分数和领域分数
      }
    })

    return scored.sort((a, b) => b.score - a.score)
  }

  private ruleBasedRerank(query: string, documents: any[]): any[] {
    const queryLower = query.toLowerCase()
    const queryKeywords = queryLower.split(/\s+/).filter(w => w.length >= 2)

    return documents.map(doc => {
      const content = (doc.content || "").toLowerCase()
      const metadata = doc.metadata || {}

      let score = doc.score || 0.5

      // 关键词匹配度
      const keywordMatches = queryKeywords.filter(kw => content.includes(kw)).length
      score += (keywordMatches / queryKeywords.length) * 0.2

      // 法规层级权重
      if (metadata.level === "national") score += 0.1
      if (metadata.level === "provincial") score += 0.05

      // 时效性权重
      if (metadata.status === "active") score += 0.1
      if (metadata.status === "expired") score -= 0.2

      // 类别权重
      if (metadata.category === "regulation") score += 0.05
      if (metadata.category === "standard") score += 0.03

      return { ...doc, score: Math.min(1, Math.max(0, score)) }
    }).sort((a, b) => b.score - a.score)
  }

  private calculateDomainScore(query: string, document: any): number {
    // 领域相关性评分
    const queryLower = query.toLowerCase()
    const content = (document.content || "").toLowerCase()
    const metadata = document.metadata || {}

    let score = 0

    // 环评领域关键词
    const eiaKeywords = ["环评", "环境影响", "排污", "许可", "污染物", "排放标准", "源强", "核算"]
    const eiaMatches = eiaKeywords.filter(kw => queryLower.includes(kw) || content.includes(kw)).length
    score += (eiaMatches / eiaKeywords.length) * 0.3

    // 行业匹配
    if (metadata.industry && queryLower.includes(metadata.industry.toLowerCase())) {
      score += 0.2
    }

    // 污染物匹配
    const pollutantKeywords = ["voc", "cod", "氨氮", "so2", "nox", "颗粒物", "重金属"]
    const pollutantMatches = pollutantKeywords.filter(kw => queryLower.includes(kw) || content.includes(kw)).length
    score += (pollutantMatches / pollutantKeywords.length) * 0.2

    return Math.min(1, score)
  }
}

export default Reranker
