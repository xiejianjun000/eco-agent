# benchmarks/ — 基准与实证剧本

## 文件组织

| 路径 | 用途 |
|:-----|:-----|
| `benchmark_harness.py` | Phase 6 基准测试框架（外部基准如实标注 not_run，内部指标 fixture 实测） |
| `ecobench/run_ecobench.py` | EcoBench-mini 50 题生态环境执法问答金标准评测 |
| `longrun_pulse_evolve.py` | L3 Pulse 心跳 + L4 Evolve 进化 长时运行实证剧本 |
| `reports/` | 长时运行实证产物（JSONL 事件流 + Markdown 汇总报告），脚本自动建目录 |

## longrun_pulse_evolve.py — L3/L4 长时运行实证剧本

README 声称 L3 Pulse（5~20 分钟自适应心跳、5 个内置步骤）与 L4 Evolve（任务后/每日
自动进化、五阶段、输出 `evolution_report.md`）具备自动化行为，但此前无实测证据。
本剧本以**纯观察**方式（只调公开 API、不改 agent_core 实现）长时运行并记录一切
可观察痕迹，产出的报告同时包含「README 声称 vs 实测对照」章节。

### 运行方式

```bash
python benchmarks/longrun_pulse_evolve.py                  # 默认 24h 长时观察
python benchmarks/longrun_pulse_evolve.py --hours 8
python benchmarks/longrun_pulse_evolve.py --smoke          # 压缩时序自检（120s）
python benchmarks/longrun_pulse_evolve.py --smoke --seconds 45 --evolve-every 15
python benchmarks/longrun_pulse_evolve.py --no-evolve      # 只观察 L3
```

- `--smoke`：心跳间隔压到秒级（含自适应边界同步压缩），用于快速验证剧本本身可用。
- 剧本内 `setdefault ECO_LLM_DISABLE=1`：不调用真实 LLM，Reflector 对抗质询与
  元认知分析章节走规则降级，报告中如实标注。
- `Ctrl-C`（SIGINT）优雅退出，仍会生成汇总报告。

### 产物与解读

`benchmarks/reports/longrun_YYYYMMDD_HHMMSS.{jsonl,md}`：

- **JSONL 事件流**：`run_start` / `heartbeat`（每次心跳的时间戳、5 步骤执行痕迹、
  当前间隔、自适应调整来源）/ `evolve_cycle`（五阶段产物、反思门禁结果、版本快照
  与报告文件存在性）/ `evolve_report_detected` / `anomaly` / `run_end`。
- **Markdown 报告**（对齐 `docs/验收报告` 风格）：
  - 一、L3 Pulse：心跳次数、实际间隔 min/avg/max/中位数、自适应降频记录、
    5 步骤观察到的返回值；
  - 二、L4 Evolve：进化次数与触发方式、五阶段产物清单、报告文件清单；
  - 三、README 声称 vs 实测对照（✅/⚠️/❌）；
  - 四、异常清单；五、产物清单。

### 已探测到的声称/实测差异（2026-07-31）

- L3 的 5 个 `step_*` 均为占位实现（常量返回），且生产接线 `EcoLoops.start()`
  只注册 sync/diff 两个，其余 3 个真实运行中不会执行；
- L3 自适应按心跳耗时伸缩（300~1200s），无 README 声称的「电池模式降频」；
- L4 无自动触发器（无任务后钩子、无每日 02:00 调度），仅 `eco evolution` CLI
  手动触发——剧本按 `--evolve-every` 手动触发并标注 `script_manual`；
- L4 报告实为 `memory-tree/obsidian_sync/quality/evolution_report_v{N}.md`
  （带版本号）；阶段 3/4 为占位（计数/固定 dict，无文件产物）。

对应 pytest：`tests/modules/test_longrun_pulse_evolve.py`（短跑 + 合成事件，
不跑真实长时运行）。
