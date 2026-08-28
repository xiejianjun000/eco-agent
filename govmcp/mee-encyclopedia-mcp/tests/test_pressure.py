"""穿透式压力冒烟测试：对 46 工具做系统性真实调用。

覆盖：
1. 全栏目列表读取（60+ 栏目逐一真实抓取，含限速合规）
2. 政策文种 / 质量报告 / 互动 / 曝光 / 英文 / 核安全局 全部分类
3. 核心穿透读取（文章正文 / 政策全文 / 标准 / 实时环境质量 / 辐射）
4. 搜索（政策 / 标准 / 危废 / 站内）
5. 下载与导出（文本 / CSV / JSON / 标准 PDF）
6. RAG 知识库
7. 容错（未知栏目 / 空参数 / 非法 URL / 超长 limit）
8. 缓存压力（重复读取应命中缓存）
9. 导览类工具

运行: python tests/test_pressure.py
输出: 逐项 PASS/FAIL + 统计摘要
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import mee_encyclopedia.server as server  # noqa: E402
from mee_encyclopedia.domains import news  # noqa: E402

RESULTS = []
T0 = time.time()


def run(name: str, fn, expect: str = "items") -> None:
    t = time.time()
    try:
        r = fn()
        dt = time.time() - t
        ok = False
        detail = ""
        if isinstance(r, dict):
            if "error" in r and not r.get("items") and not r.get("hits"):
                detail = f"error={str(r['error'])[:80]}"
                ok = expect == "error_ok"
            elif expect == "items":
                items = r.get("items", [])
                ok = bool(items) or bool(r.get("note"))
                detail = f"items={len(items)} note={r.get('note', '')[:40]}"
            elif expect == "hits":
                hits = r.get("hits", [])
                ok = bool(hits)
                detail = f"hits={len(hits)}"
            elif expect == "truthy":
                ok = bool(r)
                detail = f"keys={list(r.keys())[:6]}"
            elif expect == "count":
                ok = "count" in r and r["count"] >= 1
                detail = f"count={r.get('count')}"
        else:
            ok = bool(r)
            detail = str(r)[:60]
        RESULTS.append((name, ok, dt, detail))
        tag = "PASS" if ok else "FAIL"
        print(f"[{tag}] {name} ({dt:.1f}s) {detail}")
    except Exception as exc:  # noqa: BLE001
        dt = time.time() - t
        ok = expect == "error_ok"
        RESULTS.append((name, ok, dt, f"EXC={str(exc)[:100]}"))
        print(f"[{'PASS' if ok else 'FAIL'}] {name} ({dt:.1f}s) EXC={str(exc)[:100]}")


print("=" * 70)
print("阶段 1: 全栏目列表读取（60+ 栏目，真实抓取）")
print("=" * 70)
for cat in news.CATEGORY_URLS:
    run(f"栏目[{cat}]", lambda c=cat: server.read_mee_list(c, limit=5), expect="items")

print("=" * 70)
print("阶段 2: 分类穿透读取")
print("=" * 70)
for t in server.list_policy_types()["types"]:
    run(f"政策文种[{t['type']}]", lambda x=t["type"]: server.read_policy_type(x, limit=5), expect="items")
for r in server.list_quality_reports()["reports"]:
    run(f"质量报告[{r['type']}]", lambda x=r["type"]: server.read_quality_report(x, limit=5), expect="items")
for s in server.list_interact_sections()["interact"]:
    run(f"互动[{s}]", lambda x=s: server.read_interact(x, limit=5), expect="items")
for s in server.list_interact_sections()["exposure"]:
    run(f"曝光台[{s}]", lambda x=s: server.read_exposure(x, limit=5), expect="items")
for s in server.list_nnsa_sections()["sections"]:
    run(f"核安全局[{s['section']}]", lambda x=s["section"]: server.read_nnsa_list(x, limit=5), expect="items")
for s in server.list_interact_sections()["english"]:
    run(f"英文版[{s}]", lambda x=s: server.read_english_list(x, limit=5), expect="items")
run("政策解读", lambda: server.read_policy_interpretation(limit=5), expect="items")

print("=" * 70)
print("阶段 3: 核心穿透读取")
print("=" * 70)
# 取一篇真实文章 URL 读取正文
try:
    lst = server.read_mee_list("环境要闻", limit=3)
    art_url = lst["items"][0]["url"]
    run("文章正文穿透", lambda: server.read_mee_article(art_url), expect="truthy")
    run("政策全文穿透", lambda: server.read_policy(art_url), expect="truthy")
except Exception as exc:  # noqa: BLE001
    print("[SKIP] 文章穿透（无可用 URL）", str(exc)[:80])
run("实时空气质量[北京]", lambda: server.read_air_quality("北京"), expect="truthy")
run("空气质量预报", lambda: server.read_air_forecast(), expect="truthy")
run("地表水自动监测", lambda: server.read_surface_water(), expect="truthy")
run("辐射剂量率", lambda: server.read_radiation_level(), expect="truthy")
run("标准详情[HJ 1294—2023]", lambda: server.read_standard("HJ 1294—2023"), expect="truthy")

print("=" * 70)
print("阶段 4: 搜索能力")
print("=" * 70)
run("政策检索[排污许可]", lambda: server.search_policy("排污许可", limit=5), expect="items")
run("标准检索[水质]", lambda: server.search_standard("水质", limit=5), expect="items")
run("危废类别[废矿物油]", lambda: server.search_waste_category("废矿物油"), expect="truthy")
run("站内搜索[碳排放]", lambda: server.search_site("碳排放", limit=5), expect="items")

print("=" * 70)
print("阶段 5: 下载与导出")
print("=" * 70)
run("导出栏目CSV", lambda: server.export_mee_list("要闻动态", save_dir=".pressure", fmt="csv"), expect="truthy")
run("导出栏目JSON", lambda: server.export_mee_list("要闻动态", save_dir=".pressure", fmt="json"), expect="truthy")
run("导出空气质量CSV", lambda: server.export_air_quality_csv("北京", save_dir=".pressure"), expect="truthy")
run("下载文本文件", lambda: server.download_file("https://www.mee.gov.cn/robots.txt", save_dir=".pressure"), expect="truthy")
run("下载目录列举", lambda: server.list_downloads(".pressure"), expect="count")

print("=" * 70)
print("阶段 6: RAG 知识库")
print("=" * 70)
run("RAG 灌入", lambda: server.rag_ingest("pt1", "碳排放权交易管理暂行办法测试", "全国碳排放权交易市场覆盖发电行业，实行配额管理。", "压力测试"), expect="truthy")
run("RAG 检索", lambda: server.rag_query("碳排放配额", top_k=3), expect="hits")

print("=" * 70)
print("阶段 7: 导览与元数据")
print("=" * 70)
run("栏目导览", lambda: server.list_mee_categories(), expect="truthy")
run("领域元数据", lambda: server.list_domains_meta(), expect="truthy")
run("直属单位", lambda: server.list_agencies(), expect="truthy")
run("流域海域局", lambda: server.list_river_bureaus(), expect="truthy")
run("法规导览", lambda: server.list_laws(), expect="truthy")
run("标准分类", lambda: server.list_standard_categories(), expect="truthy")
run("核安全局入口", lambda: server.list_nuclear_entrances(), expect="truthy")
run("环评入口", lambda: server.list_eia_entrances(), expect="truthy")
run("固废入口", lambda: server.list_waste_entrances(), expect="truthy")
run("许可指南", lambda: server.permit_guide(), expect="truthy")
run("网页链接提取", lambda: server.list_web_links("https://www.mee.gov.cn/", limit=10), expect="count")
run("网页正文读取", lambda: server.read_web_page("https://www.mee.gov.cn/ywdt/", max_chars=2000), expect="truthy")

print("=" * 70)
print("阶段 8: 容错测试（应优雅返回而非崩溃）")
print("=" * 70)
run("未知栏目", lambda: server.read_mee_list("不存在的栏目", limit=5), expect="truthy")
run("空关键词站内搜索", lambda: server.search_site("   ", limit=5), expect="truthy")
run("未知文种", lambda: server.read_policy_type("未知文种", limit=5), expect="truthy")
run("未知报告类型", lambda: server.read_quality_report("不存在报告", limit=5), expect="truthy")
run("超长limit", lambda: server.read_mee_list("要闻动态", limit=9999), expect="items")
run("非法URL正文", lambda: server.read_mee_article("not-a-url"), expect="error_ok")
run("外部URL正文", lambda: server.read_mee_article("https://example.com/"), expect="truthy")
run("下载非法URL", lambda: server.download_file("not-a-url", save_dir=".pressure"), expect="error_ok")

print("=" * 70)
print("阶段 9: 缓存压力（同一栏目连续两次，第二次应 cache hit）")
print("=" * 70)
r1 = server.read_mee_list("时政要闻", limit=3)
r2 = server.read_mee_list("时政要闻", limit=3)
ok = r2.get("cache") == "hit"
RESULTS.append(("缓存命中", ok, 0, f"first={r1.get('cache','-')} second={r2.get('cache','-')}"))
print(f"[{'PASS' if ok else 'FAIL'}] 缓存命中 first={r1.get('cache','-')} second={r2.get('cache','-')}")

print("=" * 70)
total = len(RESULTS)
passed = sum(1 for _, ok, _, _ in RESULTS if ok)
failed = [x for x in RESULTS if not x[0].startswith("SKIP") and not x[1]]
elapsed = time.time() - T0
print("\n===== 压力测试摘要 =====")
print(f"总调用: {total}  通过: {passed}  失败: {len(failed)}  总耗时: {elapsed:.0f}s")
if failed:
    print("失败清单:")
    for name, _, dt, detail in failed:
        print(f"  - {name} ({dt:.1f}s) {detail}")
    sys.exit(1)
print("全部通过")
