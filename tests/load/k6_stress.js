/**
 * eco 只读接口高压测试（k6）—— 在 smoke 通过后验证更高并发下的稳定性。
 * 100 VU 持续 40s，重点看审计链缓存在高压下是否仍然稳定命中、
 * 以及链条目数会不会因并发读到半截文件而掉 0。
 *
 * 运行：k6 run tests/load/k6_stress.js
 */
import http from 'k6/http';
import { check } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';

const BASE = __ENV.ECO_BASE || 'http://127.0.0.1:8321';
const auditMs = new Trend('eco_audit_ms');
const errRate = new Rate('eco_errors');
const badEntries = new Counter('eco_audit_bad_entries');

export const options = {
  scenarios: {
    stress: {
      executor: 'ramping-vus',
      startVUs: 5,
      stages: [
        { duration: '10s', target: 50 },
        { duration: '15s', target: 100 },
        { duration: '15s', target: 100 },
        { duration: '5s', target: 0 },
      ],
      gracefulRampDown: '10s',
    },
  },
  thresholds: {
    'eco_audit_ms': ['p(95)<3000', 'p(99)<8000'],
    'eco_errors': ['rate<0.01'],
    'http_req_failed': ['rate<0.01'],
    'eco_audit_bad_entries': ['count==0'],   // 链条目数掉 0 = 并发读到脏数据
  },
};

let expected = 0;

export default function () {
  const r = http.get(`${BASE}/api/v1/slots/audit-panel/data`, { timeout: '120s' });
  auditMs.add(r.timings.duration);
  let entries = -1;
  try { entries = r.json('chain.entries') || 0; } catch (e) { entries = -1; }

  // 条目数只会随新写入单调增长，绝不该倒退或归零
  if (entries <= 0) badEntries.add(1);
  if (expected && entries > 0 && entries < expected) badEntries.add(1);
  if (entries > expected) expected = entries;

  errRate.add(!check(r, {
    'audit 200': (x) => x.status === 200,
    'entries>0': () => entries > 0,
  }));
}
