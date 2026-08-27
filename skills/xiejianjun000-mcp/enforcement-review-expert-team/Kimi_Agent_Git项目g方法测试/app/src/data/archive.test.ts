/**
 * 档案数据 + 跨模块一致性测试（src/data/archive.ts × src/data/review.ts）
 *
 * 档案模块是评查流水线的终点（评查 → 生成报告 → 归档）。
 * 同一案件在 review.queue（评查队列）与 archive.archives（档案库）
 * 之间以案号互相引用，任何一边改坏都会让「归档」链路断掉。
 */
import { describe, it, expect } from 'vitest';
import { archives, CONCL_CLS, docTree, type Conclusion } from './archive';
import { queue } from './review';

const VALID_CONCLUSIONS: Conclusion[] = ['合格', '整改', '否决', '待评'];

describe('archives 档案记录不变量', () => {
  it('档案 id 全局唯一', () => {
    const ids = archives.map((a) => a.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('案号 no 全局唯一', () => {
    const nos = archives.map((a) => a.no);
    expect(new Set(nos).size).toBe(nos.length);
  });

  it('结论只取 合格/整改/否决/待评 四种合法值', () => {
    for (const a of archives) {
      expect(VALID_CONCLUSIONS).toContain(a.conclusion);
    }
  });

  it('借阅中必须有借阅人；在库不得残留借阅人', () => {
    for (const a of archives) {
      if (a.borrow === '借阅中') {
        expect(a.borrower, `${a.no} 借阅中缺借阅人`).toBeTruthy();
      } else {
        expect(a.borrower, `${a.no} 在库不应有借阅人`).toBeUndefined();
      }
    }
  });

  it('卷内文书份数为正整数，归档日期为 YYYY-MM-DD', () => {
    for (const a of archives) {
      expect(Number.isInteger(a.docs)).toBe(true);
      expect(a.docs).toBeGreaterThan(0);
      expect(a.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });

  it('CONCL_CLS 覆盖全部四种结论', () => {
    for (const c of VALID_CONCLUSIONS) {
      expect(CONCL_CLS[c]).toBeTruthy();
    }
  });
});

describe('docTree 卷宗目录模板', () => {
  it('分类按 01-07 编号顺序排列', () => {
    const prefixes = docTree.map((c) => c.cat.slice(0, 2));
    expect(prefixes).toEqual(['01', '02', '03', '04', '05', '06', '07']);
  });

  it('分类标题标注的数量与 count 字段一致', () => {
    for (const c of docTree) {
      const m = c.cat.match(/（(\d+)）/);
      expect(m, `分类「${c.cat}」标题应含数量标注`).not.toBeNull();
      expect(Number(m![1])).toBe(c.count);
    }
  });

  it('缺失文书(missing)不得带页码；在卷文书页码为正数', () => {
    for (const c of docTree) {
      for (const d of c.docs) {
        if (d.missing) {
          expect(d.pages, `「${d.name}」缺失不应有页码`).toBeUndefined();
        } else {
          expect(d.pages, `「${d.name}」在卷应有页码`).toBeGreaterThan(0);
        }
      }
    }
  });

  it('每个分类至少含一份文书（空分类会让查阅器分页崩溃）', () => {
    for (const c of docTree) {
      expect(c.docs.length).toBeGreaterThan(0);
    }
  });
});

describe('跨模块一致性：评查队列 × 档案库', () => {
  it('评查队列中的案号都能在档案库找到对应卷宗', () => {
    const archiveNos = new Set(archives.map((a) => a.no));
    for (const q of queue) {
      expect(archiveNos.has(q.no), `评查队列案号 ${q.no} 在档案库无对应卷宗`).toBe(true);
    }
  });

  it('评查队列中被否决的案卷，档案侧结论不得是「合格」', () => {
    for (const q of queue.filter((c) => c.denied)) {
      const a = archives.find((x) => x.no === q.no);
      expect(a, `案号 ${q.no} 应存在于档案库`).toBeDefined();
      expect(a!.conclusion).not.toBe('合格');
    }
  });

  it('评查「已完成」的案卷在档案侧不得仍为「待评」', () => {
    for (const q of queue.filter((c) => c.status === '已完成')) {
      const a = archives.find((x) => x.no === q.no);
      expect(a).toBeDefined();
      expect(a!.conclusion, `案号 ${q.no} 评查已完成但档案仍待评`).not.toBe('待评');
    }
  });
});
