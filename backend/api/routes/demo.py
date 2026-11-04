"""Opt-in, zero-database demo routes.

The visitor's BYOK credential is deliberately scoped to the summary request. It
must never be logged, included in error responses, or persisted.
"""

from datetime import datetime, timezone
from dataclasses import dataclass
import ipaddress
import logging
import socket
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from fastapi import APIRouter, Header, HTTPException, Request
from httpcore._backends.sync import SyncBackend
from openai import OpenAI
from pydantic import BaseModel, Field, model_validator
import httpx

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


DEMO_ARTICLES = [
    {
        "id": "hacker-news",
        "title": "Hacker News: Community-curated technology",
        "url": "https://news.ycombinator.com/",
        "source": {
            "name": "Hacker News",
            "feed_url": "https://hnrss.org/frontpage",
        },
        "summary": "A seeded preview of Readaria's AI summary: Hacker News surfaces community-selected stories about software, startups, science, and technology culture.",
        "podcast_audio_url": "/static/demo/readaria-demo-en.mp3",
        "content": "Hacker News is a social news website focusing on computer science and entrepreneurship. Its community shares and discusses technology, science, and startup stories.",
    },
    {
        "id": "sspai",
        "title": "少数派：高效工作与数字生活",
        "url": "https://sspai.com/",
        "source": {"name": "少数派", "feed_url": "https://sspai.com/feed"},
        "summary": "这是预生成的演示摘要：少数派关注数字工具、效率方法与消费科技，帮助读者更好地选择和使用技术产品。",
        "podcast_audio_url": "/static/demo/readaria-demo-zh.mp3",
        "content": "少数派是一个关注数字生活与工作效率的中文内容平台，文章涵盖应用技巧、设备体验、自动化和生活方式。",
    },
    {
        "id": "ruanyifeng",
        "title": "阮一峰的网络日志：技术周刊",
        "url": "https://www.ruanyifeng.com/blog/",
        "source": {
            "name": "阮一峰的网络日志",
            "feed_url": "https://www.ruanyifeng.com/blog/atom.xml",
        },
        "summary": "这是预生成的演示摘要：技术周刊汇集软件开发、互联网趋势与科技评论，为读者提供每周技术动态。",
        "podcast_audio_url": "/static/demo/readaria-demo-zh.mp3",
        "content": "阮一峰的网络日志长期分享编程教程、互联网评论和每周科技动态，技术周刊整理一周值得关注的技术文章与工具。",
    },
    {
        "id": "solidot",
        "title": "Solidot: Technology and open-source news",
        "url": "https://www.solidot.org/",
        "source": {
            "name": "Solidot",
            "feed_url": "https://www.solidot.org/index.rss",
        },
        "summary": "A seeded preview of Readaria's AI summary: Solidot covers open-source software, science, security, and developments across the technology industry.",
        "podcast_audio_url": "/static/demo/readaria-demo-en.mp3",
        "content": "Solidot is a Chinese-language technology news site covering open source, science, security, and the wider computing industry.",
    },
    {
        "id": "ars-technica",
        "title": "Ars Technica: In-depth technology reporting",
        "url": "https://arstechnica.com/",
        "source": {
            "name": "Ars Technica",
            "feed_url": "https://feeds.arstechnica.com/arstechnica/index",
        },
        "summary": "A seeded preview of Readaria's AI summary: Ars Technica provides detailed reporting and analysis on computing, science, policy, and gaming.",
        "podcast_audio_url": "/static/demo/readaria-demo-en.mp3",
        "content": "Ars Technica publishes technology news, long-form analysis, reviews, and reporting on science, IT, public policy, and gaming.",
    },
    {
        "id": "mit-technology-review",
        "title": "MIT Technology Review: Emerging technology",
        "url": "https://www.technologyreview.com/",
        "source": {
            "name": "MIT Technology Review",
            "feed_url": "https://www.technologyreview.com/feed/",
        },
        "summary": "A seeded preview of Readaria's AI summary: MIT Technology Review examines emerging technologies and their effects on business, science, and society.",
        "podcast_audio_url": "/static/demo/readaria-demo-en.mp3",
        "content": "MIT Technology Review reports on emerging technologies including artificial intelligence, biotechnology, climate technology, and computing, with attention to their social impact.",
    },
]


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
        return {"articles": DEMO_ARTICLES, "audio_note": "Short seeded demo audio files; no API calls are made in showcase mode."}

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


__all__ = ["create_demo_router", "DEMO_ARTICLES"]
