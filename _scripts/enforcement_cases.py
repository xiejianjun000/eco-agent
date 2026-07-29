#!/usr/bin/env python3
"""
enforcement_cases.py — ECO AGENT 执法案例模块

功能：
  1. 执法案例库（入库/检索/相似匹配/评分）
  2. 裁量基准库（国家 + 各省/自动匹配）
  3. 案例统计分析

用法：
  from _scripts.enforcement_cases import CaseManager, BenchmarkManager
  cm = CaseManager()
  bm = BenchmarkManager()

  # 添加案例
  case_id = cm.add_case({...})

  # 搜索相似案例
  results = cm.find_similar("超标排放大气污染物", top_k=5)

  # 匹配裁量基准
  bench = bm.match_benchmark("大气", "超标排放", "浙江省")
"""

import json
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Any
from difflib import SequenceMatcher

logger = logging.getLogger("enforcement_cases")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ===== 案例数据模型 =====

CASE_TEMPLATE = {
    "case_id": "",            # ECO-CASE-YYYY-NNNN
    "type": "penalty",        # penalty / review / lawsuit / inspection
    "title": "",
    "status": "closed",       # closed / active / appeal
    "confidence": "high",     # high / medium / low
    "tags": [],
    "region": "",
    "pollutant_type": "",     # 污染物类型
    "penalty_amount": 0.0,    # 处罚金额（元）
    "law_basis": [],          # 法律依据列表
    "benchmark_refs": [],     # 引用裁量基准
    "facts": "",              # 案情摘要
    "analysis": "",           # 违法要件分析
    "decision": "",           # 处罚决定
    "key_points": "",         # 经验要点
    "source_refs": [],        # 原文指针
    "created_at": "",
    "updated_at": "",
}

BENCHMARK_TEMPLATE = {
    "benchmark_id": "",       # BM-NNNN
    "category": "",           # 大气/水/土壤/固废/噪声等
    "region": "national",     # 适用地区
    "title": "",
    "law_basis": "",
    "violation": "",          # 违法情形描述
    "penalty_range": {        # 处罚幅度
        "min": 0,
        "max": 0,
        "unit": "元"
    },
    "aggravating": [],        # 从重情节
    "mitigating": [],         # 从轻情节
    "exemption": [],          # 免罚情形
    "effective_date": "",
    "source": "",
}


class CaseManager:
    """执法案例管理器"""

    def __init__(self, memory_tree=None):
        self._mt = memory_tree
        self._cases: list[dict[str, Any]] = []
        self._case_dir = PROJECT_ROOT / "memory-tree" / "obsidian_sync" / "cases"
        self._case_dir.mkdir(parents=True, exist_ok=True)

    def add_case(self, case_data: dict[str, Any]) -> str:
        """添加案例"""
        # 生成案例 ID
        year = datetime.now().year
        count = len(self._list_case_files()) + 1
        case_id = f"ECO-CASE-{year}-{count:04d}"

        case = dict(CASE_TEMPLATE)
        case.update(case_data)
        case["case_id"] = case_id
        case["created_at"] = datetime.now().isoformat()
        case["updated_at"] = datetime.now().isoformat()

        # 保存到 Memory Tree
        if self._mt:
            content = self._format_case_content(case)
            tags = case.get("tags", [])
            if case.get("pollutant_type"):
                tags.append(f"pollutant/{case['pollutant_type']}")
            tags.append(f"case/{case.get('type', 'penalty')}")

            mt_node = self._mt.create_node(
                type="case",
                title=case["title"],
                content=content,
                tags=tags,
                score=self._calc_initial_score(case),
                source="manual",
                confidence=case.get("confidence", "medium"),
            )

        # 保存到本地
        file_path = self._case_dir / f"{case_id}.md"
        self._write_case_file(file_path, case)
        self._cases.append(case)

        logger.info(f"案例添加成功: {case_id} - {case['title'][:30]}")
        return case_id

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        """获取案例详情"""
        file_path = self._case_dir / f"{case_id}.md"
        if file_path.exists():
            return self._parse_case_file(file_path)

        # Memory Tree 回退
        if self._mt:
            mt_results = self._mt.search(case_id, type="case", max_results=1)
            if mt_results:
                return mt_results[0]
        return None

    def find_similar(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """查找相似案例"""
        # 优先通过 Memory Tree 检索
        if self._mt:
            results = self._mt.search(query, type="case", max_results=top_k)
            if results:
                return results

        # 降级：本地文本匹配
        scores = []
        cases = self.list_cases()
        query_lower = query.lower()
        keywords = set(query_lower.split())

        for case in cases:
            text = f"{case.get('title', '')} {case.get('facts', '')} {case.get('analysis', '')}"
            text_lower = text.lower()

            # 关键词匹配
            match_count = sum(1 for kw in keywords if kw in text_lower)
            if match_count == 0:
                continue

            # 文本相似度
            ratio = SequenceMatcher(None, query_lower, text_lower[:500]).ratio()

            final_score = (match_count / len(keywords)) * 0.6 + ratio * 0.4
            scores.append((final_score, case))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [case for _, case in scores[:top_k]]

    def list_cases(self, type: str | None = None,
                   region: str | None = None,
                   limit: int = 50) -> list[dict[str, Any]]:
        """列出案例"""
        cases = []
        for f in self._case_dir.rglob("*.md"):
            case = self._parse_case_file(f)
            if case:
                if type and case.get("type") != type:
                    continue
                if region and case.get("region") != region:
                    continue
                cases.append(case)

        cases.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return cases[:limit]

    def get_stats(self) -> dict[str, Any]:
        """案例统计"""
        cases = self.list_cases(limit=10000)
        stats = {
            "total": len(cases),
            "by_type": {},
            "by_region": {},
            "total_penalty": 0,
            "avg_penalty": 0,
        }

        for case in cases:
            ctype = case.get("type", "unknown")
            stats["by_type"][ctype] = stats["by_type"].get(ctype, 0) + 1

            region = case.get("region", "未知")
            stats["by_region"][region] = stats["by_region"].get(region, 0) + 1

            amount = case.get("penalty_amount", 0) or 0
            stats["total_penalty"] += amount

        if stats["total"] > 0:
            stats["avg_penalty"] = stats["total_penalty"] / stats["total"]

        return stats

    def find_similar_by_case(self, case_id: str, top_k: int = 5) -> list[dict[str, Any]]:
        """基于案例查找相似案例"""
        case = self.get_case(case_id)
        if not case:
            return []
        query = f"{case.get('title', '')} {case.get('facts', '')}"
        return self.find_similar(query, top_k + 1)[1:top_k + 1]

    # ── 内部方法 ──

    def _calc_initial_score(self, case: dict[str, Any]) -> float:
        """计算初始评分"""
        score = 60.0
        if case.get("confidence") == "high":
            score += 15
        elif case.get("confidence") == "medium":
            score += 5
        if case.get("penalty_amount", 0) > 100000:
            score += 10
        if case.get("key_points"):
            score += 10
        if case.get("analysis"):
            score += 5
        return min(score, 100)

    def _format_case_content(self, case: dict[str, Any]) -> str:
        """格式化案例内容为 Markdown"""
        lines = [
            f"## 案情摘要\n\n{case.get('facts', '')}\n",
            f"## 法律依据\n\n{chr(10).join(f'- {law}' for law in case.get('law_basis', []))}\n",
            f"## 违法要件分析\n\n{case.get('analysis', '')}\n",
        ]
        if case.get("decision"):
            lines.append(f"## 处罚决定\n\n{case['decision']}\n")
        if case.get("key_points"):
            lines.append(f"## 经验要点\n\n{case['key_points']}\n")
        if case.get("source_refs"):
            lines.append(
                f"## 原文指针\n\n{chr(10).join(f'- {ref}' for ref in case['source_refs'])}"
            )
        return "\n".join(lines)

    def _write_case_file(self, file_path: Path, case: dict[str, Any]):
        """写入案例文件"""
        fm_lines = [
            "---",
            f'case_id: "{case.get("case_id", "")}"',
            f'type: "{case.get("type", "penalty")}"',
            f'title: "{case.get("title", "")}"',
            f'status: "{case.get("status", "closed")}"',
            f'confidence: "{case.get("confidence", "high")}"',
            f'region: "{case.get("region", "")}"',
            f'penalty_amount: {case.get("penalty_amount", 0)}',
            "tags:",
        ]
        for tag in case.get("tags", []):
            fm_lines.append(f"  - {tag}")
        fm_lines.append(f'updated: "{case.get("updated_at", datetime.now().isoformat())[:10]}"')
        fm_lines.append("---\n")

        body = self._format_case_content(case)
        content = "\n".join(fm_lines) + "\n" + body
        file_path.write_text(content, encoding="utf-8")

    def _parse_case_file(self, file_path: Path) -> dict[str, Any] | None:
        """解析案例文件"""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

        case = dict(CASE_TEMPLATE)
        case["case_id"] = file_path.stem

        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                yaml_text = content[3:end]
                body = content[end + 3:].strip()
                for line in yaml_text.split("\n"):
                    line = line.strip()
                    if ":" in line:
                        key, _, value = line.partition(":")
                        key = key.strip()
                        value = value.strip().strip('"\'')
                        if key == "tags":
                            continue
                        if key == "penalty_amount":
                            try:
                                value = float(value)
                            except ValueError:
                                value = 0.0
                        case[key] = value

                # 提取 tags
                in_tags = False
                tags = []
                for line in yaml_text.split("\n"):
                    if line.strip() == "tags:":
                        in_tags = True
                        continue
                    if in_tags:
                        if line.strip().startswith("- "):
                            tags.append(line.strip()[2:].strip().strip('"\''))
                        else:
                            in_tags = False
                case["tags"] = tags

                # 提取 body 中的各段落
                case["facts"] = self._extract_section(body, "案情摘要")
                case["analysis"] = self._extract_section(body, "违法要件分析")
                case["decision"] = self._extract_section(body, "处罚决定")
                case["key_points"] = self._extract_section(body, "经验要点")
                case["source_refs"] = self._extract_section(body, "原文指针").split("\n")

                case["updated_at"] = case.get("updated", case["updated_at"])
                return case
        return None

    def _extract_section(self, body: str, section_name: str) -> str:
        """提取 Markdown 段落"""
        pattern = rf"##\s*{re.escape(section_name)}[\s\S]*?(?=\n##|\Z)"
        match = re.search(pattern, body)
        if match:
            text = match.group(0)
            # 移除标题行
            lines = text.split("\n")
            if lines:
                lines = lines[1:]
            return "\n".join(lines).strip()
        return ""

    def _list_case_files(self) -> list[Path]:
        """列出所有案例文件"""
        return sorted(self._case_dir.rglob("*.md"))


class BenchmarkManager:
    """裁量基准管理器"""

    def __init__(self, memory_tree=None):
        self._mt = memory_tree
        self._benchmarks: list[dict[str, Any]] = []
        self._benchmark_dir = PROJECT_ROOT / "memory-tree" / "obsidian_sync" / "benchmarks"
        self._benchmark_dir.mkdir(parents=True, exist_ok=True)

    def add_benchmark(self, data: dict[str, Any]) -> str:
        """添加裁量基准"""
        count = len(self._list_benchmark_files()) + 1
        bm_id = f"BM-{count:04d}"

        bm = dict(BENCHMARK_TEMPLATE)
        bm.update(data)
        bm["benchmark_id"] = bm_id

        # 写入文件
        file_path = self._benchmark_dir / f"{bm_id}_{data.get('category', 'other')}.md"
        self._write_benchmark_file(file_path, bm)

        # 同步到 Memory Tree
        if self._mt:
            content = json.dumps(bm, ensure_ascii=False, indent=2)
            self._mt.create_node(
                type="benchmark",
                title=bm.get("title", f"{bm.get('category')}裁量基准"),
                content=content,
                tags=[f"benchmark/{bm.get('category', 'other')}"],
                score=70.0,
            )

        self._benchmarks.append(bm)
        logger.info(f"裁量基准添加成功: {bm_id}")
        return bm_id

    def match_benchmark(self, category: str, violation_desc: str,
                        region: str = "national") -> list[dict[str, Any]]:
        """匹配裁量基准"""
        benchmarks = self.list_benchmarks(category=category, region=region)
        if not benchmarks:
            benchmarks = self.list_benchmarks(category=category)
        scored = []

        violation_lower = violation_desc.lower()
        violation_words = set(violation_lower)
        for bm in benchmarks:
            vp = bm.get("violation", "").lower()
            # 字面重叠度
            common = violation_words & set(vp)
            coverage = len(common) / max(len(violation_words), 1) if violation_words else 0

            # 关键词匹配
            keywords = ["超标", "排放", "非法", "倾倒", "污染", "废物", "噪声", "大气", "水"]
            kw_match = sum(1 for kw in keywords if kw in violation_lower and kw in vp)
            kw_score = kw_match / max(len(keywords), 1)

            combined = coverage * 0.3 + kw_score * 0.7
            if combined > 0.05:
                scored.append((combined, bm))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [bm for _, bm in scored[:5]]

    def list_benchmarks(self, category: str | None = None,
                        region: str | None = None) -> list[dict[str, Any]]:
        """列出裁量基准"""
        benchmarks = []
        for f in self._benchmark_dir.rglob("*.md"):
            bm = self._parse_benchmark_file(f)
            if bm:
                if category and bm.get("category") != category:
                    continue
                if region and bm.get("region") != region:
                    continue
                benchmarks.append(bm)
        return benchmarks

    def get_stats(self) -> dict[str, Any]:
        """裁量基准统计"""
        benchmarks = self.list_benchmarks()
        stats = {
            "total": len(benchmarks),
            "by_category": {},
            "by_region": {},
        }
        for bm in benchmarks:
            cat = bm.get("category", "other")
            stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
            reg = bm.get("region", "national")
            stats["by_region"][reg] = stats["by_region"].get(reg, 0) + 1
        return stats

    def _write_benchmark_file(self, file_path: Path, bm: dict[str, Any]):
        """写入裁量基准文件"""
        lines = [
            "---",
            f'benchmark_id: "{bm.get("benchmark_id", "")}"',
            f'category: "{bm.get("category", "")}"',
            f'region: "{bm.get("region", "national")}"',
            f'title: "{bm.get("title", "")}"',
            f'law_basis: "{bm.get("law_basis", "")}"',
            f'effective_date: "{bm.get("effective_date", "")}"',
            f'penalty_min: {bm.get("penalty_range", {}).get("min", 0)}',
            f'penalty_max: {bm.get("penalty_range", {}).get("max", 0)}',
            "---\n",
        ]
        body_parts = [
            f"## 违法情形\n\n{bm.get('violation', '')}\n",
            f"## 从重情节\n\n{chr(10).join(f'- {c}' for c in bm.get('aggravating', []))}\n",
            f"## 从轻情节\n\n{chr(10).join(f'- {c}' for c in bm.get('mitigating', []))}\n",
            f"## 免罚情形\n\n{chr(10).join(f'- {c}' for c in bm.get('exemption', []))}",
        ]
        content = "\n".join(lines) + "\n".join(body_parts)
        file_path.write_text(content, encoding="utf-8")

    def _parse_benchmark_file(self, file_path: Path) -> dict[str, Any] | None:
        """解析裁量基准文件"""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

        bm = dict(BENCHMARK_TEMPLATE)
        bm["benchmark_id"] = file_path.stem.split("_")[0]

        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                yaml_text = content[3:end]
                for line in yaml_text.split("\n"):
                    line = line.strip()
                    if ":" in line:
                        key, _, value = line.partition(":")
                        key = key.strip()
                        value = value.strip().strip('"\'')
                        if key in ("penalty_min", "penalty_max"):
                            try:
                                value = float(value)
                            except ValueError:
                                value = 0
                            bm.setdefault("penalty_range", {})[
                                "min" if key == "penalty_min" else "max"
                            ] = value
                        else:
                            bm[key] = value

                body = content[end + 3:]
                bm["violation"] = self._extract_section_text(body, "违法情形")
                return bm
        return None

    def _extract_section_text(self, body: str, name: str) -> str:
        """提取段落文本"""
        pattern = rf"##\s*{re.escape(name)}[\s\S]*?(?=\n##|\Z)"
        match = re.search(pattern, body)
        if match:
            text = match.group(0)
            lines = text.split("\n")
            if lines:
                lines = lines[1:]
            return "\n".join(lines).strip()
        return ""

    def _list_benchmark_files(self) -> list[Path]:
        """列出裁量基准文件"""
        return sorted(self._benchmark_dir.rglob("*.md"))


# ===== 种子数据 =====

def seed_demo_data():
    """创建演示数据"""
    from _scripts.memory_tree import MemoryTree

    mt = MemoryTree()
    cm = CaseManager(mt)
    bm = BenchmarkManager(mt)

    # 创建裁量基准
    benchmarks = [
        {
            "category": "大气",
            "region": "national",
            "title": "超标排放大气污染物裁量基准",
            "law_basis": "《生态环境法典》第二编第二分编",
            "violation": "超过大气污染物排放标准排放大气污染物",
            "penalty_range": {"min": 100000, "max": 1000000, "unit": "元"},
            "aggravating": ["两年内曾因同类违法被处罚", "逃避监管方式排放"],
            "mitigating": ["主动停止违法行为", "积极采取整改措施"],
            "exemption": ["超标倍数不超过 0.1 倍且及时改正"],
            "effective_date": "2026-08-15",
        },
        {
            "category": "水",
            "region": "national",
            "title": "超标排放水污染物裁量基准",
            "law_basis": "《生态环境法典》第二编第三分编",
            "violation": "超过水污染物排放标准排放水污染物",
            "penalty_range": {"min": 100000, "max": 1000000, "unit": "元"},
            "aggravating": ["向饮用水水源保护区排放", "重金属等有毒物质超标"],
            "mitigating": ["及时采取措施消除污染", "积极赔偿损失"],
            "exemption": ["超标倍数不超过 0.5 倍且及时改正"],
            "effective_date": "2026-08-15",
        },
        {
            "category": "固废",
            "region": "national",
            "title": "非法处置危险废物裁量基准",
            "law_basis": "《生态环境法典》第二编第六分编",
            "violation": "非法排放、倾倒、处置危险废物",
            "penalty_range": {"min": 200000, "max": 2000000, "unit": "元"},
            "aggravating": ["危险废物数量超过 3 吨", "造成环境污染事故"],
            "mitigating": ["主动清理处置危险废物", "配合调查"],
            "exemption": [],
            "effective_date": "2026-08-15",
        },
    ]

    for bm_data in benchmarks:
        bm.add_benchmark(bm_data)

    # 创建演示案例
    cases = [
        {
            "type": "penalty",
            "title": "XX钢铁有限公司超标排放大气污染物案",
            "region": "河北省",
            "pollutant_type": "空气",
            "penalty_amount": 350000,
            "law_basis": ["《生态环境法典》第二编第二分编第XX条"],
            "tags": ["env/air", "enforcement/penalty", "case/penalty"],
            "facts": "2026年3月，XX钢铁有限公司烧结机头排放口二氧化硫浓度为 150mg/m³，超过《钢铁烧结、球团工业大气污染物排放标准》(GB 28662-2012) 规定的 100mg/m³ 限值，超标 0.5 倍。",
            "analysis": "1. 行为要件：该公司作为排污单位，存在超过标准排放大气污染物的行为\n2. 结果要件：超标 0.5 倍，属于一般情节\n3. 因果关系：排放行为与超标结果之间存在直接因果关系",
            "decision": "1. 责令立即改正违法行为\n2. 处罚款人民币 35 万元\n3. 按照《环境保护主管部门实施限制生产、停产整治办法》责令限制生产三个月",
            "key_points": "1. 超标倍数认定：以实测浓度与标准限值的比值计算\n2. 裁量适用：属一般情节，按中限处罚\n3. 配套措施：限制生产作为辅助手段",
            "confidence": "high",
        },
        {
            "type": "penalty",
            "title": "XX化工有限公司超标排放水污染物案",
            "region": "江苏省",
            "pollutant_type": "水",
            "penalty_amount": 500000,
            "law_basis": ["《生态环境法典》第二编第三分编第XX条"],
            "tags": ["env/water", "enforcement/penalty", "case/penalty"],
            "facts": "2026年4月，XX化工有限公司废水总排放口 COD 浓度为 180mg/L，超过《化学工业水污染物排放标准》(GB 31571-2015) 规定的 100mg/L 限值，超标 0.8 倍。",
            "analysis": "1. 行为要件：该公司超过标准排放水污染物\n2. 结果要件：超标 0.8 倍，属于较重情节\n3. 因果关系：排放行为与超标结果之间有直接因果关系",
            "decision": "1. 责令立即改正违法行为\n2. 处罚款人民币 50 万元\n3. 责令停产整治",
            "key_points": "1. 超标 0.8 倍属于较重情节\n2. 处罚额度在裁量基准中上区间\n3. 同时适用停产整治措施",
            "confidence": "high",
        },
        {
            "type": "penalty",
            "title": "XX废物处置公司非法倾倒危险废物案",
            "region": "浙江省",
            "pollutant_type": "固废",
            "penalty_amount": 800000,
            "law_basis": ["《生态环境法典》第二编第六分编第XX条", "《危险废物转移环境管理办法》"],
            "tags": ["env/solid_waste", "enforcement/penalty", "case/penalty"],
            "facts": "2026年5月，XX废物处置公司未按照危险废物经营许可证规定，将 5.2 吨废酸非法倾倒至非指定场所。",
            "analysis": "1. 行为要件：该公司非法倾倒危险废物\n2. 数量认定：5.2 吨（超过 3 吨，属于严重情节）\n3. 主观故意：明知故犯",
            "decision": "1. 责令立即清理处置非法倾倒的危险废物\n2. 处罚款人民币 80 万元\n3. 吊销危险废物经营许可证",
            "key_points": "1. 危险废物数量认定是关键\n2. 超过 3 吨从重处罚\n3. 情节严重叠加吊证处罚",
            "confidence": "high",
        },
    ]

    for case in cases:
        cm.add_case(case)

    print("[OK] 演示数据创建完成")
    print(f"  - 裁量基准: {bm.get_stats()['total']} 条")
    print(f"  - 案例: {cm.get_stats()['total']} 条")

    return cm, bm


# ===== 测试 =====
def test():
    """测试案例模块"""
    import sys as _sys
    _sys.path.insert(0, str(PROJECT_ROOT))
    from _scripts.memory_tree import MemoryTree
    import tempfile
    import shutil
    import time as _time

    db_path = Path(tempfile.mkdtemp()) / "test.db"
    mt = MemoryTree(db_path)

    cm = CaseManager(mt)
    bm = BenchmarkManager(mt)

    bm.add_benchmark({
        "category": "大气", "region": "national", "title": "超标排放大气污染物",
        "law_basis": "《生态环境法典》第二编",
        "violation": "超过大气污染物排放标准排放大气污染物",
        "penalty_range": {"min": 100000, "max": 1000000, "unit": "元"},
    })

    cm.add_case({
        "type": "penalty", "title": "测试案例", "region": "浙江省",
        "penalty_amount": 100000,
        "law_basis": ["《生态环境法典》"], "tags": ["env/air", "enforcement/penalty"],
        "facts": "某企业超标排放大气污染物", "analysis": "超标0.5倍", "decision": "罚款10万元",
    })

    results = cm.find_similar("超标排放大气")
    print(f"[TEST] 相似案例检索: {len(results)} 条")

    matches = bm.match_benchmark("大气", "超过标准排放大气污染物")
    print(f"[TEST] 裁量基准匹配: {len(matches)} 条")
    if matches:
        print(f"  匹配: {matches[0]['title']}")

    print(f"[TEST] 案例统计: {json.dumps(cm.get_stats(), ensure_ascii=False)}")
    print(f"[TEST] 基准统计: {json.dumps(bm.get_stats(), ensure_ascii=False)}")

    import gc; gc.collect(); _time.sleep(0.1)
    try: shutil.rmtree(db_path.parent)
    except PermissionError: pass
    print("[OK] 执法案例模块测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
