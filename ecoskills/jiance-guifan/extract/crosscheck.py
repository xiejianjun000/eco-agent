# -*- coding: utf-8 -*-
"""把 PDF 抽出的《生态环境监测条例》与仓库内 mee.gov.cn 权威全文逐条比对。
重点验证三处字形缺陷修复（第三十一条 / 第四十一条 及 监督管理办法第二十一条）。"""
import difflib
import json
import re

KB = '/Users/mac/Documents/deepseek/eco-agent/ecoskills/fagui-query/kb/生态环境监测条例.md'
docs = json.load(open('appendix.json'))
tiaoli = next(d for d in docs if d['title'] == '生态环境监测条例')

kb = open(KB).read()
def norm(s):
    return re.sub(r'[\s，,、。；;：:（）()〔〕【】"""'']', '', s)

# 权威库切条
kb_arts = {}
cur = None
for line in kb.split('\n'):
    m = re.fullmatch(r'(第[一二三四五六七八九十百零]+条)', line.strip())
    if m:
        cur = m.group(1)
        kb_arts[cur] = []
    elif cur:
        kb_arts[cur].append(line.strip())
kb_arts = {k: norm(''.join(v)) for k, v in kb_arts.items()}

# 按“条”聚合：抽取结果把 (一)(二) 各项拆成独立段落，需合并到所属条后再比对
spans, cur_a, buf = {}, None, []
for c in tiaoli['content']:
    if c['article']:
        if cur_a:
            spans[cur_a] = ''.join(buf)
        cur_a, buf = c['article'], [re.sub(r'^' + c['article'], '', c['text'])]
    elif cur_a:
        buf.append(c['text'])
if cur_a:
    spans[cur_a] = ''.join(buf)

same = diff = only_pdf = 0
for a, raw_body in spans.items():
    body = norm(raw_body)
    if a not in kb_arts:
        print(f'  [仅PDF有] {a}')
        only_pdf += 1
        continue
    kb_body = kb_arts[a]
    # 权威库把“第X章”标题和文末“解读”链接并入了上一条，比对时以 PDF 正文为基准做包含判定
    ratio = difflib.SequenceMatcher(None, body, kb_body).ratio()
    if ratio < 0.97 and body and (body in kb_body or kb_body.startswith(body)):
        ratio = 1.0
    if ratio >= 0.97:
        same += 1
    else:
        diff += 1
        print(f'  [差异 {ratio:.2f}] {a}')
        print(f'      PDF : {body[:90]}')
        print(f'      权威: {kb_arts[a][:90]}')
print(f'条例交叉比对：一致 {same} / 差异 {diff} / 仅PDF {only_pdf}（权威库共 {len(kb_arts)} 条）')

# 三处修复点定向核验
print('\n--- 字形缺陷修复点定向核验 ---')
for a in ('第三十一条', '第四十一条'):
    pdf = norm(spans.get(a, ''))
    kbv = kb_arts.get(a, '')
    ok = bool(pdf) and (difflib.SequenceMatcher(None, pdf, kbv).ratio() >= 0.97
                        or pdf in kbv or kbv.startswith(pdf))
    print(f'  条例{a}：{"✅ 与权威全文一致" if ok else "❌ 需人工复核"}')
gl = next(d for d in docs if d['title'] == '检验检测机构监督管理办法')
a21 = next((c['text'] for c in gl['content'] if c['article'] == '第二十一条'), '')
print(f'  监督管理办法第二十一条：{"✅ 已还原" if a21 else "❌ 缺失"} → {a21[:60]}')
