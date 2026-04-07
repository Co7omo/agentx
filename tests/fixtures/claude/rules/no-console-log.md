# No console.log in production

- Never use `console.log` in production code
- Use the project's logger (`src/lib/logger.ts`) instead
- `console.log` is acceptable only in scripts under `tools/`
- Enforce via ESLint rule `no-console`
