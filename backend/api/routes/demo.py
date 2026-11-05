"""Opt-in public demo routes with database-backed curated content.

The visitor's BYOK credential is deliberately scoped to the summary request. It
must never be logged, included in error responses, or persisted.
"""

from contextlib import closing
from datetime import datetime, timezone
from dataclasses import dataclass
import ipaddress
import logging
from pathlib import Path
import socket
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from fastapi import APIRouter, Header, HTTPException, Request
from httpcore._backends.sync import SyncBackend
from openai import OpenAI
from pydantic import BaseModel, Field, model_validator
import httpx
import psycopg2
from psycopg2.extras import RealDictCursor

from backend.nlp.openai_client import _build_completion_params


logger = logging.getLogger(__name__)

_RATE_LIMIT_TTL_SECONDS = 60 * 60 * 48
_PROVIDER_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class _PublicURL:
    url: str
    host: str
    addresses: tuple[str, ...]


class _PinnedNetworkBackend(SyncBackend):
    """Connect only to the addresses validated for one outbound hostname."""

    def __init__(self, host: str, addresses: tuple[str, ...]):
        self._host = host.lower()
        self._addresses = addresses

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host.lower() != self._host:
            raise ValueError("Outbound host does not match the validated URL")
        last_error = None
        for address in self._addresses:
            try:
                # httpcore still performs TLS with the original hostname, so
                # pinning the TCP address does not weaken SNI/cert validation.
                return super().connect_tcp(
                    address, port, timeout, local_address, socket_options
                )
            except Exception as error:
                last_error = error
        raise last_error


def _create_pinned_http_client(validated_url: _PublicURL, timeout: float) -> httpx.Client:
    transport = httpx.HTTPTransport(trust_env=False)
    # httpx exposes no public network_backend argument; httpcore's supported
    # backend hook is installed before the pool creates any connections.
    transport._pool._network_backend = _PinnedNetworkBackend(
        validated_url.host, validated_url.addresses
    )
    return httpx.Client(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
    )


_DEMO_CURATOR_ID = "00000000-0000-0000-0000-00000000d3m0"


def _create_demo_connection(settings):
    return psycopg2.connect(**settings.postgres_config)


def _load_registry(settings):
    """Load public demo fields only; internal feed/user data stays in the DB."""
    with closing(_create_demo_connection(settings)) as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT p.share_token, p.title, p.duration, p.created_at
                FROM demo_content_registry r
                JOIN podcasts p ON p.id = r.podcast_id
                WHERE r.kind = 'podcast'
                ORDER BY r.sort_order, r.created_at, r.demo_id
                """
            )
            podcasts = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT
                    r.demo_id,
                    ga.title,
                    ga.author,
                    ga.published_at,
                    ga.language,
                    ga.url AS original_url,
                    ga.content AS excerpt,
                    r.tts_audio_path,
                    (
                        SELECT uf.feed_name
                        FROM user_article_refs uar
                        JOIN user_feeds uf ON uf.id = uar.feed_id
                        WHERE uar.user_id = %s
                          AND uar.global_article_id = ga.id
                        ORDER BY uar.id
                        LIMIT 1
                    ) AS source_name,
                    COALESCE(
                        (
                            SELECT s.summary
                            FROM article_summaries s
                            WHERE s.global_article_id = ga.id
                            ORDER BY s.generated_at DESC, s.id DESC
                            LIMIT 1
                        ),
                        ga.summary
                    ) AS summary
                FROM demo_content_registry r
                JOIN global_articles ga ON ga.id = r.global_article_id
                WHERE r.kind = 'article'
                ORDER BY r.sort_order, r.created_at, r.demo_id
                """,
                (_DEMO_CURATOR_ID,),
            )
            articles = [dict(row) for row in cursor.fetchall()]

    for article in articles:
        tts_audio_path = article.pop("tts_audio_path")
        article["audio_url"] = (
            f"/static/demo/audio/{Path(tts_audio_path).name}" if tts_audio_path else None
        )
    return {"podcasts": podcasts, "articles": articles}


def _article_list_item(article):
    return {
        key: article.get(key)
        for key in ("demo_id", "title", "source_name", "summary", "excerpt")
    }


class DemoSummaryRequest(BaseModel):
    content: Optional[str] = Field(default=None, max_length=12_000)
    url: Optional[str] = Field(default=None, max_length=2_048)
    turnstile_token: Optional[str] = Field(default=None, max_length=2_048)

    @model_validator(mode="after")
    def validate_article_source(self):
        has_content = bool(self.content and self.content.strip())
        has_url = bool(self.url and self.url.strip())
        if has_content == has_url:
            raise ValueError("Provide exactly one of content or url")
        return self


def _validate_public_url(url: str, *, https_only: bool = False) -> _PublicURL:
    """Resolve once and reject local networks before an outbound connection."""
    candidate = url.strip()
    parsed = urlparse(candidate)
    allowed_schemes = {"https"} if https_only else {"http", "https"}
    if (
        parsed.scheme.lower() not in allowed_schemes
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("URL must be a public HTTP(S) URL without credentials")
    if https_only and (parsed.query or parsed.fragment):
        raise ValueError("Provider base URL cannot contain a query or fragment")

    host = parsed.hostname.rstrip(".").lower()
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    try:
        address_info = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        resolved_ips = tuple({address[4][0] for address in address_info})
    except (OSError, ValueError):
        raise ValueError("URL host could not be resolved")
    if not resolved_ips or any(not ipaddress.ip_address(ip).is_global for ip in resolved_ips):
        raise ValueError("URL must resolve only to public IP addresses")
    return _PublicURL(candidate.rstrip("/"), host, resolved_ips)


def _fetch_article_content(url: str) -> str:
    """Fetch bounded public article text through the validated IP address."""
    validated_url = _validate_public_url(url)
    chunks = []
    downloaded = 0
    with _create_pinned_http_client(validated_url, timeout=15.0) as client:
        with client.stream("GET", validated_url.url) as response:
            if 300 <= response.status_code < 400:
                raise ValueError("Article URL redirects are not allowed")
            response.raise_for_status()
            for chunk in response.iter_bytes():
                downloaded += len(chunk)
                if downloaded > 500_000:
                    raise ValueError("Article response is too large")
                chunks.append(chunk)
    html = b"".join(chunks).decode("utf-8", errors="replace")
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    if not text:
        raise ValueError("Article has no readable text")
    return text[:12_000]


def _verify_turnstile(secret: str, token: Optional[str], ip_address: str) -> None:
    if not secret:
        return
    if not token:
        raise HTTPException(status_code=403, detail="Demo verification is required")
    try:
        response = httpx.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": secret, "response": token, "remoteip": ip_address},
            timeout=10.0,
        )
        response.raise_for_status()
        verified = bool(response.json().get("success"))
    except Exception:
        logger.error("Demo Turnstile verification request failed")
        raise HTTPException(status_code=503, detail="Demo verification is unavailable")
    if not verified:
        raise HTTPException(status_code=403, detail="Demo verification failed")


def create_demo_router(settings, redis_client) -> APIRouter:
    """Build demo routes with injectable settings and Redis for isolated tests."""
    router = APIRouter(prefix="/api/demo", tags=["demo"])

    @router.get("/content")
    def get_demo_content():
        content = _load_registry(settings)
        return {
            "podcasts": content["podcasts"],
            "articles": [_article_list_item(article) for article in content["articles"]],
        }

    @router.get("/articles")
    def get_demo_articles():
        content = _load_registry(settings)
        return {"articles": [_article_list_item(article) for article in content["articles"]]}

    @router.get("/articles/{demo_id}")
    def get_demo_article(demo_id: str):
        content = _load_registry(settings)
        article = next(
            (item for item in content["articles"] if item["demo_id"] == demo_id), None
        )
        if article is None:
            raise HTTPException(status_code=404, detail="Demo article not found")
        return article

    @router.post("/summary")
    def create_demo_summary(
        payload: DemoSummaryRequest,
        request: Request,
        x_demo_api_key: str = Header(default="", alias="x-demo-api-key", max_length=512),
        x_demo_base_url: str = Header(default="", alias="x-demo-base-url", max_length=2_048),
    ):
        if not settings.demo_mode:
            raise HTTPException(status_code=404, detail="Not found")
        api_key = x_demo_api_key.strip()
        if not api_key:
            raise HTTPException(status_code=400, detail="An API key is required for interactive demo mode")

        ip_address = request.client.host if request.client else "unknown"
        _verify_turnstile(
            settings.demo_turnstile_secret_key, payload.turnstile_token, ip_address
        )

        date = datetime.now(timezone.utc).date().isoformat()
        rate_limit_key = f"demo:ip:{date}:{ip_address}"
        try:
            interaction_count = redis_client.incr(rate_limit_key)
            if interaction_count == 1:
                redis_client.expire(rate_limit_key, _RATE_LIMIT_TTL_SECONDS)
        except Exception:
            logger.error("Demo interaction rate limiter is unavailable")
            raise HTTPException(status_code=503, detail="Interactive demo is temporarily unavailable")
        if interaction_count > settings.demo_daily_interaction_limit:
            raise HTTPException(status_code=429, detail="Daily demo interaction limit reached")

        base_url = settings.openai_base_url
        provider_http_client = None
        if x_demo_base_url.strip():
            try:
                validated_url = _validate_public_url(x_demo_base_url, https_only=True)
                base_url = validated_url.url
                provider_http_client = _create_pinned_http_client(
                    validated_url, timeout=_PROVIDER_TIMEOUT_SECONDS
                )
            except ValueError:
                raise HTTPException(status_code=400, detail="Provider base URL must be a public HTTPS URL")

        if payload.url:
            try:
                article_content = _fetch_article_content(payload.url)
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error))
            except Exception:
                logger.error("Demo article fetch failed")
                raise HTTPException(status_code=502, detail="The article could not be fetched")
        else:
            article_content = payload.content.strip()

        client = None
        try:
            client_options = {
                "api_key": api_key,
                "base_url": base_url,
                "timeout": _PROVIDER_TIMEOUT_SECONDS,
                "max_retries": 0,
            }
            if provider_http_client is not None:
                client_options["http_client"] = provider_http_client
            client = OpenAI(**client_options)
            completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "Summarize the supplied article in at most three concise sentences. Use the article's language.",
                    },
                    {"role": "user", "content": article_content},
                ],
                **_build_completion_params(
                    settings.openai_model, temperature=0.3, max_tokens=300, extra={}
                ),
            )
            summary = completion.choices[0].message.content
            if not summary:
                raise ValueError("Empty provider summary")
            return {"summary": summary.strip()}
        except Exception:
            # Provider exceptions may echo request data; never log or return them.
            logger.error("Demo summary provider request failed")
            raise HTTPException(status_code=502, detail="The AI provider could not generate a summary")
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    logger.error("Demo provider client cleanup failed")

    return router


__all__ = ["create_demo_router"]
