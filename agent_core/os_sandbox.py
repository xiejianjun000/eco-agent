"""
ECO AGENT OS-level sandbox — 对标 Codex bubblewrap / Claude Code Seatbelt

Linux 优先使用 bubblewrap(bwrap) 做内核级隔离：
  - unshare net/pid 命名空间
  - 只读 bind 系统目录，可写目录仅限 policy.allowed_paths
  - 网络命名空间隔离；可选 slirp4netns + 域名白名单
bwrap 不存在 / 非 Linux 时降级：
  - resource.setrlimit(CPU/AS/NOFILE) + timeout
  - 环境变量清洗（剔除 *_KEY / *_TOKEN / *_SECRET）
  - logging.warning 记录降级
"""
from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("os_sandbox")

# 降级路径的默认资源限额
_RLIMIT_AS_BYTES = 512 * 1024 * 1024   # 512MB 地址空间
_RLIMIT_NOFILE = 256

# bwrap 只读 bind 的系统目录（存在才 bind）
_SYSTEM_RO_DIRS = ["/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc/ld.so.cache"]

_SENSITIVE_ENV_RE = re.compile(r"(_KEY|_TOKEN|_SECRET)$")


@dataclass
class SandboxPolicy:
    """沙箱执行策略"""
    allowed_paths: list[str] = field(default_factory=list)    # 可读写
    readonly_paths: list[str] = field(default_factory=list)   # 只读
    network_allowlist: list[str] = field(default_factory=list)  # 允许访问的域名
    max_seconds: int = 30
    max_output_bytes: int = 1024 * 1024


def scrub_env(env: Optional[dict] = None) -> dict:
    """剔除敏感环境变量（*_KEY / *_TOKEN / *_SECRET），返回副本。"""
    src = dict(os.environ if env is None else env)
    return {k: v for k, v in src.items() if not _SENSITIVE_ENV_RE.search(k)}


def bwrap_available() -> bool:
    return shutil.which("bwrap") is not None


def is_linux() -> bool:
    return platform.system() == "Linux"


def build_bwrap_cmd(cmd: list[str], policy: SandboxPolicy,
                    slirp: bool = False) -> list[str]:
    """拼装 bubblewrap 命令行（纯函数，便于测试）。

    - unshare pid/ipc/uts；网络命名空间默认隔离（--unshare-net）
    - 有 network_allowlist 且 slirp 可用时保留网络（由外层 slirp4netns 限速/白名单），
      否则强制 --unshare-net
    - allowed_paths 可写 bind，readonly_paths + 系统目录只读 bind
    """
    args = ["bwrap", "--die-with-parent", "--new-session",
            "--unshare-pid", "--unshare-ipc", "--unshare-uts"]
    if not (policy.network_allowlist and slirp):
        args.append("--unshare-net")

    args += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]

    for d in _SYSTEM_RO_DIRS:
        if os.path.exists(d):
            args += ["--ro-bind", d, d]
    for p in policy.readonly_paths:
        args += ["--ro-bind", p, p]
    for p in policy.allowed_paths:
        args += ["--bind", p, p]

    # 域名白名单通过环境变量传给命名空间内的代理/ wrapper 使用
    if policy.network_allowlist:
        args += ["--setenv", "ECO_NET_ALLOWLIST",
                 ",".join(policy.network_allowlist)]

    args += ["--"] + list(cmd)
    return args


def _truncate(data, limit: int):
    if data is None:
        return data
    return data[:limit]


def _run_degraded(cmd: list[str], policy: SandboxPolicy,
                  reason: str) -> subprocess.CompletedProcess:
    """降级路径：rlimit + timeout + env 清洗。"""
    log.warning("os_sandbox degraded execution (%s): %s", reason, cmd[:1])

    preexec = None
    try:
        import resource

        def _limits():
            resource.setrlimit(resource.RLIMIT_CPU,
                               (policy.max_seconds, policy.max_seconds + 5))
            resource.setrlimit(resource.RLIMIT_AS,
                               (_RLIMIT_AS_BYTES, _RLIMIT_AS_BYTES))
            resource.setrlimit(resource.RLIMIT_NOFILE,
                               (_RLIMIT_NOFILE, _RLIMIT_NOFILE))
        preexec = _limits
    except ImportError:
        log.warning("resource module unavailable, rlimits skipped")

    result = subprocess.run(
        list(cmd),
        capture_output=True,
        text=True,
        timeout=policy.max_seconds,
        env=scrub_env(),
        preexec_fn=preexec,
    )
    result.stdout = _truncate(result.stdout, policy.max_output_bytes)
    result.stderr = _truncate(result.stderr, policy.max_output_bytes)
    return result


def run_in_sandbox(cmd: list[str],
                   policy: Optional[SandboxPolicy] = None) -> subprocess.CompletedProcess:
    """在 OS 级沙箱中执行命令，返回 CompletedProcess。

    Linux + bwrap → 内核级隔离；否则降级（rlimit/timeout/env 清洗 + warning）。
    """
    policy = policy or SandboxPolicy()

    if not is_linux():
        return _run_degraded(cmd, policy, reason=f"non-Linux platform {platform.system()}")

    if not bwrap_available():
        return _run_degraded(cmd, policy, reason="bubblewrap (bwrap) not found")

    slirp = shutil.which("slirp4netns") is not None
    if policy.network_allowlist and not slirp:
        log.warning("network_allowlist=%s requested but slirp4netns missing; "
                    "falling back to --unshare-net", policy.network_allowlist)

    wrapped = build_bwrap_cmd(cmd, policy, slirp=slirp)
    result = subprocess.run(
        wrapped,
        capture_output=True,
        text=True,
        timeout=policy.max_seconds,
        env=scrub_env(),
    )
    result.stdout = _truncate(result.stdout, policy.max_output_bytes)
    result.stderr = _truncate(result.stderr, policy.max_output_bytes)
    return result
