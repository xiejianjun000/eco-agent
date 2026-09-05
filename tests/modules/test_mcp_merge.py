"""mcp_connector 配置源合并测试（对标路线 M2 收尾：registry → ReAct 接线）

覆盖：env 与 registry 双源合并、同名 registry 覆盖 env、坏配置跳过、注册表缺失降级。
离线：只测配置解析，不发起真实 MCP 连接。
"""

import json
import os

import pytest

from agent_core.mcp_connector import (
    MCPConnectorManager,
    MCPServerConfig,
    load_configs_from_env,
    load_configs_from_registry,
    load_merged_configs,
)
from agent_core.mcp_registry import MCPRegistry


@pytest.fixture
def iso_env(tmp_path, monkeypatch):
    """隔离 registry store + env 配置，避免污染真实 ~/.eco。"""
    monkeypatch.setenv("ECO_MCP_REGISTRY", str(tmp_path / "mcp_registry.json"))
    monkeypatch.setenv(
        "ECO_MCP_SERVERS",
        json.dumps(
            [
                {"name": "env_only", "transport": "http", "url": "http://env.example/mcp"},
                {"name": "same_name", "transport": "http", "url": "http://env.example/old"},
            ]
        ),
    )
    return tmp_path


def _reg():
    """按当前 ECO_MCP_REGISTRY env 定位的 MCPRegistry（与 connector 读端一致）。"""
    return MCPRegistry(store=os.environ["ECO_MCP_REGISTRY"])


def test_env_only(iso_env):
    names = {c.name for c in load_configs_from_env()}
    assert names == {"env_only", "same_name"}


def test_registry_only(iso_env):
    _reg().add("reg_only", "http", url="http://reg.example/mcp")
    names = {c.name for c in load_configs_from_registry()}
    assert names == {"reg_only"}


def test_merged_union_and_override(iso_env):
    _reg().add("reg_only", "http", url="http://reg.example/mcp")
    _reg().add("same_name", "http", url="http://reg.example/new", headers={"X-Api-Key": "k"})
    cfg = {c.name: c for c in load_merged_configs()}
    assert set(cfg) == {"env_only", "reg_only", "same_name"}
    assert cfg["same_name"].url == "http://reg.example/new"  # registry 覆盖 env
    assert cfg["same_name"].headers == {"X-Api-Key": "k"}


def test_connector_default_configs_are_merged(iso_env):
    _reg().add("reg_only", "http", url="http://reg.example/mcp")
    mgr = MCPConnectorManager(configs=None)
    try:
        assert {c.name for c in mgr.configs} == {"env_only", "same_name", "reg_only"}
    finally:
        mgr.close()


def test_empty_registry_degrades(iso_env, monkeypatch):
    monkeypatch.setenv("ECO_MCP_REGISTRY", str(iso_env / "nope.json"))
    # 注册表缺失/为空 → registry 源为空，env 配置不受影响
    names = {c.name for c in load_merged_configs()}
    assert names == {"env_only", "same_name"}


def test_from_dict_roundtrip():
    c = MCPServerConfig.from_dict({"name": "x", "transport": "stdio", "command": ["python", "/tmp/s.py"]})
    assert c.name == "x" and c.command == ["python", "/tmp/s.py"]
