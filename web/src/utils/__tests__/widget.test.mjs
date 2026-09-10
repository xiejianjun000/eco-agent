// P3-A4 show_widget 围栏解析（对标 WorkBuddy FENCE_START_REGEX / VisualizerShowWidgetView）
import { extractWidgets, stripWidgetFences, widgetKind, WIDGET_FENCE_RE } from '../widget.ts';

let p = 0, f = 0;
const ok = (n, c) => { console.log(`${c ? '✅' : '❌'} ${n}`); c ? p++ : f++; };

console.log('=== widgetKind 判定 ===');
ok('svg → svg', widgetKind('<svg viewBox="0 0 680 200"><rect/></svg>') === 'svg');
ok('html → html', widgetKind('<div class="card"><p>x</p></div>') === 'html');
ok('纯文本 → unknown', widgetKind('hello world') === 'unknown');
ok('大小写不敏感 svg', widgetKind('<SVG width="10"></SVG>') === 'svg');

console.log('\n=== extractWidgets ===');
{
  const md = '前言\n```show_widget\n<svg viewBox="0 0 680 200"><rect width="680" height="200"/></svg>\n```\n结语';
  const w = extractWidgets(md);
  ok('提取 1 个 widget', w.length === 1);
  ok('kind=svg', w[0].kind === 'svg');
  ok('marker=show_widget', w[0].marker === 'show_widget');
  ok('code 含 svg', w[0].code.includes('<svg'));
}
{
  // 多种围栏别名 + HTML
  const md = '```widget\n<div>a</div>\n```\n```visualizer_widget\n<div>b</div>\n```';
  const w = extractWidgets(md);
  ok('提取 2 个 widget', w.length === 2);
  ok('均 html', w.every((x) => x.kind === 'html'));
  ok('marker 保留别名', w[0].marker === 'widget' && w[1].marker === 'visualizer_widget');
}
{
  // show-widget 连字符别名
  const md = '```show-widget\n<svg/>\n```';
  const w = extractWidgets(md);
  ok('show-widget 别名', w.length === 1 && w[0].marker === 'show-widget');
}
{
  // 空围栏不产出
  ok('空围栏不产出', extractWidgets('```show_widget\n\n```').length === 0);
}
{
  // 普通代码围栏（非 widget）不误判
  const md = '```python\nprint(1)\n```\n```show_widget\n<svg/>\n```';
  const w = extractWidgets(md);
  ok('只提 widget 围栏，不误提代码围栏', w.length === 1 && w[0].kind === 'svg');
}

console.log('\n=== stripWidgetFences ===');
{
  const md = 'A\n```show_widget\n<svg/>\n```\nB';
  const clean = stripWidgetFences(md);
  ok('摘除围栏后正文保留', clean.includes('A') && clean.includes('B'));
  ok('围栏内容被摘除', !clean.includes('<svg') && !clean.includes('show_widget'));
}
{
  // 多围栏摘除
  const md = 'x```widget\n<a/>\n```y```widget\n<b/>\n```z';
  const clean = stripWidgetFences(md);
  ok('多围栏全部摘除', clean === 'xyz');
}

console.log('\n=== 正则对标 ===');
{
  const src = '```show_widget\n'.toLowerCase();
  WIDGET_FENCE_RE.lastIndex = 0;
  const m = WIDGET_FENCE_RE.exec(src);
  ok('FENCE_START 命中 show_widget', !!m && m[1] === 'show_widget');
}

console.log(`\n通过 ${p} · 失败 ${f}`);
process.exit(f ? 1 : 0);
