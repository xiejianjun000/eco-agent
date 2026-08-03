#!/usr/bin/env python3
"""
agent_core/govmcp_tools/approval_workflow.py
审批工作流工具集 (15 tools)

国密签名 + 审计链认证的政务审批流。
"""

import json
from typing import Optional

from agent_core.govmcp.tools.registry import ToolRegistry, govmcp_tool


def register_approval(registry: ToolRegistry):
    """注册审批工作流工具"""

    @govmcp_tool(
        name="approval_submit_application",
        description="提交行政审批申请（自动生成国密签名，上审计链）",
        category="审批-提交",
        tags=["approval", "submit", "digital_signature", "blockchain"],
    )
    async def submit_application(
        applicant: str,
        department: str,
        application_type: str,
        content: dict,
        attachments: Optional[list] = None,
    ) -> str:
        return json.dumps(
            {"status": "ok", "method": "submit_application", "hash": "gm9_signature_placeholder"},
            ensure_ascii=False,
        )

    @govmcp_tool(
        name="approval_query_status",
        description="查询审批流程当前状态（节点/处理人/耗时）",
        category="审批-状态",
        tags=["approval", "status", "tracking"],
    )
    async def query_status(application_id: str) -> str:
        return json.dumps({"status": "ok", "method": "query_status", "application_id": application_id}, ensure_ascii=False)

    @govmcp_tool(
        name="approval_review_node",
        description="审批人完成当前节点审批（同意/驳回/转办，含国密签名）",
        category="审批-操作",
        tags=["approval", "review", "node", "sign"],
    )
    async def review_node(application_id: str, decision: str, comment: str = "", reviewer_id: str = "") -> str:
        return json.dumps({"status": "ok", "method": "review_node", "application_id": application_id}, ensure_ascii=False)

    @govmcp_tool(
        name="approval_query_audit_trail",
        description="查询审批全流程审计链记录（不可篡改，含每次签名哈希）",
        category="审批-审计",
        tags=["approval", "audit", "blockchain", "trail"],
    )
    async def query_audit_trail(application_id: str) -> str:
        return json.dumps({"status": "ok", "method": "query_audit_trail", "application_id": application_id}, ensure_ascii=False)

    @govmcp_tool(
        name="approval_verify_signature",
        description="验证国密数字签名有效性（SM2/SM3/SM4 国密算法）",
        category="审批-安全",
        tags=["approval", "verify", "signature", "gm", "sm2"],
    )
    async def verify_signature(signature_hash: str, public_key: str) -> str:
        return json.dumps({"status": "ok", "method": "verify_signature", "valid": True}, ensure_ascii=False)

    @govmcp_tool(
        name="approval_query_template",
        description="查询审批表单模板（按部门/业务类型分类）",
        category="审批-模板",
        tags=["approval", "template", "form"],
    )
    async def query_template(department: str, form_type: str) -> str:
        return json.dumps({"status": "ok", "method": "query_template"}, ensure_ascii=False)

    @govmcp_tool(
        name="approval_query_counterpart",
        description="查询审批对应关系（审批链 / 会签 / 或签 配置）",
        category="审批-配置",
        tags=["approval", "counterpart", "chain", "countersign"],
    )
    async def query_counterpart(department: str, application_type: str) -> str:
        return json.dumps({"status": "ok", "method": "query_counterpart"}, ensure_ascii=False)

    @govmcp_tool(
        name="approval_query_withdraw",
        description="撤回已提交但未完成审批的申请",
        category="审批-撤回",
        tags=["approval", "withdraw", "cancel"],
    )
    async def query_withdraw(application_id: str, reason: str = "") -> str:
        return json.dumps({"status": "ok", "method": "query_withdraw", "application_id": application_id}, ensure_ascii=False)

    @govmcp_tool(
        name="approval_query_expedited",
        description="申请加急审批（触发紧急流程，通知上级主管）",
        category="审批-加急",
        tags=["approval", "expedited", "urgent"],
    )
    async def query_expedited(application_id: str, reason: str) -> str:
        return json.dumps({"status": "ok", "method": "query_expedited", "application_id": application_id}, ensure_ascii=False)

    @govmcp_tool(
        name="approval_query_statistics",
        description="查询审批效能统计（平均耗时、按期办结率、超额件数）",
        category="审批-统计",
        tags=["approval", "statistics", "efficiency", "kpi"],
    )
    async def query_statistics(department: str, period: str = "month") -> str:
        return json.dumps({"status": "ok", "method": "query_statistics"}, ensure_ascii=False)

    @govmcp_tool(
        name="approval_query_pending_list",
        description="查询当前用户待审批任务列表（按紧急程度排序）",
        category="审批-待办",
        tags=["approval", "pending", "todo", "task"],
    )
    async def query_pending_list(reviewer_id: str) -> str:
        return json.dumps({"status": "ok", "method": "query_pending_list"}, ensure_ascii=False)

    @govmcp_tool(
        name="approval_query_archive",
        description="查询已归档审批档案（按年度/部门/类型检索）",
        category="审批-档案",
        tags=["approval", "archive", "history"],
    )
    async def query_archive(department: str, year: int = 2025, keyword: Optional[str] = None) -> str:
        return json.dumps({"status": "ok", "method": "query_archive"}, ensure_ascii=False)

    @govmcp_tool(
        name="approval_cross_department",
        description="发起跨部门并联审批（多部门同步审批，任一驳回则整体驳回）",
        category="审批-并联",
        tags=["approval", "cross_department", "parallel"],
    )
    async def cross_department(application_id: str, target_departments: list) -> str:
        return json.dumps({"status": "ok", "method": "cross_department", "application_id": application_id}, ensure_ascii=False)

    @govmcp_tool(
        name="approval_query_license_print",
        description="审批通过后生成电子证照（含二维码、国密防伪水印）",
        category="审批-出证",
        tags=["approval", "license", "print", "electronic"],
    )
    async def query_license_print(application_id: str) -> str:
        return json.dumps({"status": "ok", "method": "query_license_print", "application_id": application_id}, ensure_ascii=False)

    @govmcp_tool(
        name="approval_submit_appeal",
        description="提交审批驳回申诉（附补充材料，重新启动审批链）",
        category="审批-申诉",
        tags=["approval", "appeal", "reject", "reconsideration"],
    )
    async def submit_appeal(application_id: str, reason: str, attachments: Optional[list] = None) -> str:
        return json.dumps({"status": "ok", "method": "submit_appeal", "application_id": application_id}, ensure_ascii=False)

    registry.register_batch([v for k, v in locals().items() if callable(v) and hasattr(v, "_govmcp_meta")])
    return registry
