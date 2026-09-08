# -*- coding: utf-8 -*-
"""生成 eco-agent 可检索知识库：JSON / JSONL / Markdown 速查表 / 法规全文。"""
import json, os, re
from collections import defaultdict

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kb')
os.makedirs(OUT, exist_ok=True)

cat = json.load(open('catalog.json'))
apx = json.load(open('appendix.json'))

SRC = '《生态环境监测技术规范清单》2026年7月版（夸克网盘分享原件，88页）'

# ---------- 1. 结构化目录 ----------
json.dump(dict(source=SRC, total=len(cat), items=cat),
          open(f'{OUT}/监测技术规范清单_结构化.json', 'w'), ensure_ascii=False, indent=1)

with open(f'{OUT}/监测技术规范清单.jsonl', 'w') as f:
    for x in cat:
        f.write(json.dumps(x, ensure_ascii=False) + '\n')

# ---------- 2. Markdown 速查表 ----------
by_medium = defaultdict(lambda: defaultdict(list))
for x in cat:
    by_medium[x['medium']][x['section'] or '（不分手工/自动）'].append(x)

ORDER = ['水和废水', '环境空气和废气', '噪声与振动', '土壤和沉积物', '固体废物',
         '核辐射与电磁辐射', '海洋', '生物', '其他监测技术规范']

lines = [
    '# 生态环境监测技术规范清单（2026.7）· 速查表', '',
    f'> 来源：{SRC}',
    f'> 共收录 **{len(cat)}** 项监测技术规范/标准，按环境要素与监测方式分类。',
    '> 标准原文以发布机关正式文本为准；本表用于快速定位标准号与适用范围。', '',
    '## 使用方式', '',
    '- 按环境要素定位章节 → 按“手工/自动/自行监测/验收”细分 → 取标准号。',
    '- **GB 开头为强制性国家标准**，HJ/T 为旧行业序列（多数已被同名 HJ 标准替代，引用前须核对现行有效性）。',
    '- 表中「⚠️同名多版本」标记表示该标准存在同名不同年份版本，引用前必须确认现行版本。', '',
]

for med in ORDER:
    if med not in by_medium:
        continue
    items = [i for sec in by_medium[med].values() for i in sec]
    lines += [f'## {med}（{len(items)} 项）', '']
    for sec, arr in by_medium[med].items():
        lines += [f'### {sec}', '', '| # | 标准名称 | 标准编号 | 发布时间 | 备注 |', '|---|---|---|---|---|']
        for x in sorted(arr, key=lambda i: i['seq_in_section']):
            note = []
            if x['mandatory']:
                note.append('**强制性国标**')
            if x['prefix'] == 'HJ/T':
                note.append('旧序列')
            if x.get('same_title_versions'):
                note.append('⚠️同名多版本' + ('（最新）' if x.get('is_newest_of_title') else ''))
            if x['kind'] == '规范性文件':
                note.append('文号发布')
            lines.append(f"| {x['seq_in_section']} | {x['name']} | {x['code']} | {x['issued']} | {'；'.join(note)} |")
        lines.append('')

open(f'{OUT}/监测技术规范清单_速查表.md', 'w').write('\n'.join(lines))

# ---------- 3. 附录法规全文 ----------
apx_lines = ['# 生态环境监测配套法规与规范性文件全文（清单附录）', '',
             f'> 来源：{SRC} 第十部分附录（PDF p19–88）',
             '> 说明：原 PDF 存在字形替换缺陷（条号“十”被输出为 H、个别个位数字丢失），',
             '> 已按字形几何与条序还原，并与 mee.gov.cn 权威全文交叉比对（《生态环境监测条例》49/49 条一致）。', '']
for d in apx:
    apx_lines += [f"## {d['title']}", '', f"> {d['meta']}　｜　原件页码 p{d['pages'][0]}–{d['pages'][1]}", '']
    chap = None
    for c in d['content']:
        if c['chapter'] and c['chapter'] != chap:
            chap = c['chapter']
            apx_lines += [f'### {chap}', '']
        apx_lines += [c['text'], '']
open(f'{OUT}/监测配套法规全文.md', 'w').write('\n'.join(apx_lines))

json.dump(apx, open(f'{OUT}/监测配套法规全文.json', 'w'), ensure_ascii=False, indent=1)

# ---------- 4. 索引：标准号 → 条目 ----------
idx = {x['code'].replace(' ', ''): dict(name=x['name'], medium=x['medium'],
                                        section=x['section'], issued=x['issued'],
                                        id=x['id'], page=x['source_page'])
       for x in cat}
json.dump(idx, open(f'{OUT}/标准号索引.json', 'w'), ensure_ascii=False, indent=1)

for p in sorted(os.listdir(OUT)):
    print(f'{os.path.getsize(os.path.join(OUT, p)):>9,}  {p}')
