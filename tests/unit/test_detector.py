"""Tests for the detector layer."""

from pathlib import Path

from agent_migrate.detector import detect_artifact, detect_directory
from agent_migrate.ir import ArtifactKind, Platform


class TestDetectArtifact:
    def test_detect_claude_md(self, claude_md):
        ir = detect_artifact(claude_md)
        assert ir.kind == ArtifactKind.INSTRUCTION_DOC
        assert ir.source_platform == Platform.CLAUDE
        assert ir.name == "CLAUDE"

    def test_detect_agents_md(self, agents_md):
        ir = detect_artifact(agents_md)
        assert ir.kind == ArtifactKind.INSTRUCTION_DOC
        assert ir.source_platform == Platform.CODEX

    def test_detect_skill_directory(self, claude_skill_dir):
        ir = detect_artifact(claude_skill_dir)
        assert ir.kind == ArtifactKind.SKILL
        assert ir.source_platform == Platform.CLAUDE

    def test_detect_codex_agent_toml(self, codex_agent_toml):
        ir = detect_artifact(codex_agent_toml)
        assert ir.kind == ArtifactKind.SUBAGENT
        assert ir.source_platform == Platform.CODEX

    def test_detect_codex_config(self, codex_config_toml):
        ir = detect_artifact(codex_config_toml)
        assert ir.kind == ArtifactKind.CONFIG
        assert ir.source_platform == Platform.CODEX

    def test_detect_command(self, claude_command):
        ir = detect_artifact(claude_command)
        assert ir.kind == ArtifactKind.COMMAND

    def test_detect_rule(self, claude_rule):
        ir = detect_artifact(claude_rule)
        assert ir.kind == ArtifactKind.RULE

    def test_detect_hook(self, claude_hook):
        ir = detect_artifact(claude_hook)
        assert ir.kind == ArtifactKind.HOOK

    def test_detect_unknown_file(self, tmp_path):
        f = tmp_path / "random.txt"
        f.write_text("just some random text")
        ir = detect_artifact(f)
        assert ir.kind == ArtifactKind.UNKNOWN


class TestDetectDirectory:
    def test_detect_claude_project(self, claude_fixtures):
        artifacts = detect_directory(claude_fixtures)
        kinds = {ir.kind for ir in artifacts}
        assert ArtifactKind.INSTRUCTION_DOC in kinds
        assert ArtifactKind.SKILL in kinds
        assert len(artifacts) >= 3

    def test_detect_codex_project(self, codex_fixtures):
        artifacts = detect_directory(codex_fixtures)
        kinds = {ir.kind for ir in artifacts}
        assert ArtifactKind.INSTRUCTION_DOC in kinds
        assert len(artifacts) >= 1
