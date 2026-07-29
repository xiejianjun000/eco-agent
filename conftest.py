"""pytest 共享配置"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 单测强制走规则降级：离线可跑、不耗 API 配额（LLM 路径由 scripts/smoke_kimi.py 覆盖）
os.environ["ECO_LLM_DISABLE"] = "1"
