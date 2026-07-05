# agentx

Semantic transpiler for agent artifacts between **Claude** and **Codex** ecosystems.

`agentx` is not a naive syntax converter. It's a loss-aware migration tool that:

- Detects and classifies artifacts by **semantic intent**, not just filenames
- Converts to the **most idiomatic target construct** available
- Produces **explicit warnings** and **manual TODOs** when 1:1 equivalence doesn't exist
- Generates structured **reports** (JSON + Markdown) documenting every conversion decision
- Supports **bidirectional** conversion (Claude <-> Codex) with honest asymmetry

## Installation

```bash
pip install -e ".[dev]"
```

## Commands

### inspect

Analyze artifacts and report type, platform, portability, and dependencies.

```bash
agentx inspect ./CLAUDE.md
agentx inspect ./skills/review-pr
agentx inspect ./project --verbose
agentx inspect ./CLAUDE.md --json
```

### convert

Convert artifacts between ecosystems.

```bash
# Single file
agentx convert --from claude --to codex ./CLAUDE.md

# Entire project
agentx convert --from claude --to codex ./project --out ./converted

# Dry run (no files written)
agentx convert --from claude --to codex ./project --dry-run

# Strict mode (fail on low-confidence conversions)
agentx convert --from claude --to codex ./project --strict

# With reports
agentx convert --from claude --to codex ./project --report ./migration-report
```

### plan

Analyze a repository and produce a migration plan without converting anything.

```bash
agentx plan --from claude --to codex ./project
```

### diff-explain

Show what would be converted, reinterpreted, or lost.

```bash
agentx diff-explain --from codex --to claude ./AGENTS.md
```

### validate

Verify converted output for structural correctness.

```bash
agentx validate --target codex ./converted
```

### explain-ir

Show the intermediate representation of an artifact (useful for debugging).

```bash
agentx explain-ir ./CLAUDE.md
agentx explain-ir ./CLAUDE.md --json
```

## What it supports

### Claude artifacts

| Artifact | Detected | Parsed | Converted |
|---|---|---|---|
| `CLAUDE.md` | Yes | Sections, intents, constraints | -> `AGENTS.md` |
| Skills (`SKILL.md`) | Yes | Frontmatter, tools, steps | -> Codex skill |
| Custom commands | Yes | Frontmatter, instructions | -> Custom prompt / skill |
| Rules | Yes | Constraints, intent classification | -> AGENTS.md section / config / hook scaffold |
| Hooks | Yes | Lifecycle events, dependencies | -> Hook scaffold + warning |
| `settings.json` | Yes | `.claude/settings.json`, `.claude/settings.local.json` | -> Codex config |
| Config files | Yes | JSON/YAML/TOML | -> Codex config |

Artifacts are discovered both at the project root (`skills/`, `commands/`, `rules/`, `hooks/`, `prompts/`) and inside the `.claude/` and `.codex/` directories.

### Codex artifacts

| Artifact | Detected | Parsed | Converted |
|---|---|---|---|
| `AGENTS.md` | Yes | Sections, intents | -> `CLAUDE.md` |
| Agent TOML | Yes | Name, instructions, tools, triggers | -> Claude skill with agent persona |
| `config.toml` | Yes | Full TOML parsing | -> Claude settings fragment |
| Hooks | Yes | Events | -> Claude hook config fragment |

## Mapping philosophy

Mapping is by **semantic intent**, not by name:

| Claude concept | Codex concept | Confidence | Notes |
|---|---|---|---|
| `CLAUDE.md` | `AGENTS.md` | High | Near-direct mapping |
| Skill with `SKILL.md` | Skill file | Medium | Tool references may differ |
| Command (simple prompt) | Custom prompt | High | Direct |
| Command (multi-step) | Skill | Medium | Structural reinterpretation |
| Command (agent persona) | Subagent | Medium | Execution model differs |
| Rule (coding policy) | AGENTS.md section | High | Merge manually |
| Rule (enforcement) | Hook scaffold | Low | Requires manual implementation |
| Rule (config) | config.toml fragment | Medium | Key names may differ |
| Hook | Hook scaffold | Low-Medium | Lifecycle events may not map |
| Subagent | Agent TOML | Medium | Orchestration model differs |

## Confidence scoring

Every conversion has a confidence level:

- **high**: Near-direct mapping, semantics preserved
- **medium**: Good mapping with reinterpretation; review recommended
- **low**: Scaffold or conversion with significant semantic loss; manual work required

## Lossy conversion caveats

This tool is **honest about loss**:

1. **Round-trip is not lossless.** Converting Claude -> Codex -> Claude will not reproduce the original. The tool tells you what was lost.

2. **Tool references are adapted, not guaranteed.** Claude's `Read`, `Write`, `Edit`, `Bash`, `Grep`, `Glob` are mapped to Codex equivalents (`file_read`, `file_write`, etc.), but runtime behavior may differ.

3. **Hooks are the hardest to convert.** Lifecycle events differ between platforms. Hooks are rendered as scaffolds with the original logic commented out.

4. **Subagent orchestration differs fundamentally.** Claude uses the Agent tool for dispatch; Codex uses TOML-based agent definitions. The conversion preserves instructions and persona, but the execution model is a scaffold.

5. **MCP integrations are non-portable.** They are detected, flagged, and left as TODOs.

6. **Enforcement rules cannot be statically converted.** A rule that says "reject PRs without tests" needs runtime enforcement, not just documentation. These generate hook scaffolds with low confidence.

## Architecture

```
Input file/directory
        |
   [Detector] -- identifies kind + platform via filename, path, content patterns
        |
   [Parser] -- extracts structured content (sections, frontmatter, tools, deps)
        |
   [Classifier] -- refines semantic intent (coding policy? workflow? agent persona?)
        |
   [Mapper] -- transforms IR to target semantics, annotates losses
        |
   [Renderer] -- generates idiomatic target files
        |
   [Reporter] -- produces JSON + Markdown reports
```

The central data structure is the **Intermediate Representation (IR)** — a typed, serializable schema that captures both structural content and semantic intent.

## Project structure

```
src/agent_migrate/
  ir/           # IR schema (Pydantic models)
  detector/     # Artifact detection by filename, path, content
  parser/       # Content parsing and enrichment
  classifier/   # Semantic intent classification
  mapper/       # Source-to-target mapping with loss tracking
  renderer/     # Idiomatic output generation
  reporter/     # JSON + Markdown report generation
  cli/          # Typer CLI
  plugins/      # Plugin system for future ecosystems
  pipeline.py   # Orchestration (detect -> parse -> classify -> map -> render -> report)
tests/
  fixtures/     # Realistic test fixtures (Claude + Codex projects)
  unit/         # Unit + integration tests
```

## Running tests

```bash
pytest
pytest -v                  # verbose
pytest --cov=agent_migrate # with coverage
```

## Extending

The plugin system (`src/agent_migrate/plugins/`) supports adding new ecosystems. Registered plugins are consulted **before** the built-in logic: detector plugins get first chance at classifying a path, and a mapper plugin registered for a `(source, target)` pair overrides the built-in mapping for that direction.

```python
from agent_migrate.ir import ArtifactIR, ArtifactKind, Platform
from agent_migrate.plugins import register_detector, register_mapper

class GeminiDetector:
    def detect(self, path: str) -> ArtifactIR | None:
        if path.endswith("GEMINI.md"):
            return ArtifactIR(kind=ArtifactKind.INSTRUCTION_DOC, name="GEMINI", source_path=path)
        return None

register_detector("gemini", GeminiDetector())
```

## Limitations

- **Codex ecosystem knowledge is based on publicly documented patterns** (AGENTS.md, TOML agents, config.toml). Real Codex internals may differ.
- **No runtime validation.** The tool checks structural correctness, not whether the converted artifacts will actually work.
- **Single-pass conversion.** No iterative refinement or AI-assisted rewriting.
- **No merge logic.** When multiple rules should be merged into one AGENTS.md, the tool generates fragments. Merging is manual.
- **Limited frontmatter support.** Only YAML frontmatter in markdown is parsed; other metadata formats may not be detected.
