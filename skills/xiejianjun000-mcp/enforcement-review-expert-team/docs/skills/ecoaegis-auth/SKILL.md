---
name: ecoaegis-auth
description: 环保政务平台会话健康检测与自动登录维护.
version: 1.0.0
author: EcoAegis Team
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [auth, automation, government-platform]
    category: devops
    related_skills: []
    config:
      toolsets: [ecoaegis]
---

# EcoAegis Auth 技能

维护环保政务平台（大气监督帮扶 / 水环境管理）的登录会话，确保自动化巡更任务不会因会话过期而静默失败。

依赖 `ecoaegis` 插件提供的 `auth_health` / `auth_login` / `auth_captcha` 工具，由 hermes cron 定时驱动。

## When to Use

- 定时心跳：检查平台登录态是否有效
- 会话过期：发现 STALE / EXPIRED 状态时触发重新登录
- 验证码兜底：OCR 识别失败时查看验证码样本，用视觉模型辅助解码
- 首次部署：初始化 AuthService 并注册 cron 作业

## Prerequisites

- hermes-agent 已安装，`ecoaegis` 插件已启用（`hermes tools` 中勾选 ecoaegis 工具集）
- Node.js 已安装（`auto_login.js` 依赖 Playwright）
- `ddddocr` 已安装：`pip install ddddocr`
- macOS Keychain 中已存储平台凭据：
  ```
  security add-generic-password -a ecoaegis -s atmosphere-user -w "用户名"
  security add-generic-password -a ecoaegis -s atmosphere-pass -w "密码"
  ```

## How to Run

在 hermes 对话中直接说：

```
检测一下环保平台的登录状态
```

或指定特定操作：

```
用 auth_health 查一下 atmosphere 平台
用 auth_login 重新登录大气平台
```

## Quick Reference

| 工具 | 用途 | 副作用 |
|------|------|--------|
| `auth_health [platform]` | 三信号检测会话状态，返回 HEALTHY/STALE/EXPIRED/NO_STATE | 无 |
| `auth_login platform` | 完整自动登录流程（浏览器+OCR+提交） | 更新 storageState 和心跳账本 |
| `auth_captcha [platform]` | 列出最近 10 个验证码样本 | 无 |
| `auth_setup_cron` | 生成 cron 作业创建命令 | 无 |

## Procedure

### 1. 心跳检测

调用 `auth_health`，不传 platform 参数以检测全部平台。

**结果判定：**
- `HEALTHY` → 无需操作，结束
- `STALE` (3-7 天) → 记录告警，下次心跳时若仍 STALE 则触发登录
- `EXPIRED` (>7 天) 或 `NO_STATE` → 立即触发登录
- 日志级别对照：ok → INFO, warning → WARN, critical → ERROR

### 2. 自动登录

调用 `auth_login atmosphere`（或 water），工具内部执行：
1. 启动 Playwright Chromium（复用持久化 profile）
2. 从 Keychain 读取凭据
3. 导航到平台登录页
4. 填充用户名/密码
5. 提取验证码 → ddddocr OCR → 填充提交
6. 判定结果：URL 跳转判断成功 / 错误信息分类判断失败

**重试策略：** 单次调用内部重试 3 次验证码。若全部失败，不循环重试（避免锁号），转步骤 3。

### 3. 验证码视觉兜底

当 `auth_login` 失败且错误类型为 captcha 时：
1. 调用 `auth_captcha` 获取最近的验证码样本路径
2. 用 `read_file` 查看图片文件，或用视觉模型辅助识别
3. 将识别结果手动填入，或等待下次 cron 重试

### 4. 告警投递

心跳/登录结果中的 `severity: critical` 状态需要投递告警。如果配置了 `ECOAEGIS_NOTIFY_CHANNEL`，hermes cron 的 deliver 机制会自动投递到指定消息平台。

## Pitfalls

- **不要连续重试登录**：认证失败 2 次后停止，否则可能触发平台账号锁定（`auto_login.js` 内部已限制 3 次验证码尝试，凭据错误会立即停止）。
- **Keychain 凭据过期**：平台密码变更后必须同步更新 Keychain，否则 `auth_login` 会因 credential_failed 退出。检查方式：`security find-generic-password -a ecoaegis -s atmosphere-pass -w`。
- **ddddocr 准确率仅 40%**：这是已知限制，不要期望 OCR 能稳定通过。验证码样本保存到 `EcoAegis/auth/captcha_samples/` 供升级 OCR 模型使用。
- **storageState 跨进程共享**：`auth_health` 只读取 storageState 文件做 HTTP 探针，不启动浏览器。完整凭据验证需要 `auth_login`。

## Verification

验证 AuthService 是否正常工作：

```
# 1. 检查插件是否加载
hermes tools  # 确认 ecoaegis 工具集已勾选

# 2. 手动执行心跳
在 hermes 对话中: "用 auth_health 检测所有平台"

# 3. 手动执行登录（测试环境）
在 hermes 对话中: "用 auth_login atmosphere"

# 4. 检查产物
ls -la EcoAegis/auth/state/
# 预期: atmosphere.storageState.json + atmosphere.json 存在且近期更新
```
