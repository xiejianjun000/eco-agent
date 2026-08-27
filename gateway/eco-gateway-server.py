#!/usr/bin/env python3
"""
eco-gateway-server.py — eco Agent 统一网关服务

支持平台：飞书 · 企业微信 · 钉钉 · 微信
协议：FastAPI + HTTP Webhook
集成方式：Hermes Gateway 适配器 + 独立 Webhook

用法：
  # 启动全部平台
  python gateway/eco-gateway-server.py

  # 启动指定平台
  python gateway/eco-gateway-server.py --platforms feishu,wecom

  # 开发模式（热重载）
  python gateway/eco-gateway-server.py --reload

环境变量：
  FEISHU_* / WECOM_* / DINGTALK_* / WECHAT_*
  各平台的凭证信息
"""

import os
import sys
import json
import hmac
import hashlib
import base64
import logging
import argparse
from datetime import datetime

# ===== 条件导入 FastAPI =====
try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse, Response
    import uvicorn
except ImportError:
    print("[ERROR] 缺少依赖：pip install fastapi uvicorn")
    sys.exit(1)

# ===== 日志配置 =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("eco-gateway")

# ===== 配置 =====
CONFIG = {
    "feishu": {
        "port": int(os.environ.get("FEISHU_PORT", "7070")),
        "path": "/webhook/feishu",
        "app_id": os.environ.get("FEISHU_APP_ID", ""),
        "app_secret": os.environ.get("FEISHU_APP_SECRET", ""),
        "verification_token": os.environ.get("FEISHU_VERIFICATION_TOKEN", ""),
    },
    "wecom": {
        "port": int(os.environ.get("WECOM_PORT", "7071")),
        "path": "/webhook/wecom",
        "corp_id": os.environ.get("WECOM_CORP_ID", ""),
        "agent_id": os.environ.get("WECOM_AGENT_ID", ""),
        "secret": os.environ.get("WECOM_SECRET", ""),
        "token": os.environ.get("WECOM_TOKEN", ""),
        "encoding_aes_key": os.environ.get("WECOM_ENCODING_AES_KEY", ""),
    },
    "dingtalk": {
        "port": int(os.environ.get("DINGTALK_PORT", "7072")),
        "path": "/webhook/dingtalk",
        "app_key": os.environ.get("DINGTALK_APP_KEY", ""),
        "app_secret": os.environ.get("DINGTALK_APP_SECRET", ""),
        "robot_code": os.environ.get("DINGTALK_ROBOT_CODE", ""),
    },
    "wechat": {
        "port": int(os.environ.get("WECHAT_PORT", "7073")),
        "path": "/webhook/wechat",
        "app_id": os.environ.get("WECHAT_APP_ID", ""),
        "app_secret": os.environ.get("WECHAT_APP_SECRET", ""),
        "token": os.environ.get("WECHAT_TOKEN", ""),
        "encoding_aes_key": os.environ.get("WECHAT_ENCODING_AES_KEY", ""),
    },
}

# ===== eco Agent 消息处理核心 =====

class ECOAgentHandler:
    """eco Agent 消息处理核心"""

    def __init__(self):
        self.message_count = 0
        self.start_time = datetime.now()

    async def handle_message(self, platform: str, data: dict) -> dict:
        """处理收到的消息"""
        self.message_count += 1
        logger.info(f"[{platform}] 收到消息: {data.get('message', {}).get('content', '')[:50]}")

        # 统一消息格式
        unified = self._normalize_message(platform, data)

        # 提取用户消息
        user_msg = unified.get("message", {}).get("content", "").strip()

        if not user_msg:
            return self._reply_text("请发送消息内容。")

        # 命令路由
        cmd, args = self._parse_command(user_msg)

        if cmd == "help":
            return self._reply_text(self._get_help_text(platform))
        elif cmd == "start":
            return self._reply_text(self._get_welcome_text(platform))
        elif cmd == "status":
            return self._reply_text(self._get_status_text())
        else:
            # 普通消息转发给 eco Agent 处理
            return await self._route_to_eco_agent(platform, unified)

    def _normalize_message(self, platform: str, data: dict) -> dict:
        """将各平台消息统一为内部格式"""
        normalized = {
            "platform": platform,
            "event_type": "message",
            "event_id": str(self.message_count),
            "timestamp": datetime.now().isoformat(),
            "user": {"id": "", "name": ""},
            "conversation": {"id": "", "type": "p2p"},
            "message": {"type": "text", "content": ""},
        }

        try:
            if platform == "feishu":
                event = data.get("event", {})
                sender = event.get("sender", {})
                msg = event.get("message", {})
                normalized["user"]["id"] = sender.get("sender_id", {}).get("open_id", "")
                normalized["user"]["name"] = sender.get("sender_id", {}).get("name", "")
                normalized["conversation"]["id"] = msg.get("chat_id", "")
                normalized["conversation"]["type"] = msg.get("chat_type", "p2p")
                normalized["message"]["content"] = self._extract_feishu_content(msg)
                normalized["event_id"] = msg.get("message_id", "")

            elif platform == "wecom":
                content = data.get("Content", data.get("content", ""))
                from_user = data.get("FromUserName", data.get("from_user", ""))
                normalized["user"]["id"] = from_user
                normalized["user"]["name"] = from_user
                normalized["conversation"]["id"] = data.get("AgentID", "")
                normalized["message"]["content"] = content
                normalized["event_id"] = data.get("MsgId", str(self.message_count))

            elif platform == "dingtalk":
                text = data.get("text", {}).get("content", "")
                sender_id = data.get("senderId", data.get("sender_id", ""))
                sender_nick = data.get("senderNick", data.get("sender_nick", ""))
                conv_id = data.get("conversationId", data.get("conversation_id", ""))
                normalized["user"]["id"] = sender_id
                normalized["user"]["name"] = sender_nick
                normalized["conversation"]["id"] = conv_id
                normalized["message"]["content"] = text
                normalized["event_id"] = data.get("msgId", str(self.message_count))

            elif platform == "wechat":
                content = data.get("Content", "")
                from_user = data.get("FromUserName", "")
                normalized["user"]["id"] = from_user
                normalized["message"]["content"] = content
                normalized["event_id"] = data.get("MsgId", str(self.message_count))
        except Exception as e:
            logger.warning(f"[{platform}] 消息解析异常: {e}")

        return normalized

    def _extract_feishu_content(self, msg: dict) -> str:
        """从飞书消息中提取文本内容"""
        msg_type = msg.get("msg_type", "")
        content_str = msg.get("content", "{}")
        try:
            content = json.loads(content_str) if isinstance(content_str, str) else content_str
        except json.JSONDecodeError:
            return content_str

        if msg_type == "text":
            return content.get("text", "")
        return str(content)

    def _parse_command(self, msg: str) -> tuple:
        """解析命令"""
        msg = msg.strip().lower()
        commands = {
            "帮助": "help", "help": "help", "h": "help",
            "开始": "start", "start": "start",
            "状态": "status", "status": "status",
        }
        for key, cmd in commands.items():
            if msg == key or msg.startswith(key + " ") or msg == f"/{key}":
                args = msg[len(key):].strip() if msg != key else ""
                return cmd, args
        return "query", msg

    def _get_help_text(self, platform: str) -> str:
        return (
            "eco Agent 执法助手使用说明\n\n"
            "【法规检索】\n发送法规名称，如：大气污染防治法\n\n"
            "【执法问答】\n描述违法事实，如：某企业超标排放二氧化硫\n\n"
            "【案例查询】\n发送：案例 + 关键词\n\n"
            "【其他命令】\n帮助 / 开始 / 状态"
        )

    def _get_welcome_text(self, platform: str) -> str:
        return (
            "欢迎使用 eco Agent 执法助手！\n\n"
            "我是您的 AI 同事，精通全部生态环境法律法规。\n\n"
            "发送法规名称查询法律条文\n"
            "发送违法事实获取裁量建议\n"
            "发送「帮助」查看使用说明"
        )

    def _get_status_text(self) -> str:
        uptime = datetime.now() - self.start_time
        return (
            f"eco Agent 运行状态\n"
            f"在线时长：{uptime.days}天{uptime.seconds // 3600}小时\n"
            f"已处理消息：{self.message_count} 条\n"
            f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

    def _reply_text(self, text: str) -> dict:
        """生成文本回复"""
        return {"type": "text", "content": text}

    async def _route_to_eco_agent(self, platform: str, unified: dict) -> dict:
        """将消息路由到 eco Agent 核心处理

        当前版本：本地规则匹配
        后续版本：对接 Hermes Agent AIAgent
        """
        user_msg = unified["message"]["content"]

        # 尝试调用 MCP 知识库检索
        try:
            result = await self._mcp_search(user_msg)
            if result:
                return self._reply_text(result)
        except Exception as e:
            logger.warning(f"MCP 检索失败: {e}")

        # 降级：关键词匹配
        return self._reply_text(self._keyword_match(user_msg))

    async def _mcp_search(self, query: str) -> str | None:
        """通过 MCP 工具检索知识库"""
        try:
            # 直接调用 eco-knowledge-mcp 的搜索逻辑
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
            from _scripts.eco_knowledge_mcp import (
                find_vault_path, search_in_files, collect_wiki_files
            )
            vault = find_vault_path()
            if not vault.exists():
                return None
            wiki_files = collect_wiki_files(vault)
            results = search_in_files(wiki_files, query, max_results=3)
            if results:
                lines = [f"**{results[0]['title']}**"]
                for r in results:
                    snippet = r.get("snippet", "")[:150]
                    lines.append(f"- {r['path']}: {snippet}")
                return "\n".join(lines)
        except Exception as e:
            logger.error(f"MCP search error: {e}")
        return None

    def _keyword_match(self, msg: str) -> str:
        """关键词匹配降级方案"""
        msg_lower = msg.lower()

        if any(kw in msg_lower for kw in ["大气", "废气", "排放"]):
            return (
                "【大气污染防治相关】\n\n"
                "现行主要法规：\n"
                "- 《生态环境法典》第二编第二分编（大气污染防治）\n\n"
                "常见违法行为：\n"
                "- 超标排放大气污染物\n"
                "- 无组织排放\n"
                "- 未安装污染防治设施\n\n"
                "💡 发送具体违法事实获取详细裁量建议"
            )
        elif any(kw in msg_lower for kw in ["水", "废水", "污水"]):
            return (
                "【水污染防治相关】\n\n"
                "现行主要法规：\n"
                "- 《生态环境法典》第二编第三分编（水污染防治）\n\n"
                "常见违法行为：\n"
                "- 超标排放水污染物\n"
                "- 偷排废水\n"
                "- 违反排污许可\n\n"
                "💡 发送具体违法事实获取详细裁量建议"
            )
        elif any(kw in msg_lower for kw in ["固废", "固体废物", "危废", "垃圾"]):
            return (
                "【固体废物污染防治相关】\n\n"
                "现行主要法规：\n"
                "- 《生态环境法典》第二编第六分编（固体废物污染防治）\n"
                "- 《危险废物转移环境管理办法》\n\n"
                "💡 发送具体违法事实获取详细裁量建议"
            )
        elif any(kw in msg_lower for kw in ["噪声", "噪音"]):
            return (
                "【噪声污染防治相关】\n\n"
                "现行主要法规：\n"
                "- 《生态环境法典》第二编第七分编（噪声污染防治）\n"
                "- 《声环境质量标准》\n\n"
                "💡 发送具体违法事实获取详细裁量建议"
            )
        else:
            return (
                f"收到：{msg[:100]}\n\n"
                "我正为您检索相关法规...\n\n"
                "💡 您也可以：\n"
                "- 发送「帮助」查看使用说明\n"
                "- 发送「状态」查看系统状态\n"
                "- 发送更具体的违法事实获取精准裁量建议"
            )


# ===== FastAPI 应用 =====

app = FastAPI(title="eco Agent Gateway", version="0.1.0")
eco_handler = ECOAgentHandler()


@app.get("/")
async def root():
    return {
        "service": "eco Agent Gateway",
        "version": "0.1.0",
        "platforms": list(CONFIG.keys()),
        "uptime": str(datetime.now() - eco_handler.start_time),
    }


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/healthz")
async def healthz():
    """轻量健康检查（D4：供内网负载均衡/探活使用）。"""
    return {"status": "ok"}


# ===== 通用渠道入站（agent_core.channels 注册表：webhook/qqbot/wechat_oa 等） =====

@app.api_route("/channels/{name}", methods=["GET", "POST"])
async def channel_inbound(name: str, request: Request):
    """统一渠道回调入口（D4）。

    POST /channels/<name> → handle_inbound → {"reply": ...}
    GET  /channels/<name> → wecom/wechat_oa echostr / feishu challenge 握手
    分发逻辑与 stdlib 服务（agent_core.channels.http_server）共用，
    验签失败/注入拦截按 registry 语义回 200 固定话术。
    """
    from agent_core.channels.http_server import dispatch_request
    body = await request.body()
    status, content_type, payload = dispatch_request(
        request.method, name,
        headers=dict(request.headers.items()),
        args=dict(request.query_params), body=body)
    media_type = content_type.split(";")[0]
    return Response(content=payload, status_code=status, media_type=media_type)


# ===== 飞书 Webhook =====

@app.post(CONFIG["feishu"]["path"])
async def feishu_webhook(request: Request):
    body = await request.json()
    logger.debug(f"[飞书] 收到事件: {json.dumps(body, ensure_ascii=False)[:200]}")

    # 飞书 URL 验证
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}

    # 事件处理
    if body.get("type") == "event_callback":
        event = body.get("event", {})
        msg_type = event.get("message", {}).get("msg_type", "")
        if msg_type == "text":
            result = await eco_handler.handle_message("feishu", body)
            return _build_feishu_reply(result)

    return {"code": 0}


def _build_feishu_reply(result: dict) -> dict:
    """构建飞书回复"""
    if result.get("type") == "text":
        return {
            "code": 0,
            "data": {
                "content": json.dumps({"text": result["content"]}, ensure_ascii=False),
                "msg_type": "text",
            }
        }
    return {"code": 0}


# ===== 企业微信 Webhook =====

@app.post(CONFIG["wecom"]["path"])
async def wecom_webhook(request: Request):
    body = await request.json()
    logger.debug(f"[企业微信] 收到事件: {json.dumps(body, ensure_ascii=False)[:200]}")

    # URL 验证（GET 请求）
    if request.method == "GET":
        query = request.query_params
        if verify_wecom_signature(query):
            return JSONResponse(content=query.get("echostr", ""))
        raise HTTPException(status_code=403)

    msg_type = body.get("MsgType", "")
    if msg_type == "text":
        result = await eco_handler.handle_message("wecom", body)
        return _build_wecom_reply(result)

    return {"code": 0}


def verify_wecom_signature(query: dict) -> bool:
    """企业微信签名验证"""
    token = CONFIG["wecom"]["token"]
    if not token:
        return True  # 无配置时跳过
    signature = query.get("msg_signature", "")
    timestamp = query.get("timestamp", "")
    nonce = query.get("nonce", "")
    echostr = query.get("echostr", "")
    # sha1(sorted(token, timestamp, nonce, echostr))
    arr = sorted([token, timestamp, nonce, echostr])
    calc_sig = hashlib.sha1("".join(arr).encode()).hexdigest()
    return calc_sig == signature


def _build_wecom_reply(result: dict) -> dict:
    """构建企业微信回复"""
    if result.get("type") == "text":
        return {"content": result["content"], "msgtype": "text"}
    return {"code": 0}


# ===== 钉钉 Webhook =====

@app.post(CONFIG["dingtalk"]["path"])
async def dingtalk_webhook(request: Request):
    body = await request.json()
    logger.debug(f"[钉钉] 收到事件: {json.dumps(body, ensure_ascii=False)[:200]}")

    # 钉钉签名验证
    headers = request.headers
    timestamp = headers.get("timestamp", "")
    sign = headers.get("sign", "")
    if not verify_dingtalk_sign(timestamp, sign):
        raise HTTPException(status_code=403)

    msg_type = body.get("msgtype", body.get("msg_type", ""))
    if msg_type in ("text", ""):
        result = await eco_handler.handle_message("dingtalk", body)
        return _build_dingtalk_reply(result)

    return {"code": 0}


def verify_dingtalk_sign(timestamp: str, sign: str) -> bool:
    """钉钉签名验证"""
    secret = CONFIG["dingtalk"]["app_secret"]
    if not secret or not timestamp or not sign:
        return True
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode(), string_to_sign.encode(), hashlib.sha256
    ).digest()
    calc_sign = base64.b64encode(hmac_code).decode()
    return calc_sign == sign


def _build_dingtalk_reply(result: dict) -> dict:
    """构建钉钉回复"""
    if result.get("type") == "text":
        return {"msgtype": "text", "text": {"content": result["content"]}}
    return {"code": 0}


# ===== 微信公众平台 Webhook =====

@app.post(CONFIG["wechat"]["path"])
async def wechat_webhook(request: Request):
    # 微信签名验证（GET）
    if request.method == "GET":
        query = request.query_params
        if verify_wechat_signature(query):
            return JSONResponse(content=query.get("echostr", ""))
        raise HTTPException(status_code=403)

    # POST 消息
    body = await request.body()
    xml_data = body.decode("utf-8")
    # 简易 XML 解析
    import re
    msg_type = re.search(r"<MsgType><!\[CDATA\[(.*?)\]\]></MsgType>", xml_data)
    content = re.search(r"<Content><!\[CDATA\[(.*?)\]\]></Content>", xml_data)
    from_user = re.search(r"<FromUserName><!\[CDATA\[(.*?)\]\]></FromUserName>", xml_data)

    if msg_type and msg_type.group(1) == "text" and content:
        data = {
            "Content": content.group(1),
            "FromUserName": from_user.group(1) if from_user else "",
        }
        result = await eco_handler.handle_message("wechat", data)
        return _build_wechat_reply(result, data)

    return ""


def verify_wechat_signature(query: dict) -> bool:
    """微信签名验证"""
    token = CONFIG["wechat"]["token"]
    if not token:
        return True
    signature = query.get("signature", "")
    timestamp = query.get("timestamp", "")
    nonce = query.get("nonce", "")
    arr = sorted([token, timestamp, nonce])
    calc_sig = hashlib.sha1("".join(arr).encode()).hexdigest()
    return calc_sig == signature


def _build_wechat_reply(result: dict, data: dict) -> str:
    """构建微信 XML 回复"""
    from_user = data.get("FromUserName", "")
    to_user = data.get("ToUserName", "")
    content = result.get("content", "")
    now = str(int(datetime.now().timestamp()))
    return f"""<xml>
<ToUserName><![CDATA[{from_user}]]></ToUserName>
<FromUserName><![CDATA[{to_user}]]></FromUserName>
<CreateTime>{now}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{content}]]></Content>
</xml>"""


# ===== 启动服务 =====

def main():
    parser = argparse.ArgumentParser(description="eco Agent 网关服务")
    parser.add_argument("--platforms", default="all", help="启动的平台（逗号分隔，默认 all）")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=7070, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="热重载模式")
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("  eco Agent Gateway 启动")
    logger.info(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info(f"  平台: {args.platforms}")
    logger.info("=" * 50)

    for platform, cfg in CONFIG.items():
        has_creds = any(v for k, v in cfg.items() if k.endswith(("_id", "_key", "_secret", "_token")))
        status = "配置就绪" if has_creds else "未配置"
        logger.info(f"  [{platform}] {cfg['path']} :{cfg['port']} ({status})")
        logger.info(f"    {cfg['path']}")

    uvicorn.run(
        "eco-gateway-server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
