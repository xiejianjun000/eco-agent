"""
RAG Score - RAG质量评分器（vendored from taiji-verify, MIT License）

来源: https://github.com/xiejianjun000/taiji-verify
      src/taiji_verify/detection/rag_score.py (v2.2 Phase 1)
本地修改:
  - 移除 taiji_verify.embedding 的 TYPE_CHECKING 依赖（embedding_provider 参数保留 duck-typing）
  - _extract_claims 增加「含数字/条文号即视为声明」规则——法规场景的关键事实
    （罚款金额、条文号、期限）不一定含判断词，而幻觉恰恰藏在这些数据里
  - _extract_entities 数字实体正则支持中文数字（一二三十百千万）——
    原实现只认阿拉伯数字，中文数字编造的条款号/金额会完全逃逸检测
  - 本文件随 eco-agent 分发，遵循原项目 MIT 许可

核心概念：
- 对RAG（检索增强生成）输出进行质量评分
- 三个维度：忠实度、相关性、完整性
- 幻觉风险 = 1 - 忠实度

功能：
- Faithfulness: 答案是否忠实于检索上下文
- Relevance: 检索内容与查询的语义相关度
- Completeness: 答案是否完整覆盖问题
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np


class RAGScoreDimension(str, Enum):
    """
    RAG评分维度枚举

    - FAITHFULNESS: 忠实度，答案是否忠实于检索上下文
    - RELEVANCE: 相关性，检索内容与查询的语义相关度
    - COMPLETENESS: 完整性，答案是否完整覆盖查询的所有方面
    """

    FAITHFULNESS = "faithfulness"
    RELEVANCE = "relevance"
    COMPLETENESS = "completeness"


@dataclass
class RAGDimensionScore:
    """
    单维度评分

    Attributes:
        dimension: 评分维度
        score: 分数（0-1）
        details: 详细评分信息
    """

    dimension: RAGScoreDimension
    score: float
    details: dict = field(default_factory=dict)


@dataclass
class RAGScoreResult:
    """
    RAG评分结果

    存储RAG系统的完整评分结果，包括三个维度的分数和幻觉风险。

    Attributes:
        query: 用户查询
        answer: AI生成的答案
        contexts: 检索到的上下文列表
        dimension_scores: 各维度评分字典
        overall_score: 加权总分（0-1）
        faithfulness_score: 忠实度分数
        relevance_score: 相关性分数
        completeness_score: 完整性分数
        hallucination_risk: 幻觉风险（1 - faithfulness）
    """

    query: str
    answer: str
    contexts: list[str]
    dimension_scores: dict[str, RAGDimensionScore] = field(default_factory=dict)
    overall_score: float = 0.0
    faithfulness_score: float = 0.0
    relevance_score: float = 0.0
    completeness_score: float = 0.0
    hallucination_risk: float = 0.0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "query": self.query,
            "answer": self.answer,
            "contexts": self.contexts,
            "dimension_scores": {
                k: {"dimension": v.dimension.value, "score": v.score, "details": v.details}
                for k, v in self.dimension_scores.items()
            },
            "overall_score": self.overall_score,
            "faithfulness_score": self.faithfulness_score,
            "relevance_score": self.relevance_score,
            "completeness_score": self.completeness_score,
            "hallucination_risk": self.hallucination_risk,
        }

    @property
    def is_low_risk(self) -> bool:
        """是否为低幻觉风险"""
        return self.hallucination_risk < 0.3

    @property
    def is_medium_risk(self) -> bool:
        """是否为中等幻觉风险"""
        return 0.3 <= self.hallucination_risk < 0.6

    @property
    def is_high_risk(self) -> bool:
        """是否为高幻觉风险"""
        return self.hallucination_risk >= 0.6


class RAGScorer:
    """
    RAG质量评分器

    对RAG系统的输出进行多维度质量评估：
    - 忠实度：答案中的声明是否能在上下文中找到支撑
    - 相关性：检索到的内容与查询的语义匹配程度
    - 完整性：答案是否完整回答了查询的所有方面

    设计原则：
    - 忠实度权重最高（默认0.5），直接关联幻觉风险
    - 嵌入提供者用于语义相似度计算
    - 支持零依赖模式（使用字符级相似度）

    Usage:
        # 默认配置
        scorer = RAGScorer()
        result = scorer.score(
            query="什么是碳排放权交易？",
            answer="碳排放权交易是指...",
            contexts=["碳排放权交易管理办法...", "碳交易市场概述..."]
        )

        # 带嵌入提供者
        from taiji_verify.embedding import SimpleBagOfWordsProvider
        provider = SimpleBagOfWordsProvider(dimension=128)
        scorer = RAGScorer(embedding_provider=provider)
        result = scorer.score(query, answer, contexts)
    """

    # 默认权重配置
    DEFAULT_FAITHFULNESS_WEIGHT = 0.5
    DEFAULT_RELEVANCE_WEIGHT = 0.3
    DEFAULT_COMPLETENESS_WEIGHT = 0.2

    def __init__(
        self,
        embedding_provider=None,  # duck-typed：需提供 .embed(text) 方法
        faithfulness_weight: float = DEFAULT_FAITHFULNESS_WEIGHT,
        relevance_weight: float = DEFAULT_RELEVANCE_WEIGHT,
        completeness_weight: float = DEFAULT_COMPLETENESS_WEIGHT,
    ):
        """
        初始化RAG评分器

        Args:
            embedding_provider: 嵌入提供者（用于语义相似度计算）
            faithfulness_weight: 忠实度权重（默认0.5）
            relevance_weight: 相关性权重（默认0.3）
            completeness_weight: 完整性权重（默认0.2）
        """
        # 验证权重
        total_weight = faithfulness_weight + relevance_weight + completeness_weight
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(f"权重和必须为1.0，当前为 {total_weight}")

        self._embedding_provider = embedding_provider
        self._faithfulness_weight = faithfulness_weight
        self._relevance_weight = relevance_weight
        self._completeness_weight = completeness_weight

    def score(
        self,
        query: str,
        answer: str,
        contexts: list[str],
    ) -> RAGScoreResult:
        """
        完整RAG评分

        对RAG系统的三个维度进行评分。

        Args:
            query: 用户查询
            answer: AI生成的答案
            contexts: 检索到的上下文列表

        Returns:
            RAGScoreResult: 完整评分结果
        """
        # 计算各维度分数
        faithfulness = self.score_faithfulness(answer, contexts)
        relevance = self.score_relevance(query, contexts)
        completeness = self.score_completeness(query, answer)

        # 构建维度分数
        dimension_scores = {
            "faithfulness": RAGDimensionScore(
                dimension=RAGScoreDimension.FAITHFULNESS,
                score=faithfulness,
                details=self._get_faithfulness_details(answer, contexts),
            ),
            "relevance": RAGDimensionScore(
                dimension=RAGScoreDimension.RELEVANCE,
                score=relevance,
                details=self._get_relevance_details(query, contexts),
            ),
            "completeness": RAGDimensionScore(
                dimension=RAGScoreDimension.COMPLETENESS,
                score=completeness,
                details=self._get_completeness_details(query, answer),
            ),
        }

        # 计算加权总分
        overall_score = (
            faithfulness * self._faithfulness_weight
            + relevance * self._relevance_weight
            + completeness * self._completeness_weight
        )

        # 幻觉风险 = 1 - 忠实度
        hallucination_risk = 1.0 - faithfulness

        return RAGScoreResult(
            query=query,
            answer=answer,
            contexts=contexts,
            dimension_scores=dimension_scores,
            overall_score=overall_score,
            faithfulness_score=faithfulness,
            relevance_score=relevance,
            completeness_score=completeness,
            hallucination_risk=hallucination_risk,
        )

    def score_faithfulness(self, answer: str, contexts: list[str]) -> float:
        """
        忠实度评分

        评估答案中的声明是否能在上下文中找到支撑。
        方法：提取答案中的关键声明，检查是否在上下文中出现。

        Args:
            answer: AI生成的答案
            contexts: 检索到的上下文列表

        Returns:
            float: 忠实度分数（0-1）
        """
        if not answer or not contexts:
            return 0.0

        # 合并上下文
        combined_context = " ".join(contexts)

        # 提取答案中的关键声明
        claims = self._extract_claims(answer)

        if not claims:
            # 没有明确声明，保守给0.5分
            return 0.5

        # 检查每个声明是否在上下文中找到支撑
        supported_claims = 0
        for claim in claims:
            if self._is_supported(claim, combined_context):
                supported_claims += 1

        return supported_claims / len(claims) if claims else 0.5

    def score_relevance(self, query: str, contexts: list[str]) -> float:
        """
        相关性评分

        评估检索到的内容与查询的语义相关度。

        Args:
            query: 用户查询
            contexts: 检索到的上下文列表

        Returns:
            float: 相关性分数（0-1）
        """
        if not query or not contexts:
            return 0.0

        # 合并上下文
        combined_context = " ".join(contexts)

        # 提取查询关键词
        query_keywords = self._extract_keywords(query)

        if not query_keywords:
            return 0.5

        # 计算关键词覆盖率
        context_keywords = self._extract_keywords(combined_context)
        coverage = len(query_keywords & context_keywords) / len(query_keywords)

        # 计算语义相似度
        if self._embedding_provider:
            try:
                query_vec = self._embedding_provider.embed(query)
                context_vec = self._embedding_provider.embed(combined_context)
                semantic_sim = float(
                    np.dot(query_vec, context_vec)
                    / (np.linalg.norm(query_vec) * np.linalg.norm(context_vec))
                )
                # 综合评分
                return 0.4 * coverage + 0.6 * max(0.0, semantic_sim)
            except Exception:
                pass

        # 降级：仅使用关键词覆盖
        return coverage

    def score_completeness(self, query: str, answer: str) -> float:
        """
        完整性评分

        评估答案是否完整覆盖查询的所有方面。

        Args:
            query: 用户查询
            answer: AI生成的答案

        Returns:
            float: 完整性分数（0-1）
        """
        if not query or not answer:
            return 0.0

        # 识别查询中的问询类型
        query_types = self._identify_query_types(query)

        # 检查答案是否覆盖各种问询类型
        covered_types = 0
        for _qtype, patterns in query_types.items():
            if any(pattern in answer for pattern in patterns):
                covered_types += 1

        # 计算类型覆盖率
        type_coverage = covered_types / len(query_types) if query_types else 0.5

        # 检查答案长度是否与查询复杂度匹配
        query_complexity = len(query)
        answer_length = len(answer)
        length_ratio = answer_length / (query_complexity * 3) if query_complexity > 0 else 0
        length_score = min(1.0, length_ratio)

        # 综合评分
        return 0.6 * type_coverage + 0.4 * length_score

    def _extract_claims(self, text: str) -> list[str]:
        """
        提取文本中的关键声明

        使用规则识别可能的声明句子。

        Args:
            text: 待提取文本

        Returns:
            list[str]: 声明列表
        """
        # 分割句子
        sentences = re.split(r"[。；！？\n]", text)
        claims = []

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # 检查是否为声明性句子（包含判断性词语）
            claim_indicators = [
                "是",
                "为",
                "指",
                "表示",
                "认为",
                "包括",
                "属于",
                "具有",
                "可以",
                "应该",
                "必须",
                "需要",
                "规定",
                "实现",
                "达到",
            ]

            if any(indicator in sentence for indicator in claim_indicators):
                # 检查长度（排除过短或过长的句子）
                if 5 <= len(sentence) <= 200:
                    claims.append(sentence)
                continue

            # 法规场景补丁：含数字/条文号的句子视为声明
            # （罚款金额、条文号、期限等关键事实不一定含判断词，而幻觉恰恰藏在这些数据里）
            if 5 <= len(sentence) <= 200 and (
                re.search(r"\d", sentence) or re.search(r"第[一二三四五六七八九十百千\d]+[条章节款]", sentence)
            ):
                claims.append(sentence)

        return claims

    def _is_supported(self, claim: str, context: str) -> bool:
        """
        检查声明是否被上下文支撑

        Args:
            claim: 声明文本
            context: 上下文文本

        Returns:
            bool: 是否被支撑
        """
        # 提取声明中的关键实体
        claim_entities = self._extract_entities(claim)

        if not claim_entities:
            # 如果没有实体，检查关键词重叠
            claim_keywords = set(self._extract_keywords(claim))
            context_keywords = set(self._extract_keywords(context))
            overlap = (
                len(claim_keywords & context_keywords) / len(claim_keywords)
                if claim_keywords
                else 0
            )
            return overlap >= 0.3

        # 检查实体是否在上下文中
        return all(entity in context for entity in claim_entities)

    def _extract_entities(self, text: str) -> set[str]:
        """
        提取文本中的实体

        识别专有名词、数字+单位等实体。

        Args:
            text: 待提取文本

        Returns:
            set[str]: 实体集合
        """
        entities = set()

        # 数字+单位组合（含中文数字：八百八十八条 / 五百万元 / 十年）
        units = re.findall(r"[零一二三四五六七八九十百千万亿两\d]+(?:\.\d+)?[万千百亿]?[元吨年月日%人个家次条项部]", text)
        entities.update(units)

        # 法规名称
        laws = re.findall(r"《[^》]+》", text)
        entities.update(laws)

        # 中文专有名词（2-4字）
        chinese_terms = re.findall(
            r"[\u4e00-\u9fa5]{2,4}(?:法|条例|规定|标准|办法|制度|体系|机制)", text
        )
        entities.update(chinese_terms)

        return entities

    def _extract_keywords(self, text: str) -> set[str]:
        """
        提取关键词

        Args:
            text: 待提取文本

        Returns:
            set[str]: 关键词集合
        """
        # 中文词（2-4字）
        chinese = set(re.findall(r"[\u4e00-\u9fa5]{2,4}", text))

        # 英文词
        english = set(re.findall(r"[a-zA-Z]{3,}", text.lower()))

        return chinese | english

    def _identify_query_types(self, query: str) -> dict[str, list[str]]:
        """
        识别查询类型

        Args:
            query: 查询文本

        Returns:
            dict[str, list[str]]: 查询类型及其匹配模式
        """
        types = {}

        # 定义问询类型模式
        type_patterns = {
            "definition": ["什么", "什么是", "含义", "定义"],
            "reason": ["为什么", "原因", "为何"],
            "method": ["如何", "怎么", "怎样", "方法", "途径"],
            "comparison": ["区别", "不同", "比较", "对比"],
            "process": ["流程", "步骤", "程序", "过程"],
            "condition": ["条件", "要求", "标准"],
            "scope": ["范围", "领域", "包括"],
            "time": ["时间", "时候", "期间"],
        }

        for qtype, patterns in type_patterns.items():
            if any(p in query for p in patterns):
                types[qtype] = patterns

        return types

    def _get_faithfulness_details(self, answer: str, contexts: list[str]) -> dict:
        """获取忠实度详细评分信息"""
        claims = self._extract_claims(answer)
        combined_context = " ".join(contexts)

        supported = []
        unsupported = []

        for claim in claims:
            if self._is_supported(claim, combined_context):
                supported.append(claim[:50] + "..." if len(claim) > 50 else claim)
            else:
                unsupported.append(claim[:50] + "..." if len(claim) > 50 else claim)

        return {
            "total_claims": len(claims),
            "supported_claims": len(supported),
            "unsupported_claims": len(unsupported),
            "sample_supported": supported[:3],
            "sample_unsupported": unsupported[:3],
        }

    def _get_relevance_details(self, query: str, contexts: list[str]) -> dict:
        """获取相关性详细评分信息"""
        query_keywords = self._extract_keywords(query)
        combined_context = " ".join(contexts)
        context_keywords = self._extract_keywords(combined_context)

        matched = query_keywords & context_keywords
        unmatched = query_keywords - context_keywords

        details = {
            "query_keywords": len(query_keywords),
            "matched_keywords": len(matched),
            "unmatched_keywords": list(unmatched)[:5],
        }

        if self._embedding_provider:
            details["semantic_similarity"] = "computed"

        return details

    def _get_completeness_details(self, query: str, answer: str) -> dict:
        """获取完整性详细评分信息"""
        query_types = self._identify_query_types(query)
        covered_types = []

        for _qtype, patterns in query_types.items():
            if any(pattern in answer for pattern in patterns):
                covered_types.append(_qtype)

        return {
            "query_types": list(query_types.keys()),
            "covered_types": covered_types,
            "uncovered_types": list(set(query_types.keys()) - set(covered_types)),
            "answer_length": len(answer),
            "query_length": len(query),
        }

    @property
    def weights(self) -> tuple[float, float, float]:
        """获取各维度权重"""
        return (
            self._faithfulness_weight,
            self._relevance_weight,
            self._completeness_weight,
        )
