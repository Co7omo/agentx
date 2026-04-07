"""Artifact detection layer.

Identifies artifact type and source platform using filename, path, extension,
directory structure, content patterns, and frontmatter/metadata.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agent_migrate.ir import (
    ArtifactIR,
    ArtifactKind,
    Confidence,
    ExecutionModel,
    Platform,
    PortabilityRisk,
    SemanticIntent,
)


def detect_artifact(path: Path) -> ArtifactIR:
    """Detect what kind of artifact a file or directory represents."""
    if path.is_dir():
        return _detect_dir_artifact(path)
    return _detect_file_artifact(path)


def detect_directory(path: Path) -> list[ArtifactIR]:
    """Scan a directory and detect all recognizable artifacts."""
    results: list[ArtifactIR] = []
    if not path.is_dir():
        return [detect_artifact(path)]

    for item in sorted(path.iterdir()):
        if item.name.startswith(".") and item.name not in (".codex",):
            continue
        if item.is_file():
            ir = _detect_file_artifact(item)
            if ir.kind != ArtifactKind.UNKNOWN:
                results.append(ir)
        elif item.is_dir():
            ir = _detect_dir_artifact(item)
            if ir.kind != ArtifactKind.UNKNOWN:
                results.append(ir)
            # Recurse into known directories
            if item.name in ("skills", "commands", ".codex", "agents", "rules"):
                results.extend(detect_directory(item))
    return results


def _detect_file_artifact(path: Path) -> ArtifactIR:
    """Detect artifact type from a single file."""
    name = path.name
    stem = path.stem.lower()
    suffix = path.suffix.lower()

    ir = ArtifactIR(
        source_path=str(path),
        name=path.stem,
    )

    # Read content for pattern matching
    content = ""
    try:
        content = path.read_text(errors="replace")
        ir.raw_content = content
    except (OSError, UnicodeDecodeError):
        ir.add_warning("Could not read file content")

    # Parse frontmatter if present
    ir.frontmatter = _extract_frontmatter(content)

    # --- Claude artifacts ---
    if name == "CLAUDE.md":
        ir.kind = ArtifactKind.INSTRUCTION_DOC
        ir.source_platform = Platform.CLAUDE
        ir.intent = SemanticIntent.PROJECT_MEMORY
        ir.execution_model = ExecutionModel.STATIC_INSTRUCTION
        ir.confidence = Confidence.HIGH
        ir.portability_risk = PortabilityRisk.LOW
        ir.description = "Claude project instruction document"
        return ir

    if name == "SKILL.md":
        ir.kind = ArtifactKind.SKILL
        ir.source_platform = Platform.CLAUDE
        ir.intent = SemanticIntent.WORKFLOW_TEMPLATE
        ir.execution_model = ExecutionModel.ON_DEMAND_PROMPT
        ir.confidence = Confidence.HIGH
        ir.description = "Claude skill definition"
        return ir

    # --- Codex artifacts ---
    if name == "AGENTS.md":
        ir.kind = ArtifactKind.INSTRUCTION_DOC
        ir.source_platform = Platform.CODEX
        ir.intent = SemanticIntent.PROJECT_MEMORY
        ir.execution_model = ExecutionModel.STATIC_INSTRUCTION
        ir.confidence = Confidence.HIGH
        ir.portability_risk = PortabilityRisk.LOW
        ir.description = "Codex agent instruction document"
        return ir

    if name == "config.toml" and ".codex" in str(path):
        ir.kind = ArtifactKind.CONFIG
        ir.source_platform = Platform.CODEX
        ir.intent = SemanticIntent.RUNTIME_CONFIG
        ir.execution_model = ExecutionModel.CONFIG_SETTING
        ir.confidence = Confidence.HIGH
        ir.description = "Codex project configuration"
        return ir

    # Codex agent TOML
    if suffix == ".toml" and _path_contains(path, "agents"):
        ir.kind = ArtifactKind.SUBAGENT
        ir.source_platform = Platform.CODEX
        ir.intent = SemanticIntent.AGENT_PERSONA
        ir.execution_model = ExecutionModel.BACKGROUND_AGENT
        ir.confidence = Confidence.HIGH
        ir.description = "Codex subagent definition"
        return ir

    # --- Heuristic detection ---

    # Shell scripts that look like hooks
    if suffix in (".sh", ".bash", ".zsh") or (suffix == "" and _is_executable(content)):
        if _looks_like_hook(content, name):
            ir.kind = ArtifactKind.HOOK
            ir.source_platform = _guess_platform_from_path(path)
            ir.intent = SemanticIntent.EXECUTION_HOOK
            ir.execution_model = ExecutionModel.LIFECYCLE_HOOK
            ir.confidence = Confidence.MEDIUM
            ir.portability_risk = PortabilityRisk.MEDIUM
            ir.description = f"Lifecycle hook script: {name}"
            return ir

    # Markdown files that look like rules
    if suffix == ".md" and _path_contains(path, "rules"):
        ir.kind = ArtifactKind.RULE
        ir.source_platform = _guess_platform_from_path(path)
        ir.intent = _classify_rule_intent(content)
        ir.execution_model = ExecutionModel.STATIC_INSTRUCTION
        ir.confidence = Confidence.MEDIUM
        ir.description = f"Rule: {path.stem}"
        return ir

    # Markdown files that look like commands
    if suffix == ".md" and _path_contains(path, "commands"):
        ir.kind = ArtifactKind.COMMAND
        ir.source_platform = _guess_platform_from_path(path)
        ir.intent = _classify_command_intent(content)
        ir.execution_model = ExecutionModel.ON_DEMAND_PROMPT
        ir.confidence = Confidence.MEDIUM
        ir.description = f"Custom command: {path.stem}"
        return ir

    # JSON/YAML config files
    if suffix in (".json", ".yaml", ".yml"):
        if any(kw in content.lower() for kw in ("model", "agent", "tool", "hook")):
            ir.kind = ArtifactKind.CONFIG
            ir.source_platform = _guess_platform_from_path(path)
            ir.intent = SemanticIntent.RUNTIME_CONFIG
            ir.execution_model = ExecutionModel.CONFIG_SETTING
            ir.confidence = Confidence.LOW
            ir.description = f"Configuration file: {name}"
            return ir

    return ir


def _detect_dir_artifact(path: Path) -> ArtifactIR:
    """Detect artifact type from a directory."""
    name = path.name
    ir = ArtifactIR(
        source_path=str(path),
        name=name,
        kind=ArtifactKind.UNKNOWN,
    )

    # Claude skill directory (contains SKILL.md)
    skill_md = path / "SKILL.md"
    if skill_md.exists():
        ir.kind = ArtifactKind.SKILL
        ir.source_platform = Platform.CLAUDE
        ir.intent = SemanticIntent.WORKFLOW_TEMPLATE
        ir.execution_model = ExecutionModel.ON_DEMAND_PROMPT
        ir.confidence = Confidence.HIGH
        ir.description = f"Claude skill: {name}"
        ir.files_included = [str(f.relative_to(path)) for f in path.rglob("*") if f.is_file()]
        try:
            ir.raw_content = skill_md.read_text()
            ir.frontmatter = _extract_frontmatter(ir.raw_content)
        except OSError:
            pass
        return ir

    # .codex directory
    if name == ".codex":
        ir.kind = ArtifactKind.CONFIG
        ir.source_platform = Platform.CODEX
        ir.intent = SemanticIntent.RUNTIME_CONFIG
        ir.execution_model = ExecutionModel.CONFIG_SETTING
        ir.confidence = Confidence.HIGH
        ir.description = "Codex project configuration directory"
        return ir

    # Agents directory
    if name == "agents" and any(f.suffix == ".toml" for f in path.iterdir() if f.is_file()):
        ir.kind = ArtifactKind.SUBAGENT
        ir.source_platform = Platform.CODEX
        ir.intent = SemanticIntent.AGENT_PERSONA
        ir.confidence = Confidence.HIGH
        ir.description = "Codex agents directory"
        return ir

    return ir


def _extract_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter from markdown content."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}
    try:
        import yaml
        return yaml.safe_load(match.group(1)) or {}
    except Exception:
        return {}


def _path_contains(path: Path, segment: str) -> bool:
    return segment in path.parts


def _is_executable(content: str) -> bool:
    return content.startswith("#!") or content.startswith("#!/")


def _looks_like_hook(content: str, name: str) -> bool:
    hook_keywords = ["pre-commit", "post-commit", "pre-push", "post-push",
                     "pre_commit", "post_commit", "PreCommit", "PostCommit",
                     "lifecycle", "hook", "on_event"]
    hook_names = ["pre-commit", "post-commit", "pre-push", "post-push",
                  "pre-save", "post-save", "on-save"]
    if any(name.startswith(h) or name == h for h in hook_names):
        return True
    return any(kw in content.lower() for kw in hook_keywords)


def _guess_platform_from_path(path: Path) -> Platform:
    path_str = str(path).lower()
    if ".codex" in path_str or "codex" in path_str:
        return Platform.CODEX
    if "claude" in path_str or "skill.md" in path_str:
        return Platform.CLAUDE
    return Platform.UNKNOWN


def _classify_rule_intent(content: str) -> SemanticIntent:
    lower = content.lower()
    if any(kw in lower for kw in ("style", "format", "naming", "convention", "lint")):
        return SemanticIntent.CODING_POLICY
    if any(kw in lower for kw in ("build", "test", "run", "deploy")):
        return SemanticIntent.BUILD_TEST_INSTRUCTIONS
    if any(kw in lower for kw in ("review", "checklist", "pr ", "pull request")):
        return SemanticIntent.REVIEW_CHECKLIST
    return SemanticIntent.CODING_POLICY


def _classify_command_intent(content: str) -> SemanticIntent:
    lower = content.lower()
    if any(kw in lower for kw in ("step", "checklist", "workflow", "procedure")):
        return SemanticIntent.WORKFLOW_TEMPLATE
    return SemanticIntent.PROMPT_TEMPLATE
