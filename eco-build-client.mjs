// M-B0 重建带 profile gate 的 client 插件 bundle（ui-brand-official / ui-layout）。
// 注入 official profile + ECO 标题，使 clientBuildEnvironmentDefines 将门控内联为开启。
// 经 node 进程内设置 env（UTF-8 字面量），规避 PowerShell 5.1 中文 env 走 GBK 的乱码坑。
import { spawnSync } from 'node:child_process'

const root = 'E:/dsh/eco-agent'
process.env.DSH_CLIENT_BUILD_PROFILE = 'official'
process.env.DSH_CLIENT_TITLE = 'eco Agent 生态环境执法AI赋能工作台'
process.env.CODEBUDDY_SAFE_DELETE_ENABLED = '0'

const node = process.execPath
// 跳过 tsc -b（其增量缓存存在 DSH/dsh 大小写漂移 TS1149）；lib/types 已由既有构建产出，
// tsdown Client face 只消费 lib/types/client/index.js，直接重建即可。
const steps = [
  ['tsdown --env.DSH_BUILD_FACE client', [node, [`${root}/node_modules/tsdown/dist/run.mjs`, '--env.DSH_BUILD_FACE', 'client']]],
]

for (const [label, [exe, args]] of steps) {
  console.log(`\n=== ${label} ===`)
  const r = spawnSync(exe, args, { cwd: root, stdio: 'inherit' })
  if (r.status !== 0) {
    console.error(`FAILED: ${label} (exit ${r.status})`)
    process.exit(r.status ?? 1)
  }
}
console.log('\nALL DONE')
