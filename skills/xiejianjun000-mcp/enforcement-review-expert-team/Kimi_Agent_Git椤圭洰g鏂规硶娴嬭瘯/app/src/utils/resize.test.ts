import { describe, it, expect } from 'vitest';
import { clampPanelWidth, computeResize, PANEL_MIN, PANEL_MAX } from './resize';

describe('clampPanelWidth', () => {
  it('返回正常值（在范围内）', () => {
    expect(clampPanelWidth(260)).toBe(260);
    expect(clampPanelWidth(320)).toBe(320);
    expect(clampPanelWidth(560)).toBe(560);
  });

  it('小于下限 → 返回 PANEL_MIN', () => {
    expect(clampPanelWidth(100)).toBe(PANEL_MIN);
    expect(clampPanelWidth(0)).toBe(PANEL_MIN);
    expect(clampPanelWidth(-50)).toBe(PANEL_MIN);
    expect(clampPanelWidth(PANEL_MIN - 1)).toBe(PANEL_MIN);
  });

  it('大于上限 → 返回 PANEL_MAX', () => {
    expect(clampPanelWidth(600)).toBe(PANEL_MAX);
    expect(clampPanelWidth(999)).toBe(PANEL_MAX);
    expect(clampPanelWidth(PANEL_MAX + 1)).toBe(PANEL_MAX);
  });

  it('边界值精确命中', () => {
    expect(clampPanelWidth(PANEL_MIN)).toBe(PANEL_MIN);
    expect(clampPanelWidth(PANEL_MAX)).toBe(PANEL_MAX);
  });

  it('自定义 min/max', () => {
    expect(clampPanelWidth(50, 100, 200)).toBe(100);
    expect(clampPanelWidth(150, 100, 200)).toBe(150);
    expect(clampPanelWidth(250, 100, 200)).toBe(200);
  });
});

describe('computeResize', () => {
  const startW = 320;
  const startX = 500;

  it('direction=1：鼠标右移 → 宽度增大（左侧栏手柄）', () => {
    // startX=500, currentX=550, delta=(550-500)*1=50, 320+50=370
    expect(computeResize(startX, 550, startW, 1)).toBe(370);
  });

  it('direction=1：鼠标左移 → 宽度减小', () => {
    expect(computeResize(startX, 450, startW, 1)).toBe(270);
  });

  it('direction=-1：鼠标左移 → 宽度增大（右侧栏手柄）', () => {
    // startX=500, currentX=450, delta=(450-500)*(-1)=50, 320+50=370
    expect(computeResize(startX, 450, startW, -1)).toBe(370);
  });

  it('direction=-1：鼠标右移 → 宽度减小', () => {
    expect(computeResize(startX, 550, startW, -1)).toBe(270);
  });

  it('不超出上限（右侧栏 RP_MAX=560，左侧栏 LN_MAX=360）', () => {
    // 右侧栏方向：鼠标大幅左移 → 尺寸触碰 560
    expect(computeResize(startX, 100, startW, -1, 260, 560)).toBe(560);
    // 左侧栏方向：鼠标大幅右移 → 尺寸触碰 360
    expect(computeResize(startX, 900, startW, 1, 180, 360)).toBe(360);
  });

  it('不跌破下限（右侧栏 RP_MIN=260，左侧栏 LN_MIN=180）', () => {
    // 右侧栏方向：鼠标大幅右移 → 收缩到 260
    expect(computeResize(startX, 900, startW, -1, 260, 560)).toBe(260);
    // 左侧栏方向：鼠标大幅左移 → 收缩到 180
    expect(computeResize(startX, 0, startW, 1, 180, 360)).toBe(180);
  });

  it('自定义 min/max 生效', () => {
    expect(computeResize(100, 200, 200, 1, 150, 400)).toBe(300);
    expect(computeResize(100, 200, 200, 1, 150, 250)).toBe(250); // clamped to max
  });
});
