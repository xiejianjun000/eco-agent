/**
 * 案卷评查数据完整性测试（src/data/review.ts）
 *
 * 一票否决 25 项是评查业务的法定底线：编号错位、分组数量漂移、
 * 队列状态/得分不变量被破坏，都会直接传导到 Review 组件的扫描逻辑。
 * 这些测试不依赖渲染，毫秒级完成，守护数据层契约。
 */
import { describe, it, expect } from 'vitest';
import {
  VETO_GROUPS, SOP_STAGES, SOP_CURRENT, queue,
  RESULT_CLS, RESULT_LABEL, type VetoResult,
} from './review';

const ALL_ITEMS = VETO_GROUPS.flatMap((g) => g.items);
const VALID_RESULTS: VetoResult[] = ['pass', 'hit', 'na'];

describe('VETO_GROUPS — 25 项一票否决清单', () => {
  it('总计恰好 25 项', () => {
    expect(ALL_ITEMS.length).toBe(25);
  });

  it('编号为 1..25 连续无重复', () => {
    const nos = ALL_ITEMS.map((i) => i.no).sort((a, b) => a - b);
    expect(nos).toEqual(Array.from({ length: 25 }, (_, i) => i + 1));
  });

  it('每一项 name / keyword / law 均非空', () => {
    for (const it of ALL_ITEMS) {
      expect(it.name.trim().length).toBeGreaterThan(0);
      expect(it.keyword.trim().length).toBeGreaterThan(0);
      expect(it.law.trim().length).toBeGreaterThan(0);
    }
  });

  it('result 只取 pass / hit / na 三种合法值', () => {
    for (const it of ALL_ITEMS) {
      expect(VALID_RESULTS).toContain(it.result);
    }
  });

  it('命中(hit)项必须带卷宗摘录 extract', () => {
    const hits = ALL_ITEMS.filter((i) => i.result === 'hit');
    expect(hits.length).toBeGreaterThan(0);
    for (const h of hits) {
      expect(h.extract).toBeDefined();
      expect(h.extract!.trim().length).toBeGreaterThan(0);
    }
  });

  it('分组标题标注的数量与实际 items 数一致（如「程序类（10）」=10 项）', () => {
    for (const g of VETO_GROUPS) {
      const m = g.cat.match(/（(\d+)）/);
      expect(m, `分组「${g.cat}」标题应含数量标注`).not.toBeNull();
      expect(Number(m![1])).toBe(g.items.length);
    }
  });

  it('分组数量加总等于总项数（无归属遗漏）', () => {
    const sum = VETO_GROUPS.reduce((n, g) => n + g.items.length, 0);
    expect(sum).toBe(25);
  });
});

describe('SOP 五阶段流水线', () => {
  it('恰好 5 个阶段', () => {
    expect(SOP_STAGES.length).toBe(5);
  });

  it('阶段顺序：预审分流 → 并行分析 → 综合评估 → 文书生成 → 归档推送', () => {
    expect(SOP_STAGES.map((s) => s.name)).toEqual([
      '预审分流', '并行分析', '综合评估（一票否决）', '文书生成', '归档推送',
    ]);
  });

  it('每个阶段都指定了责任专家', () => {
    for (const s of SOP_STAGES) {
      expect(s.expert.trim().length).toBeGreaterThan(0);
    }
  });

  it('SOP_CURRENT 指向合法阶段下标', () => {
    expect(SOP_CURRENT).toBeGreaterThanOrEqual(0);
    expect(SOP_CURRENT).toBeLessThan(SOP_STAGES.length);
  });
});

describe('评查队列 queue — 状态机不变量', () => {
  it('卷号 vol 全局唯一', () => {
    const vols = queue.map((q) => q.vol);
    expect(new Set(vols).size).toBe(vols.length);
  });

  it('案号 no 全局唯一', () => {
    const nos = queue.map((q) => q.no);
    expect(new Set(nos).size).toBe(nos.length);
  });

  it('「AI初评中」必须携带 0-100 的进度值', () => {
    for (const q of queue.filter((c) => c.status === 'AI初评中')) {
      expect(q.progress).toBeDefined();
      expect(q.progress!).toBeGreaterThanOrEqual(0);
      expect(q.progress!).toBeLessThanOrEqual(100);
    }
  });

  it('「已完成」必须有得分；被否决案卷得分恒为 0', () => {
    for (const q of queue.filter((c) => c.status === '已完成')) {
      expect(q.score).toBeDefined();
      expect(q.score).not.toBeNull();
      if (q.denied) {
        expect(q.score).toBe(0);
      } else {
        expect(q.score!).toBeGreaterThan(0);
      }
    }
  });

  it('「待评 / AI初评中」不得提前携带得分', () => {
    for (const q of queue.filter((c) => c.status === '待评' || c.status === 'AI初评中')) {
      expect(q.score == null).toBe(true);
    }
  });
});

describe('结果映射表', () => {
  it('RESULT_CLS / RESULT_LABEL 覆盖全部三种结果', () => {
    for (const r of VALID_RESULTS) {
      expect(RESULT_CLS[r]).toBeTruthy();
      expect(RESULT_LABEL[r]).toBeTruthy();
    }
  });

  it('命中映射为红色 red，通过映射为 olive', () => {
    expect(RESULT_CLS.hit).toBe('red');
    expect(RESULT_CLS.pass).toBe('olive');
  });
});
