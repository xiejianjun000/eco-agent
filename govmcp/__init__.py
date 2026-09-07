#!/usr/bin/env python3
"""
govmcp — 国密加密与审计链（精简版）
=============================================

保留 eco-agent 实际依赖的两部分：
- crypto：SM2/SM3/SM4 国密算法 + 不可篡改审计链（trace_audit 等保台账地基）
- tools.registry：工具注册表与 @govmcp_tool 装饰器

已移除（2026-09，未被使用/不可达）：
- protocol / server / models：MCP 协议层与审批工作流骨架
- 各 *-mcp-server 子服务实现（github/eia/hunan-env/mee/pollution-permit）
- govmcp_tools：政务平台工具集（依赖内网域名与凭证，通用环境不可达）

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
    from govmcp.tools.registry import ToolRegistry, govmcp_tool  # noqa: F401

    __all__.extend(["ToolRegistry", "govmcp_tool"])
except ImportError:
    pass
