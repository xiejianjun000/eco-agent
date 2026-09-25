import { defineConfig } from 'tsdown'

/** 飞书助手：entry 是 tsc 编译产物（src → lib/types），打包到 lib。 */
export default defineConfig({
  entry: ['lib/types/index.js'],
  outDir: 'lib',
  format: ['esm'],
  platform: 'node',
  target: 'es2024',
  dts: false,
  clean: false,
})
