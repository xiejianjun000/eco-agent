/** 照搬阶段：第三方依赖缺类型声明时的宽松兜底。TODO(重构) 移除。 */
declare module 'qrcode' {
  const qrcode: any
  export default qrcode
}
