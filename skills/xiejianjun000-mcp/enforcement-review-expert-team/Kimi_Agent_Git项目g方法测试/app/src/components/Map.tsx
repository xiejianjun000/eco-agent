import { useState, type ReactNode } from 'react';
import {
  mapPoints, stations, pointStatusMeta, mapTasks, overEvents, aiSelectResult, heatSuggestion,
  type MapPoint,
} from '../data/map';

type Layer = 'enterprise' | 'station' | 'river' | 'over' | 'route' | 'key';
const layerMeta: { key: Layer; label: string }[] = [
  { key: 'enterprise', label: '企业点位' },
  { key: 'station', label: '监测站点' },
  { key: 'river', label: '河流断面' },
  { key: 'over', label: '超标告警' },
  { key: 'route', label: '巡查路径' },
  { key: 'key', label: '重点督察区' },
];

export default function Map({ onNavigate }: { onNavigate: (id: string) => void }): ReactNode {
  const [layers, setLayers] = useState<Set<Layer>>(new Set(['enterprise', 'station', 'river', 'over', 'route', 'key']));
  const [selected, setSelected] = useState<MapPoint | null>(null);
  const [tab, setTab] = useState<'task' | 'over' | 'ai'>('task');
  const [selecting, setSelecting] = useState(false);

  const toggle = (k: Layer) =>
    setLayers((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });

  const locate = (id: string) => {
    const p = mapPoints.find((m) => m.id === id);
    if (p) setSelected(p);
  };

  return (
    <div className="map-mod">
      <div className="map-canvas">
        {/* 底图 */}
        <svg className="basemap" viewBox="0 0 100 70" preserveAspectRatio="none">
          <rect x="0" y="0" width="100" height="70" fill="#F4F1EA" />
          {layers.has('river') && (
            <path d="M0,14 C20,18 30,10 46,16 C62,22 72,12 100,20 L100,30 C72,22 62,32 46,26 C30,20 20,28 0,24 Z" fill="#DCE4E8" />
          )}
          <path d="M28,40 C40,44 52,38 70,46 L70,52 C52,44 40,50 28,46 Z" fill="#DCE4E8" />
          {layers.has('key') && <rect x="58" y="50" width="22" height="18" rx="2" fill="#EFE3D6" stroke="#C97C3E" strokeDasharray="1.5 1" />}
          <path d="M0,60 L100,60 M50,0 L50,70" stroke="#EDE8DF" strokeWidth="1.2" />
          <path d="M20,0 L24,70 M78,0 L82,70" stroke="#EDE8DF" strokeWidth="1" />
          {/* 绿地 */}
          <circle cx="14" cy="34" r="9" fill="#E4E8DC" />
          <circle cx="86" cy="62" r="10" fill="#E4E8DC" />
          {/* 建筑 */}
          <rect x="40" y="20" width="6" height="6" fill="#E9E2D6" />
          <rect x="60" y="36" width="5" height="5" fill="#E9E2D6" />
        </svg>

        {/* 监测站点 */}
        {layers.has('station') && stations.map((s) => (
          <span key={s.id} className="station" style={{ left: `${s.x}%`, top: `${s.y}%` }} title={s.name} />
        ))}

        {/* 企业点位 */}
        {layers.has('enterprise') && mapPoints.map((p, i) => (
          <button
            key={p.id}
            className={`map-pt ${p.status}${selected?.id === p.id ? ' sel' : ''}`}
            style={{ left: `${p.x}%`, top: `${p.y}%`, animationDelay: `${i * 60}ms` }}
            onClick={() => setSelected(p)}
            title={p.name}
          >
            {p.status === 'over' && layers.has('over') && <span className="pt-pulse" />}
            {p.label && <span className="pt-label">{p.label}</span>}
          </button>
        ))}

        {/* 巡查路径 */}
        {layers.has('route') && (
          <svg className="route-svg" viewBox="0 0 100 70" preserveAspectRatio="none">
            <polyline points="58,30 32,40 24,72" fill="none" stroke="#7C8B5F" strokeWidth="0.8" strokeDasharray="2 1.5" />
            <text x="44" y="52" fontSize="2.4" fill="#5C6B43">巡查路径</text>
          </svg>
        )}

        {/* 搜索框 */}
        <div className="map-search">
          <input placeholder="搜企业、河流、点位…" />
        </div>

        {/* 图层控制 */}
        <div className="layer-ctrl">
          {layerMeta.map((l) => (
            <button key={l.key} className={`lchip${layers.has(l.key) ? ' on' : ''}`} onClick={() => toggle(l.key)}>{l.label}</button>
          ))}
        </div>

        {/* 点位弹卡 */}
        {selected && (
          <div
            className="pt-pop"
            style={{ left: `${selected.x}%`, top: `${selected.y}%`, transform: selected.y < 35 ? 'translate(-50%, 14px)' : 'translate(-50%, calc(-100% - 14px))' }}
          >
            <div className="pp-head">
              <span className="pp-name">{selected.name}</span>
              <span className={`badge ${pointStatusMeta[selected.status].cls}`}>{pointStatusMeta[selected.status].label}</span>
            </div>
            <div className="pp-rows">
              <div><span>许可证号</span>{selected.permitNo}</div>
              <div><span>行业</span>{selected.industry}</div>
              <div><span>近30天超标</span>{selected.over30} 次</div>
              <div><span>未结案件</span>{selected.openCases} 件</div>
            </div>
            <div className="pp-actions">
              <button className="todo-go" onClick={() => onNavigate('enterprises')}>查看画像 →</button>
              <button className="todo-go" onClick={() => onNavigate('enforcement')}>发起检查</button>
              <button className="todo-go">规划路线</button>
            </div>
          </div>
        )}

        {/* 缩放控件 */}
        <div className="zoom-ctrl">
          <button>+</button><button>−</button><button>◎</button>
        </div>
        <div className="scale-bar">0 ——— 2km</div>
      </div>

      {/* 右侧面板 */}
      <aside className="map-side">
        <div className="ms-tabs">
          {(['task', 'over', 'ai'] as const).map((t) => (
            <button key={t} className={`ms-tab${tab === t ? ' on' : ''}`} onClick={() => setTab(t)}>
              {{ task: '任务落图', over: '超标动态', ai: 'AI 圈选' }[t]}
            </button>
          ))}
        </div>
        <div className="ms-body">
          {tab === 'task' && (
            <div className="task-list">
              {mapTasks.map((t) => (
                <div key={t.id} className="task-item">
                  <div className="ti-time">{t.time}</div>
                  <div className="ti-body">
                    <div className="ti-title">{t.title}</div>
                    <div className="ti-type">{t.type}</div>
                  </div>
                  <button className="ti-loc" onClick={() => locate(t.pointId)}>定位</button>
                </div>
              ))}
              <button className="btn btn-ghost" style={{ width: '100%', marginTop: 8 }}>生成最优巡查路径</button>
            </div>
          )}
          {tab === 'over' && (
            <div className="over-list">
              {overEvents.map((o) => (
                <div key={o.id} className="over-item" onClick={() => locate(o.name.includes('金竹山') ? 'jinzhushan' : 'duoshan')}>
                  <div className="oi-time">{o.time}</div>
                  <div className="oi-body">
                    <b>{o.name}</b> {o.factor} {o.mult} <span className="oi-seq">{o.seq}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          {tab === 'ai' && (
            <div className="ai-select">
              <p className="ai-desc">在地图上圈一片区域，AI 帮您找出需要关注的企业。</p>
              <button className={`btn ${selecting ? 'btn-ghost' : 'btn-primary'}`} onClick={() => setSelecting((s) => !s)}>
                {selecting ? '结束圈选' : '开始圈选'}
              </button>
              {selecting && (
                <div className="ai-result">
                  <div className="ai-result-cap">圈选结果</div>
                  <div className="ai-summary">{aiSelectResult}</div>
                </div>
              )}
            </div>
          )}
        </div>
      </aside>

      {/* 底部热力条 */}
      <div className="heat-strip">
        <div className="heat-title">本月检查覆盖</div>
        <div className="heat-bar">
          {['禾青镇', '中连乡', '铎山', '渣渡', '金竹山', '冷水江', '三尖镇'].map((t, i) => (
            <div key={t} className="heat-cell" style={{ background: `rgba(124,139,95,${(i % 3) * 0.25 + 0.25})` }} title={t}>
              <span>{t}</span>
            </div>
          ))}
        </div>
        <div className="heat-ai">AI：{heatSuggestion}</div>
      </div>
    </div>
  );
}
