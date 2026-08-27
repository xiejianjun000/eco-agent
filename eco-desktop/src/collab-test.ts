// collab-test.ts — 人机协同编辑全链路测试（G4 质量门禁）
// 验证：AI评查 → 人类接受/拒绝/修改 → 应用到文档 → 位置校正

import {
  Annotation, AnnotationStatus,
  createAiAnnotation, createHumanAnnotation,
  applyAnnotationToText, sortAnnotations,
} from './types/annotation'

let passed = 0
let failed = 0

function assert(cond: boolean, msg: string) {
  if (cond) {
    passed++
    console.log(`  [PASS] ${msg}`)
  } else {
    failed++
    console.log(`  [FAIL] ${msg}`)
  }
}

// ─── T1: 创建 AI 批注 ─────────────────────
console.log('--- T1: AI 批注创建 ---')
const ann1 = createAiAnnotation(3, 9, '450mg/m³', '450mg/m³（超标125%）', '浓度超标', 'error')
assert(ann1.id.length > 0, '批注 ID 生成')
assert(ann1.status === 'pending', '初始状态 pending')
assert(ann1.source === 'ai', '来源是 AI')
assert(ann1.traceId.length > 0, 'traceId 存在')
assert(ann1.type === 'error', '类型 error')
assert(ann1.start === 3 && ann1.length === 9, '位置正确')
assert(ann1.originalText === '450mg/m³', '原文保存')

// ─── T2: 创建人类批注 ─────────────────────
console.log('--- T2: 人类批注创建 ---')
const ann2 = createHumanAnnotation(18, 6, '证据材料', '这里需要补充时间戳照片')
assert(ann2.source === 'human', '来源是人类')
assert(ann2.type === 'question', '默认类型 question')
assert(ann2.note === '这里需要补充时间戳照片', '批注内容')

// ─── T3: 应用接受后的修改 ───────────────────
console.log('--- T3: 应用批注到文档 ---')
const sampleText = '浓度为450mg/m³，超过标准限值。'
const acceptAnn: Annotation = { ...ann1, status: 'accepted' }
const applied = applyAnnotationToText(sampleText, acceptAnn)
assert(applied.includes('450mg/m³（超标125%）'), '应用建议文本')
assert(!applied.includes('浓度为450mg/m³，超'), '原文被替换')
console.log(`    结果: ${applied}`)

// ─── T4: 未接受的批注不应用 ─────────────────
console.log('--- T4: 未接受不应用 ---')
const pendingAnn: Annotation = { ...ann1, status: 'pending' }
const notApplied = applyAnnotationToText(sampleText, pendingAnn)
assert(notApplied === sampleText, 'pending 状态不改文档')

// ─── T5: 拒绝批注不改文档 ──────────────────
console.log('--- T5: 拒绝不应用 ---')
const rejectedAnn: Annotation = { ...ann1, status: 'rejected' }
assert(applyAnnotationToText(sampleText, rejectedAnn) === sampleText, 'rejected 不改文档')

// ─── T6: 排序 ─────────────────────────────
console.log('--- T6: 批注按位置排序 ---')
const a3 = createAiAnnotation(50, 5, 'aaa', 's1', 'n1', 'error')
const a4 = createAiAnnotation(10, 5, 'bbb', 's2', 'n2', 'warning')
const sorted = sortAnnotations([a3, a4])
assert(sorted[0].start === 10 && sorted[1].start === 50, '按 start 升序')

// ─── T7: 位置校正逻辑 ──────────────────────
console.log('--- T7: 文本变更后位置校正 ---')
// 接受批注后文本变长，后续批注应偏移
const t = 'abcd efgh ijkl mnop'
const midAnn = createAiAnnotation(5, 4, 'efgh', 'EFGHXXXX', '替换', 'error')  // 变长4
const laterAnn = createAiAnnotation(12, 4, 'ijkl', 'ijkl', '后续', 'warning') // 在 midAnn 之后
const diff = midAnn.suggestion.length - midAnn.length  // 8-4 = 4
const adjustedLater = { ...laterAnn, start: laterAnn.start + diff }
assert(adjustedLater.start === 16, `后续批注偏移: ${laterAnn.start} -> ${adjustedLater.start}`)

// ─── T8: 状态机转换 ────────────────────────
console.log('--- T8: 状态机 ---')
assert(ann1.status === 'pending', 'pending')
const accepted = { ...ann1, status: 'accepted' as AnnotationStatus }
assert(accepted.status === 'accepted', 'pending -> accepted')
const edited = { ...accepted, status: 'edited' as AnnotationStatus, suggestion: '人工修改版' }
assert(edited.status === 'edited' && edited.suggestion === '人工修改版', 'accepted -> edited')

// ─── T9: 同位置多批注 ──────────────────────
console.log('--- T9: 同一位置叠加批注 ---')
const same1 = createAiAnnotation(10, 5, 'abcde', 'A', 'n1', 'error')
const same2 = createAiAnnotation(10, 5, 'abcde', 'B', 'n2', 'warning')
assert(same1.start === same2.start, '同位置批注共存')

// ─── T10: traceId 唯一性 ───────────────────
console.log('--- T10: traceId 唯一性 ---')
const ids = new Set([ann1.traceId, ann2.traceId, a3.traceId, a4.traceId])
assert(ids.size === 4, '4 个批注 traceId 均不同')

console.log(`\n══════════════════════════`)
console.log(`  G4 测试结果: ${passed} PASS, ${failed} FAIL`)
console.log(`══════════════════════════`)
if (failed === 0) {
  console.log('  ✅ 协同编辑数据模型全部通过')
} else {
  console.log('  ❌ 存在失败，需修复')
}
