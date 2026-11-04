# Contributing to Readaria

Thank you for your interest in improving Readaria. Bug reports, feature ideas, documentation fixes, and pull requests are welcome.

## Before You Start

- Search existing issues before opening a duplicate.
- Use an issue to discuss substantial behavior or architecture changes before implementing them.
- Keep pull requests focused and explain what changed, why, and how you tested it.
- Do not report security vulnerabilities in public issues; use the process in [SECURITY.md](SECURITY.md).

## Local Setup

```bash
cp .env.example .env
make test-quick
```

`make test-quick` creates `venv/` when needed, installs `requirements.test.txt`, and runs the mocked unit-test suite. Real AI, TTS, database, or RSS provider credentials are not required for these tests. `tests/conftest.py` supplies dummy values for required test settings; copying `.env.example` first is the recommended setup for a new checkout.

For frontend changes, also run the relevant checks:

```bash
cd frontend
npm ci
npm run build
node --test tests/unit/*.test.mjs
```

See [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md) for Docker-backed tests and Playwright E2E tests.

## Pull Request Checklist

- `make test-quick` passes.
- Relevant frontend or broader integration tests pass for the area you changed.
- New configuration is documented in `.env.example` without real credentials.
- API, schema, and cross-stack call sites are updated together.
- User-facing documentation is updated when behavior changes.

By contributing, you agree that your contribution is licensed under the project's AGPL-3.0 license.

## Response Expectations

Readaria is maintained as a side project. Reviews and issue responses may take time; there is no guaranteed service-level agreement. Clear reproduction steps, focused diffs, and test results make review easier.
