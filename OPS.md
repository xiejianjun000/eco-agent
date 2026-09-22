# eco Agent 生产运维手册

> 这是 eco Agent 第一个正式上线生产部署项目的运维基线，作为后续所有项目的运维标杆。

## 部署环境

- 主机系统：macOS 15.7.4（x64）
- 运行时：Node.js v22.19.0
- 服务：eco Agent Web UI（端口 8088）
- 进程管理：launchd（label `com.eco.agent-web`）
- 代码仓库：`xiejianjun000/eco-agent`（本地 `/Users/mac/dev/deepseek-harness`）

## 访问信息

- 地址：`http://127.0.0.1:8088/?token=<动态生成>`
- 裸访问 `/` 返回 401（正常，需带 token）
- token 获取：`tail ~/.eco/web.log | grep -oE 'http://[^ ]+' | tail -1`（每次重启会变）

## 自动化运维（3 个 cron 全自动运转）

| 运维项 | cron id | 频率 | 脚本 | 干什么 |
|--------|---------|------|------|--------|
| 服务守护 | `3b9342eb2664` | 每 5 分钟 | `eco-agent-heartbeat.py` | 探测 8088 存活，挂了 `launchctl kickstart` 拉起；顺带轮转日志 |
| git+CI 监控 | `ff02484db0bd` | 每 30 分钟 | `eco-agent-git-ops.py` | 查未提交改动、本地/远程同步、CI 最新 push run 失败 |

三个 cron 全部 `no_agent=true`（纯脚本，零 token 消耗）、`silent-on-success`（健康时静默，异常才告警）、`deliver=all`（异常 fan-out 到所有通道）。

## 运维脚本

- `~/.hermes/scripts/eco-agent-heartbeat.py`
  - HTTP GET 健康检查（401 也算 alive，连接失败才算 dead）
  - 宕机用 `launchctl kickstart -k` 拉起（launchd 管理，不 kill+Popen）
  - 日志轮转：`~/.eco/web.log` / `web.err.log` 超 10MB 自动改名 `.1` 备份并清空
- `~/.hermes/scripts/eco-agent-git-ops.py`
  - git 未提交改动检查（`git status --porcelain`）
  - 本地 vs 远程 main 同步（`gh api` 对比 SHA，避免 fetch 断连）
  - CI 最新 `push` 事件 run 检查（`--event push` 过滤，避免 dependabot/pages 误报）

## 服务管理

```sh
# 重启服务
launchctl kickstart -k gui/$UID/com.eco.agent-web

# 查看服务状态
launchctl list | grep eco.agent

# 查看日志
tail -f ~/.eco/web.log
tail -f ~/.eco/web.err.log
```

## 故障排查

| 现象 | 排查 |
|------|------|
| 8088 无响应 | `launchctl list \| grep eco.agent`，无记录则 `launchctl load ~/Library/LaunchAgents/com.eco.agent-web.plist` |
| 服务反复宕机 | 看 `~/.eco/web.err.log` 末尾报错 + `~/.hermes/scripts/eco-agent-heartbeat.py` 的 `/tmp/eco-agent-heartbeat.log` |
| 收到 git/CI 告警 | 跑 `~/.hermes/scripts/eco-agent-git-ops.py` 看具体告警内容 |
| token 失效 | 重启服务后 token 会变，重新从 web.log 取 |

## 发布流程

1. 本地改完 `pnpm run typecheck && pnpm run lint && pnpm run build`
2. `git commit --no-verify` + `git push --no-verify eco-agent main`
3. `launchctl kickstart -k gui/$UID/com.eco.agent-web` 重启加载新 bundle
4. 从 web.log 取新 token，浏览器验证
