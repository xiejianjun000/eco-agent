# -*- coding: utf-8 -*-
"""把题库导出为 eco-agent evals 套件（Markdown，机械可校验）。
引用校验用两种新类型：
  std=<标准号>            → jiance-guifan lookup.py std 必须命中
  jcfa=<法规名>:<条号>     → jiance-guifan lookup.py law 必须返回条文
"""
import json
import re

ROOT = '/Users/mac/Documents/deepseek/eco-agent'
quiz = json.load(open('../kb/学习题库.json'))['items']

def esc(s):
    return re.sub(r'\s+', ' ', s).strip()

blocks = {'jiance-standards': [], 'jiance-laws': []}
n1 = n2 = 0
for q in quiz:
    if q['category'] in ('标准定位', '标准识别', '版本辨析', '时效风险'):
        code = None
        for k in q['answer_key']:
            if re.match(r'^[A-Z]{2,3}(/[TZ])?\d', k.replace(' ', '')):
                code = k.replace(' ', '')
                break
        if not code:
            continue
        n1 += 1
        blocks['jiance-standards'] += [
            f"## Q{n1} {esc(q['question'])}",
            f"维度: {q['category']}",
            f"黄金要点: {esc(q['reference'])}",
            f"引用校验: std={code}", '']
    elif q['category'] in ('法规条文', '罚则定位'):
        art = q.get('article')
        doc = q.get('doc')
        if not art or not doc:
            continue
        n2 += 1
        blocks['jiance-laws'] += [
            f"## Q{n2} {esc(q['question'])}",
            f"维度: {q['category']}",
            f"黄金要点: {esc(q['reference'])[:300]}",
            f"引用校验: jcfa={doc}:{art}", '']

hdr = {
    'jiance-standards': ['# 监测技术规范定位 评测集（穿透式逐条）', '',
                         '> 来源：《生态环境监测技术规范清单》2026.7（209 项标准逐条覆盖）。',
                         '> 引用校验 std=<标准号> 直查 jiance-guifan 知识库，标准号不存在即判虚构引用。', ''],
    'jiance-laws': ['# 监测配套法规条文 评测集（穿透式逐条）', '',
                    '> 来源：清单附录 8 份法规全文（205 条逐条覆盖）。',
                    '> 引用校验 jcfa=<法规名>:<条号> 直查全文库，条号不存在即判虚构引用。', ''],
}
for name, body in blocks.items():
    p = f'{ROOT}/evals/{name}.md'
    open(p, 'w').write('\n'.join(hdr[name] + body))
    print(p, len(body) // 5, '题')
