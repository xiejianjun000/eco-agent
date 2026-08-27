import { useState, useMemo, type ReactNode } from 'react';
import { IconFileText, IconFileSpreadsheet, IconFilePdf, IconPenTool, IconMessageSquare, IconPlus } from './icons-extra';
import type { ActiveDoc, Annotation, OfficeMode } from '../data/rightpanel';

interface SectionOfficeProps {
  activeDoc?: ActiveDoc | null;
  loading?: boolean;
  /** 实时 AI 审阅注解（来自 SSE 流） — 与静态 annotations 合并显示 */
  liveAnnotations?: Annotation[];
  /** 审阅进度 0-100，仅 streaming 时有效 */
  reviewProgress?: number;
  /** 审阅状态 */
  reviewStatus?: 'idle' | 'streaming' | 'done' | 'error';
  /** 触发 AI 审阅 */
  onStartReview?: () => void;
  /** 重试次数 */
  retryCount?: number;
  /** 错误信息 */
  reviewError?: string | null;
}

const FORMAT_ICON: Record<string, ReactNode> = {
  docx: <IconFileText />,
  xlsx: <IconFileSpreadsheet />,
  pdf: <IconFilePdf />,
};
const STATUS_LABEL: Record<string, string> = {
  'ai-draft': 'AI 草稿',
  'editing': '人工编辑中',
  'reviewing': '审阅中',
};
const STATUS_CLASS: Record<string, string> = {
  'ai-draft': 'blue',
  'editing': 'amber',
  'reviewing': 'violet',
};

export default function SectionOffice({
  activeDoc: doc, loading, liveAnnotations, reviewProgress, reviewStatus, onStartReview, retryCount, reviewError,
}: SectionOfficeProps): ReactNode {
  const [mode, setMode] = useState<OfficeMode>('read');
  const [hoverAi, setHoverAi] = useState<number | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  // doc 为空时展示空态（不再回退到静态 mock 文书）
  const d = doc ?? null;

  // 操作行反馈（保存/导出/送签署/归档）
  const notify = (msg: string): void => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 1600);
  };

  // 合并静态 annotations 与实时 AI 注解
  const mergedAnnotations = useMemo(() => {
    const live = liveAnnotations ?? [];
    // 去重：liveAnnotations 中的 paragraphId 如果已存在则不重复添加
    const existedIds = new Set(d?.annotations.map((a) => a.id) ?? []);
    const liveIds = new Set<string>();
    return [
      ...(d?.annotations ?? []),
      ...live.filter((a) => {
        if (existedIds.has(a.id) || liveIds.has(a.id)) return false;
        liveIds.add(a.id);
        return true;
      }),
    ];
  }, [d?.annotations, liveAnnotations]);

  // ── 加载中 ─────────────────────────
  if (loading) {
    return (
      <div className="rp-office">
        <div className="rp-office-loading">正在从 AI 引擎加载文书数据...</div>
      </div>
    );
  }

  // ── 空态 ──────────────────────────
  if (!d) return <EmptyState />;

  const formatCls = d.format;
  const statusCls = STATUS_CLASS[d.status] ?? 'blue';
  const statusLabel = STATUS_LABEL[d.status] ?? d.status;
  const unresolved = mergedAnnotations.filter((a) => !a.resolved).length;
  const isStreaming = reviewStatus === 'streaming';

  return (
    <div className="rp-office">
      {/* 文件头卡 */}
      <div className="rp-doc-card">
        <span className={`rp-doc-format ${formatCls}`}>{FORMAT_ICON[formatCls]}</span>
        <span className="rp-doc-name" title={d.name}>{d.name}</span>
        <span className={`rp-doc-status ${statusCls}`}>{statusLabel}</span>
      </div>

      {/* 三模式分段控件 */}
      <div className="rp-mode-seg">
        {(['read', 'edit', 'review'] as OfficeMode[]).map((m) => (
          <button
            key={m}
            className={`rp-mode-btn ${mode === m ? 'on' : ''}`}
            onClick={() => setMode(m)}
          >
            {m === 'read' && <span className="rp-mode-ico"><IconFileText /></span>}
            {m === 'edit' && <span className="rp-mode-ico"><IconPenTool /></span>}
            {m === 'review' && <span className="rp-mode-ico"><IconMessageSquare /></span>}
            {m === 'read' ? '阅读' : m === 'edit' ? '编辑' : `审阅${unresolved ? ` · ${unresolved}` : ''}`}
          </button>
        ))}
      </div>

      {/* 内容区 */}
      <div className="rp-office-body">
        {mode === 'read' && <ReadView doc={d} />}
        {mode === 'edit' && <EditView doc={d} hoverAi={hoverAi} onHoverAi={setHoverAi} />}
        {mode === 'review' && (
          <>
            <ReviewView annotations={mergedAnnotations} />
            {/* AI 审阅操作栏 */}
            {onStartReview && (
              <div className="rp-ai-review-bar">
                {isStreaming ? (
                  <div className="rp-ai-review-streaming">
                    <span className="spinner" />
                    <span className="rp-ai-review-status">
                      AI 审阅中 {reviewProgress ?? 0}%
                      {retryCount ? ` · 已重试 ${retryCount} 次` : ''}
                    </span>
                  </div>
                ) : (
                  <button
                    className="rp-ai-review-btn"
                    onClick={onStartReview}
                    disabled={isStreaming}
                  >
                    <IconMessageSquare />
                    AI 审阅当前文书
                  </button>
                )}
                {reviewError && (
                  <div className="rp-ai-review-error">{reviewError}</div>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* 同步指示条 */}
      <SyncBar synced={d.synced} />

      {/* 操作行 */}
      <div className="rp-office-actions">
        <button className="rp-action-btn" onClick={() => notify('已保存')}>保存</button>
        <button className="rp-action-btn" onClick={() => notify('已导出')}>导出</button>
        <button className="rp-action-btn primary" onClick={() => notify('已送签署')}>送签署</button>
        <button className="rp-action-btn" onClick={() => notify('已归档')}>归档</button>
      </div>

      {toast && <div className="toast ok">{toast}</div>}
    </div>
  );
}

// ═══════ 子组件 ═══════════════════════════════════

function EmptyState(): ReactNode {
  return (
    <div className="rp-office-empty">
      <div className="rp-empty-icon"><IconPlus /></div>
      <p className="rp-empty-title">尚无打开的文书</p>
      <p className="rp-empty-hint">从执法办案或档案管理打开一份文书，或让 AI 为您起草。</p>
      <button className="rp-empty-btn">让 AI 起草一份</button>
    </div>
  );
}

function ReadView({ doc: d }: { doc: ActiveDoc }): ReactNode {
  return (
    <div className="rp-doc-read">
      {d.paragraphs.map((p) => (
        <p key={p.id} className={`rp-doc-p ${p.aiModified ? 'ai-tagged' : ''}`}>
          {p.text}
        </p>
      ))}
    </div>
  );
}

function EditView({ doc: d, hoverAi, onHoverAi }: {
  doc: ActiveDoc;
  hoverAi: number | null;
  onHoverAi: (id: number | null) => void;
}): ReactNode {
  return (
    <div className="rp-doc-edit">
      {d.paragraphs.map((p) => (
        <div key={p.id} className="rp-edit-para">
          <p
            className={`rp-doc-p ${p.aiModified ? 'ai-edit' : ''}`}
            onMouseEnter={() => p.aiModified && onHoverAi(p.id)}
            onMouseLeave={() => onHoverAi(null)}
          >
            {p.text}
          </p>
          {p.aiModified && hoverAi === p.id && (
            <div className="rp-ai-popover">
              <span className="rp-ai-pop-expert">{p.aiExpert ?? '文书成'}</span>
              <span className="rp-ai-pop-act">修改 · 可撤销</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ReviewView({ annotations }: { annotations: Annotation[] }): ReactNode {
  return (
    <div className="rp-doc-review">
      {annotations.length === 0 ? (
        <p className="rp-review-empty">暂无批注</p>
      ) : (
        annotations.map((a) => (
          <AnnotationCard key={a.id} annotation={a} />
        ))
      )}
    </div>
  );
}

function AnnotationCard({ annotation: a }: { annotation: Annotation }): ReactNode {
  const [resolved, setResolved] = useState(a.resolved);
  const isAi = a.role === 'ai';

  return (
    <div className={`rp-anno-card ${resolved ? 'resolved' : ''}`}>
      <div className="rp-anno-head">
        <span className={`rp-anno-author ${isAi ? 'ai' : ''}`}>
          {isAi ? '🤖 ' : ''}{a.author}
        </span>
        <span className="rp-anno-time">{a.time}</span>
        {!resolved && (
          <button className="rp-anno-resolve" onClick={() => setResolved(true)}>
            已解决
          </button>
        )}
        {resolved && <span className="rp-anno-done">✓ 已解决</span>}
      </div>
      <p className="rp-anno-content">{a.content}</p>
      {a.replies.length > 0 && (
        <div className="rp-anno-replies">
          {a.replies.map((r, i) => (
            <div key={i} className="rp-anno-reply">
              <span className={`rp-anno-author ${r.role === 'ai' ? 'ai' : ''}`}>{r.author}</span>
              <span className="rp-anno-time">{r.time}</span>
              <p>{r.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SyncBar({ synced }: { synced: boolean }): ReactNode {
  return (
    <div className={`rp-sync ${synced ? 'synced' : 'writing'}`}>
      {synced ? (
        <>
          <span className="rp-sync-dot green" />
          已同步 · 文书成 与您同时在线
        </>
      ) : (
        <>
          <span className="rp-sync-dot blue pulse" />
          AI 正在写入第 3 段…
        </>
      )}
    </div>
  );
}
