#!/usr/bin/env python3
"""
湖南生态环境智慧执法办案系统 - 登录脚本
处理算术验证码 + AES加密登录

输出: /tmp/zfyth_cookies.pkl (pickled session cookies)
"""
import base64
import requests
import re
import pickle
import sys
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from collections import Counter

try:
    import ddddocr
except ImportError:
    print("请安装 ddddocr: pip3 install ddddocr")
    sys.exit(1)

BASE_URL = "http://113.246.57.20:8507/zfyth"
USERNAME = "lsjgly"
PASSWORD = "Hnzfyth@2022"
AES_KEY = "boandaxxjsgfyxgs"

def aes_ecb_encrypt(text, key_str):
    key = key_str.encode('utf-8')
    cipher = AES.new(key, AES.MODE_ECB)
    return base64.b64encode(cipher.encrypt(pad(text.encode('utf-8'), 16))).decode()

def solve_math_captcha(text):
    """Parse OCR'd math expression and compute answer"""
    text = text.strip().replace(' ', '')
    text = text.replace('×', '*').replace('x', '*').replace('X', '*')
    text = text.replace('−', '-').replace('—', '-').replace('＋', '+')
    match = re.match(r'^(\d+)\s*([+\-*])\s*(\d+)$', text)
    if match:
        a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
        if op == '+': return str(a + b)
        if op == '-': return str(a - b)
        if op == '*': return str(a * b)
    digits = re.findall(r'(\d+)', text)
    if len(digits) >= 2:
        return str(int(digits[0]) + int(digits[1]))
    return None

def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})

    username_b64 = base64.b64encode(USERNAME.encode()).decode()
    password_b64 = base64.b64encode(PASSWORD.encode()).decode()
    encrypted_pwd = aes_ecb_encrypt(password_b64, AES_KEY)
    ocr = ddddocr.DdddOcr(show_ad=False)

    for attempt in range(30):
        r = session.get(f"{BASE_URL}/code")

        # OCR multiple times, take most common result
        results = []
        for _ in range(3):
            results.append(ocr.classification(r.content))
        most_common = Counter(results).most_common(1)[0][0]

        captcha_answer = solve_math_captcha(most_common)
        if not captcha_answer:
            captcha_answer = solve_math_captcha(results[0])
        if not captcha_answer:
            continue

        login_data = {
            "XTZH": username_b64,
            "YHMM": encrypted_pwd,
            "smsCode": "",
            "validateCode": captcha_answer
        }
        r = session.post(f"{BASE_URL}/login", json=login_data)
        resp = r.json()
        msg = resp.get('msg', '')

        if '成功' in msg or resp.get('code') == 200 or resp.get('success'):
            print(f"✅ 登录成功 (尝试{attempt+1}次, 验证码: {most_common} = {captcha_answer})")

            with open('/tmp/zfyth_cookies.pkl', 'wb') as f:
                pickle.dump(dict(session.cookies), f)
            print("Session 已保存到 /tmp/zfyth_cookies.pkl")
            print(f"JSESSIONID: {session.cookies.get('JSESSIONID')}")
            return session

        if attempt % 5 == 0:
            print(f"⏳ 尝试 {attempt+1}: OCR='{most_common}', 答案={captcha_answer}, 结果={msg[:50]}")

    print("❌ 所有登录尝试失败")
    return None

if __name__ == '__main__':
    main()
