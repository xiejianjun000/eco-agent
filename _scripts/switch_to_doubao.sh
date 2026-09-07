#!/usr/bin/env bash
# 把 eco agent 切到豆包（火山方舟），并实测验证。
#
# 用法：
#   bash _scripts/switch_to_doubao.sh <ARK_API_KEY> [provider]
#
#   provider 可选：
#     doubao_plan  （默认）智能体计划订阅包，模型 ark-code-latest
#                  —— 若你的额度是「Agent Plan / 智能体计划」订阅，用这个
#     doubao        按量付费方舟，模型 doubao-pro-32k 或 ep-xxx endpoint
#
# 脚本会：先实测 key 可用性 → 写入 .env → 重启服务 → 真实对话验证
set -u

REPO="/Users/mac/Documents/deepseek/eco-agent"
KEY="${1:-}"
PROVIDER="${2:-doubao_plan}"
PORT=8321

if [ -z "$KEY" ]; then
  echo "用法: bash _scripts/switch_to_doubao.sh <ARK_API_KEY> [doubao_plan|doubao]"
  exit 2
fi

cd "$REPO" || exit 1

if [ "$PROVIDER" = "doubao_plan" ]; then
  BASE="https://ark.cn-beijing.volces.com/api/plan/v3"
  MODEL="ark-code-latest"
else
  BASE="https://ark.cn-beijing.volces.com/api/v3"
  MODEL="doubao-pro-32k"
fi

echo "── 1/4 实测 key（$PROVIDER / $MODEL）"
CODE=$(curl -s -m 25 -o /tmp/ark_probe.json -w "%{http_code}" \
  "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":5}")
echo "   HTTP $CODE"
if [ "$CODE" != "200" ]; then
  echo "   ✗ key 不可用，未改动任何配置。返回："
  head -c 400 /tmp/ark_probe.json; echo
  echo "   提示：若这是「智能体计划」订阅请用 doubao_plan；若是按量付费方舟请用 doubao，"
  echo "         且 model 可能需要填 endpoint id（ep-xxxxx）。"
  exit 1
fi
echo "   ✓ key 可用"

echo "── 2/4 写入 .env（备份原文件）"
cp .env ".env.bak.$(date +%Y%m%d_%H%M%S)"
python3 - "$KEY" "$PROVIDER" "$MODEL" <<'PY'
import re, sys
key, provider, model = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(".env", encoding="utf-8").read()

def upsert(text, k, v):
    pat = re.compile(rf"^{re.escape(k)}=.*$", re.M)
    return pat.sub(f"{k}={v}", text) if pat.search(text) else text.rstrip("\n") + f"\n{k}={v}\n"

src = upsert(src, "ECO_PROVIDER", provider)
src = upsert(src, "ARK_API_KEY", key)
src = upsert(src, "ECO_MODEL", model)
src = upsert(src, "ECO_DEFAULT_MODEL", model)  # chat 走这个变量
open(".env", "w", encoding="utf-8").write(src)
print(f"   ECO_PROVIDER={provider}  ECO_MODEL={model}  ARK_API_KEY={key[:10]}...")
PY

echo "── 3/4 重启服务"
P=$(lsof -ti:$PORT 2>/dev/null | head -1)
[ -n "$P" ] && kill "$P" && sleep 2
cat > /tmp/start_eco.sh <<EOF
cd $REPO
set -a
[ -f "\$HOME/.eco/.env" ] && . "\$HOME/.eco/.env"
[ -f .env ] && . ./.env
set +a
exec .venv-mcp/bin/python -m eco.cli server --port $PORT --host 127.0.0.1
EOF
nohup bash /tmp/start_eco.sh > /tmp/eco_server.log 2>&1 &
sleep 8

echo "── 4/4 真实对话验证"
R=$(curl -s -m 60 -X POST "http://127.0.0.1:$PORT/api/v1/chat" \
  -H 'Content-Type: application/json' \
  -d '{"message":"只回复两个字：正常","stream":false}')
echo "$R" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    r=d.get('reply','')
    print('   模型:', d.get('model'))
    print('   回复:', r[:120])
    print('   ✓ 切换成功，可以开始验收' if '失败' not in r and 'HTTP 4' not in r
          else '   ✗ 仍有错误，见上方 reply')
except Exception as e:
    print('   解析失败:', str(e)[:100])
"
echo
echo "Web UI: http://127.0.0.1:$PORT/"
