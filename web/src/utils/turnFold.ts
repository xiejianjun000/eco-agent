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
