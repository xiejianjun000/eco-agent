import React, { useEffect, useState } from 'react';
import { api, type TraceSummary, type TraceTree, type TraceSpan, type DecisionItem } from '../api';

function fmtMs(ms?: number | null): string {
  if (ms === undefined || ms === null) return '…';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function fmtClock(iso: string): string {
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return '';
  const d = new Date(t);
  const p = (n: number) => n.toString().padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

const KIND_BADGE: Record<string, string> = {
  session: 'badge olive',
  llm_call: 'badge blue',
  tool_call: 'badge amber',
};

/** span 瀑布行：DFS 按 parent_id 分层缩进，顺序按绝对 start 排序 */
function buildRows(spans: TraceSpan[]): { span: TraceSpan; depth: number }[] {
  const kids = new Map<string | null, TraceSpan[]>();
  for (const s of spans) {
    const list = kids.get(s.parent_id) ?? [];
    list.push(s);
    kids.set(s.parent_id, list);
  }
  for (const list of kids.values()) list.sort((a, b) => a.start - b.start);
  const rows: { span: TraceSpan; depth: number }[] = [];
  const walk = (pid: string | null, depth: number) => {
    for (const s of kids.get(pid) ?? []) {
      rows.push({ span: s, depth });
      walk(s.span_id, depth + 1);
    }
  };
  walk(null, 0);
  // 孤儿 span（parent 缺失）兜底挂载到根层，避免静默丢失
  const seen = new Set(rows.map((r) => r.span.span_id));
  for (const s of spans) {
    if (!seen.has(s.span_id)) rows.push({ span: s, depth: 0 });
  }
  return rows;
}

function spanSubtitle(s: TraceSpan): string {
  const a = s.attrs ?? {};
  if (s.kind === 'llm_call') {
    const toks: string[] = [];
    if (typeof a.prompt_tokens === 'number') toks.push(`in=${a.prompt_tokens}`);
    if (typeof a.completion_tokens === 'number') toks.push(`out=${a.completion_tokens}`);
    return [a.model, a.finish_reason, toks.length ? `tok(${toks.join(',')})` : '']
      .filter(Boolean).join(' · ');
  }
  if (s.kind === 'tool_call') {
    try {
      const j = JSON.stringify(a.args ?? {});
      return j.length > 60 ? `${j.slice(0, 60)}…` : j;
    } catch {
      return '';
    }
  }
  return '';
}

/** 单个 span 行：缩进标签 + 绝对时间定位的瀑布条，点击展开 attrs */
function SpanRow({ span, depth, t0, total }: {
  span: TraceSpan; depth: number; t0: number; total: number;
}): React.ReactElement {
  const [open, setOpen] = useState(false);
  const left = ((span.start - t0) / total) * 100;
  const width = span.duration_ms != null ? (span.duration_ms / total) * 100 : 0;
  const kindCls = span.kind === 'llm_call' ? 'llm' : span.kind === 'tool_call' ? 'tool' : span.kind === 'session' ? 'session' : 'other';
  const sub = spanSubtitle(span);
  return (
    <div className={`wf-row${open ? ' open' : ''}`}>
      <div className="wf-head" onClick={() => setOpen(!open)} title={span.start_iso}>
        <div className="wf-label" style={{ paddingLeft: depth * 16 }}>
          <span className={KIND_BADGE[span.kind] ?? 'badge'}>{span.kind}</span>
          <span className="wf-name">{span.name}</span>
          {sub && <span className="wf-sub">{sub}</span>}
        </div>
        <div className="wf-track">
          <span
            className={`wf-bar ${kindCls}`}
            style={{ left: `${Math.max(0, Math.min(left, 100))}%`, width: `${Math.max(width, 0.6)}%` }}
            title={`${span.name} · ${fmtMs(span.duration_ms)}`}
          />
        </div>
        <span className="wf-dur">{fmtMs(span.duration_ms)}</span>
      </div>
      {open && (
        <pre className="wf-attrs">{JSON.stringify(span.attrs ?? {}, null, 2)}</pre>
      )}
    </div>
  );
}

/** 右侧详情：span 瀑布 + 决策时间线 */
function TraceDetail({ tree }: { tree: TraceTree }): React.ReactElement {
  const [decisions, setDecisions] = useState<DecisionItem[]>([]);
  useEffect(() => {
    api.decisions(200, 0, tree.trace_id).then((r) => setDecisions(r.items)).catch(() => setDecisions([]));
  }, [tree.trace_id]);

  const rows = buildRows(tree.spans ?? []);
  const starts = (tree.spans ?? []).map((s) => s.start).filter((x) => Number.isFinite(x));
  const t0 = starts.length ? Math.min(...starts) : 0;
  const ends = (tree.spans ?? []).map((s) => s.end ?? s.start).filter((x) => Number.isFinite(x));
  const total = Math.max(((ends.length ? Math.max(...ends) : t0) - t0) * 1000, 1);

  return (
    <>
      <div className="card">
        <div className="agents-head">
          <h2>Span 瀑布</h2>
          <span className="meta">
            {tree.spans.length} spans · 总耗时 {fmtMs(total)} · trace {tree.trace_id.slice(0, 12)}…
          </span>
        </div>
        {rows.length === 0 ? (
          <div className="empty">该会话暂无 span 记录</div>
        ) : (
          <div className="wf-list">
            {rows.map(({ span, depth }) => (
              <SpanRow key={span.span_id} span={span} depth={depth} t0={t0} total={total} />
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <div className="agents-head">
          <h2>决策时间线</h2>
          <span className="meta">{decisions.length} 条（decisions.jsonl，SM3 链）</span>
        </div>
        {decisions.length === 0 ? (
          <div className="empty">该会话暂无关联决策留痕</div>
        ) : (
          decisions.map((d, i) => (
            <div key={d.hash || i} className="dec-row">
              <span className="dec-ts">{fmtClock(d.ts)}</span>
              <span className="badge blue">R{d.round}</span>
              <span className="dec-model">{d.model || '?'}</span>
              <span className="dec-finish">{d.finish_reason}</span>
              <span className="dec-tools">
                {d.selected_tools.length > 0 ? d.selected_tools.join(', ') : '直接回答'}
              </span>
              <span className="meta">候选 {d.candidate_tools}</span>
            </div>
          ))
        )}
      </div>
    </>
  );
}

export default function TracesView(): React.ReactElement {
  const [items, setItems] = useState<TraceSummary[]>([]);
  const [selected, setSelected] = useState('');
  const [tree, setTree] = useState<TraceTree | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = () => {
    api.traces().then((r) => {
      setItems(r.items ?? []);
      setSelected((cur) => cur || (r.items?.[0]?.session_id ?? ''));
    }).catch(() => {});
  };

  useEffect(refresh, []);

  useEffect(() => {
    if (!selected) { setTree(null); return; }
    setLoading(true);
    api.trace(selected)
      .then(setTree)
      .catch(() => setTree(null))
      .finally(() => setLoading(false));
  }, [selected]);

  const cur = items.find((x) => x.session_id === selected);

  return (
    <div className="traces-wrap">
      <div className="card traces-list">
        <div className="agents-head">
          <h2>轨迹会话</h2>
          <span className="meta">{items.length} 个</span>
          <button className="btn ghost" onClick={refresh}>刷新</button>
        </div>
        {items.length === 0 && (
          <div className="empty">暂无轨迹——跑一次对话后，span 树会落盘到 ~/.eco/traces/</div>
        )}
        {items.map((t) => (
          <div
            key={t.session_id}
            className={`trace-item${t.session_id === selected ? ' active' : ''}`}
            onClick={() => setSelected(t.session_id)}
            title={t.session_id}
          >
            <div className="trace-item-head">
              <span className="trace-item-name">{t.session_id}</span>
              <span className="meta">{fmtMs(t.duration_ms)}</span>
            </div>
            <div className="trace-item-meta">
              {fmtClock(t.start_iso)} · {t.span_count} spans · LLM×{t.llm_calls} · 工具×{t.tool_calls}
              {(t.prompt_tokens + t.completion_tokens) > 0 && ` · ${(t.prompt_tokens + t.completion_tokens).toLocaleString('en-US')} tok`}
            </div>
          </div>
        ))}
      </div>

      <div className="traces-detail">
        {loading && <div className="card"><div className="empty">加载中…</div></div>}
        {!loading && !tree && (
          <div className="card"><div className="empty">选择左侧会话查看 span 瀑布与决策时间线</div></div>
        )}
        {!loading && tree && (
          <>
            <div className="card">
              <div className="agents-head">
                <h2>{tree.session_id}</h2>
                <span className="meta">
                  {[tree.meta?.provider, tree.meta?.model].filter(Boolean).join(' · ') || 'meta 未记录'}
                  {cur && ` · ${fmtClock(cur.start_iso)}`}
                </span>
              </div>
            </div>
            <TraceDetail tree={tree} />
          </>
        )}
      </div>
    </div>
  );
}
