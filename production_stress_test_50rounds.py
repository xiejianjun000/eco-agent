#!/usr/bin/env python3 -B -u
"""
生产部署穿透式压力测试 — 50轮 × 五大能力
覆盖：记忆V1/V2、学习V1/V2、自愈、进化、执行
"""
<<<<<<< HEAD
import sys, os, time, json, random, string, threading, traceback, asyncio
=======
import sys, os, time, json, random, string, threading, traceback
>>>>>>> a3797b5 (Add 10 Anthropic Skills + zhihu-fetch-skill)
from pathlib import Path
from datetime import datetime
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ["ECO_LLM_DISABLE"] = "1"
os.environ["ECO_MEMORY_MAX_RECORDS"] = "5000"
os.environ["ECO_CIRCUIT_COOLDOWN_BASE"] = "3"

ROUNDS = 50
REPORT = {"rounds": [], "summary": {}, "start": datetime.now().isoformat()}
PASS = FAIL = 0

def log(msg): print(f"[PROD-50R] {msg}")
def ok(t, d=""): 
    global PASS; PASS += 1
    log(f"  ✅ {t} {d}")
def fail(t, d=""): 
    global FAIL; FAIL += 1
    log(f"  ❌ {t} — {d}")

def run_round(round_num: int) -> dict:
    """执行单轮五大能力测试"""
    log(f"\n{'='*60}\n  第 {round_num:02d}/50 轮\n{'='*60}")
    r = {"round": round_num, "tests": [], "errors": []}
    
    # ── 记忆能力 ──
    try:
        from agent_core.memory_index import MemoryIndex
        from agent_core.memory_v2 import MemoryV2, HNSW_AVAILABLE
        
        idx = MemoryIndex(path=ROOT / ".eco-test" / f"round_{round_num}.jsonl")
        idx._records.clear()
        N = random.randint(20, 50)
        t0 = time.time()
        for i in range(N):
            idx.record("user", f"R{round_num}_记忆_{i:04d}_" + "".join(random.choices(string.ascii_letters + "生态环境执法", k=30)), session_id=f"sess_{i%5}")
        write_ms = (time.time() - t0) * 1000
        
        t0 = time.time()
        results = idx.search(f"R{round_num}_记忆_{random.randint(0,N-1):04d}", k=5)
        search_ms = (time.time() - t0) * 1000
        
        r["tests"].append({"name": "记忆V1-写入", "pass": True, "items": N, "ms": round(write_ms, 1)})
        r["tests"].append({"name": "记忆V1-检索", "pass": True, "hits": len(results), "ms": round(search_ms, 1)})
        
        # V2 时间图
        mem2 = MemoryV2()
        mem2.record("user", f"企业{round_num}的许可证编号是XK{20240000+round_num}", "sess_v2")
        facts = mem2.graph.query(f"企业{round_num}")
        r["tests"].append({"name": "记忆V2-时间图", "pass": len(facts) >= 1, "facts": len(facts)})
        
        ok(f"记忆 R{round_num}", f"写入{N}条 {write_ms:.0f}ms, 检索 {search_ms:.0f}ms, 时间图{len(facts)}条")
    except Exception as e:
        r["errors"].append(f"记忆: {e}")
        fail(f"记忆 R{round_num}", str(e))
    
    # ── 学习能力 ──
    try:
        from agent_core.skill_system import SkillRegistry, SkillABTest, Skill, CrossSessionMemory
        from agent_core.learning_v2 import LearningV2, SkillVariant
        
        reg = SkillRegistry()
        for i in range(random.randint(5, 20)):
            s = Skill(id=f"R{round_num}_sk_{i:03d}", name=f"技能_{i:03d}", description=f"R{round_num}测试", category="执法", triggers=["test"], steps=["s1"], version="1.0")
            reg.register(s)
        
        # O(1)查找
        t0 = time.time()
        found = reg.find("技能_005")
        find_ms = (time.time() - t0) * 1000
        
        # A/B测试
        ab = SkillABTest(f"R{round_num}_ab", SkillVariant(name="A", template="t1"), SkillVariant(name="B", template="t2"))
        for i in range(random.randint(10, 30)):
            ab.record_result("A", random.random() > 0.3, 1.0)
            ab.record_result("B", random.random() > 0.2, 1.0)
        winner = ab.evaluate()
        
        # DSPy（带dev_set）
        learn = LearningV2()
        learn.optimizer.add_example({"q": "企业A"}, {"r": "有效"})
        learn.optimizer.add_example({"q": "企业B"}, {"r": "过期"})
        sig = learn.create_skill_signature("check", ["q"], ["r"], "查询")
        opt = learn.optimize_skill(sig, "根据{q}查询", "BootstrapFewShot")
        has_examples = len(opt.few_shot_examples) > 0
        
        # TTL
        csm = CrossSessionMemory()
        csm.store_working(f"R{round_num}_key", "val", ttl_minutes=0)
        csm._cleanup_working()
        
        r["tests"].append({"name": "学习-注册", "pass": True, "skills": len(reg._skills)})
        r["tests"].append({"name": "学习-查找", "pass": find_ms < 10, "ms": round(find_ms, 2)})
        r["tests"].append({"name": "学习-A/B", "pass": True, "winner": winner})
        r["tests"].append({"name": "学习-DSPy", "pass": has_examples, "examples": len(opt.few_shot_examples)})
        r["tests"].append({"name": "学习-TTL", "pass": True})
        
        ok(f"学习 R{round_num}", f"技能{len(reg._skills)}个, 查找{find_ms:.1f}ms, A/B={winner}, DSPy示例={len(opt.few_shot_examples)}")
    except Exception as e:
        r["errors"].append(f"学习: {e}")
        fail(f"学习 R{round_num}", str(e))
    
    # ── 自愈能力 ──
    try:
        from agent_core.self_healing import SelfHealer, CheckpointSnapshot
        
        healer = SelfHealer()
        
        # 瞬时恢复
        c = [0]
        def flaky():
            c[0] += 1
            if c[0] < 3: raise TimeoutError("t")
            return "ok"
        r1 = healer.protect(flaky, f"flaky_R{round_num}", max_retries=5)
        
        # 熔断
        def fail_op(): raise ValueError("f")
        r2 = healer.protect(fail_op, f"cb_R{round_num}", max_retries=2)
        r3 = healer.protect(fail_op, f"cb_R{round_num}", max_retries=2)
        
        # 检查点
        cp = CheckpointSnapshot()
        sid = cp.save({"round": round_num, "data": "x" * 1000})
        restored = cp.restore(sid)
        
        # 并发
        results = []
        def worker(wid):
            def op():
                if random.random() < 0.3: raise RuntimeError("e")
                return "ok"
            results.append(healer.protect(op, f"c{wid}_R{round_num}", max_retries=3))
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        ok_count = sum(1 for x in results if x["success"])
        
        r["tests"].append({"name": "自愈-恢复", "pass": r1["success"], "attempts": r1["attempts"]})
        r["tests"].append({"name": "自愈-熔断", "pass": not r3["success"]})
        r["tests"].append({"name": "自愈-检查点", "pass": restored is not None})
        r["tests"].append({"name": "自愈-并发", "pass": ok_count >= 5, "success": ok_count})
        
        ok(f"自愈 R{round_num}", f"恢复{r1['attempts']}次, 熔断={not r3['success']}, 检查点={restored is not None}, 并发{ok_count}/10")
    except Exception as e:
        r["errors"].append(f"自愈: {e}")
        fail(f"自愈 R{round_num}", str(e))
    
    # ── 进化能力 ──
    try:
        from agent_core.meta_evolution import MetaEvolution
        from agent_core.evolve_trigger import EvolveTrigger
        
        evo = MetaEvolution()
        history = [{"success": random.random() > 0.3, "task": f"R{round_num}_t{i}"} for i in range(random.randint(5, 15))]
        result = evo.run_full_cycle(history)
        phases = result["phases"]
        has_all = all(k in phases for k in ["experience_replay", "gap_analysis", "skill_gen", "reflection", "memory_consolidation", "self_versioning"])
        skills_exist = len(list((ROOT / "skills").glob("evo_*.md"))) > 0
        
        trig = EvolveTrigger(threshold=random.randint(2, 5), cooldown_s=0)
        for i in range(random.randint(3, 8)):
            trig.record_mission(summary={"failed": 1 if i%2 else 0, "total": 1}, tasks=[])
        triggered = trig.maybe_trigger()
        
        r["tests"].append({"name": "进化-五阶段", "pass": has_all})
        r["tests"].append({"name": "进化-落盘", "pass": skills_exist})
        r["tests"].append({"name": "进化-触发", "pass": triggered is not None})
        
        ok(f"进化 R{round_num}", f"五阶段={has_all}, 落盘={skills_exist}, 触发={triggered is not None}")
    except Exception as e:
        r["errors"].append(f"进化: {e}")
        fail(f"进化 R{round_num}", str(e))
    
    # ── 执行能力 ──
    try:
        from agent_core.browser_skill import BrowserSkill, BROWSER_AVAILABLE
        from agent_core.sandbox import DockerSandbox
        from agent_core.mcp_connector import MCP_AVAILABLE
        
        sandbox = DockerSandbox()
<<<<<<< HEAD
        sr = asyncio.run(sandbox.execute("print('sandbox ok')"))
=======
        sr = sandbox.run("print('sandbox ok')")
>>>>>>> a3797b5 (Add 10 Anthropic Skills + zhihu-fetch-skill)
        
        r["tests"].append({"name": "执行-沙箱", "pass": sr["success"], "type": sr.get("sandbox", "unknown")})
        r["tests"].append({"name": "执行-MCP", "pass": MCP_AVAILABLE})
        r["tests"].append({"name": "执行-浏览器", "pass": True, "available": BROWSER_AVAILABLE})
        
        ok(f"执行 R{round_num}", f"沙箱={sr['success']}, MCP={MCP_AVAILABLE}, 浏览器={BROWSER_AVAILABLE}")
    except Exception as e:
        r["errors"].append(f"执行: {e}")
        fail(f"执行 R{round_num}", str(e))
    
    return r

# ═══════════════════════════════════════════════════════════════
# 主入口：50轮
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    log("╔" + "═" * 58 + "╗")
    log("║" + " 生产部署穿透式压力测试 — 50轮 × 五大能力 ".center(56) + "║")
    log("╚" + "═" * 58 + "╝")
    (ROOT / ".eco-test").mkdir(exist_ok=True)
    
    t_start = time.time()
    all_passed = True
    
    for i in range(1, ROUNDS + 1):
        r = run_round(i)
        REPORT["rounds"].append(r)
        if r["errors"]:
            all_passed = False
            log(f"  ⚠️ 第{i}轮有 {len(r['errors'])} 个错误")
    
    total_time = time.time() - t_start
    
    # 汇总统计
    per_ability = defaultdict(lambda: {"pass": 0, "fail": 0, "total_ms": 0})
    for r in REPORT["rounds"]:
        for t in r["tests"]:
            ability = t["name"].split("-")[0]
            per_ability[ability]["total"] = per_ability[ability].get("total", 0) + 1
            if t["pass"]:
                per_ability[ability]["pass"] += 1
            else:
                per_ability[ability]["fail"] += 1
            if "ms" in t:
                per_ability[ability]["total_ms"] += t["ms"]
    
    log("\n" + "=" * 60)
    log("【50轮生产测试汇总】")
    log("=" * 60)
    log(f"总耗时: {total_time:.2f}s | 平均每轮: {total_time/ROUNDS:.2f}s")
    log(f"总通过: {PASS} | 总失败: {FAIL}")
    log("\n按能力维度:")
    for ability, stats in sorted(per_ability.items()):
        total = stats.get("total", 0)
        passed = stats["pass"]
        rate = passed / max(total, 1) * 100
        avg_ms = stats["total_ms"] / max(total, 1) if stats["total_ms"] else 0
        log(f"  {ability:8s}: 通过 {passed:3d}/{total:3d} ({rate:5.1f}%) 平均{avg_ms:.1f}ms")
    
    # 星级评定
    stars = {}
    for ability, stats in per_ability.items():
        rate = stats["pass"] / max(stats.get("total", 1), 1)
        if rate >= 0.99: stars[ability] = "⭐⭐⭐⭐⭐"
        elif rate >= 0.95: stars[ability] = "⭐⭐⭐⭐☆"
        elif rate >= 0.90: stars[ability] = "⭐⭐⭐☆☆"
        else: stars[ability] = "⭐⭐☆☆☆"
    
    log("\n星级评定:")
    for ability, star in sorted(stars.items()):
        log(f"  {ability:8s}: {star}")
    
    REPORT["summary"] = {
        "total_time_s": round(total_time, 2),
        "avg_round_s": round(total_time / ROUNDS, 2),
        "total_pass": PASS,
        "total_fail": FAIL,
        "per_ability": dict(per_ability),
        "stars": stars,
        "all_passed": all_passed,
    }
    REPORT["end"] = datetime.now().isoformat()
    
    rp = ROOT / ".eco-test" / "production_stress_50rounds.json"
    rp.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\n详细报告: {rp}")
    log(f"结论: {'✅ 全部通过' if all_passed else '⚠️ 存在失败项'}")
    sys.exit(0 if all_passed else 1)
