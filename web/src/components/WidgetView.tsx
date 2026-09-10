/**
 * WidgetView.tsx — show_widget 内联渲染（对标 WorkBuddy VisualizerShowWidgetView）。
 *
 * 两条渲染通道分离：artifact（文件类）走右栏，show_widget（内联视觉）走对话流内嵌。
 * 安全红线（执法场景，零幻觉/零执行）：
 *   SVG  → 以 <img data:image/svg+xml> 静态渲染（脚本不执行，天然防 XSS）；
 *   HTML → <iframe sandbox>（无脚本、无同源、无弹窗），隔离宿主页面。
 * 标准画布 680px（WorkBuddy viewBox 0 0 680）。
 */

import { useState } from 'react';
import { WIDGET_CANVAS_W, type WidgetBlock } from '../utils/widget';

export default function WidgetView({ block, index = 0 }: { block: WidgetBlock; index?: number }) {
  const [collapsed, setCollapsed] = useState(false);

  const label = block.kind === 'svg' ? '可视化 · SVG' : block.kind === 'html' ? '可视化 · HTML' : '可视化部件';
  const svgSrc = block.kind === 'svg'
    ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(block.code)}`
    : '';

  return (
    <div className="widget-view" data-widget-kind={block.kind} data-widget-idx={index}>
      <div className="widget-view-head">
        <span className="widget-view-label">{label}</span>
        <button className="widget-view-toggle" onClick={() => setCollapsed((v) => !v)}
                title={collapsed ? '展开' : '收起'}>
          {collapsed ? '展开' : '收起'}
        </button>
      </div>
      {!collapsed && (
        <div className="widget-view-body" style={{ maxWidth: WIDGET_CANVAS_W }}>
          {block.kind === 'svg' && (
            <img className="widget-view-svg" src={svgSrc} alt={label} loading="lazy"
                 style={{ width: '100%', height: 'auto' }} />
          )}
          {block.kind === 'html' && (
            <iframe className="widget-view-html" sandbox="" srcDoc={block.code}
                    title={label} style={{ width: '100%', border: 'none' }} />
          )}
          {block.kind === 'unknown' && (
            <pre className="widget-view-raw">{block.code}</pre>
          )}
        </div>
      )}
    </div>
  );
}
