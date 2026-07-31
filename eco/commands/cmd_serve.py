"""
eco serve - OpenAI-compatible API Server (P2 core)

Endpoints:
  GET  /v1/models
  POST /v1/chat/completions (SSE streaming support)
"""
import sys
import logging
import json
import os
import asyncio
import time
from pathlib import Path
log = logging.getLogger("eco.serve")
logging.basicConfig(level=logging.INFO, format="%(message)s")
ROOT = Path(__file__).resolve().parent.parent.parent

def run(args):
    host, port, api_key = args.host, args.port, args.api_key
    try:
        import importlib.util
        if importlib.util.find_spec("fastapi") is None:
            raise ImportError("fastapi")
        import uvicorn
    except ImportError:
        log.error("Missing dependencies. Run: pip install eco-agent[serve]")
        return 1
    app = _build_app(api_key)
    log.info("\n  ECO AGENT API Server")
    log.info(f"  POST http://{host}:{port}/v1/chat/completions")
    log.info(f"  GET  http://{host}:{port}/v1/models")
    log.info(f"  {'API Key auth enabled' if api_key else 'No auth (local only)'}\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0

def _build_app(api_key):
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import StreamingResponse, JSONResponse
    from pydantic import BaseModel

    app = FastAPI(title="ECO AGENT API", version="5.0.0a1")

    if api_key:
        @app.middleware("http")
        async def auth_mw(request: Request, call_next):
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or auth[7:] != api_key:
                return JSONResponse(status_code=401, content={"error": "unauthorized"})
            return await call_next(request)

    PROVIDER_MODELS = {
        "deepseek": "deepseek-chat", "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4", "qwen": "qwen-max",
        "doubao": "doubao-pro",
    }
    provider = os.environ.get("ECO_PROVIDER", "deepseek")
    model_id = PROVIDER_MODELS.get(provider, "deepseek-chat")

    class ChatRequest(BaseModel):
        model: str = ""
        messages: list[dict] = []
        stream: bool = False
        temperature: float = 0.7
        max_tokens: int = 4096

    class ModelInfo(BaseModel):
        id: str
        object: str = "model"
        created: int = 0
        owned_by: str = ""

    @app.get("/v1/models")
    async def list_models():
        models = [
            {"id": mid, "object": "model", "created": int(time.time()), "owned_by": prov}
            for prov, mid in PROVIDER_MODELS.items()
        ]
        return {"object": "list", "data": models}

    @app.post("/v1/chat/completions")
    async def chat_completions(req: ChatRequest):
        user_msg = ""
        for m in reversed(req.messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break
        if not user_msg:
            raise HTTPException(status_code=400, detail="No user message found")
        if req.stream:
            return StreamingResponse(
                _stream_response(user_msg, model_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        return await _sync_response(user_msg, model_id)

    return app

def _token_totals():
    """stats.jsonl 累计 token 数（请求前后取差值得到本次用量）"""
    try:
        sys.path.insert(0, str(ROOT))
        from agent_core.llm_client import summarize_llm_stats
        s = summarize_llm_stats()
        return s["prompt_tokens"], s["completion_tokens"]
    except Exception:
        return 0, 0

def _usage_since(before):
    """根据请求前的累计快照计算本次请求的 usage（含 EcoLoops 多轮调用）"""
    pt0, ct0 = before
    pt1, ct1 = _token_totals()
    pt, ct = max(pt1 - pt0, 0), max(ct1 - ct0, 0)
    return {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct}

async def _stream_response(query, model_id):
    rid = f"chatcmpl-{int(time.time())}"
    ts = int(time.time())
    before = _token_totals()
    # Role chunk
    yield f"data: {json.dumps({'id': rid, 'object': 'chat.completion.chunk', 'created': ts, 'model': model_id, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
    try:
        sys.path.insert(0, str(ROOT))
        from agent_core.eco_loops_integration import EcoLoops
        loops = EcoLoops()
        loops.start()
        result = await asyncio.to_thread(loops.execute_task, query)
        loops.stop()
        output = ""
        if isinstance(result, dict):
            obs = result.get("final_observation", "")
            output = obs if obs and obs != "任务完成" else str(result)
        else:
            output = str(result)
        if not output or output == "任务完成":
            from agent_core.llm_client import get_default_client
            c = get_default_client()
            if c.available():
                r = c.chat([{"role":"user","content":query}])
                output = r.get("choices",[{}])[0].get("message",{}).get("content","")
        for i in range(0, len(output), 100):
            chunk = output[i:i+100]
            yield f"data: {json.dumps({'id': rid, 'object': 'chat.completion.chunk', 'created': ts, 'model': model_id, 'choices': [{'index': 0, 'delta': {'content': chunk}, 'finish_reason': None}]})}\n\n"
            await asyncio.sleep(0.01)
    except Exception as e:
        yield f"data: {json.dumps({'id': rid, 'object': 'chat.completion.chunk', 'created': ts, 'model': model_id, 'choices': [{'index': 0, 'delta': {'content': f'[Error: {e}]'}, 'finish_reason': None}]})}\n\n"
    yield f"data: {json.dumps({'id': rid, 'object': 'chat.completion.chunk', 'created': ts, 'model': model_id, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}], 'usage': _usage_since(before)})}\n\n"
    yield "data: [DONE]\n\n"

async def _sync_response(query, model_id):
    before = _token_totals()
    try:
        sys.path.insert(0, str(ROOT))
        from agent_core.eco_loops_integration import EcoLoops
        loops = EcoLoops()
        loops.start()
        result = await asyncio.to_thread(loops.execute_task, query)
        loops.stop()
        output = ""
        if isinstance(result, dict):
            obs = result.get("final_observation", "")
            if obs and obs != "任务完成":
                output = obs
            else:
                from agent_core.llm_client import get_default_client
                c = get_default_client()
                if c.available():
                    r = c.chat([{"role":"user","content":query}])
                    output = r.get("choices",[{}])[0].get("message",{}).get("content","")
                else:
                    output = str(result)
        else:
            output = str(result)
    except Exception as e:
        output = f"[Error: {e}]"
    return {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": output}, "finish_reason": "stop"}],
        "usage": _usage_since(before),
    }
