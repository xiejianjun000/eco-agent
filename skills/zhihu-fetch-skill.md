---
id: zhihu-fetch-skill
name: 知乎抓取归档
version: 1.0.0
description: |
  将知乎收藏夹/专栏/回答/文章抓取为 Markdown 并归档到 Obsidian。
  支持批量抓取、自动分类、失败重试、历史记录、反反爬策略。
  原作者: handsomestWei (https://github.com/handsomestWei/zhihu-fetch-skill)
category: 内容采集
triggers:
  - 抓取知乎
  - 知乎收藏
  - 知乎归档
  - 知乎文章
  - zhihu fetch
  - 知乎内容同步
parameters:
  collection_id:
    type: string
    description: 知乎收藏夹ID（从URL获取，如 2069156136926835544）
    required: true
  output_dir:
    type: string
    description: 输出目录（默认: ./zhihu_output）
    required: false
    default: ./zhihu_output
  batch_size:
    type: integer
    description: 批量抓取数量（默认: 50）
    required: false
    default: 50
  use_stealth:
    type: boolean
    description: 是否启用反反爬策略（默认: true）
    required: false
    default: true
  classify:
    type: boolean
    description: 是否自动分类到 Obsidian（默认: true）
    required: false
    default: true
  limit:
    type: integer
    description: 最大抓取数量（默认: 1000）
    required: false
    default: 1000
author: handsomestWei (adapted by eco Agent)
source: https://github.com/handsomestWei/zhihu-fetch-skill
license: MIT
status: active
created_at: 2026-08-27
---

# 知乎抓取归档 Skill

## 功能概述

将知乎收藏夹/专栏/回答/文章批量抓取为 Markdown，自动分类归档到 Obsidian 或本地目录。

## 核心能力

| 功能 | 说明 |
|-----|------|
| 收藏夹抓取 | 输入收藏夹ID，批量抓取所有文章 |
| 专栏抓取 | 支持知乎专栏内容同步 |
| 回答抓取 | 抓取特定问题的所有回答 |
| 反反爬策略 | 模拟浏览器行为，绕过反爬限制 |
| 自动分类 | 基于内容标签自动分类到 Obsidian |
| 失败重试 | 自动记录失败项，支持断点续传 |
| 历史记录 | 记录已抓取内容，避免重复 |

## 执行步骤

1. **解析输入**：提取收藏夹ID/专栏ID/问题ID
2. **配置环境**：加载反反爬策略、设置输出路径
3. **批量抓取**：使用 `fetch_zhihu.py` 或 `fetch_zhihu_stealth.py`
4. **内容转换**：将 HTML 转为 Markdown
5. **自动分类**：使用 `obsidian_classify.py` 分类归档
6. **失败处理**：记录失败项到 `write_zhihu_failures.py`
7. **历史记录**：更新抓取历史到 `write_zhihu_history_to_obsidian.py`

## 脚本清单

| 脚本 | 功能 |
|-----|------|
| `fetch_zhihu.py` | 基础抓取（requests） |
| `fetch_zhihu_stealth.py` | 反反爬抓取（playwright） |
| `fetch_zhihu_api.py` | API 方式抓取 |
| `fetch_zhihu_batch.py` | 批量抓取 |
| `fetch_zhihu_collection.py` | 收藏夹专用抓取 |
| `fetch_zhihu_columns.py` | 专栏抓取 |
| `fetch_zhihu_history.py` | 历史记录管理 |
| `fetch_zhihu_interactive.py` | 交互式抓取 |
| `obsidian_classify.py` | Obsidian 自动分类 |
| `write_to_obsidian.py` | 写入 Obsidian 仓库 |
| `write_zhihu_failures.py` | 失败项记录 |
| `write_zhihu_history_to_obsidian.py` | 历史记录归档 |
| `fetch_limits.py` | 速率限制控制 |
| `workspace_paths.py` | 工作区路径管理 |

## 依赖

```bash
pip install requests beautifulsoup4 markdownify playwright
```

## 使用示例

```bash
# 抓取收藏夹
cd skills/zhihu-fetch-skill/scripts
python fetch_zhihu_collection.py --collection-id 2069156136926835544 --output ../../zhihu_output

# 反反爬模式抓取
python fetch_zhihu_stealth.py --url https://zhuanlan.zhihu.com/p/2069156136926835544 --output ../../zhihu_output

# 批量抓取
python fetch_zhihu_batch.py --input collections.txt --output ../../zhihu_output --batch-size 50
```

## 配置

编辑 `zhihu_fetch_config.json`：

```json
{
  "output_dir": "./zhihu_output",
  "obsidian_vault": "~/Obsidian",
  "batch_size": 50,
  "rate_limit": 1.0,
  "use_stealth": true,
  "classify_by_tag": true,
  "retry_times": 3,
  "timeout": 30
}
```

## 注意事项

- 遵守知乎 robots.txt 和 API 使用规范
- 建议启用 `use_stealth` 避免被封禁
- 合理设置 `rate_limit` 控制请求频率
- 首次抓取建议小批量测试
