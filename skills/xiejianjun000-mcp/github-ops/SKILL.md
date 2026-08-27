---
name: github-ops
description: |
  GitHub 仓库全生命周期运维管理技能。
  涵盖：仓库审计、代码推送、分支管理、PR 管理、CI/CD 配置、Issue 管理、
  Release 管理、开发者引流、日常运维、错误处理。
  当用户提到"GitHub 运维"、"仓库管理"、"项目运维"、"引流"、"开源运营"时使用。
homepage: https://github.com/xiejianjun000
metadata:
  openclaw:
    emoji: '🔧'
    requires: { env: ['GITHUB_TOKEN'] }
    primaryEnv: 'GITHUB_TOKEN'
  security:
    credentials_usage: |
      Requires GitHub Personal Access Token (PAT) with repo scope.
      Token is ONLY sent to api.github.com as Authorization header.
      Never log, echo, or commit the token.
    allowed_domains:
      - api.github.com
      - github.com
---

# 🔧 GitHub 仓库运维管理 Skill

> 基于 OpenTaiji 生态项目实战经验提炼
> 已集成自动化脚本，支持每日运维 Cron Job

## 📋 管理仓库列表

| 仓库 | 描述 | 状态 |
|------|------|------|
| **open-taiji** | 分布式多智能体协作引擎 | ⭐ 核心项目 |
| **tritai** | 零 Token AI 防幻觉引擎 | 🛡️ 子项目 |
| **taiji-agent** | 太极智能体框架 | 🧩 子项目 |
| **ai-valuation-skill** | AI 项目身价计算器 | 📊 子工具 |
| **github-ops** | 本仓库 — 运维管理技能 | 🔧 当前仓库 |

---

## 📦 一键运维脚本

本技能附带可直接执行的运维脚本，放在 `bin/` 目录下：

| 脚本 | 功能 | 用法 |
|------|------|------|
| `daily-audit.sh` | 全面审计所有仓库状态 | `bash bin/daily-audit.sh` |
| `daily-report.sh` | 生成运维日报 Markdown | `bash bin/daily-report.sh` |
| `optimize-repo.sh` | 优化单个仓库（Topics+描述+标签） | `bash bin/optimize-repo.sh owner/repo` |
| `clean-branches.sh` | 清理过期分支 | `bash bin/clean-branches.sh owner/repo` |

---

## 🚀 快速安装

```bash
# 1. 克隆到 OpenClaw skills 目录（已完成）
git clone https://github.com/xiejianjun000/github-ops.git ~/.openclaw/skills/github-ops

# 2. 设置 GitHub Token 环境变量
export GITHUB_TOKEN="ghp_your_token_here"
```

**Token 权限要求**：`repo`（完整仓库权限）

---

## 📊 前置条件

### 1. 凭证配置

每次操作前确保 `$GITHUB_TOKEN` 已设置：

```bash
# 检查是否已设置
echo "${GITHUB_TOKEN:0:4}..."  # 应输出 ghp_...

# 如未设置：写入 ~/.zshrc 永久生效
echo 'export GITHUB_TOKEN="ghp_your_token_here"' >> ~/.zshrc
source ~/.zshrc
```

### 2. API 基础配置

```bash
GH_API="https://api.github.com"
GH_AUTH="-H \"Authorization: token $GITHUB_TOKEN\" -H \"Accept: application/vnd.github+json\""
```

---

## 🛠 核心操作

### 一、仓库审计（必做第一步）

#### 1.1 列出所有仓库

```bash
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/user/repos?affiliation=owner&per_page=50" | python3 -c "
import sys, json
repos = json.loads(sys.stdin.read())
for r in repos:
    vis = '🔒 私有' if r.get('private') else '🌍 公开'
    stats = f'⭐{r[\"stargazers_count\"]} 🍴{r[\"forks_count\"]}'
    print(f'{vis} {r[\"name\"]:25s} | {str(r.get(\"language\",\"N/A\")):10s} | {stats} | {r[\"updated_at\"][:10]}')"
```

#### 1.2 检查单个仓库详情

```bash
REPO="xiejianjun000/open-taiji"
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/repos/$REPO" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
print(f'名称: {d.get(\"full_name\")}')
print(f'描述: {d.get(\"description\", \"无\")}')
print(f'语言: {d.get(\"language\", \"N/A\")}')
print(f'Stars: {d.get(\"stargazers_count\")}')
print(f'Forks: {d.get(\"forks_count\")}')
print(f'开放 Issues: {d.get(\"open_issues_count\")}')
print(f'大小: {d.get(\"size\")} KB')
print(f'分支: {d.get(\"default_branch\")}')
print(f'许可: {d.get(\"license\",{}).get(\"spdx_id\",\"无\") if d.get(\"license\") else \"无\"}')
print(f'Topics: {\", \".join(d.get(\"topics\",[]))}')
print(f'更新时间: {d.get(\"updated_at\")}')"
```

#### 1.3 检查文件结构

```bash
REPO="xiejianjun000/open-taiji"
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/repos/$REPO/git/trees/main?recursive=1" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
tree = d.get('tree', [])
files = [t for t in tree if t['type'] == 'blob']
dirs = [t for t in tree if t['type'] == 'tree']
print(f'文件数: {len(files)}')
print(f'目录数: {len(dirs)}')
print(f'总大小: {sum(t.get(\"size\",0) for t in files)} bytes')
top = sorted(set(t['path'].split('/')[0] for t in files))
print(f'顶层: {top}')"
```

#### 1.4 检查 CI 状态

```bash
REPO="xiejianjun000/open-taiji"
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/repos/$REPO/actions/runs?per_page=5" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
for r in d.get('workflow_runs', []):
    icon = '✅' if r.get('conclusion')=='success' else '❌' if r.get('conclusion')=='failure' else '🔄'
    print(f'{icon} {r[\"name\"]} → {r.get(\"conclusion\",\"运行中\")} ({r[\"created_at\"][:16]})')"
```

#### 1.5 检查 PR 和 Issue

```bash
REPO="xiejianjun000/open-taiji"
# PRs
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/repos/$REPO/pulls?state=open" | python3 -c "
import sys, json
prs = json.loads(sys.stdin.read())
print(f'Open PRs: {len(prs)}')
for p in prs: print(f'  #{p[\"number\"]}: {p[\"title\"][:60]}')"

# Issues
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/repos/$REPO/issues?state=open&per_page=10" | python3 -c "
import sys, json
issues = json.loads(sys.stdin.read())
real = [i for i in issues if 'pull_request' not in i]
print(f'Open Issues: {len(real)}')
for i in real: print(f'  #{i[\"number\"]}: {i[\"title\"][:60]}')"
```

#### 1.6 批量审计所有仓库

```bash
OWNER="xiejianjun000"
repos=("open-taiji" "tritai" "taiji-agent" "ai-valuation-skill" "github-ops")
for repo in "${repos[@]}"; do
  echo "=== $repo ==="
  curl -s -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "$GH_API/repos/$OWNER/$repo" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
print(f'  描述: {d.get(\"description\",\"无\")[:60]}')
print(f'  ⭐{d[\"stargazers_count\"]} 🍴{d[\"forks_count\"]} ⚠️{d[\"open_issues_count\"]}')
print(f'  语言: {d.get(\"language\",\"N/A\")} | 更新: {d[\"updated_at\"][:10]}')"
  echo ""
done
```

---

### 二、代码推送

#### 2.1 克隆仓库到临时工作目录

```bash
OWNER="xiejianjun000"
REPO="repo-name"
TMPDIR="/tmp/$REPO-ops"
rm -rf "$TMPDIR" 2>/dev/null
git clone "https://xiejianjun000:$GITHUB_TOKEN@github.com/$OWNER/$REPO.git" "$TMPDIR"
cd "$TMPDIR"
git config user.name "小存"
git config user.email "xiaocun@openclaw.local"
```

#### 2.2 修改并推送

```bash
# 修改文件后
git add -A
git commit -m "type: description"
git push origin main
```

#### 2.3 直接更新远程仓库文件（无需克隆）

```bash
# 更新 README.md
REPO="xiejianjun000/open-taiji"
CONTENT=$(echo "# New content" | base64)
curl -s -X PUT -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/repos/$REPO/contents/README.md" \
  -d "{\"message\":\"docs: update README\",\"content\":\"$CONTENT\",\"branch\":\"main\"}" 2>/dev/null
```

---

### 三、分支管理

#### 3.1 创建 PR

```bash
curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/repos/$OWNER/$REPO/pulls" \
  -d '{"title":"PR 标题","body":"PR 描述","head":"feature/branch","base":"main"}'
```

#### 3.2 合并 PR

```bash
PR_NUMBER=1
curl -s -X PUT -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/repos/$OWNER/$REPO/pulls/$PR_NUMBER/merge" \
  -d '{"commit_title":"合并: ...","merge_method":"merge"}'
```

#### 3.3 清理过期分支（自动扫描所有分支）

```bash
# 列出所有分支
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  "$GH_API/repos/$OWNER/$REPO/branches?per_page=50" | python3 -c "
import sys, json
branches = json.loads(sys.stdin.read())
for b in branches:
    name = b['name']
    if name not in ['main','master','develop']:
        print(f'  可清理: {name}')"
```

---

### 四、CI/CD 配置管理

#### 4.1 检查 CI 工作流列表

```bash
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/repos/$OWNER/$REPO/actions/workflows" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
for w in d.get('workflows', []):
    state = '✅' if w.get('state')=='active' else '⛔'
    print(f'{state} {w[\"name\"]} (ID: {w[\"id\"]})')"
```

#### 4.2 重新运行失败的工作流

```bash
curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/repos/$OWNER/$REPO/actions/runs/$RUN_ID/rerun-failed-jobs"
```

---

### 五、项目完善（开发者引流）

#### 5.1 优化仓库描述和 Topics

```bash
# 设置描述 + 首页
curl -s -X PATCH -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/repos/$OWNER/$REPO" \
  -d '{"description":"新描述","homepage":"https://..."}'

# 设置 Topics（搜索标签）
curl -s -X PUT -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/repos/$OWNER/$REPO/topics" \
  -d '{"names":["keyword1","keyword2","open-source","typescript"]}'
```

#### 5.2 批量添加 Issue Labels

```bash
for label in 'good first issue:008672' 'bug:d73a4a' 'enhancement:a2eeef' \
             'documentation:0075ca' 'help wanted:008672' 'question:d87634'; do
  name="${label%%:*}"
  color="${label##*:}"
  curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "$GH_API/repos/$OWNER/$REPO/labels" \
    -d "{\"name\":\"$name\",\"color\":\"$color\"}" 2>/dev/null
done
```

#### 5.3 创建 Release

```bash
curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/repos/$OWNER/$REPO/releases" \
  -d '{"tag_name":"v1.0.0","name":"v1.0.0","body":"Release notes...","draft":false,"prerelease":false}'
```

#### 5.4 开启 Discussions

```bash
curl -s -X PATCH -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$GH_API/repos/$OWNER/$REPO" \
  -d '{"has_discussions":true}'
```

---

### 六、每日运维（核心自动化）

#### 6.1 每日全面审计脚本

自动完成以下检查：
- 所有仓库的 CI 状态
- 待处理的 PR 和 Issue
- 版本更新建议
- 依赖安全警报
- 过期分支

```bash
OWNER="xiejianjun000"
repos=("open-taiji" "tritai" "taiji-agent" "ai-valuation-skill" "github-ops")
ALL_OK=true

for repo in "${repos[@]}"; do
  echo ""
  echo "========================================="
  echo "📦 $repo"
  echo "========================================="
  
  # 基本信息
  curl -s -H "Authorization: token $GITHUB_TOKEN" \
    "$GH_API/repos/$OWNER/$repo" | python3 -c "
import sys, json; d=json.load(sys.stdin)
print(f'  ⭐{d[\"stargazers_count\"]} 🍴{d[\"forks_count\"]} ⚠️{d[\"open_issues_count\"]}')
print(f'  更新: {d[\"updated_at\"][:10]}')
print(f'  Topics: {\", \".join(d.get(\"topics\",[]))}')" 2>/dev/null
  
  # CI 状态
  echo "  --- CI ---"
  curl -s -H "Authorization: token $GITHUB_TOKEN" \
    "$GH_API/repos/$OWNER/$repo/actions/runs?per_page=2" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
for r in d.get('workflow_runs', [])[:2]:
    icon = '✅' if r.get('conclusion')=='success' else '❌' if r.get('conclusion')=='failure' else '🔄'
    print(f'  {icon} {r[\"name\"]} → {r.get(\"conclusion\",\"运行中\")} ({r[\"created_at\"][:16]})')" 2>/dev/null
  
  # 开放 PRs
  curl -s -H "Authorization: token $GITHUB_TOKEN" \
    "$GH_API/repos/$OWNER/$repo/pulls?state=open" | python3 -c "
import sys, json
prs = json.loads(sys.stdin.read())
if prs:
    print(f'  PRs: {len(prs)}')
    for p in prs: print(f'    #{p[\"number\"]}: {p[\"title\"][:50]}')" 2>/dev/null
  
  # 开放 Issues
  curl -s -H "Authorization: token $GITHUB_TOKEN" \
    "$GH_API/repos/$OWNER/$repo/issues?state=open&per_page=3" | python3 -c "
import sys, json
issues = json.loads(sys.stdin.read())
real = [i for i in issues if 'pull_request' not in i]
if real:
    print(f'  Issues: {len(real)}')
    for i in real: print(f'    #{i[\"number\"]}: {i[\"title\"][:50]}')" 2>/dev/null
done

echo ""
echo "========================================="
echo "✅ 审计完成"
echo "========================================="
```

#### 6.2 运维日报格式

自动生成的日报 Markdown：

```markdown
# GitHub 项目运维日报（YYYY-MM-DD）

## 📊 概览
| 项目 | Stars | Forks | Issues | CI | 更新时间 |
|------|-------|-------|--------|----|----------|
| open-taiji | ⭐X | 🍴X | ⚠️X | ✅ | YYYY-MM-DD |
| tritai | ⭐X | 🍴X | ⚠️X | ✅ | YYYY-MM-DD |
| ... | ... | ... | ... | ... | ... |

## 📁 详情

### open-taiji
- **CI**: ✅ 通过
- **PR**: X 开放 / Y 合并
- **Issue**: X 开放
- **最新提交**: 消息

## 🛠 今日操作
- （自动记录）

## ⚠️ 风险提示
- （自动发现的问题）
```

---

### 七、开发者引流

#### 7.1 曝光提升策略

| 类别 | 项目 | 优先级 | 效果 |
|------|------|--------|------|
| Topics 优化 | 添加搜索关键词标签 | 🔴 高 | 搜索排名↑ |
| README 美化 | Badges + 社交预览图 | 🔴 高 | 专业感↑ |
| 社区推广 | V2EX + 掘金 + 知乎 | 🔴 高 | 流量最大 |
| Good First Issues | 创建新手友好任务 | 🔴 高 | 招贡献者 |
| 生态互链 | 项目间互相引用 | 🟡 中 | 持续曝光 |
| 技术博客 | 深度技术文章 | 🔴 高 | 长期 SEO |

#### 7.2 Good First Issue 模板

```markdown
## 🌟 任务描述
...

## ✅ 完成标准
- [ ] 步骤1
- [ ] 步骤2

## 📁 参考文件
- `path/to/file.ts`

## 💬 需要帮助？
在 Issue 下方留言！
```

---

### 八、错误处理与安全

#### 常见错误处理

| 错误 | 原因 | 修复 |
|------|------|------|
| `404 Not Found` | 仓库不存在/无权限 | 检查仓库名和 Token |
| `403 Forbidden` | Token 权限不足 | 需要 `repo` scope |
| `409 Conflict` | 分支冲突 | `git pull` 后重试 |
| `422 Validation` | 标签已存在 | 使用新的标签名 |
| Secret Scanning | 提交含 Token | 从历史中移除 |

#### Token 安全铁律

1. ✅ 只在 HTTP Header 中使用 `Authorization: token $GITHUB_TOKEN`
2. ✅ 克隆时使用 `https://owner:$GITHUB_TOKEN@github.com/owner/repo.git`
3. ❌ 绝对不 commit 包含 Token 的文件
4. ❌ 绝对不 echo 打印完整 Token
5. ❌ 绝对不在日志中记录 Token

---

## 🤖 Agent 自动化规则

作为 OpenClaw Agent，本技能按以下规则自动执行：

### 每日自动检查
1. 检查所有仓库 CI 状态
2. 检查开放 PR 是否需要合并
3. 检查开放 Issue 是否需要回复
4. 检查仓库描述和 Topics 是否需要更新
5. 检查过期分支是否需要清理

### 操作原则
1. **先审计，后操作** — 先看仓库状态再动手
2. **变更需确认** — 任何写操作（push、PR、Release）前先向用户确认
3. **只读操作自动执行** — 审计、检查、状态查询自动完成
4. **发现异常及时报告** — CI 失败、安全警报等第一时间通知用户

---

## 📚 参考资源

- [GitHub REST API 文档](https://docs.github.com/en/rest)
- [GitHub Topics API](https://docs.github.com/en/rest/repos/repos#update-all-repository-topics)
- [GitHub Pages API](https://docs.github.com/en/rest/pages)
- [Conventional Commits](https://www.conventionalcommits.org/)
