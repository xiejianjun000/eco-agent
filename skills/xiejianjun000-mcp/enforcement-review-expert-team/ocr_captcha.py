"""OCR captcha image using ddddocr"""
import ddddocr
import sys
import os

ocr = ddddocr.DdddOcr()

# Try multiple captcha images
for img_path in ['captcha_fresh.png', 'captcha_img.png']:
    full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), img_path)
    if os.path.exists(full_path):
        with open(full_path, 'rb') as f:
            img_bytes = f.read()
        result = ocr.classification(img_bytes)
        print(f"CAPTCHA_TEXT: {result}")
        break
else:
    print("ERROR: No captcha image found")
