#!/usr/bin/env python3
"""
wechat_personal.py — Eco Agent 微信个人号通道

基于 itchat-uos 协议实现，无需企业认证即可接入微信个人号。
对标 Hermes 的 WeChat 插件，补齐国内 IM 闭环的最后一块拼图。

依赖：pip install itchat-uos
注意：itchat 协议非官方，存在封号风险，建议使用小号测试。

用法：
  # 启动时会弹出二维码，手机微信扫码登录
  # 守护进程模式下自动启动
"""

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("wechat_personal")

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "memory-tree" / "data" / "wechat"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class WeChatPersonal:
    """微信个人号通道适配器"""

    def __init__(self, message_callback: Callable = None):
        self._bot = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._message_callback = message_callback
        self._login_status = "disconnected"
        self._qrcode_path = str(DATA_DIR / "wechat_qr.png")
        self._allowed_users: list[str] = []  # 白名单用户备注名
        self._message_history: list[dict] = []
        self._load_config()

    def _load_config(self):
        """加载微信通道配置"""
        config_path = DATA_DIR / "wechat_config.json"
        if config_path.exists():
            import json

            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                self._allowed_users = config.get("allowed_users", [])
                if config.get("auto_reply_prefix"):
                    self.auto_reply_prefix = config["auto_reply_prefix"]
            except Exception:
                pass

    def set_message_callback(self, callback: Callable):
        """设置消息回调：收到微信消息 → 回调（返回回复文本）"""
        self._message_callback = callback

    def start(self):
        """启动微信通道（阻塞式二维码登录）"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="wechat_personal")
        self._thread.start()

    def stop(self):
        """停止微信通道"""
        self._running = False
        if self._bot:
            try:
                self._bot.logout()
            except Exception:
                pass
        self._login_status = "disconnected"
        logger.info("[WeChat] 已停止")

    def _run_loop(self):
        """微信运行主循环"""
        try:
            import itchat
        except ImportError:
            logger.error("[WeChat] itchat-uos 未安装。运行: pip install itchat-uos")
            self._login_status = "error: itchat-uos not installed"
            return

        try:
            # 开启热重载（登录态持久化）
            itchat.auto_login(
                hotReload=True,
                enableCmdQR=2,  # 控制台紧凑二维码
                picDir=self._qrcode_path,
                statusStorageDir=str(DATA_DIR / "itchat.pkl"),
            )
            self._bot = itchat
            self._login_status = "connected"
            logger.info("[WeChat] 微信登录成功")

            # 注册消息处理器
            @itchat.msg_register(itchat.content.TEXT)
            def _text_reply(msg):
                return self._handle_message(msg)

            @itchat.msg_register([itchat.content.TEXT])
            def _group_reply(msg):
                # 群聊消息暂不处理，仅记录
                logger.debug(f"[WeChat] 群消息: {msg.get('ActualNickName', '')}: {msg.get('Text', '')[:50]}")
                return None

            # 运行消息循环
            logger.info("[WeChat] 消息监听已启动")
            itchat.run()

        except Exception as e:
            logger.error(f"[WeChat] 运行错误: {e}")
            self._login_status = f"error: {e}"
            self._running = False

    def _handle_message(self, msg: dict) -> str | None:
        """处理单条微信消息"""
        from_user = msg.get("FromUserName", "")
        text = msg.get("Text", "").strip()
        create_time = msg.get("CreateTime", int(time.time()))

        # 获取发送者信息
        try:
            user_info = self._bot.search_friends(userName=from_user)
            if user_info:
                remark = user_info.get("RemarkName", "") or user_info.get("NickName", "")
            else:
                remark = from_user
        except Exception:
            remark = from_user

        # 白名单检查
        if self._allowed_users and remark not in self._allowed_users:
            logger.debug(f"[WeChat] 非白名单用户: {remark}")
            return None

        # 记录消息
        self._message_history.append(
            {
                "from": remark,
                "text": text,
                "time": datetime.fromtimestamp(create_time).isoformat(),
            }
        )
        if len(self._message_history) > 500:
            self._message_history = self._message_history[-500:]

        # 特殊指令
        if text.lower() in ("/status", "/状态"):
            return self._get_status()

        # 有回调则走 Agent 引擎
        if self._message_callback:
            try:
                unified_msg = {
                    "channel": "wechat_personal",
                    "from_user": remark,
                    "from_user_id": from_user,
                    "text": text,
                    "timestamp": create_time,
                }
                reply = self._message_callback(unified_msg)
                return reply
            except Exception as e:
                logger.warning(f"[WeChat] 消息回调失败: {e}")
                return f"处理出错: {e}"

        return None

    def send_message(self, to_user: str = None, to_user_id: str = None, text: str = "") -> bool:
        """主动发送微信消息"""
        if not self._bot or self._login_status != "connected":
            logger.warning("[WeChat] 未登录，无法发送消息")
            return False
        try:
            if to_user_id:
                self._bot.send(text, toUserName=to_user_id)
            elif to_user:
                friends = self._bot.search_friends(name=to_user)
                if friends:
                    self._bot.send(text, toUserName=friends[0]["UserName"])
                else:
                    logger.warning(f"[WeChat] 未找到用户: {to_user}")
                    return False
            else:
                # 发送给自己（文件传输助手）
                self._bot.send(text, toUserName="filehelper")
            return True
        except Exception as e:
            logger.warning(f"[WeChat] 发送消息失败: {e}")
            return False

    def _get_status(self) -> str:
        """获取通道状态"""
        return (
            f"[Eco Agent 微信通道]\n"
            f"状态: {self._login_status}\n"
            f"消息数: {len(self._message_history)}\n"
            f"白名单: {', '.join(self._allowed_users) if self._allowed_users else '无限制'}\n"
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

    def get_health(self) -> dict:
        """健康检查"""
        return {
            "ok": self._login_status == "connected",
            "status": self._login_status,
            "message_count": len(self._message_history),
        }


# ===== 全局单例 =====
wechat_bot = WeChatPersonal()


# ===== 测试 =====
def test():
    import io
    import sys as _sys

    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("[WeChat] 微信个人号通道模块加载正常")
    print(f"[WeChat] 数据目录: {DATA_DIR}")
    print(f"[WeChat] 状态: {wechat_bot._login_status}")
    print("[OK] WeChat 个人号通道模块测试通过 (注: 未启动实际连接)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
