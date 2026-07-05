"""Plugin system for additional ecosystem support.

Registered plugins are consulted by the pipeline *before* the built-in
logic: detector plugins get first chance at classifying a path, and a
mapper plugin registered for a (source, target) pair overrides the
built-in mapping for that direction.

To add a new ecosystem:
1. Create a module (e.g., plugins/openai.py)
2. Implement the DetectorPlugin / MapperPlugin protocols
3. Register instances via register_detector / register_mapper
"""

from __future__ import annotations

from typing import Protocol

from agent_migrate.ir import ArtifactIR, Platform


class DetectorPlugin(Protocol):
    def detect(self, path: str) -> ArtifactIR | None:
        """Return an IR for the path, or None if not recognized."""
        ...


class MapperPlugin(Protocol):
    def map(self, ir: ArtifactIR, target: Platform) -> ArtifactIR:
        """Map an IR to the target platform."""
        ...


_detector_registry: dict[str, DetectorPlugin] = {}
_mapper_registry: dict[tuple[Platform, Platform], MapperPlugin] = {}


def register_detector(name: str, plugin: DetectorPlugin) -> None:
    _detector_registry[name] = plugin


def register_mapper(source: Platform, target: Platform, plugin: MapperPlugin) -> None:
    _mapper_registry[(source, target)] = plugin


def get_detector(name: str) -> DetectorPlugin | None:
    return _detector_registry.get(name)


def get_mapper(source: Platform, target: Platform) -> MapperPlugin | None:
    return _mapper_registry.get((source, target))


def detect_with_plugins(path: str) -> ArtifactIR | None:
    """Run all registered detector plugins; first non-None result wins."""
    for plugin in _detector_registry.values():
        result = plugin.detect(path)
        if result is not None:
            return result
    return None


def clear_registries() -> None:
    """Remove all registered plugins (mainly for tests)."""
    _detector_registry.clear()
    _mapper_registry.clear()
