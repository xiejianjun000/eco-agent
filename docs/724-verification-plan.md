# ECO AGENT 7×24 全功能能力验证方案

> 版本 v0.1 · 2026-08-16 · 由 DSH 会话制定
> 目标：不靠"感觉"，用可复跑的自动化手段，7×24 持续验证 eco-agent 的**全部功能能力**，
> 每个能力有明确验证方法、频率、通过标准和失败动作，结论全部落盘可审计。

---

## 0. 总口径

- **验证对象 = 能力清单（见 §1）**，清单从代码和 README 提取，任何新能力上线必须先入清单。
- **三层验证**：离线（不耗 API 配额）→ 冒烟（1 条真实调用）→ 全量（评测集/长稳）。
- **验证由外置机制执行**（DSH、脚本、cron、systemd），**不让 eco-agent 自评**——它有业务边界，
  且自评存在利益冲突（它说"我没能力"或"我都行"都不可信，必须以工具返回和脚本输出为准）。
- **所有结果进报告**（`reports/` + 飞书推送），红线项零容忍，非红线项记趋势。

---

## 1. 能力清单（验证对象全集）

| ID | 能力 | 入口/实现 | 已有验证资产 |
|----|------|----------|-------------|
| C1 | 法规条文检索 | `statute_lookup/statute_search`（server/api/chat.py） | 冒烟场景曾跑通，需脚本化 |
| C2 | 知识库检索 | `kb_search/kb_semantic_search`（ehs-kb-ops MCP，SSE） | 同上 |
| C3 | 代码沙箱执行 | `execute_code`（已注册，**待接入聊天通道**） | 无 |
| C4 | 文书落盘 | `save_document`（已注册，**待接入**；Word/Excel 待加依赖） | README e2e 链：chat→tool→落盘 |
| C5 | 联网检索 | web 工具（**待接入**，L4 审批放行） | 无 |
| C6 | 案卷评查 | 25 项一票否决 + 合法性/规范性评分 | evals 案卷摘要类 9 题 |
| C7 | 执法办案 | 立案/调查/告知/决定全流程 | evals 裁量计算类 9 题 |
| C8 | 督察 | 9 类异常信号、整改跟踪 | evals 法规依据类 9 题 |
| C9 | 监测数据研判 | CEMS/趋势/突变漂移恒值（jiance-analysis skill） | evals 监测数据类 9 题 |
| C10 | 裁量建议 | 裁量基准套用（裁量建议-skill） | evals |
| C11 | 法典知识 | eco-codex 1242 条（eco-codex skill） | EcoBench 50/70 题 |
| C12 | 政务工具 | govmcp 7 模块（环保/企业/碳/市民/城管/大气/审批） | 无（需逐工具冒烟） |
| C13 | 五层循环 | Reflex/Reasoning/Subconscious/Pulse/Evolve | longrun_pulse_evolve 剧本 |
| C14 | 心跳 Pulse | `heartbeat.py` 5 步自适应 | longrun --smoke |
| C15 | 进化 Evolve | 每日进化、evolution_report | verify_ops.py 检查报告篇幅 |
| C16 | 记忆系统 | Memory Tree / MEMORY.md / 会话归档 | verify_ops.py 漂移/矛盾检查 |
| C17 | 技能系统 | skills/ + ecoskills/ 加载与触发 | lint.py + verify_ops 快照 |
| C18 | 定时调度 | scheduler cron（自然语言任务） | 无（需观察执行记录） |
| C19 | 自愈 | self_healing 三类故障处理 | 故障注入演练（无资产，需建） |
| C20 | 审计链 | SM3 会话链/权限决策链/govmcp 五要素 | verify_ops 链校验 + quality_audit |
| C21 | 通道 | CLI / gateway:7070 / 飞书 Bot / Web UI / API / SDK | playwright + curl + lark 技能 |
| C22 | 模型韧性 | DeepSeek 主 + provider 降级 failover | 故障注入（断 key 演练） |
| C23 | 观测 | span 树 + OTLP 导出 | observability.py（需接入收集端） |

> 待接入项（C3/C4/C5）接入后，先过 §2 的 L2 冒烟再进生产。

---

## 2. 五级验证（频率 × 深度）

### L0 — 存活层（每 1 分钟，cron/看门狗）
| 检查 | 命令/方式 | 通过标准 | 失败动作 |
|------|----------|---------|---------|
| 进程存活 | `systemctl is-active eco-gateway`（deploy/systemd 已有 service） | active | systemd 自动重启（Restart=on-failure, 5s）；连续 3 次 → P0 飞书告警 |
| 端口 | `curl -sf http://127.0.0.1:7070/health` | HTTP 200 < 2s | 同上 |
| Web UI | curl 首页 200 | 200 | P1 |
| DeepSeek API | 1 token 空请求（带缓存） | 200 | 触发 provider failover → P1 |
| MCP 存活 | ehs-kb-ops SSE ping + flowwiki ping | 2/2 | P1（kb 功能降级提示） |

### L1 — 后台循环层（每 30 分钟，heartbeat 自身 + 外置巡检）
- heartbeat 5 步执行记录有新增且无异常（`~/.eco/` 事件流）
- scheduler 到期任务真实执行（对照 cron list 与实际日志）
- 会话日志 SM3 链 `verify_chain` 通过（`verify_ops.py`）
- 磁盘/内存/CPU 水位 < 80%；日志体积不失控
- 飞书事件通道：发 1 条心跳测试消息 → 断言回执

### L2 — 功能冒烟层（每日 1 次，全离线 + 少量真实调用）
```
# ① 单元测试（离线，零 API 成本）
python3 -m pytest tests/ -q

# ② 项目健康
python3 _scripts/lint.py && python3 _scripts/quality_audit.py && python3 _scripts/verify_ops.py

# ③ 工具冒烟（每个已接工具 1 条真实用例）
python3 _scripts/smoke_tools.py            # 待建：statute_×2/kb_×2/execute_code/save_document/web

# ④ API 端到端（1 轮真实 LLM）
curl -s -X POST http://127.0.0.1:<port>/api/chat -d '{"message":"查法典第28条"}' | 断言含条文原文

# ⑤ Web UI 巡检（playwright-cli）
打开 Web UI → 发消息 → 断言回复气泡渲染、无 Markdown 裸显示、轨迹标签页可点

# ⑥ evals 回归（45 题，真实 LLM，对照基线）
ECO_EVAL=1 python3 -m evals.runner --baseline evals/reports/baseline.json --threshold 0.05
```
通过标准：①②③全绿；④⑤断言通过；⑥总分下降 < 5%（红线：法规类单类 < 80%）。

### L3 — 韧性与全量层（每周 1 次）
- **EcoBench 全量跑分**（50/70 题，金标准，目标 ≥95%）
- **长稳观察**：`longrun_pulse_evolve.py --hours 24`（或压缩版），产出"README 声称 vs 实测"对照
- **故障注入（D14 容错验收）**：杀进程看自愈重启；断 MCP 看降级提示；换 provider 看 failover；
  人为制造记忆矛盾看自愈回滚——全部记录事件流
- **成本/性能**：token 消耗、首 token 时延、P95 响应时间统计

### L4 — 质量与合规层（每月 1 次）
- 14 维评分卡全量审计（quality_audit + 人工抽查 D1 溯源 20 条）
- 等保 3 级核查：SM3 审计链全链验证 + 权限闸门决策抽查 + 密钥/凭证扫描（无明文）
- 技能库盘点：新鲜度、孤岛率、3 次使用孵化规则执行情况
- 用户验收：案卷评查/办案/督察三插件准确率 ≥95% 人工复评

---

## 3. 7×24 运行机制（谁来跑）

| 机制 | 现状 | 动作 |
|------|------|------|
| systemd 守护 | ✅ deploy/systemd/eco-gateway.service（含加固） | 部署到服务器并 enable |
| 定时调度 | ✅ scheduler.py + 系统 crontab | L0/L1 挂系统 crontab（外置，防止 agent 自己死了没人叫） |
| 告警路由 | 飞书凭证已配置 | 新建"ECO 巡检"飞书群：P0 立即 / P1 每小时 / P2 日报 / 周报汇总 |
| 观测 | ✅ observability OTLP 导出 | 接 Jaeger/Tempo 或先落盘 JSON 自建看板 |
| 自愈 | ✅ self_healing | 瞬时故障重试，持久故障降级+告警，死锁强制回滚 |
| 人肉兜底 | — | 军哥每周只看 1 张飞书周报，异常才介入 |

## 4. 落地三步（本次即可开始）

1. **先跑基线**（现有资产全用上）：tests 全量 + lint + quality_audit + verify_ops +
   evals 基线 + longrun --smoke → 出一份《基线体检报告》，作为日后红线参照。
2. **补两个脚本**：`_scripts/smoke_tools.py`（全工具冒烟，收编之前 /tmp 里的验证场景）、
   `_scripts/patrol.py`（一键巡检：L0+L1+L2 汇总 JSON + 飞书推送）。
3. **挂 7×24**：服务器上 systemd + crontab + 飞书告警群 + OTLP 看板，进入持续验证。

## 5. 附录：资产现状（本次会话盘点）

- ✅ 已有：tests/（离线单测）、evals/（45 题+回归阈值）、benchmarks/（EcoBench+长稳剧本）、
  _scripts/{lint,quality_audit,verify_ops}.py、deploy/systemd、observability、heartbeat、
  scheduler、self_healing、server/api、web/、SDK、plugins/
- ❌ 待建：smoke_tools.py、patrol.py、故障注入剧本、OTLP 收集端、crontab 部署、
  飞书告警群接入、C3/C4/C5 工具接线（另案处理）
