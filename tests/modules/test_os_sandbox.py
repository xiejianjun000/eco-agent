"""Task A — os_sandbox 测试：策略构造、bwrap 拼装、降级、env 清洗、网络白名单。"""
import os
import subprocess
import sys
from unittest import mock

import pytest

from agent_core import os_sandbox
from agent_core.os_sandbox import SandboxPolicy, run_in_sandbox, build_bwrap_cmd, scrub_env


def _cp(rc=0, out="ok", err=""):
    return subprocess.CompletedProcess(args=["x"], returncode=rc, stdout=out, stderr=err)


# ─── SandboxPolicy 构造 ────────────────────────
class TestPolicy:
    def test_defaults(self):
        p = SandboxPolicy()
        assert p.allowed_paths == [] and p.readonly_paths == []
        assert p.network_allowlist == [] and p.max_seconds == 30
        assert p.max_output_bytes == 1024 * 1024

    def test_custom(self):
        p = SandboxPolicy(allowed_paths=["/tmp/w"], readonly_paths=["/data"],
                          network_allowlist=["api.example.com"], max_seconds=5,
                          max_output_bytes=128)
        assert p.allowed_paths == ["/tmp/w"]
        assert p.readonly_paths == ["/data"]
        assert p.network_allowlist == ["api.example.com"]
        assert p.max_seconds == 5 and p.max_output_bytes == 128


# ─── env 清洗 ─────────────────────────────────
class TestScrubEnv:
    def test_strips_sensitive(self):
        env = {"PATH": "/bin", "OPENAI_API_KEY": "x", "GH_TOKEN": "y",
               "APP_SECRET": "z", "NORMAL": "1"}
        out = scrub_env(env)
        assert out == {"PATH": "/bin", "NORMAL": "1"}

    def test_does_not_mutate_input(self):
        env = {"A_KEY": "1", "B": "2"}
        scrub_env(env)
        assert env == {"A_KEY": "1", "B": "2"}

    def test_mid_name_not_stripped(self):
        env = {"KEYSTONE": "1", "MY_KEY_DIR": "2", "TOKENIZER": "3"}
        out = scrub_env(env)
        # 仅剔除 *_KEY/*_TOKEN/*_SECRET 结尾
        assert "KEYSTONE" in out and "TOKENIZER" in out
        assert "MY_KEY_DIR" in out

    def test_uses_os_environ_by_default(self):
        with mock.patch.dict(os.environ, {"TEST_SBX_SECRET": "s"}, clear=False):
            out = scrub_env()
            assert "TEST_SBX_SECRET" not in out


# ─── bwrap 命令行拼装 ─────────────────────────
class TestBwrapCmd:
    def test_basic_structure(self):
        p = SandboxPolicy(allowed_paths=["/w"])
        cmd = build_bwrap_cmd(["echo", "hi"], p)
        assert cmd[0] == "bwrap"
        assert cmd[-3:] == ["--", "echo", "hi"]
        assert "--die-with-parent" in cmd
        assert "--unshare-pid" in cmd

    def test_no_network_allowlist_unshares_net(self):
        cmd = build_bwrap_cmd(["x"], SandboxPolicy())
        assert "--unshare-net" in cmd

    def test_allowlist_without_slirp_still_unshares(self):
        p = SandboxPolicy(network_allowlist=["a.com"])
        cmd = build_bwrap_cmd(["x"], p, slirp=False)
        assert "--unshare-net" in cmd

    def test_allowlist_with_slirp_keeps_net(self):
        p = SandboxPolicy(network_allowlist=["a.com", "b.com"])
        cmd = build_bwrap_cmd(["x"], p, slirp=True)
        assert "--unshare-net" not in cmd
        i = cmd.index("--setenv")
        assert cmd[i + 1] == "ECO_NET_ALLOWLIST"
        assert cmd[i + 2] == "a.com,b.com"

    def test_bind_modes(self):
        p = SandboxPolicy(allowed_paths=["/rw"], readonly_paths=["/ro"])
        cmd = build_bwrap_cmd(["x"], p)
        i = cmd.index("--bind")
        assert cmd[i + 1:i + 3] == ["/rw", "/rw"]
        pairs = [(cmd[i], cmd[i + 1], cmd[i + 2])
                 for i in range(len(cmd) - 2) if cmd[i] in ("--bind", "--ro-bind")]
        assert ("--ro-bind", "/ro", "/ro") in pairs
        assert ("--bind", "/rw", "/rw") in pairs

    def test_system_dirs_ro_bind(self):
        cmd = build_bwrap_cmd(["x"], SandboxPolicy())
        assert "--proc" in cmd and "--dev" in cmd and "--tmpfs" in cmd
        # 存在的系统目录只读 bind
        with mock.patch("os.path.exists", return_value=True):
            cmd2 = build_bwrap_cmd(["x"], SandboxPolicy())
        assert "/usr" in cmd2 and "/lib" in cmd2


# ─── run_in_sandbox 主路径 ────────────────────
class TestRunInSandbox:
    def test_non_linux_degrades_with_warning(self, caplog):
        with mock.patch.object(os_sandbox.platform, "system", return_value="Darwin"), \
             mock.patch("subprocess.run", return_value=_cp()) as run:
            import logging
            with caplog.at_level(logging.WARNING, logger="os_sandbox"):
                r = run_in_sandbox(["echo", "hi"], SandboxPolicy())
        assert r.returncode == 0
        assert "degraded" in caplog.text and "Darwin" in caplog.text
        # 降级：直接跑原命令（非 bwrap）
        assert run.call_args[0][0] == ["echo", "hi"]

    def test_linux_no_bwrap_degrades(self, caplog):
        import logging
        with mock.patch.object(os_sandbox, "is_linux", return_value=True), \
             mock.patch.object(os_sandbox, "bwrap_available", return_value=False), \
             mock.patch("subprocess.run", return_value=_cp()) as run:
            with caplog.at_level(logging.WARNING, logger="os_sandbox"):
                run_in_sandbox(["ls"], SandboxPolicy())
        assert "bwrap" in caplog.text
        assert run.call_args[0][0] == ["ls"]

    def test_linux_with_bwrap_wraps(self):
        with mock.patch.object(os_sandbox, "is_linux", return_value=True), \
             mock.patch.object(os_sandbox, "bwrap_available", return_value=True), \
             mock.patch.object(os_sandbox.shutil, "which", return_value=None), \
             mock.patch("subprocess.run", return_value=_cp()) as run:
            run_in_sandbox(["ls", "/"], SandboxPolicy(max_seconds=7))
        called = run.call_args[0][0]
        assert called[0] == "bwrap"
        assert called[-3:] == ["--", "ls", "/"]
        assert run.call_args[1]["timeout"] == 7

    def test_bwrap_env_is_scrubbed(self):
        with mock.patch.object(os_sandbox, "is_linux", return_value=True), \
             mock.patch.object(os_sandbox, "bwrap_available", return_value=True), \
             mock.patch("subprocess.run", return_value=_cp()) as run, \
             mock.patch.dict(os.environ, {"MY_API_KEY": "k", "X": "1"}, clear=False):
            run_in_sandbox(["ls"], SandboxPolicy())
        env = run.call_args[1]["env"]
        assert "MY_API_KEY" not in env and env.get("X") == "1"

    def test_output_truncation(self):
        big = "A" * 5000
        with mock.patch.object(os_sandbox, "is_linux", return_value=True), \
             mock.patch.object(os_sandbox, "bwrap_available", return_value=True), \
             mock.patch("subprocess.run", return_value=_cp(out=big, err=big)):
            r = run_in_sandbox(["ls"], SandboxPolicy(max_output_bytes=100))
        assert len(r.stdout) == 100 and len(r.stderr) == 100

    def test_degraded_truncation_and_timeout(self):
        big = "B" * 999
        with mock.patch.object(os_sandbox, "is_linux", return_value=False), \
             mock.patch("subprocess.run", return_value=_cp(out=big)) as run:
            r = run_in_sandbox(["ls"], SandboxPolicy(max_output_bytes=10, max_seconds=3))
        assert r.stdout == "B" * 10
        assert run.call_args[1]["timeout"] == 3

    def test_default_policy_when_none(self):
        with mock.patch.object(os_sandbox, "is_linux", return_value=True), \
             mock.patch.object(os_sandbox, "bwrap_available", return_value=True), \
             mock.patch("subprocess.run", return_value=_cp()) as run:
            run_in_sandbox(["true"])
        assert run.call_args[1]["timeout"] == 30

    def test_allowlist_without_slirp_warns(self, caplog):
        import logging
        with mock.patch.object(os_sandbox, "is_linux", return_value=True), \
             mock.patch.object(os_sandbox, "bwrap_available", return_value=True), \
             mock.patch.object(os_sandbox.shutil, "which",
                               side_effect=lambda x: "/usr/bin/bwrap" if x == "bwrap" else None), \
             mock.patch("subprocess.run", return_value=_cp()):
            with caplog.at_level(logging.WARNING, logger="os_sandbox"):
                run_in_sandbox(["ls"], SandboxPolicy(network_allowlist=["a.com"]))
        assert "slirp4netns" in caplog.text


# ─── 降级 rlimits ─────────────────────────────
class TestDegradedLimits:
    def test_preexec_sets_rlimits(self):
        import resource
        calls = []

        def fake_setrlimit(res, lim):
            calls.append((res, lim))

        with mock.patch.object(os_sandbox, "is_linux", return_value=False), \
             mock.patch.object(resource, "setrlimit", side_effect=fake_setrlimit), \
             mock.patch("subprocess.run", return_value=_cp()) as run:
            run_in_sandbox(["x"], SandboxPolicy(max_seconds=9))
            preexec = run.call_args[1]["preexec_fn"]
            preexec()
        resources = {r for r, _ in calls}
        assert resource.RLIMIT_CPU in resources
        assert resource.RLIMIT_AS in resources
        assert resource.RLIMIT_NOFILE in resources
        cpu = dict(calls)[resource.RLIMIT_CPU]
        assert cpu == (9, 14)


# ─── sandbox.py 集成 ──────────────────────────
class TestSandboxIntegration:
    def test_execute_prefers_os_sandbox(self):
        import asyncio
        from agent_core import sandbox

        sb = sandbox.DockerSandbox()
        sb._available = False
        with mock.patch.object(sandbox.os_sandbox, "run_in_sandbox",
                               return_value=_cp(rc=0, out="hello", err="")) as ris:
            r = asyncio.run(sb.execute("print('hi')", "python"))
        assert ris.called
        assert r["success"] and r["stdout"] == "hello"
        assert r["sandbox"] == "os_sandbox"

    def test_execute_falls_back_to_local_on_error(self):
        import asyncio
        from agent_core import sandbox

        sb = sandbox.DockerSandbox()
        sb._available = False
        with mock.patch.object(sandbox.os_sandbox, "run_in_sandbox",
                               side_effect=RuntimeError("boom")):
            r = asyncio.run(sb.execute("result=1+1", "python"))
        assert r["sandbox"] == "local" and r["success"]

    def test_os_sandbox_timeout_result(self):
        import asyncio
        from agent_core import sandbox

        sb = sandbox.DockerSandbox(timeout=3)
        sb._available = False
        with mock.patch.object(sandbox.os_sandbox, "run_in_sandbox",
                               side_effect=subprocess.TimeoutExpired("x", 3)):
            r = asyncio.run(sb.execute("print(1)", "python"))
        assert not r["success"] and "Timeout" in r["stderr"]
