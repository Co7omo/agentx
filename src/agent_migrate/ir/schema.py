"""Intermediate Representation schema for agent artifacts.

This IR is the central data structure that all detectors produce and all
mappers consume. It captures both the structural content and the semantic
intent of each artifact, enabling loss-aware conversion between ecosystems.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Platform(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"
    UNKNOWN = "unknown"


class ArtifactKind(str, Enum):
    INSTRUCTION_DOC = "instruction_doc"
    SKILL = "skill"
    COMMAND = "command"
    RULE = "rule"
    SUBAGENT = "subagent"
    HOOK = "hook"
    CONFIG = "config"
    INTEGRATION = "integration"
    UNKNOWN = "unknown"


class SemanticIntent(str, Enum):
    """High-level semantic classification of what the artifact *does*."""

    PROJECT_MEMORY = "project_memory"
    CODING_POLICY = "coding_policy"
    WORKFLOW_TEMPLATE = "workflow_template"
    PROMPT_TEMPLATE = "prompt_template"
    AGENT_PERSONA = "agent_persona"
    EXECUTION_HOOK = "execution_hook"
    RUNTIME_CONFIG = "runtime_config"
    EXTERNAL_TOOL_BRIDGE = "external_tool_bridge"
    BUILD_TEST_INSTRUCTIONS = "build_test_instructions"
    REVIEW_CHECKLIST = "review_checklist"
    UNKNOWN = "unknown"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PortabilityRisk(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKING = "blocking"


class ExecutionModel(str, Enum):
    """How the artifact is expected to be executed."""

    STATIC_INSTRUCTION = "static_instruction"
    ON_DEMAND_PROMPT = "on_demand_prompt"
    LIFECYCLE_HOOK = "lifecycle_hook"
    BACKGROUND_AGENT = "background_agent"
    INTERACTIVE_WORKFLOW = "interactive_workflow"
    CONFIG_SETTING = "config_setting"
    UNKNOWN = "unknown"


class WarningLevel(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class Warning(BaseModel):
    level: WarningLevel = WarningLevel.WARN
    code: str = ""
    message: str
    suggestion: str = ""


class ManualTodo(BaseModel):
    priority: str = "medium"  # high, medium, low
    description: str
    reason: str = ""
    affected_section: str = ""


class Trigger(BaseModel):
    """Describes when/how an artifact is activated."""

    event: str = ""  # e.g., "pre_commit", "on_command", "manual"
    pattern: str = ""  # e.g., glob or regex that triggers
    description: str = ""


class ExternalDependency(BaseModel):
    name: str
    kind: str = ""  # "shell_command", "service", "mcp_server", "api", "tool"
    required: bool = True
    portable: bool = False
    notes: str = ""


class Section(BaseModel):
    """A semantic section extracted from a document or config."""

    title: str = ""
    intent: SemanticIntent = SemanticIntent.UNKNOWN
    content: str = ""
    subsections: list[Section] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactIR(BaseModel):
    """The central Intermediate Representation for any agent artifact."""

    # Identity
    kind: ArtifactKind = ArtifactKind.UNKNOWN
    source_platform: Platform = Platform.UNKNOWN
    target_platform: Platform = Platform.UNKNOWN
    name: str = ""
    description: str = ""
    source_path: str = ""

    # Semantic analysis
    intent: SemanticIntent = SemanticIntent.UNKNOWN
    intents: list[SemanticIntent] = Field(
        default_factory=list,
        description="Multiple intents for composite artifacts like CLAUDE.md",
    )
    sections: list[Section] = Field(default_factory=list)

    # Behavioral
    triggers: list[Trigger] = Field(default_factory=list)
    instructions: str = ""
    constraints: list[str] = Field(default_factory=list)
    execution_model: ExecutionModel = ExecutionModel.UNKNOWN

    # Dependencies
    required_tools: list[str] = Field(default_factory=list)
    external_dependencies: list[ExternalDependency] = Field(default_factory=list)

    # Files
    files_included: list[str] = Field(default_factory=list)

    # Portability assessment
    portability_risk: PortabilityRisk = PortabilityRisk.LOW
    confidence: Confidence = Confidence.MEDIUM
    warnings: list[Warning] = Field(default_factory=list)
    manual_todos: list[ManualTodo] = Field(default_factory=list)

    # Raw
    raw_content: str = ""
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_warning(
        self,
        message: str,
        *,
        level: WarningLevel = WarningLevel.WARN,
        code: str = "",
        suggestion: str = "",
    ) -> None:
        self.warnings.append(
            Warning(level=level, code=code, message=message, suggestion=suggestion)
        )

    def add_todo(
        self,
        description: str,
        *,
        priority: str = "medium",
        reason: str = "",
        affected_section: str = "",
    ) -> None:
        self.manual_todos.append(
            ManualTodo(
                priority=priority,
                description=description,
                reason=reason,
                affected_section=affected_section,
            )
        )

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json())

    @classmethod
    def load(cls, path: Path) -> ArtifactIR:
        return cls.model_validate_json(path.read_text())
