#!/usr/bin/env python3
"""构建《生态环境法典》1242 条 BM25 检索索引（RAG 知识底座）

用法：python3 build_index.py [--src codex_articles.json路径]
默认读取 ../data/codex_articles.json，输出 ../data/codex_index.json
"""
import argparse
import json
import math
import os
import re
import sys

import jieba

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC = os.path.join(HERE, "..", "data", "codex_articles.json")
OUT_PATH = os.path.join(HERE, "..", "data", "codex_index.json")

# 法律条文常用停用词（仅过滤纯虚词，保留实质词汇）
STOPWORDS = set("的 了 在 与 和 或 及 为 是 由 对 向 从 以 于 等 之 其 该 依照 按照 规定 本法 前款 本条 第一款 第二款 第三款 第四款 第五款 第六款 第七款 第八款 第九款 第十款 处 的； 的， 年月日 予以 应当 可以 不得 应当依法 依法 违反 有下列情形 之一的".split())


def clean_text(text: str) -> str:
    """去除条文中的款项编号与空白，保留正文"""
    text = re.sub(r"第[一二三四五六七八九十百千零]+款", "", text)
    text = re.sub(r"[（(][一二三四五六七八九十]+[)）]", "", text)
    text = re.sub(r"\s+", "", text)
    return text


def tokenize(text: str) -> list:
    words = [w for w in jieba.cut(clean_text(text)) if w.strip() and w not in STOPWORDS and not re.fullmatch(r"[\d\W_]+", w)]
    return words


def build():
    parser = argparse.ArgumentParser(description="构建生态环境法典 BM25 索引")
    parser.add_argument("--src", default=DEFAULT_SRC, help="codex_articles.json 路径")
    args = parser.parse_args()
    src = args.src

    with open(src, encoding="utf-8") as f:
        articles = json.load(f)

    docs = []          # 每条约文的原文与分词
    for art_no in sorted(articles.keys(), key=int):
        text = articles[art_no]
        tokens = tokenize(text)
        docs.append({"no": int(art_no), "text": text, "tokens": tokens})

    # 文档频率
    df = {}
    for d in docs:
        for t in set(d["tokens"]):
            df[t] = df.get(t, 0) + 1

    N = len(docs)
    avgdl = sum(len(d["tokens"]) for d in docs) / max(N, 1)

    # BM25 参数
    k1, b = 1.5, 0.75
    idf = {t: math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5)) for t in df}

    # 保存索引（doc 级 tf 以节省空间；搜索时在线计算 BM25）
    index = {
        "meta": {
            "name": "生态环境法典全文检索索引",
            "article_count": N,
            "avgdl": avgdl,
            "k1": k1,
            "b": b,
            "source": "内蒙古自治区生态环境厅转载全文，1242 条",
        },
        "idf": idf,
        "docs": [
            {
                "no": d["no"],
                "text": d["text"],
                "tf": {t: d["tokens"].count(t) for t in set(d["tokens"])},
            }
            for d in docs
        ],
    }
    out_path = OUT_PATH
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    print(f"索引构建完成: {N} 条 / {len(idf)} 词项 -> {out_path}")


if __name__ == "__main__":
    build()
