"""Tests for the mapper layer."""

from agent_migrate.classifier import classify_artifact
from agent_migrate.detector import detect_artifact
from agent_migrate.ir import ArtifactKind, Confidence, Platform
from agent_migrate.mapper import map_artifact
from agent_migrate.parser import parse_artifact


def _full_pipeline(path, target):
    """Detect -> parse -> classify -> map."""
    ir = detect_artifact(path)
    ir = parse_artifact(ir)
    ir = classify_artifact(ir)
    return map_artifact(ir, target)


class TestMapToCodex:
    def test_claude_md_to_agents_md(self, claude_md):
        ir = _full_pipeline(claude_md, Platform.CODEX)
        assert ir.target_platform == Platform.CODEX
        assert ir.name == "AGENTS"
        assert ir.confidence == Confidence.HIGH

    def test_skill_to_codex(self, claude_skill_dir):
        ir = _full_pipeline(claude_skill_dir, Platform.CODEX)
        assert ir.target_platform == Platform.CODEX
        assert ir.confidence in (Confidence.HIGH, Confidence.MEDIUM)

    def test_command_to_codex_prompt(self, claude_prompt_command):
        ir = _full_pipeline(claude_prompt_command, Platform.CODEX)
        assert ir.target_platform == Platform.CODEX
        assert ir.metadata.get("codex_target") in ("custom_prompt", "skill")

    def test_hook_to_codex_scaffold(self, claude_hook):
        ir = _full_pipeline(claude_hook, Platform.CODEX)
        assert ir.target_platform == Platform.CODEX
        assert len(ir.warnings) > 0  # Hooks always generate warnings

    def test_rule_to_codex(self, claude_rule):
        ir = _full_pipeline(claude_rule, Platform.CODEX)
        assert ir.target_platform == Platform.CODEX


class TestMapToClaude:
    def test_agents_md_to_claude_md(self, agents_md):
        ir = _full_pipeline(agents_md, Platform.CLAUDE)
        assert ir.target_platform == Platform.CLAUDE
        assert ir.name == "CLAUDE"
        assert ir.confidence == Confidence.HIGH

    def test_codex_agent_to_claude(self, codex_agent_toml):
        ir = _full_pipeline(codex_agent_toml, Platform.CLAUDE)
        assert ir.target_platform == Platform.CLAUDE
        assert len(ir.warnings) > 0  # Subagent mapping generates warnings
        assert len(ir.manual_todos) > 0

    def test_codex_config_to_claude(self, codex_config_toml):
        ir = _full_pipeline(codex_config_toml, Platform.CLAUDE)
        assert ir.target_platform == Platform.CLAUDE
        assert ir.confidence in (Confidence.HIGH, Confidence.MEDIUM)


class TestToolAdaptation:
    def test_skill_instructions_and_tools_adapted_for_codex(self, tmp_path):
        skill_dir = tmp_path / "skills" / "helper"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: helper\ndescription: Helper skill\n---\n"
            "Use `Read` to open the file, then run `Bash` commands.\n"
        )
        ir = _full_pipeline(skill_dir, Platform.CODEX)
        assert "`file_read`" in ir.instructions
        assert "`shell`" in ir.instructions
        assert "`Read`" not in ir.instructions
        assert "Read" not in ir.required_tools
        assert "file_read" in ir.required_tools
        assert "Read->file_read" in ir.metadata["adapted_tools"]

    def test_command_instructions_adapted_for_codex(self, tmp_path):
        cmd = tmp_path / "commands" / "open.md"
        cmd.parent.mkdir()
        cmd.write_text("---\nallowed-tools: Read, Grep\n---\nUse `Grep` to find matches.")
        ir = _full_pipeline(cmd, Platform.CODEX)
        assert "`search`" in ir.instructions
        assert ir.required_tools == ["file_read", "search"]

    def test_codex_agent_tools_adapted_for_claude(self, codex_agent_toml):
        ir = _full_pipeline(codex_agent_toml, Platform.CLAUDE)
        codex_names = {"file_read", "file_write", "shell", "search"}
        assert not codex_names & set(ir.required_tools)


class TestSamePlatformWarning:
    def test_same_platform_warning(self, claude_md):
        ir = detect_artifact(claude_md)
        ir = parse_artifact(ir)
        ir = classify_artifact(ir)
        mapped = map_artifact(ir, Platform.CLAUDE)
        assert any("same" in w.message.lower() for w in mapped.warnings)
