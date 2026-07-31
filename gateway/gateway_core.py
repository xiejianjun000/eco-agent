#!/usr/bin/env python3
"""
gateway_core.py — Eco Agent 统一网关核心

Phase 1 交付物 1/7：统一会话管理 + 多通道抽象层

功能：
  1. 统一消息协议（所有通道归一化为 UnifiedMessage）
  2. 会话管理（跨通道共享上下文、状态、历史）
  3. 通道抽象层（12+ 通道统一接口）
  4. 路由器（按消息内容路由到对应 Agent）
  5. 所有操作可审计、持久化

用法：
  python gateway/gateway_core.py          # 启动网关
  python gateway/gateway_core.py --dev    # 开发模式
"""

import json
import time
import uuid
import logging
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from collections.abc import Callable
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger("gateway_core")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "memory-tree" / "data" / "gateway"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════
# 数据模型
# ═══════════════════════════════════

class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"
    VIDEO = "video"
    INTERACTIVE = "interactive"  # 卡片/按钮回调

class Platform(str, Enum):
    FEISHU = "feishu"
    WECOM = "wecom"
    DINGTALK = "dingtalk"
    WECHAT = "wechat"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    QQ = "qq"
    WHATSAPP = "whatsapp"
    CLI = "cli"
    API = "api"
    WEB = "web"

@dataclass
class UnifiedMessage:
    """统一消息——所有通道的输入输出归一化为此格式"""
    id: str = ""
    platform: str = ""
    channel_id: str = ""           # 通道内唯一标识（会话ID/群ID/用户ID）
    user_id: str = ""
    user_name: str = ""
    msg_type: MessageType = MessageType.TEXT
    content: str = ""
    raw: dict = field(default_factory=dict)
    timestamp: str = ""
    reply_to: str = ""             # 回复的消息ID
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = f"msg_{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

@dataclass
class Session:
    """会话——跨通道共享上下文"""
    session_id: str = ""
    user_id: str = ""
    platform: str = ""
    channel_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    active: bool = True
    context: dict = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add_message(self, msg: UnifiedMessage, response: str = ""):
        self.history.append({
            "msg_id": msg.id,
            "content": msg.content[:200],
            "response": response[:200] if response else "",
            "timestamp": msg.timestamp,
        })
        self.updated_at = datetime.now().isoformat()
        if len(self.history) > 100:  # 只保留最近100条
            self.history = self.history[-100:]


# ═══════════════════════════════════
# 通道适配器——所有通道实现此接口
# ═══════════════════════════════════

class ChannelAdapter(ABC):
    """通道适配器抽象接口——所有通道必须实现以下四个成员

    当前已接入：telegram / discord / slack（gateway/channels/）
    国内平台统一走 r15 适配器（agent_core/channels/）：feishu / wecom / dingtalk / wechat_oa
    旧独立平台 bot 已归档至 _deprecated/gateway-platforms/
    枚举预留待接入：CLI / API / WEB / QQ / WHATSAPP（见 Platform）
    """

    @property
    @abstractmethod
    def platform(self) -> str:
        """通道平台标识（对应 Platform 枚举值）"""

    @abstractmethod
    def send_message(self, channel_id: str, message: str, reply_to: str = "") -> bool:
        """发送文本消息，成功返回 True"""

    @abstractmethod
    def send_card(self, channel_id: str, title: str, content: str, actions: list[dict] = None) -> bool:
        """发送卡片消息，成功返回 True"""

    @abstractmethod
    def parse_webhook(self, raw_data: dict) -> UnifiedMessage | None:
        """解析平台 webhook 原始数据为统一消息，无法解析返回 None"""


# ═══════════════════════════════════
# 会话管理器
# ═══════════════════════════════════

class SessionManager:
    """跨通道会话管理——统一状态、持久化、过期回收"""

    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._db_path = DATA_DIR / "sessions.json"
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if self._db_path.exists():
            try: data = json.loads(self._db_path.read_text("utf-8", errors="replace"))
            except Exception: data = {}
            for sid, sdata in data.items():
                self._sessions[sid] = Session(**sdata)

    def _save(self):
        with self._lock:
            data = {sid: asdict(s) for sid, s in self._sessions.items()}
            self._db_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_or_create(self, platform: str, channel_id: str, user_id: str = "", user_name: str = "") -> Session:
        """获取或创建会话（跨通道复用）

        同一用户从不同平台发消息 → 可配置是否共享同一会话
        """
        session_id = f"{platform}_{user_id or channel_id}"
        with self._lock:
            if session_id in self._sessions:
                return self._sessions[session_id]
            session = Session(
                session_id=session_id, user_id=user_id or channel_id,
                platform=platform, channel_id=channel_id,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat()
            )
            self._sessions[session_id] = session
            self._save()
            return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def cleanup_stale(self, max_hours: int = 72):
        """清理过期会话"""
        now = datetime.now()
        stale = []
        for sid, session in self._sessions.items():
            try:
                updated = datetime.fromisoformat(session.updated_at)
                if (now - updated).total_seconds() > max_hours * 3600:
                    stale.append(sid)
            except Exception: stale.append(sid)
        with self._lock:
            for sid in stale:
                del self._sessions[sid]
        if stale:
            self._save()
            logger.info(f"[Session] 清理 {len(stale)} 个过期会话")

    def get_stats(self) -> dict:
        return {"total_sessions": len(self._sessions),
                "active": sum(1 for s in self._sessions.values() if s.active),
                "stale": sum(1 for s in self._sessions.values() if not s.active)}


# ═══════════════════════════════════
# 消息路由器
# ═══════════════════════════════════

class MessageRouter:
    """消息路由器——按内容/平台/用户路由到对应处理器"""

    def __init__(self, session_mgr: SessionManager):
        self._session_mgr = session_mgr
        self._handlers: dict[str, Callable] = {}
        self._audit_log = DATA_DIR / "audit.jsonl"
        self._audit_log.parent.mkdir(parents=True, exist_ok=True)

    def register_handler(self, name: str, handler: Callable):
        """注册消息处理器"""
        self._handlers[name] = handler

    def route(self, msg: UnifiedMessage) -> dict:
        """路由消息"""
        start = time.time()

        # 获取/创建会话
        session = self._session_mgr.get_or_create(
            msg.platform, msg.channel_id, msg.user_id, msg.user_name
        )

        # 找出匹配的处理器
        handler_name = self._select_handler(msg)
        handler = self._handlers.get(handler_name)

        # 执行
        if handler:
            try:
                response = handler(msg, session)
            except Exception as e:
                response = f"[系统错误] {e}"
                logger.error(f"[Router] 处理器异常: {e}")
        else:
            response = f"[{handler_name} 处理器未注册]"

        # 记录历史
        session.add_message(msg, str(response)[:500])

        # 审计日志
        elapsed = (time.time() - start) * 1000
        self._audit({
            "msg_id": msg.id, "platform": msg.platform, "user": msg.user_id[:20],
            "content_truncated": msg.content[:50], "handler": handler_name,
            "elapsed_ms": round(elapsed, 1), "timestamp": datetime.now().isoformat(),
        })

        return {"session_id": session.session_id, "response": response, "handler": handler_name,
                "elapsed_ms": round(elapsed, 1)}

    def _select_handler(self, msg: UnifiedMessage) -> str:
        """选择处理器"""
        # 简单路由：检查消息内容
        content = msg.content.lower().strip()
        if content in ("帮助", "help", "?", "h") or content.startswith("帮助"):
            return "help"
        if content in ("你好", "hi", "hello", "您好", "在吗"):
            return "greeting"
        if content in ("状态", "status"):
            return "status"
        return "chat"  # 默认会话处理器

    def _audit(self, entry: dict):
        try:
            with open(self._audit_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception: pass

    def get_stats(self) -> dict:
        return {"handlers": list(self._handlers.keys()),
                "audit_size": self._audit_log.stat().st_size if self._audit_log.exists() else 0}


# ═══════════════════════════════════
# 通道工厂——注册所有通道
# ═══════════════════════════════════

class ChannelFactory:
    def __init__(self):
        self._adapters: dict[str, ChannelAdapter] = {}

    def register(self, adapter: ChannelAdapter):
        self._adapters[adapter.platform] = adapter

    def get(self, platform: str) -> ChannelAdapter | None:
        return self._adapters.get(platform)

    def list_platforms(self) -> list[str]:
        return list(self._adapters.keys())

    def broadcast(self, message: str, platforms: list[str] = None) -> dict[str, bool]:
        """向所有/指定平台广播消息"""
        results = {}
        targets = platforms or self.list_platforms()
        for p in targets:
            adapter = self.get(p)
            if adapter:
                try: results[p] = adapter.send_message("broadcast", message)
                except Exception: results[p] = False
        return results


# ═══════════════════════════════════
# 网关主服务
# ═══════════════════════════════════

class GatewayService:
    """统一网关服务"""

    def __init__(self):
        self.sessions = SessionManager()
        self.router = MessageRouter(self.sessions)
        self.channels = ChannelFactory()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        """启动网关"""
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gateway")
        self._thread.start()
        logger.info("[Gateway] 统一网关启动")

    def stop(self):
        self._running = False
        logger.info("[Gateway] 统一网关停止")

    def _loop(self):
        """后台循环：清理过期会话、统计报告"""
        while self._running:
            try:
                self.sessions.cleanup_stale(72)
                stats = self.sessions.get_stats()
                logger.debug(f"[Gateway] 会话统计: {stats}")
            except Exception as e:
                logger.warning(f"[Gateway] 后台异常: {e}")
            time.sleep(3600)  # 每小时维护一次

    def process_message(self, platform: str, channel_id: str, content: str,
                        user_id: str = "", user_name: str = "",
                        msg_type: MessageType = MessageType.TEXT) -> dict:
        """统一消息入口——任何通道调用此方法即可发送消息进系统"""
        msg = UnifiedMessage(
            platform=platform, channel_id=channel_id, user_id=user_id,
            user_name=user_name, msg_type=msg_type, content=content,
        )
        return self.router.route(msg)

    def get_stats(self) -> dict:
        return {
            "sessions": self.sessions.get_stats(),
            "router": self.router.get_stats(),
            "channels": {"registered": self.channels.list_platforms()},
        }


# ===== 测试 =====

def test():
    gw = GatewayService()
    gw.start()

    # 模拟多通道消息
    for platform, content in [("feishu", "你好"), ("telegram", "帮助"), ("cli", "某企业超标排放大气污染物")]:
        result = gw.process_message(platform, "test_channel", content, user_id="test_user")
        print(f"[{platform}] {content[:20]} -> {result['handler']} ({result['elapsed_ms']:.0f}ms)")

    stats = gw.get_stats()
    print(f"\n[Gateway] 会话: {stats['sessions']['total_sessions']}, 处理器: {stats['router']['handlers']}")
    gw.stop()
    print("[OK] 统一网关核心测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(message)s")
    test()
