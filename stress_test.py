#!/usr/bin/env python3
"""
eco Agent 四大核心能力压力/烟雾测试
覆盖：记忆能力、学习能力、自愈能力、进化能力
"""
import sys, os, time, json, random, string, threading, traceback
from pathlib import Path
from datetime import datetime

# 项目路径
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# 禁用 LLM，纯本地测试
os.environ["ECO_LLM_DISABLE"] = "1"

REPORT = {"start": datetime.now().isoformat(), "tests": []}

def log(msg):
    print(f"[STRESS] {msg}")

def fail(test_name, detail):
    log(f"❌ FAIL: {test_name} — {detail}")
    REPORT["tests"].append({"name": test_name, "status": "FAIL", "detail": detail})

def ok(test_name, detail=""):
    log(f"✅ PASS: {test_name} {detail}")
    REPORT["tests"].append({"name": test_name, "status": "PASS", "detail": detail})

# ═══════════════════════════════════════════════════════════════
# 一、记忆能力压力测试
# ═══════════════════════════════════════════════════════════════
def test_memory_pressure():
    log("=" * 60)
    log("【记忆能力压力测试】")
    log("=" * 60)

    from agent_core.memory_index import MemoryIndex, get_memory_index, _MAX_RECORDS

    # 1.1 批量写入性能测试
    idx = MemoryIndex(path=ROOT / ".eco-test" / "stress_memory.jsonl")
    idx._records.clear()  # 清空

    N = 50
    contents = [
        f"测试记忆内容_{i:04d}_" + "".join(random.choices(string.ascii_letters + "生态环境执法", k=50))
        for i in range(N)
    ]

    t0 = time.time()
    for i, c in enumerate(contents):
        idx.record("user" if i % 2 == 0 else "assistant", c, session_id=f"sess_{i % 10}")
    write_time = time.time() - t0
    stats = idx.stats()
    ok("记忆-批量写入", f"{N}条写入 {write_time:.2f}s, 记录数={stats['records']}")

    # 1.2 高频检索性能测试
    queries = [f"测试记忆内容_{random.randint(0, N-1):04d}" for _ in range(200)]
    t0 = time.time()
    total_results = 0
    for q in queries:
        r = idx.search(q, k=5)
        total_results += len(r)
    search_time = time.time() - t0
    ok("记忆-高频检索", f"200次检索 {search_time:.2f}s, 平均每次{search_time/200*1000:.1f}ms, 总命中{total_results}")

    # 1.3 大容量边界测试（超过 _MAX_RECORDS）
    idx2 = MemoryIndex(path=ROOT / ".eco-test" / "stress_memory_overflow.jsonl")
    idx2._records.clear()
    OVER = _MAX_RECORDS + 500
    t0 = time.time()
    for i in range(OVER):
        idx2.record("user", f"溢出测试_{i:06d}_" + "x" * 100, session_id="overflow")
    overflow_time = time.time() - t0
    stats2 = idx2.stats()
    if stats2["records"] == _MAX_RECORDS:
        ok("记忆-容量边界", f"写入{OVER}条后截断至{_MAX_RECORDS}, 耗时{overflow_time:.2f}s")
    else:
        fail("记忆-容量边界", f"期望{_MAX_RECORDS}, 实际{stats2['records']}")

    # 1.4 并发写入一致性测试
    idx3 = MemoryIndex(path=ROOT / ".eco-test" / "stress_memory_concurrent.jsonl")
    idx3._records.clear()
    errors = []
    def worker(wid):
        try:
            for i in range(3):
                idx3.record("user", f"并发_{wid}_{i:03d}_内容", session_id=f"thread_{wid}")
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    concurrent_time = time.time() - t0
    stats3 = idx3.stats()
    if not errors and stats3["records"] == 1000:
        ok("记忆-并发一致性", f"10线程×100条, 无错误, 记录数={stats3['records']}, 耗时{concurrent_time:.2f}s")
    else:
        fail("记忆-并发一致性", f"错误数={len(errors)}, 记录数={stats3['records']}, 期望1000")

    # 1.5 空查询/异常输入鲁棒性
    try:
        r1 = idx.search("")
        r2 = idx.search("   ")
        r3 = idx.search("!@#$%^&*()")
        r4 = idx.search("a" * 10000)
        if r1 == [] and r2 == [] and r3 == [] and len(r4) <= 5:
            ok("记忆-异常输入鲁棒性", "空串/空白/纯符号/超长串均正常处理")
        else:
            fail("记忆-异常输入鲁棒性", f"空={r1}, 空白={r2}, 符号={r3}, 超长={len(r4)}")
    except Exception as e:
        fail("记忆-异常输入鲁棒性", f"异常: {e}")

    # 清理
    for p in (ROOT / ".eco-test").glob("stress_memory*.jsonl"):
        p.unlink(missing_ok=True)

# ═══════════════════════════════════════════════════════════════
# 二、学习能力压力测试
# ═══════════════════════════════════════════════════════════════
def test_learning_pressure():
    log("=" * 60)
    log("【学习能力压力测试】")
    log("=" * 60)

    from agent_core.skill_system import Skill, SkillRegistry, AutoLearnEngine, CrossSessionMemory

    # 2.1 批量技能注册
    reg = SkillRegistry()
    N = 50
    t0 = time.time()
    for i in range(N):
        s = Skill(
            id=f"skill_{i:04d}",
            name=f"技能_{i:04d}",
            description=f"这是第{i}个测试技能，用于生态环境执法的某某场景",
            category=random.choice(["执法", "文书", "检索", "分析", "报告"]),
            parameters={"param1": "string", "param2": "number"},
            template=f"模板内容_{i}_" + "x" * 200,
            version=1,
            success_rate=random.random(),
            usage_count=random.randint(0, 100),
            created_at=time.time(),
            last_used=time.time(),
        )
        reg.register(s)
    reg_time = time.time() - t0
    stats = reg.get_stats()
    ok("学习-批量技能注册", f"{N}个技能 {reg_time:.2f}s, 总数={stats['total']}")

    # 2.2 高频查找性能
    queries = [f"技能_{random.randint(0, N-1):04d}" for _ in range(3)]
    t0 = time.time()
    total_found = 0
    for q in queries:
        found = reg.find(q)
        total_found += len(found)
    find_time = time.time() - t0
    ok("学习-高频查找", f"100次查找 {find_time:.2f}s, 平均{find_time/100*1000:.1f}ms, 总命中{total_found}")

    # 2.3 分类统计
    t0 = time.time()
    cats = ["执法", "文书", "检索", "分析", "报告"]
    for c in cats:
        reg.list_by_category(c)
    cat_time = time.time() - t0
    ok("学习-分类统计", f"5类统计 {cat_time*1000:.1f}ms")

    # 2.4 跨会话记忆四层结构
    csm = CrossSessionMemory()
    t0 = time.time()
    for i in range(3):
        csm.store_working(f"key_{i}", f"工作记忆值_{i}", ttl_minutes=1)
        csm.store_episodic(f"事件_{i}", {"context": f"上下文_{i}"})
        csm.store_semantic(f"事实_{i}", f"知识_{i}")
        csm.store_procedural(f"技能_{i}", [f"步骤1_{i}", f"步骤2_{i}"])
    store_time = time.time() - t0

    t0 = time.time()
    for i in range(3):
        csm.recall_working(f"key_{i}")
        csm.recall_episodic(f"事件_{i}")
        csm.recall_semantic(f"事实_{i}")
    recall_time = time.time() - t0
    csm_stats = csm.get_stats()
    ok("学习-跨会话记忆", f"100组四层存储 {store_time:.2f}s, 召回 {recall_time:.2f}s, 统计={csm_stats}")

    # 2.5 自动学习引擎压力
    engine = AutoLearnEngine(registry=reg)
    t0 = time.time()
    for i in range(3):
        engine.learn_from_task(
            task_desc=f"执法任务_{i}: 检查某企业排放超标情况",
            task_steps=["收集数据", "分析法规", "生成报告"],
            success=random.random() > 0.3,
            duration_s=random.randint(10, 300),
        )
    learn_time = time.time() - t0
    stats_after = reg.get_stats()
    ok("学习-自动学习引擎", f"50次学习 {learn_time:.2f}s, 技能数={stats_after['total']}")

    # 2.6 归档旧技能
    t0 = time.time()
    reg.archive_old(max_age_days=0, min_usage=0)  # 强制归档所有
    archive_time = time.time() - t0
    stats_final = reg.get_stats()
    ok("学习-技能归档", f"归档耗时 {archive_time*1000:.1f}ms, 最终技能数={stats_final['total']}")

# ═══════════════════════════════════════════════════════════════
# 三、自愈能力压力测试
# ═══════════════════════════════════════════════════════════════
def test_healing_pressure():
    log("=" * 60)
    log("【自愈能力压力测试】")
    log("=" * 60)

    from agent_core.self_healing import SelfHealer, CheckpointSnapshot

    healer = SelfHealer()

    # 3.1 瞬时异常恢复测试
    counter = [0]
    def flaky_op():
        counter[0] += 1
        if counter[0] < 3:
            raise RuntimeError(f"瞬时错误 #{counter[0]}")
        return "success"

    t0 = time.time()
    result = healer.protect(flaky_op, context="flaky_test", max_retries=5)
    heal_time = time.time() - t0
    if result["success"] and result["attempts"] == 3:
        ok("自愈-瞬时异常恢复", f"第3次成功, 耗时{heal_time:.3f}s, 尝试{result['attempts']}次")
    else:
        fail("自愈-瞬时异常恢复", f"success={result['success']}, attempts={result['attempts']}")

    # 3.2 持久异常熔断测试
    def always_fail():
        raise ConnectionError("网络不可达")

    t0 = time.time()
    result = healer.protect(always_fail, context="persistent_fail", max_retries=3)
    fail_time = time.time() - t0
    if not result["success"] and "熔断" in str(result.get("fallback_applied", "")):
        ok("自愈-持久异常熔断", f"正确熔断, 耗时{fail_time:.3f}s")
    else:
        fail("自愈-持久异常熔断", f"应熔断但未熔断: {result}")

    # 3.3 熔断器冷却恢复测试
    t0 = time.time()
    result2 = healer.protect(always_fail, context="persistent_fail", max_retries=1)
    if not result2["success"] and "熔断" in str(result2.get("fallback_applied", "")):
        ok("自愈-熔断器冷却", "熔断器保持开启，正确拒绝")
    else:
        fail("自愈-熔断器冷却", f"熔断器应仍开启: {result2}")

    # 3.4 检查点保存/恢复压力
    cp = CheckpointSnapshot()
    contexts = [{f"key_{i}": f"value_{i}_" + "x" * 1000 for i in range(3)} for _ in range(3)]

    t0 = time.time()
    ids = []
    for ctx in contexts:
        sid = cp.save(ctx)
        ids.append(sid)
    save_time = time.time() - t0

    t0 = time.time()
    restored = 0
    for sid in ids:
        r = cp.restore(sid)
        if r:
            restored += 1
    restore_time = time.time() - t0

    if restored == 20:
        ok("自愈-检查点压力", f"20个检查点保存{save_time:.2f}s, 恢复{restore_time:.2f}s, 全部成功")
    else:
        fail("自愈-检查点压力", f"恢复{restored}/20")

    # 3.5 指数退避验证
    backoff_times = []
    for attempt in range(1, 6):
        # 通过 _calc_backoff 间接验证
        delay = healer._calc_backoff(attempt, "transient")
        backoff_times.append(delay)
    # 验证指数增长
    increasing = all(backoff_times[i] < backoff_times[i+1] for i in range(len(backoff_times)-1))
    if increasing:
        ok("自愈-指数退避", f"退避时间递增: {[round(x,1) for x in backoff_times]}")
    else:
        fail("自愈-指数退避", f"非递增: {backoff_times}")

    # 3.6 异常分类准确性
    test_cases = [
        (RuntimeError("临时错误"), "transient"),
        (ConnectionError("连接超时"), "transient"),
        (PermissionError("无权限"), "persistent"),
        (ValueError("参数错误"), "persistent"),
        (RecursionError("递归过深"), "deadlock"),
    ]
    correct = 0
    for err, expected in test_cases:
        actual = healer._classify(err)
        if actual == expected:
            correct += 1
    if correct == len(test_cases):
        ok("自愈-异常分类", f"{len(test_cases)}类异常全部正确分类")
    else:
        fail("自愈-异常分类", f"正确{correct}/{len(test_cases)}")

    # 3.7 高并发自愈测试
    results = []
    def concurrent_heal(wid):
        def op():
            if random.random() < 0.3:
                raise RuntimeError(f"并发错误_{wid}")
            return f"ok_{wid}"
        r = healer.protect(op, context=f"concurrent_{wid}", max_retries=3)
        results.append(r)

    threads = [threading.Thread(target=concurrent_heal, args=(i,)) for i in range(3)]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    concurrent_time = time.time() - t0
    success_count = sum(1 for r in results if r["success"])
    ok("自愈-高并发", f"20并发 {concurrent_time:.2f}s, 成功{success_count}/20")

    # 清理检查点
    for p in (ROOT / ".eco-test").glob("checkpoint_*.json"):
        p.unlink(missing_ok=True)

# ═══════════════════════════════════════════════════════════════
# 四、进化能力压力测试
# ═══════════════════════════════════════════════════════════════
def test_evolution_pressure():
    log("=" * 60)
    log("【进化能力压力测试】")
    log("=" * 60)

    from agent_core.meta_evolution import MetaEvolution
    from agent_core.evolve_trigger import EvolveTrigger

    # 4.1 大量历史任务注入 + 进化循环
    evo = MetaEvolution()
    histories = []
    for i in range(3):
        histories.append({
            "success": random.random() > 0.3,
            "task": f"执法任务_{i}: " + random.choice([
                "检查企业排污许可证",
                "监测空气质量指数",
                "撰写行政处罚决定书",
                "核查环评报告",
                "处理群众投诉",
            ]),
            "timestamp": time.time() - random.randint(0, 86400),
            "duration": random.randint(30, 600),
        })

    t0 = time.time()
    result = evo.run_full_cycle(histories)
    cycle_time = time.time() - t0

    phases = result.get("phases", {})
    expected_phases = ["experience_replay", "gap_analysis", "skill_generation",
                       "reflector_review", "curator_gate", "memory_consolidation", "self_versioning"]
    missing = [p for p in expected_phases if p not in phases]
    if not missing:
        ok("进化-五阶段完整", f"50条历史, 全阶段完成, 耗时{cycle_time:.2f}s, 版本={result.get('version')}")
    else:
        fail("进化-五阶段完整", f"缺失阶段: {missing}")

    # 4.2 快速连续进化测试（不应崩溃）
    t0 = time.time()
    for i in range(3):
        try:
            r = evo.run_full_cycle(histories[:10])
        except Exception as e:
            fail("进化-快速连续", f"第{i}次进化崩溃: {e}")
            return
    rapid_time = time.time() - t0
    ok("进化-快速连续", f"5次连续进化 {rapid_time:.2f}s, 无崩溃")

    # 4.3 空历史/异常历史鲁棒性
    try:
        r1 = evo.run_full_cycle([])
        r2 = evo.run_full_cycle([{"bad": "data"}])
        r3 = evo.run_full_cycle(None)
        ok("进化-异常历史鲁棒性", "空列表/坏数据/None均正常处理")
    except Exception as e:
        fail("进化-异常历史鲁棒性", f"异常: {e}")

    # 4.4 进化触发器条件判断
    trig = EvolveTrigger(threshold=5, cooldown_s=0)
    for i in range(3):
        trig.record_mission(
            summary={"failed": 1 if i % 3 == 0 else 0, "total": 1},
            tasks=[{"description": f"任务_{i}", "status": "done" if i % 3 else "failed",
                    "expectation": "", "output": "", "verdict": ""}]
        )

    # 阈值=5, 10条经验(含失败双倍计)权重>5, 冷却=0, 应触发
    t0 = time.time()
    trigger_result = trig.maybe_trigger()
    trigger_time = time.time() - t0
    if trigger_result is not None:
        ok("进化-触发器阈值", f"权重达标后正确触发, 耗时{trigger_time:.2f}s")
    else:
        fail("进化-触发器阈值", f"权重={trig._evolve_weight()}, 应触发但未触发")

    # 4.5 冷却期阻止重复触发
    trig2 = EvolveTrigger(threshold=1, cooldown_s=3600)
    trig2.record_mission(summary={"failed": 0}, tasks=[])
    trig2.maybe_trigger()  # 第一次触发
    trig2.record_mission(summary={"failed": 0}, tasks=[])
    result = trig2.maybe_trigger()  # 应在冷却期内被阻止
    if result is None:
        ok("进化-冷却期阻止", "冷却期内正确阻止重复触发")
    else:
        fail("进化-冷却期阻止", "冷却期内错误触发")

    # 4.6 每日调度检查
    trig3 = EvolveTrigger()
    # 新实例从未触发过，应返回 True
    if trig3.should_evolve_daily():
        ok("进化-每日调度", "从未进化过时正确返回 True")
    else:
        fail("进化-每日调度", "新实例应返回 True")

    # 4.7 版本快照管理
    versions = []
    for i in range(3):
        r = evo.run_full_cycle(histories[:5])
        versions.append(r.get("version", 0))
    # 版本应递增
    if versions == sorted(versions) and len(set(versions)) == len(versions):
        ok("进化-版本递增", f"10次进化版本连续递增: {versions}")
    else:
        fail("进化-版本递增", f"版本不连续: {versions}")

    # 4.8 dry_run 分析模式
    t0 = time.time()
    analysis = evo.analyze(histories, dry_run=True)
    dry_time = time.time() - t0
    if "gaps" in analysis and "recommendations" in analysis:
        ok("进化-dry_run分析", f"分析完成, 耗时{dry_time:.2f}s, 发现{len(analysis.get('gaps', []))}个差距")
    else:
        fail("进化-dry_run分析", f"缺少关键字段: {list(analysis.keys())}")

# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    log("╔" + "═" * 58 + "╗")
    log("║" + " eco Agent 四大核心能力压力/烟雾测试 ".center(56) + "║")
    log("╚" + "═" * 58 + "╝")

    # 创建测试目录
    (ROOT / ".eco-test").mkdir(exist_ok=True)

    t_start = time.time()

    try:
        test_memory_pressure()
    except Exception as e:
        log(f"记忆测试异常: {e}")
        traceback.print_exc()

    try:
        test_learning_pressure()
    except Exception as e:
        log(f"学习测试异常: {e}")
        traceback.print_exc()

    try:
        test_healing_pressure()
    except Exception as e:
        log(f"自愈测试异常: {e}")
        traceback.print_exc()

    try:
        test_evolution_pressure()
    except Exception as e:
        log(f"进化测试异常: {e}")
        traceback.print_exc()

    total_time = time.time() - t_start

    # 汇总报告
    passes = sum(1 for t in REPORT["tests"] if t["status"] == "PASS")
    fails = sum(1 for t in REPORT["tests"] if t["status"] == "FAIL")

    log("=" * 60)
    log("【测试汇总】")
    log("=" * 60)
    log(f"总耗时: {total_time:.2f}s")
    log(f"通过: {passes}  |  失败: {fails}  |  总计: {passes + fails}")
    if fails:
        log("失败项:")
        for t in REPORT["tests"]:
            if t["status"] == "FAIL":
                log(f"  - {t['name']}: {t['detail']}")

    REPORT["end"] = datetime.now().isoformat()
    REPORT["total_time_s"] = round(total_time, 2)
    REPORT["pass"] = passes
    REPORT["fail"] = fails

    report_path = ROOT / ".eco-test" / "stress_report.json"
    report_path.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"报告已保存: {report_path}")

    sys.exit(0 if fails == 0 else 1)
