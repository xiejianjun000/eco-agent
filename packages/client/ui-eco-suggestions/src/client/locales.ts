/** Locale bundles for the eco suggestion cards below the composer. */

/** Locale keys this surface renders. */
export type SuggestionKey =
  | 'heading' | 'elements'
  | 'role.enterprise' | 'role.enforcement' | 'role.inspection'
  | 'role.approval' | 'role.research' | 'role.training'
  | 'prompt.enterprise' | 'prompt.enforcement' | 'prompt.inspection'
  | 'prompt.approval' | 'prompt.research' | 'prompt.training'
  | 'copy.label' | 'copy.done' | 'copy.failed'

/** Namespace the dictionaries register under. */
export const NS = 'eco.suggestions'

/** English copy. */
export const en: Record<SuggestionKey, string> = {
  heading: 'Start with a professional role',
  elements: 'Covers water · air · soil · solid waste & chemicals · nuclear & radiation · EIA · discharge permits · monitoring · natural ecology · oceans · climate · inspection',
  'role.enterprise': 'Enterprise compliance',
  'role.enforcement': 'Enforcement',
  'role.inspection': 'Inspection',
  'role.approval': 'Permit approval',
  'role.research': 'Research',
  'role.training': 'Training',
  'prompt.enterprise': '以企业合规身份，帮我检查排污许可、执行报告、自行监测和台账的合规情况。',
  'prompt.enforcement': '以执法办案身份，帮我评查案卷、梳理证据链、核对法条适用。',
  'prompt.inspection': '以督察检查身份，帮我列出检查要点、问题清单和整改跟踪。',
  'prompt.approval': '以许可审批身份，帮我审核许可申请、核查技术要件。',
  'prompt.research': '以科研分析身份，帮我做数据建模、趋势研判和报告撰写。',
  'prompt.training': '以学习培训身份，帮我解读法规、讲解标准、学习案例。',
  'copy.label': 'Copy this sample question',
  'copy.done': 'Copied',
  'copy.failed': 'Copy failed — select the text manually',
}

/** Simplified Chinese copy. */
export const zh: Record<SuggestionKey, string> = {
  heading: '选择你的专业身份开始',
  elements: '覆盖 水 · 大气 · 土壤 · 固废与化学品 · 核与辐射 · 环评 · 排污许可 · 监测 · 自然生态 · 海洋 · 气候变化 · 督察',
  'role.enterprise': '企业合规',
  'role.enforcement': '执法办案',
  'role.inspection': '督察检查',
  'role.approval': '许可审批',
  'role.research': '科研分析',
  'role.training': '学习培训',
  'prompt.enterprise': '以企业合规身份，帮我检查排污许可、执行报告、自行监测和台账的合规情况。',
  'prompt.enforcement': '以执法办案身份，帮我评查案卷、梳理证据链、核对法条适用。',
  'prompt.inspection': '以督察检查身份，帮我列出检查要点、问题清单和整改跟踪。',
  'prompt.approval': '以许可审批身份，帮我审核许可申请、核查技术要件。',
  'prompt.research': '以科研分析身份，帮我做数据建模、趋势研判和报告撰写。',
  'prompt.training': '以学习培训身份，帮我解读法规、讲解标准、学习案例。',
  'copy.label': '复制这条示例问题',
  'copy.done': '已复制',
  'copy.failed': '复制失败，请手动选择文本',
}
