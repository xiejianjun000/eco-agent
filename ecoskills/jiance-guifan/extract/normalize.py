# -*- coding: utf-8 -*-
"""标准号解析、分类、替代关系推断，产出规范化知识库条目。"""
import json, re
from collections import defaultdict

recs = json.load(open('catalog_raw.json'))

PREFIX_MEANING = {
    'GB': '国家标准（强制）', 'GB/T': '国家标准（推荐）', 'GB/Z': '国家标准化指导性技术文件',
    'HJ': '国家生态环境标准', 'HJ/T': '国家环境保护行业标准（旧序列，逐步被 HJ 替代）',
    'NY': '农业行业标准', 'NY/T': '农业行业推荐标准',
    'SL': '水利行业标准', 'SL/T': '水利行业推荐标准',
    'DZ/T': '地质矿产行业推荐标准', 'HY/T': '海洋行业推荐标准',
    'DL/T': '电力行业推荐标准', 'CJ/T': '城镇建设行业推荐标准',
    'JJF': '国家计量技术规范', 'JJG': '国家计量检定规程',
    'TD/T': '土地管理行业推荐标准', 'LY/T': '林业行业推荐标准',
    'SC/T': '水产行业推荐标准', 'QX/T': '气象行业推荐标准',
    'MT/T': '煤炭行业推荐标准', 'AQ/T': '安全生产行业推荐标准',
    'WS/T': '卫生行业推荐标准', 'RB/T': '认证认可行业推荐标准',
    'CH/T': '测绘行业推荐标准', 'SN/T': '出入境检验检疫行业推荐标准',
    'GY/T': '广播电影电视行业推荐标准', 'JT/T': '交通运输行业推荐标准',
    'TB/T': '铁道行业推荐标准', 'HG/T': '化工行业推荐标准',
    'SY/T': '石油天然气行业推荐标准', 'SH/T': '石油化工行业推荐标准',
    'YD/T': '通信行业推荐标准', 'DB': '地方标准',
}

CODE_RE = re.compile(r'^(?P<pre>[A-Z]{2,3}(?:/[TZ])?)\s*(?P<num>[\d.]+)-(?P<year>\d{4})$')

def parse_code(code):
    c = re.sub(r'\s+', ' ', code).strip()
    m = CODE_RE.match(c.replace(' ', ''))
    if m:
        return dict(kind='标准', prefix=m.group('pre'), serial=m.group('num'),
                    year=int(m.group('year')),
                    family=f"{m.group('pre')} {m.group('num').split('.')[0]}",
                    prefix_meaning=PREFIX_MEANING.get(m.group('pre'), '其他标准序列'),
                    mandatory=(m.group('pre') == 'GB'))
    return dict(kind='规范性文件', prefix=None, serial=None, year=None,
                family=None, prefix_meaning='部委规范性文件（文号发布，非标准号）',
                mandatory=False)

MEDIUM = {
    '第一部分': '水和废水', '第二部分': '环境空气和废气', '第三部分': '噪声与振动',
    '第四部分': '土壤和沉积物', '第五部分': '固体废物', '第六部分': '核辐射与电磁辐射',
    '第七部分': '海洋', '第八部分': '生物', '第九部分': '其他监测技术规范',
}

out = []
for i, r in enumerate(recs, 1):
    part_key = r['part'].split('\u3000')[0]
    info = parse_code(r['code'])
    method = None
    if r['sub']:
        if '手工' in r['sub']: method = '手工监测'
        elif '自动' in r['sub']: method = '自动监测'
        elif '自行监测' in r['sub']: method = '自行监测技术指南'
        elif '验收' in r['sub']: method = '竣工环保验收技术规范'
        else: method = '其他'
    out.append(dict(
        id=f'JCGF-{i:04d}',
        medium=MEDIUM.get(part_key, part_key),
        part=r['part'], section=r['sub'], method=method,
        seq_in_section=r['no'], name=r['name'], code=r['code'],
        issued=r['date'], source_page=r['page'], **info))

# 同族（同一标准不同年份/分册）关系
fam = defaultdict(list)
for x in out:
    if x['family']:
        fam[x['family']].append(x)
for f, items in fam.items():
    if len(items) > 1:
        for x in items:
            x['family_members'] = sorted(
                (y['code'] for y in items if y['code'] != x['code']))

# 疑似替代：同名主干 + 同前缀族 + 年份更新（仅提示，不作结论）
def stem(n):
    return re.sub(r'第\d+部分.*|（试行）|\(试行\)', '', n).strip()
by_stem = defaultdict(list)
for x in out:
    if x['year']:
        by_stem[(stem(x['name']), x['prefix'].replace('/T', '').replace('/Z', ''))].append(x)
for k, items in by_stem.items():
    if len(items) > 1:
        newest = max(i['year'] for i in items)
        for x in items:
            others = [i['code'] for i in items if i['code'] != x['code']]
            x['same_title_versions'] = sorted(others)
            x['is_newest_of_title'] = (x['year'] == newest)

json.dump(out, open('catalog.json', 'w'), ensure_ascii=False, indent=1)

# 统计
print('条目', len(out))
from collections import Counter
print('\n按要素：')
for k, v in Counter(x['medium'] for x in out).most_common():
    print(f'  {v:>4}  {k}')
print('\n按序列：')
for k, v in Counter(x['prefix'] or '规范性文件' for x in out).most_common():
    print(f'  {v:>4}  {k}  {PREFIX_MEANING.get(k, "")}')
print('\n强制性国标 GB：', sum(1 for x in out if x['mandatory']))
print('同名多版本条目：', sum(1 for x in out if x.get('same_title_versions')))
yrs = [x['year'] for x in out if x['year']]
print('发布年份跨度：', min(yrs), '-', max(yrs))
print('近5年(2021+)：', sum(1 for y in yrs if y >= 2021))
