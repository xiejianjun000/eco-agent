#!/usr/bin/env python3
"""
vision_tool.py — eco 视觉工具（macOS 原生 Vision OCR + 图像元数据）

让纯文本模型"看"本地图片：OCR 提取文字 + 尺寸/格式元数据。
实现：macOS Vision framework（swift 脚本，中文识别准确）+ 回退 tesseract。
零新依赖（swift/tesseract 系统自带）。"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("vision_tool")

_OCR_SWIFT = Path(__file__).resolve().parent / "scripts" / "vision_ocr.swift"


def _img_meta(path: Path) -> dict:
    """图像尺寸/格式（sips 读取，macOS 自带）。"""
    try:
        r = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", "-g", "format", "-g", "hasAlpha", str(path)],
            capture_output=True, text=True, timeout=15)
        meta: dict = {}
        for line in r.stdout.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        return meta
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:80]}


def ocr_text(path: Path, timeout: int = 60) -> str:
    """OCR 提取文字：优先 macOS Vision（swift），回退 tesseract。"""
    # 1. macOS Vision
    if _OCR_SWIFT.is_file():
        try:
            r = subprocess.run(["swift", str(_OCR_SWIFT), str(path)],
                               capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
            logger.debug("vision ocr empty: %s", r.stderr[:120])
        except Exception as e:  # noqa: BLE001
            logger.debug("swift vision failed: %s", str(e)[:80])
    # 2. tesseract（中文）
    if shutil.which("tesseract"):
        try:
            r = subprocess.run(
                ["tesseract", str(path), "stdout", "-l", "chi_sim+eng", "--psm", "6"],
                capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:  # noqa: BLE001
            pass
    return ""


_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
         ".webp": "image/webp", ".bmp": "image/bmp", ".tiff": "image/tiff", ".heic": "image/heic"}


def _load_env_key(name: str) -> str:
    """读环境变量，回退 .env 文件（服务器 envboot 已注入 os.environ，此兜底供独立进程用）。"""
    import os as _os
    v = _os.environ.get(name, "")
    if v:
        return v
    try:
        envf = Path(__file__).resolve().parent.parent / ".env"
        for line in envf.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except Exception:  # noqa: BLE001
        pass
    return ""


def vision_model_answer(image_path: Path, question: str, timeout: int = 60) -> dict:
    """火山方舟视觉大模型图像理解（需有效 ARK_API_KEY + ARK_VISION_MODEL）。

    返回 {"ok": true, "answer": ...} 或 {"ok": false, "error": ...}；key 无效/模型不可用即降级 OCR。"""
    import base64
    import json as _json
    import urllib.error
    import urllib.request

    key = _load_env_key("ARK_API_KEY")
    model = _load_env_key("ARK_VISION_MODEL") or "doubao-seed-2.0-code"
    base = _load_env_key("ARK_VISION_BASE_URL") or "https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions"
    if not key:
        return {"ok": False, "error": "未配置 ARK_API_KEY"}
    mime = _MIME.get(image_path.suffix.lower(), "image/png")
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    body = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": str(question)[:500]},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
        "max_tokens": 800,
    }
    req = urllib.request.Request(
        base,
        data=_json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = _json.loads(r.read().decode())
            answer = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return {"ok": True, "answer": str(answer)[:2000]}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"视觉模型 HTTP {e.code}: {e.read().decode()[:100]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"视觉模型调用失败: {str(e)[:80]}"}


def analyze_image(path: str, question: str = "") -> dict:
    """分析本地图片：OCR 文字 + 尺寸/格式元数据；有 question 时优先视觉大模型图像理解（失败降级 OCR）。"""
    p = Path(str(path)).expanduser()
    if not p.is_file():
        return {"ok": False, "error": f"文件不存在: {path}"}
    ext = p.suffix.lower()
    if ext not in _MIME:
        return {"ok": False, "error": f"不支持的图片格式: {ext}（支持 png/jpg/gif/webp/bmp/tiff/heic）"}
    try:
        text = ocr_text(p)
        meta = _img_meta(p)
        result = {"ok": True, "ocr_text": text or "（未识别到文字）",
                  "width": meta.get("pixelWidth", ""),
                  "height": meta.get("pixelHeight", ""),
                  "format": meta.get("format", ext.lstrip(".")),
                  "path": str(p.resolve())}
        if question and question.strip():
            v = vision_model_answer(p, question)
            result["vision"] = v
            if v.get("ok"):
                result["answer"] = v["answer"]
            else:
                result["vision_note"] = v.get("error", "") + "——已降级为 OCR"
        return result
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:120]}


# ===== 自测 =====

def test():
    # 用现有截图测
    for img in ("/tmp/eco_page.png",):
        if Path(img).is_file():
            r = analyze_image(img)
            print("analyze:", json.dumps({k: v for k, v in r.items() if k != "path"}, ensure_ascii=False)[:200])
            assert r.get("ok") and "生态环境" in r.get("ocr_text", "")
            print("[OK] vision_tool 自测通过")


if __name__ == "__main__":
    test()
