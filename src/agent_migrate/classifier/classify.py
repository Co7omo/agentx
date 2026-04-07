"""Semantic classifier.

Refines the semantic intent classification after parsing, using content
analysis to determine the *real* purpose of the artifact beyond its
structural type.
"""

from __future__ import annotations

import re

from agent_migrate.ir import (
    ArtifactIR,
    ArtifactKind,
    Confidence,
    ExecutionModel,
    PortabilityRisk,
    SemanticIntent,
)


def classify_artifact(ir: ArtifactIR) -> ArtifactIR:
    """Refine classification of an artifact based on parsed content."""
    dispatch = {
        ArtifactKind.COMMAND: _classify_command,
        ArtifactKind.RULE: _classify_rule,
        ArtifactKind.SKILL: _classify_skill,
        ArtifactKind.HOOK: _classify_hook,
        ArtifactKind.INSTRUCTION_DOC: _classify_instruction_doc,
    }
    handler = dispatch.get(ir.kind)
    if handler:
        handler(ir)
    return ir


def _classify_command(ir: ArtifactIR) -> None:
    """Distinguish between prompt template, workflow, and agent persona."""
    content = ir.instructions or ir.raw_content
    lower = content.lower()

    step_count = len(re.findall(r"^\s*\d+\.\s+", content, re.MULTILINE))
    has_checklist = bool(re.findall(r"^\s*-\s*\[[ x]\]", content, re.MULTILINE))
    has_role = any(kw in lower for kw in ("you are", "act as", "your role", "persona"))
    has_params = bool(re.findall(r"\{\{?\w+\}?\}", content))

    if has_role and step_count <= 2:
        ir.intent = SemanticIntent.AGENT_PERSONA
        ir.execution_model = ExecutionModel.BACKGROUND_AGENT
    elif step_count > 3 or has_checklist:
        ir.intent = SemanticIntent.WORKFLOW_TEMPLATE
        ir.execution_model = ExecutionModel.INTERACTIVE_WORKFLOW
    elif has_params:
        ir.intent = SemanticIntent.PROMPT_TEMPLATE
        ir.execution_model = ExecutionModel.ON_DEMAND_PROMPT
    else:
        ir.intent = SemanticIntent.PROMPT_TEMPLATE
        ir.execution_model = ExecutionModel.ON_DEMAND_PROMPT


def _classify_rule(ir: ArtifactIR) -> None:
    """Distinguish between coding policy, config, and enforcement hook."""
    content = ir.instructions or ir.raw_content
    lower = content.lower()

    has_enforcement = any(kw in lower for kw in ("enforce", "reject", "fail", "error if", "must not"))
    has_config = any(kw in lower for kw in ("set ", "enable", "disable", "timeout", "max_", "min_"))
    has_style = any(kw in lower for kw in ("style", "format", "naming", "indent", "camelcase", "snake_case"))

    if has_enforcement and not has_style:
        ir.intent = SemanticIntent.EXECUTION_HOOK
        ir.portability_risk = PortabilityRisk.MEDIUM
        ir.add_warning(
            "Rule contains enforcement logic that may need to be implemented as a hook or CI check",
            code="ENFORCEMENT_RULE",
            suggestion="Consider creating a hook or CI step in the target platform",
        )
    elif has_config and not has_style:
        ir.intent = SemanticIntent.RUNTIME_CONFIG
    else:
        ir.intent = SemanticIntent.CODING_POLICY


def _classify_skill(ir: ArtifactIR) -> None:
    """Detect if a skill is really a workflow, prompt template, or agent."""
    content = ir.instructions or ir.raw_content
    lower = content.lower()

    has_role = any(kw in lower for kw in ("you are", "act as", "your role"))
    step_count = len(re.findall(r"^\s*\d+\.\s+", content, re.MULTILINE))

    if has_role and step_count <= 2:
        ir.intent = SemanticIntent.AGENT_PERSONA
    elif step_count > 3:
        ir.intent = SemanticIntent.WORKFLOW_TEMPLATE


def _classify_hook(ir: ArtifactIR) -> None:
    """Assess hook portability."""
    content = ir.raw_content
    lower = content.lower()

    # Hooks that rely on specific platform APIs are less portable
    if any(kw in lower for kw in ("claude", "anthropic", "mcp")):
        ir.portability_risk = PortabilityRisk.HIGH
        ir.confidence = Confidence.LOW
    elif any(kw in lower for kw in ("git ", "npm ", "make ", "cargo ")):
        ir.portability_risk = PortabilityRisk.LOW
        ir.confidence = Confidence.HIGH


def _classify_instruction_doc(ir: ArtifactIR) -> None:
    """Classify composite instruction docs (CLAUDE.md / AGENTS.md)."""
    # Already classified by section in parser; just validate
    if not ir.intents or ir.intents == [SemanticIntent.UNKNOWN]:
        ir.intents = [SemanticIntent.PROJECT_MEMORY]
