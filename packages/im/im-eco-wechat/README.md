# @deepseek-ai/dsh-im-eco-wechat

eco Agent 微信助手：把个人微信（腾讯 iLink / ClawBot 官方开放协议）桥接到 eco Agent，实现扫码登录、白名单控制、流式回复、定时任务、网页抓取（MCP）。

## 出处

本项目照搬自社区插件 [zxz9988/dsh-wechat-bridge](https://github.com/zxz9988/dsh-wechat-bridge)（v0.5.1，MIT License，见 [LICENSE](./LICENSE) 与 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)）。仅将包名 rescope 为 `@deepseek-ai/dsh-im-eco-wechat` 并改为 workspace 依赖，业务逻辑保持原样（照搬，未重构）。

## 接入方式

1. 在 profile 的 `dsh.profile.bundles` 中列出本包（或把 [cordis.patch.yml](./cordis.patch.yml) 的行并入 profile 的 `cordis.patch.yml`）。
2. 配置项走插件 `Config`（`enabled` / `token` / `accountId` / `baseUrl` / 白名单等），可在设置界面或 profile patch 中调整。
3. 首次启用留空 `token`，扫码登录个人微信。

## 关键配置

- `enabled`：总开关
- `token` / `accountId`：iLink Bot 凭据（留空则扫码登录，推荐）
- 白名单 `allowFrom`：只允许名单内的联系人（安全铁律，建议收紧）
