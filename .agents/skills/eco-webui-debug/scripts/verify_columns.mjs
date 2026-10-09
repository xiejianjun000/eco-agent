#!/usr/bin/env node
// verify_columns.mjs — CDP 验证 eco web UI 三栏是否渲染
// 前置：Chrome 154 以 --headless=new --remote-debugging-port=9223 启动，并已打开 dsh web 页面
// 用法：node verify_columns.mjs
// 依赖：Node 22 全局 WebSocket + fetch（均内置，无需安装）

const CDP = 'http://127.0.0.1:9223'
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

async function listTargets() {
  const res = await fetch(`${CDP}/json`)
  if (!res.ok) throw new Error(`fetch /json failed: ${res.status}`)
  return res.json()
}

function cdpSession(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl) // Node 22 全局浏览器式 WebSocket
    let id = 0
    const pend = new Map()
    const errors = []
    const handlers = {}
    ws.onopen = () => {
      const send = (method, params = {}) =>
        new Promise((res) => {
          const mid = ++id
          pend.set(mid, res)
          ws.send(JSON.stringify({ id: mid, method, params }))
        })
      const on = (evt, fn) => { handlers[evt] = fn }
      resolve({ send, on, errors, ws })
    }
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.id && pend.has(msg.id)) {
        pend.get(msg.id)(msg)
        pend.delete(msg.id)
      } else if (msg.method) {
        if (msg.method === 'Runtime.exceptionThrown' && handlers.exception)
          handlers.exception(msg.params)
        if (msg.method === 'Runtime.consoleAPICalled' && handlers.console)
          handlers.console(msg.params)
        if (msg.method === 'Log.entryAdded' && handlers.log)
          handlers.log(msg.params)
      }
    }
    ws.onerror = (e) => reject(e)
  })
}

;(async () => {
  const targets = await listTargets()
  const page =
    targets.find((t) => /127\.0\.0\.1|localhost/.test(t.url) && t.type === 'page') ||
    targets.find((t) => t.type === 'page')
  if (!page) {
    console.error('未找到 page target，请确认 Chrome 已打开 dsh web 页面')
    process.exit(1)
  }
  console.log('attaching ->', page.url)
  const s = await cdpSession(page.webSocketDebuggerUrl)
  await s.send('Runtime.enable')
  await s.send('Log.enable')
  await s.send('Page.enable')

  s.on('exception', (p) =>
    s.errors.push('EXCEPTION: ' + (p.exceptionDetails?.exception?.description || p.exceptionDetails?.text))
  )
  s.on('console', (p) => {
    if (p.type === 'error')
      s.errors.push('CONSOLE.ERROR: ' + (p.args || []).map((a) => a.value || a.description).join(' '))
  })
  s.on('log', (p) => {
    if (p.level === 'error') s.errors.push('LOG.ERROR: ' + p.text)
  })

  await wait(3500) // 等页面加载 + 三栏运行时加载完成

  const evalRes = await s.send('Runtime.evaluate', {
    expression: `(function(){
      var b = document.body ? document.body.innerText : '';
      var els = Array.from(document.querySelectorAll('*'))
        .filter(function(e){ return /col|side|main|panel|rightbar/i.test(e.className || ''); });
      var cols = els
        .map(function(e){ return { c: (e.className||'').toString().slice(0,24), n: (e.innerText||'').length }; })
        .sort(function(a,b){ return b.n - a.n; })
        .slice(0, 6);
      return {
        len: b.length,
        hasExplore: /探索未至之境|描述你想要构建的内容|DeepSeek-V41/.test(b),
        cols: cols
      };
    })())`,
    returnByValue: true,
  })
  const v = evalRes.result && evalRes.result.value

  console.log('--- eco web UI 验收报告 ---')
  console.log('body 文本长度      :', v && v.len)
  console.log('真实 UI 已渲染     :', v && v.hasExplore)
  console.log('栏状元素(按字符量) :')
  ;(v && v.cols || []).forEach((c) => console.log('   ', c.c, '=>', c.n, 'chars'))
  console.log('控制台/异常错误数 :', s.errors.length)
  s.errors.slice(0, 10).forEach((e) => console.log('   ', e))

  const ok = v && v.hasExplore && s.errors.length === 0
  console.log(ok ? '\n✅ 三栏渲染正常，0 错误' : '\n⚠️ 仍异常，见上')
  s.ws.close()
  process.exit(ok ? 0 : 2)
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
