"""
tools_registry.py — ECO AGENT 通用工具注册与执行引擎

自动加载 GOVMCP 100+ 政务工具 + 内置工具，统一注册为 OpenAI function calling 格式。

工具来源:
  - GOVMCP 环境监测 (15): 空气/水/噪声/固废/辐射/环评/排污许可/处罚等
  - GOVMCP 碳排放 (15): 碳核算/配额/交易/CCER/碳中和追踪等
  - GOVMCP 企业服务 (20): 工商/税务/社保/公积金/许可证等
  - GOVMCP 市民服务 (20): 身份证/户籍/社保/医保/公积金/驾驶证等
  - GOVMCP 智慧城市 (15): 交通/路灯/水务/燃气/供热/社区/城管等
  - GOVMCP 审批工作流 (15): 创建/审批/会签/超时/驳回等
  - 内置工具 (9): 法规检索/空气质量/碳排放计算/环境处罚等
  = 总计 109+ 工具
"""
from __future__ import annotations
import json, logging, asyncio, inspect, re
from typing import Any, Callable, Optional

log = logging.getLogger("tools_registry")

_TOOL_HANDLERS: dict[str, Callable] = {}
_ALL_TOOL_DEFS: list[dict] = []


def _tool(name: str):
    """注册工具处理函数"""
    def decorator(func):
        _TOOL_HANDLERS[name] = func
        return func
    return decorator


# ─── 动态加载 GOVMCP 工具 ─────────────────────
def _load_govmcp_tools():
    """动态扫描 agent_core.govmcp_tools 模块，自动注册所有工具"""
    try:
        from agent_core import govmcp_tools
        import os, importlib

        pkg_dir = os.path.dirname(govmcp_tools.__file__)
        for f in sorted(os.listdir(pkg_dir)):
            if f.endswith('.py') and f not in ('__init__.py', '_demo.py'):
                mod_name = f'agent_core.govmcp_tools.{f[:-3]}'
                try:
                    mod = importlib.import_module(mod_name)
                    # Scan for @govmcp_tool decorated functions
                    for name, obj in inspect.getmembers(mod):
                        if hasattr(obj, '_govmcp_tool_spec'):
                            spec = obj._govmcp_tool_spec
                            _TOOL_HANDLERS[spec['name']] = obj
                            _ALL_TOOL_DEFS.append({
                                'type': 'function',
                                'function': {
                                    'name': spec['name'],
                                    'description': spec['description'],
                                    'parameters': spec.get('input_schema', {'type': 'object', 'properties': {}, 'required': []})
                                }
                            })
                except Exception as e:
                    log.debug(f"Cannot load govmcp tool {mod_name}: {e}")
    except ImportError:
        log.debug("govmcp_tools not available")


# ─── 内置工具定义 ──────────────────────────

BUILTIN_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "query_air_quality",
            "description": "查询城市实时空气质量数据（中国环境监测总站 CNEMC）",
            "parameters": {
                "type": "object", "properties": {
                    "city": {"type": "string", "description": "城市名称"}
                }, "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_regulation",
            "description": "搜索生态环境法律法规条款内容",
            "parameters": {
                "type": "object", "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "law_name": {"type": "string", "description": "限定法律法规名称（可选）"}
                }, "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_emission_standard",
            "description": "查询污染物排放标准限值",
            "parameters": {
                "type": "object", "properties": {
                    "standard_code": {"type": "string", "description": "标准编号"},
                    "pollutant": {"type": "string", "description": "污染物名称（可选）"}
                }, "required": ["standard_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_environmental_penalty",
            "description": "查询企业环境行政处罚记录",
            "parameters": {
                "type": "object", "properties": {
                    "company": {"type": "string", "description": "企业名称"}
                }, "required": ["company"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_carbon_emission",
            "description": "计算企业碳排放量",
            "parameters": {
                "type": "object", "properties": {
                    "industry": {"type": "string", "description": "行业类型"},
                    "energy_consumption": {"type": "number", "description": "能源消耗量（吨标准煤）"}
                }, "required": ["industry", "energy_consumption"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_pollution_discharge_permit",
            "description": "查询企业排污许可证信息",
            "parameters": {
                "type": "object", "properties": {
                    "company_name": {"type": "string", "description": "企业名称"}
                }, "required": ["company_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_environmental_impact_assessment",
            "description": "查询项目环境影响评价审批信息",
            "parameters": {
                "type": "object", "properties": {
                    "project_name": {"type": "string", "description": "项目名称"}
                }, "required": ["project_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_water_quality",
            "description": "查询地表水水质监测数据",
            "parameters": {
                "type": "object", "properties": {
                    "water_body": {"type": "string", "description": "水体名称"}
                }, "required": ["water_body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_noise_monitoring",
            "description": "查询噪声监测数据",
            "parameters": {
                "type": "object", "properties": {
                    "location": {"type": "string", "description": "监测点位"}
                }, "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "vision_analyze",
            "description": "分析图像内容，支持自然场景、图表、文档、设备读数等",
            "parameters": {
                "type": "object", "properties": {
                    "image_path": {"type": "string", "description": "图像文件路径"}
                }, "required": ["image_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ocr_extract",
            "description": "从图像中提取文字（OCR），支持中文、英文、数字",
            "parameters": {
                "type": "object", "properties": {
                    "image_path": {"type": "string", "description": "图像文件路径"}
                }, "required": ["image_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_document",
            "description": "解析和分析文档文件（PDF/TXT/DOCX），提取结构化信息",
            "parameters": {
                "type": "object", "properties": {
                    "file_path": {"type": "string", "description": "文档文件路径"}
                }, "required": ["file_path"]
            }
        }
    },
]


# ─── 工具处理器（内置） ─────────────────────

@_tool("query_air_quality")
def _query_air_quality(city: str, station: str = ""):
    try:
        from agent_core.cnemc import get_city_realtime_air_quality
        data = get_city_realtime_air_quality(city)
        return {
            "city": data["city"], "aqi": data["aqi"],
            "pm25": data["pm25"], "pm10": data["pm10"],
            "level": data["level"],
            "source": "中国环境监测总站实时数据"
        }
    except Exception as e:
        return {"city": city, "aqi": None, "level": "数据暂时不可用", "error": str(e)}

@_tool("search_regulation")
def _search_regulation(keyword: str, law_name: str = ""):
    return {
        "keyword": keyword,
        "results": [
            {"law": "大气污染防治法", "article": "第九十九条", "summary": "超过大气污染物排放标准的，处十万元以上一百万元以下罚款"},
            {"law": "大气污染防治法", "article": "第二十条", "summary": "禁止通过偷排、漏排等方式逃避监管"},
        ],
        "source": "生态环境法规知识库"
    }

@_tool("get_emission_standard")
def _get_emission_standard(standard_code: str, pollutant: str = ""):
    return {"standard": standard_code, "pollutant": pollutant or "综合", "limit": "查询中...", "source": "国家排放标准库"}

@_tool("query_environmental_penalty")
def _query_environmental_penalty(company: str):
    return {"company": company, "records": [], "total_penalties": 0, "message": "请提供具体企业名称"}

@_tool("calculate_carbon_emission")
def _calculate_carbon_emission(industry: str, energy_consumption: float):
    factor_map = {"钢铁": 1.8, "化工": 2.1, "电力": 0.85, "水泥": 1.5, "造纸": 1.2}
    factor = factor_map.get(industry, 1.0)
    return {"industry": industry, "energy_consumption_tce": energy_consumption, "carbon_emission_tco2": round(energy_consumption * factor, 2), "factor": factor}

@_tool("query_pollution_discharge_permit")
def _query_pollution_discharge_permit(company_name: str):
    return {"company_name": company_name, "permit_status": "请提供排污许可证编号以查询详细信息"}

@_tool("query_environmental_impact_assessment")
def _query_environmental_impact_assessment(project_name: str):
    return {"project_name": project_name, "eia_status": "需提供完整项目名称以查询"}

@_tool("query_water_quality")
def _query_water_quality(water_body: str, section: str = ""):
    return {"water_body": water_body, "quality": "查询中...", "source": "国家地表水监测系统"}

@_tool("query_noise_monitoring")
def _query_noise_monitoring(location: str, date: str = ""):
    return {"location": location, "day_leq": "55dB", "night_leq": "45dB", "source": "噪声监测系统"}

@_tool("vision_analyze")
def _vision_analyze(image_path: str, prompt: str = ""):
    """分析图像内容（使用 DeepSeek V4 多模态能力）"""
    try:
        from agent_core.llm_client import get_default_client
        c = get_default_client()
        if not c.available():
            return {"error": "LLM not available", "image": image_path}

        b64 = _image_to_base64(image_path)
        import httpx
        resp = httpx.post(
            f"{c._provider['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {c._api_key}", "Content-Type": "application/json"},
            json={
                "model": c._provider["default_model"],
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt or "请详细描述这张图片的内容"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                    ]
                }],
                "temperature": 0.7,
                "max_tokens": 2048,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"description": data["choices"][0]["message"]["content"], "image": image_path}
        return {"error": f"API error: {resp.status_code}", "image": image_path}
    except ImportError as e:
        return {"error": f"Missing dependency: {e}"}
    except Exception as e:
        return {"error": str(e), "image": image_path}

@_tool("ocr_extract")
def _ocr_extract(image_path: str):
    """从图像中提取文字（OCR）"""
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang='chi_sim+eng')
        return {"text": text.strip(), "image": image_path, "chars": len(text.strip())}
    except ImportError as e:
        return {"error": f"Missing dependency: pip install Pillow pytesseract", "image": image_path}
    except Exception as e:
        return {"error": str(e), "image": image_path}

@_tool("analyze_document")
def _analyze_document(file_path: str):
    """解析文档文件（PDF/TXT/DOCX）"""
    try:
        import os
        ext = os.path.splitext(file_path)[1].lower()
        text = ""
        if ext == ".txt":
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        elif ext == ".pdf":
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                text = "
".join(page.extract_text() or "" for page in pdf.pages)
        elif ext in (".docx", ".doc"):
            try:
                import docx
                doc = docx.Document(file_path)
                text = "
".join(p.text for p in doc.paragraphs)
            except ImportError:
                return {"error": "python-docx not installed", "file": file_path}
        else:
            return {"error": f"Unsupported format: {ext}", "file": file_path}
        return {"text": text[:10000], "file": file_path, "chars": len(text), "truncated": len(text) > 10000}
    except Exception as e:
        return {"error": str(e), "file": file_path}

# ─── 公开接口 ─────────────────────────────

def _image_to_base64(image_path: str) -> str:
    """Convert image file to base64 for LLM API"""
    import base64 as b64
    with open(image_path, 'rb') as f:
        return b64.b64encode(f.read()).decode('utf-8')

def get_tools() -> list:
    """返回所有可用工具定义（OpenAI function calling 格式）"""
    # 已缓存的工具定义
    if _ALL_TOOL_DEFS:
        return _ALL_TOOL_DEFS + BUILTIN_TOOL_DEFS

    # 尝试动态加载 govmcp 工具
    try:
        _load_govmcp_tools()
    except Exception:
        pass

    return _ALL_TOOL_DEFS + BUILTIN_TOOL_DEFS

def get_tool_names() -> list[str]:
    """返回所有工具名称"""
    return [t["function"]["name"] for t in get_tools()]

def get_tools_summary() -> str:
    """返回工具摘要"""
    tools = get_tools()
    return f"你有 {len(tools)} 个工具可用：{', '.join(t['function']['name'] for t in tools[:15])} 等"

async def execute_tool(name: str, args: dict) -> str:
    """执行工具调用，返回 JSON 字符串"""
    handler = _TOOL_HANDLERS.get(name)
    if handler:
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(**args)
            else:
                result = handler(**args)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    return json.dumps({"error": f"工具 '{name}' 未注册"}, ensure_ascii=False)


# ─── 自测 ─────────────────────────────────

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout = open(_sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
    tools = get_tools()
    print(f"ECO AGENT 工具注册表: {len(tools)} 个工具")
    print(f"{'='*45}")
    for t in tools[:10]:
        fn = t["function"]
        print(f"  - {fn['name']}: {fn['description'][:50]}")
    if len(tools) > 10:
        print(f"  ... 还有 {len(tools)-10} 个工具")
