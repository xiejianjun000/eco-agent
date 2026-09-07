import { summarizeResult, statusTextOf, primaryOf, buildBeats } from '../turnFold.ts';
let p=0,f=0;
const eq=(n,g,w)=>{const ok=JSON.stringify(g)===JSON.stringify(w);
  console.log(`${ok?'✅':'❌'} ${n}`+(ok?'':` got=${JSON.stringify(g)} want=${JSON.stringify(w)}`)); ok?p++:f++;};

console.log('=== 1. 动词两态（对标 tool.*.running / done）===');
eq('file_read 运行', statusTextOf('file_read', true), '读取中');
eq('file_read 完成', statusTextOf('file_read', false), '已读取');
eq('grep 完成', statusTextOf('grep', false), '已搜索');
eq('audit_tail 完成', statusTextOf('audit_tail', false), '已读审计链');
// WorkBuddy 的 execute_command statusText 为空——命令本身就是主体
eq('shell 完成态无动词', statusTextOf('shell_run', false), '');
eq('shell 运行态有动词', statusTextOf('shell_run', true), '执行中');
eq('MCP 运行', statusTextOf('mcp__eco__x', true), '调用 MCP 中');
eq('未知工具', statusTextOf('weird', false), '已完成');

console.log('\n=== 2. 主体不与动词重复 ===');
eq('路径取 basename', primaryOf('file_read',{path:'/a/b/README.md'}), 'README.md');
eq('shell 整条命令', primaryOf('shell_run',{command:'ls -la /tmp'}), 'ls -la /tmp');
eq('检索用查询词', primaryOf('grep',{pattern:'TODO'}), 'TODO');
eq('glob 用 pattern', primaryOf('glob',{pattern:'**/README*'}), '**/README*');
eq('无参数为空', primaryOf('inspect',{}), '');
eq('长命令截断', primaryOf('shell_run',{command:'x'.repeat(60)}).length, 47);
// 实测「已出图 m³）」：标题被硬切在括号里只剩右括号
eq('标题不按斜杠取 basename',
   primaryOf('chart_render',{title:'五参数浓度对比（单位 μg/m³）'}),
   '五参数浓度对比（单位 μg/m³）');
// 40 字标题，第 34 字切在未闭合括号内 → 应回退到左括号前
eq('不切在未闭合括号内',
   primaryOf('chart_render',{title:'长沙娄底两市五参数实时空气质量浓度对比柱状图（统一单位微克每立方米，数据源省厅）'}),
   '长沙娄底两市五参数实时空气质量浓度对比柱状图…');
// 括号已闭合则正常截断
eq('闭合括号正常截断',
   primaryOf('chart_render',{title:'长沙娄底两市五参数实时空气质量浓度对比柱状图（统一单位微克每立方米）备注'}),
   '长沙娄底两市五参数实时空气质量浓度对比柱状图（统一单位微克每立方米）…');
eq('末尾标点被清掉', primaryOf('chart_render',{title:'一二三四五六七八九十'.repeat(4)}).endsWith('…'), true);

console.log('\n=== 3. 次要信息（结果摘要）===');
eq('shell 行数', summarizeResult('{"ok":true,"exit":0,"stdout":"a\\nb\\nc"}'), '3 行输出');
eq('计数', summarizeResult('{"ok":true,"count":3,"entries":[1,2,3]}'), '3 条');
// 主体已显示文件名，次要信息只报行数，不重复
eq('文件只报行数', summarizeResult('{"ok":true,"path":"/a/README.md","content":"x\\ny"}'), '2 行');
eq('失败', summarizeResult('{"ok":false,"error":"命令含危险语法"}'), '失败：命令含危险语法');
// 真实场景：result_preview 被截到 200 字符，JSON 必然非法
eq('截断残片抠 count',
   summarizeResult('{"ok": true, "count": 3, "entries": [{"ts": "2026-09-07T20:18:38", "source": "permis'),
   '3 条');
eq('截断残片抠 error', summarizeResult('{"ok": false, "error": "命令含危险语法（重定向'), '失败：命令含危险语法（重定向');
eq('截断只剩 ok', summarizeResult('{"ok": true, "stdout": "total 3408\\ndrwxr-x'), '完成');
eq('非法JSON回退原文', summarizeResult('{broken'), '{broken');
eq('空 → undefined', summarizeResult(''), undefined);

console.log('\n--- MCP 双层 JSON（实测缺陷）---');
// 实测原始形态：外层 {success,is_error,text}，text 里又是 JSON 字符串
const mcpReal = JSON.stringify({success:true,is_error:false,
  text: JSON.stringify({city:'娄底',source:'https://air.cnemc.cn',items:[{AQI:'62'},{AQI:'70'}]})});
eq('MCP 剥外层取内层条数', summarizeResult(mcpReal), '2 条');
eq('MCP 失败', summarizeResult('{"success":false,"is_error":true,"text":"x"}'), '失败');
eq('MCP is_error', summarizeResult('{"success":true,"is_error":true,"text":"x"}'), '失败');
eq('MCP 内层纯文本', summarizeResult('{"success":true,"is_error":false,"text":"已连接 24 个工具"}'), '已连接 24 个工具');

// 截断到 200 字符后 JSON.parse 必失败，正则兜底也必须认得 MCP。
// 下面这串取自实测（娄底实时空气），长度已超 200，截断后内层 city/AQI 仍在。
const realMcp = '{"success": true, "is_error": false, "text": "{\\n  \\"city\\": \\"娄底\\",\\n  \\"source\\": \\"https://air.cnemc.cn:18007/\\",\\n  \\"items\\": [\\n    {\\n      \\"城市\\": \\"娄底市\\",\\n      \\"AQI\\": \\"62\\",\\n      \\"空气质量\\": \\"良\\",\\n      \\"等级\\": \\"二级\\"';
eq('实测残片长度已超 200', realMcp.length > 200, true);
eq('截断 MCP 抠出城市+AQI', summarizeResult(realMcp), '娄底 AQI 62');
eq('截断 MCP 失败态', summarizeResult('{"success": true, "is_error": true, "text": "{oops'), '失败');
// 未截断的完整 MCP 走对象分支，按内层 items 计数
eq('完整 MCP 计数', summarizeResult(JSON.stringify({success:true,is_error:false,
   text: JSON.stringify({items:[1,2,3]})})), '3 条');

console.log('\n=== 4. 三段式组装 ===');
const b=buildBeats([
  {type:'narration',text:'先看 README。'},
  {type:'tool',name:'file_read',args:{path:'/x/README.md'},
   result_preview:'{"ok":true,"path":"/x/README.md","content":"a\\nb"}',cost_ms:5},
], ()=>false);
eq('say + act', b.map(x=>x.kind), ['say','act']);
eq('动词', b[1].status, '已读取');
eq('主体', b[1].text, 'README.md');
eq('次要只报行数', b[1].secondary, '2 行');
// 关键：三段互不重复（这正是 eco 之前的毛病）
eq('动词不含主体', b[1].status.includes('README'), false);
eq('次要不重复主体', b[1].secondary.includes('README'), false);

console.log('\n--- MCP 块主体（实测缺陷）---');
// 曾显示「已调用 MCP{"success": true, "is_error": false, "text": "…」
eq('MCP 主体取工具名', primaryOf('mcp__eco-hunan-env__air_quality_realtime', {q:1}), 'air_quality_realtime');
eq('MCP 动词', statusTextOf('mcp__eco-hunan-env__x', false), '已调用 MCP');

console.log('\n=== 5. running → done 原地替换 ===');
const r1=buildBeats([{type:'tool_start',name:'audit_tail',args:{}}], ()=>false);
eq('tool_start 占位', [r1.length, r1[0].running, r1[0].status], [1, true, '读审计链中']);

const r2=buildBeats([
  {type:'tool_start',name:'audit_tail',args:{}},
  {type:'tool',name:'audit_tail',args:{},result_preview:'{"ok":true,"count":3}',cost_ms:7},
], ()=>false);
eq('完成后仅一行', r2.length, 1);
eq('替换为完成态', [r2[0].running, r2[0].status, r2[0].secondary, r2[0].ms],
   [undefined, '已读审计链', '3 条', 7]);

// 并行：按 name+primary 配对，不能错配
const r3=buildBeats([
  {type:'tool_start',name:'glob',args:{pattern:'a'}},
  {type:'tool_start',name:'audit_tail',args:{}},
  {type:'tool',name:'audit_tail',args:{},result_preview:'{"ok":true,"count":3}',cost_ms:2},
], ()=>false);
eq('只替换匹配那行', r3.map(x=>!!x.running), [true,false]);
eq('未完成的仍在原位', [r3[0].status, r3[0].text], ['查找中','a']);

// 同名工具不同参数：不能互相顶替
const r4=buildBeats([
  {type:'tool_start',name:'file_read',args:{path:'/a.md'}},
  {type:'tool_start',name:'file_read',args:{path:'/b.md'}},
  {type:'tool',name:'file_read',args:{path:'/b.md'},result_preview:'{"ok":true}',cost_ms:1},
], ()=>false);
eq('同名不同参各自配对', r4.map(x=>[x.text,!!x.running]), [['a.md',true],['b.md',false]]);

console.log(`\n通过 ${p} · 失败 ${f}`);
process.exit(f?1:0);
