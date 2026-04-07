"""Tests for the parser layer."""

from agent_migrate.detector import detect_artifact
from agent_migrate.ir import ArtifactKind, SemanticIntent
from agent_migrate.parser import parse_artifact


class TestParseInstructionDoc:
    def test_parse_claude_md_sections(self, claude_md):
        ir = detect_artifact(claude_md)
        ir = parse_artifact(ir)
        assert len(ir.sections) > 0
        titles = [s.title for s in ir.sections]
        assert "Build & Test" in titles
        assert "Code Style" in titles

    def test_parse_claude_md_intents(self, claude_md):
        ir = detect_artifact(claude_md)
        ir = parse_artifact(ir)
        assert SemanticIntent.BUILD_TEST_INSTRUCTIONS in ir.intents

    def test_parse_agents_md(self, agents_md):
        ir = detect_artifact(agents_md)
        ir = parse_artifact(ir)
        assert len(ir.sections) > 0


class TestParseSkill:
    def test_parse_skill_frontmatter(self, claude_skill_dir):
        ir = detect_artifact(claude_skill_dir)
        ir = parse_artifact(ir)
        assert ir.name == "review-pr"
        assert "review" in ir.description.lower() or "review" in ir.instructions.lower()

    def test_parse_skill_tools(self, claude_skill_dir):
        ir = detect_artifact(claude_skill_dir)
        ir = parse_artifact(ir)
        assert "Read" in ir.required_tools


class TestParseCommand:
    def test_parse_workflow_command(self, claude_command):
        ir = detect_artifact(claude_command)
        ir = parse_artifact(ir)
        assert ir.kind == ArtifactKind.COMMAND
        assert ir.instructions  # Should have parsed instructions

    def test_parse_prompt_command(self, claude_prompt_command):
        ir = detect_artifact(claude_prompt_command)
        ir = parse_artifact(ir)
        assert ir.instructions


class TestParseSubagent:
    def test_parse_codex_agent_toml(self, codex_agent_toml):
        ir = detect_artifact(codex_agent_toml)
        ir = parse_artifact(ir)
        assert ir.name == "security-reviewer"
        assert "security" in ir.instructions.lower()
        assert len(ir.required_tools) > 0

    def test_parse_codex_agent_triggers(self, codex_agent_toml):
        ir = detect_artifact(codex_agent_toml)
        ir = parse_artifact(ir)
        assert len(ir.triggers) > 0
        assert ir.triggers[0].event == "on_pr"


class TestParseHook:
    def test_parse_hook_trigger(self, claude_hook):
        ir = detect_artifact(claude_hook)
        ir = parse_artifact(ir)
        assert len(ir.triggers) > 0
        assert "pre-commit" in ir.triggers[0].event

    def test_parse_hook_warnings(self, claude_hook):
        ir = detect_artifact(claude_hook)
        ir = parse_artifact(ir)
        assert len(ir.warnings) > 0


class TestParseConfig:
    def test_parse_codex_config_toml(self, codex_config_toml):
        ir = detect_artifact(codex_config_toml)
        ir = parse_artifact(ir)
        assert "project" in ir.metadata
        assert ir.metadata["project"]["name"] == "data-pipeline"
