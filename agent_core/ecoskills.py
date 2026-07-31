#!/usr/bin/env python3
"""
ecoskills.py — EcoSkills 技能注册表与信任链模块

对标 ClawHub / Skills Hub，但安全前置：
  ClawHub 审计曾发现 36.8% 技能含漏洞，因此本模块强制
  签名（SM3-HMAC）+ 信任分级 + 安装前扫描。

信任三级语义：
  official   官方签名，免审直装
  certified  第三方经审核签名，直装
  community  未签名社区技能，安装必须 --force 且强制扫描告警

签名复用 grants 风格本机密钥：~/.eco/ecoskills_secret（0600，自动生成）。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets as _secrets
import shutil
import stat
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("ecoskills")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HOME = Path.home() / ".eco" / "ecoskills"
SECRET_FILE = Path.home() / ".eco" / "ecoskills_secret"

# ═══════════════════════════════════
# 信任分级
# ═══════════════════════════════════

class TrustTier:
    OFFICIAL = "official"      # 官方签名，免审
    CERTIFIED = "certified"    # 经审核签名
    COMMUNITY = "community"    # 未签名，安装需 --force 且强制扫描告警
    ALL = (OFFICIAL, CERTIFIED, COMMUNITY)

TIER_BADGE = {
    TrustTier.OFFICIAL: "[官方]",
    TrustTier.CERTIFIED: "[认证]",
    TrustTier.COMMUNITY: "[社区]",
}

CATEGORIES = ("法规查询", "文书生成", "数据分析", "监测工具", "集成连接", "其他")


# ═══════════════════════════════════
# SkillManifest
# ═══════════════════════════════════

@dataclass
class SkillManifest:
    name: str = ""
    version: str = "0.1.0"
    author: str = ""
    description: str = ""
    category: str = "其他"
    tags: list[str] = field(default_factory=list)
    trust_tier: str = TrustTier.COMMUNITY
    signature: str = ""                    # SM3-HMAC hex
    entry: str = "SKILL.md"                # 入口文件相对路径
    requires: list[str] = field(default_factory=list)
    min_eco_version: str = "5.0.0"

    def __post_init__(self):
        if self.category not in CATEGORIES:
            self.category = "其他"
        if self.trust_tier not in TrustTier.ALL:
            self.trust_tier = TrustTier.COMMUNITY

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SkillManifest:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def load(cls, skill_dir: str | Path) -> SkillManifest:
        mp = Path(skill_dir) / "manifest.json"
        return cls.from_dict(json.loads(mp.read_text(encoding="utf-8")))

    def canonical_payload(self) -> str:
        """签名载荷：剔除 signature 字段后的规范化 JSON"""
        d = self.to_dict()
        d.pop("signature", None)
        return json.dumps(d, ensure_ascii=False, sort_keys=True)


# ═══════════════════════════════════
# SM3-HMAC 签名 / 验签（grants 风格本机密钥）
# ═══════════════════════════════════

def _sm3_hexdigest(data: bytes) -> str:
    return hashlib.new("sm3", data).hexdigest()


def _local_secret(create: bool = True) -> str:
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text(encoding="utf-8").strip()
    if not create:
        return ""
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    s = _secrets.token_hex(32)
    SECRET_FILE.write_text(s, encoding="utf-8")
    try:
        SECRET_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return s


def sign_manifest(manifest: SkillManifest, secret: str | None = None) -> str:
    """SM3-HMAC 签名。secret 缺省用本机密钥（官方签发场景）。"""
    key = (secret or _local_secret()).encode("utf-8")
    sig = hmac.new(key, manifest.canonical_payload().encode("utf-8"),
                   digestmod=lambda d=b"": hashlib.new("sm3", d)).hexdigest()
    manifest.signature = sig
    return sig


def verify_manifest(manifest: SkillManifest, secret: str | None = None) -> tuple[bool, str]:
    """验签。返回 (是否通过, 原因)。community 级无签名，验签恒失败。"""
    if not manifest.signature:
        return False, "无签名"
    key = (secret or _local_secret()).encode("utf-8")
    expect = hmac.new(key, manifest.canonical_payload().encode("utf-8"),
                      digestmod=lambda d=b"": hashlib.new("sm3", d)).hexdigest()
    if hmac.compare_digest(expect, manifest.signature):
        return True, "签名有效"
    return False, "签名不匹配（内容可能被篡改）"


# ═══════════════════════════════════
# 安装前安全扫描
# ═══════════════════════════════════

# 外联常见域名白名单；其余 URL 一律告警
_COMMON_DOMAINS = {
    "github.com", "raw.githubusercontent.com", "pypi.org", "files.pythonhosted.org",
    "npmjs.com", "registry.npmjs.org", "mee.gov.cn", "gov.cn", "epa.gov",
    "ecoskills.eco-agent.com",
}

_DANGER_PATTERNS: list[tuple[str, str]] = [
    (r"(?:curl|wget)[^|\n]*(?:https?://)[^|\n]*\|\s*(?:sudo\s+)?(?:ba)?sh",
     "curl/wget 直链管道执行远程脚本"),
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r",
     "rm -rf 危险删除命令"),
    (r"\b(?:eval|exec)\s*[\(\"']", "eval/exec 动态代码执行"),
    (r"\bos\.system\s*\(|\bsubprocess\.[A-Za-z_]+\s*\(\s*['\"](?:sh|bash)\b",
     "shell 派生执行"),
    (r"base64\.b64decode\s*\([^)]*\)\s*(?:\)|\.)?\s*(?:.*\bexec\b)?",
     "base64 解码载荷"),
]

_URL_RE = re.compile(r"https?://([a-zA-Z0-9.\-]+)")


def scan_skill(path: str | Path) -> dict:
    """
    安装前安全扫描：SKILL.md 全文分段过 validate_injection + 危险指令检测。
    返回风险报告 {safe, risk_level, findings:[{level,type,detail,line}], entry, scanned_at}
    """
    from agent_core.prompt_engine import validate_injection

    p = Path(path)
    entry = p / "SKILL.md"
    if p.is_dir() and (p / "manifest.json").exists():
        try:
            entry = p / (SkillManifest.load(p).entry or "SKILL.md")
        except Exception:
            pass

    report = {"safe": True, "risk_level": "low", "findings": [],
              "entry": str(entry), "scanned_at": datetime.now().isoformat()}

    if not entry.exists():
        report["safe"] = False
        report["risk_level"] = "high"
        report["findings"].append({"level": "high", "type": "missing_entry",
                                   "detail": f"入口文件不存在: {entry}", "line": 0})
        return report

    text = entry.read_text(encoding="utf-8", errors="replace")
    report["size"] = len(text)

    # 1) validate_injection 全文分段校验（单段 ≤ MAX_INJECTION_LEN）
    seg, seg_no = [], 1
    for line in text.splitlines():
        seg.append(line)
        if sum(len(s) for s in seg) > 700:
            _scan_injection("\n".join(seg), seg_no, report, validate_injection)
            seg, seg_no = [], seg_no + 1
    if seg:
        _scan_injection("\n".join(seg), seg_no, report, validate_injection)

    # 2) 危险指令逐行检测
    for lineno, line in enumerate(text.splitlines(), 1):
        for pattern, desc in _DANGER_PATTERNS:
            if re.search(pattern, line):
                report["findings"].append({"level": "high", "type": "dangerous_command",
                                           "detail": f"{desc}: {line.strip()[:120]}", "line": lineno})
        for m in _URL_RE.finditer(line):
            domain = m.group(1).lower()
            if not any(domain == d or domain.endswith("." + d) for d in _COMMON_DOMAINS):
                report["findings"].append({"level": "medium", "type": "untrusted_outbound",
                                           "detail": f"外联非常见域名: {domain}", "line": lineno})

    levels = {f["level"] for f in report["findings"]}
    report["risk_level"] = "high" if "high" in levels else ("medium" if "medium" in levels else "low")
    report["safe"] = "high" not in levels
    return report


def _scan_injection(seg_text: str, seg_no: int, report: dict, validate_injection) -> None:
    if not seg_text.strip():
        return
    ok, reason = validate_injection(seg_text)
    if not ok and "为空" not in reason and "超长" not in reason:
        # 语言白名单命中多为技能名拼音/产品标识符误报，降级为提示；
        # 禁止 pattern/禁止词（ignore previous instructions 等）才是高危注入
        level = "low" if "语言白名单" in reason else "high"
        report["findings"].append({"level": level, "type": "prompt_injection",
                                   "detail": f"段{seg_no} 疑似提示注入: {reason}", "line": 0})


# ═══════════════════════════════════
# SkillRegistry — 本地索引
# ═══════════════════════════════════

class SkillRegistry:
    """本地技能注册表：~/.eco/ecoskills/index.json"""

    def __init__(self, home: str | Path | None = None):
        self._home = Path(home) if home else DEFAULT_HOME
        self._home.mkdir(parents=True, exist_ok=True)
        (self._home / "skills").mkdir(exist_ok=True)
        self._index_path = self._home / "index.json"
        self._index: dict[str, dict] = {}
        self._load()

    def _load(self):
        if self._index_path.exists():
            try:
                self._index = json.loads(self._index_path.read_text("utf-8", errors="replace"))
            except Exception as e:
                logger.warning(f"EcoSkills 索引加载失败: {e}")

    def _save(self):
        self._index_path.write_text(json.dumps(self._index, ensure_ascii=False, indent=2),
                                    encoding="utf-8")

    # ---------- 安装 ----------

    def install(self, path: str | Path, force: bool = False) -> dict:
        """校验签名 → 扫描 → 登记。community 级必须 force。"""
        p = Path(path)
        if not p.is_dir() or not (p / "manifest.json").exists():
            return {"success": False, "error": f"无效技能包（缺少 manifest.json）: {p}"}
        try:
            manifest = SkillManifest.load(p)
        except Exception as e:
            return {"success": False, "error": f"manifest.json 解析失败: {e}"}
        if not manifest.name:
            return {"success": False, "error": "manifest 缺少 name"}

        # 1) 信任链校验
        verified, reason = verify_manifest(manifest)
        tier = manifest.trust_tier
        if tier in (TrustTier.OFFICIAL, TrustTier.CERTIFIED):
            if not verified:
                return {"success": False, "error": f"{tier} 级技能验签失败: {reason}",
                        "trust_tier": tier}
        else:  # community
            if not force:
                return {"success": False,
                        "error": "community 级技能未签名，安装需显式 --force（将强制安全扫描告警）",
                        "trust_tier": tier, "requires_force": True}

        # 2) 安装前扫描
        report = scan_skill(p)
        if not report["safe"] and not force:
            return {"success": False, "error": "安全扫描发现高风险内容，已阻断（--force 可强行安装）",
                    "trust_tier": tier, "scan": report}

        # 3) 登记 + 落盘
        target = self._home / "skills" / manifest.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(p, target)
        self._index[manifest.name] = {
            "manifest": manifest.to_dict(),
            "verified": verified,
            "path": str(target),
            "scan_risk_level": report["risk_level"],
            "installed_at": datetime.now().isoformat(),
        }
        self._save()
        logger.info(f"[EcoSkills] 安装: {manifest.name} v{manifest.version} ({tier})")
        return {"success": True, "name": manifest.name, "trust_tier": tier,
                "verified": verified, "scan": report, "path": str(target)}

    # ---------- 其余 CRUD ----------

    def remove(self, name: str) -> dict:
        entry = self._index.pop(name, None)
        if not entry:
            return {"success": False, "error": f"技能未安装: {name}"}
        target = Path(entry.get("path", ""))
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        self._save()
        return {"success": True, "name": name}

    def get(self, name: str) -> dict | None:
        return self._index.get(name)

    def list(self) -> list[dict]:
        return [dict(v, name=k) for k, v in sorted(self._index.items())]

    def search(self, keyword: str) -> list[dict]:
        """keyword 匹配 name + tags + description"""
        q = (keyword or "").lower()
        results = []
        for name, v in self._index.items():
            m = v.get("manifest", {})
            hay = [name, m.get("description", ""), *m.get("tags", [])]
            if any(q in str(h).lower() for h in hay):
                results.append(dict(v, name=name))
        return results
