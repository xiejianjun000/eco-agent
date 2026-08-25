import React, { useEffect, useRef, useState } from 'react';
import { api, type SubagentInfo } from '../api';

type OutItem = { seq: number; kind: string; status?: string; result?: string };

const STATUS_LABEL: Record<string, string> = {
  pending: '等待中',
  running: '运行中',
  idle: '空闲',
  done: '完成',
  failed: '失败',
  killed: '已中断',
};

function statusBadge(s: string): string {
  if (s === 'done') return 'badge olive';
  if (s === 'failed') return 'badge red';
  if (s === 'running' || s === 'pending') return 'badge terra';
  return 'badge';
}

function fmtDur(ms?: number): string {
  if (!ms) return '';
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

function fmtTime(ts: number): string {
  const d = new Date(ts * 1000);
  const p = (n: number) => n.toString().padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export default function AgentsView(): React.ReactElement {
  const [agents, setAgents] = useState<SubagentInfo[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [task, setTask] = useState('');
  const [selected, setSelected] = useState<SubagentInfo | null>(null);
  const [output, setOutput] = useState<OutItem[]>([]);
  const seqRef = useRef(0);
  const [followup, setFollowup] = useState('');
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | null>(null);

  const refresh = () => {
    api.subagentList().then((r) => {
      setAgents(r.agents ?? []);
      setStats(r.stats ?? {});
      setSelected((cur) => {
        if (!cur) return cur;
        const fresh = (r.agents ?? []).find((a) => a.id === cur.id);
        return fresh ?? cur;
      });
    }).catch(() => {});
  };

  const pollOutput = (id: string) => {
    api.subagentGet(id, seqRef.current).then((r) => {
      seqRef.current = r.seq;
      if (r.output.length > 0) {
        setOutput((prev) => {
          const seen = new Set(prev.map((o) => o.seq));
          const fresh = r.output.filter((o) => !seen.has(o.seq));
          return fresh.length > 0 ? [...prev, ...fresh] : prev;
        });
      }
      setSelected(r.agent);
    }).catch(() => {});
  };

  useEffect(() => {
    refresh();
    return () => { if (timer.current !== null) window.clearInterval(timer.current); };
  }, []);

  useEffect(() => {
    // 每次选中对象或其状态变化：清定时器 → 重置游标 → 拉一次增量
    if (timer.current !== null) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
    if (!selected) return;
    setOutput([]);
    seqRef.current = 0;
    pollOutput(selected.id);
    // 仅在运行中轮询；跑完（done/failed/killed）后 effect 因 status 变化重跑并停表
    if (selected.status === 'running' || selected.status === 'pending') {
      timer.current = window.setInterval(() => {
        pollOutput(selected.id);
        refresh();
      }, 2000);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.id, selected?.status]);

  const spawn = async () => {
    const text = task.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      const a = await api.subagentSpawn({ message: text, background: true, label: text.slice(0, 24) });
      setTask('');
      setSelected(a);
      refresh();
    } catch (e) {
      window.alert(`发起失败: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const interrupt = async () => {
    if (!selected) return;
    await api.subagentInterrupt(selected.id).catch(() => {});
    refresh();
  };

  const sendFollowup = async () => {
    const text = followup.trim();
    if (!text || !selected) return;
    setFollowup('');
    await api.subagentMessage(selected.id, text).catch(() => {});
    refresh();
  };

  return (
    <div className="agents-wrap">
      <div className="card agents-list-card">
        <div className="agents-head">
          <h2>子代理目录</h2>
          <span className="meta">
            运行 {stats.running ?? 0} · 完成 {stats.done ?? 0} · 失败 {stats.failed ?? 0}
          </span>
          <button className="btn ghost" onClick={refresh}>刷新</button>
        </div>
        <div className="spawn-row">
          <textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="输入任务描述，后台发起一个子代理（如：检索某企业近三年行政处罚记录并汇总）"
            rows={2}
          />
          <button className="btn" onClick={() => void spawn()} disabled={busy || !task.trim()}>
            {busy ? '发起中' : '发起'}
          </button>
        </div>
        <div className="agent-list">
          {agents.length === 0 ? (
            <div className="empty">暂无子代理——在上方输入任务发起第一个。</div>
          ) : (
            agents.map((a) => (
              <div
                key={a.id}
                className={`agent-row${selected?.id === a.id ? ' active' : ''}`}
                onClick={() => setSelected(a)}
              >
                <span className={statusBadge(a.status)}>{STATUS_LABEL[a.status] ?? a.status}</span>
                <span className="agent-label">{a.label || a.id}</span>
                <span className="agent-meta">
                  {fmtTime(a.created_at)} · {a.turns ?? 0} 轮 · {fmtDur(a.duration_ms)}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="card agent-detail">
        {selected ? (
          <>
            <div className="agents-head">
              <h2>{selected.label || selected.id}</h2>
              <span className="meta">{selected.id}</span>
              <span className={statusBadge(selected.status)}>{STATUS_LABEL[selected.status] ?? selected.status}</span>
              {(selected.status === 'running' || selected.status === 'pending') && (
                <button className="btn ghost" onClick={() => void interrupt()}>中断</button>
              )}
            </div>
            {selected.error && <div className="agent-error">❌ {selected.error}</div>}
            <div className="agent-output">
              {output.length === 0 && !selected.result && (
                <div className="empty">
                  {selected.status === 'running' || selected.status === 'pending'
                    ? '运行中…（每 2 秒自动刷新）'
                    : '无输出'}
                </div>
              )}
              {output.map((o) => (
                <div key={o.seq} className="output-row">
                  <span className="output-seq">#{o.seq}</span>
                  <span className={`badge ${o.status === 'error' ? 'red' : 'terra'}`}>{o.kind}</span>
                  {o.result && <span className="output-text">{o.result.slice(0, 200)}</span>}
                </div>
              ))}
              {selected.result && output.length === 0 && (
                <pre className="agent-result">{selected.result.slice(0, 500)}</pre>
              )}
              {selected.status === 'done' && selected.result && output.length > 0 && (
                <div className="agent-final">✅ 完成</div>
              )}
            </div>
            {(selected.status === 'done' || selected.status === 'failed' || selected.status === 'idle') && (
              <div className="spawn-row">
                <textarea
                  value={followup}
                  onChange={(e) => setFollowup(e.target.value)}
                  placeholder="追加消息继续此子代理（续聊）…"
                  rows={1}
                />
                <button className="btn" onClick={() => void sendFollowup()} disabled={!followup.trim()}>
                  发送
                </button>
              </div>
            )}
          </>
        ) : (
          <div className="empty">选择左侧一个子代理查看输出与状态。</div>
        )}
      </div>
    </div>
  );
}
