"""
eco Agent OS-level sandbox — 对标 Codex bubblewrap / Claude Code Seatbelt

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
import time
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


def scrub_env(env: dict | None = None) -> dict:
    """剔除敏感环境变量（*_KEY / *_TOKEN / *_SECRET），返回副本。"""
    src = dict(os.environ if env is None else env)
    return {k: v for k, v in src.items() if not _SENSITIVE_ENV_RE.search(k)}


def bwrap_available() -> bool:
    return shutil.which("bwrap") is not None


def is_linux() -> bool:
    return platform.system() == "Linux"


def build_bwrap_cmd(cmd: list[str], policy: SandboxPolicy,
                    slirp: bool = False,
                    unshare_pid: bool = True,
                    mount_proc: bool = True) -> list[str]:
    """拼装 bubblewrap 命令行（纯函数，便于测试）。

    - unshare pid/ipc/uts；网络命名空间默认隔离（--unshare-net）
    - 有 network_allowlist 且 slirp 可用时保留网络（由外层 slirp4netns 限速/白名单），
      否则强制 --unshare-net
    - allowed_paths 可写 bind，readonly_paths + 系统目录只读 bind
    - ``unshare_pid`` / ``mount_proc`` 可独立关闭：部分内核/容器环境拒绝
      ``--unshare-pid`` 与 ``--proc`` 组合（实测 "Can't mount proc on
      /newroot/proc: Operation not permitted"），run_in_sandbox 会探测并逐档退化
    - 不存在的 allowed/readonly 路径在绑定前过滤并 warning（D3：
      bwrap 对缺失路径硬失败 "Can't find source path"）
    """
    args = ["bwrap", "--die-with-parent", "--new-session",
            "--unshare-ipc", "--unshare-uts"]
    if unshare_pid:
        args.append("--unshare-pid")
    if not (policy.network_allowlist and slirp):
        args.append("--unshare-net")

    if mount_proc:
        args += ["--proc", "/proc"]
    args += ["--dev", "/dev", "--tmpfs", "/tmp"]

    for d in _SYSTEM_RO_DIRS:
        if os.path.exists(d):
            args += ["--ro-bind", d, d]
    for p in policy.readonly_paths:
        if os.path.exists(p):
            args += ["--ro-bind", p, p]
        else:
            log.warning("os_sandbox: readonly_path 不存在，已跳过: %s", p)
    for p in policy.allowed_paths:
        if os.path.exists(p):
            args += ["--bind", p, p]
        else:
            log.warning("os_sandbox: allowed_path 不存在，已跳过: %s", p)

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

    try:
        result = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=policy.max_seconds,
            env=scrub_env(),
            preexec_fn=preexec,
        )
    except subprocess.SubprocessError:
        # 部分平台（如 macOS 受限环境）preexec_fn 不可用——不带 preexec 重试一次
        if preexec is None:
            raise
        log.warning("preexec_fn unavailable on this platform, retrying without rlimits: %s", cmd[:1])
        result = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=policy.max_seconds,
            env=scrub_env(),
            preexec_fn=None,
        )
    result.stdout = _truncate(result.stdout, policy.max_output_bytes)
    result.stderr = _truncate(result.stderr, policy.max_output_bytes)
    return result


# bwrap 启动级失败判定阈值：进程在该时间内退出且无业务输出，视为 bwrap 自身失败
_BWRAP_LAUNCH_FAIL_SECONDS = 2.0

# bwrap 参数退化档位：(unshare_pid, mount_proc)
# 档0 完整隔离 → 档1 去 proc 挂载 → 档2 去 pid 命名空间与 proc 挂载
_BWRAP_TIERS: list[tuple[bool, bool]] = [(True, True), (True, False), (False, False)]


def _is_bwrap_launch_failure(result: subprocess.CompletedProcess,
                             elapsed: float) -> bool:
    """区分「bwrap 启动级失败」（命令从未执行）与「沙箱内命令正常返回非零」。

    判定特征（满足其一）：
    - stderr 带 bwrap 自身错误前缀 "bwrap:"（如 "bwrap: Can't mount proc ..."）
    - rc==1 且 stdout/stderr 均无业务输出且耗时低于阈值
    """
    stderr = (result.stderr or "").strip()
    if stderr.startswith("bwrap:"):
        return True
    return (result.returncode == 1
            and not (result.stdout or "").strip()
            and not stderr
            and elapsed < _BWRAP_LAUNCH_FAIL_SECONDS)


def run_in_sandbox(cmd: list[str],
                   policy: SandboxPolicy | None = None) -> subprocess.CompletedProcess:
    """在 OS 级沙箱中执行命令，返回 CompletedProcess。

    Linux + bwrap → 内核级隔离；否则降级（rlimit/timeout/env 清洗 + warning）。

    bwrap 二进制存在但启动级失败（如内核拒绝 --unshare-pid+--proc 组合）时：
    先按档位退化 bwrap 参数重试（档位数见模块常量 _BWRAP_TIERS），仍失败则自动降级到 rlimit
    路径执行并 logging.warning 记录。返回结果带 ``sandbox_mode`` 属性
    （"bwrap" / "bwrap:tierN" / "degraded" / "non-linux"），调用方可区分
    「命令在沙箱内失败」与「沙箱未能启动后降级执行」。
    """
    policy = policy or SandboxPolicy()

    if not is_linux():
        r = _run_degraded(cmd, policy, reason=f"non-Linux platform {platform.system()}")
        r.sandbox_mode = "non-linux"
        return r

    if not bwrap_available():
        r = _run_degraded(cmd, policy, reason="bubblewrap (bwrap) not found")
        r.sandbox_mode = "degraded"
        return r

    slirp = shutil.which("slirp4netns") is not None
    if policy.network_allowlist and not slirp:
        log.warning("network_allowlist=%s requested but slirp4netns missing; "
                    "falling back to --unshare-net", policy.network_allowlist)

    last_err = ""
    for tier, (unshare_pid, mount_proc) in enumerate(_BWRAP_TIERS):
        wrapped = build_bwrap_cmd(cmd, policy, slirp=slirp,
                                  unshare_pid=unshare_pid, mount_proc=mount_proc)
        start = time.monotonic()
        try:
            result = subprocess.run(
                wrapped,
                capture_output=True,
                text=True,
                timeout=policy.max_seconds,
                env=scrub_env(),
            )
        except OSError as exc:  # bwrap 启动即失败（如 exec 拒绝）
            last_err = str(exc)
            log.warning("os_sandbox bwrap launch error (tier %d): %s", tier, exc)
            continue
        elapsed = time.monotonic() - start
        if not _is_bwrap_launch_failure(result, elapsed):
            result.stdout = _truncate(result.stdout, policy.max_output_bytes)
            result.stderr = _truncate(result.stderr, policy.max_output_bytes)
            result.sandbox_mode = "bwrap" if tier == 0 else f"bwrap:tier{tier}"
            if tier > 0:
                log.warning("os_sandbox bwrap 完整参数启动失败，已退化到 tier %d "
                            "(unshare_pid=%s, mount_proc=%s) 执行成功",
                            tier, unshare_pid, mount_proc)
            return result
        last_err = (result.stderr or "").strip() or f"rc=1 in {elapsed:.3f}s"
        log.warning("os_sandbox bwrap 启动级失败 (tier %d, unshare_pid=%s, "
                    "mount_proc=%s): %s", tier, unshare_pid, mount_proc, last_err)

    r = _run_degraded(cmd, policy,
                      reason=f"bwrap launch failed at all tiers ({last_err})")
    r.sandbox_mode = "degraded"
    return r
