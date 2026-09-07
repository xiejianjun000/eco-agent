import { CompactType, isCompactContent, isPromptTooLongError, inferCompactType,
         extractSummaryBody } from '../../components/CompactDivider.tsx';
let pass=0,fail=0;
const eq=(n,g,w)=>{const ok=JSON.stringify(g)===JSON.stringify(w);
  console.log(`${ok?'✅':'❌'} ${n}`+(ok?'':` got=${JSON.stringify(g)} want=${JSON.stringify(w)}`)); ok?pass++:fail++;};

console.log('=== CompactType 枚举值（须与 WorkBuddy 一字不差）===');
eq('PRE_MESSAGE_AUTO', CompactType.PRE_MESSAGE_AUTO, 'pre-message-auto');
eq('USER_COMMAND', CompactType.USER_COMMAND, 'user-command');
eq('EMERGENCY_AUTO', CompactType.EMERGENCY_AUTO, 'emergency-auto');

console.log('\n=== 压缩内容识别（对标 isCompactUserPromptContent）===');
eq('<compact-request>', isCompactContent('<compact-request>x</compact-request>'), true);
eq('<conversation_history_summary>', isCompactContent('<conversation_history_summary>y</conversation_history_summary>'), true);
eq('<cb_summary>', isCompactContent('<cb_summary>z</cb_summary>'), true);
eq('Please continue...', isCompactContent('Please continue with the conversation based on the summarized context above'), true);
eq('Please summarize...', isCompactContent('Please summarize the conversation above'), true);
eq('前导空白容忍', isCompactContent('\n  <cb_summary>a</cb_summary>'), true);
eq('普通消息不误判', isCompactContent('帮我查一下娄底的案卷'), false);
eq('提到 summary 不误判', isCompactContent('这份 summary 写得不错'), false);
eq('空串', isCompactContent(''), false);

console.log('\n=== 上下文超限识别（对标 PROMPT_TOO_LONG_META_RE）===');
eq('prompt_too_long', isPromptTooLongError('error: prompt_too_long'), true);
eq('prompt-too-long', isPromptTooLongError('prompt-too-long'), true);
eq('context_length', isPromptTooLongError('context_length exceeded'), true);
eq('maximum_context', isPromptTooLongError('maximum_context reached'), true);
eq('空格分隔不匹配（与 WorkBuddy 原正则一致）', isPromptTooLongError('maximum context'), false);
eq('payload_too_large', isPromptTooLongError('payload_too_large'), true);
eq('普通错误不误判', isPromptTooLongError('connection refused'), false);

console.log('\n=== 类型推断 ===');
eq('超限 → EMERGENCY', inferCompactType('<cb_summary>context_length exceeded</cb_summary>'), 'emergency-auto');
eq('显式请求 → USER_COMMAND', inferCompactType('<compact-request/>'), 'user-command');
eq('默认 → PRE_MESSAGE_AUTO', inferCompactType('<cb_summary>ok</cb_summary>'), 'pre-message-auto');

console.log('\n=== 摘要正文提取 ===');
eq('剥 cb_summary 标签', extractSummaryBody('<cb_summary>正文内容</cb_summary>'), '正文内容');
eq('剥 history 标签', extractSummaryBody('<conversation_history_summary>abc</conversation_history_summary>'), 'abc');
eq('无标签原样返回', extractSummaryBody('  裸文本  '), '裸文本');

console.log(`\n通过 ${pass} · 失败 ${fail}`);
process.exit(fail?1:0);
