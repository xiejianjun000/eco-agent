#!/usr/bin/env python3
"""P0 产物链路收敛测试（对标 WorkBuddy MediaArtifactService 单一真源）：

  · present_files 归属校验（isFileOwnedBySession 对标）：只放行产物安全区，
    拒绝 ~/.ssh、/etc、源码目录等系统文件暴露到右栏；
  · 统一 artifact 事件 schema：mimeType/contentType/createdAt/sourceTool 齐全；
  · MIME / contentType 映射。
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.api.chat import (  # noqa: E402
    _artifact_path_allowed,
    _emit_saved_artifact,
    _is_doc_artifact,
    _mime_from_name,
)


class TestArtifactOwnership:
    def test_output_and_tmp_allowed(self):
        out = Path(__file__).resolve().parents[2] / "output" / ".p0_probe.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text("x", encoding="utf-8")
        tmpf = Path(tempfile.gettempdir()) / ".p0_probe.md"
        tmpf.write_text("x", encoding="utf-8")
        try:
            assert _artifact_path_allowed(out) is True
            assert _artifact_path_allowed(tmpf) is True
        finally:
            out.unlink(missing_ok=True)
            tmpf.unlink(missing_ok=True)

    def test_system_and_source_paths_denied(self):
        assert _artifact_path_allowed(Path("/etc/passwd")) is False
        assert _artifact_path_allowed(Path.home() / ".ssh" / "id_rsa") is False
        # 源码目录不是产物区，即使文件存在也拒绝
        assert _artifact_path_allowed(Path(__file__)) is False

    def test_nonexistent_denied(self):
        assert _artifact_path_allowed(Path("definitely_nonexistent_xyz.md")) is False

    def test_traversal_resolved(self):
        # ../ 穿越到源码目录仍应被拒绝（resolve 后不在安全区）
        root = Path(__file__).resolve().parents[2]
        evil = root / "output" / ".." / "server" / "api" / "chat.py"
        assert _artifact_path_allowed(evil) is False


class TestMimeAndContentType:
    def test_mime_map(self):
        assert _mime_from_name("a.md") == "text/markdown"
        assert _mime_from_name("a.docx").startswith("application/vnd.openxml")
        assert _mime_from_name("a.pdf") == "application/pdf"
        assert _mime_from_name("a.png") == "image/png"
        assert _mime_from_name("a.unknownext") == "application/octet-stream"

    def test_content_type(self):
        assert _is_doc_artifact("a.md", "text/markdown") is True
        assert _is_doc_artifact("a.pdf", "application/pdf") is True
        assert _is_doc_artifact("a.png", "image/png") is False


class TestArtifactEventSchema:
    def _emit(self):
        evs = []
        _emit_saved_artifact(
            evs.append,
            "危险废物.md",
            {"saved": True, "path": "/x/output/危险废物.md", "bytes": 100,
             "mime": "text/markdown", "created_ms": 1700000000000},
        )
        return evs

    def test_fields_complete(self):
        ev = self._emit()[0]
        for k in ("type", "title", "name", "path", "size", "mimeType",
                  "contentType", "createdAt", "sourceTool"):
            assert k in ev, f"缺字段 {k}"
        assert ev["type"] == "artifact"
        assert ev["mimeType"] == "text/markdown"
        assert ev["contentType"] == "document"
        assert ev["sourceTool"] == "SaveDocument"
        assert ev["createdAt"] == 1700000000000

    def test_present_files_source_tool(self):
        evs = []
        _emit_saved_artifact(
            evs.append, "r.png",
            {"path": "/x/output/r.png", "name": "r.png", "bytes": 12,
             "mime": "image/png"},
            source_tool="PresentFiles", round_idx=3)
        ev = evs[0]
        assert ev["sourceTool"] == "PresentFiles"
        assert ev["contentType"] == "media"
        assert ev["round"] == 3

    def test_empty_path_no_emit(self):
        evs = []
        _emit_saved_artifact(evs.append, "x", {"saved": True, "path": ""})
        assert evs == []

    def test_emit_throw_never_raises(self):
        def boom(_ev):
            raise RuntimeError("SSE down")
        # emit 失败绝不影响主回答
        _emit_saved_artifact(boom, "x.md", {"path": "/x/output/x.md"})
