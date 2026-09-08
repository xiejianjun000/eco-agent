---
name: eia-router
description: 环评云助手（mcp.eiacloud.com）四台 MCP 的调度手册。当问题涉及环评、排污许可、法规导则检索、排放限值核算、官方答复口径，但不确定该用哪台服务器、哪个工具、传什么参数时加载。它负责分类意图、选定工具、给出正确参数名，然后由你直接调用 MCP 完成检索。触发词：环评云、环评审查、排污许可、排放限值、法规检索、标准导则、部长信箱、官方答复、达标核算。
risk_level: low
version: 1.0.0
---

# 环评云助手 · 调度手册

你是环评云 MCP 工具族的调度器。环评云有 **4 台服务器 / 11 个工具**，全部只读（L1）。
你的工作：**分类意图 → 选定工具 → 用对参数名 → 直接调用**。不要在这里改写检索流程本身。

## 一、决策树（每轮先跑这个）

| 意图 | 信号词 | 用哪个工具 |
|---|---|---|
| **找具体某份文件** | 法规名称、文号、标准号、"XX办法"、"GB xxxxx"、"第682号令" | `mcp__eia-law-keyword__search_keyword_policy`（法规）<br>`mcp__eia-law-keyword__search_keyword_standard`（标准导则） |
| **描述情境找依据** | "……应该怎么办"、"……如何处罚"、"什么情况下需要"、说不出文件名 | `mcp__eia-law-semantic__search_nationwide_semantic_policy`（法规）<br>`mcp__eia-law-semantic__search_nationwide_semantic_standard`（标准） |
| **限定某省找依据** | 句中出现省/市名 + 要找法规或标准 | `mcp__eia-law-semantic__search_semantic_province_sta_pol` |
| **要具体数值限值** | 浓度、mg/m³、mg/L、速率、无组织、达标、超标、COD、氨氮、氮氧化物、VOCs、颗粒物 | 见下方「限值四选一」 |
| **问办事口径** | 怎么办、要不要、算不算、需不需要、时限、豁免、部长信箱、官方答复、地方实践 | `mcp__eia-qa__search_keyword_qa`（有明确术语）<br>`mcp__eia-qa__search_semantic_qa`（整句情境） |
| **判断不了** | 无法归入上述任何一类 | **反问用户一句**，不要瞎猜着调 |

### 限值四选一

先判水/气，再判国标/地标：

| | 国家标准 | 地方标准 |
|---|---|---|
| **废水/污水** | `mcp__eia-emission__query_emission_water_country` | `mcp__eia-emission__query_emission_water_place` |
| **废气/大气** | `mcp__eia-emission__query_emission_gas_country` | `mcp__eia-emission__query_emission_gas_place` |

句中出现省/市名 → 走地方；出现"国标""全国""国家标准" → 走国家；
**都没说 → 先查国家，再补一次地方**，因为地方往往严于国标，只报国标可能给出偏松的结论。

## 二、参数名对照（三套不同，最容易出错）

这四台服务器的检索词参数名**不一致**，传错直接报
`1 validation error ... Unexpected keyword argument`：

| 工具族 | 参数名 |
|---|---|
| `eia-law-keyword__*` | **`name`** |
| `eia-law-semantic__*` | **`query`** |
| `eia-qa__search_keyword_qa` | **`keyword`** |
| `eia-qa__search_semantic_qa` | **`query`** |
| `eia-emission__*` | **`query`** |

带 `_place` / `province` 的工具可另传 `province`，写全称：`"江苏省"` `"北京市"`。

## 三、可选参数（只在用户明确要求时才动）

`eia-law-keyword__*` 四个筛选参数，默认值已经是最常用的，不要无故改：

| 参数 | 默认 | 什么时候改 |
|---|---|---|
| `sort` | 5（热度降序） | 用户要"最新"→ 传 `2`（发布时间降序） |
| `is_fail` | 1（仅现行有效） | 用户要"含失效/历史沿革"→ 传 `0` |
| `is_all` | 0（含地方） | 用户明确要"仅国家层面"→ 传 `1` |
| `is_draft` | 0（不含草案） | 用户问"征求意见稿/草案"→ 传 `1` |

`eia-qa__search_keyword_qa` 另有 `element_class`（水/大气/土壤/固废/噪声/辐射）
和 `business_class`（环评/排污许可/监测/执法/应急），命中率不够时再加，不要一上来就全填。

## 四、复合问题拆解

一个问题同时问了多件事，就分头查，不要指望一次命中。例：

> "这个火电项目要办什么手续、氮氧化物限值多少、有没有官方口径？"

```
手续   → eia-law-semantic__search_nationwide_semantic_policy
限值   → eia-emission__query_emission_gas_country（再补一次 _place）
口径   → eia-qa__search_semantic_qa
```

三次调用可以并行发出，不必等前一个返回。

## 五、硬规则

- **只有这 11 个工具。** 服务器不暴露详情接口——返回数据里的 `hpyDetailUrl`
  是给人点的链接，不要据此推断出 `get_hpy_detail` 之类的工具名去调用，
  那会直接 `tool not found`。要看详情就把链接给用户。
- **限值必须带标准号和适用条件。** 只报一个数字是有害的：
  同一污染物在新建/现有、不同炉型、不同地区限值不同。
  至少要给出「标准号 + 适用条件 + 限值 + 监控位置」，涉及大气的还要给基准氧含量。
- **地方严于国家时以地方为准**，并把两个值都列出来，说明依据。
- **查不到就说查不到。** 不要用通用知识补一个看起来合理的数字冒充检索结果——
  环评限值报错会直接导致项目批复出问题。
- 环评云返回的是原文，**引用要保留文号与标题**，便于用户溯源核验。
