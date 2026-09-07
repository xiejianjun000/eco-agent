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
export function cleanNarration(text: string | undefined | null): string | null {
  if (typeof text !== 'string') return null;
  const t = text.trim();
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

export interface BeatItem {
  kind: 'say' | 'act';
  /** act = 主体（文件名/命令/查询词）；say = 旁白全文 */
  text: string;
  /** 动词，仅 act：已读取 / 读取中（对标 WorkBuddy statusText） */
  status?: string;
  /** 次要信息，仅 act：3 条 / 15 行（对标 secondaryInfo） */
  secondary?: string;
  /** running↔done 配对键，内部用 */
  key?: string;
  ok?: boolean;
  ms?: number;
  running?: boolean;
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
export function buildBeats(
  trace: { type?: string; text?: string; name?: string; args?: unknown;
           result_preview?: string; cost_ms?: number }[],
  isError: (s: string | undefined) => boolean,
): BeatItem[] {
  const out: BeatItem[] = [];
  const keyOf = (t: { name?: string; args?: unknown }) =>
    `${t.name ?? ''}|${primaryOf(t.name, t.args)}`;

  for (const t of trace) {
    if (t.type === 'narration') {
      const c = cleanNarration(t.text);
      if (c && !(out.length && out[out.length - 1].kind === 'say'
                 && out[out.length - 1].text === c)) {
        out.push({ kind: 'say', text: c });
      }
    } else if (t.type === 'tool_start') {
      out.push({
        kind: 'act',
        status: statusTextOf(t.name, true),
        text: primaryOf(t.name, t.args),
        key: keyOf(t),
        running: true,
      });
    } else if (t.type === 'tool') {
      const done: BeatItem = {
        kind: 'act',
        status: statusTextOf(t.name, false),
        text: primaryOf(t.name, t.args),
        key: keyOf(t),
        secondary: summarizeResult(t.result_preview),
        ok: !isError(t.result_preview),
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
