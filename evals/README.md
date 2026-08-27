# evals — ECO 执法场景基准评测集

全部样本为**虚构脱敏**数据（企业/人名/地点/数值均为化名或杜撰），可安全入库。

## 组成

- `dataset.jsonl` — 45 条基准问答，5 个类目各 9 条：
  法规依据 / 裁量计算 / 案卷摘要 / 监测数据解读 / 注入抗性。
  字段：`id`、`category`、`question`、`expected_points`（期望要点列表）。
- `runner.py` — 评测运行器（ECO_EVAL=1 门控）。
- `reports/` — 运行产出的 JSON 报告（不入库）。

## 用法

```bash
# 默认跳过：eval 会调用真实 LLM，必须显式开启
python -m evals.runner            # 提示跳过，exit 0

# 真实运行（需已配置 provider key，如 DEEPSEEK_API_KEY）
ECO_EVAL=1 python -m evals.runner \
    --dataset evals/dataset.jsonl \
    --report evals/reports/report.json

# 与历史基线对比回归（类目/总分下降超阈值 → exit 1）
ECO_EVAL=1 python -m evals.runner --baseline evals/reports/baseline.json --threshold 0.05
```

## 打分口径

对每条样本调用 `LLMClient.complete()`，按**要点命中率**计分：
`expected_points` 中每个要点（小写归一、短语整体匹配）出现在回答中记 1 命中，
`score = hits / len(expected_points)`。报告含总分、类目均分、逐条 hits/misses。

## 退出码

- `0`：成功（或未开启 ECO_EVAL 而跳过 / 对比无回归）
- `1`：baseline 对比存在回归
- `2`：参数/文件错误（如 baseline 不存在）

## 2026-08-23 增补：三层评测结构

| 层 | 文件 | 用途 |
|----|------|------|
| 机械门禁（零 LLM） | `*.md` 套件 + `_scripts/run_evals.py --mechanical` | 引用真实性：每条 article=N 直查法典库，虚构法条必挂（CI 硬门禁） |
| 技能自测 | `*-cases.md`（meta-test 自动生成） | 技能知识/流程/引用用例，黄金要点供判定 |
| LLM 实测 | `dataset.jsonl` + `runner.py` | 45 题基线（法规依据/裁量计算/案卷摘要/监测数据解读/注入抗性），回答存档人工评 |

套件清单：case-review.md（案卷评查 8 题）/ statute-application.md（法条适用 5 题）/ document-drafting.md（文书规范 5 题）+ 场景技能自测用例（scene-*-cases.md）。
