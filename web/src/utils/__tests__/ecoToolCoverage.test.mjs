import { getToolDescriptor, buildAtom, selectSummary, renderSummary, isFoldable }
  from '../metaFold.ts';

const ECO_TOOLS = ["analyze_document","api_probe","audit_tail","calculate_carbon_emission","chart_render",
"cron_add","cron_list","cron_remove","cron_run","detect_data_anomaly","eco_memory_add","eco_memory_delete",
"eco_memory_prune","eco_memory_search","eco_memory_stats","eco_memory_sync","eco_memory_update",
"eco_policy_reload","execute_code","file_edit","file_read","file_write","generate_pptx","glob","goal_status",
"grep","hunan_case_list","inspect","kb_search","kb_semantic_search","open_url","query_air_quality",
"save_document","session_log_tail","shell_run","spawn_goal","statute_lookup","statute_related",
"statute_search","switch_persona","system_reload","tdocs_upload_html","web_fetch","web_search"];

console.log('=== eco 44 个真实工具的 group 覆盖 ===');
const unknown=[];
for (const t of ECO_TOOLS) {
  const d = getToolDescriptor(t);
  if (d.category === 'unknown') unknown.push(t);
}
console.log(`覆盖 ${ECO_TOOLS.length - unknown.length}/${ECO_TOOLS.length}`);
if (unknown.length) console.log('❌ 未覆盖:', unknown.join(', '));
else console.log('✅ 全部命中，无一退到 unknown 兜底');

console.log('\n=== 真实场景摘要（模拟 eco 实际 trace）===');
const cases = [
  ['单次自检', [['inspect',{kind:'catalog'}]]],
  ['连续自检（同组）', [['inspect',{kind:'catalog'}],['inspect',{kind:'tools'}],['inspect',{kind:'services'}]]],
  ['查法条后写文书', [['statute_search',{query:'大气法'}],['save_document',{filename:'处罚决定书.docx'}]]],
  ['读改同一文件', [['file_read',{path:'/a/report.md'}],['file_edit',{path:'/a/report.md'}]]],
  ['多类操作', [['kb_search',{query:'x'}],['file_write',{path:'a'}],['shell_run',{command:'ls'}],['chart_render',{title:'t'}],['inspect',{kind:'k'}]]],
];
for (const [name, tools] of cases) {
  const atoms = tools.map(([n,a]) => buildAtom(n,a,'success'));
  const r = selectSummary(atoms,false);
  console.log(`  ${name.padEnd(14)} → 「${renderSummary(r.decision,r.status)}」`);
}

console.log('\n=== hoist：图表豁免折叠 ===');
console.log(`  chart_render 可折叠? ${isFoldable('tool','chart_render')} (期望 false)`);
console.log(`  inspect     可折叠? ${isFoldable('tool','inspect')} (期望 true)`);
process.exit(unknown.length ? 1 : 0);
