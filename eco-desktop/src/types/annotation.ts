// annotation.ts — 协同批注数据模型（人机协同编辑核心）

export type AnnotationType = 'error' | 'warning' | 'suggestion' | 'question'
export type AnnotationStatus = 'pending' | 'accepted' | 'rejected' | 'edited'
export type AnnotationSource = 'ai' | 'human'

export interface Annotation {
  id: string
  type: AnnotationType
  start: number          // 文档字符位置
  length: number         // 高亮长度
  originalText: string   // 原文
  suggestion: string     // 建议修改
  note: string           // 批注说明
  status: AnnotationStatus
  source: AnnotationSource
  traceId: string
  createdAt: number
  updatedAt?: number
}

// 批注样式配置
export const ANNOTATION_STYLES: Record<AnnotationType, { color: string; icon: string; label: string }> = {
  error:      { color: '#f04040', icon: '🔴', label: '错误' },
  warning:    { color: '#f0a040', icon: '🟠', label: '警示' },
  suggestion: { color: '#40a0f0', icon: '🔵', label: '建议' },
  question:   { color: '#a040f0', icon: '🟣', label: '疑问' },
}

// 生成唯一 ID
export function genId(): string {
  return `a_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

// 创建 AI 批注
export function createAiAnnotation(
  start: number,
  length: number,
  originalText: string,
  suggestion: string,
  note: string,
  type: AnnotationType = 'error',
  traceId: string = ''
): Annotation {
  return {
    id: genId(),
    type,
    start, length,
    originalText,
    suggestion,
    note,
    status: 'pending',
    source: 'ai',
    traceId: traceId || genId(),
    createdAt: Date.now(),
  }
}

// 创建人类批注
export function createHumanAnnotation(
  start: number,
  length: number,
  originalText: string,
  note: string,
  type: AnnotationType = 'question',
): Annotation {
  return {
    id: genId(),
    type,
    start, length,
    originalText,
    suggestion: '',
    note,
    status: 'pending',
    source: 'human',
    traceId: genId(),
    createdAt: Date.now(),
  }
}

// 应用批注到文档文本
export function applyAnnotationToText(text: string, ann: Annotation): string {
  if (ann.status !== 'accepted' || !ann.suggestion) return text
  const before = text.slice(0, ann.start)
  const after = text.slice(ann.start + ann.length)
  return before + ann.suggestion + after
}

// 按位置排序
export function sortAnnotations(anns: Annotation[]): Annotation[] {
  return [...anns].sort((a, b) => a.start - b.start)
}
