"""Tests for the reporter layer."""

import json

from agent_migrate.ir import Platform
from agent_migrate.pipeline import convert_path
from agent_migrate.reporter.report import (
    ConversionReport,
    generate_json_report,
    generate_markdown_report,
)


class TestReports:
    def test_json_report_structure(self, claude_md, tmp_output):
        _, report = convert_path(claude_md, Platform.CLAUDE, Platform.CODEX, output_dir=tmp_output)
        json_str = generate_json_report(report)
        data = json.loads(json_str)
        assert "summary" in data
        assert "converted" in data
        assert data["source_platform"] == "claude"
        assert data["target_platform"] == "codex"
        assert data["summary"]["items_converted"] > 0

    def test_markdown_report_readable(self, claude_md, tmp_output):
        _, report = convert_path(claude_md, Platform.CLAUDE, Platform.CODEX, output_dir=tmp_output)
        md = generate_markdown_report(report)
        assert "# Migration Report" in md
        assert "Summary" in md
        assert "claude" in md.lower()
        assert "codex" in md.lower()

    def test_report_confidence_summary(self, claude_fixtures, tmp_output):
        _, report = convert_path(
            claude_fixtures, Platform.CLAUDE, Platform.CODEX, output_dir=tmp_output,
        )
        total = sum(report.confidence_summary.values())
        assert total == report.items_converted

    def test_report_tracks_warnings(self, claude_hook, tmp_output):
        _, report = convert_path(claude_hook, Platform.CLAUDE, Platform.CODEX, output_dir=tmp_output)
        assert len(report.warnings) > 0

    def test_empty_report(self):
        report = ConversionReport(source_platform="claude", target_platform="codex")
        json_str = generate_json_report(report)
        data = json.loads(json_str)
        assert data["summary"]["items_converted"] == 0
