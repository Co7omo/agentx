"""Parser layer.

Takes a detected ArtifactIR (with kind/platform set) and enriches it
with structured semantic content extracted from the raw artifact.
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_migrate.ir import (
    ArtifactIR,
    ArtifactKind,
    Confidence,
    ExternalDependency,
    Platform,
    PortabilityRisk,
    Section,
    SemanticIntent,
    Trigger,
    WarningLevel,
)


def parse_artifact(ir: ArtifactIR) -> ArtifactIR:
    """Enrich an IR with parsed semantic content."""
    dispatch = {
        ArtifactKind.INSTRUCTION_DOC: _parse_instruction_doc,
        ArtifactKind.SKILL: _parse_skill,
        ArtifactKind.COMMAND: _parse_command,
        ArtifactKind.RULE: _parse_rule,
        ArtifactKind.SUBAGENT: _parse_subagent,
        ArtifactKind.HOOK: _parse_hook,
        ArtifactKind.CONFIG: _parse_config,
    }
    handler = dispatch.get(ir.kind)
    if handler:
        return handler(ir)
    return ir


def _parse_instruction_doc(ir: ArtifactIR) -> ArtifactIR:
    """Parse CLAUDE.md or AGENTS.md into structured sections."""
    content = ir.raw_content
    sections = _split_markdown_sections(content)
    ir.sections = sections
    ir.intents = _classify_sections(sections)

    # Extract constraints (lines starting with "- " under constraint-like headings)
    for sec in sections:
        if any(kw in sec.title.lower() for kw in ("constraint", "rule", "policy", "never", "always", "do not")):
            ir.constraints.extend(_extract_list_items(sec.content))

    # Detect external dependencies
    ir.external_dependencies = _detect_dependencies(content)

    # Detect required tools
    ir.required_tools = _detect_tools(content)

    return ir


def _parse_skill(ir: ArtifactIR) -> ArtifactIR:
    """Parse a skill (SKILL.md or directory with SKILL.md)."""
    content = ir.raw_content

    # Extract from frontmatter
    fm = ir.frontmatter
    if fm:
        ir.name = fm.get("name", ir.name)
        ir.description = fm.get("description", ir.description)
        if "trigger" in fm:
            ir.triggers.append(Trigger(event="pattern", pattern=str(fm["trigger"])))

    ir.sections = _split_markdown_sections(content)
    ir.instructions = _strip_frontmatter(content)
    ir.external_dependencies = _detect_dependencies(content)
    ir.required_tools = _detect_tools(content)

    # Detect files referenced
    source_path = Path(ir.source_path)
    if source_path.is_dir():
        ir.files_included = [
            str(f.relative_to(source_path))
            for f in source_path.rglob("*")
            if f.is_file() and f.name != "SKILL.md"
        ]

    return ir


def _parse_command(ir: ArtifactIR) -> ArtifactIR:
    """Parse a custom command."""
    content = ir.raw_content
    fm = ir.frontmatter

    if fm:
        ir.name = fm.get("name", ir.name)
        ir.description = fm.get("description", ir.description)
        if "allowed-tools" in fm:
            ir.required_tools = fm["allowed-tools"] if isinstance(fm["allowed-tools"], list) else [fm["allowed-tools"]]

    ir.instructions = _strip_frontmatter(content)
    ir.sections = _split_markdown_sections(content)
    ir.external_dependencies = _detect_dependencies(content)

    # Heuristic: multi-step = skill-like, single prompt = command-like
    steps = _count_steps(content)
    if steps > 3:
        ir.intent = SemanticIntent.WORKFLOW_TEMPLATE
        ir.add_warning(
            f"Command has {steps} steps - consider converting to a skill rather than a simple prompt",
            level=WarningLevel.INFO,
            code="MULTI_STEP_COMMAND",
        )

    return ir


def _parse_rule(ir: ArtifactIR) -> ArtifactIR:
    """Parse a rule file."""
    content = ir.raw_content
    ir.instructions = _strip_frontmatter(content)
    ir.constraints = _extract_list_items(content)
    ir.sections = _split_markdown_sections(content)
    return ir


def _parse_subagent(ir: ArtifactIR) -> ArtifactIR:
    """Parse a subagent definition (TOML for Codex, markdown for Claude)."""
    if ir.source_platform == Platform.CODEX:
        return _parse_codex_agent_toml(ir)
    return _parse_claude_subagent(ir)


def _parse_codex_agent_toml(ir: ArtifactIR) -> ArtifactIR:
    """Parse a Codex agent TOML file."""
    try:
        import tomli
        data = tomli.loads(ir.raw_content)
    except Exception:
        ir.add_warning("Failed to parse TOML content", level=WarningLevel.ERROR)
        return ir

    ir.name = data.get("name", ir.name)
    ir.description = data.get("description", "")
    ir.instructions = data.get("instructions", data.get("system_prompt", ""))
    ir.required_tools = data.get("tools", [])
    ir.metadata = data

    if "model" in data:
        ir.metadata["model"] = data["model"]

    if "triggers" in data:
        for t in data["triggers"]:
            ir.triggers.append(Trigger(
                event=t.get("event", ""),
                pattern=t.get("pattern", ""),
                description=t.get("description", ""),
            ))

    return ir


def _parse_claude_subagent(ir: ArtifactIR) -> ArtifactIR:
    """Parse a Claude-style subagent (typically embedded in config or CLAUDE.md)."""
    ir.instructions = _strip_frontmatter(ir.raw_content)
    ir.sections = _split_markdown_sections(ir.raw_content)
    return ir


def _parse_hook(ir: ArtifactIR) -> ArtifactIR:
    """Parse a hook script."""
    content = ir.raw_content

    # Detect trigger from filename or content
    name_lower = ir.name.lower()
    for event in ("pre-commit", "post-commit", "pre-push", "post-push", "pre-save", "post-save"):
        if event in name_lower:
            ir.triggers.append(Trigger(event=event, description=f"Lifecycle event: {event}"))
            break

    ir.instructions = content
    ir.external_dependencies = _detect_dependencies(content)
    ir.portability_risk = PortabilityRisk.MEDIUM
    ir.add_warning(
        "Hook scripts often depend on platform-specific lifecycle events",
        code="HOOK_PORTABILITY",
        suggestion="Verify that the target platform supports equivalent lifecycle events",
    )
    return ir


def _parse_config(ir: ArtifactIR) -> ArtifactIR:
    """Parse a configuration file."""
    content = ir.raw_content
    suffix = Path(ir.source_path).suffix.lower()

    if suffix == ".toml":
        try:
            import tomli
            ir.metadata = tomli.loads(content)
        except Exception:
            ir.add_warning("Failed to parse TOML", level=WarningLevel.ERROR)
    elif suffix == ".json":
        try:
            import json
            ir.metadata = json.loads(content)
        except Exception:
            ir.add_warning("Failed to parse JSON", level=WarningLevel.ERROR)
    elif suffix in (".yaml", ".yml"):
        try:
            import yaml
            ir.metadata = yaml.safe_load(content) or {}
        except Exception:
            ir.add_warning("Failed to parse YAML", level=WarningLevel.ERROR)

    return ir


# --- Helpers ---

def _split_markdown_sections(content: str) -> list[Section]:
    """Split markdown content into sections by headings."""
    lines = content.split("\n")
    sections: list[Section] = []
    current_title = ""
    current_lines: list[str] = []

    for line in lines:
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            if current_title or current_lines:
                sec_content = "\n".join(current_lines).strip()
                sections.append(Section(
                    title=current_title,
                    content=sec_content,
                    intent=_classify_section_title(current_title),
                ))
            current_title = heading_match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Last section
    if current_title or current_lines:
        sec_content = "\n".join(current_lines).strip()
        sections.append(Section(
            title=current_title,
            content=sec_content,
            intent=_classify_section_title(current_title),
        ))

    return sections


def _classify_section_title(title: str) -> SemanticIntent:
    lower = title.lower()
    if any(kw in lower for kw in ("build", "test", "run", "install", "setup", "dev")):
        return SemanticIntent.BUILD_TEST_INSTRUCTIONS
    if any(kw in lower for kw in ("style", "convention", "format", "lint", "naming", "policy")):
        return SemanticIntent.CODING_POLICY
    if any(kw in lower for kw in ("review", "checklist", "pr", "merge")):
        return SemanticIntent.REVIEW_CHECKLIST
    if any(kw in lower for kw in ("workflow", "process", "procedure", "step")):
        return SemanticIntent.WORKFLOW_TEMPLATE
    if any(kw in lower for kw in ("hook", "trigger", "event", "lifecycle")):
        return SemanticIntent.EXECUTION_HOOK
    if any(kw in lower for kw in ("config", "setting", "option", "preference")):
        return SemanticIntent.RUNTIME_CONFIG
    if any(kw in lower for kw in ("tool", "integration", "mcp", "api", "service")):
        return SemanticIntent.EXTERNAL_TOOL_BRIDGE
    if any(kw in lower for kw in ("memory", "context", "project", "overview", "about")):
        return SemanticIntent.PROJECT_MEMORY
    return SemanticIntent.UNKNOWN


def _classify_sections(sections: list[Section]) -> list[SemanticIntent]:
    intents = list({s.intent for s in sections if s.intent != SemanticIntent.UNKNOWN})
    return intents or [SemanticIntent.UNKNOWN]


def _extract_list_items(content: str) -> list[str]:
    items = []
    for line in content.split("\n"):
        match = re.match(r"^\s*[-*]\s+(.+)$", line)
        if match:
            items.append(match.group(1).strip())
    return items


def _strip_frontmatter(content: str) -> str:
    return re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, flags=re.DOTALL).strip()


def _detect_dependencies(content: str) -> list[ExternalDependency]:
    deps: list[ExternalDependency] = []
    # Shell commands
    for cmd in re.findall(r"`(npm|yarn|pnpm|pip|cargo|go|make|docker|kubectl|gh|git)\b[^`]*`", content):
        tool = cmd.split()[0]
        if not any(d.name == tool for d in deps):
            deps.append(ExternalDependency(name=tool, kind="shell_command", portable=True))
    # MCP references
    if "mcp" in content.lower():
        deps.append(ExternalDependency(
            name="MCP server",
            kind="mcp_server",
            portable=False,
            notes="MCP server configuration is platform-specific",
        ))
    # API/service references
    for service in re.findall(r"(?:https?://[^\s)]+)", content):
        deps.append(ExternalDependency(name=service, kind="api", portable=True))
    return deps


def _detect_tools(content: str) -> list[str]:
    tools = []
    # Claude-specific tool references
    for tool in re.findall(r"\b(Read|Write|Edit|Bash|Grep|Glob|Agent|WebSearch|WebFetch)\b", content):
        if tool not in tools:
            tools.append(tool)
    return tools


def _count_steps(content: str) -> int:
    """Count numbered steps or checklist items."""
    numbered = len(re.findall(r"^\s*\d+\.\s+", content, re.MULTILINE))
    checkboxes = len(re.findall(r"^\s*-\s*\[[ x]\]", content, re.MULTILINE))
    return max(numbered, checkboxes)
