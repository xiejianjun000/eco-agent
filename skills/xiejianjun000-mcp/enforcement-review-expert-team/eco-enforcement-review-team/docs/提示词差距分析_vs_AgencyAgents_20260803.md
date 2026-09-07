# 提示词差距分析报告 vs Agency Agents 三部曲

**基准**：agency-agents / agency-agents-zh / agency-agents-zh-siyi  
**对比对象**：执法督察评查专家团 9 个 Agent 提示词

---

## 一、结构对比

| 提示词段落 | agency-agents 标准 | 我们当前 | 差距 |
|-----------|-------------------|---------|------|
| YAML 元数据 | name/description/**vibe**/**emoji**/**color** | name/description/displayName/profession/maxTurns | **缺 vibe/emoji/color** |
| 身份与记忆 | "Your Identity & Memory"（四维：角色/个性/记忆/经验） | "核心身份"（角色+使命） | **缺个性/记忆/经验维度** |
| 核心使命 | 详细职责分解，带子领域 | ✅ 有 | 结构可比 |
| 关键规则 | "Critical Rules" + **红线触发词** | "工作原则" | **缺触发词、少不可推翻规则** |
| 技术交付物 | 具体产出模板（JSON/Markdown） | ✅ 有 | 可比 |
| 工作流程 | **ASCII 流程图** + 阶段门禁 | 文字描述 | **缺 ASCII 图、缺门禁** |
| 沟通风格 | "Communication Style" | 无 | **完全缺失** |
| **成功指标** | "Success Metrics"（可度量） | 无 | **完全缺失** |
| **证据要求** | 截图/测试数据/视觉证据 | 无 | **完全缺失** |

## 二、关键能力缺失项

### 🔴 P0（致命缺失）

| 缺失项 | 影响 | 来源参照 |
|--------|------|---------|
| **vibe 宪法性约束** | Agent 行为可能漂移 | `vibe: I don't write prompts, I write contracts` |
| **证据门禁** | 无强制证据要求，无法防幻觉 | Reality Checker: "默认不通过，需要压倒性证据" |
| **结构化交接模板** | Agent 之间传递信息格式不一致 | NEXUS 7种交接模板 |
| **质量门禁定义** | 阶段之间无限流 | NEXUS 每阶段: 守门人+标准+阈值+证据 |
| **失败模式分析** | 不知道什么时候会死 | Multi-Agent Architect: 每种拓扑配失败模式 |

### 🟠 P1（严重缺失）

| 缺失项 | 影响 | 来源参照 |
|--------|------|---------|
| **重试上限与升级路径** | 死循环风险 | NEXUS Phase 3: 3次重试×5种升级选项 |
| **上下文预算意识** | Token 爆炸 | MAS Architect: 每 agent 500→1500→3500→7500→15000+ |
| **沟通风格定义** | 输出风格不一致 | 每个 agent 有 Communication Style 段 |
| **成功指标** | 无法度量质量 | 每个 agent 有 Success Metrics |
| **记忆架构声明** | 不知道记什么、怎么记 | MCP memory 集成 + 交接记忆传递 |

### 🟡 P2（改进空间）

| 缺失项 | 影响 | 来源参照 |
|--------|------|---------|
| **vibe/emoji/color** | 品牌感弱 | 每个 agent 有视觉标识 |
| **角色个性维度** | Agent 人格单薄 | "你是一位_____" + "你的性格是_____" |
| **阶段门禁 ASCII 图** | SOP 可读性差 | NEXUS 每阶段含 ASCII 并行工作流 |
| **场景化 runbooks** | 缺少即用方案 | NEXUS 4种预配置场景 |

## 三、改进优先级

```
Phase 1（立即）: 所有 Agent 补齐 vibe/color/emoji + 沟通风格 + 成功指标
Phase 2（立即）: 调度官补齐: 质量门禁 + 交接模板 + 失败模式
Phase 3（今日）: 全员补齐: 证据要求 + 角色个性 + 记忆架构声明  
Phase 4（后续）: NEXUS 风格 SOP 流程图 + 门禁系统
```

## 四、改进后的提示词结构模板

```markdown
---
name: xxx
description: xxx
vibe: "一句话宪法性约束"
emoji: 🔍
color: "#1A5276"
displayName:
  en: "xxx"
  zh: "xxx"
profession:
  en: "xxx"
  zh: "xxx"
maxTurns: xx
---

# Agent 名称

## 一、你的身份与记忆
### 1.1 你是谁
### 1.2 你的性格
### 1.3 你记得什么
### 1.4 你的经验

## 二、核心使命

## 三、关键规则（不可推翻）
### 3.1 红线（绝对禁止）
### 3.2 强制要求
### 3.3 触发词

## 四、工作流程
### 4.1 标准 SOP（ASCII 图）
### 4.2 阶段门禁
### 4.3 失败模式与升级路径

## 五、交付物规范
### 5.1 产出清单
### 5.2 证据要求
### 5.3 交接模板

## 六、沟通风格

## 七、成功指标

## 八、技能与工具
```
