import { escapeHtml } from './markdown';

/**
 * 敏感信息保护（对标 WorkBuddy 敏感信息标签）：
 * 仅对「凭据/密钥」类高危泄露做默认可切换显隐的脱敏——
 *   • sk- / AKIA / AIza / ya29 / GitHub ghp_ 等 API Key
 *   • Bearer Token
 *   • -----BEGIN ... PRIVATE KEY-----
 *   • api_key / secret / token / password / passwd / pwd 赋值式
 * 不 blanket 脱敏手机号/邮箱/身份证，避免伤害生态环境执法办案场景的可用性。
 * 脱敏默认隐藏（🔒 标签 + 显隐切换），点击后显示原文——与 WorkBuddy 行为一致。
 */

const SENSITIVE_PATTERNS: RegExp[] = [
  /sk-[A-Za-z0-9_-]{16,}/g,
  /(?:AKIA|AIza|ya29|ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9_-]{16,}/g,
  /Bearer\s+[A-Za-z0-9._\-]+/gi,
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/g,
  /(?:api[_-]?key|secret|token|password|passwd|pwd)["'\s:=]+[^\s"'<>{}]{8,}/gi,
];

function maskOne(m: string): string {
  if (m.length <= 8) return '••••';
  return m.slice(0, 3) + '••••' + m.slice(-4);
}

/** 把敏感串包成可切换显隐的 span（全程只转义一次，杜绝 XSS）。 */
export function maskSensitiveInto(raw: string): string {
  if (!raw) return '';
  let out = '';
  let last = 0;
  while (last < raw.length) {
    let best: { start: number; end: number; m: string } | null = null;
    for (const p of SENSITIVE_PATTERNS) {
      p.lastIndex = last;
      const mm = p.exec(raw);
      if (mm && mm.index >= last) {
        if (!best || mm.index < best.start) best = { start: mm.index, end: mm.index + mm[0].length, m: mm[0] };
      }
    }
    if (!best) {
      out += escapeHtml(raw.slice(last));
      break;
    }
    out += escapeHtml(raw.slice(last, best.start));
    const masked = maskOne(best.m);
    out += `<span class="sensitive"><span class="sensitive__mask">${escapeHtml(masked)}</span>` +
      `<span class="sensitive__full">${escapeHtml(best.m)}</span></span>`;
    last = best.end;
  }
  return out;
}

export function hasSensitive(raw: string): boolean {
  if (!raw) return false;
  return SENSITIVE_PATTERNS.some((p) => {
    const re = new RegExp(p.source, p.flags.replace('g', ''));
    return re.test(raw);
  });
}
