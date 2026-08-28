"""envboot 空值遮蔽修复回归（2026-08-23 线上事故：DEEPSEEK_API_KEY= 空值遮蔽）。

事故链：GUI 启动器/非登录 shell 的环境里预置空 DEEPSEEK_API_KEY=，
python-dotenv override=False 跳过补填 → llm_client 报 no api key。
修复：空值视为缺失，按 仓库 .env > ~/.eco/.env 顺序补填非空值。
"""

from agent_core.envboot import _fill_empty_keys, _parse_env_file


def test_parse_env_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# 注释\nA=1\nB=2\nEMPTY=\nQ=\"quoted\"\nS='single'\nBAD_LINE\n",
                 encoding="utf-8")
    out = _parse_env_file(f)
    assert out == {"A": "1", "B": "2", "EMPTY": "", "Q": "quoted", "S": "single"}


def test_fill_empty_shadowed_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")  # 空值遮蔽
    filled = _fill_empty_keys([
        {"DEEPSEEK_API_KEY": "sk-REPO"},     # 仓库 .env
        {"DEEPSEEK_API_KEY": "", "OTHER": "x"},  # ~/.eco/.env
    ])
    import os
    assert filled >= 1
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-REPO"


def test_fill_falls_back_to_user_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    _fill_empty_keys([
        {"DEEPSEEK_API_KEY": ""},            # 仓库 .env 也是空
        {"DEEPSEEK_API_KEY": "sk-USER"},
    ])
    import os
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-USER"


def test_real_nonempty_env_wins(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-REAL")
    filled = _fill_empty_keys([{"DEEPSEEK_API_KEY": "sk-REPO"}])
    import os
    assert filled == 0
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-REAL"  # 真实环境变量优先，不被覆盖


def test_absent_key_is_filled(monkeypatch):
    # 用 setenv 空值而非 delenv：delenv 对不存在的变量不记录回滚，
    # 直接 os.environ 赋值会泄漏到后续用例（曾污染 test_keystore）
    monkeypatch.setenv("ECO_PROVIDER", "")
    filled = _fill_empty_keys([{"ECO_PROVIDER": "deepseek"}, {}])
    import os
    assert filled == 1
    assert os.environ["ECO_PROVIDER"] == "deepseek"
