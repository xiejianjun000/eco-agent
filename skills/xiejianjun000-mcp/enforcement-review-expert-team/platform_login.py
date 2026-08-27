"""Complete platform login + data extraction using Playwright"""
import asyncio
import base64
import os
import subprocess
import json
import ddddocr
from playwright.async_api import async_playwright

PLATFORM_URL = "http://114.251.10.199:8080/zfpt_zf/redirect.jsp"
USERNAME = os.environ.get("ECOAEGIS_ATMOSPHERE_USER", "430000")  # 湖南省行政区划代码（平台账号）
PASSWORD = os.environ.get("ECO_PASS") or subprocess.check_output(
    ["security", "find-generic-password", "-a", "ecoaegis", "-s", "atmosphere-pass", "-w"],
    text=True
).strip()
WORK_DIR = r"C:\Users\Administrator\WorkBuddy\执法督察评查专家团"

ocr = ddddocr.DdddOcr()

async def extract_captcha(page):
    """Extract captcha image from page as bytes"""
    captcha_bytes = await page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        for (const img of imgs) {
            if (img.src && img.src.includes('code')) {
                const canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                canvas.getContext('2d').drawImage(img, 0, 0);
                const dataUrl = canvas.toDataURL('image/png');
                return dataUrl.split(',')[1];
            }
        }
        return null;
    }""")
    if captcha_bytes:
        return base64.b64decode(captcha_bytes)
    return None

async def login(page):
    """Attempt login with captcha OCR"""
    await page.goto(PLATFORM_URL, wait_until='networkidle')
    await page.wait_for_timeout(2000)
    
    # Fill credentials
    await page.fill('input[placeholder*="登录账户"], [aria-label*="登录账户"]', USERNAME)
    await page.fill('input[placeholder*="密码"], [aria-label*="密码"]', PASSWORD)
    
    for attempt in range(8):
        print(f"\n=== Login attempt {attempt + 1} ===")
        
        # Extract captcha
        img_data = await extract_captcha(page)
        if not img_data:
            print("ERROR: Cannot find captcha image")
            return False
        
        # OCR
        captcha_text = ocr.classification(img_data)
        print(f"OCR result: '{captcha_text}'")
        
        if not captcha_text or len(captcha_text) < 3:
            print("OCR result too short, refreshing captcha...")
            await page.evaluate("""() => {
                const imgs = document.querySelectorAll('img');
                for (const img of imgs) {
                    if (img.src && img.src.includes('code')) { img.click(); break; }
                }
            }""")
            await page.wait_for_timeout(1000)
            continue
        
        # Fill captcha and submit
        captcha_input = page.locator('input[placeholder*="验证码"], [aria-label*="验证码"]')
        await captcha_input.click()
        await captcha_input.fill('')
        await captcha_input.fill(captcha_text)
        
        # Click login button
        await page.click('button')
        await page.wait_for_timeout(3000)
        
        # Check result
        current_url = page.url
        print(f"Current URL: {current_url}")
        
        # Check for error message
        error = await page.evaluate("""() => {
            const paragraphs = document.querySelectorAll('p');
            for (const p of paragraphs) {
                if (p.textContent.includes('不正确') || p.textContent.includes('错误')) {
                    return p.textContent;
                }
            }
            return null;
        }""")
        
        if error:
            print(f"Login error: {error}")
            if '验证码' in error:
                print("Wrong captcha, retrying...")
                await page.evaluate("""() => {
                    const imgs = document.querySelectorAll('img');
                    for (const img of imgs) {
                        if (img.src && img.src.includes('code')) { img.click(); break; }
                    }
                }""")
                await page.wait_for_timeout(1000)
                continue
            elif '帐号' in error or '密码' in error:
                print("WRONG CREDENTIALS - cannot proceed")
                return False
        else:
            # No error - check if we're on a different page
            if 'redirect.jsp' not in current_url or 'main' in current_url:
                print("LOGIN SUCCESSFUL!")
                return True
            else:
                print("Still on login page, checking for success...")
                heading = await page.evaluate("""() => {
                    const h1 = document.querySelector('h1');
                    return h1 ? h1.textContent : null;
                }""")
                if heading and '登录' not in heading:
                    print(f"Page heading changed to: {heading}")
                    print("LOGIN APPEARS SUCCESSFUL!")
                    return True
    
    return False

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            success = await login(page)
            if success:
                print("\n=== LOGIN SUCCESSFUL ===")
                # Take screenshot for confirmation
                await page.screenshot(path=os.path.join(WORK_DIR, 'login_success.png'))
                print("Browser will stay open for manual inspection.")
                await asyncio.sleep(300)  # Keep open for 5 minutes
            else:
                print("\n=== LOGIN FAILED ===")
                await page.screenshot(path=os.path.join(WORK_DIR, 'login_failed.png'))
        finally:
            await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
