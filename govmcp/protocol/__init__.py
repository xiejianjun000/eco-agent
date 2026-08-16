#!/usr/bin/env python3
"""
govmcp.protocol — JSON-RPC 2.0 协议层

提供 GovMCPServer 核心类，实现标准 MCP 协议及 govmcp 扩展特性。
"""

from govmcp.protocol.authorization import (
    AuthorizationCode,
    AuthorizationManager,
    AuthorizationScope,
    ClientInfo,
    FineGrainedPermissionManager,
    GrantType,
    Permission,
    TokenInfo,
    TokenType,
)
from govmcp.protocol.elicitation import (
    ConsoleElicitationHandler,
    ElicitationManager,
    ElicitRequest,
    ElicitResponse,
    ElicitStatus,
    ElicitType,
    URLElicitation,
    create_secure_prompt_request,
)
from govmcp.protocol.sampling import (
    EmbeddedSamplingProvider,
    SamplingCreateMessageRequest,
    SamplingManager,
    SamplingMessage,
    SamplingParameters,
    SamplingResponse,
    create_sampling_request,
)
from govmcp.protocol.server import GovMCPServer
from govmcp.protocol.tasks import (
    SSEHandler,
    TaskCancelError,
    TaskInfo,
    TaskManager,
    TaskNotFoundError,
    TaskStatus,
    TaskSubscriber,
    create_sse_response,
)

__all__ = [
    "GovMCPServer",
    "TaskManager",
    "TaskStatus",
    "TaskInfo",
    "TaskSubscriber",
    "TaskNotFoundError",
    "TaskCancelError",
    "create_sse_response",
    "SSEHandler",
    "SamplingManager",
    "SamplingMessage",
    "SamplingCreateMessageRequest",
    "SamplingResponse",
    "SamplingParameters",
    "EmbeddedSamplingProvider",
    "create_sampling_request",
    "ElicitationManager",
    "ElicitRequest",
    "ElicitResponse",
    "ElicitType",
    "ElicitStatus",
    "URLElicitation",
    "ConsoleElicitationHandler",
    "create_secure_prompt_request",
    "AuthorizationManager",
    "FineGrainedPermissionManager",
    "GrantType",
    "TokenType",
    "Permission",
    "AuthorizationScope",
    "ClientInfo",
    "AuthorizationCode",
    "TokenInfo",
]
