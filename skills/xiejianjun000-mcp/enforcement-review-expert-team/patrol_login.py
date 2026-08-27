"""Water platform login via Playwright + ddddocr"""
import asyncio
import os
import subprocess
import sys
import json
import requests
import warnings
warnings.filterwarnings('ignore')
from playwright.async_api import async_playwright

CAS_URL = "https://sthjzf.lem.org.cn:8090/cas/login"
USERNAME = os.environ.get("ECOAEGIS_ATMOSPHERE_USER", "430000")  # 湖南省行政区划代码（平台账号）
PASSWORD = os.environ.get("ECO_PASS") or subprocess.check_output(
    ["security", "find-generic-password", "-a", "ecoaegis", "-s", "atmosphere-pass", "-w"],
    text=True
).strip()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Navigate to CAS
        await page.goto(CAS_URL, timeout=30000)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)
        
        # Fill username/password
        await page.fill("#useraccount", USERNAME)
        await page.fill("#password", PASSWORD)
        
        # Get captcha image (id=yzm, src=kaptcha.jpg)
        captcha_img = await page.query_selector("#yzm, img[alt='captcha'], img.yzmcrm")
        if not captcha_img:
            print("ERROR: Cannot find captcha image")
            await browser.close()
            sys.exit(1)
        
        captcha_bytes = await captcha_img.screenshot()
        
        import ddddocr
        ocr = ddddocr.DdddOcr()
        captcha_text = ocr.classification(captcha_bytes)
        print(f"Captcha: {captcha_text}")
        
        await page.fill("#captcha", captcha_text)
        
        # Click submit using the submit button
        await page.click("#submit")
        
        # Wait for navigation
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except:
            pass
        await asyncio.sleep(3)
        
        url = page.url
        print(f"After CAS: {url}")
        
        # Check for errors
        body = await page.inner_text("body")
        if "用户帐号或者密码错误" in body:
            print("ERROR: Wrong credentials")
            await browser.close()
            sys.exit(1)
        if "验证码" in body and ("错误" in body or "有误" in body or "必须" in body):
            print("ERROR: Wrong captcha, retrying...")
            # Could add retry logic here
        
        # Navigate to water platform
        await page.goto("https://jkzx.envsc.cn/gf-law/", timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=15000)
        await asyncio.sleep(2)
        
        water_url = page.url
        print(f"Water platform: {water_url}")
        
        # Extract JWT from cookies
        cookies = await context.cookies()
        jwt_token = None
        for c in cookies:
            print(f"Cookie: {c['name']} = {c['value'][:60]}")
            if "law-authorized-token" in c.get("name", ""):
                jwt_token = c["value"]
        
        if jwt_token:
            print(f"\nJWT found! Length: {len(jwt_token)}")
            
            # Call API
            headers = {"Authorization": f"Bearer {jwt_token}"}
            payload = {"pageNo": 1, "pageSize": 20, "regionCode": "431381"}
            r = requests.post(
                "https://jkzx.envsc.cn/water-law-platform/statistics/pageOrder",
                json=payload, headers=headers, verify=True, timeout=15
            )
            print(f"API status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                records = data.get("data", {}).get("records", [])
                print(f"Records: {len(records)}")
                # Save to file
                with open("api_response.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print("Saved to api_response.json")
            else:
                print(f"API error: {r.text[:200]}")
        else:
            print("No JWT found in cookies, trying page text...")
            page_text = await page.inner_text("body")
            if "login" in water_url.lower():
                print("Still on login page - SSO may have failed")
            else:
                print("Page content:", page_text[:300])
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
