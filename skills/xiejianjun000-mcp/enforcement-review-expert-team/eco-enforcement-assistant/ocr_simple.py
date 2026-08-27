#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版PDF OCR - 逐页处理，增量保存
"""
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import sys
import io
import time

pdf_path = sys.argv[1]
output_path = sys.argv[2]

print(f"正在OCR提取PDF: {pdf_path}")
print(f"Tesseract版本: {pytesseract.get_tesseract_version()}")

# 打开PDF
pdf_document = fitz.open(pdf_path)
total_pages = len(pdf_document)
print(f"总页数: {total_pages}\n")

# 增量写入
with open(output_path, 'w', encoding='utf-8') as outf:
    for page_num in range(total_pages):
        print(f"处理第 {page_num+1}/{total_pages} 页...")
        
        try:
            page = pdf_document[page_num]
            
            # 渲染为图像 (150 DPI - 降低分辨率提高速度)
            mat = fitz.Matrix(1.5, 1.5)  # 1.5x缩放
            pix = page.get_pixmap(matrix=mat)
            
            # 转换为PIL Image
            img_data = pix.tobytes("ppm")
            pil_image = Image.open(io.BytesIO(img_data))
            
            # OCR识别 - 仅使用英文（如果中文识别太慢）
            # 先尝试中文，如果太慢再用英文
            try:
                text = pytesseract.image_to_string(pil_image, lang='chi_sim+eng')
            except:
                # 如果中文包不存在，仅用英文
                text = pytesseract.image_to_string(pil_image, lang='eng')
            
            if text.strip():
                page_text = f"=== 第 {page_num+1} 页 ===\n{text}\n\n"
                outf.write(page_text)
                outf.flush()  # 立即写入磁盘
                print(f"  ✓ 识别到 {len(text)} 字符")
            else:
                print(f"  ✗ 未识别到文字")
            
            # 每10页显示一次进度
            if (page_num + 1) % 10 == 0:
                elapsed = time.time() - start_time
                print(f"  进度: {page_num+1}/{total_pages} 页完成, 用时: {elapsed:.1f}秒\n")
        
        except Exception as e:
            print(f"  ✗ 错误: {e}\n")
            continue

print(f"\nOCR提取完成!")
print(f"输出文件: {output_path}")

pdf_document.close()
