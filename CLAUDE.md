# CLAUDE.md

This file provides guidance to AI coding assistants working in this repository.

## Project Overview

**Readaria** is a mobile-first, self-hostable RSS knowledge management app. It aggregates feeds, processes articles with AI, and provides reading, text-to-speech, and AI podcast features through an installable Vue PWA.

The public hosted examples are `https://readaria.com` and `https://api.marlinworks.xyz`. Self-hosted deployments should use their own domains and configuration.

## Tech Stack

- **Frontend:** Vue 3 Composition API, Vite, Vant 4, Pinia, Vue Router, Axios, vite-plugin-pwa
- **Backend:** FastAPI, PostgreSQL, Redis, APScheduler, feedparser
- **AI and audio:** OpenAI-compatible APIs, Azure/OpenAI/Google TTS, HTML5 Audio, Media Session API
- **Testing:** pytest for backend tests, Playwright for end-to-end tests
- **Packaging:** Docker and Docker Compose

## Repository Structure

- `backend/api/`: FastAPI application and routers
- `backend/fetcher/`: feed fetching, parsing, and rate limiting
- `backend/nlp/`: summarization and speech providers
- `backend/services/`: podcast, cache, subscription, and playback services
- `backend/storage/`: database access, schema, and migrations
- `core/config/`: application settings
- `frontend/src/`: Vue views, components, stores, and composables
- `frontend/tests/`: Playwright end-to-end tests
- `tests/`: backend unit and integration tests
- `scripts/`: reusable maintenance and development utilities
- `docs/`: project documentation

## Local Setup

```bash
cp .env.example .env
python -m venv venv
source venv/bin/activate
pip install -r requirements.test.txt
```

Never commit `.env` or real credentials. Keep example configuration values as obvious placeholders. Validate required PostgreSQL, Redis, and optional RSS services before debugging dependent features.

Useful checks:

```bash
python -c "from backend.api.main import app"
cd frontend && npm ci && npm run build
```

## Tests

```bash
make test-quick   # Fast mocked unit tests
make test-local   # Local Docker-backed test environment
make test-watch   # Re-run tests when files change
make test-cov     # Coverage report
make test-e2e     # Playwright tests; requires a running application
```

Test markers are defined in `pytest.ini`:

- `unit`: mocked tests without external services
- `integration`: tests requiring local Docker services
- `external`: tests requiring third-party services
- `e2e`: end-to-end tests

See `docs/TESTING_GUIDE.md` for the complete testing workflow. Run `make test-quick` before submitting small changes and the appropriate broader suite for cross-stack changes.

## Development Conventions

- Follow PEP 8: four spaces, `snake_case`, and type hints where useful.
- Use PascalCase for Vue components, kebab-case for component files, and Pinia for shared state.
- Keep existing API paths stable; prefer `/api/v1/...` for new endpoints.
- Add new API endpoints under `backend/api/routes/` using the router factory pattern rather than expanding `backend/api/main.py`.
- Keep configurable values in `core/config/settings.py` and expose safe examples in `.env.example`.
- Add production Python dependencies to `requirements.prod.txt` and test-only dependencies to `requirements.test.txt`.
- Put project documentation in `docs/`, reusable scripts in `scripts/`, and tests in `tests/` or `frontend/tests/`.

## Cross-Stack Changes

For API contract, function signature, database schema, or multi-file changes:

1. Search for every reference before editing.
2. Update parallel implementations, composables, services, fixtures, and tests together.
3. Check both backend and frontend error handling.
4. Run backend import checks, relevant tests, and the frontend build.
5. Verify media elements set the appropriate CORS attributes when changing media delivery.

Avoid silently relying on `.get()` for newly introduced database columns; validate the actual schema and selected fields instead.
