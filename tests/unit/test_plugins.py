"""Tests for the plugin system wiring."""

import pytest

from agent_migrate.detector import detect_artifact
from agent_migrate.ir import ArtifactIR, ArtifactKind, Confidence, Platform
from agent_migrate.mapper import map_artifact
from agent_migrate.plugins import (
    clear_registries,
    register_detector,
    register_mapper,
)


@pytest.fixture(autouse=True)
def clean_registries():
    clear_registries()
    yield
    clear_registries()


class FakeDetector:
    """Recognizes only files named GEMINI.md."""

    def detect(self, path: str):
        if path.endswith("GEMINI.md"):
            return ArtifactIR(
                kind=ArtifactKind.INSTRUCTION_DOC,
                source_platform=Platform.UNKNOWN,
                name="GEMINI",
                source_path=path,
                description="Gemini instruction document",
            )
        return None


class FakeMapper:
    def map(self, ir: ArtifactIR, target: Platform) -> ArtifactIR:
        ir.confidence = Confidence.LOW
        ir.metadata["mapped_by"] = "fake_plugin"
        return ir


class TestDetectorPlugin:
    def test_plugin_detects_custom_artifact(self, tmp_path):
        register_detector("gemini", FakeDetector())
        f = tmp_path / "GEMINI.md"
        f.write_text("# Gemini\n")
        ir = detect_artifact(f)
        assert ir.kind == ArtifactKind.INSTRUCTION_DOC
        assert ir.name == "GEMINI"

    def test_builtin_detection_still_works_as_fallback(self, tmp_path):
        register_detector("gemini", FakeDetector())
        f = tmp_path / "CLAUDE.md"
        f.write_text("# Project\n")
        ir = detect_artifact(f)
        assert ir.source_platform == Platform.CLAUDE

    def test_without_plugins_unknown_stays_unknown(self, tmp_path):
        f = tmp_path / "GEMINI.md"
        f.write_text("# Gemini\n")
        ir = detect_artifact(f)
        assert ir.kind == ArtifactKind.UNKNOWN


class TestMapperPlugin:
    def test_plugin_overrides_builtin_mapping(self):
        register_mapper(Platform.CLAUDE, Platform.CODEX, FakeMapper())
        ir = ArtifactIR(
            kind=ArtifactKind.INSTRUCTION_DOC,
            source_platform=Platform.CLAUDE,
            name="CLAUDE",
        )
        mapped = map_artifact(ir, Platform.CODEX)
        assert mapped.metadata["mapped_by"] == "fake_plugin"
        assert mapped.target_platform == Platform.CODEX
        # Original IR is not mutated
        assert "mapped_by" not in ir.metadata

    def test_plugin_only_applies_to_registered_direction(self):
        register_mapper(Platform.CLAUDE, Platform.CODEX, FakeMapper())
        ir = ArtifactIR(
            kind=ArtifactKind.INSTRUCTION_DOC,
            source_platform=Platform.CODEX,
            name="AGENTS",
        )
        mapped = map_artifact(ir, Platform.CLAUDE)
        assert "mapped_by" not in mapped.metadata
        assert mapped.name == "CLAUDE"  # built-in mapping ran
