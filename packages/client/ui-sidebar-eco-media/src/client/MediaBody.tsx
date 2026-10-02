/**
 * Video and audio files played inside the right Sidebar's document previewer.
 *
 * The renderer owns no reads: the document owner delivers complete bytes (the
 * same contract the builtin image renderer uses), and this body turns them into
 * one object URL for a native `<video>` / `<audio>` element. The browser — not
 * this package — decides what it can decode, so an undecodable file is reported
 * as the browser's verdict rather than guessed from the file extension.
 */

import { useEffect, useMemo, useState, type ReactNode } from 'react'
import type { PropsLocale } from '@deepseek-ai/dsh-client-ui-slots'
import type { DocumentPreviewProps } from '@deepseek-ai/dsh-client-ui-sidebar-documentpreview/client'
import css from './MediaBody.module.css'

/** Standard document props plus this renderer's dictionary. */
export type MediaBodyProps = DocumentPreviewProps & PropsLocale<'sidebarEcoMedia'>

/** Suffix-to-MIME table; `audio` and `video` mark which element to render. */
const MEDIA_TYPES = {
  mp4: { type: 'video/mp4', kind: 'video' },
  m4v: { type: 'video/mp4', kind: 'video' },
  webm: { type: 'video/webm', kind: 'video' },
  ogv: { type: 'video/ogg', kind: 'video' },
  mov: { type: 'video/quicktime', kind: 'video' },
  mp3: { type: 'audio/mpeg', kind: 'audio' },
  m4a: { type: 'audio/mp4', kind: 'audio' },
  aac: { type: 'audio/aac', kind: 'audio' },
  wav: { type: 'audio/wav', kind: 'audio' },
  oga: { type: 'audio/ogg', kind: 'audio' },
  ogg: { type: 'audio/ogg', kind: 'audio' },
  flac: { type: 'audio/flac', kind: 'audio' },
} as const

/** File suffixes this renderer claims. */
export const MEDIA_EXTENSIONS = Object.keys(MEDIA_TYPES)

/** Every media suffix is binary: none of them has a readable text fallback. */
export const MEDIA_BINARY_EXTENSIONS = MEDIA_EXTENSIONS

type MediaEntry = typeof MEDIA_TYPES[keyof typeof MEDIA_TYPES]

/**
 * Resolve one file path to the media type and element its suffix implies.
 * @param path - decoded workspace file path or filename.
 * @returns the media entry, or undefined for an unregistered suffix.
 */
export function mediaTypeOf(path: string): MediaEntry | undefined {
  const normalized = path.replaceAll('\\', '/')
  const name = normalized.slice(normalized.lastIndexOf('/') + 1).toLowerCase()
  const extension = name.slice(name.lastIndexOf('.') + 1)
  return MEDIA_TYPES[extension as keyof typeof MEDIA_TYPES]
}

/** The filename a resource address carries, decoded the way it was encoded. */
function fileNameOf(address: string): string {
  const name = address.slice(address.lastIndexOf('/') + 1)
  try {
    return decodeURIComponent(name)
  } catch {
    // A malformed percent sequence is still a name; showing it raw beats refusing it.
    return name
  }
}

/**
 * Play one media file from the bytes the document owner delivered.
 * @param props - document bytes, resource identity, and locale.
 * @returns a native player, or the reason one is not showing.
 */
export function MediaBody({ content, resourceAddress, t }: MediaBodyProps): ReactNode {
  const path = useMemo(() => fileNameOf(resourceAddress), [resourceAddress])
  const entry = mediaTypeOf(path)
  const data = content.kind === 'bytes' ? content.data : undefined
  const [url, setUrl] = useState<string>()
  const [decoded, setDecoded] = useState(true)

  useEffect(() => {
    if (data === undefined || entry === undefined) return
    const blob = new Blob([data as BlobPart], { type: entry.type })
    const objectUrl = URL.createObjectURL(blob)
    setUrl(objectUrl)
    setDecoded(true)
    return () => { URL.revokeObjectURL(objectUrl) }
  }, [data, entry])

  if (entry === undefined) return <p className={css.notice}>{t('unsupported')}</p>
  if (data === undefined || data.byteLength === 0) return <p className={css.notice}>{t('empty')}</p>
  if (url === undefined) return null
  if (!decoded) return <p className={css.notice}>{t('failed')}</p>

  const onError = (): void => { setDecoded(false) }
  return (
    <div className={css.root}>
      {entry.kind === 'video'
        ? <video className={css.player} src={url} controls preload="metadata" onError={onError} />
        : <audio className={css.audio} src={url} controls preload="metadata" onError={onError} />}
      <p className={css.meta}>
        <span className={css.name}>{path}</span>
        <span className={css.hint}>{t('hint')}</span>
      </p>
    </div>
  )
}
