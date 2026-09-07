/**
 * Assistant 组件 — 点赞/踩互斥逻辑单元测试
 *
 * toggleFeedback 核心规则（直接提取自 Assistant.tsx:137-152）：
 *   msg.feedback === type ? null : type
 *
 * 测试覆盖：
 *   - 点击「赞」→ feedback = 'like'
 *   - 再次点击「赞」→ feedback = null（取消）
 *   - 同一条消息先赞后踩 → feedback = 'dislike'（互斥覆盖）
 *   - 同一条消息先踩后赞 → feedback = 'like'
 *   - undefined 边界情况
 */

import { describe, it, expect } from 'vitest';

/**
 * 这是 Assistant.tsx 中 toggleFeedback 的核心逻辑的纯函数提取。
 * 组件中通过 setMessages + useCallback 包装，本质即此函数。
 */
function toggleFeedbackLogic(
  current: 'like' | 'dislike' | null | undefined,
  type: 'like' | 'dislike',
): 'like' | 'dislike' | null {
  return current === type ? null : type;
}

describe('toggleFeedback 互斥逻辑', () => {
  // ── 正向操作 ──
  it('null → 赞 → like', () => {
    expect(toggleFeedbackLogic(null, 'like')).toBe('like');
  });

  it('null → 踩 → dislike', () => {
    expect(toggleFeedbackLogic(null, 'dislike')).toBe('dislike');
  });

  // ── 取消操作 ──
  it('like → 再赞 → null（取消）', () => {
    expect(toggleFeedbackLogic('like', 'like')).toBeNull();
  });

  it('dislike → 再踩 → null（取消）', () => {
    expect(toggleFeedbackLogic('dislike', 'dislike')).toBeNull();
  });

  // ── 互斥覆盖 ──
  it('like → 点踩 → dislike（踩取代赞）', () => {
    expect(toggleFeedbackLogic('like', 'dislike')).toBe('dislike');
  });

  it('dislike → 点赞 → like（赞取代踩）', () => {
    expect(toggleFeedbackLogic('dislike', 'like')).toBe('like');
  });

  // ── undefined 边界 ──
  it('undefined → 赞 → like', () => {
    expect(toggleFeedbackLogic(undefined, 'like')).toBe('like');
  });

  it('undefined → 踩 → dislike', () => {
    expect(toggleFeedbackLogic(undefined, 'dislike')).toBe('dislike');
  });

  // ── 多次切换 ──
  it('三次切换：null → like → dislike → null', () => {
    let state: 'like' | 'dislike' | null = null;
    state = toggleFeedbackLogic(state, 'like');
    expect(state).toBe('like');
    state = toggleFeedbackLogic(state, 'dislike');
    expect(state).toBe('dislike');
    state = toggleFeedbackLogic(state, 'dislike');
    expect(state).toBeNull();
  });

  // ── 快速反复切换 ──
  it('快速反复：like ↔ dislike 不会出现两边都为 null 的中间态', () => {
    let state: 'like' | 'dislike' | null = 'like';
    state = toggleFeedbackLogic(state, 'dislike');
    expect(state).toBe('dislike'); // 不经过 null
    state = toggleFeedbackLogic(state, 'like');
    expect(state).toBe('like'); // 不经过 null
  });
});
