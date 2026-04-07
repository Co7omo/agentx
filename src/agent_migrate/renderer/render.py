"""Renderer layer.

Generates idiomatic target files from mapped IR. Produces well-formatted
markdown, valid TOML, correct directory structures, and placeholder
comments where appropriate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agent_migrate.ir import (
    ArtifactIR,
    ArtifactKind,
    Platform,
    SemanticIntent,
)


@dataclass
class RenderedOutput:
    """A single rendered file."""

    path: str  # relative path for the output file
    content: str
    description: str = ""


@dataclass
class RenderResult:
    """All outputs from rendering one IR."""

    files: list[RenderedOutput] = field(default_factory=list)
    ir: ArtifactIR | None = None


def render_artifact(ir: ArtifactIR, output_dir: Path | None = None) -> RenderResult:
    """Render a mapped IR into target files."""
    if ir.target_platform == Platform.CODEX:
        result = _render_for_codex(ir)
    elif ir.target_platform == Platform.CLAUDE:
        result = _render_for_claude(ir)
    else:
        result = RenderResult(ir=ir)
        result.files.append(RenderedOutput(
            path=f"{ir.name}.md",
            content=f"# {ir.name}\n\n<!-- Could not determine target platform -->\n\n{ir.instructions or ir.raw_content}",
            description="Fallback output (unknown target platform)",
        ))

    result.ir = ir

    if output_dir:
        _write_outputs(result, output_dir)

    return result


def _render_for_codex(ir: ArtifactIR) -> RenderResult:
    """Render IR as Codex artifacts."""
    result = RenderResult()
    target = ir.metadata.get("codex_target", "")
    kind = ir.kind

    if kind == ArtifactKind.INSTRUCTION_DOC:
        result.files.append(_render_agents_md(ir))
    elif kind == ArtifactKind.SKILL:
        result.files.append(_render_codex_skill(ir))
    elif kind == ArtifactKind.COMMAND and target == "skill":
        result.files.append(_render_codex_skill(ir))
    elif kind == ArtifactKind.COMMAND:
        result.files.append(_render_codex_custom_prompt(ir))
    elif kind == ArtifactKind.RULE and target == "agents_md_section":
        result.files.append(_render_codex_rule_as_section(ir))
    elif kind == ArtifactKind.RULE and target == "config":
        result.files.append(_render_codex_config_fragment(ir))
    elif kind in (ArtifactKind.SUBAGENT,) or (kind == ArtifactKind.RULE and target in ("agent_toml", "")):
        result.files.append(_render_codex_agent_toml(ir))
    elif kind == ArtifactKind.HOOK:
        result.files.append(_render_codex_hook_scaffold(ir))
    elif kind == ArtifactKind.CONFIG:
        result.files.append(_render_codex_config(ir))
    else:
        result.files.append(RenderedOutput(
            path=f"{_safe_filename(ir.name)}.md",
            content=_fallback_markdown(ir, "Codex"),
            description=f"Fallback rendering for {ir.kind}",
        ))

    return result


def _render_for_claude(ir: ArtifactIR) -> RenderResult:
    """Render IR as Claude artifacts."""
    result = RenderResult()
    target = ir.metadata.get("claude_target", "")
    kind = ir.kind

    if kind == ArtifactKind.INSTRUCTION_DOC:
        result.files.append(_render_claude_md(ir))
    elif kind in (ArtifactKind.SKILL, ArtifactKind.SUBAGENT) and target == "subagent_skill":
        result.files.extend(_render_claude_skill_dir(ir))
    elif kind == ArtifactKind.SKILL:
        result.files.extend(_render_claude_skill_dir(ir))
    elif kind == ArtifactKind.COMMAND:
        result.files.append(_render_claude_command(ir))
    elif kind == ArtifactKind.RULE:
        result.files.append(_render_claude_rule(ir))
    elif kind == ArtifactKind.HOOK:
        result.files.append(_render_claude_hook_config(ir))
    elif kind == ArtifactKind.CONFIG:
        result.files.append(_render_claude_settings(ir))
    else:
        result.files.append(RenderedOutput(
            path=f"{_safe_filename(ir.name)}.md",
            content=_fallback_markdown(ir, "Claude"),
            description=f"Fallback rendering for {ir.kind}",
        ))

    return result


# --- Codex renderers ---

def _render_agents_md(ir: ArtifactIR) -> RenderedOutput:
    """Render AGENTS.md from instruction doc IR."""
    lines = ["# AGENTS.md", ""]
    lines.append(f"<!-- Converted from {ir.source_platform.value} instruction document -->")
    lines.append(f"<!-- Source: {ir.source_path} -->")
    lines.append("")

    for section in ir.sections:
        if section.title:
            lines.append(f"## {section.title}")
            lines.append("")
        if section.content:
            lines.append(section.content)
            lines.append("")

    if ir.constraints:
        lines.append("## Constraints")
        lines.append("")
        for c in ir.constraints:
            lines.append(f"- {c}")
        lines.append("")

    _append_conversion_notes(lines, ir)

    return RenderedOutput(
        path="AGENTS.md",
        content="\n".join(lines),
        description="Codex agent instruction document",
    )


def _render_codex_skill(ir: ArtifactIR) -> RenderedOutput:
    """Render a Codex skill file."""
    lines = [f"# {ir.name}", ""]
    if ir.description:
        lines.append(f"> {ir.description}")
        lines.append("")

    lines.append(f"<!-- Converted from {ir.source_platform.value} -->")
    lines.append("")

    if ir.instructions:
        lines.append(ir.instructions)
    elif ir.raw_content:
        from agent_migrate.parser.parse import _strip_frontmatter
        lines.append(_strip_frontmatter(ir.raw_content))

    _append_conversion_notes(lines, ir)

    return RenderedOutput(
        path=f"skills/{_safe_filename(ir.name)}.md",
        content="\n".join(lines),
        description=f"Codex skill: {ir.name}",
    )


def _render_codex_custom_prompt(ir: ArtifactIR) -> RenderedOutput:
    """Render a Codex custom prompt."""
    content = ir.instructions or ir.raw_content
    lines = [f"# {ir.name}", ""]
    lines.append(f"<!-- Converted from {ir.source_platform.value} command -->")
    lines.append("")
    lines.append(content)

    _append_conversion_notes(lines, ir)

    return RenderedOutput(
        path=f"prompts/{_safe_filename(ir.name)}.md",
        content="\n".join(lines),
        description=f"Codex custom prompt: {ir.name}",
    )


def _render_codex_agent_toml(ir: ArtifactIR) -> RenderedOutput:
    """Render a Codex agent TOML file."""
    import tomli_w

    agent_data: dict = {
        "name": ir.name,
        "description": ir.description or f"Agent: {ir.name}",
    }
    if ir.instructions:
        agent_data["instructions"] = ir.instructions
    if ir.required_tools:
        agent_data["tools"] = ir.required_tools
    if ir.triggers:
        agent_data["triggers"] = [
            {"event": t.event, "pattern": t.pattern, "description": t.description}
            for t in ir.triggers
        ]

    content = f"# Converted from {ir.source_platform.value}\n"
    content += f"# Source: {ir.source_path}\n\n"
    content += tomli_w.dumps(agent_data)

    return RenderedOutput(
        path=f".codex/agents/{_safe_filename(ir.name)}.toml",
        content=content,
        description=f"Codex agent definition: {ir.name}",
    )


def _render_codex_rule_as_section(ir: ArtifactIR) -> RenderedOutput:
    """Render a rule as a section to be appended to AGENTS.md."""
    lines = [f"## {ir.name}", ""]
    lines.append(f"<!-- Converted from {ir.source_platform.value} rule -->")
    lines.append("")
    if ir.constraints:
        for c in ir.constraints:
            lines.append(f"- {c}")
    elif ir.instructions:
        lines.append(ir.instructions)

    return RenderedOutput(
        path=f"_fragments/rule_{_safe_filename(ir.name)}.md",
        content="\n".join(lines),
        description=f"AGENTS.md fragment for rule: {ir.name} (merge manually)",
    )


def _render_codex_config_fragment(ir: ArtifactIR) -> RenderedOutput:
    """Render a config fragment for .codex/config.toml."""
    import tomli_w

    # Best-effort: put constraints as config comments, metadata as values
    lines = [f"# Configuration from rule: {ir.name}"]
    lines.append(f"# Source: {ir.source_path}")
    lines.append("")

    data = {}
    for c in ir.constraints:
        key = _safe_filename(c[:40]).replace("-", "_")
        data[key] = True
    if data:
        lines.append(tomli_w.dumps(data))
    else:
        lines.append("# TODO: Map rule constraints to Codex config keys")

    return RenderedOutput(
        path=f"_fragments/config_{_safe_filename(ir.name)}.toml",
        content="\n".join(lines),
        description=f"Config fragment from rule: {ir.name} (merge manually)",
    )


def _render_codex_hook_scaffold(ir: ArtifactIR) -> RenderedOutput:
    """Render a hook scaffold for Codex."""
    event = ir.triggers[0].event if ir.triggers else "unknown"
    lines = [f"#!/usr/bin/env bash", ""]
    lines.append(f"# Hook scaffold: {ir.name}")
    lines.append(f"# Converted from {ir.source_platform.value} hook")
    lines.append(f"# Original event: {event}")
    lines.append(f"# Source: {ir.source_path}")
    lines.append("#")
    lines.append("# WARNING: This is a scaffold. Review and adapt before use.")
    lines.append("# The original hook logic may not be directly compatible.")
    lines.append("")

    if ir.instructions:
        lines.append("# --- Original hook content ---")
        for line in ir.instructions.split("\n"):
            lines.append(f"# {line}")
        lines.append("")

    lines.append("# TODO: Implement Codex-compatible hook logic")
    lines.append('echo "Hook scaffold: not yet implemented"')
    lines.append("exit 0")

    return RenderedOutput(
        path=f"hooks/{_safe_filename(ir.name)}.sh",
        content="\n".join(lines),
        description=f"Hook scaffold: {ir.name} (requires manual implementation)",
    )


def _render_codex_config(ir: ArtifactIR) -> RenderedOutput:
    """Render a Codex config.toml."""
    import tomli_w

    data = ir.metadata.copy()
    content = f"# Converted from {ir.source_platform.value} config\n"
    content += f"# Source: {ir.source_path}\n\n"
    if data:
        content += tomli_w.dumps(data)
    else:
        content += "# TODO: Populate Codex configuration\n"

    return RenderedOutput(
        path=".codex/config.toml",
        content=content,
        description="Codex project configuration",
    )


# --- Claude renderers ---

def _render_claude_md(ir: ArtifactIR) -> RenderedOutput:
    """Render CLAUDE.md from instruction doc IR."""
    lines = ["# CLAUDE.md", ""]
    lines.append(f"<!-- Converted from {ir.source_platform.value} instruction document -->")
    lines.append(f"<!-- Source: {ir.source_path} -->")
    lines.append("")

    for section in ir.sections:
        if section.title:
            lines.append(f"## {section.title}")
            lines.append("")
        if section.content:
            lines.append(section.content)
            lines.append("")

    if ir.constraints:
        lines.append("## Constraints")
        lines.append("")
        for c in ir.constraints:
            lines.append(f"- {c}")
        lines.append("")

    _append_conversion_notes(lines, ir)

    return RenderedOutput(
        path="CLAUDE.md",
        content="\n".join(lines),
        description="Claude project instruction document",
    )


def _render_claude_skill_dir(ir: ArtifactIR) -> list[RenderedOutput]:
    """Render a Claude skill directory with SKILL.md."""
    outputs: list[RenderedOutput] = []
    skill_name = _safe_filename(ir.name)

    # SKILL.md
    fm_lines = ["---"]
    if ir.name:
        fm_lines.append(f"name: {ir.name}")
    if ir.description:
        fm_lines.append(f"description: {ir.description}")
    fm_lines.append("---")
    fm_lines.append("")

    body = ir.instructions or ir.raw_content or f"# {ir.name}\n\nTODO: Add skill instructions"

    outputs.append(RenderedOutput(
        path=f"skills/{skill_name}/SKILL.md",
        content="\n".join(fm_lines) + body,
        description=f"Claude skill: {ir.name}",
    ))

    return outputs


def _render_claude_command(ir: ArtifactIR) -> RenderedOutput:
    """Render a Claude custom command."""
    fm_lines = ["---"]
    if ir.description:
        fm_lines.append(f"description: {ir.description}")
    if ir.required_tools:
        fm_lines.append(f"allowed-tools: {ir.required_tools}")
    fm_lines.append("---")
    fm_lines.append("")

    body = ir.instructions or ir.raw_content or f"# {ir.name}"

    return RenderedOutput(
        path=f"commands/{_safe_filename(ir.name)}.md",
        content="\n".join(fm_lines) + body,
        description=f"Claude command: {ir.name}",
    )


def _render_claude_rule(ir: ArtifactIR) -> RenderedOutput:
    """Render a Claude rule file."""
    content = ir.instructions or ""
    if not content and ir.constraints:
        content = "\n".join(f"- {c}" for c in ir.constraints)

    return RenderedOutput(
        path=f"rules/{_safe_filename(ir.name)}.md",
        content=content,
        description=f"Claude rule: {ir.name}",
    )


def _render_claude_hook_config(ir: ArtifactIR) -> RenderedOutput:
    """Render a Claude hook configuration snippet."""
    import json

    event = ir.triggers[0].event if ir.triggers else "unknown_event"
    hook_config = {
        "hooks": {
            event: {
                "command": f"# TODO: implement hook for {event}",
                "description": ir.description or f"Hook: {ir.name}",
            }
        },
        "_comment": f"Converted from {ir.source_platform.value} hook. Merge into .claude/settings.json",
    }

    return RenderedOutput(
        path=f"_fragments/hook_{_safe_filename(ir.name)}.json",
        content=json.dumps(hook_config, indent=2),
        description=f"Claude hook config fragment: {ir.name} (merge into settings.json)",
    )


def _render_claude_settings(ir: ArtifactIR) -> RenderedOutput:
    """Render Claude settings.json fragment."""
    import json

    data = {"_comment": f"Converted from {ir.source_platform.value} config"}
    data.update(ir.metadata)

    return RenderedOutput(
        path="_fragments/settings.json",
        content=json.dumps(data, indent=2),
        description="Claude settings fragment (merge into .claude/settings.json)",
    )


# --- Helpers ---

def _safe_filename(name: str) -> str:
    """Convert a name to a safe filename."""
    import re
    safe = re.sub(r"[^\w\s-]", "", name.lower())
    safe = re.sub(r"[\s]+", "-", safe).strip("-")
    return safe or "unnamed"


def _append_conversion_notes(lines: list[str], ir: ArtifactIR) -> None:
    """Append conversion notes as HTML comments."""
    if not ir.warnings and not ir.manual_todos:
        return

    lines.append("")
    lines.append("<!-- ===== CONVERSION NOTES ===== -->")

    if ir.warnings:
        lines.append("<!--")
        lines.append("Warnings:")
        for w in ir.warnings:
            lines.append(f"  [{w.level.value}] {w.message}")
            if w.suggestion:
                lines.append(f"    Suggestion: {w.suggestion}")
        lines.append("-->")

    if ir.manual_todos:
        lines.append("<!--")
        lines.append("Manual TODOs:")
        for t in ir.manual_todos:
            lines.append(f"  [{t.priority}] {t.description}")
            if t.reason:
                lines.append(f"    Reason: {t.reason}")
        lines.append("-->")


def _fallback_markdown(ir: ArtifactIR, target_name: str) -> str:
    lines = [f"# {ir.name}", ""]
    lines.append(f"<!-- Fallback conversion to {target_name} -->")
    lines.append(f"<!-- Original kind: {ir.kind} -->")
    lines.append(f"<!-- Source: {ir.source_path} -->")
    lines.append("")
    lines.append(ir.instructions or ir.raw_content or "<!-- No content -->")
    _append_conversion_notes(lines, ir)
    return "\n".join(lines)


def _write_outputs(result: RenderResult, output_dir: Path) -> None:
    """Write rendered outputs to disk."""
    for out in result.files:
        target = output_dir / out.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(out.content)
