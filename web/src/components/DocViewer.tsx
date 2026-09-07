/**
 * web/src/components/DocViewer.tsx — 文档渲染器（WorkBuddy 对标）
 *
 * 穿透 WorkBuddy app.asar v5.3.13 后确认它有两条并存的路径，本组件同样实现两条：
 *
 *  1) 云端文档 → 容器嵌入
 *     WorkBuddy 企业版用 Electron <webview>（partition="persist:tdoc-preview"
 *     独立会话分区），消费版降级为 iframe（源码日志原话 "fallback to C-side iframe"）。
 *     eco 是纯 Web 应用，浏览器里没有 <webview>，因此只能走 iframe 这条消费版路径。
 *     实测（Playwright，2026-09）：
 *       - docs.qq.com 文档页可正常嵌入，无 X-Frame-Options / frame-ancestors 拦截
 *       - feishu.cn 返回 report-only CSP：frame-ancestors 白名单仅
 *         base.feishubase.com 与 *.feishu.cn。当前是 report-only（仅上报不拦截），
 *         但随时可能转为强制，故飞书一律提供「新标签打开」兜底，不假设嵌入永远可用。
 *
 *  2) 本地文件 → 就地渲染（无需任何外部服务，内外网均可用）
 *     docx → docx-preview（WorkBuddy 同款库，解析 OOXML 直接生成 DOM）
 *     pdf  → pdf.js（canvas 渲染，与 WorkBuddy 一致）
 *     xlsx → SheetJS 转 HTML 表格
 *     html/图表 → sandbox="allow-scripts" iframe（无 allow-same-origin，
 *                 脚本跑得起来但碰不到宿主 DOM/cookie/localStorage）
 */

import { useEffect, useRef, useState } from 'react';

const API = '/api/v1';

export type DocSource =
  | { kind: 'local'; name: string }
  | { kind: 'url'; url: string }
  | { kind: 'html'; html: string; title?: string };

/** 云文档域名识别（对标 WorkBuddy 的 isTencentDocsUrl / TDOC_PATH_PREFIXES） */
const TDOC_PATH_PREFIXES = [
  '/doc/', '/sheet/', '/slide/', '/pdf/', '/form/',
  '/mind/', '/flowchart/', '/board/', '/smartsheet/', '/smartcanvas/', '/s/', '/desktop/',
];

export function isTencentDocsUrl(raw: string): boolean {
  try {
    const u = new URL(raw.startsWith('//') ? `https:${raw}` : raw);
    const h = u.hostname.toLowerCase();
    if (h !== 'docs.qq.com' && !h.endsWith('.docs.qq.com')) return false;
    return TDOC_PATH_PREFIXES.some((p) => u.pathname.startsWith(p));
  } catch { return false; }
}

export function isFeishuUrl(raw: string): boolean {
  try {
    const h = new URL(raw).hostname.toLowerCase();
    return h === 'feishu.cn' || h.endsWith('.feishu.cn')
        || h === 'larksuite.com' || h.endsWith('.larksuite.com');
  } catch { return false; }
}

/** 扩展名 → 渲染器（对标 WorkBuddy TENCENT_DOCS_ENGINE_FILE_TYPES 的分类口径） */
export function rendererFor(name: string): 'docx' | 'pdf' | 'sheet' | 'html' | 'image' | 'text' | 'none' {
  const ext = (name.match(/\.[^.]+$/)?.[0] ?? '').toLowerCase();
  if (['.docx', '.doc', '.dotx', '.docm'].includes(ext)) return 'docx';
  if (ext === '.pdf') return 'pdf';
  if (['.xlsx', '.xls', '.csv', '.xlsm'].includes(ext)) return 'sheet';
  if (['.html', '.htm'].includes(ext)) return 'html';
  if (['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'].includes(ext)) return 'image';
  if (['.md', '.txt', '.json', '.log', '.py', '.ts', '.js'].includes(ext)) return 'text';
  return 'none';
}

const fileUrl = (name: string) => `${API}/documents/file?name=${encodeURIComponent(name)}`;

/** 沙箱 HTML：CSP 白名单对标 WorkBuddy CDN_WHITELIST，四个公共 CDN */
const CDN_WHITELIST = ['cdnjs.cloudflare.com', 'esm.sh', 'cdn.jsdelivr.net', 'unpkg.com'];

export function buildSandboxHtml(inner: string): string {
  const cdn = CDN_WHITELIST.map((d) => `https://${d}`).join(' ');
  const csp = [
    "default-src 'none'",
    `script-src 'unsafe-inline' 'unsafe-eval' blob: ${cdn}`,
    "style-src 'unsafe-inline'",
    `img-src data: blob: ${cdn}`,
    `font-src ${cdn}`,
    `connect-src ${cdn}`,
  ].join('; ');
  // 已是完整文档则只注入 CSP，避免二次包裹破坏原结构
  if (/<html[\s>]/i.test(inner)) {
    return inner.replace(/<head([^>]*)>/i, `<head$1><meta http-equiv="Content-Security-Policy" content="${csp}">`);
  }
  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<style>*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{width:100%;height:auto;overflow:visible;background:transparent;
font:14px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;padding:12px}
html,body{scrollbar-width:thin;scrollbar-color:rgba(128,128,128,.3) transparent}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-thumb{background:rgba(128,128,128,.3);border-radius:3px}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:6px 8px}
</style></head><body>${inner}</body></html>`;
}

export default function DocViewer({ source }: { source: DocSource }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle');
  const [message, setMessage] = useState('');

  useEffect(() => {
    let cancelled = false;
    const host = hostRef.current;
    if (!host) return;

    // 仅本地文件需要异步取二进制并渲染；url / html 由 JSX 直接出容器
    if (source.kind !== 'local') { setStatus('ok'); return; }

    const kind = rendererFor(source.name);
    if (kind === 'none' || kind === 'image' || kind === 'text' || kind === 'html') {
      setStatus('ok');
      return;
    }

    host.innerHTML = '';
    setStatus('loading');
    setMessage('');

    (async () => {
      try {
        const res = await fetch(fileUrl(source.name));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const buf = await res.arrayBuffer();
        if (cancelled) return;

        if (kind === 'docx') {
          const docx = await import('docx-preview');
          if (cancelled) return;
          await docx.renderAsync(buf, host, undefined, {
            className: 'docx',
            inWrapper: true,
            ignoreWidth: false,
            breakPages: true,
            experimental: true,
          });
        } else if (kind === 'pdf') {
          const pdfjs = await import('pdfjs-dist');
          // worker 用同版本 CDN 资源；失败时 pdf.js 自动退到主线程解析
          (pdfjs as any).GlobalWorkerOptions.workerSrc =
            `https://cdn.jsdelivr.net/npm/pdfjs-dist@${(pdfjs as any).version}/build/pdf.worker.min.mjs`;
          const pdf = await (pdfjs as any).getDocument({ data: buf }).promise;
          if (cancelled) return;
          const max = Math.min(pdf.numPages, 30); // 上限 30 页，避免超大文档卡死
          for (let i = 1; i <= max; i++) {
            const page = await pdf.getPage(i);
            if (cancelled) return;
            const vp = page.getViewport({ scale: 1.4 });
            const canvas = document.createElement('canvas');
            canvas.width = vp.width; canvas.height = vp.height;
            canvas.style.cssText = 'width:100%;height:auto;display:block;margin:0 auto 12px;box-shadow:0 1px 4px rgba(0,0,0,.12)';
            host.appendChild(canvas);
            await page.render({ canvasContext: canvas.getContext('2d')!, viewport: vp }).promise;
          }
          if (pdf.numPages > max) {
            const tip = document.createElement('div');
            tip.className = 'muted';
            tip.style.cssText = 'text-align:center;padding:10px';
            tip.textContent = `仅渲染前 ${max} 页，共 ${pdf.numPages} 页`;
            host.appendChild(tip);
          }
        } else if (kind === 'sheet') {
          const XLSX = await import('xlsx');
          if (cancelled) return;
          const wb = XLSX.read(buf, { type: 'array' });
          wb.SheetNames.forEach((sn) => {
            const cap = document.createElement('div');
            cap.className = 'doc-sheet-name';
            cap.textContent = sn;
            host.appendChild(cap);
            const div = document.createElement('div');
            div.className = 'doc-sheet-table';
            div.innerHTML = XLSX.utils.sheet_to_html(wb.Sheets[sn]);
            host.appendChild(div);
          });
        }
        if (!cancelled) setStatus('ok');
      } catch (e) {
        if (cancelled) return;
        setStatus('error');
        setMessage((e as Error).message);
      }
    })();

    return () => { cancelled = true; };
  }, [source]);

  // ── 云文档：腾讯文档可嵌入；飞书受 frame-ancestors 限制，始终给新窗兜底 ──
  if (source.kind === 'url') {
    const feishu = isFeishuUrl(source.url);
    return (
      <div className="doc-viewer doc-viewer--url">
        <div className="doc-viewer-bar">
          <span className="doc-viewer-src">
            {isTencentDocsUrl(source.url) ? '腾讯文档' : feishu ? '飞书' : '网页'}
          </span>
          <a className="doc-viewer-open" href={source.url} target="_blank" rel="noopener noreferrer">
            新标签打开 ↗
          </a>
        </div>
        {feishu && (
          <div className="doc-viewer-note">
            飞书对第三方站点设有 frame-ancestors 白名单（当前为 report-only）。
            若下方空白，请用「新标签打开」。
          </div>
        )}
        <iframe
          className="doc-viewer-frame"
          src={source.url}
          title={source.url}
          allowFullScreen
          referrerPolicy="no-referrer"
        />
      </div>
    );
  }

  // ── 图表 / 网页：沙箱 iframe（无 allow-same-origin） ──
  if (source.kind === 'html') {
    return (
      <div className="doc-viewer doc-viewer--html">
        <iframe
          className="doc-viewer-frame"
          sandbox="allow-scripts"
          srcDoc={buildSandboxHtml(source.html)}
          title={source.title || 'Interactive widget'}
        />
      </div>
    );
  }

  const kind = rendererFor(source.name);

  if (kind === 'image') {
    return <div className="doc-viewer"><img className="doc-viewer-img" src={fileUrl(source.name)} alt={source.name} /></div>;
  }
  if (kind === 'html') {
    return (
      <div className="doc-viewer">
        <iframe className="doc-viewer-frame" sandbox="allow-scripts" src={fileUrl(source.name)} title={source.name} />
      </div>
    );
  }
  if (kind === 'text') {
    return <TextFile name={source.name} />;
  }
  if (kind === 'none') {
    return (
      <div className="doc-viewer doc-viewer--unsupported">
        <div className="empty">
          该格式暂不支持预览（{source.name}）
          <div style={{ marginTop: 10 }}>
            <a className="doc-viewer-open" href={fileUrl(source.name)} download>下载文件 ↓</a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="doc-viewer">
      <div className="doc-viewer-bar">
        <span className="doc-viewer-src">{source.name}</span>
        <a className="doc-viewer-open" href={fileUrl(source.name)} download>下载 ↓</a>
      </div>
      {status === 'loading' && <div className="empty" style={{ padding: 16 }}>渲染中…</div>}
      {status === 'error' && (
        <div className="empty" style={{ padding: 16 }}>
          渲染失败：{message}
          <div style={{ marginTop: 10 }}>
            <a className="doc-viewer-open" href={fileUrl(source.name)} download>改为下载 ↓</a>
          </div>
        </div>
      )}
      <div ref={hostRef} className="doc-viewer-host" />
    </div>
  );
}

function TextFile({ name }: { name: string }) {
  const [text, setText] = useState('加载中…');
  useEffect(() => {
    let off = false;
    fetch(fileUrl(name))
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((t) => { if (!off) setText(t); })
      .catch((e) => { if (!off) setText(`读取失败：${e.message}`); });
    return () => { off = true; };
  }, [name]);
  return (
    <div className="doc-viewer">
      <div className="doc-viewer-bar">
        <span className="doc-viewer-src">{name}</span>
        <a className="doc-viewer-open" href={fileUrl(name)} download>下载 ↓</a>
      </div>
      <pre className="doc-viewer-text">{text}</pre>
    </div>
  );
}
