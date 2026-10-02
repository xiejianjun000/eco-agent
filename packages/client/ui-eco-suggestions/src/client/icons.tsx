/**
 * eco 六角色图标（stroke 风格，16×16，stroke-width 1.5）。放在品牌渐变封面上时用白色。
 * 与军哥设计标准一致：strokeWidth=1.5，round cap/join。
 */
import type { ReactElement } from 'react'

/** 角色图标共享 props。 */
export interface RoleIconProps {
  /** 边长（px）。 */
  size?: number
  /** 额外 class（用于上色：默认 currentColor）。 */
  className?: string
}

const strokeProps = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
} as const

/** 企业合规 — 盾牌勾选。 */
export function IconShieldCheck({ size = 24, className }: RoleIconProps): ReactElement {
  return (
    <svg width={size} height={size} className={className} viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <path {...strokeProps} d="M8 1.8l5 2v4.5c0 3.2-2.5 5.2-5 6.2-2.5-1-5-3-5-6.2V3.8l5-2z" />
      <path {...strokeProps} d="M6 8l1.5 1.5L10.2 6.8" />
    </svg>
  )
}

/** 执法办案 — 天秤。 */
export function IconScale({ size = 24, className }: RoleIconProps): ReactElement {
  return (
    <svg width={size} height={size} className={className} viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <path {...strokeProps} d="M8 2.3v11" />
      <path {...strokeProps} d="M4.5 13.3h7" />
      <path {...strokeProps} d="M8 2.3L3.4 6.3h9.2L8 2.3z" />
      <path {...strokeProps} d="M3.4 6.3L2 9.8h2.8L3.4 6.3z" />
      <path {...strokeProps} d="M12.6 6.3l-1.4 3.5h2.8l-1.4-3.5z" />
    </svg>
  )
}

/** 督察检查 — 放大镜。 */
export function IconMagnifier({ size = 24, className }: RoleIconProps): ReactElement {
  return (
    <svg width={size} height={size} className={className} viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <circle {...strokeProps} cx="7" cy="7" r="4.4" />
      <path {...strokeProps} d="M10.6 10.6L14 14" />
    </svg>
  )
}

/** 许可审批 — 印章。 */
export function IconStamp({ size = 24, className }: RoleIconProps): ReactElement {
  return (
    <svg width={size} height={size} className={className} viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <path {...strokeProps} d="M3.4 8.4h9.2" />
      <path {...strokeProps} d="M4.4 8.4v4h7.2v-4" />
      <path {...strokeProps} d="M8 4.6c1.5 0 2.1.7 2.1 1.7H5.9c0-1 .6-1.7 2.1-1.7z" />
    </svg>
  )
}

/** 科研分析 — 锥形瓶。 */
export function IconFlask({ size = 24, className }: RoleIconProps): ReactElement {
  return (
    <svg width={size} height={size} className={className} viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <path {...strokeProps} d="M10 2.4v4.5l4 5.5v.4H2v-.4l4-5.5V2.4" />
      <path {...strokeProps} d="M6.5 2.4h3" />
      <path {...strokeProps} d="M6.7 10.4h2.6" />
    </svg>
  )
}

/** 复制 — 两张重叠的纸。 */
export function CopyGlyph({ size = 14, className }: RoleIconProps): ReactElement {
  return (
    <svg width={size} height={size} className={className} viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <rect {...strokeProps} x="5.5" y="5.5" width="8" height="8" rx="1.6" />
      <path {...strokeProps} d="M10.5 5.5V3.9c0-.9-.7-1.6-1.6-1.6H3.9c-.9 0-1.6.7-1.6 1.6v5c0 .9.7 1.6 1.6 1.6h1.6" />
    </svg>
  )
}

/** 已复制 — 勾选。 */
export function CheckGlyph({ size = 14, className }: RoleIconProps): ReactElement {
  return (
    <svg width={size} height={size} className={className} viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <path {...strokeProps} d="M3 8.6l3.2 3.2L13 4.8" />
    </svg>
  )
}

/** 学习培训 — 翻开的书。 */
export function IconBook({ size = 24, className }: RoleIconProps): ReactElement {
  return (
    <svg width={size} height={size} className={className} viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <path {...strokeProps} d="M2 3.5h4.5c1 0 1.5.5 1.5 1.5v8c0-1-.5-1.5-1.5-1.5H2v-8z" />
      <path {...strokeProps} d="M14 3.5H9.5c-1 0-1.5.5-1.5 1.5v8c0-1 .5-1.5 1.5-1.5H14v-8z" />
    </svg>
  )
}
