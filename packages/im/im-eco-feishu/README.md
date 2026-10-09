# @eco-agent/dsh-im-eco-feishu

English | [中文](README.zh.md)

eco Agent Feishu assistant: bridges Feishu (Lark) long connection into eco Agent, with persistent sessions, `/new` session creation, Markdown replies, streaming progress cards, and proactive push.

## Provenance

This package is copied from the community plugin [kriskwok/dsh-feishu-gateway](https://github.com/kriskwok/dsh-feishu-gateway) (v0.2.15, MIT License, see [LICENSE](./LICENSE)). Only the package name was rescoped to `@eco-agent/dsh-im-eco-feishu`, local imports were changed to `.ts` extensions, and dependencies were switched to the workspace protocol; the business logic stays as-is (copied, not refactored).

## Wiring it in

1. List this package in the profile's `dsh.profile.bundles` (or merge the [cordis.patch.yml](./cordis.patch.yml) lines into the profile's `cordis.patch.yml`).
2. Configuration lives in the Feishu settings namespace (`feishu.appId` / `feishu.appSecret`), adjustable in the settings UI or the profile patch.

## Key configuration

- `feishu.appId` / `feishu.appSecret`: Feishu Open Platform app credentials
- Long-connection listener; no public endpoint required
