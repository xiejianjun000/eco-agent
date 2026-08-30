#!/usr/bin/env python3
"""
approval.py — L4 审批栈（对标 DSH approval service：ask/never + answerer 瀑布 + asked/decided 审计对）

场景：非交互模式下 L4（外部服务写）工具无授权令牌时，不再单纯 deny，
而是向审批栈登记一条 pending 请求，等待授权 answerer 通过 API/CLI 决定。

设计：
  policy     : "ask"（默认）登记 pending 请求等待决定；"never" 直接 fail-closed 拒绝，
               不产生任何 pending 请求（与旧版 deny 语义一致）。
  answerers  : 授权 answerer 链（list[str]，瀑布式）。decide() 携带的 answerer
               必须命中链内成员；链为空（无 answerer）或 answerer 不在链内 → fail-closed 拒绝。
  queue      : 待决请求持久化到 ECO_DIR/approvals.jsonl（ECO_DIR 默认 ~/.eco），
               目录/文件不可写时自动降级为进程内存态（不丢本轮数据，仅不跨进程）。
  audit pair : 每次 request 写一条 asked（请求元数据），每次 decide 写一条 decided
               （决定 + 理由），均写入现有 SM3 审计链 source=approval，task_id=请求 id 成对。

配置（进程环境变量）：
  ECO_APPROVAL_POLICY     ask | never            （默认 ask）
  ECO_APPROVAL_ANSWERERS  逗号分隔 answerer 名单  （默认空 → fail-closed）
  ECO_DIR                 数据目录                （默认 ~/.eco）

安全边界：本模块不提供“跳过闸门”的裸开关；answerer 链空时绝不放行。
"""
from __future__ import annotations

import json
import logging
import os
import secrets as _secrets
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("approval")

ECO_DIR = Path(os.environ.get("ECO_DIR", str(Path.home() / ".eco")))
APPROVALS_FILE = ECO_DIR / "approvals.jsonl"

_POLICIES = ("ask", "never")
_STATUS_NOT_FOUND = "not_found"


def _default_policy() -> str:
    p = os.environ.get("ECO_APPROVAL_POLICY", "ask").strip().lower()
    return p if p in _POLICIES else "ask"


def _default_answerers() -> list[str]:
    raw = os.environ.get("ECO_APPROVAL_ANSWERERS", "").strip()
    if not raw:
        return []
    return [a.strip() for a in raw.split(",") if a.strip()]


def _new_id() -> str:
    # 128 位随机（token_hex(16)）：审批令牌不可枚举，防 request_id 猜测越权
    return f"appr-{datetime.now():%Y%m%d%H%M%S}-{_secrets.token_hex(16)}"


class ApprovalService:
    """L4 审批栈：pending 队列 + ask/never 策略 + answerer 瀑布授权 + SM3 审计对。"""

    def __init__(self, policy: str | None = None,
                 answerers: list[str] | None = None,
                 path: Path | str | None = None):
        policy = policy if policy is not None else _default_policy()
        self.policy = policy if policy in _POLICIES else "ask"
        self.answerers = list(answerers) if answerers is not None else _default_answerers()
        self.path = Path(path) if path is not None else APPROVALS_FILE
        self._lock = threading.Lock()
        self._records: dict[str, dict] = {}
        self._writable = self._probe_writable()
        self._load()

    # ── 持久化 ─────────────────────────────────────────────
    def _probe_writable(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8"):
                pass
            return True
        except OSError as e:  # noqa: BLE001 — 不可写降级内存态
            logger.warning(f"[approval] 审批队列不可写，降级内存态: {e}")
            return False

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and rec.get("id"):
                self._records[rec["id"]] = rec

    def _persist(self) -> None:
        if not self._writable:
            return
        try:
            lines = [json.dumps(r, ensure_ascii=False)
                     for r in self._records.values()]
            self.path.write_text("\n".join(lines) + ("\n" if lines else ""),
                                 encoding="utf-8")
        except OSError as e:  # noqa: BLE001 — 写失败降级内存态
            self._writable = False
            logger.warning(f"[approval] 审批队列写入失败，降级内存态: {e}")

    # ── SM3 审计对（asked / decided，source=approval）───────
    def _audit(self, kind: str, rec: dict) -> None:
        try:
            from agent_core.prompt_engine import get_prompt_engine
            eng = get_prompt_engine()
            if kind == "asked":
                eng.audit.append(
                    source="approval",
                    content=f"asked approval:{rec['id']} scope={rec.get('scope')} "
                            f"detail={json.dumps(rec.get('detail'), ensure_ascii=False)}",
                    task_id=rec["id"], phase="approval", accepted=False,
                    reason="待 answerer 决定")
            else:  # decided
                eng.audit.append(
                    source="approval",
                    content=f"decided approval:{rec['id']} -> {rec.get('status')} "
                            f"answerer={rec.get('answerer') or '-'} "
                            f"reason={rec.get('reason') or '-'}",
                    task_id=rec["id"], phase="approval",
                    accepted=(rec.get("status") == "allowed"),
                    reason=rec.get("reason") or "")
        except Exception as e:  # noqa: BLE001 — 审计失败不阻断业务
            logger.warning(f"[approval] 审计写入失败: {e}")

    # ── API ────────────────────────────────────────────────
    def request(self, scope: str, detail=None) -> dict:
        """登记一条审批请求。policy=never 时不产生 pending，直接返回 denied。"""
        if self.policy == "never":
            return {"id": None, "status": "denied", "allow": False}
        try:
            json.dumps(detail, ensure_ascii=False)
            safe_detail = detail
        except (TypeError, ValueError):
            safe_detail = str(detail)
        rec = {
            "id": _new_id(),
            "status": "pending",
            "scope": scope,
            "detail": safe_detail,
            "created_ts": datetime.now().isoformat(timespec="seconds"),
            "answerer": "",
            "reason": "",
            "decided_ts": "",
        }
        with self._lock:
            self._records[rec["id"]] = rec
            self._persist()
            self._audit("asked", rec)
        return {"id": rec["id"], "status": rec["status"]}

    def decide(self, request_id: str, allow: bool,
               answerer: str = "", reason: str = "") -> dict:
        """决定一条 pending 请求。answerer 必须命中链内成员（瀑布式）；
        链为空或 answerer 不在链内 → fail-closed 拒绝（即使 allow=True）。"""
        with self._lock:
            rec = self._records.get(request_id)
            if rec is None:
                return {"id": request_id, "status": _STATUS_NOT_FOUND,
                        "allow": False, "reason": "请求不存在"}
            if rec["status"] != "pending":
                return {"id": request_id, "status": rec["status"],
                        "allow": False, "reason": "请求已决定"}

            answerer = (answerer or "").strip()
            chain = list(self.answerers)
            if answerer in chain:
                authorized = True
            else:
                # fail-closed：链为空或 answerer 未授权；拒绝理由由服务侧裁定，
                # 不采信未授权 answerer 自述的 reason
                authorized = False
                if not chain:
                    reason = "answerer 链为空（fail-closed）"
                elif not answerer:
                    reason = "未提供 answerer（fail-closed）"
                else:
                    reason = f"answerer {answerer} 不在授权链 {chain}（fail-closed）"

            if not authorized:
                rec["status"] = "denied"
                rec["answerer"] = answerer
                rec["reason"] = reason
            else:
                rec["status"] = "allowed" if allow else "denied"
                rec["answerer"] = answerer
                rec["reason"] = reason or ("人工审批放行" if allow else "人工审批拒绝")
            rec["decided_ts"] = datetime.now().isoformat(timespec="seconds")
            self._persist()
            self._audit("decided", rec)

            return {"id": request_id, "status": rec["status"],
                    "allow": rec["status"] == "allowed",
                    "answerer": rec["answerer"], "reason": rec["reason"]}

    def list_pending(self) -> list[dict]:
        """返回全部仍处于 pending 的请求（新建副本，不暴露内部引用）。"""
        with self._lock:
            return [dict(r) for r in self._records.values()
                    if r.get("status") == "pending"]


_service: ApprovalService | None = None


def get_approval_service() -> ApprovalService:
    """进程级单例（对标 get_prompt_engine）。策略/answerer 在首次创建时读环境变量。"""
    global _service
    if _service is None:
        _service = ApprovalService()
    return _service


def _reset_approval_service_for_test() -> None:
    global _service
    _service = None
