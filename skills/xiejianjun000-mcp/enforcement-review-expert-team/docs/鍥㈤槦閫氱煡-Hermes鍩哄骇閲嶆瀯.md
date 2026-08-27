# 团队通知：EcoAegis AuthService 重构为 Hermes 插件架构

## 概述

EcoAegis 的 AuthService（环保政务平台自动登录与会话管理）已完成从独立脚本到 **Hermes 插件** 的架构迁移。`hermes-agent` 是 EcoAegis 的 **后端基座**，所有自动化任务由 hermes 统一调度执行。

## 变更说明

| 变更项 | 旧方案 | 新方案 |
|--------|--------|--------|
| 调度方式 | 独立 crontab + bash 脚本 | hermes cron 统一调度 |
| 心跳检测 | `probe_session.py` 独立 Python 脚本 | `auth_health` hermes 工具 |
| 自动登录 | `auto_login.js` 手动触发 | `auth_login` hermes 工具 |
| 告警通知 | `notify.sh` 文件落盘 | hermes cron deliver 投递到消息平台 |
| 配置文件 | `platforms.config.json` 独立维护 | `plugins/ecoaegis/adapter.py` 内聚 |

## Hermes 基座定位

- **Hermes 是后端运行时**：所有 EcoAegis 自动化任务（心跳、登录、告警、巡更）由 `hermes-agent` 内置的 cron 调度器驱动，不再依赖系统 crontab。
- **插件化扩展**：EcoAegis 作为 hermes 插件（`plugins/ecoaegis/`）注册，提供 4 个工具：`auth_health`、`auth_login`、`auth_captcha`、`auth_setup_cron`。
- **技能驱动**：hermes agent 通过 SKILL.md 理解如何使用这些工具，可自主编排心跳 → 检测异常 → 触发登录 → 告警的完整链路。

## 文件结构

```
hermes-agent/plugins/ecoaegis/
├── plugin.yaml         # 插件声明
├── __init__.py         # 入口
└── adapter.py          # 工具实现 (auth_health / auth_login / auth_captcha / auth_setup_cron)

EcoAegis/
├── auto_login.js       # 保留为底层实用脚本，由 auth_login 工具调用
├── decode_captcha.py   # 保留为 OCR 辅助
└── auth/state/         # storageState + 心跳账本（由 hermes 工具读写）
```

## 后续操作

1. 用 `hermes cron create` 注册心跳和巡更作业（运行 `auth_setup_cron` 获取命令模板）。
2. 配置告警投递通道（Telegram/Feishu/邮件等）。
3. 移除系统 crontab 中的旧作业（`crontab.example` 已废弃）。

## 不变项

- `auto_login.js` 和 `decode_captcha.py` 保持独立可用，不依赖 hermes 也能手动执行。
- macOS Keychain 凭据存储策略不变。
- `auth/state/` 目录下的 storageState 和心跳账本格式不变。

---

*以上变更已提交至 master 分支，有疑问在群里讨论。*
