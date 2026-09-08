"""结晶质量闸回归测试 —— 防"对话原话变技能"。

背景：2026-09-09 清理了 7 个 auto_learn 技能。它们的 description 直接是
用户原话（"到本地电脑去找"、"退出后，我不会重新启动你"），工作流是 6 行
重复的 shell_run，meta-audit 仅 40-50 分（及格线 70），无一被复用
（usage_count 全为 1）。

根因：validate_skill_content 只校验**结构**（frontmatter/kebab-case/非空），
一句用户原话结构完全合法，照样落盘。assess_skill_value 补的是**内容价值**判断。

本测试用真实历史坏样本作 fixture，并用真技能描述守护误伤边界。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from agent_core.skill_md import (  # noqa: E402
    assess_skill_value,
    build_skill_draft,
    is_degenerate_workflow,
    validate_skill_content,
)

# 被清理的 8 个 auto_learn 技能真实数据（description 原文 + steps）
HISTORICAL_BAD = [
    ("到本地电脑去找", ["shell_run"] * 6),
    ("没要你写检查表格？", ["shell_run", "shell_run", "file_read"]),
    ("那为什么这个mcp服务器登录不了？", ["shell_run", "shell_run", "execute_code",
                                        "shell_run", "execute_code", "shell_run"]),
    ("退出后，我不会重新启动你", ["shell_run"] * 6),
    ("作为人类操作员，我授权你在工作区目录里直接复跑回归测试（不用沙箱），"
     "验证补丁是否真的有效。如果是沙箱环境问题导致的 ma",
     ["shell_run", "shell_run", "shell_run", "file_read", "shell_run", "shell_run"]),
    ("执行以下动作，不要核查了：\n\n1. 用 execute_code 或 shell_run，在工作区目",
     ["shell_run", "execute_code", "shell_run", "execute_code", "shell_run", "shell_run"]),
    ("Loop 2 Step 6 失败原因已定位：测试代码传了 str 而不是 Path。现在你直接做：\n",
     ["shell_run"] * 6),
    ("查审计链最后3条，再用 glob 找所有 README，再读 eco-agent README 前 ",
     ["audit_tail", "glob", "file_read"]),
]

# 真技能描述（取自 ecoskills/ 现存技能），必须全部放行。
# 注意 eia-router 含"你"、code-review 含"?"——不能靠禁用这些字符来过滤。
REAL_SKILL_DESCS = [
    "环评云助手（mcp.eiacloud.com）四台 MCP 的调度手册。当问题涉及环评、排污许可、"
    "法规导则检索、排放限值核算、官方答复口径，先读本手册选服务器再发起调用。",
    'Review the changes since a fixed point (commit, branch, tag, or merge base)?',
    "生态环境监测技术规范清单速查——209 项监测标准按要素与监测方式定位标准号。",
    "安装新技能/新插件前安全检查、审查脚本风险、审计技能权限时使用。",
    "湖南生态环境智慧执法办案系统自动化操作。支持登录、查询案卷台账、批量下载案卷PDF。",
]


@pytest.mark.parametrize("desc,steps", HISTORICAL_BAD)
def test_historical_bad_samples_are_rejected(desc, steps):
    """8 个真实坏样本必须全部被拦截。"""
    r = assess_skill_value(desc, steps)
    assert r["worth"] is False, f"未拦截: {desc[:40]}"
    assert r["reasons"], "拦截必须给出理由"


@pytest.mark.parametrize("desc", REAL_SKILL_DESCS)
def test_real_skills_are_not_false_positives(desc):
    """真技能描述不得误伤（配正常多样工作流）。"""
    r = assess_skill_value(desc, ["kb_search", "file_read", "lookup"])
    assert r["worth"] is True, f"误伤真技能: {desc[:40]} | {r['reasons']}"


def test_degenerate_workflow_detection():
    assert is_degenerate_workflow(["shell_run"] * 6) is True
    assert is_degenerate_workflow(["a", "a", "b", "b"]) is True      # 去重恰好半数
    assert is_degenerate_workflow(["a", "b", "c"]) is False
    assert is_degenerate_workflow(["a", "a", "b", "c"]) is False     # 去重超半数
    assert is_degenerate_workflow([]) is False
    assert is_degenerate_workflow(["a"]) is False


def test_structural_validation_alone_would_pass_bad_samples():
    """回归锚点：坏样本的结构校验是**通过**的。

    这正是当初 7 个垃圾技能能落盘的原因——证明价值闸不可被结构校验替代。
    """
    desc, steps = HISTORICAL_BAD[0]
    draft = build_skill_draft(desc, steps, tools=steps, output="某次输出")
    structural = validate_skill_content(draft["content"])
    assert structural["valid"] is True, "前提失效：坏样本结构本就该合法"
    assert assess_skill_value(desc, steps)["worth"] is False, "价值闸必须拦下它"


def test_reasons_are_actionable():
    r = assess_skill_value("退出后，我不会重新启动你", ["shell_run"] * 6)
    joined = "；".join(r["reasons"])
    assert "一次性对话指令" in joined
    assert "工作流退化" in joined
