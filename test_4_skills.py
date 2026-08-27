#!/usr/bin/env python3 -B -u
"""4个xiejianjun000技能穿透式测试"""
import sys, os, json
from pathlib import Path
sys.path.insert(0, '.')
os.environ["ECO_LLM_DISABLE"] = "1"

REPORT = {"tests": []}
PASS = FAIL = 0

def log(msg): print(f"[TEST-4] {msg}")
def ok(t, d=""): 
    global PASS; PASS += 1; log(f"  ✅ {t} {d}"); REPORT["tests"].append({"name": t, "status": "PASS", "detail": d})
def fail(t, d=""): 
    global FAIL; FAIL += 1; log(f"  ❌ {t} — {d}"); REPORT["tests"].append({"name": t, "status": "FAIL", "detail": d})

BASE = Path("skills/xiejianjun000-mcp")

# 1. 执法督察评查专家团
log("=" * 60); log("【1/4 执法督察评查专家团】"); log("=" * 60)
d = BASE / "enforcement-review-expert-team"
# 检查关键文件
files = list(d.rglob("*.md")) + list(d.rglob("*.docx")) + list(d.rglob("*.json"))
ok("文件存在", f"找到{len(files)}个文档文件") if len(files) > 0 else fail("文件存在", "无文档")
# 检查分析报告
analysis = list(d.glob("*/深度梳理分析报告.md")) + list(d.glob("*/仓库梳理分析.md"))
ok("分析报告", f"{len(analysis)}份分析报告") if len(analysis) > 0 else fail("分析报告", "缺失")
# 检查playwright配置
pw = list(d.rglob("*.playwright/*")) + list(d.rglob("playwright*"))
ok("Playwright配置", f"找到{len(pw)}个相关文件") if len(pw) > 0 else fail("Playwright配置", "缺失")

# 2. 环评与排污许可技术审查知识库
log("=" * 60); log("【2/4 环评与排污许可技术审查知识库】"); log("=" * 60)
d = BASE / "eia-review-system"
# 检查79行业指南
guides = list((d / "行业技术审查指南").rglob("*.md")) if (d / "行业技术审查指南").exists() else []
ok("79行业指南", f"{len(guides)}个行业指南文件") if len(guides) >= 50 else fail("79行业指南", f"仅{len(guides)}个，期望>=50")
# 检查工具模板
templates = list((d / "工具模板").rglob("*.md")) if (d / "工具模板").exists() else []
ok("工具模板", f"{len(templates)}个模板") if len(templates) > 0 else fail("工具模板", "缺失")
# 检查法规知识库
laws = list((d / "docs/许可法规").rglob("*.md")) if (d / "docs/许可法规").exists() else []
ok("法规知识库", f"{len(laws)}个法规文件") if len(laws) > 0 else fail("法规知识库", "缺失")
# 检查两证衔接
xianjie = list((d / "docs/环评两证衔接").rglob("*.md")) if (d / "docs/环评两证衔接").exists() else []
ok("两证衔接", f"{len(xianjie)}个衔接文件") if len(xianjie) > 0 else fail("两证衔接", "缺失")
# 检查执法案例
cases = list((d / "docs/执法案例").rglob("*.md")) if (d / "docs/执法案例").exists() else []
ok("执法案例", f"{len(cases)}个案例") if len(cases) > 0 else fail("执法案例", "缺失")

# 3. 环评审查与排污许可技术审查DSH插件
log("=" * 60); log("【3/4 环评审查DSH插件】"); log("=" * 60)
d = BASE / "dsh-eia-review-plugin"
# 检查DSH配置
cordis = (d / "agent.cordis.yml").exists()
ok("DSH配置", "agent.cordis.yml存在") if cordis else fail("DSH配置", "缺失")
# 检查知识库
knowledge = list((d / "knowledge").rglob("*.json")) if (d / "knowledge").exists() else []
ok("知识库JSON", f"{len(knowledge)}个知识文件") if len(knowledge) > 0 else fail("知识库JSON", "缺失")
# 检查MCP服务器
mcp = list((d / "mcp-server").rglob("*.ts")) + list((d / "mcp-server").rglob("*.js")) if (d / "mcp-server").exists() else []
ok("MCP服务器", f"{len(mcp)}个服务端文件") if len(mcp) > 0 else fail("MCP服务器", "缺失")
# 检查省级规则热插拔
patch = (d / "cordis.patch.yml").exists()
ok("省级规则热插拔", "cordis.patch.yml存在") if patch else fail("省级规则热插拔", "缺失")

# 4. 执法监管平台固定工作流自动化
log("=" * 60); log("【4/4 执法监管平台固定工作流】"); log("=" * 60)
d = BASE / "zhengfa-zfjd-workflows-skill"
readme = (d / "README.md").exists()
ok("README存在", "OpenClaw Skill定义存在") if readme else fail("README存在", "缺失")
# 检查是否有工作流定义
workflows = list(d.rglob("*.yml")) + list(d.rglob("*.yaml")) + list(d.rglob("*.json"))
ok("工作流定义", f"{len(workflows)}个工作流文件") if len(workflows) > 0 else fail("工作流定义", "仅README，无工作流文件")

# 汇总
log("\n" + "=" * 60)
log(f"【4技能测试汇总】通过: {PASS} | 失败: {FAIL}")
log("=" * 60)

if FAIL > 0:
    log("失败项:")
    for t in REPORT["tests"]:
        if t["status"] == "FAIL":
            log(f"  - {t['name']}: {t['detail']}")

rp = Path(".eco-test/test_4_skills.json")
rp.parent.mkdir(exist_ok=True)
rp.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
log(f"报告: {rp}")
sys.exit(0 if FAIL == 0 else 1)
