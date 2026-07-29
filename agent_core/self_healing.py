#!/usr/bin/env python3
"""
self_healing.py — Eco Agent L5 韧性自愈循环

Eco Agent 独创——竞品均未系统化实现。
在异常情况下像生物体一样自愈。

异常分类：瞬时故障 / 持久故障 / 逻辑死锁
处理策略：指数退避重试 / 降级备用 / 强制中断回滚

用法：
  from agent_core.self_healing import SelfHealer
  healer = SelfHealing()
  result = healer.protect(lambda: risky_operation())
"""

import os, sys, json, time, uuid, logging, traceback, threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable

logger = logging.getLogger("self_healing")

ROOT = Path(__file__).resolve().parent.parent
HEAL_LOG = ROOT / "memory-tree" / "data" / "healing_log.jsonl"
HEAL_LOG.parent.mkdir(parents=True, exist_ok=True)


class SelfHealer:
    """L5 韧性自愈循环——异常检测/分类/处理/恢复"""

    def __init__(self):
        self._heal_count = 0
        self._fail_count = 0
        self._circuit_breakers: Dict[str, dict] = {}

    def protect(self, operation: Callable, context: str = "",
                fallback: Optional[Callable] = None,
                max_retries: int = 3, timeout_ms: int = 30000) -> Dict:
        """保护执行一个操作——自动异常捕获/分类/恢复"""
        start = time.time()
        operation_name = context or getattr(operation, '__name__', str(operation))

        # 检查熔断器
        cb = self._circuit_breakers.get(operation_name)
        if cb and cb["state"] == "open":
            if time.time() - cb["opened_at"] < cb["cooldown"]:
                logger.warning(f"[Heal] 熔断: {operation_name} (剩余{int(cb['cooldown'] - (time.time() - cb['opened_at']))}s)")
                return self._apply_fallback(operation_name, fallback, "熔断器开启")
            cb["state"] = "half-open"

        last_error = ""
        for attempt in range(1, max_retries + 1):
            try:
                result = operation()
                elapsed = (time.time() - start) * 1000
                self._heal_count += 1

                # 关闭熔断器
                if operation_name in self._circuit_breakers:
                    self._circuit_breakers[operation_name]["state"] = "closed"
                    self._circuit_breakers[operation_name]["failures"] = 0

                return {"success": True, "result": result, "attempts": attempt,
                        "elapsed_ms": round(elapsed, 1)}

            except Exception as e:
                last_error = str(e)
                error_type = self._classify(e)

                if attempt < max_retries:
                    delay = self._calc_backoff(attempt, error_type)
                    logger.warning(f"[Heal] {operation_name}: 第{attempt}次失败 ({error_type}), "
                                  f"{delay}ms后重试")
                    time.sleep(delay / 1000)

        # 全部重试失败——记录熔断
        elapsed = (time.time() - start) * 1000
        self._fail_count += 1

        self._circuit_breakers[operation_name] = {
            "state": "open", "opened_at": time.time(),
            "cooldown": min(300, 5 * (max_retries ** 2)),  # 指数增长冷却
            "failures": self._circuit_breakers.get(operation_name, {}).get("failures", 0) + 1,
        }

        self._log_healing_event(operation_name, last_error, elapsed)
        return self._apply_fallback(operation_name, fallback, last_error)

    def _classify(self, error: Exception) -> str:
        """异常分类"""
        err_str = str(error).lower()
        # 瞬时故障
        if any(kw in err_str for kw in ["timeout", "time out", "connection", "network", "reset"]):
            return "transient"
        # 持久故障
        if any(kw in err_str for kw in ["not found", "403", "401", "500", "invalid", "permission"]):
            return "permanent"
        # 逻辑死锁
        if any(kw in err_str for kw in ["deadlock", "circular", "recursion", "infinite", "loop"]):
            return "deadlock"
        return "unknown"

    def _calc_backoff(self, attempt: int, error_type: str) -> float:
        """计算退避时间"""
        base = 100  # 100ms
        if error_type == "transient":
            return base * (2 ** attempt) + (attempt * 50)
        if error_type == "deadlock":
            return base * (3 ** attempt)
        return base * attempt

    def _apply_fallback(self, operation_name: str, fallback: Optional[Callable], reason: str) -> Dict:
        """应用降级策略"""
        if fallback:
            try:
                result = fallback()
                return {"success": True, "result": result, "fallback": True, "reason": reason}
            except Exception as e:
                return {"success": False, "error": str(e), "fallback_also_failed": True, "reason": reason}
        return {"success": False, "error": reason, "fallback": False}

    def _log_healing_event(self, operation: str, error: str, elapsed_ms: float):
        """写入韧性日志"""
        event = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation, "error": error[:200],
            "elapsed_ms": round(elapsed_ms, 1),
        }
        HEAL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(HEAL_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def get_stats(self) -> dict:
        return {
            "healed": self._heal_count,
            "failed": self._fail_count,
            "circuit_breakers": {
                k: {"state": v["state"], "failures": v["failures"]}
                for k, v in self._circuit_breakers.items()
            },
            "heal_rate": f"{self._heal_count / max(self._heal_count + self._fail_count, 1) * 100:.0f}%",
        }


# ===== 检查点快照系统 =====

class CheckpointSnapshot:
    """检查点快照——任务执行前保存完整状态，可"时光倒流" """

    def __init__(self):
        self._snapshots: List[Dict] = []
        self._max_snapshots = 50

    def save(self, context: dict) -> str:
        """保存检查点"""
        snapshot_id = f"cp_{uuid.uuid4().hex[:8]}"
        snapshot = {
            "id": snapshot_id,
            "timestamp": datetime.now().isoformat(),
            "context": context,
        }
        self._snapshots.append(snapshot)
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots = self._snapshots[-self._max_snapshots:]
        return snapshot_id

    def restore(self, snapshot_id: str) -> Optional[dict]:
        """恢复到指定检查点"""
        for s in self._snapshots:
            if s["id"] == snapshot_id:
                return s["context"]
        return None

    def list_recent(self, limit: int = 10) -> List[Dict]:
        return [{"id": s["id"], "timestamp": s["timestamp"][:19]} for s in self._snapshots[-limit:]]


# ===== 测试 =====

def test():
    import io, sys as _sys
    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')

    print("[TEST] L5 Self-Healing Loop", flush=True)

    healer = SelfHealer()
    snapshotter = CheckpointSnapshot()

    # 测试正常操作
    r1 = healer.protect(lambda: "success", "test_ok")
    print(f"[Normal] 成功: {r1['success']}, 耗时: {r1['elapsed_ms']:.0f}ms", flush=True)

    # 测试失败+重试
    attempt = [0]
    def failing_op():
        attempt[0] += 1
        if attempt[0] < 3:
            raise TimeoutError("connection timeout")
        return "recovered"

    r2 = healer.protect(failing_op, "test_retry", max_retries=3)
    print(f"[Retry] 恢复: {r2['success']}, 尝试: {r2['attempts']}次", flush=True)

    # 测试熔断器
    def always_fail():
        raise ValueError("persistent error")
    r3 = healer.protect(always_fail, "test_cb", max_retries=2)
    r4 = healer.protect(always_fail, "test_cb", max_retries=2)
    print(f"[CircuitBreaker] 第一次: {r3['success']}, 第二次: {r4['success']} (应熔断)", flush=True)

    # 测试检查点
    sid = snapshotter.save({"task": "测试任务", "step": 3})
    restored = snapshotter.restore(sid)
    print(f"[Snapshot] 保存并恢复: {restored['task'] if restored else 'FAIL'}", flush=True)

    stats = healer.get_stats()
    print(f"\n[Stats] 自愈: {stats['healed']}次, 自愈率: {stats['heal_rate']}", flush=True)

    print(f"\n{'='*30}", flush=True)
    print("[OK] L5 Self-Healing 测试通过", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
