import { computeAnchors, buildSegments, normalizeItems, bodyTextLength, assistantEndTime,
         cleanNarration, dedupeAdjacent } from '../turnFold.ts';
let p=0,f=0;
const eq=(n,g,w)=>{const ok=JSON.stringify(g)===JSON.stringify(w);
  console.log(`${ok?'✅':'❌'} ${n}`+(ok?'':`\n     got=${JSON.stringify(g)}\n    want=${JSON.stringify(w)}`)); ok?p++:f++;};

const T=(text)=>({text});            // 正文
const X=()=>({});                    // 工具（无正文）
const txt=(c)=>c.text;

console.log('=== 1. 锚点选择（所有最长 + 最后一条）===');
eq('空输入无锚点', computeAnchors(normalizeItems([]),txt).length, 0);
eq('全是工具无锚点', computeAnchors(normalizeItems([X(),X()]),txt).length, 0);
eq('单条正文即锚点', computeAnchors(normalizeItems([T('abc')]),txt).map(i=>i.index), [0]);
// 最长 + 最后：'aaaa'(最长,idx0) 与 'bb'(最后,idx2)
eq('最长+最后都入选',
   computeAnchors(normalizeItems([T('aaaa'),X(),T('bb')]),txt).map(i=>i.index), [0,2]);
// 并列最长全部入选（源码是 === maxLength，不是取第一条）
eq('并列最长全入选',
   computeAnchors(normalizeItems([T('aaa'),T('aaa'),T('b')]),txt).map(i=>i.index), [0,1,2]);
eq('最长恰为最后一条时不重复',
   computeAnchors(normalizeItems([T('a'),T('bbbb')]),txt).map(i=>i.index), [1]);
eq('空白正文不算', computeAnchors(normalizeItems([T('   '),T('x')]),txt).map(i=>i.index), [1]);

console.log('\n=== 2. bodyTextLength ===');
eq('trim 后计长', bodyTextLength('  ab  '), 2);
eq('undefined → 0', bodyTextLength(undefined), 0);
eq('null → 0', bodyTextLength(null), 0);

console.log('\n=== 3. 分段（hidden / anchor / process）===');
// 场景：工具 → 旁白A → 工具x2 → 旁白B(最长) → 工具 → 旁白C
// 按 WorkBuddy 语义，只有「最长(B)」和「最后(C)」是锚点，A 落选并入 leading hidden。
const seq=[X(),T('A'),X(),X(),T('BBBB'),X(),T('C')];
const segs=buildSegments(seq,txt);
eq('段类型序列', segs.map(s=>s.kind), ['hidden','anchor','process','anchor']);
eq('A 因非最长非最后而并入 hidden', segs[0].items.map(i=>i.index), [0,1,2,3]);
eq('锚点 B（最长）', segs[1].items.map(i=>i.index), [4]);
eq('B 与 C 之间 1 个工具', segs[2].items.map(i=>i.index), [5]);
eq('锚点 C（最后）', segs[3].items.map(i=>i.index), [6]);
eq('最后锚点后不再产生 process 段', segs.filter(s=>s.kind==='process').length, 1);

// 等长旁白（eco 实际形态：每行都是一句话，长度相近）
// 只有并列最长者与最后一条入选 —— 这正是下面 equalizeAnchors 要解决的问题。
const even=[T('看接口'),X(),T('写文件'),X(),T('部署')];
eq('等长旁白仅并列最长+最后入选',
   computeAnchors(normalizeItems(even),txt).map(i=>i.index), [0,2,4]);
const uneven=[T('先看 helper 签名和可复用函数'),X(),T('写完了'),X(),T('部署')];
eq('长度不齐时短旁白落选',
   computeAnchors(normalizeItems(uneven),txt).map(i=>i.index), [0,4]);

console.log('\n=== 4. hoist 排除 ===');
const seq2=[T('AA'),X(),{widget:1},T('BB')];  // 等长→两条都是锚点，中间才有 process 段
const segs2=buildSegments(seq2,c=>c.text,c=>!!c.widget);
const proc=segs2.find(s=>s.kind==='process');
eq('过程段排除 hoisted widget', proc.items.map(i=>i.index), [1]);

console.log('\n=== 5. 无锚点时返回空（不产生裸 process 段）===');
eq('全工具 → 空分段', buildSegments([X(),X()],txt).length, 0);

console.log('\n=== 6. 轮次结束时间（issue #59036 修复语义）===');
eq('finishTime 优先', assistantEndTime({finishTime:200,createTime:100}), 200);
eq('缺 finishTime 回退 createTime', assistantEndTime({createTime:100}), 100);
eq('都没有 → undefined', assistantEndTime({}), undefined);

console.log('\n=== 7. 旁白清洗（实测缺陷兜底）===');
eq('正常旁白保留', cleanNarration('接口清楚了。现在三个工具并行开发。'), '接口清楚了。现在三个工具并行开发。');
// 实测模型真写出过这句 —— 系统自述，必须拦
eq('拦「上一轮…超时中断」', cleanNarration('上一轮这个任务因 LLM 超时中断了。这次先 ls。'), null);
eq('拦「重试第2次」', cleanNarration('重试第2次，继续读文件'), null);
eq('拦提示词自述', cleanNarration('按提示词规则我要先说明'), null);
eq('拦空泛套话', cleanNarration('正在处理'), null);
eq('拦「让我看看」', cleanNarration('让我看看。'), null);
eq('空串 → null', cleanNarration(''), null);
eq('非字符串 → null', cleanNarration(undefined), null);
eq('超长截断', cleanNarration('x'.repeat(200)).length, 121);
eq('相邻去重', dedupeAdjacent(['a','a','b','b','a']), ['a','b','a']);
eq('无重复不变', dedupeAdjacent(['a','b']), ['a','b']);

console.log(`\n通过 ${p} · 失败 ${f}`);
process.exit(f?1:0);
