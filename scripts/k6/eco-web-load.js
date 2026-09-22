// eco Agent Web UI — k6 负载测试
// 目标: http://127.0.0.1:8088 (本地 eco web profile)
// 用法:
//   smoke:  k6 run --env MODE=smoke  scripts/k6/eco-web-load.js
//   load:   k6 run --env MODE=load   scripts/k6/eco-web-load.js
//   stress: k6 run --env MODE=stress scripts/k6/eco-web-load.js
import http from 'k6/http'
import { check, sleep } from 'k6'
import { Trend } from 'k6/metrics'

const TOKEN = __ENV.ECO_TOKEN || 'pEXbg0jWShuvTnMNoQUJulcMfDRVQeUWoS43hICObq4'
const BASE = __ENV.ECO_BASE || 'http://127.0.0.1:8088'

const authTrend = new Trend('eco_auth_handshake', true)
const htmlTrend = new Trend('eco_home_html', true)
const assetTrend = new Trend('eco_static_asset', true)
const unauthTrend = new Trend('eco_unauth_reject', true)

// 当前 build 的静态资源（改 build 后需更新 hash）
const STATIC_ASSETS = [
  '/assets/index-Cb8QZn2p.js',
  '/assets/vendor-CCJJTK99.js',
  '/assets/index-lP1BfJ4l.css',
  '/assets/vendor-BNsW4eBh.css',
  '/favicon.svg',
  '/manifest.webmanifest',
]

const MODES = {
  smoke: { stages: [
    { duration: '10s', target: 10 },
    { duration: '10s', target: 0 },
  ] },
  load: { stages: [
    { duration: '20s', target: 100 },
    { duration: '40s', target: 100 },
    { duration: '20s', target: 0 },
  ] },
  stress: { stages: [
    { duration: '30s', target: 300 },
    { duration: '60s', target: 300 },
    { duration: '30s', target: 0 },
  ] },
}

const mode = __ENV.MODE || 'load'
const cfg = MODES[mode] || MODES.load

export const options = {
  scenarios: {
    ramp: {
      executor: 'ramping-vus',
      startVUs: 1,
      gracefulRampDown: '10s',
      stages: cfg.stages,
    },
  },
  thresholds: {
    // 401 是未认证拒绝路径的预期响应，不计入失败；只监控真实业务请求
    'http_req_failed{kind:auth}': ['rate<0.01'],
    'http_req_failed{kind:home}': ['rate<0.01'],
    'http_req_failed{kind:asset}': ['rate<0.01'],
    http_req_duration: ['p(95)<800'],             // 整体 P95 < 800ms
    eco_auth_handshake: ['p(95)<300'],            // 认证 P95 < 300ms
    eco_home_html: ['p(95)<300'],                 // 首页 HTML P95 < 300ms
    eco_static_asset: ['p(95)<1000'],             // 静态资源 P95 < 1s
    eco_unauth_reject: ['p(95)<200'],             // 未认证拒绝 P95 < 200ms
  },
}

export default function () {
  // 1. 未认证拒绝路径（无 token，最快拒绝层）
  const unauthRes = http.get(BASE + '/', { timeout: '30s', tags: { kind: 'unauth' } })
  unauthTrend.add(unauthRes.timings.duration)
  check(unauthRes, { 'unauth 401': (r) => r.status === 401 })

  // 2. 认证握手（token → cookie，跟随重定向到首页，测完整认证体验）
  const authRes = http.get(BASE + '/?token=' + TOKEN, {
    timeout: '30s',
    redirects: 1,
    tags: { kind: 'auth' },
  })
  authTrend.add(authRes.timings.duration)
  check(authRes, { 'auth 认证后 200': (r) => r.status === 200 })

  // 3. 首页 HTML（带认证 cookie，k6 自动维护 VU 级 cookie jar）
  const homeRes = http.get(BASE + '/', { timeout: '30s', tags: { kind: 'home' } })
  htmlTrend.add(homeRes.timings.duration)
  check(homeRes, { 'home 200': (r) => r.status === 200 })

  // 4. 静态资源（bundle + CSS，最重的负载）
  for (let i = 0; i < STATIC_ASSETS.length; i++) {
    const asset = STATIC_ASSETS[i]
    const res = http.get(BASE + asset, { timeout: '30s', tags: { kind: 'asset' } })
    assetTrend.add(res.timings.duration)
    check(res, { ['asset ' + asset + ' 200']: (r) => r.status === 200 })
  }

  sleep(1)
}
