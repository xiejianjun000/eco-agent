#!/usr/bin/env python3
"""《生态环境法典》全文检索入口（RAG 知识底座）

用法：
  python3 search_codex.py --article 1086           # 按条款号精确查询
  python3 search_codex.py --query "按日计罚"        # 关键词检索，默认 top 3
  python3 search_codex.py --query "未验先投" --top 5
  python3 search_codex.py --article 1060 --json     # JSON 输出（供上层调用）
"""
import argparse
import json
import math
import os
import re
import sys

import jieba

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(HERE, "..", "data", "codex_index.json")

STOPWORDS = set("的 了 在 与 和 或 及 为 是 由 对 向 从 以 于 等 之 其 该 依照 按照 规定 本法 前款 本条 第一款 第二款 第三款 第四款 第五款 第六款 第七款 第八款 第九款 第十款 处 的； 的， 年月日 予以 应当 可以 不得 应当依法 依法 违反 有下列情形 之一的".split())

# 执法/解读术语 → 法典用语 词级同义扩展表（与索引分词粒度一致，提升缩写词与口语词召回）
EXPANSIONS = {
    "未验先投": ["同时", "设计", "施工", "投产", "生产", "验收"],
    "三同时": ["同时", "设计", "施工", "投产"],
    "未批先建": ["报批", "批准", "影响", "评价"],
    "按日计罚": ["按日", "连续", "处罚"],
    "移送拘留": ["拘留", "公安", "机关"],
    "监测造假": ["监测", "数据", "伪造", "虚假"],
    "排污许可": ["排污", "许可", "许可证"],
    "擅自拆除": ["拆除", "防治", "设施"],
    "查封扣押": ["查封", "扣押"],
    "限期改正": ["责令", "改正"],
    "处罚": ["罚款", "责令", "改正"],
    "预案": ["预案", "应急"],
    "生态损害赔偿": ["赔偿", "损害"],
}


def load_index():
    with open(INDEX_PATH, encoding="utf-8") as f:
        return json.load(f)


def tokenize(text: str) -> list:
    text = re.sub(r"第[一二三四五六七八九十百千零]+款", "", text)
    text = re.sub(r"[（(][一二三四五六七八九十]+[)）]", "", text)
    text = re.sub(r"\s+", "", text)
    return [w for w in jieba.cut(text) if w.strip() and w not in STOPWORDS and not re.fullmatch(r"[\d\W_]+", w)]


def expand_query(query: str) -> list:
    """分词并追加同义扩展词"""
    raw_tokens = tokenize(query)
    expanded = list(raw_tokens)
    for t in raw_tokens:
        if t in EXPANSIONS:
            expanded.extend(EXPANSIONS[t])
    # 整句层面的扩展（如"未验先投"出现在查询整体中）
    for k, v in EXPANSIONS.items():
        if k in query and k not in raw_tokens:
            expanded.extend(v)
    return expanded


def query_article(index, no: int):
    for d in index["docs"]:
        if d["no"] == no:
            return d
    return None


def bm25_query(index, query: str, top: int = 3):
    tokens = expand_query(query)
    if not tokens:
        return []
    meta, idf = index["meta"], index["idf"]
    k1, b, avgdl = meta["k1"], meta["b"], meta["avgdl"]
    q_tf = {t: tokens.count(t) for t in set(tokens)}

    scores = []
    for d in index["docs"]:
        dl = sum(d["tf"].values())
        s = 0.0
        for t, qf in q_tf.items():
            tf = d["tf"].get(t, 0)
            if tf == 0 or t not in idf:
                continue
            s += idf[t] * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
        if s > 0:
            scores.append((s, d))
    scores.sort(key=lambda x: x[0], reverse=True)
    return [(sc, d) for sc, d in scores[:top]]


def fmt_hit(sc, d):
    return f"[第{d['no']}条] 得分{sc:.3f}\n{d['text']}"


def main():
    parser = argparse.ArgumentParser(description="生态环境法典全文检索")
    parser.add_argument("--article", type=int, help="条款号精确查询")
    parser.add_argument("--query", help="关键词检索")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    index = load_index()

    if args.article:
        d = query_article(index, args.article)
        if args.json:
            print(json.dumps(d, ensure_ascii=False))
        else:
            print(f"[第{args.article}条]\n{d['text'] if d else '未找到该条'}")
        return

    if args.query:
        hits = bm25_query(index, args.query, args.top)
        if args.json:
            print(json.dumps([{"no": d["no"], "text": d["text"], "score": sc} for sc, d in hits], ensure_ascii=False))
        else:
            if not hits:
                print("未检索到相关条文")
            for sc, d in hits:
                print(fmt_hit(sc, d))
                print("---")
        return

    print("请使用 --article 或 --query 参数", file=sys.stderr)


if __name__ == "__main__":
    main()
