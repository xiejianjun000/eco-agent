/**
 * MCP descriptor 语义化测试。
 *
 * 两个真实 bug：
 *  A) 所有 mcp__ 工具折成 mcp_call_tool，展开态一律「调用 · {参数}」，
 *     17 台服务器几百个工具长一个样。
 *  B) 修 A 时手写 descriptor 漏了 objectFields，extractObject 对 undefined
 *     做 for...of → "objectFields is not iterable" → **整页白屏**。
 *     tsc 没拦住是因为当时写了 as ToolDescriptor 断言。
 */
import { getToolDescriptor, extractObject, buildAtom, mcpObject } from '../metaFold.ts';

let pass = 0, fail = 0;
const ok = (c, msg) => c ? pass++ : (fail++, console.log('  ✗ ' + msg));
const eq = (a, b, msg) => ok(JSON.stringify(a) === JSON.stringify(b),
  `${msg}\n     实际 ${JSON.stringify(a)}\n     期望 ${JSON.stringify(b)}`);

console.log('1. descriptor 字段完整性（白屏根因）');
for (const n of [
  'mcp__eco-hunan-env__air_quality_hourly',
  'mcp__eia-emission__query_emission_gas_country',
  'mcp__eia-law-keyword__search_keyword_policy',
  'mcp__tencent_docs__get_content',
  'mcp__x__unknown_verb_here',
]) {
  const d = getToolDescriptor(n);
  ok(Array.isArray(d.objectFields), `${n}: objectFields 必须是数组，否则 for...of 白屏`);
  ok(Array.isArray(d.aliases), `${n}: aliases 必须是数组`);
  ok(typeof d.action === 'string' && d.action, `${n}: action 不能为空`);
  // 真正跑一遍 extractObject —— 这才是白屏发生的地方
  let threw = false;
  try { extractObject(d, { city: '娄底市' }); } catch { threw = true; }
  ok(!threw, `${n}: extractObject 不应抛异常`);
}

console.log('2. 动词按内层工具名细化');
eq(getToolDescriptor('mcp__eco-hunan-env__air_quality_hourly').action, '查询', 'air_quality_* → 查询');
eq(getToolDescriptor('mcp__eia-emission__query_emission_gas_country').action, '检索', 'query_* → 检索');
eq(getToolDescriptor('mcp__eia-law-keyword__search_keyword_policy').action, '检索', 'search_* → 检索');
eq(getToolDescriptor('mcp__tencent_docs__get_content').action, '读取', 'get_* → 读取');
eq(getToolDescriptor('mcp__p__download_license_page').action, '下载', 'download_* → 下载');

console.log('3. 未命中动词时仍可用（不能崩，退回泛化）');
{
  const d = getToolDescriptor('mcp__srv__zzz_weird_name');
  ok(typeof d.action === 'string' && d.action.length > 0, '未命中应有兜底 action');
  ok(Array.isArray(d.objectFields), '兜底 descriptor 也要有 objectFields');
}

console.log('4. mcpObject 提取对象名');
eq(mcpObject('mcp__eco-hunan-env__air_quality_hourly'), 'air quality hourly', '去前缀转空格');
eq(mcpObject('mcp__eia-emission__query_emission_gas_country'), 'emission gas country', '剥掉 query_ 动词');
eq(mcpObject('not_an_mcp_tool'), undefined, '非 MCP 名返回 undefined');

console.log('5. extractObject 容忍缺字段（防御层）');
{
  let threw = false;
  try {
    extractObject({ canonical: 'x', aliases: [], category: 'c', group: 'other',
                    action: 'a', noObject: 'n' }, { path: '/tmp/a.md' });
  } catch { threw = true; }
  ok(!threw, '缺 objectFields 不应抛异常 —— 单个 descriptor 写错不该炸整页');
}

console.log('6. buildAtom 端到端');
{
  const a = buildAtom('mcp__eco-hunan-env__air_quality_hourly', { city: '娄底市' });
  eq(a.action, '查询', 'buildAtom 应拿到细化后的动词');
  ok(a.group === 'external', 'MCP 仍归 external 组');
}

console.log(`\n通过 ${pass} · 失败 ${fail}`);
if (fail) process.exit(1);
