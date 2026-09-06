---
name: office-file-processing
description: Office 文件（Excel/Word/PowerPoint/CSV）与 SQLite 数据处理及省 Token 工作流。基于 openpyxl、python-docx、python-pptx、pandas、sqlite3 读写 .xlsx/.docx/.pptx/.csv 与 SQLite 建库/导入/查询/导出 Excel 报表。默认交互式工作：调用后主动分组提问（阶段 1 文件与目标→阶段 2 细节与输出→阶段 3 确认清单），每阶段一次问 2-3 个问题、每题给选项与默认值，确认后执行；Excel 任务一律经 SQLite 中转（导入→SQL 查询→导出）；探查与结果继续遵守"摘要回传、结果落盘"的省 Token 规则。当用户要求处理/生成/修改/转换/分析 Office 文件、用 SQLite 管理数据并导出 Excel，或询问如何节省处理 Office 文件时的 Token 消耗时使用。
whenToUse: >
  用户提出 Excel/Word/PPT/CSV 相关需求（读取、修改、生成、汇总、转换、格式排版、批量处理、数据匹配），
  提供 Office 文件并要求处理，或询问省 Token 处理 Office 文件的方式时使用。
  调用后默认进入交互式分组提问（每阶段一次问 2-3 个意图类问题，集齐后出确认清单再执行）。
  不适用于纯界面操作咨询或与文件读写无关的一般办公软件问题。
metadata:
  version: "2026-08-18"
  origin: 与用户会话沉淀（环境实测可用）
  python: <Python安装目录>\python.exe（通常已写入系统 PATH，直接使用 `python` 即可；若提示未找到，用 `where.exe python` 查询本机完整路径）
  libraries: openpyxl 3.1.5、python-docx 1.2.0、python-pptx 1.0.2、pandas 3.0.5（含 numpy、Pillow、lxml）；sqlite3（Python 内置）；pypandoc 1.17（pandoc 3.9 二进制）；pypdf、pdfplumber、olefile（PDF 提取与旧版 .doc 解析）
  workspace: <工作目录>（默认 D:\Workspace，可按需修改）
---

# Office 文件处理与 Token 优化

## 1. 环境约定

- **运行方式**：一律通过 pwsh 执行 `python <脚本.py>`；脚本先写成 .py 文件再执行（可复用），不要用 `python -c` 内联长代码。
- **Python 路径**：优先 `python`；若提示"Python was not found"，改用本机 Python 完整路径 `<Python安装目录>\python.exe`（可用 `where.exe python` 查询），重启 DSH 后 `python` 即生效。
- **已安装库**：openpyxl（Excel）、python-docx（Word）、python-pptx（PPT）、pandas（数据）、**sqlite3（Python 内置，SQLite 数据库，零安装零服务）**、**pypandoc（pandoc 3.9，Markdown→docx 等格式转换，自带二进制）**；**pypdf、pdfplumber（PDF 文本提取）、olefile（旧版 .doc 解析）**——需要时直接 import，无需再安装。
- **工作目录**：`<工作目录>`（本 skill 实测环境为 `D:\DeepSeek-Work`；其他机器按需修改）。输入文件放这里，输出文件写这里。
- **编码**：所有脚本开头加 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')`，避免中文输出乱码。
- **旧版 .doc/.xls**：openpyxl 与 python-docx 只支持新格式；旧版 .doc 用 olefile 读 WordDocument 流提取文本（含中文时按 UTF-16LE 片段扫描）。旧版 .xls **一律请用户转存 .xlsx**（xlrd 直读未经实测，不承诺支持）。
- **PDF**：文本提取用 pdfplumber（`pdf.pages[i].extract_text()`）；若提取字符数过少（如单页不足几十字符），说明是图片型/扫描版 PDF，无 OCR 库，需请用户提供文字版或另存为 docx。
- **PowerShell 注意**：DSH 的 pwsh 工具底层是 Windows PowerShell 5.1（非 pwsh 7）。写 .ps1 脚本时：① 含中文必须保存为 UTF-8 with BOM（否则中文按 ANSI 误读成乱码）；② `byte -shl 8` 等移位结果会被截断回 byte，必须先 `[int]$x -shl 8` 强制提升。

## 2. 核心原则：文件留在磁盘，对话只过摘要

1. **绝不直接用 read 工具读** .xlsx/.docx/.pptx：它们是 zip 二进制，读不出内容且浪费 Token。所有读写都走 Python 脚本。
2. **数据不进对话**：探查结果 ≤20 行；绝不在对话中打印整个 DataFrame、全文或全表。
3. **结果写文件**：处理输出写进新文件，对话中只报告 成功/失败 + 关键数字（行数、字数、页数、幻灯片数）+ 输出路径。
4. **失败只带最小信息**：报错类型 + 出错行号 + 关键数据片段，不在对话里贴大段 traceback。

## 3. 标准工作流（每类任务必须遵守）

```
① 交互式分组提问：按 3.1 阶段清单收集需求，集齐后出确认清单（默认工作方式）
② 探查：运行对应 probe 脚本，只输出紧凑摘要
③ 确认方向后执行：编写或复用处理脚本，结果写文件；Excel/CSV 任务一律经 SQLite 中转（见第 4 节）
④ 汇报：✅ 完成 + 输出文件路径 + 关键数字（一行内说完）
```

### 3.1 交互式分组提问（默认工作方式）

**提问纪律**：

1. **按阶段分组**：每阶段一次问 2-3 个相关问题，编号列出、每题给选项与默认值（回复字母即可）；只在阶段之间等待用户回复。
2. **不重复问**：用户开场已说明的要素直接跳过；用户一次性给全 → 跳过提问直接探查。
3. **可喊停**：用户说"不用提问/直接做" → 退回一次性问清或直接执行。
4. **只问意图不碰数据**：提问只收集路径与目标，数据内容仍走探查脚本与摘要规则（第 2 节）。
5. **确认后执行**：阶段 3 确认清单获"Y"才动手；完成后追问"还需要调整吗？"。

**阶段式提问清单**：

| 阶段 | 组内问题（编号，一条消息问完） |
| --- | --- |
| 阶段 1 · 识别任务 | ① 处理哪个文件？（给路径或拖入；新建 Word/PPT 请说"新建+类型"）② 想达到什么效果？（Excel/CSV：A 汇总统计 B 清洗去重 C 匹配合并 D 格式排版 E 入库查询；Word：新建/修改+用途；PPT：用途声明——座谈会/路演/培训/述职等，决定版式） |
| 阶段 2 · 明确细节 | Excel/CSV：① 按哪列分组/筛选条件？（可回"无"）② 输出文件名？（默认 <原名>_汇总.xlsx）；Word：① 内容来源（md 初稿/口述要点）+ 具体改什么（替换文本/排版/增删）② 输出文件名；PPT：① 内容 Markdown 材料路径 ② 输出文件名；SQLite：① 库文件（新建/已有）② 导入数据源或查询目标 ③ 输出（Excel 报表/仅显示汇总） |
| 阶段 3 · 确认 | 单行确认清单：`确认：对 <文件> 做 <目标>，输出 <文件名>。回复 Y 开始，或指出要改哪项。` |

### 3.2 探查脚本

探查脚本（在 skill 的 scripts/ 目录，可用绝对路径执行）：

| 脚本 | 用法 | 输出内容 |
| --- | --- | --- |
| `scripts/excel_probe.py` | `python <skill目录>/scripts/excel_probe.py <文件> [sheet名]` | Sheet 列表、行/列数、列名、dtype、前 3 行样本 |
| `scripts/word_probe.py` | `python <skill目录>/scripts/word_probe.py <文件.docx> [样本段数]` | 段落/表格统计、标题结构、正文前几段、页面设置 |
| `scripts/ppt_probe.py` | `python <skill目录>/scripts/ppt_probe.py <文件.pptx>` | 幻灯片数、每页标题、形状/表格/图片统计 |

## 4. 各文件类型处理要点

### Excel
- **默认链路：经 SQLite 中转**。Excel/CSV 任务一律走 `导入 SQLite → SQL 查询/汇总 → pandas → 导出 Excel 报表`（小任务同样走库，链路统一）；pandas 直接处理仅限极简探查（如只看前几行样本）。
- 导入前用 `scripts/excel_probe.py` 探查，按需决定导入哪些列（`usecols`）、是否分块（>10 万行用 `chunksize` 分块导入）。
- 聚合统计（分组求和、透视、去重、匹配）在 SQL 层完成，**只把汇总结果带回来**，绝不回传明细。
- 格式要求（边框、合并单元格、列宽行高、样式）用 openpyxl 直接操作；数据变更与格式变更分步做，避免互相干扰。
- 写回格式时保留原文件样式：优先在原 wb 对象上改再 `save` 为新文件，不重写整个表。

### 数据库（SQLite）
- **定位：所有 Excel/CSV 任务的默认中转层**（不再只是大数据场景），统一链路：`Excel/CSV ──导入──▶ SQLite(.db) ──SQL 查询/汇总──▶ pandas ──导出──▶ Excel 报表`
- **零安装零服务**：Python 内置 `sqlite3`，一个 `.db` 文件即整个库；库文件放工作目录（如 `<工作目录>\data.db`）。
- **导入**：`pd.read_excel/read_csv` → `df.to_sql('表名', conn, if_exists='append'/'replace', index=False)`；长期数据先定主键、建索引（`CREATE UNIQUE INDEX`），增量追加不重写全量。
- **查询**：`pd.read_sql('SELECT ...', conn)`；聚合、JOIN、筛选在 SQL 层完成，只把汇总结果带回对话。
- **导出**：查询结果 `df.to_excel()`；需要格式（表头、列宽、样式）时用 openpyxl 加工后输出。
- **省 Token 增益**：查询在库里完成，省去反复读 Excel；`.db` 留在磁盘可反复查询，不占对话上下文。

### Word
- 生成文档用 python-docx：标题/段落/表格/样式/页边距/页眉页脚。
- **初稿工作流（用户约定）**：需要生成初稿时先写 .md 文件（写作省 Token、易审阅），再转 .docx 交付。转换优先用 pandoc：`pypandoc.convert_file('x.md', 'docx', outputfile='x.docx')`（语法全、质量高）；pandoc 不可用时用 `scripts/md2docx.py` 兜底。初稿确认后再用 python-docx 做精细排版。公文类初稿配合 `official-document-writing` skill 起草后同样走 md→docx。
- 公文类任务（通知、报告、纪要、讲话等）配合 `official-document-writing` skill 的模板与规范。
- 替换文本：遍历段落与表格单元格，报告替换次数；正则批量替换先确认匹配片段再执行。
- 用户要求精确排版效果时，说明脚本排版的局限（无法所见即所得），建议先出结构版再人工微调。

### PowerPoint
- **PPT 生成工作流（用户约定，2026-08-17）**：
  1. 输入：用户提供 Markdown 内容 + 用途声明（座谈会/路演/汇报/培训/工作总结等）
  2. 公文审查（所有场景必做）：先调用 `official-document-writing` skill 对 Markdown 内容做公文写法审查；审查结论随交付回执
  3. 版式按场景自动选：座谈会/党政汇报→庄重政务风（深蓝/红金、方正字体）；路演/产品发布→商务冲击风（深色背景、高对比大标题）；培训/教学→清晰教学风（浅色、分区明确）；工作总结/述职→稳重商务风（蓝白、数据化排版）
  4. 图片占位双保险：页面放灰色占位框 + 框内文字「此处插入：XXX（建议尺寸）」；同一位置在演讲者备注栏再写一遍插图建议
  5. 交付：.pptx 保存到工作区，回复给路径 + 审查回执
- 生成 PPT：把文字材料整理成大纲 → 按版式填充 title/body；python-pptx 处理内容与版式，不做像素级渲染。
- 修改现有 PPT：遍历 shapes 按关键词匹配替换占位文本，报告每页改动数。
- 样式统一（字体、字号、颜色）用循环统一设置，避免逐页手写。

## 5. 省 Token 规则清单（处理全程遵守）

1. **探查先行**：先看结构（行数/列名/标题），再决定取哪些内容，不全量读入。
2. **摘要回传**：`head(3)` + `info()` + 统计数字；不打印全表全文。
3. **结果落盘**：写输出文件，对话只报关键数字与路径。
4. **意图分组问清、数据留盘**：需求用交互式分组提问收集（见 3.1 节），每阶段一次问 2-3 个意图类问题、每题带选项与默认值；数据内容一律走探查与落盘，不进对话。
5. **脚本复用**：处理脚本存成 .py 留在工作目录（如 `<工作目录>\scripts\`）；同类任务改参数调用，不重新生成大段代码。
6. **大任务用子代理**：数据量大或步骤多的任务（合并清洗多文件、批量格式转换），委托后台子代理在独立上下文完成，主会话只收一行摘要。多文件并行用 workflow 分发，只回结构化 JSON 汇总。
7. **长耗时放后台**：大文件转换等用后台 job 跑，完成时只汇报结果。
8. **任务切分**：独立任务开新会话，靠本 skill 固化的约定（SQLite 中转、Word 初稿 md→docx，见第 4 节）保持连续性，避免长对话历史持续占 Token。

## 6. 汇报格式（模板）

- 分组提问：`【阶段 1/2】① 要处理哪个文件？请给路径或拖入（新建 Word/PPT 请说"新建+类型"）。② 目标？（回复字母）：A 汇总统计 B 清洗去重 C 匹配合并 D 格式排版 E 入库查询`
- 确认清单：`确认：对 <工作目录>\xx.xlsx 按「部门」分组求和 → 输出 summary.xlsx。回复 Y 开始，或指出要改哪项。`
- 成功：`✅ 处理完成 → <输出文件路径>。合并 3 个表共 12,340 行，去除重复 456 行，生成 4 个汇总 Sheet。`
- 失败：`❌ 处理失败：<脚本名> 第 N 行 <报错类型>，原因：<一句话>。已修正后重试。`（自行重试修正，真正卡住才求助）
- 完成后追问一句："还需要对结果做什么调整吗？"
- 每次回答用简体中文；只给结论与下一步，不重复用户已知内容。

## 7. 资源

- `scripts/excel_probe.py`：Excel 紧凑探查（openpyxl read_only 取维度，pandas 取列名/dtype/样本）
- `scripts/word_probe.py`：Word 紧凑探查（段落/表格/标题/页面设置）
- `scripts/ppt_probe.py`：PPT 紧凑探查（每页标题与形状统计）
- `scripts/md2docx.py`：Markdown 初稿转 .docx（标题/列表/表格/代码块/引用/行内粗体斜体代码/链接；用法 `python md2docx.py 输入.md [输出.docx]`）
- 脚本均输出 UTF-8、参数容错，可直接复用。
