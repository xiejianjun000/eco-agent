"""生成专家团10张占位头像 (512x512 PNG)"""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))

# 团队头像配置
members = [
    # (filename, emoji, name_zh, color_hex)
    ("team.png",        "⚖️", "专家团",   "#2C3E50"),
    ("enforcement-review-lead.png", "⚖️", "法眼通", "#1A5276"),
    ("case-reviewer.png",           "📋", "卷查清", "#534AB7"),
    ("field-enforcer.png",          "🏭", "执法准", "#3B6D11"),
    ("inspection-advisor.png",      "🎯", "督察精", "#534AB7"),
    ("legal-compliance.png",        "📜", "法条通", "#993C1D"),
    ("doc-generator.png",           "📝", "文书成", "#378ADD"),
    ("data-analyst.png",            "📊", "数据芯", "#0F6E56"),
    ("kb-manager.png",              "📚", "知识库", "#854F0B"),
    ("platform-patrol.png",         "🔍", "巡检员", "#E24B4A"),
]

SIZE = 512

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def darken_color(rgb, factor=0.65):
    return tuple(int(c * factor) for c in rgb)

def lighten_color(rgb, factor=0.15):
    return tuple(min(255, int(c + (255 - c) * factor)) for c in rgb)

for filename, emoji, name, color in members:
    base_rgb = hex_to_rgb(color)
    dark_rgb = darken_color(base_rgb)
    
    # 创建圆形头像的渐变背景
    img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    
    # 外层圆 - 暗色边缘
    outer = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(outer)
    odraw.ellipse([4, 4, SIZE-4, SIZE-4], fill=dark_rgb)
    
    # 内层圆 - 主色
    inner = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    idraw = ImageDraw.Draw(inner)
    padding = 12
    idraw.ellipse([padding, padding, SIZE-padding, SIZE-padding], fill=base_rgb)
    
    # 高光渐变效果 - 顶部亮色弧
    highlight = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(highlight)
    light_rgb = lighten_color(base_rgb, 0.3)
    hdraw.ellipse([padding, padding, SIZE-padding, SIZE//2 + 40], fill=(*light_rgb, 80))
    
    # 合成图层
    img = Image.alpha_composite(img, outer)
    img = Image.alpha_composite(img, inner)
    img = Image.alpha_composite(img, highlight)
    
    draw = ImageDraw.Draw(img)
    
    # 绘制 emoji - 大号
    try:
        font_emoji = ImageFont.truetype("/System/Library/Fonts/Apple Color Emoji.ttc", 140)
    except:
        try:
            font_emoji = ImageFont.truetype("seguiemj.ttf", 140)
        except:
            try:
                font_emoji = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", 140)
            except:
                font_emoji = ImageFont.load_default()

    # 绘制文字 - 中号
    try:
        font_name = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 56)
    except:
        try:
            font_name = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 56)
        except:
            try:
                font_name = ImageFont.truetype("C:/Windows/Fonts/simhei.ttf", 56)
            except:
                font_name = ImageFont.load_default()
    
    # 计算 emoji 位置（居中偏上）
    bbox_e = draw.textbbox((0, 0), emoji, font=font_emoji)
    ew = bbox_e[2] - bbox_e[0]
    eh = bbox_e[3] - bbox_e[1]
    ex = (SIZE - ew) // 2
    ey = SIZE // 2 - eh // 2 - 30
    
    # 绘制 emoji 阴影
    draw.text((ex+3, ey+3), emoji, font=font_emoji, fill=(0, 0, 0, 60))
    # 绘制 emoji
    draw.text((ex, ey), emoji, font=font_emoji, fill=(255, 255, 255, 255))
    
    # 计算名字位置（底部）
    bbox_n = draw.textbbox((0, 0), name, font=font_name)
    nw = bbox_n[2] - bbox_n[0]
    nx = (SIZE - nw) // 2
    ny = SIZE // 2 + 70
    
    # 绘制名字阴影
    draw.text((nx+2, ny+2), name, font=font_name, fill=(0, 0, 0, 80))
    # 绘制名字
    draw.text((nx, ny), name, font=font_name, fill=(255, 255, 255, 240))
    
    # 保存
    outpath = os.path.join(OUT, filename)
    img.save(outpath, 'PNG', optimize=True)
    print(f"✅ {filename} ({os.path.getsize(outpath)//1024}KB)")

print("\n全部头像生成完毕！")
