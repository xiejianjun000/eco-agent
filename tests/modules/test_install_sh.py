# -*- coding: utf-8 -*-
"""install.sh 端到端测试：装到临时 HOME，校验 eco 原生 profile 文件落位

实跑记录（2026，临时 HOME）：脚本退出码 0，~/.eco/profiles/eco-agent 下
config.yaml / SOUL.md / MEMORY.md / USER.md / PERMISSION.md 与 skills、memory-tree
目录全部就位；未检测到 hermes CLI 时打印可选宿主跳过提示，属预期分支。
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
INSTALL_SH = REPO / "profiles" / "eco-agent" / "install.sh"


@pytest.mark.skipif(shutil.which("bash") is None, reason="需要 bash")
def test_install_sh_end_to_end(tmp_path):
    assert INSTALL_SH.exists()
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home))
    proc = subprocess.run(["bash", str(INSTALL_SH)], env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, f"install.sh 失败: {proc.stderr}\n{proc.stdout}"
    profile = home / ".eco" / "profiles" / "eco-agent"
    for f in ("config.yaml", "SOUL.md", "MEMORY.md", "USER.md", "PERMISSION.md"):
        assert (profile / f).exists(), f"缺少 {f}"
    assert (profile / "skills").is_dir()
    assert (profile / "memory-tree").is_dir()
    assert "eco profile 安装完成" in proc.stdout
    # SOUL 内容非空（人格定义真实安装）
    assert (profile / "SOUL.md").read_text(encoding="utf-8").strip()
