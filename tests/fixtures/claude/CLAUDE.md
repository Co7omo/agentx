# Project: webapp-api

This is a Node.js REST API using Express and TypeScript.

## Build & Test

```bash
npm install
npm run build
npm test
npm run lint
```

## Code Style

- Use TypeScript strict mode
- Prefer `const` over `let`
- Use named exports, not default exports
- All API handlers must validate input with zod
- Never use `any` type

## Dependencies

- Do not add new dependencies without team approval
- Prefer stdlib over third-party when possible
- Pin exact versions in package.json

## Review Checklist

Before submitting a PR:

- [ ] All tests pass
- [ ] No TypeScript errors
- [ ] API endpoints documented in OpenAPI spec
- [ ] Migration files included if schema changed
- [ ] No console.log left in production code

## Architecture Notes

- Controllers in `src/controllers/`
- Services in `src/services/`
- Use the `Result<T, E>` pattern for error handling
- Database access only through repository layer
