"""CLI integration tests via typer's test runner."""

from typer.testing import CliRunner

from agent_migrate.cli.main import app

runner = CliRunner()


class TestCLI:
    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_inspect_claude_md(self, claude_md):
        result = runner.invoke(app, ["inspect", str(claude_md)])
        assert result.exit_code == 0
        assert "instruction_doc" in result.output
        assert "claude" in result.output

    def test_inspect_json(self, claude_md):
        result = runner.invoke(app, ["inspect", str(claude_md), "--json"])
        assert result.exit_code == 0
        assert '"kind"' in result.output

    def test_convert_dry_run(self, claude_md):
        result = runner.invoke(app, [
            "convert", "--from", "claude", "--to", "codex",
            str(claude_md), "--dry-run",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_convert_with_output(self, claude_md, tmp_output):
        result = runner.invoke(app, [
            "convert", "--from", "claude", "--to", "codex",
            str(claude_md), "--out", str(tmp_output),
        ])
        assert result.exit_code == 0
        assert (tmp_output / "AGENTS.md").exists()

    def test_plan(self, claude_fixtures):
        result = runner.invoke(app, [
            "plan", "--from", "claude", "--to", "codex",
            str(claude_fixtures),
        ])
        assert result.exit_code == 0
        assert "Migration Plan" in result.output

    def test_diff_explain(self, claude_md):
        result = runner.invoke(app, [
            "diff-explain", "--from", "claude", "--to", "codex",
            str(claude_md),
        ])
        assert result.exit_code == 0
        assert "instruction_doc" in result.output

    def test_explain_ir(self, claude_md):
        result = runner.invoke(app, ["explain-ir", str(claude_md)])
        assert result.exit_code == 0
        assert "CLAUDE" in result.output

    def test_validate_output(self, claude_md, tmp_output):
        # First generate output
        runner.invoke(app, [
            "convert", "--from", "claude", "--to", "codex",
            str(claude_md), "--out", str(tmp_output),
        ])
        result = runner.invoke(app, [
            "validate", "--target", "codex", str(tmp_output),
        ])
        assert result.exit_code == 0

    def test_invalid_path(self):
        result = runner.invoke(app, ["inspect", "/nonexistent/path"])
        assert result.exit_code == 1

    def test_convert_json_report(self, claude_md):
        result = runner.invoke(app, [
            "convert", "--from", "claude", "--to", "codex",
            str(claude_md), "--dry-run", "--json",
        ])
        assert result.exit_code == 0
        assert '"summary"' in result.output
