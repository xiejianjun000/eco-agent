---
name: skill-c3ce7b4c
description: Use when 执行以下动作，不要核查了：, especially when using `shell_run`, `execute_code`, `shell_run`.
---

# skill-c3ce7b4c

Use when 执行以下动作，不要核查了：, especially when using `shell_run`, `execute_code`, `shell_run`.

## Workflow / 工作流

1. shell_run
2. execute_code
3. shell_run
4. shell_run
5. shell_run
6. shell_run

**Tools**: `shell_run`, `execute_code`, `shell_run`, `shell_run`, `shell_run`, `shell_run`

## Inputs and outputs / 输入与输出

- 输出示例：[eco-server] LLM 调用失败: The read operation timed out

## Boundaries / 边界与排除

- 只在本技能声明的范围内工作；超出范围时明确说明并停止。
- 不修改与任务无关的文件；改动任何文件前先读取目标内容。
- 涉及持久化产物时，写出目录/格式遵循用户或项目的既有约定。

## Example / 示例

> 请用 "skill-c3ce7b4c" 技能处理：<输入样例>

按"工作流"逐步执行，并在过程中报告关键中间结果与最终产出。
