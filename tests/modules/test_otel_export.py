"""test_otel_export.py — OTel collector 导出与 trace/decision 关联（全 mock 零外呼）"""
import json
from types import SimpleNamespace
from unittest import mock

import pytest
import yaml

from agent_core import observability as obs
from agent_core.observability import (OTLPExporter, SpanTree, current_trace_id,
                                      set_current_tree, trace_id_for_session)
from agent_core.decisions import record_decision

REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
DEPLOY = REPO / "deploy" / "otel"


def _tree(session_id="test-sess"):
    t = SpanTree(session_id=session_id)
    a = t.start("chat", "session")
    b = t.start("gpt", "llm_call", model="m1")
    t.end(b, finish_reason="stop", prompt_tokens=3)
    t.end(a)
    return t


@pytest.fixture(autouse=True)
def _reset_current_tree():
    yield
    set_current_tree(None)


# ── trace_id 关联 ────────────────────────────────
class TestTraceId:
    def test_deterministic(self):
        assert trace_id_for_session("s1") == trace_id_for_session("s1")
        assert len(trace_id_for_session("s1")) == 32

    def test_tree_property_matches_to_otlp(self):
        t = _tree()
        ids = {sp["traceId"] for rs in t.to_otlp()["resourceSpans"]
               for ss in rs["scopeSpans"] for sp in ss["spans"]}
        assert ids == {t.trace_id}

    def test_current_tree_registered_on_init(self):
        t = _tree("reg-sess")
        assert current_trace_id() == t.trace_id

    def test_current_trace_id_empty_without_tree(self):
        set_current_tree(None)
        assert current_trace_id() == ""

    def test_decision_carries_current_trace_id(self, tmp_path):
        t = _tree("dec-sess")
        entry = record_decision(2, ["read_file"], "tool_calls",
                                path=tmp_path / "d.jsonl")
        payload = json.loads(entry["content"])
        assert payload["trace_id"] == t.trace_id

    def test_decision_trace_id_empty_when_no_tree(self, tmp_path):
        set_current_tree(None)
        entry = record_decision(0, [], "stop", path=tmp_path / "d.jsonl")
        assert json.loads(entry["content"])["trace_id"] == ""

    def test_decision_explicit_trace_id_wins(self, tmp_path):
        entry = record_decision(0, [], "stop", trace_id="ab" * 16,
                                path=tmp_path / "d.jsonl")
        assert json.loads(entry["content"])["trace_id"] == "ab" * 16


# ── OTLPExporter ─────────────────────────────────
class _Resp:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestOTLPExporter:
    def test_default_endpoint(self):
        assert OTLPExporter().traces_url == "http://localhost:4318/v1/traces"

    def test_endpoint_injection_and_env(self, monkeypatch):
        assert OTLPExporter(endpoint="http://x:9/").traces_url == "http://x:9/v1/traces"
        monkeypatch.setenv("ECO_OTLP_ENDPOINT", "http://env:1234")
        assert OTLPExporter().endpoint == "http://env:1234"

    def test_export_success(self, tmp_path):
        t = _tree()
        ex = OTLPExporter(endpoint="http://mock:4318", fallback_dir=tmp_path)
        with mock.patch.object(obs.urllib.request, "urlopen",
                               return_value=_Resp(200)) as m:
            assert ex.export(t) is True
        req = m.call_args[0][0]
        assert req.full_url == "http://mock:4318/v1/traces"
        body = json.loads(req.data.decode("utf-8"))
        assert body["resourceSpans"][0]["resource"]["attributes"]
        assert not list(tmp_path.glob("*.otlp.json"))  # 成功不写降级文件

    def test_export_failure_fallback(self, tmp_path):
        t = _tree("fb-sess")
        ex = OTLPExporter(endpoint="http://down:4318", fallback_dir=tmp_path)
        with mock.patch.object(obs.urllib.request, "urlopen",
                               side_effect=OSError("conn refused")):
            assert ex.export(t) is False
        f = tmp_path / "fb-sess.otlp.json"
        assert f.exists()
        assert json.loads(f.read_text())["resourceSpans"]

    def test_export_non_2xx_fallback(self, tmp_path, caplog):
        t = _tree("http500")
        ex = OTLPExporter(endpoint="http://x:4318", fallback_dir=tmp_path)
        with mock.patch.object(obs.urllib.request, "urlopen",
                               return_value=_Resp(500)):
            with caplog.at_level("WARNING"):
                assert ex.export(t) is False
        assert "降级" in caplog.text
        assert (tmp_path / "http500.otlp.json").exists()

    def test_export_never_raises(self, tmp_path):
        ex = OTLPExporter(endpoint="http://x:4318", fallback_dir=tmp_path)
        with mock.patch.object(obs.urllib.request, "urlopen",
                               side_effect=ValueError("boom")):
            assert ex.export(_tree()) is False


# ── eco trace --export otlp ──────────────────────
class TestCmdTrace:
    def test_export_otlp_via_cmd(self, tmp_path, capsys):
        t = _tree("cmd-sess")
        t.save(directory=tmp_path)
        from eco.commands import cmd_trace
        args = SimpleNamespace(session="cmd-sess", tree=True, otel=None,
                               export="otlp", endpoint="http://mock:4318")
        with mock.patch.object(cmd_trace, "TRACES_DIR", tmp_path), \
             mock.patch.object(obs, "TRACES_DIR", tmp_path), \
             mock.patch.object(obs.urllib.request, "urlopen",
                               return_value=_Resp(200)):
            assert cmd_trace.run(args) == 0
        out = capsys.readouterr().out
        assert "OTel collector" in out and t.trace_id in out

    def test_export_otlp_fallback_via_cmd(self, tmp_path, capsys):
        _tree("cmd-fb").save(directory=tmp_path)
        from eco.commands import cmd_trace
        args = SimpleNamespace(session="cmd-fb", tree=True, otel=None,
                               export="otlp", endpoint="http://down:4318")
        with mock.patch.object(cmd_trace, "TRACES_DIR", tmp_path), \
             mock.patch.object(obs, "TRACES_DIR", tmp_path), \
             mock.patch.object(obs.urllib.request, "urlopen",
                               side_effect=OSError("down")), \
             mock.patch.object(OTLPExporter, "_write_fallback",
                               side_effect=lambda tree: None):
            assert cmd_trace.run(args) == 0
        assert "降级" in capsys.readouterr().out


# ── deploy/otel 配置合法性 ───────────────────────
class TestDeployFiles:
    def test_compose_yaml_valid(self):
        data = yaml.safe_load((DEPLOY / "docker-compose.yml").read_text())
        svcs = data["services"]
        assert "otel-collector" in svcs and "jaeger" in svcs
        assert any("4318" in p for p in svcs["otel-collector"]["ports"])

    def test_collector_config_yaml_valid(self):
        data = yaml.safe_load((DEPLOY / "otel-collector-config.yaml").read_text())
        otlp = data["receivers"]["otlp"]["protocols"]
        assert "grpc" in otlp and "http" in otlp
        traces = data["service"]["pipelines"]["traces"]
        assert "otlp" in traces["receivers"]
        assert any("jaeger" in e for e in traces["exporters"])
        assert "debug" in traces["exporters"]
