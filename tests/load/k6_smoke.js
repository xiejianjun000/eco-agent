/**
 * eco 只读接口压测（k6）。
 *
 * 为什么不压 /api/v1/chat/stream：单轮真实对话要 25~160 秒且直接消耗
 * 豆包订阅额度，几十个 VU 打上去测的是上游模型限流，不是 eco 自身承载力。
 * 对话链路的稳定性由 tests/modules/test_stream_timeout.py 的护栏测试覆盖。
 *
 * 这里压的是 Web UI 每次加载/轮询都会打的只读接口，
 * 其中审计链校验是已知重负载（7000+ 行纯 Python SM3 逐行重算，冷算 ~20s，
 * 靠 mtime+size 指纹缓存兜住），最值得验证并发下是否退化。
 *
 * 运行：k6 run tests/load/k6_smoke.js
 */
import http from 'k6/http';
import { check, group } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const BASE = __ENV.ECO_BASE || 'http://127.0.0.1:8321';

const healthMs = new Trend('eco_health_ms');
const auditMs = new Trend('eco_audit_ms');
const toolsMs = new Trend('eco_tools_ms');
const staticMs = new Trend('eco_static_ms');
const errRate = new Rate('eco_errors');

export const options = {
  scenarios: {
    ramp: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '15s', target: 5 },
        { duration: '30s', target: 20 },
        { duration: '20s', target: 20 },
        { duration: '10s', target: 0 },
      ],
      gracefulRampDown: '10s',
    },
  },
  thresholds: {
    // 只读接口在 20 VU 下应当保持亚秒级；审计链有缓存，放宽到 2s
    'eco_health_ms':  ['p(95)<300'],
    'eco_static_ms':  ['p(95)<800'],
    'eco_tools_ms':   ['p(95)<1500'],
    'eco_audit_ms':   ['p(95)<2000'],
    'eco_errors':     ['rate<0.01'],
    'http_req_failed': ['rate<0.01'],
  },
};

export default function () {
  group('healthz', () => {
    const r = http.get(`${BASE}/healthz`, { tags: { ep: 'health' } });
    healthMs.add(r.timings.duration);
    const ok = check(r, {
      'health 200': (x) => x.status === 200,
      'health ok': (x) => (x.json('status') || '') === 'ok',
    });
    errRate.add(!ok);
  });

  group('static', () => {
    const r = http.get(`${BASE}/`, { tags: { ep: 'static' } });
    staticMs.add(r.timings.duration);
    errRate.add(!check(r, { 'index 200': (x) => x.status === 200 }));
  });

  group('audit-panel', () => {
    const r = http.get(`${BASE}/api/v1/slots/audit-panel/data`, {
      tags: { ep: 'audit' }, timeout: '120s',
    });
    auditMs.add(r.timings.duration);
    const ok = check(r, {
      'audit 200': (x) => x.status === 200,
      // 链条目数必须稳定为正 —— 并发下若缓存失效或读到半截文件会掉 0
      'audit entries>0': (x) => {
        try { return (x.json('chain.entries') || 0) > 0; } catch (e) { return false; }
      },
    });
    errRate.add(!ok);
  });

  group('tools', () => {
    const r = http.get(`${BASE}/api/v1/tools`, { tags: { ep: 'tools' }, timeout: '60s' });
    toolsMs.add(r.timings.duration);
    errRate.add(!check(r, { 'tools 200': (x) => x.status === 200 }));
  });
}
