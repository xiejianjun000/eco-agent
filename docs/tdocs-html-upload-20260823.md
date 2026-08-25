# 腾讯文档 HTML 一键上云 — 实现与测试报告（2026-08-23）

> 追加（同日）：完成文档后**自动在 Web 界面右侧预览面板打开**，不再弹系统浏览器。

## 〇、右侧预览面板（新增）

- 服务端：`/api/v1/chat/stream` 识别 `X-ECO-CLIENT: web` 请求头；
  工具结果或最终回答中出现 `docs.qq.com` 链接时，发 `document` 轨迹事件；
  `open_url` 对 docs.qq.com 链接不再开系统浏览器，返回 `opened: side_panel` 标记。
- 前端：ChatView 新增「预览」页签——收到 `document` 事件自动切换并加宽右侧面板，
  iframe 内嵌打开文档；最终回答兜底扫描链接；「↗ 新标签页」逃生按钮。
- 实测（Playwright 无头浏览器）：发送指令后 `预览` 页签自动激活、
  面板自动加宽、iframe 加载真实腾讯文档应用（frame 标题 = 文档真实标题）。
  无头环境未登录腾讯文档故显示登录提示；军哥浏览器已有登录态（cookie 共享），直接渲染全文。
  若面板内提示登录，点「↗ 新标签页」登录一次后回面板刷新即可。

## 一、目标

数据分析 HTML 报告（如空气质量分析、排污单位在线监测分析）一键变成腾讯文档在线文档，
拿到可分享的 `docs.qq.com` 链接。对齐官方 `.aipage` 导入工作流
（`ecoskills/tencent-docs/references/aipage_references.md`），
并把原 `import_file.sh` 的 **mcporter CLI 依赖换成 Python 直连 MCP**。

## 二、管线四步（`agent_core/tdocs_import.py`）

```
① node aipage_pack.js --html <path> [--title]   → .aipage + SIZE + MD5（零依赖打包）
② manage.pre_import{file_name,file_size,file_md5} → upload_url + file_key + task_id
③ HTTP PUT <upload_url>（octet-stream 直传 COS）
④ manage.async_import → manage.import_progress 每 3s 轮询（≤60s）→ file_id + file_url
```

- 鉴权：`Authorization: TENCENT_DOCS_TOKEN`（Streamable HTTP 会话，复用 `_mcp_session` 开箱模式）
- 健壮性：pre_import/async_import 失败重试 2 次（间隔 5s）；轮询容忍任务注册延迟的
  瞬时错误（实测 `11607:docID not match pattern` 首轮必现，8s 内自愈）；
  腾讯文档 MCP 输出 schema 与实返不一致（如 `modify_time` 实返字符串）→ 校验降级放行。
- 权限：聊天通道 L2（PERMISSION.md `tool_risk_overrides`），决策写 SM3 审计链。

## 三、接线清单

| 层 | 位置 | 内容 |
|:---|:-----|:-----|
| 核心管线 | `agent_core/tdocs_import.py` | `tdocs_upload_html(path, title)` / `tdocs_upload_html_bytes()` |
| 工具定义 | `server/api/chat.py` `_codex_tools()` | `tdocs_upload_html{path,title}` |
| 工具分发 | `server/api/chat.py` `_run_tool()` | 权限闸门 → 管线调用 → JSON 结果 |
| 审计台账 | `server/api/chat.py` `_tool_level/_tool_category` | L2 / write |
| 接线清单 | `agent_core/wiring_manifest.py` | WIRED_REQUIRED + CHANNEL_DISPATCHED |
| 权限豁免 | `profiles/eco-agent/PERMISSION.md` | L2 自动放行 |
| 单测 | `tests/modules/test_tdocs_import.py` | 8 例 |

## 四、测试结果

### 4.1 单元测试（8/8 通过）

真实 `node aipage_pack.js` 打包 + mock MCP 会话/PUT：happy path、缺字段报错、
token 缺失报错、async_import 直返短路、轮询瞬时错误容忍、PUT 失败。

### 4.2 活体 E2E（3 份真实文档已上云）

| 文档 | 链接 | 耗时 |
|:-----|:-----|:-----|
| 冷水江市空气质量月度分析报告 | https://docs.qq.com/page/DWmhRSVNSVVJnc2pp | 首测（调试中发现瞬时错误规律） |
| 重点排污单位在线监测数据分析报告 | https://docs.qq.com/page/DWmVyY3FSbmNWYVNh | 5.8s |
| 冷江空气质量分析（聊天通道实测） | https://docs.qq.com/page/DWm9SYnpWbHJXZll1 | 模型自主调用工具 |

- 三份文档均经 `manage.search_file` 反查证实（file_id / ext=page / url 一致）。
- 聊天通道实测：模型自主调 `tdocs_upload_html` 并返回正确链接。
- 注意：`manage.get_content` 对 `page` 类型文档返回空内容（读取工具边界，不影响导入）。

### 4.3 回归

- `pytest tests/` 全量通过（含 test_tool_wiring 接线一致性）。
- `_scripts/lint.py` 通过。
- 服务器重启后健康检查 OK，`/api/v1/chat` 通道实测通过。

## 五、已知边界

- 上云后文档为 `page`（智能页面）类型，内容读取工具 `get_content` 对 page 类型返回空，
  需要读回时用 `manage.search_file` 定位 + `open_url` 打开链接查看。
- 聊天通道首次调用时模型可能需要在提示词中看到工具描述才会主动使用；
  直接命令式请求（"用 tdocs_upload_html 把 X 上传"）实测稳定触发。
- 3 份实测文档为军哥腾讯文档账号下的真实产物，可保留作为能力自证，也可删除。
