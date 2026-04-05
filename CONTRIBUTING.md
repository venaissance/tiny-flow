# Contributing to TinyFlow

Thank you for your interest in contributing to TinyFlow! This guide will help you get started.

## Reporting Bugs

1. Search [existing issues](https://github.com/venaissance/tiny-flow/issues) to avoid duplicates.
2. Open a new issue using the **Bug Report** template.
3. Include: steps to reproduce, expected vs actual behavior, and your environment (OS, Python/Node version).

## Suggesting Features

1. Open a new issue using the **Feature Request** template.
2. Describe the problem, your proposed solution, and any alternatives you considered.

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 20+ with pnpm
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- At least one LLM API key (GLM, OpenAI, or Anthropic)

### Backend

```bash
cd backend
cp .env.example .env       # Add your API key(s)
uv sync --extra dev        # Install all dependencies including dev
make dev                   # Start dev server at http://localhost:8000
```

### Frontend

```bash
cd frontend
pnpm install               # Install dependencies
pnpm dev                   # Start dev server at http://localhost:3000
```

## Submitting Pull Requests

1. Fork the repository and create a branch from `main`:
   ```bash
   git checkout -b feat/your-feature
   ```
2. Make your changes with clear, focused commits.
3. Add or update tests as appropriate.
4. Ensure all checks pass before submitting:
   ```bash
   # Backend
   cd backend && make test

   # Frontend
   cd frontend && pnpm check && pnpm test:run
   ```
5. Open a Pull Request using the PR template. Link any related issues.

## Code Style

### Python (backend)

- Formatter & linter: [Ruff](https://docs.astral.sh/ruff/)
- Line length: 120 characters
- Run locally: `ruff check --fix . && ruff format .`

### TypeScript (frontend)

- Linter: ESLint
- Formatter: Prettier
- Run locally: `pnpm check`

## Commit Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short description>

Types: feat, fix, docs, test, refactor, chore, ci
```

Examples:
- `feat: add memory decay configuration`
- `fix: resolve SSE reconnection on thread switch`
- `docs: update architecture diagram`

## Testing Requirements

- All existing tests must pass.
- New features should include tests. Aim for meaningful coverage, not just line count.
- Backend: `pytest` in `backend/tests/`
- Frontend: `vitest` in `frontend/src/` and Playwright in `frontend/e2e/`

## Code of Conduct

Be respectful, constructive, and collaborative. We are all here to build something useful together.
