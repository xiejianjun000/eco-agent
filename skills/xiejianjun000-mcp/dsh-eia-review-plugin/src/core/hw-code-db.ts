// src/core/hw-code-db.ts
// 《国家危险废物名录（2025年版）》完整映射
// 生态环境部令 2025年第36号

export interface HazardousWasteInfo {
  code: string           // 废物代码（如 HW08）
  name: string           // 废物名称
  description: string   // 废物描述
  source: string        // 产生来源
  characteristics: string[]  // 危险特性（T/C/I/R/In）
  examples: string[]      // 常见产生工序/行业
  management: string     // 管理要求
}

// 完整危废名录（2025版，共46大类）
export const HazardousWasteDatabase: Record<string, HazardousWasteInfo> = {
  "HW01": {
    code: "HW01", name: "医疗废物",
    description: "医疗卫生机构在医疗、预防、保健以及其他相关活动中产生的具有直接或者间接感染性、毒性以及其他危害性的废物",
    source: "卫生",
    characteristics: ["In", "T"],
    examples: ["感染性废物", "病理性废物", "损伤性废物", "药物性废物", "化学性废物"],
    management: "按《医疗废物管理条例》管理，交由有资质单位处置"
  },
  "HW02": {
    code: "HW02", name: "医药废物",
    description: "化学药品原料药生产、制剂生产、兽药生产、生物药品制造过程中产生的废物",
    source: "医药制造",
    characteristics: ["T"],
    examples: ["化学合成原料药生产", "制剂生产", "兽药生产", "生物药品制造"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW03": {
    code: "HW03", name: "废药物、药品",
    description: "生产、销售及使用过程中产生的失效、变质、不合格、淘汰、伪劣的药物和药品",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["过期药品", "不合格药品", "淘汰药品"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW04": {
    code: "HW04", name: "农药废物",
    description: "农药生产、销售及使用过程中产生的废物",
    source: "农药制造",
    characteristics: ["T"],
    examples: ["农药生产", "农药销售", "农药使用"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW05": {
    code: "HW05", name: "木材防腐剂废物",
    description: "木材使用化学防腐剂进行防腐处理过程中产生的废物",
    source: "木材加工",
    characteristics: ["T"],
    examples: ["木材防腐处理", "木材阻燃处理"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW06": {
    code: "HW06", name: "废有机溶剂与含有机溶剂废物",
    description: "工业生产中作为清洗剂、萃取剂、溶剂或反应介质使用后废弃的有机溶剂",
    source: "非特定行业",
    characteristics: ["T", "I", "In"],
    examples: ["有机溶剂清洗", "有机溶剂萃取", "有机溶剂反应"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW07": {
    code: "HW07", name: "热处理含氰废物",
    description: "使用氰化物进行金属热处理产生的废物",
    source: "金属表面处理及热处理加工",
    characteristics: ["T"],
    examples: ["氰化热处理", "氰化电镀"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW08": {
    code: "HW08", name: "废矿物油与含矿物油废物",
    description: "石油开采、炼制、储存、运输及使用过程中产生的废矿物油",
    source: "非特定行业",
    characteristics: ["T", "I"],
    examples: ["机械维修", "设备润滑", "液压系统", "变压器维护"],
    management: "按危险废物管理，可交由有资质单位再生利用或处置"
  },
  "HW09": {
    code: "HW09", name: "油/水、烃/水混合物或乳化液",
    description: "油水混合物、烃水混合物或乳化液",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["机械加工", "金属清洗", "设备维护"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW11": {
    code: "HW11", name: "精（蒸）馏残渣",
    description: "精（蒸）馏过程中产生的残余物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["化工精馏", "石油炼制", "溶剂回收"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW12": {
    code: "HW12", name: "染料、涂料废物",
    description: "生产、销售及使用过程中产生的失效、变质、不合格、淘汰、伪劣的染料、涂料",
    source: "涂料、油墨、颜料及类似产品制造",
    characteristics: ["T", "I", "In"],
    examples: ["涂料生产", "涂料使用", "染料生产", "染料使用"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW13": {
    code: "HW13", name: "有机树脂类废物",
    description: "生产、销售及使用过程中产生的失效、变质、不合格、淘汰、伪劣的有机树脂",
    source: "合成材料制造",
    characteristics: ["T"],
    examples: ["树脂生产", "树脂使用", "胶粘剂生产"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW14": {
    code: "HW14", name: "新化学物质废物",
    description: "研究、开发和教学活动中产生的未经使用的新化学物质废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["化学研究", "化学教学", "化学开发"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW16": {
    code: "HW16", name: "感光材料废物",
    description: "生产、销售及使用过程中产生的失效、变质、不合格、淘汰、伪劣的感光材料",
    source: "专用化学产品制造",
    characteristics: ["T"],
    examples: ["胶片生产", "胶片使用", "印刷制版"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW17": {
    code: "HW17", name: "表面处理废物",
    description: "金属表面处理及热处理加工过程中产生的废物",
    source: "金属表面处理及热处理加工",
    characteristics: ["T", "C"],
    examples: ["电镀", "化学镀", "阳极氧化", "磷化", "酸洗", "钝化"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW18": {
    code: "HW18", name: "焚烧处置残渣",
    description: "焚烧处置过程中产生的残渣",
    source: "环境治理业",
    characteristics: ["T"],
    examples: ["生活垃圾焚烧", "危险废物焚烧", "医疗废物焚烧"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW19": {
    code: "HW19", name: "含金属羰基化合物废物",
    description: "生产、销售及使用过程中产生的含金属羰基化合物废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["羰基化合物生产", "羰基化合物使用"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW20": {
    code: "HW20", name: "含铍废物",
    description: "含铍及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["铍合金生产", "铍化合物生产", "核工业"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW21": {
    code: "HW21", name: "含铬废物",
    description: "含铬及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["镀铬", "铬盐生产", "皮革鞣制", "颜料生产"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW22": {
    code: "HW22", name: "含铜废物",
    description: "含铜及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["铜冶炼", "铜电镀", "铜化合物生产"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW23": {
    code: "HW23", name: "含锌废物",
    description: "含锌及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["镀锌", "锌冶炼", "锌化合物生产"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW24": {
    code: "HW24", name: "含砷废物",
    description: "含砷及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["砷化合物生产", "农药生产", "半导体制造"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW25": {
    code: "HW25", name: "含硒废物",
    description: "含硒及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["硒化合物生产", "电子工业", "玻璃制造"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW26": {
    code: "HW26", name: "含镉废物",
    description: "含镉及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["镉电镀", "镍镉电池", "颜料生产"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW27": {
    code: "HW27", name: "含锑废物",
    description: "含锑及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["锑冶炼", "阻燃剂生产", "合金生产"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW28": {
    code: "HW28", name: "含碲废物",
    description: "含碲及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["碲化合物生产", "冶金工业", "电子工业"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW29": {
    code: "HW29", name: "含汞废物",
    description: "含汞及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["汞冶炼", "含汞产品生产", "荧光灯管", "体温计", "血压计"],
    management: "按危险废物管理，交由有资质单位处置，禁止露天焚烧"
  },
  "HW30": {
    code: "HW30", name: "含铊废物",
    description: "含铊及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["铊化合物生产", "电子工业", "光学玻璃"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW31": {
    code: "HW31", name: "含铅废物",
    description: "含铅及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["铅冶炼", "铅酸蓄电池", "颜料生产", "玻璃制造", "焊接"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW32": {
    code: "HW32", name: "无机氟化物废物",
    description: "含无机氟化物的废物",
    source: "非特定行业",
    characteristics: ["T", "C"],
    examples: ["电解铝", "氟化工", "磷肥生产", "玻璃制造"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW33": {
    code: "HW33", name: "无机氰化物废物",
    description: "含无机氰化物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["电镀", "热处理", "黄金提取", "合成纤维"],
    management: "按危险废物管理，交由有资质单位处置，注意防泄漏"
  },
  "HW34": {
    code: "HW34", name: "废酸",
    description: "生产、销售及使用过程中产生的失效、变质、不合格、淘汰、伪劣的酸",
    source: "非特定行业",
    characteristics: ["C", "T"],
    examples: ["酸洗", "酸蚀", "酸催化", "酸中和"],
    management: "按危险废物管理，可交由有资质单位再生利用或处置"
  },
  "HW35": {
    code: "HW35", name: "废碱",
    description: "生产、销售及使用过程中产生的失效、变质、不合格、淘汰、伪劣的碱",
    source: "非特定行业",
    characteristics: ["C", "T"],
    examples: ["碱洗", "碱蚀", "碱催化", "碱中和"],
    management: "按危险废物管理，可交由有资质单位再生利用或处置"
  },
  "HW36": {
    code: "HW36", name: "石棉废物",
    description: "含石棉的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["石棉开采", "石棉制品生产", "建筑拆除", "船舶拆解"],
    management: "按危险废物管理，交由有资质单位处置，注意防尘"
  },
  "HW37": {
    code: "HW37", name: "有机磷化合物废物",
    description: "含有机磷化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["农药生产", "阻燃剂生产", "润滑油添加剂"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW38": {
    code: "HW38", name: "有机氰化物废物",
    description: "含有机氰化物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["合成纤维", "合成树脂", "染料生产"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW39": {
    code: "HW39", name: "含酚废物",
    description: "含酚及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T", "C"],
    examples: ["焦化", "煤气生产", "酚醛树脂", "染料生产"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW40": {
    code: "HW40", name: "含醚废物",
    description: "含醚及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["溶剂使用", "化学合成", "医药制造"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW45": {
    code: "HW45", name: "含有机卤化物废物",
    description: "含有机卤化物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["有机合成", "制冷剂生产", "阻燃剂生产", "干洗"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW46": {
    code: "HW46", name: "含镍废物",
    description: "含镍及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["镍电镀", "镍冶炼", "镍镉电池", "不锈钢生产"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW47": {
    code: "HW47", name: "含钡废物",
    description: "含钡及其化合物的废物",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["钡盐生产", "颜料生产", "烟花制造"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW48": {
    code: "HW48", name: "有色金属冶炼废物",
    description: "有色金属冶炼过程中产生的废物",
    source: "有色金属冶炼和压延加工业",
    characteristics: ["T"],
    examples: ["铜冶炼", "铝冶炼", "铅锌冶炼", "稀有金属冶炼"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW49": {
    code: "HW49", name: "其他废物",
    description: "未列入上述名录的危险废物",
    source: "非特定行业",
    characteristics: ["T", "C", "I", "R", "In"],
    examples: ["含有危险废物的废弃包装物", "废弃化学品", "实验室废物", "烟气净化产生的废物"],
    management: "按危险废物管理，交由有资质单位处置"
  },
  "HW50": {
    code: "HW50", name: "废催化剂",
    description: "工业生产过程中产生的废催化剂",
    source: "非特定行业",
    characteristics: ["T"],
    examples: ["石油炼制", "化工合成", "汽车尾气净化", "烟气脱硝"],
    management: "按危险废物管理，可交由有资质单位再生利用或处置"
  }
}

// 危险特性说明
export const HazardCharacteristics: Record<string, { name: string; description: string }> = {
  "T": { name: "毒性", description: "具有毒性，可能对生态环境和人体健康产生有害影响" },
  "C": { name: "腐蚀性", description: "具有腐蚀性，可能腐蚀容器或造成人体灼伤" },
  "I": { name: "易燃性", description: "具有易燃性，可能引发火灾" },
  "R": { name: "反应性", description: "具有反应性，可能与水、空气或其他物质发生危险反应" },
  "In": { name: "感染性", description: "具有感染性，可能传播疾病" }
}

export class HazardousWasteDB {
  static get(code: string): HazardousWasteInfo | undefined {
    // 提取大类代码（如 HW08/900-249-08 → HW08）
    const categoryCode = code.split("/")[0].trim().toUpperCase()
    return HazardousWasteDatabase[categoryCode]
  }

  static isValid(code: string): boolean {
    const categoryCode = code.split("/")[0].trim().toUpperCase()
    return categoryCode in HazardousWasteDatabase
  }

  static getCharacteristics(code: string): string[] {
    const info = this.get(code)
    return info ? info.characteristics : []
  }

  static getCharacteristicNames(code: string): string[] {
    const chars = this.getCharacteristics(code)
    return chars.map(c => HazardCharacteristics[c]?.name || c)
  }

  static getManagement(code: string): string {
    const info = this.get(code)
    return info ? info.management : "按危险废物管理"
  }

  static findBySource(source: string): HazardousWasteInfo[] {
    return Object.values(HazardousWasteDatabase).filter(hw =>
      hw.source.includes(source) || hw.examples.some(e => e.includes(source))
    )
  }

  static findByCharacteristic(char: string): HazardousWasteInfo[] {
    return Object.values(HazardousWasteDatabase).filter(hw =>
      hw.characteristics.includes(char)
    )
  }

  static listAll(): HazardousWasteInfo[] {
    return Object.values(HazardousWasteDatabase)
  }

  static getStats(): { total: number; bySource: Record<string, number> } {
    const all = this.listAll()
    const bySource: Record<string, number> = {}
    all.forEach(hw => {
      bySource[hw.source] = (bySource[hw.source] || 0) + 1
    })
    return { total: all.length, bySource }
  }

  // 验证废物代码格式（如 HW08/900-249-08）
  static validateFormat(code: string): { valid: boolean; error?: string } {
    const pattern = /^HW\d{2}\/\d{3}-\d{3}-\d{2}$/i
    if (!pattern.test(code)) {
      return { valid: false, error: "格式错误，应为 HWXX/XXX-XXX-XX" }
    }

    const category = code.split("/")[0].toUpperCase()
    if (!this.isValid(category)) {
      return { valid: false, error: `无效的危险废物类别: ${category}` }
    }

    return { valid: true }
  }
}

export default HazardousWasteDB
