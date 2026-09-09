"""运行时目录解析测试。

背景：~/.eco 曾被 28 个文件、33 处硬编码。沙箱下实测同时踩中三处失效：
  权限审计链 prompt_audit.jsonl / checkpoints / traces
其中权限审计整条丢失却只在 stderr 打一行——合规系统不能这么丢证据。
"""
import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _fresh():
    """清缓存重新解析（eco_dir 带 lru_cache）。"""
    import agent_core.eco_paths as m
    importlib.reload(m)
    return m


def test_env_var_wins(tmp_path, monkeypatch):
    """显式指定 ECO_DIR 时一律听它的。"""
    target = tmp_path / "custom"
    monkeypatch.setenv("ECO_DIR", str(target))
    m = _fresh()
    assert m.eco_dir() == target
    assert target.is_dir()


def test_eco_home_alias(tmp_path, monkeypatch):
    """ECO_HOME 是历史别名，也要认。"""
    monkeypatch.delenv("ECO_DIR", raising=False)
    target = tmp_path / "viahome"
    monkeypatch.setenv("ECO_HOME", str(target))
    m = _fresh()
    assert m.eco_dir() == target


def test_fallback_when_home_unwritable(tmp_path, monkeypatch):
    """~/.eco 不可写时回退仓库 .eco/，绝不能让审计静默丢失。"""
    monkeypatch.delenv("ECO_DIR", raising=False)
    monkeypatch.delenv("ECO_HOME", raising=False)
    m = _fresh()
    # 把 _writable 打成永远失败，模拟沙箱
    monkeypatch.setattr(m, "_writable", lambda p: False)
    m.eco_dir.cache_clear()
    got = m.eco_dir()
    assert got == REPO / ".eco", f"应回退到仓库 .eco/，实际 {got}"
    assert got.is_dir()
    m.eco_dir.cache_clear()


def test_writable_probe_really_writes(tmp_path):
    """_writable 必须实写探测 —— os.access 在沙箱下会说谎。"""
    m = _fresh()
    assert m._writable(tmp_path / "sub") is True
    assert (tmp_path / "sub").is_dir()
    # 探测文件不能残留
    assert not list((tmp_path / "sub").glob(".write-probe"))


def test_consumers_share_one_root(monkeypatch, tmp_path):
    """所有消费方必须指向同一个根，不能各解析各的。"""
    target = tmp_path / "shared"
    monkeypatch.setenv("ECO_DIR", str(target))
    for name in ("agent_core.eco_paths", "agent_core.prompt_engine",
                 "agent_core.checkpoint", "agent_core.corrections",
                 "agent_core.observability"):
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    from agent_core.eco_paths import eco_dir
    assert eco_dir() == target


def test_subdir_helper(tmp_path, monkeypatch):
    monkeypatch.setenv("ECO_DIR", str(tmp_path / "s"))
    m = _fresh()
    d = m.eco_subdir("traces")
    assert d.is_dir() and d.name == "traces"
