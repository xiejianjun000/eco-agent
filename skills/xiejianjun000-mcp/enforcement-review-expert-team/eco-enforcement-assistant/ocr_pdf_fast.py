#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高效PDF OCR提取脚本 - 使用PyMuPDF + 并发处理
"""
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

pdf_path = sys.argv[1]
output_path = sys.argv[2]

print(f"正在OCR提取PDF: {pdf_path}")
print(f"Tesseract版本: {pytesseract.get_tesseract_version()}")

# 打开PDF
pdf_document = fitz.open(pdf_path)
total_pages = len(pdf_document)
print(f"总页数: {total_pages}")

def process_page(page_num):
    """处理单页OCR"""
    try:
        page = pdf_document[page_num]
        # 渲染为图像 (200 DPI - 平衡质量和速度)
        mat = fitz.Matrix(2.0, 2.0)  # 2x缩放 ≈ 200 DPI
        pix = page.get_pixmap(matrix=mat)
        
        # 转换为PIL Image
        img_data = pix.tobytes("ppm")
        pil_image = Image.open(io.BytesIO(img_data))
        
        # OCR识别
        text = pytesseract.image_to_string(pil_image, lang='chi_sim+eng')
        
        if text.strip():
            return page_num, f"=== 第 {page_num+1} 页 ===\n{text}"
        else:
            return page_num, None
    except Exception as e:
        print(f"  第 {page_num+1} 页处理错误: {e}")
        return page_num, None

import io

# 并发处理
print(f"\n开始并发OCR处理（使用多线程）...")
start_time = time.time()
full_text = []

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {executor.submit(process_page, i): i for i in range(total_pages)}
    
    for future in as_completed(futures):
        page_num, result = future.result()
        if result:
            full_text.append(result)
            print(f"  第 {page_num+1}/{total_pages} 页完成")
        
        # 进度显示
        completed = len(full_text)
        if completed % 10 == 0:
            elapsed = time.time() - start_time
            print(f"  进度: {completed}/{total_pages} 页, 用时: {elapsed:.1f}秒")

# 按页码排序
full_text.sort(key=lambda x: x[0])
full_content = "\n\n".join([text for _, text in full_text])

# 保存结果
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(full_content)

elapsed = time.time() - start_time
print(f"\nOCR提取完成!")
print(f"  识别页数: {len(full_text)}/{total_pages}")
print(f"  总字符数: {len(full_content)}")
print(f"  用时: {elapsed:.1f}秒")
print(f"  输出文件: {output_path}")

pdf_document.close()
