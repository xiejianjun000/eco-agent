# 湖南执法平台 API 参考

## 认证机制

### 登录流程
```
1. GET /zfyth/code → 验证码图片（算术题，格式如 "5+29"）
2. POST /zfyth/login → JSON body: {XTZH, YHMM, smsCode, validateCode}
```

### 密码加密
```python
1. Base64(username) → XTZH
2. Base64(password) → AES-ECB(key="boandaxxjsgfyxgs") → Base64 → YHMM
```

### 验证码
- 类型：算术题（加法/减法/乘法）
- 格式：`?+?`、`?-?`、`?*?`
- 提交：计算结果（非表达式原文）
- OCR：ddddocr 识别 → 正则提取 → eval 计算

## API 端点

### 案卷台账查询
```
POST /zfyth/general/punishment/findlist
Content-Type: application/x-www-form-urlencoded

参数:
  page: 页码
  rows: 每页条数
  serviceParam: JSON 字符串
    {
      "LASJ_START": "开始立案日期",
      "LASJ_END": "结束立案日期",
      "CJSJ_START": "开始创建日期",
      "CJSJ_END": "结束创建日期",
      "SSQX": "行政区划代码（空=全部）"
    }
```

### 案卷编辑页
```
GET /zfyth/general/punishment/ybcfinfo/{XH}/{LCDYBH}/true
返回: HTML 页面（AngularJS 渲染）
```

### 案卷文档树
```
GET /zfyth/general/punishment/getwslist/{XH}/{LCDYBH}/true
返回: JSON（文档目录树）
状态: ❌ 当前返回 500
```

### 批量导出
```
POST /zfyth/task/taskdesk/printall
参数: {XH, LCDYBH, type: "PDF"}
状态: ❌ 当前返回 500
```

## 案卷数据结构

```json
{
  "XH": "唯一标识",
  "LAH": "立案号（如 娄环冷立字[2026]8号）",
  "DSRMC": "当事人名称",
  "LASJ": "立案日期",
  "LASJ_NUM": "立案天数",
  "CJSJ": "创建时间",
  "SSQX_MC": "所属区县",
  "SSDS_MC": "所属地市",
  "WFAJLX": "违法案件类型",
  "AJLXMC": "案卷类型",
  "BZJD": "步骤阶段",
  "AQJJ": "案情简介",
  "CJR": "创建人ID",
  "ORGID": "机构ID"
}
```

## 案卷类型
- 发起立案 (FQLA)
- 一般处罚
- 按日处罚
- 限产停产
- 查封扣押 / 查封扣押(不含罚)
- 行政拘留
- 涉嫌环境犯罪
- 不予处罚

## 违法案件类型
水 / 气 / 噪声 / 固废 / 土壤 / 海洋 / 自然保护区（饮用水水源地）/ 新化学物质 / 建设项目 / 核与辐射 / 碳排放 / 消耗臭氧层物质 / 其他
