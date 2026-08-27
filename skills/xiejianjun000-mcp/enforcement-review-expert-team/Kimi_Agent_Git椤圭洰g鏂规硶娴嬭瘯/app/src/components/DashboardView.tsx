import type { ReactNode } from 'react';

const platformHealth = [
  { name: '大气监督帮扶', status: 'ok', lastCheck: '08:50', streak: 9 },
  { name: '水环境管理', status: 'ok', lastCheck: '08:50', streak: 9 },
  { name: '固废管理', status: 'warn', lastCheck: '07:30', streak: 2 },
  { name: '排污许可', status: 'ok', lastCheck: '08:50', streak: 14 },
];

const caseStats = [
  { label: '本月立案', value: 12, delta: '+3', up: true },
  { label: '在办案件', value: 8, delta: '+1', up: true },
  { label: '已结案', value: 45, delta: '+7', up: true },
  { label: '超期风险', value: 2, delta: '-1', up: false },
];

const reviewProgress = { current: 73, total: 100, passed: 68, veto: 5 };

const recentActivity = [
  { time: '08:45', text: '大气监督帮扶平台巡检完成，会话正常', type: 'ok' },
  { time: '08:30', text: '金竹山矿业 CEMS 数据更新，本月第 24 次超标', type: 'warn' },
  { time: '08:15', text: '娄环罚(冷)〔2026〕2 号决定书送达回证已生成', type: 'ok' },
  { time: '07:50', text: 'AI 专家「卷查清」完成第 73 卷初评', type: 'ok' },
  { time: '昨日 17:30', text: '冷水江市 3 家企业排污许可报告待审核', type: 'pending' },
];

export default function DashboardView(): ReactNode {
  return (
    <div className="dashboard">
      <div className="dash-kpi-grid">
        {caseStats.map((s) => (
          <div key={s.label} className="dash-kpi-card">
            <div className="dash-kpi-label">{s.label}</div>
            <div className="dash-kpi-value">{s.value}</div>
            <div className={`dash-kpi-delta ${s.up ? 'up' : 'down'}`}>{s.delta} 较上月</div>
          </div>
        ))}
      </div>

      <div className="dash-grid-2col">
        <div className="card dash-card">
          <div className="sec-head">
            <span className="sec-title">平台健康</span>
            <span className="sec-count">{platformHealth.filter(p => p.status === 'ok').length}/{platformHealth.length} 正常</span>
          </div>
          <div className="dash-platform-list">
            {platformHealth.map((p) => (
              <div key={p.name} className="dash-platform-row">
                <span className={`dash-platform-dot ${p.status}`} />
                <span className="dash-platform-name">{p.name}</span>
                <span className="dash-platform-streak">连续 {p.streak} 天</span>
                <span className="dash-platform-time">{p.lastCheck}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card dash-card">
          <div className="sec-head">
            <span className="sec-title">百卷精评</span>
            <span className="sec-count">{reviewProgress.current}/{reviewProgress.total}</span>
          </div>
          <div className="dash-review-prog">
            <div className="rv-prog-wrap">
              <div className="rv-prog">
                <div className="rv-prog-fill" style={{ width: `${(reviewProgress.current / reviewProgress.total) * 100}%` }} />
              </div>
            </div>
          </div>
          <div className="dash-review-stats">
            <div className="dash-review-stat">
              <span className="dash-review-num olive">{reviewProgress.passed}</span>
              <span className="dash-review-label">通过</span>
            </div>
            <div className="dash-review-stat">
              <span className="dash-review-num red">{reviewProgress.veto}</span>
              <span className="dash-review-label">否决</span>
            </div>
            <div className="dash-review-stat">
              <span className="dash-review-num">{reviewProgress.total - reviewProgress.current}</span>
              <span className="dash-review-label">待评</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card dash-card">
        <div className="sec-head">
          <span className="sec-title">最近动态</span>
        </div>
        <div className="dash-activity-list">
          {recentActivity.map((a, i) => (
            <div key={i} className="dash-activity-row">
              <span className="dash-activity-time">{a.time}</span>
              <span className={`dash-activity-dot ${a.type}`} />
              <span className="dash-activity-text">{a.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
