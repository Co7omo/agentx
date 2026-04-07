"""Tests for the renderer layer."""

from pathlib import Path

from agent_migrate.classifier import classify_artifact
from agent_migrate.detector import detect_artifact
from agent_migrate.ir import Platform
from agent_migrate.mapper import map_artifact
from agent_migrate.parser import parse_artifact
from agent_migrate.renderer import render_artifact


def _render_pipeline(path, target, output_dir=None):
    ir = detect_artifact(path)
    ir = parse_artifact(ir)
    ir = classify_artifact(ir)
    mapped = map_artifact(ir, target)
    return render_artifact(mapped, output_dir)


class TestRenderToCodex:
    def test_render_agents_md(self, claude_md, tmp_output):
        result = _render_pipeline(claude_md, Platform.CODEX, tmp_output)
        assert len(result.files) > 0
        agents_file = next(f for f in result.files if "AGENTS.md" in f.path)
        assert "AGENTS.md" in agents_file.path
        assert (tmp_output / "AGENTS.md").exists()
        content = (tmp_output / "AGENTS.md").read_text()
        assert "Build" in content or "Code Style" in content

    def test_render_skill(self, claude_skill_dir, tmp_output):
        result = _render_pipeline(claude_skill_dir, Platform.CODEX, tmp_output)
        assert len(result.files) > 0
        assert any("skills/" in f.path for f in result.files)

    def test_render_command_as_prompt(self, claude_prompt_command, tmp_output):
        result = _render_pipeline(claude_prompt_command, Platform.CODEX, tmp_output)
        assert len(result.files) > 0

    def test_render_hook_scaffold(self, claude_hook, tmp_output):
        result = _render_pipeline(claude_hook, Platform.CODEX, tmp_output)
        assert len(result.files) > 0
        hook_file = result.files[0]
        assert "scaffold" in hook_file.description.lower() or "hook" in hook_file.path

    def test_render_codex_agent_toml(self, codex_agent_toml, tmp_output):
        """Codex agent -> Claude -> render as skill."""
        result = _render_pipeline(codex_agent_toml, Platform.CLAUDE, tmp_output)
        assert len(result.files) > 0


class TestRenderToClaude:
    def test_render_claude_md(self, agents_md, tmp_output):
        result = _render_pipeline(agents_md, Platform.CLAUDE, tmp_output)
        assert len(result.files) > 0
        claude_file = next(f for f in result.files if "CLAUDE.md" in f.path)
        assert (tmp_output / "CLAUDE.md").exists()

    def test_render_subagent_as_skill(self, codex_agent_toml, tmp_output):
        result = _render_pipeline(codex_agent_toml, Platform.CLAUDE, tmp_output)
        assert len(result.files) > 0
        assert any("skills/" in f.path or "SKILL.md" in f.path for f in result.files)


class TestDryRun:
    def test_dry_run_does_not_write(self, claude_md, tmp_output):
        """Render without output_dir should not write files."""
        result = _render_pipeline(claude_md, Platform.CODEX, output_dir=None)
        assert len(result.files) > 0
        # Nothing should be written to disk
        assert not list(tmp_output.iterdir())
