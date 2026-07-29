# ECO AGENT 多平台接入配置指南

> **飞书 · 企业微信 · 钉钉 · 微信 接入配置说明**
> 版本：v0.1.0

---

## 通用说明

所有平台均通过统一网关服务（`gateway/eco-gateway-server.py`）接入。

### 快速启动

```bash
# 开发模式（单端口 7070）
python gateway/eco-gateway-server.py --port 7070

# 生产模式
python gateway/eco-gateway-server.py --host 0.0.0.0 --port 7070
```

### ngrok 内网穿透（开发调试）

```bash
ngrok http 7070
# 将 https://xxx.ngrok.io 配置到各平台 Webhook URL
```

---

## 1. 飞书接入

### 前置条件
- 飞书企业版/旗舰版账号
- 管理员权限创建应用

### 创建步骤

1. **打开飞书开发者后台** https://open.feishu.cn/app
2. **创建企业自建应用**
   - 应用名称：`ECO AGENT 执法助手`
   - 应用描述：生态环境执法 AI 辅助系统

3. **配置权限**
   ```
   im:message           - 消息读写
   im:resource          - 获取图片/文件
   contact:contact      - 通讯录只读
   drive:drive          - 云文档只读
   approval:approval    - 审批读写
   ```

4. **配置事件回调**
   ```
   请求地址：https://your-domain/webhook/feishu
   事件订阅：
     - im.message.receive_v1（接收消息）
     - approval.approved（审批通过）
     - approval.rejected（审批拒绝）
   ```

5. **发布应用** → **企业管理员审批**

6. **设置环境变量**
   ```bash
   export FEISHU_APP_ID=cli_xxxxxxx
   export FEISHU_APP_SECRET=xxxxxxxx
   export FEISHU_VERIFICATION_TOKEN=xxxxxx
   ```

### 使用方式
```python
from gateway.platforms.feishu_bot import FeishuBot
bot = FeishuBot()
bot.send_text("open_id", "消息内容")
```

---

## 2. 企业微信接入

### 前置条件
- 企业微信管理员账号
- 已认证的企业微信

### 创建步骤

1. **打开企业微信管理后台** https://work.weixin.qq.com/wework_admin/frame#apps
2. **创建应用**
   - 应用名称：`ECO AGENT`
   - 应用描述：生态环境执法 AI 辅助系统
   - 可见范围：选择可用人员

3. **配置接收消息**
   ```
   URL：https://your-domain/webhook/wecom
   Token：自定义（与 WECOM_TOKEN 一致）
   EncodingAESKey：随机生成
   ```

4. **配置企业可信 IP**
   - 添加服务器公网 IP

5. **设置环境变量**
   ```bash
   export WECOM_CORP_ID=wwxxxxxxx
   export WECOM_AGENT_ID=100000x
   export WECOM_SECRET=xxxxxxxx
   export WECOM_TOKEN=xxxxxxxx
   export WECOM_ENCODING_AES_KEY=xxxxxxxx
   ```

### 使用方式
```python
from gateway.platforms.wecom_bot import WecomBot
bot = WecomBot()
bot.send_text("user_id", "消息内容")
# 或发送卡片消息
bot.send_text_card("user_id", "标题", "描述内容")
```

---

## 3. 钉钉接入

### 前置条件
- 钉钉企业版账号
- 管理员权限

### 创建步骤

1. **打开钉钉开放平台** https://open.dingtalk.com
2. **创建应用**
   - 应用类型：企业应用
   - 应用名称：`ECO AGENT`

3. **配置机器人**
   - 机器人名称：`ECO AGENT 执法助手`
   - 机器人简介：生态环境执法 AI 辅助系统
   - 消息接收模式：HTTP
   - 消息接收地址：`https://your-domain/webhook/dingtalk`

4. **配置权限**
   ```
   qyapi_chat_manage      - 企业群消息
   qyapi_calendar         - 日历
   qyapi_approval         - 审批
   ```

5. **设置环境变量**
   ```bash
   export DINGTALK_APP_KEY=dingxxxxxxx
   export DINGTALK_APP_SECRET=xxxxxxxx
   export DINGTALK_ROBOT_CODE=xxxxxxxx
   ```

### 使用方式
```python
from gateway.platforms.dingtalk_bot import DingTalkBot
bot = DingTalkBot()
bot.send_text("user_id", "消息内容")
# 或发送群消息
bot.send_group_message("group_open_id", "消息内容")
```

---

## 4. 微信接入

### 4.1 微信公众平台（推荐）

#### 前置条件
- 已认证的微信服务号或订阅号

#### 创建步骤
1. **登录微信公众平台** https://mp.weixin.qq.com
2. **开发 → 基本配置 → 服务器配置**
   ```
   URL：https://your-domain/webhook/wechat
   Token：自定义（与 WECHAT_TOKEN 一致）
   EncodingAESKey：随机生成
   ```

3. **设置环境变量**
   ```bash
   export WECHAT_APP_ID=wxxxxxxx
   export WECHAT_APP_SECRET=xxxxxxxx
   export WECHAT_TOKEN=xxxxxxxx
   export WECHAT_ENCODING_AES_KEY=xxxxxxxx
   ```

#### 使用方式
```python
from gateway.platforms.wechat_bot import WechatBot
bot = WechatBot()
bot.send_template_msg("open_id", "消息内容")
```

### 4.2 Wechaty（个人微信，可选）

#### 前置条件
- Node.js 环境
- Wechaty Token（商业版）或免费 Puppet

#### 安装
```bash
npm install -g wechaty
# 或使用 Docker
docker pull wechaty/wechaty
```

#### 配置
```bash
export WECHATY_TOKEN=your_token
export WECHATY_PUPPET=wechaty-puppet-service
```

---

## 5. 各平台审批集成

| 平台 | 审批能力 | 配置位置 |
|:-----|:---------|:---------|
| **飞书** | ✅ 完整审批 + 交互卡片 | 飞书开发者后台 → 审批应用 |
| **企业微信** | ✅ 完整审批 + 模板 | 企业微信管理后台 → 审批 |
| **钉钉** | ✅ 完整审批 + 流程 | 钉钉开放平台 → 审批 |
| **微信** | ❌ 不支持审批 | — |

### 审批风险等级

| 等级 | 说明 | 处理方式 |
|:-----|:------|:---------|
| 🔴 高风险 | 处罚 ≥ 5万元 / 责令停产 / 移送公安 | 必须人工审批 |
| 🟡 中风险 | 处罚 1-5万元 / 查封扣押 | 建议人工审批 |
| 🟢 低风险 | 处罚 < 1万元 / 警告 | 自动处理 |

---

## 6. 验证部署

```bash
# 1. 启动网关服务
cd /path/to/ECO_AGENT
python gateway/eco-gateway-server.py

# 2. 测试健康检查
curl http://localhost:7070/health

# 3. 查看状态
curl http://localhost:7070/

# 4. 在各平台发送消息测试
# 飞书：向 Bot 发送 "帮助"
# 企业微信：向应用发送 "帮助"
# 钉钉：向机器人发送 "帮助"
# 微信：向公众号发送 "帮助"
```
