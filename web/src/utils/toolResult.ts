import { escapeHtml } from './markdown';

/** 工具结果增强渲染（对标 DSH output.render 轻量版）：
 *  结果若是 JSON（含 records/rows/tbody 等数组），自动表格化展示；
 *  否则转义原文。全部内容已转义，无 XSS 风险。 */
export function renderToolResult(text: string): string {
  if (!text || !text.trim().startsWith('{')) return escapeHtml(text);
  let obj: unknown;
  try {
    obj = JSON.parse(text);
  } catch {
    return escapeHtml(text);
  }
  if (!obj || typeof obj !== 'object') return escapeHtml(text);
  const rec = obj as Record<string, unknown>;
  const arr = [rec.records, rec.rows, rec.list, rec.tbody, rec.data]
    .find((v): v is unknown[] => Array.isArray(v) && v.length > 0);
  if (!arr || arr.length === 0) return escapeHtml(text);
  let html: string;
  const slice = arr.slice(0, 30);
  if (typeof arr[0] === 'object' && arr[0] !== null && !Array.isArray(arr[0])) {
    const keys = [...new Set(arr.flatMap((r) => Object.keys(r as object)))].slice(0, 6);
    html = '<table class="md-table"><thead><tr>' +
      keys.map((k) => `<th>${escapeHtml(String(k))}</th>`).join('') +
      '</tr></thead><tbody>';
    for (const r of slice) {
      html += '<tr>' + keys.map((k) =>
        `<td>${escapeHtml(String((r as Record<string, unknown>)[k] ?? ''))}</td>`).join('') + '</tr>';
    }
    html += '</tbody></table>';
  } else if (Array.isArray(arr[0])) {
    const head = Array.isArray(rec.thead) ? (rec.thead as unknown[]).slice(0, 8) : null;
    html = '<table class="md-table">' +
      (head ? '<thead><tr>' + head.map((h: unknown) =>
        `<th>${escapeHtml(String(h))}</th>`).join('') + '</tr></thead>' : '') +
      '<tbody>';
    for (const row of slice) {
      const cells = Array.isArray(row) ? row.slice(0, 8) : [];
      html += '<tr>' + cells.map((c) =>
        `<td>${escapeHtml(String(c ?? ''))}</td>`).join('') + '</tr>';
    }
    html += '</tbody></table>';
  } else {
    return escapeHtml(text);
  }
  if (arr.length > 30) {
    html += `<div class="call-more">… 共 ${arr.length} 条，前 30 条已展示</div>`;
  }
  return html;
}
