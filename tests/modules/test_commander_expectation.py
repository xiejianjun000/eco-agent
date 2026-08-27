"""L2 任务层增强测试——expectation 锚点 + 前缀保留 replan

设计来源：Yi-Biao/EcoAgent (AAAI 2026) 端云协同闭环
  ① 每个计划步骤携带 expectation（预期世界状态），完成判据可验证
  ② 失败重规划冻结已成功前缀，仅重写剩余计划
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from agent_core.commander_v2 import CommanderV2, TaskStatus


class TestExpectationAnchor:
    """① expectation 锚点：每个子任务必须携带完成判据"""

    def test_decompose_produces_expectations(self):
        """分解出的每个任务必须有非空 expectation"""
        cmd = CommanderV2()
        tasks = cmd.decomposer.decompose("开发一个待办清单App")
        assert len(tasks) >= 5
        for t in tasks:
            assert t.expectation, f"任务 {t.description} 缺少 expectation"

    def test_completed_tasks_carry_verdict(self):
        """默认执行流：每个完成的任务必须留下验证结论"""
        cmd = CommanderV2()
        result = cmd.execute("研究生态环境法规")
        assert result["failed"] == 0
        for t in cmd._tasks.values():
            if t.status == TaskStatus.COMPLETED:
                assert t.verdict, f"任务 {t.description} 完成但无 verdict"
        assert result["verified"] >= 1

    def test_verification_failure_marks_failed(self):
        """验证不通过 → 任务 FAILED，verdict 记录原因（不是没抛异常就算完成）"""
        def always_fail_verifier(task):
            return False, "产出与 expectation 不符：缺少关键条款"
        cmd = CommanderV2(verifier=always_fail_verifier, max_mission_replans=0)
        result = cmd.execute("写作一份报告")
        assert result["failed"] >= 1
        failed = [t for t in cmd._tasks.values() if t.status == TaskStatus.FAILED]
        assert any("不符" in t.verdict for t in failed)


class TestPrefixPreservingReplan:
    """② 前缀保留 replan：冻结成功前缀，重写剩余计划"""

    def test_failed_task_triggers_replan_not_blind_retry(self):
        """失败后必须重规划剩余任务，而不是原样重跑同一任务"""
        calls = []
        fail_once = {"done": False}

        def executor(task):
            calls.append(task.description)
            return f"产出: {task.description}"

        def verifier(task):
            # 第 3 个任务第一次验证失败，重规划后放行
            if "[3/" in task.description and not fail_once["done"]:
                fail_once["done"] = True
                return False, "第3步产出未达 expectation"
            return True, "达标"

        cmd = CommanderV2(executor=executor, verifier=verifier)
        result = cmd.execute("开发一个数据平台")

        assert result["mission_replans"] == 1, "必须发生恰好 1 轮重规划"
        assert result["failed"] == 1, "原始第3步保留为 FAILED 审计记录"
        # 重规划后任务链最终全部完成
        assert result["completed"] >= 5

    def test_completed_prefix_never_reexecuted(self):
        """已 COMPLETED 的任务在 replan 后绝不被重跑（副作用安全）"""
        executed_ids = []
        fail_once = {"done": False}

        def executor(task):
            executed_ids.append(task.id)
            return "产出"

        def verifier(task):
            if "[2/" in task.description and not fail_once["done"]:
                fail_once["done"] = True
                return False, "未达标"
            return True, "达标"

        cmd = CommanderV2(executor=executor, verifier=verifier)
        cmd.execute("通用任务流程测试")

        # 任何任务 id 不得被执行两次（失败的那次也只执行一回）
        assert len(executed_ids) == len(set(executed_ids)), \
            f"存在重复执行的任务: {executed_ids}"

    def test_replan_budget_exhaustion(self):
        """重规划预算耗尽后：失败定格，后续依赖任务 BLOCKED，不再无限重试"""
        def always_fail(task):
            return False, "持续未达标"

        cmd = CommanderV2(verifier=always_fail, max_mission_replans=2)
        result = cmd.execute("写作预算耗尽测试")

        assert result["mission_replans"] == 2, "必须用完 2 轮重规划预算"
        assert result["failed"] >= 1
        # 预算耗尽后不得再有任务被重跑：总任务数有限且失败已定格
        statuses = [t.status for t in cmd._tasks.values()]
        assert TaskStatus.RUNNING not in statuses

    def test_replanned_tasks_carry_expectations(self):
        """重规划产生的新任务同样必须携带 expectation（锚点不丢）"""
        fail_once = {"done": False}

        def verifier(task):
            if not fail_once["done"]:
                fail_once["done"] = True
                return False, "首步未达标"
            return True, "达标"

        cmd = CommanderV2(verifier=verifier)
        cmd.execute("研究重规划锚点测试")

        for t in cmd._tasks.values():
            if t.status == TaskStatus.COMPLETED:
                assert t.expectation, f"重规划后的任务 {t.description} 丢了 expectation"

    def test_exception_goes_to_replan_path(self):
        """executor 抛异常与验证失败走同一条 replan 路径（统一失败语义）"""
        attempts = {"n": 0}

        def executor(task):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("工具调用超时")
            return "恢复后产出"

        cmd = CommanderV2(executor=executor, max_mission_replans=1)
        result = cmd.execute("通用异常恢复测试")

        assert result["mission_replans"] == 1
        failed = [t for t in cmd._tasks.values() if t.status == TaskStatus.FAILED]
        assert any("超时" in t.error for t in failed)


class _FakeLLM:
    """模拟 get_default_client：available + complete"""
    def __init__(self, reply: str, usable: bool = True):
        self._reply = reply
        self._usable = usable

    def available(self):
        return self._usable

    def complete(self, prompt, system="", max_tokens=512, timeout=90.0):
        return self._reply


class TestLLMVerifier:
    """默认 verifier 已接真实 LLM：语义核验优先，LLM 缺席降级规则兜底"""

    def test_llm_verdict_fail_blocks_completion(self, monkeypatch):
        """LLM 判未达标 → 任务 FAILED，verdict 含 LLM 理由"""
        import agent_core.llm_client as llm_mod
        monkeypatch.setattr(llm_mod, "get_default_client",
                            lambda: _FakeLLM("未达标\n缺少排放标准条款引用"))
        cmd = CommanderV2(max_mission_replans=0)
        result = cmd.execute("通用LLM核验拦截测试")
        assert result["failed"] >= 1
        failed = [t for t in cmd._tasks.values() if t.status == TaskStatus.FAILED]
        assert any("LLM核验" in t.verdict and "条款" in t.verdict for t in failed)

    def test_llm_verdict_pass_completes(self, monkeypatch):
        """LLM 判达标 → 任务 COMPLETED，链式全跑完"""
        import agent_core.llm_client as llm_mod
        monkeypatch.setattr(llm_mod, "get_default_client",
                            lambda: _FakeLLM("达标\n判据逐条满足"))
        cmd = CommanderV2()
        result = cmd.execute("通用LLM核验放行测试")
        assert result["failed"] == 0
        assert result["completed"] == result["total_tasks"]
        assert all("LLM核验" in t.verdict for t in cmd._tasks.values())

    def test_llm_unavailable_falls_back_to_rule(self, monkeypatch):
        """LLM 缺席 → 静默降级规则核验（产出非空即过），不报错不阻塞"""
        import agent_core.llm_client as llm_mod
        monkeypatch.setattr(llm_mod, "get_default_client",
                            lambda: _FakeLLM("", usable=False))
        cmd = CommanderV2()
        result = cmd.execute("通用降级测试")
        assert result["failed"] == 0
        assert any("规则验证" in t.verdict for t in cmd._tasks.values())
