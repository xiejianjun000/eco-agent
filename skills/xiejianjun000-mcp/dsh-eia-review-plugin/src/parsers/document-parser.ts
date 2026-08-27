import { ParsedDocument } from "../types"
import * as fs from "fs"

export class DocumentParser {
  async parse(filePath: string): Promise<ParsedDocument> {
    const ext = filePath.split(".").pop()?.toLowerCase()

    if (ext === "pdf") {
      return this.parsePDF(filePath)
    } else if (ext === "docx" || ext === "doc") {
      return this.parseWord(filePath)
    } else if (ext === "txt") {
      const text = fs.readFileSync(filePath, "utf-8")
      return this.buildDocument(text)
    }

    throw new Error(`不支持的文件格式: ${ext}`)
  }

  private async parsePDF(filePath: string): Promise<ParsedDocument> {
    // 实际项目中使用 pdf-parse
    // const pdf = require("pdf-parse")
    // const data = await pdf(fs.readFileSync(filePath))
    // return this.buildDocument(data.text)

    // 占位实现
    const text = `[PDF解析占位] ${filePath}`
    return this.buildDocument(text)
  }

  private async parseWord(filePath: string): Promise<ParsedDocument> {
    // 实际项目中使用 mammoth
    // const mammoth = require("mammoth")
    // const result = await mammoth.extractRawText({ path: filePath })
    // return this.buildDocument(result.value)

    // 占位实现
    const text = `[Word解析占位] ${filePath}`
    return this.buildDocument(text)
  }

  private buildDocument(text: string): ParsedDocument {
    return {
      text,
      sections: this.extractSections(text),
      tables: this.extractTables(text),
      citations: this.extractCitations(text)
    }
  }

  private extractSections(text: string): Record<string, any> {
    const sections: Record<string, any> = {}
    const patterns: Record<string, RegExp> = {
      overview: /第[一二三四五六七八九十]+章\s*建设项目概况|1\s+建设项目概况/,
      legalBasis: /编制依据|法规依据|适用标准/,
      planning: /规划符合性|三线一单|生态环境分区管控/,
      ecological: /生态环境|生态保护|生态影响/,
      publicParticipation: /公众参与|公示|信息公开/,
      permit: /排污许可|排污许可证/,
      changes: /变动情况|重大变动|项目变更/,
      pollutantAnalysis: /污染源|污染物|源强核算/,
      waste: /固体废物|危险废物|危废/,
      standards: /评价标准|排放标准|环境质量标准/,
      sourceCalculation: /源强核算|物料衡算|产排污系数/,
      waterEnvironment: /水环境|地表水|地下水/,
      preparation: /编制单位|编制人员|环评单位/
    }

    for (const [key, pattern] of Object.entries(patterns)) {
      const match = text.match(pattern)
      if (match) {
        const startIdx = match.index || 0
        const endIdx = text.indexOf("\n\n", startIdx + 500) || startIdx + 2000
        sections[key] = {
          title: match[0],
          text: text.slice(startIdx, Math.min(endIdx, startIdx + 5000)),
          lineRange: `${startIdx}-${Math.min(endIdx, startIdx + 5000)}`
        }
      }
    }

    return sections
  }

  private extractTables(text: string): Record<string, any[]> {
    const tables: Record<string, any[]> = {}
    // 简化实现：从文本中提取表格数据
    // 实际项目中需要更复杂的表格解析逻辑
    return tables
  }

  private extractCitations(text: string): string[] {
    const citations: string[] = []
    const pattern = /《[^》]+》|GB\s*\d{4,5}[-–]\d{4}|HJ\s*\d{2,4}[-–]\d{4}/g
    let match
    while ((match = pattern.exec(text)) !== null) {
      if (!citations.includes(match[0])) {
        citations.push(match[0])
      }
    }
    return citations
  }
}
