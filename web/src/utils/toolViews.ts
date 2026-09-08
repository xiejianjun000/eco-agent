/**
 * 工具视图注册表 —— 一个工具一个视图。
 *
 * 对标 WorkBuddy conversation-render 的 defineTool + matchPriority 机制
 * （见 docs/RENDER_SPEC.md §3）。它有 33 个独立 view；eco 此前是**一套通用
 * 渲染套所有工具**，这正是「调用工具都混在一起」的根因：
 * 搜索、读文件、执行命令、MCP 调用长得一模一样，用户无法一眼分辨。
 *
 * 本文件只做「工具 → 三段式头部内容」的映射，不产生 DOM。
 * 渲染仍由 ChatView 的 beat 行完成，保证展开/折叠共用同一套头部。
 *
 * 设计取舍：不照搬 WorkBuddy 的 React 组件树（33 个 view 各自带 children
 * 明细面板）。eco 当前的过程区是扁平行，先把「可分辨」做对；
 * children 明细面板留到后续按需补。
 */

/**
 * 展开明细。
 *
 * 重要设计约束（查证自 WorkBuddy）：**不是每个工具都可展开**。
 * 它 37 个 view 里只有 18 个用 ToolExpandable，10 个是纯 ToolHeader
 * （read-file / web-fetch / skill / delete-files / image-gen …）。
 * 判据是「有没有值得展开的结构化内容」——读个文件就是读了，
 * 展开一个空面板反而是噪音。
 *
 * 因此 detail 返回 null 表示该次调用不可展开，箭头不出现。
 */
export type ToolDetail =
  /** 命令 + 输出，等宽（对标 tool-exec：bash 标题 / command / output） */
  | { kind: 'command'; command: string; output?: string }
  /** 结果条目列表（对标 tool-web-search__results） */
  | { kind: 'list'; items: { text: string; sub?: string }[]; more?: number }
  /** 纯文本块，超长截断 */
  | { kind: 'text'; text: string }
  /** 键值对 */
  | { kind: 'kv'; rows: { k: string; v: string }[] }

/** 匹配优先级，语义对齐 WorkBuddy 的 NONE/DEFAULT/EXACT */
export const MatchPriority = { NONE: 0, DEFAULT: 1, EXACT: 10 } as const

/** 工具执行阶段 */
export type ToolPhase = 'pending' | 'running' | 'success' | 'error'

/** 三段式头部内容：动词 · 对象 · 补充。与 ToolHeader 槽位一一对应。 */
export interface ToolHeadContent {
  /** 图标名（eco 自有图标集） */
  icon: string
  /** 动词，随执行态切换：搜索中… / 已搜索 */
  statusText: string
  /** 对象，可省略；过长由 CSS 省略号截断 */
  primaryContent?: string
  /** 补充信息，12px 更小，通常是计数 */
  secondaryInfo?: string
  /** 新增行数，渲染为绿色 +N（仅写文件类） */
  added?: number
  /** 删除行数，渲染为红色 -M（仅写文件类） */
  removed?: number
  /** 命中的视图 id，落到 data-tool-view 便于断言；未命中为 'fallback' */
  viewId: string
}

type Matcher = string | string[] | ((name: string) => number | boolean)

export interface ToolViewEntry {
  id: string
  match: Matcher
  /** 由工具名 + 参数 + 阶段推出三段式内容 */
  head: (ctx: {
    name: string
    args: Record<string, unknown>
    phase: ToolPhase
    count?: number
    /** 变更行数，仅写文件类工具有；渲染为 +N -M 两个分色 span */
    added?: number
    removed?: number
    /** 目标文件已存在 → 编辑；否则创建。动词不同。 */
    isModify?: boolean
  }) => Omit<ToolHeadContent, 'viewId'>
  /**
   * 由工具结果推出展开明细；返回 null 表示不可展开。
   * 不实现即视为纯头部视图（对齐 WorkBuddy 的 10 个 header-only view）。
   */
  detail?: (ctx: { name: string; args: Record<string, unknown>; result: Record<string, unknown> }) => ToolDetail | null
}

/** 计算某 entry 对一个工具的匹配优先级（0 表示不处理） */
export function matchPriority(match: Matcher, name: string): number {
  if (typeof match === 'string') return name === match ? MatchPriority.EXACT : MatchPriority.NONE
  if (Array.isArray(match)) return match.includes(name) ? MatchPriority.EXACT : MatchPriority.NONE
  const r = match(name)
  if (typeof r === 'number') return r
  return r ? MatchPriority.EXACT : MatchPriority.NONE
}

/** 取字符串参数，容错 */
function s(args: Record<string, unknown>, ...keys: string[]): string {
  for (const k of keys) {
    const v = args?.[k]
    if (typeof v === 'string' && v.trim()) return v.trim()
  }
  return ''
}

/** 路径只留末段，避免超长路径挤掉动词 */
function baseName(p: string): string {
  if (!p) return ''
  const parts = p.replace(/\/+$/, '').split('/')
  return parts[parts.length - 1] || p
}

/**
 * 视图表。顺序不重要，由 matchPriority 决定命中。
 * 覆盖 eco 高频工具；未命中走 fallback（见 resolveToolHead）。
 */
export const TOOL_VIEWS: ToolViewEntry[] = [
  {
    id: 'web-search',
    match: ['web_search', 'search'],
    head: ({ args, phase, count }) => ({
      icon: 'search',
      statusText: phase === 'running' ? '搜索中' : '已搜索',
      primaryContent: s(args, 'query', 'q', 'keyword'),
      secondaryInfo: count ? `${count} 条` : undefined,
    }),
    detail: ({ result }) => {
      const rs = Array.isArray(result?.results) ? result.results
        : Array.isArray(result?.items) ? result.items : []
      if (!rs.length) return null
      const items = rs.slice(0, 10).map((r: Record<string, unknown>) => ({
        text: String(r?.title ?? r?.name ?? r?.text ?? '').trim().slice(0, 120),
        sub: typeof r?.url === 'string' ? r.url : undefined,
      })).filter((x) => x.text)
      return items.length ? { kind: 'list', items, more: Math.max(0, rs.length - items.length) } : null
    },
  },
  {
    id: 'web-fetch',
    match: ['web_fetch', 'open_url', 'fetch'],
    head: ({ args, phase }) => ({
      icon: 'link',
      statusText: phase === 'running' ? '读取网页中' : '已读网页',
      primaryContent: s(args, 'url'),
    }),
  },
  {
    id: 'read-file',
    match: ['read_file', 'file_read', 'read', 'cat_file'],
    head: ({ args, phase }) => ({
      icon: 'file',
      statusText: phase === 'running' ? '读取中' : '已读取',
      primaryContent: baseName(s(args, 'path', 'file_path', 'filename')),
    }),
  },
  {
    id: 'write-file',
    match: ['write_file', 'save_document', 'edit_file', 'edit'],
    /**
     * 创建与编辑是两个动词（对标 WorkBuddy writeFile.create/edit）。
     * 用户贴的 WorkBuddy 实录里，「创建 connector-meta.json +24 -0」与
     * 「编辑 db.py +1 -1」是分开的两种行，一眼能分辨是新增还是改动。
     * 行数走 added/removed 两个分色 span，不塞进文字里。
     */
    head: ({ args, phase, added, removed, isModify }) => {
      const modify = isModify ?? (typeof args?.old_string === 'string' || args?.edits != null)
      const statusText = modify
        ? (phase === 'running' ? '编辑中' : '编辑')
        : (phase === 'running' ? '写入中' : '创建')
      return {
        icon: 'save',
        statusText,
        primaryContent: baseName(s(args, 'path', 'file_path', 'filename')),
        added,
        removed,
      }
    },
  },
  {
    id: 'execute-command',
    match: ['shell_run', 'bash', 'execute_command'],
    head: ({ args, phase }) => ({
      icon: 'terminal',
      statusText: phase === 'running' ? '执行中' : '已执行命令',
      primaryContent: s(args, 'command', 'cmd'),
    }),
    detail: ({ args, result }) => {
      const cmd = s(args, 'command', 'cmd')
      const out = [result?.stdout, result?.stderr].filter((x) => typeof x === 'string' && x).join('\n')
      if (!cmd && !out) return null
      return { kind: 'command', command: cmd, output: out || undefined }
    },
  },
  {
    id: 'execute-code',
    match: ['execute_code', 'python', 'run_code'],
    head: ({ phase }) => ({
      icon: 'code',
      statusText: phase === 'running' ? '运行代码中' : '已运行代码',
    }),
    detail: ({ args, result }) => {
      const code = s(args, 'code', 'source')
      const out = [result?.stdout, result?.stderr, result?.output]
        .filter((x) => typeof x === 'string' && x).join('\n')
      if (!code && !out) return null
      return { kind: 'command', command: code, output: out || undefined }
    },
  },
  {
    id: 'grep',
    match: ['grep', 'code_grep'],
    head: ({ args, phase }) => ({
      icon: 'search',
      statusText: phase === 'running' ? '检索代码中' : '已检索代码',
      primaryContent: s(args, 'pattern'),
    }),
    detail: ({ result }) => {
      const ms = Array.isArray(result?.matches) ? result.matches : []
      if (!ms.length) return null
      const items = ms.slice(0, 20).map((m: Record<string, unknown>) => ({
        text: String(m?.line ?? m?.text ?? '').trim().slice(0, 160),
        sub: m?.file ? `${m.file}${m.lineno ? ':' + m.lineno : ''}` : undefined,
      })).filter((x) => x.text)
      if (!items.length) return null
      return { kind: 'list', items, more: Math.max(0, ms.length - items.length) }
    },
  },
  {
    id: 'glob',
    match: ['glob', 'code_glob', 'list_files'],
    head: ({ args, phase }) => ({
      icon: 'folder',
      statusText: phase === 'running' ? '查找中' : '已查找文件',
      primaryContent: s(args, 'pattern', 'path'),
    }),
  },
  {
    id: 'inspect',
    match: 'inspect',
    head: ({ phase, count }) => ({
      icon: 'gear',
      statusText: phase === 'running' ? '自检中' : '已自检',
      secondaryInfo: count ? `${count} 项` : undefined,
    }),
    detail: ({ result }) => {
      const rows: { k: string; v: string }[] = []
      for (const k of ['tools', 'services', 'plugins', 'slots']) {
        const v = result?.[k]
        const n = Array.isArray(v) ? v.length : typeof v === 'number' ? v : undefined
        if (n !== undefined) rows.push({ k, v: String(n) })
      }
      return rows.length ? { kind: 'kv', rows } : null
    },
  },
  {
    id: 'api-probe',
    match: 'api_probe',
    head: ({ args, phase }) => ({
      icon: 'radar',
      statusText: phase === 'running' ? '探测中' : '已探测',
      primaryContent: s(args, 'url'),
    }),
  },
  {
    id: 'audit',
    match: ['audit_tail', 'session_log_tail'],
    head: ({ phase }) => ({
      icon: 'list',
      statusText: phase === 'running' ? '读审计链中' : '已读审计链',
    }),
  },
  {
    id: 'kb-search',
    match: (n) => (n.startsWith('kb_') ? MatchPriority.EXACT : MatchPriority.NONE),
    head: ({ args, phase, count }) => ({
      icon: 'book',
      statusText: phase === 'running' ? '检索知识库中' : '已检索知识库',
      primaryContent: s(args, 'query', 'keyword', 'q'),
      secondaryInfo: count ? `${count} 条` : undefined,
    }),
  },
  {
    id: 'statute',
    match: (n) => (n.startsWith('statute_') ? MatchPriority.EXACT : MatchPriority.NONE),
    head: ({ args, phase }) => ({
      icon: 'book',
      statusText: phase === 'running' ? '查法条中' : '已查法条',
      primaryContent: s(args, 'article', 'keyword'),
    }),
  },
  // ── eco 业务工具族 ──────────────────────────────────────
  // 108 个内置工具里 106 个曾走 fallback，全部显示「已执行」，
  // 这正是「工具混在一起」最严重的地方：查空气质量、算碳排、
  // 办许可证、出图，在界面上长得一模一样。
  // 它们命名规律很强（query_/apply_/calculate_/generate_…），
  // 用前缀族匹配一次覆盖，比逐个注册务实。
  {
    id: 'chart',
    match: (n) => (/(_chart|_trend|_plot|draw_|visualize)/.test(n) ? MatchPriority.EXACT : MatchPriority.NONE),
    head: ({ args, phase }) => ({
      icon: 'chart',
      statusText: phase === 'running' ? '出图中' : '已出图',
      primaryContent: s(args, 'title', 'name'),
    }),
  },
  {
    id: 'carbon',
    match: (n) => (/(carbon|emission|ccer|neutrality)/.test(n) ? MatchPriority.DEFAULT : MatchPriority.NONE),
    head: ({ name, args, phase }) => {
      const v = /^calculate|^predict/.test(name) ? ['核算中', '已核算']
        : /^generate/.test(name) ? ['生成报告中', '已生成报告']
        : /^register|^trade|^set|^input/.test(name) ? ['提交中', '已提交']
        : ['查询中', '已查询']
      return {
        icon: 'leaf',
        statusText: phase === 'running' ? v[0] : v[1],
        primaryContent: s(args, 'enterprise', 'name', 'project', 'year'),
      }
    },
  },
  {
    id: 'env-query',
    match: (n) => (/^(query|detect|monitor)_(air|water|noise|soil|radiation|ecological|environmental|pollution|hazardous|solid|energy|green)/.test(n)
      ? MatchPriority.EXACT : MatchPriority.NONE),
    head: ({ args, phase }) => ({
      icon: 'leaf',
      statusText: phase === 'running' ? '查环境数据中' : '已查环境数据',
      primaryContent: s(args, 'region', 'city', 'area', 'name', 'enterprise'),
    }),
  },
  {
    id: 'gov-query',
    match: (n) => (n.startsWith('query_') ? MatchPriority.DEFAULT : MatchPriority.NONE),
    head: ({ args, phase }) => ({
      icon: 'search',
      statusText: phase === 'running' ? '查询中' : '已查询',
      primaryContent: s(args, 'name', 'enterprise', 'id', 'region', 'keyword'),
    }),
  },
  {
    id: 'gov-apply',
    match: (n) => (/^(apply_|book_|register_|submit_|initiate_)/.test(n) ? MatchPriority.DEFAULT : MatchPriority.NONE),
    head: ({ args, phase }) => ({
      icon: 'file',
      statusText: phase === 'running' ? '办理中' : '已办理',
      primaryContent: s(args, 'name', 'enterprise', 'applicant'),
    }),
  },
  {
    id: 'gov-manage',
    match: (n) => (/^(manage_|handle_|configure_|control_|supervise_|monitor_|set_|dispatch_|track_)/.test(n)
      ? MatchPriority.DEFAULT : MatchPriority.NONE),
    head: ({ args, phase }) => ({
      icon: 'gear',
      statusText: phase === 'running' ? '处理中' : '已处理',
      primaryContent: s(args, 'name', 'id', 'target'),
    }),
  },
  {
    id: 'doc-gen',
    match: (n) => (/^(generate_|analyze_|ocr_|vision_)/.test(n) ? MatchPriority.DEFAULT : MatchPriority.NONE),
    head: ({ name, args, phase }) => ({
      icon: 'file',
      statusText: /^generate/.test(name)
        ? (phase === 'running' ? '生成文档中' : '已生成文档')
        : (phase === 'running' ? '解析中' : '已解析'),
      primaryContent: s(args, 'title', 'name', 'path', 'filename'),
    }),
  },
  {
    id: 'standard',
    match: ['get_emission_standard', 'search_regulation'],
    head: ({ args, phase }) => ({
      icon: 'book',
      statusText: phase === 'running' ? '查标准中' : '已查标准',
      primaryContent: s(args, 'keyword', 'name', 'industry', 'pollutant'),
    }),
  },
  {
    /**
     * MCP 动态工具：用函数匹配吃下整族 mcp__*，
     * 但只给 DEFAULT 优先级 —— 若将来为某个具体 MCP 工具注册了精确视图，
     * 那条 EXACT 会自然胜出，不必改这里。
     * 这正是 WorkBuddy 三档优先级的用途。
     */
    id: 'mcp-call',
    match: (n) => (n.startsWith('mcp__') ? MatchPriority.DEFAULT : MatchPriority.NONE),
    head: ({ name, args, phase }) => {
      const parts = name.split('__')
      const inner = parts[2] || ''
      // 动词由内层工具名推断，对象取查询词；服务器名不外露
      const verb = /^(search|query|find|lookup)/.test(inner)
        ? (phase === 'running' ? '检索外部服务' : '已检索外部服务')
        : /^(get|read|fetch|list)/.test(inner)
          ? (phase === 'running' ? '读取外部服务' : '已读外部服务')
          : (phase === 'running' ? '调用外部服务' : '已调用外部服务')
      return {
        icon: 'plug',
        statusText: verb,
        primaryContent: s(args, 'query', 'keyword', 'name', 'q'),
      }
    },
  },
]

/**
 * 解析工具的三段式头部内容。
 * 未命中任何视图时返回 fallback —— 对齐 WorkBuddy 的 unknown-tool：
 * 不白屏、不吐裸 JSON，仍给一个结构正确的头部。
 */
export function resolveToolHead(
  name: string,
  args: Record<string, unknown> = {},
  phase: ToolPhase = 'success',
  count?: number,
  extra?: { added?: number; removed?: number; isModify?: boolean },
): ToolHeadContent {
  let best: ToolViewEntry | null = null
  // 显式标注 number：MatchPriority 用了 as const，
  // 直接推断会窄成字面量 0，后续比较赋值全报类型错。
  let bestP: number = MatchPriority.NONE
  for (const e of TOOL_VIEWS) {
    const p = matchPriority(e.match, name)
    if (p > bestP) { bestP = p; best = e }
  }
  if (!best) {
    return {
      icon: 'gear',
      statusText: phase === 'running' ? '执行中' : phase === 'pending' ? '待执行' : '已执行',
      viewId: 'fallback',
    }
  }
  return { ...best.head({ name, args, phase, count, ...extra }), viewId: best.id }
}

/** 命中的 entry；供 detail 解析复用，避免两次遍历逻辑不一致 */
function pick(name: string): ToolViewEntry | null {
  let best: ToolViewEntry | null = null
  let bestP: number = MatchPriority.NONE
  for (const e of TOOL_VIEWS) {
    const p = matchPriority(e.match, name)
    if (p > bestP) { bestP = p; best = e }
  }
  return best
}

/**
 * 解析展开明细。返回 null 表示该次调用不可展开（不出箭头）。
 *
 * 三种情况都返回 null，这是刻意的：
 *  1. 视图没实现 detail   → 纯头部视图，对齐 WorkBuddy 的 10 个 header-only view
 *  2. 结果不是 JSON       → 被截断或非结构化，不猜内容
 *  3. detail 判定无内容   → 空面板比不展开更糟
 */
export function resolveToolDetail(
  name: string,
  args: Record<string, unknown> = {},
  resultPreview?: string,
): ToolDetail | null {
  const e = pick(name)
  if (!e?.detail) return null
  // 结果解析失败不等于没内容：像 shell_run 这样命令本身就在参数里，
  // 结果被截断时仍应能展开看到执行了什么。所以退化成空结果交给
  // detail 自行判断，由它决定「有没有值得展开的东西」。
  let result: Record<string, unknown> = {}
  try {
    const parsed = JSON.parse(resultPreview || '{}')
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      result = parsed as Record<string, unknown>
    }
  } catch { /* 非 JSON：按空结果处理，不猜内容 */ }
  try {
    return e.detail({ name, args, result })
  } catch {
    // 单个工具的 detail 抛错不应带走整条对话
    // （对标 WorkBuddy 给每个 view 包 ToolErrorBoundary）
    return null
  }
}
