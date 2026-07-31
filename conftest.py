"""pytest 共享配置"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 单测强制走规则降级：离线可跑、不耗 API 配额（LLM 路径由 scripts/smoke_kimi.py 覆盖）
os.environ["ECO_LLM_DISABLE"] = "1"

# 单测默认关闭权限闸门（避免非交互拒绝影响存量用例）；权限闸门测试显式开盖
os.environ.setdefault("ECO_PERMISSION_GATE", "0")
os.environ.setdefault("ECO_NONINTERACTIVE", "1")
