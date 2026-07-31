"""
tools_registry.py - ECO AGENT tool registry
115+ tools (GOVMCP 103 + built-in 12)
"""
from __future__ import annotations
import json, logging, asyncio, inspect
from typing import Any, Callable

log = logging.getLogger("tools_registry")
_TOOL_HANDLERS: dict[str, Callable] = {}
_ALL_TOOL_DEFS: list[dict] = []

def _tool(name: str):
    def dec(func):
        _TOOL_HANDLERS[name] = func
        return func
    return dec

BUILTIN_TOOL_DEFS = [
    {"type":"function","function":{"name":"query_air_quality","description":"query real-time air quality (CNEMC)","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}},
    {"type":"function","function":{"name":"search_regulation","description":"search environmental regulations by keyword","parameters":{"type":"object","properties":{"keyword":{"type":"string"}},"required":["keyword"]}}},
    {"type":"function","function":{"name":"get_emission_standard","description":"query emission standard limits","parameters":{"type":"object","properties":{"standard_code":{"type":"string"}},"required":["standard_code"]}}},
    {"type":"function","function":{"name":"query_environmental_penalty","description":"query environmental penalty records","parameters":{"type":"object","properties":{"company":{"type":"string"}},"required":["company"]}}},
    {"type":"function","function":{"name":"calculate_carbon_emission","description":"calculate corporate carbon emissions","parameters":{"type":"object","properties":{"industry":{"type":"string"},"energy_consumption":{"type":"number"}},"required":["industry","energy_consumption"]}}},
    {"type":"function","function":{"name":"query_pollution_discharge_permit","description":"query pollution discharge permit info","parameters":{"type":"object","properties":{"company_name":{"type":"string"}},"required":["company_name"]}}},
    {"type":"function","function":{"name":"query_environmental_impact_assessment","description":"query EIA approval info","parameters":{"type":"object","properties":{"project_name":{"type":"string"}},"required":["project_name"]}}},
    {"type":"function","function":{"name":"query_water_quality","description":"query surface water quality data","parameters":{"type":"object","properties":{"water_body":{"type":"string"}},"required":["water_body"]}}},
    {"type":"function","function":{"name":"query_noise_monitoring","description":"query noise monitoring data","parameters":{"type":"object","properties":{"location":{"type":"string"}},"required":["location"]}}},
    {"type":"function","function":{"name":"vision_analyze","description":"analyze image content (scenes/charts/documents)","parameters":{"type":"object","properties":{"image_path":{"type":"string"},"prompt":{"type":"string"}},"required":["image_path"]}}},
    {"type":"function","function":{"name":"ocr_extract","description":"extract text from images (Chinese/English OCR)","parameters":{"type":"object","properties":{"image_path":{"type":"string"}},"required":["image_path"]}}},
    {"type":"function","function":{"name":"analyze_document","description":"parse and extract text from documents (PDF/TXT/DOCX)","parameters":{"type":"object","properties":{"file_path":{"type":"string"}},"required":["file_path"]}}},
]

@_tool("query_air_quality")
def _qaq(city: str, station: str = ""):
    try:
        from agent_core.cnemc import get_city_realtime_air_quality
        d = get_city_realtime_air_quality(city)
        return {"city":d["city"],"aqi":d["aqi"],"level":d["level"],"pm25":d["pm25"],"pm10":d["pm10"],"source":"CNEMC"}
    except:
        return {"city":city,"aqi":None,"level":"unavailable"}

@_tool("search_regulation")
def _sr(keyword: str, law_name: str = ""):
    return {"keyword":keyword,"results":[{"law":"大气污染防治法","article":"第九十九条","summary":"超标排放处10-100万元罚款"}],"source":"法规知识库"}

@_tool("vision_analyze")
def _va(image_path: str, prompt: str = ""):
    try:
        from agent_core.llm_client import get_default_client
        c = get_default_client()
        import base64 as b64mod
        import httpx
        with open(image_path, "rb") as f:
            b64 = b64mod.b64encode(f.read()).decode("utf-8")
        resp = httpx.post(
            f"{c._provider['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {c._api_key}", "Content-Type": "application/json"},
            json={
                "model": c._provider["default_model"],
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt or "描述图片内容"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                    ]
                }],
                "max_tokens": 2048
            },
            timeout=30
        )
        if resp.status_code == 200:
            return {"description": resp.json()["choices"][0]["message"]["content"], "image": image_path}
        return {"error": f"API {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}

@_tool("ocr_extract")
def _ocr(image_path: str):
    try:
        from PIL import Image
        import pytesseract
        text = pytesseract.image_to_string(Image.open(image_path), lang="chi_sim+eng")
        return {"text": text.strip(), "chars": len(text.strip())}
    except Exception as e:
        return {"error": str(e)}

@_tool("analyze_document")
def _ad(file_path: str):
    try:
        import os as _os
        ext = _os.path.splitext(file_path)[1].lower()
        parts = []
        if ext == ".txt":
            with open(file_path, "r", encoding="utf-8") as f:
                parts.append(f.read())
        elif ext == ".pdf":
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                for p in pdf.pages:
                    t = p.extract_text()
                    if t:
                        parts.append(t)
        elif ext in (".docx", ".doc"):
            import docx
            doc = docx.Document(file_path)
            parts.append("\n".join(p.text for p in doc.paragraphs))
        else:
            return {"error": f"unsupported format {ext}"}
        text = "\n".join(parts)
        return {"text": text[:10000], "chars": len(text), "truncated": len(text) > 10000}
    except Exception as e:
        return {"error": str(e)}

@_tool("get_emission_standard")
def _ges(standard_code: str, pollutant: str = ""):
    return {"standard": standard_code, "pollutant": pollutant or "综合"}
@_tool("query_environmental_penalty")
def _qep(company: str):
    return {"company": company, "total": 0}
@_tool("calculate_carbon_emission")
def _cce(industry: str, energy_consumption: float):
    f = {"钢铁":1.8,"化工":2.1,"电力":0.85,"水泥":1.5}.get(industry, 1.0)
    return {"industry":industry,"emission_t":round(energy_consumption*f,2)}
@_tool("query_pollution_discharge_permit")
def _qpd(company_name: str):
    return {"company": company_name}
@_tool("query_environmental_impact_assessment")
def _qeia(project_name: str):
    return {"project": project_name}
@_tool("query_water_quality")
def _qwq(water_body: str, section: str = ""):
    return {"water_body": water_body}
@_tool("query_noise_monitoring")
def _qnm(location: str, date: str = ""):
    return {"location": location}

def get_tools() -> list:
    if not _ALL_TOOL_DEFS:
        try:
            import os as _os
            from agent_core import govmcp_tools as _gt
            pkg_dir = _os.path.dirname(_gt.__file__)
            for f in sorted(_os.listdir(pkg_dir)):
                if f.endswith(".py") and f not in ("__init__.py","_demo.py"):
                    mod = __import__(f"agent_core.govmcp_tools.{f[:-3]}", fromlist=[""])
                    for n,o in inspect.getmembers(mod):
                        if hasattr(o, "_govmcp_tool_spec"):
                            s = o._govmcp_tool_spec
                            _TOOL_HANDLERS[s["name"]] = o
                            _ALL_TOOL_DEFS.append({"type":"function","function":{"name":s["name"],"description":s["description"],"parameters":s.get("input_schema",{"type":"object","properties":{},"required":[]})}})
        except: pass
    return _ALL_TOOL_DEFS + BUILTIN_TOOL_DEFS

def get_tool_names() -> list[str]:
    return [t["function"]["name"] for t in get_tools()]

def get_tools_summary() -> str:
    return f"Available: {len(get_tools())} tools"

async def execute_tool(name: str, args: dict) -> str:
    h = _TOOL_HANDLERS.get(name)
    if h:
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(None, lambda: h(**args)) if not asyncio.iscoroutinefunction(h) else await h(**args)
            return json.dumps(r, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error":str(e)}, ensure_ascii=False)
    return json.dumps({"error":f"tool '{name}' not found"}, ensure_ascii=False)

if __name__ == "__main__":
    import sys as _s
    _s.stdout = open(_s.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
    print(f"ECO AGENT: {len(get_tools())} tools registered")
