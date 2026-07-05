"""CLI entry point for agent-migrate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from agent_migrate import __version__
from agent_migrate.ir import ArtifactIR, Confidence, Platform
from agent_migrate.pipeline import convert_path, inspect_path, plan_migration
from agent_migrate.reporter.report import (
    ConversionReport,
    generate_json_report,
    generate_markdown_report,
)

app = typer.Typer(
    name="agentx",
    help="Semantic transpiler for agent artifacts between Claude and Codex ecosystems.",
    no_args_is_help=True,
)

console = Console()
err_console = Console(stderr=True)


def _parse_platform(value: str) -> Platform:
    try:
        return Platform(value.lower())
    except ValueError:
        err_console.print(f"[red]Unknown platform:[/red] {value}. Use 'claude' or 'codex'.")
        raise typer.Exit(1) from None


def _version_callback(value: bool):
    if value:
        console.print(f"agentx {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        False, "--version", "-V", help="Show version", callback=_version_callback, is_eager=True
    ),
):
    pass


@app.command()
def inspect(
    path: Path = typer.Argument(..., help="File or directory to inspect"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Analyze artifacts and report type, platform, portability, and dependencies."""
    if not path.exists():
        err_console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(1)

    artifacts = inspect_path(path)

    if not artifacts:
        console.print("[yellow]No recognizable artifacts found.[/yellow]")
        raise typer.Exit(0)

    if json_output:
        data = [json.loads(ir.to_json()) for ir in artifacts]
        console.print_json(json.dumps(data, indent=2))
        return

    for ir in artifacts:
        _print_artifact_summary(ir, verbose)


@app.command()
def convert(
    path: Path = typer.Argument(..., help="File or directory to convert"),
    source: str = typer.Option(..., "--from", help="Source platform (claude/codex)"),
    target: str = typer.Option(..., "--to", help="Target platform (claude/codex)"),
    output: Optional[Path] = typer.Option(None, "--out", "-o", help="Output directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
    strict: bool = typer.Option(False, "--strict", help="Fail on low-confidence conversions"),
    json_output: bool = typer.Option(False, "--json", help="Output report as JSON"),
    report_path: Optional[Path] = typer.Option(None, "--report", help="Save report to file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Convert artifacts between Claude and Codex ecosystems."""
    if not path.exists():
        err_console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(1)

    src_platform = _parse_platform(source)
    tgt_platform = _parse_platform(target)

    if output is None:
        output = Path(f"./converted-{tgt_platform.value}")

    results, report = convert_path(
        path, src_platform, tgt_platform,
        output_dir=output, dry_run=dry_run, strict=strict,
    )

    if json_output:
        console.print_json(generate_json_report(report))
    else:
        _print_conversion_report(report, dry_run, verbose)

        if not dry_run and results:
            console.print(f"\n[green]Output written to:[/green] {output}")

    if report_path:
        _save_reports(report, report_path)

    # Exit code based on strictness
    if strict and report.incompatibilities:
        raise typer.Exit(2)


@app.command()
def plan(
    path: Path = typer.Argument(..., help="Repository root to analyze"),
    source: str = typer.Option(..., "--from", help="Source platform"),
    target: str = typer.Option(..., "--to", help="Target platform"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    report_path: Optional[Path] = typer.Option(None, "--report", help="Save report"),
):
    """Analyze a repository and produce a migration plan."""
    if not path.exists():
        err_console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(1)

    src_platform = _parse_platform(source)
    tgt_platform = _parse_platform(target)

    report = plan_migration(path, src_platform, tgt_platform)

    if json_output:
        console.print_json(generate_json_report(report))
    else:
        _print_plan(report)

    if report_path:
        _save_reports(report, report_path)


@app.command(name="diff-explain")
def diff_explain(
    path: Path = typer.Argument(..., help="File or directory to analyze"),
    source: str = typer.Option(..., "--from", help="Source platform"),
    target: str = typer.Option(..., "--to", help="Target platform"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Show what would be converted, reinterpreted, or lost."""
    if not path.exists():
        err_console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(1)

    src_platform = _parse_platform(source)
    tgt_platform = _parse_platform(target)

    results, report = convert_path(path, src_platform, tgt_platform, dry_run=True)

    if json_output:
        console.print_json(generate_json_report(report))
        return

    for result in results:
        ir = result.ir
        if not ir:
            continue

        panel_content = []
        panel_content.append(f"[bold]Kind:[/bold] {ir.kind.value}")
        panel_content.append(f"[bold]Intent:[/bold] {ir.intent.value}")
        panel_content.append(f"[bold]Confidence:[/bold] {_confidence_color(ir.confidence)}")

        if result.files:
            panel_content.append("\n[bold]Would generate:[/bold]")
            for f in result.files:
                panel_content.append(f"  -> {f.path} ({f.description})")

        if ir.warnings:
            panel_content.append("\n[bold]Warnings:[/bold]")
            for w in ir.warnings:
                color = {"info": "blue", "warn": "yellow", "error": "red"}.get(w.level.value, "white")
                panel_content.append(f"  [{color}][{w.level.value}][/{color}] {w.message}")
                if w.suggestion:
                    panel_content.append(f"    [dim]{w.suggestion}[/dim]")

        if ir.manual_todos:
            panel_content.append("\n[bold]Manual TODOs:[/bold]")
            for t in ir.manual_todos:
                panel_content.append(f"  [{t.priority}] {t.description}")

        console.print(Panel(
            "\n".join(panel_content),
            title=f"[bold]{ir.source_path}[/bold]",
            border_style="cyan",
        ))


@app.command()
def validate(
    path: Path = typer.Argument(..., help="Output directory to validate"),
    target: str = typer.Option(..., "--target", help="Expected target platform"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Validate converted output for correctness."""
    if not path.exists():
        err_console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(1)

    tgt = _parse_platform(target)
    issues = _validate_output(path, tgt)

    if json_output:
        console.print_json(json.dumps(issues, indent=2))
        return

    if not issues:
        console.print("[green]Validation passed. No issues found.[/green]")
        return

    for issue in issues:
        color = {"error": "red", "warning": "yellow", "info": "blue"}.get(issue["level"], "white")
        console.print(f"  [{color}][{issue['level']}][/{color}] {issue['path']}: {issue['message']}")

    errors = [i for i in issues if i["level"] == "error"]
    if errors:
        raise typer.Exit(1)


@app.command(name="explain-ir")
def explain_ir(
    path: Path = typer.Argument(..., help="File to inspect"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Show the intermediate representation of an artifact."""
    if not path.exists():
        err_console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(1)

    artifacts = inspect_path(path)
    if not artifacts:
        console.print("[yellow]No recognizable artifacts.[/yellow]")
        raise typer.Exit(0)

    for ir in artifacts:
        if json_output:
            console.print_json(ir.to_json())
        else:
            _print_ir_detail(ir)


# --- Display helpers ---

def _print_artifact_summary(ir: ArtifactIR, verbose: bool = False) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Path", ir.source_path)
    table.add_row("Kind", ir.kind.value)
    table.add_row("Platform", ir.source_platform.value)
    table.add_row("Intent", ir.intent.value)
    table.add_row("Confidence", _confidence_color(ir.confidence))
    table.add_row("Risk", ir.portability_risk.value)

    if ir.required_tools:
        table.add_row("Tools", ", ".join(ir.required_tools))
    if ir.external_dependencies:
        deps = ", ".join(d.name for d in ir.external_dependencies)
        table.add_row("Dependencies", deps)

    if verbose:
        if ir.intents:
            table.add_row("All intents", ", ".join(i.value for i in ir.intents))
        if ir.sections:
            table.add_row("Sections", str(len(ir.sections)))
        if ir.constraints:
            table.add_row("Constraints", str(len(ir.constraints)))

    if ir.warnings:
        table.add_row("Warnings", str(len(ir.warnings)))

    console.print(Panel(table, title=f"[bold]{ir.name}[/bold]", border_style="cyan"))


def _print_conversion_report(report: ConversionReport, dry_run: bool, verbose: bool) -> None:
    prefix = "[DRY RUN] " if dry_run else ""

    console.print(f"\n[bold]{prefix}Conversion Report[/bold]")
    console.print(f"  {report.source_platform} -> {report.target_platform}")
    console.print(
        f"  Detected: {report.items_detected}  "
        f"Converted: {report.items_converted}  Skipped: {report.items_skipped}"
    )

    if report.confidence_summary:
        parts = []
        for level, count in report.confidence_summary.items():
            if count > 0:
                parts.append(f"{level}: {count}")
        console.print(f"  Confidence: {', '.join(parts)}")

    if report.warnings:
        console.print(f"\n[yellow]Warnings ({len(report.warnings)}):[/yellow]")
        for w in report.warnings[:10]:
            console.print(f"  [{w['level']}] {w['source']}: {w['message']}")
        if len(report.warnings) > 10:
            console.print(f"  ... and {len(report.warnings) - 10} more")

    if report.manual_actions:
        console.print(f"\n[cyan]Manual actions ({len(report.manual_actions)}):[/cyan]")
        for a in report.manual_actions[:5]:
            console.print(f"  [{a['priority']}] {a['description']}")
        if len(report.manual_actions) > 5:
            console.print(f"  ... and {len(report.manual_actions) - 5} more")


def _print_plan(report: ConversionReport) -> None:
    console.print(Panel(
        f"Migration plan: [bold]{report.source_platform}[/bold] -> [bold]{report.target_platform}[/bold]\n"
        f"Artifacts detected: {report.items_detected}",
        title="Migration Plan",
        border_style="green",
    ))

    if report.converted:
        console.print("\n[bold]Proposed conversions:[/bold]")
        table = Table()
        table.add_column("Source", style="cyan")
        table.add_column("Kind")
        table.add_column("Confidence")
        table.add_column("Warnings")
        table.add_column("TODOs")

        for item in report.converted:
            table.add_row(
                item.source_path,
                item.kind,
                _confidence_color_str(item.confidence),
                str(len(item.warnings)),
                str(len(item.manual_todos)),
            )
        console.print(table)

    if report.skipped:
        console.print("\n[yellow]Skipped:[/yellow]")
        for s in report.skipped:
            console.print(f"  - {s['path']}: {s['reason']}")

    if report.manual_actions:
        console.print("\n[cyan]Required manual actions:[/cyan]")
        for i, a in enumerate(report.manual_actions, 1):
            console.print(f"  {i}. [{a['priority']}] {a['description']}")


def _print_ir_detail(ir: ArtifactIR) -> None:
    tree = Tree(f"[bold]{ir.name}[/bold] ({ir.kind.value})")
    tree.add(f"Platform: {ir.source_platform.value}")
    tree.add(f"Intent: {ir.intent.value}")
    tree.add(f"Confidence: {_confidence_color(ir.confidence)}")
    tree.add(f"Execution model: {ir.execution_model.value}")
    tree.add(f"Portability risk: {ir.portability_risk.value}")

    if ir.sections:
        sec_tree = tree.add(f"Sections ({len(ir.sections)})")
        for sec in ir.sections:
            sec_tree.add(f"{sec.title or '(untitled)'} [{sec.intent.value}]")

    if ir.constraints:
        c_tree = tree.add(f"Constraints ({len(ir.constraints)})")
        for c in ir.constraints[:5]:
            c_tree.add(c[:80])

    if ir.external_dependencies:
        d_tree = tree.add(f"Dependencies ({len(ir.external_dependencies)})")
        for d in ir.external_dependencies:
            portable = "portable" if d.portable else "non-portable"
            d_tree.add(f"{d.name} ({d.kind}, {portable})")

    if ir.warnings:
        w_tree = tree.add(f"[yellow]Warnings ({len(ir.warnings)})[/yellow]")
        for w in ir.warnings:
            w_tree.add(f"[{w.level.value}] {w.message}")

    console.print(tree)


def _confidence_color(conf: Confidence) -> str:
    colors = {Confidence.HIGH: "green", Confidence.MEDIUM: "yellow", Confidence.LOW: "red"}
    return f"[{colors[conf]}]{conf.value}[/{colors[conf]}]"


def _confidence_color_str(conf_str: str) -> str:
    colors = {"high": "green", "medium": "yellow", "low": "red"}
    color = colors.get(conf_str, "white")
    return f"[{color}]{conf_str}[/{color}]"


def _validate_output(path: Path, target: Platform) -> list[dict]:
    """Validate output directory structure and content."""
    issues: list[dict] = []

    if target == Platform.CODEX:
        # Check for AGENTS.md
        agents_md = path / "AGENTS.md"
        if not agents_md.exists():
            # Not necessarily an error - might be a partial conversion
            pass

        # Check TOML files are valid
        for toml_file in path.rglob("*.toml"):
            try:
                import tomli
                tomli.loads(toml_file.read_text())
            except Exception as e:
                issues.append({
                    "level": "error",
                    "path": str(toml_file),
                    "message": f"Invalid TOML: {e}",
                })

    elif target == Platform.CLAUDE:
        # Check for valid skill directories
        skills_dir = path / "skills"
        if skills_dir.exists():
            for skill_dir in skills_dir.iterdir():
                if skill_dir.is_dir() and not (skill_dir / "SKILL.md").exists():
                    issues.append({
                        "level": "warning",
                        "path": str(skill_dir),
                        "message": "Skill directory missing SKILL.md",
                    })

    # Check for empty files
    for f in path.rglob("*"):
        if f.is_file() and f.stat().st_size == 0:
            issues.append({
                "level": "warning",
                "path": str(f),
                "message": "Empty file",
            })

    # Check JSON files are valid
    for json_file in path.rglob("*.json"):
        try:
            json.loads(json_file.read_text())
        except Exception as e:
            issues.append({
                "level": "error",
                "path": str(json_file),
                "message": f"Invalid JSON: {e}",
            })

    return issues


def _save_reports(report: ConversionReport, path: Path) -> None:
    """Save both JSON and Markdown reports."""
    path.parent.mkdir(parents=True, exist_ok=True)

    json_path = path.with_suffix(".json")
    json_path.write_text(generate_json_report(report))

    md_path = path.with_suffix(".md")
    md_path.write_text(generate_markdown_report(report))

    console.print(f"[dim]Reports saved: {json_path}, {md_path}[/dim]")


if __name__ == "__main__":
    app()
