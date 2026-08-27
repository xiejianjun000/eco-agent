"""Simple OCR from captcha_b64.txt"""
import base64
import os
import ddddocr
import sys

base_dir = os.path.dirname(os.path.abspath(__file__))
b64_path = os.path.join(base_dir, 'captcha_b64.txt')

if not os.path.exists(b64_path):
    print('ERROR: captcha_b64.txt not found')
    sys.exit(1)

with open(b64_path, 'r') as f:
    b64_data = f.read().strip()

# Remove data URL prefix if present  
if 'base64,' in b64_data:
    b64_data = b64_data.split('base64,')[1]

try:
    img_data = base64.b64decode(b64_data)
except Exception as e:
    print(f'ERROR: base64 decode failed: {e}')
    sys.exit(1)

ocr = ddddocr.DdddOcr()
result = ocr.classification(img_data)
print(result)
