// src/core/industry-db.ts
// GB/T 4754-2017 国民经济行业分类 精确匹配数据库
// 用于环评分类管理名录的精确判定

export interface IndustryInfo {
  code: string           // 4位行业代码
  name: string           // 行业名称
  category: string       // 大类
  eiaType: "report_book" | "report_table" | "registration" | "exemption"
  permitType: "key_management" | "simplified" | "registration" | "exemption"
  keyPollutants: string[]
  specialRequirements: string[]  // 特殊审批要求
  applicableStandards: string[] // 常用排放标准
  isKeyIndustry: boolean        // 是否重点监管行业
  isNewPollutantIndustry: boolean // 是否新污染物重点行业
  isTwoHigh: boolean            // 是否两高行业
}

// 核心行业分类数据（精选高频行业，实际生产环境应加载完整数据库）
export const IndustryDatabase: Record<string, IndustryInfo> = {
  // ===== 化学原料和化学制品制造业 (C26) =====
  "C2611": {
    code: "C2611", name: "无机酸制造", category: "C26",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["SO2", "NOx", "硫酸雾", "氟化物", "COD", "氨氮"],
    specialRequirements: ["重点行业环评审批原则", "产能置换"],
    applicableStandards: ["GB 31571-2015", "GB 13271-2014", "GB 8978-1996"],
    isKeyIndustry: true, isNewPollutantIndustry: true, isTwoHigh: true
  },
  "C2612": {
    code: "C2612", name: "无机碱制造", category: "C26",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["氨", "氯气", "COD", "氨氮", "SS", "TDS"],
    specialRequirements: ["重点行业环评审批原则", "产能置换"],
    applicableStandards: ["GB 31571-2015", "GB 13271-2014"],
    isKeyIndustry: true, isNewPollutantIndustry: true, isTwoHigh: true
  },
  "C2613": {
    code: "C2613", name: "无机盐制造", category: "C26",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["颗粒物", "氟化物", "COD", "氨氮", "重金属"],
    specialRequirements: ["重点行业环评审批原则"],
    applicableStandards: ["GB 31571-2015"],
    isKeyIndustry: true, isNewPollutantIndustry: true, isTwoHigh: true
  },
  "C2614": {
    code: "C2614", name: "有机化学原料制造", category: "C26",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["VOCs", "苯系物", "COD", "氨氮", "特征污染物"],
    specialRequirements: ["重点行业环评审批原则", "新污染物专项分析", "VOCs总量替代"],
    applicableStandards: ["GB 31571-2015", "GB 37822-2019", "GB 8978-1996"],
    isKeyIndustry: true, isNewPollutantIndustry: true, isTwoHigh: true
  },
  "C2619": {
    code: "C2619", name: "其他基础化学原料制造", category: "C26",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["VOCs", "颗粒物", "COD", "氨氮"],
    specialRequirements: ["重点行业环评审批原则"],
    applicableStandards: ["GB 31571-2015"],
    isKeyIndustry: true, isNewPollutantIndustry: true, isTwoHigh: true
  },
  "C2621": {
    code: "C2621", name: "氮肥制造", category: "C26",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["氨", "NOx", "COD", "氨氮", "TDS"],
    specialRequirements: ["重点行业环评审批原则", "产能置换"],
    applicableStandards: ["GB 31571-2015", "GB 13271-2014"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },
  "C2622": {
    code: "C2622", name: "磷肥制造", category: "C26",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["氟化物", "颗粒物", "COD", "总磷", "重金属"],
    specialRequirements: ["重点行业环评审批原则"],
    applicableStandards: ["GB 31571-2015"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },
  "C2625": {
    code: "C2625", name: "有机肥料及微生物肥料制造", category: "C26",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["颗粒物", "COD", "氨氮", "臭气浓度"],
    specialRequirements: [],
    applicableStandards: ["GB 16297-1996", "GB 8978-1996"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },
  "C2631": {
    code: "C2631", name: "化学农药制造", category: "C26",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["VOCs", "农药成分", "COD", "氨氮", "特征污染物"],
    specialRequirements: ["重点行业环评审批原则", "新污染物专项分析", "农药产业政策"],
    applicableStandards: ["GB 31571-2015", "GB 37822-2019"],
    isKeyIndustry: true, isNewPollutantIndustry: true, isTwoHigh: true
  },
  "C2641": {
    code: "C2641", name: "涂料制造", category: "C26",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["VOCs", "苯系物", "颗粒物", "COD"],
    specialRequirements: ["VOCs总量替代", "低VOCs含量涂料推广"],
    applicableStandards: ["GB 37822-2019", "GB 31571-2015"],
    isKeyIndustry: true, isNewPollutantIndustry: true, isTwoHigh: false
  },
  "C2651": {
    code: "C2651", name: "初级形态塑料及合成树脂制造", category: "C26",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["VOCs", "颗粒物", "COD", "氨氮", "特征污染物"],
    specialRequirements: ["重点行业环评审批原则", "产能置换"],
    applicableStandards: ["GB 31571-2015", "GB 37822-2019"],
    isKeyIndustry: true, isNewPollutantIndustry: true, isTwoHigh: true
  },
  "C2661": {
    code: "C2661", name: "化学试剂和助剂制造", category: "C26",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["VOCs", "COD", "氨氮"],
    specialRequirements: [],
    applicableStandards: ["GB 31571-2015", "GB 37822-2019"],
    isKeyIndustry: false, isNewPollutantIndustry: true, isTwoHigh: false
  },
  "C2662": {
    code: "C2662", name: "专项化学用品制造", category: "C26",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["VOCs", "COD", "氨氮"],
    specialRequirements: [],
    applicableStandards: ["GB 31571-2015"],
    isKeyIndustry: false, isNewPollutantIndustry: true, isTwoHigh: false
  },

  // ===== 医药制造业 (C27) =====
  "C2710": {
    code: "C2710", name: "化学药品原料药制造", category: "C27",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["VOCs", "抗生素", "COD", "氨氮", "特征污染物"],
    specialRequirements: ["重点行业环评审批原则", "新污染物专项分析", "制药工业水污染物排放标准"],
    applicableStandards: ["GB 31571-2015", "GB 37822-2019", "GB 21903-2008"],
    isKeyIndustry: true, isNewPollutantIndustry: true, isTwoHigh: false
  },
  "C2720": {
    code: "C2720", name: "化学药品制剂制造", category: "C27",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["VOCs", "颗粒物", "COD", "氨氮"],
    specialRequirements: ["制药工业大气污染物排放标准"],
    applicableStandards: ["GB 37823-2019", "GB 21903-2008"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },
  "C2730": {
    code: "C2730", name: "中药饮片加工", category: "C27",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["颗粒物", "COD", "氨氮", "药渣"],
    specialRequirements: [],
    applicableStandards: ["GB 16297-1996", "GB 8978-1996"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },

  // ===== 石油、煤炭及其他燃料加工业 (C25) =====
  "C2511": {
    code: "C2511", name: "原油加工及石油制品制造", category: "C25",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["VOCs", "SO2", "NOx", "颗粒物", "COD", "石油类"],
    specialRequirements: ["重点行业环评审批原则", "产能置换", "炼油行业绿色创新高质量发展"],
    applicableStandards: ["GB 31571-2015", "GB 13271-2014", "GB 8978-1996"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },
  "C2520": {
    code: "C2520", name: "炼焦", category: "C25",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["VOCs", "SO2", "NOx", "颗粒物", "COD", "氨氮", "苯并[a]芘"],
    specialRequirements: ["重点行业环评审批原则", "产能置换", "焦化行业超低排放"],
    applicableStandards: ["GB 16171-2012", "GB 13271-2014"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },

  // ===== 黑色金属冶炼和压延加工业 (C31) =====
  "C3110": {
    code: "C3110", name: "炼铁", category: "C31",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["SO2", "NOx", "颗粒物", "CO", "COD", "氨氮"],
    specialRequirements: ["重点行业环评审批原则", "产能置换", "钢铁行业超低排放", "碳排放评价"],
    applicableStandards: ["GB 28663-2012", "GB 13271-2014"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },
  "C3120": {
    code: "C3120", name: "炼钢", category: "C31",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["SO2", "NOx", "颗粒物", "二噁英", "COD", "氨氮"],
    specialRequirements: ["重点行业环评审批原则", "产能置换", "钢铁行业超低排放", "碳排放评价"],
    applicableStandards: ["GB 28663-2012", "GB 13271-2014"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },
  "C3130": {
    code: "C3130", name: "钢压延加工", category: "C31",
    eiaType: "report_table", permitType: "key_management",
    keyPollutants: ["颗粒物", "SO2", "NOx", "COD", "石油类"],
    specialRequirements: ["钢铁行业超低排放"],
    applicableStandards: ["GB 28663-2012"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },

  // ===== 有色金属冶炼和压延加工业 (C32) =====
  "C3211": {
    code: "C3211", name: "铜冶炼", category: "C32",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["SO2", "NOx", "颗粒物", "重金属", "COD", "氨氮"],
    specialRequirements: ["重点行业环评审批原则", "产能置换", "重金属污染防控"],
    applicableStandards: ["GB 25467-2010", "GB 13271-2014"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },
  "C3216": {
    code: "C3216", name: "铝冶炼", category: "C32",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["SO2", "NOx", "颗粒物", "氟化物", "COD", "氨氮"],
    specialRequirements: ["重点行业环评审批原则", "产能置换", "电解铝行业碳排放评价"],
    applicableStandards: ["GB 25465-2010", "GB 13271-2014"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },

  // ===== 非金属矿物制品业 (C30) =====
  "C3011": {
    code: "C3011", name: "水泥制造", category: "C30",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["SO2", "NOx", "颗粒物", "氨", "COD", "氨氮"],
    specialRequirements: ["重点行业环评审批原则", "产能置换", "水泥行业超低排放", "碳排放评价"],
    applicableStandards: ["GB 4915-2013", "GB 13271-2014"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },
  "C3041": {
    code: "C3041", name: "平板玻璃制造", category: "C30",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["SO2", "NOx", "颗粒物", "COD", "氨氮"],
    specialRequirements: ["重点行业环评审批原则", "产能置换", "玻璃行业超低排放"],
    applicableStandards: ["GB 26453-2011", "GB 13271-2014"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },
  "C3042": {
    code: "C3042", name: "特种玻璃制造", category: "C30",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["颗粒物", "SO2", "NOx", "COD"],
    specialRequirements: [],
    applicableStandards: ["GB 26453-2011"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },

  // ===== 电力、热力生产和供应业 (D44) =====
  "D4411": {
    code: "D4411", name: "火力发电", category: "D44",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["SO2", "NOx", "颗粒物", "汞及其化合物", "COD", "氨氮"],
    specialRequirements: ["重点行业环评审批原则", "火电行业温室气体排放评价", "超低排放", "碳排放评价"],
    applicableStandards: ["GB 13223-2011", "GB 13271-2014"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },
  "D4412": {
    code: "D4412", name: "热电联产", category: "D44",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["SO2", "NOx", "颗粒物", "COD", "氨氮"],
    specialRequirements: ["重点行业环评审批原则", "超低排放", "碳排放评价"],
    applicableStandards: ["GB 13223-2011", "GB 13271-2014"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },
  "D4413": {
    code: "D4413", name: "水力发电", category: "D44",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["COD", "SS", "生态影响"],
    specialRequirements: ["生态流量保障", "鱼类保护措施"],
    applicableStandards: ["GB 8978-1996"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },

  // ===== 纺织业 (C17) =====
  "C1711": {
    code: "C1711", name: "棉纺纱加工", category: "C17",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["颗粒物", "COD", "氨氮", "色度"],
    specialRequirements: [],
    applicableStandards: ["GB 4287-2012", "GB 16297-1996"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },
  "C1712": {
    code: "C1712", name: "棉织造加工", category: "C17",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["颗粒物", "COD", "氨氮"],
    specialRequirements: [],
    applicableStandards: ["GB 4287-2012"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },
  "C1751": {
    code: "C1751", name: "化纤织造加工", category: "C17",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["VOCs", "COD", "氨氮", "色度"],
    specialRequirements: ["VOCs总量替代"],
    applicableStandards: ["GB 4287-2012", "GB 37822-2019"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },
  "C1752": {
    code: "C1752", name: "化纤织物染整精加工", category: "C17",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["VOCs", "COD", "氨氮", "色度", "总氮", "总磷"],
    specialRequirements: ["印染行业准入条件", "VOCs总量替代"],
    applicableStandards: ["GB 4287-2012", "GB 37822-2019"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },

  // ===== 造纸和纸制品业 (C22) =====
  "C2211": {
    code: "C2211", name: "木竹浆制造", category: "C22",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["COD", "BOD5", "SS", "AOX", "恶臭", "SO2", "NOx"],
    specialRequirements: ["重点行业环评审批原则", "产能置换", "制浆造纸工业水污染物排放标准"],
    applicableStandards: ["GB 3544-2008", "GB 13271-2014"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },
  "C2221": {
    code: "C2221", name: "机制纸及纸板制造", category: "C22",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["COD", "BOD5", "SS", "氨氮", "总氮", "总磷"],
    specialRequirements: ["制浆造纸工业水污染物排放标准"],
    applicableStandards: ["GB 3544-2008"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: true
  },

  // ===== 食品制造业 (C14) =====
  "C1411": {
    code: "C1411", name: "糕点、面包制造", category: "C14",
    eiaType: "report_table", permitType: "registration",
    keyPollutants: ["COD", "氨氮", "SS", "油烟"],
    specialRequirements: [],
    applicableStandards: ["GB 8978-1996", "GB 18483-2001"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },
  "C1431": {
    code: "C1431", name: "米、面制品制造", category: "C14",
    eiaType: "report_table", permitType: "registration",
    keyPollutants: ["COD", "氨氮", "SS"],
    specialRequirements: [],
    applicableStandards: ["GB 8978-1996"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },

  // ===== 通用设备制造业 (C34) =====
  "C3411": {
    code: "C3411", name: "锅炉及辅助设备制造", category: "C34",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["颗粒物", "SO2", "NOx", "COD", "氨氮"],
    specialRequirements: [],
    applicableStandards: ["GB 16297-1996", "GB 8978-1996"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },
  "C3421": {
    code: "C3421", name: "金属切削机床制造", category: "C34",
    eiaType: "report_table", permitType: "registration",
    keyPollutants: ["颗粒物", "COD", "氨氮", "石油类"],
    specialRequirements: [],
    applicableStandards: ["GB 16297-1996", "GB 8978-1996"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },

  // ===== 汽车制造业 (C36) =====
  "C3611": {
    code: "C3611", name: "汽车整车制造", category: "C36",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["VOCs", "颗粒物", "SO2", "NOx", "COD", "氨氮", "石油类"],
    specialRequirements: ["涂装工序VOCs治理", "VOCs总量替代"],
    applicableStandards: ["GB 37822-2019", "GB 16297-1996", "GB 8978-1996"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: false
  },
  "C3660": {
    code: "C3660", name: "汽车零部件及配件制造", category: "C36",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["VOCs", "颗粒物", "COD", "石油类"],
    specialRequirements: ["涂装工序VOCs治理"],
    applicableStandards: ["GB 37822-2019", "GB 16297-1996"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },

  // ===== 计算机、通信和其他电子设备制造业 (C39) =====
  "C3971": {
    code: "C3971", name: "电子器件制造", category: "C39",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["VOCs", "酸碱废气", "COD", "氨氮", "重金属", "氟化物"],
    specialRequirements: ["集成电路行业环评审批原则", "电子工业水污染物排放标准"],
    applicableStandards: ["GB 37822-2019", "GB 39731-2020", "GB 8978-1996"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: false
  },
  "C3974": {
    code: "C3974", name: "显示器件制造", category: "C39",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["VOCs", "酸碱废气", "COD", "氨氮", "重金属"],
    specialRequirements: ["电子工业水污染物排放标准"],
    applicableStandards: ["GB 37822-2019", "GB 39731-2020"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: false
  },

  // ===== 废弃资源综合利用业 (C42) =====
  "C4210": {
    code: "C4210", name: "金属废料和碎屑加工处理", category: "C42",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["颗粒物", "SO2", "NOx", "COD", "石油类", "重金属"],
    specialRequirements: ["再生资源行业规范条件"],
    applicableStandards: ["GB 16297-1996", "GB 8978-1996"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },
  "C4220": {
    code: "C4220", name: "非金属废料和碎屑加工处理", category: "C42",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["颗粒物", "VOCs", "COD", "氨氮"],
    specialRequirements: ["再生资源行业规范条件"],
    applicableStandards: ["GB 16297-1996", "GB 37822-2019", "GB 8978-1996"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },

  // ===== 生态保护和环境治理业 (N77) =====
  "N7721": {
    code: "N7721", name: "水污染治理", category: "N77",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["COD", "氨氮", "总氮", "总磷", "SS", "恶臭"],
    specialRequirements: ["城镇污水处理厂污染物排放标准"],
    applicableStandards: ["GB 18918-2002"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },
  "N7722": {
    code: "N7722", name: "大气污染治理", category: "N77",
    eiaType: "report_table", permitType: "simplified",
    keyPollutants: ["颗粒物", "SO2", "NOx", "VOCs"],
    specialRequirements: [],
    applicableStandards: ["GB 16297-1996"],
    isKeyIndustry: false, isNewPollutantIndustry: false, isTwoHigh: false
  },
  "N7723": {
    code: "N7723", name: "固体废物治理", category: "N77",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["颗粒物", "SO2", "NOx", "VOCs", "二噁英", "COD", "氨氮", "重金属"],
    specialRequirements: ["危险废物经营许可证", "生活垃圾焚烧污染控制标准"],
    applicableStandards: ["GB 18485-2014", "GB 16889-2008", "GB 18484-2020"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: false
  },
  "N7724": {
    code: "N7724", name: "危险废物治理", category: "N77",
    eiaType: "report_book", permitType: "key_management",
    keyPollutants: ["颗粒物", "SO2", "NOx", "VOCs", "二噁英", "重金属", "COD", "氨氮"],
    specialRequirements: ["危险废物经营许可证", "危险废物焚烧污染控制标准"],
    applicableStandards: ["GB 18484-2020", "GB 18597-2023"],
    isKeyIndustry: true, isNewPollutantIndustry: false, isTwoHigh: false
  }
}

// 行业大类映射（用于模糊匹配）
export const IndustryCategoryMap: Record<string, { name: string; typicalCodes: string[] }> = {
  "C25": { name: "石油、煤炭及其他燃料加工业", typicalCodes: ["C2511", "C2520"] },
  "C26": { name: "化学原料和化学制品制造业", typicalCodes: ["C2611", "C2614", "C2631", "C2641", "C2651"] },
  "C27": { name: "医药制造业", typicalCodes: ["C2710", "C2720"] },
  "C30": { name: "非金属矿物制品业", typicalCodes: ["C3011", "C3041"] },
  "C31": { name: "黑色金属冶炼和压延加工业", typicalCodes: ["C3110", "C3120", "C3130"] },
  "C32": { name: "有色金属冶炼和压延加工业", typicalCodes: ["C3211", "C3216"] },
  "C34": { name: "通用设备制造业", typicalCodes: ["C3411", "C3421"] },
  "C36": { name: "汽车制造业", typicalCodes: ["C3611", "C3660"] },
  "C39": { name: "计算机、通信和其他电子设备制造业", typicalCodes: ["C3971", "C3974"] },
  "D44": { name: "电力、热力生产和供应业", typicalCodes: ["D4411", "D4412", "D4413"] },
  "N77": { name: "生态保护和环境治理业", typicalCodes: ["N7721", "N7723", "N7724"] }
}

export class IndustryDB {
  static get(code: string): IndustryInfo | undefined {
    // 精确匹配4位代码
    if (IndustryDatabase[code]) {
      return IndustryDatabase[code]
    }
    // 尝试3位代码匹配（大类）
    const categoryCode = code.substring(0, 3)
    const match = Object.keys(IndustryDatabase).find(k => k.startsWith(categoryCode))
    return match ? IndustryDatabase[match] : undefined
  }

  static getByName(name: string): IndustryInfo | undefined {
    return Object.values(IndustryDatabase).find(i => 
      i.name.includes(name) || name.includes(i.name)
    )
  }

  static isReportBookRequired(code: string): boolean {
    const info = this.get(code)
    return info ? info.eiaType === "report_book" : false
  }

  static getPermitType(code: string): string {
    const info = this.get(code)
    return info ? info.permitType : "simplified"
  }

  static getKeyPollutants(code: string): string[] {
    const info = this.get(code)
    return info ? info.keyPollutants : []
  }

  static getSpecialRequirements(code: string): string[] {
    const info = this.get(code)
    return info ? info.specialRequirements : []
  }

  static isKeyIndustry(code: string): boolean {
    const info = this.get(code)
    return info ? info.isKeyIndustry : false
  }

  static isNewPollutantIndustry(code: string): boolean {
    const info = this.get(code)
    return info ? info.isNewPollutantIndustry : false
  }

  static isTwoHigh(code: string): boolean {
    const info = this.get(code)
    return info ? info.isTwoHigh : false
  }

  static listAll(): IndustryInfo[] {
    return Object.values(IndustryDatabase)
  }

  static listByCategory(category: string): IndustryInfo[] {
    return Object.values(IndustryDatabase).filter(i => i.code.startsWith(category))
  }

  static listKeyIndustries(): IndustryInfo[] {
    return Object.values(IndustryDatabase).filter(i => i.isKeyIndustry)
  }

  static listNewPollutantIndustries(): IndustryInfo[] {
    return Object.values(IndustryDatabase).filter(i => i.isNewPollutantIndustry)
  }

  static listTwoHighIndustries(): IndustryInfo[] {
    return Object.values(IndustryDatabase).filter(i => i.isTwoHigh)
  }
}

export default IndustryDB
