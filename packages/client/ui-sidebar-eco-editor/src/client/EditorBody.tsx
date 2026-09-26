/**
 * In-place text editor for one workspace file, rendered as a document body.
 *
 * The renderer owns its read: it asks `workspaceFiles` for the complete file and
 * holds the version that read reported, because a save is a guarded write — the
 * version is what lets the Host refuse to clobber a file that changed between
 * the read and the save. A refused save is reported as a conflict, not swallowed:
 * the draft is kept and the user reloads instead of silently winning.
 *
 * Every outcome is an honest state. There is no optimistic "saved" mark: the
 * button reports saving, saved, conflict, or failure, and a file the Host
 * refuses (or a deployment with no write channel mounted) says so outright.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { PropsLocale } from '@deepseek-ai/dsh-client-ui-slots'
import type { DocumentPreviewProps } from '@deepseek-ai/dsh-client-ui-sidebar-documentpreview/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import { parseFileAddress } from '@deepseek-ai/dsh-util-workspace-path'
import type { EditorKey } from './locales.ts'
import { editorRemote } from './remote-store.ts'
import css from './EditorBody.module.css'

type EditorProps = DocumentPreviewProps & PropsLocale<'sidebarEcoEditor'>

/** What the last save attempt ended in, or nothing when no attempt is pending. */
type SaveState =
  | { readonly kind: 'idle' }
  | { readonly kind: 'saving' }
  | { readonly kind: 'saved' }
  | { readonly kind: 'conflict' }
  | { readonly kind: 'failed'; readonly reason: string }

/** One file the editor resolved from its tab address. */
interface EditorTarget {
  readonly sessionId: SessionId
  readonly path: string
}

/** Decode base64 bytes as UTF-8 without the DOM's atob escaping pitfalls. */
function decodeText(base64: string): string {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
  return new TextDecoder().decode(bytes)
}

/**
 * Editable body for one text file.
 * @param props - document content, tab identity, and this package's dictionary.
 * @returns the editor surface, or a state line when the file cannot be edited.
 */
export function EditorBody({ content, useTabInfo, t }: EditorProps): ReactNode {
  const { tab } = useTabInfo()
  const target = useMemo<EditorTarget | undefined>(() => {
    const parsed = parseFileAddress(tab.contentId)
    if (parsed?.scope !== 'session') return undefined
    return { sessionId: parsed.sessionId as SessionId, path: parsed.path }
  }, [tab.contentId])

  const [source, setSource] = useState<string | undefined>(undefined)
  const [version, setVersion] = useState<string | undefined>(undefined)
  const [draft, setDraft] = useState<string | undefined>(undefined)
  const [readFailed, setReadFailed] = useState(false)
  const [saveState, setSaveState] = useState<SaveState>({ kind: 'idle' })
  const epoch = useRef(0)

  const revision = content.kind === 'renderer' ? content.revision : 0
  const remote = editorRemote()
  const writer = remote?.ecoWorkspaceWrite

  // One read per content revision; a stale settlement cannot overwrite a newer one.
  useEffect(() => {
    if (target === undefined || remote === undefined || content.kind !== 'renderer') return
    const mine = epoch.current + 1
    epoch.current = mine
    const controller = new AbortController()
    setReadFailed(false)
    void remote.workspaceFiles.readAll(target.sessionId, target.path, controller.signal).then((outcome) => {
      if (epoch.current !== mine) return
      if (!outcome.ok) {
        setReadFailed(true)
        content.loaded('')
        return
      }
      const text = decodeText(outcome.value.data)
      setSource(text)
      setVersion(outcome.value.version)
      setDraft(text)
      setSaveState({ kind: 'idle' })
      content.loaded(outcome.value.version)
    })
    return () => { controller.abort() }
  }, [target, remote, revision, content])

  const dirty = source !== undefined && draft !== undefined && draft !== source
  const canSave = writer !== undefined && version !== undefined && dirty && saveState.kind !== 'saving'

  const save = useCallback(() => {
    if (target === undefined || writer === undefined || version === undefined || draft === undefined) return
    setSaveState({ kind: 'saving' })
    void writer.writeText(target.sessionId, target.path, draft, version, new AbortController().signal)
      .then((outcome) => {
        if (!outcome.ok) {
          setSaveState(
            outcome.error.code === 'eco-write/stale-version'
              ? { kind: 'conflict' }
              : { kind: 'failed', reason: outcome.error.message },
          )
          return
        }
        setSource(draft)
        setVersion(outcome.value.version)
        setSaveState({ kind: 'saved' })
      })
  }, [target, writer, version, draft])

  if (target === undefined) {
    return <div className={css.state} data-editor-state="unsupported">{t('state.unsupported')}</div>
  }
  if (content.kind !== 'renderer') {
    return <div className={css.state} data-editor-state="unsupported">{t('state.unsupported')}</div>
  }
  if (readFailed) {
    return <div className={css.state} data-editor-state="failed">{t('error.read')}</div>
  }
  if (source === undefined || draft === undefined) {
    return <div className={css.state} data-editor-state="loading">{t('state.loading')}</div>
  }

  const stateKey: EditorKey = saveState.kind === 'saving' ? 'state.saving'
    : saveState.kind === 'saved' ? 'state.saved'
      : saveState.kind === 'conflict' ? 'state.conflict'
        : saveState.kind === 'failed' ? 'error.save'
          : dirty ? 'state.dirty'
            : 'state.clean'

  return (
    <div className={css.editor}>
      <div className={css.bar}>
        <span className={css.status} data-editor-state={saveState.kind}>{t(stateKey)}</span>
        {saveState.kind === 'failed' ? <span className={css.reason}>{saveState.reason}</span> : null}
        <span className={css.spacer} />
        <span className={css.hint}>{t('hint.shortcut')}</span>
        <button
          type="button"
          className={css.action}
          onClick={() => { content.reload() }}
          data-editor-action="reload"
        >
          {t('action.reload')}
        </button>
        <button
          type="button"
          className={`${css.action} ${css.primary}`}
          disabled={!canSave}
          onClick={save}
          data-editor-action="save"
          data-editor-enabled={canSave ? 'true' : 'false'}
        >
          {t('action.save')}
        </button>
      </div>
      <textarea
        className={css.text}
        value={draft}
        spellCheck={false}
        onChange={(event) => { setDraft(event.target.value); setSaveState({ kind: 'idle' }) }}
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === 's') {
            event.preventDefault()
            if (canSave) save()
          }
        }}
        data-editor-dirty={dirty ? 'true' : 'false'}
      />
      {writer === undefined ? <div className={css.note}>{t('state.readonly')}</div> : null}
    </div>
  )
}
