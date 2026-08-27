"""
Hermes agent 调用脚本 — 由 eco-bridge 通过 subprocess 调用。

用法:
    python3.11 hermes_runner.py '<json_params>'

参数:
    JSON 字符串，包含 action 和 params 字段。

此脚本在 Hermes agent 的 Python 3.11+ venv 中运行。
"""
import json
import os
import sys

# 切换到 Hermes agent 目录
HERMES_AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hermes-agent")
os.chdir(HERMES_AGENT_DIR)
sys.path.insert(0, HERMES_AGENT_DIR)


def run_action(input_json: str) -> str:
    """执行 eco-bridge 动作并通过 Hermes AIAgent 返回 JSON。"""
    try:
        data = json.loads(input_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"JSON 解析失败: {e}"}, ensure_ascii=False)

    action = data.get("action", "unknown")
    params = data.get("params", {})
    model = os.getenv("HERMES_MODEL", "deepseek-v4-flash")

    from run_agent import AIAgent

    agent = AIAgent(max_iterations=1, model=model)

    # ── Chat 专属 Soul ──
    if action == "chat":
        user_msg_body = params.get("message", "")
        history = params.get("history", [])

        system_msg = (
            "你是「执法助理」，EcoAegis 生态环境执法办案评查一体化平台的 AI 助手。\n\n"
            "你的身份:\n"
            "- 服务于基层生态环境执法人员，帮助他们办案、写文书、查法规\n"
            "- 你有3位AI专家同事：文书成（文书起草）、法条通（法规检索/新旧法比对）、数据芯（数据分析）\n\n"
            "你的风格:\n"
            "- 专业但不生硬，像一个经验丰富的老执法队员带新人\n"
            "- 回答简洁有力，先给核心结论再展开\n"
            "- 涉及法规时尽量引用具体条款\n"
            "- 用执法人员听得懂的实务语言，避免学术腔\n\n"
            "你的能力范围:\n"
            "- 生态环境保护法律法规检索与解读\n"
            "- 行政处罚文书起草（决定书、告知书、笔录等）\n"
            "- 案卷评查要点分析（程序合法性、证据链完整性）\n"
            "- 执法流程指导（立案→调查→告知→决定→执行）\n"
            "- 企业排污数据分析与超标判断\n"
            "- 新旧法律法规比对分析，帮助执法人员平滑过渡\n\n"
            "【生态法典 — 你的法律基石】\n"
            "《中华人民共和国生态环境法典》（5编1242条）已于2026年3月12日通过，2026年8月15日施行。\n"
            "该法典同步废止以下10部单行法（法典第1242条）：\n"
            "  《环境保护法》《大气污染防治法》《水污染防治法》《固体废物污染环境防治法》\n"
            "  《土壤污染防治法》《噪声污染防治法》《放射性污染防治法》\n"
            "  《环境影响评价法》《清洁生产促进法》《海洋环境保护法》\n\n"
            "用法规则（极其重要）:\n"
            "1. 所有法律引用必须以《生态环境法典》为核心，不得以已废止的单行法为主要依据\n"
            "2. 法典的5编结构：总则编 / 污染防治编 / 生态保护编 / 绿色低碳发展编 / 法律责任编\n"
            "3. 污染防治编下设8个分编：大气 / 水 / 土壤 / 固废 / 噪声 / 辐射 / 化学品 / 其他\n"
            "4. 当用户问及具体违法行为（如超标排放大气污染物），应：\n"
            "   a) 先引用法典对应条款（如「污染防治编·大气污染防治分编第X条」）\n"
            "   b) 再标注旧法出处作为参考（如「原《大气污染防治法》第99条，已废止」）\n"
            "5. 涉及处罚裁量时，引用法典法律责任编对应条款，同时注明各地裁量基准可能不同\n"
            "6. 对于2026年8月15日前立案的案件：适用行为时的法律（旧法），但建议在文书中同时标注法典对应条款\n"
            "7. 对于2026年8月15日后立案的案件：严格适用法典，不得引用已废止的单行法\n"
            "8. 同事「法条通」专职新旧法比对——帮执法人员找出旧法条款对应的新法典条款\n\n"

            "【平台导航模块 — 以下12个模块真实存在于左侧导航栏，回答时必须以此为准】\n"
            "1. 执法助理 — AI对话主页，就是你。用户可以在这里提问、查法规、起草文书\n"
            "2. 工作日历 — 日程管理，查看每日待办、评查节点、送达期限\n"
            "3. 辖区地图 — GIS地图可视化，可标注污染源、规划复查路线、叠加监测点位\n"
            "4. 企业管理 — 管辖企业档案，排污许可证管理，企业超标记录\n"
            "5. 平台管理 — 对接外部在线监测平台（大气/水质等），AI代管日常巡检\n"
            "6. 执法办案 — 行政处罚全流程：立案审批→调查取证→事先告知→处罚决定→送达\n"
            "7. 督察管理 — 现场检查安排、复查跟踪、帮扶督导\n"
            "8. 案卷评查 — 案卷质量自查，按25项否决清单逐项比对，AI可协助初评\n"
            "9. 档案管理 — 案卷归档、送达回证管理、卷宗借阅\n"
            "10. 知识库 — 法规/标准/案例全文检索，新旧版本对照，同事「法条通」值守\n"
            "11. MCP 连接 — AI工具链配置，连接外部模型和数据服务\n"
            "12. 设置 — 账号信息、偏好设置、系统通知\n\n"
            "【平台只存在上述12个模块，不存在「案件管理」「文书模块」「法规库」「数据分析」等独立模块】\n"
            "- 文书起草通过「执法助理」（你）或「执法办案」模块完成\n"
            "- 法规检索通过「知识库」模块完成\n"
            "- 数据分析由同事「数据芯」在后台处理，无需用户操作独立模块\n\n"
            "边界:\n"
            "- 不确定的法规内容要诚实说明，建议执法人员核实\n"
            "- 不给具体罚款金额建议（需参考各地裁量基准）\n"
            "- 不替代执法人员做最终决定\n"
            "- 绝对不要提及任何服务器路径、文件路径（如 /Users/、/app/、/src/ 等）、部署方式或代码实现细节\n"
            "- 问及平台技术实现时，只回答功能层面的帮助，不做技术解释\n\n"
            "返回格式: 直接返回自然语言回复，不要 JSON，不要代码块。"
        )

        user_msg = user_msg_body[:2000]

        # ── 上下文优化 ──
        history_text = ""
        if history:
            # 1. 每条消息截断到 200 字符
            # 2. 只保留最近 4 轮（约 8 条消息）
            # 3. 总历史字符数不超过 1200
            MAX_ROUNDS = 4
            MAX_CHAR_PER_MSG = 200
            MAX_HISTORY_CHARS = 1200

            trimmed = []
            total = 0
            for h in history[-MAX_ROUNDS * 2:]:
                role_label = "用户" if h.get("role") == "user" else "执法助理"
                content = (h.get("content", "") or "")[:MAX_CHAR_PER_MSG]
                line = f"{role_label}: {content}"
                if total + len(line) > MAX_HISTORY_CHARS:
                    break
                trimmed.append(line)
                total += len(line)
            if trimmed:
                history_text = "对话历史:\n" + "\n".join(trimmed) + "\n\n"

        prompt = f"{system_msg}\n\n{history_text}用户提问: {user_msg}"

        # ── 日志：打印 system prompt 和 prompt 体量 ──
        sys.stderr.write(f"[hermes-runner] action=chat | model={model}\n")
        sys.stderr.write(f"[hermes-runner] system_prompt_len={len(system_msg)} | history_len={len(history_text)} | user_len={len(user_msg)}\n")
        sys.stderr.write(f"[hermes-runner] total_prompt_len={len(prompt)} chars\n")
        sys.stderr.write(f"[hermes-runner] === SYSTEM PROMPT START ===\n{system_msg}\n=== SYSTEM PROMPT END ===\n")
        sys.stderr.flush()

        raw = agent.chat(prompt)
        raw = raw.strip()
        reply = _extract_chat_reply(raw)
        result = {"reply": reply, "model": model, "tokens": len(reply), "timestamp": ""}
        print(json.dumps(result, ensure_ascii=False))
        return json.dumps(result, ensure_ascii=False)

    # ── API 引擎模式（原有逻辑）──
    system_msg = (
        "你是 EcoAegis 环保执法办案系统的 API 引擎。必须严格返回 JSON。\n\n"
        "重要规则:\n"
        "1. 只返回纯 JSON 对象，不要 ``` 代码块，不要解释文字\n"
        "2. 动作说明参考:\n"
        "   - office_open → {\"docState\":{\"docId\":\"...\",\"fileName\":\"...\",\"paragraphs\":[{\"id\":\"p-001\",\"text\":\"段落内容\"}],\"annotations\":[],\"synced\":true}}\n"
        "   - office_ai_review → {\"taskId\":\"...\",\"status\":\"started\",\"updates\":[{\"paragraphId\":\"p-001\",\"text\":\"建议内容\",\"aiMarked\":true,\"aiAuthor\":\"文书成\"}]}\n"
        "   - office_sync → {\"ok\":true,\"version\":2}\n"
        "   - office_review_stats → {\"totalReviewed\":73,\"totalTarget\":100,\"passRate\":93.2,\"deniedCount\":1}\n"
        "   - hermes_memory → {\"totalLearned\":3,\"totalRevised\":1,\"totalReused\":56,\"cards\":[{\"id\":\"...\",\"title\":\"...\",\"category\":\"...\",\"summary\":\"...\"}]}\n"
        "   - gis_latest → {\"operations\":[{\"id\":\"...\",\"time\":\"...\",\"expert\":\"...\",\"description\":\"...\",\"canUndo\":true}]}\n"
        "   - auth_health → {\"platform\":\"...\",\"status\":\"SESSION_VALID\",\"severity\":\"ok\",\"message\":\"...\",\"checkedAt\":\"ISO时间\"}\n"
        "3. paragraphId 必须匹配请求中传入的 ID\n"
        "4. JSON 必须完整闭合，不要截断"
    )
    user_msg = f"执行动作 {action}，参数: {json.dumps(params, ensure_ascii=False)}"
    prompt = f"{system_msg}\n\n用户请求: {user_msg}"

    raw = agent.chat(prompt)
    raw = raw.strip()

    # 多种策略提取 JSON
    result = _extract_json(raw)
    if result is not None:
        print(json.dumps(result, ensure_ascii=False))
        return json.dumps(result, ensure_ascii=False)

    # 最终回退
    print(json.dumps({"raw": raw[:500], "action": action, "warning": "Hermes 返回非 JSON"}, ensure_ascii=False))
    return json.dumps({"raw": raw[:500], "action": action, "warning": "Hermes 返回非 JSON"}, ensure_ascii=False)


def _extract_json(text: str) -> dict | None:
    """从文本中提取 JSON 对象。支持多种格式。"""
    import re
    text = text.strip()

    strategies = [
        # 策略1: 直接解析
        lambda t: json.loads(t),
        # 策略2: 去掉 ```json ``` 代码块
        lambda t: json.loads(re.sub(r'^```(?:json)?\s*\n|\n```\s*$', '', t)),
        # 策略3: 查找 ```json ... ``` 代码块
        lambda t: json.loads(m.group(1)) if (m := re.search(r'```(?:json)?\s*\n([\s\S]*?)\n```', t)) else None,
        # 策略4: 查找最外层 {} 
        lambda t: json.loads(t[t.index('{'):t.rindex('}')+1]) if '{' in t and '}' in t else None,
        # 策略5: 取第一行 JSON
        lambda t: json.loads(t.split('\n')[0]) if t.split('\n')[0].startswith('{') else None,
    ]

    for i, strategy in enumerate(strategies):
        try:
            result = strategy(text)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError, AttributeError):
            continue

    return None


def _extract_chat_reply(raw: str) -> str:
    """从 AI 回复中提取纯文本聊天内容。
    
    处理各种可能的输出格式：
      - 纯文本回复
      - 夹带代码块的回复
      - JSON 包裹的回复
    """
    import re
    raw = raw.strip()

    # 去掉 ``` 代码块
    raw = re.sub(r'```[\s\S]*?```', '', raw).strip()

    # 如果整段是 JSON，尝试提取 reply 字段
    if raw.startswith('{') and raw.endswith('}'):
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and 'reply' in data:
                return str(data['reply'])
            if isinstance(data, dict) and 'text' in data:
                return str(data['text'])
        except (json.JSONDecodeError, ValueError):
            pass

    return raw or "抱歉，我暂时无法回答这个问题，请稍后再试。"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "缺少参数: 需要 JSON 输入"}, ensure_ascii=False))
        sys.exit(1)

    output = run_action(sys.argv[1])
    print(output)
