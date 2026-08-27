#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单连接批量检索 EHS 知识库，收集"在线监测不正常运行"办案素材。"""
import sys, time
sys.path.insert(0, "/Users/mac/.qclaw/workspace-agent-6458195c")
from mcp_session import MCPClient

SSE = "http://111.230.89.107:8000/sse/"
KEY = "891aafd24879075f04efa6657c70cb625f7f83d4fd8d0336917f3757dbab9525"

QUERIES = [
    "在线监测 不正常运行",
    "篡改 伪造 监测数据",
    "逃避监管 排放 大气",
    "自动监测 弄虚作假",
    "在线监测 证据 固定 采样",
    "不正常运行 防治设施 处罚",
    "监测造假 移送 公安 拘留",
    "在线监测 案卷 评查 要点",
]

c = MCPClient(SSE, KEY)
info = c.connect()
print(f"[connected] server={info}", flush=True)

with open("/tmp/case_research.txt", "w") as f:
    for i, q in enumerate(QUERIES, 1):
        f.write("=" * 70 + "\n")
        f.write(f"# 检索词[{i}/{len(QUERIES)}]: {q}\n")
        f.write("=" * 70 + "\n")
        try:
            t0 = time.time()
            txt = c.search(q, top_k=6)
            f.write(txt + "\n")
            print(f"[{i}/{len(QUERIES)}] {q} 完成 ({time.time()-t0:.1f}s)", flush=True)
        except Exception as e:
            f.write(f"[检索失败] {e}\n")
            print(f"[{i}/{len(QUERIES)}] {q} 失败: {e}", flush=True)
        f.write("\n")
        f.flush()

c.close()
print("全部完成，结果写入 /tmp/case_research.txt")
