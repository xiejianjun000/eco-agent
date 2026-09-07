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
  text: string;
  detail?: string;
  ok?: boolean;
  ms?: number;
  running?: boolean;   // 工具已发出、结果未回（实时态）
}

/** 工具名 → 中文动作词（与后端 _NARR_ACTION 同源，前端独立一份避免多一次往返） */
const ACTION: Record<string, string> = {
  file_read: '读取', file_write: '写入', file_edit: '修改',
  save_document: '生成文档', generate_pptx: '生成课件',
  tdocs_upload_html: '上传腾讯文档', chart_render: '出图',
  shell_run: '执行命令', execute_code: '运行代码', glob: '查找文件',
  grep: '搜索内容', analyze_document: '分析文档',
  kb_search: '检索知识库', kb_semantic_search: '语义检索',
  statute_search: '检索法条', statute_lookup: '查法条',
  statute_related: '查关联法条', web_search: '联网搜索',
  web_fetch: '抓取网页', open_url: '打开网页',
  hunan_case_list: '查案卷台账', query_air_quality: '查空气质量',
  inspect: '自检', audit_tail: '查审计链', session_log_tail: '查日志',
  api_probe: '探测接口', detect_data_anomaly: '检测异常',
  calculate_carbon_emission: '核算碳排',
};

export function actionOf(name: string | undefined): string {
  if (!name) return '执行';
  if (name.startsWith('mcp__')) return 'MCP 调用';
  return ACTION[name] ?? name;
}

/** 从工具参数里挑一个可读的对象名 */
export function objectOf(args: unknown): string {
  if (!args || typeof args !== 'object') return '';
  const a = args as Record<string, unknown>;
  for (const k of ['path', 'file', 'filename', 'query', 'q', 'command', 'url',
                   'keyword', 'title', 'kind', 'pattern']) {
    const v = a[k];
    if (typeof v === 'string' && v.trim()) {
      let s = v.trim();
      if (k !== 'command' && s.includes('/')) s = s.split('/').pop() || s;
      return s.length > 32 ? `${s.slice(0, 32)}…` : s;
    }
  }
  return '';
}

/**
 * 把一轮 trace 编织成节奏时间线。
 * narration → say 行；tool → act 行（动作 + 对象 + 结果摘要）。
 * 保持事件原始顺序，因此并行调用的多个工具会各占一行，读起来仍是逐步推进。
 */
export function buildBeats(
  trace: { type?: string; text?: string; name?: string; args?: unknown;
           result_preview?: string; cost_ms?: number }[],
  isError: (s: string | undefined) => boolean,
): BeatItem[] {
  const out: BeatItem[] = [];
  for (const t of trace) {
    if (t.type === 'narration') {
      const c = cleanNarration(t.text);
      if (c && !(out.length && out[out.length - 1].kind === 'say'
                 && out[out.length - 1].text === c)) {
        out.push({ kind: 'say', text: c });
      }
    } else if (t.type === 'tool_start') {
      /* 实时态：工具已发出但未返回。先占一行「进行中」，
         等 tool 事件到达时由下面的分支原地替换为完成行。
         没有这一行的话，用户在工具执行的几十秒里看不到任何进展。 */
      const obj = objectOf(t.args);
      out.push({
        kind: 'act',
        text: `${actionOf(t.name)}${obj ? ` ${obj}` : ''}`,
        running: true,
      });
    } else if (t.type === 'tool') {
      // 有对应的 running 行就原地替换，避免同一次调用出现两行
      const key = `${actionOf(t.name)}${objectOf(t.args) ? ` ${objectOf(t.args)}` : ''}`;
      const idx = out.findIndex((b) => b.kind === 'act' && b.running && b.text === key);
      if (idx >= 0) {
        out[idx] = {
          kind: 'act',
          text: key,
          detail: summarizeResult(t.result_preview),
          ok: !isError(t.result_preview),
          ms: t.cost_ms,
        };
        continue;
      }
      const obj = objectOf(t.args);
      out.push({
        kind: 'act',
        text: `${actionOf(t.name)}${obj ? ` ${obj}` : ''}`,
        detail: summarizeResult(t.result_preview),
        ok: !isError(t.result_preview),
        ms: t.cost_ms,
      });
    }
  }
  return out;
}

/**
 * 把工具返回压成一句人话。
 *
 * 直接取 result_preview 首行会得到一坨原始 JSON
 * （实测「{"ok": true, "exit": 0, "stdout": "total 3408\ndrwxr-x…」），
 * 那是给机器看的，不是给用户看执行节奏用的。这里只抽关键计数/状态。
 */
export function summarizeResult(raw: string | undefined): string | undefined {
  const s = (raw ?? '').trim();
  if (!s) return undefined;

  if (s.startsWith('{') || s.startsWith('[')) {
    try {
      const o = JSON.parse(s);
      const r = Array.isArray(o) ? { count: o.length } : (o as Record<string, unknown>);

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
      if (typeof r.path === 'string') {
        const n = r.path.split('/').pop() || r.path;
        const lines = typeof r.content === 'string' ? r.content.split('\n').length : 0;
        return lines ? `${n} · ${lines} 行` : n;
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
      const cnt = m(/"count"\s*:\s*(\d+)/) ?? m(/"total"\s*:\s*(\d+)/);
      if (cnt) return `${cnt} 条`;
      const path = m(/"path"\s*:\s*"([^"]+)"/);
      if (path) return path.split('/').pop() || path;
      if (/"ok"\s*:\s*true/.test(s)) return '完成';
      /* 抠不出任何结构化线索：不返回 undefined（那会让这一行没有任何结果提示），
         落到下面的纯文本分支，至少给出首行内容。 */
    }
  }
  const first = s.split('\n')[0].trim();
  if (!first) return undefined;
  return first.length > 46 ? `${first.slice(0, 46)}…` : first;
}
