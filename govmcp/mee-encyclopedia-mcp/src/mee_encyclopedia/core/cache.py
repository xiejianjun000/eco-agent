"""二级缓存：内存（快）+ 磁盘（持久）。实时数据按 TTL 失效。"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Cache:
    """内存 + 磁盘二级缓存。

    用法::
        cache = Cache(config)
        data = cache.get("air:beijing") or await cache.set("air:beijing", value, ttl=300)
    """

    def __init__(self, base_dir: Path, ttl: int = 300, ttl_slow: int = 3600, max_entries: int = 512) -> None:
        self._mem: dict[str, tuple[float, Any]] = {}
        self._disk_dir = base_dir / "cache"
        self._disk_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self.ttl_slow = ttl_slow
        self.max_entries = max_entries

    def _key_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self._disk_dir / f"{digest}.json"

    def get(self, key: str) -> Any | None:
        """命中且未过期返回数据，否则 None。"""
        now = time.time()
        hit = self._mem.get(key)
        if hit:
            expire_at, value = hit
            if expire_at > now:
                return value
            self._mem.pop(key, None)
        # 磁盘兜底
        path = self._key_path(key)
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("expire_at", 0) > now:
                    self._mem[key] = (payload["expire_at"], payload["value"])
                    return payload["value"]
            except Exception as exc:  # noqa: BLE001
                logger.debug("缓存读取失败 %s: %s", key, exc)
        return None

    def set(self, key: str, value: Any, ttl: int | None = None, slow: bool = False) -> Any:
        expire_at = time.time() + (ttl if ttl is not None else (self.ttl_slow if slow else self.ttl))
        if len(self._mem) >= self.max_entries:
            self._mem.pop(next(iter(self._mem)), None)
        self._mem[key] = (expire_at, value)
        try:
            payload = {"expire_at": expire_at, "value": value}
            self._key_path(key).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.debug("缓存写入失败 %s: %s", key, exc)
        return value

    def clear(self) -> None:
        self._mem.clear()
        for p in self._disk_dir.glob("*.json"):
            p.unlink(missing_ok=True)
