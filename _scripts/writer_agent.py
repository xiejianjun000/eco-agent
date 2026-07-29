#!/usr/bin/env python3
"""
writer_agent.py — ECO AGENT 执法文书生成 Agent

功能：
  1. 3 种执法文书模板（处罚决定书/听证通知书/现场检查记录）
  2. Jinja2 模板渲染引擎
  3. ACE 审查集成（Generator → Reflector → Curator）
  4. 文书草案导出

用法：
  from _scripts.writer_agent import WriterAgent
  wa = WriterAgent()
  doc = wa.generate("penalty_decision", {...})
  wa.ace_review(doc)
"""

import json
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Any

logger = logging.getLogger("writer_agent")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "memory-tree" / "obsidian_sync" / "documents"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    from jinja2 import Environment, FileSystemLoader, TemplateNotFound
    HAS_JINJA = True
except ImportError:
    HAS_JINJA = False
    logger.warning("jinja2 未安装，使用简易模板引擎")
    Environment = None


class SimpleTemplate:
    """简易模板引擎（无 Jinja2 时的降级方案）"""

    def __init__(self, content: str):
        self.content = content
        self.variables = set(re.findall(r'\{\{(.*?)\}\}', content))

    def render(self, **kwargs) -> str:
        result = self.content
        for var in self.variables:
            key = var.strip()
            value = kwargs.get(key, f"[{key}]")
            # 处理嵌套属性
            if "." in key:
                parts = key.split(".")
                value = kwargs
                try:
                    for p in parts:
                        value = value.get(p, f"[{key}]")
                except AttributeError:
                    value = f"[{key}]"
            # 处理列表循环
            if isinstance(value, list):
                value = "\n".join(str(v) for v in value)
            result = result.replace("{{ " + key + " }}", str(value))
            result = result.replace("{{" + key + "}}", str(value))
        return result


class TemplateEngine:
    """模板引擎（自动选择 Jinja2 或降级方案）"""

    def __init__(self):
        if HAS_JINJA and Environment:
            self.env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
        else:
            self.env = None

    def render(self, template_name: str, **kwargs) -> str:
        """渲染模板"""
        template_path = TEMPLATES_DIR / template_name
        if not template_path.exists():
            template_path = TEMPLATES_DIR / f"{template_name}.j2"

        if not template_path.exists():
            raise FileNotFoundError(f"模板不存在: {template_name}")

        content = template_path.read_text(encoding="utf-8")

        if self.env:
            try:
                tmpl = self.env.get_template(template_path.name)
                return tmpl.render(**kwargs)
            except (TemplateNotFound, Exception) as e:
                logger.warning(f"Jinja2 渲染失败，使用降级: {e}")

        # 降级方案
        tmpl = SimpleTemplate(content)
        return tmpl.render(**kwargs)


class WriterAgent:
    """执法文书生成 Agent"""

    DOC_TYPES = {
        "penalty_decision": {
            "name": "行政处罚决定书",
            "template": "penalty_decision.j2",
            "required_fields": ["party_name", "case_no", "violation_facts"],
        },
        "hearing_notice": {
            "name": "行政处罚听证通知书",
            "template": "hearing_notice.j2",
            "required_fields": ["party_name", "case_no", "case_name", "hearing_date"],
        },
        "inspection_record": {
            "name": "现场检查（勘察）笔录",
            "template": "inspection_record.j2",
            "required_fields": ["party_name", "inspection_date", "inspection_location"],
        },
    }

    def __init__(self, memory_tree=None):
        self._mt = memory_tree
        self._engine = TemplateEngine()
        self._documents: list[dict[str, Any]] = []

    def list_templates(self) -> dict[str, Any]:
        """列出可用模板"""
        return {k: {"name": v["name"], "required_fields": v["required_fields"]}
                for k, v in self.DOC_TYPES.items()}

    def generate(self, doc_type: str, data: dict[str, Any],
                 author: str = "ECO AGENT") -> dict[str, Any]:
        """生成执法文书"""
        if doc_type not in self.DOC_TYPES:
            return {"success": False, "error": f"不支持的文书类型: {doc_type}"}

        doc_config = self.DOC_TYPES[doc_type]
        template = doc_config["template"]
        doc_name = doc_config["name"]
        required = doc_config["required_fields"]

        # 验证必填字段
        missing = [f for f in required if f not in data or not data.get(f)]
        if missing:
            return {
                "success": False,
                "error": f"缺少必填字段: {', '.join(missing)}",
                "doc_type": doc_type,
            }

        # 填充默认值
        data.setdefault("now", datetime.now().strftime("%Y年%m月%d日"))
        data.setdefault("处罚机关", "生态环境主管部门")

        # 渲染模板
        try:
            content = self._engine.render(template, **data)
        except Exception as e:
            return {"success": False, "error": f"模板渲染失败: {e}"}

        # 构建文书记录
        doc_id = f"DOC-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{len(self._documents)+1:03d}"
        document = {
            "doc_id": doc_id,
            "doc_type": doc_type,
            "doc_name": doc_name,
            "title": f"{doc_name} — {data.get('party_name', '')}",
            "content": content,
            "author": author,
            "status": "draft",  # draft → reviewing → approved
            "data": data,
            "ace_result": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        self._documents.append(document)
        logger.info(f"[WriterAgent] 文书生成成功: {doc_id} - {document['title'][:40]}")
        return {"success": True, "document": document}

    # ═══════════════════════════════════
    # ACE 三阶段审查
    # ═══════════════════════════════════

    def ace_review(self, document: dict[str, Any]) -> dict[str, Any]:
        """ACE 三阶段审查文书"""
        if not document.get("success", False):
            return {"success": False, "error": "文书生成失败，无法审查"}

        doc = document["document"]

        # 阶段 1: Generator 已由 generate() 完成
        generator_result = {
            "status": "completed",
            "doc_id": doc["doc_id"],
            "content_length": len(doc["content"]),
        }

        # 阶段 2: Reflector 校验
        reflector_result = self._reflector_check(doc)

        # 阶段 3: Curator 决策
        curator_result = self._curator_decision(doc, reflector_result)

        ace = {
            "generator": generator_result,
            "reflector": reflector_result,
            "curator": curator_result,
            "final_score": curator_result["score"],
            "recommendation": curator_result["recommendation"],
        }

        # 更新文书状态
        doc["ace_result"] = ace
        if curator_result["passed"]:
            doc["status"] = "approved"
        elif curator_result["recommendation"] == "人工复核":
            doc["status"] = "reviewing"
        else:
            doc["status"] = "draft"

        logger.info(f"[ACE] 审查完成: {doc['doc_id']} "
                    f"评分 {curator_result['score']}/100 "
                    f"[{curator_result['recommendation']}]")
        return {"success": True, "ace": ace, "document": doc}

    def _reflector_check(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Reflector 校验文书"""
        content = doc.get("content", "")
        checks = {}
        issues = []

        # R1: 引用完整性
        refs = re.findall(r'《[^》]+》', content)
        checks["law_references"] = len(refs)
        if len(refs) == 0:
            issues.append("未发现法规引用")
            checks["law_ref_score"] = 0
        else:
            checks["law_ref_score"] = 90

        # R2: 金额格式
        amounts = re.findall(r'[\d,]+元', content)
        checks["penalty_amounts"] = len(amounts)
        checks["amount_format_score"] = 90 if amounts else 60

        # R3: 必填段检查
        required_sections = ["权利告知" if "处罚决定" in content else None,
                             "履行方式" if "履行" in content else None]
        present = [s for s in required_sections if s]
        checks["required_sections"] = len(present)
        checks["section_score"] = 90 if present else 50

        # R4: 日期格式
        dates = re.findall(r'\d{4}年\d{1,2}月\d{1,2}日', content)
        checks["dates_found"] = len(dates)
        checks["date_format_score"] = 90 if dates else 40

        # R5: 敏感信息
        phones = re.findall(r'1[3-9]\d{9}', content)
        if phones:
            issues.append("包含未脱敏手机号")
            checks["sensitive_data_score"] = 50
        else:
            checks["sensitive_data_score"] = 100

        # 综合评分
        scores = [v for k, v in checks.items() if k.endswith("_score")]
        overall = sum(scores) / len(scores) if scores else 50

        return {
            "checks": checks,
            "issues": issues,
            "overall_score": round(overall, 1),
            "passed": overall >= 70,
        }

    def _curator_decision(self, doc: dict[str, Any],
                          reflector: dict[str, Any]) -> dict[str, Any]:
        """Curator 最终决策"""
        score = reflector["overall_score"]
        issues = reflector["issues"]

        # 加分项
        if doc.get("data", {}).get("evidence_list"):
            score += 5
        if doc.get("data", {}).get("discretion_factors"):
            score += 5
        if doc.get("data", {}).get("benchmark_refs"):
            score += 5

        score = min(score, 100)

        # 决策
        if score >= 85:
            recommendation = "通过"
            passed = True
        elif score >= 70:
            recommendation = "人工复核"
            passed = True
        else:
            recommendation = "退回修改"
            passed = False

        return {
            "score": round(score, 1),
            "recommendation": recommendation,
            "passed": passed,
            "issues": issues,
        }

    # ═══════════════════════════════════
    # 导出
    # ═══════════════════════════════════

    def export(self, document: dict[str, Any], format: str = "md") -> dict[str, Any]:
        """导出文书到文件"""
        if not document.get("success", False):
            return {"success": False, "error": "无效文书"}

        doc = document["document"]
        doc_type = doc.get("doc_type", "unknown")
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', doc.get("title", "untitled"))[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format == "md":
            filename = f"{timestamp}_{safe_title}.md"
            file_path = OUTPUT_DIR / filename

            # 添加 frontmatter
            frontmatter = {
                "doc_id": doc["doc_id"],
                "doc_type": doc["doc_type"],
                "status": doc["status"],
                "author": doc["author"],
                "created": doc["created_at"][:10],
                "ace_score": doc.get("ace_result", {}).get("final_score", "N/A"),
            }
            fm_lines = ["---"]
            for k, v in frontmatter.items():
                fm_lines.append(f'{k}: "{v}"')
            fm_lines.append("---\n")

            full_content = "\n".join(fm_lines) + "\n" + doc["content"]
            file_path.write_text(full_content, encoding="utf-8")

            # 存入 Memory Tree
            if self._mt:
                try:
                    self._mt.create_node(
                        type="quality",
                        title=doc["title"][:80],
                        content=full_content[:3000],
                        tags=["document", doc_type],
                        score=85.0,
                        source="system",
                    )
                except Exception as e:
                    logger.warning(f"Memory Tree 写入失败: {e}")

            return {
                "success": True,
                "file_path": str(file_path),
                "format": format,
                "size": len(full_content),
            }

        return {"success": False, "error": f"不支持的格式: {format}"}

    def list_documents(self, status: str | None = None,
                       limit: int = 20) -> list[dict[str, Any]]:
        """列出已生成的文书"""
        docs = self._documents
        if status:
            docs = [d for d in docs if d.get("status") == status]
        return docs[:limit]

    def get_stats(self) -> dict[str, Any]:
        """获取文书统计"""
        return {
            "total": len(self._documents),
            "by_status": {
                status: sum(1 for d in self._documents if d.get("status") == status)
                for status in ("draft", "reviewing", "approved")
            },
            "by_type": {
                dt: sum(1 for d in self._documents if d.get("doc_type") == dt)
                for dt in self.DOC_TYPES
            },
        }


# ===== 测试 =====

def test():
    """测试执法文书生成"""
    import sys as _sys
    _sys.path.insert(0, str(PROJECT_ROOT))
    from _scripts.memory_tree import MemoryTree
    import tempfile
    import shutil

    db_path = Path(tempfile.mkdtemp()) / "test_writer.db"
    mt = MemoryTree(db_path)
    wa = WriterAgent(mt)

    # 测试生成处罚决定书
    print("[TEST] 生成行政处罚决定书...")
    doc1 = wa.generate("penalty_decision", {
        "case_no": "环罚字〔2026〕第001号",
        "party_name": "XX钢铁有限公司",
        "credit_code": "91110000MA12345678",
        "legal_representative": "张三",
        "address": "XX省XX市XX区XX路XX号",
        "investigation_process": "2026年3月15日，本机关执法人员对当事人进行现场检查...",
        "violation_facts": "经查，当事人烧结机头排放口二氧化硫浓度为150mg/m³，超过标准限值100mg/m³。",
        "evidence_list": ["现场检查笔录", "监测报告（编号：XXXX-2026-001）", "调查询问笔录"],
        "laws_violated": ["《生态环境法典》第二编第二分编第XX条"],
        "laws_basis": ["《生态环境法典》第二编第二分编第XX条第X款"],
        "discretion_factors": ["超标倍数0.5倍，属一般情节", "当事人积极配合调查"],
        "benchmark_refs": ["《主要大气污染物行政处罚裁量基准》"],
        "penalties": ["责令立即改正违法行为", "处罚款人民币叁拾伍万元整（¥350,000.00）"],
        "execution_method": "当事人应在收到本决定书之日起十五日内，将罚款缴至指定银行账户...",
        "复议机关": "XX省生态环境厅",
        "人民法院": "XX市人民法院",
    })

    # ACE 审查
    print("[TEST] ACE 审查...")
    ace_result = wa.ace_review(doc1)
    print(f"  ACE 评分: {ace_result['ace']['final_score']}/100")
    print(f"  建议: {ace_result['ace']['recommendation']}")

    # 导出
    print("[TEST] 导出...")
    export_result = wa.export(doc1, format="md")
    print(f"  导出路径: {export_result.get('file_path', 'N/A')}")

    # 统计
    stats = wa.get_stats()
    print(f"\n[TEST] 文书统计: {json.dumps(stats, ensure_ascii=False)}")

    import gc; gc.collect()
    try: shutil.rmtree(db_path.parent)
    except Exception: pass
    print("\n[OK] 执法文书模块测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
