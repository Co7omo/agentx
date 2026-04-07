# Project: data-pipeline

Python data processing pipeline using Apache Beam.

## Setup

```bash
pip install -e ".[dev]"
pytest
```

## Coding Standards

- Follow PEP 8
- Type hints required on all public functions
- Use dataclasses for data structures
- No mutable default arguments
- Docstrings on all public modules, classes, and functions

## Testing

- All pipeline transforms must have unit tests
- Use `TestPipeline` for Beam transform tests
- Integration tests go in `tests/integration/`
- Minimum 80% coverage on new code

## Architecture

- Transforms in `src/transforms/`
- IO connectors in `src/io/`
- Schemas in `src/schemas/`
- Shared utilities in `src/utils/`
