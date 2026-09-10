import React, { useEffect, useRef, useState } from 'react';
import { streamChat, api, type ChatUsage, type TraceEvent, type SubagentInfo } from '../api';
import { renderMarkdown, escapeHtml } from '../utils/markdown';
import { renderToolResult } from '../utils/toolResult';
import TerminalPanel from '../components/Terminal';
import Icon, { type IconName } from '../components/Icon';
import DocDrawer from '../components/DocDrawer';
import ProductPanel, { MAX_PRODUCT_ITEMS, HIDDEN_PRODUCT_PATH_RE, type ProductItem } from '../components/ProductPanel';
import { type DocSource, rendererFor, isTencentDocsUrl, isFeishuUrl } from '../components/DocViewer';
import { ChatSearchButton, ConnectorTags, UserPromptListButton } from '../components/ChatTopbar';
import CompactDivider, { isCompactContent, inferCompactType } from '../components/CompactDivider';
import { buildAtom, mcpObject, selectSummary, renderSummary, type AtomStatus } from '../utils/metaFold';
import { buildBeats, extractPresented, extractSources, fmtSize, stripToolNames, type BeatItem, type WebSource } from '../utils/turnFold';
import { resolveToolDetail } from '../utils/toolViews';
import { ToolDetailPanel } from '../components/ToolDetailPanel';

interface Msg {
  role: 'user' | 'assistant';
  content: string;
  time?: string;        // 发送/完成时间
  durationMs?: number;  // 总耗时
  ttftMs?: number;      // 首个 LLM 响应耗时
  usage?: ChatUsage;    // 会话级 token 计量
  rating?: 'up' | 'down' | null;
  branchId?: string;    // 该消息所属分支（分支新对话后标记）
  trace?: TraceEvent[]; // 执行轨迹（DSH 式折叠展示）
  attachments?: { name: string; path: string; size_kb: number }[]; // 用户消息附件（DSH 式 chips）
}

/** 从 Markdown 回复里提取代码块作为产物（artifact） */
function extractArtifacts(text: string): { lang: string; code: string }[] {
  const out: { lang: string; code: string }[] = [];
  const re = /```(\w*)\n([\s\S]*?)```/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    out.push({ lang: m[1] || 'text', code: m[2].trim() });
  }
  return out;
}

/** 按轮次分组轨迹事件（DSH 式 Turns/Calls 结构） */
function groupTraceByRound(trace: TraceEvent[]): { round: number; events: TraceEvent[]; totalMs: number }[] {
  const map = new Map<number, TraceEvent[]>();
  for (const t of trace) {
    const r = t.round ?? 1;
    if (!map.has(r)) map.set(r, []);
    map.get(r)!.push(t);
  }
  return Array.from(map.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([round, events]) => ({
      round,
      events,
      totalMs: events.reduce((s, e) => s + (e.cost_ms ?? 0), 0),
    }));
}

/** 生态环境场景标签（空态顶部 pill） */
const ECO_SCENES: { id: string; icon: IconName; label: string }[] = [
  { id: 'air', icon: 'air', label: '大气监测' },
  { id: 'water', icon: 'water', label: '水质分析' },
  { id: 'permit', icon: 'clipboard', label: '排污许可' },
  { id: 'xinfang', icon: 'mail', label: '信访办理' },
  { id: 'data', icon: 'chart', label: '数据分析' },
];

/** 生态快捷入口（空态底部，点击填入输入框） */
const QUICK_ACTIONS: { icon: IconName; label: string; prompt: string }[] = [
  { icon: 'air', label: '空气质量查询', prompt: '查询娄底市今日空气质量' },
  { icon: 'water', label: '水质实时监测', prompt: '查询湘江流域断面水质数据' },
  { icon: 'clipboard', label: '许可证核查', prompt: '核查冷水江企业排污许可证' },
  { icon: 'mail', label: '信访趋势分析', prompt: '分析本月生态环境信访热点' },
  { icon: 'doc', label: '生态报告生成', prompt: '生成娄底市大气环境质量月报' },
  { icon: 'scale', label: '法规比对', prompt: '比对新旧大气污染防治法差异' },
];

function fmtClock(): string {
  const d = new Date();
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

function fmtMs(ms?: number): string {
  if (ms === undefined) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** 模型计价（元/百万 token，估算口径）：默认值与服务端 DEFAULT_PRICE_PER_M 一致；
 *  挂载后经 /api/v1/stats/summary 拉取服务端计价表覆盖，前端不再硬编码口径 */
let PRICE_PER_M = { input: 4, output: 16 };
let priceLoading = false;

function ensurePricing(): void {
  if (priceLoading) return;
  priceLoading = true;
  api.statsSummary().then((s) => {
    if (s.pricing?.default) PRICE_PER_M = s.pricing.default;
  }).catch(() => { /* 拉取失败沿用兜底价 */ });
}

/** 统计行：时间 · 用时 · 首响应 · token 速率（DSH 式计量，千分位） */
function fmtStatRow(m: Msg): string {
  const parts: string[] = [];
  if (m.time) parts.push(m.time);
  if (m.durationMs !== undefined) parts.push(`用时 ${fmtMs(m.durationMs)}`);
  if (m.ttftMs !== undefined) parts.push(`首响应 ${fmtMs(m.ttftMs)}`);
  const total = m.usage?.total_tokens;
  const durS = (m.durationMs ?? 0) / 1000;
  if (total && durS > 0) {
    parts.push(`${total.toLocaleString('en-US')} tok · ${Math.round(total / durS).toLocaleString('en-US')} tok/s`);
  }
  // 花费估算（元/百万 token，计价来自 /api/v1/stats/summary，见 ensurePricing）
  const p = m.usage?.prompt_tokens ?? 0;
  const c = m.usage?.completion_tokens ?? 0;
  const costYuan = (p * PRICE_PER_M.input + c * PRICE_PER_M.output) / 1_000_000;
  if (costYuan > 0) parts.push(`≈¥${costYuan.toFixed(3)}`);
  return parts.join(' · ');
}

/** 工具结果 JSON 摘要（截断显示 + 可展开） */
function fmtArgs(args?: Record<string, unknown>): string {
  try {
    const s = JSON.stringify(args ?? {});
    return s.length > 80 ? `${s.slice(0, 80)}…` : s;
  } catch {
    return '';
  }
}

/** 展开态工具行描述：动作 + 对象，复用 buildAtom 的语义解析。
 *
 *  此前展开后直接把原始工具名拼进 desc，页面上就出现
 *    mcp__eco-hunan-env__air_quality_hourly · {"city":"娄底市"}
 *  折叠态早已做了三段式清洗，展开态却是裸的 —— 同一份内容两套面孔。
 *  这里统一走 buildAtom（与 meta-fold 摘要、beats 同源），
 *  拿不到语义时退回参数摘要，最后再兜一层 stripToolNames 防止漏网。 */
function describeTool(name: string, args?: Record<string, unknown>): string {
  const atom = buildAtom(name, args);
  // MCP 工具的 object 不从参数提取（各服务器参数名千差万别），
  // 改用内层工具名，例如 mcp__eco-hunan-env__air_quality_hourly → 「air quality hourly」
  const obj = atom.object || (name.startsWith('mcp__') ? mcpObject(name) : undefined);
  const head = obj ? `${atom.action}${obj}` : (atom.action || atom.noObject || '');
  const detail = fmtArgs(args);
  const tail = detail && detail !== '{}' ? ` · ${detail}` : '';
  return stripToolNames(head ? `${head}${tail}` : `${name}${tail}`);
}

/** DSH 式过程块：按轮次渲染思考（完整 thought）+ 工具调用卡 */
/** 交互图表卡片（DSH visualize 对标）：沙箱 iframe 渲染 ECharts HTML。
 *  sandbox="allow-scripts"（不带 allow-same-origin）：卡片脚本可运行但不具备同源权限，
 *  无法访问父页面/localStorage——模型生成的 HTML 在隔离沙箱内执行。 */
function renderCards(trace: TraceEvent[]): React.ReactElement | null {
  /* hoist（WorkBuddy use-fold-hook isHoistedWidgetContent 对标）：
     show_widget 类内容豁免折叠，并提升到结果正文下方展示。
     这里 card 事件本就渲染在正文之后，等价于 hoist 后的落位。 */
  const cards = (trace ?? []).filter((t) => t.type === 'card' && t.html);
  if (cards.length === 0) return null;
  return (
    <div className="card-stack">
      {cards.map((c, i) => (
        <details key={i} className="card-item" open>
          <summary className="card-summary">
            <span className="card-title"><Icon name="chart" size={14} /> {c.title || '图表'}</span>
            <span className="card-hint">可交互 · 沙箱隔离渲染</span>
          </summary>
          <iframe
            className="card-frame"
            sandbox="allow-scripts"
            srcDoc={c.html}
            title={c.title || '图表卡片'}
          />
        </details>
      ))}
    </div>
  );
}

/** 按扩展名返回产物图标（对齐 QClaw 文件类型图标） */
function fileIcon(name: string): IconName {
  const ext = (name.split('.').pop() || '').toLowerCase();
  if (['md', 'txt', 'log', 'csv', 'json'].includes(ext)) return 'file-text';
  if (ext === 'docx' || ext === 'doc') return 'file-text';
  if (ext === 'pdf') return 'file';
  if (['xlsx', 'xls', 'csv'].includes(ext)) return 'chart';
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)) return 'image';
  if (['ppt', 'pptx'].includes(ext)) return 'slides';
  if (['zip', 'gz', 'tar'].includes(ext)) return 'archive';
  return 'paperclip';
}

/** 回答产物卡片：完整稿落盘为文件，点击拉取原文渲染 + 下载/复制路径/复制链接（DSH/QClaw 文件产物对标） */
function ArtifactCard({ name, title, size, path, docxName, docxPath, onOpen }: {
  name: string; title: string; size?: number; path?: string;
  docxName?: string; docxPath?: string;
  onOpen?: (src: DocSource, label: string) => void;
}): React.ReactElement {
  const [open, setOpen] = React.useState(false);
  const [content, setContent] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [copied, setCopied] = React.useState<string | null>(null);

  const toggle = () => {
    setOpen((v) => !v);
    if (content === null && !loading) {
      setLoading(true);
      void api.artifact(name)
        .then((r) => setContent(r.content ?? ''))
        .catch(() => setContent(`（拉取失败，产物文件：${name}）`))
        .finally(() => setLoading(false));
    }
  };

  const copyPath = (e: React.MouseEvent) => {
    e.stopPropagation();
    const v = path || name;
    void navigator.clipboard.writeText(v).then(() => setCopied('path'));
    setTimeout(() => setCopied(null), 1200);
  };

  const copyLink = (e: React.MouseEvent) => {
    e.stopPropagation();
    const v = `${location.origin}/api/v1/documents/artifact/${encodeURIComponent(name)}`;
    void navigator.clipboard.writeText(v).then(() => setCopied('link'));
    setTimeout(() => setCopied(null), 1200);
  };

  // 拖拽产物进输入框引用（WorkBuddy artifact drag 对标）
  const onDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData('text/plain', name);
    e.dataTransfer.effectAllowed = 'copy';
  };

  return (
    <div className={`artifact-card${open ? ' open' : ''}`} draggable onDragStart={onDragStart}
         title="点击展开预览 · 可拖拽到输入框引用">
      {/* 悬停浮现的「在抽屉中打开」按钮（WorkBuddy _floatingActions 对标：常态 opacity 0） */}
      {onOpen && rendererFor(docxName || name) !== 'none' && (
        <div className="artifact-actions">
          <button
            className="artifact-action-btn"
            title="在抽屉中打开"
            onClick={(e) => {
              e.stopPropagation();
              const target = docxName || name;
              onOpen({ kind: 'local', name: target }, target);
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 3 21 3 21 9" /><polyline points="9 21 3 21 3 15" />
              <line x1="21" y1="3" x2="14" y2="10" /><line x1="3" y1="21" x2="10" y2="14" />
            </svg>
          </button>
        </div>
      )}
      <div className="artifact-card-head" onClick={toggle}>
        <span className="artifact-card-icon"><Icon name={fileIcon(name)} size={14} /></span>
        <span className="artifact-card-title" title={name}>{title || name}</span>
        {size !== undefined && <span className="artifact-card-meta">{(size / 1024).toFixed(1)} KB</span>}
        {docxName && (
          <a
            className="artifact-card-act docx"
            title={`DOCX 版（对话提到 DOCX 时生成）：${docxPath || docxName}`}
            href={`/api/v1/documents/artifact/${encodeURIComponent(docxName)}/download`}
            download={docxName}
            onClick={(e) => e.stopPropagation()}
          ><Icon name="file-text" size={13} />DOCX</a>
        )}
        <a
          className="artifact-card-act"
          title="下载文件"
          href={`/api/v1/documents/artifact/${encodeURIComponent(name)}/download`}
          download={name}
          onClick={(e) => e.stopPropagation()}
        ><Icon name="download" size={13} /></a>
        <button className="artifact-card-act" title="复制本地路径"
                onClick={copyPath}>{copied === 'path' ? <Icon name="check" size={12} /> : <Icon name="archive" size={13} />}</button>
        <button className="artifact-card-act" title="复制分享链接"
                onClick={copyLink}>{copied === 'link' ? <Icon name="check" size={12} /> : <Icon name="link" size={13} />}</button>
      </div>
      {open && (
        <div className="artifact-card-body">
          {loading ? <span className="thinking">加载中…</span> : (
            <div className="bubble md-slim" dangerouslySetInnerHTML={{ __html: content ? renderMarkdown(content) : '' }} />
          )}
        </div>
      )}
    </div>
  );
}

/** L4 审批授权卡片：工具被权限闸门拦下后，用户可直接批准/拒绝 */
function ApprovalCard({ name, requestId }: { name: string; requestId: string }): React.ReactElement {
  const [state, setState] = React.useState<'pending' | 'decided' | 'error'>('pending');
  const [decision, setDecision] = React.useState<'' | 'allowed' | 'denied'>('');

  const decide = (allow: boolean) => {
    void api.approvalDecide(requestId, allow)
      .then((r) => {
        setDecision(r.allow ? 'allowed' : 'denied');
        setState('decided');
      })
      .catch(() => setState('error'));
  };

  return (
    <div className={`approval-card${state === 'decided' ? ' decided' : ''}`}>
      <div className="approval-card-icon"><Icon name="alert" size={20} /></div>
      <div className="approval-card-body">
        <div className="approval-card-title">需要审批：{name}</div>
        <div className="approval-card-sub">
          {state === 'pending' && '该工具为 L4 外部/涉执法操作，需你授权后才能执行'}
          {state === 'decided' && (decision === 'allowed' ? '已批准（可让模型重试该工具）' : '已拒绝')}
          {state === 'error' && '审批请求失败（请求可能已过期）'}
        </div>
      </div>
      {state === 'pending' && (
        <div className="approval-card-actions">
          <button className="approval-btn approve" onClick={() => decide(true)}>批准</button>
          <button className="approval-btn reject" onClick={() => decide(false)}>拒绝</button>
        </div>
      )}
    </div>
  );
}

function getEventIcon(type: string, name?: string): IconName {
  if (type === 'think') return 'gear';
  if (type === 'answer') return 'message';
  if (type === 'correction') return 'refresh';
  if (type === 'tool' || type === 'tool_start') {
    const n = (name || '').toLowerCase();
    if (n.includes('bash') || n.includes('shell')) return 'terminal';
    if (n.includes('read')) return 'file-text';
    if (n.includes('write') || n.includes('edit')) return 'pencil';
    return 'sparkles';
  }
  return 'sparkles';
}

/** DSH 式单条过程行：图标+类型名+描述，单行截断，点击展开完整内容。
 *  state: running(执行中，灰)/ok(完成)/error(失败，红)——DSH GenericCommandCard 三态对标
 *  follow: 流式跟随（Think 摘要自动横向滚到末尾，DSH ReasoningRow 同款） */
function ProcessRow({ icon, label, desc, meta, cost, children, state, follow }: {
  icon: IconName; label: string; desc: string; meta?: string; cost?: number;
  children?: React.ReactNode; state?: 'running' | 'ok' | 'error'; follow?: boolean;
}): React.ReactElement {
  const [open, setOpen] = React.useState(false);
  const descRef = React.useRef<HTMLSpanElement>(null);
  React.useEffect(() => {
    const el = descRef.current;
    if (el && follow) el.scrollLeft = el.scrollWidth - el.clientWidth;
  }, [desc, follow]);
  return (
    <div className={`dsh-event-row${open ? ' open' : ''}${state ? ` dsh-state-${state}` : ''}`}>
      <div className="dsh-event-line" onClick={() => { if (children) setOpen(!open); }}>
        <span className="dsh-icon"><Icon name={icon} size={14} /></span>
        <span className="dsh-type">{label}</span>
        <span className="dsh-desc" ref={descRef} data-follow-end={follow || undefined}>{desc}</span>
        {meta && <span className="dsh-meta">{meta}</span>}
        {cost !== undefined && <span className="dsh-cost">({fmtMs(cost)})</span>}
        {children && (
          <button
            className="dsh-expand"
            title={open ? '收起' : '展开'}
            onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
          >{open ? '^' : 'v'}</button>
        )}
      </div>
      {open && children && <div className="dsh-event-body">{children}</div>}
    </div>
  );
}

/** 摘要规则（DSH ReasoningRow 同款）：完成取首行，流式取末行 */
function firstLine(text: string): string {
  const nl = text.indexOf('\n');
  return nl === -1 ? text : text.slice(0, nl);
}
function latestLine(text: string): string {
  const visible = text.trimEnd();
  const nl = visible.lastIndexOf('\n');
  return nl === -1 ? visible : visible.slice(nl + 1);
}

/** 把 think_delta 分片累积为运行中的 Think 行，think 事件覆盖为权威行；
 *  tool_start → running 行，tool 事件原地替换为 ok/error 完成行（DSH 三态）。 */
function renderProcessBlock(trace: TraceEvent[]): React.ReactElement | null {
  if (!trace || trace.length === 0) return null;
  const hasProc = trace.some((t) => ['think', 'think_delta', 'tool', 'tool_start', 'answer', 'correction', 'narration'].includes(t.type));
  if (!hasProc) return null;

  // 一、扁平化事件流
  type Row = { key: string; icon: IconName; label: string; desc: string; meta?: string; cost?: number; body?: React.ReactNode; state?: 'running' | 'ok' | 'error'; follow?: boolean };
  const rows: Row[] = [];
  const live: Record<number, string> = {};  // 运行中 Think 的累积文本（按 round）
  const runningIdx: Record<string, number> = {};  // 运行中工具名 → 行下标（tool 到达时原地替换）
  let liveKey = 0;

  const flushLive = (r: number) => {
    const text = live[r];
    if (!text) return;
    delete live[r];
    rows.push({
      key: `live-${r}-${liveKey++}`,
      icon: 'gear', label: '思考', state: 'running', follow: true,
      desc: latestLine(text), meta: `R${r}`,
      body: <div className="dsh-body-text">{escapeHtml(text)}</div>,
    });
  };

  for (const ev of trace) {
    const r = ev.round ?? 1;
    if (ev.type === 'think_delta') {
      if (ev.text) live[r] = (live[r] ?? '') + ev.text;
      continue;
    }
    if (ev.type === 'think') {
      // 权威版覆盖运行中累积
      delete live[r];
      if (ev.thought) {
        rows.push({
          key: `think-${r}-${ev.cost_ms ?? rows.length}`,
          icon: 'gear', label: '思考', state: 'ok',
          desc: firstLine(ev.thought), meta: `R${r}`, cost: ev.cost_ms,
          body: <div className="dsh-body-text">{escapeHtml(ev.thought)}</div>,
        });
      }
      continue;
    }
    if (ev.type === 'tool_start') {
      const name = ev.name || '';
      runningIdx[name] = rows.length;
      rows.push({
        key: `run-${name}-${rows.length}`,
        icon: getEventIcon('tool_start', name), label: '执行',
        desc: `${describeTool(name, ev.args)} · 执行中…`, state: 'running',
      });
      continue;
    }
    if (ev.type === 'tool') {
      const name = ev.name || '';
      const err = isErrorResult(ev.result_preview);
      const row: Row = {
        key: `tool-${name}-${ev.cost_ms ?? rows.length}-${rows.length}`,
        icon: getEventIcon('tool', name), label: '执行',
        desc: `${describeTool(name, ev.args)}${err ? ' · 失败' : ''}`,
        state: err ? 'error' : 'ok', cost: ev.cost_ms,
        body: ev.result_preview
          ? <pre className="dsh-body-result" dangerouslySetInnerHTML={{ __html: renderToolResult(ev.result_preview) }} />
          : undefined,
      };
      const idx = name in runningIdx ? runningIdx[name] : undefined;
      if (idx !== undefined && rows[idx]) rows[idx] = row;  // 原地替换 running 行
      else rows.push(row);
      delete runningIdx[name];
      continue;
    }
    if (ev.type === 'narration') {
      /* 工具间旁白 = turn-fold 锚点（WorkBuddy computeTurnFoldAnchors 对标）：
         折叠态下常显，用户不展开也能看到执行节奏。 */
      rows.push({
        key: `narr-${rows.length}`,
        icon: 'message', label: '', state: 'ok',
        // 旁白是模型自由生成的，规则 8.1 要求不写工具名但模型不一定照做
        // （实测「先mcp__eco-hunan-env__air_quality_hourly」这类原样漏出），
        // 渲染前统一过一遍清洗，不指望模型自觉。
        desc: stripToolNames(ev.text || ''),
      });
      continue;
    }
    if (ev.type === 'answer') {
      rows.push({
        key: `answer-${rows.length}`,
        icon: 'message', label: '作答', state: 'ok',
        desc: `生成最终回答（共 ${(ev.chars ?? 0).toLocaleString('en-US')} 字）`,
        cost: ev.cost_ms,
      });
      continue;
    }
    if (ev.type === 'correction') {
      rows.push({
        key: `corr-${rows.length}`,
        icon: 'refresh', label: '纠偏', state: 'ok',
        desc: ev.note || '自我纠偏', cost: ev.cost_ms,
      });
      continue;
    }
  }
  // 尾部未收尾的 think_delta 也 flush 出来（流式进行中）
  for (const r of Object.keys(live).map(Number)) flushLive(r);

  /* 相邻去重：同一内容连续出现只保留一条。
     不比对 label —— 实测同一句话会以两种身份连着出现：
       [ ]      冷水江为县级市，CNEMC 未收录独立站点，以娄底市国控站为背景参考…
       [思考]   冷水江为县级市，CNEMC 未收录独立站点，以娄底市国控站为背景参考…
     前者是 narration（label 为空），后者是 think 事件，内容一字不差。
     旧写法要求 label 也相同，这类跨类型重复就漏了过去。
     保留先出现的那条（narration 在前，正是执行节奏所在的位置）。 */
  const norm = (t: string) => (t || '').replace(/\s+/g, '').trim();
  const deduped = rows.filter((row, i) =>
    i === 0 || norm(row.desc) === '' || norm(row.desc) !== norm(rows[i - 1].desc));

  return (
    <div className="process-block dsh-process">
      {deduped.map((row) => (
        <ProcessRow key={row.key} icon={row.icon} label={row.label}
                    desc={row.desc} meta={row.meta} cost={row.cost}
                    state={row.state} follow={row.follow}>
          {row.body}
        </ProcessRow>
      ))}
    </div>
  );
}

/** 过程块容器：流式中实时展开，回答输出完成后自动收起为一行摘要。
 *  用户可点摘要行随时回看完整过程（DSH 整洁版面对标：过程不长期占版）。 */
/**
 * 单条执行节奏行。
 *
 * 独立成组件是为了「逐行展开」：每行自己持有展开态。
 * WorkBuddy 的 ToolExpandable 也是每个工具实例各管各的，
 * 而不是整段过程共用一个开关 —— 后者会导致展开一个工具就把
 * 十几个工具的明细全铺开，反而更乱。
 *
 * 头部结构与折叠态完全一致，明细只挂在下方 shell（见 ToolDetailPanel）。
 */
export function BeatRow({ b }: { b: BeatItem }): React.ReactElement {
  const [open, setOpen] = React.useState(false);
  // 思考块可折叠展开（对标 WorkBuddy reasoning block）
  const isThink = b.kind === 'think';
  const isTask = b.kind === 'task';
  // 只有 act 且真有结构化内容才可展开；detail 为 null 时不出箭头
  const detail = b.kind === 'act'
    ? resolveToolDetail(b.toolName || '', (b.toolArgs || {}) as Record<string, unknown>, b.resultPreview)
    : null;
  const state: 'running' | 'ok' | 'error' | 'skipped' = b.state
    ?? (b.running ? 'running' : b.ok === false ? 'error' : 'ok');
  const canExpand = detail !== null || (isThink && !!b.body) || isTask;
  const dotCls = b.kind === 'act'
    ? (state === 'running' ? ' running' : state === 'error' ? ' err' : state === 'skipped' ? ' skip' : ' ok')
    : (state === 'running' ? ' running' : ' ok');
  return (
    <div className={`turn-anchor beat-${b.kind}${state === 'running' ? ' beat-running' : ''}${state === 'skipped' ? ' beat-skip' : ''}${canExpand ? ' beat-expandable' : ''}${open ? ' beat-open' : ''}`}
         data-tool-view={b.kind === 'act' ? (b.viewId || 'fallback') : b.kind}>
      <div className="turn-anchor-head"
           onClick={canExpand ? () => setOpen((v) => !v) : undefined}
           role={canExpand ? 'button' : undefined}
           tabIndex={canExpand ? 0 : undefined}
           onKeyDown={canExpand ? (e) => {
             if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen((v) => !v); }
           } : undefined}>
        <span className={`turn-anchor-dot${dotCls}`} aria-hidden="true" />
        {isThink && <Icon name="gear" size={12} />}
        {isTask && <Icon name="clipboard" size={12} />}
        {/* 三段式（对标 WorkBuddy ToolHeader）：动词 · 主体 · 次要信息，互不重复 */}
        <span className="turn-anchor-text">
          {b.status && <span className="beat-status">{b.status}</span>}
          {b.text && <span className="beat-primary">{b.text}</span>}
          {/* 变更行数：加/删分色两段，不塞进文字里（对标 WorkBuddy +N -M）。
              创建文件时 removed 为 0 也照常显示，与「编辑」形成对照。 */}
          {(b.added !== undefined || b.removed !== undefined) && (
            <span className="beat-diff">
              <span className="beat-diff-add">+{b.added ?? 0}</span>
              <span className="beat-diff-del">-{b.removed ?? 0}</span>
            </span>
          )}
          {/* 退出码校验（对标 tool.executeCommand.exitCode）：非 0 红色 */}
          {b.exitCode !== undefined && (
            <span className={`beat-exitcode${b.exitCode === 0 ? ' ok' : ' err'}`}>
              退出码 {b.exitCode}
            </span>
          )}
          {b.secondary && <span className="beat-second">{b.secondary}</span>}
          {b.ms !== undefined && b.ms > 0 && <span className="beat-ms">{fmtMs(b.ms)}</span>}
        </span>
        {canExpand && <span className="beat-arrow" aria-hidden="true">▾</span>}
      </div>
      {/* 任务块：RoleSwarm 三角色 + 总管合成进度（对标 taskList.status） */}
      {isTask && open && (
        <div className="beat-task-body">
          {(b.steps || []).map((s, i) => (
            <div key={i} className={`beat-task-step st-${s.state}`}>
              <span className="beat-task-dot" aria-hidden="true">
                {s.state === 'running' ? '◐' : s.state === 'error' ? '✕'
                  : s.state === 'pending' ? '○' : '✓'}
              </span>
              <span className="beat-task-label">{s.label}</span>
              {s.ms !== undefined && s.ms > 0 && <span className="beat-ms">{fmtMs(s.ms)}</span>}
            </div>
          ))}
        </div>
      )}
      {/* 思考块正文：折叠在头部下（reasoning block） */}
      {isThink && open && b.body && (
        <div className="beat-think-body dsh-body-text">{escapeHtml(b.body)}</div>
      )}
      {detail && <ToolDetailPanel detail={detail} open={open} />}
    </div>
  );
}

function ProcessBlock({ trace, live }: { trace: TraceEvent[]; live: boolean }): React.ReactElement | null {
  const [open, setOpen] = React.useState(live);
  const wasLive = React.useRef(live);
  const touched = React.useRef(false);  // 用户手动开合过就不再自动接管

  React.useEffect(() => {
    if (touched.current) return;
    if (wasLive.current && !live) setOpen(false);   // 流式收尾 → 自动隐藏
    else if (!wasLive.current && live) setOpen(true);  // 新一轮开始 → 自动展开
    wasLive.current = live;
  }, [live]);

  const inner = renderProcessBlock(trace);
  if (!inner) return null;

  const nThink = trace.filter((t) => t.type === 'think').length;
  const nTool = trace.filter((t) => t.type === 'tool').length;
  const totalMs = trace.reduce((s, t) => s + (t.cost_ms ?? 0), 0);

  /* meta-fold 摘要（WorkBuddy mata-fold/summary 对标）：
     把机械计数替换成「读取 X / 修改 Y / 多阶段主题」这类人话摘要。
     决策优先级：等待 > 单一工具 > 单一分组 > 多阶段共同主题 > 多类计数 > 兜底；
     刻意不含失败分支——失败工具按完成处理，摘要只讲做了什么。 */
  const foldSummary = React.useMemo(() => {
    const atoms = trace
      .filter((t) => t.type === 'tool' || t.type === 'tool_start')
      .map((t) => buildAtom(
        t.name,
        t.args,
        (t.type === 'tool_start' ? 'running' : 'success') as AtomStatus,
      ));
    if (atoms.length === 0) return '';
    const { decision, status } = selectSummary(atoms, live);
    return renderSummary(decision, status);
  }, [trace, live]);

  const parts = [
    nThink ? `思考 ${nThink}` : '',
    nTool ? `工具 ${nTool}` : '',
    totalMs ? fmtMs(totalMs) : '',
  ].filter(Boolean);

  /* turn-fold 锚点：旁白在折叠态也常显。
     对标 buildTurnFoldSegments —— 锚点段永远可见，过程段才受折叠控制。

     ⚠️ 此处刻意偏离 WorkBuddy 的 computeTurnFoldAnchors，理由如下：
     原实现的锚点 = 「所有最长正文 + 最后一条正文」，那是为**长回答**设计的
     ——一段 800 字的分析里挑最长段落当摘要，合理。
     但 eco 的旁白（规则 8.1）是每次调工具前的**等长短句**，长度都在 15-25 字。
     套用原规则会出现：3 行旁白只留下「最长的那句 + 最后一句」，中间被吞。
     实测 [T('先看 helper 签名和可复用函数'), T('写完了'), T('部署')] → 只剩第 1、3 条。
     那样恰好破坏了要还原的执行节奏，与目的相悖。

     故这里对 narration 类型全量常显；computeAnchors 的原语义完整保留在
     utils/turnFold.ts 中（含单测），供未来对长正文分段时使用。 */
  /* 执行节奏时间线：旁白与每个工具按发生顺序交织，一步一行。
     模型会一轮并行发多个工具（快，20s vs 串行 60s+），旁白只出现在轮次边界，
     所以光渲染旁白会得到「1 行 + 一坨工具」。这里把工具也各占一行，
     还原「输出一行 → 查文件 → 输出一行 → 改文件」的阅读节奏。 */
  const beats = buildBeats(trace as never[], isErrorResult);

  /* 成果卡片（对标 WorkBuddy present_files → artifact cards）：
     没有统一呈现入口时，产物只能散落在过程块里，用户根本看不到。 */
  const presented = extractPresented(trace as never[]);

  return (
    <div className={`proc-wrap${open ? ' open' : ''}${live ? ' live' : ''}`}>
      {/* 节奏行始终常显 —— 折叠、展开、运行中都在。
          对标 WorkBuddy ToolExpandable：展开只是在同一个三段式头部下面
          追加 children 细节，不会换成另一套视觉语言。
          此前写的是 (!open || live)，导致一展开三段式整体消失、
          换回裸露的 Think / Tool call / mcp__xxx__yyy 原始行，
          等于两套皮并存，改造过的那套只在折叠时可见。 */}
      {beats.length > 0 && (
        <div className="turn-anchors">
          {beats.map((b, i) => <BeatRow b={b} key={i} />)}
        </div>
      )}
      <button
        className="proc-toggle"
        title={open ? '收起过程' : '展开过程（思考 / 执行 / 工具调用）'}
        onClick={() => { touched.current = true; setOpen((v) => !v); }}
      >
        <span className="proc-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
        <Icon name="gear" size={13} />
        <span className="proc-summary">
          {foldSummary || (live ? '执行中' : '过程')}
          {parts.length > 0 && <span className="proc-stat"> · {parts.join(' · ')}</span>}
        </span>
      </button>
      {open && inner}
      {/* 成果卡片（对标 WorkBuddy present_files → artifact cards）：
          放在过程块外常显，折叠与否都能看到并下载。 */}
      {presented.length > 0 && (
        <div className="artifact-strip">
          <div className="artifact-strip-title">成果</div>
          {presented.map((f) => (
            <a className="artifact-chip" key={f.path}
               href={`/api/v1/presented?path=${encodeURIComponent(f.path)}`}
               download={f.name} title={f.path}>
              <span className="artifact-chip-ext">{f.ext || 'file'}</span>
              <span className="artifact-chip-name">{f.name}</span>
              <span className="artifact-chip-size">{fmtSize(f.size)}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

/** ── DSH 轨迹页对标：工具栏（Duration/Turns/Calls + 搜索）+ Gantt 时间轴 + badge 事件行 ── */
type TrajKind = 'assistant' | 'tool' | 'compacted' | 'context' | 'approval';

interface TrajRow {
  key: string;
  round: number;
  kind: TrajKind;
  badge: string;
  desc: string;
  cost?: number;
  error?: boolean;
  searchText: string;
  body?: React.ReactNode;
}

/** 工具结果是否报错（无显式 error 字段，按结果预览文本特征判定） */
function isErrorResult(preview?: string): boolean {
  if (!preview) return false;
  const p = preview.trim();
  // 错误 JSON：{"ok": false, ...} / {"error": ...}（大小写兼容）
  if (/^\{\s*"ok"\s*:\s*false/i.test(p)) return true;
  if (/^\{\s*"error"/i.test(p)) return true;
  return /^(error|错误|失败|exception)/i.test(p) || /\b(Error|Exception|Traceback)\b/.test(p.slice(0, 120));
}

/** 把轨迹事件流拍平成 DSH 式事件行（think_delta/tool_start 归并不单独成行） */
function buildTrajRows(trace: TraceEvent[]): TrajRow[] {
  const rows: TrajRow[] = [];
  for (const t of trace) {
    const round = t.round ?? 1;
    if (t.type === 'think' && t.thought) {
      rows.push({
        key: `think-${rows.length}`, round, kind: 'assistant', badge: 'ASSISTANT',
        desc: t.thought, cost: t.cost_ms,
        searchText: t.thought,
        body: <div className="dsh-body-text">{escapeHtml(t.thought)}</div>,
      });
    } else if (t.type === 'narration') {
      rows.push({
        key: `narr-${rows.length}`, round, kind: 'assistant', badge: 'NARRATION',
        // 同过程块：显示前清洗工具名；searchText 保留原文，便于按真实名检索
        desc: stripToolNames(t.text || ''), searchText: t.text || '',
      });
    } else if (t.type === 'answer') {
      rows.push({
        key: `answer-${rows.length}`, round, kind: 'assistant', badge: 'ASSISTANT',
        desc: `生成回答（共 ${(t.chars ?? 0).toLocaleString('en-US')} 字）`, cost: t.cost_ms,
        searchText: 'answer 生成回答',
      });
    } else if (t.type === 'tool') {
      const err = isErrorResult(t.result_preview);
      const firstLine = (t.result_preview ?? '').split('\n')[0].slice(0, 60);
      rows.push({
        key: `tool-${rows.length}`, round, kind: 'tool', badge: 'TOOL',
        desc: `${t.name} ${fmtArgs(t.args)}${firstLine ? ` → ${err ? 'error' : firstLine}` : ''}`,
        cost: t.cost_ms, error: err,
        searchText: `${t.name ?? ''} ${JSON.stringify(t.args ?? {})} ${t.result_preview ?? ''}`,
        body: t.result_preview
          ? <pre className="dsh-body-result" dangerouslySetInnerHTML={{ __html: renderToolResult(t.result_preview) }} />
          : undefined,
      });
    } else if (t.type === 'correction') {
      rows.push({
        key: `corr-${rows.length}`, round, kind: 'compacted', badge: 'CORRECTION',
        desc: t.note || '自我纠偏', cost: t.cost_ms, error: true,
        searchText: t.note || 'correction 自我纠偏',
      });
    } else if (t.type === 'document' || t.type === 'artifact' || t.type === 'card') {
      const label = t.type === 'card' ? 'CARD' : 'CONTEXT';
      const desc = t.title || t.name || t.url || t.type;
      rows.push({
        key: `ctx-${rows.length}`, round, kind: 'context', badge: label,
        desc, cost: t.cost_ms,
        searchText: `${t.type} ${desc} ${t.url ?? ''}`,
      });
    } else if (t.type === 'approval') {
      rows.push({
        key: `appr-${rows.length}`, round, kind: 'approval', badge: 'APPROVAL',
        desc: `需要审批：${t.name ?? '工具'}`, cost: t.cost_ms, error: true,
        searchText: `approval ${t.name ?? ''}`,
      });
    }
    // think_delta / tool_start 不成行（流式分片与工具起始已由 think/tool 权威事件覆盖）
  }
  // 相邻去重：流式 answer 可能重复发射同一事件，只保留一条
  return rows.filter((r, i) => i === 0 || rows[i - 1].badge !== r.badge || rows[i - 1].desc !== r.desc);
}

/** DSH 式 Gantt 时间轴：Model 行（think/answer，紫）+ Tools 行（tool，橙）；错误红块。
 *  x 轴 = cost_ms 累积相对时间（TraceEvent 无绝对时间戳），块宽 ∝ cost_ms。 */
function TraceTimeline({ trace }: { trace: TraceEvent[] }): React.ReactElement | null {
  const spans: { lane: 'model' | 'tools'; left: number; width: number; error: boolean; title: string }[] = [];
  let acc = 0;
  for (const t of trace) {
    if (t.type === 'think_delta' || t.type === 'tool_start') continue;
    const cost = t.cost_ms ?? 0;
    if (t.type === 'think' || t.type === 'answer' || t.type === 'correction') {
      if (t.type !== 'think' || t.thought) {
        spans.push({
          lane: 'model', left: acc, width: cost, error: t.type === 'correction',
          title: `R${t.round ?? 1} · ${t.type === 'think' ? 'Think' : t.type === 'answer' ? 'Answer' : 'Correction'} · ${fmtMs(cost)}`,
        });
      }
    } else if (t.type === 'tool') {
      spans.push({
        lane: 'tools', left: acc, width: cost, error: isErrorResult(t.result_preview),
        title: `R${t.round ?? 1} · ${t.name ?? 'tool'} · ${fmtMs(cost)}`,
      });
    }
    acc += cost;
  }
  if (spans.length === 0) return null;
  const total = Math.max(acc, 1);
  const lane = (name: 'model' | 'tools', label: string) => (
    <div className="traj-lane">
      <span className="traj-lane-label">{label}</span>
      <div className="traj-lane-track">
        {spans.filter((s) => s.lane === name).map((s, i) => (
          <span
            key={i}
            className={`traj-span${s.error ? ' error' : ''} ${name}`}
            style={{ left: `${(s.left / total) * 100}%`, width: `${Math.max((s.width / total) * 100, 0.8)}%` }}
            title={s.title}
          />
        ))}
      </div>
    </div>
  );
  return (
    <div className="traj-timeline">
      {lane('model', 'Model')}
      {lane('tools', 'Tools')}
    </div>
  );
}

/** DSH 式单条轨迹行：彩色 badge + 单行截断摘要 + 耗时，点击展开详情 */
function TrajRowView({ row, showCost }: { row: TrajRow; showCost: boolean }): React.ReactElement {
  const [open, setOpen] = React.useState(false);
  return (
    <div className={`traj-row${open ? ' open' : ''}`}>
      <div className="traj-row-line" onClick={() => { if (row.body) setOpen(!open); }}>
        {row.error && <span className="traj-err-dot" title="错误" />}
        <span className={`traj-badge traj-badge-${row.kind}`}>{row.badge}</span>
        <span className="traj-desc" title={row.desc}>{row.desc}</span>
        {showCost && row.cost !== undefined && <span className="traj-cost">{fmtMs(row.cost)}</span>}
        {row.body && (
          <button
            className="dsh-expand"
            title={open ? '收起' : '展开'}
            onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
          >{open ? '^' : 'v'}</button>
        )}
      </div>
      {open && row.body && <div className="dsh-event-body">{row.body}</div>}
    </div>
  );
}

/** DSH 式轨迹工具栏：Duration/Turns/Calls pill + 搜索框（右栏面板与整页轨迹 tab 共用） */
function TrajToolbar({ dur, turns, calls, query, onDur, onTurns, onCalls, onQuery }: {
  dur: boolean; turns: boolean; calls: boolean; query: string;
  onDur: () => void; onTurns: () => void; onCalls: () => void; onQuery: (v: string) => void;
}): React.ReactElement {
  return (
    <div className="traj-toolbar">
      <button className="traj-toggle" aria-pressed={dur} title="显示耗时统计与每行耗时" onClick={onDur}>Duration</button>
      <button className="traj-toggle" aria-pressed={turns} title="按 Turn N 分组显示轮次头" onClick={onTurns}>Turns</button>
      <button className="traj-toggle" aria-pressed={calls} title="显示工具调用行" onClick={onCalls}>Calls</button>
      <div className="traj-search">
        <input type="search" placeholder="搜索" value={query} onChange={(e) => onQuery(e.target.value)} />
      </div>
    </div>
  );
}

/** 共享事件行列表：搜索过滤 + Calls 开关 + Turn 分组（右栏面板与整页轨迹 tab 共用） */
function TrajEventList({ rows, showTurns, showCalls, query, showCost }: {
  rows: TrajRow[]; showTurns: boolean; showCalls: boolean; query: string; showCost: boolean;
}): React.ReactElement {
  const q = query.trim().toLowerCase();
  const visible = rows.filter((r) =>
    (showCalls || r.kind !== 'tool')
    && (!q || r.searchText.toLowerCase().includes(q) || r.desc.toLowerCase().includes(q)));
  if (visible.length === 0) return <div className="empty" style={{ padding: 16 }}>无匹配事件</div>;
  const byRound: [number, TrajRow[]][] = [];
  for (const r of visible) {
    const last = byRound[byRound.length - 1];
    if (last && last[0] === r.round) last[1].push(r);
    else byRound.push([r.round, [r]]);
  }
  return (
    <>
      {byRound.map(([round, rs]) => (
        <div key={round} className="traj-turn-group">
          {showTurns && <div className="traj-turn-head">Turn {round}</div>}
          {rs.map((r) => <TrajRowView key={r.key} row={r} showCost={showCost} />)}
        </div>
      ))}
    </>
  );
}

export default function ChatView({
  sessionId = 'default',
  onActivity,
  workspaces = [],
  activeWorkspace = '',
  onWorkspaceChange,
  onWorkspacesChange,
}: {
  sessionId?: string;
  onActivity?: () => void;
  workspaces?: { id: string; name: string }[];
  activeWorkspace?: string;
  onWorkspaceChange?: (id: string) => void;
  onWorkspacesChange?: () => void;
}): React.ReactElement {
  // 新会话从空消息开始：欢迎信息由 hero 主页承担，不再注入"你好，我是 eco Agent…"气泡
  const [messages, setMessages] = useState<Msg[]>([]);
  const [activeScene, setActiveScene] = useState<string>('air');
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [model, setModel] = useState('');
  // 计划/只读模式（对标 WorkBuddy input.planMode）：本轮只给只读工具，不写不执行。
  const [planMode, setPlanMode] = useState<boolean>(
    () => window.localStorage.getItem('eco-plan-mode') === '1');
  // 发送中可中止（对标 input.sendButton.stop）
  const abortRef = React.useRef<AbortController | null>(null);
  const [branchTag, setBranchTag] = useState<string | null>(null);
  const [showTerminal, setShowTerminal] = useState(false);
  type SideTab = 'trace' | 'context' | 'artifact' | 'doc' | 'task' | 'slot' | 'preview' | 'tasklog';
  // 右栏 tab 按会话持久化（WorkBuddy session-detail-restore 对标：切回来恢复上次视图）
  const [_sideTab, setSideTab] = useState<SideTab>(() => {
    const saved = window.localStorage.getItem(`eco-side-tab-${sessionId}`);
    return (['trace', 'context', 'artifact', 'doc', 'task', 'slot', 'preview', 'tasklog'] as SideTab[]).includes(saved as SideTab)
      ? (saved as SideTab) : 'trace';
  });
  const switchTab = (t: SideTab) => {
    setSideTab(t);
    window.localStorage.setItem(`eco-side-tab-${sessionId}`, t);
  };
  void switchTab; // 右侧栏已移除；保留供后续预览面板复用
  // 以下三组状态的写入入口（上下文 / 日志 tab）已按需求从右侧栏移除，
  // 面板渲染代码保留以便后续按抽屉方式复用，故只保留读取端。
  const [_docFiles, setDocFiles] = useState<{ name: string; path: string; size_kb: number }[]>([]);
  const [_docTools, setDocTools] = useState<{ name: string; desc: string }[]>([]);
  /** 磁盘上已持久化的 MD 产物（全局扫描）。
   *  不再作为右栏数据源：右栏按 WorkBuddy 口径只显示**当前会话**产物（trace）。
   *  保留拉取，供 ArtifactCard 等对话内卡片需要磁盘真实状态时使用；下划线前缀
   *  标明当前不直接渲染，避免误又合并回右栏导致跨会话堆叠。 */
  const [, setPersistedArtifacts] = useState<{ name: string; title: string; size: number; path?: string }[]>([]);
  // 右侧预览面板：文档生成/上传后自动内嵌打开 docs.qq.com（不弹系统浏览器）
  const [_previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [_previewTitle, setPreviewTitle] = useState<string>('');
  const sawDocEventRef = useRef(false);
  const contentRef = useRef('');
  // 子代理任务面板（对标 DSH subagent/jobs）
  const [_taskAgents, setTaskAgents] = useState<SubagentInfo[]>([]);
  const [taskInput, setTaskInput] = useState('');
  const [taskSpawnBusy, setTaskSpawnBusy] = useState(false);
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const [_taskDetail, setTaskDetail] = useState<{ agent: SubagentInfo; output: { seq: number; kind: string; status?: string; result?: string }[] } | null>(null);
  const [taskFollowup, setTaskFollowup] = useState('');
  // Slot 动态面板（插件注册）
  const [slotPanels, setSlotPanels] = useState<{ id: string; title: string; description: string }[]>([]);
  const [activeSlot, setActiveSlot] = useState<string | null>(null);
  const [slotData, setSlotData] = useState<Record<string, unknown> | null>(null);
  // 权限闸门真实状态（来自 api.system()，null = 加载中）
  const [permGate, setPermGate] = useState<boolean | null>(null);

  // ── DSH 式右栏：输出产物可收缩 + 左右拖拽调宽 ────────────
  const [_panelOpen, setPanelOpen] = useState<boolean>(() => window.localStorage.getItem('eco-panel-open') !== '0');
  const [panelW, setPanelW] = useState<number>(() => {
    const saved = Number(window.localStorage.getItem('eco-panel-w'));
    // 默认 420：WorkBuddy 抽屉实测宽度；仍可拖拽，用户自定义值优先
    return Number.isFinite(saved) && saved >= 260 && saved <= 900 ? saved : 420;
  });

  const startResize = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = panelW;
    let w = startW;
    const onMove = (ev: PointerEvent) => {
      // 拖拽条向左 → 面板变宽（面板在右侧，宽度 = 起始 + 左移距离）
      w = Math.min(900, Math.max(260, startW + (startX - ev.clientX)));
      setPanelW(w);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    };
    const onUp = () => {
      window.localStorage.setItem('eco-panel-w', String(w));
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };
  void startResize; // 右侧栏已移除；保留供后续预览面板复用

  // ── 输入栏附件 / 语音（DSH 式）────────────────────────────
  const [attachments, setAttachments] = useState<{ name: string; path: string; size_kb: number }[]>([]);
  const [voice, setVoice] = useState<'idle' | 'recording' | 'transcribing'>('idle');
  const [voiceSec, setVoiceSec] = useState(0);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const voiceChunksRef = useRef<Blob[]>([]);
  const voiceTimerRef = useRef<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const uploadFiles = async (files: FileList | File[]) => {
    const list = Array.from(files);
    for (const f of list) {
      try {
        const data = await api.uploadFile(f);
        if (!data.ok || !data.path) throw new Error(data.ok === false ? '上传失败' : '上传失败');
        setAttachments((prev) => [...prev, { name: f.name, path: data.path, size_kb: data.size_kb ?? 0 }]);
      } catch (err) {
        window.alert(`文件上传失败: ${(err as Error).message}`);
      }
    }
  };

  const toggleVoice = async () => {
    if (voice === 'recording') {
      stopRecording();
      return;
    }
    if (voice === 'transcribing') return;
    if (!navigator.mediaDevices?.getUserMedia) {
      window.alert('当前浏览器不支持麦克风录音（需 localhost/HTTPS 环境）');
      return;
    }
    setVoiceError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : '';
      const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      recorderRef.current = rec;
      voiceChunksRef.current = [];
      rec.ondataavailable = (ev) => { if (ev.data.size > 0) voiceChunksRef.current.push(ev.data); };
      rec.onstop = () => { stream.getTracks().forEach((t) => t.stop()); void finishVoice(); };
      rec.start();
      setVoice('recording');
      setVoiceSec(0);
      voiceTimerRef.current = window.setInterval(() => setVoiceSec((s) => s + 1), 1000);
    } catch (err) {
      window.alert(`无法访问麦克风: ${(err as Error).message}`);
    }
  };

  const stopRecording = () => {
    if (voiceTimerRef.current !== null) {
      window.clearInterval(voiceTimerRef.current);
      voiceTimerRef.current = null;
    }
    if (recorderRef.current && recorderRef.current.state !== 'inactive') recorderRef.current.stop();
  };

  const finishVoice = async () => {
    const chunks = voiceChunksRef.current;
    voiceChunksRef.current = [];
    if (chunks.length === 0) {
      setVoice('idle');
      return;
    }
    const blob = new Blob(chunks, { type: chunks[0].type || 'audio/webm' });
    setVoice('transcribing');
    try {
      const data = await api.transcribeVoice(blob, `voice-${Date.now()}.webm`);
      if (data.ok && data.text) {
        setInput((prev) => (prev ? `${prev}\n${data.text!}` : data.text!));
      } else {
        setVoiceError(data.error || '转写失败（音频已保留在工作区 uploads/）');
      }
    } catch (err) {
      setVoiceError((err as Error).message);
    } finally {
      setVoice('idle');
    }
  };

  React.useEffect(() => {
    import('../api').then(({ api }) => {
      api.documents().then((r) => {
        setDocFiles(r.files);
        if (r.artifacts && r.artifacts.length > 0) {
          setPersistedArtifacts(r.artifacts.map((a) => ({
            name: a.name,
            title: a.name.replace(/\.md$/, '').replace(/_\d+$/, ''),
            size: Math.round(a.size_kb * 1024),
            path: a.path,
          })));
        }
      }).catch(() => {});
      api.documentTools().then((r) => setDocTools(r.tools)).catch(() => {});
      // 会话恢复：按当前会话（工作区点击的真实 session_id）重放历史，
      // assistant 消息一并还原过程块（trace，完成态渲染）与统计行（usage/耗时）
      api.sessionMessages(sessionId).then((r) => {
        if (r.count > 0) {
          const restored: Msg[] = r.messages.map((m) => ({
            role: m.role as 'user' | 'assistant',
            content: m.content,
            time: fmtClock(),
            trace: m.trace,
            usage: m.usage,
            durationMs: m.duration_ms,
            ttftMs: m.ttft_ms,
          }));
          setMessages((prev) => [...prev, ...restored]);
        }
      }).catch(() => {});
      // Slot 面板动态加载
      api.slots().then((r) => setSlotPanels(r.slots)).catch(() => {});
      // 权限闸门真实状态（meta 栏展示）
      api.system().then((d) => setPermGate(Boolean((d as { permission_gate?: { enabled?: boolean } }).permission_gate?.enabled))).catch(() => {});
      // 模型计价口径：从 /stats/summary 拉取（替换历史硬编码 PRICE_PER_M）
      ensurePricing();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);
  const [selectedTrace, setSelectedTrace] = useState<number | null>(null);
  // 轨迹面板视图开关（DSH 轨迹页对标）：Duration 耗时统计 / Turns 轮次分组头 / Calls 工具行
  const [durOpen, setDurOpen] = useState(true);
  const [turnsOpen, setTurnsOpen] = useState(true);
  const [callsOpen, setCallsOpen] = useState(true);
  const [traceQuery, setTraceQuery] = useState('');
  // 会话页顶部 tab：对话 / 整页轨迹（DSH 3080 布局）
  const [mainTab, setMainTab] = useState<'chat' | 'trace' | 'audit'>('chat');
  // 产物抽屉（WorkBuddy artifact drawer 对标）：本地文件 / 云文档 / 图表都走它
  const [docSource, setDocSource] = useState<DocSource | null>(null);
  const [docTitle, setDocTitle] = useState<string>('');
  const openDoc = React.useCallback((src: DocSource, label: string) => {
    setDocSource(src); setDocTitle(label);
  }, []);
  // 常驻右栏产物面板（WorkBuddy ProductPanel 对标）：默认展开，可收起
  const [productOpen, setProductOpen] = useState<boolean>(
    () => window.localStorage.getItem('eco-product-panel-open') !== '0',
  );
  const toggleProductPanel = React.useCallback(() => {
    setProductOpen((v) => {
      window.localStorage.setItem('eco-product-panel-open', v ? '0' : '1');
      return !v;
    });
  }, []);
  const logRef = useRef<HTMLDivElement>(null);

  // 最新一条带轨迹的 assistant 消息自动选中
  const lastTraceIndex = (() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === 'assistant' && (messages[i].trace?.length ?? 0) > 0) return i;
    }
    return null;
  })();
  const activeTraceMsg = selectedTrace !== null ? messages[selectedTrace] : null;
  const _activeTrace = activeTraceMsg?.trace ?? messages[lastTraceIndex ?? -1]?.trace ?? [];
  void _activeTrace; // 轨迹页改用 sessionTraceGroups；保留供后续复用

  // 整页轨迹 tab：会话级聚合（所有带轨迹的 assistant 消息）
  const sessionTraceGroups = messages
    .map((m, i) => ({ m, i }))
    .filter((g) => g.m.role === 'assistant' && (g.m.trace?.length ?? 0) > 0);
  const allSessionTrace = sessionTraceGroups.flatMap((g) => g.m.trace ?? []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const _artifacts = messages
    .filter((m) => m.role === 'assistant')
    .flatMap((m) => extractArtifacts(m.content));
  void _artifacts; // 产物面板已移除；保留供后续复用

  /** 当前会话产物：从轨迹 artifact 事件收集（WorkBuddy 单一真源口径）。
   *  只有带 sourceTool 凭证的主动产物（SaveDocument/PresentFiles）才进右栏；
   *  兼容历史 trace：无 sourceTool 但有 name/path 的旧事件也保留（回放旧会话）。 */
  const sessionArtifacts = messages
    .filter((m) => m.role === 'assistant')
    .flatMap((m) => (m.trace ?? []).filter((t) => t.type === 'artifact' && t.name))
    .map((t) => ({
      name: t.name!,
      title: t.title ?? t.name!,
      size: t.size,
      path: t.path,
      mimeType: t.mimeType,
      contentType: t.contentType,
      createdAt: typeof t.createdAt === 'number' ? t.createdAt : undefined,
      sourceTool: t.sourceTool,
    }));

  /** 右栏只显示**当前会话**的主动产物，且对标 WorkBuddy artifact-slot-panel：
   *  - 黑名单路径不显示（.eco/memory-tree/session_log 等内部文件）；
   *  - 按名去重（同名保留最新，因 save_document 同名会追加序号、PresentFiles 可能重复）；
   *  - 按 createdAt 降序（没有时间戳的旧事件退到末尾，保持稳定顺序）；
   *  - 最多 6 条（MAX_PRODUCT_ITEMS）。 */
  const allMdArtifacts: ProductItem[] = (() => {
    const hidden = (a: ProductItem) => HIDDEN_PRODUCT_PATH_RE.test(a.path || a.name);
    const dedup = new Map<string, ProductItem>();
    for (const a of sessionArtifacts) {
      if (hidden(a)) continue;
      const prev = dedup.get(a.name);
      if (!prev || (a.createdAt ?? 0) > (prev.createdAt ?? 0)) dedup.set(a.name, a);
    }
    return [...dedup.values()]
      .sort((x, y) => (y.createdAt ?? -1) - (x.createdAt ?? -1))
      .slice(0, MAX_PRODUCT_ITEMS);
  })();

  /** 来源聚合（对标 WorkBuddy DetailPanel sources）：当前会话 web_search 引用的网页。 */
  const sessionSources: WebSource[] = React.useMemo(() => {
    const all = messages.filter((m) => m.role === 'assistant')
      .flatMap((m) => extractSources((m.trace ?? []) as never[]));
    const seen = new Set<string>();
    return all.filter((s) => (seen.has(s.url) ? false : (seen.add(s.url), true)));
  }, [messages]);

  /** 新会话欢迎态：还没有任何用户消息时显示居中的 hero 主页（DSH 对标） */
  const fresh = messages.length === 0;

  // ── 子代理任务面板逻辑 ─────────────────────────────
  // 选中任务轮询（running/pending 时每 2.5s 刷新，done 后停止）
  useEffect(() => {
    if (!selectedTask) return;
    let alive = true;
    const poll = async () => {
      try {
        const d = await api.subagentGet(selectedTask);
        if (!alive) return;
        setTaskDetail({ agent: d.agent, output: d.output });
        void api.subagentList().then((l) => { if (alive) setTaskAgents(l.agents); }).catch(() => {});
        if (d.agent.status === 'running' || d.agent.status === 'pending') {
          window.setTimeout(() => void poll(), 2500);
        }
      } catch { /* 任务已移除 */ }
    };
    void poll();
    return () => { alive = false; };
  }, [selectedTask]);

  const spawnTask = async () => {
    const text = taskInput.trim();
    if (!text || taskSpawnBusy) return;
    setTaskSpawnBusy(true);
    setTaskInput('');
    try {
      const snap = await api.subagentSpawn({ message: text, background: true, label: text.slice(0, 24) });
      setSelectedTask(snap.id);
      setSideTab('task');
      const list = await api.subagentList();
      setTaskAgents(list.agents);
    } catch (e) {
      setTaskInput(text);
      window.alert(`任务发起失败: ${(e as Error).message}`);
    } finally {
      setTaskSpawnBusy(false);
    }
  };
  void spawnTask; // 任务面板已移除；保留供后续复用

  const followupTask = async (id: string) => {
    const text = taskFollowup.trim();
    if (!text) return;
    setTaskFollowup('');
    try {
      await api.subagentMessage(id, text);
      const d = await api.subagentGet(id);
      setTaskDetail({ agent: d.agent, output: d.output });
    } catch (e) {
      window.alert(`续聊失败: ${(e as Error).message}`);
    }
  };
  void followupTask; // 任务面板已移除；保留供后续复用

  const refreshTaskList = () => {
    void api.subagentList().then((l) => setTaskAgents(l.agents)).catch(() => {});
  };
  void refreshTaskList; // 任务 tab 已从右侧栏移除；保留函数供后续抽屉面板复用

  /** 工作空间选择：__new__ 走 prompt 新建（成功后刷新列表并选中；取消/失败时受控 select 自动回退原值） */
  const onWorkspaceSelect = (v: string) => {
    if (v !== '__new__') {
      onWorkspaceChange?.(v);
      return;
    }
    const name = window.prompt('工作空间名称');
    if (!name || !name.trim()) return;
    void api.createWorkspace(name.trim())
      .then((r) => {
        onWorkspacesChange?.();
        onWorkspaceChange?.(r.id);
      })
      .catch((e) => window.alert(`新建工作空间失败: ${(e as Error).message}`));
  };

  const send = async (preset?: string) => {
    const attach = attachments;
    const wsName = workspaces.find((w) => w.id === activeWorkspace)?.name ?? '';
    let text = (preset ?? input).trim();
    if (busy) return;
    if (!text && attach.length > 0) text = '请阅读并分析这些附件';
    if (!text) return;
    setInput('');
    setAttachments([]);
    // 附件信息以工作指令形式一并交给模型：模型用 file_read 读取服务器路径分析
    const withAttach =
      attach.length > 0
        ? `${text}\n\n【附件】以下文件已上传到本机服务器（工作区 uploads/ 目录）：\n${attach
            .map((a) => `- ${a.name} → ${a.path}`)
            .join('\n')}\n请先用 file_read 读取附件内容，再结合我的问题分析回答。`
        : text;
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    const sentAt = fmtClock();
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text, time: sentAt, attachments: attach },
      { role: 'assistant', content: '', time: sentAt },
    ]);
    setBusy(true);
    // 新一轮对话：重置文档事件标记与流式内容累积
    sawDocEventRef.current = false;
    contentRef.current = '';
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      await streamChat(withAttach, history, sessionId, model, wsName, (delta, meta) => {
        contentRef.current = meta?.reset ? delta : contentRef.current + delta;
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = {
            ...last,
            content: meta?.reset ? delta : last.content + delta,
            ttftMs: meta?.ttft_ms ?? last.ttftMs,
          };
          return next;
        });
      }, (ev) => {
        // 实时轨迹事件：过程块边跑边渲染（DSH 式）
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, trace: [...(last.trace ?? []), ev] };
          return next;
        });
        // document 事件：文档生成/上传完成 → 自动在右侧预览面板打开
        if (ev.type === 'document' && ev.url) {
          sawDocEventRef.current = true;
          setPreviewUrl(ev.url);
          setPreviewTitle(ev.source && ev.source !== 'final_answer'
            ? `由 ${ev.source} 生成` : '在线文档预览');
          setPanelOpen(true);
          setSideTab('preview');
        }
      }, (meta) => {
        // 兜底：链接只出现在最终回答文本时，从内容里提取 docs.qq.com 链接自动打开
        if (!sawDocEventRef.current) {
          const m = contentRef.current.match(/https:\/\/docs\.qq\.com\/[^\s"'<>()[\]]+/);
          if (m) {
            sawDocEventRef.current = true;
            setPreviewUrl(m[0]);
            setPreviewTitle('在线文档预览');
            setPanelOpen(true);
            setSideTab('preview');
          }
        }
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = {
            ...last,
            durationMs: meta.duration_ms,
            trace: meta.trace ?? last.trace,
            usage: meta.usage ?? last.usage,
            ttftMs: meta.ttft_ms ?? last.ttftMs,
            time: fmtClock(),
          };
          return next;
        });
        // 一轮对话完成 → 通知侧栏刷新会话列表（计数/时间/排序）
        onActivity?.();
      }, { signal: ctrl.signal, planMode });
    } catch (e) {
      const aborted = (e instanceof DOMException && e.name === 'AbortError')
        || ctrl.signal.aborted;
      const em = (e as Error).message || '';
      if (aborted) {
        // 用户主动停止：不报错，把已生成内容保留并标注已停止
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = {
            ...last,
            content: last.content
              ? `${last.content}\n\n_（已停止，以上为已生成部分）_`
              : '_（已停止）_',
            time: fmtClock(),
          };
          return next;
        });
      } else {
        const isServerErr = /^服务端 HTTP|^HTTP /.test(em);
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            ...next[next.length - 1],
            content: isServerErr
              ? `[服务端错误] ${em}`
              : `[连接中断] ${em}\n服务可能仍在运行（长思考期间连接易被掐断）——请重发这条消息，或刷新页面后重试。`,
            time: fmtClock(),
          };
          return next;
        });
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  };

  // 停止当前生成（对标 input.sendButton.stop：只断前端流，不假装后端已取消）
  const stop = () => { abortRef.current?.abort(); };

  React.useEffect(() => {
    window.localStorage.setItem('eco-plan-mode', planMode ? '1' : '0');
  }, [planMode]);

  // 输入法（IME）合成态：中文/日文输入时按 Enter 是「选词上屏」，绝不能当发送。
  // 对标 DSH InputBar 的三重判定——单靠 isComposing 在部分引擎
  // （旧版 Safari/Firefox、部分国产输入法）为 false，必须叠加 keyCode 229 兜底。
  const composingRef = React.useRef(false);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Shift+Enter 无条件换行——放在 IME 判定之前，
    // 这样「合成结束的那一次 Shift+Enter」仍能正常断行。
    if (e.key === 'Enter' && e.shiftKey) return;
    const ne = e.nativeEvent as unknown as { isComposing?: boolean; keyCode?: number };
    const composing =
      composingRef.current || ne.isComposing === true || ne.keyCode === 229;
    if (e.key === 'Enter' && !composing) {
      e.preventDefault();
      void send();
    }
  };

  const copyMsg = (m: Msg) => {
    void navigator.clipboard.writeText(m.content);
  };

  /** 消息日志区点击委托：代码块横幅「复制」按钮 + 选项提问按钮（DSH user-questions 行为） */
  const onLogClick = (e: React.MouseEvent) => {
    // 云文档链接（腾讯文档 / 飞书）：改为在抽屉内打开，而非跳走当前页
    const link = (e.target as HTMLElement).closest('a[href]') as HTMLAnchorElement | null;
    if (link) {
      const href = link.getAttribute('href') ?? '';
      if (isTencentDocsUrl(href) || isFeishuUrl(href)) {
        e.preventDefault();
        openDoc({ kind: 'url', url: href }, link.textContent?.trim() || href);
        return;
      }
    }
    const chip = (e.target as HTMLElement).closest('.md-filechip') as HTMLAnchorElement | null;
    if (chip) {
      e.preventDefault();
      const p = chip.getAttribute('data-path') ?? '';
      void navigator.clipboard.writeText(p).then(() => {
        chip.textContent = `✓ 已复制 ${p}`;
        setTimeout(() => { chip.textContent = `📄 ${p}`; }, 1400);
      });
      return;
    }
    const opt = (e.target as HTMLElement).closest('.md-option') as HTMLButtonElement | null;
    if (opt) {
      const v = opt.getAttribute('data-opt');
      if (v) setInput(v);
      return;
    }
    const btn = (e.target as HTMLElement).closest('.md-code-copy') as HTMLButtonElement | null;
    if (!btn) return;
    const code = btn.closest('.md-codeblock')?.querySelector('code')?.textContent ?? '';
    void navigator.clipboard
      .writeText(code)
      .then(() => {
        btn.textContent = '已复制';
        window.setTimeout(() => { btn.textContent = '复制'; }, 1200);
      })
      .catch(() => {});
  };

  const rateMsg = (index: number, rating: 'up' | 'down') => {
    setMessages((prev) => prev.map((m, i) => (i === index ? { ...m, rating: m.rating === rating ? null : rating } : m)));
  };

  /** 回滚到某条用户消息之前：调 checkpoint rewind API（第 n 个检查点 = 第 n 轮用户输入前快照），
   *  成功后本地消息截断到该用户消息之前（检查点时间线与工作区文件由服务端还原） */
  const rewindTo = async (index: number) => {
    const ordinal = messages.slice(0, index + 1).filter((m) => m.role === 'user').length;
    if (ordinal <= 0) return;
    if (!window.confirm(`回滚到第 ${ordinal} 条提问之前？该消息及之后的对话将被移除（工作区文件按快照还原）。`)) return;
    try {
      const r = await api.rewindCheckpoint(sessionId, ordinal);
      setMessages((prev) => prev.slice(0, index));
      onActivity?.();
      if (r.note) window.alert(`已回滚到检查点 #${r.checkpoint.id}。${r.note}`);
    } catch (e) {
      window.alert(`回滚失败: ${(e as Error).message}（该会话可能暂无检查点——检查点由 CLI/服务端会话循环每轮提问前自动创建）`);
    }
  };

  const branchFrom = (index: number) => {
    // 分支新对话：把该消息及之前的上下文复制为新会话
    const prefix = messages.slice(0, index + 1).filter((m) => m.content);
    setMessages([
      {
        role: 'assistant',
        content: `已从对话中分支（保留前 ${prefix.length} 条上下文）。继续提问即可。`,
        time: fmtClock(),
        branchId: `branch-${Date.now()}`,
      },
    ]);
    setBranchTag(`分支 · ${prefix.length} 条上下文`);
  };

  return (
    <div className="chat-wrap">
      <div className="chat-box">
        <div className="main-tabs">
          <button className={`main-tab${mainTab === 'chat' ? ' active' : ''}`} onClick={() => setMainTab('chat')}>对话</button>
          <button className={`main-tab${mainTab === 'trace' ? ' active' : ''}`} onClick={() => setMainTab('trace')}>轨迹</button>
          {/* 审计链：原右侧栏 slot 面板，按需求并入主 tab 栏，排在轨迹之后 */}
          {slotPanels.map((p) => (
            <button
              key={p.id}
              className={`main-tab${mainTab === 'audit' && activeSlot === p.id ? ' active' : ''}`}
              title={p.description}
              onClick={() => {
                setMainTab('audit');
                setActiveSlot(p.id);
                setSlotData(null);
                void api.slotData(p.id).then((d) => setSlotData(d)).catch(() => setSlotData({ error: '加载失败' }));
              }}
            >
              {p.title}
            </button>
          ))}
          {/* 右上角功能区（WorkBuddy workbuddy-topbar 对标）：对话内搜索 + 提问跳转 */}
          <div className="topbar-actions">
            <ConnectorTags />
            <button
              className={`tb-btn product-toggle${productOpen ? ' active' : ''}`}
              title={productOpen ? '收起右栏产物面板' : '展开右栏产物面板'}
              aria-label={productOpen ? '收起右栏' : '展开右栏'}
              onClick={toggleProductPanel}
            >
              <Icon name="folder" size={15} />
              <span className="product-toggle-label">产物{allMdArtifacts.length > 0 ? ` ${allMdArtifacts.length}` : ''}</span>
            </button>
            <UserPromptListButton
              messages={messages}
              onJump={(i) => {
                setMainTab('chat');
                setTimeout(() => {
                  const el = logRef.current?.querySelectorAll('.msg')[i] as HTMLElement | undefined;
                  el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
                  el?.classList.add('msg-flash');
                  setTimeout(() => el?.classList.remove('msg-flash'), 1200);
                }, 60);
              }}
            />
            <ChatSearchButton containerRef={logRef} />
          </div>
        </div>
        {branchTag && <div className="branch-tag">{branchTag}</div>}
        {mainTab === 'chat' ? (
        <div className={`chat-log${fresh ? ' hero-mode' : ''}`} ref={logRef} onClick={onLogClick}>
          {fresh ? (
            /* 生态环境空态主页：logo + Agent 字标 + 守护绿水青山 + 场景标签 + 快捷入口 */
            <div className="hero">
              <div className="hero-head">
                <img className="hero-logo" src="/eco-logo.svg" alt="eco Agent" />
                <span className="hero-title">Agent</span>
              </div>
              <div className="hero-sub">守护绿水青山</div>
              <div className="scene-tabs">
                {ECO_SCENES.map((s) => (
                  <button
                    key={s.id}
                    className={`scene-tab${activeScene === s.id ? ' active' : ''}`}
                    onClick={() => setActiveScene(s.id)}
                  >
                    <span><Icon name={s.icon} size={15} /></span>
                    {s.label}
                  </button>
                ))}
              </div>
              <div className="quick-actions">
                {QUICK_ACTIONS.map((a, i) => (
                  <button
                    key={i}
                    className="quick-btn"
                    onClick={() => { setInput(a.prompt); inputRef.current?.focus(); }}
                  >
                    <span><Icon name={a.icon} size={15} /></span>
                    {a.label}
                  </button>
                ))}
                <button className="quick-btn quick-more" title="更多工具">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /><circle cx="5" cy="12" r="1" />
                  </svg>
                </button>
              </div>
            </div>
          ) : (
            messages.map((m, i) => (
            /* 压缩产物不渲染成普通消息，而是一条分隔线（WorkBuddy compact-divider 对标） */
            isCompactContent(m.content) ? (
              <CompactDivider key={i} type={inferCompactType(m.content)} summary={m.content} />
            ) : (
            <div key={i} className={`msg ${m.role}`}>
              <div className="msg-meta">
                <span className="msg-role">{m.role === 'user' ? '你' : 'eco Agent'}</span>
                {m.role === 'user' && m.time && <span className="msg-time">{m.time}</span>}
                {m.role === 'assistant' && m.durationMs !== undefined && (
                  <span className="msg-stat">{fmtStatRow(m)}</span>
                )}
              </div>
              {m.role === 'assistant' && (m.trace?.length ?? 0) > 0 && (
                <ProcessBlock trace={m.trace!} live={busy && i === messages.length - 1} />
              )}
              {m.role === 'assistant' && (m.trace?.length ?? 0) > 0 && renderCards(m.trace!)}
              {m.role === 'assistant' && (m.trace ?? []).some((t) => t.type === 'answer' && t.truncated) && !busy && (
                <button
                  className="tb-btn detail-btn"
                  title="此回答为要点版，点击取完整版（原稿兑现，不重新生成）"
                  onClick={() => void send('详细版')}
                ><Icon name="doc" size={12} /> 详细版</button>
              )}
              <div
                className={`bubble${m.role === 'assistant' && !m.content ? ' streaming' : ''}`}
                dangerouslySetInnerHTML={{
                  __html: m.content
                    ? m.role === 'assistant'
                      ? renderMarkdown(m.content)
                      : escapeHtml(m.content).replace(/\n/g, '<br/>')
                    : (busy ? '<span class="thinking">正在思考<span class="dots">…</span></span>' : ''),
                }}
              />
              {m.role === 'assistant' && (() => {
                const arts = (m.trace ?? []).filter((t) => t.type === 'artifact' && t.name);
                if (arts.length === 0) return null;
                const cards = arts.map((t, ai) => (
                  <ArtifactCard key={`${t.name}-${ai}`} name={t.name!} title={t.title ?? t.name!} size={t.size} path={t.path}
                                docxName={t.docx_name} docxPath={t.docx_path} onOpen={openDoc} />
                ));
                return arts.length > 1 ? (
                  <div className="artifact-group">
                    <div className="artifact-group-head"><Icon name="package" size={12} /> {arts.length} 个产物</div>
                    {cards}
                  </div>
                ) : cards;
              })()}
              {m.role === 'assistant' && (m.trace ?? []).filter((t) => t.type === 'approval' && t.request_id).map((t, ai) => (
                <ApprovalCard key={`${t.request_id}-${ai}`} name={t.name ?? '工具'} requestId={t.request_id!} />
              ))}
              {m.role === 'user' && (m.attachments?.length ?? 0) > 0 && (
                <div className="attach-chips">
                  {m.attachments!.map((a, ai) => (
                    <span key={ai} className="attach-chip" title={a.path}>
                      <Icon name="paperclip" size={13} /> {a.name}
                      {a.size_kb > 0 ? ` · ${a.size_kb}KB` : ''}
                    </span>
                  ))}
                </div>
              )}
              {m.role === 'assistant' && !busy && m.content && (
                <div className="msg-toolbar">
                  <button className="tb-btn" title="复制" onClick={() => copyMsg(m)}><Icon name="copy" size={12} /> 复制</button>
                  <button
                    className={`tb-btn${m.rating === 'up' ? ' active' : ''}`}
                    title="点赞"
                    onClick={() => rateMsg(i, 'up')}
                  ><Icon name="thumbs-up" size={13} /></button>
                  <button
                    className={`tb-btn${m.rating === 'down' ? ' active' : ''}`}
                    title="踩"
                    onClick={() => rateMsg(i, 'down')}
                  ><Icon name="thumbs-down" size={13} /></button>
                  <button
                    className={`tb-btn${selectedTrace === i ? ' active' : ''}`}
                    title="查看执行轨迹"
                    onClick={() => {
                      setSelectedTrace(i);
                      setSideTab('trace');
                      setMainTab('trace');
                      setTimeout(() => {
                        document.getElementById(`traj-msg-${i}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                      }, 50);
                    }}
                  ><Icon name="gear" size={12} /> 轨迹</button>
                  <button className="tb-btn" title="在此处分支新对话" onClick={() => branchFrom(i)}><Icon name="branch" size={12} /> 分支</button>
                </div>
              )}
              {m.role === 'user' && m.content && (
                <div className="msg-toolbar">
                  <button className="tb-btn" title="复制" onClick={() => copyMsg(m)}><Icon name="copy" size={12} /> 复制</button>
                  {!busy && (
                    <button
                      className="tb-btn"
                      title="回滚到此处：恢复该提问前的检查点（工作区文件按快照还原），移除其后对话"
                      onClick={() => void rewindTo(i)}
                    ><Icon name="refresh" size={12} /> 回滚到此处</button>
                  )}
                </div>
              )}
            </div>
            )))
          )}
        </div>
        ) : mainTab === 'trace' ? (
        <div className="chat-log traj-page">
          {sessionTraceGroups.length === 0 ? (
            <div className="empty traj-page-empty">暂无轨迹——问一个需要查法条/知识库的问题</div>
          ) : (
            <>
              <TrajToolbar
                dur={durOpen} turns={turnsOpen} calls={callsOpen} query={traceQuery}
                onDur={() => setDurOpen((v) => !v)}
                onTurns={() => setTurnsOpen((v) => !v)}
                onCalls={() => setCallsOpen((v) => !v)}
                onQuery={setTraceQuery}
              />
              <TraceTimeline trace={allSessionTrace} />
              {durOpen && (() => {
                const totalMs = sessionTraceGroups.reduce(
                  (s, g) => s + (g.m.durationMs ?? (g.m.trace ?? []).reduce((x, t) => x + (t.cost_ms ?? 0), 0)), 0);
                const totalTurns = sessionTraceGroups.reduce((s, g) => s + groupTraceByRound(g.m.trace ?? []).length, 0);
                const totalCalls = sessionTraceGroups.reduce(
                  (s, g) => s + buildTrajRows(g.m.trace ?? []).filter((r) => r.kind === 'tool').length, 0);
                return (
                  <div className="traj-duration-row">
                    总耗时 <b>{fmtMs(totalMs)}</b>
                    <span> · {totalTurns} 轮 · {totalCalls} 次调用</span>
                  </div>
                );
              })()}
              {sessionTraceGroups.map((g) => (
                <section key={g.i} id={`traj-msg-${g.i}`} className="traj-msg-group">
                  <div className="traj-msg-head">第 {g.i + 1} 条</div>
                  <div className="traj-rows">
                    <TrajEventList
                      rows={buildTrajRows(g.m.trace ?? [])}
                      showTurns={turnsOpen} showCalls={callsOpen} query={traceQuery} showCost={durOpen}
                    />
                  </div>
                </section>
              ))}
            </>
          )}
        </div>
        ) : (
        /* 审计链页（govmcp SM3）：由主 tab 栏「审计链」进入 */
        <div className="chat-log audit-page">
          {slotData === null ? (
            <div className="empty" style={{ padding: 16 }}>加载中…</div>
          ) : (slotData as { chain?: Record<string, unknown> })?.chain ? (
            <div className="audit-card">
              {/* 区分两种性质：内容篡改 = 硬失败；链接断裂 = 并发写入所致，
                  记录本身未被改动。混为一谈会让人误以为审计证据失效。 */}
              <div className="row">
                <span className="title">链完整性</span>
                {(() => {
                  const c = (slotData as any).chain;
                  const tampered = c.tampered_line !== undefined;
                  const nb = (c.breaks?.length ?? 0) as number;
                  if (tampered) return <span className="badge red">❌ 内容被篡改（第 {c.tampered_line} 行）</span>;
                  if (nb > 0) return <span className="badge amber">⚠ {nb} 处链接断裂 · 内容未篡改</span>;
                  return <span className="badge olive">✅ 完整</span>;
                })()}
              </div>
              <div className="row">
                <span className="title">链条目</span>
                <span className="mono">{(slotData as any).chain.entries ?? 0}</span>
              </div>
              {((slotData as any).chain.breaks?.length ?? 0) > 0 && (
                <div className="audit-breaks">
                  <div className="muted">
                    断点由并发写入造成（多条记录读到同一链尾）；各段内容均通过 SM3 重算，
                    未做任何哈希重写。
                  </div>
                  {((slotData as any).chain.breaks as any[]).map((b, i) => (
                    <div key={i} className="row">
                      <span className="title">断点 · 第 {b.line} 行</span>
                      <span className="mono audit-hash">{b.actual}… ≠ {b.expect}…</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="row">
                <span className="title">尾哈希</span>
                <span className="mono audit-hash">{String((slotData as any).chain.last_hash ?? '').slice(0, 16)}…</span>
              </div>
              {(slotData as any).stats?.by_operation && (
                <div className="audit-ops">
                  {Object.entries((slotData as any).stats.by_operation).map(([op, n]) => (
                    <div key={op} className="row">
                      <span className="title">{op}</span>
                      <span className="mono">{String(n)}</span>
                    </div>
                  ))}
                </div>
              )}
              {(slotData as any).stats?.size_bytes !== undefined && (
                <div className="muted">
                  体积 {Math.round((slotData as any).stats.size_bytes / 1024)} KB
                </div>
              )}
            </div>
          ) : (
            <pre className="artifact-code" style={{ whiteSpace: 'pre-wrap' }}>
              {JSON.stringify(slotData, null, 2)}
            </pre>
          )}
        </div>
        )}
        {attachments.length > 0 && (
          <div className="attach-row">
            {attachments.map((a, ai) => (
              <span key={ai} className="attach-chip" title={a.path}>
                <Icon name="paperclip" size={13} /> {a.name}
                <button
                  className="attach-x"
                  title="移除附件"
                  onClick={() => setAttachments((prev) => prev.filter((_, i) => i !== ai))}
                >✕</button>
              </span>
            ))}
          </div>
        )}
        <div className="chat-input-row">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            onCompositionStart={() => { composingRef.current = true; }}
            onCompositionEnd={() => { composingRef.current = false; }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const t = e.dataTransfer.getData('text/plain');
              if (t) setInput((prev) => (prev ? `${prev} @${t}` : `@${t}`));
            }}
            placeholder="今天监测什么？输入问题直接提问，或点上方快捷入口填入模板"
            rows={2}
          />
          {input.length > 0 && (
            <div className={`input-charcount${input.length > 8000 ? ' over' : ''}`}>
              {input.length.toLocaleString('en-US')}
              {input.length > 8000 && ' · 已超建议长度'}
            </div>
          )}
          <div className="input-footer">
            <div className="input-tools">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                hidden
                onChange={(e) => {
                  if (e.target.files) void uploadFiles(e.target.files);
                  e.target.value = '';
                }}
              />
              <button
                className="input-tool-btn"
                title="上传文件——保存到工作区 uploads/，模型会用 file_read 读取分析"
                onClick={() => fileInputRef.current?.click()}
              ><Icon name="paperclip" size={17} /></button>
              <button
                className={`input-tool-btn${voice === 'recording' ? ' recording' : ''}`}
                title={voice === 'recording' ? '停止录音并转写' : '语音输入——录音后经飞书妙记转写成文字'}
                onClick={() => void toggleVoice()}
              >
                {voice === 'recording' ? <Icon name="stop" size={16} /> : <Icon name="mic" size={17} />}
              </button>
              <button
                className={`input-tool-btn${showTerminal ? ' active' : ''}`}
                title="内置终端（xterm.js + 本机 shell）"
                onClick={() => setShowTerminal((v) => !v)}
              ><Icon name="terminal" size={17} /></button>
            </div>
            <div className="input-modes">
              <button
                type="button"
                className={`mode-chip${planMode ? ' active' : ''}`}
                title="计划/只读模式：本轮只授予只读检索工具（不写文件、不执行命令、不触发三角色起草）。适合先让它调研、给方案"
                aria-pressed={planMode}
                onClick={() => setPlanMode((v) => !v)}
              ><Icon name="branch" size={13} /> 计划模式</button>
              <label className="meta-select" title="选择工作空间——决定可用工具集、记忆上下文、权限等级">
                <span className="meta-icon"><Icon name="folder" size={14} /></span>
                <select
                  value={activeWorkspace}
                  onChange={(e) => onWorkspaceSelect(e.target.value)}
                >
                  {workspaces.length === 0 && <option value="" disabled>无工作空间</option>}
                  {workspaces.map((w) => (
                    <option key={w.id} value={w.id}>{w.name}</option>
                  ))}
                  <option value="__new__">+ 新建工作空间…</option>
                </select>
              </label>
              <span
                className="meta-select"
                title={permGate === null ? '权限闸门状态加载中…' : permGate ? '权限闸门已启用：L1 只读检索，写操作/外部操作需审批（L1–L4 权限闸门）' : '权限闸门未启用：工具调用不经过审批'}
              >
                <span className="meta-icon"><Icon name="lock" size={14} /></span>
                {permGate === null ? '权限 …' : permGate ? '权限闸门 · 已启用' : '权限闸门 · 未启用'}
              </span>
              <select
                className="model-select"
                title="选择模型（DSH ui-model-selection）"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              >
                <option value="">默认（deepseek-v4-pro）</option>
                <option value="deepseek-chat">deepseek-chat</option>
                <option value="deepseek-v4-pro">deepseek-v4-pro（含Think流·推荐）</option>
                <option value="deepseek-reasoner">deepseek-reasoner（含Think流）</option>
                <option value="deepseek-v4-flash">deepseek-v4-flash</option>
                <option value="doubao-plan">doubao-plan（豆包 Agent Plan·火山方舟）</option>
                <option value="qwen-max">qwen-max</option>
                <option value="claude-sonnet-4-20260514">claude-sonnet-4</option>
              </select>
              {(() => {
                const tok = messages.reduce((s, m) => s + (m.usage?.total_tokens ?? 0), 0);
                const pct = Math.min(100, Math.round((tok / 65536) * 100));
                return (
                  <span className="ctx-indicator" title="会话累计 token / 64K 上下文窗口（DSH 上下文计量）">
                    {tok.toLocaleString('en-US')}/64K · {pct}%
                  </span>
                );
              })()}
            </div>
            {busy ? (
              <button
                className="btn btn-stop"
                onClick={stop}
                title="停止生成（断开当前流式输出；已生成部分会保留）"
              ><Icon name="stop" size={14} /> 停止</button>
            ) : (
              <button
                className="btn"
                onClick={() => void send()}
                disabled={!input.trim() && attachments.length === 0}
              >发送</button>
            )}
          </div>
        </div>
        {voice === 'recording' && (
          <div className="voice-status"><Icon name="record" size={12} className="voice-rec" /> 录音中 {voiceSec}s——再点语音按钮停止并转写</div>
        )}
        {voice === 'transcribing' && (
          <div className="voice-status"><Icon name="clock" size={13} /> 转写中——飞书妙记正在生成逐字稿（约 20–60 秒）…</div>
        )}
        {voiceError && <div className="voice-status error">{voiceError}</div>}
        {showTerminal && <TerminalPanel onClose={() => setShowTerminal(false)} />}
      </div>

      {/* 产物抽屉：absolute 贴在 .chat-wrap 内，宽度 px 过渡 + 全屏两态 */}
      <DocDrawer source={docSource} title={docTitle} onClose={() => setDocSource(null)} />

      {/* 常驻右栏产物面板：flex 子项，占满 chat-wrap 高度 */}
      <ProductPanel
        products={allMdArtifacts}
        sources={sessionSources}
        open={productOpen}
        onClose={() => toggleProductPanel()}
      />
    </div>
  );
}
