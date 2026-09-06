---
name: skill-d3de927a
description: Use when 那为什么这个mcp服务器登录不了？, especially when using `shell_run`, `shell_run`, `execute_code`.
---

# skill-d3de927a

Use when 那为什么这个mcp服务器登录不了？, especially when using `shell_run`, `shell_run`, `execute_code`.

## Workflow / 工作流

1. shell_run
2. shell_run
3. execute_code
4. execute_code
5. shell_run
6. shell_run

**Tools**: `shell_run`, `shell_run`, `execute_code`, `execute_code`, `shell_run`, `shell_run`

## Inputs and outputs / 输入与输出

- 输出示例：✅ **8004 根本不需要"登录"，也"登录"得上——它用的是 API Key 鉴权（请求头），不是账号登录；带正确 Key 实测 SSE 握手 200 成功。"登录不了"是三层误判叠加的假象。**

## Boundaries / 边界与排除

- 只在本技能声明的范围内工作；超出范围时明确说明并停止。
- 不修改与任务无关的文件；改动任何文件前先读取目标内容。
- 涉及持久化产物时，写出目录/格式遵循用户或项目的既有约定。

## Example / 示例

> 请用 "skill-d3de927a" 技能处理：<输入样例>

按"工作流"逐步执行，并在过程中报告关键中间结果与最终产出。
