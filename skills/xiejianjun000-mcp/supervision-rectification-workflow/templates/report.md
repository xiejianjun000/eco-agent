# 大气监督帮扶督办整改分析报告

**地区**：{{REGION}}  
**时间范围**：{{START_DATE}} 至 {{END_DATE}}  
**生成时间**：{{GENERATED_AT}}  
**轮次**：{{ROUND}}

---

## 一、总体概况

| 指标 | 数值 | 占比 |
|------|------|------|
| 总记录数 | {{TOTAL_RECORDS}} | 100% |
| 已完成整改 | {{COMPLETED}} | {{COMPLETED_RATE}}% |
| 未完成整改 | {{UNCOMPLETED}} | {{UNCOMPLETED_RATE}}% |
| 省级审核通过 | {{PROVINCIAL_APPROVED}} | {{PROVINCIAL_RATE}}% |
| 部级审核通过 | {{MINISTRY_APPROVED}} | {{MINISTRY_RATE}}% |
| **可销号** | **{{CAN_WRITEOFF}}** | **{{CAN_WRITEOFF_RATE}}%** |
| 不可销号 | {{CANNOT_WRITEOFF}} | {{CANNOT_WRITEOFF_RATE}}% |

---

## 二、问题类别分布

{{#PROBLEM_CATEGORIES}}
### {{CATEGORY_NAME}}
- **记录数**：{{COUNT}}
- **已整改**：{{COMPLETED}}
- **销号状态**：{{WRITEOFF_STATUS}}

{{/PROBLEM_CATEGORIES}}

---

## 三、重点问题企业

### 3.1 未完成整改企业

{{#UNCOMPLETED_ENTERPRISES}}
#### {{ENTERPRISE_NAME}}
- **统一社会信用代码**：{{CREDIT_CODE}}
- **问题类别**：{{PROBLEM_CATEGORY}}
- **问题描述**：{{PROBLEM_DESCRIPTION}}
- **检查时间**：{{INSPECTION_TIME}}
- **整改状态**：{{RECTIFICATION_STATUS}}
- **省级审核**：{{PROVINCIAL_AUDIT}}
- **部级审核**：{{MINISTRY_AUDIT}}
- **销号状态**：{{WRITEOFF_STATUS}}
- **备注**：{{REMARKS}}

{{/UNCOMPLETED_ENTERPRISES}}

### 3.2 部级审核未通过企业

{{#MINISTRY_REJECTED}}
#### {{ENTERPRISE_NAME}}
- **问题描述**：{{PROBLEM_DESCRIPTION}}
- **部级审核意见**：{{MINISTRY_COMMENTS}}
- **需补充材料**：{{REQUIRED_MATERIALS}}
- **建议**：{{SUGGESTIONS}}

{{/MINISTRY_REJECTED}}

---

## 四、销号情况分析

### 4.1 可销号记录（{{CAN_WRITEOFF}}条）

{{#CAN_WRITEOFF_RECORDS}}
#### 记录{{INDEX}}：{{ENTERPRISE_NAME}}
- ✅ 省级审核通过
- ✅ 部级审核通过
- ✅ 符合销号条件
- **建议**：可以执行销号操作

{{/CAN_WRITEOFF_RECORDS}}

### 4.2 不可销号记录（{{CANNOT_WRITEOFF}}条）

{{#CANNOT_WRITEOFF_RECORDS}}
#### 记录{{INDEX}}：{{ENTERPRISE_NAME}}
- **不可销号原因**：{{REASON}}
- **当前状态**：{{CURRENT_STATUS}}
- **需采取措施**：{{ACTIONS_NEEDED}}

{{/CANNOT_WRITEOFF_RECORDS}}

---

## 五、整改效果良好的企业

{{#GOOD_ENTERPRISES}}
### {{ENTERPRISE_NAME}}
- ✅ 问题已全部整改完成
- ✅ 省级审核通过
- ✅ 部级审核通过
- ✅ 可以销号
- **经验总结**：{{EXPERIENCE}}

{{/GOOD_ENTERPRISES}}

---

## 六、法规依据

根据《监督帮扶问题整改督办工作规程（试行）》（2024年7月修订）：

### 6.1 销号条件
1. 市级确认整改完成
2. 省级审核通过（审核整改材料是否符合要求）
3. 部级抽查通过

### 6.2 不同问题类别的销号材料要求

| 问题类别 | 必需材料 |
|----------|----------|
{{#MATERIAL_REQUIREMENTS}}
| {{CATEGORY}} | {{MATERIALS}} |
{{/MATERIAL_REQUIREMENTS}}

---

## 七、行动建议

### 7.1 立即行动

{{#IMMEDIATE_ACTIONS}}
1. **{{ACTION_TITLE}}**
   - 对象：{{TARGET}}
   - 措施：{{MEASURES}}
   - 时限：{{DEADLINE}}

{{/IMMEDIATE_ACTIONS}}

### 7.2 长期改进

{{#LONG_TERM_ACTIONS}}
1. **{{ACTION_TITLE}}**
   - 目标：{{GOAL}}
   - 措施：{{MEASURES}}

{{/LONG_TERM_ACTIONS}}

---

## 八、附件清单

1. `{{REGION}}_督办整改_{{START_DATE}}_至_{{END_DATE}}.json` - 原始数据
2. `{{REGION}}_省级审核记录_{{GENERATED_AT}}.json` - 省级审核完整记录
3. `检查详情_*.json` - 各企业检查详情
4. 本报告 - 完整分析

---

## 九、备注说明

1. 本报告基于《监督帮扶问题整改督办工作规程（试行）》标准生成
2. 销号判断依据：省级审核✅ + 部级审核✅
3. 整改完成 ≠ 销号，销号需满足完整审核流程
4. 数据提取时间：{{GENERATED_AT}}

---

**报告结束**
