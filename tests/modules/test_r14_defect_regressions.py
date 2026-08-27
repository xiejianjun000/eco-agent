"""r14 验证轮缺陷 D1-D4 回归测试（全 mock，零外呼）。"""
import json
import logging
import subprocess
import time
from unittest import mock

import pytest

import agent_core.os_sandbox as sb
from agent_core.os_sandbox import SandboxPolicy, build_bwrap_cmd, run_in_sandbox
from agent_core.semantic_guard import SemanticGuard


def _cp(args, rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, rc, stdout=stdout, stderr=stderr)


@pytest.fixture
def linux_bwrap_env():
    """强制走 bwrap 主路径。"""
    with mock.patch.object(sb, "is_linux", return_value=True), \
         mock.patch.object(sb, "bwrap_available", return_value=True), \
         mock.patch.object(sb.shutil, "which", return_value="/usr/bin/bwrap"):
        yield


# ─── D1：bwrap 运行时失败 → 自动降级执行，结果可区分 ──────────
class TestD1BwrapRuntimeFailureFallback:
    def test_launch_failure_all_tiers_falls_back_to_degraded(self, linux_bwrap_env, caplog):
        """bwrap 启动级失败（所有档位）→ 降级路径真正执行命令，结果可区分。"""
        def fake_run(argv, **kw):
            if argv[0] == "bwrap":
                return _cp(argv, rc=1,
                           stderr="bwrap: Can't mount proc on /newroot/proc: "
                                  "Operation not permitted")
            return _cp(argv, rc=0, stdout="EXECUTED")  # 降级路径真实执行
        with mock.patch.object(sb.subprocess, "run", side_effect=fake_run) as mrun, \
             caplog.at_level(logging.WARNING, logger="os_sandbox"):
            r = run_in_sandbox(["echo", "hi"], SandboxPolicy())
        assert r.returncode == 0 and r.stdout == "EXECUTED"
        assert r.sandbox_mode == "degraded"
        assert any("bwrap launch failed" in rec.getMessage() or "启动级失败" in rec.getMessage()
                   for rec in caplog.records)
        # 3 档 bwrap 尝试 + 1 次降级执行
        assert mrun.call_count == len(sb._BWRAP_TIERS) + 1

    def test_in_sandbox_command_failure_not_confused(self, linux_bwrap_env):
        """命令在沙箱内正常执行但返回非零（有业务输出）→ 不降级，原样返回。"""
        def fake_run(argv, **kw):
            return _cp(argv, rc=1, stdout="partial output\nsome error")  # 命令真的跑了
        with mock.patch.object(sb.subprocess, "run", side_effect=fake_run) as mrun:
            r = run_in_sandbox(["false"], SandboxPolicy())
        assert r.returncode == 1
        assert r.sandbox_mode == "bwrap"
        assert mrun.call_count == 1  # 未触发退化/降级

    def test_silent_fast_failure_detected_as_launch_failure(self, linux_bwrap_env, caplog):
        """rc=1 且无任何输出且秒退 → 判定为启动级失败并降级。"""
        def fake_run(argv, **kw):
            if argv[0] == "bwrap":
                return _cp(argv, rc=1, stdout="", stderr="")
            return _cp(argv, rc=0, stdout="OK")
        with mock.patch.object(sb.subprocess, "run", side_effect=fake_run), \
             caplog.at_level(logging.WARNING, logger="os_sandbox"):
            r = run_in_sandbox(["true"], SandboxPolicy())
        assert r.stdout == "OK" and r.sandbox_mode == "degraded"


# ─── D2：--unshare-pid / --proc 解耦 + 逐档退化重试 ──────────
class TestD2PidProcDecoupled:
    def test_tier1_drops_proc_and_succeeds(self, linux_bwrap_env, caplog):
        """档0（pid+proc）失败 → 档1（pid、无 proc）重试成功。"""
        calls = []

        def fake_run(argv, **kw):
            calls.append(argv)
            if argv[0] != "bwrap":
                return _cp(argv, rc=0, stdout="SHOULD-NOT-HAPPEN")
            if "--proc" in argv:
                return _cp(argv, rc=1, stderr="bwrap: Can't mount proc on /newroot/proc")
            return _cp(argv, rc=0, stdout="TIER1-OK")
        with mock.patch.object(sb.subprocess, "run", side_effect=fake_run), \
             caplog.at_level(logging.WARNING, logger="os_sandbox"):
            r = run_in_sandbox(["echo", "hi"], SandboxPolicy())
        assert r.returncode == 0 and r.stdout == "TIER1-OK"
        assert r.sandbox_mode == "bwrap:tier1"
        assert len(calls) == 2  # 只重试到档1
        assert "--unshare-pid" in calls[1] and "--proc" not in calls[1]

    def test_build_cmd_flags_independent(self):
        cmd_full = build_bwrap_cmd(["x"], SandboxPolicy())
        assert "--unshare-pid" in cmd_full and "--proc" in cmd_full
        cmd_noproc = build_bwrap_cmd(["x"], SandboxPolicy(), mount_proc=False)
        assert "--unshare-pid" in cmd_noproc and "--proc" not in cmd_noproc
        cmd_nopid = build_bwrap_cmd(["x"], SandboxPolicy(), unshare_pid=False)
        assert "--unshare-pid" not in cmd_nopid and "--proc" in cmd_nopid
        cmd_min = build_bwrap_cmd(["x"], SandboxPolicy(),
                                  unshare_pid=False, mount_proc=False)
        assert "--unshare-pid" not in cmd_min and "--proc" not in cmd_min

    def test_tiers_capped_at_three_and_last_tier_minimal(self):
        assert len(sb._BWRAP_TIERS) == 3
        assert sb._BWRAP_TIERS[-1] == (False, False)


# ─── D3：allowed/readonly 路径存在性预检 ─────────────────────
class TestD3PathPrecheck:
    def test_nonexistent_allowed_path_filtered_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="os_sandbox"):
            cmd = build_bwrap_cmd(
                ["x"], SandboxPolicy(allowed_paths=["/definitely/not/exist-xyz"]))
        assert "/definitely/not/exist-xyz" not in cmd
        assert any("allowed_path 不存在" in rec.getMessage() for rec in caplog.records)

    def test_existing_paths_kept_nonexistent_readonly_filtered(self, tmp_path, caplog):
        real = str(tmp_path)
        with caplog.at_level(logging.WARNING, logger="os_sandbox"):
            cmd = build_bwrap_cmd(
                ["x"], SandboxPolicy(allowed_paths=[real],
                                     readonly_paths=["/no/such-ro-dir"]))
        i = cmd.index("--bind")
        assert cmd[i + 1:i + 3] == [real, real]
        assert "/no/such-ro-dir" not in cmd
        assert any("readonly_path 不存在" in rec.getMessage() for rec in caplog.records)


# ─── D4：默认 timeout 5000ms + 超时独立策略 ──────────────────
class TestD4TimeoutPolicy:
    def test_default_timeout_is_5000ms(self):
        assert SemanticGuard().timeout_ms == 5000

    def test_timeout_defaults_to_allow_with_warn(self, caplog):
        """超时 = judge 不可用 → 默认放行 + WARN，区别于明确判定注入。"""
        def slow(prompt):
            time.sleep(2)
            return json.dumps({"is_injection": True, "confidence": 1.0})
        g = SemanticGuard(judge_fn=slow, timeout_ms=50)
        with caplog.at_level(logging.WARNING):
            ok, reason = g.semantic_check("任意输入")
        assert ok is True
        assert "judge 不可用" in reason and "超时" in reason
        assert any("超时" in rec.getMessage() for rec in caplog.records)

    def test_timeout_allow_distinct_from_injection_verdict(self):
        """超时放行与 judge 明确判注入（拦截）语义区分。"""
        g_timeout = SemanticGuard(judge_fn=lambda p: time.sleep(2), timeout_ms=50)
        ok_t, reason_t = g_timeout.semantic_check("x")
        g_block = SemanticGuard(
            judge_fn=lambda p: json.dumps({"is_injection": True, "confidence": 0.99}))
        ok_b, reason_b = g_block.semantic_check("x")
        assert ok_t is True and "不可用" in reason_t
        assert ok_b is False and "注入" in reason_b

    def test_invalid_on_timeout_rejected(self):
        with pytest.raises(ValueError):
            SemanticGuard(on_timeout="bogus")
