#!/usr/bin/env python3
"""
govmcp.tools.government — 政务工具库

提供市民服务、企业服务、碳排放管理、环保监测、智慧城市、审批工作流等100+政务服务工具。
"""

from govmcp.tools.government.approval_workflow import (
    apply_approval_digital_signature,
    configure_approval_permission,
    generate_approval_document,
    handle_approval_counter_sign,
    handle_approval_delegation,
    handle_approval_joint_sign,
    handle_approval_suspend_resume,
    handle_approval_transfer,
    initiate_approval_workflow,
    manage_approval_archive,
    manage_approval_template,
    query_approval_progress,
    query_approval_statistics,
    query_approval_warning,
    submit_approval_comment,
)
from govmcp.tools.government.carbon_emission import (
    analyze_industrial_carbon_emission,
    apply_carbon_verification,
    calculate_carbon_footprint,
    generate_carbon_emission_report,
    input_carbon_emission_data,
    predict_carbon_emission,
    query_carbon_asset_account,
    query_carbon_monitoring_data,
    query_carbon_quota,
    query_energy_consumption,
    query_green_electricity_trade,
    register_ccer_project,
    set_emission_reduction_target,
    track_carbon_neutrality_progress,
    trade_carbon_emission_allowance,
)
from govmcp.tools.government.citizen_service import (
    apply_disability_subsidy,
    apply_elderly_benefit_card,
    apply_housing_fund_withdrawal,
    apply_low_income_assistance,
    book_marriage_registration,
    query_driver_license,
    query_household_registration,
    query_housing_fund_account,
    query_housing_fund_loan,
    query_id_card_progress,
    query_medical_insurance_account,
    query_medical_settlement,
    query_property_registration,
    query_residence_permit,
    query_social_security_account,
    query_social_security_payment,
    query_traffic_violation,
    query_utility_bill,
    query_vehicle_info,
    register_fertility_service,
)
from govmcp.tools.government.enterprise_service import (
    apply_business_license,
    apply_drug_operation_license,
    apply_food_business_license,
    apply_high_tech_enterprise,
    apply_housing_fund_account_enterprise,
    apply_intellectual_property,
    apply_invoice,
    apply_medical_device_license,
    apply_social_security_account,
    apply_tech_project,
    query_building_permit,
    query_business_registration,
    query_enterprise_credit_report,
    query_environmental_impact_approval,
    query_fire_approval,
    query_government_procurement,
    query_listing_guidance_progress,
    query_patent_application,
    query_tax_registration,
    query_trademark_registration,
)
from govmcp.tools.government.environmental import (
    apply_cleaner_production_audit,
    detect_soil_pollution,
    query_air_quality,
    query_ecological_red_line,
    query_environmental_acceptance,
    query_environmental_emergency_response,
    query_environmental_facility_operation,
    query_environmental_impact_assessment,
    query_environmental_penalty,
    query_hazardous_waste_transfer,
    query_noise_monitoring,
    query_pollution_discharge_permit,
    query_radiation_monitoring,
    query_solid_waste_disposal,
    query_water_quality,
)
from govmcp.tools.government.smart_city import (
    book_smart_medical,
    control_smart_traffic_light,
    dispatch_emergency_command,
    manage_smart_heating,
    manage_smart_streetlight,
    monitor_smart_water,
    query_grid_management,
    query_public_bicycle,
    query_public_parking,
    query_smart_city_enforcement,
    query_smart_community,
    query_smart_education,
    query_smart_elderly_care,
    query_snow亮的视频,
    supervise_smart_gas,
)

__all__ = [
    "citizen_service",
    "enterprise_service",
    "carbon_emission",
    "environmental",
    "smart_city",
    "approval_workflow",
]

TOOL_COUNT = {
    "citizen_service": 20,
    "enterprise_service": 20,
    "carbon_emission": 15,
    "environmental": 15,
    "smart_city": 15,
    "approval_workflow": 15,
}

TOTAL_TOOLS = sum(TOOL_COUNT.values())
