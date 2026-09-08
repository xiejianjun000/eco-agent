# -*- coding: utf-8 -*-
"""《生态环境监测技术规范清单（2026.7）》清单表抽取。
四列 x 位置全文稳定：序号≈92 / 名称≈117 / 编号≈335-370 / 日期≈451-458。
按 x 分列、按序号行的 y 锚点切行，名称与编号允许跨行续接。"""
import fitz, os, re, json

PDF = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'raw', '规范清单2026.7.pdf')
doc = fitz.open(PDF)

PART_RE = re.compile(r'^第[一二三四五六七八九十]+部分$')
SUB_RE  = re.compile(r'^[一二三四五六七八九十]+、')
NUM_RE  = re.compile(r'^\d{1,3}$')
DATE_RE = re.compile(r'^\d{4}-\d{1,2}-\d{1,2}$')
HDR     = {'序号', '标准名称', '标准编号', '发布时间'}
WATERMARK = '独立环保人公众号'

X_NO, X_NAME, X_CODE, X_DATE = 110.0, 330.0, 440.0, 999.0

def col(x):
    if x < X_NO:   return 0
    if x < X_CODE: return 1 if x < X_CODE else 2
    return 3

def col_of(x):
    # 列 x 起点实测：序号≈89-92 / 名称≈117（续行可至 330）/ 编号≈348-380 / 日期≈457
    if x < 110:  return 0
    if x < 345:  return 1
    if x < 445:  return 2
    return 3

def page_lines(pno):
    out = []
    for b in doc[pno].get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = ''.join(s["text"] for s in l["spans"]).strip()
            if t:
                out.append(dict(y=round(l["bbox"][1], 1), x=round(l["bbox"][0], 1), t=t))
    out.sort(key=lambda r: (round(r['y'] / 3), r['x']))
    return out


CODE_INLINE = re.compile(r'^(?P<name>.*?)\s*(?P<code>(?:GB|HJ|NY|SL|DZ|DL|CJ|JJG|JJF|TD|LY|SC|QX|MT|AQ|WS|RB|CH|SN|YD|JT|SY|SH|TB|HG|HY|GY)(?:/[TZ])?\s?\d[\d.\-]*)(?:\s+(?P<date>\d{4}-\d{1,2}-\d{1,2}))?$')

def split_inline(rec):
    """名称列里粘进了标准编号（甚至发布时间）时拆回各列。"""
    m = CODE_INLINE.match(rec['name'])
    if not m or not m.group('name'):
        return rec
    rec['name'] = m.group('name')
    if not rec['code']:
        rec['code'] = m.group('code')
    if not rec['date'] and m.group('date'):
        rec['date'] = m.group('date')
    return rec

def split_code_date(rec):
    m0 = re.match(r'^(?P<code>.*?\d)(?P<date>\d{4}-\d{2}-\d{2})$', (rec['code'] or '').replace(' ', ''))
    if m0 and not rec['date']:
        rec['code'] = m0.group('code'); rec['date'] = m0.group('date')
        return rec
    """编号列里粘进了发布时间时拆回。"""
    m = re.match(r'^(?P<code>\S+\s?\S*?)\s+(?P<date>\d{4}-\d{1,2}-\d{1,2})$', rec['code'] or '')
    if m:
        rec['code'] = m.group('code')
        if not rec['date']:
            rec['date'] = m.group('date')
    return rec

def build():
    recs = []
    part = sub = None
    for pno in range(2, 18):
        lines = page_lines(pno)
        pending_part = None
        body = []
        for ln in lines:
            t = ln['t']
            if t == WATERMARK:
                continue
            if PART_RE.match(t):
                pending_part = t; continue
            if pending_part:
                part = pending_part + '　' + t; sub = None; pending_part = None; continue
            if SUB_RE.match(t) and len(t) <= 14:
                sub = t; continue
            if t in HDR:
                continue
            if ln['y'] > 760:            # 页脚页码
                continue
            ln['c'] = col_of(ln['x'])
            if ln['c'] == 0 and not NUM_RE.match(t):
                continue                                  # 页码/杂项
            body.append(dict(ln, part=part, sub=sub))

        # 以序号行的 y 为锚点切分记录
        anchors = [i for i, ln in enumerate(body) if ln['c'] == 0]
        for k, ai in enumerate(anchors):
            lo = body[ai]['y'] - 12
            hi = body[anchors[k + 1]]['y'] - 12 if k + 1 < len(anchors) else 1e9
            name, code, date = [], [], None
            for ln in body:
                if ln['c'] == 0 or not (lo <= ln['y'] < hi):
                    continue
                if ln['c'] == 1: name.append(ln['t'])
                elif ln['c'] == 2: code.append(ln['t'])
                elif ln['c'] == 3 and DATE_RE.match(ln['t']): date = ln['t']
            recs.append(dict(part=body[ai]['part'], sub=body[ai]['sub'],
                             no=int(body[ai]['t']),
                             name=re.sub(r'\s+', '', ''.join(name)),
                             code=re.sub(r'\s+', ' ', ' '.join(code)).strip(),
                             date=date or '', page=pno + 1))
    recs = [split_code_date(split_inline(r)) for r in recs]
    return recs

if __name__ == '__main__':
    recs = build()
    print('records', len(recs))
    json.dump(recs, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'catalog_raw.json'), 'w'), ensure_ascii=False, indent=1)
    from collections import defaultdict
    g = defaultdict(list)
    for x in recs:
        g[(x['part'], x['sub'])].append(x['no'])
    bad = 0
    for k, v in g.items():
        exp = list(range(1, len(v) + 1))
        ok = v == exp
        bad += 0 if ok else 1
        print('OK ' if ok else 'BAD', k, len(v), '' if ok else v)
    miss = [r for r in recs if not r['name'] or not r['code'] or not r['date']]
    print('incomplete', len(miss))
    for m in miss[:10]: print('  ', m)
