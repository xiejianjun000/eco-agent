/**
 * widget.ts — show_widget 围栏解析（对标 WorkBuddy 可视化器）。
 *
 * 实证：app.asar renderer/assets 中
 *   FENCE_START_REGEX = /```(show_widget|show-widget|widget|visualizer_widget)\s*\n?/gi
 *   widgetToolName = "show_widget"
 * agent 用 ```show_widget 围栏输出 widget_code（SVG/HTML 片段），
 * 前端解析后内联进对话流（非文件），标准画布 viewBox 0 0 680。
 *
 * 本模块只做「围栏 → widget_code」提取（纯函数、可单测），渲染在 WidgetView。
 */

export interface WidgetBlock {
  /** 原始围栏内容 */
  code: string;
  /** svg | html | unknown（按内容判定） */
  kind: 'svg' | 'html' | 'unknown';
  /** 围栏标记名（show_widget / show-widget / widget / visualizer_widget） */
  marker: string;
}

/** 对标 WorkBuddy FENCE_START_REGEX */
export const WIDGET_FENCE_RE = /```\s*(show_widget|show-widget|widget|visualizer_widget)\s*\n?/gi;

/** 标准画布尺寸（WorkBuddy viewBox 0 0 680） */
export const WIDGET_CANVAS_W = 680;

/** 判定 widget_code 类型：SVG 优先（含 <svg），其次含 HTML 标签，否则 unknown */
export function widgetKind(code: string): WidgetBlock['kind'] {
  const c = (code || '').trim().toLowerCase();
  if (/<\s*svg\b/.test(c)) return 'svg';
  if (/<\s*(div|section|table|canvas|ul|ol|p|h[1-6]|form)\b/.test(c)) return 'html';
  return 'unknown';
}

/** 从 markdown 正文里提取全部 show_widget 围栏块（保留顺序）。 */
export function extractWidgets(markdown: string): WidgetBlock[] {
  const out: WidgetBlock[] = [];
  if (!markdown) return out;
  // 重置 lastIndex（RE 带 g 标志，复用会从上次位置继续）
  WIDGET_FENCE_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = WIDGET_FENCE_RE.exec(markdown))) {
    const marker = m[1].toLowerCase();
    const afterFence = markdown.slice(m.index + m[0].length);
    const close = afterFence.search(/^```/m);
    const code = close >= 0 ? afterFence.slice(0, close) : afterFence;
    // 空围栏不产出（不臆造 widget）
    if (!code.trim()) continue;
    out.push({ code: code.trim(), kind: widgetKind(code), marker });
  }
  return out;
}

/** 把围栏块从 markdown 中摘除，返回干净正文（围栏交给 WidgetView 渲染）。 */
export function stripWidgetFences(markdown: string): string {
  if (!markdown) return markdown;
  WIDGET_FENCE_RE.lastIndex = 0;
  let result = markdown;
  // 从后往前删，避免 index 偏移
  const spans: Array<[number, number]> = [];
  let m: RegExpExecArray | null;
  while ((m = WIDGET_FENCE_RE.exec(markdown))) {
    const afterFence = markdown.slice(m.index + m[0].length);
    const close = afterFence.search(/^```/m);
    const end = close >= 0 ? m.index + m[0].length + close : markdown.length;
    spans.push([m.index, Math.min(end + 3, markdown.length)]);
  }
  for (let i = spans.length - 1; i >= 0; i--) {
    result = result.slice(0, spans[i][0]) + result.slice(spans[i][1]);
  }
  return result;
}
