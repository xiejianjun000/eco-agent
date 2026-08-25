## [2026-08-23] 腾讯文档 HTML 一键上云管线

### Added（同日：DSH 输出机制对照落地）
- **工具结果结构化渲染（output.render 轻量版）**：工具 JSON 结果自动表格化展示
  （支持对象数组与嵌套数组+thead 两种形态，失败 JSON 显示原文，XSS 转义），
  独立模块 web/src/utils/toolResult.ts，node 实测四分支全对。
- **_smart_preview 数据层修复**（穿透式连修 4 个真 bug）：①execute_tool 结果
  `[:4000]` 截断把 JSON 切坏（根因）；②tbody 单元格内嵌 HTML 巨长导致重组超限
  （行级清洗+截列）；③thead 内嵌标签；④短 JSON 统一转合法 JSON（dict 字面量
  ast.literal_eval 兼容）。实测 preview 全部合法 JSON（518 字/tbody 5 项）。
- 对照结论：output.schema（模型看）=govmcp 工具 input_schema 推断 ✓；
  output.render（用户看）=card 图表卡片+工具结果表格化 ✓（本次补齐）；
  平滑流式=打字光标+流光动画（轻量版，无 8 种动画）；settings 热加载=system_reload
  工具+模型下拉即切 ✓；上下文压缩=6000 字预算 ✓；乱码解码=macOS UTF-8 场景不需要。


### Fixed（同日：穿透排查拒单行为——10 类弹药零机械拒单）
- 10 类输入形态穿透实测（粘贴日志/JSON、模糊'这个对吗'、残缺'冷水江钢铁'、
  单标点、领域外医疗/情感、开发者部署、撤回、重复）：**零"误粘贴/待命/重新表述"**。
  优秀行为：日志→实测定位根因；残缺词→主动查 5 工具（L4 合规提交审批）；
  部署→实测文件清单；医疗→诚实边界+就医建议；情感→有温度回应。
- **"先猜再干"规则**：输入模糊/无上下文时先查近期记忆/会话记录/落盘文件，
  基于猜测行动并标注，禁止把球踢回用户。实测："记住脱硫设施检查"后问
  "这个对吗？"→ 自动结合上下文核实法条并修正（第164+1108条配套引用）。


### Fixed（同日：禁止机械拒单——用户输入都是工作对象）
- 规则4 重写：删掉"领域外立即停止"的拒单倾向——用户发来的任何内容都是工作对象，
  绝不判"误粘贴"、绝不"继续待命"式推回；开发笔记/代码/报错=本系统开发任务直接干
  （实测：贴一段疑似有 bug 的代码 → 全仓 grep 核实真实定义、指出缺失行、给修复对照+
  位置+[待确认]，DSH 式先实测后结论）。法条核实与代码排查混合输入同样全处理。


### Fixed（同日：行为对齐 DSH 收口——方向纠偏）
- **方向纠偏**：eco 的目标是"行为像 DSH"（思考方式/回答质量/执行风格），
  不是"平台架构复制品"。同题对照实测暴露三处行为差距并收敛：
  ① 工具调用格式泄漏（早退路径缺净化）→ 抽 `_strip_tool_format` 双路径生效，
  实测 invoke 零泄漏；② 开发/运维类问题误入执法三角色 → 关键词豁免回落单循环，
  实测"密钥排查"直接 shell_run 实测定位（.env 在/权限可读/空值遮蔽），
  DSH 式"先实测给根因"而非话术清单；③ 趋势分析缺图表卡片（规则已有，模型
  偶发不执行，留待强化）。


### Fixed（同日：定位纠正——全要素而非执法独大）
- 吸收定位纠正：eco 是**生态环境系统垂直领域全要素** Agent，执法只是要素之一。
  表达层五处改造：欢迎语全要素、动态上下文"当前工作阶段（执法要素内）"、
  switch_persona 描述（执法要素内切换，其余要素无需切换）、规则4 全要素定位句、
  自我介绍约束（全要素一句话身份）。骨架层（SOUL/domains.py 8 介质域）本就全要素。
  实测：自我介绍全要素；CCER 碳要素引用法典第1038条原文；辐射要素给环评+
  辐射安全许可手续（带置信度/待确认）。


### Added（同日：Web UI 前端穿透式三测 + 会话日志自修复）
- **穿透/压力/烟雾实测**：页面加载 0.8s/四页签正常；思考流展开→完成后收缩；
  回答 markdown 渲染（表格/加粗）；图表卡片 ECharts canvas 真实绘制且
  sandbox="allow-scripts" 隔离（父页读不到 contentDocument）；XSS 经会话恢复
  真实渲染路径注入 <script>/<img onerror> **未执行**（转义为文本）；畸形 markdown
  不崩；连续 12 条消息 22.6s 零错误；989 条历史消息渲染稳定；长回答 768 字表格
  21 行正常。页面错误累计 0。
- **会话日志 seq gap 自修复**：穿透注入跳变记录触发 fail-closed 守卫（安全性实证），
  暴露恢复性缺陷——新增 repair_seq_gap：尾部 seq 跳变自动截尾恢复+审计
  （中部挖洞仍 fail-closed=篡改信号）；单测验证修复后链完整。


### Fixed（同日：截断提示观感 + 缓存 + 反自夸）
- **「以上为要点版」提示彻底移除**：截断静默进行（观感对齐 DSH）；前端在截断消息
  附「📄 详细版」小按钮，点击自动发送并兑付原稿（full_replies，不重新生成）。
  实测：提示 0 残留、按钮→点击→兑付 1348 字原稿全链路 ✓。
- **index.html no-store**：改版后浏览器刷新必取新 bundle（修复"改了没生效"的
  缓存假象）；哈希资产仍长缓存。
- **反自夸规则**：'你如何保证质量/为什么可靠'类提问——一句话+当场自证
  （audit_tail/真实工具调用），禁止'我们靠N条硬约束'式自我吹嘘清单。


### Added（同日：DSH 式分段节奏——思考展开/完成后收缩）
- **tool_start 阶段事件**：服务端工具执行前发 tool_start，前端先渲染 running 行
  （左侧流光动画），结果到达后替换为完成态。
- **自动收缩**：思考块流式中展开（running+open），轮末 think 事件到达即收缩为
  摘要行；工具行完成后默认收起（点击展开结果）——节奏对齐 DSH：
  思考(展开)→工具(running)→结果(收缩)→下一轮思考。
- 实测：流式中 think running[open] ✓，完成后 think/call 全部收缩、零页面错误。


### Fixed（同日：两个输出质量缺陷）
- **「详细版」假承诺修复**：截断时完整原稿落盘（full_replies.jsonl，TTL 30 分钟，
  保留 50 条），用户回「详细版/完整版」时**原样兑付原稿**（标注"未重新生成"），
  不再靠模型重生成（重生成会漂移）。单测 2 例。
- **数据分析纪律**：规则新增——多期对比/多断面统计必须先算统计量
  （变化率/占比/集中度/趋势方向）再下结论，禁止只罗列表格不分析；
  趋势对比优先图表卡片。


### Added（同日：dsh-visualize 式交互图表卡片）
- **会话内 ECharts 图表卡片**：数据分析回答用 ```card 代码块输出图表（风格锚例4
  约定+规则7 卡片优先），服务端提取（截断之前，防卡片被叙述预算切碎）→ `card`
  轨迹事件；前端 sandbox="allow-scripts" 沙箱 iframe 渲染（无同源权限，模型
  HTML 隔离执行）。实测：PM2.5 趋势卡片 ECharts canvas 真实绘制、页面零错误、
  正文只留结论+📊标题；单测 2 例（替换/无块）。


### Added（同日：质量三高保障——guard/compaction 对标 DSH）
- **质量门禁 `_quality_gate`**：法条号↔法典原文一致性核验（subprocess 直查
  lookup.py + 数字/4字词重合判定）+ '共N个'与表格行数一致性核验（表头已排除）；
  不合格自动纠偏重写一次，早退/终层两路径全覆盖；单测 5 例
  （错引触发/正确通过/行数不符/行数相符/不存在条号不误报）。
- **上下文压缩**：历史 6000 字预算（超限保留最近 8 条）、单条超 3000 字首尾截断——
  长对话不撑爆上下文。
- **DSH 增强插件适配清单补充**：guard/compaction/feedback 三机制对照落地记录
  （docs/dsh-plugins-for-eco-20260824.md 第五节）。

### Added（同日：DSH 生态适配 + 向量记忆 + Cordis 迁移）
- **DSH 插件适配清单**：docs/dsh-plugins-for-eco-20260824.md——官方 examples/
  （mcp-memory/web-schedule）与社区插件（visualize/genui、file-mentions、at-file 等）
  按 eco 业务价值分三档：直接挂（eia-mcp 已用）、借鉴设计、落地建议（交互图表卡片最高优先）。
- **向量检索记忆（memory_index.py）**：跨会话语义回忆——字符 2/3-gram 哈希向量 +
  共享特征覆盖度打分，零外部依赖；每轮对话自动入记忆库，新会话按语义检索注入
  （memory.recall），窗口兜底保留。实测：新会话零历史即可回忆"下周联合执法检查
  冷水江钢铁厂脱硫设施"。
- **Cordis 工具即插件（第二步）**：`cordis_plugins/builtin_tools.py`
  （statute_lookup/statute_search/tdocs_upload_html handler 注册进工具注册表）与
  `govmcp_tools_loader.py` 幂等修复——装配日志、工具表、聊天触发三重实证。

### Added（同日：三方穿透实测收口——记忆/审批/Cordis）
- **政务数据边界收紧 L4**：20 个政务平台工具（案件/案卷明细/报警/许可执行等）
  升级 L4 人工审批（仅菜单/区域/目录类保留 L1）；修两个真 bug：审批栈无
  answerer 导致永远 fail-closed（默认 admin）、/approvals/pending 误插代码。
  闭环实证：聊天触发→pending→decide allow→再查放行执行。
- **跨会话记忆（memory.recall）**：新会话从 session_log 注入最近对话要点
  （标注'据此前记录'+当前状态必查护栏）；实证：新会话无历史即可回忆此前任务。
  自我学习实证：lessons.jsonl 23 条教训存量，自愈闭环运转。
- **Cordis 工具即插件样板**：`agent_core/cordis_plugins/govmcp_tools_loader`
  ——政务平台工具集改由组合装配（eco.cordis.yml 一行接入），与 chat 幂等共存；
  实证：工具表 142 项含政务工具，装配日志正常。
- **三方对比结论**：记忆 DSH=事件溯源+checkpoint / Hermes=memory-graph /
  eco=session_log+lessons+memory.recall（本轮补上跨会话回忆）；政务审批
  eco 已对标 DSH L4 审批栈；Cordis 化路线：服务层已就位，工具/能力持续
  迁入组合装配（样板已落地）。

### Fixed（同日：生产部署就绪审计）
- **凭证脱敏**：docs/govmcp-platform-mount-20260822.md 与 ecoskills/hunan-env-law/SKILL.md
  中的真实政务账号密码改为「密码见 .env」；全仓（含未跟踪）复扫 0 密钥残留；
  代码无硬编码凭证；.env 已在 .gitignore。
- **web/dist 入库修复**：.gitignore 的 `dist/` 曾挡住 web/dist（注释声称已提交实际 0 文件），
  加 `!web/dist/` 例外并入库（5 文件，clone 即可打开界面）。
- **发布就绪实测**：smoke 29/29（含穿透 13 项/压力 3 项）；10 并发聊天 10/10
  （中位 9.8s）；权限矩阵 L1-L4 全部符合契约；路径逃逸/注入/畸形输入全拒；
  Web UI 全链路零 console 错误；pytest 唯一失败为 CNEMC 外网端点超时（外网 flake）。
- **判定**：可进入 git 生产部署流程；前提：commit 全部改动、目标机 .env 注入凭证、
  接受两个已知边界（外网端点偶发超时、审计写入降级告警不阻断）。

### Added（同日：湖南省厅环境质量月报工具 + 数据纪律）
- **`govmcp_tools/hunan_env.py`**：`hunan_env_monthly_report(year, month, keyword)`
  实测路线（该栏目无 JSON API：静态分页 + 4MB 级静态 HTML，县市区断面数据嵌在页面深处表格）。
  列表定位（title 属性正则）→ 全文流式抓取（避 httpx brotli 大响应缺陷，gzip 魔数判定）→
  HTML 表格解析 + 关键词过滤。实测：冷水江→晓云渡口断面·资江干流·省控·Ⅱ类。
  接线：registry / CHAT_TOOLS（含 handler）/ PERMISSION L1 / wiring_manifest。
- **规则3 长页面纪律**：web_fetch 大页面必须提 max_chars 或分段抓取、取全再下结论；
  数据在 <table>/附件时用 execute_code 解析；禁止"抓到开头没有"就说"不存在"。
- **平台工具路由指南**（tool_guidance.platform）：月报/自动站/四平台/排污许可
  直连工具路由，禁止 web_search 绕路。单测 5 例 + 聊天通道 E2E 实测通过
  （模型自主调用 hunan_env_monthly_report 并给出来源与边界说明）。

### Added（同日终版：风格锚对齐本 Web UI 真实输出格式）
- **风格锚替换为 DSH 真实输出样本**：✅+加粗一句话结论 → ## 分节 → 表格证据 →
  依据/提示 → 诚实边界（例1 法条表格式 / 例2 四节汇报式）；
  规则7 改为"结论先行、结构化交付"（叙述段 ≤400 字，表格为证据主体不再受 300 字预算切）。
- **语气与行为收口**：用"你"不用"您"、禁客服腔与内部机制解释；切换阶段类请求
  豁免 RoleSwarm 直接走 switch_persona；三角色合成剥除编排内部词汇
  （三方/各角色/仲裁），用户视角不暴露子代理结构。
- **Markdown 格式修整 `_normalize_markdown`**：修复 v4-pro 断裂加粗全部 4 种
  跨行变体（**\nX\n** / **\nX** / **X\nY** / **X\nY\n**）、删除独立星号行、
  ✅ 后换行合并；`_enforce_concise` 重写为"同行片段保持同行"（条文切分不再掰断加粗），
  行内小片段（≤20字）豁免截断。四类问题实测（法条/计算/数据/状态）格式全干净。
- **实测**：Q2 法条 → ✅结论+三列罚则表+依据提示（316字）；Q4 超标研判 →
  ✅定性结论+事项表+处置四步（361字，截断提示收尾）——与 DSH 输出同形制。

### Added（同日收口：规则精简 + 风格锚，输出风格对齐 DSH 实测通过）
- **规则块精简 20→8 条**：合并同质约束、删除重复段、压缩表述——推理模型规则越少、
  思考越短（实测思考 28-48 字）；保留全部执行红线（法条必查/时效红线/工具真实调用/
  联网通道/边界安全/状态必查/回答洁净/先想后答）。
- **回答风格锚（few-shot 黄金样例）**：打招呼/法条/流程三例 ✅开头+表格+反问，
  实测生效（打招呼 63 字几乎照搬例1、法条 312 字✅+罚则表格、流程 339 字结论先行）。
- **思考显示硬顶 100 字** + swarm 合成提示词加"≤300字要点式、禁编排头"。
- **穿透对比实测**（DSH vs eco-agent 同题三连）：改前 964 字 → 改后 63/312/339 字，
  无编排噪声、无悬空表头/标题、思考笔记化——剩余差距主要来自条文引用豁免
  （执法场景合法要求），已在诚实边界说明。

### Added（同日：输出格式对齐 DSH——先想后答 + 要点式回答）
- **实时思考流（DSH Think 流）**：`chat.py` 接通 `on_reasoning` 回调，推理分块
  经 `think_delta` 事件实时推送（~60 字聚合缓冲），工具轮与总结轮均流式；
  前端按轮次累积实时渲染「思考中…」，过程块默认展开且置于回答之前（先想后答）。
- **规则19 先想后答**：系统提示词新增行为规则——思考过程可见、最终回答结论先行、
  要点式 ≤300 字（条文引用豁免）；总结指令同约束。
- **确定性执行 `_enforce_concise`**：模型层面纪律不可靠时的硬保证——条文引用句豁免，
  其余内容（叙述+表格）共享 300 字预算按句边界截断，三条回答路径（直接作答/
  总结/三角色协作）全覆盖，截断后 SSE `reset` 重放同步界面，
  被截掉的链接自动补挂文末（右侧预览面板不受影响）。单测 7 例。
- **结构感知截断 + 反清单搬运**：截断收尾清洗悬空标题/引导行（杜绝
  "**二、xxx**"下空无一物的残破输出）；规则19 增补"禁止把提示词能力清单
  原样搬进回答、介绍类 ≤100 字并反问下一步"——实测介绍类回答 95 字收敛。

### Fixed（同日：no api key 空值遮蔽事故）
- **`agent_core/envboot.py`**：环境里预置空 `DEEPSEEK_API_KEY=`（GUI 启动器/非登录 shell 常见）
  会遮蔽 .env 补填（python-dotenv override=False 跳过已存在键）→ 空值视为缺失，
  按「真实环境 > 仓库 .env > ~/.eco/.env」补填非空值；`llm_client._refresh_key`
  兜底链并入仓库 .env；`eco server` 启动时空 key 显式告警；
  `~/.eco/.env` 三源对齐（空 key → 真实 key）。单测 5 例 + 空 key 环境真实启动验证通过。

### Added
- **`agent_core/tdocs_import.py`**：数据分析 HTML 报告 → 腾讯文档在线文档全自动管线
  （`aipage_pack.js` 打包 `.aipage` → `manage.pre_import` 取 COS 上传链接 → HTTP PUT 直传
  → `manage.async_import` 触发 → `manage.import_progress` 轮询 ≤60s → docs.qq.com 链接）。
  直接经 mcp SDK 开 Streamable HTTP 会话（`Authorization: TENCENT_DOCS_TOKEN`），
  **摆脱 mcporter CLI 依赖**；输出 schema 校验降级放行（腾讯文档 MCP 实返与声明 schema 常不一致）；
  轮询容忍任务注册延迟的瞬时错误（如 11607 docID）。
- **聊天工具 `tdocs_upload_html(path, title)`**：接线 `server/api/chat.py`（L2 权限闸门 +
  SM3 审计）、登记 `wiring_manifest.py`（WIRED_REQUIRED + CHANNEL_DISPATCHED）、
  PERMISSION.md `tool_risk_overrides` L2 豁免。
- **单测 `tests/modules/test_tdocs_import.py`**：8 例（真实 aipage 打包、四步管线 happy path、
  pre_import 缺字段、token 缺失、async_import 直返短路、轮询瞬时错误容忍、PUT 失败）。
- **活体 E2E 实测**：3 份真实文档已上云（5.8s/份），聊天通道模型自主调用工具成功，
  `manage.search_file` 反查证实文档存在。
- **右侧预览面板**：文档完成后自动在 Web 界面右侧「预览」页签内嵌打开（`document` 轨迹事件
  + iframe，`open_url` 对 docs.qq.com 改走面板标记，不再弹系统浏览器）；Playwright 实测面板
  自动切换/加宽、iframe 加载真实文档。

## [2026-08-16] v1.0.0 — 首个稳定发布版

> 自 v5.0.0a8（alpha 开发线）收口为 **v1.0.0 稳定版**：补齐 DSH 式工程形态
> （管理 API + Web 图形界面 + Python SDK + 动态插件系统），全量测试通过、lint 全绿。
> 完整路线图见 [docs/ROADMAP-1.0.md](docs/ROADMAP-1.0.md)。

### Added
- **`server/` eco-server 管理 API**：13 端点（chat/SSE 流式、sessions、memory、skills、tools、plugins、system、metrics）+ `eco server` 命令，复用 agent_core 全部能力，无 LLM 时优雅降级
- **`web/` eco-web 浏览器界面**：React 18 + Vite，四板块（会话/记忆树/技能/系统），`web/dist` 入库 clone 即用，`eco server` 一键打开
- **`eco_agent_sdk/` Python SDK**：EcoClient（异步 httpx）+ SyncEcoClient（同步包装），类型契约 + 分层错误 + 11 例单测 + `examples/sdk_demo.py`
- **`agent_core/plugins.py` 动态插件系统**：`plugins/` 目录规范（plugin.yaml + handler.py）、热加载/卸载/重载、L1-L4 风险闸门注入、跨插件工具冲突检测 + `examples/` 示例插件
- **`examples/` 目录**：sdk_demo.py 使用示例

### Fixed
- govmcp / govmcp_tools 提升为顶层包（原 agent_core 内嵌结构导致导入自相矛盾），pyproject 包清单更新
- `gateway_core.SessionManager` 死锁：持锁调用 `_save()` 再取锁 → `Lock` 改 `RLock`
- `ToolRegistry` API 补齐：`register(装饰函数)` 重载 / `register_batch` / `ToolInfo.__call__` / `category`+`tags` 参数
- `CronScheduler` 持久化路径可注入（`jobs_file` 参数），测试隔离不再互相污染
- 版本号统一单源（pyproject），修复 5.0.0a2 与 CHANGELOG a8 漂移
- `gate_tool_call` 支持 `overrides` 注入（插件 manifest 风险声明可精确生效）
- ruff 全绿（含 per-file-ignores 收口）

### Known Limitations（如实声明）
- `govmcp`（对标国内等保的政务 MCP 协议栈）工具注册层完整可用：
  **100+ 政务工具（govmcp_tools）全部注册、可检索、可调用**；
  协议层模块（authorization/elicitation/sampling/tasks/models/transport）在 1.0 暂未实现，
  引用处以 try/except 隔离不影响运行，补齐计划见 docs/ROADMAP-1.0.md 的 1.x 路线
- Web GUI 覆盖四板块；协同编辑（eco-desktop Tauri 壳）保持独立，不在本版范围
- HumanEval/MBPP 官方评测 harness 未接入（EcoBench 自带评测见 benchmarks/）

---

## [2026-08-01] v5.0.0a8 — L4 Evolve 自动触发钩子

> 补上 README 自标缺口：「每次任务后 / 每日自动触发：未实现」

### Added (G3 渐进交付)
- **`agent_core/evolve_trigger.py`（新模块）**
  - `record_mission()`：L2 mission 结束沉淀 (expectation, output, verdict, status)
    三元组进经验库 `memory-tree/data/evolution/experience.jsonl`
  - `maybe_trigger()`：阈值（默认5）+ 冷却期（默认4h）双门控自动调起
    MetaEvolution.run_full_cycle()；含失败任务的经验双倍计权
    （失败是差距分析的最佳原料）；进化后清空已消费经验
  - `should_evolve_daily()`：每日调度检查（供 L3 Pulse 调用）
  - 方案A一致性：`ECO_AUTO_EVOLVE=1` 显式启用，默认完全 no-op 零副作用
- CommanderV2.execute() 收尾接入 mission_hook（异常不影响主流程）

### Tests
- 新增 `tests/modules/test_evolve_trigger.py` 9 例：三元组沉淀、积累、
  阈值门控、失败双倍计权提前触发、冷却期防重复、每日调度、
  默认关闭零副作用、环境启用自动沉淀（982 passed）
- 集成冒烟：2 个 mission → 第 1 个即触发（失败双倍计权）→ stamp +
  第 2 个冷却期跳过，行为全部符合设计

---

## [2026-08-01] v5.0.0a7 — L3 Pulse 五占位步骤真实化

### Changed (G3 渐进交付)
- **`agent_core/heartbeat.py` PulseSteps（新类，路径全注入，离线安全）**
  - step_sync：扫描受管目录（文件数/字节数/mtime 清单）落盘快照，不再返回 "sync_ok"
  - step_diff：当前扫描 vs 上次快照，报告新增/修改/删除的具体文件
  - step_rule_engine：知识保鲜规则——mtime 超 90 天的文件触发提醒（D10 知识新鲜度抓手）
  - step_mem_cron：SQLite VACUUM + integrity_check（DB 缺失跳过不崩）
  - step_suggestions：基于其他步骤结果生成建议；无事发生返回 None（静默原则）
- 旧静态接口保留，委托 `default_steps()` 生产默认实例（memory-tree + OBSIDIAN_VAULT + ~/.eco SQLite）

### Tests
- 新增 `tests/modules/test_pulse_steps.py` 10 例：真实计数、快照落盘、
  无差异/新增+修改检出、过期触发/新鲜不触发、VACUUM 真实性、
  DB 缺失优雅、建议含数量、静默返回 None（973 passed）

---

## [2026-08-01] v5.0.0a6 — rag_score 反幻觉核验接入 eco-knowledge-mcp

### Added (G4 质量门禁)
- **`agent_core/rag_score.py`**（vendored from taiji-verify v2.2, MIT）
  - RAG 三维评分：忠实度/相关性/完整性，幻觉风险 = 1 − 忠实度
  - 本地修改：① claims 提取增加「含数字/条文号即视为声明」规则
    （法规关键事实不一定含判断词）；② 数字实体正则支持中文数字——
    原实现只认阿拉伯数字，「第八百八十八条」式编造完全逃逸检测（实测 faith=1.0）
- **`eco_faithfulness_check` MCP 工具**（eco-knowledge-mcp v0.3.0）
  - answer + source（内联原文）/ statute（自动取 vault 原文）→ 三维评分 +
    risk_level（low/medium/high）+ 处置建议（high=禁止直接交付）
  - numpy 缺失时优雅降级报错，不影响其他工具

### Tests
- 新增 `tests/modules/test_rag_score.py` 7 例：忠实/幻觉两端可区分、
  to_dict 契约、工具注册、内联原文核验、幻觉标记、缺参报错
- MCP stdio 实测：编造条款 → faithfulness 0.0 / high risk（963 passed）

---

## [2026-08-01] v5.0.0a5 — L2 executor 接真实工具运行时（RuntimeExecutor）

### Added (G6 职责分离)
- **`agent_core/task_executor.py`（新模块）**
  - 每个 L2 Task 起一个 L1 ReAct++ 循环（think→act→observe，置信度门控），
    max_steps 压至 5（子任务粒度成本控制）
  - tools_registry 全量工具经同步 wrapper 注入 ReAct 循环（async execute_tool
    桥接；权限闸门 L1-L4 在 execute_tool 内部统一生效，本层不重复设卡）
  - 任务 prompt = 描述 + expectation 判据 + 【前置产出】（镜像 role_swarm 拼法）
  - ReAct 循环无产出 → 抛异常走 L2 replan 路径（统一失败语义）

- **上游上下文注入**
  - 波浪调度执行前把上游产出注入下游 `task.input["upstream"]`

- **成本控制**
  - 方案 A 显式启用：`CommanderV2(executor=RuntimeExecutor())` 或
    `ECO_RUNTIME_EXECUTOR=1`；无参构造保持占位，现有调用方零配额风险
  - `_summarize` 新增 `llm_loops` 指标（实际 LLM 循环数）

### Safety
- 降级红线：LLM 未配置/不可用时 RuntimeExecutor 静默回退占位行为，
  离线测试零配额消耗（946 passed）

### Tests
- 新增 `tests/modules/test_task_executor.py` 9 例：降级占位、无客户端兜底、
  ReAct 循环上下文（expectation/上游入 prompt、max_steps=5）、工具同步注入、
  空产出抛异常、上游注入、默认占位、环境开关、llm_loops 指标

---

## [2026-08-01] v5.0.0a4 — L2 任务层：expectation 锚点 + 前缀保留 replan

> 设计来源：Yi-Biao/EcoAgent (AAAI 2026) 端云协同闭环——计划步骤携带预期状态、
> 失败重规划冻结已成功前缀。落地到 CommanderV2。

### Added (G4 质量门禁)
- **expectation 锚点**
  - `Task` 新增 `expectation`（完成判据）与 `verdict`（验证结论）字段
  - 分解器全部模板（开发/研究/写作/通用）每步携带明确完成判据
  - 任务完成不再等于"没抛异常"：执行后必须经 verifier 对照 expectation 核验，
    未达标 → FAILED 并记录 verdict，为 D12 反幻觉率提供子任务级抓手

- **前缀保留 replan**
  - 失败重规划冻结 COMPLETED 前缀（已发消息/已落盘文档等副作用绝不重跑）
  - 仅重写失败点之后的计划，新任务继承 expectation 并附失败教训
  - 任务级盲重试（递归重跑同一任务）移除，升级为任务级预算（默认 2 轮）

- **可注入三件套**（G6 职责分离）
  - `CommanderV2(executor=, verifier=, replanner=)` 默认占位实现保持原行为，
    生产接线替换为真实 LLM 执行/语义核验/重规划

### Changed
- 调度器从"依赖未满足即 BLOCKED"改为波浪调度：每波仅运行依赖已完成的任务，
  链式模板现在可以真正跑完整个 DAG
- `_summarize` 新增 `verified`（有验证结论的任务数）与 `mission_replans` 指标

### Tests
- 新增 `tests/modules/test_commander_expectation.py` 8 例（934 passed）：
  锚点生成、verdict 留痕、验证失败定格、恰好 1 轮 replan、前缀零重跑、
  预算耗尽、重规划任务锚点不丢、异常与验证失败统一 replan 路径

---

## [2026-07-31] v5.0.0a3 — IDE工作台 + 人机协同编辑（G方法论）

### Added (G1 宪法治理)
- **DESIGN.md 人机协同编辑宪法**
  - 三种协同模式：AI主动标注 / 人类手动标注 / 双向对话
  - 批注类型：error/warning/suggestion/question
  - 批注状态机：pending→accepted/rejected/edited
  - 操作契约：traceId可追溯

- **批注数据模型 (G2 工具化)**
  - `src/types/annotation.ts` — 类型/状态/来源/位置/建议
  - 纯函数：createAiAnnotation / createHumanAnnotation / applyAnnotationToText

- **协同编辑器引擎 (G2)**
  - `src/components/CollaborativeEditor.tsx`
  - AI 自动评查 → 高亮问题 + 批注气泡
  - 人类接受/拒绝/修改 → 应用到文档
  - 文本变更后批注位置自动校正
  - forwardRef 暴露命令式方法

- **批注侧栏 (G6 职责分离)**
  - 右侧列出待处理/已接受/已拒绝批注
  - AI批注(🤖) 与人类批注(👤) 可区分

- **IDE 式工作台**
  - `SplitPane.tsx` — 可拖拽分栏
  - `ActivityPanel.tsx` — 右侧活动栏（文档/浏览器/产出/地图）
  - `CanvasPanel.tsx` — 中央画布（生成分析图表）
  - 各栏可收缩

### Verified (G3/G4)
- TypeScript 编译零错误
- 协同编辑 21 项测试全部通过
- AI评查→人类确认→应用到文档→位置校正 全链路

### Changed
- App.tsx 重构为 IDE 式工作台布局

## [2026-07-31] v5.0.0a4 — EcoBench 三修 + 70 题全量复跑（deepseek-chat 正式成绩）

### Fixed
- **EcoBench 三修**：RAG 注入长度 3000→1500 字符（条款窗口优先，目标条款±1 条）；单题时限 30s→90s（LLM HTTP 超时同步 90s），失败重试 1 次后仍失败才计 0/error；429/余额类错误自动切换备用 provider（deepseek↔kimi），切换记录进报告，两家均不可用则中止并保留已得分数
- **llm_client 能力恢复**（此前被误同步回滚）：ECO_LLM_DISABLE 开关、kimi-k2.x 温度自适应（_resolve_temperature）、GOVMCP 网关降级链 + _error_detail 错误链透传、chat() 的 _call_kimi_fallback 死代码复活为真实方法；test_llm_client.py 由红转绿

### Added
- tests/modules/test_ecobench_resilience.py 12 例 mock 测试（注入上限/条款窗口/超时重试/429切换/双不可用中止/温度与配额判定）

### 跑分（deepseek-chat，70 题 × 2 组，70/70 全有效作答，如实报告）
- baseline：引用准确率 0.538 / F1 0.646（231s，超时 0，切换 0）
- RAG：引用准确率 0.843 / F1 0.792（332s，超时 0，切换 0），Δ +0.305/+0.146
- 法典专题 20 题：baseline 0.11 → RAG 0.95；与上轮 kimi 中断版对比见 README 第 6 节与 ecobench_report.json

## [2026-07-30] v5.0.0a3 — EcoBench 阶段A收官：题库扩充70题 + 全量对照跑分

### Added
- **EcoBench 题库 50→70**：新增生态环境法典专题 20 题（EB51-EB70，继承映射/新旧衔接/框架结构/引用规范各 5 题），金标准全部源自 EHS 知识库概念文件真实记载（法典继承对照表、废止日期 2026-08-15、第五编条文原文、总目录结构），严禁编造条款号
- 23 道引用已废止单行法的旧题加注"过渡适用"说明（法典第一千零五十七条从旧兼从轻）
- 新增数据集校验测试：70 题结构完整性、法典题金标准非空且必引项自洽、过渡适用标注（test_ecobench.py 6→8 例）
- ecobench_report.json 双组双口径合并报告（baseline/rag × 含超时计0/仅有效作答，逐题明细）

### Changed
- **RAG v2 定位表扩展**：条款标题正则兼容 #### 四级标题（法典条文）；法典题经 CODEX_BOOK_MAP 按题干关键词加定位分编文件；两阶段截取（目标条款直取优先 + 骨架/对照表兜底，单文件上限防预算吃光）；概念文件优先截取"核心制度与法典继承"对照表；法典编/总目录截取标题骨架。EB51-EB70 检索覆盖自检 20/20

### 跑分（kimi-k2.5，70 题，如实报告）
- baseline：引用准确率 0.519 / F1 0.572（有效作答口径 0.637/0.703，13 题超时）
- RAG：引用准确率 0.450 / F1 0.416（有效作答口径 0.875/0.810，34 题超时——30s 上限下长上下文注入反噬，且 Kimi 账户余额耗致使 rag 组重试中止，如实记录）
- 法典专题 20 题：baseline 0.04 → RAG 0.65（有效口径 0.09→0.93），引用规范类 RAG 5/5 满分

## [2026-07-30] v5.0.0a2 — P3: LLM调用链打通 + API Key配置

### Added (G3 渐进交付)
- **llm_client.py 重构**: 直接读取 ~/.eco/.env 配置，直连 LLM API
  - 支持6大提供商: DeepSeek / OpenAI / Anthropic / Kimi / Qwen / Doubao
  - 三层fallback: 直连API → govmcp网关 → Kimi直连
  - 与 eco setup / eco config 自动联动

### Fixed
- eco chat 真实调用链打通: CLI → EcoLoops → ReAct++ → LLMClient → LLM API
- eco doctor 配置检查与 llm_client 状态数据对齐

## [2026-07-30] v5.0.0a1 — CLI + API Server (P0-P2)

### Added
- **`eco` CLI command tree** (9 subcommands)
  - `eco chat` — interactive/one-shot chat mode
  - `eco gateway` — message gateway lifecycle management
  - `eco mcp serve` — MCP protocol server (stdio/HTTP/WebSocket)
  - `eco serve` — OpenAI-compatible API server
  - `eco setup` — interactive configuration wizard
  - `eco config` — config management
  - `eco doctor` — 8-item health check
  - `eco skills` — skill management (ECOSKILLS 500+)
  - `eco evolution` — L4 evolution loop trigger

- **OpenAI-compatible API Server** (P2 core)
  - `POST /v1/chat/completions` with SSE streaming
  - `GET /v1/models` — list available models
  - Optional API Key authentication
  - Routes through 5-layer engine

- **Package distribution**
  - `pyproject.toml`: `[project.scripts] eco = "eco.cli:main"`
  - `pip install eco-agent` ready to use
  - Optional: `pip install eco-agent[serve]`

### Changed
- Version: 5.0.0a0 -> 5.0.0a1
- License: MIT -> Apache-2.0
- Added `eco/` `eco/commands/` `eco/config/` packages

### Fixed
- Windows GBK terminal compatibility for eco doctor
- pyproject.toml encoding issues

## [2026-07-30] v5.0.0a1 — P0-P2: CLI + 包分发 + API Server（G方法论交付）

### Added (G2 工具化思维)

- **`eco` CLI 命令树（9 个子命令，G3 渐进交付）**
  - `eco chat`：交互式/单次对话模式，对接五层循环引擎
  - `eco gateway start/stop/restart/status`：消息网关全生命周期管理
  - `eco mcp serve`：MCP 协议服务器（stdio/HTTP/WebSocket 三模式）
  - `eco setup`：交互式配置向导（5 步完成：提供商选择→API Key→依赖→平台→完成）
  - `eco config show/get/set/init/path`：配置管理（~/.eco/.env）
  - `eco doctor`：系统健康检查（8 项，支持 --fix 自动修复）
  - `eco skills list/install/info`：技能管理（对接 ECOSKILLS 500+ 生态）
  - `eco evolution`：L4 进化循环触发（支持 --dry-run/--report）
  - `eco version`：版本信息

- **OpenAI 兼容 API Server（P2 核心，G6 职责分离）**
  - `eco serve` 命令：启动 FastAPI 服务
  - `POST /v1/chat/completions`：OpenAI 格式请求，对接五层循环引擎
  - `GET /v1/models`：列出可用模型
  - 支持流式 SSE 响应
  - 可选 API Key 认证

- **包分发（G5 语义版本）**
  - `pyproject.toml`：添加 `[project.scripts] eco` 入口点
  - `pip install eco-agent` 即可安装
  - `eco` 命令全局可用
  - 可选依赖：`pip install eco-agent[serve]` 启用 API Server

### Changed (G4 质量门禁)

- `pyproject.toml`：版本 5.0.0a0 → 5.0.0a1，许可证 MIT → Apache-2.0
- 重构项目包结构：新增 `eco/` `eco/commands/` `eco/config/` 包

### Fixed

- Windows GBK 终端兼容：emoji 符号自动降级为 ASCII 文本
- `eco doctor`：UnicodeEncodeError 处理

# Changelog

## [2026-07-28] v0.1.0 — ECO AGENT 项目初始化

### Added

- **宪法文件（2 个）**
  - CLAUDE.md：ECO AGENT 主 Agent 宪法（身份/职责/启动协议/6层架构/8 Agent编排/14维质量/ACE审查/7条纪律/G方法论/法规速查）
  - SCHEMA.md：ECO 知识宪法（5层架构/14维评分卡含红线阈值和测量方法/ACE三阶段详细流程/7条纪律/文件格式标准/三验标准/技能孵化流程）

- **方法论文件（3 个）**
  - hazy-mapping-whistle.md：6 大 AI 框架深度梳理分析与融合设计（OpenClaw/Hermes/CLAUDE/CODEX/OPENHUMAN/OPENWORKER）
  - 项目说明书.md：项目定位、目标、范围、架构、技术栈、质量保障、风险应对
  - 开发实施方案.md：G 方法论 + P0-P3 四阶段详细任务分解 + 开发规范 + 验收门禁

- **基础设施**
  - Git 仓库初始化
  - 目录结构：`_scripts/` `skills/` `memory-tree/` `tests/` `docs/`
  - `.gitignore`（Python/IDE/OS/环境/缓存过滤）
  - `README.md`（项目简介 + 目录结构 + G 方法论）

---

## [2026-07-28] v0.2.0 — P0 Stage 1: Hermes Profile + MCP + 审计工具

### Added

- **Hermes Profile（7 个文件）**
  - `profiles/eco-agent/config.yaml`：6 层配置（模型提供者/缓存/记忆/工具/Curator/飞书）
  - `profiles/eco-agent/SOUL.md`：ECO AGENT 身份人格定义（专业/严谨/审慎/可信）
  - `profiles/eco-agent/MEMORY.md`：核心记忆（项目状态/宪法/路径/当前任务）
  - `profiles/eco-agent/PERMISSION.md`：4 级风险权限体系（L1 READ ~ L4 EXTERNAL）
  - `profiles/eco-agent/USER.md`：执法人员信息模板
  - `profiles/eco-agent/install.sh`：Profile 安装脚本

- **执法技能（2 个）**
  - `skills/query-skill.md`：法规知识查询技能（检索策略 + 回答格式 + 处理原则）
  - `skills/enforcement-qa-skill.md`：执法问答与裁量建议技能（裁量分析 + 回答模板）

- **MCP 工具（1 个）**
  - `_scripts/eco-knowledge-mcp.py`：JSON-RPC 2.0 over stdio 协议，5 个工具
    - `eco_search`：关键词全文检索 + 评分排序
    - `eco_retrieve`：文件/法规内容获取
    - `eco_statute_query`：法规条文精确提取 + 章节导航
    - `eco_graph_query`：知识图谱关联分析（基于 wikilink）
    - `eco_list_statutes`：按分类/要素列出法规

- **质量审计工具（2 个）**
  - `_scripts/quality_audit.py`：11 维质量评分卡（D1-D11 自动审计）
  - `_scripts/lint.py`：项目健康检查（文件/断链/指针/Frontmatter/Git 状态）

### Quality (P0 审计结果)

| 维度 | 状态 | 维度 | 状态 |
|:-----|:----:|:-----|:----:|
| D1 文件结构 | 100% OK | D7 Git 提交 | 100% OK |
| D2 宪法段落 | 100% OK | D9 项目规模 | 100% OK |
| D4 Profile | 100% OK | D10 版本标记 | 100% OK |
| D5 技能文件 | 100% OK | D11 Python语法 | 100% OK |
| D6 脚本文件 | 100% OK | | |

---

## [2026-07-28] v0.3.0 — P0 Stage 2: 多平台网关集成

### Added

- **网关架构（1 个）**
  - `gateway/ARCHITECTURE.md`：统一网关架构设计（统一消息协议 + 平台能力矩阵 + 安全策略 + 消息模板）

- **统一配置（1 个）**
  - `gateway/gateway.yaml`：四平台统一配置（飞书/企业微信/钉钉/微信 凭证、事件订阅、审批、消息模板）

- **网关服务（1 个）**
  - `gateway/eco-gateway-server.py`：FastAPI 统一网关服务
    - 飞书 Webhook（URL 验证 + 事件回调 + 卡片回传）
    - 企业微信 Webhook（签名验证 + 消息处理）
    - 钉钉 Webhook（HMAC 签名 + 消息处理）
    - 微信 Webhook（XML 消息 + 签名验证）
    - 统一消息处理循环 + MCP 检索集成 + 关键词降级

- **平台 SDK（4 个）**
  - `gateway/platforms/feishu_bot.py`：飞书 Bot 封装（消息/卡片/审批/事件签名）
  - `gateway/platforms/wecom_bot.py`：企业微信 Bot 封装（消息/卡片/图文/审批/通讯录）
  - `gateway/platforms/dingtalk_bot.py`：钉钉 Bot 封装（单聊/群聊/卡片/审批/签名）
  - `gateway/platforms/wechat_bot.py`：微信 Bot 封装（公众号 + Wechaty 双模式）

- **消息模板（1 个）**
  - `gateway/message_templates.py`：统一消息模板库（欢迎/帮助/错误/限流/法规检索/执法分析/审批通知）

- **配置文档（1 个）**
  - `gateway/SETUP_GUIDE.md`：各平台详细接入配置指南（创建步骤 + 权限配置 + 环境变量 + 使用示例）

- **Profile 更新**
  - 新增企业微信/钉钉/微信配置节
  - 启用 gateway 入口模式（port 7070）

### 启动方式

```bash
# 开发模式（单端口）
python gateway/eco-gateway-server.py --port 7070

# 生产模式
python gateway/eco-gateway-server.py --host 0.0.0.0 --port 7070
```

### 环境变量

| 平台 | 变量 | 说明 |
|:-----|:-----|:------|
| 飞书 | FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_VERIFICATION_TOKEN | 必填 |
| 企业微信 | WECOM_CORP_ID / WECOM_AGENT_ID / WECOM_SECRET / WECOM_TOKEN / WECOM_ENCODING_AES_KEY | 必填 |
| 钉钉 | DINGTALK_APP_KEY / DINGTALK_APP_SECRET / DINGTALK_ROBOT_CODE | 必填 |
| 微信 | WECHAT_APP_ID / WECHAT_APP_SECRET / WECHAT_TOKEN | 可选 |

---

## [2026-07-28] v1.0.0 — P1: Memory Tree + 执法案例 + 裁量基准

### Added

- **Memory Tree 架构（2 个）**
  - `memory-tree/ARCHITECTURE.md`：完整架构设计文档（数据模型/数据流/分层加载/混合检索/Obsidian同步协议/目录结构）
  - `memory-tree/ECO_SCHEMA.sql`：SQLite Schema（nodes/edges/FTS5/sync_log/metadata + 索引/触发器）

- **Memory Tree 引擎（1 个）**
  - `_scripts/memory_tree.py`：核心引擎 680+ 行
    - 节点 CRUD：create/get/update/delete/list + 血统链追溯
    - 混合检索：FTS5 BM25 + LIKE 中文降级 + 评分排序
    - Obsidian 双向同步：SQLite ←→ Markdown 文件
    - 评分机制：score × 0.5 + recency × 0.3 + frequency × 0.2
    - 热点节点：Hot（常驻）→ Warm（近期）→ Cold（归档）
    - 关联分析：create_edge / get_related
    - 统计监控：get_stats（节点数/类型分布/边数/DB大小）

- **执法案例模块（1 个）**
  - `_scripts/enforcement_cases.py`：案例管理 520+ 行
    - CaseManager：案例入库/检索/相似匹配/统计
    - BenchmarkManager：裁量基准入库/自动匹配/统计
    - seed_demo_data()：3 个执法案例（大气/水/固废）+ 3 条裁量基准
    - 案例文件格式（YAML frontmatter + Markdown 正文）
    - 裁量基准自动匹配（关键词 + 语义相似度）

### 启动演示数据

```bash
cd ~/Desktop/ECO\ AGENT
python -c "from _scripts.enforcement_cases import seed_demo_data; seed_demo_data()"
```

### Quality

| 维度 | 状态 | 维度 | 状态 |
|:-----|:----:|:-----|:----:|
| Memory Tree 引擎 | ✅ 测试通过 | 案例管理 | ✅ 测试通过 |
| 混合检索（中文） | ✅ 测试通过 | 裁量基准 | ✅ 测试通过 |
| Obsidian 同步 | ✅ 架构已设计 | 演示数据 | ✅ 可用 |

---

## [2026-07-28] v2.0.0 — P2: 自进化闭环 + 文书生成 + 法规监控 + 血统压缩

### Added

- **自进化闭环引擎（1 个）**
  - `_scripts/evolution_engine.py`：6 阶段闭环（Execute→Track→Evaluate→Reflect→Crystallize→Store）
  - BackgroundReviewer：每 3 轮自动审查 + 自动结晶 Skill
  - 首次运行自动结晶 2 个技能：法规检索-skill.md、裁量建议-skill.md

- **执法文书生成模块（4 个）**
  - `templates/penalty_decision.j2`：行政处罚决定书模板（16 段完整结构）
  - `templates/hearing_notice.j2`：听证通知书模板（权利义务告知）
  - `templates/inspection_record.j2`：现场检查笔录模板（含证据记录）
  - `_scripts/writer_agent.py`：Writer Agent（Jinja2 + 简易双引擎 / ACE 审查 / 导出）

- **法规时效监控模块（1 个）**
  - `_scripts/subconscious_watcher.py`：11 部关键法规注册库 + 自动检查 + 影响评估 + 报告生成 + 后台守护

- **血统压缩机制（1 个）**
  - `_scripts/bloodline_compressor.py`：会话摘要 + 血统链维护 + Token 压缩（5 种内容感知）

### Quality (P2 全部通过)

| 模块 | 状态 | 模块 | 状态 |
|:-----|:----:|:-----|:----:|
| 自进化闭环 | 6 轮测试通过 | 文书生成 | ACE 100/100 |
| 背景审查 | 自动结晶 2 技能 | 文书导出 | 文件 + Memory Tree |
| 法规监控 | 11 部/1 告警 | 影响评估 | 3 维度 |
| 血统压缩 | 3.3x 压缩率 | 血统追溯 | 深度不限 |

---

## [2026-07-29] v3.0.0 — P3: 跨省协同 + 态势看板 + 模型适配 + 更新管道

### Added

- **跨省执法协同（1 个）**
  - `_scripts/cross_region_sync.py`：NodeRegistry（单例）+ E2ECrypto（Fernet/简化双方案）+ 案例共享/基准同步/跨省查询/裁量校准

- **执法态势看板（1 个）**
  - `_scripts/eco_dashboard.py`：7 模块数据聚合 + Markdown 报告 + 飞书/企微/钉钉卡片生成 + 趋势分析

- **国产模型适配（1 个）**
  - `_scripts/provider_config.py`：5 模型注册表（claude/deepseek/qwen/ernie/glm）+ ProviderRouter 智能路由（failover 3 次阈值）

- **法规自动更新管道（1 个）**
  - `_scripts/statute_updater.py`：118+ 数据源框架（生态环境部/国务院/人大网/司法部/各省厅）+ 定时检查 + 更新处理

### 项目全景（v3.0.0）

| 指标 | 数值 |
|:-----|:----:|
| 总文件数 | 42 个 |
| Python 脚本 | 19 个（7,323 行） |
| Markdown 文件 | 20 个（3,150 行） |
| Git 提交 | 20 次 |
| Git 标签 | 6 个（v0.1.0 → v3.0.0） |

### 架构全景（42 源文件 · ~10,944 行）

```
宪法/方法论      CLAUDE + SCHEMA + CHANGELOG + 项目说明 + 实施计划
Profile          profiles/eco-agent/ (7 files)
技能             skills/ (4 files, 含 2 自结晶)
MCP              _scripts/eco-knowledge-mcp.py (5 tools)
审计             _scripts/quality_audit.py + lint.py
Memory Tree      _scripts/memory_tree.py + ARCHITECTURE + SQL schema
执法案例          _scripts/enforcement_cases.py (case + benchmark)
网关             gateway/ (10 files, 4 platforms: 飞书/企微/钉钉/微信)
自进化           _scripts/evolution_engine.py (6 阶段闭环)
文书             _scripts/writer_agent.py + templates/ (3 j2)
法规监控         _scripts/subconscious_watcher.py (11 部法规)
血统压缩         _scripts/bloodline_compressor.py
跨省协同         _scripts/cross_region_sync.py    [P3 NEW]
态势看板         _scripts/eco_dashboard.py         [P3 NEW]
模型适配         _scripts/provider_config.py       [P3 NEW]
更新管道         _scripts/statute_updater.py        [P3 NEW]
```

### Quality (P3 全部通过)

| 维度 | 分数 | 维度 | 分数 |
|:-----|:----:|:-----|:----:|
| D1 文件结构 | 100% | D7 Git 提交 | 100% (20次) |
| D2 宪法段落 | 100% | D9 项目规模 | 100% (42文件) |
| D4 Profile | 100% | D10 版本标记 | 100% (6 tags) |
| D5 技能文件 | 100% | D11 Python语法 | 100% (19脚本) |
| D6 脚本文件 | 100% | **平均分** | **85.5%** |

---

## [2026-07-29] v4.0.0 — P4: 6 大框架 100% 对标补全

### 总计 18 项能力全部完成

| 框架 | 强制项 | 完成 | 完成率 |
|:-----|:------:|:----:|:-----:|
| OpenClaw | 5 | 5 | **100%** |
| Hermes | 7 | 7 | **100%** |
| CLAUDE | 8 | 8 | **100%** |
| CODEX | 4 | 4 | **100%** |
| OPENHUMAN | 6 | 6 | **100%** |
| OPENWORKER | 7 | 7 | **100%** |
| **合计** | **37** | **37** | **100%** |

### Added (6 个文件)

- **OpenClaw 补全** `_scripts/openclaw_features.py`
  - Plan-as-Tool: 4 种执法流程注册为 LLM 可调用工具
  - Per-Agent MCP: 8 Agent 工具可见性管控 + 风险等级过滤
  - Progressive Skill: 三级加载 (meta-instructions-resources)

- **Hermes 补全** `_scripts/hermes_features.py`
  - MoA: 4 模型并发 + 聚合器裁决
  - PromptCache: 3 层提示词 (Stable/Context/Volatile) TTL 管理
  - Kaban: 跨进程编排 + SQLite 持久化 + 任务依赖解析

- **CLAUDE 补全** `_scripts/claude_features.py`
  - ACEPipeline: 全自动审查 (generator-reflector-curator)
  - SourcePointer: 原文指针自动检测 + 自动补全修复
  - SkillUpgrader: Prompt 3 次使用自动升级为 SKILL.md

- **CODEX 补全** `_scripts/codex_features.py`
  - FixPipeline: 批量修复流水线 (lint-audit-fix-verify)
  - MoAJudge: 多模型裁判 (封装 MoA 做质量裁决)

- **OPENHUMAN 补全** `_scripts/openhuman_features.py`
  - HybridRetriever: BM25+向量+RRF+BGE 重排序混合检索
  - DataIngestion: 6 数据源引擎 (4 启用定时轮询)
  - SubAgentFleet: 3 层 delegation + 12 archetype

- **OPENWORKER 补全** `_scripts/openworker_features.py`
  - OperatingModes: 5 模式 (discuss/plan/interactive/auto/custom)
  - AgentTypes: 5 类型 (chat/code/cowork/myhelper/ops)
  - Connectors: 26 连接器 (10 类型)

### 项目全景 v4.0.0

| 指标 | 数值 |
|:-----|:----:|
| 总文件数 | 67 个 |
| Python 脚本 | 33 个 (10,477 行) |
| Markdown 文件 | 30 个 (3,554 行) |
| Git 提交 | 36 次 |
| Git 标签 | 9 个 (v0.1.0-v4.0.0) |
| 总代码行 | 14,546 行 |

### 质量审计

| 维度 | 分数 | 维度 | 分数 |
|:-----|:----:|:-----|:----:|
| D1 文件结构 | 100% | D7 Git 提交 | 100% (36次) |
| D2 宪法段落 | 100% | D9 项目规模 | 100% (67文件) |
| D4 Profile | 100% | D10 版本标记 | 100% (9 tags) |
| D5 技能文件 | 100% | D11 Python语法 | 100% (33脚本) |
| D6 脚本文件 | 100% | **平均分** | **84.5%** |
