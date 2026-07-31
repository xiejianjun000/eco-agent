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
from collections.abc import Callable

log = logging.getLogger("tools_registry")
_HANDLERS: dict[str, Callable] = {}

# OpenAI function name 合法模式
TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# slug(对外合法名) -> 原始注册名 映射
_SLUG_TO_ORIGINAL: dict[str, str] = {}
_RENAMED_TOOLS: dict[str, str] = {}  # 原始名 -> slug

# 已知非法名的固定 slug（语义化，避免哈希不可读）
_KNOWN_SLUGS: dict[str, str] = {
    "query_snow亮的视频": "query_snow_xueliang_video",
}


def _slugify(name: str) -> str:
    """将非法工具名转换为合法 slug：优先固定表，否则剥离非法字符，兜底哈希。"""
    if name in _KNOWN_SLUGS:
        return _KNOWN_SLUGS[name]
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug or not re.search(r"[a-zA-Z0-9]", slug):
        import hashlib
        slug = "tool_" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    return slug[:64]


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
      "description": "parse documents PDF/TXT/DOCX",
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_air_quality",
      "description": "查询空气质量监测数据",
      "parameters": {
        "type": "object",
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_environmental_impact_assessment",
      "description": "查询环境影响评价信息",
      "parameters": {
        "type": "object",
        "properties": {}
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_environmental_penalty",
      "description": "查询环保处罚记录",
      "parameters": {
        "type": "object",
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_noise_monitoring",
      "description": "查询噪声监测数据",
      "parameters": {
        "type": "object",
        "properties": {}
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
        "properties": {}
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_pollution_discharge_permit",
      "description": "查询排污许可证信息",
      "parameters": {
        "type": "object",
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_snow亮的视频",
      "description": "雪亮工程视频监控查询",
      "parameters": {
        "type": "object",
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "query_water_quality",
      "description": "查询水质监测数据",
      "parameters": {
        "type": "object",
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
        "properties": {}
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
    return {"keyword": keyword, "results": [
        {"law": "大气污染防治法", "article": "第九十九条",
         "summary": "超标排放处10-100万元罚款"}], "source": "法规知识库"}

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


# ── 对外接口（名称统一规范化导出）──────────────────────────
_DUPLICATE_TOOLS: list[str] = []  # 重复注册被去重的名字

def _sanitized_defs() -> list:
    """返回名称全部合法化且去重的工具定义（拷贝，不改静态表）。
    非法名自动 slug 化；重名定义只保留首个并记日志（重名会让 LLM 端整批 400）。"""
    out = []
    seen: set[str] = set()
    for t in ALL_TOOL_DEFS:
        fn = t.get("function", {})
        slug = normalize_tool_name(fn.get("name", ""))
        if slug in seen:
            if slug not in _DUPLICATE_TOOLS:
                _DUPLICATE_TOOLS.append(slug)
                log.warning("[tools_registry] 重复工具名已去重: %r", slug)
            continue
        seen.add(slug)
        if slug == fn.get("name"):
            out.append(t)
        else:
            out.append({**t, "function": {**fn, "name": slug}})
    return out

def get_duplicate_tools() -> list[str]:
    """返回因重复注册被去重的工具名清单（报告/审计用）。"""
    _sanitized_defs()
    return list(_DUPLICATE_TOOLS)

def get_tools() -> list: return _sanitized_defs()
def get_tool_names() -> list[str]: return [t["function"]["name"] for t in _sanitized_defs()]
def get_tools_summary() -> str: return f"ECO AGENT: {len(ALL_TOOL_DEFS)} tools"

async def execute_tool(name: str, args: dict) -> str:
    # 权限闸门（L1-L4）：执行前检查，全部决策写 SM3 审计链（source=permission）
    # 可用 ECO_PERMISSION_GATE=0 关闭（测试/受控环境）
    import os
    if os.environ.get("ECO_PERMISSION_GATE", "1").strip().lower() not in ("0", "false", "no"):
        from agent_core.permissions import gate_tool_call
        allowed, level, reason = gate_tool_call(name, args)
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
