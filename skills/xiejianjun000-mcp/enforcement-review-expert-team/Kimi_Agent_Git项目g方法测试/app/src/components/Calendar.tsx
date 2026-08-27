import { useMemo, useState, type ReactNode } from 'react';
import {
  calTypes, filterTypes, calEvents, weekEvents, aiSuggestion, dueSoon, aiScheduled,
  TODAY, MONTH, type CalType, type CalEvent,
} from '../data/calendar';

type View = 'month' | 'week' | 'agenda';

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];

// 2026-08-01 为周六 → 周一为首列时偏移 5
function buildMonthGrid(): { day: number; inMonth: boolean }[] {
  const cells: { day: number; inMonth: boolean }[] = [];
  const offset = 5;
  for (let i = 0; i < offset; i++) cells.push({ day: 27 + i, inMonth: false }); // 7/27..7/31
  for (let d = 1; d <= 31; d++) cells.push({ day: d, inMonth: true });
  while (cells.length % 7 !== 0) {
    const n = cells.length - 35 + 1;
    cells.push({ day: n, inMonth: false }); // 9/1..
  }
  return cells;
}

export default function Calendar(): ReactNode {
  const [view, setView] = useState<View>('month');
  const [filters, setFilters] = useState<Set<CalType>>(new Set(filterTypes));
  const [monthLabel] = useState(MONTH);

  const toggleFilter = (t: CalType) =>
    setFilters((s) => {
      const n = new Set(s);
      n.has(t) ? n.delete(t) : n.add(t);
      return n;
    });

  const grid = useMemo(buildMonthGrid, []);
  const byDay = useMemo(() => {
    const m = new Map<number, CalEvent[]>();
    for (const e of calEvents) {
      if (e.type !== 'law' && !filters.has(e.type)) continue;
      if (!m.has(e.day)) m.set(e.day, []);
      m.get(e.day)!.push(e);
    }
    return m;
  }, [filters]);

  const eventsForDay = (day: number) => byDay.get(day) ?? [];

  return (
    <div className="cal">
      {/* 顶部工具条 */}
      <div className="cal-bar">
        <div className="cal-nav">
          <button className="cal-arrow">‹</button>
          <span className="cal-month">{monthLabel}</span>
          <button className="cal-arrow">›</button>
          <button className="cal-today">回到今天</button>
        </div>
        <div className="seg">
          {(['month', 'week', 'agenda'] as View[]).map((v) => (
            <button key={v} className={`seg-btn${view === v ? ' on' : ''}`} onClick={() => setView(v)}>
              {v === 'month' ? '月' : v === 'week' ? '周' : '日程'}
            </button>
          ))}
        </div>
        <div className="cal-filters">
          {filterTypes.map((t) => (
            <button
              key={t}
              className={`fchip${filters.has(t) ? ' on' : ''}`}
              style={filters.has(t) ? { background: calTypes[t].color, color: calTypes[t].text, borderColor: calTypes[t].dot } : undefined}
              onClick={() => toggleFilter(t)}
            >
              <span className="fdot" style={{ background: calTypes[t].dot }} />
              {calTypes[t].label}
            </button>
          ))}
        </div>
      </div>

      <div className="cal-body">
        <div className="cal-main">
          {view === 'month' && (
            <div className="month">
              <div className="month-head">
                {WEEKDAYS.map((w) => (
                  <div key={w} className="mh-cell">{w}</div>
                ))}
              </div>
              <div className="month-grid">
                {grid.map((c, i) => {
                  const evs = c.inMonth ? eventsForDay(c.day) : [];
                  const isToday = c.inMonth && c.day === TODAY;
                  return (
                    <div key={i} className={`mcell${c.inMonth ? '' : ' out'}${isToday ? ' today' : ''}`}>
                      <div className="mdate">{c.day}</div>
                      {evs.slice(0, 3).map((e) => (
                        <div
                          key={e.id}
                          className={`ev-chip${e.urgent ? ' urgent' : ''}`}
                          style={{ background: calTypes[e.type].color, color: calTypes[e.type].text }}
                          title={e.title}
                        >
                          {e.title}
                        </div>
                      ))}
                      {evs.length > 3 && <div className="ev-more">+{evs.length - 3} 更多</div>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {view === 'week' && (
            <div className="week">
              <div className="ai-block">
                <span className="ai-tag">AI 建议</span>
                {aiSuggestion}
              </div>
              <div className="week-grid">
                {WEEKDAYS.map((w, idx) => {
                  const day = TODAY + idx; // 8/3(一)..8/9(日)
                  const evs = weekEvents.filter((e) => e.day === day);
                  return (
                    <div key={w} className={`wcol${day === TODAY ? ' today' : ''}`}>
                      <div className="wcol-head">{w}<small>{day}</small></div>
                      {evs.map((e) => (
                        <div key={e.id} className="wev" style={{ borderLeftColor: calTypes[e.type].dot }}>
                          <div className="wev-time">{e.start}–{e.end}</div>
                          <div className="wev-title">{e.title}</div>
                          <div className="wev-place">{e.place} · {e.related}</div>
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {view === 'agenda' && (
            <div className="agenda">
              {[...new Set(calEvents.map((e) => e.day))].sort((a, b) => a - b).map((day) => (
                <div key={day} className="ag-group">
                  <div className="ag-date">
                    <span className="ag-bar" />
                    8月{day}日 {WEEKDAYS[(day - 3 + 7) % 7]}
                  </div>
                  {calEvents.filter((e) => e.day === day).map((e) => (
                    <div key={e.id} className="ag-row">
                      <span className={`ag-check${day < TODAY ? ' done' : ''}`}>{day < TODAY ? '✓' : ''}</span>
                      <span className="ag-dot" style={{ background: calTypes[e.type].dot }} />
                      <span className="ag-title">{e.title}</span>
                      {e.time && <span className="ag-time">{e.time}</span>}
                      <span className="ag-type" style={{ color: calTypes[e.type].text }}>{calTypes[e.type].label}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 右侧悬浮小面板 */}
        <aside className="cal-side">
          <div className="side-block">
            <div className="side-title">临期 3 日</div>
            {dueSoon.map((d) => (
              <div key={d.id} className="side-row">
                <div className="side-row-t">{d.title}</div>
                <div className={`side-row-l${d.urgent ? ' urgent' : ''}`}>{d.unit}</div>
                <button className="side-btn">提醒承办人</button>
              </div>
            ))}
          </div>
          <div className="side-block">
            <div className="side-title">AI 已帮您安排</div>
            {aiScheduled.map((s) => (
              <div key={s.id} className="side-row">
                <div className="side-row-t">{s.text}</div>
                {s.canUndo && <button className="side-btn ghost">撤销</button>}
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}
