/**
 * delta reset 传递测试。
 *
 * 真实 bug：api.ts 里写的是 `if (obj.delta)`，而后端撤销草稿发的是
 *   {"delta": "", "reset": true}
 * 空字符串 falsy，整个分支被跳过 → reset 永远传不到 ChatView。
 *
 * 后果：工具间旁白全部堆进最终答案气泡。实测一轮里前 5 段全是
 * 「现在从湖南生态环境厅官网查询…」「现在绘制折线图」这类过程话，
 * 答案从第 6 段才开始。刷新页面反而正常 —— 因为存储的内容是对的，
 * 只有实时渲染没吃掉撤销。这也是它长期没被发现的原因。
 */
let pass = 0, fail = 0;
const eq = (a, b, msg) => {
  const ok = JSON.stringify(a) === JSON.stringify(b);
  ok ? pass++ : (fail++, console.log(`  ✗ ${msg}\n     实际 ${JSON.stringify(a)}\n     期望 ${JSON.stringify(b)}`));
};

/** 复刻 api.ts 的分发判断 */
function dispatch(obj, onDelta) {
  if (typeof obj.delta === 'string') {
    onDelta(obj.delta, { ttft_ms: obj.ttft_ms, reset: obj.reset });
  }
}

/** 复刻 ChatView 的累积逻辑 */
function accumulate(events) {
  let content = '';
  for (const ev of events) {
    dispatch(ev, (delta, meta) => {
      content = meta?.reset ? delta : content + delta;
    });
  }
  return content;
}

console.log('1. 空 delta 携带 reset 必须被分发');
{
  let got = null;
  dispatch({ delta: '', reset: true }, (d, m) => { got = { d, reset: m.reset }; });
  eq(got, { d: '', reset: true }, '空字符串 + reset 应当分发（旧代码在此漏掉）');
}

console.log('2. 撤销后气泡只剩答案');
{
  const stream = [
    { delta: '现在从湖南生态环境厅官网查询' },
    { delta: '娄底市今日逐小时空气质量数据。' },
    { delta: '', reset: true },          // 转为 narration，撤销草稿
    { delta: '现在绘制逐小时AQI趋势折线图。' },
    { delta: '', reset: true },
    { delta: '✅ 任务完成' },
    { delta: '\n\n全市4个国控站：3个良、1个优。' },
  ];
  eq(accumulate(stream), '✅ 任务完成\n\n全市4个国控站：3个良、1个优。',
     '过程旁白必须被撤销，只留最终答案');
}

console.log('3. 无 reset 时正常累加');
{
  eq(accumulate([{ delta: 'AQI ' }, { delta: '72，' }, { delta: '等级良' }]),
     'AQI 72，等级良', '普通流式应逐块拼接');
}

console.log('4. 旧写法的回归对照');
{
  // 用旧的 if (obj.delta) 判断，重放同一串事件
  let content = '';
  for (const ev of [
    { delta: '过程话一' }, { delta: '', reset: true }, { delta: '答案' },
  ]) {
    if (ev.delta) content = ev.reset ? ev.delta : content + ev.delta;
  }
  eq(content, '过程话一答案', '旧写法确实会把过程话留在气泡里（本条固化 bug 现象）');
}

console.log('5. 缺失 delta 字段的事件不应触发');
{
  let called = 0;
  dispatch({ trace_event: { type: 'narration' } }, () => { called++; });
  eq(called, 0, 'trace_event 不带 delta，不应走 onDelta');
}

console.log(`\n通过 ${pass} · 失败 ${fail}`);
if (fail) process.exit(1);
