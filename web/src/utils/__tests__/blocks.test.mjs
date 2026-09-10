import { buildBeats, exitCodeOf } from '../turnFold.ts';
let p = 0, f = 0;
const ok = (n, cond) => { console.log(`${cond ? '✅' : '❌'} ${n}`); cond ? p++ : f++; };
const isErr = (s) => /失败|error|Error/.test(s || '');

console.log('=== P1-A 思考块（reasoning block）===');
{
  const b = buildBeats([
    { type: 'think_delta', round: 1, text: '先理解问题' },
    { type: 'think_delta', round: 1, text: '再拆解' },
    { type: 'tool', name: 'statute_search', args: { q: '未批先建' }, result_preview: '{"count":2}' },
  ], isErr);
  const think = b.find((x) => x.kind === 'think');
  ok('think_delta 聚合成思考块', !!think);
  ok('流式累积成完整正文', think && think.body === '先理解问题再拆解');
  ok('流式中为 running 态', think && think.running === true);
  ok('思考块出现在工具前（保持顺序）', b.findIndex((x) => x.kind === 'think') < b.findIndex((x) => x.kind === 'act'));
}
{
  const b = buildBeats([
    { type: 'think_delta', round: 1, text: '临时流式' },
    { type: 'think', round: 1, thought: '权威思考全文' },
  ], isErr);
  const thinks = b.filter((x) => x.kind === 'think');
  ok('think 权威版只留一行', thinks.length === 1);
  ok('权威版覆盖流式累积', thinks[0].body === '权威思考全文');
  ok('权威版为完成态', thinks[0].state === 'ok' && !thinks[0].running);
}

console.log('\n=== P1-B RoleSwarm 任务块（taskList block）===');
{
  const b = buildBeats([
    { type: 'think', round: 1, thought: '三角色协作 DAG：巡查 ∥ 法规 → 文书 → 总管合成' },
    { type: 'think', round: 1, thought: '巡查 Agent ∥ 法规 Agent 并行执行中…' },
    { type: 'tool', name: 'swarm_law', args: { 角色: '法规Agent' }, result_preview: '法规要点', cost_ms: 23000 },
    { type: 'tool', name: 'swarm_patrol', args: { 角色: '巡查Agent' }, result_preview: '巡查发现', cost_ms: 30000 },
    { type: 'think', round: 1, thought: '文书 Agent 起草中（基于巡查 + 法规产出）…' },
    { type: 'tool', name: 'swarm_doc', args: { 角色: '文书Agent' }, result_preview: '文书草稿', cost_ms: 15000 },
    { type: 'think', round: 1, thought: '总管仲裁合成完成', cost_ms: 8000 },
  ], isErr);
  const tasks = b.filter((x) => x.kind === 'task');
  ok('swarm 阶段聚合成单个任务块', tasks.length === 1);
  const t = tasks[0];
  ok('任务块含 4 个步骤', t.steps && t.steps.length === 4);
  ok('巡查步骤完成', t.steps[0].state === 'ok' && t.steps[0].ms === 30000);
  ok('法规步骤完成', t.steps[1].state === 'ok');
  ok('文书步骤完成', t.steps[2].state === 'ok');
  ok('总管合成完成', t.steps[3].state === 'ok');
  ok('整个任务完成', t.state === 'ok' && !t.running);
  // swarm_* 工具不应再作为普通 act 行出现
  ok('swarm_* 不混入普通工具行', !b.some((x) => x.kind === 'act' && String(x.toolName).startsWith('swarm_')));
  ok('阶段旁白并入任务块、不单独成思考行', !b.some((x) => x.kind === 'think'));
}
{
  // 仅并行阶段：巡查/法规 running，文书/合成 pending
  const b = buildBeats([
    { type: 'think', round: 1, thought: '三角色协作 DAG：巡查 ∥ 法规 → 文书 → 总管合成' },
    { type: 'think', round: 1, thought: '巡查 Agent ∥ 法规 Agent 并行执行中…' },
    { type: 'tool', name: 'swarm_law', args: {}, result_preview: '法规', cost_ms: 2000 },
  ], isErr);
  const t = b.find((x) => x.kind === 'task');
  ok('法规完成、巡查运行中', t.steps[1].state === 'ok' && t.steps[0].state === 'running');
  ok('文书/合成未开始为 pending', t.steps[2].state === 'pending' && t.steps[3].state === 'pending');
  ok('任务整体 running', t.running === true);
}

console.log('\n=== P1-C 退出码校验（exitCode）===');
ok('解析 exit_code', exitCodeOf('{"ok":true,"exit_code":0}') === 0);
ok('解析非零 exitCode', exitCodeOf('{"exitCode":2}') === 2);
ok('无退出码返回 undefined', exitCodeOf('{"ok":true}') === undefined);
ok('截断残片不猜', exitCodeOf('{"exit_code":') === undefined);
{
  const b = buildBeats([
    { type: 'tool_start', name: 'execute_code', args: { code: 'x' } },
    { type: 'tool', name: 'execute_code', args: { code: 'x' }, result_preview: '{"exit_code":2,"stderr":"boom"}' },
  ], isErr);
  const act = b.find((x) => x.kind === 'act');
  ok('非零退出码带 exitCode', act.exitCode === 2);
  ok('非零退出码判为 error 态', act.state === 'error' && act.ok === false);
}
{
  const b = buildBeats([
    { type: 'tool', name: 'execute_code', args: {}, result_preview: '{"exit_code":0}' },
  ], isErr);
  const act = b.find((x) => x.kind === 'act');
  ok('退出码 0 为 ok 态', act.state === 'ok' && act.exitCode === 0);
}

console.log('\n=== P1-D 跳过态（skipped）===');
{
  const b = buildBeats([
    { type: 'tool', name: 'generate_pptx', args: {}, result_preview: '{"skipped":true}' },
  ], isErr);
  const act = b.find((x) => x.kind === 'act');
  ok('skipped 标记识别为跳过态', act.state === 'skipped');
  ok('跳过态动词为「已跳过」', act.status === '已跳过');
}

console.log(`\n通过 ${p} · 失败 ${f}`);
process.exit(f ? 1 : 0);
