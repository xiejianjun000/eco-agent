# -*- coding: utf-8 -*-
"""附录 8 份法规/规范性文件全文抽取（PDF p19-88），按条/章切分。"""
import json
import re

from extract_catalog import doc

DOCS = [  # (起始页index, 结束页index含, 标题, 文号/发布信息)
    (18, 22, '关于深化环境监测改革提高环境监测数据质量的意见', '中办国办 厅字〔2017〕35号'),
    (23, 28, '生态环境监测条例', '国务院令第820号，2025-10-31公布，2026-01-01施行'),
    (29, 33, '检验检测机构资质认定管理办法', '质检总局令第163号，2021年修改'),
    (34, 36, '检验检测机构监督管理办法', '市场监管总局令第39号，2025年第101号令修订'),
    (37, 59, '检验检测机构资质认定评审准则', '市场监管总局公告2023年第21号，2023-12-01施行'),
    (60, 66, '检验检测机构资质认定生态环境监测机构评审补充要求（2025年）', '国市监检测规〔2025〕4号，2026-01-01施行'),
    (67, 83, '《生态环境监测机构评审补充要求（2025年）》条文释义', '市监检测（司）函〔2026〕51号'),
    (84, 87, '环境监测数据弄虚作假行为判定及处理办法', '环发〔2015〕175号'),
]

WATERMARK = '独立环保人公众号'

# PDF 字形替换缺陷：条号中的“十”被以 ArialMT 的 'H' 输出（个别处为 'H^'）。
# 已比对 mee.gov.cn《生态环境监测条例》权威全文与上下文条序，判定 H→十、H^→十。
GLYPH_FIX = [
    (r'第([一二三四五六七八九])H\^([一二三四五六七八九])条', r'第\1十\2条'),
    (r'第([一二三四五六七八九])H条',                       r'第\1十条'),
    (r'第([一二三四五六七八九])H',                         r'第\1十'),
]

def fix_glyph(s):
    for pat, rep in GLYPH_FIX:
        s = re.sub(pat, rep, s)
    return s

CN_DIGITS = '一二三四五六七八九'

def _render(spans):
    """由 span 序列重建行文本，并修复该 PDF 的条号字形缺陷：
       ① “十”被替换为 ArialMT / SimSun-ExtB 的 'H'；
       ② 紧随其后的个位数字整格丢失（x 轴留一个字宽空档、无 span）。"""
    parts, prev_x1, prev_txt = [], None, ''
    for s in spans:
        t = s['text']
        if t.strip() == 'H' and s['font'] in ('ArialMT', 'SimSun-ExtB'):
            t = '十'
            x1 = s['bbox'][0] + s['size'] * 0.96   # 'H' 比 '十' 窄，按字宽推真实右界
        else:
            x1 = s['bbox'][2]
        if prev_x1 is not None and s['bbox'][0] - prev_x1 > 9.0 and prev_txt.endswith('十'):
            parts.append('□')                      # 丢失的个位数字，后续按条序还原
        parts.append(t)
        prev_x1, prev_txt = x1, t
    return ''.join(parts)


def page_text(p):
    """保留 PyMuPDF 的行切分（版面正确），仅把被拆散的条号行与其正文行重新缝合。"""
    raw = []
    for blk in doc[p].get_text("dict")["blocks"]:
        for l in blk.get("lines", []):
            t = _render(l['spans']).strip()
            if t:
                raw.append((round(l['bbox'][1], 1), round(l['bbox'][0], 1), t,
                            round(l['spans'][-1]['bbox'][2], 1), l['spans'][-1]))
    # 同一视觉行的各片段 y 存在亚像素抖动（条号常比正文低 0.2pt），
    # 直接按 y 排序会把正文排到条号之前，故先按 3pt 容差聚类成行，再行内按 x 排序。
    raw.sort()
    rows, cur = [], []
    for item in raw:
        if cur and item[0] - cur[0][0] <= 3.0:
            cur.append(item)
        else:
            if cur:
                rows.append(cur)
            cur = [item]
    if cur:
        rows.append(cur)
    raw = [it for row in rows for it in sorted(row, key=lambda r: r[1])]

    # 条号被排版拆成 '第三十□' / '条' / 正文 三段且分属不同 line 时，按 y 邻近缝合
    merged = []
    i = 0
    while i < len(raw):
        y, x, t, x1, last = raw[i]
        if re.fullmatch(r'第[一二三四五六七八九十百零]+[□]?', t):
            # 'H'→'十' 时右边界要按字宽推算，否则会把正常间距误判为丢字
            if last['text'].strip() == 'H':
                x1 = round(last['bbox'][0] + last['size'] * 0.96, 1)
            j = i + 1
            frags = []
            while j < len(raw) and abs(raw[j][0] - y) <= 4.0:
                frags.append(raw[j])
                j += 1
            for f in sorted(frags, key=lambda r: r[1]):    # 同一视觉行按 x 排序拼接
                if f[1] - x1 > 9.0 and t.endswith('十'):
                    t += '□'                               # 被字形缺陷吞掉的个位数字
                t += f[2]
                x1 = f[3]
            merged.append((y, x, t))
            i = j
            continue
        merged.append((y, x, t))
        i += 1

    lines = []
    for _, _, s in merged:
        s = s.strip()
        if not s or s == WATERMARK:
            continue
        if re.fullmatch(r'\d{1,3}', s):
            continue
        lines.append(fix_glyph(s))
    return lines


def restore_gaps(lines):
    """按条序还原被字形缺陷吞掉的个位数字（'第三十□条' → '第三十一条'）。"""
    out, last = [], 0
    for l in lines:
        m = re.match(r'^第([一二三四五六七八九十百零]*)十□条', l)
        if m:
            expect = last + 1
            tens, ones = divmod(expect, 10)
            cand = (CN_DIGITS[tens - 1] if tens > 1 else '') + '十' + (CN_DIGITS[ones - 1] if ones else '')
            l = re.sub(r'^第[一二三四五六七八九十百零]*十□条', f'第{cand}条', l)
        m2 = re.match(r'^第([一二三四五六七八九十百零]+)条', l)
        if m2:
            last = cn_to_int(m2.group(1))
        out.append(l)
    return out


def cn_to_int(s):
    if s == '十':
        return 10
    if '十' not in s:
        return CN_DIGITS.index(s) + 1 if len(s) == 1 else 0
    hi, _, lo = s.partition('十')
    return ((CN_DIGITS.index(hi) + 1) if hi else 1) * 10 + ((CN_DIGITS.index(lo) + 1) if lo else 0)


def doc_text(a, b):
    out = []
    for p in range(a, b + 1):
        out.extend(page_text(p))
    return restore_gaps(out)


ART = re.compile(r'^第[一二三四五六七八九十百零]+条')
CHAP = re.compile(r'^第[一二三四五六七八九十]+章')
NUMH = re.compile(r'^\d+(\.\d+)*\s')

def structure(lines):
    """把行流合并为段落，并识别 章/条 边界。"""
    paras = []
    buf = ''
    for l in lines:
        starts = bool(ART.match(l) or CHAP.match(l) or NUMH.match(l)
                      or re.match(r'^[（(][一二三四五六七八九十\d]+[)）]', l)
                      or re.match(r'^[一二三四五六七八九十]+、', l))
        if starts and buf:
            paras.append(buf)
            buf = l
        else:
            buf = (buf + l) if buf else l
    if buf:
        paras.append(buf)
    return paras

def build():
    out = []
    for a, b, title, meta in DOCS:
        paras = structure(doc_text(a, b))
        arts = []
        chapter = None
        for p in paras:
            if CHAP.match(p):
                chapter = p
            m = ART.match(p)
            arts.append(dict(chapter=chapter, article=m.group(0) if m else None, text=p))
        out.append(dict(title=title, meta=meta, pages=[a + 1, b + 1],
                        paragraphs=len(paras),
                        articles=sum(1 for x in arts if x['article']),
                        content=arts))
    return out

if __name__ == '__main__':
    docs = build()
    json.dump(docs, open('appendix.json', 'w'), ensure_ascii=False, indent=1)
    for d in docs:
        print(f"{d['articles']:>4} 条 / {d['paragraphs']:>4} 段  p{d['pages'][0]}-{d['pages'][1]}  {d['title']}")
