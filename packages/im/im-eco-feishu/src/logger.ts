// @ts-nocheck
/** 日志工具：统一带时间戳与级别的前缀输出 */
type Level = 'debug' | 'info' | 'warn' | 'error'

const LEVEL_ORDER: Record<Level, number> = { debug: 0, info: 1, warn: 2, error: 3 }

let currentLevel: Level = (process.env.LOG_LEVEL as Level) || 'info'

export function setLogLevel(level: Level) {
  currentLevel = level
}

function log(level: Level, scope: string, ...args: unknown[]) {
  if (LEVEL_ORDER[level] < LEVEL_ORDER[currentLevel]) return
  const time = new Date().toISOString()
  const prefix = `[${time}] [${level.toUpperCase()}] [${scope}]`
  if (level === 'error') {
    console.error(prefix, ...args)
  } else {
    console.log(prefix, ...args)
  }
}

export const logger = {
  debug: (scope: string, ...args: unknown[]) => log('debug', scope, ...args),
  info: (scope: string, ...args: unknown[]) => log('info', scope, ...args),
  warn: (scope: string, ...args: unknown[]) => log('warn', scope, ...args),
  error: (scope: string, ...args: unknown[]) => log('error', scope, ...args),
}
