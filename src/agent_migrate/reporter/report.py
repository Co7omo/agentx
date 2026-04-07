"""Reporter layer.

Generates structured reports (JSON + Markdown) documenting what was
converted, what was lost, and what requires manual follow-up.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from agent_migrate.ir import ArtifactIR, Confidence, Platform, WarningLevel
from agent_migrate.renderer.render import RenderResult


@dataclass
class ConversionItem:
    source_path: str
    kind: str
    target_paths: list[str]
    confidence: str
    warnings: list[dict]
    manual_todos: list[dict]


@dataclass
class ConversionReport:
    source_platform: str = ""
    target_platform: str = ""
    items_detected: int = 0
    items_converted: int = 0
    items_skipped: int = 0
    converted: list[ConversionItem] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    incompatibilities: list[dict] = field(default_factory=list)
    confidence_summary: dict[str, int] = field(default_factory=lambda: {"high": 0, "medium": 0, "low": 0})
    manual_actions: list[dict] = field(default_factory=list)

    def add_result(self, ir: ArtifactIR, render_result: RenderResult) -> None:
        target_paths = [f.path for f in render_result.files]
        warnings = [
            {"level": w.level.value, "code": w.code, "message": w.message, "suggestion": w.suggestion}
            for w in ir.warnings
        ]
        todos = [
            {"priority": t.priority, "description": t.description, "reason": t.reason}
            for t in ir.manual_todos
        ]

        self.converted.append(ConversionItem(
            source_path=ir.source_path,
            kind=ir.kind.value,
            target_paths=target_paths,
            confidence=ir.confidence.value,
            warnings=warnings,
            manual_todos=todos,
        ))
        self.items_converted += 1
        self.confidence_summary[ir.confidence.value] = self.confidence_summary.get(ir.confidence.value, 0) + 1

        for w in warnings:
            self.warnings.append({**w, "source": ir.source_path})
        for t in todos:
            self.manual_actions.append({**t, "source": ir.source_path})

        # Track incompatibilities
        error_warnings = [w for w in ir.warnings if w.level == WarningLevel.ERROR]
        for w in error_warnings:
            self.incompatibilities.append({
                "source": ir.source_path,
                "message": w.message,
                "suggestion": w.suggestion,
            })

    def add_skipped(self, path: str, reason: str) -> None:
        self.skipped.append({"path": path, "reason": reason})
        self.items_skipped += 1


def generate_json_report(report: ConversionReport) -> str:
    """Generate a JSON report."""
    data = {
        "source_platform": report.source_platform,
        "target_platform": report.target_platform,
        "summary": {
            "items_detected": report.items_detected,
            "items_converted": report.items_converted,
            "items_skipped": report.items_skipped,
            "confidence": report.confidence_summary,
        },
        "converted": [
            {
                "source": c.source_path,
                "kind": c.kind,
                "targets": c.target_paths,
                "confidence": c.confidence,
                "warnings": c.warnings,
                "manual_todos": c.manual_todos,
            }
            for c in report.converted
        ],
        "skipped": report.skipped,
        "warnings": report.warnings,
        "incompatibilities": report.incompatibilities,
        "manual_actions": report.manual_actions,
    }
    return json.dumps(data, indent=2)


def generate_markdown_report(report: ConversionReport) -> str:
    """Generate a human-readable Markdown report."""
    lines: list[str] = []

    lines.append("# Migration Report")
    lines.append("")
    lines.append(f"**Source platform:** {report.source_platform}")
    lines.append(f"**Target platform:** {report.target_platform}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Detected | {report.items_detected} |")
    lines.append(f"| Converted | {report.items_converted} |")
    lines.append(f"| Skipped | {report.items_skipped} |")
    lines.append("")

    # Confidence breakdown
    lines.append("### Confidence Breakdown")
    lines.append("")
    for level, count in report.confidence_summary.items():
        emoji = {"high": "OK", "medium": "~~", "low": "!!"}
        lines.append(f"- **{level}**: {count} [{emoji.get(level, '??')}]")
    lines.append("")

    # Converted items
    if report.converted:
        lines.append("## Converted Items")
        lines.append("")
        for item in report.converted:
            lines.append(f"### `{item.source_path}`")
            lines.append(f"- **Kind:** {item.kind}")
            lines.append(f"- **Confidence:** {item.confidence}")
            lines.append(f"- **Target files:** {', '.join(f'`{t}`' for t in item.target_paths)}")
            if item.warnings:
                lines.append("- **Warnings:**")
                for w in item.warnings:
                    lines.append(f"  - [{w['level']}] {w['message']}")
                    if w.get("suggestion"):
                        lines.append(f"    - *Suggestion:* {w['suggestion']}")
            if item.manual_todos:
                lines.append("- **Manual TODOs:**")
                for t in item.manual_todos:
                    lines.append(f"  - [{t['priority']}] {t['description']}")
            lines.append("")

    # Skipped items
    if report.skipped:
        lines.append("## Skipped Items")
        lines.append("")
        for s in report.skipped:
            lines.append(f"- `{s['path']}`: {s['reason']}")
        lines.append("")

    # Incompatibilities
    if report.incompatibilities:
        lines.append("## Incompatibilities")
        lines.append("")
        for inc in report.incompatibilities:
            lines.append(f"- `{inc['source']}`: {inc['message']}")
            if inc.get("suggestion"):
                lines.append(f"  - *Suggestion:* {inc['suggestion']}")
        lines.append("")

    # Next steps
    if report.manual_actions:
        lines.append("## Next Steps")
        lines.append("")
        lines.append("The following items require manual review or implementation:")
        lines.append("")
        for i, action in enumerate(report.manual_actions, 1):
            lines.append(f"{i}. **[{action['priority']}]** {action['description']}")
            if action.get("reason"):
                lines.append(f"   - Reason: {action['reason']}")
            if action.get("source"):
                lines.append(f"   - Source: `{action['source']}`")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by agentx*")

    return "\n".join(lines)
