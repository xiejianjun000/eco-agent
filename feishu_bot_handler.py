#!/usr/bin/env python3
"""飞书 Bot 自动回复处理器"""

import json
import time
import subprocess
import logging
import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
EVENTS_DIR = PROJECT_ROOT / "gateway" / "feishu_events"
PROCESSED_LOG = EVENTS_DIR / ".processed_ids"
LARK_CLI = r"C:\Users\Administrator\AppData\Roaming\npm\lark-cli.cmd"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("feishu_handler")

processed = set()
if PROCESSED_LOG.exists():
    processed = set(filter(None, PROCESSED_LOG.read_text().strip().split("\n")))

# 加载 MCP 模块（文件名含短横线，需特殊加载）
_mcp = None
def _load_mcp():
    global _mcp
    if _mcp is None:
        mcp_path = PROJECT_ROOT / "_scripts" / "eco-knowledge-mcp.py"
        if mcp_path.exists():
            spec = importlib.util.spec_from_file_location("eco_knowledge_mcp", str(mcp_path))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _mcp = mod
    return _mcp

def save_processed():
    PROCESSED_LOG.write_text("\n".join(sorted(processed)))

def handle_message(event):
    content = event.get("content", "").strip()
    message_id = event.get("message_id", "")
    if not content or message_id in processed:
        return
    processed.add(message_id)
    save_processed()
    reply = generate_reply(content)
    if reply:
        cmd = [LARK_CLI, "im", "+messages-reply", "--message-id", message_id,
               "--text", reply, "--as", "bot", "--format", "json"]
        r = subprocess.run(cmd, capture_output=True, text=False, timeout=20)
        out = r.stdout.decode('utf-8', errors='replace') if r.stdout else ""  # noqa: F841 预留：回执解析
        err = r.stderr.decode('utf-8', errors='replace') if r.stderr else ""
        if r.returncode == 0:
            logger.info(f"回复成功: {content[:30]}")
        else:
            logger.warning(f"回复失败: {err[:200]}")

def generate_reply(msg: str) -> str:
    msg = msg.strip()
    msg_lower = msg.lower()
    if msg_lower in ("你好", "hi", "hello", "您好", "在吗"):
        return (
            "你好！我是 eco Agent 执法助手，精通全部现行生态环境法律法规。\n\n"
            "发送法规名称查询法律条文\n"
            "发送违法事实获取裁量建议\n"
            "发送「帮助」查看使用说明\n\n"
            "请问有什么可以帮你的？"
        )
    if msg_lower in ("帮助", "help", "?", "h") or msg.startswith("帮助"):
        return (
            "eco Agent 执法助手使用说明\n\n"
            "【法规检索】\n"
            "发送法规名称，如：大气污染防治法\n\n"
            "【执法问答】\n"
            "描述违法事实，如：某企业超标排放二氧化硫\n\n"
            "【案例查询】\n"
            "发送：案例 + 关键词\n\n"
            "【状态查询】\n"
            "发送：状态"
        )
    if msg_lower in ("状态", "status"):
        return "eco Agent 运行中 | 事件监听: 在线 | 知识库: FlowWiki 同步中"
    return search_and_reply(msg)

def search_and_reply(query: str) -> str:
    try:
        mcp = _load_mcp()
        if mcp:
            vault = mcp.find_vault_path()
            if vault and vault.exists():
                wiki_files = mcp.collect_wiki_files(vault)
                results = mcp.search_in_files(wiki_files, query, max_results=3)
                if results:
                    lines = [f"检索到与「{query}」相关的结果：\n"]
                    for r in results:
                        title = r.get("title", "?")
                        snippet = r.get("snippet", "")[:120]
                        lines.append(f"- {title}")
                        if snippet:
                            lines.append(f"  {snippet}")
                        lines.append("")
                    return "\n".join(lines)
    except Exception as e:
        logger.warning(f"检索异常: {e}")
    return (
        f"收到：「{query[:60]}」\n\n"
        "正为您检索相关法规，请稍后重试。\n"
        "发送「帮助」查看使用说明。"
    )

def watch_loop():
    logger.info("飞书 Bot 自动回复处理器启动...")
    while True:
        try:
            for f in sorted(EVENTS_DIR.glob("*.json")):
                if f.name.startswith(".") or not f.is_file():
                    continue
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    handle_message(data)
                    f.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"处理 {f.name}: {e}")
                    try: f.unlink(missing_ok=True)
                    except Exception: pass
        except Exception as e:
            logger.warning(f"循环异常: {e}")
        time.sleep(3)

if __name__ == "__main__":
    watch_loop()
