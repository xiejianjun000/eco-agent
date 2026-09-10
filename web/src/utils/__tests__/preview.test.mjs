// P3：文件预览器路由 + web 来源聚合（对标 WorkBuddy FilePreviewRouter / DetailPanel.sources）
import { rendererFor } from '../../components/DocViewer.tsx';
import { extractSources } from '../turnFold.ts';
let p = 0, f = 0;
const ok = (n, c) => { console.log(`${c ? '✅' : '❌'} ${n}`); c ? p++ : f++; };

console.log('=== 预览器路由 ===');
ok('docx → docx', rendererFor('a.docx') === 'docx');
ok('pdf → pdf', rendererFor('a.pdf') === 'pdf');
ok('xlsx/csv → sheet', rendererFor('a.csv') === 'sheet');
ok('pptx → slides（新增）', rendererFor('a.pptx') === 'slides');
ok('ppt → slides', rendererFor('a.ppt') === 'slides');
ok('mp3 → audio（新增）', rendererFor('a.mp3') === 'audio');
ok('flac → audio', rendererFor('a.flac') === 'audio');
ok('mp4 → video（新增）', rendererFor('a.mp4') === 'video');
ok('png → image', rendererFor('a.png') === 'image');
ok('html → html', rendererFor('a.html') === 'html');
ok('md → text', rendererFor('a.md') === 'text');
ok('未知 → none', rendererFor('a.bin') === 'none');

console.log('\n=== 来源聚合 extractSources ===');
{
  const trace = [{
    type: 'tool', name: 'web_search',
    args: { query: '未批先建 处罚' },
    result_preview: JSON.stringify({
      ok: true, engine: 'bing',
      results: [
        { title: '生态环境部释义', url: 'https://www.mee.gov.cn/a' },
        { title: '地方案例', url: 'https://gov.example.cn/b' },
      ],
    }),
  }];
  const s = extractSources(trace);
  ok('解析两条来源', s.length === 2);
  ok('标题/URL 正确', s[0].title === '生态环境部释义' && s[0].url.endsWith('/a'));
  ok('带 engine/query', s[0].engine === 'bing' && s[0].query === '未批先建 处罚');
}
{
  // 去重
  const trace = [{
    type: 'tool', name: 'web_search',
    result_preview: JSON.stringify({ results: [
      { title: 'A', url: 'https://x.com/1' }, { title: 'A2', url: 'https://x.com/1' } ] }),
  }];
  ok('同 URL 去重', extractSources(trace).length === 1);
}
{
  // 非 web_search 工具不收录
  const trace = [{ type: 'tool', name: 'statute_search',
    result_preview: JSON.stringify({ results: [{ title: 't', url: 'https://x.com' }] }) }];
  ok('只聚合 web_search', extractSources(trace).length === 0);
}
{
  // 截断残片：result_preview 被砍，仍能正则抠出 URL
  const frag = '{"ok":true,"engine":"bing","results":[{"title":"危险废物贮存标准解读","url":"https://www.mee.gov.cn/gb18597';
  const s = extractSources([{ type: 'tool', name: 'web_search', result_preview: frag }]);
  ok('截断残片也能抠出来源', s.length === 1 && s[0].url.startsWith('https://www.mee.gov.cn'));
  ok('残片标题保留', s[0]?.title.includes('危险废物'));
}
{
  // 非 http / 空 URL 不臆造
  const trace = [{ type: 'tool', name: 'web_search',
    result_preview: JSON.stringify({ results: [{ title: 'x', url: 'javascript:alert(1)' }] }) }];
  ok('非 http(s) 不收录', extractSources(trace).length === 0);
}

console.log(`\n通过 ${p} · 失败 ${f}`);
process.exit(f ? 1 : 0);
