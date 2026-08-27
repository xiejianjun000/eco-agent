#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二轮针对性检索：抽取判定办法/取证指引/移送标准的实质内容。"""
import sys, time
sys.path.insert(0, "/Users/mac/.qclaw/workspace-agent-6458195c")
from mcp_session import MCPClient

SSE = "http://111.230.89.107:8000/sse/"
KEY = "891aafd24879075f04efa6657c70cb625f7f83d4fd8d0336917f3757dbab9525"

QUERIES = [
    "篡改监测数据 行为 判定 停运 改动 稀释 样品",
    "伪造监测数据 凭空编造 原始记录 判定办法",
    "在线监测 设备 采样管路 干扰 稀释 弄虚作假",
    "重点排污单位 自动监测 造假 刑事 移送 标准",
    "移送拘留案卷评查 在线监测 证据 标准",
    "不正常运行 污染防治设施 认定 现场 证据",
]

c = MCPClient(SSE, KEY)
info = c.connect()
print(f"[connected] server={info}", flush=True)

with open("/tmp/case_research2.txt", "w") as f:
    for i, q in enumerate(QUERIES, 1):
        f.write("=" * 70 + "\n")
        f.write(f"# 检索词[{i}/{len(QUERIES)}]: {q}\n")
        f.write("=" * 70 + "\n")
        try:
            t0 = time.time()
            txt = c.search(q, top_k=8)
            f.write(txt + "\n")
            print(f"[{i}/{len(QUERIES)}] {q} 完成 ({time.time()-t0:.1f}s)", flush=True)
        except Exception as e:
            f.write(f"[检索失败] {e}\n")
            print(f"[{i}/{len(QUERIES)}] {q} 失败: {e}", flush=True)
        f.write("\n")
        f.flush()

c.close()
print("完成，结果写入 /tmp/case_research2.txt")
