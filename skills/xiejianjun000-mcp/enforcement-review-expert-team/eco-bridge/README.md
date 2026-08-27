# eco-bridge — EcoAegis ↔ Hermes agent 连接层

## 为什么需要这一层

Hermes agent 是 EcoAegis 的 **AI 基座**（用户原话：*"后端直接以 Hermes agent 作为 AI 基座"*）。
但 Hermes 本质是**通道消息驱动**的运行时——它通过 `gateway/` 接入飞书/企微/钉钉等
通道（webhook 或 websocket），本身**没有给前端直接调用的 REST 接口**。

所以 EcoAegis 前端（React）要以 Hermes 为基座，必须有一个**薄桥接**：

```
EcoAegis React 前端 (app/src)
   │  HTTP (fetch)
   ▼
eco-bridge (server.py)  ← 极薄 HTTP 门面，只做协议适配，不实现 AI 逻辑
   │  驱动
   ▼
Hermes agent 核心
   agent/  hermes_cli/  providers/  tools/
   + 国内三渠道插件 plugins/platforms/{feishu, wecom, dingtalk}
   + 网关框架 gateway/   （通道收发、会话路由）
```

> 这**不是**新建后端服务栈——Hermes 才是后端 AI 引擎，eco-bridge 只是它的门面。
> 符合立项铁律「不新建 FastAPI+PostgreSQL 后端」。

## 连接契约（前后端对齐）

前端实现：`app/src/lib/hermesClient.ts`
后端实现：`eco-bridge/server.py`

| 端点 | 请求体 | 返回 |
|---|---|---|
| `POST /api/platform/match` | `{ address: string }` | `{ matched: boolean, platform?: WhitelistPlatform, reason?: string }` |
| `POST /api/platform/captcha` | `{ platformId: string, sessionToken: string }` | `{ mode: 'ai'\|'manual', value?: string, imageB64?: string }` |
| `POST /api/platform/login` | `{ platformId, username, password, captcha?, remember, sessionToken }` | `{ ok: boolean, status: 'ai_managed'\|'error', message?: string }` |

字段类型（`WhitelistPlatform`）与前端 `app/src/data/whitelist.ts` 保持一致。

## 前端双模式

`hermesClient.ts` 内置 MOCK 开关，由环境变量控制（见 `app/.env`）：

- `VITE_USE_MOCK=1`（默认，当前）：前端不依赖后端，用本地白名单 + 随机验证码跑通 UI。
- `VITE_USE_MOCK=0`：前端直连 `VITE_BRIDGE_BASE`（默认 `http://localhost:8787`），由 Hermes agent 提供真实智能。

## 安全配置（必须）

| 环境变量 | 默认值 | 用途 | 说明 |
|---------|--------|------|------|
| `ECO_BRIDGE_PORT` | `8787` | 监听端口 | |
| `ECO_BRIDGE_BIND` | `127.0.0.1` | 绑定地址 | 仅本机访问；需局域网时设 `0.0.0.0`（配合 TLS+认证） |
| `ECO_BRIDGE_CORS` | `http://localhost:5173` | CORS 允许来源 | 精确匹配，非 `*` |
| `ECO_BRIDGE_PROXY_ALLOW` | （空=代理禁用） | iframe 代理白名单 | **必须设置才能启用 `/api/proxy`**。逗号分隔主机名，如 `114.251.10.199,pwq.sthjt.hunan.gov.cn` |
| `HERMES_REAL` | 空（占位模式） | `1` 启用真实 Hermes 引擎 | |

## 运行（安装 Hermes 依赖之后）

```bash
# 1) 安装 Hermes agent 依赖（在 EcoAegis/hermes-agent 内）
cd ../hermes-agent && pip install -e .

# 2) 启动桥接
cd ../eco-bridge && python server.py        # 默认 :8787
ECO_BRIDGE_PORT=9000 python server.py       # 自定义端口

# 3) 前端切真实模式
echo "VITE_USE_MOCK=0" >> ../Kimi_Agent_Git项目g方法测试/app/.env
```

## 当前状态：对接占位

`HermesCore` 目前是**占位实现**（本地白名单匹配 + 人工验证码 + 直通接管），
目的是把「前端 → 桥接 → 后端」整条链路先彻底打通（前端 MOCK 模式已可独立验证）。
安装 Hermes 依赖后，取消 `HermesCore._ensure_agent()` 中 lazy import 注释，
即可切换到真实 Hermes agent 驱动——无需改动前端与契约。
