---
name: meta-audit
description: 技能自审——对 ecoskills 里的技能做质量审计（frontmatter/触发词/风险标注/引用完整性/禁用领域），输出评分卡。触发词：技能自审、audit 技能、技能质量、审查技能。对应 Greater-China-Legal 的 self-audit 元技能。
risk_level: medium
version: 1.0.0
---

# /meta-audit — 技能自审

## 工作流程

```
Step 1: 运行 python3 ecoskills/meta-audit/scripts/audit.py <技能名>
Step 2: 按评分卡逐项修复（≤70 分不入库）
Step 3: 高危技能（涉处罚/移送）复核"禁用领域"块是否齐备
```

## 评分卡（脚本内置，10 项 × 10 分）

| 项 | 检查点 |
|----|--------|
| frontmatter name | 存在且非空 |
| description 完整 | ≥20 字且含触发场景 |
| 触发词 | description 含"触发词"或在 frontmatter 显式 trigger_phrases |
| 风险标注 | risk_level 字段存在（high 必须含"禁用领域"块） |
| 工作流 | 含 Step 序列或编号流程 |
| 决策表/清单 | 至少一张表格（时限/要素/阶次） |
| 输出格式 | 含输出模板块 |
| 引用纪律 | 提示核实出处（如 statute_lookup / [待确认]） |
| 引用完整性 | 文中引用的 references/ 或 scripts/ 路径真实存在 |
| 篇幅合理 | 正文 300-8000 字符 |

## 用法

```bash
python3 ecoskills/meta-audit/scripts/audit.py atom-discretion      # 单技能
python3 ecoskills/meta-audit/scripts/audit.py --all                # 全库体检
python3 ecoskills/meta-audit/scripts/audit.py --all --json         # JSON 输出（CI）
```
