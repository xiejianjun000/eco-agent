# -*- coding: utf-8 -*-
"""逐页逐条核对：抽取结果 vs PDF 原始文本（编号与日期为强校验锚点）。"""
import json
import re

from extract_catalog import doc

recs = json.load(open('catalog_raw.json'))
DATE = re.compile(r'\d{4}-\d{1,2}-\d{1,2}')

fail = 0
for pno in range(2, 18):
    raw = doc[pno].get_text()
    flat = re.sub(r'\s+', '', raw)
    page_recs = [r for r in recs if r['page'] == pno + 1]
    # 1) 页内日期个数应等于记录条数
    ndate = len(DATE.findall(raw))
    if ndate != len(page_recs):
        print(f'PAGE {pno+1} 日期数 {ndate} != 记录数 {len(page_recs)}')
        fail += 1
    # 2) 每条的 名称/编号/日期 必须能在原文压缩串中找到
    for r in page_recs:
        for field in ('name', 'code', 'date'):
            v = re.sub(r'\s+', '', r[field])
            if v and v not in flat:
                print(f'MISS p{pno+1} #{r["no"]} {field}={r[field]!r}')
                fail += 1
print('AUDIT', 'PASS' if fail == 0 else f'FAIL {fail}')
print('total records', len(recs))
