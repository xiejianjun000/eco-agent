#!/usr/bin/env python3
"""
bloodline_compressor.py — ECO AGENT 血统压缩机制

功能：
  1. 会话摘要生成（自动压缩长会话为摘要）
  2. parent_session_id 血统链维护
  3. Token 压缩策略（内容感知压缩）
  4. 血统追溯（可从当前会话回溯到初始会话）

用法：
  from _scripts.bloodline_compressor import BloodlineCompressor
  bc = BloodlineCompressor()
  summary = bc.compress_session(session_id, messages)
  lineage = bc.trace_lineage(session_id)
"""

import json
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Any

logger = logging.getLogger("bloodline_compressor")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LINEAGE_DIR = PROJECT_ROOT / "memory-tree" / "obsidian_sync" / "sessions"
LINEAGE_DIR.mkdir(parents=True, exist_ok=True)


class BloodlineCompressor:
    """血统压缩器"""

    def __init__(self, memory_tree=None):
        self._mt = memory_tree
        self._lineage: dict[str, dict[str, Any]] = {}

    # ═══════════════════════════════════
    # 会话摘要生成
    # ═══════════════════════════════════

    def compress_session(self, session_id: str, messages: list[dict[str, Any]],
                         parent_session_id: str | None = None,
                         max_tokens: int = 500) -> dict[str, Any]:
        """压缩会话生成血统记录"""
        logger.info(f"[Bloodline] 压缩会话: {session_id} ({len(messages)} 条消息)")

        # 提取关键信息
        summary = self._generate_summary(messages, max_tokens)

        # 提取操作类型
        operations = self._extract_operations(messages)

        # 提取关键实体
        entities = self._extract_entities(messages)

        # 提取技能线索
        skill_hints = self._extract_skill_hints(operations)

        # 构建血统记录
        lineage_record = {
            "session_id": session_id,
            "parent_session_id": parent_session_id,
            "timestamp": datetime.now().isoformat(),
            "message_count": len(messages),
            "summary": summary,
            "operations": operations,
            "entities": entities,
            "skill_hints": skill_hints,
            "token_estimate": self._estimate_tokens(messages),
            "compression_ratio": self._calc_compression_ratio(messages, summary),
        }

        # 维护血统链
        self._lineage[session_id] = lineage_record
        self._persist_lineage(session_id, lineage_record)

        # 同步到 Memory Tree
        if self._mt:
            try:
                self._mt.create_node(
                    type="session",
                    title=f"会话 {session_id[:16]}...",
                    content=json.dumps(lineage_record, ensure_ascii=False)[:3000],
                    tags=["session", "lineage"],
                    score=60.0,
                    source="system",
                )
            except Exception as e:
                logger.warning(f"Memory Tree 写入失败: {e}")

        logger.info(f"[Bloodline] 压缩完成: {len(messages)} 条 → {len(summary)} 字 "
                    f"(比率 {lineage_record['compression_ratio']:.1f}x)")
        return lineage_record

    def _generate_summary(self, messages: list[dict[str, Any]],
                          max_chars: int = 500) -> str:
        """生成会话摘要"""
        if not messages:
            return "（空会话）"

        parts = []
        # 提取系统操作
        operations = []
        queries = []

        for msg in messages:
            role = msg.get("role", "")
            content = str(msg.get("content", ""))[:200]

            if role == "user":
                queries.append(content[:100])
            elif role == "assistant" or role == "tool":
                pass

            op = msg.get("operation", "")
            if op:
                operations.append(op)

        if queries:
            parts.append(f"查询: {' → '.join(queries[:3])}")
        if operations:
            parts.append(f"操作: {', '.join(set(operations[:5]))}")

        summary = " | ".join(parts) if parts else f"共 {len(messages)} 条消息"
        return summary[:max_chars]

    def _extract_operations(self, messages: list[dict[str, Any]]) -> list[str]:
        """提取操作类型"""
        ops = set()
        for msg in messages:
            content = str(msg.get("content", ""))
            if "法规" in content or "检索" in content or "查询" in content:
                ops.add("法规检索")
            if "处罚" in content or "裁量" in content or "罚款" in content:
                ops.add("裁量建议")
            if "案例" in content:
                ops.add("案例查询")
            if "文书" in content or "决定书" in content or "通知" in content:
                ops.add("文书生成")
            op = msg.get("operation", "")
            if op:
                ops.add(op)
        return list(ops)

    def _extract_entities(self, messages: list[dict[str, Any]]) -> list[str]:
        """提取关键实体"""
        entities = set()
        for msg in messages:
            content = str(msg.get("content", ""))
            # 提取《法规名称》
            for m in re.finditer(r'《([^》]+)》', content):
                entities.add(m.group(1))
            # 提取案号
            for m in re.finditer(r'[（(]\d{4}[）)][^号]+号', content):
                entities.add(m.group(0)[:20])
        return list(entities)

    def _extract_skill_hints(self, operations: list[str]) -> list[str]:
        """提取技能线索"""
        hints = []
        if "法规检索" in operations:
            count = operations.count("法规检索")
            if count >= 3:
                hints.append("法规检索操作频繁，可结晶为 Skill")
        if "裁量建议" in operations:
            count = operations.count("裁量建议")
            if count >= 3:
                hints.append("裁量建议操作频繁，可结晶为 Skill")
        if "文书生成" in operations:
            count = operations.count("文书生成")
            if count >= 3:
                hints.append("文书生成操作频繁，可结晶为 Skill")
        return hints

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """估算 token 数"""
        total = 0
        for msg in messages:
            content = str(msg.get("content", ""))
            # 中文字符 ≈ 2 tokens，英文 ≈ 1 token
            chinese_chars = len(re.findall(r'[一-鿿]', content))
            other_chars = len(content) - chinese_chars
            total += chinese_chars * 2 + other_chars
        return total

    def _calc_compression_ratio(self, messages: list[dict[str, Any]],
                                summary: str) -> float:
        """计算压缩比率"""
        original_tokens = self._estimate_tokens(messages)
        summary_tokens = len(summary) * 1.5  # 近似
        if summary_tokens == 0:
            return 0
        return round(original_tokens / summary_tokens, 1)

    # ═══════════════════════════════════
    # 血统链维护
    # ═══════════════════════════════════

    def trace_lineage(self, session_id: str,
                      max_depth: int = 10) -> list[dict[str, Any]]:
        """追溯血统链"""
        lineage = []
        current_id = session_id
        depth = 0

        while current_id and depth < max_depth:
            record = self._lineage.get(current_id) or self._load_lineage(current_id)
            if not record:
                break

            lineage.append(record)
            current_id = record.get("parent_session_id")
            depth += 1

        return lineage

    def get_lineage_depth(self, session_id: str) -> int:
        """获取血统深度"""
        return len(self.trace_lineage(session_id))

    def format_lineage(self, session_id: str) -> str:
        """格式化血统链为可读文本"""
        lineage = self.trace_lineage(session_id)
        if not lineage:
            return f"未找到血统记录: {session_id}"

        lines = ["## 血统追溯链", ""]
        for i, record in enumerate(reversed(lineage)):
            indent = "  " * (len(lineage) - i - 1)
            prefix = "└─ " if i == len(lineage) - 1 else "┌─ "
            sid = record["session_id"][:20]
            summary = record["summary"][:60]
            ops = ", ".join(record.get("operations", [])[:3])
            lines.append(f"{indent}{prefix}会话 {sid}")
            lines.append(f"{indent}  ├ 摘要: {summary}")
            if ops:
                lines.append(f"{indent}  └ 操作: {ops}")
            lines.append("")

        return "\n".join(lines)

    # ═══════════════════════════════════
    # Token 压缩策略
    # ═══════════════════════════════════

    def compress_content(self, content: str, target_ratio: float = 0.3,
                         content_type: str = "auto") -> str:
        """内容感知压缩"""
        if not content:
            return content

        # 自动检测内容类型
        if content_type == "auto":
            content_type = self._detect_content_type(content)

        if content_type == "json":
            return self._compress_json(content, target_ratio)
        elif content_type == "code":
            return self._compress_code(content, target_ratio)
        elif content_type == "log":
            return self._compress_log(content, target_ratio)
        elif content_type == "markdown":
            return self._compress_markdown(content, target_ratio)
        else:
            return self._compress_text(content, target_ratio)

    def _detect_content_type(self, content: str) -> str:
        """检测内容类型"""
        content_stripped = content.strip()
        if content_stripped.startswith("{") or content_stripped.startswith("["):
            return "json"
        if content_stripped.startswith("def ") or content_stripped.startswith("class "):
            return "code"
        if content_stripped.startswith("INFO") or content_stripped.startswith("ERROR"):
            return "log"
        if content_stripped.startswith("#") or content_stripped.startswith("---"):
            return "markdown"
        return "text"

    def _compress_json(self, content: str, ratio: float) -> str:
        """压缩 JSON（移除空值、缩短键名）"""
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                compressed = {k[:8] if len(k) > 12 else k: v
                              for k, v in data.items()
                              if v is not None and v != "" and v != []}
            elif isinstance(data, list):
                compressed = data[:max(5, int(len(data) * ratio))]
            else:
                compressed = data
            return json.dumps(compressed, ensure_ascii=False)[:2000]
        except json.JSONDecodeError:
            return content[:1000]

    def _compress_code(self, content: str, ratio: float) -> str:
        """压缩代码（保留函数签名，压缩函数体）"""
        lines = content.split("\n")
        compressed = []
        for line in lines:
            # 保留函数定义、类定义、注释
            if (line.strip().startswith("def ") or
                line.strip().startswith("class ") or
                line.strip().startswith("#") or
                line.strip().startswith("import ") or
                line.strip().startswith("from ")) or line.strip().startswith(("    def ", "    class ")):
                compressed.append(line)
        result = "\n".join(compressed)
        return result if result else content[:1000]

    def _compress_log(self, content: str, ratio: float) -> str:
        """压缩日志（保留 ERROR/WARN，压缩 INFO/DEBUG）"""
        lines = content.split("\n")
        compressed = []
        for line in lines:
            if "ERROR" in line or "WARN" in line or "INFO" in line and len(compressed) % 3 == 0:
                compressed.append(line)
        return "\n".join(compressed)[:2000]

    def _compress_markdown(self, content: str, ratio: float) -> str:
        """压缩 Markdown（保留标题和列表结构）"""
        lines = content.split("\n")
        compressed = []
        for line in lines:
            if line.startswith("#") or line.startswith("-") or line.startswith("|") or line.strip() == "":
                compressed.append(line)
        return "\n".join(compressed)[:2000]

    def _compress_text(self, content: str, ratio: float) -> str:
        """压缩文本"""
        target_len = int(len(content) * ratio)
        return content[:max(target_len, 500)]

    # ═══════════════════════════════════
    # 持久化
    # ═══════════════════════════════════

    def _persist_lineage(self, session_id: str, record: dict[str, Any]):
        """持久化血统记录"""
        file_path = LINEAGE_DIR / f"{session_id[:20]}.json"
        file_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_lineage(self, session_id: str) -> dict[str, Any] | None:
        """加载血统记录"""
        file_path = LINEAGE_DIR / f"{session_id[:20]}.json"
        if file_path.exists():
            try:
                return json.loads(file_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return None

    # ═══════════════════════════════════
    # 统计
    # ═══════════════════════════════════

    def get_stats(self) -> dict[str, Any]:
        """获取统计"""
        total_tokens = sum(
            r.get("token_estimate", 0) for r in self._lineage.values()
        )
        total_compressed = sum(
            len(r.get("summary", "")) for r in self._lineage.values()
        )
        return {
            "total_sessions": len(self._lineage),
            "total_tokens_original": total_tokens,
            "total_tokens_compressed": total_compressed,
            "avg_compression_ratio": round(
                total_tokens / max(total_compressed, 1), 1
            ) if total_compressed else 0,
        }


# ===== 测试 =====

def test():
    """测试血统压缩"""
    bc = BloodlineCompressor()

    # 模拟消息
    messages = [
        {"role": "user", "content": "大气污染防治法有哪些规定？"},
        {"role": "assistant", "content": "《大气污染防治法》已废止，由《生态环境法典》第二编第二分编吸收。"},
        {"role": "user", "content": "针对超标排放大气污染物，裁量基准是多少？"},
        {"role": "assistant", "content": "根据《主要大气污染物行政处罚裁量基准》，超标0.5倍建议处罚10-50万元。"},
        {"role": "user", "content": "有没有类似案例参考？"},
        {"role": "assistant", "content": "参考案例：XX钢铁有限公司超标排放大气污染物案，处罚35万元。"},
    ]

    # 血统压缩
    record = bc.compress_session("session_test_001", messages)
    print("[TEST] 血统压缩:")
    print(f"  消息数: {record['message_count']}")
    print(f"  摘要: {record['summary'][:60]}...")
    print(f"  操作: {', '.join(record['operations'])}")
    print(f"  实体: {', '.join(record['entities'])}")
    print(f"  压缩比: {record['compression_ratio']}x")

    # 血统链
    print("\n[TEST] 血统链追踪:")
    bc.compress_session("session_test_002", messages[:2],
                        parent_session_id="session_test_001")
    lineage = bc.trace_lineage("session_test_002")
    print(f"  深度: {len(lineage)}")

    # Token 压缩
    print("\n[TEST] Token 压缩:")
    log_content = "\n".join([
        "INFO: 开始执法检查",
        "ERROR: 法规引用异常: 大气污染防治法已废止",
        "WARN: 建议更新裁量基准引用",
        "INFO: 检查完成",
        "DEBUG: 耗时120ms",
    ])
    compressed = bc.compress_content(log_content, content_type="log")
    print(f"  原始: {len(log_content)} 字符")
    print(f"  压缩: {len(compressed)} 字符")

    # 统计
    stats = bc.get_stats()
    print(f"\n[TEST] 统计: {json.dumps(stats, ensure_ascii=False)}")

    print("\n[OK] 血统压缩机制测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
