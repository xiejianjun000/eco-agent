"""腾讯文档 HTML → 在线文档 一键上云管线.

链路（对齐 ecoskills/tencent-docs 官方 aipage 工作流）:
  HTML ──aipage_pack.js──> .aipage ──manage.pre_import──> COS PUT 直传
      ──manage.async_import──> manage.import_progress 轮询(≤60s) ──> docs.qq.com 链接

不依赖 mcporter CLI：直接用 mcp SDK 开 Streamable HTTP 会话调用官方 MCP
（https://docs.qq.com/openapi/mcp，Authorization: TENCENT_DOCS_TOKEN）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import pathlib
import subprocess
import tempfile
from typing import Any

import httpx

logger = logging.getLogger("eco.tdocs_import")

TENCENT_MCP_URL = "https://docs.qq.com/openapi/mcp"
TENCENT_TOKEN_ENV = "TENCENT_DOCS_TOKEN"
PACK_SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "ecoskills" / "tencent-docs" / "aipage_pack.js"

POLL_INTERVAL = 3.0  # import_progress 轮询间隔（秒）
POLL_DEADLINE = 60.0  # 轮询总时限（秒）
MCP_TIMEOUT = 60.0  # 单次 MCP 调用超时
UPLOAD_TIMEOUT = 120.0  # COS PUT 上传超时
MAX_MCP_RETRY = 2  # pre_import/async_import 失败重试次数
RETRY_INTERVAL = 5.0


# ═══════════════════════════════════
# 内部工具
# ═══════════════════════════════════


def _md5(path: pathlib.Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_pack(html_path: str, title: str = "") -> dict[str, Any]:
    """调用 aipage_pack.js 把 HTML 打包为 .aipage，返回 {path,size,md5,title}."""
    html = pathlib.Path(html_path)
    if not html.is_file():
        raise FileNotFoundError(f"HTML 文件不存在: {html_path}")
    if not PACK_SCRIPT.is_file():
        raise FileNotFoundError(f"打包脚本缺失: {PACK_SCRIPT}")

    cmd = ["node", str(PACK_SCRIPT), "--html", str(html)]
    if title:
        cmd += ["--title", title]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"aipage_pack.js 打包失败: {proc.stderr.strip()[:500]}")

    # 解析脚本输出（KEY=VALUE 行）
    out: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    aipage_path = out.get("AIPAGE_PATH") or out.get("PATH")
    if not aipage_path:
        raise RuntimeError(f"aipage_pack.js 未输出打包路径: {proc.stdout.strip()[:300]}")
    p = pathlib.Path(aipage_path)
    if not p.is_file():
        raise RuntimeError(f"打包产物不存在: {p}")
    return {
        "path": str(p),
        "size": p.stat().st_size,
        "md5": _md5(p),
        "title": out.get("AIPAGE_TITLE", "") or title or html.stem,
    }


def _get_token() -> str:
    token = os.environ.get(TENCENT_TOKEN_ENV, "").strip()
    if not token:
        raise RuntimeError(f"缺少腾讯文档鉴权 token（环境变量 {TENCENT_TOKEN_ENV} 未设置）")
    return token


async def _lenient_validate(session: Any, name: str, result: Any) -> None:
    """腾讯文档 MCP 输出 schema 与真实返回常不一致：校验降级为告警放行."""
    try:
        _orig = session.__class__._validate_tool_result
        return await _orig(session, name, result)
    except Exception as e:  # noqa: BLE001
        logger.warning("[tdocs_import] %s 输出校验降级放行: %s", name, str(e)[:140])


def _mcp_session(token: str):
    """开一个带鉴权头的 Streamable HTTP MCP 会话上下文管理器."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    return _SessionCtx(token, ClientSession, streamablehttp_client)


class _SessionCtx:
    def __init__(self, token, ClientSession, client_factory):
        self._token = token
        self._ClientSession = ClientSession
        self._factory = client_factory

    async def __aenter__(self):
        headers = {"Authorization": self._token}
        cm = self._factory(TENCENT_MCP_URL, headers=headers)
        entered = await cm.__aenter__()
        if isinstance(entered, tuple) and len(entered) == 3:
            read, write, _get = entered
        else:
            read, write = entered
        self._cm = cm
        session = self._ClientSession(read, write)
        await session.__aenter__()
        session._validate_tool_result = lambda name, result: _lenient_validate(session, name, result)
        await asyncio.wait_for(session.initialize(), timeout=MCP_TIMEOUT)
        return session

    async def __aexit__(self, *exc):
        try:
            await self._cm.__aexit__(*exc)
        except Exception:  # noqa: BLE001
            pass


async def _call_tool(session: Any, name: str, arguments: dict[str, Any]) -> Any:
    """调用 MCP 工具并把 content 里第一段 text 解析成 JSON（失败回退原始文本）."""
    result = await asyncio.wait_for(session.call_tool(name, arguments=arguments), timeout=MCP_TIMEOUT)
    for item in result.content or []:
        if getattr(item, "type", "") == "text":
            try:
                return json.loads(item.text)
            except (json.JSONDecodeError, TypeError):
                return {"_raw": item.text}
    return {"_raw": json.dumps(result.model_dump(), default=str, ensure_ascii=False)}


async def _run_pipeline(html_path: str, title: str = "") -> dict[str, Any]:
    """完整上云管线（async 实现），成功返回 {ok,file_id,file_url,...}."""
    token = _get_token()
    packed = _run_pack(html_path, title)

    async with _mcp_session(token) as session:
        # ① pre_import
        pre = None
        last_err: Exception | None = None
        for attempt in range(MAX_MCP_RETRY + 1):
            try:
                pre = await _call_tool(
                    session,
                    "manage.pre_import",
                    {
                        "file_name": pathlib.Path(packed["path"]).name,
                        "file_size": packed["size"],
                        "file_md5": packed["md5"],
                    },
                )
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < MAX_MCP_RETRY:
                    await asyncio.sleep(RETRY_INTERVAL)
        if pre is None:
            raise RuntimeError(f"manage.pre_import 失败（重试 {MAX_MCP_RETRY} 次）: {last_err}")

        upload_url = pre.get("upload_url") if isinstance(pre, dict) else None
        file_key = pre.get("file_key") if isinstance(pre, dict) else None
        task_id = pre.get("task_id") if isinstance(pre, dict) else None
        if not upload_url or not file_key:
            raise RuntimeError(f"manage.pre_import 返回缺字段（upload_url/file_key）: {str(pre)[:400]}")

        # ② PUT 直传 COS
        async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as http:
            with open(packed["path"], "rb") as f:
                up = await http.put(
                    upload_url,
                    content=f.read(),
                    headers={"Content-Type": "application/octet-stream"},
                )
            if up.status_code not in (200, 204):
                raise RuntimeError(f"COS PUT 上传失败: HTTP {up.status_code} {up.text[:200]}")

        # ③ async_import（失败重试）
        imported = None
        for attempt in range(MAX_MCP_RETRY + 1):
            try:
                imported = await _call_tool(
                    session,
                    "manage.async_import",
                    {
                        "task_id": task_id,
                        "file_key": file_key,
                        "file_name": pathlib.Path(packed["path"]).name,
                        "file_md5": packed["md5"],
                        "file_size": packed["size"],
                    },
                )
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < MAX_MCP_RETRY:
                    await asyncio.sleep(RETRY_INTERVAL)
        if imported is None:
            raise RuntimeError(f"manage.async_import 失败（重试 {MAX_MCP_RETRY} 次）: {last_err}")

        # ④ 轮询 import_progress（≤60s）；async_import 已直接给 file_id/file_url 时短路
        if isinstance(imported, dict) and not imported.get("task_id"):
            imported.setdefault("task_id", task_id)
        poll_task_id = (imported or {}).get("task_id") or task_id
        file_id = (imported or {}).get("file_id") or ""
        file_url = (imported or {}).get("file_url") or ""
        progress = (imported or {}).get("progress", -1)
        if not (file_id or file_url):
            deadline = asyncio.get_event_loop().time() + POLL_DEADLINE
            while asyncio.get_event_loop().time() < deadline:
                try:
                    prog = await _call_tool(session, "manage.import_progress", {"task_id": poll_task_id})
                except Exception as e:  # noqa: BLE001 — 任务注册延迟会瞬时报错(如11607 docID)，容忍继续轮询
                    logger.warning("[tdocs_import] import_progress 瞬时错误（继续轮询）: %s", str(e)[:120])
                    prog = None
                if isinstance(prog, dict):
                    progress = prog.get("progress", -1)
                    file_id = prog.get("file_id") or file_id
                    file_url = prog.get("file_url") or file_url
                    if progress == 100 or (file_id and file_url):
                        break
                await asyncio.sleep(POLL_INTERVAL)

        if not (file_id or file_url):
            raise RuntimeError(f"导入超时未产出文档（进度 {progress}）: {str(imported)[:400]}")

        return {
            "ok": True,
            "file_id": file_id,
            "file_url": file_url,
            "task_id": poll_task_id,
            "progress": progress,
            "aipage": packed["path"],
            "md5": packed["md5"],
            "size": packed["size"],
        }


# ═══════════════════════════════════
# 对外入口
# ═══════════════════════════════════


def tdocs_upload_html(html_path: str, title: str = "") -> dict[str, Any]:
    """把本地 HTML 数据报告打包上传为腾讯文档，返回 {ok,file_id,file_url,...}.

    失败抛异常（带可读信息）；本函数为同步入口，内部驱动 asyncio 管线。
    """
    try:
        return asyncio.run(_run_pipeline(html_path, title))
    except RuntimeError as e:
        if "asyncio.run() cannot be called" in str(e):
            # 已在事件循环内（如被 MCP 工具在线程池调用时罕见）：走线程池降级
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, _run_pipeline(html_path, title)).result()
        raise


def tdocs_upload_html_bytes(html_bytes: bytes, title: str = "") -> dict[str, Any]:
    """字节版入口：把 HTML 内容落临时文件后走同一条管线."""
    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
    try:
        tmp.write(html_bytes)
        tmp.flush()
        tmp.close()
        return tdocs_upload_html(tmp.name, title)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:  # pragma: no cover
            pass


__all__ = ["tdocs_upload_html", "tdocs_upload_html_bytes"]
