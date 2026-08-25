---
name: meta-interview
description: 访谈式技能冷启动——用 8 个结构化问题访谈老师傅，把隐性执法经验显性化为新技能骨架。触发词：孵化技能、访谈、老师傅经验、沉淀技能、新技能、经验显性化。对应 Greater-China-Legal 的 cold-start-interview 元技能。
risk_level: medium
version: 1.0.0
---

# /meta-interview — 访谈式技能冷启动

## 工作流程

```
Step 1: python3 ecoskills/meta-interview/scripts/interview.py <技能名> --print  查看 8 问
Step 2: 逐问军哥/老师傅（口头即可），收集答案
Step 3: python3 ecoskills/meta-interview/scripts/interview.py <技能名> --answers answers.json
        → 生成 ecoskills/<技能名>/SKILL.md 骨架（五段式）
Step 4: meta-audit 打分 → ≥70 入库；meta-test 生成用例
```

## 8 个结构化问题（问题即骨架）

1. 这个技能叫什么？一句话说明它解决什么执法场景？
2. 触发场景是什么（用户会怎么问）？触发词有哪些？
3. 老手做这件事的标准流程分几步？每步的关键动作？
4. 有没有必须查的时限/数值/表格（如 5 日内听证申请、超标倍数阶次）？
5. 最容易出错/最容易被人忽视的坑有哪些（3 条以上）？
6. 有没有绝对不能做的红线（禁用领域）？
7. 产出的标准格式是什么（文书结构/意见格式）？
8. 有没有现成的参考文件（模板/基准文件/历史案例路径）？

## 生成骨架模板

```markdown
---
name: <技能名>
description: <一句话 + 触发词：...>
risk_level: high|medium
version: 1.0.0
---

# /<技能名> — <标题>

## 核心原则
> <原则一句话>

## 工作流程
\`\`\`
Step 1: ...
\`\`\`

## 决策表
| ... |

## 禁用领域
\`\`\`
⚠️ ...
\`\`\`

## 输出格式
\`\`\`
【输出结构】
\`\`\`
```
