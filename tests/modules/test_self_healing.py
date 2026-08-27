"""L5 韧性自愈循环测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from agent_core.self_healing import SelfHealer, CheckpointSnapshot

class TestSelfHealing:
    def test_normal_operation(self):
        healer = SelfHealer()
        result = healer.protect(lambda: "ok", "test")
        assert result['success'] is True

    def test_retry_recovery(self):
        healer = SelfHealer()
        attempt = [0]
        def failing():
            attempt[0] += 1
            if attempt[0] < 3: raise TimeoutError("timeout")
            return "recovered"
        result = healer.protect(failing, "retry_test", max_retries=3)
        assert result['success'] is True
        assert attempt[0] == 3

    def test_circuit_breaker(self):
        healer = SelfHealer()
        def always_fail():
            raise ValueError("persistent")
        r1 = healer.protect(always_fail, "cb_test", max_retries=1)
        r2 = healer.protect(always_fail, "cb_test", max_retries=1)
        assert r1['success'] is False, "持久故障重试1次后必须如实失败"
        assert r2['success'] is False, "熔断后不得恢复为成功"

    def test_checkpoint_snapshot(self):
        snap = CheckpointSnapshot()
        sid = snap.save({"task": "test", "progress": 50})
        restored = snap.restore(sid)
        assert restored['task'] == "test"
        assert restored['progress'] == 50
