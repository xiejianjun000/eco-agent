"""
tools_registry.py - ECO AGENT Complete Tool Registry
113 tools (GOVMCP 100 + Built-in 13)
"""
from __future__ import annotations
import json, logging, asyncio
from typing import Callable

log = logging.getLogger("tools_registry")
_HANDLERS: dict[str, Callable] = {}

def tool(name):
    def dec(f): _HANDLERS[name] = f; return f
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

def get_tools() -> list: return ALL_TOOL_DEFS
def get_tool_names() -> list[str]: return [t["function"]["name"] for t in ALL_TOOL_DEFS]
def get_tools_summary() -> str: return f"ECO AGENT: {len(ALL_TOOL_DEFS)} tools"

async def execute_tool(name: str, args: dict) -> str:
    h = _HANDLERS.get(name)
    if h:
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(None, lambda: h(**args))
            return json.dumps(r, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    return json.dumps({"error": f"tool {name} not found"}, ensure_ascii=False)

if __name__ == "__main__":
    print(f"ECO AGENT: {len(ALL_TOOL_DEFS)} tools")
