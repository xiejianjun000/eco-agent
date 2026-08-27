#!/usr/bin/env python3
"""
browser_skill.py — 浏览器自动化技能（基于 Playwright）

补齐政务场景中 Web 系统操作能力：
- 全国排污许可证管理信息平台
- 建设项目环评审批系统
- 全国辐射安全申报系统
- 等政务 Web 系统的自动化操作

用法：
    async with BrowserSkill() as browser:
        await browser.navigate("https://permit.mee.gov.cn")
        await browser.type("#username", "eco_agent")
        await browser.click("#login")
        data = await browser.get_table(".data-table")
"""

import logging
from typing import Any

logger = logging.getLogger("eco.browser")

try:
    from playwright.async_api import async_playwright
    BROWSER_AVAILABLE = True
except Exception:  # pragma: no cover
    BROWSER_AVAILABLE = False
    logger.warning(
        "[Browser] Playwright 未安装，浏览器自动化不可用。"
        "安装: pip install playwright && playwright install chromium"
    )


class BrowserSkill:
    """浏览器自动化——导航、点击、输入、提取、截图、表格"""

    def __init__(self, headless: bool = True, timeout_ms: int = 30000):
        self._playwright = None
        self._browser = None
        self._page = None
        self._headless = headless
        self._timeout = timeout_ms

    async def __aenter__(self):
        if not BROWSER_AVAILABLE:
            raise RuntimeError(
                "Playwright 未安装。运行: pip install playwright && playwright install chromium"
            )
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._page = await self._browser.new_page()
        self._page.set_default_timeout(self._timeout)
        logger.info("[Browser] 浏览器启动完成")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("[Browser] 浏览器已关闭")

    # ── 核心操作 ──

    async def navigate(self, url: str, wait_until: str = "networkidle") -> dict:
        """导航到指定 URL，返回 {url, status, title}"""
        response = await self._page.goto(url, wait_until=wait_until, timeout=self._timeout)
        title = await self._page.title()
        status = response.status if response else 0
        logger.info(f"[Browser] 导航 {url} -> 状态{status} 标题'{title[:40]}...'")
        return {"url": url, "status": status, "title": title}

    async def click(self, selector: str) -> dict:
        """点击元素"""
        await self._page.click(selector, timeout=self._timeout)
        logger.debug(f"[Browser] 点击 {selector}")
        return {"selector": selector, "clicked": True}

    async def type(self, selector: str, text: str) -> dict:
        """输入文本（先清空再输入）"""
        await self._page.fill(selector, text, timeout=self._timeout)
        logger.debug(f"[Browser] 输入 {selector} ({len(text)} 字符)")
        return {"selector": selector, "typed": len(text)}

    async def select(self, selector: str, value: str) -> dict:
        """下拉框选择"""
        await self._page.select_option(selector, value, timeout=self._timeout)
        return {"selector": selector, "selected": value}

    async def extract(self, selector: str, attr: str | None = None) -> str:
        """提取元素文本或属性"""
        element = await self._page.query_selector(selector)
        if not element:
            logger.warning(f"[Browser] 未找到元素: {selector}")
            return ""
        if attr:
            return await element.get_attribute(attr) or ""
        return await element.inner_text()

    async def screenshot(self, path: str | None = None, full_page: bool = True) -> bytes:
        """截图，返回 bytes 或保存到 path"""
        return await self._page.screenshot(path=path, full_page=full_page)

    async def get_table(self, selector: str) -> list[list[str]]:
        """提取表格数据为二维数组"""
        table = await self._page.query_selector(selector)
        if not table:
            logger.warning(f"[Browser] 未找到表格: {selector}")
            return []
        rows = await table.query_selector_all("tr")
        result: list[list[str]] = []
        for row in rows:
            cells = await row.query_selector_all("td, th")
            result.append([await cell.inner_text() for cell in cells])
        logger.info(f"[Browser] 提取表格 {selector}: {len(result)} 行")
        return result

    async def wait_for(self, selector: str, state: str = "visible") -> dict:
        """等待元素出现/隐藏/启用/禁用"""
        await self._page.wait_for_selector(selector, state=state, timeout=self._timeout)
        return {"selector": selector, "state": state}

    async def scroll_to(self, selector: str) -> dict:
        """滚动到元素"""
        await self._page.evaluate(f"document.querySelector('{selector}').scrollIntoView()")
        return {"selector": selector, "scrolled": True}

    async def pdf(self, path: str) -> dict:
        """生成 PDF"""
        await self._page.pdf(path=path)
        return {"path": path, "format": "A4"}

    # ── 政务场景快捷方法 ──

    async def gov_login(self, url: str, username: str, password: str,
                        user_sel: str = "#username", pass_sel: str = "#password",
                        btn_sel: str = "#loginBtn") -> dict:
        """政务系统通用登录"""
        await self.navigate(url)
        await self.type(user_sel, username)
        await self.type(pass_sel, password)
        await self.click(btn_sel)
        await self.wait_for(".main-content, .dashboard, .welcome", state="visible")
        title = await self._page.title()
        return {"logged_in": "登录" not in title, "title": title}

    async def gov_search(self, keyword: str, input_sel: str = "#searchInput",
                         btn_sel: str = "#searchBtn", result_sel: str = ".result-list") -> list[dict]:
        """政务系统通用搜索"""
        await self.type(input_sel, keyword)
        await self.click(btn_sel)
        await self.wait_for(result_sel, state="visible")
        items = await self._page.query_selector_all(f"{result_sel} li, {result_sel} tr")
        results = []
        for item in items:
            text = await item.inner_text()
            link = await item.query_selector("a")
            href = await link.get_attribute("href") if link else ""
            results.append({"text": text.strip()[:200], "href": href})
        return results


# ===== 测试 =====

async def test():
    if not BROWSER_AVAILABLE:
        print("[SKIP] Playwright 未安装，跳过浏览器测试")
        return
    async with BrowserSkill(headless=True) as browser:
        r = await browser.navigate("https://www.mee.gov.cn")
        print(f"[Browser] 标题: {r['title']}, 状态: {r['status']}")
        text = await browser.extract("title")
        print(f"[Browser] 提取: {text[:50]}...")
    print("[OK] BrowserSkill 测试通过")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test())
