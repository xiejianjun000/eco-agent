---
name: gongwen-format-skill
description: Generate Chinese official document (公文) Word files from controlled Markdown or JSON. Use when producing or updating .docx 公文 that must follow fixed fonts, line spacing, title/recipient layout, attachments, and footer page numbers, especially when the input is a controlled Markdown protocol. 触发词：公文排版、公文格式、docx 导出、GB/T 9704、红头文件、字体字号、受控 Markdown。
risk_level: medium
version: 1.0.0
---

# Gongwen Markdown Docx

## Overview

Create standard-format 公文 .docx with a deterministic script. It supports controlled Markdown (with front matter) or JSON input and uses bundled fonts for consistent rendering.

## Quick Start

Use JSON input or controlled Markdown to generate a docx.

```bash
python scripts/gongwen_doc.py --input data.json -o 输出公文.docx
python scripts/gongwen_doc.py --md input.md -o 输出公文.docx
```

## Controlled Markdown

- Read `references/受控Markdown公文解析与渲染规范v1.0.md` before generating Markdown input.
- Read `references/公文格式要求.md` for font sizes, line spacing, and layout constraints.
- Front matter supports: `recipients`, `signer`, `date`, `attachments`.
- ASCII double quotes in content are normalized to Chinese quotes (“…”).

Example (controlled Markdown):

```markdown
---
recipients: 各相关单位
signer: XX单位
date: 2026年1月30日
attachments:
  - 年度工作总结模板
---
# 关于开展年度工作总结的通知
## 一、总体要求
### （一）突出重点。
这是第一自然段。
这是第二自然段。
```

## Fonts

Use fonts in `assets/` for consistent rendering. Install them on the OS or ensure Word can locate them.

## 工作流程

```
Step 1: 确定输入——JSON 或受控 Markdown（含 front matter：recipients/signer/date/attachments）
Step 2: 读规范——references/受控Markdown公文解析与渲染规范v1.0.md 与 references/公文格式要求.md
Step 3: 生成——python scripts/gongwen_doc.py --md input.md -o 输出公文.docx
Step 4: 校验——核对字体（方正小标宋/仿宋/楷体）、字号、行距、首行缩进、页码是否达标
```

## 决策表（front matter 字段）

| 字段 | 作用 | 必填 |
|------|------|------|
| recipients | 主送机关 | 是 |
| signer | 落款单位 | 是 |
| date | 成文日期 | 是 |
| attachments | 附件列表 | 否 |

## 引用纪律

- 字体字号、行距与版式约束以 references/公文格式要求.md 原文为准，生成后逐项核对。
- 受控 Markdown 的 front matter 字段与解析规则以 references/受控Markdown公文解析与渲染规范v1.0.md 为准，不确定的字段标注 [待确认]。
