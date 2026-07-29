#!/usr/bin/env python3
"""
message_templates.py — ECO AGENT 统一消息模板

各平台公用消息模板，按平台能力自动适配。
"""

import json


class MessageTemplates:
    """消息模板库"""

    # ===== 欢迎消息 =====
    @staticmethod
    def welcome(platform: str = "feishu") -> str:
        templates = {
            "feishu": "欢迎使用 ECO AGENT 执法助手！\n\n"
                      "我是您的 AI 同事，精通全部现行生态环境法律法规。\n\n"
                      "📖 发送法规名称查询法律条文\n"
                      "⚖️ 发送违法事实获取裁量建议\n"
                      "💡 发送「帮助」查看使用说明",

            "wecom": "欢迎使用 ECO AGENT 执法助手！\n\n"
                     "我是您的 AI 同事，精通全部现行生态环境法律法规。\n\n"
                     "[法规检索] 发送法规名称查询法律条文\n"
                     "[执法问答] 发送违法事实获取裁量建议\n"
                     "[帮助] 发送「帮助」查看使用说明",

            "dingtalk": "欢迎使用 ECO AGENT 执法助手！\n\n"
                        "我是您的 AI 同事，精通全部现行生态环境法律法规。\n\n"
                        "📖 发送法规名称查询法律条文\n"
                        "⚖️ 发送违法事实获取裁量建议\n"
                        "💡 发送「帮助」查看使用说明",

            "wechat": "欢迎关注 ECO AGENT 执法助手！\n\n"
                      "我是您的 AI 同事，精通全部现行生态环境法律法规。\n\n"
                      "📖 发送法规名称查询法律条文\n"
                      "⚖️ 发送违法事实获取裁量建议\n"
                      "💡 发送「帮助」查看使用说明",
        }
        return templates.get(platform, templates["feishu"])

    # ===== 帮助消息 =====
    @staticmethod
    def help(platform: str = "feishu") -> str:
        templates = {
            "feishu": "**ECO AGENT 执法助手使用说明**\n\n"
                      "📖 **法规检索**\n"
                      "发送法规名称，如：大气污染防治法\n\n"
                      "⚖️ **执法问答**\n"
                      "描述违法事实，如：某企业超标排放二氧化硫\n\n"
                      "📁 **案例查询**\n"
                      "发送：案例 + 关键词\n\n"
                      "📊 **系统状态**\n"
                      "发送：状态\n\n"
                      "🆘 **帮助**\n"
                      "发送：帮助",

            "wecom": "ECO AGENT 执法助手使用说明\n\n"
                     "[法规检索]\n"
                     "发送法规名称，如：大气污染防治法\n\n"
                     "[执法问答]\n"
                     "描述违法事实，如：某企业超标排放二氧化硫\n\n"
                     "[案例查询]\n"
                     "发送：案例 + 关键词\n\n"
                     "[系统状态]\n"
                     "发送：状态\n\n"
                     "[帮助]\n"
                     "发送：帮助",

            "dingtalk": "ECO AGENT 执法助手使用说明\n\n"
                        "📖 法规检索\n"
                        "发送法规名称，如：大气污染防治法\n\n"
                        "⚖️ 执法问答\n"
                        "描述违法事实，如：某企业超标排放二氧化硫\n\n"
                        "📁 案例查询\n"
                        "发送：案例 + 关键词\n\n"
                        "📊 系统状态\n"
                        "发送：状态\n\n"
                        "💡 帮助\n"
                        "发送：帮助",

            "wechat": "ECO AGENT 执法助手使用说明\n\n"
                      "📖 法规检索：发送法规名称\n"
                      "⚖️ 执法问答：描述违法事实\n"
                      "📁 案例查询：发送「案例」+关键词\n"
                      "📊 系统状态：发送「状态」\n"
                      "💡 帮助：发送「帮助」",
        }
        return templates.get(platform, templates["feishu"])

    # ===== 错误消息 =====
    @staticmethod
    def error(platform: str = "feishu", detail: str = "") -> str:
        templates = {
            "feishu": f"⚠️ 处理请求时出现异常，请稍后重试。\n{detail}".strip(),
            "wecom": f"[ERROR] 处理请求时出现异常，请稍后重试。\n{detail}".strip(),
            "dingtalk": f"⚠️ 处理请求时出现异常，请稍后重试。\n{detail}".strip(),
            "wechat": f"抱歉，处理请求时出现异常，请稍后重试。\n{detail}".strip(),
        }
        return templates.get(platform, templates["feishu"])

    # ===== 频率限制 =====
    @staticmethod
    def rate_limit(platform: str = "feishu") -> str:
        templates = {
            "feishu": "⏳ 消息频率过高，请稍后再发。",
            "wecom": "[WARN] 消息频率过高，请稍后再发。",
            "dingtalk": "⏳ 消息频率过高，请稍后再发。",
            "wechat": "消息频率过高，请稍后再发。",
        }
        return templates.get(platform, templates["feishu"])

    # ===== 法规检索结果 =====
    @staticmethod
    def statute_result(platform: str, statute_name: str, summary: str, articles: list = None) -> str:
        """法规检索结果模板"""
        if platform == "feishu":
            text = f"**{statute_name}**\n\n{summary}"
        elif platform == "wecom":
            text = f"{statute_name}\n\n{summary}"
        else:
            text = f"{statute_name}\n\n{summary}"

        if articles:
            text += "\n\n**相关条款**"
            for a in articles[:5]:
                text += f"\n- {a}"
        return text

    # ===== 执法分析结果 =====
    @staticmethod
    def enforcement_analysis(platform: str, facts: str, basis: str, suggestion: str) -> str:
        """执法分析结果模板"""
        sep = "\n\n"
        header = {
            "feishu": "**⚖️ 执法分析报告**",
            "wecom": "[执法分析报告]",
            "dingtalk": "⚖️ 执法分析报告",
            "wechat": "⚖️ 执法分析报告",
        }.get(platform, "执法分析报告")

        parts = [
            header,
            f"**案情**\n{facts}" if platform == "feishu" else f"[案情]\n{facts}",
            f"**法律依据**\n{basis}" if platform == "feishu" else f"[法律依据]\n{basis}",
            f"**裁量建议**\n{suggestion}" if platform == "feishu" else f"[裁量建议]\n{suggestion}",
        ]
        return sep.join(parts)

    # ===== 审批通知 =====
    @staticmethod
    def approval_notification(platform: str, operation: str, risk_level: str, details: str) -> str:
        """审批通知模板"""
        if platform == "feishu":
            return (
                f"**🔴 ECO AGENT 执法风险操作审批**\n\n"
                f"操作类型：{operation}\n"
                f"风险等级：{risk_level}\n"
                f"操作详情：{details}\n\n"
                f"请前往飞书审批中心处理。"
            )
        elif platform == "wecom":
            return (
                f"[审批] ECO AGENT 执法风险操作\n\n"
                f"操作类型：{operation}\n"
                f"风险等级：{risk_level}\n"
                f"操作详情：{details}\n\n"
                f"请前往企业微信审批中心处理。"
            )
        elif platform == "dingtalk":
            return (
                f"🔴 ECO AGENT 执法风险操作审批\n\n"
                f"操作类型：{operation}\n"
                f"风险等级：{risk_level}\n"
                f"操作详情：{details}"
            )
        return f"[审批] {operation} - {risk_level}"

    # ===== 卡片消息构建 =====
    @staticmethod
    def build_feishu_card(title: str, content: str, risk_level: str = "normal") -> dict:
        """构建飞书交互卡片"""
        color_map = {
            "high": "red",
            "medium": "orange",
            "low": "yellow",
            "normal": "blue",
        }
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color_map.get(risk_level, "blue"),
            },
            "elements": [{"tag": "markdown", "content": content}],
        }

    @staticmethod
    def build_dingtalk_card(title: str, content: str) -> str:
        """构建钉钉 ActionCard 消息"""
        card = {
            "title": title,
            "text": f"# {title}\n\n{content}",
            "btnOrientation": "0",
            "singleTitle": "查看详情",
            "singleURL": "https://www.dingtalk.com",
        }
        return json.dumps(card, ensure_ascii=False)
