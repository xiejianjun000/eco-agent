#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF提取脚本 - 提取案卷PDF文本内容
"""
import pdfplumber
import sys

pdf_path = sys.argv[1]
output_path = sys.argv[2]

print(f"正在提取PDF: {pdf_path}")

with pdfplumber.open(pdf_path) as pdf:
    print(f"总页数: {len(pdf.pages)}")
    
    full_text = []
    for i, page in enumerate(pdf.pages):
        text = page.extract_text()
        if text:
            full_text.append(f"=== 第 {i+1} 页 ===\n{text}")
    
    full_content = "\n\n".join(full_text)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    print(f"提取完成，共 {len(full_text)} 页有文字")
    print(f"输出文件: {output_path}")

#  also extract tables
print("\n提取表格数据...")
tables_output = output_path.replace('.txt', '_tables.txt')
with pdfplumber.open(pdf_path) as pdf:
    all_tables = []
    for i, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        if tables:
            for j, table in enumerate(tables):
                all_tables.append(f"=== 第 {i+1} 页 表格{j+1} ===\n{table}")
    
    if all_tables:
        with open(tables_output, 'w', encoding='utf-8') as f:
            f.write("\n\n".join(all_tables))
        print(f"表格已保存到: {tables_output}")
