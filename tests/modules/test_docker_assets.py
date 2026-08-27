"""任务 F：Docker 镜像与离线部署资产的静态断言测试（全静态，无需 docker）。"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"
BUILD_OFFLINE = ROOT / "deploy" / "offline" / "build_offline.sh"
UNIT = ROOT / "deploy" / "systemd" / "eco-gateway.service"


@pytest.fixture(scope="module")
def dockerfile_text():
    assert DOCKERFILE.is_file(), "Dockerfile 缺失"
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dockerignore_lines():
    assert DOCKERIGNORE.is_file(), ".dockerignore 缺失"
    return [ln.strip() for ln in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


@pytest.fixture(scope="module")
def build_script_text():
    assert BUILD_OFFLINE.is_file(), "deploy/offline/build_offline.sh 缺失"
    return BUILD_OFFLINE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def unit_text():
    assert UNIT.is_file(), "eco-gateway.service 缺失"
    return UNIT.read_text(encoding="utf-8")


# ---------- Dockerfile ----------

def test_dockerfile_base_image(dockerfile_text):
    assert re.search(r"^FROM\s+python:3\.12-slim", dockerfile_text, re.M)


def test_dockerfile_multi_stage(dockerfile_text):
    stages = re.findall(r"^FROM\s+\S+\s+AS\s+(\w+)", dockerfile_text, re.M)
    assert len(stages) >= 2, "应使用多阶段构建"


def test_dockerfile_installs_requirements_into_venv(dockerfile_text):
    assert "venv" in dockerfile_text
    assert re.search(r"pip install.*-r\s+.*requirements\.txt", dockerfile_text, re.S)


def test_dockerfile_installs_bubblewrap(dockerfile_text):
    assert "bubblewrap" in dockerfile_text


def test_dockerfile_installs_slirp4netns(dockerfile_text):
    assert "slirp4netns" in dockerfile_text


def test_dockerfile_non_root_user(dockerfile_text):
    assert re.search(r"^USER\s+eco\b", dockerfile_text, re.M), "运行期必须切到非 root 用户 eco"


def test_dockerfile_entrypoint(dockerfile_text):
    assert 'ENTRYPOINT ["python", "-m", "eco.cli"]' in dockerfile_text


def test_dockerfile_no_hardcoded_secrets(dockerfile_text):
    assert not re.search(r"sk-[0-9a-f]{8,}", dockerfile_text)
    assert "ghp_" not in dockerfile_text


# ---------- .dockerignore ----------

@pytest.mark.parametrize("rule", [".git", "tests", "docs", "output", "backup"])
def test_dockerignore_required_rules(dockerignore_lines, rule):
    assert rule in dockerignore_lines


def test_dockerignore_excludes_env(dockerignore_lines):
    assert ".env" in dockerignore_lines


# ---------- build_offline.sh ----------

def test_build_script_pip_download(build_script_text):
    assert "pip download" in build_script_text
    assert "offline_wheels" in build_script_text


def test_build_script_generates_install_sh(build_script_text):
    assert "install.sh" in build_script_text
    assert "--no-index" in build_script_text, "离线安装必须 pip install --no-index"
    assert "--find-links" in build_script_text


def test_build_script_strict_mode_and_no_secrets(build_script_text):
    assert "set -euo pipefail" in build_script_text
    assert not re.search(r"sk-[0-9a-f]{8,}", build_script_text)
    assert "ghp_" not in build_script_text


# ---------- systemd unit ----------

def test_unit_service_section(unit_text):
    assert "[Service]" in unit_text
    assert "[Install]" in unit_text


def test_unit_service_fields(unit_text):
    assert re.search(r"^User=eco$", unit_text, re.M)
    assert re.search(r"^ExecStart=.*python -m eco\.cli gateway start", unit_text, re.M)
    assert re.search(r"^Restart=on-failure", unit_text, re.M)


def test_unit_hardening_and_no_secrets(unit_text):
    assert "NoNewPrivileges=true" in unit_text
    assert "EnvironmentFile=" in unit_text, "密钥必须经 EnvironmentFile 注入"
    assert not re.search(r"sk-[0-9a-f]{8,}", unit_text)
    assert "ghp_" not in unit_text
