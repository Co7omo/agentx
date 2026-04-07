"""Plugin system for future ecosystem support.

To add a new ecosystem:
1. Create a module in this package (e.g., plugins/openai.py)
2. Implement detect, parse, map, and render functions
3. Register them via the registry
"""

from __future__ import annotations

from typing import Callable, Protocol

from agent_migrate.ir import ArtifactIR, Platform


class DetectorPlugin(Protocol):
    def detect(self, path: str) -> ArtifactIR | None: ...


class MapperPlugin(Protocol):
    def map(self, ir: ArtifactIR, target: Platform) -> ArtifactIR: ...


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
