/**
 * web/src/utils/turnFold.ts — 轮次锚点分段（WorkBuddy turn-fold-anchors 对标）
 *
 * 解决的问题：一轮里工具调用很多，全展开刷屏、全折叠又看不到在干什么。
 * WorkBuddy 的答案是「锚点」——把 assistant 的正文段落挑出来常显，
 * 工具调用夹在锚点之间折叠。用户看到的就是：
 *
 *   先看 helper 签名和可复用函数。          ← 锚点（常显）
 *     [3 个工具调用]                        ← 过程段（可折叠）
 *   接口清楚了。现在三个工具并行开发。        ← 锚点（常显）
 *     [4 个工具调用]                        ← 过程段（可折叠）
 *   四个文件语法检查通过，部署。             ← 锚点（常显）
 *
 * 对标源码：packages/cb-chat-ui/src/components/message-timeline/
 *          mata-fold/turn-fold-anchors.ts
 *
 * 锚点选择规则（computeTurnFoldAnchors 原文）：
 *   「计算 turn-fold 折叠态常显锚点：所有最长正文 + 最后一条正文，按原始顺序去重。」
 */

import { resolveToolHead } from './toolViews';

export interface FoldItem<T> {
  content: T;
  index: number;
}

export type SegmentKind = 'hidden' | 'anchor' | 'process';

export interface FoldSegment<T> {
  kind: SegmentKind;
  items: FoldItem<T>[];
}

/** 取正文长度；非正文返回 0（对标 getBodyTextLength） */
export function bodyTextLength(text: string | undefined | null): number {
  return typeof text === 'string' ? text.trim().length : 0;
}

/** 对标 normalizeTurnFoldItems：补上全局 index */
export function normalizeItems<T>(contents: T[]): FoldItem<T>[] {
  return contents.map((content, index) => ({ content, index }));
}

/**
 * 对标 computeTurnFoldAnchors。
 * 锚点 = 所有「最长正文」+「最后一条正文」，按原始顺序去重。
 *
 * 注意这里是「所有最长」而非「唯一最长」——多条并列最长时全部入选，
 * 这是源码 `entry.length === maxLength` 的语义，不能改成取第一条。
 */
export function computeAnchors<T>(
  items: FoldItem<T>[],
  getText: (c: T) => string | undefined | null,
): FoldItem<T>[] {
  const bodies: { item: FoldItem<T>; length: number }[] = [];
  let maxLength = 0;
  for (const item of items) {
    const length = bodyTextLength(getText(item.content));
    if (length <= 0) continue;
    bodies.push({ item, length });
    if (length > maxLength) maxLength = length;
  }
  if (bodies.length === 0) return [];

  const anchorIndexes = new Set<number>();
  for (const b of bodies) if (b.length === maxLength) anchorIndexes.add(b.item.index);
  anchorIndexes.add(bodies[bodies.length - 1].item.index);  // 最后一条正文必为锚点

  return bodies.filter((b) => anchorIndexes.has(b.item.index)).map((b) => b.item);
}

/** 对标 collectEntries */
function collectEntries<T>(
  items: FoldItem<T>[], start: number, end: number,
  shouldSkip?: (c: T) => boolean,
): FoldItem<T>[] {
  const out: FoldItem<T>[] = [];
  for (let i = start; i < end; i++) {
    const item = items[i];
    if (!item || shouldSkip?.(item.content)) continue;
    out.push(item);
  }
  return out;
}

/**
 * 对标 buildTurnFoldSegments。
 * 「基于锚点把整轮内容切成隐藏段、常显锚点和锚点间过程消息段。
 *   过程消息段排除 hoisted widget，确保 showWidget 仍搬到末尾。」
 *
 * 段序：[hidden?] anchor [process?] anchor [process?] … anchor
 * 首个锚点之前的内容归入 hidden；最后一个锚点之后不再产生 process 段
 * （源码 `if (!nextAnchor) return`），那部分由调用方的 widget hoist 接管。
 */
export function buildSegments<T>(
  contents: T[],
  getText: (c: T) => string | undefined | null,
  isHoisted: (c: T) => boolean = () => false,
): FoldSegment<T>[] {
  const items = normalizeItems(contents);
  const anchors = computeAnchors(items, getText);
  if (anchors.length === 0) return [];

  const segments: FoldSegment<T>[] = [];

  const leading = collectEntries(items, 0, anchors[0].index);
  if (leading.length > 0) segments.push({ kind: 'hidden', items: leading });

  anchors.forEach((anchor, i) => {
    segments.push({ kind: 'anchor', items: [anchor] });
    const next = anchors[i + 1];
    if (!next) return;
    const process = collectEntries(items, anchor.index + 1, next.index, isHoisted);
    if (process.length > 0) segments.push({ kind: 'process', items: process });
  });

  return segments;
}

/**
 * 轮次耗时（对标 computeTurnDurationMs / getAssistantEndTime）。
 *
 * 源码注释指出这是 issue #59036 的修复关键：长耗时任务的 assistant 消息，
 * createTime 锁定在「开始流式输出」时刻其后不再刷新，用它做差值会严重偏短；
 * finishTime 在真正结束时写入，才反映含全部工具执行的真实耗时。
 */
export function assistantEndTime(m: { finishTime?: number; createTime?: number }): number | undefined {
  return m.finishTime ?? m.createTime;
}

// ── 旁白清洗（机制级兜底，不依赖模型遵守规则 8.1）──────────────────

/** 内部状态词：出现即说明模型在自述系统机制，而非汇报任务进度 */
const INTERNAL_STATE_RE =
  /(上一轮|上次会话|本轮|超时中断|重试第?\s*\d*\s*次|提示词|系统提示|闸门|轮次\s*\d|round\s*\d)/i;

/** 空泛套话：没有信息量的旁白 */
const VAGUE_RE = /^\s*(正在处理|让我看看|稍等|马上|好的|收到|开始处理|继续)[。.!！…]*\s*$/;

/**
 * 清洗一条旁白：返回 null 表示该丢弃。
 * 规则 8.1 已在提示词里要求，这里做机制兜底——实测模型会写出
 * 「上一轮这个任务因 LLM 超时中断了」这类系统自述，必须拦掉。
 */
/**
 * 工具标识符 → 自然说法。
 *
 * WorkBuddy craft/fragments/tool-use.md 原文硬规则：
 *   "NEVER mention specific tool names in user-facing messages or status descriptions."
 * 实测 eco 旁白 13 条里 5 条泄露工具名（38%）。提示词是软约束，
 * 这里做硬兜底 —— 模型漏写时前端替换，而不是把标识符糊给用户。
 */
const TOOL_NAME_SUBS: [RegExp, string][] = [
  [/\bmcp__[a-zA-Z0-9_-]+__([a-zA-Z0-9_]+)/g, '外部服务'],
  // 截断残片：模型输出被裁断时会留下 "mcp__eco-hunan-env__" 这种没有内层名的
  // 半截串，上一条要求 __内层名 故匹配不到，于是原样漏进 DOM。
  // 实测浏览器里抓到 6 处，全是这个形态。必须排在完整式之后。
  [/\bmcp__[a-zA-Z0-9_-]+__?/g, '外部服务'],
  [/\b(audit_tail|审计链工具)\b/gi, '审计链'],
  [/\bsession_log_tail\b/gi, '会话日志'],
  [/\bshell_run\b/gi, '命令行'],
  [/\bexecute_code\b/gi, '代码执行'],
  [/\bfile_read\b/gi, '读取'],
  [/\bfile_write\b/gi, '写入'],
  [/\bfile_edit\b/gi, '编辑'],
  [/\bchart_render\b/gi, '出图'],
  [/\bkb_semantic_search\b/gi, '语义检索'],
  [/\bkb_search\b/gi, '知识库检索'],
  [/\bstatute_(search|lookup|related)\b/gi, '法条检索'],
  [/\bweb_(search|fetch)\b/gi, '联网检索'],
  [/\b(glob|grep)\b/gi, '检索'],
  [/\binspect\b/gi, '自检'],
  [/\bMCP\b/g, '外部服务'],
];

/** 去掉旁白里的工具标识符，换成自然说法 */
export function stripToolNames(t: string): string {
  let out = t;
  for (const [re, rep] of TOOL_NAME_SUBS) out = out.replace(re, rep);
  // 「用检索扫」「调用外部服务查」这类残留句式收一下
  out = out.replace(/(?:用|调用|通过)\s*(检索|自检|外部服务|命令行|审计链)\s*(工具)?\s*/g, '');
  return out.replace(/\s{2,}/g, ' ').trim();
}

export function cleanNarration(text: string | undefined | null): string | null {
  if (typeof text !== 'string') return null;
  const t = stripToolNames(text.trim());
  if (!t) return null;
  if (VAGUE_RE.test(t)) return null;
  if (INTERNAL_STATE_RE.test(t)) return null;
  return t.length > 120 ? `${t.slice(0, 120)}…` : t;
}

/** 相邻去重：模型偶尔连发同一句，只保留一条 */
export function dedupeAdjacent(texts: string[]): string[] {
  const out: string[] = [];
  for (const t of texts) if (t !== out[out.length - 1]) out.push(t);
  return out;
}

// ── 执行节奏时间线 ──────────────────────────────────────────────
//
// 用户要的效果：「思考一下，输出一行，查看文件，输出一行，修改文件，输出一行…」
//
// 直接做法是强制模型串行调工具（每次只发一个 + 一行旁白），但那会牺牲并行
// 速度——实测模型一轮并行发 3 个工具只需 20s，串行要 60s+。
// 折中：保留并行，由 UI 把「旁白」与「每个工具」按发生顺序交织成时间线，
// 每个工具自带动作词与结果摘要，读起来仍是一步一行的节奏。

export type BeatState = 'running' | 'ok' | 'error' | 'skipped';

export interface BeatItem {
  /**
   * WorkBuddy block 对齐：
   *  say   → 旁白（narration，折叠锚点）
   *  act   → 工具块（tool-call：运行中/成功/失败/跳过）
   *  think → 思考块（reasoning，可折叠）
   *  task  → 任务块（taskList：RoleSwarm 三角色协作进度）
   */
  kind: 'say' | 'act' | 'think' | 'task';
  /** act = 主体（文件名/命令/查询词）；say = 旁白全文；think/task = 标题 */
  text: string;
  /** 动词，仅 act：已读取 / 读取中（对标 WorkBuddy statusText） */
  status?: string;
  /** 次要信息，仅 act：3 条 / 15 行（对标 secondaryInfo） */
  secondary?: string;
  /** 命中的工具视图 id，落到 DOM data-tool-view 便于断言；未命中为 'fallback'
   *  （对标 WorkBuddy ToolbarShell 的 debugAttrs） */
  viewId?: string;
  /** 写文件类的变更行数，渲染为分色 +N -M */
  added?: number;
  removed?: number;
  /** 展开明细所需的原始信息（仅 act）。
   *  刻意只存这三样：工具名、参数、结果预览，
   *  由 resolveToolDetail 在渲染时解析成结构化明细。 */
  toolName?: string;
  toolArgs?: unknown;
  resultPreview?: string;
  /** running↔done 配对键，内部用 */
  key?: string;
  ok?: boolean;
  ms?: number;
  running?: boolean;
  /** 完整工具状态机（对标 WorkBuddy ToolState；兼容旧布尔 running） */
  state?: BeatState;
  /** 命令/代码执行退出码（对标 tool.executeCommand.exitCode） */
  exitCode?: number;
  /** 思考块正文（reasoning 完整内容，折叠在头部下） */
  body?: string;
  /** 任务块：子步骤（RoleSwarm 巡查/法规/文书 + 总管合成） */
  steps?: { label: string; state: BeatState | 'pending'; ms?: number }[];
}

/**
 * 工具三态文案（对标 WorkBuddy tool.<id>.{running,done,error}）。
 *
 * WorkBuddy 每个工具块严格分三段，职责不重叠：
 *   [图标] 已读取        README.md      L1-10
 *          statusText    primaryContent secondaryInfo
 *          动词·两态      主体·可点       次要信息
 *
 * 实测原文：tool.readFile.running=读取中 / done=已读取
 *          tool.listFiles.searched=已搜索，primary=目录，secondary=查询词
 * execute_command 的 statusText 刻意为空 —— 命令本身就是主体。
 *
 * eco 此前把动词和对象拼成一句再重复一遍
 * （「读取 README.md — README.md · 5 行」），正是没分清这三段。
 */
interface Phrase { running: string; done: string }

const PHRASE: Record<string, Phrase> = {
  file_read: { running: '读取中', done: '已读取' },
  file_write: { running: '写入中', done: '已写入' },
  file_edit: { running: '修改中', done: '已修改' },
  save_document: { running: '生成文档中', done: '已生成文档' },
  generate_pptx: { running: '生成课件中', done: '已生成课件' },
  tdocs_upload_html: { running: '上传中', done: '已上传腾讯文档' },
  chart_render: { running: '出图中', done: '已出图' },
  shell_run: { running: '执行中', done: '' },        // 命令即主体，完成态不加动词
  execute_code: { running: '运行中', done: '已运行' },
  glob: { running: '查找中', done: '已查找' },
  grep: { running: '搜索中', done: '已搜索' },
  analyze_document: { running: '分析中', done: '已分析' },
  kb_search: { running: '检索中', done: '已检索' },
  kb_semantic_search: { running: '语义检索中', done: '已语义检索' },
  statute_search: { running: '检索法条中', done: '已检索法条' },
  statute_lookup: { running: '查条文中', done: '已查条文' },
  statute_related: { running: '查关联条文中', done: '已查关联条文' },
  web_search: { running: '搜索网页中', done: '已搜索网页' },
  web_fetch: { running: '抓取中', done: '已抓取' },
  open_url: { running: '打开中', done: '已打开' },
  hunan_case_list: { running: '查台账中', done: '已查台账' },
  query_air_quality: { running: '查空气质量中', done: '已查空气质量' },
  inspect: { running: '自检中', done: '已自检' },
  audit_tail: { running: '读审计链中', done: '已读审计链' },
  session_log_tail: { running: '读日志中', done: '已读日志' },
  api_probe: { running: '探测中', done: '已探测' },
  detect_data_anomaly: { running: '检测中', done: '已检测' },
  calculate_carbon_emission: { running: '核算中', done: '已核算' },
};

const UNKNOWN: Phrase = { running: '执行中', done: '已完成' };

/** 动词（statusText）：区分运行态与完成态，对标 tool.*.running / done */
export function statusTextOf(name: string | undefined, running: boolean): string {
  if (name && name.startsWith('mcp__')) return running ? '调用 MCP 中' : '已调用 MCP';
  const ph = (name && PHRASE[name]) || UNKNOWN;
  return running ? ph.running : ph.done;
}

/**
 * 截断到 n 字符，但不切在成对标点或分隔符中间。
 * 实测出现过「已出图 m³）」—— 图表标题 "…（μg/m³）" 被硬切在括号里，
 * 只剩一个右括号，读起来是乱码。
 */
function clip(t: string, n: number): string {
  if (t.length <= n) return t;
  let cut = t.slice(0, n);
  // 左括号多于右括号 → 切点落在未闭合的括号内，回退到该左括号之前。
  // 实测「已出图 m³）」就是半截括号造成的（那次还叠加了斜杠误取 basename）。
  const opens = (cut.match(/[（(【[]/g) || []).length;
  const closes = (cut.match(/[）)】\]]/g) || []).length;
  if (opens > closes) {
    const i = cut.search(/[（(【[][^（(【[]*$/);
    if (i > 0) cut = cut.slice(0, i);
  }
  return `${cut.replace(/[\s，,、·—-]+$/, '')}…`;
}

/** 主体（primaryContent）：对象名，不与动词重复 */
export function primaryOf(name: string | undefined, args: unknown): string {
  // MCP 工具：mcp__<server>__<tool> → 显示 <tool>，
  // 不要把参数里的整坨 JSON 当主体（实测出现过
  // 「已调用 MCP{"success": true, "is_error": false, …」）。
  if (name && name.startsWith('mcp__')) {
    const parts = name.split('__');
    return parts[parts.length - 1] || name;
  }
  if (!args || typeof args !== 'object') return '';
  const a = args as Record<string, unknown>;
  // shell 命令：整条命令就是主体
  if (name === 'shell_run' || name === 'execute_code') {
    const c = typeof a.command === 'string' ? a.command : (typeof a.code === 'string' ? a.code : '');
    return clip(c, 46);
  }
  // 路径类字段才取 basename
  for (const k of ['path', 'file', 'filename', 'directory', 'root']) {
    const v = a[k];
    if (typeof v === 'string' && v.trim()) {
      const t = v.trim();
      return clip(t.includes('/') ? (t.split('/').pop() || t) : t, 34);
    }
  }
  // 标题/URL 原样保留 —— 实测「已出图 m³）」正是把图表标题
  // 「…（单位 μg/m³）」按斜杠切了 basename，只剩尾巴。
  for (const k of ['title', 'url']) {
    const v = a[k];
    if (typeof v === 'string' && v.trim()) return clip(v.trim(), 34);
  }
  // 检索类：查询词即主体
  for (const k of ['query', 'q', 'keyword', 'pattern']) {
    const v = a[k];
    if (typeof v === 'string' && v.trim()) return clip(v.trim(), 34);
  }
  return '';
}

/**
 * 把一轮 trace 编织成节奏时间线（三段式块，对标 WorkBuddy ToolHeader）。
 *
 * say  → 旁白行（模型交代下一步）
 * act  → 工具块：status(动词) + primary(主体) + secondary(次要) + 耗时
 */
const SWARM_TOOLS = new Set(['swarm_patrol', 'swarm_law', 'swarm_doc']);
const SWARM_ROLE_LABEL: Record<string, string> = {
  swarm_patrol: '巡查 Agent',
  swarm_law: '法规 Agent',
  swarm_doc: '文书 Agent',
};
/** RoleSwarm 阶段旁白（这些 think 只服务任务块，不单独渲染成思考行） */
function swarmMarker(thought?: string): null | 'start' | 'parallel' | 'drafting' | 'synth' {
  const t = thought || '';
  if (t.includes('三角色协作 DAG')) return 'start';
  if (t.includes('并行执行中')) return 'parallel';
  if (t.includes('文书 Agent 起草中') || t.includes('文书Agent 起草中')) return 'drafting';
  if (t.includes('总管仲裁合成完成') || t.includes('总管合成')) return 'synth';
  return null;
}

/** 从命令/代码执行结果里取退出码（对标 tool.executeCommand.exitCode） */
export function exitCodeOf(raw: string | undefined): number | undefined {
  try {
    const r = JSON.parse(raw || '{}');
    for (const k of ['exit_code', 'exitCode', 'exit', 'returncode']) {
      if (typeof r[k] === 'number') return r[k];
    }
  } catch { /* 非 JSON/截断：不猜 */ }
  return undefined;
}

/** 工具是否被显式跳过（数据驱动，结果里带 skipped/status 才认，不靠文案猜） */
function skippedOf(raw: string | undefined): boolean {
  try {
    const r = JSON.parse(raw || '{}');
    return r.skipped === true || r.status === 'skipped';
  } catch { return false; }
}

export function buildBeats(
  trace: { type?: string; text?: string; thought?: string; name?: string; args?: unknown;
           result_preview?: string; cost_ms?: number; round?: number }[],
  isError: (s: string | undefined) => boolean,
): BeatItem[] {
  const out: BeatItem[] = [];
  const keyOf = (t: { name?: string; args?: unknown }) =>
    `${t.name ?? ''}|${primaryOf(t.name, t.args)}`;

  // ── RoleSwarm 任务块（对标 WorkBuddy taskList）：把 swarm_* 工具 + 阶段旁白
  //    聚合成「一个」协作任务块，步骤随进度 running→ok，而不是堆成普通工具行。
  const hasSwarm = trace.some((t) =>
    (t.type === 'tool' && SWARM_TOOLS.has(t.name || '')) || swarmMarker(t.thought));
  const doneRole: Record<string, { ms?: number }> = {};
  for (const t of trace) {
    if (t.type === 'tool' && SWARM_TOOLS.has(t.name || '')) {
      doneRole[t.name as string] = { ms: t.cost_ms };
    }
  }
  const markers = new Set(trace.map((t) => swarmMarker(t.thought)).filter(Boolean) as string[]);
  let taskEmitted = false;
  const liveThink: Record<number, { text: string; idx: number }> = {};  // round → 累积思考及其行下标
  let thinkSeq = 0;

  const emitTask = () => {
    if (taskEmitted) return;
    taskEmitted = true;
    const patrol: BeatState = doneRole.swarm_patrol ? 'ok' : 'running';
    const law: BeatState = doneRole.swarm_law ? 'ok' : patrol;
    const doc: BeatState | 'pending' = doneRole.swarm_doc ? 'ok'
      : (markers.has('drafting') ? 'running' : 'pending');
    const synth: BeatState | 'pending' = markers.has('synth') ? 'ok'
      : (doneRole.swarm_doc ? 'running' : 'pending');
    const step = (label: string, st: BeatState | 'pending', ms?: number) =>
      ({ label, state: st, ...(ms ? { ms } : {}) });
    out.push({
      kind: 'task',
      key: 'swarm-task',
      text: '三角色协作执法',
      state: synth === 'ok' ? 'ok' : 'running',
      running: synth !== 'ok',
      steps: [
        step('巡查', patrol, doneRole.swarm_patrol?.ms),
        step('法规', law, doneRole.swarm_law?.ms),
        step('文书', doc, doneRole.swarm_doc?.ms),
        { label: '总管合成', state: synth },
      ],
    });
  };

  for (const t of trace) {
    // 思考块（reasoning）：think_delta 按轮累积、think 权威覆盖。
    if (t.type === 'think_delta') {
      const r = t.round ?? 1;
      if (!liveThink[r]) {
        const idx = out.length;
        out.push({ kind: 'think', key: `think-live-${r}-${thinkSeq++}`, text: '思考中',
                   state: 'running', running: true, body: '' });
        liveThink[r] = { text: '', idx };
      }
      liveThink[r].text += t.text || '';
      out[liveThink[r].idx].body = liveThink[r].text;
      continue;
    }
    if (t.type === 'think') {
      const marker = hasSwarm ? swarmMarker(t.thought) : null;
      if (hasSwarm && marker) {
        if (!taskEmitted) emitTask();
        continue;  // 阶段旁白并入任务块
      }
      const r = t.round ?? 1;
      const thought = t.thought || '';
      if (!thought) continue;
      const pending = liveThink[r];
      if (pending) {  // 权威版覆盖流式累积
        out[pending.idx] = {
          kind: 'think', key: `think-${r}`, text: '思考', state: 'ok',
          body: thought, ms: t.cost_ms,
        };
        delete liveThink[r];
      } else {
        out.push({ kind: 'think', key: `think-${r}-${thinkSeq++}`, text: '思考',
                   state: 'ok', body: thought, ms: t.cost_ms });
      }
      continue;
    }
    if (hasSwarm && t.type === 'tool' && SWARM_TOOLS.has(t.name || '')) {
      if (!taskEmitted) emitTask();
      // 更新任务块步骤状态（重新生成 steps）
      const ti = out.findIndex((b) => b.kind === 'task');
      if (ti >= 0) {
        const role = t.name as string;
        const st: BeatState = isError(t.result_preview) ? 'error' : 'ok';
        out[ti].steps = (out[ti].steps || []).map((s) =>
          s.label === SWARM_ROLE_LABEL[role].replace(' Agent', '')
            ? { ...s, state: st, ms: t.cost_ms } : s);
      }
      continue;
    }
    if (t.type === 'narration') {
      const c = cleanNarration(t.text);
      if (c && !(out.length && (out[out.length - 1].kind === 'say'
                 || out[out.length - 1].kind === 'think')
                 && (out[out.length - 1].text === c
                     || normText(out[out.length - 1].body) === normText(c)))) {
        out.push({ kind: 'say', text: c });
      }
    } else if (t.type === 'tool_start') {
      {
        // 每工具独立视图（见 utils/toolViews.ts 与 docs/RENDER_SPEC.md §3）。
        const h = resolveToolHead(t.name || '', (t.args || {}) as Record<string, unknown>, 'running');
        out.push({
          kind: 'act',
          status: h.statusText || statusTextOf(t.name, true),
          text: h.primaryContent || primaryOf(t.name, t.args),
          viewId: h.viewId,
          toolName: t.name,
          toolArgs: t.args,
          key: keyOf(t),
          running: true,
          state: 'running',
        });
      }
    } else if (t.type === 'tool') {
      const failed = isError(t.result_preview);
      const exitCode = exitCodeOf(t.result_preview);
      const skipped = skippedOf(t.result_preview);
      // 退出码非 0 即失败（对标 exitCode 校验）；显式 skipped 优先。
      const state: BeatState = skipped ? 'skipped'
        : (failed || (exitCode !== undefined && exitCode !== 0) ? 'error' : 'ok');
      // 从工具结果里取变更行数（对标 WorkBuddy writeFile 的 +N -M）
      let diff: { added?: number; removed?: number } | undefined;
      try {
        const r = JSON.parse(t.result_preview || '{}');
        const a = r.added_lines ?? r.added;
        const d = r.removed_lines ?? r.removed;
        if (typeof a === 'number' || typeof d === 'number') {
          diff = { added: typeof a === 'number' ? a : 0, removed: typeof d === 'number' ? d : 0 };
        }
      } catch { /* 结果非 JSON 或被截断：不显示行数，不猜 */ }
      const hd = resolveToolHead(
        t.name || '', (t.args || {}) as Record<string, unknown>,
        state === 'error' ? 'error' : 'success', undefined, diff,
      );
      const done: BeatItem = {
        kind: 'act',
        status: state === 'skipped' ? '已跳过' : (hd.statusText || statusTextOf(t.name, false)),
        text: hd.primaryContent || primaryOf(t.name, t.args),
        viewId: hd.viewId,
        added: hd.added,
        removed: hd.removed,
        toolName: t.name,
        toolArgs: t.args,
        resultPreview: t.result_preview,
        key: keyOf(t),
        secondary: summarizeResult(t.result_preview),
        ok: state === 'ok',
        state,
        ...(exitCode !== undefined ? { exitCode } : {}),
        ms: t.cost_ms,
      };
      // 有对应 running 行就原地替换，避免同一次调用出现两行
      const idx = out.findIndex((b) => b.kind === 'act' && b.running && b.key === done.key);
      if (idx >= 0) out[idx] = done;
      else out.push(done);
    }
  }
  return out;
}

function normText(s: string | undefined): string {
  return (s || '').replace(/\s+/g, '').trim();
}

export function summarizeResult(raw: string | undefined): string | undefined {
  const s = (raw ?? '').trim();
  if (!s) return undefined;

  if (s.startsWith('{') || s.startsWith('[')) {
    try {
      const o = JSON.parse(s);
      let r = Array.isArray(o) ? { count: o.length } : (o as Record<string, unknown>);

      /* MCP 工具返回是双层 JSON：外层 {success, is_error, text}，
         text 本身又是一段 JSON 字符串。实测界面上直接糊出
         「{"success": true, "is_error": false, "text": "…」。
         这里剥掉外层，对内层再走一遍同样的摘要规则。 */
      if (typeof r.success === 'boolean' && typeof r.text === 'string') {
        if (r.success === false || r.is_error === true) return '失败';
        const inner = summarizeResult(r.text);
        if (inner) return inner;
        const t = r.text.trim();
        return t ? (t.length > 40 ? `${t.slice(0, 40)}…` : t) : '完成';
      }

      if (r.ok === false || typeof r.error === 'string') {
        const e = String(r.error ?? '失败');
        return `失败：${e.length > 40 ? `${e.slice(0, 40)}…` : e}`;
      }
      // 常见计数字段，按信息量优先
      for (const [k, label] of [['count', '条'], ['total', '条'], ['matches', '处']] as const) {
        if (typeof r[k] === 'number') return `${r[k]} ${label}`;
      }
      if (Array.isArray(r.files)) return `${r.files.length} 个文件`;
      if (Array.isArray(r.entries)) return `${r.entries.length} 条记录`;
      if (Array.isArray(r.results)) return `${r.results.length} 条结果`;
      if (Array.isArray(r.items)) return `${r.items.length} 条`;
      if (typeof r.path === 'string') {
        // 只报行数，不重复文件名 —— 文件名已由 primaryContent 显示。
        // 实测出现过「已读取 README.md  README.md · 5 行」这种重复。
        const lines = typeof r.content === 'string' ? r.content.split('\n').length : 0;
        return lines ? `${lines} 行` : undefined;
      }
      if (typeof r.stdout === 'string') {
        const lines = r.stdout.split('\n').filter(Boolean).length;
        return lines ? `${lines} 行输出` : '无输出';
      }
      if (r.ok === true) return '完成';
      return undefined;
    } catch {
      /* JSON.parse 失败的主因不是「不是 JSON」，而是被截断。
         后端 result_preview 只留 200 字符（chat.py:153），
         长返回必然在中途被砍成非法 JSON。这里用正则从残片里
         抠出关键计数/状态，而不是把半截 JSON 原样糊到界面上。 */
      const m = (re: RegExp) => s.match(re)?.[1];
      const err = m(/"error"\s*:\s*"([^"]{1,40})/);
      if (err) return `失败：${err}`;
      if (/"ok"\s*:\s*false/.test(s)) return '失败';

      /* MCP 双层返回被截断的情况（实测最常见）：
         外层 {"success":true,"is_error":false,"text":"{\n \"city\"…
         200 字符上限几乎必然砍在 text 中间，JSON.parse 一定失败，
         所以上面的对象分支根本走不到 —— 必须在正则兜底里也处理。 */
      if (/"success"\s*:\s*true/.test(s) && /"text"\s*:/.test(s)) {
        if (/"is_error"\s*:\s*true/.test(s)) return '失败';
        // 从被转义的内层 JSON 里抠线索：items 条数 / 城市 / AQI
        const city = m(/\\"(?:城市|city)\\"\s*:\s*\\"([^\\"]{1,16})/);
        const aqi = m(/\\"AQI\\"\s*:\s*\\"?(\d{1,3})/);
        if (city && aqi) return `${city} AQI ${aqi}`;
        if (city) return city;
        const total = m(/\\"total\\"\s*:\s*(\d+)/);
        if (total) return `${total} 条`;
        return '完成';
      }
      if (/"success"\s*:\s*false/.test(s) || /"is_error"\s*:\s*true/.test(s)) return '失败';
      const cnt = m(/"count"\s*:\s*(\d+)/) ?? m(/"total"\s*:\s*(\d+)/);
      if (cnt) return `${cnt} 条`;
      // 截断残片里的 path 同样不重复报文件名
      if (/"ok"\s*:\s*true/.test(s)) return '完成';
      /* 抠不出任何结构化线索：不返回 undefined（那会让这一行没有任何结果提示），
         落到下面的纯文本分支，至少给出首行内容。 */
    }
  }
  const first = s.split('\n')[0].trim();
  if (!first) return undefined;
  return first.length > 46 ? `${first.slice(0, 46)}…` : first;
}


// ── 成果卡片（对标 WorkBuddy present_files → artifact cards）─────────
//
// WorkBuddy result-presentation.md 规定：任务产生可查看成果时，
// 本轮最后一个工具调用必须是 present_files，界面渲染成可下载卡片。
// 没有统一入口时产物只能散落在过程块里，用户根本看不到。

export interface PresentedFile {
  path: string;
  name: string;
  ext: string;
  size: number;
}

/** 从一轮 trace 里抽出 present_files 呈现的成果文件（去重、保序） */
export function extractPresented(
  trace: { type?: string; name?: string; result_preview?: string }[],
): PresentedFile[] {
  const seen = new Set<string>();
  const out: PresentedFile[] = [];
  for (const t of trace) {
    if (t.type !== 'tool' || t.name !== 'present_files') continue;
    const raw = (t.result_preview ?? '').trim();
    if (!raw) continue;
    let files: unknown;
    try {
      files = (JSON.parse(raw) as { files?: unknown }).files;
    } catch {
      /* result_preview 截到 200 字符时 JSON 可能不完整，
         用正则从残片里抠已完整的 {path,name,...} 对象 */
      const got: PresentedFile[] = [];
      const re = /"path":\s*"([^"]+)"[^}]*?"name":\s*"([^"]+)"[^}]*?"ext":\s*"([^"]*)"[^}]*?"size":\s*(\d+)/g;
      let m: RegExpExecArray | null;
      while ((m = re.exec(raw)) !== null) {
        got.push({ path: m[1], name: m[2], ext: m[3], size: Number(m[4]) });
      }
      files = got;
    }
    if (!Array.isArray(files)) continue;
    for (const f of files) {
      if (!f || typeof f !== 'object') continue;
      const r = f as Record<string, unknown>;
      const path = typeof r.path === 'string' ? r.path : '';
      if (!path || seen.has(path)) continue;
      seen.add(path);
      out.push({
        path,
        name: typeof r.name === 'string' ? r.name : (path.split('/').pop() || path),
        ext: typeof r.ext === 'string' ? r.ext : '',
        size: typeof r.size === 'number' ? r.size : 0,
      });
    }
  }
  return out;
}

/** 人类可读文件大小 */
export function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export interface WebSource {
  title: string;
  url: string;
  engine?: string;
  query?: string;
}

/**
 * 来源聚合（对标 WorkBuddy DetailPanel 的 sources 视图：web 搜索来源聚合）。
 * 从 web_search 工具结果里抽 {title,url}；result_preview 只有 200 字、常被截断，
 * 所以既尝试 JSON.parse，也用正则从残片抠 URL，绝不臆造（抠不到就不收录）。
 */
export function extractSources(
  trace: { type?: string; name?: string; args?: unknown; result_preview?: string }[],
): WebSource[] {
  const out: WebSource[] = [];
  const seen = new Set<string>();
  const push = (title: string | undefined, url: string | undefined, engine?: string, query?: string) => {
    const u = (url || '').trim();
    if (!/^https?:\/\//i.test(u) || seen.has(u)) return;
    seen.add(u);
    let host = '';
    try { host = new URL(u).hostname.replace(/^www\./, ''); } catch { /* ignore */ }
    out.push({ title: (title || '').trim() || host || u, url: u, engine, query });
  };
  for (const t of trace) {
    if (t.type !== 'tool' || t.name !== 'web_search') continue;
    const raw = t.result_preview || '';
    const query = (t.args as Record<string, unknown> | undefined)?.query;
    const q = typeof query === 'string' ? query : undefined;
    let parsed: Record<string, unknown> | null = null;
    try { parsed = JSON.parse(raw) as Record<string, unknown>; } catch { parsed = null; }
    if (parsed && Array.isArray(parsed.results)) {
      const engine = typeof parsed.engine === 'string' ? parsed.engine : undefined;
      for (const r of parsed.results as Array<Record<string, unknown>>) {
        push(typeof r.title === 'string' ? r.title : undefined,
             typeof r.url === 'string' ? r.url : (typeof r.link === 'string' ? r.link : undefined),
             engine, q);
      }
      continue;
    }
    // 截断残片：正则抠 {"title":"...","url":"..."}；URL 可能在闭合引号前被砍断
    // （result_preview 200 字上限），故允许匹配到串尾。
    const re = /"title"\s*:\s*"([^"]{1,120})"[\s\S]{0,160}?"(?:url|link)"\s*:\s*"(https?:[^"]*)/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(raw))) if (m[2]) push(m[1], m[2], undefined, q);
    // 只有裸 URL 也收录（标题退化为域名），同样允许无闭合引号的截断尾部
    const urlRe = /"(?:url|link)"\s*:\s*"(https?:[^"]*)/g;
    while ((m = urlRe.exec(raw))) if (m[1]) push(undefined, m[1], undefined, q);
  }
  return out.slice(0, 12);
}
