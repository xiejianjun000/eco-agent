// mcp-server/src/knowledge-graph.ts
// 行业知识图谱：行业-工艺-污染物-标准关系

export interface IndustryNode {
  code: string
  name: string
  category: string
  processes: ProcessNode[]
  keyPollutants: string[]
  applicableStandards: string[]
  permitRequirements: string[]
  eiaRequirements: string[]
}

export interface ProcessNode {
  name: string
  description: string
  inputs: string[]
  outputs: string[]
  pollutants: Array<{
    name: string
    type: "air" | "water" | "solid" | "noise"
    typicalValue: string
    unit: string
  }>
  controlMeasures: string[]
}

export class KnowledgeGraph {
  private industries: Map<string, IndustryNode> = new Map()

  async initialize() {
    // 加载预构建的知识图谱数据
    await this.loadIndustryData()
    console.error("Knowledge graph initialized")
  }

  private async loadIndustryData() {
    // 化工行业知识图谱示例
    this.industries.set("C2614", {
      code: "C2614",
      name: "有机化学原料制造",
      category: "C26",
      processes: [
        {
          name: "合成反应",
          description: "通过化学反应合成有机原料",
          inputs: ["原料", "催化剂", "溶剂"],
          outputs: ["产品", "副产品", "废气"],
          pollutants: [
            { name: "VOCs", type: "air", typicalValue: "50-500", unit: "mg/m³" },
            { name: "NOx", type: "air", typicalValue: "100-300", unit: "mg/m³" },
            { name: "COD", type: "water", typicalValue: "1000-5000", unit: "mg/L" }
          ],
          controlMeasures: ["冷凝回收", "RTO焚烧", "碱液吸收"]
        },
        {
          name: "精馏分离",
          description: "通过精馏分离产品",
          inputs: ["反应产物"],
          outputs: ["精馏产品", "釜底残液", "不凝气"],
          pollutants: [
            { name: "VOCs", type: "air", typicalValue: "100-1000", unit: "mg/m³" },
            { name: "有机废液", type: "solid", typicalValue: "5-20", unit: "t/a" }
          ],
          controlMeasures: ["真空系统", "冷凝回收", "活性炭吸附"]
        }
      ],
      keyPollutants: ["VOCs", "NOx", "COD", "氨氮", "特征污染物"],
      applicableStandards: ["GB 31571-2015", "GB 37822-2019", "GB 8978-1996"],
      permitRequirements: ["重点管理", "VOCs总量替代", "LDAR检测"],
      eiaRequirements: ["源强核算", "预测模型", "风险评价", "新污染物分析"]
    })

    // 火电行业知识图谱
    this.industries.set("D4411", {
      code: "D4411",
      name: "火力发电",
      category: "D44",
      processes: [
        {
          name: "锅炉燃烧",
          description: "燃煤/燃气锅炉燃烧发电",
          inputs: ["煤炭", "天然气", "空气"],
          outputs: ["电力", "烟气", "灰渣"],
          pollutants: [
            { name: "SO2", type: "air", typicalValue: "35-200", unit: "mg/m³" },
            { name: "NOx", type: "air", typicalValue: "50-200", unit: "mg/m³" },
            { name: "颗粒物", type: "air", typicalValue: "5-30", unit: "mg/m³" },
            { name: "CO2", type: "air", typicalValue: "100000-150000", unit: "mg/m³" }
          ],
          controlMeasures: ["低氮燃烧", "SCR脱硝", "石灰石-石膏脱硫", "电袋除尘", "CCUS"]
        }
      ],
      keyPollutants: ["SO2", "NOx", "颗粒物", "汞及其化合物", "CO2"],
      applicableStandards: ["GB 13223-2011", "GB 13271-2014"],
      permitRequirements: ["重点管理", "超低排放", "碳排放核算"],
      eiaRequirements: ["源强核算", "预测模型", "碳排放评价", "温室气体排放"]
    })

    // 钢铁行业知识图谱
    this.industries.set("C3110", {
      code: "C3110",
      name: "炼铁",
      category: "C31",
      processes: [
        {
          name: "高炉炼铁",
          description: "高炉还原铁矿石生产生铁",
          inputs: ["铁矿石", "焦炭", "石灰石"],
          outputs: ["生铁", "高炉煤气", "炉渣"],
          pollutants: [
            { name: "SO2", type: "air", typicalValue: "50-200", unit: "mg/m³" },
            { name: "NOx", type: "air", typicalValue: "100-300", unit: "mg/m³" },
            { name: "颗粒物", type: "air", typicalValue: "20-100", unit: "mg/m³" },
            { name: "CO", type: "air", typicalValue: "5000-10000", unit: "mg/m³" }
          ],
          controlMeasures: ["煤气净化", "布袋除尘", "脱硫脱硝"]
        }
      ],
      keyPollutants: ["SO2", "NOx", "颗粒物", "CO", "二噁英"],
      applicableStandards: ["GB 28663-2012", "GB 13271-2014"],
      permitRequirements: ["重点管理", "超低排放", "产能置换"],
      eiaRequirements: ["源强核算", "预测模型", "碳排放评价", "重金属污染"]
    })
  }

  async getIndustryInfo(code: string, queryType?: string): Promise<any> {
    const industry = this.industries.get(code)
    if (!industry) {
      return { error: `Industry ${code} not found in knowledge graph` }
    }

    if (queryType === "eia") {
      return {
        code: industry.code,
        name: industry.name,
        keyPollutants: industry.keyPollutants,
        eiaRequirements: industry.eiaRequirements,
        processes: industry.processes.map(p => ({
          name: p.name,
          pollutants: p.pollutants,
          controlMeasures: p.controlMeasures
        }))
      }
    }

    if (queryType === "permit") {
      return {
        code: industry.code,
        name: industry.name,
        keyPollutants: industry.keyPollutants,
        permitRequirements: industry.permitRequirements,
        applicableStandards: industry.applicableStandards
      }
    }

    if (queryType === "standards") {
      return {
        code: industry.code,
        name: industry.name,
        applicableStandards: industry.applicableStandards,
        standards: industry.applicableStandards.map(s => ({
          code: s,
          pollutants: industry.keyPollutants
        }))
      }
    }

    return industry
  }

  async findRelatedIndustries(pollutant: string): Promise<string[]> {
    const related: string[] = []
    for (const [code, industry] of this.industries) {
      if (industry.keyPollutants.includes(pollutant)) {
        related.push(code)
      }
    }
    return related
  }

  async findProcessesByPollutant(industryCode: string, pollutant: string): Promise<any[]> {
    const industry = this.industries.get(industryCode)
    if (!industry) return []

    return industry.processes.filter(p => 
      p.pollutants.some(pl => pl.name.includes(pollutant) || pollutant.includes(pl.name))
    )
  }

  async validatePollutantSource(industryCode: string, pollutant: string, source: string): Promise<{ valid: boolean; confidence: number; expectedProcesses: string[] }> {
    const processes = await this.findProcessesByPollutant(industryCode, pollutant)
    const valid = processes.some(p => p.name.includes(source) || source.includes(p.name))

    return {
      valid,
      confidence: valid ? 0.95 : 0.3,
      expectedProcesses: processes.map(p => p.name)
    }
  }
}

export default KnowledgeGraph
