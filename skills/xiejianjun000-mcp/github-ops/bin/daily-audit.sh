#!/bin/bash
# GitHub 每日仓库审计脚本
# Usage: GITHUB_TOKEN="ghp_xxx" bash bin/daily-audit.sh

set -e

if [ -z "$GITHUB_TOKEN" ]; then
  echo "❌ 缺少 GITHUB_TOKEN 环境变量"
  exit 1
fi

GH_API="https://api.github.com"
OWNER="xiejianjun000"
REPOS=("open-taiji" "tritai" "taiji-agent" "ai-valuation-skill" "github-ops")
ALL_OK=true

echo "========================================="
echo "  🔧 GitHub 仓库每日审计报告"
echo "  日期: $(date '+%Y-%m-%d %H:%M')"
echo "  仓库数: ${#REPOS[@]}"
echo "========================================="

for repo in "${REPOS[@]}"; do
  echo ""
  echo "📦 $repo"
  echo "----------------------------------------"
  
  # 基本信息
  DATA=$(curl -sf -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "$GH_API/repos/$OWNER/$repo" 2>/dev/null)
  
  if [ -z "$DATA" ]; then
    echo "  ❌ 无法获取仓库信息 (可能 Token 权限不足或仓库不存在)"
    ALL_OK=false
    continue
  fi
  
  echo "$DATA" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
print(f'  ⭐ Stars: {d[\"stargazers_count\"]}  🍴 Forks: {d[\"forks_count\"]}  ⚠️ Issues: {d[\"open_issues_count\"]}')
print(f'  📅 更新: {d[\"updated_at\"][:10]}')
print(f'  📝 描述: {d.get(\"description\",\"无\")[:80]}')
topics = d.get('topics', [])
if topics: print(f'  🏷️  Topics: {\", \".join(topics)}')" 2>/dev/null
  
  # CI 状态
  echo "  --- CI 状态 ---"
  CI_DATA=$(curl -sf -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "$GH_API/repos/$OWNER/$repo/actions/runs?per_page=3" 2>/dev/null)
  
  CI_FAIL=false
  echo "$CI_DATA" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
runs = d.get('workflow_runs', [])
if not runs:
    print('  ➖ 无 CI 运行记录')
    sys.exit(0)
for r in runs[:3]:
    icon = '✅' if r.get('conclusion')=='success' else '❌' if r.get('conclusion')=='failure' else '🔄'
    print(f'  {icon} {r[\"name\"]} → {r.get(\"conclusion\",\"运行中\")} ({r[\"created_at\"][:16]})')
# Exit with error if any failed
for r in runs:
    if r.get('conclusion') == 'failure':
        sys.exit(1)
" 2>/dev/null && CI_FAIL=false || CI_FAIL=true
  if [ "$CI_FAIL" = true ]; then ALL_OK=false; fi
  
  # PR 状态
  echo "  --- PR 状态 ---"
  curl -sf -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "$GH_API/repos/$OWNER/$repo/pulls?state=open" 2>/dev/null | python3 -c "
import sys, json
try:
    prs = json.loads(sys.stdin.read())
    if not isinstance(prs, list):
        print('  ➖ 无法获取 PR 信息')
    elif prs:
        print(f'  📬 待处理 PR: {len(prs)}')
        for p in prs:
            lag = (__import__('datetime').datetime.now(__import__('datetime').timezone.utc) - __import__('datetime').datetime.fromisoformat(p['created_at'].replace('Z','+00:00'))).days
            print(f'    #{p[\"number\"]}: {p[\"title\"][:50]} ({lag}天前)')
    else:
        print('  ✅ 无待处理 PR')
except: print('  ➖ 无 PR 信息')" 2>/dev/null
  
  # Issue 状态
  echo "  --- Issue 状态 ---"
  curl -sf -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "$GH_API/repos/$OWNER/$repo/issues?state=open&per_page=5" 2>/dev/null | python3 -c "
import sys, json
try:
    issues = json.loads(sys.stdin.read())
    if not isinstance(issues, list):
        print('  ➖ 无法获取 Issue 信息')
    else:
        real = [i for i in issues if 'pull_request' not in i]
        if real:
            print(f'  📋 开放 Issue: {len(real)}')
            for i in real[:3]:
                lag = (__import__('datetime').datetime.now(__import__('datetime').timezone.utc) - __import__('datetime').datetime.fromisoformat(i['created_at'].replace('Z','+00:00'))).days
                labels = ','.join(l['name'] for l in i.get('labels',[]))
                print(f'    #{i[\"number\"]}: {i[\"title\"][:50]} ({lag}天前) [{labels}]')
        else:
            print('  ✅ 无开放 Issue')
except: print('  ➖ 无 Issue 信息')" 2>/dev/null
done

echo ""
echo "========================================="
if [ "$ALL_OK" = true ]; then
  echo "  ✅ 所有仓库状态正常"
else
  echo "  ⚠️ 部分仓库存在异常，请查看上方详情"
fi
echo "========================================="
