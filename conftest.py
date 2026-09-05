"""pytest 共享配置"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 单测强制走规则降级：离线可跑、不耗 API 配额（LLM 路径由 scripts/smoke_kimi.py 覆盖）
os.environ["ECO_LLM_DISABLE"] = "1"

# 单测默认关闭权限闸门（避免非交互拒绝影响存量用例）；权限闸门测试显式开盖
os.environ.setdefault("ECO_PERMISSION_GATE", "0")
os.environ.setdefault("ECO_NONINTERACTIVE", "1")

# 隔离宿主机真实环境：
# 1) 清空所有 *_API_KEY —— 避免真实 Key 触发 provider 降级链导致用例失败，
#    也避免失败断言把真实 Key 打进测试日志（见 issue #2）
# 2) HOME 重定向到临时目录 —— ~/.eco/.env、stats.jsonl 等读写全部进临时目录，
#    单测结果与宿主机配置无关
for _k in [k for k in os.environ if k.endswith("_API_KEY")]:
    os.environ.pop(_k, None)
os.environ["HOME"] = tempfile.mkdtemp(prefix="eco-test-home-")
