/**
 * Review 组件 — 25 项一票否决扫描状态机测试
 *
 * 被测状态机（src/components/Review.tsx）：
 *   idle(扫描前) → scanning(110ms/项 × 25) → done(汇总卡)
 *   切换队列案卷 → 强制回退 idle（scanStep=0, scanning=false）
 *
 * 全程使用 vi.useFakeTimers() 推进扫描定时器，零真实等待。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import Review from './Review';

const SCAN_INTERVAL = 110; // 与组件内 setInterval 周期一致
const TOTAL = 25;

function scanCountText(): string | null {
  return document.querySelector('.rv-scan-count')?.textContent ?? null;
}

function startScan(): void {
  fireEvent.click(screen.getByRole('button', { name: '开始扫描' }));
}

function advance(ms: number): void {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

// 扫满 TOTAL 项需要 TOTAL 个 tick：第 TOTAL 个 tick 推进计数到 TOTAL 并
// 同 tick 置 scanning=false（组件在 next >= TOTAL 时直接收尾，无多余 tick）
function advanceFullScan(): void {
  advance(SCAN_INTERVAL * TOTAL);
}

describe('Review — 扫描状态机', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('初始为 idle：计数 0/25，按钮为「开始扫描」，无汇总卡', () => {
    render(<Review onNavigate={() => {}} />);

    expect(scanCountText()).toBe(`0/${TOTAL} 已扫描`);
    expect(screen.getByRole('button', { name: '开始扫描' })).toBeEnabled();
    expect(document.querySelector('.rv-summary')).toBeNull();
  });

  it('点击开始扫描 → 进入 scanning：按钮变「扫描中…」并禁用', () => {
    render(<Review onNavigate={() => {}} />);

    startScan();

    const btn = screen.getByRole('button', { name: '扫描中…' });
    expect(btn).toBeDisabled();
  });

  it('扫描按 110ms/项推进，计数随之增长', () => {
    render(<Review onNavigate={() => {}} />);

    startScan();
    advance(SCAN_INTERVAL);
    expect(scanCountText()).toBe(`1/${TOTAL} 已扫描`);

    advance(SCAN_INTERVAL * 4);
    expect(scanCountText()).toBe(`5/${TOTAL} 已扫描`);
  });

  it('扫满 25 项后自动停止：状态回退、出现命中汇总卡', () => {
    render(<Review onNavigate={() => {}} />);

    startScan();
    advanceFullScan();

    expect(scanCountText()).toBe(`${TOTAL}/${TOTAL} 已扫描`);
    // 扫描结束后按钮恢复可用并变为「重新扫描」
    expect(screen.getByRole('button', { name: '重新扫描' })).toBeEnabled();
    // 数据中存在第 9 项 hit → 汇总卡应宣告不合格
    expect(document.querySelector('.rv-summary.denied')).not.toBeNull();
    expect(screen.getByText(/命中第 9 项/)).toBeInTheDocument();
  });

  it('扫描推进期间 hit 项获得命中样式（第 9 项 听证期限不足）', () => {
    render(<Review onNavigate={() => {}} />);

    startScan();
    advance(SCAN_INTERVAL * 9); // 扫到第 9 项

    const hitRow = document.querySelector('.rv-item.hit');
    expect(hitRow).not.toBeNull();
    expect(hitRow!.textContent).toContain('听证期限不足');
  });

  it('切换队列案卷 → 扫描进度与状态全部重置', () => {
    render(<Review onNavigate={() => {}} />);

    startScan();
    advance(SCAN_INTERVAL * 5);
    expect(scanCountText()).toBe(`5/${TOTAL} 已扫描`);

    // 点击另一卷（第 72 卷）行
    fireEvent.click(screen.getByText(/金竹山矿业废气案/));

    expect(scanCountText()).toBe(`0/${TOTAL} 已扫描`);
    expect(screen.getByRole('button', { name: '开始扫描' })).toBeEnabled();
  });

  it('重新扫描：完成后再次点击可从头扫描', () => {
    render(<Review onNavigate={() => {}} />);

    startScan();
    advanceFullScan();
    expect(document.querySelector('.rv-summary')).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '重新扫描' }));
    expect(scanCountText()).toBe(`0/${TOTAL} 已扫描`);
    expect(document.querySelector('.rv-summary')).toBeNull();
    expect(screen.getByRole('button', { name: '扫描中…' })).toBeDisabled();
  });

  it('汇总卡「生成评查报告 → 归档」触发 onNavigate("archive")', () => {
    const onNavigate = vi.fn();
    render(<Review onNavigate={onNavigate} />);

    startScan();
    advanceFullScan();

    fireEvent.click(screen.getByRole('button', { name: /生成评查报告/ }));
    expect(onNavigate).toHaveBeenCalledWith('archive');
  });
});

describe('Review — 否决分组折叠', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('默认全部分组展开（5 个分组的条目可见）', () => {
    render(<Review onNavigate={() => {}} />);

    expect(screen.getByText('立案管辖错误')).toBeInTheDocument(); // 程序类
    expect(screen.getByText('救济权利告知缺失')).toBeInTheDocument(); // 其他类
  });

  it('点击分组头折叠该组，再点展开', () => {
    render(<Review onNavigate={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: /程序类/ }));
    expect(screen.queryByText('立案管辖错误')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /程序类/ }));
    expect(screen.getByText('立案管辖错误')).toBeInTheDocument();
  });

  it('折叠一个分组不影响其他分组', () => {
    render(<Review onNavigate={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: /程序类/ }));

    expect(screen.queryByText('立案管辖错误')).toBeNull();
    expect(screen.getByText('主要证据缺失')).toBeInTheDocument(); // 证据类仍展开
  });
});

describe('Review — 评查队列渲染', () => {
  it('队列渲染全部案卷及其状态徽章', () => {
    render(<Review onNavigate={() => {}} />);

    // 默认选中第 74 卷时，案卷名同时出现在队列行与扫描面板的「当前案卷」标注中
    expect(screen.getAllByText(/鑫顺建材堆场案/).length).toBeGreaterThan(0);
    expect(screen.getByText(/瑞龙木艺厂粉尘案/)).toBeInTheDocument();
    expect(screen.getByText(/金竹山矿业废气案/)).toBeInTheDocument();
    expect(screen.getByText(/禾青镇页岩砖厂案/)).toBeInTheDocument();

    expect(screen.getByText('待人工复核')).toBeInTheDocument();
    expect(screen.getByText('AI初评中')).toBeInTheDocument();
  });

  it('AI初评中的案卷显示进度条百分比', () => {
    render(<Review onNavigate={() => {}} />);

    expect(screen.getByText('45%')).toBeInTheDocument();
  });

  it('已完成的被否决案卷显示「否决 · 0 分」', () => {
    render(<Review onNavigate={() => {}} />);

    expect(screen.getByText('否决 · 0 分')).toBeInTheDocument();
    expect(screen.getByText('得分 88')).toBeInTheDocument();
  });

  it('SOP 五阶段全部渲染，当前阶段为综合评估', () => {
    render(<Review onNavigate={() => {}} />);

    for (const name of ['预审分流', '并行分析', '综合评估（一票否决）', '文书生成', '归档推送']) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    const active = document.querySelector('.rv-sop-node.active');
    expect(active?.textContent).toContain('综合评估');
  });
});
