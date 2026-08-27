#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF OCR提取脚本 - 对扫描版PDF进行OCR文字识别
"""
import pdfplumber
from PIL import Image
import pytesseract
import sys
import os

pdf_path = sys.argv[1]
output_path = sys.argv[2]

print(f"正在OCR提取PDF: {pdf_path}")
print(f"Tesseract版本: {pytesseract.get_tesseract_version()}")

# 创建临时目录存储图像
temp_dir = "pdf_images_temp"
os.makedirs(temp_dir, exist_ok=True)

with pdfplumber.open(pdf_path) as pdf:
    total_pages = len(pdf.pages)
    print(f"总页数: {total_pages}")
    
    full_text = []
    
    for i, page in enumerate(pdf.pages):
        print(f"处理第 {i+1}/{total_pages} 页...")
        
        # 获取页面图像
        pil_image = page.to_image(resolution=300).original
        
        # OCR识别 - 使用中文简体
        try:
            text = pytesseract.image_to_string(pil_image, lang='chi_sim+eng')
            if text.strip():
                full_text.append(f"=== 第 {i+1} 页 ===\n{text}")
                print(f"  识别到 {len(text)} 字符")
            else:
                print(f"  未识别到文字")
        except Exception as e:
            print(f"  OCR错误: {e}")
            # 尝试仅用英文
            try:
                text = pytesseract.image_to_string(pil_image, lang='eng')
                if text.strip():
                    full_text.append(f"=== 第 {i+1} 页 ===\n{text}")
            except:
                pass
    
    # 保存结果
    full_content = "\n\n".join(full_text)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    print(f"\nOCR提取完成，共识别 {len(full_text)} 页")
    print(f"输出文件: {output_path}")
    print(f"总字符数: {len(full_content)}")
