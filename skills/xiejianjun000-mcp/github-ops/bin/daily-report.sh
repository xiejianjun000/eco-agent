#!/bin/bash
# GitHub 运维日报生成脚本
# Usage: GITHUB_TOKEN="ghp_xxx" bash bin/daily-report.sh

set -e

if [ -z "$GITHUB_TOKEN" ]; then
  echo "❌ 缺少 GITHUB_TOKEN 环境变量"
  exit 1
fi

GH_API="https://api.github.com"
OWNER="xiejianjun000"
REPOS=("open-taiji" "tritai" "taiji-agent" "ai-valuation-skill" "github-ops")
DATE=$(date '+%Y-%m-%d')

echo "# GitHub 项目运维日报（$DATE）"
echo ""
echo "## 📊 项目概览"
echo "| 项目 | Stars | Forks | Issues | CI | 更新 |"
echo "|------|-------|-------|--------|----|------|"

for repo in "${REPOS[@]}"; do
  DATA=$(curl -sf -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "$GH_API/repos/$OWNER/$repo" 2>/dev/null)
  
  if [ -z "$DATA" ]; then
    echo "| $repo | ❌ | ❌ | ❌ | ❌ | 获取失败 |"
    continue
  fi
  
  STARS=$(echo "$DATA" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['stargazers_count'])" 2>/dev/null)
  FORKS=$(echo "$DATA" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['forks_count'])" 2>/dev/null)
  ISSUES=$(echo "$DATA" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['open_issues_count'])" 2>/dev/null)
  UPDATED=$(echo "$DATA" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['updated_at'][:10])" 2>/dev/null)
  
  # Check CI
  CI_STATUS=$(curl -sf -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "$GH_API/repos/$OWNER/$repo/actions/runs?per_page=1" 2>/dev/null | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
runs = d.get('workflow_runs', [])
if runs:
    c = runs[0].get('conclusion','')
    print('✅' if c=='success' else '❌' if c=='failure' else '🔄')
else:
    print('➖')" 2>/dev/null || echo "❓")
  
  echo "| $repo | ⭐$STARS | 🍴$FORKS | ⚠️$ISSUES | $CI_STATUS | $UPDATED |"
done

echo ""
echo "## 📁 各项目详情"
echo ""

for repo in "${REPOS[@]}"; do
  echo "### $repo"
  
  DATA=$(curl -sf -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "$GH_API/repos/$OWNER/$repo" 2>/dev/null)
  
  if [ -z "$DATA" ]; then
    echo "- ❌ 无法获取仓库信息"
    echo ""
    continue
  fi
  
  echo "$DATA" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
print(f'- **描述**: {d.get(\"description\",\"无\")}')
print(f'- **语言**: {d.get(\"language\",\"N/A\")}')
print(f'- **许可**: {d.get(\"license\",{}).get(\"spdx_id\",\"无\") if d.get(\"license\") else \"无\"}')" 2>/dev/null
  
  # CI
  echo "- **CI**:"
  curl -sf -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "$GH_API/repos/$OWNER/$repo/actions/runs?per_page=3" 2>/dev/null | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
for r in d.get('workflow_runs', [])[:2]:
    icon = '✅' if r.get('conclusion')=='success' else '❌' if r.get('conclusion')=='failure' else '🔄'
    print(f'  - {icon} {r[\"name\"]} ({r[\"created_at\"][:10]})')" 2>/dev/null
  
  # PRs
  PR_COUNT=$(curl -sf -H "Authorization: token $GITHUB_TOKEN" \
    "$GH_API/repos/$OWNER/$repo/pulls?state=open" 2>/dev/null | python3 -c "import sys,json; print(len(json.loads(sys.stdin.read())))" 2>/dev/null || echo "0")
  echo "- **PR**: $PR_COUNT 开放"
  
  # Issues
  echo "- **Issue**:"
  curl -sf -H "Authorization: token $GITHUB_TOKEN" \
    "$GH_API/repos/$OWNER/$repo/issues?state=open&per_page=3" 2>/dev/null | python3 -c "
import sys, json
issues = json.loads(sys.stdin.read())
real = [i for i in issues if 'pull_request' not in i]
if real:
    for i in real: print(f'  - #{i[\"number\"]}: {i[\"title\"][:50]}')
else: print('  - 无')" 2>/dev/null
  
  # Latest commit
  echo "- **最新提交**:"
  curl -sf -H "Authorization: token $GITHUB_TOKEN" \
    "$GH_API/repos/$OWNER/$repo/commits?per_page=1" 2>/dev/null | python3 -c "
import sys, json
commits = json.loads(sys.stdin.read())
if commits:
    c = commits[0]
    msg = c['commit']['message'].split(chr(10))[0][:60]
    author = c['commit']['author']['name']
    date = c['commit']['author']['date'][:10]
    print(f'  - {msg} ({author}, {date})')" 2>/dev/null
  
  echo ""
done

echo "## 🛠️ 今日运维操作"
echo "- 待记录..."
echo ""
echo "## ⚠️ 风险提示"
echo "- 待记录..."
