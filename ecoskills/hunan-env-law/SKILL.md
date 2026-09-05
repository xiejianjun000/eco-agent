---
name: hunan-env-law
description: 湖南生态环境智慧执法办案系统自动化操作。支持登录、查询案卷台账、批量下载案卷PDF。用于军哥的环保执法日常工作——读取冷水江市案卷、打包下载案卷材料、按年度归档。触发词：湖南执法平台、案卷台账、冷水江案卷、打包下载、环保案卷、zfyth、环境执法办案系统。
risk_level: high
version: 1.0.0
---

# 湖南生态环境智慧执法办案系统

## 平台信息

| 项目 | 信息 |
|------|------|
| URL | `http://113.246.57.20:8507/zfyth/index` |
| 技术栈 | AngularJS (BoandaApp) |
| 用户名 | xiejianjun |
| 密码 | Hnzfyth@2022 |
| 身份 | 娄底市生态环境局冷水江分局 · 谢建军 |
| 技术支持 | 深圳博沃智慧科技有限公司 |

## 快速开始

### 登录

登录需处理**算术验证码**（如 `5+29`），密码需 AES-ECB 加密。

```bash
python3 scripts/login.py
```

成功后在 `/tmp/zfyth_cookies.pkl` 保存 session。

### 获取案卷列表

登录后查询案卷台账，详见 [platform.md](references/platform.md)。

## 主菜单结构

```
执法数据库 → 执法视窗 → 移动执法 → 综合办案 → 装备调度 → 实战练兵
                                          ├── 案件填报
                                          ├── 案卷台账  ← 主要入口
                                          ├── 文书管理
                                          ├── 文书下载
                                          └── 自由裁量
```

## 案卷台账操作

### 查询案卷

进入 综合办案 → 案卷台账，页面在 iframe 内加载。支持筛选：
- 立案时间、决定下达日期
- 案卷类型（一般处罚/按日处罚/限产停产/查封扣押/行政拘留等）
- 行政区划（可多级 Cascader）
- 审核状态、违法案件类型
- 步骤阶段（立案审批/调查终结/处罚告知/处罚决定/执行结案等）

### 下载案卷

1. 点击案卷行的「编辑」→ 打开编辑面板
2. 在「立案审批附件」区域找到「打包下载」按钮
3. 点击下载 → PDF 保存到本地

目前通过 Python API 直接获取案卷列表和编辑页面内容，但「打包下载」的确切 API 端点尚未定位。工作方式：
- 获取案卷列表：通过 API 查询
- 下载文件：需要浏览器交互（点击编辑→打包下载）

## 验证码处理

平台使用**算术验证码**，ddddocr 识别后需计算表达式结果：

```python
import ddddocr, re

ocr = ddddocr.DdddOcr(show_ad=False)
code = ocr.classification(image_bytes)  # e.g. "5+29"
result = str(eval(re.findall(r"[\d+\-*]+", code)[0]))  # compute answer
```

## 关键 API（探索中）

| API | 用途 | 状态 |
|-----|------|------|
| `POST /login` | 登录（需XTZH/YHMM/validateCode） | ✅ |
| `GET /code` | 获取验证码图片 | ✅ |
| `GET /platform/tools/toolcontroller/qgy` | 获取RSA公钥 | ✅ |
| `POST /general/punishment/findlist` | 查询案卷列表 | ✅ |
| `GET /general/punishment/ybcfinfo/{XH}/{LCDYBH}/{isView}` | 案卷编辑页 | ✅ |
| `GET /general/punishment/getwslist/{XH}/{LCDYBH}/{isView}` | 案卷文档树 | ❌ 500 |
| `POST /task/taskdesk/printall` | 批量导出PDF | ❌ 500 |

## 加密方式

密码传输使用双重加密：
1. Base64 编码原文
2. AES-ECB 加密（密钥 `boandaxxjsgfyxgs`，PKCS7 padding）
3. 最终 Base64 输出

```python
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import base64

key = b"boandaxxjsgfyxgs"
cipher = AES.new(key, AES.MODE_ECB)
password_b64 = base64.b64encode("Hnzfyth@2022".encode()).decode()
encrypted = base64.b64encode(cipher.encrypt(pad(password_b64.encode(), 16))).decode()
```

## 案卷保存规则

下载的案卷 PDF 保存到 `/Users/mac/Documents/谢建军/案卷/`，按年度创建子文件夹：
- `2025/` — 2025 年案卷
- `2026/` — 2026 年案卷

下载前对比已有文件，避免重复下载。

## 相关平台

国家生态环境行政处罚案件管理信息系统：`http://114.251.10.24:7070/cas/login`
- 账号：431381 / <密码见 .env>
- 身份：冷水江市本级
- 平台类型：CAS + kaptcha 验证码
- JWT Token 有效期约 8 小时

## 工作流程

```
Step 1: 登录——scripts/login.py 处理算术验证码 + AES-ECB 加密，session 落盘
Step 2: 查案卷台账——综合办案 → 案卷台账，按立案时间/案卷类型/行政区划/步骤阶段筛选
Step 3: 打包下载——编辑面板 → 立案审批附件 → 打包下载 → PDF 落盘
Step 4: 归档——按年度建子目录（2025/、2026/），下载前对比已有文件避免重复
```

## 引用纪律

- 平台接口与参数以实际抓包/API 返回为准（来源：平台响应报文），不得凭记忆臆造端点。
- 未定位的接口（如打包下载）标注 [待确认]，按浏览器交互兜底执行。

## 禁用领域

- ⚠️ 不得对外泄露平台账号、密码、AES 密钥及案卷涉密信息。
- ⚠️ 下载的案卷仅限军哥本人执法工作使用，不得外传或用于非执法用途。
- ⚠️ 不得修改、篡改平台上的原始案卷数据。
