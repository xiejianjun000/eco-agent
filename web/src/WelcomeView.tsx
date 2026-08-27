import React from "react";
import { useNavigate } from "react-router-dom";

const QUICK_TAGS = [
  { icon: "🧪", label: "环境科研", desc: "生态学/气候变化/生物多样性" },
  { icon: "🏗️", label: "生态工程", desc: "污染治理/生态修复/清洁生产" },
  { icon: "🌿", label: "绿色办公", desc: "低碳办公/绿色采购/无纸化" },
  { icon: "💨", label: "碳管理", desc: "碳核算/碳交易/碳中和路径" },
  { icon: "📚", label: "环保教育", desc: "科普创作/课程设计/研学活动" },
  { icon: "🌊", label: "自然保护", desc: "保护区/国家公园/生态红线" },
  { icon: "♻️", label: "循环经济", desc: "资源循环/废物利用/生态产品" },
  { icon: "📊", label: "ESG报告", desc: "ESG披露/绿色金融/可持续投资" },
];

const SKILL_CARDS = [
  { icon: "📄", label: "环评分析", color: "#2E7D32" },
  { icon: "📈", label: "碳足迹计算", color: "#0277BD" },
  { icon: "🌱", label: "生态修复", color: "#558B2F" },
  { icon: "🔬", label: "数据分析", color: "#00838F" },
  { icon: "🗺️", label: "遥感解译", color: "#795548" },
  { icon: "⚖️", label: "标准查询", color: "#F9A825" },
  { icon: "🎓", label: "科普创作", color: "#7B1FA2" },
  { icon: "💰", label: "绿色金融", color: "#C62828" },
  { icon: "🐦", label: "生物多样性", color: "#2E7D32" },
  { icon: "🌊", label: "水质评估", color: "#0277BD" },
  { icon: "🌲", label: "森林碳汇", color: "#558B2F" },
  { icon: "🏭", label: "清洁生产", color: "#00838F" },
];

export default function WelcomeView() {
  const nav = useNavigate();
  const [query, setQuery] = React.useState("");

  return (
    <div className="welcome-container">
      {/* 大标题 */}
      <div className="welcome-header">
        <h1 className="welcome-title">
          <span style={{ color: "#2E7D32" }}>eco</span>{" "}
          <span style={{ color: "#1a1a1a" }}>Agent</span>,{" "}
          <span style={{ color: "#0277BD" }}>最懂生态环境的 AI 伙伴</span>
        </h1>
        <p className="welcome-subtitle">—— 从科研到生活，守护每一寸绿色</p>
      </div>

      {/* 快捷标签 */}
      <div className="quick-tags">
        {QUICK_TAGS.map((t) => (
          <button
            key={t.label}
            className="quick-tag"
            onClick={() => nav(`/chat?q=${encodeURIComponent(t.label)}`)}
            title={t.desc}
          >
            <span className="qt-icon">{t.icon}</span>
            <span className="qt-label">{t.label}</span>
          </button>
        ))}
      </div>

      {/* 技能卡片 */}
      <div className="skill-cards-section">
        <p className="sc-title">生态技能</p>
        <div className="skill-cards-scroll">
          {SKILL_CARDS.map((s) => (
            <button
              key={s.label}
              className="skill-card"
              onClick={() => nav(`/chat?q=${encodeURIComponent(s.label)}`)}
            >
              <span className="sc-icon" style={{ color: s.color }}>{s.icon}</span>
              <span className="sc-label">{s.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 中央大输入框 */}
      <div className="welcome-input-area">
        <div className="welcome-input-box">
          <textarea
            className="welcome-textarea"
            placeholder="今天想探索什么生态环境话题？ @引用文献 / 调用生态技能与指令"
            rows={3}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (query.trim()) nav(`/chat?q=${encodeURIComponent(query.trim())}`);
              }
            }}
          />
          <div className="welcome-input-toolbar">
            <div className="wit-left">
              <button className="wit-btn" title="附件">+</button>
              <button className="wit-btn" title="语音">🎤</button>
            </div>
            <div className="wit-right">
              <select className="wit-mode" defaultValue="auto">
                <option value="manual">🌍 手动</option>
                <option value="auto">🌍 自动</option>
                <option value="research">🧪 科研</option>
                <option value="engineering">🏗️ 工程</option>
                <option value="education">📚 教育</option>
                <option value="business">💼 商业</option>
              </select>
              <button
                className="wit-send"
                onClick={() => query.trim() && nav(`/chat?q=${encodeURIComponent(query.trim())}`)}
              >
                ➤
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 底部生态数据 */}
      <div className="eco-stats-bar">
        <span>🌡️ 全球均温 +1.2°C</span>
        <span>🌲 森林覆盖 31%</span>
        <span>🐦 物种监测 45,231</span>
        <span>💨 碳排放 36.8 GtCO₂</span>
      </div>
    </div>
  );
}
