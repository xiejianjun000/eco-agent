/**
 * markdown.ts — 轻量安全 Markdown 渲染器（防 XSS）
 *
 * 原则：先整体 HTML 转义，再做受控的语法替换——所有用户/模型内容
 * 在插入 HTML 前已转义，语法标记本身不携带可执行内容。
 * 支持：标题、粗体、斜体、行内代码、代码块、表格、无序/有序列表、引用。
 */

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export { escapeHtml };

/** 表格块解析：连续的 | 行 → <table> */
function renderTable(lines: string[]): { html: string; consumed: number } | null {
  const header = lines[0];
  const sep = lines[1];
  if (!header || !sep || !header.includes('|') || !sep.includes('|')) return null;
  if (!/^[\s|:*-]+$/.test(sep.replace(/[^|:*-]/g, ''))) return null;

  const parseRow = (line: string): string[] =>
    line
      .trim()
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((c) => c.trim());

  const headers = parseRow(header);
  let html = '<table class="md-table"><thead><tr>';
  for (const h of headers) {
    html += `<th>${renderInline(escapeHtml(h))}</th>`;
  }
  html += '</tr></thead><tbody>';

  let i = 2;
  while (i < lines.length && lines[i].includes('|')) {
    const cells = parseRow(lines[i]);
    html += '<tr>';
    for (const c of cells) {
      html += `<td>${renderInline(escapeHtml(c))}</td>`;
    }
    html += '</tr>';
    i += 1;
  }
  html += '</tbody></table>';
  return { html, consumed: i };
}

/** 行内语法：**粗体** `代码` *斜体* + 机器标识自动包 code（DSH 规范） */
function renderInline(text: string): string {
  let out = text;
  out = out.replace(/`([^`]+)`/g, '<code class="md-inline">$1</code>');
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  out = out.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
  // 自动包裹机器标识为行内代码（审批ID/状态值/接口标识/风险级）
  // (?<!>) 跳过已由反引号生成的 <code> 内容，避免二次包裹
  out = out.replace(/(?<!>)(appr-[a-z0-9-]{6,})/g, '<code class="md-inline">$1</code>');
  out = out.replace(/(?<!>)\b(pending|approved|rejected|allowed|denied)\b/g, '<code class="md-inline">$1</code>');
  out = out.replace(/(?<!>)\b(FQ|answerer)\b/g, '<code class="md-inline">$1</code>');
  out = out.replace(/(?<!>)\b(L[1-4])\b/g, '<code class="md-inline">$1</code>');
  return out;
}

export function renderMarkdown(text: string): string {
  if (!text) return '';
  const escaped = escapeHtml(text);
  const lines = escaped.split('\n');
  const out: string[] = [];
  let listType: 'ul' | 'ol' | null = null;
  let inCodeBlock = false;
  let emittedContent = false;  // 是否已输出首个内容块（摘要行判定用）
  let codeBuffer: string[] = [];
  let codeLang = '';

  /** 代码块收口：DSH 式横幅（语言标签 + 复制按钮）+ 代码体 */
  const closeCodeBlock = () => {
    if (!inCodeBlock) return;
    const lang = codeLang.replace(/[^\w+#.-]/g, '').slice(0, 24) || 'code';
    out.push(
      `<div class="md-codeblock"><div class="md-code-banner">` +
        `<span class="md-code-lang">${lang}</span>` +
        `<button type="button" class="md-code-copy">复制</button>` +
        `</div><pre class="md-code"><code>${codeBuffer.join('\n')}</code></pre></div>`,
    );
    codeBuffer = [];
    codeLang = '';
    inCodeBlock = false;
  };

  const closeList = () => {
    if (listType) {
      out.push(`</${listType}>`);
      listType = null;
    }
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // 代码块 ```...```
    if (trimmed.startsWith('```')) {
      if (inCodeBlock) {
        // options 标签：DSH 式选项提问（渲染为可点击按钮，点击回填输入框）
        if (codeLang.toLowerCase() === 'options') {
          const opts = codeBuffer
            .map((l) => l.trim())
            .filter((l) => l.length > 0 && !l.startsWith('- '))
            .map((l) => l.replace(/^[-*]\s+/, ''));
          if (opts.length > 0) {
            out.push(
              `<div class="md-options">${opts
                .map((o) => `<button type="button" class="md-option" data-opt="${o}">${o}</button>`)
                .join('')}</div>`,
            );
          }
        } else {
          closeCodeBlock();
        }
        codeBuffer = [];
        codeLang = '';
        inCodeBlock = false;
      } else {
        closeList();
        inCodeBlock = true;
        codeLang = trimmed.slice(3).trim();
      }
      i += 1;
      continue;
    }
    if (inCodeBlock) {
      codeBuffer.push(line);
      i += 1;
      continue;
    }

    // 表格
    if (trimmed.includes('|') && i + 1 < lines.length && lines[i + 1].includes('|')) {
      const table = renderTable(lines.slice(i));
      if (table) {
        closeList();
        out.push(table.html);
        i += table.consumed;
        continue;
      }
    }

    // 标题
    const heading = trimmed.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      closeList();
      const level = heading[1].length;
      out.push(`<h${level} class="md-h${level}">${renderInline(heading[2])}</h${level}>`);
      i += 1;
      continue;
    }

    // 引用
    if (trimmed.startsWith('&gt;')) {
      closeList();
      out.push(`<blockquote class="md-quote">${renderInline(trimmed.slice(4).trim())}</blockquote>`);
      i += 1;
      continue;
    }

    // 无序列表
    if (/^[-*]\s+/.test(trimmed)) {
      if (listType !== 'ul') {
        closeList();
        out.push('<ul class="md-ul">');
        listType = 'ul';
      }
      out.push(`<li>${renderInline(trimmed.replace(/^[-*]\s+/, ''))}</li>`);
      i += 1;
      continue;
    }

    // 有序列表
    const ol = trimmed.match(/^\d+[.)]\s+(.*)$/);
    if (ol) {
      if (listType !== 'ol') {
        closeList();
        out.push('<ol class="md-ol">');
        listType = 'ol';
      }
      out.push(`<li>${renderInline(ol[1])}</li>`);
      i += 1;
      continue;
    }

    // 分隔线
    if (/^(-{3,}|\*{3,})$/.test(trimmed)) {
      closeList();
      out.push('<hr class="md-hr" />');
      i += 1;
      continue;
    }

    // 空行 = 段落分隔
    if (!trimmed) {
      closeList();
      i += 1;
      continue;
    }

    // 普通段落
    closeList();
    // 回答摘要行（首个以 ✅ 开头的段落）：加 md-summary 类，底部细线分隔正文
    const isSummary = !emittedContent && trimmed.startsWith('✅');
    emittedContent = true;
    out.push(`<p class="md-p${isSummary ? ' md-summary' : ''}">${renderInline(trimmed)}</p>`);
    i += 1;
  }

  if (inCodeBlock) closeCodeBlock();
  closeList();
  return out.join('\n');
}
