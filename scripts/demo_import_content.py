#!/usr/bin/env python3
"""Import curated, real content for the public Readaria demo.

The input JSON contains podcast/article records and optionally references audio
files in an ``audio/`` directory next to it. All database work is idempotent and
runs in one transaction. ``--dry-run`` never opens a database connection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import shutil
import sys
from typing import Any
from urllib.parse import urlparse

import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_CURATOR_ID = "00000000-0000-0000-0000-00000000d3m0"
DEMO_CURATOR_USERNAME = "demo-curator"
DEMO_CURATOR_EMAIL = "demo-curator@demo.invalid"


def _source_slug(source_name: str) -> str:
    normalized = source_name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    if slug:
        return slug
    digest = hashlib.sha256(source_name.strip().encode("utf-8")).hexdigest()[:12]
    return f"source-{digest}"


def _reading_metrics(text: str, language: str) -> tuple[int, int]:
    text = text.strip()
    word_count = len(text.split()) if language.lower().startswith("en") else len(text)
    return word_count, max(1, math.ceil(word_count / 200))


def _validate_http_url(url: str, label: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} must use an http/https URL")


def _validate_input(data: dict[str, Any]) -> None:
    for section in ("podcasts", "articles"):
        if not isinstance(data.get(section, []), list):
            raise ValueError(f"{section} must be a list")

    article_required = ("demo_id", "title", "url", "source_name", "summary", "excerpt")
    for article in data.get("articles", []):
        missing = [key for key in article_required if not article.get(key)]
        if missing:
            raise ValueError(f"Article is missing required fields: {', '.join(missing)}")
        _validate_http_url(article["url"], f"Article {article['demo_id']} URL")

    podcast_required = ("demo_id", "title", "audio_file")
    for podcast in data.get("podcasts", []):
        missing = [key for key in podcast_required if not podcast.get(key)]
        if missing:
            raise ValueError(f"Podcast is missing required fields: {', '.join(missing)}")
        share_token = f"demo-{podcast['demo_id']}"
        if len(share_token) > 32:
            raise ValueError(f"Podcast demo_id produces an overlong share_token: {share_token}")
        for story in podcast.get("stories", []):
            if story.get("url"):
                _validate_http_url(
                    story["url"], f"Podcast {podcast['demo_id']} story URL"
                )


def _audio_plan(data: dict[str, Any], input_path: Path, settings) -> list[dict[str, str]]:
    plan = []
    for podcast in data.get("podcasts", []):
        basename = Path(podcast["audio_file"]).name
        plan.append(
            {
                "source": str(input_path.parent / "audio" / basename),
                "destination": str(Path(settings.podcast_audio_cache_dir) / basename),
            }
        )
    for article in data.get("articles", []):
        if not article.get("tts_audio_file"):
            continue
        basename = Path(article["tts_audio_file"]).name
        plan.append(
            {
                "source": str(input_path.parent / "audio" / basename),
                "destination": str(PROJECT_ROOT / "backend" / "static" / "demo" / "audio" / basename),
            }
        )
    return plan


def _print_dry_run(data: dict[str, Any], input_path: Path, settings, wipe: bool) -> None:
    plan = {
        "dry_run": True,
        "operation": "wipe" if wipe else "import",
        "demo_curator_id": DEMO_CURATOR_ID,
        "podcasts": data.get("podcasts", []),
        "articles": data.get("articles", []),
        "audio_copies": _audio_plan(data, input_path, settings),
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2, default=str))


def _copy_audio(source: Path, destination: Path) -> bool:
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        print(f"Copied audio: {source} -> {destination}")
        return True
    if destination.is_file():
        print(f"Audio source absent; keeping existing destination: {destination}")
        return True
    print(f"Warning: audio file not found, skipping copy: {source}", file=sys.stderr)
    return False


def _ensure_curator(cursor) -> None:
    # The random secret is intentionally discarded and never logged. The account
    # is also inactive and excluded from all automatic content generation.
    random_password_hash = bcrypt.hashpw(
        secrets.token_urlsafe(48).encode("utf-8"), bcrypt.gensalt()
    ).decode("ascii")
    cursor.execute(
        """
        INSERT INTO users (
            id, username, email, full_name, password_hash, is_active,
            is_superuser, auto_refresh_enabled, auto_podcast_enabled, auth_provider
        ) VALUES (%s, %s, %s, %s, %s, FALSE, FALSE, FALSE, FALSE, 'password')
        ON CONFLICT DO NOTHING
        """,
        (
            DEMO_CURATOR_ID,
            DEMO_CURATOR_USERNAME,
            DEMO_CURATOR_EMAIL,
            "Readaria Demo Curator",
            random_password_hash,
        ),
    )


def _ensure_feed(cursor, source_name: str) -> tuple[int, str]:
    feed_url = f"demo://source/{_source_slug(source_name)}"
    cursor.execute(
        """
        INSERT INTO user_feeds (
            user_id, source_type_id, feed_name, feed_url, is_active, platform
        ) VALUES (%s, 'rss', %s, %s, TRUE, 'rss')
        ON CONFLICT (user_id, feed_url) DO NOTHING
        RETURNING id
        """,
        (DEMO_CURATOR_ID, source_name, feed_url),
    )
    row = cursor.fetchone()
    if row is None:
        cursor.execute(
            "SELECT id FROM user_feeds WHERE user_id = %s AND feed_url = %s",
            (DEMO_CURATOR_ID, feed_url),
        )
        row = cursor.fetchone()
    return row["id"], feed_url


def _ensure_global_article(cursor, article: dict[str, Any], feed_url: str) -> int:
    cursor.execute(
        """
        SELECT id, title, author, published_at, content, summary, source_feed_url,
               source_type_id, language, word_count, reading_time
        FROM global_articles
        WHERE url = %s
        """,
        (article["url"],),
    )
    row = cursor.fetchone()
    excerpt = article["excerpt"]
    language = article.get("language", "zh")
    word_count, reading_time = _reading_metrics(excerpt, language)
    curated_values = {
        "title": article["title"],
        "author": article.get("author"),
        "published_at": article.get("published_at"),
        "content": excerpt,
        "summary": article["summary"],
        "source_feed_url": feed_url,
        "source_type_id": "rss",
        "language": language,
        "word_count": word_count,
        "reading_time": reading_time,
    }
    if row:
        # URL collisions must not leak previously fetched private content through
        # the public demo. Mark and converge the shared row to the curated input.
        # The row comparison prevents no-op updates from advancing timestamps.
        cursor.execute(
            """
            UPDATE global_articles
            SET title = %(title)s,
                author = %(author)s,
                published_at = %(published_at)s,
                content = %(content)s,
                summary = %(summary)s,
                source_feed_url = %(source_feed_url)s,
                source_type_id = %(source_type_id)s,
                language = %(language)s,
                word_count = %(word_count)s,
                reading_time = %(reading_time)s
            WHERE id = %(id)s
              AND (
                  title, author, published_at, content, summary, source_feed_url,
                  source_type_id, language, word_count, reading_time
              ) IS DISTINCT FROM (
                  %(title)s, %(author)s, %(published_at)s, %(content)s,
                  %(summary)s, %(source_feed_url)s, %(source_type_id)s,
                  %(language)s, %(word_count)s, %(reading_time)s
              )
            """,
            {**curated_values, "id": row["id"]},
        )
        return row["id"]

    cursor.execute(
        """
        INSERT INTO global_articles (
            url, content_hash, title, author, published_at, content, summary,
            source_feed_url, source_type_id, language, word_count, reading_time
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'rss', %s, %s, %s)
        RETURNING id
        """,
        (
            article["url"],
            hashlib.md5(article["url"].encode("utf-8")).hexdigest(),
            article["title"],
            article.get("author"),
            article.get("published_at"),
            excerpt,
            article["summary"],
            feed_url,
            language,
            word_count,
            reading_time,
        ),
    )
    return cursor.fetchone()["id"]


def _ensure_legacy_article(
    cursor, article: dict[str, Any], feed_id: int, feed_url: str
) -> int:
    excerpt = article["excerpt"]
    language = article.get("language", "zh")
    word_count, reading_time = _reading_metrics(excerpt, language)
    cursor.execute(
        """
        INSERT INTO articles (
            feed_id, source_type_id, title, url, author, published_at, summary,
            content, content_hash, language, word_count, reading_time, source
        ) VALUES (%s, 'rss', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (feed_id, url) DO NOTHING
        RETURNING id
        """,
        (
            feed_id,
            article["title"],
            article["url"],
            article.get("author"),
            article.get("published_at"),
            article["summary"],
            excerpt,
            hashlib.md5(article["url"].encode("utf-8")).hexdigest(),
            language,
            word_count,
            reading_time,
            feed_url,
        ),
    )
    row = cursor.fetchone()
    if row is None:
        cursor.execute(
            "SELECT id FROM articles WHERE feed_id = %s AND url = %s",
            (feed_id, article["url"]),
        )
        row = cursor.fetchone()
    return row["id"]


def _import_article(cursor, article: dict[str, Any], tts_audio_path: str | None) -> None:
    feed_id, feed_url = _ensure_feed(cursor, article["source_name"])
    global_article_id = _ensure_global_article(cursor, article, feed_url)
    legacy_article_id = _ensure_legacy_article(cursor, article, feed_id, feed_url)
    cursor.execute(
        """
        INSERT INTO user_article_refs (
            user_id, global_article_id, legacy_article_id, feed_id, user_summary
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id, global_article_id, feed_id) DO UPDATE SET
            legacy_article_id = EXCLUDED.legacy_article_id,
            user_summary = EXCLUDED.user_summary
        """,
        (
            DEMO_CURATOR_ID,
            global_article_id,
            legacy_article_id,
            feed_id,
            article["summary"],
        ),
    )
    language = article.get("language", "zh")
    cursor.execute(
        """
        INSERT INTO article_summaries (global_article_id, language, summary)
        VALUES (%s, %s, %s)
        ON CONFLICT (global_article_id, language) DO UPDATE SET
            summary = EXCLUDED.summary,
            generated_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE article_summaries.summary IS DISTINCT FROM EXCLUDED.summary
        """,
        (global_article_id, language, article["summary"]),
    )
    cursor.execute(
        """
        INSERT INTO demo_content_registry (
            demo_id, kind, global_article_id, tts_audio_path, sort_order
        ) VALUES (%s, 'article', %s, %s, %s)
        ON CONFLICT (demo_id) DO UPDATE SET
            kind = EXCLUDED.kind,
            podcast_id = NULL,
            global_article_id = EXCLUDED.global_article_id,
            tts_audio_path = EXCLUDED.tts_audio_path,
            sort_order = EXCLUDED.sort_order
        """,
        (
            article["demo_id"],
            global_article_id,
            tts_audio_path,
            article.get("sort_order", 0),
        ),
    )


def _ensure_podcast(cursor, podcast: dict[str, Any]) -> int:
    share_token = f"demo-{podcast['demo_id']}"
    audio_url = f"/app/podcast_cache/{Path(podcast['audio_file']).name}"
    cursor.execute(
        """
        INSERT INTO podcasts (
            user_id, title, description, duration, generation_status,
            generation_completed_at, audio_url, source, share_token
        ) VALUES (%s, %s, %s, %s, 'completed', CURRENT_TIMESTAMP, %s, 'demo', %s)
        ON CONFLICT (share_token) DO UPDATE SET
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            duration = EXCLUDED.duration,
            generation_status = 'completed',
            generation_completed_at = CURRENT_TIMESTAMP,
            audio_url = EXCLUDED.audio_url,
            source = 'demo'
        WHERE podcasts.user_id = %s
          AND (
              podcasts.title, podcasts.description, podcasts.duration,
              podcasts.generation_status, podcasts.audio_url, podcasts.source
          ) IS DISTINCT FROM (
              EXCLUDED.title, EXCLUDED.description, EXCLUDED.duration,
              EXCLUDED.generation_status, EXCLUDED.audio_url, EXCLUDED.source
          )
        RETURNING id
        """,
        (
            DEMO_CURATOR_ID,
            podcast["title"],
            podcast.get("description"),
            podcast.get("duration"),
            audio_url,
            share_token,
            DEMO_CURATOR_ID,
        ),
    )
    row = cursor.fetchone()
    if row is None:
        # A content-identical upsert deliberately returns no row. Resolve the
        # existing demo podcast while still rejecting another owner's token.
        cursor.execute(
            "SELECT id, user_id FROM podcasts WHERE share_token = %s",
            (share_token,),
        )
        row = cursor.fetchone()
        if row is None or row["user_id"] != DEMO_CURATOR_ID:
            raise ValueError(
                f"Podcast share_token is already used by another account: {share_token}"
            )
    return row["id"]


def _link_podcast_stories(cursor, podcast_id: int, stories: list[dict[str, Any]]) -> None:
    for sequence_order, story in enumerate(stories):
        url = story.get("url")
        if not url:
            print("Warning: podcast story has no URL, skipping", file=sys.stderr)
            continue
        cursor.execute(
            """
            SELECT uar.global_article_id, uar.legacy_article_id
            FROM user_article_refs uar
            JOIN global_articles ga ON ga.id = uar.global_article_id
            WHERE uar.user_id = %s AND ga.url = %s
              AND uar.legacy_article_id IS NOT NULL
            ORDER BY uar.id
            LIMIT 1
            """,
            (DEMO_CURATOR_ID, url),
        )
        row = cursor.fetchone()
        if row is None:
            print(f"Warning: demo article not found for podcast story URL: {url}", file=sys.stderr)
            continue
        cursor.execute(
            """
            INSERT INTO podcast_articles (
                podcast_id, article_id, global_article_id, sequence_order
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (podcast_id, article_id) DO UPDATE SET
                global_article_id = EXCLUDED.global_article_id,
                sequence_order = EXCLUDED.sequence_order
            """,
            (
                podcast_id,
                row["legacy_article_id"],
                row["global_article_id"],
                sequence_order,
            ),
        )


def _import_podcast(cursor, podcast: dict[str, Any]) -> None:
    podcast_id = _ensure_podcast(cursor, podcast)
    _link_podcast_stories(cursor, podcast_id, podcast.get("stories", []))
    cursor.execute(
        """
        INSERT INTO demo_content_registry (
            demo_id, kind, podcast_id, sort_order
        ) VALUES (%s, 'podcast', %s, %s)
        ON CONFLICT (demo_id) DO UPDATE SET
            kind = EXCLUDED.kind,
            podcast_id = EXCLUDED.podcast_id,
            global_article_id = NULL,
            tts_audio_path = NULL,
            sort_order = EXCLUDED.sort_order
        """,
        (podcast["demo_id"], podcast_id, podcast.get("sort_order", 0)),
    )


def _wipe(cursor) -> None:
    # Registry rows go first so content deletion cannot cascade away row counts
    # before the operation is reported. Feeds cascade to articles and refs;
    # podcasts cascade to podcast_articles. Shared global_articles remain.
    cursor.execute(
        """
        DELETE FROM demo_content_registry AS r
        WHERE (
            r.podcast_id IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM podcasts p
                WHERE p.id = r.podcast_id AND p.user_id = %s
            )
        ) OR (
            r.global_article_id IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM global_articles ga
                WHERE ga.id = r.global_article_id
                  AND ga.source_feed_url LIKE %s
            )
        )
        """,
        (DEMO_CURATOR_ID, "demo://%"),
    )
    registry_count = cursor.rowcount
    cursor.execute("DELETE FROM podcasts WHERE user_id = %s", (DEMO_CURATOR_ID,))
    podcast_count = cursor.rowcount
    cursor.execute("DELETE FROM user_feeds WHERE user_id = %s", (DEMO_CURATOR_ID,))
    feed_count = cursor.rowcount
    print(
        f"Wiped demo content: {registry_count} registry rows, "
        f"{podcast_count} podcasts, {feed_count} feeds (articles/refs cascade)"
    )


def import_content(data: dict[str, Any], input_path: Path, settings, dsn: str | None = None) -> None:
    connection = (
        psycopg2.connect(dsn) if dsn else psycopg2.connect(**settings.postgres_config)
    )
    try:
        with connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                _ensure_curator(cursor)
                # Articles are imported first so podcast stories in the same
                # input can resolve their demo article references by URL.
                for article in data.get("articles", []):
                    tts_audio_path = None
                    if article.get("tts_audio_file"):
                        basename = Path(article["tts_audio_file"]).name
                        destination = PROJECT_ROOT / "backend" / "static" / "demo" / "audio" / basename
                        if _copy_audio(input_path.parent / "audio" / basename, destination):
                            tts_audio_path = str(destination)
                    _import_article(cursor, article, tts_audio_path)
                for podcast in data.get("podcasts", []):
                    basename = Path(podcast["audio_file"]).name
                    _copy_audio(
                        input_path.parent / "audio" / basename,
                        Path(settings.podcast_audio_cache_dir) / basename,
                    )
                    _import_podcast(cursor, podcast)
    finally:
        connection.close()


def wipe_content(settings, dsn: str | None = None) -> None:
    connection = (
        psycopg2.connect(dsn) if dsn else psycopg2.connect(**settings.postgres_config)
    )
    try:
        with connection:
            with connection.cursor() as cursor:
                _wipe(cursor)
    finally:
        connection.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Path to the demo content JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without any writes or DB connection")
    parser.add_argument("--wipe", action="store_true", help="Remove demo registry and demo-curator content")
    parser.add_argument("--dsn", help="Optional PostgreSQL DSN override")
    args = parser.parse_args()
    if not args.wipe and not args.input:
        parser.error("--input is required unless --wipe is used")
    return args


def main() -> None:
    args = _parse_args()
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from core.config.settings import settings

    input_path = args.input.resolve() if args.input else PROJECT_ROOT / "demo-content.json"
    data: dict[str, Any] = {"podcasts": [], "articles": []}
    if args.input:
        with input_path.open("r", encoding="utf-8") as input_file:
            data = json.load(input_file)
        _validate_input(data)

    if args.dry_run:
        _print_dry_run(data, input_path, settings, args.wipe)
        return
    if args.wipe:
        wipe_content(settings, args.dsn)
        return
    import_content(data, input_path, settings, args.dsn)
    print(
        f"Imported {len(data.get('podcasts', []))} podcasts and "
        f"{len(data.get('articles', []))} articles"
    )


if __name__ == "__main__":
    main()
