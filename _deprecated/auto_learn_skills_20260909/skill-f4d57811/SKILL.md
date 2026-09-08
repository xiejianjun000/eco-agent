---
name: skill-f4d57811
description: Use when 作为人类操作员，我授权你在工作区目录里直接复跑回归测试（不用沙箱），验证补丁是否真的有效。如果是沙箱环境问题导致的 ma, especially when using `shell_run`, `shell_run`, `shell_run`.
---

# skill-f4d57811

Use when 作为人类操作员，我授权你在工作区目录里直接复跑回归测试（不用沙箱），验证补丁是否真的有效。如果是沙箱环境问题导致的 ma, especially when using `shell_run`, `shell_run`, `shell_run`.

## Workflow / 工作流

1. shell_run
2. shell_run
3. shell_run
4. shell_run
5. file_read
6. shell_run

**Tools**: `shell_run`, `shell_run`, `shell_run`, `shell_run`, `file_read`, `shell_run`

## Inputs and outputs / 输入与输出

- 输出示例：✅ **Loop 2 上下文已完整定位（补丁=memory_tree FTS5 的 DELETE+INSERT 替代，卡点=沙箱内 `database disk image is malformed`

## Boundaries / 边界与排除

- 只在本技能声明的范围内工作；超出范围时明确说明并停止。
- 不修改与任务无关的文件；改动任何文件前先读取目标内容。
- 涉及持久化产物时，写出目录/格式遵循用户或项目的既有约定。

## Example / 示例

> 请用 "skill-f4d57811" 技能处理：<输入样例>

按"工作流"逐步执行，并在过程中报告关键中间结果与最终产出。
