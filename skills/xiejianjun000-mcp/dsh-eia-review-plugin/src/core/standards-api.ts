// src/core/standards-api.ts
// 生态环境部标准库实时校验客户端
// 支持在线查询和离线缓存双模式

export interface StandardInfo {
  code: string              // 标准号
  name: string             // 标准名称
  category: "national" | "industry" | "local"  // 标准类别
  status: "active" | "expired" | "draft" | "superseded"  // 状态
  effectiveDate: string     // 生效日期
  supersededBy?: string    // 被替代标准
  supersededDate?: string   // 替代日期
  scope: string            // 适用范围
  pollutants: string[]      // 控制污染物
  url?: string             // 官方链接
}

// 内置标准数据库（高频标准，支持离线校验）
export const StandardsDatabase: Record<string, StandardInfo> = {
  // ===== 大气污染物排放标准 =====
  "GB 16297-1996": {
    code: "GB 16297-1996", name: "大气污染物综合排放标准",
    category: "national", status: "superseded",
    effectiveDate: "1997-01-01", supersededBy: "各行业排放标准",
    supersededDate: "2015-01-01", scope: "通用",
    pollutants: ["SO2", "NOx", "颗粒物", "VOCs"]
  },
  "GB 13271-2001": {
    code: "GB 13271-2001", name: "锅炉大气污染物排放标准",
    category: "national", status: "expired",
    effectiveDate: "2002-01-01", supersededBy: "GB 13271-2014",
    supersededDate: "2014-07-01", scope: "锅炉",
    pollutants: ["SO2", "NOx", "颗粒物", "汞"]
  },
  "GB 13271-2014": {
    code: "GB 13271-2014", name: "锅炉大气污染物排放标准",
    category: "national", status: "superseded",
    effectiveDate: "2014-07-01", supersededBy: "GB 13271-2023",
    supersededDate: "2023-01-01", scope: "锅炉",
    pollutants: ["SO2", "NOx", "颗粒物", "汞"]
  },
  "GB 13271-2023": {
    code: "GB 13271-2023", name: "锅炉大气污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2023-01-01", scope: "锅炉",
    pollutants: ["SO2", "NOx", "颗粒物", "汞", "CO"]
  },
  "GB 13223-2011": {
    code: "GB 13223-2011", name: "火电厂大气污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2012-01-01", scope: "火电厂",
    pollutants: ["SO2", "NOx", "颗粒物", "汞及其化合物"]
  },
  "GB 4915-2013": {
    code: "GB 4915-2013", name: "水泥工业大气污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2014-03-01", scope: "水泥工业",
    pollutants: ["SO2", "NOx", "颗粒物", "氨", "氟化物"]
  },
  "GB 28663-2012": {
    code: "GB 28663-2012", name: "钢铁烧结、球团工业大气污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2012-10-01", scope: "钢铁烧结、球团",
    pollutants: ["SO2", "NOx", "颗粒物", "二噁英", "氟化物"]
  },
  "GB 16171-2012": {
    code: "GB 16171-2012", name: "炼焦化学工业污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2012-10-01", scope: "炼焦化学工业",
    pollutants: ["SO2", "NOx", "颗粒物", "苯并[a]芘", "酚类", "氰化物"]
  },
  "GB 31571-2015": {
    code: "GB 31571-2015", name: "石油化学工业污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2015-07-01", scope: "石油化学工业",
    pollutants: ["VOCs", "SO2", "NOx", "颗粒物", "COD", "氨氮", "石油类"]
  },
  "GB 37822-2019": {
    code: "GB 37822-2019", name: "挥发性有机物无组织排放控制标准",
    category: "national", status: "active",
    effectiveDate: "2020-07-01", scope: "VOCs排放企业",
    pollutants: ["VOCs", "NMHC", "TVOC"]
  },
  "GB 37823-2019": {
    code: "GB 37823-2019", name: "制药工业大气污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2020-07-01", scope: "制药工业",
    pollutants: ["VOCs", "NMHC", "TVOC", "特征污染物"]
  },
  "GB 39731-2020": {
    code: "GB 39731-2020", name: "电子工业水污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2021-01-01", scope: "电子工业",
    pollutants: ["COD", "氨氮", "总氮", "总磷", "重金属", "氟化物"]
  },
  "GB 25465-2010": {
    code: "GB 25465-2010", name: "铝工业污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2010-10-01", scope: "铝工业",
    pollutants: ["SO2", "NOx", "颗粒物", "氟化物", "COD", "氨氮"]
  },
  "GB 25467-2010": {
    code: "GB 25467-2010", name: "铜、镍、钴工业污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2010-10-01", scope: "铜、镍、钴工业",
    pollutants: ["SO2", "NOx", "颗粒物", "重金属", "COD", "氨氮"]
  },
  "GB 26453-2011": {
    code: "GB 26453-2011", name: "平板玻璃工业大气污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2011-10-01", scope: "平板玻璃工业",
    pollutants: ["SO2", "NOx", "颗粒物", "氟化物"]
  },
  "GB 18485-2014": {
    code: "GB 18485-2014", name: "生活垃圾焚烧污染控制标准",
    category: "national", status: "active",
    effectiveDate: "2014-07-01", scope: "生活垃圾焚烧",
    pollutants: ["SO2", "NOx", "颗粒物", "HCl", "CO", "二噁英", "重金属"]
  },
  "GB 18484-2020": {
    code: "GB 18484-2020", name: "危险废物焚烧污染控制标准",
    category: "national", status: "active",
    effectiveDate: "2021-01-01", scope: "危险废物焚烧",
    pollutants: ["SO2", "NOx", "颗粒物", "HCl", "CO", "二噁英", "重金属", "HF"]
  },
  "GB 16889-2008": {
    code: "GB 16889-2008", name: "生活垃圾填埋场污染控制标准",
    category: "national", status: "active",
    effectiveDate: "2008-07-01", scope: "生活垃圾填埋",
    pollutants: ["COD", "BOD5", "氨氮", "总氮", "总磷", "重金属", "甲烷"]
  },
  "GB 18597-2023": {
    code: "GB 18597-2023", name: "危险废物贮存污染控制标准",
    category: "national", status: "active",
    effectiveDate: "2023-07-01", scope: "危险废物贮存",
    pollutants: ["VOCs", "渗滤液", "重金属"]
  },

  // ===== 水污染物排放标准 =====
  "GB 8978-1996": {
    code: "GB 8978-1996", name: "污水综合排放标准",
    category: "national", status: "superseded",
    effectiveDate: "1998-01-01", supersededBy: "各行业排放标准",
    supersededDate: "2015-01-01", scope: "通用",
    pollutants: ["COD", "BOD5", "SS", "氨氮", "石油类", "重金属"]
  },
  "GB 18918-2002": {
    code: "GB 18918-2002", name: "城镇污水处理厂污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2003-07-01", scope: "城镇污水处理厂",
    pollutants: ["COD", "BOD5", "SS", "氨氮", "总氮", "总磷", "粪大肠菌群"]
  },
  "GB 3544-2008": {
    code: "GB 3544-2008", name: "制浆造纸工业水污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2008-08-01", scope: "制浆造纸工业",
    pollutants: ["COD", "BOD5", "SS", "氨氮", "AOX", "二噁英"]
  },
  "GB 4287-2012": {
    code: "GB 4287-2012", name: "纺织染整工业水污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2013-01-01", scope: "纺织染整工业",
    pollutants: ["COD", "BOD5", "SS", "氨氮", "色度", "总氮", "总磷"]
  },
  "GB 21903-2008": {
    code: "GB 21903-2008", name: "发酵类制药工业水污染物排放标准",
    category: "national", status: "active",
    effectiveDate: "2008-08-01", scope: "发酵类制药工业",
    pollutants: ["COD", "BOD5", "SS", "氨氮", "总氮", "总磷"]
  },

  // ===== 噪声/振动标准 =====
  "GB 12348-2008": {
    code: "GB 12348-2008", name: "工业企业厂界环境噪声排放标准",
    category: "national", status: "active",
    effectiveDate: "2008-10-01", scope: "工业企业",
    pollutants: ["等效声级", "夜间频发/偶发噪声"]
  },
  "GB 12523-2011": {
    code: "GB 12523-2011", name: "建筑施工场界环境噪声排放标准",
    category: "national", status: "active",
    effectiveDate: "2012-07-01", scope: "建筑施工",
    pollutants: ["等效声级"]
  },

  // ===== 固废标准 =====
  "GB 18599-2020": {
    code: "GB 18599-2020", name: "一般工业固体废物贮存和填埋污染控制标准",
    category: "national", status: "active",
    effectiveDate: "2021-01-01", scope: "一般工业固废",
    pollutants: ["渗滤液", "颗粒物", "甲烷"]
  },

  // ===== 地方标准（示例） =====
  "DB33/2146-2018": {
    code: "DB33/2146-2018", name: "工业涂装工序大气污染物排放标准",
    category: "local", status: "active",
    effectiveDate: "2018-11-01", scope: "浙江省工业涂装",
    pollutants: ["VOCs", "苯系物", "颗粒物"]
  }
}

export class StandardsAPI {
  private cache: Map<string, StandardInfo> = new Map()
  private apiEndpoint: string = "https://api.mee.gov.cn/standards"  // 生态环境部标准库API（示例）
  private offlineMode: boolean = true  // 默认离线模式

  constructor(options?: { offline?: boolean; apiEndpoint?: string }) {
    if (options) {
      this.offlineMode = options.offline !== false
      if (options.apiEndpoint) this.apiEndpoint = options.apiEndpoint
    }
    // 预加载内置数据库到缓存
    Object.entries(StandardsDatabase).forEach(([code, info]) => {
      this.cache.set(code, info)
    })
  }

  async checkValidity(code: string): Promise<StandardInfo | null> {
    // 1. 先查缓存
    if (this.cache.has(code)) {
      return this.cache.get(code)!
    }

    // 2. 离线模式直接返回未知
    if (this.offlineMode) {
      return {
        code, name: "未知标准", category: "national", status: "unknown",
        effectiveDate: "", scope: "", pollutants: []
      }
    }

    // 3. 在线查询（实际项目中实现）
    try {
      const response = await fetch(`${this.apiEndpoint}/query?code=${encodeURIComponent(code)}`)
      if (response.ok) {
        const data = await response.json()
        this.cache.set(code, data)
        return data
      }
    } catch (e) {
      console.warn(`[StandardsAPI] 在线查询失败: ${code}`, e)
    }

    return null
  }

  async batchCheck(codes: string[]): Promise<Record<string, StandardInfo | null>> {
    const results: Record<string, StandardInfo | null> = {}
    await Promise.all(codes.map(async code => {
      results[code] = await this.checkValidity(code)
    }))
    return results
  }

  isExpired(code: string): boolean {
    const info = this.cache.get(code)
    if (!info) return false  // 未知标准不判定为过期
    return info.status === "expired" || info.status === "superseded"
  }

  isActive(code: string): boolean {
    const info = this.cache.get(code)
    return info ? info.status === "active" : false
  }

  getSupersededBy(code: string): string | undefined {
    const info = this.cache.get(code)
    return info?.supersededBy
  }

  getRecommendedReplacement(code: string): string | undefined {
    const info = this.cache.get(code)
    if (info?.supersededBy) {
      // 查找替代标准的详细信息
      return info.supersededBy
    }
    return undefined
  }

  findApplicableStandards(industryCode: string, pollutantType: string): StandardInfo[] {
    // 根据行业代码和污染物类型推荐适用标准
    const results: StandardInfo[] = []
    for (const info of this.cache.values()) {
      if (info.status !== "active") continue
      // 简化匹配逻辑，实际应更精确
      if (pollutantType === "water" && info.code.startsWith("GB 3") || info.code === "GB 18918-2002") {
        results.push(info)
      }
      if (pollutantType === "air" && (info.code.startsWith("GB 1") || info.code.startsWith("GB 3") || info.code.startsWith("GB 4"))) {
        results.push(info)
      }
    }
    return results
  }

  listExpired(): StandardInfo[] {
    return Array.from(this.cache.values()).filter(s => s.status === "expired" || s.status === "superseded")
  }

  listActive(): StandardInfo[] {
    return Array.from(this.cache.values()).filter(s => s.status === "active")
  }

  getStats(): { total: number; active: number; expired: number; unknown: number } {
    const all = Array.from(this.cache.values())
    return {
      total: all.length,
      active: all.filter(s => s.status === "active").length,
      expired: all.filter(s => s.status === "expired" || s.status === "superseded").length,
      unknown: all.filter(s => s.status === "unknown").length
    }
  }
}

export default StandardsAPI
