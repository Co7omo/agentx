#!/usr/bin/env bash
# Pre-commit hook: run lint and type-check before committing

set -euo pipefail

echo "Running pre-commit checks..."

npm run lint --quiet
npm run typecheck

echo "Pre-commit checks passed."
