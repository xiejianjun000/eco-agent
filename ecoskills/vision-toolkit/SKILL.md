---
name: vision-toolkit
description: 让纯文本模型具备"眼睛"——分析本地图片：OCR 提取文字 + 尺寸/格式元数据。eco 已实现 vision_analyze_image 工具（macOS 原生 Vision OCR，中文识别准确）。触发词：看图、识别图片、OCR、截图分析、图片问答、案卷扫描、监测截图、地图截图、照片文字。
---

# vision-toolkit（eco 实现版）

eco 通过内置工具 **`vision_analyze_image(path, question?)`** 提供视觉能力：

- **OCR 文字提取**：macOS 原生 Vision framework（中文/英文，准确率高），回退 tesseract。
- **图像元数据**：尺寸（px）、格式、路径。
- **用法**：用户给本地图片路径（监测截图/案卷扫描/地图/文书照片）→ 调 `vision_analyze_image` → 基于返回的 `ocr_text` 回答；`question` 可附加提问意图。
- **权限**：L1 只读自动放行。
- **局限**：只做 OCR + 元数据（纯文本模型不能真正"看懂"图像内容），复杂图像理解需接视觉大模型（豆包/通义 VL）。

## 工作流

1. 拿到图片路径（用户提供 / 产物 / 上传文件）。
2. 调 `vision_analyze_image(path)` 拿 OCR 文本 + 尺寸。
3. 基于 OCR 文本回答用户问题（数据核对、案卷信息提取、截图内容转述）。
4. OCR 为空时如实说"未识别到文字"，不编造内容。
