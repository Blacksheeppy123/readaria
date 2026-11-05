# Self-Hosting Readaria

This guide covers a small Docker Compose deployment on a machine you control. You are responsible for host security, HTTPS, provider accounts, and backups.

## Prerequisites

- Docker Engine with Docker Compose v2 (`docker compose version`)
- A machine with enough disk space for PostgreSQL data and generated audio
- Optional: provider credentials for AI summaries, server-side TTS, and podcasts

## Quick Start

```bash
git clone https://github.com/Blacksheeppy123/readaria.git
cd readaria
cp .env.example .env
```

Edit `.env` before starting the application:

1. Replace `POSTGRES_PASSWORD` with a unique password.
2. Set `SECRET_KEY` to a random value of at least 32 characters.
3. Set `JWT_SECRET_KEY` to a different random value.
4. Add real provider credentials only if you plan to use AI features or server-side TTS.

Then start the services:

```bash
docker compose up -d
docker compose ps
```

Open `http://localhost:8000` for the Readaria PWA. The API image serves the built Vue frontend and supports refreshing history-mode routes; no separate frontend service is required. The backend API documentation is at `http://localhost:8000/docs` by default. For internet access, put the services behind a correctly configured HTTPS reverse proxy, update `CORS_ALLOWED_ORIGINS`, and restrict direct access to database and Redis ports. Do not expose PostgreSQL or Redis to the public internet.

RSS reading works without an AI provider account. Article narration can fall back to the browser's Web Speech implementation where supported. AI summaries, podcast generation/Q&A, and server-side audio require valid provider configuration.

## Configuration

The complete example is in [`.env.example`](../.env.example). Restart or recreate services after changing configuration.

| Variable | Purpose |
| --- | --- |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB` | PostgreSQL connection and database name |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | PostgreSQL credentials; use a unique password |
| `POSTGRES_SSLMODE` | PostgreSQL SSL mode; adjust for your network and database setup |
| `API_PORT` | Host port mapped to the API container (default `8000`); change it if the port is already in use |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` | Redis connection |
| `REDIS_PASSWORD` | Redis password, if enabled |
| `SECRET_KEY` | Application signing secret; must be at least 32 characters |
| `JWT_SECRET_KEY` | Secret used for login tokens; use a strong independent value |
| `CORS_ALLOWED_ORIGINS` | Comma-separated frontend origins allowed to call the API |
| `OPENAI_API_KEY` | Credential for the OpenAI-compatible chat API; the placeholder is sufficient only for non-AI use |
| `OPENAI_BASE_URL`, `OPENAI_MODEL` | Chat API endpoint and default summary model |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | Optional fallback for supported rate-limit/quota failures |
| `TTS_PROVIDER` | `google`, `azure`, `azure_speech`, or `openai` |
| `GOOGLE_CLOUD_*` | Google Cloud TTS credentials and voice settings when `TTS_PROVIDER=google` |
| `AZURE_OPENAI_TTS_*` | Azure OpenAI TTS endpoint, credential, and deployment when `TTS_PROVIDER=azure` |
| `AZURE_SPEECH_*` | Azure Speech credential, region, and voice when `TTS_PROVIDER=azure_speech` |
| `OPENAI_TTS_*` | OpenAI audio model, voice, and format when `TTS_PROVIDER=openai` |
| `TTS_CACHE_DIR`, `TTS_CACHE_MAX_SIZE_GB`, `TTS_CACHE_EXPIRY_DAYS` | Article-audio cache location and retention |
| `PODCAST_ENABLED` | Enables the scheduled podcast job; manual generation still needs working LLM and TTS providers |
| `PODCAST_GENERATION_HOUR`, `PODCAST_GENERATION_MINUTE` | Daily podcast schedule in UTC |
| `PODCAST_MAX_ARTICLES` | Maximum articles selected per generated podcast |
| `PODCAST_AUDIO_CACHE_DIR` | Generated podcast-audio storage path |
| `RSSHUB_ALLOWED_HOSTS` | Host allowlist used when validating RSSHub URLs |
| `WECHAT_COOKIE` | Optional WeChat cookie; avoid committing or sharing it |
| `WECHAT2RSS_BASE_URL` | Optional URL rewrite target for separately operated wechat2rss feeds |
| `SENTRY_DSN` | Optional error reporting; leave empty to disable |
| `LOG_LEVEL` | Backend logging verbosity |

### AI and audio notes

- AI summaries and podcast scripts use the OpenAI-compatible chat client. Some podcast and Q&A model names are fixed in the service code, so an arbitrary compatible endpoint is not guaranteed to work unchanged.
- Podcast audio also requires one of the server-side TTS providers. Browser Web Speech fallback does not generate podcast files.
- Cloud providers may charge for both LLM and TTS usage. Set and monitor provider-side budgets as appropriate.
- RSSHub routes are fetched through public instances. Their availability and route requirements are outside Readaria's control.
- wechat2rss is an independent paid third-party service. It is optional, not bundled, and not affiliated with Readaria.

## Updating

Back up PostgreSQL before upgrading. Review the changes between your current revision and the target revision, especially schema and configuration changes.

From the repository directory:

```bash
git pull --ff-only
```

If your Compose file references prebuilt images:

```bash
docker compose pull
docker compose up -d
```

If it builds images from the local checkout:

```bash
docker compose build --pull
docker compose up -d
```

Then verify the deployment:

```bash
docker compose ps
docker compose logs --tail=200 api
curl --fail http://localhost:8000/docs >/dev/null
```

Apply any documented schema migration required by the release before relying on the updated application. Keep `.env` and persistent volumes; do not use `down -v` during an upgrade because it deletes volume data.

## Backups

### PostgreSQL

Create a plain SQL backup using the database credentials already present in the PostgreSQL container:

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "readaria-$(date +%F).sql"
```

Store backups separately from the host, protect them as user data, and test restoration periodically. To restore into an existing database after stopping application writes:

```bash
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"' < "readaria-YYYY-MM-DD.sql"
```

Restoration over existing objects can produce conflicts. For a full disaster recovery, restore into a fresh database following your PostgreSQL recovery procedure.

### Audio and other files

Back up the persistent audio/cache volumes or host directories if regenerated audio is valuable to you. Generated audio can usually be recreated at additional provider cost; PostgreSQL contains the application state that cannot be reconstructed from feeds alone.

## Troubleshooting

Check service state and recent logs:

```bash
docker compose ps
docker compose logs --tail=200 api
docker compose logs --tail=200 postgres
docker compose logs -f api
```

Check PostgreSQL and Redis from inside their containers:

```bash
docker compose exec postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose exec redis redis-cli ping
```

Common checks:

- **API fails during configuration loading:** confirm `.env` exists, required values are present, and `SECRET_KEY` is at least 32 characters.
- **Port already allocated:** set `API_PORT` in `.env` to a free host port, then recreate the API service. Compose override files cannot reliably replace the `ports` list across Compose versions.
- **Authentication fails after a secret change:** changing token/signing secrets can invalidate existing sessions; sign in again.
- **Feeds do not update:** inspect API logs, verify outbound network access, and test the feed URL directly. RSSHub routes may be unavailable independently of Readaria.
- **AI summaries or podcasts fail:** verify model availability, credentials, provider quotas, and TTS configuration. Podcast generation needs both services.
- **Audio cannot play:** check API logs and browser network errors, then confirm the configured audio cache directory is writable and your reverse proxy supports audio responses.
- **CORS errors:** set `CORS_ALLOWED_ORIGINS` to the exact HTTP(S) origin of the frontend and recreate the API service.
- **Out of disk space:** inspect Docker volumes and the audio cache, then adjust cache retention only after preserving any data you need.

For application bugs, open a GitHub issue with reproduction steps and redacted logs. Never post credentials, cookies, tokens, private feed URLs, or database dumps.
