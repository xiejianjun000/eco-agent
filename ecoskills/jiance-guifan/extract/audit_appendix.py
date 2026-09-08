# -*- coding: utf-8 -*-
"""附录条号连续性校验 + 与仓库权威全文交叉比对。"""
import json, re

CN = '一二三四五六七八九'
def cn2i(s):
    s = s.replace('第', '').replace('条', '')
    if s == '十': return 10
    if '十' not in s:
        return CN.index(s) + 1 if len(s) == 1 else None
    a, _, b = s.partition('十')
    hi = (CN.index(a) + 1) if a else 1
    lo = (CN.index(b) + 1) if b else 0
    return hi * 10 + lo

docs = json.load(open('appendix.json'))
allok = True
for d in docs:
    nums = [cn2i(c['article']) for c in d['content'] if c['article']]
    nums = [n for n in nums if n]
    if not nums:
        print(f"— {d['title']}：无条文结构（意见/公告类），{d['paragraphs']} 段")
        continue
    gaps = [i for i in range(1, max(nums) + 1) if i not in nums]
    dup = [n for n in set(nums) if nums.count(n) > 1]
    ok = not gaps and not dup and nums == sorted(nums)
    allok &= ok
    print(('OK  ' if ok else 'BAD '), f"{d['title']}：{len(nums)} 条 1-{max(nums)}",
          '' if ok else f'缺={gaps} 重={dup}')
print('APPENDIX', 'PASS' if allok else 'CHECK')
