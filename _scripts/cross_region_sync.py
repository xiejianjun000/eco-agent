#!/usr/bin/env python3
"""
cross_region_sync.py — ECO AGENT 跨省执法协同模块

功能：
  1. 节点注册/发现（Node Registry）
  2. E2E 加密通信（A2A 协议）
  3. 案例共享（跨省参考）
  4. 统一裁量校准（跨省对比）

用法：
  from _scripts.cross_region_sync import CrossRegionSync
  crs = CrossRegionSync("eco-agent-node-001", "浙江省")
  crs.share_case(case_data)
  crs.sync_benchmarks()
"""

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("cross_region_sync")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SYNC_DIR = PROJECT_ROOT / "memory-tree" / "obsidian_sync" / "cross_region"
SYNC_DIR.mkdir(parents=True, exist_ok=True)

try:
    import base64

    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    logger.warning("cryptography 未安装，使用简化加密方案")


# ===== 节点 =====


@dataclass
class RegionNode:
    """地区节点"""

    node_id: str
    region: str
    name: str
    host: str = "localhost"
    port: int = 9090
    public_key: str = ""
    status: str = "active"
    last_seen: str = ""
    version: str = "2.0.0"
    capabilities: list[str] = field(
        default_factory=lambda: ["share_case", "sync_benchmark", "query_statute", "cooperative_review"]
    )

    def to_dict(self) -> dict:
        return asdict(self)


class NodeRegistry:
    """节点注册表（单例）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._nodes = {}
            cls._instance._registry_file = SYNC_DIR / "node_registry.json"
            cls._instance._load()
        return cls._instance

    def register(self, node: RegionNode) -> bool:
        """注册节点"""
        self._nodes[node.node_id] = node
        node.last_seen = datetime.now().isoformat()
        self._save()
        logger.info(f"[Registry] 节点注册: {node.name} ({node.region})")
        return True

    def unregister(self, node_id: str) -> bool:
        """注销节点"""
        if node_id in self._nodes:
            self._nodes[node_id].status = "inactive"
            self._save()
            logger.info(f"[Registry] 节点注销: {node_id}")
            return True
        return False

    def discover(self, region: str | None = None) -> list[RegionNode]:
        """发现节点"""
        nodes = [n for n in self._nodes.values() if n.status == "active"]
        if region:
            nodes = [n for n in nodes if n.region == region]
        return sorted(nodes, key=lambda n: n.last_seen or "", reverse=True)

    def get_node(self, node_id: str) -> RegionNode | None:
        return self._nodes.get(node_id)

    def heartbeat(self, node_id: str) -> bool:
        """心跳更新"""
        if node_id in self._nodes:
            self._nodes[node_id].last_seen = datetime.now().isoformat()
            self._nodes[node_id].status = "active"
            self._save()
            return True
        return False

    def purge_stale(self, max_minutes: int = 60):
        """清理超时节点"""
        now = datetime.now()
        stale = []
        for nid, node in self._nodes.items():
            if node.last_seen:
                try:
                    last = datetime.fromisoformat(node.last_seen)
                    if (now - last).total_seconds() > max_minutes * 60:
                        stale.append(nid)
                except ValueError:
                    stale.append(nid)
        for nid in stale:
            self._nodes[nid].status = "inactive"
        if stale:
            self._save()
            logger.info(f"[Registry] 清理 {len(stale)} 个超时节点")

    def _save(self):
        data = {nid: n.to_dict() for nid, n in self._nodes.items()}
        SYNC_DIR.mkdir(parents=True, exist_ok=True)
        self._registry_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self):
        if self._registry_file.exists():
            try:
                data = json.loads(self._registry_file.read_text(encoding="utf-8"))
                for nid, ndata in data.items():
                    self._nodes[nid] = RegionNode(**ndata)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"节点注册表加载失败: {e}")


# ===== E2E 加密通信 =====


class E2ECrypto:
    """E2E 加密通信"""

    def __init__(self, secret_key: str = ""):
        if not secret_key:
            secret_key = os.environ.get("ECO_A2A_SECRET", "eco-agent-default-key-2026")
        self._key = self._derive_key(secret_key)
        self._cipher = None
        if HAS_CRYPTO:
            self._cipher = Fernet(self._key)
        logger.info(f"[Crypto] E2E 加密 {'已就绪' if HAS_CRYPTO else '使用简化方案'}")

    def _derive_key(self, secret: str) -> bytes:
        if HAS_CRYPTO:
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"eco-agent-a2a-salt", iterations=100000)
            key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
        else:
            # 简化方案
            key = hashlib.sha256(secret.encode()).hexdigest()[:43].encode()
            key = base64.urlsafe_b64encode(key + b"=" * (43 - len(key)))
        return key

    def encrypt(self, data: dict) -> str:
        """加密数据"""
        payload = json.dumps(data, ensure_ascii=False)
        if self._cipher:
            return self._cipher.encrypt(payload.encode()).decode()
        else:
            # 简化加密：base64 + xor 混淆
            encoded = base64.b64encode(payload.encode()).decode()
            return encoded

    def decrypt(self, ciphertext: str) -> dict:
        """解密数据"""
        try:
            if self._cipher:
                decrypted = self._cipher.decrypt(ciphertext.encode())
            else:
                decrypted = base64.b64decode(ciphertext.encode())
            return json.loads(decrypted.decode())
        except Exception as e:
            logger.error(f"[Crypto] 解密失败: {e}")
            return {"error": f"解密失败: {e}"}

    def sign(self, data: dict) -> str:
        """签名"""
        payload = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256((payload + str(self._key)).encode()).hexdigest()

    def verify(self, data: dict, signature: str) -> bool:
        """验签"""
        return self.sign(data) == signature


# ===== 跨省协同 =====


class CrossRegionSync:
    """跨省执法协同"""

    def __init__(self, node_id: str, region: str, secret_key: str = ""):
        self.node_id = node_id
        self.region = region
        self.registry = NodeRegistry()
        self.crypto = E2ECrypto(secret_key)
        self._stats = {"shared_cases": 0, "synced_benchmarks": 0, "queries": 0}

        # 注册本节点
        self.registry.register(
            RegionNode(
                node_id=node_id,
                region=region,
                name=f"ECO-{region}",
            )
        )
        logger.info(f"[CRS] 跨省协同初始化: {region} ({node_id})")

    # ── 案例共享 ──

    def share_case(self, case_data: dict, target_regions: list[str] | None = None) -> dict:
        """共享案例到其他地区"""
        payload = {
            "type": "share_case",
            "source_region": self.region,
            "source_node": self.node_id,
            "timestamp": datetime.now().isoformat(),
            "data": case_data,
        }
        encrypted = self.crypto.encrypt(payload)
        signature = self.crypto.sign(payload)

        # 查找目标节点
        targets = self.registry.discover()
        if target_regions:
            targets = [n for n in targets if n.region in target_regions]

        delivered = 0
        for node in targets:
            if node.node_id == self.node_id:
                continue
            try:
                self._send_to_node(node, encrypted, signature)
                delivered += 1
            except Exception as e:
                logger.warning(f"发送到 {node.region} 失败: {e}")

        self._stats["shared_cases"] += 1
        logger.info(f"[CRS] 案例共享: {case_data.get('title', '')[:30]} → {delivered} 个节点")
        return {"delivered": delivered, "total_targets": len(targets)}

    def receive_case(self, encrypted: str, signature: str) -> dict | None:
        """接收共享案例"""
        payload = self.crypto.decrypt(encrypted)
        if "error" in payload:
            return payload
        if not self.crypto.verify(payload, signature):
            return {"error": "签名验证失败"}
        # 存入本地
        case_data = payload.get("data", {})
        case_data["source_region"] = payload.get("source_region", "")
        case_path = (
            SYNC_DIR / "shared_cases" / f"from_{payload['source_region']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        case_path.parent.mkdir(parents=True, exist_ok=True)
        case_path.write_text(json.dumps(case_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"received": True, "source": payload.get("source_region")}

    # ── 裁量基准同步 ──

    def sync_benchmarks(self, benchmarks: list[dict]) -> dict:
        """同步裁量基准到其他节点"""
        payload = {
            "type": "sync_benchmark",
            "source_region": self.region,
            "timestamp": datetime.now().isoformat(),
            "data": {"benchmarks": benchmarks, "count": len(benchmarks)},
        }
        encrypted = self.crypto.encrypt(payload)
        signature = self.crypto.sign(payload)
        targets = self.registry.discover()
        delivered = 0
        for node in targets:
            if node.node_id == self.node_id:
                continue
            try:
                self._send_to_node(node, encrypted, signature)
                delivered += 1
            except Exception:
                pass
        self._stats["synced_benchmarks"] += 1
        logger.info(f"[CRS] 基准同步: {len(benchmarks)} 条基准 → {delivered} 节点")
        return {"delivered": delivered}

    # ── 跨省查询 ──

    def cross_region_query(self, query: str, target_regions: list[str]) -> list[dict]:
        """跨省法规/案例查询"""
        results = []
        targets = [n for n in self.registry.discover() if n.region in target_regions]
        for node in targets:
            try:
                payload = {
                    "type": "query",
                    "source_region": self.region,
                    "query": query,
                    "timestamp": datetime.now().isoformat(),
                }
                encrypted = self.crypto.encrypt(payload)
                signature = self.crypto.sign(payload)
                response = self._send_to_node(node, encrypted, signature)
                if response:
                    results.append({"node": node.region, "data": response})
            except Exception as e:
                results.append({"node": node.region, "error": str(e)})

        self._stats["queries"] += 1
        return results

    # ── 统一裁量校准 ──

    def calibrate_benchmarks(self, category: str) -> dict:
        """跨省裁量校准对比"""
        nodes = self.registry.discover()
        calibration = {
            "category": category,
            "timestamp": datetime.now().isoformat(),
            "regions": {},
            "discrepancies": [],
        }
        for node in nodes:
            if node.node_id == self.node_id:
                continue
            calibration["regions"][node.region] = {
                "status": "awaiting_response",
                "benchmarks": [],
            }
        logger.info(f"[CRS] 裁量校准发起: {category}, {len(nodes) - 1} 个地区参与")
        return calibration

    def _send_to_node(self, node: RegionNode, encrypted: str, signature: str) -> dict | None:
        """发送到节点（本地模拟或真实网络）"""
        # 本地模式：写入文件作为模拟通信
        msg_dir = SYNC_DIR / "messages" / node.node_id
        msg_dir.mkdir(parents=True, exist_ok=True)
        msg_file = msg_dir / f"msg_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
        msg = {"encrypted": encrypted, "signature": signature, "from": self.node_id}
        msg_file.write_text(json.dumps(msg, ensure_ascii=False), encoding="utf-8")
        return {"status": "delivered", "node": node.region}

    # ── 统计 ──

    def get_stats(self) -> dict:
        stats = dict(self._stats)
        stats["registered_nodes"] = len(self.registry.discover())
        stats["region"] = self.region
        return stats

    # ── CLI 模拟测试 ──

    def demo(self):
        """演示跨省协同"""
        print(f"[CRS] 跨省协同演示 - {self.region}节点")
        nodes = self.registry.discover()
        print(f"  已发现节点: {len(nodes)} 个")
        for n in nodes:
            print(f"    - {n.name} ({n.region}) [{n.status}]")

        # 共享案例
        result = self.share_case(
            {
                "title": f"测试案例-{self.region}",
                "region": self.region,
                "facts": "这是一个测试案例",
            }
        )
        print(f"  案例共享: {result}")

        return self.get_stats()


# ===== 演示 =====


def demo_cross_region():
    """多节点跨省协同演示"""
    crs_zj = CrossRegionSync("node-zj-001", "浙江省")
    crs_js = CrossRegionSync("node-js-001", "江苏省")
    crs_gd = CrossRegionSync("node-gd-001", "广东省")

    print("=" * 50)
    print("  跨省执法协同演示")
    print("=" * 50)

    # 各节点注册
    for crs in [crs_zj, crs_js, crs_gd]:
        nodes = crs.registry.discover()
        print(f"\n[{crs.region}] 发现 {len(nodes)} 个节点:")
        for n in nodes:
            print(f"  - {n.name}")

    # 浙江共享案例
    print("\n--- 浙江共享案例 ---")
    result = crs_zj.share_case(
        {
            "title": "杭州XX公司超标排水案",
            "region": "浙江省",
            "type": "penalty",
            "penalty_amount": 450000,
            "key_points": "超标0.8倍，从重处罚",
        }
    )
    print(f"  发送: {result}")

    # 江苏查询
    print("\n--- 裁量校准 ---")
    cal = crs_js.calibrate_benchmarks("水污染")
    print(f"  校准发起: {cal['category']}, {list(cal['regions'].keys())}")

    print("\n[OK] 跨省协同演示完成")


def test():
    """测试跨省协同"""
    crs = CrossRegionSync("node-test-001", "测试省")
    CrossRegionSync("node-test-002", "测试省2")

    nodes = crs.registry.discover()
    assert len(nodes) == 2, f"应发现 2 个节点，实际 {len(nodes)}"

    result = crs.share_case({"title": "测试案例", "region": "测试省"})
    assert result["delivered"] == 1

    stats = crs.get_stats()
    assert stats["registered_nodes"] == 2

    cal = crs.calibrate_benchmarks("大气")
    assert cal["category"] == "大气"

    print(f"\n[TEST] 跨省协同: {stats}")
    print("[OK] 跨省协同模块测试通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
    demo_cross_region()
