import { useMemo, useState, type ReactNode } from 'react';
import {
  lawCompare, codeChapters, provinceReports, basisCards, recentList, QA_DEMO,
} from '../data/knowledge';

export default function Knowledge(): ReactNode {
  const [q, setQ] = useState('');
  const [answer, setAnswer] = useState<null | { a: string; cites: { text: string; src: string; status: string }[] }>(null);

  const ask = (): void => {
    const key = Object.keys(QA_DEMO).find((k) => q.includes(k));
    if (key) {
      const d = QA_DEMO[key];
      setAnswer({ a: d.a, cites: d.cites });
    } else {
      setAnswer({
        a: '已为您检索知识库。该问题涉及生态环境法典衔接与裁量基准，建议结合具体违法情形与所在省份衔接报告进一步确认。',
        cites: [
          { text: '生态环境法典 · 污染防治编', src: '生态环境法典', status: '2026-08-15 起施行' },
          { text: '《湖南省裁量权基准（2021 版）》', src: '湖南省生态环境厅', status: '现行有效' },
        ],
      });
    }
  };

  // 法典施行倒计时（2026-08-15）
  const daysLeft = useMemo(() => {
    const target = new Date(2026, 7, 15).getTime();
    const now = Date.now();
    return Math.max(0, Math.ceil((target - now) / 86400000));
  }, []);

  return (
    <div className="kn">
      {/* 问答大卡 */}
      <div className="card kn-qa">
        <input className="kn-qa-input" placeholder="直接问：砖厂超标该罚多少 / 法典施行后旧案子怎么引法条…" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') ask(); }} />
        <button className="btn btn-primary" onClick={ask}>提问</button>
        {answer && (
          <div className="kn-ans">
            <div className="kn-ans-body">{answer.a}</div>
            {answer.cites.map((c, i) => (
              <div className="kn-cite" key={i}>
                <div className="kn-cite-text">{c.text}</div>
                <div className="kn-cite-meta">
                  <span className="kn-cite-src">{c.src}</span>
                  <span className={`kn-cite-status ${c.status.includes('起施行') ? 'soon' : c.status === '已废止' ? 'void' : 'ok'}`}>{c.status}</span>
                  <button className="side-btn ghost">加入办案笔记</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 法典衔接专区 */}
      <div className="card kn-code">
        <div className="kn-code-head">
          <span className="sec-title" style={{ color: 'var(--c-violet)' }}>生态环境法典衔接专区</span>
        </div>
        <div className="kn-countdown">
          <span className="kn-cd-num">{daysLeft}</span>
          <span className="kn-cd-text">天 · 距生态环境法典（2026-08-15）施行</span>
        </div>

        <div className="kn-sub-grid">
          {/* 新旧法对照表 */}
          <div className="kn-sub">
            <div className="kn-sub-title">新旧法对照表</div>
            <CompareTable />
          </div>
          {/* 1242 条速览 */}
          <div className="kn-sub">
            <div className="kn-sub-title">1242 条速览</div>
            <div className="kn-chapters">
              {codeChapters.map((c) => (
                <div className="kn-chapter" key={c.name}>
                  <span className="kn-ch-name">{c.name}</span>
                  <span className="kn-ch-count">{c.count}</span>
                </div>
              ))}
            </div>
          </div>
          {/* 8 省报告 */}
          <div className="kn-sub">
            <div className="kn-sub-title">8 省法典衔接报告</div>
            <div className="kn-provs">
              {provinceReports.map((p) => (
                <details className="kn-prov" key={p.name}>
                  <summary>{p.name}</summary>
                  <div className="kn-prov-sum">{p.summary}</div>
                </details>
              ))}
            </div>
          </div>
        </div>
        <div className="kn-tip">8 月 15 日后作出的处罚决定必须引用法典条款，平台文书模板已提前完成切换校验。</div>
      </div>

      {/* 常用依据网格 */}
      <div className="kn-basis">
        {basisCards.map((b) => (
          <div className="card kn-basis-card" key={b.title}>
            <div className="kn-basis-title">{b.title}</div>
            <div className="kn-basis-desc">{b.desc}</div>
            <button className="side-btn terra">查看 →</button>
          </div>
        ))}
      </div>

      {/* 最近查阅与收藏 */}
      <div className="card kn-recent">
        <div className="sec-head"><span className="sec-title">最近查阅与收藏</span></div>
        <div className="kn-recent-row">
          {recentList.map((r) => (
            <span className="kn-recent-chip" key={r}>{r}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

function CompareTable(): ReactNode {
  const [f, setF] = useState('');
  const rows = lawCompare.filter((r) => f === '' || (r.old + r.neo).includes(f));
  return (
    <div className="kn-compare">
      <input className="kn-compare-search" placeholder="搜索旧法 / 法典编章…" value={f} onChange={(e) => setF(e.target.value)} />
      <div className="kn-compare-list">
        {rows.map((r) => (
          <div className="kn-compare-row" key={r.old}>
            <span className="kn-compare-old">{r.old}</span>
            <span className="kn-compare-arrow">→</span>
            <span className="kn-compare-neo">{r.neo}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
