"""
tools_registry.py - ECO AGENT Complete Tool Registry
113 tools (GOVMCP 100 + Built-in 13)

名称合规：OpenAI function calling 要求工具名匹配 ^[a-zA-Z0-9_-]{1,64}$，
历史注册过含中文的非法名（如 query_snow亮的视频）会导致整批 tools 被
DeepSeek/Kimi 直接 400 拒绝。注册/导出时统一规范化为合法 slug，
维护 slug↔原始名映射，执行工具调用时反查原始实现。
"""
from __future__ import annotations
import json
import logging
import asyncio
import re
import sys
from collections.abc import Callable

log = logging.getLogger("tools_registry")
_HANDLERS: dict[str, Callable] = {}

# OpenAI function name 合法模式
TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# slug(对外合法名) -> 原始注册名 映射
_SLUG_TO_ORIGINAL: dict[str, str] = {}
_RENAMED_TOOLS: dict[str, str] = {}  # 原始名 -> slug

# 已知非法名的固定 slug（语义化，避免哈希不可读）。
# 注：历史中文名 query_snow亮的视频 已在源头修复为 query_snow_xueliang_video，
# 本表留空备用；非法名统一走通用 slug 化。
_KNOWN_SLUGS: dict[str, str] = {}


def _slugify(name: str) -> str:
    """将非法工具名转换为合法 slug：优先固定表，否则剥离非法字符，兜底哈希。

    mcp__ 命名空间特殊处理：保留 mcp__<server>__ 前缀（含 server/tool
    边界双下划线），只对工具名部分清洗——否则 MCP 工具名与聊天白名单/
    权限覆盖表对不上（曾致腾讯文档带点工具名全部漏挂）。"""
    if name in _KNOWN_SLUGS:
        return _KNOWN_SLUGS[name]
    prefix = ""
    if name.startswith("mcp__"):
        parts = name.split("__", 2)
        if len(parts) == 3:
            prefix = parts[0] + "__" + parts[1] + "__"
            name = parts[2]
        else:
            prefix = "mcp__"
            name = name[len(prefix):]
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug or not re.search(r"[a-zA-Z0-9]", slug):
        import hashlib
        slug = "tool_" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    return (prefix + slug)[:64]


def normalize_tool_name(name: str) -> str:
    """返回对外暴露的合法工具名；非法名自动 slug 化并登记映射 + 日志。"""
    if TOOL_NAME_RE.match(name):
        _SLUG_TO_ORIGINAL.setdefault(name, name)
        return name
    slug = _slugify(name)
    if slug in _SLUG_TO_ORIGINAL and _SLUG_TO_ORIGINAL[slug] != name:
        import hashlib
        slug = (slug[:55] + "_" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8])[:64]
    _SLUG_TO_ORIGINAL[slug] = name
    _RENAMED_TOOLS[name] = slug
    log.warning("[tools_registry] 非法工具名已自动 slug 化: %r -> %r", name, slug)
    return slug


def resolve_tool_name(name: str) -> str:
    """执行调用时反查：接受 slug 或原始名，返回内部原始名。"""
    return _SLUG_TO_ORIGINAL.get(name, name)


def get_renamed_tools() -> dict[str, str]:
    """返回 {原始名: slug} 改名清单（报告/审计用）。"""
    return dict(_RENAMED_TOOLS)


def tool(name):
    slug = normalize_tool_name(name)
    def dec(f):
        _HANDLERS[name] = f
        if slug != name:
            _HANDLERS[slug] = f
        return f
    return dec

# ── LLM 可见表白名单（ALL_TOOL_DEFS 内）────────────────────────────
# 内置定义表中只有以下工具是真实实现；其余（govmcp 占位 status:ok 假数据、
# 无 handler 的 vision/ocr、假数据内置）一律对 LLM 不可见——
# 占位工具暴露给模型会污染回答（模型拿到假数据后可能编造结论）。
# 外部注册工具（statute_*/devtools/MCP）不在此表，不受此过滤影响。
ALL_TOOL_DEFS_KEEP: set[str] = {
    "execute_code", "query_air_quality", "analyze_document",
    "save_document", "search_regulation",
}

# 历史占位工具黑名单（保留记录：接真实政务后端后从这里移除对应名即上架）
TOOL_EXCLUDE_LIST: set[str] = set(json.loads(
    r'''[
  "approval_cross_department",
  "approval_query_archive",
  "approval_query_audit_trail",
  "approval_query_counterpart",
  "approval_query_expedited",
  "approval_query_license_print",
  "approval_query_pending_list",
  "approval_query_statistics",
  "approval_query_status",
  "approval_query_template",
  "approval_query_withdraw",
  "approval_review_node",
  "approval_submit_appeal",
  "approval_submit_application",
  "approval_verify_signature",
  "calculate_carbon_emission",
  "carbon_calculate_footprint",
  "carbon_query_baseline",
  "carbon_query_compliance",
  "carbon_query_emission_factor",
  "carbon_query_enterprise_emission",
  "carbon_query_esg_score",
  "carbon_query_green_bond",
  "carbon_query_offset_project",
  "carbon_query_policy",
  "carbon_query_quota",
  "carbon_query_technology",
  "carbon_query_trading",
  "carbon_submit_annual_report",
  "carbon_submit_offset_application",
  "carbon_submit_verification",
  "citizen_query_appointment",
  "citizen_query_birth_registration",
  "citizen_query_business_license",
  "citizen_query_certificate",
  "citizen_query_complaint",
  "citizen_query_death_certificate",
  "citizen_query_disability_benefits",
  "citizen_query_driver_license",
  "citizen_query_education",
  "citizen_query_household",
  "citizen_query_housing_fund",
  "citizen_query_id_card",
  "citizen_query_marriage",
  "citizen_query_medical_insurance",
  "citizen_query_pension",
  "citizen_query_property_rights",
  "citizen_query_social_security",
  "citizen_query_subsistence_allowance",
  "citizen_query_tax_record",
  "citizen_query_vehicle",
  "enterprise_query_annual_report",
  "enterprise_query_bidding",
  "enterprise_query_change_record",
  "enterprise_query_construction_permit",
  "enterprise_query_credit_report",
  "enterprise_query_customs",
  "enterprise_query_environmental_penalty",
  "enterprise_query_food_license",
  "enterprise_query_foreign_trade",
  "enterprise_query_inspection",
  "enterprise_query_labor_dispute",
  "enterprise_query_patent",
  "enterprise_query_pharma_license",
  "enterprise_query_registration",
  "enterprise_query_special_industry",
  "enterprise_query_statistics",
  "enterprise_query_subsidy",
  "enterprise_query_tax_info",
  "enterprise_query_trademark",
  "enterprise_query_work_safety",
  "env_query_air_quality",
  "env_query_carbon_data",
  "env_query_cnemc_standard",
  "env_query_discharge_permit",
  "env_query_ecological_redline",
  "env_query_eia_report",
  "env_query_emergency_monitor",
  "env_query_noise",
  "env_query_pollution_source",
  "env_query_radiation",
  "env_query_soil_quality",
  "env_query_trend",
  "env_query_waste_transfer",
  "env_query_water_quality",
  "env_query_weather_forecast",
  "get_emission_standard",
  "query_environmental_penalty",
  "query_pollution_discharge_permit",
  "query_water_quality",
  "smart_query_city_app_service",
  "smart_query_city_camera",
  "smart_query_city_governance",
  "smart_query_digital_twin",
  "smart_query_emergency_response",
  "smart_query_gas_supply",
  "smart_query_iot_device",
  "smart_query_open_data",
  "smart_query_parking",
  "smart_query_power_grid",
  "smart_query_public_transport",
  "smart_query_street_lamp",
  "smart_query_traffic_congestion",
  "smart_query_waste_management",
  "smart_query_water_supply"
]'''))

ALL_TOOL_DEFS = [
  {
    "type": "function",
    "function": {
      "name": "query_air_quality",
      "description": "query real-time air quality (CNEMC)",
      "parameters": {
        "type": "object",
        "properties": {
          "city": {
            "type": "string"
          }
        },
        "required": [
          "city"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "search_regulation",
      "description": "search environmental regulations",
      "parameters": {
        "type": "object",
        "properties": {
          "keyword": {
            "type": "string"
          }
        },
        "required": [
          "keyword"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "get_emission_standard",
      "description": "query emission standard limits",
      "parameters": {
        "type": "object",
        "properties": {
          "standard_code": {
            "type": "string"
          }
        },
        "required": [
          "standard_code"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_environmental_penalty",
      "description": "query penalty records",
      "parameters": {
        "type": "object",
        "properties": {
          "company": {
            "type": "string"
          }
        },
        "required": [
          "company"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "calculate_carbon_emission",
      "description": "calculate carbon emissions",
      "parameters": {
        "type": "object",
        "properties": {
          "industry": {
            "type": "string"
          },
          "energy_consumption": {
            "type": "string"
          }
        },
        "required": [
          "industry",
          "energy_consumption"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_pollution_discharge_permit",
      "description": "query discharge permit",
      "parameters": {
        "type": "object",
        "properties": {
          "company_name": {
            "type": "string"
          }
        },
        "required": [
          "company_name"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_environmental_impact_assessment",
      "description": "query EIA info",
      "parameters": {
        "type": "object",
        "properties": {
          "project_name": {
            "type": "string"
          }
        },
        "required": [
          "project_name"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_water_quality",
      "description": "query water quality",
      "parameters": {
        "type": "object",
        "properties": {
          "water_body": {
            "type": "string"
          }
        },
        "required": [
          "water_body"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_noise_monitoring",
      "description": "query noise data",
      "parameters": {
        "type": "object",
        "properties": {
          "location": {
            "type": "string"
          }
        },
        "required": [
          "location"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "vision_analyze",
      "description": "analyze image content",
      "parameters": {
        "type": "object",
        "properties": {
          "image_path": {
            "type": "string"
          }
        },
        "required": [
          "image_path"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "ocr_extract",
      "description": "OCR text extraction",
      "parameters": {
        "type": "object",
        "properties": {
          "image_path": {
            "type": "string"
          }
        },
        "required": [
          "image_path"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "analyze_document",
      "description": "read local plain-text document by path (txt/md/csv/log); PDF/DOCX not supported",
      "parameters": {
        "type": "object",
        "properties": {
          "file_path": {
            "type": "string"
          }
        },
        "required": [
          "file_path"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "execute_code",
      "description": "execute code in sandbox",
      "parameters": {
        "type": "object",
        "properties": {
          "code": {
            "type": "string"
          },
          "language": {
            "type": "string"
          }
        },
        "required": [
          "code",
          "language"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "analyze_industrial_carbon_emission",
      "description": "工业碳排放分析",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "企业全称，用于匹配其工业碳排放台账"
                },
                "year": {
                        "type": "string",
                        "description": "分析年度（YYYY），定位对应年度排放数据"
                },
                "industry": {
                        "type": "string",
                        "description": "可选，行业类别（钢铁/化工/电力等），用于同行业对标"
                }
        },
        "required": [
                "company_name",
                "year"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_approval_digital_signature",
      "description": "审批电子签章",
      "parameters": {
        "type": "object",
        "properties": {
                "approval_id": {
                        "type": "string",
                        "description": "审批事项编号，定位需签章的审批单"
                },
                "signer_name": {
                        "type": "string",
                        "description": "签章人姓名，用于核验签章权限"
                }
        },
        "required": [
                "approval_id",
                "signer_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_business_license",
      "description": "办理营业执照",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "拟注册企业名称，用于核名与登记"
                },
                "legal_person": {
                        "type": "string",
                        "description": "法定代表人姓名"
                },
                "region": {
                        "type": "string",
                        "description": "可选，登记机关所在地区（如 赣州市）"
                }
        },
        "required": [
                "company_name",
                "legal_person"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_carbon_verification",
      "description": "申请碳核查",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "申请碳核查的企业全称"
                },
                "year": {
                        "type": "string",
                        "description": "核查年度（YYYY）"
                }
        },
        "required": [
                "company_name",
                "year"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_cleaner_production_audit",
      "description": "申请清洁生产审核",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "申请清洁生产审核的企业全称"
                },
                "industry": {
                        "type": "string",
                        "description": "可选，所属行业，用于匹配审核技术规范"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_disability_subsidy",
      "description": "申请残疾人补贴",
      "parameters": {
        "type": "object",
        "properties": {
                "applicant_name": {
                        "type": "string",
                        "description": "申请人姓名"
                },
                "disability_level": {
                        "type": "string",
                        "description": "可选，残疾等级（一至四级），用于核定补贴标准"
                },
                "region": {
                        "type": "string",
                        "description": "可选，户籍所在地区"
                }
        },
        "required": [
                "applicant_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_drug_operation_license",
      "description": "申请药品经营许可证",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "申请药品经营许可的企业全称"
                },
                "region": {
                        "type": "string",
                        "description": "可选，经营场所所在地区"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_elderly_benefit_card",
      "description": "申请老年人优待证",
      "parameters": {
        "type": "object",
        "properties": {
                "applicant_name": {
                        "type": "string",
                        "description": "老年人姓名"
                },
                "region": {
                        "type": "string",
                        "description": "可选，常住地区，用于确定发卡机构"
                }
        },
        "required": [
                "applicant_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_food_business_license",
      "description": "申请食品经营许可证",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "申请食品经营许可的主体名称"
                },
                "business_type": {
                        "type": "string",
                        "description": "可选，经营业态（餐饮/销售/食堂等）"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_high_tech_enterprise",
      "description": "申请高新技术企业认定",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "申报高新技术企业认定的企业全称"
                },
                "year": {
                        "type": "string",
                        "description": "可选，申报批次年度（YYYY）"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_housing_fund_account_enterprise",
      "description": "办理公积金开户",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "办理公积金开户的企业全称"
                },
                "region": {
                        "type": "string",
                        "description": "可选，公积金管理中心所在城市"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_housing_fund_withdrawal",
      "description": "申请公积金提取",
      "parameters": {
        "type": "object",
        "properties": {
                "applicant_name": {
                        "type": "string",
                        "description": "提取人姓名"
                },
                "reason": {
                        "type": "string",
                        "description": "可选，提取事由（购房/租房/退休等）"
                },
                "amount": {
                        "type": "string",
                        "description": "可选，拟提取金额（元）"
                }
        },
        "required": [
                "applicant_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_intellectual_property",
      "description": "申请知识产权保护",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "申请知识产权保护的主体名称"
                },
                "ip_type": {
                        "type": "string",
                        "description": "可选，知识产权类型（专利/商标/著作权）"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_invoice",
      "description": "申领发票",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "申领发票的纳税人名称"
                },
                "invoice_type": {
                        "type": "string",
                        "description": "可选，发票种类（增值税专用/普通发票）"
                },
                "amount": {
                        "type": "string",
                        "description": "可选，申领数量（份）"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_low_income_assistance",
      "description": "申请低保救助",
      "parameters": {
        "type": "object",
        "properties": {
                "applicant_name": {
                        "type": "string",
                        "description": "低保申请人姓名"
                },
                "region": {
                        "type": "string",
                        "description": "可选，户籍所在地，用于确定受理街道"
                }
        },
        "required": [
                "applicant_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_medical_device_license",
      "description": "申请医疗器械经营许可证",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "申请医疗器械经营许可的企业全称"
                },
                "device_class": {
                        "type": "string",
                        "description": "可选，器械类别（二类/三类）"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_social_security_account",
      "description": "办理社保开户",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "办理社保开户的企业全称"
                },
                "region": {
                        "type": "string",
                        "description": "可选，参保登记地"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "apply_tech_project",
      "description": "申报科技项目",
      "parameters": {
        "type": "object",
        "properties": {
                "project_name": {
                        "type": "string",
                        "description": "申报科技项目的名称"
                },
                "company_name": {
                        "type": "string",
                        "description": "可选，申报单位全称"
                },
                "year": {
                        "type": "string",
                        "description": "可选，申报年度（YYYY）"
                }
        },
        "required": [
                "project_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "book_marriage_registration",
      "description": "预约婚姻登记",
      "parameters": {
        "type": "object",
        "properties": {
                "applicant_name": {
                        "type": "string",
                        "description": "预约人姓名"
                },
                "partner_name": {
                        "type": "string",
                        "description": "可选，配偶姓名"
                },
                "date": {
                        "type": "string",
                        "description": "可选，预约登记日期（YYYY-MM-DD）"
                }
        },
        "required": [
                "applicant_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "book_smart_medical",
      "description": "智慧医疗预约",
      "parameters": {
        "type": "object",
        "properties": {
                "patient_name": {
                        "type": "string",
                        "description": "就诊人姓名"
                },
                "hospital": {
                        "type": "string",
                        "description": "可选，目标医院名称"
                },
                "department": {
                        "type": "string",
                        "description": "可选，挂号科室"
                },
                "date": {
                        "type": "string",
                        "description": "可选，预约日期（YYYY-MM-DD）"
                }
        },
        "required": [
                "patient_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "calculate_carbon_footprint",
      "description": "计算碳足迹",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "核算主体的企业全称"
                },
                "year": {
                        "type": "string",
                        "description": "核算年度（YYYY）"
                },
                "scope": {
                        "type": "string",
                        "description": "可选，核算边界（范围一/二/三）"
                }
        },
        "required": [
                "company_name",
                "year"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "configure_approval_permission",
      "description": "配置审批权限",
      "parameters": {
        "type": "object",
        "properties": {
                "role_name": {
                        "type": "string",
                        "description": "待配置的角色名称"
                },
                "permission_level": {
                        "type": "string",
                        "description": "权限级别（查看/办理/审批/管理）"
                }
        },
        "required": [
                "role_name",
                "permission_level"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "control_smart_traffic_light",
      "description": "智慧交通信号灯控制",
      "parameters": {
        "type": "object",
        "properties": {
                "intersection_id": {
                        "type": "string",
                        "description": "路口编号，定位受控信号灯"
                },
                "action": {
                        "type": "string",
                        "description": "控制动作（延长绿灯/强制红灯/恢复自动）"
                }
        },
        "required": [
                "intersection_id",
                "action"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "detect_soil_pollution",
      "description": "土壤污染检测",
      "parameters": {
        "type": "object",
        "properties": {
                "site_name": {
                        "type": "string",
                        "description": "地块名称或编号，定位检测场地"
                },
                "region": {
                        "type": "string",
                        "description": "可选，地块所在地区"
                },
                "pollutant": {
                        "type": "string",
                        "description": "可选，目标污染物（重金属/VOCs 等）"
                }
        },
        "required": [
                "site_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "dispatch_emergency_command",
      "description": "应急指挥调度",
      "parameters": {
        "type": "object",
        "properties": {
                "event_id": {
                        "type": "string",
                        "description": "突发事件编号，定位调度对象"
                },
                "command_type": {
                        "type": "string",
                        "description": "指令类型（人员调度/物资调拨/现场封控）"
                }
        },
        "required": [
                "event_id",
                "command_type"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "generate_approval_document",
      "description": "生成审批文书",
      "parameters": {
        "type": "object",
        "properties": {
                "approval_id": {
                        "type": "string",
                        "description": "审批事项编号，关联待生成文书的审批单"
                },
                "doc_type": {
                        "type": "string",
                        "description": "文书类型（批复/许可证/不予许可决定书）"
                }
        },
        "required": [
                "approval_id",
                "doc_type"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "generate_carbon_emission_report",
      "description": "生成碳排放报告",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "报告主体的企业全称"
                },
                "year": {
                        "type": "string",
                        "description": "报告年度（YYYY）"
                }
        },
        "required": [
                "company_name",
                "year"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "handle_approval_counter_sign",
      "description": "审批加签处理",
      "parameters": {
        "type": "object",
        "properties": {
                "approval_id": {
                        "type": "string",
                        "description": "需加签的审批事项编号"
                },
                "signer_name": {
                        "type": "string",
                        "description": "加签人姓名"
                }
        },
        "required": [
                "approval_id",
                "signer_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "handle_approval_delegation",
      "description": "审批委托代理",
      "parameters": {
        "type": "object",
        "properties": {
                "approval_id": {
                        "type": "string",
                        "description": "待委托的审批事项编号"
                },
                "delegate_to": {
                        "type": "string",
                        "description": "被委托代理人姓名"
                }
        },
        "required": [
                "approval_id",
                "delegate_to"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "handle_approval_joint_sign",
      "description": "审批会签处理",
      "parameters": {
        "type": "object",
        "properties": {
                "approval_id": {
                        "type": "string",
                        "description": "需会签的审批事项编号"
                },
                "departments": {
                        "type": "string",
                        "description": "可选，参与会签的部门列表"
                }
        },
        "required": [
                "approval_id"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "handle_approval_suspend_resume",
      "description": "审批挂起恢复",
      "parameters": {
        "type": "object",
        "properties": {
                "approval_id": {
                        "type": "string",
                        "description": "目标审批事项编号"
                },
                "action": {
                        "type": "string",
                        "description": "操作类型（suspend 挂起 / resume 恢复）"
                }
        },
        "required": [
                "approval_id",
                "action"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "handle_approval_transfer",
      "description": "审批改签处理",
      "parameters": {
        "type": "object",
        "properties": {
                "approval_id": {
                        "type": "string",
                        "description": "待改签的审批事项编号"
                },
                "transfer_to": {
                        "type": "string",
                        "description": "改签目标办理人姓名"
                }
        },
        "required": [
                "approval_id",
                "transfer_to"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "initiate_approval_workflow",
      "description": "发起审批流程",
      "parameters": {
        "type": "object",
        "properties": {
                "workflow_type": {
                        "type": "string",
                        "description": "流程类型（许可/备案/处罚等）"
                },
                "applicant": {
                        "type": "string",
                        "description": "发起人姓名或单位"
                },
                "title": {
                        "type": "string",
                        "description": "可选，审批事项标题"
                }
        },
        "required": [
                "workflow_type",
                "applicant"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "input_carbon_emission_data",
      "description": "录入企业碳排放数据",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "数据所属企业全称"
                },
                "year": {
                        "type": "string",
                        "description": "数据年度（YYYY）"
                },
                "emission_amount": {
                        "type": "string",
                        "description": "可选，排放量数值（吨CO2当量）"
                }
        },
        "required": [
                "company_name",
                "year"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "manage_approval_archive",
      "description": "审批归档管理",
      "parameters": {
        "type": "object",
        "properties": {
                "approval_id": {
                        "type": "string",
                        "description": "审批事项编号，定位归档案卷"
                },
                "action": {
                        "type": "string",
                        "description": "可选，操作类型（归档/借阅/移交）"
                }
        },
        "required": [
                "approval_id"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "manage_approval_template",
      "description": "审批模板管理",
      "parameters": {
        "type": "object",
        "properties": {
                "template_name": {
                        "type": "string",
                        "description": "审批模板名称"
                },
                "action": {
                        "type": "string",
                        "description": "可选，操作类型（新增/修改/停用）"
                }
        },
        "required": [
                "template_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "manage_smart_heating",
      "description": "智慧供热管理",
      "parameters": {
        "type": "object",
        "properties": {
                "community_name": {
                        "type": "string",
                        "description": "供热小区名称"
                },
                "action": {
                        "type": "string",
                        "description": "可选，操作类型（升温/降温/检修）"
                },
                "temperature": {
                        "type": "string",
                        "description": "可选，目标供水温度（℃）"
                }
        },
        "required": [
                "community_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "manage_smart_streetlight",
      "description": "智慧路灯管理",
      "parameters": {
        "type": "object",
        "properties": {
                "road_name": {
                        "type": "string",
                        "description": "道路名称，定位路灯分组"
                },
                "action": {
                        "type": "string",
                        "description": "可选，操作类型（开灯/关灯/调光）"
                },
                "brightness": {
                        "type": "string",
                        "description": "可选，目标亮度百分比"
                }
        },
        "required": [
                "road_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "monitor_smart_water",
      "description": "智慧水务监控",
      "parameters": {
        "type": "object",
        "properties": {
                "region": {
                        "type": "string",
                        "description": "监控区域名称（城区/流域）"
                },
                "indicator": {
                        "type": "string",
                        "description": "可选，监控指标（水压/流量/水质）"
                }
        },
        "required": [
                "region"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "predict_carbon_emission",
      "description": "碳排放预测分析",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "预测对象企业全称"
                },
                "target_year": {
                        "type": "string",
                        "description": "预测目标年度（YYYY）"
                }
        },
        "required": [
                "company_name",
                "target_year"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_approval_progress",
      "description": "查询审批进度",
      "parameters": {
        "type": "object",
        "properties": {
                "approval_id": {
                        "type": "string",
                        "description": "审批事项编号，查询其办理进度"
                }
        },
        "required": [
                "approval_id"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_approval_statistics",
      "description": "查询审批统计分析",
      "parameters": {
        "type": "object",
        "properties": {
                "region": {
                        "type": "string",
                        "description": "可选，统计区域"
                },
                "year": {
                        "type": "string",
                        "description": "统计年度（YYYY）"
                }
        },
        "required": [
                "year"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_approval_warning",
      "description": "查询审批时限预警",
      "parameters": {
        "type": "object",
        "properties": {
                "region": {
                        "type": "string",
                        "description": "可选，预警查询区域"
                },
                "days": {
                        "type": "string",
                        "description": "可选，临期天数阈值（默认 3 天）"
                }
        }
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_building_permit",
      "description": "查询建筑许可审批进度",
      "parameters": {
        "type": "object",
        "properties": {
                "project_name": {
                        "type": "string",
                        "description": "建设项目名称，查询其施工许可进度"
                },
                "region": {
                        "type": "string",
                        "description": "可选，项目所在地区"
                }
        },
        "required": [
                "project_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_business_registration",
      "description": "查询企业工商登记信息",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "企业全称，查询其工商登记信息"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_carbon_asset_account",
      "description": "查询碳资产账户",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "企业全称，查询其碳资产账户"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_carbon_monitoring_data",
      "description": "查询碳排放监测数据",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "企业全称，查询其碳监测数据"
                },
                "year": {
                        "type": "string",
                        "description": "可选，数据年度（YYYY）"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_carbon_quota",
      "description": "查询碳排放配额",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "企业全称，查询其碳配额"
                },
                "year": {
                        "type": "string",
                        "description": "可选，配额年度（YYYY）"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_driver_license",
      "description": "查询驾驶证信息",
      "parameters": {
        "type": "object",
        "properties": {
                "id_number": {
                        "type": "string",
                        "description": "身份证号，查询驾驶证信息"
                }
        },
        "required": [
                "id_number"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_ecological_red_line",
      "description": "查询生态红线保护区信息",
      "parameters": {
        "type": "object",
        "properties": {
                "region": {
                        "type": "string",
                        "description": "地区名称，查询生态保护红线范围"
                }
        },
        "required": [
                "region"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_energy_consumption",
      "description": "查询能源消耗统计",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "企业全称，查询其能耗统计"
                },
                "year": {
                        "type": "string",
                        "description": "可选，统计年度（YYYY）"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_enterprise_credit_report",
      "description": "查询企业信用报告",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "企业全称，查询其信用报告"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_environmental_acceptance",
      "description": "查询环保竣工验收信息",
      "parameters": {
        "type": "object",
        "properties": {
                "project_name": {
                        "type": "string",
                        "description": "建设项目名称，查询环保竣工验收信息"
                }
        },
        "required": [
                "project_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_environmental_emergency_response",
      "description": "查询环境应急响应信息",
      "parameters": {
        "type": "object",
        "properties": {
                "region": {
                        "type": "string",
                        "description": "地区名称，查询环境应急响应记录"
                },
                "level": {
                        "type": "string",
                        "description": "可选，响应级别（Ⅰ-Ⅳ级）"
                }
        },
        "required": [
                "region"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_environmental_facility_operation",
      "description": "查询环保设施运行数据",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "企业全称，查询其环保设施运行数据"
                },
                "facility_type": {
                        "type": "string",
                        "description": "可选，设施类型（废水/废气/固废）"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_environmental_impact_approval",
      "description": "查询环评审批进度",
      "parameters": {
        "type": "object",
        "properties": {
                "project_name": {
                        "type": "string",
                        "description": "建设项目名称，查询环评审批进度"
                }
        },
        "required": [
                "project_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_fire_approval",
      "description": "查询消防审批进度",
      "parameters": {
        "type": "object",
        "properties": {
                "project_name": {
                        "type": "string",
                        "description": "工程名称，查询消防审批进度"
                }
        },
        "required": [
                "project_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_government_procurement",
      "description": "查询政府采购招标信息",
      "parameters": {
        "type": "object",
        "properties": {
                "project_name": {
                        "type": "string",
                        "description": "可选，采购项目名称"
                },
                "region": {
                        "type": "string",
                        "description": "可选，采购地区"
                },
                "year": {
                        "type": "string",
                        "description": "可选，公告年度（YYYY）"
                }
        }
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_green_electricity_trade",
      "description": "查询绿电交易",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "交易主体企业全称"
                },
                "year": {
                        "type": "string",
                        "description": "可选，交易年度（YYYY）"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_grid_management",
      "description": "网格化管理查询",
      "parameters": {
        "type": "object",
        "properties": {
                "grid_id": {
                        "type": "string",
                        "description": "网格编号，查询网格化管理信息"
                },
                "region": {
                        "type": "string",
                        "description": "可选，网格所在地区"
                }
        },
        "required": [
                "grid_id"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_hazardous_waste_transfer",
      "description": "查询危险废物转移联单",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "企业全称，查询其危废转移联单"
                },
                "year": {
                        "type": "string",
                        "description": "可选，联单年度（YYYY）"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_household_registration",
      "description": "查询户籍信息",
      "parameters": {
        "type": "object",
        "properties": {
                "id_number": {
                        "type": "string",
                        "description": "身份证号，查询户籍信息"
                }
        },
        "required": [
                "id_number"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_housing_fund_account",
      "description": "查询公积金账户",
      "parameters": {
        "type": "object",
        "properties": {
                "applicant_name": {
                        "type": "string",
                        "description": "缴存人姓名"
                },
                "id_number": {
                        "type": "string",
                        "description": "可选，身份证号，用于精确匹配"
                }
        },
        "required": [
                "applicant_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_housing_fund_loan",
      "description": "查询公积金贷款进度",
      "parameters": {
        "type": "object",
        "properties": {
                "applicant_name": {
                        "type": "string",
                        "description": "借款人姓名，查询公积金贷款进度"
                }
        },
        "required": [
                "applicant_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_id_card_progress",
      "description": "查询身份证办理进度",
      "parameters": {
        "type": "object",
        "properties": {
                "id_number": {
                        "type": "string",
                        "description": "身份证号，查询身份证办理进度"
                }
        },
        "required": [
                "id_number"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_listing_guidance_progress",
      "description": "查询上市辅导进度",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "企业全称，查询上市辅导进度"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_medical_insurance_account",
      "description": "查询医保账户",
      "parameters": {
        "type": "object",
        "properties": {
                "applicant_name": {
                        "type": "string",
                        "description": "参保人姓名"
                },
                "id_number": {
                        "type": "string",
                        "description": "可选，身份证号"
                }
        },
        "required": [
                "applicant_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_medical_settlement",
      "description": "查询医保结算记录",
      "parameters": {
        "type": "object",
        "properties": {
                "applicant_name": {
                        "type": "string",
                        "description": "参保人姓名，查询医保结算记录"
                },
                "year": {
                        "type": "string",
                        "description": "可选，结算年度（YYYY）"
                }
        },
        "required": [
                "applicant_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_patent_application",
      "description": "查询专利申请进度",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "申请人（企业）全称"
                },
                "patent_name": {
                        "type": "string",
                        "description": "可选，专利名称，用于精确查询"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_property_registration",
      "description": "查询不动产登记信息",
      "parameters": {
        "type": "object",
        "properties": {
                "property_address": {
                        "type": "string",
                        "description": "不动产坐落地址"
                },
                "owner_name": {
                        "type": "string",
                        "description": "可选，权利人姓名"
                }
        },
        "required": [
                "property_address"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_public_bicycle",
      "description": "查询公共自行车",
      "parameters": {
        "type": "object",
        "properties": {
                "region": {
                        "type": "string",
                        "description": "城区名称，查询公共自行车站点"
                },
                "station_name": {
                        "type": "string",
                        "description": "可选，站点名称"
                }
        },
        "required": [
                "region"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_public_parking",
      "description": "查询公共停车位",
      "parameters": {
        "type": "object",
        "properties": {
                "region": {
                        "type": "string",
                        "description": "城区名称，查询公共停车位分布"
                }
        },
        "required": [
                "region"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_radiation_monitoring",
      "description": "查询辐射环境监测数据",
      "parameters": {
        "type": "object",
        "properties": {
                "region": {
                        "type": "string",
                        "description": "地区名称，查询辐射环境监测数据"
                },
                "year": {
                        "type": "string",
                        "description": "可选，数据年度（YYYY）"
                }
        },
        "required": [
                "region"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_residence_permit",
      "description": "查询居住证办理进度",
      "parameters": {
        "type": "object",
        "properties": {
                "id_number": {
                        "type": "string",
                        "description": "身份证号，查询居住证办理进度"
                }
        },
        "required": [
                "id_number"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_smart_city_enforcement",
      "description": "智慧城管执法查询",
      "parameters": {
        "type": "object",
        "properties": {
                "region": {
                        "type": "string",
                        "description": "城区名称，查询城管执法案件"
                },
                "case_type": {
                        "type": "string",
                        "description": "可选，案件类型（占道/违建/扬尘等）"
                }
        },
        "required": [
                "region"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_smart_community",
      "description": "智慧社区服务查询",
      "parameters": {
        "type": "object",
        "properties": {
                "community_name": {
                        "type": "string",
                        "description": "社区名称，查询社区服务事项"
                },
                "service_type": {
                        "type": "string",
                        "description": "可选，服务类型（报修/缴费/活动）"
                }
        },
        "required": [
                "community_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_smart_education",
      "description": "智慧教育服务查询",
      "parameters": {
        "type": "object",
        "properties": {
                "school_name": {
                        "type": "string",
                        "description": "可选，学校名称"
                },
                "region": {
                        "type": "string",
                        "description": "可选，所在地区"
                },
                "service_type": {
                        "type": "string",
                        "description": "可选，服务类型（招生/成绩/资助）"
                }
        }
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_smart_elderly_care",
      "description": "智慧养老服务查询",
      "parameters": {
        "type": "object",
        "properties": {
                "community_name": {
                        "type": "string",
                        "description": "社区名称，查询养老服务资源"
                },
                "service_type": {
                        "type": "string",
                        "description": "可选，服务类型（助餐/护理/日间照料）"
                }
        },
        "required": [
                "community_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_snow_xueliang_video",
      "description": "雪亮工程视频监控查询",
      "parameters": {
        "type": "object",
        "properties": {
                "region": {
                        "type": "string",
                        "description": "地区名称，查询雪亮工程监控点位"
                },
                "camera_id": {
                        "type": "string",
                        "description": "可选，监控点位编号"
                }
        },
        "required": [
                "region"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_social_security_account",
      "description": "查询社保账户信息",
      "parameters": {
        "type": "object",
        "properties": {
                "applicant_name": {
                        "type": "string",
                        "description": "参保人姓名"
                },
                "id_number": {
                        "type": "string",
                        "description": "可选，身份证号"
                }
        },
        "required": [
                "applicant_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_social_security_payment",
      "description": "查询社保缴费记录",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "缴费单位全称"
                },
                "year": {
                        "type": "string",
                        "description": "可选，缴费年度（YYYY）"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_solid_waste_disposal",
      "description": "查询固废处理监管信息",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "企业全称，查询其固废处理监管信息"
                },
                "waste_type": {
                        "type": "string",
                        "description": "可选，固废类别（一般工业固废/危废）"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_tax_registration",
      "description": "查询税务登记信息",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "纳税人名称，查询税务登记信息"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_trademark_registration",
      "description": "查询商标注册进度",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "申请人（企业）全称"
                },
                "trademark_name": {
                        "type": "string",
                        "description": "可选，商标名称"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_traffic_violation",
      "description": "查询交通违章记录",
      "parameters": {
        "type": "object",
        "properties": {
                "plate_number": {
                        "type": "string",
                        "description": "车牌号（如 赣B12345），查询违章记录"
                }
        },
        "required": [
                "plate_number"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_utility_bill",
      "description": "查询水电气缴费记录",
      "parameters": {
        "type": "object",
        "properties": {
                "household_id": {
                        "type": "string",
                        "description": "户号，查询水电气缴费记录"
                },
                "utility_type": {
                        "type": "string",
                        "description": "可选，费用类型（水/电/气）"
                }
        },
        "required": [
                "household_id"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_vehicle_info",
      "description": "查询车辆信息",
      "parameters": {
        "type": "object",
        "properties": {
                "plate_number": {
                        "type": "string",
                        "description": "车牌号，查询车辆登记信息"
                }
        },
        "required": [
                "plate_number"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "register_ccer_project",
      "description": "CCER项目登记",
      "parameters": {
        "type": "object",
        "properties": {
                "project_name": {
                        "type": "string",
                        "description": "CCER 项目名称"
                },
                "company_name": {
                        "type": "string",
                        "description": "项目业主企业全称"
                },
                "reduction_amount": {
                        "type": "string",
                        "description": "可选，预计减排量（吨CO2当量）"
                }
        },
        "required": [
                "project_name",
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "register_fertility_service",
      "description": "生育服务登记",
      "parameters": {
        "type": "object",
        "properties": {
                "applicant_name": {
                        "type": "string",
                        "description": "登记人姓名"
                },
                "spouse_name": {
                        "type": "string",
                        "description": "可选，配偶姓名"
                },
                "region": {
                        "type": "string",
                        "description": "可选，登记地区"
                }
        },
        "required": [
                "applicant_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "set_emission_reduction_target",
      "description": "设定减排目标",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "目标企业全称"
                },
                "target_year": {
                        "type": "string",
                        "description": "目标年度（YYYY）"
                },
                "reduction_percent": {
                        "type": "string",
                        "description": "可选，减排目标百分比"
                }
        },
        "required": [
                "company_name",
                "target_year"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "submit_approval_comment",
      "description": "提交审批意见",
      "parameters": {
        "type": "object",
        "properties": {
                "approval_id": {
                        "type": "string",
                        "description": "审批事项编号"
                },
                "comment": {
                        "type": "string",
                        "description": "审批意见内容"
                },
                "reviewer": {
                        "type": "string",
                        "description": "可选，意见提交人姓名"
                }
        },
        "required": [
                "approval_id",
                "comment"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "supervise_smart_gas",
      "description": "智慧燃气监管",
      "parameters": {
        "type": "object",
        "properties": {
                "region": {
                        "type": "string",
                        "description": "监管区域名称"
                },
                "indicator": {
                        "type": "string",
                        "description": "可选，监管指标（管网压力/泄漏报警/用气量）"
                }
        },
        "required": [
                "region"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "track_carbon_neutrality_progress",
      "description": "追踪碳中和进度",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "追踪对象企业全称"
                },
                "year": {
                        "type": "string",
                        "description": "可选，进度年度（YYYY）"
                }
        },
        "required": [
                "company_name"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "trade_carbon_emission_allowance",
      "description": "碳排放权交易",
      "parameters": {
        "type": "object",
        "properties": {
                "company_name": {
                        "type": "string",
                        "description": "交易主体企业全称"
                },
                "amount": {
                        "type": "string",
                        "description": "交易数量（吨配额）"
                },
                "direction": {
                        "type": "string",
                        "description": "可选，交易方向（买入/卖出）"
                }
        },
        "required": [
                "company_name",
                "amount"
        ]
}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "save_document",
      "description": "将生成的文书/清单/报告等产物真实写入工作区 deliverables 目录并落盘，返回真实文件绝对路径；只有拿到本工具返回的 path 后才允许向用户声称“已保存”",
      "parameters": {
        "type": "object",
        "properties": {
          "filename": {
            "type": "string",
            "description": "目标文件名（可含中文，如 现场检查清单.md）；不允许包含路径分隔符"
          },
          "content": {
            "type": "string",
            "description": "要写入文件的完整文本内容（UTF-8 编码落盘）"
          },
          "workspace": {
            "type": "string",
            "description": "可选，目标工作区名称或 slug；缺省使用当前激活工作区，无激活工作区时写入 default 工作区"
          }
        },
        "required": [
          "filename",
          "content"
        ]
      }
    }
  }
]

# ── 内置工具 handler（执行层）─────────────────────────────
@tool("query_air_quality")
def _h_query_air_quality(city: str, station: str = ""):
    try:
        from agent_core.cnemc import get_city_realtime_air_quality
        d = get_city_realtime_air_quality(city)
        return {"city": d["city"], "aqi": d["aqi"], "level": d["level"],
                "pm25": d["pm25"], "pm10": d["pm10"],
                "o3": d.get("o3"), "no2": d.get("no2"), "so2": d.get("so2"),
                "co": d.get("co"), "source": "CNEMC"}
    except Exception as e:
        return {"city": city, "aqi": None, "level": "unavailable", "error": str(e)}

@tool("search_regulation")
def _h_search_regulation(keyword: str, law_name: str = ""):
    """法规检索——转发《生态环境法典》条文检索。

    旧单行法已于 2026-08-15 废止（法典第1242条），本工具只返回法典原文，
    避免引用已废止法律；附旧法双标注提示。
    """
    result = _ecocodex_search(keyword)
    try:
        parsed = json.loads(result)
        hits = parsed.get("hits", [])
    except json.JSONDecodeError:
        hits = []
    return {
        "keyword": keyword,
        "note": "旧单行法（大气/水/固废法等）已于2026-08-15废止，引用须以《生态环境法典》为准",
        "results": [{"codex": h.get("file", ""), "text": h.get("text", "")[:200]} for h in hits],
    }

@tool("get_emission_standard")
def _h_get_emission_standard(standard_code: str, pollutant: str = ""):
    return {"standard": standard_code, "pollutant": pollutant or "综合"}

@tool("query_environmental_penalty")
def _h_query_environmental_penalty(company: str):
    return {"company": company, "total": 0}

@tool("calculate_carbon_emission")
def _h_calculate_carbon_emission(industry: str, energy_consumption: str):
    try:
        ec = float(energy_consumption)
    except (TypeError, ValueError):
        ec = 0.0
    f = {"钢铁": 1.8, "化工": 2.1, "电力": 0.85, "水泥": 1.5}.get(industry, 1.0)
    return {"industry": industry, "emission_t": round(ec * f, 2)}

@tool("query_pollution_discharge_permit")
def _h_query_permit(company_name: str):
    return {"company": company_name}

@tool("query_water_quality")
def _h_query_water_quality(water_body: str, section: str = ""):
    return {"water_body": water_body, "section": section}



@tool("analyze_document")
def _h_analyze_document(file_path: str):
    """真实读取本地纯文本文档（txt/md/csv/log/json 等），返回内容（截断 20000 字符防撑爆上下文）。
    权限级别 L1（analyze_ 前缀，只读）。PDF/DOCX 无解析依赖，如实报不支持。"""
    from pathlib import Path as _P
    p = _P(str(file_path or "")).expanduser()
    if not p.is_file():
        return {"error": f"file not found: {file_path}"}
    if p.suffix.lower() in (".pdf", ".docx", ".doc"):
        return {"error": f"{p.suffix} 解析依赖未安装，当前仅支持纯文本；请先另存为 .txt",
                "file_path": str(p)}
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": str(e), "file_path": str(p)}
    cap = 20000
    return {"file_path": str(p), "chars": len(content),
            "truncated": len(content) > cap, "content": content[:cap]}



@tool("save_document")
def _h_save_document(filename: str, content: str, workspace: str = ""):
    """真实落盘：写入 <workspace>/deliverables/<filename>，返回真实路径。
    权限级别 L2（save_ 前缀，本地安全区写入）。文件名做路径穿越防护。"""
    import re as _re
    from pathlib import Path as _P
    from agent_core.workspace import get_workspace_manager, slugify
    fname = _P(str(filename or "")).name  # 剥离任何目录成分，防路径穿越
    if not fname or fname in (".", ".."):
        return {"error": "invalid filename", "saved": False}
    mgr = get_workspace_manager()
    ws = None
    if workspace:
        ws = mgr.get(workspace) or mgr.get(slugify(workspace))
    if ws is None:
        ws = mgr.current()
    if ws is None:
        # 无激活工作区：落到 default 工作区，保证产物一定真实落盘
        ws = mgr.get("default") or mgr.create("default", category="通用")
    deliv = ws.path / "deliverables"
    deliv.mkdir(parents=True, exist_ok=True)
    target = deliv / fname
    # 同名不覆盖，自动追加序号
    n = 1
    while target.exists():
        stem, suf = fname.rsplit(".", 1) if "." in fname else (fname, "")
        target = deliv / (f"{stem}_{n}.{suf}" if suf else f"{stem}_{n}")
        n += 1
    target.write_text(str(content), encoding="utf-8")
    try:
        ws.add_event("deliverable", f"save_document -> {target.name} ({target.stat().st_size}B)")
    except Exception:
        pass
    return {"saved": True, "path": str(target.resolve()),
            "workspace": ws.meta.get("slug", ws.path.name),
            "bytes": target.stat().st_size}



# ── Schema 质量增强：批量补齐描述（≥20字符）与参数说明 ─────────────
_CATEGORY_BY_PREFIX = [
    ("query_", "数据检索查询"), ("apply_", "在线申办受理"), ("book_", "预约办理"),
    ("handle_", "审批流程办理"), ("manage_", "配置管理"), ("monitor_", "运行监控"),
    ("control_", "设备控制"), ("calculate_", "指标核算"), ("generate_", "文书报告生成"),
    ("register_", "登记备案"), ("predict_", "预测分析"), ("track_", "进度追踪"),
    ("trade_", "交易办理"), ("detect_", "检测识别"), ("dispatch_", "指挥调度"),
    ("configure_", "参数配置"), ("input_", "数据录入"), ("submit_", "意见提交"),
    ("supervise_", "监督管理"), ("set_", "目标设定"), ("analyze_", "分析解析"),
    ("search_", "检索查询"), ("get_", "数据获取"), ("vision_", "图像识别"),
    ("ocr_", "文字识别"), ("execute_", "沙箱执行"), ("save_", "本地产物落盘"),
    ("initiate_", "流程发起"),
]

# 核心工具参数说明（按参数名通用映射 + 工具级覆盖）
@tool("execute_code")
async def _h_execute_code(code: str, language: str = "python"):
    """沙箱代码执行：Docker → OS 级隔离(bwrap/rlimit) → 本地受限降级，30s 超时。
    权限闸门按「沙箱即边界」自动放行（见 permissions.gate_tool_call），全程 SM3 审计。"""
    from agent_core.sandbox import execute_code as _sandbox_exec
    try:
        return json.loads(await _sandbox_exec(code, language))
    except Exception as e:  # noqa: BLE001 — 沙箱异常如实回传，不让主流程崩
        return {"success": False, "stdout": "", "stderr": str(e), "sandbox": "error"}


_PARAM_DESC = {
    "city": "城市名称（如 北京、赣州），用于定位监测站点数据",    "station": "可选，监测站点名称，缺省取城市全部国控站点",
    "keyword": "检索关键词（法规名、污染物、行业等），支持中文",
    "law_name": "可选，限定法规名称以缩小检索范围",
    "standard_code": "排放标准编号（如 GB 29620-2013）",
    "pollutant": "可选，污染物名称（如 颗粒物、SO2），缺省返回标准全部限值",
    "company": "企业全称，用于匹配处罚/监管记录",
    "company_name": "企业全称，用于匹配排污许可证信息",
    "industry": "行业类别（如 钢铁、化工、电力、水泥）",
    "energy_consumption": "能耗量数值（吨标煤），可传字符串数字",
    "project_name": "建设项目名称，用于匹配环评信息",
    "water_body": "水体名称（河流/湖泊/断面，如 长江、太湖）",
    "section": "可选，监测断面名称",
    "location": "监测点位或区域名称",
    "image_path": "图片文件本地路径（jpg/png 等）",
    "file_path": "文档文件本地路径（PDF/TXT/DOCX）",
    "code": "要执行的源代码文本",
    "language": "编程语言标识（python/javascript 等沙箱白名单语言）",
    "camera_id": "监控点位编号",
    "query_type": "查询类型（实时/回放/截图）",
    "start_time": "开始时间（YYYY-MM-DD HH:mm）",
    "end_time": "结束时间（YYYY-MM-DD HH:mm）",
}


def _schema_category(name: str) -> str:
    for prefix, cat in _CATEGORY_BY_PREFIX:
        if name.startswith(prefix):
            return cat
    return "业务办理"


def _enrich_function_schema(fn: dict) -> dict:
    """返回增强后的 function schema（拷贝）：description≥20字符且说明用途，
    所有参数补齐 description。零参数工具保持 properties={}。"""
    fn = dict(fn)
    name = fn.get("name", "")
    desc = (fn.get("description") or "").strip()
    if len(desc) < 20:
        cat = _schema_category(name)
        desc = (f"{desc}——面向生态环境执法/政务服务的{cat}工具，"
                f"入参为 JSON 对象，返回结构化 JSON 结果供业务使用。")
    fn["description"] = desc
    params = fn.get("parameters")
    if isinstance(params, dict):
        props = params.get("properties")
        if props:
            new_props = {}
            for pname, pschema in props.items():
                pschema = dict(pschema or {})
                if not pschema.get("description"):
                    pschema["description"] = _PARAM_DESC.get(pname, f"{pname} 参数值（详见工具用途说明）")
                new_props[pname] = pschema
            params = dict(params)
            params["properties"] = new_props
            fn["parameters"] = params
    return fn

# ── 对外接口（名称统一规范化导出）──────────────────────────
_DUPLICATE_TOOLS: list[str] = []  # 重复注册被去重的名字

def _sanitized_defs() -> list:
    """返回名称全部合法化且去重的工具定义（拷贝，不改静态表）。
    非法名自动 slug 化；重名定义只保留首个并记日志（重名会让 LLM 端整批 400）。"""
    out = []
    seen: set[str] = set()
    excluded = 0
    for t in ALL_TOOL_DEFS:
        fn = t.get("function", {})
        slug = normalize_tool_name(fn.get("name", ""))
        # 白名单制：内置定义仅真实实现可见；外部注册工具（插件/法典/MCP）
        # 豁免：_EXTERNAL_TOOL_SOURCES 标记（register_external_tool）与
        # mcp__ 前缀（attach_mcp_tools 直接并入）
        if (slug not in ALL_TOOL_DEFS_KEEP
                and slug not in _EXTERNAL_TOOL_SOURCES
                and not slug.startswith("mcp__")):
            excluded += 1
            continue
        if slug in seen:
            if slug not in _DUPLICATE_TOOLS:
                _DUPLICATE_TOOLS.append(slug)
                log.warning("[tools_registry] 重复工具名已去重: %r", slug)
            continue
        seen.add(slug)
        fn2 = _enrich_function_schema(fn)
        if slug == fn.get("name"):
            out.append({**t, "function": fn2})
        else:
            fn2["name"] = slug
            out.append({**t, "function": fn2})
    return out

def get_duplicate_tools() -> list[str]:
    """返回因重复注册被去重的工具名清单（报告/审计用）。"""
    _sanitized_defs()
    return list(_DUPLICATE_TOOLS)

def get_tools() -> list: return _sanitized_defs()
def get_tool_names() -> list[str]: return [t["function"]["name"] for t in _sanitized_defs()]
def get_tools_summary() -> str: return f"ECO AGENT: {len(ALL_TOOL_DEFS)} tools"

# ── 外部工具注册（插件系统接入）──────────────────────────────
# 插件（plugins/）通过 register_external_tool 把工具注册进 LLM 可见定义表，
# 其声明的风险级作为闸门覆盖（execute_tool 执行时生效），
# 使插件工具与内置工具在模型视角完全等价。

_EXTERNAL_RISK_OVERRIDES: dict[str, str] = {}
_EXTERNAL_TOOL_SOURCES: dict[str, str] = {}  # name -> plugin_name


def register_external_tool(name: str, description: str, parameters: dict,
                           handler: Callable, risk_level: str = "L3",
                           source: str = "plugin") -> None:
    """注册外部（插件）工具：进入 LLM 工具表 + 执行分发 + 风险级声明。

    Args:
        name: 工具名（合法 OpenAI 函数名；重复名拒绝）。
        description: 工具描述（LLM 可见）。
        parameters: OpenAI JSON Schema（properties/required）。
        handler: 同步/异步 callable(**args) -> 可 JSON 序列化结果。
        risk_level: L1-L4，写入闸门覆盖表。
        source: 来源标识（插件名），供审计与卸载时反查。
    """
    valid = ("L1", "L2", "L3", "L4")
    if risk_level not in valid:
        raise ValueError(f"风险级非法: {risk_level}")
    if name in _HANDLERS:
        raise ValueError(f"工具已存在: {name}")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"工具名非法（OpenAI 函数名规范）: {name}")
    _HANDLERS[name] = handler
    ALL_TOOL_DEFS.append({
        "type": "function",
        "function": {"name": name, "description": description, "parameters": parameters},
    })
    _EXTERNAL_RISK_OVERRIDES[name] = risk_level
    _EXTERNAL_TOOL_SOURCES[name] = source
    log.info("[tools_registry] 外部工具已注册: %s (%s, %s)", name, risk_level, source)


def unregister_external_tool(name: str) -> bool:
    """移除外部工具（插件卸载时调用）。内置工具不可移除。"""
    if name not in _EXTERNAL_TOOL_SOURCES:
        return False
    _HANDLERS.pop(name, None)
    for i, t in enumerate(ALL_TOOL_DEFS):
        if t.get("function", {}).get("name") == name:
            ALL_TOOL_DEFS.pop(i)
            break
    _EXTERNAL_RISK_OVERRIDES.pop(name, None)
    _EXTERNAL_TOOL_SOURCES.pop(name, None)
    log.info("[tools_registry] 外部工具已移除: %s", name)
    return True


def external_tool_overrides() -> dict[str, str]:
    """当前外部工具的风险覆盖表（execute_tool 闸门注入用）。"""
    return dict(_EXTERNAL_RISK_OVERRIDES)


_RISK_ORDER = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}


def _merged_risk_overrides(load_overrides_fn) -> dict[str, str]:
    """合并 PERMISSION.md 覆盖与插件声明覆盖，同工具取更严格（最严格优先，S-05）。

    load_overrides_fn: permissions.load_overrides（调用方注入，避免循环依赖）。
    """
    merged = dict(_EXTERNAL_RISK_OVERRIDES)
    try:
        for k, v in load_overrides_fn().items():
            if k not in merged or _RISK_ORDER.get(v, 3) > _RISK_ORDER.get(merged[k], 3):
                merged[k] = v
    except Exception as e:  # noqa: BLE001 — 覆盖解析失败不影响主流程
        log.warning("[tools_registry] PERMISSION.md 覆盖解析失败: %s", e)
    return merged

_GATE_DISABLED_WARNED = False

async def execute_tool(name: str, args: dict) -> str:
    # 权限闸门（L1-L4）：执行前检查，全部决策写 SM3 审计链（source=permission）
    # 可用 ECO_PERMISSION_GATE=0 关闭（测试/受控环境）；关闭时写审计链并告警
    import os
    if os.environ.get("ECO_PERMISSION_GATE", "1").strip().lower() in ("0", "false", "no"):
        global _GATE_DISABLED_WARNED
        if not _GATE_DISABLED_WARNED:
            _GATE_DISABLED_WARNED = True
            log.warning("[tools_registry] ⚠️ 权限闸门已被 ECO_PERMISSION_GATE=0 整体关闭（仅测试/受控环境允许）")
            try:
                from agent_core.prompt_engine import PromptAuditChain
                PromptAuditChain().append(
                    source="permission",
                    content="ECO_PERMISSION_GATE=0: permission gate globally disabled",
                    accepted=True, reason="gate_disabled_by_env")
            except Exception:
                pass
    else:
        from agent_core.permissions import gate_tool_call, load_overrides
        allowed, level, reason = gate_tool_call(name, args, overrides=_merged_risk_overrides(load_overrides))
        if not allowed:
            return json.dumps(
                {"error": f"permission denied [{level}]: {reason}",
                 "permission": {"level": level, "decision": "deny", "reason": reason}},
                ensure_ascii=False)
    # slug 与原始名均可调用，反查原始实现
    h = _HANDLERS.get(name) or _HANDLERS.get(resolve_tool_name(name))
    if h:
        try:
            loop = asyncio.get_event_loop()
            if asyncio.iscoroutinefunction(h):
                r = await h(**args)
            else:
                r = await loop.run_in_executor(None, lambda: h(**args))
            return json.dumps(r, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    return json.dumps({"error": f"tool {name} not found"}, ensure_ascii=False)

if __name__ == "__main__":
    print(f"ECO AGENT: {len(ALL_TOOL_DEFS)} tools")


# ── MCP 远程工具并入（ECO_MCP_SERVERS 配置驱动，优雅降级）─────────────
_MCP_MGR = None
_MCP_ATTACHED = False


def attach_mcp_tools() -> list[str]:
    """把 ECO_MCP_SERVERS 配置的 MCP server 工具并入工具体系。

    远程工具命名 mcp__{server}__{tool}，schema 入 ALL_TOOL_DEFS、handler 入
    _HANDLERS，与内置工具同等待遇（权限闸门按 mcp__ 内层名归一化分级，见
    permissions.tool_risk_level）。未配置 / mcp SDK 缺失 / 连接失败均返回 []
    并优雅降级，不影响内置工具。幂等：重复调用不重复连接、不重复注册。
    """
    global _MCP_MGR, _MCP_ATTACHED
    if _MCP_ATTACHED:
        return [n for n in _HANDLERS if n.startswith("mcp__")]
    _MCP_ATTACHED = True
    try:
        from agent_core.mcp_connector import MCPConnectorManager, MCP_AVAILABLE
        if not MCP_AVAILABLE:
            return []
        mgr = MCPConnectorManager()
        if not mgr.configs:
            mgr.close()
            return []
        status = mgr.connect_all()
        if not any(status.values()):
            mgr.close()
            return []
        _MCP_MGR = mgr
    except Exception as e:
        log.warning("[tools_registry] MCP 接入失败（降级跳过）: %s", e)
        return []
    registered = []
    for t in _MCP_MGR.all_tools():
        full = f"mcp__{t['server']}__{t['name']}"
        # 规范化：远程工具名可能含点号等非法字符（如腾讯文档 manage.create_file），
        # 必须 slug 化进 OpenAI 函数名（DeepSeek 对非法名整批 400），
        # slug↔原名映射由 normalize_tool_name 维护，call 时反查无碍。
        slug = normalize_tool_name(full)
        if slug in _HANDLERS or full in _HANDLERS:
            continue
        schema = t.get("inputSchema") or {"type": "object", "properties": {}}
        ALL_TOOL_DEFS.append({
            "type": "function",
            "function": {"name": slug,
                         "description": f"[MCP:{t['server']}] {t.get('description', '')}",
                         "parameters": schema},
        })

        def _make(srv=t["server"], tool=t["name"]):
            def _h(**kwargs):
                return _MCP_MGR.call_tool(srv, tool, kwargs)
            return _h
        _HANDLERS[slug] = _make()
        if full != slug:
            _HANDLERS[full] = _make()  # 原名也可直达（execute_tool 反查兜底）
        registered.append(slug)
    if registered:
        log.info("[tools_registry] 并入 %d 个 MCP 工具: %s", len(registered), registered)
    return registered


# ── 内置工具：生态环境法典检索（eco-codex skill 的工具化入口）──────────────
# 知识在 ecoskills/eco-codex/kb/（五编全文 + 索引），本工具只做条级/词级检索，
# L1 只读自动放行。法典 1242 条、2026-08-15 施行。

def _ecocodex_article(article: str) -> str:
    """按条号检索法典条文（支持 '1054' / '第一千零五十四条' / '第1054条'）。"""
    import subprocess
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "ecoskills" / "eco-codex" / "scripts" / "lookup.py"
    try:
        r = subprocess.run([sys.executable, str(script), "article", article],
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip() or f"检索失败: {r.stderr.strip()[:200]}"
    except (subprocess.SubprocessError, OSError) as e:
        return f"法典检索不可用: {e}"


def _ecocodex_search(keyword: str, limit: int = 5) -> str:
    """关键词检索法典条文（返回命中条文全文）。"""
    import subprocess
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "ecoskills" / "eco-codex" / "scripts" / "lookup.py"
    try:
        r = subprocess.run([sys.executable, str(script), "search", keyword],
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or f"检索失败: {r.stderr.strip()[:200]}"
    except (subprocess.SubprocessError, OSError) as e:
        return f"法典检索不可用: {e}"


register_external_tool(
    name="statute_lookup",
    description="生态环境法典条文检索——按条号（如 1054 或 第一千零五十四条）精确查询条文原文，2026-08-15 施行的《中华人民共和国生态环境法典》1242 条全文",
    parameters={
        "type": "object",
        "properties": {
            "article": {"type": "string", "description": "条号：阿拉伯数字（1054）或中文数字（第一千零五十四条）或完整引用（第1054条）"},
        },
        "required": ["article"],
    },
    handler=_ecocodex_article,
    risk_level="L1",
    source="builtin-ecocodex",
)

register_external_tool(
    name="statute_search",
    description="生态环境法典关键词检索——按关键词（如 逃避监管、按日计罚、排污许可）检索全部条文原文",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "检索关键词"},
            "limit": {"type": "integer", "description": "最多返回条数（默认5）"},
        },
        "required": ["keyword"],
    },
    handler=_ecocodex_search,
    risk_level="L1",
    source="builtin-ecocodex",
)
