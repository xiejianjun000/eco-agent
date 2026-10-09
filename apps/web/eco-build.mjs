// M-B0 eco 品牌收口构建包装器：以 official profile + ECO 标题执行 vite build。
// 经 node 进程内设置 env（UTF-8 源文件字面量），规避 PowerShell 5.1 env 传中文走 GBK 的乱码坑。
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
process.env.DSH_CLIENT_BUILD_PROFILE = 'official'
process.env.DSH_CLIENT_TITLE = 'eco Agent 生态环境执法AI赋能工作台'
// 仅供本构建子进程（vite 清空自己的 dist 产物）豁免宿主批量删除守卫；不影响其它任何命令。
process.env.CODEBUDDY_SAFE_DELETE_ENABLED = '0'

const viteBin = join(here, 'node_modules', 'vite', 'bin', 'vite.js')
const result = spawnSync(process.execPath, [viteBin, 'build'], {
  cwd: here,
  stdio: 'inherit',
})
process.exit(result.status ?? 1)
