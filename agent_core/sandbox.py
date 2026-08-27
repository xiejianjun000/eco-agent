"""
eco Agent sandbox — 安全代码执行环境（对标 HERMES Docker Sandbox）
支持: Python/Shell/Node 代码在隔离容器中执行
"""
import os
import sys
import json
import tempfile
import subprocess
import asyncio
import logging
import shutil
from pathlib import Path
from typing import Optional

log = logging.getLogger("sandbox")

try:
    from agent_core import os_sandbox
except Exception:  # pragma: no cover - os_sandbox 缺失时不影响旧路径
    os_sandbox = None

# ─── Docker Sandbox ───────────────────────────

class DockerSandbox:
    """Docker 容器沙箱 — 安全执行不可信代码"""

    IMAGE = "python:3.12-slim"

    def __init__(self, timeout: int = 30, memory_limit: str = "256m"):
        self._timeout = timeout
        self._memory_limit = memory_limit
        self._available = self._check_docker()

    def _check_docker(self) -> bool:
        try:
            subprocess.run(["docker", "info"], capture_output=True, timeout=5)
            return True
        except Exception:
            return False

    def available(self) -> bool:
        return self._available

    async def execute(self, code: str, language: str = "python") -> dict:
        """三级降级执行：Docker → OS 级(bwrap/rlimit) → 本地受限。"""
        if self._available:
            result = await self._run_docker(code, language)
            # Docker 守护进程掉线/连接失败：标记不可用并降级，后续调用跳过 docker
            if not result.get("success") and any(
                k in str(result.get("stderr", "")).lower()
                for k in ("daemon", "connect", "socket", "no such file")
            ):
                log.warning("docker daemon unavailable → os/local sandbox 降级: %s",
                            str(result.get("stderr"))[:120])
                self._available = False
            else:
                return result
        os_result = await self._os_sandbox_execute(code, language)
        if os_result is not None:
            return os_result
        return await self._local_fallback(code, language)

    async def _run_docker(self, code: str, language: str = "python") -> dict:
        ext = {"python": ".py", "shell": ".sh", "node": ".js"}.get(language, ".py")
        work_dir = Path(tempfile.mkdtemp(prefix="eco_sandbox_"))
        script_path = work_dir / f"script{ext}"

        if language == "shell":
            script_path.write_text("#!/bin/bash\n" + code)
            script_path.chmod(0o755)
        else:
            script_path.write_text(code)

        cmd = [
            "docker", "run", "--rm",
            "--memory", self._memory_limit,
            "--network", "none",
            "--read-only",
            "-v", f"{script_path}:/script{ext}:ro",
            self.IMAGE,
        ]
        exec_cmd = {"python": ["python", "/script.py"], "shell": ["bash", "/script.sh"], "node": ["node", "/script.js"]}
        cmd += exec_cmd.get(language, ["python", "/script.py"])

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self._timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:2000],
                "exit_code": result.returncode,
                "sandbox": "docker"
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": f"Timeout ({self._timeout}s)", "sandbox": "docker"}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "sandbox": "docker"}
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    async def _os_sandbox_execute(self, code: str, language: str = "python") -> dict | None:
        """通过 os_sandbox（bubblewrap / 降级 rlimit）执行；失败返回 None 走旧本地路径"""
        if os_sandbox is None:
            return None
        interpreter = {"python": [sys.executable], "shell": ["bash"], "node": ["node"]}.get(language)
        if interpreter is None:
            return None
        if language != "python" and shutil.which(interpreter[0]) is None:
            return None

        ext = {"python": ".py", "shell": ".sh", "node": ".js"}.get(language, ".py")
        work_dir = Path(tempfile.mkdtemp(prefix="eco_os_sandbox_"))
        script_path = work_dir / f"script{ext}"
        script_path.write_text(code)

        policy = os_sandbox.SandboxPolicy(
            allowed_paths=[str(work_dir)],
            readonly_paths=[],
            network_allowlist=[],          # 默认断网
            max_seconds=self._timeout,
            max_output_bytes=64 * 1024,
        )
        try:
            result = os_sandbox.run_in_sandbox(interpreter + [str(script_path)], policy)
            return {
                "success": result.returncode == 0,
                "stdout": (result.stdout or "")[:5000],
                "stderr": (result.stderr or "")[:2000],
                "exit_code": result.returncode,
                "sandbox": "os_sandbox",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": f"Timeout ({self._timeout}s)", "sandbox": "os_sandbox"}
        except Exception as e:
            log.warning("os_sandbox execution failed, falling back to local: %s", e)
            return None
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    async def _local_fallback(self, code: str, language: str = "python") -> dict:
        """本地安全执行（受限环境）"""
        if language == "python":
            import ast
            try:
                ast.parse(code)
            except SyntaxError as e:
                return {"success": False, "stdout": "", "stderr": f"SyntaxError: {e}", "sandbox": "local"}

            # Block dangerous modules
            blocked = ["os.system", "os.popen", "subprocess", "shutil.rmtree"]
            for b in blocked:
                if b in code:
                    return {"success": False, "stdout": "", "stderr": f"Blocked: {b}", "sandbox": "local"}

            try:
                ns = {}
                exec(code, {"__builtins__": __builtins__}, ns)
                return {"success": True, "stdout": str(ns.get("result", "")), "sandbox": "local"}
            except Exception as e:
                return {"success": False, "stdout": "", "stderr": str(e), "sandbox": "local"}

        return {"success": False, "stdout": "", "stderr": "Docker unavailable, only Python local fallback", "sandbox": "none"}

# ─── Tool 注册 ────────────────────────────────
def get_sandbox_tool_def():
    return {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": "在安全沙箱中执行代码（Python/Shell/Node），适合数据处理、计算、文件分析",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "要执行的代码"},
                    "language": {"type": "string", "enum": ["python", "shell", "node"], "description": "代码语言"}
                },
                "required": ["code", "language"]
            }
        }
    }

_sandbox = None
async def execute_code(code: str, language: str = "python") -> str:
    global _sandbox
    if _sandbox is None:
        _sandbox = DockerSandbox()
    result = await _sandbox.execute(code, language)
    return json.dumps(result, ensure_ascii=False)

# ─── Test ────────────────────────────────────
if __name__ == "__main__":
    r = asyncio.run(execute_code("print('hello')", "python"))
    print(json.loads(r))
