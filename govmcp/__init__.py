#!/usr/bin/env python3
"""
govmcp — 国产信创MCP协议（对标国内等保合规）
=============================================

中国政务MCP (Model Context Protocol) 标准实现。
在标准MCP协议基础上增加国密加密、审批工作流、不可篡改审计链。

协议层:
- JSON-RPC 2.0 over stdio (兼容标准MCP)
- SM4 加密传输层 (govmcp独有)
- SM3 数据完整性校验 (govmcp独有)

实现状态（1.0）:
- 可用: crypto（SM2/SM3/SM4）、tools.registry（100+ 政务工具注册/调用）、
        server.approval（审批工作流）、protocol.server（核心骨架）
- 规划: authorization / elicitation / sampling / tasks / models / transport
        协议层模块（引用处已 try/except 隔离，补齐计划见 docs/ROADMAP-1.0.md）

产品矩阵:
- open-taiji    开源多智能体框架
- govmcp        国产信创MCP协议 ← 本包
- taiji-agent   政务智能体框架
- TaijiVerify   全球首创防虚幻技术
- TaijiHub      国产大模型API聚合网关

Author: Taiji Agent Team
License: Apache 2.0
"""

__version__ = "1.0.0"
__author__ = "Taiji Agent Team"
__license__ = "Apache 2.0"

# Lazy imports — each subpackage may not exist yet during incremental development.
# govmcp.crypto always available (core dependency).
from govmcp.crypto.audit import AuditChain, AuditEntry
from govmcp.crypto.sm import (
    generate_sm4_iv,
    generate_sm4_key,
    pkcs7_pad,
    pkcs7_unpad,
    sm3_hash,
    sm4_cbc_decrypt,
    sm4_cbc_encrypt,
    sm4_decrypt,
    sm4_encrypt,
)
from govmcp.crypto.sm2 import (
    generate_sm2_keypair,
    sm2_calculate_shared_secret,
    sm2_decrypt,
    sm2_derive_key,
    sm2_encrypt,
    sm2_sign,
    sm2_verify,
)

__all__ = [
    "sm3_hash",
    "sm4_encrypt",
    "sm4_decrypt",
    "sm4_cbc_encrypt",
    "sm4_cbc_decrypt",
    "generate_sm4_key",
    "generate_sm4_iv",
    "pkcs7_pad",
    "pkcs7_unpad",
    "AuditChain",
    "AuditEntry",
    "generate_sm2_keypair",
    "sm2_encrypt",
    "sm2_decrypt",
    "sm2_sign",
    "sm2_verify",
    "sm2_derive_key",
    "sm2_calculate_shared_secret",
]

try:
    from govmcp.protocol.server import GovMCPServer

    __all__.append("GovMCPServer")
except ImportError:
    pass

try:
    from govmcp.tools.registry import ToolRegistry, govmcp_tool

    __all__.extend(["ToolRegistry", "govmcp_tool"])
except ImportError:
    pass

try:
    from govmcp.server.approval import ApprovalFlow, ApprovalStatus

    __all__.extend(["ApprovalFlow", "ApprovalStatus"])
except ImportError:
    pass

try:
    from govmcp.models import (
        get_model,
        list_models,
        register_model,
        validate_model,
    )
    from govmcp.models.registry import LLMProvider, ModelConfig, ModelRegistry

    __all__.extend(
        [
            "LLMProvider",
            "ModelConfig",
            "ModelRegistry",
            "register_model",
            "get_model",
            "list_models",
            "validate_model",
        ]
    )
except ImportError:
    pass
