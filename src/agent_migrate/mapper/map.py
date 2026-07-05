"""Mapper layer.

Transforms an IR from source platform semantics to target platform semantics.
Chooses the best target construct, annotates interpretive choices, and
generates warnings for lossy mappings.
"""

from __future__ import annotations

from copy import deepcopy

from agent_migrate.ir import (
    ArtifactIR,
    ArtifactKind,
    Confidence,
    ExecutionModel,
    ManualTodo,
    Platform,
    PortabilityRisk,
    Section,
    SemanticIntent,
    Warning,
    WarningLevel,
)


def map_artifact(ir: ArtifactIR, target: Platform) -> ArtifactIR:
    """Map an IR to the target platform, returning a new IR.

    A mapper plugin registered for (source, target) overrides the
    built-in mapping for that direction.
    """
    from agent_migrate.plugins import get_mapper

    plugin = get_mapper(ir.source_platform, target)
    if plugin is not None:
        mapped = plugin.map(deepcopy(ir), target)
        mapped.target_platform = target
        return mapped

    mapped = deepcopy(ir)
    mapped.target_platform = target

    if ir.source_platform == target:
        mapped.add_warning("Source and target platforms are the same", level=WarningLevel.INFO)
        return mapped

    if target == Platform.CODEX:
        return _map_to_codex(mapped)
    elif target == Platform.CLAUDE:
        return _map_to_claude(mapped)
    else:
        mapped.add_warning("Unknown target platform", level=WarningLevel.ERROR)
        return mapped


def _map_to_codex(ir: ArtifactIR) -> ArtifactIR:
    """Map from Claude (or unknown) to Codex."""
    dispatch = {
        ArtifactKind.INSTRUCTION_DOC: _map_instruction_doc_to_codex,
        ArtifactKind.SKILL: _map_skill_to_codex,
        ArtifactKind.COMMAND: _map_command_to_codex,
        ArtifactKind.RULE: _map_rule_to_codex,
        ArtifactKind.SUBAGENT: _map_subagent_to_codex,
        ArtifactKind.HOOK: _map_hook_to_codex,
        ArtifactKind.CONFIG: _map_config_to_codex,
    }
    handler = dispatch.get(ir.kind)
    if handler:
        return handler(ir)
    ir.add_warning(
        f"No mapper for kind={ir.kind} to Codex",
        level=WarningLevel.WARN,
        suggestion="Manual conversion required",
    )
    ir.confidence = Confidence.LOW
    return ir


def _map_to_claude(ir: ArtifactIR) -> ArtifactIR:
    """Map from Codex (or unknown) to Claude."""
    dispatch = {
        ArtifactKind.INSTRUCTION_DOC: _map_instruction_doc_to_claude,
        ArtifactKind.SKILL: _map_skill_to_claude,
        ArtifactKind.COMMAND: _map_command_to_claude,
        ArtifactKind.RULE: _map_rule_to_claude,
        ArtifactKind.SUBAGENT: _map_subagent_to_claude,
        ArtifactKind.HOOK: _map_hook_to_claude,
        ArtifactKind.CONFIG: _map_config_to_claude,
    }
    handler = dispatch.get(ir.kind)
    if handler:
        return handler(ir)
    ir.add_warning(
        f"No mapper for kind={ir.kind} to Claude",
        level=WarningLevel.WARN,
        suggestion="Manual conversion required",
    )
    ir.confidence = Confidence.LOW
    return ir


# --- Claude -> Codex mappers ---

def _map_instruction_doc_to_codex(ir: ArtifactIR) -> ArtifactIR:
    """CLAUDE.md -> AGENTS.md"""
    ir.name = "AGENTS"
    ir.description = "Converted from CLAUDE.md"
    ir.confidence = Confidence.HIGH
    ir.portability_risk = PortabilityRisk.LOW

    # Remap sections: Claude-specific tool references need adaptation
    for sec in ir.sections:
        _adapt_claude_references_for_codex(sec)

    # Warn about Claude-specific features
    if ir.required_tools:
        ir.add_warning(
            f"References to Claude-specific tools: {', '.join(ir.required_tools)}",
            code="CLAUDE_TOOLS_REF",
            suggestion="Replace with Codex-equivalent tool names or remove",
        )
        ir.add_todo(
            "Review and adapt Claude-specific tool references",
            priority="high",
            reason="Codex may not have equivalent tools with the same names",
        )

    return ir


def _map_skill_to_codex(ir: ArtifactIR) -> ArtifactIR:
    """Claude skill -> Codex skill/custom prompt."""
    ir.confidence = Confidence.MEDIUM

    # If skill uses Claude-specific tools, flag it
    claude_tools = [t for t in ir.required_tools if t in ("Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent")]
    if claude_tools:
        ir.add_warning(
            f"Skill references Claude-specific tools: {', '.join(claude_tools)}",
            code="CLAUDE_TOOLS_IN_SKILL",
            suggestion="Adapt tool references to Codex equivalents",
        )
        ir.portability_risk = PortabilityRisk.MEDIUM

    # If the skill is really a workflow, map to Codex custom prompt
    if ir.intent == SemanticIntent.WORKFLOW_TEMPLATE:
        ir.metadata["codex_target"] = "custom_prompt"
    else:
        ir.metadata["codex_target"] = "skill"

    return ir


def _map_command_to_codex(ir: ArtifactIR) -> ArtifactIR:
    """Claude command -> Codex custom prompt or skill."""
    if ir.intent == SemanticIntent.WORKFLOW_TEMPLATE:
        ir.metadata["codex_target"] = "skill"
        ir.confidence = Confidence.MEDIUM
        ir.add_warning(
            "Multi-step command converted to skill; verify workflow steps are compatible",
            code="COMMAND_TO_SKILL",
        )
    elif ir.intent == SemanticIntent.AGENT_PERSONA:
        ir.kind = ArtifactKind.SUBAGENT
        ir.metadata["codex_target"] = "agent"
        ir.confidence = Confidence.MEDIUM
        ir.add_warning(
            "Command with agent persona converted to subagent definition",
            code="COMMAND_TO_AGENT",
        )
    else:
        ir.metadata["codex_target"] = "custom_prompt"
        ir.confidence = Confidence.HIGH

    return ir


def _map_rule_to_codex(ir: ArtifactIR) -> ArtifactIR:
    """Claude rule -> Codex instruction or config."""
    if ir.intent == SemanticIntent.RUNTIME_CONFIG:
        ir.kind = ArtifactKind.CONFIG
        ir.metadata["codex_target"] = "config"
        ir.confidence = Confidence.MEDIUM
        ir.add_warning(
            "Rule with configuration semantics mapped to Codex config",
            code="RULE_TO_CONFIG",
            suggestion="Verify config key names match Codex expectations",
        )
    elif ir.intent == SemanticIntent.EXECUTION_HOOK:
        ir.kind = ArtifactKind.HOOK
        ir.metadata["codex_target"] = "hook_scaffold"
        ir.confidence = Confidence.LOW
        ir.add_warning(
            "Enforcement rule mapped to hook scaffold; requires manual implementation",
            code="RULE_TO_HOOK",
        )
        ir.add_todo(
            "Implement enforcement logic as a Codex hook or CI step",
            priority="high",
            reason="Enforcement rules cannot be directly converted to static config",
        )
    else:
        # Coding policy -> merge into AGENTS.md
        ir.metadata["codex_target"] = "agents_md_section"
        ir.confidence = Confidence.HIGH

    return ir


def _map_subagent_to_codex(ir: ArtifactIR) -> ArtifactIR:
    """Claude subagent -> Codex agent TOML."""
    ir.metadata["codex_target"] = "agent_toml"
    ir.confidence = Confidence.MEDIUM

    # Claude subagents may have different orchestration models
    ir.add_warning(
        "Subagent orchestration model may differ between Claude and Codex",
        code="SUBAGENT_ORCHESTRATION",
        suggestion="Review how the target platform dispatches and manages subagents",
    )
    ir.add_todo(
        "Verify subagent lifecycle and communication model in Codex",
        priority="medium",
        reason="Claude and Codex may handle subagent spawning differently",
    )
    return ir


def _map_hook_to_codex(ir: ArtifactIR) -> ArtifactIR:
    """Claude hook -> Codex hook (if mappable) or scaffold."""
    ir.metadata["codex_target"] = "hook_scaffold"

    # Check if the lifecycle event is mappable
    mappable_events = {"pre-commit", "post-commit", "pre-push"}
    hook_events = {t.event for t in ir.triggers}

    if hook_events & mappable_events:
        ir.confidence = Confidence.MEDIUM
        ir.add_warning(
            "Hook event is partially mappable; verify Codex hook configuration",
            code="HOOK_PARTIAL_MAP",
        )
    else:
        ir.confidence = Confidence.LOW
        ir.portability_risk = PortabilityRisk.HIGH
        ir.add_warning(
            "Hook lifecycle event has no direct Codex equivalent",
            code="HOOK_NO_EQUIVALENT",
            suggestion="Implement as a custom script or CI step",
        )
        ir.add_todo(
            "Manually implement hook behavior in Codex",
            priority="high",
            reason="No automatic mapping exists for this lifecycle event",
        )

    return ir


def _map_config_to_codex(ir: ArtifactIR) -> ArtifactIR:
    """Claude config -> Codex config.toml."""
    ir.metadata["codex_target"] = "config_toml"
    ir.confidence = Confidence.MEDIUM
    ir.add_warning(
        "Configuration keys may not map 1:1 between platforms",
        code="CONFIG_KEY_MISMATCH",
        suggestion="Review Codex config documentation for equivalent settings",
    )
    return ir


# --- Codex -> Claude mappers ---

def _map_instruction_doc_to_claude(ir: ArtifactIR) -> ArtifactIR:
    """AGENTS.md -> CLAUDE.md"""
    ir.name = "CLAUDE"
    ir.description = "Converted from AGENTS.md"
    ir.confidence = Confidence.HIGH
    ir.portability_risk = PortabilityRisk.LOW

    for sec in ir.sections:
        _adapt_codex_references_for_claude(sec)

    return ir


def _map_skill_to_claude(ir: ArtifactIR) -> ArtifactIR:
    """Codex skill -> Claude skill with SKILL.md."""
    ir.metadata["claude_target"] = "skill_directory"
    ir.confidence = Confidence.MEDIUM
    return ir


def _map_command_to_claude(ir: ArtifactIR) -> ArtifactIR:
    """Codex command/prompt -> Claude command."""
    ir.metadata["claude_target"] = "command"
    ir.confidence = Confidence.HIGH
    return ir


def _map_rule_to_claude(ir: ArtifactIR) -> ArtifactIR:
    """Codex rule -> Claude rule or CLAUDE.md section."""
    if ir.intent == SemanticIntent.RUNTIME_CONFIG:
        ir.metadata["claude_target"] = "settings_json"
        ir.confidence = Confidence.MEDIUM
    else:
        ir.metadata["claude_target"] = "rule_file"
        ir.confidence = Confidence.HIGH
    return ir


def _map_subagent_to_claude(ir: ArtifactIR) -> ArtifactIR:
    """Codex agent -> Claude subagent reference (in CLAUDE.md or as skill)."""
    ir.metadata["claude_target"] = "subagent_skill"
    ir.confidence = Confidence.MEDIUM
    ir.add_warning(
        "Codex agent TOML converted to Claude skill with agent persona",
        code="AGENT_TO_SKILL",
        suggestion="Claude uses Agent tool for subagent dispatch; review orchestration",
    )
    ir.add_todo(
        "Configure Claude Agent tool dispatch for this subagent",
        priority="medium",
        reason="Claude subagent lifecycle differs from Codex agent TOML",
    )
    return ir


def _map_hook_to_claude(ir: ArtifactIR) -> ArtifactIR:
    """Codex hook -> Claude hook (settings.json hooks section)."""
    ir.metadata["claude_target"] = "hook_config"
    ir.confidence = Confidence.MEDIUM
    ir.add_warning(
        "Codex hook mapped to Claude settings.json hook; verify event compatibility",
        code="HOOK_EVENT_MAP",
    )
    return ir


def _map_config_to_claude(ir: ArtifactIR) -> ArtifactIR:
    """Codex config.toml -> Claude settings / CLAUDE.md."""
    ir.metadata["claude_target"] = "settings_json"
    ir.confidence = Confidence.MEDIUM
    ir.add_warning(
        "Configuration keys may not map 1:1 between platforms",
        code="CONFIG_KEY_MISMATCH",
        suggestion="Review Claude settings documentation for equivalent options",
    )
    return ir


# --- Adaptation helpers ---

_CLAUDE_TO_CODEX_TOOL_MAP = {
    "Read": "file_read",
    "Write": "file_write",
    "Edit": "file_edit",
    "Bash": "shell",
    "Grep": "search",
    "Glob": "file_search",
    "Agent": "subagent",
    "WebSearch": "web_search",
    "WebFetch": "web_fetch",
}

_CODEX_TO_CLAUDE_TOOL_MAP = {v: k for k, v in _CLAUDE_TO_CODEX_TOOL_MAP.items()}


def _adapt_claude_references_for_codex(section: Section) -> None:
    """Adapt Claude-specific references in section content."""
    for old, new in _CLAUDE_TO_CODEX_TOOL_MAP.items():
        if old in section.content:
            section.content = section.content.replace(
                f"`{old}`", f"`{new}` <!-- was Claude:{old} -->"
            )
            section.metadata["adapted_tools"] = section.metadata.get("adapted_tools", [])
            section.metadata["adapted_tools"].append(f"{old}->{new}")


def _adapt_codex_references_for_claude(section: Section) -> None:
    """Adapt Codex-specific references in section content."""
    for old, new in _CODEX_TO_CLAUDE_TOOL_MAP.items():
        if old in section.content:
            section.content = section.content.replace(
                f"`{old}`", f"`{new}` <!-- was Codex:{old} -->"
            )
