import type { ToolDetail } from '../utils/toolViews'

/**
 * 工具展开明细面板。
 *
 * 对标 WorkBuddy ToolExpandable 的 children（见 docs/RENDER_SPEC.md §2）。
 * 三条纪律：
 *  1. 头部不动 —— 本组件只渲染头部**下方**的内容，展开与否头部完全一致。
 *     这是上一轮修过的老毛病：展开时整块换成裸行，等于两套皮并存。
 *  2. 逐行独立 —— 每个工具行有自己的展开态，不是整段过程一起开合。
 *  3. 无内容不展开 —— detail 返回 null 时根本不渲染箭头（见 resolveToolDetail）。
 *
 * 动效数值取自实测：height .28s cubic-bezier(.33,1,.68,1)，
 * 内容 opacity + translateY(-6px)，展开态外边距 4px 0 8px。
 */
export function ToolDetailPanel({ detail, open }: { detail: ToolDetail; open: boolean }) {
  return (
    <div className={`tool-exp-shell${open ? ' open' : ''}`} aria-hidden={!open}>
      <div className="tool-exp-content">{renderBody(detail)}</div>
    </div>
  )
}

function renderBody(d: ToolDetail) {
  switch (d.kind) {
    case 'command':
      return (
        <>
          {d.command && <div className="tool-exp-cmd">{d.command}</div>}
          {d.output && <pre className="tool-exp-out">{clip(d.output)}</pre>}
        </>
      )
    case 'list':
      return (
        <div className="tool-exp-list">
          {d.items.map((it, i) => (
            <div className="tool-exp-item" key={i}>
              <span className="tool-exp-item-text">{it.text}</span>
              {it.sub && <span className="tool-exp-item-sub">{it.sub}</span>}
            </div>
          ))}
          {!!d.more && <div className="tool-exp-more">还有 {d.more} 条</div>}
        </div>
      )
    case 'kv':
      return (
        <div className="tool-exp-kv">
          {d.rows.map((r, i) => (
            <div className="tool-exp-kv-row" key={i}>
              <span className="tool-exp-kv-k">{r.k}</span>
              <span className="tool-exp-kv-v">{r.v}</span>
            </div>
          ))}
        </div>
      )
    case 'text':
      return <pre className="tool-exp-out">{clip(d.text)}</pre>
    default:
      return null
  }
}

/** 输出限高：超长内容折断，避免一次工具调用刷屏 */
const MAX_LINES = 40
function clip(t: string): string {
  const lines = t.split('\n')
  if (lines.length <= MAX_LINES) return t
  return `${lines.slice(0, MAX_LINES).join('\n')}\n… 另有 ${lines.length - MAX_LINES} 行`
}
