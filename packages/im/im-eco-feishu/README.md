# @deepseek-ai/dsh-im-eco-feishu

eco Agent 飞书助手：把飞书（Lark）长连接桥接到 eco Agent，实现持久会话、`/new` 新建会话、Markdown 回复、流式进度卡片、主动推送。

## 出处

本项目照搬自社区插件 [kriskwok/dsh-feishu-gateway](https://github.com/kriskwok/dsh-feishu-gateway)（v0.2.15，MIT License，见 [LICENSE](./LICENSE)）。仅将包名 rescope 为 `@deepseek-ai/dsh-im-eco-feishu`、本地 import 改为 `.ts` 扩展名、依赖改为 workspace 协议，业务逻辑保持原样（照搬，未重构）。

## 接入方式

1. 在 profile 的 `dsh.profile.bundles` 中列出本包（或把 [cordis.patch.yml](./cordis.patch.yml) 的行并入 profile 的 `cordis.patch.yml`）。
2. 配置项走飞书设置 namespace（`feishu.appId` / `feishu.appSecret`），可在设置界面或 profile patch 中调整。

## 关键配置

- `feishu.appId` / `feishu.appSecret`：飞书开放平台应用凭据
- 长连接监听，无需公网端点
