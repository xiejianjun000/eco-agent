#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用 Chrome CDP WAF 绕过桥接器 v1.0
====================================

从 CEPC MCP 项目中提炼的通用组件，可复用于任何受 WAF（阿里云盾/Akamai/Cloudflare 等）
防护的 Web 系统的自动化访问。

核心原理：
  WAF 检测的是自动化框架的 CDP artifacts（Playwright/Selenium 注入的调试协议调用），
  而非 Chrome 本身。通过 child_process 直接启动真 Chrome（不经过任何自动化框架包装），
  WAF 的 JS 挑战在真实 Chrome JS 引擎中自动执行通过。

使用方式：
  from chrome_cdp_bridge import ChromeCDPBridge, BridgeConfig

  config = BridgeConfig(
      target_url="https://example.com",
      api_prefix="/api/v1",
      chrome_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      login_url="/login",
      captcha_api="/captcha",
      account="myuser",
      password="mypass",
  )

  bridge = ChromeCDPBridge(config)
  await bridge.start()        # 启动 Chrome + CDP
  await bridge.pass_waf()     # 绕过 WAF
  await bridge.login()        # 自动登录
  result = await bridge.fetch_api("users/list")  # 调用 API

依赖：
  pip install websockets ddddocr pillow
  # 或使用 Node.js 桥接（无需 websockets）：
  Node.js + ws 包

作者：执法督察评查专家团 · 费执衡
日期：2026-08-23
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Dict

log = logging.getLogger("chrome_cdp_bridge")


@dataclass
class BridgeConfig:
    """桥接器配置"""

    # 目标系统
    target_url: str = ""                    # 目标系统 URL（如 https://example.com）
    api_prefix: str = ""                   # API 前缀（如 /api/v1 或 /jeeplus-vue）

    # Chrome 配置
    chrome_path: str = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    cdp_port: int = 9230
    chrome_profile: str = "/tmp/chrome_cdp_bridge"
    headful: bool = True                   # headful 模式（headless 被多数 WAF 检测）

    # Node.js 桥接（备选方案，当 websockets 不可用时使用）
    node_bin: str = "/Users/mac/.workbuddy/binaries/node/versions/22.22.2/bin/node"
    node_ws_path: str = "/Users/mac/.workbuddy/binaries/node/workspace/node_modules/ws"
    python_bin: str = "/Users/mac/.workbuddy/binaries/python/envs/default/bin/python3"

    # WAF 配置
    waf_wait_seconds: int = 15              # WAF JS 挑战等待时间
    waf_min_page_len: int = 100            # WAF 通过的最小页面长度

    # 登录配置
    login_url_path: str = "/login"          # 登录页路径（hash 路由用 /#/login）
    captcha_api_path: str = "sys/getCode"   # 验证码 API 路径
    login_api_path: str = "sys/login"       # 登录 API 路径
    account: str = ""
    password: str = ""

    # 验证码 OCR 配置
    captcha_ocr: bool = True                # 是否启用 ddddocr OCR
    captcha_max_retries: int = 3            # OCR 最大重试次数

    # 表单填充配置
    form_input_selector: str = "input.el-input__inner"  # Vue Element UI 默认
    form_input_fallback: str = "input"      # 回退选择器
    login_button_text: str = "登录"          # 登录按钮文本（包含匹配）

    # 超时
    cdp_timeout: int = 30                   # CDP 单次操作超时（秒）
    login_wait_seconds: int = 15           # 登录后等待响应时间


class ChromeCDPBridge:
    """
    通用 Chrome CDP WAF 绕过桥接器

    架构：
      1. 直接 spawn Chrome（不通过 Playwright/Selenium，避免自动化框架痕迹）
      2. about:blank 启动 → CDP WebSocket 连接 → Network.enable → 再导航
      3. WAF JS 挑战在真实 Chrome 中自动通过
      4. 验证码通过 CDP 捕获 → ddddocr OCR → 自动填表登录（可选）
      5. API 调用通过 Chrome 内部 fetch() 执行（WAF cookie 自动携带）
    """

    def __init__(self, config: BridgeConfig):
        self.config = config
        self.chrome_process = None
        self._node_proc = None
        self.ws = None
        self.msg_id = 0
        self.callbacks: Dict[int, asyncio.Future] = {}
        self.logged_in = False
        self.token = None
        self._lock = asyncio.Lock()

    # ============ Chrome 生命周期管理 ============

    async def start(self):
        """启动 Chrome 并建立 CDP 连接"""
        log.info(f"启动 Chrome CDP 桥接器 (port={self.config.cdp_port})...")

        # 清理旧进程
        try:
            subprocess.run(
                ["pkill", "-f", f"remote-debugging-port={self.config.cdp_port}"],
                capture_output=True, timeout=5,
            )
            await asyncio.sleep(2)
        except Exception:
            pass

        # 启动 Chrome（about:blank，不直接加载目标页面）
        args = [
            self.config.chrome_path,
            f"--remote-debugging-port={self.config.cdp_port}",
            f"--user-data-dir={self.config.chrome_profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--lang=zh-CN",
            "--window-size=1920,1080",
            "--disable-extensions",
            "--disable-popup-blocking",
            "--no-sandbox",
            "about:blank",  # 关键：不直接导航到目标页面
        ]
        self.chrome_process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        await asyncio.sleep(3)

        # 获取 CDP target
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{self.config.cdp_port}/json", timeout=5
            ) as resp:
                targets = json.loads(resp.read())
        except Exception as e:
            raise RuntimeError(f"CDP 连接失败: {e}")

        target = next(
            (t for t in targets if t.get("type") == "page"), targets[0]
        )
        if not target:
            raise RuntimeError("未找到 CDP target")

        ws_url = target["webSocketDebuggerUrl"]

        # 尝试 websockets，回退到 Node.js 桥接
        try:
            import websockets
            self.ws = await websockets.connect(ws_url)
            log.info("websockets CDP 连接成功")

            # 注册消息处理
            async def message_handler():
                async for raw in self.ws:
                    msg = json.loads(raw)
                    if msg.get("id") and msg["id"] in self.callbacks:
                        cb = self.callbacks.pop(msg["id"])
                        if msg.get("error"):
                            if not cb.done():
                                cb.set_exception(
                                    RuntimeError(json.dumps(msg["error"]))
                                )
                        else:
                            if not cb.done():
                                cb.set_result(msg.get("result"))

            asyncio.create_task(message_handler())

        except ImportError:
            log.info("websockets 不可用，使用 Node.js 桥接")
            await self._start_node_bridge(ws_url)

        # 启用 CDP 域（关键：在导航之前启用）
        await self._send("Network.enable")
        await self._send("Page.enable")
        await self._send("Runtime.enable")

        log.info("Chrome CDP 桥接器已就绪")

    async def stop(self):
        """关闭 Chrome 和 CDP 连接"""
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
        if self._node_proc:
            try:
                self._node_proc.terminate()
            except Exception:
                pass
        if self.chrome_process:
            try:
                os.killpg(os.getpgid(self.chrome_process.pid), 9)
            except Exception:
                pass
        log.info("Chrome CDP 桥接器已关闭")

    # ============ CDP 通信 ============

    async def _send(self, method: str, params: dict = None) -> dict:
        """统一的 CDP 发送接口"""
        if self.ws:
            return await self._send_websockets(method, params)
        else:
            return await self._send_node(method, params)

    async def _send_websockets(self, method: str, params: dict = None) -> dict:
        """通过 websockets 发送 CDP 命令"""
        self.msg_id += 1
        msg_id = self.msg_id
        future = asyncio.Future()
        self.callbacks[msg_id] = future

        await self.ws.send(json.dumps({
            "id": msg_id,
            "method": method,
            "params": params or {},
        }))

        try:
            return await asyncio.wait_for(
                future, timeout=self.config.cdp_timeout
            )
        except asyncio.TimeoutError:
            self.callbacks.pop(msg_id, None)
            raise RuntimeError(f"CDP 超时: {method}")

    async def _start_node_bridge(self, ws_url: str):
        """使用 Node.js 子进程作为 WebSocket 桥接"""
        bridge_script = f"""
        const WebSocket = require('{self.config.node_ws_path}');
        const ws = new WebSocket('{ws_url}');
        let msgId = 0;
        const callbacks = {};

        ws.on('open', () => console.log('WS_CONNECTED'));
        ws.on('message', (data) => {{
            const msg = JSON.parse(data.toString());
            if (msg.id && callbacks[msg.id]) {{
                const cb = callbacks[msg.id];
                delete callbacks[msg.id];
                process.stdout.write('RESPONSE:' +
                    JSON.stringify({{id: msg.id, result: msg.result, error: msg.error}}) + '\\n');
            }}
        }});
        ws.on('error', (e) => {{ console.error('WS_ERROR:', e.message); process.exit(1); }});

        process.stdin.setEncoding('utf-8');
        let buffer = '';
        process.stdin.on('data', (chunk) => {{
            buffer += chunk;
            let idx;
            while ((idx = buffer.indexOf('\\n')) >= 0) {{
                const line = buffer.substring(0, idx);
                buffer = buffer.substring(idx + 1);
                try {{
                    const cmd = JSON.parse(line);
                    const id = ++msgId;
                    callbacks[id] = true;
                    ws.send(JSON.stringify({{ id, method: cmd.method, params: cmd.params || {{}} }}));
                }} catch(e) {{}}
            }}
        }});
        """

        bridge_path = "/tmp/chrome_cdp_node_bridge.js"
        with open(bridge_path, "w") as f:
            f.write(bridge_script)

        env = os.environ.copy()
        env["NODE_PATH"] = os.path.dirname(self.config.node_ws_path)

        self._node_proc = subprocess.Popen(
            [self.config.node_bin, bridge_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )

        # 等待连接
        for _ in range(50):
            line = self._node_proc.stdout.readline()
            if line and "WS_CONNECTED" in line:
                break
        else:
            raise RuntimeError("Node bridge 连接超时")

        log.info("Node.js CDP 桥接已连接")

    async def _send_node(self, method: str, params: dict = None) -> dict:
        """通过 Node.js 桥接发送 CDP 命令"""
        import select

        self.msg_id += 1
        msg_id = self.msg_id

        cmd = json.dumps({"method": method, "params": params or {}})
        self._node_proc.stdin.write(cmd + "\n")
        self._node_proc.stdin.flush()

        deadline = time.time() + self.config.cdp_timeout
        while time.time() < deadline:
            ready, _, _ = select.select([self._node_proc.stdout], [], [], 1)
            if ready:
                line = self._node_proc.stdout.readline()
                if line and line.startswith("RESPONSE:"):
                    resp = json.loads(line[len("RESPONSE:"):])
                    if resp.get("error"):
                        raise RuntimeError(json.dumps(resp["error"]))
                    return resp.get("result", {})

        raise RuntimeError(f"CDP 超时 (node): {method}")

    # ============ CDP 高层操作 ============

    async def navigate(self, url: str):
        """导航到指定页面"""
        await self._send("Page.navigate", {"url": url})

    async def evaluate(self, expression: str, await_promise: bool = False) -> Any:
        """在 Chrome 中执行 JS 并返回结果"""
        result = await self._send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": await_promise,
        })
        if result and result.get("exceptionDetails"):
            raise RuntimeError(json.dumps(result["exceptionDetails"]))
        return result.get("result", {}).get("value") if result else None

    async def get_cookies(self) -> list:
        """获取所有 Cookie"""
        result = await self._send("Network.getAllCookies")
        return result.get("cookies", []) if result else []

    async def capture_screenshot(self, path: str):
        """截图保存到文件"""
        result = await self._send("Page.captureScreenshot", {"format": "png"})
        if result and result.get("data"):
            import base64
            with open(path, "wb") as f:
                f.write(base64.b64decode(result["data"]))
            log.info(f"截图已保存: {path}")

    # ============ WAF 绕过 ============

    async def pass_waf(self, target_url: str = None) -> bool:
        """
        通过 WAF 防护

        核心步骤：
        1. 导航到目标 URL（此时 Network.enable 已注册，所有网络事件会被捕获）
        2. 等待 WAF JS 挑战自动执行（真实 Chrome JS 引擎会自动通过）
        3. 检查页面是否正常加载

        Returns:
            bool: WAF 是否通过
        """
        url = target_url or self.config.target_url
        log.info(f"导航到 {url}，等待 WAF ({self.config.waf_wait_seconds}秒)...")

        await self.navigate(url)
        await asyncio.sleep(self.config.waf_wait_seconds)

        # 检查是否通过
        state = await self.evaluate(
            'JSON.stringify({url: location.href, '
            'len: document.body ? document.body.innerHTML.length : 0})'
        )
        state_data = json.loads(state) if isinstance(state, str) else state or {}

        if state_data.get("len", 0) < self.config.waf_min_page_len:
            log.error(f"WAF 未通过 (页面长度={state_data.get('len', 0)})")
            return False

        log.info("✅ WAF 已通过")
        return True

    # ============ 自动登录 ============

    async def login(self, account: str = None, password: str = None) -> dict:
        """
        自动登录流程：验证码获取 → OCR → 填表 → 登录

        适用于 Vue.js + Element UI 系统，可根据需要重写子方法适配其他框架。

        Returns:
            dict: 登录响应
        """
        account = account or self.config.account
        password = password or self.config.password

        async with self._lock:
            if self.logged_in and self.token:
                log.info("已有有效登录态")
                return {"token": self.token}

            log.info(f"开始登录流程 (account={account})...")

            # 1. 确保在登录页
            url = await self.evaluate("location.href")
            if "login" not in (url or ""):
                await self.pass_waf()

            # 2. 获取验证码
            if self.config.captcha_ocr:
                captcha_code = await self._get_and_ocr_captcha()
                if not captcha_code:
                    raise RuntimeError("验证码 OCR 失败")
            else:
                captcha_code = ""

            # 3. 填写表单
            await self._fill_login_form(account, password, captcha_code)
            await asyncio.sleep(1)

            # 4. 点击登录按钮
            await self._click_login_button()

            # 5. 等待登录响应
            log.info(f"等待登录响应 ({self.config.login_wait_seconds}秒)...")
            await asyncio.sleep(self.config.login_wait_seconds)

            # 6. 检查登录结果
            login_state = await self.evaluate(
                'JSON.stringify({url: location.href, '
                'token: localStorage.getItem("token") || "", '
                'cookies: document.cookie.substring(0, 300)})'
            )
            ls = json.loads(login_state) if isinstance(login_state, str) else {}

            login_success = (
                "login" not in ls.get("url", "")
                or ls.get("token")
            )

            if login_success:
                self.logged_in = True
                self.token = ls.get("token") or ""
                log.info("✅ 登录成功")
                return ls
            else:
                log.error("❌ 登录失败")
                return {"error": "login failed", "state": ls}

    async def _get_and_ocr_captcha(self) -> str:
        """获取验证码并 OCR 识别"""
        for attempt in range(1, self.config.captcha_max_retries + 1):
            log.info(f"获取验证码 (第{attempt}次)...")

            # 通过 Chrome 内部 fetch 获取验证码
            if attempt > 1:
                # 重试时刷新验证码
                await asyncio.sleep(1)

            captcha_js = f"""
            (async function() {{
                try {{
                    var resp = await fetch(
                        '{self.config.target_url}/{self.config.api_prefix}/{self.config.captcha_api_path}?t=' + Date.now(),
                        {{ credentials: 'include' }}
                    );
                    var data = await resp.json();
                    return JSON.stringify(data);
                }} catch(e) {{
                    return JSON.stringify({{error: e.message}});
                }}
            }})()
            """
            result = await self.evaluate(captcha_js, await_promise=True)

            try:
                captcha_data = json.loads(result) if isinstance(result, str) else result
            except (json.JSONDecodeError, TypeError):
                captcha_data = {}

            code_img = captcha_data.get("codeImg") or captcha_data.get("img") or ""
            if not code_img:
                log.warning(f"验证码获取失败: {captcha_data}")
                continue

            # OCR
            captcha_code = self._ocr_captcha(code_img)
            if captcha_code and 4 <= len(captcha_code) <= 6:
                log.info(f"OCR 成功: '{captcha_code}'")
                return captcha_code

            log.warning(f"OCR 结果不理想: '{captcha_code}'")

        return ""

    def _ocr_captcha(self, base64_img: str) -> str:
        """使用 ddddocr 识别验证码"""
        import base64
        import tempfile

        try:
            img_data = base64.b64decode(base64_img)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(img_data)
                img_path = f.name

            # 调用 ddddocr
            ocr_script = f"""
import ddddocr
ocr = ddddocr.DdddOcr(show_ad=False)
with open("{img_path}", "rb") as f:
    print(ocr.classification(f.read()))
"""
            result = subprocess.run(
                [self.config.python_bin, "-c", ocr_script],
                capture_output=True,
                text=True,
                timeout=30,
            )
            captcha = result.stdout.strip()
            return captcha

        except Exception as e:
            log.error(f"OCR 异常: {e}")
            return ""
        finally:
            try:
                os.unlink(img_path)
            except Exception:
                pass

    async def _fill_login_form(self, account: str, password: str, captcha: str):
        """填写登录表单（Vue.js Element UI 默认）"""
        js = f"""
        (function() {{
            var selector = '{self.config.form_input_selector}';
            var inputs = document.querySelectorAll(selector);
            if (inputs.length === 0) inputs = document.querySelectorAll('{self.config.form_input_fallback}');

            var setVal = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;

            var visibleInputs = Array.from(inputs).filter(function(i) {{
                return i.type !== 'hidden' && i.offsetParent !== null;
            }});

            var result = {{ visible: visibleInputs.length, filled: [] }};

            // 按占位符/类型/name/id 匹配
            var accountFilled = false, passwordFilled = false, captchaFilled = false;

            for (var i = 0; i < visibleInputs.length; i++) {{
                var input = visibleInputs[i];
                var ph = input.placeholder || '';
                var type = input.type || '';
                var name = input.name || '';
                var id = input.id || '';

                // 账号
                if (!accountFilled && (type !== 'password') &&
                    (ph.indexOf('账号') >= 0 || ph.indexOf('用户名') >= 0 ||
                     name === 'username' || name === 'account' ||
                     id === 'username' || id === 'account')) {{
                    setVal.call(input, '{account}');
                    input.dispatchEvent(new Event('input', {{bubbles: true}}));
                    input.dispatchEvent(new Event('change', {{bubbles: true}}));
                    result.filled.push('account');
                    accountFilled = true;
                }}
                // 密码
                else if (!passwordFilled &&
                    (ph.indexOf('密码') >= 0 || type === 'password' ||
                     name === 'password' || id === 'password')) {{
                    setVal.call(input, '{password}');
                    input.dispatchEvent(new Event('input', {{bubbles: true}}));
                    input.dispatchEvent(new Event('change', {{bubbles: true}}));
                    result.filled.push('password');
                    passwordFilled = true;
                }}
                // 验证码
                else if (!captchaFilled &&
                    (ph.indexOf('验证码') >= 0 || ph.indexOf('code') >= 0 ||
                     name === 'code' || name === 'captcha' ||
                     id === 'code' || id === 'captcha')) {{
                    setVal.call(input, '{captcha}');
                    input.dispatchEvent(new Event('input', {{bubbles: true}}));
                    input.dispatchEvent(new Event('change', {{bubbles: true}}));
                    result.filled.push('captcha');
                    captchaFilled = true;
                }}
            }}

            // 回退：按索引填充（假设顺序: 账号、密码、验证码）
            if (!accountFilled && visibleInputs.length >= 3) {{
                setVal.call(visibleInputs[0], '{account}');
                visibleInputs[0].dispatchEvent(new Event('input', {{bubbles: true}}));
                setVal.call(visibleInputs[1], '{password}');
                visibleInputs[1].dispatchEvent(new Event('input', {{bubbles: true}}));
                setVal.call(visibleInputs[2], '{captcha}');
                visibleInputs[2].dispatchEvent(new Event('input', {{bubbles: true}}));
                result.filled = ['account(fallback)', 'password(fallback)', 'captcha(fallback)'];
            }}

            return JSON.stringify(result);
        }})()
        """
        result = await self.evaluate(js)
        log.info(f"表单填写: {result}")

    async def _click_login_button(self):
        """点击登录按钮"""
        btn_text = self.config.login_button_text
        js = f"""
        (function() {{
            var btns = document.querySelectorAll('button');
            for (var b of btns) {{
                var t = (b.textContent || '').trim();
                if (t.indexOf('{btn_text}') >= 0) {{
                    b.click();
                    return 'clicked: ' + t;
                }}
            }}
            var loginBtn = document.querySelector('.login-btn') ||
                          document.querySelector('[class*="login"]');
            if (loginBtn) {{ loginBtn.click(); return 'clicked class'; }}
            var submitBtn = document.querySelector('button[type="submit"]');
            if (submitBtn) {{ submitBtn.click(); return 'clicked submit'; }}
            return 'no button found';
        }})()
        """
        result = await self.evaluate(js)
        log.info(f"登录按钮: {result}")

    # ============ API 调用 ============

    async def fetch_api(self, path: str, method: str = "GET", body: dict = None) -> Any:
        """
        通过 Chrome 内部 fetch() 调用 API

        WAF cookie + 签名参数自动携带（因为在同一个 Chrome 页面上下文中执行）。

        Args:
            path: API 路径（不含 base URL 和 API prefix，如 "users/list"）
            method: HTTP 方法
            body: POST 请求体（dict，自动 JSON 序列化）

        Returns:
            dict: { status: int, data: Any }
        """
        options = {"method": method}
        if body:
            options["body"] = json.dumps(body)

        target = self.config.target_url
        prefix = self.config.api_prefix

        js = f"""
        (async function() {{
            try {{
                var url = '{target}' + '{prefix}/' + {json.dumps(path)};
                var opts = {json.dumps(options)};
                var fetchOpts = {{
                    method: opts.method,
                    credentials: 'include',
                    headers: {{ 'Content-Type': 'application/json' }},
                }};
                if (opts.body) fetchOpts.body = opts.body;
                var resp = await fetch(url, fetchOpts);
                var text = await resp.text();
                var data;
                try {{ data = JSON.parse(text); }} catch(e) {{ data = text; }}
                return JSON.stringify({{ status: resp.status, data: data }});
            }} catch(e) {{
                return JSON.stringify({{ error: e.message }});
            }}
        }})()
        """
        result = await self.evaluate(js, await_promise=True)

        try:
            return json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            return {"error": "parse failed", "raw": result}

    async def fetch_raw(self, url: str, method: str = "GET", body: dict = None) -> Any:
        """
        通过 Chrome 内部 fetch() 调用任意 URL（不受 api_prefix 约束）

        Args:
            url: 完整 URL
            method: HTTP 方法
            body: POST 请求体

        Returns:
            dict: { status: int, data: Any }
        """
        options = {"method": method}
        if body:
            options["body"] = json.dumps(body)

        js = f"""
        (async function() {{
            try {{
                var url = {json.dumps(url)};
                var opts = {json.dumps(options)};
                var fetchOpts = {{
                    method: opts.method,
                    credentials: 'include',
                    headers: {{ 'Content-Type': 'application/json' }},
                }};
                if (opts.body) fetchOpts.body = opts.body;
                var resp = await fetch(url, fetchOpts);
                var text = await resp.text();
                var data;
                try {{ data = JSON.parse(text); }} catch(e) {{ data = text; }}
                return JSON.stringify({{ status: resp.status, data: data }});
            }} catch(e) {{
                return JSON.stringify({{ error: e.message }});
            }}
        }})()
        """
        result = await self.evaluate(js, await_promise=True)
        try:
            return json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            return {"error": "parse failed", "raw": result}

    # ============ 高级功能 ============

    async def capture_network_requests(
        self, duration_seconds: int = 30, filter_types: list = None
    ) -> list:
        """
        捕获网络请求（通过 CDP Network 域）

        Args:
            duration_seconds: 捕获持续时间
            filter_types: 过滤的请求类型（默认 XHR/Fetch/Document）

        Returns:
            list: 捕获的请求列表
        """
        if filter_types is None:
            filter_types = ["XHR", "Fetch", "Document"]

        requests = []
        responses = {}

        async def on_message(raw):
            msg = json.loads(raw) if isinstance(raw, bytes) else json.loads(raw)

            if msg.get("method") == "Network.requestWillBeSent":
                r = msg["params"]
                if r.get("type") in filter_types:
                    requests.append({
                        "url": r["request"]["url"],
                        "method": r["request"]["method"],
                        "postData": r["request"].get("postData"),
                        "type": r["type"],
                        "requestId": r["requestId"],
                        "timestamp": r.get("timestamp"),
                    })

            if msg.get("method") == "Network.responseReceived":
                r = msg["params"]
                if r.get("type") in ["XHR", "Fetch"]:
                    responses[r["requestId"]] = {
                        "url": r["response"]["url"],
                        "status": r["response"]["status"],
                        "mime": r["response"]["mimeType"],
                    }

        # 注册监听
        if self.ws:
            # websockets 模式
            original_handler = self.ws._message_handler if hasattr(self.ws, '_message_handler') else None

            async def capture_handler():
                async for raw in self.ws:
                    await on_message(raw)
                    msg = json.loads(raw)
                    if msg.get("id") and msg["id"] in self.callbacks:
                        cb = self.callbacks.pop(msg["id"])
                        if msg.get("error"):
                            if not cb.done():
                                cb.set_exception(RuntimeError(json.dumps(msg["error"])))
                        else:
                            if not cb.done():
                                cb.set_result(msg.get("result"))

            asyncio.create_task(capture_handler())

        # 等待捕获
        await asyncio.sleep(duration_seconds)

        # 合并请求和响应
        for req in requests:
            rid = req.get("requestId")
            if rid in responses:
                req["response"] = responses[rid]

        return requests

    async def ensure_connected(self):
        """确保 Chrome 和 CDP 已连接"""
        if not self.chrome_process or self.chrome_process.poll() is not None:
            await self.start()
            await self.pass_waf()
            if self.config.account:
                await self.login()

    async def ensure_connected_and_logged_in(self):
        """确保已连接且已登录"""
        await self.ensure_connected()
        if not self.logged_in:
            await self.login()


# ============ 便捷工厂函数 ============

def create_bridge(
    target_url: str,
    api_prefix: str = "",
    account: str = "",
    password: str = "",
    **kwargs,
) -> ChromeCDPBridge:
    """
    快速创建桥接器

    Args:
        target_url: 目标系统 URL
        api_prefix: API 前缀
        account: 登录账号
        password: 登录密码
        **kwargs: 其他配置参数

    Returns:
        ChromeCDPBridge 实例
    """
    config = BridgeConfig(
        target_url=target_url,
        api_prefix=api_prefix,
        account=account,
        password=password,
        **kwargs,
    )
    return ChromeCDPBridge(config)
