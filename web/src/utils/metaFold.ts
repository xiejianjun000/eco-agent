/**
 * metaFold.ts — 过程输出语义折叠引擎
 *
 * 对标 WorkBuddy `metaFold` 机制（本机 app.asar 实读）：
 *   把「工具名 + JSON 参数」的工具视角日志，翻译成「动词 + 主题」的任务视角摘要。
 *
 * 例：
 *   折叠前 → file_read · {"path":"E:/DSH/eco-Agent/web/src/api.ts"}    analyze_document · {...}
 *   折叠后 → 查看 api.ts、分析文档、检索法规  ·  3 个工具调用 · 已完成 2.4s
 *
 * 设计原则：
 *   1. 纯函数，无 React 依赖，可独立单测；
 *   2. 全程不信任后端数据，所有用户输入经 escapeHtml 转义后才进 DOM；
 *   3. 映射未命中时降级为「执行 xxx」，永不抛错、永不丢失信息（原文仍可展开查看）。
 */

import type { TraceEvent } from '../api';

/** 语义分组（对齐 WorkBuddy group.{category} 十类） */
export type FoldCategory =
  | 'read' | 'modify' | 'command' | 'search' | 'research'
  | 'plan' | 'collab' | 'external' | 'diagnostics' | 'other';

/** 单个工具调用的语义化描述 */
export interface ToolSemantic {
  /** 原始工具名（展开时仍需展示） */
  raw: string;
  /** 语义化动作动词，如「读取」「检索」「生成」 */
  verb: string;
  /** 中文工具名（P1 工具名本地化，同一张表顺带产出） */
  cn: string;
  /** 语义分组 */
  category: FoldCategory;
  /** 主题宾语，如 api.ts / 空气质量 / 冷水江 */
  topic: string;
  /** 该调用耗时（ms） */
  costMs?: number;
  /** 是否出错 */
  error: boolean;
}

/** 一轮（round / turn）的折叠摘要 */
export interface TurnFold {
  round: number;
  tools: ToolSemantic[];
  /** 本轮是否有思考事件 */
  thinking: boolean;
  toolCount: number;
  errorCount: number;
  totalMs: number;
  /** 按语义分组聚合后的短语，已按出现顺序去重 */
  phrases: string[];
  /** 参与语义分组的数量 */
  categoryCount: number;
}

/* ────────────────────────────────────────────────────────────
 * 1. 工具名 → （动词 / 语义分组）映射
 *    数据来源：agent_core/tools_registry.py 实读（108 个领域工具）
 *    + agent_core/exec_tools.py 内置工具（file_* / shell_run / web_*）
 *    + agent_core/mcp_connector.py 外部 MCP（ehs_kb / govmcp / tencent_docs）
 * ──────────────────────────────────────────────────────────── */

interface ToolRule {
  verb: string;
  category: FoldCategory;
  /** 完整中文工具名（P1 本地化）；省略时取 verb（verb 已含宾语） */
  cn?: string;
}

/** 精确映射：高频 + 语义无法靠前缀推断的工具 */
const EXACT_RULES: Record<string, ToolRule> = {
  // ── 内置文件 / 命令 / 网络 ──
  file_read: { verb: '读取', category: 'read', cn: '读取文件' },
  read_file: { verb: '读取', category: 'read', cn: '读取文件' },
  file_write: { verb: '写入', category: 'modify', cn: '写入文件' },
  write_file: { verb: '写入', category: 'modify', cn: '写入文件' },
  file_edit: { verb: '修改', category: 'modify', cn: '修改文件' },
  edit_file: { verb: '修改', category: 'modify', cn: '修改文件' },
  file_append: { verb: '追加内容到', category: 'modify', cn: '追加内容到文件' },
  file_delete: { verb: '删除', category: 'modify', cn: '删除文件' },
  file_list: { verb: '查看文件列表', category: 'read', cn: '查看文件列表' },
  list_files: { verb: '查看文件列表', category: 'read', cn: '查看文件列表' },
  shell_run: { verb: '运行命令', category: 'command', cn: '运行命令' },
  run_command: { verb: '运行命令', category: 'command', cn: '运行命令' },
  execute_code: { verb: '执行代码', category: 'command', cn: '执行代码' },
  python_exec: { verb: '执行代码', category: 'command', cn: '执行代码' },
  web_search: { verb: '搜索资料', category: 'research', cn: '搜索资料' },
  web_fetch: { verb: '读取网页', category: 'research', cn: '读取网页' },
  http_request: { verb: '请求接口', category: 'external', cn: '请求接口' },
  memory_search: { verb: '检索记忆', category: 'search', cn: '检索记忆' },
  rag_search: { verb: '检索知识库', category: 'search', cn: '检索知识库' },
  save_document: { verb: '保存文档', category: 'modify', cn: '保存文档' },

  // ── 生态环境核心（Eco 主战场） ──
  query_air_quality: { verb: '查询空气质量', category: 'external' },
  query_water_quality: { verb: '查询水质', category: 'external' },
  query_noise_monitoring: { verb: '查询噪声监测', category: 'external' },
  query_radiation_monitoring: { verb: '查询辐射监测', category: 'external' },
  query_solid_waste_disposal: { verb: '查询固废处置', category: 'external' },
  query_hazardous_waste_transfer: { verb: '查询危废转移', category: 'external' },
  query_ecological_red_line: { verb: '查询生态红线', category: 'external' },
  query_environmental_acceptance: { verb: '查询环保验收', category: 'external' },
  query_environmental_emergency_response: { verb: '查询环境应急', category: 'external' },
  query_environmental_facility_operation: { verb: '查询治污设施运行', category: 'external' },
  query_environmental_impact_assessment: { verb: '查询环评', category: 'external' },
  query_environmental_impact_approval: { verb: '查询环评批复', category: 'external' },
  query_environmental_penalty: { verb: '查询环境处罚', category: 'external' },
  query_pollution_discharge_permit: { verb: '查询排污许可', category: 'external' },
  search_regulation: { verb: '检索法规', category: 'search' },
  get_emission_standard: { verb: '获取排放标准', category: 'read' },
  detect_soil_pollution: { verb: '检测土壤污染', category: 'diagnostics' },
  analyze_document: { verb: '分析文档', category: 'diagnostics' },
  analyze_industrial_carbon_emission: { verb: '分析工业碳排放', category: 'diagnostics' },
  vision_analyze: { verb: '图像识别', category: 'diagnostics' },
  ocr_extract: { verb: 'OCR 提取', category: 'diagnostics' },
  dispatch_emergency_command: { verb: '调度应急指挥', category: 'collab' },
  monitor_smart_water: { verb: '监测智慧水务', category: 'diagnostics' },
  supervise_smart_gas: { verb: '监管智慧燃气', category: 'diagnostics' },

  // ── 碳 / 双碳 ──
  calculate_carbon_emission: { verb: '核算碳排放', category: 'diagnostics' },
  calculate_carbon_footprint: { verb: '计算碳足迹', category: 'diagnostics' },
  analyze_carbon_emission: { verb: '分析碳排放', category: 'diagnostics' },
  predict_carbon_emission: { verb: '预测碳排放', category: 'diagnostics' },
  input_carbon_emission_data: { verb: '录入碳排放数据', category: 'modify' },
  generate_carbon_emission_report: { verb: '生成碳排放报告', category: 'modify' },
  query_carbon_quota: { verb: '查询碳配额', category: 'external' },
  query_carbon_asset_account: { verb: '查询碳资产账户', category: 'external' },
  query_carbon_monitoring_data: { verb: '查询碳监测数据', category: 'external' },
  query_green_electricity_trade: { verb: '查询绿电交易', category: 'external' },
  query_energy_consumption: { verb: '查询能耗', category: 'external' },
  track_carbon_neutrality_progress: { verb: '跟踪碳中和进度', category: 'diagnostics' },
  register_ccer_project: { verb: '登记 CCER 项目', category: 'modify' },
  trade_carbon_emission_allowance: { verb: '交易碳排放配额', category: 'external' },
  apply_carbon_verification: { verb: '申请碳核查', category: 'external' },
  apply_cleaner_production_audit: { verb: '申请清洁生产审核', category: 'external' },
  set_emission_reduction_target: { verb: '设定减排目标', category: 'modify' },

  // ── 外部 MCP ──
  'mcp:ehs_kb': { verb: '检索环保知识库', category: 'search' },
  'mcp:govmcp': { verb: '调用政务服务', category: 'external' },
  'mcp:tencent_docs': { verb: '操作腾讯文档', category: 'collab' },
};

/** 前缀规则（顺序敏感，长前缀在前） */
const PREFIX_RULES: [string, ToolRule][] = [
  ['apply_', { verb: '办理申请', category: 'external' }],
  ['query_', { verb: '查询', category: 'read' }],
  ['search_', { verb: '检索', category: 'search' }],
  ['get_', { verb: '获取', category: 'read' }],
  ['generate_', { verb: '生成', category: 'modify' }],
  ['create_', { verb: '创建', category: 'modify' }],
  ['register_', { verb: '登记', category: 'modify' }],
  ['submit_', { verb: '提交', category: 'modify' }],
  ['input_', { verb: '录入', category: 'modify' }],
  ['book_', { verb: '预约', category: 'modify' }],
  ['manage_', { verb: '管理', category: 'modify' }],
  ['configure_', { verb: '配置', category: 'modify' }],
  ['control_', { verb: '控制', category: 'modify' }],
  ['handle_', { verb: '处理', category: 'collab' }],
  ['initiate_', { verb: '发起', category: 'collab' }],
  ['transfer_', { verb: '流转', category: 'collab' }],
  ['supervise_', { verb: '监管', category: 'diagnostics' }],
  ['monitor_', { verb: '监测', category: 'diagnostics' }],
  ['track_', { verb: '跟踪', category: 'diagnostics' }],
  ['analyze_', { verb: '分析', category: 'diagnostics' }],
  ['detect_', { verb: '检测', category: 'diagnostics' }],
  ['calculate_', { verb: '测算', category: 'diagnostics' }],
  ['predict_', { verb: '预测', category: 'diagnostics' }],
  ['trade_', { verb: '交易', category: 'external' }],
  ['set_', { verb: '设置', category: 'modify' }],
  ['mcp:', { verb: '调用', category: 'external' }],
];

const FALLBACK_RULE: ToolRule = { verb: '执行', category: 'other' };

function matchRule(name: string): ToolRule {
  const key = name.trim().toLowerCase();
  const exact = EXACT_RULES[key];
  if (exact) return exact;
  for (const [prefix, rule] of PREFIX_RULES) {
    if (key.startsWith(prefix)) return rule;
  }
  return FALLBACK_RULE;
}

/* ────────────────────────────────────────────────────────────
 * 2. 参数 → 主题宾语（topic）
 * ──────────────────────────────────────────────────────────── */

/** topic 抽取优先级：越靠前越优先 */
const TOPIC_KEYS = [
  'path', 'file', 'file_path', 'files', 'filename',
  'query', 'q', 'keyword', 'keywords', 'search', 'question',
  'cmd', 'command', 'script', 'code',
  'city', 'region', 'area', 'station', 'enterprise', 'company',
  'name', 'title', 'subject', 'id', 'code', 'permit_no', 'license_no',
  'url', 'uri', 'link',
  'text', 'content', 'prompt', 'objective',
];

/** 参数值 → 可读短文本 */
function shortValue(key: string, v: unknown): string {
  if (v === null || v === undefined) return '';
  if (Array.isArray(v)) {
    const first = v.length > 0 ? shortValue(key, v[0]) : '';
    return v.length > 1 ? `${first} 等 ${v.length} 项` : first;
  }
  if (typeof v === 'object') {
    // 嵌套对象再挖一层
    for (const k of TOPIC_KEYS) {
      const inner = (v as Record<string, unknown>)[k];
      if (inner !== undefined && inner !== '') return shortValue(k, inner);
    }
    return '';
  }
  let s = String(v).trim();
  if (!s) return '';

  // 路径取 basename，保留可读性
  if (key === 'path' || key === 'file' || key === 'file_path' || key === 'files' || key === 'filename') {
    const parts = s.replace(/\\/g, '/').split('/');
    s = parts[parts.length - 1] || s;
  }
  // 命令只取首段（去掉长参数串）
  if (key === 'cmd' || key === 'command' || key === 'script') {
    s = s.split('\n')[0];
  }
  if (s.length > 28) s = `${s.slice(0, 28)}…`;
  return s;
}

export function extractTopic(args?: Record<string, unknown>): string {
  if (!args) return '';
  for (const k of TOPIC_KEYS) {
    const v = args[k];
    if (v === undefined || v === null || v === '') continue;
    const s = shortValue(k, v);
    if (s) return s;
  }
  // 兜底：取第一个标量值
  for (const v of Object.values(args)) {
    if (v === null || v === undefined) continue;
    if (typeof v === 'string' || typeof v === 'number') {
      const s = shortValue('', v);
      if (s) return s;
    }
  }
  return '';
}

/* ────────────────────────────────────────────────────────────
 * 3. 中文工具名（P1 工具名本地化，同一套规则顺带产出）
 * ──────────────────────────────────────────────────────────── */

/** 名词片段词典：snake_case 片段 → 中文 */
const WORD_CN: Record<string, string> = {
  air: '空气', quality: '质量', water: '水质', noise: '噪声', radiation: '辐射',
  soil: '土壤', ecology: '生态', red: '红线', line: '红线', carbon: '碳',
  emission: '排放', emissions: '排放', footprint: '足迹', quota: '配额',
  asset: '资产', account: '账户', neutrality: '中和', progress: '进度',
  ccer: 'CCER', target: '目标', reduction: '减排', standard: '标准',
  regulation: '法规', law: '法规', penalty: '处罚', punishment: '处罚',
  permit: '许可', discharge: '排污', license: '证照', approval: '审批',
  assessment: '评估', acceptance: '验收', emergency: '应急', response: '响应',
  facility: '设施', operation: '运行', hazardous: '危废', waste: '废物',
  solid: '固废', disposal: '处置', transfer: '转移', monitor: '监测',
  monitoring: '监测', data: '数据', report: '报告', document: '文书',
  pollution: '污染', environmental: '环境', industrial: '工业',
  energy: '能源', consumption: '能耗', electricity: '电力', green: '绿色',
  trade: '交易', project: '项目', enterprise: '企业', credit: '信用',
  fire: '消防', tax: '税务', invoice: '发票', patent: '专利',
  trademark: '商标', property: '产权', building: '建筑', housing: '住房',
  fund: '公积金', social: '社保', security: '社保', medical: '医保',
  insurance: '保险', driver: '驾驶证', vehicle: '车辆', traffic: '交通',
  violation: '违章', residence: '居住', household: '户籍', education: '教育',
  elderly: '养老', disability: '残疾人', subsidy: '补贴', low: '低收入',
  income: '收入', assistance: '救助', marriage: '婚姻', fertility: '生育',
  smart: '智慧', city: '城市', community: '社区', streetlight: '路灯',
  heating: '供热', water_quality: '水质', parking: '停车', bicycle: '单车',
  grid: '网格', video: '视频', applicants: '申请人', archive: '档案',
  template: '模板', delegation: '委托', comments: '意见', statistics: '统计',
  warning: '预警', workflow: '流程', counter: '会签', sign: '签',
  suspend: '挂起', resume: '恢复', permission: '权限', cleaner: '清洁',
  production: '生产', audit: '审核', verification: '核查', high: '高新',
  tech: '科技', listing: '上市', guidance: '辅导', procurement: '采购',
  food: '食品', drug: '药品', device: '器械', business: '经营',
  government: '政府', registration: '登记', record: '记录',
};

/** 去掉动词前缀后的剩余片段 → 中文宾语；词典未全覆盖则返回 null（宁可保留英文，不硬造词） */
function chineseObject(key: string, verb: string): string | null {
  const words = key.split(/[_\-\s:]+/).filter(Boolean);
  // 动词的前缀片段（verb-prefix ↔ snake word 对齐）
  const verbWords = new Set(['query', 'search', 'get', 'generate', 'create', 'register',
    'submit', 'input', 'book', 'manage', 'configure', 'control', 'handle', 'initiate',
    'transfer', 'supervise', 'monitor', 'track', 'analyze', 'detect', 'calculate',
    'predict', 'trade', 'set', 'apply', 'save', 'file', 'web', 'read', 'write', 'edit',
    'list', 'shell', 'run', 'memory', 'rag', 'execute', 'python', 'http', 'vision', 'ocr']);
  const obj = words.filter((w) => !verbWords.has(w));
  if (obj.length === 0) return null;
  const mapped = obj.map((w) => WORD_CN[w] ?? null);
  if (mapped.some((m) => m === null)) return null;
  void verb;
  return mapped.join('');
}

/** 工具名 → 可读中文名（展开态仍保留英文原名，此处只做友好别名） */
export function humanizeToolName(name: string): string {
  const key = name.trim().toLowerCase();
  const exact = EXACT_RULES[key];
  if (exact) {
    if (exact.cn) return exact.cn; // 精确中文全名（内置工具 / 动词未含宾语者）
    if (exact.verb.length > 2) return exact.verb; // 动词已自带宾语，如「查询空气质量」
    const obj = chineseObject(key, exact.verb);
    return obj ? `${exact.verb}${obj}` : name;
  }
  for (const [prefix, rule] of PREFIX_RULES) {
    if (key.startsWith(prefix)) {
      const obj = chineseObject(key.slice(prefix.length), rule.verb);
      return obj ? `${rule.verb}${obj}` : name;
    }
  }
  return name;
}

/* ────────────────────────────────────────────────────────────
 * 4. 语义分组模板（对齐 WorkBuddy group.{category}）
 * ──────────────────────────────────────────────────────────── */

const GROUP_TPL: Record<FoldCategory, string> = {
  read: '查看 {topic}',
  modify: '修改{topic}',
  command: '运行 {topic}',
  search: '定位{topic}相关代码',
  research: '收集{topic}资料',
  plan: '整理 {topic} 计划',
  collab: '协作处理{topic}',
  external: '获取 {topic}',
  diagnostics: '检查 {topic}',
  other: '处理{topic}',
};

/** 无主题时的兜底短语（对齐 WorkBuddy groupNoTopic） */
const GROUP_NO_TOPIC: Record<FoldCategory, string> = {
  read: '查看相关文件',
  modify: '修改文件',
  command: '运行命令',
  search: '搜索相关代码',
  research: '收集资料',
  plan: '整理计划',
  collab: '协作分派',
  external: '调用外部服务',
  diagnostics: '检查诊断',
  other: '处理多个步骤',
};

/** 单工具 → 短语（优先用精确动词，主题为空时才回落到分组模板） */
export function phraseOf(t: ToolSemantic): string {
  if (!t.topic) {
    // 动词已自带宾语（如「查询空气质量」）→ 直接陈述；否则用分组兜底短语
    return t.verb.length > 2 ? t.verb : GROUP_NO_TOPIC[t.category];
  }
  // 动词含宾语时宾语与主题用「：」分隔，避免歧义；短动词后补空格（如「读取 api.ts」）
  return t.verb.length > 2 ? `${t.verb}：${t.topic}` : `${t.verb} ${t.topic}`;
}

/* ────────────────────────────────────────────────────────────
 * 5. 核心：事件 → 语义 / 折叠摘要
 * ──────────────────────────────────────────────────────────── */

/** 单条工具事件 → 语义描述 */
export function describeTool(name: string, args?: Record<string, unknown>): ToolSemantic {
  const raw = name || 'unknown';
  const rule = matchRule(raw);
  return {
    raw,
    verb: rule.verb,
    cn: humanizeToolName(raw),
    category: rule.category,
    topic: extractTopic(args),
    error: false,
  };
}

/** 结果是否代表失败（后端无显式 error 字段，按文本特征判定） */
function looksLikeError(preview?: string): boolean {
  if (!preview) return false;
  const head = preview.slice(0, 200).toLowerCase();
  return (
    head.includes('"error"') ||
    head.includes('"ok": false') ||
    head.includes('traceback') ||
    head.includes('exception')
  );
}

/**
 * 按 round 折叠一轮轨迹。
 * tool_start 为「意图」，tool 为「结果」，两者按 name 配对（与 ChatView 现有配对逻辑一致）。
 */
export function foldTurn(round: number, events: TraceEvent[]): TurnFold {
  const starts = events.filter((e) => e.type === 'tool_start');
  const results = events.filter((e) => e.type === 'tool');
  const tools: ToolSemantic[] = starts.map((s) => {
    const done = results.find((r) => r.name === s.name);
    const sem = describeTool(s.name ?? '', s.args);
    sem.costMs = done?.cost_ms ?? s.cost_ms;
    sem.error = looksLikeError(done?.result_preview);
    return sem;
  });

  const phrases: string[] = [];
  const cats = new Set<FoldCategory>();
  for (const t of tools) {
    cats.add(t.category);
    const p = phraseOf(t);
    if (!phrases.includes(p)) phrases.push(p);
  }

  return {
    round,
    tools,
    thinking: events.some((e) => e.type === 'think' || e.type === 'think_delta'),
    toolCount: tools.length,
    errorCount: tools.filter((t) => t.error).length,
    totalMs: events.reduce((s, e) => s + (e.cost_ms ?? 0), 0),
    phrases,
    categoryCount: cats.size,
  };
}

/** 整条轨迹 → 每轮折叠 */
export function foldTrace(trace: TraceEvent[]): TurnFold[] {
  const map = new Map<number, TraceEvent[]>();
  for (const t of trace) {
    const r = t.round ?? 1;
    if (!map.has(r)) map.set(r, []);
    map.get(r)!.push(t);
  }
  return Array.from(map.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([round, events]) => foldTurn(round, events));
}

/* ────────────────────────────────────────────────────────────
 * 6. 文案拼装（对齐 WorkBuddy i18n 文案）
 * ──────────────────────────────────────────────────────────── */

export function fmtFoldMs(ms?: number): string {
  if (ms === undefined || ms <= 0) return '';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** 折叠行主文本：多短语用「、」连接，超 3 个截断为「等 N 项」 */
export function foldSummaryText(f: TurnFold): string {
  if (f.phrases.length === 0) {
    return f.thinking ? '思考处理任务过程' : '继续处理任务过程';
  }
  const MAX = 3;
  const head = f.phrases.slice(0, MAX);
  const rest = f.phrases.length - head.length;
  return rest > 0 ? `${head.join('、')} 等 ${f.phrases.length} 项` : head.join('、');
}

/** Turn 状态机（WorkBuddy: metaFold.turnCompleted / turnCancelled） */
export type TurnState = 'running' | 'completed' | 'cancelled';

export function turnStateText(state: TurnState, ms?: number): string {
  const d = fmtFoldMs(ms);
  if (state === 'running') return '正在进行';
  if (state === 'cancelled') return d ? `已取消 ${d}` : '已取消';
  return d ? `已完成 ${d}` : '已完成';
}
