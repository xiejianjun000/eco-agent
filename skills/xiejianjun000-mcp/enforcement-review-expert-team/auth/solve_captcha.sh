#!/bin/bash
# 验证码视觉兜底：列出最近的验证码样本，等待人工/Agent 识别
# 用法：./auth/solve_captcha.sh [platform]
# 如果指定了 --auto 模式，则尝试用脚本自动识别最新样本

CAPTCHA_DIR="/Users/mac/EcoAegis/auth/captcha_samples"
PLATFORM="${1:-atmosphere}"

if [ ! -d "$CAPTCHA_DIR" ] || [ -z "$(ls -A "$CAPTCHA_DIR" 2>/dev/null)" ]; then
  echo '{"status":"no_captchas","message":"无待处理验证码"}'
  exit 1
fi

# 最新的验证码文件
LATEST_CAPTCHA=$(ls -t "$CAPTCHA_DIR"/*.png 2>/dev/null | head -1)

if [ -z "$LATEST_CAPTCHA" ]; then
  echo '{"status":"no_png","message":"无PNG验证码文件"}'
  exit 1
fi

echo "{\"status\":\"pending\",\"image\":\"$LATEST_CAPTCHA\",\"hint\":\"Please read this captcha image and provide the 4-character code\"}"
echo ""
echo "=== 验证码图像路径 ==="
echo "$LATEST_CAPTCHA"
echo ""
echo "=== 最近 5 个验证码样本 ==="
ls -lt "$CAPTCHA_DIR"/*.png 2>/dev/null | head -5
