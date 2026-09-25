/** Locale bundles for the eco media renderer (video / audio) in the right Sidebar. */

/** Locale keys this renderer shows. */
export type MediaKey =
  | 'title'
  | 'unsupported'
  | 'failed'
  | 'empty'
  | 'hint'

/** Namespace the dictionaries register under. */
export const NS = 'sidebarEcoMedia'

/** English copy. */
export const en: Record<MediaKey, string> = {
  title: 'Media',
  unsupported: 'No registered media type for this file extension.',
  failed: 'This file could not be decoded by the browser.',
  empty: 'No media bytes arrived; the file may exceed the preview read cap.',
  hint: 'Playback runs on the file bytes the Host sent, inside the page — nothing is uploaded.',
}

/** Simplified Chinese copy. */
export const zh: Record<MediaKey, string> = {
  title: '媒体',
  unsupported: '注册的媒体类型里没有这个文件后缀。',
  failed: '浏览器无法解码这个文件。',
  empty: '没有拿到媒体数据，文件可能超过了预览读取上限。',
  hint: '播放的是宿主送来的文件字节，在页面内解码，不上传任何内容。',
}
