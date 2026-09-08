/**
 * web/src/utils/metaFold.ts — 执行块分组与折叠摘要（WorkBuddy meta-fold 对标）
 *
 * 穿透 WorkBuddy app.asar v5.3.13 得到的机制，逐条对标实现：
 *
 *  1) 工具描述符注册表（mata-fold/summary/tool-registry.ts）
 *     41 个 canonical 工具 → 9 个 group。normalizeToolName 把 CLI/别名/
 *     mcp_ 前缀统一成 canonical；未命中返回兜底描述符并保留原名。
 *
 *  2) 摘要决策树（mata-fold/summary/select.ts），优先级原文：
 *     等待用户 > 单一工具/单一阶段 > 多阶段共同主题 > 多类操作计数 > 意图兜底
 *     聚合状态：waiting > running > cancelled > success
 *     源码注释两次强调：「不存在失败聚合态——失败工具按完成处理」
 *     「刻意不含失败分支——总结只讲做了什么」，本实现照此，不生成失败摘要。
 *
 *  3) 展开预算（mata-fold/expand-budget.ts）
 *     按近似字符数估算渲染成本，标量记 SCALAR_COST=8，
 *     递归深度上限 COST_WALK_MAX_DEPTH=6，从尾部往前取
 *     （注释原话：用户展开时最关心最近发生的事）。
 *
 *  4) hoist（hooks/use-fold-hook/index.tsx）
 *     show_widget 类内容豁免折叠，并提升到结果正文下方。
 */

/** WorkBuddy 的 9 个 group（tool-registry group 字段全集） */
export type ToolGroup =
  | 'read' | 'modify' | 'search' | 'diagnostics' | 'command'
  | 'research' | 'plan' | 'collab' | 'external' | 'other';

export interface ToolDescriptor {
  canonical: string;
  aliases: string[];
  category: string;
  group: ToolGroup;
  /** 摘要动词，对标 WorkBuddy actionKey（其为 i18n key，此处直接落中文） */
  action: string;
  /** 从 args 里取「操作对象」的候选字段，顺序即优先级 */
  objectFields: string[];
  /** 无对象时的兜底措辞，对标 noObjectKey */
  noObject: string;
}

/** 对标 WorkBuddy TOOL_DESCRIPTORS（41 条），并补齐 eco 自有工具别名 */
export const TOOL_DESCRIPTORS: ToolDescriptor[] = [
  // ── group: read ──
  { canonical: 'read_file', aliases: ['Read', 'read-file', 'read', 'cat_file'], category: 'file_read', group: 'read',
    action: '读取', objectFields: ['filePath', 'file_path', 'path', 'name', 'file'], noObject: '读取文件' },
  { canonical: 'list_dir', aliases: ['LS', 'list-dir', 'ls'], category: 'dir_list', group: 'read',
    action: '浏览', objectFields: ['target_directory', 'dirPath', 'path', 'dir'], noObject: '浏览目录' },
  { canonical: 'list_files', aliases: ['glob'], category: 'dir_list', group: 'read',
    action: '列出', objectFields: ['pattern', 'path', 'dir'], noObject: '列出文件' },

  // ── group: modify ──
  { canonical: 'write_to_file', aliases: ['Write', 'write_file', 'write'], category: 'file_write', group: 'modify',
    action: '写入', objectFields: ['filePath', 'file_path', 'path'], noObject: '写入文件' },
  { canonical: 'replace_in_file', aliases: ['Edit', 'MultiEdit', 'edit_file', 'edit'], category: 'file_edit', group: 'modify',
    action: '编辑', objectFields: ['filePath', 'file_path', 'path'], noObject: '编辑文件' },
  { canonical: 'append_to_file', aliases: [], category: 'file_append', group: 'modify',
    action: '追加', objectFields: ['filePath', 'file_path', 'path'], noObject: '追加内容' },
  { canonical: 'delete_files', aliases: ['delete_file', 'delete-files'], category: 'file_delete', group: 'modify',
    action: '删除', objectFields: ['target_file', 'filePath', 'file_path', 'path', 'file'], noObject: '删除文件' },

  // ── group: search ──
  { canonical: 'search_file', aliases: ['find'], category: 'file_search', group: 'search',
    action: '查找', objectFields: ['pattern', 'query', 'path'], noObject: '查找文件' },
  { canonical: 'search_content', aliases: ['grep', 'Grep'], category: 'content_search', group: 'search',
    action: '搜索', objectFields: ['pattern', 'query', 'regex'], noObject: '搜索内容' },
  { canonical: 'codebase_search', aliases: ['CodebaseSearch'], category: 'codebase_search', group: 'search',
    action: '检索', objectFields: ['query'], noObject: '检索代码库' },

  // ── group: diagnostics ──
  { canonical: 'read_lints', aliases: ['ReadLints'], category: 'diagnostics', group: 'diagnostics',
    action: '检查', objectFields: ['path', 'paths'], noObject: '检查问题' },

  // ── group: command ──
  { canonical: 'execute_command', aliases: ['ExecuteCommand', 'run_command', 'run_terminal_cmd', 'bash', 'shell'], category: 'command', group: 'command',
    action: '执行', objectFields: ['command', 'cmd'], noObject: '执行命令' },

  // ── group: research ──
  { canonical: 'web_search', aliases: ['WebSearch', 'search'], category: 'web_search', group: 'research',
    action: '搜索', objectFields: ['query', 'q'], noObject: '联网搜索' },
  { canonical: 'web_fetch', aliases: ['WebFetch', 'fetch_url'], category: 'web_fetch', group: 'research',
    action: '抓取', objectFields: ['url'], noObject: '抓取网页' },
  { canonical: 'RAG_search', aliases: ['rag_search'], category: 'rag_search', group: 'research',
    action: '检索', objectFields: ['query'], noObject: '检索知识库' },

  // ── group: plan ──
  { canonical: 'todo_write', aliases: ['TodoWrite'], category: 'todo', group: 'plan',
    action: '规划', objectFields: ['summary'], noObject: '更新任务清单' },
  { canonical: 'plan_create', aliases: ['PlanCreate', 'PLAN_CREATE'], category: 'plan_create', group: 'plan',
    action: '制定', objectFields: ['title', 'summary'], noObject: '制定计划' },
  { canonical: 'plan_update', aliases: ['PlanUpdate'], category: 'plan_update', group: 'plan',
    action: '更新', objectFields: ['title', 'summary'], noObject: '更新计划' },

  // ── group: collab ──
  { canonical: 'task', aliases: ['Task', 'subagent'], category: 'subtask', group: 'collab',
    action: '派发', objectFields: ['description', 'prompt'], noObject: '派发子任务' },
  { canonical: 'send_message', aliases: ['SendMessage'], category: 'message', group: 'collab',
    action: '发送', objectFields: ['message'], noObject: '发送消息' },

  // ── group: external ──
  { canonical: 'mcp_call_tool', aliases: [], category: 'mcp_call', group: 'external',
    action: '调用', objectFields: ['tool', 'name', 'server'], noObject: '调用外部工具' },

  // ── group: other ──
  { canonical: 'use_skill', aliases: ['Skill', 'skill', 'SkillManage'], category: 'skill', group: 'other',
    action: '使用技能', objectFields: ['skill', 'command'], noObject: '使用技能' },
  { canonical: 'image_gen', aliases: ['ImageGen', 'image_edit'], category: 'image_gen', group: 'other',
    action: '生成图片', objectFields: ['prompt'], noObject: '生成图片' },
  // 画图两步流：先读指南，再出图（WorkBuddy 同名工具）
  { canonical: 'visualize:read_me', aliases: ['read_me', 'visualizer:read_me', 'visualizer:read_me_tool'], category: 'visualize_guide', group: 'other',
    action: '准备可视化', objectFields: [], noObject: '读取可视化指南' },
  { canonical: 'visualize:show_widget', aliases: ['visualizer:show_widget', 'show_widget'], category: 'visualize_widget', group: 'other',
    action: '生成图表', objectFields: ['title'], noObject: '生成图表' },

  // ── eco 自有 44 个工具（_codex_tools() 全集）───────────────────────
  // 只对标机制、不照搬清单：WorkBuddy 的 41 条是它自己的工具，
  // eco 必须把自己的工具映进同一套 group 体系，否则摘要全部退到「处理中」兜底。
  { canonical: 'file_read', aliases: [], category: 'file_read', group: 'read',
    action: '读取', objectFields: ['path', 'file', 'filename'], noObject: '读取文件' },
  { canonical: 'file_write', aliases: [], category: 'file_write', group: 'modify',
    action: '写入', objectFields: ['path', 'file', 'filename'], noObject: '写入文件' },
  { canonical: 'file_edit', aliases: [], category: 'file_edit', group: 'modify',
    action: '编辑', objectFields: ['path', 'file', 'filename'], noObject: '编辑文件' },
  { canonical: 'save_document', aliases: [], category: 'file_write', group: 'modify',
    action: '保存', objectFields: ['filename', 'title', 'path'], noObject: '保存文档' },
  { canonical: 'shell_run', aliases: [], category: 'command', group: 'command',
    action: '执行', objectFields: ['command', 'cmd'], noObject: '执行命令' },
  { canonical: 'execute_code', aliases: [], category: 'command', group: 'command',
    action: '运行代码', objectFields: ['language', 'lang'], noObject: '运行代码' },
  { canonical: 'kb_search', aliases: [], category: 'rag_search', group: 'research',
    action: '检索知识库', objectFields: ['query', 'q'], noObject: '检索知识库' },
  { canonical: 'kb_semantic_search', aliases: [], category: 'rag_search', group: 'research',
    action: '语义检索', objectFields: ['query', 'q'], noObject: '语义检索' },
  { canonical: 'statute_search', aliases: [], category: 'rag_search', group: 'research',
    action: '检索法条', objectFields: ['query', 'keyword'], noObject: '检索法条' },
  { canonical: 'statute_lookup', aliases: [], category: 'rag_search', group: 'research',
    action: '查法条', objectFields: ['statute', 'article', 'name'], noObject: '查法条' },
  { canonical: 'statute_related', aliases: [], category: 'rag_search', group: 'research',
    action: '关联法条', objectFields: ['statute', 'name'], noObject: '关联法条' },
  { canonical: 'open_url', aliases: [], category: 'web_fetch', group: 'research',
    action: '打开', objectFields: ['url'], noObject: '打开网页' },
  { canonical: 'hunan_case_list', aliases: [], category: 'web_fetch', group: 'research',
    action: '查询案卷', objectFields: ['city', 'year', 'keyword'], noObject: '查询案卷台账' },
  { canonical: 'query_air_quality', aliases: [], category: 'web_fetch', group: 'research',
    action: '查询空气质量', objectFields: ['city', 'station'], noObject: '查询空气质量' },
  { canonical: 'analyze_document', aliases: [], category: 'content_search', group: 'search',
    action: '分析', objectFields: ['path', 'filename'], noObject: '分析文档' },
  { canonical: 'detect_data_anomaly', aliases: [], category: 'diagnostics', group: 'diagnostics',
    action: '检测异常', objectFields: ['dataset', 'field'], noObject: '检测数据异常' },
  { canonical: 'calculate_carbon_emission', aliases: [], category: 'diagnostics', group: 'diagnostics',
    action: '核算碳排', objectFields: ['scope', 'source'], noObject: '核算碳排放' },
  { canonical: 'audit_tail', aliases: [], category: 'diagnostics', group: 'diagnostics',
    action: '查看审计链', objectFields: ['n', 'lines'], noObject: '查看审计链' },
  { canonical: 'session_log_tail', aliases: [], category: 'diagnostics', group: 'diagnostics',
    action: '查看日志', objectFields: ['n', 'lines'], noObject: '查看会话日志' },
  { canonical: 'inspect', aliases: [], category: 'diagnostics', group: 'diagnostics',
    action: '自检', objectFields: ['kind'], noObject: '系统自检' },
  { canonical: 'api_probe', aliases: [], category: 'diagnostics', group: 'diagnostics',
    action: '探测接口', objectFields: ['url', 'path'], noObject: '探测接口' },
  // 图表：eco 的 chart_render 对应 WorkBuddy 的 show_widget，同样豁免折叠
  { canonical: 'chart_render', aliases: [], category: 'visualize_widget', group: 'other',
    action: '生成图表', objectFields: ['title', 'type'], noObject: '生成图表' },
  { canonical: 'generate_pptx', aliases: [], category: 'file_write', group: 'modify',
    action: '生成课件', objectFields: ['title', 'filename'], noObject: '生成 PPT' },
  { canonical: 'tdocs_upload_html', aliases: [], category: 'file_write', group: 'modify',
    action: '上传腾讯文档', objectFields: ['title', 'filename'], noObject: '上传腾讯文档' },
  { canonical: 'eco_memory_add', aliases: [], category: 'memory', group: 'plan',
    action: '记忆', objectFields: ['content', 'key'], noObject: '写入记忆' },
  { canonical: 'eco_memory_search', aliases: [], category: 'memory', group: 'plan',
    action: '回忆', objectFields: ['query', 'q'], noObject: '检索记忆' },
  { canonical: 'eco_memory_update', aliases: [], category: 'memory', group: 'plan',
    action: '更新记忆', objectFields: ['key', 'id'], noObject: '更新记忆' },
  { canonical: 'eco_memory_delete', aliases: [], category: 'memory', group: 'plan',
    action: '删除记忆', objectFields: ['key', 'id'], noObject: '删除记忆' },
  { canonical: 'eco_memory_stats', aliases: [], category: 'memory', group: 'plan',
    action: '统计记忆', objectFields: [], noObject: '统计记忆' },
  { canonical: 'eco_memory_prune', aliases: [], category: 'memory', group: 'plan',
    action: '清理记忆', objectFields: [], noObject: '清理记忆' },
  { canonical: 'eco_memory_sync', aliases: [], category: 'memory', group: 'plan',
    action: '同步记忆', objectFields: [], noObject: '同步记忆' },
  { canonical: 'spawn_goal', aliases: [], category: 'subtask', group: 'collab',
    action: '派发目标', objectFields: ['objective', 'goal'], noObject: '派发目标' },
  { canonical: 'goal_status', aliases: [], category: 'subtask', group: 'collab',
    action: '查看目标', objectFields: ['goal_id'], noObject: '查看目标状态' },
  { canonical: 'switch_persona', aliases: [], category: 'automation', group: 'other',
    action: '切换人格', objectFields: ['persona', 'name'], noObject: '切换人格' },
  { canonical: 'cron_add', aliases: [], category: 'automation', group: 'plan',
    action: '添加定时', objectFields: ['name', 'schedule'], noObject: '添加定时任务' },
  { canonical: 'cron_list', aliases: [], category: 'automation', group: 'plan',
    action: '列出定时', objectFields: [], noObject: '列出定时任务' },
  { canonical: 'cron_remove', aliases: [], category: 'automation', group: 'plan',
    action: '移除定时', objectFields: ['name', 'id'], noObject: '移除定时任务' },
  { canonical: 'cron_run', aliases: [], category: 'automation', group: 'plan',
    action: '运行定时', objectFields: ['name', 'id'], noObject: '运行定时任务' },
  { canonical: 'eco_policy_reload', aliases: [], category: 'automation', group: 'other',
    action: '重载策略', objectFields: [], noObject: '重载策略' },
  { canonical: 'system_reload', aliases: [], category: 'automation', group: 'other',
    action: '重载系统', objectFields: [], noObject: '重载系统' },
];

const UNKNOWN_DESCRIPTOR: ToolDescriptor = {
  canonical: 'unknown', aliases: [], category: 'unknown', group: 'other',
  action: '处理', objectFields: [], noObject: '执行操作',
};

const ALIAS_TO_CANONICAL = new Map<string, string>();
const CANONICAL_TO_DESCRIPTOR = new Map<string, ToolDescriptor>();
for (const d of TOOL_DESCRIPTORS) {
  CANONICAL_TO_DESCRIPTOR.set(d.canonical, d);
  ALIAS_TO_CANONICAL.set(d.canonical.toLowerCase(), d.canonical);
  for (const a of d.aliases) ALIAS_TO_CANONICAL.set(a.toLowerCase(), d.canonical);
}

const AUTOMATION_SUFFIX = '_automation_update';

/** MCP 内层工具名 → 动作词。
 *
 *  此前所有 mcp__ 工具都折成 mcp_call_tool，展开态一律显示「调用 · {参数}」，
 *  17 个 MCP 服务器几百个工具全长一个样，等于没有信息。
 *  这里按内层名里的动词推断，命中不了才退回泛化的「调用」。
 *  只读语义为主 —— eco 挂载的 MCP 绝大多数是查询类。 */
const MCP_VERB_RULES: ReadonlyArray<readonly [RegExp, string]> = [
  [/^(search|query|find|lookup)_/, '检索'],
  [/^(get|read|fetch|list)_/, '读取'],
  [/^(download)_/, '下载'],
  [/^(air_quality|water_quality|weather)/, '查询'],
  [/(_search|_query)$/, '检索'],
  [/(_list|_detail)$/, '读取'],
];

/** 从 mcp__server__tool 提取可读的对象名：内层工具名去掉动词前缀、下划线转空格 */
export function mcpObject(raw: string): string | undefined {
  const parts = raw.split('__');
  if (parts.length < 3) return undefined;
  const inner = parts.slice(2).join('__');
  const stripped = inner
    .replace(/^(search|query|get|read|fetch|list|find|lookup|download)_/, '')
    .replace(/_/g, ' ')
    .trim();
  return stripped || undefined;
}

/** 对标 WorkBuddy normalizeToolName：CLI/别名/mcp_ 前缀 → canonical */
export function normalizeToolName(raw: unknown): string {
  if (typeof raw !== 'string' || !raw) return 'unknown';
  const lower = raw.toLowerCase();
  const hit = ALIAS_TO_CANONICAL.get(lower);
  if (hit) return hit;
  if (lower.endsWith(AUTOMATION_SUFFIX)) return 'automation_update';
  if (lower.startsWith('mcp_') || lower.startsWith('mcp__')) return 'mcp_call_tool';
  return raw;
}

/** 对标 getToolDescriptor：未命中时兜底但保留原名 */
export function getToolDescriptor(rawName: unknown): ToolDescriptor {
  const canonical = normalizeToolName(rawName);
  // MCP 工具：按内层动词细化，避免几百个工具共用一个「调用」
  if (canonical === 'mcp_call_tool' && typeof rawName === 'string') {
    const parts = rawName.split('__');
    const inner = parts.length >= 3 ? parts.slice(2).join('__').toLowerCase() : '';
    for (const [re, action] of MCP_VERB_RULES) {
      if (re.test(inner)) {
        /* 必须补齐 aliases / objectFields。
           缺了 objectFields 会让 extractObject 对 undefined 做 for...of，
           抛 "objectFields is not iterable" —— 整页白屏，不是局部降级。
           这里刻意显式标注类型而不是 as ToolDescriptor 断言：
           断言会让 tsc 放行缺字段，构建通过、运行时炸。 */
        const d: ToolDescriptor = {
          canonical, aliases: [], category: 'mcp_call', group: 'external',
          action, objectFields: [], noObject: action,
        };
        return d;
      }
    }
  }
  const d = CANONICAL_TO_DESCRIPTOR.get(canonical);
  if (d) return d;
  return { ...UNKNOWN_DESCRIPTOR, canonical: canonical || 'unknown' };
}

// ── 摘要原子与决策 ──────────────────────────────────────────────

export type AtomStatus = 'waiting' | 'running' | 'cancelled' | 'success';

export interface SummaryAtom {
  category: string;
  group: ToolGroup;
  action: string;
  object?: string;
  noObject: string;
  status: AtomStatus;
}

/** 从工具 args 里按 objectFields 顺序取第一个可用对象，长路径只留末段 */
export function extractObject(d: ToolDescriptor, args?: Record<string, unknown>): string | undefined {
  if (!args) return undefined;
  // 防御：单个 descriptor 少写 objectFields 不应该让整页白屏。
  // 实测教训 —— 手写 MCP descriptor 时漏了这个字段，for...of undefined
  // 直接把 ChatView 整棵树炸掉，页面连输入框都渲染不出来。
  for (const f of d.objectFields ?? []) {
    const v = args[f];
    if (typeof v === 'string' && v.trim()) {
      const s = v.trim();
      // 路径类只显示 basename，命令类截断，避免摘要过长
      if (/[/\\]/.test(s) && d.group !== 'command') {
        return s.split(/[/\\]/).filter(Boolean).pop();
      }
      return s.length > 40 ? `${s.slice(0, 40)}…` : s;
    }
  }
  return undefined;
}

export function buildAtom(name: unknown, args?: Record<string, unknown>, status: AtomStatus = 'success'): SummaryAtom {
  const d = getToolDescriptor(name);
  return {
    category: d.category, group: d.group, action: d.action,
    object: extractObject(d, args), noObject: d.noObject, status,
  };
}

/** 对标 aggregateStatus：waiting > running > cancelled > success，无失败态 */
export function aggregateStatus(atoms: SummaryAtom[], isRunning: boolean): AtomStatus {
  if (atoms.some((a) => a.status === 'waiting')) return 'waiting';
  if (isRunning && atoms.some((a) => a.status === 'running')) return 'running';
  if (atoms.length > 0 && atoms.every((a) => a.status === 'cancelled')) return 'cancelled';
  return 'success';
}

/** 对标 hasUsefulInfo */
const hasUsefulInfo = (a: SummaryAtom) => a.category !== 'unknown' || !!a.object;

const GROUP_LABEL: Record<ToolGroup, string> = {
  read: '读取', modify: '修改', search: '搜索', diagnostics: '检查',
  command: '执行', research: '调研', plan: '规划', collab: '协作',
  external: '调用外部工具', other: '处理',
};

export type SummaryDecision =
  | { kind: 'waiting'; object?: string; category: string }
  | { kind: 'single'; action: string; object?: string; noObject: string }
  | { kind: 'group'; group: ToolGroup; topic?: string }
  | { kind: 'multiStage'; groups: ToolGroup[]; topic?: string }
  | { kind: 'categoryCount'; count: number }
  | { kind: 'fallback' };

/** 共同主题：多个原子操作同一对象时取该对象（对标 deriveTopic） */
function deriveTopic(atoms: SummaryAtom[]): string | undefined {
  const objs = atoms.map((a) => a.object).filter(Boolean) as string[];
  if (objs.length === 0) return undefined;
  const uniq = new Set(objs);
  return uniq.size === 1 ? objs[0] : undefined;
}

function bucketByGroup(atoms: SummaryAtom[]): { group: ToolGroup; atoms: SummaryAtom[] }[] {
  const m = new Map<ToolGroup, SummaryAtom[]>();
  for (const a of atoms) {
    if (!m.has(a.group)) m.set(a.group, []);
    m.get(a.group)!.push(a);
  }
  return Array.from(m.entries()).map(([group, list]) => ({ group, atoms: list }));
}

/**
 * 对标 selectSummary，优先级与源码逐条一致：
 * 等待用户 > 单一工具 > 单一分组 > 多阶段共同主题 > 多类操作计数 > 兜底
 */
export function selectSummary(
  atoms: SummaryAtom[],
  isRunning = false,
): { decision: SummaryDecision; status: AtomStatus } {
  if (atoms.length === 0) return { decision: { kind: 'fallback' }, status: 'success' };

  const status = aggregateStatus(atoms, isRunning);
  if (status === 'waiting') {
    const w = atoms.find((a) => a.status === 'waiting')!;
    return { decision: { kind: 'waiting', object: w.object, category: w.category }, status };
  }

  const useful = atoms.filter(hasUsefulInfo);
  if (useful.length === 0) return { decision: { kind: 'fallback' }, status };

  if (useful.length === 1) {
    const a = useful[0];
    return { decision: { kind: 'single', action: a.action, object: a.object, noObject: a.noObject }, status };
  }

  const buckets = bucketByGroup(useful);
  if (buckets.length === 1) {
    return { decision: { kind: 'group', group: buckets[0].group, topic: deriveTopic(useful) }, status };
  }

  const topic = deriveTopic(useful);
  const distinctCategories = new Set(useful.map((a) => a.category)).size;
  if (topic) {
    return {
      decision: {
        kind: 'multiStage',
        groups: buckets.sort((a, b) => b.atoms.length - a.atoms.length).slice(0, 2).map((b) => b.group),
        topic,
      },
      status,
    };
  }
  if (distinctCategories > 3) {
    return { decision: { kind: 'categoryCount', count: distinctCategories }, status };
  }
  return {
    decision: {
      kind: 'multiStage',
      groups: buckets.sort((a, b) => b.atoms.length - a.atoms.length).slice(0, 2).map((b) => b.group),
      topic: undefined,
    },
    status,
  };
}

/** 决策 → 中文摘要句（对标 summary/templates.ts 的成句职责） */
export function renderSummary(decision: SummaryDecision, status: AtomStatus): string {
  /* running 后缀分两种形态：
     动词结尾直接接「中…」通顺（检查中…）；但带对象名时会粘成
     「检查、读取 README*中…」这种断词 —— 实测线上就是这样。
     对象名结尾改用「 · 进行中」，读起来是「检查、读取 README* · 进行中」。 */
  const hasObject =
    (decision.kind === 'single' && !!decision.object) ||
    (decision.kind === 'group' && !!decision.topic) ||
    (decision.kind === 'multiStage' && !!decision.topic);
  const suffix =
    status === 'running' ? (hasObject ? ' · 进行中' : '中…')
    : status === 'cancelled' ? '（已取消）'
    : '';
  switch (decision.kind) {
    case 'waiting':
      return decision.object ? `等待确认：${decision.object}` : '等待用户确认';
    case 'single':
      return (decision.object ? `${decision.action} ${decision.object}` : decision.noObject) + suffix;
    case 'group':
      return (decision.topic
        ? `${GROUP_LABEL[decision.group]} ${decision.topic}`
        : `${GROUP_LABEL[decision.group]}若干项`) + suffix;
    case 'multiStage': {
      const gs = decision.groups.map((g) => GROUP_LABEL[g]).join('、');
      return (decision.topic ? `${gs} ${decision.topic}` : `${gs}`) + suffix;
    }
    case 'categoryCount':
      return `执行了 ${decision.count} 类操作` + suffix;
    default:
      return '处理中' + suffix;
  }
}

// ── 展开预算（对标 expand-budget.ts）────────────────────────────

export const SCALAR_COST = 8;
export const COST_WALK_MAX_DEPTH = 6;
export const COST_WALK_CAP = 20000;

/** 对标 walkChars：累计达 budget 即提前返回，不追求精确总量 */
export function walkChars(value: unknown, budget: number, depth = 0): number {
  if (budget <= 0 || depth > COST_WALK_MAX_DEPTH) return 0;
  if (typeof value === 'string') return value.length;
  if (typeof value === 'number' || typeof value === 'boolean') return SCALAR_COST;
  if (Array.isArray(value)) {
    let sum = 0;
    for (const item of value) {
      sum += walkChars(item, budget - sum, depth + 1);
      if (sum >= budget) return sum;
    }
    return sum;
  }
  if (value && typeof value === 'object') {
    let sum = 0;
    for (const item of Object.values(value)) {
      sum += walkChars(item, budget - sum, depth + 1);
      if (sum >= budget) return sum;
    }
    return sum;
  }
  return 0;
}

/** 对标 estimateContentRenderCost */
export function estimateCost(args?: unknown, result?: unknown, text?: string): number {
  if (typeof text === 'string') return text.length;
  const a = walkChars(args, COST_WALK_CAP);
  if (a >= COST_WALK_CAP) return a;
  return a + walkChars(result, COST_WALK_CAP - a);
}

/**
 * 对标 computeVisibleStartIndex：从尾部往前取满预算的窗口起点。
 * 源码注释原话：「从尾部取而不是从头取：折叠块内是时间顺序，
 * 用户展开时最关心最近发生的事。」
 */
export function visibleStartIndex(costs: number[], budget: number): number {
  let sum = 0;
  for (let i = costs.length - 1; i >= 0; i--) {
    sum += costs[i];
    if (sum > budget) return Math.min(i + 1, costs.length - 1);
  }
  return 0;
}

// ── hoist（对标 use-fold-hook）──────────────────────────────────

export const SHOW_WIDGET_NAMES = new Set([
  'visualize:show_widget', 'visualizer:show_widget', 'show_widget',
  // eco 的图表工具与 show_widget 同等对待：豁免折叠 + hoist 到正文下方
  'chart_render',
]);

/** 对标 isShowWidgetContent */
export const isShowWidget = (name: unknown): boolean =>
  typeof name === 'string' && SHOW_WIDGET_NAMES.has(name);

/**
 * 对标 isFoldableContent：show_widget 不可折叠（需展示图表卡片），
 * 其余 tool-call 与 reasoning 默认可折叠。
 */
export const isFoldable = (type: string, name?: unknown): boolean => {
  if (type === 'think' || type === 'think_delta') return true;
  if (type === 'tool' || type === 'tool_start') return !isShowWidget(name);
  return false;
};
