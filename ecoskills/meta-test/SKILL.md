---
name: meta-test
description: 技能自测——从技能内容自动生成测试用例集（问题+黄金要点+引用校验项），落盘 evals/，机械校验项可本地跑通，可选 LLM-as-Judge。触发词：技能自测、生成测试用例、技能用例、test 技能、评测集。对应 Greater-China-Legal 的 auto-test 元技能。
risk_level: medium
version: 1.0.0
---

# /meta-test — 技能自测

## 工作流程

```
Step 1: python3 ecoskills/meta-test/scripts/test.py <技能名>
        → 解析 SKILL.md 的表格/时限/条款/步骤 → 生成 evals/<技能名>-cases.md
Step 2: 用例三类：
        ① 知识题（决策表数字/时限 → 问答，黄金要点=表内值）
        ② 应用场景题（触发词场景 → 期望调用流程/输出格式）
        ③ 机械校验项（引用条文存在性 → 本地即验，不依赖 LLM）
Step 3: python3 _scripts/run_evals.py --mechanical 本地跑机械项
Step 4: （可选）python3 _scripts/run_evals.py --llm 走 LLM-as-Judge（锚点校准）
```

## 用例格式（evals/*.md）

```markdown
## Q1 超标 3 倍通常属哪个裁量阶次？
维度: 裁量幅度
黄金要点: 较重（2-5 倍）
引用校验: 无
```

## 黄金法则

- 测试用例只来自技能原文，禁止凭空编题（anti-hallucination）
- 每个表格至少 2 条知识题，每个 Step 至少 1 条应用题
- 机械校验优先：能本地验证的（条文存在/路径存在/格式）不交给 LLM
