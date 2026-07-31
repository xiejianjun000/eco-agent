#!/usr/bin/env python3
"""
govmcp.protocol.server — GovMCPServer

JSON-RPC 2.0 over stdio 协议层，叠加 govmcp 独有特性：
  - SM4 加密传输层（可选，CBC 模式，PKCS7 填充）
  - SM3 数据完整性校验（每条消息附带哈希）
  - 信创模型注册（48 个国产 LLM）
  - 审批工作流集成（预留接口）
  - 多传输层支持（Stdio/WebSocket/HTTP/SSE）

兼容标准 MCP 的 initialize / tools/list / tools/call / resources/list / prompts/list 方法。
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from typing import Any
from collections.abc import Callable

from govmcp.crypto.sm import generate_sm4_key, sm3_hash, sm4_decrypt, sm4_encrypt

try:
    from govmcp.protocol.http_server import HTTPRequest, HTTPResponse, HTTPServer
    from govmcp.protocol.websocket_server import WebSocketServer
    from govmcp.transport import (
        HTTPTransport,
        StdioTransport,
        Transport,
        TransportConfig,
        TransportType,
        WebSocketTransport,
    )

    WEBSOCKET_AVAILABLE = True
    HTTP_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    HTTP_AVAILABLE = False
    WebSocketServer = None
    HTTPServer = None
    HTTPRequest = None
    HTTPResponse = None
    Transport = object
    TransportType = None
    TransportConfig = None
    StdioTransport = None
    WebSocketTransport = None
    HTTPTransport = None

from govmcp.protocol.authorization import (
    AuthorizationManager,
    AuthorizationScope,
    FineGrainedPermissionManager,
    GrantType,
    Permission,
    TokenType,
)
from govmcp.protocol.elicitation import (
    ElicitationManager,
    ElicitRequest,
    ElicitResponse,
    ElicitStatus,
    ElicitType,
    URLElicitation,
)
from govmcp.protocol.sampling import (
    SamplingCreateMessageRequest,
    SamplingManager,
    SamplingMessage,
    SamplingResponse,
)
from govmcp.protocol.tasks import (
    SSEHandler,
    TaskInfo,
    TaskManager,
    TaskStatus,
    TaskSubscriber,
    create_sse_response,
)

XINCHUANG_MODELS: list[str] = [
    "ernie-4.0",
    "ernie-3.5",
    "ernie-3.0",
    "ernie-bot",
    "qwen-turbo",
    "qwen-plus",
    "qwen-max",
    "qwen-long",
    "qwen-7b",
    "qwen-14b",
    "qwen-72b",
    "glm-4",
    "glm-4-plus",
    "glm-3-turbo",
    "chatglm-6b",
    "chatglm2-6b",
    "chatglm3-6b",
    "spark-3.5",
    "spark-4.0",
    "spark-lite",
    "hunyuan-lite",
    "hunyuan-pro",
    "hunyuan-standard",
    "pangu-alpha",
    "pangu-chat",
    "doubao-pro",
    "doubao-lite",
    "360gpt-pro",
    "360gpt-lite",
    "minimax-abab5",
    "minimax-abab6",
    "minimax-chat",
    "sensechat-5",
    "sensechat-4",
    "kimi-chat",
    "kimi-pro",
    "baichuan4",
    "baichuan-7b",
    "baichuan-13b",
    "qizhi-chat",
    "tuoshai-chat",
    "wandao-chat",
    "wenda-chat",
    "internlm-chat",
    "internlm2-chat",
    "mindchat",
    "ctyun-chat",
    "unicom-chat",
]

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603


def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    """PKCS#7 填充"""
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes, block_size: int = 16) -> bytes:
    """去除 PKCS#7 填充"""
    if not data:
        raise ValueError("无法对空数据去除填充")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > block_size:
        raise ValueError(f"无效的 PKCS#7 填充字节: {pad_len}")
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        raise ValueError("PKCS#7 填充校验失败")
    return data[:-pad_len]


def _json_serialize(obj: Any) -> str:
    """规范化的 JSON 序列化，用于 SM3 哈希计算"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class GovMCPServer:
    """
    GovMCPServer — 国产信创 MCP 协议服务器

    实现 JSON-RPC 2.0，兼容标准 MCP 协议，
    并叠加 govmcp 独有的 SM4 加密传输层和 SM3 数据完整性校验。
    支持多种传输方式: Stdio, WebSocket, HTTP/SSE。

    用法:
        server = GovMCPServer("my-gov-server", "1.0.0", crypto_enabled=True)

        @server.tool("greet", description="打招呼", input_schema={...})
        def greet(name: str) -> str:
            return f"你好, {name}!"

        server.run()  # 启动 stdio 消息循环

        # 或者启动 WebSocket 服务器:
        asyncio.run(server.run_websocket(host="0.0.0.0", port=8080))

        # 或者启动 HTTP 服务器:
        asyncio.run(server.run_http(host="0.0.0.0", port=8080))
    """

    def __init__(
        self,
        name: str,
        version: str,
        crypto_enabled: bool = False,
        sm4_key: bytes | None = None,
    ) -> None:
        """
        初始化 GovMCPServer。

        Args:
            name: 服务器名称
            version: 服务器版本号
            crypto_enabled: 是否启用 SM4 传输加密（默认 False）
            sm4_key: SM4 密钥（16字节）；为 None 时自动生成
        """
        self.name = name
        self.version = version
        self.crypto_enabled = crypto_enabled
        self.sm4_key: bytes = sm4_key if sm4_key else generate_sm4_key()

        self._tools: dict[str, dict[str, Any]] = {}
        self._resources: dict[str, dict[str, Any]] = {}
        self._prompts: dict[str, dict[str, Any]] = {}
        self._models: list[str] = list(XINCHUANG_MODELS)

        self._initialized: bool = False

        self._approval_handler: Callable[[str, dict[str, Any]], bool] | None = None

        if TaskManager is not None:
            self._task_manager: TaskManager = TaskManager()
            self._sampling_manager: SamplingManager = SamplingManager()
            self._elicitation_manager: ElicitationManager = ElicitationManager()
            self._authorization_manager: AuthorizationManager = AuthorizationManager()
            self._permission_manager: FineGrainedPermissionManager = FineGrainedPermissionManager(
                self._authorization_manager
            )
        else:
            self._task_manager = None
            self._sampling_manager = None
            self._elicitation_manager = None
            self._authorization_manager = None
            self._permission_manager = None

        self._event_loop: asyncio.AbstractEventLoop | None = None

        self._ws_server: WebSocketServer | None = None
        self._http_server: HTTPServer | None = None

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        """注册一个工具。"""
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
            "handler": handler,
        }

    def register_resource(
        self,
        uri: str,
        name: str,
        description: str,
        mime_type: str,
        handler: Callable[[str], Any],
    ) -> None:
        """注册一个资源。"""
        self._resources[uri] = {
            "uri": uri,
            "name": name,
            "description": description,
            "mimeType": mime_type,
            "handler": handler,
        }

    def register_prompt(
        self,
        name: str,
        description: str,
        arguments: list[dict[str, Any]],
        handler: Callable[..., Any],
    ) -> None:
        """注册一个提示模板。"""
        self._prompts[name] = {
            "name": name,
            "description": description,
            "arguments": arguments,
            "handler": handler,
        }

    def tool(
        self,
        name: str = None,
        *,
        description: str = "",
        input_schema: dict[str, Any] = None,
    ):
        """工具注册装饰器。@server.tool(...)"""

        def decorator(func):
            tool_name = name if name is not None else func.__name__
            schema = input_schema or {"type": "object", "properties": {}}
            self.register_tool(tool_name, description, schema, func)
            return func

        return decorator

    def resource(
        self,
        uri: str = None,
        *,
        name: str = "",
        description: str = "",
        mime_type: str = "text/plain",
    ):
        """资源注册装饰器。@server.resource(...)"""

        def decorator(func):
            resource_uri = uri if uri is not None else f"resources://{func.__name__}"
            self.register_resource(resource_uri, name, description, mime_type, func)
            return func

        return decorator

    def prompt(
        self,
        name: str = None,
        *,
        description: str = "",
        arguments: list[dict[str, Any]] = None,
    ):
        """提示模板注册装饰器。@server.prompt(...)"""

        def decorator(func):
            prompt_name = name if name is not None else func.__name__
            self.register_prompt(prompt_name, description, arguments or [], func)
            return func

        return decorator

    def register_model(self, model_name: str) -> None:
        """注册一个额外的信创模型"""
        if model_name not in self._models:
            self._models.append(model_name)

    def set_approval_handler(self, handler: Callable[[str, dict[str, Any]], bool]) -> None:
        """设置审批处理器。"""
        self._approval_handler = handler

    def _check_approval(self, tool_name: str, params: dict[str, Any]) -> bool:
        """检查工具调用是否需要审批。无处理器时默认放行。"""
        if self._approval_handler is None:
            return True
        try:
            return self._approval_handler(tool_name, params)
        except Exception:
            return False

    def _read_message(self) -> dict[str, Any] | None:
        """从 stdin 读取一行消息。"""
        line = sys.stdin.readline()
        if not line:
            return None

        raw = line.strip()
        if not raw:
            return None

        try:
            if self.crypto_enabled:
                ciphertext = base64.b64decode(raw)
                plaintext = _pkcs7_unpad(sm4_decrypt(ciphertext, self.sm4_key))
                raw = plaintext.decode("utf-8")
            return json.loads(raw)
        except (ValueError, json.JSONDecodeError, base64.binascii.Error) as exc:
            raise ValueError(f"消息解析失败: {exc}") from exc

    def _write_message(self, message: dict[str, Any]) -> None:
        """将消息写出到 stdout。"""
        payload_str = _json_serialize(message)
        sm3_val = sm3_hash(payload_str.encode("utf-8"))
        message["_sm3"] = sm3_val

        output = _json_serialize(message)

        if self.crypto_enabled:
            plaintext = output.encode("utf-8")
            padded = _pkcs7_pad(plaintext)
            ciphertext = sm4_encrypt(padded, self.sm4_key)
            output = base64.b64encode(ciphertext).decode("ascii")

        sys.stdout.write(output + "\n")
        sys.stdout.flush()

    def _jsonrpc_error(self, req_id: Any, code: int, message: str) -> dict[str, Any]:
        """构造 JSON-RPC 2.0 错误响应"""
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }

    def _jsonrpc_response(self, req_id: Any, result: Any) -> dict[str, Any]:
        """构造 JSON-RPC 2.0 成功响应"""
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """处理单个 JSON-RPC 请求并返回响应"""
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        try:
            result = self._dispatch(method, params)
            return self._jsonrpc_response(req_id, result)
        except Exception as exc:
            return self._jsonrpc_error(req_id, JSONRPC_INTERNAL_ERROR, str(exc))

    def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        """JSON-RPC 方法路由"""
        handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "initialize": self._mcp_initialize,
            "tools/list": self._mcp_tools_list,
            "tools/call": self._mcp_tools_call,
            "resources/list": self._mcp_resources_list,
            "resources/read": self._mcp_resources_read,
            "prompts/list": self._mcp_prompts_list,
            "prompts/get": self._mcp_prompts_get,
            "models/list": self._mcp_models_list,
            "sm3/verify": self._mcp_sm3_verify,
            "tasks/create": self._mcp_tasks_create,
            "tasks/status": self._mcp_tasks_status,
            "tasks/result": self._mcp_tasks_result,
            "tasks/cancel": self._mcp_tasks_cancel,
            "tasks/list": self._mcp_tasks_list,
            "tasks/subscribe": self._mcp_tasks_subscribe,
            "sampling/createMessage": self._mcp_sampling_create_message,
            "elicitation/create": self._mcp_elicitation_create,
            "elicitation/respond": self._mcp_elicitation_respond,
            "authorization/check": self._mcp_authorization_check,
        }

        handler = handlers.get(method)
        if handler is None:
            raise ValueError(f"Method not found: {method}")
        return handler(params)

    def _mcp_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """initialize — 初始化握手"""
        self._initialized = True
        return {
            # 回显客户端请求的协议版本以协商兼容（官方 MCP SDK 严格校验版本）；
            # 客户端未声明时回退到广泛支持的 2024-11-05
            "protocolVersion": params.get("protocolVersion") or "2024-11-05",
            "serverInfo": {
                "name": self.name,
                "version": self.version,
            },
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {},
                "models": {},
                "crypto": {
                    "sm3": True,
                    "sm4": self.crypto_enabled,
                },
                "tasks": {
                    "supported": True,
                    "progress": True,
                },
                "sampling": {
                    "supported": True,
                },
                "elicitation": {
                    "supported": True,
                },
                "authorization": {
                    "supported": True,
                    "oauth2": True,
                },
            },
        }

    def _mcp_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """tools/list — 列出所有已注册工具"""
        tools = []
        for t in self._tools.values():
            tools.append(
                {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": t["inputSchema"],
                }
            )
        return {"tools": tools}

    def _mcp_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """tools/call — 调用指定工具"""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")

        if not self._check_approval(tool_name, arguments):
            raise PermissionError(f"审批未通过，工具调用被拒绝: {tool_name}")

        result = tool["handler"](**arguments)

        if isinstance(result, (dict, list)):
            text = json.dumps(result, ensure_ascii=False)
        else:
            text = str(result)

        return {
            "content": [{"type": "text", "text": text}],
            "isError": False,
        }

    def _mcp_resources_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """resources/list — 列出所有已注册资源"""
        resources = []
        for r in self._resources.values():
            resources.append(
                {
                    "uri": r["uri"],
                    "name": r["name"],
                    "description": r["description"],
                    "mimeType": r["mimeType"],
                }
            )
        return {"resources": resources}

    def _mcp_resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        """resources/read — 读取指定资源"""
        uri = params.get("uri", "")
        resource = self._resources.get(uri)
        if not resource:
            raise ValueError(f"Resource not found: {uri}")

        content = resource["handler"](uri)
        if isinstance(content, (dict, list)):
            text = json.dumps(content, ensure_ascii=False)
        else:
            text = str(content)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": resource["mimeType"],
                    "text": text,
                }
            ]
        }

    def _mcp_prompts_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """prompts/list — 列出所有已注册提示模板"""
        prompts = []
        for p in self._prompts.values():
            prompts.append(
                {
                    "name": p["name"],
                    "description": p["description"],
                    "arguments": p["arguments"],
                }
            )
        return {"prompts": prompts}

    def _mcp_prompts_get(self, params: dict[str, Any]) -> dict[str, Any]:
        """prompts/get — 获取提示模板内容"""
        prompt_name = params.get("name", "")
        prompt_args = params.get("arguments", {})

        prompt = self._prompts.get(prompt_name)
        if not prompt:
            raise ValueError(f"Prompt not found: {prompt_name}")

        messages = prompt["handler"](**prompt_args)
        return {"messages": messages}

    def _mcp_models_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """models/list — 列出信创模型（govmcp 扩展）"""
        return {"models": self._models}

    def _mcp_sm3_verify(self, params: dict[str, Any]) -> dict[str, Any]:
        """sm3/verify — SM3 数据完整性验证（govmcp 扩展）"""
        data = params.get("data", "")
        expected_hash = params.get("hash", "")
        data_bytes = data.encode("utf-8") if isinstance(data, str) else data
        actual_hash = sm3_hash(data_bytes)
        return {
            "verified": actual_hash == expected_hash,
            "expected": expected_hash,
            "actual": actual_hash,
        }

    def _mcp_tasks_create(self, params: dict[str, Any]) -> dict[str, Any]:
        """tasks/create — 创建异步任务"""
        tool_name = params.get("toolName", "")
        arguments = params.get("arguments", {})
        timeout = params.get("timeout")
        metadata = params.get("metadata", {})

        if tool_name not in self._tools:
            raise ValueError(f"Tool not found: {tool_name}")

        task_id = self._task_manager.create_task(
            tool_name=tool_name,
            arguments=arguments,
            timeout=timeout,
            metadata=metadata,
        )

        return {
            "taskId": task_id,
            "status": "pending",
        }

    def _mcp_tasks_status(self, params: dict[str, Any]) -> dict[str, Any]:
        """tasks/status — 获取任务状态"""
        task_id = params.get("taskId", "")
        task = self._task_manager.get_task_info(task_id)
        return {
            "taskId": task.id,
            "status": task.status.value,
            "progress": task.progress,
            "result": task.result,
            "error": task.error,
        }

    def _mcp_tasks_result(self, params: dict[str, Any]) -> dict[str, Any]:
        """tasks/result — 获取任务结果"""
        task_id = params.get("taskId", "")
        result = self._task_manager.get_task_result(task_id)
        return {"result": result}

    def _mcp_tasks_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """tasks/cancel — 取消任务"""
        task_id = params.get("taskId", "")
        success = self._task_manager.cancel_task(task_id)
        return {"success": success}

    def _mcp_tasks_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """tasks/list — 列出任务"""
        status = params.get("status")
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)

        status_enum = None
        if status:
            status_enum = TaskStatus(status)

        tasks = self._task_manager.list_tasks(
            status=status_enum,
            limit=limit,
            offset=offset,
        )

        return {
            "tasks": [task.to_dict() for task in tasks],
        }

    def _mcp_tasks_subscribe(self, params: dict[str, Any]) -> dict[str, Any]:
        """tasks/subscribe — 订阅任务更新（SSE）"""
        task_ids = params.get("taskIds")
        all_tasks = params.get("allTasks", False)

        subscriber = self._task_manager.subscribe(
            task_ids=set(task_ids) if task_ids else None,
        )

        return {
            "subscriberId": id(subscriber),
            "message": "Subscribed to task updates",
        }

    def _mcp_sampling_create_message(self, params: dict[str, Any]) -> dict[str, Any]:
        """sampling/createMessage — 创建采样消息"""
        request = SamplingCreateMessageRequest.from_dict(params)
        response = self._sampling_manager.create_message(request)
        return response.to_dict()

    def _mcp_elicitation_create(self, params: dict[str, Any]) -> dict[str, Any]:
        """elicitation/create — 创建用户交互请求"""
        message = params.get("message", "")
        requested_schema = params.get("requestedSchema", {})
        elicit_type = params.get("type", "request")
        timeout = params.get("timeout", 300.0)
        metadata = params.get("metadata", {})

        request = self._elicitation_manager.create_request(
            message=message,
            requested_schema=requested_schema,
            elicit_type=elicit_type,
            timeout=timeout,
            metadata=metadata,
        )

        return request.to_dict()

    def _mcp_elicitation_respond(self, params: dict[str, Any]) -> dict[str, Any]:
        """elicitation/respond — 响应用户交互"""
        request_id = params.get("requestId", "")
        accepted = params.get("accepted", True)
        value = params.get("value")
        error = params.get("error")

        if accepted:
            success = self._elicitation_manager.accept(request_id, value)
        else:
            success = self._elicitation_manager.reject(request_id, error)

        return {"success": success}

    def _mcp_authorization_check(self, params: dict[str, Any]) -> dict[str, Any]:
        """authorization/check — 检查授权"""
        token = params.get("token", "")
        resource = params.get("resource", "")
        action = params.get("action", "")

        allowed = self._authorization_manager.check_permission(
            token=token,
            resource=resource,
            action=action,
        )

        return {"allowed": allowed}

    def _verify_inbound_sm3(self, message: dict[str, Any]) -> bool:
        """验证入站消息的 SM3 完整性哈希。"""
        if "_sm3" not in message:
            return True

        expected_sm3 = message.pop("_sm3")
        payload_str = _json_serialize(message)
        actual_sm3 = sm3_hash(payload_str.encode("utf-8"))
        return actual_sm3 == expected_sm3

    def run(self) -> None:
        """启动 stdio 消息循环。"""
        while True:
            try:
                message = self._read_message()
                if message is None:
                    break

                if isinstance(message, list):
                    responses: list[dict[str, Any]] = []
                    for req in message:
                        if not isinstance(req, dict):
                            continue
                        if not self._verify_inbound_sm3(req):
                            resp = self._jsonrpc_error(
                                req.get("id"),
                                JSONRPC_INVALID_REQUEST,
                                "SM3 完整性校验失败",
                            )
                            responses.append(resp)
                            continue
                        if "id" in req:
                            responses.append(self._handle_request(req))
                    if responses:
                        self._write_message(responses)
                    continue

                if not isinstance(message, dict):
                    continue

                if not self._verify_inbound_sm3(message):
                    error_resp = self._jsonrpc_error(
                        message.get("id"),
                        JSONRPC_INVALID_REQUEST,
                        "SM3 完整性校验失败",
                    )
                    self._write_message(error_resp)
                    continue

                if "id" not in message:
                    continue

                self._write_message(self._handle_request(message))

            except (ValueError, json.JSONDecodeError) as exc:
                error_resp = self._jsonrpc_error(None, JSONRPC_PARSE_ERROR, f"Parse error: {exc}")
                self._write_message(error_resp)
            except Exception as exc:
                error_resp = self._jsonrpc_error(
                    None, JSONRPC_INTERNAL_ERROR, f"Internal error: {exc}"
                )
                try:
                    self._write_message(error_resp)
                except Exception:
                    pass

    async def _async_handle_message(
        self, client_id: str, message: dict[str, Any]
    ) -> dict[str, Any] | None:
        """异步处理消息（用于 WebSocket/HTTP）"""
        if "_sm3" in message:
            if not self._verify_inbound_sm3(message):
                return self._jsonrpc_error(
                    message.get("id"),
                    JSONRPC_INVALID_REQUEST,
                    "SM3 完整性校验失败",
                )

        response = self._handle_request(message)

        if self.crypto_enabled:
            payload_str = _json_serialize(response)
            sm3_val = sm3_hash(payload_str.encode("utf-8"))
            response["_sm3"] = sm3_val

        return response

    async def run_websocket(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        path: str = "/mcp",
        auth_token: str | None = None,
        heartbeat_interval: float = 30.0,
    ) -> None:
        """
        启动 WebSocket 服务器。

        Args:
            host: 绑定主机地址
            port: 绑定端口
            path: WebSocket 路径
            auth_token: 认证 Token（可选）
            heartbeat_interval: 心跳间隔（秒）
        """
        if not WEBSOCKET_AVAILABLE:
            raise ImportError("WebSocket 服务器需要 websockets 库。请运行: pip install websockets")

        self._ws_server = WebSocketServer(
            host=host,
            port=port,
            path=path,
            auth_token=auth_token,
            crypto_enabled=self.crypto_enabled,
            sm4_key=self.sm4_key,
            heartbeat_interval=heartbeat_interval,
        )

        async def handler(client_id: str, message: dict[str, Any]) -> dict[str, Any] | None:
            return await self._async_handle_message(client_id, message)

        await self._ws_server.start(handler)

        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await self._ws_server.stop()

    async def run_http(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        path: str = "/mcp",
        sse_path: str = "/mcp/sse",
        auth_token: str | None = None,
        enable_sse: bool = True,
        sse_heartbeat: float = 15.0,
    ) -> None:
        """
        启动 HTTP/SSE 服务器。

        Args:
            host: 绑定主机地址
            port: 绑定端口
            path: HTTP 端点路径
            sse_path: SSE 端点路径
            auth_token: 认证 Token（可选）
            enable_sse: 是否启用 SSE
            sse_heartbeat: SSE 心跳间隔（秒）
        """
        if not HTTP_AVAILABLE:
            raise ImportError("HTTP 服务器需要 aiohttp 库。请运行: pip install aiohttp")

        self._http_server = HTTPServer(
            host=host,
            port=port,
            path=path,
            sse_path=sse_path,
            auth_token=auth_token,
            crypto_enabled=self.crypto_enabled,
            sm4_key=self.sm4_key,
            enable_sse=enable_sse,
            sse_heartbeat=sse_heartbeat,
        )

        async def handler(request: HTTPRequest) -> HTTPResponse:
            message = request.body
            if message is None:
                return HTTPResponse(
                    status=400,
                    body={
                        "jsonrpc": "2.0",
                        "error": {"code": -32600, "message": "Invalid Request"},
                    },
                )

            response = await self._async_handle_message("http", message)
            return HTTPResponse(body=response)

        await self._http_server.start(handler)

        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await self._http_server.stop()

    def get_transport_info(self) -> dict[str, Any]:
        """获取传输层信息"""
        return {
            "server_name": self.name,
            "server_version": self.version,
            "crypto_enabled": self.crypto_enabled,
            "tools_count": len(self._tools),
            "resources_count": len(self._resources),
            "prompts_count": len(self._prompts),
            "models_count": len(self._models),
            "websocket_available": WEBSOCKET_AVAILABLE,
            "http_available": HTTP_AVAILABLE,
        }
