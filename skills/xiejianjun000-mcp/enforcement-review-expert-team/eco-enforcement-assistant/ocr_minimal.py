#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
极简PDF OCR - 使用fitz和tesseract，增量保存
用法: python3 ocr_minimal.py <input.pdf> <output.txt>
"""
import fitz
import pytesseract
from PIL import Image
import sys
import io
import time

if len(sys.argv) != 3:
    print("用法: python3 ocr_minimal.py <input.pdf> <output.txt>")
    sys.exit(1)

pdf_path = sys.argv[1]
output_path = sys.argv[2]

print(f"PDF: {pdf_path}")
print(f"输出: {output_path}\n")

doc = fitz.open(pdf_path)
total = len(doc)
print(f"总页数: {total}\n")

start = time.time()
count = 0

with open(output_path, 'w', encoding='utf-8') as f:
    for i in range(total):
        try:
            page = doc[i]
            zoom = 1.5  # 150 DPI
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            img = Image.open(io.BytesIO(pix.tobytes("ppm")))
            text = pytesseract.image_to_string(img, lang='chi_sim+eng')
            
            if text.strip():
                f.write(f"=== 第 {i+1} 页 ===\n{text}\n\n")
                f.flush()
                count += 1
                print(f"[{i+1}/{total}] ✓ ({len(text)}字符)")
            else:
                print(f"[{i+1}/{total}] ✗ (无文字)")
                
        except Exception as e:
            print(f"[{i+1}/{total}] ✗ 错误: {e}")

elapsed = time.time() - start
print(f"\n完成! 识别 {count}/{total} 页, 用时 {elapsed:.1f}秒")
doc.close()
