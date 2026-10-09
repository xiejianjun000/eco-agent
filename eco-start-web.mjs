// eco OS 启动包装：加载 .env（含 ECO_MATRIX_API_KEY）→ 注入环境 → 启动 dsh web。
// 用途：eco-matrix MCP（生态环境知识大脑）固化在 bundle/web-app/cordis.patch.yml，
// headers.X-API-Key 直读 process.env.ECO_MATRIX_API_KEY；缺失时 schema 校验拒绝整行
// （表现为 "entry did not activate"），故必须经由此包装或外部环境提供。
import { spawnSync } from 'node:child_process'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = 'E:/dsh/eco-agent'
const envPath = join(root, '.env')

// 1) 载入 .env（KEY=VALUE 逐行，不覆盖已有环境变量）
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/)
    if (!m) continue
    if (process.env[m[1]] === undefined) process.env[m[1]] = m[2].replace(/^["']|["']$/g, '')
  }
  console.log('[eco-start] .env loaded, keys:', [...readFileSync(envPath, 'utf8').matchAll(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=/gm)].map(m => m[1]).join(', '))
} else {
  console.warn('[eco-start] WARN: .env 不存在，eco-matrix MCP 将无法激活（需 ECO_MATRIX_API_KEY）')
}

// 2) 启动 dsh web（转发全部命令行参数）
const args = [join(root, 'apps/cli/lib/bin.js'), '--profile', 'web', ...process.argv.slice(2)]
const r = spawnSync(process.execPath, args, { cwd: root, stdio: 'inherit' })
process.exit(r.status ?? 1)
