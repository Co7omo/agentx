"""Shared test fixtures."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
CLAUDE_FIXTURES = FIXTURES / "claude"
CODEX_FIXTURES = FIXTURES / "codex"


@pytest.fixture
def claude_fixtures():
    return CLAUDE_FIXTURES


@pytest.fixture
def codex_fixtures():
    return CODEX_FIXTURES


@pytest.fixture
def claude_md():
    return CLAUDE_FIXTURES / "CLAUDE.md"


@pytest.fixture
def agents_md():
    return CODEX_FIXTURES / "AGENTS.md"


@pytest.fixture
def claude_skill_dir():
    return CLAUDE_FIXTURES / "skills" / "review-pr"


@pytest.fixture
def codex_agent_toml():
    return CODEX_FIXTURES / ".codex" / "agents" / "reviewer.toml"


@pytest.fixture
def codex_config_toml():
    return CODEX_FIXTURES / ".codex" / "config.toml"


@pytest.fixture
def claude_command():
    return CLAUDE_FIXTURES / "commands" / "fix-lint.md"


@pytest.fixture
def claude_prompt_command():
    return CLAUDE_FIXTURES / "commands" / "explain-code.md"


@pytest.fixture
def claude_rule():
    return CLAUDE_FIXTURES / "rules" / "no-console-log.md"


@pytest.fixture
def claude_hook():
    return CLAUDE_FIXTURES / "hooks" / "pre-commit.sh"


@pytest.fixture
def tmp_output(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    return out
