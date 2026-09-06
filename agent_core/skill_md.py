#!/usr/bin/env python3
"""
skill_md.py — DSH 标准 SKILL.md 生成与校验

对标 dsh-skill-creator（988hj7tczd-oss/dsh-skill-creator）的零依赖逻辑：
  - 命名：kebab-case 文法（`^[a-z0-9]+(?:-[a-z0-9]+)*$`）+ slug 生成
  - 生成：frontmatter(name/description) + body(Workflow / Inputs and outputs /
    Boundaries / Example)
  - 校验：6 项检查（存在 / 可读 / frontmatter / name+description 非空 /
    name kebab-case / body 非空）

零第三方依赖（不引 PyYAML），可独立运行。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

# kebab-case 文法：小写字母/数字，单连字符连接（DSH skill registry 强制）
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


# ═══════════════════════════════════
# 1. 命名（slug / 建议）
# ═══════════════════════════════════

def is_skill_name(name: str) -> bool:
    """是否为合法 kebab-case 技能名。"""
    return bool(name) and bool(SKILL_NAME_PATTERN.match(name))


def slugify_name(text: str) -> str:
    """自由文本 → kebab-case 标识。

    非字母数字连续段折叠为单连字符，去掉首尾连字符。
    纯中文/无可用字符时返回空串（由调用方决定回退）。
    """
    t = (text or "").lower()
    t = re.sub(r"[^a-z0-9]+", "-", t)
    t = re.sub(r"^-+|-+$", "", t)
    t = re.sub(r"-{2,}", "-", t)
    return t


def suggest_skill_name(goal: str, used: Optional[set] = None) -> str:
    """从目标句建议唯一技能名（对齐 dsh-skill-creator.suggestSkillName）。"""
    used = used or set()
    first_line = re.split(r"[\n。.；;，,]", goal or "")[0] or "custom-skill"
    base = slugify_name(first_line)
    if not base:
        base = "custom-skill"
    if len(base) > 40:
        base = base[:40].rstrip("-")
    if not base:
        base = "custom-skill"
    if base not in used:
        return base
    i = 2
    while f"{base}-{i}" in used:
        i += 1
    return f"{base}-{i}"


_CJK = re.compile(r"[\u4e00-\u9fff]")


def eco_skill_name(desc: str, used: Optional[set] = None) -> str:
    """eco 扩展：为任务描述建议唯一技能名。

    - 纯英文（无 CJK）→ 语义 slug（如 `analyze-csv-data`）
    - 含中文 / 无 ASCII → `skill-<md5[:8]>` 哈希回退（DSH kebab-case 仅 ASCII，
      中文无法拼名；dsh-skill-creator 对纯中文一律回退 'custom-skill' 会大量重名，
      故 eco 用确定性短哈希保证唯一且合法）。
    """
    used = used or set()
    text = (desc or "").strip()
    slug = slugify_name(text)
    if slug and not _CJK.search(text):
        return suggest_skill_name(text, used)
    digest = hashlib.md5((text or "eco-skill").encode("utf-8")).hexdigest()[:8]
    name = f"skill-{digest}"
    i = 2
    while name in used:
        name = f"skill-{digest}-{i}"
        i += 1
    return name


# ═══════════════════════════════════
# 2. frontmatter 解析 / 生成
# ═══════════════════════════════════

def parse_frontmatter(content: str) -> tuple[Optional[dict], str]:
    """解析 SKILL.md 顶部的 YAML frontmatter。

    返回 (frontmatter_dict | None, body)。无 frontmatter 时返回 (None, 原文)。
    手写极简解析，只取 `key: value` 行，足够 name/description 校验。
    """
    text = (content or "").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end < 0:
        return None, text
    fm_block = text[4:end]
    body = text[end + 4:].lstrip("\n")
    fm: dict = {}
    for line in fm_block.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fm, body


def format_frontmatter(name: str, description: str) -> str:
    """生成 DSH 标准 frontmatter（仅 name + description）。"""
    return f"---\nname: {name}\ndescription: {description}\n---\n\n"


# ═══════════════════════════════════
# 3. SKILL.md 渲染
# ═══════════════════════════════════

def build_trigger_description(goal: str, tools: Optional[list] = None) -> str:
    """按 DSH `Use when ...` 约定生成触发描述。"""
    tools = tools or []
    first_line = next((ln.strip() for ln in re.split(r"\n+", goal or "") if ln.strip()), goal or "")
    cleaned = re.sub(r"[。.；;，,、\s]+$", "", first_line)
    cleaned = re.sub(r"^请\s*(?:帮助|帮)?\s*", "", cleaned)
    cleaned = cleaned or goal.strip() or "执行任务"
    core = cleaned if len(cleaned) <= 140 else re.sub(r"[。.；;，,、\s]+$", "", cleaned[:140])
    tool_part = ""
    if tools:
        joined = ", ".join(f"`{t}`" for t in tools[:3])
        tool_part = f", especially when using {joined}"
    return f"Use when {core}{tool_part}."


def render_skill_md(name: str, description: str, steps: list,
                    tools: Optional[list] = None,
                    formats: Optional[list] = None) -> str:
    """渲染 SKILL.md body（对齐 dsh-skill-creator.renderSkillMarkdown）。"""
    tools = tools or []
    formats = formats or []
    sections: list = []
    sections.append(f"# {name}")
    sections.append("")
    sections.append(description)
    sections.append("")
    sections.append("## Workflow / 工作流")
    sections.append("")
    if steps:
        for idx, s in enumerate(steps, 1):
            sections.append(f"{idx}. {s}")
    else:
        sections.append("1. 明确任务输入（必要时向用户确认缺失信息）。")
        sections.append("2. 按下方输入/输出约定执行核心处理。")
        sections.append("3. 校验结果完整性并汇报产出。")
    if tools:
        sections.append("")
        sections.append(f"**Tools**: {', '.join(f'`{t}`' for t in tools)}")
    sections.append("")
    sections.append("## Inputs and outputs / 输入与输出")
    sections.append("")
    if not formats:
        sections.append("- 输入 / 输出格式按实际任务确定；关键信息缺失时先向用户确认，不擅自假设。")
    else:
        for f in formats:
            sections.append(f"- {f}")
    sections.append("")
    sections.append("## Boundaries / 边界与排除")
    sections.append("")
    sections.append("- 只在本技能声明的范围内工作；超出范围时明确说明并停止。")
    sections.append("- 不修改与任务无关的文件；改动任何文件前先读取目标内容。")
    sections.append("- 涉及持久化产物时，写出目录/格式遵循用户或项目的既有约定。")
    sections.append("")
    sections.append("## Example / 示例")
    sections.append("")
    sections.append(f"> 请用 \"{name}\" 技能处理：<输入样例>")
    sections.append("")
    sections.append("按\"工作流\"逐步执行，并在过程中报告关键中间结果与最终产出。")
    sections.append("")
    return "\n".join(sections)


def build_skill_draft(desc: str, steps: list, tools: Optional[list] = None,
                      output: str = "", used: Optional[set] = None) -> dict:
    """由任务描述 + 步骤 + 工具 + 输出，构建一份完整 SKILL.md 草稿。

    返回 {"name", "description", "content", "path_rel"}；content = frontmatter + body。
    """
    tools = [t for t in (tools or []) if t]
    name = eco_skill_name(desc, used)
    description = build_trigger_description(desc, tools)
    # 输入/输出：从描述与输出样例推导
    formats = []
    if output and output.strip():
        formats.append(f"输出示例（截断）：{output.strip()[:120]}")
    body = render_skill_md(name, description, steps, tools, formats)
    content = format_frontmatter(name, description) + body
    return {
        "name": name,
        "description": description,
        "content": content,
        "path_rel": f"{name}/SKILL.md",
    }


# ═══════════════════════════════════
# 4. 校验（6 项检查，对齐 skill_validate）
# ═══════════════════════════════════

def validate_skill_content(content: str) -> dict:
    """对 SKILL.md 文本跑 6 项检查，返回 {"valid", "errors", "warnings", "frontmatter"}。"""
    errors: list = []
    warnings: list = []

    # 1. 存在性（内容非空）
    if not content or not content.strip():
        errors.append("SKILL.md 内容为空")
        return {"valid": False, "errors": errors, "warnings": warnings, "frontmatter": None}

    # 3. frontmatter
    fm, body = parse_frontmatter(content)
    if fm is None:
        errors.append("缺少 YAML frontmatter（须以 `---` 包裹 name/description）")
        return {"valid": False, "errors": errors, "warnings": warnings, "frontmatter": None}

    # 4. name + description 非空
    name = (fm.get("name") or "").strip()
    desc = (fm.get("description") or "").strip()
    if not name:
        errors.append("frontmatter 缺少 `name`（或为空）")
    if not desc:
        errors.append("frontmatter 缺少 `description`（或为空）")

    # 5. name kebab-case
    if name and not is_skill_name(name):
        errors.append(f"name 不是合法 kebab-case：'{name}'（须匹配 {SKILL_NAME_PATTERN.pattern}）")

    # 6. body 非空
    if not body.strip():
        errors.append("body 为空（frontmatter 之后无正文）")
    else:
        # 建议项（不阻断）：标准小节齐全
        for sec in ("Workflow", "Inputs and outputs", "Boundaries", "Example"):
            if sec.lower() not in body.lower():
                warnings.append(f"body 缺少标准小节：{sec}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "frontmatter": fm,
    }


def validate_skill_file(path) -> dict:
    """校验磁盘上的 SKILL.md 文件（含存在/可读检查）。path 可为 `<dir>` 或 `<dir>/SKILL.md`。"""
    p = Path(path)
    if p.name != "SKILL.md":
        p = p / "SKILL.md"
    errors: list = []
    warnings: list = []

    # 1. 存在
    if not p.exists():
        errors.append(f"SKILL.md 不存在：{p}")
        return {"valid": False, "errors": errors, "warnings": warnings, "frontmatter": None}

    # 2. 可读
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        errors.append(f"SKILL.md 不可读：{e}")
        return {"valid": False, "errors": errors, "warnings": warnings, "frontmatter": None}

    result = validate_skill_content(content)
    result.setdefault("path", str(p))
    return result


# ===== 自测 =====

def test():
    draft = build_skill_draft(
        "编写 Python 数据分析脚本并生成报告",
        ["导入数据", "清洗数据", "分析数据", "生成报告"],
        tools=["bash", "write"],
        output="分析完成，已生成 report.md",
    )
    print("=== 生成 SKILL.md ===")
    print(draft["content"])
    print("\n=== 校验结果 ===")
    print(validate_skill_content(draft["content"]))
    assert validate_skill_content(draft["content"])["valid"] is True, "自校验失败"
    # 纯中文命名回退测试
    assert eco_skill_name("查询大气污染防治法条") == "skill-" + hashlib.md5("查询大气污染防治法条".encode()).hexdigest()[:8]
    # 英文命名测试
    assert eco_skill_name("Analyze CSV data") == "analyze-csv-data"
    print("\n[OK] skill_md 自测通过")


if __name__ == "__main__":
    test()
