# -*- coding: utf-8 -*-
"""逐条生成可机械校验的学习题库：每项标准至少 1 题，另加法规条文题与易混辨析题。
每题带 answer_key（标准号/条号），可用 evals runner 机械判分。"""
import json, os, re, random
from collections import defaultdict

random.seed(20260908)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kb')
cat = json.load(open('catalog.json'))
apx = json.load(open('appendix.json'))

items = []
def add(cat_, q, key, ref, extra=None):
    items.append(dict(id=f'Q{len(items)+1:04d}', category=cat_, question=q,
                      answer_key=key, reference=ref, **(extra or {})))

# ---- A 类：标准号 ⇄ 名称（每条 1 题，共 209）----
for x in cat:
    add('标准定位',
        f"{x['medium']}·{x['section'] or '通用'}：开展「{x['name']}」应执行哪一项技术规范？给出标准编号与发布日期。",
        [x['code'].replace(' ', ''), x['issued']],
        f"清单 p{x['source_page']}｜{x['code']}｜{x['issued']}",
        dict(std_id=x['id'], medium=x['medium']))

# ---- B 类：反向题（标准号 → 适用场景），抽取有代表性的 60 条 ----
for x in random.sample([c for c in cat if c['year']], 60):
    add('标准识别',
        f"标准 {x['code']} 的名称是什么？属于哪个环境要素、哪种监测方式？",
        [re.sub(r'\s', '', x['name'])[:12], x['medium']],
        f"清单 p{x['source_page']}｜{x['name']}｜{x['medium']}/{x['section'] or '通用'}",
        dict(std_id=x['id']))

# ---- C 类：同名多版本辨析（现行版本判断）----
seen = set()
for x in cat:
    if not x.get('same_title_versions'):
        continue
    stem = re.sub(r'第\d+部分.*', '', x['name']).strip()
    k = (stem, x['prefix'])
    if k in seen:
        continue
    seen.add(k)
    vers = sorted(set([x['code'].replace(' ', '')] + [v.replace(' ', '') for v in x['same_title_versions']]))
    add('版本辨析',
        f"「{x['name']}」在清单中存在多个版本：{'、'.join(vers)}。引用时应如何处理？哪一版发布时间最新？",
        [max(vers, key=lambda c: c[-4:])],
        f"同名多版本，须核对现行有效性；最新发布：{max(vers, key=lambda c: c[-4:])}",
        dict(versions=vers))

# ---- D 类：HJ/T 旧序列风险题 ----
for x in [c for c in cat if c['prefix'] == 'HJ/T']:
    add('时效风险',
        f"{x['code']}《{x['name']}》属于 HJ/T 旧行业序列（{x['issued']} 发布）。执法引用前必须核实什么？",
        ['现行有效', '是否被替代'],
        f"HJ/T 为旧序列，多数已被同名 HJ 标准替代；须核对现行有效版本后引用",
        dict(std_id=x['id']))

# ---- E 类：法规条文题（附录 8 份，逐条）----
for d in apx:
    for c in d['content']:
        if not c['article']:
            continue
        body = re.sub(r'^' + c['article'], '', c['text']).strip()
        if len(body) < 18:
            continue
        add('法规条文',
            f"《{d['title']}》{c['article']}规定了什么？（要点作答）",
            [c['article']],
            f"{d['title']}·{c['article']}：{body[:160]}",
            dict(doc=d['title'], article=c['article'], full_text=body))

# ---- F 类：罚则定位（金额/情形 → 条号）----
for d in apx:
    for c in d['content']:
        t = c['text']
        if not c['article']:
            continue
        m = re.findall(r'(\d+\s*万元以上\s*\d+\s*万元以下)', t)
        if m:
            add('罚则定位',
                f"依据《{d['title']}》，出现「{re.sub(r'^' + c['article'], '', t)[:46]}…」情形的，罚款幅度是多少？依据哪一条？",
                [m[0].replace(' ', ''), c['article']],
                f"{d['title']}·{c['article']}：{m[0]}",
                dict(doc=d['title'], article=c['article']))

json.dump(dict(source='《生态环境监测技术规范清单》2026.7 + 附录8份法规全文',
               total=len(items), items=items),
          open(f'{OUT}/学习题库.json', 'w'), ensure_ascii=False, indent=1)
with open(f'{OUT}/学习题库.jsonl', 'w') as f:
    for x in items:
        f.write(json.dumps(x, ensure_ascii=False) + '\n')

from collections import Counter
print('题库总数', len(items))
for k, v in Counter(x['category'] for x in items).most_common():
    print(f'  {v:>4}  {k}')
