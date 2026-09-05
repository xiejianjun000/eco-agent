"""
eco doctor - System health check (8 items)
"""

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("eco.doctor")
logging.basicConfig(level=logging.INFO, format="%(message)s")
ROOT = Path(__file__).resolve().parent.parent.parent
ENV = Path.home() / ".eco" / ".env"

try:
    "".encode(sys.stdout.encoding or "utf-8")
    OK, WA, NO, IN = "[OK]", "[?]", "[X]", "[i]"
except (UnicodeEncodeError, UnicodeTranslateError):
    OK, WA, NO, IN = "[OK]", "[?]", "[X]", "[i]"


def run(args):
    checks = []
    all_pass = True
    v = sys.version.split()[0]
    ok = (sys.version_info.major, sys.version_info.minor) >= (3, 10)
    checks.append((f"Python {v} (>=3.10)", OK if ok else NO))
    if not ok:
        all_pass = False
    ok = all((ROOT / d).exists() for d in ["agent_core", "eco", "gateway"])
    checks.append(("Project structure", OK if ok else NO))
    if not ok:
        all_pass = False
    for mod, desc in [("httpx", "HTTP"), ("cryptography", "Crypto"), ("fastapi", "Web")]:
        try:
            __import__(mod)
            checks.append((f"{mod} ({desc})", OK))
        except ImportError:
            checks.append((f"{mod} ({desc})", NO))
            all_pass = False
    if ENV.exists():
        checks.append(("Config (.eco/.env)", OK))
        p = _env_get("ECO_PROVIDER")
        if p:
            ek_map = {"deepseek": "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY"}
            ek = ek_map.get(p, "DEEPSEEK_API_KEY")
            kv = os.environ.get(ek) or _env_get(ek)
            checks.append((f"API Key ({p})", OK if kv else NO))
            if not kv:
                all_pass = False
        else:
            checks.append(("Provider (ECO_PROVIDER)", WA))
    else:
        checks.append((f"Config ({ENV})", NO))
        all_pass = False
    try:
        import govmcp  # noqa: F401

        checks.append(("GovMCP (governance MCP)", OK))
    except ImportError:
        checks.append(("GovMCP (optional)", WA))
    checks.append(("Gateway config", OK if (ROOT / "gateway" / "gateway.yaml").exists() else WA))
    try:
        import mcp  # noqa: F401

        checks.append(("MCP Python SDK", OK))
    except ImportError:
        checks.append(("MCP Python SDK (optional)", IN))
    # 提示词审计链完整性（SM3 链式 JSONL）
    try:
        from agent_core.prompt_engine import PromptAuditChain

        res = PromptAuditChain().verify_chain()
        if res["valid"]:
            checks.append((f"Prompt audit chain ({res['entries']} entries, valid)", OK))
        else:
            checks.append((f"Prompt audit chain INVALID: {res.get('error', '')}", NO))
            all_pass = False
    except Exception as e:
        checks.append((f"Prompt audit chain (check failed: {e})", WA))
    # SOUL 接线状态
    try:
        from agent_core.soul import load_soul

        soul = load_soul()
        if soul.loaded:
            checks.append((f"SOUL.md 已加载 ({soul.source})", OK))
        else:
            checks.append(("SOUL.md 未找到（回退硬编码人格/安全层）", WA))
    except Exception as e:
        checks.append((f"SOUL 加载异常: {e}", WA))
    # 工具风险分级表（L1-L4）
    try:
        from agent_core.permissions import LEVEL_LABELS, risk_table

        table = risk_table()
        counts = {lv: sum(1 for v in table.values() if v == lv) for lv in ("L1", "L2", "L3", "L4")}
        checks.append((f"Permission gate (L1:{counts['L1']} L2:{counts['L2']} L3:{counts['L3']} L4:{counts['L4']})", OK))
        if getattr(args, "verbose", False):
            print("  ── 工具风险分级表 ──")
            for name in sorted(table):
                lv = table[name]
                print(f"    {lv} {LEVEL_LABELS[lv]:<12} {name}")
    except Exception as e:
        checks.append((f"Permission gate (check failed: {e})", WA))
    # LLM 调用统计（tokens/延迟，来自 ~/.eco/stats.jsonl）
    try:
        from agent_core.llm_client import summarize_llm_stats

        s = summarize_llm_stats()
        if s["calls"]:
            checks.append(
                (
                    f"LLM stats: calls={s['calls']} errors={s['errors']} "
                    f"tokens={s['total_tokens']} avg_latency={s['avg_latency_ms']}ms",
                    OK,
                )
            )
            if getattr(args, "verbose", False):
                print("  ── LLM 调用统计（按 provider）──")
                for p_, agg in sorted(s["by_provider"].items()):
                    print(
                        f"    {p_:<10} calls={agg['calls']} errors={agg['errors']} "
                        f"prompt={agg['prompt_tokens']} completion={agg['completion_tokens']}"
                    )
                print(f"    （明细: {s['stats_file']}）")
        else:
            checks.append(("LLM stats: 暂无调用记录（stats.jsonl 为空）", OK))
    except Exception as e:
        checks.append((f"LLM stats (check failed: {e})", WA))
    # LLM 决策留痕统计（~/.eco/decisions.jsonl，SM3 链）
    try:
        from agent_core.decisions import get_decision_chain, summarize_decisions

        d = summarize_decisions()
        chain_res = get_decision_chain().verify_chain()
        if d["decisions"]:
            checks.append(
                (
                    f"LLM decisions: {d['decisions']} 条，工具选择率 "
                    f"{d['tool_select_rate'] * 100:.0f}%（链校验 {'OK' if chain_res['valid'] else 'INVALID'}）",
                    OK if chain_res["valid"] else NO,
                )
            )
            if getattr(args, "verbose", False):
                print("  ── LLM 决策留痕统计 ──")
                print(f"    finish_reason 分布: {d['by_finish_reason']}")
                for t, n in d["top_tools"]:
                    print(f"    tool: {t} ×{n}")
                print(f"    （明细: {d['decisions_file']}）")
        else:
            checks.append(("LLM decisions: 暂无决策留痕（decisions.jsonl 为空）", OK))
    except Exception as e:
        checks.append((f"LLM decisions (check failed: {e})", WA))
    ml = max(len(c[0]) for c in checks)
    for label, status in checks:
        print(f"  {status} {label}{' ' * (ml - len(label) + 2)}")
    print(f"\n  {OK if all_pass else NO} {'All checks passed!' if all_pass else 'Some checks failed'}")
    return 0 if all_pass else 1


def _env_get(key):
    if not ENV.exists():
        return None
    for line in ENV.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip()
    return None
