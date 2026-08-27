/**
 * Archive 组件 — 档案检索 / 借阅弹窗 / 卷宗查阅器测试
 *
 * 覆盖案卷队列的终端交互：
 *   搜索过滤（案号/当事人/案件名）、年份与结论筛选、
 *   借阅登记弹窗开关、查阅器进出与缩放边界。
 */
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import Archive from './Archive';

function renderList() {
  return render(<Archive onNavigate={() => {}} />);
}

/** 当前表格中渲染出的案号列表 */
function visibleCaseNos(): string[] {
  return Array.from(document.querySelectorAll('.ar-no')).map((el) => el.textContent ?? '');
}

describe('Archive — 列表与搜索', () => {
  it('初始渲染全部 5 卷档案', () => {
    renderList();
    expect(visibleCaseNos().length).toBe(5);
  });

  it('按当事人搜索：「金竹山」→ 仅 1 卷', () => {
    renderList();

    fireEvent.change(screen.getByPlaceholderText(/搜案号/), { target: { value: '金竹山' } });

    expect(visibleCaseNos().length).toBe(1);
    expect(screen.getByText(/金竹山矿业废气超标案/)).toBeInTheDocument();
  });

  it('按案号搜索：「2026〕5号」命中禾青镇页岩砖厂案', () => {
    renderList();

    fireEvent.change(screen.getByPlaceholderText(/搜案号/), { target: { value: '2026〕5号' } });

    expect(visibleCaseNos().length).toBe(1);
    expect(screen.getByText(/禾青镇页岩砖厂废气案/)).toBeInTheDocument();
  });

  it('搜索无结果 → 显示空态提示', () => {
    renderList();

    fireEvent.change(screen.getByPlaceholderText(/搜案号/), { target: { value: '不存在的案件xyz' } });

    expect(visibleCaseNos().length).toBe(0);
    expect(screen.getByText(/没有找到对应卷宗/)).toBeInTheDocument();
  });

  it('清空搜索后恢复全部档案', () => {
    renderList();
    const input = screen.getByPlaceholderText(/搜案号/);

    fireEvent.change(input, { target: { value: '金竹山' } });
    expect(visibleCaseNos().length).toBe(1);

    fireEvent.change(input, { target: { value: '' } });
    expect(visibleCaseNos().length).toBe(5);
  });
});

describe('Archive — 筛选器', () => {
  it('年份筛选 2025 → 无匹配（数据均为 2026 年）', () => {
    renderList();
    const [yearSel] = screen.getAllByRole('combobox');

    fireEvent.change(yearSel, { target: { value: '2025' } });

    expect(visibleCaseNos().length).toBe(0);
    expect(screen.getByText(/没有找到对应卷宗/)).toBeInTheDocument();
  });

  it('结论筛选「否决」→ 仅金竹山矿业案', () => {
    renderList();
    const [, conclSel] = screen.getAllByRole('combobox');

    fireEvent.change(conclSel, { target: { value: '否决' } });

    expect(visibleCaseNos().length).toBe(1);
    expect(screen.getByText(/金竹山矿业废气超标案/)).toBeInTheDocument();
  });

  it('结论筛选「待评」→ 2 卷', () => {
    renderList();
    const [, conclSel] = screen.getAllByRole('combobox');

    fireEvent.change(conclSel, { target: { value: '待评' } });

    expect(visibleCaseNos().length).toBe(2);
  });

  it('借阅中统计卡与数据一致（2 卷借阅中）', () => {
    renderList();

    const borrowCard = Array.from(document.querySelectorAll('.ov-card'))
      .find((el) => el.textContent?.includes('借阅中'));
    expect(borrowCard?.querySelector('.ov-num')?.textContent).toBe('2');
  });
});

describe('Archive — 借阅登记弹窗', () => {
  it('点击借阅 → 弹窗出现，含案卷名与三个登记字段', () => {
    renderList();
    const firstRow = document.querySelector('.ar-row')!;

    fireEvent.click(within(firstRow as HTMLElement).getByRole('button', { name: '借阅' }));

    expect(screen.getByText(/借阅登记 ·/)).toBeInTheDocument();
    expect(screen.getByText('借阅人')).toBeInTheDocument();
    expect(screen.getByText('借阅事由')).toBeInTheDocument();
    expect(screen.getByText('借阅期限')).toBeInTheDocument();
  });

  it('取消按钮关闭弹窗', () => {
    renderList();
    const firstRow = document.querySelector('.ar-row')!;
    fireEvent.click(within(firstRow as HTMLElement).getByRole('button', { name: '借阅' }));

    fireEvent.click(screen.getByRole('button', { name: '取消' }));

    expect(screen.queryByText(/借阅登记 ·/)).toBeNull();
  });

  it('确认借阅关闭弹窗并回到列表', () => {
    renderList();
    const firstRow = document.querySelector('.ar-row')!;
    fireEvent.click(within(firstRow as HTMLElement).getByRole('button', { name: '借阅' }));

    fireEvent.click(screen.getByRole('button', { name: '确认借阅' }));

    expect(screen.queryByText(/借阅登记 ·/)).toBeNull();
    expect(visibleCaseNos().length).toBe(5);
  });
});

describe('Archive — 卷宗查阅器', () => {
  function openViewer(): void {
    const firstRow = document.querySelector('.ar-row')!;
    fireEvent.click(within(firstRow as HTMLElement).getByRole('button', { name: '查阅' }));
  }

  it('查阅进入阅读器：显示案卷名、默认阅读模式、缩放 100%', () => {
    renderList();
    openViewer();

    expect(screen.getByRole('button', { name: /返回卷宗列表/ })).toBeInTheDocument();
    expect(screen.getByText('阅读模式')).toBeInTheDocument();
    expect(document.querySelector('.ar-zoom')?.textContent).toBe('100%');
  });

  it('切换批注模式 → 水印变为批注模式', () => {
    renderList();
    openViewer();

    fireEvent.click(screen.getByRole('button', { name: '批注' }));

    expect(screen.getByText('批注模式')).toBeInTheDocument();
  });

  it('缩放有上下限：不低于 60%，不高于 160%', () => {
    renderList();
    openViewer();
    const zoomOut = screen.getByRole('button', { name: '－' });
    const zoomIn = screen.getByRole('button', { name: '＋' });

    for (let i = 0; i < 6; i++) fireEvent.click(zoomOut); // 100 → 60 后触底
    expect(document.querySelector('.ar-zoom')?.textContent).toBe('60%');

    for (let i = 0; i < 12; i++) fireEvent.click(zoomIn); // 60 → 160 后触顶
    expect(document.querySelector('.ar-zoom')?.textContent).toBe('160%');
  });

  it('切换目录分类 → 页码随该分类文书数变化', () => {
    renderList();
    openViewer();

    fireEvent.click(screen.getByRole('button', { name: /02 调查类/ }));

    expect(document.querySelector('.ar-page')?.textContent).toBe('第 1 / 5 页');
  });

  it('返回按钮回到档案列表', () => {
    renderList();
    openViewer();

    fireEvent.click(screen.getByRole('button', { name: /返回卷宗列表/ }));

    expect(visibleCaseNos().length).toBe(5);
  });
});
