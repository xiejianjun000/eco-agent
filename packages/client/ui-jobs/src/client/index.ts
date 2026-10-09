/**
 * Background-job plugin, browser half: contributes one session-header action
 * that renders this session's jobs. Job rows, per-row observation streams,
 * and the human kill all go through the `jobs` client service; this plugin
 * holds no transport state of its own.
 */
import type { Context as ClientContext } from '@eco-agent/cordis'
import type { JobId } from '@eco-agent/dsh-jobs/brand'
import { JobListAction } from './JobListAction.tsx'
import type { JobListInjected } from './JobListAction.tsx'
import { PluginsShortcut } from './PluginsShortcut.tsx'
import type {} from '@eco-agent/dsh-api-job-controller/client'
import type {} from '@eco-agent/dsh-client-locale/client'
import type {} from '@eco-agent/dsh-client-ui-layout/client'
import type {} from '@eco-agent/dsh-client-ui-renderer/client'
import type {} from '@eco-agent/dsh-client-ui-session/client'
import { en, NS, zh, type JobKey } from './locales.ts'

declare module '@eco-agent/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** Background-job list copy. */
    'job': JobKey
  }
}

export type { JobListActionProps, JobListInjected } from './JobListAction.tsx'

/**
 * Required services: the jobs rosters, observations, and kill, the slot
 * registry, dictionaries, and layout (the Plugins panel shortcut).
 */
export const inject = ['jobs', 'slots', 'locale', 'layout']

/**
 * Client plugin body: register the dictionaries and the header action.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-jobs: dictionaries')
  ctx.slots.inject(
    'conversation.session.header.actions',
    () => ctx.slots.register({
      name: 'conversation.session.header.actions',
      id: 'job-list',
      // Background work follows the preset label in the header actions band.
      order: 20,
      locale: NS,
      inject: (): JobListInjected => ({
        hooks: { jobs: ctx.jobs.state },
        watchRows: sessionId => ctx.jobs.watchRows(sessionId),
        observe: (sessionId, id) => ctx.jobs.observe(sessionId, id),
        // The brand is nominal typing only; the row key is the registry id the
        // roster stream delivered, so the wire boundary stamps it back here.
        killJob: async (sessionId, jobId) => (await ctx.jobs.kill(sessionId, jobId as JobId)).ok,
      }),
    }, JobListAction),
  )
  // eco 会话枢纽：会话头「插件」直达——跳转侧栏全局面板的 Plugins 页。
  // 与自动任务入口并排，把 IMA copilot 的「会话信息页聚集能力入口」心智落在会话头。
  ctx.slots.inject(
    'conversation.session.header.actions',
    () => ctx.slots.register({
      name: 'conversation.session.header.actions',
      id: 'plugins-shortcut',
      order: 21,
      locale: NS,
      inject: () => ({ openPlugins: () => ctx.layout.selectPanel('plugins' as never) }),
    }, PluginsShortcut)  )
}
