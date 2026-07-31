#!/usr/bin/env python3
"""
govmcp.tools.government.citizen_service — 市民服务工具模块

提供身份证、户籍、社保、医保、公积金、交通、不动产等市民常用政务服务的工具函数。
"""

from typing import Any, Dict, List, Optional

from govmcp.tools.government._demo import demo_govmcp_tool as govmcp_tool


@govmcp_tool(
    name="query_id_card_progress",
    description="查询身份证办理进度",
)
def query_id_card_progress(
    name: str,
    id_number: str,
    phone: str,
) -> dict[str, Any]:
    """
    查询身份证办理进度。

    Args:
        name: 申请人姓名
        id_number: 身份证号码
        phone: 联系电话

    Returns:
        办理进度信息
    """
    return {
        "status": "success",
        "data": {
            "name": name,
            "id_number": id_number[-4:],
            "progress": "制证中",
            "estimated_date": "2026-05-20",
            "pickup_location": "XX区公安局出入境大厅",
        },
    }


@govmcp_tool(
    name="query_household_registration",
    description="查询户籍信息",
)
def query_household_registration(
    id_number: str,
    name: str,
) -> dict[str, Any]:
    """
    查询户籍基本信息。

    Args:
        id_number: 身份证号码
        name: 姓名

    Returns:
        户籍信息
    """
    return {
        "status": "success",
        "data": {
            "name": name,
            "id_number": id_number,
            "household_address": "XX省XX市XX区XX街道XX号",
            "household_type": "城镇居民",
            "registered_permanent": True,
        },
    }


@govmcp_tool(
    name="query_social_security_account",
    description="查询社保账户信息",
)
def query_social_security_account(
    id_number: str,
    name: str,
) -> dict[str, Any]:
    """
    查询社保账户余额和基本信息。

    Args:
        id_number: 身份证号码
        name: 姓名

    Returns:
        社保账户信息
    """
    return {
        "status": "success",
        "data": {
            "name": name,
            "account_id": f"SS{id_number[-10:]}",
            "balance": 15680.50,
            "pension_contribution": 12500.00,
            "medical_contribution": 2180.50,
            "employment_type": "企业在职",
            "last_update": "2026-05-01",
        },
    }


@govmcp_tool(
    name="query_social_security_payment",
    description="查询社保缴费记录",
)
def query_social_security_payment(
    id_number: str,
    year: int,
    month: int,
) -> dict[str, Any]:
    """
    查询社保缴费明细记录。

    Args:
        id_number: 身份证号码
        year: 查询年份
        month: 查询月份

    Returns:
        缴费记录详情
    """
    return {
        "status": "success",
        "data": {
            "id_number": id_number[-4:],
            "year": year,
            "month": month,
            "pension": {"personal": 800.00, "company": 1600.00},
            "medical": {"personal": 200.00, "company": 500.00},
            "unemployment": {"personal": 50.00, "company": 150.00},
            "total": 3300.00,
            "payment_status": "已缴纳",
        },
    }


@govmcp_tool(
    name="query_medical_insurance_account",
    description="查询医保账户",
)
def query_medical_insurance_account(
    id_number: str,
    name: str,
) -> dict[str, Any]:
    """
    查询医保个人账户余额和消费记录。

    Args:
        id_number: 身份证号码
        name: 姓名

    Returns:
        医保账户信息
    """
    return {
        "status": "success",
        "data": {
            "name": name,
            "account_balance": 4560.80,
            "annual_limit": 300000,
            "used_amount": 12500.00,
            "insurance_type": "城镇职工基本医疗保险",
            "hospital_count": 3,
            "clinic_count": 12,
        },
    }


@govmcp_tool(
    name="query_medical_settlement",
    description="查询医保结算记录",
)
def query_medical_settlement(
    id_number: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """
    查询医保结算明细。

    Args:
        id_number: 身份证号码
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)

    Returns:
        结算记录列表
    """
    return {
        "status": "success",
        "data": {
            "id_number": id_number[-4:],
            "period": f"{start_date} 至 {end_date}",
            "records": [
                {
                    "date": "2026-05-08",
                    "hospital": "XX市第一人民医院",
                    "total_cost": 580.00,
                    "insurance_reimburse": 450.00,
                    "personal_payment": 130.00,
                    "diagnosis": "呼吸系统疾病",
                },
                {
                    "date": "2026-04-22",
                    "hospital": "XX市中医院",
                    "total_cost": 1200.00,
                    "insurance_reimburse": 960.00,
                    "personal_payment": 240.00,
                    "diagnosis": "中医理疗",
                },
            ],
            "total_reimburse": 1410.00,
        },
    }


@govmcp_tool(
    name="query_housing_fund_account",
    description="查询公积金账户",
)
def query_housing_fund_account(
    id_number: str,
    name: str,
) -> dict[str, Any]:
    """
    查询公积金账户余额。

    Args:
        id_number: 身份证号码
        name: 姓名

    Returns:
        公积金账户信息
    """
    return {
        "status": "success",
        "data": {
            "name": name,
            "account_id": f"HF{id_number[-10:]}",
            "balance": 125600.00,
            "monthly_deposit": 2400.00,
            "deposit_ratio": "12%",
            "last_deposit_date": "2026-05-01",
            "loan_balance": 0.00,
            "account_status": "正常",
        },
    }


@govmcp_tool(
    name="apply_housing_fund_withdrawal",
    description="申请公积金提取",
)
def apply_housing_fund_withdrawal(
    id_number: str,
    name: str,
    withdrawal_type: str,
    amount: float,
    bank_name: str,
    bank_account: str,
) -> dict[str, Any]:
    """
    申请公积金提取。

    Args:
        id_number: 身份证号码
        name: 姓名
        withdrawal_type: 提取类型 (租房/购房/还贷/离职等)
        amount: 提取金额
        bank_name: 银行名称
        bank_account: 银行账号

    Returns:
        申请结果
    """
    return {
        "status": "success",
        "data": {
            "application_id": f"HFWD{20260513001}",
            "name": name,
            "withdrawal_type": withdrawal_type,
            "amount": amount,
            "bank_account_masked": f"{bank_account[:4]}****{bank_account[-4:]}",
            "status": "审核中",
            "estimated_days": 3,
        },
    }


@govmcp_tool(
    name="query_housing_fund_loan",
    description="查询公积金贷款进度",
)
def query_housing_fund_loan(
    id_number: str,
    loan_app_no: str,
) -> dict[str, Any]:
    """
    查询公积金贷款申请进度。

    Args:
        id_number: 身份证号码
        loan_app_no: 贷款申请编号

    Returns:
        贷款进度信息
    """
    return {
        "status": "success",
        "data": {
            "application_no": loan_app_no,
            "progress": "审批通过",
            "loan_amount": 800000.00,
            "loan_term": 240,
            "interest_rate": 3.1,
            "current_stage": "等待抵押登记",
            "estimated_completion": "2026-05-25",
        },
    }


@govmcp_tool(
    name="query_residence_permit",
    description="查询居住证办理进度",
)
def query_residence_permit(
    name: str,
    id_number: str,
    phone: str,
) -> dict[str, Any]:
    """
    查询居住证办理进度。

    Args:
        name: 申请人姓名
        id_number: 身份证号码
        phone: 联系电话

    Returns:
        居住证办理进度
    """
    return {
        "status": "success",
        "data": {
            "name": name,
            "id_number_masked": f"{id_number[:6]}******{id_number[-4:]}",
            "status": "审核通过，待制证",
            "application_date": "2026-05-06",
            "estimated_date": "2026-05-18",
            "pickup_address": "XX区政务服务中心",
        },
    }


@govmcp_tool(
    name="query_driver_license",
    description="查询驾驶证信息",
)
def query_driver_license(
    name: str,
    license_no: str,
) -> dict[str, Any]:
    """
    查询驾驶证信息。

    Args:
        name: 姓名
        license_no: 驾驶证号码

    Returns:
        驾驶证信息
    """
    return {
        "status": "success",
        "data": {
            "name": name,
            "license_no": license_no,
            "vehicle_type": "C1",
            "issue_date": "2018-06-15",
            "validity": "2028-06-15",
            "score": 12,
            "annual_check_date": "2026-06-30",
            "status": "正常",
        },
    }


@govmcp_tool(
    name="query_vehicle_info",
    description="查询车辆信息",
)
def query_vehicle_info(
    plate_number: str,
    id_number: str,
) -> dict[str, Any]:
    """
    查询车辆登记信息。

    Args:
        plate_number: 车牌号
        id_number: 车主身份证号

    Returns:
        车辆信息
    """
    return {
        "status": "success",
        "data": {
            "plate_number": plate_number,
            "owner": f"***{id_number[-4:]}",
            "vehicle_type": "小型普通客车",
            "brand": "XX品牌",
            "model": "XXX",
            "vin": f"LSV****{id_number[-4:]}",
            "register_date": "2022-03-20",
            "annual_check_date": "2026-03-31",
            "status": "正常",
        },
    }


@govmcp_tool(
    name="query_traffic_violation",
    description="查询交通违章记录",
)
def query_traffic_violation(
    plate_number: str,
    id_number: str,
) -> dict[str, Any]:
    """
    查询车辆交通违章记录。

    Args:
        plate_number: 车牌号
        id_number: 车主身份证号

    Returns:
        违章记录列表
    """
    return {
        "status": "success",
        "data": {
            "plate_number": plate_number,
            "total_violations": 1,
            "total_penalty": 200,
            "total_deduction": 3,
            "records": [
                {
                    "date": "2026-04-15",
                    "location": "XX路与XX路口",
                    "violation": "闯红灯",
                    "penalty": 200,
                    "deduction": 6,
                    "status": "未处理",
                },
            ],
            "license_score": 9,
        },
    }


@govmcp_tool(
    name="query_property_registration",
    description="查询不动产登记信息",
)
def query_property_registration(
    id_number: str,
    property_address: str,
) -> dict[str, Any]:
    """
    查询不动产登记信息。

    Args:
        id_number: 身份证号码
        property_address: 不动产地址

    Returns:
        登记信息
    """
    return {
        "status": "success",
        "data": {
            "owner": "***",
            "property_address": property_address,
            "property_type": "住宅",
            "area": 120.5,
            "register_date": "2020-08-15",
            "certificate_no": "XX(2020)不动产权第XXXX号",
            "mortgage_status": "无抵押",
            "status": "正常",
        },
    }


@govmcp_tool(
    name="query_utility_bill",
    description="查询水电气缴费记录",
)
def query_utility_bill(
    account_no: str,
    bill_type: str,
) -> dict[str, Any]:
    """
    查询水电气等公用事业缴费情况。

    Args:
        account_no: 户号
        bill_type: 缴费类型 (水/电/气)

    Returns:
        缴费信息
    """
    return {
        "status": "success",
        "data": {
            "account_no": account_no,
            "bill_type": bill_type,
            "current_amount": 258.50,
            "due_date": "2026-05-25",
            "last_payment": "2026-04-20",
            "last_amount": 235.80,
            "payment_status": "待缴纳",
        },
    }


@govmcp_tool(
    name="apply_low_income_assistance",
    description="申请低保救助",
)
def apply_low_income_assistance(
    name: str,
    id_number: str,
    address: str,
    income: float,
    family_size: int,
) -> dict[str, Any]:
    """
    申请最低生活保障救助。

    Args:
        name: 申请人姓名
        id_number: 身份证号码
        address: 家庭住址
        income: 家庭月收入
        family_size: 家庭人口数

    Returns:
        申请结果
    """
    return {
        "status": "success",
        "data": {
            "application_id": f"DI{20260513001}",
            "name": name,
            "id_number_masked": f"{id_number[:6]}******{id_number[-4:]}",
            "status": "受理中",
            "estimated_review_days": 15,
        },
    }


@govmcp_tool(
    name="apply_disability_subsidy",
    description="申请残疾人补贴",
)
def apply_disability_subsidy(
    name: str,
    id_number: str,
    disability_level: str,
    disability_cert_no: str,
) -> dict[str, Any]:
    """
    申请残疾人补贴。

    Args:
        name: 申请人姓名
        id_number: 身份证号码
        disability_level: 残疾等级 (1-4级)
        disability_cert_no: 残疾证号

    Returns:
        申请结果
    """
    return {
        "status": "success",
        "data": {
            "application_id": f"DS{20260513001}",
            "name": name,
            "disability_level": disability_level,
            "disability_cert_no": disability_cert_no,
            "subsidy_type": "困难残疾人生活补贴",
            "estimated_amount": 200.00,
            "status": "审核中",
        },
    }


@govmcp_tool(
    name="apply_elderly_benefit_card",
    description="申请老年人优待证",
)
def apply_elderly_benefit_card(
    name: str,
    id_number: str,
    birth_date: str,
) -> dict[str, Any]:
    """
    申请老年人优待证。

    Args:
        name: 申请人姓名
        id_number: 身份证号码
        birth_date: 出生日期

    Returns:
        申请结果
    """
    return {
        "status": "success",
        "data": {
            "application_id": f"EC{20260513001}",
            "name": name,
            "age": 65,
            "birth_date": birth_date,
            "benefit_type": "60-69周岁优待证",
            "status": "审批通过",
            "pickup_date": "2026-05-20",
        },
    }


@govmcp_tool(
    name="book_marriage_registration",
    description="预约婚姻登记",
)
def book_marriage_registration(
    name1: str,
    id_number1: str,
    name2: str,
    id_number2: str,
    book_date: str,
    location: str,
) -> dict[str, Any]:
    """
    预约婚姻登记。

    Args:
        name1: 申请人1姓名
        id_number1: 申请人1身份证号
        name2: 申请人2姓名
        id_number2: 申请人2身份证号
        book_date: 预约日期 (YYYY-MM-DD)
        location: 登记地点

    Returns:
        预约结果
    """
    return {
        "status": "success",
        "data": {
            "booking_id": f"MR{20260513001}",
            "applicant1": name1,
            "applicant2": name2,
            "book_date": book_date,
            "time_slot": "09:00-10:00",
            "location": location,
            "status": "预约成功",
            "notice": "请携带双方身份证、户口本、3张2寸合影照片",
        },
    }


@govmcp_tool(
    name="register_fertility_service",
    description="生育服务登记",
)
def register_fertility_service(
    name: str,
    id_number: str,
    spouse_name: str,
    spouse_id_number: str,
    expected_date: str,
) -> dict[str, Any]:
    """
    生育服务登记（准生证办理）。

    Args:
        name: 女方姓名
        id_number: 女方身份证号
        spouse_name: 男方姓名
        spouse_id_number: 男方身份证号
        expected_date: 预产期

    Returns:
        登记结果
    """
    return {
        "status": "success",
        "data": {
            "registration_id": f"FS{20260513001}",
            "woman_name": name,
            "man_name": spouse_name,
            "expected_date": expected_date,
            "status": "登记成功",
            "certificate_no": "生育服务证XXXXXX号",
            "valid_until": "2027-05-13",
        },
    }
