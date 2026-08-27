/**
 * matchPlatform 平台地址识别测试（src/data/whitelist.ts）
 *
 * 平台接入三步流（匹配 → 验证码 → 登录接管）的第一步，
 * hermesClient 的 MOCK 与真实链路都以它为兜底。
 * 重点：大小写/空白归一化、关键字命中、未命中兜底 null。
 */
import { describe, it, expect } from 'vitest';
import { matchPlatform, WHITELIST } from './whitelist';

describe('matchPlatform — 命中场景', () => {
  it('中文关键字命中：水环境', () => {
    expect(matchPlatform('https://水环境非现场执法平台.example.cn/login')?.id).toBe('water');
  });

  it('英文关键字不区分大小写：WATER / Air', () => {
    expect(matchPlatform('http://WATER.gov.cn')?.id).toBe('water');
    expect(matchPlatform('http://Air.example.cn')?.id).toBe('air');
  });

  it('拼音关键字命中：xingzheng / paiwu / dian', () => {
    expect(matchPlatform('http://xingzheng.example.cn')?.id).toBe('enforce');
    expect(matchPlatform('http://paiwu.example.cn')?.id).toBe('permit');
    expect(matchPlatform('http://dian.example.cn')?.id).toBe('electricity');
  });

  it('地址首尾空白不影响匹配（trim 归一化）', () => {
    expect(matchPlatform('   水环境平台   ')?.id).toBe('water');
    expect(matchPlatform('\n\thttp://air.gov.cn\t')?.id).toBe('air');
  });

  it('多关键字平台任一关键字均可命中（行政执法系统）', () => {
    expect(matchPlatform('行政执法系统登录页')?.id).toBe('enforce');
    expect(matchPlatform('http://enforce.example.cn')?.id).toBe('enforce');
  });
});

describe('matchPlatform — 未命中与边界', () => {
  it('空字符串返回 null', () => {
    expect(matchPlatform('')).toBeNull();
  });

  it('纯空白字符串返回 null', () => {
    expect(matchPlatform('   ')).toBeNull();
    expect(matchPlatform('\n\t ')).toBeNull();
  });

  it('完全无关地址返回 null（白名单之外的平台不可接入）', () => {
    expect(matchPlatform('https://www.example.com')).toBeNull();
    expect(matchPlatform('随便一段文本')).toBeNull();
  });

  it('返回的平台对象来自白名单本身（引用一致，含字段标签）', () => {
    const p = matchPlatform('大气帮扶');
    expect(p).not.toBeNull();
    expect(WHITELIST).toContain(p);
    expect(p!.fields.username).toBeTruthy();
    expect(p!.fields.password).toBeTruthy();
    expect(p!.fields.captcha).toBeTruthy();
  });
});

describe('WHITELIST 白名单自身契约', () => {
  it('平台 id 全局唯一', () => {
    const ids = WHITELIST.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('每个平台至少一个关键字，且关键字无空白项', () => {
    for (const p of WHITELIST) {
      expect(p.keywords.length).toBeGreaterThan(0);
      for (const k of p.keywords) {
        expect(k.trim().length).toBeGreaterThan(0);
      }
    }
  });

  it('每个平台都能被自己的关键字命中（自洽性）', () => {
    for (const p of WHITELIST) {
      // 用第一个关键字回查，必须命中某个平台（可能因顺序命中排在前面的平台，故只断言非空）
      expect(matchPlatform(p.keywords[0])).not.toBeNull();
    }
  });
});
