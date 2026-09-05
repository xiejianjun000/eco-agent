"""冒烟测试：验证模块导入、工具注册、核心读取/下载能力。运行: python tests/test_smoke.py"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FAIL = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not cond:
        FAIL.append(name)


# 1. 模块导入
import mee_encyclopedia.server as server  # noqa: E402

check("server 导入", True, f"version={server.__version__}" if hasattr(server, "__version__") else "")

# 2. 工具注册数量（FastMCP 内部工具表）
try:
    tools = server.mcp._tool_manager._tools
    check("工具注册", len(tools) >= 45, f"共 {len(tools)} 个工具")
    tool_names = set(tools.keys())
    check("读取工具存在", {"read_web_page", "read_air_quality", "read_mee_list", "search_policy"}.issubset(tool_names))
    check(
        "下载工具存在",
        {"download_file", "download_standard_pdf", "export_mee_list", "export_air_quality_csv", "list_downloads"}.issubset(
            tool_names
        ),
    )
    check(
        "全栏目工具存在",
        {
            "list_mee_categories",
            "read_policy_type",
            "read_policy_interpretation",
            "read_quality_report",
            "read_interact",
            "read_exposure",
            "read_english_list",
            "read_nnsa_list",
            "search_site",
            "list_policy_types",
            "list_quality_reports",
            "list_interact_sections",
            "list_nnsa_sections",
        }.issubset(tool_names),
    )
except Exception as exc:  # noqa: BLE001
    check("工具注册", False, str(exc))

# 3. 静态知识域工具
check("领域元数据", server.list_domains_meta()["domains"][0]["code"] == "air")
check("单位矩阵", server.list_agencies()["count"] >= 10)
check("流域局", server.list_river_bureaus()["count"] == 6)
check("法规导览", len(server.list_laws()["laws"]) >= 5)

# 4. RAG 知识库
server.rag_ingest(
    "t1", "环境保护法测试", "中华人民共和国环境保护法于1989年颁布，2014年修订，是环境保护领域的基础法律。", "测试源"
)
hits = server.rag_query("环境保护基础法律")
check("RAG 检索", len(hits["hits"]) > 0, f"命中 {len(hits['hits'])} 条")

# 5. 下载能力（写本地文件）
saved = server.DOWNLOADER.download_text("title,url\n测试,https://www.mee.gov.cn\n", "smoke_test.csv", save_dir=".smoke")
p = Path(saved["path"])
check("下载写盘", p.exists() and p.stat().st_size > 0, saved["path"])
check("下载列目录", len(server.list_downloads(".smoke")["files"]) >= 1)

# 6. 网络读取（容忍失败，但新增栏目逐个验证）
NET_CHECKS = [
    ("主站栏目", lambda: server.read_mee_list("要闻动态", limit=5)),
    ("业务栏目", lambda: server.read_mee_list("水生态环境", limit=5)),
    ("政策文种", lambda: server.read_policy_type("部令", limit=5)),
    ("政策解读", lambda: server.read_policy_interpretation(limit=5)),
    ("质量报告", lambda: server.read_quality_report("地表水水质月报", limit=5)),
    ("互动交流", lambda: server.read_interact("留言选登", limit=5)),
    ("曝光台", lambda: server.read_exposure("通报", limit=5)),
    ("核安全局", lambda: server.read_nnsa_list("工作动态", limit=5)),
    ("英文版", lambda: server.read_english_list("新闻发布", limit=5)),
    ("站内搜索", lambda: server.search_site("排污许可", limit=5)),
    ("栏目导览", lambda: server.list_mee_categories()),
    ("政策类型导览", lambda: server.list_policy_types()),
    ("质量报告导览", lambda: server.list_quality_reports()),
    ("互动导览", lambda: server.list_interact_sections()),
    ("核安全局导览", lambda: server.list_nnsa_sections()),
]
for name, fn in NET_CHECKS:
    try:
        result = fn()
        ok = result.get("items") if isinstance(result.get("items"), list) else bool(result)
        if isinstance(result.get("items"), list):
            ok = bool(result["items"]) or bool(result.get("note"))
        check(
            f"网络读取-{name}",
            bool(ok),
            f"items={len(result.get('items', [])) if isinstance(result.get('items'), list) else '-'}",
        )
    except Exception as exc:  # noqa: BLE001
        check(f"网络读取-{name}", False, str(exc))

print()
if FAIL:
    print(f"冒烟测试失败: {FAIL}")
    sys.exit(1)
print("全部冒烟测试通过")
