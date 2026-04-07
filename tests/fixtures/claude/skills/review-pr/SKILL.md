---
name: review-pr
description: Review a pull request for code quality and correctness
---

# PR Review Skill

Review the given pull request thoroughly.

## Steps

1. Read all changed files using the `Read` tool
2. Check for TypeScript errors
3. Verify test coverage for new code
4. Check for security issues (SQL injection, XSS, etc.)
5. Verify API documentation is updated
6. Check that migration files exist if schema changed

## Output

Provide a structured review with:
- Summary of changes
- Issues found (critical, warning, suggestion)
- Approval recommendation

## Constraints

- Do not approve PRs with failing tests
- Flag any use of `any` type
- Flag console.log in production code
