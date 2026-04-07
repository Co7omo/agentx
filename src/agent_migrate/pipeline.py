"""Conversion pipeline.

Orchestrates the full detect -> parse -> classify -> map -> render -> report flow.
"""

from __future__ import annotations

from pathlib import Path

from agent_migrate.classifier import classify_artifact
from agent_migrate.detector import detect_artifact, detect_directory
from agent_migrate.ir import ArtifactIR, ArtifactKind, Confidence, Platform
from agent_migrate.mapper import map_artifact
from agent_migrate.parser import parse_artifact
from agent_migrate.renderer.render import RenderResult, render_artifact
from agent_migrate.reporter.report import ConversionReport


def inspect_path(path: Path) -> list[ArtifactIR]:
    """Inspect a path and return enriched IRs for all detected artifacts."""
    if path.is_dir():
        detected = detect_directory(path)
    else:
        detected = [detect_artifact(path)]

    results = []
    for ir in detected:
        if ir.kind != ArtifactKind.UNKNOWN:
            ir = parse_artifact(ir)
            ir = classify_artifact(ir)
            results.append(ir)
    return results


def convert_path(
    path: Path,
    source: Platform,
    target: Platform,
    output_dir: Path | None = None,
    dry_run: bool = False,
    strict: bool = False,
) -> tuple[list[RenderResult], ConversionReport]:
    """Convert artifacts from source to target platform."""
    artifacts = inspect_path(path)

    report = ConversionReport(
        source_platform=source.value,
        target_platform=target.value,
        items_detected=len(artifacts),
    )

    results: list[RenderResult] = []
    for ir in artifacts:
        ir.source_platform = source if ir.source_platform == Platform.UNKNOWN else ir.source_platform

        # Skip if already target platform
        if ir.source_platform == target:
            report.add_skipped(ir.source_path, "Already target platform")
            continue

        mapped = map_artifact(ir, target)

        if strict and mapped.confidence == Confidence.LOW:
            report.add_skipped(
                ir.source_path,
                f"Skipped in strict mode (confidence: {mapped.confidence.value})",
            )
            continue

        write_dir = None if dry_run else output_dir
        render_result = render_artifact(mapped, write_dir)
        results.append(render_result)
        report.add_result(mapped, render_result)

    return results, report


def plan_migration(path: Path, source: Platform, target: Platform) -> ConversionReport:
    """Generate a migration plan without performing any conversion."""
    artifacts = inspect_path(path)

    report = ConversionReport(
        source_platform=source.value,
        target_platform=target.value,
        items_detected=len(artifacts),
    )

    for ir in artifacts:
        ir.source_platform = source if ir.source_platform == Platform.UNKNOWN else ir.source_platform
        if ir.source_platform == target:
            report.add_skipped(ir.source_path, "Already target platform")
            continue

        mapped = map_artifact(ir, target)
        # Create a dummy render result for the plan
        dummy_result = RenderResult()
        dummy_result.ir = mapped
        report.add_result(mapped, dummy_result)

    return report
