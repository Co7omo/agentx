"""Integration tests for the full pipeline."""

from pathlib import Path

from agent_migrate.ir import Confidence, Platform
from agent_migrate.pipeline import convert_path, inspect_path, plan_migration


class TestInspect:
    def test_inspect_claude_md(self, claude_md):
        artifacts = inspect_path(claude_md)
        assert len(artifacts) == 1
        assert artifacts[0].name == "CLAUDE"

    def test_inspect_directory(self, claude_fixtures):
        artifacts = inspect_path(claude_fixtures)
        assert len(artifacts) >= 3  # CLAUDE.md + skills + commands + rules + hooks

    def test_inspect_codex_project(self, codex_fixtures):
        artifacts = inspect_path(codex_fixtures)
        assert len(artifacts) >= 1


class TestConvert:
    def test_convert_claude_to_codex(self, claude_md, tmp_output):
        results, report = convert_path(
            claude_md, Platform.CLAUDE, Platform.CODEX, output_dir=tmp_output,
        )
        assert report.items_converted > 0
        assert report.items_detected > 0
        assert (tmp_output / "AGENTS.md").exists()

    def test_convert_codex_to_claude(self, agents_md, tmp_output):
        results, report = convert_path(
            agents_md, Platform.CODEX, Platform.CLAUDE, output_dir=tmp_output,
        )
        assert report.items_converted > 0
        assert (tmp_output / "CLAUDE.md").exists()

    def test_convert_dry_run(self, claude_md, tmp_output):
        results, report = convert_path(
            claude_md, Platform.CLAUDE, Platform.CODEX,
            output_dir=tmp_output, dry_run=True,
        )
        assert report.items_converted > 0
        # Nothing written in dry-run
        assert not (tmp_output / "AGENTS.md").exists()

    def test_convert_strict_mode(self, claude_hook, tmp_output):
        results, report = convert_path(
            claude_hook, Platform.CLAUDE, Platform.CODEX,
            output_dir=tmp_output, strict=True,
        )
        # Hooks often have low confidence, may be skipped in strict mode
        assert report.items_detected > 0

    def test_convert_directory(self, claude_fixtures, tmp_output):
        results, report = convert_path(
            claude_fixtures, Platform.CLAUDE, Platform.CODEX, output_dir=tmp_output,
        )
        assert report.items_detected >= 3
        assert report.items_converted >= 1


class TestRoundTrip:
    def test_claude_codex_roundtrip_loss(self, claude_md, tmp_path):
        """Convert CLAUDE.md -> AGENTS.md -> CLAUDE.md and verify loss report."""
        # Forward
        out1 = tmp_path / "step1"
        out1.mkdir()
        results1, report1 = convert_path(
            claude_md, Platform.CLAUDE, Platform.CODEX, output_dir=out1,
        )
        assert (out1 / "AGENTS.md").exists()

        # Reverse
        out2 = tmp_path / "step2"
        out2.mkdir()
        results2, report2 = convert_path(
            out1 / "AGENTS.md", Platform.CODEX, Platform.CLAUDE, output_dir=out2,
        )
        assert (out2 / "CLAUDE.md").exists()

        # Read both and verify content is structurally similar (not identical)
        original = claude_md.read_text()
        roundtripped = (out2 / "CLAUDE.md").read_text()
        # Both should have section about Build
        assert "Build" in original
        assert "Build" in roundtripped or "Setup" in roundtripped


class TestPlan:
    def test_plan_claude_to_codex(self, claude_fixtures):
        report = plan_migration(claude_fixtures, Platform.CLAUDE, Platform.CODEX)
        assert report.items_detected >= 3
        assert report.source_platform == "claude"
        assert report.target_platform == "codex"
        assert len(report.converted) > 0
