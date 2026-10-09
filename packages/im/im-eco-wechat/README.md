# @eco-agent/dsh-im-eco-wechat

English | [中文](README.zh.md)

eco Agent WeChat assistant: bridges a personal WeChat account (Tencent iLink / ClawBot official open protocol) into eco Agent, with QR-code login, allowlist control, streaming replies, scheduled tasks, and web fetching (MCP).

## Provenance

This package is copied from the community plugin [zxz9988/dsh-wechat-bridge](https://github.com/zxz9988/dsh-wechat-bridge) (v0.5.1, MIT License, see [LICENSE](./LICENSE) and [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)). Only the package name was rescoped to `@eco-agent/dsh-im-eco-wechat` and dependencies were switched to the workspace protocol; the business logic stays as-is (copied, not refactored).

## Wiring it in

1. List this package in the profile's `dsh.profile.bundles` (or merge the [cordis.patch.yml](./cordis.patch.yml) lines into the profile's `cordis.patch.yml`).
2. Configuration lives in the plugin `Config` (`enabled` / `token` / `accountId` / `baseUrl` / allowlist), adjustable in the settings UI or the profile patch.
3. On first enablement leave `token` empty and scan the QR code to log in to the personal WeChat account.

## Key configuration

- `enabled`: master switch
- `token` / `accountId`: iLink Bot credentials (leave empty to log in by QR scan, recommended)
- Allowlist `allowFrom`: only contacts on the list are served (hard safety rule, keep it tight)
