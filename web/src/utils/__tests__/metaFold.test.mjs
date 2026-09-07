// meta-fold 对标测试：逐条比对 WorkBuddy selectSummary 决策树
import { buildAtom, selectSummary, renderSummary, normalizeToolName,
         getToolDescriptor, walkChars, visibleStartIndex, isFoldable,
         SCALAR_COST, COST_WALK_MAX_DEPTH } from '../metaFold.ts';

let pass=0, fail=0;
const eq=(name,got,want)=>{ const ok=JSON.stringify(got)===JSON.stringify(want);
  console.log(`${ok?'✅':'❌'} ${name}` + (ok?'':`\n     got=${JSON.stringify(got)}\n    want=${JSON.stringify(want)}`));
  ok?pass++:fail++; };

console.log('=== 1. normalizeToolName（别名/mcp_ 前缀 → canonical）===');
eq('Read → read_file', normalizeToolName('Read'), 'read_file');
eq('MultiEdit → replace_in_file', normalizeToolName('MultiEdit'), 'replace_in_file');
eq('run_terminal_cmd → execute_command', normalizeToolName('run_terminal_cmd'), 'execute_command');
eq('mcp__eco-hunan-env__x → mcp_call_tool', normalizeToolName('mcp__eco-hunan-env__query'), 'mcp_call_tool');
eq('mcp_foo → mcp_call_tool', normalizeToolName('mcp_foo'), 'mcp_call_tool');
eq('未知工具保留原名', normalizeToolName('eco_custom_tool'), 'eco_custom_tool');
eq('空值 → unknown', normalizeToolName(null), 'unknown');

console.log('\n=== 2. group 映射（WorkBuddy 9 group）===');
eq('read_file → read', getToolDescriptor('Read').group, 'read');
eq('write → modify', getToolDescriptor('Write').group, 'modify');
eq('grep → search', getToolDescriptor('grep').group, 'search');
eq('bash → command', getToolDescriptor('bash').group, 'command');
eq('web_search → research', getToolDescriptor('WebSearch').group, 'research');
eq('todo_write → plan', getToolDescriptor('TodoWrite').group, 'plan');
eq('task → collab', getToolDescriptor('Task').group, 'collab');
eq('mcp → external', getToolDescriptor('mcp__x__y').group, 'external');
eq('show_widget → other', getToolDescriptor('visualize:show_widget').group, 'other');

console.log('\n=== 3. 决策树优先级（对标 selectSummary）===');
const A=(n,a,s)=>buildAtom(n,a,s);
eq('空 → fallback', selectSummary([]).decision.kind, 'fallback');
eq('等待优先于一切', selectSummary([A('Read',{path:'/a.md'},'waiting'),A('Write',{path:'/b'},'success')]).decision.kind, 'waiting');
eq('单一工具 → single', selectSummary([A('Read',{file_path:'/x/report.md'})]).decision.kind, 'single');
eq('同组多工具 → group', selectSummary([A('Read',{path:'/a'}),A('LS',{path:'/b'})]).decision.kind, 'group');
eq('跨组+共同主题 → multiStage',
   selectSummary([A('Read',{path:'a.md'}),A('Write',{path:'a.md'}),A('Edit',{path:'a.md'})]).decision.kind, 'multiStage');
eq('>3 类无主题 → categoryCount',
   selectSummary([A('Read',{path:'a'}),A('Write',{path:'b'}),A('grep',{pattern:'c'}),A('bash',{command:'d'}),A('WebSearch',{query:'e'})]).decision.kind,
   'categoryCount');

console.log('\n=== 4. 无失败聚合态（源码两次强调）===');
const st = selectSummary([A('Read',{path:'a'},'success'),A('Write',{path:'b'},'success')]).status;
eq('聚合态不含 failed', ['waiting','running','cancelled','success'].includes(st), true);
eq('全 cancelled → cancelled', selectSummary([A('Read',{path:'a'},'cancelled'),A('Write',{path:'b'},'cancelled')]).status, 'cancelled');
eq('running 需 isRunning=true', selectSummary([A('Read',{path:'a'},'running')], true).status, 'running');
eq('isRunning=false 时不报 running', selectSummary([A('Read',{path:'a'},'running')], false).status, 'success');

console.log('\n=== 5. 成句 ===');
const say=(atoms,run=false)=>{const r=selectSummary(atoms,run);return renderSummary(r.decision,r.status);};
eq('单文件读取', say([A('Read',{file_path:'/x/执法报告.md'})]), '读取 执法报告.md');
// 原断言期望 '读取 a.md中…' —— 对象名与「中…」粘连成断词，线上实测
// 出现「检查、读取 README*中…」。改为带对象名时用 ' · 进行中'。
eq('运行中带对象名不粘连', say([A('Read',{file_path:'/a.md'},'running')],true), '读取 a.md · 进行中');
eq('同组摘要', say([A('Read',{path:'/a'}),A('LS',{path:'/b'})]), '读取若干项');
eq('路径只留 basename', say([A('Write',{path:'/very/long/dir/out.docx'})]), '写入 out.docx');

console.log('\n=== 6. 展开预算（对标 expand-budget）===');
eq('SCALAR_COST=8', SCALAR_COST, 8);
eq('MAX_DEPTH=6', COST_WALK_MAX_DEPTH, 6);
eq('字符串取长度', walkChars('hello', 1000), 5);
eq('数字记 8', walkChars(42, 1000), 8);
eq('布尔记 8', walkChars(true, 1000), 8);
eq('超预算提前返回', walkChars(['aaaaa','bbbbb','ccccc'], 8) >= 8, true);
eq('深度超限截断', walkChars({a:{b:{c:{d:{e:{f:{g:{h:'deep'}}}}}}}}, 1000), 0);
eq('从尾部取窗口', visibleStartIndex([10,10,10,10,10], 25), 3);
eq('预算充足从头取', visibleStartIndex([1,1,1], 100), 0);

console.log('\n=== 7. hoist / 可折叠性 ===');
eq('show_widget 不可折叠', isFoldable('tool','visualize:show_widget'), false);
eq('show_widget 别名同样', isFoldable('tool','show_widget'), false);
eq('普通工具可折叠', isFoldable('tool','Read'), true);
eq('思考可折叠', isFoldable('think'), true);
eq('正文不折叠', isFoldable('answer'), false);

console.log(`\n通过 ${pass} · 失败 ${fail}`);
process.exit(fail?1:0);
