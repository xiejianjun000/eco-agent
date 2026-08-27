import React, { useState } from 'react';
import { api } from '../api';

type LogEntry = { type: string; title?: string; message?: string; label?: string; chars?: number; error?: string };

const PRESETS: { id: string; name: string; desc: string; script: string }[] = [
  {
    id: 'smoke',
    name: '最小冒烟',
    desc: '1 个子代理，一句话任务（验证编排链路）',
    script: [
      'phase("冒烟")',
      "log(\"启动 1 个子代理\")",
      'r = agent("用一句话说明生态环境法典第28条的核心内容", label="法典检索")',
      'result = {"reply": r}',
    ].join('\n'),
  },
  {
    id: 'enforce-dag',
    name: '三角色执法 DAG',
    desc: '巡查+法规 并行 → 文书 → 综合（role_swarm 五步链）',
    script: [
      'phase("执法协作")',
      '案件 = args.get("case", "某化工企业废水 COD 超标排放，实测 125mg/L，限值 40mg/L")',
      'def 巡查(): return agent("对以下案件做现场巡查要点与证据固定清单：" + 案件, label="巡查")',
      'def 法规(): return agent("检索该违法行为对应的法典条款与罚则：" + 案件, label="法规")',
      'def 文书(d): return agent("依据以下要点起草责令改正决定书底稿：\\n" + d, label="文书")',
      'def 综合(d): return agent("综合两份材料输出办案结论与裁量建议：\\n" + d, label="综合")',
      'log("并行：巡查 + 法规")',
      'patrol, law = parallel([巡查, 法规])',
      'log("串行：文书 ← 法规")',
      'doc = 文书(law)',
      'log("串行：综合 ← 巡查+文书")',
      'final = 综合(patrol + "\\n" + doc)',
      'result = {"patrol": patrol, "law": law, "doc": doc, "final": final}',
    ].join('\n'),
  },
  {
    id: 'pipeline',
    name: '多企业研判流水线',
    desc: 'pipeline：3 家企业逐一研判（每项独立推进）',
    script: [
      'phase("企业研判")',
      '企业 = args.get("companies", ["A企业废水超标", "B企业危废台账不全", "C企业未验先投"])',
      'def 研判(prev, item, idx):',
      '    log("研判第 " + str(idx+1) + " 项：" + str(item))',
      '    return agent("对以下违法线索给出初步研判与证据要求：" + str(item), label="研判")',
      'out = pipeline(企业, 研判)',
      'result = {"reports": out}',
    ].join('\n'),
  },
];

export default function WorkflowView(): React.ReactElement {
  const [script, setScript] = useState(PRESETS[0].script);
  const [argsJson, setArgsJson] = useState('{}');
  const [result, setResult] = useState<unknown>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [duration, setDuration] = useState<number | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!script.trim() || busy) return;
    setBusy(true);
    setResult(null);
    setLog([]);
    setDuration(null);
    setErr('');
    let args: Record<string, unknown> = {};
    try {
      args = JSON.parse(argsJson || '{}') as Record<string, unknown>;
    } catch {
      setErr('args 不是合法 JSON');
      setBusy(false);
      return;
    }
    try {
      const r = await api.workflowRun(script, args);
      if (r.ok) {
        setResult(r.result);
        setLog(r.log ?? []);
        setDuration(r.duration_ms ?? null);
      } else {
        setErr(r.error ?? '运行失败');
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="wf-wrap">
      <div className="card wf-left">
        <div className="agents-head">
          <h2>编排脚本</h2>
          <span className="meta">hooks: agent / pipeline / parallel / phase / log / args · 结尾 result = …</span>
        </div>
        <div className="preset-row">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              className={`tb-btn${script === p.script ? ' active' : ''}`}
              title={p.desc}
              onClick={() => { setScript(p.script); setResult(null); setLog([]); setErr(''); }}
            >
              {p.name}
            </button>
          ))}
        </div>
        <textarea
          className="dyn-code wf-script"
          rows={16}
          value={script}
          onChange={(e) => setScript(e.target.value)}
          spellCheck={false}
        />
        <div className="setting-row">
          <span className="setting-label">args（JSON）</span>
          <input className="dyn-name" value={argsJson} onChange={(e) => setArgsJson(e.target.value)} />
        </div>
        <div className="goal-actions">
          <button className="btn" onClick={() => void run()} disabled={busy || !script.trim()}>
            {busy ? '运行中…（前台等待）' : '运行编排'}
          </button>
          {duration !== null && <span className="muted">用时 {(duration / 1000).toFixed(1)}s</span>}
        </div>
        {err && <div className="agent-error">❌ {err}</div>}
      </div>

      <div className="card wf-right">
        <div className="agents-head"><h2>执行日志</h2><span className="meta">{log.length} 条事件</span></div>
        <div className="agent-output wf-log">
          {log.length === 0 && !result && <div className="empty">运行后在此显示 phase/log/agent/error 事件流。</div>}
          {log.map((l, i) => (
            <div key={i} className={`output-row wf-${l.type}`}>
              <span className="badge terra">{l.type}</span>
              {l.title && <b>{l.title}</b>}
              {l.message && <span className="output-text">{l.message}</span>}
              {l.label && <span className="output-text">{l.label}（{l.chars ?? 0} 字）</span>}
              {l.error && <span className="agent-error">{l.error}</span>}
            </div>
          ))}
        </div>
        {result !== null && (
          <>
            <div className="agents-head"><h2>result</h2></div>
            <pre className="agent-result" style={{ maxHeight: 340, overflow: 'auto' }}>
              {typeof result === 'string' ? result : JSON.stringify(result, null, 2)}
            </pre>
          </>
        )}
      </div>
    </div>
  );
}
