import { summarizeResult, actionOf, objectOf, buildBeats }
  from '../turnFold.ts';
let p=0,f=0;
const eq=(n,g,w)=>{const ok=JSON.stringify(g)===JSON.stringify(w);
  console.log(`${ok?'✅':'❌'} ${n}`+(ok?'':` got=${JSON.stringify(g)} want=${JSON.stringify(w)}`)); ok?p++:f++;};

// 实测抓到的真实返回形态
eq('shell 输出行数', summarizeResult('{"ok":true,"exit":0,"stdout":"a\\nb\\nc"}'), '3 行输出');
eq('审计链条数', summarizeResult('{"ok":true,"count":3,"entries":[1,2,3]}'), '3 条');
eq('文件读取', summarizeResult('{"ok":true,"path":"/a/b/README.md","content":"x\\ny"}'), 'README.md · 2 行');
eq('glob 结果', summarizeResult('{"ok":true,"pattern":"**/README*","files":["a","b"]}'), '2 个文件');
eq('数组返回', summarizeResult('[{"name":"t1"},{"name":"t2"}]'), '2 条');
eq('失败带 error', summarizeResult('{"ok":false,"error":"命令含危险语法"}'), '失败：命令含危险语法');
eq('纯 ok', summarizeResult('{"ok":true}'), '完成');
eq('空输出', summarizeResult('{"ok":true,"stdout":""}'), '无输出');
eq('纯文本', summarizeResult('hello world'), 'hello world');
eq('空 → undefined', summarizeResult(''), undefined);
eq('非法JSON回退文本', summarizeResult('{broken'), '{broken');
eq('长文本截断', summarizeResult('x'.repeat(80)).length, 47);

console.log('\n--- 截断 JSON（真实场景：result_preview 只留 200 字符）---');
// 以下都是实测抓到的真实残片形态
eq('截断的 audit_tail 抠出 count',
   summarizeResult('{"ok": true, "count": 3, "entries": [{"ts": "2026-09-07T20:18:38", "source": "permis'),
   '3 条');
eq('截断的 glob 抠出 count',
   summarizeResult('{"ok": true, "pattern": "**/README.md", "root": "/Users/mac", "count": 20, "truncated": fal'),
   '20 条');
eq('截断但含 error', summarizeResult('{"ok": false, "error": "命令含危险语法（重定向'), '失败：命令含危险语法（重定向');
eq('截断只剩 ok:true', summarizeResult('{"ok": true, "stdout": "total 3408\\ndrwxr-x'), '完成');
eq('截断含 path', summarizeResult('{"ok": true, "path": "/a/b/notes.md", "conte'), 'notes.md');

console.log('\n--- 动作词 ---');
eq('file_read', actionOf('file_read'), '读取');
eq('MCP 前缀', actionOf('mcp__eco__x'), 'MCP 调用');
eq('未知工具用原名', actionOf('weird_tool'), 'weird_tool');
eq('空 → 执行', actionOf(undefined), '执行');

console.log('\n--- 对象名 ---');
eq('路径取 basename', objectOf({path:'/a/b/c.md'}), 'c.md');
eq('command 保留全文', objectOf({command:'ls -la /tmp'}), 'ls -la /tmp');
eq('无可用字段', objectOf({foo:1}), '');

console.log('\n--- 时间线交织 ---');
const beats=buildBeats([
  {type:'narration',text:'先看 README。'},
  {type:'tool',name:'file_read',args:{path:'/x/README.md'},result_preview:'{"ok":true,"path":"/x/README.md","content":"a"}',cost_ms:5},
  {type:'narration',text:'读到了，再查审计链。'},
  {type:'tool',name:'audit_tail',args:{},result_preview:'{"ok":true,"count":3}',cost_ms:2},
], ()=>false);
eq('节奏为 say/act 交替', beats.map(b=>b.kind), ['say','act','say','act']);
eq('工具行文案', beats[1].text, '读取 README.md');
eq('工具行摘要', beats[1].detail, 'README.md · 1 行');
eq('第二工具摘要', beats[3].detail, '3 条');

console.log('\n--- 实时态 running 行 ---');
const r1=buildBeats([
  {type:'narration',text:'先查审计链。'},
  {type:'tool_start',name:'audit_tail',args:{}},
], ()=>false);
eq('tool_start 产生 running 行', r1.map(b=>[b.kind,!!b.running]), [['say',false],['act',true]]);
eq('running 行无耗时', r1[1].ms, undefined);

// tool 到达后必须原地替换，不能出现两行
const r2=buildBeats([
  {type:'tool_start',name:'audit_tail',args:{}},
  {type:'tool',name:'audit_tail',args:{},result_preview:'{"ok":true,"count":3}',cost_ms:7},
], ()=>false);
eq('完成后仅一行', r2.length, 1);
eq('已替换为完成态', [r2[0].running, r2[0].detail, r2[0].ms], [undefined,'3 条',7]);

// 并行两个工具：各自独立替换
const r3=buildBeats([
  {type:'tool_start',name:'glob',args:{pattern:'a'}},
  {type:'tool_start',name:'audit_tail',args:{}},
  {type:'tool',name:'audit_tail',args:{},result_preview:'{"ok":true,"count":3}',cost_ms:2},
], ()=>false);
eq('并行时只替换匹配那行', r3.map(b=>!!b.running), [true,false]);
eq('未完成的仍在原位', r3[0].text, '查找文件 a');

console.log(`\n通过 ${p} · 失败 ${f}`);
process.exit(f?1:0);
