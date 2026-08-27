import React from "react";

interface RightPanelProps {
  open: boolean;
  onToggle: () => void;
  sessionName?: string;
  tags?: string[];
}

export default function RightPanel({ open, onToggle, sessionName, tags }: RightPanelProps) {
  return (
    <>
      <button
        className="right-panel-toggle"
        title={open ? "收起生态上下文" : "展开生态上下文"}
        onClick={onToggle}
      >
        {open ? "▶" : "◀"}
      </button>
      {open && (
        <aside className="right-panel">
          <div className="rp-header">
            <span className="rp-title">≡ 生态上下文</span>
          </div>
          <details className="rp-section" open>
            <summary className="rp-summary">
              <span className="rp-caret">▾</span>
              <span>📋 概览</span>
            </summary>
            <div className="rp-body">
              {sessionName ? (
                <>
                  <div className="rp-row"><span className="rp-key">任务</span><span className="rp-val">{sessionName}</span></div>
                  <div className="rp-row"><span className="rp-key">要素</span><span className="rp-val">{tags?.join(" / ") || "—"}</span></div>
                </>
              ) : (
                <div className="rp-empty">暂无任务</div>
              )}
            </div>
          </details>
          <details className="rp-section">
            <summary className="rp-summary"><span className="rp-caret">▸</span><span>📁 产物</span></summary>
            <div className="rp-body"><div className="rp-empty">暂无产物</div></div>
          </details>
          <details className="rp-section">
            <summary className="rp-summary"><span className="rp-caret">▸</span><span>📚 引用</span></summary>
            <div className="rp-body"><div className="rp-empty">暂无引用</div></div>
          </details>
          <details className="rp-section">
            <summary className="rp-summary"><span className="rp-caret">▸</span><span>🗺️ 关联空间</span></summary>
            <div className="rp-body"><div className="rp-empty">暂无关联</div></div>
          </details>
          <div className="rp-footer">内容由 AI 生成，请核实重要信息</div>
        </aside>
      )}
    </>
  );
}
