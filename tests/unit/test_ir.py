"""Tests for the IR schema."""

import json
from pathlib import Path

from agent_migrate.ir import (
    ArtifactIR,
    ArtifactKind,
    Confidence,
    Platform,
    SemanticIntent,
    WarningLevel,
)


class TestArtifactIR:
    def test_create_default(self):
        ir = ArtifactIR()
        assert ir.kind == ArtifactKind.UNKNOWN
        assert ir.source_platform == Platform.UNKNOWN
        assert ir.confidence == Confidence.MEDIUM

    def test_add_warning(self):
        ir = ArtifactIR()
        ir.add_warning("test warning", code="TEST")
        assert len(ir.warnings) == 1
        assert ir.warnings[0].message == "test warning"
        assert ir.warnings[0].code == "TEST"

    def test_add_todo(self):
        ir = ArtifactIR()
        ir.add_todo("implement this", priority="high", reason="needed")
        assert len(ir.manual_todos) == 1
        assert ir.manual_todos[0].priority == "high"

    def test_json_roundtrip(self):
        ir = ArtifactIR(
            kind=ArtifactKind.SKILL,
            source_platform=Platform.CLAUDE,
            name="test-skill",
            confidence=Confidence.HIGH,
        )
        ir.add_warning("test")
        json_str = ir.to_json()
        data = json.loads(json_str)
        assert data["kind"] == "skill"
        assert data["name"] == "test-skill"

    def test_save_and_load(self, tmp_path):
        ir = ArtifactIR(
            kind=ArtifactKind.INSTRUCTION_DOC,
            source_platform=Platform.CLAUDE,
            name="test",
        )
        path = tmp_path / "test.json"
        ir.save(path)
        loaded = ArtifactIR.load(path)
        assert loaded.kind == ir.kind
        assert loaded.name == ir.name
