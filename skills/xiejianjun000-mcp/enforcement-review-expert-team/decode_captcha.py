"""验证码 OCR 识别 — 支持文件模式与 stdin 管道模式"""
import base64
import sys
import os
import argparse

try:
    import ddddocr
except ImportError:
    print("ERROR: ddddocr not installed. Run: pip install ddddocr", file=sys.stderr)
    sys.exit(1)


def decode(b64_data: str) -> str:
    """从 base64 解码图片并用 ddddocr 识别"""
    if b64_data.startswith("data:image/png;base64,"):
        b64_data = b64_data[len("data:image/png;base64,"):]

    img_data = base64.b64decode(b64_data.strip())
    ocr = ddddocr.DdddOcr(show_ad=False)
    return ocr.classification(img_data)


def main():
    parser = argparse.ArgumentParser(description="验证码 OCR 识别")
    parser.add_argument("--stdin", action="store_true", help="从 stdin 读取 base64")
    parser.add_argument("file", nargs="?", help="含 base64 的文本文件路径")
    args = parser.parse_args()

    if args.stdin:
        b64_data = sys.stdin.read().strip()
        if not b64_data:
            print("ERROR: stdin is empty", file=sys.stderr)
            sys.exit(1)
    elif args.file:
        with open(args.file, "r") as f:
            b64_data = f.read().strip()
    else:
        print("ERROR: 需要 --stdin 或文件路径", file=sys.stderr)
        sys.exit(1)

    try:
        result = decode(b64_data)
        print(result)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
