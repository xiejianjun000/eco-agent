#!/usr/bin/env python3
"""
schema_guard.py — 轻量 JSON Schema 校验器（P0-4 Steering 深化）

对标 Hermes schematized subagent I/O：
- 子任务可声明 input_schema / output_schema，delegation 前后强校验
- 本实现覆盖常用 JSON Schema 子集（无第三方依赖）：
  type / required / properties / items / enum / minimum|maximum /
  minLength|maxLength / pattern / additionalProperties
- 校验失败返回第一条错误路径 + 原因；执行层据此 FAILED 并走 replan，
  避免把"结构不合规的产出"当作成功结果交给 expectation 核验。

用法：
  ok, errs = SchemaGuard.validate(data, schema)
  ok, errs = SchemaGuard.validate_json_text(text, schema)   # 文本产出先解析
"""

import json
import re
from typing import Any

_TYPE_OF = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


class SchemaGuard:
    """极简 JSON Schema 子集校验器。"""

    @staticmethod
    def validate(data: Any, schema: dict | None) -> tuple[bool, list[str]]:
        if not schema:
            return True, []
        errs: list[str] = []
        SchemaGuard._walk(data, schema, "$", errs, set())
        return not errs, errs

    @staticmethod
    def validate_json_text(text: str, schema: dict | None) -> tuple[bool, list[str]]:
        """校验一段产出文本：优先按 JSON 解析后做 schema 校验；
        无法解析 JSON 且 schema 期望 string 时按原始字符串校验。"""
        if not schema:
            return True, []
        stripped = (text or "").strip()
        if stripped.startswith("```"):
            # 剥掉 markdown fence
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            data = stripped  # 文本产出
        return SchemaGuard.validate(data, schema)

    # ── 内部 ────────────────────────────────────────────────

    @staticmethod
    def _type_name(v: Any) -> str:
        for name, t in _TYPE_OF.items():
            if isinstance(v, bool):
                if name == "boolean":
                    return name
                continue  # bool 不应落入 integer/number
            if isinstance(v, t):
                return name
        return type(v).__name__

    @staticmethod
    def _walk(data: Any, schema: dict, path: str, errs: list[str], seen: set) -> None:
        if id(schema) in seen:  # 防御循环引用
            return
        seen = seen | {id(schema)}

        # type 检查
        if "type" in schema:
            want = schema["type"]
            tname = SchemaGuard._type_name(data)
            if isinstance(want, list):
                if tname not in want:
                    errs.append(f"{path}: 期望类型 {want}，实际 {tname}")
                    return
            elif tname != want:
                errs.append(f"{path}: 期望类型 {want}，实际 {tname}")
                return

        # enum
        if "enum" in schema and data not in schema["enum"]:
            errs.append(f"{path}: 值不在允许枚举内 {schema['enum']}")

        # 数值范围
        if isinstance(data, (int, float)) and not isinstance(data, bool):
            if "minimum" in schema and data < schema["minimum"]:
                errs.append(f"{path}: {data} 小于最小值 {schema['minimum']}")
            if "maximum" in schema and data > schema["maximum"]:
                errs.append(f"{path}: {data} 大于最大值 {schema['maximum']}")

        # 字符串约束
        if isinstance(data, str):
            if "minLength" in schema and len(data) < schema["minLength"]:
                errs.append(f"{path}: 长度 {len(data)} 小于 minLength {schema['minLength']}")
            if "maxLength" in schema and len(data) > schema["maxLength"]:
                errs.append(f"{path}: 长度 {len(data)} 大于 maxLength {schema['maxLength']}")
            if "pattern" in schema:
                try:
                    if not re.search(schema["pattern"], data):
                        errs.append(f"{path}: 不匹配 pattern {schema['pattern']}")
                except re.error:
                    pass

        # object：required / properties / additionalProperties
        if isinstance(data, dict) and schema.get("type") in (None, "object"):
            props = schema.get("properties", {})
            for req in schema.get("required", []):
                if req not in data:
                    errs.append(f"{path}.{req}: 缺少必填字段")
            for k, v in data.items():
                sub = props.get(k)
                if sub is not None:
                    SchemaGuard._walk(v, sub, f"{path}.{k}", errs, seen)
                elif schema.get("additionalProperties") is False:
                    errs.append(f"{path}.{k}: 不允许的额外字段")
        # array：items
        if isinstance(data, list) and schema.get("type") in (None, "array"):
            item_schema = schema.get("items")
            if item_schema is not None:
                for i, v in enumerate(data):
                    SchemaGuard._walk(v, item_schema, f"{path}[{i}]", errs, seen)


if __name__ == "__main__":  # pragma: no cover - 快速自检
    s = {
        "type": "object",
        "required": ["action", "args"],
        "properties": {
            "action": {"type": "string", "enum": ["run", "stop"]},
            "args": {"type": "object"},
            "budget": {"type": "integer", "minimum": 1},
        },
    }
    ok, errs = SchemaGuard.validate({"action": "run", "args": {"x": 1}}, s)
    print("valid case:", ok, errs)
    ok, errs = SchemaGuard.validate({"action": "fly", "budget": -3}, s)
    print("invalid case:", ok, errs)
