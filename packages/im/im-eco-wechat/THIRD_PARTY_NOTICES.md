# Third-Party Notices

本插件（dsh-wechat-bridge）的第三方依赖与声明如下。本插件自身代码为原创，
采用 MIT 许可证（见 LICENSE）。

## qrcode (MIT)

- 包名：`qrcode`（node-qrcode，soldair 项目）
- 用途：把微信登录链接在本地编码成二维码图片（登录页展示用，不经过任何第三方服务）
- 来源：https://github.com/soldair/node-qrcode
- 许可证：MIT License（原文见本文件末尾通用 MIT 文本，版权所有：Ryan Day 及贡献者）

## wechat-ilink-client (MIT)

- 包名：`wechat-ilink-client`
- 用途：微信 iLink Bot 协议客户端（登录、长轮询收消息、发送文字/媒体消息）
- 来源：https://github.com/photon-hq/wechat-ilink-client
- 许可证：MIT License
- 说明：该项目是腾讯官方开源包 `@tencent-weixin/openclaw-weixin` 的独立 TypeScript
  实现，零运行时依赖、无状态。本插件仅以 npm 依赖方式使用其公开 API
  （`WeChatClient`、`MessageType`、`MessageItemType`、`TypingStatus`），
  未修改其源码。

MIT License 原文（适用于上述 qrcode 与 wechat-ilink-client 两个依赖，版权归各自项目的贡献者所有）：

> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in
> all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

## 网页抓取 MCP 服务器（mcp/fetch-server）依赖

配套的极简 fetch MCP 服务器（可选安装）依赖以下两个包，均为 MIT 许可，
按各自项目的版权声明执行（MIT 原文同上）：

- `@modelcontextprotocol/sdk`（Model Context Protocol 官方 TypeScript SDK）
  来源：https://github.com/modelcontextprotocol/typescript-sdk
- `zod`（schema 校验库）
  来源：https://github.com/colinhacks/zod

## 腾讯微信 iLink / ClawBot 协议

- 本插件通过腾讯官方开放的「微信 ClawBot 插件功能」接入微信，底层协议为
  iLink（域名 `ilinkai.weixin.qq.com`）。
- 使用该服务须遵守腾讯《微信 ClawBot 功能使用条款》。
- 本插件不包含腾讯官方包 `@tencent-weixin/openclaw-weixin` 的任何代码；
  协议端点信息来源于腾讯官方开源的协议实现与其公开文档。

## 关于 CC-Connect

- 本插件在功能概念上参考了 CC-Connect（微信消息中转桥接）的公开使用场景，
  但**未使用、未复制、未修改 CC-Connect 的任何代码、配置、文档或品牌元素**。
- CC-Connect 为 MIT 许可项目（npm 包 `cc-connect`）；本项目选择完全不使用其
  代码的独立实现路线，因此不承担、也不需要其许可下的署名义务。
