# 平台管理 · 自助添加平台 — 架构说明（前端扩展）

> 文档版本：v2.0（Kimi 合规重写）｜ 作者：高见远（架构）｜ 日期：2026-08-07
> 定位：本扩展是 **前端扩展**，严格遵循 Kimi `info.md` 技术铁律；后端 AI 能力统一收敛为既有 **Hermes agent（AI 基座）**，不新建独立后端服务、不引入数据库、不做反向代理注入。

---

## 0. 技术基线（必遵循 info.md 铁律）

- **React 18.3 + Vite 5.4 + TypeScript strict**（`npm run type-check` 必须零错误）
- **oxlint --deny-warnings** 零警告
- **纯 CSS**（`src/App.css` 已有完整类体系：left-nav / code-bar / nav-* / sop-bar / work-section / veto-scan / toggle / chat / hundred-board / enterprise / right-panel 等），**不加 Tailwind**
- 三栏：`LeftNav.tsx` / `MiddleWorkArea.tsx`（19 lazy 路由） / `RightToolPanel.tsx`（4 可折叠 section）
- 数据层：`src/data/{enterprises,vetoItems,discretionTables,docTemplates,knowledgeBase,platforms}.ts` —— 平台数据与白名单模板扩展写 `platforms.ts`

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────┐
│  前端（React 18 + Vite + 纯CSS）                       │
│  ├─ 平台管理路由（MiddleWorkArea）：概览条 + 2列卡片   │
│  │   + 每日巡检报告区 + 「＋添加平台」虚线卡 + 向导     │
│  ├─ 登录壳组件（按白名单模板生成，非 iframe）          │
│  └─ 数据层 src/data/platforms.ts（6真实卡 + 自定义卡）  │
└───────────────┬───────────────────────┬──────────────┘
                │ 既有 agent 调用通道     │ 本机加密存储
                ▼                         ▼
        ┌────────────────┐        ┌────────────────┐
        │ Hermes agent    │        │ 凭据加密库      │
        │ （AI 基座）      │        │（浏览器端加密） │
        │ ·白名单匹配      │        │ 不出本机        │
        │ ·登录壳字段生成  │        └────────────────┘
        │ ·验证码抓取识别  │
        │ ·会话保活/续期   │
        └────────────────┘
```

**不引入**：独立后端服务（FastAPI/Node）、独立数据库（PostgreSQL）、反向代理（Nginx+Lua / F5）注入。

---

## 2. 前端扩展落点

### 2.1 视图层（MiddleWorkArea · 平台管理路由）
- 在 platforms 现有视图**末尾**追加：「＋添加平台」虚线卡（§3 UIUX）+ 自助添加向导（步骤 0 粘贴匹配 → 步骤 1–3 沿用 Kimi 三步引导）。
- 概览条、2 列卡片网格、每日巡检报告区**沿用 platforms.md**，仅新增卡与计数 +1。

### 2.2 数据层（src/data/platforms.ts）
- 既有：6 真实平台卡（状态/数据）。
- 新增：`PlatformCustom` 类型（自定义添加平台）+ `whitelistTemplates` 表：
  ```ts
  interface WhitelistTemplate {
    id: string;
    name: string;            // 平台名
    purpose: string;         // 用途一句（人话）
    loginFields: ('account'|'password'|'captcha')[]; // 登录壳字段
    captchaType: 'simple'|'complex';                // 验证码类型预判
    mfa: boolean;            // 是否 MFA（true→标记不支持自动）
  }
  ```
- 状态枚举严格为 Kimi 四态：`'ai-managed' | 'waiting-first-login' | 'configuring' | 'error'`（对应 AI代管中 / 待人工首次登录 / 接入配置中 / 异常）。

### 2.3 组件层
- **复用**：卡片、状态徽章、弹窗、Toast、toggle、进度条、空态、AI 专家芯片（均来自 design.md 共享组件与既有组件）。
- **新增（仅 2 个）**：① 登录壳（`LoginShell`，按模板渲染账号/密码/验证码）② 向导第 0 步（粘贴地址 + 匹配结果）。
- 不新造状态、不改三栏布局、不加新色值。

---

## 3. 与 Hermes agent 的交互契约（内部）

> 前端通过**既有 agent 调用通道**与 Hermes agent 交互（具体通道由平台现有机制决定，本扩展不新建）。契约如下：

| 前端动作 | 请求 Hermes | 基座响应 | 前端呈现 |
|---|---|---|---|
| 提交粘贴地址 | 匹配白名单 | 命中模板 / 未命中 | "认出来了 ✓" / 温和拦截 |
| 请求登录壳字段 | 生成字段定义 | 该平台 loginFields + captchaType | EcoAegis 风格登录界面 |
| 抓取验证码 | 抓图 + 识别 | 图 + {recognized: true,text} / {recognized:false} | 预填 / 转人工 |
| 提交登录凭据 | 建会话 | 接通 / 失败 | AI代管中 / 错误提示 |
| 心跳保活 | 探活 | 正常 / 异常 | 维持 / 异常态 |

**约束（与 PRD §5 一致）**：MFA 平台不自动接入；凭据不出本机；非技术化语言。

---

## 4. 凭据与存储

- **本机加密存储**：凭据在浏览器端加密（Web Crypto / 既有加密工具），存于本机，不上传、不落明文。
- 「记住账号」开关控制是否持久化；可在设置统一查看/清除（沿用 settings.md）。
- 机构级恢复（P1）：由 Hermes agent 协调的托管机制兜底，避免单人丢失。

---

## 5. 约束与错误处理

- **MFA 不自动**：白名单模板 `mfa=true` 的平台，向导不进入自动流程，卡片标记「需人工激活 / 不支持自动接入」（琥珀提示）。
- **登录失败** → `error` 态（赤陶红）；会话过期 → `error` 态 + 提示重登。
- **验证码识别失败** → 登录壳转人工态（autofocus），不阻塞。
- **非白名单** → 温和拦截，不报错、不崩。

---

## 6. 与既有模块关系

- `platforms.md`：本扩展唯一落点，页面骨架与四态全部沿用。
- `rightpanel.md`：Hermes 记忆进化面板（既有基座能力展示），本扩展复用。
- `settings.md`：凭据加密存储统一入口。
- `mcp.md`：内部概念一致，对用户不提。

*文档结束。本架构为前端扩展，后端智能能力全部由 Hermes agent 提供，不新建服务栈。*
