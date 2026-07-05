"""Regression tests for detection, parsing, and rendering fixes."""

from pathlib import Path

from agent_migrate.detector import detect_artifact, detect_directory
from agent_migrate.detector.detect import _extract_frontmatter
from agent_migrate.ir import ArtifactIR, ArtifactKind, Platform, SemanticIntent
from agent_migrate.parser import parse_artifact
from agent_migrate.renderer.render import render_artifact


def _make_claude_project(tmp_path: Path) -> Path:
    """A realistic Claude project layout with artifacts under .claude/."""
    root = tmp_path / "project"
    dot_claude = root / ".claude"
    (dot_claude / "commands").mkdir(parents=True)
    (dot_claude / "commands" / "greet.md").write_text(
        "---\ndescription: Greet the user\n---\nSay hello politely."
    )
    (dot_claude / "settings.json").write_text('{"model": "claude-sonnet-5"}')
    (root / "CLAUDE.md").write_text("# Project\n\n## Build\n\nRun `make build`.")
    return root


class TestDotClaudeDetection:
    def test_detects_artifacts_inside_dot_claude(self, tmp_path):
        root = _make_claude_project(tmp_path)
        artifacts = detect_directory(root)
        kinds = {ir.kind for ir in artifacts}
        assert ArtifactKind.COMMAND in kinds
        assert ArtifactKind.CONFIG in kinds
        assert ArtifactKind.INSTRUCTION_DOC in kinds

    def test_settings_json_detected_as_claude_config(self, tmp_path):
        root = _make_claude_project(tmp_path)
        settings = root / ".claude" / "settings.json"
        ir = detect_artifact(settings)
        assert ir.kind == ArtifactKind.CONFIG
        assert ir.source_platform == Platform.CLAUDE
        assert ir.intent == SemanticIntent.RUNTIME_CONFIG


class TestHooksDirRecursion:
    def test_hook_script_in_hooks_dir_is_detected(self, claude_fixtures):
        artifacts = detect_directory(claude_fixtures)
        kinds = {ir.kind for ir in artifacts}
        assert ArtifactKind.HOOK in kinds


class TestContainerDirsNotEmitted:
    def test_agents_dir_yields_only_agent_tomls(self, codex_fixtures):
        artifacts = detect_directory(codex_fixtures)
        subagents = [ir for ir in artifacts if ir.kind == ArtifactKind.SUBAGENT]
        # Only real TOML files, not the "agents" container directory itself
        assert subagents
        assert all(ir.source_path.endswith(".toml") for ir in subagents)

    def test_codex_dir_yields_only_real_configs(self, codex_fixtures):
        artifacts = detect_directory(codex_fixtures)
        configs = [ir for ir in artifacts if ir.kind == ArtifactKind.CONFIG]
        assert all(not ir.source_path.endswith(".codex") for ir in configs)


class TestFrontmatter:
    def test_non_mapping_frontmatter_returns_empty_dict(self):
        content = "---\n- a\n- b\n---\n\nBody"
        assert _extract_frontmatter(content) == {}


class TestAllowedTools:
    def test_comma_separated_allowed_tools_are_split(self, tmp_path):
        cmd = tmp_path / "commands" / "lint.md"
        cmd.parent.mkdir()
        cmd.write_text("---\nallowed-tools: Read, Bash, Grep\n---\nFix lint errors.")
        ir = parse_artifact(detect_artifact(cmd))
        assert ir.required_tools == ["Read", "Bash", "Grep"]

    def test_allowed_tools_rendered_as_comma_separated_string(self):
        ir = ArtifactIR(
            kind=ArtifactKind.COMMAND,
            name="lint",
            target_platform=Platform.CLAUDE,
            required_tools=["Read", "Bash"],
            instructions="Fix lint errors.",
        )
        result = render_artifact(ir)
        content = result.files[0].content
        assert "allowed-tools: Read, Bash" in content
        assert "['Read'" not in content


class TestMetadataLeak:
    def test_codex_target_not_leaked_into_config_toml(self):
        ir = ArtifactIR(
            kind=ArtifactKind.CONFIG,
            name="settings",
            target_platform=Platform.CODEX,
            metadata={"codex_target": "config_toml", "model": "gpt-5"},
        )
        result = render_artifact(ir)
        content = result.files[0].content
        assert "codex_target" not in content
        assert "model" in content

    def test_claude_target_not_leaked_into_settings_json(self):
        ir = ArtifactIR(
            kind=ArtifactKind.CONFIG,
            name="config",
            target_platform=Platform.CLAUDE,
            metadata={"claude_target": "settings_json", "sandbox": True},
        )
        result = render_artifact(ir)
        content = result.files[0].content
        assert "claude_target" not in content
        assert "sandbox" in content


class TestRuleConfigRendering:
    def test_rule_mapped_to_config_renders_fragment_not_config_toml(self):
        ir = ArtifactIR(
            kind=ArtifactKind.CONFIG,  # mapper switches RULE -> CONFIG
            name="timeouts",
            target_platform=Platform.CODEX,
            constraints=["set timeout to 30s"],
            metadata={"codex_target": "config"},
        )
        result = render_artifact(ir)
        assert result.files[0].path.startswith("_fragments/")


class TestConstraintDuplication:
    def test_constraints_from_sections_not_duplicated(self, tmp_path):
        from agent_migrate.mapper import map_artifact

        doc = tmp_path / "CLAUDE.md"
        doc.write_text(
            "# Project\n\n## Rules\n\n- Never commit secrets\n- Always run tests\n"
        )
        ir = parse_artifact(detect_artifact(doc))
        mapped = map_artifact(ir, Platform.CODEX)
        assert mapped.constraints  # the Rules section must yield constraints
        result = render_artifact(mapped)
        content = result.files[0].content
        for constraint in mapped.constraints:
            # Each constraint appears exactly once in the output
            assert content.count(constraint) == 1, constraint
